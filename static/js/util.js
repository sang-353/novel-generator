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
    err.status = r.status;
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

// ==================== 全局通用模态弹窗栈与显隐统一管理 ====================
const MODAL_STACK = [];

/**
 * 统一打开模态弹窗，兼容 .show 与 style.display，推入弹窗栈并绑定遮罩点击
 * @param {string} modalId - 如 'shortcuts_modal' 或 '#shortcuts_modal'
 * @param {Object} [options]
 * @param {boolean} [options.mask=true] - 点击遮罩层是否关闭（编辑类传 false）
 * @param {boolean} [options.esc=true] - 按 Esc 是否关闭
 * @param {Function} [options.canClose] - 关闭拦截前置判断（返回 false 则阻止关闭）
 * @param {Function} [options.onClose] - 关闭后的自定义清理回调
 */
function openModal(modalId, options = {}) {
  const id = modalId.replace('#', '');
  const el = $(id);
  if (!el) return;

  // 1. 显隐处理：同时兼容 class="show" 与 style.display
  el.classList.add('show');
  if (el.style.display === 'none') {
    el.style.display = 'flex';
  }

  // 2. 推入活动弹窗栈（若已在栈中先移除再压入栈顶）
  const existingIdx = MODAL_STACK.findIndex(item => item.id === id);
  if (existingIdx !== -1) MODAL_STACK.splice(existingIdx, 1);
  const entry = { id, el, options };
  MODAL_STACK.push(entry);

  // 3. 点击遮罩背景事件绑定（仅初始化一次）
  if (!el._modalMaskBound) {
    el._modalMaskBound = true;
    el.addEventListener('mousedown', (e) => {
      // 只有直接点击最外层 mask 容器本身时才触发
      if (e.target === el) {
        const cur = MODAL_STACK.find(it => it.id === id);
        const allowMask = cur && cur.options ? cur.options.mask !== false : true;
        const canClose = cur && cur.options && cur.options.canClose ? cur.options.canClose() : true;
        if (allowMask && canClose) {
          closeModal(id);
        }
      }
    });
  }
}

/**
 * 统一关闭模态弹窗，自动从弹窗栈中移除
 * @param {string} modalId - 如 'shortcuts_modal' 或 '#shortcuts_modal'
 */
function closeModal(modalId) {
  const id = modalId.replace('#', '');
  const el = $(id);
  if (!el) return;

  el.classList.remove('show');
  if (el.style.display && el.style.display !== 'none') {
    el.style.display = 'none';
  }

  const idx = MODAL_STACK.findIndex(item => item.id === id);
  if (idx !== -1) {
    const entry = MODAL_STACK.splice(idx, 1)[0];
    if (entry && entry.options && typeof entry.options.onClose === 'function') {
      try { entry.options.onClose(); } catch (err) { console.error(err); }
    }
  }
}

// 统一全局 Esc 键调度器：严格只关闭活动弹窗栈顶的那个弹窗
window.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && MODAL_STACK.length > 0) {
    const top = MODAL_STACK[MODAL_STACK.length - 1];
    const allowEsc = top.options ? top.options.esc !== false : true;
    const canClose = top.options && top.options.canClose ? top.options.canClose() : true;
    if (allowEsc && canClose) {
      e.preventDefault();
      closeModal(top.id);
    }
  }
});
