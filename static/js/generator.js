
// ==================== 题材药丸选择器 ====================
function syncGenrePillsFromInput() {
  const inp = $('og_genre');
  const wrap = $('og_genre_pills');
  if (!inp || !wrap) return;
  const v = inp.value.trim();
  wrap.querySelectorAll('.tag-pill').forEach(p => {
    const g = p.dataset.genre || p.textContent.trim();
    p.classList.toggle('active', g === v);
  });
}

function initGenrePills() {
  const wrap = $('og_genre_pills');
  if (!wrap) return;
  wrap.querySelectorAll('.tag-pill').forEach(pill => {
    pill.onclick = () => {
      const genre = pill.dataset.genre || pill.textContent.trim();
      const inp = $('og_genre');
      if (!inp) return;
      if (inp.value.trim() === genre) {
        inp.value = '';
        pill.classList.remove('active');
      } else {
        inp.value = genre;
        wrap.querySelectorAll('.tag-pill').forEach(p => p.classList.toggle('active', p === pill));
      }
    };
  });

  const inp = $('og_genre');
  if (inp) {
    inp.addEventListener('input', syncGenrePillsFromInput);
  }
  syncGenrePillsFromInput();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initGenrePills);
} else {
  initGenrePills();
}

// ==================== P1: 灵感脑洞库与全平台经典开局模板 ====================
const TROPE_TEMPLATES = [
  // --- 🌸 情感 · 校园 · 双女主 · 慢生活 · 现实向 ---
  {
    cat: 'female',
    icon: '💍',
    label: '都市言情·合约婚姻失效',
    title: '合约婚姻在立春失效',
    genre: '都市言情',
    setting: '快节奏现代一线都市，投行投资总监与新锐建筑设计师的三年协议婚姻即将到期。同住屋檐下却恪守契约边界，随着各自职场风云变幻与家庭催婚波澜，平静湖面泛起暗涌。',
    characters: '温听竹：投行投资总监，外表清冷从容、工作严谨果断，内心慢热且防御心重。\n周应淮：享誉业界的独立建筑设计师，温润克制，看似漫不经心，实则暗恋已久。\n江予安：温听竹职场劲敌，行事狠辣。',
    storyline: '在合约到期前三个月，周应淮的项目遭遇资方做局陷害，温听竹动用投行资源暗中护盘，意外发现周应淮三年前主动促成这场婚姻的秘密手稿。随着合约解除日倒计时，成年人克制试探的感情终于爆发，双向奔赴。',
    style: '现代都市轻熟风，细腻克制，拉扯感强，职场专业度高，情感温暖治愈',
    perspective: '第三人称',
    chapters: 10,
    per_words: 2200
  },
  {
    cat: 'female',
    icon: '🎒',
    label: '青春校园·盛夏暗恋成真',
    title: '夏天结束前说喜欢你',
    genre: '青春校园',
    setting: '南方临海小城一中的高三盛夏。咸湿的海风、吱呀作响的吊扇、泛黄的高考模拟卷与操场边的单车棚。',
    characters: '林初夏：坚韧温和的普通文科生，习惯默默努力，把心事藏在笔记本最后一页。\n顾言澈：因家庭重大变故从省实验中学转来的理科天才，看似散漫寡言，实则内心孤独负疚。\n陈妙：林初夏的欢脱同桌兼死党。',
    storyline: '被班主任安排成互助同桌后，林初夏发现了顾言澈夜晚在海边废弃灯塔画画的秘密。两人从最初的小心防备，到互相补课、在高考重压下互相打气，成为彼此晦暗生活里的唯一光源，在蝉鸣散去的盛夏坦诚心意。',
    style: '青春明亮，酸甜细腻，海风与市井烟火气，双向救赎，治愈系',
    perspective: '第一人称',
    chapters: 8,
    per_words: 2000
  },
  {
    cat: 'female',
    icon: '👭',
    label: '双女主·从合租到携手破局',
    title: '双姝破局：从合租开始登顶',
    genre: '双女主/互助',
    setting: '一线都会传媒与顶尖公关咨询圈。一个是被传统大报排挤出局的前王牌调查记者，一个是替家族背负巨债的独立公关高手。两人因囊中羞涩成为老破小公寓的临时合租室友。',
    characters: '沈青宜：硬骨头调查记者，观察敏锐，笔锋如刀，坚持追寻真相。\n许明薇：八面玲珑的危机公关操盘手，深谙人性与资本游戏，外表精致冷艳。\n赵明诚：跨国医药集团公关副总裁，道貌岸然的幕后操盘手。',
    storyline: '两人从最初生活习惯的摩擦龃龉，到联手接下一桩看似必死无疑的企业危机公关案。沈青宜查真相，许明薇操盘舆论，两位性格截然相反的女性在残酷商战中互相托底成为生死搭档，最终逆袭创办属于自己的独立公关调查所，联手撕破资本伪善面具。',
    style: '大女主强强联手，节奏干脆利落，女性互助与惺惺相惜，商战逻辑严密，爽点扎实',
    perspective: '第三人称',
    chapters: 10,
    per_words: 2500
  },
  {
    cat: 'female',
    icon: '🌙',
    label: '百合纯爱·月光落在旧琴键上',
    title: '月光落在旧琴键上',
    genre: '百合纯爱',
    setting: '北方老工业城市的旧居民区与市音乐学院。秋末冬初落叶满地，旧防空洞改建的地下独立唱片店与高雅的古典乐演奏厅形成鲜明对照。',
    characters: '孟书颜：出身音乐世家的大提琴手，内敛敏感，因突发神经性耳鸣陷入前所未有的创作低谷。\n迟野：在地下唱片店修老黑胶唱片的电吉他女孩，随性热烈，看似玩世不恭，却有一双能听懂所有情绪的耳朵。',
    storyline: '失聪恐慌中的孟书颜在老街偶入迟野的唱片店，被迟野随手弹奏的粗粝旋律震颤。迟野教她用手掌贴着木吉他面板感受振动，孟书颜带迟野走入结构严谨的交响世界。两颗孤独残缺的灵魂在旋律中无限靠近，互相包扎伤口，逆光新生。',
    style: '唯美细腻，电影质感，文笔诗意清透，情感充沛且动人，氛围感拉满',
    perspective: '第三人称',
    chapters: 8,
    per_words: 2000
  },
  {
    cat: 'female',
    icon: '🍵',
    label: '都市日常·辞职回乡开糖水铺',
    title: '辞职后我在老街开了家糖水铺',
    genre: '都市日常',
    setting: '江南水乡古镇未商业化的青石板老街。一栋带小天井的晚清旧民居，院里有棵老桂花树，夏有凉风冬有炉火。',
    characters: '阮棠：大厂裸辞回乡的年轻人，擅长顺应二十四节气熬制传统甜水与温养糕点，性格恬淡。\n陆见川：隔壁旧木器修缮行的小老板，沉默寡言却手艺极巧，总默默替阮棠修好老屋破旧的木格窗。\n周婆婆：老街巷口的八十岁裁缝，知晓整座古镇半个世纪的秘辛。',
    storyline: '阮棠回到古镇接下外婆留下的空铺子，春煮桑葚红枣露，夏熬薄荷绿豆马蹄沙，秋做桂花栗子羹，冬煨陈皮红豆圆子。形形色色的镇民与远道而来的疲惫旅人在此停驻，一碗碗温润糖水串联起人间烟火百态，也温暖了彼此的人生。',
    style: '治愈温情生活流，慢节奏日常，美食食谱细致考究，文字如清茶回甘，烟火人间',
    perspective: '第三人称',
    chapters: 8,
    per_words: 1800
  },
  {
    cat: 'female',
    icon: '🌾',
    label: '经商种田·边塞客栈发家日常',
    title: '边塞客栈发家日常',
    genre: '经商种田',
    setting: '大盛王朝西北边陲咽喉重镇玉门关外，荒漠戈壁与商道绿洲交界处。商旅、驼队、戍边将士与塞外胡商往来不绝。',
    characters: '苏玉娘：遭逢家道中落、带着年幼弟妹千里逃难的落难千金，厨艺极佳且深通算账经营。\n裴烈：边关巡防营冷面校尉，常年驻守风沙一线，外冷内热，刀法如神。',
    storyline: '从商道旁一间快塌陷的废弃土坯驿站开始，苏玉娘用一口铁锅做出热气腾腾的羊肉臊子面、馕包肉和驱寒姜汤，收拢过路客商。开水井、辟菜畦、引商队、防马匪，一步步将荒凉路口发展成塞外第一繁华商贸大客栈，成就一段传奇。',
    style: '古代经商种田流，塞外风情浓郁，美食生动诱人，勤劳致富爽感，细水长流感情线',
    perspective: '第三人称',
    chapters: 10,
    per_words: 2200
  },
  {
    cat: 'female',
    icon: '👑',
    label: '古代言情·重生主母掌权夺势',
    title: '主母不慈：重生后我掀翻侯府',
    genre: '古代言情',
    setting: '大周京城钟鸣鼎食的永嘉侯府，看似光鲜亮丽的百年世家，内里早已千疮百孔，蛀虫横行、妻妾明枪暗箭。',
    characters: '薛凝：重生归来的侯府掌家嫡妻，前世贤良淑德倾尽家财却被侯府背刺惨死，今生冷心绝情，一心掌权夺利。\n谢策：当朝首辅，权倾朝野却身负隐疾，冷静纵容薛凝的一切借势复仇。',
    storyline: '重生回掌权第一日，薛凝收回所有贴补嫁妆，断了侯府虚荣开销。查亏空、夺庄产、逐刁奴、斗偏心婆母与白莲外室，一步步斩断侯府羽翼，把侯府产业牢牢掌控在自己手中，扶持娘家自立门第。',
    style: '高段位宅斗权谋，大女主清醒利落，打脸节奏飞快，反矫情不圣母',
    perspective: '第三人称',
    chapters: 10,
    per_words: 2500
  },

  // --- ⚡ 脑洞 · 悬疑 · 幻想 · 传奇向 ---
  {
    cat: 'fantasy',
    icon: '🔍',
    label: '刑侦推理·第七个未接来电',
    title: '第七个未接来电',
    genre: '刑侦推理',
    setting: '暴雨倾盆的南方二线江城，老旧筒子楼、废弃船坞与现代化监控天网交织的迷宫。连续三起看似毫无关联的离奇密室坠亡案。',
    characters: '陈恪：市刑侦支队副支队长，老练沉稳，因旧案患有应激性创伤，观察力入微。\n叶清：新调来的省厅犯罪心理画像专家，年轻直率，精通微表情与犯罪行为学。',
    storyline: '每个死者生前手机上，都出现过同一个神秘未接来电，而该号码的主人早在五年前就已经确认死亡。陈恪与叶清顺藤摸瓜，在重重伪造的自杀现场与嫌疑人谎言中剥茧抽丝，挖出一桩跨越十年的校园旧案与复仇迷局。',
    style: '本格与社会派结合，硬核刑侦推理，心理博弈紧凑，氛围阴冷潮湿，现实感强',
    perspective: '第三人称',
    chapters: 10,
    per_words: 2400
  },
  {
    cat: 'fantasy',
    icon: '⚡',
    label: '赛博修仙·反派夺舍',
    title: '赛博修仙：开局夺舍财阀老祖',
    genre: '赛博朋克',
    setting: '高科技低生活的巨型企业都市新九洲，修真宗门转型为跨国垄断财阀，灵根被改造成生化义体，灵石成为底层算力芯片。',
    characters: '顾沉：底层芯片黑客，性格狠辣果断，精通古修道法与现代黑客技术。\n姜晚：反抗军领袖之女，冷艳理智，一直在寻找财阀芯片的致命后门。',
    storyline: '主角意外截获财阀老祖夺舍实验的数据流并反向夺舍，一边潜伏在财阀顶层掌控万亿算力，一边追查仙道崩塌的赛博真相。',
    style: '快节奏爽文，冷硬赛博与东方修真融合，反差感强，带有幽默讽刺',
    perspective: '第三人称',
    chapters: 10,
    per_words: 2000
  },
  {
    cat: 'fantasy',
    icon: '❄️',
    label: '末日求生·数据避难所',
    title: '全球冰封：我的避难所能无限升级',
    genre: '末世求生',
    setting: '神秘冰河期突降，全球地表陷入零下70度的极寒绝境，文明崩溃，变异雪兽横行，残存人类只能在地下避难所抱团取暖。',
    characters: '陆舟：重生归来的避难所所长，清醒理智，拒绝圣母，拥有独家生存科技树。\n白晓：机械与武器改装天才少女，表面毒舌内心忠诚。',
    storyline: '主角利用前世记忆提前囤积海量物资并激活避难所模块化升级系统，在冰封末日中打造地下恒温生态圈与钢铁要塞。',
    style: '硬核生存建设，数据升级流，囤货爽感，逻辑严密',
    perspective: '第三人称',
    chapters: 10,
    per_words: 2000
  },
  {
    cat: 'fantasy',
    icon: '🍞',
    label: '轻小说·满级魔王退休',
    title: '明明是毁灭世界的魔王，退休后却成了萌新导师？',
    genre: '轻小说/日常',
    setting: '剑与魔法的奇幻大陆，魔王与勇者的大战以两败俱伤收场，世界迎来久违的和平。',
    characters: '维恩：前任魔王，战力天花板但只想开家小面包店过悠闲日常，吐槽役担当。\n艾莉：元气满满但冒冒失失的见习骑士少女，总把维恩的随手救命当成奇迹。',
    storyline: '厌倦打杀的魔王伪装成新手村普通店主，却阴差阳错总被麻烦卷入，不得不一边隐瞒无敌实力一边暗中收拾残局。',
    style: '轻松幽默，日常反差萌，迪化流（配角疯狂脑补），治愈温情',
    perspective: '第三人称',
    chapters: 8,
    per_words: 1800
  },
  {
    cat: 'fantasy',
    icon: '🗡️',
    label: '古风武侠·天下第一退隐',
    title: '折剑听雨江湖远',
    genre: '古风武侠',
    setting: '大晏王朝末年，朝堂党争波及江湖，各大门派暗流涌动，昔日威震天下的第一剑客在巅峰之夜销声匿迹。',
    characters: '李寻渡：前天下第一剑客，现临水小镇客栈醉酒跑堂，看似颓唐懒散，实则剑心未泯。\n云佩：逃婚南下的将门虎女，一心想拜天下第一为师行侠仗义。',
    storyline: '一柄染血的古剑被送入客栈，打破了十年的平静，为了护送遗孤并揭开当年师门覆灭的惊天阴谋，退隐剑客重握残剑。',
    style: '古风雅致，烟雨江湖韵味，刀光剑影与市井烟火交织，兼具侠义与宿命感',
    perspective: '第三人称',
    chapters: 10,
    per_words: 2500
  },
  {
    cat: 'fantasy',
    icon: '🏰',
    label: '西幻领主·蒸汽魔导拓荒',
    title: '边境开拓：从零打造蒸汽魔导领',
    genre: '西幻领主',
    setting: '拥有巨龙与魔导科技的泛大陆，北方边境是一片被称为死亡冻土的荒蛮未开发之地。',
    characters: '罗兰：被放逐到极北边境的没落贵族三子，脑中带有现代工业知识库与古魔导阵法融合。\n索菲亚：半精灵魔药学家与工匠大师，严谨理性。',
    storyline: '从修缮一座漏风的风车磨坊开始，利用蒸汽魔导抽水机、魔晶内燃机和流水线开荒拓土，将放逐之地建造成大陆商贸科技中心。',
    style: '种田攀科技，领地建设，探索开荒，史诗感',
    perspective: '第三人称',
    chapters: 10,
    per_words: 2000
  },
  {
    cat: 'fantasy',
    icon: '🎲',
    label: '无限流·剧本杀生还者',
    title: '致命副本：只有我知道正确解法',
    genre: '无限流',
    setting: '全球被神秘的高维副本系统选中，玩家每逢血月必须进入不同主题的致命剧本杀世界完成生存任务。',
    characters: '陆沉：高智商解谜狂人，心理素质极强，擅长卡副本规则bug逆向通关。\n唐柔：冷静果决的战术格斗专家。',
    storyline: '在新手局《废弃精神病院》中识破考官伪装，主角带领团队一次次颠覆规则、通关不可思议的S级副本，探寻高维游戏的终极幕后。',
    style: '高智商博弈，微恐解谜，肾上腺素飙升，节奏紧凑',
    perspective: '第三人称',
    chapters: 8,
    per_words: 2200
  }
];

