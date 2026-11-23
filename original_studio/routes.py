"""Flask Blueprint routes for Original Novel Studio."""

import json
import queue
import time
from typing import Any, Dict

from flask import Blueprint, Response, jsonify, request

from app import get_provider, sanitize_filename
from original_studio.engine import (
    ACTIVE_RUNNERS,
    apply_checkpoint_writeback,
    deduce_creative_pipeline,
    evaluate_stage_checkpoint,
    generate_stage_beats,
    get_stage_runner,
    refine_spec_field,
    start_stage_generation,
)
from original_studio.models import (
    load_novel_runtime,
    load_novel_spec,
    save_novel_runtime,
    save_novel_spec,
    validate_spec,
)

original_studio_bp = Blueprint("original_studio", __name__, url_prefix="/api/novel/original")


# =========================================================================
# 1. 设定集存取接口 (Creative Spec)
# =========================================================================

@original_studio_bp.get("/spec")
def api_get_spec():
    novel_id = request.args.get("novel_id") or request.args.get("name") or ""
    if not novel_id:
        return jsonify({"code": 400, "error": "缺少 novel_id 参数"}), 400
    stem = sanitize_filename(novel_id)
    spec = load_novel_spec(stem)
    if not spec:
        return jsonify({"code": 404, "error": f"未找到小说设定集: {stem}"}), 404
    return jsonify({"code": 200, "msg": "success", "data": {"novel_id": stem, "spec": spec}})


@original_studio_bp.put("/spec")
def api_save_spec():
    data = request.get_json(force=True) or {}
    novel_id = data.get("novel_id") or ""
    spec_data = data.get("spec")
    if not novel_id or not spec_data:
        return jsonify({"code": 400, "error": "参数 novel_id 和 spec 均为必填"}), 400

    stem = sanitize_filename(novel_id)
    try:
        save_novel_spec(stem, spec_data)
        return jsonify({"code": 200, "msg": "spec saved successfully", "data": {"novel_id": stem}})
    except ValueError as e:
        return jsonify({"code": 400, "error": f"设定集校验失败: {str(e)}"}), 400
    except Exception as e:
        return jsonify({"code": 500, "error": f"保存设定集异常: {str(e)}"}), 500


# =========================================================================
# 2. 4 步链式深度推演 (Chained Deduction)
# =========================================================================

@original_studio_bp.post("/deduce")
def api_deduce_creative():
    data = request.get_json(force=True) or {}
    title = (data.get("title") or "").strip()
    genre = (data.get("genre") or "").strip()
    if not title or not genre:
        return jsonify({"code": 400, "error": "字段 title 与 genre 均为必填项"}), 400

    selected_trope = data.get("selected_trope")
    user_pitch = data.get("user_pitch")
    meta_params = data.get("meta_params") or {}
    locked_fields = data.get("locked_fields") or []
    provider_id = data.get("provider_id")
    novel_id = data.get("novel_id")

    existing_spec = None
    if novel_id:
        existing_spec = load_novel_spec(sanitize_filename(novel_id))

    try:
        spec = deduce_creative_pipeline(
            title=title,
            genre=genre,
            selected_trope=selected_trope,
            user_pitch=user_pitch,
            meta_params=meta_params,
            locked_fields=locked_fields,
            provider_id=provider_id,
            existing_spec=existing_spec,
        )
        return jsonify({"code": 200, "msg": "推演成功", "data": spec})
    except Exception as e:
        return jsonify({"code": 500, "error": f"推演失败: {str(e)}"}), 500


# =========================================================================
# 3. 字段级无副作用润色与重写 (Universal SpecField Refiner)
# =========================================================================

@original_studio_bp.post("/refine-field")
def api_refine_field():
    data = request.get_json(force=True) or {}
    field_path = (data.get("field_path") or "").strip()
    mode = (data.get("mode") or "").strip()
    current_value = str(data.get("current_value") or "")

    if not field_path:
        return jsonify({"code": 400, "error": "参数 field_path 不能为空"}), 400
    if mode not in ("rewrite", "polish"):
        return jsonify({"code": 400, "error": "参数 mode 必须为 'rewrite' 或 'polish'"}), 400

    if mode == "polish" and not current_value.strip():
        return jsonify({"code": 400, "error": "润色模式下待润色内容不能为空"}), 400

    user_hint = data.get("user_hint")
    spec_context = data.get("spec_context") or {}
    provider_id = data.get("provider_id")
    candidates_count = int(data.get("candidates_count") or 1)

    try:
        candidates = refine_spec_field(
            field_path=field_path,
            mode=mode,
            current_value=current_value,
            spec_context=spec_context,
            user_hint=user_hint,
            provider_id=provider_id,
            candidates_count=candidates_count,
        )
        return jsonify({
            "code": 200,
            "msg": "success",
            "data": {
                "field_path": field_path,
                "mode": mode,
                "candidates": candidates,
            },
        })
    except Exception as e:
        return jsonify({"code": 500, "error": f"字段精修失败: {str(e)}"}), 500


# =========================================================================
# 4. 章节节拍表 (Beat List) 推导与保存
# =========================================================================

