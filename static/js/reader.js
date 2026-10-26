// ==================== 阅读器 ====================
let readerData = null, readerIdx = 0, tocMode = 'toc';
const chapterFetchPromises = new Map();

async function ensureChapterContent(novelName, idx) {
  if (!readerData || readerData.name !== novelName) return null;
  const ch = readerData.chapters && readerData.chapters[idx];
  if (!ch) return null;
  if (typeof ch.content === 'string') return ch;

  const key = novelName + ':' + idx;
  if (chapterFetchPromises.has(key)) {
    return await chapterFetchPromises.get(key);
  }

  const p = (async () => {
    try {
      const res = await api('/api/novels/' + encodeURIComponent(novelName) + '/chapter/' + idx);
      if (res && res.ok) {
        ch.content = res.content || '';
        ch.words = typeof res.words === 'number' ? res.words : (ch.content ? ch.content.replace(/\s/g, '').length : 0);
        if (res.title) ch.title = res.title;
        return ch;
      }
    } catch (e) {
      console.warn('Failed to load chapter', idx, e);
      throw e;
    } finally {
      chapterFetchPromises.delete(key);
    }
    return ch;
  })();

  chapterFetchPromises.set(key, p);
  return await p;
}

function prefetchAdjacentChapters(novelName, currentIdx) {
  if (!readerData || readerData.name !== novelName) return;
  const toPrefetch = [currentIdx + 1, currentIdx - 1];
  for (const idx of toPrefetch) {
    if (idx >= 0 && idx < readerData.chapters.length) {
      const ch = readerData.chapters[idx];
      if (ch && typeof ch.content !== 'string') {
        ensureChapterContent(novelName, idx).catch(() => {});
      }
    }
  }
}

// ---- 阅读设置：全部存 localStorage，改完立即生效 ----
// 正文排版只由 CSS 变量驱动（见 .chapter-body），这里负责写变量与回显控件。
const RD_DEFAULTS = { size: 17, lh: 1.9, gap: 0.85, measure: 38, font: 'sans', indent: '1', theme: 'paper' };
const RD_KEYS = { size: 'reader_font_size', lh: 'reader_line_height', gap: 'reader_para_gap',
                  measure: 'reader_measure', font: 'reader_font', indent: 'reader_indent', theme: 'reader_theme' };
const RD_THEMES = ['paper', 'sepia', 'green', 'night', 'black'];
const RD_BG = { paper: '#FFFFFF', sepia: '#F5EBD8', green: '#CFE9D3', night: '#15171B', black: '#000000' };

function rdGet(k) {
  const def = RD_DEFAULTS[k];
  let v = null;
  try { v = localStorage.getItem(RD_KEYS[k]); } catch (e) { /* 忽略 */ }
  if (v === null || v === '') return def;
  if (k === 'font' || k === 'indent' || k === 'theme') return v;
  const n = parseFloat(v);
  return isNaN(n) ? def : n;
}
function rdSet(k, v) { try { localStorage.setItem(RD_KEYS[k], String(v)); } catch (e) { /* 忽略 */ } }

// 旧版只有一个「夜间」开关，迁移成主题设置
(function migrateReaderTheme() {
  try {
    if (!localStorage.getItem(RD_KEYS.theme) && localStorage.getItem('reader_dark') === '1') {
      localStorage.setItem(RD_KEYS.theme, 'night');
    }
  } catch (e) { /* 忽略 */ }
})();

function applyReaderSettings() {
  const st = document.documentElement.style;
  st.setProperty('--rd-size', rdGet('size') + 'px');
  st.setProperty('--rd-lh', String(rdGet('lh')));
  st.setProperty('--rd-gap', rdGet('gap') + 'em');
  st.setProperty('--rd-measure', String(rdGet('measure')));
  st.setProperty('--rd-indent', rdGet('indent') === '0' ? '0em' : '2em');
  const theme = RD_THEMES.includes(rdGet('theme')) ? rdGet('theme') : 'paper';
  document.body.dataset.rdTheme = theme;
  // 夜间 / 纯黑同时切全局夜间，书架与设置页保持同一套观感
  const dark = theme === 'night' || theme === 'black';
  document.body.classList.toggle('dark', dark);
  document.documentElement.style.colorScheme = dark ? 'dark' : 'light';
  const meta = document.querySelector('meta[name=theme-color]');
  if (meta) meta.content = RD_BG[theme] || '#FFFFFF';
  const cb = $('rd_content');
  if (cb) cb.classList.toggle('serif', rdGet('font') === 'serif');
  // 面板回显
  const put = (id, v) => { const e = $(id); if (e) e.textContent = v; };
  put('rd_font_val', rdGet('size'));
  put('rd_lh_val', rdGet('lh').toFixed(2));
  put('rd_gap_val', rdGet('gap').toFixed(2));
  put('rd_measure_val', rdGet('measure'));
  const bind = (id, v) => { const e = $(id); if (e) e.value = v; };
  bind('rd_font_range', rdGet('size'));
  bind('rd_lh_range', rdGet('lh'));
  bind('rd_gap_range', rdGet('gap'));
  bind('rd_measure_range', rdGet('measure'));
  document.querySelectorAll('[data-rd-font]').forEach(b => b.classList.toggle('on', b.dataset.rdFont === rdGet('font')));
  document.querySelectorAll('[data-rd-indent]').forEach(b => b.classList.toggle('on', b.dataset.rdIndent === rdGet('indent')));
  document.querySelectorAll('[data-rd-theme-btn]').forEach(b => b.classList.toggle('on', b.dataset.rdThemeBtn === theme));
}
// 兼容旧调用名（初始化与旧代码会调用这两个）
function applyTheme() { applyReaderSettings(); }
function applyReaderFont() { applyReaderSettings(); return rdGet('size'); }

// ---- 阅读位置：章节号 + 章内滚动偏移（刷新 / 换设备回来能接上） ----
function readerOffKey() { return 'reader_off_' + (readerData ? readerData.name : ''); }
function saveReaderPos() {
  if (!readerData) return;
  try {
    localStorage.setItem('reader_pos_' + readerData.name, String(readerIdx));
    const el = $('rd_content');
    if (el) localStorage.setItem(readerOffKey(), String(Math.max(0, Math.round(-el.getBoundingClientRect().top))));
  } catch (e) { /* 忽略 */ }
}
function restoreReaderPos() {
  try {
    const v = parseInt(localStorage.getItem('reader_pos_' + readerData.name));
    if (!isNaN(v) && v >= 0 && v < readerData.chapters.length) readerIdx = v;
  } catch (e) { /* 忽略 */ }
}
// 还原章内滚动位置。offset 必须由调用方在「渲染之前」读出来：
// renderChapter() 结尾会调 saveReaderPos()，那时滚动还在 0，会把刚记住的偏移覆盖掉。
function restoreReaderScroll(off) {
  try {
    if (!off || off <= 0) return;
    const el = $('rd_content');
    if (!el) return;
    window.scrollTo(0, Math.max(0, el.getBoundingClientRect().top + window.scrollY + off));
  } catch (e) { /* 忽略 */ }
}
function readSavedOffset(name) {
  try { return parseInt(localStorage.getItem('reader_off_' + name)); }
  catch (e) { return NaN; }
}

// ---- 阅读器的面板状态：桌面用侧栏（collapsed），手机用全屏抽屉（open） ----
function isWide() { return window.innerWidth > 900; }
function tocVisible() {
  const el = $('rd_toc');
  return isWide() ? !el.classList.contains('collapsed') : el.classList.contains('open');
}
function setTocOpen(open) {
  const el = $('rd_toc');
  if (isWide()) { el.classList.toggle('collapsed', !open); el.classList.remove('open'); }
  else { el.classList.toggle('open', !!open); }
  const mask = $('rd_mask');
  if (mask) {
    const sheetOpen = $('rd_settings').classList.contains('open') || $('rd_more').classList.contains('open');
    mask.classList.toggle('open', !isWide() && !!(open || sheetOpen));
  }
}
function closeReaderPanels() {
  ['rd_settings', 'rd_more'].forEach(id => { const el = $(id); if (el) el.classList.remove('open'); });
  if (!isWide()) $('rd_toc').classList.remove('open');
  const modal = $('rd_assist_modal');
  if (modal) modal.style.display = 'none';
  $('rd_mask').classList.remove('open');
}
function openSheet(id) {
  closeReaderPanels();
  $(id).classList.add('open');
  $('rd_mask').classList.add('open');
}
function liveGenNow() {
  const m = readerData && readerData.meta;
  return !!(m && m.status === 'generating' && !readerData.stale);
}
// 慢网络下给个明确的加载反馈，别让应用看起来像没反应
function showBusy(text) {
  const el = $('rd_loading');
  if (!el) return;
  if (text) { const t = $('rd_loading_text'); if (t) t.textContent = text; el.hidden = false; }
  else el.hidden = true;
}
function showReaderView() {
  document.body.classList.add('reading');
  document.querySelectorAll('header .nav').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('section.view').forEach(s => s.classList.remove('active'));
  $('view-reader').classList.add('active');
}
// 阅读位置写进 URL（#read/书名/章号）：可刷新、可分享、浏览器后退回书架
function syncReaderHash(name, idx, replace) {
  const want = '#read/' + encodeURIComponent(name) + '/' + idx;
  if (location.hash === want) return;
  try { if (replace) history.replaceState(null, '', want); else location.hash = want; }
  catch (e) { location.hash = want; }
}

