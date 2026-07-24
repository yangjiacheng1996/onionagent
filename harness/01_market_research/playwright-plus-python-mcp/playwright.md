# playwright-plus-python-mcp — Playwright 浏览器自动化调研报告

## 0. 项目一句话定位

`playwright-plus-python-mcp`（`blackwhite084/playwright-plus-python-mcp`，PyPI 包名 `playwright-server`）是一个**基于 Playwright Python SDK** 的轻量 MCP server，比官方 TypeScript 版更适合 Python 生态，定位"llm-friendly"：只暴露 8 个核心工具，让 LLM 可以在 Python 项目里直接驱动 Chromium。

## 1. 调研依据

- 源码路径：`C:\workspace\github\onionagent\harness\01_market_research\clone\playwright-plus-python-mcp`
- 关键文件 / 关键代码片段：
  - `pyproject.toml` — 依赖声明（只声明 `mcp>=1.1.2` + `playwright`，不声明任何浏览器安装 hook）
  - `uv.lock` — 22 行的 lockfile，证实使用 uv 包管理器（旁证：`.python-version` = `3.11`）
  - `src/playwright_server/__init__.py` — 包入口，`main()` 直接 `asyncio.run(server.main())`
  - `src/playwright_server/server.py` — **整个 MCP server 只有一个文件、377 行**，所有 8 个 tool + 全部 handler + 主循环都在这里
  - `server.py:194` — `browser = await self._playwright.chromium.launch(headless=False)` 唯一一处启动浏览器
  - `server.py:215` — `await page.goto(url)` URL 访问实现
  - `server.py:217` — `text_content[:200]` HTML/text 截断
  - `server.py:300` — JS 内部 `innerText.length <= 1000` 元素过滤
  - `server.py:230-236` — screenshot 写到 `{name}.png` 然后删文件 + base64 返回
- 文档 / README 引用：
  - `README.md:47-85` — `Quickstart` / `Install` 章节，**没有提及 `playwright install`**（暗示需要用户自己跑一次 `playwright install`）
  - `README.md:96` — `uv sync` 是发布前准备步骤，**不是首次安装说明**
  - `README.md:115-127` — `Debugging` 章节用 MCP Inspector

## 2. 三个核心问题的回答

### Q1. Playwright 无头浏览器安装

**结论：需要用户手动跑 `playwright install`，项目本身不提供自动安装/自动检测/离线/本地浏览器路径支持。**

证据清单：