function strVal(v) {
  return v === null || v === undefined ? '' : String(v).trim();
}

function applyTropeTemplate(t) {
  if (!t || typeof t !== 'object') return;
  const title = strVal(t.title || t.label || t.name);
  const label = strVal(t.label || t.title || t.name);
  $('og_title').value = title;
  $('og_genre').value = strVal(t.genre);
  $('og_setting').value = strVal(t.setting || t.background);
  $('og_characters').value = strVal(t.characters || t.roles);
  $('og_storyline').value = strVal(t.storyline || t.plot);
  $('og_style').value = strVal(t.style);
  $('og_perspective').value = strVal(t.perspective || '第三人称');
  $('og_chapters').value = parseInt(t.chapters, 10) || 10;
  $('og_per_words').value = parseInt(t.per_words, 10) || 2000;

  // 同步高亮题材胶囊
  syncGenrePillsFromInput();
  toast(`已填入「${label || title}」灵感模板！`);
}

// --- 备用精选脑洞库（用于大模型未配置或本地服务未重启时无缝降级）---
const BACKUP_TROPES_POOL = [
  {
    cat: 'female',
    icon: '⚖️',
    label: '职场婚恋·红圈所假戏真做',
    title: '违约合伙人',
    genre: '职场婚恋',
    setting: '顶尖红圈律师事务所，两位常年针锋相对的高级合伙人为拿下跨国并购重组大单，不得不对外假扮成恩爱订婚情侣。',
    characters: '宋青窈：高级合伙人，以逻辑冷静和诉讼胜率闻名，防御心极强。\n沈肆：并购部合伙人，外表儒雅从容，暗中布局守护多年。\n韩越：原告方老牌律所创始合伙人。',
    storyline: '在应对棘手的上市公司股权争夺战中，两人同进同出破除对方做局，却在一次深夜闭门核查中假戏真做。当案件大获全胜，两人才发现真正的契约早已刻在心底。',
    style: '现代职场轻熟风，智商在线，双强博弈，细腻克制，拉扯感极强',
    perspective: '第三人称',
    chapters: 10,
    per_words: 2400
  },
  {
    cat: 'female',
    icon: '🍵',
    label: '都市日常·海岛咖啡治愈手记',
    title: '我在离岛煮海风与咖啡',
    genre: '都市日常',
    setting: '南方避世小岛，废弃码头改建的旧灯塔咖啡馆，潮涨潮落，烟火慢调。',
    characters: '苏棠：大厂资深运营，经历严重职场内耗后辞职包下离岛小灯塔，专注研发特调手冲。\n陆屿白：沉静少言的岛民兼木工造船师，手艺出众，守候着家族旧船坞。',
    storyline: '随着小店营业，形形色色的疲惫旅人登岛带来属于他们的故事，苏棠与陆屿白从搭伙做木工到心照不宣地并肩看日落，在最平凡的日常中治愈了彼此的焦虑与过往。',
    style: '慢节奏治愈向，生活流，清新恬淡，海风烟火气，温暖微甜',
    perspective: '第三人称',
    chapters: 8,
    per_words: 2000
  },
  {
    cat: 'female',
    icon: '👭',
    label: '双女主·真假千金联手破局',
    title: '真假千金联手整顿豪门',
    genre: '双女主/互助',
    setting: '错换人生二十载的真假千金相认现场，没有狗血互撕，只有看透豪门利益盘剥后的联手反击。',
    characters: '盛栀：被豪门领养长大的假千金，深谙商战博弈与财阀规矩，冷静清醒。\n林知遥：在民间草根打拼出独立工作室的真千金，机敏坚韧，敢想敢拼。',
    storyline: '豪门试图让两人竞争牺牲联姻以挽救家族集团，二人一拍即合、暗中结成同盟。一个居内搜集暗账把柄，一个居外联手资本做空，合力夺回属于彼此的人生自主权与产业。',
    style: '双强互助，爽快高燃，清醒搞事业，女性友谊深刻细腻',
    perspective: '第三人称',
    chapters: 10,
    per_words: 2500
  },
  {
    cat: 'female',
    icon: '🩺',
    label: '破镜重圆·急诊重逢暗涌',
    title: '心跳骤停那一秒',
    genre: '破镜重圆',
    setting: '三甲医院急诊重症监护室与心外科，生死一线的抢救日常与多年前未解的心结。',
    characters: '江晚：心胸外科新锐主刀医生，冷静利落，对手术台有近乎执拗的专注。\n程序：知名医疗器械创新公司首席架构师，当年因误会不告而别，如今回国推动急救科研。',
    storyline: '一次重大车祸抢救现场，两人在重症监护室重逢。并肩挽救生命的无数个深夜里，当年的误会与不得已的牺牲被层层揭开，爱意从未熄灭。',
    style: '专业医疗背景，双向奔赴，破镜重圆，情感浓郁张力拉满',
    perspective: '第三人称',
    chapters: 10,
    per_words: 2200
  },
  {
    cat: 'female',
    icon: '🌾',
    label: '经商种田·江南第一锦绣行',
    title: '锦绣大掌柜：从织坊到御商',
    genre: '经商种田',
    setting: '架空古代江南水乡织锦世家，濒临破产的老字号织坊。',
    characters: '沈清漪：沈家嫡女，精通传统缂丝与天然草木染技艺，极具商业远见与决断力。\n裴景安：巡按御史，微服私访查探官盐与织造税案，清正内敛。',
    storyline: '面对族叔夺产与外商联合压价，沈清漪改良织机、研发创新云锦花样，带领全坊女工自立自强，一步步打破垄断，将沈氏织坊做到名扬四海的天下第一行。',
    style: '古言经商励志，传统非遗文化，群像生动，剧情扎实引人入胜',
    perspective: '第三人称',
    chapters: 12,
    per_words: 2400
  },
  {
    cat: 'female',
    icon: '📷',
    label: '百合纯爱·山海公路摄影手记',
    title: '风吹过三千公里的夏天',
    genre: '百合纯爱',
    setting: '西北大环线公路旅行，雪山、荒原、盐湖与公路尽头的漫天星河。',
    characters: '池月：自由人文摄影师，性格随性肆意，相机里装满人间烟火。\n闻青弦：严谨古板的野生植物学家，带着一册珍稀植物图鉴踏上寻种之旅。',
    storyline: '一辆二手越野车，两个性格迥异的女子同行三千公里。从最初的互不理解到彼此依偎度过无人区的狂风暴雨，在荒凉壮阔的大地上长出最纯粹动人的爱意。',
    style: '公路片质感，辽阔诗意，细腻慢热，双向救赎，治愈清新',
    perspective: '第一人称',
    chapters: 8,
    per_words: 2200
  },
  {
    cat: 'female',
    icon: '🔍',
    label: '刑侦推理·法医物证追凶',
    title: '骨语无声，白刃留痕',
    genre: '刑侦推理',
    setting: '市公安局刑侦支队物证鉴定中心，沉睡二十年的悬案档案室。',
    characters: '秦昭：省厅特聘法医病理学专家，洞察秋毫，能从微末痕迹中还原死者生前遭遇。\n陆停云：刑侦重案大队长，雷厉风行，擅长审讯心理学。',
    storyline: '一场旧城改造挖掘出的连环白骨案，引出横跨两代人的悬案网络。两人联手用现代法医学与严密逻辑链抽丝剥茧，突破重重阻力替逝者伸张正义。',
    style: '硬核刑侦，本格推理，法医物证细节考究，节奏扣人心弦',
    perspective: '第三人称',
    chapters: 12,
    per_words: 2600
  },
  {
    cat: 'fantasy',
    icon: '💾',
    label: '赛博朋克·记忆当铺典当师',
    title: '第九街区记忆当铺',
    genre: '赛博朋克',
    setting: '霓虹永夜的未来高耸下城，巨型财阀垄断意识上传，记忆成为最昂贵的硬通货。',
    characters: '顾言：老街记忆当铺的最后一位人工解析师，拥有罕见的非数字化神经突触。\n艾琳：被财阀除名的仿生义体赏金猎人，体内藏有一段被加密的记忆核心。',
    storyline: '当顾言收到一份典当期已过八十年却从未被赎回的财阀绝密记忆，全城的猎犬与改造人蜂拥而至。二人循着记忆裂隙逆流而上，揭开虚拟永生背后的惊天谎言。',
    style: '硬核科幻，赛博朋克，悬疑博弈，视听感强烈，反乌托邦内核',
    perspective: '第三人称',
    chapters: 10,
    per_words: 2500
  },
  {
    cat: 'fantasy',
    icon: '🚪',
    label: '无限流·我能看到隐藏禁令',
    title: '逃生游戏：通关准则在最后一页',
    genre: '无限流',
    setting: '高维文明构筑的规则怪谈副本世界，所有玩家必须在各类诡异规则中寻找一线生机。',
    characters: '季云川：逻辑怪才，在进入副本后觉醒「规则解构视界」，能看到被系统涂黑的隐藏准则。\n白薇：武力值爆表的冷兵器专精独行客。',
    storyline: '在《午夜血色列车》、《无尽回廊学校》等必死副本中，季云川一次次反向利用怪谈规则算计考官与幕后黑手，带领求生小队一步步逼近游戏世界的终极底层代码。',
    style: '智商碾压，规则怪谈，微恐悬疑，反转层出不穷，脑洞大开',
    perspective: '第三人称',
    chapters: 10,
    per_words: 2400
  },
  {
    cat: 'fantasy',
    icon: '❄️',
    label: '末世求生·全息恒温生态坞',
    title: '全球冰封：我打造了地下生态城',
    genre: '末世求生',
    setting: '地磁反转引发超低温冰川期，全球气温骤降至零下六十度，人类文明退守地下。',
    characters: '陆舟：空间物理学者兼资深机械极客，重生在极寒降临前三个月。\n唐雪：动植物种质资源库主管，精通低温无土栽培。',
    storyline: '带着前世遗憾与充足物资，陆舟利用地热与模块化工程在废弃矿井打造出坚不可摧的恒温避难生态坞。在文明秩序崩塌的严冬里，开创出属于幸存者的绿色奇迹。',
    style: '末世种田，硬核避难所基建，生存探索，爽感节奏分明',
    perspective: '第三人称',
    chapters: 10,
    per_words: 2200
  },
  {
    cat: 'fantasy',
    icon: '🔮',
    label: '都市异能·非人类社畜事务所',
    title: '妖怪事务所的考勤日常',
    genre: '都市异能',
    setting: '繁华都市写字楼地下一层，表面上是普通物业咨询公司，实则是管理局设立的非人类维稳办。',
    characters: '楚非：体质罕见的普通人类实习生，拥有能让一切法术失灵的「绝对绝缘」体质。\n九月：活了上千年的白狐大仙，沉迷喝奶茶和炒股的部门毒舌主管。',
    storyline: '每天处理偷溜进人类小学的饕餮幼崽、在地铁站画符扰民的千年旱魃，楚非一边为转正绩效奔波，一边用朴素的人类智慧化解一起起险些引爆两界的大危机。',
    style: '都市日常轻喜剧，脑洞轻小说，人妖共存，反差萌，轻松幽默',
    perspective: '第一人称',
    chapters: 8,
    per_words: 2000
  },
  {
    cat: 'fantasy',
    icon: '🏰',
    label: '西幻领主·现代工业魔法基建',
    title: '穷酸领主：从蒸汽机到魔法工业革命',
    genre: '西幻领主',
    setting: '剑与魔法的中世纪边缘贫瘠封地，魔兽横行，贵族盘剥，平民食不果腹。',
    characters: '罗恩：现代材料学与机械工程博士，意外穿越为偏远落魄小男爵。\n艾米莉：被教会追捕的逃亡火系魔法学者，对元素本质充满探求欲。',
    storyline: '当魔法元素遇上热力学定律，火球术成为高压锅炉的绝佳热源，风刃被改造成高精度机床。罗恩从冶铁筑城做起，带领贫瘠领地掀起轰轰烈烈的工业魔法革命。',
    style: '西幻种田基建，硬核推演，科技树攀爬，领主争霸，爽点十足',
    perspective: '第三人称',
    chapters: 12,
    per_words: 2600
  },
  {
    cat: 'fantasy',
    icon: '🗡️',
    label: '古风武侠·长安雨夜捉刀人',
    title: '捉刀人：长安不见天',
    genre: '古风武侠',
    setting: '盛唐暮色，江湖豪侠与朝堂权奸交织，暗流涌动的长安城。',
    characters: '李不言：独眼佩刀的退伍老卒，隐于市井的头号捉刀人，出手极快，刀无虚发。\n薛青衣：大理寺正，身负血仇，行事机敏孤勇。',
    storyline: '一桩离奇的胡商暴毙案牵扯出边疆军饷亏空与江湖顶级杀手谱。李不言受雇查探，在长安漫天细雨与朱红高墙之下，以一柄断刀斩断权贵翻云覆雨的阴谋。',
    style: '传统武侠风骨，刀光剑影，市井烟火，悬疑硬朗，家国情怀',
    perspective: '第三人称',
    chapters: 10,
    per_words: 2400
  }
];

