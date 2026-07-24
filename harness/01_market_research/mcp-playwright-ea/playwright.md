# mcp-playwright-ea — Playwright 浏览器自动化调研报告

> 调研对象：`executeautomation/mcp-playwright`（npm: `@executeautomation/playwright-mcp-server`，server name: `playwright-mcp`）
> 调研版本：`v1.0.12`（2025-12-12）
> 调研日期：2026-07
> 调研人：Onion Agent 通用工作者

---

## 0. 项目一句话定位

**TypeScript 版最流行的 Playwright MCP server，2.5k+ stars，32 个 tool（4 codegen + 5 API + 23 browser），支持 Chromium / Firefox / WebKit 三引擎、HTTP/SSE + stdio 双传输、代码生成、API 请求、文件上传、143 设备预设模拟。**

> 与同期 `microsoft/playwright-mcp`（官方）相比，mcp-playwright-ea 偏向"多工具覆盖广、文档齐全、社区驱动"路线；`microsoft/playwright-mcp` 偏向"与 Playwright Test 紧集成 + 官方血统"。

---

## 1. 调研依据

### 1.1 源码路径

`C:\workspace\github\onionagent\harness\01_market_research\clone\mcp-playwright-ea`（`git clone --depth 1`，只读）

### 1.2 关键文件 / 关键代码片段

| 关注点 | 路径 | 行号 |
|---|---|---|
| 入口与 HTTP/stdio 分发 | `src/index.ts` | 11-69 |
| MCP tool 清单 | `src/tools.ts` | 4-498（`createToolDefinitions`） |
| Tool 路由 + 浏览器初始化 | `src/toolHandler.ts` | 221-397（`ensureBrowser`）、451-691（`handleToolCall`） |
| **自动安装浏览器核心实现** | `src/toolHandler.ts` | 164-216（`installBrowsers`）、272-294（首次启动）、340-354（重试） |
| Navigate（URL 访问） | `src/tools/browser/navigation.ts` | 8-58（`NavigationTool.execute`） |
| **HTML 截断 / script 剥离** | `src/tools/browser/visiblePage.ts` | 72-194（`VisibleHtmlTool`）、8-67（`VisibleTextTool`） |
| Screenshot（图片处理） | `src/tools/browser/screenshot.ts` | 1-77（`ScreenshotTool`） |
| API 请求（fetch-like） | `src/tools/api/requests.ts` | 87-289（5 个 HTTP 方法） |
| 设备模拟（device presets） | `src/tools/browser/resize.ts` | 8-114（`ResizeTool`） |
| 交互（click/fill/drag/press_key 等） | `src/tools/browser/interaction.ts` | 1-235 |
| Codegen | `src/tools/codegen/index.ts` + `recorder.ts` | 25-209 + 1-78 |
| HTTP/SSE 模式 | `src/http-server.ts` | 17-316（`startHttpServer`） |
| 浏览器基类 | `src/tools/browser/base.ts` | 1-92 |

### 1.3 文档 / README 引用

- `README.md`（v1.0.12）— 浏览器安装、stdio/HTTP 模式、安全说明
- `CHANGELOG.md` — v1.0.0 ~ v1.0.12 全部变更（含 v1.0.12 自动安装、v1.0.11 Bearer auth、v1.0.10 设备预设、v1.0.7 HTTP/SSE、v1.0.6 HTML script 剥离）
- `docs/docs/playwright-api/Supported-Tools.mdx` — 5 个 API tool 完整签名
- `docs/docs/local-setup/Installation.mdx` — 本地构建指引

---

## 2. 三个核心问题的回答

### Q1. Playwright 无头浏览器安装（自动 vs 手动）

**核心结论：v1.0.12 起实现了"检测到 Executable 不存在 → 自动 spawn `npx playwright install <browser>` 重试"机制；首次启动无需手动 install，但仍走 Playwright 默认 CDN（无国内/离线适配）。**

#### 1.1 自动安装触发链路

**实现位置**：`src/toolHandler.ts:164-216`（`installBrowsers` 函数）

