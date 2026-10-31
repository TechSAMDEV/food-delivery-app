from django.contrib import admin
from django.contrib.auth import get_user_model
from .models import StoreConfiguration, Category, MenuItem, Order, OrderItem, PaymentTransaction
from .models import OrderStatusHistory


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
    list_display = (
        'id',
        'customer',
        'order_type',
        'total_amount',
        'status',
        'assigned_rider',
        'created_at',
    )
    list_filter = ('status', 'order_type', 'assigned_rider')
    list_select_related = ('customer', 'assigned_rider', 'delivery_address')
    inlines = [OrderItemInline]

    def can_assign_riders(self, request):
        user = request.user
        return user.is_superuser or (
            user.is_active
            and user.is_staff
            and getattr(user, 'role', '') == 'ADMIN'
        )

    def has_module_permission(self, request):
        return self.can_assign_riders(request)

    def has_view_permission(self, request, obj=None):
        return self.can_assign_riders(request)

    def has_change_permission(self, request, obj=None):
        return self.can_assign_riders(request)

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    def get_fields(self, request, obj=None):
        if self.can_assign_riders(request) and not request.user.is_superuser:
            return ('assigned_rider',)
        return super().get_fields(request, obj)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'assigned_rider':
            User = get_user_model()
            kwargs['queryset'] = User.objects.filter(
                role=User.Role.RIDER,
                is_active=True,
            ).order_by('username')
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        original_status = None
        if change:
            original_status = Order.objects.only('status').get(pk=obj.pk).status
        super().save_model(request, obj, form, change)
        if change and original_status != obj.status:
            OrderStatusHistory.objects.create(
                order=obj,
                status=obj.status,
                changed_by=request.user,
            )

@admin.register(PaymentTransaction)
class PaymentTransactionAdmin(admin.ModelAdmin):
    list_display = ('reference', 'order', 'amount', 'status', 'provider_transaction_id', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('reference', 'provider_transaction_id', 'order__customer__username')
    readonly_fields = ('order', 'reference', 'provider_transaction_id', 'amount', 'status', 'created_at')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser and request.method == 'GET'

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(OrderStatusHistory)
class OrderStatusHistoryAdmin(admin.ModelAdmin):
    list_display = ('order', 'status', 'changed_at', 'changed_by')
    list_filter = ('status', 'changed_at')
    readonly_fields = ('order', 'status', 'changed_at', 'changed_by')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser and request.method == 'GET'


admin.site.register(StoreConfiguration)