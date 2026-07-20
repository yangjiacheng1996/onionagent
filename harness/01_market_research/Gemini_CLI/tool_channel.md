# Gemini CLI — 工具调用（Tool Channel）调研报告

> 调研对象:`google-gemini/gemini-cli`(v0.52.0-nightly.20260715)
> 调研维度:**Tool Channel** — 工具的来源、协议、解析、回传、文件层适配
> 调研路径:`C:\workspace\github\onionagent\harness\01_market_research\clone\gemini-cli`
> 配合阅读:`Gemini_CLI/file_backend.md`(本目录) + `standard/file_backend.md`

---

## 0. 智能体一句话定位

Google 官方终端 Agent;`gemini` 二进制 + 互动 TUI;基于 Gemini 3 / Gemini 2.5 系列,1M 上下文,免费档 60 req/min + 1000 req/day,**内置 Google Search / 文件 / Shell / Web Fetch 工具 + MCP + Agent Skills(渐进披露 SKILL.md)+ Extension 全套**。

---

## 1. 调研依据

### 1.1 关键源码定位

| 主题 | 关键文件 |
|---|---|
| 工具定义 / schema / 解析 | `packages/core/src/tools/tools.ts`、`packages/core/src/tools/tool-registry.ts` |
| 工具名常量(枚举式) | `packages/core/src/tools/tool-names.ts`、`packages/core/src/tools/definitions/coreTools.ts` |
| MCP 工具实现 | `packages/core/src/tools/mcp-tool.ts` |
| MCP 客户端管理 | `packages/core/src/tools/mcp-client-manager.ts` |
| MCP 客户端 + transport | `packages/core/src/tools/mcp-client.ts` |
| Skills 加载 / 内置 / 优先级 | `packages/core/src/skills/skillManager.ts`、`skillLoader.ts` |
| Activate Skill tool | `packages/core/src/tools/activate-skill.ts` |
| Memory tool | `packages/core/src/tools/memoryTool.ts` |
| **流式 tool-call 解析** | `packages/core/src/core/geminiChat.ts`(processStreamResponse) |
| **Turn → 事件 yield** | `packages/core/src/core/turn.ts`(handlePendingFunctionCall) |
| **tool 列表 → Gemini API** | `packages/core/src/core/client.ts`(setTools / startChat) |
| 重试 / 退避 | `packages/core/src/utils/retry.ts` |
| 工具结果回传 + 录制 | `packages/core/src/services/chatRecordingService.ts` |
| 大结果截断 | `packages/core/src/tools/shell.ts`(LIVE_OUTPUT_MAX_BUFFER_CHARS) |

### 1.2 文档引用

- `README.md` — 项目入口、Quickstart、MCP / Skills / Extension 三件套
- `GEMINI.md` — 仓库自身 context file(被 LLM 加载)
- `docs/` — Skills / MCP / Hooks / Tools 各自的指南

---

## 2. 五个核心问题的回答

### Q1. 工具来源(内置 / MCP / Skills / 其他)

#### 1.1 内置工具清单(`packages/core/src/tools/tool-names.ts:113-145` `ALL_BUILTIN_TOOL_NAMES`)

| 工具名 | Display | 类别 | 用途 |
|---|---|---|---|
| `read_file` | ReadFile | Read | 单文件读取(支持行号范围) |
| `read_many_files` | ReadManyFiles | Read | 批量读,glob 模式 |
| `write_file` | WriteFile | Edit | 创建/覆盖写 |
| `edit` | Edit | Edit | 字符串替换(支持 `replace_globally`) |
| `glob` | FindFiles | Search | glob 模式找文件 |
| `grep` | SearchText | Search | ripgrep 包装(支持上下文/范围) |
| `ls` | ReadFolder | Search | 目录列表 |
| `shell` | Shell | Execute | 本地命令执行,**支持 background 模式**(`shellBackgroundTools.ts`) |
| `web_search` | GoogleSearch | Fetch | **Google Search grounding**(原生 Gemini 工具,无 schema) |
| `web_fetch` | WebFetch | Fetch | 网页抓取 + LLM 总结 prompt |
| `write_todos` | (internal) | Think | 任务分解 / 状态跟踪 |
| `ask_user` | AskUser | Communicate | 多选题(支持 single/multi-select) |
| `activate_skill` | ActivateSkill | Other | **激活 Agent Skill**(详见 §1.3) |
| `get_internal_docs` | GetDocs | Other | 读 CLI 自身文档 |
| `enter_plan_mode` / `exit_plan_mode` | PlanMode | SwitchMode | Plan/Act 切换 |
| `update_topic` | UpdateTopic | Other | 主题更新叙述 |
| `complete_task` | CompleteTask | Other | 任务完成标记 |
| `tracker_create_task` 等 6 个 | Tracker | Other | 任务图/依赖管理 |
| `read_mcp_resource` / `list_mcp_resources` | MCPResource | Fetch | MCP 资源 |

