from django import template
register = template.Library()

@register.assignment_tag(takes_context=True)
def get_pattern(context):
    pattern = None
    try:
        container = context['container']
        component = context['component']
        pattern = container.patterns[component]
    except Exception:
        pass
    return pattern
