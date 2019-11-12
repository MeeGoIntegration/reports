import math
import os
from collections import defaultdict, OrderedDict
from copy import copy
from tempfile import mkstemp
from urllib2 import HTTPError

import pydot
import yum
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.core.files import File
from django.core.files.base import ContentFile
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils.safestring import mark_safe
from osc import core

import buildservice

from .misc import (
    _exclude_by_meta, _find_comparable_component, _find_unmet_reqs, _fmt_chlog,
    _get_pkg_meta
)
from .models import Arch, Graph, Image, PackageMetaType, Repo

try:
    from lxml import etree
except ImportError:
    try:
        import xml.etree.cElementTree as etree
    except ImportError:
        import xml.etree.ElementTree as etree


__all__ = [
    "_diff_sacks", "_get_trace", "_get_svg", "_graph_projects", "_creq",
    "_get_dot", "_get_latest_image", "_find_previous_pkg_meta",
    "_update_pkg_meta", "_sort_filter_diff", "_get_filter_meta"
]


def _get_latest_image(platform_name='Jolla'):
    images = sorted(
        Image.objects.select_related("container_repo")
        .prefetch_related("container_repo__platform").all(),
        key=lambda image: image.release,
        reverse=True,
    )

    for img in images:
        if img.platform.name == platform_name:
            return img
    return None


def _find_previous_pkg_meta(graph):
    repo = graph.repo.get()
    if not repo:
        return None
    plat = repo.platform.name
    # repos from the same platform
    repos = Repo.objects.filter(platform__name=plat)\
        .exclude(release_date=None).order_by('-release')
    for r in repos:
        if r.graph_set.count() > 0:
            r_graph = r.graph_set.all()[0]
        else:
            continue
        # return first that has pkg_meta set
        if r_graph.pkg_meta:
            return r_graph.pkg_meta
        else:
            continue

    return None


def _update_pkg_meta(graph, container, img=None):
    old_pkgs = {}
    new_pkgs = {}

    for p in graph.pkg_meta.keys():
        if p == 'img':
            continue  # skip img info
        old_pkgs[p] = graph.pkg_meta[p].keys()

    if container.components.count() == 0:
        new_pkgs[str(container.platform)] = container.packages
    else:
        for p in container.components.all():
            if p.is_live and p.projects.count() == 1:
                new_pkgs[
                    str(p.platform) + " " + str(p.projects.all()[0])
                ] = p.packages
            else:
                new_pkgs[str(p.platform)] = p.packages

    for repo in old_pkgs.keys():
        if (
            repo in new_pkgs and
            set(new_pkgs[repo].keys()) ^ set(old_pkgs[repo])
        ):
            added_pkgs = set(new_pkgs[repo].keys()) - set(old_pkgs[repo])
            removed_pkgs = set(old_pkgs[repo]) - set(new_pkgs[repo].keys())

            # add missing packages:
            for pkg in added_pkgs:
                graph.pkg_meta[repo][pkg] = {}

                for mtype in PackageMetaType.objects.all():
                    mchoices = mtype.choices.all()

                    # for multiple choices make a dictionary
                    if mtype.allow_multiple:
                        graph.pkg_meta[repo][pkg][mtype.name] = {}
                        for choice in mchoices:
                            graph.pkg_meta[repo][pkg][mtype.name].update(
                                {choice.name: False}
                            )
                    elif mtype.default:
                        graph.pkg_meta[repo][pkg][mtype.name] = \
                                mtype.default.name
                    # initalize as empty string by default
                    else:
                        graph.pkg_meta[repo][pkg][mtype.name] = ""

            # Remove packages that are now longer part of the repo
            for pkg in removed_pkgs:
                del graph.pkg_meta[repo][pkg]
    graph.save()


def _get_submit_reqs(new_prjs, old_prjs):

    reqs = {
        "incoming": [],
        "in progress": [],
        "outgoing": [],
    }
    for apiurl, prjs in new_prjs:
        bs = buildservice.BuildService(apiurl=str(apiurl))
        actions = ["(action/target/@project='%s'" % prj for prj in prjs]
        reqs["incoming"] = core.search(
            bs.apiurl,
            request="(state/@name='new' or state/@name='review') and %s)" %
            "or".join(actions)
        )

    for apiurl, prjs in old_prjs:
        bs = buildservice.BuildService(apiurl=str(apiurl))
        actions = ["(action/source/@project='%s'" % prj for prj in prjs]
        reqs["outgoing"] = core.search(
            bs.apiurl,
            request="(state/@name='new' or state/@name='review') and %s)" %
            "or".join(actions)
        )

    return reqs


