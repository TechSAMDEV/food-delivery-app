from decimal import Decimal
import hmac
import json
import logging
import math
import uuid

from django.conf import settings
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseForbidden, HttpResponseNotAllowed, JsonResponse
from django.db import transaction
from django.db.models import Prefetch, Q
from django.core.exceptions import ImproperlyConfigured
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from accounts.models import UserAddress
from .models import (
    Category,
    MenuItem,
    Order,
    OrderItem,
    OrderStatusHistory,
    PaymentTransaction,
    StoreConfiguration,
)
from .carts import Cart
from .forms import CategoryForm, MenuItemForm
from .payments import PaymentGatewayError, initialize_payment, record_order_status, verify_payment

logger = logging.getLogger(__name__)


def menu_list_view(request):
    """View to display categories and available menu items."""
    categories = Category.objects.prefetch_related(
        Prefetch('items', queryset=MenuItem.objects.filter(is_archived=False)),
    ).all()
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
    menu_item = get_object_or_404(MenuItem, id=item_id, is_archived=False)

    if not menu_item.is_available:
        messages.error(request, f'{menu_item.name} is currently unavailable.')
        return redirect('store:menu_list')

    try:
        quantity = int(request.POST.get('quantity', 1))
    except (TypeError, ValueError):
        quantity = 0

    if quantity < 1:
        messages.error(request, 'Enter a quantity greater than zero.')
        return redirect('store:menu_list')

    cart.add(menu_item=menu_item, quantity=quantity)
    messages.success(request, f'{menu_item.name} was added to your cart.')
    return redirect('store:menu_list')


@require_POST
def cart_update_view(request, item_id):
    cart = Cart(request)
    menu_item = get_object_or_404(MenuItem, pk=item_id, is_archived=False)
    try:
        quantity = int(request.POST.get('quantity', ''))
    except (TypeError, ValueError):
        quantity = 0

    if quantity < 1:
        messages.error(request, 'Enter a quantity greater than zero.')
    elif not menu_item.is_available:
        messages.error(request, f'{menu_item.name} is currently unavailable.')
    else:
        cart.update(menu_item, quantity)
        messages.success(request, f'{menu_item.name} quantity was updated.')

    return redirect('store:cart_detail')


