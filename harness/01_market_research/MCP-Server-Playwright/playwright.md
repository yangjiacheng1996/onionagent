# MCP-Server-Playwright（Automata-Labs-team）— Playwright 浏览器自动化调研报告

## 0. 项目一句话定位

Automata Labs 团队开发的极简 Playwright MCP server，把 `playwright` 的核心交互（导航、点击、填表、悬停、选择、JS 执行、截图）包装为 10 个 MCP tool，主打"小而美"的浏览器自动化能力，**不提供 HTML 提取 / fetch / Readability / 等待类工具**。

> 来源：awesome-mcp-servers browser-automation 章节；`README.md:6-7`（"browser automation capabilities using Playwright"）。

---

## 1. 调研依据

- **源码路径**：`C:\workspace\github\onionagent\harness\01_market_research\clone\MCP-Server-Playwright`
- **项目规模**：14 个文件 / 0.07 MB；**整个实现就是一个 `index.ts`（758 行）+ 配置文件**，没有 `src/` 目录、没有 `tools/` 子目录。
- **关键文件 / 关键代码片段**：
  - `index.ts:1-758` — **全部源代码**（工具定义 + 浏览器生命周期 + 工具实现 + Claude 配置写入）
  - `index.ts:22-33` — `ToolName` 枚举（10 个工具）
  - `index.ts:36-152` — `TOOLS` 数组（工具 schema 集中定义）
  - `index.ts:160-178` — `ensureBrowser()`（浏览器懒启动 + console 监听）
  - `index.ts:180-572` — `handleToolCall()`（所有工具的 switch 实现）
  - `index.ts:574-585` — `Server` 实例化
  - `index.ts:589-632` — Resources 处理器（`console://logs` + `screenshot://<n>`）
  - `index.ts:649-737` — `checkPlatformAndInstall()`（Claude Desktop 配置写入）
  - `index.ts:739-758` — CLI 入口（`yargs` + `install` 子命令）
  - `package.json:25-29` — 依赖：`@modelcontextprotocol/sdk@0.5.0` + `playwright@^1.48.0` + `yargs@^17.7.2`
  - `CHANGELOG.md:1-26` — 版本演变（v1.0.0 → v1.2.1）
  - `Dockerfile:1-31` — **不含 `npx playwright install`**，Docker 镜像实际无法跑通
  - `smithery.yaml:1-15` — Smithery 启动配置
- **文档 / README 引用**：
  - `README.md:29-35` — Features 列表（4 条：全功能、截图、交互、JS 执行）
  - `README.md:81-110` — Cursor 集成 + 手动 `npx playwright install` 提示
  - `README.md:114-199` — 10 个 Tool 的 schema 描述

---

## 2. 三个核心问题的回答

### Q1. Playwright 无头浏览器安装

#### 结论：**完全不自动，需用户手动 `npx playwright install`**

| 维度 | 结论 | 证据 |
|---|---|---|
| 用户是否需手动安装 | **是** | `README.md:85-88`："**Install Playwright browsers** (if not already): `npx playwright install`" |
| 是否自动检测 + 自动安装 | **否**，无任何 auto-install 逻辑 | `index.ts:160-178` `ensureBrowser()` 只调 `playwright.firefox.launch()`，捕获不了二进制缺失错误；`index.ts:649-737` `install` 子命令只写 Claude Desktop 配置，不下载浏览器 |
| 默认浏览器 | **Firefox**（**注意：非 headless**） | `index.ts:162`：`browser = await playwright.firefox.launch({ headless: false })` |
| 浏览器二进制存储 | **Playwright 默认路径**（未自定义）<br/>- Windows：`%LOCALAPPDATA%\ms-playwright`<br/>- macOS：`~/Library/Caches/ms-playwright`<br/>- Linux：`~/.cache/ms-playwright` | 源码无 `PLAYWRIGHT_BROWSERS_PATH` 或 `launchOptions.executablePath` 设置，依赖 Playwright 内部默认 |
| 离线 / 国内网络 | **未涉及** | README 无 `PLAYWRIGHT_DOWNLOAD_HOST` / 镜像源说明；Dockerfile 无 `npx playwright install` |
| 本地已装浏览器 | **不支持** | `index.ts:162` 启动参数只有 `headless`，没有 `executablePath` / `channel: 'chrome'` / `channel: 'msedge'` |
| Linux xvfb | **v1.2.0 曾加入，v1.2.1 回滚** | `CHANGELOG.md:5-7`：v1.2.1 两个 commit 都是 "Revert"（`b910dba` 回滚 xvfb、`56934ed` 回滚 "use chromium as default browser"） |

