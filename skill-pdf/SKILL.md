---
name: scientific-pdf-to-ppt
description: 科研 PDF 解析并组织为可编辑学术 PPT。先按正确阅读顺序提取正文、章节、表格、公式与图表题注（逐块保留页码与坐标定位），再组织成可编辑 .pptx：每页一张幻灯片、页级证据映射、讲稿/备注、真实渲染预览。用于文献阅读、汇报、问答、知识提取。触发条件：任务要求解析科研 PDF，或把论文组织为学术汇报 PPT。
---

# 科研 PDF 解析 → 可编辑学术 PPT

把一份科研 PDF 解析成**可复核的结构化结果**，并进一步组织成**可编辑的学术 PPT**。两条产出都要求：每个结果能指回原文页码与区块。

## 一、四个质量关口（解析侧，必须逐项自查）

1. **提得全**：正文、图表题注、脚注、参考文献逐字提取；不漏行不丢段；页眉页脚单列不混正文。
2. **排得对**：双栏/多栏按"左栏读完再读右栏"输出；不串栏不错行；跨页段落按页序接续。
3. **拆得清**：章节层级、表格行列/单元格、公式上下标与希腊字母还原成可继续处理的结构。
4. **核得回**：每段文字、每张表格、每页 PPT 都带页码与坐标定位；读不出的部分如实标注，**绝不靠猜补齐**。

## 二、PPT 侧要求（本 Skill 的交付形态）

- **可编辑**：交付 `.pptx`（PowerPoint 可打开编辑的源码形态），不是 PDF/截图。
- **页级证据映射**：每张幻灯片在备注与 `manifest.json` 里写明来源页码/区块（`page=N bbox=[x0,y0,x1,y1]`）。
- **讲稿/备注**：每张幻灯片的 Speaker Notes 放入该页正文要点与证据定位。
- **真实渲染预览**：用 LibreOffice 渲染 PNG/PDF 预览，供检查版式；渲染结果如实记录，不冒充。

## 三、工作流（严格按此顺序）

### 第 1 步：识别输入与边界
- 从 `/input/case.json` 读任务要求（`task`、`output_contract`、材料路径）。
- 定位 PDF 文件（真实路径，不是文件名标签）；判断有文字层还是扫描版。

### 第 2 步：运行解析脚本（确定性基线）
```bash
python3 scripts/pdf_parse.py "<输入PDF绝对路径>" /app/work/parse.json
```
输出含 `pages[].reading_order`（多栏顺序文本块）、`pages[].sections`、`tables[]`、`scanned_pages[]`。
依赖自动降级：PyMuPDF → pdfplumber → `pdftotext`（poppler）。引擎写进 `notes`。

### 第 3 步：逐项质检（解析侧）
- **多栏顺序**：核对"左栏整栏 → 右栏整栏"；全宽块（标题/摘要）排在栏首。
- **表格**：`tables[]` 为空但原文有明显表格时，用 `python3 scripts/pdf_table.py "<PDF>" <页码>` 重试；跨页续表合并并在 evidence 写明。
- **公式/特殊字符**：失真的公式标注 `uncertain` 并给页码；保留原始字节。
- **扫描件**：`scanned_pages` 非空时调用 OCR（平台 `ocr-tool` 或 `tesseract`），OCR 结果放 `ocr_text` 并标注置信度，不冒充精确文本。

### 第 4 步：组织成可编辑学术 PPT
```bash
python3 scripts/ppt_build.py /app/work/parse.json /app/output/paper.pptx \
  --manifest /app/output/ppt_manifest.json \
  --render /app/output/ppt_preview
```
`ppt_build.py`（零第三方依赖）生成：标题页、摘要页、每章节一页、每表格一页、证据与边界页；每页带 Speaker Notes（正文要点 + 页级证据映射）；`ppt_manifest.json` 记录 slide→页码/区块；`--render` 用 LibreOffice 渲染预览 PNG。

若环境无 LibreOffice，`--render` 会跳过并提示，PPTX 仍可用。

### 第 5 步：写出 result.json
见下方输出契约。

## 四、输出契约（result.json 必填字段）

```json
{
  "case_id": "<来自输入>",
  "status": "success | partial | failed | refused",
  "doc": { "source": "<pdf路径>", "pages": 0, "engine": "pymupdf|pdfplumber|pdftotext|ocr" },
  "structure": [
    {
      "type": "title|author|abstract|section|subsection|paragraph|caption|table|formula|reference|footnote|header_footer",
      "text": "<提取文字，逐字一致>",
      "page": 3,
      "bbox": [x0, y0, x1, y1],
      "order": 0,
      "evidence": "<支撑此块的原文定位说明>",
      "uncertain": "<可选：无法确定/OCR存疑/公式失真>"
    }
  ],
  "tables": [ { "page": 5, "rows": [["...", "..."]], "evidence": "表2 · 第5页" } ],
  "ppt": {
    "pptx": "/app/output/paper.pptx",
    "manifest": "/app/output/ppt_manifest.json",
    "slides": 0,
    "previews": ["/app/output/ppt_preview/paper.png"],
    "notes_included": true
  },
  "uncertainties": [ { "page": 7, "what": "公式第(12)式下标无法还原", "how_to_verify": "查看第7页原图" } ],
  "notes": ["<引擎、OCR、降级、材料缺失、渲染结果等说明>"]
}
```

## 五、异常与边界处置

| 情况 | 处置 |
|---|---|
| 加密 PDF | 不强行解密；`status:"failed"`，notes 说明"需口令" |
| 扫描版（无文字层） | 走 OCR；结果标注 `"ocr": true` 与置信度 |
| 图片型表格 | `pdf_table.py` 或渲染后 OCR；失败则标注"表格为图片" |
| 乱码/缺字 | 保留原文并标注 `uncertain`，给可人工复核的页码 |
| 无 LibreOffice | PPTX 正常生成，`--render` 跳过并提示"预览未生成" |
| 无 Python PDF 引擎 | 自动降级到系统 `pdftotext`；仍无则 `failed` |

## 六、诚实性铁律
- 实际输入 PDF 与原文是**唯一事实依据**；不依据文件名/领域标签补造内容。
- 读不出、OCR 存疑、公式失真、渲染失败一律显式标注；**不猜测、不补全、不伪造**。
- 不编造正式案例答案、测试成绩或运行日志；脚本能确定与模型推断在 `notes` 分开说明。
