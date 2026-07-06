# Linux 部署说明

目标：把 HR 简历筛选工具部署到公司内网服务器，HR 用浏览器访问。

## 推荐架构

```text
HR 浏览器
  ↓ HTTPS / 内网域名
Nginx 反向代理 / 访问控制
  ↓ 127.0.0.1:8765
Python 本地服务
```

不要直接暴露到公网。简历包含个人信息，建议放在公司内网、VPN、堡垒机或 SSO 后面。

## 1. 准备目录

在服务器上创建服务用户和目录：

```bash
sudo useradd --system --home /opt/hr-resume-filter --shell /usr/sbin/nologin hr-resume
sudo mkdir -p /opt/hr-resume-filter
sudo chown -R hr-resume:hr-resume /opt/hr-resume-filter
```

把 `hr-resume-filter` 目录上传到：

```text
/opt/hr-resume-filter
```

## 2. 安装 Python 依赖

```bash
cd /opt/hr-resume-filter
sudo -u hr-resume python3 -m venv .venv
sudo -u hr-resume .venv/bin/pip install -r requirements.txt
```

## 3. 本地试运行

```bash
sudo -u hr-resume HR_RESUME_HOST=127.0.0.1 HR_RESUME_PORT=8765 .venv/bin/python web_app.py --no-browser
```

另开一个终端检查：

```bash
curl -I http://127.0.0.1:8765/
```

看到 `200 OK` 后停止试运行。

## 4. 配置 systemd

```bash
sudo cp deploy/linux/hr-resume-filter.service /etc/systemd/system/hr-resume-filter.service
sudo systemctl daemon-reload
sudo systemctl enable --now hr-resume-filter
sudo systemctl status hr-resume-filter
```

日志查看：

```bash
journalctl -u hr-resume-filter -f
```

## 5. 配置 Nginx

复制示例配置：

```bash
sudo cp deploy/linux/nginx-hr-resume-filter.conf /etc/nginx/sites-available/hr-resume-filter.conf
sudo ln -s /etc/nginx/sites-available/hr-resume-filter.conf /etc/nginx/sites-enabled/hr-resume-filter.conf
sudo nginx -t
sudo systemctl reload nginx
```

把 `server_name hr-resume.example.com;` 改成公司内网域名。

## 6. 安全建议

- 只在内网、VPN 或 SSO 后面开放。
- Nginx 增加 HTTPS。
- Nginx 增加 Basic Auth 或接公司统一登录。
- 不要把上传的简历长期落盘；当前服务只在临时目录解析，请保持这个设计。
- 控制服务器日志，避免记录简历原文和个人联系方式。

## 直连内网端口

如果暂时不用 Nginx，可以让服务监听所有网卡：

```bash
HR_RESUME_HOST=0.0.0.0 HR_RESUME_PORT=8765 ./start_linux.sh
```

然后 HR 访问：

```text
http://服务器IP:8765
```

这只适合临时内网测试，不建议长期生产使用。