| 子问题 | 答案 | 证据 |
|---|---|---|
| 是否需要用户跑 `playwright install`？ | **是**。`pyproject.toml:7` 只声明 `["mcp>=1.1.2", "playwright"]`，没有任何 `post-install` hook / `tool.hatch.build.hooks` / `[tool.uv] post-install` / `script` 钩子去触发 `playwright install chromium`。`uv sync` 装完包后**Chromium 二进制不会自动下载**，第一次 `playwright_navigate` 必然失败并报 `playwright._impl._errors.Error: Executable doesn't exist at ...`。 | `pyproject.toml:1-17` 全文件 |
| 是否实现自动检测 + 自动安装？ | **否**。`server.py:194` 直接 `await self._playwright.chromium.launch(headless=False)`，没有任何 `try/except` 捕获缺失错误并重试安装。整份源码 0 处出现 `install`、`subprocess.run`、调用 `playwright install` 子进程。 | `server.py:184-203`（`NewSessionToolHandler`） |
| 浏览器二进制存储位置？ | **走 Playwright Python SDK 默认缓存**（由官方 `playwright._impl._driver` 决定），未在本项目任何地方覆盖。Playwright Python 默认缓存路径：<br/>• Windows：`%LOCALAPPDATA%\ms-playwright\`（如 `C:\Users\xxx\AppData\Local\ms-playwright\chromium-1140\`）<br/>• macOS：`~/Library/Caches/ms-playwright/`<br/>• Linux：`~/.cache/ms-playwright/` | 无显式配置；由 `playwright` SDK 决定 |
| 文档是否说明离线 / 国内网络？ | **完全没说**。`README.md` 全文无 `CDN` / `proxy` / `mirror` / `国内` / `offline` / `离线` / `HTTPS_PROXY` / `PLAYWRIGHT_DOWNLOAD_HOST` 等关键字。`pyproject.toml` / `uv.lock` 也没有 `PLAYWRIGHT_DOWNLOAD_HOST` 之类的 env 配置。 | `README.md` 全文 + `pyproject.toml` 全文 |
| 是否支持本地已安装的浏览器路径？ | **否**。`server.py:194` 调用 `chromium.launch(headless=False)` 时**没有传 `executable_path` 也没有 `channel='chrome' / 'chrome-beta' / 'msedge'`**，无法指向用户本机已安装的 Chrome / Edge。 | `server.py:184-203` |
| uv 包管理？ | **是**。`.python-version` 存在（`3.11`），`uv.lock` 存在（22 个间接依赖条目），`pyproject.toml:6` `requires-python = ">=3.11"`，`pyproject.toml:13-14` build-backend 是 `hatchling`。但 uv 仅用于**包管理**（解析依赖、构建、发布），**与浏览器二进制安装完全无关**。 | `.python-version`、`uv.lock`、`pyproject.toml:6,13-14` |

**关键反直觉点：** `headless=False` 是**硬编码**在 `server.py:194`，意味着这个 MCP server 默认**实际上是有头（headed）浏览器**，每次启动都会弹出一个 Chromium 窗口——和一般"无头浏览器"工具的预期不符。

---

### Q2. 浏览器自动化功能 + URL 访问 + HTML 压缩

#### Q2.1 浏览器自动化功能清单

项目暴露 **8 个 tool**（`server.py:53-152` 的 `handle_list_tools`）。注：`playwright_new_session` 在 handler 字典里注册（`server.py:343`）但**没有**在 `handle_list_tools` 注册（`server.py:54-63` 整段被注释掉），所以客户端实际能调用的是 8 个。

| 工具名（name） | 类别 | 输入参数（`inputSchema`） | 输出格式 | 代码位置 |
|---|---|---|---|---|
| `playwright_navigate` | 导航 | `url: str`（必填） | `text/plain`："Navigated to {url}\npage_text_content[:200]" | `server.py:64-74, 205-217` |
| `playwright_screenshot` | 提取 | `name: str`（必填），`selector: str`（可选，不传则全页） | `image/png`（base64 内联），文件用完即删 | `server.py:75-86, 219-236` |
| `playwright_click` | 交互 | `selector: str`（CSS，必填） | `text/plain`："Clicked element with selector {selector}" | `server.py:87-97, 238-247` |
| `playwright_fill` | 交互 | `selector: str`、`value: str`（都必填） | `text/plain`："Filled element with selector ... with value ..." | `server.py:98-109, 249-258` |
| `playwright_evaluate` | JS 执行 | `script: str`（必填） | `text/plain`："Evaluated script, result: {result}" | `server.py:110-120, 260-268` |
| `playwright_click_text` | 交互 | `text: str`（元素文本内容，必填） | `text/plain`："Clicked element with text {text}" | `server.py:121-131, 270-279` |
| `playwright_get_text_content` | 提取 | （无参数） | `text/plain`："Text content of all elements: [...]"（数组） | `server.py:132-140, 281-321` |
| `playwright_get_html_content` | 提取 | `selector: str`（必填） | `text/plain`："HTML content of element with selector ...: {html}" | `server.py:141-151, 323-331` |

**类别覆盖检查**（对照 Q2.1 分类）：
- ✅ 导航类：`playwright_navigate`（但**没有** `go_back` / `go_forward` / `reload` / `new_page` / `close_page`）
- ✅ 交互类：`playwright_click` / `playwright_fill` / `playwright_click_text`（**没有** `hover` / `drag` / `press_key` / `upload_file`）
- ✅ 提取类：`playwright_get_text_content` / `playwright_get_html_content` / `playwright_screenshot`（**没有** `get_attribute` / `get_url` / `get_console_logs`）
- ❌ 等待类：完全缺失
- ✅ JS 执行类：`playwright_evaluate`
- ❌ 高级类：完全缺失（没有 iframe / 多 tab / 设备模拟 / PDF / codegen）
- 🆕 自定义：`playwright_new_session`（handler 注册但 tool 注册被注释）

#### Q2.2 URL 网页访问如何实现？

证据集中在 `server.py:191-217`：

```python
# server.py:191-203 — 隐式 session（NavigateToolHandler 内部）
async def handle(self, name, arguments):
    if not self._sessions:
        await NewSessionToolHandler().handle("", {})   # 没有 session 就先开
    session_id = list(self._sessions.keys())[-1]        # 取最后一个 session
    page = self._sessions[session_id]["page"]
    url = arguments.get("url")
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url                            # 自动补 https://
    await page.goto(url)                                  # 走 Playwright 默认行为
