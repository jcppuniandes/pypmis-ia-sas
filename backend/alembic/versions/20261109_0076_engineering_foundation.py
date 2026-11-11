"""Canonical Engineering records, additive only.

Revision ID: 20261109_0076
Revises: 20261106_0075
"""

import sqlalchemy as sa
from alembic import op

revision = "20261109_0076"
down_revision = "20261106_0075"
branch_labels = None
depends_on = None

# Frozen from the initial schema. Do not import live application ORM here.
TABLES = (
    (
        "engineering_design_packages",
        (
            ("code", "String", (120,), False, False, ()),
            ("title", "String", (300,), False, False, ()),
            ("description", "Text", (), False, False, ()),
            ("status", "String", (24,), False, False, ()),
            ("updated_by", "Integer", (), False, False, ("user_accounts.id",)),
            ("updated_at", "DateTime", (), False, False, ()),
            ("id", "Integer", (), False, True, ()),
            ("tenant_id", "Integer", (), False, False, ("tenants.id",)),
            ("project_workspace_id", "Integer", (), False, False, ("enterprise_workspaces.id",)),
            ("version", "Integer", (), False, False, ()),
            ("created_by", "Integer", (), False, False, ("user_accounts.id",)),
            ("created_at", "DateTime", (), False, False, ()),
        ),
        (("uq_eng_design_package_code", ("tenant_id", "project_workspace_id", "code")),),
        (("ck_eng_design_package_status", "status IN ('DRAFT','REVIEWED','ISSUED','CANCELLED')"),),
        (
            ("ix_engineering_design_packages_project_workspace_id", ("project_workspace_id",), False, None),
            ("ix_engineering_design_packages_tenant_id", ("tenant_id",), False, None),
        ),
    ),
    (
        "engineering_deliverables",
        (
            ("code", "String", (120,), False, False, ()),
            ("title", "String", (300,), False, False, ()),
            ("discipline", "String", (80,), False, False, ()),
            ("deliverable_type", "String", (80,), False, False, ()),
            ("design_package_id", "Integer", (), True, False, ("engineering_design_packages.id",)),
            ("description", "Text", (), False, False, ()),
            ("responsible_party", "String", (200,), False, False, ()),
            ("area", "String", (150,), False, False, ()),
            ("planned_issue_date", "Date", (), True, False, ()),
            ("current_forecast_date", "Date", (), True, False, ()),
            ("source_reference", "String", (1000,), False, False, ()),
            ("configuration_id", "Integer", (), False, False, ("admin_configurations.id",)),
            ("configuration_hash", "String", (64,), False, False, ()),
            ("updated_by", "Integer", (), False, False, ("user_accounts.id",)),
            ("updated_at", "DateTime", (), False, False, ()),
            ("id", "Integer", (), False, True, ()),
            ("tenant_id", "Integer", (), False, False, ("tenants.id",)),
            ("project_workspace_id", "Integer", (), False, False, ("enterprise_workspaces.id",)),
            ("version", "Integer", (), False, False, ()),
            ("created_by", "Integer", (), False, False, ("user_accounts.id",)),
            ("created_at", "DateTime", (), False, False, ()),
        ),
        (("uq_eng_deliverable_code", ("tenant_id", "project_workspace_id", "code")),),
        (),
        (
            ("ix_eng_deliverable_register", ("tenant_id", "project_workspace_id", "discipline", "id"), False, None),
            ("ix_engineering_deliverables_design_package_id", ("design_package_id",), False, None),
            ("ix_engineering_deliverables_project_workspace_id", ("project_workspace_id",), False, None),
            ("ix_engineering_deliverables_tenant_id", ("tenant_id",), False, None),
        ),
    ),
    (
        "engineering_revisions",
        (
            ("deliverable_id", "Integer", (), False, False, ("engineering_deliverables.id",)),
            ("revision_code", "String", (80,), False, False, ()),
            ("revision_sequence", "Integer", (), False, False, ()),
            ("supersedes_revision_id", "Integer", (), True, False, ("engineering_revisions.id",)),
            ("status", "String", (24,), False, False, ()),
            ("purpose_of_issue", "String", (80,), False, False, ()),
            ("description", "Text", (), False, False, ()),
            ("planned_issue_date", "Date", (), True, False, ()),
            ("forecast_issue_date", "Date", (), True, False, ()),
            ("document_ref_json", "JSON", (), False, False, ()),
            ("document_hash", "String", (64,), False, False, ()),
            ("content_hash", "String", (64,), False, False, ()),
            ("configuration_id", "Integer", (), False, False, ("admin_configurations.id",)),
            ("configuration_hash", "String", (64,), False, False, ()),
            ("prepared_by", "Integer", (), False, False, ("user_accounts.id",)),
            ("updated_by", "Integer", (), False, False, ("user_accounts.id",)),
            ("updated_at", "DateTime", (), False, False, ()),
            ("checked_by", "Integer", (), True, False, ("user_accounts.id",)),
            ("checked_at", "DateTime", (), True, False, ()),
            ("approved_by", "Integer", (), True, False, ("user_accounts.id",)),
            ("approved_at", "DateTime", (), True, False, ()),
            ("id", "Integer", (), False, True, ()),
            ("tenant_id", "Integer", (), False, False, ("tenants.id",)),
            ("project_workspace_id", "Integer", (), False, False, ("enterprise_workspaces.id",)),
            ("version", "Integer", (), False, False, ()),
            ("created_by", "Integer", (), False, False, ("user_accounts.id",)),
            ("created_at", "DateTime", (), False, False, ()),
        ),
        (
            ("uq_eng_revision_code", ("deliverable_id", "revision_code")),
            ("uq_eng_revision_sequence", ("deliverable_id", "revision_sequence")),
            ("uq_eng_revision_successor", ("supersedes_revision_id",)),
        ),
        (
            ("ck_eng_revision_sequence", "revision_sequence > 0"),
            ("ck_eng_revision_status", "status IN ('DRAFT','UNDER_REVIEW','CHANGES_REQUESTED','APPROVED','REJECTED')"),
        ),
        (
            ("ix_engineering_revisions_deliverable_id", ("deliverable_id",), False, None),
            ("ix_engineering_revisions_project_workspace_id", ("project_workspace_id",), False, None),
            ("ix_engineering_revisions_tenant_id", ("tenant_id",), False, None),
        ),
    ),
    (
        "engineering_reviews",
        (
            ("revision_id", "Integer", (), False, False, ("engineering_revisions.id",)),
            ("round_number", "Integer", (), False, False, ()),
            ("status", "String", (24,), False, False, ()),
            ("decision", "String", (24,), True, False, ()),
            ("submitted_hash", "String", (64,), False, False, ()),
            ("reviewer_id", "Integer", (), True, False, ("user_accounts.id",)),
            ("reviewed_at", "DateTime", (), True, False, ()),
            ("decision_by", "Integer", (), True, False, ("user_accounts.id",)),
            ("decision_at", "DateTime", (), True, False, ()),
            ("closed_by", "Integer", (), True, False, ("user_accounts.id",)),
            ("closed_at", "DateTime", (), True, False, ()),
            ("id", "Integer", (), False, True, ()),
            ("tenant_id", "Integer", (), False, False, ("tenants.id",)),
            ("project_workspace_id", "Integer", (), False, False, ("enterprise_workspaces.id",)),
            ("version", "Integer", (), False, False, ()),
            ("created_by", "Integer", (), False, False, ("user_accounts.id",)),
            ("created_at", "DateTime", (), False, False, ()),
        ),
        (("uq_eng_review_round", ("revision_id", "round_number")),),
        (
            ("ck_eng_review_decision", "decision IS NULL OR decision IN ('REVISE_AND_RESUBMIT','APPROVED','REJECTED')"),
            ("ck_eng_review_round", "round_number > 0"),
            (
                "ck_eng_review_status",
                "status IN ('SUBMITTED','UNDER_REVIEW','COMMENTS_ISSUED','REVISE_AND_RESUBMIT','ACCEPTED','APPROVED','REJECTED','CLOSED')",
            ),
        ),
        (
            ("ix_engineering_reviews_project_workspace_id", ("project_workspace_id",), False, None),
            ("ix_engineering_reviews_revision_id", ("revision_id",), False, None),
            ("ix_engineering_reviews_tenant_id", ("tenant_id",), False, None),
        ),
    ),
    (
        "engineering_review_comments",
        (
            ("review_id", "Integer", (), False, False, ("engineering_reviews.id",)),
            ("revision_id", "Integer", (), False, False, ("engineering_revisions.id",)),
            ("discipline", "String", (80,), False, False, ()),
            ("category", "String", (80,), False, False, ()),
            ("severity", "String", (20,), False, False, ()),
            ("text", "Text", (), False, False, ()),
            ("status", "String", (16,), False, False, ()),
            ("response", "Text", (), True, False, ()),
            ("response_by", "Integer", (), True, False, ("user_accounts.id",)),
            ("response_at", "DateTime", (), True, False, ()),
            ("closed_by", "Integer", (), True, False, ("user_accounts.id",)),
            ("closed_at", "DateTime", (), True, False, ()),
            ("id", "Integer", (), False, True, ()),
            ("tenant_id", "Integer", (), False, False, ("tenants.id",)),
            ("project_workspace_id", "Integer", (), False, False, ("enterprise_workspaces.id",)),
            ("version", "Integer", (), False, False, ()),
            ("created_by", "Integer", (), False, False, ("user_accounts.id",)),
            ("created_at", "DateTime", (), False, False, ()),
        ),
        (),
        (
            ("ck_eng_comment_severity", "severity IN ('INFO','MINOR','MAJOR','BLOCKING')"),
            ("ck_eng_comment_status", "status IN ('OPEN','RESPONDED','CLOSED')"),
        ),
        (
            ("ix_engineering_review_comments_project_workspace_id", ("project_workspace_id",), False, None),
            ("ix_engineering_review_comments_review_id", ("review_id",), False, None),
            ("ix_engineering_review_comments_revision_id", ("revision_id",), False, None),
            ("ix_engineering_review_comments_tenant_id", ("tenant_id",), False, None),
        ),
    ),
    (
        "engineering_releases",
        (
            ("revision_id", "Integer", (), False, False, ("engineering_revisions.id",)),
            ("deliverable_id", "Integer", (), False, False, ("engineering_deliverables.id",)),
            ("effective_date", "Date", (), False, False, ()),
            ("released_at", "DateTime", (), False, False, ()),
            ("released_by", "Integer", (), False, False, ("user_accounts.id",)),
            ("release_reference", "String", (1000,), False, False, ()),
            ("release_hash", "String", (64,), False, False, ()),
            ("snapshot_json", "JSON", (), False, False, ()),
            ("id", "Integer", (), False, True, ()),
            ("tenant_id", "Integer", (), False, False, ("tenants.id",)),
            ("project_workspace_id", "Integer", (), False, False, ("enterprise_workspaces.id",)),
            ("version", "Integer", (), False, False, ()),
            ("created_by", "Integer", (), False, False, ("user_accounts.id",)),
            ("created_at", "DateTime", (), False, False, ()),
        ),
        (("uq_eng_release_revision", ("revision_id",)),),
        (),
        (
            (
                "ix_eng_release_cutoff",
                ("tenant_id", "project_workspace_id", "deliverable_id", "effective_date"),
                False,
                None,
            ),
            ("ix_engineering_releases_deliverable_id", ("deliverable_id",), False, None),
            ("ix_engineering_releases_project_workspace_id", ("project_workspace_id",), False, None),
            ("ix_engineering_releases_tenant_id", ("tenant_id",), False, None),
        ),
    ),
    (
        "engineering_interfaces",
        (
            ("code", "String", (120,), False, False, ()),
            ("title", "String", (300,), False, False, ()),
            ("interface_type", "String", (32,), False, False, ()),
            ("deliverable_id", "Integer", (), True, False, ("engineering_deliverables.id",)),
            ("source_reference", "String", (1000,), False, False, ()),
            ("status", "String", (20,), False, False, ()),
            ("resolution", "Text", (), True, False, ()),
            ("updated_by", "Integer", (), False, False, ("user_accounts.id",)),
            ("updated_at", "DateTime", (), False, False, ()),
            ("id", "Integer", (), False, True, ()),
            ("tenant_id", "Integer", (), False, False, ("tenants.id",)),
            ("project_workspace_id", "Integer", (), False, False, ("enterprise_workspaces.id",)),
            ("version", "Integer", (), False, False, ()),
            ("created_by", "Integer", (), False, False, ("user_accounts.id",)),
            ("created_at", "DateTime", (), False, False, ()),
        ),
        (("uq_eng_interface_code", ("tenant_id", "project_workspace_id", "code")),),
        (
            ("ck_eng_interface_status", "status IN ('OPEN','RESOLVED','CLOSED','CANCELLED')"),
            ("ck_eng_interface_type", "interface_type IN ('DISCIPLINE','PROCUREMENT','CONSTRUCTION','VENDOR','OWNER')"),
        ),
        (
            ("ix_engineering_interfaces_project_workspace_id", ("project_workspace_id",), False, None),
            ("ix_engineering_interfaces_tenant_id", ("tenant_id",), False, None),
        ),
    ),
    (
        "engineering_history",
        (
            ("entity_type", "String", (80,), False, False, ()),
            ("entity_id", "Integer", (), False, False, ()),
            ("entity_version", "Integer", (), False, False, ()),
            ("event_type", "String", (100,), False, False, ()),
            ("snapshot_json", "JSON", (), False, False, ()),
            ("reason", "Text", (), False, False, ()),
            ("id", "Integer", (), False, True, ()),
            ("tenant_id", "Integer", (), False, False, ("tenants.id",)),
            ("project_workspace_id", "Integer", (), False, False, ("enterprise_workspaces.id",)),
            ("version", "Integer", (), False, False, ()),
            ("created_by", "Integer", (), False, False, ("user_accounts.id",)),
            ("created_at", "DateTime", (), False, False, ()),
        ),
        (),
        (),
        (
            ("ix_eng_history_cursor", ("tenant_id", "project_workspace_id", "id"), False, None),
            ("ix_engineering_history_project_workspace_id", ("project_workspace_id",), False, None),
            ("ix_engineering_history_tenant_id", ("tenant_id",), False, None),
        ),
    ),
    (
        "engineering_mappings",
        (
            ("revision_id", "Integer", (), True, False, ("engineering_revisions.id",)),
            ("design_package_id", "Integer", (), True, False, ("engineering_design_packages.id",)),
            ("target_kind", "String", (32,), False, False, ()),
            ("target_id", "Integer", (), True, False, ()),
            ("schedule_version_id", "Integer", (), True, False, ("schedule_versions.id",)),
            ("external_id", "String", (160,), True, False, ()),
            ("action", "String", (12,), False, False, ()),
            ("target_snapshot_json", "JSON", (), False, False, ()),
            ("content_hash", "String", (64,), False, False, ()),
            ("reason", "Text", (), False, False, ()),
            ("id", "Integer", (), False, True, ()),
            ("tenant_id", "Integer", (), False, False, ("tenants.id",)),
            ("project_workspace_id", "Integer", (), False, False, ("enterprise_workspaces.id",)),
            ("version", "Integer", (), False, False, ()),
            ("created_by", "Integer", (), False, False, ("user_accounts.id",)),
            ("created_at", "DateTime", (), False, False, ()),
        ),
        (),
        (
            ("ck_engineering_mapping_action", "action IN ('SET','REMOVE') AND version > 1"),
            (
                "ck_engineering_mapping_kind",
                "target_kind IN ('EWP','CWP','IWP','CWA','SCOPE','PLAN','WBS','ACTIVITY','MILESTONE','CBS','COST_CODE','CONTROL_ACCOUNT')",
            ),
            (
                "ck_engineering_mapping_owner",
                "((revision_id IS NOT NULL AND design_package_id IS NULL) OR (revision_id IS NULL AND design_package_id IS NOT NULL AND target_kind='EWP'))",
            ),
            (
                "ck_engineering_mapping_target",
                "((target_kind IN ('WBS','ACTIVITY','MILESTONE') AND target_id IS NULL AND schedule_version_id IS NOT NULL AND external_id IS NOT NULL AND length(external_id)>0) OR (target_kind NOT IN ('WBS','ACTIVITY','MILESTONE') AND target_id IS NOT NULL AND schedule_version_id IS NULL AND external_id IS NULL))",
            ),
        ),
        (
            (
                "ix_engineering_mapping_reverse",
                ("tenant_id", "project_workspace_id", "target_kind", "target_id", "id"),
                False,
                None,
            ),
            ("ix_engineering_mappings_project_workspace_id", ("project_workspace_id",), False, None),
            ("ix_engineering_mappings_tenant_id", ("tenant_id",), False, None),
            (
                "uq_engineering_package_mapping_version",
                ("design_package_id", "version"),
                True,
                "design_package_id IS NOT NULL",
            ),
            ("uq_engineering_revision_mapping_version", ("revision_id", "version"), True, "revision_id IS NOT NULL"),
        ),
    ),
)

