from __future__ import annotations

import re
from dataclasses import dataclass

from .parsers import Section


@dataclass
class Chunk:
    content: str
    page: int | None
    section: str
    index: int
    token_count: int


_SENTENCE_BOUNDARY = re.compile(r"(?<=[。！？!?；;\n])")
_WHITESPACE = re.compile(r"[ \t]+")


def _normalize(text: str) -> str:
    text = text.replace("\x00", " ")
    text = _WHITESPACE.sub(" ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _split_long_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    chunks: list[str] = []
    start = 0
    length = len(text)
    while start < length:
        end = min(start + chunk_size, length)
        chunks.append(text[start:end].strip())
        if end >= length:
            break
        start = max(end - overlap, start + 1)
    return [chunk for chunk in chunks if chunk]


def split_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    text = _normalize(text)
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]

    sentences = [part.strip() for part in _SENTENCE_BOUNDARY.split(text) if part.strip()]
    chunks: list[str] = []
    current = ""

    for sentence in sentences:
        if len(sentence) > chunk_size:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(_split_long_text(sentence, chunk_size, overlap))
            continue

        if not current:
            current = sentence
            continue

        if len(current) + len(sentence) <= chunk_size:
            current += sentence
            continue

        chunks.append(current)
        tail = current[-overlap:] if overlap > 0 else ""
        current = f"{tail}{sentence}"

        while len(current) > chunk_size:
            chunks.append(current[:chunk_size].strip())
            current = current[chunk_size - overlap :]

    if current.strip():
        chunks.append(current.strip())
    return [chunk for chunk in chunks if chunk]


def chunk_sections(
    sections: list[Section],
    chunk_size: int = 800,
    overlap: int = 120,
    min_chunk_chars: int = 30,
) -> list[Chunk]:
    chunks: list[Chunk] = []
    index = 0
    for section in sections:
        for piece in split_text(section.text, chunk_size=chunk_size, overlap=overlap):
            piece = piece.strip()
            if not piece:
                continue
            if len(piece) < min_chunk_chars:
                if chunks and chunks[-1].section == section.section:
                    previous = chunks[-1]
                    previous.content = f"{previous.content}\n{piece}".strip()
                    previous.token_count = len(previous.content)
                continue
            chunks.append(
                Chunk(
                    content=piece,
                    page=section.page,
                    section=section.section,
                    index=index,
                    token_count=len(piece),
                )
            )
            index += 1
    return chunks
