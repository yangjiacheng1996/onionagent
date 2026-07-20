# Lobe Chat — 工具调用（Tool Channel）调研报告

## 0. 智能体一句话定位

Lobe Chat（lobehub/lobe-chat，80k+ ⭐）是 **Web + Desktop(Electron) + CLI 三端一体的 Agent 编排平台**，自称"首席 Agent 运营官"，主走多 Agent 编排 + MCP 深度集成 + 三端文件后端隔离 的路线，2026 年 7 月本调研为 13 个 default tool + 4 个 alwaysOn tool + MCP 协议 + 渐进式披露 Skills + 插件市场 的成熟体系。

## 1. 调研依据

- 源码路径：`C:\workspace\github\onionagent\harness\01_market_research\clone\lobe-chat`
- 关键文件 / 代码片段：
  - `packages/agent-runtime/src/executors/resolveTools.ts` / `tool.ts` — 工具执行与 blocked/aborted 处理
  - `packages/agent-runtime/src/transport/tool.ts` — `ToolRunResult` 协议结构
  - `packages/agent-runtime/src/transport/context.ts` — `ContextBuildOutput.resolvedTools`
  - `packages/context-engine/src/engine/tools/{ToolsEngine,ToolResolver,ToolNameResolver,ToolArgumentsRepairer,ManifestLoader}.ts` — 核心工具引擎
  - `packages/context-engine/src/providers/ToolSystemRole.ts` + `processors/{ToolCall,MessageCleanup}.ts` — prompt 注入 + OpenAI 协议转换
  - `packages/builtin-tools/src/{index,register}.ts` — 13 default tool + 全量 manifest registry
  - `packages/builtin-tool-{local-system,activator,skills,skill-store,knowledge-base,claude-code}/src/manifest.ts` — 各内置工具的 JSON schema
  - `packages/builtin-skills/src/{task,verify,agent-browser,lobehub,artifacts}/SKILL.md` — Skills 渐进式披露
  - `apps/desktop/src/main/const/dir.ts` + `apps/desktop/src/main/libs/mcp/client.ts` + `apps/desktop/src/main/controllers/{McpCtr,McpInstallCtr,HeterogeneousAgentCtr}.ts` — 桌面端 MCP + 异构 Agent（CC/Codex CLI）
  - `apps/cli/src/settings/index.ts` + `apps/cli/src/service/connect.ts` — `LOBEHUB_CLI_HOME` env + `~/.lobehub/`
  - `packages/database/src/schemas/connector.ts:178-202` — `user_connectors` 表（MCP server URL / stdio config）
- 文档 / README 引用：`AGENTS.md`（仓库根，v2.2.9）、`README.md`、`docs/`（未深入）

## 2. 五个核心问题的回答

### Q1. 工具来源

- **内置工具**：以 **30+ 个 `packages/builtin-tool-*` 子包** 形式存在，每个包导出 `*Manifest`（LobeToolManifest），共 13 个 default tool（`packages/builtin-tools/src/index.ts:43-57`）：`lobe-activator / lobe-skills / lobe-skill-store / web-browsing / lobe-knowledge-base / lobe-memory / lobe-local-system / lobe-browser / lobe-cloud-sandbox / lobe-topic-reference / agent-documents / lobe-task / lobe-agent`。4 个 alwaysOn：`lobe-agent / lobe-activator / lobe-skills / lobe-skill-store`（同文件 :74-79）。
  - **关键内置工具集**（完整 30+ 列出价值有限，列 5 个关键 + API 数）：
    - `LocalSystem`（10 API）— `readFile / searchFiles / moveFiles / writeFile / editFile / runCommand / getCommandOutput / killCommand / grepContent / globFiles`，`packages/builtin-tool-local-system/src/manifest.ts`
    - `Skills`（5 API）— `activateSkill / readReference / runCommand / execScript / exportFile`，`packages/builtin-tool-skills/src/manifest.base.ts`
    - `Activator`（1 API）— `activateTools`（动态激活工具），`packages/builtin-tool-activator/src/manifest.ts`
    - `SkillStore`（3 API）— `searchSkill / importFromMarket / importSkill`，`packages/builtin-tool-skill-store/src/manifest.ts`
    - `KnowledgeBase`（10 API）— 知识库管理 + 向量检索，`packages/builtin-tool-knowledge-base/src/manifest.ts`
  - 还有 `Browser`（桌面浏览器）/ `CloudSandbox`（云沙箱）/ `Calculator` / `Memory` / `WebBrowsing` / `Message` / `Task` / `Brief` / `Verify` / `LobeAgent`（plan+todo+sub-agent）/ `GroupManagement` / `GroupAgentBuilder` / `AgentBuilder` / `AgentManagement` / `AgentDocuments` / `PageAgent` / `RemoteDevice` / `SelfIteration` / `UserInteraction` / `TopicReference` / `LobeDeliveryChecker` / `WebOnboarding` / `Creds` / `SkillMaintainer` / `AgentSignal*` / `builtin-tool-claude-code`（无独立 manifest，工具通过 MCP bridge 透传）。
