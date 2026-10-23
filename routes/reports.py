from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from flask import Blueprint, g, has_request_context, jsonify, request
from sqlalchemy import case, func, or_
from sqlalchemy.orm import joinedload, selectinload

from extensions import db
from models import (
    CashierShift,
    Product,
    PurchaseOrder,
    PurchaseOrderItem,
    Sale,
    SaleItem,
    SaleReturn,
    SaleReturnItem,
    User,
)
from services.shift_service import expected_cash_for_shift
from utils.auth import manager_required

bp = Blueprint("reports", __name__, url_prefix="/api/reports")
BUSINESS_TIMEZONE = ZoneInfo("Africa/Nairobi")
UTC = timezone.utc


def business_timezone():
    timezone_name = (
        g.get("business_timezone", "Africa/Nairobi")
        if has_request_context()
        else "Africa/Nairobi"
    )
    try:
        return ZoneInfo(timezone_name)
    except (KeyError, TypeError, ValueError):
        return BUSINESS_TIMEZONE


def _date_range(start_text, end_text, default_days=None):
    try:
        start_date = date.fromisoformat(start_text) if start_text else None
        end_date = date.fromisoformat(end_text) if end_text else None
    except ValueError:
        return None, None, (
            jsonify(status="error", message="Dates must use YYYY-MM-DD format"),
            400,
        )

    if start_date is None and end_date is None and default_days:
        end_date = datetime.now(business_timezone()).date()
        start_date = end_date - timedelta(days=default_days - 1)
    elif start_date is None and end_date is not None and default_days:
        start_date = end_date - timedelta(days=default_days - 1)
    elif end_date is None and start_date is not None:
        end_date = datetime.now(business_timezone()).date()

    if start_date and end_date and start_date > end_date:
        return None, None, (
            jsonify(status="error", message="start_date cannot be after end_date"),
            400,
        )
    return start_date, end_date, None


def _utc_boundary(day, at_end=False):
    if day is None:
        return None
    if at_end:
        day += timedelta(days=1)
    local_boundary = datetime.combine(day, time.min, tzinfo=business_timezone())
    return local_boundary.astimezone(UTC)


def _period_query(start_date, end_date):
    query = Sale.query
    start_at = _utc_boundary(start_date)
    end_at = _utc_boundary(end_date, at_end=True)
    if start_at is not None:
        query = query.filter(Sale.created_at >= start_at)
    if end_at is not None:
        query = query.filter(Sale.created_at < end_at)
    return query


def filtered_sales_query():
    start_date, end_date, error = _date_range(
        request.args.get("start_date"),
        request.args.get("end_date"),
    )
    if error:
        return None, error
    return _period_query(start_date, end_date), None


def money(value):
    return str(Decimal(str(value)))


def net_revenue_expression():
    refunded = (
        db.session.query(func.coalesce(func.sum(SaleReturn.refund_total), 0))
        .filter(SaleReturn.sale_id == Sale.id)
        .correlate(Sale)
        .scalar_subquery()
    )
    return Sale.total_amount - refunded


def _decimal(value):
    return Decimal(str(value if value is not None else 0))


def _as_utc(value):
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _as_business_time(value):
    return _as_utc(value).astimezone(business_timezone())


def _rate(numerator, denominator):
    if not denominator:
        return None
    return round(float(numerator / denominator * Decimal("100")), 2)


def _blank_amounts():
    return {
        "gross_sales": Decimal("0"),
        "net_sales": Decimal("0"),
        "gross_profit": Decimal("0"),
        "refund_total": Decimal("0"),
        "transaction_count": 0,
        "units_sold": 0,
        "net_units_sold": 0,
        "costed_units": 0,
        "items_without_cost": 0,
    }


def _blank_product(product_id, title, category):
    return {
        "product_id": product_id,
        "product_title": title,
        "category": category,
        "units_sold": 0,
        "units_returned": 0,
        "net_units_sold": 0,
        "gross_revenue": Decimal("0"),
        "net_revenue": Decimal("0"),
        "gross_profit": Decimal("0"),
        "costed_units": 0,
        "items_without_cost": 0,
    }


def _product_for(item):
    product = item.product
    title = product.title if product else f"Product {item.product_id}"
    category = (
        product.category.name
        if product and product.category
        else "Uncategorized"
    )
    return title, category


