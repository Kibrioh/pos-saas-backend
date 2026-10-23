from collections import OrderedDict
from decimal import Decimal, InvalidOperation
import hashlib
import json

from flask import g
from sqlalchemy import text

from extensions import db
from models import Product, Sale, SaleItem, User
from services.audit_service import add_audit_event
from services.stock_service import ServiceError, deduct_stock

BASE_CURRENCY_QUANTUM = Decimal("0.0001")
KSH_ROUNDING_TOLERANCE = Decimal("0.0039")


def _clean_items(raw_items):
    """Validate the request items and merge duplicates: product_id -> total quantity."""
    if not isinstance(raw_items, list) or not raw_items:
        raise ServiceError("A sale needs at least one item.")

    wanted = OrderedDict()
    for entry in raw_items:
        if not isinstance(entry, dict):
            raise ServiceError("Each item needs a product_id and a quantity.")
        product_id = entry.get("product_id")
        quantity = entry.get("quantity")
        for value in (product_id, quantity):
            if not isinstance(value, int) or isinstance(value, bool):
                raise ServiceError("product_id and quantity must be integers.")
        if quantity <= 0:
            raise ServiceError("Quantity must be greater than zero.")
        wanted[product_id] = wanted.get(product_id, 0) + quantity
    return wanted


def _cash_tender_and_change(amount_tendered, total):
    if amount_tendered is None:
        return total, Decimal("0.0000")
    try:
        tendered = Decimal(str(amount_tendered))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ServiceError("Cash received must be a valid amount") from error
    if not tendered.is_finite() or tendered < 0:
        raise ServiceError("Cash received must be a non-negative amount")

    tendered = tendered.quantize(BASE_CURRENCY_QUANTUM)
    # The cashier enters whole KSh while stored prices are converted to the
    # base currency. Treat a sub-half-shilling rounding difference as exact.
    if tendered < total and (total - tendered) <= KSH_ROUNDING_TOLERANCE:
        tendered = total
    if tendered < total:
        raise ServiceError("Cash received is less than the sale total")
    return tendered, (tendered - total).quantize(BASE_CURRENCY_QUANTUM)


def create_sale(user_id, raw_items, payment_method="cash", shift_id=None,
                amount_tendered=None, idempotency_key=None):
    wanted = _clean_items(raw_items)
    request_hash = hashlib.sha256(json.dumps({
        "items": sorted(wanted.items()),
        "payment_method": payment_method,
        "amount_tendered": str(amount_tendered) if amount_tendered is not None else None,
    }, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()

    try:
        if idempotency_key and db.session.get_bind().dialect.name == "postgresql":
            lock_key = f"sale:{g.get('tenant_id')}:{g.get('branch_id')}:{idempotency_key}"
            db.session.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
                {"lock_key": lock_key},
            )

        if idempotency_key:
            existing_sale = Sale.query.filter_by(idempotency_key=idempotency_key).first()
            if existing_sale is not None:
                if existing_sale.user_id != user_id:
                    raise ServiceError("This checkout retry key is already in use.", 409)
                if existing_sale.idempotency_hash != request_hash:
                    raise ServiceError(
                        "This checkout retry key was already used for different sale details.",
                        409,
                    )
                return existing_sale

        user = db.session.get(User, user_id)
        if user is None:
            raise ServiceError("Cashier not found.", 401)

        # Lock these product rows until we commit or roll back, so two cashiers
        # can't both sell the last unit. Sorting by id avoids deadlocks.
        products = (
            Product.query
            .filter(Product.id.in_(list(wanted)))
            .filter(Product.is_active.is_(True))
            .order_by(Product.id)
            .populate_existing()
            .with_for_update()
            .all()
        )
        by_id = {p.id: p for p in products}

        # Check everything first, so the cashier sees all problems at once.
        problems = []
        for product_id, qty in wanted.items():
            product = by_id.get(product_id)
            if product is None:
                problems.append(f"Product {product_id} not found.")
            elif product.stock_quantity < qty:
                problems.append(
                    f"Not enough stock for '{product.title}': "
                    f"requested {qty}, available {product.stock_quantity}."
                )
        if problems:
            raise ServiceError(" ".join(problems), 409)

        total = sum(
            (
                (by_id[product_id].price * quantity).quantize(BASE_CURRENCY_QUANTUM)
                for product_id, quantity in wanted.items()
            ),
            Decimal("0.0000"),
        )
        if payment_method == "cash":
            tendered, change_given = _cash_tender_and_change(amount_tendered, total)
        else:
            tendered = None
            change_given = Decimal("0.0000")

        sale = Sale(
            user_id=user.id,
            shift_id=shift_id,
            payment_method=payment_method,
            amount_tendered=tendered,
            change_given=change_given,
            idempotency_key=idempotency_key,
            idempotency_hash=request_hash if idempotency_key else None,
        )
        db.session.add(sale)
        db.session.flush()  # gets sale.id without committing yet

        for product_id, qty in wanted.items():
            product = by_id[product_id]
            unit_price = product.price  # always from the database, never the client
            subtotal = (unit_price * qty).quantize(BASE_CURRENCY_QUANTUM)

            db.session.add(SaleItem(
                sale_id=sale.id, product_id=product.id,
                quantity=qty, unit_price=unit_price,
                unit_cost=product.unit_cost,
                subtotal=subtotal,
            ))
            # The team's helper lowers stock and records the stock movement.
            # It does not commit; we do that once below.
            deduct_stock(product.id, qty, user.id, sale_id=sale.id)

        sale.total_amount = total
        add_audit_event(user.id, "sale.completed", "sale", sale.id, {
            "total_amount": str(total),
            "payment_method": payment_method,
            "amount_tendered": str(tendered) if tendered is not None else None,
            "change_given": str(change_given),
            "item_count": len(wanted),
            "shift_id": shift_id,
        })
        db.session.commit()  # sale, items, stock and audit rows all succeed together
        return sale

    except Exception:
        db.session.rollback()  # any failure undoes everything and releases the locks
        raise
