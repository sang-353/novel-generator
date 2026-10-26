# AGENTS.md — 小说生成器（novel-generator）AI Agent 开发与维护指南

> **适用对象**：接手本项目进行功能迭代、UI 重构、Bug 修复及性能调优的所有 AI Coding Agent。  
> **核心宗旨**：保障系统健壮性，防止历史故障重演，杜绝"单点 JS 报错导致全站按钮失效"与"未经验证的重复造轮子"。

---

## 1. 项目定位与架构全景

### 1.1 系统定位
本项目是一款基于大语言模型（LLM）API 的**个人小说创作全流程 Studio 工作台**。
核心功能涵盖：
- **原创生成**：灵感脑洞库 → 世界观与设定集设定 → 大纲生成 → 细纲推演 → 逐章自动推进与断点续跑。
- **续写与同人**：导入已有文章或小说，AI 深度分析行文风格、人物口吻、伏笔暗线，无缝续写后续章节。
- **Studio 工作台**：双栏/三栏沉浸式阅读与编辑器、分卷与章节拖拽排序、字数与热键实时监控、本地快照恢复、划词 AI 局部润色、全局多章节查找替换。
- **个人书架与隐私保护**：书架管理、全本/单章导入导出（TXT/Markdown）、回收站防误删、加盐 PBKDF2 隐私密码书架。

### 1.2 技术栈与核心约束
- **后端**：Python 3.14 + Flask。
  - **无数据库、无 ORM**：全部数据落地在 `novels/<书名>.md`（单文件 Markdown，头部带 YAML/JSON frontmatter 存储元数据）以及 `config.json`。
  - **依赖管理**：Windows 本机依赖位于 `pylibs/`。
- **前端**：**纯原生 Vanilla ES6+，零构建工具**（无 Webpack、无 Vite、无 Node 构建管道）。
  - HTML：`static/index.html`。
  - CSS：`static/css/app.css`。
  - 模块化 JS：拆分存放于 `static/js/`，直接通过 `<script defer>` 依次加载：
    1. `util.js`：全局通用工具函数（`$`, `on`, `api`, `toast`, `escapeHtml` 等）。
    2. `state.js`：全局响应式状态与当前活动模式。
    3. `generator.js`：生成引擎、脑洞库、流式推送监控。
    4. `library.js`：书架管理、导入导出、回收站、分类标签。
    5. `reader.js`：Studio 工作台核心、目录分卷、正文编辑、划词精修、快捷键调度。
    6. `app.js`：单页应用路由调度、全局面板控制与主题切换。

---

## 2. 近期严重故障复盘与根因分析 (Post-Mortem)

在近期的快速迭代中，项目经历了数次影响重大的回归故障。所有 Agent 必须深刻理解以下成因，在后续变更中严格规避。

### 🚨 案例 1：划词 AI 辅助精修气泡四个按钮失效
- **故障现象**：在阅读器中选中文本后，浮动气泡工具条正常弹出 `[ 🔍 扩写细节 ]` `[ 🎨 换文风 ]` `[ ✂️ 精简 ]` `[ ✍️ 自定义 ]` 4 个按钮，但用户点击任何一个按钮均无反应，界面完全静止，如同按钮死掉。
- **根因剖析**：
  1. **视口与文档流严重错位**：先前修改中引入了一个轻量行内组件 `#rd_inline_assist_box`，却将其以常规流（`margin: 16px auto`）排在 `#rd_content` 之后。当正文有几千字时，该容器实际展开在正文最底部、距离视口下方数千像素的屏幕外。用户点击气泡后，气泡隐藏，行内框在视口下方屏幕外展开，用户视野中没有任何变化，直观感知就是"按钮坏了"。
  2. **Mousedown 导致浏览器选区折叠崩溃**：在浏览器机制中，用户点击未被处理的按钮会触发默认的聚焦转移，导致当前的文本选区（Selection）瞬间折叠（`isCollapsed = true`）。当 `click` 事件触发时，选区已丢失，导致后续获取 `activeSelectionSnippet` 失败直接 `return`。
  3. **重复造轮子与成熟组件旁路**：`#rd_assist_modal` 早已是一个功能完备、居中展示、支持文风选择、自定义输入、Diff 对比与就地保存的成熟弹窗，但之前的实现试图在正文下方硬塞行内元素，引发了逻辑分叉与状态断裂。