#### 关键代码证据

`index.ts:160-163`（浏览器启动）：
```typescript
async function ensureBrowser() {
  if (!browser) {
    browser = await playwright.firefox.launch({ headless: false });
  }
```

`index.ts:739-750`（CLI 入口 — install 子命令只做 Claude 配置写入，不下载浏览器）：
```typescript
await yargs(hideBin(process.argv))
  .command('install', 'Install MCP-Server-Playwright dependencies', () => {}, async () => {
    await checkPlatformAndInstall();
    process.exit(0);
  })
```

`Dockerfile:1-31` — **没有 `npx playwright install` 步骤**，镜像内 Firefox 二进制根本不存在，容器一启动就崩。

#### ⚠️ 隐患
1. `headless: false` 意味着必须有图形显示环境；服务器 / Docker / WSL 无 GUI 场景下 **直接失败**。
2. v1.1.0 曾"默认改用 chromium"，v1.2.1 又回滚到 firefox — 说明上游 Playwright 与各浏览器版本兼容性维护成本较高，稳定性不佳。
3. Firefox 在 Playwright 上的 binary 体积比 chromium 还大，国内下载更慢。

---

### Q2. 浏览器自动化功能 + URL 访问 + HTML 压缩

#### Q2.1 浏览器自动化功能清单（10 个 tool）

| 工具名 | 类别 | 输入参数 | 输出 | 代码位置 |
|---|---|---|---|---|
| `browser_navigate` | 导航 | `url: string` | `text: "Navigated to {url}"`（**不返回页面内容**） | `index.ts:38-47`（schema），`index.ts:184-192`（实现） |
| `browser_screenshot` | 提取 | `name: string`（必填）、`selector?: string`、`fullPage?: boolean` | `[text, image/png base64]` 双内容块 | `index.ts:48-60`，`index.ts:194-231` |
| `browser_click` | 交互 | `selector: string` | `text: "Clicked: {selector}"` | `index.ts:61-71`，`index.ts:233-273` |
| `browser_click_text` | 交互 | `text: string` | `text: "Clicked element with text: {text}"` | `index.ts:72-82`，`index.ts:275-314` |
| `browser_fill` | 交互 | `selector: string`、`value: string` | `text: "Filled {selector} with: {value}"` | `index.ts:83-94`，`index.ts:316-355` |
| `browser_select` | 交互 | `selector: string`、`value: string` | `text: "Selected {selector} with: {value}"` | `index.ts:95-106`，`index.ts:357-396` |
| `browser_select_text` | 交互 | `text: string`、`value: string` | `text: "Selected element with text..."` | `index.ts:107-118`，`index.ts:398-437` |
| `browser_hover` | 交互 | `selector: string` | `text: "Hovered {selector}"` | `index.ts:119-129`，`index.ts:439-478` |
| `browser_hover_text` | 交互 | `text: string` | `text: "Hovered element with text..."` | `index.ts:130-140`，`index.ts:480-519` |
| `browser_evaluate` | JS 执行 | `script: string` | `text: "Execution result:\n{json}\n\nConsole output:\n{logs}"` | `index.ts:141-151`，`index.ts:521-561` |

