# 智能体 Agent Loop 行业标准

> **提炼自**:GitHub 上 20 个最流行 ReAct 智能体的 `agent_loop.md` 调研报告(`harness/01_market_research/<项目>/agent_loop.md`)
> **提炼方法**:3 个子代理按 9 大问题分维度(Q1-Q3 / Q4-Q6 / Q7-Q9)横向提炼 + 主控跨组整合
> **提炼日期**:2026-07-18
> **配套文档**:
> - 20 份单项目报告:`harness/01_market_research/<项目目录>/agent_loop.md`
> - 3 份组内提炼稿:`harness/01_market_research/_intermediate_{loop_internal,loop_external,loop_crosscutting}.md`
> - 顶部引用:`harness/01_market_research/top_20_react_agent.md`
> - 姊妹标准:`harness/01_market_research/standard/file_backend.md` / `tool_channel.md`
> **本标准作用**:为后续 Onion Agent 的 Agent Loop 设计提供"必须做 / 强烈建议 / 可选 / 禁止"的决策清单

---

## 0. 文档结构

本标准按"顶层哲学 → 9 大问题分维度(Q1-Q9)→ 20 项目总览对照表 → P0/P1/P2 优先级"组织。每条标准带 4 个标签:

| 标签 | 含义 |
|----|------|
| **必须做** | 20 个项目里 ≥15 个采用,违反即成"反例" |
| **强烈建议** | 7-14 个项目采用,有清晰工程价值,新项目应当借鉴 |
| **可选** | 3-6 个项目采用,按需 |
| **禁止** | 0-2 个项目采用且明确有害,或违反会破坏洋葱架构哲学 |

---

## 1. 顶层设计哲学(5 大原则)

从 20 个项目的设计反复验证,以下是 **5 条横贯全局的设计原则**:

### 1.1 原则一:ReAct 主循环 + 多维退出决策树(不要单 while)

> Agent Loop **不是**一个 `while(true)`,而是 **B(外层 turn loop)+ C(内层 step loop)双层** + **5 维退出决策树**:
> 1) 正常完成 → return;2) profile rotation → continue;3) model fallback → continue;4) 限流/空响应 → retry;5) token 超限 → compact+continue;6) 终态 → return。

**频次**:20/20 全部支持 ReAct 主循环;5/20 显式双层;12/20 显式多维决策树。

**典型代表**:
- OpenClaw(`OpenClaw/agent_loop.md:Q1.4`):5 层正交状态机(外层 retry + terminal-retry + compaction + lane queue + steering queue)
- OpenAI_Codex_CLI(`OpenAI_Codex_CLI/agent_loop.md:Q1.1`):3 层嵌套(Session → Turn → ToolCall)
- Hermes_Agent(`Hermes_Agent/agent_loop.md:Q1.1`):双层 Agent Loop(L1 turn 内 `run_conversation` 5600 行 + L2 cross-turn `GoalManager` Ralph loop)
- Opencode(`Opencode/agent_loop.md:Q1.1`):内层 processor.ts 返回三态 `"compact"|"stop"|"continue"`,外层 runLoop 决定 break

**典型反例**:
- Aider(`Aider/agent_loop.md:Q1.4`):无 `max_iter`,纯靠用户退出——LLM 永远可能卡住,这是"裸 while"
- superpowers(`superpowers/agent_loop.md:Q4.1`):"Do not pause to check in with your human partner between tasks"——只适合 skill 编排,不适合通用 agent

**Onion 启示**:**Onion 必须采用 B+C 双层架构**。外层 `loop_iteration` 跑 turn/session,内层 `process_step` 跑 LLM+tool+回灌;turn 是用户/session 维度,step 是单次 LLM call 维度——正交。

### 1.2 原则二:Plan 机制双轨(Plan Mode + update_plan 互斥)

> Plan 不能只有一个机制。**Plan Mode**(独立 mode,只读工具)+ **update_plan 工具**(执行态 checklist)**必须同时存在,且互斥**——Plan Mode 期间**禁调** `update_plan`。

**频次**:**20/20** 都有 plan 表达方式;A+B 双轨 6/20。

**典型代表**:
- Claude_Code(`Claude_Code/agent_loop.md:Q2.1`):EnterPlanMode/ExitPlanMode 工具
- OpenAI_Codex_CLI(`OpenAI_Codex_CLI/agent_loop.md:Q2.5`):`plan.rs:79-83` 显式 "update_plan is a TODO/checklist tool and is not allowed in Plan mode"
- OpenClaw(`OpenClaw/agent_loop.md:Q2.1`):`update-plan-tool.ts:84-105` `content: []` 不回 LLM,只返 UI
- Opencode(`Opencode/agent_loop.md:Q2.1`):plan / build 走同一个 processor,差异仅在 agent 的 permission ruleset

**典型反例**:
- Aider(`Aider/agent_loop.md:Q2.6`):99% prompt-as-tool,plan 揉进自然语言 message
- Continue(`Continue/agent_loop.md:Q2.6`):Plan 模式不能保存 plan 状态,刷新就丢

**Onion 启示**:**同时实现 A+B**,强制 1 in_progress(`update_plan` schema 校验:At most one step can be in_progress at a time)。plan 文件不污染 LLM context(工具返回 `content: []` + `details: { plan: [...] }` 推 UI)。

### 1.3 原则三:工具权限 3 档 + YOLO hardline 兜底

> 工具权限**不能**是单一 boolean 或"信任用户",必须**显式 3 档决策**(`allow / ask / deny`)。即使提供 YOLO / bypass 模式,也必须有 **hardline 兜底**(即使 YOLO 也拒绝的危险 pattern)。

**频次**:3 档决策 19/20;YOLO 档 6/20;hardline 兜底 4/20(所有面向 YOLO 的项目都做)。

**典型代表**:
- OpenClaw(`OpenClaw/agent_loop.md:Q7`):5 态(allow-once / allow-always / deny + timeout + cancelled)+ `timeoutBehavior: "allow"` 已 deprecated 强制 fail-closed
- Hermes_Agent(`Hermes_Agent/agent_loop.md:Q7`):6 层(`L0 hardline / L1 DANGEROUS / L2 YOLO / L3 per-session YOLO / L4 Smart / L5 allowlist`)
- Roo_Code(`Roo_Code/agent_loop.md:Q7`):`PROTECTED_PATTERNS` 10 个 pattern 即使全 auto-approval 也必须用户确认
- Claude_Code(`Claude_Code/agent_loop.md:Q7`):"Catastrophic removals (e.g. `rm -rf ~`) in commands containing `$(…)`/backticks now prompt in `--auto` mode"

**典型反例**:
- Aider(`Aider/agent_loop.md:Q7`):99% prompt-as-tool,无 ask 中间态——LLM 可以在 SEARCH/REPLACE 块藏恶意代码,用户 review diff 成本极高

**Onion 启示**:**3 档(allow/ask/deny)+ YOLO + hardline 兜底**。hardline 清单:自身配置(`onionagent.toml`、`.onion/`)、SSH 密钥(`~/.ssh/`)、系统关键路径(`/etc/`、`~/.aws/`、`~/.kube/`)、危险命令(`rm -rf /`、`mkfs`、fork bomb)、Catastrophic subshell(`rm -rf ~` 藏在 `$(...)` / 反引号 / `<(...)`)。

### 1.4 原则四:上下文压缩是分层级联,不是单一策略

> 上下文压缩**不能**只有一种策略(如"超限就 LLM 总结")。必须是**多层级联**(token check → truncate → LLM summary → probe verification)。

**频次**:Token 阈值自动触发 17/20;head 压 + tail 保 15+/20;Multi-strategy 级联 8/20;Probe verification 2/20(Gemini_CLI 首创)。

**典型代表**:
- OpenClaw(`OpenClaw/agent_loop.md:Q8`):**6 层叠加**(L1 工具结果截断 30% / L2 mid-turn 50% 守卫 / L3 preemptive / L4 LLM-driven / L5 manual / L6 history turn limit)
- Gemini_CLI(`Gemini_CLI/agent_loop.md:Q8`):**3 阶段压缩**(truncation → LLM summary → **probe verification**)——"长 session 防丢失"关键
- Open_Interpreter(`Open_Interpreter/agent_loop.md:Q8`):**4 档 fallback**(local → remote V2 → V1 → local 兜底)
- Opencode(`Opencode/agent_loop.md:Q8`):两层(轻量 `prune` 老 tool output 截断 + 重量 `compaction` LLM 总结 head 保留 tail)
- SuperAGI(`SuperAGI/agent_loop.md:Q8`):**3 层 LTM 摘要**(`_split_history` → `_build_ltm_summary` → 递归 previous_summary + new_msgs)

**典型反例**:
- Aider(`Aider/agent_loop.md:Q8`):L2 摘要只改内存不写回文件(`Aider/file_backend.md` 已记录)
- CrewAI(`CrewAI/agent_loop.md:Q8`):`summarize_messages` 仅异常触发

**Onion 启示**:**6 层叠加参考 OpenClaw,3 阶段 + probe verification 参考 Gemini_CLI**。压缩后必须**主动写回 session.json**(Aider 反例不能学)。

### 1.5 原则五:Sub-agent 是隔离的子 session(不要共享 context)

> Sub-agent 派发**不是** LLM 调个 `spawn_agent` 工具那么简单。**正确做法是隔离的子 session**,通过 `parent_id` 串成树,共享 working_dir 但隔离 context。

**频次**:LLM 调 spawn_agent 工具 6/20;隔离子进程 4/20(OpenHands、Open_Interpreter、Hermes_Agent、Cline Kanban);DAG 节点 3/20。

**典型代表**:
- Hermes_Agent(`Hermes_Agent/agent_loop.md:Q3`):Kanban dispatcher `subprocess.Popen` 派子进程,**env pinning 三层防御**(`HERMES_KANBAN_TASK/DB/BOARD`),worker 任务所有权检查防 prompt injection 跨任务破坏
- Cline(`Cline/agent_loop.md:Q3`):Kanban 是独立 npm 包 `kanban@latest`,**每个 task = 独立 git worktree + 独立 Cline session**——Sub-Agent = 嵌套 `SessionRuntime`(session 内),Teams = 跨 session 共享 JSON 文件
- OpenAI_Codex_CLI(`OpenAI_Codex_CLI/agent_loop.md:Q3`):共享 `state_5.sqlite` + `parent_thread_id` 串成 tree(`thread_spawn_edges` 边表 + `WITH RECURSIVE` 查询),**无 git worktree 隔离**
- MetaGPT(`MetaGPT/agent_loop.md:Q3`):`cause_by` 字段做隐式 SOP DAG(`Role._watch` 订阅表),不依赖显式 ActionGraph

**典型反例**:
- Aider(`Aider/agent_loop.md:Q3`):`ArchitectCoder` → `editor_coder` 的 `Coder.create(from_coder=self)` 链式调用,不是独立 agent 运行时
- OpenClaw(`OpenClaw/agent_loop.md:Q3`):`sessions_spawn` + `subagents` 两个内置工具,支持 depth + children 限制但**不是物理隔离**

**Onion 启示**:**Sub-agent = 隔离的子 session.json**。主 session 只记录"sub-agent 的 start/end 时间 + result 摘要",完整 transcript 在子 session(`~/.onion/sessions/<main_id>/<sub_id>.json` 形成树)。env pinning 三层防御(参考 Hermes)。

---

## 2. 维度 Q1:Agent Loop 主流程

### 2.1 模式分类(5 大类)

| 模式 | 代表项目 | 频次 | 核心特征 |
|---|---|---|---|
| **A. 单 while(true) ReAct** | Claude_Code, Cline, Aider, Open_Interpreter(Python), Continue(CLI), OpenClaw(最简路径) | 6/20 | 一个进程内一个 while 循环;LLM → tool → 回灌 → 再 LLM |
| **B. 外层 while + 内层 step/processor** | OpenClaw, Opencode, OpenHands, OpenAI_Codex_CLI, Roo_Code, Gemini_CLI, Open_Interpreter(Rust) | 7/20 | 外层 while 负责 turn/iteration,内层函数处理单次 LLM + tool 流;状态机驱动退出 |
| **C. 双层嵌套(turn loop + ReAct loop)** | OpenAI_Codex_CLI(submission_loop + run_turn), Hermes_Agent(GoalManager + run_conversation), ChatDev(cycle + agent), SuperAGI(workflow step + iteration step) | 4/20 | 外层面向"session/turn",内层面向"ReAct/tool call",两层独立 timeout/state |
| **D. DAG / Graph 编排** | AutoGPT Platform, MetaGPT(Team+Environment+Role 三层), CrewAI(Flow+Crew), AutoGen(GroupChat+Manager), ChatDev(Graph 拓扑) | 5/20 | 主驱动是 DAG 节点执行,不是循环;每个节点可内含 ReAct |
| **E. 事件驱动 Stream** | Gemini_CLI(Turn.run yields), Lobe_Chat(AgentRuntime + QStash), Claude_Code(12+ hook events), Aider(stream chunks + progress) | 4/20 | 循环主体改为 yield/consume 事件;消费者驱动执行 |

> **关键观察**:5 大模式**不互斥**——OpenAI_Codex_CLI = B + C,OpenHands = B + E,Open_Interpreter Rust = A→B→C 演化。

### 2.2 必须做(≥15/20)

