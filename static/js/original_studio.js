// static/js/original_studio.js - 原创小说创作 Studio 前端交互控制中枢 (v2.0)
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
    fieldHistories: {}, // field_path -> [v1, v2, ...]
    activeJobId: null,
    eventSource: null,
  };

  // 预设样例库（供创作者快速对比体验言情与科幻等全题材中立能力）
  const PRESETS = {
    romance: {
      meta: { title: "微醺心跳定律", genre: "都市言情·甜宠", selected_trope: "合租屋里的猫咪与合约情侣" },
      ideation: {
        logline: "习惯用理智与配方丈量一切的高冷调香师，偶然与热情直率但生活一团糟的绘本作家成为合租室友；在一场关于‘气味与心动’的假扮情侣合约中，两人逐步解开心结，确认了彼此是唯一的解药。",
        hook: "气味过敏的调香天才唯独对邋遢室友的气味免疫",
        reader_expectation: "高甜治愈、极致推拉、生活烟火气",
        theme: "真正的爱是允许彼此在对方面前卸下防备与伪装",
        tone: "第三人称限制视角，笔触细腻温润，微酸带甜",
      },
      worldview: {
        background: "海滨梧桐老街，法式带阁楼的老洋房，楼下是清吧，楼上是充满草稿纸与香氛样品的合租屋。",
        special_rules: "同居守则十二条：公区轮流打扫、严禁越界探听对方过往隐私。",
        taboos: "不可在合约期内假戏真做动真感情。",
      },
      protagonist: {
        id: "char_protagonist",
        name: "江月白",
        role: "新锐香氛调香师",
        want: "在国际嗅觉展上凭借独立配方夺得金奖",
        need: "走出因母亲早逝导致的孤独封闭，学会接纳他人的不完美",
        flaw: "强迫症、洁癖、习惯性用刻薄言辞掩盖慌乱心动",
        arc: "从孤独防御的冰山，变为懂得珍视人间烟火与相伴温度的爱人",
      },
      characters: [
        {
          id: "char_female_lead",
          name: "苏晴好",
          relation_type: "cp_love",
          role_desc: "野生绘本作家 / 自由插画师",
          bond_or_conflict: "画室被退租被迫合租，随性散漫，与男主的严苛秩序产生剧烈碰撞",
        }
      ],
      ending: {
        climax_vision: "巴黎终审评奖前夕，男主当众销毁了保密配方，奔赴机场寻找即将离港的女主并以特调香氛告白。",
        core_dilemma: "家族香氛品牌的继承权与守护女主创作自由的二选一。",
        ultimate_cost: "男主主动脱离家族财团支持，两人合开独立手作工坊。",
        resolution_tone: "全景式的浪漫温馨，微醺余韵悠长。",
      },
      stages: [
        {
          stage_index: 1,
          title: "第 1 卷：屋檐下的冰块与野猫",
          expected_chapters: 6,
          anchors: {
            stage_goal: "建立合租契约，签署假扮情侣协议",
            main_obstacle: "作息完全颠倒与气味过敏带来的摩擦",
            climax_hook: "暴雨夜拯救流浪猫，女主发烧男主守候一夜挑明身世",
            transition_springboard: "双方家长突然登门查房，协议正式启动",
          }
        }
      ]
    },
    fantasy: {
      meta: { title: "赛博道祖", genre: "科幻修仙·赛博朋克", selected_trope: "底层义眼走私犯与机械道印" },
      ideation: {
        logline: "九龙城寨底层义眼技师在回收废弃芯片时，意外激活了上古‘太上洞玄九转机魂道印’；在巨型跨国赛博宗门的高压奴役下，他以符箓重构神经突触，掀起一场涤荡星海的机械飞升革命。",
        hook: "用电磁线圈刻画雷法符箓，赛博义体暗藏金丹大道",
        reader_expectation: "硬核设定、反差爽点、弑神破局",
        theme: "生命意志与冷酷资本算力的终极较量",
        tone: "第三人称限制视角，硬冷写实，兼具古雅道韵",
      },
      worldview: {
        background: "霓虹阴雨永不休止的九龙地底八百米，空气中弥漫着机油与廉价合成香精的酸涩，巨型全息三清巨像俯瞰着贫民窟。",
        special_rules: "香火即算力，飞升即上传意识至太虚母矩阵；违规改装灵根者受天基神雷劫灭。",
        taboos: "严禁在母矩阵防火墙外私自推演天道算法。",
      },
      protagonist: {
        id: "char_protagonist",
        name: "陈拙",
        role: "黑市义肢改装学徒",
        want: "积攒足够的太虚币为病危的妹妹赎回完整原生大脑",
        need: "打破顺从宿命的奴性，觉醒带领底层修士抗衡天道算力的道祖之志",
        flaw: "冷漠利己、重度义体排异反应引发的神经剧痛与偏执",
        arc: "从蝼蚁般的黑市盗火者，成长为重塑人神秩序的九天机魂道祖",
      },
      characters: [
        {
          id: "char_rival",
          name: "司徒渊",
          relation_type: "rival_antagonist",
          role_desc: "神霄重工集团执法长老 / 纯阳型机械天兵",
          bond_or_conflict: "奉命清洗黑市走私节点，执着于抓获陈拙夺回九转道印",
        }
      ],
      ending: {
        climax_vision: "近地轨道太虚母矩阵核心，主角肉身崩解以纯粹意识引爆天基电磁风暴，彻底重置神霄算力天网。",
        core_dilemma: "成为永生的数字天道独裁者，还是瓦解算力让整座星系回归人人平等的乱世。",
        ultimate_cost: "永久放弃飞升资格，神魂化为守护众生底层防火墙的散碎星光。",
        resolution_tone: "旷远沧桑、充满希望的史诗余韵。",
      },
      stages: [
        {
          stage_index: 1,
          title: "第 1 卷：铁锈城寨与走私符箓",
          expected_chapters: 6,
          anchors: {
            stage_goal: "在神霄执法队的扫荡中隐匿行踪并成功筑基",
            main_obstacle: "义体排异与走私黑警的勒索追查",
            climax_hook: "黑市擂台赛上以自制等离子掌心雷击溃筑基期机甲修士",
            transition_springboard: "夺得神霄天宫通行密匙，不得不踏上偷渡之旅",
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
    return el ? el.value : fallback;
  }

  function setElVal(id, val) {
    const el = getEl(id);
    if (el) el.value = val;
  }

  function setElText(id, text) {
    const el = getEl(id);
    if (el) el.textContent = text;
  }

  // =========================================================================
  // 3. 工位导航与分步切换
  // =========================================================================
  window.goToStep = function(stepNum) {
    state.activeStation = stepNum;
    for (let i = 1; i <= 4; i++) {
      const tab = getEl(`step_tab_${i}`);
      const panel = getEl(`station_${i}`);
      if (tab) {
        tab.classList.toggle('active', i === stepNum);
        tab.classList.toggle('done', i < stepNum);
      }
      if (panel) {
        panel.style.display = (i === stepNum) ? 'block' : 'none';
      }
    }
    updateSummaryBar();
  };

  function updateSummaryBar() {
    const title = safeVal('val_title') || (state.spec && state.spec.meta ? state.spec.meta.title : '未命名作品');
    const genre = safeVal('val_genre') || (state.spec && state.spec.meta ? state.spec.meta.genre : '未选题材');
    setElText('sum_title', `《${title}》`);
    setElText('sum_genre', genre);
  }

  // =========================================================================
  // 4. 题材药丸与灵感脑洞选择
  // =========================================================================
  window.selectGenre = function(btn) {
    if (!btn) return;
    const parent = btn.parentElement;
    if (parent) {
      parent.querySelectorAll('.tag-pill').forEach(b => b.classList.remove('active'));
    }
    btn.classList.add('active');
    setElVal('val_genre', btn.textContent.trim());
    updateSummaryBar();
  };

  window.chooseTrope = function(card) {
    if (!card) return;
    const parent = card.parentElement;
    if (parent) {
      parent.querySelectorAll('.trope-card').forEach(c => c.classList.remove('active'));
    }
    card.classList.add('active');
    const titleEl = card.querySelector('h4');
    const descEl = card.querySelector('p');
    if (titleEl && descEl) {
      setElVal('selected_trope_val', `${titleEl.textContent.trim()}: ${descEl.textContent.trim()}`);
    }
  };

  window.clearTropeSelection = function() {
    const container = getEl('trope_cards_container');
    if (container) {
      container.querySelectorAll('.trope-card').forEach(c => c.classList.remove('active'));
    }
    setElVal('selected_trope_val', '');
    if (window.toast) window.toast('已取消灵感选择，进入纯自主自由构思模式');
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
    const isLocked = state.lockedFields.has(fieldKey);

    if (isLocked) {
      state.lockedFields.delete(fieldKey);
      if (btn) {
        btn.textContent = '🔒 锁定';
        btn.style.color = '';
        btn.style.fontWeight = '';
      }
      if (input) input.readOnly = false;
      if (window.toast) window.toast(`已解锁 [${fieldKey}]，推演引擎可自适应更新`);
    } else {
      state.lockedFields.add(fieldKey);
      if (btn) {
        btn.textContent = '🔒 已锁定';
        btn.style.color = 'var(--accent)';
        btn.style.fontWeight = '700';
      }
      if (input) input.readOnly = true;
      if (window.toast) window.toast(`已锁定 [${fieldKey}]，推演与重写将绝对保留此字段`);
    }
  };

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

    const reviewBar = getEl(`review_${fieldPath}`);
    const diffContainer = getEl(`diff_${fieldPath}`);
    const dirBar = getEl(`dir_${fieldPath}`);

    if (reviewBar) reviewBar.style.display = 'flex';
    if (diffContainer) diffContainer.innerHTML = '<span style="color:var(--muted)">✨ 正在调用大模型生成候选...</span>';

    try {
      const payload = {
        novel_id: state.novelId || safeVal('val_title') || 'temp_book',
        field_path: fieldPath,
        mode: mode,
        current_value: currentVal,
        user_hint: userHint,
        spec_context: collectSpecFromForm(),
        candidates_count: 1,
      };

      const res = await window.api('/api/novel/original/refine-field', 'POST', payload);
      const candidates = (res.data && res.data.candidates) ? res.data.candidates : [];
      if (!candidates.length) throw new Error('模型未返回候选方案');

      const proposal = candidates[0];
      // 保存旧版本到历史快照
      if (!state.fieldHistories[fieldPath]) state.fieldHistories[fieldPath] = [];
      state.fieldHistories[fieldPath].push({ time: new Date().toLocaleTimeString(), val: currentVal });

      renderDiffView(fieldPath, currentVal, proposal);
      if (dirBar) dirBar.style.display = 'none';
      if (dirInput) dirInput.value = '';

    } catch (err) {
      if (diffContainer) diffContainer.innerHTML = `<span style="color:var(--err)">精修失败：${err.message}</span>`;
      if (window.toast) window.toast(`精修异常: ${err.message}`);
    }
  };

  function renderDiffView(fieldPath, original, proposal) {
    const diffEl = getEl(`diff_${fieldPath}`);
    if (!diffEl) return;

    // 简单行内高亮 Diff：显示原句划线与新句高亮
    diffEl.innerHTML = `
      <div style="font-size:13px;line-height:1.6;">
        ${original ? `<div style="text-decoration:line-through;color:var(--err);background:#FEF2F2;padding:4px 8px;border-radius:4px;margin-bottom:6px;">${window.escapeHtml ? window.escapeHtml(original) : original}</div>` : ''}
        <div style="color:var(--ok);background:#ECFDF5;padding:4px 8px;border-radius:4px;font-weight:500;" id="proposal_text_${fieldPath}">${window.escapeHtml ? window.escapeHtml(proposal) : proposal}</div>
      </div>
    `;
  }

  window.acceptProposal = function(fieldPath) {
    const propEl = getEl(`proposal_text_${fieldPath}`);
    const input = getEl(`val_${fieldPath}`);
    const reviewBar = getEl(`review_${fieldPath}`);

    if (propEl && input) {
      input.value = propEl.textContent.trim();
      if (reviewBar) reviewBar.style.display = 'none';
      if (window.toast) window.toast(`已采纳新版 [${fieldPath}]`);
      updateSummaryBar();
    }
  };

  window.rejectProposal = function(fieldPath) {
    const reviewBar = getEl(`review_${fieldPath}`);
    if (reviewBar) reviewBar.style.display = 'none';
    if (window.toast) window.toast('已撤销本次提议，保留原内容');
  };

  // =========================================================================
  // 6. 表单收集与设定集同步
  // =========================================================================
  function collectSpecFromForm() {
    const title = safeVal('val_title') || '未命名小说';
    const genre = safeVal('val_genre') || '都市言情';
    const selectedTrope = safeVal('selected_trope_val') || null;

    return {
      schema_version: "2.0.0",
      locked_fields: Array.from(state.lockedFields),
      meta: {
        title: title,
        genre: genre,
        selected_trope: selectedTrope,
        target_total_words: parseInt(safeVal('meta_total_words', '200000')) || 200000,
        target_stages_count: 4,
        target_words_per_chapter: 2500,
      },
      ideation: {
        logline: safeVal('val_logline', ''),
        hook: safeVal('val_hook', ''),
        reader_expectation: safeVal('val_reader_exp', ''),
        theme: safeVal('val_theme', ''),
        tone: safeVal('val_tone', ''),
      },
      worldview: {
        background: safeVal('val_wv_bg', ''),
        special_rules: safeVal('val_wv_rules', ''),
        taboos: safeVal('val_wv_taboos', ''),
      },
      protagonist: {
        id: "char_protagonist",
        name: safeVal('val_p_name', '陈拙'),
        role: safeVal('val_p_role', '主角'),
        want: safeVal('val_p_want', ''),
        need: safeVal('val_p_need', ''),
        flaw: safeVal('val_p_flaw', ''),
        arc: safeVal('val_p_arc', ''),
      },
      characters: [
        {
          id: "char_key_1",
          name: safeVal('val_c1_name', '关键关系人'),
          relation_type: safeVal('val_c1_relation', 'cp_love'),
          role_desc: safeVal('val_c1_desc', ''),
          bond_or_conflict: safeVal('val_c1_bond', ''),
        }
      ],
      ending: {
        climax_vision: safeVal('val_end_vision', ''),
        core_dilemma: safeVal('val_end_dilemma', ''),
        ultimate_cost: safeVal('val_end_cost', ''),
        resolution_tone: safeVal('val_end_tone', ''),
      },
      stages: [
        {
          stage_index: 1,
          title: safeVal('val_st1_title', '第 1 卷：破壳与启程'),
          expected_chapters: 6,
          anchors: {
            stage_goal: safeVal('val_st1_goal', ''),
            main_obstacle: safeVal('val_st1_obstacle', ''),
            climax_hook: safeVal('val_st1_climax', ''),
            transition_springboard: safeVal('val_st1_springboard', ''),
          }
        }
      ]
    };
  }

  function fillFormWithSpec(spec) {
    if (!spec) return;
    state.spec = spec;

    if (spec.meta) {
      setElVal('val_title', spec.meta.title || '');
      setElVal('val_genre', spec.meta.genre || '');
    }
    if (spec.ideation) {
      setElVal('val_logline', spec.ideation.logline || '');
      setElVal('val_hook', spec.ideation.hook || '');
      setElVal('val_reader_exp', spec.ideation.reader_expectation || '');
      setElVal('val_theme', spec.ideation.theme || '');
      setElVal('val_tone', spec.ideation.tone || '');
    }
    if (spec.worldview) {
      setElVal('val_wv_bg', spec.worldview.background || '');
      setElVal('val_wv_rules', spec.worldview.special_rules || '');
      setElVal('val_wv_taboos', spec.worldview.taboos || '');
    }
    if (spec.protagonist) {
      setElVal('val_p_name', spec.protagonist.name || '');
      setElVal('val_p_role', spec.protagonist.role || '');
      setElVal('val_p_want', spec.protagonist.want || '');
      setElVal('val_p_need', spec.protagonist.need || '');
      setElVal('val_p_flaw', spec.protagonist.flaw || '');
      setElVal('val_p_arc', spec.protagonist.arc || '');
    }
    if (spec.characters && spec.characters.length > 0) {
      const c1 = spec.characters[0];
      setElVal('val_c1_name', c1.name || '');
      setElVal('val_c1_relation', c1.relation_type || 'cp_love');
      setElVal('val_c1_desc', c1.role_desc || '');
      setElVal('val_c1_bond', c1.bond_or_conflict || '');
    }
    if (spec.ending) {
      setElVal('val_end_vision', spec.ending.climax_vision || '');
      setElVal('val_end_dilemma', spec.ending.core_dilemma || '');
      setElVal('val_end_cost', spec.ending.ultimate_cost || '');
      setElVal('val_end_tone', spec.ending.resolution_tone || '');
    }
    if (spec.stages && spec.stages.length > 0) {
      const st1 = spec.stages[0];
      setElVal('val_st1_title', st1.title || '');
      if (st1.anchors) {
        setElVal('val_st1_goal', st1.anchors.stage_goal || '');
        setElVal('val_st1_obstacle', st1.anchors.main_obstacle || '');
        setElVal('val_st1_climax', st1.anchors.climax_hook || '');
        setElVal('val_st1_springboard', st1.anchors.transition_springboard || '');
      }
    }
    updateSummaryBar();
  }

  // =========================================================================
  // 7. 4 步链式深度推演模态框与流程
  // =========================================================================
  window.openChainedModal = function() {
    const modal = getEl('chained_modal');
    if (modal) modal.style.display = 'flex';
    runChainedDeduce();
  };

  window.closeChainedModal = function() {
    const modal = getEl('chained_modal');
    if (modal) modal.style.display = 'none';
  };

  async function runChainedDeduce() {
    const title = safeVal('val_title') || '未定名新书';
    const genre = safeVal('val_genre') || '都市言情';
    const trope = safeVal('selected_trope_val') || null;

    setElText('pip_percent', '15%');
    setElText('pip_s1', '正在构思灵魂立意...');

    try {
      const payload = {
        title: title,
        genre: genre,
        selected_trope: trope,
        locked_fields: Array.from(state.lockedFields),
        meta_params: { target_stages_count: 4, target_total_words: 200000 },
      };

      setElText('pip_percent', '50%');
      setElText('pip_s2', '正在推演世界观与角色...');
      const res = await window.api('/api/novel/original/deduce', 'POST', payload);

      setElText('pip_percent', '85%');
      setElText('pip_s3', '正在锚定终局与分卷...');

      const deducedSpec = res.data;
      if (!deducedSpec) throw new Error('推演接口未返回设定集');

      setElText('pip_percent', '100%');
      setElText('pip_s4', '推演完成！');

      setTimeout(() => {
        closeChainedModal();
        fillFormWithSpec(deducedSpec);
        state.novelId = deducedSpec.meta.title;
        // 自动保存至后端
        window.api('/api/novel/original/spec', 'PUT', { novel_id: state.novelId, spec: deducedSpec });
        if (window.toast) window.toast('⚡ 全案 4 步推演完成，已自动填充各工位！');
      }, 500);

    } catch (err) {
      setElText('pip_percent', '出错');
      setElText('pip_s1', `推演异常: ${err.message}`);
      if (window.toast) window.toast(`推演失败: ${err.message}`);
    }
  }

  // =========================================================================
  // 8. 章节节拍表 (Beat List) 抽屉
  // =========================================================================
  window.openBeatDrawer = async function(stageIndex) {
    const drawer = getEl('beat_drawer');
    const mask = getEl('beat_drawer_mask');
    if (drawer) drawer.style.display = 'flex';
    if (mask) mask.style.display = 'block';

    const listEl = getEl('beat_items_list');
    if (listEl) listEl.innerHTML = '<div style="padding:20px;color:var(--muted)">📋 正在推导/加载本卷章节节拍表...</div>';

    try {
      const novelId = state.novelId || safeVal('val_title') || 'current_book';
      const res = await window.api('/api/novel/original/stage/beats', 'POST', {
        novel_id: novelId,
        stage_index: stageIndex || 1,
        action: 'generate',
      });
      const beats = (res.data && res.data.beats) ? res.data.beats : [];
      renderBeatList(beats);
    } catch (err) {
      if (listEl) listEl.innerHTML = `<div style="padding:20px;color:var(--err)">加载节拍表失败: ${err.message}</div>`;
    }
  };

  window.closeBeatDrawer = function() {
    const drawer = getEl('beat_drawer');
    const mask = getEl('beat_drawer_mask');
    if (drawer) drawer.style.display = 'none';
    if (mask) mask.style.display = 'none';
  };

  function renderBeatList(beats) {
    const listEl = getEl('beat_items_list');
    if (!listEl) return;
    if (!beats || !beats.length) {
      listEl.innerHTML = '<div style="padding:20px;color:var(--muted)">暂无节拍表，请点击重新生成</div>';
      return;
    }

    listEl.innerHTML = beats.map((b, idx) => `
      <div class="beat-item-card" style="border:1px solid var(--line);border-radius:8px;padding:12px;margin-bottom:10px;background:var(--card);">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px;">
          <b style="font-size:13px;color:var(--ink)">第 ${b.chapter_offset || (idx + 1)} 章：${window.escapeHtml ? window.escapeHtml(b.title) : b.title}</b>
          <span class="badge-${b.beat_type === 'climax' ? 'req' : 'opt'}" style="font-size:11px;">${b.beat_type === 'climax' ? '💥 阶段高潮' : (b.beat_type === 'transition' ? '🔄 破局跳板' : '铺垫推进')}</span>
        </div>
        <p style="font-size:12px;color:var(--ink-soft);margin:0;">${window.escapeHtml ? window.escapeHtml(b.summary) : b.summary}</p>
        ${(b.planted_clues && b.planted_clues.length) ? `<div style="font-size:11px;color:var(--accent);margin-top:4px;">🔍 伏笔：${window.escapeHtml ? window.escapeHtml(b.planted_clues.join('、')) : b.planted_clues.join('、')}</div>` : ''}
      </div>
    `).join('');
  }

  // =========================================================================
  // 9. 分卷两段式写作长任务与 SSE 实时打字机
  // =========================================================================
  window.startStageExecution = async function(stageIndex) {
    const novelId = state.novelId || safeVal('val_title') || 'current_novel';
    const runnerView = getEl('stage_runner_view');
    const runnerContent = getEl('runner_typewriter_content');
    const runnerTitle = getEl('runner_current_title');

    if (runnerView) runnerView.style.display = 'block';
    if (runnerContent) runnerContent.innerHTML = '正在建立 SSE 实时长连接并准备首章推演...<br>';

    try {
      const res = await window.api('/api/novel/original/stage/start', 'POST', {
        novel_id: novelId,
        stage_index: stageIndex || 1,
      });

      const jobId = res.data.job_id;
      const streamUrl = res.data.stream_url;
      state.activeJobId = jobId;

      // 建立 SSE 打字机长连接
      if (state.eventSource) state.eventSource.close();
      const es = new EventSource(streamUrl);
      state.eventSource = es;

      es.addEventListener('chapter_start', (e) => {
        const d = JSON.parse(e.data);
        if (runnerTitle) runnerTitle.textContent = `正在生成：第 ${d.global_chapter_idx} 章《${d.title}》`;
        if (runnerContent) runnerContent.innerHTML += `<hr style="margin:16px 0;border:0;border-top:1px dashed var(--line);"><h3 style="margin:8px 0;">第 ${d.global_chapter_idx} 章：${d.title}</h3>`;
      });

      es.addEventListener('token', (e) => {
        const d = JSON.parse(e.data);
        if (runnerContent) {
          runnerContent.innerHTML += (window.escapeHtml ? window.escapeHtml(d.token) : d.token).replace(/\n/g, '<br>');
          runnerContent.scrollTop = runnerContent.scrollHeight;
        }
      });

      es.addEventListener('stage_complete', (e) => {
        es.close();
        if (window.toast) window.toast('🎉 本卷全部章节生成完毕，正在唤起复盘检查点！');
        setTimeout(() => openCheckpointModal(stageIndex || 1), 1000);
      });

      es.addEventListener('error', (e) => {
        es.close();
        if (window.toast) window.toast('长连接断开或任务已完成');
      });

    } catch (err) {
      if (window.toast) window.toast(`启动失败: ${err.message}`);
    }
  };

  // =========================================================================
  // 10. 阶段检查点偏差评估与大纲自适应回写
  // =========================================================================
  window.openCheckpointModal = async function(stageIndex) {
    const modal = getEl('checkpoint_modal');
    if (modal) modal.style.display = 'flex';

    const reportEl = getEl('checkpoint_report_body');
    if (reportEl) reportEl.innerHTML = '正在深度复盘本卷正文与原设锚点偏差...';

    try {
      const novelId = state.novelId || safeVal('val_title') || 'current_novel';
      const res = await window.api('/api/novel/original/stage/checkpoint', 'POST', {
        novel_id: novelId,
        stage_index: stageIndex || 1,
        action: 'evaluate',
      });
      const rep = res.data || {};
      if (reportEl) {
        reportEl.innerHTML = `
          <div style="font-size:13px;line-height:1.65;">
            <p><b>阶段目标达成度：</b><span style="color:var(--ok);font-size:16px;font-weight:700;">${rep.goal_achievement_pct || 90}%</span></p>
            <p><b>剧情与锚点偏差总结：</b><br>${window.escapeHtml ? window.escapeHtml(rep.deviation_summary || '各章节严格承接原案。') : rep.deviation_summary}</p>
            <p><b>人物心境实际成长：</b><br>${window.escapeHtml ? window.escapeHtml(rep.character_growth_notes || '主角顺利觉醒。') : rep.character_growth_notes}</p>
            <div style="background:var(--accent-soft);border:1px solid var(--accent-ring);border-radius:6px;padding:10px;margin-top:10px;">
              <b style="color:var(--accent);">💡 推荐后续分卷自适应修订方案：</b>
              <p style="margin:4px 0 0;font-size:12px;color:var(--ink-soft);">${JSON.stringify(rep.suggested_next_stage_adjustments || {})}</p>
            </div>
          </div>
        `;
      }
    } catch (err) {
      if (reportEl) reportEl.innerHTML = `<span style="color:var(--err)">复盘失败: ${err.message}</span>`;
    }
  };

  window.closeCheckpointModal = function() {
    const modal = getEl('checkpoint_modal');
    if (modal) modal.style.display = 'none';
  };

  window.acceptCheckpointWriteback = async function() {
    const novelId = state.novelId || safeVal('val_title') || 'current_novel';
    try {
      await window.api('/api/novel/original/stage/checkpoint', 'POST', {
        novel_id: novelId,
        stage_index: 1,
        action: 'accept_and_writeback',
        spec_modifications: {},
      });
      closeCheckpointModal();
      if (window.toast) window.toast('✅ 已采纳检查点建议并自动回写设定集，进入下一卷！');
      goToStep(4);
    } catch (err) {
      if (window.toast) window.toast(`回写失败: ${err.message}`);
    }
  };

  // =========================================================================
  // 11. 演示预设切换
  // =========================================================================
  window.loadDemo = function(presetKey) {
    const preset = PRESETS[presetKey];
    if (!preset) return;
    fillFormWithSpec(preset);
    state.novelId = preset.meta.title;

    const bRomance = getEl('btn_demo_romance');
    const bFantasy = getEl('btn_demo_fantasy');
    if (bRomance) {
      bRomance.style.color = (presetKey === 'romance') ? 'var(--accent)' : '';
      bRomance.style.fontWeight = (presetKey === 'romance') ? '600' : 'normal';
    }
    if (bFantasy) {
      bFantasy.style.color = (presetKey === 'fantasy') ? 'var(--accent)' : '';
      bFantasy.style.fontWeight = (presetKey === 'fantasy') ? '600' : 'normal';
    }
    if (window.toast) window.toast(`已载入 [${preset.meta.genre}] 预设全景数据`);
  };

  // =========================================================================
  // 12. 模块初始化入口
  // =========================================================================
  function initOriginalStudio() {
    // 默认载入都市言情预设演示
    window.loadDemo('romance');
    window.goToStep(1);
  }

  // 挂载到 DOM 加载完成时
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initOriginalStudio);
  } else {
    initOriginalStudio();
  }

})();
