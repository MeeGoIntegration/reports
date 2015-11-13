from django import template
register = template.Library()

@register.assignment_tag(takes_context=True)
def get_pkg_meta(context, pkg_meta, platform, pkgname, metatype):
    try:
        return pkg_meta[platform][pkgname][metatype]
    except KeyError:
        return None
