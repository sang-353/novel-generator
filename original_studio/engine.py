"""Generation engine, Two-Stage Beat execution, Story State Memory, and SSE Runner for Original Novel Studio."""

import json
import queue
import re
import threading
import time
import uuid
from typing import Any, Dict, Generator, List, Optional, Tuple

from app import (
    NOVELS_DIR,
    ORIGINAL_SYS,
    acquire_book,
    chat,
    context_from,
    extract_json,
    generate_text,
    get_provider,
    lock_novel,
    now_iso,
    parse_novel,
    release_book,
    sanitize_filename,
    write_novel,
)

from original_studio.models import (
    SCHEMA_VERSION,
    apply_locked_fields,
    get_field_by_path,
    get_markdown_path,
    get_spec_path,
    init_novel_three_layers,
    load_novel_runtime,
    load_novel_spec,
    save_novel_runtime,
    save_novel_spec,
    set_field_by_path,
    validate_spec,
)

# 内存中活跃的任务运行期实例映射：job_id -> StageRunner
_RUNNER_LOCK = threading.Lock()
ACTIVE_RUNNERS: Dict[str, "StageRunner"] = {}


# =========================================================================
# 1. 4 步链式多工位深度推演 (Chained Creative Deduction)
# =========================================================================

def deduce_creative_pipeline(
    title: str,
    genre: str,
    selected_trope: Optional[str] = None,
    user_pitch: Optional[str] = None,
    meta_params: Optional[Dict[str, Any]] = None,
    locked_fields: Optional[List[str]] = None,
    provider_id: Optional[str] = None,
    existing_spec: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    4 步链式深度推演全书设定：
    Step 1: 核心创意与立意 (Logline, Hook, 情绪期待, 深层立意, 叙事基调)
    Step 2: 世界观与核心角色 (主角 Want/Need/Flaw/Arc + 关键关系角色)
    Step 3: 终局锚点设计 (四大终局锚点)
    Step 4: 分卷阶段大纲规划 (3~5 阶段分卷锚点)
    严格支持 locked_fields 字段锁定保护。
    """
    meta_params = meta_params or {}
    target_stages = int(meta_params.get("target_stages_count") or 4)
    target_total_words = int(meta_params.get("target_total_words") or 300000)

    # 上下文背景锚点
    pitch_text = f"【创作者一句话构想/要求】：{user_pitch}\n" if user_pitch else ""
    trope_text = f"【参考开局灵感/脑洞】：{selected_trope}\n" if selected_trope else ""

    # ----- 阶段 1：创意与立意推演 -----
    sys_ideation = "你是一位享誉业界的顶级小说策划主编，擅长从概念推导高吸引力、高张力的故事立意。"
    user_ideation = (
        f"书名：{title}\n"
        f"题材类型：{genre}\n"
        f"{trope_text}"
        f"{pitch_text}"
        "请推演该小说的核心创意与故事立意，输出 JSON 格式：\n"
        "{\n"
        '  "logline": "一句话故事梗概 (主角 + 核心困境/渴望 + 终极目标或阻力，约 30-60 字)",\n'
        '  "hook": "核心卖点与抓人抓手 (如强反差、致命倒计时、悬念冲突)",\n'
        '  "reader_expectation": "目标读者核心情绪体验与满足感 (如：甜虐交织/极致打脸/智谋博弈/幽默治愈)",\n'
        '  "theme": "深层思想立意 (探讨的普遍人性或价值观)",\n'
        '  "tone": "叙事基调与视角 (如：第三人称限制视角，笔调冷峻克制/明快轻快)"\n'
        "}\n"
        "不要输出任何其他解释文字。"
    )
    raw_ideation, _ = chat(
        [{"role": "system", "content": sys_ideation}, {"role": "user", "content": user_ideation}],
        max_tokens=2000,
        json_mode=True,
        provider_id=provider_id,
    )
    ideation_data = extract_json(raw_ideation) or {}
    if not isinstance(ideation_data, dict):
        ideation_data = {}
    logline = ideation_data.get("logline") or f"关于《{title}》的传奇故事。"

    # ----- 阶段 2：世界观与人物推演 -----
    sys_world_cast = "你是一位深度角色弧光塑造大师与世界观架构师，擅长塑造具有复杂人性弱点与强烈欲望的人物。"
    user_world_cast = (
        f"题材：{genre}\n"
        f"一句话故事：{logline}\n"
        f"核心卖点：{ideation_data.get('hook', '')}\n"
        f"基调：{ideation_data.get('tone', '')}\n\n"
        "请为该作构建核心世界观法则以及主要人物，输出 JSON 格式：\n"
        "{\n"
        '  "worldview": {\n'
        '    "background": "时代背景、社会格局与生活图景 (150-300 字)",\n'
        '    "special_rules": "核心特殊法则或运转逻辑 (如力量规则/法律约束/社会潜规则)",\n'
        '    "taboos": "不可触犯的硬性禁忌与违规代价"\n'
        '  },\n'
        '  "protagonist": {\n'
        '    "name": "主角姓名",\n'
        '    "role": "社会身份/定位",\n'
        '    "want": "外在明确追求的目标 (外在欲望)",\n'
        '    "need": "内心真正需要的顿悟或情感补全 (内在匮乏)",\n'
        '    "flaw": "致命弱点/性格盲区",\n'
        '    "arc": "全书人物成长轨迹/弧光"\n'
        '  },\n'
        '  "characters": [\n'
        '    {\n'
        '      "name": "关键角色姓名",\n'
        '      "relation_type": "cp_love|rival_antagonist|mentor|ally_friend|neutral_third",\n'
        '      "role_desc": "身份与性格特征",\n'
        '      "bond_or_conflict": "与主角的核心羁绊或冲突交锋点"\n'
        '    }\n'
        '  ]\n'
        "}\n"
        "注意：角色设定须符合题材特色（若是言情偏向CP互动，若是悬疑偏向对手交锋，中立真实）。不要输出额外文字。"
    )
    raw_world_cast, _ = chat(
        [{"role": "system", "content": sys_world_cast}, {"role": "user", "content": user_world_cast}],
        max_tokens=2500,
        json_mode=True,
        provider_id=provider_id,
    )
    wc_data = extract_json(raw_world_cast) or {}
    worldview_data = wc_data.get("worldview") if isinstance(wc_data.get("worldview"), dict) else {}
    protagonist_data = wc_data.get("protagonist") if isinstance(wc_data.get("protagonist"), dict) else {}
    characters_data = wc_data.get("characters") if isinstance(wc_data.get("characters"), list) else []

    p_name = protagonist_data.get("name") or "主角"

    # ----- 阶段 3：终局锚点推演 -----
    sys_ending = "你是一位顶级好莱坞结构编剧，精通终局高潮（Climax）与情感沉淀。"
    user_ending = (
        f"故事梗概：{logline}\n"
        f"主角：{p_name}（Want: {protagonist_data.get('want', '')} / Need: {protagonist_data.get('need', '')}）\n"
        f"深层立意：{ideation_data.get('theme', '')}\n\n"
        "请推演本书的【四大终局锚点】，防止后期烂尾失控，输出 JSON 格式：\n"
        "{\n"
        '  "climax_vision": "终局决胜场景愿景 (最终冲突在哪爆发、如何达成终极解决)",\n'
        '  "core_dilemma": "主角在终局面临的最艰难抉择 (灵魂考验，二选一的痛苦困境)",\n'
        '  "ultimate_cost": "破局所必须付出的不可逆代价或心理牺牲",\n'
        '  "resolution_tone": "终局落幕时的情感余韵与读者回味 (圆满欣慰/悲壮旷远/微酸释然)"\n'
        "}\n"
        "不要输出多余解释文字。"
    )
    raw_ending, _ = chat(
        [{"role": "system", "content": sys_ending}, {"role": "user", "content": user_ending}],
        max_tokens=1500,
        json_mode=True,
        provider_id=provider_id,
    )
    ending_data = extract_json(raw_ending) or {}
    if not isinstance(ending_data, dict):
        ending_data = {}

    # ----- 阶段 4：分卷规划推演 -----
    sys_stages = "你是一位资深长篇连载小说结构师，擅长将长篇拆解为高潮起伏的阶段分卷。"
    user_stages = (
        f"全书总目标：{target_stages} 个阶段分卷，预估总字数约 {target_total_words}。\n"
        f"故事梗概：{logline}\n"
        f"主角：{p_name}\n"
        f"终局愿景：{ending_data.get('climax_vision', '')}\n\n"
        f"请将全书划分为 {target_stages} 个结构紧密的阶段分卷，输出 JSON 格式：\n"
        "{\n"
        '  "stages": [\n'
        '    {\n'
        '      "stage_index": 1,\n'
        '      "title": "第 1 卷卷名",\n'
        '      "expected_chapters": 8,\n'
        '      "anchors": {\n'
        '        "stage_goal": "本卷主角的核心诉求/目标",\n'
        '        "main_obstacle": "本卷最主要的阻力与阻碍势力/困境",\n'
        '        "climax_hook": "本卷的阶段高潮/情感引爆点 (必须具体有事件)",\n'
        '        "transition_springboard": "本卷破局跳板与引出下一卷的悬念钩子"\n'
        '      }\n'
        '    }\n'
        '  ]\n'
        "}\n"
        "不要输出任何其他说明文字。"
    )
    raw_stages, _ = chat(
        [{"role": "system", "content": sys_stages}, {"role": "user", "content": user_stages}],
        max_tokens=3000,
        json_mode=True,
        provider_id=provider_id,
    )
    stages_obj = extract_json(raw_stages) or {}
    stages_list = stages_obj.get("stages") if isinstance(stages_obj, dict) and isinstance(stages_obj.get("stages"), list) else []

    # 组装完整 Spec
    raw_spec = {
        "schema_version": SCHEMA_VERSION,
        "locked_fields": locked_fields or [],
        "meta": {
            "title": title,
            "genre": genre,
            "selected_trope": selected_trope,
            "target_total_words": target_total_words,
            "target_stages_count": target_stages,
            "target_words_per_chapter": int(meta_params.get("target_words_per_chapter") or 2500),
        },
        "ideation": {
            "logline": logline,
            "hook": ideation_data.get("hook", ""),
            "reader_expectation": ideation_data.get("reader_expectation", ""),
            "theme": ideation_data.get("theme", ""),
            "tone": ideation_data.get("tone", ""),
        },
        "worldview": worldview_data,
        "protagonist": {
            "name": p_name,
            "role": protagonist_data.get("role", "核心主角"),
            "want": protagonist_data.get("want", "达成核心愿望"),
            "need": protagonist_data.get("need", "自我成长与觉醒"),
            "flaw": protagonist_data.get("flaw", ""),
            "arc": protagonist_data.get("arc", ""),
        },
        "characters": characters_data,
        "ending": ending_data,
        "stages": stages_list,
    }

    # 执行锁定字段回填
    final_spec = apply_locked_fields(existing_spec, raw_spec, locked_fields)
    return validate_spec(final_spec)


# =========================================================================
# 2. 字段级无副作用润色与重写 (Universal SpecField Refiner)
# =========================================================================

def refine_spec_field(
    field_path: str,
    mode: str,
    current_value: str,
    spec_context: Optional[Dict[str, Any]] = None,
    user_hint: Optional[str] = None,
    provider_id: Optional[str] = None,
    candidates_count: int = 1,
) -> List[str]:
    """
    通用字段级润色与重写。
    纯内存无状态计算，0 磁盘写盘副作用。
    mode: 'rewrite' (重新构想全新方案) | 'polish' (保留原核心骨干，提升文学文采与表现力)
    """
    spec_context = spec_context or {}
    meta = spec_context.get("meta") or {}
    title = meta.get("title") or "未定名小说"
    genre = meta.get("genre") or "网络文学"
    logline = (spec_context.get("ideation") or {}).get("logline") or ""
    tone = (spec_context.get("ideation") or {}).get("tone") or ""

    hint_str = f"\n【创作者专属指定方向】：{user_hint}" if user_hint else ""
    context_str = (
        f"【作品基本信息】：书名《{title}》，题材：{genre}\n"
        f"【核心梗概】：{logline}\n"
        f"【基调建议】：{tone}\n"
    )

    if mode == "rewrite":
        task_prompt = (
            f"目标字段：'{field_path}'\n"
            f"当前原内容：\n{current_value or '（目前为空）'}\n"
            f"{hint_str}\n\n"
            f"请结合整部作品的题材与背景，打破当前思路，以全新创意为该字段重写一份极具吸引力、张力与合理性的内容。\n"
            f"直接输出生成后的文本内容，不要输出任何引言或解释说明。"
        )
    else:  # polish
        task_prompt = (
            f"目标字段：'{field_path}'\n"
            f"待润色原内容：\n{current_value}\n"
            f"{hint_str}\n\n"
            f"请在严格保留原内容核心事实、人设与逻辑的前提下，对其进行精雕细琢：提升行文质感、语境张力与修辞精准度，消除啰嗦与语病。\n"
            f"直接输出润色后的文本内容，不要输出任何引言或说明文字。"
        )

    sys_prompt = "你是一位精通故事理论与文学创作的资深主编兼润色大师。"
    content, _ = chat(
        [{"role": "system", "content": sys_prompt}, {"role": "user", "content": f"{context_str}\n{task_prompt}"}],
        max_tokens=1500,
        provider_id=provider_id,
    )
    cleaned = content.strip().strip('"').strip("'")
    return [cleaned]


# =========================================================================
# 3. 阶段章节节拍表 (Beat List) 推导
# =========================================================================

def generate_stage_beats(
    novel_id: str,
    stage_index: int,
    provider_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """依据阶段四大锚点及故事状态记忆，推导出本卷 6~12 章的章节节拍表 (Beat List)。"""
    spec = load_novel_spec(novel_id)
    if not spec:
        raise ValueError(f"未找到小说设定集: {novel_id}")

    runtime = load_novel_runtime(novel_id)
    stages = spec.get("stages") or []
    target_stage = next((s for s in stages if s.get("stage_index") == stage_index), None)
    if not target_stage:
        raise ValueError(f"在设定集中未找到第 {stage_index} 阶段")

    anchors = target_stage.get("anchors") or {}
    expected_ch_count = int(target_stage.get("expected_chapters") or 8)
    expected_ch_count = max(4, min(16, expected_ch_count))

    story_state = runtime.get("story_state") or {}
    rolling_summary = story_state.get("rolling_summary") or "（第一阶段，尚无前情摘要）"

    sys_prompt = "你是一位专业编剧大师，精通章节节拍表（Beat Sheet）规划与节奏控制。"
    user_prompt = (
        f"作品：《{spec.get('meta', {}).get('title')}》 题材：{spec.get('meta', {}).get('genre')}\n"
        f"一句话梗概：{spec.get('ideation', {}).get('logline')}\n"
        f"前情摘要：\n{rolling_summary}\n\n"
        f"【本卷阶段信息】：\n"
        f"第 {stage_index} 卷：《{target_stage.get('title')}》 预计章数：{expected_ch_count} 章\n"
        f"- 本卷核心诉求：{anchors.get('stage_goal')}\n"
        f"- 本卷核心阻力：{anchors.get('main_obstacle')}\n"
        f"- 阶段高潮/引爆点：{anchors.get('climax_hook')}\n"
        f"- 破局跳板/转折钩子：{anchors.get('transition_springboard')}\n\n"
        f"请将本卷精准拆解为 {expected_ch_count} 章的【章节节拍表 (Beat List)】，要求按起承转合精细编排高潮与跳板，输出 JSON：\n"
        "{\n"
        '  "beats": [\n'
        '    {\n'
        '      "chapter_offset": 1,\n'
        '      "title": "第1章标题",\n'
        '      "beat_type": "setup|escalation|climax|transition",\n'
        '      "summary": "本章1-2句核心推进（主角行动、核心冲突与留下的悬念）",\n'
        '      "planted_clues": ["本章暗埋的伏笔或细节"]\n'
        '    }\n'
        '  ]\n'
        "}\n"
        "不要输出任何额外解释文字。"
    )

    raw_beats, _ = chat(
        [{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_prompt}],
        max_tokens=3500,
        json_mode=True,
        provider_id=provider_id,
    )
    beats_obj = extract_json(raw_beats) or {}
    raw_list = beats_obj.get("beats") if isinstance(beats_obj, dict) and isinstance(beats_obj.get("beats"), list) else []

    # 计算全局章节偏移量
    md_path = get_markdown_path(novel_id)
    existing_chapters_count = 0
    if md_path.exists():
        _, chs, _ = parse_novel(md_path)
        existing_chapters_count = len(chs)

    clean_beats = []
    for idx, b in enumerate(raw_list):
        if isinstance(b, dict):
            c_offset = idx + 1
            clean_beats.append({
                "chapter_offset": c_offset,
                "global_chapter_idx": existing_chapters_count + c_offset,
                "title": str(b.get("title") or f"第 {c_offset} 章").strip(),
                "beat_type": str(b.get("beat_type") or ("climax" if c_offset == expected_ch_count - 1 else "escalation")),
                "summary": str(b.get("summary") or "").strip(),
                "planted_clues": [str(c) for c in (b.get("planted_clues") or [])],
                "is_generated": False,
            })

    # 保存进 runtime
    runtime["current_stage_index"] = stage_index
    runtime["current_stage_beats"] = clean_beats
    save_novel_runtime(novel_id, runtime)
    return clean_beats


# =========================================================================
# 4. 故事状态记忆层 (Story State Memory) 滚动抽取与更新
# =========================================================================

def update_story_state_after_chapter(
    novel_id: str,
    chapter_title: str,
    chapter_content: str,
    chapter_idx: int,
    provider_id: Optional[str] = None,
) -> Dict[str, Any]:
    """单章落盘后触发微型增量抽取，更新 rolling_summary、characters_ledger 与 clues_ledger。"""
    runtime = load_novel_runtime(novel_id)
    story_state = runtime.get("story_state") or {}
    curr_summary = story_state.get("rolling_summary") or ""
    characters_ledger = story_state.get("characters_ledger") or {}
    clues_ledger = story_state.get("clues_ledger") or []

    prompt = (
        f"【已有前情摘要】：\n{curr_summary[-1000:] if curr_summary else '（无）'}\n\n"
        f"【最新章节正文】：\n《{chapter_title}》\n{chapter_content[:2500]}\n\n"
        "请对本章发生的故事进行微型增量抽取，输出 JSON 格式：\n"
        "{\n"
        '  "summary_delta": "本章核心事件提炼 (80-150 字，谁做了什么、产生了什么结果)",\n'
        '  "character_updates": [\n'
        '    {"name": "角色名", "current_status": "最新位置/心境/负伤/变化", "relationship": "与主角关系的变动"}\n'
        '  ],\n'
        '  "new_clues": ["本章新出现的未解伏笔或秘密"],\n'
        '  "resolved_clues": ["本章已被揭开或回收的伏笔关键词"]\n'
        "}\n"
        "不要输出任何其他说明文字。"
    )
    try:
        raw_delta, _ = chat(
            [{"role": "system", "content": "你是一位敏锐的故事连续性与伏笔分析师。"}, {"role": "user", "content": prompt}],
            max_tokens=1500,
            json_mode=True,
            provider_id=provider_id,
        )
        delta_obj = extract_json(raw_delta) or {}
    except Exception:
        delta_obj = {}

    delta_summary = str(delta_obj.get("summary_delta") or "").strip()
    if delta_summary:
        if curr_summary:
            curr_summary += f"\n- {delta_summary}"
        else:
            curr_summary = delta_summary

    # 滑动窗口压缩：超过 1500 字触发 Rollup Compression
    if len(curr_summary) > 1500:
        compress_prompt = (
            f"以下是小说的长篇前情摘要，因篇幅过长，请在保留所有主线因果、核心危机与人物关系的前提下，"
            f"将其精简浓缩至 800 字以内的紧凑摘要：\n\n{curr_summary}"
        )
        try:
            compressed, _ = chat(
                [{"role": "system", "content": "你精通高信息密度的前情提要提炼。"}, {"role": "user", "content": compress_prompt}],
                max_tokens=1200,
                provider_id=provider_id,
            )
            if compressed and len(compressed.strip()) > 50:
                curr_summary = compressed.strip()
        except Exception:
            pass

    # 更新角色账本
    for cu in delta_obj.get("character_updates") or []:
        if isinstance(cu, dict) and cu.get("name"):
            cname = cu["name"]
            characters_ledger[cname] = {
                "current_status": cu.get("current_status", ""),
                "relationship_with_protagonist": cu.get("relationship", ""),
                "updated_at_chapter": chapter_idx,
            }

    # 更新伏笔账本
    for nc in delta_obj.get("new_clues") or []:
        if isinstance(nc, str) and nc.strip():
            clues_ledger.append({
                "clue_id": f"clue_{uuid.uuid4().hex[:6]}",
                "content": nc.strip(),
                "planted_at_chapter": chapter_idx,
                "status": "planted",
                "resolved_at_chapter": None,
            })

    resolved_keywords = [str(rc).strip() for rc in (delta_obj.get("resolved_clues") or []) if str(rc).strip()]
    for clue in clues_ledger:
        if clue.get("status") == "planted":
            for kw in resolved_keywords:
                if kw in clue.get("content", ""):
                    clue["status"] = "revealed"
                    clue["resolved_at_chapter"] = chapter_idx
                    break

    story_state["rolling_summary"] = curr_summary
    story_state["characters_ledger"] = characters_ledger
    story_state["clues_ledger"] = clues_ledger
    runtime["story_state"] = story_state
    save_novel_runtime(novel_id, runtime)
    return story_state


# =========================================================================
# 5. 长任务执行器与 SSE 流式推送 (StageRunner)
# =========================================================================

class StageRunner:
    def __init__(self, novel_id: str, stage_index: int, provider_id: Optional[str] = None):
        self.novel_id = novel_id
        self.stage_index = stage_index
        self.provider_id = provider_id
        self.job_id = f"job_{sanitize_filename(novel_id)}_{stage_index}_{uuid.uuid4().hex[:6]}"
        self.event_queue: queue.Queue = queue.Queue(maxsize=1000)
        self.is_paused = False
        self.is_cancelled = False
        self.thread: Optional[threading.Thread] = None

    def emit(self, event_type: str, data: Any):
        payload = {
            "job_id": self.job_id,
            "novel_id": self.novel_id,
            "stage_index": self.stage_index,
            "timestamp": now_iso(),
            "data": data,
        }
        self.event_queue.put((event_type, payload))

    def start(self):
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def pause(self):
        self.is_paused = True
        runtime = load_novel_runtime(self.novel_id)
        runtime["status"] = "paused"
        save_novel_runtime(self.novel_id, runtime)
        self.emit("status_change", {"status": "paused"})

    def resume(self):
        self.is_paused = False
        runtime = load_novel_runtime(self.novel_id)
        runtime["status"] = "writing"
        save_novel_runtime(self.novel_id, runtime)
        self.emit("status_change", {"status": "writing"})

    def cancel(self):
        self.is_cancelled = True
        runtime = load_novel_runtime(self.novel_id)
        runtime["status"] = "idle"
        runtime["active_job"] = None
        save_novel_runtime(self.novel_id, runtime)
        self.emit("status_change", {"status": "cancelled"})

    def _run(self):
        stem = sanitize_filename(self.novel_id)
        if not acquire_book(stem, holder=self.job_id):
            self.emit("error", {"message": f"小说《{stem}》已有正在运行的任务，请稍后"})
            return

        try:
            spec = load_novel_spec(self.novel_id)
            if not spec:
                self.emit("error", {"message": "找不到 spec 文件"})
                return

            runtime = load_novel_runtime(self.novel_id)
            beats = runtime.get("current_stage_beats") or []
            if not beats:
                beats = generate_stage_beats(self.novel_id, self.stage_index, self.provider_id)

            runtime["status"] = "writing"
            runtime["active_job"] = {
                "job_id": self.job_id,
                "stage_index": self.stage_index,
                "total_stage_chapters": len(beats),
                "started_at": now_iso(),
                "last_heartbeat": now_iso(),
            }
            save_novel_runtime(self.novel_id, runtime)
            self.emit("init", {"total_chapters": len(beats)})

            md_path = get_markdown_path(self.novel_id)
            if not md_path.exists():
                init_novel_three_layers(self.novel_id, spec.get("meta", {}).get("title", stem), spec, runtime)

            meta, chapters, _ = parse_novel(md_path)

            for beat in beats:
                if beat.get("is_generated"):
                    continue

                while self.is_paused:
                    if self.is_cancelled:
                        break
                    time.sleep(0.5)

                if self.is_cancelled:
                    self.emit("cancelled", {"message": "任务已取消"})
                    return

                ch_offset = beat.get("chapter_offset", 1)
                global_idx = len(chapters) + 1
                ch_title = beat.get("title") or f"第 {global_idx} 章"

                self.emit("chapter_start", {
                    "chapter_offset": ch_offset,
                    "global_chapter_idx": global_idx,
                    "title": ch_title,
                    "beat_type": beat.get("beat_type"),
                    "summary": beat.get("summary"),
                })

                # 构建单章提示词
                story_state = runtime.get("story_state") or {}
                prev_context = context_from(chapters, limit=2)
                per_words = int(spec.get("meta", {}).get("target_words_per_chapter") or 2500)

                user_prompt = (
                    f"【小说世界与设定】：\n"
                    f"题材：{spec.get('meta', {}).get('genre')}\n"
                    f"世界观背景：{(spec.get('worldview') or {}).get('background')}\n"
                    f"主角：{(spec.get('protagonist') or {}).get('name')} (Want: {(spec.get('protagonist') or {}).get('want')} / Need: {(spec.get('protagonist') or {}).get('need')})\n\n"
                    f"【长篇前情提要】：\n{story_state.get('rolling_summary') or '（无前情）'}\n\n"
                    f"【本章编写指引与节拍要求】：\n"
                    f"本章预定标题：{ch_title}\n"
                    f"节拍定位：{beat.get('beat_type')}\n"
                    f"情节核心推进目标：{beat.get('summary')}\n"
                    f"需注意/带出的伏笔：{', '.join(beat.get('planted_clues') or [])}\n\n"
                    f"【承接上文正文片段】：\n{prev_context or '（这是全新起点章节）'}\n\n"
                    f"请直接创作【{ch_title}】完整正文，篇幅约 {per_words} 字，要求语言生动扎实，严禁重复前文。"
                )

                def on_token(token):
                    if self.is_cancelled:
                        raise RuntimeError("Job Cancelled")
                    self.emit("token", {"token": token})

                # 生成正文
                body = generate_text(
                    lambda sofar: [
                        {"role": "system", "content": ORIGINAL_SYS},
                        {"role": "user", "content": user_prompt + (f"\n继续写：{sofar}" if sofar else "")},
                    ],
                    max_chars=int(per_words * 1.5),
                    provider_id=self.provider_id,
                    on_chunk=on_token,
                )

                # 正文落盘
                with lock_novel(stem):
                    meta["current_volume"] = self.stage_index
                    chapters.append({"title": ch_title, "content": body})
                    meta["total_words"] = sum(len(re.sub(r"\s", "", c["content"])) for c in chapters)
                    meta["updated_at"] = now_iso()
                    write_novel(md_path, meta, chapters)

                # 更新故事状态与节拍标记
                beat["is_generated"] = True
                save_novel_runtime(self.novel_id, runtime)
                new_story_state = update_story_state_after_chapter(
                    self.novel_id, ch_title, body, global_idx, self.provider_id
                )

                self.emit("chapter_end", {
                    "global_chapter_idx": global_idx,
                    "title": ch_title,
                    "words": len(re.sub(r"\s", "", body)),
                })
                self.emit("story_state_sync", new_story_state)

            # 本阶段全部完成，进入检查点评审态
            runtime["status"] = "awaiting_review"
            runtime["active_job"] = None
            save_novel_runtime(self.novel_id, runtime)
            self.emit("stage_complete", {
                "stage_index": self.stage_index,
                "message": f"第 {self.stage_index} 阶段全部章节生成完毕，请复盘检查点报告",
            })

        except Exception as e:
            self.emit("error", {"error": str(e)})
            runtime = load_novel_runtime(self.novel_id)
            runtime["status"] = "failed"
            save_novel_runtime(self.novel_id, runtime)
        finally:
            release_book(stem)
            with _RUNNER_LOCK:
                ACTIVE_RUNNERS.pop(self.job_id, None)


def start_stage_generation(novel_id: str, stage_index: int, provider_id: Optional[str] = None) -> StageRunner:
    stem = sanitize_filename(novel_id)
    with _RUNNER_LOCK:
        for r in ACTIVE_RUNNERS.values():
            if r.novel_id == stem and not r.is_cancelled:
                raise RuntimeError(f"小说《{stem}》已有任务运行中 (job_id: {r.job_id})")

        runner = StageRunner(stem, stage_index, provider_id)
        ACTIVE_RUNNERS[runner.job_id] = runner
        runner.start()
        return runner


def get_stage_runner(job_id: str) -> Optional[StageRunner]:
    with _RUNNER_LOCK:
        return ACTIVE_RUNNERS.get(job_id)


# =========================================================================
# 6. 阶段检查点偏差评估与大纲回写闭环 (Checkpoint Review & Write-Back)
# =========================================================================

def evaluate_stage_checkpoint(novel_id: str, stage_index: int, provider_id: Optional[str] = None) -> Dict[str, Any]:
    """汇总分析当前阶段正文与设定集锚点的达成度与偏差，并提出下一阶段修订建议。"""
    spec = load_novel_spec(novel_id)
    if not spec:
        raise ValueError("未找到小说设定集")
    runtime = load_novel_runtime(novel_id)

    stages = spec.get("stages") or []
    curr_stage = next((s for s in stages if s.get("stage_index") == stage_index), None)
    if not curr_stage:
        raise ValueError(f"未找到第 {stage_index} 阶段")

    anchors = curr_stage.get("anchors") or {}
    story_state = runtime.get("story_state") or {}

    prompt = (
        f"作品：《{spec.get('meta', {}).get('title')}》 阶段：第 {stage_index} 卷《{curr_stage.get('title')}》\n"
        f"原设阶段目标：{anchors.get('stage_goal')}\n"
        f"原设阶段高潮：{anchors.get('climax_hook')}\n"
        f"原设破局跳板：{anchors.get('transition_springboard')}\n\n"
        f"实际正文生成后提炼的故事全貌：\n{story_state.get('rolling_summary')}\n\n"
        "请做阶段复盘偏差评估，并针对后续分卷大纲给出自适应调整建议，输出 JSON：\n"
        "{\n"
        '  "goal_achievement_pct": 90,\n'
        '  "deviation_summary": "原设高潮与实际正文的契合与偏差总结 (80-150字)",\n'
        '  "character_growth_notes": "主角及重要配角在这一卷的心态与实力实际跃迁",\n'
        '  "suggested_next_stage_adjustments": {\n'
        f'    "stage_index": {stage_index + 1},\n'
        '    "recommended_stage_goal": "推荐修订的下一阶段诉求",\n'
        '    "recommended_main_obstacle": "推荐修订的下一阶段阻力",\n'
        '    "recommended_climax_hook": "推荐修订的下一阶段高潮",\n'
        '    "recommended_transition": "推荐修订的下一阶段跳板"\n'
        '  }\n'
        "}\n"
        "不要输出其他多余文字。"
    )
    raw_eval, _ = chat(
        [{"role": "system", "content": "你是一位敏锐严谨的小说总编审，精通大纲追踪与剧情对齐。"}, {"role": "user", "content": prompt}],
        max_tokens=2000,
        json_mode=True,
        provider_id=provider_id,
    )
    report = extract_json(raw_eval) or {}

    # 记录进 runtime 历史
    checkpoints = runtime.get("checkpoints") or []
    checkpoints.append({
        "stage_index": stage_index,
        "completed_at": now_iso(),
        "report": report,
    })
    runtime["checkpoints"] = checkpoints
    save_novel_runtime(novel_id, runtime)
    return report


def apply_checkpoint_writeback(novel_id: str, stage_index: int, spec_modifications: Dict[str, Any]) -> bool:
    """创作者点击确认采纳后，将检查点建议自适应回写至 novel_spec.json 的后续阶段锚点。"""
    spec = load_novel_spec(novel_id)
    if not spec:
        raise ValueError("未找到小说设定集")

    # 更新后续 stages 锚点
    next_stages_data = spec_modifications.get("stages") or []
    if next_stages_data:
        spec["stages"] = next_stages_data
    save_novel_spec(novel_id, spec)

    # 推进 runtime 进入下一阶段准备态
    runtime = load_novel_runtime(novel_id)
    runtime["current_stage_index"] = stage_index + 1
    runtime["status"] = "idle"
    runtime["current_stage_beats"] = []
    save_novel_runtime(novel_id, runtime)
    return True
