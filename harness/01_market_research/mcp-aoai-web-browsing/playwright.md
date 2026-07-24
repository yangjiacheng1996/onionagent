# mcp-aoai-web-browsing — Playwright 浏览器自动化调研报告

## 0. 项目一句话定位

Python + Azure OpenAI + Playwright 的"最小" MCP server/客户端实现，基于 `FastMCP` 暴露 9 个 Playwright 工具（含 LLM 辅助的 CSS 选择器提取），通过自研 `client_bridge` 把 MCP 工具定义转换为 OpenAI function-calling 格式以驱动 Azure OpenAI / 标准 OpenAI。本质是 @microsoft/playwright-mcp 的极简 Python 复刻（README 第 6 行直接引用 "MCP Playwright server" 与 "Microsoft Playwright for Python"）。

## 1. 调研依据

- 源码路径：`C:\workspace\github\onionagent\harness\01_market_research\clone\mcp-aoai-web-browsing`
- 关键文件（全部已完整阅读）：
  - `server/browser_navigator_server.py`（215 行，9 个 MCP tool 的全部定义）
  - `server/browser_manager.py`（41 行，Playwright 浏览器生命周期管理）
  - `client_bridge/bridge.py`（221 行，MCP-LLM bridge 主循环）
  - `client_bridge/mcp_client.py`（96 行，支持 in-process + stdio 两种连接）
  - `client_bridge/llm_client.py`（97 行，OpenAI/AzureOpenAI 客户端 + tool_call 循环）
  - `client_bridge/llm_config.py`（20 行，Azure / 标准 OpenAI 配置工厂）
  - `client_bridge/config.py`（34 行，Pydantic 配置模型）
  - `pyproject.toml`（依赖声明）
  - `Dockerfile`（Smithery 部署路径）
  - `chatgui.py`（Tkinter GUI demo，启动时建立 bridge）
  - `client_test.py`（命令行 REPL demo）
- 文档 / README 引用：
  - `README.md`（项目定位 + 安装 + Claude Desktop / VS Code 接入 + 工具说明）
  - `smithery.yaml`（部署元数据）
- 关键 grep 验证：
  - `@self.mcp.tool()` 共 9 处（`server/browser_navigator_server.py:24, 34, 62, 73, 84, 95, 106, 150, 175`）
  - 唯一一处 `chromium.launch` 在 `server/browser_manager.py:13`
  - 全仓库**无任何** `fetch` / `httpx` / `requests` / `User-Agent` / `executablePath` / `readability` / `turndown` / `markdown` 关键字

## 2. 三个核心问题的回答

### Q1. Playwright 无头浏览器安装

**结论：完全手动；用户必须自行执行 `playwright install`；无任何自动检测/自动安装；hard-code 为有头模式 (`headless=False`)；不支持本地已安装浏览器路径；未文档化国内/离线环境处理。**

