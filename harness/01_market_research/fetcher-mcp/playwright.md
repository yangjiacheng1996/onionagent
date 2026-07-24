# fetcher-mcp — Playwright 浏览器自动化调研报告

## 0. 项目一句话定位

fetcher-mcp 是基于 Playwright 无头浏览器的 MCP server,定位**只读型**内容获取：暴露 `fetch_url` / `fetch_urls` 两个核心工具,通过 Chromium 渲染页面 + Mozilla Readability 智能提取正文 + Turndown 转 Markdown,目标场景是"把一个网页变成干净的 Markdown 喂给 LLM"。

## 1. 调研依据

- **源码路径**：`C:\workspace\github\onionagent\harness\01_market_research\clone\fetcher-mcp`（版本 `0.3.9`，见 `package.json:3`）
- **关键文件**：
  - `src/server.ts:14-50` — MCP server 装配（`tools` 数组 + `CallToolRequestSchema` handler）
  - `src/tools/index.ts:6-17` — 工具注册表（**只有 3 个 tool**）
  - `src/tools/fetchUrl.ts` — 单 URL 抓取
  - `src/tools/fetchUrls.ts` — 多 URL 并行抓取
  - `src/tools/browserInstall.ts` — Chromium 二进制自动安装（**双策略：本地 CLI → npx fallback**）
  - `src/services/browserService.ts` — Chromium 启动 + 反爬虫指纹 + 媒体屏蔽
  - `src/services/webContentProcessor.ts` — `page.goto` + Readability + Turndown 流水线
  - `src/utils/urlValidator.ts:16` — 协议白名单（只允许 `http:` / `https:`）
  - `src/config/args.ts:7-48` — CLI 解析（`--debug` / `--transport=http` / `--port` / `--host`）
  - `src/transports/http.ts` — 同时支持 Streamable HTTP (`/mcp`) + 旧 SSE (`/sse`) 两种传输
  - `package.json:19` — `postinstall: playwright install chromium`
  - `Dockerfile:36` — 镜像构建时 `npx playwright install --with-deps chromium`
- **文档 / README**：
  - `README.md:36-48` Quick Start（首次需 `npx playwright install chromium`）
  - `README.md:92-133` Docker / docker-compose 部署说明
  - `README.md:135-167` 三个 tool 的参数定义

## 2. 三个核心问题的回答

### Q1. Playwright 无头浏览器安装

**结论：完全自动 + 提供手动 fallback 工具，但不支持自定义浏览器路径。**

#### Q1.1 是否有 `postinstall` 自动安装？

✅ **有，且安装策略完备。** 三重保险：

1. **npm 装包时自动装**：`package.json:19` `"postinstall": "playwright install chromium"` — 只要用户 `npm install`，Chromium 二进制就会被下载。
2. **提供独立命令**：`package.json:18` `"install-browser": "npx playwright install chromium"`（README 也提示首次手动跑）。
3. **MCP 工具级安装**：`src/tools/browserInstall.ts:40-103` 暴露 `browser_install` 工具，让 LLM 在遇到错误时主动调用。**实现细节值得抄**：
   - `browserInstall.ts:110-145` **双策略 fallback**：先用 `require.resolve("playwright/package.json")` 找本地 CLI（保证版本一致），找不到再 fallback 到 `npx playwright install`（保证可用性）。
   - `browserInstall.ts:146-149` Windows 平台 `spawn` 自动加 `shell: true`。
   - `browserInstall.ts:50-58` 支持 `--with-deps`（Linux 系统依赖）和 `--force`（强制重装）。

#### Q1.2 二进制存储位置

**没有显式覆盖路径**，完全依赖 Playwright 默认位置：

- **Windows**：`%LOCALAPPDATA%\ms-playwright\chromium-<rev>\chrome-win\chrome.exe`
- **macOS**：`~/Library/Caches/ms-playwright/chromium-<rev>/chrome-mac/Chromium.app/Contents/MacOS/Chromium`
- **Linux**：`~/.cache/ms-playwright/chromium-<rev>/chrome-linux/chrome`

证据：`browserService.ts:137-150` 调用 `chromium.launch({ headless, args })` 时**没有传 `executablePath`**，所以完全走 Playwright 默认的 `PLAYWRIGHT_BROWSERS_PATH` 环境变量逻辑。

