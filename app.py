# -*- coding: utf-8 -*-
"""NovelStudio —— 本地 Flask 后端

功能：
- 原创生成：填写设定 -> 生成大纲 -> 逐章写作
- 续写/同人：分析原作文风 -> 模仿风格续写或改写
- 小说以 Markdown 文件存储于 novels/ 目录，头部为 JSON front matter

运行：python app.py  然后浏览器打开 http://127.0.0.1:8000
"""
import hashlib
import hmac
import html
import io
import json
import os
import re
import secrets
import socket
import sys
import threading
import time
import uuid
import zipfile
from datetime import datetime
from pathlib import Path
from contextlib import contextmanager

# 依赖引导：优先使用工作区 pylibs 目录中安装的依赖（pip --target 安装）
_LIBS = Path(__file__).resolve().parent / "pylibs"
if _LIBS.exists() and str(_LIBS) not in sys.path:
    sys.path.insert(0, str(_LIBS))

import requests
from flask import Flask, Response, jsonify, request, send_from_directory, stream_with_context

BASE_DIR = Path(__file__).resolve().parent
_data_dir_env = os.environ.get("NOVEL_DATA_DIR")
DATA_DIR = Path(_data_dir_env).resolve() if _data_dir_env else BASE_DIR
NOVELS_DIR = Path(os.environ.get("NOVEL_NOVELS_DIR", DATA_DIR / "novels")).resolve()
STATIC_DIR = BASE_DIR / "static"
CONFIG_FILE = Path(os.environ.get("NOVEL_CONFIG_FILE", DATA_DIR / "config.json")).resolve()
NOVELS_DIR.mkdir(parents=True, exist_ok=True)

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
    if not isinstance(data, dict):
        return {"providers": [dict(DEFAULT_PROVIDER)], "active_provider": "deepseek"}
    if "providers" in data and isinstance(data["providers"], list):
        return data
    legacy = {**DEFAULT_PROVIDER, **{k: v for k, v in data.items() if k in DEFAULT_PROVIDER}}
    res = dict(data)
    res["providers"] = [legacy]
    res.setdefault("active_provider", legacy["id"])
    return res


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
# 全站访问口令保护（Web Access Auth，用于 VPS / 局域网穿透防盗刷）
# ---------------------------------------------------------------------------
AUTH_TOKEN_TTL = 30 * 86400  # 30 天免密
AUTH_TOKENS = {}
AUTH_LOCK = threading.Lock()


def _auth_record(cfg=None):
    cfg = cfg if cfg is not None else load_config()
    rec = cfg.get("web_auth") or {}
    return rec if rec.get("hash") and rec.get("salt") else None


def auth_enabled():
    return _auth_record() is not None


def issue_auth_token():
    tok = secrets.token_urlsafe(32)
    now = time.time()
    with AUTH_LOCK:
        for k in [k for k, exp in AUTH_TOKENS.items() if exp < now]:
            AUTH_TOKENS.pop(k, None)
        AUTH_TOKENS[tok] = now + AUTH_TOKEN_TTL
    return tok


def auth_token_valid(token):
    if not token:
        return False
    with AUTH_LOCK:
        exp = AUTH_TOKENS.get(token)
        if not exp:
            return False
        if exp < time.time():
            AUTH_TOKENS.pop(token, None)
            return False
        return True


def revoke_auth_token(token):
    with AUTH_LOCK:
        AUTH_TOKENS.pop(token, None)


def get_request_auth_token():
    auth_hdr = request.headers.get("Authorization", "")
    if auth_hdr.startswith("Bearer "):
        return auth_hdr[7:].strip()
    tok = request.cookies.get("access_token") or request.headers.get("X-Access-Token") or request.args.get("access_token")
    return (tok or "").strip()


@app.before_request
def check_web_auth():
    if not auth_enabled():
        return None
    path = request.path
    # 静态资源、单页根路径、认证相关 API 始终允许访问
    if path.startswith("/static/") or path in ["/", "/api/auth/status", "/api/auth/login"]:
        return None
    token = get_request_auth_token()
    if not auth_token_valid(token):
        return jsonify({"ok": False, "error": "全站访问已锁定，请输入访问口令", "auth_required": True}), 401