def _aggregate_sales(sales):
    summary = _blank_amounts()
    by_date = {}
    by_hour = {
        hour: {"hour": hour, "net_sales": Decimal("0"), "transactions": 0}
        for hour in range(24)
    }
    by_weekday = {
        day: {"weekday": day, "net_sales": Decimal("0"), "transactions": 0}
        for day in range(7)
    }
    by_payment = {}
    by_product = {}
    by_category = {}
    by_cashier = {}

    for sale in sales:
        sale_gross = _decimal(sale.total_amount)
        sale_refunds = sum(
            (_decimal(record.refund_total) for record in sale.returns),
            Decimal("0"),
        )
        sale_net = sale_gross - sale_refunds
        summary["gross_sales"] += sale_gross
        summary["net_sales"] += sale_net
        summary["refund_total"] += sale_refunds
        summary["transaction_count"] += 1

        sale_units = 0
        for item in sale.items:
            quantity = int(item.quantity)
            sale_units += quantity
            summary["units_sold"] += quantity
            title, category_name = _product_for(item)
            product_bucket = by_product.setdefault(
                item.product_id,
                _blank_product(item.product_id, title, category_name),
            )
            category_bucket = by_category.setdefault(
                category_name,
                _blank_product(None, category_name, category_name),
            )
            item_revenue = _decimal(item.subtotal)
            product_bucket["units_sold"] += quantity
            product_bucket["gross_revenue"] += item_revenue
            product_bucket["net_revenue"] += item_revenue
            category_bucket["units_sold"] += quantity
            category_bucket["gross_revenue"] += item_revenue
            category_bucket["net_revenue"] += item_revenue

            if item.unit_cost is None:
                summary["items_without_cost"] += quantity
                product_bucket["items_without_cost"] += quantity
                category_bucket["items_without_cost"] += quantity
            else:
                unit_profit = _decimal(item.unit_price) - _decimal(item.unit_cost)
                profit = unit_profit * quantity
                summary["gross_profit"] += profit
                summary["costed_units"] += quantity
                product_bucket["costed_units"] += quantity
                category_bucket["costed_units"] += quantity
                product_bucket["gross_profit"] += profit
                category_bucket["gross_profit"] += profit

        user = sale.user
        if user and user.role == "cashier":
            cashier_bucket = by_cashier.setdefault(user.id, {
                "user_id": user.id,
                "name": user.name,
                "username": user.username,
                "gross_sales": Decimal("0"),
                "net_sales": Decimal("0"),
                "refund_total": Decimal("0"),
                "transaction_count": 0,
                "units_sold": 0,
                "units_returned": 0,
            })
            cashier_bucket["gross_sales"] += sale_gross
            cashier_bucket["net_sales"] += sale_net
            cashier_bucket["refund_total"] += sale_refunds
            cashier_bucket["transaction_count"] += 1
            cashier_bucket["units_sold"] += sale_units

        sale_returned_units = 0
        for return_record in sale.returns:
            for returned_item in return_record.items:
                quantity = int(returned_item.quantity)
                sale_returned_units += quantity
                product_title, category_name = _product_for(returned_item)
                product_bucket = by_product.setdefault(
                    returned_item.product_id,
                    _blank_product(returned_item.product_id, product_title, category_name),
                )
                category_bucket = by_category.setdefault(
                    category_name,
                    _blank_product(None, category_name, category_name),
                )
                returned_revenue = _decimal(returned_item.unit_price) * quantity
                product_bucket["net_revenue"] -= returned_revenue
                category_bucket["net_revenue"] -= returned_revenue
                product_bucket["units_returned"] += quantity
                category_bucket["units_returned"] += quantity

                # A returned sale removes its revenue. Restocked goods restore
                # their recorded cost; non-restocked goods remain a cost.
                if returned_item.unit_cost is not None:
                    product_bucket["gross_profit"] -= returned_revenue
                    category_bucket["gross_profit"] -= returned_revenue
                    summary["gross_profit"] -= returned_revenue
                if returned_item.restock and returned_item.unit_cost is not None:
                    returned_cost = _decimal(returned_item.unit_cost) * quantity
                    product_bucket["gross_profit"] += returned_cost
                    category_bucket["gross_profit"] += returned_cost
                    summary["gross_profit"] += returned_cost

        summary["net_units_sold"] += max(0, sale_units - sale_returned_units)
        if user and user.role == "cashier" and user.id in by_cashier:
            by_cashier[user.id]["units_returned"] += sale_returned_units

        local_time = _as_business_time(sale.created_at)
        date_key = local_time.date().isoformat()
        date_bucket = by_date.setdefault(date_key, {
            "date": date_key,
            "net_sales": Decimal("0"),
            "transactions": 0,
        })
        date_bucket["net_sales"] += sale_net
        date_bucket["transactions"] += 1
        by_hour[local_time.hour]["net_sales"] += sale_net
        by_hour[local_time.hour]["transactions"] += 1
        by_weekday[local_time.weekday()]["net_sales"] += sale_net
        by_weekday[local_time.weekday()]["transactions"] += 1

        payment_bucket = by_payment.setdefault(sale.payment_method, {
            "payment_method": sale.payment_method,
            "net_sales": Decimal("0"),
            "transactions": 0,
        })
        payment_bucket["net_sales"] += sale_net
        payment_bucket["transactions"] += 1

    summary["average_sale"] = (
        summary["net_sales"] / summary["transaction_count"]
        if summary["transaction_count"] else Decimal("0")
    )
    summary["average_items_per_transaction"] = (
        round(summary["net_units_sold"] / summary["transaction_count"], 2)
        if summary["transaction_count"] else 0
    )
    summary["gross_margin_rate"] = (
        _rate(summary["gross_profit"], summary["net_sales"])
        if summary["costed_units"] else None
    )
    summary["cost_coverage_rate"] = _rate(
        Decimal(summary["costed_units"]),
        Decimal(summary["units_sold"]),
    )
    summary["refund_rate"] = _rate(
        summary["refund_total"], summary["gross_sales"]
    )

    products = []
    for bucket in by_product.values():
        bucket["net_units_sold"] = max(
            0, bucket["units_sold"] - bucket["units_returned"]
        )
        bucket["margin_rate"] = (
            _rate(bucket["gross_profit"], bucket["net_revenue"])
            if bucket["costed_units"] else None
        )
        bucket["cost_coverage_rate"] = _rate(
            Decimal(bucket["costed_units"]),
            Decimal(bucket["units_sold"]),
        )
        products.append(bucket)

    categories = []
    for bucket in by_category.values():
        bucket["net_units_sold"] = max(
            0, bucket["units_sold"] - bucket["units_returned"]
        )
        bucket["margin_rate"] = (
            _rate(bucket["gross_profit"], bucket["net_revenue"])
            if bucket["costed_units"] else None
        )
        bucket["cost_coverage_rate"] = _rate(
            Decimal(bucket["costed_units"]),
            Decimal(bucket["units_sold"]),
        )
        categories.append(bucket)

    cashier_rows = list(by_cashier.values())
    for cashier in cashier_rows:
        cashier["average_sale"] = (
            cashier["net_sales"] / cashier["transaction_count"]
            if cashier["transaction_count"] else Decimal("0")
        )
        cashier["refund_rate"] = _rate(
            cashier["refund_total"], cashier["gross_sales"]
        )
        cashier["net_units_sold"] = max(
            0, cashier["units_sold"] - cashier["units_returned"]
        )

    return {
        "summary": summary,
        "daily_sales": sorted(by_date.values(), key=lambda row: row["date"]),
        "hourly_sales": list(by_hour.values()),
        "weekday_sales": list(by_weekday.values()),
        "payment_methods": sorted(
            by_payment.values(), key=lambda row: row["net_sales"], reverse=True
        ),
        "products": products,
        "categories": categories,
        "cashiers": cashier_rows,
    }