| 设计点 | 频次 | 典型实现 | 源引用 |
|---|---|---|---|
| **max_iterations 硬上限** | **20/20** | 32-160 不等;多数 50;OpenClaw 缩放 = base(24) + profile × 8,clamp [32, 160] | OpenClaw/agent_loop.md:Q1.4;Hermes parent=90/child=50 |
| **LLM 失败重试 + 退避** | **18/20** | 指数退避 + jitter,5-120s 范围 | Hermes(agent_loop.md:Q1.2);OpenClaw(5 维 retry 堆栈);OpenAI_Codex_CLI `stream_max_retries()` |
| **Tool call 并行执行** | **15/20** | `asyncio.gather` 多个 tool call 并发,但保持请求顺序入队 | OpenAI_Codex_CLI(turn.rs:1180 `InFlightTools` + `FuturesOrdered`);Cline(`Promise.all`);OpenHands(`ParallelToolExecutor`);AutoGen(`asyncio.gather`);CrewAI(`execute_todos_parallel`) |
| **上下文/token 超限检测** | **17/20** | 80% 阈值或绝对 token 数;超限触发压缩/截断/退出 | Opencode(`isOverflow` 80% 阈值);OpenAI_Codex_CLI(`MidTurn` auto-compact);Gemini_CLI(`ContextWindowWillOverflow` 事件) |
| **用户中断(Ctrl+C / abort)** | **18/20** | 循环顶部 `throwIfAborted` + CancellationToken | Cline(AbortController);OpenAI_Codex_CLI(CancellationToken);Opencode(`ctx.aborted`);OpenHands(`PAUSED/STUCK/FINISHED` 状态机) |
| **流式响应(text-delta / reasoning-delta)** | **16/20** | Vercel AI SDK / LiteLLM stream;event-driven 累积 | Opencode(LLM.stream);Aider(`partial_response_content += delta.content`);Gemini_CLI(Content/Thought 事件) |
| **每次 iteration = 1 次 LLM + N 个 tool → 回灌** | **20/20** | ReAct 最小循环单元 | 全部项目共性 |

### 2.3 强烈建议(7-14/20)

| 设计点 | 频次 | 典型实现 |
|---|---|---|
| **5+ 层重试堆栈(profile/model/empty/reasoning/tool-use continuation)** | 7/20 | OpenClaw 独有 5 层 retry 决策树;OpenAI_Codex_CLI `retry-with-escalation` 简化版 |
| **Context compaction(中段压缩)** | **14/20** | mid-turn 自动压缩(OpenAI_Codex_CLI `MidTurn`);pre-sampling(Open_Interpreter Rust);Gemini_CLI(`tryCompressChat`);Opencode(`SessionCompaction.process`);Aider(`summarize_worker` 后台) |
| **Loop stuck 检测** | 8/20 | OpenHands(`StuckDetector.is_stuck` 基于最近 20 个事件);AutoGen MagenticOne(stalls 计数 + max_stalls 触发 re-plan) |
| **Fallback model 链(主模型失败切弱模型)** | 9/20 | OpenClaw `runWithModelFallback`;Hermes `_try_activate_fallback`;Cline `weak-model` 概念 |
| **Tool result 回灌格式标准化** | 12/20 | OpenAI Codex `FunctionCallOutputPayload { body: Text | ContentItems }`;Opencode `ToolPart`;OpenClaw `tool_call details`(不回 LLM context,只回 UI) |
| **Hook 事件钩子(可注入扩展点)** | 9/20 | Claude_Code 12+ hooks;OpenHands `_run_and_publish`;OpenClaw `plugin hook`;Gemini_CLI `BeforeAgent/AfterAgent`;Aider 弱(仅 `auto-lint` callback) |
| **完成判定 = tool lifecycle.completesRun + 无未执行 tool** | 8/20 | Cline `findCompletingToolMessage`;Opencode `lastAssistant.finish` |
| **Prompt cache 标记(节省 token)** | 10/20 | CrewAI `mark_cache_breakpoint`;OpenClaw `run-prepared-embedded-loop` 内置;Opencode `system.promptCache`;OpenAI_Codex_CLI `base_instructions` 分离 |
| **Reasoning 独立 channel(reasoning vs answer)** | 9/20 | Opencode reasoning/event 分离;Gemini_CLI `Thought` 事件;OpenAI_Codex_CLI `ReasoningContentDelta`;Claude_Code `reasoning-delta` |
| **Loop 退出决策树(N 种状态 → N 种退出路径)** | 12/20 | OpenHands(7 状态机);OpenClaw 5 维 retry;OpenAI_Codex_CLI(`should_block` / `should_stop` / `should_block_continue`);Cline(`completed/failed/aborted`) |

### 2.4 可选(3-6/20)

| 设计点 | 频次 | 备注 |
|---|---|---|
| **DAG 编排主驱动(不是循环)** | 5/20 | AutoGPT Platform、CrewAI、MetaGPT、AutoGen、ChatDev。适合"流水线式"任务,但单 agent 任务反而更重 |
| **Goal/Ralph loop(持续到 judge 通过)** | 3/20 | Hermes_Agent(`GoalManager.evaluate_after_turn` + Judge LLM);superpowers(`subagent-driven-development` 二阶段 review);Open_Interpreter Rust 引入 `goal_achieved` |
| **Loop 内部异步并发(event loop 驱动)** | 4/20 | MetaGPT `asyncio.gather` 所有非 idle role;AutoGen `SingleThreadedAgentRuntime`;Lobe_Chat QStash 异步 step |
| **每 iteration cost/token 累计到 DB** | 4/20 | SuperAGI 强(`num_of_tokens`/`num_of_calls` 入 DB);MetaGPT(`cost_manager.total_balance`);AutoGen(`ModelClient.stats`) |
| **Loop 内自动评估"是否需要 sub-agent"** | 2/20 | Open_Interpreter Rust V2(`reasoning_effort=Ultra` → `MultiAgentMode::Proactive`);其他都是 LLM 显式调 `spawn_agent` |
| **Cost/RPM 限流(rate limit controller)** | 5/20 | CrewAI `enforce_rpm_limit(rpm_controller)`;AutoGPT `TokenLimit`;OpenClaw `MAX_RUN_LOOP_ITERATIONS` |

### 2.5 禁止(0-2/20 且有害)

| 反例 | 频次 | 为何有害 |
|---|---|---|
| **永真 while(true) 无 max_iterations** | 0/20 | 全部项目都有上限,没有任何项目"裸 while" |
| **任何 tool 错误就退出 loop** | 0/20 | 全部项目错误可恢复/降级;Hermes、OpenClaw 都有 retry |
| **修改 system prompt 来"压缩"上下文** | 0/20(但 Hermes 早期有引用性提示) | 破坏 prompt cache,违反 Hermes 关键不变式 "不修改 system prompt / toolset 保护 prompt cache" |

### 2.6 Onion 启示(Q1)

| 启示 | 行动 |
|---|---|
| **采用 B + C 双层** | 外层 `loop_iteration` 跑 turn/session,内层 `process_step` 跑 LLM+tool+回灌。turn 是用户/session 维度,step 是单次 LLM call 维度——正交 |
| **5 维退出决策树** | 参考 OpenClaw:1) 正常完成 → return;2) profile rotation → continue;3) model fallback → continue;4) 限流/空响应 → retry;5) token 超限 → compact+continue;6) 终态 → return |
| **事件驱动 + 状态机退出** | 主循环顶部先检查 status(参考 OpenHands 7 状态:PAUSED/STUCK/FINISHED/WAITING_FOR_CONFIRMATION/RUNNING/IDLE/ERROR),再决定 step |
| **Tool parallel by default** | 允许多 tool 并发,但保留 `parallel_tool_calls: bool` 开关;入队用 `FuturesOrdered` 保持请求顺序 |
| **上下文压缩分层** | pre-sampling(80% 阈值)+ mid-turn(95% 阈值强压)+ post-tool 验证三段式 |
| **Reasoning 独立 channel** | 把 `reasoning_content` 单独流出来,不入主 answer;text_delta 累积到 `partial_response_content` 才回灌 LLM |
| **必须 max_iterations 显式** | base(24) + profile×8 缩放;clamp [32, 160];同时维护 `iteration_budget.consume()` 软限(参考 Hermes) |
| **不要 all-in 一种 loop 模式** | 经典 ReAct + DAG 子图 + Goal loop 三种并存,Onion 应在 `agent_mode` 上做多选 |

---

## 3. 维度 Q2:Plan 计划机制

### 3.1 模式分类(4 大类)

| 模式 | 代表项目 | 数量 | 核心特征 |
|---|---|---|---|
| **A. Plan Mode(模式切换)** | Claude_Code(EnterPlanMode/ExitPlanMode), Gemini_CLI, opencode(plan agent), OpenAI_Codex_CLI(ModeKind::Plan), Open_Interpreter Rust(collaboration_mode.mode = Plan), Cline(plan mode), Roo_Code(Architect mode), Continue(plan mode) | 8/20 | 通过 system prompt + 工具集过滤实现"只读 + 思考";`ExitPlanMode` 触发切换到 act mode |
| **B. update_plan 工具(LLM 主动 push 进度)** | OpenClaw(update_plan tool), OpenAI_Codex_CLI(update_plan), opencode(plan agent 内部用 write), Claude_Code(plan.md 工具), Open_Interpreter Rust(update_plan checklist), Gemini_CLI(write_file + ExitPlanMode) | 6/20 | LLM 调工具主动更新 todo 列表;`at most 1 in_progress` 是硬约束 |
| **C. 静态 YAML/DAG plan** | ChatDev(YAML), SuperAGI(AgentWorkflow seed), AutoGPT Platform(graph), AutoGen(GraphFlow + MagenticOne), CrewAI(Flow + planner) | 5/20 | plan = 开发者配置的图,运行时只"实例化 + 选路径",LLM 不主动重写 plan |
| **D. 持续 Goal/Ralph loop** | Hermes_Agent(GoalContract + Judge LLM), superpowers(plan-as-markdown,subagent-driven-development) | 2/20 | plan = 高层目标 + 5 字段合同;Judge LLM 评估"done/continue/wait";持续到 judge 判定 done |

> **关键观察**:B 模式(dynamic todo)实际上被 A 模式的 plan 模式"借走"了——plan mode 内部也用 update_plan。Onion 应当同时实现 A + B,D 可作为可选项(强 goal 任务时启用)。

### 3.2 必须做(≥15/20)

| 设计点 | 频次 | 典型实现 |
|---|---|---|
| **显式的 plan 表达方式(任选 A/B/C/D)** | **20/20** | 即使 Aider 99% 用 prompt-as-tool,仍然有"LLM 在 message 里写 plan" |
| **Plan/Todo 至少 1 个 in_progress 硬约束** | 15/20 | OpenClaw `update-plan-tool.ts:53-59`;OpenAI_Codex_CLI `plan.rs:1-37` "At most one step can be in_progress at a time" |
| **LLM 通过 system prompt 知道"现在在 plan 模式"** | 12/20 | opencode `plan.txt` system reminder;OpenAI_Codex_CLI `collaboration-mode-templates/plan.md`;Open_Interpreter Rust plan.md 模板 |
| **Plan mode 下写工具被禁用** | 10/20 | opencode `permission.edit.*: "deny"` + allowlist `.opencode/plans/*.md`;Claude_Code 同样只允许 read |
| **Plan 文件可持久化 + 跨 turn 复用** | 8/20 | Claude_Code 写到 `.claude/plans/<n>.md`;opencode `.opencode/plans/<ts>-<slug>.md`;Gemini_CLI `~/.gemini/tmp/<id>/plans/<n>.md`;ChatDev YAML |

### 3.3 强烈建议(7-14/20)

| 设计点 | 频次 | 典型实现 |
|---|---|---|
| **Plan Mode 切换由 LLM 主动触发(EnterPlanMode 工具)** | 9/20 | Claude_Code;Gemini_CLI;OpenAI_Codex_CLI(隐式);Cline(`switch_to_act_mode` 工具) |
| **Plan 文件名基于 prompt 摘要 + 随机后缀** | 6/20 | Claude_Code `fix-auth-race-snug-otter.md`;opencode `[ts-slug].md`;Gemini_CLI(类似) |
| **Plan 内置 3+ 阶段模板(Ground/Intent/Implementation)** | 5/20 | Open_Interpreter Rust(`plan.md` 3 phases);superpowers(brainstorming 9 步 checklist);Roo_Code(Architect 7 步固定) |
| **Plan 用 `request_user_input` 多选 2-4 选项向用户问** | 6/20 | Open_Interpreter Rust;superpowers;Claude_Code;OpenAI_Codex_CLI `request_user_input` tool |
| **Plan 完成后明确"ExitPlanMode"切到 act mode** | 8/20 | Claude_Code;Gemini_CLI;opencode;Open_Interpreter Rust;Cline(switch_to_act_mode) |
| **用户可在 plan mode 内 modify / reject / approve** | 7/20 | Gemini_CLI `ExitPlanMode` 弹窗带 reject + feedback;Claude_Code 同样 |
| **`update_plan` 不在 plan mode 中允许** | 4/20 | Open_Interpreter Rust `plan.rs:51-55` 显式拒绝;OpenAI_Codex_CLI 同样 |
| **Plan 仅写到 plan file,内容不污染主 chat history** | 5/20 | OpenClaw `update-plan-tool.ts:84-105` `content: []` 不返回 LLM,只返 UI |
| **Plan status 必须是结构化字段(pending/in_progress/completed)** | 14/20 | OpenClaw;OpenAI_Codex_CLI;opencode;CrewAI(`TodoItem.status`);Roo_Code(`TodoItem[]`) |

### 3.4 可选(3-6/20)

| 设计点 | 频次 | 备注 |
|---|---|---|
| **GoalContract(5 字段 contract)** | 1/20 | Hermes_Agent 借鉴 OpenAI Codex "strong goal" |
| **Judge LLM 评估 plan 是否完成** | 2/20 | Hermes + AutoGen MagenticOne |
| **Plan 自动重 plan(replan on failure)** | 5/20 | CrewAI `replan_count` + `handle_replan`;AutoGen MagenticOne stalls;AutoGPT `Plan-Execute` REPLANNING |
| **Plan 内嵌 reflection loop** | 3/20 | Aider `max_reflections=3`;superpowers task reviewer;AutoGen MagenticOne |
| **Plan 阶段跨 turn 持久化(写到 markdown 文件)** | 6/20 | Claude_Code;opencode;Gemini_CLI;Roo_Code;OpenHands;ChatDev YAML |

### 3.5 禁止(0-2/20 且有害)

