import fcntl
import gzip
import io
import itertools
import os
import tempfile
import traceback
import urlparse
import weakref
from collections import defaultdict, namedtuple

import requests
from lxml import etree

from .rpmutils import evrcmp, EVR, split_rpm_filename


class Session(object):
    __state = {}
    _session = None

    def __init__(self):
        self.__dict__ = self.__state

    @property
    def session(self):
        if self._session is None:
            self._session = requests.Session()
        return self._session


def str_eq(a, b):
    # TODO drop this on python3 port
    if isinstance(a, unicode):
        a = a.encode('utf-8', 'replace')
    if isinstance(b, unicode):
        b = b.encode('utf-8', 'replace')
    return a == b


def fast_iter(context):
    """
    http://stackoverflow.com/questions/12160418/why-is-lxml-etree-iterparse-eating-up-all-my-memory/12161078#12161078
    http://lxml.de/parsing.html#modifying-the-tree
    Based on Liza Daly's fast_iter
    http://www.ibm.com/developerworks/xml/library/x-hiperfparse/
    See also http://effbot.org/zone/element-iterparse.htm
    Modified to act as a generator instead of using a callback
    """
    for event, elem in context:
        yield elem
        # It's safe to call clear() here because no descendants will be
        # accessed
        elem.clear()
        # Also eliminate now-empty references from the root node to elem
        for ancestor in elem.xpath('ancestor-or-self::*'):
            while ancestor.getprevious() is not None:
                del ancestor.getparent()[0]
    del context


class RepoSack(object):
    def __init__(self, repos):
        self.repos = repos
        self.ns = {}

    @property
    def base_packages(self):
        return itertools.chain.from_iterable(
            [repo.base_packages.viewitems() for repo in self.repos]
        )

    @property
    def packages(self):
        return itertools.chain.from_iterable(
            [repo.packages.viewitems() for repo in self.repos]
        )

    def get_ns(self, kind, nsmap):
        if kind not in self.ns:
            default_ns = nsmap[None]
            del(nsmap[None])
            nsmap['common'] = default_ns
            nsmap['re'] = 'http://exslt.org/regular-expressions'
            self.ns[kind] = nsmap
        return self.ns[kind]

    def search_name(self, query):
        for pkgtup, po in self.packages:
            for name in query:
                if name == po.name:
                    yield (po.name, po)

    def search_basename(self, query):
        for repo in self.repos:
            for name in query:
                po = repo.base_packages.get(name, None)
                if po:
                    yield (name, po)

    def search_name_contains(self, query, casei):
        if casei:
            query = [val.lower() for val in query]

        for pkgtup, po in self.packages:
            name = po.name.lower() if casei else po.name
            for res in itertools.ifilter(lambda q: q in name, query):
                yield (res, po)

    def search_basename_contains(self, query, casei):
        if casei:
            for i, val in enumerate(query):
                query[i] = val.lower()

        for name, po in self.base_packages:
            if casei:
                name = name.lower()
            for res in itertools.ifilter(lambda q: q in name, query):
                yield (res, po)

    def search_provides(self, query):
        for repo in self.repos:
            for pr in query:
                po = repo.provides.get(pr[0], None)
                if po:
                    yield (pr, po)

    def search_requires(self, query):
        for repo in self.repos:
            for qr in query:
                po = repo.requires.get(qr[0], None)
                if po:
                    yield (qr, po)

    def search_filenames(self, query):
        pkgnames = set()
        xp = None
        for repo in self.repos:
            for pkg in fast_iter(repo.filelists_md):
                if xp is None:
                    xp = etree.XPath(
                        "./common:file/text()",
                        namespaces=self.get_ns("filelists", pkg.nsmap),
                        smart_strings=False
                    )
                for filename in xp(pkg):
                    if filename in query:
                        pkgnames.add(pkg.attrib['name'])
        return self.search_name(pkgnames)

    def searchNames(self, name):
        for pkgtup, po in self.packages:
            if name == po.name:
                yield po

    # Yum API emulation
    def returnPackages(self):
        return itertools.chain.from_iterable(
            [repo.packages.viewvalues() for repo in self.repos]
        )

    def returnNewestByName(self, name=None):
        newest = {}
        for pkgtup, po in self.packages:
            if name is not None and name != po.name:
                continue

            cval = 1
            if po.name in newest:
                cval = po.verCMP(newest[po.name][0])
            if cval > 0:
                newest[po.name] = [po]
            elif cval == 0:
                newest[po.name].append(po)
        ret = []
        for vals in newest.itervalues():
            ret.extend(vals)
        return ret

    def searchPackages(self, fields, criteria_re, callback):
        matches = {}

        for po in self.returnPackages():
            tmpvalues = []
            for field in fields:
                value = getattr(po, field)
                if value and criteria_re.search(value):
                    tmpvalues.append(value)
            if len(tmpvalues) > 0:
                if callback:
                    callback(po, tmpvalues)
                matches[po] = tmpvalues

        return matches

    def searchFiles(self, name):
        """ Return list of packages by filename. """
        result = []
        for po in self.returnPackages():
            if name in po.files:
                result.append(po)
        return result

    def searchNevra(
        self, name=None, epoch=None, ver=None, rel=None, arch=None
    ):
        """return list of pkgobjects matching the nevra requested"""
        result = []
        for po in self.returnPackages():
            if (
                (name and name != po.name) or
                (epoch and epoch != po.epoch) or
                (ver and ver != po.ver) or
                (rel and rel != po.rel) or
                (arch and arch != po.arch)
            ):
                continue
            result.append(po)
        return result

    def getProvides(self, name, flags=None, version=(None, None, None)):
        return self.getPrco('provides', name, flags=None, version=version)

    def getRequires(self, name, flags=None, version=(None, None, None)):
        return self.getPrco('requires', name, flags=None, version=version)

    def getPrco(self, kind, name, flags=None, version=(None, None, None)):
        """return dict { packages -> list of matching provides }"""
        if version is None:
            version = (None, None, None)
        elif isinstance(version, basestring):
            version = EVR.from_string(version)
        result = {}
        for po in self.returnPackages():
            hits = po.matchingPrcos(kind, (name, flags, version))
            if hits:
                result[po] = hits
        if name[0] == '/':
            hit = (name, None, (None, None, None))
            for po in self.searchFiles(name):
                result.setdefault(po, []).append(hit)
        return result


