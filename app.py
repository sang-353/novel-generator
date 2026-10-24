# -*- coding: utf-8 -*-
"""个人小说生成器 —— 本地 Flask 后端

功能：
- 原创生成：填写设定 -> 生成大纲 -> 逐章写作
- 续写/同人：分析原作文风 -> 模仿风格续写或改写
- 小说以 Markdown 文件存储于 novels/ 目录，头部为 JSON front matter

运行：python app.py  然后浏览器打开 http://127.0.0.1:8000
"""
import hashlib
import hmac
import json
import os
import re
import secrets
import socket
import sys
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

# 依赖引导：优先使用工作区 pylibs 目录中安装的依赖（pip --target 安装）
_LIBS = Path(__file__).resolve().parent / "pylibs"
if _LIBS.exists() and str(_LIBS) not in sys.path:
    sys.path.insert(0, str(_LIBS))

import requests
from flask import Flask, jsonify, request, send_from_directory

BASE_DIR = Path(__file__).resolve().parent
NOVELS_DIR = BASE_DIR / "novels"
STATIC_DIR = BASE_DIR / "static"
CONFIG_FILE = BASE_DIR / "config.json"
NOVELS_DIR.mkdir(exist_ok=True)

app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="/static")

# ---------------------------------------------------------------------------
# 配置（多 provider：每个大模型 API 一个配置项）
# ---------------------------------------------------------------------------
DEFAULT_PROVIDER = {
    "id": "deepseek",
    "name": "DeepSeek",
    "base_url": "https://api.deepseek.com",
    "api_key": "",
    "model": "deepseek-chat",
    "temperature": 1.0,
}


def now_iso():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _migrate_legacy_config(data):
    """旧版 config.json 结构迁移为 providers 数组。"""
    if "providers" in data and isinstance(data["providers"], list):
        return data
    legacy = {**DEFAULT_PROVIDER, **{k: v for k, v in data.items() if k in DEFAULT_PROVIDER}}
    return {"providers": [legacy], "active_provider": legacy["id"]}


def load_config():
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            return _migrate_legacy_config(data)
        except Exception:
            pass
    return {"providers": [dict(DEFAULT_PROVIDER)], "active_provider": "deepseek"}


def save_config(cfg):
    CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def get_provider(provider_id=None):
    """按 id 取 provider；缺省返回当前默认 provider。不存在时回退到第一个。"""
    cfg = load_config()
    providers = cfg.get("providers") or []
    if provider_id:
        for p in providers:
            if p.get("id") == provider_id:
                return p
    active = cfg.get("active_provider")
    for p in providers:
        if p.get("id") == active:
            return p
    return providers[0] if providers else dict(DEFAULT_PROVIDER)


def get_provider_meta(provider):
    """provider 展示名：DeepSeek (deepseek-chat)"""
    name = provider.get("name") or provider.get("id") or "模型"
    model = provider.get("model") or ""
    return f"{name} ({model})".strip()


def mask_key(key):
    if not key:
        return ""
    if len(key) <= 8:
        return "*" * len(key)
    return key[:4] + "*" * 8 + key[-4:]


# ---------------------------------------------------------------------------
# 隐私书架（密码以加盐 PBKDF2 哈希存于 config.json；解锁令牌只存内存）
# ---------------------------------------------------------------------------
PRIVACY_ITERATIONS = 200_000
PRIVACY_TOKEN_TTL = 30 * 60          # 解锁状态有效期（秒）
PRIVACY_TOKENS = {}                  # token -> 过期时间戳
PRIVACY_LOCK = threading.Lock()


def _privacy_record(cfg=None):
    cfg = cfg if cfg is not None else load_config()
    rec = cfg.get("privacy") or {}
    return rec if rec.get("hash") and rec.get("salt") else None


def privacy_enabled():
    return _privacy_record() is not None


def hash_password(password):
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                             bytes.fromhex(salt), PRIVACY_ITERATIONS)
    return {"salt": salt, "hash": dk.hex(), "iterations": PRIVACY_ITERATIONS}


def verify_password(password, rec):
    if not rec:
        return False
    try:
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                                 bytes.fromhex(rec["salt"]), int(rec["iterations"]))
    except Exception:
        return False
    return hmac.compare_digest(dk.hex(), rec.get("hash", ""))


def issue_privacy_token():
    tok = secrets.token_urlsafe(24)
    now = time.time()
    with PRIVACY_LOCK:
        for k in [k for k, exp in PRIVACY_TOKENS.items() if exp < now]:
            PRIVACY_TOKENS.pop(k, None)
        PRIVACY_TOKENS[tok] = now + PRIVACY_TOKEN_TTL
    return tok


def privacy_token_valid(token):
    if not token:
        return False
    with PRIVACY_LOCK:
        exp = PRIVACY_TOKENS.get(token)
        if not exp:
            return False
        if exp < time.time():
            PRIVACY_TOKENS.pop(token, None)
            return False
        return True


def revoke_privacy_token(token):
    with PRIVACY_LOCK:
        PRIVACY_TOKENS.pop(token, None)


def can_access_private(token):
    """未设置密码时隐私书架不设防（没有可校验的凭据）；设置后必须持有效令牌。"""
    if not privacy_enabled():
        return True
    return privacy_token_valid(token)


def _request_token(payload=None):
    """令牌来源：query 参数或 JSON body。"""
    tok = request.args.get("token")
    if not tok and isinstance(payload, dict):
        tok = payload.get("token")
    return (tok or "").strip()


def _deny_private(meta, token):
    """私密书籍且令牌无效 -> True（应拒绝访问）。"""
    return bool(meta.get("private")) and not can_access_private(token)


def _mask_private_title(meta, title, token):
    """回收站/章节备份列表中对隐私书脱敏。"""
    if meta.get("private") and not can_access_private(token):
        return "（隐私书籍）"
    return title


# ---------------------------------------------------------------------------
# 大模型调用（OpenAI 兼容，多 provider）
# ---------------------------------------------------------------------------
def chat(messages, max_tokens=2000, temperature=None, json_mode=False, timeout=300, provider_id=None, provider=None):
    """调用 chat/completions，返回 (content, finish_reason)。失败自动重试 3 次。

    provider_id：指定使用哪个大模型配置（缺省用默认 provider）。
    provider：直接传入 provider 配置 dict（用于测试尚未保存的新增模型）。
    """
    if provider is None:
        provider = get_provider(provider_id)
    if not provider or not provider.get("api_key"):
        raise RuntimeError("未配置 API Key，请先在「设置」页填写。")
    url = (provider["base_url"] or "").rstrip("/") + "/chat/completions"
    payload = {
        "model": provider["model"],
        "messages": messages,
        "temperature": temperature if temperature is not None else provider.get("temperature", 1.0),
        "max_tokens": max_tokens,
        "stream": False,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    headers = {"Authorization": f"Bearer {provider['api_key']}", "Content-Type": "application/json"}
    last_err = None
    for attempt in range(3):
        try:
            r = requests.post(url, json=payload, headers=headers, timeout=timeout)
            if r.status_code == 200:
                data = r.json()
                choice = data["choices"][0]
                return choice["message"]["content"], choice.get("finish_reason")
            last_err = f"HTTP {r.status_code}: {r.text[:300]}"
        except requests.RequestException as e:
            last_err = str(e)
        time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"调用模型失败（已重试 3 次）：{last_err}")


def generate_text(messages_fn, max_chars, max_tokens_per_call=8000, temperature=None, provider_id=None):
    """循环调用模型直到章节写完（finish_reason 非 length）或达到字数上限。

    messages_fn(sofar) -> messages：sofar 为本章已生成内容，用于上下文续写。
    """
    sofar = ""
    while True:
        msgs = messages_fn(sofar)
        content, reason = chat(msgs, max_tokens=max_tokens_per_call, temperature=temperature, provider_id=provider_id)
        sofar += content
        if reason != "length" or len(sofar) >= max_chars:
            break
    return sofar


def extract_json(text):
    """从模型输出中提取 JSON 对象（容忍 ```json 围栏与多余文字）。

    只接受对象（dict）；`null`/数组/标量视为无效并抛错，避免调用方拿到 None。
    """
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
        raise ValueError("模型返回的不是 JSON 对象")
    except Exception:
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            try:
                obj = json.loads(m.group(0))
                if isinstance(obj, dict):
                    return obj
            except Exception:
                pass
    raise RuntimeError("模型返回的不是有效 JSON：" + text[:200])


def chunk_text(text, chunk_size=8000, overlap=500):
    """将长文本切成带重叠的块，防止剧情在切点被截断。"""
    text = text.strip()
    if len(text) <= chunk_size:
        return [text]
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunks.append(text[start:end])
        if end >= len(text):
            break
        start = max(start + chunk_size - overlap, start + 1)
    return chunks


# ---------------------------------------------------------------------------
# 小说文件存取
# ---------------------------------------------------------------------------
def sanitize_filename(name):
    name = re.sub(r'[\\/:*?"<>|\r\n\t]', "_", name).strip()
    name = re.sub(r"\s+", " ", name)[:60]
    return name or "未命名小说"


def unique_path(title):
    base = sanitize_filename(title)
    p = NOVELS_DIR / f"{base}.md"
    i = 2
    while p.exists():
        p = NOVELS_DIR / f"{base}({i}).md"
        i += 1
    return p


def parse_novel(path, repair=True):
    """解析 novels/*.md -> (meta, chapters, words)

    repair=True 时自动修正「标题被误当正文」的存量章节；返回的 chapters
    已修正，调用方可写回文件。
    """
    text = path.read_text(encoding="utf-8")
    meta = {}
    body = text
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            try:
                meta = json.loads(parts[1])
            except Exception:
                meta = {}
            body = parts[2]
    chapters = []
    cur_title = None
    cur_lines = []

    def flush():
        nonlocal cur_title
        if cur_title is not None:
            chapters.append({"title": cur_title, "content": "".join(cur_lines).strip()})
        cur_title = None
        cur_lines.clear()

    for line in body.splitlines(keepends=True):
        if line.startswith("# "):
            flush()
            cur_title = line[2:].strip()
        else:
            cur_lines.append(line)
    flush()
    if repair:
        for ch in chapters:
            repair_chapter_title(ch)
    words = sum(len(re.sub(r"\s", "", c["content"])) for c in chapters)
    meta.setdefault("title", path.stem)
    return meta, chapters, words


def write_novel(path, meta, chapters):
    meta = dict(meta)
    meta["updated"] = now_iso()
    parts = ["---", json.dumps(meta, ensure_ascii=False), "---", ""]
    for c in chapters:
        parts.append(f"# {c['title']}")
        parts.append("")
        parts.append(c["content"])
        parts.append("")
    path.write_text("\n".join(parts), encoding="utf-8")


def safe_novel_path(name):
    """校验书名参数，防止路径穿越，返回 Path 或 None。"""
    if not name or name != sanitize_filename(name):
        return None
    p = NOVELS_DIR / f"{name}.md"
    return p if p.exists() else None


