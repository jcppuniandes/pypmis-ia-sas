"""Document control endpoints: register, attachments, transmittals, reviews and project mail."""

from __future__ import annotations

import hashlib
import json
import mimetypes
import socket
from io import BytesIO
from pathlib import Path, PurePosixPath
from uuid import uuid4
from zipfile import BadZipFile, ZipFile

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
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
    require_project as _require_project,
)
from app.api.v1._helpers import (
    touch_collaborative_record as _touch_collaborative_record,
)
from app.api.v1._helpers import (
    write_audit_log as _audit,
)
from app.core.config import get_settings
from app.core.time import utc_now
from app.database.session import get_db
from app.domain.models import (
    Document,
    DocumentAttachment,
    DocumentReview,
    DocumentTransmittal,
    DocumentTransmittalItem,
    Project,
    ProjectMail,
    ProjectMembership,
)
from app.domain.schemas import (
    DocumentAttachmentOut,
    DocumentControlSummary,
    DocumentCreate,
    DocumentOut,
    DocumentReviewCreate,
    DocumentReviewOut,
    DocumentReviewUpdate,
    DocumentTransmittalCreate,
    DocumentTransmittalItemOut,
    DocumentTransmittalOut,
    DocumentUpdate,
    ProjectMailCreate,
    ProjectMailOut,
    ProjectMailUpdate,
)

router = APIRouter()


def _count(db: Session, model: type, tenant_id: int, project_id: int) -> int:
    # Late import: router.py includes this module, so shared counters resolve
    # once the aggregate router finished loading.
    from app.api.v1.router import _count as count_records

    return count_records(db, model, tenant_id, project_id)