class Repo(object):
    def __init__(self, repoid, baseurl, cachedir=None, ssl_verify=True):
        self.repoid = repoid
        self.baseurl = baseurl
        if not baseurl.endswith("/"):
            self.baseurl = baseurl + "/"

        if cachedir is None:
            cachedir = tempfile.mkdtemp()

        if not os.path.isdir(cachedir):
            os.makedirs(cachedir)

        self._cachedir = cachedir
        self._ssl_verify = ssl_verify
        self._revision = 0
        self._repomd = None
        self._mds = None
        self._patterns = None
        self._packages = None
        self._base_packages = None
        self._changelogs = None
        self._providx = None
        self._reqidx = None

        # Init cached properties
        self.repomd
        self.mds
        self.packages

    def __repr__(self):
        return "<Repo: %s>" % self.baseurl

    def read_cache(self, refresh=False):
        cached_file = os.path.join(self._cachedir, "repomd.xml")
        cached_revision = None

        if os.path.isfile(cached_file):
            with open(cached_file) as fd:
                fcntl.lockf(fd, fcntl.LOCK_SH)
                cached = etree.parse(fd)
                fcntl.lockf(fd, fcntl.LOCK_UN)
            cached_revision = cached.find("{*}revision").text

        if cached_revision != self.revision or refresh:
            self.refresh_cache()

        for mdfile in self.repomd.iterfind("{*}data"):
            cached_file = os.path.join(
                self._cachedir, mdfile.attrib["type"] + ".xml")
            self._mds[mdfile.attrib["type"]] = cached_file

        return True

    def refresh_cache(self):
        for mdfile in self.repomd.iterfind("{*}data"):
            req = Session().session.get(
                urlparse.urljoin(
                    self.baseurl, mdfile.find("{*}location").attrib["href"]
                ),
                verify=self._ssl_verify,
            )
            print req.url
            if not req.status_code == requests.codes.ok:
                req.raise_for_status()

            with io.BytesIO(req.content) as fd:
                gzfd = gzip.GzipFile(fileobj=fd)
                self.write_cache_file(
                    mdfile.attrib["type"] + ".xml", inputfd=gzfd)
        self.write_cache_file(
            "repomd.xml", content=etree.tostring(self.repomd))

    def write_cache_file(self, filename, content=None, inputfd=None):
        cached_file = os.path.join(self._cachedir, filename)
        with open(cached_file, "w") as fd:
            fcntl.lockf(fd, fcntl.LOCK_EX)
            if content:
                fd.write(content)
            if inputfd:
                fd.write(inputfd.read())
            fcntl.lockf(fd, fcntl.LOCK_UN)

    @property
    def repomd(self):
        if self._repomd is None:
            req = Session().session.get(
                urlparse.urljoin(self.baseurl, "repodata/repomd.xml"),
                verify=self._ssl_verify,
            )
            print req.url
            if req.status_code == requests.codes.ok:
                self._repomd = etree.fromstring(req.content)
                self.revision = self._repomd.find("{*}revision").text
            else:
                req.raise_for_status()

        return self._repomd

    @property
    def revision(self):
        return self._revision

    @revision.setter
    def revision(self, rev):
        self._revision = rev

    @property
    def mds(self):
        if self._mds is None:
            self._mds = {}
            if self.repomd is None:
                return self._mds

            try:
                self.read_cache()
            except Exception:
                traceback.print_exc()
                self._mds = {}

        return self._mds

    @property
    def primary_md(self):
        return etree.iterparse(
            self.mds["primary"],
            tag="{*}package", events=("end",),
            encoding='utf-8', recover=True
        )

    @property
    def filelists_md(self):
        return etree.iterparse(
            self.mds["filelists"],
            tag="{*}package", events=("end",),
            encoding='utf-8', recover=True
        )

    @property
    def other_md(self):
        return etree.iterparse(
            self.mds["other"],
            tag="{*}package", events=("end",),
            encoding='utf-8', recover=True
        )

    @property
    def patterns_md(self):
        return etree.iterparse(
            self.mds["patterns"],
            tag="{*}pattern", events=("end",),
            encoding='utf-8', recover=True
        )

    @property
    def patterns(self):
        if self._patterns is None and 'patterns' in self.mds:
            self._patterns = Patterns(self.patterns_md)
        return self._patterns

    @property
    def packages(self):
        if self._packages is None and 'primary' in self.mds:
            self._packages = {}
            for xml in fast_iter(self.primary_md):
                Package(weakref.proxy(self), xml)
        return self._packages

    @property
    def base_packages(self):
        if self._base_packages is None:
            self._base_packages = defaultdict(list)
            for po in self.packages.viewvalues():
                self._base_packages[po.basename].append(po)
        return self._base_packages

    @property
    def changelogs(self):
        if self._changelogs is None:
            self._changelogs = {}
            for xml in fast_iter(self.other_md):
                self._parse_chlog(xml)
        return self._changelogs

    def _parse_chlog(self, xml):
        if xml is None:
            return
        version = xml.find('{*}version')
        evrtup = EVR(
            version.attrib['epoch'],
            version.attrib['ver'],
            version.attrib['rel'],
        )
        pkgtup = (xml.attrib['name'], xml.attrib['arch']) + evrtup
        po = self.packages.get(pkgtup, None)
        if po:
            basetup = (po.basename,) + evrtup
            if basetup not in self._changelogs:
                self._changelogs[basetup] = [
                    Changelog(
                        entry.attrib['date'],
                        entry.attrib['author'],
                        text=entry.text
                    ) for entry in xml.iterfind("{*}changelog")
                ]

    @property
    def provides(self):
        # TODO should consider package arch and version too, not just name
        if self._providx is None:
            self._providx = {}
            for po in self.packages.viewvalues():
                for prov in po.provides:
                    self._providx[prov.name] = po
        return self._providx

    @property
    def requires(self):
        # TODO should consider package arch and version too, not just name
        if self._reqidx is None:
            self._reqidx = {}
            for po in self.packages.viewvalues():
                for req in po.requires:
                    self._reqidx[req.name] = po
        return self._reqidx


