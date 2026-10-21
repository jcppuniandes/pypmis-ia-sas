# ADR 95: Owner vs Contractor applicability

Status: IMPLEMENTED_O1A_AUTHORIZATION_ONLY

Requirement alias: ADR-O-010

Date: 2026-10-19

## Context

Existing route adapters and policy requirements already distinguish strategic decision, contract award and direct authorization.

## Proposed decision

Governance Model is independent of Project Type. Reuse canonical creation/initialization/activation and route policies for CAPITAL_OWNER, CONTRACTOR_DELIVERY and DIRECT_INTERNAL; do not impose Capital Owner sequence by default on other legitimate routes.

## Consequences and implementation boundary

Operational domain applicability is tailored mandatory/optional/conditional/not-applicable; authorization/conditions remain upstream, no copied local FID.

O1A implements a read-only authorization resolver for all three governance models. CAPITAL_OWNER consumes current decision/Post-FID authority and conditions. CONTRACTOR_DELIVERY consumes contract/NTP/mobilization authority; DIRECT_INTERNAL consumes sponsor/internal authorization. Neither non-owner route fabricates FID/Funding/FEL requirements. ACTIVE never grants commitment authority. Full downstream domain applicability remains future work. No business approval is recorded by this ADR.

## Evidence inspected (not tests executed)

- `backend/app/modules/project_creation/governance.py:25`
- `backend/app/modules/project_creation/governance.py:53`
- `backend/app/modules/project_creation/governance.py:85`
- `backend/app/modules/project_creation/governance.py:122`
- `backend/tests/test_post_fid_governance_gate07l.py:124`
