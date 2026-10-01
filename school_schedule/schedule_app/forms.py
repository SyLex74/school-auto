from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm, PasswordChangeForm
from captcha.fields import CaptchaField
from cities_light.models import Region, City
from .models import School


# ==================== РУССКИЕ НАЗВАНИЯ ====================

def russian_name(obj):
    """Русское название из alternate_names, иначе name."""
    for alt in (obj.alternate_names or '').split(','):
        alt = alt.strip()
        if alt and any('\u0400' <= ch <= '\u04FF' for ch in alt):
            return alt
    return obj.name


class RussianRegionChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return russian_name(obj)


class RussianCityChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return russian_name(obj)


class SchoolChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        if obj.has_main_teacher():
            return f'{obj.name} (Занята: {obj.get_main_teacher_name()})'
        return f'{obj.name} (Свободна)'


# ==================== РЕГИСТРАЦИЯ ====================

class RegistrationForm(UserCreationForm):
    full_name = forms.CharField(
        max_length=150,
        required=True,
        label='ФИО',
        widget=forms.TextInput(attrs={'placeholder': 'Иванов Иван Иванович'}),
    )
    email = forms.EmailField(
        required=True,
        label='Электронная почта',
        widget=forms.EmailInput(attrs={'placeholder': 'ivan@example.com'}),
    )
    region = RussianRegionChoiceField(
        queryset=Region.objects.none(),
        required=True,
        label='Регион (область/край/республика)',
        widget=forms.Select(attrs={'class': 'region-select'}),
    )
    city = RussianCityChoiceField(
        queryset=City.objects.none(),
        required=True,
        label='Город / Населенный пункт',
        widget=forms.Select(attrs={'class': 'city-select'}),
    )
    school = SchoolChoiceField(
        queryset=School.objects.none(),
        required=True,
        label='Школа',
        widget=forms.Select(attrs={'class': 'school-select'}),
    )
    position = forms.CharField(
        max_length=100,
        required=False,
        label='Должность',
        widget=forms.TextInput(attrs={'placeholder': 'Учитель математики'}),
    )
    captcha = CaptchaField(label='Капча')

    class Meta:
        model = User
        fields = (
            'username', 'full_name', 'email',
            'region', 'city', 'school', 'position',
            'password1', 'password2',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['region'].queryset = Region.objects.filter(
            country__code2='RU'
        ).order_by('name')

        if 'region' in self.data:
            try:
                self.fields['city'].queryset = City.objects.filter(
                    region_id=int(self.data.get('region')),
                    country__code2='RU',
                ).order_by('name')
            except (ValueError, TypeError):
                pass

        if 'city' in self.data:
            try:
                self.fields['school'].queryset = School.objects.filter(
                    city_id=int(self.data.get('city'))
                ).order_by('name')
            except (ValueError, TypeError):
                pass

    def clean_username(self):
        username = self.cleaned_data.get('username')
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError(
                'Пользователь с таким именем уже существует.'
            )
        return username

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError(
                'Пользователь с таким email уже существует.'
            )
        return email

    def clean_full_name(self):
        full_name = self.cleaned_data.get('full_name', '').strip()
        if len(full_name) < 3:
            raise forms.ValidationError('ФИО должно содержать минимум 3 символа')
        if len(full_name.split()) < 2:
            raise forms.ValidationError('Введите полное ФИО (Фамилия и Имя)')
        return full_name

    def clean_password1(self):
        password = self.cleaned_data.get('password1')
        if password and len(password) < 8:
            raise forms.ValidationError('Пароль должен содержать минимум 8 символов')
        if password and not any(c.isdigit() for c in password):
            raise forms.ValidationError('Пароль должен содержать хотя бы одну цифру')
        if password and not any(c.isupper() for c in password):
            raise forms.ValidationError('Пароль должен содержать хотя бы одну заглавную букву')
        if password and not any(c.islower() for c in password):
            raise forms.ValidationError('Пароль должен содержать хотя бы одну строчную букву')
        return password

    def clean_school(self):
        school = self.cleaned_data.get('school')
        if not school:
            return None
        if school.has_main_teacher():
            raise forms.ValidationError(
                f'Эта школа уже занята пользователем '
                f'"{school.get_main_teacher_name()}". '
                f'Пожалуйста, выберите другую школу.'
            )
        return school

    def get_registration_data(self):
        return {
            'username': self.cleaned_data['username'],
            'email': self.cleaned_data['email'],
            'full_name': self.cleaned_data['full_name'],
            'password': self.cleaned_data['password1'],
            'region_id': self.cleaned_data['region'].id if self.cleaned_data.get('region') else None,
            'city_id': self.cleaned_data['city'].id if self.cleaned_data.get('city') else None,
            'school_id': self.cleaned_data['school'].id if self.cleaned_data.get('school') else None,
            'position': self.cleaned_data.get('position', ''),
        }


# ==================== ВХОД ====================

class LoginForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].widget.attrs.update({'placeholder': 'Введите имя пользователя'})
        self.fields['password'].widget.attrs.update({'placeholder': 'Введите пароль'})

    def clean(self):
        username = self.cleaned_data.get('username')
        password = self.cleaned_data.get('password')
        if username and password:
            try:
                user = User.objects.get(username=username)
                if not user.check_password(password):
                    raise forms.ValidationError('Неверный пароль. Пожалуйста, попробуйте снова.')
            except User.DoesNotExist:
                raise forms.ValidationError('Пользователь с таким именем не найден. Пожалуйста, зарегистрируйтесь.')
        return super().clean()


