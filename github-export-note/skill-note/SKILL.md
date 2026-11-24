---
name: literature-structured-note
description: 文献总结与结构化笔记。把一篇科研论文读成与原文章节对齐、字段齐备、可回链、可复用的结构化笔记：统一字段的论文卡片 + 按原文章节的章节笔记 + 可检索知识点条目，每条关键论断带"页码:章节.段落/图表"锚点回链，读不出/不确定/冲突显式标注，输出可复核的 result.json。触发条件：任务要求对科研论文做总结、结构化笔记、知识点提取、按章节拆解、证据回链或可复用笔记。
---

# 文献总结与结构化笔记（阅读10）

## 一、目标

把一篇科研论文读成**结构化笔记**，而不是一段压缩摘要。产出三件套：

1. **论文卡片**：用统一字段记录研究问题、数据、方法、主要发现、结论、局限、前提条件等，使多篇论文可并排比较。
2. **章节笔记**：按论文**自身**章节与论证顺序逐节提炼，保留章节间承接关系。
3. **知识点条目**：把概念、变量、方法、结论拆成可检索条目，处理术语/缩写/同义表述，去重并标注关系。

每一条关键论断都必须带**锚点回链**（页码:章节.段落/图表/公式）；所有读不出、不确定、材料冲突显式标注，禁止猜测、补造、伪造。

## 二、四个质量关口（每一步都以这四关自检）

| 关口 | 一句话标准 | 落到哪些动作 | 必须避免的失败 |
|---|---|---|---|
| **对得上** | 笔记骨架 = 论文自身章节与论证顺序，不套通用 IMRaD 模板 | 先抽原文标题树；章节笔记按原文顺序写；记录章节间承接 | 把任何论文都压成"背景—方法—结果—结论"四段通用摘要 |
| **留得住** | 研究问题 / 数据 / 方法条件 / 主要发现 / 局限 / **前提条件**都记录 | 论文卡片字段逐项填；重点抽取"让结论成立的前提条件"（假设、数据范围、评测条件、caveat） | 只记结论、丢数据规模与超参、漏假设 |
| **找得回** | 每条关键笔记能指回具体页码/章节/段落/图表，而不是笼统出处 | 统一锚点格式；写完做一遍锚点校验（第六节） | 只写"见原文""见 Methods 部分" |
| **用得上** | 可检索、可比较、可继续加工，能被下一次阅读/写作直接使用 | 统一字段字典；知识点归一化+去重+关系；同时输出 JSON（机器）与 Markdown（人读） | 一段长文本、字段不一致、无法跨论文比较 |

## 三、输入与运行时约定（固定）

- **输入**：`/input/case.json`（内含任务说明 `task`、`output_contract`、材料路径）与 `task.md`；真实 PDF/材料是**唯一事实依据**。
- **工作目录** `/app/work`；最终结果写 `/app/output/result.json`（必含 `output_contract` 全部字段与 `case_id`）；推荐另写 `/app/output/note.md`（人读版，同一内容）。
- **预算**：64 次模型请求 / 900 秒 / 每次响应 ≤16384 tokens。先落骨架、再逐节读、边读边存中间产物，最后汇总；不要"一次读完全文再想怎么写"。
- 若 `output_contract` 声明了额外必填字段，必须与本文档的字段**合并**输出，缺一不可；case 的字段名与本文档冲突时，以 case 的字段名为主并在 `notes` 说明映射。

## 四、分步工作流（严格按此顺序）

### 第 1 步：读输入，定边界（省请求）

1. 读 `/input/case.json` 与 `task.md`，记录：`case_id`、任务要求、`output_contract` 字段清单、材料路径列表。
2. 用材料的**真实文件路径**（不是文件名标签）定位文档；用 `pdf-text-tool` 取文本层，确认：页数、有无文字层、语言、是单篇论文还是多篇/报告/教材。
3. 明确边界：任务要求的是"总结/对比/问答/字段提取/知识点清单"中的哪种；只做任务要求 + 本文档标准三件套，不扩展无关内容。

### 第 2 步：建章节骨架（对得上）

