import type { AppShellCtx } from "../components/AppShellCtx";
import { fileSize, statusLabel } from "../components/utils";

export default function DocumentsView({ ctx }: { ctx: AppShellCtx }) {
  const { activeView, dashboard, setActiveView, handleAttachmentDownload } = ctx;
  return (
    <section
      className={activeView === "documents" ? "viewPanel workspaceSection" : "viewPanel workspaceSection hidden"}
    >
      <div className="panelHeader">
        <h2>Aconex-style Document Control</h2>
        <button className="linkButton" onClick={() => setActiveView("bp-entry-forms")} type="button">
          Open document forms
        </button>
      </div>
      <div className="costManagerSummary">
        <article>
          <span>Controlled Score</span>
          <strong>{dashboard.document_control_summary.controlled_document_score.toFixed(1)}%</strong>
          <small>
            {dashboard.document_control_summary.current_documents} current /{" "}
            {dashboard.document_control_summary.total_documents} total
          </small>
        </article>
        <article className={dashboard.document_control_summary.outstanding_reviews ? "risk" : ""}>
          <span>Reviews</span>
          <strong>{dashboard.document_control_summary.outstanding_reviews}</strong>
          <small>{dashboard.document_control_summary.overdue_reviews} overdue reviews</small>
        </article>
        <article>
          <span>Transmittals</span>
          <strong>{dashboard.document_control_summary.transmittals_sent}</strong>
          <small>{dashboard.document_transmittal_items.length} issued document revisions</small>
        </article>
        <article>
          <span>Files</span>
          <strong>{dashboard.document_attachments.length}</strong>
          <small>
            {fileSize(dashboard.document_attachments.reduce((total, item) => total + item.size_bytes, 0))} stored
            evidence
          </small>
        </article>
        <article className={dashboard.document_control_summary.open_mail ? "risk" : ""}>
          <span>Project Mail</span>
          <strong>{dashboard.document_control_summary.open_mail}</strong>
          <small>{dashboard.document_control_summary.overdue_mail} overdue responses</small>
        </article>
      </div>
      <div className="viewSplit">
        <div>
          <div className="subHeader">
            <strong>Document Register</strong>
            <span>{dashboard.documents.length} records</span>
          </div>
          <table>
            <thead>
              <tr>
                <th>No.</th>
                <th>Rev</th>
                <th>Title</th>
                <th>Discipline</th>
                <th>Status</th>
                <th>Review</th>
              </tr>
            </thead>
            <tbody>
              {dashboard.documents.map((document) => (
                <tr key={document.id}>
                  <td>{document.document_number}</td>
                  <td>{document.revision}</td>
                  <td>{document.title}</td>
                  <td>{document.discipline || document.doc_type}</td>
                  <td>{statusLabel(document.status)}</td>
                  <td>{statusLabel(document.review_status)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="subHeader spaced">
            <strong>Stored Files</strong>
            <span>{dashboard.document_attachments.length} files</span>
          </div>
          <div className="workList compactList">
            {dashboard.document_attachments.map((attachment) => {
              const document = dashboard.documents.find((item) => item.id === attachment.document_id);
              return (
                <article key={attachment.id}>
                  <strong>{attachment.original_file_name}</strong>
                  <span>
                    {document?.document_number ?? `Document ${attachment.document_id}`} /{" "}
                    {attachment.extension || "file"} / {fileSize(attachment.size_bytes)}
                  </span>
                  <small>
                    {attachment.sha256.slice(0, 16)}... / {statusLabel(attachment.source)} /{" "}
                    {statusLabel(attachment.scan_status)}
                  </small>
                  <button
                    className="linkButton compact"
                    onClick={() => void handleAttachmentDownload(attachment)}
                    type="button"
                  >
                    Download
                  </button>
                </article>
              );
            })}
          </div>
          <div className="subHeader spaced">
            <strong>Transmittals</strong>
            <span>{dashboard.document_transmittals.length} records</span>
          </div>
          <div className="workList compactList">
            {dashboard.document_transmittals.map((transmittal) => (
              <article key={transmittal.id}>
                <strong>
                  {transmittal.transmittal_no} / {statusLabel(transmittal.purpose)}
                </strong>
                <span>{transmittal.subject}</span>
                <small>
                  {transmittal.recipient_org || "No recipient"} / Due {transmittal.due_date ?? "Open"} /{" "}
                  {statusLabel(transmittal.status)}
                </small>
              </article>
            ))}
          </div>
        </div>
        <div>
          <div className="subHeader">
            <strong>Project Mail</strong>
            <span>{dashboard.project_mail.length} records</span>
          </div>
          <div className="workList compactList">
            {dashboard.project_mail.map((mail) => (
              <article className={mail.status === "outstanding" ? "blockedPackage" : ""} key={mail.id}>
                <strong>
                  {mail.mail_no} / {statusLabel(mail.mail_type)}
                </strong>
                <span>{mail.subject}</span>
                <small>
                  {mail.from_role || "Project"} to {mail.to_role || "Team"} / Due {mail.due_date ?? "Open"} /{" "}
                  {statusLabel(mail.status)}
                </small>
              </article>
            ))}
          </div>
          <div className="subHeader spaced">
            <strong>Review Steps</strong>
            <span>{dashboard.document_reviews.length} records</span>
          </div>
          <div className="workList compactList">
            {dashboard.document_reviews.map((review) => {
              const document = dashboard.documents.find((item) => item.id === review.document_id);
              return (
                <article className={review.review_status === "outstanding" ? "blockedPackage" : ""} key={review.id}>
                  <strong>
                    {document?.document_number ?? `Document ${review.document_id}`} / {review.reviewer_role}
                  </strong>
                  <span>{review.comments || "No comments"}</span>
                  <small>
                    Due {review.due_date ?? "Open"} / {statusLabel(review.review_status)}
                  </small>
                </article>
              );
            })}
          </div>
        </div>
      </div>
    </section>
  );
}
