from __future__ import annotations

import argparse
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Tuple
from xml.etree.ElementTree import iterparse

from openpyxl import Workbook


NS_MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def _col_letters_to_index(col: str) -> int:
    """A -> 1, B -> 2, Z -> 26, AA -> 27 ..."""
    n = 0
    for ch in col:
        if not ("A" <= ch <= "Z"):
            continue
        n = n * 26 + (ord(ch) - ord("A") + 1)
    return n


_CELL_REF_RE = re.compile(r"^([A-Z]+)(\d+)$")


def _cell_ref_to_row_col(ref: str) -> Tuple[int, int]:
    m = _CELL_REF_RE.match((ref or "").strip().upper())
    if not m:
        return 0, 0
    col = _col_letters_to_index(m.group(1))
    row = int(m.group(2))
    return row, col


def _load_shared_strings(z: zipfile.ZipFile) -> List[str]:
    """
    Parse xl/sharedStrings.xml into a list.
    We need this for cells with t="s" (shared string).
    """
    path = "xl/sharedStrings.xml"
    if path not in z.namelist():
        return []
    out: List[str] = []
    # Stream parse to avoid loading huge XML at once
    with z.open(path) as f:
        buf: List[str] = []
        in_si = False
        for event, elem in iterparse(f, events=("start", "end")):
            tag = elem.tag
            if event == "start" and tag == f"{NS_MAIN}si":
                in_si = True
                buf = []
            elif event == "end" and tag == f"{NS_MAIN}t" and in_si:
                if elem.text:
                    buf.append(elem.text)
            elif event == "end" and tag == f"{NS_MAIN}si":
                in_si = False
                out.append("".join(buf))
                buf = []
                elem.clear()
            # clear aggressively
            if event == "end":
                elem.clear()
    return out


@dataclass(frozen=True)
class SheetRow:
    row_index: int
    values_by_col: Dict[int, str]


def _iter_sheet_rows(z: zipfile.ZipFile, *, sheet_xml_path: str, shared_strings: List[str]) -> Iterator[SheetRow]:
    """
    Stream parse worksheet XML to yield rows.
    This deliberately ignores <dimension ref="A1"> bugs.
    """
    with z.open(sheet_xml_path) as f:
        current_row_index = 0
        current: Dict[int, str] = {}
        row_open = False
        cell_ref: Optional[str] = None
        cell_type: Optional[str] = None
        cell_value: Optional[str] = None
        cell_inline_parts: List[str] = []
        in_inline_is = False

        for event, elem in iterparse(f, events=("start", "end")):
            tag = elem.tag
            if event == "start":
                if tag == f"{NS_MAIN}row":
                    row_open = True
                    current = {}
                    current_row_index = int(elem.attrib.get("r") or "0")
                elif row_open and tag == f"{NS_MAIN}c":
                    cell_ref = elem.attrib.get("r")
                    cell_type = elem.attrib.get("t")
                    cell_value = None
                    cell_inline_parts = []
                    in_inline_is = False
                elif row_open and cell_type == "inlineStr" and tag == f"{NS_MAIN}is":
                    in_inline_is = True
            else:  # end
                if row_open and tag == f"{NS_MAIN}v":
                    cell_value = elem.text
                elif row_open and cell_type == "inlineStr" and in_inline_is and tag == f"{NS_MAIN}t":
                    if elem.text:
                        cell_inline_parts.append(elem.text)
                elif row_open and cell_type == "inlineStr" and tag == f"{NS_MAIN}is":
                    in_inline_is = False
                elif row_open and tag == f"{NS_MAIN}c":
                    # finalize cell
                    if cell_ref:
                        _r, col = _cell_ref_to_row_col(cell_ref)
                        v = cell_value
                        if cell_type == "inlineStr":
                            s = "".join(cell_inline_parts).strip()
                            if s != "":
                                current[col] = s
                        elif v is None:
                            pass
                        elif cell_type == "s":
                            try:
                                s = shared_strings[int(v)]
                            except Exception:
                                s = v
                            current[col] = s
                        else:
                            # Keep as string; downstream importer will parse datetime/decimal as needed.
                            current[col] = v
                    cell_ref = None
                    cell_type = None
                    cell_value = None
                    cell_inline_parts = []
                    in_inline_is = False
                elif tag == f"{NS_MAIN}row":
                    row_open = False
                    if current_row_index > 0 and current:
                        yield SheetRow(row_index=current_row_index, values_by_col=current)
                    current = {}
                    current_row_index = 0

                elem.clear()