function generateLocalTropes(category, genre, count) {
  let pool = [...BACKUP_TROPES_POOL, ...TROPE_TEMPLATES];
  if (category && category !== 'all') {
    pool = pool.filter(t => t.cat === category);
  }
  if (genre) {
    const matched = pool.filter(t => t.genre === genre || (t.genre && t.genre.includes(genre)) || (genre.includes(t.genre)));
    const rest = pool.filter(t => !matched.includes(t));
    matched.sort(() => Math.random() - 0.5);
    rest.sort(() => Math.random() - 0.5);
    pool = [...matched, ...rest];
  } else {
    pool.sort(() => Math.random() - 0.5);
  }
  return pool.slice(0, count || 5);
}

let currentTropeCat = 'all';
let currentTropesList = [...TROPE_TEMPLATES];

function renderTropeList() {
  const container = $('og_trope_pills');
  if (!container) return;

  // 严格过滤：杜绝任何未定义或空标签对象
  const validList = currentTropesList.filter(t => t && typeof t === 'object' && ((t.label && strVal(t.label)) || (t.title && strVal(t.title))));
  const filtered = currentTropeCat === 'all' 
    ? validList 
    : validList.filter(t => t.cat === currentTropeCat);

  container.innerHTML = filtered.map(t => {
    const origIdx = currentTropesList.indexOf(t);
    const labelText = escapeHtml(strVal(t.label || t.title) || '灵感脑洞');
    const iconText = escapeHtml(strVal(t.icon) || '💡');
    return `
      <button type="button" class="trope-pill" data-idx="${origIdx}">
        <span class="trope-icon">${iconText}</span>
        <span>${labelText}</span>
      </button>
    `;
  }).join('');

  container.querySelectorAll('.trope-pill').forEach(btn => {
    btn.onclick = () => {
      const idx = parseInt(btn.dataset.idx, 10);
      container.querySelectorAll('.trope-pill').forEach(b => b.classList.toggle('active', b === btn));
      applyTropeTemplate(currentTropesList[idx]);
    };
  });
}

async function refreshTropes() {
  const btn = $('btn_refresh_tropes');
  if (!btn) return;
  const origText = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = '<span class="rd-spin" style="width:11px;height:11px;border-width:2px;display:inline-block;vertical-align:middle;margin-right:4px;"></span>构思中…';

  try {
    const providerId = $('og_provider') ? $('og_provider').value : null;
    const currentGenre = $('og_genre') ? $('og_genre').value.trim() : '';

    let newTropes = [];
    let isFallback = false;
    let fallbackMsg = '';

    try {
      const res = await api('/api/suggest-tropes', 'POST', {
        category: currentTropeCat,
        genre: currentGenre,
        provider_id: providerId,
        count: 5
      });

      const raw = (res && Array.isArray(res.tropes)) ? res.tropes : [];
      // 严格清洗并校验每个脑洞对象
      const parsed = raw.filter(t => t && typeof t === 'object').map(t => {
        const title = strVal(t.title || t.book_name || t.name);
        const label = strVal(t.label || t.tag || title);
        if (!title && !label) return null;
        return {
          icon: strVal(t.icon) || '💡',
          label: label || title,
          title: title || label,
          genre: strVal(t.genre || t.category || currentGenre || '都市'),
          setting: strVal(t.setting || t.background),
          characters: strVal(t.characters || t.roles),
          storyline: strVal(t.storyline || t.plot || t.outline),
          style: strVal(t.style || '生动细腻，节奏明快'),
          perspective: strVal(t.perspective || '第三人称'),
          chapters: parseInt(t.chapters, 10) || 10,
          per_words: parseInt(t.per_words, 10) || 2200,
          cat: t.cat || (currentTropeCat === 'all' ? 'female' : currentTropeCat)
        };
      }).filter(Boolean);

      if (parsed.length) {
        newTropes = parsed.slice(0, 6);
      }
    } catch (apiErr) {
      console.warn('API /api/suggest-tropes 请求未成功，切换为备选智能构思库：', apiErr);
      isFallback = true;
      if (apiErr && (apiErr.message || '').includes('404')) {
        fallbackMsg = '后端服务尚未重启（404），已先行为您动态生成精选灵感！在命令行重启 python app.py 即可启用大模型实时生成。';
      } else {
        fallbackMsg = '大模型调用波动，已动态切换为备选脑洞库为您生成新灵感！';
      }
      newTropes = generateLocalTropes(currentTropeCat, currentGenre, 5);
    }

    if (!newTropes.length) {
      newTropes = generateLocalTropes(currentTropeCat, currentGenre, 5);
      isFallback = true;
    }

    newTropes.forEach(t => {
      if (!t.cat) t.cat = currentTropeCat === 'all' ? (t.cat || 'female') : currentTropeCat;
    });

    // 动态灵感直接置于前列，去重展示，最多保留前 30 个脑洞
    const combined = [...newTropes, ...currentTropesList];
    const seenTitles = new Set();
    currentTropesList = combined.filter(t => {
      if (!t || typeof t !== 'object') return false;
      const key = strVal(t.title || t.label);
      if (!key || seenTitles.has(key)) return false;
      seenTitles.add(key);
      return true;
    }).slice(0, 30);

    renderTropeList();

    if (isFallback) {
      toast(fallbackMsg || '已动态生成一批新灵感脑洞！');
    } else {
      toast(`已由 AI 实时生成 ${newTropes.length} 个新灵感脑洞！`);
    }
  } catch (e) {
    toast(`生成新脑洞失败：${e.message}`);
  } finally {
    btn.disabled = false;
    btn.innerHTML = origText;
  }
}

