-- Frozen additive O3A schema. Compiled from the reviewed models; no backfill.
CREATE TABLE field_workfronts (
    workfront_code VARCHAR(120) NOT NULL,
    title VARCHAR(240) NOT NULL,
    description TEXT NOT NULL,
    location_reference JSON NOT NULL,
    cwa_id INTEGER,
    cwp_id INTEGER,
    iwp_id INTEGER,
    source_references JSON NOT NULL,
    responsible_user_id INTEGER NOT NULL,
    status VARCHAR(24) NOT NULL,
    planned_start DATE NOT NULL,
    planned_finish DATE NOT NULL,
    actual_start DATE,
    actual_finish DATE,
    updated_by INTEGER NOT NULL,
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    configuration_id INTEGER NOT NULL,
    configuration_hash VARCHAR(64) NOT NULL,
    source_hash VARCHAR(64) NOT NULL,
    id SERIAL NOT NULL,
    tenant_id INTEGER NOT NULL,
    project_workspace_id INTEGER NOT NULL,
    version INTEGER NOT NULL,
    created_by INTEGER NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_o3a_workfront_code UNIQUE (tenant_id, project_workspace_id, workfront_code),
    CONSTRAINT ck_o3a_workfront_plan_dates CHECK (planned_start <= planned_finish),
    CONSTRAINT ck_o3a_workfront_actual_dates CHECK (actual_finish IS NULL OR actual_start <= actual_finish),
    CONSTRAINT ck_o3a_workfront_status CHECK (status IN ('PLANNED','ACTIVE','SUSPENDED','COMPLETE')),
    FOREIGN KEY(cwa_id) REFERENCES awp_cwas (id),
    FOREIGN KEY(cwp_id) REFERENCES awp_work_packages (id),
    FOREIGN KEY(iwp_id) REFERENCES awp_work_packages (id),
    FOREIGN KEY(responsible_user_id) REFERENCES user_accounts (id),
    FOREIGN KEY(updated_by) REFERENCES user_accounts (id),
    FOREIGN KEY(configuration_id) REFERENCES admin_configurations (id),
    FOREIGN KEY(tenant_id) REFERENCES tenants (id),
    FOREIGN KEY(project_workspace_id) REFERENCES enterprise_workspaces (id),
    FOREIGN KEY(created_by) REFERENCES user_accounts (id)
);

CREATE INDEX ix_field_workfronts_tenant_id ON field_workfronts (tenant_id);

CREATE INDEX ix_field_workfronts_project_workspace_id ON field_workfronts (project_workspace_id);

CREATE TABLE field_crews (
    crew_code VARCHAR(120) NOT NULL,
    description TEXT NOT NULL,
    trade VARCHAR(80) NOT NULL,
    vendor_id INTEGER,
    supervisor_user_id INTEGER NOT NULL,
    status VARCHAR(24) NOT NULL,
    updated_by INTEGER NOT NULL,
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    configuration_id INTEGER NOT NULL,
    configuration_hash VARCHAR(64) NOT NULL,
    source_hash VARCHAR(64) NOT NULL,
    id SERIAL NOT NULL,
    tenant_id INTEGER NOT NULL,
    project_workspace_id INTEGER NOT NULL,
    version INTEGER NOT NULL,
    created_by INTEGER NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_o3a_crew_code UNIQUE (tenant_id, project_workspace_id, crew_code),
    CONSTRAINT ck_o3a_crew_status CHECK (status IN ('ACTIVE','INACTIVE')),
    FOREIGN KEY(vendor_id) REFERENCES procurement_vendors (id),
    FOREIGN KEY(supervisor_user_id) REFERENCES user_accounts (id),
    FOREIGN KEY(updated_by) REFERENCES user_accounts (id),
    FOREIGN KEY(configuration_id) REFERENCES admin_configurations (id),
    FOREIGN KEY(tenant_id) REFERENCES tenants (id),
    FOREIGN KEY(project_workspace_id) REFERENCES enterprise_workspaces (id),
    FOREIGN KEY(created_by) REFERENCES user_accounts (id)
);

CREATE INDEX ix_field_crews_project_workspace_id ON field_crews (project_workspace_id);

CREATE INDEX ix_field_crews_tenant_id ON field_crews (tenant_id);