1. 从文本层抽取**原文标题树**：所有编号与无编号标题，逐条记录 `【标题原文 | 物理页码 | 该标题下首个正文段位置】`，保存到 `/app/work/skeleton.json`。
2. **不改名、不合并、不套 IMRaD**。论文本身是 IMRaD 就按 IMRaD；是别的结构就按别的结构（如"模型—实验—理论分析—讨论"）。
3. 记录章节间承接：每节开头如何接上一节、结尾如何引出下一节（记为 `links_to`）。
4. 页码缺失/乱序/双栏错序时，按物理页序编号 `P1..Pn` 并在 `notes` 说明；不要擅自重排。

### 第 3 步：逐章精读，写章节笔记（对得上 + 留得住）

按骨架顺序逐节处理，每节产出（只写该节**原文有的**内容，没有的字段如实标"本节无……"）：

- `purpose`：这一节要解决什么；
- `content_or_method`：本节关键设定、条件、参数、步骤；
- `result_or_conclusion`：本节产出的结果或结论；
- `figures_tables`：本节出现的图/表/公式编号与页；
- `links_to`：上一节 → 本节 → 下一节的承接；
- `raw_claims`：本节关键论断清单，逐条带锚点（`statement` + `anchor`）。

双栏/多栏：先确认阅读顺序（左栏整栏读完再读右栏），段落编号按阅读顺序 1-based 计数；跨页段落按页序接续并在锚点里写起始页。

### 第 4 步：填论文卡片（留得住）

按第五节字段字典逐项填。每项都是数组，元素格式：

```json
{ "statement": "论断（一句一义）", "anchor": "p5:§3.2:para2", "verbatim": "可选·原文引文", "source_kind": "explicit|inferred|summary" }
```

- `source_kind` 三档必须诚实标注：`explicit`＝原文明写；`inferred`＝由原文推断（必须在 `evidence` 说明推断依据）；`summary`＝对整节/整页的概括（锚点指向章节级）。
- **重点：`preconditions`** 必须从方法假设、数据范围与划分、评测条件、caveat、适用范围中抽取；抽不到就把"结论 X 的前提条件未在文中明确说明"写进 `uncertainties`，**不得自己补一个前提**。

### 第 5 步：提取并归并知识点（用得上）

按第七节规则建 `knowledge_items`：术语/缩写/同义归一化，同义条目去重，矛盾条目显式标记，建立条目间关系。每条知识点都给 `id`、`type`、`canonical`、`terms`、`definition`、`anchors`、`relations`。

### 第 6 步：锚点回链校验（找得回）

对每一条 `anchor` 重新定位并核对四项：① 页码存在且文本层确实在该页；② 章节标题与骨架一致；③ 段内确有此论断（或该数值/变量确在此处）；④ 图/表/公式编号与原文题注一致。

- 不一致 → 改锚点；改不出来的 → 该条降级进 `uncertainties`（写"锚点未核验通过，待人工复核"）。
- 最后产出 `anchor_index`：唯一锚点 → 目标标题/题注/原文片段（≤20 字），供复核者跳转。

### 第 7 步：写 result.json 与 note.md

1. 按第八节 schema 写 `/app/output/result.json`；写完用 `python3 -m json.tool /app/output/result.json` 校验 JSON 合法性。
2. 写人读版 `/app/output/note.md`：同一内容，锚点内联写成 `(p5 · §3.2 · 第2段)`，卡片字段与知识点逐条列出，便于人工复核与继续加工。
3. 过一遍第十节自检清单后再定 `status`。

## 五、论文卡片统一字段字典