**证据**:`tool-names.ts:113-145` 数组 + `definitions/coreTools.ts:32-52` 的 `DEFAULT_LEGACY_SET` / `GEMINI_3_SET` 两套 schema(模型族切换)。

#### 1.2 MCP 支持(**是**,MCP 是其"一等公民")

| 配置位置 | 代码位置 | 作用 |
|---|---|---|
| `settings.json` `mcpServers: { [name]: { command, args, env, httpUrl, ... } }` | `config.ts:2451 getMcpServers()` | 用户级 / 项目级 / 系统级 |
| `extensions/<name>/gemini-extension.json` `mcpServers: {...}` | `config/config.ts` Extension 解析 | 扩展自带 MCP server |
| `~/.gemini/mcp-oauth-tokens.json` | `storage.ts:57` | MCP OAuth 凭据 |
| `~/.gemini/extensions/installs.json` | `extensions/storage.ts` | 扩展安装元数据 |
| `.gemini/.mcp-config-cache` | `mcp-client-manager.ts:441 getClientKey()` | 客户端 hash(基于 name+config sha256) |

**evidence**:
- `mcp-client.ts:231-280 discoverInto()` 调 `client.listTools()` 后 for-loop `registries.toolRegistry.registerTool(tool)`,把 MCP 工具注入 ToolRegistry
- `mcp-client.ts:1435-1487 callTool()` 把 `McpClient.callTool` 包装成 `Part[]` 返回
- `mcp-client-manager.ts:266-364` 管理多 server 生命周期(connect / disconnect / restart),`scheduleMcpContextRefresh()` 调度刷新

#### 1.3 Agent Skills 支持(**是**,渐进披露 SKILL.md)

**evidence**(`skillManager.ts:50-104`、`skillLoader.ts:138-200`):

```typescript
// skillManager.ts:50-104
async discoverSkills(storage, extensions, isTrusted) {
  this.clearSkills();
  // 1. Built-in skills (lowest precedence)
  await this.discoverBuiltinSkills();
  // 2. Extension skills
  for (const extension of extensions) {
    if (extension.isActive && extension.skills) {
      this.addSkillsWithPrecedence(extension.skills);
    }
  }
  // 3. User skills (~/.gemini/skills/<name>/SKILL.md)
  this.addSkillsWithPrecedence(await loadSkillsFromDir(Storage.getUserSkillsDir()));
  // 3.1 User agent skills alias (~/.agents/skills)
  this.addSkillsWithPrecedence(await loadSkillsFromDir(Storage.getUserAgentSkillsDir()));
  // 4. Workspace skills (highest precedence, requires trust)
  if (!isTrusted) return;
  this.addSkillsWithPrecedence(await loadSkillsFromDir(storage.getProjectSkillsDir()));
  this.addSkillsWithPrecedence(await loadSkillsFromDir(storage.getProjectAgentSkillsDir()));
}
```

**Skill 目录**:
- 内置:`packages/core/src/skills/builtin/<name>/SKILL.md`(`skillManager.ts:107-117`,e.g. `antigravity/`、`skill-creator/`)
- 用户:`~/.gemini/skills/<name>/SKILL.md`(或别名 `~/.agents/skills/`)
- 项目 `<cwd>/.gemini/skills/<name>/SKILL.md`(或别名 `<cwd>/.agents/skills/`)
- 扩展 `extensions/<name>/skills/<name>/SKILL.md`

**Skill 格式**(`skillLoader.ts:18-20`、`loadSkillFromFile:191-217`):
- YAML frontmatter + Markdown body(必须含 `name` + `description`)
- 注册时**只存 name + description + location**,**body 在 `activate_skill` 工具被调用时才注入到 LLM context**

**Activate Skill tool**(`tools/activate-skill.ts`):LLM 只能看到 `name` + `description` 摘要(几十个 token),被 LLM 选中后才 `getSkill(name).body` 全文加载。**这是 Gemini CLI 真正的"渐进披露"机制**。

#### 1.4 其他工具类型

- **DiscoveredTool**(`tool-registry.ts:51-105`):用户配置 `toolDiscoveryCommand` + `toolCallCommand` 后,运行 discovery 命令得到 JSON 数组,每个 item 包装为 `DiscoveredTool`(名字加 `discovered_tool_` 前缀)
- **Codebase Investigator**(`agents/codebase-investigator.ts`):子 agent 形式的 tool(可 spawn subagent)
- **CLI Help Agent**(`agents/cli-help-agent.ts`):问 CLI 自身用法的 subagent tool
- **Generalist Agent**(`agents/generalist-agent.ts`):通用 subagent tool
- **Extension tools**(`mcp-client-manager.ts:280-300`):扩展可自带 `commands/`, `hooks/`, `agents/`, `skills/`, `policies/`

