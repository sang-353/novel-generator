/**
 * static/js/og_step1.js
 * 原创小说生成第 1 步增强：作品卡摘要条、完成度、灵感应用反馈与撤销、下一步校验
 */

(function() {
  'use strict';

  const SNAPSHOT_FIELDS = [
    'og_title', 'og_genre', 'og_setting', 'og_characters', 'og_storyline',
    'og_style', 'og_perspective', 'og_chapters', 'og_per_words'
  ];

  const CONTENT_FIELDS = [
    'og_title', 'og_genre', 'og_setting', 'og_storyline', 'og_characters', 'og_style'
  ];

  let lastSnapshot = null;
  let undoTimer = null;
  let lastAnnouncedProgress = '';
  let lastGenreVal = '';

  // 1. 同步测量 header 高度并赋给 CSS 变量 --og2-header-height
  function syncHeaderHeight() {
    const hdr = document.querySelector('header');
    if (hdr) {
      const h = hdr.offsetHeight;
      if (h > 0) {
        document.documentElement.style.setProperty('--og2-header-height', h + 'px');
      }
    }
  }

  // 2. 检查第 1 步是否满足下一步校验规则（题材、背景、书名至少有一项非空）
  function checkStep1Valid() {
    const genre = $('og_genre') ? $('og_genre').value.trim() : '';
    const setting = $('og_setting') ? $('og_setting').value.trim() : '';
    const title = $('og_title') ? $('og_title').value.trim() : '';
    return !!(genre || setting || title);
  }

  function updateStep1NextButtonState() {
    const btn = $('btn_step1_next');
    if (!btn) return;
    const isValid = checkStep1Valid();
    btn.setAttribute('aria-disabled', isValid ? 'false' : 'true');
    btn.classList.toggle('og2-btn-disabled', !isValid);

    if (isValid) {
      hideStep1InlineTip();
    }
  }

  function showStep1InlineTip() {
    const tip = $('og2_step1_next_inline_tip');
    if (tip) {
      tip.style.display = 'flex';
    }
  }

  function hideStep1InlineTip() {
    const tip = $('og2_step1_next_inline_tip');
    if (tip) {
      tip.style.display = 'none';
    }
  }

  // 3. 更新摘要条内容与完成度
  function updateOgSummary() {
    const bar = $('og2_summary_bar');
    if (!bar) return;

    // 字段读取
    const genre = $('og_genre') ? $('og_genre').value.trim() : '';
    const title = $('og_title') ? $('og_title').value.trim() : '';
    const setting = $('og_setting') ? $('og_setting').value.trim() : '';
    const storyline = $('og_storyline') ? $('og_storyline').value.trim() : '';

    // 题材
    const elGenre = $('og2_summary_genre');
    if (elGenre) {
      elGenre.textContent = genre || '未选题材';
      elGenre.classList.toggle('is-empty', !genre);
      elGenre.title = genre || '未选题材';
    }

    // 书名
    const elTitle = $('og2_summary_title');
    if (elTitle) {
      elTitle.textContent = title || '未命名';
      elTitle.classList.toggle('is-empty', !title);
      elTitle.title = title || '未命名';
    }

    // 背景字数
    const elSettingWc = $('og2_summary_setting_wc');
    if (elSettingWc) {
      elSettingWc.textContent = `背景 ${setting.length} 字`;
    }

    // 主线字数
    const elStorylineWc = $('og2_summary_storyline_wc');
    if (elStorylineWc) {
      elStorylineWc.textContent = `主线 ${storyline.length} 字`;
    }

    // 4 项指标计算：题材、书名、背景、主线
    let count = 0;
    const hasGenre = !!genre;
    const hasTitle = !!title;
    const hasSetting = !!setting;
    const hasStoryline = !!storyline;

    if (hasGenre) count++;
    if (hasTitle) count++;
    if (hasSetting) count++;
    if (hasStoryline) count++;

    // 圆点状态：填了为 solid (.filled)，未填为空心
    const dotGenre = $('og2_dot_genre');
    if (dotGenre) dotGenre.classList.toggle('filled', hasGenre);

    const dotTitle = $('og2_dot_title');
    if (dotTitle) dotTitle.classList.toggle('filled', hasTitle);

    const dotSetting = $('og2_dot_setting');
    if (dotSetting) dotSetting.classList.toggle('filled', hasSetting);

    const dotStoryline = $('og2_dot_storyline');
    if (dotStoryline) dotStoryline.classList.toggle('filled', hasStoryline);

    // 完成度文本
    const countText = `已填写 ${count}/4`;
    const elCount = $('og2_summary_completion');
    if (elCount) {
      elCount.textContent = countText;
    }

    // aria-live 仅在 count 变化时通报
    if (countText !== lastAnnouncedProgress) {
      lastAnnouncedProgress = countText;
      const announceEl = $('og2_summary_announce');
      if (announceEl) {
        announceEl.textContent = countText;
      }
    }

    // 同步下一步按钮状态
    updateStep1NextButtonState();
  }

  // 4. 快照管理
  function takeSnapshot() {
    const snap = {};
    SNAPSHOT_FIELDS.forEach(id => {
      const el = $(id);
      snap[id] = el ? el.value : '';
    });
    return snap;
  }

  function restoreSnapshot(snap) {
    if (!snap) return;
    SNAPSHOT_FIELDS.forEach(id => {
      const el = $(id);
      if (el && snap[id] !== undefined) {
        el.value = snap[id];
      }
    });

    // 静默退出任何审阅状态
    cancelAllReviews();

    // 触发全局链路
    if (typeof window.ogStep1AfterFill === 'function') {
      window.ogStep1AfterFill();
    }

    // 派发 input 事件触发草稿保存
    dispatchDraftInput();
  }

  // 派发草稿同步 input 事件
  function dispatchDraftInput() {
    const setEl = $('og_setting');
    if (setEl) {
      setEl.dispatchEvent(new Event('input', { bubbles: true }));
    }
  }

  // 静默退出所有审阅状态
  function cancelAllReviews() {
    const settingReview = $('og_setting_review_bar');
    if (settingReview && settingReview.style.display !== 'none') {
      const btn = $('btn_setting_accept');
      if (btn) btn.click();
    }
    const storylineReview = $('og_storyline_review_bar');
    if (storylineReview && storylineReview.style.display !== 'none') {
      const btn = $('btn_storyline_accept');
      if (btn) btn.click();
    }
  }

  // 5. 撤销 Toast 展示与关闭
  function adjustUndoToastPosition() {
    const toastEl = $('og2_undo_toast');
    if (!toastEl || toastEl.style.display === 'none') return;

    const isMobile = window.innerWidth <= 640;
    const baseBottom = isMobile ? 16 : 24;

    toastEl.style.bottom = `${baseBottom}px`;
    const toastRect = toastEl.getBoundingClientRect();

    const obstacles = [];
    const nextBtn = $('btn_step1_next');
    if (nextBtn) obstacles.push(nextBtn);
    document.querySelectorAll('#view-original .og2-field-footer').forEach(el => obstacles.push(el));

    let maxBottom = baseBottom;
    const vh = window.innerHeight || document.documentElement.clientHeight;

    obstacles.forEach(el => {
      const r = el.getBoundingClientRect();
      if (r.width <= 0 || r.height <= 0 || r.bottom <= 0 || r.top >= vh) return;

      const xOverlap = !(toastRect.right <= r.left || toastRect.left >= r.right);
      if (!xOverlap) return;

      const toastTop = vh - maxBottom - toastRect.height;
      const toastBottom = vh - maxBottom;
      const yOverlap = !(toastBottom <= r.top || toastTop >= r.bottom);

      if (yOverlap) {
        const needed = (vh - r.top) + 8;
        if (needed > maxBottom) {
          maxBottom = needed;
        }
      }
    });

    toastEl.style.bottom = `${maxBottom}px`;
  }

  function showUndoToast(tropeName) {
    const toastEl = $('og2_undo_toast');
    if (!toastEl) return;

    clearTimeout(undoTimer);

    // 隐藏可能弹出的全局通用 toast，防止重叠
    const gToast = $('toast');
    if (gToast) {
      gToast.style.display = 'none';
    }

    const msgEl = $('og2_undo_toast_msg');
    if (msgEl) {
      msgEl.textContent = `已应用灵感「${tropeName || '未命名'}」`;
    }

    toastEl.style.display = 'flex';
    adjustUndoToastPosition();

    // 保留 10 秒后自动消失
    undoTimer = setTimeout(() => {
      hideUndoToast();
    }, 10000);
  }

  function hideUndoToast() {
    clearTimeout(undoTimer);
    lastSnapshot = null;
    const toastEl = $('og2_undo_toast');
    if (toastEl) {
      toastEl.style.display = 'none';
      toastEl.style.bottom = '';
    }
  }

  // 6. 灵感应用后的平滑滚动与高亮反馈
  function feedbackAfterTropeApply() {
    const titleEl = $('og_title');
    if (!titleEl) return;

    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    // 检查书名框是否在可视范围内（避开 header 和 summary bar）
    const rect = titleEl.getBoundingClientRect();
    const headerH = parseInt(getComputedStyle(document.documentElement).getPropertyValue('--og2-header-height') || '53', 10);
    const summaryH = 44;
    const topSafe = headerH + summaryH + 10;
    const inViewport = (rect.top >= topSafe && rect.bottom <= (window.innerHeight || document.documentElement.clientHeight));

    if (!inViewport) {
      titleEl.scrollIntoView({
        behavior: reducedMotion ? 'auto' : 'smooth',
        block: 'center'
      });
    }

    if (reducedMotion) {
      ['og_title', 'og_genre', 'og_setting', 'og_storyline'].forEach(id => {
        const el = $(id);
        if (el) el.classList.remove('og2-flash-highlight');
      });
    } else {
      ['og_title', 'og_genre', 'og_setting', 'og_storyline'].forEach(id => {
        const el = $(id);
        if (el) {
          el.classList.remove('og2-flash-highlight');
          void el.offsetWidth;
          el.classList.add('og2-flash-highlight');
          setTimeout(() => el.classList.remove('og2-flash-highlight'), 600);
        }
      });
    }
  }

  // 7. 捕获阶段拦截灵感应用
  function handleTropeApplyCapture(e) {
    // 捕获阶段：在 generator.js 执行 applyTropeTemplate 前取快照
    const snapshotBefore = takeSnapshot();

    // 静默结束审阅状态（撤销快照取屏幕显示的值）
    cancelAllReviews();

    // 隐藏题材更改提示条
    hideGenreHintBar();

    // 在微任务中检查应用结果
    setTimeout(() => {
      // 检查原本是否有内容字段存在且发生改变（避免空表单因默认章节数/单章字数误判为已有内容）
      const isOriginallyEmpty = CONTENT_FIELDS.every(id => !(snapshotBefore[id] || '').trim());
      const hasContentChange = CONTENT_FIELDS.some(id => {
        const oldVal = (snapshotBefore[id] || '').trim();
        const newVal = ($(id) ? $(id).value : '').trim();
        return oldVal !== '' && oldVal !== newVal;
      });

      const appliedTitle = $('og_title') ? $('og_title').value.trim() : '';

      if (!isOriginallyEmpty && hasContentChange) {
        lastSnapshot = snapshotBefore;
        showUndoToast(appliedTitle);
      } else {
        lastSnapshot = null;
        hideUndoToast();
      }

      feedbackAfterTropeApply();
      dispatchDraftInput();
    }, 10);
  }

  // 8. 题材更改提示条
  function showGenreHintBar() {
    const hint = $('og2_genre_hint_bar');
    if (hint) {
      hint.style.display = 'block';
    }
  }

  function hideGenreHintBar() {
    const hint = $('og2_genre_hint_bar');
    if (hint) {
      hint.style.display = 'none';
    }
  }

  function handleGenreChange() {
    const currentGenre = $('og_genre') ? $('og_genre').value.trim() : '';
    if (currentGenre && currentGenre !== lastGenreVal) {
      showGenreHintBar();
    }
    lastGenreVal = currentGenre;
  }

  // 9. 挂载到 window.ogStep1AfterFill 链路中
  function setupHook() {
    const prevHook = window.ogStep1AfterFill;
    window.ogStep1AfterFill = function() {
      if (typeof prevHook === 'function') {
        try { prevHook(); } catch (e) { console.error(e); }
      }
      updateOgSummary();
      const isAllEmpty = CONTENT_FIELDS.every(id => !($(id) ? $(id).value.trim() : ''));
      if (isAllEmpty) {
        hideUndoToast();
      }
    };
  }

  // 10. 初始化模块
  function init() {
    syncHeaderHeight();
    window.addEventListener('resize', syncHeaderHeight);
    window.addEventListener('scroll', adjustUndoToastPosition, { passive: true });
    window.addEventListener('resize', adjustUndoToastPosition, { passive: true });

    setupHook();

    // 监听输入事件实时更新摘要条；真实用户手动输入（isTrusted）立即隐藏撤销 Toast
    SNAPSHOT_FIELDS.forEach(id => {
      const el = $(id);
      if (el) {
        el.addEventListener('input', (e) => {
          updateOgSummary();
          if (id === 'og_genre') {
            handleGenreChange();
          }
          if (e && e.isTrusted) {
            hideUndoToast();
          }
        });
        el.addEventListener('change', (e) => {
          if (e && e.isTrusted) {
            hideUndoToast();
          }
        });
      }
    });

    // 监听清空表单按钮
    const clearBtn = $('btn_clear_og');
    if (clearBtn) {
      clearBtn.addEventListener('click', () => {
        setTimeout(() => {
          const isAllEmpty = CONTENT_FIELDS.every(id => !($(id) ? $(id).value.trim() : ''));
          if (isAllEmpty) {
            hideUndoToast();
          }
        }, 50);
      });
    }

    // 监听题材药丸点击
    const pillsGenreWrap = $('og_genre_pills');
    if (pillsGenreWrap) {
      pillsGenreWrap.addEventListener('click', (e) => {
        const pill = e.target.closest('.tag-pill');
        if (pill) {
          setTimeout(() => {
            updateOgSummary();
            handleGenreChange();
          }, 10);
        }
      });
    }

    // 捕获阶段拦截：灵感卡片网格点击
    const pillsWrap = $('og_trope_pills');
    if (pillsWrap) {
      pillsWrap.addEventListener('click', (e) => {
        const pill = e.target.closest('.trope-pill');
        if (pill) {
          handleTropeApplyCapture(e);
        }
      }, true);
    }

    // 捕获阶段拦截：随机灵感按钮
    const randBtn = $('btn_random_trope');
    if (randBtn) {
      randBtn.addEventListener('click', (e) => {
        handleTropeApplyCapture(e);
      }, true);
    }

    // 捕获阶段拦截：下一步按钮点击校验
    const nextBtn = $('btn_step1_next');
    if (nextBtn) {
      nextBtn.addEventListener('click', (e) => {
        if (!checkStep1Valid()) {
          e.preventDefault();
          e.stopImmediatePropagation();
          showStep1InlineTip();
          const setEl = $('og_setting');
          if (setEl) setEl.focus();
          return;
        }
        hideStep1InlineTip();
        hideUndoToast();
      }, true);
    }

    // 换一批按钮点击隐藏题材提示条
    const refreshBtn = $('btn_refresh_tropes');
    if (refreshBtn) {
      refreshBtn.addEventListener('click', () => {
        hideGenreHintBar();
      });
    }

    // 撤销按钮点击绑定
    const undoBtn = $('btn_og2_undo');
    if (undoBtn) {
      undoBtn.onclick = () => {
        if (lastSnapshot) {
          restoreSnapshot(lastSnapshot);
          lastSnapshot = null;
        }
        hideUndoToast();
      };
    }

    // 撤销关闭按钮绑定
    const undoCloseBtn = $('btn_og2_undo_close');
    if (undoCloseBtn) {
      undoCloseBtn.onclick = hideUndoToast;
    }

    // 记录初始题材
    lastGenreVal = $('og_genre') ? $('og_genre').value.trim() : '';

    // 初始渲染一次
    updateOgSummary();
  }

  // 导出全局命名空间供测试与外部访问
  window.ogStep1Summary = {
    update: updateOgSummary,
    syncHeader: syncHeaderHeight,
    checkValid: checkStep1Valid,
    undo: function() {
      if (lastSnapshot) {
        restoreSnapshot(lastSnapshot);
        lastSnapshot = null;
        hideUndoToast();
      }
    },
    getLastSnapshot: function() {
      return lastSnapshot;
    }
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
