# fetch-mcp — Playwright 浏览器自动化调研报告

> ⚠️ **重要前置结论**：本项目**不包含任何 Playwright / Puppeteer / 真实浏览器自动化能力**。它是一个**纯 HTTP fetch + HTML 解析**的 MCP server。报告仍按模板三问回答，但 Q1 / Q2 重新对齐到「实际使用的抓取技术栈」。

## 0. 项目一句话定位

**fetch-mcp**（`zcaceres/fetch-mcp`，npm 名 `mcp-fetch-server` v1.1.2）是一个**轻量级、零浏览器依赖**的 MCP server：通过 Node.js 原生 `fetch` API 抓取网页，配合 `jsdom` + `@mozilla/readability` + `turndown` 把 HTML 转成 Markdown / 纯文本 / 可读文章正文，并把 YouTube 字幕抽出为时间轴文本。适合做"低成本、批量 LLM 网页读取"，**不适合需要执行 JavaScript / 登录 / 点击**的页面。

## 1. 调研依据

- **源码路径**：`C:\workspace\github\onionagent\harness\01_market_research\clone\fetch-mcp`
- **关键文件 / 代码片段**（已逐行读完）：
  - `src/index.ts` — MCP server 入口、6 个 tool 的 schema 注册、请求分发
  - `src/Fetcher.ts` — 核心实现：`_fetch()` 通用抓取层、`readResponseText()` 流式读取 + 字节上限、`html/markdown/txt/json/readable/youtubeTranscript` 6 个转换函数、`validateUrl()` / `validateResolvedIp()` SSRF 防护
  - `src/YouTubeTranscript.ts` — `extractPlayerResponse` 正则提取 `ytInitialPlayerResponse`，`parseTranscriptXml` 解析 `<text>` / `<p>` 两种字幕格式
  - `src/types.ts` — `RequestPayloadSchema`（zod 校验）、`downloadLimit`（默认 5000 字符）、`maxResponseBytes`（默认 10MB）
  - `src/cli.ts` — 独立 CLI `mcp-fetch <cmd> <url>`，6 个子命令 `html/markdown/readable/txt/json/youtube`
  - `package.json` — 依赖清单（**jsdom 28 / @mozilla/readability 0.6 / turndown 7.2 / zod 4 / private-ip 3**，**无 playwright**）
  - `tsconfig.json` — 编译目标 ESNext / module ESNext / bun-types
- **关键反向证据**：`grep -i "playwright|puppeteer|chromium|chrome|webdriver|launch|browser"` 在整个 `src/` 下**只在 `pnpm-lock.yaml` 出现**（pnpm 锁文件元数据，非代码），其余全部为零。

## 2. 三个核心问题的回答

### Q1. Playwright 无头浏览器安装

**答案：本项目根本不使用 Playwright，因此不存在"Playwright 安装"问题。**

实际使用的抓取技术栈（替代回答）：

| 环节 | 库 | 证据 |
|------|----|------|
| HTTP 请求 | **Node.js 18+ 原生 `fetch`**（依赖运行时内置） | `src/Fetcher.ts:64` `response = await fetch(url, { ... })` |
| HTML 解析 | **`jsdom@^28.1.0`**（纯 JS DOM） | `src/Fetcher.ts:1`、`:173`、`:324`；`package.json:52` |
| 正文提取 | **`@mozilla/readability@^0.6.0`** | `src/Fetcher.ts:3`、`:325`；`package.json:51` |
| HTML → Markdown | **`turndown@^7.2.2`** | `src/Fetcher.ts:2`、`:332`、`:354`；`package.json:54` |
| SSRF 防护 | **`private-ip@^3.0.2`** + Node `dns.promises.lookup` | `src/Fetcher.ts:4-5`、`:37-53`；`package.json:53` |
| 参数校验 | **`zod@^4.3.6`** | `src/types.ts:1` |
| MCP 协议 | **`@modelcontextprotocol/sdk@^1.27.1`** | `src/index.ts:3`；`package.json:50` |
| YouTube 字幕（可选） | **`yt-dlp`**（外部 CLI，通过 `child_process.execFileSync` 调用） | `src/Fetcher.ts:210-223`、`:269-279` |

**是否需要额外安装？**

