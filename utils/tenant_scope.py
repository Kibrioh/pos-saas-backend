from flask import g, has_request_context
from sqlalchemy import event, select
from sqlalchemy.orm import Session, with_loader_criteria


_registered = False


def register_tenant_scope_events():
    global _registered
    if _registered:
        return

    from models.tenant import Branch
    from models.tenant_scope import BranchScoped, TenantScoped

    @event.listens_for(Session, "do_orm_execute")
    def apply_tenant_scope(execute_state):
        if not execute_state.is_orm_statement:
            return
        if not (execute_state.is_select or execute_state.is_update or execute_state.is_delete):
            return

        tenant_id = g.get("tenant_id") if has_request_context() else None
        if tenant_id is None:
            tenant_id = execute_state.session.info.get("tenant_id")
        if tenant_id is None:
            return

        statement = execute_state.statement.options(
            with_loader_criteria(
                TenantScoped,
                lambda model: model.tenant_id == tenant_id,
                include_aliases=True,
            )
        )

        branch_id = g.get("branch_id") if has_request_context() else None
        if branch_id is None:
            branch_id = execute_state.session.info.get("branch_id")
        if branch_id is not None:
            statement = statement.options(
                with_loader_criteria(
                    BranchScoped,
                    lambda model: model.branch_id == branch_id,
                    include_aliases=True,
                )
            )

        execute_state.statement = statement

    @event.listens_for(Session, "before_flush")
    def attach_tenant_to_new_rows(session, flush_context, instances):
        tenant_id = g.get("tenant_id") if has_request_context() else None
        branch_id = g.get("branch_id") if has_request_context() else None
        tenant_id = tenant_id or session.info.get("tenant_id")
        branch_id = branch_id or session.info.get("branch_id")

        for row in session.new:
            if not isinstance(row, TenantScoped):
                continue

            if tenant_id is not None:
                if row.tenant_id not in (None, tenant_id):
                    raise ValueError("Cannot create a record for another business.")
                row.tenant_id = tenant_id

            if isinstance(row, BranchScoped):
                if branch_id is not None:
                    if row.branch_id not in (None, branch_id):
                        raise ValueError("Cannot create a record for another branch.")
                    row.branch_id = branch_id
                elif row.branch_id is None:
                    raise ValueError("A branch must be selected for this record.")

            elif hasattr(row, "branch_id") and row.branch_id is None and branch_id is not None:
                row.branch_id = branch_id

            if hasattr(row, "branch_id"):
                effective_tenant = row.tenant_id or tenant_id
                if effective_tenant is not None and row.branch_id is not None:
                    branch_exists = session.execute(
                        select(Branch.id).where(
                            Branch.id == row.branch_id,
                            Branch.tenant_id == effective_tenant,
                            Branch.is_active.is_(True),
                        )
                    ).scalar_one_or_none()
                    if branch_exists is None:
                        raise ValueError("Branch must belong to the selected business.")

        if tenant_id is None:
            return
        for row in session.dirty:
            if not isinstance(row, TenantScoped):
                continue
            if row.tenant_id != tenant_id:
                raise ValueError("Cannot modify a record for another business.")
            if branch_id is not None and isinstance(row, BranchScoped) and row.branch_id != branch_id:
                raise ValueError("Cannot modify a record for another branch.")

    _registered = True
