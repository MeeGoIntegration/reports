import math
from collections import defaultdict, namedtuple

from django.db.models import ObjectDoesNotExist

from .models import Arch
from .rpmutils import evrcmp
from .misc import _find_comparable_component, _fmt_chlog, _get_pkg_meta

PkgKey = namedtuple(
    'PkgKey', ['repo_id', 'repo_name', 'comp_id', 'comp_name', 'pkg_name']
)


class RepoCompare:
    def __init__(self, new_repo, old_repo, group_by_component=True):
        self.new_repo = new_repo
        self.old_repo = old_repo
        self.group_by_component = group_by_component
        self.repo_pkg_meta = new_repo.pkg_meta
        self.platforms = set([new_repo.platform.name])
        self.new_repos = {}
        if new_repo.comps:
            for repo in new_repo.comps:
                self.new_repos[repo.id] = repo
                self.platforms.add(repo.platform.name)
        else:
            self.new_repos[new_repo.id] = new_repo
        self.new_packages = defaultdict(set)

        self.old_repos = {}
        if old_repo.comps:
            for repo in old_repo.comps:
                self.old_repos[repo.id] = repo
                self.platforms.add(repo.platform.name)
        else:
            self.old_repos[old_repo.id] = old_repo
        self.old_packages = defaultdict(set)

        self.repo_count = len(self.new_repos) + len(self.old_repos)

        self.ARCHS = set([str(x) for x in Arch.objects.all()])
        self.ARCHS.add("src")
        self.DEBUG_SUFFIXES = set(["debuginfo", "debugsource"])

        self.package_data = dict()
        self.obsoletes = dict()
        self.obsoleted = defaultdict(dict)
        self.repo_map = dict()

    def can_be_skipped(self, pkg):
        if pkg.arch not in self.ARCHS:
            return True
        suffix = pkg.name.split("-")[-1]
        if suffix in self.DEBUG_SUFFIXES:
            return True
        return False

    def _map_repo(self, repo):
        prjsack = list(repo.prjsack)
        project = None
        if repo.is_live and len(prjsack) == 1:
            project = prjsack[0].request_target
            if project:
                if project in self.old_repo.prjsack:
                    project = str(project.name)
                else:
                    try:
                        project = prjsack[0].request_source.get()
                        project = str(project.name)
                    except ObjectDoesNotExist:
                        pass

        old_comparable = _find_comparable_component(
            repo, self.old_repo, project=project)

        if old_comparable:
            self.repo_map[repo.id] = old_comparable.id

    def _colect_pkg_data(self, repo_id, pkg):
        repo_pkg_key = (repo_id, pkg.base_package_name)
        if repo_pkg_key not in self.package_data:
            self.package_data[repo_pkg_key] = {
                "binaries": set([pkg.name]),
                "changelog": pkg.changelog,
                "evr": pkg.version,
                "meta": _get_pkg_meta(
                    pkg.base_package_name, self.platforms,
                    self.repo_pkg_meta,
                ),
            }
        else:
            self.package_data[repo_pkg_key]["binaries"].add(pkg.name)

    def fetch(self):
        obs_map = defaultdict(dict)
        for repo_id, repo in self.new_repos.items():
            repo_str = str(repo)
            for pkg in repo.yumsack.returnNewestByName():
                if self.can_be_skipped(pkg):
                    continue
                self._colect_pkg_data(repo_id, pkg)
                self.new_packages[pkg.base_package_name].add(
                    (repo_id, repo_str))
                for cap in pkg.obsoletes:
                    obs_map[cap.name][(pkg.base_package_name, pkg.name)] = cap

            self._map_repo(repo)
            yield repo_id

        for repo_id, repo in self.old_repos.items():
            repo_str = str(repo)
            for pkg in repo.yumsack.returnNewestByName():
                if self.can_be_skipped(pkg):
                    continue
                self._colect_pkg_data(repo_id, pkg)
                self.old_packages[pkg.base_package_name].add(
                    (repo_id, repo_str))
                for obs_by, obs_cap in obs_map[pkg.name].viewitems():
                    if pkg.inPrcoRange('provides', obs_cap):
                        self.obsoleted[pkg.name] = obs_by

            yield repo_id

    def _get_pkg_key(self, comp_id, comp_str, pkg_name):
        if self.group_by_component:
            return PkgKey(comp_id, comp_str, None, None, pkg_name)
        else:
            return PkgKey(
                self.new_repo.id, str(self.new_repo),
                comp_id, comp_str, pkg_name
            )

    def get_diff(self, group_by_component=True):
        new_pkg_names = set(self.new_packages.keys())
        old_pkg_names = set(self.old_packages.keys())

        added = dict()
        for pkg_name in new_pkg_names - old_pkg_names:
            for repo_id, repo_str in self.new_packages[pkg_name]:
                pkg_data = self.package_data[(repo_id, pkg_name)]
                pkg_key = self._get_pkg_key(repo_id, repo_str, pkg_name)
                added[pkg_key] = dict(
                    binaries=sorted(pkg_data['binaries']),
                    chlog=_fmt_chlog(pkg_data['changelog']),
                    meta=pkg_data['meta'],
                )

        modified = dict()
        for pkg_name in old_pkg_names & new_pkg_names:
            for repo_id, repo_str in self.new_packages[pkg_name]:
                new_pkg = self.package_data[(repo_id, pkg_name)]
                old_pkg = None
                old_repo_id = self.repo_map.get(repo_id)
                if old_repo_id:
                    old_pkg = self.package_data.get((old_repo_id, pkg_name))
                else:
                    print "no old repo found for %s" % pkg_name
                if old_pkg is None:
                    print "no exact comparable pacakge found for %s" % pkg_name
                    # maybe it was moved, lets just pick the first one
                    old_repo_id, _ = list(self.old_packages[pkg_name])[0]
                    old_pkg = self.package_data[(old_repo_id, pkg_name)]

                if new_pkg['evr'].ver == old_pkg['evr'].ver:
                    # If the version is the same we assume there is no changes,
                    # epoch shouldn't be used, and release can differ per build
                    # counts
                    continue

                ver_diff = evrcmp(new_pkg['evr'], old_pkg['evr'])
                chlog = _fmt_chlog(
                    _limit_chlog(new_pkg['changelog'], old_pkg['evr'])
                )
                if not len(chlog):
                    chlog.append("No new changelog entries!")

                pkg_key = self._get_pkg_key(repo_id, repo_str, pkg_name)
                modified[pkg_key] = {
                    "sense": "Updated" if ver_diff == 1 else "Reverted",
                    "ovr": str(old_pkg['evr']),
                    "nvr": str(new_pkg['evr']),
                    "ba": sorted(new_pkg['binaries'] - old_pkg['binaries']),
                    "br": sorted(old_pkg['binaries'] - new_pkg['binaries']),
                    "chlog": chlog,
                    "meta": new_pkg['meta'],
                }

        removed = dict()
        obsoleted = dict()
        for pkg_name in old_pkg_names - new_pkg_names:
            for repo_id, repo_str in self.old_packages[pkg_name]:
                pkg_data = self.package_data[(repo_id, pkg_name)]
                pkg_key = self._get_pkg_key(repo_id, repo_str, pkg_name)
                removed_binaries = set()
                for bin_name in pkg_data['binaries']:
                    if bin_name in self.obsoleted:
                        obs_base, obs_bin = self.obsoleted[bin_name]
                    else:
                        removed_binaries.add(bin_name)
                removed[pkg_key] = sorted(removed_binaries)

        return {
            "added": added,
            "removed": removed,
            "modified": modified,
            "obsoleted": obsoleted,
        }


def _limit_chlog(changelog, after_evr):
    print changelog
    print after_evr
    return [
        entry for entry in changelog
        if evrcmp(entry.version, after_evr, ignore_release=True) > 0
    ]


def _new_diff_sacks(newrepo, oldrepo, progress_cb):

    repo_diff = RepoCompare(
        newrepo, oldrepo,
        group_by_component=newrepo.is_live and oldrepo.is_live,
    )

    # steps include fetching repo metadata + doing the diff
    step_count = repo_diff.repo_count + 1
    done_count = 0

    for _ in repo_diff.fetch():
        done_count += 1
        progress_cb(math.ceil((float(done_count)/step_count)*100))

    diff = repo_diff.get_diff()
    progress_cb(100)
    return diff
