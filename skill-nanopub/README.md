# 科研断言抽取与证据绑定（Nanopublication）Skill — 使用说明

把科研论文的"结论段落"拆成**逐条可复核的断言**，并为每条断言绑定**最小充分证据片段 + 原文位置 + 来源元数据**，输出可被下游程序直接解析的结构化 JSON（可选附 JSON-LD / Nanopublication 惯用字段）。

> 本 README 是 `SKILL.md` 的配套文档：字段字典、受控词表、抽取规则、调用示例、适用范围、限制与维护。

---

## 1. 用途与适用条件

- **用途**：从科研论文（PDF/文本）中做"结论 → 断言 → 证据 → 来源"的知识结构化，用于 Nanopublication 生成、断言校验、证据绑定、来源检索、可追溯导出。
- **适用**：数字版（有文字层）科研论文 PDF 或已提取文本；含摘要/结论/讨论/结果段落的主张句。
- **不适用**：仅做全文版面解析（那是 PDF 解析类 Skill 的职责）；要求"理解并生成新科学结论"的开放式研究任务。本 Skill 只做**忠实抽取与绑定**，不生成新知识。

## 2. 文件结构

```
skill-nanopub/
├── SKILL.md   # 主指令：四关、工作流、输出契约、schema、粒度/证据/词表/去重/质检规则
└── README.md  # 本说明：字段字典、受控词表、抽取规则、调用示例、范围与维护
```

纯指令型，无脚本依赖。

## 3. 运行约定与安装

- **安装**：纯指令型，无脚本、无第三方依赖，**无需安装任何包**；运行环境由平台提供（`pdf-text-tool` / `pdf-render-tool` / `ocr-tool`）。
- 输入：`/input/case.json`（任务说明 + 材料路径）与 `task.md`；实际 PDF/材料是唯一事实依据。
- 工作目录 `/app/work`；最终结果写 `/app/output/result.json`（含输出契约全部字段与 `case_id`）。
- 预算：64 次模型请求、900 秒、单次响应 ≤16384 tokens；尽早保存 partial。

## 4. 四个质量关口

1. **拆得细**：一段结论拆成多条各自可判断真假的断言；一条断言 = 单一主体 + 单一受控关系 + 单一对象 + 完整限定。
2. **对得上**：每条断言绑定真正支撑它的最小逐字证据片段，并指出原文位置。
3. **追得回**：断言、证据、论文、作者、年份、版本链路完整，可回到原文。
4. **读得懂**：合法 JSON + 约定字段，下游程序无需清洗即可解析。

## 5. 字段字典

### 5.1 顶层 `result.json`

| 字段 | 类型 | 必填 | 含义 |
|---|---|---|---|
| `case_id` | string | 是 | 来自输入的案例标识 |
| `status` | string | 是 | `success / partial / failed / refused` |
| `output_kind` | string | 是 | 固定 `nanopub_assertions` |
| `schema_version` | string | 是 | 当前 `1.0` |
| `source` | object | 是 | 来源元数据（见 5.5） |
| `assertions` | array | 是 | 主结果：断言数组（见 5.2） |
| `evidence` | array | 是 | 证据定位汇总索引（见 5.4） |
| `quality_report` | object | 是 | 质量汇总（见 8） |
| `uncertainties` | array | 是 | 未报告/不确定项，空数组也须存在 |
| `notes` | array | 是 | 引擎/OCR/降级/范围/变更记录 |
| `nanopub` | object | 否 | 可选 JSON-LD / Nanopublication 惯用字段 |

### 5.2 断言对象 `assertions[]`

| 字段 | 类型 | 必填 | 含义 |
|---|---|---|---|
| `assertion_id` | string | 是 | 稳定 ID（`A001…`），去重不重排 |
| `assertion_text` | string | 是 | 单一、可验证、含限定的断言表述 |
| `polarity` | string | 是 | `positive / negative / neutral / mixed` |
| `modality` | string | 是 | `claim / finding / hypothesis / recommendation / attribution / definition` |
| `subject` | object | 是 | `{term, type, ref_id}` |
| `predicate` | string | 是 | 受控谓词（只能取第 6 节词表值） |
| `object` | object | 是 | `{term, type, ref_id}` |
| `conditions` | array | 是 | 适用条件（可空） |
| `qualifiers` | object | 是 | `scope/population/model_system/dose/temporal/magnitude/comparator/direction` |
| `evidence` | array | 是 | 证据对象数组（见 5.3）；无证据时 `sufficiency=insufficient` |
| `confidence` | object | 是 | `{level: high|medium|low, basis, uncertain, uncertainty_note}` |
| `quality` | object | 是 | 5 项检查旗标 + `passed_checks`（见 8） |
| `merged_from` | array | 否 | 合并时记录被合并的断言 ID |

**实体类型 `type`**（`subject.type` / `object.type`）：`drug | disease | gene | protein | method | dataset | metric | material | condition | population | concept | other`。

### 5.3 证据对象 `evidence[]`

