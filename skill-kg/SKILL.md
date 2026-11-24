---
name: literature-kg-builder
description: 从科研论文抽取实体与关系、构建带证据的可查询知识图谱。触发条件：任务要求把论文转成知识图谱、抽取实体/关系、实体对齐/归一、跨篇对齐、图谱查询或增量更新。受控词表：实体＝研究者/材料/方法/任务/指标/结论；关系＝使用/提出/评估于/比较/优于/支持/矛盾/属于；每个节点与每条边绑定 source_id、JATS paragraph_id 与原文短引，并标注证据强度。
---

# 文献知识图谱构建（阅读15）

把一批论文变成**可查询、可复核、可增量更新**的知识图谱：节点 = 论文中真实出现的科研对象，边 = 有原文证据支撑的关系，每个节点每条边都能回到 `source_id + JATS段落ID + 原文短引`。产出一份 `result.json`（含图结构、对齐记录、冲突记录、查询结果与证据）和一份人可读的 `graph.md` 图谱导出。

> 事实依据只有 `/input` 下的材料原文，不依据文件名/领域标签/模型常识补造数据。

## 〇、目标与四个质量关口

**目标**：在同一张图中保留多篇论文的节点、关系与来源；实体真实存在于论文、关系有原文证据、别名对齐可解释、每个元素可回查。

四个质量关口（每步结束都要逐项自查）：

1. **抽得准**：实体必须是论文里真实出现的科研对象（研究者/材料/方法/任务/指标/结论），不是模型凭常识补全的概念。凡不能在原文定位到短引的实体一律不建节点。
2. **连得对**：关系类型、方向、适用条件与原文一致；只建有证据的关系。**共现 ≠ 关系，综述转述 ≠ 直接证据，推测 ≠ 断言**。
3. **对得齐**：别名、缩写、大小写、全称简称、同名冲突正确处理：该合不重、该分不并；每次合并/拒绝合并都要写清可解释依据。
4. **查得到、回得去**：图谱能回答真实查询；每个节点每条边都能回到 `source_id + paragraph_id + 原文短引`，并带证据强度。

## 一、受控词表 · 实体类型（6 类，不许自行增删）

| 类型取值 | 含义 | 实例范围 | 典型对象 | 抽取时必须确认 |
|---|---|---|---|---|
| `researcher` | 研究者/机构 | 具体个人或机构 | 论文作者、被引工作作者、研究组/实验室/机构 | 记录 `role`（第一/通讯/共同作者）；区分"作者自述"与"转述他人"（`claim_origin`） |
| `material` | 材料/制品/数据资源 | 以 `specific` 为主，仅同一实例才可跨篇合并 | 化合物/物质、试剂/药物/抗体、细胞/菌株/生物体、物理样品、仪器设备、数据集、预训练模型实例（有检查点/版本）、软件制品 | 记录版本/DOI/货号/下载链接/来源标识；**通用术语 ≠ 同一物理样品/模型实例/数据集** |
| `method` | 方法/技术/算法 | 通常 `generic`（方法类）；有命名版本/检查点的模型实例归 `material` | 技术、算法、模型架构、流程/规程、评估协议、软件工具/框架、统计检验 | 把"命名实例（如 GPT-3 检查点）"与"通用类（如 自回归语言模型）"分开 |
| `task` | 任务/基准 | 命名基准 `specific`；通用任务 `generic` | 研究任务、基准评测、下游应用问题 | 记录版本/数据集构成；不把不同设定当同一任务 |
| `metric` | 指标/统计量 | `generic`（同一指标定义） | 准确率、F1、BLEU、MSE、AUC | 指标节点只存定义；**数值属于边属性，不并入指标节点** |
| `conclusion` | 结论/论断/假设 | 每条结论属于特定论文，**跨篇永不合并** | 论文论断、发现、假设、声明 | 记录支持/反对它的证据；区分"断言"与"推测"（`certainty`） |

每个实体的 `instance_scope` 取 `specific` 或 `generic`；跨篇合并规则（第五节）按类型与实例范围分别生效。

## 二、受控词表 · 关系类型（方向 + 适用条件）

方向固定为「主语 → 宾语」，写入边的 `source_node` / `target_node`。**只有满足"适用条件"才建边，否则不建或降为弱证据并注明。**