def _sales_detail_options():
    return (
        joinedload(Sale.user),
        selectinload(Sale.items)
        .selectinload(SaleItem.product)
        .selectinload(Product.category),
        selectinload(Sale.returns)
        .selectinload(SaleReturn.items)
        .selectinload(SaleReturnItem.product)
        .selectinload(Product.category),
    )


def _summary_response(summary):
    return {
        "gross_sales": money(summary["gross_sales"]),
        "net_sales": money(summary["net_sales"]),
        "gross_profit": money(summary["gross_profit"]),
        "gross_margin_rate": summary["gross_margin_rate"],
        "refund_total": money(summary["refund_total"]),
        "refund_rate": summary["refund_rate"],
        "transaction_count": summary["transaction_count"],
        "average_sale": money(summary["average_sale"]),
        "units_sold": summary["units_sold"],
        "net_units_sold": summary["net_units_sold"],
        "average_items_per_transaction": summary["average_items_per_transaction"],
        "costed_units": summary["costed_units"],
        "items_without_cost": summary["items_without_cost"],
        "cost_coverage_rate": summary["cost_coverage_rate"],
    }


def _summary_for_period(start_date, end_date):
    query = _period_query(start_date, end_date)
    gross_sales, net_sales, transaction_count = query.with_entities(
        func.coalesce(func.sum(Sale.total_amount), 0),
        func.coalesce(func.sum(net_revenue_expression()), 0),
        func.count(Sale.id),
    ).one()

    item_totals = db.session.query(
        func.coalesce(func.sum(SaleItem.quantity), 0),
        func.coalesce(func.sum(case(
            (SaleItem.unit_cost.is_not(None), SaleItem.quantity),
            else_=0,
        )), 0),
        func.coalesce(func.sum(case(
            (
                SaleItem.unit_cost.is_not(None),
                (SaleItem.unit_price - SaleItem.unit_cost) * SaleItem.quantity,
            ),
            else_=0,
        )), 0),
    ).join(
        Sale, Sale.id == SaleItem.sale_id
    ).filter(
        Sale.created_at >= _utc_boundary(start_date),
        Sale.created_at < _utc_boundary(end_date, at_end=True),
    ).one()
    units_sold, costed_units, item_profit = item_totals

    returned_units, return_profit = db.session.query(
        func.coalesce(func.sum(SaleReturnItem.quantity), 0),
        func.coalesce(func.sum(case(
            (
                SaleReturnItem.unit_cost.is_not(None),
                case(
                    (
                        SaleReturnItem.restock.is_(True),
                        SaleReturnItem.unit_cost * SaleReturnItem.quantity,
                    ),
                    else_=0,
                ) - SaleReturnItem.unit_price * SaleReturnItem.quantity,
            ),
            else_=0,
        )), 0),
    ).join(
        SaleReturn, SaleReturn.id == SaleReturnItem.sale_return_id
    ).join(
        Sale, Sale.id == SaleReturn.sale_id
    ).filter(
        Sale.created_at >= _utc_boundary(start_date),
        Sale.created_at < _utc_boundary(end_date, at_end=True),
    ).one()

    gross_sales = _decimal(gross_sales)
    net_sales = _decimal(net_sales)
    refund_total = gross_sales - net_sales
    transaction_count = int(transaction_count)
    units_sold = int(units_sold)
    costed_units = int(costed_units)
    net_units_sold = max(0, units_sold - int(returned_units))
    gross_profit = _decimal(item_profit) + _decimal(return_profit)
    summary = {
        "gross_sales": gross_sales,
        "net_sales": net_sales,
        "gross_profit": gross_profit,
        "gross_margin_rate": (
            _rate(gross_profit, net_sales) if costed_units else None
        ),
        "refund_total": refund_total,
        "refund_rate": _rate(refund_total, gross_sales),
        "transaction_count": transaction_count,
        "average_sale": net_sales / transaction_count if transaction_count else Decimal("0"),
        "units_sold": units_sold,
        "net_units_sold": net_units_sold,
        "average_items_per_transaction": round(net_units_sold / transaction_count, 2)
        if transaction_count else 0,
        "costed_units": costed_units,
        "items_without_cost": max(0, units_sold - costed_units),
        "cost_coverage_rate": _rate(Decimal(costed_units), Decimal(units_sold)),
    }
    return summary


