# Security and Reliable Programming

## Task 1 Find and correct defects

Implemented 10 selected defect fixes in `Order_Processing_Starter`. The supplied `payments.py` and simulated `FakePaymentGateway` remain unchanged.

## Defects and fixes

All paths below are relative to `Order_Processing_Starter/`.

| # | Location | Problem | Fix |
| --- | --- | --- | --- |
| 1 | `cart.py`, `add_item` | Zero, negative, fractional, boolean, or nonnumeric quantities could create invalid cart lines or cause errors. | Accept only positive integers, excluding booleans. Invalid additions return `False` without changing the cart. |
| 2 | `cart.py`, `add_item` | Adding the same product repeatedly could exceed stock because only the incoming quantity was checked. | Check the existing quantity plus the incoming quantity against available stock before merging. |
| 3 | `cart.py`, `total` | Editing the cart after applying a discount left the cached total unchanged. | Calculate the discounted total from the current subtotal each time. |
| 4 | `cart.py`, `apply_discount` | Reapplying or changing a coupon compounded discounts on an already discounted amount. | Keep one active coupon and apply it to the original current subtotal. A new valid coupon replaces the old one. |
| 5 | `cart.py`, `subtotal` and `total` | Floating-point arithmetic and unrounded discounts produced fractions of a cent. | Calculate using `Decimal` and round to two decimal places using `ROUND_HALF_UP`. Return floats at the existing API boundary. |
| 6 | `cart.py`, `total` | `SAVE15` could make totals below zero when the subtotal was less than $15. | Set the minimum payable amount to zero. |
| 7 | `checkout.py`, stock check | Stock could change after a product was added to the cart, causing checkout to sell unavailable inventory. | Recheck current stock inside a SQLite write transaction before charging. Return `out_of_stock` without changing the cart or calling the gateway. |
| 8 | `checkout.py`, payment handling | Declined payments and payment exceptions still consumed stock and cleared the cart. | Record `declined` or `payment_error` while preserving inventory and cart state. Only approved payments consume stock and clear the cart. Malformed approval responses are treated as errors. |
| 9 | `checkout.py`, database updates | Orders, individual stock deductions, and saved-cart removal committed separately, allowing partial updates. | Commit all checkout database changes in one transaction. Roll back on database failure and clear the in-memory cart only after commit succeeds. |
| 10 | `checkout.py`, request handling | Retrying a request could charge again and create duplicate orders. | Require a nonblank request ID. Look up a recorded result before checking cart emptiness and return it without charging again. Serialize checkout writers with `BEGIN IMMEDIATE`; reject another user's reuse of the ID. |

## Assumptions

- Additions require positive whole-number quantities. Cart methods maintain one line per SKU and retain the price captured when the product was added.
- Currency has two decimal places. Unit prices and discounted totals use half-up rounding.
- Only one coupon applies: `WELCOME10` gives 10% off, `STUDENT20` gives 20% off, and `SAVE15` subtracts $15 with a zero minimum. `FREESHIP` changes no amount because this application has no shipping charge. Invalid codes leave the current coupon unchanged.
- Editing a cart retains its active coupon and recalculates the total.
- Successful checkout clears both saved and current cart contents and resets the coupon. Failed payments preserve them.

## Task 2 Unit tests

Exactly **12 unit tests** are in `Order_Processing_Starter/tests/test_reliability.py`, replacing the two starter smoke tests:

1. Reject invalid addition quantities without changing the cart.
2. Merge duplicate products and enforce combined stock limits.
3. Recalculate discounts after cart additions and removals.
4. Prevent stacked coupons and replace the active coupon correctly.
5. Round monetary calculations half up to cents.
6. Prevent a fixed discount from making the total negative.
7. Reject empty checkout without charging or creating an order.
8. Recheck changed inventory before charging.
9. Preserve inventory and cart state after a declined payment.
10. Handle unexpected payment errors without repeating the charge.
11. Roll back all local checkout changes after a database failure.
12. Commit successful checkout once when a request is repeated.

Run from `Order_Processing_Starter`:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```
<img width="1327" height="117" alt="image" src="https://github.com/user-attachments/assets/742dde52-0fb5-4bae-94f5-65222d5c54e4" />


## Task 3 GitHub Actions
<img width="1251" height="268" alt="image" src="https://github.com/user-attachments/assets/7007962e-f83f-426b-8619-1620bf85b482" />