TITLE_RE = re.compile(
    r"^\s*[【\[]?\s*(?:#+\s*)?(第\s*\d+\s*(?:章|回|节|话|卷)|Chapter\s*\d+)\s*[:：·—\-、]?\s*(.*?)\s*[】\]]?\s*$",
    re.IGNORECASE,
)

# 标题尾部需清理的标点（括号内带句号的标题：『第58章 标题。』）
_TITLE_TRAIL = re.compile(r"[。，,！!？?；;：:、·—\-]+$")


def _clean_title_suffix(suffix):
    suffix = suffix.strip()
    return _TITLE_TRAIL.sub("", suffix).strip()


def _format_num_part(num_part):
    num_part = num_part.strip()
    if num_part.lower().startswith("chapter"):
        # 统一为 Chapter N
        m = re.search(r"(\d+)", num_part)
        return f"Chapter {m.group(1)}" if m else num_part
    return re.sub(r"\s+", "", num_part)


def extract_title_from_line(line):
    """从标题行提取 (title, num)。识别失败返回 (None, None)。"""
    m = TITLE_RE.match(line.strip())
    if not m:
        return None, None
    num_part = _format_num_part(m.group(1))
    suffix = _clean_title_suffix(m.group(2))
    title = f"{num_part} {suffix}".strip() if suffix else num_part
    return title, chapter_number_from(num_part)


def chapter_title_from(content, idx):
    """从章节正文提取标题；正文首行为标题行时拆出。返回 (title, body)

    支持格式：第X章 标题 / 第X章：标题 / 【第X章 标题】 / # 第X章 标题 /
    Chapter X: Title 等。识别失败则用「第X章」兜底。
    """
    s = content.strip()
    if not s:
        return f"第{idx}章", ""
    lines = s.splitlines()
    first = lines[0].strip()
    title, _ = extract_title_from_line(first)
    if title:
        return title, "\n".join(lines[1:]).strip()
    return f"第{idx}章", s


def chapter_number_from(title):
    """从章节标题提取编号（第5章/第5回/第五章…），失败返回 None。"""
    m = re.search(r"第\s*(\d+)\s*(?:章|回|节|话|卷)", title or "")
    return int(m.group(1)) if m else None


def repair_chapter_title(chapter):
    """存量数据修正：若标题是纯编号（如「第58章」）但正文首行是完整标题
    （如「【第58章 标题】」），则把标题从正文提取回目录，避免标题丢在正文里。
    返回 True 表示发生了修正。"""
    title = (chapter.get("title") or "").strip()
    content = (chapter.get("content") or "").strip()
    num = chapter_number_from(title)
    if num is None or not content:
        return False  # 无编号章节（原作等）不修正
    # 标题已是「第X章 副标题」形式则无需修正
    if title != f"第{num}章":
        return False
    first = content.splitlines()[0].strip()
    new_title, new_num = extract_title_from_line(first)
    if not new_title or new_num is None:
        return False
    # 新标题编号必须与章节编号一致才提取（避免误把正文首行当标题）
    if new_num != num:
        return False
    chapter["title"] = new_title
    chapter["content"] = "\n".join(content.splitlines()[1:]).strip()
    return True


def max_chapter_number(chapters, original_count=0):
    """现有章节中的最大编号（跳过原作章节），用于续写接续编号。"""
    nums = [chapter_number_from(c["title"]) for c in chapters[original_count:]]
    nums = [n for n in nums if n is not None]
    return max(nums) if nums else 0


# ---------------------------------------------------------------------------
# 后台任务（job）
# ---------------------------------------------------------------------------
JOBS = {}
JOBS_LOCK = threading.Lock()


def new_job(mode, total, novel_name=None):
    job = {
        "id": uuid.uuid4().hex[:12],
        "mode": mode,
        "status": "running",
        "step": "准备中",
        "message": "",
        "current": 0,
        "total": total,
        "novel_name": novel_name,
        "error": None,
        "result": None,
        "chars_done": 0,
        "chars_total": 0,
        "eta": 0,
        "cancel": False,
    }
    with JOBS_LOCK:
        JOBS[job["id"]] = job
    return job


def update_job(job, **kw):
    with JOBS_LOCK:
        job.update(kw)


# ---------------------------------------------------------------------------
# 并发控制 / 回收站 / 章节备份 / 文本切分
# ---------------------------------------------------------------------------
class BookBusyError(RuntimeError):
    """同书并发任务被拒：只报错，不改动书文件状态。"""


class JobCancelledError(RuntimeError):
    """任务被用户取消（用于分析任务等无书文件写入的场景）。"""


# 正在被任务占用的书名（并发保护 + 判定「生成中」是否为僵尸状态）
ACTIVE_BOOKS = set()
ACTIVE_BOOKS_LOCK = threading.Lock()


def acquire_book(name):
    with ACTIVE_BOOKS_LOCK:
        if name in ACTIVE_BOOKS:
            return False
        ACTIVE_BOOKS.add(name)
        return True


def release_book(name):
    with ACTIVE_BOOKS_LOCK:
        ACTIVE_BOOKS.discard(name)


def book_busy(name):
    with ACTIVE_BOOKS_LOCK:
        return name in ACTIVE_BOOKS


TRASH_DIR = NOVELS_DIR / "_trash"
CHAPTER_BACKUP_DIR = TRASH_DIR / "chapters"


def split_source_paragraphs(text):
    """把原作正文切成段落：优先按空行分段；空行分段只有 1 段时退化为按行分段
    （兼容网文单换行分段）。前后端使用同一规则。"""
    blank = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if len(blank) > 1:
        return blank
    return [p.strip() for p in re.split(r"\n+", text) if p.strip()]


