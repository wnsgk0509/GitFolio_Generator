"""Send generated portfolio markdown to Notion as native blocks."""

from __future__ import annotations

import re
from typing import Any

from notion_client import Client
from notion_client.errors import APIResponseError

BLOCKS_PER_REQUEST = 100
RICH_TEXT_LIMIT = 2000
NOTION_LANGUAGES = {
    "python": "python",
    "py": "python",
    "js": "javascript",
    "javascript": "javascript",
    "ts": "typescript",
    "typescript": "typescript",
    "json": "json",
    "bash": "bash",
    "sh": "shell",
    "shell": "shell",
    "md": "markdown",
    "markdown": "markdown",
    "yaml": "yaml",
    "yml": "yaml",
    "html": "html",
    "css": "css",
    "sql": "sql",
    "text": "plain text",
}


def send_markdown_to_notion(
    notion_token: str,
    target: str,
    markdown: str,
    page_title: str = "GitFolio 포트폴리오",
) -> str:
    """Insert markdown as Notion blocks into a page or as a new database page.

    Returns the destination page URL.
    """
    if not notion_token:
        raise ValueError("Notion Integration Token이 필요합니다.")
    if not target.strip():
        raise ValueError("Notion 페이지 또는 데이터베이스 ID/URL이 필요합니다.")
    if not markdown.strip():
        raise ValueError("전송할 포트폴리오가 없습니다.")

    client = Client(auth=notion_token)
    target_id = parse_notion_id(target)
    blocks = markdown_to_blocks(markdown)
    if not blocks:
        raise RuntimeError("노션 블록으로 변환된 내용이 없습니다.")

    kind = _detect_parent_kind(client, target_id)
    try:
        if kind == "database":
            page = client.pages.create(
                parent={"database_id": target_id},
                properties=_database_title_properties(client, target_id, page_title),
                children=blocks[:BLOCKS_PER_REQUEST],
            )
            remaining = blocks[BLOCKS_PER_REQUEST:]
            page_id = page["id"]
        else:
            client.blocks.children.append(
                block_id=target_id,
                children=blocks[:BLOCKS_PER_REQUEST],
            )
            remaining = blocks[BLOCKS_PER_REQUEST:]
            page_id = target_id
            page = client.pages.retrieve(page_id)

        _append_remaining(client, page_id, remaining)
    except APIResponseError as exc:
        _raise_notion_error(exc)

    return str(page.get("url") or f"https://www.notion.so/{page_id.replace('-', '')}")


def parse_notion_id(raw: str) -> str:
    """Accept a Notion URL or UUID and return a dashed UUID."""
    text = raw.strip()
    hex_only = re.sub(r"[^0-9a-fA-F]", "", text)
    if len(hex_only) < 32:
        raise ValueError(
            "유효한 Notion 페이지/데이터베이스 URL 또는 ID가 아닙니다."
        )
    hex_id = hex_only[-32:]
    return (
        f"{hex_id[0:8]}-{hex_id[8:12]}-{hex_id[12:16]}-"
        f"{hex_id[16:20]}-{hex_id[20:32]}"
    )


def markdown_to_blocks(markdown: str) -> list[dict[str, Any]]:
    """Convert GitFolio markdown into Notion block objects."""
    lines = markdown.replace("\r\n", "\n").split("\n")
    blocks: list[dict[str, Any]] = []
    paragraph: list[str] = []
    in_code = False
    code_lang = "plain text"
    code_lines: list[str] = []

    def flush_paragraph() -> None:
        text = " ".join(part.strip() for part in paragraph if part.strip())
        paragraph.clear()
        if text:
            blocks.append(_block("paragraph", text))

    for line in lines:
        if line.startswith("```"):
            if in_code:
                blocks.append(_code_block("\n".join(code_lines), code_lang))
                code_lines = []
                in_code = False
                code_lang = "plain text"
            else:
                flush_paragraph()
                in_code = True
                fence = line[3:].strip().lower()
                code_lang = NOTION_LANGUAGES.get(fence, "plain text")
            continue

        if in_code:
            code_lines.append(line)
            continue

        stripped = line.strip()
        if not stripped:
            flush_paragraph()
            continue
        if stripped == "---":
            flush_paragraph()
            blocks.append({"object": "block", "type": "divider", "divider": {}})
            continue

        heading = re.match(r"^(#{1,3})\s+(.+)$", stripped)
        if heading:
            flush_paragraph()
            level = len(heading.group(1))
            key = f"heading_{level}"
            blocks.append(_block(key, heading.group(2).strip()))
            continue

        bullet = re.match(r"^[-*]\s+(.+)$", stripped)
        if bullet:
            flush_paragraph()
            blocks.append(_block("bulleted_list_item", bullet.group(1).strip()))
            continue

        numbered = re.match(r"^\d+\.\s+(.+)$", stripped)
        if numbered:
            flush_paragraph()
            blocks.append(_block("numbered_list_item", numbered.group(1).strip()))
            continue

        paragraph.append(stripped)

    if in_code:
        blocks.append(_code_block("\n".join(code_lines), code_lang))
    else:
        flush_paragraph()
    return blocks


