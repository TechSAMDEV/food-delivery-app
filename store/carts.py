from decimal import Decimal
from .models import MenuItem

class Cart:
    def __init__(self, request):
        self.session = request.session
        cart = self.session.get('cart')
        if not cart:
            cart = self.session['cart'] = {}
        self.cart = cart

    def add(self, menu_item, quantity=1):
        item_id = str(menu_item.id)
        if item_id not in self.cart:
            self.cart[item_id] = {'quantity': 0, 'price': str(menu_item.price)}
        
        self.cart[item_id]['quantity'] += int(quantity)
        self.save()

    def remove(self, menu_item):
        item_id = str(menu_item.id)
        if item_id in self.cart:
            del self.cart[item_id]
            self.save()

    def save(self):
        self.session.modified = True

    def __iter__(self):
        item_ids = self.cart.keys()
        menu_items = MenuItem.objects.filter(id__in=item_ids)
        cart = self.cart.copy()

        for item in menu_items:
            cart[str(item.id)]['menu_item'] = item

        for item in cart.values():
            item['total_price'] = Decimal(item['price']) * item['quantity']
            yield item

    def __len__(self):
        return len(self.cart)

    def get_total_price(self):
        return sum(Decimal(item['price']) * item['quantity'] for item in self.cart.values())

    def clear(self):
        del self.session['cart']
        self.save()