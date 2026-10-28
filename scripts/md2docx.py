# -*- coding: utf-8 -*-
"""将课程论文 Markdown 转换为排版规范的 Word (.docx) 文档。
仅使用 Python 标准库，直接生成 OOXML 包。
"""
import os
import re
import zipfile

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(BASE, "创新药与CRO板块轮动交易策略设计与回测研究.md")
DST = os.path.join(BASE, "创新药与CRO板块轮动交易策略设计与回测研究.docx")

PAGE_W, PAGE_H = 11906, 16838          # A4
MARGIN_LR, MARGIN_TB = 1418, 1440      # 2.5cm / 2.54cm
USABLE = PAGE_W - 2 * MARGIN_LR        # 9070


# ---------------------------------------------------------------- XML 基础
def esc(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def runs_xml(runs):
    """runs: list of dict(text, b, i, mono, sub, sup, sz, ea, szcs)"""
    out = []
    for r in runs:
        if not r.get("text"):
            continue
        pr = []
        fonts = ['<w:rFonts w:ascii="%s" w:hAnsi="%s" w:cs="%s" w:eastAsia="%s"/>' % (
            r.get("ascii", "Times New Roman"), r.get("hAnsi", "Times New Roman"),
            r.get("cs", "Times New Roman"), r.get("ea", "宋体"))]
        pr.append(fonts[0])
        if r.get("b"):
            pr.append("<w:b/>")
        if r.get("i"):
            pr.append("<w:i/>")
        if r.get("sub"):
            pr.append('<w:vertAlign w:val="subscript"/>')
        if r.get("sup"):
            pr.append('<w:vertAlign w:val="superscript"/>')
        sz = r.get("sz")
        if sz:
            pr.append('<w:sz w:val="%d"/><w:szCs w:val="%d"/>' % (sz, sz))
        if r.get("color"):
            pr.append('<w:color w:val="%s"/>' % r["color"])
        out.append("<w:r>%s%s</w:r>" % (
            ("<w:rPr>" + "".join(pr) + "</w:rPr>") if pr else "",
            '<w:t xml:space="preserve">%s</w:t>' % esc(r["text"])))
    return "".join(out)


def p_xml(runs, style=None, jc=None, indent=None, sb=None, sa=None,
          line=None, shd=None, keep_next=False, outline=None):
    ppr = []
    if style:
        ppr.append('<w:pStyle w:val="%s"/>' % style)
    if keep_next:
        ppr.append("<w:keepNext/>")
    if outline is not None:
        ppr.append('<w:outlineLvl w:val="%d"/>' % outline)
    sp = []
    if sb is not None:
        sp.append('w:before="%d"' % sb)
    if sa is not None:
        sp.append('w:after="%d"' % sa)
    if line is not None:
        sp.append('w:line="%d" w:lineRule="auto"' % line)
    if sp:
        ppr.append("<w:spacing %s/>" % " ".join(sp))
    if jc:
        ppr.append('<w:jc w:val="%s"/>' % jc)
    if indent == "first2":
        ppr.append('<w:ind w:firstLineChars="200" w:firstLine="480"/>')
    elif indent == "hang":
        ppr.append('<w:ind w:left="420" w:hanging="420"/>')
    elif indent == "none":
        ppr.append('<w:ind w:firstLine="0" w:left="0"/>')
    if shd:
        ppr.append('<w:shd w:val="clear" w:color="auto" w:fill="%s"/>' % shd)
    return "<w:p>%s%s</w:p>" % (
        ("<w:pPr>" + "".join(ppr) + "</w:pPr>") if ppr else "", runs_xml(runs))


# ---------------------------------------------------------------- 行内解析
INLINE_RE = re.compile(
    r"\[\[(?P<ltext>[^\]]+)\]\]\((?P<lurl>[^)]+)\)"
    r"|\*\*(?P<bold>.+?)\*\*"
    r"|`(?P<code>[^`]+)`"
    r"|(?P<ital>\*[^*]+\*)"
)

MATH_MAP = [
    (r"\\mathbf\{1\}", "1"),
    (r"\\left", ""), (r"\\right", ""),
    (r"\\sigma\^\*", "σ*"), (r"\\sigma\^\{\*\}", "σ*"),
    (r"\\sigma", "σ"), (r"\\Sigma", "Σ"), (r"\\Pi", "Π"),
    (r"\\sqrt", "√"), (r"\\min", "min"), (r"\\max", "max"),
    (r"\\quad", "    "), (r"\\,", " "), (r"\\%", "%"),
    (r"\\\{", "{"), (r"\\\}", "}"),
]


def clean_math(s):
    s = re.sub(r"\\frac\{([^{}]*)\}\{([^{}]*)\}", r"\1 / \2", s)
    for a, b in MATH_MAP:
        s = re.sub(a, b, s)
    s = re.sub(r"_\{([^{}]*)\}", r"(\1)", s)
    s = re.sub(r"_([A-Za-z0-9])", r"(\1)", s)
    s = re.sub(r"\^\{([^{}]*)\}", r"*\1", s)
    s = s.replace("\\", "")
    return s


def parse_inline(text, *, base_sz=None, ea="宋体", ref_mode=False):
    """返回 runs 列表。"""
    runs = []
    pos = 0
    for m in INLINE_RE.finditer(text):
        if m.start() > pos:
            runs.append({"text": clean_math(text[pos:m.start()]), "sz": base_sz, "ea": ea})
        if m.group("ltext") is not None:
            lt, url = m.group("ltext"), m.group("lurl")
            if lt.strip().isdigit():
                runs.append({"text": "[%s]" % lt.strip(), "sup": True, "sz": base_sz, "ea": ea})
            else:
                runs.append({"text": "%s：%s" % (lt, url), "sz": base_sz, "ea": ea})
        elif m.group("bold") is not None:
            inner = m.group("bold")
            sub = re.sub(r"\[\[(\d+)\]\]\([^)]*\)", r"[\1]", inner)
            for piece in re.split(r"(\[\[\d+\]\]\([^)]*\))", inner):
                if not piece:
                    continue
                mm = re.match(r"\[\[(\d+)\]\]\(", piece)
                if mm:
                    runs.append({"text": "[%s]" % mm.group(1), "sup": True, "b": True,
                                 "sz": base_sz, "ea": ea})
                else:
                    runs.append({"text": clean_math(piece), "b": True, "sz": base_sz, "ea": ea})
        elif m.group("code") is not None:
            runs.append({"text": m.group("code"), "mono": True,
                         "ascii": "Consolas", "hAnsi": "Consolas", "cs": "Consolas",
                         "sz": (base_sz or 21), "ea": ea})
        elif m.group("ital") is not None:
            runs.append({"text": clean_math(m.group("ital").strip("*")), "i": True,
                         "sz": base_sz, "ea": ea})
        pos = m.end()
    if pos < len(text):
        runs.append({"text": clean_math(text[pos:]), "sz": base_sz, "ea": ea})
    return runs


# ---------------------------------------------------------------- 公式
def formula_runs(tokens, sz=24):
    runs = []
    for kind, txt in tokens:
        runs.append({"text": txt, "i": True, "sub": kind == "sub", "sup": kind == "sup",
                     "sz": sz, "ea": "Cambria Math", "ascii": "Cambria Math",
                     "hAnsi": "Cambria Math", "cs": "Cambria Math"})
    return runs


FORMULAS = [
    [("t", "Mom"), ("sub", "i,t"), ("t", " = ( "), ("t", "P"), ("sub", "i,t"),
     ("t", " / "), ("t", "P"), ("sub", "i,t−L"), ("t", " ) − 1"), ("t", "        "),
     ("t", "L = 120")],
    [("t", "Trend"), ("sub", "i,t"), ("t", " = 1{ "), ("t", "P"), ("sub", "i,t"),
     ("t", " > MA"), ("sub", "i,t"), ("t", "(M) }"), ("t", "        "),
     ("t", "M = 180")],
    [("t", "w"), ("sub", "t"), ("t", " = min( 1, σ"), ("sup", "*"), ("t", " / σ"),
     ("sub", "t"), ("t", " )"), ("t", "        "), ("t", "σ"), ("sup", "*"),
     ("t", " = 15%")],
    [("t", "IR"), ("sub", "t"), ("t", " = ( Mom"), ("sub", "A,t"), ("t", " − Mom"),
     ("sub", "B,t"), ("t", " ) / ( σ"), ("sub", "20"), ("t", "(r"), ("sub", "A"),
     ("t", " − r"), ("sub", "B"), ("t", ") √L )")],
]


def formula_index(latex):
    if "IR" in latex:
        return 3
    if "\\frac" in latex and "Mom" in latex:
        return 0
    if "Trend" in latex:
        return 1
    return 2


# ---------------------------------------------------------------- 表格
def disp_width(s):
    w = 0
    for ch in s:
        w += 2 if "\u4e00" <= ch <= "\u9fff" or ch in "　（）％" else 1
    return w


def build_table(rows, header=True):
    ncol = max(len(r) for r in rows)
    widths = [0] * ncol
    for r in rows:
        for j, c in enumerate(r):
            widths[j] = max(widths[j], disp_width(c))
    weights = [max(w, 3) for w in widths]
    total = sum(weights)
    cols = [max(int(USABLE * w / total), 500) for w in weights]
    diff = USABLE - sum(cols)
    cols[0] += diff

    xml = ['<w:tbl><w:tblPr>',
           '<w:tblW w:w="5000" w:type="pct"/>',
           '<w:jc w:val="center"/>',
           '<w:tblBorders>',
           '<w:top w:val="single" w:sz="12" w:space="0" w:color="000000"/>',
           '<w:bottom w:val="single" w:sz="12" w:space="0" w:color="000000"/>',
           '<w:insideH w:val="single" w:sz="4" w:space="0" w:color="808080"/>',
           '<w:left w:val="nil"/><w:right w:val="nil"/><w:insideV w:val="nil"/>',
           '</w:tblBorders>',
           '<w:tblCellMar><w:top w:w="40" w:type="dxa"/><w:left w:w="80" w:type="dxa"/>'
           '<w:bottom w:w="40" w:type="dxa"/><w:right w:w="80" w:type="dxa"/></w:tblCellMar>',
           '</w:tblPr>',
           '<w:tblGrid>' + "".join('<w:gridCol w:w="%d"/>' % c for c in cols) + '</w:tblGrid>']

    small = ncol >= 7
    sz = 18 if small else 21

    for ri, row in enumerate(rows):
        is_head = header and ri == 0
        trpr = '<w:trPr><w:tblHeader/></w:trPr>' if is_head else ""
        xml.append("<w:tr>%s" % trpr)
        for j in range(ncol):
            txt = row[j] if j < len(row) else ""
            tcpr = ['<w:tcW w:w="%d" w:type="dxa"/>' % cols[j],
                    '<w:vAlign w:val="center"/>']
            if j == 0 and ncol > 3:
                tcpr.append('<w:tcBorders><w:top w:val="nil"/><w:bottom w:val="nil"/>'
                            '<w:left w:val="nil"/><w:right w:val="nil"/></w:tcBorders>')
            inner = re.sub(r"\*\*(.+?)\*\*", r"\1", txt)
            runs = parse_inline(inner, base_sz=sz)
            for r in runs:
                r.setdefault("sz", sz)
                if is_head:
                    r["b"] = True
            pp = p_xml(runs, jc="left" if j == 0 and ncol > 3 else "center",
                       indent="none", line=260, sb=20, sa=20)
            xml.append("<w:tc>%s%s</w:tc>" % ("<w:tcPr>" + "".join(tcpr) + "</w:tcPr>", pp))
        xml.append("</w:tr>")
    xml.append("</w:tbl>")
    return "".join(xml)


# ---------------------------------------------------------------- 正文构建
CAPTION_RE = re.compile(r"^\*\*(表\s*[^\*]+)\*\*$")


def convert(md):
    lines = md.split("\n")
    body = []
    i = 0
    in_ref = False
    in_abstract = False

    while i < len(lines):
        line = lines[i].rstrip()
        stripped = line.strip()

        if stripped in ("---", ""):
            i += 1
            continue

        # 代码块
        if stripped.startswith("```"):
            lang = stripped[3:].strip()
            i += 1
            code = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code.append(lines[i].rstrip("\n"))
                i += 1
            i += 1
            if lang == "mermaid":
                steps = [
                    "1. 每月最后一个交易日收盘后计算信号（信号与执行严格分离）；",
                    "2. 计算创新药组合与 CRO 组合过去 120 个交易日累计收益之差，并按 IR 公式计算可辨识度；",
                    "3. 若 IR 的绝对值小于阈值 1.0，判定为轮动信号不可辨识，转持静态 50/50 组合；",
                    "4. 若 IR 的绝对值不小于阈值，则持有动量更强的一方；",
                    "5. 对确定的持仓，按过去 20 个交易日已实现波动率 σ 计算仓位 w = min(1, 目标波动率 / σ)，目标波动率取 15%；",
                    "6. 自下一交易日起按新仓位持有，期间不调仓，直至下月末重新评估并回到步骤 1。",
                ]
                for s in steps:
                    body.append(p_xml(parse_inline(s), indent="hang", line=300, sa=60))
            else:
                for k, cl in enumerate(code):
                    body.append(p_xml(
                        [{"text": cl, "mono": True, "ascii": "Consolas", "hAnsi": "Consolas",
                          "cs": "Consolas", "sz": 17, "ea": "宋体"}],
                        indent="none", line=240,
                        sb=120 if k == 0 else 0, sa=120 if k == len(code) - 1 else 0,
                        shd="F2F2F2"))
            continue

        # 公式
        if stripped == "\\[":
            i += 1
            latex = []
            while i < len(lines) and lines[i].strip() != "\\]":
                latex.append(lines[i].strip())
                i += 1
            i += 1
            body.append(p_xml(formula_runs(FORMULAS[formula_index(" ".join(latex))]),
                              jc="center", indent="none", sb=100, sa=140, line=300))
            continue

        # 表格
        if stripped.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                raw = lines[i].strip().strip("|")
                cells = [c.strip() for c in raw.split("|")]
                if not all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c != ""):
                    rows.append(cells)
                i += 1
            body.append(build_table(rows))
            body.append(p_xml([], indent="none", sb=0, sa=0, line=120))
            continue

        # 标题
        if stripped.startswith("# "):
            body.append(p_xml(parse_inline(stripped[2:], ea="黑体"), style="Title",
                              jc="center", indent="none", sa=120))
            i += 1
            continue
        if stripped.startswith("## "):
            txt = stripped[3:].strip()
            in_ref = txt.startswith("参考文献")
            in_abstract = txt.startswith("摘要")
            body.append(p_xml(parse_inline(txt, ea="黑体"), style="Heading1",
                              jc="center", indent="none"))
            i += 1
            continue
        if stripped.startswith("### "):
            body.append(p_xml(parse_inline(stripped[4:], ea="黑体"), style="Heading2",
                              indent="none"))
            i += 1
            continue

        # 副标题
        if stripped.startswith("——"):
            body.append(p_xml(parse_inline(stripped, ea="楷体"), style="Subtitle",
                              jc="center", indent="none"))
            i += 1
            continue

        # 表题
        mc = CAPTION_RE.match(stripped)
        if mc:
            body.append(p_xml(parse_inline(mc.group(1), ea="黑体"), style="Caption",
                              jc="center", indent="none"))
            i += 1
            continue

        # 表注 / 注释（排除以 ** 开头的加粗段落）
        if (stripped.startswith("注：")
                or stripped.startswith("\\*")
                or (stripped.startswith("*") and not stripped.startswith("**"))):
            txt = stripped.lstrip("\\").lstrip("*").rstrip("*")
            if not txt.startswith("注："):
                txt = "注：" + txt
            body.append(p_xml(parse_inline(txt), style="Note", indent="none"))
            i += 1
            continue

        # 关键词 / 摘要正文
        if stripped.startswith("**关键词**"):
            body.append(p_xml(parse_inline(stripped), style="Abstract"))
            i += 1
            continue
        if in_ref is False and stripped.startswith("## ") is False:
            pass

        # 参考文献条目
        if re.match(r"^\[\d+\]", stripped):
            body.append(p_xml(parse_inline(stripped, base_sz=21), style="Ref"))
            i += 1
            continue

        # 普通段落
        body.append(p_xml(parse_inline(stripped), style="Abstract" if in_abstract else None))
        i += 1

    return "".join(body)