function initTropeTemplates() {
  const catTabs = document.querySelectorAll('#og_trope_cat_tabs .trope-cat-tab');
  catTabs.forEach(tab => {
    tab.onclick = () => {
      catTabs.forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      currentTropeCat = tab.dataset.cat || 'all';
      renderTropeList();
    };
  });

  renderTropeList();

  const refreshBtn = $('btn_refresh_tropes');
  if (refreshBtn) {
    refreshBtn.onclick = refreshTropes;
  }

  const randBtn = $('btn_random_trope');
  if (randBtn) {
    randBtn.onclick = () => {
      const candidates = currentTropeCat === 'all'
        ? currentTropesList
        : currentTropesList.filter(t => t.cat === currentTropeCat);
      if (!candidates.length) return;
      const chosen = candidates[Math.floor(Math.random() * candidates.length)];
      const origIdx = currentTropesList.indexOf(chosen);
      applyTropeTemplate(chosen);
      const pill = document.querySelector(`#og_trope_pills .trope-pill[data-idx="${origIdx}"]`);
      if (pill) {
        document.querySelectorAll('#og_trope_pills .trope-pill').forEach(b => b.classList.toggle('active', b === pill));
        pill.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' });
      }
    };
  }
}

initTropeTemplates();

// ==================== P2: 原创表单分步向导 (Stepper) ====================
let currentOriginalStep = 1;

function goToOriginalStep(step) {
  currentOriginalStep = Math.max(1, Math.min(3, step));
  try { sessionStorage.setItem('og_current_step', String(currentOriginalStep)); } catch (e) {}

  // 1. 切换面板显隐
  ['og_step_1', 'og_step_2', 'og_step_3'].forEach((id, idx) => {
    const p = $(id);
    if (p) p.style.display = (idx + 1 === currentOriginalStep) ? 'block' : 'none';
  });

  // 2. 更新向导条样式
  const bar = $('og_stepper_bar');
  if (bar) {
    bar.querySelectorAll('.stepper-step').forEach(s => {
      const sNum = parseInt(s.dataset.step, 10);
      s.classList.toggle('active', sNum === currentOriginalStep);
      s.classList.toggle('done', sNum < currentOriginalStep);
    });
  }
}

function initOriginalStepper() {
  const bar = $('og_stepper_bar');
  if (bar) {
    bar.querySelectorAll('.stepper-step').forEach(s => {
      s.onclick = () => {
        const targetStep = parseInt(s.dataset.step, 10);
        goToOriginalStep(targetStep);
      };
    });
  }

  const b1Next = $('btn_step1_next');
  if (b1Next) b1Next.onclick = () => {
    const setting = $('og_setting').value.trim();
    const genre = $('og_genre').value.trim();
    if (!setting && !genre && !$('og_title').value.trim()) {
      toast('请先输入故事背景/题材，或点击上方灵感脑洞库一键填入');
      return;
    }
    goToOriginalStep(2);
  };

  const b2Prev = $('btn_step2_prev');
  if (b2Prev) b2Prev.onclick = () => goToOriginalStep(1);

  const b2Next = $('btn_step2_next');
  if (b2Next) b2Next.onclick = () => goToOriginalStep(3);

  const b3Prev = $('btn_step3_prev');
  if (b3Prev) b3Prev.onclick = () => goToOriginalStep(2);

  const bWriteAll = $('btn_write_all');
  if (bWriteAll) {
    bWriteAll.onclick = async () => {
      if (currentOutline) {
        $('btn_write').click();
        return;
      }
      const payload = originalPayload();
      bWriteAll.disabled = true;
      setStatus('og_status', '正在启动全书生成任务…');
      try {
        const d = await api('/api/generate', 'POST', payload);
        startPolling('og', d.job_id, 'og_progress_card', payload.title || '原创小说');
      } catch (e) {
        toast('生成失败：' + e.message);
      } finally {
        bWriteAll.disabled = false;
        setStatus('og_status', '');
      }
    };
  }

  let savedStep = 1;
  try { savedStep = parseInt(sessionStorage.getItem('og_current_step') || '1', 10); } catch (e) {}
  goToOriginalStep(savedStep || 1);
}
initOriginalStepper();

on('btn_suggest_titles', async () => {
  const btn = $('btn_suggest_titles');
  btn.disabled = true;
  btn.textContent = '✨ 拟名中…';
  try {
    const d = await api('/api/suggest-titles', 'POST', originalPayload());
    btn.textContent = '✨ AI 拟名';
    btn.disabled = false;
    const list = $('og_title_list');
    const candWrap = $('og_title_candidates');
    if (d.titles && d.titles.length) {
      candWrap.style.display = 'block';
      list.innerHTML = d.titles.map(t => `<button type="button" class="tag-pill" data-title="${escapeHtml(t)}">${escapeHtml(t)}</button>`).join('');
      list.querySelectorAll('.tag-pill').forEach(b => {
        b.onclick = () => {
          $('og_title').value = b.dataset.title;
          list.querySelectorAll('.tag-pill').forEach(p => p.classList.toggle('active', p === b));
        };
      });
      if (!$('og_title').value.trim()) {
        $('og_title').value = d.titles[0];
        const firstPill = list.querySelector('.tag-pill');
        if (firstPill) firstPill.classList.add('active');
      }
    }
  } catch (e) {
    btn.textContent = '✨ AI 拟名';
    btn.disabled = false;
    toast('拟名失败：' + e.message);
  }
});

// ==================== 设定档案 (World Bible) 可视化编辑 ====================
let currentBible = null;

function renderBibleEditor(bible) {
  currentBible = bible || {};
  $('og_bible_setting').value = currentBible.setting || '';
  $('og_bible_conflict').value = currentBible.conflict || '';
  $('og_bible_tone').value = currentBible.tone || '';
  syncBibleRawJson();

  const chars = Array.isArray(currentBible.characters) ? currentBible.characters : [];
  renderBibleCharCards(chars);
  $('og_bible_card').style.display = 'block';
}

function renderBibleCharCards(chars) {
  const box = $('og_bible_chars');
  if (!chars.length) {
    box.innerHTML = '<p class="mini" style="color:var(--muted);padding:8px 0;">暂无角色档案，点击「+ 添加角色」进行补充</p>';
    return;
  }
  box.innerHTML = chars.map((c, i) => `
    <div class="char-card" data-idx="${i}">
      <div class="char-card-hd">
        <input type="text" class="char-name" value="${escapeHtml(c.name || '')}" placeholder="角色姓名">
        <input type="text" class="char-role" value="${escapeHtml(c.role || '')}" placeholder="身份/定位（如：主角 / 宿敌）">
        <button type="button" class="btn-oc-action danger" data-act="del-char" title="删除角色" aria-label="删除角色">×</button>
      </div>
      <div class="char-card-bd">
        <input type="text" class="char-desc" value="${escapeHtml(c.desc || '')}" placeholder="性格特征、外貌或核心能力…">
        <input type="text" class="char-goal" value="${escapeHtml(c.goal || '')}" placeholder="核心动机、追求目标或与主角的关系…">
      </div>
    </div>`).join('');

  box.querySelectorAll('.char-card').forEach(card => {
    const idx = parseInt(card.dataset.idx);
    card.querySelector('[data-act=del-char]').onclick = () => {
      const b = collectBible();
      b.characters.splice(idx, 1);
      renderBibleCharCards(b.characters);
      syncBibleRawJson();
    };
    card.querySelectorAll('input').forEach(inp => {
      inp.oninput = syncBibleRawJson;
    });
  });
}

function collectBible() {
  const chars = [...$('og_bible_chars').querySelectorAll('.char-card')].map(card => ({
    name: card.querySelector('.char-name').value.trim(),
    role: card.querySelector('.char-role').value.trim(),
    desc: card.querySelector('.char-desc').value.trim(),
    goal: card.querySelector('.char-goal').value.trim(),
  })).filter(c => c.name || c.role || c.desc);

  return {
    setting: $('og_bible_setting').value.trim(),
    characters: chars,
    conflict: $('og_bible_conflict').value.trim(),
    tone: $('og_bible_tone').value.trim(),
  };
}

function syncBibleRawJson() {
  const data = collectBible();
  const rawEl = $('og_bible_raw');
  if (rawEl) rawEl.value = JSON.stringify(data, null, 2);
}

on('btn_add_bible_char', () => {
  const b = collectBible();
  b.characters.push({ name: '', role: '', desc: '', goal: '' });
  renderBibleCharCards(b.characters);
  syncBibleRawJson();
});

on('btn_toggle_bible_raw', () => {
  const el = $('og_bible_raw');
  if (!el) return;
  const isHidden = el.style.display === 'none';
  el.style.display = isHidden ? 'block' : 'none';
  if ($('btn_toggle_bible_raw')) {
    $('btn_toggle_bible_raw').textContent = isHidden ? '收起原始 JSON' : '查看原始 JSON';
  }
});

// ==================== 原创生成 ====================
let currentOutline = null;

function originalPayload() {
  return {
    mode: 'original',
    title: $('og_title').value.trim(),
    genre: $('og_genre').value.trim(),
    setting: $('og_setting').value.trim(),
    characters: $('og_characters').value.trim(),
    storyline: $('og_storyline').value.trim(),
    style: $('og_style').value.trim(),
    perspective: $('og_perspective').value,
    chapters: parseInt($('og_chapters').value) || 10,
    per_chapter_words: parseInt($('og_per_words').value) || 1500,
    extra: $('og_extra').value.trim(),
    provider_id: $('og_provider').value,
  };
}

// ---- 表单自动草稿（防刷新丢失）----
const OG_DRAFT_KEY = 'og_draft_v1';
function ogDraft() {
  const ids = ['og_title','og_genre','og_setting','og_characters','og_storyline','og_style',
               'og_perspective','og_chapters','og_per_words','og_extra'];
  const d = {};
  ids.forEach(id => { const el = $(id); if (el) d[id] = el.value; });
  return d;
}
function restoreOgDraft() {
  try {
    const d = JSON.parse(localStorage.getItem(OG_DRAFT_KEY) || 'null');
    if (!d) return;
    Object.entries(d).forEach(([id, v]) => { const el = $(id); if (el && v !== undefined && v !== null) el.value = v; });
    syncGenrePillsFromInput();
  } catch (e) { /* 忽略 */ }
}
let ogDraftTimer = null;
['og_title','og_genre','og_setting','og_characters','og_storyline','og_style',
 'og_perspective','og_chapters','og_per_words','og_extra'].forEach(id => {
  const el = $(id);
  if (!el) return;
  el.addEventListener('input', () => {
    clearTimeout(ogDraftTimer);
    ogDraftTimer = setTimeout(() => {
      try { localStorage.setItem(OG_DRAFT_KEY, JSON.stringify(ogDraft())); } catch (e) {}
    }, 500);
  });
});
on('btn_clear_og', () => {
  if (!confirm('确定清空本页所有输入？（不会影响已生成的小说）')) return;
  ['og_title','og_genre','og_setting','og_characters','og_storyline','og_style','og_extra'].forEach(id => {
    const el = $(id); if (el) el.value = '';
  });
  $('og_perspective').value = '第三人称';
  $('og_chapters').value = 10;
  $('og_per_words').value = 1500;
  syncGenrePillsFromInput();
  const tWrap = $('og_trope_pills');
  if (tWrap) tWrap.querySelectorAll('.trope-pill').forEach(p => p.classList.remove('active'));
  try { localStorage.removeItem(OG_DRAFT_KEY); } catch (e) {}
  toast('已清空本页表单');
});