| 关系取值 | 方向（主语→宾语） | 适用主语 | 适用宾语 | 建边条件（原文必须满足） | 禁止（反例） |
|---|---|---|---|---|---|
| `proposes` 提出 | 提出者 → 被提出物 | researcher / 论文 | method / conclusion / material | 有 "propose/introduce/develop/present/提出/设计/构建" 等直接动词 | 转述他人提出，不算该论文自提（用 `claim_origin=attributed` 或改为 `uses`） |
| `uses` 使用 | 使用者 → 被用物 | method / researcher / 论文 | method / material / task / metric | 有 "use/employ/apply/adopt/leverage/采用/使用/应用" 等直接动词 | 仅同段共现不算使用 |
| `evaluated_on` 评估于 | 方法/模型 → 数据集/任务 | method / material(模型实例) | task / material(数据集) | 有 "evaluate on/benchmark on/test on/在…上评估/在…上测试" 等表述 | 未说明评估对象不建边 |
| `compared_with` 比较 | 比较方 → 被比较基线 | method | method | 有 "compare with/baseline/对比/与…比较" 等表述 | 表格相邻但无显式比较语句不算 |
| `outperforms` 优于 | 胜者 → 败者 | method | method | 论文**自己明确声称**优于，且指明指标与条件（任务/数据集/样本量/显著性）；优先采论文结论句，数值只作佐证 | 仅数值更优而论文未声称 → 不建；若要记，降为弱证据并写进 `uncertainties` |
| `supports` 支持 | 证据 → 结论 | conclusion / 结果 / 论文 | conclusion | 有 "support/confirm/indicate/suggest/consistent with/支持/证实/表明/与…一致" | 纯推测语气不标"支持"，用 `supports` 需降级或改 `notes` |
| `contradicts` 矛盾 | 反对方 → 被反对方 | conclusion / 结果 | conclusion | 有 "contradict/inconsistent with/contrary to/矛盾/不一致/相反" 且是显式对立 | 数值差异 ≠ 矛盾；无显式对立不建 |
| `instance_of` 属于 | 实例 → 类别 | material / method / task | material / method / task（类别） | 有 "X is a Y / X 是一种 Y" 或结构化定义 | 模型常识归类不建（那是补全，不是抽取） |

方向/条件写进每条边；`outperforms` 必须携带 `conditions`（指标 + 任务/数据集 + 条件），缺条件即不建。

## 三、节点 / 边 schema

### 3.1 节点

```json
{
  "node_id": "n0001",
  "entity_type": "researcher|material|method|task|metric|conclusion",
  "canonical_name": "规范化后的标准名",
  "instance_scope": "specific|generic",
  "attributes": { "role": "corresponding_author", "version": null, "doi": null, "catalog": null },
  "certainty": "asserted|hypothesized",
  "surface_forms": [
    { "text": "原文中的表面形式", "source_id": "P1", "paragraph_id": "sec2-para5" }
  ],
  "evidence": [
    { "source_id": "P1", "paragraph_id": "sec2-para5", "section": "2. Methods", "fig_table": null, "quote": "…原文短引…", "formula_lossy": false }
  ],
  "merged_from": ["n0003", "n0017"],
  "merge_basis": "同一数据集：两文均给出同一下载 URL 且版本相同",
  "conflict_notes": []
}
```

- `node_id`：全局稳定编号 `n0001…`，增量更新**永不重号**（见第八节）。
- `certainty`：`asserted`（论文明确断言）或 `hypothesized`（论文以假设/推测提出）；后者必须出现在 `uncertainties`。
- `merged_from`：被合并进来的旧节点 id；`merge_basis` 必填且可解释。同名但判定为不同对象时 `merged_from` 为空，改在 `conflict_notes` 记原因并保留各自节点。

### 3.2 边

```json
{
  "edge_id": "e0001",
  "source_node": "n0001",
  "relation": "outperforms",
  "target_node": "n0004",
  "evidence": [
    { "source_id": "P1", "paragraph_id": "sec4-para7", "section": "4. Results", "fig_table": "tab3", "quote": "…原文短引…", "formula_lossy": false }
  ],
  "evidence_strength": "强|中|弱",
  "claim_origin": "self|attributed|derived",
  "conditions": { "metric": "BLEU", "task": "机器翻译", "dataset": "WMT14 En-De", "significance": null },
  "status": "asserted|conflicted|superseded",
  "superseded_by": null
}
```