class Changelog(namedtuple("Changelog", ["time", "author_version", "text"])):
    def __init__(self, *args, **kwargs):
        super(Changelog, self).__init__(*args, **kwargs)
        try:
            author, version = self.author_version.rsplit(None, 1)
        except ValueError:
            author = self.author_version
            version = '0'
        author = author.rstrip(' -')
        self.author = author
        self.version = version


class Capability(namedtuple("Capability", ["name", "flag", "EVR"])):
    def __str__(self):

        e, v, r = self.EVR
        flags = {
            'GT': '>',
            'GE': '>=',
            'EQ': '=',
            'LT': '<',
            'LE': '<='
        }
        if self.flag is None:
            return self.name

        return '%s %s %s' % (self.name, flags[self.flag], self.EVR)


class Package(object):
    def __init__(self, repo, pkg):
        self.repoid = repo.repoid
        self.repo = repo
        self.name = None
        self.checksum = None
        self.version = EVR(None, None, None)
        self.arch = None
        self._sourcerpm = None
        self._license = None
        self._group = None
        self._vendor = None
        self.description = None
        self.summary = None
        self._filelist = None
        self._ghost = None
        self._dir = None
        self._conflicts = None
        self._requires = None
        self._provides = None
        self._obsoletes = None

        for elem in pkg.iterchildren():
            if etree.QName(elem.tag).localname == "location":
                self.location = elem.attrib["href"]
            elif etree.QName(elem.tag).localname == "version":
                self.version = EVR(
                    elem.attrib["epoch"],
                    elem.attrib["ver"],
                    elem.attrib["rel"]
                )
            elif etree.QName(elem.tag).localname == "format":
                self.format_xml = elem
            else:
                setattr(self, etree.QName(elem.tag).localname, elem.text)

        if not self.arch == "src":
            self.repo._packages[self.pkgtup] = self

    def __repr__(self):
        return "<Package: %s %s %s>" % (self.name, self.arch, self.version)

    @property
    def sourcerpm(self):
        if self._sourcerpm is None:
            xml = self.format_xml.find("{*}sourcerpm")
            self._sourcerpm = ""
            if xml is not None:
                self._sourcerpm = xml.text
        return self._sourcerpm

    @property
    def basename(self):
        if self.sourcerpm:
            return split_rpm_filename(str(self.sourcerpm))[0]
        else:
            return self.name

    @property
    def epoch(self):
        return self.version[0]

    @property
    def ver(self):
        return self.version[1]

    @property
    def rel(self):
        return self.version[2]

    @property
    def license(self):
        if self._license is None:
            xml = self.format_xml.find("{*}license")
            self._license = ""
            if xml is not None:
                self._license = xml.text
        return self._license

    @property
    def vendor(self):
        if self._vendor is None:
            xml = self.format_xml.find("{*}vendor")
            self._vendor = ""
            if xml is not None:
                self._vendor = xml.text
        return self._vendor

    @property
    def group(self):
        if self._group is None:
            xml = self.format_xml.find("{*}group")
            self._group = ""
            if xml is not None:
                self._group = xml.text
        return self._group

    def _set_prco(self, kind):
        xml = self.format_xml.find("{*}%s" % kind)
        if xml is None:
            return []
        return [
            Capability(
                entry.attrib["name"],
                entry.attrib.get("flags", None),
                EVR(
                    entry.attrib.get("epoch", None),
                    entry.attrib.get("ver", None),
                    entry.attrib.get("rel", None),
                ),
            ) for entry in xml.iterfind("{*}entry")
        ]

    @property
    def requires(self):
        if self._requires is None:
            self._requires = self._set_prco("requires")
        return self._requires

    @property
    def provides(self):
        if self._provides is None:
            self._provides = self._set_prco("provides")
        return self._provides

    @property
    def obsoletes(self):
        if self._obsoletes is None:
            self._obsoletes = self._set_prco("obsoletes")
        return self._obsoletes

    @property
    def conflicts(self):
        if self._conflicts is None:
            self._conflicts = self._set_prco("conflicts")
        return self._conflicts

    @conflicts.setter
    def conflicts(self, xml):
        self._conflicts = self._prco_xml_to_list(xml)

    def _set_filelists(self):
        self._filelist = []
        self._ghosts = []
        self._dirs = []
        for xml in fast_iter(self.repo.filelists_md):
            self._parse_filelists(xml)

    def _parse_filelists(self, xml):
        if xml is None:
            return

        if xml.attrib["pkgid"] != self.checksum:
            return

        for item in xml.iterchildren():
            tag = etree.QName(item.tag).localname
            if tag == "file":
                self._filelist.append(item.text)
            elif tag == "dir":
                self._dirs.append(item.text)
            elif tag == "ghost":
                self._ghosts.append(item.text)

    @property
    def filelist(self):
        if self._filelist is None:
            self._set_filelists()
        return self._filelist

    @property
    def dirs(self):
        if self._dirs is None:
            self._set_filelists()
        return self._dirs

    @property
    def ghosts(self):
        if self._ghosts is None:
            self._set_filelists()
        return self._ghosts

    @property
    def changelog(self):
        basetup = (self.basename,) + self.version
        return self.repo.changelogs.get(basetup, [])

    @property
    def prco(self):
        return {
            "provides": self.provides,
            "requires": self.requires,
            "obsoletes": self.obsoletes,
            "conflicts": self.conflicts,
        }

    # RPM object emulation
    @property
    def base_package_name(self):
        return self.basename

    @property
    def pkgtup(self):
        return (self.name, self.arch, self.epoch, self.ver, self.rel)

    @property
    def files(self):
        return {
            "files": self.filelist,
            "dir": self.dirs,
            "ghost": self.ghosts
        }

    def verCMP(self, other):
        return evrcmp(self.version, other.version)

    def inPrcoRange(self, prcotype, reqtuple):
        return bool(self.matchingPrcos(prcotype, reqtuple))

    def matchingPrcos(self, prcotype, reqtuple):
        (reqn, reqf, (reqe, reqv, reqr)) = reqtuple
        # find the named entry in pkgobj, do the comparsion
        result = []
        for (n, f, (e, v, r)) in self.prco.get(prcotype, []):
            if not str_eq(reqn, n):
                continue

            if f == '=':
                f = 'EQ'
            if f != 'EQ' and prcotype == 'provides':
                # isn't this odd, it's not 'EQ' and it is a provides
                # - it really should be EQ
                # use the pkgobj's evr for the comparison
                if e is None:
                    e = self.epoch
                if v is None:
                    v = self.ver
                if r is None:
                    r = self.rel

            matched = rangeCompare(
                reqtuple, (n, f, (e, v, r)))
            if matched:
                result.append((n, f, (e, v, r)))

        return result


