"""Convert the project initiation document from Markdown to a Word (.docx) file.

Supports the subset of Markdown used in ``docs/project-initiation-document.md``:
headings, pipe tables, fenced code blocks, bullet/ordered lists, blockquotes,
horizontal rules, inline code, bold, italic and hyperlinks.

Usage:
    python scripts/md_to_docx.py docs/project-initiation-document.md \
        docs/TradePulse-Project-Initiation-Document.docx
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

# --------------------------------------------------------------------------
# Inline formatting
# --------------------------------------------------------------------------

INLINE_RE = re.compile(
    r"\*\*(?P<bold>.+?)\*\*"
    r"|`(?P<code>[^`]+)`"
    r"|<(?P<autolink>https?://[^>\s]+)>"
    r"|\[(?P<ltext>[^\]]+)\]\((?P<lurl>[^)]+)\)"
    r"|(?<![A-Za-z0-9])_(?P<italic>[^_\n]+?)_(?![A-Za-z0-9])"
)

CODE_FONT = "Consolas"
LINK_COLOR = "0B5394"

# Layout settings, overridden by --compact for page-limited submissions.
CFG = {
    "margin": 1.0,
    "body_pt": 10.5,
    "body_space_after": 6,
    "line_spacing": 1.15,
    "h1_pt": 15,
    "h2_pt": 12.5,
    "h3_pt": 11,
    "table_pt": 9,
    "code_pt": 8,
    "title_pt": 28,
}

COMPACT = {
    "margin": 0.85,
    "body_pt": 10,
    "body_space_after": 4,
    "line_spacing": 1.05,
    "h1_pt": 13.5,
    "h2_pt": 11.5,
    "h3_pt": 10.5,
    "table_pt": 8.5,
    "code_pt": 7.5,
    "title_pt": 24,
}


def add_hyperlink(paragraph, url: str, text: str, bold: bool = False) -> None:
    """Append a clickable hyperlink to a paragraph."""
    r_id = paragraph.part.relate_to(url, RT.HYPERLINK, is_external=True)

    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("r:id"), r_id)

    run = OxmlElement("w:r")
    r_pr = OxmlElement("w:rPr")

    r_fonts = OxmlElement("w:rFonts")
    r_fonts.set(qn("w:ascii"), "Calibri")
    r_fonts.set(qn("w:hAnsi"), "Calibri")
    r_pr.append(r_fonts)

    if bold:
        r_pr.append(OxmlElement("w:b"))

    color = OxmlElement("w:color")
    color.set(qn("w:val"), LINK_COLOR)
    r_pr.append(color)

    underline = OxmlElement("w:u")
    underline.set(qn("w:val"), "single")
    r_pr.append(underline)

    run.append(r_pr)

    text_el = OxmlElement("w:t")
    text_el.set(qn("xml:space"), "preserve")
    text_el.text = text
    run.append(text_el)

    hyperlink.append(run)
    paragraph._p.append(hyperlink)


def add_inline(paragraph, text: str, bold: bool = False, italic: bool = False) -> None:
    """Render inline Markdown into runs on an existing paragraph."""
    position = 0

    for match in INLINE_RE.finditer(text):
        if match.start() > position:
            run = paragraph.add_run(text[position:match.start()])
            run.bold = bold or None
            run.italic = italic or None

        if match.group("bold") is not None:
            add_inline(paragraph, match.group("bold"), bold=True, italic=italic)
        elif match.group("code") is not None:
            run = paragraph.add_run(match.group("code"))
            run.font.name = CODE_FONT
            run.font.size = Pt(9.5)
            run.font.color.rgb = RGBColor(0xA3, 0x1D, 0x4E)
            run.bold = bold or None
        elif match.group("autolink") is not None:
            url = match.group("autolink")
            add_hyperlink(paragraph, url, url, bold=bold)
        elif match.group("lurl") is not None:
            add_hyperlink(
                paragraph, match.group("lurl"), match.group("ltext"), bold=bold
            )
        elif match.group("italic") is not None:
            add_inline(paragraph, match.group("italic"), bold=bold, italic=True)

        position = match.end()

    if position < len(text):
        run = paragraph.add_run(text[position:])
        run.bold = bold or None
        run.italic = italic or None


# --------------------------------------------------------------------------
# Block helpers
# --------------------------------------------------------------------------


def shade_paragraph(paragraph, fill: str = "F2F2F2") -> None:
    """Apply a background fill to a paragraph."""
    p_pr = paragraph._p.get_or_add_pPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    p_pr.append(shd)


def add_horizontal_rule(document) -> None:
    paragraph = document.add_paragraph()
    paragraph.paragraph_format.space_before = Pt(4)
    paragraph.paragraph_format.space_after = Pt(8)
    p_pr = paragraph._p.get_or_add_pPr()
    borders = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "6")
    bottom.set(qn("w:space"), "1")
    bottom.set(qn("w:color"), "BFBFBF")
    borders.append(bottom)
    p_pr.append(borders)


def add_code_block(document, lines: list[str]) -> None:
    paragraph = document.add_paragraph()
    fmt = paragraph.paragraph_format
    fmt.space_before = Pt(6)
    fmt.space_after = Pt(8)
    fmt.line_spacing = 1.0
    fmt.left_indent = Inches(0.12)
    fmt.right_indent = Inches(0.05)
    shade_paragraph(paragraph)

    for index, line in enumerate(lines):
        run = paragraph.add_run(line if line else " ")
        run.font.name = CODE_FONT
        run.font.size = Pt(CFG["code_pt"])
        if index < len(lines) - 1:
            run.add_break()


def split_row(line: str) -> list[str]:
    """Split a pipe-table row into stripped cell strings."""
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    return [cell.strip() for cell in stripped.split("|")]


def is_separator_row(line: str) -> bool:
    stripped = line.strip()
    if not stripped.startswith("|"):
        return False
    cells = split_row(stripped)
    return bool(cells) and all(
        re.fullmatch(r":?-{2,}:?", cell) for cell in cells
    )


def add_table(document, rows: list[list[str]]) -> None:
    if not rows:
        return

    column_count = max(len(row) for row in rows)
    rows = [row + [""] * (column_count - len(row)) for row in rows]

    header = rows[0]
    has_header = any(cell for cell in header)
    if has_header:
        body = rows[1:]
    else:
        # A leading all-empty row is an unstyled table header, not real content.
        body = rows[1:] if not any(rows[0]) else rows

    table = document.add_table(rows=0, cols=column_count)
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = True

    def fill(cells, values, bold=False):
        for cell, value in zip(cells, values):
            cell.paragraphs[0].text = ""
            paragraph = cell.paragraphs[0]
            paragraph.paragraph_format.space_before = Pt(2)
            paragraph.paragraph_format.space_after = Pt(2)
            add_inline(paragraph, value, bold=bold)
            for run in paragraph.runs:
                if run.font.size is None:
                    run.font.size = Pt(CFG["table_pt"])

    if has_header:
        header_cells = table.add_row().cells
        fill(header_cells, header, bold=True)
        for cell in header_cells:
            tc_pr = cell._tc.get_or_add_tcPr()
            shd = OxmlElement("w:shd")
            shd.set(qn("w:val"), "clear")
            shd.set(qn("w:color"), "auto")
            shd.set(qn("w:fill"), "DCE6F1")
            tc_pr.append(shd)

    for row in body:
        fill(table.add_row().cells, row)

    spacer = document.add_paragraph()
    spacer.paragraph_format.space_after = Pt(4)
    spacer.paragraph_format.line_spacing = 1.0


def add_page_number_footer(document, label: str) -> None:
    footer = document.sections[0].footer
    paragraph = footer.paragraphs[0]
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER

    prefix = paragraph.add_run(f"{label}  |  Page ")
    prefix.font.size = Pt(8)
    prefix.font.color.rgb = RGBColor(0x77, 0x77, 0x77)

    run = paragraph.add_run()
    run.font.size = Pt(8)
    run.font.color.rgb = RGBColor(0x77, 0x77, 0x77)

    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = "PAGE"
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")

    run._r.append(begin)
    run._r.append(instr)
    run._r.append(end)


# --------------------------------------------------------------------------
# Document builder
# --------------------------------------------------------------------------


def build(markdown_path: Path, output_path: Path) -> None:
    lines = markdown_path.read_text(encoding="utf-8").splitlines()

    document = Document()

    margin = Inches(CFG["margin"])
    section = document.sections[0]
    section.top_margin = margin
    section.bottom_margin = margin
    section.left_margin = margin
    section.right_margin = margin

    normal = document.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(CFG["body_pt"])
    normal.paragraph_format.space_after = Pt(CFG["body_space_after"])
    normal.paragraph_format.line_spacing = CFG["line_spacing"]

    for style_name, size, color in (
        ("Heading 1", CFG["h1_pt"], RGBColor(0x1F, 0x3B, 0x63)),
        ("Heading 2", CFG["h2_pt"], RGBColor(0x1F, 0x3B, 0x63)),
        ("Heading 3", CFG["h3_pt"], RGBColor(0x33, 0x33, 0x33)),
    ):
        style = document.styles[style_name]
        style.font.name = "Calibri"
        style.font.size = Pt(size)
        style.font.color.rgb = color
        style.paragraph_format.space_before = Pt(10 if size > 12 else 8)
        style.paragraph_format.space_after = Pt(4)
        style.paragraph_format.keep_with_next = True

    index = 0
    total = len(lines)
    first_heading = True

    while index < total:
        raw = lines[index]
        line = raw.rstrip()
        stripped = line.strip()

        # Fenced code block
        if stripped.startswith("```"):
            index += 1
            block: list[str] = []
            while index < total and not lines[index].strip().startswith("```"):
                block.append(lines[index].rstrip("\n").replace("\t", "    "))
                index += 1
            index += 1
            add_code_block(document, block)
            continue

        # Blank line
        if not stripped:
            index += 1
            continue

        # Table
        if (
            stripped.startswith("|")
            and index + 1 < total
            and is_separator_row(lines[index + 1])
        ):
            rows = [split_row(stripped)]
            index += 2
            while index < total and lines[index].strip().startswith("|"):
                rows.append(split_row(lines[index]))
                index += 1
            add_table(document, rows)
            continue

        # Headings
        heading = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if heading:
            level = len(heading.group(1))
            text = heading.group(2).strip()
            if level == 1:
                paragraph = document.add_paragraph()
                paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
                paragraph.paragraph_format.space_before = Pt(30)
                paragraph.paragraph_format.space_after = Pt(4)
                run = paragraph.add_run(re.sub(r"[*`]", "", text))
                run.font.size = Pt(CFG["title_pt"])
                run.font.bold = True
                run.font.color.rgb = RGBColor(0x1F, 0x3B, 0x63)
                first_heading = False
            elif level == 2:
                if first_heading:
                    paragraph = document.add_paragraph()
                    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    paragraph.paragraph_format.space_after = Pt(10)
                    run = paragraph.add_run(re.sub(r"[*`]", "", text))
                    run.font.size = Pt(14)
                    run.font.color.rgb = RGBColor(0x55, 0x55, 0x55)
                    first_heading = False
                else:
                    document.add_heading(re.sub(r"[*`]", "", text), level=1)
            else:
                doc_level = min(level - 1, 3)
                document.add_heading(re.sub(r"[*`]", "", text), level=doc_level)
            index += 1
            continue

        # Horizontal rule
        if re.fullmatch(r"-{3,}|\*{3,}|_{3,}", stripped):
            add_horizontal_rule(document)
            index += 1
            continue

        # Blockquote
        if stripped.startswith(">"):
            quote: list[str] = []
            while index < total and lines[index].strip().startswith(">"):
                quote.append(lines[index].strip().lstrip(">").strip())
                index += 1
            paragraph = document.add_paragraph()
            paragraph.paragraph_format.left_indent = Inches(0.3)
            paragraph.paragraph_format.space_before = Pt(6)
            paragraph.paragraph_format.space_after = Pt(8)
            add_inline(paragraph, " ".join(part for part in quote if part), italic=True)
            continue

        # Bullet list
        bullet = re.match(r"^(\s*)-\s+(.*)$", line)
        if bullet:
            depth = len(bullet.group(1).expandtabs(2)) // 2
            style = "List Bullet" if depth == 0 else f"List Bullet {min(depth + 1, 3)}"
            try:
                paragraph = document.add_paragraph(style=style)
            except KeyError:
                paragraph = document.add_paragraph(style="List Bullet")
                paragraph.paragraph_format.left_indent = Inches(0.25 * depth)
            paragraph.paragraph_format.space_after = Pt(2)
            add_inline(paragraph, bullet.group(2).strip())
            index += 1
            continue

        # Ordered list (numbers rendered literally so each list restarts at 1)
        ordered = re.match(r"^(\s*)(\d+)\.\s+(.*)$", line)
        if ordered:
            depth = len(ordered.group(1).expandtabs(2)) // 2
            paragraph = document.add_paragraph()
            paragraph.paragraph_format.left_indent = Inches(0.25 + 0.25 * depth)
            paragraph.paragraph_format.first_line_indent = Inches(-0.25)
            paragraph.paragraph_format.space_after = Pt(2)
            paragraph.add_run(f"{ordered.group(2)}. ")
            add_inline(paragraph, ordered.group(3).strip())
            index += 1
            continue

        # Paragraph (join wrapped lines)
        buffer: list[str] = [stripped]
        index += 1
        while index < total:
            nxt = lines[index].strip()
            if not nxt:
                break
            if re.match(r"^(#{1,6})\s", nxt) or nxt.startswith("|") or nxt.startswith("```"):
                break
            if re.match(r"^(\s*)[-*]\s+", lines[index]) or re.match(r"^\s*\d+\.\s+", lines[index]):
                break
            if re.fullmatch(r"-{3,}|\*{3,}|_{3,}", nxt) or nxt.startswith(">"):
                break
            buffer.append(nxt)
            index += 1

        paragraph = document.add_paragraph()
        add_inline(paragraph, " ".join(buffer))

    add_page_number_footer(document, "TradePulse — Project Initiation Document")
    document.save(str(output_path))


def main() -> int:
    positional = [arg for arg in sys.argv[1:] if not arg.startswith("--")]
    source = Path(positional[0] if positional else "docs/project-initiation-document.md")
    target = Path(
        positional[1]
        if len(positional) > 1
        else "docs/TradePulse-Project-Initial-Document.docx"
    )

    if not source.is_file():
        print(f"error: source not found: {source}")
        return 1

    if "--compact" in sys.argv:
        CFG.update(COMPACT)

    target.parent.mkdir(parents=True, exist_ok=True)
    build(source, target)
    print(f"wrote {target} ({target.stat().st_size / 1024:.1f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
