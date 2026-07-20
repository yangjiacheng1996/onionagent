# OpenClaw — 工具调用（Tool Channel）调研报告

> 调研对象：`github.com/openclaw/openclaw` 仓库 `main` 分支（`git clone --depth 1` 快照，2026-07-17）
> 调研范围：仅 OpenClaw 一个智能体，聚焦"工具调用 / Tool Channel"维度
> 调研日期：2026-07-19

---

## 0. 智能体一句话定位

OpenClaw 是 2026 年现象级个人 AI 助手（GitHub 38 万 ⭐），持续运行的 agent loop + 20+ 渠道接入，工具生态庞大（内置 30+ 工具 + 100+ plugin + MCP 协议 + Agent Skills + 工具目录动态搜索）。

---

## 1. 调研依据

### 1.1 源码路径
```
C:\workspace\github\onionagent\harness\01_market_research\clone\openclaw\
```

### 1.2 关键文件（已重点阅读）

| # | 文件 | 说明 |
|---|------|------|
| 1 | `src/agents/openclaw-tools.ts` | **核心**——`createOpenClawTools` 工厂，组装 30+ 内置工具（`createOpenClawTools:103`,`openclaw-tools.ts:292-599`） |
| 2 | `src/agents/sessions/tools/index.ts:202` | `createCodingTools` 工厂（read / bash / edit / write / grep / find / ls） |
| 3 | `src/agents/agent-tools.ts:655` | agent tool surface 组装入口 |
| 4 | `src/agents/tool-search.ts` | **核心**——Tool Search 机制（`tool_search` / `tool_describe` / `tool_call` / `tool_search_code`，`tool-search.ts:17-23`） |
| 5 | `src/agents/agent-tools.before-tool-call.ts` | 工具执行前 hook、loop detection、approval、tracked 状态（`agent-tools.before-tool-call.ts:788,932,1193`） |
| 6 | `src/agents/embedded-agent-runner/run-loop.ts:167-320` | agent loop 主体 + `MAX_RUN_LOOP_ITERATIONS` 限制（默认 32-160） |
| 7 | `src/agents/embedded-agent-runner/run/helpers.ts:131-148` | `resolveMaxRunRetryIterations` 算法（base 24 + perProfile 8 × profiles，min 32，max 160） |
| 8 | `src/agents/embedded-agent-runner/tool-result-truncation.ts:45-58` | 工具结果截断（`MAX_TOOL_RESULT_CONTEXT_SHARE = 0.3`，`DEFAULT_MAX_LIVE_TOOL_RESULT_CHARS = 16_000`） |
| 9 | `src/agents/embedded-agent-runner/tool-result-context-guard.ts:38` | mid-turn 上下文守卫（`SINGLE_TOOL_RESULT_CONTEXT_SHARE = 0.5`） |
| 10 | `src/agents/embedded-agent-runner/run/attempt.tool-call-argument-repair.ts` | 工具参数修复（smart quotes / truncation / 平衡 JSON prefix） |
| 11 | `src/agents/embedded-agent-runner/run/attempt.tool-call-normalization.ts` | 工具调用归一化（`resolveCaseInsensitiveAllowedToolName`，`attempt.tool-call-normalization.ts:42-60`） |
| 12 | `packages/tool-call-repair/src/stream-normalizer.ts` | **核心**——plain-text 工具调用流式解析（58890 字节，scanXmlishToolCall / Harmony markers） |
| 13 | `packages/tool-call-repair/src/grammar.ts` | 4 种语法解析：`<function>` / `[tool:name]` / Harmony `<|channel|>` `<|message|>` `<|call|>` / `[END_TOOL_REQUEST]`（`grammar.ts:42-46,67-85`） |
| 14 | `packages/tool-call-repair/src/promote.ts:33-43` | 把 plain-text tool call promote 成 provider-native toolCall block |
| 15 | `src/agents/openai-completions-transport.ts:373-525,707-770` | **核心**——OpenAI 协议：流式解析 `choiceDelta.tool_calls` + `parseStreamingJson` + `toolcall_start/delta/end` 事件 |
| 16 | `src/agents/anthropic-transport-stream.ts:540-575,595-615,1443-1710` | **核心**——Anthropic 协议：流式解析 `content_block_start / input_json_delta / content_block_stop` + `convertAnthropicTools` |
| 17 | `packages/llm-core/src/types.ts:330-408` | 统一事件协议（`toolcall_start / toolcall_delta / toolcall_end` + `ToolResultMessage { toolCallId, content, isError }`） |
| 18 | `packages/llm-core/src/validation.ts:332-373` | TypeBox schema 校验（`validateToolCall` / `validateToolArguments`） |
| 19 | `packages/ai/src/providers/openai-tool-projection.ts:55-128` | OpenAI tool schema 投影（异常工具隔离 + 降级） |
| 20 | `src/config/mcp-config.ts:122,176,238,252` | MCP 配置加载/写入（`normalizeConfiguredMcpServers(sourceConfig.mcp?.servers)`） |
| 21 | `src/config/types.mcp.ts` | MCP schema 定义 |
| 22 | `src/config/paths.ts:64,197` | 状态目录解析（`resolveStateDir` + `OPENCLAW_STATE_DIR`） |
| 23 | `src/plugin-sdk/plugin-entry.ts` + `src/plugin-sdk/tool-plugin.ts:200` | plugin 工具注册（`api.registerTool(...)`） |
| 24 | `src/skills/loading/frontmatter.ts` + `skills/skill-creator/SKILL.md` | Agent Skills 实现（frontmatter + body 渐进披露） |
| 25 | `src/mcp/` | MCP Server / 客户端实现（plugin-tools-serve / openclaw-tools-serve / codex-supervision） |

