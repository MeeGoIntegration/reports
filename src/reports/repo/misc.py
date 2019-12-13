import datetime
from collections import defaultdict, OrderedDict

import rpmUtils.miscutils
import yum


def _get_pkg_meta(pkg, platforms, repo_pkg_meta):
    pkg_meta = {}
    if repo_pkg_meta:
        for plat in platforms:
            try:
                pkg_meta = repo_pkg_meta[plat][pkg]
            except KeyError:
                pass

            if pkg_meta:
                break
    return pkg_meta


def _get_latest_repo_pkg_meta(repo):
    # try to find an associated graph that has pkg_meta
    for graph in repo.graphs.all().order_by("-id"):
        if graph.has_pkg_meta:
            return graph.pkg_meta
    # try to find a container that has a pkg_meta with our platform
    for container in repo.containers.all():
        if repo.platform.name in container.pkg_meta:
            return container.pkg_meta
    return {}


def _find_repo_by_id(repo, repoid):
    if str(repo.pk) == str(repoid):
        return repo

    else:
        for comp in repo.comps:
            found = _find_repo_by_id(comp, repoid)
            if found:
                return found
        return False


def _fmt_chlog(chlog):

    def _get_chlog_ver(item):
        x = "0"
        if "> -" in item[1]:
            x = item[1].rsplit("> -", 1)[-1].strip()
        elif "> " in item[1]:
            x = item[1].rsplit("> ", 1)[-1].strip()
        if "-" in x:
            x = x.rsplit("-", 1)[0]
        return x

    chlog.sort(
        cmp=rpmUtils.miscutils.compareVerOnly,
        key=_get_chlog_ver,
        reverse=True,
    )
    flat = []
    for item in chlog:
        tm = datetime.date.fromtimestamp(int(item[0]))
        flat.append("* %s %s" % (
            tm.strftime("%a %b %d %Y"), yum.misc.to_unicode(item[1]))
        )
        flat.extend([yum.misc.to_unicode(line)
                     for line in item[2].splitlines()])
        flat.append("")
    return flat


# recursive function that given a list of repos,
# will find their common container repos set containers is passed by reference
def _find_containers(repos, containers):
    for repo in repos:
        x = list(repo.containers.only("id"))
        if len(x):
            _find_containers(x, containers)
        else:
            containers[repo.id] += 1


def _release_date(release):
    date = None
    date_split = release.split(".")
    if len(date_split) > 1:
        date_string = date_split[1]
        if len(date_string) == 8:
            date = datetime.datetime.date(
                datetime.datetime.strptime(date_string, "%Y%m%d")
            )
    return date


def _find_comparable_component(component, repo, project=None):
    prjsack = repo.prjsack
    if component in repo.comparable:
        if project is None:
            return repo
        elif prjsack and str(prjsack[0].name) == str(project):
            return repo

    for comp in repo.comps:
        result = _find_comparable_component(component, comp, project=project)
        if result:
            return result

    return False


def _exclude_by_meta(pkg, meta):
    exclude = True
    if not hasattr(pkg, 'get'):
        return exclude

    for metatype, choices in pkg.get('meta', {}).items():
        if metatype in meta:
            for choice in meta[metatype]:
                if isinstance(choices, dict):
                    if choices[choice]:
                        exclude = False
                else:
                    if choices == choice:
                        exclude = False
    return exclude


def _regroup_repo_packages(repo, pkgs=None, repos=None, meta=None):
    # regroup packages by leaf repo
    packages = defaultdict(OrderedDict)

    for pkgname, repoids_pkg in repo.packages.iteritems():
        if pkgs and pkgname not in pkgs:
            continue
        for repoid, pkg in repoids_pkg.iteritems():
            packages[repoid][pkgname] = pkg

    for repoid in packages.keys():
        subrepo = _find_repo_by_id(repo, repoid)
        subrepo_str = str(subrepo)
        if repos and subrepo.id not in repos:
            continue

        for pkgname in sorted(packages[repoid].keys()):
            if meta:
                if _exclude_by_meta(packages[repoid][pkgname], meta):
                    continue

            packages[subrepo_str][pkgname] = packages[repoid][pkgname]

        packages.pop(repoid)

    return dict(packages)