```

| 子问题 | 答案 | 证据 |
|---|---|---|
| 用 `page.goto(url)`？ | **是**。`server.py:202, 215` 两处（`NewSessionToolHandler` 与 `NavigateToolHandler`） | `server.py:202, 215` |
| 超时控制（`timeout`）？ | **没有**。两处 `page.goto(url)` 都没传第二个参数。Playwright 默认 `timeout=30_000ms`，超时抛 `playwright._impl._errors.TimeoutError` 后**直接冒泡给 MCP 调用方**（handler 没 try/except）。 | `server.py:202, 215` |
| 等待策略（`waitUntil`）？ | **没有**。完全用 Playwright 默认 `wait_until='load'`。 | `server.py:202, 215` |
| 重试机制？ | **没有**。无 retry、无指数退避。 | `server.py:184-358` 全文 |
| 反爬虫对抗？ | **完全没做**。<br/>• **User-Agent 伪装**：没有 `page.set_extra_http_headers`、没有 `user_agent=` 参数<br/>• **WebDriver 标识隐藏**：没有 `navigator.webdriver = undefined` 的 evaluate<br/>• **代理支持**：没有 `proxy={"server": "..."}` 参数 | `server.py:184-203`（`launch` 调用） |

**安全 / 设计小问题**：
- `server.py:200, 213` 的 `if not url.startswith("http://")` 拼写检查不严格——如果用户传 `ftp://foo` 或 `javascript:alert(1)`，会被强行改成 `https://javascript:alert(1)`（虽然浏览器最终会拦截 javascript: scheme，但代码本身没做白名单）。
- `server.py:165` 的 `list(self._sessions.keys())[-1]` 是**单 session 设计**：永远拿最后一个。多个 session 同时存在会被静默覆盖。
- `server.py:194` 的 `headless=False` 是硬编码，**没法在 MCP tool 层切换**。

#### Q2.3 网页 HTML 过大如何处理？压缩策略？

**该项目的压缩策略 = 几乎不做。** 仅有 3 个非常简陋的截断点：

| 位置 | 截断策略 | 代码 | 评价 |
|---|---|---|---|
| `NavigateToolHandler` 返回 | 取 `text_content` 字符串的 `[:200]` 前缀 | `server.py:217` `text_content[:200]` | 极简，200 字符内可能只有导航栏 |
| `GetTextContentToolHandler` 内部 JS | 元素 `innerText.length <= 1000` 才被加入集合 | `server.py:300` `if (innerText && innerText.length <= 1000)` | 元素级 1000 字符硬切 |
| `GetTextContentToolHandler` 整体返回 | 全部 unique 文本数组一次性返回，**无总长度限制** | `server.py:321` | 集合到几千个元素时可能直接 OOM 客户端 |
| `GetHtmlContentToolHandler` | `page.locator(selector).inner_html()` **无任何截断** | `server.py:330` | selector 选到 `<html>` 时返回完整 HTML |
| `ScreenshotToolHandler` | base64 编码后**删原文件**；base64 字符串**无大小限制直接内联返回** | `server.py:230-236` | 1024×768 PNG 可能 ~1-2MB base64 |

