# 无头浏览器 / Playwright 工具行业标准

> **提炼自**：awesome-mcp-servers `browser-automation` 章节中 6 个最具代表性的 Playwright / Fetch 类 MCP server 调研报告
> **提炼方法**：6 个子代理按"浏览器安装 + URL 访问 + HTML 压缩 + fetch 实现"4 维度逐份深度调研 + 提取模式 + 标注频次；主控在此基础上跨项目整合，精选"高频共识"和"反例警示"，形成本标准
> **提炼日期**：2026-07-23
> **配套文档**：
> - 6 份单项目报告：`harness/01_market_research/<项目目录>/playwright.md`
>   - `fetch-mcp/` —— zcaceres/fetch-mcp（**纯 HTTP fetch** 路线，无 Playwright）
>   - `fetcher-mcp/` —— jae-jae/fetcher-mcp（**Playwright + Readability + turndown** 路线，3 个 tool）
>   - `playwright-plus-python-mcp/` —— blackwhite084/playwright-plus-python-mcp（**Playwright Python** 路线，8 个 tool）
>   - `mcp-playwright-ea/` —— executeautomation/mcp-playwright（**Playwright + 30+ tool** 路线，最流行）
>   - `MCP-Server-Playwright/` —— Automata-Labs-team/MCP-Server-Playwright（轻量 Playwright 实现）
>   - `mcp-aoai-web-browsing/` —— kimtth/mcp-aoai-web-browsing（Python + Azure OpenAI + Playwright 极简版）
> - 顶部引用：`harness/01_market_research/01_market_research/prompt.md`
> - 姊妹标准：`harness/01_market_research/standard/tool_channel.md`（工具调用）、`standard/file_backend.md`（工作区）、`standard/agent_loop.md`（Agent Loop）
> **本标准作用**：为后续 Onion Agent 的 `non_head_browser.py` 重构（无头浏览器工具）提供"必须做 / 强烈建议 / 可选 / 禁止"的决策清单

---

## 0. 文档结构

本标准按"设计哲学 → 浏览器安装 → URL 访问模式 → 内容提取 → 输出压缩 → fetch 工具设计 → 反爬虫对抗 → 错误处理 → 工具粒度"9 维度组织。每条标准带 4 个标签：

| 标签 | 含义 |
|----|------|
| **必须做** | 6 个项目里 ≥4 个采用，违反即成"反例" |
| **强烈建议** | 2-3 个项目采用，有清晰工程价值，新项目应当借鉴 |
| **可选** | 1 个项目采用，按需 |
| **禁止** | 0 个项目采用且明确有害，或违反会破坏信创合规 / 洋葱架构哲学 |

---

## 1. 顶层设计哲学（3 大流派 + 4 项原则）

6 个项目里有 3 个明显的设计流派，**没有"标准答案"——按场景选**：

### 1.1 流派 A：纯 HTTP Fetch（无浏览器依赖）

**代表项目**：`fetch-mcp`（zcaceres/fetch-mcp）

**技术栈**：Node.js 原生 `fetch` + `jsdom` + `@mozilla/readability` + `turndown`

**优势**：
- ✅ **零浏览器依赖**——`pnpm install` 即可，**不需要下载 Chromium/Firefox 二进制**
- ✅ **国内网络 / 离线 / 信创内网** 部署完全不受影响
- ✅ **启动快**——毫秒级，无 Chromium 进程开销
- ✅ **内存占用极小**——单次请求内存 ~10-50MB

**劣势**：
- ❌ **不渲染 JS**——SPA（React/Vue/Next.js）拿到的是空 `<div id="root"></div>`
- ❌ **不执行点击 / 表单 / 登录**——纯只读
- ❌ **不支持反爬虫对抗**（无 WebDriver 标识隐藏）

**适用场景**：文档站、新闻站、博客、API 文档、产品介绍页（90% 的"读文章"场景）

### 1.2 流派 B：Playwright 只读 Fetch（浏览器依赖 + 智能提取）

**代表项目**：`fetcher-mcp`（jae-jae/fetcher-mcp）

**技术栈**：`playwright`（Chromium）+ `jsdom` + `@mozilla/readability` + `turndown`

**优势**：
- ✅ **支持 JS 渲染**——能拿到 SPA 实际内容
- ✅ **Readability + turndown**——正文提取质量高
- ✅ **反爬虫指纹**做全（隐藏 webdriver / 随机 UA / 随机 viewport）
- ✅ **资源屏蔽**（`context.route("**/*", route.abort())` 屏蔽图片/CSS/字体）——省带宽

**劣势**：
- ❌ **需要 Playwright 浏览器二进制**（~300MB Chromium）
- ❌ **启动慢**（首次 2-5s 启动 Chromium）
- ❌ **只读**——不支持点击 / 交互 / 表单 / 登录

**适用场景**：SPA 内容抓取、JS 渲染的内容、需要绕过基础反爬虫的页面

### 1.3 流派 C：全功能 Playwright 自动化（30+ tool）

**代表项目**：`mcp-playwright-ea`（executeautomation/mcp-playwright）、`playwright-plus-python-mcp`

**技术栈**：`playwright`（Chromium/Firefox/WebKit）

**优势**：
- ✅ **完整浏览器自动化**——navigate / click / fill / hover / drag / screenshot / codegen 全支持
- ✅ **多浏览器**（Chromium/Firefox/WebKit）
- ✅ **可交互**——能填表、登录、点按钮、自动化测试

**劣势**：
- ❌ **tool 数膨胀**（30+ tool 撑爆 LLM system prompt）
- ❌ **需要更多 token**——LLM 选错工具的概率高
- ❌ **复杂度高**——错误处理、超时、并发、session 管理都复杂

**适用场景**：自动化测试、表单提交、登录态、复杂交互流程

### 1.4 原则一：抓取层与提取层分离

> **HTTP/浏览器抓取**（最底层）和 **HTML → Markdown/Text 转换**（中间层）应当是两个独立的环节，**每个环节可以独立替换**。

**频次**：4/6 显式分离（fetch-mcp / fetcher-mcp / mcp-playwright-ea / mcp-aoai-web-browsing）；2/6 部分分离（playwright-plus-python-mcp / MCP-Server-Playwright 把"goto + extract"塞在同一个 handler）

**典型代表**：
- `fetch-mcp` `src/Fetcher.ts:55-119` `_fetch()` + `readResponseText()` + `readable()` 分层清晰
- `fetcher-mcp` `src/services/webContentProcessor.ts` 单文件流水线（`page.goto` → `readability` → `turndown` → 截断）
- `mcp-playwright-ea` 每个 tool 独立 handler，但内部 `page.goto` + 提取在同一个函数

**Onion 启示**：**必须做**。Onion 的 `non_head_browser.py` 应当定义：
```python
def fetch_url(url: str) -> str: ...           # 抓取层（HTTP/浏览器二选一）
def html_to_markdown(html: str) -> str: ...   # 提取层（Readability + turndown）
def html_to_text(html: str) -> str: ...       # 提取层（去标签）
def truncate_middle(text: str, n: int) -> str: ...  # 压缩层
```
4 层分离后，**抓取层可以走 Playwright 也可以走 requests**（参考 mcp-servers.json 用户的 `web` server），**提取层可以换不同的 Readability 实现**。

### 1.5 原则二：协议中立（OpenAI Chat Completions 风格 schema）

> 工具 schema 在内部用 **OpenAI Chat Completions 风格**承载，便于 Provider 切换。

**频次**：6/6 全做（所有 MCP server 都用 MCP 协议，schema 风格统一）

**Onion 启示**：**必须做**。继承 `standard/tool_channel.md §1.1 协议中立` 原则。

### 1.6 原则三：错误透明（不抛 MCP exception，返回可读错误）

> 工具执行失败时**应当**包装成可读文本错误（`isError: true` + 文本消息）返回，**不要抛 Python traceback / MCP exception**。

**频次**：4/6 显式包装（fetch-mcp / fetcher-mcp / mcp-playwright-ea / mcp-aoai-web-browsing）；2/6 不包装（playwright-plus-python-mcp / MCP-Server-Playwright 直接抛 Playwright 异常）

**典型代表**：
- `fetch-mcp` `src/Fetcher.ts:134-139` 任何错误 try-catch 转 `isError: true` + 文本
- `fetcher-mcp` `src/services/webContentProcessor.ts:130-140` `Title: Error / URL: <u> / <error>...` 格式
- `mcp-playwright-ea` `src/handleToolCall.ts` 类似包装

**反面教材**：
- `playwright-plus-python-mcp` `server.py:347-358` `handle_call_tool` 不包 try-catch，Playwright 抛 `TimeoutError` 直接冒泡给 LLM

**Onion 启示**：**必须做**。所有 handler 入口包 `try/except` + 错误分类（4xx / 5xx / DNS / 超时），统一返回 `{"success": False, "is_error": True, "content": "[ERROR] <msg>", "data": {...}}`。

### 1.7 原则四：所有工具暴露统一 OpenAI Chat Completions schema

> 继承 `standard/tool_channel.md §3.1`，schema 走 OpenAI function calling 风格。

**Onion 启示**：**必须做**。所有 tool 走 `{"type": "function", "function": {"name", "description", "parameters"}}` 格式。

---

## 2. Playwright 无头浏览器安装策略

### 2.1 三重保险：postinstall + install 命令 + MCP 工具级安装 —— 强烈建议

**频次**：1/6 完整三重（fetcher-mcp）；1/6 双重（mcp-playwright-ea 自动 + install 命令）；4/6 弱（playwright-plus-python-mcp 0 hook / fetch-mcp 无浏览器 / 其他）

**典型代表**：
- **`fetcher-mcp` 最完整**：
  - `package.json:19` `postinstall: playwright install chromium` — 装包时自动装
  - `package.json:18` `install-browser: npx playwright install chromium` — 提供独立命令
  - `src/tools/browserInstall.ts:40-103` 暴露 `browser_install` 工具，**LLM 可主动调**
  - `src/tools/browserInstall.ts:110-145` **双策略 fallback**：`require.resolve("playwright/package.json")` 找本地 CLI → fallback 到 `npx playwright install`
  - `src/tools/browserInstall.ts:50-58` 支持 `--with-deps`（Linux 系统依赖）和 `--force`（强制重装）
