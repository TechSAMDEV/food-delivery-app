from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model

from .models import Category, MenuItem, Order, OrderItem, StoreConfiguration


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

    def test_unavailable_menu_item_is_displayed_without_add_button(self):
        self.menu_item.is_available = False
        self.menu_item.save(update_fields=['is_available'])

        response = self.client.get(reverse('store:menu_list'))

        self.assertContains(response, self.menu_item.name)
        self.assertContains(response, 'Currently unavailable')
        self.assertNotContains(response, reverse('store:cart_add', args=[self.menu_item.id]))

    def test_homepage_shows_sign_in_link_for_anonymous_users(self):
        response = self.client.get(reverse('store:menu_list'))

        self.assertContains(response, reverse('login'))
        self.assertContains(response, reverse('register'))
        self.assertContains(response, 'Register')
        self.assertNotContains(response, 'Kitchen dashboard')

    def test_homepage_shows_kitchen_link_only_for_staff_and_admins(self):
        customer = get_user_model().objects.create_user(
            username='customer',
            password='customer-password',
        )
        kitchen_user = get_user_model().objects.create_user(
            username='kitchen',
            password='kitchen-password',
            role='KITCHEN',
        )

        self.client.force_login(customer)
        customer_response = self.client.get(reverse('store:menu_list'))
        self.assertContains(customer_response, 'Sign out')
        self.assertContains(customer_response, 'customer')
        self.assertNotContains(customer_response, 'Kitchen dashboard')

        self.client.force_login(kitchen_user)
        kitchen_response = self.client.get(reverse('store:menu_list'))
        self.assertContains(kitchen_response, reverse('store:kitchen_dashboard'))
        self.assertContains(kitchen_response, 'Kitchen dashboard')
        self.assertContains(kitchen_response, 'kitchen')

    def test_homepage_shows_full_name_for_authenticated_admin(self):
        admin_user = get_user_model().objects.create_user(
            username='admin',
            password='admin-password',
            role='ADMIN',
            first_name='Ada',
            last_name='Admin',
        )
        self.client.force_login(admin_user)

        response = self.client.get(reverse('store:menu_list'))

        self.assertContains(response, 'Ada Admin')
        self.assertContains(response, 'Kitchen dashboard')
        self.assertContains(response, 'Manage staff')
        self.assertContains(response, 'Admin')
        self.assertContains(response, 'class="account-menu"')

    def test_password_visibility_controls_render_on_account_forms(self):
        login_response = self.client.get(reverse('login'))
        self.assertContains(login_response, 'data-password-toggle')
        self.assertContains(login_response, 'aria-controls="id_password"')
        self.assertContains(login_response, "input.type = isVisible ? 'text' : 'password';")

        register_response = self.client.get(reverse('register'))
        self.assertEqual(register_response.content.count(b'data-password-toggle'), 3)
        self.assertContains(register_response, 'aria-controls="id_password1"')
        self.assertContains(register_response, 'aria-controls="id_password2"')
        self.assertContains(register_response, "input.type = isVisible ? 'text' : 'password';")

        admin_user = get_user_model().objects.create_user(
            username='admin',
            password='admin-password',
            role='ADMIN',
        )
        self.client.force_login(admin_user)
        staff_response = self.client.get(reverse('staff_register'))
        self.assertEqual(staff_response.content.count(b'data-password-toggle'), 3)
        self.assertContains(staff_response, 'aria-controls="id_password1"')
        self.assertContains(staff_response, 'aria-controls="id_password2"')
        self.assertContains(staff_response, "input.type = isVisible ? 'text' : 'password';")


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
            },
        )

        self.assertRedirects(response, reverse('store:menu_list'))
        homepage_response = self.client.get(reverse('store:menu_list'))
        self.assertContains(homepage_response, reverse('store:kitchen_dashboard'))
        self.assertEqual(
            self.client.get(reverse('store:kitchen_dashboard')).status_code,
            200,
        )

    def test_customer_sign_in_redirects_to_homepage_without_staff_link(self):
        response = self.client.post(
            reverse('login'),
            {
                'username': 'customer',
                'password': 'customer-password',
            },
        )

        self.assertRedirects(response, reverse('store:menu_list'))
        homepage_response = self.client.get(reverse('store:menu_list'))
        self.assertEqual(homepage_response.status_code, 200)
        self.assertNotContains(homepage_response, 'Kitchen dashboard')

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


