from decimal import Decimal
import json
import math

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden, HttpResponseNotAllowed, JsonResponse
from django.db import transaction
from django.utils import timezone

from accounts.models import UserAddress
from .models import Category, MenuItem, Order, OrderItem, StoreConfiguration
from .carts import Cart


def menu_list_view(request):
    """View to display categories and available menu items."""
    categories = Category.objects.prefetch_related('items').all()
    store_config = StoreConfiguration.objects.first()
    context = {
        'categories': categories,
        'store_config': store_config,
    }
    return render(request, 'store/menu.html', context)


def cart_add_view(request, item_id):
    """Add a menu item to the session cart."""
    if request.method != 'POST':
        return redirect('store:menu_list')

    cart = Cart(request)
    menu_item = get_object_or_404(MenuItem, id=item_id)

    if not menu_item.is_available:
        return redirect('store:menu_list')

    try:
        quantity = int(request.POST.get('quantity', 1))
    except (TypeError, ValueError):
        quantity = 0

    if quantity < 1:
        return redirect('store:menu_list')

    cart.add(menu_item=menu_item, quantity=quantity)
    return redirect('store:menu_list')


def cart_detail_view(request):
    """View the items currently in the cart."""
    cart = Cart(request)
    return render(request, 'store/cart.html', {'cart': cart})


def calculate_delivery_api(request):
    """API endpoint to calculate delivery fee based on customer lat/lng."""
    if request.method != 'POST':
        return JsonResponse(
            {'status': 'error', 'message': 'Invalid request method.'},
            status=405,
        )

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse(
            {'status': 'error', 'message': 'Request body must contain valid JSON.'},
            status=400,
        )

    if not isinstance(data, dict):
        return JsonResponse(
            {'status': 'error', 'message': 'Request body must be a JSON object.'},
            status=400,
        )

    try:
        customer_lat = float(data['latitude'])
        customer_lng = float(data['longitude'])
    except (KeyError, TypeError, ValueError):
        return JsonResponse(
            {'status': 'error', 'message': 'Valid latitude and longitude are required.'},
            status=400,
        )

    if (
        not math.isfinite(customer_lat)
        or not math.isfinite(customer_lng)
        or not -90 <= customer_lat <= 90
        or not -180 <= customer_lng <= 180
    ):
        return JsonResponse(
            {'status': 'error', 'message': 'Latitude or longitude is out of range.'},
            status=400,
        )

    store = StoreConfiguration.objects.first()
    if not store:
        return JsonResponse(
            {'status': 'error', 'message': 'Store location is not configured.'},
            status=400,
        )

    fee, distance, is_valid = store.calculate_delivery_fee(customer_lat, customer_lng)
    if not is_valid:
        return JsonResponse({
            'status': 'out_of_range',
            'message': (
                f'You are {distance}km away. Maximum delivery radius is '
                f'{store.max_delivery_radius_km}km.'
            ),
        })

    return JsonResponse({
        'status': 'success',
        'distance_km': distance,
        'delivery_fee': float(fee),
    })


