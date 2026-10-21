# Artifact contract — Operational master architecture

Date: 2026-10-19. Scope: architecture and documentation only.

## Deliverables and authority

Create exactly two Word documents and one Excel workbook under
`outputs/operational-master-architecture-20261019/`. The Master Architecture is
the technical report requested by the user; the second Word is the implementation
roadmap. The workbook supplies the twelve exact matrices requested in section 60.
No product module, navigation change, database command, migration, live rollout,
commit or push is authorized by this architecture increment. Strategic business
signoff remains pending. Design proposals do not constitute approvals.

## Source and template selection

No template-picker tool is available. Retain the existing P&Pmis corporate Word
visual system from the unchanged report:
`outputs/business-uat-signoff-20261018/P&Pmis_Informe_Tecnico_Business_UAT_Signoff_20261018.docx`.
Source SHA256: `475c1674cf398f005e3239df01cf84c3e649951d8a45b3056d9f0fddf6c7f3a7`.
The prior source QA has eight rendered pages. Review the reference's actual
native styles, logo, section geometry, table treatment and footer before use.
Only the body and footer date may change in the new files; preserve the remaining
17 ZIP parts byte-for-byte. Never modify the reference.

Retain Letter portrait, one section, 0.7201-inch margins, 0.3-inch header and
0.35-inch footer; Aptos 11 body, 24 title, 12 subtitle, 15 H1, 12 H2; native logo;
navy #17324D table headers, white 9.5-point header text, 9.5-point body, gray borders,
intentional column widths, repeated header row, no exact fixed row height. Body
may reflow for the new subject. New issue date is 19 October 2026. Keep the PAGE
field and export read-only with Word for an accurate PDF preview; never save the
source using Word automation. Two reports share this source-derived style.

Master report must contain all 24 chapters in prompt section 58. Roadmap contains
four waves, O1A/B/C prerequisites, 25-domain scoring, entry/exit, risk, reuse,
relative complexity, release constraints and exactly one next increment.
No copied strategic signoff narrative presented as new operational completion.

## Data and evidence contract

Canonical data: `docs/architecture/operational/architecture-data.json`, generated
from independently inspected backend/frontend/procurement evidence. Each target
domain remains labelled proposed, with current capability explicitly separate.
56 BE/FE/PH rows are evidence units at different granularity, not a function count.
All 32 acceptance checks are architecture-defined checks, not runtime test passes.
No product tests or browser UAT are claimed run in this increment.

Workbook must use Artifact Tool only for authoring, export, reimport, render and
formula simulation; OpenXML may be read independently for structural QA. Exact
12 tab names, no extra tabs. Proposed scoring weights sum to one. Integer 1–5
scores; complexity/model risk/coupling penalize. Missing/invalid input must not
silently become zero. User urgency stays neutral 3. DAG/security prerequisites
override numerical score; no invented business priority or approved dates.

## Verification and private files

Run authoring markers immediately before first Word/Excel authoring. Use bundled
runtime only; no global package installation. Bundled LibreOffice is unavailable;
native hidden read-only Word export plus canonical packaged render_docx.py adapter
will be used, with DOCX→PDF→PNG SHA provenance. Private previews and intermediate
files stay under ignored `outputs/.qa/operational-master-architecture-20261019/`.
Review every final Word page and every workbook sheet/range image. Audit Word
sections/styles/a11y, template preservation, source hash, workbook formulas and
edge cases, all evidence references, DAG and 32 architecture criteria.

Capture SHA256 of all 860 tracked product files before and after documentation.
Final-scope audit must prove unchanged HEAD, prompt and product hashes. New ADRs
follow global numeric convention 86–97 and remain PROPOSED_DESIGN. No deletions:
SAFE_TO_REMOVE is zero. Deliver only the three requested Office artifacts, with
concise Spanish summary and exactly one next implementation prompt.
