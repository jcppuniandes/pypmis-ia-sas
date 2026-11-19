"""Frozen O2B PostgreSQL DDL for revision 0077. Do not edit on model changes."""

TABLES = (
    (
        "procurement_mappings",
        "CREATE TABLE procurement_mappings (\n\tsource_kind VARCHAR(32) NOT NULL, \n\tsource_id INTEGER NOT NULL, \n\ttarget_kind VARCHAR(32) NOT NULL, \n\ttarget_id INTEGER, \n\tschedule_version_id INTEGER, \n\texternal_id VARCHAR(160), \n\teffective_date DATE NOT NULL, \n\taction VARCHAR(8) NOT NULL, \n\ttarget_snapshot_json JSON NOT NULL, \n\tcontent_hash VARCHAR(64) NOT NULL, \n\treason TEXT NOT NULL, \n\tid SERIAL NOT NULL, \n\ttenant_id INTEGER NOT NULL, \n\tproject_workspace_id INTEGER NOT NULL, \n\tversion INTEGER NOT NULL, \n\tcreated_by INTEGER NOT NULL, \n\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (tenant_id, project_workspace_id, source_kind, source_id, version), \n\tCONSTRAINT ck_procurement_mapping_action CHECK (source_id > 0 AND version > 1 AND action IN ('SET','REMOVE')), \n\tCONSTRAINT ck_procurement_mapping_target CHECK ((target_kind IN ('WBS','ACTIVITY','MILESTONE') AND target_id IS NULL AND schedule_version_id IS NOT NULL AND external_id IS NOT NULL AND length(external_id)>0) OR (target_kind NOT IN ('WBS','ACTIVITY','MILESTONE') AND target_id > 0 AND target_id IS NOT NULL AND schedule_version_id IS NULL AND external_id IS NULL)), \n\tFOREIGN KEY(schedule_version_id) REFERENCES schedule_versions (id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id), \n\tFOREIGN KEY(project_workspace_id) REFERENCES enterprise_workspaces (id), \n\tFOREIGN KEY(created_by) REFERENCES user_accounts (id)\n)",
        (
            "CREATE INDEX ix_procurement_mapping_reverse ON procurement_mappings (tenant_id, project_workspace_id, target_kind, target_id, id)",
            "CREATE INDEX ix_procurement_mappings_project_workspace_id ON procurement_mappings (project_workspace_id)",
            "CREATE INDEX ix_procurement_mappings_tenant_id ON procurement_mappings (tenant_id)",
        ),
    ),
    (
        "procurement_material_items",
        "CREATE TABLE procurement_material_items (\n\tmaterial_code VARCHAR(120) NOT NULL, \n\tdescription VARCHAR(300) NOT NULL, \n\tspecification TEXT NOT NULL, \n\tuom VARCHAR(24) NOT NULL, \n\tcategory VARCHAR(80) NOT NULL, \n\tid SERIAL NOT NULL, \n\ttenant_id INTEGER NOT NULL, \n\tproject_workspace_id INTEGER NOT NULL, \n\tversion INTEGER NOT NULL, \n\tcreated_by INTEGER NOT NULL, \n\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_procurement_material_item_code UNIQUE (tenant_id, project_workspace_id, material_code), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id), \n\tFOREIGN KEY(project_workspace_id) REFERENCES enterprise_workspaces (id), \n\tFOREIGN KEY(created_by) REFERENCES user_accounts (id)\n)",
        (
            "CREATE INDEX ix_procurement_material_items_project_workspace_id ON procurement_material_items (project_workspace_id)",
            "CREATE INDEX ix_procurement_material_items_tenant_id ON procurement_material_items (tenant_id)",
        ),
    ),
    (
        "procurement_shipments",
        "CREATE TABLE procurement_shipments (\n\tshipment_number VARCHAR(120) NOT NULL, \n\tvendor_id INTEGER NOT NULL, \n\torigin VARCHAR(240) NOT NULL, \n\tdestination VARCHAR(240) NOT NULL, \n\ttransport_mode VARCHAR(80) NOT NULL, \n\tcarrier_reference VARCHAR(240) NOT NULL, \n\tcustoms_reference VARCHAR(240) NOT NULL, \n\tstatus VARCHAR(30) NOT NULL, \n\tdispatch_date DATE, \n\tplanned_arrival DATE, \n\tforecast_arrival DATE, \n\tactual_arrival DATE, \n\tlast_event_date DATE, \n\tdocument_reference_json JSON NOT NULL, \n\tid SERIAL NOT NULL, \n\ttenant_id INTEGER NOT NULL, \n\tproject_workspace_id INTEGER NOT NULL, \n\tversion INTEGER NOT NULL, \n\tcreated_by INTEGER NOT NULL, \n\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_procurement_shipment_code UNIQUE (tenant_id, project_workspace_id, shipment_number), \n\tCONSTRAINT ck_procurement_shipment_status CHECK (status IN ('PLANNED','READY_FOR_DISPATCH','DISPATCHED','IN_TRANSIT','ARRIVED','PARTIALLY_RECEIVED','RECEIVED','CANCELLED')), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id), \n\tFOREIGN KEY(project_workspace_id) REFERENCES enterprise_workspaces (id), \n\tFOREIGN KEY(created_by) REFERENCES user_accounts (id)\n)",
        (
            "CREATE INDEX ix_procurement_shipments_project_workspace_id ON procurement_shipments (project_workspace_id)",
            "CREATE INDEX ix_procurement_shipments_tenant_id ON procurement_shipments (tenant_id)",
        ),
    ),
    (
        "procurement_vendors",
        "CREATE TABLE procurement_vendors (\n\tid SERIAL NOT NULL, \n\ttenant_id INTEGER NOT NULL, \n\tvendor_code VARCHAR(80) NOT NULL, \n\tlegal_name VARCHAR(240) NOT NULL, \n\tdisplay_name VARCHAR(200) NOT NULL, \n\tbusiness_identifier VARCHAR(120) NOT NULL, \n\tcountry VARCHAR(2) NOT NULL, \n\tcontact_reference VARCHAR(400) NOT NULL, \n\tqualification_reference VARCHAR(400) NOT NULL, \n\tstatus VARCHAR(20) NOT NULL, \n\tversion INTEGER NOT NULL, \n\tcreated_by INTEGER NOT NULL, \n\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_proc_vendor_code UNIQUE (tenant_id, vendor_code), \n\tCONSTRAINT uq_proc_vendor_business UNIQUE (tenant_id, country, business_identifier), \n\tCONSTRAINT ck_proc_vendor_status CHECK (status IN ('ACTIVE','SUSPENDED','RETIRED')), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id), \n\tFOREIGN KEY(created_by) REFERENCES user_accounts (id)\n)",
        ("CREATE INDEX ix_procurement_vendors_tenant_id ON procurement_vendors (tenant_id)",),
    ),
    (
        "procurement_packages",
        "CREATE TABLE procurement_packages (\n\tpackage_code VARCHAR(120) NOT NULL, \n\ttitle VARCHAR(240) NOT NULL, \n\tdescription TEXT NOT NULL, \n\tprocurement_type VARCHAR(80) NOT NULL, \n\tcategory VARCHAR(80) NOT NULL, \n\tdiscipline VARCHAR(80) NOT NULL, \n\tresponsible_user_id INTEGER NOT NULL, \n\tprocurement_manager_id INTEGER NOT NULL, \n\tstrategy TEXT NOT NULL, \n\tsourcing_method VARCHAR(80) NOT NULL, \n\tlong_lead_flag BOOLEAN NOT NULL, \n\tpriority VARCHAR(20) NOT NULL, \n\trequired_on_site_date DATE NOT NULL, \n\tplanned_rfq_date DATE, \n\tplanned_award_date DATE, \n\tplanned_po_date DATE, \n\tforecast_delivery_date DATE, \n\tstatus VARCHAR(24) NOT NULL, \n\tconfiguration_id INTEGER NOT NULL, \n\tconfiguration_hash VARCHAR(64) NOT NULL, \n\tupdated_by INTEGER NOT NULL, \n\tupdated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n\tid SERIAL NOT NULL, \n\ttenant_id INTEGER NOT NULL, \n\tproject_workspace_id INTEGER NOT NULL, \n\tversion INTEGER NOT NULL, \n\tcreated_by INTEGER NOT NULL, \n\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_proc_package_code UNIQUE (tenant_id, project_workspace_id, package_code), \n\tCONSTRAINT ck_proc_package_status CHECK (status IN ('DRAFT','PLANNED','CLOSED','CANCELLED')), \n\tFOREIGN KEY(responsible_user_id) REFERENCES user_accounts (id), \n\tFOREIGN KEY(procurement_manager_id) REFERENCES user_accounts (id), \n\tFOREIGN KEY(configuration_id) REFERENCES admin_configurations (id), \n\tFOREIGN KEY(updated_by) REFERENCES user_accounts (id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id), \n\tFOREIGN KEY(project_workspace_id) REFERENCES enterprise_workspaces (id), \n\tFOREIGN KEY(created_by) REFERENCES user_accounts (id)\n)",
        (
            "CREATE INDEX ix_proc_package_register ON procurement_packages (tenant_id, project_workspace_id, status, id)",
            "CREATE INDEX ix_procurement_packages_project_workspace_id ON procurement_packages (project_workspace_id)",
            "CREATE INDEX ix_procurement_packages_tenant_id ON procurement_packages (tenant_id)",
        ),
    ),
    (
        "procurement_history",
        "CREATE TABLE procurement_history (\n\tentity_type VARCHAR(80) NOT NULL, \n\tentity_id INTEGER NOT NULL, \n\tentity_version INTEGER NOT NULL, \n\tprevious_version INTEGER, \n\tevent_type VARCHAR(100) NOT NULL, \n\tsnapshot_json JSON NOT NULL, \n\treason TEXT NOT NULL, \n\tid SERIAL NOT NULL, \n\ttenant_id INTEGER NOT NULL, \n\tproject_workspace_id INTEGER NOT NULL, \n\tversion INTEGER NOT NULL, \n\tcreated_by INTEGER NOT NULL, \n\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id), \n\tFOREIGN KEY(project_workspace_id) REFERENCES enterprise_workspaces (id), \n\tFOREIGN KEY(created_by) REFERENCES user_accounts (id)\n)",
        (
            "CREATE INDEX ix_proc_history_workspace_entity ON procurement_history (tenant_id, project_workspace_id, entity_type, entity_id, id)",
            "CREATE INDEX ix_procurement_history_project_workspace_id ON procurement_history (project_workspace_id)",
            "CREATE INDEX ix_procurement_history_tenant_id ON procurement_history (tenant_id)",
        ),
    ),
    (
        "procurement_material_receipts",
        "CREATE TABLE procurement_material_receipts (\n\treceipt_number VARCHAR(120) NOT NULL, \n\tshipment_id INTEGER NOT NULL, \n\tlocation VARCHAR(240) NOT NULL, \n\treceived_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n\tdocument_reference_json JSON NOT NULL, \n\tid SERIAL NOT NULL, \n\ttenant_id INTEGER NOT NULL, \n\tproject_workspace_id INTEGER NOT NULL, \n\tversion INTEGER NOT NULL, \n\tcreated_by INTEGER NOT NULL, \n\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_procurement_material_receipt_code UNIQUE (tenant_id, project_workspace_id, receipt_number), \n\tFOREIGN KEY(shipment_id) REFERENCES procurement_shipments (id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id), \n\tFOREIGN KEY(project_workspace_id) REFERENCES enterprise_workspaces (id), \n\tFOREIGN KEY(created_by) REFERENCES user_accounts (id)\n)",
        (
            "CREATE INDEX ix_procurement_material_receipts_project_workspace_id ON procurement_material_receipts (project_workspace_id)",
            "CREATE INDEX ix_procurement_material_receipts_shipment_id ON procurement_material_receipts (shipment_id)",
            "CREATE INDEX ix_procurement_material_receipts_tenant_id ON procurement_material_receipts (tenant_id)",
        ),
    ),
    (
        "procurement_requirements",
        "CREATE TABLE procurement_requirements (\n\trequirement_code VARCHAR(120) NOT NULL, \n\tpackage_id INTEGER NOT NULL, \n\tdescription TEXT NOT NULL, \n\titem_type VARCHAR(80) NOT NULL, \n\trequired_quantity NUMERIC(18, 6) NOT NULL, \n\tuom VARCHAR(24) NOT NULL, \n\trequired_on_site_date DATE NOT NULL, \n\tpriority VARCHAR(20) NOT NULL, \n\tsource_authority VARCHAR(80) NOT NULL, \n\tsource_entity_type VARCHAR(80) NOT NULL, \n\tsource_entity_id INTEGER, \n\tsource_hash VARCHAR(64) NOT NULL, \n\tsource_reference JSON NOT NULL, \n\tstatus VARCHAR(24) NOT NULL, \n\tupdated_by INTEGER NOT NULL, \n\tupdated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n\tid SERIAL NOT NULL, \n\ttenant_id INTEGER NOT NULL, \n\tproject_workspace_id INTEGER NOT NULL, \n\tversion INTEGER NOT NULL, \n\tcreated_by INTEGER NOT NULL, \n\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_proc_requirement_code UNIQUE (tenant_id, project_workspace_id, requirement_code), \n\tCONSTRAINT ck_proc_requirement_qty CHECK (required_quantity > 0), \n\tCONSTRAINT ck_proc_requirement_status CHECK (status IN ('DRAFT','ACTIVE','CANCELLED')), \n\tFOREIGN KEY(package_id) REFERENCES procurement_packages (id), \n\tFOREIGN KEY(updated_by) REFERENCES user_accounts (id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id), \n\tFOREIGN KEY(project_workspace_id) REFERENCES enterprise_workspaces (id), \n\tFOREIGN KEY(created_by) REFERENCES user_accounts (id)\n)",
        (
            "CREATE INDEX ix_procurement_requirements_package_id ON procurement_requirements (package_id)",
            "CREATE INDEX ix_procurement_requirements_project_workspace_id ON procurement_requirements (project_workspace_id)",
            "CREATE INDEX ix_procurement_requirements_tenant_id ON procurement_requirements (tenant_id)",
        ),
    ),
    (
        "procurement_requisitions",
        "CREATE TABLE procurement_requisitions (\n\trequisition_number VARCHAR(120) NOT NULL, \n\tpackage_id INTEGER NOT NULL, \n\trevision INTEGER NOT NULL, \n\tstatus VARCHAR(24) NOT NULL, \n\trequested_by INTEGER NOT NULL, \n\tprepared_by INTEGER NOT NULL, \n\tapproved_by INTEGER, \n\tissue_date DATE NOT NULL, \n\trequired_date DATE NOT NULL, \n\tcurrency VARCHAR(3) NOT NULL, \n\testimated_value NUMERIC(20, 6), \n\ttechnical_reference JSON NOT NULL, \n\tdocument_reference JSON NOT NULL, \n\tnotes TEXT NOT NULL, \n\tconfiguration_id INTEGER NOT NULL, \n\tconfiguration_hash VARCHAR(64) NOT NULL, \n\tupdated_by INTEGER NOT NULL, \n\tupdated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n\tid SERIAL NOT NULL, \n\ttenant_id INTEGER NOT NULL, \n\tproject_workspace_id INTEGER NOT NULL, \n\tversion INTEGER NOT NULL, \n\tcreated_by INTEGER NOT NULL, \n\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_proc_req_revision UNIQUE (tenant_id, project_workspace_id, requisition_number, revision), \n\tCONSTRAINT ck_proc_req_status CHECK (status IN ('DRAFT','SUBMITTED','APPROVED','REJECTED','CANCELLED')), \n\tFOREIGN KEY(package_id) REFERENCES procurement_packages (id), \n\tFOREIGN KEY(requested_by) REFERENCES user_accounts (id), \n\tFOREIGN KEY(prepared_by) REFERENCES user_accounts (id), \n\tFOREIGN KEY(approved_by) REFERENCES user_accounts (id), \n\tFOREIGN KEY(configuration_id) REFERENCES admin_configurations (id), \n\tFOREIGN KEY(updated_by) REFERENCES user_accounts (id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id), \n\tFOREIGN KEY(project_workspace_id) REFERENCES enterprise_workspaces (id), \n\tFOREIGN KEY(created_by) REFERENCES user_accounts (id)\n)",
        (
            "CREATE INDEX ix_procurement_requisitions_package_id ON procurement_requisitions (package_id)",
            "CREATE INDEX ix_procurement_requisitions_project_workspace_id ON procurement_requisitions (project_workspace_id)",
            "CREATE INDEX ix_procurement_requisitions_tenant_id ON procurement_requisitions (tenant_id)",
        ),
    ),
    (
        "procurement_material_requirements",
        "CREATE TABLE procurement_material_requirements (\n\trequirement_code VARCHAR(120) NOT NULL, \n\tmaterial_item_id INTEGER NOT NULL, \n\tprocurement_requirement_id INTEGER, \n\trequired_quantity NUMERIC(20, 6) NOT NULL, \n\tuom VARCHAR(24) NOT NULL, \n\trequired_on_site_date DATE, \n\tsource_reference_json JSON NOT NULL, \n\tid SERIAL NOT NULL, \n\ttenant_id INTEGER NOT NULL, \n\tproject_workspace_id INTEGER NOT NULL, \n\tversion INTEGER NOT NULL, \n\tcreated_by INTEGER NOT NULL, \n\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_procurement_material_requirement_code UNIQUE (tenant_id, project_workspace_id, requirement_code), \n\tCONSTRAINT uq_procurement_material_demand_link UNIQUE (tenant_id, project_workspace_id, procurement_requirement_id), \n\tCONSTRAINT ck_procurement_material_required_quantity CHECK (required_quantity > 0), \n\tFOREIGN KEY(material_item_id) REFERENCES procurement_material_items (id), \n\tFOREIGN KEY(procurement_requirement_id) REFERENCES procurement_requirements (id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id), \n\tFOREIGN KEY(project_workspace_id) REFERENCES enterprise_workspaces (id), \n\tFOREIGN KEY(created_by) REFERENCES user_accounts (id)\n)",
        (
            "CREATE INDEX ix_procurement_material_requirements_material_item_id ON procurement_material_requirements (material_item_id)",
            "CREATE INDEX ix_procurement_material_requirements_procurement_requirement_id ON procurement_material_requirements (procurement_requirement_id)",
            "CREATE INDEX ix_procurement_material_requirements_project_workspace_id ON procurement_material_requirements (project_workspace_id)",
            "CREATE INDEX ix_procurement_material_requirements_tenant_id ON procurement_material_requirements (tenant_id)",
        ),
    ),
    (
        "procurement_package_items",
        "CREATE TABLE procurement_package_items (\n\tpackage_id INTEGER NOT NULL, \n\trequirement_id INTEGER NOT NULL, \n\tquantity NUMERIC(18, 6) NOT NULL, \n\tuom VARCHAR(24) NOT NULL, \n\tid SERIAL NOT NULL, \n\ttenant_id INTEGER NOT NULL, \n\tproject_workspace_id INTEGER NOT NULL, \n\tversion INTEGER NOT NULL, \n\tcreated_by INTEGER NOT NULL, \n\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_proc_package_item_req UNIQUE (package_id, requirement_id), \n\tCONSTRAINT ck_proc_package_item_qty CHECK (quantity > 0), \n\tFOREIGN KEY(package_id) REFERENCES procurement_packages (id), \n\tFOREIGN KEY(requirement_id) REFERENCES procurement_requirements (id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id), \n\tFOREIGN KEY(project_workspace_id) REFERENCES enterprise_workspaces (id), \n\tFOREIGN KEY(created_by) REFERENCES user_accounts (id)\n)",
        (
            "CREATE INDEX ix_procurement_package_items_package_id ON procurement_package_items (package_id)",
            "CREATE INDEX ix_procurement_package_items_project_workspace_id ON procurement_package_items (project_workspace_id)",
            "CREATE INDEX ix_procurement_package_items_requirement_id ON procurement_package_items (requirement_id)",
            "CREATE INDEX ix_procurement_package_items_tenant_id ON procurement_package_items (tenant_id)",
        ),
    ),
    (
        "procurement_requisition_lines",
        "CREATE TABLE procurement_requisition_lines (\n\trequisition_id INTEGER NOT NULL, \n\trequirement_id INTEGER NOT NULL, \n\tline_number INTEGER NOT NULL, \n\tdescription TEXT NOT NULL, \n\tquantity NUMERIC(18, 6) NOT NULL, \n\tuom VARCHAR(24) NOT NULL, \n\trequired_date DATE NOT NULL, \n\ttechnical_specification_reference VARCHAR(400) NOT NULL, \n\tengineering_revision_reference JSON NOT NULL, \n\tdestination VARCHAR(240) NOT NULL, \n\tnotes TEXT NOT NULL, \n\tid SERIAL NOT NULL, \n\ttenant_id INTEGER NOT NULL, \n\tproject_workspace_id INTEGER NOT NULL, \n\tversion INTEGER NOT NULL, \n\tcreated_by INTEGER NOT NULL, \n\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_proc_req_line_no UNIQUE (requisition_id, line_number), \n\tCONSTRAINT ck_proc_req_line_qty_no CHECK (quantity > 0 AND line_number > 0), \n\tFOREIGN KEY(requisition_id) REFERENCES procurement_requisitions (id), \n\tFOREIGN KEY(requirement_id) REFERENCES procurement_requirements (id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id), \n\tFOREIGN KEY(project_workspace_id) REFERENCES enterprise_workspaces (id), \n\tFOREIGN KEY(created_by) REFERENCES user_accounts (id)\n)",
        (
            "CREATE INDEX ix_procurement_requisition_lines_project_workspace_id ON procurement_requisition_lines (project_workspace_id)",
            "CREATE INDEX ix_procurement_requisition_lines_requirement_id ON procurement_requisition_lines (requirement_id)",
            "CREATE INDEX ix_procurement_requisition_lines_requisition_id ON procurement_requisition_lines (requisition_id)",
            "CREATE INDEX ix_procurement_requisition_lines_tenant_id ON procurement_requisition_lines (tenant_id)",
        ),
    ),
    (
        "procurement_rfqs",
        "CREATE TABLE procurement_rfqs (\n\trfq_number VARCHAR(120) NOT NULL, \n\tpackage_id INTEGER NOT NULL, \n\trequisition_id INTEGER NOT NULL, \n\trevision INTEGER NOT NULL, \n\tissue_date DATE NOT NULL, \n\tclosing_date DATE NOT NULL, \n\tstatus VARCHAR(24) NOT NULL, \n\tcommercial_terms_reference VARCHAR(400) NOT NULL, \n\ttechnical_package_reference JSON NOT NULL, \n\tdocument_reference JSON NOT NULL, \n\tapproved_by INTEGER, \n\tconfiguration_id INTEGER NOT NULL, \n\tconfiguration_hash VARCHAR(64) NOT NULL, \n\tupdated_by INTEGER NOT NULL, \n\tupdated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n\tid SERIAL NOT NULL, \n\ttenant_id INTEGER NOT NULL, \n\tproject_workspace_id INTEGER NOT NULL, \n\tversion INTEGER NOT NULL, \n\tcreated_by INTEGER NOT NULL, \n\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_proc_rfq_revision UNIQUE (tenant_id, project_workspace_id, rfq_number, revision), \n\tCONSTRAINT ck_proc_rfq_dates CHECK (closing_date >= issue_date), \n\tCONSTRAINT ck_proc_rfq_status CHECK (status IN ('DRAFT','ISSUED','CLOSED','CANCELLED')), \n\tFOREIGN KEY(package_id) REFERENCES procurement_packages (id), \n\tFOREIGN KEY(requisition_id) REFERENCES procurement_requisitions (id), \n\tFOREIGN KEY(approved_by) REFERENCES user_accounts (id), \n\tFOREIGN KEY(configuration_id) REFERENCES admin_configurations (id), \n\tFOREIGN KEY(updated_by) REFERENCES user_accounts (id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id), \n\tFOREIGN KEY(project_workspace_id) REFERENCES enterprise_workspaces (id), \n\tFOREIGN KEY(created_by) REFERENCES user_accounts (id)\n)",
        (
            "CREATE INDEX ix_procurement_rfqs_package_id ON procurement_rfqs (package_id)",
            "CREATE INDEX ix_procurement_rfqs_project_workspace_id ON procurement_rfqs (project_workspace_id)",
            "CREATE INDEX ix_procurement_rfqs_requisition_id ON procurement_rfqs (requisition_id)",
            "CREATE INDEX ix_procurement_rfqs_tenant_id ON procurement_rfqs (tenant_id)",
        ),
    ),
    (
        "procurement_rfq_vendors",
        "CREATE TABLE procurement_rfq_vendors (\n\trfq_id INTEGER NOT NULL, \n\tvendor_id INTEGER NOT NULL, \n\tvendor_snapshot JSON NOT NULL, \n\tid SERIAL NOT NULL, \n\ttenant_id INTEGER NOT NULL, \n\tproject_workspace_id INTEGER NOT NULL, \n\tversion INTEGER NOT NULL, \n\tcreated_by INTEGER NOT NULL, \n\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_proc_rfq_vendor UNIQUE (rfq_id, vendor_id), \n\tFOREIGN KEY(rfq_id) REFERENCES procurement_rfqs (id), \n\tFOREIGN KEY(vendor_id) REFERENCES procurement_vendors (id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id), \n\tFOREIGN KEY(project_workspace_id) REFERENCES enterprise_workspaces (id), \n\tFOREIGN KEY(created_by) REFERENCES user_accounts (id)\n)",
        (
            "CREATE INDEX ix_procurement_rfq_vendors_project_workspace_id ON procurement_rfq_vendors (project_workspace_id)",
            "CREATE INDEX ix_procurement_rfq_vendors_rfq_id ON procurement_rfq_vendors (rfq_id)",
            "CREATE INDEX ix_procurement_rfq_vendors_tenant_id ON procurement_rfq_vendors (tenant_id)",
            "CREATE INDEX ix_procurement_rfq_vendors_vendor_id ON procurement_rfq_vendors (vendor_id)",
        ),
    ),
    (
        "procurement_bids",
        "CREATE TABLE procurement_bids (\n\trfq_id INTEGER NOT NULL, \n\tvendor_id INTEGER NOT NULL, \n\tbid_revision INTEGER NOT NULL, \n\tsupersedes_id INTEGER, \n\treceived_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n\tcurrency VARCHAR(3) NOT NULL, \n\ttotal_bid_value NUMERIC(20, 6) NOT NULL, \n\tvalidity_date DATE NOT NULL, \n\toverall_status VARCHAR(24) NOT NULL, \n\tdocument_reference JSON NOT NULL, \n\tcontent_hash VARCHAR(64) NOT NULL, \n\tid SERIAL NOT NULL, \n\ttenant_id INTEGER NOT NULL, \n\tproject_workspace_id INTEGER NOT NULL, \n\tversion INTEGER NOT NULL, \n\tcreated_by INTEGER NOT NULL, \n\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_proc_bid_revision UNIQUE (rfq_id, vendor_id, bid_revision), \n\tCONSTRAINT uq_proc_bid_successor UNIQUE (supersedes_id), \n\tCONSTRAINT ck_proc_bid_value CHECK (total_bid_value > 0), \n\tFOREIGN KEY(rfq_id) REFERENCES procurement_rfqs (id), \n\tFOREIGN KEY(vendor_id) REFERENCES procurement_vendors (id), \n\tFOREIGN KEY(supersedes_id) REFERENCES procurement_bids (id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id), \n\tFOREIGN KEY(project_workspace_id) REFERENCES enterprise_workspaces (id), \n\tFOREIGN KEY(created_by) REFERENCES user_accounts (id)\n)",
        (
            "CREATE INDEX ix_procurement_bids_project_workspace_id ON procurement_bids (project_workspace_id)",
            "CREATE INDEX ix_procurement_bids_rfq_id ON procurement_bids (rfq_id)",
            "CREATE INDEX ix_procurement_bids_tenant_id ON procurement_bids (tenant_id)",
            "CREATE INDEX ix_procurement_bids_vendor_id ON procurement_bids (vendor_id)",
        ),
    ),
    (
        "procurement_evaluations",
        "CREATE TABLE procurement_evaluations (\n\tbid_id INTEGER NOT NULL, \n\tevaluation_type VARCHAR(24) NOT NULL, \n\tevaluated_on DATE NOT NULL, \n\tresult VARCHAR(24) NOT NULL, \n\tscore NUMERIC(8, 4), \n\tcomments TEXT NOT NULL, \n\trecommendation VARCHAR(24) NOT NULL, \n\tengineering_reference JSON NOT NULL, \n\tdocument_reference JSON NOT NULL, \n\tcontent_hash VARCHAR(64) NOT NULL, \n\tid SERIAL NOT NULL, \n\ttenant_id INTEGER NOT NULL, \n\tproject_workspace_id INTEGER NOT NULL, \n\tversion INTEGER NOT NULL, \n\tcreated_by INTEGER NOT NULL, \n\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_proc_eval_duty UNIQUE (bid_id, evaluation_type), \n\tCONSTRAINT ck_proc_eval_type CHECK (evaluation_type IN ('TECHNICAL','COMMERCIAL')), \n\tCONSTRAINT ck_proc_eval_result CHECK (result IN ('ACCEPTED','REJECTED','CONDITIONAL')), \n\tFOREIGN KEY(bid_id) REFERENCES procurement_bids (id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id), \n\tFOREIGN KEY(project_workspace_id) REFERENCES enterprise_workspaces (id), \n\tFOREIGN KEY(created_by) REFERENCES user_accounts (id)\n)",
        (
            "CREATE INDEX ix_procurement_evaluations_bid_id ON procurement_evaluations (bid_id)",
            "CREATE INDEX ix_procurement_evaluations_project_workspace_id ON procurement_evaluations (project_workspace_id)",
            "CREATE INDEX ix_procurement_evaluations_tenant_id ON procurement_evaluations (tenant_id)",
        ),
    ),
    (
        "procurement_awards",
        "CREATE TABLE procurement_awards (\n\trfq_id INTEGER NOT NULL, \n\tbid_id INTEGER NOT NULL, \n\tvendor_id INTEGER NOT NULL, \n\tpackage_id INTEGER NOT NULL, \n\tdecision_date DATE NOT NULL, \n\tapproval_reference VARCHAR(400) NOT NULL, \n\tdecision VARCHAR(24) NOT NULL, \n\tsnapshot_json JSON NOT NULL, \n\tcontent_hash VARCHAR(64) NOT NULL, \n\tid SERIAL NOT NULL, \n\ttenant_id INTEGER NOT NULL, \n\tproject_workspace_id INTEGER NOT NULL, \n\tversion INTEGER NOT NULL, \n\tcreated_by INTEGER NOT NULL, \n\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (rfq_id), \n\tFOREIGN KEY(rfq_id) REFERENCES procurement_rfqs (id), \n\tFOREIGN KEY(bid_id) REFERENCES procurement_bids (id), \n\tFOREIGN KEY(vendor_id) REFERENCES procurement_vendors (id), \n\tFOREIGN KEY(package_id) REFERENCES procurement_packages (id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id), \n\tFOREIGN KEY(project_workspace_id) REFERENCES enterprise_workspaces (id), \n\tFOREIGN KEY(created_by) REFERENCES user_accounts (id)\n)",
        (
            "CREATE INDEX ix_procurement_awards_bid_id ON procurement_awards (bid_id)",
            "CREATE INDEX ix_procurement_awards_package_id ON procurement_awards (package_id)",
            "CREATE INDEX ix_procurement_awards_project_workspace_id ON procurement_awards (project_workspace_id)",
            "CREATE INDEX ix_procurement_awards_tenant_id ON procurement_awards (tenant_id)",
            "CREATE INDEX ix_procurement_awards_vendor_id ON procurement_awards (vendor_id)",
        ),
    ),
    (
        "procurement_purchase_orders",
        "CREATE TABLE procurement_purchase_orders (\n\tpo_number VARCHAR(120) NOT NULL, \n\tpackage_id INTEGER NOT NULL, \n\tvendor_id INTEGER NOT NULL, \n\taward_id INTEGER, \n\tcurrency VARCHAR(3) NOT NULL, \n\tissue_date DATE NOT NULL, \n\teffective_date DATE NOT NULL, \n\texpected_delivery_date DATE NOT NULL, \n\tstatus VARCHAR(24) NOT NULL, \n\toriginal_value NUMERIC(20, 6) NOT NULL, \n\tcurrent_value NUMERIC(20, 6) NOT NULL, \n\tcurrent_revision_id INTEGER, \n\tapproved_by INTEGER, \n\tissued_by INTEGER, \n\tconfiguration_id INTEGER NOT NULL, \n\tconfiguration_hash VARCHAR(64) NOT NULL, \n\tlegacy_purchase_order_id INTEGER, \n\treference_contract_id INTEGER, \n\treference_commitment_id INTEGER, \n\tdocument_reference JSON NOT NULL, \n\tupdated_by INTEGER NOT NULL, \n\tupdated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n\tid SERIAL NOT NULL, \n\ttenant_id INTEGER NOT NULL, \n\tproject_workspace_id INTEGER NOT NULL, \n\tversion INTEGER NOT NULL, \n\tcreated_by INTEGER NOT NULL, \n\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_proc_po_no UNIQUE (tenant_id, project_workspace_id, po_number), \n\tCONSTRAINT ck_proc_po_status CHECK (status IN ('DRAFT','APPROVED','ISSUED','CANCELLED')), \n\tCONSTRAINT ck_proc_po_value CHECK (original_value >= 0 AND current_value >= 0), \n\tFOREIGN KEY(package_id) REFERENCES procurement_packages (id), \n\tFOREIGN KEY(vendor_id) REFERENCES procurement_vendors (id), \n\tUNIQUE (award_id), \n\tFOREIGN KEY(award_id) REFERENCES procurement_awards (id), \n\tFOREIGN KEY(approved_by) REFERENCES user_accounts (id), \n\tFOREIGN KEY(issued_by) REFERENCES user_accounts (id), \n\tFOREIGN KEY(configuration_id) REFERENCES admin_configurations (id), \n\tUNIQUE (legacy_purchase_order_id), \n\tFOREIGN KEY(legacy_purchase_order_id) REFERENCES purchase_orders (id), \n\tFOREIGN KEY(reference_contract_id) REFERENCES contracts (id), \n\tFOREIGN KEY(updated_by) REFERENCES user_accounts (id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id), \n\tFOREIGN KEY(project_workspace_id) REFERENCES enterprise_workspaces (id), \n\tFOREIGN KEY(created_by) REFERENCES user_accounts (id)\n)",
        (
            "CREATE INDEX ix_procurement_purchase_orders_package_id ON procurement_purchase_orders (package_id)",
            "CREATE INDEX ix_procurement_purchase_orders_project_workspace_id ON procurement_purchase_orders (project_workspace_id)",
            "CREATE INDEX ix_procurement_purchase_orders_tenant_id ON procurement_purchase_orders (tenant_id)",
            "CREATE INDEX ix_procurement_purchase_orders_vendor_id ON procurement_purchase_orders (vendor_id)",
        ),
    ),
    (
        "procurement_po_lines",
        "CREATE TABLE procurement_po_lines (\n\tpurchase_order_id INTEGER NOT NULL, \n\trequirement_id INTEGER NOT NULL, \n\tline_number INTEGER NOT NULL, \n\tdescription TEXT NOT NULL, \n\tquantity NUMERIC(18, 6) NOT NULL, \n\tuom VARCHAR(24) NOT NULL, \n\tunit_price NUMERIC(18, 6) NOT NULL, \n\trequested_date DATE NOT NULL, \n\tpromised_date DATE, \n\tforecast_date DATE, \n\tid SERIAL NOT NULL, \n\ttenant_id INTEGER NOT NULL, \n\tproject_workspace_id INTEGER NOT NULL, \n\tversion INTEGER NOT NULL, \n\tcreated_by INTEGER NOT NULL, \n\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_proc_po_line_no UNIQUE (purchase_order_id, line_number), \n\tCONSTRAINT ck_proc_po_line_qty_price CHECK (quantity > 0 AND unit_price >= 0 AND line_number > 0), \n\tFOREIGN KEY(purchase_order_id) REFERENCES procurement_purchase_orders (id), \n\tFOREIGN KEY(requirement_id) REFERENCES procurement_requirements (id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id), \n\tFOREIGN KEY(project_workspace_id) REFERENCES enterprise_workspaces (id), \n\tFOREIGN KEY(created_by) REFERENCES user_accounts (id)\n)",
        (
            "CREATE INDEX ix_procurement_po_lines_project_workspace_id ON procurement_po_lines (project_workspace_id)",
            "CREATE INDEX ix_procurement_po_lines_purchase_order_id ON procurement_po_lines (purchase_order_id)",
            "CREATE INDEX ix_procurement_po_lines_requirement_id ON procurement_po_lines (requirement_id)",
            "CREATE INDEX ix_procurement_po_lines_tenant_id ON procurement_po_lines (tenant_id)",
        ),
    ),
    (
        "procurement_po_revisions",
        "CREATE TABLE procurement_po_revisions (\n\tpurchase_order_id INTEGER NOT NULL, \n\tprevious_revision_id INTEGER, \n\trevision INTEGER NOT NULL, \n\teffective_date DATE NOT NULL, \n\tstatus VARCHAR(24) NOT NULL, \n\treason TEXT NOT NULL, \n\tlines_snapshot JSON NOT NULL, \n\tvalue_delta NUMERIC(20, 6) NOT NULL, \n\ttotal_value NUMERIC(20, 6) NOT NULL, \n\tschedule_impact_reference JSON NOT NULL, \n\tapproved_by INTEGER, \n\tapproval_reference VARCHAR(400) NOT NULL, \n\tcontent_hash VARCHAR(64) NOT NULL, \n\tupdated_by INTEGER NOT NULL, \n\tupdated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n\tid SERIAL NOT NULL, \n\ttenant_id INTEGER NOT NULL, \n\tproject_workspace_id INTEGER NOT NULL, \n\tversion INTEGER NOT NULL, \n\tcreated_by INTEGER NOT NULL, \n\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_proc_po_revision UNIQUE (purchase_order_id, revision), \n\tCONSTRAINT ck_proc_po_revision_status CHECK (status IN ('DRAFT','APPROVED') AND revision > 0), \n\tFOREIGN KEY(purchase_order_id) REFERENCES procurement_purchase_orders (id), \n\tUNIQUE (previous_revision_id), \n\tFOREIGN KEY(previous_revision_id) REFERENCES procurement_po_revisions (id), \n\tFOREIGN KEY(approved_by) REFERENCES user_accounts (id), \n\tFOREIGN KEY(updated_by) REFERENCES user_accounts (id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id), \n\tFOREIGN KEY(project_workspace_id) REFERENCES enterprise_workspaces (id), \n\tFOREIGN KEY(created_by) REFERENCES user_accounts (id)\n)",
        (
            "CREATE INDEX ix_procurement_po_revisions_project_workspace_id ON procurement_po_revisions (project_workspace_id)",
            "CREATE INDEX ix_procurement_po_revisions_purchase_order_id ON procurement_po_revisions (purchase_order_id)",
            "CREATE INDEX ix_procurement_po_revisions_tenant_id ON procurement_po_revisions (tenant_id)",
        ),
    ),
    (
        "procurement_vendor_milestones",
        "CREATE TABLE procurement_vendor_milestones (\n\tpo_line_id INTEGER NOT NULL, \n\tcode VARCHAR(80) NOT NULL, \n\tplanned_date DATE NOT NULL, \n\tforecast_date DATE, \n\tactual_date DATE, \n\tsupersedes_id INTEGER, \n\tcontent_hash VARCHAR(64) NOT NULL, \n\tid SERIAL NOT NULL, \n\ttenant_id INTEGER NOT NULL, \n\tproject_workspace_id INTEGER NOT NULL, \n\tversion INTEGER NOT NULL, \n\tcreated_by INTEGER NOT NULL, \n\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_procurement_milestone_version UNIQUE (po_line_id, code, version), \n\tFOREIGN KEY(po_line_id) REFERENCES procurement_po_lines (id), \n\tUNIQUE (supersedes_id), \n\tFOREIGN KEY(supersedes_id) REFERENCES procurement_vendor_milestones (id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id), \n\tFOREIGN KEY(project_workspace_id) REFERENCES enterprise_workspaces (id), \n\tFOREIGN KEY(created_by) REFERENCES user_accounts (id)\n)",
        (
            "CREATE INDEX ix_procurement_vendor_milestones_po_line_id ON procurement_vendor_milestones (po_line_id)",
            "CREATE INDEX ix_procurement_vendor_milestones_project_workspace_id ON procurement_vendor_milestones (project_workspace_id)",
            "CREATE INDEX ix_procurement_vendor_milestones_tenant_id ON procurement_vendor_milestones (tenant_id)",
        ),
    ),
    (
        "procurement_expediting_events",
        "CREATE TABLE procurement_expediting_events (\n\tpo_line_id INTEGER NOT NULL, \n\tevent_type VARCHAR(40) NOT NULL, \n\tobservation_date DATE NOT NULL, \n\tforecast_date DATE, \n\tprogress_percent NUMERIC(7, 3), \n\tdetail TEXT NOT NULL, \n\tcontent_hash VARCHAR(64) NOT NULL, \n\tid SERIAL NOT NULL, \n\ttenant_id INTEGER NOT NULL, \n\tproject_workspace_id INTEGER NOT NULL, \n\tversion INTEGER NOT NULL, \n\tcreated_by INTEGER NOT NULL, \n\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT ck_procurement_vendor_progress CHECK (progress_percent BETWEEN 0 AND 100), \n\tFOREIGN KEY(po_line_id) REFERENCES procurement_po_lines (id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id), \n\tFOREIGN KEY(project_workspace_id) REFERENCES enterprise_workspaces (id), \n\tFOREIGN KEY(created_by) REFERENCES user_accounts (id)\n)",
        (
            "CREATE INDEX ix_procurement_expediting_events_po_line_id ON procurement_expediting_events (po_line_id)",
            "CREATE INDEX ix_procurement_expediting_events_project_workspace_id ON procurement_expediting_events (project_workspace_id)",
            "CREATE INDEX ix_procurement_expediting_events_tenant_id ON procurement_expediting_events (tenant_id)",
        ),
    ),
    (
        "procurement_inspections",
        "CREATE TABLE procurement_inspections (\n\tpo_line_id INTEGER NOT NULL, \n\tvendor_id INTEGER NOT NULL, \n\tinspection_type VARCHAR(80) NOT NULL, \n\tinspection_date DATE NOT NULL, \n\tstatus VARCHAR(20) NOT NULL, \n\tdecided_by INTEGER, \n\tdecided_at TIMESTAMP WITHOUT TIME ZONE, \n\tdetail TEXT NOT NULL, \n\tncr_reference VARCHAR(240) NOT NULL, \n\tdocument_reference_json JSON NOT NULL, \n\tid SERIAL NOT NULL, \n\ttenant_id INTEGER NOT NULL, \n\tproject_workspace_id INTEGER NOT NULL, \n\tversion INTEGER NOT NULL, \n\tcreated_by INTEGER NOT NULL, \n\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT ck_procurement_inspection_status CHECK (status IN ('PLANNED','ACCEPTED','REJECTED','CONDITIONAL')), \n\tFOREIGN KEY(po_line_id) REFERENCES procurement_po_lines (id), \n\tFOREIGN KEY(decided_by) REFERENCES user_accounts (id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id), \n\tFOREIGN KEY(project_workspace_id) REFERENCES enterprise_workspaces (id), \n\tFOREIGN KEY(created_by) REFERENCES user_accounts (id)\n)",
        (
            "CREATE INDEX ix_procurement_inspections_po_line_id ON procurement_inspections (po_line_id)",
            "CREATE INDEX ix_procurement_inspections_project_workspace_id ON procurement_inspections (project_workspace_id)",
            "CREATE INDEX ix_procurement_inspections_tenant_id ON procurement_inspections (tenant_id)",
        ),
    ),
    (
        "procurement_shipment_lines",
        "CREATE TABLE procurement_shipment_lines (\n\tshipment_id INTEGER NOT NULL, \n\tpo_line_id INTEGER NOT NULL, \n\tmaterial_requirement_id INTEGER NOT NULL, \n\tquantity NUMERIC(20, 6) NOT NULL, \n\tuom VARCHAR(24) NOT NULL, \n\tpo_revision_hash VARCHAR(64) NOT NULL, \n\tid SERIAL NOT NULL, \n\ttenant_id INTEGER NOT NULL, \n\tproject_workspace_id INTEGER NOT NULL, \n\tversion INTEGER NOT NULL, \n\tcreated_by INTEGER NOT NULL, \n\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_procurement_shipment_po_line UNIQUE (shipment_id, po_line_id), \n\tCONSTRAINT ck_procurement_shipment_line_qty CHECK (quantity > 0), \n\tFOREIGN KEY(shipment_id) REFERENCES procurement_shipments (id), \n\tFOREIGN KEY(po_line_id) REFERENCES procurement_po_lines (id), \n\tFOREIGN KEY(material_requirement_id) REFERENCES procurement_material_requirements (id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id), \n\tFOREIGN KEY(project_workspace_id) REFERENCES enterprise_workspaces (id), \n\tFOREIGN KEY(created_by) REFERENCES user_accounts (id)\n)",
        (
            "CREATE INDEX ix_procurement_shipment_lines_material_requirement_id ON procurement_shipment_lines (material_requirement_id)",
            "CREATE INDEX ix_procurement_shipment_lines_po_line_id ON procurement_shipment_lines (po_line_id)",
            "CREATE INDEX ix_procurement_shipment_lines_project_workspace_id ON procurement_shipment_lines (project_workspace_id)",
            "CREATE INDEX ix_procurement_shipment_lines_shipment_id ON procurement_shipment_lines (shipment_id)",
            "CREATE INDEX ix_procurement_shipment_lines_tenant_id ON procurement_shipment_lines (tenant_id)",
        ),
    ),
    (
        "procurement_material_receipt_lines",
        "CREATE TABLE procurement_material_receipt_lines (\n\treceipt_id INTEGER NOT NULL, \n\tshipment_line_id INTEGER NOT NULL, \n\tpo_line_id INTEGER NOT NULL, \n\tmaterial_item_id INTEGER NOT NULL, \n\tmaterial_requirement_id INTEGER NOT NULL, \n\tquantity NUMERIC(20, 6) NOT NULL, \n\tuom VARCHAR(24) NOT NULL, \n\tid SERIAL NOT NULL, \n\ttenant_id INTEGER NOT NULL, \n\tproject_workspace_id INTEGER NOT NULL, \n\tversion INTEGER NOT NULL, \n\tcreated_by INTEGER NOT NULL, \n\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_procurement_receipt_shipment_line UNIQUE (receipt_id, shipment_line_id), \n\tCONSTRAINT ck_procurement_material_receipt_qty CHECK (quantity > 0), \n\tFOREIGN KEY(receipt_id) REFERENCES procurement_material_receipts (id), \n\tFOREIGN KEY(shipment_line_id) REFERENCES procurement_shipment_lines (id), \n\tFOREIGN KEY(po_line_id) REFERENCES procurement_po_lines (id), \n\tFOREIGN KEY(material_item_id) REFERENCES procurement_material_items (id), \n\tFOREIGN KEY(material_requirement_id) REFERENCES procurement_material_requirements (id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id), \n\tFOREIGN KEY(project_workspace_id) REFERENCES enterprise_workspaces (id), \n\tFOREIGN KEY(created_by) REFERENCES user_accounts (id)\n)",
        (
            "CREATE INDEX ix_procurement_material_receipt_lines_material_item_id ON procurement_material_receipt_lines (material_item_id)",
            "CREATE INDEX ix_procurement_material_receipt_lines_material_requirement_id ON procurement_material_receipt_lines (material_requirement_id)",
            "CREATE INDEX ix_procurement_material_receipt_lines_po_line_id ON procurement_material_receipt_lines (po_line_id)",
            "CREATE INDEX ix_procurement_material_receipt_lines_project_workspace_id ON procurement_material_receipt_lines (project_workspace_id)",
            "CREATE INDEX ix_procurement_material_receipt_lines_receipt_id ON procurement_material_receipt_lines (receipt_id)",
            "CREATE INDEX ix_procurement_material_receipt_lines_shipment_line_id ON procurement_material_receipt_lines (shipment_line_id)",
            "CREATE INDEX ix_procurement_material_receipt_lines_tenant_id ON procurement_material_receipt_lines (tenant_id)",
        ),
    ),
    (
        "procurement_material_acceptances",
        "CREATE TABLE procurement_material_acceptances (\n\treceipt_line_id INTEGER NOT NULL, \n\tinspection_id INTEGER, \n\taccepted_quantity NUMERIC(20, 6) NOT NULL, \n\trejected_quantity NUMERIC(20, 6) NOT NULL, \n\tquarantine_quantity NUMERIC(20, 6) NOT NULL, \n\tdetail TEXT NOT NULL, \n\tcontent_hash VARCHAR(64) NOT NULL, \n\tid SERIAL NOT NULL, \n\ttenant_id INTEGER NOT NULL, \n\tproject_workspace_id INTEGER NOT NULL, \n\tversion INTEGER NOT NULL, \n\tcreated_by INTEGER NOT NULL, \n\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT ck_procurement_material_acceptance_qty CHECK (accepted_quantity >= 0 AND rejected_quantity >= 0 AND quarantine_quantity >= 0 AND accepted_quantity + rejected_quantity + quarantine_quantity > 0), \n\tUNIQUE (receipt_line_id), \n\tFOREIGN KEY(receipt_line_id) REFERENCES procurement_material_receipt_lines (id), \n\tFOREIGN KEY(inspection_id) REFERENCES procurement_inspections (id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id), \n\tFOREIGN KEY(project_workspace_id) REFERENCES enterprise_workspaces (id), \n\tFOREIGN KEY(created_by) REFERENCES user_accounts (id)\n)",
        (
            "CREATE INDEX ix_procurement_material_acceptances_project_workspace_id ON procurement_material_acceptances (project_workspace_id)",
            "CREATE INDEX ix_procurement_material_acceptances_tenant_id ON procurement_material_acceptances (tenant_id)",
        ),
    ),
    (
        "procurement_material_allocations",
        "CREATE TABLE procurement_material_allocations (\n\treceipt_line_id INTEGER NOT NULL, \n\tacceptance_id INTEGER NOT NULL, \n\tmaterial_requirement_id INTEGER NOT NULL, \n\twork_package_id INTEGER NOT NULL, \n\tquantity NUMERIC(20, 6) NOT NULL, \n\tuom VARCHAR(24) NOT NULL, \n\tallocation_date DATE NOT NULL, \n\texpires_on DATE, \n\tsource_location VARCHAR(240) NOT NULL, \n\tstate VARCHAR(12) NOT NULL, \n\tsupersedes_id INTEGER, \n\tcontent_hash VARCHAR(64) NOT NULL, \n\tid SERIAL NOT NULL, \n\ttenant_id INTEGER NOT NULL, \n\tproject_workspace_id INTEGER NOT NULL, \n\tversion INTEGER NOT NULL, \n\tcreated_by INTEGER NOT NULL, \n\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT ck_procurement_material_allocation_qty CHECK (quantity > 0), \n\tCONSTRAINT ck_procurement_material_allocation_state CHECK ((state='ACTIVE' AND supersedes_id IS NULL) OR (state='RELEASED' AND supersedes_id IS NOT NULL)), \n\tFOREIGN KEY(receipt_line_id) REFERENCES procurement_material_receipt_lines (id), \n\tFOREIGN KEY(acceptance_id) REFERENCES procurement_material_acceptances (id), \n\tFOREIGN KEY(material_requirement_id) REFERENCES procurement_material_requirements (id), \n\tFOREIGN KEY(work_package_id) REFERENCES awp_work_packages (id), \n\tUNIQUE (supersedes_id), \n\tFOREIGN KEY(supersedes_id) REFERENCES procurement_material_allocations (id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id), \n\tFOREIGN KEY(project_workspace_id) REFERENCES enterprise_workspaces (id), \n\tFOREIGN KEY(created_by) REFERENCES user_accounts (id)\n)",
        (
            "CREATE INDEX ix_procurement_alloc_destination ON procurement_material_allocations (tenant_id, project_workspace_id, work_package_id, state)",
            "CREATE INDEX ix_procurement_material_allocations_material_requirement_id ON procurement_material_allocations (material_requirement_id)",
            "CREATE INDEX ix_procurement_material_allocations_project_workspace_id ON procurement_material_allocations (project_workspace_id)",
            "CREATE INDEX ix_procurement_material_allocations_receipt_line_id ON procurement_material_allocations (receipt_line_id)",
            "CREATE INDEX ix_procurement_material_allocations_tenant_id ON procurement_material_allocations (tenant_id)",
        ),
    ),
)

DEFERRED = (
    "ALTER TABLE procurement_purchase_orders ADD CONSTRAINT fk_proc_po_current_revision FOREIGN KEY(current_revision_id) REFERENCES procurement_po_revisions (id)",
)