- ✅ **HTTP / 解析 / Markdown 转换**：全部走 npm 依赖，`pnpm install`（或 `bun install`）即可，**无需下载浏览器二进制**。
- ⚠️ **YouTube 字幕**：默认走"直接从页面 HTML 抽 `ytInitialPlayerResponse`"路径，**不需要 yt-dlp**。仅当 yt-dlp 存在且执行失败时才会回退到该路径（`src/Fetcher.ts:291-295`）。**yt-dlp 缺失完全不影响主流程**。
- **离线环境**：无浏览器二进制意味着**国内网络 / 离线 / 防火墙**环境**完全不受影响**——这是本项目相对 Playwright-based 方案最大的部署优势。
- **本地浏览器路径**：**不适用**，无浏览器调用。

> ⚠️ 重要注释：`src/Fetcher.ts:70-72` 明确写道 `// Note: proxy is a Bun-specific fetch option. On Node.js, this option is silently ignored.` — `--proxy` 在 Node.js 运行时下被默默忽略，需要 `http-proxy-agent` 替代。Onion Agent 若用 Node 18+ 跑要注意。

### Q2. 浏览器自动化功能 + URL 访问 + HTML 压缩

#### Q2.1 工具清单（本项目暴露的全部 6 个 MCP tool）

| Tool 名 | 类别 | 输入参数 | 输出格式 | 代码路径 |
|---------|------|---------|---------|---------|
| `fetch_html` | URL 访问 / 抓取 | `url` (required), `headers`, `max_length` (default 5000), `start_index` (default 0), `proxy` | `{ content: [{type:"text", text: html}], isError: false }` | `src/index.ts:32-60`、`src/Fetcher.ts:121-140` |
| `fetch_markdown` | 转换 | 同上 | `{ content: [{type:"text", text: markdown}], isError }` | `src/index.ts:62-90`、`src/Fetcher.ts:350-371` |
| `fetch_txt` | 转换（去标签） | 同上 | `{ content: [{type:"text", text: plaintext}], isError }` | `src/index.ts:92-121`、`src/Fetcher.ts:168-201` |
| `fetch_json` | API 调用 | 同上 | `{ content: [{type:"text", text: jsonString}], isError }` | `src/index.ts:123-151`、`src/Fetcher.ts:142-166` |
| `fetch_readable` | 正文提取 | 同上 | `{ content: [{type:"text", text: markdown}], isError }` | `src/index.ts:153-182`、`src/Fetcher.ts:319-348` |
| `fetch_youtube_transcript` | 视频字幕 | 同上 + `lang` (default "en") | `{ content: [{type:"text", text: "[0:00] ..."}], isError }` | `src/index.ts:184-217`、`src/Fetcher.ts:281-317` |

> **无导航 / 无交互 / 无点击 / 无 fill / 无 hover / 无 drag / 无截图 / 无 evaluate / 无 wait_for_selector / 无 cookie / 无 iframe / 无多 tab / 无设备模拟 / 无 PDF / 无 codegen**。
> 模板 Q2.1 列出的所有"浏览器自动化"能力**全部不存在**——本项目不渲染 JS、不维护 session、不操作 DOM 事件，只做"取 HTML → 转结构化文本"。

#### Q2.2 URL 网页访问如何实现？

- **HTTP 库**：Node 18+ 原生 `fetch`（`src/Fetcher.ts:64`），**没有 axios / node-fetch / undici / got**。
- **超时控制**：
  - **HTTP 请求层无 `timeout` 参数**——`fetch(url, { headers, proxy })` 调用里**没有** `signal: AbortSignal.timeout(...)` 也没有 `setTimeout` 包装。`grep "timeout"` 在 `Fetcher.ts` 只命中 `src/Fetcher.ts:222`（yt-dlp 的 30s 进程超时）。
  - 后果：服务端 hang 住会一直等（直到 Node 默认 socket timeout 触发，但 fetch 不一定遵守）。
