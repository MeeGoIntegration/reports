import datetime
import json
import os
import uuid
from collections import defaultdict
from copy import copy

from django import forms
from django.conf.urls import patterns, url
from django.contrib import admin, messages
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.files import File
from django.core.urlresolvers import reverse
from django.http import HttpResponseNotAllowed, HttpResponse
from django.template.response import TemplateResponse

from .forms import RepoSearchForm
from .misc import _regroup_repo_packages, _search

from .models import (
    ABI, Arch, BuildService, Graph, Image, IssueTracker, Note,
    PackageMetaChoice, PackageMetaType, Platform, Pointer, Project, Repo,
    RepoServer
)
from .utils import (
    _creq, _diff_sacks, _find_previous_pkg_meta, _get_dot, _get_filter_meta,
    _get_latest_image, _get_svg, _graph_projects, _sort_filter_diff,
    _update_pkg_meta
)

try:
    from reports import settings
except ImportError:
    # during development it is in the cwd
    import settings


def _deref(plat, symb):
    if symb == "latest":
        repos = Repo.objects.filter(
            platform__name=plat
        ).exclude(
            release_date=None
        ).order_by('-release')
        return repos[0].id
    elif symb == "previous":
        repos = Repo.objects.filter(
            platform__name=plat
        ).exclude(
            release_date=None
        ).order_by('-release')
        return repos[1].id
    else:
        repos = Repo.objects.filter(platform__name=plat, release=symb)
        if repos.count():
            return repos[0].id

        pointer = Pointer.objects.filter(
            name=symb, target__platform__name=plat
        )
        if pointer.count():
            return pointer[0].target.id
        raise RuntimeError("Unknown symbol %s or platform %s" % (symb, plat))


class GraphForm(forms.ModelForm):
    class Meta:
        model = Graph
        exclude = ("svg", "dot", "pkg_meta")

    def clean(self):
        repos = self.cleaned_data.get("repo")
        image = self.cleaned_data.get("image")
        packages = self.cleaned_data.get("packages")

        if repos and image:
            raise ValidationError(
                'Please choose only an image or set of repos, not both')
        if not repos and not image:
            raise ValidationError(
                'Please choose either an image or a set of repos')

        if packages:
            pkgs = [p.strip() for p in packages.split(",")]
            if image:
                not_in_image = set(pkgs) - set(image.bpkgs)
                if len(not_in_image):
                    raise ValidationError(
                        'Package names %s are not in image %s' %
                        (",".join(not_in_image), image)
                    )
            else:
                not_in_repos = set(copy(pkgs))
                for repo in repos:
                    not_in_repos = not_in_repos - set(repo.packages)
                if len(not_in_repos):
                    raise ValidationError(
                        'Package names %s are not in selected repos' %
                        ",".join(not_in_repos)
                    )

        super(forms.ModelForm, self).clean()

        return self.cleaned_data


class ProjectAdmin(admin.ModelAdmin):
    readonly_fields = ("request_source_wrapper",)

    def request_source_wrapper(self, prj):
        # workaround for https://code.djangoproject.com/ticket/16433
        class req_src(object):
            def __init__(self, prj):
                self.prj = prj

            def __str__(self):
                try:
                    return str(self.prj.request_source.get())
                except Exception:
                    return ""

            def help_text(self):
                return "Request source"

        return req_src(prj)
    request_source_wrapper.short_description = "Request source"


