# Gate 04H - Workspace Revision Manager Operational Hardening

The implementation and CI harness are present, but the local heavy-test gate is intentionally not claimed as passed.

Preflight found less than the required 10 GB of free disk space. The required PostgreSQL E2E, full regression and snapshot benchmark were therefore not executed. Restore at least 10 GB, then run:

```text
docker compose -f docker-compose.gate04h.yml up --build --abort-on-container-exit --exit-code-from gate04h-test
```

The environment uses PostgreSQL 16 on `tmpfs`, applies Alembic to head, runs the complete transactional/concurrency/SoD suite, writes the benchmark artifacts, and is destroyed without touching persistent local volumes.

Current final state: `HARDENING_REQUIRED`.