- **防范机制**：
  - **视口居中或绝对锚定**：所有交互弹窗和反馈组件，要么采用 Viewport 固定居中蒙层（`position: fixed; inset: 0; z-index: ...`），要么基于 `Range.getBoundingClientRect()` 进行严格的视口位置运算，严禁把针对局部视口交互的反馈放入超长滚动容器末尾。
  - **选区防失焦保护**：针对选区的浮动操作按钮，必须在 `onmousedown` 事件中调用 `e.preventDefault(); e.stopPropagation();`，确保点击操作不破坏浏览器当前的文本选择。

---

### 🚨 案例 2：全站/阅读器全局 JS 崩溃导致所有按钮失效
- **故障现象**：重构顶栏与样式后，用户反馈"刚才更新的内容，大量按钮无效，进入小说的所有按钮几乎都无效"。
- **根因剖析**：
  - **单点 Null 报错阻断全局脚本执行**：在重构 HTML 时，删除了历史遗留的 `#rd_toc_search` 搜索框。但 `reader.js` 顶层代码中有一行无防护的直接赋值：
    ```javascript
    $('rd_toc_search').onclick = () => { ... }; // 当元素不存在时抛出 TypeError
    ```
  - 原生 JavaScript 没有打包工具的安全沙箱，一个未捕获的全局 TypeError 会**立即终止整个 `reader.js` 文件的后续执行**。这导致后面所有的事件监听器（包括章节加载、阅读器初始化、弹窗绑定、键盘快捷键）完全没有被注册，整个阅读器交互全面瘫痪。
- **防范机制**：
  - **严禁直接对 `$(id)` 属性赋值**：必须使用 `static/js/util.js` 中提供的安全辅助函数 `on(id, event, fn)`，该函数内部自带 `if (!el) return;` 存在性检查。
  - **子模块初始化隔离**：独立功能面板的初始化（如目录面板、辅助精修、大纲树等）应封装在独立的 `initXxx()` 函数中，并在外层通过 `try...catch` 隔离保护，严禁一个次要面板的 DOM 缺失阻断全局核心逻辑。

---

### 🚨 案例 3：灵感脑洞库换一批生成后，题材标签失效与出现 `undefined` 药丸
- **故障现象**：在原创生成页面点击"换一批"，重新生成的开局脑洞卡片中题材药丸显示为 `undefined`，点击后无反应或报错。
- **根因剖析**：
  - **数据契约漂移与模板脆弱性**：后端大模型生成结构在升级后输出格式发生变动（例如由字符串数组变为对象字典，或者字段名由 `name` 变为 `tag`）。前端渲染模板盲目读取 `trope.name`，未做类型判断与回退，导致渲染出 `<span class="tag-pill">undefined</span>`，同时导致 dataset 属性为空，事件委托命中失效。
- **防范机制**：
  - **数据消费边界的防御性兼容 (Defensive Normalization)**：
    ```javascript
    const tagName = typeof trope === 'string' ? trope : (trope.name || trope.title || trope.tag || '');
    ```
  - 对任何来自大模型或后端异步 API 的动态字段，在拼接 HTML 之前必须经过防御性解析与 `escapeHtml()` 处理。

---

### 🚨 案例 4：Windows 环境控制台编码异常 (`UnicodeEncodeError: 'gbk'`)
- **故障现象**：在执行测试脚本或运行排查工具时，控制台抛出 `UnicodeEncodeError: 'gbk' codec can't encode character '\U0001f50d'` 并中断。
- **根因剖析**：
  - 本地运行环境为 Windows，控制台默认代码页通常是 CP936 (GBK)，无法直接输出 4 字节 UTF-8 字符（如 Emoji 图标 `🔍`、`🎨`、`✨`、`✅`）。
- **防范机制**：
  - 在任何需要向控制台输出日志的 Python 脚本或测试入口处，统一添加流重构：
    ```python
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    ```
  - 避免在裸命令行执行带特殊 Unicode 字符的批处理指令。

---

## 3. AI Agent 编码黄金铁律 (Golden Rules)

