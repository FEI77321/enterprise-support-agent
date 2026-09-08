# 模块职责：将解析后的文档按标题和长度生成可追溯的父子 KnowledgeChunk。

from __future__ import annotations
import re
from dataclasses import dataclass
from hashlib import sha256
from typing import Sequence

from app.knowledge_models import (
    ChunkKind,
    Document,
    KnowledgeChunk,
    PageMapEntry,
    ParsedDocument,
    ParseStatus,
)


@dataclass(frozen=True)
class HeadingSection:
    """一个按 Markdown 标题识别出的逻辑章节。"""

    heading_path: list[str]
    char_start: int
    char_end: int
    content: str

HEADING_PATTERN = re.compile(
    r"^(#{1,6})[ \t]+(.+?)\s*$",
    re.MULTILINE,
)

def build_heading_sections(
    markdown_content: str,
) -> list[HeadingSection]:
    """按 Markdown 标题将文本拆成最细粒度的逻辑章节。"""

    matches = list(HEADING_PATTERN.finditer(markdown_content))

    if not matches:
        content = markdown_content.strip()

        if not content:
            return []

        char_start = len(markdown_content) - len(
            markdown_content.lstrip()
        )
        char_end = char_start + len(content)

        return [
            HeadingSection(
                heading_path=[],
                char_start=char_start,
                char_end=char_end,
                content=content,
            )
        ]

    headings: list[dict[str, object]] = []
    heading_stack: list[tuple[int, str]] = []

    for match in matches:
        level = len(match.group(1))
        title = match.group(2).strip()

        while heading_stack and heading_stack[-1][0] >= level:
            heading_stack.pop()

        heading_stack.append((level, title))

        headings.append(
            {
                "level": level,
                "char_start": match.start(),
                "heading_path": [
                    item_title
                    for _, item_title in heading_stack
                ],
            }
        )

    sections: list[HeadingSection] = []

    prefix_content = markdown_content[: matches[0].start()]
    if prefix_content.strip():
        char_start = len(prefix_content) - len(
            prefix_content.lstrip()
        )
        content = prefix_content.strip()

        sections.append(
            HeadingSection(
                heading_path=[],
                char_start=char_start,
                char_end=char_start + len(content),
                content=content,
            )
        )

    for index, heading in enumerate(headings):
        level = heading["level"]
        char_start = heading["char_start"]

        assert isinstance(level, int)
        assert isinstance(char_start, int)

        char_end = len(markdown_content)

        for next_heading in headings[index + 1 :]:
            next_level = next_heading["level"]
            next_char_start = next_heading["char_start"]

            assert isinstance(next_level, int)
            assert isinstance(next_char_start, int)

            if next_level <= level:
                char_end = next_char_start
                break

        has_child_heading = any(
            isinstance(next_heading["level"], int)
            and next_heading["level"] > level
            and isinstance(next_heading["char_start"], int)
            and next_heading["char_start"] < char_end
            for next_heading in headings[index + 1 :]
        )

        if has_child_heading:
            continue

        raw_content = markdown_content[char_start:char_end]
        content = raw_content.strip()

        if not content:
            continue

        leading_whitespace = len(raw_content) - len(
            raw_content.lstrip()
        )
        section_char_start = char_start + leading_whitespace
        section_char_end = section_char_start + len(content)

        heading_path = heading["heading_path"]
        assert isinstance(heading_path, list)

        sections.append(
            HeadingSection(
                heading_path=heading_path,
                char_start=section_char_start,
                char_end=section_char_end,
                content=content,
            )
        )

    return sections


def split_text_with_overlap(
    text: str,
    chunk_size: int,
    chunk_overlap: int,
) -> list[tuple[int, int, str]]:
    """按自然边界切分文本，返回相对字符范围和子块内容。"""

    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than 0")

    if chunk_overlap < 0:
        raise ValueError(
            "chunk_overlap must be greater than or equal to 0"
        )

    if chunk_overlap >= chunk_size:
        raise ValueError(
            "chunk_overlap must be smaller than chunk_size"
        )

    if not text.strip():
        return []

    chunks: list[tuple[int, int, str]] = []
    natural_boundaries = "\n。！？；.!?; "
    sentence_boundaries = "\n。！？；.!?;"
    text_length = len(text)
    current_start = 0

    def find_overlap_start(
        current_chunk_start: int,
        desired_start: int,
        current_chunk_end: int,
    ) -> int:
        """在目标 overlap 起点前寻找更自然的重新开始位置。"""

        for boundary_index in range(
            desired_start - 1,
            current_chunk_start,
            -1,
        ):
            if text[boundary_index] in sentence_boundaries:
                candidate_start = boundary_index + 1

                while (
                    candidate_start < desired_start
                    and text[candidate_start].isspace()
                ):
                    candidate_start += 1

                return candidate_start

        for boundary_index in range(
            desired_start,
            current_chunk_end,
        ):
            if text[boundary_index] in sentence_boundaries:
                candidate_start = boundary_index + 1

                while (
                    candidate_start < current_chunk_end
                    and text[candidate_start].isspace()
                ):
                    candidate_start += 1

                return candidate_start

        for boundary_index in range(
            desired_start - 1,
            current_chunk_start,
            -1,
        ):
            if text[boundary_index].isspace():
                return boundary_index + 1

        return desired_start

    while current_start < text_length:
        max_end = min(
            current_start + chunk_size,
            text_length,
        )

        if max_end == text_length:
            raw_end = text_length
        else:
            min_natural_end = min(
                current_start + chunk_overlap + 1,
                max_end,
            )
            raw_end = max_end

            for candidate_end in range(
                max_end,
                min_natural_end - 1,
                -1,
            ):
                if text[candidate_end - 1] in natural_boundaries:
                    raw_end = candidate_end
                    break

        raw_content = text[current_start:raw_end]
        content = raw_content.strip()

        if content:
            leading_whitespace = len(raw_content) - len(
                raw_content.lstrip()
            )
            char_start = current_start + leading_whitespace
            char_end = char_start + len(content)

            chunks.append(
                (
                    char_start,
                    char_end,
                    content,
                )
            )

        if raw_end == text_length:
            break

        desired_start = raw_end - chunk_overlap
        next_start = find_overlap_start(
            current_chunk_start=current_start,
            desired_start=desired_start,
            current_chunk_end=raw_end,
        )

        if next_start <= current_start:
            next_start = raw_end

        current_start = next_start

    return chunks


