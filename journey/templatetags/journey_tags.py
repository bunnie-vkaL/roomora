import uuid
from django import template

register = template.Library()


@register.filter
def vnd(value):
    if value is None:
        return "Chưa biết"
    return f"{int(value):,} đ".replace(",", ".")


@register.filter
def get_item(value, key):
    return value.get(key) if isinstance(value, dict) else None


@register.simple_tag
def mutation_key():
    return str(uuid.uuid4())
