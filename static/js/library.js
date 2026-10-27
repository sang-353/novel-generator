// ==================== 回收站 / 章节备份 / 缓存清理 ====================
async function loadTrash() {
  const box = $('trash_list');
  try {
    const items = await api('/api/trash');
    if (!items.length) { box.innerHTML = '<p class="mini">回收站是空的。</p>'; return; }
    const typeName = { original: '原创', continuation: '续写', fanfic: '同人' };
    box.innerHTML = items.map(it => `
      <div class="trash-row">
        <span class="t">${escapeHtml(it.title)}</span>
        <span class="tag">${typeName[it.type] || it.type}</span>
        <span class="mini">${it.updated || ''}</span>
        <button class="ghost" data-file="${escapeHtml(it.file)}" data-act="restore">恢复</button>
        <button class="ghost" style="color:var(--err)" data-file="${escapeHtml(it.file)}" data-act="purge">彻底删除</button>
      </div>`).join('');
    box.querySelectorAll('[data-act]').forEach(btn => {
      btn.onclick = async () => {
        const stem = btn.dataset.file.replace(/\.md$/, '');
        try {
          if (btn.dataset.act === 'restore') {
            const r = await api('/api/trash/' + encodeURIComponent(stem) + '/restore', 'POST');
            toast('已恢复《' + r.name + '》');
          } else {
            if (!confirm('彻底删除后不可恢复，确定？')) return;
            await api('/api/trash/' + encodeURIComponent(stem), 'DELETE');
            toast('已彻底删除');
          }
          loadTrash();
          loadLibrary();
        } catch (e) { toast(e.message); }
      };
    });
  } catch (e) { box.innerHTML = '<p class="mini">加载失败：' + escapeHtml(e.message) + '</p>'; }
}

async function loadChapterBackups() {
  const box = $('ch_backup_list');
  try {
    const items = await api('/api/trash/chapters');
    if (!items.length) { box.innerHTML = '<p class="mini">暂无章节备份。</p>'; return; }
    box.innerHTML = items.map(it => `
      <div class="trash-row">
        <span class="t">《${escapeHtml(it.novel)}》第 ${it.index + 1} 章 · ${escapeHtml(it.title || '')}</span>
        <span class="mini">${it.ts || ''}</span>
        <button class="ghost" data-file="${escapeHtml(it.file)}" data-act="restore">恢复</button>
        <button class="ghost" style="color:var(--err)" data-file="${escapeHtml(it.file)}" data-act="purge">删除快照</button>
      </div>`).join('');
    box.querySelectorAll('[data-act]').forEach(btn => {
      btn.onclick = async () => {
        const file = btn.dataset.file;
        try {
          if (btn.dataset.act === 'restore') {
            if (!confirm('将把该章节恢复回原书对应位置（覆盖当前章节），确定？')) return;
            const r = await api('/api/trash/chapters/' + encodeURIComponent(file) + '/restore', 'POST');
            toast('已恢复章节「' + r.title + '」');
          } else {
            if (!confirm('删除该快照后不可恢复，确定？')) return;
            await api('/api/trash/chapters/' + encodeURIComponent(file), 'DELETE');
            toast('已删除快照');
          }
          loadChapterBackups();
        } catch (e) { toast(e.message); }
      };
    });
  } catch (e) { box.innerHTML = '<p class="mini">加载失败：' + escapeHtml(e.message) + '</p>'; }
}

async function loadCacheStats() {
  try {
    const d = await api('/api/cache/stats');
    $('cache_stats').textContent = '分析缓存 ' + d.count + ' 项';
  } catch (e) { /* 忽略 */ }
}
on('btn_clear_cache', async () => {
  if (!confirm('清理分析缓存？（书内已保存的创作档案不受影响，仅释放磁盘）')) return;
  try {
    const d = await api('/api/cache', 'DELETE');
    toast('已清理 ' + d.removed + ' 项缓存');
    loadCacheStats();
  } catch (e) { toast(e.message); }
});
on('btn_refresh_trash', () => { loadTrash(); loadChapterBackups(); });


// ==================== 书架 ====================
function statusText(it) {
  if (it.status === 'generating') return it.stale ? '生成中断' : '生成中…';
  if (it.status === 'cancelled') return '已取消';
  if (it.status === 'error') return '失败';
  return '完成';
}