- `evidence_strength`：见第四节。`outperforms` / `contradicts` / `supports` 三类强断言边，`弱` 证据一律不建或改记 `uncertainties`。
- `claim_origin`：`self`=作者自述；`attributed`=转述他人（如 "X 报告…"）；`derived`=由结果数值推导。`attributed`/`derived` 只能配 `中`/`弱` 证据，且必须写入 `uncertainties`。
- `conditions`：关系的适用条件（指标/任务/数据集/样本量/温度等），凡能定位就写全。
- `status`：`conflicted`（源内或跨篇冲突）、`superseded`（被更新的边取代，配合 `superseded_by` 指向新边 id），用于冲突处理与增量更新。

## 四、来源绑定与证据强度

**位置一律用 `source_id + paragraph_id`（JATS 段落 ID），不编造 PDF 页码。** 本包无 PDF 页码，任何"自建页面 1"都不等于原 PDF 页。

证据强度三档：

- `强`：原文逐字、作者自述、直接陈述该实体存在或该关系成立；有 verbatim 短引。
- `中`：论文报告的表格/摘要/结果中的作者结论，直接支撑该关系；短引为作者原句摘要。
- `弱`：需拼接多句、或他人转述、或仅数值比较而论文未明确声称；**必须同时写入 `uncertainties`**，且不得用于 `优于/矛盾/支持` 强断言。

`claim_origin` 与强度联动：`self` 可配强/中；`attributed` 配中/弱；`derived` 只配弱。

行内公式/上下标被线性化：短引含公式时，先到 `*-publisher.xml` 核对原始标记；无法确认就设 `formula_lossy: true` 并在 `uncertainties` 说明，**不猜测上下标**。

## 五、实体对齐与别名归一（可执行规则）

按顺序执行，每步都留下可解释记录。

1. **收集表面形式**：逐篇把同一实体的所有写法（全称、简称、缩写、大小写、单复数、连字符变体）连同 `source_id + paragraph_id` 收进 `surface_forms`。
2. **规范化（纯字符串，不改语义）**：trim 空白；英文转小写；Unicode 全角转半角；去尾部标点；统一希腊字母与常用变体（α↔alpha 仅当原文同段给出对应）；**缩写展开只采用论文自己声明的等价**（如 "MoS2 (molybdenum disulfide)"），不凭外部常识展开。
3. **篇内别名合并**：同一论文内明确等价（"X (Y)"、"Y, X"、上下文同指）→ 合并为一个节点，`merge_basis` 记"篇内同指"。
4. **跨篇候选匹配**：规范化名相同才进入候选；再按类型判定是否可合并：

| 实体类型 | 可合并条件（全部满足） | 不可合并（保持分节点） |
|---|---|---|
| `researcher` | 同名 + 机构/领域/邮箱/ORCID 一致或有直接引用线索 | 同名不同机构/领域 → 同名冲突，`conflict_notes` 记录，**不合并** |
| `material`（数据集/模型实例/物理样品/试剂等） | 两文引用**同一外部实例**：相同 DOI/下载 URL/货号/版本号/明确出处 | 仅术语相同、无实例标识、版本/条件不同 → **不同实例，不合并** |
| `method`（方法类） | 同一命名方法/架构类（如 BERT、随机森林）→ 合并为方法类节点 | 具体模型实例（某检查点）与通用类不混并；实例归 `material` |
| `task`（命名基准） | 同一基准且版本一致（如 GLUE）→ 合并 | 通用任务术语（如"文本分类"）不与具体基准混并 |
| `metric` | 同一指标定义 → 合并；数值仍在各边 `conditions` | 不同定义/不同版本指标（如 BLEU 的不同实现）不并 |
| `conclusion` | **永不跨篇合并** | 每条结论是特定论文的论断；仅篇内逐字重复才并 |

5. **写出依据**：每次合并必须写 `merge_basis`（具体依据）+ `merged_from`；拒绝合并写 `conflict_notes`（为何同名却是不同对象）。不确定时**不强行合并**：保持两节点，另加一条 `alignment` 记录 `decision=unresolved`。
6. **不强迫合并**：不要求每个别名都并；同篇多文件格式不是跨篇证据；相同通用方法/材料术语不等于相同物理样品、模型实例、数据集或实验条件。

## 六、分步工作流（严格按序执行）

