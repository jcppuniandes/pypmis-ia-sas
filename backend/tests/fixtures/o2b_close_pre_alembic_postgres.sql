-- Original pre-Alembic PostgreSQL schema: dd5b5149efc1b876e72b5f1a2ce390378bc44b81
-- Origin: backend/app/domain/models.py; application startup used Base.metadata.create_all.
-- Offline compiler: scripts/wave-o2b-close/generate_historical_bootstrap.py
-- Test fixture only; never apply to an existing or production database.
CREATE TYPE schedulesource AS ENUM ('p6_xer', 'p6_xml', 'ms_project_xml', 'ms_project_mpp');

CREATE TYPE importstatus AS ENUM ('received', 'validated', 'rejected', 'imported');

CREATE TYPE relationshiptype AS ENUM ('fs', 'ss', 'ff', 'sf');

CREATE TYPE costsource AS ENUM ('invoice', 'payroll', 'equipment', 'materials', 'commitment');

CREATE TYPE alertseverity AS ENUM ('green', 'amber', 'red');

CREATE TYPE workflowstatus AS ENUM ('draft', 'analyzing', 'approved', 'rejected', 'closed');

CREATE TABLE tenants (
	id SERIAL NOT NULL,
	name VARCHAR(160) NOT NULL,
	slug VARCHAR(80) NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (slug)
);

CREATE TABLE projects (
	id SERIAL NOT NULL,
	tenant_id INTEGER NOT NULL,
	code VARCHAR(40) NOT NULL,
	name VARCHAR(220) NOT NULL,
	phase VARCHAR(80) NOT NULL,
	currency VARCHAR(8) NOT NULL,
	start_date DATE,
	finish_date DATE,
	PRIMARY KEY (id),
	UNIQUE (tenant_id, code),
	FOREIGN KEY(tenant_id) REFERENCES tenants (id)
);

CREATE TABLE user_accounts (
	id SERIAL NOT NULL,
	tenant_id INTEGER NOT NULL,
	email VARCHAR(180) NOT NULL,
	full_name VARCHAR(180) NOT NULL,
	title VARCHAR(120) NOT NULL,
	status VARCHAR(40) NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (tenant_id, email),
	FOREIGN KEY(tenant_id) REFERENCES tenants (id)
);

CREATE TABLE business_process_templates (
	id SERIAL NOT NULL,
	tenant_id INTEGER NOT NULL,
	code VARCHAR(80) NOT NULL,
	name VARCHAR(160) NOT NULL,
	category VARCHAR(120) NOT NULL,
	description TEXT NOT NULL,
	form_schema TEXT NOT NULL,
	status VARCHAR(40) NOT NULL,
	version_no INTEGER NOT NULL,
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (tenant_id, code),
	FOREIGN KEY(tenant_id) REFERENCES tenants (id)
);

CREATE TABLE project_memberships (
	id SERIAL NOT NULL,
	tenant_id INTEGER NOT NULL,
	project_id INTEGER NOT NULL,
	user_id INTEGER NOT NULL,
	role VARCHAR(80) NOT NULL,
	can_capture_progress BOOLEAN NOT NULL,
	can_capture_cost BOOLEAN NOT NULL,
	can_approve_workflow BOOLEAN NOT NULL,
	can_manage_contract BOOLEAN NOT NULL,
	can_configure BOOLEAN NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (tenant_id, project_id, user_id),
	FOREIGN KEY(tenant_id) REFERENCES tenants (id),
	FOREIGN KEY(project_id) REFERENCES projects (id),
	FOREIGN KEY(user_id) REFERENCES user_accounts (id)
);

CREATE TABLE schedule_imports (
	id SERIAL NOT NULL,
	tenant_id INTEGER NOT NULL,
	project_id INTEGER NOT NULL,
	source schedulesource NOT NULL,
	file_name VARCHAR(260) NOT NULL,
	status importstatus NOT NULL,
	data_date DATE,
	baseline_name VARCHAR(160) NOT NULL,
	quality_score FLOAT NOT NULL,
	validation_summary TEXT NOT NULL,
	imported_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(project_id) REFERENCES projects (id)
);

CREATE TABLE control_periods (
	id SERIAL NOT NULL,
	tenant_id INTEGER NOT NULL,
	project_id INTEGER NOT NULL,
	period_label VARCHAR(40) NOT NULL,
	data_date DATE,
	status VARCHAR(40) NOT NULL,
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (tenant_id, project_id, period_label),
	FOREIGN KEY(project_id) REFERENCES projects (id)
);

