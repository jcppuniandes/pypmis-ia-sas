# Validation Note 63 — Gate 07M-FID full-stack revalidation

## Status

Accepted for the `CAPITAL_OWNER / PYP-FFA` strategic path after disposable PostgreSQL, browser, regression, hash-chain and cleanup validation.

## Context

Gate 07M-EVID added `BUSINESS_CASE_READINESS` and `ECONOMIC_FINANCIAL_READINESS` as blocking Class A governed evidence for PYP-FFA. The release therefore needs one reproducible path from a commercial Project through Business Case, FIN, Gate 07J, Gate 07K FID and Gate 07L without adding business functionality or changing Alembic head `20260902_0058`.

## Decision

- Reuse all existing domain services. Direct ORM seeding is limited to identities, the upstream proposal and test-only configurations that have no public factory.
- Run the canonical USD 100,000,000 Project only in disposable databases. Project ID 14 and the persistent application database are read-only validation subjects.
- Keep the five-source funding lineage explicit: sponsor equity 20M, external-investor equity 15M, senior bank loan 50M, development-bank debt 10M and grant 5M.
- Reuse policy `787`, revision `1`, effective at `2026-09-03T12:34:44.035309` interpreted as UTC when the value is timezone-naive.
- Rank same-scope policies by effective timestamp and then revision. Revision numbers cannot order independent configuration identities.
- Treat a completed READY Business Case revision that points back to the exact FIN id/version/hash as a valid forward bridge. This closes the governed BC↔FIN cycle without mutating either completed revision.
- Re-evaluate the referenced Funding Readiness against current governed sources whenever FIN currentness is requested. A suspended source makes live FIN evidence stale but leaves frozen Gate 07J and DECIDED Gate 07K snapshots immutable.
- Canonicalize the authorized FID amount to two decimal places before hashing so SQLite and PostgreSQL round trips yield the same decision hash.

## Validation architecture

`backend/tests/test_gate07m_fid_e2e.py` builds a single commercial Project through real services, writes auditable ids/hashes/timings, validates GO/FID/full-funds/no-auto-activation and exercises a real funding-stale negative plus recovery. `docker-compose.gate07m-fid-e2e.yml` supplies PostgreSQL 16, real migrations, isolated regression phases and a dedicated API/frontend profile. `frontend/e2e/gate07m-fid-real-stack.spec.ts` runs Chromium against those real localhost services with no request routing or mocked core providers.

## Guardrails

- No new domain model, migration, provider, financial formula, Gate 07J policy rule, Gate 07K semantic or Gate 07L semantic.
- No procurement, contracting, commitment, payment, accounting, treasury, NTP, execution or operations record.
- No automatic Project initialization or activation after FID.
- Test mutations remain inside the disposable `gate07e` PostgreSQL database and are removed with `docker compose down -v`.

## Consequences

The strategic path has a reproducible release gate and catches three previously latent contract defects: BC↔FIN mutual-current linkage, published-policy effective ordering, and FIN staleness after governed funding changes. Historical decision packages remain valid and immutable while new preparations correctly block on stale evidence.

## Final state

`GATE07M_FID_E2E_RELEASE_VALIDATED`  
`NEW_PYP_FFA_FID_PATH_FULL_STACK_VALIDATED`  
`NEXT = READY_TO_ENTER_OPERATIONAL_MACROPROCESSES_REVIEW`
