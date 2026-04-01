"""Message attachment upload endpoint."""

import os
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.api.deps import get_current_org_user, OrgUserContext
from src.models.message_attachment import MessageAttachment

router = APIRouter(prefix="/attachments", tags=["attachments"])

BLOCKED_TYPES = {
    "application/x-msdownload", "application/x-executable", "application/x-msdos-program",
    "application/x-sh", "application/x-bat", "application/x-csh",
    "image/svg+xml", "text/html", "application/xhtml+xml",
}
BLOCKED_EXTENSIONS = {
    ".exe", ".bat", ".cmd", ".sh", ".com", ".msi", ".scr", ".ps1", ".vbs", ".js", ".wsf",
    ".svg", ".html", ".htm", ".xhtml",
}
MAX_TOTAL_STORAGE = 2 * 1024 * 1024 * 1024  # 2GB total attachments
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
MAX_ATTACHMENTS_PER_MESSAGE = 5
UPLOAD_ROOT = Path(os.environ.get("UPLOAD_DIR", "./uploads"))


class AttachmentResponse(BaseModel):
    id: str
    filename: str
    url: str
    mime_type: str
    file_size: int


@router.post("/upload", response_model=AttachmentResponse)
async def upload_attachment(
    file: UploadFile = File(...),
    source_type: str = Form(...),
    ctx: OrgUserContext = Depends(get_current_org_user),
    db: AsyncSession = Depends(get_db),
):
    if source_type not in ("internal_message", "agent_message"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid source_type")

    ext = ("." + (file.filename or "").rsplit(".", 1)[-1].lower()) if file.filename and "." in file.filename else ""
    if file.content_type in BLOCKED_TYPES or ext in BLOCKED_EXTENSIONS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Executable files are not allowed")

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "File too large (max 10MB)")

    # Check total storage
    att_dir = UPLOAD_ROOT / "attachments"
    if att_dir.exists():
        total = sum(f.stat().st_size for f in att_dir.rglob("*") if f.is_file())
        if total + len(content) > MAX_TOTAL_STORAGE:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Storage limit reached")

    ext_clean = ext.lstrip(".") if ext else "bin"
    stored_name = f"{uuid.uuid4()}.{ext_clean}"
    dest_dir = UPLOAD_ROOT / "attachments" / ctx.organization_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / stored_name

    with open(dest_path, "wb") as f:
        f.write(content)

    attachment = MessageAttachment(
        organization_id=ctx.organization_id,
        source_type=source_type,
        uploaded_by=ctx.user_id,
        filename=file.filename or "file",
        stored_filename=stored_name,
        mime_type=file.content_type,
        file_size=len(content),
    )
    db.add(attachment)
    await db.commit()

    return AttachmentResponse(
        id=attachment.id,
        filename=attachment.filename,
        url=f"/uploads/attachments/{ctx.organization_id}/{stored_name}",
        mime_type=attachment.mime_type,
        file_size=attachment.file_size,
    )
