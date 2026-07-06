# HR Resume Filter

一个本地运行的简历初筛工具。它只处理 HR 已经合法获得的简历文件，不登录招聘平台、不抓网页、不绕过验证码。

## HR 怎么使用

如果拿到的是 Windows 免安装交付包，HR 解压后双击：

```text
Windows用户点我启动.bat
```

这个交付包不要求 HR 安装 Python。脚本会启动包里的免安装程序，然后浏览器会打开本地页面：

```text
http://127.0.0.1:8765
```

如果拿到的是源码仓库而不是免安装交付包，Windows 电脑才需要预先安装 Python 3.10 或更高版本；脚本会自动创建 `.venv` 并安装依赖。

页面流程：

1. 第一次使用时，点击右上角“设置”，在弹窗里配置是否启用 LLM、Provider、模型、Base URL，点击“保存设置”。
2. 第一次录入岗位时，填写岗位名称和 JD，点击“保存岗位”。
3. 后续使用时，只需要在“选择已保存岗位”里选岗位。
4. 在“简历文件”里选择或拖入多份简历。
5. 点击“开始筛选”。
6. 在页面上查看候选人排序结果。
7. 点击“下载 CSV”，用 Excel 打开结果。

工具已经预置一个“AI 工程师”岗位 JD，可以直接选择后测试。

macOS 用户双击或运行：

```text
Mac用户点我启动.command
```

如果 macOS 提示没有执行权限，管理员执行一次：

```bash
chmod +x Mac用户点我启动.command
```

Linux 服务器部署见：

```text
app/deploy/linux/README.md
```

服务器上推荐通过 systemd 启动服务，再用 Nginx 做反向代理和访问控制。

## 为什么这样做

推荐做成“本地 Web 页面 + Python 服务”：

- Windows：适合 HR 日常使用，双击脚本或用共享目录处理文件。
- macOS：适合开发和调试，命令行环境更顺手。
- 跨平台：最稳。页面、输入文件和输出 CSV 都不绑定系统。
- 后续可继续打包成 `.exe` 或 `.dmg`，让 HR 完全看不到命令行窗口。

当前版本默认支持 `.txt/.md/.csv`。如果要解析 `.pdf` 或 `.docx`，安装可选依赖：

```bash
python -m pip install pypdf python-docx
```

## 管理员命令行用法

准备目录：

```text
sample/
  jd.txt
  resumes/
    candidate-a.txt
    candidate-b.txt
```

运行：

```bash
cd app
python resume_filter.py --input sample/resumes --jd sample/jd.txt --output sample/candidates.csv
```

输出 `candidates.csv` 可直接用 Excel 打开。

## 生成 Windows 免安装包

开发者在 Windows 电脑上运行：

```powershell
PowerShell -ExecutionPolicy Bypass -File app\build_windows_package.ps1
```

生成结果：

```text
dist/hr-resume-filter-windows.zip
```

把这个 zip 发给 HR。HR 解压后只需要双击 `Windows用户点我启动.bat`，不需要安装 Python。

## JD 写法

脚本会优先识别这两类字段：

```text
必须条件：Python, FastAPI, 本科
加分项：Docker, PostgreSQL
```

没有写“必须条件”时，脚本会从 JD 里提取关键词做弱匹配。

## 输出字段

- `文件名`：简历文件名
- `匹配分`：0-100 匹配分
- `推荐结论`：优先沟通 / 可沟通 / 需人工复核 / 暂缓
- `必须条件命中数`：命中的必须条件数量
- `必须条件总数`：JD 中的必须条件数量
- `缺失必须条件`：缺失的必须条件
- `命中必须条件`：命中的必须条件
- `命中加分项`：命中的加分项
- `识别年限`：从简历文本里粗略识别的最高年限
- `LLM评分`：LLM 返回的 0-100 语义匹配分
- `LLM结论`：LLM 返回的沟通建议
- `LLM理由`：LLM 返回的简短匹配理由
- `风险点`：LLM 返回的待确认风险
- `面试问题`：LLM 建议的追问问题
- `LLM错误`：LLM 请求失败时的错误信息

## PDF 识别方式

当前 PDF 通过 `pypdf` 读取 PDF 文件里的文本层。

适合：

- 电脑生成的 PDF 简历
- 从招聘平台导出的文本型 PDF

不适合：

- 扫描件
- 图片型简历
- 字体编码异常导致文本抽取乱码的 PDF

这类文件需要后续接 OCR，例如 Tesseract、PaddleOCR 或云 OCR。

## LLM Provider 填法

默认不开启 LLM。不开启时，系统只做本地规则筛选，不会把简历发送给任何模型服务。

开启后，系统会把 JD、规则初筛结果和简历文本发送给你填写的模型服务，请确认该服务符合公司隐私和数据合规要求。

LLM 设置保存在：

```text
app/data/config.json
```

默认不会保存 API Key。只有勾选“保存 API Key 到本机配置文件”时，才会把 API Key 写入本地配置文件。

岗位 JD 列表也保存在同一个配置文件中。后续 HR 打开页面后可以直接选择岗位，不需要重复输入 JD。

OpenAI 兼容接口示例：

```text
Provider: OpenAI 兼容接口
模型: gpt-4o-mini
Base URL: https://api.openai.com/v1
API Key: your-api-key
```

其他 OpenAI-compatible 服务也可以填写自己的地址，例如：

```text
Base URL: https://your-provider.example.com/v1
```

Ollama 本地接口示例：

```text
Provider: Ollama 本地接口
模型: qwen2.5
Base URL: http://127.0.0.1:11434/v1/chat/completions
API Key: 留空
```

如果部署在 Linux 服务器上，并且 Ollama 也在同一台服务器，Base URL 用服务器本机地址即可。

## 合规边界

不要把这个脚本改成自动登录 BOSS 直聘、自动翻页、批量抓取未授权简历或绕过风控。建议只处理候选人主动投递、授权查看、HR 手动下载、企业后台合法导出或自建投递表单收集的简历。
