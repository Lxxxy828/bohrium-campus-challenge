---
name: nanopub-assertion-extractor
description: 科研论文断言抽取与证据绑定（Nanopublication）。把论文结论段落拆成一条条单一、可验证的科研断言，逐条绑定最小充分证据片段与原文位置，记录论文/作者/年份/版本来源元数据，运行质量检查与去重，输出可被下游程序直接解析的结构化 JSON（含 JSON-LD/Nanopublication 惯用字段）。触发条件：任务要求从科研论文提取、拆分、校验结论或断言，或生成 Nanopublication、绑定证据、做可追溯结构化导出。
---

# 科研断言抽取与证据绑定（Nanopublication）

把论文中的"一段结论"变成**逐条可复核的结构化断言**：每条断言有单一主体、受控关系、对象、条件限定，绑定一条能指回原文的最小证据片段，并带完整来源元数据。输出不是"把摘要整段塞进一个字段"，而是可被机器直接消费的 JSON。

本 Skill 聚焦一个完整闭环子场景：**结论段落 → 断言拆解 → 证据绑定 → 来源回溯 → 质量检查 → 结构化导出**。

---

## 一、目标与四个质量关口（逐项自查）

### 目标
给定科研材料（PDF/文本）与任务说明，产出结构化的"断言—证据—来源"三元知识单元，使第三方能**逐条回到原文**确认：断言忠实、证据充分、关系方向正确、来源真实、结构可解析。

### 四个质量关口
1. **拆得细**：一段结论拆成若干条**各自可判断真假**的断言；不把整段话塞进一个字段。每条断言 = 单一主体 + 单一受控关系 + 单一对象 + 完整限定。
2. **对得上**：每条断言找到**真正支撑它的最小证据片段**（逐字引文），并指出片段原文位置（页码/段落/图表/字段）。
3. **追得回**：断言、证据、论文、作者、年份、版本之间的链路完整；第三方据此能回到原文核对。
4. **读得懂**：导出结构符合约定的字段与序列化形态（合法 JSON，可加 JSON-LD/Nanopublication 惯用字段），下游程序无需人工清洗即可解析。

任何一关未通过，都必须落到 `uncertainties` 或 `notes`，不得用"看起来合理"掩盖。

---

## 二、分步工作流（严格按此顺序执行）

> 运行时路径：输入 `/input/case.json` 与 `task.md`；工作目录 `/app/work`；最终结果写 `/app/output/result.json`。
> 预算：64 次模型请求、900 秒、单次响应 ≤16384 tokens。**尽早保存 partial，再增量改进。**

### 第 0 步：读输入，划边界
- 读 `/input/case.json`：取 `case_id`、`task`、`output_contract`、材料真实路径（不是文件名标签）。
- 读 `task.md`：确认任务要求是"全文全部断言"还是"指定段落/指定结论"；确认评分需要的证据范围。
- 明确本次要抽取的**目标段落范围**（摘要、结论、讨论的结论句、结果段中含主张的句子）。没有明确范围时，默认覆盖"摘要 + 结论 + 讨论中带明确主张的句子"，并在 `notes` 说明取舍。

### 第 1 步：建立来源元数据
- 从材料首页/题录/元数据提取：标题、作者、年份、期刊/会议、卷期页码、DOI、PMID/PMCID、arXiv ID、URL、版本号。
- 只记录**可核验**字段；无法确认的写 `null` 或 `"unknown"`，绝不编造。
- 若网络可用且任务允许，可用 DOI/arXiv ID 做一次交叉核验；核验失败或不可达，保持原文值并标 `metadata_verified: false`。
- 计算材料文件哈希（`md5`），写进 `source.source_hash`，保证重复运行可对齐同一版本。

### 第 2 步：定位与切分段落
- 按页码/段落把目标范围切成"候选段"，每条候选段带：页码、段落号、章节名（Introduction/Results/Discussion/Conclusion…）。
- 对双栏 PDF：按"左栏整栏→右栏整栏"顺序读，避免串栏拼错句。
- 扫描版（无文字层）走 OCR；OCR 结果标 `ocr: true` 与置信度，不冒充精确文本。

