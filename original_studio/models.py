"""Data models, JSON Schema validators, and Three-Layer storage management for Original Novel Studio."""

import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app import (
    NOVELS_DIR,
    lock_novel,
    now_iso,
    parse_novel,
    sanitize_filename,
    write_novel,
)

SCHEMA_VERSION = "2.0.0"

VALID_STATUSES = {
    "idle",
    "planning_beats",
    "writing",
    "paused",
    "awaiting_review",
    "completed",
    "failed",
}


def get_spec_path(novel_id: str) -> Path:
    stem = sanitize_filename(novel_id)
    return NOVELS_DIR / f"{stem}.spec.json"


def get_runtime_path(novel_id: str) -> Path:
    stem = sanitize_filename(novel_id)
    return NOVELS_DIR / f"{stem}.runtime.json"


def get_markdown_path(novel_id: str) -> Path:
    stem = sanitize_filename(novel_id)
    return NOVELS_DIR / f"{stem}.md"


def validate_spec(data: Any) -> Dict[str, Any]:
    """严格校验 novel_spec.json 数据结构。校验不通过抛出 ValueError。"""
    if not isinstance(data, dict):
        raise ValueError("spec 必须为 JSON 对象 (dict)")

    schema_version = data.get("schema_version") or SCHEMA_VERSION
    if str(schema_version) != SCHEMA_VERSION:
        raise ValueError(f"schema_version 必须为 '{SCHEMA_VERSION}'")

    meta = data.get("meta")
    if not isinstance(meta, dict):
        raise ValueError("缺少 meta 对象")
    title = (meta.get("title") or "").strip()
    if not title:
        raise ValueError("meta.title 不能为空")
    genre = (meta.get("genre") or "").strip()
    if not genre:
        raise ValueError("meta.genre 不能为空")

    ideation = data.get("ideation")
    if not isinstance(ideation, dict):
        raise ValueError("缺少 ideation 对象")
    logline = (ideation.get("logline") or "").strip()
    if not logline:
        raise ValueError("ideation.logline 不能为空")

    protagonist = data.get("protagonist")
    if not isinstance(protagonist, dict):
        raise ValueError("缺少 protagonist 对象")
    p_name = (protagonist.get("name") or "").strip()
    if not p_name:
        raise ValueError("protagonist.name 不能为空")

    ending = data.get("ending")
    if not isinstance(ending, dict):
        raise ValueError("缺少 ending 对象")

    stages = data.get("stages")
    if not isinstance(stages, list):
        raise ValueError("stages 必须为数组 (list)")

    # 规范化并清洗各层结构，补全默认值
    normalized_meta = {
        "title": title,
        "genre": genre,
        "selected_trope": meta.get("selected_trope") if isinstance(meta.get("selected_trope"), str) else None,
        "target_total_words": int(meta.get("target_total_words") or 300000),
        "target_stages_count": int(meta.get("target_stages_count") or len(stages) or 4),
        "target_words_per_chapter": int(meta.get("target_words_per_chapter") or 2500),
    }

    normalized_ideation = {
        "logline": logline,
        "hook": str(ideation.get("hook") or "").strip(),
        "reader_expectation": str(ideation.get("reader_expectation") or "").strip(),
        "theme": str(ideation.get("theme") or "").strip(),
        "tone": str(ideation.get("tone") or "").strip(),
    }

    worldview = data.get("worldview") if isinstance(data.get("worldview"), dict) else {}
    normalized_worldview = {
        "background": str(worldview.get("background") or "").strip(),
        "special_rules": str(worldview.get("special_rules") or "").strip(),
        "taboos": str(worldview.get("taboos") or "").strip(),
    }

    normalized_protagonist = {
        "id": str(protagonist.get("id") or "char_protagonist"),
        "name": p_name,
        "role": str(protagonist.get("role") or "").strip(),
        "want": str(protagonist.get("want") or "").strip(),
        "need": str(protagonist.get("need") or "").strip(),
        "flaw": str(protagonist.get("flaw") or "").strip(),
        "arc": str(protagonist.get("arc") or "").strip(),
    }

    characters = data.get("characters") if isinstance(data.get("characters"), list) else []
    normalized_characters = []
    for idx, c in enumerate(characters):
        if isinstance(c, dict):
            c_name = str(c.get("name") or "").strip()
            if c_name:
                normalized_characters.append({
                    "id": str(c.get("id") or f"char_{idx + 1}"),
                    "name": c_name,
                    "relation_type": str(c.get("relation_type") or "ally_friend"),
                    "role_desc": str(c.get("role_desc") or "").strip(),
                    "bond_or_conflict": str(c.get("bond_or_conflict") or "").strip(),
                })

    normalized_ending = {
        "climax_vision": str(ending.get("climax_vision") or "").strip(),
        "core_dilemma": str(ending.get("core_dilemma") or "").strip(),
        "ultimate_cost": str(ending.get("ultimate_cost") or "").strip(),
        "resolution_tone": str(ending.get("resolution_tone") or "").strip(),
    }

    normalized_stages = []
    for idx, st in enumerate(stages):
        if isinstance(st, dict):
            st_idx = int(st.get("stage_index") or (idx + 1))
            st_title = str(st.get("title") or f"第 {st_idx} 阶段").strip()
            anchors = st.get("anchors") if isinstance(st.get("anchors"), dict) else {}
            normalized_stages.append({
                "stage_index": st_idx,
                "title": st_title,
                "expected_chapters": int(st.get("expected_chapters") or 8),
                "anchors": {
                    "stage_goal": str(anchors.get("stage_goal") or "").strip(),
                    "main_obstacle": str(anchors.get("main_obstacle") or "").strip(),
                    "climax_hook": str(anchors.get("climax_hook") or "").strip(),
                    "transition_springboard": str(anchors.get("transition_springboard") or "").strip(),
                },
            })

    locked_fields = data.get("locked_fields") if isinstance(data.get("locked_fields"), list) else []
    clean_locked = [str(f).strip() for f in locked_fields if str(f).strip()]

    return {
        "schema_version": SCHEMA_VERSION,
        "locked_fields": clean_locked,
        "meta": normalized_meta,
        "ideation": normalized_ideation,
        "worldview": normalized_worldview,
        "protagonist": normalized_protagonist,
        "characters": normalized_characters,
        "ending": normalized_ending,
        "stages": normalized_stages,
    }


