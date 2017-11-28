import datetime
import os
import urlparse
from collections import defaultdict
from copy import copy

import requests
import yum
from django.contrib.auth.backends import RemoteUserBackend
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import models
from rpmUtils.miscutils import splitFilename

import buildservice
import rpmmd
from .misc import (
    _find_containers, _fmt_chlog, _gen_abi,
    _get_latest_repo_pkg_meta, _get_pkg_meta, _leaf_components, _release_date
)
from south.modelsinspector import add_introspection_rules

try:
    from reports.jsonfield import JSONField
except ImportError:
    # during development it is in the cwd
    from jsonfield import JSONField

add_introspection_rules([], ["^reports\.jsonfield\.fields\.JSONField"])


class Arch(models.Model):

    def __str__(self):
        return self.name

    name = models.CharField(max_length=50, unique=True)


class DocService(models.Model):

    name = models.CharField(max_length=250, unique=True)
    weburl = models.CharField(max_length=250, null=True, blank=True)

    def __unicode__(self):
        return self.name


class LocalizationService(models.Model):

    name = models.CharField(max_length=250, unique=True)
    apiurl = models.CharField(max_length=250, null=True, blank=True)
    weburl = models.CharField(max_length=250, null=True, blank=True)

    def __unicode__(self):
        return self.name


class BuildService(models.Model):

    name = models.CharField(max_length=250, unique=True)
    namespace = models.CharField(max_length=50, unique=True)
    apiurl = models.CharField(max_length=250, unique=True)
    weburl = models.CharField(max_length=250, null=True, blank=True)

    def __unicode__(self):
        return self.name

    @property
    def api(self):
        return buildservice.BuildService(apiurl=self.apiurl)


class Project(models.Model):

    def __str__(self):
        return "%s on %s" % (self.name, self.buildservice)

    name = models.CharField(max_length=100, null=False, blank=False)
    buildservice = models.ForeignKey(BuildService, null=True)
    request_target = models.ForeignKey(
        "self", blank=True, null=True, related_name="request_source")


class Platform(models.Model):

    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name


class RepoServer(models.Model):

    def __str__(self):
        return self.url

    url = models.CharField(max_length=250, unique=True)
    buildservice = models.ForeignKey(BuildService, blank=True, null=True)