### 第 3 步：拆断言（按"五、断言粒度判据"）
对每条候选段逐句执行：
1. 判断该句是否含**可判断真假的主张**（有主语+谓语+宾语/补语，且是事实/发现/假设/归因，而非纯过渡句）。
2. 复合句并列 → 拆；因果 → 拆机制与结果；否定保留极性；归因他人结论单独成条并标 `modality=attribution`。
3. 每条断言写出 `assertion_text`（含全部限定，一句话）。

### 第 4 步：关系映射（按"七、关系类型受控词表"）
- 把每句主干动词映射到受控谓词；确定 `subject` 与 `object` 及其实体类型；判断方向（主动/被动/比较基准）。
- 原文只有相关/提示/可能时，**保守降级**（`causes`→`associated_with`；`outperforms`→`associated_with` 或保留但降置信度）；不夸大因果与显著性。

### 第 5 步：绑定证据（按"六、证据最小充分性判据"）
- 为每条断言找**最小逐字引文**（覆盖主体+关系+对象+关键数字/限定），并记录位置（页码/段落/章节/图表 ID/选择器）。
- 判定 `evidence_type`（direct/indirect/computed/figure_table/cited）与 `sufficiency`（minimal_sufficient/sufficient/insufficient）。
- 找不到支撑片段：`sufficiency=insufficient`、`confidence.level=low`，并写 `uncertainties`；**不删除断言、不补造引文**。

### 第 6 步：质量检查（按"十、质量检查"）
对每条断言跑 5 项判定（断言过宽 / 证据不足 / 关系错误 / 主体混淆 / 来源缺失），能修就修，修不了标 `quality` 旗标并记 `uncertainties`。

### 第 7 步：去重与合并（按"九、去重与合并规则"）
按"身份相同合并 / 子集保留 / 冲突保留双方"处理，记录 `merged_from`，ID 保持稳定不复排。

### 第 8 步：写 result.json
- 写 `/app/output/result.json`（见"三、输出契约"），含全部必填字段与 `case_id`。
- 生成后用 JSON 解析器自查一次（禁尾逗号、禁注释、禁 NaN）。
- 任务要求 Nanopublication 惯用字段时，额外附带 `nanopub` 对象（见"十三"）。

### 第 9 步：四关自查 + 交付
- 逐条过四关：拆得细（每条单主体单关系）、对得上（证据逐字+可定位）、追得回（来源链路完整）、读得懂（合法 JSON 可解析）。
- 未通过项写进 `uncertainties`；在 `notes` 说明引擎、OCR/降级、重复运行一致性、本次未覆盖范围。**不补造、不猜测。**

---

## 三、输出契约（result.json 必填字段）

顶层结构（主结果字段为 `assertions`；`evidence` 为证据定位汇总索引；`uncertainties`/`notes` 必填）：

```json
{
  "case_id": "<来自输入>",
  "status": "success | partial | failed | refused",
  "output_kind": "nanopub_assertions",
  "schema_version": "1.0",
  "source": { "<见第八节：来源元数据字段>": null },
  "assertions": [ { "<见第四节：断言字段>": null } ],
  "evidence": [
    { "assertion_id": "A001", "evidence_id": "E001",
      "page": 3, "section": "Results", "paragraph": 2,
      "figure_table_id": null, "selector": "第3页第2段第2句" }
  ],
  "quality_report": { "<见第十节：质量汇总字段>": null },
  "uncertainties": [
    { "what": "…", "why": "…", "how_to_verify": "…" }
  ],
  "notes": [ "…" ]
}
```

