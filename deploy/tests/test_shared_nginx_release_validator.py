from pathlib import Path
import subprocess
import sys

import pytest

from deploy.shared_nginx_release_validator import validate_nginx_template


FIXTURE = Path(__file__).with_name("fixtures") / "shared-production.conf.template"


def fixture_text() -> str:
    return FIXTURE.read_text(encoding="utf-8")


def test_accepts_real_equivalent_shared_production_template():
    assert validate_nginx_template(fixture_text()) == []


@pytest.mark.parametrize(
    ("duplicate_block", "expected_domain"),
    [
        (
            "server { server_name hr.aurora-tek.cn; location ^~ /api/ { proxy_pass http://api:8000; } }",
            "hr.aurora-tek.cn",
        ),
        (
            "server { server_name aurora-tek.cn; location / { proxy_pass http://aurora-web:3000; } }",
            "aurora-tek.cn",
        ),
    ],
)
def test_rejects_duplicate_protected_server_blocks(duplicate_block, expected_domain):
    errors = validate_nginx_template(f"{fixture_text()}\n{duplicate_block}\n")
    assert f"duplicate_server_name:{expected_domain}" in errors


def test_requires_hr_spa_root_try_files():
    text = fixture_text().replace(
        "    location / {\n        try_files $uri $uri/ /index.html;\n    }\n",
        "",
        1,
    )
    assert validate_nginx_template(text) == ["wrong_spa_root:hr.aurora-tek.cn"]


def test_requires_hr_api_prefix_to_use_caret_tilde_and_api_upstream():
    text = fixture_text().replace("location ^~ /api/", "location /api/", 1)
    assert validate_nginx_template(text) == ["wrong_api_route:hr.aurora-tek.cn"]


def test_caret_tilde_api_prefix_cannot_be_overridden_by_regex_location():
    text = fixture_text().replace(
        "    location /health/ {",
        "    location ~ ^/api/ {\n"
        "        proxy_pass http://wrong:8000;\n"
        "    }\n\n"
        "    location /health/ {",
        1,
    )
    assert validate_nginx_template(text) == []


def test_rejects_wrong_exact_api_upstream():
    text = fixture_text().replace(
        "location = /api/v1/auth/login {\n"
        "        limit_req zone=login_per_ip burst=20 nodelay;\n"
        "        proxy_pass http://api:8000;",
        "location = /api/v1/auth/login {\n"
        "        limit_req zone=login_per_ip burst=20 nodelay;\n"
        "        proxy_pass http://wrong:8000;",
        1,
    )
    assert validate_nginx_template(text) == [
        "wrong_exact_api_upstream:/api/v1/auth/login"
    ]


def test_accepts_exact_api_location_with_nested_if_and_direct_proxy():
    text = fixture_text().replace(
        "        limit_req zone=login_per_ip burst=20 nodelay;\n"
        "        proxy_pass http://api:8000;",
        "        if ($request_method = OPTIONS) { return 204; }\n"
        "        proxy_pass http://api:8000;",
        1,
    )
    assert validate_nginx_template(text) == []


def test_rejects_website_root_with_wrong_upstream():
    text = fixture_text().replace(
        "proxy_pass http://aurora-web:3000;",
        "proxy_pass http://wrong:3000;",
        1,
    )
    assert validate_nginx_template(text) == [
        "wrong_upstream:aurora-tek.cn",
        "wrong_upstream:www.aurora-tek.cn",
    ]


def test_rejects_template_that_drops_website_route():
    website_server = fixture_text().split("\nserver {", 2)[-1]
    text = fixture_text()[: -(len(website_server) + len("\nserver {"))]
    assert validate_nginx_template(text) == [
        "missing_server_name:aurora-tek.cn",
        "missing_server_name:www.aurora-tek.cn",
    ]


def test_cli_reports_only_error_codes_without_template_contents(tmp_path):
    template = tmp_path / "nginx.conf"
    template.write_text(
        fixture_text().replace("server_name aurora-tek.cn www.aurora-tek.cn;", ""),
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "deploy.shared_nginx_release_validator",
            "--nginx-template",
            str(template),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert result.stderr.splitlines() == [
        "missing_server_name:aurora-tek.cn",
        "missing_server_name:www.aurora-tek.cn",
    ]
    assert "proxy_pass" not in result.stderr


def test_cli_accepts_real_equivalent_fixture_without_stderr():
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "deploy.shared_nginx_release_validator",
            "--nginx-template",
            str(FIXTURE),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert result.stderr == ""