@require_POST
def cart_remove_view(request, item_id):
    cart = Cart(request)
    cart.remove(item_id)
    messages.success(request, 'Item removed from your cart.')
    return redirect('store:cart_detail')


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
    cart_items = list(cart)
    if not cart_items:
        return redirect('store:cart_detail')

    store_config = StoreConfiguration.objects.first()
    user_addresses = list(request.user.addresses.order_by('-is_default', '-created_at'))
    if request.method == 'POST':
        order_type = request.POST.get('order_type', Order.OrderType.DELIVERY)
    else:
        default_order_type = (
            Order.OrderType.DELIVERY
            if store_config
            else Order.OrderType.PICKUP
        )
        order_type = request.GET.get('order_type', default_order_type)
    selected_address_id = request.POST.get('address_id', '') if request.method == 'POST' else request.GET.get('address_id', '')
    if not selected_address_id and request.method != 'POST':
        default_address = next((address for address in user_addresses if address.is_default), None)
        if default_address:
            selected_address_id = str(default_address.id)
    subtotal = sum(
        (item['menu_item'].price * item['quantity'] for item in cart_items),
        Decimal('0.00'),
    )
    delivery_fee = Decimal('0.00')
    delivery_fee_available = True

    if order_type == Order.OrderType.DELIVERY:
        if not store_config:
            delivery_fee_available = False
        else:
            selected_address = next(
                (address for address in user_addresses if str(address.id) == str(selected_address_id)),
                next((address for address in user_addresses if address.is_default), None),
            )
            if selected_address and selected_address.latitude is not None and selected_address.longitude is not None:
                coordinates_valid = (
                    math.isfinite(selected_address.latitude)
                    and math.isfinite(selected_address.longitude)
                    and -90 <= selected_address.latitude <= 90
                    and -180 <= selected_address.longitude <= 180
                )
                if coordinates_valid:
                    delivery_fee_value, _, is_valid = store_config.calculate_delivery_fee(
                        selected_address.latitude,
                        selected_address.longitude,
                    )
                    if is_valid:
                        delivery_fee = Decimal(str(delivery_fee_value))
                    else:
                        delivery_fee_available = False
                else:
                    delivery_fee_available = False
            else:
                delivery_fee = store_config.base_delivery_fee

    total_amount = subtotal + delivery_fee

    def render_checkout(error=None):
        return render(request, 'store/checkout.html', {
            'cart': cart,
            'addresses': user_addresses,
            'store_config': store_config,
            'error': error,
            'subtotal': subtotal,
            'delivery_fee': delivery_fee,
            'total_amount': total_amount,
            'delivery_fee_available': delivery_fee_available,
            'selected_order_type': order_type,
            'selected_address_id': str(selected_address_id),
        })

    if request.method == 'POST':
        if order_type not in dict(Order.OrderType.choices):
            return render_checkout('Please select a valid order type.')

        delivery_address = None
        delivery_fee = Decimal('0.00')

        if order_type == 'DELIVERY':
            if not user_addresses:
                return render_checkout('Add a delivery address before placing a delivery order.')
            if not store_config:
                return render_checkout('Delivery is unavailable because the store location is not configured.')

            address_id = request.POST.get('address_id')
            if not address_id:
                return render_checkout('Please select a delivery address.')

            delivery_address = UserAddress.objects.filter(id=address_id, user=request.user).first()
            if not delivery_address:
                return render_checkout('Please select one of your saved delivery addresses.')

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

        if not request.user.email:
            return render_checkout('Add an email address to your account before paying online.')

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
                    menu_item_name=item['menu_item'].name,
                    quantity=item['quantity'],
                    unit_price=item['menu_item'].price,
                )
                for item in cart_items
            ])
            OrderStatusHistory.objects.create(
                order=order,
                status=order.status,
            )
            payment = PaymentTransaction.objects.create(
                order=order,
                reference=f'savor-{uuid.uuid4().hex}',
                amount=total_amount,
            )

        try:
            payment_url = initialize_payment(
                payment,
                request.build_absolute_uri(reverse('store:payment_callback')),
            )
        except (ImproperlyConfigured, PaymentGatewayError) as error:
            logger.warning('Could not start payment for order %s: %s', order.pk, error)
            return render_checkout(str(error))

        cart.clear()
        return redirect(payment_url)

    return render_checkout()


@login_required
def order_success_view(request, order_id):
    order = get_object_or_404(Order, id=order_id, customer=request.user)
    return render(request, 'store/order_success.html', {'order': order})


def _orders_for_customer(user):
    payments = PaymentTransaction.objects.order_by('-created_at')
    return Order.objects.filter(customer=user).select_related(
        'delivery_address',
        'assigned_rider',
    ).prefetch_related(
        'items__menu_item',
        'status_history',
        Prefetch('payment_transactions', queryset=payments),
    )


@login_required
def order_history_view(request):
    orders = _orders_for_customer(request.user).order_by('-created_at')
    return render(request, 'store/order_history.html', {'orders': orders})


@login_required
def order_detail_view(request, order_id):
    order = get_object_or_404(
        _orders_for_customer(request.user),
        pk=order_id,
    )
    return render(request, 'store/order_detail.html', {'order': order})


@login_required
@require_GET
def order_tracking_status_view(request, order_id):
    order = get_object_or_404(
        Order.objects.filter(customer=request.user).select_related('assigned_rider').prefetch_related(
            'status_history',
            Prefetch(
                'payment_transactions',
                queryset=PaymentTransaction.objects.order_by('-created_at'),
            ),
        ),
        pk=order_id,
    )
    return JsonResponse({
        'status': order.status,
        'status_label': order.get_status_display(),
        'updated_at': order.updated_at.isoformat(),
        'payment_status': (
            order.latest_payment.status
            if order.latest_payment
            else None
        ),
        'events': [
            {
                'status': event.get_status_display(),
                'changed_at': event.changed_at.isoformat(),
            }
            for event in order.status_history.all()
        ],
    })


