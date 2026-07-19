import subprocess
import sys

from deploy.shared_nginx_release_validator import validate_nginx_template


def test_accepts_shared_hr_and_website_routes():
    text = """
    server { server_name hr.aurora-tek.cn; location / { proxy_pass http://api:8000; } }
    server { server_name aurora-tek.cn www.aurora-tek.cn; location / { proxy_pass http://aurora-web:3000; } }
    """
    assert validate_nginx_template(text) == []


def test_rejects_template_that_drops_website_route():
    text = "server { server_name hr.aurora-tek.cn; location / { proxy_pass http://api:8000; } }"
    assert validate_nginx_template(text) == [
        "missing_server_name:aurora-tek.cn",
        "missing_server_name:www.aurora-tek.cn",
    ]


def test_keeps_nested_location_inside_server_block():
    text = """
    server {
        server_name hr.aurora-tek.cn;
        location / {
            if ($request_method = OPTIONS) { return 204; }
            proxy_pass http://api:8000;
        }
    }
    server { server_name aurora-tek.cn www.aurora-tek.cn; location / { proxy_pass http://aurora-web:3000; } }
    """
    assert validate_nginx_template(text) == []


def test_reports_wrong_upstream_for_named_route():
    text = """
    server { server_name hr.aurora-tek.cn; location / { proxy_pass http://wrong:8000; } }
    server { server_name aurora-tek.cn www.aurora-tek.cn; location / { proxy_pass http://aurora-web:3000; } }
    """
    assert validate_nginx_template(text) == ["wrong_upstream:hr.aurora-tek.cn"]


def test_rejects_correct_upstream_in_non_root_location():
    text = """
    server {
        server_name hr.aurora-tek.cn;
        location / { proxy_pass http://aurora-web:3000; }
        location /health { proxy_pass http://api:8000; }
    }
    server { server_name aurora-tek.cn www.aurora-tek.cn; location / { proxy_pass http://aurora-web:3000; } }
    """
    assert validate_nginx_template(text) == ["wrong_upstream:hr.aurora-tek.cn"]


def test_cli_reports_only_error_codes_without_template_contents(tmp_path):
    template = tmp_path / "nginx.conf"
    template.write_text(
        "server { server_name hr.aurora-tek.cn; location / { proxy_pass http://api:8000; } }",
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
    assert "hr.aurora-tek.cn" not in result.stderr


def test_cli_accepts_valid_template_without_stderr(tmp_path):
    template = tmp_path / "nginx.conf"
    template.write_text(
        """
        server { server_name hr.aurora-tek.cn; location / { proxy_pass http://api:8000; } }
        server { server_name aurora-tek.cn www.aurora-tek.cn; location / { proxy_pass http://aurora-web:3000; } }
        """,
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
    assert result.returncode == 0
    assert result.stderr == ""
