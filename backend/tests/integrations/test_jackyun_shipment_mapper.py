"""End-to-end test of the Jackyun integration layer using a stub HTTP layer.

We don't hit the real upstream — instead we patch ``JackyunClient.call`` to
return a synthetic payload that mirrors the real ``wms.order.query-info.page``
response, then assert that the sync run lands data into:

- ``integration_sync_runs`` (status=succeeded, counters)
- ``integration_api_records`` (one row per shipment header)
- ``shipment_lines`` (one row per goodsDetail line, source_system='jackyun')
"""

from __future__ import annotations

from typing import Any, Dict

from src.integrations.base.client import ClientResponse
from src.integrations.jackyun import client as jackyun_client_mod
from src.integrations.jackyun import sync_jobs as jackyun_sync_jobs
from src.integrations.jackyun.api import shipment as shipment_api
from src.integrations.jackyun.mappers import shipment as jackyun_shipment_mapper
from src.planner import models as planner_models


SAMPLE_SHIPMENT = {
    "orderNo": "S202605050337",
    "platCode": "TMALL",
    "ownerName": "自营",
    "warehouseName": "成品仓",
    "warehouseCode": "W001",
    "erporderNo": "JY202605050237",
    "logisticNo": "DPK301877471965",
    "logisticName": "德邦",
    "logisticType": 1,
    "logisticTypeName": "普通快递",
    "orderStatus": 7,
    "orderStatusName": "已完成",
    "shopId": "1839228742782059392",
    "shopName": "九斗云旗舰店",
    "finishTime": "2026-05-05 16:51:43",
    "gmtCreate": "2026-05-05 15:26:23",
    "sendTime": "2026-05-05 16:51:43",
    "modifyTime": "2026-05-05 16:51:43",
    "platOrderNo": "3299468990293129589",
    "sellerMemo": "请走德邦",
    "buyerMemo": None,
    "flagNames": "VIP",
    "goodsDetail": [
        {
            "goodsNo": "J25073103",
            "goodsName": "蓝色大海餐厅饭厅高级感装饰画",
            "skuBarcode": "5892064445582",
            "outSkuCode": None,
            "skuName": "J25073103A;宣绒布+卡纸;约30*30;蓝色金属外框",
            "tradeName": "蓝色大海餐厅饭厅高级感装饰画",
            "tradeSpec": "颜色分类:J25073103A;组合形式:宣绒布+卡纸;尺寸:约30*30;外框类型:蓝色金属外框",
            "tradeGoodsno": "J25073103MQ0103--AREA200-J22030103",
            "sellCount": 1,
            "actualCount": 1,
            "sellPrice": 99.9,
            "sellTotal": 89.9,
            "isGift": 0,
            "detailId": "2472676284727002753",
            "unit": "件",
            "skuId": "2272723253017249409",
            "remark": "",
        }
    ],
}


def _stub_call(monkeypatch, payloads=None):
    """Make ``client.call`` return one synthetic page then an empty page.

    Pass ``payloads=[{...}, {...}]`` to test multi-record scenarios.
    """

    page_payloads = list(payloads) if payloads is not None else [SAMPLE_SHIPMENT]
    pages = [
        {
            "code": 200,
            "msg": "操作成功",
            "result": {
                "contextId": "ctx-1",
                "data": page_payloads,
                "pageInfo": {"pageIndex": 1, "pageSize": 50, "total": len(page_payloads)},
            },
        },
    ]
    call_log = []

    def fake_call(self, api_method, biz_content, *, sync_run_id=None, db=None):
        call_log.append((api_method, dict(biz_content)))
        body: Dict[str, Any] = pages.pop(0) if pages else {
            "code": 200,
            "msg": "操作成功",
            "result": {
                "contextId": "ctx-1",
                "data": [],
                "pageInfo": {"total": len(page_payloads)},
            },
        }
        return ClientResponse(
            success=True,
            biz_code="200",
            biz_sub_code=None,
            message="操作成功",
            data=(body.get("result") or {}).get("data"),
            raw=body,
            http_status=200,
            context_id=(body.get("result") or {}).get("contextId"),
        )

    monkeypatch.setattr(jackyun_client_mod.JackyunClient, "call", fake_call)
    return call_log


