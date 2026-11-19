-- Frozen O2C schema. See scripts/wave-o2c/compile_migration.py for model comparison.
CREATE TABLE contract_packages (
    package_code VARCHAR(120) NOT NULL,
    title VARCHAR(240) NOT NULL,
    description TEXT NOT NULL,
    contract_strategy TEXT NOT NULL,
    contract_type VARCHAR(80) NOT NULL,
    commercial_model VARCHAR(80) NOT NULL,
    responsible_user_id INTEGER NOT NULL,
    planned_award_date DATE,
    planned_execution_date DATE,
    currency VARCHAR(8) NOT NULL,
    estimated_value NUMERIC(24, 8) NOT NULL,
    procurement_sources JSON NOT NULL,
    status VARCHAR(24) NOT NULL,
    updated_by INTEGER NOT NULL,
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    configuration_id INTEGER NOT NULL,
    configuration_hash VARCHAR(64) NOT NULL,
    id SERIAL NOT NULL,
    tenant_id INTEGER NOT NULL,
    project_workspace_id INTEGER NOT NULL,
    version INTEGER NOT NULL,
    created_by INTEGER NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_o2c_package_code UNIQUE (tenant_id, project_workspace_id, package_code),
    CONSTRAINT ck_o2c_package_estimate CHECK (estimated_value >= 0),
    CONSTRAINT ck_o2c_package_state CHECK (status IN ('DRAFT','PLANNED','CANCELLED')),
    FOREIGN KEY(responsible_user_id) REFERENCES user_accounts (id),
    FOREIGN KEY(updated_by) REFERENCES user_accounts (id),
    FOREIGN KEY(configuration_id) REFERENCES admin_configurations (id),
    FOREIGN KEY(tenant_id) REFERENCES tenants (id),
    FOREIGN KEY(project_workspace_id) REFERENCES enterprise_workspaces (id),
    FOREIGN KEY(created_by) REFERENCES user_accounts (id)
);

CREATE INDEX ix_contract_packages_project_workspace_id ON contract_packages (project_workspace_id);

CREATE INDEX ix_contract_packages_tenant_id ON contract_packages (tenant_id);

