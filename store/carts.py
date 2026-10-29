from decimal import Decimal

from .models import MenuItem


class Cart:
    def __init__(self, request):
        self.session = request.session
        cart = self.session.get('cart')
        if not isinstance(cart, dict):
            cart = {}
            self.session['cart'] = cart
        self.cart = cart

    def add(self, menu_item, quantity=1):
        if quantity < 1:
            raise ValueError('Cart quantity must be greater than zero.')

        item_id = str(menu_item.id)
        current_item = self.cart.get(item_id, {})
        current_quantity = current_item.get('quantity', 0) if isinstance(current_item, dict) else 0
        try:
            current_quantity = max(int(current_quantity), 0)
        except (TypeError, ValueError):
            current_quantity = 0

        self.cart[item_id] = {
            'quantity': current_quantity + int(quantity),
            'price': str(menu_item.price),
        }
        self.save()

    def update(self, menu_item, quantity):
        if quantity < 1:
            raise ValueError('Cart quantity must be greater than zero.')

        item_id = str(menu_item.id)
        self.cart[item_id] = {
            'quantity': int(quantity),
            'price': str(menu_item.price),
        }
        self.save()

    def remove(self, menu_item):
        item_id = str(menu_item.id if isinstance(menu_item, MenuItem) else menu_item)
        if item_id in self.cart:
            del self.cart[item_id]
            self.save()

    def save(self):
        self.session.modified = True

    def __iter__(self):
        item_ids = [
            str(item_id)
            for item_id in self.cart
            if str(item_id).isdigit()
        ]
        menu_items = {
            str(item.id): item
            for item in MenuItem.objects.filter(id__in=item_ids)
        }
        valid_items = {}
        changed = False

        for item_id, entry in self.cart.items():
            item_key = str(item_id)
            menu_item = menu_items.get(item_key)
            if not menu_item or not isinstance(entry, dict):
                changed = True
                continue

            try:
                quantity = int(entry.get('quantity', 0))
            except (TypeError, ValueError):
                changed = True
                continue
            if quantity < 1:
                changed = True
                continue

            current_price = str(menu_item.price)
            if entry.get('price') != current_price or entry.get('quantity') != quantity:
                changed = True
            valid_items[item_key] = {
                'quantity': quantity,
                'price': current_price,
            }
            if item_key != item_id:
                changed = True

        if changed or len(valid_items) != len(self.cart):
            self.cart.clear()
            self.cart.update(valid_items)
            self.save()

        for item_id, entry in self.cart.items():
            menu_item = menu_items[item_id]
            yield {
                'menu_item': menu_item,
                'quantity': entry['quantity'],
                'price': Decimal(entry['price']),
                'total_price': Decimal(entry['price']) * entry['quantity'],
            }

    def __len__(self):
        return sum(1 for _ in self)

    def get_total_price(self):
        return sum((item['total_price'] for item in self), Decimal('0.00'))

    def clear(self):
        self.session.pop('cart', None)
        self.save()