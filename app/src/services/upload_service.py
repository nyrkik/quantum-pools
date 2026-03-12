"""File upload service — local disk storage with MIME validation."""

import uuid
import logging
from pathlib import Path
from fastapi import UploadFile, HTTPException, status

from src.core.config import settings

logger = logging.getLogger(__name__)

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}


async def save_file(file: UploadFile, subdir: str) -> str:
    """Save an uploaded file to {upload_dir}/{subdir}/{uuid}_{name}. Returns relative path."""
    content_type = file.content_type or ""
    if content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type: {content_type}. Allowed: JPEG, PNG, WebP, HEIC",
        )

    content = await file.read()
    size_mb = len(content) / (1024 * 1024)
    if size_mb > settings.max_upload_size_mb:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File too large: {size_mb:.1f}MB (max {settings.max_upload_size_mb}MB)",
        )

    upload_dir = Path(settings.upload_dir) / subdir
    upload_dir.mkdir(parents=True, exist_ok=True)

    safe_name = "".join(c if c.isalnum() or c in ".-_" else "_" for c in (file.filename or "photo.jpg"))
    filename = f"{uuid.uuid4().hex[:12]}_{safe_name}"
    filepath = upload_dir / filename

    filepath.write_bytes(content)
    logger.info(f"Saved upload: {filepath} ({size_mb:.1f}MB)")

    return f"{subdir}/{filename}"
