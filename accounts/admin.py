from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, UserAddress

@admin.register(User)
class CustomUserAdmin(UserAdmin):
    model = User
    list_display = ('username', 'email', 'role', 'phone_number', 'is_staff')
    fieldsets = UserAdmin.fieldsets + (
        ('Additional Info', {'fields': ('role', 'phone_number')}),
    )

@admin.register(UserAddress)
class UserAddressAdmin(admin.ModelAdmin):
    list_display = ('user', 'address_line', 'city', 'is_default')
    list_filter = ('is_default', 'city')