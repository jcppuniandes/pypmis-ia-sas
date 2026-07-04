"""RFQ endpoints: bid packages, bids and evaluation summary."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_tenant_id, get_user_id
from app.api.v1._helpers import (
    require_active_user as _require_user,
)
from app.api.v1._helpers import (
    require_current_version as _require_current_version,
)
from app.api.v1._helpers import (
    require_membership as _require_membership,
)
from app.api.v1._helpers import (
    require_permission as _require_permission,
)
from app.api.v1._helpers import (
    touch_collaborative_record as _touch_collaborative_record,
)
from app.api.v1._helpers import (
    write_audit_log as _audit,
)
from app.core.time import utc_now
from app.database.session import get_db
from app.domain.models import RFQBid, RFQPackage
from app.domain.schemas import (
    RFQBidCreate,
    RFQBidOut,
    RFQBidUpdate,
    RFQPackageCreate,
    RFQPackageOut,
    RFQPackageUpdate,
    RFQSummary,
)

router = APIRouter()


def rfq_packages(db: Session, tenant_id: int, project_id: int) -> list[RFQPackage]:
    return list(
        db.scalars(
            select(RFQPackage)
            .where(RFQPackage.tenant_id == tenant_id, RFQPackage.project_id == project_id)
            .order_by(RFQPackage.due_date, RFQPackage.package_no)
        ).all()
    )


def rfq_bids(db: Session, tenant_id: int, project_id: int, rfq_package_id: int | None = None) -> list[RFQBid]:
    query = select(RFQBid).where(RFQBid.tenant_id == tenant_id, RFQBid.project_id == project_id)
    if rfq_package_id is not None:
        query = query.where(RFQBid.rfq_package_id == rfq_package_id)
    return list(db.scalars(query.order_by(RFQBid.weighted_score.desc(), RFQBid.bid_amount, RFQBid.bidder_name)).all())


def rfq_summary(packages: list[RFQPackage], bids: list[RFQBid]) -> RFQSummary:
    scored_bids = [bid for bid in bids if bid.status not in {"withdrawn", "disqualified", "void"}]
    recommended = max(scored_bids, key=lambda bid: (bid.weighted_score, -bid.bid_amount), default=None)
    return RFQSummary(
        total_packages=len(packages),
        issued_packages=sum(
            1 for package in packages if package.status in {"issued", "open", "under_evaluation", "awarded"}
        ),
        bids_received=len(scored_bids),
        average_weighted_score=round(sum(bid.weighted_score for bid in scored_bids) / len(scored_bids), 1)
        if scored_bids
        else 0,
        recommended_bidder=recommended.bidder_name if recommended else "",
        recommended_bid_amount=round(float(recommended.bid_amount or 0), 2) if recommended else 0,
    )


def _require_rfq_package(db: Session, tenant_id: int, project_id: int, rfq_package_id: int) -> RFQPackage:
    package = db.scalar(
        select(RFQPackage).where(
            RFQPackage.tenant_id == tenant_id,
            RFQPackage.project_id == project_id,
            RFQPackage.id == rfq_package_id,
        )
    )
    if not package:
        raise HTTPException(status_code=404, detail="RFQ package not found")
    return package


def _validate_rfq_bid_values(
    bid_amount: float, technical_score: float, commercial_score: float, schedule_score: float, risk_score: float
) -> None:
    if bid_amount <= 0:
        raise HTTPException(status_code=400, detail="Bid amount must be greater than zero")
    for field_name, value in {
        "technical_score": technical_score,
        "commercial_score": commercial_score,
        "schedule_score": schedule_score,
        "risk_score": risk_score,
    }.items():
        if value < 0 or value > 100:
            raise HTTPException(status_code=400, detail=f"{field_name} must be between 0 and 100")


def _rfq_weighted_score(
    technical_score: float, commercial_score: float, schedule_score: float, risk_score: float
) -> float:
    return round(technical_score * 0.35 + commercial_score * 0.35 + schedule_score * 0.15 + risk_score * 0.15, 1)


def _require_control_account(db: Session, tenant_id: int, project_id: int, account_id: int):
    # Late import: router.py includes this module, so the shared control-account
    # lookup can only be resolved once the aggregate router finished loading.
    from app.api.v1.router import _require_control_account as require_control_account

    return require_control_account(db, tenant_id, project_id, account_id)


@router.get("/projects/{project_id}/rfq-packages", response_model=list[RFQPackageOut])
def list_rfq_packages(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[RFQPackage]:
    _require_membership(db, tenant_id, project_id, user_id)
    return rfq_packages(db, tenant_id, project_id)


@router.post("/projects/{project_id}/rfq-packages", response_model=RFQPackageOut)
def create_rfq_package(
    project_id: int,
    payload: RFQPackageCreate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> RFQPackage:
    membership = _require_membership(db, tenant_id, project_id, user_id)
    _require_permission(membership, "can_manage_contract", "Current role cannot create RFQ packages")
    current_user = _require_user(db, tenant_id, user_id)
    if payload.control_account_id is not None:
        _require_control_account(db, tenant_id, project_id, payload.control_account_id)
    if payload.budget_amount < 0:
        raise HTTPException(status_code=400, detail="RFQ budget cannot be negative")
    package_no = payload.package_no.strip()
    if not package_no:
        raise HTTPException(status_code=400, detail="RFQ package number is required")
    existing = db.scalar(
        select(RFQPackage).where(
            RFQPackage.tenant_id == tenant_id,
            RFQPackage.project_id == project_id,
            RFQPackage.package_no == package_no,
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail="RFQ package number already exists in this project")
    package = RFQPackage(
        tenant_id=tenant_id,
        project_id=project_id,
        control_account_id=payload.control_account_id,
        package_no=package_no,
        title=payload.title.strip(),
        scope_summary=payload.scope_summary.strip(),
        procurement_method=payload.procurement_method.strip() or "RFQ",
        status=payload.status.strip() or "draft",
        budget_amount=payload.budget_amount,
        issue_date=payload.issue_date,
        due_date=payload.due_date,
    )
    db.add(package)
    db.flush()
    _audit(
        db,
        tenant_id,
        project_id,
        "create_rfq_package",
        "RFQPackage",
        package.id,
        json.dumps({"package_no": package.package_no, "budget_amount": package.budget_amount}),
        current_user.full_name,
    )
    db.commit()
    db.refresh(package)
    return package


@router.patch("/projects/{project_id}/rfq-packages/{rfq_package_id}", response_model=RFQPackageOut)
def update_rfq_package(
    project_id: int,
    rfq_package_id: int,
    payload: RFQPackageUpdate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> RFQPackage:
    membership = _require_membership(db, tenant_id, project_id, user_id)
    _require_permission(membership, "can_manage_contract", "Current role cannot update RFQ packages")
    current_user = _require_user(db, tenant_id, user_id)
    package = _require_rfq_package(db, tenant_id, project_id, rfq_package_id)
    _require_current_version(package, payload.expected_version)
    if payload.control_account_id is not None:
        _require_control_account(db, tenant_id, project_id, payload.control_account_id)
    if payload.budget_amount is not None and payload.budget_amount < 0:
        raise HTTPException(status_code=400, detail="RFQ budget cannot be negative")
    for field_name in (
        "control_account_id",
        "title",
        "scope_summary",
        "procurement_method",
        "status",
        "budget_amount",
        "issue_date",
        "due_date",
    ):
        value = getattr(payload, field_name)
        if value is not None:
            setattr(package, field_name, value.strip() if isinstance(value, str) else value)
    _touch_collaborative_record(package)
    _audit(
        db,
        tenant_id,
        project_id,
        "update_rfq_package",
        "RFQPackage",
        package.id,
        json.dumps({"status": package.status, "version": package.version}),
        current_user.full_name,
    )
    db.commit()
    db.refresh(package)
    return package


@router.get("/projects/{project_id}/rfq-packages/{rfq_package_id}/bids", response_model=list[RFQBidOut])
def list_rfq_bids(
    project_id: int,
    rfq_package_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[RFQBid]:
    _require_membership(db, tenant_id, project_id, user_id)
    _require_rfq_package(db, tenant_id, project_id, rfq_package_id)
    return rfq_bids(db, tenant_id, project_id, rfq_package_id)


@router.post("/projects/{project_id}/rfq-packages/{rfq_package_id}/bids", response_model=RFQBidOut)
def create_rfq_bid(
    project_id: int,
    rfq_package_id: int,
    payload: RFQBidCreate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> RFQBid:
    membership = _require_membership(db, tenant_id, project_id, user_id)
    _require_permission(membership, "can_manage_contract", "Current role cannot create RFQ bids")
    current_user = _require_user(db, tenant_id, user_id)
    _require_rfq_package(db, tenant_id, project_id, rfq_package_id)
    _validate_rfq_bid_values(
        payload.bid_amount,
        payload.technical_score,
        payload.commercial_score,
        payload.schedule_score,
        payload.risk_score,
    )
    bidder_name = payload.bidder_name.strip()
    if not bidder_name:
        raise HTTPException(status_code=400, detail="Bidder name is required")
    existing = db.scalar(
        select(RFQBid).where(
            RFQBid.tenant_id == tenant_id,
            RFQBid.project_id == project_id,
            RFQBid.rfq_package_id == rfq_package_id,
            RFQBid.bidder_name == bidder_name,
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail="Bidder already exists for this RFQ package")
    bid = RFQBid(
        tenant_id=tenant_id,
        project_id=project_id,
        rfq_package_id=rfq_package_id,
        bidder_name=bidder_name,
        bid_amount=payload.bid_amount,
        technical_score=payload.technical_score,
        commercial_score=payload.commercial_score,
        schedule_score=payload.schedule_score,
        risk_score=payload.risk_score,
        weighted_score=_rfq_weighted_score(
            payload.technical_score, payload.commercial_score, payload.schedule_score, payload.risk_score
        ),
        status=payload.status.strip() or "received",
        submitted_on=payload.submitted_on or utc_now().date(),
        notes=payload.notes.strip(),
    )
    db.add(bid)
    db.flush()
    _audit(
        db,
        tenant_id,
        project_id,
        "create_rfq_bid",
        "RFQBid",
        bid.id,
        json.dumps({"bidder_name": bid.bidder_name, "weighted_score": bid.weighted_score}),
        current_user.full_name,
    )
    db.commit()
    db.refresh(bid)
    return bid


@router.patch("/projects/{project_id}/rfq-bids/{bid_id}", response_model=RFQBidOut)
def update_rfq_bid(
    project_id: int,
    bid_id: int,
    payload: RFQBidUpdate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> RFQBid:
    membership = _require_membership(db, tenant_id, project_id, user_id)
    _require_permission(membership, "can_manage_contract", "Current role cannot update RFQ bids")
    current_user = _require_user(db, tenant_id, user_id)
    bid = db.scalar(
        select(RFQBid).where(
            RFQBid.tenant_id == tenant_id,
            RFQBid.project_id == project_id,
            RFQBid.id == bid_id,
        )
    )
    if not bid:
        raise HTTPException(status_code=404, detail="RFQ bid not found")
    _require_current_version(bid, payload.expected_version)
    bid_amount = payload.bid_amount if payload.bid_amount is not None else bid.bid_amount
    technical_score = payload.technical_score if payload.technical_score is not None else bid.technical_score
    commercial_score = payload.commercial_score if payload.commercial_score is not None else bid.commercial_score
    schedule_score = payload.schedule_score if payload.schedule_score is not None else bid.schedule_score
    risk_score = payload.risk_score if payload.risk_score is not None else bid.risk_score
    _validate_rfq_bid_values(bid_amount, technical_score, commercial_score, schedule_score, risk_score)
    for field_name in (
        "bidder_name",
        "bid_amount",
        "technical_score",
        "commercial_score",
        "schedule_score",
        "risk_score",
        "status",
        "submitted_on",
        "notes",
    ):
        value = getattr(payload, field_name)
        if value is not None:
            setattr(bid, field_name, value.strip() if isinstance(value, str) else value)
    bid.weighted_score = _rfq_weighted_score(
        bid.technical_score, bid.commercial_score, bid.schedule_score, bid.risk_score
    )
    _touch_collaborative_record(bid)
    _audit(
        db,
        tenant_id,
        project_id,
        "update_rfq_bid",
        "RFQBid",
        bid.id,
        json.dumps({"status": bid.status, "weighted_score": bid.weighted_score}),
        current_user.full_name,
    )
    db.commit()
    db.refresh(bid)
    return bid
