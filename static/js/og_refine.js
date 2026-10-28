// static/js/og_refine.js - 原创小说生成第 1 步输入框字数统计与辅助写作管理
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

  // 暴露全局 hook 供程序化写入后调用（灵感卡片应用、草稿恢复、表单清空）
  window.ogStep1AfterFill = function() {
    updateWordCounts();
  };

  function initOgRefine() {
    on('og_setting', 'input', updateWordCounts);
    on('og_storyline', 'input', updateWordCounts);

    // 题材芯片与候选书名事件委托：延迟到微任务刷新
    const genreWrap = $('og_genre_pills');
    if (genreWrap) {
      genreWrap.addEventListener('click', () => {
        queueMicrotask(updateWordCounts);
      });
    }

    const titleList = $('og_title_list');
    if (titleList) {
      titleList.addEventListener('click', () => {
        queueMicrotask(updateWordCounts);
      });
    }

    // 初始执行一次统计（如草稿或初始值）
    updateWordCounts();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initOgRefine);
  } else {
    initOgRefine();
  }
})();
