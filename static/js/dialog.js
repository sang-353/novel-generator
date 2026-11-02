/**
 * static/js/dialog.js - NovelStudio 现代化交互弹窗与浮动菜单体系
 * 
 * 按照功能属性划分为 4 大专属 UI 形态，统一遵循 Literary Atelier 现代文学工坊设计语言：
 * Group 1: 书架卡片浮动气泡菜单 (Floating Context Popover)
 * Group 2: 阅读器目录行内极速输入条 (Inline Quick-Prompt Bar)
 * Group 3: 角色蓝图档案卡片模态框 (Character Blueprint Modal)
 * Group 4: 安全敏感门禁与危险操作确认 (Security Shield & Destructive Dialog)
 */

// ==============================================================
// Group 1: 书架卡片浮动气泡上下文菜单 (Floating Context Popover)
// ==============================================================

let activePopoverMenu = null;

/**
 * 展开书籍卡片「更多操作」浮动气泡菜单
 * @param {HTMLElement} triggerBtn 触发按钮
 * @param {Object} item 书籍元数据
 * @param {Object} actions 回调操作集合
 */
function openCardMoreMenu(triggerBtn, item, actions = {}) {
  // 先关闭任何已存在的浮动菜单
  closeCardMoreMenu();

  const popover = document.createElement('div');
  popover.className = 'atelier-popover-menu';
  popover.setAttribute('role', 'menu');
  popover.setAttribute('aria-label', `《${item.title || item.name}》更多操作菜单`);

  const titleText = escapeHtml(item.title || item.name);
  popover.innerHTML = `
    <div class="popover-header">
      <span class="popover-title" title="${titleText}">《${titleText}》</span>
      <span class="popover-meta">${item.chapters || 0} 章 · ${(item.words || 0).toLocaleString()} 字</span>
    </div>
    <div class="popover-group">
      <button type="button" class="popover-item" data-act="rename">
        <span class="popover-icon">✏️</span>
        <span class="popover-text">修改书名</span>
      </button>
      <button type="button" class="popover-item" data-act="privacy">
        <span class="popover-icon">🔒</span>
        <span class="popover-text">移入隐私书架</span>
      </button>
    </div>
    <div class="popover-divider"></div>
    <div class="popover-group">
      <button type="button" class="popover-item" data-act="export_txt">
        <span class="popover-icon">📄</span>
        <span class="popover-text">导出 TXT 纯文本</span>
      </button>
      <button type="button" class="popover-item" data-act="export_md">
        <span class="popover-icon">📑</span>
        <span class="popover-text">导出 Markdown</span>
      </button>
    </div>
    <div class="popover-divider"></div>
    <div class="popover-group">
      <button type="button" class="popover-item danger" data-act="delete">
        <span class="popover-icon">🗑️</span>
        <span class="popover-text">移至回收站</span>
      </button>
    </div>
  `;

  // 绑定菜单内部各项点击
  popover.querySelectorAll('.popover-item').forEach(btn => {
    btn.onmousedown = e => { e.preventDefault(); e.stopPropagation(); };
    btn.onclick = e => {
      e.stopPropagation();
      const act = btn.dataset.act;
      closeCardMoreMenu();
      if (typeof actions[act] === 'function') {
        actions[act](item);
      }
    };
  });

  document.body.appendChild(popover);
  activePopoverMenu = popover;

  // 定位计算：检测视口上下方空间，自适应向上翻转 (Flip)
  const rect = triggerBtn.getBoundingClientRect();
  const popoverWidth = 204;
  const popoverHeight = 220; // 预估最大高度

  let top = rect.bottom + 6;
  let left = rect.right - popoverWidth;

  // 视口下边缘碰撞检测，向上弹出
  if (top + popoverHeight > window.innerHeight - 12) {
    top = rect.top - popoverHeight - 6;
  }
  // 视口左侧碰撞检测
  if (left < 10) left = 10;

  popover.style.top = `${Math.max(10, top + window.scrollY)}px`;
  popover.style.left = `${Math.max(10, left + window.scrollX)}px`;

  // 触发入场微动效
  requestAnimationFrame(() => {
    popover.classList.add('visible');
  });
}

function closeCardMoreMenu() {
  if (activePopoverMenu) {
    const el = activePopoverMenu;
    activePopoverMenu = null;
    el.classList.remove('visible');
    setTimeout(() => {
      if (el.parentNode) el.parentNode.removeChild(el);
    }, 180);
  }
}

// 全局监听：点击外部空白或按 Esc 键关闭卡片浮动菜单
document.addEventListener('mousedown', e => {
  if (activePopoverMenu && !activePopoverMenu.contains(e.target)) {
    closeCardMoreMenu();
  }
}, true);

document.addEventListener('keydown', e => {
  if (e.key === 'Escape' && activePopoverMenu) {
    closeCardMoreMenu();
  }
});


// ==============================================================
// Group 2: 阅读器目录行内极速输入条 (Inline Quick-Prompt Bar)
// ==============================================================

let inlineTocCallback = null;

/**
 * 在阅读器目录区域展示就地快速输入条
 * @param {Object} options 配置项 { title, defaultValue, placeholder, onConfirm }
 */
function showInlineTocInput(options = {}) {
  const bar = $('rd_inline_toc_bar');
  if (!bar) return;

  inlineTocCallback = options.onConfirm || null;
  const labelEl = $('rd_inline_label');
  const inp = $('rd_inline_input');

  if (labelEl) labelEl.textContent = options.title || '新增章节';
  if (inp) {
    inp.value = options.defaultValue || '';
    inp.placeholder = options.placeholder || '请输入…';
  }

  bar.style.display = 'block';
  requestAnimationFrame(() => {
    bar.classList.add('visible');
    if (inp) {
      inp.focus();
      inp.select();
    }
  });
}