class GraphAdmin(admin.ModelAdmin):
    list_display = (
        '__unicode__', 'related_container', 'has_pkg_meta', 'packages_report',
    )
    raw_id_fields = ['repo']
    radio_fields = {
        "direction": admin.HORIZONTAL
    }
    form = GraphForm
    readonly_fields = ("dot_url", "svg_url")
    anchor = ''

    def related_container(self, obj):
        if obj.image:
            return "image %s" % str(obj.image)
        elif obj.repo.count():
            return "repo %s" % str(obj.repo.all()[0])
        else:
            return ""

    def packages_report(self, obj):
        if self.has_pkg_meta(obj):
            return "<a href='testpackage/%s'>view</a>" % (obj.pk)
        else:
            return ""
    packages_report.allow_tags = True

    def has_pkg_meta(self, obj):
        if obj.pkg_meta and len(obj.pkg_meta.keys()):
            return True
        return False
    has_pkg_meta.boolean = True

    def get_urls(self):
        urls = super(GraphAdmin, self).get_urls()
        my_urls = patterns(
            '',
            url(r'^view/(\d+)/$',
                self.admin_site.admin_view(self.view),
                name="repo_graph_view"),
            url(r'^testpackage/(\d+)/$',
                self.admin_site.admin_view(self.view_testreport),
                name="repo_testpackage_view"),
            url(r'^testpackage/(.+)/(previous|latest|live.*)/$',
                self.admin_site.admin_view(self.view_shortcut),
                name="repo_view_shortcut"),
            url(r'^certification/(\d+)/$',
                self.admin_site.admin_view(self.view_testreport),
                name="repo_testpackage_view"),
            url(r'^certification/(.+)/(previous|latest|live.*)/$',
                self.admin_site.admin_view(self.view_shortcut),
                name="repo_view_shortcut"),
        )
        return my_urls + urls

    def view_shortcut(self, request, plat, symb):
        repoid = _deref(plat, symb)
        graphs = Graph.objects.filter(repo__pk=repoid, packages__in=[None, ""])
        id = None
        if graphs:
            id = graphs[0].id
        return self.view_testreport(request, id, repoid)

    def dot_url(self, graph):
        if (
            graph.dot and
            os.path.exists(os.path.join(settings.MEDIA_ROOT, graph.dot.name))
        ):
            return '<a href="%s">Download</a>' % (
                os.path.join("/", settings.MEDIA_URL, graph.dot.name),
            )
        else:
            return "Not yet generated"

    dot_url.short_description = "DOT file"
    dot_url.allow_tags = True

    def svg_url(self, graph):
        if (
            graph.svg and
            os.path.exists(os.path.join(settings.MEDIA_ROOT, graph.svg.name))
        ):
            return '<a href="%s">Download</a> or <a href="%s">View</a>' % (
                os.path.join("/", settings.MEDIA_URL, graph.svg.name),
                reverse('admin:repo_graph_view', args=(graph.id,)),
            )
        elif (
            graph.dot and
            os.path.exists(os.path.join(settings.MEDIA_ROOT, graph.dot.name))
        ):
            return 'Not yet rendered.<a href="%s">Render and view</a>' % (
                reverse('admin:repo_graph_view', args=(graph.id,)),
            )

    svg_url.short_description = "SVG file"
    svg_url.allow_tags = True

    def pre_fill_pkg_meta(self, graph):
        if graph.image:
            # image packages
            pkgs = {str(graph.image.container_repo): graph.image.packages}
        else:
            # repo packages
            pkgs = {}
            repo = graph.repo.get()
            if repo.components.count() == 0:
                pkgs.update({str(repo.platform): repo.packages})
            else:
                for r in repo.components.all():
                    if r.is_live and r.projects.count() == 1:
                        pkgs.update({
                            str(r.platform) + " " + str(r.projects.all()[0]):
                            r.packages
                        })
                    else:
                        pkgs.update({str(r.platform): r.packages})
        pkg_data = {}

        # loop over packages and fill info
        for repo in pkgs.keys():
            pkg_data[repo] = {}

            for pkg in pkgs[repo].keys():
                pkg_data[repo][pkg] = {}

                for mtype in PackageMetaType.objects.all():
                    mchoices = mtype.choices.all()

                    # for multiple choices make a dictionary
                    if mtype.allow_multiple:
                        pkg_data[repo][pkg][mtype.name] = {}
                        for choice in mchoices:
                            pkg_data[repo][pkg][mtype.name].update(
                                {choice.name: False}
                            )
                    elif mtype.default:
                        pkg_data[repo][pkg][mtype.name] = mtype.default.name
                    # initalize as empty string by default
                    else:
                        pkg_data[repo][pkg][mtype.name] = ""

        return pkg_data

    def view(self, request, graphid):

        graph = Graph.objects.get(pk=graphid)
        if (
            not graph.svg or
            not os.path.exists(
                os.path.join(settings.MEDIA_ROOT, graph.svg.name))
        ):
            dot = os.path.join(settings.MEDIA_ROOT, graph.dot.name)
            svg = _get_svg(dot)
            graph.svg.save(dot.replace(".dot", ".svg"), File(open(svg)))
            graph.save()
            os.unlink(svg)

        context = {
          "title": str(graph),
          "opts": self.model._meta,
          "app_label": self.model._meta.app_label,
          'graph': graph,
        }

        return TemplateResponse(
            request, 'graph.html',
            context=context,
            current_app=self.admin_site.name,
        )

    def view_testreport(self, request, graphid, repoid=None):
        if graphid:
            graph = Graph.objects.get(pk=graphid)
            if graph.repo.count() > 0:
                container = graph.repo.get()
            else:
                container = graph.image
        else:
            graph = None
            container = None

        # for the case when no graph is created yet we need repo
        if repoid:
            container = Repo.objects.get(pk=repoid)

        self.anchor = ""  # only POST will set the anchor

        if (
            request.method == 'POST' and
            request.user.has_perms("reports.add_packagemetatype")
        ):
            repository = request.POST.get('repository')
            pkgs = request.POST.getlist('package')
            pkg_meta_types = list(PackageMetaType.objects.all())
            # generate list of keys that are present on POST
            # and are not key for another dict
            getlist_keys = set([
                x.name for x in pkg_meta_types if not x.allow_multiple
            ]) & set(
                request.POST.keys()
            )
            getlist_items = {}
            for key in getlist_keys:
                getlist_items.update({key: request.POST.getlist(key)})
            # got through all packages and put
            for i, pkg in enumerate(pkgs):
                for k, v in getlist_items.items():
                    graph.pkg_meta[repository][pkg][k] = v[i]

            # checkbox part
            checkbox_types = [
                x for x in
                PackageMetaType.objects.all()
                if x.allow_multiple
            ]
            for ctype in checkbox_types:
                if ctype.name not in graph.pkg_meta[repository][pkg].keys():
                    # dict for different checkboxes
                    graph.pkg_meta[repository][pkg][ctype.name] = {}
                ctype_choices = list(ctype.choices.all())
                cb_choices = [x.name for x in ctype_choices]
                # first initialize to False
                for cb_choice in cb_choices:
                    for pkg in pkgs:
                        if (
                            ctype.name not in
                            graph.pkg_meta[repository][pkg].keys()
                        ):
                            graph.pkg_meta[repository][pkg][ctype.name] = {}
                        graph.pkg_meta[repository][pkg][ctype.name].update(
                            {cb_choice: False}
                        )
                # check relevant checkboxes
                for cb_choice in cb_choices:
                    for pkg in request.POST.getlist(cb_choice):
                        graph.pkg_meta[repository][pkg][ctype.name].update(
                            {cb_choice: True}
                        )

            self.anchor = repository
            graph.save()

        img = _get_latest_image(container.platform.name)

        # generate pkg_meta by copying from latest repo/graph that has it set
        # and then update against repo packages.
        if graph and not graph.pkg_meta:
            old_meta = _find_previous_pkg_meta(graph)
            if old_meta and 'live' not in container.release:
                graph.pkg_meta = old_meta
                _update_pkg_meta(graph, container, img)
            else:
                json_data = self.pre_fill_pkg_meta(graph)
                graph.pkg_meta = json.dumps(json_data)
                graph.save()

        # Update against live data (add/remove)
        if graph and 'live' in container.release:
            _update_pkg_meta(graph, container, img)

        # filter graph.pkg_meta against graph.packages
        if graph and graph.packages:
            graph_pkgs = [p.strip() for p in graph.packages.split(",")]
            for repo in graph.pkg_meta.keys():
                for pkg in graph.pkg_meta[repo].keys():
                    if pkg not in graph_pkgs:
                        del graph.pkg_meta[repo][pkg]

        if not img:
            img_packages = {}
        else:
            img_packages = img.packages

        context = {
            "title": "Testpackage Tracking Tool",
            "opts": self.model._meta,
            "app_label": self.model._meta.app_label,
            'graph': graph,
            'container': container,
            'metatypes': list(
                PackageMetaType.objects.all(
                ).select_related("default").prefetch_related("choices")
            ),
            'latest_image': img,
            'image_packages': img_packages,
            'container_packages': container.packages,
            'anchor': self.anchor
        }
        if "certification" in request.path:
            return TemplateResponse(
                request, 'certification.html',
                context=context,
                current_app=self.admin_site.name,
            )
        else:
            return TemplateResponse(
                request, 'testreport.html',
                context=context,
                current_app=self.admin_site.name,
            )