| 字段 | 类型 | 必填 | 含义 |
|---|---|---|---|
| `evidence_id` | string | 是 | 稳定 ID（`E001…`） |
| `text` | string | 是 | 逐字引文（原文原样） |
| `location` | object | 是 | `{page, section, paragraph, figure_table_id, selector, bbox}` |
| `evidence_type` | string | 是 | `direct / indirect / computed / figure_table / cited` |
| `sufficiency` | string | 是 | `minimal_sufficient / sufficient / insufficient` |
| `verbatim` | bool | 是 | 是否逐字；改写时 `false` 并在 `note` 给原文 |
| `note` | string/null | 否 | 推理步骤、算式、OCR 说明等 |

### 5.4 证据定位汇总 `evidence[]`（顶层）

| 字段 | 含义 |
|---|---|
| `assertion_id` | 指向断言 |
| `evidence_id` | 指向证据 |
| `page / section / paragraph / figure_table_id / selector` | 可回到原文的定位 |

### 5.5 来源元数据 `source`

| 字段 | 含义 |
|---|---|
| `paper_id` | `doi:… / pmid:… / arxiv:… / internal:…` |
| `title / authors[] / year / venue / volume / issue / pages` | 题录 |
| `doi / pmid / pmcid / arxiv_id / url` | 标识符 |
| `version` | 版本号 |
| `id_type` | 主要标识符类型 |
| `source_file / source_hash` | 材料文件与 md5 |
| `metadata_verified` | 是否经核验 |
| `metadata_source` | `paper_header / crossref / doi_registry / unknown` |

## 6. 关系类型受控词表（`predicate` 只能取这些值）

| 类别 | 谓词 |
|---|---|
| 因果 | `causes`, `increases`, `decreases`, `modulates`, `mediates`, `inhibits`, `activates` |
| 相关（非因果） | `associated_with`, `correlates_with`, `predicts` |
| 比较 | `outperforms`, `comparable_to`, `worse_than`, `equivalent_to` |
| 证据/主张 | `supports`, `refutes`, `consistent_with`, `inconsistent_with` |
| 定义/分类 | `is_a`, `instance_of`, `part_of` |
| 属性/空间 | `has_property`, `located_in` |
| 方法 | `measured_by`, `evaluated_by`, `compared_with`, `uses`, `derived_from` |
| 定量 | `has_value` |

完整触发词与降级规则见 `SKILL.md` 第七节。核心降级原则：**原文只有相关/提示/可能，就不写因果与显著比较**；`associated_with` 是保守首选。

## 7. 抽取规则（执行摘要）

### 7.1 断言粒度判据
1. **单一可验证**：一条断言只一个主体+一个关系+一个对象。
2. **含限定范围**：人群/模型/剂量/条件/对照/时间/效应量必须保留。
3. **复合句并列**：`A and B improve Z` 拆两条；联合/交互不可分时保留为一条并注明"联合"。
4. **因果结构**：`Because M, D reduces R` 拆为"结果断言"+"机制断言"；不把相关升格为因果。
5. **否定保留**：`did not improve` → 保留谓词、`polarity=negative`，不删否定。
6. **归因拆分**：转述他人结论 → `modality=attribution`，不写成本文发现。

### 7.2 证据最小充分性
- 最小逐字引文（一至两句，非整段）；覆盖主体+关系+对象+关键数字/限定。
- `direct / indirect / computed / figure_table / cited` 五类；跨图表必须给 `figure_table_id`，不编数字。
- 缺任一要素 → `insufficient` + 降置信度 + 写 `uncertainties`；找不到引文不补造。

### 7.3 去重与合并
- 主体+关系+对象+限定归一化相同 → 合并证据、记 `merged_from`。
- 子集（更具体限定）保留；冲突（相反极性）双方保留并写 `conflicts`。
- ID 稳定不复排。

### 7.4 质量检查（5 项）
`too_broad`（断言过宽）、`insufficient_evidence`（证据不足）、`relation_error`（关系类型错误）、`subject_confusion`（主体混淆）、`missing_source`（来源缺失）——判定规则与处置见 `SKILL.md` 第十节。

## 8. 调用示例（示意，非正式案例结果）

输入：`/input/case.json` 指定材料 `paper.pdf`，任务为"抽取结论段落的可复核断言"。

Agent 按 `SKILL.md` 工作流执行后写 `/app/output/result.json`：

