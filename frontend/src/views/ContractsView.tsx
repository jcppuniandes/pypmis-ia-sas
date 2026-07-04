import type { AppShellCtx } from "../components/AppShellCtx";
import { currency, statusLabel } from "../components/utils";

export default function ContractsView({ ctx }: { ctx: AppShellCtx }) {
  const { activeView, dashboard, project, setActiveView, accountLabel } = ctx;
  return (
    <section
      className={activeView === "contracts" ? "viewPanel workspaceSection" : "viewPanel workspaceSection hidden"}
    >
      <div className="panelHeader">
        <h2>Contract Administration</h2>
        <button className="linkButton" onClick={() => setActiveView("bp-entry-forms")} type="button">
          Open contract forms
        </button>
      </div>
      <div className="contractGrid">
        <div>
          <strong>Contracts</strong>
          <div className="workList">
            {dashboard.contracts.map((contract) => (
              <article key={contract.id}>
                <strong>
                  {contract.code} / {contract.counterparty}
                </strong>
                <span>{contract.title}</span>
                <small>
                  {currency(contract.value, project.currency)} /{" "}
                  {contract.control_account_id ? accountLabel(contract.control_account_id) : "No control account"} /{" "}
                  {statusLabel(contract.status)}
                </small>
              </article>
            ))}
          </div>
        </div>
        <div>
          <strong>Purchase Orders</strong>
          <div className="workList">
            {dashboard.purchase_orders.map((order) => (
              <article key={order.id}>
                <strong>
                  {order.po_number} / {currency(order.committed_amount, project.currency)}
                </strong>
                <span>{order.description}</span>
                <small>
                  {order.control_account_id ? accountLabel(order.control_account_id) : "No control account"} /{" "}
                  {order.vendor || "No vendor"} / {statusLabel(order.status)}
                </small>
              </article>
            ))}
          </div>
        </div>
        <div>
          <strong>Payment Certificates</strong>
          <div className="workList">
            {dashboard.payment_certificates.map((certificate) => (
              <article key={certificate.id}>
                <strong>
                  {certificate.certificate_no} / {currency(certificate.certified_amount, project.currency)}
                </strong>
                <span>{certificate.period_label || "No period"}</span>
                <small>
                  {certificate.control_account_id ? accountLabel(certificate.control_account_id) : "No control account"}{" "}
                  / {statusLabel(certificate.status)}
                </small>
              </article>
            ))}
          </div>
        </div>
        <div>
          <strong>Warehouse Receipts</strong>
          <div className="workList">
            {dashboard.warehouse_receipts.map((receipt) => (
              <article key={receipt.id}>
                <strong>
                  {receipt.receipt_no} / {currency(receipt.received_value, project.currency)}
                </strong>
                <span>{receipt.description || "Warehouse receipt"}</span>
                <small>
                  {receipt.control_account_id ? accountLabel(receipt.control_account_id) : "No control account"} /{" "}
                  {statusLabel(receipt.status)}
                </small>
              </article>
            ))}
          </div>
        </div>
        <div>
          <strong>Communications</strong>
          <div className="workList">
            {dashboard.communications.map((communication) => (
              <article key={communication.id}>
                <strong>
                  {statusLabel(communication.communication_type)} / {communication.sent_on}
                </strong>
                <span>{communication.subject}</span>
                <small>{communication.reference || "No reference"}</small>
              </article>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