- **MCP 支持**：✅ 深度集成（三层入口）：
  - **运行时声明**：`LobeToolManifest.type` 含 `'mcp'`（`packages/context-engine/src/engine/tools/types.ts:10`），`ToolSource` 含 `'mcp'`（同 :189）
  - **客户端 SDK**：`apps/desktop/src/main/libs/mcp/client.ts` 用官方 `@modelcontextprotocol/sdk`，支持 `http` (Streamable HTTP) + `stdio`（带 stderr 监听）+ `bearer`/`oauth2` 鉴权
  - **桌面 UI / 安装**：`apps/desktop/src/main/controllers/{McpCtr,McpInstallCtr}.ts`
  - **异构 Agent 桥接**：`apps/desktop/src/main/controllers/HeterogeneousAgentCtr.ts:907-928` 写临时 `mcp.json` 调起 Claude Code CLI / Codex CLI，格式 `{mcpServers: {lobe_cc: {type: 'http', url, alwaysLoad: true}}}`
  - **服务端注册表**：`user_connectors` 表（`packages/database/src/schemas/connector.ts:195-202`）字段 `mcpServerUrl` + `mcpConnectionType` (`'http' | 'stdio' | 'cloud'`) + `mcpStdioConfig` (`{command, args?, env?}`) + `status` + `isEnabled`
  - 注意：用户级 plugin 表 `user_installed_plugins` 的 `type` 仍仅 `'plugin' | 'customPlugin'`（不直接含 `mcp`）—— MCP server 通过 connector 表管理，区别于普通 plugin
- **Agent Skills 支持**：✅ 渐进式披露（典型 pattern）：
  - **包内置**：`packages/builtin-skills/src/{task,verify,agent-browser,lobehub,artifacts}/SKILL.md` —— 每个目录下一个 SKILL.md，运行时打包到 binary
  - **运行时激活**：`packages/builtin-tool-skills/src/ExecutionRuntime/index.ts:64-69` `ProjectSkillRuntimeItem` 字段 `{name, location, source: 'device' | 'project'}`，从 `deviceFileAccess.listFiles(skillDir)` 懒枚举（`:308-319`）
  - **Web 端 DB 存储**：`agent_skills` 表（`packages/database/src/models/agentSkill.ts:11-24`）字段 `identifier, name, content, manifest, source, zipFileHash, resources, userId`
  - **管理工具**：`SkillMaintainer`（list/get/create/replace/rename，agent_document 存储），`SkillStore`（marketplace search/import），`activateSkill`（运行时按需加载）
- **其他工具类型**：
  - **Connector 集成**（OAuth 服务）— `user_connectors` 表存 Linear / Notion / Slack / GitHub / Google Drive 等第三方的 OIDC + credentials
  - **异构 Agent 桥接** — `HeterogeneousAgentCtr` 调外部 Claude Code CLI / Codex CLI（用 mcp.json 桥接）
  - **Composio 集成** — `ToolSource: 'composio'` 标记，lobe-creds 工具列出 `<composio_integrations>` 触发 `connectComposioService`
  - **插件市场** — Web 端通过 `user_installed_plugins` 表 + `PluginModel` API 装载第三方 plugin（HTTP 协议插件）；desktop 端还有 `INSTALL_PLUGINS_DIR = 'plugins'`（`apps/desktop/src/main/const/dir.ts:33`，但 file_backend 调研指其生产代码未引用）

### Q2. 工具列表的生成、传递、格式

- **生成方式**：双层管线
  1. **操作级** `OperationToolSet` 在 `createOperation` 时由 `ToolsEngine.generateTools()` 静态生成（`packages/context-engine/src/engine/tools/ToolsEngine.ts:62-93`）—— 合并 `toolIds` + `defaultToolIds`（13 个）→ 按 `functionCallChecker` 过滤（不支持 FC 的模型直接返回 undefined）→ 按 `enableChecker` 过滤（运行时条件，如"用户有 KB 才启用 lobe-knowledge-base"）→ `convertManifestsToTools()` 转 `{type:'function', function:{name,description,parameters}}`
  2. **步骤级动态激活** `StepToolDelta`（`ToolResolver.ts:24-100`）—— `accumulatedActivations`（历史 step 激活）+ `stepDelta.activatedTools`（本 step LLM 调用 `activateTools` 注入的）→ `applyActivation()` 累积生成 `ResolvedToolSet`
  - **动态刷新**：✅ 全程支持，LLM 每 step 都能 `activateTools` 拉新工具，新工具会进入下一轮 LLM 调用的 `tools` 数组；`ToolsEngine.addPluginManifest()` / `updateManifestSchemas()` / `removePluginManifest()` 三个方法在运行时增删 manifest（`ToolsEngine.ts:268-285`）