**Resources（2 个，区别于 tool）**：
- `console://logs` — 浏览器 console 累积输出（`index.ts:589-602` 注册、`index.ts:604-632` 读取）
- `screenshot://<n>` — 已命名截图的 base64 列表（命名空间由 `browser_screenshot` 的 `name` 参数决定）

**全局状态**（`index.ts:155-158`）：
```typescript
let browser: Browser | undefined;        // 全局单例
let page: Page | undefined;              // 全局单例
const consoleLogs: string[] = [];        // console 累积
const screenshots = new Map<string, string>();  // name -> base64
```

**不支持的类别**（与同类型项目对比）：
- ❌ 等待类（`wait_for_selector` / `wait_for_navigation` / `wait_for_timeout`）
- ❌ HTML 文本提取（`get_visible_text` / `get_visible_html` / `get_attribute`）
- ❌ 导航历史（`go_back` / `go_forward` / `reload` / `new_page` / `close_page`）
- ❌ 拖拽 / 按键 / 文件上传
- ❌ iframe 操作 / 多 tab / 设备模拟
- ❌ PDF 保存 / codegen / 录制

#### Q2.2 URL 网页访问如何实现？

**仅一行代码**：`index.ts:184-192`：
```typescript
case ToolName.BrowserNavigate:
  await page.goto(args.url);
  return {
    content: [{
      type: "text",
      text: `Navigated to ${args.url}`,
    }],
    isError: false,
  };
```

| 维度 | 结论 |
|---|---|
| 调用的 API | `page.goto(url)`，Playwright 标准 API |
| 超时控制 | **无** — 不传 `timeout`，用 Playwright 默认 30s |
| 等待策略 | **无** — 不传 `waitUntil`，用默认 `load` |
| 重试机制 | **无** |
| 反爬虫对抗 | **无** — 不设置 User-Agent、不隐藏 `navigator.webdriver`、不支持代理 |
| 返回内容 | **仅字符串** `"Navigated to {url}"`，**不返回 HTML / 标题 / 状态码** |

#### Q2.3 网页 HTML 过大如何处理？

**该项目没有 HTML 提取工具，因此不存在"HTML 过大"问题。**

要从页面拿内容，**只能通过 `browser_evaluate` 工具**手写 JS，例如：
- `document.title` → 拿标题
- `document.body.innerText` → 拿可见文本（受 outerHTML 大小无限制，可能几 MB 一次性塞进 LLM context）
- `document.documentElement.outerHTML` → 拿完整 HTML（更大，更危险）

`browser_evaluate` 实现（`index.ts:521-561`）：
```typescript
case ToolName.BrowserEvaluate:
  try {
    const result = await page.evaluate((script) => {
      // ... 重写 console 收集日志
      const result = eval(script);
      return { result, logs };
    }, args.script);
    return {
      content: [{
        type: "text",
        text: `Execution result:\n${JSON.stringify(result.result, null, 2)}\n\nConsole output:\n${result.logs.join('\n')}`,
      }],
      isError: false,
    };
```

**HTML 压缩相关功能：全部 0 项**

| 功能 | 是否有 |
|---|---|
| `max_length` / `max_chars` 参数 | ❌ |
| 头尾截断 / 智能截断 | ❌ |
| `<script>` / `<style>` 标签剥离 | ❌ |
| HTML → Markdown 转换（`turndown` / `readability`） | ❌ |
| 大结果旁路到磁盘 | ❌ |

**截图（screenshot）相关**：

| 功能 | 是否有 |
|---|---|
| base64 限制 | ❌ — `index.ts:200` 直接 `screenshot.toString('base64')`，**无大小校验** |
| 图片压缩 | ❌ — PNG 原始输出，无 `quality` / `type: 'jpeg'` |
| 磁盘溢出保护 | ❌ — `index.ts:158` `screenshots` 是内存 `Map<string, string>`，**永远不会清理**，跑久了 OOM |

