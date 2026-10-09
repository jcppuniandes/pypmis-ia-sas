# AWP Draft Packaging Agent Design

## Purpose

Extend the existing AI Control Auditor so it can convert an AWP packaging proposal into editable draft work packages for review.

## Reference Pattern

The example PDF `272_2_v3-1_vol2.pdf` describes AWP as a hierarchy from construction area to construction work package and then installation work package. The useful rules for this app are:

- Group work by construction area/WBS, discipline and path of construction.
- CWPs must cover the area scope without overlap.
- IWPs inherit the CWP boundary and carry readiness constraints before field release.
- Packages should stay controlled by revision/history and human approval.

## Scope

Add a backend endpoint and UI action:

```text
POST /api/v1/projects/{project_id}/agents/control-audit/awp-draft-packages
```

The endpoint creates missing draft AWP packages from current project control data:

- `CWA`: one construction work area per WBS area when missing.
- `CWP`: one construction package per control account/discipline when missing.
- `IWP`: one installation package under each CWP when missing.
- Initial constraints: engineering documents, materials, safety/quality, permits, and recost/funding readiness.

## Safety

- No existing package is overwritten.
- Existing codes are skipped, not updated.
- Created packages use `readiness_status="constraint_review"` and `progress_percent=0`.
- The action does not approve baseline, release work, close constraints, or change forecast/funding.
- The run is persisted as a `ControlAgentRun` with `ControlAgentFinding` rows for created and skipped items.

## User Experience

In Integrated Control, the AI Control Auditor panel adds `Create Draft Packages`. After running it, the UI shows the run summary and refreshes project data so the new packages appear under Work Packages.
