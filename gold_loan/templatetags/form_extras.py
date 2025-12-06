from django import template
from django.utils.safestring import mark_safe

register = template.Library()

@register.filter(name='add_class')
def add_class(field, css):
    """
    Usage: {{ form.field|add_class:"my-class" }}
    Works with BoundField. Merges with existing widget 'class' attr; falls back to string injection.
    """
    try:
        # BoundField -> widget attrs merging
        widget = field.field.widget
        existing = widget.attrs.get('class', '')
        classes = (existing + ' ' + css).strip() if existing else css
        attrs = dict(widget.attrs)
        attrs['class'] = classes
        return field.as_widget(attrs=attrs)
    except Exception:
        # Fallback: try to inject into rendered HTML
        try:
            s = str(field)
            if '<input' in s:
                return mark_safe(s.replace('<input', f'<input class="{css}"', 1))
            return s
        except Exception:
            return ''
