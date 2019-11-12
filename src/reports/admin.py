from django.conf import settings
from django.contrib.admin.sites import AdminSite
from django.shortcuts import redirect
from rest_framework import routers

from reports.repo import views as repo_views

router = routers.DefaultRouter()
router.register(r'repo', repo_views.RepoViewSet)
router.register(r'reposerver', repo_views.RepoServerViewSet)
router.register(r'releases', repo_views.ReleaseViewSet)


class ReportsAdmin(AdminSite):
    index_template = 'index.html'

    def get_urls(self):
        # This method is overriden to get rid of the /<app_label>/ component
        # in the urls.

        from django.conf.urls import url, include
        # Empty registry while we get the default admin urls as we don't want
        # the model admin urls from there
        registry = self._registry
        self._registry = {}
        default_patterns = super(ReportsAdmin, self).get_urls()
        self._registry = registry

        app_list_pattern = None
        urlpatterns = []
        for p in default_patterns:
            if p.name != 'app_list':
                urlpatterns.append(p)
            else:
                app_list_pattern = p

        urlpatterns.extend([
            url(r'^api/', include(router.urls)),
            url(r'^releases/$', repo_views.releases),
        ])

        # Add in each model's views, but without the app label
        for model, model_admin in self._registry.iteritems():
            urlpatterns.append(
                url(r'^%s/' % model._meta.module_name,
                    include(model_admin.urls))
            )

        # The app_list view with pattern /<app_label> is added last.
        # Some admin templates require it, but we just redirect to the index
        # view
        urlpatterns.append(app_list_pattern)
        return urlpatterns

    def app_index(self, request, app_label, extra_context=None):
        return redirect('admin:index')

    def index(self, request, extra_context=None):
        if extra_context is None:
            extra_context = {}
        extra_context['shortcuts_template'] = settings.SHORTCUTS_TEMPLATE
        return super(ReportsAdmin, self).index(
            request, extra_context=extra_context
        )


site = ReportsAdmin(name='admin', app_name='reports')