async function openReader(name, idx, opts) {
  opts = opts || {};
  // 同一本书：只切章，不重新拉接口（目录、深层链接、生成完成回调都会走到这里）
  if (readerData && readerData.name === name && !opts.reload) {
    showReaderView();
    if (typeof idx === 'number' && idx !== readerIdx) gotoChapter(idx, false);
    syncReaderHash(name, readerIdx, true);
    return;
  }
  const busyTimer = setTimeout(() => showBusy('正在打开《' + name + '》…'), 350);
  try {
    chapterFetchPromises.clear();
    const d = await api('/api/novels/' + encodeURIComponent(name) + '?toc=1');
    // 记住的章节号：只有 URL 指向的章节跟它一致时才还原章内滚动位置，
    // 这样「刷新页面」能接上原来的位置，而「明确跳到另一章」则从章首开始。
    const remembered = (() => {
      try { const v = parseInt(localStorage.getItem('reader_pos_' + name)); return isNaN(v) ? null : v; }
      catch (e) { return null; }
    })();
    const savedOff = readSavedOffset(name);
    readerData = d; readerIdx = 0;
    restoreReaderPos();
    if (typeof idx === 'number' && idx >= 0 && idx < d.chapters.length) readerIdx = idx;
    const wantScroll = (typeof idx !== 'number') || (remembered !== null && remembered === readerIdx);
    tocMode = 'toc';
    $('rd_toc_filter').value = '';
    showReaderView();
    renderReader();
    closeReaderPanels();
    setTocOpen(isWide());
    const astPanel = $('rd_assistant');
    const astToggle = $('rd_assistant_toggle');
    if (astPanel) {
      if (isWide()) {
        astPanel.classList.remove('collapsed');
        if (astToggle) astToggle.classList.add('active');
      } else {
        astPanel.classList.add('collapsed');
        if (astToggle) astToggle.classList.remove('active');
      }
    }
    syncStudioBible();
    if (typeof loadProviderSelectsInto === 'function' && $('ast_ct_provider')) {
      loadProviderSelectsInto('ast_ct_provider', (readerData.meta && readerData.meta.provider_id) || undefined);
    }
    document.body.classList.remove('rd-immersive');
    if (typeof idx === 'number') window.scrollTo(0, 0);
    syncReaderHash(name, readerIdx, typeof idx === 'number');

    const cur = readerIdx;
    ensureChapterContent(name, cur).then(() => {
      if (readerData && readerData.name === name && readerIdx === cur) {
        renderChapter();
        requestAnimationFrame(() => {
          if (wantScroll) restoreReaderScroll(savedOff);
          updateReadingProgress();
        });
      }
      prefetchAdjacentChapters(name, cur);
    }).catch(e => {
      console.warn('Load chapter failed', e);
    });
  } catch (e) {
    if (e.locked) {
      toast('这是一本隐私书籍，请先在书架下方解锁隐私书架');
      document.querySelector('header .nav[data-view=library]').click();
      loadPrivateShelf();
      setTimeout(() => { const inp = $('pv_password'); if (inp) inp.focus(); }, 220);
      return;
    }
    toast(e.message);
  } finally {
    clearTimeout(busyTimer);
    showBusy(null);
  }
}

function renderReader() {
  const d = readerData, meta = d.meta;
  const stale = !!(meta.status === 'generating' && d.stale);
  $('rd_title').textContent = meta.title || d.name;
  document.title = (meta.title || d.name) + ' · 小说生成器';
  const typeName = { original: '原创', continuation: '续写', fanfic: '同人' };
  $('rd_type').textContent = typeName[meta.type] || meta.type;
  const st = $('rd_status');
  st.className = 'status ' + (meta.status || 'done');
  st.textContent = stale ? '生成中断' :
    meta.status === 'generating' ? '生成中…' :
    meta.status === 'cancelled' ? '已取消' :
    meta.status === 'error' ? '失败' : '完成';
  if (meta.status === 'error' && meta.error) st.title = meta.error;
  if (stale) st.title = '服务重启导致生成中断，可「从断点继续生成」';
  $('rd_meta').textContent = `共 ${d.chapters.length} 章 · 全本 ${d.words.toLocaleString()} 字 · 更新于 ${meta.updated || ''}` +
    (meta.source_title ? ` · 基于《${meta.source_title}》` : '');
  // 创作档案：书籍元数据里留存的分析总结，可随时查看
  const profile = parseStyleProfile(meta.style_profile);
  const rdProfile = $('rd_profile');
  if (profile) {
    rdProfile.style.display = 'block';
    renderStyleProfile(profile, $('rd_profile_body'));
  } else {
    rdProfile.style.display = 'none';
  }
  // 章节下拉：桌面工具条与「更多」抽屉两处同源
  const optsHtml = d.chapters.map((c, i) => `<option value="${i}">${i + 1}. ${escapeHtml(chapterRealTitle(i))}</option>`).join('');
  ['rd_chapter_sel', 'rd_chapter_sel_m'].forEach(id => {
    const sel = $(id);
    if (!sel) return;
    sel.innerHTML = optsHtml;
    sel.value = readerIdx;
    sel.onchange = () => gotoChapter(parseInt(sel.value));
  });
  // 断点续跑：error / cancelled / 生成中断（stale）均可恢复
  const canResume = meta.job_payload && (meta.status === 'error' || meta.status === 'cancelled' || (meta.status === 'generating' && stale));
  ['rd_resume', 'rd_resume_m'].forEach(id => { const el = $(id); if (el) el.style.display = canResume ? '' : 'none'; });
  applyReaderSettings();
  renderChapter();
  renderToc($('rd_toc_filter').value);
  updateReadingProgress();
}

function chapterFolio(i) {
  const title = (readerData && readerData.chapters[i] && readerData.chapters[i].title) || '';
  const m = title.match(/第\s*(\d+)\s*(?:章|回|节|话|卷)/);
  const n = m ? parseInt(m[1]) : i + 1;
  return String(n).padStart(2, '0');
}

