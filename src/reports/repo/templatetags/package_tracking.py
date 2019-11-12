from django import template

register = template.Library()


@register.filter
def is_any_defined(data, values_list):
    for choice in values_list:
        if data.get(choice.name):
            return True
    return False


@register.filter
def get_from_dict(data, key):
    try:
        return data.get(key, '')
    except KeyError:
        return None


@register.assignment_tag
def is_checked(data, mtype, choice):

    try:
        if mtype.allow_multiple:
            return data[mtype.name][choice.name]
        else:
            return data[mtype.name] == choice.name
    except Exception:
        return ""


@register.filter(is_safe=True)
def list_test_bins(container_packages, pkg):
    try:
        first = container_packages[pkg].keys()[0]
        test_pkgs = ", ".join([
            bpkg
            for bpkg in container_packages[pkg][first]['binaries']
            if bpkg.endswith("-tests")
        ])
        return test_pkgs
    except Exception:
        return ""
