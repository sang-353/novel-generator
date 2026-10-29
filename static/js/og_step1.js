/**
 * static/js/og_step1.js
 * 原创小说生成第 1 步增强：作品卡摘要条、完成度、灵感应用反馈与撤销、下一步校验
 */

(function() {
  'use strict';

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

  // 2. 更新摘要条内容与完成度
  let lastAnnouncedProgress = '';

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
  }

  // 3. 挂载到 window.ogStep1AfterFill 链路中（不覆盖原有钩子）
  function setupHook() {
    const prevHook = window.ogStep1AfterFill;
    window.ogStep1AfterFill = function() {
      if (typeof prevHook === 'function') {
        try { prevHook(); } catch (e) { console.error(e); }
      }
      updateOgSummary();
    };
  }

  // 4. 初始化模块
  function init() {
    syncHeaderHeight();
    window.addEventListener('resize', syncHeaderHeight);

    setupHook();

    // 监听输入事件实时更新摘要条
    ['og_genre', 'og_title', 'og_setting', 'og_storyline'].forEach(id => {
      const el = $(id);
      if (el) {
        el.addEventListener('input', () => {
          updateOgSummary();
        });
      }
    });

    // 初始执行一次
    updateOgSummary();
  }

  // 导出全局命名空间供测试与外部访问
  window.ogStep1Summary = {
    update: updateOgSummary,
    syncHeader: syncHeaderHeight,
    getCount: function() {
      return lastAnnouncedProgress;
    }
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
