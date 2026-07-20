# Continue — 工具调用（Tool Channel）调研报告

> 调研对象：[continuedev/continue](https://github.com/continuedev/continue) `@ v1.3.40`（`core/package.json` 声明）
> 调研范围：`core/tools/`、`core/llm/`、`core/config/markdown/`、`core/context/mcp/`、`packages/config-yaml/src/schemas/`、`packages/config-yaml/src/mcp/`
> 调研日期：2026-07

---

## 0. 智能体一句话定位

Continue 是**开源 IDE 编码 Agent**（VS Code / JetBrains 插件 + `cn` CLI），在 IDE 侧边栏 / TUI 中提供 Chat / Edit / Apply / Agent 四种工作模式；工具调用走 **OpenAI `tool_calls` + Anthropic `tool_use` 双协议**，**对不支持原生 tool calling 的模型有"XML/代码块"格式 prompt-as-tool fallback**。

---

## 1. 调研依据

- 源码路径：`C:\workspace\github\onionagent\harness\01_market_research\clone\continue\`
- 关键文件（带行号）：
  - 工具定义总入口：`core/tools/index.ts:6-53`
  - 内置工具名枚举 + 路由：`core/tools/builtIn.ts:1-26`、`core/tools/callTool.ts:191-227`
  - 参数解析（容错 + 类型强转）：`core/tools/parseArgs.ts:3-22`（`safeParseToolCallArgs`）、`core/tools/parseArgs.ts:25-58`（`coerceArgsToSchema`）
  - 工具覆盖（按 config 重写 description / 禁用）：`core/tools/applyToolOverrides.ts:8-69`
  - 工具元数据 schema：`packages/config-yaml/src/schemas/index.ts:241-243`、`packages/config-yaml/src/schemas/models.ts:96-114`（`toolOverrideSchema`）
  - 流式 `delta.tool_calls` 解析：`core/llm/openaiTypeConverters.ts:357-389`（`fromChatCompletionChunk`）
  - Anthropic 流式 `input_json_delta` 解析：`core/llm/llms/Anthropic.ts:366-378`
  - Anthropic `tool_result` 回传块构造：`core/llm/llms/Anthropic.ts:153-163`（`getContentBlocksFromChatMessage` 中 `role: "tool"` 分支）
  - 主循环 + tools 上游传递：`core/llm/index.ts:1106-1143`（`applyToolOverrides` + `streamChat`）
  - prompt-as-tool fallback（codeblocks 框架）：`core/tools/systemMessageTools/toolCodeblocks/index.ts:5-44`、`core/tools/systemMessageTools/buildToolsSystemMessage.ts:12-66`
  - 工具流式拦截 / 解析：`core/tools/systemMessageTools/interceptSystemToolCalls.ts:23-60`、`core/tools/systemMessageTools/detectToolCallStart.ts:3-25`
  - Agent Skills 加载：`core/config/markdown/loadMarkdownSkills.ts:21-91`
  - Agent Skills 工具定义：`core/tools/definitions/readSkill.ts:8-32`
  - 规则渐进式披露工具：`core/tools/definitions/requestRule.ts:6-58`
  - MCP Manager（动态加载 + 热重连）：`core/context/mcp/MCPManagerSingleton.ts:60-108`
  - MCP JSON 配置加载（三种格式）：`core/context/mcp/json/loadJsonMcpConfigs.ts:23-187`
  - MCP YAML schema（stdio / sse / http）：`packages/config-yaml/src/schemas/mcp/index.ts:1-46`
  - 大结果截断：`core/tools/implementations/grepSearch.ts:8-130`、`core/tools/implementations/fetchUrlContent.ts:5-37`
  - `role: "tool"` 回传类型：`core/index.d.ts:374-380`（`ToolResultChatMessage`）
- README / 文档：`core/tools/builtIn.ts` 注释、`core/tools/parseArgs.ts` 注释、`docs/customize/deep-dives/configuration.mdx`

---

## 2. 五个核心问题的回答

### Q1. 工具来源

**内置工具（19 个，由 `core/tools/builtIn.ts:1-20` 声明）：**

| 工具名 | 功能 | 路由位置 |
|---|---|---|
| `read_file` | 读文件全文 | `core/tools/callTool.ts:194-196` |
| `read_file_range` | 读文件指定行号范围（experimental） | `callTool.ts:197` |
| `create_new_file` | 新建文件 | `callTool.ts:198` |
| `edit_existing_file` | 整文件重写式编辑（**客户端实现**） | `builtIn.ts:23`（`CLIENT_TOOLS_IMPLS`） |
| `single_find_and_replace` | 单次 find/replace（**客户端实现**） | `builtIn.ts:23` |
| `multi_edit` | 多次编辑（agent 模型推荐） | `tools/index.ts:42-46` |
| `read_currently_open_file` | 读 IDE 当前打开文件 | `callTool.ts:204` |
| `run_terminal_command` | 终端命令 | `callTool.ts:201` |
| `grep_search` | ripgrep 搜索 | `callTool.ts:199` |
| `file_glob_search` | glob 模式列文件 | `callTool.ts:200` |
| `search_web` | 联网搜索 | `tools/index.ts:27` |
| `fetch_url_content` | 抓取 URL | `callTool.ts:202` |
| `view_diff` | 查看 diff | `callTool.ts:203` |
| `ls` | 列目录 | `callTool.ts:205` |
| `create_rule_block` | 创建规则块 | `callTool.ts:206` |
| `request_rule` | **按需拉取规则**（渐进式披露） | `callTool.ts:207` |
| `codebase` | 代码库语义检索（experimental） | `callTool.ts:209` |
| `read_skill` | **按需读取 skill**（Anthropic Agent Skills 风格） | `callTool.ts:210` |
| `view_repo_map` / `view_subdirectory` | experimental 工具 | `tools/index.ts:32-35` |

**MCP 支持：是**（完整 `modelcontextprotocol/sdk` 集成）

- 配置文件路径（三层）：
  1. **YAML 内嵌**：`config.yaml` 顶层 `mcpServers: [...]` 数组（`packages/config-yaml/src/schemas/index.ts:161, 173`）
  2. **JSON 文件**（Claude Desktop / Claude Code 风格）：`<workspace>/.continue/mcpServers/*.json` + `~/.continue/mcpServers/*.json`（`core/context/mcp/json/loadJsonMcpConfigs.ts:34-50`）
  3. **Marketplace `uses:` + `with:` 引用**（`packages/config-yaml/src/schemas/index.ts:128-138`）
- Schema 支持 stdio / sse / streamable-http 三种 transport（`packages/config-yaml/src/schemas/mcp/index.ts:8-46`）
- **动态刷新**：是，`MCPManagerSingleton.setConnections()` 会 diff 配置变化并自动重连，`setEnabled()` 可运行时启停（`MCPManagerSingleton.ts:38-58, 68-110`）

**Agent Skills 支持：是**（Anthropic Agent Skills 风格）

- 技能目录（三层搜索）：
  1. `<workspace>/.continue/skills/**/*.md`（项目级）
  2. `<workspace>/.claude/skills/**/*.md`（兼容 Claude Skills）
  3. `~/.continue/skills/**/*.md`（全局）
- 文件名约定：必须以 `SKILL.md` 结尾（`loadMarkdownSkills.ts:69-70`）
- Frontmatter：`{ name: string, description: string }`（`loadMarkdownSkills.ts:13-16`）
- **渐进式披露**：`read_skill` 工具默认列出所有 skill 的 name + description，LLM 按需调用 `read_skill(skillName="xxx")` 拉完整内容（`core/tools/definitions/readSkill.ts:21-30`）
- skill 目录下其他文件（除 `SKILL.md`）作为附属资源（`loadMarkdownSkills.ts:78-86`）

**其他工具类型：**

- **HTTP 工具**（`callToolFromUri` 的 `http(s):` 分支）：`core/tools/callTool.ts:38-52`，支持把工具调用路由到任意 HTTP 端点（POST JSON），用于 marketplace/远程工具
- **Context Provider**（独立于工具机制，但概念相邻）：`.continue/config.yaml` 顶层 `context: [...]`（`packages/config-yaml/src/schemas/index.ts:127`），由 `core/context/providers/` 实现，注入上下文但**不进入 tools 列表**
- **Slash Command**（`config.yaml` 顶层 `commands: [...]`）：用户显式调用的命令，不算 LLM 自由调用的工具

---

### Q2. 工具列表的生成、传递、格式

**生成方式**（`core/tools/index.ts:6-53`）：

```ts
// 基础工具（不依赖 config）
export const getBaseToolDefinitions = () => [
  readFileTool, createNewFileTool, runTerminalCommandTool,
  globSearchTool, viewDiffTool, readCurrentlyOpenFileTool,
  lsTool, createRuleBlock, fetchUrlContentTool,
];

// 配置相关工具（需读 rules/skills）
export const getConfigDependentToolDefinitions = async (params) => {
  tools.push(await requestRuleTool(params));   // 需要 rules
  tools.push(await readSkillTool(params));     // 需要 skills
  tools.push(searchWebTool);
  if (enableExperimentalTools) tools.push(...);
  if (isRecommendedAgentModel(modelName))
    tools.push(multiEditTool);
  else
    tools.push(editFileTool, singleFindAndReplaceTool);
  if (!isRemote) tools.push(grepSearchTool);
  return tools;
};
```

- 工具列表**不是启动时一次性加载**，而是**每次 config 加载时按需聚合**：基础工具 9 个 + config 依赖工具（含 read_skill / request_rule） + 客户端/服务端专属工具 + MCP 工具 + rules/skills 工具。
- **动态刷新**：是。每次 `ConfigHandler.loadConfig()` 都重新聚合（`core/llm/index.ts:1106-1120`，`applyToolOverrides` 在 streamChat 入口处再次过滤）。
- 工具选择**与模型能力相关**：`isRecommendedAgentModel()`（`core/llm/toolSupport.ts:490-510`）判断是否是 agent 推荐模型（Claude Sonnet 3.7+ / GPT-5+ / Gemini 2.5+ Pro / Grok 4+），决定走 `multiEdit` 还是 `edit_existing_file` + `single_find_and_replace`。
- **作者在注释中明确承认踩过坑**：`core/tools/index.ts:4` — "I'm writing these as functions because we've messed up 3 TIMES by pushing to const, causing duplicate tool definitions on subsequent config loads."

**传递方式**：双协议

- **OpenAI 协议**：通过 `chat.completions.create({ tools: [...] })` 直接传，`tools: options.tools`（`core/llm/index.ts:962, 1141`）
- **Anthropic 协议**：在 `Anthropic.convertArgs` 中映射为 `tools: options.tools?.map(this.convertToolToAnthropicTool)`，把 OpenAI 风格的 `function.parameters` 重写为 `input_schema`（`core/llm/llms/Anthropic.ts:69`）
- **Cohere / Bedrock / Gemini / VertexAI 等**：各有自己的转换器（`core/llm/llms/*.ts`），全部走 `options.tools` 同一上游入口

**格式：JSON（OpenAI Function Calling 标准格式）**

实际 JSON 片段（`core/tools/definitions/readFile.ts` 经 `getBaseToolDefinitions` 调用产出）：

```json
{
  "type": "function",
  "function": {
    "name": "read_file",
    "description": "Read the contents of a file (or list of files) ... filepath relative to the workspace root",
    "parameters": {
      "type": "object",
      "required": ["filepath"],
      "properties": {
        "filepath": { "type": "string", "description": "..." }
      }
    }
  }
}
```

**Prompt-as-tool fallback：是**

- 触发条件：模型**不支持原生 tool calling**（通过 `PROVIDER_TOOL_SUPPORT` 字典判断，`core/llm/toolSupport.ts:8-260`）
- Fallback 框架在 `core/tools/systemMessageTools/`，**核心是 `SystemMessageToolCodeblocksFramework`**（`core/tools/systemMessageTools/toolCodeblocks/index.ts:5-44`），它用一种**自有的"代码块"格式**注入到 system message（**不是 XML，是 ```tool 围栏**）：

```
```tool
TOOL_NAME: read_file
BEGIN_ARG: filepath
src/index.ts
END_ARG
```
```

- LLM 学会这个格式后输出同样的代码块，**流式拦截器** `interceptSystemToolCalls` 在 assistant 流式 content 中检测 `detectToolCallStart()`（`core/tools/systemMessageTools/detectToolCallStart.ts:3-25`），**把 codeblock 拆成 `toolCalls: [...]` delta** 喂回 LLM loop（`interceptSystemToolCalls.ts:23-60`）
- 工具描述前缀：`generateToolsSystemMessage`（`core/tools/systemMessageTools/buildToolsSystemMessage.ts:12-66`），把 `systemMessageDescription.prefix` 注入到 system message

**config.yaml 的 `tools` 块写法**：

```yaml
# packages/config-yaml/src/schemas/index.ts:241-243
tools:
  - name: my_custom_tool        # 工具名
    description: "..."          # 工具描述
    defaultIcon: ""             # 可选
```

- 顶层 `tools` 数组用于声明**额外**的 context provider / 工具（不是覆盖）—— 实际工具 schema 偏简单，仅 name+description
- **真正的工具覆盖**走 `chatOptions.toolOverrides`（`packages/config-yaml/src/schemas/models.ts:96-114`），按工具名 dict 重写 `description` / `displayTitle` / `wouldLikeTo` / `isCurrently` / `hasAlready` / `systemMessageDescription` 或 `disabled: true`：

```yaml
chatOptions:
  toolOverrides:
    run_terminal_command:
      description: "新描述..."
      disabled: false
```

**动态刷新**：是。配置变化时 `MCPManagerSingleton.setConnections` 重新 diff + 重连（`MCPManagerSingleton.ts:68-110`）；`applyToolOverrides` 每次 `streamChat` 入口处重新应用（`core/llm/index.ts:1106-1120`）。

---

### Q3. 工具调用指令的解析、错误修复、准确性保证

**解析方式（三层）**：

1. **OpenAI 流式增量解析**（主流）：
   - `fromChatCompletionChunk` 解析 `chunk.choices[0].delta.tool_calls` 数组（`core/llm/openaiTypeConverters.ts:357-389`）
   - 每个 delta 提取 `id` / `type` / `function.name` / `function.arguments`，产出 `{ role: "assistant", toolCalls: [...] }`
2. **Anthropic SSE 流式解析**（`core/llm/llms/Anthropic.ts:303-378`）：
   - `content_block_start` 拿 `tool_use.id` + `tool_use.name`
   - `content_block_delta` 的 `input_json_delta` 拿 `partial_json` 增量（**JSON 字符串流式追加，不重组**）
3. **Prompt-as-tool 流式解析**（fallback）：
   - `detectToolCallStart` 在 stream buffer 中检测 `\`\`\`tool\n` 或 `tool_name:` 等起始符
   - `handleToolCallBuffer` 按行 + 按 `BEGIN_ARG/END_ARG` 切分，把每个 arg 攒为完整 JSON 后 `JSON.parse` 一次

**错误修复机制**：

- `safeParseToolCallArgs`（`core/tools/parseArgs.ts:3-22`）：**JSON.parse 失败时返回 `{}` 而不是 throw**，避免 LLM 流式输出半截 JSON 时整个 loop 崩

```ts
// parseArgs.ts:3-22
export function safeParseToolCallArgs(toolCall: ToolCallDelta): Record<string, any> {
  const args = toolCall.function?.arguments;
  if (args && typeof args === "object' && !Array.isArray(args) && Object.keys(args).length > 0) {
    return args;  // 已经是对象
  }
  try {
    return JSON.parse(toolCall.function?.arguments?.trim() || "{}");
  } catch (e) {
    return {};  // 容错：返回空对象
  }
}
```

- `coerceArgsToSchema`（`parseArgs.ts:25-58`）：**按 schema 重新类型强转**。场景：LLM 想创建 `.json` 文件，合法 JSON 字符串 `{"a":1}` 被 deep parse 后变成对象；但 schema 要求 string，于是把它 `JSON.stringify` 回字符串

- 兜底非标准 tool call 收尾（`core/tools/systemMessageTools/interceptSystemToolCalls.ts:32-38`）：流结束但参数不完整时，主动 yield `{"}"` 闭合 delta，避免永久悬挂

- prompt-as-tool "Poor models" 兜底（`core/tools/systemMessageTools/toolCodeblocks/index.ts:7-11`）：`acceptedToolCallStarts` 数组容忍 `\`\`\`tool\n` / `tool_name:` / 大小写不敏感等多种起始

**准确性保证**：

- **Schema 校验**（zod）：`mcpServerSchema` / `toolOverrideSchema` 等都用 zod 严格校验（`packages/config-yaml/src/schemas/mcp/index.ts:31-46`）
- **运行时类型守卫**：`getStringArg` / `getNumberArg` / `getBooleanArg`（`core/tools/parseArgs.ts:60-160`）每个工具在入口强校验，类型不对就 throw，throw 后被 `callTool` 顶层 catch 转为 `errorMessage` 反馈给 LLM（`core/tools/callTool.ts:280-295`）
- **Plan-then-Act 模式**：**没有显式的 Plan 模式**（不像 Cline / Roo Code 那样有 Plan/Act 切换）—— 靠 system message + 工具描述约束

**重试机制**：

- **没有显式 retry 计数器**。错误回流靠 `callTool` 的 catch 把 `errorMessage` 塞进 `errorMessage: string`（`callTool.ts:280-295`），作为下一个 LLM 调用的上下文，由 LLM 自行决定是否重试
- 用户可在 UI 手动"撤销 + 重发"

---

### Q4. 工具执行结果回传

**回传方式**：

- **OpenAI 协议**：通过 `ToolResultChatMessage`（`core/index.d.ts:374-380`）：
  ```ts
  interface ToolResultChatMessage {
    role: "tool";
    content: string;
    toolCallId: string;
    metadata?: Record<string, unknown>;
  }
  ```
  → `core/llm/openaiTypeConverters.ts:152-160` 转 `msg.tool_calls` 反向构造 `assistant` 消息
- **Anthropic 协议**：在 `getContentBlocksFromChatMessage` 的 `role: "tool"` 分支（`core/llm/llms/Anthropic.ts:153-163`）：
  ```ts
  case "tool":
    return [{ type: "tool_result", tool_use_id: message.toolCallId, content: ... }];
  ```
  → 作为 user 消息的一部分追加

**格式：JSON（结构化）**

- 工具结果内部是 `ContextItem[]`（`core/index.d.ts:449-457`）：
  ```ts
  interface ContextItem {
    content: string;
    name: string;
    description: string;
    editing?: boolean;
    editable?: boolean;
    icon?: string;
    uri?: ContextItemUri;
    hidden?: boolean;
  }
  ```
- MCP 工具结果有 type 分发（`core/tools/callTool.ts:155-181`）：`text` / `resource` / 其他 → 各自映射到 `ContextItem` 字段；`isError: true` 时直接 throw 让外层 catch
- 回传给 LLM 时是字符串（`content: string`），不是 `ContextItem` 整体

**通信协议：多协议（Provider 无关）**

- 同一条 `ChatMessage[]` 流式经 `compileChatMessages` + provider-specific 转换器变成 OpenAI / Anthropic / Bedrock / Cohere / Gemini 等不同 wire format
- `toolCallId` 通用，由 `generateOpenAIToolCallId()`（`core/tools/systemMessageTools/systemToolUtils.ts`）生成，**所有 provider 共享同一 ID 体系**

**大结果处理：截断 + 追加 warning**

- `grepSearch` 默认截断 **100 条结果 / 7500 字符**（`core/tools/implementations/grepSearch.ts:8-9, 88-130`），截断时 append 独立 `Truncation warning` ContextItem
- `fetchUrlContent` 默认截断 **20000 字符**（`core/tools/implementations/fetchUrlContent.ts:5, 17-37`），同款 warning
- `isItemTooBig`（`core/core.ts:1191-1207`）：在 IDE 注入前 token-count vs `llm.contextLength - llm.maxTokens`，超大直接拦截，提示用户换模型或换工具
- `countToolsTokens`（`core/llm/countTokens.ts:135`）单独算 tools 列表本身的 token 用量
- 图片：`Anthropic.convertMessageContentToBlocks` 处理 base64 data URL → image block（`Anthropic.ts:99-119`）

---

### Q5. File Backend 是否为工具调用做了适配

**工具配置目录/文件清单**：

| 路径 | 作用 | 加载函数 |
|---|---|---|
| `<workspace>/.continue/mcpServers/*.json` | **项目级** MCP server JSON（多 server 一文件 / 单 server 多文件） | `core/context/mcp/json/loadJsonMcpConfigs.ts:34-50, 122-187` |
| `~/.continue/mcpServers/*.json` | **全局** MCP server JSON | 同上 |
| `config.yaml` 顶层 `mcpServers: [...]` | **YAML 内嵌** MCP server 数组 | `core/config/yaml/loadYaml.ts:369-381` |
| `config.yaml` `chatOptions.toolOverrides` | 工具描述/启用覆盖 | `core/llm/index.ts:1106-1120` + `core/tools/applyToolOverrides.ts` |
| `<workspace>/.continue/skills/SKILL.md` | **项目级** Agent Skills（Anthropic 风格） | `core/config/markdown/loadMarkdownSkills.ts:52-91` |
| `<workspace>/.claude/skills/SKILL.md` | **兼容 Claude Skills** 目录 | `loadMarkdownSkills.ts:21-40` |
| `~/.continue/skills/SKILL.md` | **全局** Agent Skills | 同上 |
| `<workspace>/.continue/rules/*.md` | 项目级 rules（被 `request_rule` 渐进式披露） | `core/config/markdown/loadMarkdownRules.ts:11-86` |
| `~/.continue/rules/*.md` | 全局 rules | 同上 |
| `<workspace>/AGENTS.md` / `AGENT.md` / `CLAUDE.md` | **项目级** 根 agent 文件（自动 alwaysApply） | `loadMarkdownRules.ts:10, 18-44` |
| `~/.continue/permissions.yaml` | TUI 模式"approve + don't ask again"持久授权 | `docs/cli/tool-permissions.mdx:50-57` |
| `~/.continue/.continuerc.json` | `{ "disableIndexing": true }` **禁止 Continue 索引自己的配置目录** | `core/util/paths.ts:210-224` |
| `config.yaml` 顶层 `tools: [...]` | 额外工具（name + description 简单声明） | `packages/config-yaml/src/schemas/index.ts:241-243` |

**加载入口**：

- MCP 加载：`mcpManager.setConnections(mcpOptions, false, { ide })`（`core/config/load.ts:544`、`core/config/yaml/loadYaml.ts:380`）
- Skills/Rules 加载：每次 `ConfigHandler.loadConfig()` 时由 `loadMarkdownSkills` / `loadMarkdownRules` 触发
- 工具聚合：`streamChat` 入口的 `applyToolOverrides(options.tools, this.toolOverrides)`（`core/llm/index.ts:1106-1110`）

**全局 vs 项目级**：

- MCP：**两者都有**，且去重（同名 project 覆盖 global，见 `loadJsonMcpConfigs.ts:184-187` 的 `deduplicateArray`）
- Skills：**两者都有**，无明确覆盖语义（合并列表）
- Rules：**两者都有**，AGENTS.md/AGENT.md/CLAUDE.md 是**项目级独占**（自动 alwaysApply）
- Tool overrides：**项目级 config.yaml 内**（不是文件系统级）

**与 `standard/file_backend.md` 对照**：

- ✅ §3.1 三层分离：`~/.continue/`（全局）+ `<workspace>/.continue/`（项目级）+ IDE globalState（仅 secrets）
- ✅ §10.4 包内嵌 default config + user override：`core/util/paths.ts:119-130` 首次 `getConfigYamlPath()` 时写入 default YAML
- ✅ §10.5 多级配置/数据搜索链：`getAllDotContinueDefinitionFiles` 同时扫 `<workspace>/.continue/` 和 `~/.continue/`
- ✅ §10.8 MCP 协议支持：是（YAML + JSON 双格式 + 三 transport）
- ⚠️ §5.3 secrets 独立文件 + 0o600：VS Code 端用 SecretStorage（OS keychain，**比 0o600 更强**），JetBrains 端没看到独立 secrets 文件
- ❌ **不做**的事：没有 per-workspace hash 隔离，没有 profile 隔离（`CONTINUE_GLOBAL_DIR` 是测试用，不是用户功能）

---

## 3. 关键代码片段

### 3.1 内置工具枚举 + 客户端/服务端分流（`core/tools/builtIn.ts:1-26`）

```ts
export enum BuiltInToolNames {
  ReadFile = "read_file",
  EditExistingFile = "edit_existing_file",
  SingleFindAndReplace = "single_find_and_replace",
  MultiEdit = "multi_edit",
  ReadCurrentlyOpenFile = "read_currently_open_file",
  CreateNewFile = "create_new_file",
  RunTerminalCommand = "run_terminal_command",
  GrepSearch = "grep_search",
  // ... 共 19 个
}

export const CLIENT_TOOLS_IMPLS = [
  BuiltInToolNames.EditExistingFile,
  BuiltInToolNames.SingleFindAndReplace,
  BuiltInToolNames.MultiEdit,  // 这 3 个在 IDE 端执行（需要 LSP 能力）
];
```

### 3.2 流式 `delta.tool_calls` 解析（`core/llm/openaiTypeConverters.ts:357-389`）

```ts
} else if (delta?.tool_calls) {
  const toolCalls = delta?.tool_calls
    .filter((tool_call) => !tool_call.type || tool_call.type === "function")
    .map((tool_call) => ({
      id: tool_call.id,
      type: "function" as const,
      function: {
        name: (tool_call as any).function?.name,
        arguments: (tool_call as any).function?.arguments,
      },
    }));
  if (toolCalls.length > 0) {
    return { role: "assistant", content: "", toolCalls };
  }
}
```

### 3.3 容错参数解析（`core/tools/parseArgs.ts:3-22`）

```ts
export function safeParseToolCallArgs(toolCall: ToolCallDelta): Record<string, any> {
  const args = toolCall.function?.arguments;
  if (args && typeof args === "object' && !Array.isArray(args) && Object.keys(args).length > 0) {
    return args;
  }
  try {
    return JSON.parse(toolCall.function?.arguments?.trim() || "{}");
  } catch (e) {
    return {};  // 容错：返回空对象而不是 throw
  }
}
```

### 3.4 Anthropic `tool_result` 块构造（`core/llm/llms/Anthropic.ts:153-163`）

```ts
case "tool":
  return [{
    type: "tool_result",
    tool_use_id: message.toolCallId,
    content: renderChatMessage(message) || undefined,
  }];
```

### 3.5 Prompt-as-tool fallback 注入（`core/tools/systemMessageTools/toolCodeblocks/index.ts:7-11, 14-31`）

```ts
acceptedToolCallStarts: [string, string][] = [
  ["```tool\n", "```tool\n"],
  ["tool_name:", "```tool\nTOOL_NAME:"],  // 兼容"差模型"
];
toolCallStateToSystemToolCall(state: ToolCallState): string {
  let parts = ["```tool"];
  parts.push(`TOOL_NAME: ${state.toolCall.function.name}`);
  for (const arg in state.parsedArgs) {
    parts.push(`BEGIN_ARG: ${arg}`);
    parts.push(JSON.stringify(state.parsedArgs[arg]));
    parts.push(`END_ARG`);
  }
  parts.push("```");
  return parts.join("\n");
}
```

---

## 4. 与 Onion Agent 设计的关联

- **Onion 可以学 X**：
  1. **`safeParseToolCallArgs` 的"JSON parse 失败返回 `{}`"模式**（`parseArgs.ts:3-22`）—— Onion 的 `parseArgs` 工具层应同样容错，避免流式半截 JSON 把整个 loop 崩；`coerceArgsToSchema` 的"按 schema 反向 stringify"也很值得借鉴（`parseArgs.ts:25-58`）。
  2. **MCP YAML + JSON 双格式 + 三 transport**（stdio / sse / streamable-http）支持（`packages/config-yaml/src/schemas/mcp/index.ts:8-46`）—— Onion 应当至少支持 stdio + http，sse 可放 P1。
  3. **工具覆盖的"按工具名 dict 重写 description / 禁用"**（`applyToolOverrides.ts:8-69`）—— Onion 可以让用户在不修改工具源码的情况下重写"工具描述 + 行动短语"，对信创场景下的"对外屏蔽某些危险工具"很有用（`disabled: true`）。
  4. **Agent Skills 渐进式披露**（`readSkillTool` 把所有 skill 的 name+description 注入 description，LLM 按需 `read_skill(name="...")` 拉完整内容）—— Onion 应当走"列表在 description，全文在 file"模式，避免大 SKILL.md 撑爆 context。
  5. **大结果截断 + 追加独立 warning ContextItem**（`grepSearch.ts:88-130`、`fetchUrlContent.ts:17-37`）—— Onion 的工具实现规范应当强制："工具输出超过 X 字符必须截断并追加 warning"。

- **Onion 应当避免 Y**：
  1. **作者注释明说"we've messed up 3 TIMES by pushing to const"**（`tools/index.ts:4`）—— Onion 的工具列表必须是**函数**（`getBaseToolDefinitions()`），不能是模块级 const，否则 reload 时会重复。
  2. **`CONTINUE_GLOBAL_DIR` 用模块加载期 IIFE 一次性求值**（`paths.ts:27-35`）—— 不能动态切换，Onion 如果要支持 per-task home override，应改为按调用读 env var（参考 Hermes 教训）。
  3. **没有显式 retry 计数器**，错误回流靠 LLM 自行决定（`callTool.ts:280-295`）—— Onion 应当有显式 maxRetries（参考 Claude Code 的 6 次），防止 LLM 死循环。
  4. **没有 Plan/Act 切换**（不像 Cline / Roo Code），靠 system prompt 约束 —— Onion P1 可以加 plan 工具（`update_plan` + `finish_plan`）做 plan-then-act。

---

## 5. 不确定 / 未找到

- **MCP UI resource 的实际渲染流程**：`callTool.ts:125-145` 有 mcpUiState 抓取逻辑，但具体到 IDE 侧边栏如何渲染没在 `core/` 找到（应是在 `gui/` 端）。
- **JetBrains / CLI 端的 MCP 加载路径**：仅看 `core/` 源码，JetBrains 端的 `MCPManager` 包装、CLI 端的 `cn mcp` 命令没在本次范围内确认。
- **skill / rule 的"项目级 vs 全局"覆盖优先级**：`loadMarkdownSkills` / `loadMarkdownRules` 是直接 `flat()` 合并，没看到同名 skill 的覆盖逻辑。可能是 LLM 端靠 tool description 顺序决定优先级。
- **`config.yaml` 顶层 `tools: [...]` 数组的实际使用方**：`packages/config-yaml/src/schemas/index.ts:241-243` 定义了 schema，但 `getBaseToolDefinitions` / `getConfigDependentToolDefinitions` 都没读它；可能是给 context provider 用而非 LLM tool。需在 `core/config/yaml/loadYaml.ts` 进一步确认。
- **errorMessage 回流到 LLM 后 LLM 的"自动重试"行为**：`callTool.ts:280-295` 把 errorMessage 塞回去，但 LLM 究竟能"看到"还是"忽略"取决于 `compileChatMessages` 的策略，本次未深挖。
- **`compileChatMessages` 的 tool 列表 token 计算 + 截断策略**：`countTokens.ts:135` 提到了 `countToolsTokens`，但完整的"超限就降级到 prompt-as-tool"切换逻辑没在源码里看到完整路径。
