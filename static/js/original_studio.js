// static/js/original_studio.js - 原创小说创作 Studio 前端交互控制中枢 (v2.0 · 稿纸工坊适配版)
(function() {
  'use strict';

  // =========================================================================
  // 1. 全局状态与预设配置
  // =========================================================================
  const state = {
    novelId: '',
    spec: null,
    runtime: null,
    activeStation: 1,
    lockedFields: new Set(),
    fieldHistories: {}, // field_path -> [{ time, val }, ...]
    activeJobId: null,
    eventSource: null,
    lastBeats: [],
    chainedCancelled: false,
    extraCharCounter: 2,
    extraVolCounter: 2,
    currentStageIndex: 1,
    drawerStageIndex: 1,
    checkpointStageIndex: 1,
    isStagePaused: false,
    runnerTotalChapters: 0,
    isRestoring: false,
    draftRestored: false,
  };

  const OG_DRAFT_KEY = 'novel_og_studio_draft_v2';

  // 预设样例库（供创作者快速对比体验言情与科幻等全题材中立能力）
  const PRESETS = {
    romance: {
      meta: { title: "微醺心跳定律", genre: "都市言情", selected_trope: "假戏真做：合租室友的心跳契约" },
      ideation: {
        logline: "习惯用理智与配方丈量一切的高冷调香师，偶然与热情直率但生活一团糟的绘本作家成为合租室友；在一场关于‘气味与心动’的假扮情侣合约中，两人逐步解开心结，确认了彼此是唯一的解药。",
        hook: "“气味嗅觉通感 + 极致暧昧拉扯”。男主是嗅觉超凡却情感钝感的调香师，女主是感知丰富却嗅觉有创伤的画师；以香气为暗号，逐步试探彼此底线。",
        reader_expectation: "追求高糖微酸的沉浸式恋爱代入感、成年人克制而汹涌的心动细节、相互治愈的精神共振与温馨治愈的日常烟火气。",
        theme: "真正的相爱不是成为无懈可击的完美伴侣，而是敢于在对方面前袒露不完美的软肋。",
        tone: "轻快幽默中带着细腻酸甜，对白自然生活化，多用意象白描心动瞬间；第三人称双重视角。",
      },
      worldview: {
        background: "老城区梧桐树下的两居室老洋房；男主书房陈列着 300 种冷门香料浸膏；女主阳台堆满多肉植物与涂鸦画板。",
        special_rules: "【职业与心理约束】：男主家族企业对调香师有严苛的“感情中立”职业伦理，认为恋爱会让情绪波动破坏嗅觉灵敏度；女主因童年火灾创伤对焦糊味有应激反应。",
        taboos: "不可在合约期内假戏真做动真感情。",
      },
      protagonist: {
        id: "char_protagonist",
        name: "陆承舟",
        role: "Lu Chengzhou",
        want: "研发出失传的‘第七号白夜’香水，保住独立工作室经营权",
        need: "打破冰冷理性防线，学会向信任的人表达真实情感",
        flaw: "童年被家族视作没有感情的调香机器，害怕被抛弃",
        arc: "绝不用廉价工业香精伪造手作香，尊重每一个生命的嗅觉记忆",
      },
      characters: [
        {
          id: "char_female_lead",
          name: "姜幼柠",
          en_name: "Jiang Youning",
          relation_type: "cp_love",
          role_desc: "乐天随性却坚韧，急需完成个人首部绘本出版以证明自己的创作价值",
          bond_or_conflict: "作息黑白颠倒、生活习惯大碰撞，但能精准捕捉男主隐藏的脆弱",
        }
      ],
      ending: {
        climax_vision: "男女主克服误会与家族干预，联手以属于两人的‘第七号白夜’香氛绘本赢得国际大奖；陆承舟在全城花期大典上公开告白，圆满HE。",
      },
      stages: [
        {
          stage_index: 1,
          title: "第一卷：试探同居与薄荷微风",
          expected_chapters: 10,
          anchors: {
            stage_goal: "两人被迫开启同居生活，在生活习惯的剧烈碰撞中订立三条‘互不越界’的合租契约。",
            main_obstacle: "男主严重的洁癖与感情防备，以及女主因手部神经痛面临绘本截稿危机。",
            climax_hook: "台风停电之夜，女主幽闭发作，男主打破理性第一次破例拥抱安抚，感情实质破冰。",
            transition_springboard: "男主母亲突然登门拜访，为了应对危机，男主主动提议签署为期三个月的‘假扮情侣’协议。",
          }
        },
        {
          stage_index: 2,
          title: "第二卷：契约情侣与香调升温",
          expected_chapters: 12,
          anchors: {
            stage_goal: "以情侣身份出席艺术展，在公开场合高甜互动逐渐弄假成真",
            climax_hook: "雨中露天酒会初吻，假戏真做情感彻底失控",
          }
        }
      ]
    },
    fantasy: {
      meta: { title: "赛博道祖", genre: "科幻未来", selected_trope: "底层义眼走私犯与机械道印" },
      ideation: {
        logline: "九龙城寨底层义眼技师在回收废弃芯片时，意外激活了上古‘太上洞玄九转机魂道印’；在巨型跨国赛博宗门的高压奴役下，他以符箓重构神经突触，掀起一场涤荡星海的机械飞升革命。",
        hook: "用电磁线圈刻画雷法符箓，赛博义体暗藏金丹大道；物理超度赛博仙尊，算力与道法硬核碰撞。",
        reader_expectation: "硬核设定推演、底层逆袭的反差爽点、弑神破局的史诗震撼感。",
        theme: "生命意志与冷酷资本算力的终极较量——人不是冰冷的数据零件。",
        tone: "第三人称限制视角，硬冷写实，兼具古雅道韵与赛博霓虹质感。",
      },
      worldview: {
        background: "霓虹阴雨永不休止的九龙地底八百米，空气中弥漫着机油与廉价合成香精的酸涩，巨型全息三清巨像俯瞰着贫民窟。",
        special_rules: "香火即算力，飞升即上传意识至太虚母矩阵；违规改装灵根者受天基神雷劫灭。",
        taboos: "严禁在母矩阵防火墙外私自推演天道算法。",
      },
      protagonist: {
        id: "char_protagonist",
        name: "陈拙",
        role: "Chen Zhuo",
        want: "积攒足够的太虚币为病危的妹妹赎回完整原生大脑",
        need: "打破顺从宿命的奴性，觉醒带领底层修士抗衡天道算力的道祖之志",
        flaw: "冷漠利己、重度义体排异反应引发的神经剧痛与偏执",
        arc: "绝不出卖同伴魂魄换取飞升算力，以凡胎肉骨硬抗神霄天网",
      },
      characters: [
        {
          id: "char_rival",
          name: "司徒渊",
          en_name: "Situ Yuan",
          relation_type: "rival_antagonist",
          role_desc: "神霄重工集团执法长老，奉命清洗黑市走私节点",
          bond_or_conflict: "执着于抓获陈拙夺回九转道印，却在交手中逐渐动摇对母矩阵的绝对信仰",
        }
      ],
      ending: {
        climax_vision: "近地轨道太虚母矩阵核心，陈拙肉身崩解以纯粹意识引爆天基电磁风暴，彻底重置神霄算力天网，为众生夺回自由意志。",
      },
      stages: [
        {
          stage_index: 1,
          title: "第一卷：铁锈城寨与走私符箓",
          expected_chapters: 8,
          anchors: {
            stage_goal: "在神霄执法队的扫荡中隐匿行踪并成功凝练机械筑基。",
            main_obstacle: "义体排异剧痛、资金匮乏与走私黑警的双重追查。",
            climax_hook: "黑市地下擂台赛上以自制等离子掌心雷击溃筑基期机甲修士。",
            transition_springboard: "夺得神霄天宫通行密匙，被迫踏上偷渡星港之旅。",
          }
        },
        {
          stage_index: 2,
          title: "第二卷：星港潜行与算力夺舍",
          expected_chapters: 10,
          anchors: {
            stage_goal: "潜入神霄外门，窃取灵根防火墙核心源码破解妹妹脑锁。",
            climax_hook: "在太虚幻境试炼中反向夺舍执法长老的量子神识。",
          }
        }
      ]
    }
  };

  // =========================================================================
  // 2. DOM 元素定位与辅助函数
  // =========================================================================
  function getEl(id) {
    return document.getElementById(id);
  }

  function safeVal(id, fallback = '') {
    const el = getEl(id);
    return el ? (el.value !== undefined ? el.value : el.textContent) : fallback;
  }

  function safeText(id, fallback = '') {
    const el = getEl(id);
    return el ? (el.textContent || fallback) : fallback;
  }

  function setElVal(id, val) {
    const el = getEl(id);
    if (el) el.value = val;
  }

  function setElText(id, text) {
    const el = getEl(id);
    if (el) el.textContent = text;
  }

  function esc(t) {
    return window.escapeHtml ? window.escapeHtml(String(t == null ? '' : t))
      : String(t == null ? '' : t).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }

  function currentProviderId() {
    return safeVal('og_provider', '') || undefined;
  }

  // =========================================================================
  // 3. 工位导航、分步切换与当前攻坚卷状态管理
  // =========================================================================
  function getFormStages() {
    const stages = [];
    const st1Title = safeText('st1_title').trim();
    if (st1Title) stages.push({ stage_index: 1, title: st1Title });
    const st2Title = safeText('st2_title').trim();
    if (st2Title) stages.push({ stage_index: 2, title: st2Title });
    document.querySelectorAll('#og_route_list .og-extra-vol').forEach((volEl) => {
      const idx = parseInt(volEl.dataset.stage || '0', 10);
      const tEl = volEl.querySelector('.og-vol-title');
      if (idx > 2) stages.push({ stage_index: idx, title: tEl ? tEl.textContent.trim() : `第 ${idx} 卷` });
    });
    return stages.length ? stages : [{ stage_index: 1, title: '第一卷：开篇启程' }];
  }

  function syncStageSelector() {
    const sel = getEl('st4_stage_sel');
    if (!sel) return;
    const stages = getFormStages();
    const valid = stages.some(s => s.stage_index === state.currentStageIndex);
    if (!valid) state.currentStageIndex = stages[0].stage_index;
    const html = stages.map(s =>
      `<option value="${s.stage_index}">第 ${s.stage_index} 卷：${esc(s.title)}</option>`
    ).join('');
    if (sel._lastOptionsHtml !== html) {
      sel._lastOptionsHtml = html;
      sel.innerHTML = html;
    }
    sel.value = String(state.currentStageIndex);
    if (!sel._stageBound) {
      sel._stageBound = true;
      sel.addEventListener('change', () => {
        window.selectStage(parseInt(sel.value || '1', 10));
      });
    }
  }

  window.selectStage = function(stageIdx) {
    const idx = parseInt(stageIdx, 10) || 1;
    const changed = idx !== state.currentStageIndex;
    state.currentStageIndex = idx;
    if (changed) {
      if (state.eventSource) {
        try { state.eventSource.close(); } catch (e) { /* 忽略 */ }
        state.eventSource = null;
      }
      state.activeJobId = null;
      state.isStagePaused = false;
      const runnerView = getEl('stage_runner_view');
      const chkBox = getEl('box_checkpoint');
      if (runnerView) runnerView.style.display = 'none';
      if (chkBox) chkBox.style.display = 'none';
    }
    const stages = getFormStages();
    const cur = stages.find(s => s.stage_index === idx) || stages[0];
    if (cur) setElText('st4_cur_title', cur.title.replace('：', ' · '));
    setElText('st4_status_tag', `第 ${idx} 卷 · 节拍就绪`);

    document.querySelectorAll('#og_route_list .og-vol[data-stage]').forEach((volEl) => {
      const vIdx = parseInt(volEl.dataset.stage || '0', 10);
      const isCur = vIdx === idx;
      volEl.classList.toggle('is-current', isCur);
      volEl.classList.toggle('is-pending', !isCur);
      const pill = volEl.querySelector('.og-vol-meta .og-pill');
      if (pill) {
        pill.classList.toggle('is-now', isCur);
        pill.textContent = isCur ? '当前攻坚卷' : '待前卷完成';
      }
    });
    syncStageSelector();
    refreshOverview();
    saveOgDraft();
  };

  window.goToStep = function(stepNum, stageIdx) {
    if (stageIdx !== undefined && stageIdx !== null) {
      window.selectStage(stageIdx);
    }
    state.activeStation = stepNum;
    for (let i = 1; i <= 4; i++) {
      const tab = getEl(`step_tab_${i}`);
      const panel = getEl(`station_${i}`);
      if (tab) {
        tab.classList.toggle('active', i === stepNum);
        tab.classList.toggle('done', i < stepNum);
        tab.setAttribute('aria-current', i === stepNum ? 'step' : 'false');
      }
      if (panel) {
        panel.style.display = (i === stepNum) ? 'block' : 'none';
        if (i === stepNum) autosize(panel);
      }
    }
    if (stepNum === 4) syncStageSelector();
    updateSummaryBar();
    saveOgDraft();
    const sheet = getEl('og_sheet');
    if (sheet && sheet.getBoundingClientRect().top < 0) window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  function updateSummaryBar() {
    const title = safeVal('val_title') || (state.spec && state.spec.meta ? state.spec.meta.title : '未命名作品');
    const genre = safeVal('val_genre') || (state.spec && state.spec.meta ? state.spec.meta.genre : '未选题材');
    setElText('sum_title', `《${title}》`);
    setElText('sum_genre', genre);
    const curTitle = safeText(`st${state.currentStageIndex}_title`) || safeText('st1_title');
    if (curTitle) setElText('st4_cur_title', curTitle.replace('：', ' · '));
    syncStageSelector();
    updateCounts();
    refreshOverview();
  }

  // =========================================================================
  // 4. 题材药丸与灵感脑洞选择
  // =========================================================================
  window.selectGenre = function(btn) {
    if (!btn) return;
    const parent = btn.parentElement;
    if (parent) {
      parent.querySelectorAll('.og-chip').forEach(b => b.classList.remove('active'));
    }
    btn.classList.add('active');
    setElVal('val_genre', btn.textContent.trim());
    updateSummaryBar();
    saveOgDraft();
  };

  function syncGenreChips(genreText) {
    const chips = document.querySelectorAll('#station_1 .og-chip');
    let matched = false;
    chips.forEach(btn => {
      const t = btn.textContent.trim();
      const isMatch = genreText && (t === genreText || genreText.includes(t) || t.includes(genreText));
      btn.classList.toggle('active', Boolean(isMatch));
      if (isMatch) matched = true;
    });
    if (!matched && chips.length && genreText) {
      chips.forEach(btn => btn.classList.remove('active'));
    }
  }

  window.chooseTrope = function(card) {
    if (!card) return;
    const parent = card.parentElement;
    if (parent) {
      parent.querySelectorAll('.og-trope').forEach(c => c.classList.remove('active'));
    }
    card.classList.add('active');
    const titleEl = card.querySelector('h4');
    const descEl = card.querySelector('p');
    if (titleEl && descEl) {
      setElVal('selected_trope_val', `${titleEl.textContent.trim()}: ${descEl.textContent.trim()}`);
    }
    saveOgDraft();
  };

  window.clearTropeSelection = function() {
    const container = getEl('trope_cards_container');
    if (container) {
      container.querySelectorAll('.og-trope').forEach(c => c.classList.remove('active'));
    }
    setElVal('selected_trope_val', '');
    saveOgDraft();
    if (window.toast) window.toast('已取消灵感选择，进入纯自主自由构思模式');
  };

  window.randomTrope = function() {
    const cards = document.querySelectorAll('#trope_cards_container .og-trope');
    if (cards.length) {
      window.chooseTrope(cards[Math.floor(Math.random() * cards.length)]);
      if (window.toast) window.toast('已为您随机选用一个灵感脑洞');
    }
  };

  window.refreshTropes = async function() {
    const container = getEl('trope_cards_container');
    if (!container) return;
    const genre = safeVal('val_genre') || '都市言情';
    if (window.toast) window.toast('正在依据当前题材生成一批新灵感…');
    try {
      const res = await window.api('/api/suggest-tropes', 'POST', {
        genre,
        count: 3,
        provider_id: currentProviderId(),
      });
      const tropes = (res && res.tropes) ? res.tropes : [];
      if (!tropes.length) throw new Error('未返回灵感列表');
      container.innerHTML = tropes.slice(0, 3).map((tp, idx) => {
        const title = tp.label || tp.title || `新灵感 ${idx + 1}`;
        const desc = tp.storyline || tp.setting || '点击采用此脑洞继续创作';
        return `<div class="og-trope${idx === 0 ? ' active' : ''}" role="button" tabindex="0" onclick="chooseTrope(this)">
          <h4>${esc(title)}</h4><p>${esc(desc)}</p></div>`;
      }).join('');
      const firstCard = container.querySelector('.og-trope');
      if (firstCard) window.chooseTrope(firstCard);
      if (window.toast) window.toast('已为您刷新一批新灵感脑洞');
    } catch (err) {
      if (window.toast) window.toast(`刷新灵感失败: ${err.message}`);
    }
  };

  // =========================================================================
  // 5. 核心通用组件：SpecField 状态机与工具条联动
  // =========================================================================
  window.toggleDirective = function(fieldKey) {
    const bar = getEl(`dir_${fieldKey}`);
    if (bar) {
      bar.style.display = (bar.style.display === 'none' || !bar.style.display) ? 'flex' : 'none';
      if (bar.style.display === 'flex') {
        const inp = getEl(`dir_input_${fieldKey}`);
        if (inp) inp.focus();
      }
    }
  };

  window.toggleLock = function(fieldKey) {
    const btn = getEl(`lock_${fieldKey}`);
    const input = getEl(`val_${fieldKey}`);
    const willLock = !state.lockedFields.has(fieldKey);
    if (willLock) state.lockedFields.add(fieldKey); else state.lockedFields.delete(fieldKey);
    if (btn) {
      btn.classList.toggle('is-locked', willLock);
      btn.setAttribute('aria-pressed', String(willLock));
      btn.title = willLock ? '已锁定，点击解锁' : '锁定此字段';
    }
    if (input) input.readOnly = willLock;
    if (window.toast) window.toast(willLock
      ? `已锁定 [${fieldKey}]，推演与重写将保留此字段`
      : `已解锁 [${fieldKey}]，推演引擎可自适应更新`);
  };

  // 审阅面板：静态 HTML 里没有时按需创建，保证每个字段都能走完 重写→对比→保留/撤回
  function ensureReview(fieldPath) {
    let rev = getEl(`review_${fieldPath}`);
    if (rev) return rev;
    const input = getEl(`val_${fieldPath}`);
    if (!input) return null;
    rev = document.createElement('div');
    rev.id = `review_${fieldPath}`;
    rev.className = 'og-review';
    rev.innerHTML = `
      <div class="og-review-head"><span>AI 提议的新版本</span>
        <div class="og-review-actions">
          <button type="button" class="og-btn sm" data-act="reject" data-field="${esc(fieldPath)}">撤回</button>
          <button type="button" class="og-btn is-primary sm" data-act="accept" data-field="${esc(fieldPath)}">保留此版</button>
        </div></div>
      <div class="og-diff" id="diff_${esc(fieldPath)}"></div>`;
    input.insertAdjacentElement('afterend', rev);
    return rev;
  }

  window.triggerRefine = async function(fieldPath, mode) {
    if (state.lockedFields.has(fieldPath)) {
      if (window.toast) window.toast(`字段 [${fieldPath}] 已锁定，请先解锁后再重写或润色`);
      return;
    }

    const input = getEl(`val_${fieldPath}`);
    const currentVal = input ? input.value : '';
    const dirInput = getEl(`dir_input_${fieldPath}`);
    const userHint = (dirInput && dirInput.value) ? dirInput.value.trim() : '';

    if (mode === 'polish' && !currentVal.trim()) {
      if (window.toast) window.toast('请先填写一点内容再执行润色');
      return;
    }

    const reviewBar = ensureReview(fieldPath);
    const diffContainer = getEl(`diff_${fieldPath}`);
    const dirBar = getEl(`dir_${fieldPath}`);

    if (reviewBar) reviewBar.style.display = 'flex';
    if (diffContainer) diffContainer.innerHTML = `<span class="diff-hint">正在${mode === 'polish' ? '润色' : '重写'}，请稍候…</span>`;

    try {
      const payload = {
        novel_id: resolveNovelId('temp_book'),
        field_path: fieldPath,
        mode: mode,
        current_value: currentVal,
        user_hint: userHint,
        spec_context: collectSpecFromForm(),
        provider_id: currentProviderId(),
        candidates_count: 1,
      };

      const res = await window.api('/api/novel/original/refine-field', 'POST', payload);
      const candidates = (res.data && res.data.candidates) ? res.data.candidates : [];
      if (!candidates.length) throw new Error('模型未返回候选方案');

      const proposal = candidates[0];
      if (!state.fieldHistories[fieldPath]) state.fieldHistories[fieldPath] = [];
      state.fieldHistories[fieldPath].push({ time: new Date().toLocaleTimeString(), val: currentVal });

      renderDiffView(fieldPath, currentVal, proposal);
      if (dirBar) dirBar.style.display = 'none';
      if (dirInput) dirInput.value = '';

    } catch (err) {
      if (diffContainer) diffContainer.innerHTML = `<span class="diff-err">${mode === 'polish' ? '润色' : '重写'}失败：${esc(err.message)}。可再试一次，原内容未改动。</span>`;
      if (window.toast) window.toast(`精修异常: ${err.message}`);
    }
  };

  function renderDiffView(fieldPath, original, proposal) {
    const diffEl = getEl(`diff_${fieldPath}`);
    if (!diffEl) return;
    diffEl.innerHTML =
      (original ? `<span class="diff-old">${esc(original)}</span>` : '') +
      `<span class="diff-new" id="proposal_text_${esc(fieldPath)}">${esc(proposal)}</span>`;
  }

  window.acceptProposal = function(fieldPath) {
    const propEl = getEl(`proposal_text_${fieldPath}`);
    const input = getEl(`val_${fieldPath}`);
    const reviewBar = getEl(`review_${fieldPath}`);

    if (propEl && input) {
      input.value = propEl.textContent.trim();
      input.dispatchEvent(new Event('input', { bubbles: true }));
      if (reviewBar) reviewBar.style.display = 'none';
      if (window.toast) window.toast(`已采纳新版 [${fieldPath}]`);
    }
  };

  window.rejectProposal = function(fieldPath) {
    const reviewBar = getEl(`review_${fieldPath}`);
    if (reviewBar) reviewBar.style.display = 'none';
    if (window.toast) window.toast('已撤销本次提议，保留原内容');
  };
  // 兼容旧模板里的命名
  window.acceptDiff = window.acceptDiff || window.acceptProposal;
  window.revertDiff = window.revertDiff || window.rejectProposal;
  window.submitDirective = window.submitDirective || function(f) { window.triggerRefine(f, 'rewrite'); };

  // =========================================================================
  // 5.5 人物卡与分卷卡扩展操作
  // =========================================================================
  window.addCharacterCard = function(charData, silent) {
    const btn = getEl('btn_add_og_char');
    const sec = btn ? btn.closest('.og-section') : null;
    if (!sec) return;
    state.extraCharCounter += 1;
    const idx = state.extraCharCounter;
    const cName = (charData && charData.name) ? charData.name : `新登场角色 ${idx}`;
    const cRelType = (charData && charData.relation_type) ? charData.relation_type : 'ally_friend';
    const cMot = (charData && charData.role_desc) ? charData.role_desc : '';
    const cRel = (charData && charData.bond_or_conflict) ? charData.bond_or_conflict : '';

    const card = document.createElement('div');
    card.className = 'og-char is-support og-extra-char';
    card.dataset.charIdx = String(idx);
    card.innerHTML = `
      <div class="og-mono" aria-hidden="true">${esc((cName.trim() || '配')[0])}</div>
      <div>
        <div class="og-char-head">
          <div>
            <div class="og-char-name"><input type="text" class="og-input og-char-name-inp" value="${esc(cName)}" style="font-size:18px;font-weight:700;padding:4px 8px;width:auto;"></div>
            <div class="og-char-role">
              <select class="og-select-inline" aria-label="角色定位">
                <option value="ally_friend" ${cRelType === 'ally_friend' ? 'selected' : ''}>好友 / 搭档</option>
                <option value="cp_love" ${cRelType === 'cp_love' ? 'selected' : ''}>恋爱 / CP 对象</option>
                <option value="rival_antagonist" ${cRelType === 'rival_antagonist' ? 'selected' : ''}>竞争对手 / 宿敌</option>
                <option value="mentor" ${cRelType === 'mentor' ? 'selected' : ''}>导师 / 长辈</option>
              </select>
            </div>
          </div>
          <div class="og-tools">
            <button type="button" class="og-tool" data-act="remove-char">移除</button>
          </div>
        </div>
        <div class="og-kv">
          <div><div class="og-k" style="--c:#7A8296"><i></i>核心性格与驱动力<small>Motivation</small></div><textarea class="og-input og-char-mot" rows="2" placeholder="描述角色性格与行动目标…">${esc(cMot)}</textarea></div>
          <div><div class="og-k" style="--c:#7A8296"><i></i>与主角的互动焦点<small>Relation</small></div><textarea class="og-input og-char-rel" rows="2" placeholder="描述与主角的羁绊或冲突点…">${esc(cRel)}</textarea></div>
        </div>
      </div>`;
    sec.appendChild(card);
    autosize(card);
    const nameInp = card.querySelector('.og-char-name-inp');
    if (nameInp) {
      nameInp.addEventListener('input', () => {
        const mono = card.querySelector('.og-mono');
        if (mono) mono.textContent = (nameInp.value.trim() || '配')[0];
      });
      if (!silent) nameInp.focus();
    }
    if (!silent && window.toast) window.toast('已新增一张角色卡片');
  };

  window.refineCharacterCard = async function(charKey, mode) {
    const isMain = charKey === 'char1';
    const targetId = isMain ? 'c1_want' : 'c2_mot';
    const targetEl = getEl(targetId);
    if (!targetEl) return;
    const currentVal = targetEl.value || '';
    if (mode === 'polish' && !currentVal.trim()) {
      if (window.toast) window.toast('请先填写人物设定后再润色');
      return;
    }
    if (window.toast) window.toast(`正在${mode === 'polish' ? '润色' : '重写'}人物设定…`);
    try {
      const res = await window.api('/api/novel/original/refine-field', 'POST', {
        novel_id: resolveNovelId('temp_book'),
        field_path: isMain ? 'protagonist.want' : 'characters[0].role_desc',
        mode: mode || 'polish',
        current_value: currentVal,
        spec_context: collectSpecFromForm(),
        provider_id: currentProviderId(),
        candidates_count: 1,
      });
      const candidates = (res.data && res.data.candidates) ? res.data.candidates : [];
      if (!candidates.length) throw new Error('模型未返回候选方案');
      targetEl.value = candidates[0];
      targetEl.dispatchEvent(new Event('input', { bubbles: true }));
      if (window.toast) window.toast(`已完成人物设定${mode === 'polish' ? '润色' : '重写'}`);
    } catch (err) {
      if (window.toast) window.toast(`人物精修失败: ${err.message}`);
    }
  };

  window.addVolumeStage = function(stageData, silent) {
    const route = getEl('og_route_list');
    if (!route) return;
    state.extraVolCounter += 1;
    const idx = (stageData && stageData.stage_index) ? parseInt(stageData.stage_index, 10) : state.extraVolCounter;
    if (idx > state.extraVolCounter) state.extraVolCounter = idx;
    const vTitle = (stageData && stageData.title) ? stageData.title : `第${idx}卷：待规划新篇章`;
    const vCh = (stageData && stageData.expected_chapters) ? stageData.expected_chapters : 10;
    const anchors = (stageData && stageData.anchors) ? stageData.anchors : {};
    const vGoal = anchors.stage_goal || '推进主线矛盾升级，开启全新剧情舞台。';
    const vClimax = anchors.climax_hook || '卷末揭示核心秘密，完成阶段性局势反转。';

    const vol = document.createElement('div');
    vol.className = 'og-vol is-pending og-extra-vol';
    vol.dataset.stage = String(idx);
    vol.innerHTML = `
      <span class="og-vol-node"></span>
      <div class="og-vol-head">
        <div>
          <div class="og-vol-title" id="st${idx}_title">${esc(vTitle)}</div>
          <div class="og-vol-meta"><span class="og-pill">待前卷完成</span><span>预估 ${esc(vCh)} 章 · 约 ${Math.round(vCh * 2.5) / 10} 万字</span></div>
        </div>
        <div class="og-actions">
          <button type="button" class="og-btn sm" data-act="edit-vol" data-stage="${idx}">编辑锚点</button>
          <button type="button" class="og-btn is-primary sm" onclick="goToStep(4, ${idx})">去写作台</button>
          <button type="button" class="og-tool" data-act="remove-vol">移除</button>
        </div>
      </div>
      <div class="og-anchors">
        <div class="og-anchor" style="--c:#3B5BDB"><b>核心目标</b><p id="st${idx}_a1">${esc(vGoal)}</p></div>
        <div class="og-anchor" style="--c:#A86A0C"><b>高潮引爆点</b><p id="st${idx}_a3">${esc(vClimax)}</p></div>
      </div>`;
    route.appendChild(vol);
    syncStageSelector();
    if (!silent && window.toast) window.toast(`已新增第 ${idx} 卷阶段`);
  };

  window.rewriteStageAnchors = async function(stageIdx) {
    const st = stageIdx || 1;
    const goalEl = getEl(`st${st}_a1`);
    const currentGoal = goalEl ? goalEl.textContent.trim() : '';
    if (window.toast) window.toast('正在重新推演本卷锚点…');
    try {
      const res = await window.api('/api/novel/original/refine-field', 'POST', {
        novel_id: resolveNovelId('temp_book'),
        field_path: `stages[${st - 1}].anchors.stage_goal`,
        mode: 'rewrite',
        current_value: currentGoal,
        spec_context: collectSpecFromForm(),
        provider_id: currentProviderId(),
        candidates_count: 1,
      });
      const candidates = (res.data && res.data.candidates) ? res.data.candidates : [];
      if (!candidates.length) throw new Error('模型未返回新锚点');
      if (goalEl) goalEl.textContent = candidates[0];
      updateSummaryBar();
      if (window.toast) window.toast('已更新本卷阶段核心目标锚点');
    } catch (err) {
      if (window.toast) window.toast(`锚点推演失败: ${err.message}`);
    }
  };

  window.editStageAnchors = function(stageIdx, btnEl) {
    const st = stageIdx || 1;
    const card = btnEl ? btnEl.closest('.og-vol') : null;
    if (!card) return;
    const editableEls = card.querySelectorAll('.og-vol-title, .og-anchor p');
    const editing = card.dataset.editing === '1';
    if (editing) {
      card.dataset.editing = '0';
      editableEls.forEach(el => {
        el.contentEditable = 'false';
        el.style.outline = '';
        el.style.background = '';
        el.style.padding = '';
        el.style.borderRadius = '';
      });
      if (btnEl) btnEl.textContent = '编辑锚点';
      updateSummaryBar();
      saveOgDraft();
      if (window.toast) window.toast(`第 ${st} 卷锚点编辑已保存`);
    } else {
      card.dataset.editing = '1';
      editableEls.forEach(el => {
        el.contentEditable = 'true';
        el.style.outline = '1px dashed var(--accent)';
        el.style.background = 'var(--accent-soft)';
        el.style.padding = '3px 6px';
        el.style.borderRadius = '6px';
      });
      if (btnEl) btnEl.textContent = '完成编辑';
      if (editableEls[0]) editableEls[0].focus();
      if (window.toast) window.toast('已进入就地编辑模式，直接修改文本后点“完成编辑”即可');
    }
  };

  // =========================================================================
  // 6. 表单收集与设定集同步（完全匹配新版稿纸工坊 DOM ID）
  // =========================================================================
  function collectSpecFromForm() {
    const title = safeVal('val_title').trim() || '未命名小说';
    const genre = safeVal('val_genre').trim() || '都市言情';
    const selectedTrope = safeVal('selected_trope_val').trim() || null;

    const characters = [];
    const c2Name = safeText('c2_name_badge').trim();
    const c2RelSel = getEl('c2_relation_sel');
    if (c2Name || safeVal('c2_mot') || safeVal('c2_rel')) {
      characters.push({
        id: 'char_key_1',
        name: c2Name || '关键关系人',
        relation_type: c2RelSel ? c2RelSel.value : 'cp_love',
        role_desc: safeVal('c2_mot', ''),
        bond_or_conflict: safeVal('c2_rel', ''),
      });
    }
    document.querySelectorAll('#station_2 .og-extra-char').forEach((card, i) => {
      const nInp = card.querySelector('.og-char-name-inp');
      const rSel = card.querySelector('.og-select-inline');
      const motEl = card.querySelector('.og-char-mot');
      const relEl = card.querySelector('.og-char-rel');
      characters.push({
        id: `char_extra_${i + 2}`,
        name: nInp ? nInp.value.trim() : `配角${i + 2}`,
        relation_type: rSel ? rSel.value : 'ally_friend',
        role_desc: motEl ? motEl.value : '',
        bond_or_conflict: relEl ? relEl.value : '',
      });
    });

    const stages = [
      {
        stage_index: 1,
        title: safeText('st1_title').trim() || '第一卷：开篇启程',
        expected_chapters: 6,
        anchors: {
          stage_goal: safeText('st1_a1').trim() || '建立核心开局冲突与人物关系',
          main_obstacle: safeText('st1_a2').trim() || '',
          climax_hook: safeText('st1_a3').trim() || '',
          transition_springboard: safeText('st1_a4').trim() || '',
        }
      }
    ];
    const st2Title = safeText('st2_title').trim();
    if (st2Title) {
      stages.push({
        stage_index: 2,
        title: st2Title,
        expected_chapters: 8,
        anchors: {
          stage_goal: safeText('st2_a1').trim() || '',
          main_obstacle: '',
          climax_hook: safeText('st2_a3').trim() || '',
          transition_springboard: '',
        }
      });
    }
    document.querySelectorAll('#og_route_list .og-extra-vol').forEach((volEl) => {
      const idx = parseInt(volEl.dataset.stage || '3', 10);
      const tEl = volEl.querySelector('.og-vol-title');
      const pEls = volEl.querySelectorAll('.og-anchor p');
      stages.push({
        stage_index: idx,
        title: tEl ? tEl.textContent.trim() : `第 ${idx} 卷`,
        expected_chapters: 8,
        anchors: {
          stage_goal: pEls[0] ? pEls[0].textContent.trim() : '',
          main_obstacle: '',
          climax_hook: pEls[1] ? pEls[1].textContent.trim() : '',
          transition_springboard: '',
        }
      });
    });

    return {
      schema_version: '2.0.0',
      locked_fields: Array.from(state.lockedFields),
      meta: {
        title: title,
        genre: genre,
        selected_trope: selectedTrope,
        target_total_words: 200000,
        target_stages_count: stages.length,
        target_words_per_chapter: 2500,
      },
      ideation: {
        logline: safeVal('val_logline', ''),
        hook: safeVal('val_hook', ''),
        reader_expectation: safeVal('val_reader', ''),
        theme: safeVal('val_theme', ''),
        tone: safeVal('val_tone', ''),
      },
      worldview: {
        background: safeVal('val_micro', ''),
        special_rules: safeVal('val_rules', ''),
        taboos: (state.spec && state.spec.worldview && state.spec.worldview.taboos) || '',
      },
      protagonist: {
        id: 'char_protagonist',
        name: safeText('c1_name_badge').trim() || '主角',
        role: '主角',
        want: safeVal('c1_want', ''),
        need: safeVal('c1_need', ''),
        flaw: safeVal('c1_wound', ''),
        arc: safeVal('c1_principle', ''),
      },
      characters: characters,
      ending: {
        climax_vision: safeVal('val_ending', ''),
        core_dilemma: (state.spec && state.spec.ending && state.spec.ending.core_dilemma) || '',
        ultimate_cost: (state.spec && state.spec.ending && state.spec.ending.ultimate_cost) || '',
        resolution_tone: (state.spec && state.spec.ending && state.spec.ending.resolution_tone) || '',
      },
      stages: stages,
    };
  }

  function syncCharSubLabel(badgeId, text) {
    const badge = getEl(badgeId);
    if (badge && badge.nextElementSibling && badge.nextElementSibling.tagName === 'EM') {
      badge.nextElementSibling.textContent = text || '';
    }
  }

  function fillFormWithSpec(spec) {
    if (!spec) return;
    state.spec = spec;

    // 清理既有动态扩展的人物与分卷卡片，防止切换预设或再次推演时残留串台
    document.querySelectorAll('#station_2 .og-extra-char').forEach(el => el.remove());
    document.querySelectorAll('#og_route_list .og-extra-vol').forEach(el => el.remove());
    state.extraCharCounter = 2;
    state.extraVolCounter = 2;

    if (spec.meta) {
      setElVal('val_title', spec.meta.title || '');
      const genreVal = spec.meta.genre || '';
      setElVal('val_genre', genreVal);
      syncGenreChips(genreVal);
      if (spec.meta.selected_trope) {
        setElVal('selected_trope_val', spec.meta.selected_trope);
      }
    }
    if (spec.ideation) {
      setElVal('val_logline', spec.ideation.logline || '');
      setElVal('val_hook', spec.ideation.hook || '');
      setElVal('val_reader', spec.ideation.reader_expectation || '');
      setElVal('val_theme', spec.ideation.theme || '');
      setElVal('val_tone', spec.ideation.tone || '');
    }
    if (spec.worldview) {
      setElVal('val_rules', spec.worldview.special_rules || '');
      setElVal('val_micro', spec.worldview.background || '');
    }
    if (spec.protagonist) {
      const pName = spec.protagonist.name || '主角';
      setElText('c1_name_badge', pName);
      setElText('c1_mono', pName[0] || '主');
      syncCharSubLabel('c1_name_badge', (spec.protagonist.role && spec.protagonist.role !== '主角') ? spec.protagonist.role : '');
      setElVal('c1_want', spec.protagonist.want || '');
      setElVal('c1_need', spec.protagonist.need || '');
      setElVal('c1_wound', spec.protagonist.flaw || '');
      setElVal('c1_principle', spec.protagonist.arc || '');
    }
    if (spec.characters && spec.characters.length > 0) {
      const c1 = spec.characters[0];
      const cName = c1.name || '重要角色';
      setElText('c2_name_badge', cName);
      setElText('c2_mono', cName[0] || '角');
      syncCharSubLabel('c2_name_badge', c1.en_name || '');
      const relSel = getEl('c2_relation_sel');
      if (relSel && c1.relation_type) {
        relSel.value = c1.relation_type;
      }
      setElVal('c2_mot', c1.role_desc || '');
      setElVal('c2_rel', c1.bond_or_conflict || '');

      spec.characters.slice(1).forEach(extraChar => {
        window.addCharacterCard(extraChar, true);
      });
    }
    if (spec.ending) {
      const endText = [
        spec.ending.climax_vision,
        spec.ending.core_dilemma ? `核心抉择：${spec.ending.core_dilemma}` : '',
        spec.ending.resolution_tone ? `余韵：${spec.ending.resolution_tone}` : '',
      ].filter(Boolean).join('\n');
      setElVal('val_ending', endText || spec.ending.climax_vision || '');
    }
    if (spec.stages && spec.stages.length > 0) {
      const st1 = spec.stages[0];
      setElText('st1_title', st1.title || '');
      if (st1.anchors) {
        setElText('st1_a1', st1.anchors.stage_goal || '');
        setElText('st1_a2', st1.anchors.main_obstacle || '');
        setElText('st1_a3', st1.anchors.climax_hook || '');
        setElText('st1_a4', st1.anchors.transition_springboard || '');
      }
      if (spec.stages.length > 1) {
        const st2 = spec.stages[1];
        setElText('st2_title', st2.title || '');
        if (st2.anchors) {
          setElText('st2_a1', st2.anchors.stage_goal || '');
          setElText('st2_a3', st2.anchors.climax_hook || '');
        }
      }
      spec.stages.slice(2).forEach(extraStage => {
        window.addVolumeStage(extraStage, true);
      });
    }
    updateSummaryBar();
  }

  function resolveNovelId(fallback) {
    const title = safeVal('val_title').trim();
    if (title) {
      state.novelId = title;
      return title;
    }
    return state.novelId || fallback || 'current_novel';
  }

  async function ensureSpecSynced() {
    const spec = collectSpecFromForm();
    const novelId = resolveNovelId((spec.meta && spec.meta.title) || 'current_novel');
    state.novelId = novelId;
    await window.api('/api/novel/original/spec', 'PUT', {
      novel_id: novelId,
      spec: spec,
    });
    return novelId;
  }

  // =========================================================================
  // 7. 4 步链式深度推演模态框与流程
  // =========================================================================
  function setPct(p) {
    setElText('pip_percent', p + '%');
    const bar = getEl('pip_bar');
    if (bar) bar.style.width = p + '%';
  }
  function setPip(n, status, text) {
    const row = getEl(`pip_row_${n}`);
    if (row) {
      row.classList.toggle('is-active', status === 'active');
      row.classList.toggle('is-done', status === 'done');
    }
    setElText(`pip_s${n}`, text);
  }

  window.openChainedModal = function() {
    state.chainedCancelled = false;
    const modal = getEl('chained_modal');
    for (let n = 1; n <= 4; n++) setPip(n, '', '等待中');
    setPct(0);
    setElText('pip_title', '正在推演全案');
    if (modal) modal.style.display = 'flex';
    runChainedDeduce();
  };

  window.closeChainedModal = function() {
    state.chainedCancelled = true;
    const modal = getEl('chained_modal');
    if (modal) modal.style.display = 'none';
  };

  async function runChainedDeduce() {
    const title = safeVal('val_title').trim() || '未定名新书';
    const genre = safeVal('val_genre').trim() || '都市言情';
    const trope = safeVal('selected_trope_val').trim() || null;

    setPct(15);
    setPip(1, 'active', '构思中');

    try {
      const payload = {
        title: title,
        genre: genre,
        selected_trope: trope,
        locked_fields: Array.from(state.lockedFields),
        provider_id: currentProviderId(),
        meta_params: { target_stages_count: 4, target_total_words: 200000 },
      };

      setPct(50);
      setPip(1, 'done', '完成');
      setPip(2, 'active', '推演中');
      const res = await window.api('/api/novel/original/deduce', 'POST', payload);
      if (state.chainedCancelled) return;

      setPct(85);
      setPip(2, 'done', '完成');
      setPip(3, 'done', '完成');
      setPip(4, 'active', '规划中');

      const deducedSpec = res.data;
      if (!deducedSpec) throw new Error('推演接口未返回设定集');

      setPct(100);
      setPip(4, 'done', '完成');
      setElText('pip_title', '推演完成');

      setTimeout(() => {
        if (state.chainedCancelled) return;
        window.closeChainedModal();
        fillFormWithSpec(deducedSpec);
        state.novelId = deducedSpec.meta.title;
        window.api('/api/novel/original/spec', 'PUT', { novel_id: state.novelId, spec: deducedSpec });
        autosize(document);
        saveOgDraft();
        if (window.toast) window.toast('全案推演完成，已填入各工位，请逐项审阅');
      }, 400);

    } catch (err) {
      if (state.chainedCancelled) return;
      setElText('pip_title', '推演未完成');
      const active = document.querySelector('#chained_modal .og-pip li.is-active');
      if (active) { active.classList.remove('is-active'); const em = active.querySelector('em'); if (em) em.textContent = '失败'; }
      if (window.toast) window.toast(`推演失败: ${err.message}`);
    }
  }

  // =========================================================================
  // 8. 章节节拍表 (Beat List) 抽屉与工位 4 节拍同步
  // =========================================================================
  window.openBeatDrawer = async function(stageIndex) {
    const stIdx = parseInt(stageIndex || state.currentStageIndex || '1', 10) || 1;
    state.drawerStageIndex = stIdx;
    const drawer = getEl('beat_drawer');
    const mask = getEl('beat_drawer_mask');
    if (drawer) drawer.style.display = 'flex';
    if (mask) mask.style.display = 'block';

    const listEl = getEl('beat_items_list');
    if (listEl) listEl.innerHTML = `<div class="og-empty">正在推导第 ${stIdx} 卷章节节拍…</div>`;

    try {
      const novelId = await ensureSpecSynced();
      const res = await window.api('/api/novel/original/stage/beats', 'POST', {
        novel_id: novelId,
        stage_index: stIdx,
        action: 'generate',
        provider_id: currentProviderId(),
      });
      const beats = (res.data && res.data.beats) ? res.data.beats : [];
      state.lastBeats = beats;
      renderBeatList(beats);
      renderStationBeats(beats);
    } catch (err) {
      if (listEl) listEl.innerHTML = `<div class="og-empty" style="color:var(--og-seal)">节拍表加载失败：${esc(err.message)}。可点击下方「重新推演节拍」重试。</div>`;
    }
  };

  window.closeBeatDrawer = function() {
    const drawer = getEl('beat_drawer');
    const mask = getEl('beat_drawer_mask');
    if (drawer) drawer.style.display = 'none';
    if (mask) mask.style.display = 'none';
  };

  window.confirmBeatDrawer = async function() {
    const stIdx = parseInt(state.drawerStageIndex || state.currentStageIndex || '1', 10) || 1;
    if (state.lastBeats && state.lastBeats.length) {
      try {
        const novelId = await ensureSpecSynced();
        await window.api('/api/novel/original/stage/beats', 'POST', {
          novel_id: novelId,
          stage_index: stIdx,
          action: 'save',
          beats: state.lastBeats,
        });
        renderStationBeats(state.lastBeats);
        if (window.toast) window.toast(`已确认并保存第 ${stIdx} 卷章节节拍表`);
      } catch (err) {
        if (window.toast) window.toast(`保存节拍失败: ${err.message}`);
      }
    }
    window.closeBeatDrawer();
  };

  window.regenerateStageBeats = async function(stageIndex) {
    const stIdx = parseInt(stageIndex || state.currentStageIndex || '1', 10) || 1;
    if (window.toast) window.toast(`正在重新规划第 ${stIdx} 卷节拍表…`);
    try {
      const novelId = await ensureSpecSynced();
      const res = await window.api('/api/novel/original/stage/beats', 'POST', {
        novel_id: novelId,
        stage_index: stIdx,
        action: 'generate',
        provider_id: currentProviderId(),
      });
      const beats = (res.data && res.data.beats) ? res.data.beats : [];
      state.lastBeats = beats;
      renderStationBeats(beats);
      if (window.toast) window.toast(`已生成第 ${stIdx} 卷 ${beats.length} 章最新节拍表`);
    } catch (err) {
      if (window.toast) window.toast(`节拍推演失败: ${err.message}`);
    }
  };

  function renderBeatList(beats) {
    const listEl = getEl('beat_items_list');
    if (!listEl) return;
    if (!beats || !beats.length) {
      listEl.innerHTML = '<div class="og-empty">还没有节拍表，点击下方「重新推演节拍」生成。</div>';
      return;
    }
    listEl.innerHTML = beats.map((b, idx) => {
      const kind = b.beat_type === 'climax' ? 'climax' : (b.beat_type === 'transition' ? 'hook' : '');
      const pill = kind === 'climax' ? '<span class="og-pill is-amber">阶段高潮</span>'
        : kind === 'hook' ? '<span class="og-pill is-violet">破局跳板</span>' : '';
      const clues = (b.planted_clues && b.planted_clues.length)
        ? `<div class="og-clue">伏笔：${esc(b.planted_clues.join('、'))}</div>` : '';
      return `<div class="og-beat ${kind}">
        <div class="og-beat-top"><span class="og-beat-no">第 ${b.chapter_offset || (idx + 1)} 章</span><span class="og-beat-name">${esc(b.title)}</span>${pill}</div>
        <p>${esc(b.summary)}</p>${clues}</div>`;
    }).join('');
  }

  function renderStationBeats(beats) {
    const ol = getEl('beats_list');
    if (!ol || !beats || !beats.length) return;
    setElText('st4_beats_count', `共 ${beats.length} 章`);
    ol.innerHTML = beats.map((b, idx) => {
      const kind = b.beat_type === 'climax' ? 'climax' : (b.beat_type === 'transition' ? 'hook' : '');
      const pill = kind === 'climax' ? '<span class="og-pill is-amber">阶段高潮</span>'
        : kind === 'hook' ? '<span class="og-pill is-violet">破局跳板</span>' : '';
      return `<li class="og-beat ${kind}"><div class="og-beat-top"><span class="og-beat-no">第 ${b.chapter_offset || (idx + 1)} 章</span><span class="og-beat-name">${esc(b.title)}</span>${pill}</div><p>${esc(b.summary)}</p></li>`;
    }).join('');
    updateCounts();
  }

  // =========================================================================
  // 9. 分卷两段式写作长任务与 SSE 实时打字机
  // =========================================================================
  function unwrapSseData(e) {
    const raw = JSON.parse(e.data);
    return (raw && raw.data && typeof raw.data === 'object') ? raw.data : raw;
  }

  function ensureRunnerCaret(container) {
    if (!container) return null;
    let caret = container.querySelector('.og-caret');
    let host = container.querySelector('p:last-of-type');
    if (!host || host.classList.contains('og-note')) {
      host = document.createElement('p');
      container.appendChild(host);
    }
    if (!caret) {
      caret = document.createElement('span');
      caret.className = 'og-caret';
      caret.setAttribute('aria-hidden', 'true');
    }
    if (caret.parentNode !== host || host.lastChild !== caret) {
      host.appendChild(caret);
    }
    return caret;
  }

  function removeRunnerCaret(container) {
    if (!container) return;
    container.querySelectorAll('.og-caret').forEach(el => el.remove());
  }

  function setRunnerCaretPaused(container, paused) {
    if (!container) return;
    container.querySelectorAll('.og-caret').forEach(el => {
      el.classList.toggle('is-paused', !!paused);
    });
  }

  function appendRunnerTokenHtml(container, rawToken) {
    if (!container || rawToken === undefined || rawToken === null) return;
    const caret = ensureRunnerCaret(container);
    if (!caret) return;
    const html = esc(String(rawToken)).replace(/\n/g, '<br>');
    caret.insertAdjacentHTML('beforebegin', html);
  }

  function setRunnerControls(running, paused) {
    const pauseBtn = getEl('btn_runner_pause');
    const cancelBtn = getEl('btn_runner_cancel');
    if (pauseBtn) {
      pauseBtn.style.display = running ? 'inline-flex' : 'none';
      pauseBtn.disabled = !running;
      pauseBtn.textContent = paused ? '继续写作' : '暂停';
    }
    if (cancelBtn) {
      cancelBtn.style.display = running ? 'inline-flex' : 'none';
      cancelBtn.disabled = !running;
    }
  }

  function setRunnerProgress(pct, label) {
    const bar = getEl('runner_progress_bar');
    if (bar && pct !== null && pct !== undefined) bar.style.width = `${Math.max(0, Math.min(100, pct))}%`;
    if (label !== undefined) setElText('runner_progress_text', label);
  }

  window.handleStageControl = async function(action) {
    const jobId = state.activeJobId;
    if (!jobId) {
      if (action === 'cancel') {
        const runnerView = getEl('stage_runner_view');
        if (runnerView) runnerView.style.display = 'none';
      }
      return;
    }

    const act = action === 'toggle-pause' ? (state.isStagePaused ? 'resume' : 'pause') : action;
    const pauseBtn = getEl('btn_runner_pause');
    const cancelBtn = getEl('btn_runner_cancel');
    if (pauseBtn) pauseBtn.disabled = true;
    if (cancelBtn) cancelBtn.disabled = true;

    try {
      await window.api('/api/novel/original/stage/control', 'POST', { job_id: jobId, action: act });
      if (act === 'pause') {
        state.isStagePaused = true;
        setRunnerControls(true, true);
        setRunnerProgress(null, '已暂停');
        setRunnerCaretPaused(getEl('runner_typewriter_content'), true);
        if (window.toast) window.toast('已暂停本卷写作，可随时点击继续');
      } else if (act === 'resume') {
        state.isStagePaused = false;
        setRunnerControls(true, false);
        setRunnerProgress(null, '继续写作中…');
        setRunnerCaretPaused(getEl('runner_typewriter_content'), false);
        if (window.toast) window.toast('已恢复本卷写作');
      } else if (act === 'cancel') {
        if (state.eventSource) {
          state.eventSource.close();
          state.eventSource = null;
        }
        state.activeJobId = null;
        state.isStagePaused = false;
        setRunnerControls(false, false);
        removeRunnerCaret(getEl('runner_typewriter_content'));
        const runnerView = getEl('stage_runner_view');
        if (runnerView) runnerView.style.display = 'none';
        if (window.toast) window.toast('已取消本卷写作任务');
      }
    } catch (err) {
      setRunnerControls(true, state.isStagePaused);
      if (window.toast) window.toast(`任务控制失败: ${err.message}`);
    }
  };

  window.startStageExecution = async function(stageIndex) {
    const stIdx = parseInt(stageIndex || state.currentStageIndex || '1', 10) || 1;
    state.currentStageIndex = stIdx;
    state.isStagePaused = false;
    state.runnerTotalChapters = 0;

    const runnerView = getEl('stage_runner_view');
    const runnerContent = getEl('runner_typewriter_content');
    const runnerTitle = getEl('runner_current_title');
    const chkBox = getEl('box_checkpoint');
    let runnerChars = 0;
    let runnerChapterLabel = '正在写作';

    if (chkBox) chkBox.style.display = 'none';
    if (runnerView) runnerView.style.display = 'block';
    if (runnerTitle) runnerTitle.textContent = `准备第 ${stIdx} 卷写作…`;
    setRunnerControls(true, false);
    setRunnerProgress(5, '连接中…');
    if (runnerContent) {
      runnerContent.innerHTML = `<p class="og-note">正在同步设定集并准备第 ${stIdx} 卷首章连接…</p>`;
      ensureRunnerCaret(runnerContent);
    }

    try {
      const novelId = await ensureSpecSynced();
      const res = await window.api('/api/novel/original/stage/start', 'POST', {
        novel_id: novelId,
        stage_index: stIdx,
        provider_id: currentProviderId(),
      });

      const jobId = res.data.job_id;
      const streamUrl = res.data.stream_url;
      state.activeJobId = jobId;

      if (state.eventSource) state.eventSource.close();
      const es = new EventSource(streamUrl);
      state.eventSource = es;

      es.addEventListener('init', (e) => {
        const d = unwrapSseData(e);
        if (d && d.total_chapters) state.runnerTotalChapters = Number(d.total_chapters) || 0;
        setRunnerProgress(10, '节拍就绪');
      });

      es.addEventListener('chapter_start', (e) => {
        const d = unwrapSseData(e);
        const chOff = Number(d.chapter_offset || d.global_chapter_idx || 1);
        const total = state.runnerTotalChapters || Math.max(chOff, 1);
        const pct = Math.min(95, Math.round((chOff - 0.5) / total * 100));
        runnerChars = 0;
        runnerChapterLabel = `第 ${chOff}/${total} 章`;
        if (runnerTitle) runnerTitle.textContent = `正在生成：第 ${d.global_chapter_idx} 章《${d.title}》`;
        setRunnerProgress(pct, runnerChapterLabel);
        if (runnerContent) {
          removeRunnerCaret(runnerContent);
          runnerContent.insertAdjacentHTML('beforeend', `<h3>第 ${d.global_chapter_idx} 章：${esc(d.title)}</h3><p></p>`);
          ensureRunnerCaret(runnerContent);
        }
      });

      es.addEventListener('token', (e) => {
        const d = unwrapSseData(e);
        if (runnerContent && d.token !== undefined) {
          const tokStr = String(d.token);
          runnerChars += tokStr.replace(/\s+/g, '').length;
          appendRunnerTokenHtml(runnerContent, tokStr);
          runnerContent.scrollTop = runnerContent.scrollHeight;
          setRunnerProgress(null, `${runnerChapterLabel} · 已写 ${runnerChars} 字`);
        }
      });

      es.addEventListener('status_change', (e) => {
        const d = unwrapSseData(e);
        if (d.status === 'paused') {
          state.isStagePaused = true;
          setRunnerControls(true, true);
          setRunnerProgress(null, '已暂停');
          setRunnerCaretPaused(runnerContent, true);
        } else if (d.status === 'writing') {
          state.isStagePaused = false;
          setRunnerControls(true, false);
          setRunnerProgress(null, '写作中…');
          setRunnerCaretPaused(runnerContent, false);
        }
      });

      es.addEventListener('cancelled', () => {
        es.close();
        state.eventSource = null;
        state.activeJobId = null;
        state.isStagePaused = false;
        setRunnerControls(false, false);
        removeRunnerCaret(runnerContent);
        if (runnerView) runnerView.style.display = 'none';
      });

      es.addEventListener('stage_complete', () => {
        es.close();
        state.eventSource = null;
        state.activeJobId = null;
        setRunnerControls(false, false);
        removeRunnerCaret(runnerContent);
        setRunnerProgress(100, '本卷完成');
        const box = getEl('box_checkpoint');
        if (box) box.style.display = 'block';
        if (window.toast) window.toast(`第 ${stIdx} 卷全部章节已生成，正在打开阶段复盘`);
        setTimeout(() => window.openCheckpointModal(stIdx), 600);
      });

      es.addEventListener('error', () => {
        es.close();
        state.eventSource = null;
        removeRunnerCaret(runnerContent);
        if (!state.activeJobId) return;
        setRunnerProgress(null, '连接已断开（可继续控停）');
        if (window.toast) window.toast('实时流连接已断开，或任务已结束');
      });

    } catch (err) {
      setRunnerControls(false, false);
      removeRunnerCaret(runnerContent);
      setRunnerProgress(0, '启动失败');
      if (runnerContent) runnerContent.innerHTML = `<p class="og-note" style="color:var(--og-seal)">启动失败：${esc(err.message)}</p>`;
      if (window.toast) window.toast(`启动失败: ${err.message}`);
    }
  };

  // =========================================================================
  // 10. 阶段检查点偏差评估与大纲自适应回写
  // =========================================================================
  window.openCheckpointModal = async function(stageIndex) {
    const stIdx = parseInt(stageIndex || state.currentStageIndex || '1', 10) || 1;
    state.checkpointStageIndex = stIdx;
    const modal = getEl('checkpoint_modal');
    if (modal) modal.style.display = 'flex';

    const reportEl = getEl('checkpoint_report_body');
    if (reportEl) reportEl.innerHTML = `<div class="og-empty">正在对照原定锚点复盘第 ${stIdx} 卷正文…</div>`;

    try {
      const novelId = await ensureSpecSynced();
      const res = await window.api('/api/novel/original/stage/checkpoint', 'POST', {
        novel_id: novelId,
        stage_index: stIdx,
        action: 'evaluate',
        provider_id: currentProviderId(),
      });
      const rep = res.data || {};
      if (reportEl) {
        const adj = rep.suggested_next_stage_adjustments;
        const adjText = (adj && typeof adj === 'object') ? Object.values(adj).filter(Boolean).join('；') : (adj || '暂无修订建议');
        reportEl.innerHTML = `
          <div class="og-stats" style="margin-top:0"><div><strong>${esc(rep.goal_achievement_pct || 90)}%</strong>阶段目标达成度</div></div>
          <div class="og-check-cols" style="grid-template-columns:1fr">
            <div class="og-check-col"><b>与原锚点的偏差</b><p>${esc(rep.deviation_summary || '各章节严格承接原案。')}</p></div>
            <div class="og-check-col"><b>人物实际成长</b><p>${esc(rep.character_growth_notes || '主角顺利觉醒。')}</p></div>
            <div class="og-check-col is-advice"><b>对后续分卷的修订建议</b><p>${esc(adjText)}</p></div>
          </div>`;
      }
      setElText('chk_dev', rep.deviation_summary || '各章节严格承接原案。');
      const adj = rep.suggested_next_stage_adjustments;
      if (adj) {
        setElText('chk_adv', typeof adj === 'object' ? Object.values(adj).filter(Boolean).join('；') : String(adj));
      }
    } catch (err) {
      if (reportEl) reportEl.innerHTML = `<div class="og-empty" style="color:var(--og-seal)">复盘失败：${esc(err.message)}。可稍后重试。</div>`;
    }
  };

  window.closeCheckpointModal = function() {
    const modal = getEl('checkpoint_modal');
    if (modal) modal.style.display = 'none';
  };

  window.acceptCheckpointWriteback = async function(stageIndex) {
    const stIdx = parseInt(stageIndex || state.checkpointStageIndex || state.currentStageIndex || '1', 10) || 1;
    try {
      const novelId = await ensureSpecSynced();
      const res = await window.api('/api/novel/original/stage/checkpoint', 'POST', {
        novel_id: novelId,
        stage_index: stIdx,
        action: 'accept_and_writeback',
        spec_modifications: {},
      });
      window.closeCheckpointModal();
      const nextIdx = (res.data && res.data.next_stage_index) ? parseInt(res.data.next_stage_index, 10) : (stIdx + 1);
      const stages = getFormStages();
      if (stages.some(s => s.stage_index === nextIdx)) {
        window.selectStage(nextIdx);
      }
      if (window.toast) window.toast(`已采纳第 ${stIdx} 卷建议并切换至第 ${nextIdx} 卷`);
      window.goToStep(4);
    } catch (err) {
      if (window.toast) window.toast(`回写失败: ${err.message}`);
    }
  };

  window.enterStudioReader = function() {
    const novelId = safeVal('val_title').trim() || state.novelId;
    if (!novelId) {
      if (window.toast) window.toast('请先命名并创建作品后再进入阅读器');
      return;
    }
    if (typeof window.openReader === 'function') {
      window.openReader(novelId);
    } else {
      location.hash = 'read/' + encodeURIComponent(novelId);
    }
  };

  // =========================================================================
  // 11. 演示预设切换与本地草稿自动保存/恢复
  // =========================================================================
  function saveOgDraft() {
    if (state.isRestoring) return;
    try {
      const draft = {
        novelId: state.novelId,
        activeStation: state.activeStation,
        currentStageIndex: state.currentStageIndex,
        spec: collectSpecFromForm(),
        updatedAt: Date.now(),
      };
      localStorage.setItem(OG_DRAFT_KEY, JSON.stringify(draft));
    } catch (e) { /* 忽略浏览器存储配额或无痕模式限制 */ }
  }

  window.restoreOgDraft = function() {
    if (state.draftRestored) return true;
    try {
      const raw = localStorage.getItem(OG_DRAFT_KEY);
      if (!raw) return false;
      const draft = JSON.parse(raw);
      if (!draft || typeof draft !== 'object' || !draft.spec) return false;
      state.isRestoring = true;
      fillFormWithSpec(draft.spec);
      state.novelId = safeVal('val_title').trim() || (draft.spec.meta && draft.spec.meta.title) || draft.novelId || '';
      window.selectStage(draft.currentStageIndex || 1);
      window.goToStep(draft.activeStation || 1);
      autosize(document);
      state.isRestoring = false;
      state.draftRestored = true;
      return true;
    } catch (e) {
      state.isRestoring = false;
      try { localStorage.removeItem(OG_DRAFT_KEY); } catch (e2) { /* 忽略 */ }
      return false;
    }
  };

  window.loadDemo = function(presetKey, silent) {
    const preset = PRESETS[presetKey];
    if (!preset) return;
    fillFormWithSpec(preset);
    state.novelId = preset.meta.title;
    window.selectStage(1);
    const bRomance = getEl('btn_demo_romance');
    const bFantasy = getEl('btn_demo_fantasy');
    if (bRomance) bRomance.classList.toggle('is-on', presetKey === 'romance');
    if (bFantasy) bFantasy.classList.toggle('is-on', presetKey === 'fantasy');
    autosize(document);
    if (!silent) {
      saveOgDraft();
      if (window.toast) window.toast(`已载入 [${preset.meta.genre}] 预设数据`);
    }
  };

  // =========================================================================
  // 11.5 界面交互层：事件委托、设定速览、完成度、文本框自适应高度
  // =========================================================================
  const STATION_FIELDS = {
    1: ['val_title', 'val_logline', 'val_hook', 'val_reader', 'val_theme', 'val_tone'],
    2: ['val_rules', 'val_micro', 'c1_want', 'c1_need', 'c1_wound', 'c1_principle', 'c2_mot', 'c2_rel'],
    3: ['val_ending', 'st1_a1', 'st1_a2', 'st1_a3', 'st1_a4'],
    4: ['b1_t', 'b2_t', 'b5_t', 'b6_t'],
  };

  function fieldFilled(id) {
    const el = getEl(id);
    if (!el) return false;
    const v = (el.value !== undefined ? el.value : el.textContent) || '';
    return v.trim().length > 0;
  }

  function updateCounts() {
    Object.keys(STATION_FIELDS).forEach(n => {
      if (n === '4') {
        const beatItems = document.querySelectorAll('#beats_list > li:not(.is-fold)');
        const total = Math.max(beatItems.length, 4);
        const done = beatItems.length;
        setElText('cnt_4', `${done}/${total}`);
        const bar4 = getEl('bar_4');
        if (bar4) bar4.style.width = `${Math.min(100, Math.round(done / total * 100))}%`;
        return;
      }
      const ids = STATION_FIELDS[n];
      const done = ids.filter(fieldFilled).length;
      setElText(`cnt_${n}`, `${done}/${ids.length}`);
      const bar = getEl(`bar_${n}`);
      if (bar) bar.style.width = `${Math.round(done / ids.length * 100)}%`;
    });
  }

  function refreshOverview() {
    const put = (id, text, html) => {
      const el = getEl(id);
      if (!el) return;
      const v = (text || '').trim();
      el.classList.toggle('is-empty', !v);
      if (!v) el.textContent = '尚未填写';
      else if (html) el.innerHTML = html; else el.textContent = v;
    };
    put('ov_logline', safeVal('val_logline'));
    const nameEl = getEl('c1_name_badge');
    const pname = nameEl ? nameEl.textContent.trim() : '';
    const want = safeVal('c1_want').trim();
    put('ov_protagonist', pname + want, `<b>${esc(pname)}</b>${want ? '：' + esc(want) : ''}`);
    put('ov_ending', safeVal('val_ending'));
    const t = getEl('st1_title'), g = getEl('st1_a1');
    const tt = t ? t.textContent.trim() : '';
    put('ov_stage', tt, `<b>${esc(tt)}</b>${g ? '<br>' + esc(g.textContent.trim()) : ''}`);
  }

  const supportsFieldSizing = !!(window.CSS && CSS.supports && CSS.supports('field-sizing', 'content'));
  function autosize(root) {
    if (supportsFieldSizing) return;
    (root || document).querySelectorAll('.og textarea.og-input').forEach(t => {
      t.style.height = 'auto';
      if (t.scrollHeight) t.style.height = (t.scrollHeight + 2) + 'px';
    });
  }

  window.showHistory = function(f) {
    const h = state.fieldHistories[f] || [];
    if (window.toast) window.toast(h.length ? `已保存 ${h.length} 个历史快照，最近一次在 ${h[h.length - 1].time}` : '暂无历史版本');
  };

  window.toggleQuickDrawer = function() {
    const shell = getEl('og_shell');
    if (!shell) return;
    if (window.matchMedia('(max-width: 1260px)').matches) shell.classList.toggle('aside-open');
    else shell.classList.toggle('aside-off');
    refreshOverview();
  };

  document.addEventListener('click', (e) => {
    const el = e.target.closest('[data-act]');
    if (!el) return;
    const f = el.dataset.field;
    switch (el.dataset.act) {
      case 'rewrite': case 'polish': window.triggerRefine(f, el.dataset.act); break;
      case 'lock': window.toggleLock(f); break;
      case 'directive': window.toggleDirective(f); break;
      case 'submit-directive': window.triggerRefine(f, 'rewrite'); break;
      case 'history': window.showHistory(f); break;
      case 'accept': window.acceptProposal(f); break;
      case 'reject': window.rejectProposal(f); break;
      case 'refresh-tropes': window.refreshTropes(); break;
      case 'add-char': window.addCharacterCard(); saveOgDraft(); break;
      case 'remove-char': {
        const c = el.closest('.og-char');
        if (c) { c.remove(); saveOgDraft(); if (window.toast) window.toast('已移除角色卡片'); }
        break;
      }
      case 'refine-char': window.refineCharacterCard(f, el.dataset.mode || 'polish'); break;
      case 'add-vol': window.addVolumeStage(); saveOgDraft(); break;
      case 'remove-vol': {
        const v = el.closest('.og-vol');
        if (v) { v.remove(); syncStageSelector(); saveOgDraft(); if (window.toast) window.toast('已移除新增分卷'); }
        break;
      }
      case 'rewrite-vol': window.rewriteStageAnchors(parseInt(el.dataset.stage || '1', 10)); break;
      case 'edit-vol': window.editStageAnchors(parseInt(el.dataset.stage || '1', 10), el); break;
      case 'regen-beats': window.regenerateStageBeats(); break;
      case 'pause-stage': window.handleStageControl('toggle-pause'); break;
      case 'cancel-stage': window.handleStageControl('cancel'); break;
      case 'writeback': window.acceptCheckpointWriteback(); break;
      case 'enter-reader': window.enterStudioReader(); break;
      case 'toast': if (window.toast) window.toast(el.dataset.msg || ''); break;
    }
  });

  document.addEventListener('keydown', (e) => {
    const t = e.target;
    if (t && t.classList && t.classList.contains('og-trope') && (e.key === 'Enter' || e.key === ' ')) {
      e.preventDefault();
      window.chooseTrope(t);
    }
    if (e.key === 'Escape') {
      ['chained_modal', 'checkpoint_modal'].forEach(id => { const m = getEl(id); if (m && m.style.display === 'flex') m.style.display = 'none'; });
      window.closeBeatDrawer();
    }
  });

  document.addEventListener('input', (e) => {
    if (!e.target.closest || !e.target.closest('#view-original')) return;
    if (e.target.id === 'st4_stage_sel') return;
    if (e.target.id === 'val_title') {
      state.novelId = e.target.value.trim();
    } else if (e.target.id === 'c1_name_badge') {
      const txt = e.target.textContent.trim();
      setElText('c1_mono', (txt || '主')[0]);
    } else if (e.target.id === 'c2_name_badge') {
      const txt = e.target.textContent.trim();
      setElText('c2_mono', (txt || '角')[0]);
    }
    if (e.target.tagName === 'TEXTAREA') autosize(e.target.parentElement);
    updateSummaryBar();
    saveOgDraft();
  });

  // =========================================================================
  // 12. 模块初始化入口
  // =========================================================================
  function initOriginalStudio() {
    if (!window.restoreOgDraft()) {
      window.loadDemo('romance', true);
      window.goToStep(1);
      state.draftRestored = true;
    }
    autosize(document);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initOriginalStudio);
  } else {
    initOriginalStudio();
  }

})();