def _write_chunk_xlsx(*, out_path: Path, headers: List[str], rows: Iterable[List[Optional[str]]]) -> None:
    wb = Workbook(write_only=True)
    ws = wb.create_sheet("sku_master")
    ws.append(headers)
    for r in rows:
        ws.append(list(r))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out_path)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="归一化“天猫店铺平台商品列表”类xlsx（修复dimension=A1导致openpyxl无法读取的问题），并分片输出可导入的xlsx"
    )
    parser.add_argument(
        "--in",
        dest="in_path",
        required=True,
        help="输入xlsx路径（例如：DOC/基础表单/天猫绮妙店铺平台商品列表(22026.1.10).xlsx）",
    )
    parser.add_argument(
        "--out-dir",
        default="/home/admin/ai-costing-system/DOC/agents/fixtures/tmall_platform_list_chunks",
        help="输出目录（会生成 chunk_0001.xlsx ...）",
    )
    parser.add_argument("--chunk-size", type=int, default=20000, help="每个分片xlsx行数（不含表头）")
    parser.add_argument("--max-rows", type=int, default=0, help="最多处理多少行（0表示不限制，用于小范围验证）")
    args = parser.parse_args()

    in_path = Path(args.in_path)
    out_dir = Path(args.out_dir)
    chunk_size = max(int(args.chunk_size), 1000)
    max_rows = max(int(args.max_rows), 0)

    with zipfile.ZipFile(in_path) as z:
        # We only saw sheet1.xml in this type of file, but keep it explicit.
        sheet_path = "xl/worksheets/sheet1.xml"
        if sheet_path not in z.namelist():
            raise SystemExit(f"missing worksheet: {sheet_path}")

        print("[info] parsing sharedStrings.xml ...")
        shared_strings = _load_shared_strings(z)
        print(f"[info] shared strings: {len(shared_strings)}")

        # Extract header row (row_index=1)
        print("[info] scanning header row ...")
        row_iter = _iter_sheet_rows(z, sheet_xml_path=sheet_path, shared_strings=shared_strings)
        header_row = None
        for r in row_iter:
            if r.row_index == 1:
                header_row = r
                break
        if not header_row:
            raise SystemExit("failed to find header row (row 1)")

        # Build header list by max col in header row.
        max_col = max(header_row.values_by_col.keys())
        header_cells = [header_row.values_by_col.get(i, "").strip() for i in range(1, max_col + 1)]
        # Trim trailing empties
        while header_cells and not header_cells[-1]:
            header_cells.pop()
        headers = header_cells
        print(f"[info] header columns: {len(headers)}")
        print("[info] first 20 headers:", [h for h in headers[:20] if h])

        # Decide output schema: keep a compact subset aligned with sku-master/import
        # (Plus a few ERP/system columns that we want to preserve.)
        wanted = [
            "规格图片（网店）",
            "销售渠道",
            "商品名称（网店）",
            "商品编码（网店）",
            "商品图片（网店）",
            "商品规格（网店）",
            "货品规格（系统）",
            "规格编码（网店）",
            "平台商品Id（网店）",
            "平台规格Id（网店）",
            "匹配状态",
            "货品名称（系统）",
            "货品编号（系统）",
            "货品条码（系统）",
            "最后更新时间",
            "匹配方式",
            # optional in future
            "生产工艺",
        ]

        header_to_col: Dict[str, int] = {}
        for idx, h in enumerate(headers, start=1):
            name = (h or "").strip()
            if not name:
                continue
            header_to_col[name] = idx

        missing = [h for h in ("货品条码（系统）", "平台规格Id（网店）") if h not in header_to_col]
        if missing:
            print("[warn] missing required columns in this file header:", missing)

        out_headers = wanted
        out_dir.mkdir(parents=True, exist_ok=True)

        # Continue iterating from current position: header row already consumed.
        processed = 0
        chunk_no = 1
        buf_rows: List[List[Optional[str]]] = []

        def flush() -> None:
            nonlocal chunk_no, buf_rows
            if not buf_rows:
                return
            out_path = out_dir / f"chunk_{chunk_no:04d}.xlsx"
            _write_chunk_xlsx(out_path=out_path, headers=out_headers, rows=buf_rows)
            print(f"[ok] wrote {out_path} rows={len(buf_rows)}")
            chunk_no += 1
            buf_rows = []

        for r in row_iter:
            if r.row_index <= 1:
                continue
            processed += 1
            if max_rows and processed > max_rows:
                break

            row_out: List[Optional[str]] = []
            for h in out_headers:
                col = header_to_col.get(h)
                v = r.values_by_col.get(col) if col else None
                if v is None:
                    row_out.append(None)
                else:
                    s = str(v).strip()
                    row_out.append(s if s != "" else "")

            # Skip fully empty rows
            if not any(x not in (None, "") for x in row_out):
                continue

            buf_rows.append(row_out)
            if len(buf_rows) >= chunk_size:
                flush()

            if processed % 10000 == 0:
                print(f"[info] processed rows: {processed}")

        flush()
        print(f"[done] processed rows: {processed}, chunks: {chunk_no - 1}, out_dir: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