class NoteAdmin(admin.ModelAdmin):
    raw_id_fields = ("repo",)


class PointerAdmin(admin.ModelAdmin):
    raw_id_fields = ("target",)


class ABIAdmin(admin.ModelAdmin):
    raw_id_fields = ("version",)
    readonly_fields = ("abi_list",)

    def get_urls(self):
        urls = super(ABIAdmin, self).get_urls()
        my_urls = patterns(
            '',
            url(r'^export/(.+)/$',
                self.admin_site.admin_view(self.abi_export),
                name="repo_abi_export"),
        )
        return my_urls + urls

    def abi_export(self, request, pk):
        print pk
        abi = ABI.objects.get(pk=pk)
        print abi
        return HttpResponse(
            json.dumps(abi.listing),
            content_type='application/json',
        )

    def abi_list(self, abi):
        return '<a href="%s?format=json">Get JSON</a>' % (
            reverse('admin:repo_abi_export', args=(abi.id,)),
        )

    abi_list.short_description = "ABI listing"
    abi_list.allow_tags = True


class NoteInline(admin.TabularInline):
    model = Note


class RepoAdmin(admin.ModelAdmin):
    list_display = ['__str__', 'server', 'repo_path']
    filter_horizontal = ['components', 'projects', 'archs']
    date_hierarchy = "release_date"
    list_filter = ('platform', 'server')
    search_fields = ['repo_path', 'release']
    raw_id_fields = ('components', 'projects')
    inlines = [NoteInline]

    def get_urls(self):
        urls = super(RepoAdmin, self).get_urls()
        my_urls = patterns(
            '',
            url(r'^diff/(.+)/(.+)/(.+)/$',
                self.admin_site.admin_view(self.diff_shortcut),
                name="repo_diff_shortcut"),
            url(r'^diff/progress/(.+)/$',
                self.admin_site.admin_view(self.diff_progress),
                name="repo_repo_diff_progress"),
            url(r'^view/(.+)/(.+)/$',
                self.admin_site.admin_view(self.view_shortcut),
                name="repo_view_shortcut"),
            url(r'^prjgraph/(.+)/(previous|latest|live.*)/$',
                self.admin_site.admin_view(self.prjgraph_shortcut),
                name="repo_prjgraph_shortcut"),
            url(r'^prjgraph/(\d+)/$',
                self.admin_site.admin_view(self.prjgraph),
                name="repo_repo_prjgraph"),
            url(r'^diff/(\d+)/(\d+)/$',
                self.admin_site.admin_view(self.diff),
                name="repo_repo_diff"),
            url(r'^view/(\d+)/$',
                self.admin_site.admin_view(self.view),
                name="repo_repo_view"),
            url(r'^search/$',
                self.admin_site.admin_view(self.search),
                name="repo_repo_search"),
            url(r'^list/$',
                self.admin_site.admin_view(self.listall),
                name="repo_repo_list"),
        )
        return my_urls + urls

    def listall(self, request):
        plat_repos = {}
        for p in Platform.objects.all():
            repos = Repo.objects.filter(
                platform__name=p,
                containers=None
            ).order_by('-release_date', '-release')
            repos = repos.select_related(
                'platform', 'server'
            ).prefetch_related(
                'projects', "note_set")
            if repos.count():
                plat_repos[p] = list(repos)

        context = {
            "title": "Repository list",
            "opts": self.model._meta,
            "app_label": self.model._meta.app_label,
            'container': plat_repos
        }

        return TemplateResponse(
            request, 'list.html',
            context=context,
            current_app=self.admin_site.name
        )

    def view_shortcut(self, request, plat, symb):
        repoid = _deref(plat, symb)
        return self.view(request, repoid)

    def search(self, request):
        results = {}
        capidx = {}
        if request.method == "GET":
            form = RepoSearchForm()
        elif request.method == "POST":
            form = RepoSearchForm(request.POST)
            if form.is_valid():
                querytype = form.cleaned_data["QueryType"]
                query = form.cleaned_data["Query"]
                exact = form.cleaned_data["Exact"]
                casei = form.cleaned_data["Casei"]
                for pointer in form.cleaned_data["Targets"]:
                    container = pointer.target
                    pkgs, newcaps = _search(
                        querytype, query, container,
                        exact=exact, casei=casei,
                    )
                    results[str(container)] = pkgs
                    capidx[str(container)] = newcaps
        else:
            return HttpResponseNotAllowed(['GET', 'POST'])

        context = {
            "title": "Repository Search",
            "opts": self.model._meta,
            "app_label": self.model._meta.app_label,
            'form': form,
            'results': results,
            'capidx': capidx,
            'request': request,
        }

        return TemplateResponse(
            request, 'search.html',
            context=context,
            current_app=self.admin_site.name,
        )

    def view(self, request, repoid):
        start = datetime.datetime.now()
        repo = Repo.objects.select_related(
            "server", "platform"
        ).prefetch_related(
            "components", "containers", "projects", "note_set",
            "platform__issuetracker_set", "graph_set"
        ).get(pk=repoid)
        filter_repos = set(request.GET.getlist("repo", None))
        filter_meta = _get_filter_meta(request.GET)
        packages = request.GET.getlist("packages", None)
        if request.GET.get('digraph', False):
            dot = _get_dot(
                [repo], None, packages,
                int(request.GET.get('depth', 1)),
                int(request.GET.get('direction', 0))
            )
            return HttpResponse(dot, content_type='text/vnd.graphviz')
        end = datetime.datetime.now() - start
        context = {
            "title": "Repository details",
            "opts": self.model._meta,
            "app_label": self.model._meta.app_label,
            'container': repo,
            'container_packages': _regroup_repo_packages(
                repo, pkgs=packages, repos=filter_repos, meta=filter_meta),
            'notes': list(repo.note_set.all()),
            'issue_ref': json.dumps(
                [{'name': i.name, 're': i.re, 'url': i.url}
                 for i in repo.platform.issuetracker_set.all()]
            ),
            'graphs': list(repo.graph_set.all()),
            'packagemetatypes': list(PackageMetaType.objects.all()),
            'request': request,
            'is_popup': request.GET.get('is_popup', False),
            'details': request.GET.get('details', False),
            'processing_time': end.total_seconds(),
        }

        return TemplateResponse(
            request, 'view.html',
            context=context,
            current_app=self.admin_site.name,
        )

    def diff_shortcut(self, request, plat, nsymb, osymb):
        nrepoid = _deref(plat, nsymb)
        orepoid = _deref(plat, osymb)
        return self.diff(request, nrepoid, orepoid)

    def diff_progress(self, request, progress_id):
        progress = {progress_id: cache.get(progress_id)}
        return HttpResponse(
            json.dumps(progress),
            content_type="application/json",
        )

    def diff(self, request, new_repoid, old_repoid):
        start = datetime.datetime.now()

        is_popup = request.GET.get('is_popup', False)
        do_regen = request.GET.get('do_regen', False)
        progress_id = request.GET.get('progress_id', None)

        if not request.is_ajax() and request.method != 'POST':
            progress_id = uuid.uuid4()
            context = {
                "title": "",
                "opts": self.model._meta,
                "app_label": self.model._meta.app_label,
                "progress_id": progress_id,
                "do_regen": do_regen,
            }
            return TemplateResponse(
                request, 'diff.html',
                context=context,
                current_app=self.admin_site.name,
            )

        def progress_cb(msg):
            if progress_id is not None:
                cache.set(progress_id, msg, 60*5)

        progress_cb("Initializing repositories")
        new_repo = Repo.objects.select_related(
            "server", "platform"
        ).prefetch_related(
            "projects", "components", "containers"
        ).get(pk=new_repoid)
        old_repo = Repo.objects.select_related(
            "server", "platform"
        ).prefetch_related(
            "projects", "components", "containers"
        ).get(pk=old_repoid)
        live_diff = (new_repo.is_live, old_repo.is_live)

        end = datetime.datetime.now() - start
        context = {
            "title": "",
            "opts": self.model._meta,
            "app_label": self.model._meta.app_label,
            'is_popup': is_popup,
            'new_obj': new_repo,
            'old_obj': old_repo,
            'live_diff': live_diff,
            'processing_time': end.total_seconds(),
            }

        if request.method == 'POST':
            progress_cb("Creating request")
            if not (live_diff[0] and live_diff[1]):
                raise ValidationError("Can only creq on live repos")
            submit = request.POST.getlist('submit')
            delete = request.POST.getlist('delete')
            comment = "Request by %s from repodiff of %s to %s" % (
                request.user, new_repo, old_repo
            )
            creq_msg = request.POST.get('creq_msg')
            if creq_msg:
                comment = "%s\n%s" % (comment, creq_msg)
            mesgs, errors = _creq(new_repo, old_repo, submit, delete, comment)
            for msg in mesgs:
                messages.info(request, msg, extra_tags="safe")
            for err in errors:
                messages.error(request, err, extra_tags="safe")
            progress_cb("Done")

            return TemplateResponse(
                request, 'diff_noprogress.html',
                context=context,
                current_app=self.admin_site.name,
            )

        progress_cb("Generating repository diff")
        cachekey = "%s%s%s" % ("repodiff", new_repoid, old_repoid)
        cached = cache.get_many([cachekey, cachekey + 'ts'])
        diff = cached.get(cachekey)
        diffts = cached.get(cachekey + 'ts')

        if diff is None or do_regen:
            diff = _diff_sacks(new_repo, old_repo, progress_cb)
            diffts = datetime.datetime.now()
            cachelife = (60 * 3) if (
                live_diff[0] or live_diff[1]
            ) else (60 * 60 * 24)
            cache.set_many(
                {cachekey: diff, cachekey + 'ts': diffts}, cachelife
            )

        filter_repos = set(request.GET.getlist("repo", None))
        filter_meta = _get_filter_meta(request.GET)
        diff = _sort_filter_diff(diff, repos=filter_repos, meta=filter_meta)

        issue_ref = []
        names = []
        for i in new_repo.platform.issuetracker_set.all():
            if i.name not in names:
                issue_ref.append(
                    {'name': i.name, 're': i.re, 'url': i.url}
                )
                names.append(i.name)

        full_path = "%s?" % request.path
        for query, values in request.GET.lists():
            full_path += "&".join([
                '%s=%s' % (query, val) for val in values
            ])

        full_path += "&"

        end = datetime.datetime.now() - start
        context.update({
            'title': "Comparing repositories",
            'packagemetatypes': list(PackageMetaType.objects.all()),
            'diff': diff,
            'diffts': diffts,
            'issue_ref': json.dumps(issue_ref),
            'full_path': full_path,
            'processing_time': end.total_seconds()
            })

        progress_cb("Done")
        return TemplateResponse(
            request, "diff_content.html",
            context=context,
            current_app=self.admin_site.name,
        )

    def prjgraph_shortcut(self, request, plat, symb):
        repoid = _deref(plat, symb)
        return self.prjgraph(request, repoid)

    def prjgraph(self, request, repoid):

        repo = Repo.objects.get(pk=repoid)
        graph = _graph_projects(repo.platform, repo.prjsack)

        context = {
          "title": "%s build chain graph" % str(repo),
          "opts": self.model._meta,
          "app_label": self.model._meta.app_label,
          "graph": graph,
        }

        return TemplateResponse(
            request, 'graph.html',
            context=context,
            current_app=self.admin_site.name,
        )


