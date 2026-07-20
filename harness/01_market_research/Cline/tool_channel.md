# Cline — 工具调用（Tool Channel）调研报告

## 0. 智能体一句话定位

Cline 是 `cline/cline` 仓库下的开源自主编码 Agent，提供 **SDK / VS Code 扩展 / JetBrains 插件 / CLI 四形态**，基于自家 `@cline/sdk` + Vercel AI SDK 兼容任意 OpenAI 协议模型（Q2/Q3 答案可能让用户意外 —— **Cline v3 已全面从 XML 工具协议迁移到 OpenAI JSON Schema function calling**，XML 协议只存在于旧版和其 fork Roo-Code）。

## 1. 调研依据

- 源码路径：`C:\workspace\github\onionagent\harness\01_market_research\clone\vscode\apps\vscode\src\`（VSCode 宿主）+ `cline\sdk\packages\core\src\extensions\tools\`（工具 SDK）+ `cline\sdk\packages\llms\src\providers\ai-sdk.ts`（大模型网关）
- 关键文件：
  - `cline\sdk\packages\core\src\extensions\tools\runtime.ts`（工具目录）
  - `cline\sdk\packages\core\src\extensions\tools\definitions.ts`（内置工具工厂）
  - `cline\sdk\packages\core\src\extensions\tools\schemas.ts`（Zod → JSON Schema）
  - `cline\sdk\packages\core\src\extensions\tools\executors\output-limits.ts`（输出截断）
  - `cline\sdk\packages\shared\src\tools\create.ts`（AgentTool 适配层）
  - `cline\sdk\packages\llms\src\providers\ai-sdk.ts`（streamText 网关，含 `repairMalformedToolCall`）
  - `cline\apps\vscode\src\services\mcp\McpHub.ts`（MCP 总线，stdio/SSE/streamableHttp 三种 transport）
  - `cline\apps\vscode\src\core\storage\skill-directories.ts`（Agent Skills 6 目录扫描）
  - `cline\apps\vscode\src\core\context\instructions\user-instructions\skills.ts`（SKILL.md 解析）
  - `cline\apps\vscode\src\core\storage\disk.ts`（MCP/Rules/Hooks/Skills 路径常量）
- 文档 / README 引用：
  - `cline\.cline\skills\publish-cli\SKILL.md`（实际 SKILL.md frontmatter 范本）
  - `cline\apps\vscode\src\sdk\sdk-api-handler.ts`（Provider 配置路由）

## 2. 五个核心问题的回答

### Q1. 工具来源

- **内置工具**（10 个，源码：`cline\sdk\packages\core\src\extensions\tools\runtime.ts:23-79`）：

  | tool id | 功能 | 源码位置 |
  |---------|------|---------|
  | `read_files` | 读文件，支持 `start_line`/`end_line` 行范围分页 | `definitions.ts:createReadFilesTool` |
  | `search_codebase` | regex 搜索代码 | `definitions.ts:createSearchTool` |
  | `run_commands` | shell 命令执行（heredoc 合并、超时控制） | `definitions.ts:createShellTool` |
  | `editor` | 受控文件编辑（create/replace/insert） | `definitions.ts:createEditorTool` |
  | `apply_patch` | patch 形式编辑（与 `editor` 互斥） | `executors/apply-patch.ts` |
  | `fetch_web_content` | URL 内容抓取 + LLM 分析 | `definitions.ts:createWebFetchTool` |
  | `skills` | 调用命名 Skill（`skill: "pdf"` / `skill: "ms-office-suite:pdf"`） | `definitions.ts:createSkillsTool` |
  | `ask_question` | 问用户 2-5 个选项澄清问题 | `definitions.ts:createAskQuestionTool` |
  | `spawn_agent` | 派生子 Agent（subagent-driven-development） | `team/spawn-agent-tool.ts` |
  | `submit_and_exit` | 提交最终结果并退出循环 | `definitions.ts:createSubmitAndExitTool` |
  | `teams` | 多 agent 协作套件（mailbox、mission、outcome） | `team/team-tools.ts` |

- **MCP 支持**：✅ 完全支持。配置位置：`cline_mcp_settings.json`（在 `cline\apps\vscode\src\core\storage\disk.ts:13` 定义为 `GlobalFileNames.mcpSettings`），支持三种 transport —— stdio / SSE / streamableHttp，完整支持 OAuth（`McpOAuthManager`），运行时通过 chokidar **热重载** MCP 服务（`McpHub.ts:watchMcpSettingsFile` + `lastConnectionFingerprint` 防止自循环重连）。原子写入用 `temp → fs.link → unlink` 三步（`disk.ts:getMcpSettingsFilePath:114-127`，EEXIST 安全）。
- **Agent Skills 支持**：✅ 完全支持（progressive disclosure SKILL.md 模式）。每个 Skill 是一个子目录，内含 `SKILL.md`，YAML frontmatter 至少需要 `name`（必须与目录名一致）和 `description`（`cline\apps\vscode\src\core\context\instructions\user-instructions\skills.ts:loadSkillMetadata:178-220`）。6 个扫描目录（`skill-directories.ts:SKILL_DIRECTORY_NAMES:3-8`）：

  | 类型 | 路径 |
  |------|------|
  | project | `<cwd>/.clinerules/skills` |
  | project | `<cwd>/.cline/skills` |
  | project | `<cwd>/.claude/skills`（与 Anthropic Agent Skills 互通） |
  | project | `<cwd>/.agents/skills` |
  | global | `~/.cline/skills` |
  | global | `~/.agents/skills` |

  优先级：`remote > disk-global > project`（`skills.ts:discoverSkills:240`），通过数组顺序 + 反向遍历实现 last-wins。
- **其他工具类型**：
  - **Hooks**（事件钩子）：`~/.clinerules/hooks/`，支持 `PreToolUse` / `PostToolUse` / `UserPromptSubmit` / `TaskStart` / `TaskResume` / `TaskComplete` / `TaskCancel` 7 类事件（`cline\apps\vscode\src\core\hooks\` 完整 fixture 集）
  - **Workflows**（Slash 命令）：`~/.clinerules/workflows/`
  - **Marketplace**（远端注册中心）：`cline\apps\vscode\src\core\controller\marketplace\` 8 个 handler，支持远端安装 MCP server + Skills
  - **Remote Config**（企业下发）：`cline_mcp_settings.json` 支持 `remoteConfigured: true` 标记，便于识别组织下发的 server

### Q2. 工具列表的生成、传递、格式

- **生成方式**：**启动时一次性构建 + 运行时热刷新**。Cline v3 的工具列表由 `BASE_TOOL_CATALOG`（`runtime.ts:23-79` 常量数组）声明；运行时通过 `getCoreAcpToolNames` / `getCoreBuiltinToolCatalog` / `resolveCoreSelectedToolIds` 三个函数按 `mode`（plan/act/yolo）、`providerId`、`modelId` 动态筛选（`runtime.ts:resolveToolRoutingConfig` + `presets.ts:ToolPresets`）。MCP 工具通过 `McpHub` 连接后**动态追加**，触发 `toolListChangeCallback` 通知 SDK 重启 session。
- **传递方式**：通过 Vercel AI SDK 的 `streamText({ tools, model, messages })`（`cline\sdk\packages\llms\src\providers\ai-sdk.ts:1212`）。Provider 在 Cline 内部被 SDK 抽象为 `GatewayStreamRequest` → `AiSdk` 内部转 OpenAI 协议 / Anthropic 协议，**Provider 无关**。
- **格式**：**JSON Schema（OpenAI function calling）** —— 不是 XML。证据：
  - 工具定义 schema：`cline\sdk\packages\shared\src\tools\create.ts:65-67` 强制 `inputSchema.type === "object"`，Zod 通过 `zodToJsonSchema` 转 JSON Schema（`definitions.ts:1-15` import）。
  - 工具调用流：`cline\sdk\packages\llms\src\providers\ai-sdk.tool-calls.test.ts:32-50` 展示了 OpenAI 标准的 `chat.completion.chunk` SSE 流格式 —— `delta.tool_calls: [{ index, id, type: "function", function: { name, arguments } }]`。

  **实际工具定义片段**（简化自 `ai-sdk.tool-calls.test.ts:30-44`）：
  ```json
  {
    "name": "run_commands",
    "description": "Run shell commands",
    "inputSchema": {
      "type": "object",
      "properties": {
        "commands": { "type": "array", "items": { "type": "string" } }
      },
      "required": ["commands"]
    }
  }
  ```
  **实际流式响应片段**（同文件 `sseToolCall:46-66`）：
  ```
  data: {"choices":[{"index":0,"delta":{"role":"assistant","tool_calls":[{"index":0,"id":"call_1","type":"function","function":{"name":"run_commands","arguments":""}}]}}]}
  data: {"choices":[{"index":0,"delta":{"tool_calls":[{"index":0,"function":{"arguments":"{\"commands\":"}}]}}]}
  data: {"choices":[{"index":0,"delta":{"tool_calls":[{"index":0,"function":{"arguments":" [\"ls\"]}"}}]}}]}
  data: {"choices":[{"index":0,"delta":{},"finish_reason":"tool_calls"}]}
  data: [DONE]
  ```

- **是否 prompt-as-tool**：❌ 否（这是与旧 Cline 的关键区别）。v3 完全采用 function calling 协议；description 中也不会把工具语法塞进 system prompt。
- **动态刷新**：✅ 是。MCP 工具通过 `McpHub.toolListChangeCallback`（`McpHub.ts:97-108`）通知 session 重建；内建工具通过 `resolveCoreSelectedToolIds` 实时按 `BuiltinToolAvailabilityContext` 解析。

### Q3. 工具调用指令的解析、错误修复、准确性

- **解析方式**：**流式 + 累积**。OpenAI 标准的 `delta.tool_calls[].function.arguments` 增量累积，`Vercel AI SDK` 内部维护 stream 状态机；Cline 的 `AgentModelEvent` 抽象层定义为 `tool-call-delta` 事件，metadata 含 `inputParseError`（`ai-sdk.tool-calls.test.ts:108-119`）。
- **错误修复机制**：`repairMalformedToolCall` 函数（`cline\sdk\packages\llms\src\providers\ai-sdk.ts:423-449`），**6 类修复**：
  1. **截断 JSON**：`{"files": [{"path": "/tmp/a.txt"}]`（缺右括号）→ 自动补全（`ai-sdk.tool-calls.test.ts:130-142` 验证）
  2. **单引号 JSON**：`{'commands': ['ls']}` → 自动转双引号（同文件 `148-160`）
  3. **未转义换行符**：multi-line string 自动 escape
  4. **空 input** / **已 valid JSON**：返回 null（让上层 AI SDK 走原始错误路径）
  5. **未知工具名**（`NoSuchToolError`）：返回 null，**不修复**（让 schema mismatch 路径处理）
  6. **类型不匹配**（如 string 传给 string[]）：不修复，把锅交给 executor 的 lenient union schema
- **准确性保证**：
  - **Zod 严格 schema 校验**：所有内置工具通过 `validateWithZod(Schema, input)` 在 executor 入口校验（`definitions.ts:createReadFilesTool` 等每个工厂函数都做）
  - **输入宽松 union**：`ReadFilesInputUnionSchema` 兼容 `file_path` / `filePath` / `paths` / `file_paths` 多种 alias（`schemas.ts:LooseReadFileRequestSchema:64-82`）
  - **强制 object top-level**：`createTool` 拒绝非 object 的 inputSchema（`cline\sdk\packages\shared\src\tools\create.ts:normalizeToolInputSchema:24-75` 在注册时 fail-loud）
  - **Plan-then-Act**：Cline 有 `mode: "plan" | "act"`（`runtime.ts:resolveContextMode:80-82`），plan 模式下只读 + ask_question，禁止写
- **重试机制**：每个工具默认 `retryable: true, maxRetries: 3, timeoutMs: 30_000`（`create.ts:140-143`），可逐工具覆盖。Skills/ask_question 强制 `retryable: false, maxRetries: 0`（`definitions.ts:createSkillsTool:678-680` + `createAskQuestionTool:722`），避免重复调用副作用。

### Q4. 工具执行结果回传

- **回传方式**：**Vercel AI SDK 抽象 + 标准化 message block**。SDK 网关把工具执行结果包成 `AgentMessage`（role 为 `tool` / `function`），下一轮 `messages` 中以 tool result 形式回传；具体由 AI SDK 内部按 provider 转 OpenAI `tool_call_id` 或 Anthropic `tool_use_id` 协议 —— **Cline 不自己写 tool-result 协议**。
- **格式**：**字符串**。每个工具 executor 返回 `string`（`definitions.ts:createSkillsTool:665-669` 签名 `Promise<string>`），由 AI SDK 标准化为下一个 message block。
- **通信协议**：**OpenAI 协议**（默认） + **Anthropic 协议**（自动判别）。Provider 通过 `toSdkProviderId` 路由（`sdk-api-handler.ts:62`），Cline 提供超过 25 个 provider（openai / anthropic / bedrock / vertex / openrouter / ollama / litellm / groq / baseten / vscodelm 等）。`isAnthropicCompatibleModel`（`ai-sdk.ts` 引用）判别 Anthropic 兼容。
- **大结果处理**：**head + tail 中间截断**。`truncateCommandOutput`（`cline\sdk\packages\core\src\extensions\tools\executors\output-limits.ts:25-41`）保留前 50% + 后 50%（按 char 计数），中间插入 `[... output truncated: N chars total. Refine the command (grep, head, tail) to view the elided middle ...]` 提示，**截断通知放在 head/tail 边缘**，以防 provider 端再次中间截断丢失提示。

  **输出限额常量**（同文件 `47-58`）：
  - `MAX_COMMAND_OUTPUT_CHARS = 48_000`
  - `MAX_READ_OUTPUT_CHARS = 48_000`
  - `MAX_SEARCH_OUTPUT_CHARS = 48_000`
  - `MAX_READ_LINES = 2_000`
  - `MAX_LINE_CHARS = 2_000`

  工具 description 会显式引用这些限额（`definitions.ts` 注释），让模型主动分页而不是撞墙重试。

### Q5. File Backend 是否为工具调用做了适配

- **工具配置目录/文件清单**（来自 `cline\apps\vscode\src\core\storage\disk.ts:11-34` + `skill-directories.ts:3-8`）：

  | 用途 | 路径 | 加载代码 |
  |------|------|---------|
  | **MCP server 注册** | `cline_mcp_settings.json`（settings dir 下） | `McpHub.ts:readAndValidateMcpSettingsFile`，chokidar 热重载 |
  | **全局 Agent Skills** | `~/.cline/skills/` | `skill-directories.ts:getClineSkillsDirectoryPath:23` |
  | **全局 Agent Skills** | `~/.agents/skills/` | `skill-directories.ts:getAgentSkillsDirectoryPath:27` |
  | **项目 Agent Skills** | `<cwd>/.clinerules/skills` | `skill-directories.ts:32` |
  | **项目 Agent Skills** | `<cwd>/.cline/skills` | 同上 |
  | **项目 Agent Skills** | `<cwd>/.claude/skills` | 同上（与 Anthropic Agent Skills 互通） |
  | **项目 Agent Skills** | `<cwd>/.agents/skills` | 同上 |
  | **Rules 规则** | `<cwd>/.clinerules` / `~/.clinerules` / `AGENTS.md` / `.cursorrules` / `.windsurfrules` | `cline-rules.ts` / `external-rules.ts` |
  | **Workflows** | `<cwd>/.clinerules/workflows` / `~/.clinerules/workflows` | `user-instructions/workflows.ts` |
  | **Hooks 事件脚本** | `<cwd>/.clinerules/hooks` / `~/.clinerules/hooks` | `cline\apps\vscode\src\core\hooks\` |

- **加载代码**（按事件）：
  - Skills 启动扫描：`skills.ts:discoverSkills:240`，每个 task 启动时按 cwd 扫描 6 个目录
  - MCP 启动 + 热重载：`McpHub.ts:initializeMcpServers` + `watchMcpSettingsFile`（用 fingerprint 防止自循环）
  - Rules 加载：`cline-rules.ts`（AGENTS.md 兼容）
  - Hooks 事件分发：`hooks/hook-factory.ts`（7 类事件）

- **全局 vs 项目级 vs 两者都有**：
  - **Skills：两者都有**（4 project + 2 global，按"remote > disk-global > project"优先级合并，last-wins）
  - **MCP：单点**（VSCode 端是 globalState，CLI 端是 settings dir，无项目级 mcp.json —— **与 Claude Code 双层 .mcp.json 不同**）
  - **Rules：两者都有**（`AGENTS.md` / `.clinerules` 在 cwd 向上扫到 `.git` 边界，user-level `~/.clinerules` 兜底）
  - **Hooks：两者都有**（项目级 + user-level）
  - **Workflows：两者都有**

- **与 `standard/file_backend.md` 的对照**：
  - ✅ §1.1 固定用户属主目录：`~/.cline/` 默认
  - ✅ §1.3 AGENTS.md 向上扫描：兼容 AGENTS.md / .cursorrules / .windsurfrules 多种命名
  - ✅ §1.4 secrets 独立 + 0o600：`StateManager.isSecretKey` 显式区分 secrets（`StateManager.ts:18-30`）
  - ✅ §2.1 平台原生默认：`os.homedir() + ".cline"` 跨平台
  - ✅ §3.8 Bootstrap 种子：Cline 无显式 seed，但 Marketplace + first-run 引导生成默认 MCP 空文件
  - ✅ §8.1 用户可改存储根：`CLINE_DIR` env（`vscode-rollout/standalone/runtime-files/` 中验证）
  - ✅ §8.3 atomic write：MCP settings 用 `temp → fs.link → unlink`（`disk.ts:114-127`）
  - ✅ §10.8 MCP 协议支持：McpHub 三 transport + OAuth
  - ⚠ §3.6 per-workspace hash 隔离：VSCode 端靠 `globalState` 自动 per-workspace，无显式 hash；CLI 端 `workspaces/<hash>/` 模式
  - ⚠ §3.4 强结构化：仅在 settings/ 目录下，不是整个 `~/.cline/`
  - ⚠ §2.5 per-project workspace：Cline **明确跟 cwd**（编程 Agent 默认行为），与 Onion Agent "不跟 cwd" 哲学相反

## 3. 关键代码片段

### 3.1 工具目录声明（`cline\sdk\packages\core\src\extensions\tools\runtime.ts:23-79`）

```typescript
const BASE_TOOL_CATALOG: readonly RuntimeToolCatalogEntry[] = [
    { id: "read_files", description: "Read the content of text or image files...",
      headlessToolNames: ["read_files"] },
    { id: "search_codebase", description: "Perform regex pattern searches...",
      headlessToolNames: ["search_codebase"] },
    { id: "run_commands", description: "Run shell commands from the root of the workspace...",
      headlessToolNames: ["run_commands"] },
    { id: "editor", description: "Make controlled filesystem edits...",
      headlessToolNames: ["editor"] },
    { id: "fetch_web_content", description: "Fetch URL content and analyze it with a prompt...",
      headlessToolNames: ["fetch_web_content"] },
    { id: "skills", description: "Execute a configured skill within the main conversation...",
      headlessToolNames: ["skills"] },
    { id: "ask_question", description: "Ask the user a single clarifying question...",
      headlessToolNames: ["ask_question"] },
    { id: "spawn_agent", description: createSpawnAgentTool({ configProvider: {} as never }).description,
      headlessToolNames: ["spawn_agent"] },
    { id: "teams", description: "Enable team collaboration tools...",
      headlessToolNames: [...TEAM_TOOL_NAMES] },
] as const;
```

### 3.2 Zod → JSON Schema + AgentTool 工厂（`cline\sdk\packages\core\src\extensions\tools\definitions.ts:6-19`）

```typescript
import { type AgentTool, type AgentToolContext, createTool,
         validateWithZod, zodToJsonSchema } from "@cline/shared";

export function createReadFilesTool(
    executor: FileReadExecutor,
    config: Pick<DefaultToolsConfig, "readFilesTimeoutMs"> = {},
): AgentTool<ReadFilesInput, string> {
    const timeoutMs = config.readFilesTimeoutMs ?? 15_000;
    return createTool<ReadFilesInput, string>({
        name: "read_files",
        description: "Read text/image files; support line ranges...",
        inputSchema: zodToJsonSchema(ReadFilesInputUnionSchema),  // 兼容多种 alias
        timeoutMs,
        retryable: true,
        maxRetries: 3,
        execute: async (input, ctx) => {
            const validated = validateWithZod(ReadFilesInputSchema, input);
            return withTimeout(executor(validated, ctx), timeoutMs, ...);
        },
    });
}
```

### 3.3 Tool Call 修复（`cline\sdk\packages\llms\src\providers\ai-sdk.ts:423-449`）

```typescript
export async function repairMalformedToolCall<T extends RepairableToolCall>({
    toolCall, error,
}: { toolCall: T; error: unknown }): Promise<T | null> {
    if (NoSuchToolError.isInstance(error)) return null;        // 未知工具 → 不修
    if (typeof toolCall.input !== "string" || !toolCall.input.trim()) return null;
    try { JSON.parse(toolCall.input); return null; }           // valid JSON → 留给 executor
    catch { /* fall through to repair */ }
    const repaired = parseJsonStream(toolCall.input);          // 截断/单引号/换行修复
    if (repaired === toolCall.input || typeof repaired === "string") return null;
    return { ...toolCall, input: JSON.stringify(repaired) };
}
```

### 3.4 Skills 6 目录扫描（`cline\apps\vscode\src\core\storage\skill-directories.ts:1-43`）

```typescript
const SKILL_DIRECTORY_NAMES = {
    clineruleSkillsDir: ".clinerules/skills",
    clineSkillsDir:     ".cline/skills",
    claudeSkillsDir:    ".claude/skills",     // 与 Anthropic Agent Skills 互通
    agentsSkillsDir:    ".agents/skills",
} as const;

export function getSkillsDirectoriesForScan(cwd: string): SkillsScanDirectory[] {
    return [
        { path: path.join(cwd, SKILL_DIRECTORY_NAMES.clineruleSkillsDir), source: "project" },
        { path: path.join(cwd, SKILL_DIRECTORY_NAMES.clineSkillsDir),     source: "project" },
        { path: path.join(cwd, SKILL_DIRECTORY_NAMES.claudeSkillsDir),    source: "project" },
        { path: path.join(cwd, SKILL_DIRECTORY_NAMES.agentsSkillsDir),    source: "project" },
        { path: getClineSkillsDirectoryPath(),   source: "global" },      // ~/.cline/skills
        { path: getAgentSkillsDirectoryPath(),   source: "global" },      // ~/.agents/skills
    ];
}
```

### 3.5 MCP 原子写（`cline\apps\vscode\src\core\storage\disk.ts:114-127`）

```typescript
export async function getMcpSettingsFilePath(settingsDirectoryPath: string): Promise<string> {
    const mcpSettingsFilePath = path.join(settingsDirectoryPath, GlobalFileNames.mcpSettings);
    const tempPath = `${mcpSettingsFilePath}.tmp.${process.pid}.${Date.now()}.${Math.random().toString(36).slice(2)}`;
    try {
        await fs.writeFile(tempPath, JSON.stringify({ mcpServers: {} }, null, 2), { encoding: "utf8", flag: "wx" });
        await fs.link(tempPath, mcpSettingsFilePath);   // hard-link 原子发布，EEXIST 安全
    } catch (error) {
        if ((error as NodeFS.ErrnoException).code !== "EEXIST") throw error;
    } finally {
        await fs.unlink(tempPath).catch(() => {});
    }
    return mcpSettingsFilePath;
}
```

## 4. 与 Onion Agent 设计的关联

1. **Onion 可以学 Cline 的 `createTool` 工厂 + Zod → JSON Schema 模式**（`create.ts`）—— Onion 计划 L5 层的 `buildin_client.py` 可以直接用 Pydantic v2 替代 Zod，Pydantic v2 的 `model_json_schema()` 与 `zodToJsonSchema` 输出等价，省去手写 JSON Schema 的维护成本。
2. **Onion **不要学** Cline v3 完全抛弃 XML** —— 旧 Cline 的 XML 工具协议在弱模型（如 DeepSeek、Qwen2.5）上比 function calling 更稳健；Onion 可以做 **XML + JSON Schema 双协议**（按模型 capability 自动切换），覆盖 2026 年国产模型生态（参考 §5 不确定项 2）。
3. **Onion 应该学 Cline 的 `repairMalformedToolCall` 设计**（`ai-sdk.ts:423-449`）—— 6 类修复策略（截断/单引号/换行/空/已 valid/未知工具名）覆盖了国产模型最常见的 tool call 出错场景；Onion 的 `tool_shell/buildin_client.py` 应当内置等价的 `json_repair` pass。
4. **Onion 应当参考 Cline 的输出限额 + head/tail 截断**（`output-limits.ts`）—— 48K char cap + 保留 head/tail 边缘提示，避免 provider 端二次截断丢失修复引导；Onion 的 session.json 压缩器应保留 32K~48K 范围。
5. **Onion **不要学** Cline 单一全局 MCP 配置**（无项目级 `.mcp.json`）—— Onion 标准 §10.8 明确要求"用户级 `~/.onion/mcp.json` + 项目级 `<repo>/.onion/mcp.json` 双层"，Cline 这里是个反例；CLI 多 workspace 场景下单一 mcp.json 会导致跨项目污染。
6. **Onion 应当学 Cline 的 fingerprint 防自循环**（`McpHub.ts:lastConnectionFingerprint`）—— MCP 热重载时如不在自己写入时记录 fingerprint，会陷入 "write → watcher → reconnect → write" 死循环；Onion 的 MCP 客户端必须实现等价机制。
7. **Onion 应当学 Cline 的 hooks 事件系统**（`cline\apps\vscode\src\core\hooks\`）—— 7 类事件（PreToolUse/PostToolUse/UserPromptSubmit/TaskStart/TaskResume/TaskComplete/TaskCancel）覆盖了 Agent Loop 的关键节点，Onion 在 P1 阶段可借鉴。

## 5. 不确定 / 未找到

1. **XML 工具协议的现状**：源码未找到 `parseAssistantMessage` 之类的 XML 解析器（`grep -r "parseAssistantMessage" cline/` 无结果）。**结论**：Cline v3 已完全迁移到 OpenAI function calling，XML 协议只存在于旧 Cline（pre-v3）和它的 fork Roo-Code。`cline/Roo-Code/src/core/assistant-message/presentAssistantMessage.ts` 仍保留 XML 解析器（819 行），但已不属于 Cline 主仓。
2. **`<cwd>/.mcp.json` 项目级 MCP 配置**：源码未找到 —— Cline 只有全局 `cline_mcp_settings.json`，无项目级 `.mcp.json`，与 Claude Code / Codex 的双层 mcp 设计不同。若 Onion 要"项目级 mcp.json"必须自己实现。
3. **流的 token-level 增量解析细节**：Vercel AI SDK 内部用 `streamText` 抽象，Cline 在 `ai-sdk.ts:1212` 调用，没自己写 delta 解析器。Onion 若要更细粒度控制（如 Anthropic 思考预算），需要绕过 AI SDK 直接走 OpenAI / Anthropic SDK。
4. **Skills 的"渐进式披露"完整度**：Cline 实现了 SKILL.md 解析（YAML frontmatter 必填 `name`+`description`），但 description 会被附加到 `skills` 工具的 description 中（`definitions.ts:createSkillsTool:688-700` 动态 getter），**没有实现 Anthropic Agent Skills 那种"按需 SKILL.md 全量加载"**（即模型看到的是 skill name + short desc，全量 markdown 在执行时才塞进 context）。Onion P2 阶段可考虑补齐这个差距。
5. **Provider 无关的抽象层**：Cline 通过自研 `@cline/llms` + Vercel AI SDK 实现 25+ provider 兼容，但 source 路径较深（`cline\sdk\packages\llms\src\providers\`），完整 provider 列表未在本次调研内逐个核验；Onion 若要同样 25+ provider，需要投入约 5-10 人天做抽象层。