def validate_runtime(data: Any) -> Dict[str, Any]:
    """校验 novel_runtime.json 结构。"""
    if not isinstance(data, dict):
        raise ValueError("runtime 必须为 JSON 对象 (dict)")

    status = data.get("status") or "idle"
    if status not in VALID_STATUSES:
        raise ValueError(f"无效的 status: {status}，允许值为 {VALID_STATUSES}")

    schema_version = data.get("schema_version") or SCHEMA_VERSION
    current_stage_index = int(data.get("current_stage_index") or 1)
    active_job = data.get("active_job") if isinstance(data.get("active_job"), dict) else None

    current_stage_beats = []
    for idx, b in enumerate(data.get("current_stage_beats") or []):
        if isinstance(b, dict):
            current_stage_beats.append({
                "chapter_offset": int(b.get("chapter_offset") or (idx + 1)),
                "global_chapter_idx": int(b.get("global_chapter_idx") or (idx + 1)),
                "title": str(b.get("title") or f"第 {idx + 1} 章").strip(),
                "beat_type": str(b.get("beat_type") or "setup"),
                "summary": str(b.get("summary") or "").strip(),
                "planted_clues": [str(c) for c in (b.get("planted_clues") or [])],
                "is_generated": bool(b.get("is_generated", False)),
            })

    story_state = data.get("story_state") if isinstance(data.get("story_state"), dict) else {}
    normalized_story_state = {
        "rolling_summary": str(story_state.get("rolling_summary") or "").strip(),
        "characters_ledger": story_state.get("characters_ledger") if isinstance(story_state.get("characters_ledger"), dict) else {},
        "clues_ledger": story_state.get("clues_ledger") if isinstance(story_state.get("clues_ledger"), list) else [],
    }

    checkpoints = data.get("checkpoints") if isinstance(data.get("checkpoints"), list) else []

    return {
        "schema_version": schema_version,
        "status": status,
        "current_stage_index": current_stage_index,
        "active_job": active_job,
        "current_stage_beats": current_stage_beats,
        "story_state": normalized_story_state,
        "checkpoints": checkpoints,
    }


def default_runtime() -> Dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "idle",
        "current_stage_index": 1,
        "active_job": None,
        "current_stage_beats": [],
        "story_state": {
            "rolling_summary": "",
            "characters_ledger": {},
            "clues_ledger": [],
        },
        "checkpoints": [],
    }


