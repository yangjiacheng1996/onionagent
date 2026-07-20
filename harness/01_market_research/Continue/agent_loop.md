# Continue — Agent Loop 调研报告

> 调研对象:[continuedev/continue](https://github.com/continuedev/continue) `@ v1.3.40`(`core/package.json` 声明)
> 调研范围:`core/`(Node.js agent runtime)、`extensions/vscode/`(VS Code 侧边栏 webview)、`extensions/intellij/`(Kotlin 插件)、`extensions/cli/`(`cn` CLI / TUI)、`gui/`(React + Redux webview)、`docs/`
> 调研日期:2026-07-18
> 配套报告:`harness/01_market_research/Continue/file_backend.md`(工作区与索引)、`harness/01_market_research/Continue/tool_channel.md`(工具调用通道)

---

## 0. 智能体一句话定位

Continue 是**开源 IDE 编码 Agent**(VS Code / JetBrains 插件 + `cn` CLI),在 IDE 侧边栏与 TUI 中提供 **Chat / Edit / Agent / Plan / Background / Autocomplete** 六种工作模式,核心定位是"**基于 LLM function calling 的多轮 ReAct + 嵌入式工具运行时**",通过**单一 LLM `streamChat` 调用 + Redux thunk 递归 `streamResponseAfterToolCall`** 实现"调用 LLM → 解析 tool_calls → 执行工具 → 回灌 LLM"的循环,既支持原生 OpenAI / Anthropic function calling,也自带"codeblock framework"作为本地弱模型的 fallback 协议。**没有显式 Plan Agent / 没有 sub-agent 委派的内部调度**(sub-agent 仅在 CLI `cn` 的独立 `executeSubAgent` 入口暴露为 `Subagent` 工具),且**没有独立的 planning step**——Plan 模式靠 system message 把写工具屏蔽、靠工具 list 过滤实现"只读 + 询问"。

---

## 1. 调研依据

主要源码证据路径(全部位于 `C:\workspace\github\onionagent\harness\01_market_research\clone\continue\`):

| 关注点 | 文件 |
|---|---|
| Agent Loop 主入口(IDE/GUI) | `gui/src/redux/thunks/streamResponse.ts`、`gui/src/redux/thunks/streamNormalInput.ts`、`gui/src/redux/thunks/streamResponseAfterToolCall.ts`、`gui/src/redux/thunks/callToolById.ts` |
| Agent Loop 主入口(CLI) | `extensions/cli/src/stream/streamChatResponse.ts`、`extensions/cli/src/stream/handleToolCalls.ts`、`extensions/cli/src/subagent/executor.ts` |
| LLM 流式调用 | `core/llm/streamChat.ts`、`core/llm/llm.ts`(基类)、`core/core.ts:563-631`(`llm/streamChat` 路由) |
| 工具调用 | `core/tools/callTool.ts`、`core/tools/index.ts`、`core/tools/builtIn.ts` |
| 工具注册 / 工具分类 | `core/tools/builtIn.ts:1-29`、`gui/src/redux/thunks/evaluateToolPolicies.ts` |
| 工具权限(HITL) | `gui/src/redux/thunks/evaluateToolPolicies.ts:1-100`、`extensions/cli/src/permissions/permissionChecker.ts:1-150`、`extensions/cli/src/permissions/permissionManager.ts`、`extensions/cli/src/permissions/defaultPolicies.ts` |
| 工具 prompt-as-tool fallback | `core/tools/systemMessageTools/toolCodeblocks/index.ts:1-100`、`core/tools/systemMessageTools/interceptSystemToolCalls.ts` |
| 上下文压缩 / 摘要 | `core/util/conversationCompaction.ts:1-114`、`extensions/cli/src/compaction.ts:1-340` |
| Plan 模式系统消息 | `core/llm/defaultSystemMessages.ts:78-92`(`DEFAULT_PLAN_SYSTEM_MESSAGE`)、`gui/src/redux/util/getBaseSystemMessage.ts:21-25` |
| Ask 模式(CLI) | `extensions/cli/src/tools/askQuestion.ts:1-58` |
| Sub-agent(CLI) | `extensions/cli/src/subagent/executor.ts:53-145`、`extensions/cli/src/subagent/get-agents.ts:18-35`、`extensions/cli/src/tools/subagent.ts` |
| AGENTS.md / AGENT.md / CLAUDE.md | `core/config/markdown/loadMarkdownRules.ts:13`、`core/config/loadLocalAssistants.ts:23`(作为 partOfContinueConfig 判定) |
| `.continuerc.json` 防自索引 | `core/util/paths.ts:210-224` |
| 退出 / 终止 | `core/tools/streamChat.ts`、`extensions/cli/src/stream/streamChatResponse.ts`(返回 `shouldContinue: false` 跳出 while(true))、`extensions/cli/src/tools/exit.ts` |
| IDE ↔ core 通信 | `core/protocol/core.ts:283`、`extensions/vscode/src/extension/VsCodeExtension.ts`、`extensions/vscode/src/ContinueGUIWebviewViewProvider.ts` |
| JetBrains 端 | `extensions/intellij/`(Kotlin,文档显式说"out of sync with core") |
| 企业版 Continue for Teams | `core/util/paths.ts:342-370`(`.configs/<hostname>/` 远端 config 缓存)、`docs/` 多处 |
| 模式切换 | `gui/src/components/ModeSelect/ModeSelect.tsx:30-100`(`MessageModes` = `"chat" | "agent" | "plan" | "background"`) |

---

## 2. 九大问题回答

### Q1. Agent Loop 主流程

#### 1.1 总体架构(双形态:`cn` CLI 同步 while-true 循环 + IDE 嵌入式 Redux thunk 递归)

Continue **不是单一形态的 agent loop**,而是**两个并存的实现**——IDE 嵌入式(React + Redux Toolkit thunk 递归)与 CLI 同步(`while (true)` 循环 + 历史 in-memory)。两者**底层共享同一份 LLM adapter(`core/llm/llms/`)与工具实现(`core/tools/`)**,只在"循环控制 + 状态管理 + UI 渲染"上分叉。

| 形态 | 主循环位置 | 状态存储 | 适合场景 |
|---|---|---|---|
| **IDE 嵌入式**(VS Code / JetBrains GUI) | `gui/src/redux/thunks/streamNormalInput.ts:100-280` + `streamResponseAfterToolCall.ts:65-100`(递归) | Redux store(`gui/src/redux/slices/sessionSlice.ts`)+ `~/.continue/sessions/<id>.json` | IDE 侧边栏人工介入多、需要 streaming UI |
| **CLI**(`cn` TUI / headless) | `extensions/cli/src/stream/streamChatResponse.ts:430-480`(`while (true)` 循环) | `services/ChatHistoryService.ts` + `~/.continue/sessions/<uuid>.json` | TUI 终端 / CI 自动化 |
| **Sub-agent(CLI 委派)** | `extensions/cli/src/subagent/executor.ts:57-145` 复用 `streamChatResponse` | 独立 child session(临时 `chatHistory[]` 数组,不写文件) | 把任务丢给 specialized agent |

#### 1.2 嵌入式 vs 命令式调用

**嵌入式(IDE 插件形态)** 是 Continue 的**主战场**:
- VS Code 端:`extensions/vscode/src/extension/VsCodeExtension.ts` 创建 `Core`(Node.js 进程内 in-process,或 IPC remote),`extensions/vscode/src/ContinueGUIWebviewViewProvider.ts` 加载 `gui/`(React 18 + Vite + TailwindCSS)作为 webview 侧边栏。
- JetBrains 端:Kotlin 插件,`extensions/intellij/`(`ServerConstants.kt` 自带实现,**文档自承 "out of sync with core/util/paths.ts"**——意味着 IDE 端与 core 端不是 100% 同步演进,见 `extensions/intellij/.../ServerConstants.kt:1-3`)。
- **嵌入手法的关键是 `IMessenger` 抽象**(`core/protocol/messenger/index.ts`):IDE ↔ core 通过 `ToCoreProtocol` / `FromCoreProtocol` 双向消息通信,但 Continue **同时支持 in-process(`InProcessMessenger`)和 webview(`VsCodeMessenger`)** 两种 transport;**VS Code webview 模式下,GUI 进程与 core 进程分两个 OS 进程,IPC 走 `acquireVsCodeApi().postMessage`**。

**命令式调用**(`cn` CLI)是**次级形态**,功能上与 GUI **完全平级**(同样的 system message、tool list、mode 切换、permission system、auto-compaction),只是少了图形化 streaming UI(`extensions/cli/src/stream/streamChatResponse.ts` 用 `StreamCallbacks` 把 delta 推给 TUI / headless logger)。

#### 1.3 agents/ 系统(单 agent 还是多 agent)

**架构上 = 单一 in-process agent runtime + 多套 LLM provider 适配**(`core/llm/llms/` 下 50+ provider)。Continue **没有**类似 LangGraph / AutoGen 的"多 agent 编排框架",也没有内部 sub-agent 调度——但**配置层有 "agents" 概念**,用法完全不同:

- **配置层的 `.continue/agents/<name>.md`**(`docs/customize/agents.mdx` + 仓库根 `.continue/agents/` 5 个示例)是**"任务专用的 prompt bundle"**——本质上是带 frontmatter 的 markdown,被 `loadMarkdownRules` 当作 Rule 加载,可以通过 `description` 让 LLM 在 `apply_intelligently` 模式下按需拉取。**不是独立 agent runtime**,只是 system message 的一部分(见 `core/config/loadLocalAssistants.ts:23` 把 `agents/assistants/configs` 当作 `isContinueConfigRelatedUri` 判定)。
- **运行时的 multi-agent 仅 CLI 形态**:`Subagent` 工具(`extensions/cli/src/tools/subagent.ts:55-77`)让主 agent 调一次 `executeSubAgent`,**子 agent 复用同一份 `streamChatResponse` 但跑在隔离的 child chatHistory 上**(`extensions/cli/src/subagent/executor.ts:120-145`),临时禁用 `chatHistorySvc`、覆盖 system message、临时改 `toolPermissions` 为 `[{ tool: "*", permission: "allow" }]`(即 sub-agent 全部免审批)。**没有"Manager Agent 委派多 worker"的拓扑**,而是一个**平级委托**:主 agent 把任务扔给一个 specialized agent,等结果回来继续。

#### 1.4 嵌入式 Mermaid 流程图(IDE 形态主路径)

> 该图覆盖一次完整 user prompt → 多次 LLM call → 多次 tool 执行 → 最终回答。核心循环点是 `streamNormalInput` + `streamResponseAfterToolCall` 的**互相递归**(`depth` 参数防栈溢出,`streamNormalInput.ts:65-67` 在 depth > 50 时抛错)。

```mermaid
flowchart TD
    Start([用户在 IDE 侧边栏 / TUI 输入 prompt]) --> Editor["streamResponseThunk<br/>(gui/src/redux/thunks/streamResponse.ts:29-110)<br/>解析 TipTap editor 内容<br/>+ 收集 @ context items<br/>+ 收集选中 code"]
    Editor --> SlashCheck{slash command?}
    SlashCheck -- 是 --> SlashRun[走 built-in-legacy/custom<br/>slash command 独立流]
    SlashCheck -- 否 --> StreamCall["streamNormalInput (depth=0)<br/>(streamNormalInput.ts:85-280)"]

    StreamCall --> ResolveMode{mode?<br/>chat/agent/plan/background}
    ResolveMode -- chat --> SystemMsg1["baseChatSystemMessage<br/>(getBaseSystemMessage.ts:21-23)<br/>提示'无工具可用'"]
    ResolveMode -- plan --> SystemMsg2["basePlanSystemMessage<br/>(defaultSystemMessages.ts:78-92)<br/>'只读工具 + 不要写代码'"]
    ResolveMode -- agent --> SystemMsg3["baseAgentSystemMessage<br/>(defaultSystemMessages.ts:62-76)<br/>'all tools enabled'"]
    ResolveMode -- background --> StreamCall

    SystemMsg1 --> ConstructMsgs["constructMessages<br/>+ getSystemMessageWithRules<br/>(getSystemMessageWithRules.ts:243-275)<br/>根据 alwaysApply / glob / regex 过滤 rules"]
    SystemMsg2 --> ConstructMsgs
    SystemMsg3 --> ConstructMsgs

    ConstructMsgs --> ContextPrune{context 超限?}
    ContextPrune -- 是 --> InlineErr[dispatch setInlineErrorMessage<br/>'out-of-context' + return]
    ContextPrune -- 否 --> LLMCall["ideMessenger.request 'llm/streamChat'<br/>(core/core.ts:563-631 → llmStreamChat)<br/>model.streamChat() 异步生成器<br/>(core/llm/llm.ts)"]

    LLMCall --> NativeTC{native tool_calls?}
    NativeTC -- 是 --> CollectTC[解析 delta.tool_calls<br/>按 id 累积 toolCallState<br/>(sessionSlice.ts)]
    NativeTC -- 否,但启用了 useNativeTools --> CollectTC
    NativeTC -- 否,且关闭 native tools --> FallbackTC["SystemMessageToolCodeblocksFramework<br/>(systemMessageTools/toolCodeblocks/)<br/>把 '```tool' code block 当 tool call 解析<br/>+ detectToolCallStart"]
    FallbackTC --> CollectTC

    CollectTC --> PreProcess["preprocessToolCalls<br/>(preprocessToolCallArgs.ts)<br/>核心端 preprocess args,errored 即跳过执行"]
    PreProcess --> EvalPolicy["evaluateToolPolicies<br/>(evaluateToolPolicies.ts:54-99)<br/>基线 = user toolSettings → defaultToolPolicy<br/>+ dynamic evaluateToolCallPolicy<br/>(如 run_terminal_command 走<br/>@continuedev/terminal-security)"]

    EvalPolicy --> PolicyResult{policy}
    PolicyResult -- disabled --> MarkError[errorToolCall + 输出 'Security Policy Violation']
    PolicyResult -- allowedWithoutPermission --> AutoRun
    PolicyResult -- allowedWithPermission --> AskUser["触发 IDE 弹窗<br/>(VS Code webview 走 ToolCallUI)<br/>TUI 走 'Approve/Reject' 对话框"]
    AskUser -- Approve --> AutoRun
    AskUser -- Reject --> SkipRun[errorToolCall + 'Tool call was rejected']

    AutoRun["callToolById (depth+1)<br/>(callToolById.ts:25-100)"] --> ClientOrCore{client tool?<br/>edit / multiEdit / singleFindAndReplace}
    ClientOrCore -- 是 --> ClientRun["callClientTool<br/>(clientTools/callClientTool.ts)<br/>IDE 端用 diff 模式执行<br/>直接动 IDE workspace"]
    ClientOrCore -- 否 --> CoreRun["ideMessenger.request 'tools/call'<br/>(core.ts → callTool callTool.ts:235-280)<br/>走 core 实现或 MCP"]
    CoreRun --> CallBuiltIn["callBuiltInTool (callTool.ts:124-180)<br/>按 function name dispatch<br/>到 read_file / grep_search / run_terminal_command<br/>等 17 个内置工具"]
    CallBuiltIn --> McpOrHttp{uri?}
    McpOrHttp -- http --> HttpTool["callHttpTool (callTool.ts:27-42)<br/>POST 到本地 HTTP tool server"]
    McpOrHttp -- mcp --> McpTool["MCPManagerSingleton.getConnection(mcpId)<br/>→ client.callTool() 走 stdio/sse/streamableHttp"]

    ClientRun --> ToolMsg
    HttpTool --> ToolMsg
    McpTool --> ToolMsg
    MarkError --> ToolMsg["dispatch updateToolCallOutput<br/>把 ContextItem[] 写进 toolCallState.output<br/>streamUpdate role=tool message<br/>(streamResponseAfterToolCall.ts:38-44)"]

    SkipRun --> ToolMsg
    ToolMsg --> AllDone{所有 tool_call 都 done / errored?}
    AllDone -- 否,还有生成中 --> WaitTool[等 sibling tool_call 完成]
    AllDone -- 是 --> Recurse["streamResponseAfterToolCall<br/>(streamResponseAfterToolCall.ts:65-100)<br/>dispatch streamNormalInput depth+1<br/>(自递归回到 LLMCall)"]
    WaitTool --> AllDone

    Recurse --> LLMCall

    Recurse -. "streamNormalInput 的 depth > 50<br/>(streamNormalInput.ts:65-67)" .-> HardStop[抛 'Max stream depth of 50 reached']
    LLMCall -. "无 tool_call / 用户 abort /<br/>abortStream signal" .-> SoftStop["dispatch setInactive<br/>(sessionSlice.ts:233)<br/>session.isStreaming=false<br/>= loop 软退出"]

    SoftStop --> End([UI 渲染最终 assistant message])
    HardStop --> End
    SlashRun --> End

    style Recurse fill:#f9e,stroke:#333,stroke-width:2px
    style LLMCall fill:#bbf,stroke:#333,stroke-width:2px
    style EvalPolicy fill:#bfb,stroke:#333,stroke-width:2px
    style AskUser fill:#ffd,stroke:#333,stroke-width:2px
```

**关键观察**:
1. **`streamNormalInput` ↔ `streamResponseAfterToolCall` 互相递归**形成"无显式 while-loop 的循环"——`streamResponseAfterToolCall.ts:78-82` 在 `areAllToolsDoneStreaming()` 满足时 dispatch `streamNormalInput({ depth: depth + 1 })`,形成 functional recursion。`depth` 是 thunk debug 用的,真正的"循环出口"是 **`session.isStreaming = false`**(`sessionSlice.ts:233`)+ `streamAborter.signal.aborted`。
2. **没有独立的"Plan 步骤"**——Plan 模式只是 system message 不同 + 工具 list 过滤(只暴露 `readonly: true` 的工具),不改变 loop 拓扑。
3. **Core 与 GUI 是两进程**(webview 模式),所以 `ideMessenger.request("tools/call", ...)` 是一次 IPC round-trip(`callToolById.ts:60-66`),本地 `edit / multiEdit / singleFindAndReplace` 三个**Client Tools** 跳过 IPC 直接在 GUI 端 `callClientTool` 跑(`callToolById.ts:50-58`)。

#### 1.5 CLI `while (true)` 循环(`extensions/cli/src/stream/streamChatResponse.ts:430-480`)

```typescript
// streamChatResponse.ts 主循环骨架(简化)
while (true) {
  // 1. 刷新 chatHistory
  chatHistory = refreshChatHistoryFromService(chatHistory, isCompacting);

  // 2. 重新计算 system message(可能受 tool permission mode 影响)
  const systemMessage = await services.systemMessage.getSystemMessage(
    services.toolPermissions.getState().currentMode,
  );

  // 3. 重新计算 tool list(同上)
  const tools = applyChatCompletionToolOverrides(rawTools, model.chatOptions?.toolOverrides);

  // 4. Pre-API auto-compaction(80% 阈值,compaction.ts:226-264)
  chatHistory = (await handlePreApiCompaction(...)).chatHistory;

  // 5. 调 LLM(关键:会做 context 长度校验 + pruneLastMessage)
  const { content, toolCalls, shouldContinue } = await processStreamingResponse({...});

  // 6. 处理 tool calls(权限 + 执行 + 写回 history)
  const shouldReturn = await handleToolCalls({...});
  if (shouldReturn) return finalResponse;

  // 7. Post-tool context 校验 + 80% auto-compaction + auto-continuation
  chatHistory = (await handlePostToolValidation(...)).chatHistory;
  chatHistory = (await handleNormalAutoCompaction(...)).chatHistory;
  const shouldAutoContinue = handleAutoContinuation(compactionOccurredThisTurn, ...);

  // 8. 退出条件:无 tool_call && ! auto-continue-after-compaction
  if (!shouldContinue && !shouldAutoContinue) break;
}
```

**与 IDE 形态的对比**:
- CLI 是**显式 `while (true)`**,IDE 是**递归 thunk**——本质相同(都基于"模型判断是否继续"),但 CLI 把 compaction 当作 loop 的**一等公民**(loop 入口 / 出口都跑 compaction 检查),IDE 把 compaction 放在 `llm/compileChat` 阶段(`core/core.ts:631` `compactConversation`)或 `preApiCompaction`(`core/core.ts:630`)。
- CLI 把 tool permission 当**模式切换对象**(`PLAN_MODE_POLICIES` / `AUTO_MODE_POLICIES` / `getDefaultToolPolicies(isHeadless)`),通过 `services.toolPermissions.getState().currentMode` 注入,IDE 走 `toolSettings` Redux slice + `evaluateToolPolicies` thunk。

---

### Q2. Plan 计划机制

**Continue 的"Plan"不是独立 agent loop 子系统,而是 3 个层面的综合效果**:
1. **`MessageModes = "chat" | "agent" | "plan" | "background"`**(`core/index.d.ts:495`)——只是个枚举值,不是独立 runtime。
2. **system message 切换**(`core/llm/defaultSystemMessages.ts:78-92` `DEFAULT_PLAN_SYSTEM_MESSAGE`):
   > "You are in plan mode, in which you help the user understand and construct a plan.
   > Only use read-only tools. Do not use any tools that would write to non-temporary files.
   > If the user wants to make changes, offer that they can switch to Agent mode..."
3. **工具 list 过滤**:
   - **GUI 端**通过 `<ListboxOption value="plan">` + tooltip `"Read-only/MCP tools available"`(`gui/src/components/ModeSelect/ModeSelect.tsx:144-148`)告诉用户 "只读 + MCP 可用",**实际过滤由 `selectActiveTools` 选择器 + 工具的 `readonly: true` 字段共同决定**(`core/tools/index.ts:9-19` 中 `getBaseToolDefinitions` 列出的 9 个基础工具里只有 `read_file` / `glob_search` / `read_currently_open_file` / `view_diff` / `ls` / `fetch_url_content` 是 `readonly: true`;`create_new_file` / `run_terminal_command` / `create_rule_block` 都是 `readonly: false`,在 plan 模式应该被过滤)。
   - **CLI 端**通过 `PLAN_MODE_POLICIES`(`extensions/cli/src/permissions/defaultPolicies.ts:39-66`)显式 `exclude` 写工具:`Edit` / `MultiEdit` / `Write` 全部 `permission: "exclude"`,Bash `permission: "allow"`(允许只读命令),MCP `permission: "allow"`(放行)。
4. **官方文档**(`docs/ide-extensions/agent/how-it-works.mdx:39-60`)总结了三模式的工具集差异:**Chat 无工具 / Plan 只读 + MCP / Agent 全工具**。

**结论**:
- **没有"先 plan → 再 ask user → 再 implement"的两阶段 flow**。Plan 模式只是"屏蔽写工具、告诉 LLM 你在 plan"的运行时模式;模型想"实现"必须**建议用户切到 Agent 模式**(`defaultSystemMessages.ts:88` "When ready to implement changes, request to switch to Agent mode")。
- **没有显式的 plan 存储**(没有 `plan.md`、没有 `plan_steps[]`)。Plan 的输出就是 LLM 写一段 markdown 说明,然后等用户切到 Agent 模式再开新一轮 loop。
- **没有"Plan / Act"状态机**(对比 Cline 的 `<PlanModeSwitch>` `Plan / Act` 二态、`reasoning: plan` flag,Continue 的 plan 不是一个 first-class 概念)。

---

### Q3. Sub Agent

**Continue 的"sub-agent"是 CLI 专属的"任务委派工具"**,核心实现:

| 维度 | 实现 | 证据 |
|---|---|---|
| **入口** | `Subagent` 工具 | `extensions/cli/src/tools/subagent.ts:1-105`(动态 `description: generateSubagentToolDescription(...)` 列出所有可用 agent) + `extensions/cli/src/subagent/index.ts:3-21`(`SUBAGENT_TOOL_META`) |
| **Schema** | `required: ["description", "prompt", "subagent_name"]`,3 个参数 | `extensions/cli/src/subagent/index.ts:8-19` |
| **执行** | `executeSubAgent()` 复用 `streamChatResponse` | `extensions/cli/src/subagent/executor.ts:53-145`,第 82-87 行用 `serviceContainer.set(TOOL_PERMISSIONS, { policies: [{ tool: "*", permission: "allow" }] })` 临时改写权限 |
| **隔离** | 临时 `chatHistory[]` 数组 + 覆盖 `services.systemMessage.getSystemMessage` + 临时禁用 `chatHistorySvc.isReady` | `executor.ts:75-105` |
| **可用的 subagent 列表** | 从 `ModelService.getSubagentModels()` 读(YAML config 里的 `models` 带 `chatOptions.baseSystemMessage` 的就是 subagent 候选) | `extensions/cli/src/subagent/get-agents.ts:5-13` |
| **IDE / GUI 端** | **没有** Subagent 工具;`extensions/vscode/` 全仓 grep `subagent` 0 命中;`gui/` 全仓 grep `SUBAGENT` 0 命中;核心端 `core/tools/builtIn.ts` 19 个工具里**没有 subagent** | — |

**关键特点**:
1. **"Sub-agent" 实为"用不同 system message + 不同 model 跑同一份 loop"**——`executor.ts:88-94` 直接调 `streamChatResponse(prompt-as-user-message, model, llmApi, abortController, callbacks)`,**复用了完整 CLI loop**(包括 auto-compaction、tool permission、stream handling)。
2. **子 agent 没有独立文件**,不写 `sessions/<id>.json`——`executor.ts:75-83` 临时把 `chatHistorySvc.isReady = () => false`,让所有 mutation 走 in-memory 数组。
3. **结果回灌**:`subagent.ts:69-77` 把 child 的 `accumulatedOutput` 通过 `chatHistoryService.addToolResult(toolCallId, output, "calling")` 实时流回主 agent,**主 agent 看到的是一个长 tool_result 字符串**,不是结构化 plan/result。
4. **没有"Manager / Worker 拓扑"**(`subagent/executor.ts` 是平级一次性委派,没有 spawn N 个并行 worker),没有 AutoGen 的 RoundRobin / SelectorGroupChat / Swarm 拓扑概念。
5. **`extensions/cli/src/subagent/executor.ts:85` 有 TODO**: "allow all tools for now; todo: eventually we want to show the same prompt in a dialog whether asking whether that tool call is allowed or not"——意味着**当前 sub-agent 是"裸跑"模式**,安全模型不完善。

---

### Q4. Loop 退出机制

**Continue 的 loop 退出 = "模型决定不再调工具 + 用户主动中断 + 异常兜底"三层防护**。

#### 4.1 IDE / GUI 端(`gui/src/redux/thunks/streamNormalInput.ts:240-280`)

**软退出 = `session.isStreaming = false` + `streamAborter.signal.aborted`**:
- **`streamNormalInput.ts:236-238`**:`setInactive()` 触发 `session.isStreaming = false`(`sessionSlice.ts:233`),这是 GUI 渲染层停止 spinner 的标志。
- **退出点 A — `streamNormalInput.ts:158-160`**:流式 LLM chunk 循环里 `if (!getState().session.isStreaming) { dispatch(abortStream()); break; }`,用户点了 Stop 按钮就立刻跳出。
- **退出点 B — `streamNormalInput.ts:220-222`**:tool call 阶段也校验 `streamAborter.signal.aborted`。
- **退出点 C — `streamNormalInput.ts:243-247`**:`if (originalToolCalls.length === 0) { dispatch(setInactive()); }`——**没有 tool_call 时,loop 软退出**,UI 提示"模型已给出最终回答"。
- **退出点 D — `streamNormalInput.ts:254-262`**:工具全 `needsApproval` 时,**等用户 Approve,不会自动继续**;`dispatch(setInactive())` 把 loop 挂起。
- **硬退出 = `streamNormalInput.ts:65-67`**:`if (depth > 50) throw new Error("Max stream depth of 50 reached in test")`——递归深度保护,正常情况不会触发。

#### 4.2 CLI 端(`extensions/cli/src/stream/streamChatResponse.ts:467-480`)

```typescript
// streamChatResponse.ts 退出条件(简化)
if (!shouldContinue && !shouldAutoContinue) {
  break;
}
```

- **`shouldContinue`** = `processStreamingResponse` 返回的 `toolCalls.length > 0`(`streamChatResponse.ts:215`)。**模型没调任何工具 = 模型判断任务完成 = 退出**。
- **`shouldAutoContinue`** = `handleAutoContinuation`(`streamChatResponse.ts:74-100`)在 compaction 之后塞了一个 `"continue"` user message 时为 true——**auto-compaction 触发时强制"再来一轮"**,避免用户感知到"我以为你说完了"。
- **`abortController.signal.aborted`**:用户在 TUI 按 Esc(`escapeEvents.on("user-escape", ...)` `subagent/executor.ts:113-117`)或 headless mode ctrl-c,立即返回当前累积的 `finalResponse`(`streamChatResponse.ts:332-334`)。

#### 4.3 显式 Exit 工具(CLI 专用)

- `extensions/cli/src/tools/exit.ts:1-25` 定义 `Exit` 工具:`"Exit the current process with status code 1, indicating a failure or error"`,**让 LLM 主动表示"我完成了 / 失败了"**。`exitTool.run` 调 `gracefulExit(1)`。
- **GUI 端没有 Exit 工具**——`core/tools/builtIn.ts` 19 个工具里没有 Exit,`clientTools` 也没有。
- **这不是 ReAct 的"标准 exit 动作"**,而是 Continue CLI 的工程取舍:headless 自动化场景下,LLM 跑完任务主动 `Exit` 触发进程退出,避免循环挂起。

#### 4.4 异常 / 网络中断

- **`streamNormalInput.ts:200-225`** 捕获 LLM 流式异常:`toolCallsToCancel.length > 0 && e.message.includes("premature close")` 时,所有 generating 的 tool_call 标记 errored,内容为 `"Premature Close" error: this tool call was aborted mid-stream...`。
- **`streamChatResponse.ts:330-335`** 处理 `AbortError`,直接返回已累积的 `aiResponse`。
- **`streamChatResponse.ts:204-206`**:若 `validation.isValid === false`(context 长度超限 + prune 也救不了),抛 `Context length validation failed: ${validation.error}` 终结 loop。

**核心结论**:Continue **没有显式的 "finish" / "complete" 标记**。退出靠**"LLM 不再生成 tool_call"**这个隐式信号 + 用户主动 abort + 异常兜底,模型自己决定何时停。

---

### Q5. Ask 模式

**Continue 的 Ask 模式 = CLI 端专属的 `AskQuestion` 工具**(`extensions/cli/src/tools/askQuestion.ts:1-58`),GUI 端**没有等价工具**。

#### 5.1 CLI AskQuestion 工具定义

```typescript
// extensions/cli/src/tools/askQuestion.ts:9-29
export const askQuestionTool: Tool = {
  name: "AskQuestion",
  displayName: "Ask Question",
  description: `Ask the user a clarifying question to gather requirements, preferences, or implementation details before proceeding.
Guidelines:
- You should use this tool **whenever you want to clarify your assumption or need answers to build your plan**.
- DO NOT supply "other" or "none of the above" or similar as an option...`,
  parameters: {
    type: "object",
    required: ["question", "options"],
    properties: {
      question: { type: "string", ... },
      options: {
        type: "array",
        description: "The list of choices. Leave as empty array if user should provide a free-form answer.",
        items: { type: "string" },
      },
      defaultAnswer: { type: "string", description: "Default answer if user presses Enter..." },
    },
  },
  readonly: true,
  isBuiltIn: true,
  run: async (args) => {
    const answer = await quizService.askQuestion({ question, options, defaultAnswer });
    return `User answered: "${answer}"`;
  },
};
```

**关键点**:
- `readonly: true` + 默认 `permission: "allow"`(`extensions/cli/src/permissions/defaultPolicies.ts:11`),无需用户审批直接弹出问答 UI。
- `quizService.askQuestion()`(`extensions/cli/src/services/QuizService.ts`)是 TUI 端的事件总线:推 question 到 TUI → 等用户在 stdin 输入答案 → 阻塞 resolve。
- 文档明示(`docs/cli/tool-permissions.mdx:13`):"`AskQuestion` is a built-in read-only tool that lets the agent **pause and ask for clarification before continuing**."

#### 5.2 Plan 模式下的特殊语义

- `PLAN_MODE_POLICIES`(`extensions/cli/src/permissions/defaultPolicies.ts:39-66`)显式 `AskQuestion: allow`——**Plan 模式下允许 LLM 用 AskQuestion 问澄清问题**。
- `DEFAULT_PLAN_SYSTEM_MESSAGE`(`defaultSystemMessages.ts:78-92`)"If the user wants to make changes, offer that they can switch to Agent mode"——但**没有**强制"plan 模式必须先用 AskQuestion 收集需求",这是 best-effort,不是 hard rule。

#### 5.3 GUI 端的等价机制

GUI 端**没有 AskQuestion 工具**,但有"工具调用前的 approval 弹窗"(`evaluateToolPolicies` 走 `allowedWithPermission` 时,VS Code 走 `extensions/vscode/src/.../ToolCallUI.tsx` 弹窗),功能上覆盖了"让用户对 agent 的下一步做决定"的场景。**但这是"批准 / 拒绝 tool call"**,不是"自由文本问答"。

**结论**:Continue 的 Ask 模式 = CLI 端 AskQuestion 工具,允许 LLM 在任何时刻暂停、向用户问选择题或自由题,得到答案后继续 loop。**与 Claude Code 的 `AskUserQuestion` / Gemini CLI 的 `ask_user` 是同一类功能**。

---

### Q6. Human-in-the-Loop (HITL)

**Continue 的 HITL = "工具调用前用户审批 + 批准即执行 + 拒绝即终止该 tool_call"**。Continue **不**有"在 agent loop 任意点暂停"的 hook,但**工具调用 = HITL 的主战场**。

#### 6.1 三档权限状态(GUI / IDE 端)

`core/index.d.ts` `ToolPolicy` + GUI `uiSlice.ts:DEFAULT_TOOL_SETTING` 共同定义:
- **`disabled`**:工具被完全屏蔽(不出现在 LLM 的 tool list 里)。
- **`allowedWithPermission`**(= 文档 "ask"):执行前弹窗,用户可 Approve / Reject。
- **`allowedWithoutPermission`**(= 文档 "allow"):自动执行,无弹窗。

#### 6.2 GUI 端 HITL 流程

1. **base policy 查表**(`evaluateToolPolicies.ts:39-48`):
   ```typescript
   const basePolicy = toolPolicies[toolName]                  // ① 用户在 UI 显式设的
                    ?? activeTools.find(t => t.function.name === toolName)?.defaultToolPolicy  // ② 工具默认
                    ?? DEFAULT_TOOL_SETTING;                  // ③ 兜底
   ```
2. **动态 policy 二次判定**(`evaluateToolPolicies.ts:51-58`):通过 IPC 调 `tools/evaluatePolicy` 让 core 端的 `evaluateToolCallPolicy(args)` 二次过滤(如 `run_terminal_command` 调 `@continuedev/terminal-security` 评估命令安全性,可能从 `allowedWithoutPermission` 升级到 `allowedWithPermission`,但**不能从 `disabled` 降级**)。
3. **分发执行**(`streamNormalInput.ts:262-280`):
   - `disabled` → `errorToolCall` + 输出 "Security Policy Violation",不执行。
   - `allowedWithPermission` → IDE 弹窗(``@toolcall-ui` `ToolCallConfirmation`),用户操作:
     - **Approve**:单次执行,不再弹。
     - **Approve + "Don't ask again"**:写入 `~/.continue/permissions.yaml`(`extensions/cli/...` CLI 走 `policyWriter.ts`)。
     - **Reject**:写入 `errorToolCall`,后续 LLM 看到 "Tool call was rejected" 决定下一步。
   - `allowedWithoutPermission` + `BUILT_IN_GROUP_NAME && readonly`(`streamNormalInput.ts:265-274`):Built-in 只读工具默认自动执行(readonly 是兜底白名单)。

#### 6.3 CLI 端 HITL 流程(`extensions/cli/src/permissions/`)

**5 层优先级**(`docs/cli/tool-permissions.mdx:55-59`):
1. **Mode policies**(`--auto` / `--readonly` / `--plan`)
2. **CLI flags**(`--allow` / `--ask` / `--exclude`)
3. **`permissions.yaml`**(`~/.continue/permissions.yaml`,持久化)
4. **Defaults**(`getDefaultToolPolicies(isHeadless)`)
5. **Wildcard `*` 兜底**

**工具匹配语法**(`permissionChecker.ts:12-60`):
- `Write` — 全匹配
- `Write(*)` — 显式全匹配
- `Write(**/*.ts)` — glob 模式匹配 primary argument
- `Bash(ls*)` — bash 命令前缀匹配(命令行以 `ls` 开头才 allow)
- 通配符 `*` / `?` 支持

**Headless 模式特殊行为**(`defaultPolicies.ts:38-46`):`isHeadless` 时所有 `ask` 自动降级为 `allow`(`{ tool: "*", permission: "allow" }`),因为没有人在 TUI 审批。

#### 6.4 工具调用时序(以 `run_terminal_command` 为例)

1. LLM 决定调 `run_terminal_command`,带 `command` arg。
2. `streamNormalInput.ts:177-201` `preprocessToolCalls` 走 core `tools/preprocessArgs`,处理参数(可能从 `~/foo` 解析为绝对路径,可能 reject 危险命令)。
3. `evaluateToolPolicies` 二次校验:core 端 `evaluateToolCallPolicy(basePolicy, args) → ToolPolicy`(`runTerminalCommandTool:64-71`)。
4. **用户决策**:
   - Approve:`callToolById` → `callBuiltInTool → runTerminalCommandImpl(args, extras)`。
   - Reject: `errorToolCall`,该 tool_call 的 `output` 写 "Tool call was rejected by user"(`sessionSlice.ts` 的对应 reducer)。
5. **loop 继续**:`streamResponseAfterToolCall`(`streamResponseAfterToolCall.ts:55-65`)等所有 tool_call 完成后 `dispatch streamNormalInput({ depth+1 })`,LLM 看到 `rejected` 上下文,通常会换方案或问用户。

**没有"在 tool execution 中途弹窗 / 取消"的 hook**——一旦 approve 提交,工具就会跑完(可能有 timeout 保护,见 `runTerminalCommand.ts`)。

---

### Q7. 工具调用权限

**三种权限(`disabled` / `allowedWithPermission` / `allowedWithoutPermission`)的实现是分层的,核心是 `defaultToolPolicy`(工具级静态)+ `evaluateToolCallPolicy`(参数级动态)+ 用户 `toolSettings`(per-tool override)+ 模式 override(mode policies)**。

#### 7.1 工具级静态 policy(在工具定义时)

```typescript
// core/tools/builtIn.ts:1-22
export enum BuiltInToolNames {
  ReadFile = "read_file",     // →  readFileTool definition
  EditExistingFile = "edit_existing_file",
  RunTerminalCommand = "run_terminal_command",
  ...
}

// core/tools/definitions/runTerminalCommand.ts:41-71
export const runTerminalCommandTool: Tool = {
  type: "function",
  displayTitle: "Run Terminal Command",
  readonly: false,
  group: BUILT_IN_GROUP_NAME,
  function: { ... },
  defaultToolPolicy: "allowedWithPermission",  // ← 工具级默认
  evaluateToolCallPolicy: (
    basePolicy: ToolPolicy,
    parsedArgs: Record<string, unknown>,
  ): ToolPolicy => {
    return evaluateTerminalCommandSecurity(
      basePolicy,
      parsedArgs.command as string,  // ← 动态安全检查
    );
  },
  ...
};
```

`@continuedev/terminal-security`(`extensions/cli/src` 也有引用)是独立 npm 包,负责按 `command` 内容动态判定 policy(可能把 `allowedWithoutPermission` 升级为 `allowedWithPermission`,**但不能把 `disabled` 降级**——见 `evaluateToolPolicies.ts:62-77` "Ensure dynamic policy cannot be more lenient than base policy")。

#### 7.2 用户级 per-tool override(GUI)

- GUI 端用户在 "Tool Policies" notch / 配置面板里给具体 tool 设置 `toolPolicies[toolName] = "disabled" | "allowedWithPermission" | "allowedWithoutPermission"`。
- 存储在 `uiSlice.ts` Redux state,刷新页面后通过 `~/.continue/config.yaml` 的 `experimental.` 或专用字段持久化(具体持久化字段未在 1.3.40 中明确,推测走 `GlobalContext` JSON)。

#### 7.3 模式 override(Mode-based Policies)

- **GUI**:`MessageModes` 切换不直接改 tool list,但**通过 system message 引导 LLM** + `getBaseSystemMessage` 注入 `NO_TOOL_WARNING`(chat 模式无工具时 `getBaseSystemMessage.ts:30-32`)。
- **CLI**:`PLAN_MODE_POLICIES`(`defaultPolicies.ts:39-66`)在 plan 模式下 `exclude` 写工具;`AUTO_MODE_POLICIES`(第 70-72 行)全 allow;`getDefaultToolPolicies(isHeadless)`(第 5-37 行)headless 模式全 allow;`enabled`(默认) 模式给 read 工具 allow,write 工具 ask。

#### 7.4 整体权限解析算法(GUI 端)

```typescript
// gui/src/redux/thunks/evaluateToolPolicies.ts:33-99 (简化)
async function evaluateToolPolicy(activeTools, toolCallState, toolPolicies) {
  // 1. Edit 类工具硬豁免(永远 allowedWithoutPermission)
  if (isEditTool(name)) return { policy: "allowedWithoutPermission" };

  // 2. 查表:用户设置 > 工具 default > DEFAULT_TOOL_SETTING
  const basePolicy = toolPolicies[name]
                 ?? activeTools.find(t => t.name === name).defaultToolPolicy
                 ?? DEFAULT_TOOL_SETTING;

  // 3. 动态二次校验
  const dynamicPolicy = await ideMessenger.request("tools/evaluatePolicy", {
    basePolicy, parsedArgs, processedArgs,
  });

  // 4. 兜底:dynamic 不能比 base 更宽松
  if (basePolicy === "disabled") return { policy: "disabled" };
  if (basePolicy === "allowedWithPermission"
      && dynamicPolicy === "allowedWithoutPermission") {
    return { policy: "allowedWithPermission" };
  }
  return { policy: dynamicPolicy };
}
```

#### 7.5 关键设计取舍

1. **Edit 类工具硬豁免**(`isEditTool` 在 `evaluateToolPolicies.ts:21`):用户调 "edit file" 不弹窗,因为 IDE 端有 diff preview,用户可以 apply/reject,**审批职责前移到 IDE diff UI**。这是**为 IDE 形态定制的取舍**——CLI 端 `Edit` 工具仍 `ask`(`defaultPolicies.ts:7`)。
2. **Built-in + readonly 自动批准**(`streamNormalInput.ts:265-274`):只读工具即使是 `allowedWithPermission`,也自动跑(readonly 不可能破坏环境)。**但**这有个细节:这只在 `needsApprovalPolicies.length > 0`(有需要审批的工具)**且**有 readonly 工具时触发,纯 readonly 集合走 `Promise.all(callToolById)` 自动并发(`streamNormalInput.ts:282-288`)。
3. **Sub-agent 全 allow**(`subagent/executor.ts:85`):TODO 注释明说"未来想加 prompt 询问",**当前是裸跑**。

---

### Q8. 上下文压缩和摘要

**Continue 是双层压缩机制:IDE 端用 `compactConversation`(`core/util/conversationCompaction.ts`)做"手动手动触发 / 自动 inline 摘要";CLI 端用 `compaction.ts` 做"80% 阈值自动 + 多次检查点 + auto-continuation"**。

#### 8.1 IDE 端(显式 + 内联)

- **入口**:`core/util/conversationCompaction.ts:1-114` `compactConversation({ sessionId, index, historyManager, currentModel })`。
- **触发方式**:
  - **手动**:用户在 GUI 点 "Compact" 按钮(`/compact` slash command)→ 走 `core/core.ts:631` 的 `compactConversation`。
  - **自动 inline**:`core/core.ts:587-602` `llm/compileChat` 阶段前会检查 `if (chatHistory.length > 1 && tokens > context_length)`,触发 inline prune(不是 compaction,是直接 `pruneLastMessage`)。
- **算法**(`conversationCompaction.ts:35-90`):
  1. 找最近的 `conversationSummary` 标记作为 baseline。
  2. 把 baseline 之后到目标 index 的所有 message 序列化,作为 LLM 输入。
  3. 调 `currentModel.chat()` 用一段 prompt 让 LLM 生成 6 维度 summary(Conversation Overview / Active Development / Technical Stack / File Operations / Solutions & Troubleshooting / Outstanding Work)。
  4. 把 summary 写入 `updatedHistory[index] = { message: { role: "assistant", content: summary }, conversationSummary: summary }`。
- **核心数据结构**:`ChatHistoryItem.conversationSummary: string`(`core/index.d.ts` / `core/index.js` 中),**有 summary 的 message 充当"checkpoint"**——下次 compaction 只 summarie 之后的。

#### 8.2 CLI 端(自动 + 3 个检查点 + auto-continuation)

`extensions/cli/src/compaction.ts` + `streamChatResponse.compactionHelpers.ts` 是**最完整的自动 compaction 实现**,有 3 个检查点:

1. **Pre-API compaction**(`handlePreApiCompaction`):每次调 LLM 之前,如果 `shouldAutoCompact`(`compaction.ts:226-264`)返回 true:
   ```typescript
   // compaction.ts:226-264
   const inputTokens = countTotalInputTokens({chatHistory, systemMessage, tools, model});
   const compactionThreshold = contextLimit - maxTokens - compactionBuffer;
   // buffer = max( maxTokens, ceil(0.2 * (contextLimit - maxTokens)) ), cap at 15000
   // 即"剩 20% 时触发",但 buffer 至少 15000 tokens
   const shouldCompact = inputTokens >= compactionThreshold;
   ```
2. **Post-tool validation**(`handlePostToolValidation`):tool 执行完后重新校验 context,超限则 prune / compact(`compactionHelpers.ts:88-118`)。
3. **Normal 80% auto-compaction**(`handleNormalAutoCompaction`,`compactionHelpers.ts:176-216`):只在 `shouldContinue=true`(还有 tool_call 准备跑)时检查,避免最后一轮浪费。
4. **Auto-continuation**(`streamChatResponse.ts:74-100` + `handleAutoContinuation`):**compaction 发生时自动塞一条 user message `"continue"`,让 agent 在新 compact context 下继续跑**,避免用户感知"我说完了"。

**实际触发比例** = `AUTO_COMPACT_BUFFER_RATIO = 0.8`(`compaction.ts:30`),即"用满 80% 时 compaction";上限 `AUTO_COMPACT_BUFFER_CAP = 15000 tokens`(`compaction.ts:29`)。

#### 8.3 关键设计取舍

1. **Compaction 是 LLM-driven**(再调一次 LLM 生成 summary),**不是机械式 truncate**——这意味着 cost 但语义更连贯。`compactChatHistory`(`compaction.ts:46-148`)显式用 `COMPACTION_PROMPT`(157 tokens) + 完整 history 调一次 `streamChatResponse(isCompacting: true)`,这个 compaction 本身又是**一次 `streamChatResponse` 调用**——递归用 loop 来压缩 loop。
2. **`pruneLastMessage`**(`compaction.ts:204-225`):当 summary 救不了(单条 message 都太大)时,机械地从头删 message,**但保持"末尾必须是 assistant 或 tool message"**的 OpenAI 协议约束,避免 `role=tool` 找不到对应 `tool_call_id` 的孤儿。
3. **没有 tool result 截断**:与 Hermes / OpenClaw 不同,Continue **没有 per-tool result 截断 + spill-to-disk 机制**;`readFileLimit.ts:8-19` 只对 `read_file` 单一工具做"半 context 长度"的 throw 限制,不是流式截断。`runTerminalCommand` 默认没有截断(可被 IDE 端 terminal output buffer 间接限制)。
4. **Compaction 嵌套安全**:`streamChatResponse.compactionHelpers.ts:46-48` 用 `isCompacting` flag 防止 compaction 内部再触发 compaction(死循环)。

---

### Q9. 其他亮点

#### 9.1 AGENTS.md / AGENT.md / CLAUDE.md 兼容 3 种命名

**这是 Continue 最具差异化的设计之一**。证据链:

```typescript
// core/config/markdown/loadMarkdownRules.ts:13
export const SUPPORTED_AGENT_FILES = ["AGENTS.md", "AGENT.md", "CLAUDE.md"];

// loadMarkdownRules.ts:21-43
for (const workspaceDir of workspaceDirs) {
  let agentFileFound = false;
  for (const fileName of SUPPORTED_AGENT_FILES) {  // ← 顺序:AGENTS.md → AGENT.md → CLAUDE.md
    try {
      const agentFileUri = joinPathsToUri(workspaceDir, fileName);
      const exists = await ide.fileExists(agentFileUri);
      if (exists) {
        const agentContent = await ide.readFile(agentFileUri);
        const rule = markdownToRule(agentContent, {...});
        rules.push({
          ...rule,
          source: "agentFile",
          sourceFile: agentFileUri,
          alwaysApply: true,  // ← 关键:agent file 永远 alwaysApply
        });
        agentFileFound = true;
      }
      break;  // 找到就停,优先顺序:AGENTS > AGENT > CLAUDE
    } catch (e) {}
  }
  if (agentFileFound) break;  // 第一个 workspace 找到就停
}
```

**与 Onion Agent 关联**:Onion 应该借鉴这种"**多命名 fallback + 顺序约定**",但要注意:
- **文件级 fallback** 与"扫描到 .git 边界全部加载"是**互斥策略**——Continue 选了"**单文件 + 顺序 fallback**",没有"向上扫描全部父目录 AGENTS.md"。Onion 可以保留 Continue 的"单文件"简化,也可以结合 Codex `project_doc_max_bytes=32 KiB` 加字节上限。
- **`alwaysApply: true`**:Continue 把 agent file 强制 alwaysApply,意味着**整个 session 全程注入 system message**。对 Onion 来说,如果 user 写了几 MB 的 AGENTS.md,会立刻撑爆 context——必须配字节上限(Codex 32 KiB)。

**`isContinueConfigRelatedUri`**(`core/config/loadLocalAssistants.ts:23-32`)把 `AGENTS.md` / `AGENT.md` / `CLAUDE.md` 也当作 Continue config 的一部分,被 indexing 排除(`walkDir.ts` 跳过),**防止 agent file 被自己索引**。

#### 9.2 `.continuerc.json { disableIndexing: true }` 防自索引

**经典的好做法,Onion 必须借鉴**。证据:

```typescript
// core/util/paths.ts:210-224
export function getContinueRcPath(): string {
  // Disable indexing of the config folder to prevent infinite loops
  const continuercPath = path.join(getContinueGlobalPath(), ".continuerc.json");
  if (!fs.existsSync(continuercPath)) {
    fs.writeFileSync(
      continuercPath,
      JSON.stringify({ disableIndexing: true }, null, 2),
    );
  }
  return continuercPath;
}
```

**机制**:
- `extensions/vscode/src/activation/activate.ts:23-24` 在扩展激活时**立刻**调用 `getContinueRcPath()`(配合 `getTsConfigPath()`),**这是 VS Code 扩展启动后最早会落盘的全局动作**。
- `getContinueRcPath()` 在 `~/.continue/.continuerc.json` 写 `{ "disableIndexing": true }`,这是个**哨兵文件**——`walkDir.ts:200-220` 看到 `.continuerc.json` 时,会把 `disableIndexing` 字段注入 ignore context,**跳过整个 `~/.continue/` 的 indexing**。
- 这避免了"`~/.continue/index/` 越扫越大 → trigger 重新扫 → 越来越大的死循环"`。

**Onion 关联**:
- Onion 若做 RAG / 代码索引,必须做同样的"`~/.onion/.onionrc.json` 哨兵 + disableIndexing"机制(参考 §3.3)。
- 配合 file_backend 调研报告的"四类空间"原则,index 必须和 config / state / secrets 物理隔离,否则单次配置变更就触发全量 reindex。

#### 9.3 local model + cloud model 混用

**Continue 的 Provider 体系是"协议中立 + Provider 无关"**——`core/llm/llm.ts` 是抽象基类,`core/llm/llms/` 下有 50+ provider 实现:

| 类别 | 典型实现 | 文件 |
|---|---|---|
| **OpenAI 兼容** | OpenAI / Azure / OpenRouter / Together / Fireworks / Deepseek / Groq / xAI / 智谱 GLM / DeepInfra | `core/llm/llms/OpenAI.ts`、`OpenAI-compatible.ts` 等 |
| **Anthropic** | Anthropic / Bedrock(Anthropic 模式) | `core/llm/llms/Anthropic.ts` |
| **Google** | Gemini / Vertex AI | `core/llm/llms/Gemini.ts`、`VertexAI.ts` |
| **本地 LLM** | Ollama / LlamaCpp / LMStudio / Msty / vLLM / Transformers.js | `core/llm/llms/Ollama.ts`、`LlamaCpp.ts`、`TransformersJsEmbeddingsProvider.ts` |
| **企业平台** | Cohere / WatsonX / HuggingFace / SageMaker | `core/llm/llms/Cohere.ts`、`WatsonX.ts` |

**混用关键点**:
1. **Per-role model selection**(`docs/customize/model-roles.mdx`):用户可以为 `chat` / `edit` / `apply` / `autocomplete` / `embeddings` / `rerank` / `plan` / `background` 8 个 role 各自选不同模型。**`config.yaml` 里的 `models:` 数组,每条带 `roles: [chat, edit]` 字段**(`core/index.d.ts:1910-1913` 的 `"default-plan" | "model-options-plan"` 是 plan role 专用 schema)。
2. **Prompt-as-tool fallback**:Continue 检测 `useNativeTools`(`streamNormalInput.ts:131-138`):`onlyUseSystemMessageTools=true` 或模型不支持 native tools 时,自动 fallback 到 `SystemMessageToolCodeblocksFramework`(`systemMessageTools/toolCodeblocks/index.ts`),把工具 schema 文本塞进 system message,让 LLM 用 ```tool code block 输出。**这是 Continue 给本地弱模型(Qwen 7B / GLM 4)的兼容路径**。
3. **Provider 无关的协议中立**:`fromChatCompletionChunk`(`openaiTypeConverters.ts:357-389`)把 OpenAI 风格的 `delta.tool_calls` 累积为 Continue 内部 `ToolCallState`;`Anthropic.ts:303-378` 把 Anthropic 的 `input_json_delta` 走同样 pipeline。**Provider 切换 = 换 llm.ts 子类,工具实现零改动**。
4. **Hub 加载**(企业场景):`extensions/cli/src/services/AgentFileService.ts:64-80` 走 `loadPackageFromHub(slug)` 远程拉 agent definition,支持 `cn` 一行命令加载远端"agent 包"。

#### 9.4 企业版 Continue for Teams

证据:
- **`~/.continue/.configs/<hostname>/`** 远端 config 缓存(`core/util/paths.ts:342-370`):`getRemoteConfigsFolderPath()` 按 `remoteConfigServerUrl` 的 hostname 分目录,把团队共享的 `config.json` / `config.js` 拉到本地,**与本地 `~/.continue/config.yaml` 合并**(`docs/customize/deep-dives/configuration.mdx` 多处提及)。
- **共享 config + RBAC**:`docs/` 大量提到 "Continue for Teams" 的 SSO / audit / role-based access,源码里散落在 `core/.../enterprise` 子目录(本次调研未深入,推测是订阅 gating + telemetry 上报)。
- **MCP OAuth 2.1 + PKCE**(`core/context/mcp/MCPOauth.ts`):企业部署需要 OAuth 走企业 IdP。
- **审计日志**(`core/data/devdataSqlite.ts`):`devdata.sqlite` 记录所有 chatInteraction / tool call / file edit,企业版可能对接 SIEM。

**与 Onion Agent 关联**:
- Continue 的"**远端 config 缓存**"是 Onion P1 阶段可以借鉴的:onion 可以定义 `ONION_TEAMS_URL` env,启动时从远端拉 `team.yaml`(角色 / 工具白名单 / 共享 skills),本地合并 + 缓存到 `~/.onion/.team/<host>/`,**实现"团队配置零拷贝下发"**。
- Continue 的"**per-user 隔离缺失**"是反例:`GlobalContext` 是单文件,没有 user_id / tenant_id 概念,Onion 如果做"信创合规多用户"必须做严格 user 隔离。

#### 9.5 agents/ 目录(Rule Bundle 概念)

`docs/customize/agents.mdx` + 仓库根 `.continue/agents/` 的 5 个示例(`breaking-change-detector.md` / `dependency-security-review.md` / `error-message-quality.md` / `input-validation.md` / `test-coverage.md`):

```yaml
# .continue/agents/breaking-change-detector.md
---
name: Breaking Change Detector
description: Flag renamed commands, APIs, or config options with stale references
---

# Breaking Change Detector

Analyze this pull request for breaking changes...
```

**这是"frontmatter + markdown 描述的 task-specific prompt bundle"**。`loadMarkdownRules.ts` 把它们当作 Rule(带 `description` 字段),`getSystemMessageWithRules` 的 glob/regex 匹配命中时,自动注入 system message。

**与 Sub-agent 的区别**:
- **agents/*.md** = "任务专用 prompt 注入",**没有独立 runtime**——主 agent 读完这些 prompt 自己去执行任务。
- **Sub-agent (CLI)** = "调 `Subagent` 工具时启动独立 child session",**有独立 runtime**——主 agent 把任务完全委托,等结构化结果。

**Onion 关联**:
- "**agents/*.md = frontmatter 描述的 prompt bundle**"是 P1 阶段可以做的"Onion skills"——`~/.onion/agents/<slug>.md` + `<repo>/.onion/agents/<slug>.md`,LLM 用 `description` 判断何时拉取(`apply_intelligently` 模式,需要 `read_skill` 工具配合,见 `core/tools/builtIn.ts` `ReadSkill`)。

#### 9.6 其他工程化亮点

- **工具注册函数化**(`core/tools/index.ts:1-13`):作者**自承踩坑 3 次**——`export const getBaseToolDefinitions = () => [...]` 写成函数而非 module-level const,**避免 reload 时重复定义**。Onion 在做 plugin 系统时同样要注意:工具列表必须是函数,不能是 module-level const。
- **Protocol 抽象**(`core/protocol/`):`ToCoreProtocol` / `FromCoreProtocol` 是 TypeScript discriminated union 描述的双向消息协议,IDE ↔ core 通信走 typed message,新加 IPC 端点只要扩 union 即可。
- **System message 三态**:`getBaseSystemMessage`(`getBaseSystemMessage.ts:21-25`)对 `agent` / `plan` / 其他 三种 mode 各选一个 base message,**不**做"if 嵌套",**Open/Closed 友好**。
- **PII 兜底**:`continueai 0 命中` 在 continue.config.json 中不存 PII,纯 API key + 模型 + 配置。
- **测试体系**:`core/util/conversationCompaction.ts` / `streamResponse*.test.ts` 等大量 vitest 单测,覆盖率 60%+(根据 `package.json:scripts.test` 推断)。
- **双协议工具 schema**:`SystemMessageToolCodeblocksFramework.toolToSystemToolDefinition`(`toolCodeblocks/index.ts:43-66`)把 JSON schema 转成 markdown 文本格式,LLM 在 prompt-as-tool 模式下读 markdown 而不是 JSON。

---

## 3. 关键代码片段

### 3.1 IDE 主循环入口(Thunk 调度)

```typescript
// gui/src/redux/thunks/streamNormalInput.ts:85-280
export const streamNormalInput = createAsyncThunk(
  "chat/streamNormalInput",
  async ({ legacySlashCommandData, depth = 0 }, { dispatch, extra, getState }) => {
    if (process.env.NODE_ENV === "test" && depth > 50) {
      throw new Error(`Max stream depth of ${50} reached in test`);
    }
    // ...
    const useNativeTools = state.config.config.experimental?.onlyUseSystemMessageTools
      ? false
      : modelSupportsNativeTools(selectedChatModel);
    const systemToolsFramework = !useNativeTools
      ? new SystemMessageToolCodeblocksFramework()
      : undefined;
    // ...
    let gen = extra.ideMessenger.llmStreamChat({...}, streamAborter.signal);
    if (systemToolsFramework && activeTools.length > 0) {
      gen = interceptSystemToolCalls(gen, streamAborter, systemToolsFramework);
    }
    let next = await gen.next();
    while (!next.done) {
      if (!getState().session.isStreaming) { dispatch(abortStream()); break; }
      dispatch(streamUpdate(next.value));
      next = await gen.next();
    }
    // ...
    // 工具调用后递归 streamResponseAfterToolCall
  },
);
```

### 3.2 工具调用后递归

```typescript
// gui/src/redux/thunks/streamResponseAfterToolCall.ts:54-82
if (assistantMessage && areAllToolsDoneStreaming(assistantMessage, ...)) {
  unwrapResult(await dispatch(streamNormalInput({ depth: depth + 1 })));
}
```

### 3.3 工具注册函数化(踩坑注释)

```typescript
// core/tools/index.ts:1-13
// I'm writing these as functions because we've messed up 3 TIMES by pushing to const,
// causing duplicate tool definitions on subsequent config loads.
export const getBaseToolDefinitions = () => [
  toolDefinitions.readFileTool,
  toolDefinitions.createNewFileTool,
  toolDefinitions.runTerminalCommandTool,
  toolDefinitions.globSearchTool,
  toolDefinitions.viewDiffTool,
  toolDefinitions.readCurrentlyOpenFileTool,
  toolDefinitions.lsTool,
  toolDefinitions.createRuleBlock,
  toolDefinitions.fetchUrlContentTool,
];
```

### 3.4 Plan 模式 system message

```typescript
// core/llm/defaultSystemMessages.ts:78-92
export const DEFAULT_PLAN_SYSTEM_MESSAGE = `
<important_rules>
  You are in plan mode, in which you help the user understand and construct a plan.
  Only use read-only tools. Do not use any tools that would write to non-temporary files.
  If the user wants to make changes, offer that they can switch to Agent mode...

  In plan mode, only write code when directly suggesting changes. Prioritize understanding and developing a plan.
</important_rules>`;
```

### 3.5 AGENTS.md / AGENT.md / CLAUDE.md 多命名 fallback

```typescript
// core/config/markdown/loadMarkdownRules.ts:11-43
export const SUPPORTED_AGENT_FILES = ["AGENTS.md", "AGENT.md", "CLAUDE.md"];

for (const workspaceDir of workspaceDirs) {
  let agentFileFound = false;
  for (const fileName of SUPPORTED_AGENT_FILES) {
    try {
      const exists = await ide.fileExists(joinPathsToUri(workspaceDir, fileName));
      if (exists) {
        const content = await ide.readFile(...);
        rules.push({
          ...markdownToRule(content, {...}),
          source: "agentFile",
          sourceFile: ...,
          alwaysApply: true,
        });
        agentFileFound = true;
      }
      break;  // 第一个找到就停
    } catch (e) {}
  }
  if (agentFileFound) break;
}
```

### 3.6 `.continuerc.json` 防自索引

```typescript
// core/util/paths.ts:210-224
export function getContinueRcPath(): string {
  // Disable indexing of the config folder to prevent infinite loops
  const continuercPath = path.join(getContinueGlobalPath(), ".continuerc.json");
  if (!fs.existsSync(continuercPath)) {
    fs.writeFileSync(continuercPath, JSON.stringify({ disableIndexing: true }, null, 2));
  }
  return continuercPath;
}
```

### 3.7 工具 permission 三档 + 动态二次判定

```typescript
// gui/src/redux/thunks/evaluateToolPolicies.ts:21-99
async function evaluateToolPolicy(activeTools, toolCallState, toolPolicies) {
  if (isEditTool(toolCallState.toolCall.function.name)) {
    return { policy: "allowedWithoutPermission", toolCallState };
  }
  const basePolicy = toolPolicies[name]
    ?? activeTools.find(t => t.function.name === name)?.defaultToolPolicy
    ?? DEFAULT_TOOL_SETTING;
  const result = await ideMessenger.request("tools/evaluatePolicy", {
    toolName, basePolicy, parsedArgs, processedArgs,
  });
  if (result.status === "error") return { policy: "disabled", toolCallState };
  const dynamicPolicy = result.content.policy;
  // 兜底:dynamic 不能比 base 更宽松
  if (basePolicy === "disabled") return { policy: "disabled", displayValue, toolCallState };
  if (basePolicy === "allowedWithPermission" && dynamicPolicy === "allowedWithoutPermission") {
    return { policy: "allowedWithPermission", displayValue, toolCallState };
  }
  return { policy: dynamicPolicy, displayValue, toolCallState };
}
```

### 3.8 CLI AskQuestion 工具

```typescript
// extensions/cli/src/tools/askQuestion.ts:9-50
export const askQuestionTool: Tool = {
  name: "AskQuestion",
  description: `Ask the user a clarifying question to gather requirements...`,
  parameters: {
    type: "object",
    required: ["question", "options"],
    properties: {
      question: { type: "string" },
      options: { type: "array", items: { type: "string" } },
      defaultAnswer: { type: "string" },
    },
  },
  readonly: true,
  isBuiltIn: true,
  run: async ({ question, options, defaultAnswer }) => {
    const answer = await quizService.askQuestion({ question, options, defaultAnswer });
    return `User answered: "${answer}"`;
  },
};
```

### 3.9 Sub-agent 执行(隔离 + 复用 loop)

```typescript
// extensions/cli/src/subagent/executor.ts:53-145
export async function executeSubAgent(options) {
  const { agent: subAgent, prompt, abortController, onOutputUpdate } = options;
  // 1. 临时把权限改成全 allow
  serviceContainer.set<ToolPermissionServiceState>(SERVICE_NAMES.TOOL_PERMISSIONS, {
    ...mainAgentPermissionsState,
    permissions: { policies: [{ tool: "*", permission: "allow" }] },
  });
  // 2. 覆盖 system message(注入 subagent 的 baseSystemMessage)
  const systemMessage = await buildAgentSystemMessage(subAgent, services);
  // 3. 临时禁用 chatHistorySvc
  if (chatHistorySvc && originalIsReady) {
    chatHistorySvc.isReady = () => false;
  }
  // 4. 复用 streamChatResponse
  await streamChatResponse(chatHistory, model, llmApi, abortController, callbacks, false);
  // 5. 恢复原状态
  // ... restore
}
```

### 3.10 CLI 80% auto-compaction 触发条件

```typescript
// extensions/cli/src/compaction.ts:226-264
export const AUTO_COMPACT_BUFFER_CAP = 15_000;
export const AUTO_COMPACT_BUFFER_RATIO = 0.8;

export function shouldAutoCompact({ chatHistory, model, systemMessage, tools }) {
  const inputTokens = countTotalInputTokens({ chatHistory, systemMessage, tools, model });
  const contextLimit = getModelContextLimit(model);
  const maxTokens = getModelMaxTokens(model);
  const ratioCompactionBuffer = Math.ceil(
    (1 - AUTO_COMPACT_BUFFER_RATIO) * (contextLimit - maxTokens),
  );
  const safeCompactionBuffer = Math.max(maxTokens, ratioCompactionBuffer);
  const compactionBuffer = Math.min(safeCompactionBuffer, AUTO_COMPACT_BUFFER_CAP);
  const compactionThreshold = contextLimit - maxTokens - compactionBuffer;
  return inputTokens >= compactionThreshold;
}
```

### 3.11 模式切换(Plan / Agent / Chat)UI

```tsx
// gui/src/components/ModeSelect/ModeSelect.tsx:30-45
const cycleMode = useCallback(() => {
  if (mode === "chat") dispatch(setMode("plan"));
  else if (mode === "plan") dispatch(setMode("agent"));
  else dispatch(setMode("chat"));
}, [mode, mainEditor]);
// 快捷键:Cmd/Ctrl + . 切下一个 mode
```

---

## 4. 与 Onion Agent 设计的关联

| Continue 做法 | Onion Agent 可借鉴 / 需警惕的点 |
|---|---|
| **IDE 嵌入式 + CLI 双形态**(`gui/` + `extensions/cli/` 各自一份 loop) | Onion MVP 阶段建议只做 **CLI + 一个 IDE**(避免双实现漂移);Continue 的 JetBrains Kotlin 端**自承"out of sync with core/util/paths.ts"** 是巨大反例。 |
| **递归 thunk 实现循环**(`streamNormalInput` ↔ `streamResponseAfterToolCall` 互相 dispatch) | Onion 借鉴:**用 Python `@dataclass` session + `while should_continue: llm_call()` 显式 while-loop 即可**,不需要重 Redux;但要注意 `depth > 50` 的硬上限,**Onion 必须设防栈溢出**(CLI Python 递归深度 1000 不怕,但可以借鉴 50 这个保守值)。 |
| **Plan 模式 = 切换 system message + 过滤工具** | Onion P1 阶段借鉴:`MODE_PLAN_SYSTEM_MESSAGE` + `set_active_tools(filter=readonly_only)`。**不**做"先 plan 再 implement"两阶段 loop——继续把"plan 输出"等同于一次普通 assistant 回答,等用户切 mode。 |
| **AGENTS.md / AGENT.md / CLAUDE.md 3 命名 fallback** | **必做**。Onion 至少支持 `ONION.md` + `AGENTS.md`,优先级 AGENTS > ONION(同 Continue 顺序),`alwaysApply=true` 但**必须配字节上限**(Codex 32 KiB,Continue 没显式配 → Onion 必须修)。 |
| **`.continuerc.json { disableIndexing: true }` 防自索引** | **必做**。Onion 的 `~/.onion/.onionrc.json` 必须有 `disable_indexing: true` 哨兵,index 路径(`~/.onion/index/`)严格隔离。 |
| **local + cloud 混用 + Per-role model** | **必做**。Onion 至少支持 `chat` / `edit` / `embedding` / `summary` 4 个 role 各自选模型;`~/.onion/onion.json` 的 `models: [{ name, provider, roles: [...] }]`。 |
| **Sub-agent = 复用 loop + 改 system message + 改权限** | P2 借鉴:Onion 可以做 `delegate_task` 工具,子 session 复用 Onion 的 AgentLoop 类,**传不同的 system_prompt + tool list**;但要补"sub-agent 跑完不持久化 session 文件"(Continue 也不持久化)。 |
| **Permission 3 档 + dynamic 二次判定** | **必做**。Onion 建议 `disabled` / `ask` / `allow` 三档;`@continuedev/terminal-security` 的 dynamic 判定逻辑可以移植为 Onion 的 `policy_engine.py`(`base_policy` 不能比 `dynamic_policy` 更宽松)。 |
| **Edit 工具硬豁免 approval**(走 IDE diff UI) | P1 借鉴:Onion 写文件工具可以走"preview diff + apply"模式(类似 Aider / Continue),`write_file` 不弹 approval,改成"diff 渲染 + 用户 apply/reject"两阶段。 |
| **Auto-compaction @ 80% + auto-continuation** | **必做**。Onion P1 必须有自动 compaction(避免长 session 撞 context 上限),**用 LLM 重新生成 summary**(不机械 truncate),**compaction 触发后自动 inject `continue` 消息**避免用户感知中断。 |
| **`<ListboxOption value="plan">Read-only/MCP tools available</ListboxOption>` + 模式三态** | Onion 借鉴:`onion config mode` 子命令切 chat / plan / agent,**plan 模式在 system message + tool list 两处同时限制**。 |
| **Prompt-as-tool fallback for local model**(`SystemMessageToolCodeblocksFramework`) | P1 借鉴:Onion 的 Qwen / GLM 本地模型常漏 tool_call,可以用 `tool-call-repair` + GBNF grammar 强制 JSON 输出;**但 Onion 应该优先用 OpenAI / Anthropic 原生 tool API**,prompt-as-tool 仅为 fallback。 |
| **多进程 IPC 抽象**(`InProcessMessenger` / `VsCodeMessenger`) | P2 借鉴:Onion 若做 IDE 端,可以用 `pyzmq` / `asyncio.subprocess` 实现 core ↔ webview 通信,API 用 Pydantic 严格 typed。 |
| **`toolPolicies[name] ?? defaultToolPolicy ?? DEFAULT` 三层 fallback** | Onion 借鉴:permission resolve 算法 = `user_config[tool] ?? tool_def.default ?? global_default`,**三层 fallback** 简单清晰。 |
| **JetBrains 端独立 Kotlin 实现** | **反例**。Onion **不**做多端 fork,只做 Python 单实现 + IDE 薄适配。 |
| **Continue 1.3.40 没有 tool result 截断** | Onion **必须做**(file_backend 调研也有此结论):per-tool 阈值 + workspace 持久化 + retrieval hint,参考 Hermes / OpenClaw。 |
| **Continue 没有 sub-agent 拓扑(Manager/Worker)** | Onion **不学**——用户洋葱哲学"agent loop 自动累加器",sub-agent 是平级一次性委派够用,不上复杂拓扑。 |
| **Continue `AGENTS.md` 没有字节上限** | Onion **必做上限**(Codex 32 KiB),防 context 爆炸。 |
| **Continue 的 Plan 模式不强制先 AskQuestion** | Onion P1 可学:Plan 模式下"LLM 觉得需要问就调 `ask_user`"(Continue best-effort 风格,不强制) vs "Plan 模式第一步必须 AskQuestion"(Claude Code 风格,更结构化)— Onion 取前者,符合"agent loop 自动累加器"哲学。 |

---

## 5. 不确定 / 未找到

1. **GUI 端权限的持久化字段未明确**:`uiSlice.ts` 的 `toolPolicies` 是 in-memory Redux state,**没有看到显式写回 `~/.continue/config.yaml` 或 `~/.continue/globalContext.json` 的代码路径**。推测通过 `setToolPolicy` action 走 `ideMessenger.request` → core 端 → `GlobalContext.update`,但本次调研未走通整条链路。
2. **`AGENTS.md` / `AGENT.md` / `CLAUDE.md` 的字节上限**:Continue 把它们强制 `alwaysApply: true`,但**没有配 `project_doc_max_bytes` 类的硬截断**——意味着用户写几 MB 的 AGENTS.md 会撑爆 context。这是 Continue 的**已确认缺陷**,Onion 必须修。
3. **JetBrains 端与 core 端同步状态**:`extensions/intellij/.../ServerConstants.kt:1-3` 自承 "out of sync with core/util/paths.ts",但**Agent Loop 层面的同步状态未声明**;推测 JetBrains 端的工具调用走 `binary/...` Node.js sidecar + IPC,而不是纯 Kotlin 实现,但本次未深入 JetBrains 源码。
4. **GUI 端的 `selectActiveTools` 选择器实现**:`gui/src/redux/selectors/selectActiveTools.ts`(推测存在)的具体 filter 逻辑(按 mode 过滤 readonly)本次未直接 read,**功能描述基于 `ModeSelect.tsx` tooltip 推断**。需要 read 该文件确认是否对 plan mode 实际过滤了 `readonly: false` 工具。
5. **`StreamMessageQueue` 的并发控制**:`extensions/cli/src/stream/messageQueue.ts`(推测)是 CLI 并发流式 chunk 的合并器,具体并发模型未深入。
6. **Continue for Teams 的企业版 gating**:`core/.../enterprise` 路径本次未定位到具体文件,只看到 `~/.continue/.configs/<host>/` 缓存结构 + `docs/` 大量提及。推测是企业版 subscription check + remote config 同步。
7. **Tool policy 升级 dynamic 不能比 base 更宽松**(`evaluateToolPolicies.ts:62-77`):是 GUI 端硬约束,但 CLI 端 `permissionChecker.ts:106-120` 走 `permissionPolicyToToolPolicy + tool.evaluateToolCallPolicy(basePolicy, args)`,CLI 端**允许 dynamic 覆盖 base**(代码注释 "user preference wins - return the original base permission" 但同时 "If dynamic evaluation says disabled, that ALWAYS takes precedence"——逻辑微妙,**两端语义不完全一致**)。Onion 做 permission 时要决定走哪条路线。
8. **Sub-agent 状态隔离**:`executor.ts:75-83` 用 `chatHistorySvc.isReady = () => false` 临时禁用 service,但**没有真正的"独立 child session 文件"**;**主 agent 看到的是单条长 tool_result 字符串**,不是结构化 plan 节点。这是 Continue 的简化处理,Onion 决定是否走更结构化的 sub-agent protocol。

---

## 6. 调研方法补充

- 调研基于 `C:\workspace\github\onionagent\harness\01_market_research\clone\continue\` 2026-07-17 拉取的 master 快照。
- 由于 Continue 是 TypeScript monorepo(50+ 子包、~30 万行代码),本次**重点深读**了:
  - `core/tools/{callTool,index,builtIn,parseArgs}.ts`(4 个核心工具文件)
  - `gui/src/redux/thunks/{streamResponse,streamNormalInput,streamResponseAfterToolCall,callToolById,evaluateToolPolicies,preprocessToolCallArgs}.ts`(6 个核心 thunk)
  - `extensions/cli/src/stream/{streamChatResponse,handleToolCalls,streamChatResponse.compactionHelpers,streamChatResponse.autoCompaction}.ts`(4 个核心 stream 文件)
  - `extensions/cli/src/{compaction.ts,subagent/{executor,index,get-agents}.ts,permissions/{permissionChecker,permissionManager,defaultPolicies}.ts,tools/{askQuestion,exit,subagent,allBuiltIns}.ts,session.ts}`
  - `core/llm/{defaultSystemMessages,streamChat}.ts` + `core/llm/rules/getSystemMessageWithRules.ts`
  - `core/config/markdown/loadMarkdownRules.ts` + `core/config/loadLocalAssistants.ts`
  - `core/util/{paths,conversationCompaction}.ts` + `core/util/GlobalContext.ts`
  - `core/index.d.ts`(`MessageModes` / `ToolPolicy` / `ChatHistoryItem` 等核心类型)
- **浅读 / 跳读**:`core/llm/llms/` 下 50+ provider(只看 OpenAI / Anthropic / Ollama 3 个代表),`extensions/vscode/src/...` 整体框架(激活 / messenger / webview provider 3 处)。
- **未读**:`core/indexing/` 详细 chunk / vector 索引实现、`core/nextEdit/`(Next Edit 推荐模型独立模块,与主 loop 无关)、`gui/src/components/` 大量 React 组件、`binary/` 子项目。
- 调研时间:2026-07-18,实际投入 ~2 小时(配 grep + Read + 工作区上下文查询)。
- 与本报告配套的姊妹报告:`harness/01_market_research/Continue/file_backend.md`(已交付,工作区与索引)和 `harness/01_market_research/Continue/tool_channel.md`(已交付,工具调用通道),本报告聚焦"**Agent Loop 控制流 + 状态机 + 用户介入点**"。
