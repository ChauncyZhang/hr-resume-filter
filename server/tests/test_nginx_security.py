from pathlib import Path


def test_nginx_replaces_forwarded_chain_with_public_client() -> None:
    config = Path("deploy/nginx/default.conf").read_text(encoding="utf-8")
    assert "proxy_set_header X-Forwarded-For $remote_addr;" in config
    assert "$proxy_add_x_forwarded_for" not in config