CREATE TABLE field_equipment_references (
    source_system VARCHAR(120) NOT NULL,
    external_id VARCHAR(160) NOT NULL,
    description TEXT NOT NULL,
    equipment_type VARCHAR(80) NOT NULL,
    status VARCHAR(24) NOT NULL,
    updated_by INTEGER NOT NULL,
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    configuration_id INTEGER NOT NULL,
    configuration_hash VARCHAR(64) NOT NULL,
    source_hash VARCHAR(64) NOT NULL,
    id SERIAL NOT NULL,
    tenant_id INTEGER NOT NULL,
    project_workspace_id INTEGER NOT NULL,
    version INTEGER NOT NULL,
    created_by INTEGER NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_o3a_equipment_identity UNIQUE (tenant_id, project_workspace_id, source_system, external_id),
    CONSTRAINT ck_o3a_equipment_status CHECK (status IN ('AVAILABLE','UNAVAILABLE')),
    FOREIGN KEY(updated_by) REFERENCES user_accounts (id),
    FOREIGN KEY(configuration_id) REFERENCES admin_configurations (id),
    FOREIGN KEY(tenant_id) REFERENCES tenants (id),
    FOREIGN KEY(project_workspace_id) REFERENCES enterprise_workspaces (id),
    FOREIGN KEY(created_by) REFERENCES user_accounts (id)
);

CREATE INDEX ix_field_equipment_references_tenant_id ON field_equipment_references (tenant_id);

CREATE INDEX ix_field_equipment_references_project_workspace_id ON field_equipment_references (project_workspace_id);

CREATE TABLE field_record_closures (
    entity_type VARCHAR(80) NOT NULL,
    entity_id INTEGER NOT NULL,
    entity_version INTEGER NOT NULL,
    reason TEXT NOT NULL,
    id SERIAL NOT NULL,
    tenant_id INTEGER NOT NULL,
    project_workspace_id INTEGER NOT NULL,
    version INTEGER NOT NULL,
    created_by INTEGER NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_o3a_closure UNIQUE (tenant_id, project_workspace_id, entity_type, entity_id),
    CONSTRAINT ck_o3a_closure_type CHECK (entity_type='DailyConstructionReport'),
    FOREIGN KEY(tenant_id) REFERENCES tenants (id),
    FOREIGN KEY(project_workspace_id) REFERENCES enterprise_workspaces (id),
    FOREIGN KEY(created_by) REFERENCES user_accounts (id)
);

CREATE INDEX ix_field_record_closures_tenant_id ON field_record_closures (tenant_id);

CREATE INDEX ix_field_record_closures_project_workspace_id ON field_record_closures (project_workspace_id);

CREATE TABLE field_history (
    entity_type VARCHAR(80) NOT NULL,
    entity_id INTEGER NOT NULL,
    entity_version INTEGER NOT NULL,
    previous_version INTEGER,
    previous_state VARCHAR(32),
    new_state VARCHAR(32),
    event_type VARCHAR(100) NOT NULL,
    reason TEXT NOT NULL,
    snapshot_json JSON NOT NULL,
    id SERIAL NOT NULL,
    tenant_id INTEGER NOT NULL,
    project_workspace_id INTEGER NOT NULL,
    version INTEGER NOT NULL,
    created_by INTEGER NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(tenant_id) REFERENCES tenants (id),
    FOREIGN KEY(project_workspace_id) REFERENCES enterprise_workspaces (id),
    FOREIGN KEY(created_by) REFERENCES user_accounts (id)
);

CREATE INDEX ix_o3a_field_history_entity ON field_history (tenant_id, project_workspace_id, entity_type, entity_id);

CREATE INDEX ix_field_history_project_workspace_id ON field_history (project_workspace_id);

CREATE INDEX ix_field_history_tenant_id ON field_history (tenant_id);

CREATE TABLE field_mappings (
    source_kind VARCHAR(24) NOT NULL,
    source_id INTEGER NOT NULL,
    target_kind VARCHAR(32) NOT NULL,
    target_reference JSON NOT NULL,
    action VARCHAR(12) NOT NULL,
    reason TEXT NOT NULL,
    source_hash VARCHAR(64) NOT NULL,
    id SERIAL NOT NULL,
    tenant_id INTEGER NOT NULL,
    project_workspace_id INTEGER NOT NULL,
    version INTEGER NOT NULL,
    created_by INTEGER NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT ck_field_mapping_action CHECK (action IN ('SET','REMOVE') AND source_id > 0),
    FOREIGN KEY(tenant_id) REFERENCES tenants (id),
    FOREIGN KEY(project_workspace_id) REFERENCES enterprise_workspaces (id),
    FOREIGN KEY(created_by) REFERENCES user_accounts (id)
);

CREATE INDEX ix_field_mappings_tenant_id ON field_mappings (tenant_id);

CREATE INDEX ix_field_mappings_project_workspace_id ON field_mappings (project_workspace_id);

CREATE INDEX ix_field_mapping_source ON field_mappings (tenant_id, project_workspace_id, source_kind, source_id, id);

