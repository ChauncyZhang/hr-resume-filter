"""Validate the routes inherited by the shared production Nginx template."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys


_SERVER_BLOCK = re.compile(r"(?m)(?:^|[{};])\s*server\s*\{")
_LOCATION_BLOCK = re.compile(
    r"(?m)(?:^|[{};])\s*location\s+([^\s{]+)\s*\{"
)
_SERVER_NAME_DIRECTIVE = re.compile(
    r"(?m)(?:^|[{};])\s*server_name\s+([^;{}]*);"
)
_PROXY_PASS_DIRECTIVE = re.compile(r"(?m)(?:^|[{};])\s*proxy_pass\s+([^;{}]+);")


def _without_comments(text: str) -> str:
    return re.sub(r"#[^\r\n]*", "", text)


def _matching_brace(text: str, opening: int) -> int | None:
    depth = 0
    quote: str | None = None
    escaped = False
    for index in range(opening, len(text)):
        character = text[index]
        if quote is not None:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = None
            continue
        if character in ('"', "'"):
            quote = character
        elif character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                return index
    return None


def extract_server_blocks(text: str) -> list[str]:
    """Return complete server blocks, including nested location blocks."""
    text = _without_comments(text)
    blocks: list[str] = []
    for match in _SERVER_BLOCK.finditer(text):
        opening = text.find("{", match.start(), match.end())
        closing = _matching_brace(text, opening)
        if closing is not None:
            blocks.append(text[match.start() : closing + 1])
    return blocks


def server_names(block: str) -> list[str]:
    """Return names declared by server_name directives in a server block."""
    return [
        name
        for directive in _SERVER_NAME_DIRECTIVE.findall(block)
        for name in directive.split()
    ]


def extract_location_blocks(server_block: str) -> list[tuple[str, str]]:
    """Return location paths and their complete bodies from a server block."""
    server_block = _without_comments(server_block)
    locations: list[tuple[str, str]] = []
    for match in _LOCATION_BLOCK.finditer(server_block):
        opening = server_block.find("{", match.start(), match.end())
        closing = _matching_brace(server_block, opening)
        if closing is not None:
            locations.append(
                (match.group(1), server_block[opening + 1 : closing])
            )
    return locations


def _brace_depth_through(text: str, index: int) -> int:
    depth = 0
    quote: str | None = None
    escaped = False
    for character in text[: index + 1]:
        if quote is not None:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = None
            continue
        if character in ('"', "'"):
            quote = character
        elif character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
    return depth


def _direct_proxy_passes(location_body: str) -> list[str]:
    """Return proxy_pass values declared directly in a location body."""
    location_body = _without_comments(location_body)
    return [
        match.group(1).strip()
        for match in _PROXY_PASS_DIRECTIVE.finditer(location_body)
        if _brace_depth_through(location_body, match.start()) == 0
    ]


def validate_nginx_template(text: str) -> list[str]:
    blocks = extract_server_blocks(text)
    routes = [
        ("hr.aurora-tek.cn", "http://api:8000"),
        ("aurora-tek.cn", "http://aurora-web:3000"),
        ("www.aurora-tek.cn", "http://aurora-web:3000"),
    ]
    errors: list[str] = []
    for name, upstream in routes:
        named = [block for block in blocks if name in server_names(block)]
        if not named:
            errors.append(f"missing_server_name:{name}")
        elif not any(
            upstream in _direct_proxy_passes(body)
            for block in named
            for path, body in extract_location_blocks(block)
            if path == "/"
        ):
            errors.append(f"wrong_upstream:{name}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--nginx-template", type=Path, required=True)
    args = parser.parse_args()
    try:
        text = args.nginx_template.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        print("invalid_nginx_template_file", file=sys.stderr)
        return 1

    errors = validate_nginx_template(text)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