- **依赖声明**：`pyproject.toml:8-19` 声明 `pytest-playwright>=0.7.2`（仅 Python 包，不含二进制）。注意：项目用 `pytest-playwright` 依赖间接拉入 `playwright`，**而非直接声明 `playwright`**，这是一个轻微的"间接依赖"特征。
- **安装步骤**：README 第 52-56 行只写 `pip install uv` + `uv sync`，**没有任何一步提示用户运行 `playwright install`**——完全依赖 `pytest-playwright` 自带的"首次 import 触发下载"行为，且 README 未明示。
- **自动检测/安装**：grep `playwright install` 全仓库**零命中**。`browser_manager.py:10-31` 的 `ensure_browser` 只检查 `if not self.browser`，不检查 Chromium 二进制是否缺失，缺失时会直接抛 Playwright 原始错误（被 `browser_navigator_server.py` 的 `try/except` 包成 `ValueError`）。
- **二进制存储路径**：未在源码/文档中显式说明；遵循 Playwright 默认（`%LOCALAPPDATA%\ms-playwright\` on Windows，`~/Library/Caches/ms-playwright/` on macOS，`~/.cache/ms-playwright/` on Linux）。
- **离线 / 国内网络**：**完全未文档化**。无 `PLAYWRIGHT_DOWNLOAD_HOST` / `PLAYWRIGHT_BROWSERS_PATH=0` / 国内镜像相关说明。`Dockerfile:14-15` 用 `uv sync` 装 Python 包，**但 `Dockerfile` 也没有任何 `playwright install` / `playwright install --with-deps chromium` 步骤**——意味着 Docker 镜像里**没有 Chromium 二进制**，容器内启动必崩。这是个明显的工程缺陷。
- **本地浏览器路径**：`browser_manager.py:13` 调用 `self._playwright.chromium.launch(headless=False)`，**没有 `executablePath` / `channel: 'chrome'` / `channel: 'msedge'` 任何参数**，无法直接挂本地 Chrome。
- **headless 模式**：`browser_manager.py:13` 写死 `headless=False`（有头模式）。这对桌面 GUI demo (`chatgui.py`) 是合理的（MCP server 跑在用户机器上、想看到浏览器），但**部署到 Linux 服务器 / Docker 时会因缺 X server / xvfb 直接失败**。`server/browser_navigator_server.py` 与 `browser_manager.py` 全局无 `headless` 开关、无环境变量读取。

### Q2. 浏览器自动化功能 + URL 访问 + HTML 压缩

#### Q2.1 工具清单（共 9 个 MCP tool）

| 工具名 | 类别 | 入参 | 返回 | 代码路径 |
|---|---|---|---|---|
| `playwright_navigate` | 导航 | `url: str, timeout=30000, wait_until="load"` | 文本 `"Navigated to {url} with {wait_until} wait"` | `browser_navigator_server.py:24-32` |
| `playwright_screenshot` | 提取 | `name: str, selector=None, width=800, height=600` | `TextContent` + `ImageContent`（base64 PNG） | `browser_navigator_server.py:34-60` |
| `playwright_click` | 交互 | `selector: str` | 文本 `"Clicked on {selector}"` | `browser_navigator_server.py:62-71` |
| `playwright_fill` | 交互 | `selector: str, value: str` | 文本 `"Filled {selector} with {value}"` | `browser_navigator_server.py:73-82` |
| `playwright_select` | 交互 | `selector: str, value: str` | 文本 `"Selected {value} in {selector}"`（`<select>` 下拉） | `browser_navigator_server.py:84-93` |
| `playwright_hover` | 交互 | `selector: str` | 文本 `"Hovered over {selector}"` | `browser_navigator_server.py:95-104` |
| `playwright_evaluate` | JS 执行 | `script: str` | 文本（拼接 `"Execution result:\n{json}\n\nConsole output:\n{logs}"`） | `browser_navigator_server.py:106-148` |
| `extract_selector_by_page_content` | 高级 | `user_message: str` | 字符串（**调用 LLM 推断 CSS selector**） | `browser_navigator_server.py:150-172` |
| `read_all_screenshots` | 资源读取 | `file_name_list: list[str], ctx: Context` | `"Processing complete"`，期间通过 `ctx.report_progress` 推送进度 | `browser_navigator_server.py:175-185` |

外加 2 个 MCP resource：

- `console://logs` — 返回 `self.browser_manager.console_logs` 累积列表（`browser_navigator_server.py:188-193`）
- `screenshot://{name}` — 按名字返回 `self.screenshots[name]` 的 base64 PNG（`browser_navigator_server.py:195-207`）

1 个 prompt：

- `hello_world` — `browser_navigator_server.py:210-212`

**工具数确实很少**（9 tool + 2 resource + 1 prompt），与项目"最小化"定位一致。与 @microsoft/playwright-mcp 的 21+ 工具相比，`mcp-aoai-web-browsing` 砍掉了 `browser_close` / `browser_resize` / `browser_navigate_back` / `browser_console_messages`（仅 resource 暴露）/ `browser_evaluate` 简化版 / `browser_take_screenshot`（同名但缺参数）/ `browser_install` / `browser_tab_*` 等。

**类别覆盖盲区**：
- **无 `go_back` / `go_forward` / `reload` / `new_page` / `close_page`**（导航类缺大半）
- **无 `get_visible_text` / `get_visible_html` / `get_attribute` / `get_url`**（提取类除了 screenshot 外几乎为零）
- **无 `press_key` / `drag` / `upload_file`**（交互类只有 click/fill/select/hover 4 个）
- **无 `wait_for_selector` / `wait_for_navigation` / `wait_for_timeout` 作为独立 tool**（仅在 click/fill/select/hover 内部隐式 `wait_for_selector`）
- **无 iframe / 多 tab / 设备模拟 / PDF 保存 / codegen**
- **`extract_selector_by_page_content` 是该项目独有特色**——用 LLM 把用户自然语言描述（如"登录按钮"）映射成 CSS selector，本质是"AI 自动找元素"，需要 `page.content()`（完整 HTML）做 prompt 输入

