// ==================== 视图切换（hash 深链：URL 反映当前标签页） ====================
const VIEW_NAMES = ['original', 'continuation', 'library', 'settings'];
function switchView(name) {
  // 离开阅读器时收掉沉浸态与面板，并恢复页面标题
  if (name !== 'read') {
    document.body.classList.remove('reading', 'rd-immersive');
    document.title = 'NovelStudio';
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
on('btn_manage_og', () => { location.hash = 'settings'; });
on('btn_manage_ct', () => { location.hash = 'settings'; });


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
on('ct_source_title', 'input', restoreProfileFromStorage);
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
on('lib_refresh_btn', () => { loadLibrary(); updateLibTrashBadge(); });
on('lib_trash_toggle_btn', () => {
  const card = $('lib_trash_card');
  if (!card) return;
  const isShow = card.style.display !== 'none';
  card.style.display = isShow ? 'none' : 'block';
  if (!isShow) loadLibTrash();
});
on('lib_trash_close_btn', () => {
  const card = $('lib_trash_card');
  if (card) card.style.display = 'none';
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

// ==================== P3: 文风与提示词模板设置 ====================

let promptTemplatesData = {};
let activePromptTid = 'default';

async function loadPromptSettings() {
  const pillsWrap = $('prompt_template_pills');
  const descEl = $('prompt_template_desc');
  const customInp = $('prompt_custom_instruction');
  const statusEl = $('prompt_settings_status');

  if (!pillsWrap) return;

  try {
    const res = await api('/api/settings/prompts', 'GET');
    if (res && res.ok && res.templates) {
      promptTemplatesData = res.templates;
      activePromptTid = res.active || 'default';
      renderPromptPills();
    }
  } catch (e) {
    if (statusEl) statusEl.textContent = '加载文风模板失败：' + e.message;
  }
}

function renderPromptPills() {
  const pillsWrap = $('prompt_template_pills');
  const descEl = $('prompt_template_desc');
  const customInp = $('prompt_custom_instruction');
  if (!pillsWrap) return;

  pillsWrap.innerHTML = '';
  Object.keys(promptTemplatesData).forEach(tid => {
    const tmpl = promptTemplatesData[tid];
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'tag-pill' + (tid === activePromptTid ? ' active' : '');
    btn.textContent = tmpl.name || tid;
    btn.onclick = () => {
      activePromptTid = tid;
      renderPromptPills();
    };
    pillsWrap.appendChild(btn);
  });

  const cur = promptTemplatesData[activePromptTid];
  if (cur) {
    if (descEl) descEl.innerHTML = `<b>【${escapeHtml(cur.name || activePromptTid)}】</b> ${escapeHtml(cur.desc || '')}`;
    if (customInp) customInp.value = cur.instruction || '';
  }
}

function initPromptSettings() {
  const saveBtn = $('btn_save_prompt_settings');
  const customInp = $('prompt_custom_instruction');
  const statusEl = $('prompt_settings_status');

  if (saveBtn) {
    saveBtn.onclick = async () => {
      const instruction = customInp ? customInp.value.trim() : '';
      saveBtn.disabled = true;
      saveBtn.textContent = '正在保存…';
      if (statusEl) statusEl.textContent = '保存中…';

      try {
        const payload = {
          active: activePromptTid,
          custom_template: {
            id: activePromptTid,
            name: (promptTemplatesData[activePromptTid] && promptTemplatesData[activePromptTid].name) || activePromptTid,
            instruction: instruction
          }
        };
        const res = await api('/api/settings/prompts', 'POST', payload);
        if (res && res.ok) {
          promptTemplatesData = res.templates;
          activePromptTid = res.active;
          renderPromptPills();
          toast('✅ 文风模板已成功保存！');
          if (statusEl) statusEl.textContent = '已保存！';
        }
      } catch (e) {
        toast('保存失败：' + e.message);
        if (statusEl) statusEl.textContent = '保存失败：' + e.message;
      } finally {
        saveBtn.disabled = false;
        saveBtn.textContent = '保存文风模板';
      }
    };
  }
}

// Hook into switchView
const origSwitchView = window.switchView;
if (typeof origSwitchView === 'function') {
  window.switchView = function(name) {
    origSwitchView(name);
    if (name === 'settings') {
      loadPromptSettings();
    }
  };
}

initPromptSettings();