// 有些书的真实标题在正文首行（`## 第一章 …` 或 `第1章 …`），而元数据里的标题只是光秃秃的「第1章」。
// 这种情况把首行提升为标题，免得目录和正文各显示一半。
function chapterRealTitle(i) {
  const c = readerData && readerData.chapters[i];
  if (!c) return '';
  const base = (c.title || '').trim();
  if (base && !/^第\s*\d+\s*[章回节话卷]?$/.test(base)) return base;
  const first = (c.content || '').replace(/^[\s\u3000]+/, '').split('\n')[0].trim();
  const h = first.match(/^#{1,6}\s+(.+?)\s*$/);
  const cand = (h ? h[1] : first).trim();
  if (cand && cand.length <= 60 && /^第\s*\d+\s*[章回节话卷]/.test(cand)) return cand;
  if (h && h[1].trim()) return h[1].trim();
  return base || ('第 ' + (i + 1) + ' 章');
}

// 首行与标题重复时从正文里去掉，避免「第1章」下面又出现一遍同样的一行
function stripLeadingTitle(text, title) {
  const lines = String(text || '').replace(/\r\n?/g, '\n').split('\n');
  let i = 0;
  while (i < lines.length && !lines[i].trim()) i++;
  if (i >= lines.length) return lines.join('\n');
  const first = lines[i].trim();
  const h = first.match(/^#{1,6}\s+(.+?)\s*$/);
  if ((h ? h[1] : first).trim() === title) lines.splice(i, 1);
  return lines.join('\n');
}

// 正文 -> HTML。本工具的规则是「空行与单换行都算分段」，但这些书多数按 ~45 字硬换行，
// 所以用中文排版的常规还原法：上一行以句末标点结尾才另起一段，否则当硬换行接回去。
const RD_SENT_END = /[。！？…”』」）\)\?!]$/;
function renderChapterBody(text) {
  const lines = String(text || '').replace(/\r\n?/g, '\n').split('\n');
  const out = [];
  let buf = '';
  const flush = () => { if (buf) { out.push('<p>' + escapeHtml(buf) + '</p>'); buf = ''; } };
  for (const raw of lines) {
    const line = raw.replace(/\s+$/, '');
    if (!line.trim()) { flush(); continue; }
    const h = line.match(/^(#{1,6})\s+(.*)$/);
    if (h) { flush(); out.push('<h4 class="rd-h">' + escapeHtml(h[2].trim()) + '</h4>'); continue; }
    if (/^\s{0,3}(-{3,}|\*{3,}|_{3,})\s*$/.test(line)) { flush(); out.push('<div class="rd-hr">· · ·</div>'); continue; }
    const q = line.match(/^>\s?(.*)$/);
    if (q) { flush(); out.push('<p class="rd-quote">' + escapeHtml(q[1].trim()) + '</p>'); continue; }
    if (!buf) buf = line;
    else if (RD_SENT_END.test(buf)) { flush(); buf = line; }
    else buf += line;                       // 中文硬换行：直接接上，不加空格
  }
  flush();
  return out.join('') || '<p>（本章暂无正文）</p>';
}

function renderChapter() {
  const d = readerData;
  if (!d.chapters.length) { $('rd_content').innerHTML = '<p>（本章暂无正文）</p>'; return; }
  const c = d.chapters[readerIdx];
  const hasContent = c && typeof c.content === 'string';
  const words = hasContent ? (c.words || c.content.replace(/\s/g, '').length) : (c ? (c.words || 0) : 0);
  const last = readerIdx >= d.chapters.length - 1;
  const title = chapterRealTitle(readerIdx);
  $('rd_words').textContent = hasContent ? `本章 ${words.toLocaleString()} 字` : (words ? `本章约 ${words.toLocaleString()} 字` : '加载中…');
  const sub = $('rd_top_sub');
  if (sub) sub.textContent = `第 ${readerIdx + 1}/${d.chapters.length} 章 · ${hasContent ? `本章 ${words.toLocaleString()} 字` : '加载中…'}`;

  const bodyHtml = !hasContent ? `
    <div class="chapter-skeleton" aria-busy="true">
      <div class="sk-line" style="width: 82%;"></div>
      <div class="sk-line" style="width: 96%;"></div>
      <div class="sk-line" style="width: 90%;"></div>
      <div class="sk-line" style="width: 76%;"></div>
      <div class="sk-line" style="width: 88%; margin-top: 24px;"></div>
      <div class="sk-line" style="width: 94%;"></div>
      <div class="sk-line" style="width: 65%;"></div>
    </div>` : `<div class="chapter-body">${renderChapterBody(stripLeadingTitle(c.content, title))}</div>`;

  $('rd_content').innerHTML =
    `<div class="chapter-folio">${chapterFolio(readerIdx)}</div>` +
    `<div class="chapter-flow">` +
      `<h3 class="chapter-title">${escapeHtml(title)}</h3>` +
      bodyHtml +
    `</div>` +
    `<div class="chapter-end">` +
      `<button class="rd-btn" id="rd_prev_bottom"${readerIdx === 0 ? ' disabled' : ''}>上一章</button>` +
      `<button class="rd-btn" id="rd_next_bottom"${last ? ' disabled' : ''}>下一章</button>` +
      `<span class="grow"></span>` +
      `<span class="mini" style="color:var(--rd-muted)">第 ${readerIdx + 1} / ${d.chapters.length} 章 · ${hasContent ? `本章 ${words.toLocaleString()} 字` : '加载中…'}</span>` +
    `</div>`;

  if ($('rd_prev_bottom')) $('rd_prev_bottom').onclick = () => gotoChapter(readerIdx - 1);
  if ($('rd_next_bottom')) $('rd_next_bottom').onclick = () => gotoChapter(readerIdx + 1);
  ['rd_chapter_sel', 'rd_chapter_sel_m'].forEach(id => { const el = $(id); if (el) el.value = readerIdx; });
  // 桌面工具条上的上下章按钮：到边界时置灰
  const pd = $('rd_prev_d'), nd = $('rd_next_d');
  if (pd) pd.disabled = readerIdx === 0;
  if (nd) nd.disabled = readerIdx >= d.chapters.length - 1;
  // 原作章节不可删/重写
  const originalCount = parseInt(d.meta.original_count || 0);
  const isOriginal = readerIdx < originalCount || c.title === '原作';
  ['rd_rewrite_m', 'rd_del_chapter_m'].forEach(id => {
    const el = $(id);
    if (el) { el.disabled = isOriginal; el.style.opacity = isOriginal ? '.35' : '1'; }
  });
  const tip = $('rd_chapter_tip');
  if (tip) tip.textContent = isOriginal ? '原作章节不可重写 / 删除' : '';
  saveReaderPos();
}

// 切章统一入口：渲染 + 目录高亮 + 回顶 + 进度 + 写回 URL（供目录 / 上下章 / 键盘 / 章末导航共用）
async function gotoChapter(i, scroll) {
  const d = readerData;
  if (!d || i < 0 || i >= d.chapters.length) return;
  if (isEditingChapter) {
    if (isEditDirty() && !confirm('当前章节有未保存的修改，切换将放弃修改，确定？')) return;
    isEditingChapter = false;
    resetEditButtons();
  }
  const changed = i !== readerIdx;
  readerIdx = i;
  const currentReqIdx = i;
  renderChapter();
  renderToc($('rd_toc_filter').value);
  if (scroll !== false) scrollToReaderTop();
  updateReadingProgress();
  syncReaderHash(d.name, i, true);
  if (changed && !isWide()) setTocOpen(false);

  const c = d.chapters[i];
  if (!c || typeof c.content !== 'string') {
    try {
      await ensureChapterContent(d.name, i);
      if (readerData && readerData.name === d.name && readerIdx === currentReqIdx) {
        renderChapter();
        updateReadingProgress();
      }
    } catch (e) {
      if (readerData && readerData.name === d.name && readerIdx === currentReqIdx) {
        const el = $('rd_content');
        if (el) el.innerHTML = `<div class="chapter-flow" style="padding:48px 0;text-align:center;"><p style="color:#ef4444;font-size:14px;margin-bottom:12px;">本章加载失败：${escapeHtml(e.message)}</p><button class="rd-btn" onclick="gotoChapter(${i})">重新加载</button></div>`;
      }
    }
  }
  prefetchAdjacentChapters(d.name, i);
}

function scrollToReaderTop() {
  window.scrollTo(0, 0);
}

// ---- 阅读器在线就地编辑 (Inline Edit) ----
let isEditingChapter = false;
let editingChapterInitialText = '';
let editingChapterInitialTitle = '';

function isEditDirty() {
  if (!isEditingChapter) return false;
  const bodyInp = $('rd_edit_body_inp');
  const titleInp = $('rd_edit_title_inp');
  return (bodyInp && bodyInp.value !== editingChapterInitialText) ||
         (titleInp && titleInp.value.trim() !== editingChapterInitialTitle);
}

function toggleChapterEdit() {
  if (isEditingChapter) {
    saveChapterEdit();
  } else {
    enterChapterEdit();
  }
}

async function enterChapterEdit() {
  const d = readerData;
  if (!d || !d.chapters.length) return;
  const c = d.chapters[readerIdx];
  if (!c) return;

  if (typeof c.content !== 'string') {
    showBusy('正在拉取本章正文…');
    try {
      await ensureChapterContent(d.name, readerIdx);
    } catch (e) {
      toast('无法读取本章正文：' + e.message);
      return;
    } finally {
      showBusy(null);
    }
  }

  isEditingChapter = true;
  editingChapterInitialTitle = c.title || chapterRealTitle(readerIdx);
  editingChapterInitialText = c.content || '';

  const rdContent = $('rd_content');
  if (rdContent) rdContent.classList.add('editing');

  const editBtn = $('rd_edit_btn');
  if (editBtn) {
    editBtn.textContent = '💾 保存修改';
    editBtn.classList.remove('ghost');
    editBtn.classList.add('rd-btn-primary');
  }
  const editBtnM = $('rd_edit_m');
  if (editBtnM) editBtnM.textContent = '💾 保存修改';

  const title = editingChapterInitialTitle;
  const rawContent = editingChapterInitialText;
  const words = rawContent.replace(/\s/g, '').length;

  $('rd_content').innerHTML = `
    <div class="rd-edit-container">
      <div class="rd-edit-header">
        <div class="rd-edit-title-wrap">
          <label style="font-size:12px;color:var(--rd-muted);font-weight:600">章节标题</label>
          <input type="text" id="rd_edit_title_inp" class="rd-edit-title-input" value="${escapeHtml(title)}">
        </div>
        <div class="rd-edit-meta">
          <span class="mini" id="rd_edit_words_live" style="color:var(--rd-muted)">当前字数：${words.toLocaleString()} 字</span>
          <div class="rd-edit-actions">
            <button type="button" class="rd-btn rd-btn-primary" id="rd_edit_save_btn">💾 保存修改 (Ctrl+S)</button>
            <button type="button" class="rd-btn ghost" id="rd_edit_cancel_btn">取消</button>
          </div>
        </div>
      </div>
      <textarea id="rd_edit_body_inp" class="rd-edit-body-input" placeholder="输入本章正文…">${escapeHtml(rawContent)}</textarea>
    </div>
  `;

  const bodyInp = $('rd_edit_body_inp');
  const wordsLive = $('rd_edit_words_live');
  let autoSaveTimer = null;
  if (bodyInp) {
    bodyInp.oninput = () => {
      const w = bodyInp.value.replace(/\s/g, '').length;
      if (wordsLive) wordsLive.textContent = '当前字数：' + w.toLocaleString() + ' 字';
      showAutoSaveStatus('saving');
      clearTimeout(autoSaveTimer);
      autoSaveTimer = setTimeout(() => {
        silentAutoSave();
      }, 1500);
    };
    bodyInp.focus();
  }

  const saveBtn = $('rd_edit_save_btn');
  if (saveBtn) saveBtn.onclick = saveChapterEdit;
  const cancelBtn = $('rd_edit_cancel_btn');
  if (cancelBtn) cancelBtn.onclick = cancelChapterEdit;

  toast('已进入编辑模式，可直接修改正文；Ctrl+S 快速保存');
}

async function saveChapterEdit() {
  if (!isEditingChapter || !readerData) return;
  const titleInp = $('rd_edit_title_inp');
  const bodyInp = $('rd_edit_body_inp');
  if (!bodyInp) return;

  const newTitle = titleInp ? titleInp.value.trim() : '';
  const newContent = bodyInp.value;
  const d = readerData;

  showBusy('正在保存本章修改…');
  try {
    const res = await api('/api/novels/' + encodeURIComponent(d.name) + '/chapter/' + readerIdx, 'POST', {
      title: newTitle,
      content: newContent
    });
    if (res && res.ok) {
      d.chapters[readerIdx].title = res.title || newTitle;
      d.chapters[readerIdx].content = res.content || newContent;
      d.chapters[readerIdx].words = res.words;
      if (typeof res.total_words === 'number') d.words = res.total_words;

      isEditingChapter = false;
      resetEditButtons();
      renderReader();
      toast('已保存修改并自动生成快照备份！');
    }
  } catch (e) {
    toast('保存失败：' + e.message);
  } finally {
    showBusy(null);
  }
}


function showAutoSaveStatus(status, text) {
  const el = $('rd_save_status');
  if (!el) return;
  if (status === 'saving') {
    el.className = 'rd-status-indicator saving';
    el.textContent = '💾 正在自动保存…';
  } else if (status === 'saved') {
    el.className = 'rd-status-indicator';
    const now = new Date();
    const timeStr = now.toTimeString().split(' ')[0];
    el.textContent = text || `✅ 已自动保存 (${timeStr})`;
  } else if (status === 'error') {
    el.className = 'rd-status-indicator';
    el.textContent = text || '⚠️ 保存失败';
  } else {
    el.className = 'rd-status-indicator';
    el.textContent = text || '💾 就绪';
  }
}

async function silentAutoSave() {
  if (!isEditingChapter || !readerData) return;
  const bodyInp = $('rd_edit_body_inp');
  const titleInp = $('rd_edit_title_inp');
  if (!bodyInp) return;
  const newContent = bodyInp.value;
  const newTitle = titleInp ? titleInp.value.trim() : '';
  const d = readerData;

  try {
    const res = await api('/api/novels/' + encodeURIComponent(d.name) + '/chapter/' + readerIdx, 'POST', {
      title: newTitle,
      content: newContent
    });
    if (res && res.ok) {
      d.chapters[readerIdx].title = res.title || newTitle;
      d.chapters[readerIdx].content = res.content || newContent;
      d.chapters[readerIdx].words = res.words;
      if (typeof res.total_words === 'number') d.words = res.total_words;
      showAutoSaveStatus('saved');
    }
  } catch (e) {
    showAutoSaveStatus('error', '⚠️ 自动保存出错');
  }
}

function cancelChapterEdit() {
  if (!isEditingChapter) return;
  if (isEditDirty() && !confirm('有未保存的修改，确定放弃？')) return;
  isEditingChapter = false;
  resetEditButtons();
  renderChapter();
}

function resetEditButtons() {
  const rdContent = $('rd_content');
  if (rdContent) rdContent.classList.remove('editing');
  const editBtn = $('rd_edit_btn');
  if (editBtn) {
    editBtn.textContent = '✏️ 编辑本章';
    editBtn.classList.remove('rd-btn-primary');
    editBtn.classList.add('ghost');
  }
  const editBtnM = $('rd_edit_m');
  if (editBtnM) editBtnM.textContent = '✏️ 编辑本章';
}

// 阅读进度：顶部进度线 = 全书进度（含当前章内比例），底栏显示章与百分比
function updateReadingProgress() {
  const d = readerData;
  if (!d) return;
  const doc = document.documentElement;
  const max = doc.scrollHeight - window.innerHeight;
  const inChapter = max > 40 ? Math.min(1, Math.max(0, window.scrollY / max)) : 0;
  const total = Math.max(1, d.chapters.length);
  const overall = Math.min(1, (readerIdx + inChapter) / total);
  const fill = $('rd_progress_fill');
  if (fill) fill.style.transform = 'scaleX(' + overall.toFixed(4) + ')';
  const pos = $('rd_pos');
  if (pos) pos.textContent = `第 ${readerIdx + 1}/${total} 章 · 全书 ${Math.round(overall * 100)}%`;
}
let rdProgressRaf = null, rdSaveTimer = null;
function readerActive() { return $('view-reader').classList.contains('active'); }
window.addEventListener('scroll', () => {
  if (rdProgressRaf) return;
  rdProgressRaf = requestAnimationFrame(() => {
    rdProgressRaf = null;
    if (readerActive()) updateReadingProgress();
  });
  clearTimeout(rdSaveTimer);
  rdSaveTimer = setTimeout(() => { if (readerActive()) saveReaderPos(); }, 400);
}, { passive: true });
window.addEventListener('resize', () => {
  if (readerActive()) { updateReadingProgress(); setTocOpen(isWide());
    const astPanel = $('rd_assistant');
    const astToggle = $('rd_assistant_toggle');
    if (astPanel) {
      if (isWide()) {
        astPanel.classList.remove('collapsed');
        if (astToggle) astToggle.classList.add('active');
      } else {
        astPanel.classList.add('collapsed');
        if (astToggle) astToggle.classList.remove('active');
      }
    }
    syncStudioBible();
    if (typeof loadProviderSelectsInto === 'function' && $('ast_ct_provider')) {
      loadProviderSelectsInto('ast_ct_provider', (readerData.meta && readerData.meta.provider_id) || undefined);
    } }
}, { passive: true });

// ---- 目录（过滤 + 全文搜索）----
function renderToc(filterText) {
  const d = readerData;
  if (!d) return;
  const list = $('rd_toc_list');
  if (!list) return;
  const q = (filterText || '').trim();
  if (tocMode === 'search') return;

  const volumes = {};
  d.chapters.forEach((c, i) => {
    const vol = (c.volume || '正文').trim();
    if (!volumes[vol]) volumes[vol] = [];
    volumes[vol].push({ ch: c, idx: i });
  });

  const volNames = Object.keys(volumes);
  let html = '';

  volNames.forEach(volName => {
    const items = volumes[volName];
    const filteredItems = q ? items.filter(it => (chapterRealTitle(it.idx) || '').includes(q)) : items;
    if (filteredItems.length === 0) return;

    if (volNames.length > 1 || volName !== '正文') {
      html += `<div class="toc-vol-header"><span class="toc-vol-title">📖 ${escapeHtml(volName)}</span><span class="toc-vol-count">${items.length} 章</span></div>`;
    }

    filteredItems.forEach(({ ch: c, idx: i }) => {
      const words = typeof c.words === 'number' ? c.words : (c.content ? c.content.replace(/\s/g, '').length : 0);
      html += `
        <div class="toc-item ${i === readerIdx ? 'active' : ''}">
          <button type="button" class="toc-title-btn" data-i="${i}" style="background:none;border:none;padding:0;text-align:left;flex:1;cursor:pointer;display:flex;align-items:center;min-width:0;color:inherit;">
            <span class="num" style="margin-right:6px;font-size:11px;color:var(--muted);">${chapterFolio(i)}</span>
            <span class="t" style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:12px;">${escapeHtml(chapterRealTitle(i))}</span>
          </button>
          <div class="toc-reorder-btns">
            <button type="button" class="toc-reorder-btn" data-act="up" data-idx="${i}" title="上移">▲</button>
            <button type="button" class="toc-reorder-btn" data-act="down" data-idx="${i}" title="下移">▼</button>
          </div>
          <span class="mini" style="font-size:10px;color:var(--muted);margin-left:4px;">${words.toLocaleString()}字</span>
        </div>`;
    });
  });

  list.innerHTML = html || '<p class="mini" style="padding:12px">无匹配章节</p>';

  list.querySelectorAll('.toc-title-btn').forEach(el => {
    el.onclick = () => gotoChapter(parseInt(el.dataset.i, 10));
  });

  list.querySelectorAll('.toc-reorder-btn').forEach(btn => {
    btn.onclick = async (e) => {
      e.stopPropagation();
      const act = btn.dataset.act;
      const fromIdx = parseInt(btn.dataset.idx, 10);
      const toIdx = act === 'up' ? fromIdx - 1 : fromIdx + 1;
      if (toIdx < 0 || toIdx >= d.chapters.length) return;
      await reorderChapterItem(fromIdx, toIdx);
    };
  });

  const act = list.querySelector('.toc-item.active');
  if (act && !isWide() && $('rd_toc').classList.contains('open')) act.scrollIntoView({ block: 'center' });
}

async function reorderChapterItem(fromIdx, toIdx) {
  const d = readerData;
  if (!d || !d.chapters) return;
  const item = d.chapters.splice(fromIdx, 1)[0];
  d.chapters.splice(toIdx, 0, item);

  if (readerIdx === fromIdx) {
    readerIdx = toIdx;
  } else if (fromIdx < readerIdx && toIdx >= readerIdx) {
    readerIdx--;
  } else if (fromIdx > readerIdx && toIdx <= readerIdx) {
    readerIdx++;
  }

  renderToc($('rd_toc_filter') ? $('rd_toc_filter').value : '');
  renderChapter();

  try {
    const order = d.chapters.map((c, i) => ({
      index: i,
      volume: c.volume || '正文',
      title: c.title
    }));
    await api('/api/novels/' + encodeURIComponent(d.name) + '/reorder-chapters', 'POST', { order });
    toast('已调整章节顺序');
  } catch (e) {
    toast('保存章节顺序失败：' + e.message);
  }
}

async function searchNovel(q) {
  const d = readerData;
  if (!d || !q) return;
  tocMode = 'search';
  const list = $('rd_toc_list');
  list.innerHTML = '<p class="mini" style="padding:12px">搜索中…</p>';
  try {
    const res = await api('/api/novels/' + encodeURIComponent(d.name) + '/search?q=' + encodeURIComponent(q));
    const rs = res.results || [];
    if (!rs.length) { list.innerHTML = '<p class="mini" style="padding:12px">未找到「' + escapeHtml(q) + '」</p>'; return; }
    list.innerHTML = rs.map(r => `
      <button type="button" class="toc-hit" data-i="${r.index}">
        <span class="t">第 ${r.index + 1} 章 ${escapeHtml(chapterRealTitle(r.index) || r.title)}</span>
        <span class="s">${escapeHtml(r.snippet)}</span>
      </button>`).join('');
    list.querySelectorAll('.toc-hit').forEach(el => {
      el.onclick = () => {
        tocMode = 'toc';
        $('rd_toc_filter').value = '';
        renderToc('');
        gotoChapter(parseInt(el.dataset.i));
      };
    });
  } catch (e) {
    list.innerHTML = '<p class="mini" style="padding:12px">搜索失败：' + escapeHtml(e.message) + '</p>';
    tocMode = 'toc';
  }
}
on('rd_toc_filter', 'input', () => {
  tocMode = 'toc';
  renderToc($('rd_toc_filter').value);
});
on('rd_toc_filter', 'keydown', e => {
  if (e.key === 'Enter') { e.preventDefault(); const q = $('rd_toc_filter') ? $('rd_toc_filter').value.trim() : ''; if (q) searchNovel(q); }
});
on('rd_toc_search', () => { const q = $('rd_toc_filter') ? $('rd_toc_filter').value.trim() : ''; if (q) searchNovel(q); });
on('rd_toc_close', () => setTocOpen(false));

// ---- 手机手势：点左侧上一章 / 点右侧下一章 / 点中间收起工具栏；左右滑动翻章 ----
let rdSwipedAt = 0;
(function readerGestures() {
  const surface = document.querySelector('#view-reader .reader-surface');
  if (!surface) return;
  let t0 = null;
  const INTERACTIVE = 'a,button,input,select,textarea,summary,label,.toc-item,.toc-hit,.toc-panel,.rd-sheet,.rd-bar,.rd-foot';
  surface.addEventListener('click', e => {
    if (!readerData || isWide()) return;
    if (Date.now() - rdSwipedAt < 400) return;                 // 刚滑动过，别把滑动当点击
    if (e.target.closest(INTERACTIVE)) return;
    const sel = window.getSelection();
    if (sel && String(sel).length > 0) return;                 // 正在选字，不翻章
    if (document.body.classList.contains('rd-immersive')) {     // 沉浸态下轻点先唤出工具栏
      document.body.classList.remove('rd-immersive');
      return;
    }
    const w = window.innerWidth, x = e.clientX;
    if (x < w * 0.25) { if (readerIdx > 0) gotoChapter(readerIdx - 1); else toast('已经是第一章'); }
    else if (x > w * 0.75) {
      if (readerIdx < readerData.chapters.length - 1) gotoChapter(readerIdx + 1);
      else toast('已经是最后一章');
    } else {
      document.body.classList.toggle('rd-immersive');
    }
  });
  surface.addEventListener('touchstart', e => {
    t0 = e.touches.length === 1 ? { x: e.touches[0].clientX, y: e.touches[0].clientY } : null;
  }, { passive: true });
  surface.addEventListener('touchend', e => {
    if (!t0 || !readerData || isWide()) { t0 = null; return; }
    const t = e.changedTouches[0];
    const dx = t.clientX - t0.x, dy = t.clientY - t0.y;
    t0 = null;
    if (Math.abs(dx) < 60 || Math.abs(dx) < Math.abs(dy) * 1.5) return;
    rdSwipedAt = Date.now();
    if (dx < 0) {
      if (readerIdx < readerData.chapters.length - 1) gotoChapter(readerIdx + 1);
      else toast('已经是最后一章');
    } else {
      if (readerIdx > 0) gotoChapter(readerIdx - 1);
      else toast('已经是第一章');
    }
  }, { passive: true });
})();

// ---- 键盘（桌面）：← → / J K 翻章，空格翻页，T 目录，E 编辑，Esc 退出沉浸 ----
document.addEventListener('keydown', e => {
  if (isEditingChapter) {
    if ((e.ctrlKey || e.metaKey) && (e.key === 's' || e.key === 'S')) {
      e.preventDefault();
      saveChapterEdit();
      return;
    }
    if (e.key === 'Escape') {
      e.preventDefault();
      cancelChapterEdit();
      return;
    }
  }
  if (!readerActive() || $('round_modal').classList.contains('show') || !readerData) return;
  const tag = (e.target.tagName || '').toLowerCase();
  if (tag === 'input' || tag === 'textarea' || tag === 'select') return;
  const last = readerData.chapters.length - 1;
  if (e.key === 'e' || e.key === 'E') {
    e.preventDefault();
    toggleChapterEdit();
    return;
  }
  if (e.key === 'ArrowLeft' || e.key === 'k' || e.key === 'K') {
    if (readerIdx > 0) { e.preventDefault(); gotoChapter(readerIdx - 1); }
  } else if (e.key === 'ArrowRight' || e.key === 'j' || e.key === 'J') {
    if (readerIdx < last) { e.preventDefault(); gotoChapter(readerIdx + 1); }
  } else if (e.key === ' ') {
    e.preventDefault();
    window.scrollBy({ top: window.innerHeight * (e.shiftKey ? -0.9 : 0.9), behavior: 'smooth' });
  } else if (e.key === 't' || e.key === 'T') {
    e.preventDefault(); setTocOpen(!tocVisible());
  } else if (e.key === 'Escape') {
    if (document.body.classList.contains('rd-immersive')) document.body.classList.remove('rd-immersive');
    else closeReaderPanels();
  }
});


// ==================== 阅读器：一次性接线 ====================
// 这些控件不随书变化，只接一次；回调里现读 readerData，所以不必每次渲染重接。
(function wireReader() {
  const on = (id, fn) => { const el = $(id); if (el) el.onclick = fn; };
  on('rd_back', () => { if (location.hash.indexOf('#read/') === 0) location.hash = 'library'; else switchView('library'); });
  on('rd_toc_toggle', () => setTocOpen(!tocVisible()));
  on('rd_prev', () => gotoChapter(readerIdx - 1));
  on('rd_next', () => gotoChapter(readerIdx + 1));
  on('rd_prev_d', () => gotoChapter(readerIdx - 1));
  on('rd_next_d', () => gotoChapter(readerIdx + 1));
  on('rd_mask', () => closeReaderPanels());
  on('rd_settings_toggle', () => { const open = $('rd_settings').classList.contains('open'); closeReaderPanels(); if (!open) openSheet('rd_settings'); });
  on('rd_more_toggle', () => { const open = $('rd_more').classList.contains('open'); closeReaderPanels(); if (!open) openSheet('rd_more'); });
  on('rd_edit_btn', () => toggleChapterEdit());
  on('rd_edit_m', () => { closeReaderPanels(); enterChapterEdit(); });
  document.querySelectorAll('[data-rd-close]').forEach(b => { b.onclick = () => closeReaderPanels(); });

  const rdContent = $('rd_content');
  if (rdContent) {
    rdContent.addEventListener('dblclick', e => {
      const tag = (e.target.tagName || '').toLowerCase();
      if (tag === 'button' || tag === 'input' || tag === 'textarea' || isEditingChapter) return;
      enterChapterEdit();
    });
  }

  // 断点续跑
  const doResume = async () => {
    if (!readerData) return;
    if (!confirm('从断点继续生成？将从未完成章节重新生成。')) return;
    try {
      const meta = readerData.meta;
      const payload = { resume_novel: readerData.name, provider_id: meta.provider_id || undefined };
      payload.mode = meta.type === 'original' ? 'original' : meta.type;
      const r = await api('/api/generate', 'POST', payload);
      const prefix = meta.type === 'original' ? 'og' : 'ct';
      startPolling(prefix, r.job_id, prefix + '_progress_card', meta.title, meta.type === 'original' ? null : 'round');
      closeReaderPanels();
      toast('已从断点继续生成');
    } catch (e) { toast(e.message); }
  };
  ['rd_resume', 'rd_resume_m'].forEach(id => on(id, doResume));

  // 继续续写
  const doContinue = () => {
    if (!readerData) return;
    if (liveGenNow()) { toast('本书仍在生成中，请稍候'); return; }
    closeReaderPanels();
    openContinueCard(readerData.name, readerData.meta.type === 'fanfic' ? 'fanfic' : 'continuation');
  };
  ['rd_continue', 'rd_continue_m'].forEach(id => on(id, doContinue));

  // 导出
  ['rd_export_txt', 'rd_export_txt_m'].forEach(id => on(id, () => readerData && exportNovel(readerData.name, 'txt')));
  ['rd_export_md', 'rd_export_md_m'].forEach(id => on(id, () => readerData && exportNovel(readerData.name, 'md')));
  ['rd_export_epub', 'rd_export_epub_m'].forEach(id => on(id, () => readerData && exportNovel(readerData.name, 'epub')));

  // 章节操作（原作章节在 renderChapter 里被禁用）
  const doRewrite = () => {
    if (!readerData) return;
    if (liveGenNow()) { toast('本书仍在生成中，请稍候'); return; }
    closeReaderPanels();
    openRewriteCard(readerData.name, readerIdx);
  };
  const doDeleteChapter = async () => {
    if (!readerData) return;
    const c = readerData.chapters[readerIdx];
    if (!c) return;
    const t = chapterRealTitle(readerIdx);
    if (!confirm(`确定删除「${t}」？删除前会自动备份到「设置 → 章节备份」，可恢复。`)) return;
    const name = readerData.name;
    const next = Math.max(0, readerIdx - 1);
    try {
      await api('/api/novels/' + encodeURIComponent(name) + '/chapters/delete', 'POST', { index: readerIdx });
      toast('已删除「' + t + '」（已备份）');
      closeReaderPanels();
      readerData = null;                       // 章节数已变，强制重新拉取
      openReader(name, next);
    } catch (e) { toast(e.message); }
  };
  on('rd_rewrite_m', doRewrite);
  on('rd_del_chapter_m', doDeleteChapter);

  // 阅读设置：字号 / 行距 / 段距 / 页宽 / 字体 / 缩进 / 主题 / 沉浸 / 全屏 / 重置
  const bump = d => { rdSet('size', Math.min(26, Math.max(13, rdGet('size') + d))); applyReaderSettings(); };
  on('rd_font_minus', () => bump(-1));
  on('rd_font_plus', () => bump(1));
  const range = (id, key) => { const el = $(id); if (el) el.oninput = () => { rdSet(key, el.value); applyReaderSettings(); }; };
  range('rd_font_range', 'size'); range('rd_lh_range', 'lh'); range('rd_gap_range', 'gap'); range('rd_measure_range', 'measure');
  document.querySelectorAll('[data-rd-font]').forEach(b => { b.onclick = () => { rdSet('font', b.dataset.rdFont); applyReaderSettings(); }; });
  document.querySelectorAll('[data-rd-indent]').forEach(b => { b.onclick = () => { rdSet('indent', b.dataset.rdIndent); applyReaderSettings(); }; });
  document.querySelectorAll('[data-rd-theme-btn]').forEach(b => { b.onclick = () => { rdSet('theme', b.dataset.rdThemeBtn); applyReaderSettings(); }; });
  on('rd_reset_btn', () => { Object.keys(RD_DEFAULTS).forEach(k => rdSet(k, RD_DEFAULTS[k])); applyReaderSettings(); toast('已恢复默认阅读设置'); });
  on('rd_immersive_btn', () => { document.body.classList.toggle('rd-immersive'); closeReaderPanels(); });
  on('rd_fullscreen_btn', async () => {
    try {
      if (!document.fullscreenElement) await document.documentElement.requestFullscreen();
      else await document.exitFullscreen();
    } catch (err) { toast('当前浏览器不支持全屏（iPhone 上可用「添加到主屏幕」）'); }
  });
  if (!document.fullscreenEnabled) { const b = $('rd_fullscreen_btn'); if (b) b.style.display = 'none'; }
})();

// ==================== 阅读器设定集与重命名 ====================
const doReaderRename = () => {
  if (!readerData) return;
  openRenameModal(readerData.name, readerData.meta.title || readerData.name, (newTitle, newName) => {
    readerData.name = newName;
    readerData.meta.title = newTitle;
    renderReader();
    syncReaderHash(newName, readerIdx, true);
  });
};
on('rd_rename_btn', doReaderRename);
on('rd_rename_btn_m', doReaderRename);

function renderBmCharCards(chars) {
  const box = $('bm_chars');
  if (!chars.length) {
    box.innerHTML = '<p class="mini" style="color:var(--muted);padding:8px 0;">暂无角色档案，点击「+ 添加角色」进行补充</p>';
    return;
  }
  box.innerHTML = chars.map((c, i) => `
    <div class="char-card" data-idx="${i}">
      <div class="char-card-hd">
        <input type="text" class="char-name" value="${escapeHtml(c.name || '')}" placeholder="角色姓名">
        <input type="text" class="char-role" value="${escapeHtml(c.role || '')}" placeholder="身份/定位">
        <button type="button" class="btn-oc-action danger" data-act="del-char" title="删除角色" aria-label="删除角色">×</button>
      </div>
      <div class="char-card-bd">
        <input type="text" class="char-desc" value="${escapeHtml(c.desc || '')}" placeholder="性格特征或外貌…">
        <input type="text" class="char-goal" value="${escapeHtml(c.goal || '')}" placeholder="动机、目标或与主角的关系…">
      </div>
    </div>`).join('');
  box.querySelectorAll('.char-card').forEach(card => {
    const idx = parseInt(card.dataset.idx);
    card.querySelector('[data-act=del-char]').onclick = () => {
      const b = collectBmBible();
      b.characters.splice(idx, 1);
      renderBmCharCards(b.characters);
    };
  });
}

function collectBmBible() {
  const chars = [...$('bm_chars').querySelectorAll('.char-card')].map(card => ({
    name: card.querySelector('.char-name').value.trim(),
    role: card.querySelector('.char-role').value.trim(),
    desc: card.querySelector('.char-desc').value.trim(),
    goal: card.querySelector('.char-goal').value.trim(),
  })).filter(c => c.name || c.role || c.desc);
  return {
    setting: $('bm_setting').value.trim(),
    characters: chars,
    conflict: $('bm_conflict').value.trim(),
    tone: $('bm_tone').value.trim(),
  };
}

on('btn_add_bm_char', () => {
  const b = collectBmBible();
  b.characters.push({ name: '', role: '', desc: '', goal: '' });
  renderBmCharCards(b.characters);
});

async function openReaderBibleModal() {
  if (!readerData) return;
  $('bm_title').textContent = '《' + (readerData.meta.title || readerData.name) + '》设定档案 (Bible)';
  $('bm_status').textContent = '加载中…';
  $('bible_modal').classList.add('show');
  try {
    const res = await api('/api/novels/' + encodeURIComponent(readerData.name) + '/bible');
    const b = (res && res.bible) || {};
    $('bm_setting').value = b.setting || '';
    $('bm_conflict').value = b.conflict || '';
    $('bm_tone').value = b.tone || '';
    renderBmCharCards(b.characters || []);
    $('bm_status').textContent = '';
  } catch (e) {
    $('bm_status').textContent = '加载失败：' + e.message;
  }
}

on('bm_save', async () => {
  if (!readerData) return;
  const b = collectBmBible();
  $('bm_status').textContent = '保存中…';
  try {
    await api('/api/novels/' + encodeURIComponent(readerData.name) + '/bible', 'POST', { bible: b });
    if (readerData.meta) readerData.meta.bible = b;
    $('bm_status').textContent = '已保存！';
    toast('设定档案已保存，后续续写将以此为准');
    setTimeout(() => { $('bible_modal').classList.remove('show'); $('bm_status').textContent = ''; }, 600);
  } catch (e) {
    $('bm_status').textContent = '保存失败：' + e.message;
  }
});

on('bm_close', () => $('bible_modal').classList.remove('show'));
on('bm_cancel', () => $('bible_modal').classList.remove('show'));
on('rd_bible_btn', openReaderBibleModal);
on('rd_bible_btn_m', openReaderBibleModal);

// ==================== P1: 划词 AI 辅助精修 ====================
let activeSelectionSnippet = '';
let activeAssistType = 'expand';
let activeAssistStyle = '幽默风趣';

function hideSelectionToolbar() {
  const tb = $('rd_selection_toolbar');
  if (tb) tb.style.display = 'none';
}

function closeAssistModal() {
  const modal = $('rd_assist_modal');
  if (modal) modal.style.display = 'none';
  const mask = $('rd_mask');
  if (mask) mask.classList.remove('open');
  hideSelectionToolbar();
}

async function runAssist() {
  if (!readerData || !activeSelectionSnippet) return;
  const ch = readerData.chapters && readerData.chapters[readerIdx];
  const fullContent = (ch && ch.content) || '';
  const idx = fullContent.indexOf(activeSelectionSnippet);
  const contextBefore = idx !== -1 ? fullContent.slice(Math.max(0, idx - 800), idx) : '';
  const contextAfter = idx !== -1 ? fullContent.slice(idx + activeSelectionSnippet.length, idx + activeSelectionSnippet.length + 800) : '';

  const payload = {
    selected_text: activeSelectionSnippet,
    instruction_type: activeAssistType,
    style_target: activeAssistStyle,
    custom_instruction: $('rd_assist_custom_input') ? $('rd_assist_custom_input').value.trim() : '',
    context_before: contextBefore,
    context_after: contextAfter,
    provider_id: (readerData.meta && readerData.meta.provider_id) || undefined
  };

  const loading = $('rd_assist_loading');
  const resWrap = $('rd_assist_result_wrap');
  const runBtn = $('rd_assist_run_btn');
  if (loading) loading.style.display = 'flex';
  if (resWrap) resWrap.style.display = 'none';
  if (runBtn) runBtn.disabled = true;

  try {
    const res = await api('/api/novels/' + encodeURIComponent(readerData.name) + '/selection-assist', 'POST', payload);
    if (loading) loading.style.display = 'none';
    if (runBtn) runBtn.disabled = false;
    if (res && res.ok && res.result) {
      if ($('rd_assist_result_text')) $('rd_assist_result_text').value = res.result;
      const diff = res.result.length - activeSelectionSnippet.length;
      if ($('rd_assist_diff')) $('rd_assist_diff').textContent = `原有 ${activeSelectionSnippet.length} 字 → 精修 ${res.result.length} 字 (${diff >= 0 ? '+' : ''}${diff} 字)`;
      if (resWrap) resWrap.style.display = 'flex';
    } else {
      toast('未能生成精修结果');
    }
  } catch (e) {
    if (loading) loading.style.display = 'none';
    if (runBtn) runBtn.disabled = false;
    toast('精修失败：' + e.message);
  }
}

function openAssistModal(defaultType = 'expand') {
  if (!activeSelectionSnippet) {
    const sel = window.getSelection();
    if (sel && !sel.isCollapsed) {
      activeSelectionSnippet = sel.toString().trim();
    }
  }
  hideSelectionToolbar();
  if (!activeSelectionSnippet) return;
  const modal = $('rd_assist_modal');
  if (!modal) return;
  if ($('rd_assist_orig')) $('rd_assist_orig').textContent = activeSelectionSnippet;
  if ($('rd_assist_loading')) $('rd_assist_loading').style.display = 'none';
  if ($('rd_assist_result_wrap')) $('rd_assist_result_wrap').style.display = 'none';
  if ($('rd_assist_result_text')) $('rd_assist_result_text').value = '';

  activeAssistType = defaultType || 'expand';
  const typeChips = $('rd_assist_types');
  if (typeChips) {
    typeChips.querySelectorAll('.rd-chip').forEach(b => {
      b.classList.toggle('active', b.dataset.type === activeAssistType);
    });
  }
  const styleBox = $('rd_assist_style_opts');
  if (styleBox) styleBox.style.display = activeAssistType === 'style' ? 'block' : 'none';
  const customBox = $('rd_assist_custom_wrap');
  if (customBox) {
    customBox.style.display = activeAssistType === 'custom' ? 'block' : 'none';
    if (activeAssistType === 'custom') {
      setTimeout(() => {
        const inp = $('rd_assist_custom_input');
        if (inp) inp.focus();
      }, 50);
    }
  }

  modal.style.display = 'flex';
  const mask = $('rd_mask');
  if (mask) mask.classList.add('open');

  if (activeAssistType === 'expand' || activeAssistType === 'concise') {
    runAssist();
  }
}

function initSelectionAssist() {
  const toolbar = $('rd_selection_toolbar');
  const modal = $('rd_assist_modal');
  if (!toolbar || !modal) return;

  const checkSelection = (e) => {
    if (isEditingChapter) { hideSelectionToolbar(); return; }
    if (e && (toolbar.contains(e.target) || modal.contains(e.target))) return;

    const sel = window.getSelection();
    if (!sel || sel.isCollapsed) {
      hideSelectionToolbar();
      return;
    }
    const text = sel.toString().trim();
    if (text.length < 2 || text.length > 3000) {
      hideSelectionToolbar();
      return;
    }

    const range = sel.rangeCount > 0 ? sel.getRangeAt(0) : null;
    if (!range) { hideSelectionToolbar(); return; }
    const container = range.commonAncestorContainer;
    const bodyEl = container.nodeType === 1 ? container.closest('.chapter-body') : (container.parentElement && container.parentElement.closest('.chapter-body'));
    if (!bodyEl) {
      hideSelectionToolbar();
      return;
    }

    activeSelectionSnippet = text;
    const rect = range.getBoundingClientRect();
    toolbar.style.display = 'flex';
    const topPos = Math.max(10, rect.top - 10);
    const leftPos = Math.min(window.innerWidth - 150, Math.max(150, rect.left + rect.width / 2));
    toolbar.style.top = `${topPos}px`;
    toolbar.style.left = `${leftPos}px`;
  };

  document.addEventListener('mouseup', checkSelection);
  document.addEventListener('touchend', checkSelection);

  toolbar.querySelectorAll('.rd-sel-btn').forEach(btn => {
    btn.onmousedown = (e) => {
      e.preventDefault();
      e.stopPropagation();
    };
    btn.onclick = (e) => {
      e.preventDefault();
      e.stopPropagation();
      openAssistModal(btn.dataset.act);
    };
  });

  on('rd_assist_close', closeAssistModal);

  const typeChips = $('rd_assist_types');
  if (typeChips) {
    typeChips.querySelectorAll('.rd-chip').forEach(btn => {
      btn.onclick = () => {
        activeAssistType = btn.dataset.type;
        typeChips.querySelectorAll('.rd-chip').forEach(b => b.classList.toggle('active', b === btn));
        if ($('rd_assist_style_opts')) $('rd_assist_style_opts').style.display = activeAssistType === 'style' ? 'block' : 'none';
        if ($('rd_assist_custom_wrap')) $('rd_assist_custom_wrap').style.display = activeAssistType === 'custom' ? 'block' : 'none';
        if (activeAssistType === 'custom') {
          if ($('rd_assist_custom_input')) $('rd_assist_custom_input').focus();
        } else if (activeAssistType === 'expand' || activeAssistType === 'concise') {
          runAssist();
        }
      };
    });
  }

  const stylePills = $('rd_assist_style_pills');
  if (stylePills) {
    stylePills.querySelectorAll('.tag-pill').forEach(pill => {
      pill.onclick = () => {
        activeAssistStyle = pill.dataset.style;
        stylePills.querySelectorAll('.tag-pill').forEach(p => p.classList.toggle('active', p === pill));
        runAssist();
      };
    });
  }

  const customInput = $('rd_assist_custom_input');
  if (customInput) {
    customInput.onkeydown = (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        runAssist();
      }
    };
  }

  on('rd_assist_run_btn', runAssist);
  on('rd_assist_retry_btn', runAssist);

  on('rd_assist_copy_btn', () => {
    const val = $('rd_assist_result_text') ? $('rd_assist_result_text').value : '';
    if (!val) return;
    navigator.clipboard.writeText(val).then(() => toast('已复制精修结果到剪贴板'));
  });

  on('rd_assist_apply_btn', async () => {
      if (!readerData || !activeSelectionSnippet) return;
      const newText = $('rd_assist_result_text') ? $('rd_assist_result_text').value.trim() : '';
      if (!newText) { toast('精修文本不能为空'); return; }

      if (isEditingChapter) {
        const inp = $('rd_edit_input');
        if (inp && inp.value.includes(activeSelectionSnippet)) {
          inp.value = inp.value.replace(activeSelectionSnippet, newText);
          updateWordCount(inp.value.replace(/\s/g, '').length);
          closeAssistModal();
          toast('✅ 已在编辑框中替换原句！');
          return;
        }
      }

      const ch = readerData.chapters && readerData.chapters[readerIdx];
      if (!ch) return;

      if (!ch.content.includes(activeSelectionSnippet)) {
        toast('未在正文中找到原句（可能已被修改），请手动复制');
        return;
      }

      const updatedContent = ch.content.replace(activeSelectionSnippet, newText);
      const btn = $('rd_assist_apply_btn');
      btn.disabled = true;
      btn.textContent = '保存中…';

      try {
        const res = await api('/api/novels/' + encodeURIComponent(readerData.name) + '/chapter/' + readerIdx, 'POST', {
          title: ch.title,
          content: updatedContent
        });
        btn.disabled = false;
        btn.textContent = '✅ 替换原句并保存';
        if (res && res.ok) {
          ch.content = res.content || updatedContent;
          ch.words = typeof res.words === 'number' ? res.words : ch.content.replace(/\s/g, '').length;
          if (typeof res.book_words === 'number') readerData.words = res.book_words;
          closeAssistModal();
          renderChapter();
          toast('已就地替换并保存！');
        }
      } catch (e) {
        btn.disabled = false;
        btn.textContent = '✅ 替换原句并保存';
        toast('保存失败：' + e.message);
      }
    });
}
initSelectionAssist();


// ==================== P3: Studio 工作台全能交互 ====================

function initStudioPanels() {
  const tocToggle = $('rd_toc_toggle');
  const tocPanel = $('rd_toc');
  const tocClose = $('rd_toc_close');

  if (tocToggle) {
    tocToggle.onclick = () => {
      if (tocPanel) {
        tocPanel.classList.toggle('collapsed');
        tocToggle.classList.toggle('active', !tocPanel.classList.contains('collapsed'));
      }
    };
  }
  if (tocClose && tocPanel) {
    tocClose.onclick = () => {
      tocPanel.classList.add('collapsed');
      if (tocToggle) tocToggle.classList.remove('active');
    };
  }

  const astToggle = $('rd_assistant_toggle');
  const astPanel = $('rd_assistant');
  const astClose = $('rd_ast_close');

  if (astToggle) {
    astToggle.onclick = () => {
      if (astPanel) {
        astPanel.classList.toggle('collapsed');
        astToggle.classList.toggle('active', !astPanel.classList.contains('collapsed'));
      }
    };
  }
  if (astClose && astPanel) {
    astClose.onclick = () => {
      astPanel.classList.add('collapsed');
      if (astToggle) astToggle.classList.remove('active');
    };
  }

  const tabDirs = $('rd_toc_tab_dirs');
  const tabOutline = $('rd_toc_tab_outline');
  const panelDirs = $('rd_toc_panel_dirs');
  const panelOutline = $('rd_toc_panel_outline');

  if (tabDirs && tabOutline) {
    tabDirs.onclick = () => {
      tabDirs.classList.add('active');
      tabOutline.classList.remove('active');
      if (panelDirs) panelDirs.style.display = 'flex';
      if (panelOutline) panelOutline.style.display = 'none';
    };
    tabOutline.onclick = () => {
      tabOutline.classList.add('active');
      tabDirs.classList.remove('active');
      if (panelDirs) panelDirs.style.display = 'none';
      if (panelOutline) {
        panelOutline.style.display = 'flex';
        renderOutlineMemo();
      }
    };
  }

  const addChBtn = $('rd_toc_add_ch_btn');
  if (addChBtn) {
    addChBtn.onclick = async () => {
      if (!readerData) return;
      const chNum = (readerData.chapters ? readerData.chapters.length : 0) + 1;
      const newTitle = prompt('请输入新章节标题：', `第${chNum}章 `);
      if (!newTitle) return;
      readerData.chapters.push({
        title: newTitle.trim(),
        content: '',
        volume: '正文',
        words: 0
      });
      renderToc();
      gotoChapter(readerData.chapters.length - 1, false);
      enterChapterEdit();
      toast('已新增章节，请开始创作！');
    };
  }

  const addVolBtn = $('rd_toc_add_vol_btn');
  if (addVolBtn) {
    addVolBtn.onclick = async () => {
      if (!readerData) return;
      const volTitle = prompt('请输入新分卷名称（例如：第二卷 龙争虎斗）：');
      if (!volTitle) return;
      if (readerData.chapters && readerData.chapters[readerIdx]) {
        readerData.chapters[readerIdx].volume = volTitle.trim();
        renderToc();
        toast(`已将当前第 ${readerIdx + 1} 章划分至【${volTitle.trim()}】`);
        try {
          const order = readerData.chapters.map((c, i) => ({
            index: i,
            volume: c.volume || '正文',
            title: c.title
          }));
          await api('/api/novels/' + encodeURIComponent(readerData.name) + '/reorder-chapters', 'POST', { order });
        } catch (e) {}
      }
    };
  }

  const astTabs = document.querySelectorAll('.rd-ast-tab');
  astTabs.forEach(tab => {
    tab.onclick = () => {
      astTabs.forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      const targetPanel = tab.dataset.panel;
      document.querySelectorAll('.rd-ast-panel').forEach(p => p.style.display = 'none');
      const panelEl = $('rd_ast_panel_' + targetPanel);
      if (panelEl) panelEl.style.display = 'flex';
      if (targetPanel === 'bible') syncStudioBible();
    };
  });

  const saveBibleBtn = $('btn_save_ast_bible');
  if (saveBibleBtn) {
    saveBibleBtn.onclick = async () => {
      if (!readerData) return;
      const bible = {
        setting: $('ast_bible_setting') ? $('ast_bible_setting').value.trim() : '',
        conflict: $('ast_bible_conflict') ? $('ast_bible_conflict').value.trim() : '',
        tone: $('ast_bible_tone') ? $('ast_bible_tone').value.trim() : '',
        characters: collectStudioBibleChars()
      };
      saveBibleBtn.disabled = true;
      saveBibleBtn.textContent = '保存中…';
      try {
        await api('/api/novels/' + encodeURIComponent(readerData.name) + '/bible', 'POST', { bible });
        readerData.bible = bible;
        toast('设定档案已同步保存！');
      } catch (e) {
        toast('保存设定失败：' + e.message);
      } finally {
        saveBibleBtn.disabled = false;
        saveBibleBtn.textContent = '💾 保存设定';
      }
    };
  }

  const addCharBtn = $('btn_add_ast_char');
  if (addCharBtn) {
    addCharBtn.onclick = () => {
      const name = prompt('角色姓名：');
      if (!name) return;
      const desc = prompt('角色身份、性格与目标：') || '';
      const list = $('ast_bible_chars');
      if (list) {
        const card = document.createElement('div');
        card.className = 'ast-char-card';
        card.innerHTML = `<div class="ast-char-name">${escapeHtml(name)}</div><div class="ast-char-desc">${escapeHtml(desc)}</div>`;
        list.appendChild(card);
      }
    };
  }

  const srPrevBtn = $('sr_preview_btn');
  const srExecBtn = $('sr_execute_btn');
  if (srPrevBtn) srPrevBtn.onclick = () => runSearchReplace(true);
  if (srExecBtn) srExecBtn.onclick = () => runSearchReplace(false);

  const astStartCtBtn = $('btn_ast_start_continue');
  if (astStartCtBtn) {
    astStartCtBtn.onclick = () => {
      triggerQuickContinue();
    };
  }

  const triggerVarBtn = $('btn_ast_trigger_variants');
  const retryVarBtn = $('btn_ast_variants_retry');
  const variantsBox = $('ast_variants_box');
  const variantsCards = $('ast_variants_cards');

  const doVariants = async () => {
    if (!readerData) return;
    const instruction = $('ast_ct_instruction') ? $('ast_ct_instruction').value.trim() : '';
    const ch = readerData.chapters && readerData.chapters[readerIdx];
    const prevText = (ch && ch.content) ? ch.content.slice(-2000) : '';

    if (triggerVarBtn) {
      triggerVarBtn.disabled = true;
      triggerVarBtn.textContent = '正在推演走向小样…';
    }
    if (variantsBox) variantsBox.style.display = 'block';
    if (variantsCards) variantsCards.innerHTML = '<div class="spinner" style="margin:12px auto;"></div><div style="font-size:12px;text-align:center;color:var(--muted)">AI 正在构思两种不同的剧情走向小样…</div>';

    try {
      const res = await api('/api/generate-variants', 'POST', {
        title: readerData.name,
        context: prevText,
        instruction: instruction,
        provider_id: $('ast_ct_provider') ? $('ast_ct_provider').value : undefined
      });
      if (res && res.variants && res.variants.length) {
        if (variantsCards) {
          variantsCards.innerHTML = '';
          res.variants.forEach((v, vIdx) => {
            const card = document.createElement('div');
            card.className = 'variant-card';
            card.innerHTML = `
              <div class="variant-head" style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
                <span class="variant-tag" style="font-weight:700;color:var(--accent);">走向 ${vIdx === 0 ? 'A' : 'B'}</span>
                <span class="variant-label" style="font-size:12px;font-weight:600;">${escapeHtml(v.label || '剧情分支')}</span>
              </div>
              <div class="variant-body" style="font-size:12px;line-height:1.5;color:var(--ink);margin-bottom:8px;">${escapeHtml(v.content || v.sample || '')}</div>
              <button type="button" class="primary mini-btn variant-choose-btn" style="width:100%;">选用此走向继续写作</button>
            `;
            card.querySelector('.variant-choose-btn').onclick = () => {
              if ($('ast_ct_instruction')) {
                $('ast_ct_instruction').value = (instruction ? instruction + '\n' : '') + `【选用剧情走向】：${v.label}。${v.content || v.sample || ''}`;
              }
              variantsCards.querySelectorAll('.variant-card').forEach(c => c.classList.remove('selected'));
              card.classList.add('selected');
              toast(`已选用走向 ${vIdx === 0 ? 'A' : 'B'} 作为后续创作指引！`);
            };
            variantsCards.appendChild(card);
          });
        }
      } else {
        if (variantsCards) variantsCards.innerHTML = '<div style="font-size:12px;color:var(--muted);text-align:center;padding:10px;">未能生成有效分支小样，请重试</div>';
      }
    } catch (e) {
      if (variantsCards) variantsCards.innerHTML = `<div style="font-size:12px;color:var(--accent);text-align:center;padding:10px;">生成失败：${escapeHtml(e.message)}</div>`;
    } finally {
      if (triggerVarBtn) {
        triggerVarBtn.disabled = false;
        triggerVarBtn.textContent = '🎲 2 选 1 分支小样';
      }
    }
  };

  if (triggerVarBtn) triggerVarBtn.onclick = doVariants;
  if (retryVarBtn) retryVarBtn.onclick = doVariants;

  const histBtn = $('rd_history_btn');
  if (histBtn) histBtn.onclick = openChapterHistoryModal;

  const srToolbarBtn = $('rd_search_replace_btn');
  if (srToolbarBtn) {
    srToolbarBtn.onclick = () => {
      if (astPanel && astPanel.classList.contains('collapsed')) {
        astPanel.classList.remove('collapsed');
        if (astToggle) astToggle.classList.add('active');
      }
      const searchTab = $('rd_ast_tab_search');
      if (searchTab) searchTab.click();
      if ($('sr_find_input')) $('sr_find_input').focus();
    };
  }

  const shortcutsBtn = $('rd_shortcuts_btn');
  if (shortcutsBtn) {
    shortcutsBtn.onclick = () => {
      const modal = $('shortcuts_modal');
      if (modal) modal.style.display = 'flex';
    };
  }
  const smClose = $('sm_close');
  const smDone = $('sm_done_btn');
  if (smClose) smClose.onclick = () => { $('shortcuts_modal').style.display = 'none'; };
  if (smDone) smDone.onclick = () => { $('shortcuts_modal').style.display = 'none'; };
}

function renderOutlineMemo() {
  const container = $('rd_outline_memo_content');
  if (!container || !readerData) return;
  const d = readerData;
  const meta = d.meta || {};
  const bible = d.bible || meta.bible || {};

  container.innerHTML = `
    <div class="memo-card">
      <div class="memo-card-title">📖 作品设定</div>
      <p style="margin:0;color:var(--ink);">${escapeHtml(meta.setting || bible.setting || '暂无设定描述')}</p>
    </div>
    <div class="memo-card">
      <div class="memo-card-title">⚔️ 核心冲突</div>
      <p style="margin:0;color:var(--ink);">${escapeHtml(meta.storyline || bible.conflict || '暂无主线冲突')}</p>
    </div>
    <div class="memo-card">
      <div class="memo-card-title">👥 主要角色</div>
      <div style="display:flex;flex-wrap:wrap;gap:4px;margin-top:4px;">
        ${(bible.characters || []).map(c => `<span class="tag-pill" style="font-size:11px;">${escapeHtml(typeof c === 'string' ? c : c.name || '')}</span>`).join('') || '<span style="color:var(--muted)">暂无角色档案</span>'}
      </div>
    </div>
  `;
}

function syncStudioBible() {
  if (!readerData) return;
  const bible = readerData.bible || (readerData.meta && readerData.meta.bible) || {};
  if ($('ast_bible_setting')) $('ast_bible_setting').value = bible.setting || (readerData.meta && readerData.meta.setting) || '';
  if ($('ast_bible_conflict')) $('ast_bible_conflict').value = bible.conflict || (readerData.meta && readerData.meta.storyline) || '';
  if ($('ast_bible_tone')) $('ast_bible_tone').value = bible.tone || (readerData.meta && readerData.meta.style) || '';

  const list = $('ast_bible_chars');
  if (list) {
    list.innerHTML = '';
    const chars = bible.characters || [];
    chars.forEach(c => {
      const card = document.createElement('div');
      card.className = 'ast-char-card';
      const name = typeof c === 'string' ? c.split('：')[0] : (c.name || '角色');
      const desc = typeof c === 'string' ? (c.split('：')[1] || '') : (c.identity || c.personality || '');
      card.innerHTML = `<div class="ast-char-name">${escapeHtml(name)}</div><div class="ast-char-desc">${escapeHtml(desc)}</div>`;
      list.appendChild(card);
    });
  }
}

function collectStudioBibleChars() {
  const list = $('ast_bible_chars');
  if (!list) return [];
  const cards = list.querySelectorAll('.ast-char-card');
  const res = [];
  cards.forEach(card => {
    const nameEl = card.querySelector('.ast-char-name');
    const descEl = card.querySelector('.ast-char-desc');
    if (nameEl) {
      res.push({
        name: nameEl.textContent.trim(),
        identity: descEl ? descEl.textContent.trim() : ''
      });
    }
  });
  return res;
}

async function runSearchReplace(previewOnly = true) {
  if (!readerData) return;
  const findText = $('sr_find_input') ? $('sr_find_input').value.trim() : '';
  const replaceText = $('sr_replace_input') ? $('sr_replace_input').value : '';
  const caseSensitive = $('sr_case_sensitive') ? $('sr_case_sensitive').checked : false;
  const isRegex = $('sr_regex') ? $('sr_regex').checked : false;
  const statusEl = $('sr_status');
  const resultsEl = $('sr_results_list');

  if (!findText) {
    toast('请输入查找内容');
    return;
  }

  if (!previewOnly && !confirm(`确定要在全书各章节中将【${findText}】全部替换为【${replaceText}】吗？\n（系统将自动创建快照备份）`)) {
    return;
  }

  if (statusEl) statusEl.textContent = '正在检索全书章节…';
  try {
    const res = await api('/api/novels/' + encodeURIComponent(readerData.name) + '/search-replace', 'POST', {
      find: findText,
      replace: replaceText,
      case_sensitive: caseSensitive,
      regex: isRegex,
      preview_only: previewOnly
    });

    if (res && res.ok) {
      if (statusEl) {
        statusEl.textContent = previewOnly
          ? `共发现 ${res.total_matches} 处匹配（分布在 ${res.modified_chapters} 个章节中）`
          : `✅ 全书替换完成！共修改 ${res.modified_chapters} 章，替换 ${res.total_matches} 处`;
      }
      if (resultsEl) {
        resultsEl.innerHTML = '';
        (res.results || []).forEach(r => {
          const item = document.createElement('div');
          item.className = 'sr-result-item';
          item.innerHTML = `
            <div class="sr-result-head">
              <span>${escapeHtml(r.chapter_title)}</span>
              <span style="color:var(--accent);">${r.matches_count} 处</span>
            </div>
            ${(r.snippets || []).map(s => `<div class="sr-match-snippet">…${escapeHtml(s)}…</div>`).join('')}
          `;
          item.onclick = () => gotoChapter(r.chapter_index, false);
          resultsEl.appendChild(item);
        });
      }
      if (!previewOnly) {
        toast(`全书替换成功！共替换 ${res.total_matches} 处`);
        await ensureChapterContent(readerData.name, readerIdx);
        renderChapter();
      }
    }
  } catch (e) {
    if (statusEl) statusEl.textContent = '操作失败：' + e.message;
    toast('替换请求失败：' + e.message);
  }
}

async function openChapterHistoryModal() {
  if (!readerData) return;
  const modal = $('history_modal');
  const listEl = $('hm_snapshots_list');
  if (!modal || !listEl) return;

  listEl.innerHTML = '<p class="mini">正在拉取本章历史快照记录…</p>';
  modal.style.display = 'flex';

  try {
    const res = await api('/api/novels/' + encodeURIComponent(readerData.name) + '/chapters/' + readerIdx + '/history', 'GET');
    if (res && res.ok && res.snapshots) {
      if (!res.snapshots.length) {
        listEl.innerHTML = '<p class="mini" style="color:var(--muted);padding:14px 0;">本章尚无历史快照备份。在您每次编辑保存、AI 精修或重写时，系统将自动留存快照。</p>';
        return;
      }
      listEl.innerHTML = '';
      res.snapshots.forEach(s => {
        const card = document.createElement('div');
        card.className = 'history-snapshot-card';
        card.innerHTML = `
          <div class="snap-head">
            <span class="snap-title">${escapeHtml(s.title || '章节快照')} (${s.words} 字)</span>
            <span class="snap-time">${escapeHtml(s.ts || '')}</span>
          </div>
          <div class="snap-preview">“${escapeHtml(s.preview || '')}”</div>
          <div style="display:flex;justify-content:flex-end;gap:8px;">
            <button type="button" class="primary mini-btn snap-restore-btn" data-id="${escapeHtml(s.id)}">⏪ 一键还原至此快照</button>
          </div>
        `;
        card.querySelector('.snap-restore-btn').onclick = async () => {
          if (!confirm(`确定要将第 ${readerIdx + 1} 章还原到 ${s.ts} 的快照吗？当前内容会自动生成新备份。`)) return;
          try {
            const restoreRes = await api('/api/novels/' + encodeURIComponent(readerData.name) + '/chapters/' + readerIdx + '/restore-snapshot', 'POST', {
              snapshot_id: s.id
            });
            if (restoreRes && restoreRes.ok) {
              readerData.chapters[readerIdx].content = restoreRes.content;
              readerData.chapters[readerIdx].words = restoreRes.words;
              modal.style.display = 'none';
              renderChapter();
              toast('已成功还原至历史快照！');
            }
          } catch (err) {
            toast('恢复快照失败：' + err.message);
          }
        };
        listEl.appendChild(card);
      });
    }
  } catch (e) {
    listEl.innerHTML = `<p class="mini" style="color:var(--accent);">读取历史快照失败：${escapeHtml(e.message)}</p>`;
  }

  const cancelBtn = $('hm_cancel_btn');
  const closeBtn = $('hm_close');
  if (cancelBtn) cancelBtn.onclick = () => { modal.style.display = 'none'; };
  if (closeBtn) closeBtn.onclick = () => { modal.style.display = 'none'; };
}

async function triggerQuickContinue() {
  if (!readerData) return;
  const instruction = $('ast_ct_instruction') ? $('ast_ct_instruction').value.trim() : '';
  const chaptersCount = $('ast_ct_chapters') ? parseInt($('ast_ct_chapters').value, 10) || 1 : 1;
  const perWords = $('ast_ct_per_words') ? parseInt($('ast_ct_per_words').value, 10) || 2000 : 2000;
  const providerId = $('ast_ct_provider') ? $('ast_ct_provider').value : undefined;

  const btn = $('btn_ast_start_continue');
  if (btn) {
    btn.disabled = true;
    btn.textContent = '正在启动续写…';
  }

  const payload = {
    mode: 'continuation',
    novel_name: readerData.name,
    instruction: instruction,
    chapters: chaptersCount,
    per_chapter_words: perWords,
    provider_id: providerId
  };

  try {
    const res = await api('/api/generate', 'POST', payload);
    if (res && res.job_id) {
      toast('⚡ 续写任务已在后台启动！');
      const streamWrap = $('ast_stream_wrap');
      if (streamWrap) streamWrap.style.display = 'block';
      subscribeAstStream(res.job_id);
    }
  } catch (e) {
    toast('启动续写失败：' + e.message);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = '⚡ 立即开始续写 (Ctrl+Enter)';
    }
  }
}

function subscribeAstStream(jobId) {
  const streamBody = $('ast_stream_body');
  const streamCh = $('ast_stream_ch');
  const wordsEl = $('ast_stream_words');

  const es = new EventSource('/api/jobs/' + jobId + '/stream');
  let totalChars = 0;

  es.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      if (data.type === 'chunk' && data.chunk) {
        if (streamBody) {
          streamBody.textContent += data.chunk;
          streamBody.scrollTop = streamBody.scrollHeight;
        }
        totalChars += data.chunk.length;
        if (wordsEl) wordsEl.textContent = `${totalChars} 字`;
      } else if (data.type === 'chapter_start') {
        if (streamCh) streamCh.textContent = `正在创作：${data.title || ''}`;
      } else if (data.type === 'done') {
        es.close();
        toast('🎉 续写任务创作完成！已添加至目录。');
        openReader(readerData.name, readerIdx);
      } else if (data.type === 'error') {
        es.close();
        toast('续写任务出错：' + (data.error || '未知错误'));
      }
    } catch (e) {}
  };
  es.onerror = () => {
    es.close();
  };
}

