"""Optional local static-container/browser gate; never contacts production.

Set BRANDING_RUNTIME_IMAGE to an existing Nginx frontend image and
BRANDING_PRODUCT_ROOT to a built public checkout. The image serves only that
checkout's dist plus read-only branding assets; no real API is used.
"""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
from urllib.error import URLError
from urllib.request import urlopen
from uuid import uuid4

import pytest


ROOT = Path(__file__).resolve().parents[2]
PRODUCT = Path(os.getenv("BRANDING_PRODUCT_ROOT", str(ROOT / "product")))
pytestmark = pytest.mark.skipif(not os.getenv("BRANDING_RUNTIME_IMAGE"), reason="Local branding runtime image not configured")


def run(*args, timeout=30):
    result = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", timeout=timeout)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


@pytest.mark.parametrize("custom", [False, True])
def test_real_read_only_brand_mounts_apply_to_login_title_icon_and_mobile(tmp_path, custom):
    dist = (PRODUCT / "frontend/dist").resolve()
    assert (dist / "index.html").is_file(), "Build the current public frontend first"
    # A read-only parent bind needs its nested mount point to exist beforehand.
    staged_dist = tmp_path / "dist"
    shutil.copytree(dist, staged_dist)
    (staged_dist / "branding").mkdir(exist_ok=True)
    source = ROOT / "deploy/branding.json" if custom else PRODUCT / "frontend/public/branding.json"
    branding = json.loads(source.read_text(encoding="utf-8"))
    config = tmp_path / "static.conf"
    config.write_text("""server {
      listen 8080;
      root /usr/share/nginx/html;
      include /etc/nginx/snippets/security-headers.conf;
      location = /branding.json { add_header Cache-Control no-store; try_files $uri =404; }
      location / { try_files $uri $uri/ /index.html; }
    }
    """, encoding="utf-8")
    script = tmp_path / "browser.cjs"
    script.write_text("""
const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs/promises');
const {chromium} = require(path.join(process.argv[2], 'frontend/node_modules/playwright'));
(async () => {
 const brand = JSON.parse(process.argv[4]);
 const browser = await chromium.launch({headless:true});
 try {
  for (const width of [1440,390]) {
   const page = await browser.newPage({viewport:{width,height:900}});
   await page.route('**/api/**', route => route.fulfill({status:401,json:{code:'session_invalid'}}));
   await page.goto(process.argv[3]);
   await page.getByRole('heading',{name:'登录工作台',exact:true}).waitFor();
   await page.getByText(brand.name + ' · 候选人全流程招聘平台',{exact:true}).waitFor();
   assert.equal(await page.title(), brand.name + ' | 候选人全流程招聘平台');
   const mark = page.locator('.login-mark img');
   await mark.waitFor();
   assert.equal(await mark.getAttribute('alt'),brand.name);
   await page.waitForFunction(() => document.querySelector('.login-mark img')?.naturalWidth > 0);
   assert.equal(new URL(await page.locator('link[rel="icon"]').getAttribute('href'),page.url()).pathname,brand.favicon_url || brand.logo_url);
   const box = await page.locator('.login-heading').boundingBox();
   assert.ok(box.x >= -1 && box.x + box.width <= width + 1);
   await fs.mkdir(process.argv[5],{recursive:true});
   await page.screenshot({path:path.join(process.argv[5],process.argv[6]+'-'+width+'.png'),fullPage:true});
   await page.close();
  }
 } finally {await browser.close();}
})().catch(error => {console.error(error); process.exitCode=1;});
    """, encoding="utf-8")
    name = "branding-runtime-" + uuid4().hex[:10]
    try:
        run("docker", "run", "--detach", "--name", name, "--read-only",
            "--tmpfs", "/var/cache/nginx", "--tmpfs", "/var/run", "--tmpfs", "/tmp",
            "--publish", "127.0.0.1::8080",
            "--mount", f"type=bind,source={staged_dist},target=/usr/share/nginx/html,readonly",
            "--mount", f"type=bind,source={source.resolve()},target=/usr/share/nginx/html/branding.json,readonly",
            "--mount", f"type=bind,source={ROOT / 'deploy/branding'},target=/usr/share/nginx/html/branding,readonly",
            "--mount", f"type=bind,source={config},target=/etc/nginx/conf.d/default.conf,readonly",
            os.environ["BRANDING_RUNTIME_IMAGE"])
        port = re.fullmatch(r"127\.0\.0\.1:(\d+)", run("docker", "port", name, "8080/tcp"))
        assert port
        url = f"http://127.0.0.1:{port[1]}/"
        deadline = time.monotonic() + 15
        while True:
            try:
                with urlopen(url + "branding.json", timeout=2) as response:
                    assert json.load(response) == branding
                break
            except (URLError, ConnectionError):
                if time.monotonic() >= deadline:
                    pytest.fail("Local static container did not become ready")
                time.sleep(0.1)
        with urlopen(url.rstrip("/") + branding["logo_url"], timeout=3) as response:
            assert response.status == 200
        run("node", str(script), str(PRODUCT.resolve()), url, json.dumps(branding),
            str(ROOT / ".tmp/branding-runtime"), "custom" if custom else "default", timeout=90)
    finally:
        # Only this test's random container, with synthetic content, is removed.
        subprocess.run(["docker", "rm", "--force", name], capture_output=True, timeout=15)
