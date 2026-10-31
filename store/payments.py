import logging
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse

import requests
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction

from .models import Order, OrderStatusHistory, PaymentTransaction

logger = logging.getLogger(__name__)

FLUTTERWAVE_API_URL = 'https://api.flutterwave.com/v3'


class PaymentGatewayError(Exception):
    pass


def _secret_key():
    secret_key = getattr(settings, 'FLUTTERWAVE_SECRET_KEY', '')
    if not secret_key:
        raise ImproperlyConfigured('Set FLUTTERWAVE_SECRET_KEY to enable online payments.')
    return secret_key


def initialize_payment(payment, redirect_url):
    secret_key = _secret_key()
    customer = payment.order.customer
    if not customer.email:
        raise PaymentGatewayError('Add an email address to your account before paying online.')

    customer_name = customer.get_full_name().strip() or customer.username
    payload = {
        'tx_ref': payment.reference,
        'amount': str(payment.amount),
        'currency': 'NGN',
        'redirect_url': redirect_url,
        'customer': {
            'email': customer.email,
            'name': customer_name,
            'phonenumber': customer.phone_number or '',
        },
        'customizations': {
            'title': 'Savor Kitchen',
            'description': f'Payment for order #{payment.order_id}',
        },
    }

    try:
        response = requests.post(
            f'{FLUTTERWAVE_API_URL}/payments',
            json=payload,
            headers={'Authorization': f'Bearer {secret_key}'},
            timeout=(5, 20),
        )
        response.raise_for_status()
        result = response.json()
    except (requests.RequestException, ValueError) as error:
        logger.exception('Flutterwave payment initialization failed.')
        raise PaymentGatewayError(
            'We could not connect to the payment service. Your order is still unpaid; try again shortly.'
        ) from error

    link = result.get('data', {}).get('link') if isinstance(result, dict) else None
    parsed_link = urlparse(link or '')
    if (
        not isinstance(link, str)
        or parsed_link.scheme != 'https'
        or parsed_link.hostname != 'checkout.flutterwave.com'
    ):
        logger.error('Flutterwave returned an invalid checkout response.')
        raise PaymentGatewayError(
            'The payment service did not provide a valid checkout link. Please try again.'
        )
    return link


def verify_payment(payment, provider_transaction_id):
    secret_key = _secret_key()
    provider_transaction_id = str(provider_transaction_id)
    if not provider_transaction_id.isdigit():
        raise PaymentGatewayError('The payment reference could not be verified.')

    try:
        response = requests.get(
            f'{FLUTTERWAVE_API_URL}/transactions/{provider_transaction_id}/verify',
            headers={'Authorization': f'Bearer {secret_key}'},
            timeout=(5, 20),
        )
        response.raise_for_status()
        result = response.json()
    except (requests.RequestException, ValueError) as error:
        logger.exception('Flutterwave transaction verification failed.')
        raise PaymentGatewayError(
            'We could not verify your payment yet. Check your order again in a moment.'
        ) from error

    data = result.get('data') if isinstance(result, dict) else None
    if not isinstance(data, dict):
        raise PaymentGatewayError('Flutterwave returned an invalid verification response.')

    try:
        paid_amount = Decimal(str(data.get('amount')))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise PaymentGatewayError('Flutterwave returned an invalid payment amount.') from error

    if (
        str(data.get('tx_ref')) != payment.reference
        or data.get('currency') != 'NGN'
        or paid_amount < payment.amount
    ):
        logger.warning(
            'Flutterwave verification did not match payment record %s.',
            payment.pk,
        )
        raise PaymentGatewayError('Payment details did not match this order.')

    provider_status = data.get('status')
    if provider_status == 'successful':
        with transaction.atomic():
            locked_payment = PaymentTransaction.objects.select_for_update().get(pk=payment.pk)
            locked_order = Order.objects.select_for_update().get(pk=locked_payment.order_id)
            if locked_payment.status != PaymentTransaction.PaymentStatus.SUCCESSFUL:
                locked_payment.status = PaymentTransaction.PaymentStatus.SUCCESSFUL
                locked_payment.provider_transaction_id = provider_transaction_id
                locked_payment.save(update_fields=['status', 'provider_transaction_id'])
                if locked_order.status == Order.Status.PENDING:
                    locked_order.status = Order.Status.PREPARING
                    locked_order.save(update_fields=['status', 'updated_at'])
                    OrderStatusHistory.objects.create(
                        order=locked_order,
                        status=locked_order.status,
                    )
        return True

    if provider_status in {'failed', 'cancelled'}:
        PaymentTransaction.objects.filter(
            pk=payment.pk,
            status=PaymentTransaction.PaymentStatus.PENDING,
        ).update(
            status=PaymentTransaction.PaymentStatus.FAILED,
            provider_transaction_id=provider_transaction_id,
        )
    return False


def record_order_status(order, status, changed_by=None):
    if order.status == status:
        return False
    order.status = status
    order.save(update_fields=['status', 'updated_at'])
    OrderStatusHistory.objects.create(
        order=order,
        status=status,
        changed_by=changed_by,
    )
    return True
