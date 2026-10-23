import re
import secrets
from decimal import Decimal, InvalidOperation

from flask import Blueprint, g, request, jsonify
from flask_jwt_extended import create_access_token, get_jwt_identity
from sqlalchemy import text
from extensions import db
from models import AuditLog, Branch, Tenant, User
from services.audit_service import add_audit_event
from utils.auth import get_current_user, login_required, manager_required
from utils.password_policy import password_policy_error

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")

VALID_ROLES = ("manager", "cashier")


def _payload():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def _branch_coordinates(latitude, longitude):
    def parse(value, label, minimum, maximum):
        if value is None or (isinstance(value, str) and not value.strip()):
            return None, None
        if isinstance(value, bool) or not isinstance(value, (int, float, str)):
            return None, f"Branch {label} must be a number"
        try:
            coordinate = Decimal(str(value).strip())
        except (InvalidOperation, ValueError):
            return None, f"Branch {label} must be a number"
        if not coordinate.is_finite() or coordinate < minimum or coordinate > maximum:
            return None, f"Branch {label} must be between {minimum} and {maximum}"
        return coordinate, None

    latitude, error = parse(latitude, "latitude", -90, 90)
    if error:
        return None, None, error
    longitude, error = parse(longitude, "longitude", -180, 180)
    if error:
        return None, None, error
    if (latitude is None) != (longitude is None):
        return None, None, "Enter both latitude and longitude, or leave both blank"
    return latitude, longitude, None


def _branch_google_place_id(value):
    if value is None or (isinstance(value, str) and not value.strip()):
        return None, None
    if not isinstance(value, str) or len(value.strip()) > 8192:
        return None, "Google Place ID must be a string of at most 8192 characters"
    return value.strip(), None


@auth_bp.post("/login")
def login():
    data = _payload()
    raw_username = data.get("username")
    username = raw_username.strip() if isinstance(raw_username, str) else ""
    raw_password = data.get("password")
    password = raw_password if isinstance(raw_password, str) else ""

    if not username or not password:
        return jsonify(status="error",
                       message="Username and password are required"), 400

    user = User.query.filter(
        db.func.lower(User.username) == username.lower()
    ).first()

    # Same message for unknown user and wrong password (no user enumeration)
    if user is None or not user.check_password(password):
        return jsonify(status="error", message="Invalid username or password"), 401
    tenant = Tenant.query.filter_by(id=user.tenant_id).first()
    if tenant is None or tenant.status != "active":
        return jsonify(status="error", message="Invalid username or password"), 401
    branch = Branch.query.filter_by(
        id=user.branch_id,
        tenant_id=tenant.id,
        is_active=True,
    ).first()
    if branch is None:
        return jsonify(status="error", message="Invalid username or password"), 401

    token = create_access_token(
        identity=str(user.id),
        additional_claims={
            "role": user.role,
            "tenant_id": user.tenant_id,
            "branch_id": user.branch_id,
        },
    )
    user_data = user.to_dict()
    user_data["business"] = tenant.to_dict()
    user_data["active_branch_id"] = user.branch_id
    user_data["active_branch"] = branch.to_dict()
    return jsonify(status="success", access_token=token, user=user_data), 200


@auth_bp.get("/manager-signup-available")
def manager_signup_available():
    return jsonify(status="success", available=True), 200