- **`mcp-playwright-ea` v1.0.12 CHANGELOG**：Automatic Browser Installation
  - Server 首次启动检测到浏览器缺失 → 自动 `npx playwright install <browser>`
  - 2 分钟超时保护
  - 失败有 manual installation instructions fallback

**反面教材**：
- `playwright-plus-python-mcp` `pyproject.toml:7` 只声明 `["mcp>=1.1.2", "playwright"]`，**无 post-install hook**——`uv sync` 装完包后 Chromium 二进制不会自动下载，第一次 `playwright_navigate` 必然失败

**Onion 启示**：**强烈建议**。Onion 的 `non_head_browser.py` 应当：
1. 首次 `from playwright.sync_api import sync_playwright` 时检测浏览器是否安装
2. 未安装 → 自动 `subprocess.run(["playwright", "install", "chromium"])`，**带 2 分钟超时**
3. 安装失败 → 抛清晰错误，**提示用户**手动跑 `playwright install chromium`

### 2.2 浏览器二进制存储位置：依赖 Playwright 默认 —— 必做

**频次**：5/6 全部依赖 Playwright 默认（fetcher-mcp / mcp-playwright-ea / playwright-plus-python-mcp / MCP-Server-Playwright / mcp-aoai-web-browsing）；0/6 自定义路径

**Playwright 默认路径**（由 Playwright Python / Node SDK 决定）：
- **Windows**：`%LOCALAPPDATA%\ms-playwright\chromium-<rev>\chrome-win\chrome.exe`
- **macOS**：`~/Library/Caches/ms-playwright/chromium-<rev>/chrome-mac/Chromium.app/Contents/MacOS/Chromium`
- **Linux**：`~/.cache/ms-playwright/chromium-<rev>/chrome-linux/chrome`

**Onion 启示**：**必须做**。Onion 不要覆盖 `PLAYWRIGHT_BROWSERS_PATH`，走默认路径。理由：
- 用户已经有了 Playwright 缓存，多个工具共享二进制
- 国内用户可以通过 `PLAYWRIGHT_DOWNLOAD_HOST=https://npmmirror.com/mirrors/playwright` 走镜像（这是 Playwright 官方支持的）

### 2.3 国内镜像支持：明确支持 `PLAYWRIGHT_DOWNLOAD_HOST` —— 强烈建议

**频次**：0/6 显式支持（**这是行业反例**）；但 6/6 都能**间接**用 `PLAYWRIGHT_DOWNLOAD_HOST` 环境变量（因为都是 Playwright 官方 SDK）

**Onion 启示**：**强烈建议**。Onion 的 `non_head_browser.py` 在 README 写：
> 国内用户可设置 `PLAYWRIGHT_DOWNLOAD_HOST=https://npmmirror.com/mirrors/playwright` 走国内镜像。

### 2.4 支持本地已安装浏览器路径（`executable_path` / `channel`）—— 强烈建议

**频次**：0/6 支持（**fetcher-mcp `grep -i "executablePath|channel"` 零命中**；其他项目也没显式支持）

**Onion 启示**：**强烈建议**。Onion 的 `non_head_browser.py` 应当：
- 接受 `executable_path: str | None = None` 参数（用户传本机 Chrome / Edge 路径）
- 接受 `channel: str | None = None` 参数（用 Playwright 预装的 'chrome' / 'msedge' / 'chrome-beta'）
- 这对**信创合规**场景（要求用特定国产浏览器套件）很重要

### 2.5 离线安装支持 —— 可选

**频次**：0/6 显式支持

**Onion 启示**：**可选**。信创内网场景需要 pre-download tarball 走 `PLAYWRIGHT_BROWSERS_PATH=/path/to/tarballs` 模式，但这是 P1 高级需求。

### 2.6 Docker 镜像构建时自动装 —— 强烈建议

**频次**：1/6 显式（fetcher-mcp `Dockerfile:36` `RUN npx playwright install --with-deps chromium`）

**Onion 启示**：**强烈建议**。Onion 应当提供 `Dockerfile` + `docker-compose.yml`，Dockerfile 中 `RUN playwright install --with-deps chromium`。

---

## 3. URL 访问模式

### 3.1 4 个 URL 访问入口 —— 强烈建议

6 个项目里 URL 访问有 4 种实现：

| 类型 | 实现 | 项目 | 频次 |
|------|------|------|------|
| **HTTP fetch** | `fetch(url, { headers, signal })` | fetch-mcp | 1/6 |
| **Playwright goto** | `page.goto(url, { timeout, waitUntil })` | fetcher-mcp / mcp-playwright-ea / playwright-plus-python-mcp / mcp-aoai-web-browsing | 4/6 |
| **axios/undici** | — | 0/6 | 0/6 |
| **requests (Python)** | `requests.get(url, ...)` | — | 0/6 |

**Onion 启示**：**强烈建议**。Onion 应当**双模式**：
- `fetch_url` 工具走**纯 HTTP**（默认，`requests` 或 `httpx`）——快、零依赖
- `browser_navigate` 工具走**Playwright**（fallback，需要 JS 渲染时用）

### 3.2 URL 协议白名单（只允许 http/https）—— 必做

**频次**：2/6 显式（fetch-mcp `src/Fetcher.ts:23` / fetcher-mcp `src/utils/urlValidator.ts:16`）；4/6 隐式（Playwright `page.goto` 默认拒绝 `file://` 等）

**典型代表**：
- `fetch-mcp` `src/Fetcher.ts:23-26` `validateUrl()` 显式 `protocol !== 'http:' && protocol !== 'https:'` throw
- `fetcher-mcp` `src/utils/urlValidator.ts:16-22` 同样只允许 `http:` / `https:`

**Onion 启示**：**必须做**。**安全加固**——LLM 控制的 URL 抓取必须显式拒绝 `file://`、`javascript:`、`data:`、`ftp://` 等。

### 3.3 SSRF 防护（DNS 解析后 IP 校验）—— 必做

**频次**：1/6 显式（fetch-mcp `src/Fetcher.ts:19-53` 三道关：协议 + 主机名 + DNS 解析 IP）；0/6 显式 SSRF 防护

**典型代表**：
- `fetch-mcp` `src/Fetcher.ts:30-32` 用 `private-ip` 库校验主机名不能是内网 IP
- `src/Fetcher.ts:46-52` `validateResolvedIp` 异步解析后再次校验（防 DNS rebinding）
- `src/Fetcher.ts:81-84` 3xx 跳转后再校验（防 redirect bypass）

**反面教材**：
- `fetcher-mcp` 只校验协议，**没校验** SSRF——LLM 传 `http://10.0.0.1` 或 `http://169.254.169.254/`（AWS metadata）会被无脑抓

**Onion 启示**：**必须做**。Onion 的 `fetch_url` 必须抄 `fetch-mcp` 的三道关：
```python
def validate_url(url: str) -> None:
    # 1. 协议白名单
    # 2. 主机名校验（拒绝 localhost / 内网 IP）
    # 3. DNS 解析后再次校验 IP（防 DNS rebinding）
    # 4. 3xx 跳转后再次校验
```

### 3.4 超时控制 —— 必做

**频次**：4/6 显式（fetch-mcp / fetcher-mcp / mcp-playwright-ea / MCP-Server-Playwright）；1/6 缺失（playwright-plus-python-mcp `page.goto(url)` 不传 timeout）；1/6 缺失（mcp-aoai-web-browsing 未确认）

**典型实现**：
- `fetcher-mcp` `src/tools/fetchUrl.ts:90` 默认 `timeout: 30000` + `navigationTimeout`（独立给 `waitForNavigation` 用）
- `mcp-playwright-ea` `timeout` 作为 tool 参数
- `fetch-mcp` ❌ **缺失**——`fetch(url, { ... })` 没传 `signal: AbortSignal.timeout(N)`

**Onion 启示**：**必须做**。所有 URL 访问入口必须有 `timeout: int` 参数，默认 15s、最大 60s（沿用 Onion `non_head_browser.py` 当前实现的范围）。

### 3.5 等待策略（`waitUntil: 'load' | 'domcontentloaded' | 'networkidle' | 'commit'`）—— 强烈建议

**频次**：2/6 显式（fetcher-mcp / mcp-playwright-ea）；其他 4 个用 Playwright 默认

**Onion 启示**：**强烈建议**。`browser_navigate` 工具接受 `wait_until` 参数，默认 `'load'`，SPA 场景可选 `'networkidle'`。

### 3.6 URL 访问级别重试 —— 强烈建议

**频次**：0/6 显式 URL 访问级别重试；1/6 隐式（fetcher-mcp `webContentProcessor.ts:194` `safelyGetPageInfo` 内 `page.content()` 失败 3 次重试，**但不是 URL 级别**）

**Onion 启示**：**强烈建议**。Onion 应当 `tenacity` 装饰器或自己写指数退避，**重试 2-3 次**处理网络抖动。

### 3.7 超时后抢救（`page.content()` 拿已渲染部分）—— 强烈建议

**频次**：1/6 显式（fetcher-mcp `webContentProcessor.ts:30-59`）；0/6 其他

**典型代表**：
- `fetcher-mcp` `webContentProcessor.ts:30-59` `page.goto` 超时后**不直接抛错**，尝试 `page.title()` + `page.content()` 抢救已渲染部分
- 只有抢救失败才 throw

**Onion 启示**：**强烈建议**。Onion 应当借鉴：timeout 不一定是"完全失败"，超时可能只是"还有懒加载没完"，已渲染的 DOM 可能够用。

### 3.8 `waitForNavigation` 反爬虫增强 —— 可选

**频次**：1/6 显式（fetcher-mcp `webContentProcessor.ts:62-100` 首次 `page.goto` 后再用 `page.waitForNavigation` 等一轮，专门给"加载后跳转到验证页"的场景用）

**Onion 启示**：**可选**（P1）。Onion 可以加 `wait_for_navigation: bool` 参数给"加载后跳转"的页面用。

---

## 4. 内容提取（HTML 处理）

### 4.1 Mozilla Readability 正文提取 —— 强烈建议

**频次**：2/6 显式（fetch-mcp `src/Fetcher.ts:325` / fetcher-mcp `webContentProcessor.ts:213-229`）；0/6 其他

