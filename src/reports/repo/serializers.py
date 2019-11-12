from rest_framework import serializers

from .models import Pointer, Repo, RepoServer


class RepoServerSerializer(serializers.ModelSerializer):
    class Meta:
        model = RepoServer
        fields = ('url',)


class RepoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Repo
        fields = (
            'server', 'repo_path', 'platform', 'components', 'release',
            'archs',
        )
        depth = 10


class ReleaseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Pointer
