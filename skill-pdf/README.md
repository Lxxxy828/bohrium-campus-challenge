# 科研 PDF 解析 → 可编辑学术 PPT Skill

把科研 PDF 解析成**可复核的结构化结果**，并组织成**可编辑的学术 PPT**（含页级证据映射、讲稿/备注、真实渲染预览）。

## 用途与适用条件

- **用途**：文献阅读/翻译/问答/知识提取的前置解析；把论文做成可编辑的学术汇报 PPT。
- **适用**：数字版（有文字层）与扫描版（无文字层，走 OCR）科研论文 PDF。
- **不适用**：要求"理解科学含义"的语义摘要（本 Skill 只做结构提取与结构化组织）。

## 文件结构

```
skill-pdf/
├── SKILL.md               # 主指令：四关 + PPT 侧要求 + 工作流 + 输出契约 + 异常处置
├── README.md              # 本说明（版本/来源/输入输出/自查/示例）
└── scripts/
    ├── pdf_parse.py       # 主解析器：阅读顺序 + 章节 + 表格 + 扫描检测
    ├── pdf_table.py       # 专用表格提取器
    └── ppt_build.py       # 组织为可编辑 .pptx：幻灯片 + 备注 + 证据映射 + 渲染预览
```

## 脚本版本与来源

| 文件 | 版本 | 来源 / 依赖 |
|---|---|---|
| `pdf_parse.py` | v1 | 本 Skill 实现；引擎按 PyMuPDF → pdfplumber → `pdftotext`（poppler）自动降级 |
| `pdf_table.py` | v1 | 本 Skill 实现；引擎 pdfplumber → PyMuPDF |
| `ppt_build.py` | v1 | 本 Skill 实现；**纯 Python 标准库**（`zipfile` + OOXML），零第三方依赖 |

渲染预览依赖系统 LibreOffice（`soffice`）；无则跳过预览，PPTX 仍可用。

## 依赖与安装

```bash
pip install pymupdf        # 可选，首选引擎
pip install pdfplumber     # 可选，备用引擎
# 均未安装时自动降级到系统 pdftotext（poppler-utils）
```

## 输入与输出

**输入**
- 论文 PDF 文件（真实路径，或 `/input/case.json` 指定的材料路径）。
- 可选：主线大纲 JSON（`ppt_build.py --outline` 模式）。

**输出**
- `parse.json`：结构化解析结果（`pages[].reading_order`、`sections`、`tables[]`、`scanned_pages[]`）。
- `paper.pptx`：可编辑演示文件（每页幻灯片 + Speaker Notes）。
- `ppt_manifest.json`：slide → 来源页码/区块的证据映射。
- 预览 PNG/PDF（LibreOffice 渲染，若可用）。

## 调用示例（示意，非正式案例结果）

```bash
# 1) 解析 PDF
python3 scripts/pdf_parse.py paper.pdf parse.json

# 2) 组织为可编辑学术 PPT（含备注 + 证据映射 + 渲染预览）
python3 scripts/ppt_build.py parse.json paper.pptx \
  --manifest ppt_manifest.json --render preview_dir
```

示意输出（非正式案例）：

```json
{"status": "success", "slides": 6, "pptx": "paper.pptx",
 "evidence_map": [{"slide": 2, "title": "1. Introduction", "evidence": ["page=1 bbox=[40,45,129,64]"]}]}
```

## 自查方法（提交前逐项检查）

1. **阅读顺序**：双栏/多栏是否"左栏整栏读完再读右栏"，全宽块（标题/摘要）是否排栏首。
2. **表格**：行列/合并单元格是否还原；跨页续表是否合并并在 evidence 写明。
3. **公式/特殊字符**：上下标、希腊字母是否失真；失真处是否标 `uncertain` 并给页码。
4. **扫描件**：无文字层页面是否走 OCR 并标注置信度（不冒充精确文本）。
5. **证据映射**：每页 PPT 是否带 `page=N` / 图/表定位，可回溯原文。
6. **PPT 有效性**：能否用 LibreOffice 打开并渲染（可打开 = 合法）。
7. **诚实性**：读不出/不确定/失败是否显式标注，是否未补造数据。

## 质量口径

- **解析四关**：提得全 / 排得对 / 拆得清 / 核得回。
- **PPT 四要求**：可编辑 .pptx / 页级证据映射 / 讲稿备注 / 真实渲染预览。

## 限制与维护

- 复杂跨栏跨页表格、扫描件低分辨率、特殊字体映射仍可能失败；失败处按 SKILL.md 的 `uncertainties` 如实标注。
- `ppt_build.py` 生成的是"结构性"幻灯片（章节/正文/表格/证据），非语义摘要。
- 维护：更新脚本时同步本 README 的依赖与版本说明；脚本不依赖作者个人文件。
