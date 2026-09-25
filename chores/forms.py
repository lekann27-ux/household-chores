from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User

from .models import Chore, Household


class RegisterForm(UserCreationForm):
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={'placeholder': 'you@example.com', 'autocomplete': 'email'}),
        help_text="Required for household communications and notifications."
    )
    first_name = forms.CharField(
        max_length=30,
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'First Name', 'autocomplete': 'given-name'})
    )
    last_name = forms.CharField(
        max_length=30,
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Last Name', 'autocomplete': 'family-name'})
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username', 'email', 'first_name', 'last_name')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].widget.attrs.update({
            'placeholder': 'Choose a username',
            'autocomplete': 'username',
        })
        self.fields['password1'].widget.attrs.update({
            'placeholder': 'Create a secure password',
            'autocomplete': 'new-password',
        })
        self.fields['password2'].widget.attrs.update({
            'placeholder': 'Confirm your password',
            'autocomplete': 'new-password',
        })
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-input'

    def clean_email(self):
        email = self.cleaned_data.get('email', '').strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email address already exists.")
        return email


class LoginForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].widget.attrs.update({
            'placeholder': 'Enter your username',
            'class': 'form-input',
            'autocomplete': 'username',
        })
        self.fields['password'].widget.attrs.update({
            'placeholder': 'Enter your password',
            'class': 'form-input',
            'autocomplete': 'current-password',
        })


class HouseholdCreationForm(forms.ModelForm):
    class Meta:
        model = Household
        fields = ('name',)
        widgets = {
            'name': forms.TextInput(attrs={
                'placeholder': 'e.g. Elm Street Flat, Apartment 4B',
                'class': 'form-input',
                'autocomplete': 'off',
            })
        }
        labels = {
            'name': 'Household Name',
        }
        help_texts = {
            'name': 'A friendly name to identify your shared home.',
        }

    def clean_name(self):
        name = self.cleaned_data.get('name', '').strip()
        if not name:
            raise forms.ValidationError("Household name cannot be blank.")
        return name


class HouseholdJoinForm(forms.Form):
    join_code = forms.CharField(
        max_length=12,
        label="Household Join Code",
        widget=forms.TextInput(attrs={
            'placeholder': 'Enter invite code',
            'class': 'form-input',
            'autocomplete': 'off',
            'style': 'text-transform: uppercase; font-family: monospace; letter-spacing: 0.1em; font-weight: 600;',
        }),
        help_text="Ask your household administrator for the invite code."
    )

    def clean_join_code(self):
        code = self.cleaned_data.get('join_code', '').strip().upper()
        if not code:
            raise forms.ValidationError("Please provide a join code.")
        if not Household.objects.filter(join_code=code).exists():
            raise forms.ValidationError("Invalid join code. Please check with your household administrator.")
        return code


class ChoreForm(forms.ModelForm):
    class Meta:
        model = Chore
        fields = ('title', 'description', 'frequency_type', 'frequency_interval', 'is_active')
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'e.g. Clean the kitchen',
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-input',
                'rows': 4,
                'placeholder': 'Instructions or notes (optional)',
            }),
            'frequency_type': forms.Select(attrs={'class': 'form-input'}),
            'frequency_interval': forms.NumberInput(attrs={
                'class': 'form-input',
                'min': 1,
            }),
            'is_active': forms.CheckboxInput(),
        }
        labels = {
            'frequency_type': 'Frequency',
            'frequency_interval': 'Interval',
            'is_active': 'Active',
        }
        help_texts = {
            'frequency_interval': 'How many days, weeks, or months between occurrences.',
        }

    def clean_frequency_interval(self):
        interval = self.cleaned_data['frequency_interval']
        if interval < 1:
            raise forms.ValidationError('The interval must be at least 1.')
        return interval