def _inventory_snapshot():
    today = datetime.now(business_timezone()).date()
    sales_start = today - timedelta(days=29)
    sold_rows = db.session.query(
        SaleItem.product_id,
        func.coalesce(func.sum(SaleItem.quantity), 0),
    ).join(
        Sale, Sale.id == SaleItem.sale_id
    ).filter(
        Sale.created_at >= _utc_boundary(sales_start),
        Sale.created_at < _utc_boundary(today, at_end=True),
    ).group_by(SaleItem.product_id).all()
    sold_by_product = {product_id: int(quantity) for product_id, quantity in sold_rows}

    returned_rows = db.session.query(
        SaleReturnItem.product_id,
        func.coalesce(func.sum(SaleReturnItem.quantity), 0),
    ).join(
        SaleReturn, SaleReturn.id == SaleReturnItem.sale_return_id
    ).join(
        Sale, Sale.id == SaleReturn.sale_id
    ).filter(
        Sale.created_at >= _utc_boundary(sales_start),
        Sale.created_at < _utc_boundary(today, at_end=True),
    ).group_by(SaleReturnItem.product_id).all()
    returned_by_product = {
        product_id: int(quantity) for product_id, quantity in returned_rows
    }

    products = Product.query.filter(
        Product.is_active.is_(True)
    ).options(joinedload(Product.category)).order_by(Product.title.asc()).all()

    stock_cost_value = Decimal("0")
    stock_retail_value = Decimal("0")
    stock_units = 0
    stock_units_without_cost = 0
    low_stock = []
    slow_moving = []
    out_of_stock_count = 0

    for product in products:
        quantity = int(product.stock_quantity or 0)
        stock_units += quantity
        stock_retail_value += _decimal(product.price) * quantity
        if product.unit_cost is None:
            stock_units_without_cost += quantity
        else:
            stock_cost_value += _decimal(product.unit_cost) * quantity

        net_units_30d = max(
            0,
            sold_by_product.get(product.id, 0)
            - returned_by_product.get(product.id, 0),
        )
        days_cover = (
            round(quantity / (net_units_30d / 30), 1)
            if net_units_30d else None
        )
        row = {
            "product_id": product.id,
            "product_title": product.title,
            "category": product.category.name if product.category else "Uncategorized",
            "stock_quantity": quantity,
            "low_stock_threshold": int(product.low_stock_threshold or 0),
            "units_sold_30d": net_units_30d,
            "days_cover": days_cover,
            "unit_cost": money(product.unit_cost) if product.unit_cost is not None else None,
            "stock_value_at_cost": money(_decimal(product.unit_cost) * quantity)
            if product.unit_cost is not None else None,
        }
        if quantity == 0:
            out_of_stock_count += 1
        if quantity <= int(product.low_stock_threshold or 0):
            low_stock.append(row)
        if quantity > 0 and net_units_30d == 0:
            slow_moving.append(row)

    low_stock.sort(key=lambda row: (
        row["stock_quantity"] != 0,
        row["days_cover"] is None,
        row["days_cover"] if row["days_cover"] is not None else float("inf"),
        row["stock_quantity"],
    ))

    outstanding_quantity = func.sum(
        PurchaseOrderItem.quantity - PurchaseOrderItem.received_quantity
    )
    outstanding_value = func.sum(
        (PurchaseOrderItem.quantity - PurchaseOrderItem.received_quantity)
        * PurchaseOrderItem.unit_cost
    )
    open_order_count, pending_units, pending_value = db.session.query(
        func.count(func.distinct(PurchaseOrder.id)),
        func.coalesce(outstanding_quantity, 0),
        func.coalesce(outstanding_value, 0),
    ).join(
        PurchaseOrder, PurchaseOrder.id == PurchaseOrderItem.purchase_order_id
    ).filter(
        PurchaseOrder.status.in_(("ordered", "partially_received")),
        PurchaseOrderItem.received_quantity < PurchaseOrderItem.quantity,
    ).one()

    return {
        "active_product_count": len(products),
        "stock_units": stock_units,
        "stock_value_at_cost": money(stock_cost_value),
        "stock_value_at_retail": money(stock_retail_value),
        "stock_units_without_cost": stock_units_without_cost,
        "stock_cost_coverage_rate": _rate(
            Decimal(stock_units - stock_units_without_cost), Decimal(stock_units)
        ),
        "low_stock_count": len(low_stock),
        "out_of_stock_count": out_of_stock_count,
        "slow_moving_count": len(slow_moving),
        "slow_moving_stock_value_at_cost": money(sum(
            (_decimal(row["stock_value_at_cost"]) for row in slow_moving if row["stock_value_at_cost"] is not None),
            Decimal("0"),
        )),
        "low_stock_products": low_stock[:8],
        "slow_moving_products": slow_moving[:8],
        "days_cover_basis_days": 30,
        "open_purchase_order_count": int(open_order_count or 0),
        "pending_purchase_order_units": int(pending_units or 0),
        "pending_purchase_order_value": money(pending_value),
    }


