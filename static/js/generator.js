// static/js/generator.js - 续写 / 同人模块（原创生成已解耦迁移至 original_studio.js）

// ==================== 续写 / 同人 ====================
let styleProfile = null;

function continuationPayload() {
  return {
    mode: $('ct_mode').value,
    source_title: $('ct_source_title').value.trim(),
    source_author: $('ct_source_author').value.trim(),
    source_intro: $('ct_source_intro').value.trim(),
    source_text: $('ct_source_text').value,
    start_para: parseInt($('ct_start_para').value) || 0,
    twist: $('ct_twist').value.trim(),
    chapters: parseInt($('ct_chapters').value) || 1,
    per_chapter_words: parseInt($('ct_per_words').value) || 3000,
    extra: $('ct_extra').value.trim(),
    provider_id: $('ct_provider').value,
  };
}

// 段落切分规则与后端 split_source_paragraphs 保持一致：空行分段优先，单换行退化按行
function splitParagraphs(t) {
  const blank = t.split(/\n\s*\n/).map(s => s.trim()).filter(Boolean);
  if (blank.length > 1) return blank;
  return t.split(/\n+/).map(s => s.trim()).filter(Boolean);
}

function countParagraphs() {
  const t = $('ct_source_text').value.trim();
  const hint = $('ct_para_hint');
  const num = $('ct_start_para');
  if (!t) {
    hint.textContent = '';
    if (num) num.max = 0;
    updateShortHint();
    return;
  }
  const paras = splitParagraphs(t);
  if (num) {
    num.max = paras.length;
    if (parseInt(num.value) > paras.length) num.value = paras.length;
  }
  hint.textContent = '已识别 ' + paras.length + ' 个段落（0 = 从文末继续）';
  updateShortHint();
}

// 短文本（<=2000 字）可不经「通读全书」直接续写：后端会自动做快速风格分析
function updateShortHint() {
  const t = $('ct_source_text').value.trim();
  const btn = $('btn_continue');
  const status = $('ct_status');
  if (!styleProfile && t && t.length <= 2000) {
    btn.disabled = false;
    status.textContent = '文本较短，可直接「开始续写」（将自动快速分析风格）';
  } else if (!styleProfile && !t) {
    btn.disabled = true;
    status.textContent = '';
  }
}
on('ct_source_text', 'input', countParagraphs);

on('ct_file', 'change', e => {
  const f = e.target.files[0]; if (!f) return;
  const rd = new FileReader();
  rd.onload = () => {
    const buf = rd.result;
    let text = null, enc = 'UTF-8';
    try { text = new TextDecoder('utf-8', { fatal: true }).decode(buf); }
    catch (err) {
      try { text = new TextDecoder('gb18030').decode(buf); enc = 'GBK/GB18030'; }
      catch (err2) { text = null; }
    }
    if (text === null) { toast('无法识别文件编码'); return; }
    $('ct_source_text').value = text;
    countParagraphs();
    toast('已读取文件（' + enc + '）');
  };
  rd.onerror = () => toast('读取文件失败');
  rd.readAsArrayBuffer(f);
});