#### Q1.3 离线环境 / 国内网络

**❌ 源码未明确处理。** 整个 `src/` 没有任何关于：
- `PLAYWRIGHT_DOWNLOAD_HOST`（Playwright 官方提供的国内镜像环境变量）
- 离线 tarball 安装（`PLAYWRIGHT_DOWNLOAD_HOST` + 预下载 zip）
- `npm config set registry https://registry.npmmirror.com` 的提示

`browserInstall.ts:90-101` 错误处理也只是泛泛提示 "check your internet connection"，没给出国内镜像配置建议。**对信创 / 内网环境不友好**。

#### Q1.4 自定义本地浏览器路径 / `executablePath` / `channel`

**❌ 完全不支持。** `grep -i "executablePath|channel"` 在整个 `src/` 下零命中。`chromium.launch` 永远用默认 Playwright 内置 Chromium，无法切换到用户本机的 Chrome / Edge / Firefox。**对信创合规场景（如必须用国产 Chromium 套件）有适配门槛。**

#### Q1.5 Docker 支持

✅ **有，且构建时自动装好浏览器。**

- `Dockerfile:36` `RUN npx playwright install --with-deps chromium` — 镜像 build 阶段就把 Chromium + 系统依赖（libnss3 / libatk-bridge2.0 等）装好
- `Dockerfile:42` 默认以 HTTP transport + port 3000 启动
- `docker-compose.yml:5-9` 直接 `image: ghcr.io/jae-jae/fetcher-mcp:latest`，无需自建镜像
- `docker-compose.yml:13` 注释提到 `network_mode: "host"` 在 Linux 上可改善性能
- `docker-compose.yml:16` `/tmp:/tmp` 卷挂载（让 Playwright 用宿主机的临时目录）

### Q2. 浏览器自动化功能 + URL 访问 + HTML 压缩

#### Q2.1 工具清单（**只有 3 个**）

| 工具名 | 类别 | 输入参数 | 输出 | 代码路径 |
|---|---|---|---|---|
| `fetch_url` | 导航+提取 | `url` (req), `timeout`, `waitUntil`, `extractContent`, `maxLength`, `returnHtml`, `waitForNavigation`, `navigationTimeout`, `disableMedia`, `debug` | `text`（Title/URL/Content 格式） | `src/tools/fetchUrl.ts:11-74` |
| `fetch_urls` | 导航+提取（并行） | `urls` (req), 其余同 `fetch_url` | `text`（多个 webpage 块拼起来） | `src/tools/fetchUrls.ts:11-76` |
| `browser_install` | 环境 | `withDeps`, `force` | `text`（成功/失败消息） | `src/tools/browserInstall.ts:12-35` |

**关键定位：fetcher-mcp 是"只读型 fetch 工具"，故意没暴露 navigate/click/fill/screenshot/evaluate 等细粒度操作。**（grep `screenshot|cookie|proxy|executablePath|channel` 在 `src/` 下零命中）

#### Q2.2 URL 网页访问实现

- ✅ **标准 `page.goto`**：`webContentProcessor.ts:26-29` `await page.goto(url, { timeout, waitUntil })`
- ✅ **超时控制**：`fetchUrl.ts:90` 默认 30000ms，**有独立参数** `timeout` 和 `navigationTimeout`（专门给 `waitForNavigation` 用）
- ✅ **等待策略**：`types/index.ts:3` 支持 `'load' | 'domcontentloaded' | 'networkidle' | 'commit'`
- ✅ **`waitForNavigation` 反爬虫增强**：`webContentProcessor.ts:62-100` 首次 `page.goto` 后再用 `page.waitForNavigation` 等一轮，专门给"加载后跳转到验证页"的场景用
- ❌ **没有 URL 重试**：`grep -i "retry"` 只在 `webContentProcessor.ts:194` 命中，是 `safelyGetPageInfo` 内**单次** `page.content()` 失败的 3 次重试，**不是 URL 访问级别的重试**
- ✅ **反爬虫对抗做得很全**（`browserService.ts:66-112`）：
  - 隐藏 `navigator.webdriver`（返回 `false`）
  - 删除 `cdc_adoQpoasnfa76pfcZLmcfl_*` 反指纹变量
  - 注入 `window.chrome.runtime = {}`
  - 随机 UA（7 个版本混用 Chrome 122/123 + Firefox 123 + Safari 17.3）
  - 随机 viewport（1920×1080 / 1366×768 / 1536×864 / 1440×900 / 1280×720）
  - 随机 `deviceScaleFactor`（1 或 2）
  - 随机 plugin 数量（5-9 个）
  - 锁定 `Accept-Language=en-US` / `timezone=America/New_York` / `locale=en-US`
  - `chromium.launch` 加 `--disable-blink-features=AutomationControlled` 启动参数