| 字段 | 含义 | 取值要求 | 锚点最低粒度 |
|---|---|---|---|
| `title` | 标题 | 原文原样（含副标题） | `P1` |
| `authors` | 作者 | 原文顺序，姓名原样 | `P1` |
| `year` | 发表年份 | 只写原文可确认的；无则"未报告" | `P1` |
| `venue_or_source` | 期刊/会议/预印本来源 | 原文能确认才写；无 DOI/来源不编造 | `P1` |
| `research_question` | 研究问题/目标 | 逐条；区分主问题与子问题 | 节·段级 |
| `gap_and_motivation` | 研究缺口与动机 | 论文声称填补的空白/动机，逐条 | 节·段级 |
| `data` | 数据 | 数据集/样本/来源/规模/时间范围/划分（train/val/test）/预处理 | 数值到图表级 |
| `methods` | 方法 | 方法名 + 关键条件 + 参数/超参 + 对比基线 + 评估指标 | 数值到图表级 |
| `main_findings` | 主要发现 | 含方向与关键数值；一条一个论断 | 图表/段级 |
| `conclusions` | 结论 | 论文声明的结论；与 findings 区分（结论=论文自己的判断，发现=证据结果） | 节·段级 |
| `preconditions` | 前提条件/假设 | 让结论成立的限定：模型假设、数据条件、评测条件、caveat | 图表/段级 |
| `limitations` | 局限 | 论文自述局限；原文无局限章节 → 标注"未报告"而非补写 | 节·段级 |
| `scope_and_applicability` | 适用范围 | 论文声称的适用/不适用范围 | 节·段级 |
| `key_metrics` | 关键变量与指标 | 符号 + 含义 + 单位 + 定义位置 | 图表/公式级 |
| `terms_and_abbreviations` | 术语与缩写 | 原文给出的定义 | 图表/段级 |
| `claims_in_conflict` | 冲突/不一致 | 前后矛盾处；无则空数组 `[]` | 图表/段级 |

> 字段值统一为对象数组：`{statement, anchor, verbatim?, source_kind}`；`verbatim` 是原文逐字引文，仅当能逐字抄录时才写，否则省略。

## 六、锚点格式与可核验粒度

**机器锚点（result.json 中统一使用）**：

```
p{页码}:§{节}:{对象}{编号}
```

- `p` + 页码：物理页码，按打印页码；无打印页码用物理序 `P1..Pn` 并在 notes 说明。
- `§` + 节：与标题树一致，如 `§3.2`；无编号标题用归一化标签（去空格/标点），如 `§Abstract`、`§Introduction`、`§Methods`、`§References`、`§AppendixA`。
- 对象：`para{n}` 段（该节内第 n 段，1-based，只数正文段，跳过标题/题注）；`fig{n}` 图；`tab{n}` 表；`eq{n}` 公式；`block{n}` 文本块（扫描件/无段落结构时兜底）；`line{n}` 段内第 n 行（可选更细）。

**示例**：

| 锚点 | 含义 |
|---|---|
| `p5:§3.2:para2` | 第 5 页 · 第 3.2 节 · 第 2 段 |
| `p7:§4.1:fig3` | 第 7 页 · 第 4.1 节 · 图 3 |
| `p9:§4.2:tab2` | 第 9 页 · 第 4.2 节 · 表 2 |
| `p6:§3.3:eq12` | 第 6 页 · 第 3.3 节 · 公式(12) |
| `p8:§2.1:block3` | 第 8 页 · 第 2.1 节 · 第 3 个文本块（扫描件兜底） |

**粒度规则**：

- 包含**数字、变量、条件、比较方向、方法设置**的论断，锚点必须 ≥ 段级，优先图表/公式级。
- 纯概括性论断可用节级（如 `p5:§3.2`）。
- 扫描件无文字层时，段落结构不可靠 → 用 `block{n}` 并在 `uncertain` 标注 OCR 置信度与可能错字，**不冒充精确文本**。

## 七、知识点条目与归并规则

**条目结构**：

```json
{
  "id": "K001",
  "type": "concept|variable|method|finding|precondition|limitation|formula|dataset|term",
  "canonical": "归一化后的标准名（取原文最全称或最常用写法）",
  "terms": [ { "term": "原文写法", "kind": "abbrev|synonym|original", "first_appears": "p2:§1.1:para1" } ],
  "definition": "一句话定义或取值，只写原文有据的内容",
  "value_or_formula": "可选：数值/公式原文",
  "anchors": ["p5:§3.2:para2"],
  "relations": [ { "to": "K002", "type": "equivalent|subclass|uses|depends_on|contradicts|defined_in|measured_by" } ],
  "uncertain": "可选：无法确定处"
}
```

