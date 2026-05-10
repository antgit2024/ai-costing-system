"""finance C1 v1.3 端到端 smoke 脚本(派单 §2.8)。

任务来源
--------
``DOC/agents/briefings/costing_c1_client_v1.3_upgrade.md`` §2.8 + B8 完成标准。

做什么
------
对 finance C1 v1.3 终态 7 个 endpoint 各发 1 个标准请求 + assert 响应基本结构 +
输出 "all 7 endpoints consumed OK / X failed" 总结。

支持 2 种模式:
    --mock                    走本地 mock 数据(默认 ·  finance staging 还没拿到时用)
    --live --base-url=<URL>   走真接口(等用户拿到 finance staging URL + test key 时切)

使用
----
::

    # 1) 默认 mock 模式 — 不需要 finance staging
    cd /home/admin/ai-costing-system
    PYTHONPATH=backend python -m backend.scripts.finance_c1_e2e_smoke --mock

    # 2) live 模式 — 等拿到 staging URL + key
    PYTHONPATH=backend python -m backend.scripts.finance_c1_e2e_smoke \\
        --live --base-url=https://finance-staging.example.com \\
        --api-key=<test-key> --payroll-authorized

退出码
------
- 0  : 7 个 endpoint 全部消费成功(B8 验收对勾)
- 1  : 任一 endpoint 失败 → CI 会显红 ·  让 dev 修

注意
----
- 脚本**只发 GET 不写**·  对 finance 完全无副作用 ·  即使打到生产也安全。
- mock 模式不读环境变量 ·  完全 self-contained ·  CI 跑也不会被 env 污染。
- live 模式如果不传 --api-key ·  会 fallback 到 settings.finance_c1_api_key
  (来自 .env 的 FINANCE_C1_API_KEY) ·  方便本地调试。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple

if __package__ is None and __name__ == "__main__":
    BACKEND_DIR = Path(__file__).resolve().parents[1]
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))
    REPO_DIR = BACKEND_DIR.parent
    if str(REPO_DIR) not in sys.path:
        sys.path.insert(0, str(REPO_DIR))


# ---------------------------------------------------------------------------
# 颜色输出 — 让 7/7 OK 时一眼看到绿色
# ---------------------------------------------------------------------------


class _Color:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    RESET = "\033[0m"


def _ok(msg: str) -> str:
    return f"{_Color.GREEN}✓{_Color.RESET} {msg}"


def _fail(msg: str) -> str:
    return f"{_Color.RED}✗{_Color.RESET} {msg}"


def _info(msg: str) -> str:
    return f"{_Color.CYAN}ℹ{_Color.RESET} {msg}"


# ---------------------------------------------------------------------------
# Endpoint 定义 — 7 个 v1.3 终态接口
# ---------------------------------------------------------------------------


def _build_smoke_calls(client: Any) -> List[Tuple[str, Callable[[], Any], List[str]]]:
    """返回 [(endpoint name, lambda 调用, 期望字段 list), ...]。

    期望字段 = 每条 data row 里至少要有的关键字段 (assert 用)。
    """

    return [
        (
            "GET /api/v1/c1/companies (v1.0 + v1.3 4 recognition + floor_area)",
            lambda: client.list_companies(is_active=True),
            [
                "id",
                "legal_name",
                "entity_role",
                "tax_payer_type",
                # v1.3 增量 — 至少存在(可为 false / null)
                "revenue_recognition",
                "material_purchase_recognition",
                "payroll_recognition",
                "fixed_cost_recognition",
            ],
        ),
        (
            "GET /api/v1/c1/stores (v1.0)",
            lambda: client.list_stores(is_active=True),
            ["id", "store_name", "company_id"],
        ),
        (
            "GET /api/v1/c1/stores/revenue (v1.3 §4.2)",
            lambda: client.list_stores_revenue(period_year=2026, period_month=4),
            [
                "store_id",
                "store_name",
                "company_id",
                "gross_revenue",
                "net_revenue",
                "period_year",
                "period_month",
            ],
        ),
        (
            "GET /api/v1/c1/employees (v1.0)",
            lambda: client.list_employees(is_active=True),
            ["id", "employee_no", "name", "contract_company_id"],
        ),
        (
            "GET /api/v1/c1/fixed-costs (v1.0)",
            lambda: client.list_fixed_costs(period_year=2026, period_month=4),
            ["id", "company_id", "cost_category", "amount"],
        ),
        (
            "GET /api/v1/c1/payroll?aggregation=by_employee (v1.3 §4.5)",
            lambda: client.list_payroll(
                company_id="mock-company-uuid-factory-1",
                period_year=2026,
                period_month=4,
                aggregation="by_employee",
            ),
            [
                "employee_id",
                "employee_no",
                "name_masked",
                "company_id",
                "gross_salary",
                "total_labor_cost",
            ],
        ),
        (
            "GET /api/v1/c1/payment-requests (v1.3 §4.6)",
            lambda: client.list_payment_requests(period="202604"),
            [
                "id",
                "payment_date",
                "belong_month",
                "amount",
                "company_name",
                "expense_category",
                "is_monthly_amortized",
            ],
        ),
    ]


# ---------------------------------------------------------------------------
# Assertions
# ---------------------------------------------------------------------------


def _assert_envelope(envelope: Any, expected_data_source: str) -> List[str]:
    """检查 envelope 顶层基础字段。返回 errors list。"""

    errors: List[str] = []
    if not hasattr(envelope, "data") or not isinstance(envelope.data, list):
        errors.append("envelope.data 不是 list")
        return errors  # 后续断言依赖 data 结构 ·  早退

    if envelope.data_source != expected_data_source:
        errors.append(
            f"envelope.data_source={envelope.data_source!r} ·  期望 {expected_data_source!r}"
        )

    if envelope.fetched_at is None:
        errors.append("envelope.fetched_at 缺失")

    # v1.3 envelope 标记 — mock 模式 api_version 应含 1.3 标识
    if expected_data_source == "mock":
        api_v = envelope.api_version or ""
        if "1.3" not in str(api_v):
            errors.append(f"envelope.api_version={api_v!r} ·  期望含 '1.3'")

    return errors


def _assert_data_fields(rows: List[Dict[str, Any]], expected_fields: List[str]) -> List[str]:
    """检查每行至少有 expected_fields 列。返回 errors list。

    注意: 这里只验存在性(不要求 truthy)·  finance 给 None 也算字段就位 ·  避免
    误判「True/False/0/空字符串」这种合法值。
    """

    errors: List[str] = []
    if not rows:
        return errors  # 空数据放过 — endpoint 可能合法返空(过滤条件未命中)

    for i, row in enumerate(rows[:3]):  # 只查前 3 行 ·  保持 smoke 速度
        if not isinstance(row, dict):
            errors.append(f"row[{i}] 不是 dict ·  实际 type={type(row).__name__}")
            continue
        missing = [f for f in expected_fields if f not in row]
        if missing:
            errors.append(f"row[{i}] 缺字段: {missing}")

    return errors


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------


def run_smoke(
    *,
    mode: str,
    base_url: str | None,
    api_key: str | None,
    payroll_authorized: bool,
    timeout: float,
) -> int:
    """执行 7 个 endpoint smoke ·  返回退出码(0=全过 / 1=有失败)。"""

    # Lazy import ·  避免在模块导入阶段就吃 settings
    from src.planner.services.finance_c1_client import (  # type: ignore
        FinanceC1Client,
        FinanceC1Error,
        clear_cache,
    )

    use_mock = mode == "mock"
    expected_source = "mock" if use_mock else "live"

    print()
    print(f"{_Color.BOLD}finance C1 v1.3 E2E Smoke{_Color.RESET}")
    print(f"  mode               : {_Color.CYAN}{mode}{_Color.RESET}")
    if not use_mock:
        print(f"  base_url           : {base_url}")
        print(f"  api_key            : {'<set>' if api_key else '<from env>'}")
        print(f"  payroll_authorized : {payroll_authorized}")
    print()

    # 清 module-level cache ·  避免上一轮 live 跑残留
    clear_cache()

    client = FinanceC1Client(
        base_url=base_url,
        api_key=api_key,
        payroll_authorized=payroll_authorized if not use_mock else True,
        use_mock=use_mock,
        timeout=timeout,
    )

    calls = _build_smoke_calls(client)

    passed = 0
    failed = 0
    failure_details: List[str] = []

    for label, fn, expected_fields in calls:
        try:
            envelope = fn()
        except FinanceC1Error as exc:
            failed += 1
            print(_fail(f"{label}"))
            print(f"    └─ FinanceC1Error: {exc}")
            failure_details.append(f"{label}: {exc}")
            continue
        except Exception as exc:  # noqa: BLE001 — smoke 兜底
            failed += 1
            print(_fail(f"{label}"))
            print(f"    └─ {type(exc).__name__}: {exc}")
            failure_details.append(f"{label}: {type(exc).__name__}: {exc}")
            continue

        errors: List[str] = []
        errors.extend(_assert_envelope(envelope, expected_source))
        errors.extend(_assert_data_fields(envelope.data, expected_fields))

        if errors:
            failed += 1
            print(_fail(f"{label} — rows={len(envelope.data)}"))
            for err in errors:
                print(f"    └─ {err}")
            failure_details.append(f"{label}: {'; '.join(errors)}")
        else:
            passed += 1
            api_v = envelope.api_version or "—"
            print(
                _ok(
                    f"{label} — rows={len(envelope.data)}, "
                    f"data_source={envelope.data_source}, api_version={api_v}"
                )
            )

    print()
    print("=" * 70)
    if failed == 0:
        print(
            f"{_Color.GREEN}{_Color.BOLD}all 7 endpoints consumed OK{_Color.RESET} "
            f"({passed}/{passed + failed})"
        )
        print()
        return 0
    else:
        print(
            f"{_Color.RED}{_Color.BOLD}{failed} failed{_Color.RESET} "
            f"({passed}/{passed + failed})"
        )
        for detail in failure_details:
            print(f"  - {detail}")
        print()
        return 1


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="finance C1 v1.3 7-endpoint E2E smoke (--mock / --live)",
    )
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--mock",
        action="store_const",
        dest="mode",
        const="mock",
        help="走本地 mock 数据 (default; 不需要 finance staging)",
    )
    mode_group.add_argument(
        "--live",
        action="store_const",
        dest="mode",
        const="live",
        help="走真接口 (需 --base-url=<URL>)",
    )
    parser.set_defaults(mode="mock")

    parser.add_argument(
        "--base-url",
        default=None,
        help="finance staging URL (--live 时必填)",
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="X-Costing-Api-Key (默认从 settings.finance_c1_api_key 读)",
    )
    parser.add_argument(
        "--payroll-authorized",
        action="store_true",
        help="开启 X-Payroll-Authorized: true 头 (默认 false)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        help="HTTP timeout 秒 (默认 10.0)",
    )

    args = parser.parse_args()
    if args.mode == "live" and not args.base_url:
        parser.error("--live 模式必须传 --base-url=<finance staging URL>")
    return args


def main() -> int:
    args = _parse_args()
    return run_smoke(
        mode=args.mode,
        base_url=args.base_url,
        api_key=args.api_key,
        payroll_authorized=args.payroll_authorized,
        timeout=args.timeout,
    )


if __name__ == "__main__":
    sys.exit(main())
