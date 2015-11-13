from django import template
register = template.Library()

@register.assignment_tag(takes_context=True)
def what_lookup(context):
    x = []
    try:
        kind = context["kind"]
        x = context["capidx"][context["container"]][kind][context['cap']]
    except KeyError:
        pass
    return x
