CREATE TABLE quality_plans (
	scope TEXT NOT NULL, 
	responsible_user_id INTEGER NOT NULL, 
	source_references JSON NOT NULL, 
	document_references JSON NOT NULL, 
	supersedes_id INTEGER, 
	code VARCHAR(120) NOT NULL, 
	title VARCHAR(300) NOT NULL, 
	revision INTEGER NOT NULL, 
	effective_date DATE NOT NULL, 
	status VARCHAR(24) NOT NULL, 
	submitted_by INTEGER, 
	submitted_at TIMESTAMP WITHOUT TIME ZONE, 
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
	CONSTRAINT uq_quality_plan_revision UNIQUE (tenant_id, project_workspace_id, code, revision), 
	CONSTRAINT ck_quality_plan_state CHECK (revision > 0 AND status IN ('DRAFT','SUBMITTED','APPROVED')), 
	FOREIGN KEY(responsible_user_id) REFERENCES user_accounts (id), 
	UNIQUE (supersedes_id), 
	FOREIGN KEY(supersedes_id) REFERENCES quality_plans (id), 
	FOREIGN KEY(submitted_by) REFERENCES user_accounts (id), 
	FOREIGN KEY(approved_by) REFERENCES user_accounts (id), 
	FOREIGN KEY(updated_by) REFERENCES user_accounts (id), 
	FOREIGN KEY(configuration_id) REFERENCES admin_configurations (id), 
	FOREIGN KEY(tenant_id) REFERENCES tenants (id), 
	FOREIGN KEY(project_workspace_id) REFERENCES enterprise_workspaces (id), 
	FOREIGN KEY(created_by) REFERENCES user_accounts (id)
);

CREATE INDEX ix_quality_plans_tenant_id ON quality_plans (tenant_id);

CREATE INDEX ix_quality_plans_project_workspace_id ON quality_plans (project_workspace_id);

CREATE TABLE quality_inspection_requests (
	inspection_type VARCHAR(80) NOT NULL, 
	reinspection_of_id INTEGER, 
	corrective_action_id INTEGER, 
	request_number VARCHAR(120) NOT NULL, 
	itp_item_id INTEGER NOT NULL, 
	subject_key VARCHAR(240) NOT NULL, 
	subject_reference JSON NOT NULL, 
	quantity NUMERIC(24, 8), 
	uom VARCHAR(40), 
	requested_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	requested_for TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	requester_user_id INTEGER NOT NULL, 
	inspector_user_id INTEGER NOT NULL, 
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
	CONSTRAINT uq_quality_inspection_request UNIQUE (tenant_id, project_workspace_id, request_number), 
	CONSTRAINT ck_quality_inspection_request_state CHECK (status IN ('DRAFT','SUBMITTED','SCHEDULED','IN_INSPECTION','COMPLETED','CANCELLED')), 
	CONSTRAINT ck_quality_inspection_request_times CHECK (requested_at <= requested_for AND (quantity IS NULL OR quantity > 0))
);

CREATE INDEX ix_quality_inspection_requests_reinspection_of_id ON quality_inspection_requests (reinspection_of_id);

CREATE INDEX ix_quality_inspection_requests_project_workspace_id ON quality_inspection_requests (project_workspace_id);

CREATE INDEX ix_quality_inspection_requests_tenant_id ON quality_inspection_requests (tenant_id);

CREATE INDEX ix_quality_inspection_requests_itp_item_id ON quality_inspection_requests (itp_item_id);

CREATE INDEX ix_quality_inspection_requests_corrective_action_id ON quality_inspection_requests (corrective_action_id);

CREATE INDEX ix_quality_inspection_requests_subject_key ON quality_inspection_requests (subject_key);

CREATE TABLE quality_inspection_records (
	request_id INTEGER NOT NULL, 
	inspected_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	checklist_template JSON NOT NULL, 
	checklist_responses JSON NOT NULL, 
	record_number VARCHAR(120) NOT NULL, 
	itp_item_id INTEGER NOT NULL, 
	subject_key VARCHAR(240) NOT NULL, 
	subject_reference JSON NOT NULL, 
	quantity NUMERIC(24, 8), 
	uom VARCHAR(40), 
	engineering_reference JSON NOT NULL, 
	requirement_reference JSON NOT NULL, 
	inspector_user_id INTEGER NOT NULL, 
	result VARCHAR(32) NOT NULL, 
	comments TEXT NOT NULL, 
	document_references JSON NOT NULL, 
	submitted_by INTEGER, 
	submitted_at TIMESTAMP WITHOUT TIME ZONE, 
	closed_by INTEGER, 
	closed_at TIMESTAMP WITHOUT TIME ZONE, 
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
	CONSTRAINT uq_quality_inspection_record UNIQUE (tenant_id, project_workspace_id, record_number), 
	CONSTRAINT ck_quality_inspection_result CHECK (status IN ('DRAFT','SUBMITTED','CLOSED') AND result IN ('PASS','FAIL','CONDITIONAL','NOT_APPLICABLE')), 
	CONSTRAINT ck_quality_inspection_closed CHECK ((status <> 'CLOSED' AND closed_by IS NULL AND closed_at IS NULL) OR (status='CLOSED' AND closed_by IS NOT NULL AND closed_at IS NOT NULL)), 
	UNIQUE (request_id)
);