CREATE TABLE wbs (
	id SERIAL NOT NULL,
	tenant_id INTEGER NOT NULL,
	project_id INTEGER NOT NULL,
	parent_id INTEGER,
	code VARCHAR(80) NOT NULL,
	name VARCHAR(220) NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(project_id) REFERENCES projects (id),
	FOREIGN KEY(parent_id) REFERENCES wbs (id)
);

CREATE TABLE business_process_instances (
	id SERIAL NOT NULL,
	tenant_id INTEGER NOT NULL,
	project_id INTEGER NOT NULL,
	trigger_entity_type VARCHAR(80) NOT NULL,
	trigger_entity_id INTEGER NOT NULL,
	process_code VARCHAR(80) NOT NULL,
	process_name VARCHAR(160) NOT NULL,
	record_no VARCHAR(80) NOT NULL,
	title VARCHAR(260) NOT NULL,
	status VARCHAR(40) NOT NULL,
	current_step VARCHAR(120) NOT NULL,
	ball_in_court VARCHAR(160) NOT NULL,
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(project_id) REFERENCES projects (id)
);

CREATE TABLE business_process_step_templates (
	id SERIAL NOT NULL,
	tenant_id INTEGER NOT NULL,
	template_id INTEGER NOT NULL,
	step_order INTEGER NOT NULL,
	name VARCHAR(120) NOT NULL,
	detail VARCHAR(260) NOT NULL,
	owner_role VARCHAR(160) NOT NULL,
	status VARCHAR(40) NOT NULL,
	tone VARCHAR(40) NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (tenant_id, template_id, step_order),
	FOREIGN KEY(tenant_id) REFERENCES tenants (id),
	FOREIGN KEY(template_id) REFERENCES business_process_templates (id)
);

CREATE TABLE business_process_transition_templates (
	id SERIAL NOT NULL,
	tenant_id INTEGER NOT NULL,
	template_id INTEGER NOT NULL,
	action VARCHAR(80) NOT NULL,
	label VARCHAR(120) NOT NULL,
	from_step VARCHAR(120) NOT NULL,
	to_step VARCHAR(120) NOT NULL,
	process_status VARCHAR(40) NOT NULL,
	ball_in_court VARCHAR(160) NOT NULL,
	from_status VARCHAR(40) NOT NULL,
	from_tone VARCHAR(40) NOT NULL,
	to_status VARCHAR(40) NOT NULL,
	to_tone VARCHAR(40) NOT NULL,
	requires_approval BOOLEAN NOT NULL,
	permission_key VARCHAR(80) NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(tenant_id) REFERENCES tenants (id),
	FOREIGN KEY(template_id) REFERENCES business_process_templates (id)
);

CREATE TABLE resources (
	id SERIAL NOT NULL,
	tenant_id INTEGER NOT NULL,
	project_id INTEGER NOT NULL,
	code VARCHAR(80) NOT NULL,
	name VARCHAR(180) NOT NULL,
	resource_type VARCHAR(60) NOT NULL,
	unit_of_measure VARCHAR(30) NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(project_id) REFERENCES projects (id)
);

CREATE TABLE forecast_scenarios (
	id SERIAL NOT NULL,
	tenant_id INTEGER NOT NULL,
	project_id INTEGER NOT NULL,
	period_label VARCHAR(40) NOT NULL,
	name VARCHAR(120) NOT NULL,
	method VARCHAR(120) NOT NULL,
	cpi_factor FLOAT NOT NULL,
	spi_factor FLOAT NOT NULL,
	eac FLOAT NOT NULL,
	etc FLOAT NOT NULL,
	vac FLOAT NOT NULL,
	completion_risk VARCHAR(40) NOT NULL,
	summary VARCHAR(360) NOT NULL,
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (tenant_id, project_id, period_label, name),
	FOREIGN KEY(project_id) REFERENCES projects (id)
);

CREATE TABLE contracts (
	id SERIAL NOT NULL,
	tenant_id INTEGER NOT NULL,
	project_id INTEGER NOT NULL,
	code VARCHAR(80) NOT NULL,
	title VARCHAR(220) NOT NULL,
	counterparty VARCHAR(180) NOT NULL,
	contract_type VARCHAR(80) NOT NULL,
	value FLOAT NOT NULL,
	status VARCHAR(40) NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (tenant_id, project_id, code),
	FOREIGN KEY(project_id) REFERENCES projects (id)
);

CREATE TABLE documents (
	id SERIAL NOT NULL,
	tenant_id INTEGER NOT NULL,
	project_id INTEGER NOT NULL,
	linked_entity_type VARCHAR(80) NOT NULL,
	linked_entity_id INTEGER NOT NULL,
	title VARCHAR(220) NOT NULL,
	doc_type VARCHAR(80) NOT NULL,
	uri VARCHAR(500) NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(project_id) REFERENCES projects (id)
);