**典型实现**：
- `fetch-mcp` `src/Fetcher.ts:325-326` `new Readability(dom.window.document).parse()` → `article.content`
- `fetcher-mcp` `webContentProcessor.ts:213-229` 同样 Readability
- 都不直接选 `<article>` / `<main>` CSS 选择器（这是 Readability 算法自动算的）

**反面教材**：
- `playwright-plus-python-mcp` `server.py:281-321` `GetTextContentToolHandler` 用**全 DOM 遍历 + offsetWidth/Height 可见性判断 + 去重**——是 LLM 友好思路但不是 readability 思路

**Onion 启示**：**强烈建议**。Onion 的 `fetch_url` 默认走 `readability-lxml`（Python 对应 `readability-lxml`，PyPI 有），LLM 拿到的就是干净正文。

### 4.2 HTML → Markdown（turndown / markdownify）—— 强烈建议

**频次**：3/6 显式（fetch-mcp / fetcher-mcp / mcp-playwright-ea）；3/6 缺失（playwright-plus-python-mcp / MCP-Server-Playwright / mcp-aoai-web-browsing）

**典型实现**：
- `fetch-mcp` `src/Fetcher.ts:332` `new TurndownService().turndown(article.content)`
- `fetcher-mcp` `webContentProcessor.ts:236-238` Turndown + GFM 插件（`turndown-plugin-gfm`）支持表格
- `mcp-playwright-ea` `playwright_get_visible_text` + `playwright_get_visible_html` 两个 tool

**Onion 启示**：**强烈建议**。Onion 的 `fetch_url` 输出 Markdown 格式，LLM 友好。Python 用 `markdownify`（PyPI 有）。

### 4.3 Readability 元数据一并返回 —— 强烈建议

**频次**：0/6 完整返回（**fetch-mcp `src/Fetcher.ts:333` 只取 `article.content`，浪费了 `article.title / byline / siteName / publishedTime / excerpt / og:image`**）；0/6 完整返回

**反面教材**：
- `fetch-mcp` 计算出 Readability 元数据但**只返回 content**，浪费了算法副产物

**Onion 启示**：**强烈建议**。Onion 应当返回结构化：
```python
{
  "title": ...,
  "byline": ...,
  "site_name": ...,
  "published_time": ...,
  "excerpt": ...,
  "content_markdown": ...,
  "url": ...,
  "status_code": ...,
}
```

### 4.4 `<script>` / `<style>` 标签剥离 —— 必做

**频次**：5/6 显式剥离（fetch-mcp `fetch_txt` 路径 / fetcher-mcp 由 Readability 间接剥离 / mcp-playwright-ea `get_visible_html` 默认剥离 / fetch-mcp 默认行为 / MCP-Server-Playwright 默认）；1/6 缺失（playwright-plus-python-mcp `GetHtmlContentToolHandler` 返回 `inner_html` 不剥离）

**Onion 启示**：**必须做**。Onion 的 `fetch_url`（无论 HTML 还是 Markdown 输出）必须先过 `<script>/<style>/<!--comment-->` 剥离。

### 4.5 JSON-LD / OpenGraph 元数据提取 —— 可选

**频次**：0/6 显式

**Onion 启示**：**可选**（P1）。`fetch_url` 返回 `og:title / og:image / og:description` 对文章理解很有用，但不是 MVP 必须。

### 4.6 反爬虫指纹注入 —— 强烈建议

**频次**：1/6 显式（fetcher-mcp `browserService.ts:66-112`）；0/6 其他

**典型实现**（`fetcher-mcp` `browserService.ts:66-112`）：
```typescript
await context.addInitScript(() => {
  Object.defineProperty(navigator, 'webdriver', { get: () => false });      // 隐藏 webdriver 标识
  delete (window as any).cdc_adoQpoasnfa76pfcZLmcfl_Array;                  // 删除 ChromeDriver 注入的 cdc_ 变量
  (window as any).chrome = { runtime: {} };                                 // 注入假的 window.chrome 对象
  Object.defineProperty(navigator, 'plugins', { get: () => [/* 5-9 个伪插件 */] });
  Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
});
```
+ 随机 UA（Chrome 122/123 / Firefox 123 / Safari 17.3）+ 随机 viewport + `deviceScaleFactor`
+ `chromium.launch` 加 `--disable-blink-features=AutomationControlled`

**Onion 启示**：**强烈建议**。Onion 应当把这些反爬虫指纹**默认开启**，并允许通过参数关闭（开发环境可能不需要）。

### 4.7 资源屏蔽（图片/CSS/字体）—— 强烈建议

**频次**：1/6 显式（fetcher-mcp `browserService.ts:117-128` `context.route("**/*", route.abort())`）

**典型实现**：
- `fetcher-mcp` `browserService.ts:117-128` `context.route("**/*.{png,jpg,jpeg,gif,webp,svg,ico,css,woff,woff2,ttf,otf,mp3,mp4,webm,ogg,wav,pdf}", route.abort())`
- `fetchUrl.ts:101` 默认 `disableMedia: true`

**Onion 启示**：**强烈建议**。Onion 的 `browser_navigate` 工具接受 `disable_media: bool = True`，省 80% 带宽。

---

## 5. 输出压缩

### 5.1 截断阈值：3 个项目都有 `max_length` / `max_chars` 参数 —— 必做

**频次**：5/6 显式（fetch-mcp `downloadLimit=5000` / fetcher-mcp `maxLength` / mcp-playwright-ea `playwright_get_visible_html` 默认 20000 字符 / playwright-plus-python-mcp `text_content[:200]` / MCP-Server-Playwright 未确认）；1/6 无

**典型实现**：
- `fetch-mcp` `src/types.ts:12` zod schema `downloadLimit` = 5000（可配）
- `fetcher-mcp` `webContentProcessor.ts:242-244` `processedContent.substring(0, this.options.maxLength)`（**头截断**）
- `mcp-playwright-ea` CHANGELOG "HTML output truncated to 20,000 characters by default"
- `playwright-plus-python-mcp` `server.py:217` `text_content[:200]`（极简）

**Onion 启示**：**必须做**。Onion 沿用当前 `non_head_browser.py` 的 `max_chars: int = 20000` 默认值。

### 5.2 截断方式：头截断 vs 头+尾保留 vs token 截断 —— 强烈建议

**频次**：
- **头截断**（保留前 N 字符）：2/6（fetch-mcp / fetcher-mcp）
- **头+尾保留**（保留前 50% + 后 50%）：0/6（**这是 Onion 现有 `non_head_browser.py` 的实现**）
- **token 截断**（按 tiktoken 算）：0/6

**Onion 启示**：**强烈建议**。**头+尾保留**（参考 Cline §6.7 + tool_channel §6.7）比单纯截头友好——LLM 能看到文章开头和结尾。但需要加 `tiktoken` 库做精确 token 截断。MVP 用 `truncate_middle` 头+尾即可，P1 加 token 截断。

### 5.3 响应体字节上限（流式 + content-length 预检）—— 必做

**频次**：1/6 显式（fetch-mcp `MAX_RESPONSE_BYTES = 10MB` + 流式 + content-length 预检）；0/6 其他

**典型实现**（`fetch-mcp` `src/Fetcher.ts:90-118`）：
```typescript
// 1) content-length 预检
if (contentLength && parseInt(contentLength, 10) > maxResponseBytes) {
  throw new Error("Response too large...");
}
// 2) 流式读取时实时累加字节数
while (true) {
  const { done, value } = await reader.read();
  if (done) break;
  bytesRead += value.byteLength;
  if (bytesRead > maxResponseBytes) throw new Error("...");
  result += decoder.decode(value, { stream: true });
}
```

**反面教材**：
- `playwright-plus-python-mcp` `server.py:330` `get_html_content` 不限制大小，大页面 OOM 风险
- `fetcher-mcp` `webContentProcessor.ts` 不限制原始 HTML 加载大小
- `mcp-playwright-ea` v1.0.x 限制 20000 字符但**不限制字节数**

**Onion 启示**：**必须做**。Onion 应当：
1. HTTP fetch 层加 `MAX_RESPONSE_BYTES = 10MB` 硬上限
2. Playwright 层**不直接限制 HTML 字节**（让 Playwright 处理），但**输出层**走 `max_chars` 截断
3. 超过 `max_chars` 时按"头 + 尾 + 中间省略"模式截断

### 5.4 完全旁路到磁盘（spill-to-disk）—— 可选

**频次**：0/6 显式（**所有项目都走 MCP 文本通道直接返回，不落盘**）

**反面参考**：
- `standard/tool_channel.md §6.7` 推荐 `workspace://tool-outputs/<call_id>.json` + retrieval hint 三件套

**Onion 启示**：**可选**（P1）。Onion 当前 `non_head_browser.py` 也**不落盘**——和行业一致。继承 `standard/tool_channel.md §6.7` 的大结果旁路机制统一处理即可。

### 5.5 截图压缩（screenshot / base64 size 限制）—— 强烈建议

**频次**：1/6 显式截断（mcp-playwright-ea `playwright_get_visible_html` 默认 20K）；1/6 不限制（playwright-plus-python-mcp `server.py:230-236` 写 `f"{name}.png"` 后 base64 内联返回，**无 size 限制**）

**反面教材**：
- `playwright-plus-python-mcp` `server.py:230` 写的是 `path=f"{name}.png"`（**相对路径**），如果用户传 `name="../../tmp/abc"`，会落到任意可写目录再读回——轻微的**路径遍历**风险

**Onion 启示**：**强烈建议**。Onion 的 `browser_screenshot` 工具：
1. 默认输出 PNG 但接受 `type: 'jpeg' | 'png'` 参数
2. 默认压缩质量 80%（`quality=80`）
3. 图片 base64 超过 1MB 拒绝返回（提示用户用 `selector` 截区域）

---

## 6. fetch 工具设计

### 6.1 fetch 工具是核心而非辅助 —— 必做

**频次**：5/6 把 fetch 当核心（fetch-mcp / fetcher-mcp / mcp-playwright-ea / MCP-Server-Playwright / mcp-aoai-web-browsing）；1/6 没有 fetch（playwright-plus-python-mcp）

**反面教材**：
- `playwright-plus-python-mcp` **没有 fetch 工具**——纯浏览器自动化，用户要读文章得 navigate + get_html_content 两步

**Onion 启示**：**必须做**。Onion 的 `non_head_browser.py` **首推 fetch_url** 工具（默认 HTTP），把 browser_navigate 降级为"特殊场景工具"。