**完全没有实现的能力**：
- ❌ `max_length` / `max_chars` / `max_tokens` 参数（无任何相关关键字：`grep` 0 命中）
- ❌ 头尾截断（head+tail 模式）
- ❌ 智能截断（按 token 算）
- ❌ `<script>` / `<style>` 标签剥离（虽然有 `GetTextContentToolHandler` 走 `innerText` 间接跳过，但 `GetHtmlContentToolHandler` 返回的 inner_html 里 script/style 都在）
- ❌ Markdown 转换（**不依赖** `markdownify` / `html2text` / `beautifulsoup4` / `turndown` / `readability-lxml` 任何一个，pyproject.toml 也没声明）
- ❌ 截图图片压缩（无 `quality` / `type: 'jpeg'` 参数）
- ❌ 大结果旁路到磁盘（`~/.cache/...` 模式完全没做）

**图片内联的潜在 MCP 风险**：`server.py:230` 写的是 `path=f"{name}.png"`（**相对路径**），如果用户传 `name="../../tmp/abc"`，会落到任意可写目录再读回——轻微的**路径遍历**风险。

---

### Q3. fetch 功能实现

**结论：这个项目没有独立的 fetch 工具。** 它是一个**纯浏览器自动化 MCP server**，不提供"快读网页正文"的专用 API。

| 子问题 | 答案 | 证据 |
|---|---|---|
| 是否有专门 `fetch` / `fetch_url` / `fetch_markdown` 工具？ | **否**。`handle_list_tools`（`server.py:47-152`）列出的 8 个 tool 里**没有**任何 `fetch` 命名空间的工具。 | `server.py:47-152` |
| 与"获取 HTML"工具有何区别？ | **不区分**。`playwright_navigate` + `playwright_get_html_content` 组合是唯一"读网页"路径，但二者**没有合并**为 fetch 工具：navigate 只返回 200 字符预览，get_html_content 需要先 navigate 并传 selector。 | `server.py:205-217, 323-331` |
| 是否支持多格式输出（HTML / Markdown / Text / JSON-LD）？ | **只支持原始 HTML**（`page.locator(selector).inner_html()`，`server.py:330`）和**仅 innerText 数组**（`server.py:291-313` 的 JS）。**无** Markdown 转换、**无** JSON-LD 解析。 | `server.py:281-331` |
| 元数据提取（title / author / og:image）？ | **否**。没有任何 `document.querySelector('meta[property="og:title"]')` / `JSON.parse LD-JSON` 逻辑。 | `server.py:281-331` 全文 |
| 正文提取（Readability / `<article>` / `<main>`）？ | **否**。`pyproject.toml` 也没声明 `readability-lxml`。`GetTextContentToolHandler` 用的是**全 DOM 遍历 + offsetWidth/Height 可见性判断 + 去重**，是 LLM 友好的"暴露所有可见文本"思路，不是 readability 思路。 | `server.py:281-321` |
| HTTP 请求层用什么库？ | **Playwright Chromium**（`page.goto`）。**不**用 `httpx`（虽然在 `uv.lock` 里有 httpx-0.28.1 出现，但那是 `mcp` 包的传递依赖，与本 MCP server 的抓取逻辑无关）。 | `server.py:202, 215`；`uv.lock:59-71` |
| 自定义 headers？ | **没有**。`launch` 时不传 `extra_http_headers`，`new_page` 时也不传，调用方**无法注入** User-Agent / Cookie / Authorization。 | `server.py:194-195` |
| 重定向跟随（`maxRedirects`）？ | **走 Playwright 默认**（无限制，最多 20 次，与 Chromium 自身行为一致），代码未做额外控制。 | `server.py:202, 215` |
| 请求 / 响应大小限制（防 OOM）？ | **没有**。`page.goto` 不设 `max_length`，`get_html_content` 不截断 HTML。 | `server.py:330` |
| 错误分类（404 / 403 / 5xx / DNS / 超时）？ | **没有**。所有错误都直接让 Playwright 抛异常，handler **不包 try/except**，冒泡给 MCP 调用方。`handle_call_tool`（`server.py:347-358`）也**不**做错误分类包装，只在 `name not in tool_handlers` 时 `raise ValueError`。 | `server.py:184-358` |