CREATE INDEX ix_quality_inspection_records_itp_item_id ON quality_inspection_records (itp_item_id);

CREATE INDEX ix_quality_inspection_records_subject_key ON quality_inspection_records (subject_key);

CREATE INDEX ix_quality_inspection_records_tenant_id ON quality_inspection_records (tenant_id);

CREATE INDEX ix_quality_inspection_records_project_workspace_id ON quality_inspection_records (project_workspace_id);

CREATE TABLE quality_history (
	entity_type VARCHAR(80) NOT NULL, 
	entity_id INTEGER NOT NULL, 
	entity_version INTEGER NOT NULL, 
	previous_version INTEGER, 
	previous_state VARCHAR(32), 
	new_state VARCHAR(32), 
	event_type VARCHAR(120) NOT NULL, 
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

CREATE INDEX ix_quality_history_tenant_id ON quality_history (tenant_id);

CREATE INDEX ix_quality_history_entity ON quality_history (tenant_id, project_workspace_id, entity_type, entity_id);

CREATE INDEX ix_quality_history_project_workspace_id ON quality_history (project_workspace_id);

CREATE TABLE quality_ncrs (
	ncr_number VARCHAR(120) NOT NULL, 
	title VARCHAR(300) NOT NULL, 
	description TEXT NOT NULL, 
	category VARCHAR(80) NOT NULL, 
	severity VARCHAR(40) NOT NULL, 
	responsible_user_id INTEGER NOT NULL, 
	subject_key VARCHAR(500) NOT NULL, 
	subject_reference JSON NOT NULL, 
	inspection_record_id INTEGER, 
	test_record_id INTEGER, 
	requirement_reference TEXT NOT NULL, 
	detected_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	due_date DATE, 
	document_reference JSON NOT NULL, 
	disposition_id INTEGER, 
	disposition_reference JSON, 
	status VARCHAR(30) NOT NULL, 
	issued_by INTEGER, 
	issued_at TIMESTAMP WITHOUT TIME ZONE, 
	verified_by INTEGER, 
	verified_at TIMESTAMP WITHOUT TIME ZONE, 
	closed_by INTEGER, 
	closed_at TIMESTAMP WITHOUT TIME ZONE, 
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
	CONSTRAINT uq_quality_ncr_number UNIQUE (tenant_id, project_workspace_id, ncr_number), 
	CONSTRAINT ck_quality_ncr_status CHECK (status IN ('DRAFT','ISSUED','UNDER_REVIEW','DISPOSITIONED','CORRECTED','VERIFIED','CLOSED','REJECTED','CANCELLED')), 
	CONSTRAINT ck_quality_ncr_single_result CHECK (inspection_record_id IS NULL OR test_record_id IS NULL), 
	CONSTRAINT ck_quality_ncr_disposition_required CHECK (status NOT IN ('DISPOSITIONED','CORRECTED','VERIFIED','CLOSED') OR disposition_id IS NOT NULL)
);

CREATE INDEX ix_quality_ncr_subject_status ON quality_ncrs (tenant_id, project_workspace_id, subject_key, status);

CREATE INDEX ix_quality_ncrs_tenant_id ON quality_ncrs (tenant_id);

CREATE INDEX ix_quality_ncrs_subject_key ON quality_ncrs (subject_key);

CREATE INDEX ix_quality_ncrs_project_workspace_id ON quality_ncrs (project_workspace_id);

CREATE TABLE quality_dispositions (
	ncr_id INTEGER NOT NULL, 
	disposition_code VARCHAR(120) NOT NULL, 
	disposition_type VARCHAR(80) NOT NULL, 
	description TEXT NOT NULL, 
	engineering_decision_reference JSON, 
	document_reference JSON NOT NULL, 
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
	CONSTRAINT uq_quality_disposition_code UNIQUE (tenant_id, project_workspace_id, disposition_code), 
	CONSTRAINT ck_quality_disposition_status CHECK (status IN ('PROPOSED','APPROVED','REJECTED'))
);

CREATE INDEX ix_quality_dispositions_ncr_id ON quality_dispositions (ncr_id);

CREATE INDEX ix_quality_dispositions_tenant_id ON quality_dispositions (tenant_id);

CREATE INDEX ix_quality_dispositions_project_workspace_id ON quality_dispositions (project_workspace_id);

CREATE TABLE quality_corrective_actions (
	action_code VARCHAR(120) NOT NULL, 
	action_kind VARCHAR(40) NOT NULL, 
	ncr_id INTEGER, 
	description TEXT NOT NULL, 
	owner_user_id INTEGER NOT NULL, 
	due_date DATE NOT NULL, 
	subject_key VARCHAR(500) NOT NULL, 
	subject_reference JSON NOT NULL, 
	document_reference JSON NOT NULL, 
	status VARCHAR(30) NOT NULL, 
	completion_reference JSON, 
	completion_document_reference JSON, 
	completed_by INTEGER, 
	completed_at TIMESTAMP WITHOUT TIME ZONE, 
	verification_reference JSON, 
	verification_document_reference JSON, 
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
	CONSTRAINT uq_quality_action_code UNIQUE (tenant_id, project_workspace_id, action_code), 
	CONSTRAINT ck_quality_action_kind CHECK (action_kind IN ('CORRECTIVE','PREVENTIVE','IMPROVEMENT')), 
	CONSTRAINT ck_quality_corrective_ncr_required CHECK (action_kind <> 'CORRECTIVE' OR ncr_id IS NOT NULL), 
	CONSTRAINT ck_quality_action_status CHECK (status IN ('OPEN','IN_PROGRESS','COMPLETED','VERIFIED','CLOSED')), 
	CONSTRAINT ck_quality_action_completion CHECK (status NOT IN ('COMPLETED','VERIFIED','CLOSED') OR completed_by IS NOT NULL)
);

CREATE INDEX ix_quality_corrective_actions_subject_key ON quality_corrective_actions (subject_key);

CREATE INDEX ix_quality_corrective_actions_tenant_id ON quality_corrective_actions (tenant_id);

CREATE INDEX ix_quality_corrective_actions_ncr_id ON quality_corrective_actions (ncr_id);

CREATE INDEX ix_quality_corrective_actions_project_workspace_id ON quality_corrective_actions (project_workspace_id);

CREATE TABLE quality_punch_items (
	item_number VARCHAR(120) NOT NULL, 
	subject_key VARCHAR(500) NOT NULL, 
	subject_reference JSON NOT NULL, 
	location_reference JSON NOT NULL, 
	description TEXT NOT NULL, 
	category VARCHAR(80) NOT NULL, 
	responsible_user_id INTEGER NOT NULL, 
	due_date DATE NOT NULL, 
	document_reference JSON NOT NULL, 
	status VARCHAR(30) NOT NULL, 
	completion_document_reference JSON, 
	verification_document_reference JSON, 
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
	CONSTRAINT uq_quality_punch_number UNIQUE (tenant_id, project_workspace_id, item_number), 
	CONSTRAINT ck_quality_punch_status CHECK (status IN ('OPEN','IN_PROGRESS','READY_FOR_VERIFICATION','CLOSED')), 
	CONSTRAINT ck_quality_punch_verification CHECK (status <> 'CLOSED' OR verified_by IS NOT NULL), 
	FOREIGN KEY(responsible_user_id) REFERENCES user_accounts (id), 
	FOREIGN KEY(verified_by) REFERENCES user_accounts (id), 
	FOREIGN KEY(updated_by) REFERENCES user_accounts (id), 
	FOREIGN KEY(configuration_id) REFERENCES admin_configurations (id), 
	FOREIGN KEY(tenant_id) REFERENCES tenants (id), 
	FOREIGN KEY(project_workspace_id) REFERENCES enterprise_workspaces (id), 
	FOREIGN KEY(created_by) REFERENCES user_accounts (id)
);

CREATE INDEX ix_quality_punch_items_tenant_id ON quality_punch_items (tenant_id);

CREATE INDEX ix_quality_punch_items_project_workspace_id ON quality_punch_items (project_workspace_id);

CREATE INDEX ix_quality_punch_items_subject_key ON quality_punch_items (subject_key);

CREATE TABLE quality_mappings (
	receipt_line_id INTEGER NOT NULL, 
	production_record_id INTEGER NOT NULL, 
	subject_key VARCHAR(500) NOT NULL, 
	receipt_reference JSON NOT NULL, 
	production_reference JSON NOT NULL, 
	lot_identifiers JSON NOT NULL, 
	quantity NUMERIC(24, 8), 
	uom VARCHAR(40), 
	document_reference JSON NOT NULL, 
	action VARCHAR(12) NOT NULL, 
	supersedes_id INTEGER, 
	reason TEXT NOT NULL, 
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
	CONSTRAINT ck_quality_lot_link_values CHECK (action IN ('SET','REMOVE') AND (quantity IS NULL OR quantity>0)), 
	CONSTRAINT uq_quality_lot_link_stream UNIQUE (tenant_id, project_workspace_id, subject_key, version), 
	FOREIGN KEY(receipt_line_id) REFERENCES procurement_material_receipt_lines (id), 
	FOREIGN KEY(production_record_id) REFERENCES field_production_records (id), 
	UNIQUE (supersedes_id), 
	FOREIGN KEY(supersedes_id) REFERENCES quality_mappings (id), 
	FOREIGN KEY(updated_by) REFERENCES user_accounts (id), 
	FOREIGN KEY(configuration_id) REFERENCES admin_configurations (id), 
	FOREIGN KEY(tenant_id) REFERENCES tenants (id), 
	FOREIGN KEY(project_workspace_id) REFERENCES enterprise_workspaces (id), 
	FOREIGN KEY(created_by) REFERENCES user_accounts (id)
);

CREATE INDEX ix_quality_mappings_production_record_id ON quality_mappings (production_record_id);

CREATE INDEX ix_quality_mappings_subject_key ON quality_mappings (subject_key);

CREATE INDEX ix_quality_mappings_receipt_line_id ON quality_mappings (receipt_line_id);

CREATE INDEX ix_quality_mappings_project_workspace_id ON quality_mappings (project_workspace_id);

CREATE INDEX ix_quality_mappings_tenant_id ON quality_mappings (tenant_id);

CREATE TABLE quality_consumer_decisions (
	consumer VARCHAR(24) NOT NULL, 
	source_domain VARCHAR(24) NOT NULL, 
	source_entity_type VARCHAR(40) NOT NULL, 
	source_entity_id INTEGER NOT NULL, 
	source_root_id INTEGER NOT NULL, 
	source_version INTEGER NOT NULL, 
	source_hash VARCHAR(64) NOT NULL, 
	observed_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	subject_key VARCHAR(500) NOT NULL, 
	decision VARCHAR(20) NOT NULL, 
	linked_entity_type VARCHAR(80), 
	linked_entity_id INTEGER, 
	effective_period_id INTEGER, 
	mapping_reference JSON NOT NULL, 
	source_snapshot JSON NOT NULL, 
	previous_decision_id INTEGER, 
	reason TEXT NOT NULL, 
	id SERIAL NOT NULL, 
	tenant_id INTEGER NOT NULL, 
	project_workspace_id INTEGER NOT NULL, 
	version INTEGER NOT NULL, 
	created_by INTEGER NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_quality_consumer CHECK (consumer IN ('PROGRESS','AWP','COST','CONTRACTS','SCHEDULE','FIELD_OPERATIONS')), 
	CONSTRAINT ck_quality_consumer_source CHECK (source_domain='QUALITY' AND source_version>0 AND source_root_id>0 AND length(source_hash)=64), 
	CONSTRAINT ck_quality_consumer_decision CHECK (decision IN ('ADOPT','REJECT','RECONCILE')), 
	CONSTRAINT uq_quality_consumer_stream UNIQUE (tenant_id, project_workspace_id, consumer, subject_key, source_entity_type, source_root_id, version), 
	FOREIGN KEY(effective_period_id) REFERENCES project_controls_periods (id), 
	FOREIGN KEY(previous_decision_id) REFERENCES quality_consumer_decisions (id), 
	FOREIGN KEY(tenant_id) REFERENCES tenants (id), 
	FOREIGN KEY(project_workspace_id) REFERENCES enterprise_workspaces (id), 
	FOREIGN KEY(created_by) REFERENCES user_accounts (id)
);

CREATE INDEX ix_quality_consumer_decisions_consumer ON quality_consumer_decisions (consumer);

CREATE INDEX ix_quality_consumer_native_link ON quality_consumer_decisions (tenant_id, project_workspace_id, consumer, linked_entity_type, linked_entity_id);

CREATE INDEX ix_quality_consumer_decisions_project_workspace_id ON quality_consumer_decisions (project_workspace_id);

CREATE INDEX ix_quality_consumer_decisions_tenant_id ON quality_consumer_decisions (tenant_id);

CREATE INDEX ix_quality_consumer_decisions_subject_key ON quality_consumer_decisions (subject_key);

CREATE TABLE quality_itps (
	quality_plan_id INTEGER NOT NULL, 
	description TEXT NOT NULL, 
	discipline VARCHAR(80) NOT NULL, 
	source_references JSON NOT NULL, 
	engineering_reference JSON NOT NULL, 
	document_references JSON NOT NULL, 
	items_snapshot JSON NOT NULL, 
	supersedes_id INTEGER, 
	code VARCHAR(120) NOT NULL, 
	title VARCHAR(300) NOT NULL, 
	revision INTEGER NOT NULL, 
	effective_date DATE NOT NULL, 
	status VARCHAR(24) NOT NULL, 
	submitted_by INTEGER, 
	submitted_at TIMESTAMP WITHOUT TIME ZONE, 
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
	CONSTRAINT uq_quality_itp_revision UNIQUE (tenant_id, project_workspace_id, code, revision), 
	CONSTRAINT ck_quality_itp_state CHECK (revision > 0 AND status IN ('DRAFT','SUBMITTED','APPROVED')), 
	FOREIGN KEY(quality_plan_id) REFERENCES quality_plans (id), 
	UNIQUE (supersedes_id), 
	FOREIGN KEY(supersedes_id) REFERENCES quality_itps (id), 
	FOREIGN KEY(submitted_by) REFERENCES user_accounts (id), 
	FOREIGN KEY(approved_by) REFERENCES user_accounts (id), 
	FOREIGN KEY(updated_by) REFERENCES user_accounts (id), 
	FOREIGN KEY(configuration_id) REFERENCES admin_configurations (id), 
	FOREIGN KEY(tenant_id) REFERENCES tenants (id), 
	FOREIGN KEY(project_workspace_id) REFERENCES enterprise_workspaces (id), 
	FOREIGN KEY(created_by) REFERENCES user_accounts (id)
);

CREATE INDEX ix_quality_itps_project_workspace_id ON quality_itps (project_workspace_id);

CREATE INDEX ix_quality_itps_quality_plan_id ON quality_itps (quality_plan_id);

CREATE INDEX ix_quality_itps_tenant_id ON quality_itps (tenant_id);

CREATE TABLE quality_itp_items (
	itp_id INTEGER NOT NULL, 
	itp_item_code VARCHAR(120) NOT NULL, 
	sequence INTEGER NOT NULL, 
	activity VARCHAR(500) NOT NULL, 
	control_type VARCHAR(80) NOT NULL, 
	requirement_reference TEXT NOT NULL, 
	acceptance_criteria TEXT NOT NULL, 
	responsible_party VARCHAR(300) NOT NULL, 
	witness_party VARCHAR(300) NOT NULL, 
	evidence_required BOOLEAN NOT NULL, 
	next_step_rule VARCHAR(500) NOT NULL, 
	required BOOLEAN NOT NULL, 
	inspection_required BOOLEAN NOT NULL, 
	test_required BOOLEAN NOT NULL, 
	test_type VARCHAR(80), 
	test_uom VARCHAR(40), 
	test_lower_limit NUMERIC(24, 8), 
	test_upper_limit NUMERIC(24, 8), 
	checklist_template_code VARCHAR(120) NOT NULL, 
	checklist_template JSON NOT NULL, 
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
	CONSTRAINT uq_quality_itp_item_code UNIQUE (itp_id, itp_item_code), 
	CONSTRAINT uq_quality_itp_item_sequence UNIQUE (itp_id, sequence), 
	CONSTRAINT ck_quality_itp_item_state CHECK (sequence > 0 AND status='ACTIVE'), 
	CONSTRAINT ck_quality_item_limits CHECK (test_lower_limit IS NULL OR test_upper_limit IS NULL OR test_lower_limit <= test_upper_limit), 
	FOREIGN KEY(itp_id) REFERENCES quality_itps (id), 
	FOREIGN KEY(updated_by) REFERENCES user_accounts (id), 
	FOREIGN KEY(configuration_id) REFERENCES admin_configurations (id), 
	FOREIGN KEY(tenant_id) REFERENCES tenants (id), 
	FOREIGN KEY(project_workspace_id) REFERENCES enterprise_workspaces (id), 
	FOREIGN KEY(created_by) REFERENCES user_accounts (id)
);

CREATE INDEX ix_quality_itp_items_project_workspace_id ON quality_itp_items (project_workspace_id);

CREATE INDEX ix_quality_itp_items_tenant_id ON quality_itp_items (tenant_id);

CREATE INDEX ix_quality_itp_items_itp_id ON quality_itp_items (itp_id);

CREATE TABLE quality_acceptances (
	acceptance_code VARCHAR(120) NOT NULL, 
	revision INTEGER NOT NULL, 
	supersedes_id INTEGER, 
	subject_key VARCHAR(500) NOT NULL, 
	subject_reference JSON NOT NULL, 
	itp_id INTEGER NOT NULL, 
	acceptance_profile_code VARCHAR(80) NOT NULL, 
	quantity NUMERIC(24, 8) NOT NULL, 
	uom VARCHAR(40) NOT NULL, 
	effective_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	document_reference JSON NOT NULL, 
	source_references JSON NOT NULL, 
	readiness_snapshot JSON NOT NULL, 
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
	CONSTRAINT uq_quality_acceptance_revision UNIQUE (tenant_id, project_workspace_id, acceptance_code, revision), 
	CONSTRAINT ck_quality_acceptance_fact CHECK (status='APPROVED' AND revision>0 AND quantity>0), 
	UNIQUE (supersedes_id), 
	FOREIGN KEY(supersedes_id) REFERENCES quality_acceptances (id), 
	FOREIGN KEY(itp_id) REFERENCES quality_itps (id), 
	FOREIGN KEY(updated_by) REFERENCES user_accounts (id), 
	FOREIGN KEY(configuration_id) REFERENCES admin_configurations (id), 
	FOREIGN KEY(tenant_id) REFERENCES tenants (id), 
	FOREIGN KEY(project_workspace_id) REFERENCES enterprise_workspaces (id), 
	FOREIGN KEY(created_by) REFERENCES user_accounts (id)
);

CREATE INDEX ix_quality_acceptances_subject_key ON quality_acceptances (subject_key);

CREATE INDEX ix_quality_acceptances_tenant_id ON quality_acceptances (tenant_id);

CREATE INDEX ix_quality_acceptances_itp_id ON quality_acceptances (itp_id);

CREATE INDEX ix_quality_acceptances_project_workspace_id ON quality_acceptances (project_workspace_id);

CREATE TABLE quality_readiness_assessments (
	itp_id INTEGER NOT NULL, 
	subject_key VARCHAR(500) NOT NULL, 
	subject_reference JSON NOT NULL, 
	as_of TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	readiness_state VARCHAR(30) NOT NULL, 
	snapshot_json JSON NOT NULL, 
	reason TEXT NOT NULL, 
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
	CONSTRAINT ck_quality_readiness_state CHECK (readiness_state IN ('READY','PARTIALLY_READY','NOT_READY','STALE','BROKEN_REFERENCE')), 
	CONSTRAINT uq_quality_readiness_stream UNIQUE (tenant_id, project_workspace_id, itp_id, subject_key, version), 
	FOREIGN KEY(itp_id) REFERENCES quality_itps (id), 
	FOREIGN KEY(updated_by) REFERENCES user_accounts (id), 
	FOREIGN KEY(configuration_id) REFERENCES admin_configurations (id), 
	FOREIGN KEY(tenant_id) REFERENCES tenants (id), 
	FOREIGN KEY(project_workspace_id) REFERENCES enterprise_workspaces (id), 
	FOREIGN KEY(created_by) REFERENCES user_accounts (id)
);

CREATE INDEX ix_quality_readiness_assessments_subject_key ON quality_readiness_assessments (subject_key);

CREATE INDEX ix_quality_readiness_assessments_project_workspace_id ON quality_readiness_assessments (project_workspace_id);

CREATE INDEX ix_quality_readiness_assessments_itp_id ON quality_readiness_assessments (itp_id);

CREATE INDEX ix_quality_readiness_assessments_tenant_id ON quality_readiness_assessments (tenant_id);

CREATE TABLE quality_test_requests (
	test_type VARCHAR(80) NOT NULL, 
	laboratory_vendor_id INTEGER, 
	request_number VARCHAR(120) NOT NULL, 
	itp_item_id INTEGER NOT NULL, 
	subject_key VARCHAR(240) NOT NULL, 
	subject_reference JSON NOT NULL, 
	quantity NUMERIC(24, 8), 
	uom VARCHAR(40), 
	requested_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	requested_for TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	requester_user_id INTEGER NOT NULL, 
	inspector_user_id INTEGER NOT NULL, 
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
	CONSTRAINT uq_quality_test_request UNIQUE (tenant_id, project_workspace_id, request_number), 
	CONSTRAINT ck_quality_test_request_state CHECK (status IN ('DRAFT','SUBMITTED','SCHEDULED','IN_TEST','COMPLETED','CANCELLED')), 
	CONSTRAINT ck_quality_test_request_times CHECK (requested_at <= requested_for AND (quantity IS NULL OR quantity > 0)), 
	FOREIGN KEY(laboratory_vendor_id) REFERENCES procurement_vendors (id), 
	FOREIGN KEY(itp_item_id) REFERENCES quality_itp_items (id), 
	FOREIGN KEY(requester_user_id) REFERENCES user_accounts (id), 
	FOREIGN KEY(inspector_user_id) REFERENCES user_accounts (id), 
	FOREIGN KEY(updated_by) REFERENCES user_accounts (id), 
	FOREIGN KEY(configuration_id) REFERENCES admin_configurations (id), 
	FOREIGN KEY(tenant_id) REFERENCES tenants (id), 
	FOREIGN KEY(project_workspace_id) REFERENCES enterprise_workspaces (id), 
	FOREIGN KEY(created_by) REFERENCES user_accounts (id)
);

CREATE INDEX ix_quality_test_requests_tenant_id ON quality_test_requests (tenant_id);

CREATE INDEX ix_quality_test_requests_subject_key ON quality_test_requests (subject_key);

CREATE INDEX ix_quality_test_requests_itp_item_id ON quality_test_requests (itp_item_id);

CREATE INDEX ix_quality_test_requests_project_workspace_id ON quality_test_requests (project_workspace_id);

CREATE TABLE quality_test_records (
	request_id INTEGER NOT NULL, 
	tested_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	method VARCHAR(500) NOT NULL, 
	standard VARCHAR(500) NOT NULL, 
	laboratory_vendor_id INTEGER, 
	equipment_reference JSON, 
	measurements JSON NOT NULL, 
	record_number VARCHAR(120) NOT NULL, 
	itp_item_id INTEGER NOT NULL, 
	subject_key VARCHAR(240) NOT NULL, 
	subject_reference JSON NOT NULL, 
	quantity NUMERIC(24, 8), 
	uom VARCHAR(40), 
	engineering_reference JSON NOT NULL, 
	requirement_reference JSON NOT NULL, 
	inspector_user_id INTEGER NOT NULL, 
	result VARCHAR(32) NOT NULL, 
	comments TEXT NOT NULL, 
	document_references JSON NOT NULL, 
	submitted_by INTEGER, 
	submitted_at TIMESTAMP WITHOUT TIME ZONE, 
	closed_by INTEGER, 
	closed_at TIMESTAMP WITHOUT TIME ZONE, 
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
	CONSTRAINT uq_quality_test_record UNIQUE (tenant_id, project_workspace_id, record_number), 
	CONSTRAINT ck_quality_test_result CHECK (status IN ('DRAFT','SUBMITTED','CLOSED') AND result IN ('PASS','FAIL','CONDITIONAL','NOT_APPLICABLE')), 
	CONSTRAINT ck_quality_test_closed CHECK ((status <> 'CLOSED' AND closed_by IS NULL AND closed_at IS NULL) OR (status='CLOSED' AND closed_by IS NOT NULL AND closed_at IS NOT NULL)), 
	UNIQUE (request_id), 
	FOREIGN KEY(request_id) REFERENCES quality_test_requests (id), 
	FOREIGN KEY(laboratory_vendor_id) REFERENCES procurement_vendors (id), 
	FOREIGN KEY(itp_item_id) REFERENCES quality_itp_items (id), 
	FOREIGN KEY(inspector_user_id) REFERENCES user_accounts (id), 
	FOREIGN KEY(submitted_by) REFERENCES user_accounts (id), 
	FOREIGN KEY(closed_by) REFERENCES user_accounts (id), 
	FOREIGN KEY(updated_by) REFERENCES user_accounts (id), 
	FOREIGN KEY(configuration_id) REFERENCES admin_configurations (id), 
	FOREIGN KEY(tenant_id) REFERENCES tenants (id), 
	FOREIGN KEY(project_workspace_id) REFERENCES enterprise_workspaces (id), 
	FOREIGN KEY(created_by) REFERENCES user_accounts (id)
);

CREATE INDEX ix_quality_test_records_tenant_id ON quality_test_records (tenant_id);

CREATE INDEX ix_quality_test_records_subject_key ON quality_test_records (subject_key);

CREATE INDEX ix_quality_test_records_project_workspace_id ON quality_test_records (project_workspace_id);

CREATE INDEX ix_quality_test_records_itp_item_id ON quality_test_records (itp_item_id);

CREATE TABLE quality_control_point_decisions (
	itp_item_id INTEGER NOT NULL, 
	subject_key VARCHAR(240) NOT NULL, 
	subject_reference JSON NOT NULL, 
	inspection_record_id INTEGER, 
	test_record_id INTEGER, 
	source_references JSON NOT NULL, 
	decision VARCHAR(24) NOT NULL, 
	reason TEXT NOT NULL, 
	document_references JSON NOT NULL, 
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
	CONSTRAINT uq_quality_control_decision_stream UNIQUE (tenant_id, project_workspace_id, itp_item_id, subject_key, version), 
	CONSTRAINT ck_quality_control_decision CHECK (decision IN ('RELEASED','WAIVED')), 
	FOREIGN KEY(itp_item_id) REFERENCES quality_itp_items (id), 
	FOREIGN KEY(inspection_record_id) REFERENCES quality_inspection_records (id), 
	FOREIGN KEY(test_record_id) REFERENCES quality_test_records (id), 
	FOREIGN KEY(updated_by) REFERENCES user_accounts (id), 
	FOREIGN KEY(configuration_id) REFERENCES admin_configurations (id), 
	FOREIGN KEY(tenant_id) REFERENCES tenants (id), 
	FOREIGN KEY(project_workspace_id) REFERENCES enterprise_workspaces (id), 
	FOREIGN KEY(created_by) REFERENCES user_accounts (id)
);

CREATE INDEX ix_quality_control_point_decisions_subject_key ON quality_control_point_decisions (subject_key);

CREATE INDEX ix_quality_control_point_decisions_project_workspace_id ON quality_control_point_decisions (project_workspace_id);

CREATE INDEX ix_quality_control_point_decisions_itp_item_id ON quality_control_point_decisions (itp_item_id);

CREATE INDEX ix_quality_control_point_decisions_tenant_id ON quality_control_point_decisions (tenant_id);

ALTER TABLE quality_inspection_requests ADD FOREIGN KEY(project_workspace_id) REFERENCES enterprise_workspaces (id);

ALTER TABLE quality_inspection_records ADD FOREIGN KEY(closed_by) REFERENCES user_accounts (id);

ALTER TABLE quality_corrective_actions ADD FOREIGN KEY(ncr_id) REFERENCES quality_ncrs (id);

ALTER TABLE quality_ncrs ADD FOREIGN KEY(disposition_id) REFERENCES quality_dispositions (id);

ALTER TABLE quality_inspection_requests ADD FOREIGN KEY(created_by) REFERENCES user_accounts (id);

ALTER TABLE quality_corrective_actions ADD FOREIGN KEY(verified_by) REFERENCES user_accounts (id);

ALTER TABLE quality_inspection_records ADD FOREIGN KEY(updated_by) REFERENCES user_accounts (id);

ALTER TABLE quality_ncrs ADD FOREIGN KEY(issued_by) REFERENCES user_accounts (id);

ALTER TABLE quality_dispositions ADD FOREIGN KEY(tenant_id) REFERENCES tenants (id);

ALTER TABLE quality_dispositions ADD FOREIGN KEY(ncr_id) REFERENCES quality_ncrs (id);

ALTER TABLE quality_inspection_records ADD FOREIGN KEY(request_id) REFERENCES quality_inspection_requests (id);

ALTER TABLE quality_ncrs ADD FOREIGN KEY(created_by) REFERENCES user_accounts (id);

ALTER TABLE quality_ncrs ADD FOREIGN KEY(responsible_user_id) REFERENCES user_accounts (id);

ALTER TABLE quality_corrective_actions ADD FOREIGN KEY(updated_by) REFERENCES user_accounts (id);

ALTER TABLE quality_inspection_records ADD FOREIGN KEY(configuration_id) REFERENCES admin_configurations (id);

ALTER TABLE quality_inspection_requests ADD FOREIGN KEY(corrective_action_id) REFERENCES quality_corrective_actions (id);

ALTER TABLE quality_ncrs ADD FOREIGN KEY(verified_by) REFERENCES user_accounts (id);

ALTER TABLE quality_inspection_requests ADD FOREIGN KEY(inspector_user_id) REFERENCES user_accounts (id);

ALTER TABLE quality_corrective_actions ADD FOREIGN KEY(configuration_id) REFERENCES admin_configurations (id);

ALTER TABLE quality_inspection_records ADD FOREIGN KEY(tenant_id) REFERENCES tenants (id);

ALTER TABLE quality_ncrs ADD FOREIGN KEY(closed_by) REFERENCES user_accounts (id);

ALTER TABLE quality_inspection_requests ADD FOREIGN KEY(updated_by) REFERENCES user_accounts (id);

ALTER TABLE quality_dispositions ADD FOREIGN KEY(project_workspace_id) REFERENCES enterprise_workspaces (id);

ALTER TABLE quality_corrective_actions ADD FOREIGN KEY(owner_user_id) REFERENCES user_accounts (id);

ALTER TABLE quality_corrective_actions ADD FOREIGN KEY(tenant_id) REFERENCES tenants (id);

ALTER TABLE quality_ncrs ADD FOREIGN KEY(updated_by) REFERENCES user_accounts (id);

ALTER TABLE quality_inspection_requests ADD FOREIGN KEY(configuration_id) REFERENCES admin_configurations (id);

ALTER TABLE quality_dispositions ADD FOREIGN KEY(created_by) REFERENCES user_accounts (id);

ALTER TABLE quality_inspection_records ADD FOREIGN KEY(inspector_user_id) REFERENCES user_accounts (id);

ALTER TABLE quality_ncrs ADD FOREIGN KEY(configuration_id) REFERENCES admin_configurations (id);

ALTER TABLE quality_ncrs ADD FOREIGN KEY(inspection_record_id) REFERENCES quality_inspection_records (id);

ALTER TABLE quality_inspection_requests ADD FOREIGN KEY(tenant_id) REFERENCES tenants (id);

ALTER TABLE quality_inspection_records ADD FOREIGN KEY(project_workspace_id) REFERENCES enterprise_workspaces (id);

ALTER TABLE quality_corrective_actions ADD FOREIGN KEY(completed_by) REFERENCES user_accounts (id);

ALTER TABLE quality_inspection_requests ADD FOREIGN KEY(itp_item_id) REFERENCES quality_itp_items (id);

ALTER TABLE quality_ncrs ADD FOREIGN KEY(test_record_id) REFERENCES quality_test_records (id);

ALTER TABLE quality_inspection_requests ADD FOREIGN KEY(reinspection_of_id) REFERENCES quality_inspection_records (id);

ALTER TABLE quality_dispositions ADD FOREIGN KEY(approved_by) REFERENCES user_accounts (id);

ALTER TABLE quality_inspection_records ADD FOREIGN KEY(itp_item_id) REFERENCES quality_itp_items (id);

ALTER TABLE quality_dispositions ADD FOREIGN KEY(configuration_id) REFERENCES admin_configurations (id);

ALTER TABLE quality_ncrs ADD FOREIGN KEY(tenant_id) REFERENCES tenants (id);

ALTER TABLE quality_corrective_actions ADD FOREIGN KEY(project_workspace_id) REFERENCES enterprise_workspaces (id);

ALTER TABLE quality_corrective_actions ADD FOREIGN KEY(created_by) REFERENCES user_accounts (id);

ALTER TABLE quality_inspection_records ADD FOREIGN KEY(created_by) REFERENCES user_accounts (id);

ALTER TABLE quality_inspection_records ADD FOREIGN KEY(submitted_by) REFERENCES user_accounts (id);

ALTER TABLE quality_dispositions ADD FOREIGN KEY(updated_by) REFERENCES user_accounts (id);

ALTER TABLE quality_ncrs ADD FOREIGN KEY(project_workspace_id) REFERENCES enterprise_workspaces (id);

ALTER TABLE quality_inspection_requests ADD FOREIGN KEY(requester_user_id) REFERENCES user_accounts (id);