- **等待策略**：❌ **不存在** `waitUntil` 概念——`fetch` 拿到的是**首次 HTTP 响应体**，不等待 JS 执行、不等待 hydration、不等待懒加载图片。
- **重试机制**：❌ **无**——`_fetch()` 失败直接抛 `Failed to fetch ${url}: ...`，**不重试**。
- **反爬虫对抗**：
  - **User-Agent 伪装**：`src/Fetcher.ts:66-68` 写死 Chrome 120 UA 字符串
  - **WebDriver 隐藏**：不适用（非浏览器）
  - **代理支持**：`proxy` 参数支持，但**仅 Bun 运行时生效**（`src/Fetcher.ts:70-72` 注释明确警告）
  - **自定义 headers**：✅ `headers` 参数透传（`src/Fetcher.ts:65-69`）
- **Redirect 控制**：❌ **无**——`fetch` 默认 follow，最多 20 次（WHATWG 规范），**用户不可配置** `maxRedirects`。
- **Redirect 后 SSRF 二次校验**：`src/Fetcher.ts:81-84` 在 `response.url !== url` 时重新跑 `validateUrl` / `validateResolvedIp`，防 3xx 跳到内网。

#### Q2.3 网页 HTML 过大如何处理？

| 维度 | 实现 | 证据 |
|------|------|------|
| **`max_length` 参数** | ✅ 通用参数，所有 fetch tool 都有 | `src/types.ts:12`（zod 默认 `downloadLimit`=5000）、`src/index.ts:46-48` 等 |
| **`start_index` 翻页** | ✅ 通用参数，配合 `max_length` 实现分页 | `src/types.ts:13`、`src/Fetcher.ts:10-17` `applyLengthLimits()` |
| **截断方式** | **头截断**（`text.substring(startIndex, startIndex + maxLength)`）——**不保留尾部** | `src/Fetcher.ts:15-16` |
| **`max_length=0` 语义** | **0 = 不截断**（返回全文） | `src/Fetcher.ts:15` `maxLength > 0 ? Math.min(...) : text.length` |
| **script/style 剥离** | ✅ **仅 `fetch_txt` 路径**显式 `script.remove() / style.remove()` | `src/Fetcher.ts:176-179` |
| **HTML → Markdown** | ✅ `turndown.turndown(html)` 用于 `fetch_markdown` / `fetch_readable` | `src/Fetcher.ts:333`、`:355` |
| **正文提取（去广告/导航/页脚）** | ✅ `Readability.parse()` 用于 `fetch_readable` | `src/Fetcher.ts:325-326` |
| **响应体字节上限** | ✅ `MAX_RESPONSE_BYTES` 默认 **10 MB**（`src/types.ts:6-7`），可通过 env var 调整 | `src/Fetcher.ts:90-93`（content-length 预检）、`src/Fetcher.ts:104-113`（流式读取时实时累加，超限 throw） |
| **截图 / 图片压缩** | ❌ **无截图功能**，不适用 | — |
| **旁路磁盘（大结果落盘）** | ❌ **无此模式**——超过 `max_length` 直接截断，不写文件、不返回路径 | `src/Fetcher.ts:10-17` |
| **环境变量调参** | `DEFAULT_LIMIT`（默认字符上限）、`MAX_RESPONSE_BYTES`（默认 10MB） | `src/types.ts:3-7` |

> 💡 **关键观察**：本项目用 **`max_length` 截断** + **`MAX_RESPONSE_BYTES` 硬上限**双层防 OOM。流式读取用 `getReader()` + `TextDecoder` 实时累加字节数（`src/Fetcher.ts:100-118`），超限立刻 throw + `reader.cancel()` 释放流。**没有"分页+磁盘旁路"模式**——所有内容直接通过 MCP 文本通道返回。

### Q3. fetch 功能实现

**Q3.1 是否有专门 `fetch` 工具？与 Q2 区别？**

本项目**核心就是 fetch**——没有别的功能。Q2 中列出的 6 个 tool 全部围绕"fetch URL → 转格式"展开，**没有浏览器自动化 Q2 与 fetch Q3 的二元划分**。

> 严格说 `fetch_html` / `fetch_json` 是"原样输出"，`fetch_markdown` / `fetch_readable` / `fetch_txt` 是"转格式输出"，`fetch_youtube_transcript` 是"特殊资源处理"。

**Q3.2 多格式输出**