def _find_projects(repo):
    prjs_by_apiurl = defaultdict(set)
    if repo.is_live:
        for prj in repo.prjsack:
            prjs_by_apiurl[prj.apiurl].add(prj)
    return prjs_by_apiurl


def _get_trace(old_repo, new_repo):

    new_prjs = _find_projects(new_repo)
    old_prjs = _find_projects(old_repo)
    reqs = _get_submit_reqs(new_prjs, old_prjs)

    return dict(reqs)


# lifted from repo-graph from yum-utils
def _get_dot(repos, img, pacs, depth, direction):

    sack = yum.packageSack.ListPackageSack()
    for repo in repos:
        sack.addList(repo.yumsack.returnPackages())

    dot = [
        'digraph packages {',
        """
    size="45,50";
    center="true";
    rankdir="TB";
    orientation=port;
    node[style="filled"];
    mode="hier";
    overlap="false";
    ratio="compress";
    splines="true";
    """
    ]

    maxdeps = 0
    if pacs and direction == 2:
        deps = _get_deps(sack, img, pacs, depth, 0)
        temp = {}
        for pac in pacs:
            temp[pac] = copy(deps[pac])
        deps.update(_get_deps(sack, img, pacs, depth, 1))
        for pac in pacs:
            deps[pac].extend(temp[pac])
    else:
        deps = _get_deps(sack, img, pacs, depth, direction)

    for pkg in deps.keys():
        if len(deps[pkg]) > maxdeps:
            maxdeps = len(deps[pkg])

        # color calculations lifted from rpmgraph
        h = 0.5+(0.6/23*len(deps[pkg]))
        s = h+0.1
        b = 1.0

        dot.append('"%s" [color="%s %s %s"];' % (pkg, h, s, b))
        dot.append('"%s" -> {' % pkg)
        for req in deps[pkg]:
            dot.append('"%s"' % req)
        dot.append('} [color="%s %s %s"];\n' % (h, s, b))
    dot.append("}")
    return str("\n".join(dot))


# lifted from repo-graph from yum-utils
def _get_deps(sack, img, pacs, depth, direction):
    requires = {}
    skip = ["glibc", "gcc", "rpm", "libgcc", "rpmlib", "libstdc++"]

    if direction == 1:
        prco = "provides"
        xprco = "requires"
    elif direction == 0:
        prco = "requires"
        xprco = "provides"

    def _get_requires(pkg):
        xx = {}
        for r in pkg.returnPrco(prco):
            reqname = str(r[0])
            if reqname in skip:
                continue
            provider = sack.searchPrco(reqname, xprco)
            if not provider:
                continue
            for p in provider:
                if p.name == pkg.name:
                    xx[p.name] = None
                if p.name in xx or p.name in skip:
                    continue
                if img and p.name not in img.bpkgs:
                    continue
                else:
                    xx[p.name] = None
        return xx.keys()

    if pacs:
        if not depth:
            depth = 20
        count = 0
        for pac in pacs:
            start = sack.searchNevra(name=pac, arch="armv7hl")
            while count < depth:
                for pkg in start:
                    if img and pkg.name not in img.bpkgs:
                        continue
                    if pkg.name in skip:
                        continue

                    requires[pkg.name] = _get_requires(pkg)

                for key, val in requires.items():
                    for n in val:
                        start.extend(sack.searchNevra(name=n, arch="armv7hl"))
                        start.extend(sack.searchNevra(name=n, arch="noarch"))
                count += 1

    else:
        for pkg in sack.returnPackages():
            if img and pkg.name not in img.bpkgs:
                continue
            if pkg.name in skip:
                continue

            requires[pkg.name] = _get_requires(pkg)

    return requires


def _get_svg(dot, prog="neato"):
    _, svg_name = mkstemp()
    dot_graph = pydot.graph_from_dot_data(open(dot).read())
    dot_graph.set_maxiter('2000')
    dot_graph.write_svg(svg_name, prog=prog)
    return svg_name