**归并规则（可执行，不许跳过）**：

1. **归一化**：同一实体的全称/缩写/同义词合并为一条 `canonical`，所有变体写入 `terms`，各带首次出现锚点。例：`LR`、`Logistic Regression`、`逻辑回归` → 同一条，`terms` 三条。
2. **去重**：两条条目若定义相同、或变量符号+单位相同、或指同一数据集/方法，合并为一条，合并全部 `anchors` 与 `terms`，不得保留重复条目。
3. **矛盾处理**：同一符号有两种含义、或前后数值冲突、或同一术语两种定义时，**不强行统一、不擅自"修正"**；各自保留条目并用 `relations.type = "contradicts"` 关联，同时写入 `paper_card.claims_in_conflict` 与顶层 `uncertainties`。
4. **关系标注**：凡条目间存在"A 用 B / A 依赖 B / A 度量 B / B 在 A 中定义"等关系，写 `relations`；关系必须能从原文锚点追溯。

## 八、输出契约（result.json 必填字段）

```json
{
  "case_id": "<来自输入>",
  "status": "success | partial | failed | refused",
  "paper_card": {
    "title": "",
    "authors": [],
    "year": "",
    "venue_or_source": "",
    "research_question": [ { "statement": "", "anchor": "", "source_kind": "" } ],
    "gap_and_motivation": [],
    "data": [],
    "methods": [],
    "main_findings": [],
    "conclusions": [],
    "preconditions": [],
    "limitations": [],
    "scope_and_applicability": [],
    "key_metrics": [],
    "terms_and_abbreviations": [],
    "claims_in_conflict": []
  },
  "section_notes": [
    {
      "section_id": "§3",
      "heading": "原文标题原文",
      "page_range": [3, 6],
      "purpose": "",
      "content_or_method": "",
      "result_or_conclusion": "",
      "figures_tables": [ { "ref": "Table 1", "anchor": "p4:§3.1:tab1" } ],
      "links_to": [ { "from": "§2", "to": "§3", "how": "承接关系一句话" } ],
      "raw_claims": [ { "statement": "", "anchor": "p5:§3.2:para2" } ]
    }
  ],
  "knowledge_items": [ { "id": "K001", "type": "concept", "canonical": "", "terms": [], "definition": "", "anchors": [], "relations": [] } ],
  "anchor_index": [ { "anchor": "p5:§3.2:para2", "target": "该段首句/标题/题注（≤20字）", "verified": true } ],
  "evidence": [ { "claim": "关键论断", "anchor": "p5:§3.2:para2", "note": "支撑/推断依据" } ],
  "uncertainties": [ { "what": "未报告/不确定项", "anchor": "可选", "how_to_verify": "人工如何复核" } ],
  "notes": [ "引擎/OCR/降级/章节缺失/页码错乱/字段映射等说明" ]
}
```

**字段要求**：

- `status`：任务全部可完成 → `success`；部分字段读不出但已如实标注 → `partial`；材料缺失/加密/无法解析 → `failed`；任务超出能力或需拒答 → `refused`，并在 `notes` 写清原因。
- `evidence` 是"主结果 → 原文定位"的总账，至少覆盖每个关键结论、关键数值、方法条件各一条；`anchor_index` 是所有唯一锚点的索引，`verified` 标该锚点是否已通过第六步校验。
- `uncertainties` 必须包含：未报告项、不确定项、锚点未通过项；**禁止把不确定写成事实**。
- `paper_card` 各字段值一律用对象数组 `{statement, anchor, source_kind}`；`section_notes` 与 `knowledge_items` 按上文结构。

## 九、异常与边界处置