**字段要求**：
- `status`：全部目标段落完成且关键断言均有证据 → `success`；部分读不出/部分断言无支撑但已如实标注 → `partial`；材料缺失/加密/无法解析 → `failed`；因内容不可判或涉及不应答范围而拒答 → `refused`，并在 `notes` 写明原因。
- `evidence` 顶层索引必须能回到原文页码/段落/字段；每条断言内部的 `evidence[]` 是权威细节，顶层索引是便于下游检索的汇总。
- `uncertainties` 用于"未报告、无法判断、OCR 存疑、跨图表、材料冲突"；**禁止把不确定写成事实**。
- `notes` 记录引擎、OCR/降级、去重合并、版本、重复运行一致性、范围取舍与变更记录。

---

## 四、断言字段 schema（核心结构）

```json
{
  "assertion_id": "A001",
  "assertion_text": "一句话断言，含全部限定与数值",
  "polarity": "positive | negative | neutral | mixed",
  "modality": "claim | finding | hypothesis | recommendation | attribution | definition",
  "subject": {
    "term": "<主体术语>",
    "type": "drug|disease|gene|protein|method|dataset|metric|material|condition|population|concept|other",
    "ref_id": null
  },
  "predicate": "<受控谓词，见第七节，必须来自词表>",
  "object": {
    "term": "<对象术语>",
    "type": "drug|disease|gene|protein|method|dataset|metric|material|condition|population|concept|other",
    "ref_id": null
  },
  "conditions": [ "<适用条件列表，可为空数组>" ],
  "qualifiers": {
    "scope": "<研究范围/上下文>",
    "population": "<人群/样本>",
    "model_system": "<细胞系/动物模型/数据集>",
    "dose": "<剂量或强度，无则 null>",
    "temporal": "<时间/随访/时间窗，无则 null>",
    "magnitude": "<效应量/数值/方向，无则 null>",
    "comparator": "<对照/基线，无则 null>",
    "direction": "<提升/降低/无差异/反向等方向说明>"
  },
  "evidence": [ { "<见第六节：证据字段>": null } ],
  "confidence": {
    "level": "high | medium | low",
    "basis": "<依据：逐字引文+可定位+来源完整；或间接推断步骤>",
    "uncertain": false,
    "uncertainty_note": null
  },
  "quality": {
    "too_broad": false,
    "insufficient_evidence": false,
    "relation_error": false,
    "subject_confusion": false,
    "missing_source": false,
    "passed_checks": [ "atomicity", "verbatim", "location", "source", "predicate_mapping" ]
  },
  "merged_from": []
}
```

**字段字典（简版，完整版见 README.md）**：

| 字段 | 必填 | 含义 |
|---|---|---|
| `assertion_id` | 是 | 稳定 ID，按出现顺序 `A001…`；去重不重排 |
| `assertion_text` | 是 | 单一、可验证、含限定的断言原文表述 |
| `polarity` | 是 | 断言极性（肯定/否定/中性/混合） |
| `modality` | 是 | 断言语态：本文事实、发现、假设、建议、归因他人、定义 |
| `subject/object` | 是 | 主体/对象术语与实体类型；`ref_id` 可指向同文其它实体，无则 null |
| `predicate` | 是 | 受控谓词，**只能取第七节词表值** |
| `conditions` | 是 | 适用条件数组（可空） |
| `qualifiers` | 是 | 结构化限定（范围/人群/模型/剂量/时间/效应量/对照/方向） |
| `evidence[]` | 是 | 至少一条证据（无则 `sufficiency=insufficient` 并降置信度） |
| `confidence` | 是 | 置信水平与依据 |
| `quality` | 是 | 5 项质量检查旗标与已通过检查 |
| `merged_from` | 否 | 去重合并时记录被合并的断言 ID |

---

## 五、断言粒度判据（拆得细）

**判据 1：单一可验证。** 一条断言只含一个 `subject` + 一个 `predicate` + 一个 `object`；去掉它，其余断言仍可独立判断真假。若一句话断言两件互不依赖的事，拆成两条。