#### Q2.2 URL 网页访问实现

- **API**：直接用 Playwright `page.goto(url, timeout=timeout, wait_until=wait_until)`（`browser_navigator_server.py:29`）
- **超时控制**：参数 `timeout=30000`（30s 默认），透传给 Playwright。
- **等待策略**：参数 `wait_until="load"`（默认，可选 `"load"` / `"domcontentloaded"` / `"networkidle"` / `"commit"`），透传给 Playwright。
- **重试机制**：**无**。`browser_navigator_server.py:31-32` 的 `except Exception as e` 一次性失败就抛 `ValueError` 给上层。
- **反爬对抗**：**全部缺失**。
  - 无 `User-Agent` 伪装（沿用 Chromium 默认 UA，且 headless=False 时 UA 暴露 `HeadlessChrome` 字样；本项目用 `headless=False` 反而不暴露）
  - 无 WebDriver 标识隐藏（无 `navigator.webdriver = false` 注入）
  - 无代理支持（`browser_manager.py:14-17` 创建 context 时只设 `viewport` 与 `device_scale_factor`，**没有 `proxy` / `extra_http_headers`**）
  - 无 cookies / storage state 持久化
  - 无 stealth 插件（不像 `playwright-extra` / `puppeteer-extra-plugin-stealth`）

#### Q2.3 HTML 过大处理 / 压缩策略

**结论：完全没有处理。这是一个"裸用 Playwright content()"的最小实现。**

- 唯一一处取 HTML 的代码是 `extract_selector_by_page_content`（`browser_navigator_server.py:157`）调用 `page.content()`，**直接把整页 HTML 拼进 LLM prompt**，没有任何截断、剥离、压缩：
  ```
  prompt = (
      "Given the following HTML content of a web page:\n\n"
      f"{html_content}\n\n"
      f"User request: '{user_message}'\n\n"
      "Provide the CSS selector that best matches the user's request. Return only the CSS selector."
  )
  ```
  （`browser_navigator_server.py:160-165`）
- grep `max_length` / `truncat` / `readability` / `turndown` / `cheerio` / `markdown` 全仓库**零命中**。
- 无 `script` / `style` 标签剥离；无 Markdown 转换；无 token 计数限长。
- **风险点**：当目标页面是大型电商/SPA/列表页时，`page.content()` 可能 1-5 MB，瞬间击穿 LLM context window（Azure OpenAI GPT-4 8K/32K），且 token 费用极高。这是个**未解决的工程缺陷**。
- 截图（`playwright_screenshot`）处理：
  - 默认 `type="png"` + `full_page=True`（`browser_navigator_server.py:48`），无 JPEG 压缩选项。
  - 全页截图 base64 后通过 MCP `ImageContent` 直接回传（`browser_navigator_server.py:55-57`），**无 size 上限、无磁盘旁路**。一个全页 1080p PNG 可能 500KB-3MB base64 后塞进 JSON-RPC 消息。
  - `width` / `height` 参数（`browser_navigator_server.py:36`）**实际未使用**——代码里没看到 viewport 调整调用，是个**死参数**。
- 无"大结果写到磁盘只返回摘要"模式。

**与其他 Playwright MCP server 对比**：
- 微软官方 `@microsoft/playwright-mcp`：21+ 工具，有 `browser_evaluate` 支持 element refs、accessibility tree 提取
- `executeautomation/mcp-playwright`：15+ 工具，有 `browser_get_visible_text` / `browser_get_visible_html` / `browser_close_page`
- `mcp-aoai-web-browsing`（本项目）：9 工具，**功能最薄**，但**独家**提供 `extract_selector_by_page_content`（LLM 推断 selector），这是用 LLM 调用成本换"用户友好"的取舍

### Q3. fetch 功能实现

**结论：没有专门 fetch 工具。该项目用 Playwright 替代了一切"HTTP 拉取"场景。**

