from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import httpx

from ...config import settings


def _fallback_description(payload: Dict[str, Any]) -> str:
    module_name = str(payload.get("module_name") or "").strip()
    category = str(payload.get("category") or "").strip()
    materials = payload.get("materials") or []
    steps = payload.get("steps") or []

    lines: List[str] = []
    title = module_name or "工艺模块"
    if category:
        title = f"{title}（{category}）"
    lines.append(title)

    if steps:
        lines.append("工序：")
        for i, s in enumerate(steps[:12], start=1):
            pname = str(s.get("process_name") or s.get("process_code") or "").strip() or "未命名工序"
            team = str(s.get("team_name") or "").strip()
            mt = str(s.get("measure_type") or "").strip()
            base = s.get("base_minutes")
            unit = s.get("unit_minutes")
            rate = s.get("rate_per_minute")
            extra = []
            if team:
                extra.append(f"班组:{team}")
            if mt:
                extra.append(f"计量:{mt}")
            if base is not None or unit is not None:
                extra.append(f"工时:{base or 0}+{unit or 0}")
            if rate:
                extra.append(f"单价:{rate}元/分")
            suffix = f"（{'，'.join(extra)}）" if extra else ""
            lines.append(f"- {i}. {pname}{suffix}")

    if materials:
        lines.append("物料：")
        for i, m in enumerate(materials[:12], start=1):
            name = str(m.get("material_name") or m.get("material_code") or "").strip() or "未命名物料"
            qty = m.get("quantity")
            unit = str(m.get("unit_of_measure") or "").strip()
            loss = m.get("loss_rate")
            calc = str(m.get("calculation_method") or "").strip()
            price = m.get("bom_unit_price")
            bom_unit = str(m.get("bom_unit") or "").strip()
            parts = []
            if qty is not None:
                parts.append(f"数量:{qty}{unit or ''}")
            if loss is not None:
                parts.append(f"损耗:{loss}%")
            if calc:
                parts.append(f"计量:{calc}")
            if price is not None:
                parts.append(f"BOM:{price}/{bom_unit or '-'}")
            suffix = f"（{'，'.join(parts)}）" if parts else ""
            lines.append(f"- {i}. {name}{suffix}")

    return "\n".join(lines).strip()


def generate_process_module_description(payload: Dict[str, Any]) -> Tuple[str, str]:
    """
    Return (description, provider).
    provider: 'llm' or 'fallback'
    """

    if settings.feature_flag_mock_integrations:
        return _fallback_description(payload), "fallback"

    if not settings.llm_base_url or not settings.llm_api_key:
        return _fallback_description(payload), "fallback"

    prompt = (
        "你是资深工艺工程师。请根据给定的工艺模块信息，生成一段自然语言的“工艺模块描述”，要求：\n"
        "1) 说明该模块产出/目的；2) 概括主要工序顺序；3) 概括关键物料与计量口径；\n"
        "4) 用中文，150~300字，尽量贴近生产口吻；5) 不要输出Markdown。\n\n"
        f"工艺模块信息(JSON)：{payload}\n"
    )

    provider = str(settings.llm_provider or "openai_compatible").strip().lower()

    # Provider A: DashScope (百炼) native API
    # POST {base_url}/api/v1/services/aigc/text-generation/generation
    # Payload:
    # {
    #   "model": "qwen-plus",
    #   "input": {"messages":[...]},
    #   "parameters": {"result_format":"message","temperature":0.2}
    # }
    if provider in {"dashscope", "bailian"}:
        url = settings.llm_base_url.rstrip("/") + "/api/v1/services/aigc/text-generation/generation"
        headers = {
            "Authorization": f"Bearer {settings.llm_api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": settings.llm_model,
            "input": {
                "messages": [
                    {"role": "system", "content": "你是企业ERP工艺知识库助手。"},
                    {"role": "user", "content": prompt},
                ]
            },
            "parameters": {"result_format": "message", "temperature": 0.2},
        }
        try:
            with httpx.Client(timeout=settings.llm_timeout_seconds) as client:
                resp = client.post(url, headers=headers, json=body)
                resp.raise_for_status()
                data = resp.json() or {}
                out = data.get("output") or {}
                choices = out.get("choices") or data.get("choices") or []
                first = (choices[0] if choices else {}) or {}
                msg = first.get("message") or {}
                content = str(msg.get("content") or "").strip()
                if not content and out.get("text"):
                    content = str(out.get("text") or "").strip()
                if not content:
                    return _fallback_description(payload), "fallback"
                return content, "llm"
        except Exception:
            return _fallback_description(payload), "fallback"

    # Provider B: OpenAI-compatible
    url = settings.llm_base_url.rstrip("/") + "/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.llm_api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "model": settings.llm_model,
        "messages": [
            {"role": "system", "content": "你是企业ERP工艺知识库助手。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
    }

    try:
        with httpx.Client(timeout=settings.llm_timeout_seconds) as client:
            resp = client.post(url, headers=headers, json=body)
            resp.raise_for_status()
            data = resp.json()
            content = ((data.get("choices") or [{}])[0].get("message", {}) or {}).get("content", "")
            content = str(content or "").strip()
            if not content:
                return _fallback_description(payload), "fallback"
            return content, "llm"
    except Exception:
        return _fallback_description(payload), "fallback"