```ts
// src/toolHandler.ts:164-216
async function installBrowsers(browserType: string = 'chromium'): Promise<{ success: boolean; message: string }> {
  return new Promise((resolve) => {
    console.error(`[Playwright MCP] Attempting to install ${browserType} browser...`);

    const installProcess = spawn('npx', ['playwright', 'install', browserType], {
      stdio: ['ignore', 'pipe', 'pipe']   // 注意：没有 shell: true（CHANGELOG v1.0.12 安全改进）
    });
    // ...
    setTimeout(() => {
      installProcess.kill();
      resolve({ success: false, message: `Browser installation timed out. Please run manually: npx playwright install ${browserType}` });
    }, 120000);  // 2 分钟超时
  });
}
```

**触发点**（2 处）：

- `src/toolHandler.ts:272-294` — `ensureBrowser` 首次 `browserInstance.launch()` 抛错时
  ```ts
  catch (launchError: any) {
    if (launchError.message?.includes("Executable doesn't exist") ||
        launchError.message?.includes("Failed to launch") ||
        launchError.message?.includes("browserType.launch")) {
      const installResult = await installBrowsers(browserType);
      if (installResult.success) {
        browser = await browserInstance.launch({ headless, executablePath });
        // ...
      } else {
        throw new Error(installResult.message);
      }
    }
  }
  ```
- `src/toolHandler.ts:340-354` — `ensureBrowser` catch 兜底分支里再次触发
  ```ts
  if (errorMessage?.includes("Executable doesn't exist") ||
      errorMessage?.includes("Failed to launch") ||
      errorMessage?.includes("browserType.launch")) {
    const installResult = await installBrowsers(browserType);
    if (!installResult.success) throw new Error(installResult.message);
  }
  ```

**触发条件**：Playwright 抛错信息包含以下任一字符串（依赖错误消息文本，脆弱）：
- `Executable doesn't exist`
- `Failed to launch`
- `browserType.launch`

#### 1.2 浏览器二进制存储位置

**未自定义路径**，直接走 Playwright 默认（`@playwright/browser-chromium` 等包已声明，详见 `package.json:30-40`）：

| OS | 路径 |
|---|---|
| Windows | `%USERPROFILE%\AppData\Local\ms-playwright` |
| macOS | `~/Library/Caches/ms-playwright` |
| Linux | `~/.cache/ms-playwright` |

> 来源：`README.md:142-144`，与 Playwright 官方默认一致。

#### 1.3 本地已安装浏览器路径

**支持** — 通过环境变量 `CHROME_EXECUTABLE_PATH` 注入 `executablePath`：

```ts
// src/toolHandler.ts:263-268
const executablePath = process.env.CHROME_EXECUTABLE_PATH;

try {
  browser = await browserInstance.launch({
    headless,
    executablePath: executablePath   // undefined 时走 Playwright 默认下载的二进制
  });
```

注意：
- **只支持 `executablePath`，不支持 `channel: 'chrome' | 'msedge'`**（grep 验证：`channel` 在源码中无匹配）
- **README 未提及此环境变量** — 只能从源码或测试用例（`src/__tests__/toolHandler.test.ts:381-396`）发现

#### 1.4 离线 / 国内网络环境

**❌ 源码层面未做适配。**

- 没有 `PLAYWRIGHT_DOWNLOAD_HOST` / `MS_PLAYWRIGHT_DOWNLOAD_HOST` 等环境变量的处理逻辑（grep 验证）
- README 的 `Manual Installation` 段只说 `npx playwright install`，没说国内镜像
- 自动安装走的也是 `npx playwright install`，同样受 CDN 限制

> **Onion Agent 适配提示**：若公司内网/信创环境无法访问 Playwright CDN，需要：
> 1. 预设 `PLAYWRIGHT_DOWNLOAD_HOST=https://npmmirror.com/mirrors/playwright` 等镜像
> 2. 或预先在镜像环境跑一次 `npx playwright install`，让目标机器直接复用
> 3. 或挂 `CHROME_EXECUTABLE_PATH` 指向信创版 Chromium（如麒麟、统信自带的浏览器）

#### 1.5 HTTP/SSE 模式 vs stdio 模式

**两种模式都支持**，入口 `src/index.ts:12-69`：

| 模式 | 启动命令 | 传输层 | 适用 |
|---|---|---|---|
| **stdio**（默认） | `playwright-mcp-server` | `StdioServerTransport` | Claude Desktop、Claude Code |
| **HTTP/SSE** | `playwright-mcp-server --port 8931` | Express + `SSEServerTransport` | VS Code Copilot、远程部署、多客户端 |

