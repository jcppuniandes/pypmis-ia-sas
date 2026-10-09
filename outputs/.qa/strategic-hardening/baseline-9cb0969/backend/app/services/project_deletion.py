from __future__ import annotations

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domain.models import Base, Project


class ProjectDeletionService:
    def __init__(self, db: Session):
        self.db = db

    def delete(self, project_id: int) -> None:
        self._clear_project_cycles(project_id)
        remaining = [
            table
            for table in reversed(list(Base.metadata.tables.values()))
            if table.name != Project.__tablename__ and "project_id" in table.c
        ]

        for _ in range(len(remaining) + 5):
            if not remaining:
                break
            next_remaining = []
            progressed = False
            for table in remaining:
                savepoint = self.db.begin_nested()
                try:
                    self.db.execute(table.delete().where(table.c.project_id == project_id))
                    savepoint.commit()
                    progressed = True
                except IntegrityError:
                    savepoint.rollback()
                    next_remaining.append(table)
            if not progressed:
                table_names = ", ".join(table.name for table in next_remaining)
                raise RuntimeError(f"Could not delete project records from dependent tables: {table_names}")
            remaining = next_remaining

        self.db.execute(Project.__table__.delete().where(Project.id == project_id))

    def _clear_project_cycles(self, project_id: int) -> None:
        updates = [
            ("control_accounts", {"awp_package_id": None}),
            ("work_packages", {"parent_id": None, "control_account_id": None, "wbs_id": None}),
            ("wbs", {"parent_id": None}),
            ("cost_breakdown_structures", {"parent_id": None}),
            ("funding_sources", {"parent_id": None}),
        ]
        for table_name, values in updates:
            table = Base.metadata.tables.get(table_name)
            if table is None or "project_id" not in table.c:
                continue
            existing_values = {key: value for key, value in values.items() if key in table.c}
            if not existing_values:
                continue
            self.db.execute(table.update().where(table.c.project_id == project_id).values(**existing_values))