CREATE TABLE field_consumer_decisions (
    consumer VARCHAR(20) NOT NULL,
    source_domain VARCHAR(30) NOT NULL,
    source_entity_type VARCHAR(40) NOT NULL,
    source_entity_id INTEGER NOT NULL,
    source_root_id INTEGER NOT NULL,
    source_version INTEGER NOT NULL,
    source_hash VARCHAR(64) NOT NULL,
    observed_at TIMESTAMP WITH TIME ZONE NOT NULL,
    observation_date DATE NOT NULL,
    effective_period_id INTEGER,
    quantity NUMERIC(24, 8),
    uom VARCHAR(40),
    decision VARCHAR(20) NOT NULL,
    linked_entity_type VARCHAR(60),
    linked_entity_id INTEGER,
    mapping_reference JSON NOT NULL,
    source_snapshot JSON NOT NULL,
    reason TEXT NOT NULL,
    id SERIAL NOT NULL,
    tenant_id INTEGER NOT NULL,
    project_workspace_id INTEGER NOT NULL,
    version INTEGER NOT NULL,
    created_by INTEGER NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_o3a_consumer_stream UNIQUE (tenant_id, project_workspace_id, consumer, source_entity_type, source_root_id, version),
    CONSTRAINT ck_o3a_consumer_source CHECK (source_domain='FIELD_OPERATIONS' AND source_version > 0 AND version > 0),
    CONSTRAINT ck_o3a_consumer_domain CHECK (consumer IN ('PROGRESS','AWP','COST','CONTRACTS','SCHEDULE')),
    CONSTRAINT ck_o3a_consumer_decision CHECK (decision IN ('ADOPT','PARTIAL_ADOPT','REJECT')),
    CONSTRAINT ck_o3a_consumer_quantity CHECK (quantity IS NULL OR quantity > 0),
    FOREIGN KEY(effective_period_id) REFERENCES project_controls_periods (id),
    FOREIGN KEY(tenant_id) REFERENCES tenants (id),
    FOREIGN KEY(project_workspace_id) REFERENCES enterprise_workspaces (id),
    FOREIGN KEY(created_by) REFERENCES user_accounts (id)
);

CREATE INDEX ix_o3a_consumer_history ON field_consumer_decisions (tenant_id, project_workspace_id, consumer, id);

CREATE INDEX ix_field_consumer_decisions_tenant_id ON field_consumer_decisions (tenant_id);

CREATE INDEX ix_field_consumer_decisions_project_workspace_id ON field_consumer_decisions (project_workspace_id);

CREATE TABLE field_shifts (
    shift_code VARCHAR(120) NOT NULL,
    shift_type VARCHAR(80) NOT NULL,
    shift_date DATE NOT NULL,
    start_time TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    end_time TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    workfront_id INTEGER NOT NULL,
    supervisor_user_id INTEGER NOT NULL,
    weather_reference TEXT NOT NULL,
    status VARCHAR(24) NOT NULL,
    approved_by INTEGER,
    approved_at TIMESTAMP WITHOUT TIME ZONE,
    updated_by INTEGER NOT NULL,
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    configuration_id INTEGER NOT NULL,
    configuration_hash VARCHAR(64) NOT NULL,
    source_hash VARCHAR(64) NOT NULL,
    id SERIAL NOT NULL,
    tenant_id INTEGER NOT NULL,
    project_workspace_id INTEGER NOT NULL,
    version INTEGER NOT NULL,
    created_by INTEGER NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_o3a_shift_code UNIQUE (tenant_id, project_workspace_id, shift_code),
    CONSTRAINT ck_o3a_shift_window CHECK (start_time < end_time),
    CONSTRAINT ck_o3a_shift_status CHECK (status IN ('OPEN','SUBMITTED','APPROVED','CLOSED')),
    FOREIGN KEY(workfront_id) REFERENCES field_workfronts (id),
    FOREIGN KEY(supervisor_user_id) REFERENCES user_accounts (id),
    FOREIGN KEY(approved_by) REFERENCES user_accounts (id),
    FOREIGN KEY(updated_by) REFERENCES user_accounts (id),
    FOREIGN KEY(configuration_id) REFERENCES admin_configurations (id),
    FOREIGN KEY(tenant_id) REFERENCES tenants (id),
    FOREIGN KEY(project_workspace_id) REFERENCES enterprise_workspaces (id),
    FOREIGN KEY(created_by) REFERENCES user_accounts (id)
);

CREATE INDEX ix_field_shifts_tenant_id ON field_shifts (tenant_id);

CREATE INDEX ix_field_shifts_project_workspace_id ON field_shifts (project_workspace_id);

CREATE INDEX ix_field_shifts_workfront_id ON field_shifts (workfront_id);