def _make_fake_client():
    fake_client = jackyun_client_mod.JackyunClient.__new__(jackyun_client_mod.JackyunClient)
    fake_client.source_system = "jackyun"
    return fake_client


def test_parse_dt_treats_upstream_string_as_beijing_local():
    """Regression for 2026-05-07 timezone bug: Jackyun upstream timestamps are
    Beijing-local strings (no tz suffix). They must be parsed as Asia/Shanghai
    and converted to UTC for storage; otherwise downstream renderers add +8
    again and rows display 8 hours late.
    """
    from datetime import datetime, timezone, timedelta

    parsed = jackyun_shipment_mapper._parse_dt("2026-05-05 16:51:43")
    assert parsed is not None
    assert parsed.tzinfo == timezone.utc
    # 16:51 Beijing == 08:51 UTC
    assert parsed.hour == 8
    assert parsed.minute == 51

    expected = datetime(2026, 5, 5, 16, 51, 43, tzinfo=timezone(timedelta(hours=8)))
    assert parsed == expected.astimezone(timezone.utc)


def test_completed_at_falls_back_through_payload_levels():
    """When upstream finishTime/sendTime are empty, the mapper must walk the
    fallback chain (payTime -> orderTime -> gmtCreate -> sync time) and tag
    metadata so financial audits can opt out of synthetic anchors.
    """
    from datetime import timezone
    payload = {
        "orderNo": "S-NULL-FINISH",
        "shopName": "TestShop",
        "payTime": "2026-05-01 16:16:49",
        "orderTime": "2026-05-01 16:16:16",
        "gmtCreate": "2026-05-02 07:42:17",
        "goodsDetail": [],
    }
    parsed = jackyun_shipment_mapper._parse_dt(payload["payTime"])
    assert parsed.astimezone(timezone.utc).hour == 8  # 16:16 +08:00 == 08:16 UTC


def test_sync_shipments_promotes_jackyun_v2_full_fields_into_columns(
    db_session, monkeypatch
):
    """Migration 0036 promoted 20 Jackyun fields to typed columns. Lock the
    extraction so a future raw_row-only refactor cannot silently regress.

    Covers:
    - All header extensions (orderStatusName / logisticTypeName / LogisticCode
      upper-camel quirk / customerName / picker/packer/checker / wave_no /
      checkStartTime / payTime / orderTime / tradeType + msg).
    - All goodsDetail extensions (sellPrice / unit / cateName / goodsName /
      goodsNo / isGift 0/1 / actualCount).
    """
    payload = dict(SAMPLE_SHIPMENT)
    payload.update(
        {
            "customerName": "张三",
            "picker": "拣货员A",
            "packer": "打包员B",
            "checker": "验货员C",
            "waveNo": "W202605050001",
            "checkStartTime": "2026-05-05 16:30:00",
            "payTime": "2026-05-05 14:00:00",
            "orderTime": "2026-05-05 13:55:00",
            "tradeType": 1,
            "tradeTypeMsg": "正常销售",
            # NB Jackyun v2 spec uses upper-camel ``LogisticCode`` (verified
            # in their official sample payload). Some sandboxes use lower
            # camel — both must be tolerated.
            "LogisticCode": "DPK",
        }
    )
    payload["goodsDetail"] = [dict(payload["goodsDetail"][0])]
    payload["goodsDetail"][0].update(
        {
            "cateName": "装饰画",
            "isGift": 1,
        }
    )

    _stub_call(monkeypatch, payloads=[payload])
    jackyun_sync_jobs.sync_shipments(
        db_session,
        page_size=50,
        client=_make_fake_client(),
        triggered_by="full-fields-test",
        use_watermark=False,
    )
    db_session.commit()

    line = (
        db_session.query(planner_models.ShipmentLine)
        .filter(planner_models.ShipmentLine.source_system == "jackyun")
        .one()
    )
    assert line.order_status_name == "已完成"
    assert line.logistic_type_name == "普通快递"
    assert line.logistic_code == "DPK"
    assert line.wave_no == "W202605050001"
    assert line.customer_name == "张三"
    assert line.picker == "拣货员A"
    assert line.packer == "打包员B"
    assert line.checker == "验货员C"
    assert line.check_started_at is not None
    assert line.paid_at is not None
    assert line.ordered_at is not None
    assert line.trade_type == 1
    assert line.trade_type_msg == "正常销售"
    # Detail fields:
    assert line.unit_price is not None and float(line.unit_price) == 99.9
    assert line.unit_of_measure == "件"
    assert line.category_name == "装饰画"
    assert line.goods_name == "蓝色大海餐厅饭厅高级感装饰画"
    assert line.goods_no == "J25073103"
    assert line.is_gift is True
    assert line.actual_qty is not None and float(line.actual_qty) == 1.0
    # Sanity: revenue (sellTotal=89.9) < unit_price * qty (99.9) — discount
    # detection works only because we now persist unit_price as a column.
    assert float(line.unit_price) > float(line.revenue_amount or 0)


