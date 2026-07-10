# macOS 使用说明

## 启动

双击：

```text
Mac用户点我启动.command
```

脚本会自动：

1. 进入工具目录
2. 检查 `python3`
3. 首次运行时创建 `.venv`
4. 安装 PDF/DOCX 解析依赖
5. 启动本地网页
6. 自动打开浏览器访问 `http://127.0.0.1:8765`

## 第一次运行提示无权限

打开“终端”，进入工具目录后执行：

```bash
chmod +x Mac用户点我启动.command
```

然后再双击。

## macOS 安全提示

如果系统提示：

```text
Apple 无法验证是否包含可能危害 Mac 安全或泄露隐私的恶意软件
```

这是 macOS Gatekeeper 对下载文件加了隔离标记。打开“终端”，进入解压后的工具目录，执行：

```bash
xattr -dr com.apple.quarantine .
chmod +x Mac用户点我启动.command
```

然后再双击 `Mac用户点我启动.command`。

## Python 要求

需要 Python 3.10 或更高版本。

推荐安装地址：

```text
https://www.python.org/downloads/macos/
```

## 停止工具

关闭启动脚本打开的终端窗口即可。
