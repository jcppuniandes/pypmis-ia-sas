"""O2B tables must be created only through their guarded Alembic revision."""

PROCUREMENT_MIGRATION_TABLE_NAMES = frozenset(
    {
        "procurement_mappings",
        "procurement_material_items",
        "procurement_shipments",
        "procurement_vendors",
        "procurement_packages",
        "procurement_history",
        "procurement_material_receipts",
        "procurement_requirements",
        "procurement_requisitions",
        "procurement_material_requirements",
        "procurement_package_items",
        "procurement_requisition_lines",
        "procurement_rfqs",
        "procurement_rfq_vendors",
        "procurement_bids",
        "procurement_evaluations",
        "procurement_awards",
        "procurement_purchase_orders",
        "procurement_po_lines",
        "procurement_po_revisions",
        "procurement_vendor_milestones",
        "procurement_expediting_events",
        "procurement_inspections",
        "procurement_shipment_lines",
        "procurement_material_receipt_lines",
        "procurement_material_acceptances",
        "procurement_material_allocations",
    }
)
