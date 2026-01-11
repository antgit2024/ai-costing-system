from __future__ import annotations

import hashlib
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ...config import settings


@dataclass
class LocalImageRef:
    path: str
    content_type: Optional[str] = None
    source_url: Optional[str] = None


def _media_root() -> Path:
    root = Path(settings.planner_media_dir)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _sku_root() -> Path:
    p = _media_root() / "sku_master_images"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _cleanup_stamp_path() -> Path:
    return _sku_root() / "_last_cleanup_ts.txt"


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
    for ext in ("png", "jpg", "jpeg", "webp", "gif"):
        if source_url.lower().endswith(f".{ext}"):
            return "jpg" if ext == "jpeg" else ext
    return "bin"


def resolve_local_path(rel_path: str) -> Path:
    rel = rel_path.lstrip("/").replace("..", "")
    return _media_root() / rel


def read_local_bytes(ref: LocalImageRef) -> bytes:
    p = resolve_local_path(ref.path)
    # touch for LRU-ish mtime
    try:
        now = time.time()
        os.utime(p, (now, now))
    except Exception:
        pass
    return p.read_bytes()


def get_local_image_ref(metadata: dict, kind: str) -> Optional[LocalImageRef]:
    d = (metadata or {}).get("sku_local_images") or {}
    if not isinstance(d, dict):
        return None
    item = d.get(kind)
    if not isinstance(item, dict):
        return None
    path = item.get("path")
    if not path:
        return None
    return LocalImageRef(path=str(path), content_type=item.get("content_type"), source_url=item.get("source_url"))


def set_local_image_ref(metadata: dict, kind: str, ref: LocalImageRef) -> None:
    d = (metadata or {}).get("sku_local_images")
    if not isinstance(d, dict):
        d = {}
    d[kind] = {"path": ref.path, "content_type": ref.content_type, "source_url": ref.source_url}
    metadata["sku_local_images"] = d


def persist_bytes(
    *,
    sku_master_id: str,
    kind: str,
    source_url: str,
    content: bytes,
    content_type: Optional[str],
) -> LocalImageRef:
    digest = hashlib.sha256(content).hexdigest()[:16]
    ext = _safe_ext(content_type, source_url)
    rel_dir = Path("sku_master_images") / sku_master_id
    rel_name = f"{kind}_{digest}.{ext}"
    rel_path = str(rel_dir / rel_name)
    abs_path = resolve_local_path(rel_path)
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = abs_path.with_suffix(abs_path.suffix + ".tmp")
    tmp_path.write_bytes(content)
    os.replace(tmp_path, abs_path)
    return LocalImageRef(path=rel_path, content_type=content_type, source_url=source_url)


def _iter_cache_files() -> list[Path]:
    root = _sku_root()
    out: list[Path] = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if p.name.startswith("_"):
            continue
        out.append(p)
    return out


def maybe_cleanup() -> None:
    """
    Best-effort cleanup:
    - delete files older than TTL days (by mtime)
    - enforce max_files (delete oldest by mtime)
    """
    try:
        interval = max(int(settings.planner_sku_image_cache_cleanup_interval_seconds or 300), 10)
        stamp_path = _cleanup_stamp_path()
        now = int(time.time())
        last = 0
        try:
            last = int(stamp_path.read_text().strip() or "0")
        except Exception:
            last = 0
        if last and now - last < interval:
            return

        ttl_days = max(int(settings.planner_sku_image_cache_ttl_days or 365), 1)
        ttl_cutoff = now - ttl_days * 86400
        max_files = max(int(settings.planner_sku_image_cache_max_files or 100_000), 1)

        files = _iter_cache_files()
        # remove expired first
        for p in files:
            try:
                if int(p.stat().st_mtime) < ttl_cutoff:
                    p.unlink(missing_ok=True)
            except Exception:
                continue

        files = _iter_cache_files()
        if len(files) > max_files:
            files.sort(key=lambda x: x.stat().st_mtime)
            for p in files[: max(0, len(files) - max_files)]:
                try:
                    p.unlink(missing_ok=True)
                except Exception:
                    continue

        stamp_path.write_text(str(now))
    except Exception:
        # fail-open: never break image serving
        return