document.addEventListener('keydown', (e) => {
  if (!readerActive()) return;

  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
    e.preventDefault();
    if (isEditingChapter) {
      saveChapterEdit();
    } else {
      enterChapterEdit();
    }
    return;
  }

  if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
    e.preventDefault();
    triggerQuickContinue();
    return;
  }

  const assistModal = $('rd_assist_modal');
  if (assistModal && assistModal.style.display !== 'none') {
    if (e.key === 'Escape') {
      e.preventDefault();
      closeAssistModal();
      return;
    }
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault();
      const applyBtn = $('rd_assist_apply_btn');
      const resWrap = $('rd_assist_result_wrap');
      if (resWrap && resWrap.style.display !== 'none' && applyBtn && !applyBtn.disabled) {
        applyBtn.click();
      } else {
        runAssist();
      }
      return;
    }
  }

  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'b') {
    e.preventDefault();
    const tocToggle = $('rd_toc_toggle');
    if (tocToggle) tocToggle.click();
    return;
  }

  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'j') {
    e.preventDefault();
    const astToggle = $('rd_assistant_toggle');
    if (astToggle) astToggle.click();
    return;
  }

  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'f') {
    e.preventDefault();
    const srBtn = $('rd_search_replace_btn');
    if (srBtn) srBtn.click();
    return;
  }
});

initStudioPanels();