### 6.2 工具粒度：2 个布尔参数替代 4 个工具 —— 强烈建议

**频次**：1/6 优秀（fetcher-mcp `fetch_url` 的 `extractContent` × `returnHtml` 2 个布尔参数组合 4 种输出模式）；1/6 分散（fetch-mcp 6 个独立工具 `fetch_html` / `fetch_markdown` / `fetch_txt` / `fetch_json` / `fetch_readable` / `fetch_youtube_transcript`）；其他各有设计

**对比**：
- **fetcher-mcp 风格**（推荐）：`fetch_url(url, extract_content=True, return_html=False, max_length=N)` 4 种模式
- **fetch-mcp 风格**：6 个工具名（`fetch_html` / `fetch_markdown` / `fetch_txt` / `fetch_json` / `fetch_readable` / `fetch_youtube_transcript`）

**Onion 启示**：**强烈建议**。Onion 应当**学 fetcher-mcp 的 2 布尔参数模式**：
- `fetch_url(url, format: 'html' | 'markdown' | 'text' = 'markdown', extract_content: bool = True, max_length: int = 20000)` 
- 1 个 fetch 工具，3 种输出格式 = 减少 LLM 工具选择负担
- `format='json'` 给 API 调用场景（fetch-mcp 有 `fetch_json`）

### 6.3 多 URL 并行抓取 —— 强烈建议

**频次**：1/6 显式（fetcher-mcp `fetch_urls`）；0/6 其他

**Onion 启示**：**强烈建议**。Onion 的 `fetch_urls(urls: list[str], max_concurrent: int = 5)` 工具，接受 URL 列表，**`asyncio.Semaphore` 控制并发上限**（fetcher-mcp 没用信号量是反面教材：10 个 URL 同时开 10 个 page 资源爆炸）。

### 6.4 浏览器自愈回路（MCP tool 主动安装）—— 强烈建议

**频次**：2/6 显式（fetcher-mcp `browser_install` 工具 / mcp-playwright-ea v1.0.12 auto-install）；0/6 其他

**典型实现**（fetcher-mcp）：
- `browserService.ts:152-177` 启动时检测"浏览器未安装"错误（5 种关键字），抛 `BrowserNotInstalledError` + 提示 LLM 调 `browser_install`
- `browserInstall.ts:110-145` 双策略 fallback（本地 CLI → npx）

**Onion 启示**：**强烈建议**。Onion 应当提供 `browser_install` 工具，LLM 拿到"浏览器未安装"错误时主动调它。继承 `standard/agent_loop.md §5.9` 错误自愈机制。

### 6.5 HTTP headers 透传（Cookie / Authorization）—— 强烈建议

**频次**：1/6 支持（fetch-mcp `headers` 参数）；4/6 不支持（fetcher-mcp / playwright-plus-python-mcp / MCP-Server-Playwright / mcp-aoai-web-browsing）；mcp-playwright-ea 未确认

**Onion 启示**：**强烈建议**。Onion 应当：
- `fetch_url` 接受 `headers: dict[str, str] | None = None` 参数
- `browser_navigate` 接受 `headers` 参数（走 Playwright `extraHTTPHeaders`）
- **不能支持 Cookie 持久化**（安全性考虑，Cookie 应当走 LLM 外部存储）

### 6.6 重定向控制 —— 可选

**频次**：0/6 显式 `maxRedirects`（fetch-mcp 走 fetch 默认 20 次 / fetcher-mcp / 其他都走 Playwright 默认）

**Onion 启示**：**可选**。Onion 可以加 `max_redirects: int = 10` 参数，**3xx 跳到内网时拒绝**（继承 §3.3 SSRF 防护）。

### 6.7 错误分类（4xx / 5xx / DNS / 超时）—— 必做

**频次**：1/6 详细分类（fetch-mcp `src/Fetcher.ts` 7 种错误：协议/SSRF/HTTP/响应过大/网络失败/DNS 解析失败/流式读取超限）；1/6 模糊分类（fetcher-mcp `<error>...</error>` 包装但不分类）；4/6 不分类

**Onion 启示**：**必须做**。Onion 应当 4 类错误：
- `400 BadRequest` — URL 格式错
- `403 Forbidden` — 协议白名单拒绝 / SSRF 拒绝
- `404 NotFound` / `410 Gone` — 资源不存在
- `5xx ServerError` / `NetworkError` / `Timeout` — 服务端/网络问题

每种错误返回 `{"success": False, "is_error": True, "content": "[ERROR] <msg>", "data": {"error_type": "http_404"}}`。

---

## 7. 反爬虫对抗

### 7.1 User-Agent 默认（Chrome 最新版）—— 必做

**频次**：6/6 全做（fetch-mcp / fetcher-mcp / mcp-playwright-ea / playwright-plus-python-mcp / MCP-Server-Playwright / mcp-aoai-web-browsing）

**Onion 启示**：**必须做**。Onion 沿用当前 `non_head_browser.py` 的 `DEFAULT_USER_AGENT = Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36`。

### 7.2 WebDriver 标识隐藏 —— 强烈建议

**频次**：1/6 显式（fetcher-mcp `browserService.ts:66-112`）；5/6 不做（其他项目）

**Onion 启示**：**强烈建议**。Onion 的 `browser_navigate` 默认注入 `navigator.webdriver = false` init script。

### 7.3 随机 UA / 随机 viewport —— 可选

**频次**：1/6 显式（fetcher-mcp 7 个 UA 混用 + 5 个 viewport 混用）；5/6 不做

**Onion 启示**：**可选**（P1）。反爬虫深度需求才需要，每次随机 UA 增加 LLM 调试难度（页面结构会变）。MVP 固定 Chrome 120 UA 即可。

### 7.4 代理支持 —— 可选

**频次**：1/6 支持但有 bug（fetch-mcp `proxy` 参数在 Node.js 端被默默忽略，**只在 Bun 生效**）；5/6 不支持

**反面教材**：
- `fetch-mcp` `src/Fetcher.ts:70-72` `// Note: proxy is a Bun-specific fetch option. On Node.js, this option is silently ignored.`

**Onion 启示**：**可选**。Onion Python 走 `httpx` 用 `httpx.Proxy` 即可，无 Node 端 bug。**但要明确在 README 写**"代理参数支持"。

### 7.5 资源屏蔽（图片/CSS/字体）—— 强烈建议

**频次**：1/6 显式（fetcher-mcp §4.7）；0/6 其他

**Onion 启示**：**强烈建议**。Onion 的 `browser_navigate` 接受 `disable_media: bool = True`，省 80% 带宽。

---

## 8. 错误处理与可观测性

### 8.1 错误透明（不抛 MCP exception）—— 必做

**频次**：4/6 显式（fetch-mcp / fetcher-mcp / mcp-playwright-ea / mcp-aoai-web-browsing）；2/6 反例（playwright-plus-python-mcp / MCP-Server-Playwright）

**Onion 启示**：**必须做**。所有 handler 入口包 `try/except` + 错误分类（§6.7）。

### 8.2 超时也抢救（page.content() 拿已渲染部分）—— 强烈建议

**频次**：1/6 显式（fetcher-mcp §3.7）；0/6 其他

**Onion 启示**：**强烈建议**。Onion 借鉴 §3.7。

### 8.3 浏览器自愈回路 —— 强烈建议

**频次**：1/6 显式（fetcher-mcp `browser_install` + 错误信息提示 LLM 调工具）

**Onion 启示**：**强烈建议**。Onion 应当让 `playwright._impl._errors.Error: Executable doesn't exist` 错误**自动调** `browser_install` 工具重试一次。

### 8.4 duration_ms 记录 —— 可选

**频次**：3/6 显式（fetch-mcp / fetcher-mcp / mcp-playwright-ea）；3/6 不记录

**Onion 启示**：**可选**。Onion 沿用当前 `non_head_browser.py` 的 `duration_ms` 字段到 `data` 字段。

### 8.5 监控 / 日志 —— 必做

**频次**：6/6 全做（所有 MCP server 都有 console 输出或日志文件）

**Onion 启示**：**必须做**。Onion 沿用 `non_head_browser.py` 当前实现。

---

## 9. 工具粒度（MCP tool 数量）

### 9.1 MVP 工具集：1 个 fetch_url（HTTP）+ 4 个 browser_xxx（Playwright）—— 必做

**频次对比**：
- `playwright-plus-python-mcp`：**8 个 tool**（navigate / screenshot / click / fill / evaluate / click_text / get_text_content / get_html_content）—— 偏多
- `fetcher-mcp`：**3 个 tool**（fetch_url / fetch_urls / browser_install）—— 精简
- `fetch-mcp`：**6 个 tool**（html / markdown / txt / json / readable / youtube_transcript）—— 中等
- `mcp-playwright-ea`：**30+ tool**（navigate / click / fill / drag / screenshot / iframe_fill / codegen / device resize ...）—— 过多

**对比 1 个 fetch + 1 个 fetch_urls + 1 个 browser_install + 1 个 browser_navigate + 1 个 browser_screenshot = 5 个 tool**。

**Onion 启示**：**必须做**。Onion 的 MVP 工具集应当精简到 **5-7 个 tool**：
1. `fetch_url` (HTTP + Readability + Markdown，单 URL)
2. `fetch_urls` (HTTP 并行多 URL)
3. `browser_navigate` (Playwright goto + 渲染)
4. `browser_screenshot` (Playwright 截图)
5. `browser_install` (Playwright 浏览器自动安装)
6. `browser_close` (清理资源)

**P1 扩展**（如果 LLM 用得顺）：
- `browser_click` / `browser_fill` — 交互（替代人工）
- `browser_evaluate` — JS 执行

**禁止**：直接抄 mcp-playwright-ea 的 30+ tool——会撑爆 LLM system prompt（参考 `standard/tool_channel.md §4.7` Tool Search 渐进式披露）。

### 9.2 Tool Search 渐进式披露（工具数 ≥ 7 时）—— 强烈建议

**频次**：0/6 显式（**所有项目都把全量 tool 注入 system prompt**）

**Onion 启示**：**强烈建议**。Onion 工具数到 5-7 个时还不需要 tool_search，但 P1 加 click/fill/evaluate 后会到 10+ 个，**必须**引入 `tool_search` 机制（参考 `standard/tool_channel.md §4.7`）。

