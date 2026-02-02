# qr_app/templatetags/qr_extras.py

from django import template

register = template.Library()


@register.filter(name='get_field_name')
def get_field_name(field_id, schema):
    """
    Принимает ID поля и схему шаблона.
    Возвращает человекочитаемое имя поля ('name') из схемы.
    Если поле не найдено (например, было удалено), возвращает сам ID.
    """
    if not isinstance(schema, list):
        return field_id

    for field in schema:
        if field.get('id') == field_id:
            return field.get('name', field_id)  # Возвращаем имя, или ID если у поля нет имени

    return field_id  # Возвращаем ID, если поле вообще не найдено в схеме

@register.filter(name='widget_type')
def widget_type(field):
    """
    Возвращает имя класса виджета в нижнем регистре.
    Это позволяет в шаблоне проверять, какой тип поля используется.
    Использование: {{ form.my_field.field.widget|widget_type }}
    """
    if hasattr(field, 'widget'):
        return field.widget.__class__.__name__.lower()
    return field.__class__.__name__.lower()

@register.filter(name='add_class')
def add_class(field, class_name):
    return field.as_widget(attrs={
        'class': class_name
    })