class Repo(models.Model):

    def __str__(self):
        _str = "%s %s" % (self.platform.name, self.release)
        prjs = list(self.projects.all())
        if self.is_live and len(prjs) == 1:
            _str = "%s %s" % (_str, prjs[0])
        return _str

    @models.permalink
    def get_absolute_url(self):
        return ('admin:view', [str(self.id)])

    @property
    def yumrepourl(self):
        return str(os.path.join(self.server.url, self.repo_path))

    @property
    def is_live(self):
        return "live" in self.release

    @property
    def version(self):
        pointer = list(self.pointer_set.all())
        if pointer:
            return pointer[0].name
        else:
            return None

    @property
    def pkg_meta(self):
        if self.is_live:
            # try to find a the latest not live repo for our platform
            not_live = Repo.objects.filter(
                platform=self.platform,
            ).exclude(release_date=None).order_by('-release')
            for container in not_live:
                pkg_meta = _get_latest_repo_pkg_meta(container)
                if pkg_meta:
                    return pkg_meta
        else:
            return _get_latest_repo_pkg_meta(self)

        return {}

    @property
    def timestamp(self):
        timestamp = datetime.datetime.now()
        return datetime.datetime.isoformat(timestamp)

    @property
    def yumrepoid(self):
        return str(self.pk)

    @property
    def packages(self):
        cachekey = "%s%s" % ("repopackages", self.id)
        pkgs = cache.get(cachekey)

        if pkgs is not None:
            return pkgs

        pkgs = {}
        ARCHS = [str(x) for x in Arch.objects.all()]
        PLATS = set(repo.platform.name for repo in self.comps)
        PLATS.add(self.platform.name)
        repo_pkg_meta = self.pkg_meta
        for pkg in self.yumsack.returnPackages():
            if pkg.arch not in ARCHS:
                continue

            # have we seen a binary from the same base package before ?
            if pkg.base_package_name in pkgs:
                # yes, check where it lives
                if pkg.repoid in pkgs[pkg.base_package_name]:
                    # same repo
                    base_pkg = pkgs[pkg.base_package_name][pkg.repoid]
                    if pkg.ver == base_pkg["version"]:
                        # same version, append to binaries list
                        base_pkg['binaries'].add(pkg)
                        base_pkg['binary_names'].add(pkg.name)
                        if (
                            not pkg.name.endswith("debuginfo") and
                            not pkg.name.endswith("debugsource")and
                            not pkg.name.endswith("-doc") and
                            not pkg.name.endswith("-tests") and
                            not pkg.name.endswith("-devel")
                        ):
                            base_pkg.update({
                                "description": pkg.description,
                                "summary": pkg.summary,
                            })
                    else:
                        # oh no different version!
                        base_pkg["messages"].append(
                            "Warning: %s exists in the same repo "
                            "with different version %s!" %
                            (pkg.name, pkg.ver)
                        )
                    # no need to look further
                    continue
            else:
                pkgs[pkg.base_package_name] = {}

            pkg_meta = _get_pkg_meta(
                pkg.base_package_name, PLATS, repo_pkg_meta
            )
            pkgs[pkg.base_package_name][pkg.repoid] = {
                "version": pkg.ver,
                "release": pkg.rel,
                "changelog": _fmt_chlog(pkg.changelog),
                "license": pkg.license,
                "binaries": set([pkg]),
                "binary_names": set([pkg.name]),
                "meta": pkg_meta,
                "messages": [],
            }
            if (
                not pkg.name.endswith("debuginfo") and
                not pkg.name.endswith("debugsource")and
                not pkg.name.endswith("-doc") and
                not pkg.name.endswith("-tests") and
                not pkg.name.endswith("-devel")
            ):
                pkgs[pkg.base_package_name][pkg.repoid].update({
                    "description": pkg.description,
                    "summary": pkg.summary,
                })

        cachelife = (60 * 5) if self.is_live else (60 * 60 * 24)
        cache.set(cachekey, pkgs, cachelife)

        return pkgs

    @property
    def patterns(self):
        _patterns = {}
        if self.comps:
            for comp in self.comps:
                _patterns.update(comp.patterns)
        else:
            for repo in self.yumrepos:
                _patterns[str(self)] = repo.patterns

        return _patterns

    @property
    def comps(self):
        if hasattr(self, "_comps"):
            return self._comps

        self._comps = _leaf_components(self)
        return self._comps

    @property
    def yumrepos(self):
        if hasattr(self, "_yumrepos"):
            return self._yumrepos

        comp = None
        self._yumrepos = []
        for comp in self.comps:
            self._yumrepos.extend(comp.yumrepos)

        if comp is None:
            archs = [arch.name for arch in self.archs.all()]
            # backward compat, as well as passthrough for urls without @ARCH@
            if not archs:
                archs = ["armv7hl"]

            # replace @ARCH@ to desired arch
            for arch in archs:
                yumrepoid = self.yumrepoid
                yumrepourl = self.yumrepourl.replace("@ARCH@", arch)
                print yumrepourl
                cachedir = os.path.join(
                    yum.misc.getCacheDir(tmpdir=os.path.expanduser("~")),
                    self.yumrepoid, str(arch),
                )
                try:
                    yumrepo = rpmmd.Repo(
                        yumrepoid, yumrepourl, cachedir=cachedir
                    )
                    self._yumrepos.append(yumrepo)
                except requests.exceptions.RequestException, exc:
                    print exc

        return self._yumrepos

    @property
    def yumsack(self):
        if hasattr(self, '_yumsack'):
            return self._yumsack

        self._yumsack = rpmmd.RepoSack(self.yumrepos)
        return self._yumsack

    @property
    def comparable(self):
        if hasattr(self, '_comparable'):
            return self._comparable

        _comparable = Repo.objects.filter(platform=self.platform)\
            .exclude(id=self.id)\
            .order_by('-release')\
            .select_related('platform', 'server')\
            .prefetch_related('projects')
        self._comparable = list(_comparable)
        return self._comparable

    @property
    def prjsack(self):
        if hasattr(self, '_prjsack'):
            return self._prjsack
        self._prjsack = list(self.projects.all())
        for comp in self.comps:
            self._prjsack.extend(comp.prjsack)
        return self._prjsack

    def save(self, *args, **kwargs):
        if not self.release_date and self.release and not self.is_live:
            self.release_date = _release_date(self.release)

        super(Repo, self).save(*args, **kwargs)

    class Meta:
        unique_together = ("server", "repo_path")

    server = models.ForeignKey(RepoServer)
    repo_path = models.CharField(max_length=250)
    platform = models.ForeignKey(Platform)
    projects = models.ManyToManyField(Project, blank=True, null=True)
    components = models.ManyToManyField(
        "self", symmetrical=False, blank=True, null=True,
        related_name="containers"
    )
    release = models.CharField(max_length=250)
    release_date = models.DateField(blank=True, null=True)
    archs = models.ManyToManyField(Arch, blank=True, null=True)