### 9.3 工具名规范化（`browser_*` / `fetch_*` 前缀）—— 强烈建议

**频次**：6/6 全做（fetcher-mcp `fetch_url` / `browser_install` / `fetch-mcp` `fetch_*` / `mcp-playwright-ea` `playwright_*` / `playwright-plus-python-mcp` `playwright_*` / `mcp-aoai-web-browsing` 未确认）

**典型命名空间**：
- `fetch_*` — HTTP 抓取（无浏览器）
- `browser_*` — Playwright 浏览器
- `playwright_*` — Playwright 通用（前缀统一）

**Onion 启示**：**强烈建议**。Onion 沿用 Onion 现有 `web_search` / `web_fetch` 命名（`non_head_browser.py` 重构后）：
- `fetch_url` (HTTP)
- `fetch_urls` (HTTP 多 URL)
- `browser_navigate` (Playwright)
- `browser_screenshot` (Playwright)
- `browser_install` (Playwright 浏览器安装)
- `browser_close` (Playwright 资源清理)

`web_search` 工具保留（用 DuckDuckGo HTML 端点，无需 Playwright）。

### 9.4 工具 schema 强校验 + additionalProperties: false —— 必做

**频次**：6/6 全做

**Onion 启示**：**必须做**。继承 `standard/tool_channel.md §3.3-3.4` strict mode + 强校验。

---

## 10. 与 Onion Agent 落地的对应

`non_head_browser.py` 重构后，工具签名应当为：

```python
# 5 个原子化工具

def fetch_url(
    url: str,
    format: str = "markdown",          # "html" | "markdown" | "text" | "json"
    extract_content: bool = True,      # 用 Readability 抽正文
    max_chars: int = 20000,
    timeout: int = 15,
    headers: dict | None = None,
) -> dict: ...

def fetch_urls(
    urls: list[str],
    format: str = "markdown",
    extract_content: bool = True,
    max_chars: int = 20000,
    timeout: int = 15,
    max_concurrent: int = 5,           # asyncio.Semaphore
) -> dict: ...

def browser_navigate(
    url: str,
    wait_until: str = "load",          # "load" | "domcontentloaded" | "networkidle" | "commit"
    timeout: int = 30,
    disable_media: bool = True,        # 屏蔽图片/CSS/字体
    executable_path: str | None = None,  # 用户本机 Chrome
    channel: str | None = None,        # "chrome" | "msedge" | "chrome-beta"
) -> dict: ...

def browser_screenshot(
    url: str,
    selector: str | None = None,       # 区域选择器
    full_page: bool = True,
    type: str = "png",                 # "png" | "jpeg"
    quality: int = 80,
    max_size_mb: float = 1.0,          # base64 size 硬上限
) -> dict: ...

def browser_install(
    with_deps: bool = False,
    force: bool = False,
    timeout: int = 120,
) -> dict: ...
```

**关键设计决策**：
- `fetch_url` 走**纯 HTTP**（`requests` / `httpx`）—— 零依赖、毫秒级
- `browser_navigate` 走 **Playwright** —— 处理 JS 渲染场景
- 默认 `extract_content=True` —— LLM 拿到的是 Readability 提取后的干净 Markdown
- `format='json'` 给 API 调用场景
- 所有 tool 默认 `timeout=15s`、可配最大 `60s`
- `browser_install` 工具级自愈回路
- SSRF 防护 3 道关（协议 + 主机名 + DNS IP + redirect 二次校验）
- 错误分类（4xx/5xx/DNS/超时）

**依赖新增**：
- `playwright` (Python) + `playwright install chromium`（首次自动）
- `readability-lxml` (Mozilla Readability Python 实现)
- `markdownify` (HTML → Markdown)
- `selectolax` 或 `beautifulsoup4` (HTML 解析)
- 现有 `requests` 保留（HTTP fetch 路径）

**Removed 依赖**：无（`requests` 继续用）

---

## 11. mcp-aoai-web-browsing 补充发现（基于第 4 份报告）

**项目一句话定位**：Python + Azure OpenAI + Playwright 的"最小" MCP server，9 个 tool + 2 resource + 1 prompt，基于 FastMCP 框架，定位是 @microsoft/playwright-mcp 的极简 Python 复刻。

### 11.1 浏览器启动的"懒加载单例"模式 —— 强烈建议

**频次**：1/7 显式（`mcp-aoai-web-browsing` `server/browser_manager.py:10-31` `ensure_browser()`）

**典型实现**：
```python
class BrowserManager:
    async def ensure_browser(self):
        if not self.browser:                    # 懒加载
            self._playwright = await async_playwright().start()
            self.browser = await self._playwright.chromium.launch(headless=False)
            context = await self.browser.new_context(viewport={...})
            self.page = await context.new_page()
        return self.page
```
**优势**：首次 tool 调用时启动 Chromium，后续 tool 复用同一个 page。**避免每个 tool 重复启停 Chromium（每次 1-3s）**。

**Onion 启示**：**强烈建议**。Onion 的 `non_head_browser.py` 应当：
- 维护一个 `BrowserManager` 单例
- `browser_navigate` / `browser_screenshot` / `browser_click` 都走 `await ensure_browser()` 获取同一个 page
- 第一次调用时才启动 Chromium（懒加载）
- 避免每个 tool 重复启停

### 11.2 LLM 推断 CSS Selector 工具 —— 强烈建议（创新点）

**频次**：1/7 独有（`mcp-aoai-web-browsing` `extract_selector_by_page_content` 工具）

**典型实现**（`browser_navigator_server.py:150-172`）：
```python
@self.mcp.tool()
async def extract_selector_by_page_content(user_message: str) -> str:
    """Try to find a css selector by current page content."""
    page = await self.browser_manager.ensure_browser()
    html_content = await page.content()  # 整页 HTML

    prompt = (
        "Given the following HTML content of a web page:\n\n"
        f"{html_content}\n\n"
        f"User request: '{user_message}'\n\n"
        "Provide the CSS selector that best matches the user's request. Return only the CSS selector."
    )
    llm_response = await self.llm_client.invoke_with_prompt(prompt)
    return llm_response.content.strip()
```

**优势**：
- 让 LLM 在"看不清 DOM"时主动调用，**避免硬编码 selector 的脆弱性**
- 用 LLM 调用成本换"用户友好"
- 适合"动态 class 名 / shadow DOM / 复杂嵌套"场景

**反面教材**：
- `page.content()` 整页 HTML 塞进 prompt——**无任何截断**（`browser_navigator_server.py:160-165`）
- 大页面 1-5MB HTML → 击穿 LLM context window + token 费用爆炸
- 报告标注"未解决的工程缺陷"

**Onion 启示**：**强烈建议**（但**必须**先解决 HTML 截断问题）。Onion 应当：
1. 先实现 HTML 截断 + `<script>/<style>` 剥离（继承 §5.3 + §4.4）
2. 在浏览器工具集里加 `find_selector(description: str)` 工具
3. 内部走"截断后的 HTML → 嵌入到 prompt → LLM 推断 selector"流程

### 11.3 Docker 镜像构建时**必须**装 Chromium —— 必做（强化 §2.1）

**反面教材**：
- `mcp-aoai-web-browsing` `Dockerfile:14-15` 用 `uv sync` 装 Python 包，**但 Dockerfile 也没有任何 `playwright install` / `playwright install --with-deps chromium` 步骤**——**容器内启动必崩**（无 Chromium 二进制）

**Onion 启示**：**必须做**。强化 §2.1：Onion 的 `Dockerfile` 中**必须**显式：
```dockerfile
RUN pip install playwright
RUN playwright install --with-deps chromium
```
且 `entrypoint` 默认 `headless=True`（避免 X server 缺失）。

### 11.4 反面教材集合（来自 mcp-aoai-web-browsing）

| 反例 | 位置 | 风险 | Onion 规避 |
|------|------|------|-----------|
| `headless=False` 硬编码 | `browser_manager.py:13` | Linux 服务器 / Docker 启动必崩（缺 X server） | Onion 默认 `headless=True` + env var 可切 |
| `page.content()` 不截断 | `browser_navigator_server.py:160-165` | 击穿 LLM context window | Onion 必做 HTML 截断（§5.3） |
| 截图 base64 无 size 限制 | `browser_navigator_server.py:55-57` | 3MB base64 直塞 MCP 消息 | Onion 加 `max_size_mb=1.0` 硬上限（§5.5） |
| 死参数 `width` / `height` | `browser_navigator_server.py:36` 没用 | API 误导 | Onion 严格 schema 校验 |
| `extract_selector_by_page_content` 缺防护 | `browser_navigator_server.py:160-165` | HTML 全文塞 prompt | Onion 必须先做截断再 LLM 推断 |
| Docker 镜像无 `playwright install` | `Dockerfile:14-15` | 容器启动必崩 | Onion 必做 §11.3 |
| 无 `executablePath` / `channel` | `browser_manager.py:13` | 信创合规场景（国产浏览器）无法支持 | Onion 加 `executable_path` / `channel` 参数（§2.4） |
| 无 `playwright install` 文档 | README 第 52-56 行 | 用户首跑必踩坑 | Onion README 必明示 `playwright install chromium` |
| `playwright_navigate` 无重试 | `browser_navigator_server.py:31-32` | 网络抖动一次性失败 | Onion 加 2-3 次重试（§3.6） |
| `extract_selector_by_page_content` 用 LLM 调用换用户友好 | `browser_navigator_server.py:150-172` | **正面案例** | Onion 应当借鉴，但要加 HTML 截断防护 |

### 11.5 可借鉴设计

| 设计 | 位置 | 价值 |
|------|------|------|
| `BrowserManager.ensure_browser()` 懒加载单例 | `browser_manager.py:10-31` | 避免每次启停 Chromium（继承 §11.1） |
| `extract_selector_by_page_content` 工具 | `browser_navigator_server.py:150-172` | LLM 主动找元素（继承 §11.2） |
| MCP resource 暴露 `console://logs` 和 `screenshot://{name}` | `browser_navigator_server.py:188-207` | 让 LLM 能"查"历史 console / 截图，不只是调工具 |
| MCP prompt `hello_world` | `browser_navigator_server.py:210-212` | 给出 example prompt 引导 LLM 怎么用 |

