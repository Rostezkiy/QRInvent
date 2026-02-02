# qr_app/forms.py
from copy import deepcopy

from django import forms
from .models import User, EquipmentTemplate, Invitation, Company


# --- Формы для пользователей и приглашений (БЕЗ ИЗМЕНЕНИЙ) ---

class UserRegistrationForm(forms.ModelForm):
    company_name = forms.CharField(max_length=100, label="Название вашей компании")
    password = forms.CharField(widget=forms.PasswordInput, label="Пароль")
    password2 = forms.CharField(widget=forms.PasswordInput, label="Подтвердите пароль")

    class Meta:
        model = User
        fields = ('email', 'company_name', 'password', 'password2')

    def clean_password2(self):
        cd = self.cleaned_data
        if cd['password'] != cd['password2']:
            raise forms.ValidationError('Пароли не совпадают.')
        return cd['password2']

    def clean_email(self):
        email = self.cleaned_data['email']
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError('Пользователь с таким email уже существует.')
        return email


class InvitationForm(forms.ModelForm):
    email = forms.EmailField(
        label="Email сотрудника",
        widget=forms.EmailInput(attrs={'class': 'mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md',
                                       'placeholder': 'name@example.com'})
    )

    class Meta:
        model = Invitation
        fields = ['email']


class InvitedUserRegistrationForm(forms.ModelForm):
    password = forms.CharField(label="Придумайте пароль", widget=forms.PasswordInput(
        attrs={'class': 'mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md'}))
    password2 = forms.CharField(label="Подтвердите пароль", widget=forms.PasswordInput(
        attrs={'class': 'mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md'}))

    class Meta:
        model = User
        fields = ('password', 'password2')

    def clean_password2(self):
        cd = self.cleaned_data
        if cd['password'] != cd['password2']:
            raise forms.ValidationError('Пароли не совпадают.')
        return cd['password2']


# --- Формы для Шаблонов (БЕЗ ИЗМЕНЕНИЙ) ---

class EquipmentTemplateForm(forms.ModelForm):
    class Meta:
        model = EquipmentTemplate
        fields = ['name']
        labels = {'name': 'Название шаблона'}
        widgets = {
            'name': forms.TextInput(attrs={'class': 'mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md'})
        }




# === НОВЫЕ ДИНАМИЧЕСКИЕ ФОРМЫ ===

# --- Базовый класс для динамических форм ---
class BaseDynamicForm(forms.Form):
    """Общий родительский класс для форм, генерирующих поля из JSON-схемы."""

    FIELD_TYPE_MAP = {
        'short_text': (forms.CharField, forms.TextInput, {}),
        'long_text': (forms.CharField, forms.Textarea, {'attrs': {'rows': 3}}),
        'number': (forms.IntegerField, forms.NumberInput, {}),
        'date': (forms.DateField, forms.DateInput, {'attrs': {'type': 'date'}}),
        'checkbox': (forms.BooleanField, forms.CheckboxInput, {}),
    }

    # --- ИЗМЕНЕНИЕ: Определяем CSS-классы для полей ---
    # Классы взяты из вашего примера + добавлены стили для фокуса для лучшего UX
    COMMON_INPUT_CLASSES = (
        'mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm '
        'focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm'
    )
    # У чекбоксов обычно свои, отдельные стили
    CHECKBOX_CLASSES = 'h-4 w-4 text-indigo-600 border-gray-300 rounded focus:ring-indigo-500'


    def __init__(self, *args, **kwargs):
        # Используем ту же исправленную версию, что и в прошлый раз
        self.schema = kwargs.pop('schema', [])
        super().__init__(*args, **kwargs)
        self._create_fields_from_schema()

    def _create_fields_from_schema(self):
        for field_schema in self.schema:
            if 'id' not in field_schema:
                continue

            field_id = field_schema.get('id')
            field_label = field_schema.get('name')
            field_type_key = field_schema.get('type')

            FieldClass, WidgetClass, widget_kwargs = self.FIELD_TYPE_MAP.get(
                field_type_key,
                (forms.CharField, forms.TextInput, {})
            )

            # --- ИЗМЕНЕНИЕ: Логика добавления CSS-классов ---
            final_widget_kwargs = deepcopy(widget_kwargs)
            attrs = final_widget_kwargs.setdefault('attrs', {})

            # Выбираем нужный набор классов в зависимости от типа поля
            if field_type_key == 'checkbox':
                current_classes = self.CHECKBOX_CLASSES
            else:
                current_classes = self.COMMON_INPUT_CLASSES

            # Безопасно добавляем классы, не затирая уже существующие
            attrs['class'] = f"{attrs.get('class', '')} {current_classes}".strip()
            # --- КОНЕЦ ИЗМЕНЕНИЯ ---

            widget_instance = WidgetClass(**final_widget_kwargs)
            is_required = field_type_key != 'checkbox'

            self.fields[field_id] = FieldClass(
                label=field_label,
                required=is_required,
                widget=widget_instance
            )

# --- Форма для статических данных оборудования ---
class StaticDataForm(BaseDynamicForm):
    """Форма для создания/редактирования статических данных оборудования."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Добавляем стандартное поле "Название" в начало
        self.fields = {'name': forms.CharField(
            label="Название оборудования",
            widget=forms.TextInput(attrs={'class': 'mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md'})
        ), **self.fields}


# --- Форма для чек-листа в журнале обслуживания ---
class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput(attrs={
            'class': 'mt-1 block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-md file:border-0 file:text-sm file:font-semibold file:bg-primary-50 file:text-primary-600 hover:file:bg-primary-100'}))
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single_file_clean = super().clean
        if isinstance(data, (list, tuple)):
            return [single_file_clean(d, initial) for d in data]
        return single_file_clean(data, initial)


class DynamicChecklistForm(BaseDynamicForm):
    """Форма для заполнения чек-листа и добавления записи в журнал."""

    images = MultipleFileField(
        label="Прикрепить фотографии (до 3 шт., макс. 5 МБ каждая)",
        required=False
    )

    def clean_images(self):
        images = self.cleaned_data.get('images', [])
        if len(images) > 3:
            raise forms.ValidationError("Можно загрузить не более 3 фотографий.")

        for image in images:
            # ПРОВЕРКА РАЗМЕРА (5 МБ)
            if image.size > 5 * 1024 * 1024:
                raise forms.ValidationError(f"Файл '{image.name}' слишком большой. Максимальный размер - 5 МБ.")
            # ПРОВЕРКА ТИПА (только изображения)
            if image.content_type not in ['image/jpeg', 'image/png', 'image/gif']:
                raise forms.ValidationError(
                    f"Файл '{image.name}' имеет недопустимый формат. Разрешены только JPG, PNG, GIF.")

        return images

class CompanySettingsForm(forms.ModelForm):
    """Форма для редактирования названия и логотипа компании."""
    class Meta:
        model = Company
        fields = ['name', 'logo']
        labels = {
            'name': 'Название компании',
            'logo': 'Логотип (старый будет заменен)'
        }
        widgets = {
            'name': forms.TextInput(attrs={'class': 'mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md', 'readonly': True}),
            'logo': forms.ClearableFileInput(attrs={'class': 'mt-1 block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-md file:border-0 file:text-sm file:font-semibold file:bg-primary-50 file:text-primary-600 hover:file:bg-primary-100'}),
        }