---

### Q2. 工具列表的生成、传递、格式

#### 2.1 生成:集中式 `ToolRegistry`(`tool-registry.ts:206-280`)

- `ToolRegistry` 是一个 `Map<string, AnyDeclarativeTool>`
- 注册入口:内置 tool 在 `Config` 构造时 `registerTool()`,MCP 工具在 `McpClient.discoverInto()` 时 `registerTool()`
- `getFunctionDeclarations(modelId?: string): FunctionDeclaration[]` 返回**所有 active tool** 的 `FunctionDeclaration`(Gemini API 的 schema 类型)
- 工具名规范(`tool-names.ts:236-294 isValidToolName`):
  - 内置:`read_file` 等原名
  - Discovered:`discovered_tool_<name>`
  - MCP:`mcp_<serverName>_<toolName>`(强制前缀 `mcp_`,最长 64 字符,中间 `...` 截断)

**关键代码**(`tool-registry.ts:647-707`):
```typescript
getFunctionDeclarations(modelId?: string): FunctionDeclaration[] {
  const isPlanMode = this.config.getApprovalMode() === ApprovalMode.PLAN;
  const declarations: FunctionDeclaration[] = [];
  const seenNames = new Set<string>();
  // ...遍历 getActiveTools(),每个 tool 调 tool.getSchema(modelId)
}
```

**`getSchema` 实现**(`tools.ts:387-394`、`BaseDeclarativeTool`):
```typescript
getSchema(_modelId?: string): FunctionDeclaration {
  return {
    name: this.name,
    description: this.description,
    parametersJsonSchema: this.addWaitForPreviousParameter(this.parameterSchema),
  };
}
```

#### 2.2 传递给 LLM:Google `@google/genai` SDK 的 `Tool` 类型

**evidence**(`client.ts:307-317`):
```typescript
async setTools(modelId?: string): Promise<void> {
  // ...
  const toolRegistry = this.context.toolRegistry;
  const toolDeclarations = toolRegistry.getFunctionDeclarations(modelId);
  const tools: Tool[] = [{ functionDeclarations: toolDeclarations }];
  this.getChat().setTools(tools);
}
```

**协议 = Google genai(非 OpenAI、非 Anthropic)**。`tools: [{ functionDeclarations: [FunctionDeclaration, ...] }]` 数组结构(顶层包 `functionDeclarations` 数组,每个 declaration 是 `{ name, description, parametersJsonSchema }`)。

#### 2.3 实际 JSON 片段(简化)

```json
{
  "tools": [{
    "functionDeclarations": [
      {
        "name": "read_file",
        "description": "Reads and returns the content of a specified file...",
        "parametersJsonSchema": {
          "type": "object",
          "properties": {
            "absolute_path": { "type": "string", "description": "..." },
            "start_line":   { "type": "integer", "description": "..." },
            "end_line":     { "type": "integer", "description": "..." },
            "wait_for_previous": { "type": "boolean", "description": "..." }
          },
          "required": ["absolute_path"]
        }
      },
      {
        "name": "shell",
        "description": "Runs a shell command...",
        "parametersJsonSchema": {
          "type": "object",
          "properties": {
            "command":     { "type": "string" },
            "is_background": { "type": "boolean" },
            "wait_for_previous": { "type": "boolean" }
          },
          "required": ["command"]
        }
      },
      {
        "name": "mcp_github_create_issue",
        "description": "Create a GitHub issue (from github MCP Server)",
        "parametersJsonSchema": { "type": "object", "properties": { ... } }
      },
      {
        "name": "activate_skill",
        "description": "Activates a skill by name. Skills are pre-defined...",
        "parametersJsonSchema": {
          "type": "object",
          "properties": {
            "name": { "type": "string", "description": "The name of the skill to activate" },
            "wait_for_previous": { "type": "boolean" }
          },
          "required": ["name"]
        }
      }
    ]
  }]
}
```

> 注释:每个 schema 都会**自动注入 `wait_for_previous: boolean`**(`tools.ts:405-426 addWaitForPreviousParameter`),让 LLM 显式控制并行/串行。

#### 2.4 是否 prompt-as-tool:**否**,纯 function calling

- System prompt 只描述身份 + 行为约束,不放工具描述
- 工具描述全在 schema.description 里
- **不学 Cline 的 XML 协议**

#### 2.5 动态刷新:**是**

`config.ts:2542-2548 refreshMcpContext()`:
```typescript
async refreshMcpContext(): Promise<void> {
  await this.memoryContextManager?.refresh();
  if (this._geminiClient?.isInitialized()) {
    await this._geminiClient.setTools();    // ← 重新调 getFunctionDeclarations
    this._geminiClient.updateSystemInstruction();
  }
}
```