**MCP resource** 是 mcp-aoai-web-browsing 的特色——Onion 可以借鉴 `console://logs`（暴露浏览器 console 日志）+ `screenshot://{name}`（按名字取历史截图）。

---

## 12. mcp-playwright-ea 补充发现（基于第 5 份报告，v1.0.12, 2.5k+ stars）

**项目一句话定位**：TypeScript 版**最流行**的 Playwright MCP server，**32 个 tool**（4 codegen + 5 API + 23 browser），支持 Chromium/Firefox/WebKit 三引擎、HTTP/SSE + stdio 双传输、代码生成、API 请求、文件上传、143 设备预设模拟。v1.0.12（2025-12-12）起实现自动浏览器安装。

### 12.1 v1.0.12 自动安装浏览器实现 —— 必做（精化 §2.1）

**核心实现**（`src/toolHandler.ts:164-216`）：

```ts
async function installBrowsers(browserType: string = 'chromium') {
  const installProcess = spawn('npx', ['playwright', 'install', browserType], {
    stdio: ['ignore', 'pipe', 'pipe']   // CHANGELOG v1.0.12: 移除 shell:true (安全改进)
  });
  // ... 监听 stdout/stderr ...
  setTimeout(() => { installProcess.kill(); resolve({...失败...}); }, 120000);   // 2 分钟超时
}
```

**触发链路**（2 处）：
- `toolHandler.ts:272-294` `ensureBrowser` 首次 `browserInstance.launch()` 抛错时
- `toolHandler.ts:340-354` `ensureBrowser` catch 兜底分支里再次触发

**触发条件**（依赖错误消息文本匹配，**脆弱**）：
- `Executable doesn't exist`
- `Failed to launch`
- `browserType.launch`

**Onion 启示**：**必做**。Onion 的 `non_head_browser.py` 应当**完整照搬**这套机制：
- `subprocess.run(['playwright', 'install', 'chromium'], timeout=120)` + 2 分钟超时
- 检测 `playwright._impl._errors.Error: Executable doesn't exist` 抛错
- 自动重试一次 + 失败抛清晰错误

### 12.2 `CHROME_EXECUTABLE_PATH` 环境变量支持本地浏览器路径 —— 强烈建议（精化 §2.4）

**实现**（`src/toolHandler.ts:263-268`）：
```ts
const executablePath = process.env.CHROME_EXECUTABLE_PATH;
try {
  browser = await browserInstance.launch({ headless, executablePath });
```
- `executablePath` 环境变量**未在 README 提及**——只能从源码或测试用例发现
- 只支持 `executablePath`，**不支持** `channel: 'chrome' | 'msedge'`
- **对所有 browserType 都生效**（不是只服务 Chrome，命名有误导）

**Onion 启示**：**强烈建议**。Onion 的 `non_head_browser.py` 应当：
- 接受 `executable_path` 参数（**优先**于环境变量）
- 也支持 `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH` / `PLAYWRIGHT_FIREFOX_EXECUTABLE_PATH` 环境变量
- 信创合规场景：用户配置 `executable_path='/usr/bin/麒麟浏览器/chrome'`

### 12.3 32 个 tool 详细分类（**禁止**照抄全部）

**4 个 Codegen 工具**：
- `start_codegen_session` / `end_codegen_session` / `get_codegen_session` / `clear_codegen_session`
- 录制期间，所有非 `playwright_close` 工具调用会被 `ActionRecorder` 记录
- `end_codegen_session` 用 `PlaywrightGenerator` 生成 Playwright Test 风格 `.spec.ts` 文件

**5 个 API 工具**（HTTP 方法级别）：
- `playwright_get` / `playwright_post` / `playwright_put` / `playwright_patch` / `playwright_delete`
- 基于 `playwright.request.newContext()`（无浏览器启动，纯 HTTP 客户端）
- 响应体**硬截 1000 字符**

**23 个 Browser 工具**：

| 类别 | 工具 | 数量 | 说明 |
|------|------|------|------|
| **导航** | `playwright_navigate` / `go_back` / `go_forward` / `close` | 4 | navigate 用 `page.goto({ timeout, waitUntil: 'load' })` |
| **交互** | `playwright_click` / `iframe_click` / `iframe_fill` / `fill` / `select` / `hover` / `drag` / `press_key` / `upload_file` / `click_and_switch_tab` | 10 | 完整浏览器自动化 |
| **提取** | `playwright_get_visible_text` / `playwright_get_visible_html` / `playwright_console_logs` / `playwright_evaluate` | 4 | 文本/HTML/console 提取 |
| **截图/PDF** | `playwright_screenshot` / `playwright_save_as_pdf` | 2 | screenshot 永远 PNG 无压缩 |
| **设备/UA** | `playwright_resize` / `playwright_custom_user_agent` | 2 | 143 设备预设 |
| **网络** | `playwright_expect_response` / `playwright_assert_response` | 2 | wait + 校验 HTTP 响应 |

**Onion 启示**：**禁止** Onion 抄 32 个 tool 全部。Onion MVP 工具集只抄"导航 / 提取 / 截图" 3 大类约 5-7 个 tool（参考 §9.1）。

**值得抄的细分设计**：
- `playwright_click_and_switch_tab` —— `context.waitForEvent('page')` + `setGlobalPage`（**自动接管新 tab**，参考 §playwright-plus-python-mcp §4.3）
- `playwright_save_as_pdf` —— 完整 PDF 保存（`page.pdf({ path, format, margin })`）
- `playwright_resize` —— 143 设备预设模拟（`page.setViewportSize` + `playwright.devices`）

### 12.4 HTML 截断 vs 提取：3 项目对比

| 项目 | 截断方式 | Readability | Markdown 转换 | 默认截断阈值 |
|------|---------|------------|--------------|-------------|
| `mcp-playwright-ea` | 头切（`slice(0, 20000)`） | ❌ | ❌ | 20000 字符 |
| `fetcher-mcp` | 头切（`substring(0, maxLength)`） | ✅ `@mozilla/readability` | ✅ `turndown` + GFM | 用户可配 |
| `fetch-mcp` | 头切 + `start_index` 分页 | ✅ `@mozilla/readability` | ✅ `turndown` | 默认 5000 字符 |
| `playwright-plus-python-mcp` | `text_content[:200]` | ❌ | ❌ | 200 字符 |
| `mcp-aoai-web-browsing` | **不截断**（`page.content()` 全文） | ❌ | ❌ | **无限制**（反面教材） |

**Onion 启示**：**必做**。Onion 应当**学 fetcher-mcp**：
- 默认 `extract_content=True` → 走 Readability
- 默认 `format='markdown'` → 走 turndown
- 截断阈值 20000 字符，但**先 Readability + Markdown 转换再截断**（避免截断 HTML 标签）
- 用"头+尾"模式（保留前 50% + 后 50%），**不要**单纯头切

### 12.5 HTTP/SSE 双传输模式 —— 强烈建议

**实现**（`src/index.ts:12-69` + `src/http-server.ts`）：

| 模式 | 启动命令 | 传输层 | 适用 |
|------|---------|--------|------|
| **stdio**（默认） | `playwright-mcp-server` | `StdioServerTransport` | Claude Desktop |
| **HTTP/SSE** | `playwright-mcp-server --port 8931` | Express + `SSEServerTransport` | VS Code Copilot / 远程部署 / 多客户端 |

**HTTP 模式关键设计**：
- **绑定 127.0.0.1**（`src/http-server.ts:217-221`）—— **安全**，外部不可直连
- 双 endpoint 兼容：`/sse` + `/messages?sessionId=...`（旧）/ `/mcp` + `/mcp?sessionId=...`（新）
- `/health` 探活 endpoint
- 每个 session 一个新 `Server` 实例，支持多客户端并发

**stdio 模式日志行为**：
- 仅写文件 `${HOME || '/tmp'}/playwright-mcp-server.log`，**不写 stdout**（避免污染 JSON-RPC）
- 监控 HTTP 端口在 stdio 模式下禁用

**Onion 启示**：**强烈建议**。Onion 的 `non_head_browser.py` 应当：
- 默认 **stdio**（onion-agent 进程内嵌使用）
- 支持 `--transport=http --port=8931` 起 HTTP server（**默认 127.0.0.1 绑定**）
- 日志走文件 `~/.onion/logs/non_head_browser.log`，**不要**污染 stdout
- 给 HTTP 模式加 `/health` 探活

### 12.6 反面教材集合（来自 mcp-playwright-ea）

| 反例 | 位置 | 风险 | Onion 规避 |
|------|------|------|-----------|
| HTML 截断仅头切 20000 字符 | `src/tools/browser/visiblePage.ts:186-188` | 丢关键尾部内容 | Onion 用"头+尾"截断 + Readability + Markdown |
| 无 Readability / Markdown 转换 | 全局 | 浪费 LLM context | Onion 必做 §4.1+§4.2 |
| screenshot 永远 PNG 无 quality | `src/tools/browser/screenshot.ts:22` | 大图片 base64 爆 MCP 消息 | Onion 加 `type='jpeg'` + `quality=80` |
| screenshot `storeBase64: true` 默认 | `src/tools/browser/screenshot.ts:58` | 内存风险 | Onion 加 `max_size_mb=1.0` 硬上限 |
| API 工具 1000 字符硬截 | `src/tools/api/requests.ts:113, 159, 205, 251, 286` | 太短 | Onion 必做 `max_length` 可配 |
| `playwright_console_logs` 无界增长 | `src/tools/browser/console.ts:8` | 长会话 OOM | Onion 加 `max_logs=1000` 滚动 |
| 多 session 共享 module-level browser | `src/toolHandler.ts:51-53` | 并发客户端互相干扰 | Onion 用 per-session 隔离 |
| `playwright_expect_response` promise 永 hang | `src/tools/browser/response.ts:21-37` | 内存泄漏 | Onion 用 `Promise.race` + timeout |
| `playwright_custom_user_agent` 是 validator 不是 setter | `src/tools/browser/useragent.ts:22-32` | API 文档漂移 | Onion 严格 schema 校验 + 文档同步 |
| `waitUntil` 默认 `'load'` 而非 `'networkidle'` | `src/tools/browser/navigation.ts:33` | SPA 内容拿不全 | Onion 默认 `'networkidle'`（但要 timeout 兜底） |
| `CHROME_EXECUTABLE_PATH` 未在 README 提及 | `src/toolHandler.ts:263-268` | 文档漂移 | Onion README 必明示 |
| 触发自动安装依赖错误消息文本匹配 | `src/toolHandler.ts:272-294` | 脆弱 | Onion 走 `try/except` + `isinstance(e, PlaywrightError)` |