# ---------------------------------------------------------------------------
# 大模型调用（OpenAI 兼容，多 provider）
# ---------------------------------------------------------------------------
def chat(messages, max_tokens=2000, temperature=None, json_mode=False, timeout=300, provider_id=None, provider=None, stream=False, on_chunk=None):
    """调用 chat/completions，返回 (content, finish_reason)。失败自动重试 3 次。

    provider_id：指定使用哪个大模型配置（缺省用默认 provider）。
    provider：直接传入 provider 配置 dict（用于测试尚未保存的新增模型）。
    stream：是否启用流式传输。
    on_chunk：流式 chunk 回调 (接收文本片段)。
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
        "stream": bool(stream and on_chunk),
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    headers = {"Authorization": f"Bearer {provider['api_key']}", "Content-Type": "application/json"}
    last_err = None
    for attempt in range(3):
        try:
            if stream and on_chunk:
                r = requests.post(url, json=payload, headers=headers, timeout=timeout, stream=True)
                if r.status_code == 200:
                    chunks = []
                    finish_reason = None
                    for line in r.iter_lines():
                        if not line:
                            continue
                        decoded = line.decode("utf-8", errors="replace").strip()
                        if decoded.startswith("data: "):
                            data_str = decoded[6:].strip()
                            if data_str == "[DONE]":
                                break
                            try:
                                chunk = json.loads(data_str)
                                choices = chunk.get("choices") or []
                                if choices:
                                    c0 = choices[0]
                                    delta = c0.get("delta") or {}
                                    txt = delta.get("content") or ""
                                    if txt:
                                        chunks.append(txt)
                                        try:
                                            on_chunk(txt)
                                        except Exception:
                                            pass
                                    if c0.get("finish_reason"):
                                        finish_reason = c0.get("finish_reason")
                            except Exception:
                                pass
                    return "".join(chunks), finish_reason or "stop"
                last_err = f"HTTP {r.status_code}: {r.text[:300]}"
            else:
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


def generate_text(messages_fn, max_chars, max_tokens_per_call=8000, temperature=None, provider_id=None, on_chunk=None):
    """循环调用模型直到章节写完（finish_reason 非 length）或达到字数上限。

    messages_fn(sofar) -> messages：sofar 为本章已生成内容，用于上下文续写。
    """
    sofar = ""
    while True:
        msgs = messages_fn(sofar)
        content, reason = chat(msgs, max_tokens=max_tokens_per_call, temperature=temperature, provider_id=provider_id, stream=bool(on_chunk), on_chunk=on_chunk)
        sofar += content
        if reason != "length" or len(sofar) >= max_chars:
            break
    return sofar


def extract_json(text):
    """从模型输出中提取 JSON 对象或数组（容忍 ```json 围栏、中文全角标点、不完整截断与多余文字）。

    接受对象（dict）或数组（list）；`null`/标量视为无效；遇到截断时尽全力自动闭合修复或正则抢救。
    """
    if not text or not str(text).strip():
        raise RuntimeError("模型返回内容为空，未生成有效内容。")
    text = str(text).strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    # 1. 直接尝试标准解析
    try:
        obj = json.loads(text)
        if isinstance(obj, (dict, list)):
            return obj
    except Exception:
        pass

    # 2. 匹配最外层完整的大括号或中括号
    first_brace = text.find("{")
    first_bracket = text.find("[")
    m = None
    if first_brace != -1 and (first_bracket == -1 or first_brace < first_bracket):
        m = re.search(r"\{.*\}", text, re.S)
    elif first_bracket != -1:
        m = re.search(r"\[.*\]", text, re.S)

    if m:
        try:
            obj = json.loads(m.group(0))
            if isinstance(obj, (dict, list)):
                return obj
        except Exception:
            pass

    # 3. 常见中文全角标点与多余尾随逗号清洗
    cleaned = text
    # 替换中文弯引号
    cleaned = cleaned.replace("“", "\"").replace("”", "\"").replace("‘", "\"").replace("’", "\"")
    # 替换中文冒号为英文冒号（作为键值分隔符时）
    cleaned = re.sub(r"\"\s*：\s*", "\": ", cleaned)
    # 替换中文逗号
    cleaned = re.sub(r"\"\s*，\s*", "\", ", cleaned)
    cleaned = re.sub(r"([0-9]|true|false|null|\]|\})\s*，\s*", r"\1, ", cleaned)
    # 替换中文全角括号
    cleaned = cleaned.replace("｛", "{").replace("｝", "}").replace("［", "[").replace("］", "]")
    # 去除数组/对象尾随多余逗号
    cleaned = re.sub(r",\s*([\}\]])", r"\1", cleaned)

    first_brace = cleaned.find("{")
    first_bracket = cleaned.find("[")
    m = None
    if first_brace != -1 and (first_bracket == -1 or first_brace < first_bracket):
        m = re.search(r"\{.*\}", cleaned, re.S)
    elif first_bracket != -1:
        m = re.search(r"\[.*\]", cleaned, re.S)

    if m:
        try:
            obj = json.loads(m.group(0))
            if isinstance(obj, (dict, list)):
                return obj
        except Exception:
            pass

    # 4. 截断闭合修复（当输出触及 max_tokens 未闭合字符串或括号时）
    first_brace = cleaned.find("{")
    first_bracket = cleaned.find("[")
    start_pos = -1
    if first_brace != -1 and (first_bracket == -1 or first_brace < first_bracket):
        start_pos = first_brace
    elif first_bracket != -1:
        start_pos = first_bracket

    if start_pos != -1:
        s = cleaned[start_pos:]
        # 去除末尾不完整的 key、冒号或逗号
        s = re.sub(r"[,:\s]+$", "", s)

        # 补全未闭合的双引号
        quotes = len(re.findall(r"(?<!\\)\"", s))
        if quotes % 2 != 0:
            s += "\""

        # 利用栈统计并闭合未匹配的括号
        stack = []
        in_str = False
        escape = False
        for c in s:
            if escape:
                escape = False
                continue
            if c == "\\":
                escape = True
                continue
            if c == "\"":
                in_str = not in_str
                continue
            if not in_str:
                if c in "{[":
                    stack.append(c)
                elif c == "}":
                    if stack and stack[-1] == "{":
                        stack.pop()
                elif c == "]":
                    if stack and stack[-1] == "[":
                        stack.pop()

        while stack:
            top = stack.pop()
            if top == "{":
                s += "}"
            elif top == "[":
                s += "]"

        try:
            obj = json.loads(s)
            if isinstance(obj, (dict, list)):
                return obj
        except Exception:
            pass

    # 5. 正则保底抢救（提取所有完整的 "key": "value" 或 "key": [...] 字段）
    salvaged = {}
    pattern = r"\"([^\"]+)\"\s*[:：]\s*(?:\"([^\"]*)\"|\[(.*?)\]|(\{.*?\})|(\d+(?:\.\d+)?)|(true|false|null))"
    for match in re.finditer(pattern, cleaned, re.S):
        k = match.group(1).strip()
        if not k:
            continue
        if match.group(2) is not None:
            salvaged[k] = match.group(2)
        elif match.group(3) is not None:
            try:
                salvaged[k] = json.loads("[" + match.group(3) + "]")
            except Exception:
                salvaged[k] = [x.strip().strip("\"") for x in match.group(3).split(",") if x.strip()]
        elif match.group(4) is not None:
            try:
                salvaged[k] = json.loads(match.group(4))
            except Exception:
                salvaged[k] = {}
        elif match.group(5) is not None:
            salvaged[k] = float(match.group(5)) if "." in match.group(5) else int(match.group(5))
        elif match.group(6) is not None:
            val = match.group(6)
            salvaged[k] = True if val == "true" else (False if val == "false" else None)

    if salvaged and isinstance(salvaged, dict) and len(salvaged) > 0:
        return salvaged

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


def escape_content_line(line):
    """转义正文行开头的 Markdown 标题定界符，防止误识别为章节/分卷结构。"""
    end = ""
    if line.endswith("\r\n"):
        end = "\r\n"
        content_part = line[:-2]
    elif line.endswith("\n") or line.endswith("\r"):
        end = line[-1]
        content_part = line[:-1]
    else:
        content_part = line

    m = re.match(r"^(\s*)(\\*)(#.*)$", content_part)
    if m:
        indent, slashes, rest = m.groups()
        return f"{indent}\\{slashes}{rest}{end}"
    return line


def unescape_content_line(line):
    """还原正文行首被转义的 Markdown 标题定界符。"""
    end = ""
    if line.endswith("\r\n"):
        end = "\r\n"
        content_part = line[:-2]
    elif line.endswith("\n") or line.endswith("\r"):
        end = line[-1]
        content_part = line[:-1]
    else:
        content_part = line

    m = re.match(r"^(\s*)\\(\\*)(#.*)$", content_part)
    if m:
        indent, slashes, rest = m.groups()
        return f"{indent}{slashes}{rest}{end}"
    return line


def parse_novel(path, repair=True):
    """解析 novels/*.md -> (meta, chapters, words)

    repair=True 时自动修正「标题被误当正文」的存量章节；返回的 chapters
    已修正，调用方可写回文件。支持分卷 (## 卷：...) 解析。
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
    cur_volume = ""

    def flush():
        nonlocal cur_title, cur_volume
        if cur_title is not None:
            unescaped_content = "".join(unescape_content_line(l) for l in cur_lines).strip()
            chapters.append({
                "title": cur_title,
                "content": unescaped_content,
                "volume": cur_volume or "正文"
            })
        cur_title = None
        cur_lines.clear()

    for line in body.splitlines(keepends=True):
        stripped = line.strip()
        if stripped.startswith("## 卷：") or stripped.startswith("## 卷名：") or stripped.startswith("## Volume:"):
            flush()
            if stripped.startswith("## 卷："):
                cur_volume = stripped[len("## 卷："):].strip()
            elif stripped.startswith("## 卷名："):
                cur_volume = stripped[len("## 卷名："):].strip()
            else:
                cur_volume = stripped[len("## Volume:"):].strip()
        elif line.startswith("# "):
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
    """原子写入小说 Markdown 文件，正文行首敏感结构符自动转义。"""
    meta = dict(meta)
    meta["updated"] = now_iso()
    parts = ["---", json.dumps(meta, ensure_ascii=False), "---", ""]
    last_volume = None
    for c in chapters:
        vol = (c.get("volume") or "").strip()
        if vol and vol != "正文" and vol != last_volume:
            parts.append(f"## 卷：{vol}")
            parts.append("")
            last_volume = vol
        elif not vol and last_volume is not None:
            last_volume = None
        parts.append(f"# {c['title']}")
        parts.append("")
        escaped_lines = [escape_content_line(l) for l in c["content"].splitlines(keepends=True)]
        parts.append("".join(escaped_lines))
        parts.append("")

    # 原子写入：同目录下写入临时文件再用 os.replace 替换，避免并发中断造成文件损坏
    dir_name = path.parent
    tmp_p = dir_name / f".tmp_{path.stem}_{os.getpid()}_{time.time_ns()}.tmp"
    try:
        tmp_p.write_text("\n".join(parts), encoding="utf-8")
        os.replace(str(tmp_p), str(path))
    except Exception:
        try:
            if tmp_p.exists():
                tmp_p.unlink()
        except Exception:
            pass
        raise


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
        "streaming_text": "",
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
ACTIVE_BOOKS = {}  # name -> holder (True or job_id)
ACTIVE_BOOKS_LOCK = threading.Lock()


def acquire_book(name, holder=True):
    with ACTIVE_BOOKS_LOCK:
        if name in ACTIVE_BOOKS:
            if holder is not True and ACTIVE_BOOKS.get(name) == holder:
                return True
            return False
        ACTIVE_BOOKS[name] = holder
        return True


def release_book(name):
    with ACTIVE_BOOKS_LOCK:
        ACTIVE_BOOKS.pop(name, None)


def book_busy(name):
    with ACTIVE_BOOKS_LOCK:
        return name in ACTIVE_BOOKS


# 按小说名划分的读-备-写互斥锁（使用 RLock 防重入）
_NOVEL_IO_LOCKS = {}
_NOVEL_IO_LOCKS_LOCK = threading.Lock()


@contextmanager
def lock_novel(name_or_stem: str):
    """按小说文件名获取临界区重入互斥锁（RLock），确保‘读取旧内容 -> 备份快照 -> 写入新内容’成为原子操作。"""
    stem = sanitize_filename(name_or_stem) if name_or_stem else "default"
    with _NOVEL_IO_LOCKS_LOCK:
        lock = _NOVEL_IO_LOCKS.setdefault(stem, threading.RLock())
    with lock:
        yield


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

CACHE_DIR = Path(os.environ.get("NOVEL_CACHE_DIR", DATA_DIR / "analysis_cache")).resolve()
CACHE_DIR.mkdir(parents=True, exist_ok=True)


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
            max_tokens=4500,
            json_mode=True,
            provider_id=provider_id,
        )
        profile = extract_json(content)
        if not isinstance(profile, dict):
            profile = {"人物表": profile}
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
        max_tokens=4500,
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
        max_tokens=2500,
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
        max_tokens=5000,
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
    if not isinstance(profile, dict):
        profile = {"总结": profile}
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


DEFAULT_PROMPT_TEMPLATES = {
    "default": {
        "id": "default",
        "name": "标准网文风",
        "desc": "文笔流畅通俗，叙事节奏明晰，适度环境渲染与人物对白。",
        "instruction": "语言自然流畅，节奏分明，富有画面感与感染力。"
    },
    "zhihu": {
        "id": "zhihu",
        "name": "知乎爽文风",
        "desc": "强第一人称/贴身视角，高压开局，反转密集，情绪拉扯与痛快打脸。",
        "instruction": "文风采用知乎热榜第一人称/贴身视角爽文风格。开局迅速切入核心冲突或不公待遇，节奏极快，心理反差剧烈，短句居多，每千字必有剧情反转或伏笔揭示，情绪张力饱满。"
    },
    "qidian": {
        "id": "qidian",
        "name": "起点硬核升级流",
        "desc": "世界法则严密，设定扎实，文风沉稳老辣，升级与谋略并重。",
        "instruction": "文风沉稳老辣，细节扎实严谨。力量体系、地缘势力与功法设定逻辑自洽，战斗描写具有极强动作感与策略博弈，拒绝无脑弱智反派，侧重主角心性成长与长线经营。"
    },
    "jjwx": {
        "id": "jjwx",
        "name": "晋江唯美治愈流",
        "desc": "细腻心理刻画，眼神与微表情交锋，情感拉扯拉满，语言优美含蓄。",
        "instruction": "文风唯美细腻，擅长捕捉微表情与眼神暗流。情感拉扯深刻，注重角色间独特的张力与宿命感，描写富有诗意与余韵，注重心理变化与生活细节。"
    },
    "fanqie": {
        "id": "fanqie",
        "name": "番茄快节奏脑洞",
        "desc": "黄金三章快节奏，三段一钩子，打脸解压，直切主题爽点连贯。",
        "instruction": "节奏极其轻快，开门见山，毫不拖泥带水。语言生动接地气，冲突与金手指爽点紧凑连贯，段落简练，悬念密集，让读者欲罢不能。"
    },
    "traditional": {
        "id": "traditional",
        "name": "传统文学质感",
        "desc": "现实主义群像刻画，文字凝练厚重，时代风貌与人生命运交织。",
        "instruction": "语言凝练厚重，富有现实主义文学质感。人物群像立体，避免网文套路化脸谱，重在社会风貌与人性复杂度的真实呈现。"
    }
}


def get_prompt_templates():
    cfg = load_config()
    custom = cfg.get("prompt_templates") or {}
    merged = {k: dict(v) for k, v in DEFAULT_PROMPT_TEMPLATES.items()}
    for k, v in custom.items():
        if isinstance(v, dict):
            if k in merged:
                merged[k].update(v)
            else:
                merged[k] = v
    active = cfg.get("active_prompt_template", "default")
    return merged, active


def build_style_instruction(template_id=None):
    templates, active = get_prompt_templates()
    tid = template_id or active
    tmpl = templates.get(tid)
    if tmpl and tmpl.get("instruction"):
        return f"\n\n【特定文风与写作规范】\n{tmpl['instruction']}"
    return ""


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

    if not acquire_book(path.stem, holder=job["id"]):
        raise BookBusyError(f"《{path.stem}》已有生成任务在进行中，请等待完成或取消后再试。")
    try:
        update_job(job, novel_name=path.stem, step="开始写作")
        for i in range(start, n + 1):
            if job.get("cancel"):
                _finalize_cancelled(job, path, meta, chapters)
                return
            update_job(job, step=f"正在写第 {i}/{n} 章", current=i, streaming_text="")
            prev = context_from(chapters)

            def on_chunk(token):
                if job.get("cancel"):
                    raise JobCancelledError()
                with JOBS_LOCK:
                    job["streaming_text"] = (job.get("streaming_text") or "") + token

            def mk_msgs(sofar, i=i, prev=prev):
                msgs = [
                    {"role": "system", "content": ORIGINAL_SYS + build_style_instruction(data.get("style_template") or data.get("prompt_template"))},
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

            content = generate_text(mk_msgs, max_chars=int(per * 1.6), provider_id=provider_id, on_chunk=on_chunk)
            title_line, body = chapter_title_from(content, i)
            with lock_novel(path.stem):
                chapters.append({"title": title_line, "content": body})
                meta["status"] = "generating"
                write_novel(path, meta, chapters)

        with lock_novel(path.stem):
            meta["status"] = "done"
            meta["words"] = sum(len(re.sub(r"\s", "", c["content"])) for c in chapters)
            write_novel(path, meta, chapters)
        update_job(job, status="done", step="完成", message="生成完成", novel_name=path.stem)
    finally:
        release_book(path.stem)


def _finalize_cancelled(job, path, meta, chapters):
    """任务取消收尾：书标记为 cancelled（保留已生成章节），job 标记已取消。"""
    with lock_novel(path.stem):
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
            src = "\n\n".join(c.get("content", "") for c in chapters)
            try:
                style_profile = analyze_style({"source_text": src, "source_title": meta.get("title", "")},
                                              provider_id=provider_id)
            except Exception as e:
                bible = meta.get("bible") or (meta.get("job_payload") and meta["job_payload"].get("bible")) or {}
                style_profile = {
                    "文风": bible.get("tone") or (meta.get("job_payload") and meta["job_payload"].get("style")) or "延续前文文风",
                    "叙事视角": (meta.get("job_payload") and meta["job_payload"].get("perspective")) or "第三人称",
                    "人物表": bible.get("characters") or [],
                    "当前剧情状态": f"前 {len(chapters)} 章已完成",
                    "备注": "自动继承自原创设定与已有章节",
                }
            meta["style_profile"] = style_profile
            with lock_novel(path.stem):
                write_novel(path, meta, chapters)
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

    if not acquire_book(path.stem, holder=job["id"]):
        raise BookBusyError(f"《{path.stem}》已有生成任务在进行中，请等待完成或取消后再试。")
    try:
        update_job(job, novel_name=path.stem, step="开始续写")
        round_start = start
        for i in range(start, start + n):
            if job.get("cancel"):
                _finalize_cancelled(job, path, meta, chapters)
                return
            update_job(job, step=f"正在续写第 {i} 章（本轮 {i - start + 1}/{n}）", current=i - start + 1, streaming_text="")
            prev = context_from(chapters, budget=12000)

            def on_chunk(token):
                if job.get("cancel"):
                    raise JobCancelledError()
                with JOBS_LOCK:
                    job["streaming_text"] = (job.get("streaming_text") or "") + token

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

            content = generate_text(mk_msgs, max_chars=int(per * 1.6), provider_id=provider_id, on_chunk=on_chunk)
            title_line, body = chapter_title_from(content, i)
            with lock_novel(path.stem):
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

        with lock_novel(path.stem):
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

    if not acquire_book(p.stem, holder=job["id"]):
        raise BookBusyError(f"《{p.stem}》已有生成任务在进行中，请等待完成或取消后再试。")
    try:
        # 重写前自动备份旧章节，可到「设置 -> 章节备份」恢复
        _backup_chapter(p.stem, idx, chapters[idx])

        update_job(job, novel_name=p.stem, step=f"正在重写第 {num} 章…", current=1, streaming_text="")
        if job.get("cancel"):
            _finalize_cancelled(job, p, meta, chapters)
            return

        def on_chunk(token):
            if job.get("cancel"):
                raise JobCancelledError()
            with JOBS_LOCK:
                job["streaming_text"] = (job.get("streaming_text") or "") + token

        content = generate_text(mk_msgs, max_chars=int(per * 1.6), provider_id=provider_id, on_chunk=on_chunk)
        title_line, body = chapter_title_from(content, num)
        with lock_novel(p.stem):
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


def run_job_safe(job, data, target_book=None):
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
                    with lock_novel(p.stem):
                        meta, chapters, _ = parse_novel(p)
                        meta["status"] = "error"
                        meta["error"] = str(e)
                        write_novel(p, meta, chapters)
        except Exception:
            pass
        update_job(job, status="error", step="失败", message=str(e), error=str(e))
    finally:
        if target_book:
            release_book(target_book)


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


# ---------- 全站访问门禁 ----------
@app.get("/api/auth/status")
def api_auth_status():
    enabled = auth_enabled()
    token = get_request_auth_token()
    authorized = (not enabled) or auth_token_valid(token)
    return jsonify({"enabled": enabled, "authorized": authorized})


@app.post("/api/auth/login")
def api_auth_login():
    if not auth_enabled():
        return jsonify({"ok": True, "token": "", "message": "未启用全站口令"})
    data = request.get_json(force=True) or {}
    password = (data.get("password") or "").strip()
    rec = _auth_record()
    if not verify_password(password, rec):
        return jsonify({"ok": False, "error": "访问口令错误"}), 403
    tok = issue_auth_token()
    resp = jsonify({"ok": True, "token": tok})
    resp.set_cookie("access_token", tok, max_age=int(AUTH_TOKEN_TTL), httponly=False, samesite="Lax")
    return resp


@app.post("/api/auth/set-password")
def api_auth_set_password():
    data = request.get_json(force=True) or {}
    new_pw = (data.get("new_password") or "").strip()
    old_pw = (data.get("old_password") or "").strip()
    cfg = load_config()
    rec = _auth_record(cfg)
    if rec:
        if not verify_password(old_pw, rec):
            return jsonify({"ok": False, "error": "原访问口令不正确"}), 403
    if not new_pw:
        # 清除口令（关闭全站访问门禁）
        cfg.pop("web_auth", None)
        save_config(cfg)
        with AUTH_LOCK:
            AUTH_TOKENS.clear()
        return jsonify({"ok": True, "enabled": False, "message": "全站访问口令已关闭"})
    if len(new_pw) < 4:
        return jsonify({"ok": False, "error": "口令长度至少 4 位"}), 400
    cfg["web_auth"] = hash_password(new_pw)
    save_config(cfg)
    with AUTH_LOCK:
        AUTH_TOKENS.clear()
    tok = issue_auth_token()
    resp = jsonify({"ok": True, "enabled": True, "token": tok, "message": "全站访问口令设置成功"})
    resp.set_cookie("access_token", tok, max_age=int(AUTH_TOKEN_TTL), httponly=False, samesite="Lax")
    return resp


@app.post("/api/auth/logout")
def api_auth_logout():
    tok = get_request_auth_token()
    if tok:
        revoke_auth_token(tok)
    resp = jsonify({"ok": True})
    resp.delete_cookie("access_token")
    return resp


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
    with lock_novel(p.stem):
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
    # 轻量目录模式：仅返回元数据与章节标题/字数，不返回长文本正文
    if request.args.get("toc") or request.args.get("outline"):
        chapter_summaries = [
            {
                "title": c.get("title", ""),
                "words": len(re.sub(r"\s+", "", c.get("content", ""))),
                "volume": c.get("volume", "正文")
            }
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


@app.post("/api/novels/<name>/chapters/<int:idx>")
@app.post("/api/novels/<name>/chapter/<int:idx>")
def api_edit_chapter(name, idx):
    """就地编辑章节正文与标题，并在保存前自动生成快照备份。"""
    token = _request_token()
    p = safe_novel_path(name)
    if not p:
        return jsonify({"error": "小说不存在"}), 404

    with lock_novel(p.stem):
        meta, chapters, words = parse_novel(p, repair=False)
        if _deny_private(meta, token):
            return jsonify({"error": "隐私书架已锁定，请先输入隐私密码", "locked": True}), 403
        if idx < 0 or idx >= len(chapters):
            return jsonify({"error": "章节不存在"}), 404
        if book_busy(p.stem):
            return jsonify({"error": "小说正在生成中，暂时无法编辑章节"}), 409

        data = request.get_json(force=True) or {}
        new_title = data.get("title")
        new_content = data.get("content")
        if new_content is None:
            return jsonify({"error": "章节正文内容不能为空"}), 400

        old_ch = chapters[idx]
        # 编辑前自动备份旧版本快照（可在「设置 -> 章节备份」恢复）
        _backup_chapter(p.stem, idx, old_ch)

        if new_title is not None and str(new_title).strip():
            chapters[idx]["title"] = str(new_title).strip()
        chapters[idx]["content"] = str(new_content)

        c_words = len(re.sub(r"\s+", "", chapters[idx]["content"]))
        meta["words"] = sum(len(re.sub(r"\s+", "", c.get("content", ""))) for c in chapters)
        write_novel(p, meta, chapters)
        return jsonify({
            "ok": True,
            "index": idx,
            "title": chapters[idx]["title"],
            "content": chapters[idx]["content"],
            "words": c_words,
            "total_words": meta["words"]
        })


@app.delete("/api/novels/<name>")
def api_delete_novel(name):
    token = _request_token()
    p = safe_novel_path(name)
    if not p:
        return jsonify({"error": "小说不存在"}), 404
    if _deny_private(read_meta_only(p), token):
        return jsonify({"error": "隐私书架已锁定，请先输入隐私密码", "locked": True}), 403
    if book_busy(p.stem):
        return jsonify({"error": "小说正在生成中，暂时无法删除小说"}), 409
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

    with lock_novel(p.stem):
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
    with lock_novel(p.stem):
        meta["bible"] = bible
        if "job_payload" in meta and isinstance(meta["job_payload"], dict):
            meta["job_payload"]["bible"] = bible
        write_novel(p, meta, chapters)
    return jsonify({"ok": True, "bible": bible})

@app.post("/api/novels/<name>/preferences")
def api_set_novel_preferences(name):
    token = _request_token()
    p = safe_novel_path(name)
    if not p:
        return jsonify({"error": "小说不存在"}), 404
    meta, chapters, words = parse_novel(p, repair=False)
    if _deny_private(meta, token):
        return jsonify({"error": "未解锁隐私小说", "locked": True}), 403

    data = request.get_json(force=True) or {}
    with lock_novel(p.stem):
        for k in ["preferred_style", "preferred_style_template", "preferred_model", "preferred_perspective", "preferred_words"]:
            if k in data:
                meta[k] = data[k]
        write_novel(p, meta, chapters)
    return jsonify({"ok": True, "meta": meta})


@app.post("/api/novels/<name>/reorder-chapters")
def api_reorder_chapters(name):
    token = _request_token()
    p = safe_novel_path(name)
    if not p:
        return jsonify({"error": "小说不存在"}), 404

    with lock_novel(p.stem):
        meta, chapters, words = parse_novel(p, repair=False)
        if _deny_private(meta, token):
            return jsonify({"error": "未解锁隐私小说", "locked": True}), 403
        if book_busy(p.stem):
            return jsonify({"error": "小说正在生成中，暂时无法调整章节"}), 409

        data = request.get_json(force=True) or {}
        order = data.get("order")
        if not isinstance(order, list):
            return jsonify({"error": "参数 order 必须为列表"}), 400

        if all(isinstance(x, int) for x in order):
            if set(order) != set(range(len(chapters))):
                return jsonify({"error": "章节索引不完整或越界"}), 400
            chapters = [chapters[i] for i in order]
        elif all(isinstance(x, dict) for x in order):
            reordered = []
            for item in order:
                idx = item.get("index")
                if idx is None or not isinstance(idx, int) or idx < 0 or idx >= len(chapters):
                    return jsonify({"error": f"章节索引无效: {idx}"}), 400
                ch = dict(chapters[idx])
                if "volume" in item and item["volume"] is not None:
                    ch["volume"] = str(item["volume"]).strip() or "正文"
                if "title" in item and item["title"]:
                    ch["title"] = str(item["title"]).strip()
                reordered.append(ch)
            chapters = reordered
        else:
            return jsonify({"error": "order 格式不支持"}), 400

        write_novel(p, meta, chapters)
        return jsonify({"ok": True, "count": len(chapters), "chapters": [{"title": c["title"], "volume": c.get("volume", "正文")} for c in chapters]})


@app.get("/api/novels/<name>/chapters/<int:idx>/history")
def api_chapter_history(name, idx):
    token = _request_token()
    p = safe_novel_path(name)
    if not p:
        return jsonify({"error": "小说不存在"}), 404
    meta, chapters, words = parse_novel(p, repair=False)
    if _deny_private(meta, token):
        return jsonify({"error": "未解锁隐私小说", "locked": True}), 403
    if idx < 0 or idx >= len(chapters):
        return jsonify({"error": "章节不存在"}), 404

    prefix = f"{sanitize_filename(name)}_{idx}_"
    snapshots = []
    if CHAPTER_BACKUP_DIR.exists():
        for f in CHAPTER_BACKUP_DIR.glob(f"{prefix}*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                content = data.get("content", "")
                snapshots.append({
                    "id": f.name,
                    "title": data.get("title", ""),
                    "ts": data.get("ts", ""),
                    "words": len(re.sub(r"\s+", "", content)),
                    "preview": content[:120] + ("..." if len(content) > 120 else ""),
                    "content": content
                })
            except Exception:
                continue
    snapshots.sort(key=lambda s: s["ts"], reverse=True)
    return jsonify({
        "ok": True,
        "index": idx,
        "current_title": chapters[idx].get("title", ""),
        "current_words": len(re.sub(r"\s+", "", chapters[idx].get("content", ""))),
        "snapshots": snapshots
    })


@app.post("/api/novels/<name>/chapters/<int:idx>/restore-snapshot")
def api_restore_chapter_snapshot(name, idx):
    token = _request_token()
    p = safe_novel_path(name)
    if not p:
        return jsonify({"error": "小说不存在"}), 404

    with lock_novel(p.stem):
        meta, chapters, words = parse_novel(p, repair=False)
        if _deny_private(meta, token):
            return jsonify({"error": "未解锁隐私小说", "locked": True}), 403
        if idx < 0 or idx >= len(chapters):
            return jsonify({"error": "章节不存在"}), 404
        if book_busy(p.stem):
            return jsonify({"error": "小说正在生成中，暂时无法恢复快照"}), 409

        data = request.get_json(force=True) or {}
        snapshot_id = data.get("snapshot_id")
        if not snapshot_id:
            return jsonify({"error": "缺少 snapshot_id 参数"}), 400

        target_file = CHAPTER_BACKUP_DIR / sanitize_filename(snapshot_id)
        if not target_file.exists():
            return jsonify({"error": "快照不存在"}), 404

        try:
            snap_data = json.loads(target_file.read_text(encoding="utf-8"))
        except Exception as e:
            return jsonify({"error": f"读取快照失败: {e}"}), 500

        _backup_chapter(p.stem, idx, chapters[idx])
        if snap_data.get("title"):
            chapters[idx]["title"] = snap_data["title"]
        chapters[idx]["content"] = snap_data.get("content", "")
        meta["words"] = sum(len(re.sub(r"\s+", "", c.get("content", ""))) for c in chapters)
        write_novel(p, meta, chapters)

        return jsonify({
            "ok": True,
            "index": idx,
            "title": chapters[idx]["title"],
            "content": chapters[idx]["content"],
            "words": len(re.sub(r"\s+", "", chapters[idx]["content"]))
        })


@app.post("/api/novels/import-txt")
def api_import_txt():
    token = _request_token()
    raw_text = ""
    title = ""
    genre = "都市言情"

    if "file" in request.files:
        f = request.files["file"]
        title = Path(f.filename).stem
        raw_text = f.read().decode("utf-8", errors="replace")
    else:
        data = request.get_json(silent=True) or {}
        raw_text = data.get("text", "")
        title = data.get("title", "")
        genre = data.get("genre", "都市言情")

    if request.form:
        if request.form.get("title"):
            title = request.form.get("title")
        if request.form.get("genre"):
            genre = request.form.get("genre")

    title = sanitize_filename(title.strip() or "未命名导入作品")
    if not raw_text.strip():
        return jsonify({"error": "导入内容不能为空"}), 400

    candidate_title = title
    counter = 1
    while (NOVELS_DIR / f"{candidate_title}.md").exists():
        candidate_title = f"{title}_{counter}"
        counter += 1
    title = candidate_title

    pattern = re.compile(
        r'(?:^|\r?\n)[ \t]*(第[0-9零一二三四五六七八九十百千万]+[章节回集卷篇节][^\r\n]*|Chapter\s+[0-9]+[^\r\n]*|[【\[（(]第[0-9零一二三四五六七八九十百千万]+[章节回集卷][】\]）)][^\r\n]*|引子[^\r\n]*|序章[^\r\n]*|尾声[^\r\n]*|番外[^\r\n]*)',
        re.IGNORECASE
    )

    matches = list(pattern.finditer(raw_text))
    chapters = []
    if matches:
        first_start = matches[0].start()
        preamble = raw_text[:first_start].strip()
        if preamble:
            chapters.append({
                "title": "序章",
                "content": preamble,
                "volume": "正文"
            })
        for i, match in enumerate(matches):
            ch_title = match.group(1).strip()
            start_pos = match.end()
            end_pos = matches[i + 1].start() if i + 1 < len(matches) else len(raw_text)
            ch_content = raw_text[start_pos:end_pos].strip()
            chapters.append({
                "title": ch_title,
                "content": ch_content,
                "volume": "正文"
            })
    else:
        paragraphs = raw_text.splitlines()
        chunks = []
        cur_chunk = []
        cur_len = 0
        for p_line in paragraphs:
            cur_chunk.append(p_line)
            cur_len += len(p_line)
            if cur_len >= 3000:
                chunks.append("\n".join(cur_chunk).strip())
                cur_chunk = []
                cur_len = 0
        if cur_chunk:
            chunks.append("\n".join(cur_chunk).strip())
        if not chunks:
            chunks = [raw_text.strip()]
        for i, ch_text in enumerate(chunks):
            chapters.append({
                "title": f"第{i+1}章",
                "content": ch_text,
                "volume": "正文"
            })

    total_words = sum(len(re.sub(r"\s+", "", c["content"])) for c in chapters)
    meta = {
        "title": title,
        "type": "imported",
        "genre": genre,
        "status": "completed",
        "created": now_iso(),
        "updated": now_iso(),
        "chapters": len(chapters),
        "words": total_words
    }
    p = NOVELS_DIR / f"{title}.md"
    write_novel(p, meta, chapters)

    bible_path = NOVELS_DIR / f"{title}.bible.json"
    bible_data = {
        "setting": f"根据导入作品《{title}》自适应提取世界观设定。",
        "characters": [],
        "conflict": "",
        "tone": "自然流畅"
    }
    try:
        bible_path.write_text(json.dumps(bible_data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass

    return jsonify({
        "ok": True,
        "name": title,
        "title": title,
        "chapters_count": len(chapters),
        "total_words": total_words,
        "sample_chapters": [c["title"] for c in chapters[:5]]
    })


@app.post("/api/novels/<name>/search-replace")
def api_search_replace(name):
    token = _request_token()
    p = safe_novel_path(name)
    if not p:
        return jsonify({"error": "小说不存在"}), 404

    with lock_novel(p.stem):
        meta, chapters, words = parse_novel(p, repair=False)
        if _deny_private(meta, token):
            return jsonify({"error": "未解锁隐私小说", "locked": True}), 403
        if book_busy(p.stem):
            return jsonify({"error": "小说正在生成中，暂时无法进行全书替换"}), 409

        data = request.get_json(force=True) or {}
        find_text = str(data.get("find", "")).strip()
        replace_text = str(data.get("replace", ""))
        case_sensitive = bool(data.get("case_sensitive", False))
        use_regex = bool(data.get("regex", False))
        preview_only = bool(data.get("preview_only", True))

        if not find_text:
            return jsonify({"error": "查找内容不能为空"}), 400

        try:
            flags = 0 if case_sensitive else re.IGNORECASE
            pattern = re.compile(find_text if use_regex else re.escape(find_text), flags)
        except Exception as e:
            return jsonify({"error": f"正则表达式错误: {e}"}), 400

        results = []
        total_matches = 0
        modified_chapters = 0

        for idx, ch in enumerate(chapters):
            content = ch.get("content", "")
            matches = list(pattern.finditer(content))
            if matches:
                total_matches += len(matches)
                modified_chapters += 1
                snippets = []
                for m in matches[:4]:
                    s = max(0, m.start() - 25)
                    e = min(len(content), m.end() + 25)
                    snippets.append(content[s:e].replace("\n", " "))
                results.append({
                    "chapter_index": idx,
                    "chapter_title": ch.get("title", f"第{idx+1}章"),
                    "volume": ch.get("volume", "正文"),
                    "matches_count": len(matches),
                    "snippets": snippets
                })
                if not preview_only:
                    _backup_chapter(p.stem, idx, ch)
                    ch["content"] = pattern.sub(replace_text, content)

        if not preview_only and modified_chapters > 0:
            meta["words"] = sum(len(re.sub(r"\s+", "", c.get("content", ""))) for c in chapters)
            write_novel(p, meta, chapters)

        return jsonify({
            "ok": True,
            "preview_only": preview_only,
            "find": find_text,
            "replace": replace_text,
            "total_matches": total_matches,
            "modified_chapters": modified_chapters,
            "results": results
        })


@app.get("/api/settings/prompts")
def api_get_prompt_settings():
    templates, active = get_prompt_templates()
    return jsonify({
        "ok": True,
        "active": active,
        "templates": templates
    })


@app.post("/api/settings/prompts")
def api_save_prompt_settings():
    data = request.get_json(force=True)
    if not isinstance(data, dict):
        return jsonify({"error": "请求体格式错误，必须为 JSON 对象"}), 400
    cfg = load_config()
    if "active" in data and str(data["active"]).strip():
        cfg["active_prompt_template"] = str(data["active"]).strip()
    if "custom_template" in data and isinstance(data["custom_template"], dict):
        cfg.setdefault("prompt_templates", {})
        ct = data["custom_template"]
        tid = ct.get("id", "custom")
        cfg["prompt_templates"][tid] = ct
    save_config(cfg)
    templates, active = get_prompt_templates()
    return jsonify({
        "ok": True,
        "active": active,
        "templates": templates
    })



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
    data = request.get_json(silent=True) or {}
    if _deny_private(read_meta_only(p), _request_token(data)):
        return jsonify({"error": "隐私书架已锁定，请先输入隐私密码", "locked": True}), 403
    target = unique_path(p.stem)
    p.rename(target)
    return jsonify({"ok": True, "name": target.stem})


@app.delete("/api/trash/<name>")
def api_purge_trash(name):
    p = TRASH_DIR / f"{name}.md"
    if not p.exists():
        return jsonify({"error": "回收站中不存在该书"}), 404
    if _deny_private(read_meta_only(p), _request_token()):
        return jsonify({"error": "隐私书架已锁定，请先输入隐私密码", "locked": True}), 403
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

    with lock_novel(p.stem):
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
    snap = load_chapter_backup(fname) or {}
    novel_name = snap.get("novel", "")
    if novel_name:
        novel_p = safe_novel_path(novel_name)
        if novel_p and _deny_private(read_meta_only(novel_p), _request_token()):
            return jsonify({"error": "隐私书架已锁定，请先输入隐私密码", "locked": True}), 403
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


def generate_epub(title, author, intro, chapters, meta=None) -> bytes:
    """纯标准库生成符合 EPUB 2/3 标准规范的电子书，适配 Apple Books、微信读书、Kindle 等。"""
    meta = meta or {}
    book_id = str(uuid.uuid4())
    mod_time = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    title_esc = html.escape(title or "未命名小说")
    author_esc = html.escape(author or "AI 创作")
    intro_esc = html.escape(intro or "")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        # 1. mimetype (必须是首个文件且无压缩存储)
        z.writestr("mimetype", b"application/epub+zip", compress_type=zipfile.ZIP_STORED)

        # 2. META-INF/container.xml
        container_xml = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>"""
        z.writestr("META-INF/container.xml", container_xml, compress_type=zipfile.ZIP_DEFLATED)

        # 3. OEBPS/style.css
        css = """@charset "utf-8";
body {
  margin: 5% 8%;
  font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
  line-height: 1.85;
  color: #2c3e50;
  text-align: justify;
}
h1, h2, h3 {
  font-weight: 600;
  color: #1a202c;
  text-align: center;
  margin-top: 1.5em;
  margin-bottom: 0.8em;
}
p {
  text-indent: 2em;
  margin: 0.5em 0;
  line-height: 1.85;
}
.cover-wrap {
  text-align: center;
  padding: 16% 5%;
}
.cover-title {
  font-size: 2.2em;
  font-weight: bold;
  color: #111;
  margin-bottom: 0.4em;
}
.cover-author {
  font-size: 1.1em;
  color: #666;
  margin-top: 1em;
}
.cover-meta {
  font-size: 0.9em;
  color: #888;
  margin-top: 1.8em;
}
.cover-intro {
  margin: 2.2em auto 0 auto;
  font-size: 0.95em;
  color: #555;
  text-align: left;
  max-width: 80%;
  border-left: 3px solid #cbd5e1;
  padding-left: 1em;
}
"""
        z.writestr("OEBPS/style.css", css, compress_type=zipfile.ZIP_DEFLATED)

        manifest_items = [
            '<item id="style" href="style.css" media-type="text/css"/>',
            '<item id="cover" href="cover.xhtml" media-type="application/xhtml+xml"/>',
            '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>',
            '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>',
        ]
        spine_items = [
            '<itemref idref="cover"/>',
            '<itemref idref="nav"/>',
        ]
        nav_points = []
        nav_lis = []

        # 4. 封面 XHTML
        words_count = meta.get("words", 0)
        intro_block = f'<div class="cover-intro"><p>{intro_esc}</p></div>' if intro_esc else ""
        cover_html = f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="zh-CN">
<head>
  <title>{title_esc}</title>
  <link rel="stylesheet" type="text/css" href="style.css"/>
</head>
<body>
  <div class="cover-wrap">
    <div class="cover-title">{title_esc}</div>
    <div class="cover-author">作者：{author_esc}</div>
    <div class="cover-meta">总字数：{words_count:,} 字 · 共 {len(chapters)} 章</div>
    {intro_block}
  </div>
</body>
</html>"""
        z.writestr("OEBPS/cover.xhtml", cover_html, compress_type=zipfile.ZIP_DEFLATED)

        # 5. 章节 XHTML
        for i, ch in enumerate(chapters):
            ch_title = ch.get("title") or f"第 {i + 1} 章"
            ch_title_esc = html.escape(ch_title)
            ch_content = ch.get("content") or ""
            paras = [f"<p>{html.escape(p.strip())}</p>" for p in ch_content.split("\n") if p.strip()]
            paras_html = "\n    ".join(paras) if paras else "<p>（本章无正文）</p>"

            ch_id = f"chapter_{i}"
            ch_fname = f"{ch_id}.xhtml"
            manifest_items.append(f'<item id="{ch_id}" href="{ch_fname}" media-type="application/xhtml+xml"/>')
            spine_items.append(f'<itemref idref="{ch_id}"/>')
            nav_points.append(f"""    <navPoint id="nav_{i}" playOrder="{i + 1}">
      <navLabel><text>{ch_title_esc}</text></navLabel>
      <content src="{ch_fname}"/>
    </navPoint>""")
            nav_lis.append(f'      <li><a href="{ch_fname}">{ch_title_esc}</a></li>')

            ch_xhtml = f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="zh-CN">
<head>
  <title>{ch_title_esc} - {title_esc}</title>
  <link rel="stylesheet" type="text/css" href="style.css"/>
</head>
<body>
  <h2>{ch_title_esc}</h2>
  <div class="chapter-content">
    {paras_html}
  </div>
</body>
</html>"""
            z.writestr(f"OEBPS/{ch_fname}", ch_xhtml, compress_type=zipfile.ZIP_DEFLATED)

        # 6. OEBPS/nav.xhtml (EPUB 3 导航)
        nav_lis_str = "\n".join(nav_lis)
        nav_html = f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="zh-CN">
<head>
  <title>目录 - {title_esc}</title>
  <link rel="stylesheet" type="text/css" href="style.css"/>
</head>
<body>
  <nav epub:type="toc" id="toc">
    <h2>目录</h2>
    <ol>
{nav_lis_str}
    </ol>
  </nav>
</body>
</html>"""
        z.writestr("OEBPS/nav.xhtml", nav_html, compress_type=zipfile.ZIP_DEFLATED)

        # 7. OEBPS/toc.ncx (EPUB 2 兼容目录)
        nav_points_str = "\n".join(nav_points)
        ncx_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head>
    <meta name="dtb:uid" content="urn:uuid:{book_id}"/>
    <meta name="dtb:depth" content="1"/>
    <meta name="dtb:totalPageCount" content="0"/>
    <meta name="dtb:maxPageNumber" content="0"/>
  </head>
  <docTitle><text>{title_esc}</text></docTitle>
  <docAuthor><text>{author_esc}</text></docAuthor>
  <navMap>
{nav_points_str}
  </navMap>
</ncx>"""
        z.writestr("OEBPS/toc.ncx", ncx_xml, compress_type=zipfile.ZIP_DEFLATED)

        # 8. OEBPS/content.opf (包清单与元数据)
        manifest_str = "\n    ".join(manifest_items)
        spine_str = "\n    ".join(spine_items)
        desc_xml = f"<dc:description>{intro_esc}</dc:description>" if intro_esc else ""
        opf_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="BookID" version="3.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">
    <dc:title>{title_esc}</dc:title>
    <dc:creator>{author_esc}</dc:creator>
    <dc:language>zh-CN</dc:language>
    <dc:identifier id="BookID">urn:uuid:{book_id}</dc:identifier>
    <meta property="dcterms:modified">{mod_time}</meta>
    {desc_xml}
  </metadata>
  <manifest>
    {manifest_str}
  </manifest>
  <spine toc="ncx">
    {spine_str}
  </spine>
</package>"""
        z.writestr("OEBPS/content.opf", opf_xml, compress_type=zipfile.ZIP_DEFLATED)

    return buf.getvalue()


@app.get("/api/novels/<name>/export")
def api_export_novel(name):
    """导出整本小说为 epub、txt 或 md。fmt=epub|txt|md"""
    p = safe_novel_path(name)
    if not p:
        return jsonify({"error": "小说不存在"}), 404
    fmt = request.args.get("fmt", "txt").lower()
    meta, chapters, _ = parse_novel(p)
    if _deny_private(meta, _request_token()):
        return jsonify({"error": "隐私书架已锁定，请先输入隐私密码", "locked": True}), 403
    title = meta.get("title", p.stem)

    from urllib.parse import quote
    if fmt == "epub":
        author = meta.get("author") or "AI 创作"
        job_payload = meta.get("job_payload") or {}
        intro = meta.get("intro") or job_payload.get("setting") or ""
        epub_data = generate_epub(title, author, intro, chapters, meta=meta)
        fname = f"{p.stem}.epub"
        resp = app.response_class(epub_data, mimetype="application/epub+zip")
        resp.headers["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote(fname)}"
        return resp
    elif fmt == "md":
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

    resp = app.response_class(content, mimetype=mime)
    resp.headers["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote(fname)}"
    return resp


@app.post("/api/novels/<name>/selection-assist")
def api_selection_assist(name):
    """划词局部 AI 辅助精修：扩写细节、转换文风、精简降水或自定义指示。"""
    p = safe_novel_path(name)
    if not p:
        return jsonify({"error": "小说不存在"}), 404
    data = request.get_json(force=True) or {}
    meta, _, _ = parse_novel(p)
    if _deny_private(meta, _request_token(data)):
        return jsonify({"error": "隐私书架已锁定，请先输入隐私密码", "locked": True}), 403
    selected_text = (data.get("selected_text") or "").strip()
    if not selected_text:
        return jsonify({"error": "未提供选中的文本片段"}), 400
    if len(selected_text) > 4000:
        return jsonify({"error": "选中文本过长，请选择 2000 字以内的局部片段进行精修"}), 400

    instruction_type = data.get("instruction_type") or "expand"
    style_target = (data.get("style_target") or "生动细腻").strip()
    custom_instruction = (data.get("custom_instruction") or "").strip()
    context_before = (data.get("context_before") or "")[-800:]
    context_after = (data.get("context_after") or "")[:800:]
    provider_id = data.get("provider_id")

    meta, _, _ = parse_novel(p)
    novel_title = meta.get("title", p.stem)
    novel_tone = (meta.get("style_profile") and meta["style_profile"].get("文风")) or ""

    if instruction_type == "expand":
        task_desc = "丰富并扩充所选文本的细节（五感、动作神态、环境氛围与心理描写），保持人物设定与情节连贯，使其更加生动细腻。"
    elif instruction_type == "style":
        task_desc = f"将所选文本改写为「{style_target}」风格，保持核心事件与信息不变，替换遣词造句与叙事语调。"
    elif instruction_type == "concise":
        task_desc = "对所选文本进行精简降水，剔除陈词滥调与冗余描述，加快叙事节奏，强化语言力度。"
    elif instruction_type == "custom":
        task_desc = f"根据要求进行针对性改写：{custom_instruction}" if custom_instruction else "润色并优化所选文本。"
    else:
        task_desc = "优化所选文本的行文质感与表达。"

    sys_prompt = (
        "你是一位精通小说改写与润色的资深文学编辑。"
        "你的任务是仅针对用户提供的【选中文本片段】进行局部改写/扩写/精修，使其完美嵌入上下文。"
        "严格规则：\n"
        "1. 只输出改写后的正文文字；\n"
        "2. 绝对不要输出任何前言、解释、前后缀标记（如：'以下是修改后的内容：'）、或用引号包裹；\n"
        "3. 保持前后剧情与标点承接自然。"
    )

    user_prompt = (
        f"小说书名：《{novel_title}》\n"
        f"{f'整体文风基调：{novel_tone}' if novel_tone else ''}\n\n"
        f"【上文语境】：\n...{context_before}\n\n"
        f"【需要修改的原文片段】：\n{selected_text}\n\n"
        f"【下文语境】：\n{context_after}...\n\n"
        f"【改写指令】：{task_desc}\n\n"
        "请直接输出改写后的正文片段："
    )

    try:
        content, _ = chat([
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_prompt}
        ], max_tokens=1500, temperature=0.7, provider_id=provider_id)
        result_text = content.strip()
        result_text = re.sub(r"^```(?:markdown|text)?\s*", "", result_text)
        result_text = re.sub(r"\s*```$", "", result_text).strip()
        if result_text.startswith("“") and result_text.endswith("”") and not selected_text.startswith("“"):
            result_text = result_text[1:-1].strip()
        elif result_text.startswith('"') and result_text.endswith('"') and not selected_text.startswith('"'):
            result_text = result_text[1:-1].strip()
        return jsonify({"ok": True, "result": result_text, "original": selected_text})
    except Exception as e:
        return jsonify({"error": f"AI 辅助改写失败：{str(e)}"}), 500