- **传递给 LLM**：走 **`ContextBuilder.build()`**（`packages/agent-runtime/src/transport/context.ts:18-37`）—— server 适配器包 `serverMessagesEngine`，client 适配器包各自的 build；输出 `ContextBuildOutput.resolvedTools: ResolvedToolSet` 进入 LLM transport 的 `runAttempt({ context, ... })`
- **格式**：**OpenAI function calling JSON**（`type: 'function'`），通过 `ToolCallProcessor` 把内部 `ChatMessage.tools[]` 转 `tool_calls` 数组（`packages/context-engine/src/processors/ToolCall.ts:96-115`），并用 `sanitizeToolCallArguments()` 最后防线修复残缺 JSON（`packages/context-engine/src/processors/ToolCall.ts:101` 引用）
  - 实际片段（来自 `ToolsEngine.ts:222-230` + `utils.ts:generateToolName`）：
    ```json
    [
      {
        "type": "function",
        "function": {
          "name": "lobe-local-system____readFile",
          "description": "Read the content of a text or document file ...",
          "parameters": {
            "type": "object",
            "properties": {
              "path": { "type": "string", "description": "The file path to read" },
              "loc":  { "type": "array", "items": { "type": "number" }, "description": "Optional range [startLine, endLine]" }
            },
            "required": ["path"]
          }
        }
      }
    ]
    ```
  - 工具名格式：`identifier____apiName____type`（`PLUGIN_SCHEMA_SEPARATOR = '____'`，`ToolNameResolver.ts:13`）；若 > 64 字符（OpenAI 上限）→ MD5 哈希 `MD5HASH_xxxxxxxxxxxx`（`ToolNameResolver.ts:34-86`），阈值由 env `TOOL_NAME_MAX_LENGTH` 可配（默认 64，0 禁用）
- **是否 prompt-as-tool**：**两种并存**—— OpenAI FC 是主线，但**额外注入 system role** 用自然语言描述工具选择指南（`packages/builtin-tool-skills/src/systemRole.ts`、`packages/builtin-tool-activator/src/systemRole.ts`、`packages/builtin-tool-knowledge-base/src/systemRole.ts`）—— `ToolSystemRoleProvider` 把所有 manifest 的 `systemRole` + `meta.title/description` 拼成 `<tools>` 块（`providers/ToolSystemRole.ts:78-93`），通过 `pluginPrompts({tools})` 渲染。`ToolDiscoveryProvider`（`providers/ToolDiscoveryProvider.ts`）还把未激活工具列在 `<available_tools>` 里供 LLM 通过 `activateTools` 拉取
- **动态刷新**：✅ `ToolResolver.resolve()` 每个 step 都跑；`ToolsEngine.addPluginManifest/removePluginManifest` 运行时增删；Lobe Chat 还有 `PluginEnableChecker`（`types.ts:43-51`）按 runtime context 决定每个工具是否启用

### Q3. 工具调用指令的解析、错误修复、准确性

- **解析方式**：双重解析
  1. **Wire 层（OpenAI delta）**：上层 LLM 适配器（`@lobechat/model-runtime`）做 `stream=True` 增量解析 OpenAI `tool_calls` 数组 / Anthropic `input_json_delta` —— 由 `@lobechat/model-runtime` 各 provider 实现，本调研未深入此层
  2. **Manifest 还原层**：`ToolNameResolver.resolve()`（`packages/context-engine/src/engine/tools/ToolNameResolver.ts:131-186`）—— 把 `"lobe-local-system____readFile"` 拆回 `{identifier: 'lobe-local-system', apiName: 'readFile', type: 'builtin'}`，并支持：
     - **MD5 反查**（`type MD5HASH_xxx` 时查所有 manifest 的 hash 匹配）
     - **无 `____` 分隔符降级**（LLM 返回裸 `activateTools` 时扫描所有 manifest 找唯一匹配，要求在 `offeredToolNames` 白名单内才接受，避免 LLM 触发未启用工具）