def _shift_snapshot(start_date, end_date):
    now = datetime.now(UTC)
    start_at = _utc_boundary(start_date)
    end_at = _utc_boundary(end_date, at_end=True)
    effective_end = min(end_at, now) if end_at else now

    overlap_query = CashierShift.query.options(
        joinedload(CashierShift.user)
    )
    if end_at is not None:
        overlap_query = overlap_query.filter(CashierShift.opened_at < end_at)
    if start_at is not None:
        overlap_query = overlap_query.filter(
            or_(CashierShift.closed_at.is_(None), CashierShift.closed_at > start_at)
        )
    shifts = overlap_query.all()

    cashier_hours = {}
    for shift in shifts:
        if shift.user is None or shift.user.role != "cashier":
            continue
        opened_at = _as_utc(shift.opened_at)
        closed_at = _as_utc(shift.closed_at) if shift.closed_at else now
        interval_start = max(opened_at, start_at) if start_at else opened_at
        interval_end = min(closed_at, effective_end)
        if interval_end > interval_start:
            cashier_hours[shift.user_id] = cashier_hours.get(shift.user_id, 0) + (
                interval_end - interval_start
            ).total_seconds() / 3600

    open_shifts = [shift for shift in shifts if shift.status == "open"]
    open_rows = []
    stale_count = 0
    expected_cash_total = Decimal("0")
    for shift in open_shifts:
        hours_open = max(0, (now - _as_utc(shift.opened_at)).total_seconds() / 3600)
        stale = hours_open >= 12
        stale_count += int(stale)
        expected_cash = expected_cash_for_shift(shift)
        expected_cash_total += expected_cash
        open_rows.append({
            "shift_id": shift.id,
            "user_id": shift.user_id,
            "cashier": shift.user.name if shift.user else f"User {shift.user_id}",
            "role": shift.user.role if shift.user else None,
            "opened_at": shift.opened_at.isoformat(),
            "hours_open": round(hours_open, 1),
            "is_stale": stale,
            "expected_cash": money(expected_cash),
        })
    open_rows.sort(key=lambda row: row["hours_open"], reverse=True)

    closed_query = CashierShift.query.options(
        joinedload(CashierShift.user)
    ).filter(
        CashierShift.status == "closed",
        CashierShift.closed_at.is_not(None),
    )
    if start_at is not None:
        closed_query = closed_query.filter(CashierShift.closed_at >= start_at)
    if end_at is not None:
        closed_query = closed_query.filter(CashierShift.closed_at < end_at)
    closed_shifts = closed_query.order_by(CashierShift.closed_at.desc()).all()

    shortage = Decimal("0")
    overage = Decimal("0")
    variance_count = 0
    for shift in closed_shifts:
        variance = _decimal(shift.cash_variance)
        if variance < 0:
            shortage += abs(variance)
            variance_count += 1
        elif variance > 0:
            overage += variance
            variance_count += 1

    return {
        "open_shift_count": len(open_shifts),
        "stale_open_shift_count": stale_count,
        "open_expected_cash": money(expected_cash_total),
        "open_shifts": open_rows,
        "closed_shift_count": len(closed_shifts),
        "variance_shift_count": variance_count,
        "cash_shortage_total": money(shortage),
        "cash_overage_total": money(overage),
        "recent_closed_shifts": [
            {
                "shift_id": shift.id,
                "cashier": shift.user.name if shift.user else f"User {shift.user_id}",
                "closed_at": shift.closed_at.isoformat(),
                "expected_cash": money(_decimal(shift.expected_cash)),
                "closing_cash": money(_decimal(shift.closing_cash)),
                "cash_variance": money(_decimal(shift.cash_variance)),
            }
            for shift in closed_shifts[:6]
        ],
        "cashier_hours": {
            user_id: round(hours, 2) for user_id, hours in cashier_hours.items()
        },
    }


