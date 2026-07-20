# 本地桌面简历筛选工具（旧版）

一个本地运行的简历初筛工具，面向 HR 日常批量筛选简历场景。

它支持上传岗位 JD 和多份简历，自动生成候选人排序结果；也可以选择接入 OpenAI 兼容接口、Ollama 等 LLM Provider 做语义评估。

## 产品边界

本 README 只描述根目录 `app/` 下的旧版本地桌面工具，包括下文的本地规则筛选、可选 LLM 配置和 CSV 输出。它与 `server/` 下的多人协作 ATS 是两个独立产品，桌面工具的规则、分数和人工操作流程不代表服务端当前行为。

服务端 ATS 的新筛选任务使用 LLM 作为唯一评分来源，并根据结果自动流转状态。服务端开发、配置和 LLM-only 筛选流程请从 [server/README.md](server/README.md) 开始。

## 重要说明

本项目只处理你已经合法获得的简历文件。

它不会自动登录招聘平台，不抓取网页，不绕过验证码，不批量获取未授权简历。请只用于候选人主动投递、企业后台合法导出、HR 手动下载或自建投递表单收集的简历。

## 普通用户怎么用

推荐使用 Release 或别人发给你的压缩包，而不是直接下载源码。

解压后目录里会看到：

```text
Windows用户点我启动.bat
Mac用户点我启动.command
app/
```

### Windows

双击：

```text
Windows用户点我启动.bat
```

如果拿到的是打包好的 Windows 交付包，Windows 用户不需要安装 Python。脚本会启动 `app/HRResumeFilter.exe`，然后自动打开浏览器：

```text
http://127.0.0.1:8765
```

### macOS

双击：

```text
Mac用户点我启动.command
```

macOS 脚本会自动创建本地 `.venv` 并安装依赖，但要求电脑里已经有 `python3`。

如果提示没有执行权限：

```bash
chmod +x Mac用户点我启动.command
```

如果出现“Apple 无法验证是否包含可能危害 Mac 安全或泄露隐私的恶意软件”，这是 macOS Gatekeeper 对下载脚本加了隔离标记。打开“终端”，进入解压后的工具目录，执行：

```bash
xattr -dr com.apple.quarantine .
chmod +x Mac用户点我启动.command
```

然后再双击 `Mac用户点我启动.command`。

## 页面使用流程

1. 点击右上角“设置”，配置是否启用 LLM、Provider、模型、Base URL 和 API Key。
2. 在“岗位 JD”区域填写岗位名称和 JD，点击“保存岗位”。
3. 后续使用时直接选择已保存岗位。
4. 在“简历文件”区域选择或拖入多份简历。
5. 点击“开始筛选”。
6. 在页面查看候选人卡片和排序结果。
7. 点击“下载 CSV”，用 Excel 打开结果。

工具内置了一个 AI 工程师 JD 示例，可以直接用于测试。

## 支持的文件

当前支持：

- `.txt`
- `.md`
- `.csv`
- `.pdf`
- `.docx`

PDF 通过 `pypdf` 读取文本层。扫描件、图片型简历、特殊编码 PDF 可能无法正常识别，后续需要接 OCR。

## LLM 配置

默认不开启 LLM。不开启时，系统只做本地规则筛选，不会把简历发送给任何模型服务。

开启 LLM 后，系统会把 JD、规则初筛结果和简历文本发送给你填写的模型服务。请确认该服务符合公司隐私和数据合规要求。

支持：

- OpenAI 兼容接口
- Ollama 本地接口
- 其他兼容 `/v1/chat/completions` 的服务

OpenAI 兼容接口示例：

```text
Provider: OpenAI 兼容接口
模型: gpt-4o-mini
Base URL: https://api.openai.com/v1
API Key: your-api-key
```

Ollama 示例：

```text
Provider: Ollama 本地接口
模型: qwen2.5
Base URL: http://127.0.0.1:11434/v1/chat/completions
API Key: 留空
```

配置保存在本机：

```text
app/data/config.json
```

默认不会保存 API Key。只有勾选“保存 API Key 到本机配置文件”时，才会写入本地配置文件。

## 从源码运行

如果你是开发者，或者直接 clone 了源码：

```bash
git clone git@github.com:ChauncyZhang/hr-resume-filter.git
cd hr-resume-filter
```

Windows：

```text
双击 Windows用户点我启动.bat
```

源码模式下 Windows 需要本机已有 Python 3.10 或更高版本；脚本会自动创建 `.venv` 并安装依赖。

macOS：

```bash
chmod +x Mac用户点我启动.command
./Mac用户点我启动.command
```

也可以手动启动：

```bash
cd app
python -m pip install -r requirements.txt
python web_app.py
```

## 生成 Windows 免安装包

在 Windows 开发机上运行：

```powershell
PowerShell -ExecutionPolicy Bypass -File app\build_windows_package.ps1
```

生成：

```text
dist/hr-resume-filter-windows.zip
```

把这个 zip 发给 HR，HR 解压后双击 `Windows用户点我启动.bat` 即可，不需要安装 Python。

## 生产运维入口

运维人员统一从以下 canonical 文档开始：

- [生产部署、升级与回滚](deploy/production-operations-runbook.md)
- [备份与恢复](deploy/backup-recovery-runbook.md)
- [监控、告警与排障](deploy/observability/runbook.md)

当前仓库的本地测试和 Compose 拓扑检查只属于代码门禁，不能证明生产环境可用。上线前仍必须按上述 runbook 在目标 Linux 主机、真实域名和 TLS 链路、真正异地的备份目的端以及实际告警接收端完成环境验收和恢复演练。

当前 Phase 6C 仅提供 fail-closed 的运维基础，不是 production ready；环境验收和 runbook 中的发布阻塞项未全部关闭前，不得开放生产流量。

## 命令行筛选

也可以不用网页，直接命令行筛选：

```bash
cd app
python resume_filter.py --input sample/resumes --jd sample/jd.txt --output sample/candidates.csv
```

输出的 CSV 可以用 Excel 打开。

## JD 写法

建议在 JD 中明确写：

```text
必须条件：Python, FastAPI, 本科
加分项：Docker, PostgreSQL
```

没有写“必须条件”时，系统会从 JD 中提取关键词做弱匹配。

## 输出字段

- `文件名`
- `匹配分`
- `推荐结论`
- `必须条件命中数`
- `必须条件总数`
- `缺失必须条件`
- `命中必须条件`
- `命中加分项`
- `识别年限`
- `LLM评分`
- `LLM结论`
- `LLM理由`
- `风险点`
- `面试问题`
- `LLM错误`

## 隐私和数据

- 简历文件默认只在本机临时处理。
- 岗位 JD 和 LLM 设置保存在本机 `app/data/config.json`。
- 未启用 LLM 时，不会向外部模型服务发送简历文本。
- 启用 LLM 后，会把 JD 和简历文本发送给你配置的模型服务。
- 请不要把 API Key、候选人隐私数据或公司内部 JD 提交到仓库。

## 开发验证

运行测试：

```bash
python -m unittest discover -s app/tests
```

## 项目结构

```text
.
├── Windows用户点我启动.bat
├── Mac用户点我启动.command
└── app/
    ├── web_app.py
    ├── resume_filter.py
    ├── web/
    ├── data/
    ├── sample/
    ├── tests/
    └── deploy/
```
