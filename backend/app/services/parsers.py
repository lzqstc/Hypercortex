from __future__ import annotations

import csv
import email
import io
import ipaddress
import json
import mimetypes
import re
import socket
from dataclasses import dataclass
from email import policy
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

MAX_TEXT_CHARS = 3_000_000
MAX_SHEET_ROWS = 5000
MAX_JSON_ITEMS = 5000


class ParserError(Exception):
    pass


class UnsupportedFileType(ParserError):
    pass


@dataclass
class Section:
    text: str
    page: int | None = None
    section: str = ""


def _clean_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _read_text(path: Path) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "latin-1"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="ignore")


def _read_csv(path: Path) -> list[Section]:
    text = _read_text(path)
    rows: list[str] = []
    for index, row in enumerate(csv.reader(io.StringIO(text))):
        if index >= MAX_SHEET_ROWS:
            break
        values = [value.strip() for value in row if value.strip()]
        if values:
            rows.append(" | ".join(values))
    return [Section(_clean_text("\n".join(rows)), section=path.stem)]


def _read_markdown(path: Path) -> list[Section]:
    text = _read_text(path)
    sections: list[Section] = []
    heading = path.stem
    buffer: list[str] = []

    def flush() -> None:
        if buffer:
            content = _clean_text("\n".join(buffer))
            if content:
                sections.append(Section(content, section=heading))
            buffer.clear()

    for line in text.splitlines():
        match = re.match(r"^(#{1,6})\s+(.*)$", line)
        if match:
            flush()
            heading = match.group(2).strip() or heading
            continue
        buffer.append(line)
    flush()
    return sections or [Section(_clean_text(text), section=path.stem)]


def _read_pdf(path: Path, ocr_enabled: bool = False) -> list[Section]:
    try:
        import fitz  # PyMuPDF
    except ImportError as exc:  # pragma: no cover - dependency is in requirements
        raise ParserError("缺少 PyMuPDF，无法解析 PDF") from exc

    sections: list[Section] = []
    document = fitz.open(path)
    try:
        for page_index, page in enumerate(document, start=1):
            text = page.get_text("text", sort=True).strip()
            if not text and ocr_enabled:
                text = _ocr_pdf_page(page)
            if text.strip():
                sections.append(Section(_clean_text(text), page=page_index, section=f"第 {page_index} 页"))
    finally:
        document.close()
    return sections


def _ocr_pdf_page(page) -> str:
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        return ""

    try:
        import fitz

        pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2))
        image = Image.open(io.BytesIO(pixmap.tobytes("png")))
        return pytesseract.image_to_string(image, lang="chi_sim+eng")
    except Exception:
        return ""


def _read_docx(path: Path) -> list[Section]:
    try:
        from docx import Document
        from docx.table import Table
        from docx.text.paragraph import Paragraph
    except ImportError as exc:
        raise ParserError("缺少 python-docx，无法解析 DOCX") from exc

    document = Document(path)
    sections: list[Section] = []
    heading = path.stem

    def add_table(table: Table) -> None:
        rows: list[str] = []
        for row in table.rows:
            values = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if values:
                rows.append(" | ".join(values))
        if rows:
            sections.append(Section(_clean_text("\n".join(rows)), section=heading or "表格"))

    try:
        blocks: Iterable = document.iter_inner_content()
    except AttributeError:
        blocks = list(document.paragraphs) + list(document.tables)

    for block in blocks:
        if isinstance(block, Paragraph):
            text = block.text.strip()
            if not text:
                continue
            style = (block.style.name or "").lower() if block.style else ""
            if style.startswith("heading") or style.startswith("标题"):
                heading = text
            sections.append(Section(text, section=heading))
        elif isinstance(block, Table):
            add_table(block)

    return sections


def _read_pptx(path: Path) -> list[Section]:
    try:
        from pptx import Presentation
    except ImportError as exc:
        raise ParserError("缺少 python-pptx，无法解析 PPTX") from exc

    presentation = Presentation(path)
    sections: list[Section] = []
    for slide_index, slide in enumerate(presentation.slides, start=1):
        parts: list[str] = []
        for shape in slide.shapes:
            if getattr(shape, "has_text_frame", False) and shape.text.strip():
                parts.append(shape.text.strip())
            if getattr(shape, "has_table", False):
                for row in shape.table.rows:
                    values = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                    if values:
                        parts.append(" | ".join(values))
        notes = ""
        try:
            notes = slide.notes_slide.notes_text_frame.text.strip()
        except Exception:
            notes = ""
        if notes:
            parts.append(f"备注：{notes}")
        if parts:
            sections.append(
                Section(
                    _clean_text("\n".join(parts)),
                    page=slide_index,
                    section=f"幻灯片 {slide_index}",
                )
            )
    return sections


def _read_xlsx(path: Path) -> list[Section]:
    try:
        import openpyxl
    except ImportError as exc:
        raise ParserError("缺少 openpyxl，无法解析 XLSX") from exc

    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    sections: list[Section] = []
    try:
        for sheet in workbook.worksheets:
            rows: list[str] = []
            for row_index, row in enumerate(sheet.iter_rows(values_only=True)):
                if row_index >= MAX_SHEET_ROWS:
                    break
                values = [str(value).strip() for value in row[:50] if value is not None and str(value).strip()]
                if values:
                    rows.append(" | ".join(values))
            if rows:
                sections.append(Section(_clean_text("\n".join(rows)), section=sheet.title))
    finally:
        workbook.close()
    return sections