@app.post("/api/novels/<name>/chapters/delete")
def api_delete_chapter(name):
    """删除指定章节（0 基下标；原作章节不可删）。只删选中章，其余保留。"""
    p = safe_novel_path(name)
    if not p:
        return jsonify({"error": "小说不存在"}), 404

    with lock_novel(p.stem):
        data = request.get_json(force=True) or {}
        idx = int(data.get("index", -1))
        meta, chapters, _ = parse_novel(p)
        if _deny_private(meta, _request_token(data)):
            return jsonify({"error": "隐私书架已锁定，请先输入隐私密码", "locked": True}), 403
        if book_busy(p.stem):
            return jsonify({"error": "小说正在生成中，暂时无法删除章节"}), 409
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
    if book_busy(p.stem):
        return jsonify({"error": "小说正在生成中，暂时无法重写章节"}), 409
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


@app.route("/api/suggest-tropes", methods=["GET", "POST"], strict_slashes=False)
def api_suggest_tropes():
    """实时生成一批富有创意且结构化的小说灵感脑洞模板。"""
    if request.method == "GET":
        category = request.args.get("category") or "all"
        genre = (request.args.get("genre") or "").strip()
        provider_id = request.args.get("provider_id")
        try:
            count = min(max(int(request.args.get("count", 8)), 2), 12)
        except Exception:
            count = 8
    else:
        data = request.get_json(silent=True) or {}
        category = data.get("category") or "all"
        genre = (data.get("genre") or "").strip()
        provider_id = data.get("provider_id")
        try:
            count = min(max(int(data.get("count", 8)), 2), 12)
        except Exception:
            count = 8

    category_desc = ""
    if category == "female":
        category_desc = "侧重晋江/番茄女性向、现实情感与治愈生活：都市言情、青春校园、双女主/百合、都市日常、古代言情等多元细分题材。"
    elif category == "fantasy":
        category_desc = "侧重起点/番茄脑洞、奇幻科幻与探案传奇：刑侦推理、悬疑惊悚、赛博朋克、末世求生、古风武侠、西幻领主、无限流等多元脑洞题材。"
    else:
        category_desc = "题材与设定完全自由随机发散、高度多元！不拘泥于固定套路分类，涵盖但不限于：科幻未来、悬疑推理、无限流、蒸汽朋克、末日废土、奇幻诡秘、都市情感、现实日常、微恐惊悚、历史架空等多元脑洞组合。"

    import random
    sparks_pool = [
        "赛博修仙·反派夺舍", "蒸汽朋克·飞空艇海盗", "旧日诡秘·民俗怪谈", "第四天灾·幕后流",
        "末日废土·移动城堡", "星际拓荒·机甲种田", "无限流·民俗凶宅", "古风武侠·长安捉刀",
        "都市异能·时间回溯", "先婚后爱·双面间谍", "深海探险·远古遗迹", "微恐解谜·规则怪谈",
        "古代权谋·女帝心腹", "退役魔王·乡村慢生活", "硬核科幻·戴森球危机", "志怪传奇·山海百妖",
        "悬疑刑侦·第七个目击者", "百合纯爱·星际领航员", "反套路快穿·手撕剧本", "都市美食·深夜治愈食堂"
    ]
    random_sparks = "、".join(random.sample(sparks_pool, min(5, len(sparks_pool))))
    batch_seed = random.randint(1000, 9999)

    sys_prompt = (
        "你是一位精通各大网络文学平台（晋江文学城、起点中文网、番茄小说）的资深金牌策划编辑（suggest-tropes）。"
        f"请当场策划 {count} 个极具戏剧张力、设定新颖、高脑洞反差且完全随机多元的小说灵感开局模板。\n"
        "【核心原则】各卡片题材大类必须各不相同、彻底互斥，杜绝题材扎堆！语言短平快，拒绝冗长套话，突出核心矛盾与人设反差。\n"
        "必须严格输出符合 JSON 格式的对象，包含键 'tropes'（数组，每个元素为一个对象）：\n"
        "字段规范：\n"
        "- 'icon': 单个 emoji 图标\n"
        "- 'label': 标签简称（6-12字，格式为'题材·核心梗'）\n"
        "- 'title': 极具吸引力的网文书名\n"
        "- 'genre': 题材分类（必须多元互斥，不可重复）\n"
        "- 'setting': 世界观背景（精炼1-2句话交代核心设定即可）\n"
        "- 'characters': 主要角色（精炼1-2位核心人物身份与反差性格）\n"
        "- 'storyline': 主线故事与核心冲突（精炼1-2句话点明剧情主线）\n"
        "- 'style': 文风语调要求（简短描述）\n"
        "- 'perspective': '第三人称' 或 '第一人称'\n"
        "- 'chapters': 推荐初始章节数（8-12之间整数）\n"
        "- 'per_words': 推荐单章字数（2000-3000之间整数）"
    )

    user_prompt = f"请策划 {count} 个全新的小说开局灵感脑洞。\n要求：{category_desc}\n"
    if genre:
        user_prompt += f"指定重点偏好题材：{genre}\n"
    user_prompt += f"【随机激发源#{batch_seed}】：参考但不限于 {random_sparks} 等多元跨界方向。每个脑洞题材互不相同，注重人物动机与冲突反差。以 JSON 输出："

    try:
        content, _ = chat([
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_prompt}
        ], max_tokens=1800, temperature=1.05, json_mode=True, provider_id=provider_id)
        obj = extract_json(content)
        raw_tropes = obj.get("tropes") if isinstance(obj, dict) else (obj if isinstance(obj, list) else [])
        if not raw_tropes and isinstance(obj, dict):
            for k in ("templates", "list", "data", "items"):
                if isinstance(obj.get(k), list):
                    raw_tropes = obj[k]
                    break

        clean_tropes = []
        if isinstance(raw_tropes, list):
            for item in raw_tropes:
                if not isinstance(item, dict):
                    continue
                title = str(item.get("title") or item.get("book_name") or item.get("name") or "").strip()
                label = str(item.get("label") or item.get("tag") or title or "").strip()
                if not title and not label:
                    continue
                icon = str(item.get("icon") or "💡").strip() or "💡"
                t_genre = str(item.get("genre") or item.get("category") or genre or "都市").strip()
                setting = str(item.get("setting") or item.get("background") or "").strip()
                characters = str(item.get("characters") or item.get("roles") or "").strip()
                storyline = str(item.get("storyline") or item.get("plot") or item.get("outline") or "").strip()
                style = str(item.get("style") or "生动细腻，节奏明快").strip()
                perspective = str(item.get("perspective") or "第三人称").strip()
                try:
                    chapters = int(item.get("chapters", 10))
                except Exception:
                    chapters = 10
                try:
                    per_words = int(item.get("per_words", 2200))
                except Exception:
                    per_words = 2200

                cat_val = category
                if cat_val == "all":
                    cat_val = "female" if any(w in t_genre for w in ("言情", "校园", "双女", "百合", "婚恋", "日常")) else "fantasy"

                clean_tropes.append({
                    "icon": icon,
                    "label": label or title,
                    "title": title or label,
                    "genre": t_genre,
                    "setting": setting,
                    "characters": characters,
                    "storyline": storyline,
                    "style": style,
                    "perspective": perspective,
                    "chapters": chapters,
                    "per_words": per_words,
                    "cat": cat_val
                })
                if len(clean_tropes) >= count:
                    break

        if not clean_tropes:
            raise ValueError("模型未返回有效灵感模板")
        return jsonify({"ok": True, "tropes": clean_tropes})
    except Exception as e:
        return jsonify({"error": f"生成灵感脑洞失败：{str(e)}"}), 500


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
        if isinstance(bible, list):
            bible = {"characters": bible}
        elif not isinstance(bible, dict):
            bible = {}
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
        if isinstance(outline, list):
            outline = {"logline": "", "chapters": outline}
        elif not isinstance(outline, dict):
            outline = {"logline": "", "chapters": []}
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