@auth_bp.post("/manager-signup")
def manager_signup():
    data = _payload()
    raw_username = data.get("username")
    raw_name = data.get("name")
    raw_business_name = data.get("business_name")
    raw_branch_name = data.get("branch_name", "Main Branch")
    username = raw_username.strip() if isinstance(raw_username, str) else ""
    name = raw_name.strip() if isinstance(raw_name, str) else ""
    business_name = raw_business_name.strip() if isinstance(raw_business_name, str) else ""
    branch_name = raw_branch_name.strip() if isinstance(raw_branch_name, str) else ""
    raw_password = data.get("password")
    password = raw_password if isinstance(raw_password, str) else ""

    errors = {}
    if len(username) < 3:
        errors["username"] = "At least 3 characters"
    elif len(username) > 80:
        errors["username"] = "At most 80 characters"
    if not name:
        errors["name"] = "Name is required"
    elif len(name) > 120:
        errors["name"] = "At most 120 characters"
    if not business_name:
        errors["business_name"] = "Business name is required"
    elif len(business_name) > 160:
        errors["business_name"] = "At most 160 characters"
    if not branch_name:
        errors["branch_name"] = "Branch name is required"
    elif len(branch_name) > 120:
        errors["branch_name"] = "At most 120 characters"
    password_error = password_policy_error(password)
    if password_error:
        errors["password"] = password_error
    if errors:
        return jsonify(status="error", message="Validation failed",
                       errors=errors), 400
    username = username.lower()

    # Serialize public signups so the case-insensitive username check is race-safe.
    if db.session.get_bind().dialect.name == "postgresql":
        db.session.execute(text("LOCK TABLE users IN EXCLUSIVE MODE"))

    if User.query.filter(
        db.func.lower(User.username) == username.lower()
    ).first():
        return jsonify(status="error", message="Username already exists"), 409

    slug_base = re.sub(r"[^a-z0-9]+", "-", business_name.lower()).strip("-")[:80] or "business"
    tenant = Tenant(
        name=business_name,
        slug=f"{slug_base}-{secrets.token_hex(8)}",
    )
    db.session.add(tenant)
    db.session.flush()

    branch = Branch(
        tenant_id=tenant.id,
        name=branch_name,
        is_default=True,
    )
    db.session.add(branch)
    db.session.flush()

    user = User(
        username=username,
        name=name,
        role="manager",
        tenant_id=tenant.id,
        branch_id=branch.id,
    )
    user.set_password(password)
    db.session.add(user)
    db.session.flush()
    db.session.add(AuditLog(
        tenant_id=tenant.id,
        branch_id=branch.id,
        actor_user_id=user.id,
        action="business.created",
        entity_type="tenant",
        entity_id=tenant.id,
        details={"business_name": tenant.name, "owner_username": user.username},
    ))
    db.session.commit()

    token = create_access_token(
        identity=str(user.id),
        additional_claims={
            "role": user.role,
            "tenant_id": user.tenant_id,
            "branch_id": user.branch_id,
        },
    )
    user_data = user.to_dict()
    user_data["business"] = tenant.to_dict()
    user_data["active_branch_id"] = branch.id
    user_data["active_branch"] = branch.to_dict()
    return jsonify(status="success", access_token=token,
                   user=user_data), 201


@auth_bp.get("/me")
@login_required
def me():
    user = get_current_user()
    user_data = user.to_dict()
    user_data["active_branch_id"] = g.branch_id
    user_data["active_branch"] = g.active_branch.to_dict()
    tenant = Tenant.query.filter_by(id=user.tenant_id).first()
    user_data["business"] = tenant.to_dict() if tenant else None
    return jsonify(status="success", user=user_data), 200


@auth_bp.post("/register")
@manager_required
def register():
    data = _payload()
    raw_username = data.get("username")
    raw_name = data.get("name")
    username = raw_username.strip() if isinstance(raw_username, str) else ""
    name = raw_name.strip() if isinstance(raw_name, str) else ""
    raw_password = data.get("password")
    password = raw_password if isinstance(raw_password, str) else ""
    role = data.get("role", "cashier")

    errors = {}
    if len(username) < 3:
        errors["username"] = "At least 3 characters"
    if not name:
        errors["name"] = "Name is required"
    password_error = password_policy_error(password)
    if password_error:
        errors["password"] = password_error
    if role not in VALID_ROLES:
        errors["role"] = f"Must be one of {VALID_ROLES}"
    if errors:
        return jsonify(status="error", message="Validation failed",
                       errors=errors), 400
    username = username.lower()

    if User.query.filter(db.func.lower(User.username) == username.lower()).first():
        return jsonify(status="error", message="Username already exists"), 409

    user = User(
        username=username,
        name=name,
        role=role,
        tenant_id=g.tenant_id,
        branch_id=g.branch_id,
    )
    user.set_password(password)
    db.session.add(user)
    db.session.flush()
    add_audit_event(int(get_jwt_identity()), "user.registered", "user", user.id, {
        "username": user.username,
        "role": user.role,
    })
    db.session.commit()
    return jsonify(status="success", user=user.to_dict()), 201


@auth_bp.post("/change-password")
@login_required
def change_password():
    data = _payload()
    raw_old_pw = data.get("old_password")
    raw_new_pw = data.get("new_password")
    old_pw = raw_old_pw if isinstance(raw_old_pw, str) else ""
    new_pw = raw_new_pw if isinstance(raw_new_pw, str) else ""
    user = get_current_user()

    if not user.check_password(old_pw):
        return jsonify(status="error",
                       message="Current password is incorrect"), 401
    password_error = password_policy_error(new_pw)
    if password_error:
        return jsonify(status="error",
                       message=password_error), 400

    user.set_password(new_pw)
    add_audit_event(user.id, "user.password_changed", "user", user.id)
    db.session.commit()
    return jsonify(status="success", message="Password updated"), 200

@auth_bp.get("/users")
@manager_required
def list_users():
    query = User.query
    role = (request.args.get("role") or "").strip().lower()
    if role:
        if role not in VALID_ROLES:
            return jsonify(status="error", message="Invalid user role filter"), 400
        query = query.filter(db.func.lower(User.role) == role)

    users = query.order_by(User.created_at.desc()).all()
    return jsonify(status="success", users=[u.to_dict() for u in users]), 200