GUARD_SQL = r"""
CREATE FUNCTION o2a_engineering_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  d jsonb; old_d jsonb; workspace_row jsonb; related jsonb; release_snapshot jsonb;
  t bigint; w bigint; field_name text; actor_id bigint; rid bigint;
  target_table text; current_revision_sequence integer;
BEGIN
  IF TG_OP='DELETE' THEN
    RAISE EXCEPTION 'Engineering history cannot be deleted';
  END IF;
  d := to_jsonb(NEW);
  t := (d->>'tenant_id')::bigint; w := (d->>'project_workspace_id')::bigint;
  IF TG_OP='UPDATE' THEN
    old_d := to_jsonb(OLD);
    IF TG_TABLE_NAME IN ('engineering_history','engineering_releases','engineering_mappings')
       OR (TG_TABLE_NAME='engineering_revisions' AND old_d->>'status' IN ('APPROVED','REJECTED'))
       OR (TG_TABLE_NAME='engineering_review_comments' AND old_d->>'status'='CLOSED')
       OR (TG_TABLE_NAME='engineering_reviews' AND old_d->>'status'='CLOSED') THEN
      RAISE EXCEPTION 'Engineering terminal record is immutable';
    END IF;
    FOREACH field_name IN ARRAY ARRAY['id','tenant_id','project_workspace_id','created_by','created_at',
        'deliverable_id','revision_id','review_id','round_number','supersedes_revision_id',
        'revision_sequence','revision_code','prepared_by','configuration_id','configuration_hash','submitted_hash'] LOOP
      IF d->field_name IS DISTINCT FROM old_d->field_name THEN
        RAISE EXCEPTION 'Engineering identity and parent are immutable';
      END IF;
    END LOOP;
    IF TG_TABLE_NAME='engineering_reviews' AND old_d->>'decision' IS NOT NULL AND
       (d - ARRAY['status','version','closed_by','closed_at']) IS DISTINCT FROM
       (old_d - ARRAY['status','version','closed_by','closed_at']) THEN
      RAISE EXCEPTION 'Engineering review decision is immutable';
    END IF;
    IF TG_TABLE_NAME='engineering_review_comments' AND
       (d - ARRAY['status','version','response','response_by','response_at','closed_by','closed_at']) IS DISTINCT FROM
       (old_d - ARRAY['status','version','response','response_by','response_at','closed_by','closed_at']) THEN
      RAISE EXCEPTION 'Engineering comment text is immutable';
    END IF;
  END IF;
  SELECT to_jsonb(p) INTO workspace_row FROM enterprise_workspaces p WHERE p.id=w AND p.tenant_id=t;
  IF workspace_row IS NULL OR workspace_row->>'workspace_type_code' <> 'project'
       OR lower(workspace_row->>'status') <> 'active' THEN
    RAISE EXCEPTION 'Engineering requires same-tenant active Project';
  END IF;
  FOREACH field_name IN ARRAY ARRAY['created_by','updated_by','prepared_by','checked_by','approved_by',
      'reviewer_id','decision_by','response_by','closed_by','released_by'] LOOP
    actor_id := (d->>field_name)::bigint;
    IF actor_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM user_accounts a WHERE a.id=actor_id AND a.tenant_id=t) THEN
      RAISE EXCEPTION 'Engineering actor outside tenant';
    END IF;
  END LOOP;
  IF d->>'configuration_id' IS NOT NULL AND NOT EXISTS(
    SELECT 1 FROM admin_configurations c WHERE c.id=(d->>'configuration_id')::bigint
      AND c.tenant_id=t AND c.kind='engineering_profile' AND c.status='published'
  ) THEN RAISE EXCEPTION 'Engineering requires same-tenant published profile'; END IF;
  IF d->>'design_package_id' IS NOT NULL AND NOT EXISTS(
    SELECT 1 FROM engineering_design_packages p WHERE p.id=(d->>'design_package_id')::bigint
      AND p.tenant_id=t AND p.project_workspace_id=w
  ) THEN RAISE EXCEPTION 'Engineering design package outside Project'; END IF;
  IF d->>'deliverable_id' IS NOT NULL AND NOT EXISTS(
    SELECT 1 FROM engineering_deliverables p WHERE p.id=(d->>'deliverable_id')::bigint
      AND p.tenant_id=t AND p.project_workspace_id=w
  ) THEN RAISE EXCEPTION 'Engineering deliverable outside Project'; END IF;
  IF d->>'revision_id' IS NOT NULL THEN
    rid := (d->>'revision_id')::bigint;
    SELECT to_jsonb(r) INTO related FROM engineering_revisions r
      WHERE r.id=rid AND r.tenant_id=t AND r.project_workspace_id=w;
    IF related IS NULL THEN RAISE EXCEPTION 'Engineering revision outside Project'; END IF;
  END IF;
  IF TG_TABLE_NAME='engineering_revisions' THEN
    IF TG_OP='INSERT' AND d->>'status'<>'DRAFT' THEN
      RAISE EXCEPTION 'Engineering revision must start DRAFT';
    END IF;
    IF d->>'supersedes_revision_id' IS NOT NULL AND NOT EXISTS(
      SELECT 1 FROM engineering_revisions r WHERE r.id=(d->>'supersedes_revision_id')::bigint
        AND r.deliverable_id=(d->>'deliverable_id')::bigint AND r.tenant_id=t AND r.project_workspace_id=w
        AND r.revision_sequence+1=(d->>'revision_sequence')::integer
    ) THEN RAISE EXCEPTION 'Engineering successor lineage is invalid'; END IF;
    IF (d->>'supersedes_revision_id' IS NULL) <> ((d->>'revision_sequence')::integer=1) THEN
      RAISE EXCEPTION 'Engineering successor requires predecessor';
    END IF;
    IF d->>'status'='APPROVED' AND (
      d->>'approved_by' IS NULL OR d->>'approved_at' IS NULL
      OR d->>'approved_by' = d->>'prepared_by' OR d->>'approved_by' = d->>'checked_by'
    ) THEN RAISE EXCEPTION 'Engineering approval requires independent actor'; END IF;
  ELSIF TG_TABLE_NAME='engineering_review_comments' THEN
    IF NOT EXISTS(
      SELECT 1 FROM engineering_reviews r WHERE r.id=(d->>'review_id')::bigint
        AND r.revision_id=rid AND r.tenant_id=t AND r.project_workspace_id=w
    ) THEN RAISE EXCEPTION 'Engineering comment review outside revision'; END IF;
    IF related->>'status' IN ('APPROVED','REJECTED') THEN
      RAISE EXCEPTION 'Engineering revision comments are frozen';
    END IF;
  ELSIF TG_TABLE_NAME='engineering_reviews' THEN
    IF related->>'status' IN ('APPROVED','REJECTED') AND (
      TG_OP='INSERT' OR d->>'status' NOT IN ('APPROVED','REJECTED','CLOSED')
    ) THEN RAISE EXCEPTION 'Engineering terminal revision cannot reopen review'; END IF;
  ELSIF TG_TABLE_NAME='engineering_releases' THEN
    IF related->>'status'<>'APPROVED' OR related->>'deliverable_id' IS DISTINCT FROM d->>'deliverable_id'
       OR nullif(related->>'document_hash','') IS NULL OR nullif(d->>'release_hash','') IS NULL
       OR (d->>'effective_date')::date < (related->>'approved_at')::date THEN
      RAISE EXCEPTION 'IFC release requires approved revision and pinned document';
    END IF;
    current_revision_sequence := (related->>'revision_sequence')::integer;
    release_snapshot := d->'snapshot_json';
    IF release_snapshot->>'revision_id' IS DISTINCT FROM d->>'revision_id'
       OR release_snapshot->>'deliverable_id' IS DISTINCT FROM d->>'deliverable_id'
       OR release_snapshot->>'revision_content_hash' IS DISTINCT FROM related->>'content_hash'
       OR release_snapshot->>'document_hash' IS DISTINCT FROM related->>'document_hash'
       OR release_snapshot->>'effective_date' IS DISTINCT FROM d->>'effective_date'
       OR release_snapshot->>'released_by' IS DISTINCT FROM d->>'released_by'
       OR d->>'released_by' = related->>'prepared_by'
       OR NOT EXISTS(
         SELECT 1 FROM engineering_reviews review WHERE review.id=(release_snapshot->>'review_id')::bigint
          AND review.revision_id=rid AND review.tenant_id=t AND review.project_workspace_id=w
          AND review.status IN ('APPROVED','CLOSED') AND review.decision='APPROVED'
          AND review.submitted_hash=related->>'content_hash'
       )
       OR EXISTS(
         SELECT 1 FROM engineering_revisions newest WHERE newest.tenant_id=t AND newest.project_workspace_id=w
          AND newest.deliverable_id=(d->>'deliverable_id')::bigint
          AND newest.revision_sequence>current_revision_sequence
       ) THEN
      RAISE EXCEPTION 'IFC release requires the current approved review and matching snapshot';
    END IF;
    IF d->>'released_by' = related->>'approved_by' AND EXISTS(
      SELECT 1 FROM admin_configurations c WHERE c.id=(related->>'configuration_id')::bigint
       AND (c.content_json::jsonb #>> '{ifc_release_rules,releaser_distinct_from_approver}')::boolean IS TRUE
    ) THEN RAISE EXCEPTION 'IFC releaser must be independent'; END IF;
    IF EXISTS (
      SELECT 1 FROM engineering_releases e JOIN engineering_revisions r ON r.id=e.revision_id
      WHERE e.tenant_id=t AND e.project_workspace_id=w AND e.deliverable_id=(d->>'deliverable_id')::bigint
        AND (r.revision_sequence>=current_revision_sequence OR e.effective_date>(d->>'effective_date')::date)
    ) THEN RAISE EXCEPTION 'IFC release successor must follow effective lineage'; END IF;
  ELSIF TG_TABLE_NAME='engineering_mappings' THEN
    target_table := CASE d->>'target_kind'
      WHEN 'EWP' THEN 'awp_work_packages' WHEN 'CWP' THEN 'awp_work_packages'
      WHEN 'IWP' THEN 'awp_work_packages' WHEN 'CWA' THEN 'awp_cwas'
      WHEN 'SCOPE' THEN 'scope_items' WHEN 'PLAN' THEN 'scope_plan_items'
      WHEN 'WBS' THEN 'schedule_versions' WHEN 'ACTIVITY' THEN 'schedule_versions'
      WHEN 'MILESTONE' THEN 'schedule_versions' WHEN 'CBS' THEN 'cost_cbs'
      WHEN 'COST_CODE' THEN 'cost_code_dictionary' WHEN 'CONTROL_ACCOUNT' THEN 'cost_control_accounts'
    END;
    EXECUTE format('SELECT to_jsonb(p) FROM %I p WHERE p.id=$1 AND p.tenant_id=$2 AND p.project_workspace_id=$3', target_table)
      INTO related USING (COALESCE(d->>'target_id',d->>'schedule_version_id'))::bigint,t,w;
    IF related IS NULL OR (target_table='awp_work_packages' AND related->>'package_type' IS DISTINCT FROM d->>'target_kind') THEN
      RAISE EXCEPTION 'Engineering mapping target outside Project or type';
    END IF;
  END IF;
  RETURN NEW;
END $$;

CREATE FUNCTION o2a_engineering_profile_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.kind='engineering_profile' AND OLD.status='published' THEN
    RAISE EXCEPTION 'Published Engineering profile is immutable; create a successor';
  END IF;
  IF TG_OP='DELETE' THEN RETURN OLD; END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER tr_engineering_profile_o2a BEFORE UPDATE OR DELETE ON admin_configurations
FOR EACH ROW EXECUTE FUNCTION o2a_engineering_profile_guard();
"""