class Patterns(object):
    def __init__(self, patxml):
        self._items = {}
        for xml in fast_iter(patxml):
            self._xml_to_pat(xml)
        self._count = len(self._items.keys())

    def _xml_to_pat(self, patxml):
        ns = patxml.nsmap[None]
        nsrpm = patxml.nsmap["rpm"]
        name = patxml.find("{%s}%s" % (ns, "name")).text
        vertag = patxml.find("{%s}%s" % (ns, "version"))
        version = (None, None)
        if vertag is not None:
            version = (
                vertag.attrib.get("ver", None),
                vertag.attrib.get("rel", None)
            )
        summary = patxml.find("{%s}%s" % (ns, "summary")).text
        description = patxml.find("{%s}%s" % (ns, "description")).text
        reqtag = patxml.find("{%s}%s" % (nsrpm, "requires"))
        requires = []
        if reqtag is not None:
            requires = [
                entry.attrib["name"]
                for entry in reqtag.findall("{%s}%s" % (nsrpm, "entry"))
            ]
        provtag = patxml.find("{%s}%s" % (nsrpm, "provides"))
        provides = []
        if provtag is not None:
            provides = [
                entry.attrib["name"]
                for entry in provtag.findall("{%s}%s" % (nsrpm, "entry"))
            ]
        self._items[name] = {
            "version": version,
            "summary": summary,
            "description": description,
            "requires": requires,
            "provides": provides
        }

    @property
    def count(self):
        return self._count

    @count.setter
    def count(self, value):
        self._count = value

    @property
    def items(self):
        return self._items

    @items.setter
    def items(self, value):
        self._items = value


