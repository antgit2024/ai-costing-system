#!/usr/bin/env python3
"""Markdown → PDF（中文，Noto Sans SC）。

用法:
  backend/venv/bin/python tools/export_md_pdf.py <输入.md> <输出.pdf>

环境变量 NOTO_FONT: .otf/.ttf 路径，默认 ~/.local/share/fonts/NotoSansSC-Regular.otf
"""
from __future__ import annotations

import os
import re
import sys
from html import unescape
from pathlib import Path

from fpdf import FPDF

FONT_DEFAULT = Path.home() / ".local/share/fonts/NotoSansSC-Regular.otf"


def strip_yaml_frontmatter(text: str) -> str:
    t = text.lstrip()
    if not t.startswith("---"):
        return text
    end = t.find("\n---\n", 3)
    if end == -1:
        return text
    return t[end + 5 :]


def split_md_and_code(src: str) -> list[tuple[str, str]]:
    """交替 md / code。"""
    parts = src.split("```")
    out: list[tuple[str, str]] = []
    for i, raw in enumerate(parts):
        if i % 2 == 0:
            if raw.strip():
                out.append(("md", raw))
            continue
        body = raw.lstrip("\n")
        lines = body.split("\n")
        if lines and re.match(r"^[A-Za-z0-9_+-]+$", lines[0].strip()):
            body = "\n".join(lines[1:])
        out.append(("code", body.strip("\n")))
    return out


def strip_inline(s: str) -> str:
    s = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", s)
    s = re.sub(r"`([^`]+)`", r"\1", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"\1", s)
    s = unescape(s)
    return s


def parse_md_piece(piece: str) -> list[tuple[str, str]]:
    lines = piece.splitlines()
    res: list[tuple[str, str]] = []
    buf: list[str] = []

    def flush_para() -> None:
        nonlocal buf
        if buf:
            t = "\n".join(buf).strip()
            if t:
                res.append(("p", strip_inline(t)))
            buf = []

    i = 0
    while i < len(lines):
        s = lines[i].strip()
        if not s:
            flush_para()
            i += 1
            continue
        if re.match(r"^#{1,6}\s+", lines[i]):
            flush_para()
            m = re.match(r"^(#{1,6})\s+(.*)$", lines[i].strip())
            if m:
                res.append(("h", f"{len(m.group(1))}\t{m.group(2).strip()}"))
            i += 1
            continue
        if s.startswith("|"):
            flush_para()
            rows: list[str] = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                row = lines[i].strip()
                if row.replace("|", "").replace("-", "").replace(":", "").strip() == "":
                    i += 1
                    continue
                cells = [c.strip() for c in row.strip("|").split("|")]
                rows.append(" │ ".join(strip_inline(c) for c in cells))
                i += 1
            res.append(("table", "\n".join(rows)))
            continue
        mli = re.match(r"^\s*[-+*]\s+(.*)$", lines[i])
        if mli:
            flush_para()
            res.append(("li", strip_inline(mli.group(1))))
            i += 1
            continue
        buf.append(lines[i])
        i += 1
    flush_para()
    return res


class DocPdf(FPDF):
    def __init__(self, font_key: str) -> None:
        super().__init__(format="A4")
        self._fk = font_key

    def footer(self) -> None:
        self.set_y(-13)
        self.set_font(self._fk, "", 8)
        self.set_text_color(130, 130, 130)
        self.cell(0, 5, str(self.page_no()), align="R")


def render(md_file: Path, pdf_file: Path, font_otf: Path) -> None:
    full = strip_yaml_frontmatter(md_file.read_text(encoding="utf-8"))
    pdf = DocPdf(font_key="Ns")
    pdf.add_font("Ns", "", str(font_otf))
    pdf.add_font("Ns", "B", str(font_otf))
    pdf.set_margins(18, 18, 18)
    pdf.set_auto_page_break(auto=True, margin=16)
    pdf.add_page()

    lh, lh_small = 6.4, 5.7
    w_body = pdf.w - pdf.l_margin - pdf.r_margin

    for kind, chunk in split_md_and_code(full):
        if kind == "code":
            pdf.ln(1)
            pdf.set_x(pdf.l_margin)
            pdf.set_font("Ns", "", 9)
            pdf.set_text_color(42, 42, 55)
            pdf.set_fill_color(248, 248, 250)
            for ln in chunk.split("\n"):
                txt = ln.expandtabs(4)
                pdf.set_x(pdf.l_margin)
                if not txt.strip():
                    pdf.ln(lh_small)
                    continue
                pdf.multi_cell(w_body, lh_small, txt, fill=True)
            pdf.set_fill_color(255, 255, 255)
            pdf.set_text_color(28, 28, 28)
            pdf.ln(2)
            continue
        for tag, payload in parse_md_piece(chunk):
            if tag == "h":
                lvl, ttl = payload.split("\t", 1)
                n = int(lvl)
                fs = max(20 - n * 2, 11)
                pdf.set_font("Ns", "B", fs)
                pdf.set_text_color(18, 18, 18)
                pdf.ln(2 if n == 1 else 1 if n <= 3 else 0.4)
                pdf.set_x(pdf.l_margin)
                pdf.multi_cell(w_body, fs * 0.56, ttl)
                pdf.set_font("Ns", "", 11)
                pdf.set_text_color(28, 28, 28)
                pdf.ln(0.6)
            elif tag == "table":
                pdf.ln(1)
                pdf.set_font("Ns", "", 9)
                for row in payload.split("\n"):
                    pdf.set_x(pdf.l_margin)
                    pdf.multi_cell(w_body, lh_small - 0.3, row)
                pdf.set_font("Ns", "", 11)
                pdf.ln(1)
            elif tag == "li":
                pdf.set_x(pdf.l_margin)
                pdf.multi_cell(w_body, lh, "•  " + payload)
                pdf.ln(0.15)
            else:
                pdf.set_font("Ns", "", 11)
                pdf.set_x(pdf.l_margin)
                pdf.multi_cell(w_body, lh, payload)
                pdf.ln(1.0)

    pdf_file.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(pdf_file))


def main() -> None:
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    src = Path(sys.argv[1])
    dst = Path(sys.argv[2])
    ff = Path(os.environ.get("NOTO_FONT", str(FONT_DEFAULT))).expanduser().resolve()
    if not ff.is_file():
        sys.stderr.write(f"字体不存在: {ff}\n设置 NOTO_FONT=/path/to/NotoSansSC-Regular.otf\n")
        sys.exit(2)
    if not src.is_file():
        sys.stderr.write(f"文件不存在: {src}\n")
        sys.exit(3)
    render(src, dst, ff)
    print(dst.resolve())


if __name__ == "__main__":
    main()
