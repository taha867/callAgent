"""Shared ORM-layer guard for Phase 1+ insert-only tables (runtime_failure_event,
complaint_sla_event) — layer 2 of the three-layer enforcement src/audit/models.py's module
docstring describes for audit_event. audit_event itself keeps its own, earlier,
specifically-named listeners rather than being refactored onto this shared mechanism —
this module exists so the *next* insert-only table doesn't have to hand-write the same
three event listeners again, not to change already-tested Phase 0 code.

The database-layer REVOKE (layer 3) is separate, per-table, hand-written in
migrations/versions/*_insert_only_grants*.py — this module has no knowledge of it.
"""

from typing import Any

from sqlalchemy import event
from sqlalchemy.orm import Session
from sqlalchemy.orm.mapper import Mapper

from src.exceptions import InsertOnlyTableViolationError

_insert_only_classes: set[type] = set()


def enforce_insert_only[ModelT: type](model_cls: ModelT) -> ModelT:
    """Class decorator. Registers mapper-level before_update/before_delete listeners (block
    per-instance mutation) and adds `model_cls` to the set the one shared Session-level
    do_orm_execute listener below checks for *bulk* UPDATE/DELETE statements, which
    mapper-level events don't see.
    """
    _insert_only_classes.add(model_cls)
    # ModelT is bound to plain `type` (so the decorator can return the exact decorated
    # class, preserving its type at every call site) — mypy has no way to know every
    # caller is actually a SQLAlchemy declarative model with __tablename__.
    table_name = model_cls.__tablename__  # type: ignore[attr-defined]

    @event.listens_for(model_cls, "before_update", propagate=True)
    def _block_instance_update(mapper: Mapper, connection: Any, target: Any) -> None:
        raise InsertOnlyTableViolationError(table_name)

    @event.listens_for(model_cls, "before_delete", propagate=True)
    def _block_instance_delete(mapper: Mapper, connection: Any, target: Any) -> None:
        raise InsertOnlyTableViolationError(table_name)

    return model_cls


@event.listens_for(Session, "do_orm_execute")
def _block_bulk_mutation(orm_execute_state: Any) -> None:
    if not (orm_execute_state.is_update or orm_execute_state.is_delete):
        return
    for desc in orm_execute_state.all_mappers:
        if desc.mapper.class_ in _insert_only_classes:
            raise InsertOnlyTableViolationError(desc.mapper.class_.__tablename__)