#### Q2.3 HTML 过大处理

| 维度 | 实现 | 代码 |
|---|---|---|
| `maxLength` 截断 | ✅ **硬截断**（保留前 N 字符） | `webContentProcessor.ts:245-253` `processedContent.substring(0, this.options.maxLength)` |
| 截断策略 | ❌ **没有"头尾保留"**；只截头 | 同上 |
| `script`/`style` 标签剥离 | ✅ 由 `@mozilla/readability` 自动完成 | `webContentProcessor.ts:213-229` |
| HTML → Markdown 转换 | ✅ **turndown + turndown-plugin-gfm**（支持 GFM 表格） | `webContentProcessor.ts:236-238` |
| 截图 / base64 处理 | ❌ **无此功能**（工具集里没有 screenshot） | — |
| 旁路到磁盘（大结果写文件） | ❌ **未实现** | — |
| 资源屏蔽（图片/CSS/字体/媒体） | ✅ **`context.route("**/*", route.abort())`** | `browserService.ts:117-128`，`fetchUrl.ts:101` 默认 `disableMedia=true` |
| 等待页面稳定 | ✅ 等 `readyState === 'complete'` 再 `waitForTimeout(500)` | `webContentProcessor.ts:144-161` |
| **超时也尽量抢救** | ✅ **`page.goto` 超时后**不直接抛错，尝试 `page.title()` + `page.content()` 抢救已渲染部分 | `webContentProcessor.ts:30-59` |

**输出格式**：固定 `Title: <t>\nURL: <u>\nContent:\n\n<content>` 三段式（`webContentProcessor.ts:124`），方便 LLM 解析。

#### Q2.4 错误处理亮点

- `browserService.ts:152-177` 检测"浏览器未安装"错误（`executable doesn't exist` / `browser not found` / `chromium browser not found` 等 5 种关键字），抛 `BrowserNotInstalledError` 并提示 LLM 调用 `browser_install` 工具 — **MCP 工具间的自愈回路**
- `webContentProcessor.ts:130-140` 顶层 try/catch 把任何错误包装成 `Title: Error / URL: <u> / <error>...` 格式返回，**不抛 MCP exception**（让 LLM 看到的是可读错误而不是 stacktrace）

### Q3. fetch 功能实现

#### Q3.1 fetch 工具变体

**只有 1 个核心 + 1 个并行变体**，**没有** `fetch_html` / `fetch_markdown` / `fetch_readerable` 等多个细分工具。**通过参数组合控制行为**：

| 参数 | 作用 | 默认值 |
|---|---|---|
| `extractContent` | 是否用 Readability 抽正文（`true`）还是保留全 HTML | `true` |
| `returnHtml` | 输出 Markdown（`false`）还是 HTML | `false`（输出 Markdown） |
| `maxLength` | 输出字符数上限 | `0`（不限） |
| `disableMedia` | 是否屏蔽图片/CSS/字体 | `true`（省带宽） |
| `waitForNavigation` | 是否等二次跳转（反爬虫） | `false` |

通过这两个参数能组合出 4 种输出模式：
- `extractContent=true, returnHtml=false` → **Readability 提取后转 Markdown**（默认）
- `extractContent=true, returnHtml=true` → Readability 提取后保留 HTML
- `extractContent=false, returnHtml=false` → 全页面转 Markdown
- `extractContent=false, returnHtml=true` → 原始 HTML

**这是个不错的 API 设计**：用 2 个布尔参数替代 4 个工具名，减少 LLM 工具选择的认知负担。

#### Q3.2 正文提取算法

**`@mozilla/readability` + `jsdom`**（`webContentProcessor.ts:213-229`）：

```typescript
const virtualConsole = new VirtualConsole();
const dom = new JSDOM(html, { url, virtualConsole });
const reader = new Readability(dom.window.document);
const article = reader.parse();
contentToProcess = article.content;  // Firefox 用的同款正文提取
```