def read_meta_only(path):
    """只读小说文件头部 front matter，避免整本解析（书架/档案复用等场景）。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            first = f.readline()
            if first.strip() != "---":
                return {}
            meta_lines = []
            for line in f:
                if line.strip() == "---":
                    break
                meta_lines.append(line)
        return json.loads("".join(meta_lines))
    except Exception:
        return {}


def find_existing_profile(title):
    """按书名查找已建书留存的分析档案（避免重复通读消耗额度）。"""
    if not title:
        return None
    title = title.strip()
    for p in NOVELS_DIR.glob("*.md"):
        try:
            meta = read_meta_only(p)
        except Exception:
            continue
        prof = meta.get("style_profile")
        if not prof:
            continue
        t = (meta.get("title") or p.stem).strip()
        if title in t or t in title:
            return prof
    return None


def _backup_chapter(novel_name, idx, chapter):
    """重写/删除章节前把旧版快照到 _trash/chapters/，返回快照文件名（失败返回 None）。"""
    try:
        CHAPTER_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = f"{sanitize_filename(novel_name)}_{idx}_{ts}_{uuid.uuid4().hex[:6]}.json"
        (CHAPTER_BACKUP_DIR / fname).write_text(json.dumps({
            "novel": novel_name,
            "index": idx,
            "title": chapter.get("title", ""),
            "content": chapter.get("content", ""),
            "ts": now_iso(),
        }, ensure_ascii=False), encoding="utf-8")
        return fname
    except Exception:
        return None


def load_chapter_backup(fname):
    """读取章节快照；防路径穿越。返回 dict 或 None。"""
    if not fname or Path(fname).name != fname:
        return None
    p = CHAPTER_BACKUP_DIR / fname
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


# ---------------------------------------------------------------------------
# 提示词与流程
# ---------------------------------------------------------------------------
def extract_initial_bible(meta):
    """从元数据（job_payload 或 style_profile）中提取/合成初始设定集。"""
    bible = {"setting": "", "characters": [], "conflict": "", "tone": ""}
    jp = meta.get("job_payload") or {}
    sp = meta.get("style_profile") or {}

    if jp.get("setting"):
        bible["setting"] = jp["setting"]
    elif meta.get("story_summary"):
        bible["setting"] = meta["story_summary"]

    chars = []
    if jp.get("characters"):
        raw_chars = jp["characters"]
        if isinstance(raw_chars, list):
            for c in raw_chars:
                if isinstance(c, dict):
                    chars.append(c)
                elif isinstance(c, str):
                    chars.append({"name": c, "role": "", "desc": "", "goal": ""})
        elif isinstance(raw_chars, str):
            for line in raw_chars.splitlines():
                line = line.strip().lstrip("-").strip()
                if line:
                    parts = line.split("：", 1)
                    if len(parts) == 2:
                        chars.append({"name": parts[0].strip(), "role": "", "desc": parts[1].strip(), "goal": ""})
                    else:
                        chars.append({"name": line, "role": "", "desc": "", "goal": ""})
    elif sp.get("人物表"):
        for c in sp["人物表"]:
            if isinstance(c, dict):
                chars.append({
                    "name": c.get("姓名") or c.get("name") or "",
                    "role": c.get("身份") or c.get("role") or "",
                    "desc": c.get("性格") or c.get("当前状态") or c.get("desc") or "",
                    "goal": c.get("关系") or c.get("goal") or ""
                })
    bible["characters"] = chars

    if jp.get("storyline"):
        bible["conflict"] = jp["storyline"]
    elif sp.get("续写要点"):
        bible["conflict"] = str(sp.get("续写要点"))

    if jp.get("style"):
        bible["tone"] = jp["style"]
    elif sp.get("文风"):
        bible["tone"] = str(sp.get("文风"))

    return bible


def build_original_setup(d):
    lines = []
    if d.get("title"):
        lines.append(f"书名：{d['title']}")
    if d.get("genre"):
        lines.append(f"题材：{d['genre']}")

    # 优先使用结构化设定档案 (bible)
    bible = d.get("bible")
    if bible and isinstance(bible, dict):
        if bible.get("setting"):
            lines.append(f"世界观与背景设定：\n{bible['setting']}")
        chars = bible.get("characters")
        if chars and isinstance(chars, list):
            char_lines = []
            for c in chars:
                if isinstance(c, dict):
                    name = c.get("name") or c.get("姓名") or ""
                    role = c.get("role") or c.get("身份") or ""
                    desc = c.get("desc") or c.get("性格") or ""
                    goal = c.get("goal") or c.get("动机") or ""
                    part = f"- {name}"
                    if role:
                        part += f"（{role}）"
                    if desc:
                        part += f"：{desc}"
                    if goal:
                        part += f"；核心目标：{goal}"
                    char_lines.append(part)
                elif isinstance(c, str) and c.strip():
                    char_lines.append(f"- {c.strip()}")
            if char_lines:
                lines.append("主要角色档案：\n" + "\n".join(char_lines))
        if bible.get("conflict"):
            lines.append(f"核心冲突与主线：{bible['conflict']}")
        if bible.get("tone"):
            lines.append(f"故事基调：{bible['tone']}")
    else:
        if d.get("setting"):
            lines.append(f"故事背景/核心设定：{d['setting']}")
        chars = d.get("characters")
        if chars:
            if isinstance(chars, str):
                chars = [c.strip() for c in chars.splitlines() if c.strip()]
            if chars:
                lines.append("主要角色：\n" + "\n".join(f"- {c}" for c in chars))
        if d.get("storyline"):
            lines.append(f"故事主线/目标：{d['storyline']}")

    if d.get("style"):
        lines.append(f"风格要求：{d['style']}")
    if d.get("perspective"):
        lines.append(f"叙事视角：{d['perspective']}")
    if d.get("extra"):
        lines.append(f"补充要求：{d['extra']}")
    return "\n".join(lines)


def build_continuation_setup(d):
    lines = []
    if d.get("source_title"):
        lines.append(f"原作书名：{d['source_title']}")
    if d.get("source_author"):
        lines.append(f"原作作者：{d['source_author']}")
    if d.get("source_intro"):
        lines.append(f"原作简介：{d['source_intro']}")
    if d.get("twist"):
        lines.append(f"同人改写设定：{d['twist']}")
    if d.get("extra"):
        lines.append(f"额外要求：{d['extra']}")

    # 结构化设定集 (Bible)
    bible = d.get("bible")
    if bible and isinstance(bible, dict):
        if bible.get("setting"):
            lines.append(f"世界观与背景设定：\n{bible['setting']}")
        chars = bible.get("characters")
        if chars and isinstance(chars, list):
            char_lines = []
            for c in chars:
                if isinstance(c, dict):
                    name = c.get("name") or c.get("姓名") or ""
                    role = c.get("role") or c.get("身份") or ""
                    desc = c.get("desc") or c.get("性格") or ""
                    goal = c.get("goal") or c.get("目标") or ""
                    part = f"- {name}"
                    if role:
                        part += f"（{role}）"
                    if desc:
                        part += f"：{desc}"
                    if goal:
                        part += f" [动机/目标: {goal}]"
                    char_lines.append(part)
            if char_lines:
                lines.append("核心角色档案：\n" + "\n".join(char_lines))
        if bible.get("conflict"):
            lines.append(f"核心矛盾与发展方向：{bible['conflict']}")
        if bible.get("tone"):
            lines.append(f"叙事基调：{bible['tone']}")
    return "\n".join(lines)


def context_from(chapters, budget=12000):
    parts = [f"【{c['title']}】\n{c['content']}" for c in chapters]
    joined = "\n\n".join(parts)
    if len(joined) <= budget:
        return joined
    return joined[-budget:]


ANALYZE_CHUNK_SIZE = 12000
ANALYZE_OVERLAP = 500
ANALYZE_CONCURRENCY = 4
ANALYZE_DIRECT_LIMIT = 30000  # 原文不超过此字符时单次分析，不切块

# 智能抽样策略（长文时启用）：精读开头+结尾，中间按比例抽样
SAMPLE_HEAD_RATIO = 0.15   # 开头精读比例
SAMPLE_TAIL_RATIO = 0.10   # 结尾精读比例
SAMPLE_MID_EVERY = 3       # 中间每 3 块取 1 块

CACHE_DIR = BASE_DIR / "analysis_cache"
CACHE_DIR.mkdir(exist_ok=True)


def analysis_cache_key(title, text):
    import hashlib
    return hashlib.sha1((title + "\x00" + text).encode("utf-8")).hexdigest()[:20]


def load_analysis_cache(key):
    p = CACHE_DIR / f"{key}.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def save_analysis_cache(key, profile):
    try:
        (CACHE_DIR / f"{key}.json").write_text(
            json.dumps(profile, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        pass


def analyze_style(data, on_progress=None, provider_id=None, cancel_check=None):
    """风格/全书分析：长文分块通读，短文单次分析；无原文则凭书名/简介推断。

    返回结构化创作档案 dict：
    文风、叙事视角、语言特色、人物表、当前剧情状态、伏笔与线索、
    章节命名规律（含原书标题样例）、续写要点。
    """
    text = (data.get("source_text") or "").strip()
    title = data.get("source_title") or "未知作品"
    author = data.get("source_author") or ""
    intro = data.get("source_intro") or ""

    if not text:
        if not intro and not title:
            raise RuntimeError("请提供原文，或至少提供书名和简介。")
        user = (
            f"书名：{title}\n作者：{author or '未知'}\n简介：{intro or '（无）'}\n\n"
            "根据以上信息推断这部小说的可能文风，以 JSON 输出，键为："
            "文风、叙事视角、语言特色、人物表、当前剧情状态、伏笔与线索、章节命名规律、续写要点。"
            "人物表为数组，每项含姓名/身份/性格/当前状态/关系；章节命名规律含风格描述与标题样例。"
            "这是推断结果，请注明不确定性。不要输出其他内容。"
        )
        sys = "你是一位精通文本风格分析的文学编辑。"
        content, _ = chat(
            [{"role": "system", "content": sys}, {"role": "user", "content": user}],
            max_tokens=2500,
            json_mode=True,
            provider_id=provider_id,
        )
        profile = extract_json(content)
        profile.setdefault("备注", "无原文，风格为推断结果，可能与原作有偏差。")
        return profile

    if len(text) > ANALYZE_DIRECT_LIMIT:
        return analyze_long_text(text, title, author, on_progress=on_progress,
                                 provider_id=provider_id, cancel_check=cancel_check)

    # 短文单次完整分析
    user = (
        f"这是小说《{title}》的原文（作者：{author or '未知'}）：\n\n{text}\n\n"
        "请深入分析这部小说，输出完整的创作档案，以 JSON 输出，键为："
        "文风、叙事视角、语言特色、人物表、当前剧情状态、伏笔与线索、章节命名规律、续写要点。"
        "人物表为数组，每项含姓名/身份/性格/当前状态/关系；"
        "章节命名规律为对象，含 风格描述 与 标题样例（列出原文真实章节标题，最多 10 个）；"
        "当前剧情状态要写清剧情进行到哪一步。不要输出其他内容。"
    )
    sys = "你是一位精通文本风格分析的文学编辑。"
    content, _ = chat(
        [{"role": "system", "content": sys}, {"role": "user", "content": user}],
        max_tokens=2500,
        json_mode=True,
        provider_id=provider_id,
    )
    return extract_json(content)


def _partial_summary(chunk, title, author, idx, total, provider_id=None):
    """单块原文的局部总结。"""
    user = (
        f"这是小说《{title}》原文的第 {idx}/{total} 部分（作者：{author or '未知'}）：\n\n{chunk}\n\n"
        "请对该部分做局部总结，以 JSON 输出，键为："
        "剧情推进（这段发生了什么、剧情进行到哪）、人物（出场人物及其状态变化）、"
        "文风特征（文笔、语言特点）、伏笔线索（埋下的伏笔）、章节标题（这段若含章节标题，列出原文标题，最多 5 个）。"
        "每个键的值用 1-3 句中文。不要输出其他内容。"
    )
    sys = "你是一位精通文本分析的小说编辑，正在逐部分通读一部小说，为后续续写做准备。"
    content, _ = chat(
        [{"role": "system", "content": sys}, {"role": "user", "content": user}],
        max_tokens=1200,
        json_mode=True,
        provider_id=provider_id,
    )
    return extract_json(content)


def _merge_profile(merged, title, author, provider_id=None):
    """把各部分的局部总结汇总成完整创作档案。"""
    user = (
        f"小说《{title}》（作者：{author or '未知'}）各部分通读总结如下：\n\n{merged}\n\n"
        "请汇总为一份完整的创作档案，以 JSON 输出，键为："
        "文风、叙事视角、语言特色、人物表（数组，每项含姓名/身份/性格/当前状态/关系）、"
        "当前剧情状态（剧情进行到哪一步、关键事件时间线）、伏笔与线索（数组）、"
        "章节命名规律（对象：风格描述 + 标题样例数组，总结原书章节标题的命名风格）、"
        "续写要点（数组，对续写的建议与约束）。不要输出其他内容。"
    )
    sys = "你是一位资深文学编辑，正在为续写一部小说准备完整的创作档案。"
    content, _ = chat(
        [{"role": "system", "content": sys}, {"role": "user", "content": user}],
        max_tokens=3000,
        json_mode=True,
        provider_id=provider_id,
    )
    return extract_json(content)


def select_sampled_chunks(n):
    """智能抽样：返回要精读的块下标列表。

    精读开头 SAMPLE_HEAD_RATIO、结尾 SAMPLE_TAIL_RATIO，中间每 SAMPLE_MID_EVERY 块取 1 块。
    块数 <= 4 时全读。
    """
    if n <= 4:
        return list(range(n))
    head_n = max(1, round(n * SAMPLE_HEAD_RATIO))
    tail_n = max(1, round(n * SAMPLE_TAIL_RATIO))
    mid = list(range(head_n, n - tail_n))
    sampled_mid = mid[::SAMPLE_MID_EVERY]
    sel = sorted(set(list(range(head_n)) + sampled_mid + list(range(n - tail_n, n))))
    return sel


def analyze_long_text(text, title, author="", on_progress=None, provider_id=None, cancel_check=None):
    """长文分块并发通读（智能抽样）-> 汇总创作档案。

    on_progress(done, total, chars_done, chars_total, eta_seconds)：
    done/total 为块进度；chars_* 为已读/总字符数；eta_seconds 为预计剩余秒数。
    cancel_check()：返回 True 时中止分析（抛 JobCancelledError）。
    """
    chunks = chunk_text(text, ANALYZE_CHUNK_SIZE, ANALYZE_OVERLAP)
    total_chars = len(text)
    if cancel_check and cancel_check():
        raise JobCancelledError()
    if len(chunks) == 1:
        # 单块直接做完整分析
        if on_progress:
            on_progress(1, 2, total_chars, total_chars, 0)
        user = (
            f"这是小说《{title}》的原文（作者：{author or '未知'}）：\n\n{chunks[0]}\n\n"
            "请深入分析这部小说，输出完整的创作档案，以 JSON 输出，键为："
            "文风、叙事视角、语言特色、人物表、当前剧情状态、伏笔与线索、章节命名规律、续写要点。"
            "人物表为数组，每项含姓名/身份/性格/当前状态/关系；"
            "章节命名规律为对象，含 风格描述 与 标题样例（列出原文真实章节标题，最多 10 个）。"
            "不要输出其他内容。"
        )
        sys = "你是一位精通文本风格分析的文学编辑。"
        content, _ = chat(
            [{"role": "system", "content": sys}, {"role": "user", "content": user}],
            max_tokens=2500,
            json_mode=True,
            provider_id=provider_id,
        )
        if on_progress:
            on_progress(2, 2, total_chars, total_chars, 0)
        return extract_json(content)

    from concurrent.futures import ThreadPoolExecutor, as_completed

    selected = select_sampled_chunks(len(chunks))
    sampled = len(selected) < len(chunks)
    partials = {}
    done_count = [0]
    t0 = time.time()
    chars_read = [0]

    def work(i, chunk):
        try:
            return i, _partial_summary(chunk, title, author, i + 1, len(chunks), provider_id=provider_id)
        except Exception as e:
            return i, {
                "剧情推进": f"（第 {i+1} 部分分析失败：{str(e)[:100]}）",
                "人物": "", "文风特征": "", "伏笔线索": "", "章节标题": [],
            }

    with ThreadPoolExecutor(max_workers=ANALYZE_CONCURRENCY) as ex:
        futures = {ex.submit(work, i, chunks[i]): i for i in selected}
        for fut in as_completed(futures):
            if cancel_check and cancel_check():
                ex.shutdown(wait=False, cancel_futures=True)
                raise JobCancelledError()
            i, summary = fut.result()
            partials[i] = summary
            done_count[0] += 1
            chars_read[0] += len(chunks[i])
            if on_progress:
                elapsed = time.time() - t0
                per_block = elapsed / done_count[0] if done_count[0] else 0
                eta = int(per_block * (len(selected) - done_count[0]))
                on_progress(done_count[0], len(selected), chars_read[0], total_chars, eta)

    # 把未抽样的中间块标为"跳过"，保持编号连续，便于汇总理解剧情全貌
    merged_parts = []
    for i in range(len(chunks)):
        if i in partials:
            merged_parts.append(f"【第 {i+1}/{len(chunks)} 部分】\n{json.dumps(partials[i], ensure_ascii=False, indent=1)}")
        else:
            merged_parts.append(f"【第 {i+1}/{len(chunks)} 部分】（中间抽样未精读，仅作占位）")
    merged = "\n\n".join(merged_parts)

    # 分层汇总：精读块数多时分两组，避免单次汇总输入过长导致模型返回 null/截断
    read_indices = sorted(partials.keys())
    if len(read_indices) > 8:
        mid = len(read_indices) // 2
        group_a = read_indices[:mid]
        group_b = read_indices[mid:]
        merged_a = "\n\n".join(
            f"【第 {i+1}/{len(chunks)} 部分】\n{json.dumps(partials[i], ensure_ascii=False, indent=1)}"
            for i in group_a
        )
        merged_b = "\n\n".join(
            f"【第 {i+1}/{len(chunks)} 部分】\n{json.dumps(partials[i], ensure_ascii=False, indent=1)}"
            for i in group_b
        )
        summary_a = _merge_half(merged_a, title, author, "前半部", provider_id=provider_id)
        if on_progress:
            on_progress(len(selected), len(selected), total_chars, total_chars, 0)
        summary_b = _merge_half(merged_b, title, author, "后半部", provider_id=provider_id)
        merged = f"【前半部通读总结】\n{summary_a}\n\n【后半部通读总结】\n{summary_b}"
    if on_progress:
        on_progress(len(selected), len(selected), total_chars, total_chars, 0)
    profile = _merge_profile(merged, title, author, provider_id=provider_id)
    if sampled:
        profile.setdefault("备注", "本次为抽样通读：精读开头与结尾、中间按比例抽样，未逐字通读全文。")
    return profile


def _merge_half(merged, title, author, which, provider_id=None):
    """把半部局部总结合并成一段结构化小结（纯文本，供最终汇总）。"""
    user = (
        f"小说《{title}》（作者：{author or '未知'}）{which}各部分通读总结如下：\n\n{merged}\n\n"
        f"请把{which}的剧情脉络、人物状态、伏笔与文风特点合并成一段紧凑的结构化小结（中文，600 字以内），"
        "以 JSON 输出：{\"剧情脉络\": \"...\", \"人物状态\": \"...\", \"伏笔线索\": \"...\", \"文风特点\": \"...\"}。不要输出其他内容。"
    )
    sys = "你是一位资深文学编辑，正在分阶段汇总一部小说的通读笔记。"
    content, _ = chat(
        [{"role": "system", "content": sys}, {"role": "user", "content": user}],
        max_tokens=1500,
        json_mode=True,
        provider_id=provider_id,
    )
    return json.dumps(extract_json(content), ensure_ascii=False, indent=1)


ORIGINAL_SYS = (
    "你是一位才华横溢的中文长篇小说作家。你根据用户给出的小说设定与章节大纲逐章创作正文。\n"
    "创作要求：\n"
    "1. 只输出本章正文，开头用「第X章」或「第X章 标题」作为标题行，不要输出大纲、说明或点评。\n"
    "2. 严格遵循大纲要点，情节推进自然，人物言行符合设定，注意与前面章节的连贯与伏笔呼应。\n"
    "3. 语言贴合用户要求的风格与视角，富有画面感与感染力。\n"
    "4. 控制篇幅接近用户要求的字数。"
)

CONTINUATION_SYS = (
    "你是一位续写高手，必须严格模仿给定小说的文风、人物口吻、叙事节奏与语言习惯进行续写。\n"
    "创作要求：\n"
    "1. 忠实于原作已确立的人物、设定与伏笔，不改变已有事实，与上文无缝衔接。\n"
    "2. 只输出续写正文，开头用「第X章」或「第X章 标题」作为标题行。\n"
    "3. 控制篇幅接近用户要求的字数。"
)

FANFIC_SYS = (
    "你是一位同人创作高手，在保留原作人物性格、文风质感与世界观的基础上，按用户给出的改写设定展开新剧情。\n"
    "创作要求：\n"
    "1. 保留原作风格与人物灵魂，但剧情按改写设定合理变化。\n"
    "2. 只输出正文，开头用「第X章」或「第X章 标题」作为标题行。\n"
    "3. 控制篇幅接近用户要求的字数。"
)


def run_original_job(job, data):
    title = data.get("title") or "未命名小说"
    n = int(data.get("chapters") or 10)
    per = int(data.get("per_chapter_words") or 1500)
    start = max(1, int(data.get("start_chapter") or 1))
    outline = data.get("outline") or ""
    provider_id = data.get("provider_id")

    novel_name = data.get("novel_name")
    if novel_name and (NOVELS_DIR / f"{novel_name}.md").exists():
        path = NOVELS_DIR / f"{novel_name}.md"
        meta, chapters, _ = parse_novel(path)
        if data.get("bible"):
            meta["bible"] = data.get("bible")
    else:
        path = unique_path(title)
        meta = {
            "title": title,
            "type": "original",
            "status": "generating",
            "created": now_iso(),
            "job_payload": data,
        }
        if data.get("bible"):
            meta["bible"] = data.get("bible")
        chapters = []

    outline_text = outline if isinstance(outline, str) else json.dumps(outline, ensure_ascii=False, indent=1)
    setup = build_original_setup(data)
    provider = get_provider(provider_id)
    meta["model_used"] = get_provider_meta(provider)
    meta["provider_id"] = provider.get("id")

    if not acquire_book(path.stem):
        raise BookBusyError(f"《{path.stem}》已有生成任务在进行中，请等待完成或取消后再试。")
    try:
        update_job(job, novel_name=path.stem, step="开始写作")
        for i in range(start, n + 1):
            if job.get("cancel"):
                _finalize_cancelled(job, path, meta, chapters)
                return
            update_job(job, step=f"正在写第 {i}/{n} 章", current=i)
            prev = context_from(chapters)

            def mk_msgs(sofar, i=i, prev=prev):
                msgs = [
                    {"role": "system", "content": ORIGINAL_SYS},
                    {"role": "user", "content": (
                        f"【小说设定】\n{setup}\n\n"
                        f"【章节大纲】\n{outline_text}\n\n"
                        f"【前情提要】\n{prev or '（这是第一章，无前文）'}\n\n"
                        f"现在创作第 {i} 章正文，约 {per} 字。"
                    )},
                ]
                if sofar:
                    msgs.append({"role": "assistant", "content": sofar})
                    msgs.append({"role": "user", "content": "继续写这一章，接着上面的内容往下写，不要重复。"})
                return msgs

            content = generate_text(mk_msgs, max_chars=int(per * 1.6), provider_id=provider_id)
            title_line, body = chapter_title_from(content, i)
            chapters.append({"title": title_line, "content": body})
            meta["status"] = "generating"
            write_novel(path, meta, chapters)

        meta["status"] = "done"
        meta["words"] = sum(len(re.sub(r"\s", "", c["content"])) for c in chapters)
        write_novel(path, meta, chapters)
        update_job(job, status="done", step="完成", message="生成完成", novel_name=path.stem)
    finally:
        release_book(path.stem)


def _finalize_cancelled(job, path, meta, chapters):
    """任务取消收尾：书标记为 cancelled（保留已生成章节），job 标记已取消。"""
    meta["status"] = "cancelled"
    meta["words"] = sum(len(re.sub(r"\s", "", c["content"])) for c in chapters)
    write_novel(path, meta, chapters)
    update_job(job, status="cancelled", step="已取消", message="任务已取消", novel_name=path.stem)


def run_continuation_job(job, data):
    mode = data.get("mode") or "continuation"
    source_text = data.get("source_text") or ""
    start_para = int(data.get("start_para") or 0)
    n = int(data.get("chapters") or 1)
    per = int(data.get("per_chapter_words") or 3000)
    source_title = data.get("source_title") or "未知原作"
    new_instruction = (data.get("new_instruction") or "").strip()
    provider_id = data.get("provider_id")

    # 截取到续写点（仅首轮使用）
    paras = split_source_paragraphs(source_text)
    if 0 < start_para <= len(paras):
        context_text = "\n\n".join(paras[:start_para])
    else:
        context_text = source_text
    CONTEXT_BUDGET = 16000
    if len(context_text) > CONTEXT_BUDGET:
        context_text = context_text[-CONTEXT_BUDGET:]

    novel_name = data.get("novel_name")
    if novel_name and (NOVELS_DIR / f"{novel_name}.md").exists():
        # ===== 追加续写：从现有文件恢复档案、指示与章节 =====
        path = NOVELS_DIR / f"{novel_name}.md"
        meta, chapters, _ = parse_novel(path)
        style_profile = meta.get("style_profile") or {}
        if not style_profile:
            # 原创生成的书首次续写：用已有章节自动建档案并缓存
            update_job(job, step="正在通读已有章节分析风格…")
            src = "\n\n".join(c["content"] for c in chapters)
            style_profile = analyze_style({"source_text": src, "source_title": meta.get("title", "")},
                                          provider_id=provider_id)
            meta["style_profile"] = style_profile
        if data.get("bible"):
            meta["bible"] = data.get("bible")
        elif "bible" not in data and meta.get("bible"):
            data["bible"] = meta["bible"]
        instructions = list(meta.get("instructions") or [])
        original_count = int(meta.get("original_count") or 0)
        start = max_chapter_number(chapters, original_count) + 1  # 接续最大编号
        # 兜底：若无编号（如原作无编号续写），退回按位置
        if start <= 1 and len(chapters) > original_count:
            start = len(chapters) - original_count + 1
    else:
        # ===== 首轮续写：创建新文件 =====
        if mode == "fanfic":
            out_title = data.get("title") or f"同人·{source_title}"
        else:
            out_title = data.get("title") or f"{source_title}·续写"
        path = unique_path(out_title)
        style_profile = data.get("style_profile")
        if not style_profile:
            update_job(job, step="正在通读全书分析风格…")
            style_profile = analyze_style(data, on_progress=None, provider_id=provider_id)
        instructions = []
        original_count = 0
        chapters = []
        # 原文作为「原作」章节进目录开头（# 转 ## 防误拆）
        if source_text.strip():
            orig_body = re.sub(r"^#\s+", "## ", source_text.strip(), flags=re.M)
            chapters.append({"title": "原作", "content": orig_body})
            original_count = 1
        initial_bible = data.get("bible") or extract_initial_bible({"style_profile": style_profile, "job_payload": data})
        if "bible" not in data:
            data["bible"] = initial_bible
        meta = {
            "title": out_title,
            "type": mode,
            "status": "generating",
            "created": now_iso(),
            "job_payload": data,
            "style_profile": style_profile,
            "bible": initial_bible,
            "source_title": source_title,
            "source_author": data.get("source_author", ""),
            "instructions": instructions,
            "original_count": original_count,
            "rounds": [],
            "story_summary": "",
            "summary_upto": 0,
        }
        start = 1

    if new_instruction:
        instructions.append(new_instruction)
        meta["instructions"] = instructions

    provider = get_provider(provider_id)
    meta["model_used"] = get_provider_meta(provider)
    meta["provider_id"] = provider.get("id")

    style_text = style_profile if isinstance(style_profile, str) else json.dumps(style_profile, ensure_ascii=False, indent=1)
    # 章节命名规律（仿原书）
    naming = ""
    if isinstance(style_profile, dict):
        nrule = style_profile.get("章节命名规律")
        if nrule:
            naming = json.dumps(nrule, ensure_ascii=False, indent=1)
    naming_hint = f"\n【章节命名规律（仿照原书风格命名本章标题，若无规律则用「第X章」）】\n{naming}" if naming else ""

    if mode == "fanfic":
        sys_prompt = FANFIC_SYS + f"\n\n【创作档案】\n{style_text}"
    else:
        sys_prompt = CONTINUATION_SYS + f"\n\n【创作档案】\n{style_text}"
    setup = build_continuation_setup(data)
    if setup:
        sys_prompt += f"\n\n【附加设定】\n{setup}"

    # 历史续写指示（最近 5 条）
    hist = "\n".join(f"{j+1}. {ins}" for j, ins in enumerate(instructions[-5:]))

    if not acquire_book(path.stem):
        raise BookBusyError(f"《{path.stem}》已有生成任务在进行中，请等待完成或取消后再试。")
    try:
        update_job(job, novel_name=path.stem, step="开始续写")
        round_start = start
        for i in range(start, start + n):
            if job.get("cancel"):
                _finalize_cancelled(job, path, meta, chapters)
                return
            update_job(job, step=f"正在续写第 {i} 章（本轮 {i - start + 1}/{n}）", current=i - start + 1)
            prev = context_from(chapters, budget=12000)

            def mk_msgs(sofar, i=i, prev=prev):
                msgs = [
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": (
                        (f"【原作截止位置之前的正文节选】\n{context_text or '（无原文）'}\n\n" if not chapters or (original_count and len(chapters) <= original_count) else "") +
                        f"【续写历史摘要】\n{meta.get('story_summary') or '（暂无）'}\n\n"
                        f"【前情提要】\n{prev or '（暂无）'}\n\n"
                        f"【历史续写指示】\n{hist or '（无）'}\n\n"
                        f"现在续写第 {i} 章，约 {per} 字。{naming_hint}"
                    )},
                ]
                if sofar:
                    msgs.append({"role": "assistant", "content": sofar})
                    msgs.append({"role": "user", "content": "继续写这一章，接着上面的内容往下写，不要重复。"})
                return msgs

            content = generate_text(mk_msgs, max_chars=int(per * 1.6), provider_id=provider_id)
            title_line, body = chapter_title_from(content, i)
            chapters.append({"title": title_line, "content": body})
            meta["status"] = "generating"
            write_novel(path, meta, chapters)

        meta["rounds"] = meta.get("rounds", []) + [{
            "start": round_start, "end": start + n - 1,
            "instruction": new_instruction,
            "ts": now_iso(),
        }]
        meta["words"] = sum(len(re.sub(r"\s", "", c["content"])) for c in chapters)

        # 滚动摘要：续写内容累计超阈值时增量压缩
        maybe_rollup_summary(meta, chapters, job, provider_id=provider_id)

        meta["status"] = "done"
        write_novel(path, meta, chapters)
        update_job(job, status="done", step="完成", message="生成完成", novel_name=path.stem)
    finally:
        release_book(path.stem)


ROLLUP_THRESHOLD = 30000  # 续写正文累计超过该字符数后启用滚动摘要


def maybe_rollup_summary(meta, chapters, job=None, provider_id=None):
    """续写内容过多时，对新增章节做增量摘要并存入 meta.story_summary。"""
    original_count = int(meta.get("original_count") or 0)
    continuation = chapters[original_count:]
    total = sum(len(re.sub(r"\s", "", c["content"])) for c in continuation)
    if total <= ROLLUP_THRESHOLD:
        return
    upto = int(meta.get("summary_upto") or 0)
    new_chapters = continuation[upto:]
    if not new_chapters:
        return
    if job:
        update_job(job, step="正在压缩前文…")
    old_summary = meta.get("story_summary") or ""
    new_text = "\n\n".join(f"【{c['title']}】\n{c['content']}" for c in new_chapters)
    if len(new_text) > 20000:
        new_text = new_text[-20000:]
    user = (
        f"这是小说续写内容的历史摘要：\n{old_summary or '（暂无）'}\n\n"
        f"新增的续写章节如下：\n{new_text}\n\n"
        "请输出更新后的续写内容摘要（中文，800 字以内）：当前剧情进行到哪、人物状态、"
        "已埋下的伏笔、最近发生的关键事件。只输出摘要正文，不要其他内容。"
    )
    try:
        content, _ = chat(
            [{"role": "system", "content": "你是一位小说剧情摘要专家，负责维护一部连载小说的最新剧情摘要。"},
             {"role": "user", "content": user}],
            max_tokens=1500,
            provider_id=provider_id,
        )
        meta["story_summary"] = content.strip()
        meta["summary_upto"] = upto + len(new_chapters)
    except Exception:
        pass  # 摘要失败不影响主流程


def run_analyze_job(job, data):
    try:
        text = (data.get("source_text") or "").strip()
        title = data.get("source_title") or ""
        provider_id = data.get("provider_id")
        cache_key = analysis_cache_key(title, text) if text else None

        # 命中缓存：直接返回，不花 token
        if cache_key:
            cached = load_analysis_cache(cache_key)
            if cached:
                update_job(job, status="done", step="分析完成（命中缓存）",
                           message="直接使用已缓存的分析结果",
                           result=cached, chars_done=0, chars_total=0, eta=0)
                return

        if job.get("cancel"):
            update_job(job, status="cancelled", step="已取消", message="任务已取消")
            return

        # 复用已建书留存的分析档案（同一本书只需分析一次）
        existing = find_existing_profile(title)
        if existing:
            update_job(job, status="done", step="已沿用本书档案",
                       message="已复用本书已保存的创作档案（未重新消耗额度）",
                       result=existing, chars_done=0, chars_total=0, eta=0)
            return

        def on_progress(done, total, chars_done=0, chars_total=0, eta=0):
            if job.get("cancel"):
                raise JobCancelledError()
            step = f"正在通读第 {done}/{total} 部分…" if total > 2 else "正在分析风格…"
            update_job(job, current=done, total=total, step=step,
                       chars_done=chars_done, chars_total=chars_total, eta=eta)

        profile = analyze_style(data, on_progress=on_progress, provider_id=provider_id,
                                cancel_check=lambda: bool(job.get("cancel")))
        if cache_key:
            save_analysis_cache(cache_key, profile)
        update_job(job, status="done", step="分析完成", message="全书通读完成",
                   result=profile, chars_done=0, chars_total=0, eta=0)
    except JobCancelledError:
        update_job(job, status="cancelled", step="已取消", message="任务已取消")
    except Exception as e:
        update_job(job, status="error", step="失败", message=str(e), error=str(e))


def run_rewrite_job(job, data):
    """重写章节 job：以该章前文为上下文重新生成一章，替换原位置。"""
    novel_name = data.get("novel_name")
    p = safe_novel_path(novel_name)
    if not p:
        raise RuntimeError("小说不存在")
    idx = int(data.get("chapter_index", -1))
    per = int(data.get("per_chapter_words") or 3000)
    provider_id = data.get("provider_id")

    meta, chapters, _ = parse_novel(p)
    original_count = int(meta.get("original_count") or 0)
    if idx < original_count:
        raise RuntimeError("原作章节不可重写")
    if idx >= len(chapters):
        raise RuntimeError("章节下标越界")

    num = chapter_number_from(chapters[idx]["title"]) or (idx - original_count + 1)
    prev = context_from(chapters[:idx], budget=16000)
    style_profile = meta.get("style_profile") or {}
    style_text = style_profile if isinstance(style_profile, str) else json.dumps(style_profile, ensure_ascii=False, indent=1)
    naming = ""
    if isinstance(style_profile, dict):
        nrule = style_profile.get("章节命名规律")
        if nrule:
            naming = json.dumps(nrule, ensure_ascii=False, indent=1)
    naming_hint = f"\n【章节命名规律（仿照原书风格命名本章标题，若无规律则用「第{num}章」）】\n{naming}" if naming else f"\n【标题】请用「第{num}章」或「第{num}章 标题」开头。"
    twist = data.get("twist") or ""
    extra = data.get("extra") or ""

    if meta.get("type") == "fanfic":
        sys_prompt = FANFIC_SYS + f"\n\n【创作档案】\n{style_text}"
    else:
        sys_prompt = CONTINUATION_SYS + f"\n\n【创作档案】\n{style_text}"
    if twist:
        sys_prompt += f"\n\n【同人改写设定】\n{twist}"
    if extra:
        sys_prompt += f"\n\n【额外要求】\n{extra}"

    def mk_msgs(sofar):
        msgs = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": (
                f"【本章之前的前情提要】\n{prev or '（暂无前文）'}\n\n"
                f"【续写历史摘要】\n{meta.get('story_summary') or '（暂无）'}\n\n"
                f"现在重写第 {num} 章，约 {per} 字。{naming_hint}"
            )},
        ]
        if sofar:
            msgs.append({"role": "assistant", "content": sofar})
            msgs.append({"role": "user", "content": "继续写这一章，接着上面的内容往下写，不要重复。"})
        return msgs

    if not acquire_book(p.stem):
        raise BookBusyError(f"《{p.stem}》已有生成任务在进行中，请等待完成或取消后再试。")
    try:
        # 重写前自动备份旧章节，可到「设置 -> 章节备份」恢复
        _backup_chapter(p.stem, idx, chapters[idx])

        update_job(job, novel_name=p.stem, step=f"正在重写第 {num} 章…", current=1)
        if job.get("cancel"):
            _finalize_cancelled(job, p, meta, chapters)
            return
        content = generate_text(mk_msgs, max_chars=int(per * 1.6), provider_id=provider_id)
        title_line, body = chapter_title_from(content, num)
        chapters[idx] = {"title": title_line, "content": body}
        meta["words"] = sum(len(re.sub(r"\s", "", c["content"])) for c in chapters)
        meta["story_summary"] = ""
        meta["summary_upto"] = 0
        meta["status"] = "done"
        meta.pop("error", None)
        write_novel(p, meta, chapters)
        update_job(job, status="done", step="重写完成", message=f"第 {num} 章已重写", novel_name=p.stem)
    finally:
        release_book(p.stem)


def run_job_safe(job, data):
    try:
        mode = data.get("mode")
        if mode == "original":
            run_original_job(job, data)
        elif mode == "analyze":
            run_analyze_job(job, data)
        elif mode == "rewrite":
            run_rewrite_job(job, data)
        else:
            run_continuation_job(job, data)
    except BookBusyError as e:
        # 同书并发被拒：只报错，不改动书文件状态
        update_job(job, status="error", step="失败", message=str(e), error=str(e))
    except Exception as e:
        try:
            if job.get("novel_name"):
                p = safe_novel_path(job["novel_name"])
                if p:
                    meta, chapters, _ = parse_novel(p)
                    meta["status"] = "error"
                    meta["error"] = str(e)
                    write_novel(p, meta, chapters)
        except Exception:
            pass
        update_job(job, status="error", step="失败", message=str(e), error=str(e))


# ---------------------------------------------------------------------------
# 路由
# ---------------------------------------------------------------------------
@app.get("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")


# ---------- 隐私密码 ----------
@app.get("/api/privacy")
def api_privacy_status():
    return jsonify({"enabled": privacy_enabled()})


@app.post("/api/privacy/set")
def api_privacy_set():
    """设置 / 更改隐私密码。已设置过时必须提供 old_password。"""
    data = request.get_json(force=True) or {}
    old = data.get("old_password") or ""
    new = (data.get("new_password") or "").strip()
    if len(new) < 4:
        return jsonify({"error": "新密码至少 4 位"}), 400
    cfg = load_config()
    rec = _privacy_record(cfg)
    if rec and not verify_password(old, rec):
        return jsonify({"error": "当前密码不正确"}), 403
    cfg["privacy"] = hash_password(new)
    save_config(cfg)
    with PRIVACY_LOCK:      # 改密码后所有旧令牌失效
        PRIVACY_TOKENS.clear()
    return jsonify({"ok": True})


@app.post("/api/privacy/unlock")
def api_privacy_unlock():
    data = request.get_json(force=True) or {}
    rec = _privacy_record()
    if not rec:
        return jsonify({"error": "尚未设置隐私密码，请先到「设置 → 隐私密码」中设置"}), 400
    if not verify_password(data.get("password") or "", rec):
        return jsonify({"error": "密码不正确"}), 403
    return jsonify({"ok": True, "token": issue_privacy_token()})


@app.post("/api/privacy/lock")
def api_privacy_lock():
    data = request.get_json(silent=True) or {}
    revoke_privacy_token(_request_token(data))
    return jsonify({"ok": True})


@app.get("/api/settings")
def api_get_settings():
    cfg = load_config()
    providers = [
        {**p, "api_key": mask_key(p.get("api_key", ""))}
        for p in (cfg.get("providers") or [])
    ]
    return jsonify({
        "providers": providers,
        "active_provider": cfg.get("active_provider", ""),
    })


@app.post("/api/settings")
def api_save_settings():
    data = request.get_json(force=True) or {}
    cfg = load_config()
    incoming = data.get("providers")
    if isinstance(incoming, list):
        # 保留未修改的 Key：前端回传的是掩码，需与已存配置比对
        existing = {p.get("id"): p for p in (cfg.get("providers") or [])}
        providers = []
        for p in incoming:
            pid = p.get("id")
            old = existing.get(pid, {})
            api_key = p.get("api_key", "")
            if not api_key or "*" in api_key:
                api_key = old.get("api_key", "")
            providers.append({
                "id": pid or uuid.uuid4().hex[:12],
                "name": p.get("name", "未命名"),
                "base_url": p.get("base_url", "").strip(),
                "api_key": api_key,
                "model": p.get("model", "").strip(),
                "temperature": float(p.get("temperature", 1.0)) if p.get("temperature") is not None else 1.0,
            })
        cfg["providers"] = providers
        if not cfg.get("active_provider") or cfg["active_provider"] not in [x["id"] for x in providers]:
            cfg["active_provider"] = providers[0]["id"] if providers else ""
    if data.get("active_provider"):
        cfg["active_provider"] = data["active_provider"]
    save_config(cfg)
    return jsonify({"ok": True})


@app.post("/api/test")
def api_test():
    data = request.get_json(force=True) or {}
    provider_id = data.get("provider_id")
    prov = data.get("provider")
    try:
        if isinstance(prov, dict):
            # 支持测试「尚未保存」的新增模型：以表单内容为准，缺 key 时回退已存配置
            base = get_provider(provider_id) or {}
            merged = {**base, **{k: v for k, v in prov.items() if v not in (None, "")}}
            content, _ = chat([{"role": "user", "content": "请只回复两个字：正常"}],
                              max_tokens=20, timeout=60, provider=merged)
        else:
            content, _ = chat([{"role": "user", "content": "请只回复两个字：正常"}],
                              max_tokens=20, timeout=60, provider_id=provider_id)
        return jsonify({"ok": True, "reply": content.strip()[:50]})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.get("/api/novels")
def api_list_novels():
    items = []
    for p in sorted(NOVELS_DIR.glob("*.md"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            meta, chapters, words = parse_novel(p)
        except Exception:
            continue
        if meta.get("private"):
            continue          # 隐私书籍不进普通书架
        name = p.stem
        status = meta.get("status", "done")
        items.append({
            "name": name,
            "title": meta.get("title", p.stem),
            "type": meta.get("type", "original"),
            "status": status,
            "stale": status == "generating" and not book_busy(name),
            "chapters": len(chapters),
            "words": meta.get("words", words),
            "updated": meta.get("updated", ""),
            "error": meta.get("error", ""),
            "source_title": meta.get("source_title", ""),
            "model_used": meta.get("model_used", ""),
        })
    return jsonify(items)


def _novel_item(p, meta, chapters, words):
    name = p.stem
    status = meta.get("status", "done")
    return {
        "name": name,
        "title": meta.get("title", p.stem),
        "type": meta.get("type", "original"),
        "status": status,
        "stale": status == "generating" and not book_busy(name),
        "chapters": len(chapters),
        "words": meta.get("words", words),
        "updated": meta.get("updated", ""),
        "error": meta.get("error", ""),
        "source_title": meta.get("source_title", ""),
        "model_used": meta.get("model_used", ""),
        "private": bool(meta.get("private")),
    }


@app.get("/api/novels/private")
def api_list_private_novels():
    """隐私书架列表：需有效解锁令牌（未设置密码时视为未设防）。"""
    if not can_access_private(_request_token()):
        return jsonify({"error": "隐私书架已锁定，请先输入隐私密码", "locked": True}), 403
    items = []
    for p in sorted(NOVELS_DIR.glob("*.md"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            meta, chapters, words = parse_novel(p)
        except Exception:
            continue
        if not meta.get("private"):
            continue
        items.append(_novel_item(p, meta, chapters, words))
    return jsonify(items)


@app.post("/api/novels/<name>/privacy")
def api_set_novel_privacy(name):
    """把书移入 / 移出隐私书架。"""
    data = request.get_json(force=True) or {}
    if not can_access_private(_request_token(data)):
        return jsonify({"error": "隐私书架已锁定，请先输入隐私密码", "locked": True}), 403
    p = safe_novel_path(name)
    if not p:
        return jsonify({"error": "小说不存在"}), 404
    want = bool(data.get("private"))
    if want and not privacy_enabled():
        return jsonify({"error": "请先在「设置 → 隐私密码」中设置密码"}), 400
    meta, chapters, _ = parse_novel(p)
    if want:
        meta["private"] = True
    else:
        meta.pop("private", None)
    write_novel(p, meta, chapters)
    return jsonify({"ok": True, "private": want, "title": meta.get("title", p.stem)})


@app.get("/api/novels/<name>")
def api_get_novel(name):
    token = _request_token()
    p = safe_novel_path(name)
    if not p:
        return jsonify({"error": "小说不存在"}), 404
    meta, chapters, words = parse_novel(p, repair=True)
    if _deny_private(meta, token):
        return jsonify({"error": "隐私书架已锁定，请先输入隐私密码", "locked": True}), 403
    # 若发生了标题修正，写回文件使其持久化
    raw_meta, raw_chapters, _ = parse_novel(p, repair=False)
    if [c["title"] for c in raw_chapters] != [c["title"] for c in chapters]:
        try:
            write_novel(p, meta, chapters)
        except Exception:
            pass
    # 轻量目录模式：仅返回元数据与章节标题/字数，不返回长文本正文
    if request.args.get("toc") or request.args.get("outline"):
        chapter_summaries = [
            {"title": c.get("title", ""), "words": len(re.sub(r"\s+", "", c.get("content", "")))}
            for c in chapters
        ]
        return jsonify({
            "name": p.stem, "meta": meta, "chapters": chapter_summaries, "words": words,
            "stale": meta.get("status") == "generating" and not book_busy(p.stem),
            "toc_only": True
        })
    return jsonify({
        "name": p.stem, "meta": meta, "chapters": chapters, "words": words,
        "stale": meta.get("status") == "generating" and not book_busy(p.stem),
    })


@app.get("/api/novels/<name>/chapters/<int:idx>")
@app.get("/api/novels/<name>/chapter/<int:idx>")
def api_get_chapter(name, idx):
    token = _request_token()
    p = safe_novel_path(name)
    if not p:
        return jsonify({"error": "小说不存在"}), 404
    meta, chapters, words = parse_novel(p, repair=False)
    if _deny_private(meta, token):
        return jsonify({"error": "隐私书架已锁定，请先输入隐私密码", "locked": True}), 403
    if idx < 0 or idx >= len(chapters):
        return jsonify({"error": "章节不存在"}), 404
    c = chapters[idx]
    c_words = len(re.sub(r"\s+", "", c.get("content", "")))
    return jsonify({
        "ok": True,
        "index": idx,
        "title": c.get("title", ""),
        "content": c.get("content", ""),
        "words": c_words
    })


@app.delete("/api/novels/<name>")
def api_delete_novel(name):
    token = _request_token()
    p = safe_novel_path(name)
    if not p:
        return jsonify({"error": "小说不存在"}), 404
    if _deny_private(read_meta_only(p), token):
        return jsonify({"error": "隐私书架已锁定，请先输入隐私密码", "locked": True}), 403
    # 不直接删除：移入回收站（_trash），可恢复
    try:
        TRASH_DIR.mkdir(parents=True, exist_ok=True)
        target = TRASH_DIR / p.name
        i = 2
        while target.exists():
            target = TRASH_DIR / f"{p.stem}({i}).md"
            i += 1
        p.rename(target)
        return jsonify({"ok": True, "trashed": target.name})
    except Exception as e:
        return jsonify({"error": "移入回收站失败：" + str(e)}), 500


@app.post("/api/novels/<name>/rename")
def api_rename_novel(name):
    token = _request_token()
    p = safe_novel_path(name)
    if not p:
        return jsonify({"error": "小说不存在"}), 404
    meta, chapters, words = parse_novel(p, repair=False)
    if _deny_private(meta, token):
        return jsonify({"error": "隐私书架已锁定，请先输入隐私密码", "locked": True}), 403
    if book_busy(p.stem):
        return jsonify({"error": "小说正在生成中，暂时无法更改标题"}), 409

    data = request.get_json(force=True) or {}
    new_title = (data.get("title") or "").strip()
    if not new_title:
        return jsonify({"error": "小说标题不能为空"}), 400

    new_stem = sanitize_filename(new_title)
    if not new_stem:
        return jsonify({"error": "小说标题不合法"}), 400

    # 同名无需重命名文件
    if new_stem == p.stem:
        meta["title"] = new_title
        write_novel(p, meta, chapters)
        return jsonify({"ok": True, "old_name": name, "new_name": p.stem, "title": new_title})

    target = NOVELS_DIR / f"{new_stem}.md"
    if target.exists():
        return jsonify({"error": f"已存在名为《{new_title}》的小说，请更换名称"}), 409

    meta["title"] = new_title
    write_novel(p, meta, chapters)
    p.rename(target)
    return jsonify({"ok": True, "old_name": name, "new_name": target.stem, "title": new_title})


@app.route("/api/novels/<name>/bible", methods=["GET", "POST"])
def api_novel_bible(name):
    token = _request_token()
    p = safe_novel_path(name)
    if not p:
        return jsonify({"error": "小说不存在"}), 404
    meta, chapters, words = parse_novel(p, repair=False)
    if _deny_private(meta, token):
        return jsonify({"error": "隐私书架已锁定，请先输入隐私密码", "locked": True}), 403

    if request.method == "GET":
        bible = meta.get("bible")
        if not bible:
            bible = extract_initial_bible(meta)
        return jsonify({"ok": True, "name": p.stem, "title": meta.get("title", p.stem), "bible": bible})

    data = request.get_json(force=True) or {}
    bible = data.get("bible") or {}
    meta["bible"] = bible
    if "job_payload" in meta and isinstance(meta["job_payload"], dict):
        meta["job_payload"]["bible"] = bible
    write_novel(p, meta, chapters)
    return jsonify({"ok": True, "bible": bible})


# ---------- 回收站（整本） ----------
@app.get("/api/trash")
def api_list_trash():
    token = _request_token()
    items = []
    for p in sorted(TRASH_DIR.glob("*.md"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            meta = read_meta_only(p)
        except Exception:
            meta = {}
        items.append({
            "file": p.name,
            "title": _mask_private_title(meta, meta.get("title", p.stem), token),
            "private": bool(meta.get("private")),
            "type": meta.get("type", "original"),
            "updated": meta.get("updated", ""),
        })
    return jsonify(items)


@app.post("/api/trash/<name>/restore")
def api_restore_trash(name):
    p = TRASH_DIR / f"{name}.md"
    if not p.exists():
        return jsonify({"error": "回收站中不存在该书"}), 404
    target = unique_path(p.stem)
    p.rename(target)
    return jsonify({"ok": True, "name": target.stem})


@app.delete("/api/trash/<name>")
def api_purge_trash(name):
    p = TRASH_DIR / f"{name}.md"
    if not p.exists():
        return jsonify({"error": "回收站中不存在该书"}), 404
    p.unlink()
    return jsonify({"ok": True})


# ---------- 章节备份（重写/删除前自动快照） ----------
@app.get("/api/trash/chapters")
def api_list_chapter_backups():
    token = _request_token()
    items = []
    if CHAPTER_BACKUP_DIR.exists():
        for p in sorted(CHAPTER_BACKUP_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
            snap = load_chapter_backup(p.name) or {}
            novel = snap.get("novel", "")
            novel_path = safe_novel_path(novel)
            novel_meta = read_meta_only(novel_path) if novel_path else {}
            items.append({
                "file": p.name,
                "novel": _mask_private_title(novel_meta, novel, token),
                "index": snap.get("index", 0),
                "title": snap.get("title", ""),
                "ts": snap.get("ts", ""),
            })
    return jsonify(items)


@app.post("/api/trash/chapters/<fname>/restore")
def api_restore_chapter_backup(fname):
    snap = load_chapter_backup(fname)
    if not snap:
        return jsonify({"error": "快照不存在或已损坏"}), 404
    p = safe_novel_path(snap.get("novel", ""))
    if not p:
        return jsonify({"error": "原书已不存在，无法恢复章节"}), 404
    meta, chapters, _ = parse_novel(p)
    if _deny_private(meta, _request_token(request.get_json(silent=True) or {})):
        return jsonify({"error": "隐私书架已锁定，请先输入隐私密码", "locked": True}), 403
    original_count = int(meta.get("original_count") or 0)
    idx = int(snap.get("index", 0))
    if idx < original_count:
        return jsonify({"error": "原作章节位置不可覆盖"}), 400
    idx = min(idx, len(chapters))
    new_ch = {"title": snap.get("title", ""), "content": snap.get("content", "")}
    if idx < len(chapters):
        chapters[idx] = new_ch
    else:
        chapters.insert(idx, new_ch)
    meta["words"] = sum(len(re.sub(r"\s", "", c["content"])) for c in chapters)
    meta["story_summary"] = ""
    meta["summary_upto"] = 0
    meta["status"] = "done"
    meta.pop("error", None)
    write_novel(p, meta, chapters)
    try:
        (CHAPTER_BACKUP_DIR / fname).unlink()
    except Exception:
        pass
    return jsonify({"ok": True, "title": new_ch["title"]})


@app.delete("/api/trash/chapters/<fname>")
def api_delete_chapter_backup(fname):
    p = CHAPTER_BACKUP_DIR / fname
    if not p.exists() or Path(fname).name != fname:
        return jsonify({"error": "快照不存在"}), 404
    p.unlink()
    return jsonify({"ok": True})


# ---------- 全书搜索 ----------
@app.get("/api/novels/<name>/search")
def api_search_novel(name):
    q = (request.args.get("q") or "").strip()
    if not q:
        return jsonify({"results": []})
    p = safe_novel_path(name)
    if not p:
        return jsonify({"error": "小说不存在"}), 404
    meta, chapters, _ = parse_novel(p)
    if _deny_private(meta, _request_token()):
        return jsonify({"error": "隐私书架已锁定，请先输入隐私密码", "locked": True}), 403
    results = []
    for i, c in enumerate(chapters):
        body = c.get("content", "")
        pos = body.find(q)
        if pos >= 0:
            start = max(0, pos - 60)
            snippet = ("…" if start > 0 else "") + body[start:pos + len(q) + 120] + ("…" if pos + len(q) + 120 < len(body) else "")
            results.append({"index": i, "title": c.get("title", ""), "snippet": snippet})
    return jsonify({"results": results[:100]})


# ---------- 分析缓存清理 ----------
@app.delete("/api/cache")
def api_clear_cache():
    n = 0
    for p in CACHE_DIR.glob("*.json"):
        try:
            p.unlink()
            n += 1
        except Exception:
            pass
    return jsonify({"ok": True, "removed": n})


@app.get("/api/cache/stats")
def api_cache_stats():
    n = len(list(CACHE_DIR.glob("*.json"))) if CACHE_DIR.exists() else 0
    return jsonify({"count": n})


@app.get("/api/novels/<name>/export")
def api_export_novel(name):
    """导出整本小说为 txt 或 md。fmt=txt|md"""
    p = safe_novel_path(name)
    if not p:
        return jsonify({"error": "小说不存在"}), 404
    fmt = request.args.get("fmt", "txt").lower()
    meta, chapters, _ = parse_novel(p)
    if _deny_private(meta, _request_token()):
        return jsonify({"error": "隐私书架已锁定，请先输入隐私密码", "locked": True}), 403
    title = meta.get("title", p.stem)

    if fmt == "md":
        parts = [f"# {title}", ""]
        for c in chapters:
            parts.append(f"## {c['title']}")
            parts.append("")
            parts.append(c["content"])
            parts.append("")
        content = "\n".join(parts)
        fname = f"{p.stem}.md"
        mime = "text/markdown; charset=utf-8"
    else:
        parts = [title, ""]
        for c in chapters:
            parts.append(c["title"])
            parts.append("")
            parts.append(c["content"])
            parts.append("")
        content = "\n".join(parts)
        fname = f"{p.stem}.txt"
        mime = "text/plain; charset=utf-8"

    from urllib.parse import quote
    resp = app.response_class(content, mimetype=mime)
    resp.headers["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote(fname)}"
    return resp


@app.post("/api/novels/<name>/chapters/delete")
def api_delete_chapter(name):
    """删除指定章节（0 基下标；原作章节不可删）。只删选中章，其余保留。"""
    p = safe_novel_path(name)
    if not p:
        return jsonify({"error": "小说不存在"}), 404
    data = request.get_json(force=True) or {}
    idx = int(data.get("index", -1))
    meta, chapters, _ = parse_novel(p)
    if _deny_private(meta, _request_token(data)):
        return jsonify({"error": "隐私书架已锁定，请先输入隐私密码", "locked": True}), 403
    original_count = int(meta.get("original_count") or 0)
    if idx < original_count:
        return jsonify({"error": "原作章节不可删除"}), 400
    if idx >= len(chapters):
        return jsonify({"error": "章节下标越界"}), 400
    # 先备份被删章节（可到「设置 -> 章节备份」恢复）
    _backup_chapter(p.stem, idx, chapters[idx])
    removed = chapters.pop(idx)
    meta["words"] = sum(len(re.sub(r"\s", "", c["content"])) for c in chapters)
    # 剧情变了，滚动摘要作废，下次续写时重建
    meta["story_summary"] = ""
    meta["summary_upto"] = 0
    meta["status"] = "done"
    meta.pop("error", None)
    write_novel(p, meta, chapters)
    return jsonify({"ok": True, "removed": removed["title"]})


@app.post("/api/novels/<name>/chapters/rewrite")
def api_rewrite_chapter(name):
    """重写指定章节（job 化）：删除该章，并以其前文为上下文重新生成一章替换。"""
    p = safe_novel_path(name)
    if not p:
        return jsonify({"error": "小说不存在"}), 404
    data = request.get_json(force=True) or {}
    idx = int(data.get("index", -1))
    meta, chapters, _ = parse_novel(p)
    if _deny_private(meta, _request_token(data)):
        return jsonify({"error": "隐私书架已锁定，请先输入隐私密码", "locked": True}), 403
    original_count = int(meta.get("original_count") or 0)
    if idx < original_count:
        return jsonify({"error": "原作章节不可重写"}), 400
    if idx >= len(chapters):
        return jsonify({"error": "章节下标越界"}), 400
    job = new_job("rewrite", 1)
    payload = {
        "mode": "rewrite",
        "novel_name": p.stem,
        "chapter_index": idx,
        "per_chapter_words": int(data.get("per_chapter_words") or 3000),
        "provider_id": data.get("provider_id"),
        "twist": data.get("twist", ""),
        "extra": data.get("extra", ""),
    }
    t = threading.Thread(target=run_job_safe, args=(job, payload), daemon=True)
    t.start()
    return jsonify({"job_id": job["id"]})


@app.post("/api/suggest-titles")
def api_suggest_titles():
    data = request.get_json(force=True) or {}
    setup = build_original_setup(data)
    provider_id = data.get("provider_id")
    genre = (data.get("genre") or "").strip()
    if not setup and not genre:
        return jsonify({"error": "请至少填写题材或部分设定"}), 400
    user = (
        f"题材：{genre or '网络小说'}\n"
        f"{setup}\n\n"
        "请根据以上信息，为这部小说拟定 6 个极具吸引力、符合网文命名潮流的书名。\n"
        "涵盖主流爆款命名逻辑（如主线悬念型、反差爽点型、精炼书卷型）。\n"
        "以 JSON 格式输出：{\"titles\": [\"书名1\", \"书名2\", \"书名3\", \"书名4\", \"书名5\", \"书名6\"]}\n"
        "不要输出任何其他说明文字。"
    )
    try:
        content, _ = chat(
            [{"role": "system", "content": "你是一位顶级畅销小说主编，精通网络小说爆款命名艺术。"},
             {"role": "user", "content": user}],
            max_tokens=600,
            json_mode=True,
            provider_id=provider_id,
        )
        res = extract_json(content)
        titles = res.get("titles", []) if isinstance(res, dict) else (res if isinstance(res, list) else [])
        return jsonify({"ok": True, "titles": titles[:6]})
    except Exception as e:
        return jsonify({"error": "AI 拟名失败：" + str(e)}), 500


@app.post("/api/generate-bible")
def api_generate_bible():
    data = request.get_json(force=True) or {}
    setup = build_original_setup(data)
    provider_id = data.get("provider_id")
    title = (data.get("title") or "").strip()
    genre = (data.get("genre") or "").strip()

    if not setup and not genre and not title:
        return jsonify({"error": "请至少填写题材或部分设定"}), 400

    user = (
        f"【已知信息】\n"
        f"书名：{title or '（待AI拟定）'}\n"
        f"题材：{genre or '网络小说'}\n"
        f"{setup}\n\n"
        "请为这部小说构建一套详尽、扎实且极具吸引力的【世界观与角色设定集（World & Character Bible）】。\n"
        "要求以 JSON 格式输出，结构严格如下：\n"
        "{\n"
        '  "suggested_title": "推荐书名（若用户已提供书名则沿用原书名，未提供则自拟一个爆款书名）",\n'
        '  "candidate_titles": ["备选书名1", "备选书名2", "备选书名3", "备选书名4"],\n'
        '  "setting": "世界观与背景设定（时代背景、地理势力格局、核心法则/力量体系，300-500字）",\n'
        '  "characters": [\n'
        '    {"name": "主角姓名", "role": "主角身份/定位", "desc": "外貌与核心性格特征", "goal": "核心动机与驱动目标"},\n'
        '    {"name": "重要配角姓名", "role": "配角身份/关系", "desc": "性格与特点", "goal": "动机与跟主角的关系"},\n'
        '    {"name": "主要对手或关键人物", "role": "反派/竞争者身份", "desc": "能力与性格", "goal": "阻碍主角的动机"}\n'
        "  ],\n"
        '  "conflict": "核心冲突与故事主线（主要的矛盾交锋、终极挑战或阶段目标）",\n'
        '  "tone": "叙事基调与风格特点"\n'
        "}\n"
        "不要输出任何其他解释文字。"
    )
    try:
        content, _ = chat(
            [{"role": "system", "content": "你是一位顶级网络小说策划主编与世界观架构师，擅长构筑逻辑严密、人物鲜活、看点十足的设定集。"},
             {"role": "user", "content": user}],
            max_tokens=3000,
            json_mode=True,
            provider_id=provider_id,
        )
        bible = extract_json(content)
        return jsonify({"ok": True, "bible": bible})
    except Exception as e:
        return jsonify({"error": "生成设定档案失败：" + str(e)}), 500


@app.post("/api/outline")
def api_outline():
    data = request.get_json(force=True) or {}
    setup = build_original_setup(data)
    n = int(data.get("chapters") or 10)
    provider_id = data.get("provider_id")
    if not setup:
        return jsonify({"error": "请至少填写一项设定内容"}), 400
    user = (
        f"{setup}\n\n"
        f"请为这部小说生成共 {n} 章的章节大纲。\n\n"
        "以 JSON 输出，格式：{\"logline\": \"一句话梗概\", \"chapters\": [{\"title\": \"第1章标题\", \"points\": \"本章要点\"}]}\n"
        "每章 points 写 2-4 句要点，包含情节推进、人物变化、冲突与伏笔。不要输出其他内容。"
    )
    try:
        content, _ = chat(
            [{"role": "system", "content": "你是一位资深小说编辑与大纲规划师。"},
             {"role": "user", "content": user}],
            max_tokens=4000,
            json_mode=True,
            provider_id=provider_id,
        )
        outline = extract_json(content)
        return jsonify({"outline": outline})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.post("/api/analyze-style")
def api_analyze_style():
    data = request.get_json(force=True) or {}
    try:
        profile = analyze_style(data, provider_id=data.get("provider_id"))
        return jsonify({"style_profile": profile})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.post("/api/analyze")
def api_analyze():
    """job 化全书通读分析：长文分块并发通读 -> 汇总创作档案。"""
    data = request.get_json(force=True) or {}
    text = (data.get("source_text") or "").strip()
    if not text and not data.get("source_intro") and not data.get("source_title"):
        return jsonify({"error": "请提供原文，或至少提供书名和简介。"}), 400
    job = new_job("analyze", 1)
    t = threading.Thread(target=run_job_safe, args=(job, {"mode": "analyze", **data}), daemon=True)
    t.start()
    return jsonify({"job_id": job["id"]})


@app.post("/api/generate")
def api_generate():
    data = request.get_json(force=True) or {}

    # 隐私书架：续写/断点续跑目标书为隐私书时必须已解锁
    _target = data.get("resume_novel") or data.get("novel_name")
    if _target:
        _tp = safe_novel_path(_target)
        if _tp and _deny_private(read_meta_only(_tp), _request_token(data)):
            return jsonify({"error": "隐私书架已锁定，请先输入隐私密码", "locked": True}), 403

    # 断点续跑：从已有小说的 meta.job_payload 恢复参数
    if data.get("resume_novel"):
        p = safe_novel_path(data["resume_novel"])
        if not p:
            return jsonify({"error": "小说不存在"}), 404
        meta, chapters, _ = parse_novel(p)
        saved = meta.get("job_payload") or {}
        data = {**saved, **{k: v for k, v in data.items() if k not in ("resume_novel",)}}
        data["novel_name"] = p.stem
        # 追加模式：从断点续写未完成的章节（继续上一轮指示）
        original_count = int(meta.get("original_count") or 0)
        if not data.get("start_chapter"):
            data["start_chapter"] = len(chapters) - original_count + 1
        # 恢复 instructions：把已有指示并回 new_instruction 空（沿用 meta 中的）
        data.pop("new_instruction", None)
        # 旧书兼容：payload 无 provider_id 时按书元数据所用模型兜底（仍以默认 provider 为准）
        if not data.get("provider_id"):
            data["provider_id"] = get_provider().get("id")

    mode = data.get("mode")
    if mode == "original":
        if not data.get("outline"):
            return jsonify({"error": "缺少大纲，请先生成大纲"}), 400
        n = int(data.get("chapters") or 10)
        job = new_job("original", n)
    elif mode in ("continuation", "fanfic"):
        n = int(data.get("chapters") or 1)
        job = new_job(mode, n)
    else:
        return jsonify({"error": "未知生成模式"}), 400

    t = threading.Thread(target=run_job_safe, args=(job, data), daemon=True)
    t.start()
    return jsonify({"job_id": job["id"]})


@app.get("/api/jobs/<job_id>")
def api_get_job(job_id):
    job = JOBS.get(job_id)
    if not job:
        return jsonify({"error": "任务不存在"}), 404
    return jsonify(job)


@app.post("/api/jobs/<job_id>/cancel")
def api_cancel_job(job_id):
    """请求取消任务：在章节边界生效，已写出的章节保留。"""
    job = JOBS.get(job_id)
    if not job:
        return jsonify({"error": "任务不存在"}), 404
    if job.get("status") not in ("running",):
        return jsonify({"error": "任务已结束，无法取消"}), 400
    update_job(job, cancel=True, message="取消请求已发送，将在当前章节完成后停止…")
    return jsonify({"ok": True})


def _lan_urls(port):
    """列出本机在局域网中的访问地址（用于手机浏览器）。"""
    urls = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))          # 不发包，仅用于取默认出口网卡地址
        urls.append(f"http://{s.getsockname()[0]}:{port}")
        s.close()
    except Exception:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            u = f"http://{info[4][0]}:{port}"
            if u not in urls:
                urls.append(u)
    except Exception:
        pass
    return urls


if __name__ == "__main__":
    host = (os.environ.get("NOVEL_HOST") or "127.0.0.1").strip()
    port = int(os.environ.get("NOVEL_PORT") or 8000)
    print(f"个人小说生成器已启动： http://127.0.0.1:{port}")
    if host not in ("127.0.0.1", "localhost"):
        print("局域网访问已开启，同一 Wi-Fi 下手机浏览器可打开：")
        for u in _lan_urls(port):
            print("  " + u)
        print("提示：局域网内的其他设备也能访问本工具（公开书架与生成接口），请只在可信网络下使用。")
    app.run(host=host, port=port, debug=False, threaded=True)
