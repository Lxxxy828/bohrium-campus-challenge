# 文献知识图谱构建 Skill（阅读15）

把一批科研论文转成**带证据、可查询、可增量更新**的知识图谱：节点只收录论文中真实出现的科研对象，边只建立有原文证据的关系，每个节点与每条边都能回到 `source_id + JATS段落ID + 原文短引`。本 Skill 是纯指令型（无脚本），运行时由加载它的 Agent 逐条执行 SKILL.md 中的工作流。

## 一、用途与适用条件

- **用途**：从论文抽取实体与关系 → 实体对齐/别名归一 → 证据绑定与强度标注 → 图谱查询 → 跨篇对齐与增量更新；交付 `result.json` 与人可读 `graph.md` 图谱导出。
- **适用**：有正文文本的科研论文材料（JATS 段落文本 + 可选 `*-publisher.xml`），单篇或多篇（含跨篇对齐）。
- **不适用**：只有图像像素而无正文文本、只做纯 PDF 版面还原（那是 PDF 解析 Skill 的职责）、以及要求从补充附件/底层实验数据推断数值的任务——本 Skill 明确不推断未提供的数据。
- **安装**：纯指令型，无脚本、无第三方依赖，**无需安装任何包**；运行环境由平台提供（文本抽取/渲染工具）。

## 二、实体类型定义

| 取值 | 定义 | 实例范围 | 跨篇合并关键 |
|---|---|---|---|
| `researcher` | 研究者/机构 | specific | 同名 + 机构/领域/ORCID/邮箱一致才并；否则同名冲突分节点 |
| `material` | 材料/制品/数据集/模型实例/试剂/仪器/软件制品 | specific 为主 | 同一外部实例标识（DOI/URL/货号/版本）才并；术语相同 ≠ 同一实例 |
| `method` | 方法/技术/算法/流程/工具/统计检验 | generic 为主 | 同一命名方法类才并；命名模型实例归 `material` |
| `task` | 任务/基准 | 命名基准 specific；通用任务 generic | 同一基准且版本一致才并 |
| `metric` | 指标/统计量 | generic | 同一指标定义才并；数值在边属性，不在节点 |
| `conclusion` | 结论/论断/假设 | 特定论文 | **跨篇永不合并** |

## 三、关系类型定义（方向 + 适用条件）

| 关系 | 方向 | 建边条件（原文必须出现） |
|---|---|---|
| `proposes` 提出 | 提出者 → 被提出物 | propose/introduce/develop/present/提出/设计 |
| `uses` 使用 | 使用者 → 被用物 | use/employ/apply/adopt/采用/使用 |
| `evaluated_on` 评估于 | 方法/模型 → 数据集/任务 | evaluate on/benchmark on/在…上评估 |
| `compared_with` 比较 | 比较方 → 基线 | compare with/baseline/与…比较 |
| `outperforms` 优于 | 胜者 → 败者 | 论文自述优于 + 指标 + 条件（任务/数据集/样本量） |
| `supports` 支持 | 证据 → 结论 | support/confirm/indicate/consistent with/支持/表明 |
| `contradicts` 矛盾 | 反对方 → 被反对方 | contradict/inconsistent with/矛盾/不一致 |
| `instance_of` 属于 | 实例 → 类别 | X is a Y / X 是一种 Y（原文显式） |

硬约束：共现 ≠ 关系；转述（`claim_origin=attributed`）降级；仅数值优势无作者结论不建 `outperforms`。

## 四、schema

### 节点

```json
{
  "node_id": "n0001",
  "entity_type": "material",
  "canonical_name": "ImageNet-1k",
  "instance_scope": "specific",
  "attributes": { "version": "1k", "doi": null, "catalog": null },
  "certainty": "asserted",
  "surface_forms": [ { "text": "ImageNet", "source_id": "P1", "paragraph_id": "sec3-para2" } ],
  "evidence": [ { "source_id": "P1", "paragraph_id": "sec3-para2", "section": "3. Experiments", "fig_table": null, "quote": "…", "formula_lossy": false } ],
  "merged_from": ["n0005"],
  "merge_basis": "两文均引用同一 ImageNet 下载来源且同为 1k 类别",
  "conflict_notes": []
}
```

### 边

```json
{
  "edge_id": "e0001",
  "source_node": "n0001",
  "relation": "outperforms",
  "target_node": "n0004",
  "evidence": [ { "source_id": "P1", "paragraph_id": "sec4-para7", "section": "4. Results", "fig_table": "tab3", "quote": "…", "formula_lossy": false } ],
  "evidence_strength": "强",
  "claim_origin": "self",
  "conditions": { "metric": "BLEU", "task": "机器翻译", "dataset": "WMT14 En-De", "significance": null },
  "status": "asserted",
  "superseded_by": null
}
```

### 证据强度

- `强`：原文逐字、作者自述、直接陈述；有 verbatim 短引。
- `中`：论文表格/摘要/结果中的作者结论直接支撑。
- `弱`：拼接多句、他人转述、或仅数值比较而论文未声称；**必须写进 `uncertainties`，不得用于强断言边**。

## 五、对齐与别名归一规则（可解释）

1. 收全表面形式（全称/简称/缩写/大小写/变体）。
2. 字符串规范化：trim、小写、全角转半角、去尾标点、统一希腊字母；缩写展开仅用论文自述等价。
3. 篇内明确同指合并；跨篇按类型判定（见第二节"跨篇合并关键"）。
4. 每次合并写 `merge_basis + merged_from`；拒绝合并写 `conflict_notes`；不确定写 `alignments.decision=unresolved` 并保持分节点。
5. 不强迫合并；相同通用术语不默认同一实例；同篇多文件格式不是跨篇证据。