CREATE TABLE audit_logs (
	id SERIAL NOT NULL,
	tenant_id INTEGER NOT NULL,
	project_id INTEGER,
	actor VARCHAR(160) NOT NULL,
	action VARCHAR(120) NOT NULL,
	entity_type VARCHAR(80) NOT NULL,
	entity_id INTEGER,
	payload TEXT NOT NULL,
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(project_id) REFERENCES projects (id)
);

CREATE TABLE schedule_validation_findings (
	id SERIAL NOT NULL,
	tenant_id INTEGER NOT NULL,
	project_id INTEGER NOT NULL,
	schedule_import_id INTEGER NOT NULL,
	check_code VARCHAR(80) NOT NULL,
	severity VARCHAR(40) NOT NULL,
	message VARCHAR(360) NOT NULL,
	item_count INTEGER NOT NULL,
	weight FLOAT NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(project_id) REFERENCES projects (id),
	FOREIGN KEY(schedule_import_id) REFERENCES schedule_imports (id)
);

CREATE TABLE baseline_versions (
	id SERIAL NOT NULL,
	tenant_id INTEGER NOT NULL,
	project_id INTEGER NOT NULL,
	schedule_import_id INTEGER NOT NULL,
	version_no INTEGER NOT NULL,
	name VARCHAR(160) NOT NULL,
	status VARCHAR(40) NOT NULL,
	data_date DATE,
	quality_score FLOAT NOT NULL,
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (tenant_id, project_id, version_no),
	FOREIGN KEY(project_id) REFERENCES projects (id),
	FOREIGN KEY(schedule_import_id) REFERENCES schedule_imports (id)
);

CREATE TABLE control_accounts (
	id SERIAL NOT NULL,
	tenant_id INTEGER NOT NULL,
	project_id INTEGER NOT NULL,
	wbs_id INTEGER NOT NULL,
	code VARCHAR(80) NOT NULL,
	name VARCHAR(220) NOT NULL,
	responsible VARCHAR(160) NOT NULL,
	discipline VARCHAR(80) NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(project_id) REFERENCES projects (id),
	FOREIGN KEY(wbs_id) REFERENCES wbs (id)
);

CREATE TABLE activity_relationships (
	id SERIAL NOT NULL,
	tenant_id INTEGER NOT NULL,
	project_id INTEGER NOT NULL,
	schedule_import_id INTEGER NOT NULL,
	predecessor_external_id VARCHAR(120) NOT NULL,
	successor_external_id VARCHAR(120) NOT NULL,
	relationship_type relationshiptype NOT NULL,
	lag_days FLOAT NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(project_id) REFERENCES projects (id),
	FOREIGN KEY(schedule_import_id) REFERENCES schedule_imports (id)
);

CREATE TABLE workflow_step_instances (
	id SERIAL NOT NULL,
	tenant_id INTEGER NOT NULL,
	project_id INTEGER NOT NULL,
	process_instance_id INTEGER NOT NULL,
	step_order INTEGER NOT NULL,
	name VARCHAR(120) NOT NULL,
	detail VARCHAR(260) NOT NULL,
	owner_role VARCHAR(160) NOT NULL,
	status VARCHAR(40) NOT NULL,
	tone VARCHAR(40) NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(project_id) REFERENCES projects (id),
	FOREIGN KEY(process_instance_id) REFERENCES business_process_instances (id)
);

CREATE TABLE contract_communications (
	id SERIAL NOT NULL,
	tenant_id INTEGER NOT NULL,
	project_id INTEGER NOT NULL,
	contract_id INTEGER,
	communication_type VARCHAR(80) NOT NULL,
	subject VARCHAR(260) NOT NULL,
	reference VARCHAR(160) NOT NULL,
	sent_on DATE NOT NULL,
	status VARCHAR(40) NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(project_id) REFERENCES projects (id),
	FOREIGN KEY(contract_id) REFERENCES contracts (id)
);

CREATE TABLE activities (
	id SERIAL NOT NULL,
	tenant_id INTEGER NOT NULL,
	project_id INTEGER NOT NULL,
	control_account_id INTEGER NOT NULL,
	code VARCHAR(80) NOT NULL,
	name VARCHAR(260) NOT NULL,
	logic_type VARCHAR(2) NOT NULL,
	baseline_start DATE,
	baseline_finish DATE,
	planned_percent FLOAT NOT NULL,
	critical_path BOOLEAN NOT NULL,
	lookahead_window VARCHAR(40) NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(project_id) REFERENCES projects (id),
	FOREIGN KEY(control_account_id) REFERENCES control_accounts (id)
);