CREATE TABLE field_site_instructions (
    instruction_number VARCHAR(120) NOT NULL,
    instruction_type VARCHAR(80) NOT NULL,
    instruction_date DATE NOT NULL,
    issuer VARCHAR(300) NOT NULL,
    recipient VARCHAR(300) NOT NULL,
    workfront_id INTEGER NOT NULL,
    scope_item_id INTEGER,
    iwp_id INTEGER,
    description TEXT NOT NULL,
    document_reference JSON NOT NULL,
    status VARCHAR(24) NOT NULL,
    issued_by INTEGER,
    issued_at TIMESTAMP WITHOUT TIME ZONE,
    acknowledged_by INTEGER,
    acknowledged_at TIMESTAMP WITHOUT TIME ZONE,
    updated_by INTEGER NOT NULL,
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    configuration_id INTEGER NOT NULL,
    configuration_hash VARCHAR(64) NOT NULL,
    source_hash VARCHAR(64) NOT NULL,
    id SERIAL NOT NULL,
    tenant_id INTEGER NOT NULL,
    project_workspace_id INTEGER NOT NULL,
    version INTEGER NOT NULL,
    created_by INTEGER NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_field_instruction_number UNIQUE (tenant_id, project_workspace_id, instruction_number),
    CONSTRAINT ck_field_instruction_status CHECK (status IN ('DRAFT','ISSUED','ACKNOWLEDGED','CLOSED')),
    FOREIGN KEY(workfront_id) REFERENCES field_workfronts (id),
    FOREIGN KEY(scope_item_id) REFERENCES scope_items (id),
    FOREIGN KEY(iwp_id) REFERENCES awp_work_packages (id),
    FOREIGN KEY(issued_by) REFERENCES user_accounts (id),
    FOREIGN KEY(acknowledged_by) REFERENCES user_accounts (id),
    FOREIGN KEY(updated_by) REFERENCES user_accounts (id),
    FOREIGN KEY(configuration_id) REFERENCES admin_configurations (id),
    FOREIGN KEY(tenant_id) REFERENCES tenants (id),
    FOREIGN KEY(project_workspace_id) REFERENCES enterprise_workspaces (id),
    FOREIGN KEY(created_by) REFERENCES user_accounts (id)
);

CREATE INDEX ix_field_site_instructions_tenant_id ON field_site_instructions (tenant_id);

CREATE INDEX ix_field_site_instructions_project_workspace_id ON field_site_instructions (project_workspace_id);

CREATE INDEX ix_field_site_instructions_workfront_id ON field_site_instructions (workfront_id);

CREATE TABLE field_constraint_observations (
    observation_code VARCHAR(120) NOT NULL,
    constraint_type VARCHAR(80) NOT NULL,
    workfront_id INTEGER NOT NULL,
    iwp_id INTEGER,
    observation_date DATE NOT NULL,
    description TEXT NOT NULL,
    severity VARCHAR(16) NOT NULL,
    document_reference JSON NOT NULL,
    status VARCHAR(24) NOT NULL,
    verified_by INTEGER,
    verified_at TIMESTAMP WITHOUT TIME ZONE,
    updated_by INTEGER NOT NULL,
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    configuration_id INTEGER NOT NULL,
    configuration_hash VARCHAR(64) NOT NULL,
    source_hash VARCHAR(64) NOT NULL,
    id SERIAL NOT NULL,
    tenant_id INTEGER NOT NULL,
    project_workspace_id INTEGER NOT NULL,
    version INTEGER NOT NULL,
    created_by INTEGER NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_field_observation_code UNIQUE (tenant_id, project_workspace_id, observation_code),
    CONSTRAINT ck_field_observation_status CHECK (status IN ('REPORTED','VERIFIED','REJECTED') AND severity IN ('LOW','MEDIUM','HIGH','CRITICAL')),
    FOREIGN KEY(workfront_id) REFERENCES field_workfronts (id),
    FOREIGN KEY(iwp_id) REFERENCES awp_work_packages (id),
    FOREIGN KEY(verified_by) REFERENCES user_accounts (id),
    FOREIGN KEY(updated_by) REFERENCES user_accounts (id),
    FOREIGN KEY(configuration_id) REFERENCES admin_configurations (id),
    FOREIGN KEY(tenant_id) REFERENCES tenants (id),
    FOREIGN KEY(project_workspace_id) REFERENCES enterprise_workspaces (id),
    FOREIGN KEY(created_by) REFERENCES user_accounts (id)
);

CREATE INDEX ix_field_constraint_observations_tenant_id ON field_constraint_observations (tenant_id);

CREATE INDEX ix_field_constraint_observations_workfront_id ON field_constraint_observations (workfront_id);

CREATE INDEX ix_field_constraint_observations_project_workspace_id ON field_constraint_observations (project_workspace_id);