class Note(models.Model):

    def __str__(self):
        return "Note for %s %s" % (self.repo.platform.name, self.repo.release)

    body = models.TextField()
    repo = models.ForeignKey(Repo, unique=True)


class IssueTracker(models.Model):

    def __str__(self):
        return "%s %s %s" % (self.name, self.re, self.url)

    name = models.CharField(max_length=100, unique=True)
    re = models.CharField(max_length=100)
    url = models.CharField(max_length=200)
    platform = models.ManyToManyField(Platform, blank=True, null=True)


class Image(models.Model):

    @models.permalink
    def get_absolute_url(self):
        return ('admin:view', [str(self.id)])

    def __str__(self):
        return "%s %s" % (self.name, self.release)

    name = models.CharField(max_length=100)
    url = models.CharField(max_length=250)
    url_file = models.CharField(max_length=250)
    urls = models.TextField(blank=True, null=True)
    repo = models.ManyToManyField(Repo, blank=True, null=True)
    container_repo = models.ForeignKey(
        Repo, blank=True, null=True, related_name="images")

    @property
    def archs(self):
        return self.container_repo.archs.all()

    @property
    def yumrepoid(self):
        return self.container_repo.yumrepoid

    @property
    def components(self):
        if self.container_repo:
            return self.container_repo.components
        else:
            return None

    @property
    def platform(self):
        if self.container_repo:
            return self.container_repo.platform
        else:
            return None

    @property
    def release(self):
        if self.container_repo:
            return self.container_repo.release
        else:
            return None

    @property
    def version(self):
        if self.container_repo:
            return self.container_repo.version
        else:
            return None

    @property
    def release_date(self):
        if self.container_repo:
            return self.container_repo.release_date
        else:
            return None

    @property
    def projects(self):
        if self.container_repo:
            return self.container_repo.projects
        else:
            return None

    @property
    def bpkgs(self):
        _bpkgs = []
        for line in self.urls.splitlines():
            rpm_name = os.path.basename(line.strip())
            name, version, release, epoch, arch = splitFilename(rpm_name)
            _bpkgs.append(name)
        return _bpkgs

    @property
    def packages(self):
        image_bpkgs = self.bpkgs
        image_packages = defaultdict(dict)
        for repo in self.repo.all():
            for pkgname, repoid_pkg in repo.packages.items():
                for repoid, pkg in repoid_pkg.items():
                    binaries = copy(pkg['binaries'])
                    for binary in pkg['binaries']:
                        if binary not in image_bpkgs:
                            binaries.remove(binary)
                    if binaries:
                        pkg['binaries'] = binaries
                        image_packages[pkgname][repoid] = pkg
        return dict(image_packages)

    @property
    def repos(self):
        linked_repos = list(self.repo.all())
        if not linked_repos:
            self.link_to_repos()
            linked_repos = list(self.repo.all())

        return linked_repos

    @property
    def comparable(self):
        imgs = set()
        for crepo in self.container_repo.comparable:
            imgs.update(crepo.images.all())
        return imgs

    def save(self, *args, **kwargs):
        # performs regular validation then clean()
        self.full_clean()
        super(Image, self).save(*args, **kwargs)
        # won't work through admin view since m2m field is cleared after save
        self.link_to_repos()

    def clean(self):
        if self.id:
            # FIXME: what is this supposed to do?
            len(self.repos)
        return

    def set_container_repo(self):

        containers = defaultdict(int)
        _find_containers(
            list(self.repo.all().prefetch_related("containers")),
            containers
        )
        _cont = None
        if containers:
            _cont = max(
                containers.iterkeys(),
                key=(lambda key: containers[key])
            )

        if _cont:
            __container_repo = Repo.objects.get(id=_cont)
        else:
            # currently support only images that have a single container repo
            __container_repo = None

        self.container_repo = __container_repo
        self.save()

    def link_to_repos(self):
        _repos = set()
        found_repos = set()
        archs = set([arch.name for arch in Arch.objects.all()])
        for url in self.urls.splitlines():
            _repos.add(os.path.dirname(url))

        for urlline in _repos:
            print urlline
            for arch in archs:
                urlline = urlline.replace(arch, '@ARCH@')
            parts = urlparse.urlsplit(urlline)
            srv = parts.scheme + "://" + parts.netloc + "/"
            path = os.path.dirname(parts.path.replace("/", "", 1))
            found = False
            while not found and path:
                try:
                    repo = Repo.objects.get(
                        server__url=srv, repo_path=path, components=None)
                    found_repos.add(repo)
                    found = True
                except Repo.DoesNotExist:
                    path = os.path.dirname(path)

            if not found:
                # reset and retry with a possible pointer
                try:
                    path = os.path.dirname(parts.path.replace("/", "", 1))
                    split_path = path.split("/")
                    pointer = Pointer.objects.get(name=split_path[1])

                    for repo in pointer.target.components.all():
                        repo_split_path = repo.repo_path.split("/")
                        split_path = path.split("/")

                        while not found and split_path:
                            print pointer.name
                            print repo_split_path
                            print split_path
                            if split_path == repo_split_path:
                                found_repos.add(repo)
                                found = True
                            else:
                                split_path = split_path[0:-1]

                        split_path = path.split("/")
                        split_path[1] = pointer.target.release

                        while not found and split_path:
                            if split_path == repo_split_path:
                                found_repos.add(repo)
                                found = True
                            else:
                                split_path = split_path[0:-1]

                except Pointer.DoesNotExist:
                    pass

            if not found:
                raise ValidationError(
                    "Cannot find Repo matching url %s" % urlline
                )

        for _repo in found_repos:
            self.repo.add(_repo)