`index.ts:194-231` 关键代码：
```typescript
const screenshot = await (args.selector ?
  page.locator(args.selector).screenshot() :
  page.screenshot({ fullPage }));  // 注意 line 195: fullPage = (args.fullPage === 'true')
                                   // 字符串比较 'true'，对 boolean 永远 false！
const base64Screenshot = screenshot.toString('base64');
screenshots.set(args.name, base64Screenshot);
```

**Bug 发现**：`index.ts:195` `(args.fullPage === 'true')` 永远为 false（Yargs 解析后 `fullPage` 是 boolean，不是字符串 `'true'`），**`fullPage` 参数实际无效**。

#### Q2.4 错误处理亮点

虽然 HTML/截图压缩 0 实现，但 **strict mode violation 兜底**值得借鉴 — 每个交互类工具都有同样的两段重试模式：

`index.ts:233-273`（`browser_click`）：
```typescript
try {
  await page.locator(args.selector).click();
  // ...
} catch (error) {
  if ((error as Error).message.includes("strict mode violation")) {
    // 退回到 .first() 重试
    await page.locator(args.selector).first().click();
    // ...
  }
  return { isError: true, /* ... */ };
}
```

`browser_click_text`（`index.ts:286-289`）、`browser_fill`（`index.ts:327-330`）、`browser_select`（`index.ts:368-371`）、`browser_hover`（`index.ts:450-453`）**全部一致** — 用文字定位时直接退到第一个匹配元素。这是个比较贴心的 LLM 容错设计：LLM 给的 selector 经常有歧义，自动取第一个匹配比直接报错好。

---

### Q3. fetch 功能实现

#### 结论：**完全没有 fetch 工具，HTTP 层隐藏在 `page.goto` 内部**

| 维度 | 结论 | 证据 |
|---|---|---|
| 是否有专门 `fetch` / `fetch_url` / `fetch_markdown` 工具 | **无** | `index.ts:36-152` `TOOLS` 数组里无 `fetch` 相关工具；`ToolName` 枚举（`index.ts:22-33`）也无 |
| 与 Q2 工具的关系 | **完全替代** — Q2 的"获取 HTML"路径不存在，所有内容获取只能靠 `browser_evaluate` 写 JS | `index.ts:521-561` |
| 多格式输出（HTML / Markdown / Text / JSON-LD） | **无** | 仅 `browser_evaluate` 的 `JSON.stringify(result, null, 2)` 输出 |
| 元数据提取（title / author / og:image） | **无内置**，要靠 `browser_evaluate` + JS 自取 |  |
| Readability / `<article>` / `<main>` 提取 | **无** |  |
| HTTP 请求层 | **Playwright 内置**（Chromium / Firefox 网络栈） | `index.ts:20`：`import playwright, { Browser, Page } from "playwright"` |
| 自定义 headers / Cookie / Authorization | **无** | `page.goto()` 不传 `extraHTTPHeaders` |
| 代理 | **无** | `launch()` 不传 `proxy` |
| 重定向跟随控制 | **无** — 用 Playwright 默认 |  |
| 请求 / 响应大小限制 | **无** |  |
| 错误分类（404 / 403 / 5xx / DNS 失败） | **无** — 失败时 Playwright 抛 `page.goto` 异常，**未捕获**，整个 tool 调用会冒到 MCP 协议层 | `index.ts:185` 没有 try/catch |

**Q3 与 Q2 的工具关系总结**：

```
┌─────────────────────────────────────────────┐
│  没有 fetch 工具                            │
│  没有 HTML/text 提取工具                    │
│  没有 Readability / Markdown 转换工具       │
├─────────────────────────────────────────────┤
│  唯一的内容获取通道：browser_evaluate + JS   │
│  示例：                                    │
│    script: "document.title"                │
│    script: "document.body.innerText"       │
│    script: "fetch('/api').then(r=>r.json())"│
└─────────────────────────────────────────────┘
```