def _block(block_type: str, text: str) -> dict[str, Any]:
    return {
        "object": "block",
        "type": block_type,
        block_type: {"rich_text": _rich_text(text)},
    }


def _code_block(text: str, language: str) -> dict[str, Any]:
    content = text if text else " "
    rich: list[dict[str, Any]] = []
    for i in range(0, len(content), RICH_TEXT_LIMIT):
        rich.append(
            {
                "type": "text",
                "text": {"content": content[i : i + RICH_TEXT_LIMIT]},
            }
        )
    return {
        "object": "block",
        "type": "code",
        "code": {"rich_text": rich, "language": language},
    }


def _rich_text(text: str) -> list[dict[str, Any]]:
    pieces: list[dict[str, Any]] = []
    pattern = re.compile(r"(\*\*[^*]+\*\*|`[^`]+`|\*[^*]+\*)")
    cursor = 0
    for match in pattern.finditer(text):
        if match.start() > cursor:
            pieces.extend(_plain_chunks(text[cursor : match.start()]))
        token = match.group(0)
        if token.startswith("**"):
            pieces.extend(_plain_chunks(token[2:-2], bold=True))
        elif token.startswith("`"):
            pieces.extend(_plain_chunks(token[1:-1], code=True))
        else:
            pieces.extend(_plain_chunks(token[1:-1], italic=True))
        cursor = match.end()
    if cursor < len(text):
        pieces.extend(_plain_chunks(text[cursor:]))
    return pieces or _plain_chunks("")


def _plain_chunks(
    text: str,
    *,
    bold: bool = False,
    italic: bool = False,
    code: bool = False,
) -> list[dict[str, Any]]:
    if text == "":
        return []
    annotations = {
        "bold": bold,
        "italic": italic,
        "strikethrough": False,
        "underline": False,
        "code": code,
        "color": "default",
    }
    chunks: list[dict[str, Any]] = []
    for i in range(0, len(text), RICH_TEXT_LIMIT):
        chunks.append(
            {
                "type": "text",
                "text": {"content": text[i : i + RICH_TEXT_LIMIT]},
                "annotations": annotations,
            }
        )
    return chunks


def _detect_parent_kind(client: Client, target_id: str) -> str:
    try:
        client.pages.retrieve(page_id=target_id)
        return "page"
    except APIResponseError as page_exc:
        status = getattr(page_exc, "status", None)
        if status in (401, 403, "unauthorized", "restricted_resource"):
            _raise_notion_error(page_exc)
    try:
        client.databases.retrieve(database_id=target_id)
        return "database"
    except APIResponseError as exc:
        _raise_notion_error(exc)
    raise RuntimeError("Notion 대상을 확인할 수 없습니다.")


def _database_title_properties(
    client: Client,
    database_id: str,
    title: str,
) -> dict[str, Any]:
    database = client.databases.retrieve(database_id=database_id)
    properties = database.get("properties") or {}
    title_name = next(
        (name for name, prop in properties.items() if prop.get("type") == "title"),
        None,
    )
    if not title_name:
        raise RuntimeError("데이터베이스에 제목(title) 속성이 없습니다.")
    return {
        title_name: {
            "title": [{"type": "text", "text": {"content": title[:2000]}}],
        }
    }


def _append_remaining(client: Client, page_id: str, blocks: list[dict[str, Any]]) -> None:
    for i in range(0, len(blocks), BLOCKS_PER_REQUEST):
        chunk = blocks[i : i + BLOCKS_PER_REQUEST]
        if chunk:
            client.blocks.children.append(block_id=page_id, children=chunk)


def _raise_notion_error(exc: APIResponseError) -> None:
    status = getattr(exc, "status", None) or getattr(exc, "code", None)
    if status in (401, "unauthorized"):
        raise RuntimeError("Notion 인증에 실패했습니다. Integration Token을 확인하세요.") from exc
    if status in (404, "object_not_found"):
        raise RuntimeError(
            "페이지/데이터베이스를 찾을 수 없습니다. "
            "URL이 맞는지, Integration을 해당 페이지에 연결했는지 확인하세요."
        ) from exc
    if status in (403, "restricted_resource"):
        raise RuntimeError(
            "Notion 권한이 없습니다. 페이지에서 Connection으로 Integration을 초대해 주세요."
        ) from exc
    raise RuntimeError(f"Notion API 오류: {exc}") from exc
