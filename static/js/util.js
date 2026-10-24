// ==================== 工具 ====================
const $ = id => document.getElementById(id);
const on = (id, fn) => { const el = $(id); if (el) el.onclick = fn; };
function toast(msg) {
  const t = $('toast'); t.textContent = msg; t.classList.add('show');
  clearTimeout(t._h); t._h = setTimeout(() => t.classList.remove('show'), 2600);
}
async function api(path, method = 'GET', body = null) {
  const opt = { method, headers: {} };
  if (body !== null) { opt.headers['Content-Type'] = 'application/json'; opt.body = JSON.stringify(body); }
  const r = await fetch(withToken(path), opt);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) {
    const err = new Error(data.error || ('请求失败 ' + r.status));
    err.locked = !!data.locked;       // 隐私书架未解锁
    throw err;
  }
  return data;
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
