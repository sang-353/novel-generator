// ==================== 工具 ====================
const $ = id => document.getElementById(id);
const on = (id, evOrFn, maybeFn) => {
  const el = $(id);
  if (!el) return;
  if (typeof evOrFn === 'function') {
    el.onclick = evOrFn;
  } else if (typeof maybeFn === 'function') {
    el.addEventListener(evOrFn, maybeFn);
  }
};
function toast(msg) {
  const t = $('toast'); t.textContent = msg; t.classList.add('show');
  clearTimeout(t._h); t._h = setTimeout(() => t.classList.remove('show'), 2600);
}
async function api(path, method = 'GET', body = null) {
  const opt = { method, headers: {} };
  const authTk = webAccessToken();
  if (authTk) opt.headers['Authorization'] = 'Bearer ' + authTk;
  if (body !== null) { opt.headers['Content-Type'] = 'application/json'; opt.body = JSON.stringify(body); }
  const r = await fetch(withToken(path), opt);
  const data = await r.json().catch(() => ({}));
  if (r.status === 401 || data.auth_required) {
    showWebAuthModal();
    const err = new Error(data.error || '需要全站访问口令');
    err.auth_required = true;
    throw err;
  }
  if (!r.ok) {
    const err = new Error(data.error || ('请求失败 ' + r.status));
    err.locked = !!data.locked;       // 隐私书架未解锁
    throw err;
  }
  return data;
}

// ---- 全站访问口令令牌（持久保存在 localStorage）----
function webAccessToken() {
  try { return localStorage.getItem('web_access_token') || ''; } catch (e) { return ''; }
}
function setWebAccessToken(t) {
  try {
    if (t) localStorage.setItem('web_access_token', t);
    else localStorage.removeItem('web_access_token');
  } catch (e) { /* 忽略 */ }
}
function showWebAuthModal() {
  const m = $('web_auth_modal');
  if (m) {
    m.style.display = 'flex';
    const inp = $('web_auth_input');
    if (inp) { inp.value = ''; setTimeout(() => inp.focus(), 100); }
  }
}
function hideWebAuthModal() {
  const m = $('web_auth_modal');
  if (m) m.style.display = 'none';
}

// ---- 隐私解锁令牌（仅存本标签页会话，关闭标签即失效）----
function privacyToken() {
  try { return sessionStorage.getItem('privacy_token') || ''; } catch (e) { return ''; }
}
function setPrivacyToken(t) {
  try {
    if (t) sessionStorage.setItem('privacy_token', t);
    else sessionStorage.removeItem('privacy_token');
  } catch (e) { /* 忽略 */ }
}
function withToken(path) {
  const tk = privacyToken();
  if (!tk) return path;
  return path + (path.includes('?') ? '&' : '?') + 'token=' + encodeURIComponent(tk);
}
function setStatus(el, text) {
  const e = $(el);
  if (!e) return;
  if (typeof text === 'string' && text.includes('<')) e.innerHTML = text;
  else e.textContent = text || '';
}

function escapeHtml(s) {
  return String(s || '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

function parseStyleProfile(sp) {
  if (!sp) return null;
  if (typeof sp === 'object') return sp;
  try { return JSON.parse(sp); } catch (e) { return null; }
}

function renderStyleProfile(profile, targetEl = null) {
  const box = targetEl || $('ct_style_summary');
  if (!box || !profile) return;
  const secs = [
    ['文风', profile.文风], ['叙事视角', profile.叙事视角], ['语言特色', profile.语言特色],
    ['当前剧情状态', profile.当前剧情状态], ['伏笔与线索', profile.伏笔与线索], ['续写要点', profile.续写要点],
  ];
  let html = '';
  for (const [k, v] of secs) {
    if (!v) continue;
    const val = Array.isArray(v) ? v.join('\n') : (typeof v === 'object' ? JSON.stringify(v, null, 2) : String(v));
    html += `<div class="profile-sec"><b>${k}</b><p>${escapeHtml(val)}</p></div>`;
  }
  const chars = profile.人物表;
  if (Array.isArray(chars) && chars.length) {
    html += `<div class="profile-sec"><b>人物表</b>`;
    chars.forEach(c => {
      if (!c) return;
      html += `<p>· ${escapeHtml(String(c.姓名 || c.name || ''))}${c.身份 ? '（' + escapeHtml(String(c.身份)) + '）' : ''}：${escapeHtml(String(c.性格 || c.当前状态 || ''))}</p>`;
    });
    html += `</div>`;
  }
  const naming = profile.章节命名规律;
  if (naming) {
    const desc = typeof naming === 'object' ? (naming.风格描述 || '') : String(naming);
    const samples = typeof naming === 'object' && Array.isArray(naming.标题样例) ? naming.标题样例 : [];
    html += `<div class="profile-sec"><b>章节命名规律</b><p>${escapeHtml(String(desc))}${samples.length ? '\n样例：' + samples.map(s => escapeHtml(String(s))).join(' / ') : ''}</p></div>`;
  }
  if (profile.备注) html += `<div class="profile-sec"><b>备注</b><p>${escapeHtml(String(profile.备注))}</p></div>`;
  box.innerHTML = html || '<p class="mini">（档案内容为空）</p>';
}
