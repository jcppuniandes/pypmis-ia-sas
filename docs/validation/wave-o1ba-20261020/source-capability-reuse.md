# O1B A source capability reuse inspection

Inspection date 20 October 2026. This is an implementation inventory, not a
declaration of downstream Schedule, Cost, Progress or AWP completion.

| Existing capability | Classification | O1B A use and boundary |
|---|---|---|
| `frontend/src/components/BimIfcModelViewer.tsx` | REUSE and EXTEND | The existing web-ifc and Three viewer continues to own IFC geometry, selection, properties and visibility. Feature adapters supply a canonical Scope source and immutable version; source geometry is not rewritten. |
| `backend/app/services/ifc_geometry_converter.py:11` | REUSE | The pinned IFCOpenShell engine already converts original IFC geometry. O1B A imports the same installed engine for typed source extraction; it does not introduce a second rendering engine or regenerate physical fragments for logical splits. |
| `backend/app/services/quantity_takeoff.py:80` IFC product class catalogue | REUSE | The existing supported product classifications seed Scope importer support. Other typed IFC products are retained with an explicit unsupported mapping warning, never silently discarded. |
| `backend/app/services/quantity_takeoff.py:629` shared strings and `:640` worksheet token readers | REUSE and EXTEND | XLSX literal tokens use the existing reader. Scope adds workbook relationship resolution, actual sheet and row lineage, field mapping, duplicate/header/parent/nature/unit validation, bounded ZIP expansion and formula/external-content rejection. |
| `backend/app/services/bim_models.py:49` legacy BIM registry | RESERVED | Existing records require legacy `projects.id`. Canonical Scope model versions use `enterprise_workspaces.id` and immutable source bytes/hash instead of creating a hidden legacy Project. Existing legacy models and uploads remain intact. |
| `backend/app/services/bim_models.py:556` and `quantity_takeoff.py:1058` regex IFC indexers | RESERVED | These remain compatibility indexers for legacy consumers. Governed promotion uses actual IFCOpenShell parsing, not a partial name/regex identity approximation. No legacy indexer was removed. |
| `backend/app/domain/models.py:183` QuantityTakeoffRun and `:282` QuantityTakeoffLine | RESERVED | They are quantity extraction and legacy control/APU mapping records, not governed canonical Scope masters. Scope items, revisions and immutable approved baselines do not overwrite them. |
| `backend/app/services/bim_quantity_rules.py` | RESERVED | Existing constructive quantity rules remain available to legacy BIM/APU. Scope preserves declared source quantity and source units without silently applying a rule or converting quantities. |
| `backend/app/services/colombia_apu_catalog.py:84` and `frontend/src/components/BimApuReviewPanel.tsx` | RESERVED | Existing APU integration remains unchanged. Excel APU/WBS/CBS/package references are retained as inactive future mapping metadata, not activated Cost authority. |
| `backend/app/services/bim_geometry_quantities.py:36` | RESERVED | Existing geometric quantity calculation is not silently invoked by source import or Scope baseline approval. Source quantities distinguish published IFC quantities from explicit object count. |
| Existing AWP work packages and legacy Schedule mapping | RESERVED | Future Plan Item mapping contracts retain source references without enforcing AWP, creating schedule activities, calculating CPM or moving WBS/CBS ownership. |
| Existing PlanItem, ScopeItem or ExecutionStrategy canonical implementation | No compatible master found in the inspected baseline | Search of backend application and frontend source outside the new feature found no compatible canonical implementation. New domain-owned records are additive; existing legacy takeoff entities are not renamed into a competing authority. |

## Source parser guarantees

IFC source SHA256 is computed from the original upload bytes. IFC GUID is the
only identity basis across versions; ExpressID is local to a model version.
Missing/duplicate/invalid GUIDs and unresolvable units block acceptance.
Properties, typed quantities, materials, classification and spatial context are
extracted through IFCOpenShell. Semantic geometry and placement hashes ignore
version-local STEP numbers. A mapping to a lost GUID blocks promotion. Object
loss/growth and unsupported products remain visible review findings.

Excel import validates literal XLSX or UTF8 CSV without needing any IFC model.
Source file hash, actual worksheet, physical row number, supplied source row ID,
raw source values and row hash remain available. A preview is not an approved
Scope baseline. Repeating a parser call is deterministic and has no write or
approval side effects; HTTP command idempotency belongs to the governed service.

The parsers neither update source IFC bytes nor execute links/formulas/macros.
No files were deleted or migrated by this inspection.
