from django import template

register = template.Library()


@register.filter
def get(dictionary, key):
    """Look up a key in a dictionary. Usage: {{ mydict|get:key }}"""
    if dictionary is None:
        return None
    return dictionary.get(key)