- Readability 是 Firefox 阅读模式的提取算法，对新闻/博客正文识别率很高
- **没找到文章时**会 fallback 到全 HTML（`webContentProcessor.ts:220-223`），不会直接报错
- Markdown 转换用 turndown + gfm 插件（`webContentProcessor.ts:236-238`），所以 Readability 输出的是 HTML，turndown 二次转 Markdown

#### Q3.3 HTTP / 渲染层

**全部用 Playwright 自带**，没有引入 axios / node-fetch / undici：

- `browserService.ts:1` `import { chromium } from "playwright"`
- 唯一的网络入口是 `page.goto`（`webContentProcessor.ts:26`）
- HTTP headers 在 `browserService.ts:197-209` 通过 `extraHTTPHeaders` 静态注入（含 `Sec-Fetch-*` 反爬虫特征）

#### Q3.4 Headers / Redirect / Size 限制

| 维度 | 现状 | 评价 |
|---|---|---|
| 自定义 headers（Cookie / Authorization） | ❌ **完全不支持** | LLM 无法传入 Cookie，登录态场景需用 `debug: true` 手动登录后复用 page（README 188-242 有说明） |
| 重定向控制 `maxRedirects` | ❌ 不暴露参数 | 走 Playwright 默认（应该是不限） |
| 响应 size 限制 | ❌ 不限制 | 只在 `maxLength` 输出层截断，原始 HTML 完整加载到内存 |
| 错误分类 | ❌ 不分类 | 4xx / 5xx / 网络超时统一返回 `Title: Error / <error>...`（`webContentProcessor.ts:130-140`），HTTP status code 不传给 LLM |
| 协议白名单 | ✅ 严格 | `urlValidator.ts:16` 只允许 `http:` / `https:`，拒绝 `file:` / `javascript:` / `data:`（安全加固） |
| URL 数组验证 | ✅ 容错 | `urlValidator.ts:65-101` 全部 URL 验证完才一次性报错，把失败的 URL 列表返回给 LLM |

## 3. 关键代码片段

### 3.1 反爬虫指纹注入（`browserService.ts:66-112`）

```typescript
await context.addInitScript(() => {
  // 隐藏 webdriver 标识
  Object.defineProperty(navigator, 'webdriver', { get: () => false });
  // 删除 ChromeDriver 注入的 cdc_ 变量
  delete (window as any).cdc_adoQpoasnfa76pfcZLmcfl_Array;
  // 注入假的 window.chrome 对象
  (window as any).chrome = { runtime: {} };
  // 伪造 plugins / languages
  Object.defineProperty(navigator, 'plugins', { get: () => [/* 5-9 个伪插件 */] });
  Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
});
```

### 3.2 超时也能抢救内容（`webContentProcessor.ts:30-59`）

```typescript
try {
  await page.goto(url, { timeout, waitUntil });
} catch (gotoError) {
  if (gotoError.message.includes("Timeout")) {
    // 抢一把：直接拿 page.content() 已有部分
    const { pageTitle, html } = await this.safelyGetPageInfo(page, url);
    if (html?.trim().length > 0) {
      // 哪怕超时也把已渲染的内容返回
      return { success: true, content: `Title: ${pageTitle}\nURL: ${url}\n\n...` };
    }
  }
  throw gotoError;  // 真的不行才抛
}
```

### 3.3 提取 + 转换 + 截断流水线（`webContentProcessor.ts:209-256`）

```typescript
private async processContent(html: string, url: string): Promise<string> {
  let contentToProcess = html;
  // 1) Readability 抽正文（可选）
  if (this.options.extractContent) {
    const dom = new JSDOM(html, { url, virtualConsole: new VirtualConsole() });
    const reader = new Readability(dom.window.document);
    const article = reader.parse();
    if (article) contentToProcess = article.content;
  }
  // 2) Turndown 转 Markdown（可选）
  let processedContent = contentToProcess;
  if (!this.options.returnHtml) {
    const turndownService = new TurndownService();
    turndownService.use(gfm);  // GFM 表格支持
    processedContent = turndownService.turndown(contentToProcess);
  }
  // 3) 硬截断
  if (this.options.maxLength > 0 && processedContent.length > this.options.maxLength) {
    processedContent = processedContent.substring(0, this.options.maxLength);
  }
  return processedContent;
}
```

