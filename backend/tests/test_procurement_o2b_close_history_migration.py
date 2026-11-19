"""Replay every historical revision on physically fresh PostgreSQL.

The first Alembic revision extends a pre-existing app schema. Restore only
its original, frozen pre-Alembic DDL; no current ORM create_all and no stamps.
The allowed endpoint and empty-database guard are deliberately narrow.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import DBAPIError

from app.core.config import get_settings
from app.modules.engineering_foundation.migration_schema import ENGINEERING_MIGRATION_TABLE_NAMES
from app.modules.procurement_foundation.migration_schema import PROCUREMENT_MIGRATION_TABLE_NAMES

BACKEND = Path(__file__).resolve().parents[1]
BOOTSTRAP = BACKEND / "tests/fixtures/o2b_close_pre_alembic_postgres.sql"
ORIGIN = "dd5b5149efc1b876e72b5f1a2ce390378bc44b81"
BOOTSTRAP_SHA256 = "62a6023c5aac393436e123db63ff28d8f24f5ff9a8b15b1a07459785dcef8418"
PRE_O1 = "20261011_0068"
O1 = (
    "20261019_0069",
    "20261020_0070",
    "20261021_0071",
    "20261021_0072",
    "20261022_0073",
    "20261104_0074",
    "20261106_0075",
)
O2A = "20261109_0076"
O2B = "20261111_0077"
CLOSE = "20261111_0078"
ADOPTIONS = "operational_procurement_adoptions"
TEST_ID = 91_000_001
PROFILE_TRIGGERS = {
    "tr_engineering_profile_o2a",
    "tr_procurement_profile_o2b",
}
O1_PROFILE_TRIGGERS = frozenset(
    {
        "o1a_immutable",
        "scope_o1ba_profile_immutable",
        "tr_awp_four_d_profile_b1",
        "tr_cost_profile_o1bc",
        "tr_forecast_profile_o1c",
        "tr_progress_profile_o1bd",
        "tr_schedule_profile_o1bb",
    }
)

CATALOG_QUERIES = {
    "tables": """
        SELECT c.relname, c.relkind FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='public' AND c.relkind IN ('r','p') ORDER BY c.relname
    """,
    "columns": """
        SELECT c.relname, a.attname, format_type(a.atttypid, a.atttypmod),
               a.attnotnull, pg_get_expr(d.adbin,d.adrelid)
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        JOIN pg_attribute a ON a.attrelid=c.oid
        LEFT JOIN pg_attrdef d ON d.adrelid=c.oid AND d.adnum=a.attnum
        WHERE n.nspname='public' AND c.relkind IN ('r','p') AND a.attnum>0 AND NOT a.attisdropped
        ORDER BY c.relname,a.attnum
    """,
    "constraints": """
        SELECT c.relname,x.conname,x.contype,pg_get_constraintdef(x.oid),x.convalidated,x.condeferrable,x.condeferred
        FROM pg_constraint x JOIN pg_class c ON c.oid=x.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='public' ORDER BY c.relname,x.conname
    """,
    "indexes": """
        SELECT c.relname,i.relname,pg_get_indexdef(i.oid),x.indisvalid,x.indisready
        FROM pg_index x JOIN pg_class c ON c.oid=x.indrelid JOIN pg_class i ON i.oid=x.indexrelid
        JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='public' ORDER BY c.relname,i.relname
    """,
    "triggers": """
        SELECT c.relname,t.tgname,pg_get_triggerdef(t.oid),t.tgenabled
        FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='public' AND NOT t.tgisinternal ORDER BY c.relname,t.tgname
    """,
    "functions": """
        SELECT p.oid::regprocedure::text,pg_get_functiondef(p.oid)
        FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
        WHERE n.nspname='public' AND p.prokind IN ('f','p') ORDER BY 1
    """,
}


@dataclass
class MigrationRun:
    engine: Engine
    config: Config
    events: list[dict]
    root_count: int
    postgres_version: str
    pre_o1: dict
    post_o1: dict
    post_o2a: dict
    post_o2b: dict
    head: dict
    identity: dict
    binding: dict


def _sha256(payload) -> str:
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def _catalog(engine: Engine) -> dict:
    with engine.connect() as connection:
        connection.exec_driver_sql("SET TRANSACTION READ ONLY")
        return {key: [tuple(row) for row in connection.exec_driver_sql(sql)] for key, sql in CATALOG_QUERIES.items()}


def _names(snapshot: dict) -> set[str]:
    return {row[0] for row in snapshot["tables"]}


def _preserved(snapshot: dict, later: dict, allowed_new_triggers: frozenset[str] = frozenset()) -> None:
    names = _names(snapshot)
    for key, rows in snapshot.items():
        if key == "functions":
            old_functions = {row[0] for row in rows}
            assert rows == [row for row in later[key] if row[0] in old_functions], key
            continue
        assert rows == [
            row for row in later[key] if row[0] in names and not (key == "triggers" and row[1] in allowed_new_triggers)
        ], key


def _identity(engine: Engine) -> dict:
    with engine.connect() as connection:
        connection.exec_driver_sql("SET TRANSACTION READ ONLY")
        return {
            table: connection.scalar(text(f"SELECT to_jsonb(r) FROM {table} r WHERE id=:id"), {"id": TEST_ID})
            for table in ("tenants", "user_accounts", "projects", "enterprise_workspaces", "workspace_module_settings")
        }


def _binding(engine: Engine) -> dict:
    with engine.connect() as connection:
        connection.exec_driver_sql("SET TRANSACTION READ ONLY")
        return connection.scalar(
            text("SELECT to_jsonb(r) FROM operational_project_bindings r WHERE id=:id"), {"id": TEST_ID}
        )


def _insert_sentinel(engine: Engine) -> None:
    """Non-14 canonical and legacy identities existing before the O1 wave."""
    with engine.begin() as connection:
        for sql in (
            """
            INSERT INTO tenants (id,name,slug,base_currency)
            VALUES (:id,'O2B history test tenant','o2b-history-test','COP'),
                   (:id + 1,'O2B other test tenant','o2b-history-other','COP')
            """,
            """
            INSERT INTO user_accounts (id,tenant_id,email,full_name,title,status)
            VALUES (:id,:id,'history@example.invalid','Historical fixture','Test actor','active'),
                   (:id + 1,:id + 1,'other@example.invalid','Other fixture','Test actor','active')
            """,
            """
            INSERT INTO projects (id,tenant_id,code,name,phase,currency)
            VALUES (:id,:id,'CLOSE-HISTORY','Historical fixture project','Execution','COP')
            """,
            """
            INSERT INTO enterprise_workspaces
                (id,tenant_id,workspace_type_code,code,external_key,record_code,name,status,
                 defaults_json,sort_order,version,created_by_user_id,created_at,updated_at)
            VALUES (:id,:id,'project','CLOSE-HISTORY','test-close-history','CLOSE-HISTORY','Historical project',
                    'active','{}',0,3,:id,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP),
                   (:id + 1,:id,'project','CLOSE-OTHER','test-close-other','CLOSE-OTHER','Other project',
                    'active','{}',1,1,:id,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)
            """,
            """
            INSERT INTO workspace_module_settings
                (id,tenant_id,workspace_id,module_key,enabled,version,updated_by_user_id,updated_at)
            VALUES (:id,:id,:id,'scope',true,7,:id,CURRENT_TIMESTAMP)
            """,
        ):
            connection.execute(text(sql), {"id": TEST_ID})


@pytest.fixture(scope="module")
def migrated_history():
    supplied = os.getenv("PYPMIS_O2B_CLOSE_MIGRATION_URL")
    if not supplied:
        pytest.skip("Dedicated physically fresh O2B.CLOSE PostgreSQL required")
    assert os.getenv("PYPMIS_O2B_CLOSE_FIXTURE") == "disposable-only"
    url = make_url(supplied)
    assert (url.drivername, url.host, url.port, url.username) == (
        "postgresql+psycopg",
        "127.0.0.1",
        5558,
        "o2b_close_migration",
    )
    assert url.database in {
        "o2b_close_migration",
        "o2b_close_migration_diagnostic",
        "o2b_close_migration_diagnostic_0078",
    }
    engine = create_engine(url)
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    scripts = ScriptDirectory.from_config(config)
    assert scripts.get_heads() == [CLOSE]
    chain = list(reversed([rev.revision for rev in scripts.walk_revisions(base="base", head=CLOSE)]))
    assert chain[0] == "20260505_0001"
    assert chain[-11:] == [PRE_O1, *O1, O2A, O2B, CLOSE]
    events: list[dict] = []
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("DATABASE_URL", supplied)
        patch.setenv("AUTO_CREATE_SCHEMA", "false")
        patch.setenv("SEED_DEMO_DATA", "false")
        get_settings.cache_clear()
        try:
            with engine.begin() as connection:
                assert connection.execute(text("SELECT current_database(), current_user")).one() == (
                    url.database,
                    "o2b_close_migration",
                )
                postgres_version = connection.scalar(text("SHOW server_version"))
                assert connection.scalar(text("SELECT count(*) FROM pg_tables WHERE schemaname='public'")) == 0
                assert connection.scalar(text("SELECT to_regclass('public.alembic_version')")) is None
                # The SQL file is frozen from Git, contains no data, and is never used for normal startup.
                sql = BOOTSTRAP.read_text(encoding="utf-8")
                assert hashlib.sha256(sql.encode()).hexdigest() == BOOTSTRAP_SHA256
                connection.exec_driver_sql(sql)
                assert connection.scalar(text("SELECT count(*) FROM pg_tables WHERE schemaname='public'")) == 39
                assert connection.scalar(text("SELECT to_regclass('public.alembic_version')")) is None

            def upgrade(target: str) -> dict:
                command.upgrade(config, target)
                with engine.connect() as connection:
                    expected = CLOSE if target == "head" else target
                    assert connection.scalars(text("SELECT version_num FROM alembic_version")).all() == [expected]
                schema = _catalog(engine)
                events.append({"action": "upgrade", "revision": expected, "tables": len(schema["tables"])})
                return schema

            pre_o1 = upgrade(PRE_O1)
            _insert_sentinel(engine)
            identity = _identity(engine)
            assert all(identity.values()) and identity["enterprise_workspaces"]["version"] == 3
            for stage in O1:
                post_o1 = upgrade(stage)
                assert _identity(engine) == identity
                if stage == O1[0]:
                    with engine.begin() as connection:
                        connection.execute(
                            text("""
                                INSERT INTO operational_project_bindings
                                  (id,tenant_id,project_workspace_id,legacy_project_id,status,revision,version,source,
                                   reason,created_by,validated_by,created_at,effective_from)
                                VALUES (:id,:id,:id,:id,'ACTIVE',1,1,'migration-fixture','Preserve test identity',
                                        :id,:id,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)
                            """),
                            {"id": TEST_ID},
                        )
                    binding = _binding(engine)
                assert _binding(engine) == binding
            post_o2a = upgrade(O2A)
            post_o2b = upgrade(O2B)
            head = upgrade("head")
            yield MigrationRun(
                engine,
                config,
                events,
                len(chain),
                postgres_version,
                pre_o1,
                post_o1,
                post_o2a,
                post_o2b,
                head,
                identity,
                binding,
            )
        finally:
            get_settings.cache_clear()
            engine.dispose()
    get_settings.cache_clear()


def test_fresh_base_to_o2b_and_preserved_canonical_identity(migrated_history):
    run = migrated_history
    assert run.root_count == 78
    assert _identity(run.engine) == run.identity
    assert _binding(run.engine) == run.binding
    assert run.identity["enterprise_workspaces"]["id"] == TEST_ID != 14
    # O1 revisions are additive; only the scoped triggers are installed on existing tables.
    assert {
        row[1] for row in run.post_o1["triggers"] if row[0] in _names(run.pre_o1) and row not in run.pre_o1["triggers"]
    } == O1_PROFILE_TRIGGERS
    _preserved(run.pre_o1, run.post_o1, O1_PROFILE_TRIGGERS)
    _preserved(run.post_o1, run.post_o2a, frozenset({"tr_engineering_profile_o2a"}))
    _preserved(run.post_o2a, run.post_o2b, frozenset({"tr_procurement_profile_o2b"}))
    _preserved(run.post_o2b, run.head)


def test_frozen_schema_indexes_foreign_keys_uniqueness_versions_and_guards(migrated_history):
    run = migrated_history
    names = _names(run.head)
    assert names - _names(run.post_o2b) == {ADOPTIONS}
    assert _names(run.post_o2b) - _names(run.post_o2a) == PROCUREMENT_MIGRATION_TABLE_NAMES
    assert _names(run.post_o2a) - _names(run.post_o1) == ENGINEERING_MIGRATION_TABLE_NAMES
    assert {
        "operational_project_bindings",
        "scope_items",
        "scope_plan_items",
        "schedule_versions",
        "awp_work_packages",
        "cost_control_accounts",
        "progress_measurements",
        "forecast_versions",
        "contracts",
        "purchase_orders",
    } <= names
    assert len(run.head["tables"]) == len(names)
    assert all(row[4] for row in run.head["constraints"])
    assert all(row[3] and row[4] for row in run.head["indexes"])
    procurement = PROCUREMENT_MIGRATION_TABLE_NAMES
    assert sum(row[2] == "f" and row[0] in procurement for row in run.head["constraints"]) == 151
    assert sum(row[2] == "u" and row[0] in procurement for row in run.head["constraints"]) == 31
    assert any(row[1] == "fk_proc_po_current_revision" and row[2] == "f" for row in run.head["constraints"])
    assert {
        row[0] for row in run.head["triggers"] if row[2].endswith("o2b_procurement_record_guard()") and row[3] == "O"
    } == procurement
    assert PROFILE_TRIGGERS <= {row[1] for row in run.head["triggers"] if row[0] == "admin_configurations"}
    assert any(
        row[0] == ADOPTIONS
        and row[1] == "tr_operational_procurement_adoptions_o2b_close"
        and row[2].endswith("o2b_consumer_adoption_guard()")
        and row[3] == "O"
        for row in run.head["triggers"]
    )
    assert any(
        row[0] == ADOPTIONS and row[1] == "uq_op_proc_adoption_stream" and row[2] == "u"
        for row in run.head["constraints"]
    )
    assert sum(row[0] == ADOPTIONS and row[2] == "f" for row in run.head["constraints"]) == 6
    for table in (
        "enterprise_workspaces",
        "operational_project_bindings",
        "schedule_versions",
        "awp_work_packages",
        "engineering_revisions",
        "procurement_purchase_orders",
        "procurement_material_items",
        ADOPTIONS,
    ):
        assert (table, "version", "integer", True, None) in run.head["columns"]


def test_scope_and_append_only_guards_execute_on_postgresql(migrated_history):
    def rejected(connection, sql, params, code, detail=None):
        with pytest.raises(DBAPIError) as error, connection.begin_nested():
            connection.execute(text(sql), params)
        assert error.value.orig.sqlstate == code
        if detail:
            assert detail in error.value.orig.diag.message_primary

    insert_item = """
        INSERT INTO procurement_material_items
          (id,tenant_id,project_workspace_id,material_code,description,specification,uom,category,version,created_by,created_at)
        VALUES (:row,:tenant,:workspace,'STEEL-TEST','Synthetic material','Test only','EA','STEEL',1,:actor,CURRENT_TIMESTAMP)
    """
    params = {"row": TEST_ID, "tenant": TEST_ID, "workspace": TEST_ID, "actor": TEST_ID}
    with migrated_history.engine.connect() as connection, connection.begin() as transaction:
        connection.execute(text(insert_item), params)
        rejected(
            connection,
            insert_item,
            {**params, "row": TEST_ID + 1, "tenant": TEST_ID + 1, "actor": TEST_ID + 1},
            "P0001",
            "same tenant",
        )
        rejected(connection, insert_item, {**params, "row": TEST_ID + 1}, "23505")
        rejected(
            connection,
            """
            INSERT INTO procurement_material_requirements
              (id,tenant_id,project_workspace_id,requirement_code,material_item_id,required_quantity,uom,
               source_reference_json,version,created_by,created_at)
            VALUES (:row,:tenant,:other_workspace,'REQ-TEST',:row,1,'EA','{}',1,:actor,CURRENT_TIMESTAMP)
            """,
            {**params, "other_workspace": TEST_ID + 1},
            "P0001",
            "outside tenant or Project",
        )
        rejected(
            connection,
            "UPDATE procurement_material_items SET description='Changed' WHERE id=:row",
            params,
            "P0001",
            "fact is immutable",
        )
        rejected(
            connection,
            "DELETE FROM procurement_material_items WHERE id=:row",
            params,
            "P0001",
            "history cannot be deleted",
        )
        rejected(
            connection,
            "UPDATE workspace_module_settings SET updated_by_user_id=0 WHERE id=:row",
            params,
            "23503",
        )
        transaction.rollback()


def test_o2b_and_o2a_roundtrip_keeps_o1_and_records_evidence(migrated_history):
    run = migrated_history
    command.downgrade(run.config, O1[-1])
    after_down = _catalog(run.engine)
    assert after_down == run.post_o1
    assert _identity(run.engine) == run.identity and _binding(run.engine) == run.binding
    run.events.append({"action": "downgrade", "revision": O1[-1], "tables": len(after_down["tables"])})
    command.upgrade(run.config, "head")
    after_up = _catalog(run.engine)
    assert after_up == run.head
    with run.engine.connect() as connection:
        assert connection.scalars(text("SELECT version_num FROM alembic_version")).all() == [CLOSE]
    assert _identity(run.engine) == run.identity and _binding(run.engine) == run.binding
    run.events.append({"action": "re-upgrade", "revision": CLOSE, "tables": len(after_up["tables"])})

    artifact = os.getenv("PYPMIS_O2B_CLOSE_MIGRATION_EVIDENCE")
    if artifact:
        target = Path(artifact).resolve()
        qa = BACKEND.parent / "outputs" / ".qa"
        assert target.is_relative_to(qa)
        assert target.relative_to(qa).parts[0].startswith("wave-o2b-close-")
        assert target.suffix == ".json"
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("x", encoding="utf-8") as output:
            json.dump(
                {
                    "result": "PASS",
                    "source_origin": ORIGIN,
                    "historical_bootstrap_sha256": BOOTSTRAP_SHA256,
                    "fresh_bootstrap_tables": 39,
                    "database_name": run.engine.url.database,
                    "postgres_version": run.postgres_version,
                    "alembic_revisions": run.root_count,
                    "pre_o1": PRE_O1,
                    "o2a": O2A,
                    "o2b": O2B,
                    "head": CLOSE,
                    "events": run.events,
                    "catalog_counts": {key: len(rows) for key, rows in run.head.items()},
                    "catalog_head_sha256": _sha256(run.head),
                    "catalog_reupgrade_sha256": _sha256(after_up),
                    "canonical_identity_sha256": _sha256(run.identity),
                    "operational_binding_sha256": _sha256(run.binding),
                    "observed_at_utc": datetime.now(UTC).isoformat(),
                },
                output,
                indent=2,
            )
            output.write("\n")
