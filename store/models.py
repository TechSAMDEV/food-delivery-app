from django.db import models
from django.conf import settings
from geopy.distance import geodesic

# ================================
# 1. STORE & DELIVERY CONFIG
# ================================
class StoreConfiguration(models.Model):
    name = models.CharField(max_length=100, default="Kilimanjaro Branch")
    address = models.CharField(max_length=255)
    latitude = models.FloatField(help_text="Store latitude coordinate")
    longitude = models.FloatField(help_text="Store longitude coordinate")
    
    base_delivery_fee = models.DecimalField(max_digits=10, decimal_places=2, default=500.00)
    per_km_rate = models.DecimalField(max_digits=10, decimal_places=2, default=100.00)
    max_delivery_radius_km = models.FloatField(default=15.0, help_text="Maximum service coverage area in kilometers")

    def calculate_delivery_fee(self, customer_lat, customer_lng):
        store_coords = (self.latitude, self.longitude)
        customer_coords = (customer_lat, customer_lng)
        
        distance_km = geodesic(store_coords, customer_coords).km
        
        if distance_km > self.max_delivery_radius_km:
            return None, distance_km, False
            
        fee = self.base_delivery_fee + (float(distance_km) * float(self.per_km_rate))
        return round(fee, 2), round(distance_km, 2), True

    def __str__(self):
        return self.name


# ================================
# 2. MENU & INVENTORY
# ================================
class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True)
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name_plural = "Categories"
        ordering = ['display_order', 'name']

    def __str__(self):
        return self.name


class MenuItem(models.Model):
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='items')
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    image = models.ImageField(upload_to='menu_items/', blank=True, null=True)
    is_available = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} - ₦{self.price}"


# ================================
# 3. ORDERS & PAYMENTS
# ================================
class Order(models.Model):
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending Payment'
        PREPARING = 'PREPARING', 'Preparing in Kitchen'
        OUT_FOR_DELIVERY = 'OUT_FOR_DELIVERY', 'Out for Delivery'
        DELIVERED = 'DELIVERED', 'Delivered'
        CANCELLED = 'CANCELLED', 'Cancelled'

    class OrderType(models.TextChoices):
        DELIVERY = 'DELIVERY', 'Home Delivery'
        PICKUP = 'PICKUP', 'Store Pickup'

    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='orders')
    delivery_address = models.ForeignKey('accounts.UserAddress', on_delete=models.SET_NULL, null=True, blank=True)
    order_type = models.CharField(max_length=10, choices=OrderType.choices, default=OrderType.DELIVERY)
    
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    delivery_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Order #{self.id} - {self.customer.username} ({self.status})"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    menu_item = models.ForeignKey(MenuItem, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)

    @property
    def get_total(self):
        return self.quantity * self.unit_price

    def __str__(self):
        return f"{self.quantity}x {self.menu_item.name} for Order #{self.order.id}"


class PaymentTransaction(models.Model):
    class PaymentStatus(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        SUCCESSFUL = 'SUCCESSFUL', 'Successful'
        FAILED = 'FAILED', 'Failed'

    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name='payment')
    reference = models.CharField(max_length=100, unique=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Tx {self.reference} - {self.status}"