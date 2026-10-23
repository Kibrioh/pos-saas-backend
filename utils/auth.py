from functools import wraps
from flask import g, jsonify, request
from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity
from extensions import db
from models import Branch, Tenant, User


def get_current_user():
    """Return the logged-in User (from the JWT), or None."""
    user_id = get_jwt_identity()
    if user_id is None:
        return None
    return db.session.get(User, int(user_id))


def establish_request_scope(user):
    """Set the authenticated business and permitted branch for this request."""
    g.tenant_id = user.tenant_id
    tenant = Tenant.query.filter_by(id=user.tenant_id).first()
    if tenant is None or tenant.status != "active":
        return jsonify(status="error", message="Business account is not active"), 403
    g.business_timezone = tenant.timezone
    requested_branch = request.headers.get("X-Branch-ID")

    if requested_branch:
        try:
            branch_id = int(requested_branch)
        except (TypeError, ValueError):
            return jsonify(status="error", message="Invalid branch selection"), 400
    else:
        branch_id = user.branch_id

    if user.role != "manager" and branch_id != user.branch_id:
        return jsonify(status="error", message="You cannot access another branch"), 403

    branch = Branch.query.filter_by(
        id=branch_id,
        tenant_id=user.tenant_id,
        is_active=True,
    ).first()
    if branch is None:
        return jsonify(status="error", message="Branch not found"), 404

    g.branch_id = branch.id
    g.active_branch = branch
    return None


def roles_required(*allowed_roles):
    """
    401 -> no/invalid/expired token or user no longer exists
    403 -> logged in but role not allowed
    """
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            verify_jwt_in_request()
            user = get_current_user()
            if user is None:
                return jsonify(status="error", message="User not found"), 401
            scope_error = establish_request_scope(user)
            if scope_error:
                return scope_error
            if user.role not in allowed_roles:
                return jsonify(
                    status="error",
                    message="You do not have permission to perform this action",
                ), 403
            return fn(*args, **kwargs)
        return wrapper
    return decorator


login_required = roles_required("manager", "cashier")
manager_required = roles_required("manager")