**与典型"fetch MCP"工具的对比**：
- 典型 fetch MCP（如 `@modelcontextprotocol/server-fetch`）走 `httpx` 拿 HTML → 调 Readability → 输出 Markdown 摘要。
- 本项目**完全不是这条路线**——它是把"fetch 动作"也走 Playwright Chromium 渲染，**慢但能拿到 JS 渲染后的 DOM**。
- 代价：每次 navigate 都要起/复用 Chromium 进程，500ms+ 延迟起跑；大页面（如知乎、掘金）截图 + HTML 直接 base64 走 MCP 协议，可能爆 MCP message size 上限。

---

## 3. 关键代码片段

**片段 1 — `NavigateToolHandler` 核心逻辑（`server.py:205-217`）**

```python
class NavigateToolHandler(ToolHandler):
    async def handle(self, name, arguments):
        if not self._sessions:
            await NewSessionToolHandler().handle("", {})  # 懒启动 browser
        session_id = list(self._sessions.keys())[-1]
        page = self._sessions[session_id]["page"]
        url = arguments.get("url")
        if not url.startswith("http://") and not url.startswith("https://"):
            url = "https://" + url
        await page.goto(url)                            # 走 Playwright 默认
        text_content = await GetTextContentToolHandler().handle("", {})
        return [types.TextContent(type="text", text=f"Navigated to {url}\npage_text_content[:200]:\n\n{text_content[:200]}")]
```

**片段 2 — 浏览器启动（`server.py:191-203`，整份代码唯一一处）**

```python
class NewSessionToolHandler(ToolHandler):
    async def handle(self, name, arguments):
        self._playwright = await async_playwright().start()
        browser = await self._playwright.chromium.launch(headless=False)   # 硬编码有头
        page = await browser.new_page()
        session_id = str(uuid.uuid4())
        self._sessions[session_id] = {"browser": browser, "page": page}
        url = arguments.get("url")
        if url:
            if not url.startswith("http://") and not url.startswith("https://"):
                url = "https://" + url
            await page.goto(url)
        return [types.TextContent(type="text", text="succ")]
```

**片段 3 — `GetTextContentToolHandler` 内部 JS（`server.py:281-321`）**

```python
async def get_unique_texts_js(page):
    unique_texts = await page.evaluate('''() => {
    var elements = Array.from(document.querySelectorAll('*'));
    var uniqueTexts = new Set();
    for (var element of elements) {
        if (element.offsetWidth > 0 || element.offsetHeight > 0) {  // 可见性
            var childrenCount = element.querySelectorAll('*').length;
            if (childrenCount <= 3) {                                // 只取"叶子"级文本
                var innerText = element.innerText ? element.innerText.trim() : '';
                if (innerText && innerText.length <= 1000) {         // 1000 字符上限
                    uniqueTexts.add(innerText);
                }
                var value = element.getAttribute('value');
                if (value) { uniqueTexts.add(value); }
            }
        }
    }
    return Array.from(uniqueTexts);
}''')
    return unique_texts
```

**片段 4 — `update_page_after_click` 装饰器（`server.py:161-182`）**

```python
def update_page_after_click(func):
    async def wrapper(self, name, arguments):
        if not self._sessions:
            return [types.TextContent(type="text", text="No active session. ...")]
        session_id = list(self._sessions.keys())[-1]
        page = self._sessions[session_id]["page"]
        new_page_future = asyncio.ensure_future(page.context.wait_for_event("page", timeout=3000))
        result = await func(self, name, arguments)        # 实际 click/fill
        try:
            new_page = await new_page_future              # 等 3 秒看是否弹新 tab
            await new_page.wait_for_load_state()
            self._sessions[session_id]["page"] = new_page
        except:
            pass
        return result
    return wrapper
```

**片段 5 — `ScreenshotToolHandler`（`server.py:219-236`）**

```python
async def handle(self, name, arguments):
    if not self._sessions:
        return [types.TextContent(type="text", text="No active session. ...")]
    session_id = list(self._sessions.keys())[-1]
    page = self._sessions[session_id]["page"]
    name = arguments.get("name")
    selector = arguments.get("selector")
    if selector:
        element = await page.locator(selector)
        await element.screenshot(path=f"{name}.png")           # 相对路径，无 sanitize
    else:
        await page.screenshot(path=f"{name}.png", full_page=True)
    with open(f"{name}.png", "rb") as image_file:
        encoded_string = base64.b64encode(image_file.read()).decode("utf-8")
    os.remove(f"{name}.png")                                   # 写完即删
    return [types.ImageContent(type="image", data=encoded_string, mimeType="image/png")]
```

