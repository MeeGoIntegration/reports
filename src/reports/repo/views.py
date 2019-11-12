from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.template.response import TemplateResponse

from rest_framework import viewsets

from .models import Pointer, Repo, RepoServer
from .serializers import (
    ReleaseSerializer, RepoSerializer, RepoServerSerializer
)


class RepoViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint that allows repos to be viewed or edited.
    """
    queryset = Repo.objects.filter(components=None)\
        .select_related("server", "platform")\
        .prefetch_related("archs")\
        .order_by('-release_date', '-release')
    serializer_class = RepoSerializer


class RepoServerViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint that allows repos to be viewed or edited.
    """
    queryset = RepoServer.objects.all()
    serializer_class = RepoServerSerializer


class ReleaseViewSet(viewsets.ReadOnlyModelViewSet):

    queryset = Pointer.objects.select_related("target")\
        .prefetch_related("target__images", "target__note_set")\
        .all().order_by("-target__release")
    serializer_class = ReleaseSerializer


def releases(request):

    releases = Pointer.objects.select_related("target")\
        .prefetch_related("target__images", "target__note_set")\
        .all().order_by("-target__release")
    paginator = Paginator(releases, 25)

    page = request.GET.get('page')
    try:
        rels = paginator.page(page)
    except PageNotAnInteger:
        # If page is not an integer, deliver first page.
        rels = paginator.page(1)
    except EmptyPage:
        # If page is out of range (e.g. 9999), deliver last page of results.
        rels = paginator.page(paginator.num_pages)

    context = {"releases":  rels}
    return TemplateResponse(request, 'releases.html', context=context)