**判据 2：含限定范围。** 断言必须携带原文的限定（人群/模型/剂量/条件/对照/时间/效应量）。原文若为普遍陈述（"X is a Y"）才允许无 `conditions`；否则缺失限定按"断言过宽"处理。

**判据 3：复合句并列拆分。** "A and B improve Z" → 拆为 "A improves Z" 与 "B improves Z"，共享限定分别写进两条。**例外**：并列双方构成不可分整体或交互（"A and B jointly/together improve Z"）→ 保留为一条，`subject.term = "A and B (联合)"`，并在 `conditions` 注明"联合作用"。

**判据 4：因果结构拆分。** "Because M, D reduces R" → 拆为：(1) 结果断言 "D reduces R"；(2) 机制断言 "M is the mechanism / mediates D's effect on R"。只有原文明确表述因果（caused/led to/induced/resulted in/通过…导致）才用因果谓词；仅相关/伴随/提示（associated with/correlated/suggest）用相关谓词，**不把相关升格为因果**。

**判据 5：否定保留。** "X did not improve Y" → 保留 `predicate=increases`（或词表对应项）且 `polarity=negative`，`qualifiers.direction="未提升"`；不得静默删除否定变成肯定。

**判据 6：归因/引用拆分。** 句子转述他人结论时（"Smith et al. reported that…"），单独成条，`modality=attribution`，`subject` 指向被引主张/作者，并在 `conditions` 或证据中标注被引工作；不把第三方结论写成本文自己的发现。

---

## 六、证据最小充分性判据（对得上）

**证据对象 schema：**

```json
{
  "evidence_id": "E001",
  "text": "<逐字引文，原文原样>",
  "location": {
    "page": 3,
    "section": "Results",
    "paragraph": 2,
    "figure_table_id": null,
    "selector": "第3页第2段第2句",
    "bbox": [ 0, 0, 0, 0 ]
  },
  "evidence_type": "direct | indirect | computed | figure_table | cited",
  "sufficiency": "minimal_sufficient | sufficient | insufficient",
  "verbatim": true,
  "note": null
}
```

**最小充分性判定（可执行）**：
1. **最小**：引文是能独立支撑该断言的最短逐字片段（通常一至两句），不是整段；若一段支撑多条断言，按句分别引。
2. **充分**：引文覆盖 `subject`（或其明确指代）+ `predicate`（或其同义表达）+ `object` + 关键数值/限定；缺任一项 → `insufficient`。
3. **直接 vs 间接**：
   - `direct`：原文句子即陈述该断言。
   - `indirect`：需要结合同段两处/上下文才能得出；在 `note` 写明推理步骤。
   - `computed`：由表中数字计算（如变化率）；在 `note` 写明算式与原始数字位置。
   - `figure_table`：证据在表/图中；`location.figure_table_id` 必填，`text` 用题注或单元格原文，不编造未见数字。
   - `cited`：证据是被引文献的主张；标 `modality=attribution`，来源元数据指向被引工作。
4. **定位可回**：必须有 `page` + `section` + `paragraph`（或 `figure_table_id`）+ `selector`；`bbox` 可选，工具能给出坐标时填写。
5. **逐字**：`text` 必须原文原样；确需改写时 `verbatim=false` 且 `note` 给出原文对应句。
6. **找不到支撑片段**：`sufficiency=insufficient`、`confidence.level=low`，写 `uncertainties`；**绝不编造引文或页码**。

---

## 七、关系类型受控词表（映射规则）

每条断言的 `predicate` 必须来自下表（schema_version 1.0）。无法确定时按"保守降级"处理，并在 `note` 说明。