@receiver(pre_save)
def _graph_pre_save(sender, **kwargs):
    if sender.__name__ == "Graph" and not kwargs['raw']:
        graph = kwargs["instance"]
        if graph.dot and os.path.exists(
            os.path.join(settings.MEDIA_ROOT, graph.dot.name)
        ):
            old_graph = _get_or_none(Graph, pk=graph.id)
            if (
                old_graph and old_graph.dot and
                old_graph.direction == graph.direction and
                old_graph.depth == graph.depth and
                old_graph.packages == graph.packages and
                old_graph.image == graph.image and
                [x.id for x in old_graph.repo.all()] == [
                    x.id for x in graph.repo.all()]
            ):
                return
            else:
                os.remove(os.path.join(settings.MEDIA_ROOT, graph.dot.name))
                if (
                    old_graph and old_graph.svg and
                    os.path.exists(
                        os.path.join(settings.MEDIA_ROOT, graph.svg.name)
                    )
                ):
                    os.remove(
                        os.path.join(settings.MEDIA_ROOT, graph.svg.name)
                    )


@receiver(post_save)
def _graph_post_save(sender, **kwargs):
    if sender.__name__ == "Graph":
        graph = kwargs["instance"]
        if (
            graph.dot and
            os.path.exists(os.path.join(settings.MEDIA_ROOT, graph.dot.name))
        ):
            print "already exists"
            return
        if graph.image:
            repos = graph.image.repo.all()
        elif graph.repo:
            repos = graph.repo.all()
        else:
            print "neither image or repo"
            return

        packages = None
        if graph.packages:
            packages = [p.strip() for p in graph.packages.split(",")]

        graph.dot.save(
            "%s.dot" % graph.id,
            ContentFile(
                _get_dot(
                    repos, graph.image, packages, graph.depth, graph.direction
                )
            )
        )


def _get_project(bs, project):
    return etree.fromstring(bs.getProjectMeta(project))


def _get_project_dot(apiurl, projectname, done, cache):
    if projectname in done:
        return []

    done.add(projectname)

    bs = buildservice.BuildService(apiurl=str(apiurl))

    if projectname in cache:
        project = cache[projectname]
    else:
        project = _get_project(bs, projectname)
        cache[projectname] = project

    dot = []
    for repository in project.iter('repository'):
        parent_node = '"%s~%s"' % (
            project.attrib['name'], repository.attrib['name']
        )

        for child in repository:
            if child.tag == "arch":
                arch = child.text
                dot.append(
                    parent_node + ' [label="%s\\n%s\\n%s"];' % (
                        project.attrib['name'],
                        repository.attrib['name'],
                        arch
                    )
                )
            elif child.tag == "path":
                dep_project = child.attrib['project']
                dot.extend(_get_project_dot(apiurl, dep_project, done, cache))
                child_node = '"%s~%s"' % (
                    child.attrib['project'], child.attrib['repository']
                )
                dot.append("%s -> %s;" % (parent_node, child_node))
    return dot


def _get_projects_dot(apiurl, projects):
    done = set()
    cache = {}
    dot = []
    for project in projects:
        dot.extend(_get_project_dot(apiurl, project, done, cache))

    dot.insert(0, "digraph obs{")
    dot.append("}")
    return dot


def _graph_projects(platform, prjsack):
    projects = set()
    prjids = set()
    for prj in prjsack:
        projects.add(prj.name)
        prjids.add(str(prj.id))
    projects = sorted(projects)
    prjids = sorted(prjids)
    dotfilename = os.path.join(
        settings.MEDIA_ROOT, "graph", "%s_%s.dot" % (
            str(platform.id), "_".join(prjids)
        )
    )
    graph = _get_or_none(Graph, dot=dotfilename)
    if not graph:
        graph = Graph(direction=0)
    dot = _get_projects_dot(prj.buildservice.apiurl, projects)
    graph.dot.save(dotfilename, ContentFile(str("\n".join(dot))), save=False)
    svg = _get_svg(dotfilename, prog="dot")
    graph.svg.save(
        dotfilename.replace(".dot", ".svg"),
        File(open(svg)),
        save=False
    )

    graph.save()
    os.unlink(svg)
    return graph


def _find_obs_pkg(bs, pkg, src_project):
    # probably OBS package name is different from src rpm name
    # use obs search api to find the owner
    # api call path
    path = 'published/binary/id'
    # search predicate
    predicate = "(@name = '%s') and path/@project='%s'" % (pkg, src_project)
    kwa = {path: predicate}
    print kwa
    # osc search function wants keyword args
    result = core.search(bs.apiurl, **kwa)
    # obs search will return results from subprojects as well,
    # so filter further
    filtered = result[path].findall("./binary[@project='%s']" % (src_project))
    if filtered:
        # extract the first package name
        pkg = filtered[0].attrib['package']
        return pkg
    else:

        predicate = "(contains(@name , '%s')) and path/@project='%s'" % (
            pkg, src_project
        )
        kwa = {path: predicate}
        print kwa
        # osc search function wants keyword args
        result = core.search(bs.apiurl, **kwa)
        # obs search will return results from subprojects as well,
        # so filter further
        filtered = result[path].findall(
            "./binary[@project='%s']" % src_project
        )
        if filtered:
            pkg = filtered[0].attrib['package']
            return pkg
        else:
            return None