def _serialize_product_rows(rows):
    return [
        {
            "product_id": row["product_id"],
            "product_title": row["product_title"],
            "category": row["category"],
            "units_sold": row["net_units_sold"],
            "net_revenue": money(row["net_revenue"]),
            "gross_profit": money(row["gross_profit"]),
            "margin_rate": row["margin_rate"],
            "cost_coverage_rate": row["cost_coverage_rate"],
            "items_without_cost": row["items_without_cost"],
        }
        for row in rows
    ]


def _serialize_category_rows(rows):
    return [
        {
            "category": row["category"],
            "units_sold": row["net_units_sold"],
            "net_revenue": money(row["net_revenue"]),
            "gross_profit": money(row["gross_profit"]),
            "margin_rate": row["margin_rate"],
            "cost_coverage_rate": row["cost_coverage_rate"],
            "items_without_cost": row["items_without_cost"],
        }
        for row in rows
    ]


@bp.get("/summary")
@manager_required
def sales_summary():
    query, error = filtered_sales_query()
    if error:
        return error

    revenue, count = query.with_entities(
        func.coalesce(func.sum(net_revenue_expression()), 0),
        func.count(Sale.id),
    ).one()

    return jsonify(
        status="success",
        total_revenue=money(revenue),
        transaction_count=int(count),
    ), 200


@bp.get("/sales-by-cashier")
@manager_required
def sales_by_cashier():
    query, error = filtered_sales_query()
    if error:
        return error

    rows = query.join(User, User.id == Sale.user_id).with_entities(
        User.id.label("user_id"),
        User.username,
        User.name,
        func.sum(net_revenue_expression()).label("total_revenue"),
        func.count(Sale.id).label("transaction_count"),
    ).group_by(
        User.id, User.username, User.name
    ).order_by(func.sum(net_revenue_expression()).desc()).all()

    return jsonify(status="success", results=[
        {
            "user_id": row.user_id,
            "username": row.username,
            "name": row.name,
            "total_revenue": money(row.total_revenue),
            "transaction_count": int(row.transaction_count),
        }
        for row in rows
    ]), 200