HTTP 模式实现：
- `src/http-server.ts:51-67` — Express 初始化 + 请求日志
- `src/http-server.ts:200-205` — 双 endpoint 兼容：
  - 旧：`GET /sse` + `POST /messages?sessionId=...`
  - 新（推荐）：`GET /mcp` + `POST /mcp?sessionId=...`
- `src/http-server.ts:208-214` — `GET /health` 探活
- `src/http-server.ts:218` — **绑定 127.0.0.1**（安全，外部不可直连，需 SSH 隧道）
- `src/http-server.ts:76-91` — 每个 session 一个新 `Server` 实例，支持多客户端并发

stdio 模式日志行为：
- `src/index.ts:73-80` — **仅写文件 `${HOME || '/tmp'}/playwright-mcp-server.log`**，不写 stdout（避免污染 JSON-RPC）
- 监控 HTTP 端口在 stdio 模式下禁用（line 85）

---

### Q2. 浏览器自动化功能 + URL 访问 + HTML 压缩

#### Q2.1 工具清单（32 个）

> 完整定义在 `src/tools.ts:4-498` 的 `createToolDefinitions()` 数组 + `BROWSER_TOOLS` / `API_TOOLS` / `CODEGEN_TOOLS` 分类常量（`src/tools.ts:500-549`）

**4 个 Codegen 工具**（`src/tools/codegen/index.ts:25-209`）：

| 工具名 | 输入 | 输出 | 用途 |
|---|---|---|---|
| `start_codegen_session` | `{ options: { outputPath, testNamePrefix, includeComments } }` | `{ sessionId, options, message }` | 启动录制 |
| `end_codegen_session` | `{ sessionId }` | `{ filePath, testCode, message }` | 停止录制，生成 `@playwright/test` 测试文件 |
| `get_codegen_session` | `{ sessionId }` | `CodegenSession` | 查 session |
| `clear_codegen_session` | `{ sessionId }` | `{ success }` | 取消 session |

> 录制期间，所有非 `playwright_close` 工具调用会被 `ActionRecorder` 记录到 session（`src/toolHandler.ts:473-477`、`src/tools/codegen/recorder.ts:44-62`）。`end_codegen_session` 会用 `PlaywrightGenerator` 生成 Playwright Test 风格的 `.spec.ts` 文件（`src/tools/codegen/generator.ts:30-44`）。

**5 个 API 工具**（`src/tools/api/requests.ts:87-289`）：

| 工具名 | 方法 | 关键参数 |
|---|---|---|
| `playwright_get` | GET | `url`, `token?`, `headers?` |
| `playwright_post` | POST | `url`, `value`, `token?`, `headers?` |
| `playwright_put` | PUT | 同上 |
| `playwright_patch` | PATCH | 同上 |
| `playwright_delete` | DELETE | `url`, `token?`, `headers?` |

**23 个 Browser 工具**：

