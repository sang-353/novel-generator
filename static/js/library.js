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
$('btn_clear_cache').onclick = async () => {
  if (!confirm('清理分析缓存？（书内已保存的创作档案不受影响，仅释放磁盘）')) return;
  try {
    const d = await api('/api/cache', 'DELETE');
    toast('已清理 ' + d.removed + ' 项缓存');
    loadCacheStats();
  } catch (e) { toast(e.message); }
};
$('btn_refresh_trash').onclick = () => { loadTrash(); loadChapterBackups(); };


// ==================== 书架 ====================
function statusText(it) {
  if (it.status === 'generating') return it.stale ? '生成中断' : '生成中';
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

async function loadLibrary() {
  const tb = $('lib_tbody'); tb.innerHTML = '<tr><td colspan="9" class="mini">加载中…</td></tr>';
  try {
    const items = await api('/api/novels');
    if (!items.length) { tb.innerHTML = '<tr><td colspan="9" class="mini">书架空空如也，去「原创生成」或「续写·同人」写一本吧。</td></tr>'; return; }
    const typeName = { original: '原创', continuation: '续写', fanfic: '同人' };
    tb.innerHTML = items.map((it, idx) => `
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
          <button class="ghost" style="padding:4px 10px" data-act="open">阅读</button>
          <button class="ghost" style="padding:4px 10px" data-act="rename" title="修改书名">改名</button>
          <button class="ghost" style="padding:4px 10px" data-act="priv" title="移入隐私书架（需先设置隐私密码）">设为隐私</button>
          <button class="ghost" style="padding:4px 10px;color:var(--err);border-color:var(--err)" data-act="del">删除</button>
        </td>
      </tr>`).join('');
    tb.querySelectorAll('tr.novel').forEach(tr => {
      tr.tabIndex = 0;
      tr.addEventListener('keydown', e => {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openReader(tr.dataset.name); }
      });
      tr.querySelector('[data-act=open]').onclick = e => { e.stopPropagation(); openReader(tr.dataset.name); };
      const renBtn = tr.querySelector('[data-act=rename]');
      if (renBtn) renBtn.onclick = e => {
        e.stopPropagation();
        openRenameModal(tr.dataset.name, tr.querySelector('td:nth-child(2)').textContent);
      };
      tr.querySelector('[data-act=priv]').onclick = async e => {
        e.stopPropagation();
        try {
          await api('/api/novels/' + encodeURIComponent(tr.dataset.name) + '/privacy', 'POST', { private: true });
          toast('已移入隐私书架');
          loadLibrary();
          loadPrivateShelf();
        } catch (err) {
          if (err.locked) { toast('隐私书架已锁定，请先在下方解锁'); }
          else toast(err.message);
        }
      };
      tr.querySelector('[data-act=del]').onclick = async e => {
        e.stopPropagation();
        if (!confirm('确定删除《' + tr.querySelector('td:nth-child(2)').textContent + '》？删除后先移入回收站，可在「设置 → 回收站」恢复。')) return;
        try { await api('/api/novels/' + encodeURIComponent(tr.dataset.name), 'DELETE'); toast('已移入回收站'); loadLibrary(); }
        catch (err) { toast(err.message); }
      };
      tr.onclick = () => openReader(tr.dataset.name);
    });
  } catch (e) { tb.innerHTML = `<tr><td colspan="9" class="mini">加载失败：${escapeHtml(e.message)}</td></tr>`; }
}

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
$('pv_unlock').onclick = unlockPrivate;
$('pv_password').addEventListener('keydown', e => {
  if (e.key === 'Enter') { e.preventDefault(); unlockPrivate(); }
});
$('pv_lock').onclick = async () => {
  try { await api('/api/privacy/lock', 'POST'); } catch (e) { /* 忽略 */ }
  setPrivacyToken('');
  await loadPrivateShelf();
  toast('隐私书架已锁定');
};


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
  $('rename_modal').classList.add('show');
  setTimeout(() => $('rename_input').focus(), 150);
}

function closeRenameModal() {
  $('rename_modal').classList.remove('show');
  renameTargetName = null;
  renameCallback = null;
}

$('btn_cancel_rename').onclick = closeRenameModal;
$('btn_confirm_rename').onclick = async () => {
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
};