@app.post("/api/generate-variants")
def api_generate_variants():
    """生成续写起手剧情候选小样（2 选 1）：为半自动导演模式提供走向选择。"""
    data = request.get_json(force=True) or {}
    novel_name = data.get("novel_name")
    instruction = (data.get("instruction") or "继续推进剧情").strip()
    provider_id = data.get("provider_id")

    title = ""
    tail_text = ""
    tone = ""

    if novel_name:
        p = safe_novel_path(novel_name)
        if p and p.exists():
            meta, chapters, _ = parse_novel(p)
            if _deny_private(meta, _request_token(data)):
                return jsonify({"error": "隐私书架已锁定，请先输入隐私密码", "locked": True}), 403
            if chapters:
                title = meta.get("title", p.stem)
                last_ch = chapters[-1]
                tail_text = (last_ch.get("content") or "")[-1200:]
                tone = (meta.get("style_profile") and meta["style_profile"].get("文风")) or ""

    if not tail_text and data.get("source_text"):
        tail_text = (data["source_text"] or "")[-1200:]
        title = data.get("source_title") or data.get("novel_name") or "未命名作品"
        if data.get("style_profile") and isinstance(data["style_profile"], dict):
            tone = data["style_profile"].get("文风", "")

    if not tail_text:
        if novel_name:
            p = safe_novel_path(novel_name)
            if not p or not p.exists():
                return jsonify({"error": "小说不存在"}), 404
            return jsonify({"error": "小说暂无章节，无法生成续写小样"}), 400
        return jsonify({"error": "缺少小说名称或正文上下文"}), 400

    sys_prompt = (
        "你是一位精通故事结构与情节推进的资深小说编辑兼编剧。"
        "你的任务是为小说的后续章节构思【两种截然不同走向的起手剧情小样（每样约 250-350 字）】，供作者/导演二选一。"
        "输出必须为严格的 JSON 对象，包含键 'variants'（数组，含两个对象）：\n"
        "每个对象含：\n"
        "- 'id': 'A' 或 'B'\n"
        "- 'title': 走向简述（8字以内，如'暗流涌动·潜行调查'、'正面冲突·突发意外'）\n"
        "- 'synopsis': 核心看点（1-2句说明该走向的戏剧冲突）\n"
        "- 'preview': 起手剧情正文片段（200-300字，承接前文，直接可作为下章开篇）"
    )

    user_prompt = (
        f"小说书名：《{title}》\n"
        f"{f'文风基调：{tone}' if tone else ''}\n"
        f"前文结局片段：\n...{tail_text}\n\n"
        f"当前续写指示：{instruction}\n\n"
        "请构思两种风格差异鲜明的剧情小样（例如：一个偏重伏笔反转/智斗，一个偏重正面交锋/突发危机），以 JSON 输出："
    )

    try:
        content, _ = chat([
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_prompt}
        ], max_tokens=1500, temperature=1.0, json_mode=True, provider_id=provider_id)
        obj = extract_json(content)
        variants = obj.get("variants") if isinstance(obj, dict) else (obj if isinstance(obj, list) else [])
        if not variants or len(variants) < 2:
            variants = [
                {"id": "A", "title": "方向 A：顺承推进", "synopsis": "顺应前文线索展开调查", "preview": content[:300]},
                {"id": "B", "title": "方向 B：突发意外", "synopsis": "引入突发事件打破僵局", "preview": content[300:600] if len(content) > 300 else "忽然间门外传来急促的脚步声..."}
            ]
        return jsonify({"ok": True, "variants": variants})
    except Exception as e:
        return jsonify({"error": f"生成剧情小样失败：{str(e)}"}), 500