### 1.3 文档/README 关键引用

- `README.md:163-165,188` — 工具能力（browser / canvas / nodes / cron / sessions / skills / webhooks）
- `docs/concepts/agent-workspace.md`（file_backend.md 调研已确认）— workspace + skills 目录布局
- `skills/skill-creator/SKILL.md`（已读前 40 行）— Skills 元数据契约（frontmatter + 渐进披露）

---

## 2. 五个核心问题的回答

### Q1. 工具来源

#### 内置工具（30+ 个，按工厂分组）

- **Coding 工具**（`src/agents/sessions/tools/index.ts:202-212`）
  - `read`、`write`、`edit`、`bash`、`grep`、`find`、`ls`

- **OpenClaw 高层工具**（`src/agents/openclaw-tools.ts:292-599`）
  - 媒体生成：`image_generate` / `video_generate` / `music_generate` / `image`（`openclaw-tools.ts:292-336`）
  - 文档：`pdf`（`openclaw-tools.ts:351`）
  - Web：`web_search` / `web_fetch`（`openclaw-tools.ts:362-370`）
  - 通信：`message`（`openclaw-tools.ts:379`，channel 平台消息）
  - 系统：`heartbeat` / `nodes`（`openclaw-tools.ts:407,409`）
  - 控制平面：`computer` / `cron` / `sessions` / `screen` / `terminal` / `tts` / `transcripts` / `gateway`（`openclaw-tools.ts:465-524`）
  - 多 agent：`agents_list` / `get_goal` / `create_goal` / `update_goal`（`openclaw-tools.ts:527-543`）
  - Skills：`skill_workshop`（`openclaw-tools.ts:552`）
  - 规划：`update_plan`（`openclaw-tools.ts:562`）
  - Session 工具：`sessions_list` / `sessions_history` / `sessions_search`（`openclaw-tools.ts:563-575`）
  - 跨对话：`conversations_list` / `conversations_send` / `conversations_turn`（`openclaw-tools.ts:585-599`）