@bp.get("/sales-by-date")
@manager_required
def sales_by_date():
    query, error = filtered_sales_query()
    if error:
        return error

    rows = _aggregate_sales(query.options(*_sales_detail_options()).all())["daily_sales"]

    return jsonify(status="success", results=[
        {
            "date": row["date"],
            "total_revenue": money(row["net_sales"]),
            "transaction_count": row["transactions"],
        }
        for row in rows
    ]), 200


@bp.get("/payment-methods")
@manager_required
def payment_methods():
    query, error = filtered_sales_query()
    if error:
        return error

    rows = query.with_entities(
        Sale.payment_method.label("payment_method"),
        func.sum(net_revenue_expression()).label("total_revenue"),
        func.count(Sale.id).label("transaction_count"),
    ).group_by(
        Sale.payment_method
    ).order_by(
        func.sum(net_revenue_expression()).desc(),
        Sale.payment_method.asc(),
    ).all()

    return jsonify(status="success", results=[
        {
            "payment_method": row.payment_method,
            "total_revenue": money(row.total_revenue),
            "transaction_count": int(row.transaction_count),
        }
        for row in rows
    ]), 200


@bp.get("/best-selling-products")
@manager_required
def best_selling_products():
    query, error = filtered_sales_query()
    if error:
        return error

    rows = query.join(
        SaleItem, SaleItem.sale_id == Sale.id
    ).join(
        Product, Product.id == SaleItem.product_id
    ).with_entities(
        Product.id.label("product_id"),
        Product.title.label("product_title"),
        func.sum(SaleItem.quantity).label("quantity_sold"),
        func.sum(SaleItem.subtotal).label("total_revenue"),
    ).group_by(
        Product.id, Product.title
    ).order_by(
        func.sum(SaleItem.quantity).desc(),
        Product.title.asc(),
    ).all()

    sale_ids = query.with_entities(Sale.id)
    returned_rows = (
        db.session.query(
            SaleReturnItem.product_id,
            func.sum(SaleReturnItem.quantity),
            func.sum(SaleReturnItem.unit_price * SaleReturnItem.quantity),
        )
        .join(SaleReturn, SaleReturn.id == SaleReturnItem.sale_return_id)
        .filter(SaleReturn.sale_id.in_(sale_ids))
        .group_by(SaleReturnItem.product_id)
        .all()
    )
    returned_by_product = {
        product_id: (int(quantity), Decimal(str(revenue)))
        for product_id, quantity, revenue in returned_rows
    }

    results = [
        {
            "product_id": row.product_id,
            "product_title": row.product_title,
            "quantity_sold": max(
                0,
                int(row.quantity_sold) - returned_by_product.get(row.product_id, (0, Decimal("0")))[0],
            ),
            "total_revenue": money(
                Decimal(str(row.total_revenue))
                - returned_by_product.get(row.product_id, (0, Decimal("0")))[1]
            ),
        }
        for row in rows
    ]
    results.sort(key=lambda result: (-result["quantity_sold"], result["product_title"]))
    return jsonify(status="success", results=results), 200


@bp.get("/dashboard")
@manager_required
def dashboard_summary():
    query, error = filtered_sales_query()
    if error:
        return error

    total_sales, revenue, count = query.with_entities(
        func.coalesce(func.sum(Sale.total_amount), 0),
        func.coalesce(func.sum(net_revenue_expression()), 0),
        func.count(Sale.id),
    ).one()

    low_stock = Product.query.filter(
        Product.is_active.is_(True),
        Product.stock_quantity <= Product.low_stock_threshold
    ).order_by(
        Product.stock_quantity.asc(),
        Product.title.asc(),
    ).all()

    return jsonify(
        status="success",
        total_sales=money(total_sales),
        total_revenue=money(revenue),
        transaction_count=int(count),
        product_count=Product.query.filter(Product.is_active.is_(True)).count(),
        low_stock_count=len(low_stock),
        low_stock_products=[
            {
                "id": product.id,
                "title": product.title,
                "stock_quantity": product.stock_quantity,
                "low_stock_threshold": product.low_stock_threshold,
            }
            for product in low_stock
        ],
        cashier_count=User.query.filter_by(role="cashier").count(),
    ), 200


@bp.get("/gross-margin")
@manager_required
def gross_margin_summary():
    query, error = filtered_sales_query()
    if error:
        return error

    gross_margin = Decimal("0.00")
    net_revenue = Decimal("0.00")
    items_without_cost = 0
    for sale in query.all():
        net_revenue += Decimal(str(sale.total_amount))
        for sale_return in sale.returns:
            net_revenue -= Decimal(str(sale_return.refund_total))
        for item in sale.items:
            if item.unit_cost is None:
                items_without_cost += item.quantity
                continue
            gross_margin += (
                Decimal(str(item.unit_price)) - Decimal(str(item.unit_cost))
            ) * item.quantity
        for sale_return in sale.returns:
            for returned_item in sale_return.items:
                if returned_item.restock and returned_item.unit_cost is not None:
                    gross_margin += Decimal(str(returned_item.unit_cost)) * returned_item.quantity
                gross_margin -= Decimal(str(returned_item.unit_price)) * returned_item.quantity

    return jsonify(
        status="success",
        net_revenue=money(net_revenue),
        gross_margin=money(gross_margin),
        items_without_cost=items_without_cost,
    ), 200