@login_required
@require_POST
def retry_order_payment_view(request, order_id):
    order = get_object_or_404(
        Order.objects.filter(customer=request.user),
        pk=order_id,
        status=Order.Status.PENDING,
    )
    if order.payment_transactions.filter(
        status=PaymentTransaction.PaymentStatus.SUCCESSFUL,
    ).exists():
        return redirect('store:order_detail', order_id=order.id)
    if not request.user.email:
        messages.error(request, 'Add an email address to your account before paying online.')
        return redirect('store:order_detail', order_id=order.id)

    payment = PaymentTransaction.objects.create(
        order=order,
        reference=f'savor-{uuid.uuid4().hex}',
        amount=order.total_amount,
    )
    try:
        payment_url = initialize_payment(
            payment,
            request.build_absolute_uri(reverse('store:payment_callback')),
        )
    except (ImproperlyConfigured, PaymentGatewayError) as error:
        logger.warning('Could not retry payment for order %s: %s', order.pk, error)
        messages.error(request, str(error))
        return redirect('store:order_detail', order_id=order.id)
    return redirect(payment_url)


@require_GET
def flutterwave_callback_view(request):
    reference = request.GET.get('tx_ref', '')
    payment = get_object_or_404(
        PaymentTransaction.objects.select_related('order', 'order__customer'),
        reference=reference,
    )
    if request.user.is_authenticated and request.user.pk != payment.order.customer_id:
        return HttpResponseForbidden('This payment does not belong to your account.')

    provider_transaction_id = request.GET.get('transaction_id', '')
    if provider_transaction_id:
        try:
            verify_payment(payment, provider_transaction_id)
        except (ImproperlyConfigured, PaymentGatewayError) as error:
            logger.warning('Could not verify payment return for order %s: %s', payment.order_id, error)
            if request.user.is_authenticated:
                messages.error(request, str(error))

    detail_url = reverse('store:order_detail', args=[payment.order_id])
    if request.user.is_authenticated:
        return redirect(detail_url)
    return redirect(f'{reverse("login")}?next={detail_url}')


@csrf_exempt
@require_POST
def flutterwave_webhook_view(request):
    secret = settings.FLUTTERWAVE_WEBHOOK_SECRET
    signature = request.headers.get('verif-hash', '')
    if not secret or not hmac.compare_digest(signature, secret):
        return HttpResponse(status=401)

    try:
        payload = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return HttpResponse(status=400)
    if not isinstance(payload, dict) or payload.get('event') != 'charge.completed':
        return JsonResponse({'status': 'ignored'})

    event_data = payload.get('data')
    if not isinstance(event_data, dict):
        return HttpResponse(status=400)
    payment = PaymentTransaction.objects.filter(
        reference=event_data.get('tx_ref', ''),
    ).first()
    if not payment:
        return JsonResponse({'status': 'ignored'})

    try:
        verify_payment(payment, event_data.get('id', ''))
    except (ImproperlyConfigured, PaymentGatewayError) as error:
        logger.warning('Could not verify Flutterwave webhook for order %s: %s', payment.order_id, error)
        return HttpResponse(status=503)
    return JsonResponse({'status': 'processed'})


def is_kitchen_staff(user):
    """Helper to check if user is staff, kitchen, or admin."""
    return user.is_authenticated and (user.is_staff or getattr(user, 'role', '') in ['KITCHEN', 'ADMIN'])


@login_required
def menu_management_view(request):
    """Show the staff menu editor and handle category creation."""
    if not is_kitchen_staff(request.user):
        return HttpResponseForbidden('Kitchen staff access is required.')

    category_form = CategoryForm(request.POST or None)
    if request.method == 'POST':
        if category_form.is_valid():
            category = category_form.save()
            messages.success(request, f'Category "{category.name}" was added.')
            return redirect('store:menu_manage')
        messages.error(request, 'Please fix the category form errors.')

    menu_items = MenuItem.objects.filter(
        is_archived=False,
    ).select_related('category').order_by('category__display_order', 'category__name', 'name')
    archived_items = MenuItem.objects.filter(
        is_archived=True,
    ).select_related('category').order_by('category__display_order', 'category__name', 'name')
    return render(request, 'store/menu_management.html', {
        'categories': Category.objects.order_by('display_order', 'name'),
        'menu_items': menu_items,
        'archived_items': archived_items,
        'category_form': category_form,
    })


