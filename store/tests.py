from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model

from .models import Category, MenuItem, Order, OrderItem


class MenuPageTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name='Mains', slug='mains')
        self.menu_item = MenuItem.objects.create(
            category=self.category,
            name='Jollof rice',
            description='Smoky party-style rice.',
            price='2500.00',
        )

    def test_menu_page_renders_categories_and_available_items(self):
        response = self.client.get(reverse('store:menu_list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Our menu')
        self.assertContains(response, self.category.name)
        self.assertContains(response, self.menu_item.name)
        self.assertContains(response, reverse('store:cart_add', args=[self.menu_item.id]))

    def test_menu_page_shows_empty_state_without_categories(self):
        Category.objects.all().delete()

        response = self.client.get(reverse('store:menu_list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'The menu is getting ready.')

    def test_add_to_cart_from_menu(self):
        response = self.client.post(
            reverse('store:cart_add', args=[self.menu_item.id]),
            {'quantity': '1'},
        )

        self.assertRedirects(response, reverse('store:menu_list'))
        self.assertEqual(self.client.session['cart'][str(self.menu_item.id)]['quantity'], 1)


class KitchenDashboardTests(TestCase):
    def setUp(self):
        self.customer = get_user_model().objects.create_user(
            username='customer',
            password='customer-password',
        )
        self.kitchen_user = get_user_model().objects.create_user(
            username='kitchen',
            password='kitchen-password',
            role='KITCHEN',
        )
        self.category = Category.objects.create(name='Mains', slug='mains')
        self.menu_item = MenuItem.objects.create(
            category=self.category,
            name='Jollof rice',
            price='2500.00',
        )
        self.order = Order.objects.create(
            customer=self.customer,
            order_type=Order.OrderType.DELIVERY,
            subtotal='5000.00',
            delivery_fee='500.00',
            total_amount='5500.00',
            status=Order.Status.PENDING,
        )
        OrderItem.objects.create(
            order=self.order,
            menu_item=self.menu_item,
            quantity=2,
            unit_price='2500.00',
        )

    def test_dashboard_requires_login_and_kitchen_role(self):
        response = self.client.get(reverse('store:kitchen_dashboard'))
        self.assertRedirects(
            response,
            f'{reverse("login")}?next={reverse("store:kitchen_dashboard")}',
        )

        self.client.force_login(self.customer)
        response = self.client.get(reverse('store:kitchen_dashboard'))
        self.assertEqual(response.status_code, 403)

    def test_kitchen_user_can_sign_in_and_open_dashboard(self):
        response = self.client.post(
            reverse('login'),
            {
                'username': 'kitchen',
                'password': 'kitchen-password',
                'next': reverse('store:kitchen_dashboard'),
            },
        )

        self.assertRedirects(response, reverse('store:kitchen_dashboard'))
        self.assertEqual(
            self.client.get(reverse('store:kitchen_dashboard')).status_code,
            200,
        )

    def test_dashboard_shows_items_and_provides_live_partial(self):
        self.client.force_login(self.kitchen_user)

        response = self.client.get(reverse('store:kitchen_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Incoming orders')
        self.assertContains(response, '2 × Jollof rice')
        self.assertContains(response, 'Start preparing')

        partial_response = self.client.get(
            reverse('store:kitchen_dashboard'),
            {'partial': '1'},
        )
        self.assertEqual(partial_response.status_code, 200)
        self.assertContains(partial_response, 'Order #{}'.format(self.order.id))
        self.assertNotContains(partial_response, '<html')

    def test_kitchen_can_advance_order_one_step_at_a_time(self):
        self.client.force_login(self.kitchen_user)
        status_url = reverse('store:update_order_status', args=[self.order.id])

        response = self.client.post(status_url, {'status': Order.Status.PREPARING})
        self.assertRedirects(response, reverse('store:kitchen_dashboard'))
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PREPARING)

        response = self.client.post(status_url, {'status': Order.Status.OUT_FOR_DELIVERY})
        self.assertRedirects(response, reverse('store:kitchen_dashboard'))
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.OUT_FOR_DELIVERY)

    def test_invalid_status_jump_does_not_change_order(self):
        self.client.force_login(self.kitchen_user)
        response = self.client.post(
            reverse('store:update_order_status', args=[self.order.id]),
            {'status': Order.Status.OUT_FOR_DELIVERY},
            follow=True,
        )

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PENDING)
        self.assertContains(response, 'That status change is not allowed.', status_code=200)

    def test_pickup_can_be_completed_after_preparation(self):
        self.order.order_type = Order.OrderType.PICKUP
        self.order.save(update_fields=['order_type'])
        self.client.force_login(self.kitchen_user)
        status_url = reverse('store:update_order_status', args=[self.order.id])

        self.client.post(status_url, {'status': Order.Status.PREPARING})
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PREPARING)

        self.client.post(status_url, {'status': Order.Status.DELIVERED})
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.DELIVERED)