def _find_promotion_target(prj, prjsack, reverse=True):
    ranked = {}
    prj_parts = set(prj.split(":"))
    for target in prjsack:
        target_parts = set(target.name.split(":"))
        overlap = len(target_parts - prj_parts)
        ranked[overlap] = target
    rank = ranked.keys()
    rank.sort(reverse=not reverse)
    if rank:
        return ranked[rank[0]]
    else:
        return False


def _creq(new_repo, old_repo, submit, delete, comment):
    messages = []
    options = defaultdict(list)
    apiurl = str(new_repo.server.buildservice.apiurl)
    weburl = str(new_repo.server.buildservice.weburl)
    bs = buildservice.BuildService(apiurl=apiurl)
    old_prjsack = old_repo.prjsack

    for pkg_repoid in submit:
        pkg, repoid = pkg_repoid.split("@")
        src_repo = Repo.objects.get(id=repoid)

        src_prj = src_repo.prjsack[0]
        src_prj_pkgs = bs.getPackageList(str(src_prj.name))

        tgt_prj = src_prj.request_target
        if not tgt_prj or tgt_prj not in old_prjsack:
            try:
                tgt_prj = src_prj.request_source.get()
            except ObjectDoesNotExist:
                tgt_prj = None

        if not tgt_prj or tgt_prj not in old_prjsack:
            messages.append(
                "No target project for SR from %s to %s" % (src_prj, old_repo)
            )
            continue

        tgt_prj_pkgs = bs.getPackageList(str(tgt_prj.name))

        if pkg not in src_prj_pkgs:
            print pkg
            print src_prj
            pkg = _find_obs_pkg(bs, pkg, src_prj.name)
            if not pkg:
                messages.append(
                    "OBS package for %s was not found in %s" % (pkg, src_prj)
                )
                continue

        options[tgt_prj.name].append(
            {
                'action': "submit",
                'src_project': src_prj.name,
                'src_package': pkg,
                'tgt_project': tgt_prj.name,
                'tgt_package': pkg,
            }
        )

    for pkg_repoid in delete:
        pkg, repoid = pkg_repoid.split("@")
        tgt_repo = Repo.objects.get(id=repoid)

        tgt_prj = tgt_repo.prjsack[0]
        tgt_prj_pkgs = bs.getPackageList(tgt_prj.name)

        if pkg not in tgt_prj_pkgs:
            pkg = _find_obs_pkg(bs, pkg, tgt_prj.name)
            if not pkg:
                messages.append(
                    "OBS package for %s was not found in %s" % (
                        pkg, tgt_prj.name)
                )
                continue

        options[tgt_prj.name].append(
            {
                'action': "delete",
                'tgt_project': tgt_prj.name,
                'tgt_package': pkg,
            }
        )
    print options
    all_actions = []
    tgts = []
    for tgt, actions in options.items():
        all_actions.extend(actions)
        tgts.append(tgt)

    messages = []
    errors = []
    try:
        req = bs.createRequest(
            options_list=all_actions,
            description=comment,
            comment="Automated request"
        )
        messages.append(
            mark_safe(
                'Created <a href="%s/request/show/%s">SR#%s</a> for %s' % (
                    weburl, req.reqid, req.reqid, ", ".join(tgts)))
        )

    except HTTPError, err:
        status = etree.fromstring(err.read())
        errors.append(
            "Error while creating request: %s" % status.find(("summary")).text
        )

    return messages, errors


def _get_or_other(model, **kwargs):
    try:
        return model.objects.get(**kwargs)
    except ObjectDoesNotExist:
        return "Other"


def _get_or_none(model, **kwargs):
    try:
        return model.objects.get(**kwargs)
    except ObjectDoesNotExist:
        return None


def _sort_filter_diff(diff, pkgs=None, repos=None, meta=None):
    new_diff = {}
    for action, dic in diff.items():
        sdic = OrderedDict()
        for key in sorted(dic.iterkeys()):
            if pkgs and not key[2] in pkgs:
                continue
            if repos and not str(key[0]) in repos:
                continue
            if meta:
                if _exclude_by_meta(dic[key], meta):
                    continue

            sdic[key] = dic[key]
        new_diff[action] = sdic
    return new_diff