CREATE TABLE work_packages (
	id SERIAL NOT NULL,
	tenant_id INTEGER NOT NULL,
	project_id INTEGER NOT NULL,
	control_account_id INTEGER,
	parent_id INTEGER,
	package_type VARCHAR(20) NOT NULL,
	code VARCHAR(80) NOT NULL,
	title VARCHAR(260) NOT NULL,
	discipline VARCHAR(80) NOT NULL,
	sequence_no INTEGER NOT NULL,
	path_of_construction VARCHAR(260) NOT NULL,
	owner_role VARCHAR(120) NOT NULL,
	readiness_status VARCHAR(60) NOT NULL,
	planned_start DATE,
	planned_finish DATE,
	progress_percent FLOAT NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (tenant_id, project_id, code),
	FOREIGN KEY(project_id) REFERENCES projects (id),
	FOREIGN KEY(control_account_id) REFERENCES control_accounts (id),
	FOREIGN KEY(parent_id) REFERENCES work_packages (id)
);

CREATE TABLE budgets (
	id SERIAL NOT NULL,
	tenant_id INTEGER NOT NULL,
	project_id INTEGER NOT NULL,
	control_account_id INTEGER NOT NULL,
	cbs_code VARCHAR(80) NOT NULL,
	bac FLOAT NOT NULL,
	cost_loaded_pv FLOAT NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(project_id) REFERENCES projects (id),
	FOREIGN KEY(control_account_id) REFERENCES control_accounts (id)
);

CREATE TABLE cost_records (
	id SERIAL NOT NULL,
	tenant_id INTEGER NOT NULL,
	project_id INTEGER NOT NULL,
	control_account_id INTEGER NOT NULL,
	source costsource NOT NULL,
	amount FLOAT NOT NULL,
	incurred_on DATE NOT NULL,
	description VARCHAR(260) NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(project_id) REFERENCES projects (id),
	FOREIGN KEY(control_account_id) REFERENCES control_accounts (id)
);

CREATE TABLE progress_records (
	id SERIAL NOT NULL,
	tenant_id INTEGER NOT NULL,
	project_id INTEGER NOT NULL,
	control_account_id INTEGER NOT NULL,
	physical_percent FLOAT NOT NULL,
	quantity_installed FLOAT NOT NULL,
	labor_hours FLOAT NOT NULL,
	reported_on DATE NOT NULL,
	evidence_ref VARCHAR(260) NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(project_id) REFERENCES projects (id),
	FOREIGN KEY(control_account_id) REFERENCES control_accounts (id)
);

CREATE TABLE kpis (
	id SERIAL NOT NULL,
	tenant_id INTEGER NOT NULL,
	project_id INTEGER NOT NULL,
	control_account_id INTEGER,
	period VARCHAR(40) NOT NULL,
	pv FLOAT NOT NULL,
	ev FLOAT NOT NULL,
	ac FLOAT NOT NULL,
	spi FLOAT NOT NULL,
	cpi FLOAT NOT NULL,
	sv FLOAT NOT NULL,
	cv FLOAT NOT NULL,
	bac FLOAT NOT NULL,
	eac FLOAT NOT NULL,
	etc FLOAT NOT NULL,
	vac FLOAT NOT NULL,
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(project_id) REFERENCES projects (id),
	FOREIGN KEY(control_account_id) REFERENCES control_accounts (id)
);

CREATE TABLE control_snapshots (
	id SERIAL NOT NULL,
	tenant_id INTEGER NOT NULL,
	project_id INTEGER NOT NULL,
	control_account_id INTEGER,
	period_label VARCHAR(40) NOT NULL,
	data_date DATE,
	pv FLOAT NOT NULL,
	ev FLOAT NOT NULL,
	ac FLOAT NOT NULL,
	spi FLOAT NOT NULL,
	cpi FLOAT NOT NULL,
	sv FLOAT NOT NULL,
	cv FLOAT NOT NULL,
	bac FLOAT NOT NULL,
	eac FLOAT NOT NULL,
	etc FLOAT NOT NULL,
	vac FLOAT NOT NULL,
	productivity_index FLOAT,
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (tenant_id, project_id, control_account_id, period_label),
	FOREIGN KEY(project_id) REFERENCES projects (id),
	FOREIGN KEY(control_account_id) REFERENCES control_accounts (id)
);

