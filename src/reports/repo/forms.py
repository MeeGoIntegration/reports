from django import forms

from .models import Pointer

search_choices = [("packagename", "package name"),
                  ("provides", "provides"),
                  ("file", "file name")]
queryset = Pointer.objects.all().order_by("-target__release")


class RepoSearchForm(forms.Form):

    QueryType = forms.ChoiceField(
        label="Look for", choices=search_choices
    )
    Query = forms.CharField(
        label="", required=True,
    )
    Exact = forms.BooleanField(
        label="Exact match",
        initial=True, required=False
    )
    Casei = forms.BooleanField(
        label="Case insensitive",
        initial=False, required=False
    )
    Targets = forms.ModelMultipleChoiceField(
        label="in",
        queryset=queryset,
        required=True,
        widget=forms.SelectMultiple(attrs={'size': 5})
    )
