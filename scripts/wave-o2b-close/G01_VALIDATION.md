# O2B.CLOSE — functional regression runners

Run from the repository root with `backend/.venv/Scripts/python.exe`. Use the final frozen Alembic revision (shown below as `20261111_0078`) and a new attempt label on every retry. The runners refuse to replace previous artifacts and never use the default application database.

## PostgreSQL functional regression

```powershell
backend/.venv/Scripts/python.exe scripts/wave-o2b-close/postgres_regression.py o1 final-a --expected-head 20261111_0078
backend/.venv/Scripts/python.exe scripts/wave-o2b-close/postgres_regression.py o2a final-a --expected-head 20261111_0078
backend/.venv/Scripts/python.exe scripts/wave-o2b-close/postgres_regression.py o2b final-a --expected-head 20261111_0078
```

The dedicated Compose `db` services use PostgreSQL 16 on loopback ports 5550 (`o1c`), 5552 (`o2a`) and 5555 (`o2b`). Each result is in `outputs/.qa/wave-o2b-close-20261111/postgres-regression/<suite>/<attempt>/`. A pass requires every selected module to execute, no skips, no failures, a matching database head and unchanged source. Exact historical migrations and downgrade tests are deliberately not run by this launcher; they need a physically fresh migration database.

## Chromium

```powershell
backend/.venv/Scripts/python.exe scripts/wave-o2b-close/chromium_gate.py prepare o2a final-a --expected-head 20261111_0078
backend/.venv/Scripts/python.exe scripts/wave-o2b-close/chromium_gate.py build o2a final-a --expected-head 20261111_0078
# Start each of the following two commands in its own terminal and leave it running.
backend/.venv/Scripts/python.exe scripts/wave-o2b-close/chromium_gate.py serve-api o2a final-a --expected-head 20261111_0078
backend/.venv/Scripts/python.exe scripts/wave-o2b-close/chromium_gate.py serve-frontend o2a final-a --expected-head 20261111_0078
# Run this when the two HTTP services respond.
backend/.venv/Scripts/python.exe scripts/wave-o2b-close/chromium_gate.py validate o2a final-a --expected-head 20261111_0078
```

Repeat with `o2b` for Procurement. Use the separate Compose `browser-db` services, not the functional regression or historical migration databases. O2A uses DB 5554, API 8859 and frontend 5519; O2B uses DB 5557, API 8860 and frontend 5520. Both bind to loopback. Each `prepare` creates a new synthetic tenant and leaves the original O2A/O2B browser fixtures unchanged.

Results are in `outputs/.qa/wave-o2b-close-20261111/chromium/<wave>/<attempt>/`. Each wave runs its unchanged lifecycle UAT plus the dedicated Project context smoke. Keep private fixture JSON, attachments, unredacted trace archives and raw logs out of published artifacts. A failure stays in its original attempt; investigate it before preparing a new synthetic tenant. Do not combine artifacts from different attempts to claim a pass.