@app.post("/api/generate")
def api_generate():
    data = request.get_json(force=True) or {}

    # 隐私书架：续写/断点续跑目标书为隐私书时必须已解锁
    _target = data.get("resume_novel") or data.get("novel_name") or data.get("source_title") or data.get("target_novel")
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

    # 计算目标书名用于排它性校验（复用 book_busy）
    target_book = None
    if data.get("novel_name"):
        _p = safe_novel_path(data["novel_name"])
        target_book = _p.stem if _p else sanitize_filename(data["novel_name"])
    elif data.get("source_title"):
        _p = safe_novel_path(data["source_title"])
        target_book = _p.stem if _p else sanitize_filename(data["source_title"])
    elif data.get("title"):
        _p = safe_novel_path(data["title"])
        target_book = _p.stem if _p else sanitize_filename(data["title"])

    if target_book and book_busy(target_book):
        return jsonify({"error": f"小说《{target_book}》正在生成中，请勿重复提交", "busy": True}), 409

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

    if target_book:
        if not acquire_book(target_book, holder=job["id"]):
            return jsonify({"error": f"小说《{target_book}》正在生成中，请勿重复提交", "busy": True}), 409

    t = threading.Thread(target=run_job_safe, args=(job, data, target_book), daemon=True)
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


@app.get("/api/jobs/<job_id>/stream")
def api_job_stream(job_id):
    """实时 Server-Sent Events (SSE) 流式推送生成文本与进度。"""
    job = JOBS.get(job_id)
    if not job:
        return jsonify({"error": "任务不存在"}), 404

    def generate_events():
        last_len = 0
        while True:
            cur_job = JOBS.get(job_id)
            if not cur_job:
                break
            st = cur_job.get("streaming_text") or ""
            if len(st) > last_len:
                chunk = st[last_len:]
                last_len = len(st)
                yield f"data: {json.dumps({'type': 'chunk', 'text': chunk, 'step': cur_job.get('step', ''), 'current': cur_job.get('current', 0), 'total': cur_job.get('total', 0)}, ensure_ascii=False)}\n\n"

            status = cur_job.get("status")
            if status in ("done", "error", "cancelled"):
                yield f"data: {json.dumps({'type': 'done', 'status': status, 'message': cur_job.get('message', ''), 'novel_name': cur_job.get('novel_name')}, ensure_ascii=False)}\n\n"
                break
            time.sleep(0.12)

    return Response(stream_with_context(generate_events()), mimetype="text/event-stream")


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
    print(f"NovelStudio 已启动： http://127.0.0.1:{port}")
    if host not in ("127.0.0.1", "localhost"):
        print("局域网访问已开启，同一 Wi-Fi 下手机浏览器可打开：")
        for u in _lan_urls(port):
            print("  " + u)
        print("提示：局域网内的其他设备也能访问本工具（公开书架与生成接口），请只在可信网络下使用。")
    app.run(host=host, port=port, debug=False, threaded=True)