- 触发点 1:`McpClientManager.scheduleMcpContextRefresh()`(`mcp-client-manager.ts:711-757`),MCP server listChanged / extension 安装/卸载时
- 触发点 2:`restart()` / `restartServer()` 后
- 触发点 3:信任目录变更时

---

### Q3. 工具调用指令的解析、错误修复、准确性

#### 3.1 流式解析(关键代码 `geminiChat.ts:1118-1180 processStreamResponse`)

```typescript
// geminiChat.ts:1118-1180(节选)
const finalFunctionCallsMap = new Map<string, FunctionCall>();
const legacyFunctionCalls: FunctionCall[] = [];
const callIndexToId = new Map<number, string>();
let runningFunctionCallCounter = 0;

for await (const chunk of streamResponse) {
  if (chunk.functionCalls && chunk.functionCalls.length > 0) {
    if (this.context.config.isContextManagementEnabled()) {
      // 新协议:用 id 去重合并,支持流式跨 chunk 补全
      for (let i = 0; i < chunk.functionCalls.length; i++) {
        const fnCall = chunk.functionCalls[i];
        const globalIndex = currentChunkStartCounter + i;
        if (!fnCall.id) {
          let id = callIndexToId.get(globalIndex);
          if (!id) {
            id = `synth_${this.context.promptId}_${Date.now()}_${this.callCounter++}`;
            callIndexToId.set(globalIndex, id);
          }
          fnCall.id = id;
        }
        const name = fnCall.name?.trim() || 'generic_tool';
        if (fnCall.id && !fnCall.id.startsWith(`${name}__`)) {
          fnCall.id = `${name}__${fnCall.id}`;        // 名字前缀化,防 id 冲突
        }
        finalFunctionCallsMap.set(fnCall.id, fnCall);  // ← Map 按 id 去重,保留最新版本
      }
      runningFunctionCallCounter += chunk.functionCalls.length;
    } else {
      // 老协议:直接 push 列表
      for (const fnCall of chunk.functionCalls) {
        const name = fnCall.name?.trim() || 'generic_tool';
        if (fnCall.id && !fnCall.id.startsWith(`${name}__`)) {
          fnCall.id = `${name}__${fnCall.id}`;
        }
      }
      legacyFunctionCalls.push(...chunk.functionCalls);
    }
  }
  // ...
}
```

**关键点**:
- **不是 OpenAI 风格的 `delta.tool_calls` 数组增量**,而是 Google genai SDK **直接给 `chunk.functionCalls` 完整数组**(SDK 内部已合并)
- 用 `Map<id, FunctionCall>` 跨 chunk 去重,保证 id 稳定
- **工具 id 格式**:`<name>__<id>`(双下划线分隔),其中 `<id>` 是 `synth_<promptId>_<ts>_<counter>` 或上游给的真实 id
- `turn.ts:422-465 handlePendingFunctionCall` 把 FunctionCall 包装成 `ToolCallRequestInfo` 抛给 scheduler

#### 3.2 错误修复

- **Schema 校验**:`BaseDeclarativeTool.validateToolParams`(`tools.ts:432-456`)调 `SchemaValidator.validate(schema, params)`(Ajv-based)。失败抛 `Invalid parameters provided. Reason: ...` 错误
- **静默 build**:`tools.ts:464-492 silentBuild` 不抛错,把 Error 装回 invocation。`validateBuildAndExecute`(`tools.ts:497-524`) 兜底把错误结构化成 `ToolResult.llmContent: "Error: ..."` 回传给 LLM,LLM 看到错误可自行 retry
- **MCP 错误**(`mcp-tool.ts:267-295 isMCPToolError`):检查 `response.isError` 字段,识别 MCP spec-compliant 错误,转成 `ToolErrorType.MCP_TOOL_ERROR` 回传
- **Abort**:`execute` 接受 `AbortSignal`,MCP 工具 race promise with abort(`mcp-tool.ts:303-322`)

#### 3.3 准确性保证

- `ToolCallRequestInfo` 在抛给 scheduler 前先 `tool.build(args)` 一次,失败 throw → 错误不抛给 LLM 而是本地 `discard` 但记录日志
- **plan-then-act**:Plan Mode 下 `getFunctionDeclarations` 会改写 write_file/edit 的 description 加 `ONLY FOR PLANS: ...` 后缀(`tool-registry.ts:689-700`)
- **allowlist 防误调**:`DiscoveredMCPToolInvocation.allowlist`(`mcp-tool.ts:107`)用户可"永久允许"某个 server / tool
- **policy engine + hook system**:`packages/core/src/scheduler/policy.ts` + `packages/core/src/hooks/` 在执行前/后/中可插 12 种 hook 事件

#### 3.4 重试上限

