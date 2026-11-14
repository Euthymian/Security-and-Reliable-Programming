from contextlib import closing
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from unittest.mock import Mock

import pytest

from cart import ShoppingCart
from checkout import CheckoutService
from models import Product
from repository import StoreRepository
from setup_db import SCHEMA


@pytest.fixture
def cart():
    repository = Mock()
    repository.get_product.return_value = Product('USB-01', 'USB cable', 9.99, 50)
    return ShoppingCart('student', repository)


@pytest.fixture
def shop():
    base = Path(__file__).resolve().parents[1] / '.test-tmp'
    base.mkdir(exist_ok=True)
    with TemporaryDirectory(dir=base) as directory:
        database = str(Path(directory) / 'shop.db')
        with closing(sqlite3.connect(database)) as connection, connection:
            connection.executescript(SCHEMA)
            connection.executemany('INSERT INTO products VALUES (?, ?, ?, ?)', [
                ('USB-01', 'USB cable', 9.99, 50),
                ('MOU-01', 'Mouse', 29.95, 20),
                ('LAP-01', 'Laptop', 999.99, 5),
            ])
        repository = StoreRepository(database)
        cart = ShoppingCart('student', repository)
        gateway = Mock()
        gateway.charge.return_value = {'approved': True, 'transaction_id': 'TEST-001'}
        yield repository, cart, gateway, CheckoutService(repository, gateway)


def test_add_rejects_invalid_quantities_without_changing_cart(cart):
    for quantity in (0, -1, 1.5, '2', True, None):
        assert cart.add_item('USB-01', quantity) is False
        assert cart.lines == []
    cart.repository.get_product.assert_not_called()


def test_duplicate_add_merges_items_and_enforces_combined_stock(cart):
    assert cart.add_item('USB-01', 30)
    assert cart.add_item('USB-01', 20)
    assert len(cart.lines) == 1
    assert cart.lines[0].quantity == 50
    assert cart.add_item('USB-01', 1) is False
    assert cart.lines[0].quantity == 50


def test_discount_recalculates_after_adding_and_removing_items(cart):
    cart.add_item('USB-01', 1)
    cart.apply_discount('WELCOME10')
    assert cart.total() == 8.99
    cart.add_item('USB-01', 1)
    assert cart.total() == 17.98
    assert cart.remove_item('USB-01', 1)
    assert cart.total() == 8.99
    assert cart.remove_item('USB-01')
    assert cart.total() == 0


def test_coupon_reapplication_does_not_stack_and_new_coupon_replaces_old(cart):
    cart.add_item('USB-01', 2)
    cart.apply_discount('WELCOME10')
    cart.apply_discount('WELCOME10')
    assert cart.total() == 17.98
    assert cart.apply_discount('STUDENT20')
    assert cart.total() == 15.98
    assert cart.apply_discount('INVALID') is False
    assert cart.total() == 15.98


def test_money_calculations_round_half_up_to_cents(cart):
    cart.repository.get_product.return_value = Product('MOU-01', 'Mouse', 29.95, 20)
    cart.add_item('MOU-01', 1)
    assert cart.subtotal() == 29.95
    cart.apply_discount('WELCOME10')
    assert cart.total() == 26.96  # 29.95 * 0.90 = 26.955


def test_fixed_discount_cannot_make_total_negative(cart):
    cart.add_item('USB-01', 1)
    cart.apply_discount('SAVE15')
    assert cart.subtotal() == 9.99
    assert cart.total() == 0


def test_empty_checkout_does_not_charge_or_create_order(shop):
    repository, cart, gateway, service = shop
    result = service.checkout(cart, 'TEST_TOKEN', 'empty')
    assert result.status == 'empty'
    assert result.order_id is None
    assert result.total == 0
    gateway.charge.assert_not_called()
    assert repository.list_orders('student') == []


def test_checkout_rechecks_changed_stock_before_charging(shop):
    repository, cart, gateway, service = shop
    cart.add_item('LAP-01', 5)
    repository.update_stock('LAP-01', 1)
    result = service.checkout(cart, 'TEST_TOKEN', 'stock')
    assert result.status == 'out_of_stock'
    gateway.charge.assert_not_called()
    assert repository.get_product('LAP-01').stock == 4
    assert cart.lines[0].quantity == 5
    assert repository.list_orders('student') == []


def test_declined_payment_preserves_inventory_and_cart(shop):
    repository, cart, gateway, service = shop
    cart.add_item('USB-01', 2)
    cart.apply_discount('WELCOME10')
    cart.save()
    gateway.charge.return_value = {'approved': False}
    result = service.checkout(cart, 'TEST_TOKEN', 'declined')
    assert result.status == 'declined'
    gateway.charge.assert_called_once_with(17.98, 'TEST_TOKEN')
    assert repository.get_product('USB-01').stock == 50
    assert cart.lines[0].quantity == 2
    assert cart.discount_code == 'WELCOME10'
    assert repository.get_saved_cart('student') == [('USB-01', 2)]
    assert repository.list_orders('student')[0][3] == 'declined'


def test_unexpected_payment_error_preserves_state_and_is_not_retried(shop):
    repository, cart, gateway, service = shop
    cart.add_item('USB-01', 1)
    cart.save()
    gateway.charge.side_effect = RuntimeError('Simulated gateway failure')
    result = service.checkout(cart, 'TEST_TOKEN', 'error')
    assert result.status == 'payment_error'
    assert service.checkout(cart, 'TEST_TOKEN', 'error') == result
    gateway.charge.assert_called_once_with(9.99, 'TEST_TOKEN')
    assert repository.get_product('USB-01').stock == 50
    assert cart.lines[0].quantity == 1
    assert repository.get_saved_cart('student') == [('USB-01', 1)]
    assert len(repository.list_orders('student')) == 1


def test_database_failure_rolls_back_all_local_checkout_changes(shop):
    repository, cart, gateway, service = shop
    cart.add_item('USB-01', 1)
    cart.add_item('MOU-01', 1)
    cart.save()
    with closing(repository.connect()) as connection, connection:
        connection.execute("CREATE TRIGGER reject_second_stock BEFORE UPDATE ON products "
                           "WHEN OLD.sku = 'MOU-01' BEGIN "
                           "SELECT RAISE(ABORT, 'simulated database failure'); END")
    with pytest.raises(sqlite3.IntegrityError, match='simulated database failure'):
        service.checkout(cart, 'TEST_TOKEN', 'rollback')
    gateway.charge.assert_called_once()
    assert repository.get_product('USB-01').stock == 50
    assert repository.get_product('MOU-01').stock == 20
    assert repository.list_orders('student') == []
    assert len(repository.get_saved_cart('student')) == 2
    assert len(cart.lines) == 2


def test_successful_checkout_is_committed_once_for_repeated_request(shop):
    repository, cart, gateway, service = shop
    cart.add_item('USB-01', 2)
    cart.apply_discount('WELCOME10')
    cart.save()
    result = service.checkout(cart, 'TEST_TOKEN', 'same')
    assert result.status == 'paid'
    assert result.order_id is not None
    assert result.total == 17.98
    assert service.checkout(cart, 'TEST_TOKEN', 'same') == result
    gateway.charge.assert_called_once_with(17.98, 'TEST_TOKEN')
    assert repository.get_product('USB-01').stock == 48
    assert len(repository.list_orders('student')) == 1
    assert repository.get_saved_cart('student') == []
    assert cart.lines == []
    assert cart.discount_code is None