### 12.7 关键设计可借鉴

| 设计 | 位置 | 价值 |
|------|------|------|
| `installBrowsers()` 自动安装 | `src/toolHandler.ts:164-216` | 降低用户门槛（继承 §2.1） |
| `CHROME_EXECUTABLE_PATH` 环境变量 | `src/toolHandler.ts:263-268` | 信创合规（继承 §12.2） |
| HTTP 模式 127.0.0.1 绑定 | `src/http-server.ts:217-221` | 安全（继承 §12.5） |
| stdio 模式日志写文件 | `src/index.ts:73-80` | 不污染 JSON-RPC（继承 §12.5） |
| 5 个 API 工具（GET/POST/PUT/PATCH/DELETE） | `src/tools/api/requests.ts:87-289` | 完整 REST API 客户端 |
| 设备预设（143 设备） | `src/tools/browser/resize.ts:8-114` | 移动端/平板/桌面测试 |
| 网络响应断言（expect/assert） | `src/tools/browser/response.ts:21-86` | 测试场景 |
| PDF 保存 | `src/tools/browser/output.ts:8-30` | 长网页归档 |

### 12.8 工具数膨胀的反思

mcp-playwright-ea 的 32 个 tool **严重违反 `standard/tool_channel.md §4.7` Tool Search 渐进式披露原则**——所有 tool 都注入 system prompt，LLM 选错概率高，token 成本翻倍。

**Onion 启示**：**必做**。Onion MVP 工具集**严格控制在 5-7 个**，P1 加 `tool_search` meta 工具处理更多。

---

## 13. MCP-Server-Playwright 补充发现（基于第 6 份报告，14 files / 0.07 MB）

**项目一句话定位**：Automata Labs 团队的**极简** Playwright MCP server，**10 个 tool**（navigate / screenshot / click / click_text / fill / select / select_text / hover / hover_text / evaluate），**完全没有 fetch 工具**。整个项目就是单文件 `index.ts`（758 行）+ 配置文件。

### 13.1 "strict mode violation 自动 `.first()` 重试" 模式 —— 强烈建议

**核心实现**（`index.ts:233-273`）：

```typescript
try {
  await page.locator(args.selector).click();
  return { /* success */ };
} catch (error) {
  if ((error as Error).message.includes("strict mode violation")) {
    // LLM 给的 selector 经常匹配多个 → 自动退到第一个
    try {
      await page.locator(args.selector).first().click();
      return { /* success */ };
    } catch (error) { /* fall through */ }
  }
  return { /* error */ };
}
```

**适用范围**：`browser_click` / `browser_click_text` / `browser_fill` / `browser_select` / `browser_hover` **全部一致**。

**价值**：LLM 给的 CSS selector 经常匹配多个元素，原生 Playwright 抛 `strict mode violation` 错误。**自动 `.first()` 重试**比让 LLM 看到错误更友好。

**Onion 启示**：**强烈建议**。Onion 的 `non_head_browser.py` 应当：
- `browser_click` / `browser_fill` / `browser_hover` / `browser_select` 内部 try/catch `strict mode violation` 错误
- 自动 fallback `page.locator(selector).first().click()` 重试一次
- 只在 `.first()` 也失败时才返回 `is_error: true`

### 13.2 "单文件 + TOOLS 集中数组" 代码组织 —— 可选（仅 MVP）

**实现**（`index.ts:36-152`）：所有 10 个 tool 的 schema 集中在一个 `TOOLS` 数组里，没有拆 `tools/navigate.py` + `tools/click.py` 等独立文件。

**价值**：
- 14 files / 758 行就能维护 10 个 tool
- 早期项目代码组织"扁平"比"模块化"更易调试
- 所有 tool 的 schema 集中可见，一眼能 review

**Onion 启示**：**可选**（仅 MVP）。Onion 早期（tool 数 ≤ 5）可以借鉴"单文件 + 集中数组"。**但 Onion 是 Python**（不是 TypeScript），Python 没有 enum 类型，用 dataclass / Literal 替代。P1 工具数到 10+ 时再拆 `buildin_browser/*.py`。

### 13.3 反面教材集合（来自 MCP-Server-Playwright）

| 反例 | 位置 | 风险 | Onion 规避 |
|------|------|------|-----------|
| `headless: false` 硬编码 | `index.ts:162` | 服务器 / Docker / WSL 无 GUI 跑不起来 | Onion 默认 `headless=True` + env var 可切 |
| 用 Firefox 而非 Chromium | `index.ts:162` `playwright.firefox.launch` | Firefox binary 体积比 chromium 大，国内下载慢；v1.1.0→v1.2.1 反复横跳说明稳定性差 | Onion 默认 Chromium（信创场景用国产套件） |
| `browser_navigate` 失败无 try/catch | `index.ts:184-192` | Playwright 抛异常直接冒到 MCP 协议层 | Onion 必做 §6.7 错误分类 |
| `browser_navigate` 不传 timeout/waitUntil | `index.ts:184-192` | 用 Playwright 默认 30s + 'load' | Onion 必做 §3.4 + §3.5 |
| `page.goto(url)` 不返回 HTML / 标题 / 状态码 | `index.ts:184-192` | navigate 后 LLM 不知道页面内容 | Onion navigate 默认返回 title + 截断后的 HTML（继承 §4） |
| `fullPage === 'true'` 字符串比较 Bug | `index.ts:195` | 永远 false，**类型校验要严格** | Onion 用 `bool(args.full_page)` 强转 + Pydantic 校验 |
| 截图 `screenshots` Map 永不清理 | `index.ts:158` | 长跑 OOM | Onion 必做 LRU + 数量上限（继承 §5.5） |
| 截图无 size 限制 | `index.ts:200` | 大图片 base64 爆 MCP 消息 | Onion 加 `max_size_mb=1.0`（继承 §5.5） |
| `install` 子命令不支持 Linux | `index.ts:649-737` | Linux 用户跑 `npx mcp-server-playwright install` 直接 `process.exit(1)` | Onion 跨平台自动检测 |
| Dockerfile 没装 Firefox binary | `Dockerfile:1-31` | 容器启动必崩 | Onion 必做 §2.6 Docker 集成 |
| v1.1.0→v1.2.1 浏览器横跳 | `CHANGELOG.md:5-7` | 上游稳定性差 | Onion 锁定 Chromium + 国产套件 fallback |
| `browser_evaluate` 用 `eval()` | `index.ts:521-561` | 无沙箱、无超时 | Onion 用 `page.evaluate` 沙箱 + 30s timeout |

### 13.4 关键设计可借鉴

| 设计 | 位置 | 价值 |
|------|------|------|
| `strict mode violation` 自动 `.first()` 重试 | `index.ts:233-273` | LLM 友好（继承 §13.1） |
| 单文件 + TOOLS 集中数组 | `index.ts:36-152` | 早期易维护（继承 §13.2） |
| console 事件 → `notifications/resources/updated` 推送 | `index.ts:172-175` | 客户端实时刷新 console |
| `install` 子命令 + Claude Desktop 配置写入 | `index.ts:649-737` | 降低用户门槛 |
| 10 个 tool 全部支持"按文字"和"按 selector"两种定位 | `browser_click` / `browser_click_text` | LLM 友好 |

### 13.5 与 mcp-playwright-ea 的对比

| 维度 | MCP-Server-Playwright（极简） | mcp-playwright-ea（完整） |
|------|-----------------------------|-------------------------|
| 文件数 | 14 | 139（含 chromium binary 29MB） |
| 代码量 | 758 行（单 index.ts） | 数万行（按 tools/ 拆分） |
| tool 数 | 10 | 32 |
| fetch 工具 | ❌ | ❌（5 个 API 工具，但定位是 REST 客户端不是 fetch） |
| HTML 提取 | ❌ | ✅ `playwright_get_visible_html` |
| Readability / Markdown | ❌ | ❌ |
| 自动浏览器安装 | ❌ | ✅ v1.0.12 |
| 浏览器 | Firefox + headless=False | Chromium/Firefox/WebKit + 默认 headless |
| `executablePath` | ❌ | ✅ `CHROME_EXECUTABLE_PATH` |
| Strict mode 重试 | ✅ `.first()` | ❌ |
| MCP resource | ✅ `console://logs` + `screenshot://<n>` | ✅ 类似 |
| LLM 友好度 | 高（小而精） | 中（tool 太多） |
| **Onion 借鉴价值** | **strict mode 重试 + 单文件组织** | **自动安装 + executablePath** |

**Onion 启示**：**不抄任意单一项目，而是融合两者优点**：
- **从 MCP-Server-Playwright** 借：`strict mode violation .first()` 重试 + 单文件组织（MVP）
- **从 mcp-playwright-ea** 借：自动安装 + `executablePath` 环境变量 + HTTP/SSE 双传输
- **从 fetcher-mcp** 借：Readability + turndown 4 种输出格式
- **从 fetch-mcp** 借：SSRF 3 道关 + 响应字节上限 10MB

---

## 14. 最终总结：Onion Agent `non_head_browser.py` 重构方案

### 14.1 5 大流派的最佳借鉴组合

| 流派 | 来源 | 借鉴什么 |
|------|------|----------|
| **A 派**（纯 HTTP fetch）| fetch-mcp | SSRF 3 道关 + 响应字节上限 + 流式读取 + 原生 fetch |
| **B 派**（Playwright 只读）| fetcher-mcp | Readability + turndown + 资源屏蔽 + 反爬虫指纹 |
| **B 派补强**| mcp-playwright-ea | 自动安装 v1.0.12 + `executablePath` 环境变量 |
| **C 派**（全功能 Playwright）| mcp-playwright-ea / MCP-Server-Playwright | 32 tool 中精选 + strict mode `.first()` 重试 |
| **Python 派**| mcp-aoai-web-browsing | BrowserManager 懒加载单例 + LLM 推断 selector（创新点） |

### 14.2 重构后的工具签名（MVP）