这与同类型项目（如 `zcaceres/fetch-mcp`、`anaisbetts/mcp-installer` 风格的项目）形成鲜明对比 — 后者专门做 HTTP fetch + 格式转换；本项目**完全聚焦"操作浏览器"**，把内容获取推给 LLM 在 `browser_evaluate` 里手写。

---

## 3. 关键代码片段

#### 片段 1：浏览器懒启动 + console 监听（`index.ts:160-178`）

```typescript
async function ensureBrowser() {
  if (!browser) {
    browser = await playwright.firefox.launch({ headless: false });
  }
  if (!page) {
    page = await browser.newPage();
  }
  page.on("console", (msg) => {
    const logEntry = `[${msg.type()}] ${msg.text()}`;
    consoleLogs.push(logEntry);
    server.notification({
      method: "notifications/resources/updated",
      params: { uri: "console://logs" },
    });
  });
  return page!;
}
```

设计要点：浏览器首次 tool 调用才启动（lazy init），`console` 事件持续累积并通过 MCP `resources/updated` 通知客户端刷新。

#### 片段 2：10 个工具的 schema 集中定义（`index.ts:36-152`）

```typescript
const TOOLS: Tool[] = [
  {
    name: ToolName.BrowserNavigate,
    description: "Navigate to a URL",
    inputSchema: {
      type: "object",
      properties: { url: { type: "string" } },
      required: ["url"],
    },
  },
  // ... 9 个类似定义
];
```

设计要点：所有工具在一个 `TOOLS` 数组里集中声明，**没有把每个 tool 拆到独立文件**。对小型项目非常合理。

#### 片段 3：strict mode violation 兜底（`index.ts:233-273`）

```typescript
case ToolName.BrowserClick:
  try {
    await page.locator(args.selector).click();
    return { content: [{ type: "text", text: `Clicked: ${args.selector}` }], isError: false };
  } catch (error) {
    if ((error as Error).message.includes("strict mode violation")) {
      // LLM 给的 selector 经常匹配多个 → 自动退到第一个
      try {
        await page.locator(args.selector).first().click();
        return { content: [{ type: "text", text: `Clicked: ${args.selector}` }], isError: false };
      } catch (error) { /* fall through */ }
    }
    return { content: [{ type: "text", text: `Failed to click ${args.selector}: ${(error as Error).message}` }], isError: true };
  }
```

这是整个项目最值得借鉴的 LLM 友好设计 — **selector 多匹配时自动 `.first()` 重试**，避免把 strict mode 错误抛回给 LLM。

#### 片段 4：截图 base64 内存缓存（`index.ts:194-231`）

```typescript
case ToolName.BrowserScreenshot: {
  const fullPage = (args.fullPage === 'true');  // ⚠️ Bug: 永远 false
  const screenshot = await (args.selector ?
    page.locator(args.selector).screenshot() :
    page.screenshot({ fullPage }));
  const base64Screenshot = screenshot.toString('base64');
  screenshots.set(args.name, base64Screenshot);
  server.notification({ method: "notifications/resources/list_changed" });
  return {
    content: [
      { type: "text", text: `Screenshot '${args.name}' taken` } as TextContent,
      { type: "image", data: base64Screenshot, mimeType: "image/png" } as ImageContent,
    ],
    isError: false,
  };
}
```

设计要点：截图同时返回 inline（`ImageContent`）和存入 `screenshots` Map（通过 `screenshot://<name>` resource 二次读取）。**没有磁盘 fallback、没有大小限制、没有 LRU 清理**。

#### 片段 5：Claude Desktop 配置写入（`index.ts:649-737`）