所有在此代码库中工作的 Agent 必须无条件遵守以下开发准则：

### 规则 1：DOM 防御性操作（Defensive DOM Manipulation）
1. 严禁书写 `$(id).onclick = ...` 或 `document.getElementById(id).addEventListener(...)`。
2. 绑定事件一律使用项目标准辅助函数 `on(id, handler)` 或在绑定前显式判空：
   ```javascript
   // 正确做法 A：使用内置安全绑定
   on('my_button_id', () => handleClick());

   // 正确做法 B：显式条件判断
   const btn = $('my_button_id');
   if (btn) btn.onclick = () => handleClick();
   ```
3. 查询子元素集合前，确保父容器有效，并使用可选链或条件守卫：
   ```javascript
   const panel = $('rd_toc');
   if (panel) {
     panel.querySelectorAll('.ch-item').forEach(el => ...);
   }
   ```

### 规则 2：视图层级与视口规范（Viewport & Layering）
1. 绝对不要将划词操作、提示气泡或即时反馈面板放入带有 `overflow: auto` 或长正文滚动区域的底部普通流中。
2. 全局层级（z-index）体系规范：
   - 基础内容区：`z-index: 1 ~ 10`
   - 顶部导航栏 / 状态条：`z-index: 100`
   - 侧边栏（目录/设定集）：`z-index: 200`（桌面展开）/ `z-index: 1040`（移动端抽屉）
   - 选区浮动工具栏：`z-index: 1050`
   - 全局遮罩层（`.rd-mask`, `.modal-mask`）：`z-index: 1055`
   - 居中弹窗（划词精修、快照历史、人设卡片等）：`z-index: 1060`
   - Toast 瞬态通知：`z-index: 9999`
3. 任何打开弹窗的操作，必须配套管理遮罩层状态，并支持 `Esc` 键快捷退出。

### 规则 3：保持单一事实来源（Single Source of Truth）
1. 修改现有功能前，**先全局搜索现有代码库**。严禁在不知晓已有组件存在的情况下重复实现功能。
2. 划词精修统一使用 `#rd_assist_modal`，不要另外造第二套 inline/floating box。
3. 章节保存统一通过后端 `/api/novels/<name>/chapter/<idx>` 接口，确保字数统计、备份与全书字数同步刷新。

### 规则 4：数据与文件安全（Data Integrity）
1. 小说文本直接存储在磁盘 `novels/*.md` 中。修改前必须先确认文件是否存在。
2. 保存或更新章节时，务必保留 Markdown 文件开头的 YAML/JSON frontmatter 块（包含小说标题、模式、题材、设定集关联等元数据），严禁覆盖或丢弃元数据。
3. 在编辑与精修替换时，必须核实原句在正文中唯一存在，若被用户二次修改则提示手动复制，防止误替换错误段落。

---

## 4. 交付前自检清单 (Pre-flight Checklist)

在宣布任何任务完成前，Agent 必须依次完成以下 5 步验证：

1. **JS 语法严格检验**：
   ```powershell
   node -e "['app.js', 'generator.js', 'library.js', 'reader.js', 'state.js', 'util.js'].forEach(f => require('child_process').execSync('node --check static/js/' + f)); console.log('All JS OK');"
   ```
   - 结果必须输出 `All JS OK`，无任何语法错误。

2. **Python 自动化单元测试**：
   ```powershell
   $env:PYTHONPATH = ".;pylibs"; python -m pytest tests/
   ```
   - 必须确保所有测试用例（当前共 51 项）全部通过（`51 passed`），无任何 regression。

3. **DOM 关联性检查**：
   - 若在 `index.html` 中修改或删除了任何元素 ID，必须对 `static/js/` 进行全局 grep，确保没有任何 JS 文件在尝试访问已被废弃的 ID。

4. **交互体验回归**：
   - 检查控制台（F12）是否存在静默的 `TypeError` 或 `ReferenceError`。
   - 确认划词气泡能在不同滚动高度下正常触发居中精修弹窗。
   - 确认弹窗的关闭按钮、遮罩层点击、`Esc` 按键均能优雅关闭。

5. **文档与 Git 状态一致性**：
   - 运行 `git status` 检查变动文件，确保没有意外的临时垃圾文件残留。