- **错误修复机制**：
  - **`ToolArgumentsRepairer`**（`packages/context-engine/src/engine/tools/ToolArgumentsRepairer.ts`）—— 修复 LLM 转义错误（如 Claude haiku-4.5 把多个字段塞进第一个字段的字符串值），用 `partial-json` 库（`safeParseJSON` fallback `parsePartialJSON`）恢复尽可能多的字段；按 manifest schema 的 `required` 字段做"被吞字段重建"尝试
  - **`sanitizeToolCallArguments`**（`packages/utils/src/sanitizeToolCallArguments.ts:18-34`）—— 写历史前的最后防线：合法 JSON 直接返回（保 prompt-cache key）；可 partial 解析则 re-stringify；无法恢复则降级 `'{}'`（让 tool_call 结构存活，下一轮让模型 replan）。专门为 NVIDIA NIM 这类"严格校验全 history"的 provider 准备
  - **`toolNameMaxLength` 截断**（`ToolNameResolver.ts:43-86`）—— 工具名 > 64 自动 MD5 压缩
- **准确性保证**：
  - **Schema 校验**：`LobeToolManifest.api[].parameters` 强制 JSON Schema（含 `required` 字段，`ToolArgumentsRepairer.repair()` 据此反推丢失字段）
  - **Human Intervention 闸门**：每个 API 可声明 `humanIntervention: 'never' | 'always' | 'required' | 'first'` 或基于参数的规则（如 `pathScopeAudit`，见 `builtin-tool-local-system/src/manifest.ts:23-29`）—— LLM 调用前 `InterventionChecker` 弹用户审批
  - **Plan-then-Act 模式**：`lobe-agent` 工具集内置 plan + todo + sub-agent dispatch，`groupOrchestration/GroupOrchestrationRuntime.ts` 实现 supervisor 编排
  - **工具白名单**：`chatModeAllowedToolIds` / `runtimeManagedToolIds` / `manualModeExcludeToolIds` 三套白名单（`builtin-tools/src/index.ts:85-99, 105-110, 124-132`）按模式裁剪
  - **可执行性分类**：`ToolSource: 'builtin' | 'client' | 'mcp' | 'composio' | 'lobehubSkill'` + `ToolExecutor: 'client' | 'server'`（`types.ts:189-194`）—— 决定工具在 client（浏览器/Electron）还是 server 跑
- **重试上限**：
  - **工具级**：`DEFAULT_TOOL_MAX_RETRIES = 2`（`packages/agent-runtime/src/executors/tool.ts:18`），每次失败 stream 一个 `tool_end` 事件带 `attempts` + `maxAttempts = maxRetries + 1`
  - **LLM 级**：`callLlm.ts` 用 `LLMRetryPolicy`（`packages/agent-runtime/src/utils/runtimeRetry.ts`）+ `retryPolicy.maxAttempts(provider)`，按 `classified.kind`（超时/网络/限流/服务端/上下文）分类决定是否重试，`getLLMRetryDelayMs(attempt)` 退避
  - **操作级**：被用户中断 → `interruption.canResume: true` + `interruptedInstruction` 持久化，重启后能续跑（`pauseForTools()` + `newState.interruption`，`tool.ts:127-148`）

### Q4. 工具执行结果回传

- **回传方式**：**OpenAI 协议 `role: 'tool' + tool_call_id`**，所有执行结果落到 `messages` 数组的 `role: 'tool'` 消息里
  - `createToolMessage`（`packages/agent-runtime/src/executors/tool.ts:175-206`）调用 `transports.messages.createToolMessage({ role: 'tool', tool_call_id: tool.id, content: result.content, plugin: tool, pluginState: result.state, pluginError: result.error, ... })`
  - batch 模式下 `callToolsBatch` 用 `Promise.all` 并行执行多个 tool，逐个创建 `role: 'tool'` 消息（`tool.ts:317-444`）
- **格式**：
  - **`content: string`**（必有，结果主文）—— 见 `ToolRunResult.content: string`（`packages/agent-runtime/src/transport/tool.ts:6`）
  - **`state?: Record<string, any>`** —— 工具自己的结构化状态（如 `type: 'blocked' / 'aborted' / 'execSubAgent' / 'async_tool'`）
  - **`success: boolean`** + **`error?: unknown`**
  - **`executionTime?: number`**
  - **`deferred?: boolean`** —— 异步工具，runtime 暂停等结果回填
  - **`stop?: boolean`** —— 工具请求终止当前 step
  - **`workRegistration?: WorkRegistrationIntent`** —— 任务/技能/文档的 Work 版本注册意图（`tool.ts:48-69`）
  - **没有结构化 result 对象**（如 `{success, content, error}` 三件套），走 `content: string + success: boolean + error: unknown` 组合 —— 这跟 Anthropic 的 `tool_result` 块结构有差异