CREATE TABLE field_daily_reports (
    report_number VARCHAR(120) NOT NULL,
    revision INTEGER NOT NULL,
    supersedes_id INTEGER,
    report_date DATE NOT NULL,
    shift_id INTEGER NOT NULL,
    workfront_ids JSON NOT NULL,
    reporting_party VARCHAR(240) NOT NULL,
    weather JSON NOT NULL,
    work_conditions TEXT NOT NULL,
    comments TEXT NOT NULL,
    summaries JSON NOT NULL,
    source_references JSON NOT NULL,
    document_references JSON NOT NULL,
    status VARCHAR(24) NOT NULL,
    submitted_by INTEGER,
    submitted_at TIMESTAMP WITHOUT TIME ZONE,
    reviewed_by INTEGER,
    reviewed_at TIMESTAMP WITHOUT TIME ZONE,
    approved_by INTEGER,
    approved_at TIMESTAMP WITHOUT TIME ZONE,
    updated_by INTEGER NOT NULL,
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    configuration_id INTEGER NOT NULL,
    configuration_hash VARCHAR(64) NOT NULL,
    source_hash VARCHAR(64) NOT NULL,
    id SERIAL NOT NULL,
    tenant_id INTEGER NOT NULL,
    project_workspace_id INTEGER NOT NULL,
    version INTEGER NOT NULL,
    created_by INTEGER NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_o3a_daily_revision UNIQUE (tenant_id, project_workspace_id, report_number, revision),
    CONSTRAINT ck_o3a_daily_revision CHECK (revision > 0),
    CONSTRAINT ck_o3a_daily_status CHECK (status IN ('DRAFT','SUBMITTED','REVIEWED','APPROVED')),
    UNIQUE (supersedes_id),
    FOREIGN KEY(supersedes_id) REFERENCES field_daily_reports (id),
    FOREIGN KEY(shift_id) REFERENCES field_shifts (id),
    FOREIGN KEY(submitted_by) REFERENCES user_accounts (id),
    FOREIGN KEY(reviewed_by) REFERENCES user_accounts (id),
    FOREIGN KEY(approved_by) REFERENCES user_accounts (id),
    FOREIGN KEY(updated_by) REFERENCES user_accounts (id),
    FOREIGN KEY(configuration_id) REFERENCES admin_configurations (id),
    FOREIGN KEY(tenant_id) REFERENCES tenants (id),
    FOREIGN KEY(project_workspace_id) REFERENCES enterprise_workspaces (id),
    FOREIGN KEY(created_by) REFERENCES user_accounts (id)
);

CREATE INDEX ix_field_daily_reports_tenant_id ON field_daily_reports (tenant_id);

CREATE INDEX ix_field_daily_reports_shift_id ON field_daily_reports (shift_id);

CREATE INDEX ix_field_daily_reports_project_workspace_id ON field_daily_reports (project_workspace_id);

CREATE TABLE field_labor_usage (
    record_code VARCHAR(120) NOT NULL,
    shift_id INTEGER NOT NULL,
    workfront_id INTEGER NOT NULL,
    crew_id INTEGER NOT NULL,
    trade VARCHAR(80) NOT NULL,
    headcount INTEGER NOT NULL,
    regular_hours NUMERIC(24, 8) NOT NULL,
    overtime_hours NUMERIC(24, 8) NOT NULL,
    productive_hours NUMERIC(24, 8),
    nonproductive_hours NUMERIC(24, 8),
    activity_reference JSON NOT NULL,
    document_references JSON NOT NULL,
    supersedes_id INTEGER,
    status VARCHAR(24) NOT NULL,
    updated_by INTEGER NOT NULL,
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    configuration_id INTEGER NOT NULL,
    configuration_hash VARCHAR(64) NOT NULL,
    source_hash VARCHAR(64) NOT NULL,
    id SERIAL NOT NULL,
    tenant_id INTEGER NOT NULL,
    project_workspace_id INTEGER NOT NULL,
    version INTEGER NOT NULL,
    created_by INTEGER NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_o3a_labor_code UNIQUE (tenant_id, project_workspace_id, record_code),
    CONSTRAINT ck_o3a_labor_amount CHECK (headcount > 0 AND regular_hours >= 0 AND overtime_hours >= 0),
    CONSTRAINT ck_o3a_labor_productive CHECK (productive_hours IS NULL OR productive_hours >= 0),
    CONSTRAINT ck_o3a_labor_nonproductive CHECK (nonproductive_hours IS NULL OR nonproductive_hours >= 0),
    CONSTRAINT ck_o3a_labor_status CHECK (status='RECORDED'),
    FOREIGN KEY(shift_id) REFERENCES field_shifts (id),
    FOREIGN KEY(workfront_id) REFERENCES field_workfronts (id),
    FOREIGN KEY(crew_id) REFERENCES field_crews (id),
    UNIQUE (supersedes_id),
    FOREIGN KEY(supersedes_id) REFERENCES field_labor_usage (id),
    FOREIGN KEY(updated_by) REFERENCES user_accounts (id),
    FOREIGN KEY(configuration_id) REFERENCES admin_configurations (id),
    FOREIGN KEY(tenant_id) REFERENCES tenants (id),
    FOREIGN KEY(project_workspace_id) REFERENCES enterprise_workspaces (id),
    FOREIGN KEY(created_by) REFERENCES user_accounts (id)
);