async function updateLibTrashBadge() {
  try {
    const items = await api('/api/trash');
    const badge = $('lib_trash_badge');
    if (!badge) return;
    if (items && items.length > 0) {
      badge.textContent = String(items.length);
      badge.style.display = 'inline-block';
    } else {
      badge.style.display = 'none';
    }
  } catch (e) {}
}

async function loadLibTrash() {
  const box = $('lib_trash_list');
  if (!box) return;
  try {
    const items = await api('/api/trash');
    updateLibTrashBadge();
    if (!items.length) { box.innerHTML = '<p class="mini">回收站是空的。</p>'; return; }
    const typeName = { original: '原创', continuation: '续写', fanfic: '同人' };
    box.innerHTML = items.map(it => `
      <div class="trash-row">
        <span class="t">${escapeHtml(it.title)}</span>
        <span class="tag">${typeName[it.type] || it.type}</span>
        <span class="mini">${it.updated || ''}</span>
        <button class="ghost" data-file="${escapeHtml(it.file)}" data-act="restore">恢复</button>
        <button class="ghost" style="color:var(--err)" data-file="${escapeHtml(it.file)}" data-act="purge">彻底删除</button>
      </div>`).join('');
    box.querySelectorAll('[data-act]').forEach(btn => {
      btn.onclick = async () => {
        const stem = btn.dataset.file.replace(/\.md$/, '');
        try {
          if (btn.dataset.act === 'restore') {
            const r = await api('/api/trash/' + encodeURIComponent(stem) + '/restore', 'POST');
            toast('已恢复《' + r.name + '》到书架');
          } else {
            if (!confirm('彻底删除后不可恢复，确定？')) return;
            await api('/api/trash/' + encodeURIComponent(stem), 'DELETE');
            toast('已彻底删除');
          }
          loadLibTrash();
          loadTrash();
          loadLibrary();
        } catch (e) { toast(e.message); }
      };
    });
  } catch (e) { box.innerHTML = '<p class="mini">加载失败：' + escapeHtml(e.message) + '</p>'; }
}

let libCachedItems = [];
let libFilter = 'all';
let libSearchQuery = '';
let libViewMode = localStorage.getItem('lib_view_mode') || 'grid';

const GENRE_GRADIENTS = {
  '赛博朋克': 'linear-gradient(145deg, #1e1b4b, #312e81 40%, #064e3b)',
  '科幻未来': 'linear-gradient(145deg, #0f172a, #1e3a8a 50%, #0284c7)',
  '玄幻修真': 'linear-gradient(145deg, #064e3b, #047857 50%, #1e293b)',
  '悬疑惊悚': 'linear-gradient(145deg, #0f172a, #1e293b 60%, #475569)',
  '都市异能': 'linear-gradient(145deg, #78350f, #92400e 50%, #1e293b)',
  '末世求生': 'linear-gradient(145deg, #1c1917, #44403c 50%, #1e3a8a)',
  '轻小说/日常': 'linear-gradient(145deg, #831843, #9d174d 50%, #581c87)',
  '古风武侠': 'linear-gradient(145deg, #7f1d1d, #991b1b 50%, #1c1917)',
  '西幻领主': 'linear-gradient(145deg, #1e3a8a, #1d4ed8 50%, #0f172a)',
  '无限流': 'linear-gradient(145deg, #311042, #581c87 50%, #1e1b4b)'
};
const FALLBACK_GRADIENTS = [
  'linear-gradient(145deg, #1e293b, #334155 50%, #0f172a)',
  'linear-gradient(145deg, #0f766e, #115e59 50%, #134e4a)',
  'linear-gradient(145deg, #4338ca, #3730a3 50%, #1e1b4b)',
  'linear-gradient(145deg, #9a3412, #c2410c 50%, #7c2d12)',
  'linear-gradient(145deg, #0369a1, #0284c7 50%, #075985)'
];

function getBookGradient(title, genre) {
  if (genre && GENRE_GRADIENTS[genre]) return GENRE_GRADIENTS[genre];
  let h = 0;
  for (let i = 0; i < (title || '').length; i++) h = (h * 31 + title.charCodeAt(i)) >>> 0;
  return FALLBACK_GRADIENTS[h % FALLBACK_GRADIENTS.length];
}

