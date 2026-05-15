from __future__ import annotations

from dataclasses import dataclass
import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.domain.models import (
    ActivitySheet,
    ActivitySheetRecostRun,
    BusinessProcessInstance,
    BusinessProcessLineItemRevision,
    BusinessProcessPolicy,
    ControlAgentFinding,
    ControlAgentRun,
    ControlAccount,
    CostCode,
    RateSheet,
    WBS,
    WorkPackage,
    WorkPackageConstraint,
)
from app.services.ai_insights import AIInsightsError, generate_control_agent_synthesis


@dataclass
class FindingDraft:
    severity: str
    category: str
    title: str
    evidence: str
    recommendation: str
    owner_role: str
    entity_type: str = ""
    entity_id: int | None = None


class ControlAuditAgentService:
    agent_code = "control_audit"
    agent_name = "AI Control Auditor"
    model_name = "deterministic-control-audit-v1"
    awp_profile_name = "Senior AWP Packaging Advisor"
    awp_profile_principles = (
        "POC-first CWA/CWP/IWP hierarchy, non-overlapping CWP boundaries, "
        "EWP/procurement alignment and constraint-free IWP release readiness"
    )

    def __init__(self, db: Session, settings=None):
        self.db = db
        self.settings = settings or get_settings()

    def run(self, tenant_id: int, project_id: int, actor: str) -> ControlAgentRun:
        findings = self._collect_findings(tenant_id, project_id)
        summary = self._summary_with_optional_synthesis(self._summary(findings), findings)
        run = ControlAgentRun(
            tenant_id=tenant_id,
            project_id=project_id,
            agent_code=self.agent_code,
            agent_name=self.agent_name,
            run_mode="deterministic",
            model_name=self.model_name,
            status="completed",
            score=self._score(findings),
            summary=summary,
            created_by=actor,
        )
        self.db.add(run)
        self.db.flush()
        for finding in findings:
            self.db.add(
                ControlAgentFinding(
                    tenant_id=tenant_id,
                    project_id=project_id,
                    run_id=run.id,
                    severity=finding.severity,
                    category=finding.category,
                    title=finding.title,
                    evidence=finding.evidence,
                    recommendation=finding.recommendation,
                    owner_role=finding.owner_role,
                    entity_type=finding.entity_type,
                    entity_id=finding.entity_id,
                    status="open",
                )
            )
        self.db.commit()
        self.db.refresh(run)
        return run

    def create_awp_draft_packages(self, tenant_id: int, project_id: int, actor: str) -> ControlAgentRun:
        existing_packages = {
            package.code: package
            for package in self.db.scalars(
                select(WorkPackage).where(WorkPackage.tenant_id == tenant_id, WorkPackage.project_id == project_id)
            ).all()
        }
        wbs_by_id = {
            wbs.id: wbs
            for wbs in self.db.scalars(
                select(WBS).where(WBS.tenant_id == tenant_id, WBS.project_id == project_id)
            ).all()
        }
        accounts = list(
            self.db.scalars(
                select(ControlAccount)
                .where(
                    ControlAccount.tenant_id == tenant_id,
                    ControlAccount.project_id == project_id,
                    ControlAccount.lifecycle_status != "closed",
                )
                .order_by(ControlAccount.start_date, ControlAccount.code)
            ).all()
        )

        findings: list[FindingDraft] = []
        created_constraints = 0
        skipped = 0
        for index, account in enumerate(accounts, start=1):
            wbs = wbs_by_id.get(account.wbs_id)
            area_token = _package_token(wbs.code if wbs else "AREA")
            account_token = _package_token(account.code)
            discipline = account.discipline or "General"
            cwa = self._ensure_package(
                existing_packages,
                tenant_id,
                project_id,
                code=f"CWA-{area_token}",
                package_type="CWA",
                title=f"Construction area - {(wbs.name if wbs else area_token)}",
                description=(
                    "Draft construction work area generated from WBS boundary for senior AWP review. "
                    "Validate geographic boundary and path-of-construction sequence before release."
                ),
                discipline="Multi-discipline",
                sequence_no=index * 10,
                path_of_construction=f"Area sequence for {(wbs.code if wbs else area_token)}",
                owner_role="AWP Champion",
                wbs_id=(wbs.id if wbs else None),
                control_account_id=None,
                parent_id=None,
                findings=findings,
            )
            if cwa.created:
                pass
            else:
                skipped += 1
            cwp = self._ensure_package(
                existing_packages,
                tenant_id,
                project_id,
                code=f"CWP-{account_token}",
                package_type="CWP",
                title=f"{discipline} construction package - {account.name}",
                description=(
                    "Draft CWP generated from control account scope. Review non-overlapping boundary, "
                    "contract alignment, EWP/procurement support and project controls before release."
                ),
                discipline=discipline,
                sequence_no=index * 10 + 1,
                path_of_construction=account.scope or f"Execute {account.name} in WBS {(wbs.code if wbs else area_token)}.",
                owner_role="Workface Planner",
                wbs_id=account.wbs_id,
                control_account_id=account.id,
                parent_id=cwa.package.id,
                findings=findings,
            )
            if cwp.created:
                pass
            else:
                skipped += 1
            iwp = self._ensure_package(
                existing_packages,
                tenant_id,
                project_id,
                code=f"IWP-{account_token}",
                package_type="IWP",
                title=f"Install workface package - {account.name}",
                description=(
                    "Draft IWP generated for workface planning. Validate documents, material availability, "
                    "access, permits, safety and quality checks for a constraint-free field release."
                ),
                discipline=discipline,
                sequence_no=index * 10 + 2,
                path_of_construction=account.scope or f"Install scope for {account.code}.",
                owner_role="Workface Planner",
                wbs_id=account.wbs_id,
                control_account_id=account.id,
                parent_id=cwp.package.id,
                findings=findings,
            )
            if iwp.created:
                created_constraints += self._create_default_iwp_constraints(tenant_id, project_id, iwp.package)
            else:
                skipped += 1

        created = sum(1 for finding in findings if finding.entity_type == "WorkPackage")
        if not accounts:
            findings.append(
                FindingDraft(
                    severity="medium",
                    category="awp_packaging",
                    title="No active control accounts available for AWP draft packaging",
                    evidence="The agent requires WBS-linked active control accounts to derive CWA/CWP/IWP boundaries.",
                    recommendation="Create or activate control accounts before generating AWP draft packages.",
                    owner_role="Control Manager",
                )
            )
        summary = (
            f"{self.awp_profile_name} created {created} draft AWP package(s) and "
            f"{created_constraints} readiness constraint(s). "
            f"Review criteria: {self.awp_profile_principles}. "
            f"Skipped {skipped} existing package(s)."
        )
        summary = self._summary_with_optional_synthesis(summary, findings)
        run = ControlAgentRun(
            tenant_id=tenant_id,
            project_id=project_id,
            agent_code=self.agent_code,
            agent_name=self.agent_name,
            run_mode="deterministic",
            model_name=self.model_name,
            status="completed",
            score=self._score(findings),
            summary=summary,
            created_by=actor,
        )
        self.db.add(run)
        self.db.flush()
        for finding in findings:
            self.db.add(
                ControlAgentFinding(
                    tenant_id=tenant_id,
                    project_id=project_id,
                    run_id=run.id,
                    severity=finding.severity,
                    category=finding.category,
                    title=finding.title,
                    evidence=finding.evidence,
                    recommendation=finding.recommendation,
                    owner_role=finding.owner_role,
                    entity_type=finding.entity_type,
                    entity_id=finding.entity_id,
                    status="open",
                )
            )
        self.db.commit()
        self.db.refresh(run)
        return run

    def _collect_findings(self, tenant_id: int, project_id: int) -> list[FindingDraft]:
        findings: list[FindingDraft] = []
        findings.extend(self._bp_policy_findings(tenant_id, project_id))
        findings.extend(self._recost_findings(tenant_id, project_id))
        findings.extend(self._funding_findings(tenant_id, project_id))
        findings.extend(self._variance_findings(tenant_id, project_id))
        findings.extend(self._line_revision_findings(tenant_id, project_id))
        return findings

    def _summary_with_optional_synthesis(self, summary: str, findings: list[FindingDraft]) -> str:
        try:
            synthesis = generate_control_agent_synthesis(
                {
                    "agent_name": self.agent_name,
                    "summary": summary,
                    "findings": [
                        {
                            "severity": finding.severity,
                            "category": finding.category,
                            "title": finding.title,
                            "evidence": finding.evidence,
                            "recommendation": finding.recommendation,
                            "owner_role": finding.owner_role,
                        }
                        for finding in findings
                    ],
                },
                ai_provider=self.settings.ai_provider,
                api_key=self.settings.anthropic_api_key,
                model=self.settings.ai_model,
                max_tokens=min(self.settings.ai_max_tokens, 512),
                timeout=self.settings.ai_timeout_seconds,
            )
        except AIInsightsError:
            return summary
        if not synthesis:
            return summary
        return f"{summary} Model synthesis: {synthesis}"

    def _ensure_package(
        self,
        existing_packages: dict[str, WorkPackage],
        tenant_id: int,
        project_id: int,
        *,
        code: str,
        package_type: str,
        title: str,
        description: str,
        discipline: str,
        sequence_no: int,
        path_of_construction: str,
        owner_role: str,
        wbs_id: int | None,
        control_account_id: int | None,
        parent_id: int | None,
        findings: list[FindingDraft],
    ) -> "_PackageResult":
        normalized_code = code[:80]
        existing = existing_packages.get(normalized_code)
        if existing:
            return _PackageResult(package=existing, created=False)
        package = WorkPackage(
            tenant_id=tenant_id,
            project_id=project_id,
            wbs_id=wbs_id,
            control_account_id=control_account_id,
            parent_id=parent_id,
            package_type=package_type,
            code=normalized_code,
            title=title[:260],
            description=description,
            discipline=discipline,
            sequence_no=sequence_no,
            path_of_construction=path_of_construction[:260],
            owner_role=owner_role,
            readiness_status="constraint_review",
            main_constraints=(
                f"Generated as draft by {self.awp_profile_name}; validate POC, CWP boundary, "
                "EWP/procurement support and IWP constraints before release."
            ),
            progress_percent=0,
        )
        self.db.add(package)
        self.db.flush()
        existing_packages[normalized_code] = package
        findings.append(
            FindingDraft(
                severity="info",
                category="awp_packaging",
                title=f"Created draft {package_type} {normalized_code}",
                evidence=f"{package.title} was generated from current WBS/control account boundaries.",
                recommendation=(
                    "Apply senior AWP review: confirm POC sequence, package boundary, owner, "
                    "EWP/procurement support and open constraints before field release."
                ),
                owner_role=owner_role,
                entity_type="WorkPackage",
                entity_id=package.id,
            )
        )
        return _PackageResult(package=package, created=True)

    def _create_default_iwp_constraints(self, tenant_id: int, project_id: int, package: WorkPackage) -> int:
        rows = [
            ("Engineering Documents", "Confirm IFC drawings, EWP references, terminal points and latest revisions."),
            ("Materials", "Confirm BOM, bag-and-tag readiness, warehouse allocation and long-lead item availability."),
            ("Safety / Quality", "Confirm JHA/FLHA, inspection points, ITP and quality hold points for the workface."),
            ("Permits / Access", "Confirm permits, access, scaffolding, lifting and work-front prerequisites."),
            ("Recost / Funding", "Confirm recost, CBS/FBS funding alignment and commitment availability before release."),
        ]
        for constraint_type, description in rows:
            self.db.add(
                WorkPackageConstraint(
                    tenant_id=tenant_id,
                    project_id=project_id,
                    work_package_id=package.id,
                    constraint_type=constraint_type,
                    description=description,
                    owner_role="Workface Planner",
                    status="open",
                    priority="medium",
                    evidence_ref="",
                    closure_note="",
                    exception_ref="",
                    blocking=True,
                )
            )
        return len(rows)

    def _bp_policy_findings(self, tenant_id: int, project_id: int) -> list[FindingDraft]:
        findings: list[FindingDraft] = []
        processes = list(
            self.db.scalars(
                select(BusinessProcessInstance)
                .where(
                    BusinessProcessInstance.tenant_id == tenant_id,
                    BusinessProcessInstance.project_id == project_id,
                    BusinessProcessInstance.process_code.in_(["BP-CBS-WBS", "BP-CBS-FUND"]),
                    BusinessProcessInstance.status != "closed",
                )
                .order_by(BusinessProcessInstance.created_at.desc())
            ).all()
        )
        seen_codes: set[str] = set()
        for process in processes:
            if process.process_code in seen_codes:
                continue
            seen_codes.add(process.process_code)
            policy = self.db.scalar(
                select(BusinessProcessPolicy).where(
                    BusinessProcessPolicy.tenant_id == tenant_id,
                    BusinessProcessPolicy.project_id == project_id,
                    BusinessProcessPolicy.process_code == process.process_code,
                    BusinessProcessPolicy.action == "approve_baseline",
                    BusinessProcessPolicy.status == "active",
                )
            )
            if not policy:
                findings.append(
                    FindingDraft(
                        severity="high",
                        category="bp_policy",
                        title=f"{process.process_code} approval policy is not configured",
                        evidence=f"{process.record_no} is active at {process.current_step} without an approve_baseline policy.",
                        recommendation="Configure BP Permissions with required_role and permission_key before production approvals.",
                        owner_role="Control Manager",
                        entity_type="BusinessProcessInstance",
                        entity_id=process.id,
                    )
                )
        return findings

    def _recost_findings(self, tenant_id: int, project_id: int) -> list[FindingDraft]:
        latest_sheet = self.db.scalar(
            select(ActivitySheet)
            .where(ActivitySheet.tenant_id == tenant_id, ActivitySheet.project_id == project_id)
            .order_by(ActivitySheet.created_at.desc(), ActivitySheet.id.desc())
        )
        rate_sheet_count = int(
            self.db.scalar(
                select(func.count(RateSheet.id)).where(
                    RateSheet.tenant_id == tenant_id,
                    RateSheet.project_id == project_id,
                    RateSheet.status == "active",
                )
            )
            or 0
        )
        if not latest_sheet or rate_sheet_count == 0:
            return []
        recost_count = int(
            self.db.scalar(
                select(func.count(ActivitySheetRecostRun.id)).where(
                    ActivitySheetRecostRun.tenant_id == tenant_id,
                    ActivitySheetRecostRun.project_id == project_id,
                    ActivitySheetRecostRun.activity_sheet_id == latest_sheet.id,
                )
            )
            or 0
        )
        if recost_count:
            return []
        return [
            FindingDraft(
                severity="medium",
                category="recost",
                title="Latest Activity Sheet has active rates but no recost run",
                evidence=f"{latest_sheet.source_file_name} has {rate_sheet_count} active Rate Sheet(s) available.",
                recommendation="Run Recost Latest before using planned cost or planned value for production decisions.",
                owner_role="Project Controls",
                entity_type="ActivitySheet",
                entity_id=latest_sheet.id,
            )
        ]

    def _funding_findings(self, tenant_id: int, project_id: int) -> list[FindingDraft]:
        rows = list(
            self.db.scalars(
                select(CostCode)
                .where(
                    CostCode.tenant_id == tenant_id,
                    CostCode.project_id == project_id,
                    CostCode.forecast > CostCode.funds_available,
                )
                .order_by((CostCode.forecast - CostCode.funds_available).desc())
                .limit(3)
            ).all()
        )
        return [
            FindingDraft(
                severity="high",
                category="funding",
                title=f"{row.code} forecast exceeds available funding",
                evidence=f"Forecast {row.forecast:,.2f} vs funding {row.funds_available:,.2f}.",
                recommendation="Reconcile FBS allocation or revise forecast before approving new commitments.",
                owner_role="Cost Engineer",
                entity_type="CostCode",
                entity_id=row.id,
            )
            for row in rows
        ]

    def _variance_findings(self, tenant_id: int, project_id: int) -> list[FindingDraft]:
        rows = list(
            self.db.scalars(
                select(CostCode)
                .where(
                    CostCode.tenant_id == tenant_id,
                    CostCode.project_id == project_id,
                    func.abs(CostCode.budget - CostCode.forecast) > 0.01,
                )
                .order_by(func.abs(CostCode.budget - CostCode.forecast).desc())
                .limit(3)
            ).all()
        )
        return [
            FindingDraft(
                severity="medium",
                category="reconciliation",
                title=f"{row.code} budget and forecast are out of balance",
                evidence=f"Budget {row.budget:,.2f} vs forecast {row.forecast:,.2f}.",
                recommendation="Review Reconciliation export and confirm whether the delta is approved change or forecast drift.",
                owner_role="Control Manager",
                entity_type="CostCode",
                entity_id=row.id,
            )
            for row in rows
        ]

    def _line_revision_findings(self, tenant_id: int, project_id: int) -> list[FindingDraft]:
        revision_count = int(
            self.db.scalar(
                select(func.count(BusinessProcessLineItemRevision.id)).where(
                    BusinessProcessLineItemRevision.tenant_id == tenant_id,
                    BusinessProcessLineItemRevision.project_id == project_id,
                )
            )
            or 0
        )
        if not revision_count:
            return []
        return [
            FindingDraft(
                severity="info",
                category="line_versioning",
                title="Business process line items have controlled revisions",
                evidence=f"{revision_count} line item revision(s) are available for audit trail review.",
                recommendation="Review Line Versions before closeout or baseline approval.",
                owner_role="Project Controls",
            )
        ]

    def _score(self, findings: list[FindingDraft]) -> int:
        weights = {"high": 20, "medium": 10, "low": 5, "info": 0}
        penalty = sum(weights.get(finding.severity, 5) for finding in findings)
        return max(0, 100 - penalty)

    def _summary(self, findings: list[FindingDraft]) -> str:
        if not findings:
            return "Control Audit Agent found no production hardening gaps in the current project snapshot."
        high = sum(1 for finding in findings if finding.severity == "high")
        medium = sum(1 for finding in findings if finding.severity == "medium")
        return f"Control Audit Agent found {len(findings)} finding(s): {high} high and {medium} medium priority."


@dataclass
class _PackageResult:
    package: WorkPackage
    created: bool


def _package_token(value: str) -> str:
    token = re.sub(r"[^A-Za-z0-9]+", "-", value.upper()).strip("-")
    return token[:60] or "GEN"