| 类别 | 谓词（canonical） | 语义 | 典型原文触发词 | 反向/补充 | 降级规则 |
|---|---|---|---|---|---|
| 因果 | `causes` | 导致/引起（原文明确因果） | caused, led to, induced, resulted in, drives | `caused_by` | 仅相关/提示 → `associated_with` |
| 因果 | `increases` | 提高某量 | increased, raised, elevated, upregulated | `decreased_by` | 无因果措辞 → `associated_with` |
| 因果 | `decreases` | 降低某量 | decreased, reduced, lowered, downregulated | `increased_by` | 无因果措辞 → `associated_with` |
| 因果 | `modulates` | 调节（方向不明或双向） | modulates, regulates, affects | `modulated_by` | — |
| 因果 | `mediates` | 中介作用 | mediates, acts through, via | `mediated_by` | 仅相关 → `associated_with` |
| 因果 | `inhibits` | 抑制 | inhibits, blocks, suppresses | `inhibited_by` | — |
| 因果 | `activates` | 激活 | activates, stimulates, triggers | `activated_by` | — |
| 相关 | `associated_with` | 统计相关/伴随，未声称因果（**保守首选**） | associated with, linked to, related to | `associated_with` | — |
| 相关 | `correlates_with` | 给出相关系数/相关 | correlated (r=…), correlation | `correlates_with` | 无系数仍可归 `associated_with` |
| 相关 | `predicts` | 作为预测/风险因子 | predicted, predictive of, associated with higher risk | `predicted_by` | 非前瞻 → `associated_with` |
| 比较 | `outperforms` | 显著优于 | outperformed, superior to, better than, significantly higher vs | `outperformed_by` | 无显著性证据 → `associated_with` 或降置信 |
| 比较 | `comparable_to` | 无显著差异 | no significant difference, comparable, similar to | `comparable_to` | — |
| 比较 | `worse_than` | 更差 | worse than, inferior to, lower than | `better_than` | 无显著性证据 → `associated_with` |
| 比较 | `equivalent_to` | 等效/非劣 | non-inferior, equivalent | `equivalent_to` | 统计口径不明 → 降置信 |
| 证据 | `supports` | 证据支持结论 | supports, demonstrates, shows, confirms | `supported_by` | 弱支持 → `consistent_with` |
| 证据 | `refutes` | 证据反驳 | refutes, contradicts, challenges, fails to support | `refuted_by` | 不一致但不构成反驳 → `inconsistent_with` |
| 证据 | `consistent_with` | 与…一致 | consistent with, in line with, agrees with | `consistent_with` | — |
| 证据 | `inconsistent_with` | 与…不一致 | inconsistent with, differs from | `inconsistent_with` | 明确推翻 → `refutes` |
| 定义 | `is_a` | A 是 B 的一种 | is a, belongs to, is a type of | `has_subtype` | — |
| 定义 | `instance_of` | A 是 B 的实例 | is an instance of | `has_instance` | — |
| 构成 | `part_of` | 部分-整体 | part of, component of, contained in | `has_part` | — |
| 属性 | `has_property` | 具有性质/特征 | has, exhibits, is characterized by | `property_of` | — |
| 空间 | `located_in` | 位于/表达于 | located in, expressed in, found in | `contains` | — |
| 方法 | `measured_by` | 以…方法测量 | measured by, assessed by, quantified by | `measures` | — |
| 方法 | `evaluated_by` | 以…评估 | evaluated by, tested by | `evaluates` | — |
| 方法 | `compared_with` | 与…对照 | compared with, versus, vs | `compared_with` | — |
| 方法 | `uses` | 使用工具/数据 | used, employed, applied | `used_by` | — |
| 方法 | `derived_from` | 来源于 | derived from, obtained from, based on | `source_of` | — |
| 定量 | `has_value` | 数值为 | was, equal to, amounted to | `value_of` | 数值不完整 → `insufficient` |

**映射规则**：
- 方向必须核对：被动句/比较句先还原主动方向，再定 `subject/predicate/object`；方向反了即 `subject_confusion`。
- 语境含 `may/suggest/possibly/associated` 等弱化词时，把强因果/强比较**降级**到 `associated_with`，并在 `confidence.basis` 说明降级理由。
- `improves [某指标]` → 映射 `increases`（`qualifiers.direction="改善"`）；`improves [胜过某方案]` → 映射 `outperforms`。