# ==================== РЕДАКТИРОВАНИЕ ПРОФИЛЯ ====================

class ProfileEditForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'email')
        labels = {
            'first_name': 'Имя',
            'last_name': 'Фамилия',
            'email': 'Электронная почта',
        }
        widgets = {
            'first_name': forms.TextInput(attrs={'placeholder': 'Введите ваше имя'}),
            'last_name': forms.TextInput(attrs={'placeholder': 'Введите вашу фамилию'}),
            'email': forms.EmailInput(attrs={'placeholder': 'example@mail.com'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['first_name'].required = True
        self.fields['last_name'].required = True
        self.fields['email'].required = True

    def clean_email(self):
        email = self.cleaned_data.get('email')
        user_id = self.instance.id if self.instance else None
        if User.objects.exclude(id=user_id).filter(email=email).exists():
            raise forms.ValidationError('Этот email уже используется другим пользователем')
        return email

    def clean_first_name(self):
        first_name = self.cleaned_data.get('first_name', '').strip()
        if len(first_name) < 2:
            raise forms.ValidationError('Имя должно содержать минимум 2 символа')
        return first_name

    def clean_last_name(self):
        last_name = self.cleaned_data.get('last_name', '').strip()
        if len(last_name) < 2:
            raise forms.ValidationError('Фамилия должна содержать минимум 2 символа')
        return last_name


# ==================== СМЕНА ПАРОЛЯ ====================

class CustomPasswordChangeForm(PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['old_password'].widget.attrs.update({'placeholder': 'Введите текущий пароль'})
        self.fields['new_password1'].widget.attrs.update({'placeholder': 'Введите новый пароль'})
        self.fields['new_password2'].widget.attrs.update({'placeholder': 'Повторите новый пароль'})

    def clean_new_password1(self):
        password = self.cleaned_data.get('new_password1')
        if password and len(password) < 8:
            raise forms.ValidationError('Новый пароль должен содержать минимум 8 символов')
        if password and not any(c.isdigit() for c in password):
            raise forms.ValidationError('Новый пароль должен содержать хотя бы одну цифру')
        if password and not any(c.isupper() for c in password):
            raise forms.ValidationError('Новый пароль должен содержать хотя бы одну заглавную букву')
        if password and not any(c.islower() for c in password):
            raise forms.ValidationError('Новый пароль должен содержать хотя бы одну строчную букву')
        return password


# ==================== КОД ПОДТВЕРЖДЕНИЯ ====================

class VerificationCodeForm(forms.Form):
    code = forms.CharField(
        max_length=6,
        min_length=6,
        label='Код подтверждения',
        widget=forms.TextInput(attrs={
            'placeholder': 'Введите 6-значный код',
            'class': 'verification-input',
            'maxlength': '6',
            'inputmode': 'numeric',
            'pattern': '[0-9]*',
        }),
    )