- `DEFAULT_MAX_ATTEMPTS = 10`(`retry.ts:29`)
- **mid-stream API 错误硬限 3 次 retry / 4 attempts**(`geminiChat.ts:591-605`)
- 网络错误 / 429 / 401:由 `shouldRetryOnError` 决定,默认 retryable
- **Content retry**:`shouldRetryOnContent` 触发 429/5xx 整个 turn 重新打
- **工具结果 error 不触发 retry**,而是把 error 回传给 LLM 让它理解后重发

---

### Q4. 工具执行结果回传

#### 4.1 回传格式:**Gemini 协议 `functionResponse` Part**(`geminiChat.ts`)

**不是** OpenAI 的 `{role: "tool", tool_call_id: ..., content: ...}` 风格(那需要 role 切到 `tool`);
**是** Google genai 的 `user` role message 包含一个 `Part.functionResponse = { name, response, id? }` 块。

**evidence**(`mcp-client.ts:1454-1465`):
```typescript
return [
  {
    functionResponse: {
      name: call.name,
      response: result,    // ← 工具结果,任意 JSON
    },
  },
];
```

**写入 history**(`geminiChat.ts:974-988 addHistory`):`role: 'user'`,parts 含 `functionResponse`,`id` 字段记录关联。

**回传与 tool_use_id 关联**:`id` 字段就是 `functionCall.id`,Gemini API 内部配对。`chatRecordingService.ts:914-947` 进一步同步到 session record(Masking Sync:工具结果变化时同步到 `ToolCallRecord.result`)。

#### 4.2 通信协议:Google genai(单协议,**非** OpenAI/Anthropic 通用)

- 全代码只用 `@google/genai` 包,**没有任何 OpenAI 客户端 / Anthropic SDK**
- 工具 schema 描述字段是 `parametersJsonSchema`(JSON Schema draft 2020-12),不是 OpenAI 的 `parameters` 也不是 Anthropic 的 `input_schema`
- 工具结果回传用 `functionResponse: { name, response }`,不是 OpenAI 的 `role: 'tool'` + `content`
- 也不学 Anthropic 的 `tool_use_id` 块结构

#### 4.3 大结果处理

| 机制 | 位置 | 限制 |
|---|---|---|
| Shell live output buffer | `shell.ts:62 LIVE_OUTPUT_MAX_BUFFER_CHARS` | **100,000 chars**,超过就 trim 头部 |
| MCP discovery stdout/stderr | `tool-registry.ts:298-299` | **10 MB × 2**,超就 kill 子进程 |
| `truncateConversation` | `agentChatHistory.ts` | 上下文 token 超限时分段保留头/尾 |
| Schema depth | `geminiChat.ts:1064-1085` | 检测 `maximum schema depth exceeded`,给 LLM 提示禁用 cyclic schema 工具 |
| **MCP image/audio 块** | `mcp-tool.ts:378-431 transformImageAudioBlock` | 转成 `Part.inlineData: { mimeType, data }`,LLM 直接看 |

**注意:Gemini CLI 没用 Anthropic 那套 "thinking/separator + truncation" marker**,也没有显式的"摘要压缩 tool result"模式。完全靠 token budget 触发 `truncateConversation`。

---

### Q5. File Backend 是否为工具调用做了适配

> 配合 `Gemini_CLI/file_backend.md` 看;这里是"为工具调用服务的目录"。

#### 5.1 工具配置目录/文件清单

| 路径(全局) | 路径(项目) | 用途 | 加载代码 |
|---|---|---|---|
| `~/.gemini/settings.json` | `<cwd>/.gemini/settings.json` | `mcpServers` + `hooks` + `coreTools` 排除 + `useWriteTodos` + `enableAgents` + `experimental` + ... | `settings.ts:768-908` mergeSettings |
| `~/.gemini/commands/*.toml` | `<cwd>/.gemini/commands/*.toml` | 用户/项目级 slash 命令(可被 tool 引用) | `services/FileCommandLoader.ts` |
| `~/.gemini/skills/<name>/SKILL.md` | `<cwd>/.gemini/skills/<name>/SKILL.md` | **Agent Skills**(通过 activate_skill 工具调用) | `skills/skillManager.ts:75-101` |
| `~/.gemini/agents/*.md` | `<cwd>/.gemini/agents/*.md` | **Sub-Agent definitions**(invoke_agent 工具) | `agents/agentLoader.ts` |
| `~/.gemini/policies/*.toml` | `<cwd>/.gemini/policies/*.toml` | 工具调用策略(allow/deny/ask) | `policy/toml-loader.ts` |
| `~/.gemini/extensions/<name>/` | `<cwd>/.gemini/extensions/<name>/` | 扩展(可含 mcpServers + commands + skills + agents + policies + hooks) | `extension-manager.ts:1058` |
| `~/.gemini/mcp-oauth-tokens.json` | — | MCP OAuth 凭据 | `mcp/oauth-token-storage.ts` |
| `~/.gemini/extensions/installs.json` | — | 扩展安装元数据 | `extensions/storage.ts` |

#### 5.2 加载代码