CREATE TABLE alerts (
	id SERIAL NOT NULL,
	tenant_id INTEGER NOT NULL,
	project_id INTEGER NOT NULL,
	control_account_id INTEGER,
	severity alertseverity NOT NULL,
	rule VARCHAR(120) NOT NULL,
	message VARCHAR(360) NOT NULL,
	recommendation VARCHAR(360) NOT NULL,
	status VARCHAR(40) NOT NULL,
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(project_id) REFERENCES projects (id),
	FOREIGN KEY(control_account_id) REFERENCES control_accounts (id)
);

CREATE TABLE change_requests (
	id SERIAL NOT NULL,
	tenant_id INTEGER NOT NULL,
	project_id INTEGER NOT NULL,
	control_account_id INTEGER,
	title VARCHAR(220) NOT NULL,
	deviation TEXT NOT NULL,
	cost_impact FLOAT NOT NULL,
	schedule_impact_days INTEGER NOT NULL,
	status workflowstatus NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(project_id) REFERENCES projects (id),
	FOREIGN KEY(control_account_id) REFERENCES control_accounts (id)
);

CREATE TABLE claims (
	id SERIAL NOT NULL,
	tenant_id INTEGER NOT NULL,
	project_id INTEGER NOT NULL,
	control_account_id INTEGER,
	title VARCHAR(220) NOT NULL,
	causality TEXT NOT NULL,
	impact TEXT NOT NULL,
	evidence_summary TEXT NOT NULL,
	status workflowstatus NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(project_id) REFERENCES projects (id),
	FOREIGN KEY(control_account_id) REFERENCES control_accounts (id)
);

CREATE TABLE events (
	id SERIAL NOT NULL,
	tenant_id INTEGER NOT NULL,
	project_id INTEGER NOT NULL,
	control_account_id INTEGER,
	event_type VARCHAR(80) NOT NULL,
	title VARCHAR(220) NOT NULL,
	occurred_on DATE NOT NULL,
	contractual_notice_required BOOLEAN NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(project_id) REFERENCES projects (id),
	FOREIGN KEY(control_account_id) REFERENCES control_accounts (id)
);

CREATE TABLE schedule_activity_maps (
	id SERIAL NOT NULL,
	tenant_id INTEGER NOT NULL,
	project_id INTEGER NOT NULL,
	schedule_import_id INTEGER NOT NULL,
	activity_id INTEGER,
	external_activity_id VARCHAR(120) NOT NULL,
	wbs_code VARCHAR(120) NOT NULL,
	activity_name VARCHAR(260) NOT NULL,
	planned_start DATE,
	planned_finish DATE,
	total_float_days FLOAT NOT NULL,
	critical_path BOOLEAN NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(project_id) REFERENCES projects (id),
	FOREIGN KEY(schedule_import_id) REFERENCES schedule_imports (id),
	FOREIGN KEY(activity_id) REFERENCES activities (id)
);

CREATE TABLE work_package_constraints (
	id SERIAL NOT NULL,
	tenant_id INTEGER NOT NULL,
	project_id INTEGER NOT NULL,
	work_package_id INTEGER NOT NULL,
	constraint_type VARCHAR(80) NOT NULL,
	description VARCHAR(360) NOT NULL,
	owner_role VARCHAR(120) NOT NULL,
	required_by DATE,
	status VARCHAR(40) NOT NULL,
	blocking BOOLEAN NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(project_id) REFERENCES projects (id),
	FOREIGN KEY(work_package_id) REFERENCES work_packages (id)
);

CREATE TABLE claim_entitlement_items (
	id SERIAL NOT NULL,
	tenant_id INTEGER NOT NULL,
	project_id INTEGER NOT NULL,
	claim_id INTEGER NOT NULL,
	practice_source VARCHAR(40) NOT NULL,
	category VARCHAR(120) NOT NULL,
	element VARCHAR(220) NOT NULL,
	requirement TEXT NOT NULL,
	assessment TEXT NOT NULL,
	evidence_ref VARCHAR(260) NOT NULL,
	status VARCHAR(40) NOT NULL,
	weight FLOAT NOT NULL,
	score FLOAT NOT NULL,
	sequence_no INTEGER NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(project_id) REFERENCES projects (id),
	FOREIGN KEY(claim_id) REFERENCES claims (id)
);

CREATE TABLE contract_notices (
	id SERIAL NOT NULL,
	tenant_id INTEGER NOT NULL,
	project_id INTEGER NOT NULL,
	contract_id INTEGER,
	claim_id INTEGER,
	change_request_id INTEGER,
	notice_type VARCHAR(80) NOT NULL,
	subject VARCHAR(260) NOT NULL,
	reference VARCHAR(120) NOT NULL,
	event_date DATE,
	notice_date DATE,
	due_date DATE,
	status VARCHAR(40) NOT NULL,
	days_late INTEGER NOT NULL,
	compliance_status VARCHAR(40) NOT NULL,
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(project_id) REFERENCES projects (id),
	FOREIGN KEY(contract_id) REFERENCES contracts (id),
	FOREIGN KEY(claim_id) REFERENCES claims (id),
	FOREIGN KEY(change_request_id) REFERENCES change_requests (id)
);

