from __future__ import annotations

import argparse
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# Reuse parser utilities from normalizer
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from tools.integration.normalize_tmall_platform_list_xlsx import (  # noqa: E402
    _iter_sheet_rows,
    _load_shared_strings,
)


@dataclass
class Stats:
    total_rows: int = 0  # data rows (exclude header)
    empty_rows: int = 0
    missing_barcode: int = 0
    unique_barcodes: int = 0
    unique_platform_sku_ids: int = 0
    duplicate_barcode_rows: int = 0  # rows where barcode repeats (not unique)
    barcode_conflict_platform_sku: int = 0  # barcode maps to multiple platform_sku_id
    barcode_conflict_channel: int = 0  # barcode maps to multiple channel values


def main() -> int:
    parser = argparse.ArgumentParser(description="统计平台商品列表xlsx的唯一条码/重复/冲突，用于解释sku_master总数差异")
    parser.add_argument("--in", dest="in_path", required=True, help="输入xlsx路径")
    parser.add_argument("--limit", type=int, default=0, help="最多处理多少行（0=全量）")
    args = parser.parse_args()

    in_path = Path(args.in_path)
    if not in_path.exists():
        raise SystemExit(f"file not found: {in_path}")

    with zipfile.ZipFile(in_path) as z:
        ss = _load_shared_strings(z)
        sheet = "xl/worksheets/sheet1.xml"
        it = _iter_sheet_rows(z, sheet_xml_path=sheet, shared_strings=ss)

        header: Optional[Dict[str, int]] = None  # name->colIndex(1-based)
        stats = Stats()

        seen_barcode: Dict[str, Tuple[str, str]] = {}  # barcode -> (platform_sku_id, channel)
        barcodes: set[str] = set()
        platform_skus: set[str] = set()

        def get_cell(row_map: Dict[int, str], col_idx: Optional[int]) -> str:
            if not col_idx:
                return ""
            return (row_map.get(col_idx) or "").strip()

        for r in it:
            if r.row_index == 1:
                # build header mapping
                header = {}
                for col_idx, val in r.values_by_col.items():
                    name = (val or "").strip()
                    if name:
                        header[name] = col_idx
                continue

            if not header:
                continue

            stats.total_rows += 1
            if args.limit and stats.total_rows > args.limit:
                break

            barcode = get_cell(r.values_by_col, header.get("货品条码（系统）"))
            platform_sku_id = get_cell(r.values_by_col, header.get("平台规格Id（网店）"))
            channel = get_cell(r.values_by_col, header.get("销售渠道"))

            # detect empty row (all cells empty)
            if not any((v or "").strip() for v in r.values_by_col.values()):
                stats.empty_rows += 1
                continue

            if not barcode:
                stats.missing_barcode += 1
                continue

            if platform_sku_id:
                platform_skus.add(platform_sku_id)

            if barcode in barcodes:
                stats.duplicate_barcode_rows += 1
            else:
                barcodes.add(barcode)

            prev = seen_barcode.get(barcode)
            if prev:
                prev_platform_sku, prev_channel = prev
                if platform_sku_id and prev_platform_sku and platform_sku_id != prev_platform_sku:
                    stats.barcode_conflict_platform_sku += 1
                if channel and prev_channel and channel != prev_channel:
                    stats.barcode_conflict_channel += 1
                # keep first seen as baseline
            else:
                seen_barcode[barcode] = (platform_sku_id, channel)

            if stats.total_rows % 50000 == 0:
                print(f"[info] processed rows={stats.total_rows}")

        stats.unique_barcodes = len(barcodes)
        stats.unique_platform_sku_ids = len(platform_skus)

        print("=== profile result ===")
        print("file:", str(in_path))
        print("data_rows_total:", stats.total_rows)
        print("empty_rows:", stats.empty_rows)
        print("missing_barcode_rows:", stats.missing_barcode)
        print("unique_barcodes:", stats.unique_barcodes)
        print("duplicate_barcode_rows:", stats.duplicate_barcode_rows)
        print("unique_platform_sku_ids:", stats.unique_platform_sku_ids)
        print("barcode_conflict_platform_sku:", stats.barcode_conflict_platform_sku)
        print("barcode_conflict_channel:", stats.barcode_conflict_channel)

        # A rough expected upper bound for sku_master new inserts from this file:
        print("expected_sku_master_after_upsert≈unique_barcodes:", stats.unique_barcodes)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())