CREATE INDEX ix_field_labor_usage_shift_id ON field_labor_usage (shift_id);

CREATE INDEX ix_field_labor_usage_project_workspace_id ON field_labor_usage (project_workspace_id);

CREATE INDEX ix_field_labor_usage_tenant_id ON field_labor_usage (tenant_id);

CREATE TABLE field_equipment_usage (
    record_code VARCHAR(120) NOT NULL,
    equipment_id INTEGER NOT NULL,
    shift_id INTEGER NOT NULL,
    workfront_id INTEGER NOT NULL,
    usage_type VARCHAR(80) NOT NULL,
    operating_hours NUMERIC(24, 8) NOT NULL,
    idle_hours NUMERIC(24, 8) NOT NULL,
    standby_hours NUMERIC(24, 8) NOT NULL,
    downtime_hours NUMERIC(24, 8) NOT NULL,
    activity_reference JSON NOT NULL,
    document_references JSON NOT NULL,
    supersedes_id INTEGER,
    status VARCHAR(24) NOT NULL,
    updated_by INTEGER NOT NULL,
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    configuration_id INTEGER NOT NULL,
    configuration_hash VARCHAR(64) NOT NULL,
    source_hash VARCHAR(64) NOT NULL,
    id SERIAL NOT NULL,
    tenant_id INTEGER NOT NULL,
    project_workspace_id INTEGER NOT NULL,
    version INTEGER NOT NULL,
    created_by INTEGER NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_o3a_equipment_usage_code UNIQUE (tenant_id, project_workspace_id, record_code),
    CONSTRAINT ck_o3a_equipment_hours CHECK (operating_hours >= 0 AND idle_hours >= 0 AND standby_hours >= 0 AND downtime_hours >= 0),
    CONSTRAINT ck_o3a_equipment_usage_status CHECK (status='RECORDED'),
    FOREIGN KEY(equipment_id) REFERENCES field_equipment_references (id),
    FOREIGN KEY(shift_id) REFERENCES field_shifts (id),
    FOREIGN KEY(workfront_id) REFERENCES field_workfronts (id),
    UNIQUE (supersedes_id),
    FOREIGN KEY(supersedes_id) REFERENCES field_equipment_usage (id),
    FOREIGN KEY(updated_by) REFERENCES user_accounts (id),
    FOREIGN KEY(configuration_id) REFERENCES admin_configurations (id),
    FOREIGN KEY(tenant_id) REFERENCES tenants (id),
    FOREIGN KEY(project_workspace_id) REFERENCES enterprise_workspaces (id),
    FOREIGN KEY(created_by) REFERENCES user_accounts (id)
);

CREATE INDEX ix_field_equipment_usage_tenant_id ON field_equipment_usage (tenant_id);

CREATE INDEX ix_field_equipment_usage_shift_id ON field_equipment_usage (shift_id);

CREATE INDEX ix_field_equipment_usage_project_workspace_id ON field_equipment_usage (project_workspace_id);

CREATE TABLE field_conditions (
    condition_code VARCHAR(120) NOT NULL,
    condition_date DATE NOT NULL,
    shift_id INTEGER NOT NULL,
    workfront_id INTEGER NOT NULL,
    location_reference JSON NOT NULL,
    weather_condition VARCHAR(80) NOT NULL,
    temperature NUMERIC(24, 8),
    rainfall NUMERIC(24, 8),
    wind NUMERIC(24, 8),
    access_condition VARCHAR(80) NOT NULL,
    site_condition TEXT NOT NULL,
    source TEXT NOT NULL,
    document_references JSON NOT NULL,
    status VARCHAR(24) NOT NULL,
    updated_by INTEGER NOT NULL,
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    configuration_id INTEGER NOT NULL,
    configuration_hash VARCHAR(64) NOT NULL,
    source_hash VARCHAR(64) NOT NULL,
    id SERIAL NOT NULL,
    tenant_id INTEGER NOT NULL,
    project_workspace_id INTEGER NOT NULL,
    version INTEGER NOT NULL,
    created_by INTEGER NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_o3a_condition_code UNIQUE (tenant_id, project_workspace_id, condition_code),
    CONSTRAINT ck_o3a_condition_rainfall CHECK (rainfall IS NULL OR rainfall >= 0),
    CONSTRAINT ck_o3a_condition_wind CHECK (wind IS NULL OR wind >= 0),
    CONSTRAINT ck_o3a_condition_status CHECK (status='RECORDED'),
    FOREIGN KEY(shift_id) REFERENCES field_shifts (id),
    FOREIGN KEY(workfront_id) REFERENCES field_workfronts (id),
    FOREIGN KEY(updated_by) REFERENCES user_accounts (id),
    FOREIGN KEY(configuration_id) REFERENCES admin_configurations (id),
    FOREIGN KEY(tenant_id) REFERENCES tenants (id),
    FOREIGN KEY(project_workspace_id) REFERENCES enterprise_workspaces (id),
    FOREIGN KEY(created_by) REFERENCES user_accounts (id)
);