# ---------------------------------------------------------------- 包生成
STYLES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:docDefaults>
<w:rPrDefault><w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:cs="Times New Roman" w:eastAsia="%(body)s"/><w:sz w:val="24"/><w:szCs w:val="24"/></w:rPr></w:rPrDefault>
<w:pPrDefault><w:pPr><w:spacing w:line="360" w:lineRule="auto" w:after="60"/></w:pPr></w:pPrDefault>
</w:docDefaults>
<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:qFormat/>
<w:pPr><w:spacing w:line="360" w:lineRule="auto" w:after="60"/><w:ind w:firstLineChars="200" w:firstLine="480"/></w:pPr>
<w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:cs="Times New Roman" w:eastAsia="%(body)s"/><w:sz w:val="24"/><w:szCs w:val="24"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/><w:qFormat/>
<w:pPr><w:keepNext/><w:spacing w:before="0" w:after="160" w:line="360" w:lineRule="auto"/><w:jc w:val="center"/><w:ind w:firstLine="0"/></w:pPr>
<w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:cs="Times New Roman" w:eastAsia="%(head)s"/><w:b/><w:sz w:val="36"/><w:szCs w:val="36"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Subtitle"><w:name w:val="Subtitle"/><w:basedOn w:val="Normal"/><w:qFormat/>
<w:pPr><w:spacing w:before="0" w:after="240" w:line="360" w:lineRule="auto"/><w:jc w:val="center"/><w:ind w:firstLine="0"/></w:pPr>
<w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:cs="Times New Roman" w:eastAsia="%(kai)s"/><w:sz w:val="24"/><w:szCs w:val="24"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/>
<w:pPr><w:keepNext/><w:spacing w:before="320" w:after="160" w:line="360" w:lineRule="auto"/><w:jc w:val="center"/><w:ind w:firstLine="0"/><w:outlineLvl w:val="0"/></w:pPr>
<w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:cs="Times New Roman" w:eastAsia="%(head)s"/><w:b/><w:sz w:val="30"/><w:szCs w:val="30"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/>
<w:pPr><w:keepNext/><w:spacing w:before="240" w:after="120" w:line="360" w:lineRule="auto"/><w:ind w:firstLine="0"/><w:outlineLvl w:val="1"/></w:pPr>
<w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:cs="Times New Roman" w:eastAsia="%(head)s"/><w:b/><w:sz w:val="26"/><w:szCs w:val="26"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading3"><w:name w:val="heading 3"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/>
<w:pPr><w:keepNext/><w:spacing w:before="200" w:after="100" w:line="360" w:lineRule="auto"/><w:ind w:firstLine="0"/><w:outlineLvl w:val="2"/></w:pPr>
<w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:cs="Times New Roman" w:eastAsia="%(head)s"/><w:b/><w:sz w:val="24"/><w:szCs w:val="24"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Abstract"><w:name w:val="Abstract"/><w:basedOn w:val="Normal"/><w:qFormat/>
<w:pPr><w:spacing w:line="320" w:lineRule="auto" w:after="60"/><w:jc w:val="both"/><w:ind w:firstLineChars="200" w:firstLine="420"/></w:pPr>
<w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:cs="Times New Roman" w:eastAsia="%(body)s"/><w:sz w:val="21"/><w:szCs w:val="21"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Caption"><w:name w:val="caption"/><w:basedOn w:val="Normal"/><w:qFormat/>
<w:pPr><w:keepNext/><w:spacing w:before="180" w:after="80" w:line="300" w:lineRule="auto"/><w:jc w:val="center"/><w:ind w:firstLine="0"/></w:pPr>
<w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:cs="Times New Roman" w:eastAsia="%(head)s"/><w:b/><w:sz w:val="21"/><w:szCs w:val="21"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Note"><w:name w:val="Note"/><w:basedOn w:val="Normal"/><w:qFormat/>
<w:pPr><w:spacing w:before="60" w:after="180" w:line="300" w:lineRule="auto"/><w:jc w:val="both"/><w:ind w:firstLine="0"/></w:pPr>
<w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:cs="Times New Roman" w:eastAsia="%(body)s"/><w:sz w:val="19"/><w:szCs w:val="19"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Ref"><w:name w:val="Ref"/><w:basedOn w:val="Normal"/><w:qFormat/>
<w:pPr><w:spacing w:before="0" w:after="60" w:line="300" w:lineRule="auto"/><w:jc w:val="both"/><w:ind w:left="420" w:hanging="420"/></w:pPr>
<w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:cs="Times New Roman" w:eastAsia="%(body)s"/><w:sz w:val="21"/><w:szCs w:val="21"/></w:rPr></w:style>
<w:style w:type="table" w:styleId="TableGrid"><w:name w:val="Table Grid"/></w:style>
</w:styles>""" % {"body": "宋体", "head": "黑体", "kai": "楷体"}


def build():
    md = open(SRC, encoding="utf-8").read()
    body = convert(md)

    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body>" + body +
        '<w:sectPr>'
        '<w:footerReference w:type="default" r:id="rId3" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"/>'
        '<w:pgSz w:w="%d" w:h="%d"/>'
        '<w:pgMar w:top="%d" w:right="%d" w:bottom="%d" w:left="%d" '
        'w:header="851" w:footer="992" w:gutter="0"/>'
        '<w:cols w:space="425"/><w:docGrid w:linePitch="312"/>'
        "</w:sectPr></w:body></w:document>" % (PAGE_W, PAGE_H, MARGIN_TB, MARGIN_LR,
                                              MARGIN_TB, MARGIN_LR)
    )

    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
        '<Override PartName="/word/settings.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"/>'
        '<Override PartName="/word/footer1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>'
        '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
        '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
        "</Types>"
    )

    root_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
        '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>'
        "</Relationships>"
    )

    doc_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/settings" Target="settings.xml"/>'
        '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" Target="footer1.xml"/>'
        "</Relationships>"
    )

    footer = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:ftr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:p><w:pPr><w:jc w:val="center"/><w:spacing w:line="240" w:lineRule="auto"/>'
        '<w:ind w:firstLine="0"/></w:pPr>'
        '<w:r><w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:eastAsia="宋体"/>'
        '<w:sz w:val="20"/><w:szCs w:val="20"/></w:rPr><w:t xml:space="preserve">— </w:t></w:r>'
        '<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
        '<w:r><w:instrText xml:space="preserve"> PAGE </w:instrText></w:r>'
        '<w:r><w:fldChar w:fldCharType="end"/></w:r>'
        '<w:r><w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:eastAsia="宋体"/>'
        '<w:sz w:val="20"/><w:szCs w:val="20"/></w:rPr><w:t xml:space="preserve"> —</w:t></w:r>'
        "</w:p></w:ftr>"
    )

    settings = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:settings xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:zoom w:percent="100"/><w:defaultTabStop w:val="420"/>'
        "</w:settings>"
    )

    core = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        "<dc:title>创新药与 CRO 板块轮动交易策略设计与回测研究</dc:title>"
        "<dc:subject>金融市场交易策略设计</dc:subject>"
        "<dc:creator>课程论文</dc:creator>"
        '<cp:lastModifiedBy>课程论文</cp:lastModifiedBy>'
        '<dcterms:created xsi:type="dcterms:W3CDTF">2026-10-15T00:00:00Z</dcterms:created>'
        '<dcterms:modified xsi:type="dcterms:W3CDTF">2026-10-15T00:00:00Z</dcterms:modified>'
        "</cp:coreProperties>"
    )

    app = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" '
        'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
        "<Application>WorkBuddy</Application></Properties>"
    )

    with zipfile.ZipFile(DST, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", root_rels)
        z.writestr("word/document.xml", document)
        z.writestr("word/_rels/document.xml.rels", doc_rels)
        z.writestr("word/styles.xml", STYLES)
        z.writestr("word/settings.xml", settings)
        z.writestr("word/footer1.xml", footer)
        z.writestr("docProps/core.xml", core)
        z.writestr("docProps/app.xml", app)
    print("written:", DST, os.path.getsize(DST), "bytes")


if __name__ == "__main__":
    build()
