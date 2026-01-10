from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from .. import models
from . import bundle_template_service, line_variant_service, product_model_service, spec_parser_service


def _parse_bundle_scoped_phrases(spec_text: str) -> List[Dict[str, Any]]:
    """
    Parse customer-facing spec_text to extract scoped phrases with counts, e.g.:
      - 材质:雪尼尔2个(30*30)
      - 枕芯：PP棉3个

    Returns list of dicts: {key, value, qty}
    Notes:
      - Dimensions in parentheses are ignored (template defines size).
      - Bundle code tokens (B:/BUNDLE:) are ignored.
    """
    import re

    text = str(spec_text or "")
    # remove bundle codes to avoid confusing parsing
    text = re.sub(r"(?:BUNDLE:|B:)[A-Z0-9]{4,16}", "", text, flags=re.IGNORECASE)
    # normalize separators
    text = text.replace("；", ";").replace("，", ",").replace("＋", "+")
    parts = re.split(r"[+;,/|、\n]+", text)

    out: List[Dict[str, Any]] = []
    # key:valueN个(...)  or valueN个(...) (key optional)
    pat = re.compile(
        r"^\s*(?:(?P<key>材质|枕芯)\s*[:：]\s*)?(?P<value>.+?)(?P<qty>\d+)\s*(?:个|只|条|件|套)?\s*(?:[（(].*[）)])?\s*$"
    )
    for raw in parts:
        s = str(raw or "").strip()
        if not s:
            continue
        m = pat.match(s)
        if not m:
            continue
        key = str(m.group("key") or "").strip() or None
        value = str(m.group("value") or "").strip()
        # clean trailing punctuation
        value = value.strip("：:，,;； ")
        try:
            qty = int(m.group("qty"))
        except Exception:
            continue
        if not value or qty <= 0:
            continue
        out.append({"key": key, "value": value, "qty": qty})
    return out


def generate_bom(
    db: Session,
    *,
    spec_text: str,
    model_version_id: Optional[str],
    sku_code: Optional[str],
    quantity: Optional[Decimal],
    include_disabled_variants: bool = False,
) -> Dict[str, Any]:
    version = _resolve_version(db, model_version_id=model_version_id, sku_code=sku_code)
    model = db.get(models.ProductModel, version.model_id)
    if not model or model.is_archived:
        raise ValueError("产品模型不存在或已归档")

    spec_result = spec_parser_service.parse_spec(spec_text or "")
    # IMPORTANT:
    # - Keep parse_spec output "pure" (only from spec_text) for audit/replay.
    # - But when matching variants, add binding context tokens to avoid cross-model false hits.
    #   These tokens are NOT required to exist in spec_text:
    #   - MODEL:<model_code> (e.g., MODEL:PI5)
    #   - BOUND_VERSION:<version_id>
    #   - SKU:<sku_code>
    runtime_tokens = _augment_runtime_tokens(
        list(spec_result.get("tokens") or []),
        sku_code=sku_code,
        model_code=getattr(model, "model_code", None),
        bound_version_id=version.id,
    )
    measurement = _build_measurement(version, spec_result, quantity)
    metrics = _build_metrics(spec_result, measurement)
    diameter_cm = metrics.get("diameter_cm")

    base_lines = product_model_service.list_version_material_lines(db, version.id)
    process_lines = product_model_service.list_version_process_lines(db, version.id)
    variants = line_variant_service.list_variants(db, version_id=version.id)
    variants_by_line: Dict[str, List[models.ProductModelLineVariant]] = {}
    for variant in variants:
        variants_by_line.setdefault(variant.base_line_id, []).append(variant)

    final_lines: List[Dict[str, Any]] = []
    trace_hits: List[Dict[str, Any]] = []
    line_counter = 0

    def _push(line: Dict[str, Any]) -> None:
        nonlocal line_counter
        line_counter += 1
        line["line_index"] = line_counter
        final_lines.append(line)

    for row in base_lines:
        variant_rules = variants_by_line.get(row.id, [])
        # Ensure stable and intuitive precedence:
        # - primary: higher priority first
        # - when diameter is present in spec, evaluate diameter rules before width/height rules,
        #   otherwise a square rule (W=H) can shadow a diameter rule due to stop_on_hit.
        # - finally: older rules first for determinism
        if variant_rules:
            def _is_diameter_rule(v: models.ProductModelLineVariant) -> bool:
                cond = v.conditions_json or {}
                return "diameter_between" in cond

            variant_rules = sorted(
                variant_rules,
                key=lambda v: (
                    -(v.priority or 0),
                    0 if (diameter_cm is not None and _is_diameter_rule(v)) else 1,
                    v.created_at,
                ),
            )
        keep_base = True
        replacement_lines: List[Dict[str, Any]] = []
        additions: List[Dict[str, Any]] = []

        for variant in variant_rules:
            if not variant.enabled and not include_disabled_variants:
                trace_hits.append(
                    {
                        "variant_id": variant.id,
                        "base_line_id": row.id,
                        "action": variant.action,
                        "matched": False,
                        "reason": "disabled",
                    }
                )
                continue

            matched = line_variant_service.evaluate_conditions(
                variant,
                tokens=runtime_tokens,
                metrics=metrics,
            )
            trace_entry = {
                "variant_id": variant.id,
                "base_line_id": row.id,
                "action": variant.action,
                "matched": matched,
            }
            if matched:
                produced = [
                    _materialize_variant_item(
                        item,
                        base_row=row,
                        measurement=measurement,
                        variant_id=variant.id,
                        base_line_id=row.id,
                    )
                    for item in variant.items or []
                ]
                trace_entry["produced_item_ids"] = [line["variant_item_id"] for line in produced]
                if variant.action in ("replace_bundle", "replace_self"):
                    keep_base = False
                    replacement_lines = produced
                    trace_entry["effect"] = f"replace_with_{len(produced)}"
                elif variant.action == "remove_self":
                    keep_base = False
                    replacement_lines = []
                    trace_entry["effect"] = "removed"
                elif variant.action == "add_siblings":
                    additions.extend(produced)
                    trace_entry["effect"] = f"added_{len(produced)}"
                trace_hits.append(trace_entry)
                if variant.stop_on_hit:
                    break
            else:
                trace_entry["effect"] = "skipped"
                trace_hits.append(trace_entry)

        if keep_base:
            _push(_materialize_base_line(row, measurement=measurement))
            for add_line in additions:
                _push(add_line)
        else:
            for repl_line in replacement_lines:
                _push(repl_line)
            for add_line in additions:
                _push(add_line)

    # Fill missing unit_of_measure (common data issue in base lines):
    # - If version line unit_of_measure is empty, try fallback to material master unit by material_ref_id.
    # - This improves preview readability and reduces downstream confusion without mutating stored lines.
    _fill_missing_units(db, final_lines)

    costing = _attach_costing(db, final_lines, process_lines=process_lines, measurement=measurement)
    inventory = _build_inventory_lines(db, final_lines)

    return {
        "final_material_lines": final_lines,
        "trace": {
            "model_id": model.id,
            "model_version_id": version.id,
            "sku_code": sku_code,
            "parsed": spec_result,
            "runtime_tokens": runtime_tokens,
            "measurement_mm": measurement,
            "matched_variants": trace_hits,
            "costing": costing,
            "inventory": inventory,
        },
    }