def resolve_page_range(
    page_map: Sequence[PageMapEntry],
    char_start: int,
    char_end: int,
) -> tuple[int, int]:
    """根据字符范围推导来源页码区间。"""

    if char_start < 0:
        raise ValueError("char_start must be greater than or equal to 0")

    if char_end <= char_start:
        raise ValueError("char_end must be greater than char_start")

    if not page_map:
        raise ValueError(
            "cannot resolve page range without page_map"
        )

    overlapping_pages = [
        entry
        for entry in page_map
        if entry.char_start < char_end
        and entry.char_end > char_start
    ]

    if not overlapping_pages:
        raise ValueError(
            "chunk character range does not overlap any page_map entry"
        )

    return (
        min(entry.page_number for entry in overlapping_pages),
        max(entry.page_number for entry in overlapping_pages),
    )


def chunk_parsed_document(
    document: Document,
    parsed_document: ParsedDocument,
    child_chunk_size: int = 400,
    child_chunk_overlap: int = 60,
) -> list[KnowledgeChunk]:
    """将一个成功或部分成功的 ParsedDocument 转为父子 KnowledgeChunk。"""

    if parsed_document.document_id != document.document_id:
        raise ValueError(
            "parsed_document.document_id must match document.document_id"
        )

    if parsed_document.parse_status == ParseStatus.FAILED:
        return []

    markdown_content = parsed_document.markdown_content

    if not markdown_content or not markdown_content.strip():
        return []

    if not parsed_document.page_map:
        raise ValueError(
            "cannot chunk parsed content without page_map"
        )

    document_token = sha256(
        document.document_id.encode("utf-8")
    ).hexdigest()[:12]

    sections = build_heading_sections(markdown_content)
    chunks: list[KnowledgeChunk] = []

    for section_index, section in enumerate(sections, start=1):
        parent_chunk_id = (
            f"chunk_{document_token}_parent_{section_index:04d}"
        )

        parent_page_start, parent_page_end = resolve_page_range(
            page_map=parsed_document.page_map,
            char_start=section.char_start,
            char_end=section.char_end,
        )

        parent_chunk = KnowledgeChunk(
            chunk_id=parent_chunk_id,
            document_id=document.document_id,
            parsed_document_id=parsed_document.parsed_document_id,
            document_version=document.version,
            kind=ChunkKind.PARENT,
            heading_path=list(section.heading_path),
            page_start=parent_page_start,
            page_end=parent_page_end,
            content=section.content,
            content_hash=sha256(
                section.content.encode("utf-8")
            ).hexdigest(),
        )

        chunks.append(parent_chunk)

        child_slices = split_text_with_overlap(
            text=section.content,
            chunk_size=child_chunk_size,
            chunk_overlap=child_chunk_overlap,
        )

        for child_index, (
            relative_char_start,
            relative_char_end,
            child_content,
        ) in enumerate(child_slices, start=1):
            child_char_start = (
                section.char_start + relative_char_start
            )
            child_char_end = (
                section.char_start + relative_char_end
            )

            child_page_start, child_page_end = resolve_page_range(
                page_map=parsed_document.page_map,
                char_start=child_char_start,
                char_end=child_char_end,
            )

            child_chunk = KnowledgeChunk(
                chunk_id=(
                    f"{parent_chunk_id}:child:{child_index:04d}"
                ),
                document_id=document.document_id,
                parsed_document_id=parsed_document.parsed_document_id,
                document_version=document.version,
                kind=ChunkKind.CHILD,
                parent_chunk_id=parent_chunk_id,
                heading_path=list(section.heading_path),
                page_start=child_page_start,
                page_end=child_page_end,
                content=child_content,
                content_hash=sha256(
                    child_content.encode("utf-8")
                ).hexdigest(),
            )

            chunks.append(child_chunk)

    return chunks
