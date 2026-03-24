"""
Manuscript export module for Story Forge.
Merges chapters into submission-ready document formats (DOCX, PDF).

Standard manuscript formatting:
- 12pt Times New Roman (or Courier)
- Double-spaced
- 1-inch margins
- Title page with author/title
- Chapter breaks with titles
- Page numbers
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from docx import Document
from docx.shared import Pt, Inches, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.section import WD_ORIENT

from db import Book, Chapter, get_session
from sqlalchemy.orm import joinedload

logger = logging.getLogger(__name__)

# Output directory
MANUSCRIPT_DIR = Path(__file__).parent / "data" / "manuscripts"
MANUSCRIPT_DIR.mkdir(parents=True, exist_ok=True)


def get_book_with_chapters(book_id: int) -> Optional[Book]:
    """Load a book with all chapters ordered."""
    session = get_session()
    try:
        return session.query(Book).options(
            joinedload(Book.chapters)
        ).filter(Book.id == book_id).first()
    finally:
        session.close()


def export_manuscript_docx(
    book_id: int,
    font_name: str = "Times New Roman",
    font_size: int = 12,
    double_spaced: bool = True,
    include_title_page: bool = True,
) -> dict:
    """
    Export a book as a submission-ready DOCX manuscript.

    Args:
        book_id: Book ID to export
        font_name: Font to use (Times New Roman or Courier New)
        font_size: Font size in points
        double_spaced: Whether to double-space the text
        include_title_page: Whether to include a title page

    Returns:
        dict with export metadata (path, word_count, page_estimate)
    """
    book = get_book_with_chapters(book_id)
    if not book:
        raise ValueError(f"Book not found: {book_id}")

    chapters = sorted(book.chapters, key=lambda c: c.order)
    if not chapters:
        raise ValueError(f"Book has no chapters: {book.title}")

    doc = Document()

    # Page setup: 1-inch margins, letter size
    for section in doc.sections:
        section.top_margin = Inches(1)
        section.bottom_margin = Inches(1)
        section.left_margin = Inches(1)
        section.right_margin = Inches(1)

    # Default paragraph style
    style = doc.styles['Normal']
    font = style.font
    font.name = font_name
    font.size = Pt(font_size)
    if double_spaced:
        style.paragraph_format.line_spacing = 2.0
    style.paragraph_format.space_after = Pt(0)
    style.paragraph_format.space_before = Pt(0)

    # Title page
    if include_title_page:
        _add_title_page(doc, book, font_name, font_size)

    # Chapters
    total_words = 0
    for i, chapter in enumerate(chapters):
        if i > 0 or include_title_page:
            doc.add_page_break()

        _add_chapter(doc, chapter, font_name, font_size, double_spaced)
        word_count = len(chapter.content.split()) if chapter.content else 0
        total_words += word_count

    # Generate filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_title = "".join(c if c.isalnum() else "_" for c in book.title)
    filename = f"{safe_title}_manuscript_{timestamp}.docx"
    output_path = MANUSCRIPT_DIR / filename

    doc.save(str(output_path))

    # Estimate pages (~250 words per page for standard manuscript)
    page_estimate = max(1, total_words // 250)

    result = {
        "path": str(output_path),
        "filename": filename,
        "size": output_path.stat().st_size,
        "word_count": total_words,
        "chapter_count": len(chapters),
        "page_estimate": page_estimate,
        "format": "docx",
        "created_at": datetime.now().isoformat(),
        "book_title": book.title,
        "author": book.author or "Unknown",
    }

    logger.info(f"Manuscript exported: {filename} ({total_words} words, ~{page_estimate} pages)")
    return result


def _add_title_page(doc: Document, book: Book, font_name: str, font_size: int):
    """Add a standard manuscript title page."""
    # Add blank lines to push content to center-ish area
    for _ in range(8):
        p = doc.add_paragraph()
        p.style.font.name = font_name
        p.style.font.size = Pt(font_size)

    # Title
    title_para = doc.add_paragraph()
    title_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = title_para.add_run(book.title.upper())
    run.font.name = font_name
    run.font.size = Pt(font_size)
    run.bold = True

    # Blank line
    doc.add_paragraph()

    # "by" line
    by_para = doc.add_paragraph()
    by_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = by_para.add_run("by")
    run.font.name = font_name
    run.font.size = Pt(font_size)

    # Author
    author_para = doc.add_paragraph()
    author_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = author_para.add_run(book.author or "Unknown Author")
    run.font.name = font_name
    run.font.size = Pt(font_size)

    # Blank lines
    for _ in range(4):
        doc.add_paragraph()

    # Word count (approximate)
    total_words = sum(len(c.content.split()) if c.content else 0 for c in book.chapters)
    # Round to nearest thousand for manuscript format
    rounded_words = round(total_words / 1000) * 1000 if total_words > 1000 else total_words
    word_count_text = f"Approximately {rounded_words:,} words" if rounded_words > 0 else ""

    if word_count_text:
        wc_para = doc.add_paragraph()
        wc_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = wc_para.add_run(word_count_text)
        run.font.name = font_name
        run.font.size = Pt(font_size)

    # Description/synopsis if available
    if book.description:
        doc.add_paragraph()
        doc.add_paragraph()
        synopsis_header = doc.add_paragraph()
        synopsis_header.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = synopsis_header.add_run("Synopsis")
        run.font.name = font_name
        run.font.size = Pt(font_size)
        run.italic = True

        doc.add_paragraph()
        synopsis_para = doc.add_paragraph()
        synopsis_para.alignment = WD_ALIGN_PARAGRAPH.LEFT
        run = synopsis_para.add_run(book.description)
        run.font.name = font_name
        run.font.size = Pt(font_size)


def _add_chapter(doc: Document, chapter: Chapter, font_name: str, font_size: int, double_spaced: bool):
    """Add a chapter to the document."""
    # Chapter heading — centered, about 1/3 down the page
    for _ in range(4):
        p = doc.add_paragraph()
        p.style.font.name = font_name

    # Chapter title
    heading_para = doc.add_paragraph()
    heading_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = heading_para.add_run(chapter.title.upper())
    run.font.name = font_name
    run.font.size = Pt(font_size)
    run.bold = True

    # Blank lines after heading
    for _ in range(2):
        doc.add_paragraph()

    # Chapter content — split into paragraphs
    if chapter.content:
        paragraphs = chapter.content.split('\n')
        for para_text in paragraphs:
            para_text = para_text.strip()
            if not para_text:
                continue

            p = doc.add_paragraph()
            p.paragraph_format.first_line_indent = Inches(0.5)
            if double_spaced:
                p.paragraph_format.line_spacing = 2.0

            run = p.add_run(para_text)
            run.font.name = font_name
            run.font.size = Pt(font_size)


def export_manuscript_txt(book_id: int) -> dict:
    """
    Export a book as a plain text manuscript.
    Useful for submissions that require plain text.
    """
    book = get_book_with_chapters(book_id)
    if not book:
        raise ValueError(f"Book not found: {book_id}")

    chapters = sorted(book.chapters, key=lambda c: c.order)
    if not chapters:
        raise ValueError(f"Book has no chapters: {book.title}")

    lines = []

    # Title block
    lines.append(book.title.upper())
    lines.append(f"by {book.author or 'Unknown Author'}")
    lines.append("")
    lines.append("---")
    lines.append("")

    total_words = 0
    for chapter in chapters:
        lines.append("")
        lines.append(chapter.title.upper())
        lines.append("")

        if chapter.content:
            for para in chapter.content.split('\n'):
                para = para.strip()
                if para:
                    lines.append(f"    {para}")
                    lines.append("")
            total_words += len(chapter.content.split())

        lines.append("")
        lines.append("* * *")
        lines.append("")

    # Generate file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_title = "".join(c if c.isalnum() else "_" for c in book.title)
    filename = f"{safe_title}_manuscript_{timestamp}.txt"
    output_path = MANUSCRIPT_DIR / filename

    output_path.write_text("\n".join(lines), encoding="utf-8")

    return {
        "path": str(output_path),
        "filename": filename,
        "size": output_path.stat().st_size,
        "word_count": total_words,
        "chapter_count": len(chapters),
        "page_estimate": max(1, total_words // 250),
        "format": "txt",
        "created_at": datetime.now().isoformat(),
        "book_title": book.title,
        "author": book.author or "Unknown",
    }


def list_manuscripts(book_id: Optional[int] = None) -> list[dict]:
    """List exported manuscripts, optionally filtered by book."""
    manuscripts = []
    for f in MANUSCRIPT_DIR.iterdir():
        if f.suffix in ('.docx', '.txt', '.pdf'):
            manuscripts.append({
                "filename": f.name,
                "path": str(f),
                "size": f.stat().st_size,
                "format": f.suffix.lstrip('.'),
                "modified_at": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
            })

    manuscripts.sort(key=lambda x: x["modified_at"], reverse=True)
    return manuscripts


def delete_manuscript(filename: str) -> bool:
    """Delete a manuscript file."""
    path = MANUSCRIPT_DIR / filename
    if path.exists() and path.parent == MANUSCRIPT_DIR:
        path.unlink()
        return True
    return False