def generate_bom_by_spec(
    db: Session,
    *,
    spec_text: str,
    sku_code: Optional[str],
    include_disabled_variants: bool = False,
    return_components: bool = False,
) -> Dict[str, Any]:
    """
    Generate BOM by spec_text tokens (high-priority, customer-facing).

    Current supported token(s):
    - BUNDLE:<code> => load bundle template and generate multi-model merged BOM.
    """
    spec_result = spec_parser_service.parse_spec(spec_text or "")
    tokens = [str(x) for x in (spec_result.get("tokens") or [])]
    bundle_token = next(
        (
            t
            for t in tokens
            if str(t).upper().startswith("B:")
            or str(t).upper().startswith("BUNDLE:")
            or str(t).upper().startswith("B-")
        ),
        None,
    )
    if not bundle_token:
        raise ValueError("交易规格未包含套装编码（B:CODE / BUNDLE:CODE / B-CODE-XX / B-XXXXXX）")
    # Accept:
    # - "B:CODE" / "B:CODE:A" / "B:CODE:AA" / "BUNDLE:CODE" / "BUNDLE:CODE:A" / "BUNDLE:CODE:AA"
    # - "B-CODE" / "B-CODE-A" / "B-CODE-AA"
    # - "B-XXXX" / "B-XXXXAA" (new short form, CODE length fixed to 4; selector is 2 letters)
    # Only CODE is used to load template;
    # selector is parsed from spec_text below.
    raw_bt = str(bundle_token).strip()
    if raw_bt.upper().startswith("B-"):
        # Dash forms:
        # - legacy: B-CODE / B-CODE-A / B-CODE-AA
        # - new short: B-XXXX / B-XXXXAA (CODE length fixed to 4; selector 2 letters)
        rest = raw_bt[2:].strip()  # after "B-"
        if "-" in rest:
            # B-CODE-A
            code = rest.split("-", 1)[0].strip().upper()
        else:
            # B-XXXXAA: treat as CODE=first 4 if len==6.
            # Also accept legacy 1-letter selector form (len==5) for backward compatibility.
            code = (rest[:4] if len(rest) in (5, 6) else rest).strip().upper()
    else:
        # Colon forms: B:CODE(:A) / BUNDLE:CODE(:A)
        rest = raw_bt.split(":", 1)[1].strip()
        code = rest.split(":", 1)[0].strip().upper()
    if not code:
        raise ValueError("套装编码非法")

    tpl = bundle_template_service.get_by_code(db, code)
    tpl_meta = tpl.metadata_json or {}
    components = list(tpl.components_json or [])

    # Optional bundle suffix:
    # - (B:CODE:A) / (BUNDLE:CODE:A) / "B:CODE:A"
    # - (B-CODE-A) / "B-CODE-A"
    # - A/B/C... means selecting the 1st/2nd/3rd... phrase preset row directly (NOT "Auto").
    #   This allows operators to keep customer-facing text unchanged, while mapping is driven by template presets.
    import re

    _mode_match = re.search(
        rf"(?:BUNDLE:|B:){re.escape(code)}(?::(?P<sel_colon>[A-Za-z]{{1,2}}))?"
        rf"|(?:\bB-{re.escape(code)}-(?P<sel_dash>[A-Za-z]{{1,2}})\b)"
        rf"|(?:\bB-{re.escape(code)}(?P<sel_short>[A-Za-z]{{2}})\b)",
        str(spec_text or ""),
        flags=re.IGNORECASE,
    )
    bundle_selector = (
        (str(_mode_match.group("sel_colon") or "").strip().upper() if _mode_match else "")
        or (str(_mode_match.group("sel_dash") or "").strip().upper() if _mode_match else "")
        or (str(_mode_match.group("sel_short") or "").strip().upper() if _mode_match else "")
        or ""
    ) or None

    def _selector2_to_index(sel: str) -> Optional[int]:
        s = (sel or "").strip().upper()
        if len(s) != 2:
            return None
        if not ("A" <= s[0] <= "Z" and "A" <= s[1] <= "Z"):
            return None
        return (ord(s[0]) - ord("A")) * 26 + (ord(s[1]) - ord("A"))

    def _parse_qty_from_phrase(text: str) -> Optional[int]:
        import re

        s = str(text or "")
        m = re.search(r"(\d+)\s*(?:个|只|件)?", s)
        if not m:
            return None
        try:
            v = int(m.group(1))
            return v if v > 0 else None
        except Exception:
            return None

    forced_preset_index: Optional[int] = None
    forced_preset_selector: Optional[str] = None
    if bundle_selector and len(bundle_selector) == 1 and "A" <= bundle_selector <= "Z":
        # Legacy 1-letter selector maps to index directly (A=0,B=1,...)
        forced_preset_index = ord(bundle_selector) - ord("A")
    elif bundle_selector and len(bundle_selector) == 2:
        forced_preset_selector = bundle_selector

    # New mode: when selector is present, allow phrase preset row to carry a full component list.
    # This supports "同模型多尺寸/多数量" (e.g. 照片墙) without relying on customer-facing text parsing.
    if forced_preset_selector or isinstance(forced_preset_index, int):
        raw_presets = tpl_meta.get("phrase_presets")
        presets = raw_presets if isinstance(raw_presets, list) else []
        preset = None
        if forced_preset_selector:
            for p in presets:
                if isinstance(p, dict) and str(p.get("selector") or "").strip().upper() == forced_preset_selector:
                    preset = p
                    break
            # Backward compatibility: old presets without selector field can still be addressed by AA/AB... as index.
            if preset is None:
                idx = _selector2_to_index(forced_preset_selector)
                if isinstance(idx, int) and 0 <= idx < len(presets):
                    preset = presets[idx]
        elif isinstance(forced_preset_index, int) and 0 <= forced_preset_index < len(presets):
            preset = presets[forced_preset_index]
        if preset is not None and isinstance(preset, dict) and isinstance(preset.get("components"), list):
            comps_raw = preset.get("components") or []
            comps_new: List[Dict[str, Any]] = []
            for i, c in enumerate(comps_raw):
                if not isinstance(c, dict):
                    continue
                vid = str(c.get("model_version_id") or "").strip()
                if not vid:
                    raise ValueError(f"短语预设组件缺少 model_version_id：selector={bundle_selector} idx={i}")
                # Keep only fields used by generate_bom_multi_bundle / downstream generate_bom.
                # width_mm/height_mm/quantity are required for actual generation.
                comps_new.append(
                    {
                        "model_version_id": vid,
                        "width_mm": c.get("width_mm") or c.get("width") or 0,
                        "height_mm": c.get("height_mm") or c.get("height") or 0,
                        "quantity": c.get("quantity") or 1,
                        "spec_text": c.get("spec_text") or "",
                        "tokens": c.get("tokens") or [],
                        # Optional: force a specific line-variant per base_line_id (used by bundle template UI "指定(强制命中)")
                        # Shape: { "<base_line_id>": "<variant_id>" }
                        "force_variant_by_base_line": c.get("force_variant_by_base_line") or {},
                    }
                )
            if not comps_new:
                raise ValueError(f"短语预设未配置组件行：{code}:{bundle_selector}")
            # Use these components as the generation source for selector mode.
            components = comps_new

    if not components:
        raise ValueError(f"套装模板无组件：{code}")

    def _apply_phrase_presets(
        *,
        tpl_meta: Dict[str, Any],
        spec_text: str,
        components: List[Dict[str, Any]],
        forced_index: Optional[int] = None,
        forced_selector: Optional[str] = None,
    ) -> tuple[List[Dict[str, Any]], List[str], List[Dict[str, Any]], bool]:
        """
        Phrase presets (短语预设):
        - contains match, longer phrase first
        - apply mappings group (字段/词/目标组件) when phrase hits
        Returns: (components_override_by_index, remove_tokens, trace_entries, matched_any)
        """
        raw = tpl_meta.get("phrase_presets")
        presets = raw if isinstance(raw, list) else []
        items: List[Dict[str, Any]] = []
        for i_p, p in enumerate(presets):
            if not isinstance(p, dict):
                continue
            phrase = str(p.get("phrase") or "").strip()
            if not phrase:
                continue
            sel = str(p.get("selector") or "").strip().upper() or None
            enabled = p.get("enabled")
            enabled = bool(enabled) if enabled is not None else True
            mappings = p.get("mappings")
            mappings = mappings if isinstance(mappings, list) else []

            # Backward compatibility: old format uses tokens + target_component_index
            if not mappings:
                tci = p.get("target_component_index")
                try:
                    tci = int(tci) if tci is not None else None
                except Exception:
                    tci = None
                tokens = p.get("tokens") or p.get("inject_tokens") or []
                tok_list = [str(x).strip() for x in tokens] if isinstance(tokens, list) else []
                tok_list = [x for x in tok_list if x]
                if tci is not None and tok_list:
                    for t in tok_list:
                        if ":" in t:
                            k, v = t.split(":", 1)
                            mappings.append({"match_key": k.strip() or None, "match_value": v.strip(), "target_component_index": tci})
                        else:
                            mappings.append({"match_key": None, "match_value": t, "target_component_index": tci})

            clean_mappings: List[Dict[str, Any]] = []
            for m in mappings:
                if not isinstance(m, dict):
                    continue
                mk = str(m.get("match_key") or m.get("key") or "").strip() or None
                mv = str(m.get("match_value") or m.get("value") or "").strip()
                tci = m.get("target_component_index")
                try:
                    tci = int(tci) if tci is not None else None
                except Exception:
                    tci = None
                if not mv or tci is None:
                    continue
                clean_mappings.append({"match_key": mk, "match_value": mv, "target_component_index": tci})

            if not clean_mappings:
                continue

            qty = _parse_qty_from_phrase(phrase)
            items.append(
                {
                    "phrase": phrase,
                    "selector": sel,
                    "enabled": enabled,
                    "raw_index": i_p,
                    "quantity": qty,
                    "mappings": clean_mappings,
                }
            )

        # longer phrase first (only for contains-match mode)
        items.sort(key=lambda x: len(str(x.get("phrase") or "")), reverse=True)
        matched_any = False
        # index -> {tokens:set, best_phrase_len:int, qty:int|None}
        per_index: Dict[int, Dict[str, Any]] = {}
        trace_entries: List[Dict[str, Any]] = []
        remove_tokens: List[str] = []
        s = str(spec_text or "")

        # Forced selection mode:
        # - preferred: choose preset by its stable selector (AA/AB/...), no order shift.
        # - legacy: forced_index (A=0,B=1,...) for old one-letter selectors.
        if forced_selector:
            it = next((x for x in items if x.get("selector") == forced_selector), None)
            if it is None:
                idx = _selector2_to_index(forced_selector)
                it = items[idx] if isinstance(idx, int) and 0 <= idx < len(items) else None
            if not it or not bool(it.get("enabled", True)):
                trace_entries = [{"selector": forced_selector, "matched": False, "reason": "forced_selector_not_found_or_disabled"}]
                return [], [], trace_entries, False
        elif isinstance(forced_index, int):
            if forced_index < 0 or forced_index >= len(items):
                trace_entries = [{"selector": forced_index, "matched": False, "reason": "forced_index_out_of_range"}]
                return [], [], trace_entries, False
            it = items[forced_index]
            phrase = str(it["phrase"])
            matched_any = True
            mappings = it.get("mappings") or []
            uniq_targets: set[int] = set()
            injected_tokens_this_phrase: List[str] = []
            for m in mappings:
                try:
                    idx = int(m.get("target_component_index"))
                except Exception:
                    continue
                if idx < 0 or idx >= len(components):
                    continue
                uniq_targets.add(idx)
                mk = str(m.get("match_key") or "").strip()
                mv = str(m.get("match_value") or "").strip()
                if not mv:
                    continue
                token_kv = f"{mk}:{mv}" if mk else mv
                toks = [token_kv, mv]
                injected_tokens_this_phrase.extend(toks)
                remove_tokens.extend(toks)
                rec = per_index.get(idx) or {"tokens": set(), "best_phrase_len": 0, "quantity": None}
                for t in toks:
                    rec["tokens"].add(t)
                rec["best_phrase_len"] = len(phrase) if phrase else 0
                rec["quantity"] = it.get("quantity")
                per_index[idx] = rec

            qty_applies = (it.get("quantity") if len(uniq_targets) == 1 else None)
            trace_entries.append(
                {
                    "selector": forced_selector or forced_index,
                    "phrase": phrase,
                    "matched": True,
                    "forced": True,
                    "mappings_count": len(mappings),
                    "affected_components": sorted(list(uniq_targets)),
                    "quantity": qty_applies,
                    "tokens": list(dict.fromkeys([t for t in injected_tokens_this_phrase if t])),
                }
            )
        else:
            for it in items:
                if not bool(it.get("enabled", True)):
                    continue
                phrase = str(it["phrase"])
                if phrase and phrase in s:
                    matched_any = True
                    mappings = it.get("mappings") or []
                    affected: List[int] = []
                    uniq_targets: set[int] = set()
                    injected_tokens_this_phrase: List[str] = []

                    for m in mappings:
                        try:
                            idx = int(m.get("target_component_index"))
                        except Exception:
                            continue
                        if idx < 0 or idx >= len(components):
                            continue
                        uniq_targets.add(idx)
                        mk = str(m.get("match_key") or "").strip()
                        mv = str(m.get("match_value") or "").strip()
                        if not mv:
                            continue
                        token_kv = f"{mk}:{mv}" if mk else mv
                        toks = [token_kv, mv]
                        injected_tokens_this_phrase.extend(toks)
                        remove_tokens.extend(toks)
                        rec = per_index.get(idx) or {"tokens": set(), "best_phrase_len": 0, "quantity": None}
                        for t in toks:
                            rec["tokens"].add(t)
                        # keep longer phrase's qty (longer first)
                        if len(phrase) >= int(rec.get("best_phrase_len") or 0):
                            rec["best_phrase_len"] = len(phrase)
                            rec["quantity"] = it.get("quantity")
                        per_index[idx] = rec
                        affected.append(idx)

                    # If this phrase maps to exactly one component, allow qty override
                    qty_applies = (it.get("quantity") if len(uniq_targets) == 1 else None)
                    trace_entries.append(
                        {
                            "phrase": phrase,
                            "matched": True,
                            "mappings_count": len(mappings),
                            "affected_components": sorted(list(uniq_targets)),
                            "quantity": qty_applies,
                            "tokens": list(dict.fromkeys([t for t in injected_tokens_this_phrase if t])),
                        }
                    )
                else:
                    trace_entries.append({"phrase": str(it.get("phrase") or ""), "matched": False})

        scoped_by_index: List[Dict[str, Any]] = []
        for idx, rec in per_index.items():
            base_raw = components[idx]
            if not isinstance(base_raw, dict):
                continue
            base_def = dict(base_raw)
            qty = rec.get("quantity")
            if isinstance(qty, int) and qty > 0:
                base_def["quantity"] = qty
            base_tokens = []
            if isinstance(base_def.get("tokens"), list):
                base_tokens = [str(x).strip() for x in base_def.get("tokens") if str(x).strip()]
            injected = sorted([str(x).strip() for x in (rec.get("tokens") or set()) if str(x).strip()])
            base_def["tokens"] = base_tokens + injected
            scoped_by_index.append({"index": idx, "component": base_def})

        return scoped_by_index, remove_tokens, trace_entries, matched_any

    # Apply shared tokens from the (single) customer-facing spec_text to ALL components.
    # IMPORTANT: do NOT let spec_text dimensions override component measurement_mm.
    # So we inject shared tokens via component.tokens, and set component.spec_text empty for per-component parsing.
    shared_tokens = [str(x) for x in (spec_result.get("tokens") or []) if str(x).strip()]
    # remove bundle code tokens themselves from shared tokens (avoid accidental rule matching)
    shared_tokens = [t for t in shared_tokens if not t.upper().startswith("B:") and not t.upper().startswith("BUNDLE:")]

    # Merge template-level shared trigger text (applies to all components)
    tpl_shared = str(tpl_meta.get("shared_trigger_text") or "").strip()
    if tpl_shared:
        tpl_shared_parsed = spec_parser_service.parse_spec(tpl_shared)
        tpl_shared_tokens = [str(x) for x in (tpl_shared_parsed.get("tokens") or []) if str(x).strip()]
        tpl_shared_tokens = [t for t in tpl_shared_tokens if not t.upper().startswith("B:") and not t.upper().startswith("BUNDLE:")]
        shared_tokens = shared_tokens + tpl_shared_tokens

    # --- Phrase presets (recommended): contains match, longer-first ---
    phrase_scoped, phrase_remove_tokens, phrase_trace, phrase_matched_any = _apply_phrase_presets(
        tpl_meta=tpl_meta,
        spec_text=spec_text,
        components=components,
        forced_index=forced_preset_index,
        forced_selector=forced_preset_selector,
    )
    if phrase_remove_tokens:
        rm2 = {str(x).strip().lower() for x in phrase_remove_tokens if str(x).strip()}
        shared_tokens = [t for t in shared_tokens if str(t).strip().lower() not in rm2]

    # --- Bundle lexicon (scoped mapping; avoid global token broadcast conflicts) ---
    # If any phrase preset matched, we intentionally DO NOT apply global lexicon_rules (avoid "too flexible").
    lex_rules = [] if phrase_matched_any else tpl_meta.get("lexicon_rules")
    scoped_phrases = _parse_bundle_scoped_phrases(spec_text)
    lex_rules = lex_rules if isinstance(lex_rules, list) else []
    # index rules by (key,value,target_component_index / target_label)
    indexed_rules: List[Dict[str, Any]] = []
    for r in lex_rules:
        if not isinstance(r, dict):
            continue
        key = str(r.get("match_key") or r.get("key") or "").strip() or None
        value = str(r.get("match_value") or r.get("value") or "").strip()
        target_label = str(r.get("target_label") or "").strip() or None
        target_component_index = r.get("target_component_index")
        try:
            target_component_index = int(target_component_index) if target_component_index is not None else None
        except Exception:
            target_component_index = None
        if not value or (target_component_index is None and not target_label):
            continue
        indexed_rules.append(
            {
                "match_key": key,
                "match_value": value,
                "target_label": target_label,
                "target_component_index": target_component_index,
            }
        )

    # Determine which labels can be scoped; enforce uniqueness to avoid ambiguous splits
    label_to_components: Dict[str, List[Dict[str, Any]]] = {}
    for c in components:
        if not isinstance(c, dict):
            continue
        lab = str(c.get("label") or "").strip()
        if not lab:
            continue
        label_to_components.setdefault(lab, []).append(c)

    scoped_components_by_label: Dict[str, List[Dict[str, Any]]] = {}
    scoped_components_by_index: Dict[int, List[Dict[str, Any]]] = {}
    scoped_remove_tokens: List[str] = []

    # seed phrase-scoped overrides (index-based)
    if phrase_scoped:
        for item in phrase_scoped:
            try:
                idx = int(item.get("index"))
            except Exception:
                continue
            comp = item.get("component")
            if isinstance(idx, int) and isinstance(comp, dict):
                scoped_components_by_index.setdefault(idx, []).append(comp)
                # also remove tokens from shared broadcast
                for t in (comp.get("tokens") or []) if isinstance(comp.get("tokens"), list) else []:
                    if str(t).strip():
                        scoped_remove_tokens.append(str(t).strip())

    if indexed_rules and scoped_phrases:
        for ph in scoped_phrases:
            ph_key = ph.get("key")
            ph_value = str(ph.get("value") or "").strip()
            ph_qty = int(ph.get("qty") or 0)
            if not ph_value or ph_qty <= 0:
                continue
            for rule in indexed_rules:
                if rule["match_value"] != ph_value:
                    continue
                if rule["match_key"] is not None and ph_key is not None and rule["match_key"] != ph_key:
                    continue
                if rule["match_key"] is not None and ph_key is None:
                    # rule expects key but phrase lacks it
                    continue
                target_idx = rule.get("target_component_index")
                target_label = rule.get("target_label")

                # New mode: target_component_index (recommended)
                if isinstance(target_idx, int):
                    if target_idx < 0 or target_idx >= len(components):
                        raise ValueError(f"套装字符映射目标组件索引非法：{target_idx}")
                    base_raw = components[target_idx]
                    if not isinstance(base_raw, dict):
                        raise ValueError(f"套装模板组件非法：components[{target_idx}]")
                    base_def = dict(base_raw)
                    target_key = ("idx", target_idx)
                else:
                    # Legacy mode: target_label (must be unique)
                    base_defs = label_to_components.get(str(target_label or "")) or []
                    if not base_defs:
                        raise ValueError(f"套装字符映射未找到目标组件 label：{str(target_label or '')}")
                    if len(base_defs) != 1:
                        raise ValueError(
                            f"套装组件 label 必须唯一（{str(target_label or '')} 出现 {len(base_defs)} 次），否则无法按 label 分配/拆分"
                        )
                    base_def = dict(base_defs[0])
                    target_key = ("label", str(target_label or ""))

                # Inject tokens for this scoped phrase:
                # - prefer key:value token (e.g., 材质:雪尼尔)
                # - also include raw value for backward compatibility (e.g., 雪尼尔)
                token_key = ph_key or ""
                token_kv = f"{token_key}:{ph_value}" if token_key else ph_value
                scoped_tokens = [token_kv, ph_value]
                scoped_remove_tokens.extend(scoped_tokens)

                base_def["quantity"] = ph_qty
                base_tokens = []
                if isinstance(base_def.get("tokens"), list):
                    base_tokens = [str(x).strip() for x in base_def.get("tokens") if str(x).strip()]
                base_def["tokens"] = base_tokens + scoped_tokens
                if target_key[0] == "idx":
                    scoped_components_by_index.setdefault(int(target_key[1]), []).append(base_def)
                else:
                    scoped_components_by_label.setdefault(str(target_key[1]), []).append(base_def)

    # Remove scoped tokens from shared tokens to avoid global broadcast conflicts
    if scoped_remove_tokens:
        rm = {str(x).strip().lower() for x in scoped_remove_tokens if str(x).strip()}
        shared_tokens = [t for t in shared_tokens if str(t).strip().lower() not in rm]

    comps2: List[Dict[str, Any]] = []
    scoped_labels_done: set[str] = set()
    for i, c in enumerate(components):
        if not isinstance(c, dict):
            raise ValueError(f"套装模板组件非法：components[{i}]")
        c2 = dict(c)

        # If lexicon produced scoped components for this index, replace this row by scoped ones
        if i in scoped_components_by_index:
            for sc in scoped_components_by_index[i]:
                comps2.append(sc)
            continue

        # If lexicon produced scoped components for this label, replace originals by scoped ones
        label = str(c2.get("label") or "").strip()
        if label and label in scoped_components_by_label:
            # only append once per label (skip other originals with same label)
            if label in scoped_labels_done:
                continue
            for sc in scoped_components_by_label[label]:
                comps2.append(sc)
            scoped_labels_done.add(label)
            continue

        # Treat template's per-component spec_text as "extra trigger words" only (no size parsing).
        extra_tokens: List[str] = []
        extra_spec = str(c2.get("spec_text") or "").strip()
        if extra_spec:
            extra_parsed = spec_parser_service.parse_spec(extra_spec)
            extra_tokens = [str(x) for x in (extra_parsed.get("tokens") or []) if str(x).strip()]
        tokens = []
        if isinstance(c2.get("tokens"), list):
            tokens = [str(x).strip() for x in c2.get("tokens") if str(x).strip()]
        # dedup keep order
        seen = set()
        merged_tokens: List[str] = []
        for t in (shared_tokens + extra_tokens + tokens):
            k = t.lower()
            if k in seen:
                continue
            merged_tokens.append(t)
            seen.add(k)
        c2["tokens"] = merged_tokens
        # Clear spec_text for component-level parsing to avoid dimension contamination.
        c2["spec_text"] = ""
        comps2.append(c2)

    res = generate_bom_multi_bundle(
        db,
        sku_code=sku_code,
        components=comps2,
        include_disabled_variants=include_disabled_variants,
    )
    merged = res.get("merged") or {}
    if not isinstance(merged, dict):
        raise ValueError("合并器返回异常")
    trace = merged.get("trace") if isinstance(merged.get("trace"), dict) else {}
    trace = dict(trace)
    trace["bundle_code"] = f"B:{code}"
    trace["bundle_code_legacy"] = f"BUNDLE:{code}"
    trace["bundle_template_id"] = tpl.id
    trace["bundle_template_name"] = tpl.name
    if phrase_trace:
        trace["phrase_presets"] = phrase_trace
    trace["parsed"] = spec_result  # overwrite parsed to be the original spec parse result
    merged["trace"] = trace
    if return_components:
        # Keep the same enriched merged trace, and return full multi-bundle result for debugging.
        res["merged"] = merged
        return res
    return merged