@auth_bp.get("/branches")
@login_required
def list_branches():
    user = get_current_user()
    query = Branch.query.filter_by(tenant_id=user.tenant_id, is_active=True)
    if user.role != "manager":
        query = query.filter_by(id=user.branch_id)
    branches = query.order_by(Branch.is_default.desc(), Branch.name.asc()).all()
    return jsonify(status="success", branches=[branch.to_dict() for branch in branches]), 200


@auth_bp.post("/branches")
@manager_required
def create_branch():
    data = _payload()
    name = data.get("name")
    location = data.get("location")
    google_place_id, place_id_error = _branch_google_place_id(data.get("google_place_id"))
    if place_id_error:
        return jsonify(status="error", message=place_id_error), 400
    if google_place_id:
        if data.get("latitude") not in (None, "") or data.get("longitude") not in (None, ""):
            return jsonify(status="error", message="Google coordinates are resolved when needed; enter coordinates manually to save them"), 400
        latitude, longitude, coordinate_error = None, None, None
    else:
        latitude, longitude, coordinate_error = _branch_coordinates(
            data.get("latitude"), data.get("longitude")
        )
    if not isinstance(name, str) or not name.strip():
        return jsonify(status="error", message="Branch name is required"), 400
    if len(name.strip()) > 120:
        return jsonify(status="error", message="Branch name must be at most 120 characters"), 400
    if location is not None and (not isinstance(location, str) or len(location) > 200):
        return jsonify(status="error", message="Branch location must be at most 200 characters"), 400
    if coordinate_error:
        return jsonify(status="error", message=coordinate_error), 400

    normalized_name = name.strip()
    if Branch.query.filter(
        Branch.tenant_id == g.tenant_id,
        db.func.lower(Branch.name) == normalized_name.lower(),
    ).first():
        return jsonify(status="error", message="A branch with this name already exists"), 409

    branch = Branch(
        tenant_id=g.tenant_id,
        name=normalized_name,
        location=location.strip() if location else None,
        google_place_id=google_place_id,
        latitude=latitude,
        longitude=longitude,
    )
    db.session.add(branch)
    db.session.flush()
    add_audit_event(int(get_jwt_identity()), "branch.created", "branch", branch.id, {
        "name": branch.name,
        "location": branch.location,
        "latitude": branch.to_dict()["latitude"],
        "longitude": branch.to_dict()["longitude"],
    })
    db.session.commit()
    return jsonify(status="success", branch=branch.to_dict()), 201


@auth_bp.patch("/branches/<int:branch_id>")
@manager_required
def update_branch(branch_id):
    data = _payload()
    allowed_fields = {"location", "latitude", "longitude", "google_place_id"}
    if not data or set(data) - allowed_fields:
        return jsonify(status="error", message="Provide a branch location, Google Place ID, or coordinates to update"), 400

    branch = Branch.query.filter_by(id=branch_id, tenant_id=g.tenant_id).first()
    if branch is None:
        return jsonify(status="error", message="Branch not found"), 404

    location = branch.location
    if "location" in data:
        location = data["location"]
        if location is not None and (not isinstance(location, str) or len(location) > 200):
            return jsonify(status="error", message="Branch location must be at most 200 characters"), 400
        location = location.strip() if isinstance(location, str) and location.strip() else None

    google_place_id = branch.google_place_id
    if "google_place_id" in data:
        google_place_id, place_id_error = _branch_google_place_id(data["google_place_id"])
        if place_id_error:
            return jsonify(status="error", message=place_id_error), 400
        if google_place_id and (data.get("latitude") not in (None, "") or data.get("longitude") not in (None, "")):
            return jsonify(status="error", message="Google coordinates are resolved when needed; enter coordinates manually to save them"), 400

    if "google_place_id" not in data and ("latitude" in data or "longitude" in data):
        google_place_id = None

    if google_place_id:
        latitude, longitude = None, None
    elif "latitude" in data or "longitude" in data:
        latitude, longitude, coordinate_error = _branch_coordinates(
            data.get("latitude", branch.latitude),
            data.get("longitude", branch.longitude),
        )
        if coordinate_error:
            return jsonify(status="error", message=coordinate_error), 400
    elif "location" in data and "google_place_id" not in data and not ("latitude" in data or "longitude" in data):
        google_place_id = None
        latitude, longitude = None, None
    else:
        latitude, longitude = branch.latitude, branch.longitude

    branch.location = location
    branch.google_place_id = google_place_id
    branch.latitude = latitude
    branch.longitude = longitude

    add_audit_event(int(get_jwt_identity()), "branch.location_updated", "branch", branch.id, {
        "location": branch.location,
        "latitude": branch.to_dict()["latitude"],
        "longitude": branch.to_dict()["longitude"],
    })
    db.session.commit()
    return jsonify(status="success", branch=branch.to_dict()), 200
