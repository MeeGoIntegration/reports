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
from rpmUtils.miscutils import (
    compareEVR, rangeCompare, splitFilename, stringToVersion
)
from yum import i18n


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
        for repo in self.repos:
            for name in query:
                po = repo.packages.get(name, None)
                if po:
                    yield (name, po)

    def search_basename(self, query):
        for repo in self.repos:
            for name in query:
                po = repo.base_packages.get(name, None)
                if po:
                    yield (name, po)

    def search_name_contains(self, query, casei):
        if casei:
            for i, val in enumerate(query):
                query[i] = val.lower()

        for name, po in self.packages:
            if casei:
                name = name.lower()
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
        for repo in self.repos:
            po = repo.packages.get(name, None)
            if po:
                yield po

    # Yum API emulation
    def returnPackages(self):
        return itertools.chain.from_iterable(
            [repo.packages.viewvalues() for repo in self.repos]
        )

    def returnNewestByName(self, name=None):
        newest = {}
        for key, pkg in self.packages:
            if name is not None and name != key:
                continue

            cval = 1
            if key in newest:
                cval = pkg.verCMP(newest[key][0])
            if cval > 0:
                newest[key] = [pkg]
            elif cval == 0:
                newest[key].append(pkg)
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
        elif type(version) in (str, type(None), unicode):
            version = stringToVersion(version)
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
    def __init__(self, repoid, baseurl, cachedir=None):
        self.repoid = repoid
        self.baseurl = baseurl
        if not baseurl.endswith("/"):
            self.baseurl = baseurl + "/"

        if cachedir is None:
            cachedir = tempfile.mkdtemp()

        if not os.path.isdir(cachedir):
            os.makedirs(cachedir)

        self._cachedir = cachedir
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
                verify=False
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
                verify=False
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
        name = xml.attrib['name']
        po = self.packages.get(name, None)
        if po:
            basename = po.basename
            if basename not in self._changelogs:
                self._changelogs[basename] = [
                    Changelog(
                        entry.attrib['date'], entry.attrib['author'],
                        entry.text
                    ) for entry in xml.iterfind("{*}changelog")
                ]

    @property
    def provides(self):
        if self._providx is None:
            self._providx = {}
            for name, po in self.packages.viewitems():
                for prov in po.provides:
                    self._providx[prov.name] = po
        return self._providx

    @property
    def requires(self):
        if self._reqidx is None:
            self._reqidx = {}
            for name, po in self.packages.viewitems():
                for req in po.requires:
                    self._reqidx[req.name] = po
        return self._reqidx


Changelog = namedtuple("Changelog", ["time", "author", "text"])
EVR = namedtuple("EVR", ["epoch", "ver", "rel"])


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

        s = ""

        if e not in [0, '0', None]:
            s += '%s:' % e
        if v is not None:
            s += '%s' % v
        if r is not None:
            s += '-%s' % r

        return '%s %s %s' % (self.name, flags[self.flag], s)


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
            self.repo._packages[self.name] = self

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
            return splitFilename(str(self.sourcerpm))[0]
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
        return self.repo.changelogs.get(self.basename, [])

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
        return compareEVR(self.version, other.version)

    def inPrcoRange(self, prcotype, reqtuple):
        return bool(self.matchingPrcos(prcotype, reqtuple))

    def matchingPrcos(self, prcotype, reqtuple):
        (reqn, reqf, (reqe, reqv, reqr)) = reqtuple
        # find the named entry in pkgobj, do the comparsion
        result = []
        for (n, f, (e, v, r)) in self.prco.get(prcotype, []):
            if not i18n.str_eq(reqn, n):
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