def generate_bom_bundle(
    db: Session,
    *,
    model_version_id: str,
    sku_code: Optional[str],
    components: List[Dict[str, Any]],
    include_disabled_variants: bool = False,
) -> Dict[str, Any]:
    """
    Bundle/set wrapper:
    - components provide explicit width_mm/height_mm/quantity.
    - spec_text/tokens are optional and only used for variant matching.
    - output includes per-component BOM + merged BOM summary.
    """
    if not components:
        raise ValueError("components 不能为空")

    version = _resolve_version(db, model_version_id=model_version_id, sku_code=None)
    model = db.get(models.ProductModel, version.model_id)
    if not model or model.is_archived:
        raise ValueError("产品模型不存在或已归档")

    base_lines = product_model_service.list_version_material_lines(db, version.id)
    process_lines = product_model_service.list_version_process_lines(db, version.id)
    variants = line_variant_service.list_variants(db, version_id=version.id)
    variants_by_line: Dict[str, List[models.ProductModelLineVariant]] = {}
    for variant in variants:
        variants_by_line.setdefault(variant.base_line_id, []).append(variant)

    component_results: List[Dict[str, Any]] = []
    merged_material_lines: List[Dict[str, Any]] = []
    merged_inventory_lines: List[Dict[str, Any]] = []

    # cost totals (apply overhead once on sum)
    material_cost_total = Decimal("0")
    process_cost_total = Decimal("0")
    overhead_rate = Decimal("0.3")

    def _d(v: Any) -> Decimal:
        if v in (None, ""):
            return Decimal("0")
        if isinstance(v, Decimal):
            return v
        try:
            return Decimal(str(v))
        except Exception:
            return Decimal("0")

    def _merge_material_lines(lines: List[Dict[str, Any]]) -> None:
        nonlocal merged_material_lines
        agg: Dict[str, Dict[str, Any]] = {}
        for r in lines or []:
            kind = str(r.get("material_kind") or "real")
            ref = str(r.get("material_ref_id") or "")
            code = str(r.get("material_code") or "")
            name = str(r.get("material_name") or "")
            uom = str(r.get("unit_of_measure") or "")
            method = str(r.get("calculation_method") or "count")
            key = "|".join([kind, ref or code or name, method, uom])
            cur = agg.get(key)
            if not cur:
                cur = dict(r)
                cur["computed_quantity"] = _d(r.get("computed_quantity"))
                cur["line_cost"] = _d(r.get("line_cost"))
                agg[key] = cur
            else:
                cur["computed_quantity"] = _d(cur.get("computed_quantity")) + _d(r.get("computed_quantity"))
                cur["line_cost"] = _d(cur.get("line_cost")) + _d(r.get("line_cost"))
        merged_material_lines = list(agg.values())
        # assign stable line_index
        merged_material_lines.sort(key=lambda x: str(x.get("material_code") or x.get("material_name") or ""))
        for i, r in enumerate(merged_material_lines, 1):
            r["line_index"] = i

    def _merge_inventory_lines(lines: List[Dict[str, Any]]) -> None:
        nonlocal merged_inventory_lines
        agg: Dict[str, Dict[str, Any]] = {}
        for r in lines or []:
            code = str(r.get("material_code") or r.get("virtual_code") or "")
            mid = str(r.get("material_id") or "")
            name = str(r.get("material_name") or r.get("virtual_name") or "")
            unit = str(r.get("unit_of_measure") or r.get("unit") or "")
            key = "|".join([mid or code or name, unit])
            cur = agg.get(key)
            if not cur:
                cur = dict(r)
                cur["quantity"] = _d(r.get("quantity"))
                agg[key] = cur
            else:
                cur["quantity"] = _d(cur.get("quantity")) + _d(r.get("quantity"))
        merged_inventory_lines = list(agg.values())
        merged_inventory_lines.sort(key=lambda x: str(x.get("material_code") or x.get("virtual_code") or ""))

    for idx, comp in enumerate(components):
        width_mm = _d(comp.get("width_mm"))
        height_mm = _d(comp.get("height_mm"))
        qty = _d(comp.get("quantity") or Decimal("1"))
        if width_mm <= 0 or height_mm <= 0 or qty <= 0:
            raise ValueError(f"components[{idx}] 尺寸/数量非法：width_mm/height_mm/quantity 必须 > 0")

        # Optional per-component forced variant mapping: base_line_id -> variant_id
        force_map_raw = comp.get("force_variant_by_base_line") or {}
        force_map: Dict[str, str] = {}
        if isinstance(force_map_raw, dict):
            for k, v in force_map_raw.items():
                kk = str(k or "").strip()
                vv = str(v or "").strip()
                if kk and vv:
                    force_map[kk] = vv

        spec_text = str(comp.get("spec_text") or "").strip()
        spec_result = spec_parser_service.parse_spec(spec_text)
        extra_tokens = []
        if isinstance(comp.get("tokens"), list):
            extra_tokens = [str(x).strip() for x in comp.get("tokens") if str(x).strip()]
        runtime_tokens = _augment_runtime_tokens(
            list(spec_result.get("tokens") or []) + extra_tokens,
            sku_code=sku_code,
            model_code=getattr(model, "model_code", None),
            bound_version_id=version.id,
        )
        measurement = {"width_mm": width_mm, "height_mm": height_mm, "quantity": qty}
        metrics = _build_metrics(spec_result, measurement)

        # Apply variants per line (mostly same as generate_bom)
        final_lines: List[Dict[str, Any]] = []
        trace_hits: List[Dict[str, Any]] = []
        line_counter = 0

        def _push(line: Dict[str, Any]) -> None:
            nonlocal line_counter
            line_counter += 1
            line["line_index"] = line_counter
            final_lines.append(line)

        for row in base_lines:
            variant_rules = variants_by_line.get(row.id, [])
            keep_base = True
            replacement_lines: List[Dict[str, Any]] = []
            additions: List[Dict[str, Any]] = []

            forced_variant_id = force_map.get(str(row.id))
            if forced_variant_id:
                forced_variant = next((v for v in variant_rules if str(v.id) == str(forced_variant_id)), None)
                if not forced_variant:
                    raise ValueError(f"components[{idx}] 强制命中失败：base_line_id={row.id} 未找到 variant_id={forced_variant_id}")
                if not forced_variant.enabled and not include_disabled_variants:
                    raise ValueError(f"components[{idx}] 强制命中失败：所选规则已禁用 variant_id={forced_variant_id}")

                produced = [
                    _materialize_variant_item(
                        item,
                        base_row=row,
                        measurement=measurement,
                        variant_id=forced_variant.id,
                        base_line_id=row.id,
                    )
                    for item in forced_variant.items or []
                ]
                trace_entry = {
                    "variant_id": forced_variant.id,
                    "base_line_id": row.id,
                    "action": forced_variant.action,
                    "matched": True,
                    "reason": "forced_by_bundle",
                }
                trace_entry["produced_item_ids"] = [line["variant_item_id"] for line in produced]
                if forced_variant.action in ("replace_bundle", "replace_self"):
                    keep_base = False
                    replacement_lines = produced
                    trace_entry["effect"] = f"replace_with_{len(produced)}"
                elif forced_variant.action == "remove_self":
                    keep_base = False
                    replacement_lines = []
                    trace_entry["effect"] = "removed"
                elif forced_variant.action == "add_siblings":
                    additions.extend(produced)
                    trace_entry["effect"] = f"added_{len(produced)}"
                trace_hits.append(trace_entry)
                # Forced selection always stops further evaluation for this base line.
                if keep_base:
                    _push(_materialize_base_line(row, measurement=measurement))
                    for add_line in additions:
                        _push(add_line)
                else:
                    for repl_line in replacement_lines:
                        _push(repl_line)
                    for add_line in additions:
                        _push(add_line)
                continue

            for variant in variant_rules:
                if not variant.enabled and not include_disabled_variants:
                    trace_hits.append(
                        {
                            "variant_id": variant.id,
                            "base_line_id": row.id,
                            "action": variant.action,
                            "matched": False,
                            "reason": "disabled",
                        }
                    )
                    continue

                matched = line_variant_service.evaluate_conditions(
                    variant,
                    tokens=runtime_tokens,
                    metrics=metrics,
                )
                trace_entry = {
                    "variant_id": variant.id,
                    "base_line_id": row.id,
                    "action": variant.action,
                    "matched": matched,
                }
                if matched:
                    produced = [
                        _materialize_variant_item(
                            item,
                            base_row=row,
                            measurement=measurement,
                            variant_id=variant.id,
                            base_line_id=row.id,
                        )
                        for item in variant.items or []
                    ]
                    trace_entry["produced_item_ids"] = [line["variant_item_id"] for line in produced]
                    if variant.action in ("replace_bundle", "replace_self"):
                        keep_base = False
                        replacement_lines = produced
                        trace_entry["effect"] = f"replace_with_{len(produced)}"
                    elif variant.action == "remove_self":
                        keep_base = False
                        replacement_lines = []
                        trace_entry["effect"] = "removed"
                    elif variant.action == "add_siblings":
                        additions.extend(produced)
                        trace_entry["effect"] = f"added_{len(produced)}"
                    trace_hits.append(trace_entry)
                    if variant.stop_on_hit:
                        break
                else:
                    trace_entry["effect"] = "skipped"
                    trace_hits.append(trace_entry)

            if keep_base:
                _push(_materialize_base_line(row, measurement=measurement))
                for add_line in additions:
                    _push(add_line)
            else:
                for repl_line in replacement_lines:
                    _push(repl_line)
                for add_line in additions:
                    _push(add_line)

        _fill_missing_units(db, final_lines)
        costing = _attach_costing(db, final_lines, process_lines=process_lines, measurement=measurement)
        inventory = _build_inventory_lines(db, final_lines)

        component_results.append(
            {
                "component_index": idx,
                "final_material_lines": final_lines,
                "trace": {
                    "model_id": model.id,
                    "model_version_id": version.id,
                    "sku_code": sku_code,
                    "parsed": spec_result,
                    "runtime_tokens": runtime_tokens,
                    "measurement_mm": measurement,
                    "matched_variants": trace_hits,
                    "costing": costing,
                    "inventory": inventory,
                },
            }
        )

        material_cost_total += _d(costing.get("material_cost_total"))
        process_cost_total += _d(costing.get("process_cost_total"))
        overhead_rate = _d(costing.get("overhead_rate") or overhead_rate)

        # merge accumulators
        _merge_material_lines((merged_material_lines or []) + final_lines)
        _merge_inventory_lines((merged_inventory_lines or []) + list((inventory or {}).get("inventory_lines") or []))

    # Bundle totals (overhead once)
    overhead_cost = (material_cost_total + process_cost_total) * overhead_rate
    total_cost = material_cost_total + process_cost_total + overhead_cost

    merged_costing = {
        "currency": "CNY",
        "material_cost_total": material_cost_total,
        "process_cost_total": process_cost_total,
        "overhead_rate": overhead_rate,
        "overhead_cost": overhead_cost,
        "total_cost": total_cost,
        "unit_cost": total_cost,  # per bundle (kit) default
        "process_lines": [],  # per-component kept in components.trace.costing.process_lines
    }
    merged_warnings: List[str] = []
    for r in component_results:
        inv = ((r.get("trace") or {}).get("inventory") or {}) if isinstance(r.get("trace"), dict) else {}
        ws = inv.get("warnings")
        if isinstance(ws, list):
            merged_warnings.extend([str(x) for x in ws if str(x)])
    merged_inventory = {
        "inventory_lines": merged_inventory_lines,
        "inventory_line_count": len(merged_inventory_lines),
        "warnings": merged_warnings[:50],
    }

    merged = {
        "final_material_lines": merged_material_lines,
        "trace": {
            "model_id": model.id,
            "model_version_id": version.id,
            "sku_code": sku_code,
            "bundle_components": [
                {
                    "index": r.get("component_index"),
                    "measurement_mm": (r.get("trace") or {}).get("measurement_mm"),
                    "tokens": (r.get("trace") or {}).get("runtime_tokens"),
                }
                for r in component_results
            ],
            "costing": merged_costing,
            "inventory": merged_inventory,
        },
    }
    return {"merged": merged, "components": component_results}