// ---- 大纲可视化编辑 ----
let ogTimer = null;

function syncOutlineJsonView() {
  const data = collectOutline();
  const txt = $('og_outline_text');
  if (txt) txt.value = JSON.stringify(data, null, 2);
  const cnt = $('og_ch_count');
  if (cnt) cnt.textContent = String(data.chapters.length);
}

function renderOutlineEditor(outline) {
  currentOutline = outline;
  $('og_logline_input').value = (outline && outline.logline) || '';
  const chs = Array.isArray(outline && outline.chapters) ? outline.chapters : [];
  const cnt = $('og_ch_count');
  if (cnt) cnt.textContent = String(chs.length);
  const container = $('og_outline_editor');
  if (!chs.length) {
    container.innerHTML = '<p class="mini" style="padding:16px 0;text-align:center;color:var(--muted)">大纲暂无章节，请点击下方「添加一章」或重新生成</p>';
  } else {
    container.innerHTML = chs.map((c, i) => {
      const title = typeof c === 'string' ? c : (c && c.title) || ('第' + (i + 1) + '章');
      const points = typeof c === 'string' ? '' : (c && c.points) || '';
      return `
      <div class="outline-ch" data-idx="${i}">
        <div class="outline-ch-hd">
          <span class="outline-ch-badge">第 ${i + 1} 章</span>
          <div class="outline-ch-actions">
            <button type="button" class="btn-oc-action" data-act="up" title="上移" aria-label="上移本章"${i === 0 ? ' disabled' : ''}>↑</button>
            <button type="button" class="btn-oc-action" data-act="down" title="下移" aria-label="下移本章"${i === chs.length - 1 ? ' disabled' : ''}>↓</button>
            <button type="button" class="btn-oc-action danger" data-act="del" title="删除本章" aria-label="删除本章">×</button>
          </div>
        </div>
        <div class="outline-ch-body">
          <div>
            <label>章节标题</label>
            <input type="text" class="oc-title" value="${escapeHtml(title)}" placeholder="第 ${i + 1} 章 标题">
          </div>
          <div style="margin-top:8px">
            <label>本章要点</label>
            <textarea class="oc-points" rows="2" placeholder="本章关键情节、转折或伏笔…">${escapeHtml(points)}</textarea>
          </div>
        </div>
      </div>`;
    }).join('');
  }

  container.querySelectorAll('.outline-ch').forEach(card => {
    const idx = parseInt(card.dataset.idx);
    const upBtn = card.querySelector('[data-act=up]');
    if (upBtn) {
      upBtn.onclick = () => {
        const cur = collectOutline();
        if (idx > 0 && idx < cur.chapters.length) {
          const temp = cur.chapters[idx];
          cur.chapters[idx] = cur.chapters[idx - 1];
          cur.chapters[idx - 1] = temp;
          renderOutlineEditor(cur);
        }
      };
    }
    const downBtn = card.querySelector('[data-act=down]');
    if (downBtn) {
      downBtn.onclick = () => {
        const cur = collectOutline();
        if (idx >= 0 && idx < cur.chapters.length - 1) {
          const temp = cur.chapters[idx];
          cur.chapters[idx] = cur.chapters[idx + 1];
          cur.chapters[idx + 1] = temp;
          renderOutlineEditor(cur);
        }
      };
    }
    const delBtn = card.querySelector('[data-act=del]');
    if (delBtn) {
      delBtn.onclick = () => {
        const cur = collectOutline();
        cur.chapters.splice(idx, 1);
        renderOutlineEditor(cur);
      };
    }
    const titleInp = card.querySelector('.oc-title');
    const pointsInp = card.querySelector('.oc-points');
    if (titleInp) titleInp.oninput = syncOutlineJsonView;
    if (pointsInp) pointsInp.oninput = syncOutlineJsonView;
  });

  const loglineInp = $('og_logline_input');
  if (loglineInp) loglineInp.oninput = syncOutlineJsonView;
  syncOutlineJsonView();
}

function collectOutline() {
  const chs = [...$('og_outline_editor').querySelectorAll('.outline-ch')].map(el => ({
    title: el.querySelector('.oc-title').value.trim(),
    points: el.querySelector('.oc-points').value.trim(),
  }));
  return { logline: $('og_logline_input').value.trim(), chapters: chs };
}

on('btn_add_outline_ch', () => {
  const cur = collectOutline();
  const nextIdx = cur.chapters.length + 1;
  cur.chapters.push({ title: '第 ' + nextIdx + ' 章', points: '' });
  renderOutlineEditor(cur);
});

on('btn_outline', async () => {
  const btn = $('btn_outline');
  btn.disabled = true;
  const startAt = Date.now();
  setStatus('og_status', '<span class="heartbeat-pulse"></span>正在构建设定集与大纲（已用时 0s）…');
  clearInterval(ogTimer);
  ogTimer = setInterval(() => {
    const sec = Math.floor((Date.now() - startAt) / 1000);
    setStatus('og_status', `<span class="heartbeat-pulse"></span>正在构建设定集与大纲（已用时 ${sec}s）…`);
  }, 1000);
  try {
    const payload = originalPayload();
    // 1. 生成设定集（世界观背景 + 角色档案 + 拟定书名）
    const bibleRes = await api('/api/generate-bible', 'POST', payload);
    const bible = (bibleRes && bibleRes.bible) || {};
    if (bible.suggested_title && !$('og_title').value.trim()) {
      $('og_title').value = bible.suggested_title;
    }
    if (bible.candidate_titles && bible.candidate_titles.length) {
      const candWrap = $('og_title_candidates');
      const list = $('og_title_list');
      candWrap.style.display = 'block';
      list.innerHTML = bible.candidate_titles.map(t => `<button type="button" class="tag-pill" data-title="${escapeHtml(t)}">${escapeHtml(t)}</button>`).join('');
      list.querySelectorAll('.tag-pill').forEach(b => {
        b.onclick = () => {
          $('og_title').value = b.dataset.title;
          list.querySelectorAll('.tag-pill').forEach(p => p.classList.toggle('active', p === b));
        };
      });
    }
    renderBibleEditor(bible);

    // 2. 生成大纲（注入生成的设定）
    payload.bible = bible;
    payload.title = $('og_title').value.trim() || bible.suggested_title || '';
    const outlineRes = await api('/api/outline', 'POST', payload);
    clearInterval(ogTimer);
    currentOutline = outlineRes.outline;
    renderOutlineEditor(outlineRes.outline);
    $('og_outline_card').style.display = 'block';
    $('btn_write').disabled = false;
    setStatus('og_status', '设定集与大纲已就绪，可随时修改后开始写作');
  } catch (e) {
    clearInterval(ogTimer);
    setStatus('og_status', '规划失败：' + e.message);
    toast(e.message);
  } finally {
    btn.disabled = false;
  }
});
on('btn_regenerate', () => {
  const btn = $('btn_outline');
  if (btn) btn.click();
});

on('btn_write', async () => {
  const payload = originalPayload();
  try {
    payload.title = $('og_title').value.trim() || '未命名小说';
    payload.outline = JSON.stringify(collectOutline(), null, 2);
    payload.bible = collectBible();
  } catch (e) { toast('大纲或设定数据不完整：' + e.message); return; }
  try {
    const d = await api('/api/generate', 'POST', payload);
    startPolling('og', d.job_id, 'og_progress_card', payload.title || '未命名小说');
  } catch (e) { toast(e.message); }
});


// ==================== 续写 / 同人 ====================
let styleProfile = null;

function continuationPayload() {
  return {
    mode: $('ct_mode').value,
    source_title: $('ct_source_title').value.trim(),
    source_author: $('ct_source_author').value.trim(),
    source_intro: $('ct_source_intro').value.trim(),
    source_text: $('ct_source_text').value,
    start_para: parseInt($('ct_start_para').value) || 0,
    twist: $('ct_twist').value.trim(),
    chapters: parseInt($('ct_chapters').value) || 1,
    per_chapter_words: parseInt($('ct_per_words').value) || 3000,
    extra: $('ct_extra').value.trim(),
    provider_id: $('ct_provider').value,
  };
}

// 段落切分规则与后端 split_source_paragraphs 保持一致：空行分段优先，单换行退化按行
function splitParagraphs(t) {
  const blank = t.split(/\n\s*\n/).map(s => s.trim()).filter(Boolean);
  if (blank.length > 1) return blank;
  return t.split(/\n+/).map(s => s.trim()).filter(Boolean);
}

function countParagraphs() {
  const t = $('ct_source_text').value.trim();
  const hint = $('ct_para_hint');
  const num = $('ct_start_para');
  if (!t) {
    hint.textContent = '';
    if (num) num.max = 0;
    updateShortHint();
    return;
  }
  const paras = splitParagraphs(t);
  if (num) {
    num.max = paras.length;
    if (parseInt(num.value) > paras.length) num.value = paras.length;
  }
  hint.textContent = '已识别 ' + paras.length + ' 个段落（0 = 从文末继续）';
  updateShortHint();
}

// 短文本（<=2000 字）可不经「通读全书」直接续写：后端会自动做快速风格分析
function updateShortHint() {
  const t = $('ct_source_text').value.trim();
  const btn = $('btn_continue');
  const status = $('ct_status');
  if (!styleProfile && t && t.length <= 2000) {
    btn.disabled = false;
    status.textContent = '文本较短，可直接「开始续写」（将自动快速分析风格）';
  } else if (!styleProfile && !t) {
    btn.disabled = true;
    status.textContent = '';
  }
}
on('ct_source_text', 'input', countParagraphs);

on('ct_file', 'change', e => {
  const f = e.target.files[0]; if (!f) return;
  const rd = new FileReader();
  rd.onload = () => {
    const buf = rd.result;
    let text = null, enc = 'UTF-8';
    try { text = new TextDecoder('utf-8', { fatal: true }).decode(buf); }
    catch (err) {
      try { text = new TextDecoder('gb18030').decode(buf); enc = 'GBK/GB18030'; }
      catch (err2) { text = null; }
    }
    if (text === null) { toast('无法识别文件编码'); return; }
    $('ct_source_text').value = text;
    countParagraphs();
    toast('已读取文件（' + enc + '）');
  };
  rd.onerror = () => toast('读取文件失败');
  rd.readAsArrayBuffer(f);
});