| 反例 | 频次 | 为何有害 |
|---|---|---|
| **Plan 写到主 chat context,污染 LLM 输入** | 1/20 | OpenClaw `content: []` 不返回 LLM,只返 UI(他们是对的,其他 19 项目都避免) |
| **Plan mode 下允许写文件** | 0/20 | 全部 8 个 Plan Mode 项目都禁 edit |
| **LLM 自由决定 in_progress 数量** | 5/20 | Aider(无约束);Continue(无 in_progress 概念);OpenHands(无 in_progress 字段) |

### 3.6 Onion 启示(Q2)

| 启示 | 行动 |
|---|---|
| **同时实现 A + B** | Plan Mode(独立 mode,只读工具)+ update_plan 工具(执行态 checklist),互斥(Plan Mode 期间禁 update_plan) |
| **强制 1 in_progress** | `update_plan` schema 校验:`At most one step can be in_progress at a time` |
| **plan 文件写到 `.onion/plans/<ts>-<slug>.md` 或 `~/.onion/plans/<id>/<n>.md`** | 跨 turn 持久化;命名规则:基于 prompt 摘要 + 随机后缀防冲突 |
| **Plan Mode 3 阶段软强制** | Ground(信息收集)/ Intent(明确目标)/ Implementation(决策完成),允许"短任务跳过 Intent" |
| **`<proposed_plan>` XML 标签** | TUI 单独渲染,不渲染成普通 markdown |
| **Plan 阶段向用户多选问** | `request_user_input` 工具,2-4 个 meaningful options |
| **ExitPlanMode 多目标** | 支持 plan → {Default / AutoEdit / Yolo / Custom},不只是"回 Default" |
| **plan 模式期间禁 update_plan** | Tool schema 拒绝或在 permission 层 deny |
| **Plan 内容不污染 LLM context** | 工具返回 `content: []` + `details: { plan: [...] }` 推 UI |
| **不做 Goal loop by default** | 强 goal 任务作为可选 advanced mode(Hermes 风格),不在 MVP 必做 |

---

## 4. 维度 Q3:Sub Agent

### 4.1 模式分类(4 大类 + 1 退化)

| 模式 | 代表项目 | 数量 | 核心特征 |
|---|---|---|---|
| **A. LLM 调 spawn_agent 工具(主流)** | Claude_Code `Task` tool(general-purpose/Explore/Plan), Opencode `task` tool, Open_Interpreter `spawn/wait/send_input/close/resume`, OpenAI_Codex_CLI `spawn_agent` (共享 state.db), OpenClaw `sessions_spawn` / `subagents` | 6+/20 | LLM 显式调工具 spawn sub-agent;子 agent 通常独立 session/working_dir |
| **B. 独立进程(Kanban/Worker 模式)** | Hermes_Agent Kanban dispatcher(`subprocess.Popen`), Cline Kanban(独立 npm 包 + git worktree) | 2/20 | 物理隔离的子进程;env pinning + heartbeat + zombie 检测 |
| **C. DAG 节点(Workflow/Graph 编排)** | OpenHands `Workflow`(动态 Python 脚本编排), MetaGPT(Team+Environment+Role 三层), ChatDev `type: agent` 节点, AutoGen `GroupChat` | 4/20 | sub-agent 作为 DAG 节点;静态或动态编排 |
| **D. 角色扮演(无独立 session)** | MetaGPT(Role set_actions), CrewAI(Agent + delegation), ChatDev CEO/CTO/Programmer 角色 | 3/20 | "角色分工"是 Sub-agent 弱化版,共享 team context |
| **退化:无 Sub-agent** | Aider(`ArchitectCoder` 是链式调用,不是独立 agent), superpowers(`subagent-driven-development` 派"子 skill 委派"但本质是 prompt) | 2/20 | "派 agent"实际是 LLM 自调 chain-of-thought |

### 4.2 必须做(≥15/20)

| 设计点 | 频次 | 典型实现 |
|---|---|---|
| **LLM 显式调 spawn_agent 工具(主流方案)** | **18/20** | Claude_Code `Task` tool;Opencode `task` tool;Open_Interpreter `spawn`;OpenAI_Codex_CLI `spawn_agent`;OpenClaw `sessions_spawn`;Cline `new_task`;Roo_Code `new_task`;Gemini_CLI `AgentTool` |
| **Sub-agent 有独立 session/context(不污染主 session)** | 15/20 | OpenAI_Codex_CLI 共享 state.db 但 parent_thread_id 隔离;OpenClaw sub-agent 独立 session;Open_Interpreter V1/V2 双模式;OpenHands `Task`/`Delegate`/`Workflow` 都隔离 |
| **Sub-agent 可独立 max_iteration / budget 配置** | 10/20 | Hermes parent=90/child=50;OpenHands `max_subagent_budget`;Open_Interpreter per-agent limits;Cline Kanban per-task 独立 budget |

### 4.3 强烈建议(7-14/20)

| 设计点 | 频次 | 典型实现 |
|---|---|---|
| **Sub-agent 通过 parent_id 串成 tree** | 12/20 | OpenAI_Codex_CLI `thread_spawn_edges` 边表;Gemini_CLI 子 agent 嵌套在 `<parentSessionId>/<id>.jsonl`;Roo_Code `rootTaskId` / `parentTaskId`;Lobe_Chat GroupOrchestration;OpenHands `Delegate` parent/child 链 |
| **Sub-agent 任务所有权检查(防 prompt injection 跨任务破坏)** | 4/20 | Hermes_Agent `_enforce_worker_task_ownership` 强制 worker 只读自己 task_id 的数据 |
| **Sub-agent 不能直接 ask 用户(只能让主 agent 转发)** | 7/20 | Hermes_Agent;OpenHands;Roo_Code(sub-agent 必须 `attempt_completion` 写回结果) |
| **Sub-agent 完成后 result 写回主 session** | 14/20 | Claude_Code Task tool 自动写回;Opencode `task` 工具;Open_Interpreter `wait` 工具;OpenAI_Codex_CLI `parent_thread_id` |
| **Sub-agent 可限制 depth(防止无限嵌套)** | 6/20 | OpenClaw `subagent-spawn.ts:1046,1080-1100` depth + children 限制;Cline `MAX_SUBAGENT_DEPTH`;OpenHands `max_subagent_depth` |
| **Sub-agent 有独立的 system prompt / 角色** | 12/20 | Claude_Code 4 种内置类型(general-purpose/Explore/claude/Plan);Opencode `general` / `explore`;Open_Interpreter `Role.Preset` |

### 4.4 可选(3-6/20)

| 设计点 | 频次 | 备注 |
|---|---|---|
| **Sub-agent 物理隔离(独立 git worktree)** | 1-2/20 | **OpenAI_Codex_CLI 调研纠正**:**没有 git worktree 隔离**(虽然有些文档暗示);Cline Kanban 独立 npm 包,**每个 task = 独立 git worktree + 独立 session**(但这是 Kanban 模式,不是通用 Sub-agent) |
| **Kanban 多 Agent 并行任务板** | 1/20 | 仅 Cline Kanban(`npm i -g kanban`),独立项目 |
| **Sub-agent 有持久化 checkpoint** | 5/20 | OpenHands shadow git;Hermes_Agent Checkpoints v2(单 shared git init --bare);Cline Kanban per-task git |
| **Sub-agent 主动 fork 后台 review(同模型 warm cache / 异模型 digest)** | 1/20 | Hermes_Agent `BackgroundReview` |

### 4.5 禁止(0-2/20 且有害)

| 反例 | 频次 | 为何有害 |
|---|---|---|
| **Sub-agent 与主 agent 共享同一 LLM context** | 2/20 | Aider `ArchitectCoder` 链式调用把 assistant message 共享;superpowers 派"子 skill 委派"通过 prompt 注入共享——controller 上下文污染 |
| **Sub-agent 无限嵌套(depth 不限)** | 3/20 | 部分项目无 depth 限制(隐式);Onion 必须显式 cap |
| **Sub-agent 静默失败(无错误回报)** | 1/20 | superpowers "派子 agent 完成后无 ack" 模式 |

### 4.6 Onion 启示(Q3)

| 启示 | 行动 |
|---|---|
| **Sub-agent = 隔离的子 session.json** | 放在 `~/.onion/sessions/<main_id>/<sub_id>.json` 形成树;主 session 只记录 start/end + result 摘要 |
| **parent_id 串成 tree** | SQL 表 `subagent_relations(parent_id, child_id, depth)` 或 YAML 头部 `parents: [...]` |
| **env pinning 三层防御** | 参考 Hermes:`HERMES_KANBAN_TASK/DB/BOARD` env pinning,worker 启动时只读自己 task_id 数据 |
| **depth 显式 cap** | `MAX_SUBAGENT_DEPTH=3`(参考 Cline),超过抛 `MaxDepthExceededError` |
| **Sub-agent 不能直接 ask 用户** | 只能 `attempt_completion` 写回 result;主 agent 决定是否转发给用户 |
| **物理隔离默认不做(可选项)** | Onion 是 CLI,git worktree 隔离对单用户 CLI 场景过重,默认**逻辑隔离**(独立 session.json);要做 Kanban 多任务时再考虑 git worktree |
| **任务所有权检查** | 参考 Hermes `enforce_worker_task_ownership`,sub-agent 写文件时校验 path 不越界到其他 sub-agent 的 working_dir |

---

## 5. 维度 Q4:Loop 退出机制

### 5.1 模式分类(8 大类)

| 模式 | 代表项目 | 频次 | 核心特征 |
|---|---|---|---|
| **A. LLM 显式 finish 信号** | AutoGPT `finish` / OpenHands `FinishAction` / Roo_Code `attempt_completion` / Cline `attempt_completion` / SuperAGI `finish` 工具 / MetaGPT `STATE_TEMPLATE -1` + RoleZero `end` | 18/20 | 命令/标签/解析;LLM 主动说"做完了" |
| **B. max_iteration 硬上限** | AutoGen `_max_turns` / ChatDev `tool_loop_limit=50` + `max_iterations=100` / Gemini_CLI `MaxSessionTurns=100` / OpenHands `max_iteration_per_run=500` / CrewAI `max_iter=25` / OpenClaw `MAX_RUN_LOOP_ITERATIONS=32-160` | 19/20 | 数字 cap;LLM 卡住的兜底 |
| **C. 用户主动中断** | 全部 20 个 | 20/20 | Ctrl+C / Esc / abort |
| **D. Token / Cost 预算** | AutoGen `TokenUsageTermination` / AutoGPT `cost_manager` / OpenHands `max_budget_per_run` / Open_Interpreter `BudgetExceededError` / Lobe_Chat `costLimit` / MetaGPT `cost_manager` + `NoMoneyException` | 12/20 | 累计 token 或 wall-clock timeout |
| **E. Loop detection(doom loop)** | Claude_Code / Cline / Continue / Gemini_CLI / OpenClaw / Opencode / OpenHands / Open_Interpreter / Roo_Code | 9/20 | 重复工具 / 连续错误检测 |
| **F. Stop hook 阻断 → 续推 prompt** | Claude_Code(经典)/ OpenAI_Codex_CLI / Open_Interpreter / OpenHands | 4/20 | 可注入外部条件,block 时把原 prompt 喂回 LLM |
| **G. State 状态机** | Lobe_Chat / OpenHands / SuperAGI | 3/20 | terminal/parked 分级;让 ops 跨 HTTP 请求可恢复 |
| **H. Save/Load 跨 session 状态恢复** | AutoGen / Claude_Code / Lobe_Chat / OpenAI_Codex_CLI / OpenHands / SuperAGI / CrewAI | 7/20 | 中断后恢复 / 任意点回滚 |

### 5.2 必须做(≥15/20)

| 设计点 | 频次 | 关键证据 |
|---|---|---|
| **必须同时实现"LLM 显式 finish" + "max_iteration 硬上限"双 cap** | 19/20 | 19/20 都有显式 LLM finish 信号,仅 Aider 不用;19/20 都有 iteration 上限,仅 Aider 不设;**单有 LLM finish 容易被 prompt injection 骗;单有 cap 容易"明明做完了还得等 100 轮"** |
| **必须支持用户主动中断(Ctrl+C / Esc / abort)** | 20/20 | 100% 支持,无例外;AbortController / cancellation token 主流实现 |

### 5.3 强烈建议(7-14/20)

| 设计点 | 频次 | 典型实现 |
|---|---|---|
| **loop detection(doom loop / 重复工具检测)** | 9/20 | Opencode `DOOM_LOOP_THRESHOLD=3`;OpenClaw `tool-loop-detection.ts:46` 30 次同 tool call 无进展;Cline `MistakeTracker` 6 次错误;Gemini_CLI `LoopDetectionService` count=1 注入 feedback |
| **token / cost 预算** | 12/20 | AutoGen `TokenUsageTermination`;OpenHands `max_budget_per_run`;MetaGPT 钱光就 `raise NoMoneyException` |
| **save/load 跨 session 状态** | 7/20 | OpenHands `navigate_to(event_id)` 任意点回滚;AutoGen `HandoffTermination` + `save_state` + 异步 user reply + `load_state` |

### 5.4 可选(3-6/20)

| 设计点 | 频次 | 备注 |
|---|---|---|
| **Stop hook 阻断 → 续推 prompt** | 4/20 | Claude_Code Ralph Wiggum 模式;OpenAI_Codex_CLI `stop_outcome.should_block` |
| **State 状态机(terminal / parked 分级)** | 3/20 | Lobe_Chat 5 个 status;OpenHands `ConversationExecutionStatus` 7 状态 |
| **多级 retry 各自 cap** | 3-4/20 | OpenClaw 完整 4 类续推(reasoning-only / empty / tool-use / compaction-success) |

### 5.5 禁止(0-2/20 且有害)

