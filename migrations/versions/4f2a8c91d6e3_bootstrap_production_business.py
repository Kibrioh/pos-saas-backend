"""bootstrap a production business on an empty database

Revision ID: 4f2a8c91d6e3
Revises: d1f81ac4372b
Create Date: 2026-10-29 00:00:00.000000

"""
import os
import re

from alembic import op
import sqlalchemy as sa
from werkzeug.security import generate_password_hash


revision = "4f2a8c91d6e3"
down_revision = "d1f81ac4372b"
branch_labels = None
depends_on = None


DEFAULT_CATEGORIES = (
    "Groceries",
    "Beverages",
    "Household",
    "Electronics",
    "Phones & Accessories",
    "Computers",
    "Fashion",
    "Shoes",
    "Beauty & Personal Care",
    "Home & Kitchen",
    "Sports & Outdoors",
    "Toys & Games",
    "Books & Stationery",
    "Automotive",
    "Baby Products",
)


def _required_setting(name):
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(
            f"{name} must be set before upgrading a database without users."
        )
    return value


def _password_is_valid(password):
    return (
        len(password) >= 8
        and any(char.isupper() for char in password)
        and any(char.islower() for char in password)
        and any(not char.isalnum() and not char.isspace() for char in password)
    )


def upgrade():
    connection = op.get_bind()

    # Existing databases already have an owner or staff account. Leave all
    # existing business data untouched when this data migration is applied.
    has_users = connection.execute(
        sa.text("SELECT id FROM users ORDER BY id LIMIT 1")
    ).first()
    if has_users:
        return

    business_name = _required_setting("BOOTSTRAP_BUSINESS_NAME")
    manager_name = _required_setting("BOOTSTRAP_MANAGER_NAME")
    manager_username = _required_setting("BOOTSTRAP_MANAGER_USERNAME").lower()
    manager_password = os.getenv("BOOTSTRAP_MANAGER_PASSWORD", "")
    branch_name = os.getenv("BOOTSTRAP_BRANCH_NAME", "Main Branch").strip()

    if len(business_name) > 160:
        raise RuntimeError("BOOTSTRAP_BUSINESS_NAME must be at most 160 characters.")
    if len(manager_name) > 120:
        raise RuntimeError("BOOTSTRAP_MANAGER_NAME must be at most 120 characters.")
    if len(manager_username) < 3 or len(manager_username) > 80:
        raise RuntimeError(
            "BOOTSTRAP_MANAGER_USERNAME must be between 3 and 80 characters."
        )
    if not branch_name or len(branch_name) > 120:
        raise RuntimeError(
            "BOOTSTRAP_BRANCH_NAME must be between 1 and 120 characters."
        )
    if not _password_is_valid(manager_password):
        raise RuntimeError(
            "BOOTSTRAP_MANAGER_PASSWORD must be at least 8 characters and include "
            "an uppercase letter, a lowercase letter, and a special character."
        )

    tenant = connection.execute(
        sa.text("SELECT id FROM tenants ORDER BY id LIMIT 1")
    ).first()
    if tenant is None:
        raise RuntimeError("The tenant migration must run before business bootstrap.")
    tenant_id = tenant.id

    branch = connection.execute(
        sa.text(
            "SELECT id FROM branches "
            "WHERE tenant_id = :tenant_id AND is_default = TRUE "
            "ORDER BY id LIMIT 1"
        ),
        {"tenant_id": tenant_id},
    ).first()
    if branch is None:
        raise RuntimeError("The tenant must have a default branch before bootstrap.")
    branch_id = branch.id

    slug_base = re.sub(r"[^a-z0-9]+", "-", business_name.lower()).strip("-")
    slug = f"{(slug_base or 'business')[:80]}-{tenant_id}"
    connection.execute(
        sa.text("UPDATE tenants SET name = :name, slug = :slug WHERE id = :id"),
        {"name": business_name, "slug": slug, "id": tenant_id},
    )
    connection.execute(
        sa.text("UPDATE branches SET name = :name WHERE id = :id"),
        {"name": branch_name, "id": branch_id},
    )

    connection.execute(
        sa.text(
            "INSERT INTO users "
            "(tenant_id, branch_id, username, password_hash, name, role, created_at) "
            "VALUES (:tenant_id, :branch_id, :username, :password_hash, :name, "
            "'manager', CURRENT_TIMESTAMP)"
        ),
        {
            "tenant_id": tenant_id,
            "branch_id": branch_id,
            "username": manager_username,
            "password_hash": generate_password_hash(manager_password),
            "name": manager_name,
        },
    )

    for category_name in DEFAULT_CATEGORIES:
        connection.execute(
            sa.text(
                "INSERT INTO categories (tenant_id, name, created_at) "
                "SELECT :tenant_id, :name, CURRENT_TIMESTAMP "
                "WHERE NOT EXISTS ("
                "SELECT 1 FROM categories WHERE tenant_id = :tenant_id AND name = :name"
                ")"
            ),
            {"tenant_id": tenant_id, "name": category_name},
        )


def downgrade():
    # Keep the manager and categories: people may already have signed in and
    # edited this data by the time a schema downgrade is considered.
    pass