- **Memory 工具**（`extensions/memory-core/index.ts:115-148`，plugin 注册）
  - `memory_search`（`memory-core/index.ts:117`）—— 强制 recall
  - `memory_get`（`memory-core/index.ts:148`）—— 精确读 MEMORY.md / memory/*.md

- **Tool Search 工具**（`src/agents/tool-search.ts:17-23`）
  - `tool_search` / `tool_describe` / `tool_call`（**目录式**，把 100+ 工具缩成 3-4 个元工具）
  - `tool_search_code`（Code Mode，JS 沙箱里动态调用工具）

- **Plugin 工具**（`src/plugin-sdk/tool-plugin.ts:200`）
  - 各 channel 工具（discord / slack / telegram / whatsapp / signal / imessage …）
  - 各 domain 工具（firecrawl / 1password / 飞书 / github / brave / exa …）
  - 通过 `api.registerTool((ctx) => factory(ctx), { name: "..." })` 注册

#### MCP 支持
- **是**。配置在 `openclaw.json` 的 `mcp.servers` 字段（`src/config/mcp-config.ts:122`）：
  ```ts
  mcpServers: normalizeConfiguredMcpServers(sourceConfig.mcp?.servers),
  ```
- MCP 类型定义在 `src/config/types.mcp.ts`（3832 字节）
- MCP server 启动配置在 `src/mcp/openclaw-tools-serve-config.ts:5663`（含 OAuth / SSE / stdio 模式）
- MCP plugin client 在 `src/mcp/plugin-tools-serve.ts:4042`（plugin ↔ MCP client）
- ACP 翻译器（`src/acp/translator.ts:1772`）也支持 `mcpServers: [{ name, command }]`
- 配置加载：`src/config/mcp-config.ts:141-176` 读 + 写（带 redact / restore argv 敏感值）

#### Agent Skills 支持
- **是**。`skills/<name>/SKILL.md` 是渐进披露技能格式。
- 仓库自带 50+ skill（`skills/` 目录，每个子目录都有 `SKILL.md`），如 `1password` / `github` / `goplaces` / `node-connect` / `weather` / `tmux` / `summarize` / `skill-creator` 等。
- SKILL.md 格式（`skills/skill-creator/SKILL.md:1-9`）：
  ```yaml
  ---
  name: skill-name
  description: "短触发描述——只放 trigger-critical facts"
  ---
  # Body — 触发后才加载
  ```
- 可选子目录：`references/` / `scripts/` / `assets/` / `agents/`
- 加载器：`src/skills/loading/local-loader.ts` + `workspace.ts` + `frontmatter.ts`（frontmatter 解析，errors throw with code+message）
- 生命周态：`src/skills/lifecycle/{install,clawhub,gh-config-discovery,archive-install,upload-install}.ts`

#### 其他工具类型
- **Channel 工具**（每个 channel 一个 plugin，提供 `send_message` / `react` 等）
- **Cron 工具**（定时任务，6 模式 hook）
- **Webhook 工具**（外部触发器）
- **Code Mode**（`tool_search_code` —— 在 JS 沙箱里批量执行工具调用）

### Q2. 工具列表的生成、传递、格式

#### 生成方式
- **动态组装 + plugin 注入**，不是写死：
  1. 核心层：`createCodingTools` 7 个工具（`sessions/tools/index.ts:202`）
  2. OpenClaw 层：`createOpenClawTools` 30+ 工具（`openclaw-tools.ts:103`，用 sandbox / profile / sender / group / sub-agent policy 过滤）
  3. Plugin 层：plugin 入口 `register(api) { api.registerTool(...) }` 注册（`src/plugin-sdk/tool-plugin.ts:200`）
  4. MCP 层：启动时从 `mcp.servers` 拉取 list_tools，包装成 AnyAgentTool
  5. Memory 层：`memory-core` plugin 注入 `memory_search` / `memory_get`
  6. Tool Search 包装层：当工具数 > 阈值时，全部工具被替换为 3 个 meta 工具（`tool_search` / `tool_describe` / `tool_call`），描述**实际工具**通过 on-demand describe 加载（`src/agents/tool-search.ts:21-23`）

#### 传递方式
- 抽象为 `Context.tools: Tool[]`（`packages/llm-core/src/types.ts:687-695`，TSchema parameters）
- provider-specific 转换：
  - **OpenAI 协议**：`src/agents/openai-completions-transport.ts:1330-1360` `convertTools` 把 `Tool[]` 转成 `{ type: "function", function: { name, description, parameters, strict? } }` 数组
  - **OpenAI Responses 协议**：`src/agents/openai-responses-transport.ts:1168-1180` 类似，包装为 `ResponseCreateParamsStreaming["tools"]`
  - **Anthropic 协议**：`src/agents/anthropic-transport-stream.ts:595-615` `convertAnthropicTools` 转成 `{ name, description, input_schema: { type, properties, required } }`
- 工具名按字母排序（`openai-completions-transport.ts:1348` `sortTransportToolsByName`，保证 OpenAI cache hit）
- Schema 投影：异常工具被隔离或降级（`packages/ai/src/providers/openai-tool-projection.ts:55-128`）

#### 格式（实际 JSON 片段）

OpenAI 协议下 `convertTools` 输出（简化版，基于 `openai-completions-transport.ts:1330-1360`）：
```json
[
  {
    "type": "function",
    "function": {
      "name": "bash",
      "description": "Run a shell command in the workspace...",
      "parameters": { "type": "object", "properties": { "cmd": {...} }, "required": ["cmd"] },
      "strict": true
    }
  },
  { "type": "function", "function": { "name": "read", ... } }
]
```

Anthropic 协议下 `convertAnthropicTools` 输出（`anthropic-transport-stream.ts:595-615`）：
```json
[
  {
    "name": "bash",
    "description": "Run a shell command...",
    "input_schema": { "type": "object", "properties": {...}, "required": [...] }
  }
]
```

#### 是否 prompt-as-tool
- **否**。核心走 function calling 协议（OpenAI `tools` / Anthropic `tools`）。
- **特殊例外**：当 provider 走 plain text 输出（local model / 弱模型），`tool-call-repair` 把 plain text 的 `<function>` / `[tool:name]` / Harmony markers **promote** 成 tool call（`packages/tool-call-repair/src/promote.ts:33-43`）。
- 工具 description 主要走 system prompt 注入，但工具本身是 function call，不是 prompt-as-tool。

#### 动态刷新
- **是**。Tool Search 机制：`tool_search` / `tool_describe` 让 LLM 按需查目录（`src/agents/tool-search.ts`），不需要把 100+ 工具塞进 system prompt。
- MCP 工具可启动时新增（`resolveSessionAgentIds` 后注册到 run-scoped catalog）。
- 失败隔离：`openai-tool-projection.ts:55-128` 坏工具被 quarantine（`unreadable_tool`），不影响同请求其他工具。

### Q3. 工具调用指令的解析、错误修复、准确性

#### 解析方式（流式增量 + 统一事件协议）

**统一抽象**（`packages/llm-core/src/types.ts:401-408`）：
```ts
| { type: "toolcall_start"; contentIndex: number; partial: AssistantMessage }
| { type: "toolcall_delta"; contentIndex: number; delta: string; partial: AssistantMessage }
| { type: "toolcall_end"; contentIndex: number; toolCall: ToolCall; partial: AssistantMessage }
```

**OpenAI 协议流式解析**（`src/agents/openai-completions-transport.ts:707-770`）：
```ts
if (choiceDelta.tool_calls && choiceDelta.tool_calls.length > 0) {
  for (const toolCall of choiceDelta.tool_calls) {
    // 按 index / id 找到对应 block
    if (!block) { /* 第一个 delta：创建 block，emit toolcall_start */ }
    if (toolCall.function?.arguments) {
      block.partialArgs += toolCall.function.arguments;  // 增量拼 JSON 字符串
      block.arguments = parseStreamingJson(block.partialArgs);  // 实时解析
      pushStreamEvent({ type: "toolcall_delta", contentIndex, delta: ..., partial: output });
    }
  }
}
```
- 字节上限保护：`MAX_TOOL_CALL_ARGUMENT_BUFFER_BYTES`（单 tool call 参数累计字节超过即抛错）
- `[DONE]` 检测：与 `finish_reason` 双判（`openai-completions-transport.ts:792-806`，避免 Evolink DeepSeek V4 类"无 finish_reason 但有 delta.tool_calls"被误判 stop）
- DeepSeek DSML 特殊处理：`createDeepSeekDsmlToolCallRecoverer()`（`openai-completions-transport.ts:838-985`）—— 解析 `<|DSML|tool_calls|>{...}</|DSML|tool_calls|>` 自定义标签

**Anthropic 协议流式解析**（`src/agents/anthropic-transport-stream.ts:1443-1710`）：
```ts
if (event.type === "content_block_start") {
  // tool_use 块：open new toolCall block
}
if (event.type === "content_block_delta") {
  if (delta?.type === "input_json_delta" && typeof delta.partial_json === "string") {
    block.partialJson += delta.partial_json;
    block.arguments = parseAnthropicToolCallArguments(partialJson);  // 渐进 JSON parse
    eventSink.push({ type: "toolcall_delta", ... });
  }
}
if (event.type === "content_block_stop") {
  // 收尾
}
```

#### 错误修复机制

**1. Plain text tool call 修复**（`packages/tool-call-repair/`，核心 58890 字节）：
- 4 种语法支持（`grammar.ts:42-46`）：
  - XML-ish：`<function=name><parameter=k>v</parameter></function>`
  - Named bracket：`[tool_name]\n{...}`
  - Harmony stream markers：`<|channel|>analysis<|message|>{...}<|call|>`
  - Legacy：`[END_TOOL_REQUEST]`
- 三态扫描：`{ kind: "prefix" } | { kind: "complete" } | { kind: "invalid" }`（`payload.ts:48-72`）—— 支持流式增量修复
- 字节上限：`MAX_PAYLOAD_BYTES = 256_000`（`stream-normalizer.ts:44`）
- 工具名白名单：`allowedToolNames` matcher，未在白名单则拒绝（`promote.ts:33-43`）

**2. Tool call 参数修复**（`src/agents/embedded-agent-runner/run/attempt.tool-call-argument-repair.ts`，23375 字节）：
- Smart quotes（`\u201c \u201d \u201e \u201f`）自动转 ASCII
- 截断 / 缺 closing brace 修复（`extractBalancedJsonPrefix`）
- 已知参数键名容错（`TOOLCALL_REPAIR_KNOWN_ARG_KEYS` 30+ 个：`path` / `cmd` / `content` / `edits` / `oldText` / `newText` 等）
- `edits` 数组容错（smart-quoted 数组解析）
- 最大 buffer：`MAX_TOOLCALL_REPAIR_BUFFER_CHARS = 64_000`

**3. Unknown tool name fallback**（`src/agents/embedded-agent-runner/run/attempt.tool-call-normalization.ts:42-60`）：
- 大小写不敏感匹配（`resolveCaseInsensitiveAllowedToolName`）
- `normalizeToolName` 规范化

#### 准确性保证

- **Schema 校验**（`packages/llm-core/src/validation.ts:332-373`）：TypeBox / JSON schema 双路径校验（`validateToolCall` + `validateToolArguments`），错误信息按 path 格式化（`formatValidationPath`）
- **Loop detection**（`src/agents/tool-loop-detection-config.ts`）—— 防死循环
- **Tool Search 黑名单**（`src/agents/tool-search.ts:21-23`）—— Tool Search 工具被屏蔽（`TOOL_SEARCH_CONTROL_TOOL_NAMES`）不允许自我递归
- **Unreadable tool 隔离**（`packages/ai/src/providers/openai-tool-projection.ts:55-128`）—— 坏工具被 quarantine，不影响 sibling tools
- **Plan-then-act 模式**：可选 `update_plan` 工具（`openclaw-tools.ts:562`）—— LLM 主动声明计划，但非强制

#### 重试上限

- **Run loop 兜底**（`src/agents/embedded-agent-runner/run-loop.ts:167,277-285`）：
  - `MAX_RUN_LOOP_ITERATIONS = resolveMaxRunRetryIterations(profileCandidateCount, cfg, agentId)`（`run/helpers.ts:131-148`）
  - 算法：`base = max(1, runRetries.base ?? 24)` + `perProfile = max(0, runRetries.perProfile ?? 8) × profiles` → 截断在 `[min=32, max=160]`
  - 触发后行为：`Exceeded retry limit after N attempts (max=160).` —— `[run-retry-limit]` 错误信号
- **Provider failover**（`src/agents/embedded-agent-runner/run/failover-retry-controller.ts`）—— 同一 provider 内部 retry + 跨 provider 切换
- **Tool-call 内部**未发现"工具执行失败 → 自动 LLM 重新生成 tool call"的硬编码 retry，是 model-driven（LLM 看到 tool result 错误后自己决定是否换工具）

### Q4. 工具执行结果回传

#### 回传方式（双协议）

**Anthropic 协议**（`src/agents/anthropic-transport-stream.ts:555-585`）：
```ts
if (msg.role === "toolResult") {
  const toolResults = [{
    type: "tool_result",
    tool_use_id: toolResult.toolCallId,  // ← 关联回 assistant tool_use
    content: convertContentBlocks(toolResult.content),
    is_error: toolResult.isError,        // ← 错误标记
  }];
  // ... 连续 toolResult 合并到一个 user message
  params.push({ role: "user", content: toolResults });
}
```

**OpenAI 协议**（待确认 — 在 `openai-completions-transport.ts` 中通过 `ToolResultMessage` 抽象，转换成 `role: "tool" / tool_call_id` 形态）
- `ToolResultMessage` 统一类型（`packages/llm-core/src/types.ts:330-345`）：
  ```ts
  interface ToolResultMessage {
    role: "toolResult";
    toolCallId: string;   // 关联回 toolCall
    toolName: string;
    content: (TextContent | ImageContent)[];  // 支持 text + images
    details?: TDetails;
    isError: boolean;
    timestamp: number;
  }
  ```

#### 格式
- content 是 `TextContent | ImageContent` 数组（`types.ts:330`），不是裸字符串
- 错误用 `isError: boolean` 字段标记
- 序列化为 JSON 由 transport 完成，**不是 LLM 看到的结构**

#### 通信协议
- **多协议并行**（OpenAI / Anthropic / Google / OpenAI Responses / Codex 等 30+ provider 插件，详见 `extensions/` 目录）
- 上层统一为 `Context.tools + AssistantMessageEventStream` 抽象
- 同一份 tool list 可被任意 provider adapter 消费（`projectOpenAITools` / `projectAnthropicTools`）

#### 大结果处理

**截断策略**（`src/agents/embedded-agent-runner/tool-result-truncation.ts:45-58`）：
```ts
const MAX_TOOL_RESULT_CONTEXT_SHARE = 0.3;       // 单 tool result 不超 30% 上下文
export const DEFAULT_MAX_LIVE_TOOL_RESULT_CHARS = 16_000;
const LARGE_CONTEXT_MAX_LIVE_TOOL_RESULT_CHARS = 32_000;
const XL_CONTEXT_MAX_LIVE_TOOL_RESULT_CHARS = 64_000;
const AGGREGATE_TOOL_RESULT_CONTEXT_SHARE = 0.5;  // 累计不超过 50%
const MIN_KEEP_CHARS = 2_000;                     // 最少保留 2K
```

**完整 output 旁路**：`formatFullOutputFooter`（`sessions/tools/tool-contracts.ts`）—— 完整结果写到磁盘（`~/.openclaw/sessions/<id>/`），prompt 里只放 truncated + 引用路径

**Mid-turn precheck**（`src/agents/embedded-agent-runner/tool-result-context-guard.ts:38-55`）：
- `SINGLE_TOOL_RESULT_CONTEXT_SHARE = 0.5`（单个 tool result 50% 阈值就触发 preemptive compaction）
- `PREEMPTIVE_OVERFLOW_RATIO = 0.9`（90% 上下文占用即触发压缩）

**图像 / 媒体**：`ToolResultMessage.content` 支持 `ImageContent`，transport 在 OpenAI / Anthropic 各自 protocol 转换（`convertContentBlocks` 走 image blocks）

### Q5. File Backend 是否为工具调用做了适配

#### 工具配置目录 / 文件清单

| 路径 | 作用 | 加载位置 |
|------|------|---------|
| `~/.openclaw/openclaw.json`（默认 state dir） | **主配置**，含 `mcp.servers` / `tools` / `plugins` / `agents` / `channels` | `src/config/paths.ts:197` `resolveConfigPath` + `src/config/mcp-config.ts:122` |
| `~/.openclaw/workspace/skills/<name>/SKILL.md` | **Agent Skills** 渐进披露 | `src/skills/loading/local-loader.ts` + `workspace.ts` |
| `~/.openclaw/workspace/AGENTS.md` / `SOUL.md` / `USER.md` 等 | 注入式 prompt 模板 | `src/agents/workspace-templates.ts`（file_backend.md 调研已确认） |
| `<repo>/extensions/<name>/openclaw.plugin.json` | **plugin manifest**（含工具 / channel / provider 声明） | 各 plugin `index.ts` |
| `~/.openclaw/openclaw.json` 内 `mcp.servers.<name>` | MCP server 注册（stdio / http / sse） | `src/config/mcp-config.ts:122,238` |
| `~/.openclaw/sessions/<id>/` | 工具结果完整 output 存档 | `src/agents/embedded-agent-runner/tool-result-truncation.ts` |

#### 加载代码证据

- 主配置 + MCP：`src/config/mcp-config.ts:122` `mcpServers: normalizeConfiguredMcpServers(sourceConfig.mcp?.servers)`
- State dir 解析：`src/config/paths.ts:64` `resolveStateDir(env, homedir)` —— 单一 env 覆盖点 `OPENCLAW_STATE_DIR`
- Config 路径：`src/config/paths.ts:197` `resolveConfigPath` —— 单一 env 覆盖点 `OPENCLAW_CONFIG_PATH`
- Skill frontmatter 解析：`src/skills/loading/frontmatter.ts:24-32` `parseFrontmatter`（YAML → `ParsedSkillFrontmatter`）
- Tool Search 目录：`src/agents/tool-search.ts:43` `MAX_REUSABLE_CATALOG_SNAPSHOTS = 256`
- Plugin 注册：`src/plugin-sdk/tool-plugin.ts:200` `api.registerTool(...)`

#### 全局 vs 项目级 vs 两者
- **全局生效**：`~/.openclaw/openclaw.json` —— MCP / plugin / 工具 / skills 全部主配置
- **项目级**：`~/.openclaw/workspace/`（**仍然是全局位置**，但语义上是"每个 agent 自己的 workspace"）
- **plugin 自带**：`extensions/<name>/openclaw.plugin.json`（跟随代码仓）
- **Profile 隔离**：`OPENCLAW_PROFILE=work` → `~/.openclaw/workspace-work` / `~/.openclaw/agents-work`（`src/agents/workspace-default.ts:7-23`）

#### 与 standard/file_backend.md 对照

| standard § | OpenClaw 表现 | 一致性 |
|------------|--------------|------|
| §1.1 固定用户属主目录 + env 单一覆盖点 | `~/.openclaw/` + `OPENCLAW_STATE_DIR` / `OPENCLAW_CONFIG_PATH` / `OPENCLAW_WORKSPACE_DIR`（3 个 env，但语义清晰） | ✅ 强烈建议 |
| §1.2 控制平面 vs workspace 双层 | state dir（配置 / sessions / state.db）vs workspace dir（AGENTS.md / skills / memory）显式分离（file_backend.md §1.2 已确认） | ✅ 强烈建议 |
| §1.3 AGENTS.md 向上扫描到 .git 边界 | 显式支持（`workspace.ts`），**字节上限未在源码中找到（未确认）** | ⚠ 部分一致 |
| §1.4 secrets 独立 + 0o600 | `~/.openclaw/auth-profiles.json` + `auth.json`（独立）| ✅ 强烈建议 |
| §3.1 三层分离 | state dir / workspace / `tmp/<shortId>/` | ✅ 必须做 |
| §3.8 Bootstrap 种子文件 | workspace 首次 seed 9 个文件（AGENTS.md / SOUL.md / USER.md / IDENTITY.md / TOOLS.md / HEARTBEAT.md / BOOT.md / BOOTSTRAP.md / MEMORY.md）—— 缺失文件注入"missing file"标记（file_backend.md 调研已确认） | ✅ 强烈建议 |
| §10.8 MCP 协议支持 | `openclaw.json` 内 `mcp.servers` + OAuth + SSE + stdio 多种 backend | ✅ 强烈建议（实现深度领先）|

---

## 3. 关键代码片段

### 3.1 统一事件协议（`packages/llm-core/src/types.ts:401-408`）

```ts
| { type: "toolcall_start"; contentIndex: number; partial: AssistantMessage }
| { type: "toolcall_delta"; contentIndex: number; delta: string; partial: AssistantMessage }
| { type: "toolcall_end"; contentIndex: number; toolCall: ToolCall; partial: AssistantMessage }
```

### 3.2 OpenAI 协议流式解析（`src/agents/openai-completions-transport.ts:707-770` 简化版）

```ts
if (choiceDelta.tool_calls && choiceDelta.tool_calls.length > 0) {
  for (const toolCall of choiceDelta.tool_calls) {
    const streamIndex = typeof toolCall.index === "number" ? toolCall.index : undefined;
    let block = streamIndex !== undefined ? toolCallBlocksByIndex.get(streamIndex) : undefined;
    if (!block) {
      // First delta: create tool call block + emit start
      block = { type: "toolCall", id: toolCall.id || "", name: toolCall.function?.name || "", ... };
      pushStreamEvent({ type: "toolcall_start", contentIndex, partial: output });
    }
    if (toolCall.function?.arguments) {
      // Byte-budget guard
      if (currentBlockArgBytes + nextArgumentBytes > MAX_TOOL_CALL_ARGUMENT_BUFFER_BYTES) {
        throw new Error("Exceeded tool-call argument buffer limit");
      }
      block.partialArgs += toolCall.function.arguments;
      block.arguments = parseStreamingJson(block.partialArgs);  // 实时解析
      pushStreamEvent({ type: "toolcall_delta", contentIndex, delta: ..., partial: output });
    }
  }
}
```

### 3.3 Tool 投影 + 隔离（`packages/ai/src/providers/openai-tool-projection.ts:55-95` 简化版）

```ts
export function projectOpenAITools(tools: readonly OpenAIToolDescriptor[]): OpenAIToolProjection {
  for (let toolIndex = 0; toolIndex < tools.length; toolIndex += 1) {
    try { tool = tools[toolIndex]; } catch { diagnostics.push(unreadableToolDiagnostic(toolIndex)); continue; }
    // 参数 schema 投影
    const schemaProjection = projectRuntimeToolInputSchema(parameters ?? {}, `${name}.parameters`);
    if (!isRecord(schemaProjection.schema) || schemaProjection.violations.length > 0) {
      diagnostics.push({ toolIndex, toolName: name, violations: schemaProjection.violations });
      continue;  // ← 隔离坏工具，不影响其他
    }
    projectedTools.push({ toolIndex, name, description, parameters: schemaProjection.schema });
  }
}
```

### 3.4 工具结果截断（`src/agents/embedded-agent-runner/tool-result-truncation.ts:43-58`）

```ts
const MAX_TOOL_RESULT_CONTEXT_SHARE = 0.3;
export const DEFAULT_MAX_LIVE_TOOL_RESULT_CHARS = 16_000;
const LARGE_CONTEXT_MAX_LIVE_TOOL_RESULT_CHARS = 32_000;
const XL_CONTEXT_MAX_LIVE_TOOL_RESULT_CHARS = 64_000;
const AGGREGATE_TOOL_RESULT_CONTEXT_SHARE = 0.5;
const MIN_KEEP_CHARS = 2_000;
```

### 3.5 Tool-call repair 三态扫描（`packages/tool-call-repair/src/grammar.ts:62-95` 简化版）

```ts
// 扫描 XML-ish / named-bracket / tool-bracket 工具调用
while (true) {
  const markerStart = skipWhitespace(text, cursor);
  if (markerStart === text.length) return { kind: "prefix", ... };  // 流式未完成
  if (startsWithAsciiMarkerIgnoreCase(text, markerStart, FUNCTION_CLOSE)) {
    return complete(markerStart);  // 完成
  }
  // 找参数：<parameter=name>value</parameter>
  if (startsWithAsciiMarkerIgnoreCase(text, markerStart, PARAMETER_OPEN)) {
    const closeStart = indexOfAsciiMarkerIgnoreCase(text, PARAMETER_CLOSE, valueStart);
    if (closeStart === -1) return prefix(text.length, valueStart);  // prefix
    parameters.push({ name: {start, end: nameEnd}, value: {start: valueStart, end: closeStart} });
  }
}
```

### 3.6 MCP 配置加载（`src/config/mcp-config.ts:122`）

```ts
mcpServers: normalizeConfiguredMcpServers(sourceConfig.mcp?.servers),
// → 来自 ~/.openclaw/openclaw.json
// → normalizeConfiguredMcpServers 在 mcp-config-normalize.ts:3181
```

---

## 4. 与 Onion Agent 设计的关联

1. **Onion 可以学 —— "Tool Search" 机制**：`tool_search` / `tool_describe` / `tool_call` 三件套把 100+ 工具缩成 3 个 meta 工具（`src/agents/tool-search.ts:17-23`），避免 system prompt 被工具列表撑爆。Onion 工具量上来后（≥ 20 个），必须引入类似机制。
2. **Onion 可以学 —— plain-text tool call repair**：`tool-call-repair` 包是 OpenClaw 应对"小模型 / 弱模型"漏出 XML/Harmony markers 时的最后防线（`packages/tool-call-repair/src/`），Onion 在 Provider 热插拔场景下必须考虑这种 repair 路径。
3. **Onion 应当避免 —— 工具结果全量塞 prompt**：OpenClaw 用了 30% 上下文 + 16K chars 上限 + 完整 output 旁路到磁盘（`tool-result-truncation.ts`），Onion 必须照做（不能 Aider 化 —— 不截断）。
4. **Onion 应当避免 —— TypeBox schema 双路径校验遗漏**：`packages/llm-core/src/validation.ts:332-373` 的 `validateToolCall` 是必做项（Onion 应当走 TypeBox 强校验 + 错误按 path 格式化），不要用 Pydantic 软校验。
5. **Onion 可以学 —— "unreadable tool 隔离"模式**：`openai-tool-projection.ts:55-128` 让一个坏工具不影响 sibling，Onion 的 tool projection 阶段应当实现同等隔离（避免 1 个 MCP server crash 导致整轮失败）。

---

## 5. 不确定 / 未找到

- **AGENTS.md 字节上限**：源码中未明确找到 `project_doc_max_bytes` 之类的硬截断（与 Codex 的 32 KiB 风格不同），**待确认** —— 可能依赖 plugin / 工作流层默认行为。
- **Plugin 动态热加载**：`api.registerTool` 是 `register` API，但**未确认是否支持运行时新增**（`src/plugin-sdk/tool-plugin.ts:200`）。MCP 工具启动时拉取 `list_tools` 后是静态的，**待运行时增量确认**。
- **Tool execution 自身的"LLM 自动 retry 工具"**：`src/agents/embedded-agent-runner/run-loop.ts` 提供 `MAX_RUN_LOOP_ITERATIONS` 兜底，但**未发现工具执行失败 → 自动 prompt LLM 重发的硬编码路径**，看起来是 model-driven（LLM 看到 tool result.isError=true 自行决定）。
- **沙箱对工具的限制粒度**：file_backend.md 已确认 sandbox 模式（Docker / SSH / OpenShell），但**沙箱下哪些工具被禁用**的精确名单需要进一步查 `src/agents/sandbox/workspace-authority.ts`（未在本调研深读）。
- **Tool-call-argument-repair 与 tool-call-repair 的关系**：`attempt.tool-call-argument-repair.ts` 处理的是 JSON 截断/smart quotes，`tool-call-repair` 包处理的是纯文本泄漏的 tool call 语法，**两者职责边界需要在 dev 文档明确**。
- **Tool result JSON Schema 投影**：仅 OpenAI 有 `projectOpenAITools` 投影层（`packages/ai/src/providers/openai-tool-projection.ts`），**Anthropic 路径的 projection 行为待对齐确认**。

---

**报告完**。源码快照：`git clone --depth 1` @ 2026-07-17；调研日期：2026-07-19。