class AccountRegistrationTests(TestCase):
    def test_customer_can_register_and_is_always_a_customer(self):
        response = self.client.post(
            reverse('register'),
            {
                'username': 'new-customer',
                'email': 'customer@example.com',
                'phone_number': '1234567890',
                'password1': 'Secure-test-pass-934!',
                'password2': 'Secure-test-pass-934!',
                'role': 'ADMIN',
            },
        )

        self.assertRedirects(response, reverse('store:menu_list'))
        user = get_user_model().objects.get(username='new-customer')
        self.assertEqual(user.role, 'CUSTOMER')
        self.assertTrue(user.is_authenticated)
        self.assertContains(
            self.client.get(reverse('store:menu_list')),
            'Sign out',
        )

    def test_admin_can_create_another_admin_account(self):
        admin_user = get_user_model().objects.create_user(
            username='admin',
            password='admin-password',
            role='ADMIN',
        )
        self.client.force_login(admin_user)

        response = self.client.post(
            reverse('staff_register'),
            {
                'username': 'second-admin',
                'email': 'second-admin@example.com',
                'phone_number': '',
                'role': 'ADMIN',
                'password1': 'Secure-test-pass-934!',
                'password2': 'Secure-test-pass-934!',
            },
        )

        self.assertRedirects(response, reverse('staff_register'))
        new_admin = get_user_model().objects.get(username='second-admin')
        self.assertEqual(new_admin.role, 'ADMIN')
        self.assertTrue(new_admin.check_password('Secure-test-pass-934!'))

    def test_non_admin_cannot_create_staff_or_admin_accounts(self):
        kitchen_user = get_user_model().objects.create_user(
            username='kitchen',
            password='kitchen-password',
            role='KITCHEN',
        )
        self.client.force_login(kitchen_user)

        response = self.client.get(reverse('staff_register'))

        self.assertEqual(response.status_code, 403)
        self.assertFalse(get_user_model().objects.filter(role='ADMIN').exists())

    def test_login_page_offers_customer_registration(self):
        response = self.client.get(reverse('login'))

        self.assertContains(response, reverse('register'))
        self.assertContains(response, 'Create an account')


