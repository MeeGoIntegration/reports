from django import template

register = template.Library()


@register.assignment_tag(takes_context=True)
def get_pkg(context, pkgname):
    return context['container_packages'].get(pkgname)