```typescript
// config.ts:585-590:loadCliConfig 入口
export async function loadCliConfig(settings, sessionId, argv, options) {
  const { cwd = process.cwd(), projectHooks, skipExtensions = false, loadedSettings } = options;
  // ...
  return new Config({ targetDir: cwd, settings, ... });
}
```

```typescript
// config.ts:2542-2548:refreshMcpContext 触发完整 reload
async refreshMcpContext(): Promise<void> {
  await this.memoryContextManager?.refresh();
  if (this._geminiClient?.isInitialized()) {
    await this._geminiClient.setTools();   // ← 重新生成 tool list
    this._geminiClient.updateSystemInstruction();
  }
}
```

#### 5.3 全局 vs 项目级 vs 两者

**4 层 merge,全部支持**:
- 系统默认(`getDefaultsFromSchema()`) < 系统 defaults(`system-defaults.json`) < 系统 settings(`systemSettings.json`) < **用户** `~/.gemini/settings.json` < **项目** `<cwd>/.gemini/settings.json`(优先级最高)
- 见 `settings.ts:904-908 mergeSettings(...)` 晚到覆盖早到

#### 5.4 与 `standard/file_backend.md` 的对照

| `file_backend.md` 条款 | Gemini CLI 落实情况 |
|---|---|
| §1.3 AGENTS.md 向上扫描到 .git 边界 | **是**,但用 `GEMINI.md` 而非 `AGENTS.md`(同时 `memoryContextManager.ts:46-64` 支持 4 类,详见 file_backend §2.6) |
| §2.1 单一 env override 点 | ✅ `GEMINI_CLI_HOME`(`paths.ts:22-29`) |
| §2.3 4 层覆盖链 | ✅ 5 层(系统默认 + 系统 defaults + 系统 + user + workspace) |
| §3.1 严格三层分离 | ✅ `~/.gemini/`(全局) + `<cwd>/`(项目) + `~/.gemini/tmp/<shortId>/`(运行时) |
| §3.9 项目级 scratch + .gitignore | ❌ **没有项目级 scratch 目录**,所有项目级配置都在 `<cwd>/.gemini/` |
| §5.3 secrets 独立 + 0o600 | ⚠️ `oauth_creds.json` / `mcp-oauth-tokens.json` / `google_accounts.json` 独立存储,**但未声明 0o600 权限** |
| §10.7 hook + plugin 系统 | ✅ **完整**:`hooks` 12 种事件 + Extension 系统(含 commands/hooks/skills/agents/policies/mcpServers) |
| §10.8 MCP 协议支持 | ✅ **完整**:`mcpServers` 在 settings.json + extension.json + 项目级覆盖;OAuth / SSE / Stdio / HTTP / 鉴权全有 |
| §9.3 folder-trust 弹窗 | ✅ `folderTrust.enabled` 默认 `true`,headless 阻塞报错,详见 `file_backend.md §3.5` |

---

## 3. 关键代码片段(精选)

### 3.1 工具列表生成 + 传递(`client.ts:307-320`)

```typescript
async setTools(modelId?: string): Promise<void> {
  if (!this.chat) return;
  if (modelId && modelId === this.lastUsedModelId) return;
  this.lastUsedModelId = modelId;
  const toolRegistry = this.context.toolRegistry;
  const toolDeclarations = toolRegistry.getFunctionDeclarations(modelId);
  const tools: Tool[] = [{ functionDeclarations: toolDeclarations }];
  this.getChat().setTools(tools);
}
```

### 3.2 流式 functionCall 解析(`geminiChat.ts:1144-1175`)

```typescript
if (chunk.functionCalls && chunk.functionCalls.length > 0) {
  if (this.context.config.isContextManagementEnabled()) {
    for (let i = 0; i < chunk.functionCalls.length; i++) {
      const fnCall = chunk.functionCalls[i];
      const globalIndex = currentChunkStartCounter + i;
      if (!fnCall.id) {
        let id = callIndexToId.get(globalIndex);
        if (!id) {
          id = `synth_${this.context.promptId}_${Date.now()}_${this.callCounter++}`;
          callIndexToId.set(globalIndex, id);
        }
        fnCall.id = id;
      }
      const name = fnCall.name?.trim() || 'generic_tool';
      if (fnCall.id && !fnCall.id.startsWith(`${name}__`)) {
        fnCall.id = `${name}__${fnCall.id}`;
      }
      finalFunctionCallsMap.set(fnCall.id, fnCall);  // Map 去重
    }
  } else {
    for (const fnCall of chunk.functionCalls) {
      const name = fnCall.name?.trim() || 'generic_tool';
      if (fnCall.id && !fnCall.id.startsWith(`${name}__`)) {
        fnCall.id = `${name}__${fnCall.id}`;
      }
    }
    legacyFunctionCalls.push(...chunk.functionCalls);
  }
}
```

