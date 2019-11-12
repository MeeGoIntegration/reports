from django import template
register = template.Library()


@register.assignment_tag(takes_context=True)
def render_pkg_meta(context):
    output = []
    for metatype in context['packagemetatypes']:
        try:
            value = context['pkg'].get("meta", {}).get(metatype.name, {})
            if metatype.allow_multiple:
                values = [k for k in value if value[k]]
                if values:
                    output.append((metatype.description, ", ".join(values)))
            else:
                if value:
                    output.append((metatype.description, value))
        except KeyError:
            pass

    return output
