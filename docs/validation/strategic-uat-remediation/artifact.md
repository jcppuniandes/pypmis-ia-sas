# Contract for current UAT artifact revisions

Retained sources are the five DOCX and the XLSX in the repository directory
`outputs/strategic-final-uat-20261014`. Their source SHA256 values are captured in
`release-results.json` immediately before the final builder runs. The inputs
must remain byte-for-byte unchanged. Source render QA resides in
`outputs/.qa/strategic-final-uat`; prior source page counts are Business13,
User23, Admin29, UAT32 and Closeout11.

This increment outputs only three revised Word documents and one revised XLSX
in `outputs/strategic-uat-remediation-20261015`.

## Word fidelity and edit slots

The existing document itself is the design authority. Do not substitute a new
theme or page system. Keep its Letter portrait sections, margins, header/footer
distances, Aptos body11 and existing black Title/Heading styles. Preserve
styles.xml, numbering, relationships, embedded logo and unrelated package parts.
Table body follows the existing 9.5pt style, navy header with white labels,
light gray borders, alternating pale gray rows, repeating header and cantSplit.

Measured retained Closeout geometry is 8.5 by11inches, margins
0.7201388889inches on all sides, header0.3inches and footer0.35inches.
Title is Aptos24; Heading1 is Aptos15. These are retained, not new presets.

- Admin: append only the affected CORE reconciliation API instructions as an
  addendum; retain the prior29pages as history and all business/manual content.
- UAT: append the new execution matrix and scoped evidence/counts; do not
  silently overwrite prior failed/blocked results or infer signatures.
- Closeout: replace the body content with the required27technical sections,
  retaining the source logo, styles, section system and PAGE footer field.
  Change only its literal cutoff date to15October2026.
- Business Process and User Guide: preserve the original bytes; do not create
  unnecessary copies or rewrite unaffected content.

No tracked changes, comments, content controls or new links are requested. The
native PAGE field is retained; render via hidden, read-only Word export then
the canonical packaged PNG renderer. Inspect every generated page and compare
unaffected source structures. Do not deliver render PDFs or PNGs.

## Workbook fidelity and edit slots

Import the existing8-sheet XLSX using bundled Artifact Tool. Preserve sheet
names/order, original formulas, tables, validation, panes, signoff fields and
unchanged content. Update only current UAT results, affected defect dispositions
and directly dependent release criteria. Add adjacent historical-result columns
to the UAT table area so the prior status/result/evidence remain recorded.
Never replace a previous failure/blocked result without that history. Render
the input area before editing and changed views afterward. Verify saved native
formulas/validations and cached calculation errors. ACCEPTED without name,
date and evidence must still be BLOCKED; all human signatures stay blank.

## Evidence gate

No partial technical stage becomes a full formal UAT PASS. No focused suite or
sum of reruns becomes a green global invocation. Use NOT_COMPLETED for missing
JUnit after interruption. Report the exact current blocker and only one next
recommendation. Final release remains NOT_VALIDATED unless every required
technical criterion is proven and independently checked.