# Copied from rpmUtils.miscutils
# TODO This looks overly complicated, I'm sure we can do better...
def rangeCompare(reqtuple, provtuple):
    """returns true if provtuple satisfies reqtuple"""
    (reqn, reqf, (reqe, reqv, reqr)) = reqtuple
    (n, f, (e, v, r)) = provtuple
    if reqn != n:
        return 0

    # unversioned satisfies everything
    if not f or not reqf:
        return 1

    # and you thought we were done having fun
    # if the requested release is left out then we have
    # to remove release from the package prco to make sure the match
    # is a success - ie: if the request is EQ foo 1:3.0.0 and we have
    # foo 1:3.0.0-15 then we have to drop the 15 so we can match
    if reqr is None:
        r = None
    if reqe is None:
        e = None
    # just for the record if ver is None then we're going to segfault
    if reqv is None:
        v = None

    # if we just require foo-version, then foo-version-* will match
    if r is None:
        reqr = None

    rc = evrcmp(EVR(e, v, r), EVR(reqe, reqv, reqr))

    # does not match unless
    if rc >= 1:
        if reqf in ['GT', 'GE', 4, 12, '>', '>=']:
            return 1
        if reqf in ['EQ', 8, '=']:
            if f in ['LE', 10, 'LT', 2, '<=', '<']:
                return 1
        if reqf in ['LE', 'LT', 'EQ', 10, 2, 8, '<=', '<', '=']:
            if f in ['LE', 'LT', 10, 2, '<=', '<']:
                return 1

    if rc == 0:
        if reqf in ['GT', 4, '>']:
            if f in ['GT', 'GE', 4, 12, '>', '>=']:
                return 1
        if reqf in ['GE', 12, '>=']:
            if f in ['GT', 'GE', 'EQ', 'LE', 4, 12, 8, 10, '>', '>=', '=', '<=']:
                return 1
        if reqf in ['EQ', 8, '=']:
            if f in ['EQ', 'GE', 'LE', 8, 12, 10, '=', '>=', '<=']:
                return 1
        if reqf in ['LE', 10, '<=']:
            if f in ['EQ', 'LE', 'LT', 'GE', 8, 10, 2, 12, '=', '<=', '<', '>=']:
                return 1
        if reqf in ['LT', 2, '<']:
            if f in ['LE', 'LT', 10, 2, '<=', '<']:
                return 1
    if rc <= -1:
        if reqf in ['GT', 'GE', 'EQ', 4, 12, 8, '>', '>=', '=']:
            if f in ['GT', 'GE', 4, 12, '>', '>=']:
                return 1
        if reqf in ['LE', 'LT', 10, 2, '<=', '<']:
            return 1
#                if rc >= 1:
#                    if reqf in ['GT', 'GE', 4, 12, '>', '>=']:
#                        return 1
#                if rc == 0:
#                    if reqf in ['GE', 'LE', 'EQ', 8, 10, 12, '>=', '<=', '=']:
#                        return 1
#                if rc <= -1:
#                    if reqf in ['LT', 'LE', 2, 10, '<', '<=']:
#                        return 1

    return 0