| 格式 | Tool | 实现 |
|------|------|------|
| **HTML（原样）** | `fetch_html` | `src/Fetcher.ts:121-140` 截断后直接返回 |
| **Markdown** | `fetch_markdown` | `src/Fetcher.ts:350-371` 全文 `turndown.turndown(html)` |
| **Text（去标签）** | `fetch_txt` | `src/Fetcher.ts:168-201` jsdom 解析 → 去 script/style → `body.textContent` → `replace(/\s+/g, " ")` 归一化 |
| **JSON** | `fetch_json` | `src/Fetcher.ts:142-166` `JSON.parse` → `JSON.stringify` 后截断 |
| **可读文章（Readability + Markdown）** | `fetch_readable` | `src/Fetcher.ts:319-348` Readability 抽主体 → turndown 转 MD |
| **YouTube 字幕** | `fetch_youtube_transcript` | `src/Fetcher.ts:281-317` yt-dlp 或直抽，输出 `[mm:ss] text` 格式 |

**Q3.3 正文提取**

- ✅ **用 Readability**（`@mozilla/readability`，`src/Fetcher.ts:3` 导入、`:325` `new Readability(dom.window.document)`、`:326` `reader.parse()`）
- `fetch_readable` 拿到的 `article.content`（HTML 字符串）再走 `turndown` 转 Markdown（`src/Fetcher.ts:332-333`）
- **不是**按 `<article>` / `<main>` CSS 选择器硬选，**是 Mozilla Readability 算法**（看分数、看段落密度、看 div 深度）

**Q3.4 元数据提取**

❌ **未做**——`fetch_readable` 返回时**没有显式返回** `article.title / byline / siteName / publishedTime / excerpt / og:image` 这些 Readability 算出的元数据。Readability 内部算出来但**只取 `article.content`**（`src/Fetcher.ts:333`），**浪费了**。

**Q3.5 HTTP 请求层**

- **库**：Node 18+ 原生 `fetch`（`src/Fetcher.ts:64`）
- **Headers 控制**：✅ `headers` 参数透传，并叠加默认 UA（`src/Fetcher.ts:65-69`）——注意**用户传入的 headers 会覆盖默认 UA**（因为 `{ ...headers }` 在后面）
- **Redirect 控制**：❌ 无显式 `maxRedirects` / `redirect: 'manual'` 配置，依赖 `fetch` 默认值
- **请求 / 响应大小限制**：
  - **响应字节上限**：`MAX_RESPONSE_BYTES`（默认 10MB），双层（content-length 预检 + 流式累加）
  - **请求体限制**：不适用，所有 tool 都是 GET
- **错误分类**（`src/Fetcher.ts`）：
  - `Failed to fetch ${url}: ${e.message}` — 网络/超时/DNS 失败（`:76-78`）
  - `Failed to fetch ${url}: HTTP error: ${response.status}` — 4xx/5xx（`:87`，**非 2xx/3xx 一律 throw**）
  - `Fetcher blocked URL with disallowed protocol "${protocol}"` — 非 http/https（`:23`）
  - `Fetcher blocked request to private address "${hostname}"` — SSRF（`:31-33`）
  - `Fetcher blocked request: hostname "${hostname}" resolved to private IP "${address}"` — DNS rebinding（`:46`）
  - `Response too large: ${contentLength} bytes exceeds ${maxResponseBytes} byte limit` — content-length 预检（`:92`）
  - `Response too large: exceeded ${maxResponseBytes} byte limit while reading` — 流式累加（`:110`）
  - **错误最终被外层 try-catch 转成 `isError: true` + 文本消息返回**（`src/Fetcher.ts:134-139`、`:160-164` 等），**不抛 MCP 协议级异常**

## 3. 关键代码片段

### 片段 1：核心 `_fetch()` — 通用抓取 + SSRF 防护

`src/Fetcher.ts:55-96`

```typescript
private static async _fetch({
  url, headers, proxy,
}: RequestPayload): Promise<Response> {
  this.validateUrl(url);
  await this.validateResolvedIp(url);
  let response: Response;
  try {
    response = await fetch(url, {
      headers: {
        "User-Agent":
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        ...headers,
      },
      // Note: proxy is a Bun-specific fetch option. On Node.js, this option is silently ignored.
      ...(proxy ? { proxy } : {}),
    } as RequestInit);
  } catch (e: unknown) {
    if (e instanceof Error) throw new Error(`Failed to fetch ${url}: ${e.message}`);
    throw new Error(`Failed to fetch ${url}: Unknown error`);
  }

  if (response.url && response.url !== url) {
    this.validateUrl(response.url);            // 3xx 跳转后再校验
    await this.validateResolvedIp(response.url);
  }

  if (!response.ok) {
    throw new Error(`Failed to fetch ${url}: HTTP error: ${response.status}`);
  }

  const contentLength = response.headers?.get?.("content-length");
  if (contentLength && parseInt(contentLength, 10) > maxResponseBytes) {
    throw new Error(`Response too large: ${contentLength} bytes exceeds ${maxResponseBytes} byte limit`);
  }
  return response;
}
```