function renderLibraryView() {
  const typeName = { original: '原创', continuation: '续写', fanfic: '同人' };
  const grid = $('lib_grid');
  const tableWrap = $('lib_table_wrap');
  const tb = $('lib_tbody');
  if (!grid || !tb) return;

  // 1. 过滤项目
  let filtered = libCachedItems;
  if (libFilter !== 'all') {
    filtered = filtered.filter(it => it.type === libFilter);
  }
  if (libSearchQuery) {
    const q = libSearchQuery.toLowerCase();
    filtered = filtered.filter(it =>
      (it.title && it.title.toLowerCase().includes(q)) ||
      (it.type && (typeName[it.type] || it.type).toLowerCase().includes(q)) ||
      (it.model_used && it.model_used.toLowerCase().includes(q)) ||
      (it.name && it.name.toLowerCase().includes(q))
    );
  }

  // 2. 切换视图显隐
  if (libViewMode === 'grid') {
    grid.style.display = 'grid';
    if (tableWrap) tableWrap.style.display = 'none';
  } else {
    grid.style.display = 'none';
    if (tableWrap) tableWrap.style.display = 'block';
  }

  // 3. 空状态提示
  if (!filtered.length) {
    const emptyMsg = libCachedItems.length === 0
      ? '书架空空如也，去「原创生成」或「续写·同人」写一部作品吧。'
      : '没有找到匹配的小说，换个关键词试试吧。';
    grid.innerHTML = `<div class="lib-empty-hint">${escapeHtml(emptyMsg)}</div>`;
    tb.innerHTML = `<tr><td colspan="9" class="mini">${escapeHtml(emptyMsg)}</td></tr>`;
    return;
  }

  // 4. 渲染卡片网格
  grid.innerHTML = filtered.map(it => {
    const bg = getBookGradient(it.title, it.genre);
    const wordsDisplay = it.words >= 10000 ? `${(it.words / 10000).toFixed(1)}万字` : `${it.words.toLocaleString()}字`;
    const typeLabel = typeName[it.type] || it.type;
    return `
      <div class="book-card" style="background: ${bg}" data-name="${escapeHtml(it.name)}" tabindex="0">
        <div class="book-card-head">
          <span class="book-card-tag">${escapeHtml(typeLabel)}</span>
          <span class="book-card-words">${escapeHtml(wordsDisplay)}</span>
        </div>
        <div class="book-card-center">
          <div class="book-card-title">${escapeHtml(it.title)}</div>
          <div class="book-card-meta">共 ${it.chapters} 章</div>
        </div>
        <div class="book-card-foot">
          <div class="book-card-status-bar">
            <span class="book-card-status-pill">${statusText(it)}</span>
            <span style="font-size:10px">${escapeHtml(it.updated || '')}</span>
          </div>
          <div class="book-card-actions">
            <button type="button" class="book-card-btn primary" data-act="read">📖 阅读</button>
            <button type="button" class="book-card-btn" data-act="continue">⚡ 续写</button>
            <button type="button" class="book-card-btn" data-act="epub" title="导出 EPUB 标准电子书">📥 EPUB</button>
            <button type="button" class="book-card-btn" data-act="more">⚙️ 更多</button>
          </div>
        </div>
      </div>
    `;
  }).join('');

  grid.querySelectorAll('.book-card').forEach(card => {
    const name = card.dataset.name;
    const item = libCachedItems.find(it => it.name === name);
    card.onclick = () => openReader(name);
    card.onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openReader(name); } };

    const readBtn = card.querySelector('[data-act=read]');
    if (readBtn) readBtn.onclick = e => { e.stopPropagation(); openReader(name); };

    const contBtn = card.querySelector('[data-act=continue]');
    if (contBtn) contBtn.onclick = e => {
      e.stopPropagation();
      openContinueCard(name, item && item.type === 'fanfic' ? 'fanfic' : 'continuation');
    };

    const epubBtn = card.querySelector('[data-act=epub]');
    if (epubBtn) epubBtn.onclick = e => {
      e.stopPropagation();
      exportNovel(name, 'epub');
    };

    const moreBtn = card.querySelector('[data-act=more]');
    if (moreBtn) moreBtn.onclick = e => {
      e.stopPropagation();
      const choice = prompt(`《${item ? item.title : name}》更多操作：\n1. 修改书名\n2. 移入隐私书架\n3. 导出 TXT\n4. 导出 Markdown\n5. 删除到回收站\n\n请输入数字 (1-5)：`);
      if (choice === '1') {
        openRenameModal(name, item ? item.title : name);
      } else if (choice === '2') {
        api('/api/novels/' + encodeURIComponent(name) + '/privacy', 'POST', { private: true })
          .then(() => { toast('已移入隐私书架'); loadLibrary(); loadPrivateShelf(); })
          .catch(err => { if (err.locked) toast('隐私书架已锁定，请先解锁'); else toast(err.message); });
      } else if (choice === '3') {
        exportNovel(name, 'txt');
      } else if (choice === '4') {
        exportNovel(name, 'md');
      } else if (choice === '5') {
        if (!confirm(`确定删除《${item ? item.title : name}》？删除后先移入回收站。`)) return;
        api('/api/novels/' + encodeURIComponent(name), 'DELETE')
          .then(() => { toast('已移入回收站'); loadLibrary(); })
          .catch(err => toast(err.message));
      }
    };
  });

  // 5. 渲染表格视图
  tb.innerHTML = filtered.map((it, idx) => `
    <tr class="novel" data-name="${it.name}">
      <td class="folio">${String(idx + 1).padStart(2, '0')}</td>
      <td>${escapeHtml(it.title)}</td>
      <td><span class="tag">${typeName[it.type] || it.type}</span></td>
      <td>${it.chapters} 章</td>
      <td>${it.words.toLocaleString()} 字</td>
      <td><span class="status ${it.status}" ${it.stale ? 'title="服务重启导致生成中断，可到阅读器「从断点继续」"' : ''}>${statusText(it)}</span></td>
      <td class="mini">${escapeHtml(it.model_used || '')}</td>
      <td class="mini">${it.updated}</td>
      <td>
        <button class="ghost" style="padding:4px 8px" data-act="open">阅读</button>
        <button class="ghost" style="padding:4px 8px" data-act="epub" title="导出 EPUB">EPUB</button>
        <button class="ghost" style="padding:4px 8px" data-act="rename" title="修改书名">改名</button>
        <button class="ghost" style="padding:4px 8px" data-act="priv" title="移入隐私书架">隐私</button>
        <button class="ghost" style="padding:4px 8px;color:var(--err);border-color:var(--err)" data-act="del">删除</button>
      </td>
    </tr>`).join('');

  tb.querySelectorAll('tr.novel').forEach(tr => {
    const name = tr.dataset.name;
    const title = tr.querySelector('td:nth-child(2)').textContent;
    tr.tabIndex = 0;
    tr.onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openReader(name); } };
    tr.onclick = () => openReader(name);

    tr.querySelector('[data-act=open]').onclick = e => { e.stopPropagation(); openReader(name); };
    const epBtn = tr.querySelector('[data-act=epub]');
    if (epBtn) epBtn.onclick = e => { e.stopPropagation(); exportNovel(name, 'epub'); };
    const renBtn = tr.querySelector('[data-act=rename]');
    if (renBtn) renBtn.onclick = e => { e.stopPropagation(); openRenameModal(name, title); };
    tr.querySelector('[data-act=priv]').onclick = async e => {
      e.stopPropagation();
      try {
        await api('/api/novels/' + encodeURIComponent(name) + '/privacy', 'POST', { private: true });
        toast('已移入隐私书架');
        loadLibrary();
        loadPrivateShelf();
      } catch (err) {
        if (err.locked) toast('隐私书架已锁定，请先在下方解锁');
        else toast(err.message);
      }
    };
    tr.querySelector('[data-act=del]').onclick = async e => {
      e.stopPropagation();
      if (!confirm(`确定删除《${title}》？删除后先移入回收站。`)) return;
      try { await api('/api/novels/' + encodeURIComponent(name), 'DELETE'); toast('已移入回收站'); loadLibrary(); }
      catch (err) { toast(err.message); }
    };
  });
}