```typescript
async function checkPlatformAndInstall() {
  const platform = os.platform();
  if (platform === "win32") {
    const configFilePath = path.join(os.homedir(), 'AppData', 'Roaming', 'Claude', 'claude_desktop_config.json');
    // ... 读 / 改 / 写 JSON
    config.mcpServers.playwright = {
      command: "npx",
      args: ["-y", "@automatalabs/mcp-server-playwright"]
    };
  } else if (platform === "darwin") {
    const configFilePath = path.join(os.homedir(), 'Library', 'Application Support', 'Claude', 'claude_desktop_config.json');
    // ... 同样逻辑
  } else {
    console.error("Unsupported platform:", platform);
    process.exit(1);
  }
}
```

设计要点：`install` 子命令只做 Claude Desktop 配置注入，**不支持 Linux**（直接报错退出）。这是 2024-12 的 v0.9.0 引入、至今未补齐。

---

## 4. 与 Onion Agent `non_head_browser.py` 重构的关联

本项目对 `non_head_browser.py` 的启发：

1. **"strict mode violation 自动 .first() 重试" 模式值得照搬** — `non_head_browser.py` 当前 LLM 给的 CSS selector 经常有歧义，原生 Playwright 会抛 strict mode 错误。让 `click / fill / hover / select` 在内部 try/catch 后退到 `.first()`，能显著降低 tool 调用失败率（见 `index.ts:233-273` 等 4 处一致实现）。
2. **保持单文件 + `TOOLS` 集中数组** — 当工具数 ≤ 20 时，把所有 schema 放在一个数组里比拆 `tools/navigate.py` + `tools/click.py` 更易维护，Onion Agent 早期可以借鉴这种"小而扁平"的代码组织。
3. **反面教材（要规避的设计）**：
   - `headless: false`（`index.ts:162`）— 服务器环境跑不起来，**务必强制 headless**；
   - 截图 `screenshots` Map 永不清理（`index.ts:158`）— **必须加 LRU / 数量上限**，否则长跑 OOM；
   - `fullPage === 'true'` 字符串比较 Bug（`index.ts:195`）— **类型校验要严格**；
   - 没有 fetch / HTML 提取 / Markdown 转换工具 — Onion Agent 必须补齐这一层。

---

## 5. 不确定 / 未找到

1. **`browser_navigate` 失败时的错误处理**：源码未用 try/catch 包裹 `page.goto`，**实际行为未实测**（404 / DNS 失败 / 超时是否会冒到 MCP 协议层抛错）。
2. **Firefox 与最新 Playwright 版本的兼容性**：CHANGELOG 暗示上游在 chromium / firefox 间反复横跳（v1.1.0 → chromium，v1.2.1 → 回滚 firefox），**未实测当前 `playwright@^1.48.0` + Firefox 默认启动是否稳定**。
3. **Linux 平台支持**：`install` 子命令（`index.ts:649-737`）**直接 `process.exit(1)`**，但 README 没明确说"不支持 Linux"；Dockerfile 也是 Linux，但**没装 Firefox 二进制**，实际跑必崩。
4. **`browser_evaluate` 安全性**：用 `eval(script)` 在页面 context 执行 LLM 生成的 JS，**无沙箱、无超时**，对不可信 prompt 有 XSS / DoS 风险。
5. **没找到 `dist/` 构建产物**（`.gitignore` 排除了），但 `package.json:14-16` 声明了 `bin: mcp-server-playwright` 指向 `dist/index.js` — 上游 npm 包应当预编译，本地 clone 无法直接 `node index.ts`（要 `tsc`）。
6. **`screenshots` Map 内存上限与清理策略**：源码 0 提及，长期运行的 server 必然 OOM。
7. **`server.notification` 调用**（`index.ts:172-175, 213-215`）：在 MCP SDK 0.5.0 版本上是否能正确触发客户端刷新，**未实测**。

---

> **调研者备注**：本项目是调研过的 Playwright MCP 中**代码量最小**的一个（单文件 758 行，工具数 10 个，无 fetch / 无 HTML 提取）。作为"小而美"的浏览器操作参考很合适，但**不适合直接当通用 fetch 工具使用**。
