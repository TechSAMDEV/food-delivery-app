from django import forms
from django.contrib.auth.forms import UserCreationForm
import math

from .models import User, UserAddress


class CustomerRegistrationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username', 'email', 'phone_number')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['email'].required = True
        self.fields['phone_number'].required = False
        self.fields['username'].widget.attrs.update({'autocomplete': 'username'})
        self.fields['email'].widget.attrs.update({'autocomplete': 'email'})
        self.fields['phone_number'].widget.attrs.update({'autocomplete': 'tel'})
        self.fields['password1'].widget.attrs.update({'autocomplete': 'new-password'})
        self.fields['password2'].widget.attrs.update({'autocomplete': 'new-password'})

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = User.Role.CUSTOMER
        if commit:
            user.save()
        return user


class StaffRegistrationForm(UserCreationForm):
    role = forms.ChoiceField(
        choices=(
            (User.Role.KITCHEN, 'Kitchen staff'),
            (User.Role.ADMIN, 'Administrator'),
            (User.Role.RIDER, 'Delivery rider'),
        ),
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username', 'email', 'phone_number', 'role')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['email'].required = True
        self.fields['phone_number'].required = False
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-control'

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = self.cleaned_data['role']
        user.is_staff = user.role in (User.Role.KITCHEN, User.Role.ADMIN)
        if commit:
            user.save()
        return user


class UserAddressForm(forms.ModelForm):
    class Meta:
        model = UserAddress
        fields = ('address_line', 'city', 'latitude', 'longitude', 'is_default')
        widgets = {
            'address_line': forms.TextInput(attrs={'placeholder': 'House number and street'}),
            'city': forms.TextInput(attrs={'placeholder': 'City'}),
            'latitude': forms.NumberInput(attrs={'step': 'any', 'placeholder': 'Optional'}),
            'longitude': forms.NumberInput(attrs={'step': 'any', 'placeholder': 'Optional'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        latitude = cleaned_data.get('latitude')
        longitude = cleaned_data.get('longitude')

        if (latitude is None) != (longitude is None):
            raise forms.ValidationError('Enter both coordinates, or leave both blank.')
        if latitude is not None and longitude is not None:
            if (
                not math.isfinite(latitude)
                or not math.isfinite(longitude)
                or not -90 <= latitude <= 90
                or not -180 <= longitude <= 180
            ):
                raise forms.ValidationError('Enter valid latitude and longitude coordinates.')

        return cleaned_data

    def save(self, user, commit=True):
        address = super().save(commit=False)
        address.user = user
        if not user.addresses.exists():
            address.is_default = True
        if commit:
            address.save()
        return address