def _read_xls(path: Path) -> list[Section]:
    try:
        import xlrd
    except ImportError as exc:
        raise ParserError("缺少 xlrd，无法解析 XLS") from exc

    workbook = xlrd.open_workbook(path)
    sections: list[Section] = []
    for sheet in workbook.sheets():
        rows: list[str] = []
        for row_index in range(min(sheet.nrows, MAX_SHEET_ROWS)):
            values = [
                str(sheet.cell_value(row_index, column)).strip()
                for column in range(min(sheet.ncols, 50))
                if str(sheet.cell_value(row_index, column)).strip()
            ]
            if values:
                rows.append(" | ".join(values))
        if rows:
            sections.append(Section(_clean_text("\n".join(rows)), section=sheet.name))
    return sections


def _read_html(text: str, title: str = "") -> list[Section]:
    soup = BeautifulSoup(text, "lxml")
    for node in soup(["script", "style", "noscript", "template"]):
        node.decompose()
    page_title = title or (soup.title.get_text(strip=True) if soup.title else "")
    content = soup.get_text("\n")
    return [Section(_clean_text(content), section=page_title)] if content.strip() else []


def _read_mhtml(path: Path) -> list[Section]:
    raw = path.read_bytes()
    message = email.message_from_bytes(raw, policy=policy.default)
    html_parts: list[str] = []
    text_parts: list[str] = []
    for part in message.walk():
        content_type = part.get_content_type()
        if content_type == "text/html":
            try:
                html_parts.append(part.get_content())
            except Exception:
                continue
        elif content_type == "text/plain":
            try:
                text_parts.append(part.get_content())
            except Exception:
                continue
    if html_parts:
        return _read_html("\n".join(html_parts), path.stem)
    return [Section(_clean_text("\n".join(text_parts)), section=path.stem)] if text_parts else []


def _read_json(path: Path) -> list[Section]:
    data = json.loads(_read_text(path))

    def flatten(value, depth: int = 0) -> list[str]:
        if depth > 6 or len(lines) >= MAX_JSON_ITEMS:
            return lines
        if isinstance(value, dict):
            for key, item in value.items():
                if isinstance(item, (dict, list)):
                    lines.append(str(key))
                    flatten(item, depth + 1)
                else:
                    lines.append(f"{key}: {item}")
        elif isinstance(value, list):
            for item in value:
                flatten(item, depth + 1)
        else:
            lines.append(str(value))
        return lines

    lines: list[str] = []
    flatten(data)
    return [Section(_clean_text("\n".join(lines)), section=path.stem)]


def parse_file(path: Path, filename: str, ocr_enabled: bool = False) -> list[Section]:
    extension = Path(filename).suffix.lower()
    suffix = path.suffix.lower() or extension

    if suffix == ".pdf":
        return _read_pdf(path, ocr_enabled=ocr_enabled)
    if suffix == ".docx":
        return _read_docx(path)
    if suffix == ".pptx":
        return _read_pptx(path)
    if suffix == ".xlsx":
        return _read_xlsx(path)
    if suffix == ".xls":
        return _read_xls(path)
    if suffix == ".csv":
        return _read_csv(path)
    if suffix in {".md", ".markdown"}:
        return _read_markdown(path)
    if suffix in {".txt", ".text"}:
        return [Section(_clean_text(_read_text(path)), section=Path(filename).stem)]
    if suffix in {".html", ".htm"}:
        return _read_html(_read_text(path), Path(filename).stem)
    if suffix == ".mhtml":
        return _read_mhtml(path)
    if suffix == ".json":
        return _read_json(path)

    guessed = mimetypes.guess_type(filename)[0] or ""
    if guessed.startswith("text/"):
        return [Section(_clean_text(_read_text(path)), section=Path(filename).stem)]
    raise UnsupportedFileType(f"暂不支持的文件类型：{suffix or '未知'}")


def _validate_public_url(url: str, allow_private: bool) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ParserError("只支持 http/https 链接")
    if not parsed.hostname or parsed.username or parsed.password:
        raise ParserError("链接格式不合法")
    if allow_private:
        return
    try:
        addresses = socket.getaddrinfo(parsed.hostname, None)
    except socket.gaierror as exc:
        raise ParserError("无法解析链接域名") from exc
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            raise ParserError("出于安全原因，不允许抓取内网地址")


def parse_url(url: str, timeout_seconds: int = 20, allow_private: bool = False) -> list[Section]:
    _validate_public_url(url, allow_private)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (compatible; HyperCortexRAG/1.0; +https://github.com/lzqstc/Hypercortex)"
        )
    }
    with httpx.Client(follow_redirects=True, timeout=timeout_seconds, headers=headers) as client:
        response = client.get(url)
        response.raise_for_status()
    content_type = response.headers.get("content-type", "")
    if "html" not in content_type and "text" not in content_type:
        raise ParserError(f"链接返回的内容类型不支持：{content_type}")

    title = ""
    text = ""
    try:
        import trafilatura

        metadata = trafilatura.extract_metadata(response.text)
        title = metadata.title if metadata and metadata.title else ""
        text = trafilatura.extract(
            response.text,
            include_links=False,
            include_tables=True,
            include_comments=False,
            favor_precision=True,
        ) or ""
    except Exception:
        text = ""

    if not text.strip():
        sections = _read_html(response.text, title=title or url)
        return sections
    return [Section(_clean_text(text[:MAX_TEXT_CHARS]), section=title or url)]