| 类别 | 工具 | 代码位置 | 关键实现 |
|---|---|---|---|
| **导航** | `playwright_navigate` | `src/tools/browser/navigation.ts:8-58` | `page.goto(url, { timeout, waitUntil })` |
|  | `playwright_go_back` | `src/tools/browser/navigation.ts:96-106` | `page.goBack()` |
|  | `playwright_go_forward` | `src/tools/browser/navigation.ts:111-121` | `page.goForward()` |
|  | `playwright_close` | `src/tools/browser/navigation.ts:63-91` + `toolHandler.ts:480-506` | 关闭 + reset 全局状态 |
| **交互** | `playwright_click` | `src/tools/browser/interaction.ts:7-17` | `page.click(selector)` |
|  | `playwright_iframe_click` | `src/tools/browser/interaction.ts:51-66` | `page.frameLocator(...).locator(...).click()` |
|  | `playwright_iframe_fill` | `src/tools/browser/interaction.ts:71-86` | 同上 + fill |
|  | `playwright_fill` | `src/tools/browser/interaction.ts:91-102` | `page.fill`（含 `waitForSelector`） |
|  | `playwright_select` | `src/tools/browser/interaction.ts:107-118` | `page.selectOption` |
|  | `playwright_hover` | `src/tools/browser/interaction.ts:123-134` | `page.hover` |
|  | `playwright_drag` | `src/tools/browser/interaction.ts:184-214` | mouse.move + down + move + up |
|  | `playwright_press_key` | `src/tools/browser/interaction.ts:219-234` | `page.keyboard.press` |
|  | `playwright_upload_file` | `src/tools/browser/interaction.ts:139-150` | `page.setInputFiles` |
|  | `playwright_click_and_switch_tab` | `src/tools/browser/interaction.ts:21-47` | `context.waitForEvent('page')` + `setGlobalPage` |
| **提取** | `playwright_get_visible_text` | `src/tools/browser/visiblePage.ts:8-67` | DOM TreeWalker + 20000 字符截断 |
|  | `playwright_get_visible_html` | `src/tools/browser/visiblePage.ts:72-194` | DOMParser 过滤 + 20000 字符截断 |
|  | `playwright_console_logs` | `src/tools/browser/console.ts:7-67` | 内存数组 + type/search/limit 过滤 |
|  | `playwright_evaluate` | `src/tools/browser/interaction.ts:155-179` | `page.evaluate(script)` + JSON.stringify |
| **截图/PDF** | `playwright_screenshot` | `src/tools/browser/screenshot.ts:1-77` | PNG 写盘 + base64 内存 |
|  | `playwright_save_as_pdf` | `src/tools/browser/output.ts:8-30` | `page.pdf({ path, format, margin })` |
| **设备/UA** | `playwright_resize` | `src/tools/browser/resize.ts:8-114` | `page.setViewportSize` + `playwright.devices` |
|  | `playwright_custom_user_agent` | `src/tools/browser/useragent.ts:12-39` | **仅校验**已生效的 UA，不主动设 |
| **网络** | `playwright_expect_response` | `src/tools/browser/response.ts:21-37` | `page.waitForResponse` 存到 Map |
|  | `playwright_assert_response` | `src/tools/browser/response.ts:42-86` | 从 Map 取 promise 校验 body |

> **注意 `playwright_custom_user_agent` 是反直觉的**——从代码看（`src/tools/browser/useragent.ts:22-32`），它不做"设置"动作，而是 **验证** 当前 page 的 UA 是否等于参数。真正的 UA 设置只在 `ensureBrowser` 初始化 `BrowserContext` 时生效（`src/toolHandler.ts:302-309`），且只能从 `playwright_navigate` 的 `args.userAgent` 注入（`src/toolHandler.ts:530`）。

#### Q2.2 URL 网页访问（`playwright_navigate`）

**实现位置**：`src/tools/browser/navigation.ts:8-58`

```ts
// src/tools/browser/navigation.ts:29-34
return this.safeExecute(context, async (page) => {
  try {
    await page.goto(args.url, {
      timeout: args.timeout || 30000,
      waitUntil: args.waitUntil || "load"
    });
    return createSuccessResponse(`Navigated to ${args.url}`);
```

| 维度 | 现状 | 证据 |
|---|---|---|
| API | `page.goto(url, { timeout, waitUntil })`（Playwright 原生） | `navigation.ts:31-34` |
| **超时控制** | ✅ `timeout: args.timeout \|\| 30000`（30s 默认） | `navigation.ts:32` |
| **等待策略** | ⚠️ `waitUntil: args.waitUntil \|\| "load"`（**默认 `load`，非 `networkidle`**） | `navigation.ts:33` |
| **重试机制** | ❌ 无 | — |
| **反爬虫对抗** | ❌ 无 | 没有 `playwright-extra` / `puppeteer-extra-stealth`，没隐藏 `navigator.webdriver` |
| **代理支持** | ❌ 无 | `browserInstance.launch({ headless, executablePath })` 不传 `proxy` |
| **User-Agent** | ⚠️ 仅支持 navigate 时一次性设置（`args.userAgent` → `BrowserContext`） | `src/toolHandler.ts:530, 302-309` |

> 讽刺的细节：测试代码 `src/__tests__/tools/browser/navigation.test.ts:53, 70` 里 **断言** `waitUntil: 'networkidle'`，但生产代码默认是 `'load'`。可能是测试期望值与实现漂移的 bug。

#### Q2.3 网页 HTML 过大处理

