from django import template
from django.contrib.admin.templatetags.admin_list import _boolean_icon

register = template.Library()
register.filter('boolean_icon', _boolean_icon)
