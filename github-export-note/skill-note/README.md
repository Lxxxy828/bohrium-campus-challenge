# 文献总结与结构化笔记 Skill（阅读10）

把一篇科研论文读成**与原文结构对齐、字段齐备、可回链、可复用**的结构化笔记，而不是一段压缩摘要。产出三件套：统一字段的**论文卡片**、按原文章节的**章节笔记**、可检索的**知识点条目**；每条关键论断带"页码:章节.段落/图表"锚点回链；读不出/不确定/冲突显式标注。

## 用途

- 单篇科研论文的总结、结构化笔记、知识点提取、按章节拆解。
- 为"多篇论文并排比较"提供统一字段字典（论文卡片）。
- 为下一次阅读或写作保留可检索、可继续加工的中间产物（`result.json` + `note.md`）。
- 回答"论文做了什么、用什么数据、什么条件下成立、局限在哪"并逐条回到原文证据。

**不适用**：需要外部检索/引文补齐、需要领域专家判断才能定性的深层评审；本 Skill 只做"忠于原文的结构化整理"，不替作者补前提、不补外部来源。

## 文件结构

```
skill-note/
├── SKILL.md    # 主指令：四关 + 分步工作流 + 输出契约 + 异常处置 + 诚实性铁律
└── README.md   # 本说明（字段字典、锚点格式、依赖、示例、限制与维护）
```

纯指令型任务，**不含 scripts**；无自定义脚本依赖。

## 论文卡片字段字典（15 个统一字段）

| 字段 | 含义 | 锚点最低粒度 |
|---|---|---|
| `title` | 标题（原文原样） | 页 |
| `authors` | 作者 | 页 |
| `year` | 年份（原文可确认） | 页 |
| `venue_or_source` | 期刊/会议/预印本来源 | 页 |
| `research_question` | 研究问题/目标 | 节·段 |
| `gap_and_motivation` | 研究缺口与动机 | 节·段 |
| `data` | 数据（来源/规模/划分/时间） | 数值到图表 |
| `methods` | 方法（条件/参数/基线/指标） | 数值到图表 |
| `main_findings` | 主要发现（方向+数值） | 图表/段 |
| `conclusions` | 结论（论文自己的判断） | 节·段 |
| `preconditions` | 前提条件/假设（让结论成立） | 图表/段 |
| `limitations` | 局限（自述；无则"未报告"） | 节·段 |
| `scope_and_applicability` | 适用范围 | 节·段 |
| `key_metrics` | 关键变量与指标（符号+单位+定义处） | 图表/公式 |
| `terms_and_abbreviations` | 术语与缩写 | 图表/段 |
| `claims_in_conflict` | 冲突/不一致 | 图表/段 |

字段值统一为对象数组：`{statement, anchor, verbatim?, source_kind}`，`source_kind ∈ explicit|inferred|summary`（原文明写 / 由原文推断 / 概括）。

## 锚点格式

机器锚点（`result.json` 内统一使用）：

```
p{页码}:§{节}:{对象}{编号}
```

对象：`para{n}` 段、`fig{n}` 图、`tab{n}` 表、`eq{n}` 公式、`block{n}` 文本块（扫描件兜底）、`line{n}` 行（可选）。

示例：`p5:§3.2:para2` = 第 5 页 · 第 3.2 节 · 第 2 段；`p7:§4.1:fig3` = 第 7 页 · 第 4.1 节 · 图 3。

人读版（`note.md`）可内联写成 `(p5 · §3.2 · 第2段)`。详见 SKILL.md 第六节。

## 输出契约（`/app/output/result.json`）

必含：`case_id`、`status`（success/partial/failed/refused）、`paper_card`（论文卡片）、`section_notes`（章节笔记）、`knowledge_items`（知识点条目）、`anchor_index`（锚点索引）、`evidence`（主结果→原文定位总账）、`uncertainties`（未报告/不确定项）、`notes`（运行说明）。完整 schema 见 SKILL.md 第八节。

## 依赖

- 运行环境（平台提供）：`pdf-text-tool`（文本层）、`pdf-render-tool`（渲染页面查看图表/公式）、`ocr-tool`（扫描件）。
- JSON 校验：`python3 -m json.tool`（标准库，无需安装）。
- 本 Skill 无第三方库、无自研脚本依赖。

## 调用示例

**输入**：`/input/case.json`（`task` + `output_contract` + 材料路径）与 `task.md`；材料为真实论文 PDF。

**执行**：按 SKILL.md 分步工作流——读输入定边界 → 建章节骨架 → 逐章精读写章节笔记 → 填论文卡片 → 提取归并知识点 → 锚点回链校验 → 写 `result.json` 与 `note.md`。

**输出**：`/app/output/result.json` + `/app/output/note.md`。节选示意（**示例，非正式案例结果**）：

```json
{
  "case_id": "example-case",
  "status": "success",
  "paper_card": {
    "research_question": [ { "statement": "…", "anchor": "p2:§1:para2", "source_kind": "explicit" } ],
    "preconditions": [ { "statement": "…", "anchor": "p5:§3.2:para1", "source_kind": "explicit" } ]
  },
  "section_notes": [ { "section_id": "§3", "heading": "3. Methods", "page_range": [4, 6], "content_or_method": "…" } ],
  "knowledge_items": [ { "id": "K001", "type": "concept", "canonical": "…", "terms": [], "definition": "", "anchors": ["p2:§1.1:para1"], "relations": [] } ],
  "anchor_index": [ { "anchor": "p2:§1:para2", "target": "…", "verified": true } ],
  "evidence": [ { "claim": "…", "anchor": "p2:§1:para2" } ],
  "uncertainties": [],
  "notes": ["纯指令型 Skill，无脚本"]
}
```

## 自查方法（提交前逐项检查）

1. **对得上**：章节笔记是否按原文标题树组织，未套通用摘要模板。
2. **留得住**：研究问题/数据/方法条件/主要发现/局限/前提条件是否都已记录（尤其 `preconditions`）。
3. **找得回**：每条关键论断是否有锚点，锚点是否真实指回原文（`p页码:§节:对象编号`）。
4. **用得上**：知识点是否已归一/去重、矛盾是否标记，能否被检索与复用。
5. **诚实性**：`source_kind` 是否如实标注（explicit/inferred/summary），读不出/不确定/冲突是否写入 `uncertainties`，未补造。
6. **状态如实**：有未决项则 `status=partial`，不要写 `success`。

## 适用范围

- 数字版（有文字层）与扫描版（走 OCR）科研论文；中英文均可，英文论文笔记用中文写、关键句保留英文引文。
- 也适用于按原文结构整理的综述、报告、教材（卡片中不适用字段标"不适用"）。
- 预算内可处理常见篇幅论文；超长文按 SKILL.md 第九节降级为"标题树 + 关键字段 + 每节一段 + 关键知识点"。

## 限制与维护

- **纯指令型、无脚本**：多数字段由模型依原文整理，语义正确性依赖"锚点回链"兜底；含数值/条件的字段必须人工按锚点复核一遍。
- 复杂跨栏跨页表格、低分辨率扫描件、特殊字体公式仍可能失败；失败处写入 `uncertainties` 并给出可人工接管位置，不冒充精确文本。
- 术语归并依赖同义判断，存在边界；不确定是否同义时保留两条并加 `uncertain`，不强行合并。
- 维护：字段字典或锚点格式变更时，同步更新 SKILL.md 第五节/第六节与本节，保持版本一致；新增字段先并入 `paper_card` 再补 README 说明。