**核心实现**：`src/tools/browser/visiblePage.ts:72-194`（`VisibleHtmlTool`）

**配置参数**（`src/tools.ts:402-419`）：
```ts
{
  selector?: string,
  removeScripts?: boolean,   // 默认 true
  removeComments?: boolean,  // 默认 false
  removeStyles?: boolean,    // 默认 false
  removeMeta?: boolean,      // 默认 false
  cleanHtml?: boolean,       // 默认 false（一次性全开）
  minify?: boolean,          // 默认 false
  maxLength?: number         // 默认 20000
}
```

**核心过滤逻辑**（`visiblePage.ts:120-180`）—— 在浏览器内用 DOMParser 处理：
```ts
if (removeScripts) doc.querySelectorAll('script').forEach(s => s.remove());
if (removeStyles)  doc.querySelectorAll('style').forEach(s => s.remove());
if (removeMeta)    doc.querySelectorAll('meta').forEach(s => s.remove());
if (removeComments) {/* 递归遍历删 nodeType === 8 */}
if (minify) result = result.replace(/>\s+</g, '><').trim();
```

**截断逻辑**（`visiblePage.ts:183-188`）—— **头截断，丢弃尾部**：
```ts
const maxLength = typeof args.maxLength === 'number' ? args.maxLength : 20000;
let output = htmlContent;
if (output.length > maxLength) {
  output = output.slice(0, maxLength) + '\n<!-- Output truncated due to size limits -->';
}
```

**VisibleTextTool**（`visiblePage.ts:8-67`）走另一条路：用 `TreeWalker` 遍历 text 节点，过滤 `display: none` / `visibility: hidden`（`visiblePage.ts:30-52`），同样 20000 字符头截断（line 54-60）。

| 处理维度 | 现状 | 评价 |
|---|---|---|
| **默认 `<script>` 剥离** | ✅ 默认 `removeScripts: true`（CHANGELOG v1.0.6 起） | OK |
| **头尾智能截断** | ❌ 仅头截断（slice(0, maxLength)） | 不够好，丢关键尾部内容 |
| **压缩到 Markdown** | ❌ 完全没有（无 `turndown` / `readability` / `cheerio`） | 缺失 |
| **完全旁路到磁盘** | ❌ 总是返回内联字符串 | 缺失，大页面会 OOM |
| **screenshot 图片压缩** | ❌ 总是 PNG，无 JPEG 选项，无 quality 参数（`screenshot.ts:22`） | 缺失 |
| **screenshot base64 size 限制** | ⚠️ 默认 `storeBase64: true`（`screenshot.ts:58`），无 size 上限；可通过 `storeBase64: false` 关掉 | 有内存风险 |

> **对 Onion Agent 的启发**：mcp-playwright-ea 的 HTML 处理 **不抓重点**——它只解决"别太大塞爆 LLM context"，但不解决"提取最有用的内容"。我们做 `non_head_browser.py` 重构时应该补齐：
> 1. 引入 `@mozilla/readability`（Mozilla 文章提取算法）+ `turndown`（HTML→Markdown）做"fetch + 自动读模式"
> 2. 大结果旁路到 `~/.cache/onion/.../<id>.html`，返回 path + 摘要

---

### Q3. fetch 功能实现

**核心结论：没有 `fetch` / `fetch_url` / `fetch_markdown` 工具。是 5 个分离的 HTTP 方法工具（`playwright_get/post/put/patch/delete`），构建在 Playwright 的 `request.newContext()` 之上。能力边界非常"API 客户端"而非"网页抓取"——没有 Readability / Markdown / 元数据提取，响应体硬截 1000 字符。**

#### 3.1 工具集合

5 个独立工具（`src/tools/api/requests.ts:87-289`）：
- `playwright_get`（line 87-117）
- `playwright_post`（line 122-163）
- `playwright_put`（line 168-209）
- `playwright_patch`（line 214-255）
- `playwright_delete`（line 260-289）

#### 3.2 与"获取 HTML"工具的区别

