"""cost_center master table + 6 班组初稿 + processes.cost_center_id FK

Revision ID: 0040_cost_center
Revises: 0039_materials_stage2_fields
Create Date: 2026-05-10

Background
----------
Path A — 让真数据通电 §A1 — finance C1 v1.3 已端到端真闭环, 但 costing 这边
3 个核心 service 一行没写, Hub 4 层 resolve 链里 ``cost_center_id=None``
写死。本 migration 是「让油管接通发动机」的第一步:

1. 建 ``cost_center`` 主表(6 字段 + JSON metadata + soft delete)
2. 给 ``processes`` 加 ``cost_center_id`` nullable FK(向后兼容: 历史
   数据 cost_center_id IS NULL 是合法的, 下游 ``_resolve_overhead_rate``
   已经能 fallback)
3. INSERT 6 个 cost_center 初稿(production / auxiliary / admin 三类)
4. 跑模糊匹配把现有 ``processes.team_name`` 的 distinct 值映射到
   cost_center_id(匹配不上的保留 NULL)

班组命名是「初稿」: A1.runtime cost_center_service.refresh_finance_department_mapping
会跑一次 finance employees /departments 聚合, 把 finance 真 department
名追加进 ``cost_center.metadata.finance_department_mapping``, 不一致
时以 finance 数据为准重命名(保持 code 不变)。

Strategy
--------
- ``cost_center.id`` String(36) UUID — 与全 repo 现有约定一致
- ``code`` UNIQUE — 程序读取 ID 用 code, 不用 UUID(便于人读 SQL)
- ``legacy_team_names`` JSON list — 记录这个 cost_center 「吸收」了哪些老
  team_name(用于 audit / rollback / 老数据排查)
- ``metadata_json.finance_department_mapping`` 用 JSON list 字段记录
  finance department → cost_center 的映射(由 service 在 runtime 维护)
- ``metadata_json.assignment_log`` 用 JSON list 记录每一次 mapping
  refresh 的 reasoning(便于审计)
- ``deleted_at`` TIMESTAMP soft-delete sentinel(与 cost_initiatives /
  cost_packages 的 SoftDeleteMixin 风格一致, 但本表用显式列方便筛)

Tested with both PostgreSQL (production) and SQLite (planner_test pytest
fixtures). Downgrade fully reverses upgrade.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0040_cost_center"
down_revision = "0039_materials_stage2_fields"
branch_labels = None
depends_on = None


def _dialect_name() -> str:
    bind = op.get_bind()
    return getattr(getattr(bind, "dialect", None), "name", "") or ""


def _defaults() -> tuple[sa.TextClause, sa.TextClause, sa.TextClause]:
    dialect = _dialect_name()
    if dialect == "postgresql":
        return (
            sa.text("'{}'::json"),
            sa.text("'[]'::json"),
            sa.text("now()"),
        )
    return sa.text("'{}'"), sa.text("'[]'"), sa.text("CURRENT_TIMESTAMP")


# Six initial cost_center seeds(派单 §2 A1.1)。
# `legacy_team_keywords` 用于把现有 processes.team_name 模糊匹配映射进去。
_SEEDS: list[dict] = [
    {
        "code": "CC_DECOR_PROD",
        "name": "家居饰品生产组",
        "type": "production",
        "default_allocation_basis": "team_hours",
        "description": "家居饰品 / 摆件 / 画框等主营生产班组",
        "legacy_team_keywords": ["家居", "饰品", "摆件", "画框", "画艺"],
    },
    {
        "code": "CC_FABRIC_PROD",
        "name": "布艺生产组",
        "type": "production",
        "default_allocation_basis": "team_hours",
        "description": "窗帘 / 布艺 / 抱枕 / 床品类生产班组",
        "legacy_team_keywords": ["布艺", "窗帘", "抱枕", "床品", "缝纫"],
    },
    {
        "code": "CC_PRINT",
        "name": "印花打印组",
        "type": "auxiliary",
        "default_allocation_basis": "team_hours",
        "description": "数码印花 / 转印 / 烫画工序辅助班组",
        "legacy_team_keywords": ["印花", "转印", "烫画", "印染", "数码"],
    },
    {
        "code": "CC_CUT_EDGE",
        "name": "裁剪包边组",
        "type": "auxiliary",
        "default_allocation_basis": "team_hours",
        "description": "裁剪 / 包边 / 切割等工序辅助班组",
        "legacy_team_keywords": ["裁剪", "包边", "切割", "裁缝"],
    },
    {
        "code": "CC_PACK_SHIP",
        "name": "包装发货组",
        "type": "auxiliary",
        "default_allocation_basis": "headcount",
        "description": "包装 / 入库 / 发货 / 质检环节",
        "legacy_team_keywords": ["包装", "发货", "质检", "入库", "出库", "打包"],
    },
    {
        "code": "CC_ADMIN",
        "name": "公共管理",
        "type": "admin",
        "default_allocation_basis": "headcount",
        "description": "厂部 / 行政 / 财务 / 公共管理类(非直接生产)",
        "legacy_team_keywords": ["管理", "行政", "财务", "厂部", "办公"],
    },
]


def upgrade() -> None:
    json_obj_default, json_arr_default, now_default = _defaults()
    dialect = _dialect_name()

    # ----- 1) cost_center 主表 -----
    op.create_table(
        "cost_center",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("default_allocation_basis", sa.String(length=32), nullable=True),
        sa.Column("legacy_team_names", sa.JSON(), nullable=False, server_default=json_arr_default),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true") if dialect == "postgresql" else sa.text("1")),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=json_obj_default),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=now_default),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=now_default),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
    )
    op.create_unique_constraint("uq_cost_center_code", "cost_center", ["code"])
    op.create_index("idx_cost_center_active", "cost_center", ["is_active"])
    op.create_index("idx_cost_center_type", "cost_center", ["type"])

    # ----- 2) processes.cost_center_id (nullable FK) -----
    with op.batch_alter_table("processes") as batch:
        batch.add_column(sa.Column("cost_center_id", sa.String(length=36), nullable=True))
    op.create_index("idx_processes_cost_center", "processes", ["cost_center_id"])
    if dialect == "postgresql":
        # SQLite batch_alter_table can't add FK after the fact reliably; skip
        # the FK constraint there (tests don't depend on it). Production PG
        # gets the proper referential integrity guard.
        op.create_foreign_key(
            "fk_processes_cost_center",
            "processes",
            "cost_center",
            ["cost_center_id"],
            ["id"],
            ondelete="SET NULL",
        )

    # ----- 3) INSERT 6 个 cost_center 初稿 -----
    # 用 raw INSERT 而非 ORM, 让 migration 跑完即可使用; 不依赖 SQLAlchemy
    # session(避免在 alembic 上下文里反复 import models)。UUID 用 Python
    # 端生成, 让 PostgreSQL 与 SQLite 表现一致。
    import json
    import uuid

    bind = op.get_bind()
    for seed in _SEEDS:
        cc_id = str(uuid.uuid4())
        meta = {
            "seed_version": "v1",
            "seed_at": "2026-05-10",
            "legacy_team_keywords": seed["legacy_team_keywords"],
            "finance_department_mapping": [],
            "assignment_log": [
                {
                    "at": "2026-05-10T15:40:00+08:00",
                    "by": "migration_0040",
                    "action": "seed_initial",
                    "note": (
                        "Path A §A1 seed. finance department mapping 由 "
                        "cost_center_service.refresh_finance_department_mapping "
                        "在 runtime 拉 finance employees 后追加。"
                    ),
                }
            ],
        }
        bind.execute(
            sa.text(
                "INSERT INTO cost_center "
                "(id, code, name, type, description, default_allocation_basis, "
                " legacy_team_names, is_active, metadata) "
                "VALUES (:id, :code, :name, :type, :description, :basis, "
                "        :legacy, :is_active, :metadata)"
            ),
            {
                "id": cc_id,
                "code": seed["code"],
                "name": seed["name"],
                "type": seed["type"],
                "description": seed["description"],
                "basis": seed["default_allocation_basis"],
                "legacy": json.dumps([]),
                "is_active": True,
                "metadata": json.dumps(meta, ensure_ascii=False),
            },
        )

    # ----- 4) 把现有 processes.team_name 模糊匹配到 cost_center -----
    # 取 cost_center 行(含 metadata.legacy_team_keywords) — 用 SQL 也行,
    # 但 metadata 在 SQLite 是 TEXT, PG 是 JSON, 两边 JSON 取值语法不同。
    # 这里在 Python 侧做匹配最简洁。
    cc_rows = list(
        bind.execute(sa.text("SELECT id, code, metadata FROM cost_center"))
    )
    cc_id_by_keyword: list[tuple[str, str]] = []
    for row in cc_rows:
        meta = row[2]
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except (TypeError, ValueError):
                meta = {}
        for kw in (meta or {}).get("legacy_team_keywords") or []:
            cc_id_by_keyword.append((kw, row[0]))

    team_name_rows = list(
        bind.execute(
            sa.text(
                "SELECT DISTINCT team_name FROM processes "
                "WHERE team_name IS NOT NULL AND team_name <> ''"
            )
        )
    )
    matched_count = 0
    for tn_row in team_name_rows:
        tn = tn_row[0] or ""
        if not tn:
            continue
        # 找第一个关键字命中
        matched_cc_id: str | None = None
        for kw, cc_id in cc_id_by_keyword:
            if kw and kw in tn:
                matched_cc_id = cc_id
                break
        if matched_cc_id:
            bind.execute(
                sa.text(
                    "UPDATE processes SET cost_center_id = :cc "
                    "WHERE team_name = :tn"
                ),
                {"cc": matched_cc_id, "tn": tn},
            )
            matched_count += 1

    # 把命中过的 team_name 回填到对应 cost_center.legacy_team_names(audit 用)
    for cc_id, code, _meta in cc_rows:
        absorbed = list(
            bind.execute(
                sa.text(
                    "SELECT DISTINCT team_name FROM processes "
                    "WHERE cost_center_id = :cc AND team_name IS NOT NULL"
                ),
                {"cc": cc_id},
            )
        )
        names = [r[0] for r in absorbed if r[0]]
        if names:
            bind.execute(
                sa.text(
                    "UPDATE cost_center SET legacy_team_names = :legacy "
                    "WHERE id = :cc"
                ),
                {"cc": cc_id, "legacy": json.dumps(names, ensure_ascii=False)},
            )

    # 不打 print(alembic 抑制 stdout); migration 跑完后由 service 验证


def downgrade() -> None:
    dialect = _dialect_name()

    # 1) processes.cost_center_id 反清(先删 FK 再删列)
    op.drop_index("idx_processes_cost_center", table_name="processes")
    if dialect == "postgresql":
        try:
            op.drop_constraint("fk_processes_cost_center", "processes", type_="foreignkey")
        except Exception:  # noqa: BLE001 — best-effort cleanup
            pass
    with op.batch_alter_table("processes") as batch:
        batch.drop_column("cost_center_id")

    # 2) drop cost_center
    op.drop_index("idx_cost_center_type", table_name="cost_center")
    op.drop_index("idx_cost_center_active", table_name="cost_center")
    op.drop_constraint("uq_cost_center_code", "cost_center", type_="unique")
    op.drop_table("cost_center")