def _diff_chlog(oldlogs, newlogs):

    newlog = _fmt_chlog(newlogs)
    oldlog = _fmt_chlog(oldlogs)
    chlog = []
    skip = False
    for line in newlog:
        if line.startswith("*"):
            if line not in oldlog:
                chlog.append(line)
                skip = False
            else:
                skip = True
                continue
        else:
            if not skip:
                chlog.append(line)

    return chlog


def _diff_sacks(newrepo, oldrepo, progress_cb):

    is_livediff = newrepo.is_live and oldrepo.is_live
    newprjsack = newrepo.prjsack
    oldprjsack = oldrepo.prjsack

    repo_pkg_meta = newrepo.pkg_meta
    platforms = set(repo.platform.name for repo in newrepo.comps)
    platforms.add(newrepo.platform.name)

    # key_tuple = ( repo id, repo string, pkg base name )
    # { key_tuple : { binaries : set[] , chlog : [] } }
    added = defaultdict(dict)
    # { key_tuple : set[] }
    removed = defaultdict(set)
    # { key_tuple : {
    #       ovr : old version ,
    #       oa : old arch ,
    #       nvr : new version ,
    #       na : new arch ,
    #       chlo : changelog diff
    #   }
    # }
    modified = {}

    obsoleted = {}
    obsoletes = {}

    ARCHS = set([str(x) for x in Arch.objects.all()])
    ARCHS.add("src")
    toskip = set(["debuginfo", "debugsource"])

    # first go through the new repo collection
    repoids = {}
    if is_livediff and newrepo.comps:
        for repo in newrepo.comps:
            repoids[repo.yumrepoid] = repo
    else:
        repoids[newrepo.yumrepoid] = newrepo

    repo_count = len(repoids.keys()) * 2
    done_count = 0
    for repoid, repo in repoids.items():
        done_count += 1
        progress_cb(math.ceil((float(done_count)/repo_count)*100))
        repo_str = str(repo)
        prjsack = list(repo.prjsack)
        project = None
        if repo.is_live and len(prjsack) == 1:
            project = prjsack[0].request_target
            if not project or project not in oldprjsack:
                try:
                    project = prjsack[0].request_source.get()
                except ObjectDoesNotExist:
                    project = None

            if project and project in oldprjsack:
                project = str(project.name)
            else:
                project = None

        old_comparable = _find_comparable_component(
            repo, oldrepo, project=project)

        if old_comparable:
            old_comparable = old_comparable.yumsack
        else:
            old_comparable = oldrepo.yumsack

        pkgs = []
        if is_livediff:
            pkgs = repo.yumsack.returnPackages()
        else:
            pkgs = repo.yumsack.returnNewestByName()

        for pkg in pkgs:
            # skip archs we don't care about
            if pkg.arch not in ARCHS:
                continue

            # skip debuginfo and debugsource rpms
            suffix = pkg.name.split("-")[-1]
            if suffix in toskip:
                continue

            key_tuple = (repo.id, repo_str, pkg.base_package_name)
            nvr = "%s - %s-%s" % (pkg.name, pkg.ver, pkg.rel)

            oldpkgs = list(old_comparable.searchNames(pkg.name))
            oldpkgs.sort(cmp=lambda x, y: x.verCMP(y), reverse=True)
            oldpkgs = oldpkgs[:1]

            for oldpkg in oldpkgs:

                if key_tuple not in modified:
                    # check for a change in version or release number
                    if not pkg.ver == oldpkg.ver or not pkg.rel == oldpkg.rel:
                        # get new changelog entries
                        chlog = _diff_chlog(oldpkg.changelog, pkg.changelog)
                        # a version change is reported even without changelog
                        # while a release change is ignored in that case
                        if len(chlog) or not pkg.ver == oldpkg.ver:
                            if not len(chlog):
                                chlog.append("No new changelog entries!")
                            modified.update({
                                key_tuple: {
                                    "sense": "Updated"
                                    if pkg.verCMP(oldpkg) == 1 else "Reverted",
                                    "ovr": "%s-%s" % (oldpkg.ver, oldpkg.rel),
                                    "oa": oldpkg.arch,
                                    "nvr": "%s-%s" % (pkg.ver, pkg.rel),
                                    "na": pkg.arch,
                                    "ba": set(),
                                    "br": set(),
                                    "chlo": chlog,
                                    "meta": _get_pkg_meta(
                                        pkg.base_package_name, platforms,
                                        repo_pkg_meta),
                                    "unmet_reqs": set()
                                }
                            })

                if key_tuple in modified:
                    modified[key_tuple]["unmet_reqs"].update(
                        _find_unmet_reqs(
                            pkg, repo.yumsack,
                            oldsack=old_comparable
                        )
                    )

                # we don't need to look further
                break

            if not len(oldpkgs):
                if key_tuple not in added:
                    added[key_tuple]["binaries"] = set()
                    added[key_tuple]["chlog"] = _fmt_chlog(pkg.changelog)
                    added[key_tuple]["meta"] = _get_pkg_meta(
                        pkg.base_package_name, platforms, repo_pkg_meta)
                    added[key_tuple]["unmet_reqs"] = set()
                added[key_tuple]["binaries"].add(nvr)
                added[key_tuple]["unmet_reqs"].update(
                    _find_unmet_reqs(
                        pkg, repo.yumsack, oldsack=old_comparable
                    )
                )

                if pkg.obsoletes:
                    obsoletes[nvr] = pkg.obsoletes

    oldpkgs_by_repoid = defaultdict(list)
    # now go through the old repo collection
    repoids = {}
    if is_livediff and oldrepo.comps:
        for repo in oldrepo.comps:
            repoids[repo.yumrepoid] = repo
    else:
        repoids[oldrepo.yumrepoid] = oldrepo
    repo_count = len(repoids.keys())
    done_count = 0

    for repoid, repo in repoids.items():
        done_count += 1
        progress_cb(math.ceil((((float(done_count)/repo_count)*100)/2)+50))
        pkgs = repo.yumsack.returnPackages()
        repo_str = str(repo)

        # cache the specific comparable component in the older repo
        prjsack = list(repo.prjsack)
        project = None
        if repo.is_live and len(prjsack) == 1:
            try:
                project = prjsack[0].request_source.get()
            except ObjectDoesNotExist:
                project = prjsack[0].request_target

            if project and project in newprjsack:
                project = str(project.name)
            else:
                project = None

        new_comparable = _find_comparable_component(
            repo, newrepo, project=project)

        if new_comparable:
            new_comparable_id = new_comparable.id
            new_comparable_str = str(new_comparable)
            new_comparable = new_comparable.yumsack
        else:
            new_comparable_id = newrepo.id
            new_comparable_str = str(newrepo)
            new_comparable = newrepo.yumsack

        for pkg in pkgs:
            if pkg.arch not in ARCHS:
                continue

            # skip debuginfo and debugsource rpms
            suffix = pkg.name.split("-")[-1]
            if suffix in toskip:
                continue

            # look for removed packages
            if not list(new_comparable.searchNames(pkg.name)):
                key_tuple = (
                    new_comparable_id, new_comparable_str,
                    pkg.base_package_name
                )
                if key_tuple in modified:
                    modified[key_tuple]['br'].add(pkg.name)
                else:
                    oldpkgs_by_repoid[pkg.repoid].append(pkg)

    for repoid, pkgs in oldpkgs_by_repoid.items():
        repo = repoids.get(repoid, oldrepo)
        repo_str = str(repo)

        for pkg in pkgs:
            nvr = "%s - %s-%s" % (pkg.name, pkg.ver, pkg.rel)
            removed[(repo.id, repo_str, pkg.base_package_name)].add(nvr)

            for obsby, obss in obsoletes.items():
                for obs in obss:
                    if pkg.inPrcoRange('provides', obs):
                        obsoleted.update({nvr: obsby})

    # merge added binaries to corresponding entries in modified
    # leftover packages are really new or have been completely removed
    for key_tuple in modified:
        repoid, repostr, pkg = key_tuple
        if key_tuple in added:
            modified[key_tuple]["ba"] = added[key_tuple]['binaries']
            del(added[key_tuple])

    diff = {
        "added": dict(added),
        "removed": dict(removed),
        "modified": modified,
        "obsoleted": obsoleted,
    }

    progress_cb(100)
    return diff


def _get_filter_meta(querydict):
    pkg_meta_types = PackageMetaType.objects.all().prefetch_related("choices")
    filter_meta = {}
    for metatype in pkg_meta_types:
        choices = querydict.getlist(metatype.name, None)
        if choices:
            filter_meta[metatype.name] = choices
    if filter_meta:
        return filter_meta
    else:
        return None
