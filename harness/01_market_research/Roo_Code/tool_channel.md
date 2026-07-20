# Roo Code — 工具调用（Tool Channel）调研报告

## 0. 智能体一句话定位

> **Roo Code（RooCodeInc/Roo-Code）是 Cline 的"整支开发团队"fork**——在 Cline 基础上引入 **4 个内置 Mode（Architect / Code / Ask / Debug，2025 后加入 Orchestrator）**、**5 层并行 Skills 覆盖矩阵**、**Mode 工具集 + 文件 regex 权限隔离**、并把 Cline 的 **XML 工具协议彻底改造为 provider-native function calling**。VS Code 扩展形态（亦可打包为 CLI）。

## 1. 调研依据

- **源码路径**：`C:\workspace\github\onionagent\harness\01_market_research\clone\Roo-Code\`
- **关键文件**（按调研顺序）：
  1. `src/core/prompts/sections/tool-use.ts`（`getSharedToolUseSection`，4 行：明确"provider-native tool-calling"，**禁用 XML**）
  2. `src/core/prompts/tools/native-tools/index.ts`（`getNativeTools()`，21 个内置工具集中点）
  3. `src/core/prompts/tools/native-tools/converters.ts`（OpenAI ↔ Anthropic 工具格式转换器）
  4. `src/core/prompts/tools/filter-tools-for-mode.ts`（Mode 工具过滤 + alias rename）
  5. `src/core/task/build-tools.ts`（核心：`buildNativeToolsArray` 装配 4 类工具源）
  6. `src/core/assistant-message/NativeToolCallParser.ts`（流式 tool call 解析 + `partial-json` 增量 JSON）
  7. `src/core/tools/BaseTool.ts`（抽象基类 + "XML 不再支持" 错误）
  8. `src/core/tools/validateToolUse.ts`（双层校验：工具名合法性 + Mode 权限 + fileRegex）
  9. `src/core/tools/ToolRepetitionDetector.ts`（3 次重复检测器）
  10. `src/services/skills/SkillsManager.ts`（5 层 + 8 路径 Skills 覆盖 + 文件监听）
  11. `src/services/mcp/McpHub.ts`（MCP 集成 + 双层 mcp.json + project > global 优先级）
  12. `src/services/roo-config/index.ts`（5 路径解析函数族）
  13. `src/shared/tools.ts`（`TOOL_GROUPS`、`ALWAYS_AVAILABLE_TOOLS`、`TOOL_ALIASES`）
  14. `src/core/config/CustomModesManager.ts`（`.roomodes` YAML/JSON 解析 + 文件监听）
  15. `packages/types/src/mode.ts`（5 个 `DEFAULT_MODES` 定义）
  16. `packages/types/src/provider-settings.ts:29`（`DEFAULT_CONSECUTIVE_MISTAKE_LIMIT = 3`）
  17. `src/utils/mcp-name.ts`（`MCP_TOOL_PREFIX="mcp"`，`MCP_TOOL_SEPARATOR="--"`，64-char 截断）
  18. `src/api/providers/anthropic.ts`（`convertOpenAIToolsToAnthropic` 调用证据）
  19. `src/api/transform/stream.ts`（provider-无关的 `ApiStream` 协议）
  20. `src/core/prompts/sections/skills.ts`（`<available_skills>` + `<mandatory_skill_check>` XML 提示）
- **文档 / 仓库**：`README.md`（4 Mode + Custom Mode 介绍）、`.roomodes`（项目级 Custom Mode 7 个示例）、`.roo/skills/*/SKILL.md`（3 个内置 Skill 实例）、`schemas/roomodes.json`（JSON Schema）

## 2. 五个核心问题的回答

### Q1. 工具来源

#### 内置工具（21 个，集中定义在 `getNativeTools()`）

| 类别 | 工具名 | 关键文件 |
|------|--------|---------|
| **文件读** | `read_file`（含 slice / indentation 双模式、`DEFAULT_LINE_LIMIT=2000`） | `native-tools/read_file.ts` |
| | `list_files` / `search_files` / `codebase_search` | `native-tools/list_files.ts` 等 |
| **文件写** | `write_to_file` / `apply_diff`（Cline 风格 SEARCH/REPLACE） | `native-tools/write_to_file.ts` / `apply_diff.ts` |
| | `edit` / `search_replace` / `edit_file` / `apply_patch`（Codex patch 格式，作为 `edit` 组的 opt-in customTools） | `native-tools/edit.ts` 等 |
| | `generate_image`（实验特性） | `native-tools/generate_image.ts` |
| **命令执行** | `execute_command` / `read_command_output` | `native-tools/execute_command.ts` 等 |
| **MCP** | `use_mcp_tool`（legacy 包装：server_name + tool_name + arguments）+ `access_mcp_resource` | `native-tools/mcp_server.ts`（动态生成 `mcp--server--tool` 形式） |
| **Mode 控制** | `switch_mode` / `new_task` | `native-tools/switch_mode.ts` 等 |
| **通用** | `ask_followup_question` / `attempt_completion` / `update_todo_list`（markdown checklist） | `native-tools/ask_followup_question.ts` 等 |
| **Slash / Skills** | `run_slash_command` / `skill`（渐进式披露 SKILL.md） | `native-tools/run_slash_command.ts` / `skill.ts` |
| **Custom 工具**（实验） | `<cwd>/.roo/tools/*.ts` 自定义 | `src/core/task/build-tools.ts:131-138`（`customToolRegistry.loadFromDirectoriesIfStale(toolDirs)`） |

代码证据：`src/core/prompts/tools/native-tools/index.ts:42-65` 一次性返回 21 个工具的 OpenAI `ChatCompletionTool` 数组。

#### MCP 支持

- **支持**：✅（`McpHub` + 标准 `mcpServers` 配置）
- **配置文件路径**（**双层 mcp.json**，与 `file_backend.md` §10.8 完全对齐）：
  - **全局**：`%APPDATA%\Roo-Code\MCP\settings\mcp.json`（Windows）/ `~/.local/share/Roo-Code/MCP/settings/mcp.json`（Linux）/ `~/Documents/Cline/MCP/settings/mcp.json`（macOS，保留 Cline 命名）—— `src/core/webview/ClineProvider.ts` 中 `ensureMcpServersDirectoryExists` 函数
  - **项目级**：`<cwd>/.roo/mcp.json`—— `src/services/mcp/McpHub.ts` 中 `getProjectMcpPath()` 函数
- **优先级**：project > global（`McpHub.getServers()` 内 `serversByName` Map 去重，project 优先）
- **MCP 工具名规范**：`mcp--{sanitizedServer}--{sanitizedTool}`，最长 64 char（Gemini 限制），`src/utils/mcp-name.ts`
- **Singleton 模式**：`src/services/mcp/McpServerManager.ts:21-58`（`getInstance` 一次性创建 + promise-based lock）

#### Agent Skills 支持（**真正的渐进式披露**）

- **支持**：✅（与 Anthropic Agent Skills / `obra/superpowers` SKILL.md 规范兼容）
- **技能目录路径**（**5 层 + 8 路径并行覆盖**，对比 Cline 完全无此概念）：
  - 优先级从低到高（`SkillsManager.getSkillsDirectories()`，`src/services/skills/SkillsManager.ts:391-432`）：
    1. `<global>/.agents/skills` —— 跨 IDE 共享（与 opencode / Claude Code / Gemini CLI 跨工具协议对齐）
    2. `<global>/.agents/skills-<mode>` —— 同上 + mode 限定
    3. `<project>/.agents/skills`
    4. `<project>/.agents/skills-<mode>`
    5. `<global>/.roo/skills`
    6. `<global>/.roo/skills-<mode>`
    7. `<project>/.roo/skills`
    8. `<project>/.roo/skills-<mode>`（**最高优先**）
- **SKILL.md frontmatter 规范**（`SkillsManager.loadSkillMetadata`）：
  - 必填 `name`（必须匹配目录名）、`description`（1-1024 字符）
  - 可选 `modeSlugs: [code, debug]`（frontmatter 方式指定适用 mode，新格式）
  - 可选 `mode: <single>`（遗留单 mode 方式，向后兼容）
  - `skills-<mode>/` 目录命名（遗留目录方式）
- **强制 Skill 检查**（`src/core/prompts/sections/skills.ts:42-78`）：模型每次响应前必须做 skill 适用性检查，未匹配则不允许调用 skill 工具（`<mandatory_skill_check>` 标签）
- **progressive disclosure**：仅暴露 `name + description + path` 给模型；只有调用 `skill` 工具时才读取完整 `SKILL.md` 内容（`resolveSkillContentForMode`）
- **支持 symlink**：`SkillsManager.scanSkillsDirectory` 解析 `realpath`（`.roo/skills` 或 skill 子目录可作为 symlink）
- **运行时热更新**：`setupFileWatchers` 用 `vscode.workspace.createFileSystemWatcher` 监听所有 8 路径下的 `**/SKILL.md` 变更

#### 其他工具类型

- **Custom Tools（实验）**：`experiments.customTools` 启用时，从 `<global>/.roo/tools/` + `<cwd>/.roo/tools/` 扫描用户编写的工具（`packages/core/src/custom-tools/`），用 `customToolRegistry` 注册
- **Slash Commands**：`.roo/commands/*.md`（如 `.roo/commands/commit.md`），通过 `run_slash_command` 工具调用
- **Rules（不是工具，但被加载进 system prompt）**：`.roo/rules/*.md` + `.roo/rules-<mode>/*.md`（全局 + 项目级 + mode 限定）

### Q2. 工具列表的生成、传递、格式

#### 生成方式

**集中装配函数** `buildNativeToolsArray`（`src/core/task/build-tools.ts:62-74`）按以下顺序合并 4 类源：

1. **内置工具**（21 个）→ `getNativeTools({ supportsImages })`
2. **Mode 过滤** → `filterNativeToolsForMode(nativeTools, mode, customModes, experiments, codeIndexManager, filterSettings, mcpHub)`
3. **MCP 工具** → `getMcpServerTools(mcpHub)`（动态连接 + dedupe by name）
4. **MCP Mode 过滤** → `filterMcpToolsForMode`
5. **Custom Tools**（可选）→ `customToolRegistry.loadFromDirectoriesIfStale([<global>/.roo/tools, <cwd>/.roo/tools])` → `customToolRegistry.getAllSerialized()`

最终：`[...filteredNativeTools, ...filteredMcpTools, ...nativeCustomTools]`。

**Mode 过滤的具体规则**（`filter-tools-for-mode.ts:265-339`）：
- 通过 `getToolsForMode(modeConfig.groups)` 计算该 mode 允许的工具集
- 多个 conditional 排除：`codebase_search`（需 code index 已配置）、`update_todo_list`（todoListEnabled=false）、`generate_image`（需 imageGeneration 实验）、`run_slash_command`（需 runSlashCommand 实验）、`access_mcp_resource`（无 MCP 资源时）、`disabledTools` 用户显式禁用
- **alias rename**：`applyModelToolCustomization` 允许模型用 `modelInfo.includedTools` 中的别名（如 `edit_file`）替代规范名（如 `edit`），并用 `RENAMED_TOOL_CACHE` 缓存避免重复分配

#### 传递方式（**provider-无关**）

- **Provider 中间层架构**：`src/api/transform/stream.ts` 定义统一的 `ApiStream` 协议（`ApiStreamTextChunk` / `ApiStreamToolCallStartChunk` / `ApiStreamToolCallDeltaChunk` / `ApiStreamToolCallEndChunk` / `ApiStreamUsageChunk` / `ApiStreamError` 等）
- 35+ 个 provider（OpenAI / Anthropic / Bedrock / Vertex / Gemini / OpenRouter / 国产 GLM/Qwen/MiniMax/Moonshot 等）各自把原生 stream 转换为 `ApiStream`
- Task.ts 只处理一种格式

#### 实际片段（OpenAI 原生 JSON 格式，**非 XML**）

```typescript
// src/core/prompts/tools/native-tools/apply_diff.ts:21-41
{
  type: "function",
  function: {
    name: "apply_diff",
    description: "Apply precise, targeted modifications to an existing file using one or more search/replace blocks...",
    parameters: {
      type: "object",
      properties: {
        path: { type: "string", description: "The path of the file to modify, relative to the current workspace directory." },
        diff: { type: "string", description: "A string containing one or more search/replace blocks..." },
      },
      required: ["path", "diff"],
      additionalProperties: false,
    },
  },
} satisfies OpenAI.Chat.ChatCompletionTool
```

```typescript
// src/core/prompts/tools/native-tools/skill.ts:16-31
{
  type: "function",
  function: {
    name: "skill",
    description: "Load and execute a skill by name. Skills provide specialized instructions for common tasks...",
    strict: true,
    parameters: {
      type: "object",
      properties: {
        skill: { type: "string", description: "Name of the skill to load..." },
        args: { type: ["string", "null"], description: "Optional context or arguments to pass to the skill" },
      },
      required: ["skill", "args"],
      additionalProperties: false,
    },
  },
} satisfies OpenAI.Chat.ChatCompletionTool
```

#### 格式：**JSON（OpenAI ChatCompletionTool），禁用 XML**

**对比 Cline 的重大变化**——Cline 早期用 XML 工具协议（`<read_file>...</read_file>`），Roo Code 彻底抛弃：

```typescript
// src/core/prompts/sections/tool-use.ts（全部内容，4 行）
export function getSharedToolUseSection(): string {
  return `====
TOOL USE
You have access to a set of tools that are executed upon the user's approval.
Use the provider-native tool-calling mechanism.
Do not include XML markup or examples.
You must call at least one tool per assistant response.
Prefer calling as many tools as are reasonably needed in a single response
to reduce back-and-forth and complete tasks faster.`
}
```

```typescript
// src/core/tools/BaseTool.ts:124-134 —— 显式拒绝 XML
if (paramsText.includes("<") && paramsText.includes(">")) {
  throw new Error(
    "XML tool calls are no longer supported. Use native tool calling (nativeArgs) instead.",
  )
}
```

**system prompt 中没有"工具示例 + 提示词描述工具"**（非 prompt-as-tool），工具描述完全由 `ChatCompletionTool.function.description` 字段承载。

#### 是否 prompt-as-tool

**否**——工具描述 100% 走 `tools` 参数（function calling 协议），system prompt 只指引"用 provider-native tool-calling"。

#### Anthropic 转换证据

`src/api/providers/anthropic.ts` 用 `convertOpenAIToolsToAnthropic(metadata?.tools ?? [])` 把 OpenAI 格式 tools 转 Anthropic（`{name, description, input_schema}`）后传给 `messages.create({ stream: true, ...nativeToolParams })`。`tool_choice` 也单独转换（`convertOpenAIToolChoiceToAnthropic`），含 `disable_parallel_tool_use` 支持。

#### 动态刷新

**是**——MCP 工具（`McpHub.getServers()`）、Skills（`SkillsManager.discoverSkills()`）、Custom Tools（`customToolRegistry.loadFromDirectoriesIfStale`）都是**运行时动态**获取。但原生 21 个工具是启动时静态加载，模式切换时重新过滤。

### Q3. 工具调用指令的解析、错误修复、准确性

#### 解析方式：**双层流式解析**

1. **原始 chunk 层**：`NativeToolCallParser.processRawChunk` 处理 `tool_call_partial` 事件，按 `index` 跟踪，发出 `tool_call_start` / `tool_call_delta` / `tool_call_end` 三种事件
2. **参数累积层**：`processStreamingChunk(id, chunk)` 把 JSON 字符串增量累积，用 **`partial-json` 库**（`import { parseJSON } from "partial-json"`，`NativeToolCallParser.ts:1`）提取不完整 JSON 的部分值——即使 JSON 还没闭合也能立即得到 `path: "src/in"` 这种部分值，用于实时 UI 预览
3. **MCP 工具特例**：动态 MCP 工具名以 `mcp--` 开头，`processStreamingChunk` 在 MCP 情况下**不返回 partial**，等待完整（避免提前误触发）

```typescript
// src/core/assistant-message/NativeToolCallParser.ts:243-279
public static processStreamingChunk(id: string, chunk: string): ToolUse | null {
  const toolCall = this.streamingToolCalls.get(id)
  if (!toolCall) return null
  toolCall.argumentsAccumulator += chunk
  // For dynamic MCP tools, we don't return partial updates - wait for final
  const mcpPrefix = MCP_TOOL_PREFIX + MCP_TOOL_SEPARATOR
  if (toolCall.name.startsWith(mcpPrefix)) {
    return null
  }
  // Parse whatever we can from the incomplete JSON!
  try {
    const partialArgs = parseJSON(toolCall.argumentsAccumulator)
    const resolvedName = resolveToolAlias(toolCall.name) as ToolName
    return this.createPartialToolUse(toolCall.id, resolvedName, partialArgs || {}, true, ...)
  } catch {
    // Even partial-json-parser can fail on severely malformed JSON
    return null  // wait for next chunk
  }
}
```

#### 错误修复机制

1. **重复 tool_call 防御**（`Task.ts` 流处理）：`streamingToolCallIndices` 集合去重——`tool_call_start` 重复时直接 `continue` 并 warn（防止流重连 / API quirk 引起的 duplicate ID 触发 400 "tool_use ids must be unique"）
2. **Pre-flight 去重**：保存到 API history 前用 `seenToolUseIds` 集合跳过重复
3. **`sanitizeToolUseId`**：每个 tool_use_id 在加入 API 请求前做 sanitize（处理 Anthropic 64-char 限制、特殊字符）
4. **`flushPendingToolResultsToHistory`**：等待 `assistantMessageSavedToHistory=true`（最多 30s）后再 flush tool_result，避免 tool_result 出现在 tool_use 之前（400 "unexpected `tool_use_id` found in `tool_result` blocks"）
5. **`new_task` 隔离**：与 new_task 同 turn 的其他工具被截断并注入错误 tool_result（`This tool was not executed because new_task was called in the same message turn`）
6. **路径稳定检测**（`BaseTool.hasPathStabilized`）：`partial-json` 可能在 chunk 边界截断字符串（如 `src/ind` → `src/inde`），`handlePartial` 收到连续两次相同 path 才视为稳定，避免显示截断路径

#### 准确性保证（**多层校验**）

1. **`isValidToolName`**（`validateToolUse.ts:17-30`）：工具名必须在 `validToolNames` 集合内、或是 `customToolRegistry` 注册、或是 `mcp_` 前缀
2. **`isToolAllowedForMode`**（`validateToolUse.ts:121-208`）：检查 mode 的 groups 是否包含该工具 + **fileRegex 严格校验**（edit 组特别严，对 `apply_patch` 还提取所有文件路径逐一校验）
3. **`required` + `additionalProperties: false`**：OpenAI strict mode + 必填参数，schema 校验在 API 端完成
4. **`consecutiveMistakeCount`**（Task.ts 字段）：每次工具错误（缺参数、不允许等）累加 1
5. **`ToolRepetitionDetector`**（`ToolRepetitionDetector.ts`）：**3 次完全相同的连续工具调用** → 停止执行并询问用户（`"mistake_limit_reached"`，防止 AI 死循环）

#### 重试上限

- **`DEFAULT_CONSECUTIVE_MISTAKE_LIMIT = 3`**（`packages/types/src/provider-settings.ts:29`）
- 触发时 `Task.ts` 用 `ask("mistake_limit_reached", ...)` 询问用户，由用户决定继续 / 改方向
- **OR 关系**：`toolRepetitionDetector`（同工具重复 3 次）+ `consecutiveMistakeCount`（连续错误 3 次）共享同一上限
- **`consecutiveMistakeCountForApplyDiff` / `consecutiveMistakeCountForEditFile`**（`Map<string, number>`）：per-tool 错误计数（与全局计数并行）
- **`consecutiveNoToolUseCount`**：模型返回 0 工具调用的连续计数（防"忘记调工具"）

### Q4. 工具执行结果回传

#### 回传方式：**Anthropic 协议为主，多 provider 适配**

- **结构**：`Anthropic.ToolResultBlockParam`，由 `Task.pushToolResultToUserContent` 加入 `userMessageContent: (TextBlockParam | ImageBlockParam | ToolResultBlockParam)[]`
- **去重**：相同 `tool_use_id` 重复时 warn 并 skip（防 duplicate）
- **格式**：
  ```typescript
  {
    type: "tool_result",
    tool_use_id: string,  // 对应 assistant 的 tool_use.id
    content: string | Array<Anthropic.TextBlockParam | Anthropic.ImageBlockParam>,
    is_error?: boolean,
  }
  ```

#### 格式：**JSON 字符串为主，结构化结果走 Anthropic blocks**

- **简单文本结果**：`pushToolResult(string)` → 直接作为 `tool_result.content` 的 string
- **结构化结果**（如 `formatResponse.toolResult(text, images)`，`src/core/prompts/responses.ts:111-122`）：
  - 有 image → `[TextBlockParam, ...ImageBlockParam]`
  - 无 image → `string`
- **错误响应**：JSON 字符串（`{"status": "error", "message": "...", "error": "..."}`）或带类型（`{"type": "access_denied", "path": "..."}`）的拒绝消息
- **示例**（`formatResponse.toolError`、`formatResponse.toolDenied`、`formatResponse.invalidMcpToolArgumentError` 等）

#### 通信协议：**Provider 无关（统一 ApiStream 协议）**

- 内部统一为 `ApiStream` 流（`src/api/transform/stream.ts`）
- 出站时 `Task.recursivelyMakeClineRequests` → `api.createMessage(systemPrompt, messages, metadata)` → 各 provider 转换
- Anthropic provider：`convertOpenAIToolsToAnthropic` + `convertOpenAIToolChoiceToAnthropic`（`src/api/providers/anthropic.ts`）
- OpenAI provider：直接传 `tools` + `tool_choice` + `parallel_tool_calls`

#### 大结果处理：**直接传 / 截断 / 分块，三种策略并存**

1. **图片**：直接转 `Anthropic.ImageBlockParam` 嵌入（`formatResponse.toolResult(text, images)`，`responses.ts:111-122`）—— "Placing images after text leads to better results"
2. **大文本/列表截断**（`responses.ts:155-160`）：`if (didHitLimit)` 追加 `(File list truncated. Use list_files on specific subdirectories if you need to explore further.)`
3. **`read_file` 工具自带截断**（`native-tools/read_file.ts:13-15`）：
   - `DEFAULT_LINE_LIMIT = 2000`（Codex 启发）
   - `MAX_LINE_LENGTH = 2000`（单行截断）
   - slice / indentation 双模式
4. **Context overflow**（`Task.ts` `contextWindowExceeded` handler）：自动触发 `manageContext` → condense 摘要 + sliding window 截断（保留 75% conversation）
5. **MCP 图片结果**（隐含）：MCP server 可返回 image content，Roo Code 透传为 `ImageBlockParam`

### Q5. File Backend 是否为工具调用做了适配

#### 工具配置目录/文件清单（**5 层 + 8 路径并行**）

| 层 | 路径（模式） | 工具类型 | 优先级 |
|---|------|--------|------|
| 0 | `~/.agents/skills[-<mode>]/` | Skills（跨 IDE 共享） | 最低 |
| 0 | `~/.agents/mcp.json` | MCP（隐含，无显式 `getGlobalAgentsMcpPath`） | - |
| 1 | `~/.roo/skills[-<mode>]/` | Skills（Roo 专属） | 中 |
| 1 | `~/.roo/rules[-<mode>]/` | Rules（注入 system prompt） | 中 |
| 1 | `~/.roo/commands/` | Slash Commands | 中 |
| 1 | `~/.roo/tools/`（实验） | Custom Tools | 中 |
| 1 | `%APPDATA%\Roo-Code\MCP\settings\mcp.json`（Windows） | MCP 全局 | 中 |
| 2 | `<cwd>/.roo/skills[-<mode>]/` | Skills 项目级 | 高 |
| 2 | `<cwd>/.roo/rules[-<mode>]/` | Rules 项目级 | 高 |
| 2 | `<cwd>/.roo/commands/` | Slash Commands 项目级 | 高 |
| 2 | `<cwd>/.roo/tools/`（实验） | Custom Tools 项目级 | 高 |
| 2 | `<cwd>/.roo/mcp.json` | MCP 项目级 | 高 |
| 2 | `<cwd>/.roomodes`（YAML/JSON） | Custom Modes | 高 |
| 3 | `<cwd>/subdir/.roo/...`（monorepo） | 通过 `discoverSubfolderRooDirectories` 用 ripgrep 发现 | 最高 |
| - | `<cwd>/.rooignore` | 写保护/忽略白名单（`RooIgnoreController` + `RooProtectedController`） | - |

#### 加载代码

- **Skills 路径枚举**：`src/services/skills/SkillsManager.ts:391-432`（`getSkillsDirectories`）—— 显式列出 8 个 `(dir, source, mode)` 元组
- **MCP 路径**：`src/services/mcp/McpHub.ts:739-754`（`getMcpSettingsFilePath` + `getProjectMcpPath`）
- **路径解析函数族**：`src/services/roo-config/index.ts`
  - `getGlobalRooDirectory()` → `~/.roo`
  - `getGlobalAgentsDirectory()` → `~/.agents`（**首次出现**于本批 20 个项目）
  - `getProjectRooDirectoryForCwd(cwd)` → `<cwd>/.roo`
  - `getProjectAgentsDirectoryForCwd(cwd)` → `<cwd>/.agents`（**首次出现**）
  - `getRooDirectoriesForCwd(cwd)` → `[global, project]`
  - `getAllRooDirectoriesForCwd(cwd)` → `[global, project, ...subfolders]`
  - `discoverSubfolderRooDirectories(cwd)` → ripgrep 扫 monorepo
  - `loadConfiguration(relativePath, cwd)` → `{global, project, merged}` 合并两个 `.roo/<path>` 文件
- **Custom Modes 加载**：`src/core/config/CustomModesManager.ts:96-117`（`getWorkspaceRoomodes`）+ 合并 settings + .roomodes（后者优先）

#### 全局 vs 项目级 vs 两者

**两者并存 + 4 级优先级**：
1. `<global>/.agents/...`（最低）
2. `<global>/.roo/...`
3. `<project>/.agents/...`
4. `<project>/.roo/...`
+ Subfolder monorepo 自动发现
+ **同 source 内 mode 限定 > generic**（`SkillsManager.shouldOverrideSkill`：`newHasModes && !existingHasModes → true`）
+ **同 source 同 mode 限定**：first wins（`Map.set` 覆盖语义）

#### 与 `standard/file_backend.md` 对照

| 标准条款 | Roo Code 实践 | 一致性 |
|----------|------------|------|
| §1.1 固定用户属主目录 + env 单一覆盖 | `customStoragePath`（VSCode 配置）覆盖默认 `%APPDATA%/Roo-Code` 或 `~/.roo-code/mcp` fallback | ✅（env 改为 VSCode 配置项，效果等价） |
| §1.3 AGENTS.md 向上扫描到 .git 边界 | **部分支持**：`.roo/` 子目录递归（`discoverSubfolderRooDirectories`），但不直接读 `AGENTS.md`（注：本项目**有** AGENTS.md，是给 repo agent 看，不是 Roo 自己的加载目标） | ⚠ 部分 |
| §1.4 secrets 独立文件 + 0o600 | `auth.json` 在 settings 目录，未显式 chmod 0o600（`ensureMcpServersDirectoryExists` 不设权限） | ⚠ 不一致 |
| §2.1 单一 env 覆盖点 | **反例**：MCP 路径有 3 套平台默认值（`%APPDATA%\Roo-Code\MCP` / `~/Documents/Cline/MCP` / `~/.local/share/Roo-Code/MCP`），通过 VSCode `customStoragePath` 配置项覆盖 | ⚠ 单点通过配置项而非 env |
| §2.5 跟随 cwd vs 固定 home | **混合**：MCP 走固定 home（`%APPDATA%`），Skills/Rules/Custom Modes 走 `<cwd>/.roo/` | ✅ 合理分工 |
| §3.1 严格三层分离 | **远超三层**：5 层 × 3 类（skills / rules / mcp）+ subfolder | ✅ 优秀 |
| §3.4 强结构化 | 强结构化（每个能力有独立子目录） | ✅ |
| §5.4 LLM 不可读凭证白名单 | 无显式 `_ROOT_CREDENTIAL_DIRS`（**反例**，仅靠工具层不暴露） | ❌ |
| §8.3 atomic write | `temp+rename` 部分实现（`getTaskDirectoryPath` 用 `fs.mkdir recursive`） | ⚠ 部分 |
| §9.4 AGENTS.md 字节上限 | 读 `custom-instructions.md` 但无显式 32 KiB 限制 | ❌ |
| §10.8 MCP 协议支持 | 双层 mcp.json（`%APPDATA%\Roo-Code\MCP\settings\mcp.json` + `<cwd>/.roo/mcp.json`） | ✅ 优秀 |
| §3.8 Bootstrap 种子文件 | 无显式 seed 9 个文件 | ❌（Cline 也不做） |
| **独占创新** | **`.agents/skills` 跨 IDE 共享层**（与 opencode / Claude Code / Gemini CLI 等其他工具协作） | 🆕 行业首个 |

## 3. 关键代码片段（最有说服力的 5 段）

### 片段 1：纯 JSON function calling，禁用 XML（**对比 Cline 最大变化**）

```typescript
// src/core/prompts/sections/tool-use.ts
export function getSharedToolUseSection(): string {
  return `====
TOOL USE
You have access to a set of tools that are executed upon the user's approval.
Use the provider-native tool-calling mechanism.
Do not include XML markup or examples.
You must call at least one tool per assistant response.
Prefer calling as many tools as are reasonably needed in a single response
to reduce back-and-forth and complete tasks faster.`
}
```

### 片段 2：partial-json 流式增量解析（**准确性核心**）

```typescript
// src/core/assistant-message/NativeToolCallParser.ts:243-279
public static processStreamingChunk(id: string, chunk: string): ToolUse | null {
  const toolCall = this.streamingToolCalls.get(id)
  if (!toolCall) return null
  toolCall.argumentsAccumulator += chunk

  // For dynamic MCP tools, we don't return partial updates - wait for final
  const mcpPrefix = MCP_TOOL_PREFIX + MCP_TOOL_SEPARATOR
  if (toolCall.name.startsWith(mcpPrefix)) {
    return null
  }

  // Parse whatever we can from the incomplete JSON!
  // partial-json-parser extracts partial values (strings, arrays, objects) immediately
  try {
    const partialArgs = parseJSON(toolCall.argumentsAccumulator)
    const resolvedName = resolveToolAlias(toolCall.name) as ToolName
    return this.createPartialToolUse(toolCall.id, resolvedName, partialArgs || {}, true, ...)
  } catch {
    // Even partial-json-parser can fail on severely malformed JSON
    return null  // wait for next chunk
  }
}
```

### 片段 3：21 个工具 + 5 层 8 路径 Skills 集中装配

```typescript
// src/core/prompts/tools/native-tools/index.ts:42-65
export function getNativeTools(options: NativeToolsOptions = {}): OpenAI.Chat.ChatCompletionTool[] {
  const { supportsImages = false } = options
  const readFileOptions: ReadFileToolOptions = { supportsImages }
  return [
    accessMcpResource, apply_diff, applyPatch, askFollowupQuestion, attemptCompletion,
    codebaseSearch, executeCommand, generateImage, listFiles, newTask,
    readCommandOutput, createReadFileTool(readFileOptions), runSlashCommand, skill,
    searchReplace, edit_file, editTool, searchFiles, switchMode, updateTodoList, writeToFile,
  ] satisfies OpenAI.Chat.ChatCompletionTool[]
}

// src/core/task/build-tools.ts:108-115
// 4 类源合并
const filteredTools = [...filteredNativeTools, ...filteredMcpTools, ...nativeCustomTools]

// src/services/skills/SkillsManager.ts:391-432 —— 8 路径优先级
dirs.push({ dir: path.join(globalAgentsDir, "skills"), source: "global" })
for (const mode of modesList) dirs.push({ dir: path.join(globalAgentsDir, `skills-${mode}`), source: "global", mode })
// ... <project>/.agents/...
// ... <global>/.roo/...
// ... <project>/.roo/... 最高
```

### 片段 4：Mode 工具集定义（5 个 DEFAULT_MODES + fileRegex 严格隔离）

```typescript
// packages/types/src/mode.ts:168-225（节选 architect + code）
{
  slug: "architect",
  name: "🏗️ Architect",
  groups: ["read", ["edit", { fileRegex: "\\.md$", description: "Markdown files only" }], "mcp"],
  // ... 无 execute_command、switch_mode
},
{ slug: "code", name: "💻 Code", groups: ["read", "edit", "command", "mcp"] },  // 全工具
{ slug: "ask", name: "❓ Ask", groups: ["read", "mcp"] },                          // 只读
{ slug: "debug", name: "🪲 Debug", groups: ["read", "edit", "command", "mcp"] },
{ slug: "orchestrator", name: "🪃 Orchestrator", groups: [] },                     // 只能 new_task 委派
```

```typescript
// src/shared/tools.ts:225-244
export const TOOL_GROUPS: Record<ToolGroup, ToolGroupConfig> = {
  read:    { tools: ["read_file", "search_files", "list_files", "codebase_search"] },
  edit:    { tools: ["apply_diff", "write_to_file", "generate_image"],
             customTools: ["edit", "search_replace", "edit_file", "apply_patch"] },
  command: { tools: ["execute_command", "read_command_output"] },
  mcp:     { tools: ["use_mcp_tool", "access_mcp_resource"] },
  modes:   { tools: ["switch_mode", "new_task"], alwaysAvailable: true },
}
export const ALWAYS_AVAILABLE_TOOLS: ToolName[] = [
  "ask_followup_question", "attempt_completion", "switch_mode", "new_task",
  "update_todo_list", "run_slash_command", "skill",
]
```

### 片段 5：3 次错误上限 + 工具重复检测

```typescript
// packages/types/src/provider-settings.ts:29
export const DEFAULT_CONSECUTIVE_MISTAKE_LIMIT = 3

// src/core/tools/ToolRepetitionDetector.ts:29-31
constructor(limit: number = 3) { this.consecutiveIdenticalToolCallLimit = limit }

// src/core/tools/BaseTool.ts:124-134 —— XML 显式拒绝
if (paramsText.includes("<") && paramsText.includes(">")) {
  throw new Error(
    "XML tool calls are no longer supported. Use native tool calling (nativeArgs) instead.",
  )
}
```

## 4. 与 Onion Agent 设计的关联

1. **Onion 可学 Roo Code：纯 function calling + 5 层 + 8 路径 Skills 并行**
   - 抛弃 XML 工具协议（"Do not include XML markup"）是 2025 后的行业共识（OpenAI / Anthropic / Google 都用 provider-native）
   - 8 路径 Skills 覆盖矩阵是 **5 层并行的极致**——`~/.agents/` + `~/.roo/` + `<cwd>/.agents/` + `<cwd>/.roo/` × generic/mode-specific = 8 路径，且 project > global、.roo > .agents、mode-specific > generic 三重优先级
   - **Onion 可以**用 `~/.onion/skills/` + `<repo>/.onion/skills/` + `~/.agents/skills/` 三层（向 Roo 学习 5 层 + 跨 IDE 共享，但 Onion 是单一产品不需要这么复杂）
   - **Onion 必须警惕**：Roo 没有显式 env 覆盖点（用 VSCode 配置项替代），Onion P0 必须坚持 `ONION_HOME` env（参照 `file_backend.md` §2.1）

2. **Onion 可学 Roo Code：Mode 工具集 + fileRegex 权限隔离**
   - 5 个 DEFAULT_MODES（architect / code / ask / debug / orchestrator）+ 6 个 tool groups（read / edit / command / mcp / modes / browser）+ fileRegex 限制（architect 只能改 .md）
   - 适合"洋葱架构"的"工具按角色分层"——每层（user / orchestrator / sub-agent）有自己的工具集
   - **Onion 可以**为 3 个洋葱层（system / plan / act）分配不同 tool groups，例如 plan 层只有 read + mcp，act 层有 read + edit + command + mcp

3. **Onion 必须避免 Roo Code 的反例：MCP 平台路径混乱**
   - 3 套 MCP 默认路径（`%APPDATA%\Roo-Code\MCP` / `~/Documents/Cline/MCP` / `~/.local/share/Roo-Code\MCP`）——保留 Cline 命名是历史包袱
   - **Onion 必须**用 `ONION_HOME` 单一 env + `~/.onion/mcp.json` 一处

4. **Onion 可学 Roo Code：`partial-json` 流式增量解析**
   - 工具调用准确性核心——`partial-json` 库能从不完整 JSON 提取部分值
   - **Onion 必须**：用 `partial-json` + `processRawChunk` 三阶段（start / delta / end）+ 路径稳定检测

5. **Onion 可学 Roo Code：3 次错误上限 = `consecutiveMistakeCount` + `ToolRepetitionDetector`**
   - "连续 3 次相同工具调用" / "连续 3 次错误" → 询问用户（`mistake_limit_reached`）
   - **Onion 可以**直接复用这个机制作为 `session.json` 中的 `state.consecutive_mistake_count` 字段

## 5. 不确定 / 未找到

1. **未找到 Roo Code 的"非 IDE 形态" CLI 工具调用完整路径**（README 提到 CLI mode 但本次未深入 `/cli` 子项目调研），主要调研集中在 VSCode 扩展端
2. **`src/core/prompts/tools/native-tools/apply_patch.ts`** 的具体 `inputSchema` 形态未深入展开（仅 `apply_diff`/`attempt_completion`/`update_todo_list`/`access_mcp_resource` 等已展示）
3. **CLI 模式下 `<cwd>/.roo/` 是否仍为优先路径**未验证（`ROO_CLI_RUNTIME === "1"` env 在 `ExecuteCommandTool` 中被检测，但完整 CLI 路径解析未调研）
4. **实验特性 `customTools`** 的用户文档 / 示例工程未在仓库中（`packages/core/src/custom-tools/` 目录存在但未深入展开）
5. **`<global>/.agents/mcp.json`** 是否被 Roo Code 显式读取——`getGlobalAgentsDirectory()` 函数存在但未在 `McpHub.getMcpSettingsFilePath()` 找到对应使用，**仅 SkillsManager 用到 `.agents`**，MCP 仍走 `~/.roo/` 下的 platform-specific 路径
6. **`packages/core/src/custom-tools/`** 的格式（用户编写自定义工具的具体文件结构、注册表 API）未深入展开
7. **monorepo subfolder `.roo/` 在多 SkillManager 实例下的行为**（每个 provider 一个 SkillsManager，subfolder 会不会重复发现）未在源码中显式约束——仅在 `discoverSubfolderRooDirectories` 注释中提到 "Does not include the root .roo directory"

---

**报告完。** 数据来源：Roo-Code 仓库 `git clone --depth 1` 快照（2026-07-13）。