CREATE TABLE claim_impact_analyses (
	id SERIAL NOT NULL,
	tenant_id INTEGER NOT NULL,
	project_id INTEGER NOT NULL,
	claim_id INTEGER NOT NULL,
	method VARCHAR(120) NOT NULL,
	impacted_activity VARCHAR(160) NOT NULL,
	cause TEXT NOT NULL,
	effect TEXT NOT NULL,
	schedule_impact_days INTEGER NOT NULL,
	cost_impact FLOAT NOT NULL,
	productivity_loss_percent FLOAT NOT NULL,
	evidence_ref VARCHAR(260) NOT NULL,
	confidence_score FLOAT NOT NULL,
	status VARCHAR(40) NOT NULL,
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(project_id) REFERENCES projects (id),
	FOREIGN KEY(claim_id) REFERENCES claims (id)
);

CREATE TABLE control_account_mappings (
	id SERIAL NOT NULL,
	tenant_id INTEGER NOT NULL,
	project_id INTEGER NOT NULL,
	schedule_import_id INTEGER NOT NULL,
	schedule_activity_map_id INTEGER NOT NULL,
	activity_id INTEGER,
	control_account_id INTEGER,
	wbs_code VARCHAR(120) NOT NULL,
	wbs_name VARCHAR(220) NOT NULL,
	cbs_code VARCHAR(120) NOT NULL,
	mapping_rule VARCHAR(120) NOT NULL,
	planned_cost FLOAT NOT NULL,
	planned_value FLOAT NOT NULL,
	planned_percent FLOAT NOT NULL,
	status VARCHAR(40) NOT NULL,
	review_note VARCHAR(260) NOT NULL,
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (tenant_id, project_id, schedule_activity_map_id),
	FOREIGN KEY(project_id) REFERENCES projects (id),
	FOREIGN KEY(schedule_import_id) REFERENCES schedule_imports (id),
	FOREIGN KEY(schedule_activity_map_id) REFERENCES schedule_activity_maps (id),
	FOREIGN KEY(activity_id) REFERENCES activities (id),
	FOREIGN KEY(control_account_id) REFERENCES control_accounts (id)
);

CREATE INDEX ix_activities_code ON activities (code);

CREATE INDEX ix_activities_control_account_id ON activities (control_account_id);

CREATE INDEX ix_activities_project_id ON activities (project_id);

CREATE INDEX ix_activities_tenant_id ON activities (tenant_id);

CREATE INDEX ix_activity_relationships_predecessor_external_id ON activity_relationships (predecessor_external_id);

CREATE INDEX ix_activity_relationships_project_id ON activity_relationships (project_id);

CREATE INDEX ix_activity_relationships_schedule_import_id ON activity_relationships (schedule_import_id);

CREATE INDEX ix_activity_relationships_successor_external_id ON activity_relationships (successor_external_id);

CREATE INDEX ix_activity_relationships_tenant_id ON activity_relationships (tenant_id);

CREATE INDEX ix_alerts_control_account_id ON alerts (control_account_id);

CREATE INDEX ix_alerts_project_id ON alerts (project_id);

CREATE INDEX ix_alerts_tenant_id ON alerts (tenant_id);

CREATE INDEX ix_audit_logs_project_id ON audit_logs (project_id);

CREATE INDEX ix_audit_logs_tenant_id ON audit_logs (tenant_id);

CREATE INDEX ix_baseline_versions_project_id ON baseline_versions (project_id);

CREATE INDEX ix_baseline_versions_schedule_import_id ON baseline_versions (schedule_import_id);

CREATE INDEX ix_baseline_versions_tenant_id ON baseline_versions (tenant_id);

CREATE INDEX ix_budgets_control_account_id ON budgets (control_account_id);

CREATE INDEX ix_budgets_project_id ON budgets (project_id);

CREATE INDEX ix_budgets_tenant_id ON budgets (tenant_id);

CREATE INDEX ix_business_process_instances_process_code ON business_process_instances (process_code);

CREATE INDEX ix_business_process_instances_project_id ON business_process_instances (project_id);

CREATE INDEX ix_business_process_instances_record_no ON business_process_instances (record_no);

CREATE INDEX ix_business_process_instances_tenant_id ON business_process_instances (tenant_id);

CREATE INDEX ix_business_process_instances_trigger_entity_id ON business_process_instances (trigger_entity_id);

