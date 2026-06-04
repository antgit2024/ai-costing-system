from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional


def _parse_dt(s: str) -> Optional[datetime]:
    raw = (s or "").strip()
    if not raw:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(raw)
    except Exception:  # noqa: BLE001
        return None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="按边界清理 SKU 主档导入数据（建议仅用于测试/误导入回滚）。默认 dry-run。"
    )
    parser.add_argument("--requested-by", required=True, help="匹配 metadata_json.requested_by")
    parser.add_argument(
        "--source",
        default="erp_import",
        help="匹配 metadata_json.source（默认 erp_import；不会动 manual / shipment_autobackfill 等来源）",
    )
    parser.add_argument("--created-after", default="", help="仅清理 created_at >=（YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS）")
    parser.add_argument("--created-before", default="", help="仅清理 created_at <=（同上）")
    parser.add_argument("--channel", default="", help="可选：仅清理指定渠道/店铺")
    parser.add_argument("--dry-run", action="store_true", help="只打印将影响的行数/样例，不实际修改（默认推荐先开）")
    parser.add_argument("--hard-delete", action="store_true", help="危险：物理删除（默认是软删除 is_archived=true）")
    args = parser.parse_args()

    # Make backend package importable: repo_root/tools/integration -> repo_root/backend/src
    repo_root = Path(__file__).resolve().parents[2]
    backend_dir = repo_root / "backend"
    sys.path.insert(0, str(backend_dir))

    try:
        from sqlalchemy import and_  # type: ignore
        from src.database import SessionLocal  # type: ignore
        from src.planner import models  # type: ignore
    except Exception as exc:  # noqa: BLE001
        print(f"[fatal] failed to import backend modules. run with backend venv? err={exc}")
        return 2

    created_after = _parse_dt(args.created_after)
    created_before = _parse_dt(args.created_before)

    db = SessionLocal()
    try:
        q = db.query(models.SkuMaster).filter(models.SkuMaster.is_archived.is_(False))
        # only affect a single import source boundary
        q = q.filter(models.SkuMaster.metadata_json["source"].as_string() == str(args.source))
        q = q.filter(models.SkuMaster.metadata_json["requested_by"].as_string() == str(args.requested_by))
        if args.channel:
            q = q.filter(models.SkuMaster.channel == args.channel)
        if created_after:
            q = q.filter(models.SkuMaster.created_at >= created_after)
        if created_before:
            q = q.filter(models.SkuMaster.created_at <= created_before)

        total = q.count()
        print(
            f"[plan] matched sku_master rows={total} source={args.source} requested_by={args.requested_by}"
            + (f" channel={args.channel}" if args.channel else "")
            + (f" created_after={created_after}" if created_after else "")
            + (f" created_before={created_before}" if created_before else "")
        )
        sample = q.order_by(models.SkuMaster.updated_at.desc()).limit(5).all()
        for r in sample:
            print(" -", r.erp_sku_barcode, r.channel, r.platform_sku_id, r.created_at, r.updated_at)

        if total == 0:
            return 0

        if args.dry_run:
            print("[dry-run] no rows changed")
            return 0

        if args.hard_delete:
            # physical delete (dangerous)
            affected = q.delete(synchronize_session=False)
        else:
            affected = q.update({models.SkuMaster.is_archived: True}, synchronize_session=False)

        db.commit()
        print(f"[ok] affected rows={affected} (hard_delete={bool(args.hard_delete)})")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())