- grep `fetch` / `httpx` / `requests.get` / `aiohttp.ClientSession` 全仓库**零命中**（注意 `aiohttp>=3.13.5` 在 `pyproject.toml:9` 有声明，但**源码中无任何使用**——属于遗留/未用依赖）。
- 项目**没有** `fetch_url` / `fetch_markdown` / `fetch_html` / `fetch` 任一工具。
- 与 Q2 工具的关系：
  - "获取 HTML" 的唯一路径是 `extract_selector_by_page_content` 内部的 `page.content()`（`browser_navigator_server.py:157`）——但这个**不是给 LLM 用的提取工具**，而是中间步骤，把 HTML 喂给另一个 LLM 调用去推断 selector。
  - 项目定位是"用 LLM 驱动浏览器自动化"，**而不是**"用 LLM 抓网页文本"。所以没有 `fetch_markdown` 这种"轻量取页"工具——必须通过 `playwright_navigate` 走完整浏览器渲染。
- 隐含的副作用：
  - 即便用户只想"读取一篇博客"，也会触发完整 Chromium 启动（`browser_manager.py:12-13`），开销巨大（启动 1-3s + 内存 200MB+）
  - 反过来也意味着"JS 渲染后的页面" / "登录后页面" / "SPA 动态内容" 都能直接拿——这是 Playwright 方案 vs 纯 fetch 方案的根本差异
- HTTP 请求层：完全由 Playwright 内部处理（Chromium devtools protocol），项目层无 axios / node-fetch / undici / aiohttp 直接使用。

**与 Onion Agent non_head_browser.py 重构的关联**：
- `extract_selector_by_page_content` 的设计思路值得借鉴——把"用户自然语言 → CSS selector"作为独立 MCP tool，让 LLM 在"看不清 DOM"时主动调用，避免硬编码 selector 的脆弱性。
- 但本项目的"裸 `page.content()` 不截断"是个**反面教材**：Onion Agent 改造时一定要加 `max_length`（建议 8K-16K 字符截断 + 优先保留 `<body>`/`<main>`/`<article>`）+ 剥离 `<script>`/`<style>`，否则长页面直接击穿 context。
- `headless=False` + 无 `executablePath` + Docker 镜像无 `playwright install` 是个**三连坑**，Onion Agent 部署 Linux 必须全部修：加 `headless=True` 默认 + 允许环境变量切到 `False`、加 `executablePath` / `channel` 透传、Dockerfile 加 `playwright install --with-deps chromium` + `xvfb-run`（如果保留有头 demo）。

## 3. 关键代码片段

### 片段 1：浏览器启动（**全项目唯一的 `chromium.launch`，写死有头 + 无路径**）

```python
# server/browser_manager.py:10-19
async def ensure_browser(self):
    if not self.browser:
        self._playwright = await async_playwright().start()
        self.browser = await self._playwright.chromium.launch(headless=False)  # 写死有头
        context = await self.browser.new_context(
            viewport={"width": 1920, "height": 1080},
            device_scale_factor=1,
            # 无 proxy / extra_http_headers / storage_state
        )
        self.page = await context.new_page()
        ...
```

### 片段 2：唯一带 LLM 调用的 tool（**HTML 整页塞进 prompt**）

```python
# server/browser_navigator_server.py:150-172
@self.mcp.tool()
async def extract_selector_by_page_content(user_message: str) -> str:
    """Try to find a css selector by current page content."""
    page = await self.browser_manager.ensure_browser()
    html_content = await page.content()  # 整页 HTML，无截断

    prompt = (
        "Given the following HTML content of a web page:\n\n"
        f"{html_content}\n\n"
        f"User request: '{user_message}'\n\n"
        "Provide the CSS selector that best matches the user's request. Return only the CSS selector."
    )
    llm_response: LLMResponse = await self.llm_client.invoke_with_prompt(prompt)
    return llm_response.content.strip()
```

### 片段 3：截图回传（**base64 全塞 MCP 消息，无 size 限制**）

```python
# server/browser_navigator_server.py:46-58
screenshot = await element.screenshot(type="png")  # 或 page.screenshot(type="png", full_page=True)
screenshot_base64 = base64.b64encode(screenshot).decode("utf-8")
self.screenshots[name] = screenshot_base64
return [
    TextContent(type="text", text=f"Screenshot {name} taken"),
    ImageContent(
        type="image", data=screenshot_base64, mimeType="image/png"
    ),
]
```