@original_studio_bp.post("/stage/beats")
def api_stage_beats():
    data = request.get_json(force=True) or {}
    novel_id = (data.get("novel_id") or "").strip()
    stage_index = int(data.get("stage_index") or 1)
    action = (data.get("action") or "generate").strip()

    if not novel_id:
        return jsonify({"code": 400, "error": "参数 novel_id 必填"}), 400

    stem = sanitize_filename(novel_id)
    if action == "generate":
        provider_id = data.get("provider_id")
        try:
            beats = generate_stage_beats(stem, stage_index, provider_id)
            return jsonify({"code": 200, "msg": "beats generated", "data": {"stage_index": stage_index, "beats": beats}})
        except Exception as e:
            return jsonify({"code": 500, "error": f"生成节拍表失败: {str(e)}"}), 500

    elif action == "save":
        beats_list = data.get("beats")
        if not isinstance(beats_list, list):
            return jsonify({"code": 400, "error": "action 为 save 时 beats 必须为数组"}), 400
        runtime = load_novel_runtime(stem)
        runtime["current_stage_index"] = stage_index
        runtime["current_stage_beats"] = beats_list
        save_novel_runtime(stem, runtime)
        return jsonify({"code": 200, "msg": "beats saved", "data": {"stage_index": stage_index, "beats": beats_list}})

    else:
        return jsonify({"code": 400, "error": f"未知 action: {action}"}), 400


# =========================================================================
# 5. 分卷长任务启动与控制
# =========================================================================

@original_studio_bp.post("/stage/start")
def api_stage_start():
    data = request.get_json(force=True) or {}
    novel_id = (data.get("novel_id") or "").strip()
    stage_index = int(data.get("stage_index") or 1)
    provider_id = data.get("provider_id")

    if not novel_id:
        return jsonify({"code": 400, "error": "缺少 novel_id 参数"}), 400

    stem = sanitize_filename(novel_id)
    try:
        runner = start_stage_generation(stem, stage_index, provider_id)
        return jsonify({
            "code": 202,
            "msg": "stage generation started",
            "data": {
                "job_id": runner.job_id,
                "stream_url": f"/api/novel/original/stage/stream/{runner.job_id}",
            },
        }), 202
    except RuntimeError as e:
        return jsonify({"code": 409, "error": str(e)}), 409
    except Exception as e:
        return jsonify({"code": 500, "error": f"启动任务失败: {str(e)}"}), 500


@original_studio_bp.post("/stage/control")
def api_stage_control():
    data = request.get_json(force=True) or {}
    job_id = (data.get("job_id") or "").strip()
    action = (data.get("action") or "").strip()

    if not job_id or not action:
        return jsonify({"code": 400, "error": "参数 job_id 与 action 均为必填"}), 400

    runner = get_stage_runner(job_id)
    if not runner:
        return jsonify({"code": 404, "error": f"未找到运行中任务: {job_id}"}), 404

    if action == "pause":
        runner.pause()
        return jsonify({"code": 200, "msg": "job paused"})
    elif action == "resume":
        runner.resume()
        return jsonify({"code": 200, "msg": "job resumed"})
    elif action == "cancel":
        runner.cancel()
        return jsonify({"code": 200, "msg": "job cancelled"})
    else:
        return jsonify({"code": 400, "error": f"未知 action: {action}"}), 400


@original_studio_bp.get("/stage/status/<job_id>")
def api_stage_status(job_id: str):
    runner = get_stage_runner(job_id)
    if runner:
        runtime = load_novel_runtime(runner.novel_id)
        return jsonify({
            "code": 200,
            "data": {
                "job_id": job_id,
                "novel_id": runner.novel_id,
                "stage_index": runner.stage_index,
                "status": runtime.get("status"),
                "is_active": True,
            },
        })
    return jsonify({"code": 200, "data": {"job_id": job_id, "is_active": False, "status": "finished"}})


# =========================================================================
# 6. HTML5 SSE 实时打字机推送通道
# =========================================================================

@original_studio_bp.get("/stage/stream/<job_id>")
def api_stage_stream(job_id: str):
    runner = get_stage_runner(job_id)
    if not runner:
        return jsonify({"code": 404, "error": f"未找到活跃任务流: {job_id}"}), 404

    def event_stream():
        # 发送建立连接 handshake
        yield f"event: connect\ndata: {json.dumps({'job_id': job_id, 'status': 'connected'})}\n\n"
        while True:
            try:
                event_type, payload = runner.event_queue.get(timeout=1.0)
                yield f"event: {event_type}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
                if event_type in ("stage_complete", "cancelled", "error"):
                    break
            except queue.Empty:
                if runner.is_cancelled:
                    break
                # 发送 SSE keep-alive 注释行
                yield ": ping\n\n"

    response = Response(event_stream(), mimetype="text/event-stream")
    response.headers["Cache-Control"] = "no-cache"
    response.headers["X-Accel-Buffering"] = "no"
    return response


# =========================================================================
# 7. 阶段检查点偏差评估与大纲自适应回写
# =========================================================================

@original_studio_bp.post("/stage/checkpoint")
def api_stage_checkpoint():
    data = request.get_json(force=True) or {}
    novel_id = (data.get("novel_id") or "").strip()
    stage_index = int(data.get("stage_index") or 1)
    action = (data.get("action") or "evaluate").strip()

    if not novel_id:
        return jsonify({"code": 400, "error": "缺少 novel_id 参数"}), 400

    stem = sanitize_filename(novel_id)
    provider_id = data.get("provider_id")

    if action == "evaluate":
        try:
            report = evaluate_stage_checkpoint(stem, stage_index, provider_id)
            return jsonify({"code": 200, "msg": "evaluation completed", "data": report})
        except Exception as e:
            return jsonify({"code": 500, "error": f"检查点偏差评估失败: {str(e)}"}), 500

    elif action == "accept_and_writeback":
        spec_modifications = data.get("spec_modifications") or {}
        try:
            apply_checkpoint_writeback(stem, stage_index, spec_modifications)
            return jsonify({
                "code": 200,
                "msg": "checkpoint applied and spec updated",
                "data": {"next_stage_index": stage_index + 1, "status": "idle"},
            })
        except Exception as e:
            return jsonify({"code": 500, "error": f"回写大纲失败: {str(e)}"}), 500

    else:
        return jsonify({"code": 400, "error": f"未知 action: {action}"}), 400
