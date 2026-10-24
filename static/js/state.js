// ==================== 设置（多 provider 管理） ====================
let providersState = [];   // [{id,name,base_url,api_key,model,temperature}]
let activeProviderId = '';

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
      <input type="password" data-field="api_key" value="" placeholder="${p.api_key ? ('已保存：' + p.api_key) : 'sk-...'}" aria-label="API Key" autocomplete="new-password">
    </div>`).join('') || '<p class="mini">尚未配置任何模型，点击「添加模型」。</p>';
}

function renderProviderList() {
  const list = $('provider_list');
  list.innerHTML = providerListHtml();
  const cards = [...list.querySelectorAll('.provider-card')];
  cards.forEach((card, idx) => {
    const prov = providersState[idx];
    card.querySelector('.del').onclick = () => {
      providersState.splice(idx, 1);
      if (activeProviderId === prov.id) activeProviderId = providersState[0]?.id || '';
      renderProviderList();
    };
    card.querySelector('[data-test]').onclick = async () => {
      const st = card.querySelector('[data-status]');
      st.textContent = '测试中…';
      try {
        // 未保存的新增模型也可直接测试：把表单内容整体发给后端
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
    await loadProviderSelects();
  } catch (e) { toast('读取设置失败：' + e.message); }
  loadTrash();
  loadChapterBackups();
  loadCacheStats();
  loadPrivacyState();
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
    const opts = list.map(p => `<option value="${escapeHtml(p.id)}">${escapeHtml((p.name || p.id) + ' · ' + (p.model || '?'))}</option>`).join('');
    ['og_provider', 'ct_provider'].forEach(id => {
      const sel = $(id);
      if (!sel) return;
      sel.innerHTML = opts || '<option value="">（请先在设置中添加模型）</option>';
      if (preferId && list.some(p => p.id === preferId)) sel.value = preferId;
      else if (d.active_provider) sel.value = d.active_provider;
    });
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

function escapeHtml(s) { return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