class Pointer(models.Model):
    def __unicode__(self):
        return "%s -> %s" % (self.name, str(self.target))

    name = models.CharField(max_length=200)
    public = models.BooleanField(default=False)
    factory = models.BooleanField(default=False)
    target = models.ForeignKey(Repo, unique=True)


class ABI(models.Model):

    def __unicode__(self):
        return "ABI for %s" % self.version.name

    version = models.ForeignKey(Pointer)
    private = models.TextField(blank=True)
    public = models.TextField()
    files = models.TextField(blank=True)
    dump = models.CharField(max_length=1000, blank=True)

    @property
    def listing(self):
        return _gen_abi(self)


class Graph(models.Model):

    def __unicode__(self):
        return "Graph %s" % self.id

    @property
    def has_pkg_meta(self):
        return self.pkg_meta and len(self.pkg_meta.keys())

    direction = models.IntegerField(
        choices=[
            (0, "normal"),
            (1, "reverse"),
            (2, "both")
        ]
    )
    depth = models.PositiveIntegerField(blank=True, null=True, default=3)
    image = models.ForeignKey(Image, blank=True, null=True)
    packages = models.TextField(blank=True, null=True)
    repo = models.ManyToManyField(Repo, blank=True, null=True)
    dot = models.FileField(upload_to="graph")
    svg = models.FileField(upload_to="graph", null=True)
    pkg_meta = JSONField(blank=True, null=True)


class PackageMetaType(models.Model):

    def __str__(self):
        return self.name

    name = models.CharField(
        max_length=100, null=False, blank=False, unique=True
    )
    description = models.TextField()
    allow_multiple = models.BooleanField()
    default = models.ForeignKey("PackageMetaChoice", blank=True, null=True)


class PackageMetaChoice(models.Model):

    def __str__(self):
        return self.name

    name = models.CharField(
        max_length=100, null=False, blank=False, unique=True)
    description = models.TextField()
    metatype = models.ForeignKey(
        PackageMetaType, blank=False, null=False, related_name="choices")


class RemoteStaffBackend(RemoteUserBackend):

    def configure_user(self, user):

        user.is_staff = True
        return user