@login_required
@require_http_methods(['GET', 'POST'])
def menu_item_form_view(request, item_id=None):
    """Create or edit a menu item from the staff-facing menu manager."""
    if not is_kitchen_staff(request.user):
        return HttpResponseForbidden('Kitchen staff access is required.')

    menu_item = (
        get_object_or_404(MenuItem, pk=item_id, is_archived=False)
        if item_id is not None
        else None
    )
    form = MenuItemForm(
        request.POST or None,
        request.FILES or None,
        instance=menu_item,
    )
    if request.method == 'POST':
        if form.is_valid():
            saved_item = form.save()
            action = 'updated' if menu_item else 'added'
            messages.success(request, f'"{saved_item.name}" was {action}.')
            return redirect('store:menu_manage')
        messages.error(request, 'Please fix the menu item form errors.')

    return render(request, 'store/menu_item_form.html', {
        'form': form,
        'menu_item': menu_item,
    })


@login_required
@require_POST
def menu_item_delete_view(request, item_id):
    if not is_kitchen_staff(request.user):
        return HttpResponseForbidden('Kitchen staff access is required.')

    menu_item = get_object_or_404(MenuItem, pk=item_id)
    item_name = menu_item.name
    if menu_item.is_archived:
        menu_item.is_archived = False
        menu_item.save(update_fields=['is_archived'])
        messages.success(request, f'"{item_name}" was restored to the menu.')
    else:
        menu_item.is_archived = True
        menu_item.is_available = False
        menu_item.save(update_fields=['is_archived', 'is_available'])
        messages.success(
            request,
            f'"{item_name}" was removed from the menu. Previous orders remain unchanged.',
        )
    return redirect('store:menu_manage')


@login_required
def kitchen_dashboard_view(request):
    """Display the active order feed for kitchen staff and administrators."""
    if not is_kitchen_staff(request.user):
        return HttpResponseForbidden('Kitchen staff access is required.')

    active_orders = Order.objects.filter(
        Q(status__in=[Order.Status.PREPARING, Order.Status.OUT_FOR_DELIVERY])
        | Q(status=Order.Status.PENDING, payment_transactions__isnull=True)
        | Q(
            status=Order.Status.PENDING,
            payment_transactions__status=PaymentTransaction.PaymentStatus.SUCCESSFUL,
        )
    ).exclude(
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
    if order.status == Order.Status.PENDING:
        payment_attempts = PaymentTransaction.objects.filter(order=order)
        if (
            payment_attempts.exists()
            and not payment_attempts.filter(
                status=PaymentTransaction.PaymentStatus.SUCCESSFUL,
            ).exists()
        ):
            next_statuses.pop(Order.Status.PENDING)
    new_status = next_statuses.get(order.status)

    if new_status and request.POST.get('status') == new_status:
        with transaction.atomic():
            locked_order = Order.objects.select_for_update().get(pk=order.pk)
            updated = (
                locked_order.status == order.status
                and record_order_status(locked_order, new_status, request.user)
            )
        if updated:
            messages.success(request, f'Order #{order.id} moved to {order.get_status_display()}.')
        else:
            messages.warning(request, 'This order was updated by another team member. The board is refreshing.')
    else:
        messages.error(request, 'That status change is not allowed.')

    return redirect('store:kitchen_dashboard')


@login_required
def rider_dashboard_view(request):
    if request.user.role != 'RIDER':
        return HttpResponseForbidden('Delivery rider access is required.')

    orders = Order.objects.filter(
        assigned_rider=request.user,
        order_type=Order.OrderType.DELIVERY,
        status__in=[Order.Status.OUT_FOR_DELIVERY, Order.Status.DELIVERED],
    ).select_related(
        'customer',
        'delivery_address',
    ).prefetch_related(
        'items__menu_item',
    ).order_by('status', '-updated_at')
    return render(request, 'store/rider_dashboard.html', {'orders': orders})


@login_required
@require_POST
def rider_mark_delivered_view(request, order_id):
    if request.user.role != 'RIDER':
        return HttpResponseForbidden('Delivery rider access is required.')

    with transaction.atomic():
        order = get_object_or_404(
            Order.objects.select_for_update(),
            pk=order_id,
            assigned_rider=request.user,
            order_type=Order.OrderType.DELIVERY,
        )
        if order.status != Order.Status.OUT_FOR_DELIVERY:
            messages.error(request, 'Only assigned orders out for delivery can be completed.')
        else:
            record_order_status(order, Order.Status.DELIVERED, request.user)
            messages.success(request, f'Order #{order.id} marked delivered.')
    return redirect('store:rider_dashboard')