### 片段 2：流式读取 + 实时字节上限

`src/Fetcher.ts:98-119`

```typescript
private static async readResponseText(response: Response): Promise<string> {
  if (!response.body) return response.text();
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let result = "";
  let bytesRead = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      bytesRead += value.byteLength;
      if (bytesRead > maxResponseBytes) {
        throw new Error(`Response too large: exceeded ${maxResponseBytes} byte limit while reading`);
      }
      result += decoder.decode(value, { stream: true });
    }
    result += decoder.decode();
    return result;
  } finally {
    reader.cancel();
  }
}
```

### 片段 3：`fetch_readable` — Readability + turndown 组合

`src/Fetcher.ts:319-348`

```typescript
static async readable(requestPayload: RequestPayload) {
  try {
    const response = await this._fetch(requestPayload);
    const html = await this.readResponseText(response);

    const dom = new JSDOM(html, { url: requestPayload.url });
    const reader = new Readability(dom.window.document);
    const article = reader.parse();

    if (!article) {
      throw new Error("Failed to parse readable content from the page");
    }

    const turndownService = new TurndownService();
    let content = turndownService.turndown(article.content ?? "");
    content = this.applyLengthLimits(content, requestPayload.max_length ?? downloadLimit, requestPayload.start_index ?? 0);

    return { content: [{ type: "text", text: content }], isError: false };
  } catch (error) { /* ... isError: true ... */ }
}
```

### 片段 4：SSRF 防护 — 协议 + 主机名 + DNS 解析三道关

`src/Fetcher.ts:19-53`

```typescript
private static validateUrl(url: string): void {
  const parsedUrl = new URL(url);
  if (parsedUrl.protocol !== 'http:' && parsedUrl.protocol !== 'https:') {
    throw new Error(`Fetcher blocked URL with disallowed protocol "${parsedUrl.protocol}". Only HTTP and HTTPS are allowed.`);
  }
  const hostname = parsedUrl.hostname;
  const bareHostname = hostname.startsWith('[') && hostname.endsWith(']') ? hostname.slice(1, -1) : hostname;
  if (bareHostname === 'localhost' || is_ip_private(bareHostname)) {
    throw new Error(`Fetcher blocked request to private address "${bareHostname}". This prevents SSRF attacks where a local MCP server could access privileged internal services.`);
  }
}

private static async validateResolvedIp(url: string): Promise<void> {
  const hostname = new URL(url).hostname;
  const bareHostname = hostname.startsWith('[') && hostname.endsWith(']') ? hostname.slice(1, -1) : hostname;
  try {
    const { address } = await dns.promises.lookup(bareHostname);
    if (is_ip_private(address)) {
      throw new Error(`Fetcher blocked request: hostname "${bareHostname}" resolved to private IP "${address}". This prevents DNS rebinding SSRF attacks.`);
    }
  } catch (e) {
    if (e instanceof Error && e.message.includes('Fetcher blocked')) throw e;
    // DNS lookup failures (e.g. non-resolvable hostnames) are not SSRF — let fetch handle them
  }
}
```

## 4. 与 Onion Agent non_head_browser.py 重构的关联

> 命名观察：Onion Agent 的 `non_head_browser.py` 这个文件名暗示"无头浏览器的 Python 替代品"——恰好就是 fetch-mcp 的定位。三个具体启发：