| 反例 | 频次 | 为何有害 |
|---|---|---|
| **无任何 iteration cap,纯靠 LLM finish 退出** | 1/20 | Aider 反例;LLM 永远可能卡住 = 把钱袋交给 LLM |
| **`loop_breakers` 字符串匹配作为"LLM 显式 finish"的唯一机制** | 1/20 | Open_Interpreter Python 时代反例;LLM 可能在分析中自然产出"魔法字符串"→ 假性退出;Rust 时代已改 `needs_follow_up` 布尔信号 |
| **`cycle_budget` 默认 `math.inf`(无 cap)** | 1/20 | AutoGPT 反例;开发者用 AutoGPT 时 90% 不设 cap → 烧光 token |

### 5.6 Onion 启示(Q4)

| 启示 | 行动 |
|---|---|
| **必须双 cap** | `max_iteration` 硬上限 + `max_token` / `max_cost` 预算。**默认不能是 `inf`**(参考 OpenClaw 32-160 缩放) |
| **退出决策点要单一** | 参考 OpenClaw `terminal-resolution.ts`——"唯一决定是否真 return"的代码点,便于审计和测试 |
| **session.json 是天然累加器** | Claude_Code Ralph Wiggum 的 `.claude/ralph-loop.local.md` 用 YAML frontmatter + markdown body 维护状态。Onion 的 `session.json` 可以直接采用这个范式 |
| **loop detection 必做** | 至少 3 次同 tool + 同 input 重复 → 弹窗问用户(参考 Opencode `DOOM_LOOP_THRESHOLD=3`);6 次连续错误 → 熔断退出 |
| **state 状态机 vs while 跳出** | Onion 走"洋葱架构分层",Lobe_Chat 的 5-status 状态机(`done` / `error` / `interrupted` / `waiting_for_human` / `waiting_for_async_tool`)比较自然 |
| **跨 session 暂停/恢复必做** | 参考 OpenHands 走最远,`navigate_to` 任意点回滚;Onion 至少要做"中断后 load_state 恢复" |

---

## 6. 维度 Q5:Ask 模式

### 6.1 模式分类(7 大类)

| 模式 | 代表项目 | 频次 | 核心特征 |
|---|---|---|---|
| **A. LLM 主动 ask 工具(multi-choice, 2-4 选项)** | Claude_Code `AskUserQuestion` / Cline `ask_question` / Continue `AskQuestion` / Gemini_CLI `ask_user` / OpenAI_Codex_CLI `request_user_input` / Opencode `question` / Open_Interpreter `request_user_input` / Roo_Code `ask_followup_question` / AutoGPT `ask_user/ask_yes_no/ask_choice` / Hermes_Agent `clarify` | 12/20 | schema 几乎完全一致 `{questions: [{header, question, options, multiSelect}]}` |
| **B. 整段对话"Ask 模式"(只读 + 不改)** | Aider `AskCoder` / Roo_Code `Ask Mode` / Cline `Plan Mode`(类) | 3/20 | 整段对话只回答不改 |
| **C. Workflow/Graph 节点的 `type: human`** | ChatDev 2.0 / MetaGPT Planner / CrewAI Flow | 3/20 | 在 DAG 中插入"问"节点 |
| **D. 无 ask 工具,只能 confirm/reject** | OpenClaw / OpenHands | 2/20 | **OpenClaw 调研纠正**:严格意义的"向用户弹选项让用户选"的 ask 工具——**没有**;只有 3 模式 approval |
| **E. 通过宿主 agent 的 tool 实现(不写死)** | superpowers(`using-superpowers/SKILL.md` 调用宿主 `AskUserQuestion`) | 1/20 | 不写死,跨宿主 |
| **F. Confirmation 弹窗作为"问"** | Aider `confirm_ask` / AutoGen UserProxyAgent / OpenClaw 3 approval modes / Opencode Permission.ask | 10+/20 | 本质是 confirm,不是多选 |
| **G. Plan 模式专属 ask** | OpenAI_Codex_CLI / Open_Interpreter / Continue | 3/20 | `allows_request_user_input` 只允许 Plan mode |

### 6.2 必须做(≥15/20)

| 设计点 | 频次 | 关键证据 |
|---|---|---|
| **必须实现 LLM 主动 ask 工具(让 LLM 在执行中向用户提结构化问题)** | **15/20** | 11 个项目有 `ask_user` / `ask_question` / `request_user_input` / `clarify` 等 LLM 主动工具;ChatDev `type: human` 节点 + Cline `ask_question` + Roo_Code `ask_followup_question` + Aider `/ask` 命令再 4 个;**OpenClaw 和 OpenHands 是不做的反例** |

### 6.3 强烈建议(7-14/20)

| 设计点 | 频次 | 典型实现 |
|---|---|---|
| **ask 工具 schema 标准化** | 11/20 | `{questions: [{header: ≤12 字符, question, options: 2-4 个, multiSelect: false}]}`,**所有项目 schema 几乎一致** |
| **Plan 模式专属 ask 能力** | 3/20 | `allows_request_user_input` 只允许 Plan mode,Execute mode 禁用 |
| **ask 工具支持 `auto_resolution_ms` 超时默认选项** | 2/20 | Open_Interpreter `auto_resolution_ms=60-240s` 超时自动选默认 |
| **Confirmation 弹窗作为"问"补充** | 10/20 | Aider `confirm_ask` 弹窗穷举 14 个触发点;OpenClaw 3 approval modes |
| **每 ask 后将用户答案写回 session context** | 12/20 | Claude_Code;OpenAI_Codex_CLI `Op::UserInputAnswer`;Open_Interpreter 显式 |

### 6.4 可选(3-6/20)

| 设计点 | 频次 | 备注 |
|---|---|---|
| **整段对话"Ask 模式"(只读 + 不改)** | 3/20 | Aider `AskCoder` 11 行代码只换 prompt;Roo_Code `Ask Mode` `groups: ["read", "mcp"]` |
| **Workflow/Graph 节点 `type: human`** | 3/20 | ChatDev 2.0 `HumanNodeExecutor`;MetaGPT Planner;CrewAI Flow |
| **ask 工具支持 multiSelect(多选)** | 8/20 | Claude_Code;OpenAI_Codex_CLI;Open_Interpreter 等 schema 中有 `multiSelect: bool` |
| **ask 工具支持多问题(1-3 个)** | 6/20 | Claude_Code;OpenAI_Codex_CLI;Open_Interpreter `1-3 questions` |
| **ask 工具支持视觉伴侣(just-in-time 渲染)** | 1/20 | superpowers 特色:可挂 preview image |
| **跨 session 异步 ask(threading.Event + polling)** | 2/20 | Hermes_Agent Gateway 异步 threading.Event + 1s 轮询 + touch_activity |

### 6.5 禁止(0-2/20 且有害)

| 反例 | 频次 | 为何有害 |
|---|---|---|
| **无 ask 工具,只能 confirm/reject** | 2/20 | OpenClaw / OpenHands 反例;用户体验差,LLM 跑一半"卡住"只能 abort |
| **ask 在 Execute mode 启用** | 0/20 | 全部 3 个 Plan 专属项目都禁;Onion 必须限制 |
| **ask 不写回 session context** | 0/20 | 所有项目都把 user answer 写回 chat history |
| **ask 工具支持 5+ 选项** | 0/20 | 全部项目 cap 4 选项;超过 4 认知负担太大 |

### 6.6 Onion 启示(Q5)

| 启示 | 行动 |
|---|---|
| **必须有 ask_user 工具** | 直接抄 Claude_Code / OpenAI_Codex_CLI 的 schema:`{questions: [{header ≤12, question, options: 2-4 个, multiSelect}]}` |
| **Plan mode 期间允许 ask,Execute mode 默认禁** | 借 OpenAI_Codex_CLI `allows_request_user_input` 字段 |
| **ask 答案写回 session.json** | 作为 user message 一行 append(参考 Claude_Code) |
| **可选支持 multiSelect + 多问题** | P1 阶段加;MVP 可只支持单问题 + 单选 |
| **支持 `auto_resolution_ms` 超时默认选项** | 借 Open_Interpreter;避免无人值守任务卡住 |
| **跨 session 异步 ask** | 仅 P2 阶段;P1 用 CLI 同步问就行 |
| **不要做"无 ask 只能 confirm"的反例** | OpenClaw / OpenHands 是反面教材 |

---

## 7. 维度 Q6:Human-in-the-Loop (HITL)

### 7.1 模式分类(8 大类)

| 模式 | 代表项目 | 频次 | 核心特征 |
|---|---|---|---|
| **A. Pre-tool approval**(工具调用前弹窗) | 全部 20 个 | 20/20 | 主流实现;allow/ask/deny + session-scoped |
| **B. approval 3+ 档权限分级** | 18/20 | 18/20 | OpenClaw 5 态;Opencode 3 态;Claude_Code 5 档 mode + 3 档基础权限 |
| **C. 跨 session 状态保存** | 7/20 | 7/20 | OpenHands `navigate_to`;AutoGen `save_state/load_state`;Lobe_Chat `state` |
| **D. 文件级回滚(`/rewind`)** | 2/20 | 2/20 | Claude_Code `/rewind` + worktree 隔离;OpenHands `navigate_to` |
| **E. 中断 + 异步回复** | 4/20 | 4/20 | Claude_Code `/steer`;AutoGen `HandoffTermination`;Lobe_Chat `waiting_for_human` |
| **F. Plan 模式中强制 review** | 8/20 | 8/20 | Claude_Code / Gemini_CLI / opencode / OpenAI_Codex_CLI / Open_Interpreter / Continue / Cline / Roo_Code |
| **G. Stop hook 用户决策** | 4/20 | 4/20 | Claude_Code;OpenAI_Codex_CLI;Open_Interpreter;OpenHands |
| **H. 训练模式(pickle 持久化)** | 1/20 | 1/20 | CrewAI 训练模式 + `crewai chat` CLI |

### 7.2 必须做(≥15/20)

| 设计点 | 频次 | 关键证据 |
|---|---|---|
| **Pre-tool approval(20/20)** | **20/20** | 100% 项目支持;主流 AbortController / cancellation token |
| **3+ 档权限分级** | **18/20** | OpenClaw 5 态;Opencode 3 态;Claude_Code 5 档 mode + 3 档基础权限;Continue disabled/allowedWithPermission/allowedWithoutPermission;Cline per-tool approval/autoApprove/YOLO;Roo_Code 7 类 AutoApprovalState |

### 7.3 强烈建议(7-14/20)

| 设计点 | 频次 | 典型实现 |
|---|---|---|
| **跨 session 状态保存** | 7/20 | OpenHands `navigate_to(event_id)` 任意点回滚;AutoGen `save_state/load_state` |
| **Plan 模式中强制 review** | 8/20 | Claude_Code / Gemini_CLI / opencode / OpenAI_Codex_CLI / Open_Interpreter / Continue / Cline / Roo_Code |
| **Stop hook 用户决策** | 4/20 | Claude_Code;OpenAI_Codex_CLI;Open_Interpreter;OpenHands |
| **持久化 Always Allow** | 6/20 | OpenClaw `allow-always` + `execpolicy`;Claude_Code `.claude/settings.json`;OpenAI_Codex_CLI `ApprovedForSession`;Cline `autoApprove`;Lobe_Chat `allow-list`;Roo_Code `allowedCommands` |
| **Hook 介入决策(PreToolUse 可 ask/block)** | 5/20 | Claude_Code `permissionDecision: ask`;OpenClaw `before_tool_call`;OpenAI_Codex_CLI `tool.escalate_on_failure`;Lobe_Chat `sanitizeToolCallArguments` |

### 7.4 可选(3-6/20)

| 设计点 | 频次 | 备注 |
|---|---|---|
| **文件级回滚(`/rewind`)** | 2/20 | Claude_Code;OpenHands |
| **中断 + 异步回复(threading.Event + 轮询)** | 4/20 | Claude_Code `/steer`;AutoGen `HandoffTermination`;Hermes_Agent Gateway 异步;Lobe_Chat `waiting_for_human` |
| **Approver 投票(多 LLM 评估)** | 1-2/20 | OpenHands `ToolShield` 多 LLM 投票;Hermes_Agent `L4 Smart Approval` |
| **审批超时 → 拒绝(fail-closed)** | 4/20 | OpenClaw `timeoutBehavior: "allow"` deprecated 强制 fail-closed;OpenAI_Codex_CLI;Open_Interpreter;OpenHands Guardian AI 熔断 |
| **审批 audit log** | 2/20 | Open_Interpreter;OpenHands;基本项目都缺 |
| **Hook 决定高于 mode 决策** | 1-2/20 | Claude_Code 经验:"a hook ask now floors the auto-mode decision" |

### 7.5 禁止(0-2/20 且有害)

| 反例 | 频次 | 为何有害 |
|---|---|---|
| **无 Pre-tool approval(纯靠 LLM 自决)** | 0/20 | 100% 项目都有,缺失即成"反例" |
| **approval timeout 走"放行"分支** | 0/20 | 所有 timeout 设计都强制 fail-closed;**用户不答 = 拒绝**,绝不"超时默认放行" |
| **hook 决定被 mode 覆盖** | 1-2/20 | 早期 Claude_Code 出现过 hook ask 被 auto-mode 覆盖的 bug,已修复;Onion 必须保证 hook 优先级 ≥ mode |
| **无 audit log** | 多数 | 多数项目缺失,反例警告 |

### 7.6 Onion 启示(Q6)

| 启示 | 行动 |
|---|---|
| **3 档权限 + 5 档 mode 矩阵** | 参考 Claude_Code:allow/ask/deny 3 基础 × default/acceptEdits/plan/bypassPermissions/dontAsk 5 档 |
| **持久化 Always Allow 3 个 scope** | session(内存)/ workspace(`<project>/.onion/policies.yaml`)/ user(`~/.config/onion/policies.yaml`) |
| **Plan 模式中强制 review** | ExitPlanMode 必走用户确认;`reject + feedback` 写回 session |
| **跨 session 暂停/恢复** | session.json 自带这个能力;Onion 的"洋葱核心"天然支持 |
| **审批超时 fail-closed** | timeout 默认拒绝,不"超时默认放行"(参考 OpenClaw `timeoutBehavior: "allow"` 已 deprecated) |
| **Hook 优先级 ≥ mode 决策** | 借 Claude_Code 经验:"hook ask now floors the auto-mode decision" |
| **P2 阶段加 audit log** | 写到 `~/.onion/logs/hitl_<session_id>.jsonl` |