### 3.3 MCP 工具回传(`mcp-client.ts:1454-1465`)

```typescript
return [
  {
    functionResponse: {
      name: call.name,
      response: result,    // 任意 MCP result JSON
    },
  },
];
```

### 3.4 工具 schema 自动注入 `wait_for_previous`(`tools.ts:405-426`)

```typescript
private addWaitForPreviousParameter(schema: unknown): unknown {
  if (!this.isParameterSchema(schema) || schema.type !== 'object') return schema;
  const props = schema.properties;
  let propertiesObj = props && isRecord(props) ? props : {};
  return {
    ...schema,
    properties: {
      ...propertiesObj,
      wait_for_previous: {
        type: 'boolean',
        description:
          'Set to true to wait for all previously requested tools in this turn to complete before starting. Set to false (or omit) to run in parallel...',
      },
    },
  };
}
```

### 3.5 Agent Skills 渐进披露(`skillManager.ts:50-104`)

```typescript
async discoverSkills(storage, extensions, isTrusted) {
  this.clearSkills();
  await this.discoverBuiltinSkills();           // 内置
  for (const ext of extensions) { ... }          // 扩展
  this.addSkillsWithPrecedence(
    await loadSkillsFromDir(Storage.getUserSkillsDir()));    // 用户
  this.addSkillsWithPrecedence(
    await loadSkillsFromDir(Storage.getUserAgentSkillsDir())); // ~/.agents/skills alias
  if (!isTrusted) return;                       // 信任检查
  this.addSkillsWithPrecedence(
    await loadSkillsFromDir(storage.getProjectSkillsDir()));  // 项目
}
```

---

## 4. 与 Onion Agent 设计的关联

| Gemini CLI 做法 | Onion Agent 可借鉴 / 规避 |
|---|---|
| **协议 = Google genai 单协议**,不是 Provider 无关 | ⚠️ **反着来**。Onion 是 Provider 热插拔设计,要学 Cline / opencode / Continue 的 OpenAI/Anthropic 兼容协议,**不要学 Gemini CLI 把协议写死**。但工具结构 `{ functionDeclarations: [...] }` 可作为参考原型。 |
| **工具 schema 自动注入 `wait_for_previous`** 让 LLM 控制并行/串行 | ✅ **强烈推荐抄**。Onion 的 tool schema 生成器也应该注入此参数(可避免 LLM 把独立 IO 操作串行化)。 |
| **流式 functionCall 解析用 `Map<id, FunctionCall>` 去重合并**(`geminiChat.ts:1144-1180`) | ✅ **抄**。Anthropic `input_json_delta` / OpenAI `delta.tool_calls` 都需要类似的"按 id 合并跨 chunk 数据"的机制。Onion 抽一个 `StreamToolCallAccumulator` 类,统一处理多协议。 |
| **MCP 工具命名强制 `mcp_<server>_<tool>` 前缀 + 64 字符限制**(`mcp-tool.ts:441-486`) | ✅ **抄**。Onion 应统一 `mcp_<server>_<tool>` 命名,避免和 builtin tool 重名。 |
| **Skill 渐进披露 = 工具只暴露 name+description,body 在 `activate_skill` 调用时全文注入** | ✅ **强烈推荐抄**。Onion 可设计 `activate_skill(name)` tool,skill body 在 tool 执行时塞进下一轮 user message。**这比"全量塞进 system prompt"高效得多**。 |
| **Skill discovery 4 层优先级:内置 < 扩展 < user < project**,且 project 必须 folder trust | ✅ **抄 + 改**。Onion 借鉴 OpenClaw 模式 `~/.onion/skills/` + `<repo>/.onion/skills/`,但项目级用 folder-trust 保护。 |
| **`DiscoveredMCPTool` 临时 register** + `McpClientManager` 全局管理 + `scheduleMcpContextRefresh` 增量更新 | ✅ **抄**。Onion 的 MCP 客户端管理可沿用 `McpClientManager` 模式,扩展热加载/卸载走 `refreshMcpContext` 重新生成 tool list。 |
| **工具结果回传用 `functionResponse` Part** + `id` 字段配对 | ✅ **抄(改为对应协议)**。Onion 用 OpenAI `role: 'tool'` + `tool_call_id`,Anthropic `tool_use_id` block,**但要抽 `ToolResultMessage` 抽象层**统一两种。 |
| **错误修复用 `validateBuildAndExecute` 静默 build** + 把错误回传 LLM | ✅ **抄**。Onion 的 tool shell 应该统一把"参数错误"和"执行错误"两类异常都回传 LLM,让 LLM 自纠。**不要 silent fail**(会误导 LLM)。 |
| **重试上限 `DEFAULT_MAX_ATTEMPTS = 10`,mid-stream API 硬限 3 次** | ✅ **抄**。Onion 可设 `MAX_API_RETRIES=10, MAX_MID_STREAM=3, MAX_TOOL_RETRIES=3`(工具结果错误不触发 retry,只回传 LLM)。 |
| **大结果截断用 token budget 触发 + `truncateConversation` 保留头尾** | ✅ **抄**。Onion 不需要逐 tool 维护截断(像 Anthropic 那样),走"总 token 预算 → 历史压缩"即可。 |
| **`shell.ts` 的 `LIVE_OUTPUT_MAX_BUFFER_CHARS = 100_000`** | ✅ **抄常量**。Onion 的 shell 工具可设 100k chars 上限。 |
| **MCP image/audio 直接转 `Part.inlineData`**(而非文本) | ✅ **抄(若用 Gemini 后端)**。OpenAI 用 `image_url`,Anthropic 用 `image` block — **Onion 抽 `MediaContent` 抽象**自动转对应协议。 |
| **没有专门的 `<repo>/.onion/scratch/`**(项目级 scratch 目录) | ❌ **不抄**。Onion 应借鉴 superpowers / Aider 模式,有 `<repo>/.onion/scratch/`(写时 .gitignore 提示)。 |
| **`folderTrust` 默认 true,未信任阻塞**(详见 `file_backend.md §3.5`) | ⚠️ **看场景**。信创内网可默认全信;若做 SaaS 则保留 trust 弹窗。 |
| **Hooks 12 种事件 + Extension 插件体系** | ✅ P2 阶段抄。MVP 先做核心 6 个 hook:`PreToolUse / PostToolUse / SessionStart / SessionEnd / PreCompact / Notification`。 |
| **plan-then-act = Plan Mode 时改写 `write_file`/`edit` 的 description 加 ONLY FOR PLANS 后缀** | ✅ **抄**。Onion 可以 `planMode = true` 时给 mutator tool 改 description,LLM 自纠。 |

