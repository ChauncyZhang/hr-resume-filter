"""Validate the routes inherited by the shared production Nginx template."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys


_SERVER_BLOCK = re.compile(r"(?m)(?:^|[{};])\s*server\s*\{")
_LOCATION_BLOCK = re.compile(
    r"(?m)(?:^|[{};])\s*location\s+"
    r"(?:(?P<modifier>=|\^~|~\*|~)\s+)?(?P<path>[^\s{]+)\s*\{"
)
_SERVER_NAME_DIRECTIVE = re.compile(
    r"(?m)(?:^|[{};])\s*server_name\s+([^;{}]*);"
)
_PROXY_PASS_DIRECTIVE = re.compile(r"(?m)(?:^|[{};])\s*proxy_pass\s+([^;{}]+);")
_TRY_FILES_DIRECTIVE = re.compile(r"(?m)(?:^|[{};])\s*try_files\s+([^;{}]+);")

_HR_DOMAIN = "hr.aurora-tek.cn"
_WEBSITE_DOMAINS = ("aurora-tek.cn", "www.aurora-tek.cn")
_API_UPSTREAM = "http://api:8000"
_WEBSITE_UPSTREAM = "http://aurora-web:3000"
_SPA_TRY_FILES = ("$uri", "$uri/", "/index.html")


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
        start = text.find("server", match.start(), match.end())
        opening = text.find("{", match.start(), match.end())
        closing = _matching_brace(text, opening)
        if closing is not None:
            blocks.append(text[start : closing + 1])
    return blocks


def server_names(block: str) -> list[str]:
    """Return names declared by server_name directives in a server block."""
    return [
        name
        for directive in _SERVER_NAME_DIRECTIVE.findall(block)
        for name in directive.split()
    ]


def extract_location_blocks(server_block: str) -> list[tuple[str | None, str, str]]:
    """Return modifier, path, and body for direct child location blocks."""
    server_block = _without_comments(server_block)
    locations: list[tuple[str | None, str, str]] = []
    for match in _LOCATION_BLOCK.finditer(server_block):
        if _brace_depth_through(server_block, match.start("path")) != 1:
            continue
        opening = server_block.find("{", match.start(), match.end())
        closing = _matching_brace(server_block, opening)
        if closing is not None:
            locations.append(
                (
                    match.group("modifier"),
                    match.group("path"),
                    server_block[opening + 1 : closing],
                )
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


def _direct_try_files(location_body: str) -> list[tuple[str, ...]]:
    """Return direct try_files argument lists from a location body."""
    location_body = _without_comments(location_body)
    return [
        tuple(match.group(1).split())
        for match in _TRY_FILES_DIRECTIVE.finditer(location_body)
        if _brace_depth_through(location_body, match.start()) == 0
    ]


def _has_proxy(
    locations: list[tuple[str | None, str, str]],
    *,
    modifier: str | None,
    path: str,
    upstream: str,
) -> bool:
    return any(
        candidate_modifier == modifier
        and candidate_path == path
        and upstream in _direct_proxy_passes(body)
        for candidate_modifier, candidate_path, body in locations
    )


def validate_nginx_template(text: str) -> list[str]:
    blocks = extract_server_blocks(text)
    errors: list[str] = []

    protected_domains = (_HR_DOMAIN, *_WEBSITE_DOMAINS)
    protected_blocks: dict[str, str] = {}
    for name in protected_domains:
        named = [block for block in blocks if name in server_names(block)]
        if not named:
            errors.append(f"missing_server_name:{name}")
        elif len(named) > 1:
            errors.append(f"duplicate_server_name:{name}")
        else:
            protected_blocks[name] = named[0]

    hr_block = protected_blocks.get(_HR_DOMAIN)
    if hr_block is not None:
        hr_locations = extract_location_blocks(hr_block)
        spa_roots = [
            body
            for modifier, path, body in hr_locations
            if modifier is None and path == "/"
        ]
        if not any(_SPA_TRY_FILES in _direct_try_files(body) for body in spa_roots):
            errors.append(f"wrong_spa_root:{_HR_DOMAIN}")

        if not _has_proxy(
            hr_locations,
            modifier="^~",
            path="/api/",
            upstream=_API_UPSTREAM,
        ):
            errors.append(f"wrong_api_route:{_HR_DOMAIN}")

        for modifier, path, body in hr_locations:
            if modifier == "=" and path.startswith("/api/"):
                if _API_UPSTREAM not in _direct_proxy_passes(body):
                    errors.append(f"wrong_exact_api_upstream:{path}")

    for name in _WEBSITE_DOMAINS:
        block = protected_blocks.get(name)
        if block is None:
            continue
        if not _has_proxy(
            extract_location_blocks(block),
            modifier=None,
            path="/",
            upstream=_WEBSITE_UPSTREAM,
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
