// ==================== 设置（多 provider 管理） ====================
let providersState = [];   // [{id,name,base_url,api_key,model,temperature}]
let activeProviderId = '';

const PROVIDER_PRESETS = [
  { id: 'deepseek', label: 'DeepSeek', name: 'DeepSeek', base_url: 'https://api.deepseek.com', model: 'deepseek-chat', temperature: 1.0, hint: '从 platform.deepseek.com 获取' },
  { id: 'siliconflow', label: '硅基流动 (SiliconFlow)', name: 'SiliconFlow', base_url: 'https://api.siliconflow.cn/v1', model: 'deepseek-ai/DeepSeek-V3', temperature: 0.7, hint: '从 cloud.siliconflow.cn 获取' },
  { id: 'qwen', label: '通义千问 (DashScope)', name: '通义千问', base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1', model: 'qwen-plus', temperature: 0.8, hint: '从阿里云 DashScope 控制台获取' },
  { id: 'kimi', label: 'Kimi (Moonshot)', name: 'Kimi', base_url: 'https://api.moonshot.cn/v1', model: 'moonshot-v1-32k', temperature: 0.7, hint: '从 platform.moonshot.cn 获取' },
  { id: 'ollama', label: '本地 Ollama (免Key)', name: '本地 Ollama', base_url: 'http://localhost:11434/v1', model: 'qwen2.5:14b', temperature: 0.7, hint: '本地运行无需 Key，可填 ollama 或留空' },
  { id: 'openai', label: 'OpenAI (官方)', name: 'OpenAI', base_url: 'https://api.openai.com/v1', model: 'gpt-4o', temperature: 0.8, hint: '从 platform.openai.com 获取' }
];

function checkProviderStatus(providers) {
  const list = providers || providersState || [];
  const hasValid = list.some(p => (p.api_key && p.api_key.trim()) || (p.base_url && (p.base_url.includes('localhost') || p.base_url.includes('127.0.0.1'))));
  ['og_no_provider_banner', 'ct_no_provider_banner'].forEach(id => {
    const el = $(id);
    if (el) el.style.display = hasValid ? 'none' : 'flex';
  });
  return hasValid;
}

function renderPresetPills() {
  const box = $('provider_preset_pills');
  if (!box) return;
  box.innerHTML = PROVIDER_PRESETS.map(p => `
    <button type="button" class="tag-pill" data-preset="${p.id}" title="${p.base_url}">+ ${escapeHtml(p.label)}</button>
  `).join('');
  box.querySelectorAll('[data-preset]').forEach(btn => {
    btn.onclick = () => {
      const preset = PROVIDER_PRESETS.find(p => p.id === btn.dataset.preset);
      if (!preset) return;
      providersState.push({
        id: 'p_' + Date.now(),
        name: preset.name,
        base_url: preset.base_url,
        api_key: '',
        model: preset.model,
        temperature: preset.temperature
      });
      if (!activeProviderId) activeProviderId = providersState[providersState.length - 1].id;
      renderProviderList();
      toast('已添加 ' + preset.name + ' 预设模版，请填入 API Key 后点保存');
      const lastCard = document.querySelector('.provider-card:last-child');
      if (lastCard) {
        const keyInput = lastCard.querySelector('input[data-field="api_key"]');
        if (keyInput) keyInput.focus();
      }
    };
  });
}

function providerListHtml() {
  return providersState.map((p, idx) => `
    <div class="provider-card">
      <div class="phead">
        <input type="radio" name="active_provider" value="${escapeHtml(p.id)}" ${p.id === activeProviderId ? 'checked' : ''}
               title="设为默认" onchange="activeProviderId='${escapeHtml(p.id)}'">
        <b>${escapeHtml(p.name || ('模型 ' + (idx + 1)))}</b>
        <span class="mini">${p.id === activeProviderId ? '默认' : '设为默认'}</span>
        <button class="ghost" data-test="${idx}" style="padding:2px 10px;font-size:12px">测试</button>
        <span class="inline-status" data-status="${idx}"></span>
        <select class="preset-apply-sel" data-apply="${idx}" style="margin-left:auto;font-size:12px;padding:2px 6px;">
          <option value="">⚡ 套用厂商预设…</option>
          ${PROVIDER_PRESETS.map(pr => `<option value="${pr.id}">${pr.label}</option>`).join('')}
        </select>
        <button class="del" data-idx="${idx}">删除</button>
      </div>
      <div class="prow">
        <div><label>名称</label><input type="text" data-field="name" value="${escapeHtml(p.name || '')}" placeholder="如：DeepSeek / Kimi" aria-label="名称" autocomplete="off"></div>
        <div><label>模型名</label><input type="text" data-field="model" value="${escapeHtml(p.model || '')}" placeholder="如：deepseek-chat / gpt-4o" aria-label="模型名" autocomplete="off"></div>
      </div>
      <div class="prow">
        <div><label>接口地址</label><input type="text" data-field="base_url" value="${escapeHtml(p.base_url || '')}" placeholder="https://api.deepseek.com" aria-label="接口地址" autocomplete="off"></div>
        <div><label>temperature</label><input type="number" data-field="temperature" value="${p.temperature ?? 1.0}" min="0" max="2" step="0.1" aria-label="temperature" autocomplete="off"></div>
      </div>
      <label>API Key（掩码显示，留空表示不修改）</label>
      <input type="password" data-field="api_key" value="" placeholder="${p.api_key ? ('已保存：' + p.api_key) : 'sk-…'}" aria-label="API Key" autocomplete="new-password" spellcheck="false">
    </div>`).join('') || '<p class="mini">尚未配置任何模型，点击「添加模型」或上方预设。</p>';
}

function renderProviderList() {
  const list = $('provider_list');
  list.innerHTML = providerListHtml();
  renderPresetPills();
  const cards = [...list.querySelectorAll('.provider-card')];
  cards.forEach((card, idx) => {
    const prov = providersState[idx];
    card.querySelector('.del').onclick = () => {
      providersState.splice(idx, 1);
      if (activeProviderId === prov.id) activeProviderId = providersState[0]?.id || '';
      renderProviderList();
      checkProviderStatus(providersState);
    };
    const applySel = card.querySelector('[data-apply]');
    if (applySel) {
      applySel.onchange = () => {
        const pr = PROVIDER_PRESETS.find(x => x.id === applySel.value);
        if (pr) {
          prov.name = pr.name;
          prov.base_url = pr.base_url;
          prov.model = pr.model;
          prov.temperature = pr.temperature;
          renderProviderList();
          toast('已套用 ' + pr.name + ' 预设参数，请填入 API Key');
          const currentCard = list.querySelectorAll('.provider-card')[idx];
          if (currentCard) {
            const ki = currentCard.querySelector('input[data-field="api_key"]');
            if (ki) ki.focus();
          }
        }
      };
    }
    card.querySelector('[data-test]').onclick = async () => {
      const st = card.querySelector('[data-status]');
      st.textContent = '测试中…';
      try {
        const d = await api('/api/test', 'POST', { provider_id: prov.id, provider: prov });
        st.textContent = d.ok ? '连接正常：' + d.reply : '失败：' + d.error;
      } catch (e) { st.textContent = '失败：' + e.message; }
    };
    card.querySelectorAll('input[data-field]').forEach(inp => {
      inp.oninput = () => { prov[inp.dataset.field] = inp.value; };
    });
  });
}

async function loadSettings() {
  try {
    const d = await api('/api/settings');
    providersState = (d.providers || []).map(p => ({ ...p }));
    activeProviderId = d.active_provider || (providersState[0] && providersState[0].id) || '';
    renderProviderList();
    checkProviderStatus(providersState);
    await loadProviderSelects();
  } catch (e) { toast('读取设置失败：' + e.message); }
  loadTrash();
  loadChapterBackups();
  loadCacheStats();
  loadPrivacyState();
  loadWebAuthState();
}
$('btn_add_provider').onclick = () => {
  providersState.push({ id: 'p_' + Date.now(), name: '', base_url: '', api_key: '', model: '', temperature: 1.0 });
  if (!activeProviderId) activeProviderId = providersState[0].id;
  renderProviderList();
};
$('btn_save_settings').onclick = async () => {
  setStatus('st_status', '保存中…');
  try {
    await api('/api/settings', 'POST', { providers: providersState, active_provider: activeProviderId });
    setStatus('st_status', '已保存'); loadSettings();
    setTimeout(() => setStatus('st_status', ''), 2500);
  } catch (e) { setStatus('st_status', '失败：' + e.message); }
};
$('btn_test').onclick = async () => {
  setStatus('st_status', '测试中…');
  try {
    const d = await api('/api/test', 'POST', { provider_id: activeProviderId });
    setStatus('st_status', d.ok ? ('连接正常，模型回复：' + d.reply) : ('失败：' + d.error));
  } catch (e) { setStatus('st_status', '失败：' + e.message); }
};


// ==================== 模型选择下拉（原创/续写页共用） ====================
async function loadProviderSelects(preferId) {
  try {
    const d = await api('/api/settings');
    const list = d.providers || [];
    checkProviderStatus(list);
    const opts = list.map(p => `<option value="${escapeHtml(p.id)}">${escapeHtml((p.name || p.id) + ' · ' + (p.model || '?'))}</option>`).join('');
    ['og_provider', 'ct_provider'].forEach(id => {
      const sel = $(id);
      if (!sel) return;
      sel.innerHTML = opts || '<option value="">（请先在设置中添加模型）</option>';
      if (preferId && list.some(p => p.id === preferId)) sel.value = preferId;
      else if (d.active_provider) sel.value = d.active_provider;
    });
    const ogBtn = $('og_go_settings_btn'); if (ogBtn) ogBtn.onclick = () => { location.hash = 'settings'; };
    const ctBtn = $('ct_go_settings_btn'); if (ctBtn) ctBtn.onclick = () => { location.hash = 'settings'; };
  } catch (e) { /* 忽略 */ }
}

// 把模型选项加载进指定下拉，并尽量选中 preferId
async function loadProviderSelectsInto(selectId, preferId) {
  try {
    const d = await api('/api/settings');
    const list = d.providers || [];
    const sel = $(selectId);
    if (!sel) return;
    sel.innerHTML = list.map(p => `<option value="${escapeHtml(p.id)}">${escapeHtml((p.name || p.id) + ' · ' + (p.model || '?'))}</option>`).join('')
      || '<option value="">（请先在设置中添加模型）</option>';
    if (preferId && list.some(p => p.id === preferId)) sel.value = preferId;
    else if (d.active_provider) sel.value = d.active_provider;
  } catch (e) { /* 忽略 */ }
}


// ==================== 设置页：隐私密码 ====================
async function loadPrivacyState() {
  try {
    const d = await api('/api/privacy');
    $('pv_state').textContent = d.enabled
      ? '已设置隐私密码；更改密码需先填入当前密码。'
      : '尚未设置隐私密码；设置后才能把书移入隐私书架。';
  } catch (e) { $('pv_state').textContent = '读取失败：' + e.message; }
}
$('pv_save').onclick = async () => {
  const oldP = $('pv_old').value, newP = $('pv_new').value, newP2 = $('pv_new2').value;
  if (newP.length < 4) { setStatus('pv_save_status', '新密码至少 4 位'); return; }
  if (newP !== newP2) { setStatus('pv_save_status', '两次输入的新密码不一致'); return; }
  setStatus('pv_save_status', '保存中…');
  try {
    await api('/api/privacy/set', 'POST', { old_password: oldP, new_password: newP });
    $('pv_old').value = ''; $('pv_new').value = ''; $('pv_new2').value = '';
    setStatus('pv_save_status', '已保存');
    setPrivacyToken('');            // 改密码后需要重新解锁
    setStatus('pv_status', '');
    loadPrivacyState();
  } catch (e) { setStatus('pv_save_status', '失败：' + e.message); }
};

// ==================== 设置页：全站访问口令 ====================
async function loadWebAuthState() {
  const stateEl = $('web_auth_state');
  if (!stateEl) return;
  try {
    const d = await api('/api/auth/status');
    stateEl.textContent = d.enabled
      ? '已启用全站访问口令；外网/局域网访问时需凭口令登录。'
      : '尚未启用全站口令；外网部署暴露端口可能存在被盗刷风险。';
    const oldWrap = $('web_auth_old_wrap');
    if (oldWrap) oldWrap.style.display = d.enabled ? 'block' : 'none';
    const disableBtn = $('web_auth_disable_btn');
    if (disableBtn) disableBtn.style.display = d.enabled ? 'inline-block' : 'none';
  } catch (e) { stateEl.textContent = '读取状态失败：' + e.message; }
}

const authSaveBtn = $('web_auth_save_btn');
if (authSaveBtn) {
  authSaveBtn.onclick = async () => {
    const oldP = $('web_auth_old').value;
    const newP = $('web_auth_new').value;
    const newP2 = $('web_auth_new2').value;
    if (newP.length < 4) { setStatus('web_auth_save_status', '新口令至少 4 位'); return; }
    if (newP !== newP2) { setStatus('web_auth_save_status', '两次输入的新口令不一致'); return; }
    setStatus('web_auth_save_status', '保存中…');
    try {
      const res = await api('/api/auth/set-password', 'POST', { old_password: oldP, new_password: newP });
      $('web_auth_old').value = ''; $('web_auth_new').value = ''; $('web_auth_new2').value = '';
      if (res && res.token) setWebAccessToken(res.token);
      setStatus('web_auth_save_status', '设置成功！');
      toast('全站访问口令已生效');
      loadWebAuthState();
    } catch (e) { setStatus('web_auth_save_status', '失败：' + e.message); }
  };
}

const authDisableBtn = $('web_auth_disable_btn');
if (authDisableBtn) {
  authDisableBtn.onclick = async () => {
    const oldP = prompt('关闭全站访问口令，请输入当前访问口令：');
    if (!oldP) return;
    try {
      await api('/api/auth/set-password', 'POST', { old_password: oldP, new_password: '' });
      setWebAccessToken('');
      toast('全站访问口令已关闭');
      loadWebAuthState();
    } catch (e) { toast('关闭失败：' + e.message); }
  };
}

function escapeHtml(s) { return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
