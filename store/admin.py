from django.contrib import admin
from .models import StoreConfiguration, Category, MenuItem, Order, OrderItem, PaymentTransaction

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'display_order')
    prepopulated_fields = {'slug': ('name',)}

@admin.register(MenuItem)
class MenuItemAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'price', 'is_available')
    list_filter = ('category', 'is_available')
    search_fields = ('name',)

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