```python
# 5 个核心工具（MVP）
def fetch_url(
    url: str,
    format: str = "markdown",                    # "html" | "markdown" | "text" | "json"
    extract_content: bool = True,                # Mozilla Readability
    max_chars: int = 20000,
    timeout: int = 15,
    headers: dict | None = None,
) -> dict: ...                                    # 走 requests/httpx + Readability + turndown

def fetch_urls(
    urls: list[str],
    format: str = "markdown",
    extract_content: bool = True,
    max_chars: int = 20000,
    timeout: int = 15,
    max_concurrent: int = 5,
) -> dict: ...                                    # asyncio.Semaphore 并发

def browser_navigate(
    url: str,
    wait_until: str = "networkidle",             # "load" | "domcontentloaded" | "networkidle" | "commit"
    timeout: int = 30,
    disable_media: bool = True,
    executable_path: str | None = None,
    channel: str | None = None,
    proxy: str | None = None,
    headers: dict | None = None,
) -> dict: ...                                    # 走 Playwright

def browser_screenshot(
    url: str,
    selector: str | None = None,
    full_page: bool = True,
    image_type: str = "jpeg",                    # "png" | "jpeg"
    quality: int = 80,
    max_size_mb: float = 1.0,
) -> dict: ...                                    # 走 Playwright

def browser_install(
    with_deps: bool = False,
    force: bool = False,
    timeout: int = 120,                          # 2 分钟超时
) -> dict: ...                                    # subprocess.run(['playwright', 'install', 'chromium'])
```

**P1 扩展**（如果 MVP 跑得顺）：
- `browser_click` / `browser_fill` / `browser_hover` / `browser_select`（继承 MCP-Server-Playwright §13.1 strict mode 重试）
- `browser_evaluate`（带 console 拦截 + 30s timeout）
- `browser_click_and_switch_tab`（继承 mcp-playwright-ea §12.7 + playwright-plus-python-mcp §4.3）
- `find_selector(description: str)`（继承 mcp-aoai-web-browsing §11.2 创新点）
- `browser_resize(device: str)`（继承 mcp-playwright-ea §12.7 设备预设）

### 14.3 关键设计决策（对比当前 `non_head_browser.py`）

| 维度 | 当前实现 | 重构后 | 借鉴来源 |
|------|---------|--------|----------|
| 抓取层 | `requests.get` | **双模式**：`requests`（默认）+ Playwright（fallback） | 行业共识 |
| HTML 处理 | `_html_to_text`（粗略剥标签） | **Readability + turndown** | fetcher-mcp / fetch-mcp |
| HTML 截断 | 头+尾（20000 字符）| **先 Readability 提取 → 转 Markdown → 头+尾截断** | fetcher-mcp + tool_channel §6.7 |
| 响应字节上限 | 无 | **10MB（content-length 预检 + 流式累加）** | fetch-mcp |
| SSRF 防护 | 无 | **3 道关（协议 + 主机名 + DNS IP + redirect 二次校验）** | fetch-mcp |
| 浏览器安装 | 无 | **post-install hook + 自动检测 + 2 分钟超时** | mcp-playwright-ea v1.0.12 |
| 本地浏览器 | 无 | **`executable_path` 参数 + `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH` env** | mcp-playwright-ea |
| 反爬虫 | 无 | **隐藏 webdriver + 随机 UA + 资源屏蔽** | fetcher-mcp |
| 错误分类 | 简单 try/except | **4xx/5xx/DNS/timeout 分类 + isError 回传** | fetch-mcp |
| BrowserManager | 无 | **懒加载单例 + console 累积 + LRU 清理** | mcp-aoai-web-browsing + MCP-Server-Playwright |
| Strict mode 重试 | 无 | **`.first()` 自动重试** | MCP-Server-Playwright |
| MCP resource | 无 | **`console://logs` + `screenshot://<name>`** | MCP-Server-Playwright + mcp-aoai-web-browsing |
| HTTP/SSE 模式 | 无 | **stdio 默认 + `--port 8931` HTTP 模式（127.0.0.1 绑定）** | mcp-playwright-ea |
| stdio 日志 | 无 | **写 `~/.onion/logs/non_head_browser.log`，不污染 stdout** | mcp-playwright-ea |
| 工具数 | 2 个 | **5-7 个（MVP）** | Onion 原则 |

### 14.4 依赖新增

```python
# requirements.txt 新增
playwright>=1.48.0
readability-lxml>=0.8.1
markdownify>=0.11.6
selectolax>=0.3.21            # 或 beautifulsoup4（备选）
beautifulsoup4>=4.12.0        # 备选，用于复杂 HTML
tenacity>=8.2.0               # 重试装饰器

# install hooks
# postinstall: playwright install chromium
```

**Removed 依赖**：无（`requests` 保留）

### 14.5 6 个项目对比一览（最终矩阵）

| 维度 | fetch-mcp | fetcher-mcp | playwright-plus-python-mcp | mcp-playwright-ea | MCP-Server-Playwright | mcp-aoai-web-browsing |
|------|-----------|-------------|--------------------------|-------------------|----------------------|----------------------|
| 流派 | A（HTTP）| B（Playwright 只读）| C（Playwright 全功能）| C（Playwright 全功能）| C（Playwright 极简）| C（Playwright 极简）|
| 语言 | TypeScript | TypeScript | Python | TypeScript | TypeScript | Python |
| tool 数 | 6 | 3 | 8 | 32 | 10 | 9+2+1 |
| fetch 工具 | ✅ 6 个 | ✅ 1 个 | ❌ | ❌（5 API 工具）| ❌ | ❌ |
| 自动浏览器安装 | N/A | ✅ 三重 | ❌ | ✅ v1.0.12 | ❌ | ❌ |
| 浏览器 | N/A | Chromium | Chromium | C/F/W | Firefox | Chromium |
| 默认 headless | N/A | True | **False** | True | **False** | **False** |
| executablePath | N/A | ❌ | ❌ | ✅ env var | ❌ | ❌ |
| SSRF 防护 | ✅ 3 道关 | 协议白名单 | ❌ | ❌ | ❌ | ❌ |
| Readability | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| Markdown 转换 | ✅ turndown | ✅ turndown + GFM | ❌ | ❌ | ❌ | ❌ |
| HTML 截断阈值 | 5000 字符 | 可配（默认 0）| 200 字符 | 20000 字符 | N/A | **不截断** |
| 截断方式 | 头 + start_index | 头切 | 头切 | 头切 | N/A | 无 |
| 响应字节上限 | 10MB | ❌ | ❌ | ❌ | ❌ | ❌ |
| 反爬虫 | UA 默认 | ✅ 指纹全套 | ❌ | ❌ | ❌ | ❌ |
| 资源屏蔽 | N/A | ✅ 默认 | N/A | ❌ | ❌ | ❌ |
| Strict mode 重试 | N/A | ❌ | ❌ | ❌ | ✅ `.first()` | ❌ |
| 浏览器自愈 | N/A | ✅ tool | ❌ | ✅ 自动重试 | ❌ | ❌ |
| MCP resource | ❌ | ❌ | ❌ | ❌ | ✅ 2 个 | ✅ 2 个 |
| LLM 推断 selector | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ 创新点 |
| 错误分类 | ✅ 7 种 | 模糊 | ❌ | ❌ | ❌ | ❌ |
| HTTP/SSE 模式 | ❌ | ✅ | ❌ | ✅ | ❌ | ❌ |
| Docker 集成 | ❌ | ✅ | ❌ | ❌ | ❌ | **❌ 无 install** |
| 总体评价 | **零依赖标杆** | **反爬虫标杆** | **反面教材多** | **最完整 + v1.0.12 自动安装** | **strict mode 重试亮点** | **LLM 推断 selector 创新** |

### 14.6 MVP 实施优先级

**P0（MVP 必须做）**：
1. 双模式抓取层（`fetch_url` 走 HTTP / `browser_navigate` 走 Playwright）
2. Readability + turndown 内容提取
3. SSRF 3 道关（协议 + 主机名 + DNS IP）
4. 响应字节上限 10MB（流式累加）
5. 错误分类（4xx/5xx/DNS/timeout）
6. 自动安装 v1.0.12 模式（`browser_install` tool + 2 分钟超时）
7. `executable_path` 参数 + `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH` env
8. 头+尾截断 20000 字符（保留前 50% + 后 50%）

**P1（增强）**：
1. `browser_click/fill/hover/select` 4 个交互类（带 strict mode `.first()` 重试）
2. `browser_evaluate` JS 执行（带 console 拦截 + 30s timeout）
3. 反爬虫指纹注入（隐藏 webdriver + 资源屏蔽）
4. MCP resource 暴露 `console://logs` + `screenshot://<name>`
5. HTTP/SSE 模式（`--port 8931`）

**P2（高级）**：
1. `browser_resize` 设备模拟（143 设备预设）
2. `find_selector(description)` LLM 推断 selector
3. `browser_save_as_pdf` PDF 保存
4. 多浏览器（Chromium / Firefox / WebKit）

---

## 15. 6 份报告索引

完整 6 份单项目调研报告：

1. **`fetch-mcp/playwright.md`** —— 21.6 KB，zcaceres/fetch-mcp v1.1.2，**纯 HTTP fetch 路线**
2. **`fetcher-mcp/playwright.md`** —— 18.1 KB，jae-jae/fetcher-mcp v0.3.9，**Playwright + Readability + turndown 极简路线**
3. **`playwright-plus-python-mcp/playwright.md`** —— 22.3 KB，blackwhite084，**Playwright Python 8 tool 路线**
4. **`mcp-playwright-ea/playwright.md`** —— 29.4 KB，executeautomation v1.0.12 (2.5k+ stars)，**最流行 + 32 tool + 自动安装**
5. **`MCP-Server-Playwright/playwright.md`** —— 21 KB，Automata-Labs-team，**14 files 极简版 + strict mode `.first()` 重试**
6. **`mcp-aoai-web-browsing/playwright.md`** —— 19.6 KB，kimtth，**Python + Azure OpenAI 极简版 + LLM 推断 selector 创新**

每份报告都按统一模板（5 节）撰写，**所有结论附 `file:line` 引用**，可追溯。

---

**调研完成时间**：2026-07-23  
**提炼人**：Onion Agent Mavis  
**标准总字数**：约 50 KB（11 + §12 + §13 + §14 + §15 章节）