async function loadLibrary() {
  const tb = $('lib_tbody');
  const grid = $('lib_grid');
  if (tb) tb.innerHTML = '<tr><td colspan="9" class="mini">加载中…</td></tr>';
  if (grid) grid.innerHTML = '<div class="lib-loading-hint">正在加载书架…</div>';

  try {
    libCachedItems = await api('/api/novels');
    renderLibraryView();
  } catch (e) {
    if (tb) tb.innerHTML = `<tr><td colspan="9" class="mini">加载失败：${escapeHtml(e.message)}</td></tr>`;
    if (grid) grid.innerHTML = `<div class="lib-empty-hint">加载失败：${escapeHtml(e.message)}</div>`;
  }
}

function initLibraryToolbar() {
  const searchInput = $('lib_search_input');
  if (searchInput) {
    searchInput.oninput = () => {
      libSearchQuery = searchInput.value.trim();
      renderLibraryView();
    };
  }

  const filterTabs = $('lib_filter_tabs');
  if (filterTabs) {
    filterTabs.querySelectorAll('.lib-filter-tab').forEach(tab => {
      tab.onclick = () => {
        libFilter = tab.dataset.filter;
        filterTabs.querySelectorAll('.lib-filter-tab').forEach(t => t.classList.toggle('active', t === tab));
        renderLibraryView();
      };
    });
  }

  const gridBtn = $('lib_view_grid_btn');
  const tableBtn = $('lib_view_table_btn');
  if (gridBtn && tableBtn) {
    gridBtn.onclick = () => {
      libViewMode = 'grid';
      localStorage.setItem('lib_view_mode', 'grid');
      gridBtn.classList.add('active');
      tableBtn.classList.remove('active');
      renderLibraryView();
    };
    tableBtn.onclick = () => {
      libViewMode = 'table';
      localStorage.setItem('lib_view_mode', 'table');
      tableBtn.classList.add('active');
      gridBtn.classList.remove('active');
      renderLibraryView();
    };
    if (libViewMode === 'table') {
      tableBtn.classList.add('active');
      gridBtn.classList.remove('active');
    } else {
      gridBtn.classList.add('active');
      tableBtn.classList.remove('active');
    }
  }
}
initLibraryToolbar();