class AccountAddressTests(TestCase):
    def setUp(self):
        self.customer = get_user_model().objects.create_user(
            username='customer',
            password='customer-password',
        )

    def test_customer_can_add_address_and_it_becomes_default(self):
        self.client.force_login(self.customer)

        response = self.client.post(
            reverse('address_list'),
            {
                'address_line': '12 Market Road',
                'city': 'Lagos',
                'latitude': '6.5244',
                'longitude': '3.3792',
            },
        )

        self.assertRedirects(response, reverse('address_list'))
        address = self.customer.addresses.get()
        self.assertTrue(address.is_default)
        self.assertEqual(address.address_line, '12 Market Road')
        self.assertEqual(address.latitude, 6.5244)

    def test_address_coordinates_must_be_provided_together(self):
        self.client.force_login(self.customer)

        response = self.client.post(
            reverse('address_list'),
            {
                'address_line': '12 Market Road',
                'city': 'Lagos',
                'latitude': '6.5244',
                'longitude': '',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Enter both coordinates, or leave both blank.')
        self.assertFalse(self.customer.addresses.exists())

    def test_address_page_requires_login(self):
        response = self.client.get(reverse('address_list'))

        self.assertRedirects(
            response,
            f'{reverse("login")}?next={reverse("address_list")}',
        )


class MenuAdminAccessTests(TestCase):
    def setUp(self):
        self.kitchen_user = get_user_model().objects.create_user(
            username='kitchen-admin',
            password='kitchen-password',
            role='KITCHEN',
            is_staff=True,
        )
        self.category = Category.objects.create(name='Mains', slug='mains')

    def test_kitchen_staff_can_manage_menu_in_django_admin(self):
        self.client.force_login(self.kitchen_user)

        self.assertEqual(self.client.get(reverse('admin:index')).status_code, 200)
        self.assertEqual(
            self.client.get(reverse('admin:store_category_changelist')).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(reverse('admin:store_category_add')).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(reverse('admin:store_menuitem_changelist')).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(reverse('admin:store_menuitem_add')).status_code,
            200,
        )

    def test_kitchen_staff_can_add_food_with_its_price(self):
        self.client.force_login(self.kitchen_user)

        response = self.client.post(
            reverse('admin:store_menuitem_add'),
            {
                'category': self.category.id,
                'name': 'Grilled chicken',
                'description': 'Freshly grilled.',
                'price': '4200.00',
                'is_available': 'on',
                '_save': 'Save',
            },
        )

        self.assertRedirects(response, reverse('admin:store_menuitem_changelist'))
        menu_item = MenuItem.objects.get(name='Grilled chicken')
        self.assertEqual(menu_item.price, Decimal('4200.00'))
        self.assertEqual(menu_item.category, self.category)

    def test_kitchen_staff_cannot_access_orders_or_delete_menu(self):
        self.client.force_login(self.kitchen_user)

        self.assertEqual(
            self.client.get(reverse('admin:store_order_changelist')).status_code,
            403,
        )
        self.assertEqual(
            self.client.get(
                reverse('admin:store_menuitem_delete', args=[1])
            ).status_code,
            403,
        )

    def test_new_kitchen_and_admin_accounts_get_django_admin_access(self):
        admin_user = get_user_model().objects.create_user(
            username='admin',
            password='admin-password',
            role='ADMIN',
        )
        self.client.force_login(admin_user)

        response = self.client.post(
            reverse('staff_register'),
            {
                'username': 'new-kitchen',
                'email': 'new-kitchen@example.com',
                'role': 'KITCHEN',
                'password1': 'Secure-test-pass-934!',
                'password2': 'Secure-test-pass-934!',
            },
        )

        self.assertRedirects(response, reverse('staff_register'))
        kitchen_user = get_user_model().objects.get(username='new-kitchen')
        self.assertTrue(kitchen_user.is_staff)
        self.assertEqual(kitchen_user.role, 'KITCHEN')


class StaffMenuManagerTests(TestCase):
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

    def test_menu_manager_is_staff_only(self):
        response = self.client.get(reverse('store:menu_manage'))
        self.assertRedirects(
            response,
            f'{reverse("login")}?next={reverse("store:menu_manage")}',
        )

        self.client.force_login(self.customer)
        response = self.client.get(reverse('store:menu_manage'))
        self.assertEqual(response.status_code, 403)

    def test_kitchen_staff_can_add_category_and_dish(self):
        self.client.force_login(self.kitchen_user)

        category_response = self.client.post(
            reverse('store:menu_manage'),
            {'name': 'Fresh Drinks', 'display_order': '2', 'form_type': 'category'},
        )
        self.assertRedirects(category_response, reverse('store:menu_manage'))
        category = Category.objects.get(name='Fresh Drinks')
        self.assertEqual(category.slug, 'fresh-drinks')

        add_item_url = reverse('store:menu_item_add')
        self.assertEqual(self.client.get(add_item_url).status_code, 200)
        item_response = self.client.post(
            add_item_url,
            {
                'name': 'Mango juice',
                'category': category.id,
                'description': 'Fresh mango juice.',
                'price': '1500.00',
                'is_available': 'on',
            },
        )
        self.assertRedirects(item_response, reverse('store:menu_manage'))

        item = MenuItem.objects.get(name='Mango juice')
        self.assertEqual(item.category, category)
        self.assertEqual(item.price, Decimal('1500.00'))
        self.assertTrue(item.is_available)

        manager_response = self.client.get(reverse('store:menu_manage'))
        self.assertContains(manager_response, 'Mango juice')
        self.assertContains(manager_response, '₦1500.00')

    def test_kitchen_staff_can_edit_price_and_availability(self):
        item = MenuItem.objects.create(
            category=self.category,
            name='Jollof rice',
            price='2500.00',
        )
        self.client.force_login(self.kitchen_user)

        response = self.client.post(
            reverse('store:menu_item_edit', args=[item.id]),
            {
                'name': item.name,
                'category': self.category.id,
                'description': 'Smoky rice.',
                'price': '2800.00',
            },
        )

        self.assertRedirects(response, reverse('store:menu_manage'))
        item.refresh_from_db()
        self.assertEqual(item.price, Decimal('2800.00'))
        self.assertFalse(item.is_available)

    def test_menu_item_price_must_be_greater_than_zero(self):
        self.client.force_login(self.kitchen_user)

        response = self.client.post(
            reverse('store:menu_item_add'),
            {
                'name': 'Free dish',
                'category': self.category.id,
                'description': '',
                'price': '0.00',
                'is_available': 'on',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Enter a price greater than zero.')
        self.assertFalse(MenuItem.objects.filter(name='Free dish').exists())


class CartAndCheckoutTests(TestCase):
    def setUp(self):
        self.customer = get_user_model().objects.create_user(
            username='customer',
            password='customer-password',
        )
        self.category = Category.objects.create(name='Mains', slug='mains')
        self.item = MenuItem.objects.create(
            category=self.category,
            name='Jollof rice',
            price=Decimal('2500.00'),
        )
        self.client.force_login(self.customer)

    def test_cart_uses_current_menu_price(self):
        self.client.post(reverse('store:cart_add', args=[self.item.id]), {'quantity': '2'})
        self.item.price = Decimal('2800.00')
        self.item.save(update_fields=['price'])

        response = self.client.get(reverse('store:cart_detail'))

        self.assertContains(response, '₦2800.00')
        self.assertContains(response, '₦5600.00')
        self.assertEqual(
            self.client.session['cart'][str(self.item.id)]['price'],
            '2800.00',
        )

    def test_removed_menu_item_is_pruned_from_cart(self):
        self.client.post(reverse('store:cart_add', args=[self.item.id]), {'quantity': '1'})
        self.item.delete()

        response = self.client.get(reverse('store:cart_detail'))

        self.assertContains(response, 'Your cart is waiting for something delicious.')
        self.assertEqual(self.client.session.get('cart', {}), {})

    def test_customer_can_update_and_remove_cart_items(self):
        self.client.post(reverse('store:cart_add', args=[self.item.id]), {'quantity': '1'})
        update_response = self.client.post(
            reverse('store:cart_update', args=[self.item.id]),
            {'quantity': '3'},
        )
        self.assertRedirects(update_response, reverse('store:cart_detail'))
        self.assertEqual(self.client.session['cart'][str(self.item.id)]['quantity'], 3)

        remove_response = self.client.post(reverse('store:cart_remove', args=[self.item.id]))
        self.assertRedirects(remove_response, reverse('store:cart_detail'))
        self.assertEqual(self.client.session.get('cart', {}), {})

    def test_checkout_defaults_to_pickup_when_store_delivery_is_unconfigured(self):
        self.client.post(reverse('store:cart_add', args=[self.item.id]), {'quantity': '2'})

        response = self.client.get(reverse('store:checkout'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['selected_order_type'], Order.OrderType.PICKUP)
        self.assertContains(response, '₦5000.00')
        self.assertContains(response, 'Delivery is not configured yet.')

    def test_pickup_checkout_uses_current_price_and_creates_order(self):
        self.client.post(reverse('store:cart_add', args=[self.item.id]), {'quantity': '2'})
        self.item.price = Decimal('3000.00')
        self.item.save(update_fields=['price'])

        response = self.client.post(
            reverse('store:checkout'),
            {'order_type': Order.OrderType.PICKUP},
        )

        order = Order.objects.get(customer=self.customer)
        self.assertRedirects(
            response,
            reverse('store:order_success', args=[order.id]),
        )
        self.assertEqual(order.subtotal, Decimal('6000.00'))
        self.assertEqual(order.delivery_fee, Decimal('0.00'))
        self.assertEqual(order.total_amount, Decimal('6000.00'))
        self.assertEqual(order.items.get().unit_price, Decimal('3000.00'))
        self.assertEqual(self.client.session.get('cart', {}), {})

    def test_delivery_checkout_requires_customer_saved_address(self):
        self.client.post(reverse('store:cart_add', args=[self.item.id]), {'quantity': '1'})
        StoreConfiguration.objects.create(
            name='Test branch',
            address='1 Main Street',
            latitude=6.5244,
            longitude=3.3792,
            base_delivery_fee=Decimal('500.00'),
            per_km_rate=Decimal('100.00'),
            max_delivery_radius_km=15,
        )

        response = self.client.post(
            reverse('store:checkout'),
            {'order_type': Order.OrderType.DELIVERY},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Add a delivery address before placing a delivery order.')
        self.assertFalse(Order.objects.filter(customer=self.customer).exists())

    def test_delivery_checkout_previews_and_saves_calculated_fee(self):
        store = StoreConfiguration.objects.create(
            name='Test branch',
            address='1 Main Street',
            latitude=6.5244,
            longitude=3.3792,
            base_delivery_fee=Decimal('500.00'),
            per_km_rate=Decimal('100.00'),
            max_delivery_radius_km=15,
        )
        address = self.customer.addresses.create(
            address_line='2 Market Road',
            city='Lagos',
            latitude=6.5244,
            longitude=3.3792,
            is_default=True,
        )
        self.client.post(reverse('store:cart_add', args=[self.item.id]), {'quantity': '1'})

        preview = self.client.get(reverse('store:checkout'))
        self.assertEqual(preview.context['delivery_fee'], Decimal('500.00'))
        self.assertContains(preview, '₦500.00')
        self.assertContains(preview, '₦3000.00')

        response = self.client.post(
            reverse('store:checkout'),
            {
                'order_type': Order.OrderType.DELIVERY,
                'address_id': str(address.id),
            },
        )

        order = Order.objects.get(customer=self.customer)
        expected_fee, _, is_valid = store.calculate_delivery_fee(
            address.latitude,
            address.longitude,
        )
        self.assertTrue(is_valid)
        self.assertEqual(order.delivery_fee, Decimal(str(expected_fee)))
        self.assertEqual(order.delivery_address, address)
        self.assertEqual(order.total_amount, Decimal('3000.00'))
        self.assertRedirects(response, reverse('store:order_success', args=[order.id]))

    def test_delivery_checkout_rejects_addresses_outside_delivery_radius(self):
        StoreConfiguration.objects.create(
            name='Test branch',
            address='1 Main Street',
            latitude=6.5244,
            longitude=3.3792,
            base_delivery_fee=Decimal('500.00'),
            per_km_rate=Decimal('100.00'),
            max_delivery_radius_km=15,
        )
        address = self.customer.addresses.create(
            address_line='1 Faraway Road',
            city='New York',
            latitude=40.7128,
            longitude=-74.0060,
            is_default=True,
        )
        self.client.post(reverse('store:cart_add', args=[self.item.id]), {'quantity': '1'})

        response = self.client.post(
            reverse('store:checkout'),
            {
                'order_type': Order.OrderType.DELIVERY,
                'address_id': str(address.id),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Selected address is out of delivery range.')
        self.assertFalse(Order.objects.filter(customer=self.customer).exists())