function hideInlineTocInput() {
  const bar = $('rd_inline_toc_bar');
  if (bar) {
    bar.classList.remove('visible');
    setTimeout(() => {
      bar.style.display = 'none';
      inlineTocCallback = null;
    }, 150);
  }
}

function initInlineTocInput() {
  const bar = $('rd_inline_toc_bar');
  if (!bar) return;

  on('rd_inline_confirm_btn', () => {
    const inp = $('rd_inline_input');
    const val = inp ? inp.value.trim() : '';
    if (!val) {
      if (inp) inp.focus();
      return;
    }
    const cb = inlineTocCallback;
    hideInlineTocInput();
    if (typeof cb === 'function') cb(val);
  });

  on('rd_inline_cancel_btn', hideInlineTocInput);

  const inp = $('rd_inline_input');
  if (inp) {
    inp.onkeydown = e => {
      if (e.key === 'Enter') {
        e.preventDefault();
        const val = inp.value.trim();
        if (!val) return;
        const cb = inlineTocCallback;
        hideInlineTocInput();
        if (typeof cb === 'function') cb(val);
      } else if (e.key === 'Escape') {
        e.preventDefault();
        hideInlineTocInput();
      }
    };
  }
}


// ==============================================================
// Group 3: 角色蓝图档案卡片模态框 (Character Blueprint Modal)
// ==============================================================

let charBlueprintCallback = null;

function showCharBlueprintModal(onSave) {
  charBlueprintCallback = onSave;
  const nameInp = $('cb_name_inp');
  const descInp = $('cb_desc_inp');
  if (nameInp) nameInp.value = '';
  if (descInp) descInp.value = '';

  openModal('char_blueprint_modal', {
    mask: false,
    esc: true,
    onClose: () => { charBlueprintCallback = null; }
  });

  setTimeout(() => {
    if (nameInp) nameInp.focus();
  }, 120);
}

function initCharBlueprintModal() {
  on('cb_cancel_btn', () => closeModal('char_blueprint_modal'));
  on('cb_save_btn', () => {
    const nameInp = $('cb_name_inp');
    const descInp = $('cb_desc_inp');
    const name = nameInp ? nameInp.value.trim() : '';
    const desc = descInp ? descInp.value.trim() : '';

    if (!name) {
      toast('角色姓名不能为空');
      if (nameInp) nameInp.focus();
      return;
    }

    closeModal('char_blueprint_modal');
    if (typeof charBlueprintCallback === 'function') {
      charBlueprintCallback(name, desc);
    }
  });

  const nameInp = $('cb_name_inp');
  if (nameInp) {
    nameInp.onkeydown = e => {
      if (e.key === 'Enter') {
        const descInp = $('cb_desc_inp');
        if (descInp) descInp.focus();
      }
    };
  }
}


// ==============================================================
// Group 4: 安全敏感门禁与危险确认 (Security Shield & Destructive Dialog)
// ==============================================================

let securityPwdResolve = null;

function showSecurityPasswordModal(options = {}) {
  return new Promise(resolve => {
    securityPwdResolve = resolve;
    const titleEl = $('sec_pwd_title');
    const descEl = $('sec_pwd_desc');
    const inp = $('sec_pwd_input');

    if (titleEl) titleEl.textContent = options.title || '安全身份验证';
    if (descEl) descEl.textContent = options.desc || '请输入访问口令以继续：';
    if (inp) {
      inp.value = '';
      inp.type = 'password';
    }

    openModal('security_pwd_modal', {
      mask: false,
      esc: true,
      onClose: () => {
        if (securityPwdResolve) {
          const fn = securityPwdResolve;
          securityPwdResolve = null;
          fn(null);
        }
      }
    });

    setTimeout(() => {
      if (inp) inp.focus();
    }, 120);
  });
}

function initSecurityPasswordModal() {
  on('sec_pwd_cancel_btn', () => {
    closeModal('security_pwd_modal');
    if (securityPwdResolve) {
      const fn = securityPwdResolve;
      securityPwdResolve = null;
      fn(null);
    }
  });

  const doConfirm = () => {
    const inp = $('sec_pwd_input');
    const val = inp ? inp.value.trim() : '';
    if (!val) {
      toast('请输入访问口令');
      if (inp) inp.focus();
      return;
    }
    closeModal('security_pwd_modal');
    if (securityPwdResolve) {
      const fn = securityPwdResolve;
      securityPwdResolve = null;
      fn(val);
    }
  };

  on('sec_pwd_confirm_btn', doConfirm);

  const inp = $('sec_pwd_input');
  if (inp) {
    inp.onkeydown = e => {
      if (e.key === 'Enter') {
        e.preventDefault();
        doConfirm();
      }
    };
  }

  // 小眼睛密码显隐切换
  const toggleBtn = $('sec_pwd_toggle_vis');
  if (toggleBtn && inp) {
    toggleBtn.onclick = () => {
      if (inp.type === 'password') {
        inp.type = 'text';
        toggleBtn.textContent = '🙈';
        toggleBtn.setAttribute('title', '隐藏口令');
      } else {
        inp.type = 'password';
        toggleBtn.textContent = '👁️';
        toggleBtn.setAttribute('title', '显示口令');
      }
    };
  }
}

// 页面加载完成后初始化各弹窗事件
document.addEventListener('DOMContentLoaded', () => {
  initInlineTocInput();
  initCharBlueprintModal();
  initSecurityPasswordModal();
});