### 第 1 步：读输入与建源清单
- 读 `/input/case.json`（任务与 `output_contract`）、`/input/task.md`。
- 读 `corpus-manifest.json`：为每个条目建 `source_id`（P1、P2…按清单顺序；若清单含显式 id/doi 用其 id），记录各篇自己的 DOI/作者/来源哈希/许可证。
- **根 DOI/title/authors 只属于第一篇（P1），不得套到第二篇。**
- 读 `material.json`（段落汇总索引）、`primary-material.json`（P1 正文）、`secondary-material.json`（P2 正文）；必要时读 `*-publisher.xml` 核对公式。
- 检查哈希/许可证是否齐全，缺失写进 `notes`，不影响构建但不得伪装已校验。

### 第 2 步：建段落索引
- 由 `material.json` 建 `paragraph_id → (source_id, text)` 映射。
- `paragraph_id` 一律原样引用输入给的 JATS 段落 ID；若两篇段落 ID 可能撞名，引用时写成 `P1:段落ID` / `P2:段落ID`。
- 记录章节标题、图/表编号（`fig_table`）作为可回查定位；**不编页码**。

### 第 3 步：实体识别（先全后筛）
- 每篇独立抽取 6 类候选：表面形式 + `paragraph_id` + 原文短引。
- 判 `instance_scope`（specific/generic）、`certainty`（asserted/hypothesized）、作者自述 vs 转述（看引用标记、"they/previous work reported"、"根据…"）。
- 筛掉无法回原文定位的候选；缺短引的候选不建节点。

### 第 4 步：实体规范化与对齐
- 按第五节执行字符串规范化 → 篇内别名合并 → 跨篇候选匹配 → 写 `merge_basis`/`conflict_notes`。
- 生成 `alignments` 记录：`{node_ids, decision: merged|separate|unresolved, basis, confidence}`。

### 第 5 步：关系抽取（只建有证据的边）
- 对每对候选实体，只在原文存在第二节"建边条件"的动词/表述时建边。
- 确定方向、`conditions`、`evidence_strength`、`claim_origin`。
- 共现无动词 → 不建；转述 → `claim_origin=attributed` 并降级；仅数值比较 → 不建 `outperforms`，改记 `uncertainties`。

### 第 6 步：证据标注与冲突处理
- 每条节点/边绑定 `source_id + paragraph_id + quote`，标强度。
- 源内冲突（如摘要与正文结论相反）、跨篇冲突（两文对同一方法结论相反）→ 分别建两条边、`status=conflicted`，在 `conflicts` 记录对立内容与各自证据，**不自行裁决谁对**。

### 第 7 步：执行查询（≥3 个，见第七节）
- 至少执行 3 个真实查询，逐条返回子图 + 支撑证据 + 无法确定的关系。

### 第 8 步：写出结果与图谱导出
- 写 `/app/output/result.json`（第九节契约）。
- 同时写人可读导出 `/app/output/graph.md`（节点表 + 边表 + 对齐/冲突记录）；如任务要求可视化再写 `/app/output/graph.gv`（Graphviz DOT）。这些是运行时产物，非预置答案。

## 七、图谱查询（≥3 个模板，含子图与证据返回）

查询返回格式统一为：

```json
{
  "query": "<自然语言查询>",
  "traversal": "<遍历路径说明>",
  "subgraph": { "nodes": [ …节点子集… ], "edges": [ …边子集… ] },
  "evidence": [ { "node_or_edge": "n0001|e0004", "source_id": "P1", "paragraph_id": "…", "quote": "…", "evidence_strength": "强" } ],
  "unanswered": [ "<本次材料无法回答的问题，留空不猜>" ]
}
```

### 查询模板 1：方法 → 数据集/任务 → 结果
**问**："方法 M 在哪些数据集/任务上被评估？相对基线表现如何？"
**遍历**：`method M --evaluated_on--> task/dataset D`，再找 `M --compared_with--> baseline B` 与 `M --outperforms--> B`，取各边 `conditions` 中的指标数值。
**返回**：M、D、各 B 节点子集；`evaluated_on`、`compared_with`、`outperforms` 边子集。
**证据**：每条边回 `source_id + paragraph_id + quote`；数值附 `conditions.metric` 与所在图表（`fig_table`）。
**unanswered**：若某数据集的评估只在摘要提及而正文无表，标注"未报告对应数值"。