// ----- 1 通读全书（job 化，带进度） -----
function renderStyleProfile(profile, targetEl = null) {
  const box = targetEl || $('ct_style_summary');
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

// 解析可能为字符串或对象的风格档案（兼容旧数据）
function parseStyleProfile(sp) {
  if (!sp) return null;
  if (typeof sp === 'object') return sp;
  try { return JSON.parse(sp); } catch (e) { return null; }
}

on('btn_analyze', async () => {
  const btn = $('btn_analyze'); btn.disabled = true;
  setStatus('ct_status', '通读分析中…');
  $('ct_analyze_progress').style.display = 'block';
  setBar('ct_analyze_bar', 0);
  $('ct_analyze_text').textContent = '准备中…';
  const cancelBtn = $('ct_analyze_cancel');
  try {
    const d = await api('/api/analyze', 'POST', continuationPayload());
    cancelBtn.style.display = 'inline-block';
    cancelBtn.onclick = async () => {
      try { await api('/api/jobs/' + d.job_id + '/cancel', 'POST'); toast('已发送取消请求…'); }
      catch (e) { toast(e.message); }
    };
    const t0 = Date.now();
    let failCount = 0;
    const timer = setInterval(async () => {
      try {
        const j = await api('/api/jobs/' + d.job_id);
        failCount = 0;
        const pct = j.total ? Math.round(j.current / j.total * 100) : 0;
        setBar('ct_analyze_bar', pct);
        let txt = j.step || '';
        if (j.total > 2) {
          txt += `（${j.current}/${j.total}）`;
          if (j.chars_total) {
            const doneW = Math.round((j.chars_done || 0) / 10000 * 10) / 10;
            const totalW = Math.round(j.chars_total / 10000 * 10) / 10;
            txt += ` · 已读 ${doneW} 万字/共 ${totalW} 万字`;
          }
          if (j.eta > 0) txt += ` · 预计还需约 ${j.eta >= 60 ? Math.round(j.eta / 60) + ' 分钟' : j.eta + ' 秒'}`;
          else if (j.status === 'running') txt += ` · 已用时 ${Math.round((Date.now() - t0) / 1000)} 秒`;
        }
        $('ct_analyze_text').textContent = txt;
        if (j.status === 'done') {
          clearInterval(timer); cancelBtn.style.display = 'none';
          styleProfile = j.result || null;
          if (styleProfile) {
            renderStyleProfile(styleProfile);
            $('ct_style_box').textContent = JSON.stringify(styleProfile, null, 2);
            $('ct_style_card').style.display = 'block';
            renderCtBibleEditor(profileToBible(styleProfile));
            $('btn_continue').disabled = false;
            if ($('btn_continue_variants')) $('btn_continue_variants').disabled = false;
            // 按书名持久化档案，刷新后自动恢复查看
            const srcTitle = $('ct_source_title').value.trim() || '未命名';
            try { localStorage.setItem('novel_profile_' + srcTitle, JSON.stringify(styleProfile)); } catch (e) {}
            const step = j.step || '';
            if (step.includes('命中缓存')) setStatus('ct_status', '分析结果已命中缓存（未重新消耗额度）');
            else if (step.includes('已沿用本书档案')) setStatus('ct_status', '已复用本书已保存的创作档案（未重新消耗额度）');
            else setStatus('ct_status', '全书通读完成，可开始续写');
          } else {
            setStatus('ct_status', '分析结果为空（模型未返回有效档案），请点击「重新通读分析」重试');
            toast('分析结果为空，请重试');
          }
        } else if (j.status === 'error') {
          clearInterval(timer); cancelBtn.style.display = 'none';
          setStatus('ct_status', '失败：' + j.message); toast('通读失败：' + j.message);
        } else if (j.status === 'cancelled') {
          clearInterval(timer); cancelBtn.style.display = 'none';
          setStatus('ct_status', '分析已取消');
        }
      } catch (e) {
        failCount++;
        if (failCount >= 6) {
          clearInterval(timer); cancelBtn.style.display = 'none';
          $('ct_analyze_text').textContent = '生成服务连接中断（可能已重启）。刷新页面后重试。';
          setStatus('ct_status', '生成服务连接中断');
          toast('通读服务连接中断');
        }
      }
    }, 1200);
  } catch (e) { setStatus('ct_status', '失败：' + e.message); toast(e.message); }
  btn.disabled = false;
});
on('btn_reanalyze', () => {
  const btn = $('btn_analyze');
  if (btn) btn.click();
});

// ==================== 续写设定档案 (Bible) 编辑器 ====================
function renderCtBibleEditor(bible) {
  const b = bible || {};
  $('ct_bible_setting').value = b.setting || '';
  $('ct_bible_conflict').value = b.conflict || '';
  $('ct_bible_tone').value = b.tone || '';
  renderCtBibleCharCards(b.characters || []);
  syncCtBibleRawJson();
  $('ct_bible_card').style.display = 'block';
}

function renderCtBibleCharCards(chars) {
  const box = $('ct_bible_chars');
  if (!chars.length) {
    box.innerHTML = '<p class="mini" style="color:var(--muted);padding:8px 0;">暂无角色档案，点击「+ 添加角色」进行补充</p>';
    return;
  }
  box.innerHTML = chars.map((c, i) => `
    <div class="char-card" data-idx="${i}">
      <div class="char-card-hd">
        <input type="text" class="char-name" value="${escapeHtml(c.name || '')}" placeholder="角色姓名">
        <input type="text" class="char-role" value="${escapeHtml(c.role || '')}" placeholder="身份/定位（如：主角 / 盟友）">
        <button type="button" class="btn-oc-action danger" data-act="del-char" title="删除角色" aria-label="删除角色">×</button>
      </div>
      <div class="char-card-bd">
        <input type="text" class="char-desc" value="${escapeHtml(c.desc || '')}" placeholder="性格特征、外貌或现状…">
        <input type="text" class="char-goal" value="${escapeHtml(c.goal || '')}" placeholder="当前目标、关系或行动动机…">
      </div>
    </div>`).join('');

  box.querySelectorAll('.char-card').forEach(card => {
    const idx = parseInt(card.dataset.idx);
    card.querySelector('[data-act=del-char]').onclick = () => {
      const b = collectCtBible();
      b.characters.splice(idx, 1);
      renderCtBibleCharCards(b.characters);
      syncCtBibleRawJson();
    };
    card.querySelectorAll('input').forEach(inp => {
      inp.oninput = syncCtBibleRawJson;
    });
  });
}

function collectCtBible() {
  const chars = [...$('ct_bible_chars').querySelectorAll('.char-card')].map(card => ({
    name: card.querySelector('.char-name').value.trim(),
    role: card.querySelector('.char-role').value.trim(),
    desc: card.querySelector('.char-desc').value.trim(),
    goal: card.querySelector('.char-goal').value.trim(),
  })).filter(c => c.name || c.role || c.desc);

  return {
    setting: $('ct_bible_setting').value.trim(),
    characters: chars,
    conflict: $('ct_bible_conflict').value.trim(),
    tone: $('ct_bible_tone').value.trim(),
  };
}

function syncCtBibleRawJson() {
  const data = collectCtBible();
  const rawEl = $('ct_bible_raw');
  if (rawEl) rawEl.value = JSON.stringify(data, null, 2);
}

on('btn_add_ct_bible_char', () => {
  const b = collectCtBible();
  b.characters.push({ name: '', role: '', desc: '', goal: '' });
  renderCtBibleCharCards(b.characters);
  syncCtBibleRawJson();
});

on('btn_toggle_ct_bible_raw', () => {
  const el = $('ct_bible_raw');
  if (!el) return;
  const isHidden = el.style.display === 'none';
  el.style.display = isHidden ? 'block' : 'none';
  if ($('btn_toggle_ct_bible_raw')) {
    $('btn_toggle_ct_bible_raw').textContent = isHidden ? '收起原始 JSON' : '查看原始 JSON';
  }
});

function profileToBible(sp) {
  if (!sp) return { setting: '', characters: [], conflict: '', tone: '' };
  const rawChars = sp['人物表'] || sp.characters || [];
  const chars = Array.isArray(rawChars) ? rawChars.map(c => ({
    name: c.姓名 || c.name || '',
    role: c.身份 || c.role || '',
    desc: c.性格 || c.当前状态 || c.desc || '',
    goal: c.关系 || c.goal || '',
  })) : [];
  let setting = '';
  if (sp['当前剧情状态']) {
    setting = Array.isArray(sp['当前剧情状态']) ? sp['当前剧情状态'].join('\n') : String(sp['当前剧情状态']);
  }
  let conflict = '';
  if (sp['续写要点']) {
    conflict = Array.isArray(sp['续写要点']) ? sp['续写要点'].join('；') : String(sp['续写要点']);
  }
  let tone = '';
  if (sp['文风']) {
    tone = String(sp['文风']);
  }
  return { setting, characters: chars, conflict, tone };
}

// ==================== P2: 续写 2 选 1 候选小样流程 ====================
async function runVariantsFlow(payload) {
  const wrap = $('ct_variants_wrap');
  const cardsBox = $('ct_variants_cards');
  if (!wrap || !cardsBox) return;

  wrap.style.display = 'block';
  cardsBox.innerHTML = '<div style="grid-column:1/-1;text-align:center;padding:24px;color:var(--muted);"><span class="rd-spin"></span> 正在构思两种不同走向的剧情小样…</div>';

  try {
    const res = await api('/api/generate-variants', 'POST', {
      novel_name: payload.novel_name || payload.source_title,
      instruction: payload.instruction || payload.extra || '顺应情节推进下章',
      provider_id: payload.provider_id
    });
    const variants = (res && res.variants) || [];
    if (!variants.length) throw new Error('未返回有效小样');

    cardsBox.innerHTML = variants.map(v => `
      <div class="variant-card" data-id="${v.id}">
        <div>
          <div class="variant-card-head">
            <span class="variant-card-title">${escapeHtml(v.title || ('走向 ' + v.id))}</span>
            <span class="variant-badge">方向 ${v.id}</span>
          </div>
          <div class="variant-card-synopsis">${escapeHtml(v.synopsis || '')}</div>
          <div class="variant-card-preview">${escapeHtml(v.preview || '')}</div>
        </div>
        <button type="button" class="primary variant-select-btn">选用此走向继续写 →</button>
      </div>
    `).join('');

    cardsBox.querySelectorAll('.variant-card').forEach((card, idx) => {
      const v = variants[idx];
      const chooseBtn = card.querySelector('.variant-select-btn');
      chooseBtn.onclick = async (e) => {
        e.stopPropagation();
        chooseBtn.disabled = true;
        chooseBtn.textContent = '启动生成中…';
        const addInst = `【采纳剧情走向】：${v.title}。${v.preview}`;
        payload.instruction = (payload.instruction ? payload.instruction + '\n\n' : '') + addInst;
        wrap.style.display = 'none';
        try {
          const d = await api('/api/generate', 'POST', payload);
          startPolling('ct', d.job_id, 'ct_progress_card', payload.source_title || '未命名续写', 'round');
        } catch (err) {
          toast(err.message);
        }
      };
    });

    on('ct_variants_retry_btn', () => runVariantsFlow(payload));
  } catch (e) {
    cardsBox.innerHTML = `<div style="grid-column:1/-1;text-align:center;padding:16px;color:var(--err);">生成小样失败：${escapeHtml(e.message)}</div>`;
  }
}

on('btn_continue_variants', async () => {
  const payload = continuationPayload();
  payload.style_profile = styleProfile;
  payload.bible = collectCtBible();
  await runVariantsFlow(payload);
});

async function loadExistingNovelsIntoContinuation() {
  const sel = $('ct_existing_sel');
  if (!sel) return;
  try {
    const novels = await api('/api/novels');
    const curVal = sel.value;
    sel.innerHTML = '<option value="">-- 选择书架中的已有小说 --</option>' +
      novels.map(n => `<option value="${escapeHtml(n.name)}">${escapeHtml(n.title || n.name)} (${n.chapters_count || 0}章 · ${(n.type === 'fanfic' ? '同人' : (n.type === 'continuation' ? '续写' : '原创'))})</option>`).join('');
    if (curVal) sel.value = curVal;
  } catch (e) {}
}

on('ct_open_round_btn', () => {
  const name = $('ct_existing_sel') ? $('ct_existing_sel').value : '';
  if (!name) { toast('请先在下拉列表中选择要续写的小说'); return; }
  openContinueCard(name, 'continuation');
});

on('ct_open_variants_btn', async () => {
  const name = $('ct_existing_sel') ? $('ct_existing_sel').value : '';
  if (!name) { toast('请先在下拉列表中选择要续写的小说'); return; }
  await openContinueCard(name, 'continuation');
  await runRoundVariantsFlow();
});

on('btn_continue', async () => {
  const btn = $('btn_continue');
  if (btn && btn.disabled) return;
  if (btn) btn.disabled = true;

  const payload = continuationPayload();
  payload.style_profile = styleProfile;
  payload.bible = collectCtBible();
  const useVariants = $('ct_use_variants') && $('ct_use_variants').checked;
  if (useVariants) {
    try {
      await runVariantsFlow(payload);
    } finally {
      if (btn) btn.disabled = false;
    }
    return;
  }
  try {
    const d = await api('/api/generate', 'POST', payload);
    startPolling('ct', d.job_id, 'ct_progress_card', payload.source_title || '未命名续写', 'round');
  } catch (e) {
    toast(e.message);
    if (btn) btn.disabled = false;
  }
});


// ==================== 任务轮询 ====================
const activePollingStreams = {};
const activePollingTimers = {};

function setGenerateButtonsDisabled(prefix, disabled) {
  if (prefix === 'ct') {
    const bc = $('btn_continue'); if (bc) bc.disabled = disabled;
  }
}

// 进度条用 transform: scaleX 驱动（合成器友好，避免 width 触发布局）
function setBar(id, pct) {
  const el = $(id);
  if (!el) return;
  const p = Math.max(0, Math.min(100, Math.round(pct || 0)));
  el.style.transform = 'scaleX(' + (p / 100) + ')';
}

function startPolling(prefix, jobId, cardId, defaultTitle, doneAction = null) {
  setGenerateButtonsDisabled(prefix, true);

  // 开启新连接前先关闭旧的 EventSource 与轮询计时器
  if (activePollingStreams[prefix]) {
    try { activePollingStreams[prefix].close(); } catch (err) {}
    activePollingStreams[prefix] = null;
  }
  if (activePollingTimers[prefix]) {
    clearInterval(activePollingTimers[prefix]);
    activePollingTimers[prefix] = null;
  }

  const card = $(cardId); card.style.display = 'block';
  setBar(prefix + '_progress_bar', 0);
  $(prefix + '_progress_text').textContent = '准备中…';
  $(prefix + '_progress_msg').textContent = '';
  $(prefix + '_open_reader').style.display = 'none';

  // 实时流式预览初始化
  const streamWrap = $(prefix + '_stream_wrap');
  const streamBody = $(prefix + '_stream_body');
  const liveBadge = $(prefix + '_live_badge');
  const streamWords = $(prefix + '_stream_words');
  const streamCh = $(prefix + '_stream_ch');
  if (streamWrap && streamBody) {
    streamBody.textContent = '';
    streamWrap.style.display = 'block';
    if (liveBadge) liveBadge.style.display = 'inline-flex';
    if (streamWords) streamWords.textContent = '';
    if (streamCh) streamCh.textContent = '正文创作实时预览';
  }

  try {
    const es = new EventSource('/api/jobs/' + jobId + '/stream');
    activePollingStreams[prefix] = es;
    es.onmessage = e => {
      try {
        const d = JSON.parse(e.data);
        if (d.type === 'chunk' && d.text) {
          if (streamBody) {
            streamBody.textContent += d.text;
            streamBody.scrollTop = streamBody.scrollHeight;
            if (streamWords) streamWords.textContent = '已输出 ' + streamBody.textContent.replace(/\s/g, '').length + ' 字';
          }
          if (d.step && streamCh) streamCh.textContent = d.step;
        } else if (d.type === 'done') {
          if (activePollingStreams[prefix]) {
            try { activePollingStreams[prefix].close(); } catch (err) {}
            activePollingStreams[prefix] = null;
          }
          if (liveBadge) liveBadge.style.display = 'none';
        }
      } catch (err) {}
    };
    es.onerror = () => {
      if (activePollingStreams[prefix]) {
        try { activePollingStreams[prefix].close(); } catch (err) {}
        activePollingStreams[prefix] = null;
      }
    };
  } catch (err) {}

  let failCount = 0;
  const cancelBtn = $(prefix + '_cancel_job');
  if (cancelBtn) {
    cancelBtn.style.display = 'inline-block';
    cancelBtn.onclick = async () => {
      try { await api('/api/jobs/' + jobId + '/cancel', 'POST'); toast('已发送取消请求，将在当前章节完成后停止…'); }
      catch (e) { toast(e.message); }
    };
  }

  const timer = setInterval(async () => {
    try {
      const j = await api('/api/jobs/' + jobId);
      failCount = 0;
      const pct = j.total ? Math.round(j.current / j.total * 100) : 0;
      setBar(prefix + '_progress_bar', pct);
      $(prefix + '_progress_text').textContent = j.step + (j.current && j.total ? `（${j.current}/${j.total}）` : '');
      $(prefix + '_progress_msg').textContent = j.message || '';

      // 兜底更新流式输出（防止个别环境下 SSE 阻断）
      if (streamBody && j.streaming_text && (!streamBody.textContent || streamBody.textContent.length < j.streaming_text.length)) {
        streamBody.textContent = j.streaming_text;
        streamBody.scrollTop = streamBody.scrollHeight;
        if (streamWords) streamWords.textContent = '已输出 ' + streamBody.textContent.replace(/\s/g, '').length + ' 字';
      }
      if (j.step && streamCh) streamCh.textContent = j.step;

      if (j.status === 'done') {
        clearInterval(timer);
        activePollingTimers[prefix] = null;
        if (activePollingStreams[prefix]) {
          try { activePollingStreams[prefix].close(); } catch (err) {}
          activePollingStreams[prefix] = null;
        }
        setGenerateButtonsDisabled(prefix, false);
        if (liveBadge) liveBadge.style.display = 'none';
        if (cancelBtn) cancelBtn.style.display = 'none';
        $(prefix + '_progress_text').textContent = '生成完成';
        if (j.novel_name) {
          const rd = $(prefix + '_open_reader');
          rd.style.display = 'inline-block';
          rd.dataset.novel = j.novel_name;
          rd.onclick = () => openReader(j.novel_name);
        }
        toast('生成完成');
        if (doneAction === 'round' && j.novel_name && (j.mode === 'continuation' || j.mode === 'fanfic')) {
          openContinueCard(j.novel_name, j.mode, { fromRound: true });
        }
      } else if (j.status === 'error') {
        clearInterval(timer);
        activePollingTimers[prefix] = null;
        if (activePollingStreams[prefix]) {
          try { activePollingStreams[prefix].close(); } catch (err) {}
          activePollingStreams[prefix] = null;
        }
        setGenerateButtonsDisabled(prefix, false);
        if (liveBadge) liveBadge.style.display = 'none';
        if (cancelBtn) cancelBtn.style.display = 'none';
        $(prefix + '_progress_text').textContent = '生成失败：' + j.message;
        toast('生成失败：' + j.message);
      } else if (j.status === 'cancelled') {
        clearInterval(timer);
        activePollingTimers[prefix] = null;
        if (activePollingStreams[prefix]) {
          try { activePollingStreams[prefix].close(); } catch (err) {}
          activePollingStreams[prefix] = null;
        }
        setGenerateButtonsDisabled(prefix, false);
        if (liveBadge) liveBadge.style.display = 'none';
        if (cancelBtn) cancelBtn.style.display = 'none';
        $(prefix + '_progress_text').textContent = '任务已取消（已生成章节保留，可到阅读器「从断点继续」）';
        toast('任务已取消');
      }
    } catch (e) {
      failCount++;
      if (failCount >= 6) {
        clearInterval(timer);
        activePollingTimers[prefix] = null;
        if (activePollingStreams[prefix]) {
          try { activePollingStreams[prefix].close(); } catch (err) {}
          activePollingStreams[prefix] = null;
        }
        setGenerateButtonsDisabled(prefix, false);
        if (liveBadge) liveBadge.style.display = 'none';
        if (cancelBtn) cancelBtn.style.display = 'none';
        $(prefix + '_progress_text').textContent = '生成服务连接中断（服务可能已重启）。可刷新页面后到书架「从断点继续」。';
        toast('生成服务连接中断');
      }
    }
  }, 1500);
  activePollingTimers[prefix] = timer;
}


// ==================== 续写/重写任务卡片 ====================
let roundNovelName = null;   // 关联的小说
let roundMode = null;        // continuation | fanfic | rewrite
let roundProviderId = null;  // 该书所用模型 id
let roundChapterIdx = null;  // 重写模式下的章节下标

// 卡片要用的书籍数据：阅读器里已经拉过整本就直接复用。
// 否则点一次「继续续写」会把整本书重新下载一遍 —— 19MB 的书在手机上要等几十秒，
// 而且旧写法是「下载完才弹卡片」，用户看到的就是「点了没反应」。
async function novelForCard(novelName) {
  if (readerData && readerData.name === novelName) return readerData;
  return await api('/api/novels/' + encodeURIComponent(novelName) + '?toc=1');
}

// 打开续写卡片（阅读器「继续续写」或轮次完成后）
async function openContinueCard(novelName, mode, opts = {}) {
  roundNovelName = novelName; roundMode = mode; roundChapterIdx = null;
  // 先把卡片弹出来，再去取数据；取数期间「开始续写」置灰
  $('rm_title').textContent = (opts.fromRound ? '本轮续写完成' : '续写') + '《' + novelName + '》';
  $('rm_summary').textContent = '加载中…';
  if ($('rm_variants_box')) $('rm_variants_box').style.display = 'block';
  if ($('rm_variants_wrap')) $('rm_variants_wrap').style.display = 'none';
  if ($('rm_variants_btn')) $('rm_variants_btn').style.display = 'inline-flex';
  if ($('rm_use_variants')) $('rm_use_variants').checked = false;
  $('rm_instruction_label').textContent = opts.fromRound ? '下一轮续写指示（可选）' : '续写指示（可选，可调整后续走向）';
  $('rm_instruction').value = '';
  $('rm_instruction').placeholder = '如：让主角发现某个秘密 / 加快节奏 / 引入新角色 / 解开某处伏笔…';
  $('rm_chapters_wrap').style.display = 'block';
  $('rm_chapters').value = 1;
  $('rm_per_words').value = 3000;
  $('rm_preview').style.display = 'none';
  $('rm_start').textContent = '开始续写';
  $('rm_start').disabled = true;
  showRoundForm();
  openModal('round_modal', {
    mask: true,
    esc: true,
    canClose: () => {
      const p = $('rm_progress');
      return !(p && p.style.display !== 'none');
    },
    onClose: cleanupRoundModalState
  });
  try {
    const d = await novelForCard(novelName);
    const meta = d.meta;
    roundProviderId = meta.provider_id || null;
    $('rm_title').textContent = (opts.fromRound ? '本轮续写完成' : '续写') + '《' + (meta.title || novelName) + '》';
    $('rm_summary').textContent =
      `全书共 ${d.chapters.length} 章（含原作）· ${d.words.toLocaleString()} 字` +
      (meta.model_used ? ` · 上次模型：${meta.model_used}` : '');
    $('rm_per_words').value = meta.job_payload && meta.job_payload.per_chapter_words || 3000;
    const last = d.chapters[d.chapters.length - 1];
    if (opts.fromRound && last) {
      $('rm_preview').style.display = 'block';
      const ctext = last.content || '';
      $('rm_preview').textContent = `${last.title}\n\n${ctext.slice(0, 500)}${ctext.length > 500 ? '\n……' : ''}`;
    }
    $('rm_start').disabled = false;
    await loadProviderSelectsInto('rm_provider', roundProviderId);
  } catch (e) {
    $('rm_summary').textContent = '加载失败：' + e.message;
    toast('加载失败：' + e.message);
  }
}

// 打开重写卡片
async function openRewriteCard(novelName, chapterIdx) {
  roundNovelName = novelName; roundMode = 'rewrite'; roundChapterIdx = chapterIdx;
  $('rm_title').textContent = '重写《' + novelName + '》';
  $('rm_summary').textContent = '加载中…';
  if ($('rm_variants_box')) $('rm_variants_box').style.display = 'none';
  if ($('rm_variants_wrap')) $('rm_variants_wrap').style.display = 'none';
  if ($('rm_variants_btn')) $('rm_variants_btn').style.display = 'none';
  $('rm_instruction_label').textContent = '重写要求（可选）';
  $('rm_instruction').value = '';
  $('rm_instruction').placeholder = '如：换一种写法 / 让本章更紧凑 / 突出某个情节…';
  $('rm_chapters_wrap').style.display = 'none';
  $('rm_per_words').value = 3000;
  $('rm_preview').style.display = 'none';
  $('rm_start').textContent = '开始重写';
  $('rm_start').disabled = true;
  showRoundForm();
  openModal('round_modal', {
    mask: true,
    esc: true,
    canClose: () => {
      const p = $('rm_progress');
      return !(p && p.style.display !== 'none');
    },
    onClose: cleanupRoundModalState
  });
  try {
    const d = await novelForCard(novelName);
    const meta = d.meta;
    const ch = d.chapters[chapterIdx];
    roundProviderId = meta.provider_id || null;
    $('rm_title').textContent = '重写《' + (meta.title || novelName) + '》· ' + (ch ? ch.title : '');
    $('rm_summary').textContent = '将以本章之前的内容为上下文重新生成，编号保持不变。' + (meta.model_used ? ` · 上次模型：${meta.model_used}` : '');
    $('rm_per_words').value = meta.job_payload && meta.job_payload.per_chapter_words || 3000;
    $('rm_start').disabled = false;
    await loadProviderSelectsInto('rm_provider', roundProviderId);
  } catch (e) {
    $('rm_summary').textContent = '加载失败：' + e.message;
    toast('加载失败：' + e.message);
  }
}

function showRoundForm() {
  $('rm_form').style.display = 'block';
  $('rm_progress').style.display = 'none';
  setBar('rm_bar', 0);
  $('rm_cancel_job').style.display = 'none';
}

function showRoundProgress() {
  $('rm_form').style.display = 'none';
  $('rm_progress').style.display = 'block';
  $('rm_progress_text').textContent = '准备中…';
}

let roundJobId = null, roundTimer = null, roundEs = null;

function cleanupRoundModalState() {
  if (roundTimer) { clearInterval(roundTimer); roundTimer = null; }
  if (roundEs) { roundEs.close(); roundEs = null; }
  roundJobId = null;
  roundNovelName = null; roundMode = null; roundChapterIdx = null;
}

function closeRoundModal() {
  closeModal('round_modal');
  cleanupRoundModalState();
}

on('rm_cancel', closeRoundModal);
on('rm_close', closeRoundModal);

async function runRoundVariantsFlow() {
  if (!roundNovelName) { toast('请先选择要续写的小说'); return; }
  const wrap = $('rm_variants_wrap');
  const cardsBox = $('rm_variants_cards');
  if (!wrap || !cardsBox) return;

  wrap.style.display = 'block';
  cardsBox.innerHTML = `<div style="grid-column:1/-1;text-align:center;padding:24px;color:var(--muted);"><span class="rd-spin"></span> 正在为《${escapeHtml(roundNovelName)}》构思两种不同走向的剧情小样…</div>`;
  if (wrap.scrollIntoView) wrap.scrollIntoView({ behavior: 'smooth', block: 'nearest' });

  try {
    const res = await api('/api/generate-variants', 'POST', {
      novel_name: roundNovelName,
      instruction: $('rm_instruction').value.trim() || '继续推进剧情',
      provider_id: $('rm_provider').value
    });
    const variants = (res && res.variants) || [];
    if (!variants.length) throw new Error('未返回有效小样');

    cardsBox.innerHTML = variants.map(v => `
      <div class="variant-card" data-id="${v.id}">
        <div>
          <div class="variant-card-head">
            <span class="variant-card-title">${escapeHtml(v.title || ('走向 ' + v.id))}</span>
            <span class="variant-badge">方向 ${v.id}</span>
          </div>
          <div class="variant-card-synopsis">${escapeHtml(v.synopsis || '')}</div>
          <div class="variant-card-preview">${escapeHtml(v.preview || '')}</div>
        </div>
        <button type="button" class="primary variant-select-btn" data-id="${v.id}">✅ 采纳此走向并开始续写 →</button>
      </div>
    `).join('');

    cardsBox.querySelectorAll('.variant-select-btn').forEach((btn, idx) => {
      const v = variants[idx];
      btn.onclick = async (e) => {
        e.stopPropagation();
        btn.disabled = true;
        btn.textContent = '启动生成中…';
        const addInst = `【采纳剧情走向】：${v.title}。${v.preview}`;
        wrap.style.display = 'none';
        await startRoundJob(addInst);
      };
    });

    on('rm_variants_retry_btn', () => runRoundVariantsFlow());
  } catch (e) {
    cardsBox.innerHTML = `<div style="grid-column:1/-1;text-align:center;padding:16px;color:var(--err);">生成小样失败：${escapeHtml(e.message)}</div>`;
  }
}

on('rm_variants_btn', () => runRoundVariantsFlow());
on('rm_trigger_variants_btn', () => runRoundVariantsFlow());

on('rm_start', async () => {
  if ($('rm_use_variants') && $('rm_use_variants').checked && roundMode !== 'rewrite') {
    await runRoundVariantsFlow();
    return;
  }
  await startRoundJob();
});

async function startRoundJob(extraInstruction = null) {
  if (!roundNovelName) return;
  const providerId = $('rm_provider').value;
  showRoundProgress();
  const cancelBtn = $('rm_cancel_job');

  const streamWrap = $('rm_stream_wrap');
  const streamBody = $('rm_stream_body');
  const liveBadge = $('rm_live_badge');
  const streamWords = $('rm_stream_words');
  const streamCh = $('rm_stream_ch');
  if (streamWrap && streamBody) {
    streamBody.textContent = '';
    streamWrap.style.display = 'block';
    if (liveBadge) liveBadge.style.display = 'inline-flex';
    if (streamWords) streamWords.textContent = '';
    if (streamCh) streamCh.textContent = '正文创作实时预览';
  }

  try {
    let jobId;
    if (roundMode === 'rewrite') {
      const r = await api('/api/novels/' + encodeURIComponent(roundNovelName) + '/chapters/rewrite', 'POST', {
        index: roundChapterIdx,
        per_chapter_words: parseInt($('rm_per_words').value) || 3000,
        provider_id: providerId,
        extra: $('rm_instruction').value.trim(),
      });
      jobId = r.job_id;
    } else {
      let finalInst = $('rm_instruction').value.trim();
      if (extraInstruction) {
        finalInst = finalInst ? (finalInst + '\n\n' + extraInstruction) : extraInstruction;
      }
      const r = await api('/api/generate', 'POST', {
        mode: roundMode,
        novel_name: roundNovelName,
        new_instruction: finalInst,
        chapters: parseInt($('rm_chapters').value) || 1,
        per_chapter_words: parseInt($('rm_per_words').value) || 3000,
        provider_id: providerId,
      });
      jobId = r.job_id;
    }
    roundJobId = jobId;
    cancelBtn.style.display = 'inline-block';
    cancelBtn.onclick = async () => {
      try { await api('/api/jobs/' + roundJobId + '/cancel', 'POST'); toast('已发送取消请求，将在当前章节完成后停止…'); }
      catch (e) { toast(e.message); }
    };

    if (roundEs) { roundEs.close(); roundEs = null; }
    try {
      roundEs = new EventSource('/api/jobs/' + jobId + '/stream');
      roundEs.onmessage = e => {
        try {
          const d = JSON.parse(e.data);
          if (d.type === 'chunk' && d.text) {
            if (streamBody) {
              streamBody.textContent += d.text;
              streamBody.scrollTop = streamBody.scrollHeight;
              if (streamWords) streamWords.textContent = '已输出 ' + streamBody.textContent.replace(/\s/g, '').length + ' 字';
            }
            if (d.step && streamCh) streamCh.textContent = d.step;
          } else if (d.type === 'done') {
            if (roundEs) { roundEs.close(); roundEs = null; }
            if (liveBadge) liveBadge.style.display = 'none';
          }
        } catch (err) {}
      };
      roundEs.onerror = () => { if (roundEs) { roundEs.close(); roundEs = null; } };
    } catch (err) {}

    // 卡片内轮询进度
    let failCount = 0;
    roundTimer = setInterval(async () => {
      try {
        const j = await api('/api/jobs/' + jobId);
        failCount = 0;
        const pct = j.total ? Math.round(j.current / j.total * 100) : 0;
        setBar('rm_bar', pct);
        $('rm_progress_text').textContent = j.step + (j.current && j.total ? `（${j.current}/${j.total}）` : '');

        if (streamBody && j.streaming_text && (!streamBody.textContent || streamBody.textContent.length < j.streaming_text.length)) {
          streamBody.textContent = j.streaming_text;
          streamBody.scrollTop = streamBody.scrollHeight;
          if (streamWords) streamWords.textContent = '已输出 ' + streamBody.textContent.replace(/\s/g, '').length + ' 字';
        }
        if (j.step && streamCh) streamCh.textContent = j.step;

        if (j.status === 'done') {
          clearInterval(roundTimer); roundTimer = null;
          if (roundEs) { roundEs.close(); roundEs = null; }
          if (liveBadge) liveBadge.style.display = 'none';
          cancelBtn.style.display = 'none';
          $('rm_progress_text').textContent = '完成';
          toast('完成');
          setTimeout(() => { closeRoundModal(); if (readerData && readerData.name === roundNovelName) openReader(roundNovelName); }, 600);
        } else if (j.status === 'error') {
          clearInterval(roundTimer); roundTimer = null;
          if (roundEs) { roundEs.close(); roundEs = null; }
          if (liveBadge) liveBadge.style.display = 'none';
          cancelBtn.style.display = 'none';
          $('rm_progress_text').textContent = '失败：' + j.message;
          toast('失败：' + j.message);
        } else if (j.status === 'cancelled') {
          clearInterval(roundTimer); roundTimer = null;
          if (roundEs) { roundEs.close(); roundEs = null; }
          if (liveBadge) liveBadge.style.display = 'none';
          cancelBtn.style.display = 'none';
          $('rm_progress_text').textContent = '任务已取消';
          toast('任务已取消');
          $('rm_close').textContent = '关闭';
        }
      } catch (e) {
        failCount++;
        if (failCount >= 6) {
          clearInterval(roundTimer); roundTimer = null;
          if (roundEs) { roundEs.close(); roundEs = null; }
          if (liveBadge) liveBadge.style.display = 'none';
          cancelBtn.style.display = 'none';
          $('rm_progress_text').textContent = '生成服务连接中断（服务可能已重启）';
          toast('生成服务连接中断');
        }
      }
    }, 1500);
  } catch (e) {
    $('rm_progress_text').textContent = '失败：' + e.message;
    toast('失败：' + e.message);
    cancelBtn.style.display = 'none';
  }
};