@login_required
def checkout_view(request):
    cart = Cart(request)
    if len(cart.cart) == 0:
        return redirect('store:cart_detail')

    store_config = StoreConfiguration.objects.first()
    user_addresses = request.user.addresses.all()

    def render_checkout(error=None):
        return render(request, 'store/checkout.html', {
            'cart': cart,
            'addresses': user_addresses,
            'store_config': store_config,
            'error': error,
        })

    if request.method == 'POST':
        order_type = request.POST.get('order_type', 'DELIVERY')

        if order_type not in dict(Order.OrderType.choices):
            return render_checkout('Please select a valid order type.')

        delivery_address = None
        delivery_fee = Decimal('0.00')

        if order_type == 'DELIVERY':
            if not store_config:
                return render_checkout('Delivery is unavailable because the store location is not configured.')

            address_id = request.POST.get('address_id')
            if not address_id:
                return render_checkout('Please select a delivery address.')

            delivery_address = get_object_or_404(UserAddress, id=address_id, user=request.user)

            # Recalculate delivery fee securely on backend
            if delivery_address.latitude is not None and delivery_address.longitude is not None:
                if (
                    not math.isfinite(delivery_address.latitude)
                    or not math.isfinite(delivery_address.longitude)
                    or not -90 <= delivery_address.latitude <= 90
                    or not -180 <= delivery_address.longitude <= 180
                ):
                    return render_checkout('The selected address has invalid location details.')

                fee, distance, is_valid = store_config.calculate_delivery_fee(
                    delivery_address.latitude, delivery_address.longitude
                )
                if not is_valid:
                    return render_checkout('Selected address is out of delivery range.')
                delivery_fee = Decimal(str(fee))
            else:
                delivery_fee = store_config.base_delivery_fee

        cart_items = list(cart)
        if len(cart_items) != len(cart):
            return render_checkout('A menu item in your cart is no longer available. Please review your cart.')

        unavailable_item = next(
            (item['menu_item'] for item in cart_items if not item['menu_item'].is_available),
            None,
        )
        if unavailable_item:
            return render_checkout(
                f'{unavailable_item.name} is no longer available. Please review your cart.'
            )

        # Use current database prices rather than prices retained in the session cart.
        subtotal = sum(
            (item['menu_item'].price * item['quantity'] for item in cart_items),
            Decimal('0.00'),
        )
        total_amount = subtotal + delivery_fee

        with transaction.atomic():
            order = Order.objects.create(
                customer=request.user,
                delivery_address=delivery_address,
                order_type=order_type,
                subtotal=subtotal,
                delivery_fee=delivery_fee,
                total_amount=total_amount,
                status=Order.Status.PENDING,
            )

            OrderItem.objects.bulk_create([
                OrderItem(
                    order=order,
                    menu_item=item['menu_item'],
                    quantity=item['quantity'],
                    unit_price=item['menu_item'].price,
                )
                for item in cart_items
            ])

        cart.clear()
        return redirect('store:order_success', order_id=order.id)

    return render_checkout()


@login_required
def order_success_view(request, order_id):
    order = get_object_or_404(Order, id=order_id, customer=request.user)
    return render(request, 'store/order_success.html', {'order': order})


def is_kitchen_staff(user):
    """Helper to check if user is staff, kitchen, or admin."""
    return user.is_authenticated and (user.is_staff or getattr(user, 'role', '') in ['KITCHEN', 'ADMIN'])


@login_required
def kitchen_dashboard_view(request):
    """Display the active order feed for kitchen staff and administrators."""
    if not is_kitchen_staff(request.user):
        return HttpResponseForbidden('Kitchen staff access is required.')

    active_orders = Order.objects.exclude(
        status__in=[Order.Status.DELIVERED, Order.Status.CANCELLED]
    ).select_related(
        'customer', 'delivery_address',
    ).prefetch_related(
        'items__menu_item',
    ).order_by('-created_at')

    if request.GET.get('partial') == '1':
        return render(request, 'store/_kitchen_orders.html', {'orders': active_orders})

    context = {
        'orders': active_orders,
    }
    return render(request, 'store/kitchen_dashboard.html', context)


@login_required
def update_order_status_view(request, order_id):
    """Advance an order by one valid step from the kitchen dashboard."""
    if not is_kitchen_staff(request.user):
        return HttpResponseForbidden('Kitchen staff access is required.')

    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    order = get_object_or_404(Order, id=order_id)
    next_statuses = {
        Order.Status.PENDING: Order.Status.PREPARING,
        Order.Status.PREPARING: (
            Order.Status.OUT_FOR_DELIVERY
            if order.order_type == Order.OrderType.DELIVERY
            else Order.Status.DELIVERED
        ),
        Order.Status.OUT_FOR_DELIVERY: Order.Status.DELIVERED,
    }
    new_status = next_statuses.get(order.status)

    if new_status and request.POST.get('status') == new_status:
        with transaction.atomic():
            updated = Order.objects.filter(
                pk=order.pk,
                status=order.status,
            ).update(status=new_status, updated_at=timezone.now())
        if updated:
            messages.success(request, f'Order #{order.id} moved to {order.get_status_display()}.')
        else:
            messages.warning(request, 'This order was updated by another team member. The board is refreshing.')
    else:
        messages.error(request, 'That status change is not allowed.')

    return redirect('store:kitchen_dashboard')