// ----- 1 通读全书（job 化，带进度） -----
function renderStyleProfile(profile, targetEl = null) {
  const box = targetEl || $('ct_style_summary');
  const secs = [
    ['文风', profile.文风], ['叙事视角', profile.叙事视角], ['语言特色', profile.语言特色],
    ['当前剧情状态', profile.当前剧情状态], ['伏笔与线索', profile.伏笔与线索], ['续写要点', profile.续写要点],
  ];
  let html = '';
  for (const [k, v] of secs) {
    if (!v) continue;
    const val = Array.isArray(v) ? v.join('\n') : (typeof v === 'object' ? JSON.stringify(v, null, 2) : String(v));
    html += `<div class="profile-sec"><b>${k}</b><p>${escapeHtml(val)}</p></div>`;
  }
  const chars = profile.人物表;
  if (Array.isArray(chars) && chars.length) {
    html += `<div class="profile-sec"><b>人物表</b>`;
    chars.forEach(c => {
      if (!c) return;
      html += `<p>· ${escapeHtml(String(c.姓名 || c.name || ''))}${c.身份 ? '（' + escapeHtml(String(c.身份)) + '）' : ''}：${escapeHtml(String(c.性格 || c.当前状态 || ''))}</p>`;
    });
    html += `</div>`;
  }
  const naming = profile.章节命名规律;
  if (naming) {
    const desc = typeof naming === 'object' ? (naming.风格描述 || '') : String(naming);
    const samples = typeof naming === 'object' && Array.isArray(naming.标题样例) ? naming.标题样例 : [];
    html += `<div class="profile-sec"><b>章节命名规律</b><p>${escapeHtml(String(desc))}${samples.length ? '\n样例：' + samples.map(s => escapeHtml(String(s))).join(' / ') : ''}</p></div>`;
  }
  if (profile.备注) html += `<div class="profile-sec"><b>备注</b><p>${escapeHtml(String(profile.备注))}</p></div>`;
  box.innerHTML = html || '<p class="mini">（档案内容为空）</p>';
}

// 解析可能为字符串或对象的风格档案（兼容旧数据）
function parseStyleProfile(sp) {
  if (!sp) return null;
  if (typeof sp === 'object') return sp;
  try { return JSON.parse(sp); } catch (e) { return null; }
}

on('btn_analyze', async () => {
  const btn = $('btn_analyze'); btn.disabled = true;
  setStatus('ct_status', '通读分析中…');
  $('ct_analyze_progress').style.display = 'block';
  setBar('ct_analyze_bar', 0);
  $('ct_analyze_text').textContent = '准备中…';
  const cancelBtn = $('ct_analyze_cancel');
  try {
    const d = await api('/api/analyze', 'POST', continuationPayload());
    cancelBtn.style.display = 'inline-block';
    cancelBtn.onclick = async () => {
      try { await api('/api/jobs/' + d.job_id + '/cancel', 'POST'); toast('已发送取消请求…'); }
      catch (e) { toast(e.message); }
    };
    const t0 = Date.now();
    let failCount = 0;
    const timer = setInterval(async () => {
      try {
        const j = await api('/api/jobs/' + d.job_id);
        failCount = 0;
        const pct = j.total ? Math.round(j.current / j.total * 100) : 0;
        setBar('ct_analyze_bar', pct);
        let txt = j.step || '';
        if (j.total > 2) {
          txt += `（${j.current}/${j.total}）`;
          if (j.chars_total) {
            const doneW = Math.round((j.chars_done || 0) / 10000 * 10) / 10;
            const totalW = Math.round(j.chars_total / 10000 * 10) / 10;
            txt += ` · 已读 ${doneW} 万字/共 ${totalW} 万字`;
          }
          if (j.eta > 0) txt += ` · 预计还需约 ${j.eta >= 60 ? Math.round(j.eta / 60) + ' 分钟' : j.eta + ' 秒'}`;
          else if (j.status === 'running') txt += ` · 已用时 ${Math.round((Date.now() - t0) / 1000)} 秒`;
        }
        $('ct_analyze_text').textContent = txt;
        if (j.status === 'done') {
          clearInterval(timer); cancelBtn.style.display = 'none';
          styleProfile = j.result || null;
          if (styleProfile) {
            renderStyleProfile(styleProfile);
            $('ct_style_box').textContent = JSON.stringify(styleProfile, null, 2);
            $('ct_style_card').style.display = 'block';
            renderCtBibleEditor(profileToBible(styleProfile));
            $('btn_continue').disabled = false;
            if ($('btn_continue_variants')) $('btn_continue_variants').disabled = false;
            // 按书名持久化档案，刷新后自动恢复查看
            const srcTitle = $('ct_source_title').value.trim() || '未命名';
            try { localStorage.setItem('novel_profile_' + srcTitle, JSON.stringify(styleProfile)); } catch (e) {}
            const step = j.step || '';
            if (step.includes('命中缓存')) setStatus('ct_status', '分析结果已命中缓存（未重新消耗额度）');
            else if (step.includes('已沿用本书档案')) setStatus('ct_status', '已复用本书已保存的创作档案（未重新消耗额度）');
            else setStatus('ct_status', '全书通读完成，可开始续写');
          } else {
            setStatus('ct_status', '分析结果为空（模型未返回有效档案），请点击「重新通读分析」重试');
            toast('分析结果为空，请重试');
          }
        } else if (j.status === 'error') {
          clearInterval(timer); cancelBtn.style.display = 'none';
          setStatus('ct_status', '失败：' + j.message); toast('通读失败：' + j.message);
        } else if (j.status === 'cancelled') {
          clearInterval(timer); cancelBtn.style.display = 'none';
          setStatus('ct_status', '分析已取消');
        }
      } catch (e) {
        failCount++;
        if (failCount >= 6) {
          clearInterval(timer); cancelBtn.style.display = 'none';
          $('ct_analyze_text').textContent = '生成服务连接中断（可能已重启）。刷新页面后重试。';
          setStatus('ct_status', '生成服务连接中断');
          toast('通读服务连接中断');
        }
      }
    }, 1200);
  } catch (e) { setStatus('ct_status', '失败：' + e.message); toast(e.message); }
  btn.disabled = false;
});
on('btn_reanalyze', () => {
  const btn = $('btn_analyze');
  if (btn) btn.click();
});

// ==================== 续写设定档案 (Bible) 编辑器 ====================
function renderCtBibleEditor(bible) {
  const b = bible || {};
  $('ct_bible_setting').value = b.setting || '';
  $('ct_bible_conflict').value = b.conflict || '';
  $('ct_bible_tone').value = b.tone || '';
  renderCtBibleCharCards(b.characters || []);
  syncCtBibleRawJson();
  $('ct_bible_card').style.display = 'block';
}

function renderCtBibleCharCards(chars) {
  const box = $('ct_bible_chars');
  if (!chars.length) {
    box.innerHTML = '<p class="mini" style="color:var(--muted);padding:8px 0;">暂无角色档案，点击「+ 添加角色」进行补充</p>';
    return;
  }
  box.innerHTML = chars.map((c, i) => `
    <div class="char-card" data-idx="${i}">
      <div class="char-card-hd">
        <input type="text" class="char-name" value="${escapeHtml(c.name || '')}" placeholder="角色姓名">
        <input type="text" class="char-role" value="${escapeHtml(c.role || '')}" placeholder="身份/定位（如：主角 / 盟友）">
        <button type="button" class="btn-oc-action danger" data-act="del-char" title="删除角色" aria-label="删除角色">×</button>
      </div>
      <div class="char-card-bd">
        <input type="text" class="char-desc" value="${escapeHtml(c.desc || '')}" placeholder="性格特征、外貌或现状…">
        <input type="text" class="char-goal" value="${escapeHtml(c.goal || '')}" placeholder="当前目标、关系或行动动机…">
      </div>
    </div>`).join('');

  box.querySelectorAll('.char-card').forEach(card => {
    const idx = parseInt(card.dataset.idx);
    card.querySelector('[data-act=del-char]').onclick = () => {
      const b = collectCtBible();
      b.characters.splice(idx, 1);
      renderCtBibleCharCards(b.characters);
      syncCtBibleRawJson();
    };
    card.querySelectorAll('input').forEach(inp => {
      inp.oninput = syncCtBibleRawJson;
    });
  });
}

function collectCtBible() {
  const chars = [...$('ct_bible_chars').querySelectorAll('.char-card')].map(card => ({
    name: card.querySelector('.char-name').value.trim(),
    role: card.querySelector('.char-role').value.trim(),
    desc: card.querySelector('.char-desc').value.trim(),
    goal: card.querySelector('.char-goal').value.trim(),
  })).filter(c => c.name || c.role || c.desc);

  return {
    setting: $('ct_bible_setting').value.trim(),
    characters: chars,
    conflict: $('ct_bible_conflict').value.trim(),
    tone: $('ct_bible_tone').value.trim(),
  };
}

function syncCtBibleRawJson() {
  const data = collectCtBible();
  const rawEl = $('ct_bible_raw');
  if (rawEl) rawEl.value = JSON.stringify(data, null, 2);
}

on('btn_add_ct_bible_char', () => {
  const b = collectCtBible();
  b.characters.push({ name: '', role: '', desc: '', goal: '' });
  renderCtBibleCharCards(b.characters);
  syncCtBibleRawJson();
});

on('btn_toggle_ct_bible_raw', () => {
  const el = $('ct_bible_raw');
  if (!el) return;
  const isHidden = el.style.display === 'none';
  el.style.display = isHidden ? 'block' : 'none';
  if ($('btn_toggle_ct_bible_raw')) {
    $('btn_toggle_ct_bible_raw').textContent = isHidden ? '收起原始 JSON' : '查看原始 JSON';
  }
});

function profileToBible(sp) {
  if (!sp) return { setting: '', characters: [], conflict: '', tone: '' };
  const rawChars = sp['人物表'] || sp.characters || [];
  const chars = Array.isArray(rawChars) ? rawChars.map(c => ({
    name: c.姓名 || c.name || '',
    role: c.身份 || c.role || '',
    desc: c.性格 || c.当前状态 || c.desc || '',
    goal: c.关系 || c.goal || '',
  })) : [];
  let setting = '';
  if (sp['当前剧情状态']) {
    setting = Array.isArray(sp['当前剧情状态']) ? sp['当前剧情状态'].join('\n') : String(sp['当前剧情状态']);
  }
  let conflict = '';
  if (sp['续写要点']) {
    conflict = Array.isArray(sp['续写要点']) ? sp['续写要点'].join('；') : String(sp['续写要点']);
  }
  let tone = '';
  if (sp['文风']) {
    tone = String(sp['文风']);
  }
  return { setting, characters: chars, conflict, tone };
}

// ==================== P2: 续写 2 选 1 候选小样流程 ====================
async function runVariantsFlow(payload) {
  const wrap = $('ct_variants_wrap');
  const cardsBox = $('ct_variants_cards');
  if (!wrap || !cardsBox) return;

  wrap.style.display = 'block';
  cardsBox.innerHTML = '<div style="grid-column:1/-1;text-align:center;padding:24px;color:var(--muted);"><span class="rd-spin"></span> 正在构思两种不同走向的剧情小样…</div>';

  try {
    const res = await api('/api/generate-variants', 'POST', {
      novel_name: payload.novel_name || payload.source_title,
      instruction: payload.instruction || payload.extra || '顺应情节推进下章',
      provider_id: payload.provider_id
    });
    const variants = (res && res.variants) || [];
    if (!variants.length) throw new Error('未返回有效小样');

    cardsBox.innerHTML = variants.map(v => `
      <div class="variant-card" data-id="${v.id}">
        <div>
          <div class="variant-card-head">
            <span class="variant-card-title">${escapeHtml(v.title || ('走向 ' + v.id))}</span>
            <span class="variant-badge">方向 ${v.id}</span>
          </div>
          <div class="variant-card-synopsis">${escapeHtml(v.synopsis || '')}</div>
          <div class="variant-card-preview">${escapeHtml(v.preview || '')}</div>
        </div>
        <button type="button" class="primary variant-select-btn">选用此走向继续写 →</button>
      </div>
    `).join('');

    cardsBox.querySelectorAll('.variant-card').forEach((card, idx) => {
      const v = variants[idx];
      const chooseBtn = card.querySelector('.variant-select-btn');
      chooseBtn.onclick = async (e) => {
        e.stopPropagation();
        chooseBtn.disabled = true;
        chooseBtn.textContent = '启动生成中…';
        const addInst = `【采纳剧情走向】：${v.title}。${v.preview}`;
        payload.instruction = (payload.instruction ? payload.instruction + '\n\n' : '') + addInst;
        wrap.style.display = 'none';
        try {
          const d = await api('/api/generate', 'POST', payload);
          startPolling('ct', d.job_id, 'ct_progress_card', payload.source_title || '未命名续写', 'round');
        } catch (err) {
          toast(err.message);
        }
      };
    });

    on('ct_variants_retry_btn', () => runVariantsFlow(payload));
  } catch (e) {
    cardsBox.innerHTML = `<div style="grid-column:1/-1;text-align:center;padding:16px;color:var(--err);">生成小样失败：${escapeHtml(e.message)}</div>`;
  }
}