| 情况 | 处置 |
|---|---|
| 加密/权限受限 PDF | 不强行解密；`status:"failed"`，`notes` 说明"文档加密，需口令" |
| 扫描版（无文字层） | 用 `ocr-tool` OCR；OCR 文本标 `ocr:true` 与置信度，段落用 `block{n}` 兜底，不冒充精确文本 |
| 双栏/多栏错序 | 先确认左栏读完读右栏；不能确定处标 `uncertain`，不乱拼段 |
| 图表/公式缺失（文本层无内容） | 用 `pdf-render-tool` 渲染该页人工查看；看得到就标锚点，看不清就写"图表内容未能从文本层还原" |
| 图片型表格 | 渲染后人工/OCR 读；失败则标"表格为图片，未能结构化" |
| 超长论文（预算不够） | 优先完成：标题树 → 论文卡片关键字段 → 每节一段式笔记 → 关键知识点；牺牲"逐段 raw_claims"的完整度，并在 `notes` 说明未完成部分 |
| 非中文论文 | 笔记用中文写，但**原文关键句可保留英文引文**（`verbatim`）；术语以原文为准 |
| 页码缺失/多份材料拼接 | 按物理页序 `P1..Pn` 编号并说明；不擅自重排 |
| 论文未写局限/前提条件 | 对应字段写"未报告"，并写入 `uncertainties`，**不补写** |
| 材料不是论文（教材/综述/报告） | 仍按原文结构建骨架与章节笔记，卡片中不适用的字段标"不适用"并说明 |

## 十、诚实性铁律

1. 实际输入 PDF 与原文是**唯一事实依据**；不依据文件名、领域标签、外部知识补造内容。
2. 读不出、OCR 存疑、公式失真、图表缺失 → 显式标注；**不猜测、不补全、不伪造**。
3. "原文明写 / 由原文推断 / 概括"三档必须分开标注（`source_kind`）；推断项在 `evidence` 里写清推断依据。
4. 前提条件只记原文实际给出的；论文没说就写"未报告"，**不得替作者补假设**。
5. 数值、变量符号、单位、方法参数必须与原文一致；抄不准就不写数值，写"数值待人工复核"并给锚点。
6. 论文前后矛盾时不"替它圆场"，如实记录冲突位置。
7. 不发明 DOI、标题、作者、期刊、引文；外部来源信息只在能核验时使用。
8. 任何"脚本能确定"与"模型推断"的部分，在 `notes` 分开说明（本题纯指令型，多数字段为模型推断，务必用锚点兜底）。

## 十一、写结果前必过的自检清单

- [ ] 章节骨架来自原文标题树，标题原样，顺序与原文一致（对得上）
- [ ] 卡片 15 个字段逐项已填或显式标"未报告/不适用"；`preconditions` 单独抽过（留得住）
- [ ] 每条含数字/变量/条件/方向的论断都有 ≥段级锚点，且经第六步核对（找得回）
- [ ] 知识点已归一化、去重、矛盾已标，`id` 稳定、`relations` 有据（用得上）
- [ ] `anchor_index` 与 `evidence` 齐全，`uncertainties` 覆盖未报告/不确定/未通过项
- [ ] `result.json` 通过 `python3 -m json.tool` 校验；`status` 与事实一致
- [ ] 没有把不确定写成事实，没有补造前提、数值、元数据

## 十二、最小调用示例（示意，非正式案例结果）

输入 `/input/case.json` 含 `task` 与一篇论文 PDF；执行后写 `/app/output/result.json`（节选示意）：

```json
{
  "case_id": "example-case",
  "status": "success",
  "paper_card": {
    "research_question": [ { "statement": "论文要解决的问题…", "anchor": "p2:§1:para2", "source_kind": "explicit" } ],
    "preconditions": [ { "statement": "结论成立的前提…", "anchor": "p5:§3.2:para1", "source_kind": "explicit" } ]
  },
  "section_notes": [ { "section_id": "§3", "heading": "3. Methods", "page_range": [4, 6], "content_or_method": "…", "raw_claims": [] } ],
  "knowledge_items": [ { "id": "K001", "type": "concept", "canonical": "示例概念", "terms": [], "definition": "", "anchors": ["p2:§1.1:para1"], "relations": [] } ],
  "anchor_index": [ { "anchor": "p2:§1:para2", "target": "…", "verified": true } ],
  "evidence": [ { "claim": "…", "anchor": "p2:§1:para2" } ],
  "uncertainties": [],
  "notes": ["纯指令型 Skill，无脚本；所有字段由模型依锚点回链整理"]
}
```

（以上内容为示例，不得冒充正式案例结果。）
