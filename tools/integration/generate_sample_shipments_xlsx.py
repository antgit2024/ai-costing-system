from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from openpyxl import Workbook


@dataclass(frozen=True)
class SampleRow:
    shipment_no: str | None
    completed_at: Any  # str | datetime | float | None (openpyxl will handle)
    channel: str | None
    sku_code: str | None
    spec_text: str | None
    qty: int | float | None
    revenue_amount: int | float | None
    customer_note: str | None = None


DEFAULT_HEADERS = [
    "发货单号",
    "完成时间",
    "销售渠道",
    "货品条码",
    "交易规格",
    "数量",
    "金额",
    "客服备注",
]


def build_rows(*, base_date: str) -> list[SampleRow]:
    # base_date 用于让样例稳定可读（不依赖当天）
    dt1 = f"{base_date} 10:00:00"
    dt2 = f"{base_date} 10:05:00"
    dt3 = f"{base_date} 10:10:00"

    return [
        # 1) 期望能出 BOM 快照：前提是 SKU-001 已在本系统绑定到“已发布标准版本”
        SampleRow(
            shipment_no="S-MVP-0001",
            completed_at=dt1,
            channel="单店验证-示例店",
            sku_code="SKU-001",
            spec_text="约50*140;024画框",
            qty=2,
            revenue_amount=199,
            customer_note="用于验证：已绑定SKU → 产出BOM快照",
        ),
        # 2) 未绑定：应进 SKU_NOT_BOUND
        SampleRow(
            shipment_no="S-MVP-0002",
            completed_at=dt1,
            channel="单店验证-示例店",
            sku_code="SKU-NOT-BOUND-001",
            spec_text="45X45;黑色包边",
            qty=1,
            revenue_amount=39,
            customer_note="用于验证：SKU_NOT_BOUND 分流",
        ),
        # 3) 缺 SKU：应进 MISSING_SKU
        SampleRow(
            shipment_no="S-MVP-0003",
            completed_at=dt1,
            channel="单店验证-示例店",
            sku_code=None,
            spec_text="45X45;黑色包边",
            qty=1,
            revenue_amount=39,
            customer_note="用于验证：MISSING_SKU 分流",
        ),
        # 4) 缺规格：应进 SPEC_EMPTY
        SampleRow(
            shipment_no="S-MVP-0004",
            completed_at=dt2,
            channel="单店验证-示例店",
            sku_code="SKU-001",
            spec_text=None,
            qty=1,
            revenue_amount=39,
            customer_note="用于验证：SPEC_EMPTY 分流",
        ),
        # 5) 规格在备注里：交易规格为空，但猜测逻辑可命中
        SampleRow(
            shipment_no="S-MVP-0005",
            completed_at=dt2,
            channel="单店验证-示例店",
            sku_code="SKU-NOT-BOUND-002",
            spec_text="",
            qty=1,
            revenue_amount=49,
            customer_note="颜色分类:Q25102709D山水绮梦-黑色包边 45X45;尺寸:PP棉枕芯+枕套",
        ),
        # 6) 金额缺失（可选字段）
        SampleRow(
            shipment_no="S-MVP-0006",
            completed_at=dt2,
            channel="单店验证-示例店",
            sku_code="SKU-NOT-BOUND-003",
            spec_text="30X50;蓝色",
            qty=1,
            revenue_amount=None,
            customer_note="用于验证：金额可为空",
        ),
        # 7) 数量缺失（系统会默认 1；但仍建议填）
        SampleRow(
            shipment_no="S-MVP-0007",
            completed_at=dt3,
            channel="单店验证-示例店",
            sku_code="SKU-NOT-BOUND-004",
            spec_text="60X90;红色",
            qty=None,
            revenue_amount=99,
            customer_note="用于验证：数量空值默认1（建议仍填）",
        ),
        # 8) 另一渠道：用于验证 channel 维度
        SampleRow(
            shipment_no="S-MVP-0008",
            completed_at=dt3,
            channel="单店验证-另一个店",
            sku_code="SKU-NOT-BOUND-005",
            spec_text="70X100;绿色",
            qty=3,
            revenue_amount=299,
            customer_note="用于验证：不同渠道分组",
        ),
        # 9) 边界：规格里混入全角/空格
        SampleRow(
            shipment_no="S-MVP-0009",
            completed_at=dt3,
            channel="单店验证-示例店",
            sku_code="SKU-NOT-BOUND-006",
            spec_text="  颜色分类:黑色包边；尺寸:45X45  ",
            qty=1,
            revenue_amount=59,
            customer_note="用于验证：spec_text 清洗（trim）",
        ),
        # 10) 边界：sku_code 带空格（系统会 trim）
        SampleRow(
            shipment_no="S-MVP-0010",
            completed_at=dt3,
            channel="单店验证-示例店",
            sku_code="  SKU-NOT-BOUND-007  ",
            spec_text="80X120;白色",
            qty=1,
            revenue_amount=129,
            customer_note="用于验证：sku_code 清洗（trim）",
        ),
    ]


def write_xlsx(*, out_path: Path, base_date: str) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "shipments"

    ws.append(DEFAULT_HEADERS)
    for r in build_rows(base_date=base_date):
        ws.append(
            [
                r.shipment_no,
                r.completed_at,
                r.channel,
                r.sku_code,
                r.spec_text,
                r.qty,
                r.revenue_amount,
                r.customer_note,
            ]
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out_path)


def main() -> int:
    parser = argparse.ArgumentParser(description="生成发货导入样例 xlsx（10行造数，用于MVP验收）")
    parser.add_argument(
        "--out",
        default="/home/admin/ai-costing-system/DOC/agents/fixtures/shipments_import_sample_10rows.xlsx",
        help="输出文件路径",
    )
    parser.add_argument(
        "--base-date",
        default=datetime.now().strftime("%Y-%m-%d"),
        help="样例完成时间使用的日期（YYYY-MM-DD）",
    )
    args = parser.parse_args()

    out_path = Path(args.out)
    write_xlsx(out_path=out_path, base_date=args.base_date)
    print(f"[ok] wrote: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