### 查询模板 2：研究者 → 提出 → 比较/优于
**问**："研究者 A 提出了什么方法？该方法与哪些基线比较、在什么条件下是否优于？"
**遍历**：`researcher A --proposes--> method M`，再按模板 1 展开比较与优于子图。
**返回**：A、M、基线集合及其 `compared_with`/`outperforms` 边（含 `conditions` 与 `claim_origin`）。
**证据**：区分作者自述（`self`）与转述（`attributed`）；若"优于"只是数值优势无作者结论，放进 `unanswered`。

### 查询模板 3：跨篇对齐 / 同名冲突
**问**："两篇论文中的术语 T 是否指向同一对象（同一材料/数据集/模型实例/方法/研究者）？"
**遍历**：取 `canonical_name` 含 T 的所有节点 → 返回其 `merge_basis` 或 `conflict_notes`，以及 `alignments` 记录。
**返回**：候选节点子集 + 各自的 `evidence`；合并则显示同一 `node_id`，分节点则显示两个 `node_id` 与各自来源。
**证据**：每个节点回各自 `source_id + paragraph_id + quote`；合并依据必须是"同一外部实例标识"或"机构/领域一致"等可解释理由，而不是术语相同。
**unanswered**：缺少版本/DOI/出处时，明确写"无法判定是否同一实例"。

### 查询模板 4：证据 → 结论（支持/矛盾）
**问**："哪些证据支持或反对结论 C？"
**遍历**：`conclusion C <--supports-- 证据节点` 与 `conclusion C <--contradicts-- 对立节点`。
**返回**：C 及其 `supports`/`contradicts` 入边子图。
**证据**：每条边回原文定位；`claim_origin` 区分作者结论与他人转述。
**unanswered**：无直接证据时写"材料未报告支持/反对 C 的直接证据"。

## 八、增量更新（保留既有节点编号）

新论文加入时执行：

1. **只增不改**：既有 `node_id`/`edge_id` 永不重号、永不删除；新对象取新的全局序号。
2. **复用与合并**：新实体匹配既有节点且满足第五节合并条件 → 不改既有 `node_id`，把新 `surface_forms`/`evidence` 追加到该节点，`merged_from` 追加旧/新 id，更新 `merge_basis`。
3. **同名冲突**：不合并 → 新建节点，`conflict_notes` 记"与 nXXXX 同名但非同一对象（原因）"。
4. **关系更新**：新证据推翻旧关系时**不删旧边**，把旧边 `status=superseded` + `superseded_by=新边id`，新建边承载新证据；新旧同时保留可追溯。
5. **版本与变更日志**：`graph_version` 递增（v1→v2），`change_log` 逐条记 `{version, action: add_node|merge_nodes|add_edge|supersede_edge|conflict, ids, reason, evidence}`。
6. **重导图谱**：更新后重写 `graph.md`（及可选 `graph.gv`），保证导出与 `result.json` 一致。

## 九、输出契约（result.json 必填字段）

```json
{
  "case_id": "<来自输入>",
  "status": "success | partial | failed | refused",
  "graph": {
    "graph_version": "v1",
    "sources": [
      { "source_id": "P1", "doi": "…", "title": "…", "authors": ["…"], "hash": "…", "license": "…", "role": "primary" },
      { "source_id": "P2", "doi": "…", "title": "…", "authors": ["…"], "hash": "…", "license": "…", "role": "secondary" }
    ],
    "nodes": [ { "node_id": "n0001", "entity_type": "…", "canonical_name": "…", "instance_scope": "…", "attributes": {}, "certainty": "…", "surface_forms": [], "evidence": [], "merged_from": [], "merge_basis": "", "conflict_notes": [] } ],
    "edges": [ { "edge_id": "e0001", "source_node": "n0001", "relation": "…", "target_node": "n0002", "evidence": [], "evidence_strength": "…", "claim_origin": "…", "conditions": {}, "status": "…", "superseded_by": null } ],
    "alignments": [ { "node_ids": ["n0001","n0002"], "decision": "merged|separate|unresolved", "basis": "…", "confidence": "确定|可能|不确定" } ],
    "conflicts": [ { "node_or_edge_ids": ["e0003","e0007"], "kind": "源内冲突|跨篇冲突", "description": "…", "evidence": [] } ],
    "change_log": [ { "version": "v1", "action": "…", "ids": [], "reason": "…", "evidence": [] } ]
  },
  "queries": [
    { "query": "…", "traversal": "…", "subgraph": { "nodes": [], "edges": [] }, "evidence": [], "unanswered": [] }
  ],
  "evidence": [ { "node_or_edge": "…", "source_id": "…", "paragraph_id": "…", "section": "…", "fig_table": null, "quote": "…", "evidence_strength": "…" } ],
  "uncertainties": [ { "where": "…", "what": "…", "why": "…", "how_to_verify": "…" } ],
  "notes": [ "输入清单、公式线性化、材料缺失、降级等说明" ]
}
```