def _find_unmet_reqs(pkg, newsack, oldsack=None):
    pkgreqs = pkg.requires
    unmet_reqs = set()
    newprovs = {req: prov for req, prov in
                newsack.search_provides(pkgreqs)}
    if oldsack is not None:
        oldprovs = {req: prov for req, prov in
                    oldsack.search_provides(pkgreqs)}

    for req in pkgreqs:
        if oldsack is None:
            if req not in newprovs:
                unmet_reqs.add(str(req))
        else:
            if req in newprovs and req not in oldprovs:
                unmet_reqs.add(str(req))
    return unmet_reqs


def _regroup(pos, container):
    PLATS = set(repo.platform.name for repo in container.comps)
    PLATS.add(container.platform.name)
    repo_pkg_meta = container.pkg_meta
    pkgs = {}
    capidx = {"requires": {}, "provides": {}, "obsoletes": {}, "conflicts": {}}
    for po in pos:
        repo = str(_find_repo_by_id(container, po.repoid))
        if repo not in pkgs:
            pkgs[repo] = {}

        if po.basename not in pkgs[repo]:
            pkg_meta = _get_pkg_meta(po.basename, PLATS, repo_pkg_meta)
            pkgs[repo][po.basename] = {
                "version": po.ver,
                "release": po.rel,
                "changelog": _fmt_chlog(po.changelog),
                "license": po.license,
                "binaries": [],
                "meta": pkg_meta,
                "messages": [],
            }
        pkgs[repo][po.basename]["binaries"].append(po)
        for kind, prco in po.prco.viewitems():
            capidx[kind].update(dict.fromkeys(prco, None))

    for kind, prco in capidx.viewitems():
        search = None
        if kind == "requires":
            search = container.yumsack.search_provides(prco)
        elif kind == "provides":
            search = container.yumsack.search_requires(prco)
        if search:
            for cap, what in search:
                if not capidx[kind][cap]:
                    capidx[kind][cap] = set([what.name])
                else:
                    capidx[kind][cap].add(what.name)
    return pkgs, capidx


def _search(querytype, query, container, exact=True, casei=False):
    pos = []
    if querytype == "packagename":
        if exact and not casei:
            pos = [
                res[1] for res in
                container.yumsack.search_name([query])
            ]
            if not pos:
                pos = [
                    res[1] for res in
                    container.yumsack.search_basename([query])
                ]
        else:
            pos = [
                res[1] for res in
                container.yumsack.search_name_contains([query], casei)
            ]
            if not pos:
                pos = [
                    res[1] for res in
                    container.yumsack.search_basename_contains([query], casei)
                ]
    elif querytype == "provides":
        pos = [
            res[1] for res in
            container.yumsack.search_provides(
                [(query, None, (None, None, None))]
            )
        ]
    elif querytype == "file":
        pos = [
            res[1] for res in
            container.yumsack.search_filenames([query])
        ]

    return _regroup(pos, container)


def _gen_abi(abi_obj):

    yumsack = abi_obj.version.target.yumsack
    abi = {"public": set(), "private": set(), "files": set()}
    if abi_obj.public.strip():
        names = [name.strip() for name in abi_obj.public.splitlines()]
        pos = yumsack.search_name(names)
        for name, po in pos:
            abi["public"].update(po.provides)
    if abi_obj.private.strip():
        names = [name.strip() for name in abi_obj.private.splitlines()]
        pos = yumsack.search_name(names)
        for name, po in pos:
            abi["private"].update(po.provides)
    if abi_obj.files.strip():
        abi["files"] = [name.strip() for name in abi_obj.files.splitlines()]

    return {
        "public": list(abi["public"]),
        "private": list(abi["private"]),
        "files": abi["files"],
        "version": abi_obj.version.name,
    }


def _leaf_components(repo):
    comps = set()
    for comp in repo.components.all().select_related("server"):
        if comp.comps:
            comps.update(_leaf_components(comp))
        else:
            comps.add(comp)
    return comps