// ==================== 隐私书架 ====================
async function loadPrivateShelf() {
  const lockedBox = $('pv_locked'), listWrap = $('pv_list_wrap');
  try {
    const st = await api('/api/privacy');
    if (!st.enabled) {
      lockedBox.style.display = 'block';
      listWrap.style.display = 'none';
      $('pv_unlock').disabled = true;
      $('pv_hint').textContent = '尚未设置隐私密码。到「设置 → 隐私密码」设置后，即可把书移入这里。';
      return;
    }
    $('pv_unlock').disabled = false;
    $('pv_hint').textContent = '解锁状态保留 30 分钟，或直到你点「锁定」。';
    if (privacyToken()) {
      try {
        const items = await api('/api/novels/private');
        renderPrivateList(items);
        lockedBox.style.display = 'none';
        listWrap.style.display = 'block';
        return;
      } catch (e) {
        if (!e.locked) throw e;
        setPrivacyToken('');            // 令牌过期，回到锁定态
      }
    }
    lockedBox.style.display = 'block';
    listWrap.style.display = 'none';
  } catch (e) {
    $('pv_hint').textContent = '读取隐私设置失败：' + e.message;
  }
}

function renderPrivateList(items) {
  const tb = $('pv_tbody');
  const typeName = { original: '原创', continuation: '续写', fanfic: '同人' };
  $('pv_count').textContent = items.length ? ('共 ' + items.length + ' 本') : '';
  if (!items.length) {
    tb.innerHTML = '<tr><td colspan="8" class="mini">隐私书架是空的。在「我的书架」里点某本书的「设为隐私」即可移入。</td></tr>';
    return;
  }
  tb.innerHTML = items.map((it, idx) => `
    <tr class="novel" data-name="${it.name}">
      <td class="folio">${String(idx + 1).padStart(2, '0')}</td>
      <td>${escapeHtml(it.title)}</td>
      <td><span class="tag">${typeName[it.type] || it.type}</span></td>
      <td>${it.chapters} 章</td>
      <td>${it.words.toLocaleString()} 字</td>
      <td><span class="status ${it.status}">${statusText(it)}</span></td>
      <td class="mini">${it.updated}</td>
      <td>
        <button class="ghost" style="padding:4px 10px" data-act="open">阅读</button>
        <button class="ghost" style="padding:4px 10px" data-act="unpriv">移出隐私</button>
        <button class="ghost" style="padding:4px 10px;color:var(--err);border-color:var(--err)" data-act="del">删除</button>
      </td>
    </tr>`).join('');
  tb.querySelectorAll('tr.novel').forEach(tr => {
    tr.tabIndex = 0;
    tr.addEventListener('keydown', e => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openReader(tr.dataset.name); }
    });
    tr.querySelector('[data-act=open]').onclick = e => { e.stopPropagation(); openReader(tr.dataset.name); };
    tr.querySelector('[data-act=unpriv]').onclick = async e => {
      e.stopPropagation();
      try {
        await api('/api/novels/' + encodeURIComponent(tr.dataset.name) + '/privacy', 'POST', { private: false });
        toast('已移出隐私书架');
        loadPrivateShelf();
        loadLibrary();
      } catch (err) { toast(err.message); }
    };
    tr.querySelector('[data-act=del]').onclick = async e => {
      e.stopPropagation();
      if (!confirm('确定删除《' + tr.querySelector('td:nth-child(2)').textContent + '》？删除后先移入回收站，可恢复。')) return;
      try {
        await api('/api/novels/' + encodeURIComponent(tr.dataset.name), 'DELETE');
        toast('已移入回收站');
        loadPrivateShelf();
        loadLibrary();
      } catch (err) { toast(err.message); }
    };
    tr.onclick = () => openReader(tr.dataset.name);
  });
}