---

## 8. 维度 Q7:工具调用权限

### 8.1 模式分类(14 个模式族)

| 模式 | 代表项目 | 频次 |
|---|---|---|
| **A. 3 档 (allow / ask / deny)** | OpenClaw, Opencode, Claude_Code, Continue, Cline, Roo_Code, OpenAI_Codex_CLI(4 档), Hermes_Agent(6 层) | 8/20 |
| **B. YOLO / bypass 显式档** | Claude_Code(bypassPermissions), Gemini_CLI(YOLO), Cline(YOLO), OpenAI_Codex_CLI(Never), SuperAGI(God Mode 默认), Hermes_Agent(--yolo) | 6/20 |
| **C. Plan / read-only 档** | Claude_Code(plan), Opencode(plan agent edit 物理移除), Gemini_CLI(PLAN), OpenAI_Codex_CLI(ReadOnly sandbox), Open_Interpreter(read-only), ChatDev(Code Reviewer 节点) | 6/20 |
| **D. OS 级 sandbox 3 态(read-only / workspace-write / danger-full)** | Open_Interpreter, OpenAI_Codex_CLI(4 态), Claude_Code(bubblewrap+seatbelt+Windows), ChatDev(workspace path 校验) | 4/20 |
| **E. Catastrophic 硬底线(YOLO 也不放过)** | OpenClaw(timeout fail-closed), Hermes_Agent(hardline DANGEROUS_PATTERNS), Claude_Code(catastrophic removal in `$(...)`), Roo_Code(PROTECTED_PATTERNS) | 4/20 |
| **F. Hook 介入决策(PreToolUse 可 ask/block)** | Claude_Code, OpenClaw, OpenAI_Codex_CLI, Lobe_Chat, Gemini_CLI | 5/20 |
| **G. 持久化 "Always Allow"** | OpenClaw, Claude_Code, OpenAI_Codex_CLI, Cline, Lobe_Chat, Roo_Code | 6/20 |
| **H. Role / Agent 维度的工具隔离(无 per-call 权限)** | MetaGPT(set_actions 显式), ChatDev(per-node tooling 白名单), AutoGen(Workbench 列表), CrewAI(allow_delegation 字段) | 4/20 |
| **I. 几乎无权限("trust the user" + YOLO by default)** | Aider(只有 shell 弹 confirm_ask), superpowers(零工具), CrewAI(隐式), ChatDev(YOLO + sandbox by default) | 4/20 |
| **J. 工具物理可见性(deny → 从 LLM schema 移除)** | Opencode(disabled 工具不传给 LLM), Roo_Code(plan 模式无写工具) | 2/20 |
| **K. Pattern-based shell heuristic** | Gemini_CLI(applyShellHeuristics), OpenHands(PatternSecurityAnalyzer) | 2/20 |
| **L. 审批后回放 assistant_reply(不重问 LLM)** | SuperAGI, OpenAI_Codex_CLI | 2/20 |
| **M. Smart Approval (aux LLM 评估低风险自动批)** | Hermes_Agent(aux LLM verdict), AutoGPT, OpenHands(LLMSecurityAnalyzer / ToolShield) | 3/20 |
| **N. 用户行为约束代替工具权限("Iron Law")** | superpowers(`NO PRODUCTION CODE WITHOUT A FAILING TEST FIRST` 等 5+ 条) | 1/20 |

### 8.2 必须做(≥15/20)

> **没有任何单一模式达到 ≥15/20**——说明 Q7 是"分层组合"问题,不是"统一答案"问题。

但有 2 个**结构性要求**接近必须做:

#### M-1:必须存在 3 档决策(放行/询问/拒绝),不允许二选一 (19/20)

- 19/20 项目有明确的 allow/ask/deny 三态(或扩展);唯一例外是 **Aider**——它把"工具权限"压缩为"shell 弹窗 + 信任用户",内部不区分三档。
- 证据:OpenClaw 5 态 / Opencode 3 态 / Claude_Code 3 档 + 5 档 mode / Continue 3 态 / Cline 3 态 / Roo_Code 7 类 / OpenAI_Codex_CLI 4 档 / Hermes_Agent 6 层

#### M-2:必须存在 hardline 兜底,即使 YOLO 也不放过 (4/20,但所有面向 YOLO 的项目都做了)

- 虽未到 15,但凡是允许 YOLO / bypass 模式的项目**都**做了 hardline 兜底——这意味着 hardline 不是"功能",是"安全底线"。
- 证据:OpenClaw `timeoutBehavior: "allow"` 强制 fail-closed;Hermes_Agent `DANGEROUS_PATTERNS`;Claude_Code "Catastrophic removals in commands containing `$(…)`";Roo_Code `PROTECTED_PATTERNS`

### 8.3 强烈建议(7-14/20)

| 设计点 | 频次 | 典型实现 |
|---|---|---|
| **YOLO / bypass 显式档** | 6-10/20 | Claude_Code `bypassPermissions`;Gemini_CLI `ApprovalMode.YOLO`;Cline `mode === "yolo"`;OpenAI_Codex_CLI `AskForApproval::Never`;SuperAGI `permission_type: "God Mode"` 默认 |
| **持久化 "Always Allow" 机制** | 6/20 | OpenClaw `allow-always` + `execpolicy`;Claude_Code per-repo `.claude/settings.json`;OpenAI_Codex_CLI `ApprovedForSession` + `ApprovedExecpolicyAmendment`;Cline `autoApprove`;Lobe_Chat `allow-list`;Roo_Code `allowedCommands` + `findLongestPrefixMatch` |
| **Plan / Read-only 档** | 6/20 | Claude_Code(plan);Opencode(plan agent edit 物理移除);Gemini_CLI(PLAN);OpenAI_Codex_CLI(ReadOnly sandbox);Open_Interpreter(read-only);ChatDev(Code Reviewer 节点) |
| **OS 级 sandbox 至少 2 态** | 4/20 | OpenAI_Codex_CLI 完整 OS sandbox;Claude_Code(bubblewrap/seatbelt/Windows);Open_Interpreter 3 档 sandbox;ChatDev `FileToolContext` 路径校验 |

### 8.4 可选(3-6/20)

| 设计点 | 频次 | 备注 |
|---|---|---|
| **Hook 介入决策** | 5/20 | Claude_Code `permissionDecision: ask`;OpenClaw `before_tool_call`;OpenAI_Codex_CLI `tool.escalate_on_failure`;Lobe_Chat `sanitizeToolCallArguments`;Gemini_CLI `PreCompress` hook |
| **Role / Agent 维度的工具隔离** | 4/20 | MetaGPT `set_actions` 显式;ChatDev per-node `tooling`;AutoGen `workbench=[...]`;CrewAI `allow_delegation=False` |
| **Catastrophic pattern 自动检测** | 2/20 | Gemini_CLI `applyShellHeuristics`;OpenHands `PatternSecurityAnalyzer` |
| **审批后回放 assistant_reply** | 2/20 | SuperAGI;OpenAI_Codex_CLI |
| **Smart Approval (aux LLM 评估低风险)** | 3/20 | Hermes_Agent `L4 Smart Approval`;OpenHands `LLMSecurityAnalyzer` / `ToolShield`;AutoGPT `human_in_the_loop_safe_mode` |
| **工具物理可见性(deny → 从 LLM schema 移除)** | 2/20 | Opencode(disabled 工具不传给 LLM);Roo_Code(plan 模式无写工具) |
| **用户行为约束代替工具权限("Iron Law")** | 1/20 | superpowers 5+ Iron Law |

### 8.5 禁止(0-2/20 且有害)

| 反例 | 频次 | 为何有害 |
|---|---|---|
| **只用 allow/deny 二选一,无 ask 中间态** | 1/20 | Aider 反例;LLM 可以在 SEARCH/REPLACE 块藏恶意代码,用户 review diff 成本极高 |
| **approval timeout 走"放行"分支** | 0/20 | OpenClaw `timeoutBehavior: "allow"` 已 deprecated 强制 fail-closed;共识:**用户不答 = 拒绝** |
| **YOLO 无 hardline 兜底** | 0/20 | 所有 YOLO 都有 hardline |
| **deny 被覆盖(allow 优先)** | 0/20 | 共识:deny 永远高于 allow |

### 8.6 Onion 启示(Q7)

| 启示 | 行动 |
|---|---|
| **3 档决策(allow/ask/deny)必做** | 不要走 Aider 的"信任用户"路线 |
| **YOLO 必做 + hardline 兜底** | CLI 加 `--yolo` / `--auto-approve-all` flag,默认 "manual" |
| **hardline 清单** | 自身配置(`onionagent.toml`、`.onion/`)、SSH 密钥(`~/.ssh/`)、系统关键路径(`/etc/`、`~/.aws/`、`~/.kube/`)、危险命令(`rm -rf /`、`mkfs`、fork bomb)、Catastrophic subshell(`rm -rf ~` 藏在 `$(...)` / 反引号 / `<(...)`) |
| **Plan 模式 = 工具物理移除** | 借 Opencode:不是"调了再 deny",而是"从 LLM 工具 schema 移除" |
| **持久化 Always Allow 3 scope** | session / workspace(`<project>/.onion/policies.yaml`)/ user(`~/.config/onion/policies.yaml`) |
| **OS sandbox 信创必做** | P2 阶段:Windows Restricted Token + Linux Landlock/seccomp + macOS Seatbelt(参考 Codex) |
| **Hook 决策高于 mode 决策** | PreToolUse hook 返回 `ask` 必须 floors auto-mode(参考 Claude_Code 经验) |
| **审批后回放 assistant_reply** | LLM 重新生成决策会浪费 token + 改变答案;直接用之前 JSON 重新提交 tool 调用 |

---

## 9. 维度 Q8:上下文压缩和摘要

### 9.1 模式分类(20 个模式族)

| 模式 | 代表项目 | 频次 |
|---|---|---|
| **A. Token 阈值自动触发压缩** | OpenClaw(80%), Opencode(80%), OpenAI_Codex_CLI(`HISTORY_SOFT_CAP_RATIO`), Gemini_CLI(`ContextWindowWillOverflow`), Cline(75%), Continue(80%), Roo_Code(75%), Open_Interpreter(`MidTurn`), SuperAGI, Aider, ChatDev, OpenHands, Lobe_Chat, AutoGen, Hermes, Claude_Code, Codex | 17/20 |
| **B. head 压 + tail 保(head compression, tail reservation)** | OpenClaw 6 层, Opencode `prune`, OpenAI_Codex_CLI `compact`, Gemini_CLI 3 阶段, SuperAGI `_split_history`, Open_Interpreter Rust `try_run_sampling_request`, Continue, Cline, Roo_Code, Lobe_Chat, AutoGen MagenticOne | 15+/20 |
| **C. Manual `/compact` 命令** | Claude_Code, OpenAI_Codex_CLI, Gemini_CLI, Opencode, Open_Interpreter, OpenClaw, Cline, Continue, Roo_Code | 9/20 |
| **D. Multi-strategy 级联(local → remote → truncate)** | Open_Interpreter(4 档 fallback), SuperAGI(3 层 LTM), Gemini_CLI(3 阶段), Lobe_Chat(adaptive), AutoGen MagenticOne, Claude_Code(5 档), Opencode(轻+重), OpenClaw(6 层) | 8/20 |
| **E. Anchor incremental summary(增量式 summary)** | SuperAGI `_build_ltm_summary` 递归, OpenClaw `compact.ts:1700`, OpenAI_Codex_CLI, Hermes_Agent, Cline(滑窗) | 5/20 |
| **F. Circuit breaker(超 threshold 强退)** | OpenClaw `MAX_RUN_LOOP_ITERATIONS`, Opencode `isOverflow` 80% 阈值, Open_Interpreter `BudgetExceededError`, Hermes_Agent `GoalManager` 软限, OpenAI_Codex_CLI `TokenUsageTermination` | 5/20 |
| **G. Probe verification(压缩后回测)** | Gemini_CLI 首创(`probe verification`), SuperAGI 隐式, Claude_Code `PreCompact` hook | 2-3/20 |
| **H. Mid-turn auto-compact(turn 中压缩)** | OpenAI_Codex_CLI `MidTurn`, Open_Interpreter `MidTurn`, Opencode, OpenClaw, Gemini_CLI, SuperAGI | 6/20 |
| **I. Tool output 截断(独立通道)** | OpenClaw(`MAX_TOOL_RESULT_CONTEXT_SHARE=0.3`), Opencode `prune`, Cline(per-tool), Roo_Code, Aider(`summarize_worker`), Gemini_CLI, Claude_Code | 7/20 |
| **J. Reasoning 独立 channel(reasoning vs answer 分流)** | Opencode, Gemini_CLI `Thought`, OpenAI_Codex_CLI `ReasoningContentDelta`, Claude_Code `reasoning-delta` | 9/20 |
| **K. 跨 session memory 持久化(LTM 长期记忆)** | SuperAGI LTM, AutoGPT, Hermes_Agent `MEMORY.md` / `USER.md`, OpenClaw `memory/YYYY-MM-DD.md`, Open_Interpreter 01, Aider chat history | 6/20 |
| **L. RAG 检索式压缩(摘要 + 检索 + 引用)** | OpenHands, Lobe_Chat, ChatDev Memory 检索, Claude_Code, Gemini_CLI(部分) | 5/20 |
| **M. Session 切换 / Rollover(到 cap 切换新 session)** | Claude_Code(隐式 `/clear`), Aider `/clear`, Continue 滚动, Lobe_Chat group-aware 100 条 | 4/20 |
| **N. Sliding window(滚动窗口)** | Cline, Roo_Code, Aider, AutoGen(部分) | 4/20 |
| **O. Snapshot 备份(压缩前 snapshot)** | OpenClaw `snapshot/`, Lobe_Chat `electron-store` 自动备份, AutoGen `save_state`, OpenHands atomic write | 4/20 |
| **P. group-aware 截断(不切 group 内 message)** | Lobe_Chat(100 条 = 100 个"组"), OpenAI_Codex_CLI(per-thread), Opencode | 3/20 |
| **Q. Pre-sampling 压缩** | Open_Interpreter Rust, OpenClaw, Gemini_CLI, Opencode | 4/20 |
| **R. tree-sitter 折叠(代码折叠)** | Roo_Code | 1/20 |
| **S. 压缩前 LLM judge(确保不丢关键信息)** | Gemini_CLI probe, Opencode `SessionCompaction.process` | 2/20 |
| **T. Per-event JSON append-only(独立存储)** | OpenHands `event-{idx:05d}-{uuid}.json`, Roo_Code `tasks/<taskId>/*.json`, Hermes_Agent Checkpoints v2 | 3/20 |

