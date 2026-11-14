"""Shopping cart validation and monetary calculations."""
from decimal import Decimal, ROUND_HALF_UP
from models import CartLine


def valid_quantity(quantity):
    return type(quantity) is int and quantity > 0


def money(amount):
    return Decimal(str(amount)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


class ShoppingCart:
    def __init__(self, user_id, repository):
        self.user_id = user_id
        self.repository = repository
        self.lines = []
        self.discount_code = None

    def add_item(self, sku, quantity):
        if not valid_quantity(quantity):
            return False
        product = self.repository.get_product(sku)
        if not product:
            return False
        existing = next((x for x in self.lines if x.sku == sku), None)
        combined = quantity + (existing.quantity if existing else 0)
        if combined > product.stock:
            return False
        if existing:
            existing.quantity = combined
        else:
            self.lines.append(CartLine(sku, product.name, product.price, quantity))
        return True

    def remove_item(self, sku, quantity=None):
        for line in self.lines:
            if line.sku == sku:
                if quantity is None or quantity >= line.quantity:
                    self.lines.remove(line)
                else:
                    line.quantity -= quantity
                return True
        print('Item not found')
        return False

    def subtotal(self):
        return float(sum((money(line.unit_price) * line.quantity
                          for line in self.lines), Decimal('0.00')))

    def total(self):
        amount = money(self.subtotal())
        if self.discount_code == 'WELCOME10':
            amount *= Decimal('0.90')
        elif self.discount_code == 'STUDENT20':
            amount *= Decimal('0.80')
        elif self.discount_code == 'SAVE15':
            amount -= Decimal('15.00')
        return float(money(max(Decimal('0.00'), amount)))

    def apply_discount(self, code):
        if code not in ('WELCOME10', 'STUDENT20', 'SAVE15', 'FREESHIP'):
            return False
        self.discount_code = code
        return True

    def load(self):
        for sku, quantity in self.repository.get_saved_cart(self.user_id):
            self.add_item(sku, quantity)

    def save(self):
        self.repository.save_cart(self.user_id, self.lines)