CREATE INDEX ix_business_process_step_templates_template_id ON business_process_step_templates (template_id);

CREATE INDEX ix_business_process_step_templates_tenant_id ON business_process_step_templates (tenant_id);

CREATE INDEX ix_business_process_templates_code ON business_process_templates (code);

CREATE INDEX ix_business_process_templates_tenant_id ON business_process_templates (tenant_id);

CREATE INDEX ix_business_process_transition_templates_action ON business_process_transition_templates (action);

CREATE INDEX ix_business_process_transition_templates_template_id ON business_process_transition_templates (template_id);

CREATE INDEX ix_business_process_transition_templates_tenant_id ON business_process_transition_templates (tenant_id);

CREATE INDEX ix_change_requests_control_account_id ON change_requests (control_account_id);

CREATE INDEX ix_change_requests_project_id ON change_requests (project_id);

CREATE INDEX ix_change_requests_tenant_id ON change_requests (tenant_id);

CREATE INDEX ix_claim_entitlement_items_category ON claim_entitlement_items (category);

CREATE INDEX ix_claim_entitlement_items_claim_id ON claim_entitlement_items (claim_id);

CREATE INDEX ix_claim_entitlement_items_project_id ON claim_entitlement_items (project_id);

CREATE INDEX ix_claim_entitlement_items_tenant_id ON claim_entitlement_items (tenant_id);

CREATE INDEX ix_claim_impact_analyses_claim_id ON claim_impact_analyses (claim_id);

CREATE INDEX ix_claim_impact_analyses_project_id ON claim_impact_analyses (project_id);

CREATE INDEX ix_claim_impact_analyses_tenant_id ON claim_impact_analyses (tenant_id);

CREATE INDEX ix_claims_control_account_id ON claims (control_account_id);

CREATE INDEX ix_claims_project_id ON claims (project_id);

CREATE INDEX ix_claims_tenant_id ON claims (tenant_id);

CREATE INDEX ix_contract_communications_contract_id ON contract_communications (contract_id);

CREATE INDEX ix_contract_communications_project_id ON contract_communications (project_id);

CREATE INDEX ix_contract_communications_tenant_id ON contract_communications (tenant_id);

CREATE INDEX ix_contract_notices_change_request_id ON contract_notices (change_request_id);

CREATE INDEX ix_contract_notices_claim_id ON contract_notices (claim_id);

CREATE INDEX ix_contract_notices_contract_id ON contract_notices (contract_id);

CREATE INDEX ix_contract_notices_project_id ON contract_notices (project_id);

CREATE INDEX ix_contract_notices_tenant_id ON contract_notices (tenant_id);

CREATE INDEX ix_contracts_code ON contracts (code);

CREATE INDEX ix_contracts_project_id ON contracts (project_id);

CREATE INDEX ix_contracts_tenant_id ON contracts (tenant_id);

CREATE INDEX ix_control_account_mappings_activity_id ON control_account_mappings (activity_id);

CREATE INDEX ix_control_account_mappings_control_account_id ON control_account_mappings (control_account_id);

CREATE INDEX ix_control_account_mappings_project_id ON control_account_mappings (project_id);

CREATE INDEX ix_control_account_mappings_schedule_activity_map_id ON control_account_mappings (schedule_activity_map_id);

CREATE INDEX ix_control_account_mappings_schedule_import_id ON control_account_mappings (schedule_import_id);

CREATE INDEX ix_control_account_mappings_tenant_id ON control_account_mappings (tenant_id);

CREATE INDEX ix_control_accounts_code ON control_accounts (code);

CREATE INDEX ix_control_accounts_project_id ON control_accounts (project_id);

CREATE INDEX ix_control_accounts_tenant_id ON control_accounts (tenant_id);

CREATE INDEX ix_control_accounts_wbs_id ON control_accounts (wbs_id);

CREATE INDEX ix_control_periods_period_label ON control_periods (period_label);

CREATE INDEX ix_control_periods_project_id ON control_periods (project_id);

CREATE INDEX ix_control_periods_tenant_id ON control_periods (tenant_id);

CREATE INDEX ix_control_snapshots_control_account_id ON control_snapshots (control_account_id);

CREATE INDEX ix_control_snapshots_period_label ON control_snapshots (period_label);

CREATE INDEX ix_control_snapshots_project_id ON control_snapshots (project_id);

CREATE INDEX ix_control_snapshots_tenant_id ON control_snapshots (tenant_id);

CREATE INDEX ix_cost_records_control_account_id ON cost_records (control_account_id);

CREATE INDEX ix_cost_records_project_id ON cost_records (project_id);

CREATE INDEX ix_cost_records_tenant_id ON cost_records (tenant_id);