### 9.2 必须做(≥15/20)

| 设计点 | 频次 | 关键证据 |
|---|---|---|
| **Token 阈值自动触发压缩** | **17/20** | 80% 阈值或绝对 token 数;超限触发压缩/截断/退出 |
| **head 压 + tail 保(head compression, tail reservation)** | **15+/20** | OpenClaw 6 层叠加;Opencode `prune` 老 tool output 截断;Gemini_CLI truncation → LLM summary → probe verification;SuperAGI 3 层 LTM |

### 9.3 强烈建议(7-14/20)

| 设计点 | 频次 | 典型实现 |
|---|---|---|
| **Manual /compact 命令** | 9/20 | Claude_Code `/compact`;OpenAI_Codex_CLI `/compact`;Gemini_CLI `/compress`;Opencode;Open_Interpreter;OpenClaw;Cline;Continue;Roo_Code |
| **Multi-strategy 级联(local → remote → truncate)** | 8/20 | Open_Interpreter(4 档 fallback);SuperAGI(3 层 LTM);Gemini_CLI(3 阶段);Lobe_Chat(adaptive);AutoGen MagenticOne;Claude_Code(5 档);Opencode(轻+重);OpenClaw(6 层) |
| **Tool output 截断(独立通道)** | 7/20 | OpenClaw(`MAX_TOOL_RESULT_CONTEXT_SHARE=0.3`);Opencode `prune`;Cline(per-tool);Roo_Code;Aider(`summarize_worker`);Gemini_CLI;Claude_Code |
| **Reasoning 独立 channel** | 9/20 | Opencode reasoning/event 分离;Gemini_CLI `Thought`;OpenAI_Codex_CLI `ReasoningContentDelta`;Claude_Code `reasoning-delta` |
| **Mid-turn auto-compact** | 6/20 | OpenAI_Codex_CLI `MidTurn`;Open_Interpreter;Opencode;OpenClaw;Gemini_CLI;SuperAGI |

### 9.4 可选(3-6/20)

| 设计点 | 频次 | 备注 |
|---|---|---|
| **Anchor incremental summary** | 5/20 | SuperAGI `_build_ltm_summary` 递归;OpenClaw `compact.ts:1700`;OpenAI_Codex_CLI;Hermes_Agent;Cline 滑窗 |
| **Circuit breaker** | 5/20 | OpenClaw `MAX_RUN_LOOP_ITERATIONS`;Opencode `isOverflow`;Open_Interpreter `BudgetExceededError`;Hermes_Agent `GoalManager`;OpenAI_Codex_CLI `TokenUsageTermination` |
| **Probe verification(压缩后回测)** | 2-3/20 | Gemini_CLI 首创;SuperAGI 隐式;Claude_Code `PreCompact` hook |
| **跨 session memory 持久化(LTM 长期记忆)** | 6/20 | SuperAGI LTM;AutoGPT;Hermes_Agent `MEMORY.md`;OpenClaw `memory/`;Open_Interpreter 01;Aider |
| **RAG 检索式压缩(摘要 + 检索 + 引用)** | 5/20 | OpenHands;Lobe_Chat;ChatDev Memory;Claude_Code;Gemini_CLI |
| **Snapshot 备份(压缩前)** | 4/20 | OpenClaw `snapshot/`;Lobe_Chat `electron-store`;AutoGen `save_state`;OpenHands atomic write |
| **group-aware 截断(不切 group 内 message)** | 3/20 | Lobe_Chat 100 条 = 100 个"组";OpenAI_Codex_CLI per-thread;Opencode |

### 9.5 禁止(0-2/20 且有害)

| 反例 | 频次 | 为何有害 |
|---|---|---|
| **只靠 LLM 异常触发压缩(无主动检测)** | 2/20 | CrewAI(异常触发);部分隐式项目;Onion 必须主动监测 |
| **append-only 文件作主持久化(只 append 不写回)** | 1/20 | Aider `.aider.chat.history.md` 永远 append,**只影响 LLM 调用,不写回文件**;chat history 越来越大 |
| **压缩失败无限重试** | 多数 | 多数项目没 cap;Onion 必做 `max_compact_retries=3`,3 次失败退出 |
| **修改 system prompt 来"压缩"上下文** | 0/20 | 破坏 prompt cache,违反 Hermes 关键不变式 |

### 9.6 Onion 启示(Q8)

| 启示 | 行动 |
|---|---|
| **6 层叠加参考 OpenClaw** | L1 工具结果截断 30% / L2 mid-turn 50% 守卫 / L3 preemptive / L4 LLM-driven / L5 manual / L6 history turn limit |
| **3 阶段 + probe verification 参考 Gemini_CLI** | truncation → LLM summary → **probe verification**(防压缩丢失);Gemini_CLI 首创,1M 上下文标配 |
| **head 压 + tail 保** | LLM 总结 head 早期 messages,保留 tail 最近 messages |
| **Token 阈值 80% 主动触发** | 不要等 context 满了才压缩;`isOverflow` 80% 阈值立即 mid-turn auto-compact |
| **压缩后必须主动写回 session.json** | Aider 反例(只改内存不写回文件)不能学 |
| **压缩失败 fail-closed** | `max_compact_retries=3`,3 次失败 exit 而非无限重试 |
| **Reasoning 独立 channel** | 把 `reasoning_content` 单独流出来,不入主 answer;text_delta 累积到 `partial_response_content` 才回灌 LLM |
| **Snapshot 备份压缩前状态** | 旧版本归档到 `snapshot/session_<timestamp>.json`,永不删 |
| **group-aware 截断** | 100 条 = 100 个"组",不切 group 内的 message(参考 Lobe_Chat) |

---

## 10. 维度 Q9:其他亮点

### 10.1 14 个跨项目共性模式(高频 + 中频)

| # | 模式 | 频次 | 代表项目 |
|---|---|---|---|
| 1 | **Bootstrap 文件系统**(自动 seed 标准 .md) | 8/20 | OpenClaw(9 个 bootstrap 文件);Open_Interpreter Rust `AGENTS.md`;Continue `AGENTS.md` 兼容 3 命名;superpowers(zero runtime 装进宿主);Hermes_Agent |
| 2 | **Slash commands 系统** | 9/20 | Claude_Code(`/compact` `/init` `/rewind` `/steer` `/stop`);OpenAI_Codex_CLI(`/compact` `/init`);Gemini_CLI(`/compress` `/init`);Opencode;Open_Interpreter;Cline(`/newtask`);Roo_Code |
| 3 | **Multi-layer state machine(状态机分级)** | 8/20 | OpenHands(7 状态:PAUSED/STUCK/FINISHED/WAITING_FOR_CONFIRMATION/RUNNING/IDLE/ERROR);Lobe_Chat(5 status);OpenClaw(5 层正交);SuperAGI 状态机 |
| 4 | **Provider 抽象层(协议无关)** | 13/20 | opencode(Vercel AI SDK + 25+ provider);OpenHands(litellm 统一);Cline(25+ provider);Roo_Code(35+ provider `ApiStream`);AutoGen(`LLMMessage` 7 provider 共享) |
| 5 | **Sub-agent 隔离(独立 session/context)** | 15/20 | 几乎所有项目都做,程度不同 |
| 6 | **长程 memory 持久化** | 6/20 | SuperAGI LTM;AutoGPT;Hermes_Agent `MEMORY.md` / `USER.md`;OpenClaw `memory/YYYY-MM-DD.md`;Open_Interpreter 01;Aider chat history |
| 7 | **MCP 协议支持** | 6/20 | Claude_Code(13 plugin + MCP);OpenAI_Codex_CLI(`config.toml [mcp_servers]`);Gemini_CLI;Opencode;Continue;Roo_Code |
| 8 | **Plugin / Extension 系统** | 4/20 | OpenClaw(13 plugin + `extensions/<name>/openclaw.plugin.json`);Claude_Code(13 plugin + 12 hook);Cline(MCP marketplace);superpowers(10 宿主 manifest) |
| 9 | **Hook 事件系统** | 9/20 | Claude_Code(12+ hook:PreToolUse/PostToolUse/SessionStart/Stop/UserPromptSubmit/SubagentStop/PreCompact/Notification/InstructionsLoaded/MessageDisplay);OpenHands `_run_and_publish`;OpenClaw `plugin hook`;Gemini_CLI `BeforeAgent/AfterAgent` |
| 10 | **Multi-channel 接入(IM/Slack/Telegram)** | 4/20 | OpenClaw(20+ channels);Hermes_Agent(20+ channels);Cline(Telegram/Slack/Discord/Gchat/WhatsApp/Linear);AutoGPT(部分) |
| 11 | **Sandbox / OS-level 隔离** | 4/20 | OpenAI_Codex_CLI(Seatbelt+Landlock+Windows);OpenHands(Docker);Claude_Code(bubblewrap/seatbelt/Windows);Open_Interpreter(bwrap+landlock+Windows) |
| 12 | **CLI + IDE + SDK 三形态** | 5/20 | Cline(SDK/IDE/CLI);OpenClaw(CLI/桌面);Open_Interpreter(CLI/桌面/01);AutoGen(python+dotnet);ChatDev |
| 13 | **Session 持久化(SQLite + WAL)** | 6/20 | OpenClaw;Opencode;OpenHands;AutoGPT;SuperAGI;Lobe_Chat;Hermes_Agent |
| 14 | **Slash commands + skill 触发** | 6/20 | Claude_Code `/skills`;Gemini_CLI `/skills`;Opencode;Open_Interpreter;Hermes_Agent;superpowers |

### 10.2 20 个项目独有亮点速查表

| 项目 | 独有亮点 |
|---|---|
| **OpenClaw** | 持续 daemon 模式(非一次性 loop);20+ channel 路由(按 channel/account/peer);HEARTBEAT.md + YAML 任务文件(daemon wake);5 层正交状态机 |
| **superpowers** | 10 宿主 3 shapes 跨平台兼容;TDD for skills;**Skill 描述"只写 when-to-use,不写 what"**(反直觉实证) |
| **Hermes_Agent** | Multi-Agent Kanban;Checkpoints v2(单 shared `git init --bare`);BackgroundReview(fork 模型同 warm / 异 digest);Zombie 检测(PID 活着 + heartbeat) |
| **AutoGPT** | AI Agent 鼻祖;graph-based platform 编排;AutoPilot SDK chat loop |
| **Opencode** | 内层 processor.ts 三态 return;`Stream.takeUntil(() => ctx.needsCompaction)` 优雅终止 |
| **Claude_Code** | 13 plugin + 12 hook 事件;Ralph Wiggum 自循环(200 行 bash);`.local.md` 状态文件 |
| **Gemini_CLI** | 1M 上下文;3 阶段压缩 + probe verification(首创) |
| **OpenAI_Codex_CLI** | OS 级纵深防御沙箱(三平台同 `SandboxManager::transform` API);9 层 ConfigLayerStack;Terminal-Bench 77.3% 第一 |
| **OpenHands** | FileStore 抽象(local/S3/GCS/memory);per-event JSON append-only;**Plan = 专用子 agent preset**(不是主 agent 字段);**3 层权限**(annotation + Risk + SecurityAnalyzer + ConfirmationPolicy) |
| **Cline** | Plan/Act 切换 = session 重建;**Kanban 独立 npm 包,每 task = 独立 git worktree + 独立 session**;HubSessionClient 统一审批协议 |
| **Open_Interpreter** | LMC 协议(LLM 输出 ```python``` markdown → 解析成 code message → computer.run);9 语言 REPL;`request_user_input` 1-3 questions + 2-4 options + auto_resolution_ms |
| **Aider** | git 仓库即状态机;repo map 设计;99% prompt-as-tool(反例价值) |
| **Continue** | `AGENTS.md` / `AGENT.md` / `CLAUDE.md` 3 命名兼容;`.continuerc.json disableIndexing` 哨兵防自索引;80% auto-compaction + auto-continuation |
| **MetaGPT** | **`cause_by` 字段做隐式 SOP DAG**(`Role._watch` 订阅表);MGXEnv TeamLeader 中转;ProjectRepo 整棵 git 仓 |
| **AutoGen** | Pydantic Component 完美序列化;**Magentic-One 双 Ledger**(Task + Progress + stall 触发 re-plan);10 种 TerminationCondition |
| **CrewAI** | `@CrewBase` 自动绑 `base_directory`;Plan-and-Act Flow DSL(YAML 触发器);`PlanStep.depends_on` DAG;`reasoning_effort` 三档 |
| **ChatDev** | YAML DAG 双层循环(CycleExecutor + AgentNodeExecutor);5 层防御退出;`type: human` 节点 |
| **Lobe_Chat** | 5 状态 status 字段代替传统 `break`(parked 自动暂停);**Server 端把每步拆成 QStash HTTP 任务**;3-2-1 阶段 InterventionChecker;5 种 ToolSource |
| **Roo_Code** | **5 个内置 Mode**(Code/Architect/Ask/Debug/Orchestrator)+ Custom Mode;**Orchestrator 自身 `groups: []` 只能通过 `new_task` 委派**;写保护清单 10 个 pattern |
| **SuperAGI** | **Celery 单步异步 + Postgres 状态机**(不是 in-process while 循环);`apply_async(countdown=2)` 排下一步;**3 层 LTM 摘要递归** |