- **通信协议**：**OpenAI（`role: 'tool'`）为主，Provider-agnostic 通过 `ToolTransport` 抽象**
  - `ToolTransport` 接口（`packages/agent-runtime/src/transport/tool.ts:100-117`）：`run / getCost / handleError / canRunClientTools / shouldRetry / registerWork / maxRetries`
  - server 适配器包 `ToolExecutionService`（含 `dispatchClientTool`、结果归档、设备审计）；client 适配器包 `internal_invokeDifferentTypePlugin`
  - 流式传输：`stream.publishEvent({ type: 'tool_start' | 'tool_end' | 'error' })` —— 前端实时看到工具开始 / 结束 / 错误
- **大结果处理**：
  - **不截断原始结果**，`content` 直接塞 `messages` —— 这是 Lobe Chat 的"信任 provider"哲学
  - **client 工具暂停**：`runContext.toolSource === 'client' && !tools.canRunClientTools` 时 `pauseForTools()` 暂停 op，让前端跑（`tool.ts:226-232`）—— 不污染 server context
  - **异步工具暂停**：`execution.result.deferred === true` 时同样暂停，等结果回填（`tool.ts:234-244`）
  - **Work 注册**：大结果若产生 task/skill/document → 通过 `executionResult.workRegistration` 意图 + `tools.registerWork()` 单独落 Work 版本，**剥离 args/data 防止 event blob 膨胀**（`redactResultForEvents()`，`tool.ts:46-52`）
  - **流式结果**：本地命令支持 `run_in_background: true`（返回 `shell_id`） + `getCommandOutput(shell_id)`（`builtin-tool-local-system/src/manifest.ts:198-251`），类似 Codex 的"后台 shell"
  - **toolResultMaxLength**：agentConfig.chatConfig.toolResultMaxLength 可设（`tool.ts:91`），具体截断逻辑在 client executor

### Q5. File Backend 是否为工具调用做了适配

Lobe Chat **三端独立**为工具调用做了文件系统适配，完全对照 `file_backend.md` §2.6 三端隔离模式：

#### 5.1 工具配置目录 / 文件清单

| 端 | 工具配置存储 | 证据 |
|---|---|---|
| **Web** | **PostgreSQL** 4 张表 + Drizzle ORM | `packages/database/src/schemas/`（`agent.ts` / `connector.ts` / `agentSkill.ts` / `agentDocuments.ts`）|
| **Desktop** | **Electron `app.getPath('userData')`** + 本地 SQLite 仿真 + 临时 `mcp.json` | `apps/desktop/src/main/const/dir.ts:22-32`、`apps/desktop/src/main/controllers/HeterogeneousAgentCtr.ts:923` |
| **CLI** | **`~/.lobehub/`**（`LOBEHUB_CLI_HOME` 可覆盖）| `apps/cli/src/settings/index.ts:15-17` + `apps/cli/src/service/connect.ts:41` |

具体目录 / 文件 / 表：

- **全局**：
  - Web（PG）：`user_installed_plugins`（type: 'plugin' | 'customPlugin'，`connector.ts:367-389`）—— 用户级 plugin 注册
  - Web（PG）：`user_connectors`（含 `mcpServerUrl` / `mcpConnectionType` / `mcpStdioConfig` / `oidcConfig` / `credentials`，`connector.ts:178-202`）—— **MCP server 注册表 + OIDC/OAuth 凭据**（`credentials` 字段配合 P2 加密） 
  - Web（PG）：`agent_skills`（`identifier / name / content / manifest / source / zipFileHash / resources / userId`，`models/agentSkill.ts:11-24`）—— 设备上 skills 内容
  - Web（PG）：`agent_documents`（`policy: jsonb` + 模板源 `'claw' / 'custom'`，`schemas/agentDocuments.ts:116-186`）—— 技能 bundle 文档
  - Web（PG）：`agents`、`sessions`、`messages`、`topics`、`user_memories`（40+ 表，工具消息 + tool_call_id + plugin + pluginState + pluginError 全存这里）
  - Desktop：`<userData>/lobehub-storage/file-storage/` + `plugins/`（`apps/desktop/src/main/const/dir.ts:27-33`，`file_backend.md` §2.6 已标注 plugins/ 实际未引用 —— 是历史遗物）
  - Desktop 临时：`os.tmpdir()/lobe-cc-mcp-<operationId>.json`（`HeterogeneousAgentCtr.ts:920`）—— 每 op 一次性 mcp 配置
  - CLI：`~/.lobehub/settings.json` + `~/.lobehub/connection-id` + `~/.lobehub/workspace-enrollments.json`（`settings/index.ts:15-24`）
