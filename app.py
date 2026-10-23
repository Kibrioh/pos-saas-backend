from flask import Flask, jsonify, request 
from config import Config
from extensions import db, migrate, cors, jwt
from sqlalchemy import text
from models import User, Category, Product, Sale, SaleItem, StockMovement
from routes import (
    categories_bp,
    products_bp,
    restocks_bp,
    stock_bp,
    reports_bp,
    sales_bp,
    shifts_bp,
    suppliers_bp,
    purchase_orders_bp,
    audit_bp,
)


def _configured_frontend_origins(value):
    """Return normalized origins from the FRONTEND_ORIGIN setting.

    A comma-separated value is supported so local and deployed frontends can
    both be allowed when needed. Browsers send an origin without a trailing
    slash, so normalize that common configuration mismatch here.
    """
    if not value:
        return []

    values = value if isinstance(value, (list, tuple, set)) else str(value).split(",")
    return [origin.strip().rstrip("/") for origin in values if origin.strip()]


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    db.init_app(app)
    migrate.init_app(app, db)
    frontend_origins = _configured_frontend_origins(app.config.get("FRONTEND_ORIGIN"))
    app.logger.warning(
        "CORS DIAGNOSTIC: raw FRONTEND_ORIGIN=%r; normalized=%r",
        app.config.get("FRONTEND_ORIGIN"),
        frontend_origins,
    )
    if not frontend_origins:
        app.logger.warning(
            "FRONTEND_ORIGIN is unset; browser requests to /api/* will not pass CORS."
        )
    cors.init_app(
        app,
        resources={r"/api/*": {"origins": frontend_origins}},
        methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "X-Branch-ID", "Idempotency-Key"],
        max_age=600,
    )
    jwt.init_app(app)

    from utils.tenant_scope import register_tenant_scope_events
    register_tenant_scope_events()

    from routes.auth import auth_bp
    app.register_blueprint(auth_bp)

    @jwt.unauthorized_loader
    def missing_token(reason):
        return jsonify(status="error", message="Authentication required"), 401

    @jwt.invalid_token_loader
    def invalid_token(reason):
        return jsonify(status="error", message="Invalid token"), 401

    @jwt.expired_token_loader
    def expired_token(header, payload):
        return jsonify(status="error",
                       message="Token expired, please log in again"), 401


    #test connection to postgresql
    @app.get("/api/health")
    def health():
        try:
            db.session.execute(text("SELECT 1"))

            return jsonify({
                "status": "success",
                "message": "POS API is running",
                "database": "connected"
            }), 200

        except Exception as e:
            db.session.rollback()

            return jsonify({
                "status": "error",
                "message": "Database connection failed",
                "error": str(e)
            }), 500
    
    app.register_blueprint(stock_bp)
    app.register_blueprint(restocks_bp)
    app.register_blueprint(categories_bp)
    app.register_blueprint(products_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(sales_bp)
    app.register_blueprint(shifts_bp)
    app.register_blueprint(suppliers_bp)
    app.register_blueprint(purchase_orders_bp)
    app.register_blueprint(audit_bp)
    return app

app = create_app()
if __name__ == "__main__":
    app.run(debug=app.config["DEBUG"], port=Config.PORT)