- `status`：全部完成 `success`；部分关系/数值读不出但已如实标注 `partial`；材料缺失/无法解析 `failed`；拒绝（如越权/涉敏）`refused`，并在 `notes` 写原因。
- 主结果字段 = `graph`（节点/边/对齐/冲突/变更日志）；`queries` 为查询交付；`evidence`/`uncertainties`/`notes` 满足输出契约要求。
- 每条 `evidence` 都能回到原文；`uncertainties` 只装"未报告/不确定"，**不把不确定写成事实**。

## 十、异常与边界处置

| 情况 | 处置 |
|---|---|
| `corpus-manifest.json` 缺失/缺条目 | 仍可从 material 文件构建，`status=partial`，`notes` 写"清单缺失，DOI/哈希未校验"；不伪造 DOI/哈希 |
| 某篇正文缺失或空 | 只构建可读部分，`status=partial`，缺失篇不进图，`notes` 说明 |
| 段落 ID 缺失/重复 | 用 `source_id:第k段` 兜底并在 `notes` 声明"段落 ID 为自建索引，非原文 JATS ID" |
| 公式被线性化、上下标不确定 | 回 `*-publisher.xml` 核对；仍不确定 → `formula_lossy:true` + `uncertainties`，不猜 |
| 同名实体、无法判定是否同一实例 | 保持分节点，`alignments.decision=unresolved`，`conflict_notes` 记原因 |
| 源内/跨篇结论相反 | 两边各建边、`status=conflicted`、`conflicts` 记录，不自行裁决 |
| 无图像像素/补充附件/底层临床或实验数据 | 不推断其中数值；相关数值写 `uncertainties` 并注明"未提供" |
| 查询无结果 | 返回空子图 + `unanswered` 说明"材料未报告"，不硬凑答案 |
| 关系只有共现/转述/推测 | 不建边或降为弱证据并写 `uncertainties` |
| 预算将尽 | 先落盘 `partial` 的 result.json（保 case_id/status/已完成的 graph/queries），再增量完善 |

## 十一、诚实性铁律

1. 实际输入材料与原文是**唯一事实依据**；不依据文件名/领域标签/模型常识补造实体或数值。
2. 读不出、无法判断、公式失真、材料缺失 → 一律显式标注；**不猜测、不补全、不伪造**。
3. **不把共现当关系，不把转述当作者自述，不把推测当断言**；缺适用条件的 `优于/矛盾/支持` 一律不建或降级并注明。
4. 不把两篇论文的条件、样本、数值合成一个结论；相同通用术语不默认同一实例；同篇多格式不是跨篇证据。
5. 根 DOI/title/authors 只属 P1；位置只认 JATS `paragraph_id`，不编造 PDF 页码。
6. 合并必须可解释（写 `merge_basis`），拒绝合并写 `conflict_notes`；不确定就保持分节点。
7. `status` 如实反映完成度；部分结果要写清边界，供人工接管。

## 十二、自查清单（提交前逐项打勾）

- [ ] 每个节点都能在原文定位到短引？有 `entity_type` 与 `instance_scope`？
- [ ] 每条边都有触发动词/表述、方向正确、`conditions` 齐全、证据强度与 `claim_origin` 匹配？
- [ ] 每次合并/拒绝合并都有 `merge_basis`/`conflict_notes`，且依据可解释？
- [ ] 至少 3 个查询已实际执行，子图 + 证据 + `unanswered` 齐全？
- [ ] 结果含 `case_id/status/graph/queries/evidence/uncertainties/notes`，`status` 诚实？
- [ ] 没有自造 PDF 页码、没有把根 DOI 套到第二篇、没有推断未提供的数据？