@bp.get("/manager-dashboard")
@manager_required
def manager_dashboard():
    start_date, end_date, error = _date_range(
        request.args.get("start_date"),
        request.args.get("end_date"),
        default_days=30,
    )
    if error:
        return error

    period_days = (end_date - start_date).days + 1
    previous_end = start_date - timedelta(days=1)
    previous_start = previous_end - timedelta(days=period_days - 1)
    details = _sales_detail_options()

    current_sales = _period_query(start_date, end_date).options(*details).all()
    current = _aggregate_sales(current_sales)
    previous_summary = _summary_for_period(previous_start, previous_end)
    shifts = _shift_snapshot(start_date, end_date)
    inventory = _inventory_snapshot()

    cashier_hours = shifts.pop("cashier_hours")
    cashier_data = {
        row["user_id"]: row for row in current["cashiers"]
    }
    for cashier in User.query.filter_by(role="cashier").order_by(User.name.asc()).all():
        row = cashier_data.setdefault(cashier.id, {
            "user_id": cashier.id,
            "name": cashier.name,
            "username": cashier.username,
            "gross_sales": Decimal("0"),
            "net_sales": Decimal("0"),
            "refund_total": Decimal("0"),
            "transaction_count": 0,
            "units_sold": 0,
            "units_returned": 0,
            "net_units_sold": 0,
            "average_sale": Decimal("0"),
            "refund_rate": None,
        })
        hours_worked = cashier_hours.get(cashier.id, 0)
        row["hours_worked"] = round(hours_worked, 2)
        row["sales_per_hour"] = (
            money(row["net_sales"] / Decimal(str(hours_worked)))
            if hours_worked > 0 else None
        )

    cashier_rows = sorted(
        cashier_data.values(),
        key=lambda row: (row["net_sales"], row["transaction_count"]),
        reverse=True,
    )
    for row in cashier_rows:
        row["gross_sales"] = money(row["gross_sales"])
        row["net_sales"] = money(row["net_sales"])
        row["refund_total"] = money(row["refund_total"])
        row["average_sale"] = money(row["average_sale"])

    product_rows = current["products"]
    bestseller_rows = sorted(
        product_rows,
        key=lambda row: (row["net_units_sold"], row["net_revenue"]),
        reverse=True,
    )
    profit_rows = sorted(
        (row for row in product_rows if row["costed_units"] > 0),
        key=lambda row: (row["gross_profit"], row["net_revenue"]),
        reverse=True,
    )
    category_rows = sorted(
        current["categories"],
        key=lambda row: (row["gross_profit"], row["net_revenue"]),
        reverse=True,
    )

    return jsonify(
        status="success",
        timezone="Africa/Nairobi",
        period={
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "days": period_days,
            "previous_start_date": previous_start.isoformat(),
            "previous_end_date": previous_end.isoformat(),
        },
        current=_summary_response(current["summary"]),
        previous=_summary_response(previous_summary),
        daily_sales=[
            {
                "date": row["date"],
                "net_sales": money(row["net_sales"]),
                "transactions": row["transactions"],
            }
            for row in current["daily_sales"]
        ],
        payment_methods=[
            {
                "payment_method": row["payment_method"],
                "net_sales": money(row["net_sales"]),
                "transactions": row["transactions"],
            }
            for row in current["payment_methods"]
        ],
        best_sellers=_serialize_product_rows(bestseller_rows[:10]),
        profit_products=_serialize_product_rows(profit_rows[:10]),
        profit_by_category=_serialize_category_rows(category_rows),
        cashier_performance=cashier_rows,
        hourly_sales=[
            {
                "hour": row["hour"],
                "net_sales": money(row["net_sales"]),
                "transactions": row["transactions"],
            }
            for row in current["hourly_sales"]
        ],
        weekday_sales=[
            {
                "weekday": row["weekday"],
                "label": ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")[row["weekday"]],
                "net_sales": money(row["net_sales"]),
                "transactions": row["transactions"],
            }
            for row in current["weekday_sales"]
        ],
        inventory=inventory,
        shifts=shifts,
    ), 200