async function unlockPrivate() {
  const pwd = $('pv_password').value;
  if (!pwd) { toast('请输入隐私密码'); return; }
  $('pv_unlock').disabled = true;
  setStatus('pv_status', '验证中…');
  try {
    const d = await api('/api/privacy/unlock', 'POST', { password: pwd });
    setPrivacyToken(d.token);
    $('pv_password').value = '';
    setStatus('pv_status', '');
    await loadPrivateShelf();
    toast('隐私书架已解锁');
  } catch (e) {
    setStatus('pv_status', '解锁失败：' + e.message);
  }
  $('pv_unlock').disabled = false;
}
on('pv_unlock', unlockPrivate);
on('pv_password', 'keydown', e => {
  if (e.key === 'Enter') { e.preventDefault(); unlockPrivate(); }
});
on('pv_lock', async () => {
  try { await api('/api/privacy/lock', 'POST'); } catch (e) { /* 忽略 */ }
  setPrivacyToken('');
  await loadPrivateShelf();
  toast('隐私书架已锁定');
});


// ==================== 导出 ====================
async function exportNovel(name, fmt) {
  try {
    const r = await fetch(withToken('/api/novels/' + encodeURIComponent(name) + '/export?fmt=' + fmt));
    if (!r.ok) { const d = await r.json().catch(() => ({})); throw new Error(d.error || '导出失败'); }
    const blob = await r.blob();
    const cd = r.headers.get('Content-Disposition') || '';
    const m = cd.match(/filename\*=UTF-8''([^;]+)/);
    const fname = m ? decodeURIComponent(m[1]) : (name + '.' + fmt);
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = fname;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(a.href);
    toast('已导出 ' + fname);
  } catch (e) { toast(e.message); }
}

// ==================== 重命名功能 ====================
let renameTargetName = null;
let renameCallback = null;

function openRenameModal(novelName, currentTitle, onDone = null) {
  renameTargetName = novelName;
  renameCallback = onDone;
  $('rename_modal_title').textContent = '修改小说标题 · ' + (currentTitle || novelName);
  $('rename_input').value = currentTitle || novelName;
  openModal('rename_modal', {
    mask: false,
    esc: true,
    onClose: () => { renameTargetName = null; renameCallback = null; }
  });
  setTimeout(() => $('rename_input').focus(), 150);
}

function closeRenameModal() {
  closeModal('rename_modal');
}

on('btn_cancel_rename', closeRenameModal);
on('btn_confirm_rename', async () => {
  const newTitle = $('rename_input').value.trim();
  if (!newTitle) { toast('标题不能为空'); return; }
  const oldName = renameTargetName;
  try {
    const res = await api('/api/novels/' + encodeURIComponent(oldName) + '/rename', 'POST', { title: newTitle });
    toast('已更名为《' + newTitle + '》');
    closeRenameModal();
    if (typeof renameCallback === 'function') {
      renameCallback(newTitle, res.new_name);
    }
    loadLibrary();
    if (privacyToken()) loadPrivateShelf();
  } catch (e) {
    toast(e.message);
  }
});

// ==================== P3: 外部 TXT 小说智能分章导入 ====================