- **项目级 / 运行时临时**：✅ 有
  - Web：单次 op 的 `mcp.json`（temp 写盘）由 Heterogeneous Agent 触发
  - Desktop：`<userData>/lobehub-storage/file-storage/`（local S3 仿真，存截图/上传文件等大结果）
  - CLI：`<cwd>/.lobehub/` 无，但每个 LLM 操作产出都走 `~/.lobehub/` + server
  - Skills 项目级：`ProjectSkillRuntimeItem.source: 'device' | 'project'`（`ExecutionRuntime/index.ts:64-69`），从 device/project 文件系统 SKILL.md 加载

#### 5.2 加载代码

- **MCP Server 加载**：
  - Desktop 端：进程启动时 `McpCtr` 初始化（`apps/desktop/src/main/controllers/McpCtr.ts`）→ `MCPClient` 构造（`libs/mcp/client.ts:31-78`）→ 按 `type: 'http' | 'stdio'` 选 `StreamableHTTPClientTransport` / `StdioClientTransport`
  - Web 端：从 `user_connectors` 表 SELECT → 适配 `ToolSource: 'mcp'` 注入 `OperationToolSet`（`packages/context-engine/src/engine/tools/types.ts:10, 189`）
- **插件加载**：`PluginModel.create()` 写 `user_installed_plugins`（`models/plugin.ts:27-45`）；`ToolsEngine.generateTools()` 合并
- **Skill 加载**：`SkillRuntimeService.findById/findByName/findAll/readResource`（`builtin-tool-skills/src/ExecutionRuntime/index.ts:41-54`），DB 端通过 `agentSkill` model 查；device/project 端通过 `DeviceFileAccess.listFiles/readFile`（`ExecutionRuntime/index.ts:76-86`）
- **用户级 manifest 注册中心**：`ToolsEngine.manifestSchemas: Map<identifier, manifest>`（`ToolsEngine.ts:18-22`），构造时一次性 build，但通过 `addPluginManifest/removePluginManifest/updateManifestSchemas` 支持运行时增删

#### 5.3 全局 vs 项目级 vs 两者

**两者都有**：
- 全局用户级：`~/.lobehub/`（CLI）、`<userData>/lobehub-storage/`（Desktop）、`user_installed_plugins / user_connectors / agents / user_memories`（Web PG）
- 项目级 / 临时：`os.tmpdir()/lobe-cc-mcp-<op>.json`（Desktop 异构 Agent 桥接）、`device: 'device' | 'project'` skills 源

**没有显式 .lobehub/ 跟随 cwd 的设计** —— 与 file_backend §2.5 / 2.6 总结一致："Lobe Chat 三端都不跟随 cwd"（§11 总览表的反例标注）

#### 5.4 与 `standard/file_backend.md` 对照

| 标准条款 | Lobe Chat 表现 | 评估 |
|---|---|---|
| §1.1 用户家固定 + env override | Desktop `userData`、CLI `LOBEHUB_CLI_HOME` → `~/.lobehub/`、Web 走 PG/Redis env | ✅ 满足（**但 Desktop 生产 build 不可 env override — §11 标反例**）|
| §1.2 控制平面 vs 工作区分离 | Desktop: `lobehub-storage/`（控制平面）+ `file-storage/`（内容存储）| ✅ 强结构化分离 |
| §1.3 AGENTS.md 向上扫描 | ❌ **不采用** —— Lobe Chat 是 server 多用户架构，AGENTS.md 不直接相关，agent 系统提示用 `SystemRoleInjector` + `AgentDocumentInjector`（`providers/`）注入 | 不适用（产品形态不同）|
| §1.4 secrets 独立 + 0o600 | `user_connectors.credentials` 独立 + （file_backend 提到）AES-256-GCM 加密 | ✅ 满足 |
| §2.6 三端隔离 | **典型代表** —— Web / Desktop / CLI 各自独立 | ✅ 强匹配（20 项目中 1/20 显式三端）|
| §3.4 强结构化 | 5/20 强结构化之一 | ✅ 满足 |
| §3.8 Bootstrap 种子 | ❌ 不采用（Web 走 `pnpm db:migrate` + 显式 alembic 129 migration）| ❌ 显式而非隐式 |
| §5.6 配置版本迁移 | **典型代表** —— 129 个 migration 文件 | ✅ 满足 |
| §8.3 atomic write | `electron-store` 自动备份 `lobehub-settings.json.bak / .tmp` | ✅ 满足 |
| §10.7 plugin / hook 系统 | Claude Code 风格 — 有 manifest registry + enableChecker | ✅ 满足 |
| §10.8 MCP 协议 | **典型代表** —— Lobe Chat 是 MCP 深度集成的旗舰 | ✅ 强满足 |
| §11 信创支持 | ❌ 桌面端生产 build 不可 env override（信创反例）| ❌ 失败 |