## 六、查询模板（≥3，实际执行时替换为真实实体）

1. **方法 → 数据集/任务 → 结果**：方法 M 在哪些数据集/任务被评估？相对基线表现如何？
2. **研究者 → 提出 → 比较/优于**：研究者 A 提出了什么方法？与哪些基线比较、在什么条件下是否优于？
3. **跨篇对齐/同名冲突**：两篇中的术语 T 是否同一对象？合并依据或冲突是什么？
4. **证据 → 结论**：哪些证据支持/反对结论 C？

每个查询返回：`query + traversal + subgraph{nodes,edges} + evidence + unanswered`（模板见 SKILL.md 第七节）。

## 七、增量更新规则

- 既有 `node_id`/`edge_id` 永不重号、永不删除；新对象取新序号。
- 匹配则复用既有节点（追加 surface_forms/evidence、更新 merged_from/merge_basis）。
- 同名不同对象 → 新建节点 + `conflict_notes`。
- 新证据推翻旧关系 → 旧边 `status=superseded + superseded_by`，不删除。
- `graph_version` 递增，`change_log` 逐条记录增/并/取代/冲突。

## 八、调用示例（示意，非正式案例答案）

输入目录结构（平台运行时提供）：

```
/input/case.json                 # 任务说明 + output_contract + 材料路径
/input/task.md
/input/corpus-manifest.json      # 各篇 DOI/作者/哈希/许可证
/input/material.json             # 两篇正文段落汇总索引
/input/primary-material.json     # P1 正文
/input/secondary-material.json   # P2 正文
/input/*-publisher.xml           # JATS 原文，供公式核对（可选）
```

Agent 按 SKILL.md 工作流执行，最终写出：

```
/app/output/result.json   # 含 case_id/status/graph/queries/evidence/uncertainties/notes
/app/output/graph.md      # 人可读图谱导出（节点表+边表+对齐/冲突）
/app/output/graph.gv      # 可选：Graphviz DOT 可视化
```

示意输出（节选，标注为示例）：

```json
{
  "case_id": "example",
  "status": "success",
  "graph": {
    "graph_version": "v1",
    "sources": [
      { "source_id": "P1", "doi": "10.xxxx/primary", "title": "…", "authors": ["…"], "role": "primary" }
    ],
    "nodes": [
      { "node_id": "n0001", "entity_type": "method", "canonical_name": "BERT", "instance_scope": "generic", "surface_forms": [{"text":"BERT","source_id":"P1","paragraph_id":"sec1-para1"}], "evidence": [{"source_id":"P1","paragraph_id":"sec1-para1","quote":"…"}], "merged_from": [], "merge_basis": "", "conflict_notes": [] }
    ],
    "edges": [
      { "edge_id": "e0001", "source_node": "n0001", "relation": "evaluated_on", "target_node": "n0002", "evidence": [{"source_id":"P1","paragraph_id":"sec3-para5","quote":"…"}], "evidence_strength": "强", "claim_origin": "self", "conditions": {"dataset":"GLUE"}, "status": "asserted", "superseded_by": null }
    ],
    "alignments": [], "conflicts": [], "change_log": []
  },
  "queries": [ { "query": "BERT 在哪些基准上被评估？", "subgraph": { "nodes": [], "edges": [] }, "evidence": [], "unanswered": [] } ],
  "evidence": [],
  "uncertainties": [],
  "notes": ["示例：正式运行以实际输入材料为准"]
}
```

## 九、适用范围与限制

- **适用范围**：科研论文正文文本；单篇或多篇；中英文材料；任务主题不限。
- **限制**：
  - 不处理纯图像像素、不读取补充附件/底层临床或实验数据、不推断其中数值。
  - 位置只认 JATS `paragraph_id`，无 PDF 页码，不编造页码。
  - 行内公式/上下标已线性化，短引含公式时需回 `*-publisher.xml` 核对，无法确认则标 `formula_lossy`。
  - 抽取质量受原文写法与 Agent 模型能力影响；弱证据/不确定项一律如实标注，不冒充确定事实。

## 十、维护

- 词表（6 类实体、8 类关系）如需扩展，必须同步更新 SKILL.md 的受控词表、本 README 的类型定义与关系约束，保持两边一致。
- 修改对齐规则时，同时更新"跨篇合并关键"与查询模板 3 的返回口径。
- 每次修改后自查：节点可回原文、边有证据、合并可解释、`result.json` 字段完整。
- 无脚本依赖、无个人文件依赖；本 Skill 可直接被他人或 Agent 复用。

## 十一、失败处理

| 异常 | 处置 |
|---|---|
| 文献缺失/无法访问 | `status="failed"` 或 `refused`，说明原因，不补造 |
| PDF 无法解析/无正文文本 | 只处理可读文本；缺失部分记入 `uncertainties` |
| 实体同名冲突 | 按跨篇合并关键判定；无法判定则分节点并写 `conflict_notes`，不误并 |
| 关系证据冲突 | 两条证据都保留并标 `[材料冲突]`，不替原文选边 |
| 查询无结果 | 返回空子图 + `unanswered` 说明，不臆造答案 |
| 字段缺失 | 标 `null` 或"未报告"，与 `uncertainties` 对应 |

预算铁律：**先落盘再完善**——第一版至少含实体/关系骨架 + 证据定位并写入 `result.json`（`status=partial`），再逐步补全。
