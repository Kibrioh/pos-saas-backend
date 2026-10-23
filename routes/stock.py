from flask import Blueprint, jsonify, request

from services.stock_service import (
    ServiceError,
    adjust_stock,
    get_all_stock,
    get_low_stock,
    get_movements,
    get_movements_for_product,
    get_out_of_stock,
    restock_product,
)

from utils.auth import get_current_user, login_required, manager_required
bp = Blueprint("stock", __name__, url_prefix="/api/stock")


@bp.get("")
@login_required
def list_stock():
    return jsonify(get_all_stock()), 200


@bp.get("/low")
@login_required
def low_stock():
    return jsonify(get_low_stock()), 200


@bp.get("/out")
@login_required
def out_of_stock():
    return jsonify(get_out_of_stock()), 200


@bp.get("/movements")
@login_required
def all_movements():
    return jsonify(get_movements()), 200


@bp.get("/movements/<int:product_id>")
@login_required
def movements_for_product(product_id):
    try:
        return jsonify(get_movements_for_product(product_id)), 200
    except ServiceError as e:
        return jsonify({"status": "error", "message": str(e)}), e.status_code


@bp.post("/restock")
@manager_required
def restock():
    payload = request.get_json(silent=True) or {}
    try:
        result = restock_product(payload, get_current_user().id)
    except ServiceError as e:
        return jsonify({"status": "error", "message": str(e)}), e.status_code
    return jsonify(result), 201


@bp.post("/adjust")
@manager_required
def adjust():
    payload = request.get_json(silent=True) or {}
    try:
        result = adjust_stock(payload, get_current_user().id)
    except ServiceError as e:
        return jsonify({"status": "error", "message": str(e)}), e.status_code
    return jsonify(result), 201