| 维度 | `playwright_get/post/...` | `playwright_get_visible_html` |
|---|---|---|
| 是否需要浏览器 | ❌ 不启动浏览器 | ✅ 需要 |
| HTTP 引擎 | `playwright.request.newContext()` | `page.content()` / DOMParser |
| 渲染 JS | ❌ 不渲染 | ✅ 渲染后拿 DOM |
| 用途 | API 客户端（JSON 通信） | 抓取渲染后的网页内容 |
| 速度 | 快（无浏览器启动） | 慢（需 30s~ 等待加载） |

#### 3.3 HTTP 请求层

```ts
// src/toolHandler.ts:402-406
async function ensureApiContext(url: string) {
  return await request.newContext({
    baseURL: url,    // 注意：url 被作为 baseURL，而非完整 URL；调用时再传 url
  });
}
```

底层是 **Playwright 的 `request.newContext()`**（即 node-fetch 系的封装，不是 axios / undici）。

#### 3.4 请求构造

`src/tools/api/requests.ts:45-65`（`buildHeaders`）：
```ts
function buildHeaders(token?, customHeaders?, includeContentType = false) {
  const headers: Record<string, string> = {};
  if (includeContentType) headers['Content-Type'] = 'application/json';
  if (token) headers['Authorization'] = `Bearer ${token}`;
  if (customHeaders) {
    if (token && customHeaders['Authorization']) {
      console.warn('Both token and Authorization header provided. Custom Authorization header will override token.');
    }
    Object.assign(headers, customHeaders);
  }
  return headers;
}
```

| 能力 | 现状 | 证据 |
|---|---|---|
| **自定义 headers** | ✅ `headers: Record<string, string>` | `requests.ts:45-65`、`tools.ts:280-283` |
| **Bearer token** | ✅ `token` 参数（自定义 Authorization 优先） | `requests.ts:52-54, 58-60` |
| **Content-Type** | ✅ POST/PUT/PATCH 默认 `application/json` | `requests.ts:48-50, 146` |
| **请求 body** | ✅ POST/PUT/PATCH 接受 `value: string \| object` | `requests.ts:135-141, 144-147` |
| **JSON 解析** | ✅ `parseJsonSafely` + `{`/`[` 启发式校验 | `requests.ts:25-36, 135-141` |
| **Header 校验** | ✅ `validateHeaders`（value 必须是 string） | `requests.ts:72-82, 94-96` |
| **`maxRedirects` 控制** | ❌ 无（依赖 Playwright 默认） | — |
| **请求 timeout** | ❌ 无暴露 | — |
| **请求 body size 限制** | ❌ 无限制 | — |
| **Cookie 管理** | ❌ 无（Playwright context 默认禁用 cookie） | — |
| **代理** | ❌ 无 `proxy` 字段 | — |
| **重试** | ❌ 无 | — |
| **错误分类** | ❌ 只把 `error.message` 拼成 `API operation failed: ...` | `src/tools/api/base.ts:60` |

#### 3.5 响应处理

**硬截 1000 字符**（`requests.ts:113, 159, 205, 251, 286`）：
```ts
return createSuccessResponse([
  `GET request to ${args.url}`,
  `Status: ${response.status()} ${response.statusText()}`,
  `Response: ${responseText.substring(0, 1000)}${responseText.length > 1000 ? '...' : ''}`
]);
```

| 能力 | 现状 | 评价 |
|---|---|---|
| **多格式输出** | ❌ 始终返回 string（不区分 HTML/JSON/Markdown/Text） | 缺失 |
| **元数据提取**（title/og:image/...） | ❌ 完全没做 | 缺失 |
| **正文提取**（Readability / `<article>` / `<main>`） | ❌ 完全没做 | 缺失 |
| **响应体 size 限制** | ⚠️ 仅 1000 字符硬截（`substring(0, 1000)`） | 防 OOM 但太少 |
| **错误分类**（404/403/5xx/timeout/DNS） | ❌ 全归一为 `API operation failed: <msg>` | 缺失 |
| **响应 headers 回传** | ❌ 只回 status + body | 缺失 |

#### 3.6 与"专业 fetch MCP"对比

| 维度 | mcp-playwright-ea (`playwright_get`) | zcaceres/fetch-mcp（参考） |
|---|---|---|
| HTML/Markdown 双格式 | ❌ 只 string | ✅ 显式 `format` 参数 |
| Readability 提取 | ❌ | ✅ 内置 |
| 长度限制 | 1000 硬截 | `max_length` 参数 |
| 错误分类 | ❌ | ✅ 详细分类 |
| 渲染层 | Playwright request context | cheerio / jsdom |