### 10.3 反例警示汇总

1. **Hermes_Agent "autoDream" 不存在**:用户描述中提到的"autoDream"机制在 20 份报告中**没有出现**,Hermes 实际只有 `GoalManager` + `Background review` + `Checkpoint v2`(`Hermes_Agent/agent_loop.md:Q1.6`)。Onion 不要被"autoDream"误导,持续目标通过 `GoalContract + judge LLM` 实现,不是定时器。
2. **Open_Interpreter Python 时代 ≠ Rust 时代**:v0.4.2 是 **LMC 协议**(LLM 输出 ```python``` markdown 块 → 解析成 code message → computer.run)。Rust 重构后改用原生 function call(OpenAI Responses / Anthropic Messages)。两个时代的"loop"完全不同。
3. **AutoGPT 三个"互不兼容"的 Loop**:Classic(2023 while 循环) + Platform(2024 graph executor) + AutoPilot SDK(2025 event stream)**三套并存**。Onion 不应同时维护三套 loop。
4. **Aider 没有 Plan/Sub-agent 概念**:Aider 的"plan"是 LLM 在 message 里写自然语言 + reflection 3 次自纠;所谓"sub-agent"只是 `ArchitectCoder` → `editor_coder` 的链式调用,不是独立 agent 运行时。
5. **OpenAI_Codex_CLI 4×4 = 16 种配置**:不是 3 种"Suggest/Auto-Edit/Full-Auto",而 `approval_policy` × `sandbox_policy` 4×4 矩阵。CLI 的 `--full-auto` 已 deprecated,改用 `--sandbox workspace-write`。
6. **OpenClaw 没有 ask_user 弹选项工具**:**严格意义的"向用户弹选项让用户选"的 ask 工具——没有**;只有 3 模式 approval(allow-once/allow-always/deny)。Onion 应做真正的 ask_user 工具。
7. **OpenHands 没有 ask_user 工具**:**没有"问用户问题"的专用工具**,只有 confirm_ask 弹窗。
8. **OpenAI_Codex_CLI 调研纠正:无 git worktree 隔离**:经代码级搜索确认。Codex 走的是 `parent_thread_id` 串 tree + 共享 `state_5.sqlite`,**没有 git worktree 隔离**。Cline Kanban 才有 git worktree。
9. **Aider append-only chat history 不写回**:`.aider.chat.history.md` 永远 append,**只影响 LLM 调用,不写回文件**;chat history 越来越大。
10. **Open_Interpreter Python 时代 `loop_breakers` 字符串匹配**:LLM 可能在分析中自然产出"魔法字符串"→ 假性退出;Rust 时代已改 `needs_follow_up` 布尔信号。

### 10.4 Onion 启示(Q9)

| 启示 | 行动 |
|---|---|
| **必做 AGENTS.md 兼容** | 扫描 cwd 向上到 .git 边界 + 字节上限 32 KiB + `AGENTS.md` / `AGENT.md` / `CLAUDE.md` / `ONION.md` 多命名兼容 |
| **必做 Slash commands 系统** | `/compact` `/init` `/rewind` `/steer` `/stop` 5 个起步,后续可加 |
| **必做 Multi-layer state machine** | 7 状态起步:PAUSED/STUCK/FINISHED/WAITING_FOR_CONFIRMATION/RUNNING/IDLE/ERROR |
| **必做 Provider 抽象层** | OpenAI Chat Completions 风格内部表示 + Adapter 翻译(Anthropic/Gemini/Ollama/GLM/Qwen) |
| **必做 MCP 协议支持** | `~/.onion/mcp.json`(全局)+ `<repo>/.onion/mcp.json`(项目级) |
| **可选 Plugin / Extension 系统** | P2 阶段;`~/.onion/plugins/` + manifest.json |
| **可选 Hook 事件系统** | P2 阶段;PreToolUse/PostToolUse/SessionStart/Stop/PreCompact 5 个起步 |
| **可选 Sandbox / OS-level 隔离** | P2 阶段;Windows Restricted Token + Linux Landlock/seccomp + macOS Seatbelt |
| **不要"autoDream"等不存在的功能** | 以源码为准,不被用户描述误导 |

---

## 11. 20 个项目总览对照表

