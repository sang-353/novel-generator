// ==================== 视图切换（hash 深链：URL 反映当前标签页） ====================
const VIEW_NAMES = ['original', 'continuation', 'library', 'settings'];
function switchView(name) {
  // 离开阅读器时收掉沉浸态与面板，并恢复页面标题
  if (name !== 'read') {
    document.body.classList.remove('reading', 'rd-immersive');
    document.title = '小说生成器';
    try { closeReaderPanels(); } catch (e) { /* 忽略 */ }
    try { if (typeof resetEditButtons === 'function') resetEditButtons(); } catch (e) { /* 忽略 */ }
  }
  document.querySelectorAll('header .nav').forEach(b => b.classList.toggle('active', b.dataset.view === name));
  document.querySelectorAll('section.view').forEach(s => s.classList.toggle('active', s.id === 'view-' + name));
  if (name === 'library') { loadLibrary(); loadPrivateShelf(); }
  if (name === 'settings') { loadSettings(); loadPrivacyState(); }
  if (name === 'original' || name === 'continuation') loadProviderSelects();
  if (name === 'continuation') {
    if (typeof loadExistingNovelsIntoContinuation === 'function') loadExistingNovelsIntoContinuation();
  }
}
document.querySelectorAll('header .nav').forEach(btn => {
  btn.onclick = () => {
    const cur = (location.hash || '').replace(/^#/, '');
    if (cur !== btn.dataset.view) location.hash = btn.dataset.view;
    else switchView(btn.dataset.view);
  };
});
function onHashChange() {
  const raw = (location.hash || '#original').replace(/^#/, '');
  // 阅读深链 #read/<书名>/<章号>：可刷新、可分享、浏览器「后退」回书架
  if (raw.indexOf('read/') === 0) {
    const parts = raw.split('/');
    const name = decodeURIComponent(parts[1] || '');
    const i = parts.length > 2 ? parseInt(parts[2]) : NaN;
    if (name) { openReader(name, isNaN(i) ? undefined : i, { fromHash: true }); return; }
  }
  const v = raw || 'original';
  if (VIEW_NAMES.includes(v)) switchView(v);
}
window.addEventListener('hashchange', onHashChange);
$('btn_manage_og').onclick = () => { location.hash = 'settings'; };
$('btn_manage_ct').onclick = () => { location.hash = 'settings'; };


// ==================== 初始化 ====================
function restoreProfileFromStorage() {
  const srcTitle = $('ct_source_title').value.trim();
  if (!srcTitle) return;
  try {
    const saved = localStorage.getItem('novel_profile_' + srcTitle);
    if (!saved) return;
    const p = JSON.parse(saved);
    if (p && typeof p === 'object') {
      styleProfile = p;
      renderStyleProfile(p);
      $('ct_style_box').textContent = JSON.stringify(p, null, 2);
      $('ct_style_card').style.display = 'block';
      $('btn_continue').disabled = false;
    }
  } catch (e) { /* 忽略恢复失败 */ }
}
// 输入书名时尝试恢复已保存的档案
$('ct_source_title').addEventListener('input', restoreProfileFromStorage);
restoreProfileFromStorage();
restoreOgDraft();
applyTheme();
// 表单控件补 name / autocomplete（防密码管理器误触发）
document.querySelectorAll('input, select, textarea').forEach(el => {
  if (!el.name && el.id) el.name = el.id;
  if (el.type !== 'file' && el.type !== 'radio' && el.type !== 'checkbox') {
    el.setAttribute('autocomplete', el.type === 'password' ? 'new-password' : 'off');
  }
});
onHashChange();
loadLibrary();
updateLibTrashBadge();
$('lib_refresh_btn').onclick = () => { loadLibrary(); updateLibTrashBadge(); };
$('lib_trash_toggle_btn').onclick = () => {
  const card = $('lib_trash_card');
  if (!card) return;
  const isShow = card.style.display !== 'none';
  card.style.display = isShow ? 'none' : 'block';
  if (!isShow) loadLibTrash();
};
$('lib_trash_close_btn').onclick = () => {
  const card = $('lib_trash_card');
  if (card) card.style.display = 'none';
};

window.addEventListener('keydown', e => {
  if (e.key === 'Escape') {
    const rm = $('rename_modal'); if (rm && rm.classList.contains('show')) rm.classList.remove('show');
    const bm = $('bible_modal'); if (bm && bm.classList.contains('show')) bm.classList.remove('show');
  }
});

// ==================== P2: 全站轻量访问口令拦截与登录 ====================
async function checkGlobalWebAuth() {
  try {
    const res = await api('/api/auth/status');
    if (res && res.enabled && !res.authorized) {
      showWebAuthModal();
    }
  } catch (e) {
    if (e.auth_required) showWebAuthModal();
  }
}
checkGlobalWebAuth();

const authLoginBtn = $('web_auth_login_btn');
if (authLoginBtn) {
  authLoginBtn.onclick = async () => {
    const pw = $('web_auth_input').value.trim();
    if (!pw) { toast('请输入访问口令'); return; }
    authLoginBtn.disabled = true;
    authLoginBtn.textContent = '验证中…';
    $('web_auth_err').textContent = '';
    try {
      const res = await api('/api/auth/login', 'POST', { password: pw });
      authLoginBtn.disabled = false;
      authLoginBtn.textContent = '解锁访问';
      if (res && res.ok && res.token) {
        setWebAccessToken(res.token);
        hideWebAuthModal();
        toast('口令验证成功，欢迎使用！');
        onHashChange();
        loadLibrary();
      }
    } catch (e) {
      authLoginBtn.disabled = false;
      authLoginBtn.textContent = '解锁访问';
      $('web_auth_err').textContent = e.message || '访问口令错误';
    }
  };
  const authInp = $('web_auth_input');
  if (authInp) {
    authInp.addEventListener('keydown', e => {
      if (e.key === 'Enter') authLoginBtn.click();
    });
  }
}