def generate_bom_multi_bundle(
    db: Session,
    *,
    sku_code: Optional[str],
    components: List[Dict[str, Any]],
    include_disabled_variants: bool = False,
) -> Dict[str, Any]:
    """
    Multi-model bundle wrapper:
    - components[i].model_version_id specifies which version to use for that component.
    - We group by model_version_id, run generate_bom_bundle per group, then merge group-level merged BOMs.
    """
    if not components:
        raise ValueError("components 不能为空")

    # group by version
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for idx, c in enumerate(components):
        vid = str(c.get("model_version_id") or "").strip()
        if not vid:
            raise ValueError(f"components[{idx}] 缺少 model_version_id")
        groups.setdefault(vid, []).append(c)

    group_results: List[Dict[str, Any]] = []
    all_component_results: List[Dict[str, Any]] = []

    def _d(v: Any) -> Decimal:
        if v in (None, ""):
            return Decimal("0")
        if isinstance(v, Decimal):
            return v
        try:
            return Decimal(str(v))
        except Exception:
            return Decimal("0")

    # merged aggregations across groups
    merged_material_lines: List[Dict[str, Any]] = []
    merged_inventory_lines: List[Dict[str, Any]] = []
    material_cost_total = Decimal("0")
    process_cost_total = Decimal("0")
    overhead_rate = Decimal("0.3")

    def _merge_material_lines(existing: List[Dict[str, Any]], incoming: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        agg: Dict[str, Dict[str, Any]] = {}
        for r in (existing or []) + (incoming or []):
            kind = str(r.get("material_kind") or "real")
            ref = str(r.get("material_ref_id") or "")
            code = str(r.get("material_code") or "")
            name = str(r.get("material_name") or "")
            uom = str(r.get("unit_of_measure") or "")
            method = str(r.get("calculation_method") or "count")
            key = "|".join([kind, ref or code or name, method, uom])
            cur = agg.get(key)
            if not cur:
                cur = dict(r)
                cur["computed_quantity"] = _d(r.get("computed_quantity"))
                cur["line_cost"] = _d(r.get("line_cost"))
                agg[key] = cur
            else:
                cur["computed_quantity"] = _d(cur.get("computed_quantity")) + _d(r.get("computed_quantity"))
                cur["line_cost"] = _d(cur.get("line_cost")) + _d(r.get("line_cost"))
        out = list(agg.values())
        out.sort(key=lambda x: str(x.get("material_code") or x.get("material_name") or ""))
        for i, r in enumerate(out, 1):
            r["line_index"] = i
        return out

    def _merge_inventory_lines(existing: List[Dict[str, Any]], incoming: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        agg: Dict[str, Dict[str, Any]] = {}
        for r in (existing or []) + (incoming or []):
            code = str(r.get("material_code") or r.get("virtual_code") or "")
            mid = str(r.get("material_id") or "")
            name = str(r.get("material_name") or r.get("virtual_name") or "")
            unit = str(r.get("unit_of_measure") or r.get("unit") or "")
            key = "|".join([mid or code or name, unit])
            cur = agg.get(key)
            if not cur:
                cur = dict(r)
                cur["quantity"] = _d(r.get("quantity"))
                agg[key] = cur
            else:
                cur["quantity"] = _d(cur.get("quantity")) + _d(r.get("quantity"))
        out = list(agg.values())
        out.sort(key=lambda x: str(x.get("material_code") or x.get("virtual_code") or ""))
        return out
    merged_inventory_warnings: List[str] = []

    for vid, comps in groups.items():
        # strip model_version_id before passing into single-version bundle generator
        comps2 = []
        for c in comps:
            c2 = dict(c)
            c2.pop("model_version_id", None)
            comps2.append(c2)
        res = generate_bom_bundle(
            db,
            model_version_id=vid,
            sku_code=sku_code,
            components=comps2,
            include_disabled_variants=include_disabled_variants,
        )
        merged = res.get("merged") or {}
        if not isinstance(merged, dict):
            merged = {}
        group_results.append({"model_version_id": vid, "merged": merged})
        all_component_results.extend(list(res.get("components") or []))

        # sum totals
        costing = ((merged.get("trace") or {}).get("costing") or {}) if isinstance(merged.get("trace"), dict) else {}
        material_cost_total += _d(costing.get("material_cost_total"))
        process_cost_total += _d(costing.get("process_cost_total"))
        overhead_rate = _d(costing.get("overhead_rate") or overhead_rate)

        merged_material_lines = _merge_material_lines(merged_material_lines, list(merged.get("final_material_lines") or []))
        inv = ((merged.get("trace") or {}).get("inventory") or {}) if isinstance(merged.get("trace"), dict) else {}
        inv_lines = (inv.get("inventory_lines") or []) if isinstance(inv, dict) else []
        merged_inventory_lines = _merge_inventory_lines(merged_inventory_lines, list(inv_lines))
        inv_ws = inv.get("warnings") if isinstance(inv, dict) else None
        if isinstance(inv_ws, list):
            merged_inventory_warnings.extend([f"[{vid}] {str(x)}" for x in inv_ws if str(x)])

    overhead_cost = (material_cost_total + process_cost_total) * overhead_rate
    total_cost = material_cost_total + process_cost_total + overhead_cost

    merged_out = {
        "final_material_lines": merged_material_lines,
        "trace": {
            "sku_code": sku_code,
            "bundle_groups": [{"model_version_id": x.get("model_version_id")} for x in group_results],
            "costing": {
                "currency": "CNY",
                "material_cost_total": material_cost_total,
                "process_cost_total": process_cost_total,
                "overhead_rate": overhead_rate,
                "overhead_cost": overhead_cost,
                "total_cost": total_cost,
                "unit_cost": total_cost,
            },
            "inventory": {
                "inventory_lines": merged_inventory_lines,
                "inventory_line_count": len(merged_inventory_lines),
                "warnings": merged_inventory_warnings[:50],
            },
        },
    }
    return {"merged": merged_out, "components": all_component_results}


def _fill_missing_units(db: Session, final_lines: List[Dict[str, Any]]) -> None:
    missing_ids: List[str] = []
    missing_codes: List[str] = []
    for line in final_lines:
        kind = str(line.get("material_kind") or "real")
        if kind not in ("real", "bom"):
            continue
        if line.get("unit_of_measure"):
            continue
        # Prefer metadata hints when available (common for placeholder/bom lines):
        # - metadata.display_unit: explicitly prepared for UI display
        # - metadata.bom_unit: derived from material/virtual master during sync
        meta = line.get("metadata") or {}
        if isinstance(meta, dict):
            hinted = (meta.get("display_unit") or meta.get("bom_unit") or "").strip()
            if hinted:
                line["unit_of_measure"] = hinted
                continue
        mid = str(line.get("material_ref_id") or "").strip()
        if mid:
            missing_ids.append(mid)
            continue
        code = str(line.get("material_code") or "").strip()
        if code:
            missing_codes.append(code)
    if not missing_ids and not missing_codes:
        return

    unit_by_id: Dict[str, str | None] = {}
    unit_by_code: Dict[str, str | None] = {}

    if missing_ids:
        rows = (
            db.query(models.Material)
            .filter(models.Material.id.in_(list({*missing_ids})))
            .all()
        )
        unit_by_id = {str(m.id): (m.unit or None) for m in rows}

    if missing_codes:
        rows2 = (
            db.query(models.Material)
            .filter(models.Material.material_code.in_(list({*missing_codes})))
            .all()
        )
        unit_by_code = {str(m.material_code): (m.unit or None) for m in rows2}

    for line in final_lines:
        if line.get("unit_of_measure"):
            continue
        mid = str(line.get("material_ref_id") or "").strip()
        unit = unit_by_id.get(mid) if mid else None
        if not unit:
            code = str(line.get("material_code") or "").strip()
            if code:
                unit = unit_by_code.get(code)
        if unit:
            line["unit_of_measure"] = unit


def _augment_runtime_tokens(
    tokens: List[str],
    *,
    sku_code: Optional[str],
    model_code: Optional[str],
    bound_version_id: str,
) -> List[str]:
    """
    Add binding context tokens for safer variant matching, while keeping stable order.

    Tokens are compared case-insensitively by evaluate_conditions, so we de-dup using lower().
    """
    out: List[str] = list(tokens or [])
    seen = {str(t).lower() for t in out if t not in (None, "")}

    def _add(tok: Optional[str]) -> None:
        if not tok:
            return
        s = str(tok).strip()
        if not s:
            return
        k = s.lower()
        if k in seen:
            return
        out.append(s)
        seen.add(k)

    if model_code:
        _add(f"MODEL:{str(model_code).strip().upper()}")
    if bound_version_id:
        _add(f"BOUND_VERSION:{bound_version_id}")
    if sku_code:
        _add(f"SKU:{str(sku_code).strip()}")
    return out


def _attach_costing(
    db: Session,
    final_lines: List[Dict[str, Any]],
    *,
    process_lines: List[models.ModelVersionProcess],
    measurement: Dict[str, Decimal],
) -> Dict[str, Any]:
    """
    Compute and attach costing fields (read-only):
    - bom_unit_price: CNY per BOM unit
    - line_cost: computed_quantity * bom_unit_price
    Also compute process (labor) cost from model_version_processes and include in totals.
    """
    real_ids: List[str] = []
    for line in final_lines:
        if (line.get("material_kind") or "real") == "real" and line.get("material_ref_id"):
            real_ids.append(str(line["material_ref_id"]))

    materials: Dict[str, models.Material] = {}
    if real_ids:
        rows = (
            db.query(models.Material)
            .filter(models.Material.id.in_(list({*real_ids})))
            .all()
        )
        materials = {m.id: m for m in rows}

    material_cost_total = Decimal("0")
    priced_lines = 0
    missing_price_lines = 0
    missing_price_material_codes: List[str] = []

    for line in final_lines:
        price: Optional[Decimal] = None

        if (line.get("material_kind") or "real") == "real" and line.get("material_ref_id"):
            m = materials.get(str(line.get("material_ref_id")))
            if m is not None:
                price = product_model_service._derive_bom_unit_price(m)

        if price is None:
            meta = line.get("metadata") or {}
            raw_price = meta.get("bom_unit_price") or meta.get("unit_price")
            if raw_price not in (None, ""):
                try:
                    price = Decimal(str(raw_price))
                except Exception:  # noqa: BLE001
                    price = None

        qty = line.get("computed_quantity")
        if not isinstance(qty, Decimal):
            try:
                qty = Decimal(str(qty))
            except Exception:  # noqa: BLE001
                qty = None

        # Apply line-level loss_rate for costing.
        # 口径：computed_quantity 为“净用量（未计损耗）”；成本按“含损耗用量”计算，
        # 与扣库（inventory）一致。
        if qty is not None:
            try:
                loss_rate = Decimal(str(line.get("loss_rate") or 0))
            except Exception:  # noqa: BLE001
                loss_rate = Decimal("0")
            if loss_rate > 0:
                qty = qty * (Decimal("1") + (loss_rate / Decimal("100")))

        line_cost: Optional[Decimal] = None
        if price is not None and qty is not None:
            try:
                line_cost = qty * price
            except Exception:  # noqa: BLE001
                line_cost = None

        line["bom_unit_price"] = price
        line["line_cost"] = line_cost

        if line_cost is not None:
            material_cost_total += line_cost
            priced_lines += 1
        else:
            missing_price_lines += 1
            code = line.get("material_code")
            if code:
                missing_price_material_codes.append(str(code))

    process_cost_total, process_costing = _compute_process_costing(
        db,
        process_lines=process_lines,
        width_mm=measurement["width_mm"],
        height_mm=measurement["height_mm"],
        quantity=measurement["quantity"],
    )

    overhead_rate = _resolve_overhead_rate(db, model_version_processes=process_lines)
    overhead_cost = (material_cost_total + process_cost_total) * overhead_rate
    total_cost = material_cost_total + process_cost_total + overhead_cost
    unit_cost = None
    try:
        if measurement.get("quantity") and measurement["quantity"] > 0:
            unit_cost = total_cost / measurement["quantity"]
    except Exception:  # noqa: BLE001
        unit_cost = None

    return {
        "currency": "CNY",
        "material_cost_total": material_cost_total,
        "process_cost_total": process_cost_total,
        "overhead_rate": overhead_rate,
        "overhead_cost": overhead_cost,
        "total_cost": total_cost,
        "unit_cost": unit_cost,
        "priced_material_lines": priced_lines,
        "missing_price_material_lines": missing_price_lines,
        "missing_price_material_codes": missing_price_material_codes[:50],
        **process_costing,
    }


def _compute_process_costing(
    db: Session,
    *,
    process_lines: List[models.ModelVersionProcess],
    width_mm: Decimal,
    height_mm: Decimal,
    quantity: Decimal,
) -> tuple[Decimal, Dict[str, Any]]:
    """
    Compute process(labor) costs from version process lines.

    Expected metadata on each process line (stored in metadata_json):
    - pricing_method: fixed/count/area/perimeter/width/height
    - cost_type: time/piece
    - base_minutes, unit_minutes
    - rate_per_minute, piece_rate
    """
    process_cost_total = Decimal("0")
    priced_process_lines = 0
    missing_price_process_lines = 0
    missing_price_process_codes: List[str] = []
    process_cost_lines: List[Dict[str, Any]] = []

    for row in process_lines or []:
        meta = row.metadata_json or {}
        proc = db.get(models.Process, row.process_id)

        pricing_method = str(meta.get("pricing_method") or "count")
        measure_method = (
            pricing_method
            if pricing_method in ("fixed", "count", "area", "perimeter", "width", "height")
            else "count"
        )
        measure_qty = product_model_service._measure_qty(
            measure_method if measure_method != "fixed" else "count",
            width_mm=width_mm,
            height_mm=height_mm,
            quantity=quantity,
        )

        cost_type = str(meta.get("cost_type") or "").strip() or None
        base_minutes = _to_decimal(meta.get("base_minutes"), Decimal("0"))
        unit_minutes = _to_decimal(meta.get("unit_minutes"), Decimal("0"))
        rate_per_minute = meta.get("rate_per_minute")
        piece_rate = meta.get("piece_rate")
        rate = _to_decimal(rate_per_minute, Decimal("0")) if rate_per_minute not in (None, "") else None
        piece = _to_decimal(piece_rate, Decimal("0")) if piece_rate not in (None, "") else None

        # Backward compatibility:
        # Older versions (or module sync) may have pricing_method/base_minutes/unit_minutes filled,
        # but miss meta.cost_type. In UI this effectively means "计时(time)".
        if cost_type not in ("time", "piece"):
            # If piece rate exists, assume piece; otherwise default to time.
            if piece is not None and piece > 0:
                cost_type = "piece"
            else:
                cost_type = "time"

        total_minutes: Optional[Decimal] = None
        total_cost: Optional[Decimal] = None
        warnings: List[str] = []
        if cost_type == "time":
            total_minutes = base_minutes + (unit_minutes * measure_qty)
            if rate is not None and rate > 0:
                total_cost = total_minutes * rate
            else:
                warnings.append("未配置分钟单价（rate_per_minute）")
                missing_price_process_lines += 1
                if proc and proc.process_code:
                    missing_price_process_codes.append(str(proc.process_code))
        elif cost_type == "piece":
            if piece is not None and piece > 0:
                total_cost = measure_qty * piece
            else:
                warnings.append("未配置计件单价（piece_rate）")
                missing_price_process_lines += 1
                if proc and proc.process_code:
                    missing_price_process_codes.append(str(proc.process_code))
        else:
            # Should not happen due to normalization above, but keep a safe fallback.
            warnings.append("未配置工序计价类型（cost_type=time/piece）")
            missing_price_process_lines += 1
            if proc and proc.process_code:
                missing_price_process_codes.append(str(proc.process_code))

        if total_cost is not None:
            process_cost_total += total_cost
            priced_process_lines += 1

        process_cost_lines.append(
            {
                "process_id": row.process_id,
                "process_code": proc.process_code if proc else None,
                "process_name": proc.process_name if proc else None,
                "team_name": meta.get("team_name") or (proc.team_name if proc else None),
                "pricing_method": pricing_method,
                "measure_quantity": measure_qty,
                "cost_type": cost_type,
                "base_minutes": base_minutes,
                "unit_minutes": unit_minutes,
                "rate_per_minute": rate,
                "piece_rate": piece,
                "total_minutes": total_minutes,
                "total_cost": total_cost,
                "warnings": warnings,
            }
        )

    return process_cost_total, {
        "priced_process_lines": priced_process_lines,
        "missing_price_process_lines": missing_price_process_lines,
        "missing_price_process_codes": missing_price_process_codes[:50],
        "process_lines": process_cost_lines,
    }


def _resolve_overhead_rate(db: Session, *, model_version_processes: List[models.ModelVersionProcess]) -> Decimal:
    """
    Resolve manufacturing overhead rate for costing.
    Priority:
    - version.metadata_json.costing.overhead_rate / manufacturing_overhead_rate
    - model.metadata_json.costing.overhead_rate / manufacturing_overhead_rate
    Fallback: 0.3 (consistent with existing UI stats / preview_model_cost).
    """
    version_id = model_version_processes[0].version_id if model_version_processes else None
    version = db.get(models.ProductModelVersion, version_id) if version_id else None
    model = db.get(models.ProductModel, version.model_id) if version else None

    def _read(meta: Any) -> Optional[Decimal]:
        if not isinstance(meta, dict):
            return None
        costing = meta.get("costing") if isinstance(meta.get("costing"), dict) else {}
        raw = (
            costing.get("overhead_rate")
            or costing.get("manufacturing_overhead_rate")
            or meta.get("overhead_rate")
            or meta.get("manufacturing_overhead_rate")
        )
        if raw in (None, ""):
            return None
        try:
            r = Decimal(str(raw))
            if r < 0:
                return Decimal("0")
            # 0-100 => 0-1
            if r > Decimal("1.5"):
                r = r / Decimal("100")
            return r
        except Exception:  # noqa: BLE001
            return None

    rate = _read(version.metadata_json if version else None)
    if rate is None:
        rate = _read(model.metadata_json if model else None)
    return rate if rate is not None else Decimal("0.3")


def _build_inventory_lines(db: Session, final_lines: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Build inventory deduction lines (REAL materials only).

    Rules:
    - real line => keep as-is (apply line loss_rate already included in computed_quantity? We keep computed_quantity here).
    - virtual line => expand using virtual_material_bindings into real materials by quantity_ratio and binding.loss_rate.
      expanded_qty = virtual_computed_qty * quantity_ratio * (1 + binding_loss_rate/100)

    Output is stored under trace.inventory for snapshot/audit.
    """
    out_lines: List[Dict[str, Any]] = []
    warnings: List[str] = []

    # Preload bindings and materials for virtual lines
    def _kind(v: Any) -> str:
        return str(v or "").strip().lower()

    v_ids = [
        str(l.get("material_ref_id"))
        for l in final_lines
        if (_kind(l.get("material_kind")).startswith("virtual") and l.get("material_ref_id"))
    ]
    v_ids = list({*v_ids})
    bindings_by_virtual: Dict[str, List[models.VirtualMaterialBinding]] = {}
    if v_ids:
        rows = (
            db.query(models.VirtualMaterialBinding)
            .filter(models.VirtualMaterialBinding.virtual_material_id.in_(v_ids))
            .all()
        )
        for b in rows:
            bindings_by_virtual.setdefault(b.virtual_material_id, []).append(b)

    mat_ids = list({str(b.material_id) for xs in bindings_by_virtual.values() for b in xs if b.material_id})
    mats: Dict[str, models.Material] = {}
    if mat_ids:
        ms = db.query(models.Material).filter(models.Material.id.in_(mat_ids)).all()
        mats = {m.id: m for m in ms}

    def _d(v: Any, default: Decimal = Decimal("0")) -> Decimal:
        if isinstance(v, Decimal):
            return v
        if v in (None, ""):
            return default
        try:
            return Decimal(str(v))
        except Exception:  # noqa: BLE001
            return default

    for line in final_lines:
        kind = _kind(line.get("material_kind") or "real")
        qty = _d(line.get("computed_quantity"), Decimal("0"))
        # Apply line-level loss_rate (0-100%) for inventory deduction.
        # 口径：computed_quantity 为“净用量”；扣库应按“含损耗用量”扣。
        line_loss = _d(line.get("loss_rate"), Decimal("0"))
        if line_loss > 0:
            qty = qty * (Decimal("1") + (line_loss / Decimal("100")))
        if qty <= 0:
            continue

        # NOTE:
        # - kind=real => deduct directly
        # - kind=bom  => treat as real for inventory deduction (some legacy/module lines use bom)
        if kind.startswith("real") or kind == "bom":
            out_lines.append(
                {
                    "source": "real_line",
                    "from_line_index": line.get("line_index"),
                    "material_id": line.get("material_ref_id"),
                    "material_code": line.get("material_code"),
                    "material_name": line.get("material_name"),
                    "unit_of_measure": line.get("unit_of_measure"),
                    "quantity": qty,
                }
            )
            continue

        if not kind.startswith("virtual"):
            # Unknown kinds are not inventory objects (but warn for diagnostics)
            code = str(line.get("material_code") or "").strip()
            name = str(line.get("material_name") or "").strip()
            if code or name:
                warnings.append(f"扣库跳过：未知 material_kind={kind}（{code or name}）")
            continue

        vid = str(line.get("material_ref_id") or "")
        binds = bindings_by_virtual.get(vid) or []
        if not binds:
            warnings.append(f"虚拟物料未配置绑定：{line.get('material_code') or vid}")
            continue

        for b in binds:
            m = mats.get(str(b.material_id))
            if not m or m.is_archived:
                warnings.append(f"虚拟物料绑定的真实物料不存在或已归档：{getattr(b,'material_id',None)}")
                continue
            ratio = _d(getattr(b, "quantity_ratio", None), Decimal("0"))
            # safety: recipe legacy 0-100 => 0-1
            if ratio > Decimal("1.5"):
                ratio = ratio / Decimal("100")
            loss = _d(getattr(b, "loss_rate", None), Decimal("0"))
            loss_factor = Decimal("1") + (loss / Decimal("100"))
            used = qty * ratio * loss_factor
            if used <= 0:
                continue
            out_lines.append(
                {
                    "source": "virtual_expand",
                    "from_line_index": line.get("line_index"),
                    "virtual_code": line.get("material_code"),
                    "virtual_name": line.get("material_name"),
                    "material_id": m.id,
                    "material_code": m.material_code,
                    "material_name": m.material_name,
                    "unit_of_measure": m.unit or line.get("unit_of_measure"),
                    "quantity": used,
                    "ratio": ratio,
                    "binding_loss_rate": loss,
                }
            )

    # Aggregate by real material_code (fallback to material_id/name) for readability
    agg: Dict[str, Dict[str, Any]] = {}
    for r in out_lines:
        code = str(r.get("material_code") or "").strip()
        mid = str(r.get("material_id") or "").strip()
        name = str(r.get("material_name") or "").strip()
        key = code or mid or name
        if not key:
            continue
        agg.setdefault(
            key,
            {
                "material_id": r.get("material_id"),
                "material_code": r.get("material_code"),
                "material_name": r.get("material_name"),
                "unit_of_measure": r.get("unit_of_measure"),
                "quantity": Decimal("0"),
                "sources": [],
            },
        )
        agg[key]["quantity"] = _d(agg[key]["quantity"]) + _d(r.get("quantity"))
        # keep limited trace
        if len(agg[key]["sources"]) < 20:
            agg[key]["sources"].append(
                {
                    "source": r.get("source"),
                    "from_line_index": r.get("from_line_index"),
                    "virtual_code": r.get("virtual_code"),
                    "ratio": r.get("ratio"),
                    "binding_loss_rate": r.get("binding_loss_rate"),
                    "quantity": r.get("quantity"),
                }
            )

    agg_lines = sorted(agg.values(), key=lambda x: str(x.get("material_code") or x.get("material_id") or x.get("material_name") or ""))
    total_qty = sum([_d(x.get("quantity")) for x in agg_lines], Decimal("0"))
    return {
        "inventory_lines": agg_lines,
        "inventory_line_count": len(agg_lines),
        "inventory_total_quantity_sum": total_qty,
        "warnings": warnings[:50],
    }

def _resolve_version(
    db: Session,
    *,
    model_version_id: Optional[str],
    sku_code: Optional[str],
) -> models.ProductModelVersion:
    version: Optional[models.ProductModelVersion] = None
    if model_version_id:
        version = product_model_service.get_model_version(db, model_version_id)
    elif sku_code:
        mapping = (
            db.query(models.SkuModelVersionMapping)
            .filter(
                models.SkuModelVersionMapping.sku_code == sku_code,
                models.SkuModelVersionMapping.is_archived.is_(False),
            )
            .order_by(
                models.SkuModelVersionMapping.is_active.desc(),
                models.SkuModelVersionMapping.updated_at.desc(),
            )
            .first()
        )
        if mapping:
            version = product_model_service.get_model_version(db, mapping.model_version_id)
    if not version or version.is_archived:
        raise ValueError("未找到可用的标准版本（model_version_id 或 sku_code）")
    return version


def _build_measurement(
    version: models.ProductModelVersion,
    spec_result: Dict[str, Any],
    quantity: Optional[Decimal],
) -> Dict[str, Decimal]:
    version_meta = version.metadata_json or {}
    std_meta = version_meta.get("standard") if isinstance(version_meta.get("standard"), dict) else {}
    default_width_mm = _to_decimal(std_meta.get("width_mm"), Decimal("1000"))
    default_height_mm = _to_decimal(std_meta.get("height_mm"), Decimal("1000"))

    width_cm = spec_result.get("width_cm")
    height_cm = spec_result.get("height_cm")
    width_mm = _to_decimal(width_cm, default_width_mm / Decimal("10")) * Decimal("10") if width_cm is not None else default_width_mm
    height_mm = (
        _to_decimal(height_cm, default_height_mm / Decimal("10")) * Decimal("10") if height_cm is not None else default_height_mm
    )
    qty = _to_decimal(quantity, Decimal("1"))
    return {
        "width_mm": width_mm,
        "height_mm": height_mm,
        "quantity": qty,
    }


def _build_metrics(spec_result: Dict[str, Any], measurement: Dict[str, Decimal]) -> Dict[str, Decimal | None]:
    width_cm = spec_result.get("width_cm")
    height_cm = spec_result.get("height_cm")
    diameter_cm = spec_result.get("diameter_cm")
    area_m2 = spec_result.get("area_m2")
    perimeter_m = spec_result.get("perimeter_m")
    if width_cm is None:
        width_cm = measurement["width_mm"] / Decimal("10")
    if height_cm is None:
        height_cm = measurement["height_mm"] / Decimal("10")
    if area_m2 is None:
        area_m2 = (measurement["width_mm"] * measurement["height_mm"]) / Decimal("1000000")
    if perimeter_m is None:
        perimeter_m = (
            Decimal("2") * (measurement["width_mm"] + measurement["height_mm"]) / Decimal("1000")
        )
    return {
        "width_cm": width_cm,
        "height_cm": height_cm,
        "diameter_cm": diameter_cm,
        "area_m2": area_m2,
        "perimeter_m": perimeter_m,
    }


def _materialize_base_line(
    row: models.ModelVersionMaterial,
    *,
    measurement: Dict[str, Decimal],
) -> Dict[str, Any]:
    meta = row.metadata_json or {}
    fixed_quantity = _to_decimal(meta.get("fixed_quantity"))
    coverage_ratio = _to_decimal(meta.get("coverage_ratio"), Decimal("1"))
    return _build_line_payload(
        measurement=measurement,
        source_type="base_line",
        base_line_id=row.id,
        variant_id=None,
        variant_item_id=None,
        material_kind=row.material_type,
        material_ref_id=row.material_ref_id,
        material_code=row.material_code,
        material_name=row.material_name,
        unit_of_measure=row.unit_of_measure,
        calculation_method=row.calculation_method or "count",
        base_quantity=_to_decimal(row.base_quantity),
        fixed_quantity=fixed_quantity,
        coverage_ratio=coverage_ratio,
        loss_rate=_to_decimal(row.loss_rate),
        metadata=dict(meta),
    )


def _materialize_variant_item(
    item: models.ProductModelLineVariantItem,
    *,
    base_row: models.ModelVersionMaterial,
    measurement: Dict[str, Decimal],
    variant_id: str,
    base_line_id: str,
) -> Dict[str, Any]:
    # ERP 最稳第一步：replace_self 同单位 1→1。
    # 历史数据里经常出现：替换物料的 calculation_method/base_quantity 没填或为 0，导致 computed_quantity=0。
    # 这里做兜底：替换行继承基准行的计量方式/β/单位（若替换行自身缺失或为 0）。
    base_method = str(getattr(base_row, "calculation_method", None) or "count")
    base_uom = getattr(base_row, "unit_of_measure", None)
    base_beta = _to_decimal(getattr(base_row, "base_quantity", None), Decimal("1"))

    item_method = str(getattr(item, "calculation_method", None) or "").strip()
    # 如果替换行仍是默认 count，但基准行是 area/perimeter/...，则优先继承基准行（避免替换后数量变成“按个数=1”的假象）。
    if (not item_method or item_method == "count") and base_method and base_method != "count":
        method = base_method
    else:
        method = item_method or base_method or "count"
    beta = _to_decimal(getattr(item, "base_quantity", None), Decimal("0"))
    if beta <= 0:
        beta = base_beta if base_beta > 0 else Decimal("1")
    uom = getattr(item, "unit_of_measure", None) or base_uom
    return _build_line_payload(
        measurement=measurement,
        source_type="variant_item",
        base_line_id=base_line_id,
        variant_id=variant_id,
        variant_item_id=item.id,
        material_kind=item.material_kind,
        material_ref_id=item.material_ref_id,
        material_code=item.material_code,
        material_name=item.material_name,
        unit_of_measure=uom,
        calculation_method=method,
        base_quantity=beta,
        fixed_quantity=_to_decimal(item.fixed_quantity),
        coverage_ratio=_to_decimal(item.coverage_ratio, Decimal("1")),
        loss_rate=_to_decimal(item.loss_rate),
        metadata=dict(item.metadata_json or {}),
    )


def _build_line_payload(
    *,
    measurement: Dict[str, Decimal],
    source_type: str,
    base_line_id: Optional[str],
    variant_id: Optional[str],
    variant_item_id: Optional[str],
    material_kind: str | None,
    material_ref_id: Optional[str],
    material_code: Optional[str],
    material_name: Optional[str],
    unit_of_measure: Optional[str],
    calculation_method: str,
    base_quantity: Decimal,
    fixed_quantity: Decimal,
    coverage_ratio: Decimal,
    loss_rate: Decimal,
    metadata: Dict[str, Any],
) -> Dict[str, Any]:
    method = calculation_method or "count"
    # 工艺余量：用于“宽/高不固定，但固定扎口/封边/包边”等确定性规则
    # 约定（单位：mm，>=0）：
    # - extra_width_mm / extra_height_mm：对宽/高做确定性尺寸修正（如桌布四周折边）
    # - extra_long_side_mm / extra_short_side_mm：对长边/短边做确定性修正（如编织袋按短边卷 + 固定放量）
    # 以及：
    # - fixed_per_count_quantity：按件固定追加用量（与数量线性相关），用于“每根切割余头”类场景的近似表达
    extra_w = _to_decimal((metadata or {}).get("extra_width_mm"), Decimal("0"))
    extra_h = _to_decimal((metadata or {}).get("extra_height_mm"), Decimal("0"))
    extra_long = _to_decimal((metadata or {}).get("extra_long_side_mm"), Decimal("0"))
    extra_short = _to_decimal((metadata or {}).get("extra_short_side_mm"), Decimal("0"))
    fixed_per_count = _to_decimal((metadata or {}).get("fixed_per_count_quantity"), Decimal("0"))
    eff_w = measurement["width_mm"] + max(Decimal("0"), extra_w)
    eff_h = measurement["height_mm"] + max(Decimal("0"), extra_h)
    q = measurement["quantity"]
    if method == "long_side":
        side = max(eff_w, eff_h) + max(Decimal("0"), extra_long)
        measure_qty = (side / Decimal("1000")) * q
    elif method == "short_side":
        side = min(eff_w, eff_h) + max(Decimal("0"), extra_short)
        measure_qty = (side / Decimal("1000")) * q
    else:
        measure_qty = product_model_service._measure_qty(
            method,
            width_mm=eff_w,
            height_mm=eff_h,
            quantity=q,
        )

    per_count = max(Decimal("0"), fixed_per_count) * q
    total = fixed_quantity + per_count + (base_quantity * coverage_ratio * measure_qty)

    if (extra_w or extra_h or extra_long or extra_short or fixed_per_count) and isinstance(metadata, dict):
        # 仅用于审计/排查；不影响扣库/成本的关键字段
        metadata = dict(metadata)
        metadata.setdefault("extra_width_mm", str(extra_w))
        metadata.setdefault("extra_height_mm", str(extra_h))
        metadata.setdefault("extra_long_side_mm", str(extra_long))
        metadata.setdefault("extra_short_side_mm", str(extra_short))
        metadata.setdefault("fixed_per_count_quantity", str(fixed_per_count))
    return {
        "source_type": source_type,
        "base_line_id": base_line_id,
        "variant_id": variant_id,
        "variant_item_id": variant_item_id,
        "material_kind": material_kind or "real",
        "material_ref_id": material_ref_id,
        "material_code": material_code,
        "material_name": material_name,
        "unit_of_measure": unit_of_measure,
        "calculation_method": method,
        "base_quantity": base_quantity,
        "fixed_quantity": fixed_quantity,
        "coverage_ratio": coverage_ratio,
        "loss_rate": loss_rate,
        "computed_quantity": total,
        "metadata": metadata,
    }


def _to_decimal(value: Any, default: Decimal = Decimal("0")) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if value in (None, ""):
        return default
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return default