## 3. 关键代码片段

### 3.1 OpenAI 工具协议 + role: 'tool' 回传（`packages/agent-runtime/src/executors/tool.ts:175-206`）

```typescript
const createToolMessage = async ({ host, parentMessageId, result, state, tool }) => {
  try {
    const agentId = host.operation.agentId ?? state.metadata?.agentId;
    if (!agentId) throw new Error(`[call_tool] Missing agentId for tool message`);
    return await host.transports.messages.createToolMessage({
      agentId, content: result.content, groupId: ...,
      metadata: { toolExecutionTimeMs: result.executionTime ?? 0 },
      parentId: parentMessageId, plugin: tool as any,
      pluginError: result.error, pluginState: result.state,
      role: 'tool', threadId: ..., tool_call_id: tool.id, topicId: ...,
    });
  } catch (error) {
    await publishError(host, error, TOOL_MESSAGE_PERSIST_PHASE);
    throw markPersistFatal(error);
  }
};
```

### 3.2 工具名生成 + 64 字符 MD5 压缩（`packages/context-engine/src/engine/tools/ToolNameResolver.ts:54-86`）

```typescript
generate(identifier: string, name: string, type: string = 'builtin'): string {
  const pluginType = type && type !== 'builtin' && type !== 'default'
    ? `${PLUGIN_SCHEMA_SEPARATOR}${this.normalizeComponent(type)}` : '';
  let identifierName = this.normalizeComponent(identifier);
  let apiName = this.normalizeComponent(name);
  let toolName = identifierName + PLUGIN_SCHEMA_SEPARATOR + apiName + pluginType;
  const maxLength = getToolNameMaxLength();
  // 长度超限 MD5 压缩（OpenAI 64 char 上限）
  if (maxLength > 0 && toolName.length >= maxLength) {
    apiName = this.hashComponent(name);
    toolName = identifierName + PLUGIN_SCHEMA_SEPARATOR + apiName + pluginType;
    if (toolName.length >= maxLength) {
      identifierName = this.hashComponent(identifier);
      toolName = identifierName + PLUGIN_SCHEMA_SEPARATOR + apiName + pluginType;
    }
  }
  return toolName;
}
```

### 3.3 残缺 JSON 修复（`packages/context-engine/src/engine/tools/ToolArgumentsRepairer.ts:30-44` + `packages/utils/src/sanitizeToolCallArguments.ts:18-34`）

```typescript
// Repairer：用 partial-json 修复 LLM 转义错误
const safeParseJSON = <T>(text?: string): T | undefined => {
  if (typeof text !== 'string') return undefined;
  try { return JSON.parse(text) as T; }
  catch {
    try { return parsePartialJSON(text) as T; } catch { return undefined; }
  }
};
// Sanitizer：写历史前最后防线（保 prompt-cache key）
export const sanitizeToolCallArguments = (argsStr: string | undefined): string => {
  if (typeof argsStr !== 'string' || argsStr.length === 0) return '{}';
  if (safeParseJSON(argsStr) !== undefined) return argsStr;
  const recovered = safeParsePartialJSON(argsStr);
  if (recovered !== undefined && typeof recovered === 'object' && recovered !== null) {
    return JSON.stringify(recovered);
  }
  return '{}';
};
```

### 3.4 MCP 三层入口（`apps/desktop/src/main/libs/mcp/client.ts:31-78` + `HeterogeneousAgentCtr.ts:914-928`）

```typescript
// 客户端 SDK：HTTP / Stdio 双 transport
constructor(params: MCPClientParams) {
  this.mcp = new Client({ name: 'lobehub-desktop-mcp-client', version: '1.0.0' });
  switch (params.type) {
    case 'http':
      this.transport = new StreamableHTTPClientTransport(new URL(params.url), { requestInit: { headers } });
      break;
    case 'stdio':
      this.transport = new StdioClientTransport({ args: params.args, command: params.command,
        env: { ...getDefaultEnvironment(), ...params.env }, stderr: 'pipe' });
      break;
  }
}
// 异构 Agent 桥接：写临时 mcp.json 调起 CC/Codex CLI
const config = {
  mcpServers: { lobe_cc: { alwaysLoad: true, type: 'http' as const, url: server.urlForOperation(operationId) } },
};
await writeFile(tmpConfigPath, JSON.stringify(config), 'utf8');
```

### 3.5 三端用户家（`apps/desktop/src/main/const/dir.ts:22-33` + `apps/cli/src/settings/index.ts:15-17` + `packages/database/src/schemas/connector.ts:195-202`）

