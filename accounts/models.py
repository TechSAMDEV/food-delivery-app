from django.db import models
from django.contrib.auth.models import AbstractUser

class User(AbstractUser):
    class Role(models.TextChoices):
        CUSTOMER = 'CUSTOMER', 'Customer'
        KITCHEN = 'KITCHEN', 'Kitchen Staff'
        RIDER = 'RIDER', 'Delivery Rider'
        ADMIN = 'ADMIN', 'Admin'

    role = models.CharField(
        max_length=20, 
        choices=Role.choices, 
        default=Role.CUSTOMER
    )
    phone_number = models.CharField(max_length=15, blank=True, null=True)

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"


class UserAddress(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='addresses')
    address_line = models.CharField(max_length=255)
    city = models.CharField(max_length=100, default='Lagos')
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        # Ensure only one address is marked default per user
        if self.is_default:
            UserAddress.objects.filter(user=self.user, is_default=True).update(is_default=False)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user.username} - {self.address_line}"