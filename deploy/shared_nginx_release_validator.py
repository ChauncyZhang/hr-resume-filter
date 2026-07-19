"""Validate the routes inherited by the shared production Nginx template."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys


_SERVER_BLOCK = re.compile(r"(?m)(?:^|[{};])\s*server\s*\{")
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


def _proxy_passes(block: str) -> list[str]:
    return [value.strip() for value in _PROXY_PASS_DIRECTIVE.findall(block)]


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
        elif not any(upstream in _proxy_passes(block) for block in named):
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