@router.get("/projects/{project_id}/documents", response_model=list[DocumentOut])
def list_documents(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[Document]:
    membership = _require_membership(db, tenant_id, project_id, user_id)
    return _accessible_documents(db, tenant_id, project_id, membership)


@router.post("/projects/{project_id}/documents", response_model=DocumentOut)
def create_document(
    project_id: int,
    payload: DocumentCreate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> Document:
    membership = _require_membership(db, tenant_id, project_id, user_id)
    _require_document_control_role(membership)
    project = _require_project(db, tenant_id, project_id)
    current_user = _require_user(db, tenant_id, user_id)
    document_number = payload.document_number.strip() or _next_document_number(db, tenant_id, project)
    revision = payload.revision.strip() or "A"
    _ensure_document_revision_available(db, tenant_id, project_id, document_number, revision)
    document = Document(
        tenant_id=tenant_id,
        project_id=project_id,
        document_number=document_number,
        revision=revision,
        revision_date=payload.revision_date,
        linked_entity_type=payload.linked_entity_type,
        linked_entity_id=payload.linked_entity_id,
        title=payload.title,
        doc_type=payload.doc_type,
        discipline=payload.discipline,
        organization=payload.organization,
        status=payload.status,
        review_status=payload.review_status,
        confidentiality=payload.confidentiality,
        file_name=payload.file_name,
        uri=payload.uri,
    )
    db.add(document)
    db.flush()
    _audit(
        db,
        tenant_id,
        project_id,
        "register_document",
        "Document",
        document.id,
        json.dumps(
            {"document_number": document.document_number, "revision": document.revision, "title": document.title}
        ),
        current_user.full_name,
    )
    db.commit()
    db.refresh(document)
    return document


@router.patch("/projects/{project_id}/documents/{document_id}", response_model=DocumentOut)
def update_document(
    project_id: int,
    document_id: int,
    payload: DocumentUpdate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> Document:
    membership = _require_membership(db, tenant_id, project_id, user_id)
    _require_document_control_role(membership)
    current_user = _require_user(db, tenant_id, user_id)
    document = _require_document(db, tenant_id, project_id, document_id)
    _require_current_version(document, payload.expected_version)
    next_document_number = (
        payload.document_number.strip() if payload.document_number is not None else document.document_number
    )
    next_revision = payload.revision.strip() if payload.revision is not None else document.revision
    if next_document_number != document.document_number or next_revision != document.revision:
        _ensure_document_revision_available(
            db, tenant_id, project_id, next_document_number, next_revision, exclude_id=document.id
        )
    for field, value in payload.model_dump(exclude_unset=True, exclude={"expected_version"}).items():
        if isinstance(value, str):
            value = value.strip()
        setattr(document, field, value)
    if not document.document_number:
        document.document_number = _next_document_number(db, tenant_id, _require_project(db, tenant_id, project_id))
    if not document.revision:
        document.revision = "A"
    _touch_collaborative_record(document)
    _audit(
        db,
        tenant_id,
        project_id,
        "update_document",
        "Document",
        document.id,
        json.dumps(
            {"document_number": document.document_number, "revision": document.revision, "status": document.status}
        ),
        current_user.full_name,
    )
    db.commit()
    db.refresh(document)
    return document


@router.get("/projects/{project_id}/document-attachments", response_model=list[DocumentAttachmentOut])
def list_project_document_attachments(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[DocumentAttachment]:
    membership = _require_membership(db, tenant_id, project_id, user_id)
    return _accessible_document_attachments(db, tenant_id, project_id, membership)


@router.get("/projects/{project_id}/documents/{document_id}/attachments", response_model=list[DocumentAttachmentOut])
def list_document_attachments(
    project_id: int,
    document_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[DocumentAttachment]:
    membership = _require_membership(db, tenant_id, project_id, user_id)
    document = _require_document(db, tenant_id, project_id, document_id)
    _require_document_access(membership, document)
    return _document_attachments(db, tenant_id, project_id, document_id)


@router.post("/projects/{project_id}/documents/{document_id}/attachments", response_model=list[DocumentAttachmentOut])
async def upload_document_attachment(
    project_id: int,
    document_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[DocumentAttachment]:
    membership = _require_membership(db, tenant_id, project_id, user_id)
    _require_document_control_role(membership)
    current_user = _require_user(db, tenant_id, user_id)
    document = _require_document(db, tenant_id, project_id, document_id)
    _require_document_access(membership, document)
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Document file is empty")

    original_name = _safe_original_file_name(file.filename or "document.bin")
    extension = _attachment_extension(original_name)
    if extension == ".zip":
        attachments = _store_zip_attachments(
            db=db,
            tenant_id=tenant_id,
            project_id=project_id,
            document=document,
            zip_name=original_name,
            content=content,
            uploaded_by=current_user.full_name,
        )
    else:
        attachments = [
            _store_document_bytes(
                db=db,
                tenant_id=tenant_id,
                project_id=project_id,
                document=document,
                original_name=original_name,
                content=content,
                content_type=file.content_type or _guess_content_type(original_name),
                source="upload",
                uploaded_by=current_user.full_name,
            )
        ]

    document.file_name = document.file_name or attachments[0].original_file_name
    document.uri = document.uri or f"attachment://{attachments[0].id}"
    _touch_collaborative_record(document)
    _audit(
        db,
        tenant_id,
        project_id,
        "upload_document_attachment",
        "Document",
        document.id,
        json.dumps(
            {"document_number": document.document_number, "attachments": [attachment.id for attachment in attachments]}
        ),
        current_user.full_name,
    )
    db.commit()
    for attachment in attachments:
        db.refresh(attachment)
    return attachments


@router.get("/projects/{project_id}/documents/{document_id}/attachments/{attachment_id}/download")
def download_document_attachment(
    project_id: int,
    document_id: int,
    attachment_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> FileResponse:
    membership = _require_membership(db, tenant_id, project_id, user_id)
    document = _require_document(db, tenant_id, project_id, document_id)
    _require_document_access(membership, document)
    attachment = _require_document_attachment(db, tenant_id, project_id, document_id, attachment_id)
    path = _attachment_absolute_path(attachment)
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Stored document file not found")
    return FileResponse(path, media_type=attachment.content_type, filename=attachment.original_file_name)


@router.get("/projects/{project_id}/document-transmittals", response_model=list[DocumentTransmittalOut])
def list_document_transmittals(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[DocumentTransmittal]:
    _require_membership(db, tenant_id, project_id, user_id)
    return _document_transmittals(db, tenant_id, project_id)


@router.post("/projects/{project_id}/document-transmittals", response_model=DocumentTransmittalOut)
def create_document_transmittal(
    project_id: int,
    payload: DocumentTransmittalCreate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> DocumentTransmittal:
    membership = _require_membership(db, tenant_id, project_id, user_id)
    _require_document_control_role(membership)
    project = _require_project(db, tenant_id, project_id)
    current_user = _require_user(db, tenant_id, user_id)
    if not payload.document_ids:
        raise HTTPException(status_code=400, detail="At least one document is required for a transmittal")
    transmittal_no = payload.transmittal_no.strip() or _next_transmittal_no(db, tenant_id, project)
    existing = db.scalar(
        select(DocumentTransmittal).where(
            DocumentTransmittal.tenant_id == tenant_id,
            DocumentTransmittal.project_id == project_id,
            DocumentTransmittal.transmittal_no == transmittal_no,
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail="Transmittal number already exists for this project")
    documents = [_require_document(db, tenant_id, project_id, document_id) for document_id in payload.document_ids]
    transmittal = DocumentTransmittal(
        tenant_id=tenant_id,
        project_id=project_id,
        transmittal_no=transmittal_no,
        subject=payload.subject,
        purpose=payload.purpose,
        recipient_org=payload.recipient_org,
        recipient_contact=payload.recipient_contact,
        status=payload.status,
        sent_on=payload.sent_on or utc_now().date(),
        due_date=payload.due_date,
        created_by=current_user.full_name,
    )
    db.add(transmittal)
    db.flush()
    for document in documents:
        db.add(
            DocumentTransmittalItem(
                tenant_id=tenant_id,
                project_id=project_id,
                transmittal_id=transmittal.id,
                document_id=document.id,
                document_number=document.document_number,
                revision=document.revision,
                action_required=payload.action_required,
                response_status="outstanding" if payload.purpose in {"for_review", "for_approval"} else "issued",
            )
        )
    _audit(
        db,
        tenant_id,
        project_id,
        "issue_document_transmittal",
        "DocumentTransmittal",
        transmittal.id,
        json.dumps(
            {"transmittal_no": transmittal.transmittal_no, "documents": [document.id for document in documents]}
        ),
        current_user.full_name,
    )
    db.commit()
    db.refresh(transmittal)
    return transmittal


@router.get("/projects/{project_id}/document-transmittal-items", response_model=list[DocumentTransmittalItemOut])
def list_document_transmittal_items(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[DocumentTransmittalItem]:
    _require_membership(db, tenant_id, project_id, user_id)
    return _document_transmittal_items(db, tenant_id, project_id)


@router.get("/projects/{project_id}/document-reviews", response_model=list[DocumentReviewOut])
def list_document_reviews(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[DocumentReview]:
    _require_membership(db, tenant_id, project_id, user_id)
    return _document_reviews(db, tenant_id, project_id)


@router.post("/projects/{project_id}/documents/{document_id}/reviews", response_model=DocumentReviewOut)
def create_document_review(
    project_id: int,
    document_id: int,
    payload: DocumentReviewCreate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> DocumentReview:
    membership = _require_membership(db, tenant_id, project_id, user_id)
    _require_document_control_role(membership)
    current_user = _require_user(db, tenant_id, user_id)
    document = _require_document(db, tenant_id, project_id, document_id)
    review = DocumentReview(
        tenant_id=tenant_id,
        project_id=project_id,
        document_id=document.id,
        reviewer_role=payload.reviewer_role,
        review_status=payload.review_status,
        comments=payload.comments,
        due_date=payload.due_date,
    )
    document.review_status = payload.review_status
    _touch_collaborative_record(document)
    db.add(review)
    db.flush()
    _audit(
        db,
        tenant_id,
        project_id,
        "create_document_review",
        "DocumentReview",
        review.id,
        json.dumps({"document_id": document.id, "reviewer_role": review.reviewer_role}),
        current_user.full_name,
    )
    db.commit()
    db.refresh(review)
    return review


@router.patch("/projects/{project_id}/document-reviews/{review_id}", response_model=DocumentReviewOut)
def update_document_review(
    project_id: int,
    review_id: int,
    payload: DocumentReviewUpdate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> DocumentReview:
    membership = _require_membership(db, tenant_id, project_id, user_id)
    _require_document_control_role(membership)
    current_user = _require_user(db, tenant_id, user_id)
    review = db.scalar(
        select(DocumentReview).where(
            DocumentReview.tenant_id == tenant_id,
            DocumentReview.project_id == project_id,
            DocumentReview.id == review_id,
        )
    )
    if not review:
        raise HTTPException(status_code=404, detail="Document review not found")
    _require_current_version(review, payload.expected_version)
    for field, value in payload.model_dump(exclude_unset=True, exclude={"expected_version"}).items():
        setattr(review, field, value.strip() if isinstance(value, str) else value)
    _touch_collaborative_record(review)
    document = _require_document(db, tenant_id, project_id, review.document_id)
    document.review_status = review.review_status
    _touch_collaborative_record(document)
    _audit(
        db,
        tenant_id,
        project_id,
        "update_document_review",
        "DocumentReview",
        review.id,
        json.dumps({"review_status": review.review_status}),
        current_user.full_name,
    )
    db.commit()
    db.refresh(review)
    return review


@router.get("/projects/{project_id}/project-mail", response_model=list[ProjectMailOut])
def list_project_mail(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[ProjectMail]:
    _require_membership(db, tenant_id, project_id, user_id)
    return _project_mail(db, tenant_id, project_id)


@router.post("/projects/{project_id}/project-mail", response_model=ProjectMailOut)
def create_project_mail(
    project_id: int,
    payload: ProjectMailCreate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ProjectMail:
    membership = _require_membership(db, tenant_id, project_id, user_id)
    _require_document_control_role(membership)
    project = _require_project(db, tenant_id, project_id)
    current_user = _require_user(db, tenant_id, user_id)
    if payload.document_id is not None:
        _require_document(db, tenant_id, project_id, payload.document_id)
    mail_no = payload.mail_no.strip() or _next_mail_no(db, tenant_id, project)
    existing = db.scalar(
        select(ProjectMail).where(
            ProjectMail.tenant_id == tenant_id,
            ProjectMail.project_id == project_id,
            ProjectMail.mail_no == mail_no,
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail="Mail number already exists for this project")
    mail = ProjectMail(
        tenant_id=tenant_id,
        project_id=project_id,
        mail_no=mail_no,
        mail_type=payload.mail_type,
        subject=payload.subject,
        from_role=payload.from_role or membership.role,
        to_role=payload.to_role,
        status=payload.status,
        response_required=payload.response_required,
        sent_on=payload.sent_on or utc_now().date(),
        due_date=payload.due_date,
        body=payload.body,
        linked_entity_type=payload.linked_entity_type,
        linked_entity_id=payload.linked_entity_id,
        document_id=payload.document_id,
    )
    db.add(mail)
    db.flush()
    _audit(
        db,
        tenant_id,
        project_id,
        "send_project_mail",
        "ProjectMail",
        mail.id,
        json.dumps({"mail_no": mail.mail_no, "mail_type": mail.mail_type}),
        current_user.full_name,
    )
    db.commit()
    db.refresh(mail)
    return mail


@router.patch("/projects/{project_id}/project-mail/{mail_id}", response_model=ProjectMailOut)
def update_project_mail(
    project_id: int,
    mail_id: int,
    payload: ProjectMailUpdate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ProjectMail:
    membership = _require_membership(db, tenant_id, project_id, user_id)
    _require_document_control_role(membership)
    current_user = _require_user(db, tenant_id, user_id)
    mail = db.scalar(
        select(ProjectMail).where(
            ProjectMail.tenant_id == tenant_id,
            ProjectMail.project_id == project_id,
            ProjectMail.id == mail_id,
        )
    )
    if not mail:
        raise HTTPException(status_code=404, detail="Project mail not found")
    _require_current_version(mail, payload.expected_version)
    for field, value in payload.model_dump(exclude_unset=True, exclude={"expected_version"}).items():
        setattr(mail, field, value.strip() if isinstance(value, str) else value)
    _touch_collaborative_record(mail)
    _audit(
        db,
        tenant_id,
        project_id,
        "update_project_mail",
        "ProjectMail",
        mail.id,
        json.dumps({"status": mail.status}),
        current_user.full_name,
    )
    db.commit()
    db.refresh(mail)
    return mail


def _documents(db: Session, tenant_id: int, project_id: int) -> list[Document]:
    return list(
        db.scalars(
            select(Document)
            .where(Document.tenant_id == tenant_id, Document.project_id == project_id)
            .order_by(Document.document_number, Document.revision.desc(), Document.id)
        ).all()
    )


def _accessible_documents(
    db: Session,
    tenant_id: int,
    project_id: int,
    membership: ProjectMembership,
) -> list[Document]:
    return [
        document for document in _documents(db, tenant_id, project_id) if _can_access_document(membership, document)
    ]


def _document_attachments(
    db: Session,
    tenant_id: int,
    project_id: int,
    document_id: int | None = None,
) -> list[DocumentAttachment]:
    filters = [
        DocumentAttachment.tenant_id == tenant_id,
        DocumentAttachment.project_id == project_id,
    ]
    if document_id is not None:
        filters.append(DocumentAttachment.document_id == document_id)
    return list(
        db.scalars(
            select(DocumentAttachment)
            .where(*filters)
            .order_by(DocumentAttachment.created_at.desc(), DocumentAttachment.id.desc())
        ).all()
    )


def _accessible_document_attachments(
    db: Session,
    tenant_id: int,
    project_id: int,
    membership: ProjectMembership,
) -> list[DocumentAttachment]:
    attachments = _document_attachments(db, tenant_id, project_id)
    if not attachments:
        return []
    documents = {
        document.id: document
        for document in db.scalars(
            select(Document).where(
                Document.tenant_id == tenant_id,
                Document.project_id == project_id,
                Document.id.in_({attachment.document_id for attachment in attachments}),
            )
        ).all()
    }
    return [
        attachment
        for attachment in attachments
        if _can_access_document(membership, documents.get(attachment.document_id))
    ]


def _store_document_bytes(
    db: Session,
    tenant_id: int,
    project_id: int,
    document: Document,
    original_name: str,
    content: bytes,
    content_type: str,
    source: str,
    uploaded_by: str,
) -> DocumentAttachment:
    settings = get_settings()
    extension = _attachment_extension(original_name)
    _validate_document_upload(original_name, extension, len(content))
    scan_status, validation_message = _scan_document_content(original_name, content)
    digest = hashlib.sha256(content).hexdigest()
    stored_name = f"{uuid4().hex}{extension or '.bin'}"
    relative_path = Path(f"tenant_{tenant_id}") / f"project_{project_id}" / f"document_{document.id}" / stored_name
    root = Path(settings.document_storage_path).resolve()
    target = (root / relative_path).resolve()
    if not target.is_relative_to(root):
        raise HTTPException(status_code=400, detail="Invalid storage path")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    attachment = DocumentAttachment(
        tenant_id=tenant_id,
        project_id=project_id,
        document_id=document.id,
        original_file_name=original_name,
        stored_file_name=stored_name,
        storage_path=relative_path.as_posix(),
        content_type=content_type or _guess_content_type(original_name),
        extension=extension,
        size_bytes=len(content),
        sha256=digest,
        source=source,
        uploaded_by=uploaded_by,
        scan_status=scan_status,
        validation_message=validation_message,
    )
    db.add(attachment)
    db.flush()
    return attachment


def _store_zip_attachments(
    db: Session,
    tenant_id: int,
    project_id: int,
    document: Document,
    zip_name: str,
    content: bytes,
    uploaded_by: str,
) -> list[DocumentAttachment]:
    _validate_document_upload(zip_name, ".zip", len(content))
    settings = get_settings()
    try:
        archive = ZipFile(BytesIO(content))
    except BadZipFile as exc:
        raise HTTPException(status_code=400, detail="ZIP file is invalid") from exc
    with archive:
        members = [member for member in archive.infolist() if not member.is_dir()]
        if len(members) > settings.document_max_zip_files:
            raise HTTPException(
                status_code=413, detail=f"ZIP contains more than {settings.document_max_zip_files} files"
            )
        total_uncompressed = sum(member.file_size for member in members)
        if total_uncompressed > settings.document_max_zip_uncompressed_bytes:
            raise HTTPException(status_code=413, detail="ZIP uncompressed size exceeds configured limit")

        attachments: list[DocumentAttachment] = []
        for member in members:
            original_name = _safe_zip_member_name(member.filename)
            extension = _attachment_extension(original_name)
            if extension == ".zip":
                raise HTTPException(status_code=400, detail="Nested ZIP files are not accepted")
            _validate_document_upload(original_name, extension, member.file_size)
            attachments.append(
                _store_document_bytes(
                    db=db,
                    tenant_id=tenant_id,
                    project_id=project_id,
                    document=document,
                    original_name=original_name,
                    content=archive.read(member),
                    content_type=_guess_content_type(original_name),
                    source="zip",
                    uploaded_by=uploaded_by,
                )
            )
    if not attachments:
        raise HTTPException(status_code=400, detail="ZIP file does not contain supported files")
    return attachments


def _validate_document_upload(original_name: str, extension: str, size_bytes: int) -> None:
    settings = get_settings()
    blocked_extensions = {".bat", ".cmd", ".com", ".dll", ".exe", ".jar", ".js", ".msi", ".ps1", ".scr", ".sh", ".vbs"}
    if extension in blocked_extensions:
        raise HTTPException(status_code=400, detail=f"File type {extension} is not allowed")
    if extension not in settings.document_allowed_extension_set:
        raise HTTPException(status_code=400, detail=f"File type {extension or '(none)'} is not allowed")
    if size_bytes <= 0:
        raise HTTPException(status_code=400, detail=f"{original_name} is empty")
    if size_bytes > settings.document_max_upload_bytes:
        raise HTTPException(status_code=413, detail=f"{original_name} exceeds the configured upload size limit")


def _scan_document_content(original_name: str, content: bytes) -> tuple[str, str]:
    settings = get_settings()
    mode = settings.document_scan_mode.strip().lower()
    if mode in {"", "disabled", "off", "none"}:
        return "not_scanned", "Stored without antivirus scan. Enable DOCUMENT_SCAN_MODE=local or clamav."
    if _contains_eicar_signature(content):
        raise HTTPException(
            status_code=400, detail=f"{original_name} failed antivirus scan: EICAR test signature detected"
        )
    if mode == "local":
        return "clean", "Local malware signature gate passed."
    if mode == "clamav":
        _scan_with_clamav(original_name, content, settings.document_clamav_host, settings.document_clamav_port)
        return "clean", "ClamAV scan passed."
    raise HTTPException(status_code=500, detail=f"Unsupported DOCUMENT_SCAN_MODE: {settings.document_scan_mode}")


def _contains_eicar_signature(content: bytes) -> bool:
    return b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR" in content


def _scan_with_clamav(original_name: str, content: bytes, host: str, port: int) -> None:
    try:
        with socket.create_connection((host, port), timeout=5) as sock:
            sock.settimeout(10)
            sock.sendall(b"zINSTREAM\0")
            for index in range(0, len(content), 8192):
                chunk = content[index : index + 8192]
                sock.sendall(len(chunk).to_bytes(4, "big") + chunk)
            sock.sendall((0).to_bytes(4, "big"))
            response = sock.recv(4096).decode("utf-8", "replace")
    except OSError as exc:
        raise HTTPException(status_code=503, detail="ClamAV scan service is unavailable") from exc
    if "FOUND" in response:
        raise HTTPException(status_code=400, detail=f"{original_name} failed ClamAV scan")
    if "OK" not in response:
        raise HTTPException(status_code=503, detail=f"Unexpected ClamAV response: {response.strip()}")


def _attachment_absolute_path(attachment: DocumentAttachment) -> Path:
    root = Path(get_settings().document_storage_path).resolve()
    path = (root / attachment.storage_path).resolve()
    if not path.is_relative_to(root):
        raise HTTPException(status_code=400, detail="Stored document path is invalid")
    return path


def _safe_original_file_name(file_name: str) -> str:
    name = Path(file_name.replace("\\", "/")).name.strip()
    safe = "".join(char if char.isalnum() or char in {" ", ".", "-", "_"} else "_" for char in name)
    return (safe or "document.bin")[:240]


def _safe_zip_member_name(file_name: str) -> str:
    normalized = file_name.replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise HTTPException(status_code=400, detail=f"Unsafe ZIP member path: {file_name}")
    return _safe_original_file_name(path.name)


def _attachment_extension(file_name: str) -> str:
    return Path(file_name).suffix.lower()


def _guess_content_type(file_name: str) -> str:
    return mimetypes.guess_type(file_name)[0] or "application/octet-stream"


def _document_transmittals(db: Session, tenant_id: int, project_id: int) -> list[DocumentTransmittal]:
    return list(
        db.scalars(
            select(DocumentTransmittal)
            .where(DocumentTransmittal.tenant_id == tenant_id, DocumentTransmittal.project_id == project_id)
            .order_by(DocumentTransmittal.sent_on.desc(), DocumentTransmittal.id.desc())
        ).all()
    )


def _document_transmittal_items(db: Session, tenant_id: int, project_id: int) -> list[DocumentTransmittalItem]:
    return list(
        db.scalars(
            select(DocumentTransmittalItem)
            .where(DocumentTransmittalItem.tenant_id == tenant_id, DocumentTransmittalItem.project_id == project_id)
            .order_by(DocumentTransmittalItem.transmittal_id, DocumentTransmittalItem.id)
        ).all()
    )


def _document_reviews(db: Session, tenant_id: int, project_id: int) -> list[DocumentReview]:
    return list(
        db.scalars(
            select(DocumentReview)
            .where(DocumentReview.tenant_id == tenant_id, DocumentReview.project_id == project_id)
            .order_by(DocumentReview.review_status, DocumentReview.due_date, DocumentReview.id)
        ).all()
    )


def _project_mail(db: Session, tenant_id: int, project_id: int) -> list[ProjectMail]:
    return list(
        db.scalars(
            select(ProjectMail)
            .where(ProjectMail.tenant_id == tenant_id, ProjectMail.project_id == project_id)
            .order_by(ProjectMail.sent_on.desc(), ProjectMail.id.desc())
        ).all()
    )


def _document_control_summary(
    documents: list[Document],
    transmittals: list[DocumentTransmittal],
    reviews: list[DocumentReview],
    mail: list[ProjectMail],
) -> DocumentControlSummary:
    today = utc_now().date()
    current_documents = sum(1 for document in documents if document.status in {"current", "approved", "issued"})
    superseded_documents = sum(1 for document in documents if document.status in {"superseded", "void"})
    outstanding_reviews = sum(
        1 for review in reviews if review.review_status in {"outstanding", "in_review", "revise_and_resubmit"}
    )
    overdue_reviews = sum(
        1
        for review in reviews
        if review.due_date
        and review.due_date < today
        and review.review_status in {"outstanding", "in_review", "revise_and_resubmit"}
    )
    open_mail = sum(1 for item in mail if item.status in {"outstanding", "open", "in_review"})
    overdue_mail = sum(
        1
        for item in mail
        if item.due_date and item.due_date < today and item.status in {"outstanding", "open", "in_review"}
    )
    total_documents = len(documents)
    score = 0.0
    if total_documents:
        numbered = sum(1 for document in documents if document.document_number and document.revision)
        reviewed = sum(1 for document in documents if document.review_status in {"approved", "reviewed", "closed"})
        transmitted = len(transmittals)
        score = min((numbered / total_documents) * 45 + (reviewed / total_documents) * 35 + (transmitted > 0) * 20, 100)
        score = max(score - overdue_reviews * 5 - overdue_mail * 3, 0)
    return DocumentControlSummary(
        total_documents=total_documents,
        current_documents=current_documents,
        superseded_documents=superseded_documents,
        outstanding_reviews=outstanding_reviews,
        overdue_reviews=overdue_reviews,
        transmittals_sent=len([item for item in transmittals if item.status in {"sent", "closed"}]),
        open_mail=open_mail,
        overdue_mail=overdue_mail,
        controlled_document_score=round(score, 1),
    )


def _require_document(db: Session, tenant_id: int, project_id: int, document_id: int) -> Document:
    document = db.scalar(
        select(Document).where(
            Document.tenant_id == tenant_id,
            Document.project_id == project_id,
            Document.id == document_id,
        )
    )
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


def _require_document_attachment(
    db: Session,
    tenant_id: int,
    project_id: int,
    document_id: int,
    attachment_id: int,
) -> DocumentAttachment:
    attachment = db.scalar(
        select(DocumentAttachment).where(
            DocumentAttachment.tenant_id == tenant_id,
            DocumentAttachment.project_id == project_id,
            DocumentAttachment.document_id == document_id,
            DocumentAttachment.id == attachment_id,
        )
    )
    if not attachment:
        raise HTTPException(status_code=404, detail="Document attachment not found")
    return attachment


def _require_document_access(membership: ProjectMembership, document: Document) -> None:
    if not _can_access_document(membership, document):
        raise HTTPException(status_code=403, detail="Current role cannot access this confidential document")


def _can_access_document(membership: ProjectMembership, document: Document | None) -> bool:
    if document is None:
        return False
    confidentiality = (document.confidentiality or "project").strip().lower()
    if confidentiality in {"", "public", "project", "team", "internal"}:
        return True
    privileged_roles = {"Control Manager", "Project Controls", "Document Controller", "Contract Manager"}
    restricted_roles = {"Control Manager", "Document Controller"}
    if confidentiality in {"confidential", "controlled"}:
        return membership.role in privileged_roles or membership.can_configure
    if confidentiality in {"restricted", "private", "executive"}:
        return membership.role in restricted_roles or membership.can_configure
    return membership.role in privileged_roles or membership.can_configure


def _require_document_control_role(membership: ProjectMembership) -> None:
    if membership.role not in {
        "Control Manager",
        "Project Controls",
        "Document Controller",
        "Contract Manager",
        "Planner",
    }:
        raise HTTPException(status_code=403, detail="Current role cannot manage document control")


def _ensure_document_revision_available(
    db: Session,
    tenant_id: int,
    project_id: int,
    document_number: str,
    revision: str,
    exclude_id: int | None = None,
) -> None:
    query = select(Document).where(
        Document.tenant_id == tenant_id,
        Document.project_id == project_id,
        Document.document_number == document_number,
        Document.revision == revision,
    )
    if exclude_id is not None:
        query = query.where(Document.id != exclude_id)
    if db.scalar(query):
        raise HTTPException(status_code=409, detail="Document number and revision already exist for this project")


def _next_document_number(db: Session, tenant_id: int, project: Project) -> str:
    count = _count(db, Document, tenant_id, project.id) + 1
    return f"{project.code}-DOC-{count:04d}"


def _next_transmittal_no(db: Session, tenant_id: int, project: Project) -> str:
    count = _count(db, DocumentTransmittal, tenant_id, project.id) + 1
    return f"{project.code}-TR-{count:04d}"


def _next_mail_no(db: Session, tenant_id: int, project: Project) -> str:
    count = _count(db, ProjectMail, tenant_id, project.id) + 1
    return f"{project.code}-MAIL-{count:04d}"