CREATE INDEX ix_documents_project_id ON documents (project_id);

CREATE INDEX ix_documents_tenant_id ON documents (tenant_id);

CREATE INDEX ix_events_control_account_id ON events (control_account_id);

CREATE INDEX ix_events_project_id ON events (project_id);

CREATE INDEX ix_events_tenant_id ON events (tenant_id);

CREATE INDEX ix_forecast_scenarios_period_label ON forecast_scenarios (period_label);

CREATE INDEX ix_forecast_scenarios_project_id ON forecast_scenarios (project_id);

CREATE INDEX ix_forecast_scenarios_tenant_id ON forecast_scenarios (tenant_id);

CREATE INDEX ix_kpis_control_account_id ON kpis (control_account_id);

CREATE INDEX ix_kpis_project_id ON kpis (project_id);

CREATE INDEX ix_kpis_tenant_id ON kpis (tenant_id);

CREATE INDEX ix_progress_records_control_account_id ON progress_records (control_account_id);

CREATE INDEX ix_progress_records_project_id ON progress_records (project_id);

CREATE INDEX ix_progress_records_tenant_id ON progress_records (tenant_id);

CREATE INDEX ix_project_memberships_project_id ON project_memberships (project_id);

CREATE INDEX ix_project_memberships_role ON project_memberships (role);

CREATE INDEX ix_project_memberships_tenant_id ON project_memberships (tenant_id);

CREATE INDEX ix_project_memberships_user_id ON project_memberships (user_id);

CREATE INDEX ix_projects_code ON projects (code);

CREATE INDEX ix_projects_tenant_id ON projects (tenant_id);

CREATE INDEX ix_resources_code ON resources (code);

CREATE INDEX ix_resources_project_id ON resources (project_id);

CREATE INDEX ix_resources_tenant_id ON resources (tenant_id);

CREATE INDEX ix_schedule_activity_maps_activity_id ON schedule_activity_maps (activity_id);

CREATE INDEX ix_schedule_activity_maps_external_activity_id ON schedule_activity_maps (external_activity_id);

CREATE INDEX ix_schedule_activity_maps_project_id ON schedule_activity_maps (project_id);

CREATE INDEX ix_schedule_activity_maps_schedule_import_id ON schedule_activity_maps (schedule_import_id);

CREATE INDEX ix_schedule_activity_maps_tenant_id ON schedule_activity_maps (tenant_id);

CREATE INDEX ix_schedule_imports_project_id ON schedule_imports (project_id);

CREATE INDEX ix_schedule_imports_tenant_id ON schedule_imports (tenant_id);

CREATE INDEX ix_schedule_validation_findings_check_code ON schedule_validation_findings (check_code);

CREATE INDEX ix_schedule_validation_findings_project_id ON schedule_validation_findings (project_id);

CREATE INDEX ix_schedule_validation_findings_schedule_import_id ON schedule_validation_findings (schedule_import_id);

CREATE INDEX ix_schedule_validation_findings_tenant_id ON schedule_validation_findings (tenant_id);

CREATE INDEX ix_user_accounts_email ON user_accounts (email);

CREATE INDEX ix_user_accounts_tenant_id ON user_accounts (tenant_id);

CREATE INDEX ix_wbs_code ON wbs (code);

CREATE INDEX ix_wbs_project_id ON wbs (project_id);

CREATE INDEX ix_wbs_tenant_id ON wbs (tenant_id);

CREATE INDEX ix_work_package_constraints_constraint_type ON work_package_constraints (constraint_type);

CREATE INDEX ix_work_package_constraints_project_id ON work_package_constraints (project_id);

CREATE INDEX ix_work_package_constraints_tenant_id ON work_package_constraints (tenant_id);

CREATE INDEX ix_work_package_constraints_work_package_id ON work_package_constraints (work_package_id);

CREATE INDEX ix_work_packages_code ON work_packages (code);

CREATE INDEX ix_work_packages_control_account_id ON work_packages (control_account_id);

CREATE INDEX ix_work_packages_package_type ON work_packages (package_type);

CREATE INDEX ix_work_packages_parent_id ON work_packages (parent_id);

CREATE INDEX ix_work_packages_project_id ON work_packages (project_id);

CREATE INDEX ix_work_packages_tenant_id ON work_packages (tenant_id);

CREATE INDEX ix_workflow_step_instances_process_instance_id ON workflow_step_instances (process_instance_id);

CREATE INDEX ix_workflow_step_instances_project_id ON workflow_step_instances (project_id);

CREATE INDEX ix_workflow_step_instances_tenant_id ON workflow_step_instances (tenant_id);