**关键 takeaway**:
1. **工具 schema 注入 `wait_for_previous`** 是 Gemini CLI 最巧妙的设计(让 LLM 显式控制并发),值得全盘抄。
2. **Skill 渐进披露**:用 `activate_skill` 工具,description 在 schema、body 在 tool result — 这是解决"agent 加载过多 skill 撑爆 context"的标准答案。
3. **MCP 工具命名规范**(`mcp_<server>_<tool>` + 长度限制)OpenAI/Anthropic/Google 三家都没 Gemini CLI 这套严格,但对 Onion 这种"Provider 无关"产品反而更有用(因为需要 namespace)。
4. **Provider 无关 = 协议抽象层必须做** — Onion 千万不要学 Gemini CLI 写死 genai 协议。

---

## 5. 不确定 / 未找到

| 疑问 | 备注 |
|---|---|
| **`mcp_oauth_tokens.json` 写盘是否 chmod 0o600?** | 推测是但源码未直接确认,需查 `extensions/storage.ts` / `mcp/oauth-token-storage.ts` 实现细节。本次未深查。 |
| **`DiscoveredTool` 的 `toolDiscoveryCommand` / `toolCallCommand` 在哪里配置?** | 推测在 `settings.json` 的 `toolDiscoveryCommand` / `toolCallCommand` 字段(类似 Codex 的 `experimental` 块),但本次未深查 config 字段;ToolRegistry 第 348 行起只用了,未追到 source。 |
| **MCP 的 `discoveryCommand` 输出的 JSON schema 校验?** | ToolRegistry `discoverAndRegisterToolsFromCommand` 直接信任外部 JSON,不验 schema 完整性(只 `func.name` 必填)。风险点,但没找到专门验证函数。 |
| **`activate_skill` 工具的 description 摘要如何生成?** | `activate-skill.ts:51-60 getDescription` 只返 `"<name>": <description>`,没自动生成更短摘要。**推测:Agent 应该自己控制 description 字数**(skillManager discover 时不做截断)。 |
| **`Tracker*` 6 个 tool 的具体用途?** | 名称看似任务图/依赖管理,但 `trackerTools.ts` 未深读。**推测**:跟 `write_todos` 互补,用于复杂多任务依赖图(类似 MetaGPT 的 SOP)。 |
| **Token 重压缩/截断 `truncateConversation` 的具体算法?** | 已知在 `agentChatHistory.ts`,但实现细节未读。**推测**:跟 `compression` 事件同源,token 超限触发"保留头尾 + 摘要中间"模式。 |
| **Extension 热加载的"hook 注册到 hook system"具体实现?** | `extension-manager.ts:1058` 提到了 `hooks/hooks.json` 是扩展自带,本次没看完整 hook 注入流程。**待补**。 |

---

**调研人**:general(子代理)
**调研范围**:仅 `C:\workspace\github\onionagent\harness\01_market_research\clone\gemini-cli`,未做修改
**引用行号格式**:`path:line`,所有代码均来自该 snapshot
