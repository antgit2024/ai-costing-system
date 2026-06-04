from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ...config import settings


@dataclass
class LocalImageRef:
    path: str
    content_type: Optional[str] = None


def _media_root() -> Path:
    root = Path(settings.planner_media_dir)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _safe_ext(content_type: Optional[str], source_url: str) -> str:
    ct = (content_type or "").lower().strip()
    if "png" in ct:
        return "png"
    if "jpeg" in ct or "jpg" in ct:
        return "jpg"
    if "webp" in ct:
        return "webp"
    if "gif" in ct:
        return "gif"
    # fallback: try url suffix
    for ext in ("png", "jpg", "jpeg", "webp", "gif"):
        if source_url.lower().endswith(f".{ext}"):
            return "jpg" if ext == "jpeg" else ext
    return "bin"


def resolve_local_path(rel_path: str) -> Path:
    rel = rel_path.lstrip("/").replace("..", "")
    return _media_root() / rel


def read_local_bytes(ref: LocalImageRef) -> bytes:
    path = resolve_local_path(ref.path)
    return path.read_bytes()


def get_local_image_ref(metadata: dict, image_index: int) -> Optional[LocalImageRef]:
    local_images = metadata.get("local_images") or []
    if not isinstance(local_images, list):
        return None
    if image_index < 0 or image_index >= len(local_images):
        return None
    item = local_images[image_index]
    if isinstance(item, dict) and item.get("path"):
        return LocalImageRef(path=str(item["path"]), content_type=item.get("content_type"))
    if isinstance(item, str) and item:
        return LocalImageRef(path=item)
    return None


def set_local_image_ref(metadata: dict, image_index: int, ref: LocalImageRef) -> None:
    local_images = metadata.get("local_images")
    if not isinstance(local_images, list):
        local_images = []
    while len(local_images) <= image_index:
        local_images.append(None)
    local_images[image_index] = {"path": ref.path, "content_type": ref.content_type}
    metadata["local_images"] = local_images


def persist_bytes(
    *,
    material_id: str,
    image_index: int,
    source_url: str,
    content: bytes,
    content_type: Optional[str],
) -> LocalImageRef:
    digest = hashlib.sha256(content).hexdigest()[:16]
    ext = _safe_ext(content_type, source_url)
    rel_dir = Path("material_images") / material_id
    rel_name = f"img_{image_index}_{digest}.{ext}"
    rel_path = str(rel_dir / rel_name)
    abs_path = resolve_local_path(rel_path)
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    # atomic-ish write
    tmp_path = abs_path.with_suffix(abs_path.suffix + ".tmp")
    tmp_path.write_bytes(content)
    os.replace(tmp_path, abs_path)
    return LocalImageRef(path=rel_path, content_type=content_type)