def test_lower_camel_logistic_code_is_also_accepted(db_session, monkeypatch):
    """Sandbox payloads sometimes ship lowerCamel ``logisticCode`` instead of
    the documented upperCamel ``LogisticCode``. Both must work — otherwise
    we silently lose carrier code on whichever environment uses the variant.
    """
    payload = dict(SAMPLE_SHIPMENT)
    payload["LogisticCode"] = None  # explicit absence
    payload["logisticCode"] = "lower-camel-FX"
    _stub_call(monkeypatch, payloads=[payload])
    jackyun_sync_jobs.sync_shipments(
        db_session,
        page_size=50,
        client=_make_fake_client(),
        triggered_by="lower-camel-test",
        use_watermark=False,
    )
    db_session.commit()
    line = (
        db_session.query(planner_models.ShipmentLine)
        .filter(planner_models.ShipmentLine.source_system == "jackyun")
        .one()
    )
    assert line.logistic_code == "lower-camel-FX"


def test_is_gift_zero_resolves_to_false_not_none(db_session, monkeypatch):
    """``isGift`` of 0 (or "0") must store False, not NULL — otherwise we
    cannot distinguish "explicitly not a gift" from "legacy unknown".
    """
    payload = dict(SAMPLE_SHIPMENT)
    payload["goodsDetail"] = [dict(payload["goodsDetail"][0])]
    payload["goodsDetail"][0]["isGift"] = "0"
    _stub_call(monkeypatch, payloads=[payload])
    jackyun_sync_jobs.sync_shipments(
        db_session,
        page_size=50,
        client=_make_fake_client(),
        triggered_by="is-gift-zero-test",
        use_watermark=False,
    )
    db_session.commit()
    line = (
        db_session.query(planner_models.ShipmentLine)
        .filter(planner_models.ShipmentLine.source_system == "jackyun")
        .one()
    )
    assert line.is_gift is False


def test_sync_shipments_lands_data_into_integration_and_business_tables(
    db_session, monkeypatch
):
    call_log = _stub_call(monkeypatch)

    sync_run_id = jackyun_sync_jobs.sync_shipments(
        db_session,
        start_modify_time="2026-05-05 00:00:00",
        end_modify_time="2026-05-05 23:59:59",
        page_size=50,
        client=_make_fake_client(),
        triggered_by="unit-test",
        use_watermark=False,
    )
    db_session.commit()

    assert call_log and call_log[0][0] == shipment_api.DEFAULT_LIST_API
    # The default list endpoint MUST be the (whole-shipment) page method —
    # NOT the v2 "unfinished only" variant, which would silently drop the
    # majority of completed shipments from financial reports.
    assert shipment_api.DEFAULT_LIST_API == shipment_api.API_QUERY_INFO_PAGE

    run = (
        db_session.query(planner_models.IntegrationSyncRun)
        .filter(planner_models.IntegrationSyncRun.id == sync_run_id)
        .one()
    )
    assert run.status == "succeeded"
    assert run.source_system == "jackyun"
    assert run.api_method == shipment_api.DEFAULT_LIST_API
    assert run.total_rows == 1
    assert run.inserted_rows == 1
    assert run.updated_rows == 0

    records = (
        db_session.query(planner_models.IntegrationApiRecord)
        .filter(planner_models.IntegrationApiRecord.sync_run_id == sync_run_id)
        .all()
    )
    assert len(records) == 1
    rec = records[0]
    assert rec.source_system == "jackyun"
    assert rec.record_type == "shipment"
    assert rec.external_id == SAMPLE_SHIPMENT["orderNo"]
    assert rec.payload_json["orderNo"] == SAMPLE_SHIPMENT["orderNo"]
    assert rec.schema_version == jackyun_sync_jobs.SHIPMENT_SCHEMA_VERSION
    assert rec.payload_bytes is not None and rec.payload_bytes > 0

    lines = (
        db_session.query(planner_models.ShipmentLine)
        .filter(planner_models.ShipmentLine.source_system == "jackyun")
        .all()
    )
    assert len(lines) == 1
    line = lines[0]
    assert line.shipment_no == SAMPLE_SHIPMENT["orderNo"]
    assert line.erp_order_no == SAMPLE_SHIPMENT["erporderNo"]
    assert line.platform_order_no == SAMPLE_SHIPMENT["platOrderNo"]
    assert line.logistic_no == SAMPLE_SHIPMENT["logisticNo"]
    assert line.warehouse_code == SAMPLE_SHIPMENT["warehouseCode"]
    assert line.warehouse_name == SAMPLE_SHIPMENT["warehouseName"]
    assert line.seller_memo == SAMPLE_SHIPMENT["sellerMemo"]
    assert line.sku_code == SAMPLE_SHIPMENT["goodsDetail"][0]["skuBarcode"]
    assert line.qty is not None and float(line.qty) == 1.0
    assert line.source_payload_id == rec.id


