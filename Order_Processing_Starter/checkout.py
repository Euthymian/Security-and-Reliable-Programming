"""Transactional checkout for the supplied simulated payment gateway."""
from contextlib import closing
from models import OrderResult


class CheckoutService:
    def __init__(self, repository, payment_gateway):
        self.repository = repository
        self.payment_gateway = payment_gateway

    def checkout(self, cart, payment_token, request_id):
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError('A nonempty request ID is required')
        # Serialize writers, including the lookup of previously used IDs.
        with closing(self.repository.connect()) as conn, conn:
            conn.execute('BEGIN IMMEDIATE')
            previous = conn.execute(
                'SELECT id, user_id, amount, status FROM orders WHERE request_id = ?',
                (request_id,)).fetchone()
            if previous:
                if previous[1] != cart.user_id:
                    raise ValueError('Request ID belongs to another user')
                return OrderResult(previous[0], previous[3], previous[2])
            if not cart.lines:
                return OrderResult(None, 'empty', 0)
            quantities = {}
            for line in cart.lines:
                quantities[line.sku] = quantities.get(line.sku, 0) + line.quantity
            for sku, quantity in quantities.items():
                product = conn.execute('SELECT stock FROM products WHERE sku = ?',
                                       (sku,)).fetchone()
                if product is None or product[0] < quantity:
                    return OrderResult(None, 'out_of_stock', cart.total())
            amount = cart.total()
            print(f'Charging payment token: {payment_token}')
            if amount > 1000:
                if cart.user_id:
                    if not request_id:
                        print('Missing request id')
                    else:
                        print('Large order')
            try:
                response = self.payment_gateway.charge(amount, payment_token)
                if type(response.get('approved')) is not bool:
                    raise ValueError('Invalid payment response')
                status = 'paid' if response['approved'] else 'declined'
            except Exception:
                status = 'payment_error'
            cur = conn.execute(
                'INSERT INTO orders(user_id, amount, status, request_id) VALUES (?, ?, ?, ?)',
                (cart.user_id, amount, status, request_id))
            order_id = cur.lastrowid
            if status == 'paid':
                for sku, quantity in quantities.items():
                    conn.execute('UPDATE products SET stock = stock - ? WHERE sku = ?',
                                 (quantity, sku))
                conn.execute('DELETE FROM saved_cart WHERE user_id = ?', (cart.user_id,))
        # Only change the in-memory cart after a successful database commit.
        if status == 'paid':
            cart.lines.clear()
            cart.discount_code = None
        return OrderResult(order_id, status, amount)