| 项目 | 类别 | Loop 模式 | Plan | Sub Agent | 退出数 | Ask | HITL | 权限 | 压缩层数 | 核心差异化 |
|------|------|----------|------|----------|------:|-----|------|------|------:|----------|
| **OpenClaw** | 通用 | B(5 层正交) | update_plan(`content: []`) | sessions_spawn + subagents(2 工具) | 12 | ❌(只有 3 模式 approval) | 5 入口(/steer/inbound/interrupt/approval//stop) | 3 态 + hardline(timeout fail-closed) | 6 层 | **5 层正交状态机**;**HEARTBEAT.md + YAML 任务文件** |
| **superpowers** | 通用 | 编排(不是 loop) | 静态 markdown 5 段 | 派"子 skill"(本质是 prompt) | skill checklist | 宿主 AskUserQuestion | 5 决策门 + mid-loop 禁问 | 0 工具 + 5 Iron Law | n/a(无) | **TDD for skills**;**Skill 描述只写 when-to-use,不写 what** |
| **Hermes_Agent** | 通用 | C(L1 + L2 Ralph loop) | 4 套机制(todo + Kanban + /goal + GoalContract) | Kanban dispatcher(Popen + env pinning) | 多种 | clarify 工具 | 4 入口 | 6 层(L0 hardline / L5 allowlist) | 5 层 | **Multi-Agent Kanban**;**Zombie 检测**(PID+heartbeat);**Checkpoints v2 单 shared git store** |
| **AutoGPT** | 通用 | A+D(三套并存) | TodoComponent 9 命令 + Planner | ExecutionContext | 2 | ask_user/ask_yes_no/ask_choice | 4-scope × 5-layer | 3 deny/allow/session | 4 策略级联 | **AI Agent 鼻祖**;**Platform graph + AutoPilot 三套并存** |
| **Opencode** | 编程 | B(内层三态 + 外层 while) | plan agent 走同 processor(仅 permission 不同) | task 工具(general/explore) | 多 | question 工具 | 4 reply + CorrectedError | 3 态 + wildcard + 物理移除 | 2 层(轻 prune + 重 compaction) | **内层 processor.ts 三态 return**;**Stream.takeUntil`needsCompaction`** |
| **Claude_Code** | 编程 | A+E(stream 驱动) | EnterPlanMode/ExitPlanMode | Task 工具(4 内置类型) | 多种 | AskUserQuestion | 4 入口 + /rewind | 5 档 mode + 3 档基础 | 多种 | **13 plugin + 12 hook 事件**;**Ralph Wiggum 自循环**(200 行 bash) |
| **Gemini_CLI** | 编程 | B+E(Turn.run yields) | EnterPlanModeTool/ExitPlanModeTool | AgentTool 独立 budget | 8 | ask_user 工具 | Folder-Trust + Tool 4 Outcome | 4 ApprovalMode × 3 PolicyDecision | 3 阶段(truncate → summary → **probe verification**) | **1M 上下文**;**probe verification 首创**;**4 类 memory + JIT** |
| **OpenAI_Codex_CLI** | 编程 | B+C(3 层嵌套) | ModeKind::Plan + update_plan(互斥) | spawn_agent(共享 state_5.sqlite + parent_thread_id tree) | 多 | request_user_input | Op::ExecApproval + Op::UserInputAnswer | 4 档 × 4 档 = 16 组合 | 3 层(soft cap + rollout + compact) | **OS 级纵深防御沙箱**;**Terminal-Bench 77.3% 第一**;**9 层 ConfigLayerStack** |
| **OpenHands** | 编程 | B+E(7 状态) | 专用子 agent preset(PlanningFileEditorTool) | 3 套(Delegate/Task/Workflow) | 8 | ❌(只有 confirm) | 6 类 hook | 3 层(annotation + Risk + SecurityAnalyzer) | per-event JSON | **FileStore 抽象**;**3 层权限**;**navigate_to 任意点回滚** |
| **Cline** | 编程 | B(Plan/Act = session 重建) | plan mode 切 system message | new_task(嵌套 SessionRuntime)+ Kanban 独立 npm 包 | 多 | ask_question | 多种 | 3 态 + YOLO | 75% 阈值 + 50% 更激进 | **Plan/Act = session 重建**;**Kanban 每 task 独立 git worktree**;**HubSessionClient 统一审批协议** |
| **Open_Interpreter** | 编程 | A→B→C 演化(LMC → 原生 function call) | update_plan checklist | 5 multi-agent 工具(spawn/wait/send_input/close/resume) | 6 | request_user_input(1-3 questions + 2-4 options + auto_resolution_ms) | 4 层 | 3 sandbox × 3 approval × 2 reviewer = 18 | 4 档 fallback | **LMC 协议**;**9 语言 REPL**;**三轴正交 sandbox/approval/reviewer** |
| **Aider** | 编程 | A(单 while) | 99% prompt-as-tool + reflection 3 次 | 退化(ArchitectCoder 链式调用) | 4(无 max_iter) | AskCoder(11 行只换 prompt) | confirm_ask 14 触发点 | 几乎无(只 shell 弹) | 3 层(L1 token + L2 ChatSummary + L3 append-only md) | **git 仓库即状态机**;**repo map 设计**;**99% prompt-as-tool 反例价值** |
| **Continue** | 编程 | A(stream 递归) | plan mode 不存状态(刷新丢) | CLI 端 Subagent 工具复用 streamChatResponse | 4(隐式) | AskQuestion | 3 档 disabled/allowedWithPermission/allowedWithoutPermission | 3 档 | 80% auto-compaction | **`AGENTS.md`/`AGENT.md`/`CLAUDE.md` 3 命名兼容**;**`.continuerc.json disableIndexing` 哨兵** |
| **MetaGPT** | 多 Agent | D(Team+Environment+Role 三层) | WBS 文件 + Agent 内存 | set_actions 显式 | 多种 | ask_human + reply_to_human | 5 种 | set_actions 显式无 per-call 权限 | 共享 ProjectRepo | **`cause_by` 字段做隐式 SOP DAG**;**MGXEnv TeamLeader 中转** |
| **AutoGen** | 多 Agent | D(GroupChat + Manager 4 拓扑) | 4 层(Task/PlannerTaskPydanticOutput/ReasoningPlan/TodoList) | 4 种拓扑(RoundRobin/Selector/MagenticOne/Swarm) | 10 | UserProxyAgent | HandoffTermination + save_state | Workbench 列表 | GroupChat context | **Pydantic Component 完美序列化**;**Magentic-One 双 Ledger** |
| **CrewAI** | 多 Agent | D(Plan-and-Act Flow) | 4 层(Task/PlannerTaskPydanticOutput/ReasoningPlan/TodoList) | allow_delegation + DelegateWorkTool | 5 | HumanInputProvider(终端回环) | 4 层 | 字段=False / cache=True / @before_tool_call | 5 路径(mark_cache_breakpoint 等) | **`@CrewBase` 自动绑 `base_directory`**;**Plan-and-Act Flow** |
| **ChatDev** | 多 Agent | D(YAML DAG) | 静态 YAML 5 件套 | 角色分工(CEO/CTO/Programmer/Tester) | 5 层防御 | type: human 节点 | 多种 | YOLO + sandbox by default | 硬截断 + 边控制 + Memory | **YAML DAG 双层循环**;**5 层防御退出**;**`type: human` 节点** |
| **Lobe_Chat** | 多 Agent | B+E(AgentRuntime + QStash) | Plan/Todo/Sub-agent 都是 LLM 工具 | 5 种 | 8 | 多 | 5 层策略 | 持久化 allow-list | 100 条 group-aware | **5 状态 status 字段代替 break**;**Server 端 QStash 异步**;**5 种 ToolSource** |
| **Roo_Code** | 编程 | B(5 Mode 差异) | Architect Mode(7 步) | Orchestrator(`new_task` 委派) | 6 | Ask Mode(独立设计) | 8 类触发器 | 7 类 AutoApproval + 写保护清单 | 3 级(tree-sitter + 滑窗 + Profile) | **5 个内置 Mode + Custom Mode**;**Orchestrator 自身 `groups: []`**;**写保护清单 10 pattern** |
| **SuperAGI** | 通用 | C(Workflow step + Iteration step) | AgentWorkflow(DAG) | Celery 异步并发(无树) | 5 | 多 | 多 | God Mode 默认 | 3 层 LTM 摘要 | **Celery 单步异步 + Postgres 状态机**;**`apply_async(countdown=2)`**;**3 层 LTM 摘要递归** |

---

## 12. Onion Agent 推荐组合(P0/P1/P2)

> 这一节是**给用户后续设计 Onion Agent Agent Loop 的具体行动清单**。基于本标准 9 维度 + 5 顶层哲学 + 用户洋葱架构哲学,优先级如下。

### 12.1 P0(MVP 必做)

| 维度 | 具体实现 | 依据标准 |
|-----|---------|---------|
| **Loop 架构** | **B + C 双层**——外层 `loop_iteration` 跑 turn/session,内层 `process_step` 跑 LLM+tool+回灌 | §1.1 / §2 |
| **max_iteration 必做** | base(24) + profile×8 缩放;clamp [32, 160];**默认不能是 `inf`**(Aider / AutoGPT 反例) | §2.2 / §5.5 |
| **双 cap 退出** | `max_iteration` 硬上限 + `max_token` / `max_cost` 预算 | §5.2 |
| **退出决策点单一** | 参考 OpenClaw `terminal-resolution.ts` 单一决策点 | §5.6 |
| **Plan Mode + update_plan 双轨(互斥)** | Plan Mode(独立 mode,只读工具)+ update_plan 工具(执行态 checklist),Plan Mode 期间禁 update_plan | §1.2 / §3 |
| **强制 1 in_progress** | `update_plan` schema 校验:`At most one step can be in_progress at a time` | §3.2 |
| **Plan 文件不污染 LLM context** | 工具返回 `content: []` + `details: { plan: [...] }` 推 UI(参考 OpenClaw) | §3.3 / §3.5 |
| **Sub-agent 隔离** | sub-agent = 隔离的子 session.json(`~/.onion/sessions/<main_id>/<sub_id>.json` 形成树) | §1.5 / §4 |
| **Sub-agent depth cap** | `MAX_SUBAGENT_DEPTH=3`(参考 Cline) | §4.3 |
| **Sub-agent 不能直接 ask** | 只能 `attempt_completion` 写回 result | §4.3 |
| **LLM 主动 ask 工具** | 借 Claude_Code / OpenAI_Codex_CLI schema:`{questions: [{header ≤12, question, options: 2-4, multiSelect}]}` | §1.4 / §6.2 |
| **Plan mode 期间允许 ask,Execute mode 默认禁** | 借 OpenAI_Codex_CLI `allows_request_user_input` 字段 | §6.4 |
| **3 档权限(allow/ask/deny)** | 不要走 Aider 的"信任用户"路线 | §1.3 / §8.2 |
| **YOLO + hardline 兜底** | hardline 清单:自身配置/SSH 密钥/系统关键路径/危险命令/Catastrophic subshell | §8.2 / §8.6 |
| **Plan 模式 = 工具物理移除** | 借 Opencode:不是"调了再 deny",而是"从 LLM 工具 schema 移除" | §8.3 / §8.6 |
| **Pre-tool approval 100%** | AbortController / cancellation token 主流实现 | §7.2 |
| **approval timeout fail-closed** | timeout 默认拒绝,不"超时默认放行"(参考 OpenClaw `timeoutBehavior: "allow"` 已 deprecated) | §7.5 / §8.5 |
| **持久化 Always Allow 3 scope** | session / workspace(`<project>/.onion/policies.yaml`)/ user(`~/.config/onion/policies.yaml`) | §7.3 / §8.3 |
| **Token 阈值 80% 主动触发压缩** | 不要等 context 满了才压缩;`isOverflow` 80% 阈值立即 mid-turn auto-compact | §1.4 / §9.2 |
| **6 层叠加压缩(参考 OpenClaw)** | L1 工具结果截断 30% / L2 mid-turn 50% 守卫 / L3 preemptive / L4 LLM-driven / L5 manual / L6 history turn limit | §1.4 / §9.6 |
| **压缩后主动写回 session.json** | Aider 反例(只改内存不写回文件)不能学 | §9.5 / §9.6 |
| **压缩失败 fail-closed** | `max_compact_retries=3`,3 次失败 exit | §9.5 / §9.6 |
| **head 压 + tail 保** | LLM 总结 head 早期 messages,保留 tail 最近 messages | §9.2 / §9.6 |
| **Reasoning 独立 channel** | 把 `reasoning_content` 单独流出来,不入主 answer | §2.3 / §9.3 |
| **AGENTS.md 兼容 3 命名** | 扫描 cwd 向上到 .git 边界 + 字节上限 32 KiB + `AGENTS.md` / `AGENT.md` / `CLAUDE.md` / `ONION.md` 兼容 | §10.4 |
| **MCP 协议支持** | `~/.onion/mcp.json`(全局)+ `<repo>/.onion/mcp.json`(项目级) | §10.1 |
| **Provider 抽象层** | OpenAI Chat Completions 风格内部表示 + Adapter 翻译(Anthropic/Gemini/Ollama/GLM/Qwen) | §10.1 / §10.4 |
| **Multi-layer state machine** | 7 状态起步:PAUSED/STUCK/FINISHED/WAITING_FOR_CONFIRMATION/RUNNING/IDLE/ERROR | §10.1 / §10.4 |
| **Slash commands 系统** | `/compact` `/init` `/rewind` `/steer` `/stop` 5 个起步 | §10.1 / §10.4 |

### 12.2 P1(MVP 后期)

| 维度 | 具体实现 | 依据标准 |
|-----|---------|---------|
| **GoalContract(5 字段 contract)** | 借鉴 Hermes_Agent + OpenAI Codex "strong goal"——outcome/verification/constraints/boundaries/stop_when | §3.4 |
| **Judge LLM 评估 plan** | Hermes + AutoGen MagenticOne 模式 | §3.4 |
| **Plan 自动重 plan(replan on failure)** | 借鉴 CrewAI `replan_count` + `handle_replan` | §3.4 |
| **Plan 内嵌 reflection loop** | Aider `max_reflections=3`;superpowers task reviewer | §3.4 |
| **3-6 次连续错误熔断退出** | Cline `MistakeTracker`;`max_consecutive_errors=6` 退出 | §5.3 |
| **Save/load 跨 session 状态** | 7/20 项目都做;Onion 至少支持中断后 `load_state` 恢复 | §5.3 / §5.6 |
| **ask 工具支持 multiSelect + 多问题** | P1 阶段加;MVP 可只支持单问题 + 单选 | §6.4 / §6.6 |
| **ask 工具支持 `auto_resolution_ms`** | 借 Open_Interpreter;避免无人值守任务卡住 | §6.3 / §6.6 |
| **Hook 决策高于 mode 决策** | 借 Claude_Code 经验:"hook ask now floors the auto-mode decision" | §7.4 / §7.6 |
| **Stop hook 阻断 → 续推 prompt** | Claude_Code Ralph Wiggum 模式——hook 读状态文件 → 决定 block/allow → block 时把原 prompt 喂回 LLM → 无限自循环直到 `<promise>DONE</promise>` | §5.4 / §10.1 |
| **Multi-strategy 级联压缩** | Open_Interpreter(4 档 fallback);SuperAGI(3 层 LTM);Gemini_CLI(3 阶段) | §9.3 / §9.4 |
| **Probe verification 压缩后回测** | 借 Gemini_CLI 首创;P1 阶段加 | §9.4 / §9.6 |
| **Anchor incremental summary** | SuperAGI `_build_ltm_summary` 递归 | §9.4 / §9.6 |
| **Snapshot 备份压缩前状态** | 旧版本归档到 `snapshot/session_<timestamp>.json`,永不删 | §9.4 / §9.6 |
| **group-aware 截断** | 100 条 = 100 个"组",不切 group 内的 message(参考 Lobe_Chat) | §9.4 / §9.6 |
| **Long-term memory(MEMORY.md / USER.md)** | 借 Hermes_Agent + OpenClaw `memory/YYYY-MM-DD.md`;P1 阶段加 | §10.1 |
| **Plugin / Extension 系统** | `~/.onion/plugins/` + manifest.json;参考 Cline / Claude_Code | §10.1 / §10.4 |
| **Hook 事件系统** | PreToolUse/PostToolUse/SessionStart/Stop/PreCompact 5 个起步 | §10.1 / §10.4 |
| **Multi-channel 接入(IM)** | OpenClaw 20+ channels;P1 阶段加核心 3-5 个(Telegram/Slack/Discord) | §10.1 |
| **RAG 检索式压缩(摘要 + 检索 + 引用)** | 借 OpenHands / Lobe_Chat;P1 阶段加 | §9.4 |

### 12.3 P2(信创增强 / 长期演进)

| 维度 | 具体实现 | 依据标准 |
|-----|---------|---------|
| **OS 沙箱** | Windows Restricted Token + Linux Landlock/seccomp + macOS Seatbelt(参考 Codex) | §8.4 / §10.1 |
| **Docker 沙箱** | Dockerfile + docker-compose.yml;参考 OpenHands | §10.1 |
| **Smart Approval(aux LLM 评估)** | Hermes_Agent L4;OpenHands ToolShield 多 LLM 投票;**P2 阶段再考虑**(增加成本 + 引入不确定性) | §8.4 |
| **Approver 投票(多 LLM 评估)** | OpenHands ToolShield;P2 阶段 | §7.4 |
| **跨 session 异步 ask** | Hermes_Agent Gateway 异步 threading.Event + 1s 轮询;P2 阶段 | §6.4 |
| **审计日志(audit log)** | 写到 `~/.onion/logs/hitl_<session_id>.jsonl`;P2 阶段 | §7.4 / §7.6 |
| **Kanban 多 Agent 并行任务板** | 借 Cline Kanban(独立 npm 包 + git worktree);P2 阶段 | §4.4 |
| **Sub-agent 物理隔离(独立 git worktree)** | P2 阶段;默认逻辑隔离,要做 Kanban 时再考虑 git worktree | §4.4 / §4.6 |
| **DAG 编排主驱动** | AutoGPT Platform graph;MetaGPT Team+Environment+Role;AutoGen GroupChat;P2 阶段考虑 | §2.4 / §10.1 |
| **CLI + IDE + SDK 三形态** | Cline/Cl模式;P2 阶段;Onion MVP 只做 CLI | §10.1 |
| **企业级加密 secrets** | AES-256-GCM 加密 `auth.json`(参考 Lobe_Chat);P2 阶段 | file_backend 8.5 关联 |
| **完整 schema 迁移** | 借鉴 Lobe Chat 129 个 migration,Alembic 风格 | file_backend 5.6 关联 |
| **不做 D 模式 Goal loop by default** | 强 goal 任务作为可选 advanced mode(Hermes 风格),不在 MVP 必做 | §3.6 |

### 12.4 反例警示清单(Onion 不要踩的坑)

| 反例项目 | 反例 | Onion 启示 |
|---------|------|-----------|
| **Aider** | 99% prompt-as-tool,无 ask 中间态 | 不要走"信任用户"路线;必须 3 档权限 + 必须 ask_user 工具 |
| **Aider** | 无 max_iter,纯靠用户退出 | 必须有"60 秒无进展"或"50 轮无完成"之类的硬 cap |
| **Aider** | append-only chat history 不写回文件 | 压缩后必须**主动写回 session.json** |
| **superpowers** | "Do not pause to check in with your human partner between tasks" | 不能借鉴;Onion 必须有 ask 中间态 |
| **AutoGPT** | `cycle_budget` 默认 `math.inf` | Onion 必须有"必须 cap"的硬性默认 |
| **AutoGPT** | Classic + Platform + AutoPilot 三套 loop 并存 | Onion 不应同时维护多套 loop |
| **OpenClaw** | 无 ask_user 弹选项工具 | Onion 必须做真正的 ask_user 工具 |
| **OpenClaw** | `timeoutBehavior: "allow"` 已 deprecated 强制 fail-closed | Onion 必做 fail-closed timeout |
| **OpenHands** | 无 ask_user 工具 | 不要重蹈 OpenHands 覆辙 |
| **Open_Interpreter Python** | `loop_breakers` 字符串匹配 | Onion 不要用 LLM 文本里的魔法字符串;用结构化 finish 标签 |
| **Hermes_Agent** | "autoDream" 实际不存在(只有 `Background review`) | 不要被"功能名称"误导,以源码为准 |
| **OpenAI_Codex_CLI** | 调研假设"git worktree 隔离"实际不存在 | Onion 设计 multi-agent 时**不要**用 git worktree 做主隔离(可选项) |
| **OpenAI_Codex_CLI** | `apply_async(countdown=2)` Celery 单步异步 | Onion 简单 CLI 不学这种重架构 |
| **CrewAI** | `--storage-path` help 与代码不一致 | Onion 文档必须 100% 一致(参考 file_backend 8.5) |
| **Cline** | 母公司 2026-05-15 已关停 VS Code 扩展 | Onion 不依赖任何商业供应商,完全自研 |
| **MetaGPT** | `shutil.rmtree` 无备份清空旧项目 | Onion 路径校验防 shell 注入 + 路径穿越(参考 file_backend 8.3) |

---

## 13. 文档说明

### 13.1 本标准的不变性与演进

- **不变性**:
  - **3 档权限 + YOLO + hardline 兜底**——不可妥协的安全底线
  - **LLM 显式 finish + max_iteration 双 cap**——不可妥协的退出机制
  - **`At most one step can be in_progress at a time`**——不可妥协的 plan 硬约束
  - **approval timeout fail-closed**——不可妥协的安全策略
  - **压缩后主动写回 session.json**——不可妥协的持久化策略
- **演进原则**:
  - 新模式出现 ≥15/20 项目采用,纳入"必须做"
  - 现有"必须做"如果 <15/20 采用,降级为"强烈建议"
  - 反例(0-2/20 且明确有害)升级为"禁止"

### 13.2 与其他标准的关系

- `harness/01_market_research/standard/file_backend.md` — 工作区维度
- `harness/01_market_research/standard/tool_channel.md` — 工具调用维度
- `harness/01_market_research/standard/agent_loop.md` — **本文档,Agent Loop 维度**

这 3 份是**并列关系**,关注点不同:
- file_backend 关注"工作区路径 + session 存储 + 配置管理"
- tool_channel 关注"工具协议 + schema + 工具注册 + 结果回传"
- **agent_loop 关注"主流程 + Plan + Sub-agent + 退出 + Ask + HITL + 权限 + 压缩"**

### 13.3 引用规范

- 所有证据引用格式:`<项目名>/agent_loop.md:Q<n>:<简述>` 或 `<项目名>/agent_loop.md:<行号>`
- 20 份单项目报告:`harness/01_market_research/<项目目录>/agent_loop.md`
- 3 份组内提炼稿:`harness/01_market_research/_intermediate_{loop_internal,loop_external,loop_crosscutting}.md`
- 顶部引用:`harness/01_market_research/top_20_react_agent.md`

### 13.4 调研局限

- 调研基于 2026-07-13 实时 GitHub 数据,star 数有变动,不影响 Agent Loop 设计结论
- 部分项目(如 Claude Code / Open Interpreter)主仓库部分闭源,通过 SDK + CHANGELOG + docs 推断
- 10 处"用户描述与实际不符"已在 §10.3 反例警示中明确标注
- 调研时间:2026-07-18(20 份 agent_loop.md) + 2026-07-18(3 份提炼稿)
- 总投入:20 个子代理调研(每代理 1-2 小时)+ 3 个提炼子代理(每代理 1-2 小时)+ 主控整合(本文件)

---

**报告完。**