### 3.4 浏览器自愈回路（`browserService.ts:152-177` + `browserInstall.ts:110-185`）

```typescript
// 启动时检测到 binary 缺失 → 抛特殊错误
if (this.isBrowserNotInstalledError(error)) {
  throw new Error(
    `Browser not installed. ${error.message}\n\n` +
    `💡 To fix this issue, please call the 'browser_install' tool ` +
    `to install the required browser binaries.`
  );
}

// browserInstall.ts: 双策略 fallback
// 策略1: 直接调本地 CLI（版本一致）
const playwrightCliPath = require.resolve("playwright/package.json")
  .replace("/package.json", "/cli.js");
// 策略2: 找不到就 spawn npx
command = "npx";
commandArgs = args;
```

## 4. 与 Onion Agent `non_head_browser.py` 重构的关联

**fetcher-mcp 给我的最大启发是"工具粒度要克制"**：它故意只暴露 fetch_url / fetch_urls / browser_install 三个工具，把 Chromium 当成"渲染引擎"而不是"自动化平台"。这对我们 `non_head_browser.py` 的启示：

1. **反爬虫指纹的代码可整段抄**：`browserService.ts:66-112` 的 navigator.webdriver / cdc_xxx / window.chrome / plugins / languages 注入逻辑，是 Python Playwright 几乎 1:1 可移植的（`page.add_init_script` 对应 Python 的 `context.add_init_script`）。
2. **`page.goto` 超时后抢救内容**（`webContentProcessor.ts:30-59`）是亮点 — 我们 `non_head_browser.py` 现在超时直接抛，太浪费。可以借鉴"超时后尝试拿已加载 DOM"的 fallback 模式。
3. **`browser_install` 双策略 fallback**（`browserInstall.ts:110-145`）值得学：本地 CLI 优先 / npx 兜底，对国内 npm 镜像环境更鲁棒。
4. **`maxLength` 硬截断不够好** — 我们的 `non_head_browser.py` 可以升级成"头 + 尾 + 中间省略"的智能截断（保留前 60% + 后 40%），或者 token 数截断，而不是 `substring(0, N)`。
5. **fetcher-mcp 缺的东西我们正好补上**：自定义 headers（Cookie/Authorization）、HTTP status code 透传、`maxRedirects` 控制、错误分类（4xx/5xx 区分）、旁路到磁盘模式。

## 5. 不确定 / 未找到

- **离线/国内镜像支持**：源码完全没提 `PLAYWRIGHT_DOWNLOAD_HOST` / 国内 npm 镜像配置，仅 README 一句"check your internet connection"。信创内网环境需要二次开发。
- **Cookie 持久化**：没有任何 cookie 持久化逻辑，每次 fetch 都是新 context（`browserService.ts:182-219` 每次 `browser.newContext()`），无法跨请求保持登录态。要保持登录只能靠 `debug: true` 手动登录。
- **`channel: 'chrome'` / `executablePath` 支持**：完全没有，固定用 Playwright 内置 Chromium，对信创合规场景（要求用特定国产浏览器套件）不友好。
- **错误分类粒度**：所有错误都包装成 `<error>...</error>` 字符串返回，HTTP 4xx / 5xx / 网络超时 / DNS 失败无法区分。LLM 只能根据错误文本判断。
- **screenshot / 截图功能**：完全没有，是"纯文本"型 fetch 工具。如果需要截图（如验证码识别 / 长网页留证）需要换 mcp-playwright 之类的全功能工具。
- **PDF 保存 / PDF 输出**：不支持。
- **并发上限控制**：`fetch_urls` 用 `Promise.all`（`fetchUrls.ts:123`）一次性全发，没看到并发数限制 — 10 个 URL 会同时开 10 个 page，资源占用可观。
- **重试机制**：URL 访问级别无重试，只有 `page.content()` 失败时的 3 次重试（`webContentProcessor.ts:164-204`）。网络抖动场景需外层包装。
- **Readability 提取失败的 fallback 行为**：如果 `extractContent=true` 但 Readability 抽不到，**默默** fallback 到全 HTML（`webContentProcessor.ts:220-223`），不告知 LLM，LLM 可能误以为"全 HTML 就是正文"。