def _atomic_write_json(p: Path, payload: Dict[str, Any]) -> None:
    """Write JSON atomically with a brief Windows PermissionError retry loop."""
    dir_name = p.parent
    dir_name.mkdir(parents=True, exist_ok=True)
    tmp_p = dir_name / f".tmp_{p.stem}_{os.getpid()}_{time.time_ns()}.tmp"
    try:
        with open(tmp_p, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        for attempt in range(5):
            try:
                os.replace(str(tmp_p), str(p))
                break
            except PermissionError:
                if attempt == 4:
                    raise
                time.sleep(0.02 * (attempt + 1))
    except Exception:
        try:
            if tmp_p.exists():
                tmp_p.unlink()
        except Exception:
            pass
        raise


def load_novel_spec(novel_id: str) -> Optional[Dict[str, Any]]:
    stem = sanitize_filename(novel_id)
    p = get_spec_path(stem)
    with lock_novel(stem):
        if not p.exists():
            return None
        try:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None


def save_novel_spec(novel_id: str, spec_dict: Dict[str, Any]) -> bool:
    clean_spec = validate_spec(spec_dict)
    stem = sanitize_filename(novel_id)
    p = get_spec_path(stem)
    with lock_novel(stem):
        _atomic_write_json(p, clean_spec)
    return True


def load_novel_runtime(novel_id: str) -> Dict[str, Any]:
    stem = sanitize_filename(novel_id)
    p = get_runtime_path(stem)
    with lock_novel(stem):
        if not p.exists():
            return default_runtime()
        try:
            with open(p, "r", encoding="utf-8") as f:
                return validate_runtime(json.load(f))
        except Exception:
            return default_runtime()


def save_novel_runtime(novel_id: str, runtime_dict: Dict[str, Any]) -> bool:
    clean_runtime = validate_runtime(runtime_dict)
    stem = sanitize_filename(novel_id)
    p = get_runtime_path(stem)
    with lock_novel(stem):
        _atomic_write_json(p, clean_runtime)
    return True


def init_novel_three_layers(
    novel_id: str,
    title: str,
    spec_dict: Dict[str, Any],
    runtime_dict: Optional[Dict[str, Any]] = None,
) -> Tuple[Path, Path, Path]:
    """初始化三层物理落盘：<id>.spec.json, <id>.runtime.json, <id>.md。"""
    stem = sanitize_filename(novel_id or title)
    spec_p = get_spec_path(stem)
    runtime_p = get_runtime_path(stem)
    md_p = get_markdown_path(stem)

    clean_spec = validate_spec(spec_dict)
    clean_runtime = validate_runtime(runtime_dict or default_runtime())

    with lock_novel(stem):
        # 1. 写入 spec
        save_novel_spec(stem, clean_spec)
        # 2. 写入 runtime
        save_novel_runtime(stem, clean_runtime)
        # 3. 写入 md (若尚不存在正文)
        if not md_p.exists():
            meta = {
                "id": stem,
                "title": title,
                "type": "original",
                "schema_version": SCHEMA_VERSION,
                "spec_ref": f"{stem}.spec.json",
                "runtime_ref": f"{stem}.runtime.json",
                "current_volume": 1,
                "total_words": 0,
                "created_at": now_iso(),
                "updated_at": now_iso(),
            }
            write_novel(md_p, meta, [])

    return spec_p, runtime_p, md_p


def get_field_by_path(root: Dict[str, Any], path: str) -> Any:
    """按点分隔路径读取字典值：如 'protagonist.want'。"""
    parts = path.split(".")
    curr = root
    for p in parts:
        if isinstance(curr, dict) and p in curr:
            curr = curr[p]
        else:
            return None
    return curr


def set_field_by_path(root: Dict[str, Any], path: str, val: Any) -> None:
    """按点分隔路径设置字典值：如 'protagonist.want'。"""
    parts = path.split(".")
    curr = root
    for p in parts[:-1]:
        if p not in curr or not isinstance(curr[p], dict):
            curr[p] = {}
        curr = curr[p]
    curr[parts[-1]] = val


def apply_locked_fields(
    base_spec: Optional[Dict[str, Any]],
    new_spec: Dict[str, Any],
    locked_fields: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """根据 locked_fields 列表，将 base_spec 中对应被锁定的字段值回填到 new_spec 中，确保不被覆盖。"""
    if not base_spec:
        return new_spec
    locks = locked_fields or new_spec.get("locked_fields") or base_spec.get("locked_fields") or []
    for field_path in locks:
        orig_val = get_field_by_path(base_spec, field_path)
        if orig_val is not None:
            set_field_by_path(new_spec, field_path, orig_val)
    new_spec["locked_fields"] = list(set(locks))
    return new_spec