CREATE INDEX ix_field_conditions_shift_id ON field_conditions (shift_id);

CREATE INDEX ix_field_conditions_project_workspace_id ON field_conditions (project_workspace_id);

CREATE INDEX ix_field_conditions_tenant_id ON field_conditions (tenant_id);

CREATE TABLE field_events (
    event_code VARCHAR(120) NOT NULL,
    workfront_id INTEGER NOT NULL,
    shift_id INTEGER,
    event_type VARCHAR(80) NOT NULL,
    observed_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    title VARCHAR(300) NOT NULL,
    description TEXT NOT NULL,
    severity VARCHAR(16) NOT NULL,
    duration_hours NUMERIC(24, 8),
    document_reference JSON NOT NULL,
    status VARCHAR(24) NOT NULL,
    reviewed_by INTEGER,
    reviewed_at TIMESTAMP WITHOUT TIME ZONE,
    updated_by INTEGER NOT NULL,
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    configuration_id INTEGER NOT NULL,
    configuration_hash VARCHAR(64) NOT NULL,
    source_hash VARCHAR(64) NOT NULL,
    id SERIAL NOT NULL,
    tenant_id INTEGER NOT NULL,
    project_workspace_id INTEGER NOT NULL,
    version INTEGER NOT NULL,
    created_by INTEGER NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_field_event_code UNIQUE (tenant_id, project_workspace_id, event_code),
    CONSTRAINT ck_field_event_status CHECK (status IN ('RECORDED','REVIEWED','CLOSED') AND severity IN ('LOW','MEDIUM','HIGH','CRITICAL')),
    CONSTRAINT ck_field_event_hours CHECK (duration_hours IS NULL OR duration_hours >= 0),
    FOREIGN KEY(workfront_id) REFERENCES field_workfronts (id),
    FOREIGN KEY(shift_id) REFERENCES field_shifts (id),
    FOREIGN KEY(reviewed_by) REFERENCES user_accounts (id),
    FOREIGN KEY(updated_by) REFERENCES user_accounts (id),
    FOREIGN KEY(configuration_id) REFERENCES admin_configurations (id),
    FOREIGN KEY(tenant_id) REFERENCES tenants (id),
    FOREIGN KEY(project_workspace_id) REFERENCES enterprise_workspaces (id),
    FOREIGN KEY(created_by) REFERENCES user_accounts (id)
);

CREATE INDEX ix_field_events_project_workspace_id ON field_events (project_workspace_id);

CREATE INDEX ix_field_events_tenant_id ON field_events (tenant_id);

CREATE INDEX ix_field_events_workfront_id ON field_events (workfront_id);