### 片段 4：JS 执行（**带 console 拦截的"贴心"实现**）

```python
# server/browser_navigator_server.py:106-148
@self.mcp.tool()
async def playwright_evaluate(script: str):
    page = await self.browser_manager.ensure_browser()
    script_result = await page.evaluate("""
        (script) => {
            const logs = [];
            const originalConsole = { ...console };
            ['log', 'info', 'warn', 'error'].forEach(method => {
                console[method] = (...args) => {
                    logs.push(`[${method}] ${args.join(' ')}`);
                    originalConsole[method](...args);
                };
            });
            try {
                const result = eval(script);
                Object.assign(console, originalConsole);
                return { result, logs };
            } catch (error) {
                Object.assign(console, originalConsole);
                throw error;
            }
        }
    """, script)
    return_string = (
        "Execution result:\n" + json.dumps(script_result["result"], indent=2)
        + "\n\n" + "Console output:\n" + "\n".join(script_result["logs"])
    )
    return return_string
```

### 片段 5：MCP-LLM bridge 的 tool_call 循环（**OpenAI 工具名到 MCP 工具名的双向映射**）

```python
# client_bridge/bridge.py:55-117
def _convert_mcp_tools_to_openai_format(self, mcp_tools):
    for tool in tools_list:
        if hasattr(tool, "name") and hasattr(tool, "description"):
            openai_name = self._sanitize_tool_name(tool.name)  # playwright_navigate -> playwright_navigate
            self.tool_name_mapping[openai_name] = tool.name   # 反向映射
            ...
            openai_tool = {
                "type": "function",
                "function": {
                    "name": openai_name,
                    "description": tool.description,
                    "parameters": tool_schema,  # 透传 inputSchema
                },
            }
```

## 4. 与 Onion Agent non_head_browser.py 重构的关联

- **可借鉴**：`extract_selector_by_page_content` 把"LLM 选 selector"显式建模成 tool，是"AI 主动用浏览器"比"硬编码 selector"更鲁棒的设计，可考虑作为 Onion Agent 的辅助工具（搭配传统 selector 失败时降级使用）。
- **必须规避**：(1) `page.content()` 必须截断 + 剥离 `<script>/<style>`（本项目裸用是反例）；(2) 截图需加 size 上限或磁盘旁路（本项目 3MB base64 直传 MCP 是反例）；(3) 必须实现 `playwright install` 的 Dockerfile 集成 + `headless` 可切 + `executablePath` 透传（本项目三连坑是反例）。
- **可直接采用**：本项目 `BrowserManager.ensure_browser` 的"懒加载单例 + 复用 page" 模式（`browser_manager.py:11-19`）是干净的——首次访问 page 时启动 Chromium，后续 tool 直接复用，避免每个 tool 重复启停。Onion Agent 可以借鉴这个"browser 进程池"思路。

## 5. 不确定 / 未找到

- **二进制存储路径**：源码/文档未显式说明，依赖 Playwright 默认行为（`%LOCALAPPDATA%\ms-playwright\` 等），本报告所写路径为 Playwright 通用默认，未在仓库内验证。
- **Docker 镜像能否运行**：`Dockerfile:34` ENTRYPOINT 是 `uv run fastmcp dev`，但镜像里没有 Chromium 二进制（无 `playwright install` 步骤），**实际启动会崩**——这点是基于"Dockerfile 阅读 + 无安装步骤"推断，未实际跑过容器验证。
- **国内/离线环境**：完全未文档化，README 也没提任何镜像源切换建议。
- **是否还有未列出的 tool**：本仓库全部 .py 已读，9 个 tool 是确认全量。但 `client_bridge/mcp_client.py` 用了 `mcp.shared.memory.create_connected_server_and_client_session`（行 5-7），这个 API 是否暴露额外能力，未深究。
- **`playwright_screenshot` 的 `width` / `height` 参数**：源码中**未使用**，疑似未实现完成的 dead params。
- **macOS / Linux 路径**：本报告引用的是 Windows 路径，macOS / Linux 用户实际存储位置是 `~/Library/Caches/ms-playwright/` 与 `~/.cache/ms-playwright/`，未在 Windows 环境实测确认。
