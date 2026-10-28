from django.urls import path
from . import views

app_name = 'store'

urlpatterns = [
    path('', views.menu_list_view, name='menu_list'),
    path('cart/', views.cart_detail_view, name='cart_detail'),
    path('cart/add/<int:item_id>/', views.cart_add_view, name='cart_add'),
    path('api/calculate-delivery/', views.calculate_delivery_api, name='calculate_delivery'),
    path('checkout/', views.checkout_view, name='checkout'),
    path('order/success/<int:order_id>/', views.order_success_view, name='order_success'),
    path('kitchen/', views.kitchen_dashboard_view, name='kitchen_dashboard'),
    path('kitchen/order/<int:order_id>/status/', views.update_order_status_view, name='update_order_status'),
]