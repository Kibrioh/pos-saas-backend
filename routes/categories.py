from flask import Blueprint, jsonify, request

from extensions import db
from models import Category
from utils.auth import login_required, manager_required

bp = Blueprint("categories", __name__, url_prefix="/api/categories")


def _json_payload():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return None
    return payload


def _unsupported_fields(payload):
    unsupported = sorted(set(payload) - {"name"})
    if unsupported:
        return jsonify(
            {"error": f"Unsupported field(s): {', '.join(unsupported)}."}
        ), 400
    return None


@bp.get("")
@login_required
def get_categories():
    categories = Category.query.order_by(Category.name.asc()).all()
    return jsonify([category.to_dict() for category in categories])


@bp.get("/<int:category_id>")
@login_required
def get_category(category_id):
    category = Category.query.get_or_404(category_id)
    return jsonify(category.to_dict())


@bp.post("")
@manager_required
def create_category():
    payload = _json_payload()
    if payload is None:
        return jsonify({"error": "A JSON object is required."}), 400
    unsupported_response = _unsupported_fields(payload)
    if unsupported_response:
        return unsupported_response

    name = payload.get("name")
    if not isinstance(name, str) or not name.strip():
        return jsonify({"error": "Category name is required."}), 400
    name = name.strip()

    if Category.query.filter_by(name=name).first():
        return jsonify({"error": "Category with this name already exists."}), 409

    category = Category(name=name)
    db.session.add(category)
    db.session.commit()
    return jsonify(category.to_dict()), 201


@bp.put("/<int:category_id>")
@manager_required
def update_category(category_id):
    category = Category.query.get_or_404(category_id)
    payload = _json_payload()
    if payload is None:
        return jsonify({"error": "A JSON object is required."}), 400
    unsupported_response = _unsupported_fields(payload)
    if unsupported_response:
        return unsupported_response

    if "name" in payload:
        name = payload.get("name")
        if not isinstance(name, str) or not name.strip():
            return jsonify({"error": "Category name cannot be empty."}), 400
        name = name.strip()
        if Category.query.filter(
            Category.id != category_id, Category.name == name
        ).first():
            return jsonify({"error": "Category with this name already exists."}), 409
        category.name = name

    db.session.commit()
    return jsonify(category.to_dict())