CREATE TABLE contract_history (
    entity_type VARCHAR(64) NOT NULL,
    entity_id INTEGER NOT NULL,
    entity_version INTEGER NOT NULL,
    previous_version INTEGER,
    event_type VARCHAR(100) NOT NULL,
    reason TEXT NOT NULL,
    effective_date DATE,
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

CREATE INDEX ix_o2c_history_entity ON contract_history (tenant_id, project_workspace_id, entity_type, entity_id);

CREATE INDEX ix_contract_history_project_workspace_id ON contract_history (project_workspace_id);

CREATE INDEX ix_contract_history_tenant_id ON contract_history (tenant_id);

CREATE TABLE contract_mappings (
    source_kind VARCHAR(32) NOT NULL,
    source_id INTEGER NOT NULL,
    target_kind VARCHAR(32) NOT NULL,
    target_id INTEGER NOT NULL,
    action VARCHAR(12) NOT NULL,
    effective_date DATE NOT NULL,
    target_snapshot JSON NOT NULL,
    source_hash VARCHAR(64) NOT NULL,
    id SERIAL NOT NULL,
    tenant_id INTEGER NOT NULL,
    project_workspace_id INTEGER NOT NULL,
    version INTEGER NOT NULL,
    created_by INTEGER NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_o2c_mapping_version UNIQUE (tenant_id, project_workspace_id, source_kind, source_id, version),
    CONSTRAINT ck_o2c_mapping_action CHECK (action IN ('SET','REMOVE')),
    FOREIGN KEY(tenant_id) REFERENCES tenants (id),
    FOREIGN KEY(project_workspace_id) REFERENCES enterprise_workspaces (id),
    FOREIGN KEY(created_by) REFERENCES user_accounts (id)
);

CREATE INDEX ix_o2c_mapping_source ON contract_mappings (tenant_id, project_workspace_id, source_kind, source_id);

CREATE INDEX ix_contract_mappings_tenant_id ON contract_mappings (tenant_id);

CREATE INDEX ix_contract_mappings_project_workspace_id ON contract_mappings (project_workspace_id);

CREATE TABLE operational_contracts (
    contract_number VARCHAR(120) NOT NULL,
    contract_package_id INTEGER NOT NULL,
    title VARCHAR(240) NOT NULL,
    description TEXT NOT NULL,
    contract_type VARCHAR(80) NOT NULL,
    commercial_model VARCHAR(80) NOT NULL,
    vendor_id INTEGER NOT NULL,
    counterparty JSON NOT NULL,
    currency VARCHAR(8) NOT NULL,
    original_contract_value NUMERIC(24, 8) NOT NULL,
    effective_date DATE NOT NULL,
    commencement_date DATE NOT NULL,
    planned_completion_date DATE NOT NULL,
    governing_reference TEXT NOT NULL,
    source_instrument_type VARCHAR(40),
    source_instrument_id INTEGER,
    source_version INTEGER,
    source_hash VARCHAR(64),
    source_reference JSON NOT NULL,
    status VARCHAR(24) NOT NULL,
    current_version_id INTEGER,
    executed_by INTEGER,
    executed_at TIMESTAMP WITHOUT TIME ZONE,
    execution_date DATE,
    execution_document JSON NOT NULL,
    supporting_documents JSON NOT NULL,
    updated_by INTEGER NOT NULL,
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    configuration_id INTEGER NOT NULL,
    configuration_hash VARCHAR(64) NOT NULL,
    id SERIAL NOT NULL,
    tenant_id INTEGER NOT NULL,
    project_workspace_id INTEGER NOT NULL,
    version INTEGER NOT NULL,
    created_by INTEGER NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_o2c_contract_number UNIQUE (tenant_id, project_workspace_id, contract_number),
    CONSTRAINT ck_o2c_contract_value CHECK (original_contract_value >= 0),
    CONSTRAINT ck_o2c_contract_dates CHECK (effective_date <= commencement_date AND commencement_date <= planned_completion_date),
    CONSTRAINT ck_o2c_contract_state CHECK (status IN ('DRAFT','APPROVED','EXECUTED','EFFECTIVE')),
    FOREIGN KEY(contract_package_id) REFERENCES contract_packages (id),
    FOREIGN KEY(vendor_id) REFERENCES procurement_vendors (id),
    FOREIGN KEY(executed_by) REFERENCES user_accounts (id),
    FOREIGN KEY(updated_by) REFERENCES user_accounts (id),
    FOREIGN KEY(configuration_id) REFERENCES admin_configurations (id),
    FOREIGN KEY(tenant_id) REFERENCES tenants (id),
    FOREIGN KEY(project_workspace_id) REFERENCES enterprise_workspaces (id),
    FOREIGN KEY(created_by) REFERENCES user_accounts (id)
);

CREATE INDEX ix_operational_contracts_tenant_id ON operational_contracts (tenant_id);

CREATE INDEX ix_operational_contracts_project_workspace_id ON operational_contracts (project_workspace_id);

CREATE INDEX ix_operational_contracts_contract_package_id ON operational_contracts (contract_package_id);

CREATE TABLE contract_versions (
    contract_id INTEGER NOT NULL,
    revision INTEGER NOT NULL,
    effective_date DATE NOT NULL,
    value NUMERIC(24, 8) NOT NULL,
    completion_date DATE NOT NULL,
    terms_reference TEXT NOT NULL,
    document_reference JSON NOT NULL,
    source_hash VARCHAR(64) NOT NULL,
    status VARCHAR(24) NOT NULL,
    approved_by INTEGER,
    approved_at TIMESTAMP WITHOUT TIME ZONE,
    supersedes_version_id INTEGER,
    source_change_id INTEGER,
    updated_by INTEGER NOT NULL,
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    configuration_id INTEGER NOT NULL,
    configuration_hash VARCHAR(64) NOT NULL,
    id SERIAL NOT NULL,
    tenant_id INTEGER NOT NULL,
    project_workspace_id INTEGER NOT NULL,
    version INTEGER NOT NULL,
    created_by INTEGER NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_o2c_contract_revision UNIQUE (tenant_id, project_workspace_id, contract_id, revision),
    CONSTRAINT ck_o2c_version_content CHECK (value >= 0 AND revision > 0 AND effective_date <= completion_date),
    CONSTRAINT ck_o2c_version_approval CHECK ((status = 'DRAFT' AND approved_by IS NULL AND approved_at IS NULL) OR (status = 'APPROVED' AND approved_by IS NOT NULL AND approved_at IS NOT NULL)),
    FOREIGN KEY(contract_id) REFERENCES operational_contracts (id),
    FOREIGN KEY(approved_by) REFERENCES user_accounts (id),
    UNIQUE (supersedes_version_id),
    FOREIGN KEY(supersedes_version_id) REFERENCES contract_versions (id),
    FOREIGN KEY(updated_by) REFERENCES user_accounts (id),
    FOREIGN KEY(configuration_id) REFERENCES admin_configurations (id),
    FOREIGN KEY(tenant_id) REFERENCES tenants (id),
    FOREIGN KEY(project_workspace_id) REFERENCES enterprise_workspaces (id),
    FOREIGN KEY(created_by) REFERENCES user_accounts (id)
);

CREATE INDEX ix_contract_versions_project_workspace_id ON contract_versions (project_workspace_id);

CREATE INDEX ix_contract_versions_tenant_id ON contract_versions (tenant_id);

CREATE INDEX ix_contract_versions_contract_id ON contract_versions (contract_id);

CREATE TABLE operational_contract_notices (
    contract_id INTEGER NOT NULL,
    notice_number VARCHAR(120) NOT NULL,
    notice_type VARCHAR(80) NOT NULL,
    sender VARCHAR(240) NOT NULL,
    recipient VARCHAR(240) NOT NULL,
    issue_date DATE NOT NULL,
    received_date DATE,
    subject VARCHAR(300) NOT NULL,
    event_reference TEXT,
    response_due_date DATE,
    document_reference JSON NOT NULL,
    status VARCHAR(24) NOT NULL,
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
    CONSTRAINT uq_o2c_notice_number UNIQUE (tenant_id, project_workspace_id, contract_id, notice_number),
    CONSTRAINT ck_o2c_notice_state CHECK (status IN ('ISSUED','RECEIVED','CLOSED')),
    FOREIGN KEY(contract_id) REFERENCES operational_contracts (id),
    FOREIGN KEY(configuration_id) REFERENCES admin_configurations (id),
    FOREIGN KEY(tenant_id) REFERENCES tenants (id),
    FOREIGN KEY(project_workspace_id) REFERENCES enterprise_workspaces (id),
    FOREIGN KEY(created_by) REFERENCES user_accounts (id)
);

CREATE INDEX ix_operational_contract_notices_project_workspace_id ON operational_contract_notices (project_workspace_id);

CREATE INDEX ix_operational_contract_notices_tenant_id ON operational_contract_notices (tenant_id);

CREATE INDEX ix_operational_contract_notices_contract_id ON operational_contract_notices (contract_id);

CREATE TABLE commercial_commitments (
    commitment_code VARCHAR(120) NOT NULL,
    revision INTEGER NOT NULL,
    contract_id INTEGER NOT NULL,
    contract_version_id INTEGER NOT NULL,
    vendor_id INTEGER NOT NULL,
    currency VARCHAR(8) NOT NULL,
    committed_amount NUMERIC(24, 8) NOT NULL,
    effective_date DATE NOT NULL,
    commercial_basis TEXT NOT NULL,
    source_hash VARCHAR(64) NOT NULL,
    contract_version_hash VARCHAR(64) NOT NULL,
    supersedes_id INTEGER,
    status VARCHAR(24) NOT NULL,
    approved_by INTEGER,
    approved_at TIMESTAMP WITHOUT TIME ZONE,
    updated_by INTEGER NOT NULL,
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    configuration_id INTEGER NOT NULL,
    configuration_hash VARCHAR(64) NOT NULL,
    id SERIAL NOT NULL,
    tenant_id INTEGER NOT NULL,
    project_workspace_id INTEGER NOT NULL,
    version INTEGER NOT NULL,
    created_by INTEGER NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_o2c_commitment_revision UNIQUE (tenant_id, project_workspace_id, commitment_code, revision),
    CONSTRAINT ck_o2c_commitment_content CHECK (committed_amount > 0 AND revision > 0),
    CONSTRAINT ck_o2c_commitment_approval CHECK ((status = 'DRAFT' AND approved_by IS NULL AND approved_at IS NULL) OR (status = 'APPROVED' AND approved_by IS NOT NULL AND approved_at IS NOT NULL)),
    FOREIGN KEY(contract_id) REFERENCES operational_contracts (id),
    FOREIGN KEY(contract_version_id) REFERENCES contract_versions (id),
    FOREIGN KEY(vendor_id) REFERENCES procurement_vendors (id),
    UNIQUE (supersedes_id),
    FOREIGN KEY(supersedes_id) REFERENCES commercial_commitments (id),
    FOREIGN KEY(approved_by) REFERENCES user_accounts (id),
    FOREIGN KEY(updated_by) REFERENCES user_accounts (id),
    FOREIGN KEY(configuration_id) REFERENCES admin_configurations (id),
    FOREIGN KEY(tenant_id) REFERENCES tenants (id),
    FOREIGN KEY(project_workspace_id) REFERENCES enterprise_workspaces (id),
    FOREIGN KEY(created_by) REFERENCES user_accounts (id)
);

CREATE INDEX ix_commercial_commitments_contract_id ON commercial_commitments (contract_id);

CREATE INDEX ix_commercial_commitments_tenant_id ON commercial_commitments (tenant_id);

CREATE INDEX ix_commercial_commitments_project_workspace_id ON commercial_commitments (project_workspace_id);

CREATE TABLE contract_sovs (
    contract_id INTEGER NOT NULL,
    contract_version_id INTEGER NOT NULL,
    code VARCHAR(120) NOT NULL,
    status VARCHAR(24) NOT NULL,
    currency VARCHAR(8) NOT NULL,
    total_value NUMERIC(24, 8) NOT NULL,
    published_by INTEGER,
    published_at TIMESTAMP WITHOUT TIME ZONE,
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
    CONSTRAINT uq_o2c_sov_code UNIQUE (tenant_id, project_workspace_id, contract_id, code),
    CONSTRAINT ck_o2c_sov_state CHECK (total_value > 0 AND status IN ('DRAFT','PUBLISHED')),
    FOREIGN KEY(contract_id) REFERENCES operational_contracts (id),
    FOREIGN KEY(contract_version_id) REFERENCES contract_versions (id),
    FOREIGN KEY(published_by) REFERENCES user_accounts (id),
    FOREIGN KEY(configuration_id) REFERENCES admin_configurations (id),
    FOREIGN KEY(tenant_id) REFERENCES tenants (id),
    FOREIGN KEY(project_workspace_id) REFERENCES enterprise_workspaces (id),
    FOREIGN KEY(created_by) REFERENCES user_accounts (id)
);

CREATE INDEX ix_contract_sovs_project_workspace_id ON contract_sovs (project_workspace_id);

CREATE INDEX ix_contract_sovs_contract_id ON contract_sovs (contract_id);

CREATE INDEX ix_contract_sovs_tenant_id ON contract_sovs (tenant_id);

CREATE TABLE contract_changes (
    contract_id INTEGER NOT NULL,
    base_version_id INTEGER NOT NULL,
    resulting_version_id INTEGER,
    change_number VARCHAR(120) NOT NULL,
    change_type VARCHAR(80) NOT NULL,
    description TEXT NOT NULL,
    value_delta NUMERIC(24, 8) NOT NULL,
    time_delta INTEGER NOT NULL,
    effective_date DATE NOT NULL,
    notice_id INTEGER,
    schedule_references JSON NOT NULL,
    document_reference JSON,
    status VARCHAR(24) NOT NULL,
    requested_by INTEGER,
    reviewed_by INTEGER,
    approved_by INTEGER,
    approved_at TIMESTAMP WITHOUT TIME ZONE,
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
    CONSTRAINT uq_o2c_change_number UNIQUE (tenant_id, project_workspace_id, contract_id, change_number),
    CONSTRAINT ck_o2c_change_state CHECK (status IN ('POTENTIAL','REQUESTED','UNDER_REVIEW','ORDER_APPROVED','REJECTED') AND (value_delta <> 0 OR time_delta <> 0)),
    FOREIGN KEY(contract_id) REFERENCES operational_contracts (id),
    FOREIGN KEY(base_version_id) REFERENCES contract_versions (id),
    FOREIGN KEY(resulting_version_id) REFERENCES contract_versions (id),
    FOREIGN KEY(notice_id) REFERENCES operational_contract_notices (id),
    FOREIGN KEY(requested_by) REFERENCES user_accounts (id),
    FOREIGN KEY(reviewed_by) REFERENCES user_accounts (id),
    FOREIGN KEY(approved_by) REFERENCES user_accounts (id),
    FOREIGN KEY(configuration_id) REFERENCES admin_configurations (id),
    FOREIGN KEY(tenant_id) REFERENCES tenants (id),
    FOREIGN KEY(project_workspace_id) REFERENCES enterprise_workspaces (id),
    FOREIGN KEY(created_by) REFERENCES user_accounts (id)
);

CREATE INDEX ix_contract_changes_project_workspace_id ON contract_changes (project_workspace_id);

CREATE INDEX ix_contract_changes_tenant_id ON contract_changes (tenant_id);

CREATE INDEX ix_contract_changes_contract_id ON contract_changes (contract_id);

CREATE TABLE contract_claims (
    contract_id INTEGER NOT NULL,
    claim_number VARCHAR(120) NOT NULL,
    claim_type VARCHAR(80) NOT NULL,
    cause TEXT NOT NULL,
    notice_id INTEGER,
    claimed_amount NUMERIC(24, 8) NOT NULL,
    claimed_time INTEGER NOT NULL,
    effective_date DATE NOT NULL,
    currency VARCHAR(8) NOT NULL,
    vendor_id INTEGER NOT NULL,
    documents JSON NOT NULL,
    status VARCHAR(24) NOT NULL,
    decided_by INTEGER,
    decided_at TIMESTAMP WITHOUT TIME ZONE,
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
    CONSTRAINT uq_o2c_claim_number UNIQUE (tenant_id, project_workspace_id, contract_id, claim_number),
    CONSTRAINT ck_o2c_claim_state CHECK (claimed_amount >= 0 AND claimed_time >= 0 AND status IN ('REGISTERED','ACCEPTED','REJECTED')),
    FOREIGN KEY(contract_id) REFERENCES operational_contracts (id),
    FOREIGN KEY(notice_id) REFERENCES operational_contract_notices (id),
    FOREIGN KEY(vendor_id) REFERENCES procurement_vendors (id),
    FOREIGN KEY(decided_by) REFERENCES user_accounts (id),
    FOREIGN KEY(configuration_id) REFERENCES admin_configurations (id),
    FOREIGN KEY(tenant_id) REFERENCES tenants (id),
    FOREIGN KEY(project_workspace_id) REFERENCES enterprise_workspaces (id),
    FOREIGN KEY(created_by) REFERENCES user_accounts (id)
);

CREATE INDEX ix_contract_claims_project_workspace_id ON contract_claims (project_workspace_id);

CREATE INDEX ix_contract_claims_contract_id ON contract_claims (contract_id);

CREATE INDEX ix_contract_claims_tenant_id ON contract_claims (tenant_id);

CREATE TABLE payment_applications (
    contract_id INTEGER NOT NULL,
    contract_version_id INTEGER NOT NULL,
    sov_id INTEGER NOT NULL,
    application_number VARCHAR(120) NOT NULL,
    period_id INTEGER NOT NULL,
    effective_date DATE NOT NULL,
    status VARCHAR(24) NOT NULL,
    currency VARCHAR(8) NOT NULL,
    applied_amount NUMERIC(24, 8) NOT NULL,
    document_reference JSON NOT NULL,
    reviewed_by INTEGER,
    reviewed_at TIMESTAMP WITHOUT TIME ZONE,
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
    CONSTRAINT uq_o2c_application_number UNIQUE (tenant_id, project_workspace_id, contract_id, application_number),
    CONSTRAINT ck_o2c_application_state CHECK (applied_amount > 0 AND status IN ('SUBMITTED','REVIEWED','REJECTED')),
    FOREIGN KEY(contract_id) REFERENCES operational_contracts (id),
    FOREIGN KEY(contract_version_id) REFERENCES contract_versions (id),
    FOREIGN KEY(sov_id) REFERENCES contract_sovs (id),
    FOREIGN KEY(period_id) REFERENCES project_controls_periods (id),
    FOREIGN KEY(reviewed_by) REFERENCES user_accounts (id),
    FOREIGN KEY(configuration_id) REFERENCES admin_configurations (id),
    FOREIGN KEY(tenant_id) REFERENCES tenants (id),
    FOREIGN KEY(project_workspace_id) REFERENCES enterprise_workspaces (id),
    FOREIGN KEY(created_by) REFERENCES user_accounts (id)
);

CREATE INDEX ix_payment_applications_contract_id ON payment_applications (contract_id);

CREATE INDEX ix_payment_applications_tenant_id ON payment_applications (tenant_id);

CREATE INDEX ix_payment_applications_project_workspace_id ON payment_applications (project_workspace_id);

CREATE TABLE contract_sov_lines (
    sov_id INTEGER NOT NULL,
    line_number VARCHAR(80) NOT NULL,
    description TEXT NOT NULL,
    uom VARCHAR(40) NOT NULL,
    quantity NUMERIC(24, 8) NOT NULL,
    unit_rate NUMERIC(24, 8) NOT NULL,
    original_value NUMERIC(24, 8) NOT NULL,
    current_value NUMERIC(24, 8) NOT NULL,
    retention_rule VARCHAR(80),
    retention_rate NUMERIC(10, 8) NOT NULL,
    mappings JSON NOT NULL,
    source_hash VARCHAR(64) NOT NULL,
    id SERIAL NOT NULL,
    tenant_id INTEGER NOT NULL,
    project_workspace_id INTEGER NOT NULL,
    version INTEGER NOT NULL,
    created_by INTEGER NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_o2c_sov_line_number UNIQUE (sov_id, line_number),
    CONSTRAINT ck_o2c_sov_line_value CHECK (quantity > 0 AND unit_rate > 0 AND current_value > 0 AND retention_rate BETWEEN 0 AND 1),
    FOREIGN KEY(sov_id) REFERENCES contract_sovs (id),
    FOREIGN KEY(tenant_id) REFERENCES tenants (id),
    FOREIGN KEY(project_workspace_id) REFERENCES enterprise_workspaces (id),
    FOREIGN KEY(created_by) REFERENCES user_accounts (id)
);

CREATE INDEX ix_contract_sov_lines_tenant_id ON contract_sov_lines (tenant_id);

CREATE INDEX ix_contract_sov_lines_project_workspace_id ON contract_sov_lines (project_workspace_id);

CREATE INDEX ix_contract_sov_lines_sov_id ON contract_sov_lines (sov_id);

CREATE TABLE cost_commercial_commitment_adoptions (
    source_domain VARCHAR(20) NOT NULL,
    source_entity_type VARCHAR(40) NOT NULL,
    source_entity_id INTEGER NOT NULL,
    source_version INTEGER NOT NULL,
    source_hash VARCHAR(64) NOT NULL,
    observed_at TIMESTAMP WITH TIME ZONE NOT NULL,
    effective_at DATE NOT NULL,
    cbs_id INTEGER NOT NULL,
    cost_code_id INTEGER NOT NULL,
    control_account_id INTEGER NOT NULL,
    consumer_status VARCHAR(16) NOT NULL,
    reason TEXT NOT NULL,
    source_snapshot JSON NOT NULL,
    mapping_reference JSON NOT NULL,
    id SERIAL NOT NULL,
    tenant_id INTEGER NOT NULL,
    project_workspace_id INTEGER NOT NULL,
    version INTEGER NOT NULL,
    created_by INTEGER NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_o2c_cost_adoption_stream UNIQUE (tenant_id, project_workspace_id, source_entity_id, version),
    CONSTRAINT ck_o2c_cost_adoption_source CHECK (source_domain = 'CONTRACTS' AND source_entity_type = 'COMMERCIAL_COMMITMENT' AND source_version > 0 AND version > 0),
    CONSTRAINT ck_o2c_cost_adoption_status CHECK (consumer_status IN ('ADOPTED','NOT_ADOPTED')),
    FOREIGN KEY(source_entity_id) REFERENCES commercial_commitments (id),
    FOREIGN KEY(cbs_id) REFERENCES cost_cbs (id),
    FOREIGN KEY(cost_code_id) REFERENCES cost_code_dictionary (id),
    FOREIGN KEY(control_account_id) REFERENCES cost_control_accounts (id),
    FOREIGN KEY(tenant_id) REFERENCES tenants (id),
    FOREIGN KEY(project_workspace_id) REFERENCES enterprise_workspaces (id),
    FOREIGN KEY(created_by) REFERENCES user_accounts (id)
);

CREATE INDEX ix_o2c_cost_adoption_history ON cost_commercial_commitment_adoptions (tenant_id, project_workspace_id, id);

CREATE INDEX ix_cost_commercial_commitment_adoptions_tenant_id ON cost_commercial_commitment_adoptions (tenant_id);

CREATE INDEX ix_cost_commercial_commitment_adoptions_project_workspace_id ON cost_commercial_commitment_adoptions (project_workspace_id);

CREATE TABLE operational_payment_certificates (
    application_id INTEGER NOT NULL,
    contract_id INTEGER NOT NULL,
    contract_version_id INTEGER NOT NULL,
    certificate_number VARCHAR(120) NOT NULL,
    effective_date DATE NOT NULL,
    status VARCHAR(24) NOT NULL,
    currency VARCHAR(8) NOT NULL,
    gross_amount NUMERIC(24, 8) NOT NULL,
    net_amount NUMERIC(24, 8) NOT NULL,
    document_reference JSON NOT NULL,
    approved_by INTEGER,
    approved_at TIMESTAMP WITHOUT TIME ZONE,
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
    CONSTRAINT uq_o2c_certificate_number UNIQUE (tenant_id, project_workspace_id, contract_id, certificate_number),
    CONSTRAINT ck_o2c_certificate_state CHECK (gross_amount > 0 AND net_amount BETWEEN 0 AND gross_amount AND status IN ('DRAFT','APPROVED','REJECTED')),
    FOREIGN KEY(application_id) REFERENCES payment_applications (id),
    FOREIGN KEY(contract_id) REFERENCES operational_contracts (id),
    FOREIGN KEY(contract_version_id) REFERENCES contract_versions (id),
    FOREIGN KEY(approved_by) REFERENCES user_accounts (id),
    FOREIGN KEY(configuration_id) REFERENCES admin_configurations (id),
    FOREIGN KEY(tenant_id) REFERENCES tenants (id),
    FOREIGN KEY(project_workspace_id) REFERENCES enterprise_workspaces (id),
    FOREIGN KEY(created_by) REFERENCES user_accounts (id)
);

CREATE INDEX ix_operational_payment_certificates_tenant_id ON operational_payment_certificates (tenant_id);

CREATE INDEX ix_operational_payment_certificates_contract_id ON operational_payment_certificates (contract_id);

CREATE INDEX ix_operational_payment_certificates_project_workspace_id ON operational_payment_certificates (project_workspace_id);

CREATE INDEX ix_operational_payment_certificates_application_id ON operational_payment_certificates (application_id);

CREATE TABLE payment_application_lines (
    application_id INTEGER NOT NULL,
    sov_line_id INTEGER NOT NULL,
    progress_measurement_id INTEGER NOT NULL,
    progress_reference JSON NOT NULL,
    quantity NUMERIC(24, 8) NOT NULL,
    applied_amount NUMERIC(24, 8) NOT NULL,
    id SERIAL NOT NULL,
    tenant_id INTEGER NOT NULL,
    project_workspace_id INTEGER NOT NULL,
    version INTEGER NOT NULL,
    created_by INTEGER NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_o2c_application_sov_line UNIQUE (application_id, sov_line_id),
    CONSTRAINT ck_o2c_application_line_positive CHECK (quantity > 0 AND applied_amount > 0),
    FOREIGN KEY(application_id) REFERENCES payment_applications (id),
    FOREIGN KEY(sov_line_id) REFERENCES contract_sov_lines (id),
    FOREIGN KEY(progress_measurement_id) REFERENCES progress_measurements (id),
    FOREIGN KEY(tenant_id) REFERENCES tenants (id),
    FOREIGN KEY(project_workspace_id) REFERENCES enterprise_workspaces (id),
    FOREIGN KEY(created_by) REFERENCES user_accounts (id)
);

CREATE INDEX ix_payment_application_lines_project_workspace_id ON payment_application_lines (project_workspace_id);

CREATE INDEX ix_payment_application_lines_application_id ON payment_application_lines (application_id);

CREATE INDEX ix_payment_application_lines_progress_measurement_id ON payment_application_lines (progress_measurement_id);

CREATE INDEX ix_payment_application_lines_tenant_id ON payment_application_lines (tenant_id);

CREATE INDEX ix_payment_application_lines_sov_line_id ON payment_application_lines (sov_line_id);

CREATE TABLE payment_certificate_lines (
    certificate_id INTEGER NOT NULL,
    application_line_id INTEGER NOT NULL,
    quantity NUMERIC(24, 8) NOT NULL,
    gross_amount NUMERIC(24, 8) NOT NULL,
    retention NUMERIC(24, 8) NOT NULL,
    advance_recovery NUMERIC(24, 8) NOT NULL,
    deductions NUMERIC(24, 8) NOT NULL,
    withholdings NUMERIC(24, 8) NOT NULL,
    other_adjustments NUMERIC(24, 8) NOT NULL,
    net_amount NUMERIC(24, 8) NOT NULL,
    id SERIAL NOT NULL,
    tenant_id INTEGER NOT NULL,
    project_workspace_id INTEGER NOT NULL,
    version INTEGER NOT NULL,
    created_by INTEGER NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_o2c_certificate_application_line UNIQUE (certificate_id, application_line_id),
    CONSTRAINT ck_o2c_certificate_line_value CHECK (quantity > 0 AND gross_amount > 0 AND net_amount BETWEEN 0 AND gross_amount AND retention >= 0 AND advance_recovery >= 0 AND deductions >= 0 AND withholdings >= 0 AND other_adjustments >= 0),
    FOREIGN KEY(certificate_id) REFERENCES operational_payment_certificates (id),
    FOREIGN KEY(application_line_id) REFERENCES payment_application_lines (id),
    FOREIGN KEY(tenant_id) REFERENCES tenants (id),
    FOREIGN KEY(project_workspace_id) REFERENCES enterprise_workspaces (id),
    FOREIGN KEY(created_by) REFERENCES user_accounts (id)
);

CREATE INDEX ix_payment_certificate_lines_project_workspace_id ON payment_certificate_lines (project_workspace_id);

CREATE INDEX ix_payment_certificate_lines_certificate_id ON payment_certificate_lines (certificate_id);

CREATE INDEX ix_payment_certificate_lines_tenant_id ON payment_certificate_lines (tenant_id);

CREATE INDEX ix_payment_certificate_lines_application_line_id ON payment_certificate_lines (application_line_id);

CREATE TABLE contract_finance_references (
    certificate_id INTEGER NOT NULL,
    certificate_hash VARCHAR(64) NOT NULL,
    source_system VARCHAR(120) NOT NULL,
    invoice_reference VARCHAR(260) NOT NULL,
    source_version INTEGER NOT NULL,
    source_hash VARCHAR(64) NOT NULL,
    amount NUMERIC(24, 8) NOT NULL,
    currency VARCHAR(8) NOT NULL,
    status_reference VARCHAR(120) NOT NULL,
    payment_status VARCHAR(120),
    supersedes_id INTEGER,
    id SERIAL NOT NULL,
    tenant_id INTEGER NOT NULL,
    project_workspace_id INTEGER NOT NULL,
    version INTEGER NOT NULL,
    created_by INTEGER NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_o2c_finance_ref_revision UNIQUE (tenant_id, project_workspace_id, source_system, invoice_reference, source_version),
    CONSTRAINT ck_o2c_finance_ref_amount CHECK (amount > 0 AND source_version > 0),
    FOREIGN KEY(certificate_id) REFERENCES operational_payment_certificates (id),
    FOREIGN KEY(supersedes_id) REFERENCES contract_finance_references (id),
    FOREIGN KEY(tenant_id) REFERENCES tenants (id),
    FOREIGN KEY(project_workspace_id) REFERENCES enterprise_workspaces (id),
    FOREIGN KEY(created_by) REFERENCES user_accounts (id)
);

CREATE INDEX ix_contract_finance_references_certificate_id ON contract_finance_references (certificate_id);

CREATE INDEX ix_contract_finance_references_project_workspace_id ON contract_finance_references (project_workspace_id);

CREATE INDEX ix_contract_finance_references_tenant_id ON contract_finance_references (tenant_id);

ALTER TABLE operational_contracts ADD CONSTRAINT fk_o2c_contract_current_version FOREIGN KEY(current_version_id) REFERENCES contract_versions (id);

