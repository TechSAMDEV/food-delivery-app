from django import forms
from django.utils.text import slugify

from .models import Category, MenuItem


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ('name', 'display_order')
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'e.g. Main dishes'}),
            'display_order': forms.NumberInput(attrs={'min': 0}),
        }

    def clean_name(self):
        name = self.cleaned_data['name'].strip()
        base_slug = slugify(name)
        if not base_slug:
            raise forms.ValidationError('Enter a category name containing letters or numbers.')

        slug = base_slug
        suffix = 2
        while Category.objects.filter(slug=slug).exists():
            slug = f'{base_slug}-{suffix}'
            suffix += 1
        self.instance.slug = slug
        return name


class MenuItemForm(forms.ModelForm):
    class Meta:
        model = MenuItem
        fields = ('name', 'category', 'description', 'price', 'image', 'is_available')
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'e.g. Grilled chicken'}),
            'description': forms.Textarea(attrs={
                'rows': 3,
                'placeholder': 'Describe the dish and what makes it special.',
            }),
            'price': forms.NumberInput(attrs={'min': '0.01', 'step': '0.01', 'placeholder': '0.00'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['category'].queryset = Category.objects.order_by('display_order', 'name')
        self.fields['image'].required = False

    def clean_price(self):
        price = self.cleaned_data['price']
        if price <= 0:
            raise forms.ValidationError('Enter a price greater than zero.')
        return price