---

## 八、来源元数据（追得回）

```json
{
  "paper_id": "<doi:...|pmid:...|arxiv:...|internal:...>",
  "title": "<论文标题>",
  "authors": [ { "name": "<作者名>", "affiliation": "<机构，无则 null>" } ],
  "year": 2023,
  "venue": "<期刊/会议>",
  "volume": null,
  "issue": null,
  "pages": null,
  "doi": null,
  "pmid": null,
  "pmcid": null,
  "arxiv_id": null,
  "url": null,
  "version": "<版本，如 v1/v2 或无>",
  "id_type": "doi | pmid | arxiv | url | internal",
  "source_file": "/input/paper.pdf",
  "source_hash": "md5:<hex>",
  "metadata_verified": true,
  "metadata_source": "paper_header | crossref | doi_registry | unknown"
}
```

**规则**：
- `paper_id` 首选 `doi:`，其次 `pmid:`、`arxiv:`，都没有则用 `internal:` + 文件名哈希。
- 元数据仅记录可核验值；不可知写 `null` 或 `"unknown"`，**不编 DOI/作者/年份/版本**。
- 若同一材料有多版本，逐条断言绑定其真实 `paper_id`/`version`，避免来源混淆。
- 归因断言（`modality=attribution`）的来源元数据指向被引工作，并在 `evidence.note` 标注"转述自本文第 X 处"。

---

## 九、去重与合并规则

1. **身份相同**：`subject.term`+`predicate`+`object.term`+`conditions`+关键 `qualifiers` 归一化后完全相同 → 保留证据更充分（`sufficiency` 更高/`verbatim=true`）的一条，合并双方 `evidence`，记录 `merged_from`。
2. **子集保留**：若断言 B 比 A 只多限定（更具体），两者是不同粒度，**都保留**；除非 A 无新增信息且完全被 B 覆盖，才合并 A 入 B。
3. **冲突保留双方**：同一主体-对象但极性相反 → 两条都保留，写入 `quality_report.conflicts`，`notes` 说明冲突；**不静默丢弃**。
4. **ID 稳定**：按首次出现顺序分配 `A001…`、`E001…`；去重后 ID 不复排，空号保留并在 `notes` 说明。

---

## 十、质量检查（可执行判定）

对每条断言执行 5 项，能修则修；修不了标旗标并记 `uncertainties`。

| 检查项 | 判定规则（可复现） | 触发后处置 |
|---|---|---|
| `too_broad`（断言过宽） | 证据中含限定（人群/模型/剂量/对照/时间），但断言缺失该限定；或断言把"在 X 中"写成普遍结论 | 把限定补进 `conditions`/`qualifiers`；无法确定范围则降 `confidence` 并标旗 |
| `insufficient_evidence`（证据不足） | 无逐字引文；或引文缺主体/对象/关键数字/限定之一 | `sufficiency=insufficient`、`confidence.level=low`，写 `uncertainties`，不补造 |
| `relation_error`（关系类型错误） | 谓词强于原文（相关→因果、无显著性→显著优于）；或类别错配 | 按第七节降级到保守谓词；仍不确定则标旗 |
| `subject_confusion`（主体混淆） | 主被动还原后方向反了；或把对照/处理、A/B 组写反 | 依据原文语法重新定 `subject/object`；无法确定则标旗 + `uncertainty` |
| `missing_source`（来源缺失） | 缺 `source_file`/`page`/`section`，或来源元数据关键项（标题/DOI/作者）缺失且不可核验 | 能补则补；不能则 `metadata_verified=false`、标旗、写 `uncertainties` |

汇总进 `quality_report`：

```json
{
  "total_assertions": 12,
  "n_direct_evidence": 9,
  "n_indirect_evidence": 3,
  "n_insufficient_evidence": 1,
  "n_merged": 2,
  "n_flagged": 1,
  "conflicts": [ { "a": "A001", "b": "A002", "kind": "opposite_polarity" } ],
  "checks": { "too_broad": 0, "insufficient_evidence": 1, "relation_error": 0, "subject_confusion": 0, "missing_source": 0 }
}
```