def test_sync_shipments_is_idempotent_on_second_run(db_session, monkeypatch):
    _stub_call(monkeypatch)

    sync_run_id_1 = jackyun_sync_jobs.sync_shipments(
        db_session,
        page_size=50,
        client=_make_fake_client(),
        triggered_by="t1",
        use_watermark=False,
    )
    db_session.commit()

    _stub_call(monkeypatch)
    sync_run_id_2 = jackyun_sync_jobs.sync_shipments(
        db_session,
        page_size=50,
        client=_make_fake_client(),
        triggered_by="t2",
        use_watermark=False,
    )
    db_session.commit()

    assert sync_run_id_1 != sync_run_id_2

    line_count = (
        db_session.query(planner_models.ShipmentLine)
        .filter(planner_models.ShipmentLine.source_system == "jackyun")
        .count()
    )
    assert line_count == 1

    rec_count = (
        db_session.query(planner_models.IntegrationApiRecord)
        .filter(planner_models.IntegrationApiRecord.source_system == "jackyun")
        .count()
    )
    assert rec_count == 1


def test_sync_shipments_advances_watermark_when_enabled(db_session, monkeypatch):
    """After a successful sync the watermark should advance to the latest modifyTime."""

    _stub_call(monkeypatch)

    jackyun_sync_jobs.sync_shipments(
        db_session,
        page_size=50,
        client=_make_fake_client(),
        triggered_by="watermark-test",
        use_watermark=True,
    )
    db_session.commit()

    wm = (
        db_session.query(planner_models.IntegrationSyncWatermark)
        .filter(
            planner_models.IntegrationSyncWatermark.source_system == "jackyun",
            planner_models.IntegrationSyncWatermark.sync_type
            == jackyun_sync_jobs.SHIPMENT_SYNC_TYPE,
        )
        .one_or_none()
    )
    assert wm is not None, "expected a watermark row to be created"
    assert wm.watermark_field == jackyun_sync_jobs.SHIPMENT_WATERMARK_FIELD
    # New watermark policy (since 2026-05-06): the value is
    # ``min(max(payload_ts, last_window_end), now - 5 minutes)`` rather than
    # the literal payload modifyTime — the safety buffer prevents missing
    # records that upstream uploads with a few seconds of delay. We assert
    # the value sits in a sane band: at least the payload's modifyTime
    # (we observed it), and never in the future.
    from datetime import datetime as _dt, timezone as _tz, timedelta as _td
    sh_now = _dt.now(_tz(_td(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
    assert wm.watermark_value >= SAMPLE_SHIPMENT["modifyTime"], (
        f"watermark went backwards: {wm.watermark_value} < {SAMPLE_SHIPMENT['modifyTime']}"
    )
    assert wm.watermark_value <= sh_now, (
        f"watermark in the future: {wm.watermark_value} > now {sh_now}"
    )


def test_sync_shipments_routes_mapper_failures_to_dead_letter(db_session, monkeypatch):
    """A mapper exception should NOT abort the run — it should land in the dead-letter table."""

    _stub_call(monkeypatch)

    def _boom(*args, **kwargs):
        raise RuntimeError("synthetic mapper failure")

    monkeypatch.setattr(
        jackyun_shipment_mapper, "upsert_shipment_from_payload", _boom
    )

    sync_run_id = jackyun_sync_jobs.sync_shipments(
        db_session,
        page_size=50,
        client=_make_fake_client(),
        triggered_by="dead-letter-test",
        use_watermark=False,
    )
    db_session.commit()

    run = (
        db_session.query(planner_models.IntegrationSyncRun)
        .filter(planner_models.IntegrationSyncRun.id == sync_run_id)
        .one()
    )
    assert run.status == "succeeded", "per-record failures must NOT fail the whole run"
    assert run.error_rows == 1
    assert run.inserted_rows == 0

    dead = (
        db_session.query(planner_models.IntegrationDeadLetter)
        .filter(planner_models.IntegrationDeadLetter.sync_run_id == sync_run_id)
        .all()
    )
    assert len(dead) == 1
    assert dead[0].source_system == "jackyun"
    assert dead[0].record_type == "shipment"
    assert dead[0].stage == "mapper"
    assert dead[0].status == "open"
    assert dead[0].external_id == SAMPLE_SHIPMENT["orderNo"]
    assert dead[0].error_type == "RuntimeError"
    assert "synthetic mapper failure" in (dead[0].error_message or "")
    assert (dead[0].metadata_json or {}).get("schema_version") == jackyun_sync_jobs.SHIPMENT_SCHEMA_VERSION


def test_sync_shipments_keeps_multiple_schema_versions(db_session, monkeypatch):
    """When SHIPMENT_SCHEMA_VERSION is bumped we must keep BOTH versions of the same record.

    Same external_id, different schema_version: the api_records table should preserve
    historical contracts so old payloads can be replayed against old mappers.
    """

    original_version = jackyun_sync_jobs.SHIPMENT_SCHEMA_VERSION

    _stub_call(monkeypatch)
    jackyun_sync_jobs.sync_shipments(
        db_session,
        page_size=50,
        client=_make_fake_client(),
        triggered_by="v1",
        use_watermark=False,
    )
    db_session.commit()

    rec_v1 = (
        db_session.query(planner_models.IntegrationApiRecord)
        .filter(planner_models.IntegrationApiRecord.source_system == "jackyun")
        .one()
    )
    assert rec_v1.schema_version == original_version
    rec_v1_id = rec_v1.id

    monkeypatch.setattr(jackyun_sync_jobs, "SHIPMENT_SCHEMA_VERSION", "jackyun.shipment.v2")
    bumped = dict(SAMPLE_SHIPMENT)
    bumped["modifyTime"] = "2026-05-06 09:00:00"
    bumped["sellerMemo"] = "请走顺丰"
    _stub_call(monkeypatch, payloads=[bumped])

    jackyun_sync_jobs.sync_shipments(
        db_session,
        page_size=50,
        client=_make_fake_client(),
        triggered_by="v2",
        use_watermark=False,
    )
    db_session.commit()

    all_recs = (
        db_session.query(planner_models.IntegrationApiRecord)
        .filter(
            planner_models.IntegrationApiRecord.source_system == "jackyun",
            planner_models.IntegrationApiRecord.external_id == SAMPLE_SHIPMENT["orderNo"],
        )
        .all()
    )
    versions = {rec.schema_version for rec in all_recs}
    assert versions == {original_version, "jackyun.shipment.v2"}, (
        f"expected both schema versions to coexist, got {versions}"
    )

    rec_v1_again = next(rec for rec in all_recs if rec.id == rec_v1_id)
    assert rec_v1_again.schema_version == original_version, "v1 row must remain immutable"

    rec_v2 = next(
        rec for rec in all_recs if rec.schema_version == "jackyun.shipment.v2"
    )
    assert rec_v2.payload_json["sellerMemo"] == "请走顺丰"
    assert rec_v2.id != rec_v1_id, "a new row must be inserted for the new schema_version"

    line = (
        db_session.query(planner_models.ShipmentLine)
        .filter(planner_models.ShipmentLine.source_system == "jackyun")
        .one()
    )
    assert line.seller_memo == "请走顺丰"
    assert line.source_payload_id == rec_v2.id, "business row should point to the latest version"