on('btn_continue_variants', async () => {
  const payload = continuationPayload();
  payload.style_profile = styleProfile;
  payload.bible = collectCtBible();
  await runVariantsFlow(payload);
});

async function loadExistingNovelsIntoContinuation() {
  const sel = $('ct_existing_sel');
  if (!sel) return;
  try {
    const novels = await api('/api/novels');
    const curVal = sel.value;
    sel.innerHTML = '<option value="">-- 选择书架中的已有小说 --</option>' +
      novels.map(n => `<option value="${escapeHtml(n.name)}">${escapeHtml(n.title || n.name)} (${n.chapters_count || 0}章 · ${(n.type === 'fanfic' ? '同人' : (n.type === 'continuation' ? '续写' : '原创'))})</option>`).join('');
    if (curVal) sel.value = curVal;
  } catch (e) {}
}

on('ct_open_round_btn', () => {
  const name = $('ct_existing_sel') ? $('ct_existing_sel').value : '';
  if (!name) { toast('请先在下拉列表中选择要续写的小说'); return; }
  openContinueCard(name, 'continuation');
});

on('ct_open_variants_btn', async () => {
  const name = $('ct_existing_sel') ? $('ct_existing_sel').value : '';
  if (!name) { toast('请先在下拉列表中选择要续写的小说'); return; }
  await openContinueCard(name, 'continuation');
  await runRoundVariantsFlow();
});

on('btn_continue', async () => {
  const payload = continuationPayload();
  payload.style_profile = styleProfile;
  payload.bible = collectCtBible();
  const useVariants = $('ct_use_variants') && $('ct_use_variants').checked;
  if (useVariants) {
    await runVariantsFlow(payload);
    return;
  }
  try {
    const d = await api('/api/generate', 'POST', payload);
    startPolling('ct', d.job_id, 'ct_progress_card', payload.source_title || '未命名续写', 'round');
  } catch (e) { toast(e.message); }
});


// ==================== 任务轮询 ====================
// 进度条用 transform: scaleX 驱动（合成器友好，避免 width 触发布局）
function setBar(id, pct) {
  const el = $(id);
  if (!el) return;
  const p = Math.max(0, Math.min(100, Math.round(pct || 0)));
  el.style.transform = 'scaleX(' + (p / 100) + ')';
}

function startPolling(prefix, jobId, cardId, defaultTitle, doneAction = null) {
  const card = $(cardId); card.style.display = 'block';
  setBar(prefix + '_progress_bar', 0);
  $(prefix + '_progress_text').textContent = '准备中…';
  $(prefix + '_progress_msg').textContent = '';
  $(prefix + '_open_reader').style.display = 'none';

  // 实时流式预览初始化
  const streamWrap = $(prefix + '_stream_wrap');
  const streamBody = $(prefix + '_stream_body');
  const liveBadge = $(prefix + '_live_badge');
  const streamWords = $(prefix + '_stream_words');
  const streamCh = $(prefix + '_stream_ch');
  if (streamWrap && streamBody) {
    streamBody.textContent = '';
    streamWrap.style.display = 'block';
    if (liveBadge) liveBadge.style.display = 'inline-flex';
    if (streamWords) streamWords.textContent = '';
    if (streamCh) streamCh.textContent = '正文创作实时预览';
  }

  let es = null;
  try {
    es = new EventSource('/api/jobs/' + jobId + '/stream');
    es.onmessage = e => {
      try {
        const d = JSON.parse(e.data);
        if (d.type === 'chunk' && d.text) {
          if (streamBody) {
            streamBody.textContent += d.text;
            streamBody.scrollTop = streamBody.scrollHeight;
            if (streamWords) streamWords.textContent = '已输出 ' + streamBody.textContent.replace(/\s/g, '').length + ' 字';
          }
          if (d.step && streamCh) streamCh.textContent = d.step;
        } else if (d.type === 'done') {
          if (es) { es.close(); es = null; }
          if (liveBadge) liveBadge.style.display = 'none';
        }
      } catch (err) {}
    };
    es.onerror = () => { if (es) { es.close(); es = null; } };
  } catch (err) {}

  let failCount = 0;
  const cancelBtn = $(prefix + '_cancel_job');
  if (cancelBtn) {
    cancelBtn.style.display = 'inline-block';
    cancelBtn.onclick = async () => {
      try { await api('/api/jobs/' + jobId + '/cancel', 'POST'); toast('已发送取消请求，将在当前章节完成后停止…'); }
      catch (e) { toast(e.message); }
    };
  }

  const timer = setInterval(async () => {
    try {
      const j = await api('/api/jobs/' + jobId);
      failCount = 0;
      const pct = j.total ? Math.round(j.current / j.total * 100) : 0;
      setBar(prefix + '_progress_bar', pct);
      $(prefix + '_progress_text').textContent = j.step + (j.current && j.total ? `（${j.current}/${j.total}）` : '');
      $(prefix + '_progress_msg').textContent = j.message || '';

      // 兜底更新流式输出（防止个别环境下 SSE 阻断）
      if (streamBody && j.streaming_text && (!streamBody.textContent || streamBody.textContent.length < j.streaming_text.length)) {
        streamBody.textContent = j.streaming_text;
        streamBody.scrollTop = streamBody.scrollHeight;
        if (streamWords) streamWords.textContent = '已输出 ' + streamBody.textContent.replace(/\s/g, '').length + ' 字';
      }
      if (j.step && streamCh) streamCh.textContent = j.step;

      if (j.status === 'done') {
        clearInterval(timer);
        if (es) { es.close(); es = null; }
        if (liveBadge) liveBadge.style.display = 'none';
        if (cancelBtn) cancelBtn.style.display = 'none';
        $(prefix + '_progress_text').textContent = '生成完成';
        if (j.novel_name) {
          const rd = $(prefix + '_open_reader');
          rd.style.display = 'inline-block';
          rd.dataset.novel = j.novel_name;
          rd.onclick = () => openReader(j.novel_name);
        }
        toast('生成完成');
        if (doneAction === 'round' && j.novel_name && (j.mode === 'continuation' || j.mode === 'fanfic')) {
          openContinueCard(j.novel_name, j.mode, { fromRound: true });
        }
      } else if (j.status === 'error') {
        clearInterval(timer);
        if (es) { es.close(); es = null; }
        if (liveBadge) liveBadge.style.display = 'none';
        if (cancelBtn) cancelBtn.style.display = 'none';
        $(prefix + '_progress_text').textContent = '生成失败：' + j.message;
        toast('生成失败：' + j.message);
      } else if (j.status === 'cancelled') {
        clearInterval(timer);
        if (es) { es.close(); es = null; }
        if (liveBadge) liveBadge.style.display = 'none';
        if (cancelBtn) cancelBtn.style.display = 'none';
        $(prefix + '_progress_text').textContent = '任务已取消（已生成章节保留，可到阅读器「从断点继续」）';
        toast('任务已取消');
      }
    } catch (e) {
      failCount++;
      if (failCount >= 6) {
        clearInterval(timer);
        if (es) { es.close(); es = null; }
        if (liveBadge) liveBadge.style.display = 'none';
        if (cancelBtn) cancelBtn.style.display = 'none';
        $(prefix + '_progress_text').textContent = '生成服务连接中断（服务可能已重启）。可刷新页面后到书架「从断点继续」。';
        toast('生成服务连接中断');
      }
    }
  }, 1500);
}


// ==================== 续写/重写任务卡片 ====================
let roundNovelName = null;   // 关联的小说
let roundMode = null;        // continuation | fanfic | rewrite
let roundProviderId = null;  // 该书所用模型 id
let roundChapterIdx = null;  // 重写模式下的章节下标

// 卡片要用的书籍数据：阅读器里已经拉过整本就直接复用。
// 否则点一次「继续续写」会把整本书重新下载一遍 —— 19MB 的书在手机上要等几十秒，
// 而且旧写法是「下载完才弹卡片」，用户看到的就是「点了没反应」。
async function novelForCard(novelName) {
  if (readerData && readerData.name === novelName) return readerData;
  return await api('/api/novels/' + encodeURIComponent(novelName) + '?toc=1');
}

// 打开续写卡片（阅读器「继续续写」或轮次完成后）
async function openContinueCard(novelName, mode, opts = {}) {
  roundNovelName = novelName; roundMode = mode; roundChapterIdx = null;
  // 先把卡片弹出来，再去取数据；取数期间「开始续写」置灰
  $('rm_title').textContent = (opts.fromRound ? '本轮续写完成' : '续写') + '《' + novelName + '》';
  $('rm_summary').textContent = '加载中…';
  if ($('rm_variants_box')) $('rm_variants_box').style.display = 'block';
  if ($('rm_variants_wrap')) $('rm_variants_wrap').style.display = 'none';
  if ($('rm_variants_btn')) $('rm_variants_btn').style.display = 'inline-flex';
  if ($('rm_use_variants')) $('rm_use_variants').checked = false;
  $('rm_instruction_label').textContent = opts.fromRound ? '下一轮续写指示（可选）' : '续写指示（可选，可调整后续走向）';
  $('rm_instruction').value = '';
  $('rm_instruction').placeholder = '如：让主角发现某个秘密 / 加快节奏 / 引入新角色 / 解开某处伏笔…';
  $('rm_chapters_wrap').style.display = 'block';
  $('rm_chapters').value = 1;
  $('rm_per_words').value = 3000;
  $('rm_preview').style.display = 'none';
  $('rm_start').textContent = '开始续写';
  $('rm_start').disabled = true;
  showRoundForm();
  $('round_modal').classList.add('show');
  try {
    const d = await novelForCard(novelName);
    const meta = d.meta;
    roundProviderId = meta.provider_id || null;
    $('rm_title').textContent = (opts.fromRound ? '本轮续写完成' : '续写') + '《' + (meta.title || novelName) + '》';
    $('rm_summary').textContent =
      `全书共 ${d.chapters.length} 章（含原作）· ${d.words.toLocaleString()} 字` +
      (meta.model_used ? ` · 上次模型：${meta.model_used}` : '');
    $('rm_per_words').value = meta.job_payload && meta.job_payload.per_chapter_words || 3000;
    const last = d.chapters[d.chapters.length - 1];
    if (opts.fromRound && last) {
      $('rm_preview').style.display = 'block';
      const ctext = last.content || '';
      $('rm_preview').textContent = `${last.title}\n\n${ctext.slice(0, 500)}${ctext.length > 500 ? '\n……' : ''}`;
    }
    $('rm_start').disabled = false;
    await loadProviderSelectsInto('rm_provider', roundProviderId);
  } catch (e) {
    $('rm_summary').textContent = '加载失败：' + e.message;
    toast('加载失败：' + e.message);
  }
}