class ImageAdmin(admin.ModelAdmin):
    filter_horizontal = ['repo']

    def get_urls(self):
        urls = super(ImageAdmin, self).get_urls()
        my_urls = patterns(
            '',
            url(r'^diff/(\d+)/(\d+)/$',
                self.admin_site.admin_view(self.diff),
                name="repo_image_diff"),
            url(r'^view/(\d+)/$',
                self.admin_site.admin_view(self.view),
                name="repo_image_view"),
            url(r'^list/$',
                self.admin_site.admin_view(self.listall),
                name="repo_image_list"),
        )
        return my_urls + urls

    def listall(self, request):
        plat_images = defaultdict(list)
        images = Image.objects.select_related(
            "container_repo"
        ).prefetch_related(
            "container_repo__platform"
        ).all().order_by("-container_repo__release")
        for image in images:
            plat_images[image.platform].append(image)

        context = {
            "title": "Image list",
            "opts": self.model._meta,
            "app_label": self.model._meta.app_label,
            'container': dict(plat_images)
        }

        return TemplateResponse(
            request, 'list.html',
            context=context,
            current_app=self.admin_site.name,
        )

    def view(self, request, imageid):
        img = Image.objects.select_related(
            "container_repo"
        ).prefetch_related(
            "repo", "container_repo__platform"
        ).get(pk=imageid)
        issue_ref = []
        for repo in img.repo.all():
            for i in repo.platform.issuetracker_set.all():
                issue_ref.append({'name': i.name, 're': i.re, 'url': i.url})
        # FIXME None does not work in django 'in' lookup
        graphs = Graph.objects.filter(
            image__pk=img.id, packages__in=[None, ""]
        )

        filter_repos = set(request.GET.getlist("repo", None))
        filter_meta = _get_filter_meta(request.GET)

        context = {
            "title": "Image details",
            "opts": self.model._meta,
            "app_label": self.model._meta.app_label,
            'issue_ref': json.dumps(issue_ref),
            'container': img,
            'container_packages': _regroup_repo_packages(
                img.container_repo,
                pkgs=img.packages.keys(),
                repos=filter_repos,
                meta=filter_meta,
            ),
            'graphs': graphs,
            'packagemetatypes': list(PackageMetaType.objects.all()),
            'is_popup': request.GET.get('is_popup', False),
        }
        return TemplateResponse(
            request, 'view.html',
            context=context,
            current_app=self.admin_site.name,
        )

    def diff(self, request, new_imgid, old_imgid):

        new_img = Image.objects.select_related(
            "container_repo"
        ).prefetch_related(
            "repo", "container_repo__platform"
        ).get(pk=new_imgid)
        old_img = Image.objects.select_related(
            "container_repo"
        ).prefetch_related(
            "repo", "container_repo__platform"
        ).get(pk=old_imgid)
        live_diff = (False, False)

        new_repo = new_img.container_repo
        old_repo = old_img.container_repo
        issue_ref = []
        names = []
        for repo in new_img.repo.all():
            for i in repo.platform.issuetracker_set.all():
                if i.name not in names:
                    issue_ref.append(
                        {'name': i.name, 're': i.re, 'url': i.url}
                    )
                    names.append(i.name)
        filter_repos = set(request.GET.getlist("repo"))
        filter_meta = _get_filter_meta(request.GET)

        cachekey = "%s%s%s" % ("repodiff", new_repo.id, old_repo.id)
        cached = cache.get_many([cachekey, cachekey + 'ts'])
        diff = cached.get(cachekey)
        diffts = cached.get(cachekey + 'ts')

        if diff is None:
            diff = _diff_sacks(new_repo, old_repo)
            diffts = datetime.datetime.now()
            cachelife = (60 * 3) if (
                live_diff[0] or live_diff[1]
            ) else (60 * 60 * 24)
            cache.set_many(
                {cachekey: diff, cachekey + 'ts': diffts}, cachelife
            )

        diff = _sort_filter_diff(
            diff,
            pkgs=list(
                set(new_img.packages) | set(old_img.packages)
            ),
            repos=filter_repos,
            meta=filter_meta,
        )

        title = "Comparing Images"
        is_popup = request.GET.get('is_popup', False)

        full_path = "%s?" % request.path
        for query, values in request.GET.lists():
            full_path += "&".join(['%s=%s' % (query, val) for val in values])

        full_path += "&"

        context = {
            "title": title,
            "opts": self.model._meta,
            "app_label": self.model._meta.app_label,
            'diff': diff,
            'diffts': diffts,
            'live_diff': live_diff,
            'new_obj': new_img,
            'old_obj': old_img,
            'is_popup': is_popup,
            'issue_ref': json.dumps(issue_ref),
            'packagemetatypes': list(
                PackageMetaType.objects.all().prefetch_related("choices")
            ),
            "full_path": full_path,
            }

        return TemplateResponse(
            request, 'diff.html',
            context=context,
            current_app=self.admin_site.name,
        )


class PackageMetaChoiceInline(admin.StackedInline):
    model = PackageMetaChoice
    extra = 1


class PackageMetaTypeForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super(PackageMetaTypeForm, self).__init__(*args, **kwargs)
        self.fields['default'].queryset = self.instance.choices.all()


class PackageMetaTypeAdmin(admin.ModelAdmin):
    inlines = [PackageMetaChoiceInline, ]
    form = PackageMetaTypeForm


admin.site.register(RepoServer)
admin.site.register(Platform)
admin.site.register(Repo, RepoAdmin)
admin.site.register(Project, ProjectAdmin)
admin.site.register(Arch)
admin.site.register(Note, NoteAdmin)
admin.site.register(IssueTracker)
admin.site.register(Image, ImageAdmin)
admin.site.register(Graph, GraphAdmin)
admin.site.register(Pointer, PointerAdmin)
admin.site.register(ABI, ABIAdmin)
admin.site.register(PackageMetaType, PackageMetaTypeAdmin)
admin.site.register(PackageMetaChoice)
admin.site.register(BuildService)