def upgrade():
    for table, columns, unique, checks, indexes in TABLES:
        fields = [
            sa.Column(
                name,
                getattr(sa, kind)(*args),
                *(sa.ForeignKey(ref) for ref in refs),
                nullable=nullable,
                primary_key=primary,
            )
            for name, kind, args, nullable, primary, refs in columns
        ]
        constraints = [sa.UniqueConstraint(*cols, name=name) for name, cols in unique]
        constraints.extend(sa.CheckConstraint(sql, name=name) for name, sql in checks)
        op.create_table(table, *fields, *constraints)
        for name, cols, unique_index, condition in indexes:
            options = {"postgresql_where": sa.text(condition), "sqlite_where": sa.text(condition)} if condition else {}
            op.create_index(name, table, list(cols), unique=unique_index, **options)
    if op.get_bind().dialect.name == "postgresql":
        op.execute(GUARD_SQL)
        for table, *_ in TABLES:
            op.execute(
                f"CREATE TRIGGER tr_{table}_o2a BEFORE INSERT OR UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION o2a_engineering_guard()"
            )


def downgrade():
    bind = op.get_bind()
    for table, *_ in TABLES:
        if bind.scalar(sa.text(f"SELECT EXISTS(SELECT 1 FROM {table})")):
            raise RuntimeError("Engineering business records exist; downgrade refused")
    if bind.scalar(sa.text("SELECT EXISTS(SELECT 1 FROM admin_configurations WHERE kind='engineering_profile')")):
        raise RuntimeError("Engineering profiles exist; downgrade refused")
    if bind.dialect.name == "postgresql":
        op.execute("DROP TRIGGER tr_engineering_profile_o2a ON admin_configurations")
    for table, *_ in reversed(TABLES):
        op.drop_table(table)
    if bind.dialect.name == "postgresql":
        op.execute("DROP FUNCTION o2a_engineering_profile_guard()")
        op.execute("DROP FUNCTION o2a_engineering_guard()")