> **结论**：mcp-playwright-ea 的 fetch 工具是"API 客户端"定位（适合 REST API 调试），**不适合做"网页抓取+摘要"**——后者要专门搭一个 fetch MCP（如 zcaceres/fetch-mcp）。

---

## 3. 关键代码片段

### 3.1 自动安装浏览器（核心创新）

`src/toolHandler.ts:164-216`：

```ts
async function installBrowsers(browserType: string = 'chromium'): Promise<{ success: boolean; message: string }> {
  return new Promise((resolve) => {
    console.error(`[Playwright MCP] Attempting to install ${browserType} browser...`);

    const installProcess = spawn('npx', ['playwright', 'install', browserType], {
      stdio: ['ignore', 'pipe', 'pipe']   // CHANGELOG v1.0.12: 移除 shell:true
    });

    let output = '';
    let errorOutput = '';

    installProcess.stdout?.on('data', (data) => { output += data.toString(); });
    installProcess.stderr?.on('data', (data) => { errorOutput += data.toString(); });

    installProcess.on('close', (code) => {
      if (code === 0) {
        console.error(`[Playwright MCP] Successfully installed ${browserType} browser`);
        resolve({ success: true, message: `Successfully installed ${browserType} browser. Please try your request again.` });
      } else {
        resolve({ success: false, message: `Failed to automatically install ${browserType} browser. Please run: npx playwright install ${browserType}` });
      }
    });

    installProcess.on('error', (error) => {
      resolve({ success: false, message: `Error during installation: ${error.message}. Please run: npx playwright install ${browserType}` });
    });

    setTimeout(() => {
      installProcess.kill();
      resolve({ success: false, message: `Browser installation timed out. Please run manually: npx playwright install ${browserType}` });
    }, 120000);   // 2 分钟超时
  });
}
```

### 3.2 Navigate 简单粗暴

`src/tools/browser/navigation.ts:8-58`：

```ts
export class NavigationTool extends BrowserToolBase {
  async execute(args: any, context: ToolContext): Promise<ToolResponse> {
    if (!context.browser || !context.browser.isConnected()) {
      resetBrowserState();
      return createErrorResponse("Browser is not connected. The connection has been reset - please retry your navigation.");
    }
    if (!context.page || context.page.isClosed()) {
      return createErrorResponse("Page is not available or has been closed. Please retry your navigation.");
    }

    return this.safeExecute(context, async (page) => {
      try {
        await page.goto(args.url, {
          timeout: args.timeout || 30000,
          waitUntil: args.waitUntil || "load"   // 注意：默认 'load'，不是 'networkidle'
        });
        return createSuccessResponse(`Navigated to ${args.url}`);
      } catch (error) {
        // ... 错误处理 + resetBrowserState
      }
    });
  }
}
```

### 3.3 HTML 截断（"头切"模式）

`src/tools/browser/visiblePage.ts:183-188`：

```ts
// Truncate logic
const maxLength = typeof args.maxLength === 'number' ? args.maxLength : 20000;
let output = htmlContent;
if (output.length > maxLength) {
  output = output.slice(0, maxLength) + '\n<!-- Output truncated due to size limits -->';
}
return createSuccessResponse(`HTML content:\n${output}`);
```

### 3.4 API 请求响应截断（1000 字符硬限）

`src/tools/api/requests.ts:110-114`：

```ts
return createSuccessResponse([
  `GET request to ${args.url}`,
  `Status: ${response.status()} ${response.statusText()}`,
  `Response: ${responseText.substring(0, 1000)}${responseText.length > 1000 ? '...' : ''}`
]);
```

### 3.5 HTTP 模式 + 127.0.0.1 绑定

`src/http-server.ts:217-221`：

```ts
// SECURITY: Bind to localhost only to prevent external access
const host = '127.0.0.1';

return new Promise<void>((resolve, reject) => {
  const httpServer = app.listen(port, host, () => {
    logger.info(`Playwright MCP HTTP server listening on ${host}:${port}`, { ... });
```

---

## 4. 与 Onion Agent non_head_browser.py 重构的关联

3 点启发：