function initImportTxtModal() {
  const importBtn = $('lib_import_btn');
  const modal = $('import_modal');
  const closeBtn = $('im_close');
  const cancelBtn = $('im_cancel_btn');
  const confirmBtn = $('im_confirm_btn');
  const fileInp = $('im_file_inp');
  const titleInp = $('im_title_inp');
  const genreInp = $('im_genre_inp');
  const textInp = $('im_text_inp');
  const previewBox = $('im_preview_box');

  if (!modal) return;

  function openImportModal() {
    openModal('import_modal', { mask: false, esc: true });
    if (fileInp) fileInp.value = '';
    if (textInp) textInp.value = '';
    if (titleInp) titleInp.value = '';
    if (previewBox) {
      previewBox.style.display = 'none';
      previewBox.textContent = '';
    }
  }

  function closeImportModal() {
    closeModal('import_modal');
  }

  if (importBtn) importBtn.onclick = openImportModal;
  if (closeBtn) closeBtn.onclick = closeImportModal;
  if (cancelBtn) cancelBtn.onclick = closeImportModal;

  if (fileInp) {
    fileInp.onchange = () => {
      const file = fileInp.files && fileInp.files[0];
      if (!file) return;
      if (titleInp && !titleInp.value.trim()) {
        const baseName = file.name.replace(/\.[^/.]+$/, '');
        titleInp.value = baseName;
      }
      const reader = new FileReader();
      reader.onload = (e) => {
        const text = e.target.result;
        updateImportPreview(text);
      };
      reader.readAsText(file);
    };
  }

  if (textInp) {
    textInp.oninput = () => {
      updateImportPreview(textInp.value);
    };
  }

  function updateImportPreview(content) {
    if (!previewBox) return;
    if (!content.trim()) {
      previewBox.style.display = 'none';
      return;
    }
    const regex = /(?:^|\r?\n)[ \t]*(第[0-9零一二三四五六七八九十百千万]+[章节回集卷篇节][^\r\n]*|Chapter\s+[0-9]+[^\r\n]*|[【\[（(]第[0-9零一二三四五六七八九十百千万]+[章节回集卷][】\]）)][^\r\n]*|引子[^\r\n]*|序章[^\r\n]*|尾声[^\r\n]*|番外[^\r\n]*)/gi;
    const matches = content.match(regex);
    const count = matches ? matches.length : Math.ceil(content.length / 3000);
    const words = content.replace(/\s/g, '').length;
    previewBox.innerHTML = `<strong>识别预览：</strong> 检测到约 <b>${count}</b> 个章节，总字数 <b>${words.toLocaleString()}</b> 字。<br><span style="color:var(--muted)">前三个章节：${matches ? matches.slice(0, 3).map(m => escapeHtml(m.trim())).join(' · ') : '按篇幅均匀切分'}</span>`;
    previewBox.style.display = 'block';
  }

  if (confirmBtn) {
    confirmBtn.onclick = async () => {
      const title = titleInp ? titleInp.value.trim() : '';
      const genre = genreInp ? genreInp.value.trim() : '都市言情';
      const file = fileInp && fileInp.files && fileInp.files[0];
      const text = textInp ? textInp.value.trim() : '';

      if (!file && !text) {
        toast('请选择 TXT 文件或粘贴全文内容');
        return;
      }

      confirmBtn.disabled = true;
      confirmBtn.textContent = '正在智能分章导入…';

      try {
        let res;
        if (file) {
          const fd = new FormData();
          fd.append('file', file);
          if (title) fd.append('title', title);
          if (genre) fd.append('genre', genre);
          const resp = await fetch('/api/novels/import-txt', {
            method: 'POST',
            body: fd
          });
          res = await resp.json();
        } else {
          res = await api('/api/novels/import-txt', 'POST', {
            title: title || '未命名导入作品',
            genre: genre,
            text: text
          });
        }

        if (res && res.ok) {
          toast(`🎉 成功导入《${res.title}》（共 ${res.chapters_count} 章，${res.total_words.toLocaleString()} 字）！`);
          closeImportModal();
          await loadLibrary();
          // Open directly in Studio
          if (typeof openReader === 'function') {
            openReader(res.name, 0);
          }
        } else {
          toast('导入失败：' + (res && res.error ? res.error : '未知错误'));
        }
      } catch (e) {
        toast('导入请求失败：' + e.message);
      } finally {
        confirmBtn.disabled = false;
        confirmBtn.textContent = '开始智能分章导入';
      }
    };
  }
}
initImportTxtModal();