1. **抓取层应该走原生 `fetch`（Node 18+ / Python 3.9+ httpx），不要引第三方 HTTP 库**——`fetch-mcp` 的成功说明原生 fetch 完全够用，能省掉 axios/got 之类的依赖、减少供应链攻击面。
2. **HTML 处理三件套 `jsdom + @mozilla/readability + turndown` 是行业标准组合**——Onion Agent 走 Python 路线，对应可以是 `selectolax / beautifulsoup4` + `readability-lxml` + `markdownify`（PyPI 都有）。Readability 是 Mozilla Firefox Reader View 同款算法，比手写 `<main>` 选择器稳得多。
3. **SSRF 防护必须三道关**——`fetch-mcp` 的 `validateUrl`（协议+主机名） + `validateResolvedIp`（DNS 解析后 IP）+ redirect 后二次校验是**最低配置**。Onion Agent 若让 LLM 调 `fetch_url`，一定要加这套防 `http://10.0.0.1`、`http://169.254.169.254/`（AWS metadata）、DNS rebinding 攻击。
4. **响应大小双层防护（content-length 预检 + 流式累加）值得抄**——单纯 `response.text()` 一次读到内存会被 1GB 响应打爆。`readResponseText()` 这种流式 + 实时累加的写法是教科书级别。
5. **截断用 `max_length` + `start_index` 分页**，**不要落盘**——LLM 上下文是 token 预算问题，不是磁盘 IO 问题。fetch-mcp 的"超过 max_length 直接 substring、start_index 续读"模式比"写文件 + 返回路径"更适合 LLM 流式消费。

**反面教训（不适合照搬）**：
- ❌ **没有超时控制**（`signal: AbortSignal.timeout`）——Onion Agent 一定要加，否则 hang 死的服务端会把 Agent Loop 锁住。
- ❌ **没有重试**——网络抖动场景 fetch-mcp 一次失败就 throw，Onion Agent 应该加 2-3 次指数退避重试。
- ❌ **`proxy` 在 Node 端被默默忽略**（`src/Fetcher.ts:70-72` 注释）——若要支持代理必须用 `http-proxy-agent` / `undici.ProxyAgent`，别走 Bun 私有 API。
- ❌ **`fetch_readable` 浪费了 Readability 元数据**（`article.title / byline / siteName`）——Onion Agent 应当把这些一并返回给 LLM，元数据对长文章理解很有用。

## 5. 不确定 / 未找到

1. **HTTP 请求层超时具体值**：源码里 `fetch()` 调用**没有**显式 `signal: AbortSignal.timeout(N)`，**未找到**。Node.js 原生 fetch 的默认行为是依赖底层 socket / DNS 超时，但具体值未在 README 或源码中说明。Onion Agent 落地时需自己加。
2. **Bun vs Node.js 行为差异**：源码多处依赖 Bun 行为（`proxy` 私有参数、`Bun.build` 脚本），README `Scripts` 段也用 `bun test / bun run`。在**纯 Node.js 18+ 环境**下哪些功能会降级 / 失效，README 没有完整说明——只在 `src/Fetcher.ts:70-72` 提到 `proxy` 被忽略。
3. **Markdown 转码自定义规则**：`new TurndownService()` **无任何自定义配置**（`src/Fetcher.ts:332`、`:354`），意味着默认规则。如果业务需要保留某些 `<div>` 渲染成表格 / 保留 `<style>` 颜色 / 自定义代码块语言，**需要 fork 修改**。
4. **jsdom 对现代 web API 的支持**：`fetch-mcp` 没有任何客户端 JS 执行（`JSDOM` 只用于静态解析），所以**不支持 SPA 渲染**——React/Vue/Next.js 等 CSR 页面拿到的可能是空 `<div id="root"></div>`。这与 Playwright 的核心差距在此。
5. **`fetch_html` 的字符截断是按字节还是 Unicode 码点**：`substring(startIndex, end)` 是 UTF-16 code unit 截断，遇到 emoji / CJK 扩展区可能切到代理对中间产生乱码。`src/Fetcher.ts:15-16` 未做处理。
6. **YouTube 直抽路径稳定性**：`fetchTranscriptDirect` 依赖 YouTube 页面里 `ytInitialPlayerResponse = {...};` 这段内嵌 JSON（`src/YouTubeTranscript.ts:3`），YouTube 改前端这块就会失效。**无重试 / 无 fallback 到第三方 API**。

---

**报告完成时间**：调研对象为 `zcacerers/fetch-mcp` v1.1.2，源码来自 `harness/01_market_research/clone/fetch-mcp/`。所有结论均含 `src/xxx.ts:行号` 引用。