1. **"自动检测 + 自动安装"是降低用户门槛的关键能力**——但 `mcp-playwright-ea` 的实现依赖 `npx playwright install` 走 Playwright 官方 CDN，**国内/信创环境会失败**。Onion Agent 应当：(a) 把 `CHROME_EXECUTABLE_PATH` 环境变量作为首选支持（比自动 install 更可靠）；(b) 启动前先检查 `~/.cache/ms-playwright` 是否已有可执行文件，避免每次都走 install；(c) 提供"信创版 Chromium 路径"配置项。

2. **"HTML 截断"是表层优化，"读+提取"才是 LLM 真正需要的**——mcp-playwright-ea 只做 `slice(0, 20000)`，不解决"页面核心内容在哪"。Onion Agent 应在 `non_head_browser.py` 里：(a) 默认用 `@mozilla/readability` + `trafilatura` 提取正文；(b) 把正文转 Markdown 后再喂给 LLM（更省 token、更结构化）；(c) 大结果（>50KB）旁路到 `~/.cache/onion/.../`，返回 path + 摘要 + `load_file` 工具供后续按需读取。

3. **"fetch 工具"与"浏览器抓取"是两回事**——mcp-playwright-ea 把 `playwright_get` 做成"无头 API 客户端"（无 JS 渲染、无 Readability、1000 字符硬截），是 REST 调试定位而不是网页抓取定位。Onion Agent 应该：(a) 把这两类拆成两个 MCP tool（`http_request` + `webpage_fetch`）；(b) `webpage_fetch` 应支持 `format: "html" | "markdown" | "text"`、`max_length`、元数据提取（title/og:image/author）、错误分类（404/403/5xx/timeout）。

---

## 5. 不确定 / 未找到

| # | 不确定项 | 备注 |
|---|---|---|
| 1 | `playwright_custom_user_agent` 的实际语义 | 代码看是 **验证** UA 而非 **设置** UA（`src/tools/browser/useragent.ts:22-32`），但 `tools.ts:382-392` 的 schema 写的是 "Set a custom User Agent"。可能是文档与实现漂移，或早期版本是 setter 后期改成 validator。从代码逻辑判断当前是 validator。 |
| 2 | `playwright_navigate` 默认 `waitUntil` 的真实期望 | 生产代码默认 `'load'`，但 `src/__tests__/tools/browser/navigation.test.ts:53, 70` 断言 `'networkidle'`。可能是有意为之（更严格的测试），也可能是测试期望值未同步实现。 |
| 3 | `CHROME_EXECUTABLE_PATH` 是否对所有浏览器都生效 | 代码只在 chromium 分支里读它，但 `firefox` / `webkit` 的 `launch()` 也接受 `executablePath`。从代码 `src/toolHandler.ts:263-268` 看是**对所有 browserType 都生效**的，但因为是 `executablePath` 单一字段，传 firefox 路径但 `browserType: 'chromium'` 就会启动失败。命名暗示只服务 Chrome。 |
| 4 | HTTP 模式下多 session 是否共享浏览器 | `src/http-server.ts:76-91` 每个 session 创建一个新 `Server`，但 `ensureBrowser` 是 module-level 单例（`src/toolHandler.ts:51-53`），意味着 **所有 session 共享同一个 browser + page**——多客户端并发会互相干扰。这是单进程多客户端的潜在风险。 |
| 5 | `playwright_expect_response` 的 timeout | 没用 `Promise.race` + timeout 包裹，依赖 `page.waitForResponse(url)` 默认 30s。若 `assert_response` 永远不被调用，promise 永远 hang 住、占用 Map 内存。 |
| 6 | `playwright_console_logs` 的内存清理 | `src/tools/browser/console.ts:8` 是 `private consoleLogs: string[] = []`，只在 `args.clear: true` 时清空。否则无界增长，**长会话会 OOM**。 |
| 7 | v1.0.12 自动安装能否在国内网络下成功 | 没有自动重试 `PLAYWRIGHT_DOWNLOAD_HOST`，也没有降级到"提示用户手动安装"的友好提示（CHANGELOG 说 "Graceful fallback with helpful manual installation instructions"，但代码里 `console.error` 输出的就是 `npx playwright install chromium` 命令，没有镜像提示）。 |

---

**调研完成**。