// 打开重写卡片
async function openRewriteCard(novelName, chapterIdx) {
  roundNovelName = novelName; roundMode = 'rewrite'; roundChapterIdx = chapterIdx;
  $('rm_title').textContent = '重写《' + novelName + '》';
  $('rm_summary').textContent = '加载中…';
  if ($('rm_variants_box')) $('rm_variants_box').style.display = 'none';
  if ($('rm_variants_wrap')) $('rm_variants_wrap').style.display = 'none';
  if ($('rm_variants_btn')) $('rm_variants_btn').style.display = 'none';
  $('rm_instruction_label').textContent = '重写要求（可选）';
  $('rm_instruction').value = '';
  $('rm_instruction').placeholder = '如：换一种写法 / 让本章更紧凑 / 突出某个情节…';
  $('rm_chapters_wrap').style.display = 'none';
  $('rm_per_words').value = 3000;
  $('rm_preview').style.display = 'none';
  $('rm_start').textContent = '开始重写';
  $('rm_start').disabled = true;
  showRoundForm();
  $('round_modal').classList.add('show');
  try {
    const d = await novelForCard(novelName);
    const meta = d.meta;
    const ch = d.chapters[chapterIdx];
    roundProviderId = meta.provider_id || null;
    $('rm_title').textContent = '重写《' + (meta.title || novelName) + '》· ' + (ch ? ch.title : '');
    $('rm_summary').textContent = '将以本章之前的内容为上下文重新生成，编号保持不变。' + (meta.model_used ? ` · 上次模型：${meta.model_used}` : '');
    $('rm_per_words').value = meta.job_payload && meta.job_payload.per_chapter_words || 3000;
    $('rm_start').disabled = false;
    await loadProviderSelectsInto('rm_provider', roundProviderId);
  } catch (e) {
    $('rm_summary').textContent = '加载失败：' + e.message;
    toast('加载失败：' + e.message);
  }
}

function showRoundForm() {
  $('rm_form').style.display = 'block';
  $('rm_progress').style.display = 'none';
  setBar('rm_bar', 0);
  $('rm_cancel_job').style.display = 'none';
}

function showRoundProgress() {
  $('rm_form').style.display = 'none';
  $('rm_progress').style.display = 'block';
  $('rm_progress_text').textContent = '准备中…';
}

let roundJobId = null, roundTimer = null, roundEs = null;

function closeRoundModal() {
  $('round_modal').classList.remove('show');
  if (roundTimer) { clearInterval(roundTimer); roundTimer = null; }
  if (roundEs) { roundEs.close(); roundEs = null; }
  roundJobId = null;
  roundNovelName = null; roundMode = null; roundChapterIdx = null;
}

on('rm_cancel', closeRoundModal);
on('rm_close', closeRoundModal);

async function runRoundVariantsFlow() {
  if (!roundNovelName) { toast('请先选择要续写的小说'); return; }
  const wrap = $('rm_variants_wrap');
  const cardsBox = $('rm_variants_cards');
  if (!wrap || !cardsBox) return;

  wrap.style.display = 'block';
  cardsBox.innerHTML = `<div style="grid-column:1/-1;text-align:center;padding:24px;color:var(--muted);"><span class="rd-spin"></span> 正在为《${escapeHtml(roundNovelName)}》构思两种不同走向的剧情小样…</div>`;
  if (wrap.scrollIntoView) wrap.scrollIntoView({ behavior: 'smooth', block: 'nearest' });

  try {
    const res = await api('/api/generate-variants', 'POST', {
      novel_name: roundNovelName,
      instruction: $('rm_instruction').value.trim() || '继续推进剧情',
      provider_id: $('rm_provider').value
    });
    const variants = (res && res.variants) || [];
    if (!variants.length) throw new Error('未返回有效小样');

    cardsBox.innerHTML = variants.map(v => `
      <div class="variant-card" data-id="${v.id}">
        <div>
          <div class="variant-card-head">
            <span class="variant-card-title">${escapeHtml(v.title || ('走向 ' + v.id))}</span>
            <span class="variant-badge">方向 ${v.id}</span>
          </div>
          <div class="variant-card-synopsis">${escapeHtml(v.synopsis || '')}</div>
          <div class="variant-card-preview">${escapeHtml(v.preview || '')}</div>
        </div>
        <button type="button" class="primary variant-select-btn" data-id="${v.id}">✅ 采纳此走向并开始续写 →</button>
      </div>
    `).join('');

    cardsBox.querySelectorAll('.variant-select-btn').forEach((btn, idx) => {
      const v = variants[idx];
      btn.onclick = async (e) => {
        e.stopPropagation();
        btn.disabled = true;
        btn.textContent = '启动生成中…';
        const addInst = `【采纳剧情走向】：${v.title}。${v.preview}`;
        wrap.style.display = 'none';
        await startRoundJob(addInst);
      };
    });

    on('rm_variants_retry_btn', () => runRoundVariantsFlow());
  } catch (e) {
    cardsBox.innerHTML = `<div style="grid-column:1/-1;text-align:center;padding:16px;color:var(--err);">生成小样失败：${escapeHtml(e.message)}</div>`;
  }
}

on('rm_variants_btn', () => runRoundVariantsFlow());
on('rm_trigger_variants_btn', () => runRoundVariantsFlow());

on('rm_start', async () => {
  if ($('rm_use_variants') && $('rm_use_variants').checked && roundMode !== 'rewrite') {
    await runRoundVariantsFlow();
    return;
  }
  await startRoundJob();
});

async function startRoundJob(extraInstruction = null) {
  if (!roundNovelName) return;
  const providerId = $('rm_provider').value;
  showRoundProgress();
  const cancelBtn = $('rm_cancel_job');

  const streamWrap = $('rm_stream_wrap');
  const streamBody = $('rm_stream_body');
  const liveBadge = $('rm_live_badge');
  const streamWords = $('rm_stream_words');
  const streamCh = $('rm_stream_ch');
  if (streamWrap && streamBody) {
    streamBody.textContent = '';
    streamWrap.style.display = 'block';
    if (liveBadge) liveBadge.style.display = 'inline-flex';
    if (streamWords) streamWords.textContent = '';
    if (streamCh) streamCh.textContent = '正文创作实时预览';
  }

  try {
    let jobId;
    if (roundMode === 'rewrite') {
      const r = await api('/api/novels/' + encodeURIComponent(roundNovelName) + '/chapters/rewrite', 'POST', {
        index: roundChapterIdx,
        per_chapter_words: parseInt($('rm_per_words').value) || 3000,
        provider_id: providerId,
        extra: $('rm_instruction').value.trim(),
      });
      jobId = r.job_id;
    } else {
      let finalInst = $('rm_instruction').value.trim();
      if (extraInstruction) {
        finalInst = finalInst ? (finalInst + '\n\n' + extraInstruction) : extraInstruction;
      }
      const r = await api('/api/generate', 'POST', {
        mode: roundMode,
        novel_name: roundNovelName,
        new_instruction: finalInst,
        chapters: parseInt($('rm_chapters').value) || 1,
        per_chapter_words: parseInt($('rm_per_words').value) || 3000,
        provider_id: providerId,
      });
      jobId = r.job_id;
    }
    roundJobId = jobId;
    cancelBtn.style.display = 'inline-block';
    cancelBtn.onclick = async () => {
      try { await api('/api/jobs/' + roundJobId + '/cancel', 'POST'); toast('已发送取消请求，将在当前章节完成后停止…'); }
      catch (e) { toast(e.message); }
    };

    if (roundEs) { roundEs.close(); roundEs = null; }
    try {
      roundEs = new EventSource('/api/jobs/' + jobId + '/stream');
      roundEs.onmessage = e => {
        try {
          const d = JSON.parse(e.data);
          if (d.type === 'chunk' && d.text) {
            if (streamBody) {
              streamBody.textContent += d.text;
              streamBody.scrollTop = streamBody.scrollHeight;
              if (streamWords) streamWords.textContent = '已输出 ' + streamBody.textContent.replace(/\s/g, '').length + ' 字';
            }
            if (d.step && streamCh) streamCh.textContent = d.step;
          } else if (d.type === 'done') {
            if (roundEs) { roundEs.close(); roundEs = null; }
            if (liveBadge) liveBadge.style.display = 'none';
          }
        } catch (err) {}
      };
      roundEs.onerror = () => { if (roundEs) { roundEs.close(); roundEs = null; } };
    } catch (err) {}

    // 卡片内轮询进度
    let failCount = 0;
    roundTimer = setInterval(async () => {
      try {
        const j = await api('/api/jobs/' + jobId);
        failCount = 0;
        const pct = j.total ? Math.round(j.current / j.total * 100) : 0;
        setBar('rm_bar', pct);
        $('rm_progress_text').textContent = j.step + (j.current && j.total ? `（${j.current}/${j.total}）` : '');

        if (streamBody && j.streaming_text && (!streamBody.textContent || streamBody.textContent.length < j.streaming_text.length)) {
          streamBody.textContent = j.streaming_text;
          streamBody.scrollTop = streamBody.scrollHeight;
          if (streamWords) streamWords.textContent = '已输出 ' + streamBody.textContent.replace(/\s/g, '').length + ' 字';
        }
        if (j.step && streamCh) streamCh.textContent = j.step;

        if (j.status === 'done') {
          clearInterval(roundTimer); roundTimer = null;
          if (roundEs) { roundEs.close(); roundEs = null; }
          if (liveBadge) liveBadge.style.display = 'none';
          cancelBtn.style.display = 'none';
          $('rm_progress_text').textContent = '完成';
          toast('完成');
          setTimeout(() => { closeRoundModal(); if (readerData && readerData.name === roundNovelName) openReader(roundNovelName); }, 600);
        } else if (j.status === 'error') {
          clearInterval(roundTimer); roundTimer = null;
          if (roundEs) { roundEs.close(); roundEs = null; }
          if (liveBadge) liveBadge.style.display = 'none';
          cancelBtn.style.display = 'none';
          $('rm_progress_text').textContent = '失败：' + j.message;
          toast('失败：' + j.message);
        } else if (j.status === 'cancelled') {
          clearInterval(roundTimer); roundTimer = null;
          if (roundEs) { roundEs.close(); roundEs = null; }
          if (liveBadge) liveBadge.style.display = 'none';
          cancelBtn.style.display = 'none';
          $('rm_progress_text').textContent = '任务已取消';
          toast('任务已取消');
          $('rm_close').textContent = '关闭';
        }
      } catch (e) {
        failCount++;
        if (failCount >= 6) {
          clearInterval(roundTimer); roundTimer = null;
          if (roundEs) { roundEs.close(); roundEs = null; }
          if (liveBadge) liveBadge.style.display = 'none';
          cancelBtn.style.display = 'none';
          $('rm_progress_text').textContent = '生成服务连接中断（服务可能已重启）';
          toast('生成服务连接中断');
        }
      }
    }, 1500);
  } catch (e) {
    $('rm_progress_text').textContent = '失败：' + e.message;
    toast('失败：' + e.message);
    cancelBtn.style.display = 'none';
  }
};