```typescript
// Desktop
export const userDataDir = app.getPath('userData');
export const appStorageDir = path.join(userDataDir, 'lobehub-storage');
export const FILE_STORAGE_DIR = 'file-storage';
export const INSTALL_PLUGINS_DIR = 'plugins';  // 实际生产代码未引用
// CLI
const LOBEHUB_DIR_NAME = process.env.LOBEHUB_CLI_HOME || '.lobehub';
const SETTINGS_DIR = path.join(os.homedir(), LOBEHUB_DIR_NAME);
const SETTINGS_FILE = path.join(SETTINGS_DIR, 'settings.json');
// Web（PG）MCP 连接表
mcpServerUrl: text('mcp_server_url'),
mcpConnectionType: text('mcp_connection_type'),  // 'http' | 'stdio' | 'cloud'
mcpStdioConfig: jsonb('mcp_stdio_config').$type<{ args?: string[]; command: string; env?: Record<string, string> }>(),
```

## 4. 与 Onion Agent 设计的关联

Lobe Chat 是 **三端 + MCP + 渐进式 Skills + 多 Agent 编排** 的旗舰实现，Onion Agent（CLI + Desktop 双端）应学其精要：

1. **学 `ToolsEngine` + `ToolResolver` 双层管线** —— 静态 `defaultToolIds`（13 个 Onion 常驻工具）+ 动态 `activateTools` 拉新工具，是"洋葱架构"中"工具通道"统一汇总的范例。Onion 可简化为 `defaultToolIds` + `manualModeExcludeToolIds` 两套，但 `ToolResolver` 累积 `activatedStepTools` 的设计是 Onion sub-agent 跨 step 持久工具上下文的天然机制。
2. **学 64 字符 MD5 压缩 + `TOOL_NAME_MAX_LENGTH` env** —— Onion 若对接 OpenAI / Anthropic 双 provider，必须有同样的工具名规范化层；建议在 `tool-name-resolver` 包做单一来源。
3. **学 `ToolArgumentsRepairer` + `sanitizeToolCallArguments` 双层** —— Onion `tool.ts` 必备"残缺 JSON 修复 + 写历史前最后防线"，避免一个非法参数拖死整段 history（OpenAI / Anthropic 都会 400 整个 request）。
4. **学 MCP `LobeToolManifest.type: 'mcp'` 一等公民** —— Onion `~/.onion/mcp.json` + `<repo>/.onion/mcp.json` 双层 + 工具源标记 `ToolSource: 'mcp'`，让 MCP server 跟内置工具走同一条 `OperationToolSet` 管线，不必单开通道。
5. **避坑 —— Desktop 生产 build 不可 env override 是信创反例**：Onion 必须保证 `ONION_HOME` + `ONION_PROFILE` 单一 env 覆盖点**在打包后仍生效**（不能只在 dev 模式生效），Lobe Chat 的 Electron-builder 配置中 process.resourcesPath 写死就是反例。
6. **避坑 —— `INSTALL_PLUGINS_DIR` 常量定义但生产代码未引用**（file_backend §8.5 已标），Onion 的 `~/.onion/plugins/` 目录必须在代码里有真引用，**否则 help 字符串和代码脱节**。

## 5. 不确定 / 未找到

- **流式增量解析的具体 delta 处理逻辑**（OpenAI `delta.tool_calls` / Anthropic `input_json_delta` 累积）**不在 `agent-runtime` 包内** —— 应该在 `@lobechat/model-runtime`（model-runtime 包内），本调研未深入。
- **MCP `ToolSource: 'mcp'` 工具的具体注册流程**（如何把 `user_connectors` 表里的 mcp 字段转成 LobeToolManifest）未找到对应代码 —— 应该分布在 `apps/server/src/serverModules/Mecha/AgentToolsEngine`（注释 `builtin-tools/src/index.ts:128-131` 提到），未深入。
- **`toolNameMaxLength` 实际触发场景** —— 仅看代码无法判断 OpenAI 实际是否真有超 64 字符的工具名（标识符 21 字符 + API 名 30 字符 + 4 个分隔符，理论刚好）。
- **`pauseForTools` 暂停后的客户端工具结果回填机制**（`toolMessageIds: Record<tool_call_id, toolMessageId>`）—— 知道是停 + 续跑，但具体怎么从 client 把 result 喂回 server op 未深入。
- **Skills 的"项目级"（`source: 'project'`）加载根路径** —— `ProjectSkillRuntimeItem` 有 source 字段，但具体从 `<cwd>/.lobehub/skills/` 还是 `<cwd>/skills/` 加载未确认。
