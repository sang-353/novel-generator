// static/js/og_refine.js - 原创小说生成第 1 步输入框字数统计与 AI 辅助写作管理
(function() {
  'use strict';

  function countWords(str) {
    if (!str) return 0;
    // 统计中文汉字、全角标点、英文单词与非空字符
    return str.replace(/\s+/g, '').length;
  }

  function updateWordCounts() {
    const settingInp = $('og_setting');
    const storylineInp = $('og_storyline');
    const settingCount = $('txt_setting_word_count');
    const storylineCount = $('txt_storyline_word_count');

    if (settingInp && settingCount) {
      settingCount.textContent = `${countWords(settingInp.value)} 字`;
    }
    if (storylineInp && storylineCount) {
      storylineCount.textContent = `${countWords(storylineInp.value)} 字`;
    }
  }

  async function requestRefine(payload, signal) {
    const opt = {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal,
    };
    const authTk = typeof webAccessToken === 'function' ? webAccessToken() : '';
    if (authTk) opt.headers['Authorization'] = 'Bearer ' + authTk;
    const path = typeof withToken === 'function' ? withToken('/api/refine-field') : '/api/refine-field';
    const r = await fetch(path, opt);
    const data = await r.json().catch(() => ({}));
    if (r.status === 401 || data.auth_required) {
      if (typeof showWebAuthModal === 'function') showWebAuthModal();
      const err = new Error(data.error || '需要全站访问口令');
      err.auth_required = true;
      throw err;
    }
    if (!r.ok) {
      const err = new Error(data.error || ('请求失败 ' + r.status));
      err.status = r.status;
      throw err;
    }
    return data;
  }

  // 辅助写作状态控制器（针对 setting 与 storyline 独立实例化）
  class RefineController {
    constructor(field) {
      this.field = field; // 'setting' | 'storyline'
      this.state = 'idle'; // 'idle' | 'loading' | 'review'
      this.originalText = '';
      this.modifiedText = '';
      this.currentVersion = 'new';
      this.abortController = null;
      this.activeActionBtn = null;

      // DOM 元素引用
      this.textarea = $(field === 'setting' ? 'og_setting' : 'og_storyline');
      this.errBanner = $(field === 'setting' ? 'og_setting_err' : 'og_storyline_err');
      this.errMsg = $(field === 'setting' ? 'og_setting_err_msg' : 'og_storyline_err_msg');
      this.btnErrClose = $(field === 'setting' ? 'btn_setting_err_close' : 'btn_storyline_err_close');

      this.toolbar = $(field === 'setting' ? 'og_setting_toolbar' : 'og_storyline_toolbar');
      this.btnRegen = $(field === 'setting' ? 'btn_setting_regen' : 'btn_storyline_regen');
      this.btnPolish = $(field === 'setting' ? 'btn_setting_polish' : 'btn_storyline_polish');
      this.btnExpand = $(field === 'setting' ? 'btn_setting_expand' : 'btn_storyline_expand');
      this.btnCancel = $(field === 'setting' ? 'btn_setting_cancel' : 'btn_storyline_cancel');

      this.reviewBar = $(field === 'setting' ? 'og_setting_review_bar' : 'og_storyline_review_bar');
      this.btnViewOrig = $(field === 'setting' ? 'btn_setting_view_orig' : 'btn_storyline_view_orig');
      this.btnViewNew = $(field === 'setting' ? 'btn_setting_view_new' : 'btn_storyline_view_new');
      this.btnAccept = $(field === 'setting' ? 'btn_setting_accept' : 'btn_storyline_accept');
      this.btnRevert = $(field === 'setting' ? 'btn_setting_revert' : 'btn_storyline_revert');

      this.bindEvents();
      this.updateButtonStates();
    }

    bindEvents() {
      if (this.textarea) {
        this.textarea.addEventListener('input', () => {
          this.updateButtonStates();
        });
      }

      if (this.btnErrClose) {
        this.btnErrClose.addEventListener('click', () => {
          this.hideError();
        });
      }

      if (this.btnRegen) {
        this.btnRegen.addEventListener('click', () => this.startRefine('regen', this.btnRegen));
      }
      if (this.btnPolish) {
        this.btnPolish.addEventListener('click', () => this.startRefine('polish', this.btnPolish));
      }
      if (this.btnExpand) {
        this.btnExpand.addEventListener('click', () => this.startRefine('expand', this.btnExpand));
      }
      if (this.btnCancel) {
        this.btnCancel.addEventListener('click', () => this.cancelRefine());
      }

      if (this.btnViewOrig) {
        this.btnViewOrig.addEventListener('click', () => this.showVariant('orig'));
      }
      if (this.btnViewNew) {
        this.btnViewNew.addEventListener('click', () => this.showVariant('new'));
      }
      if (this.btnAccept) {
        this.btnAccept.addEventListener('click', () => this.acceptReview());
      }
      if (this.btnRevert) {
        this.btnRevert.addEventListener('click', () => this.revertReview());
      }
    }

    updateButtonStates() {
      if (this.state === 'loading') return;
      if (!this.textarea) return;

      const textVal = this.textarea.value.trim();
      const genreVal = $('og_genre') ? $('og_genre').value.trim() : '';
      const titleVal = $('og_title') ? $('og_title').value.trim() : '';

      // regen: 题材或书名至少填一项
      if (this.btnRegen) {
        const canRegen = Boolean(genreVal || titleVal);
        this.btnRegen.disabled = !canRegen;
        if (!canRegen) {
          this.btnRegen.title = '请先选择题材或填写书名';
        } else {
          this.btnRegen.removeAttribute('title');
        }
      }

      // polish & expand: 需要有内容
      const hasContent = textVal.length > 0;
      if (this.btnPolish) {
        this.btnPolish.disabled = !hasContent;
        if (!hasContent) {
          this.btnPolish.title = '请先写一点内容';
        } else {
          this.btnPolish.removeAttribute('title');
        }
      }
      if (this.btnExpand) {
        this.btnExpand.disabled = !hasContent;
        if (!hasContent) {
          this.btnExpand.title = '请先写一点内容';
        } else {
          this.btnExpand.removeAttribute('title');
        }
      }
    }

    showError(msg) {
      if (this.errBanner && this.errMsg) {
        this.errMsg.textContent = msg;
        this.errBanner.style.display = 'flex';
      }
    }

    hideError() {
      if (this.errBanner) {
        this.errBanner.style.display = 'none';
      }
    }

    async startRefine(mode, actionBtn) {
      if (this.state === 'loading') return; // 防重复点击
      this.hideError();

      this.state = 'loading';
      this.activeActionBtn = actionBtn;
      this.originalText = this.textarea ? this.textarea.value : '';

      if (this.textarea) {
        this.textarea.readOnly = true;
        this.textarea.setAttribute('readonly', 'true');
        this.textarea.setAttribute('aria-busy', 'true');
        this.textarea.classList.add('og2-shimmer');
      }

      // 禁用同一栏内的按钮
      if (this.btnRegen) this.btnRegen.disabled = true;
      if (this.btnPolish) this.btnPolish.disabled = true;
      if (this.btnExpand) this.btnExpand.disabled = true;

      if (actionBtn) {
        const svg = actionBtn.querySelector('svg');
        if (svg) svg.classList.add('og2-spin');
      }
      if (this.btnCancel) {
        this.btnCancel.style.display = 'inline-flex';
      }

      this.abortController = new AbortController();

      const payload = {
        field: this.field,
        mode,
        genre: $('og_genre') ? $('og_genre').value.trim() : '',
        title: $('og_title') ? $('og_title').value.trim() : '',
        setting: $('og_setting') ? $('og_setting').value.trim() : '',
        storyline: $('og_storyline') ? $('og_storyline').value.trim() : '',
        provider_id: $('og_provider') ? $('og_provider').value : '',
      };

      try {
        const res = await requestRefine(payload, this.abortController.signal);
        this.modifiedText = res.text || '';
        this.enterReview();
      } catch (err) {
        if (err.name === 'AbortError') {
          // 用户手动取消，恢复原文本并回到 idle
          if (this.textarea) this.textarea.value = this.originalText;
          this.resetToIdle();
        } else {
          this.showError(err.message || '请求失败，请稍后重试');
          this.resetToIdle();
        }
      }
    }

    cancelRefine() {
      if (this.abortController) {
        this.abortController.abort();
      }
    }

    enterReview() {
      this.state = 'review';
      this.cleanupLoadingVisuals();

      if (this.toolbar) this.toolbar.style.display = 'none';
      if (this.reviewBar) this.reviewBar.style.display = 'inline-flex';

      this.currentVersion = 'new';
      if (this.textarea) {
        this.textarea.value = this.modifiedText;
        this.textarea.dispatchEvent(new Event('input', { bubbles: true }));
      }

      this.updateSegDisplay();
      updateWordCounts();
    }

    showVariant(targetVer) {
      if (this.currentVersion === targetVer) return;

      // 如果当前是新版，且用户在新版上手动编辑过，先暂存修改
      if (this.currentVersion === 'new' && this.textarea) {
        this.modifiedText = this.textarea.value;
      }

      this.currentVersion = targetVer;
      if (this.textarea) {
        this.textarea.value = targetVer === 'orig' ? this.originalText : this.modifiedText;
        this.textarea.dispatchEvent(new Event('input', { bubbles: true }));
      }

      this.updateSegDisplay();
      updateWordCounts();
    }

    updateSegDisplay() {
      if (this.btnViewOrig && this.btnViewNew) {
        if (this.currentVersion === 'orig') {
          this.btnViewOrig.classList.add('active');
          this.btnViewOrig.setAttribute('aria-pressed', 'true');
          this.btnViewNew.classList.remove('active');
          this.btnViewNew.setAttribute('aria-pressed', 'false');
        } else {
          this.btnViewNew.classList.add('active');
          this.btnViewNew.setAttribute('aria-pressed', 'true');
          this.btnViewOrig.classList.remove('active');
          this.btnViewOrig.setAttribute('aria-pressed', 'false');
        }
      }
    }

    acceptReview() {
      // 保留当前 textarea 中展示的内容（无论是新版、二次编辑版还是原版）
      if (this.textarea) {
        this.textarea.dispatchEvent(new Event('input', { bubbles: true }));
      }
      if (typeof toast === 'function') toast('已保留当前内容');
      this.resetToIdle();
    }

    revertReview() {
      // 撤回回最初的 originalText
      if (this.textarea) {
        this.textarea.value = this.originalText;
        this.textarea.dispatchEvent(new Event('input', { bubbles: true }));
      }
      if (typeof toast === 'function') toast('已撤回原版');
      this.resetToIdle();
    }

    cleanupLoadingVisuals() {
      if (this.textarea) {
        this.textarea.readOnly = false;
        this.textarea.removeAttribute('readonly');
        this.textarea.removeAttribute('aria-busy');
        this.textarea.classList.remove('og2-shimmer');
      }
      if (this.activeActionBtn) {
        const svg = this.activeActionBtn.querySelector('svg');
        if (svg) svg.classList.remove('og2-spin');
        this.activeActionBtn = null;
      }
      if (this.btnCancel) {
        this.btnCancel.style.display = 'none';
      }
    }

    resetToIdle() {
      this.state = 'idle';
      this.abortController = null;
      this.cleanupLoadingVisuals();

      if (this.reviewBar) this.reviewBar.style.display = 'none';
      if (this.toolbar) this.toolbar.style.display = 'flex';

      this.updateButtonStates();
      updateWordCounts();
    }
  }

  let settingCtrl = null;
  let storylineCtrl = null;

  function updateAllButtonStates() {
    if (settingCtrl) settingCtrl.updateButtonStates();
    if (storylineCtrl) storylineCtrl.updateButtonStates();
  }

  // 暴露全局 hook 供程序化写入后调用（灵感卡片应用、草稿恢复、表单清空）
  window.ogStep1AfterFill = function() {
    updateWordCounts();
    updateAllButtonStates();
  };

  function initOgRefine() {
    on('og_setting', 'input', updateWordCounts);
    on('og_storyline', 'input', updateWordCounts);

    settingCtrl = new RefineController('setting');
    storylineCtrl = new RefineController('storyline');

    // 监听书名与题材变化，实时更新换个设定/主线按钮状态
    on('og_title', 'input', updateAllButtonStates);
    on('og_genre', 'input', updateAllButtonStates);

    // 题材芯片与候选书名事件委托：延迟到微任务刷新
    const genreWrap = $('og_genre_pills');
    if (genreWrap) {
      genreWrap.addEventListener('click', () => {
        queueMicrotask(() => {
          updateWordCounts();
          updateAllButtonStates();
        });
      });
    }

    const titleList = $('og_title_list');
    if (titleList) {
      titleList.addEventListener('click', () => {
        queueMicrotask(() => {
          updateWordCounts();
          updateAllButtonStates();
        });
      });
    }

    // 初始执行一次统计与按钮状态计算
    updateWordCounts();
    updateAllButtonStates();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initOgRefine);
  } else {
    initOgRefine();
  }
})();