```json
{
  "case_id": "example-001",
  "status": "success",
  "output_kind": "nanopub_assertions",
  "schema_version": "1.0",
  "source": {
    "paper_id": "doi:10.xxxx/example",
    "title": "示例论文（示意）",
    "authors": [{"name": "示例作者", "affiliation": null}],
    "year": 2025,
    "venue": "示例期刊",
    "doi": "10.xxxx/example",
    "id_type": "doi",
    "source_file": "/input/paper.pdf",
    "source_hash": "md5:<示例>",
    "metadata_verified": true,
    "metadata_source": "paper_header"
  },
  "assertions": [
    {
      "assertion_id": "A001",
      "assertion_text": "示例药物在示例患者人群中使示例指标相对安慰剂显著下降（示意）",
      "polarity": "positive",
      "modality": "finding",
      "subject": {"term": "示例药物", "type": "drug", "ref_id": null},
      "predicate": "decreases",
      "object": {"term": "示例指标", "type": "metric", "ref_id": null},
      "conditions": ["示例患者人群", "相对安慰剂"],
      "qualifiers": {
        "scope": "示例研究",
        "population": "示例患者人群",
        "model_system": null,
        "dose": null,
        "temporal": null,
        "magnitude": null,
        "comparator": "安慰剂",
        "direction": "下降"
      },
      "evidence": [
        {
          "evidence_id": "E001",
          "text": "示例药物使示例指标相对安慰剂显著下降（示意，非真实引文）",
          "location": {"page": 3, "section": "Results", "paragraph": 2, "figure_table_id": null, "selector": "第3页第2段第2句", "bbox": [0,0,0,0]},
          "evidence_type": "direct",
          "sufficiency": "minimal_sufficient",
          "verbatim": true,
          "note": null
        }
      ],
      "confidence": {"level": "high", "basis": "逐字引文+可定位+来源完整", "uncertain": false, "uncertainty_note": null},
      "quality": {
        "too_broad": false,
        "insufficient_evidence": false,
        "relation_error": false,
        "subject_confusion": false,
        "missing_source": false,
        "passed_checks": ["atomicity", "verbatim", "location", "source", "predicate_mapping"]
      },
      "merged_from": []
    }
  ],
  "evidence": [
    {"assertion_id": "A001", "evidence_id": "E001", "page": 3, "section": "Results", "paragraph": 2, "figure_table_id": null, "selector": "第3页第2段第2句"}
  ],
  "quality_report": {
    "total_assertions": 1,
    "n_direct_evidence": 1,
    "n_indirect_evidence": 0,
    "n_insufficient_evidence": 0,
    "n_merged": 0,
    "n_flagged": 0,
    "conflicts": [],
    "checks": {"too_broad": 0, "insufficient_evidence": 0, "relation_error": 0, "subject_confusion": 0, "missing_source": 0}
  },
  "uncertainties": [],
  "notes": ["示例输出，非正式案例结果"]
}
```

> 上面内容全部是**示意**，用于说明接口与流程，不冒充正式案例结果；真实运行时 `assertion_text` 与 `evidence.text` 必须来自实际材料且逐字一致。

## 9. 适用范围

- 适合：期刊/会议/预印本论文中"摘要、结论、讨论结论句、结果段主张句"的断言化抽取与证据绑定。
- 可扩展：替换/追加受控词表即可适配特定领域（如临床试验、组学、材料）。
- 边界：本 Skill 不负责版面解析（交给 PDF 解析类 Skill）、不做新科学推断、不替代人工对"统计显著性"的最终判读。

## 10. 限制与维护

- **限制**：扫描件依赖 OCR 质量；复杂图表数字需人工核；代词指代与被动语态可能造成主体不明（按规则标 `subject_confusion`）；统计显著性/因果强度只能按原文措辞保守映射。
- **维护**：更新受控词表或字段时，同步 `SKILL.md` 与本节字典，并递增 `schema_version`；`nanopub_id` 生成规则保持确定性以便重复运行比对。
- **诚实性**：读不出、无法判断、材料冲突显式标注；禁止猜测/补造/伪造（含引文、页码、DOI、作者、年份、数字）。

## 11. 自查清单（提交前）

- [ ] `SKILL.md` 含合法 YAML frontmatter（`name`/`description`）。
- [ ] 覆盖：目标与四关 → 分步工作流 → 输出契约 → 异常与边界 → 诚实性铁律。
- [ ] 输出契约含 `case_id`、`status`、主结果、`evidence`、`uncertainties`、`notes`。
- [ ] 断言 schema 含：ID/文本/主体/关系/对象/条件限定/证据片段/证据位置/来源元数据/置信度依据。
- [ ] 给出断言粒度判据、证据最小充分性判据、关系受控词表、去重合并规则。
- [ ] 5 项质量检查写成可执行判定（过宽/不足/关系错/主体混淆/来源缺）。
- [ ] 输出为合法 JSON（可加 JSON-LD/Nanopublication 惯用字段）。

## 12. 失败处理

| 异常 | 处置 |
|---|---|
| 扫描版无文本层 | 走 OCR，标注置信度；OCR 不确定处列入 `uncertainties`，不冒充精确原文 |
| 原文无法访问 | `status="failed"` 或 `refused`，说明原因，不补造 |
| 证据跨图表 | 证据定位指向图表编号与页码，标注"证据在图中，需人工核对数值" |
| 断言找不到支撑片段 | 该断言标 `unsupported`，或降级为 `uncertain`，不强行绑定 |
| 断言与证据冲突 | 两处都保留并标 `[材料冲突]`，不替原文选边 |
| 字段缺失 | 缺失字段标 `null` 或"未报告"，与 `uncertainties` 对应 |

预算铁律：**先落盘再完善**——第一版至少含拆分出的断言 + 证据定位骨架并写入 `result.json`（`status=partial`），再逐步补全。
