#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ppt_build.py —— 把解析结果组织成"可编辑学术 PPT"（零第三方依赖，纯标准库）。

从 pdf_parse.py 的解析 JSON 生成一个合法 .pptx：
  - 标题页（论文标题/来源）
  - 摘要页
  - 每个章节一页（按原文结构，非语义摘要）
  - 每个表格一页（结构化文本）
  - 参考文献/脚注页
  - 每页带"讲稿/备注"（Speaker Notes），含该页正文要点与页级证据映射
  - 输出 manifest.json：slide -> 来源页码/区块（证据映射）

用法：
  python3 ppt_build.py parse_out.json out.pptx [--manifest manifest.json]
  python3 ppt_build.py parse_out.json out.pptx --render out_preview  # 用 soffice 渲染预览

渲染预览依赖系统 LibreOffice（soffice），无则跳过并提示。
"""
import sys
import json
import zipfile
import argparse
import subprocess
import shutil
from pathlib import Path

NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
NS_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_P = "http://schemas.openxmlformats.org/presentationml/2006/main"
NS_CT = "http://schemas.openxmlformats.org/package/2006/content-types"
NS_REL = "http://schemas.openxmlformats.org/package/2006/relationships"

EMU_W = 12192000  # 16:9
EMU_H = 6858000


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _p_para(text, size=1800, bold=False, color="000000"):
    """One <a:p> paragraph from plain text."""
    b = ' b="1"' if bold else ''
    return (f'<a:p><a:r><a:rPr lang="zh-CN" sz="{size}"{b}>'
            f'<a:solidFill><a:srgbClr val="{color}"/></a:solidFill>'
            f'</a:rPr><a:t>{esc(text)}</a:t></a:r></a:p>')


def _paras_to_xml(texts, size=1800, bold=False):
    lines = []
    for t in texts:
        t = str(t).strip()
        if not t:
            continue
        # 每行一个段落，避免超长单段
        lines.append(_p_para(t[:600], size=size, bold=bold))
    return "\n".join(lines) if lines else _p_para("(本页无正文文本)", size=size)


def _slide_xml(title, body_texts):
    """A slide with a title placeholder and a body text frame."""
    body = _paras_to_xml(body_texts)
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:a="{NS_A}" xmlns:r="{NS_R}" xmlns:p="{NS_P}">
<p:cSld><p:spTree>
<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>
<p:grpSpPr/>
<p:sp>
<p:nvSpPr><p:cNvPr id="2" name="Title"/><p:cNvSpPr/><p:nvPr><p:ph type="title"/></p:nvPr></p:nvSpPr>
<p:spPr><a:xfrm><a:off x="457200" y="274638"/><a:ext cx="11277600" cy="823485"/></a:xfrm></p:spPr>
<p:txBody><a:bodyPr/><a:lstStyle/>
{_p_para(title, size=2800, bold=True)}
</p:txBody>
</p:sp>
<p:sp>
<p:nvSpPr><p:cNvPr id="3" name="Body"/><p:cNvSpPr/><p:nvPr><p:ph type="body" idx="1"/></p:nvPr></p:nvSpPr>
<p:spPr><a:xfrm><a:off x="457200" y="1371600"/><a:ext cx="11277600" cy="4800600"/></a:xfrm></p:spPr>
<p:txBody><a:bodyPr/><a:lstStyle/>
{body}
</p:txBody>
</p:sp>
</p:spTree></p:cSld>
<p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr>
</p:sld>'''


def _notes_xml(notes_texts):
    notes = _paras_to_xml(notes_texts, size=1400)
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:notes xmlns:a="{NS_A}" xmlns:r="{NS_R}" xmlns:p="{NS_P}">
<p:cSld><p:spTree>
<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>
<p:grpSpPr/>
<p:sp><p:nvSpPr><p:cNvPr id="2" name="Slide Image Placeholder"/><p:cNvSpPr/><p:nvPr><p:ph type="sldImg"/></p:nvPr></p:nvSpPr>
<p:spPr/><p:txBody><a:bodyPr/><a:lstStyle/><a:p/></p:txBody></p:sp>
<p:sp><p:nvSpPr><p:cNvPr id="3" name="Notes Placeholder"/><p:cNvSpPr/><p:nvPr><p:ph type="body" idx="1"/></p:nvPr></p:nvSpPr>
<p:spPr/><p:txBody><a:bodyPr/><a:lstStyle/>
{notes}
</p:txBody></p:sp>
</p:spTree></p:cSld>
<p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr>
</p:notes>'''


def _content_types(n_slides):
    parts = [
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
        '<Default Extension="xml" ContentType="application/xml"/>',
        '<Default Extension="png" ContentType="image/png"/>',
        '<Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>',
        '<Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/>',
        '<Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/>',
        '<Override PartName="/ppt/notesMasters/notesMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.notesMaster+xml"/>',
        '<Override PartName="/ppt/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>',
    ]
    for i in range(1, n_slides + 1):
        parts.append(f'<Override PartName="/ppt/slides/slide{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>')
        parts.append(f'<Override PartName="/ppt/notesSlides/notesSlide{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.notesSlide+xml"/>')
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<Types xmlns="{NS_CT}">' + "".join(parts) + "</Types>")


def _root_rels():
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="{NS_REL}">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/>
</Relationships>'''


def _presentation_xml(n_slides):
    ids = "".join(f'<p:sldId id="{255 + i}" r:id="rId{3 + i}"/>' for i in range(n_slides))
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:presentation xmlns:a="{NS_A}" xmlns:r="{NS_R}" xmlns:p="{NS_P}">
<p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst>
<p:notesMasterIdLst><p:notesMasterId r:id="rId2"/></p:notesMasterIdLst>
<p:sldIdLst>{ids}</p:sldIdLst>
<p:sldSz cx="{EMU_W}" cy="{EMU_H}" type="screen16x9"/>
<p:notesSz cx="6858000" cy="9144000"/>
</p:presentation>'''


def _presentation_rels(n_slides):
    rels = [
        ('rId1', 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster', 'slideMasters/slideMaster1.xml'),
        ('rId2', 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/notesMaster', 'notesMasters/notesMaster1.xml'),
        ('rId3', 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme', 'theme/theme1.xml'),
    ]
    for i in range(n_slides):
        rels.append((f'rId{4 + i}', 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide', f'slides/slide{i + 1}.xml'))
    body = "".join(f'<Relationship Id="{rid}" Type="{t}" Target="{tg}"/>' for rid, t, tg in rels)
    return f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="{NS_REL}">{body}</Relationships>'


def _slide_rels():
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="{NS_REL}">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/notesSlide" Target="../notesSlides/notesSlide1.xml"/>
</Relationships>'''


def _slide_rels_for(i):
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="{NS_REL}">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/notesSlide" Target="../notesSlides/notesSlide{i}.xml"/>
</Relationships>'''


def _notes_rels():
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="{NS_REL}">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="../slides/slide1.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/notesMaster" Target="../notesMasters/notesMaster1.xml"/>
</Relationships>'''


def _notes_rels_for(i):
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="{NS_REL}">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="../slides/slide{i}.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/notesMaster" Target="../notesMasters/notesMaster1.xml"/>
</Relationships>'''


def _slide_master():
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sldMaster xmlns:a="{NS_A}" xmlns:r="{NS_R}" xmlns:p="{NS_P}">
<p:cSld><p:spTree>
<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>
<p:grpSpPr/>
<p:sp><p:nvSpPr><p:cNvPr id="2" name="Title Placeholder"/><p:cNvSpPr/><p:nvPr><p:ph type="title"/></p:nvPr></p:nvSpPr>
<p:spPr/><p:txBody><a:bodyPr/><a:lstStyle/><a:p/></p:txBody></p:sp>
<p:sp><p:nvSpPr><p:cNvPr id="3" name="Body Placeholder"/><p:cNvSpPr/><p:nvPr><p:ph type="body" idx="1"/></p:nvPr></p:nvSpPr>
<p:spPr/><p:txBody><a:bodyPr/><a:lstStyle/><a:p/></p:txBody></p:sp>
</p:spTree></p:cSld>
<p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" hlink="hlink" folHlink="folHlink"/>
<p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/></p:sldLayoutIdLst>
</p:sldMaster>'''


def _slide_master_rels():
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="{NS_REL}">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="../theme/theme1.xml"/>
</Relationships>'''


def _slide_layout():
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sldLayout xmlns:a="{NS_A}" xmlns:r="{NS_R}" xmlns:p="{NS_P}" type="blank">
<p:cSld name="Blank"><p:spTree>
<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>
<p:grpSpPr/>
</p:spTree></p:cSld>
<p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr>
</p:sldLayout>'''


def _slide_layout_rels():
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="{NS_REL}">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="../slideMasters/slideMaster1.xml"/>
</Relationships>'''


def _notes_master():
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:notesMaster xmlns:a="{NS_A}" xmlns:r="{NS_R}" xmlns:p="{NS_P}">
<p:cSld><p:spTree>
<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>
<p:grpSpPr/>
<p:sp><p:nvSpPr><p:cNvPr id="2" name="Slide Image Placeholder"/><p:cNvSpPr/><p:nvPr><p:ph type="sldImg"/></p:nvPr></p:nvSpPr>
<p:spPr/><p:txBody><a:bodyPr/><a:lstStyle/><a:p/></p:txBody></p:sp>
<p:sp><p:nvSpPr><p:cNvPr id="3" name="Body Placeholder"/><p:cNvSpPr/><p:nvPr><p:ph type="body" idx="1"/></p:nvPr></p:nvSpPr>
<p:spPr/><p:txBody><a:bodyPr/><a:lstStyle/><a:p/></p:txBody></p:sp>
</p:spTree></p:cSld>
<p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" hlink="hlink" folHlink="folHlink"/>
</p:notesMaster>'''


def _notes_master_rels():
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="{NS_REL}">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="../theme/theme1.xml"/>
</Relationships>'''


def _theme():
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<a:theme xmlns:a="{NS_A}" name="Office">
<a:themeElements>
<a:clrScheme name="Office">
<a:dk1><a:sysClr val="windowText" lastClr="000000"/></a:dk1>
<a:lt1><a:sysClr val="window" lastClr="FFFFFF"/></a:lt1>
<a:dk2><a:srgbClr val="1F497D"/></a:dk2>
<a:lt2><a:srgbClr val="EEECE1"/></a:lt2>
<a:accent1><a:srgbClr val="4F81BD"/></a:accent1>
<a:accent2><a:srgbClr val="C0504D"/></a:accent2>
<a:accent3><a:srgbClr val="9BBB59"/></a:accent3>
<a:accent4><a:srgbClr val="8064A2"/></a:accent4>
<a:accent5><a:srgbClr val="4BACC6"/></a:accent5>
<a:accent6><a:srgbClr val="F79646"/></a:accent6>
<a:hlink><a:srgbClr val="0000FF"/></a:hlink>
<a:folHlink><a:srgbClr val="800080"/></a:folHlink>
</a:clrScheme>
<a:fontScheme name="Office">
<a:majorFont><a:latin typeface="Cambria"/><a:ea typeface=""/><a:cs typeface=""/></a:majorFont>
<a:minorFont><a:latin typeface="Calibri"/><a:ea typeface=""/><a:cs typeface=""/></a:minorFont>
</a:fontScheme>
<a:fmtScheme name="Office">
<a:fillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:fillStyleLst>
<a:lnStyleLst><a:ln w="9525" cap="flat" cmpd="sng" algn="ctr"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln></a:lnStyleLst>
<a:effectStyleLst><a:effectStyle><a:effectLst/></a:effectStyle></a:effectStyleLst>
<a:bgFillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:bgFillStyleLst>
</a:fmtScheme>
</a:themeElements>
</a:theme>'''


def _text_from_blocks(page):
    """Concatenate reading-order blocks of a page into lines, with page prefix."""
    lines = []
    for b in page.get("reading_order", []):
        t = b.get("text", "").strip()
        if t:
            lines.append(t)
    return lines


def build_pptx(parsed, out_path, manifest_path=None):
    pages = parsed.get("pages", [])
    tables = parsed.get("tables", [])
    source = parsed.get("source", "")
    notes = parsed.get("notes", [])

    slides = []   # list of dicts: {title, body(list), notes(list), evidence(list)}
    evidence_map = []  # slide -> pages

    # 标题页
    slides.append({
        "title": "文献解析 · 学术汇报",
        "body": [f"来源：{source}", f"总页数：{len(pages)}", f"引擎：{parsed.get('notes', [''])[0] if notes else 'pymupdf/pdfplumber'}"],
        "notes": ["这是由文献结构化解析结果自动组织的可编辑学术 PPT。",
                  f"来源文档：{source}", "本页为标题页。"],
        "evidence": [f"source={source}"],
    })

    # 章节页（从 pages 的 sections 识别 + 正文）
    for p in pages:
        pno = p.get("page")
        # 章节标题
        for sec in p.get("sections", []):
            slides.append({
                "title": sec.get("heading", f"第 {pno} 页"),
                "body": [f"（原文第 {pno} 页 · 区块 {[round(x) for x in sec.get('block_bbox', [])]}）"],
                "notes": [f"章节标题：{sec.get('heading')}（原文第 {pno} 页）"],
                "evidence": [f"page={pno} bbox={[round(x) for x in sec.get('block_bbox', [])]}"],
            })
        # 正文块
        body_lines = _text_from_blocks(p)
        if body_lines:
            slides.append({
                "title": f"第 {pno} 页正文",
                "body": body_lines[:12],
                "notes": [f"第 {pno} 页正文要点（证据映射到该页各文本块）"] + body_lines[:20],
                "evidence": [f"page={pno}"],
            })

    # 表格页
    for i, t in enumerate(tables):
        rows = t.get("rows", [])
        flat = [" | ".join(r) for r in rows[:15]]
        slides.append({
            "title": f"表格 {i + 1}（第 {t.get('page')} 页）",
            "body": flat if flat else ["（表格无结构化内容）"],
            "notes": [f"表格 {i + 1} · 原文第 {t.get('page')} 页", f"bbox={t.get('bbox')}"] + flat,
            "evidence": [f"page={t.get('page')} bbox={t.get('bbox')}"],
        })

    # 参考文献/边界页
    slides.append({
        "title": "证据与边界",
        "body": notes if notes else ["（无补充说明）"],
        "notes": ["以下为解析过程中记录的边界、不确定与异常说明。"] + notes,
        "evidence": ["notes 来自解析 JSON 的 notes 字段"],
    })

    n = len(slides)

    def add(zf, name, content):
        zf.writestr(name, content)

    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        add(zf, "[Content_Types].xml", _content_types(n))
        add(zf, "_rels/.rels", _root_rels())
        add(zf, "ppt/presentation.xml", _presentation_xml(n))
        add(zf, "ppt/_rels/presentation.xml.rels", _presentation_rels(n))
        add(zf, "ppt/slideMasters/slideMaster1.xml", _slide_master())
        add(zf, "ppt/slideMasters/_rels/slideMaster1.xml.rels", _slide_master_rels())
        add(zf, "ppt/slideLayouts/slideLayout1.xml", _slide_layout())
        add(zf, "ppt/slideLayouts/_rels/slideLayout1.xml.rels", _slide_layout_rels())
        add(zf, "ppt/notesMasters/notesMaster1.xml", _notes_master())
        add(zf, "ppt/notesMasters/_rels/notesMaster1.xml.rels", _notes_master_rels())
        add(zf, "ppt/theme/theme1.xml", _theme())
        for i, s in enumerate(slides, 1):
            add(zf, f"ppt/slides/slide{i}.xml", _slide_xml(s["title"], s["body"]))
            add(zf, f"ppt/slides/_rels/slide{i}.xml.rels", _slide_rels_for(i))
            add(zf, f"ppt/notesSlides/notesSlide{i}.xml", _notes_xml(s["notes"]))
            add(zf, f"ppt/notesSlides/_rels/notesSlide{i}.xml.rels", _notes_rels_for(i))
            evidence_map.append({"slide": i, "title": s["title"], "evidence": s["evidence"]})

    if manifest_path:
        Path(manifest_path).write_text(
            json.dumps({"source": source, "slides": evidence_map}, ensure_ascii=False, indent=2),
            encoding="utf-8")
    return n, evidence_map


def render_pptx(pptx_path, out_dir):
    """用 LibreOffice 渲染预览图；无 soffice 时返回 None。"""
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        return None
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    subprocess.run([soffice, "--headless", "--convert-to", "png",
                    "--outdir", str(out), str(pptx_path)],
                   timeout=300, check=False, capture_output=True)
    pngs = sorted(out.glob("*.png"))
    return [str(p) for p in pngs]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("parsed_json")
    ap.add_argument("out_pptx")
    ap.add_argument("--manifest", default=None)
    ap.add_argument("--render", default=None, help="输出预览 PNG 的目录")
    args = ap.parse_args()
    parsed = json.load(open(args.parsed_json, encoding="utf-8"))
    n, ev = build_pptx(parsed, args.out_pptx, args.manifest)
    print(json.dumps({"status": "success", "slides": n, "pptx": args.out_pptx,
                      "manifest": args.manifest, "evidence_map": ev[:3] + ["..."] if len(ev) > 3 else ev},
                     ensure_ascii=False))
    if args.render:
        pngs = render_pptx(args.out_pptx, args.render)
        print(json.dumps({"render": {"pngs": pngs, "dir": args.render}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
