from django.contrib import admin
from .models import StoreConfiguration, Category, MenuItem, Order, OrderItem, PaymentTransaction


class MenuManagerAdminMixin:
    """Grant kitchen staff and admins access only to menu management."""

    def can_manage_menu(self, request):
        user = request.user
        return user.is_superuser or (
            user.is_active
            and user.is_staff
            and getattr(user, 'role', '') in ('KITCHEN', 'ADMIN')
        )

    def has_module_permission(self, request):
        return self.can_manage_menu(request)

    def has_view_permission(self, request, obj=None):
        return self.can_manage_menu(request)

    def has_add_permission(self, request):
        return self.can_manage_menu(request)

    def has_change_permission(self, request, obj=None):
        return self.can_manage_menu(request)

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(Category)
class CategoryAdmin(MenuManagerAdminMixin, admin.ModelAdmin):
    list_display = ('name', 'display_order')
    search_fields = ('name',)
    prepopulated_fields = {'slug': ('name',)}
    fields = ('name', 'slug', 'display_order')

@admin.register(MenuItem)
class MenuItemAdmin(MenuManagerAdminMixin, admin.ModelAdmin):
    list_display = ('name', 'category', 'price', 'is_available')
    list_filter = ('category', 'is_available')
    search_fields = ('name', 'description')
    list_editable = ('price', 'is_available')
    autocomplete_fields = ('category',)
    fields = ('category', 'name', 'description', 'price', 'image', 'is_available')

class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'customer', 'order_type', 'total_amount', 'status', 'created_at')
    list_filter = ('status', 'order_type')
    inlines = [OrderItemInline]

admin.site.register(StoreConfiguration)
admin.site.register(PaymentTransaction)