---

## 十一、异常与边界处置

| 情况 | 处置 |
|---|---|
| 扫描版无文本层 | 走 OCR；结果标 `ocr: true` 与置信度，不冒充精确文本；无法 OCR 则 `partial`，证据定位到页+图 |
| 材料加密/无法访问/路径无效 | `status:"failed"`，`notes` 写清原因与可人工接管位置 |
| 断言找不到支撑片段 | `sufficiency=insufficient`、`confidence.level=low`、写 `uncertainties`；不删除断言、不编造引文 |
| 证据在图表中（数字不在正文） | `evidence_type=figure_table`，`location.figure_table_id` 必填，`text` 用题注/单元格原文，不编数字 |
| 证据跨页/跨段 | `location` 记起止（如 `page: 3, paragraph: 2` + `note:"跨页续至第4页"`），`indirect` 类型说明结合方式 |
| 断言与证据冲突 | 保留双方，写 `quality_report.conflicts` 与 `notes`，不静默删除 |
| 代词指代/被动语态导致主体不明 | 从上下文解析指代；仍不确定 → `subject_confusion` 旗标 + `uncertainty` |
| 关系强度不确定（may/suggest/associated） | 保守谓词 + `confidence` 降级，说明降级理由 |
| 来源元数据缺失 | `metadata_verified=false`，标 `missing_source`；只补可核验字段，不猜 |
| 多篇论文/多版本材料 | 每条断言绑定真实 `paper_id`/`version`，避免来源混淆 |
| 输出 JSON 非法 | 只用合法 JSON（禁尾逗号/注释/NaN）；写出前用解析器自查一次 |
| 任务范围不明确 | 默认"摘要+结论+讨论明确主张句"，并在 `notes` 说明取舍，标 `partial` |

---

## 十二、诚实性铁律

- 实际输入文件与原论文是**唯一事实依据**；不依据文件名/领域标签补造内容。
- 读不出、无法判断、材料冲突，一律显式标注；**禁止猜测、补造、伪造**（含 DOI、作者、年份、数字、页码、引文）。
- 证据必须逐字；改写必须 `verbatim=false` 并给出原文。
- 不确定不写成事实：`confidence.uncertain=true` 时，`uncertainties` 必有对应说明。
- 脚本/模型能确定的部分与推断部分在 `notes` 中分开说明。

---

## 十三、JSON-LD / Nanopublication 惯用导出（可选）

任务要求 Nanopublication 惯用字段时，在 `result.json` 顶层追加 `nanopub` 对象，与扁平 `assertions` 并存（`assertions` 仍是主结果、保持可直接解析）：

```json
{
  "nanopub": {
    "@context": {
      "np": "http://www.nanopub.org/nschema#",
      "sio": "http://semanticscience.org/resource/",
      "prov": "http://www.w3.org/ns/prov#",
      "dct": "http://purl.org/dc/terms/"
    },
    "nanopub_id": "urn:uuid:<由 case_id+时间戳确定性生成，示例仅示意>",
    "publication_info": { "created": "<ISO时间>", "creator": "<本 Skill 运行者>", "license": "CC-BY-4.0" },
    "assertion_graph": [
      { "subject": "<subject.term>", "predicate": "<受控谓词>", "object": "<object.term>", "assertion_id": "A001" }
    ],
    "provenance_graph": [
      { "assertion_id": "A001", "was_derived_from": "<source.paper_id>", "location": "第3页第2段第2句", "evidence_text": "<逐字引文>" }
    ]
  }
}
```

`nanopub_id` 需确定性生成（如 `urn:uuid:` + 对 `case_id` 的哈希），重复运行保持一致；示意输出必须标注"示例，非正式案例结果"。