CREATE TABLE field_production_records (
    production_code VARCHAR(120) NOT NULL,
    revision INTEGER NOT NULL,
    workfront_id INTEGER NOT NULL,
    shift_id INTEGER NOT NULL,
    report_id INTEGER,
    scope_item_id INTEGER NOT NULL,
    plan_item_id INTEGER,
    iwp_id INTEGER,
    quantity NUMERIC(24, 8) NOT NULL,
    planned_quantity NUMERIC(24, 8),
    uom VARCHAR(40) NOT NULL,
    production_type VARCHAR(80) NOT NULL,
    observed_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    source_reference VARCHAR(500) NOT NULL,
    location_reference JSON NOT NULL,
    scope_reference JSON NOT NULL,
    plan_reference JSON,
    iwp_reference JSON,
    engineering_reference JSON,
    material_reference JSON,
    document_reference JSON NOT NULL,
    execution_condition VARCHAR(80) NOT NULL,
    exception_reason TEXT,
    variance_reason TEXT,
    evidence_key VARCHAR(64) NOT NULL,
    status VARCHAR(24) NOT NULL,
    verified_by INTEGER,
    verified_at TIMESTAMP WITHOUT TIME ZONE,
    supersedes_id INTEGER,
    original_production_id INTEGER,
    rework_reason TEXT,
    responsible_party VARCHAR(300),
    updated_by INTEGER NOT NULL,
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    configuration_id INTEGER NOT NULL,
    configuration_hash VARCHAR(64) NOT NULL,
    source_hash VARCHAR(64) NOT NULL,
    id SERIAL NOT NULL,
    tenant_id INTEGER NOT NULL,
    project_workspace_id INTEGER NOT NULL,
    version INTEGER NOT NULL,
    created_by INTEGER NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_field_prod_code_revision UNIQUE (tenant_id, project_workspace_id, production_code, revision),
    CONSTRAINT uq_field_prod_evidence_revision UNIQUE (tenant_id, project_workspace_id, evidence_key, revision),
    CONSTRAINT ck_field_prod_quantity CHECK (quantity > 0 AND revision > 0 AND (planned_quantity IS NULL OR planned_quantity >= 0)),
    CONSTRAINT ck_field_prod_status CHECK (status IN ('RECORDED','VERIFIED','REJECTED')),
    CONSTRAINT ck_field_prod_verification CHECK ((status = 'RECORDED' AND verified_by IS NULL AND verified_at IS NULL) OR (status <> 'RECORDED' AND verified_by IS NOT NULL AND verified_at IS NOT NULL)),
    FOREIGN KEY(workfront_id) REFERENCES field_workfronts (id),
    FOREIGN KEY(shift_id) REFERENCES field_shifts (id),
    FOREIGN KEY(report_id) REFERENCES field_daily_reports (id),
    FOREIGN KEY(scope_item_id) REFERENCES scope_items (id),
    FOREIGN KEY(plan_item_id) REFERENCES scope_plan_items (id),
    FOREIGN KEY(iwp_id) REFERENCES awp_work_packages (id),
    FOREIGN KEY(verified_by) REFERENCES user_accounts (id),
    FOREIGN KEY(supersedes_id) REFERENCES field_production_records (id),
    FOREIGN KEY(original_production_id) REFERENCES field_production_records (id),
    FOREIGN KEY(updated_by) REFERENCES user_accounts (id),
    FOREIGN KEY(configuration_id) REFERENCES admin_configurations (id),
    FOREIGN KEY(tenant_id) REFERENCES tenants (id),
    FOREIGN KEY(project_workspace_id) REFERENCES enterprise_workspaces (id),
    FOREIGN KEY(created_by) REFERENCES user_accounts (id)
);

CREATE INDEX ix_field_production_records_workfront_id ON field_production_records (workfront_id);

CREATE INDEX ix_field_production_records_scope_item_id ON field_production_records (scope_item_id);

CREATE INDEX ix_field_production_records_project_workspace_id ON field_production_records (project_workspace_id);

CREATE INDEX ix_field_production_records_shift_id ON field_production_records (shift_id);

CREATE INDEX ix_field_production_records_tenant_id ON field_production_records (tenant_id);

CREATE TABLE field_material_consumption (
    consumption_code VARCHAR(120) NOT NULL,
    production_record_id INTEGER NOT NULL,
    material_item_id INTEGER NOT NULL,
    allocation_id INTEGER NOT NULL,
    workfront_id INTEGER NOT NULL,
    consumption_date DATE NOT NULL,
    quantity NUMERIC(24, 8) NOT NULL,
    uom VARCHAR(40) NOT NULL,
    allocation_reference JSON NOT NULL,
    document_reference JSON NOT NULL,
    status VARCHAR(24) NOT NULL,
    updated_by INTEGER NOT NULL,
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    configuration_id INTEGER NOT NULL,
    configuration_hash VARCHAR(64) NOT NULL,
    source_hash VARCHAR(64) NOT NULL,
    id SERIAL NOT NULL,
    tenant_id INTEGER NOT NULL,
    project_workspace_id INTEGER NOT NULL,
    version INTEGER NOT NULL,
    created_by INTEGER NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_field_consumption_code UNIQUE (tenant_id, project_workspace_id, consumption_code),
    CONSTRAINT ck_field_consumption_quantity CHECK (quantity > 0 AND status = 'RECORDED'),
    FOREIGN KEY(production_record_id) REFERENCES field_production_records (id),
    FOREIGN KEY(material_item_id) REFERENCES procurement_material_items (id),
    FOREIGN KEY(allocation_id) REFERENCES procurement_material_allocations (id),
    FOREIGN KEY(workfront_id) REFERENCES field_workfronts (id),
    FOREIGN KEY(updated_by) REFERENCES user_accounts (id),
    FOREIGN KEY(configuration_id) REFERENCES admin_configurations (id),
    FOREIGN KEY(tenant_id) REFERENCES tenants (id),
    FOREIGN KEY(project_workspace_id) REFERENCES enterprise_workspaces (id),
    FOREIGN KEY(created_by) REFERENCES user_accounts (id)
);

CREATE INDEX ix_field_material_consumption_project_workspace_id ON field_material_consumption (project_workspace_id);

CREATE INDEX ix_field_material_consumption_production_record_id ON field_material_consumption (production_record_id);

CREATE INDEX ix_field_material_consumption_tenant_id ON field_material_consumption (tenant_id);