---

## 4. 与 Onion Agent non_head_browser.py 重构的关联

1. **不要把这个项目当 fetch 工具的参考**——它没有 fetch 工具、没有 Markdown 转换、没有 Readability、没有 metadata 提取。要做 Onion Agent 的"非无头浏览器"或"快读网页正文"工具，应该参考 `fetch-mcp` / `@modelcontextprotocol/server-fetch` 的路线，而不是这个项目。

2. **`headless=False` 是个反例**——Onion Agent 自己的 `non_head_browser.py` 一定要默认 `headless=True`，而且要把 `headless` / `executable_path` / `channel` / `proxy` 都做成可配置项（这个项目一个都没做，是个教训）。

3. **`update_page_after_click` 装饰器是值得抄的"小聪明"**——它用 `asyncio.ensure_future` + `wait_for_event("page", timeout=3000)` 在 click 后**自动接管新打开的 tab**，避免 SPA / 链接打开新窗口后 page 对象失效的经典问题。Onion Agent 重构时可以借鉴。

4. **会话管理是单例反例**——`_sessions: dict[str, any] = {}` + `list(self._sessions.keys())[-1]` 的"永远拿最后一个"模式在多 agent / 多任务并发时一定会冲突。Onion Agent 重构时必须用**按 agent 隔离的 session 存储**（如 `session_id` 作为 key、绑定到 `session.json`）。

5. **HTML 截断是反面教材**——`text_content[:200]` 这种粗暴切片 + 不剥离 `<script>` / `<style>` + 不转换 Markdown 的做法，会让 LLM 上下文里充斥噪声。Onion Agent 的"非无头浏览器"工具至少要做：script/style 剥离 + 按 token 截断（tiktoken）+ Markdown 转换（markdownify）三件套。

---

## 5. 不确定 / 未找到

1. **未在源码中确认**：Playwright 浏览器二进制的具体存储路径——本项目**没有**覆盖 `PLAYWRIGHT_BROWSERS_PATH`，所以走 Python SDK 默认缓存。本报告给出的 `%LOCALAPPDATA%\ms-playwright\` 等路径是 Playwright Python 的官方默认行为，**不是本项目源码证据**，而是 SDK 文档知识。
2. **未在源码中确认**：错误处理路径——handler 全程不包 `try/except`，意味着 Playwright 抛 `TimeoutError` / `Error: Executable doesn't exist` 时会直接冒泡；MCP 客户端收到的是 Python traceback 字符串，**没有**做人类友好的错误分类（404 / 403 / 5xx / DNS / 超时）。
3. **未在源码中确认**：并发安全性——`_sessions` 是类变量 `dict`，且 `list(self._sessions.keys())[-1]` 在并发 MCP 调用下**不是原子操作**，会丢 session。本报告对此标注为"潜在 bug"，但未在源码里找到并发测试覆盖。
4. **未在源码中确认**：截图 / HTML 的大小阈值——`server.py` 全程没有 `if len(...) > MAX: ...` 类的防护，完全依赖 Playwright / Chromium 自身的内存管理。大页面 + 多次 screenshot 调用时存在 OOM 风险，但没有源码证据。
5. **未找到**：`playwright_new_session` 这个 tool 的注册。`server.py:343` 把它注册到 `tool_handlers` 字典里，但 `handle_list_tools`（`server.py:47-152`）的 list 里**没有**它的 `types.Tool(...)`。所以即便客户端发来 `playwright_new_session` 也会被 `handle_call_tool` 路由到 handler 执行——但**不会在 `tools/list` 列表里出现**，对客户端是"hidden tool"。
6. **未找到**：LICENSE 内容（虽然有 `LICENSE` 文件 11558 字节，但本报告未读其内容）。可能影响"信创合规"判断，但不属于本次 Playwright 调研范围。
