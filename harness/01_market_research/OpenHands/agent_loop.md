# OpenHands — Agent Loop 调研报告

> 调研对象：`All-Hands-AI/OpenHands`（原 OpenDevin，Devin 复刻项目）
> 调研日期：2026-07-18
> 调研范围：`openhands-ai`（app_server） + `All-Hands-AI/agent-sdk` v1.36.0（**核心 SDK**） + `openhands-tools` v1.36.0（工具集）
> 调研方法：clone `OpenHands/` 主仓库 + 浅克隆 `All-Hands-AI/agent-sdk.git` 到 `clone/OpenHands-sdk/`，读源码 + `pyproject.toml` 依赖清单

---

## 0. 智能体一句话定位

**OpenHands（原 OpenDevin，Devin 复刻项目）** 是一个**自主软件工程 Agent**——在隔离的 Docker / 远程沙箱里执行代码、改文件、跑测试、提交 PR。2026 年它正在做一次**重大的架构拆分**：

| 层 | 仓库 | 作用 |
|---|---|---|
| `openhands-ai`（本仓库 `OpenHands/`） | `All-Hands-AI/OpenHands` | **企业级 app_server**：FastAPI + 多租户 + settings DB + SaaS 控制平面 + 旧 V0 兼容 |
| **`openhands-sdk`** | `All-Hands-AI/agent-sdk` | **核心 Agent Loop、Conversation、Event、LLM、Security、Tool 抽象、Workspace、Condenser、Skills、SubAgent、Hooks、Plugin**——所有"实际跑 agent"的代码都在这里 |
| **`openhands-tools`** | `All-Hands-AI/agent-sdk` | **内置工具集**（Terminal / FileEditor / Browser / Planning / Task / Delegate / Workflow / Glob / Grep / Tom-consult / ApplyPatch 等） |
| **`openhands-agent-server`** | `All-Hands-AI/agent-sdk` | **沙箱 HTTP 服务**：把 SDK 包装成 FastAPI，对外暴露 conversation / bash / file / event / settings / llm / openai 兼容 API |

**核心 Agent Loop 不在本仓库，而在 `openhands-sdk` v1.36.0 包中**。本仓库只通过 `from openhands.sdk import ...` 把它装进来（见 `openhands/app_server/app_conversation/live_status_app_conversation_service.py:125-145`）。

---

## 1. 调研依据

### 1.1 源码路径

| 仓库 | 路径 | 角色 |
|---|---|---|
| 主仓库 | `C:\workspace\github\onionagent\harness\01_market_research\clone\OpenHands\` | `openhands-ai` 1.36.0，app_server |
| SDK | `C:\workspace\github\onionagent\harness\01_market_research\clone\OpenHands-sdk\` | `openhands-sdk` 1.36.0，**核心 agent loop** |
| 工具集 | `C:\workspace\github\onionagent\harness\01_market_research\clone\OpenHands-sdk\openhands-tools\` | 内置 tools |
| agent-server | `C:\workspace\github\onionagent\harness\01_market_research\clone\OpenHands-sdk\openhands-agent-server\` | FastAPI 沙箱运行时 |

### 1.2 关键代码

#### 1.2.1 Agent Loop 入口

- `openhands-sdk/openhands/sdk/conversation/impl/local_conversation.py:1725` `LocalConversation.run()` — **同步 run loop**
- `openhands-sdk/openhands/sdk/conversation/impl/local_conversation.py:1900+` `LocalConversation.arun()` — **异步 run loop**
- `openhands-sdk/openhands/sdk/agent/agent.py:613` `Agent.step()` — **单步 LLM 调用 + 响应分类 + 工具分发**
- `openhands-sdk/openhands/sdk/agent/agent.py:737` `Agent.astep()` — **异步版 step**
- `openhands-sdk/openhands/sdk/agent/base.py:607` `AgentBase.step()` — **抽象 step 接口**

#### 1.2.2 双层架构（控制平面 / 运行时）

- `openhands/app_server/app_conversation/live_status_app_conversation_service.py:400-660` `start_app_conversation()` / `_start_app_conversation()` — **app_server 启动流程**
- `openhands/app_server/sandbox/sandbox_service.py` — **沙箱生命周期管理**
- `openhands/app_server/sandbox/{docker,remote,process}_sandbox_service.py` — **三种 sandbox 后端**
- `openhands-sdk/openhands/agent_server/event_service.py:905` `EventService.run()` — **agent-server 内的 run 启动**
- `openhands-sdk/openhands/sdk/workspace/remote/base.py:50` `RemoteWorkspace` — **控制平面与运行时之间的 HTTP 网关**

#### 1.2.3 FileStore 抽象（4 种实现）

- `openhands-sdk/openhands/sdk/io/base.py` `FileStore` — **核心 ABC**
- `openhands-sdk/openhands/sdk/io/local.py` `LocalFileStore` — **本地 + filelock + LRU 缓存**
- `openhands-sdk/openhands/sdk/io/memory.py` `InMemoryFileStore` — **纯内存 + threading.Lock**
- `openhands/app_server/file_store/{local,s3,google_cloud,memory,files}.py` — **app_server 侧 4 后端（多一个 S3）**

#### 1.2.4 关键模块

- Plan：`openhands-tools/openhands/tools/preset/planning.py:140` `get_planning_agent()` + `PlanningFileEditorTool`
- Sub Agent：`openhands-sdk/openhands/sdk/subagent/registry.py:151` `register_agent()` + `tools/delegate/impl.py:33` `DelegateExecutor`
- 任务/委托：`openhands-tools/openhands/tools/task/manager.py:113` `TaskManager` + `tools/task/impl.py:25` `TaskExecutor`
- Workflow（动态编排）：`openhands-tools/openhands/tools/workflow/impl.py:65` `WorkflowExecutor`
- 退出：`openhands-sdk/openhands/sdk/tool/builtins/finish.py:55` `FinishAction` + `FinishTool`
- 权限：`openhands-sdk/openhands/sdk/security/confirmation_policy.py` `AlwaysConfirm` / `NeverConfirm` / `ConfirmRisky`
- 风险等级：`openhands-sdk/openhands/sdk/security/risk.py:18` `SecurityRisk` (`LOW`/`MEDIUM`/`HIGH`/`UNKNOWN`)
- 防御性 analyzer：`openhands-sdk/openhands/sdk/security/defense_in_depth/pattern.py:42` `PatternSecurityAnalyzer`（regex 签名）+ `policy_rails.py`
- 上下文压缩：`openhands-sdk/openhands/sdk/context/condenser/llm_summarizing_condenser.py` + `context/condenser/base.py`
- 事件存储：`openhands-sdk/openhands/sdk/conversation/event_store.py:42` `EventLog`（per-event JSON）
- 事件类型：`openhands-sdk/openhands/sdk/event/llm_convertible/{action,message,observation,system}.py` + `event/types.py`（`EventID`）
- 多 LLM 路由：`openhands-sdk/openhands/sdk/llm/router/{base,impl/multimodal,impl/random}.py` + `llm/fallback_strategy.py`
- Hooks（Claude Code 风格）：`openhands-sdk/openhands/sdk/hooks/{config,executor,manager,conversation_hooks}.py`
- Skills：`openhands-sdk/openhands/sdk/skills/skill.py` + `openhands-tools/openhands/tools/preset/subagents/*.md`（4 个内置子 agent 定义）
- Marketplace / Plugin：`openhands-sdk/openhands/sdk/{marketplace,plugin}/*`
- Stuck 检测：`openhands-sdk/openhands/sdk/conversation/stuck_detector.py:46` `StuckDetector`
- Observability：`openhands-sdk/openhands/sdk/observability/laminar.py:59`（基于 Laminar + OpenTelemetry OTLP）
- MCP：`openhands-sdk/openhands/sdk/mcp/{client,config,tool,utils}.py` + `mcp/__init__.py`
- Secrets（`secrets` 注入到工具参数）：`openhands-sdk/openhands/sdk/secret/secrets.py:30` `SecretSource` / `StaticSecret` / `LookupSecret`

### 1.3 文档引用

- `openhands-ai/README.md` + `openhands-ai/AGENTS.md:166-167` "current V1 application server lives in `openhands/app_server/`"
- `openhands-ai/pyproject.toml:60-63` 依赖：`openhands-agent-server==1.36.0` / `openhands-sdk==1.36.0` / `openhands-tools==1.36.0`
- `agent-sdk/AGENTS.md:5-20` monorepo 根说明
- `agent-sdk/openhands-sdk/openhands/sdk/subagent/AGENTS.md` subagent 设计
- `agent-sdk/openhands-sdk/openhands/sdk/context/condenser/README.md` condenser 策略
- `OpenHands/skills/README.md:10-26` V0 microagents / V1 skills 命名
- `OpenHands/AGENTS.md:1-50` 主仓库开发流程

---

## 2. 九大问题回答

### Q1. Agent Loop 主流程（含 Mermaid 流程图）

#### 1.1 双层架构

OpenHands 的"运行 agent"实际上由**两个独立的进程**协同完成：

```
┌──────────────────────────────────────────────────────┐
│  控制平面：app_server（openhands-ai 进程）          │
│  • FastAPI + 多租户（用户/组织/订阅）               │
│  • Settings / SaaS / 持久化目录 ~/.openhands/       │
│  • 启动 sandbox（Docker / remote / process）       │
│  • 通过 AsyncRemoteWorkspace HTTP 调用 agent-server │
└────────────────┬─────────────────────────────────────┘
                 │ HTTP/WS（RemoteWorkspace → agent-server）
                 ▼
┌──────────────────────────────────────────────────────┐
│  运行时：agent-server（独立 Docker 容器）            │
│  • 加载 openhands-sdk 真正跑 agent loop            │
│  • 在沙箱内执行 bash / 文件编辑 / 浏览器            │
│  • 把事件流持久化到 FileStore（/workspace/...）     │
│  • 通过 WebSocket 把事件推回 app_server            │
└──────────────────────────────────────────────────────┘
```

**两边各有一个 EventLog**：
- app_server 端：`./{user_id}/v1_conversations/{conv_id}/event-*.json`（V1 主存）
- agent-server 端：`/workspace/conversations/{conv_id}/event-*.json`（沙箱内，运行态）

#### 1.2 完整 Mermaid 流程图

```mermaid
flowchart TD
    A[用户在 Web UI 发送 prompt] --> B[app_server: POST /api/v1/conversations]
    B --> C[live_status_app_conversation_service.py<br/>_start_app_conversation]
    C --> D[启动或复用 sandbox<br/>Docker / remote / process]
    C --> E[组装 Agent + 加载 skills<br/>+ 加载 hooks + 注入 MCP]
    C --> F[创建 AsyncRemoteWorkspace<br/>host=agent-server:8000]
    F --> G[agent-server: POST /api/conversations<br/>StartConversationRequest]
    G --> H[ConversationService._start_conversation<br/>openhands-agent-server/.../conversation_service.py:735]
    H --> I[EventService 创建 LocalConversation<br/>加载 base_state.json + event 索引]
    I --> J[EventService.run<br/>event_service.py:905 创建 background task]
    J --> K[LocalConversation.run / arun<br/>sdk/conversation/impl/local_conversation.py:1725]

    K --> L{while True<br/>run loop}
    L -->|status 检查| M[检查 status:<br/>PAUSED / STUCK / FINISHED /<br/>WAITING_FOR_CONFIRMATION / IDLE]
    M -->|PAUSED/STUCK| N[跳出 loop]
    M -->|FINISHED + 有 stop hook| O[run_stop hook<br/>可拒绝停止,继续 loop]
    O -->|hook 允许停| N
    O -->|hook 拒绝停| L
    M -->|WAITING_FOR_CONFIRMATION| P[跳出 loop,等待用户回复]
    M -->|RUNNING| Q[StuckDetector.is_stuck<br/>基于最近 20 个事件]
    Q -->|stuck=true| R[设置 STUCK,continue]
    Q -->|stuck=false| S[Agent.step<br/>agent.py:613]

    S --> T[prepare_llm_messages<br/>从 cached view 取事件]
    T --> U{condenser}
    U -->|返回 Condensation| V[emit Condensation 事件,return]
    V --> L
    U -->|返回 messages list| W[make_llm_completion<br/>通过 RouterLLM → 真实 LLM]
    W --> X[response_type = classify_response<br/>TOOL_CALLS / CONTENT / REASONING_ONLY / EMPTY]

    X -->|TOOL_CALLS| Y[_handle_tool_calls<br/>逐个 ActionEvent + security_risk 提取]
    Y --> Z{SecurityAnalyzer.analyze_pending_actions}
    Z -->|HIGH risk| AA[confirmation_policy.should_confirm<br/>HIGH → 设 WAITING_FOR_CONFIRMATION,跳出]
    Z -->|OK| AB[_execute_actions<br/>ParallelToolExecutor 并行执行]
    AB --> AC[emit ActionEvent + ObservationEvent]
    AC --> AD[iterative_refinement 检查<br/>需要时触发 critic]
    AD --> L

    X -->|CONTENT| AE[_handle_content_response<br/>emit MessageEvent]
    AE --> AF{FinishAction?}
    AF -->|是| AG[set execution_status = FINISHED]
    AF -->|否| L

    X -->|REASONING_ONLY/EMPTY| AH[_handle_no_content_response]
    AH --> L

    L -->|budget 超|max_budget_per_run| AI[emit ConversationErrorEvent MaxBudgetReached]
    L -->|iteration 达|max_iteration_per_run| AJ[emit ConversationErrorEvent MaxIterationsReached]
    L -->|正常 FINISHED| N

    AA --> AK[前端显示 confirm 对话框]
    AK -->|用户确认| AL[再次 run, status 切回 RUNNING]
    AL --> L
    AK -->|用户拒绝| AM[emit UserRejectObservation, FINISHED]

    subgraph "Event 存储"
        ES1[agent-server 端 FileStore<br/>open /workspace/conversations/{conv_id}/event-{idx:05d}-{id}.json]
        ES2[app_server 端通过 RemoteWorkspace 镜像<br/>~/.openhands/{user_id}/v1_conversations/{conv_id}/]
    end

    AC --> ES1
    ES1 -.HTTP GET/POST.-> ES2
```

#### 1.3 简化版文字描述

1. **app_server 启动对话**（`live_status_app_conversation_service.py:400-660`）：
   - 选/启动 sandbox
   - 通过 `get_default_tools(enable_browser, enable_sub_agents)` 装配工具
   - 调 `_load_skills_onto_request` 加载 skills、`_load_hooks_from_workspace` 加载 hooks、`_add_system_mcp_servers` 注入系统 MCP
   - `AsyncRemoteConversation` 通过 HTTP 连到 agent-server

2. **agent-server 启动 run**（`event_service.py:905`）：
   - 异步执行 `_run_and_publish` 协程
   - 优先用 `conversation.arun()`（异步 LLM I/O），否则用线程池跑 `conversation.run()`
   - 加锁 `_run_lock` + `_run_task` 防止并发

3. **核心 run loop**（`local_conversation.py:1725`）：
   ```
   while True:
       # 1. 状态守卫
       if status in (PAUSED, STUCK, FINISHED, WAITING_FOR_CONFIRMATION): break
       # 2. Stuck 检测（最近 20 个事件）
       if stuck_detector.is_stuck(): status = STUCK; continue
       # 3. WAITING_FOR_CONFIRMATION → RUNNING（用户已确认）
       # 4. Agent.step(conversation, on_event, on_token)
       # 5. 失败 / 触发停止条件 → break
   ```

4. **Agent.step**（`agent.py:613`）：
   ```
   step():
     1. 处理 pending actions（confirmation mode 第二轮）
     2. 准备 LLM 消息（prepare_llm_messages → condenser.condense）
     3. make_llm_completion → LLM 响应
     4. classify_response → TOOL_CALLS / CONTENT / REASONING_ONLY / EMPTY
     5. _handle_*  分支处理
   ```

5. **TOOL_CALLS 路径**（`agent.py` + `security/analyzer.py`）：
   - 逐个 `_get_action_event` 生成 ActionEvent
   - 用 `SecurityAnalyzer.analyze_pending_actions` 给每个 action 打 risk
   - 如果 `confirmation_policy.should_confirm(risk)` → 切 `WAITING_FOR_CONFIRMATION` 并 break
   - 否则 `_execute_actions` 用 `ParallelToolExecutor.execute_batch` 并行执行
   - 每个 action → `ObservationEvent`
   - 任何错误 → `AgentErrorEvent`

6. **FINISHED 路径**：
   - LLM 调 `FinishAction` 工具（`tool/builtins/finish.py:55`）→ 切 `FINISHED`
   - 或 LLM 调 `TaskToolSet` 启动子 agent → 主 agent 不结束，等子 agent 返回
   - 或 ACP agent（`acp_agent.py:3098`）每轮结束 emit `FinishAction`

#### 1.4 FileStore 抽象（4 种实现）

OpenHands 在两个地方有"FileStore 抽象"，但语义**不同**：

##### 1.4.1 SDK 侧（`openhands-sdk/openhands/sdk/io/`）

- `FileStore` ABC（`base.py:10`）— `write` / `read` / `list` / `delete` / `exists` / `get_absolute_path` / `lock`（带 timeout 的 context manager）
- `LocalFileStore`（`local.py:34`）— 本地 + 路径沙箱（`os.path.commonpath` 防越狱）+ `filelock.FileLock` + LRU 缓存
- `InMemoryFileStore`（`memory.py:30`）— `MemoryLRUCache` + `threading.Lock`
- 注：SDK 侧**只有这 2 种实现**——EventLog（`event_store.py:42`）用它来存 per-event JSON

##### 1.4.2 app_server 侧（`openhands/app_server/file_store/`）—— 4 种

```python
# openhands/app_server/file_store/__init__.py:7-23
FileStore = Annotated[
    LocalFileStore | S3FileStore | GoogleCloudFileStore | InMemoryFileStore,
    Field(discriminator="kind"),
]
```

- `LocalFileStore`（`local.py`）— 本地 + 临时文件 + atomic rename + fsync
- `S3FileStore`（`s3.py`）— boto3
- `GoogleCloudFileStore`（`google_cloud.py`）— google-cloud-storage
- `InMemoryFileStore`（`memory.py`）— **仅文本**（二进制会 corrupt 警告）
- 选择：`OH_FILE_STORE` (V0) / `OH_FILE_STORE_KIND` (V1) 环境变量 + `DiscriminatedUnionMixin` 路由

> **两套 FileStore 互不相关**：SDK FileStore 存的是 agent-server 沙箱内的事件；app_server FileStore 存的是控制平面（settings、事件镜像）。

---

### Q2. Plan 计划机制

#### 2.1 实现方式

OpenHands 的 **Plan 是一个独立的 agent preset**，不是"在主 agent 里有一个 plan 字段"。

- 入口：`openhands-tools/openhands/tools/preset/planning.py:140` `get_planning_agent(llm)`
- Plan 文件：`{working_dir}/.agents_tmp/PLAN.md`（默认，可改 `plan_path`）
- 工具集：`get_planning_tools()` 返回 3 个工具：
  - `GlobTool`（`tools/glob`）
  - `GrepTool`（`tools/grep`）
  - **`PlanningFileEditorTool`**（`tools/planning_file_editor/definition.py:73`）—— **可以 view 任何文件，但 edit 只能改 PLAN.md**

#### 2.2 Plan 文档结构

`planning.py:23-69` 强制 PLAN.md 包含 5 段（`PLAN_STRUCTURE`）：

```python
PLAN_STRUCTURE = [
    ("OBJECTIVE", "..."),                          # 1
    ("CONTEXT SUMMARY", "..."),                    # 2
    ("APPROACH OVERVIEW", "..."),                   # 3
    ("IMPLEMENTATION STEPS", "..."),                # 4
    ("TESTING AND VALIDATION", "..."),              # 5
]
```

`PlanningFileEditorTool.create()`（`definition.py:101-150`）在第一次创建时自动用 `get_plan_headers()` 写入 5 个 `# N. SECTION` 标题。

#### 2.3 Plan 与主 Agent 的协作

**没有主 agent 自动调 planning agent 的内置流程**——plan 是**可选项**，由用户在配置中显式选择。

- app_server 装配时（`live_status_app_conversation_service.py:1827`）：`if request.profile == "planning": tools = get_planning_tools(plan_path=...)`
- 也就是说，"plan" 是 OpenHands 提供的一个**专门用于规划的 agent preset**，通过 system prompt（`system_prompt_planning.j2` + `plan_structure` kwargs）告诉 LLM 严格按这 5 段写
- 主 agent 完成后，PLAN.md 通过 `live_status_app_conversation_service.py:1156-1162` 在下次会话中作为 `.agents_tmp/PLAN.md` 持久化
- **没有 LLM 实时回写**：plan 是用户/agent 显式通过 `PlanningFileEditorTool` 的 str_replace / insert 修改

#### 2.4 与"plan 模式"的差异（重要）

OpenHands 的"plan 模式"是**两种东西**：

1. **规划 agent preset**（上面 Q2.1-2.3）—— 一个**专用子 agent** 来生成 PLAN.md
2. **Wait-for-confirmation 模式**（`security/confirmation_policy.py:50`）—— 任何 action 都需要用户确认，对应 `execution_status = WAITING_FOR_CONFIRMATION`

后者跟"plan 模式"看起来像，但不是一回事。

---

### Q3. Sub Agent

**是，OpenHands 有非常完整的 Sub Agent 体系**。有 **3 种不同抽象**，各有不同语义：

#### 3.1 第一层：子 agent 注册表（`subagent/registry.py`）

**Discovery 顺序**（`subagent/AGENTS.md:30-70`）：
1. **Programmatic** `register_agent(...)`（最高优先级）
2. **Plugin-provided** agents
3. **Project** file-based：`{project}/.agents/agents/*.md` > `{project}/.openhands/agents/*.md`
4. **User** file-based：`~/.agents/agents/*.md` > `~/.openhands/agents/*.md`
5. **SDK built-ins**：`openhands-tools/openhands/tools/preset/subagents/*.md`（最低）

**Schema**（`subagent/schema.py`）—— frontmatter：
```yaml
name: code-reviewer
description: |
  Reviews code changes.
  <example>please review this PR</example>   # 触发示例
tools: [ReadTool, GrepTool]                   # 工具名列表
model: inherit                                 # inherit = 用父 agent 的 LLM
color: purple
```

#### 3.2 第二层：4 个内置子 agent（`openhands-tools/.../preset/subagents/`）

| Name | File | 工具集 | 用途 |
|---|---|---|---|
| `general-purpose` | `default.md` | terminal + file_editor + task_tracker | 通用编程任务 |
| `bash-runner` | `bash_runner.md` | terminal | 跑 shell 命令,精炼返回 |
| `code-explorer` | `code_explorer.md` | （只读工具） | 代码探索 |
| `web-researcher` | `web_researcher.md` | terminal + browser | 网络调研 |

#### 3.3 第三层：3 种调用抽象

##### 3.3.1 `Delegate` 工具（`tools/delegate/impl.py:33` `DelegateExecutor`）

- 父 agent 用 `delegate` 工具 spawn/delegate 多个子 agent
- 行为：spawn（创建并配置子 agent） + delegate（并行发任务 + 阻塞等结果）
- **多 workspace**：父 agent 和子 agent **共享同一个 `parent_conversation.state.workspace.working_dir`**（`impl.py:198` `workspace_path = parent_conversation.state.workspace.working_dir`）—— 没有真正的多 workspace
- `subagent_type` 是注册表里的名字

##### 3.3.2 `Task` 工具（`tools/task/manager.py:113` `TaskManager` + `tools/task/impl.py:25` `TaskExecutor`）

- 跟 Delegate 类似，但**走 sub_conversation 临时目录**：
  - `persistence_dir = self._persistence_dir`（通常是父的 persistence_dir 下 `subagents/` 子目录）
  - `delete_on_close=True`（关掉子对话就删）
- 返回 `TaskObservation` 包含 `task_id` + 状态

##### 3.3.3 `Workflow` 工具（`tools/workflow/impl.py:65` `WorkflowExecutor`）

- **最强大**：让父 agent 写一段 Python 脚本（`async def main(wf):`），通过 `wf` 对象编排 sub-agent
- 提供 `wf.run_agent` / `wf.map_agents`（并行） / `wf.reduce_agent`（汇总） / `wf.pipeline`
- 脚本是 AST 校验 + 沙箱化（`_UNSAFE_CALLS` 黑名单：eval/exec/open/import 全部禁止）
- 父 agent 通过 `WorkflowAction(script=...)` 触发，返回 `WorkflowObservation`
- 典型用例：批量代码审计、安全扫描、并行多策略方案评审

#### 3.4 Sub-agent 共享 vs 独立 workspace

- **共享父 agent 的 working_dir**（delegate/task 都是）
- **独立的 persistence_dir**：delegate 是 `parent_persistence_dir/subagents/{conv_id}/`（`impl.py:212-216`），task 是 `self._persistence_dir`（manager 控制）
- **独立的 LLM 实例**：`sub_agent_llm = parent_llm.model_copy()` + `reset_metrics()`（每个子 agent 自己计 token）
- **独立的 confirmation policy**：默认继承父 agent 的，但 agent 定义里可显式指定

#### 3.5 ACP Agent

还有一种**外部 agent**——`openhands-sdk/openhands/sdk/agent/acp_agent.py` `ACPAgent`：

- 通过 [Agent Client Protocol](https://agentclientprotocol.com/) 调用**外部**的 LLM agent（Claude Code / Gemini CLI 等）
- **每轮 step = 一次外部完整 turn**（不是单次 LLM call）
- 强制在每轮结束时 emit `FinishAction` 来标记 turn 结束（`acp_agent.py:3098`）
- 可以**运行时切换**（`acp_agent.py:1073` 注释）—— `current_model_id` live PrivateAttr

---

### Q4. Loop 退出机制

**有 8 种退出路径**，每种都设置不同的 `ConversationExecutionStatus`：

| # | 触发 | Status | 错误码 | 源码 |
|---|---|---|---|---|
| 1 | LLM 调 `FinishAction` 工具 | `FINISHED` | — | `tool/builtins/finish.py:55` + `agent.py:_handle_content_response` |
| 2 | 用户 `pause()` | `PAUSED` | — | `local_conversation.py:2432` |
| 3 | 用户 `interrupt()` | `PAUSED` + `InterruptEvent` | — | `local_conversation.py:2482` |
| 4 | Stop hook 拒绝继续（FINISHED 后） | 保持 `RUNNING` | — | `local_conversation.py:1775-1794` |
| 5 | Stop hook 允许停止 | `FINISHED` | — | 同上 |
| 6 | 达 `max_iteration_per_run`（默认 500） | `ERROR` | `MaxIterationsReached` | `local_conversation.py:1865-1880` |
| 7 | 达 `max_budget_per_run`（USD 成本上限） | `ERROR` | `MaxBudgetReached` | `local_conversation.py:608-624` + `1860` |
| 8 | Stuck Detector 检测到死循环 | `STUCK` | — | `conversation/stuck_detector.py:46` + `local_conversation.py:1808-1813` |
| 9 | Confirmation policy 拒绝 | `WAITING_FOR_CONFIRMATION` | — | `agent.py:_requires_user_confirmation` |
| 10 | LLM 抛 context window 异常 | `ERROR`（无 condenser 时） | `LLMContextWindowExceedError` | `agent.py:767-785` |
| 11 | LLM 抛 content filter | **不退出**，nudge 重试 | — | `agent.py:710-733` |
| 12 | 工具执行 ValueError | **不退出**，emit `AgentErrorEvent` | — | `agent.py:_execute_action_event` |

**关键代码段**（`local_conversation.py:1755-1884`）：

```python
while True:
    with self._state:
        if status in (PAUSED, STUCK): break
        if status == FINISHED:
            # 1) 跑 stop hook,允许拒绝
            if hook and not hook.run_stop("agent_finished").should_stop:
                # emit 反馈,status 改回 RUNNING,continue
                continue
            break
        if stuck_detector.is_stuck():
            status = STUCK; continue
        if status == WAITING_FOR_CONFIRMATION:
            status = RUNNING  # 用户已确认
        try:
            self.agent.step(self, on_event=self._on_event, on_token=self._on_token)
        finally:
            self._step_holds_state_lock = False
        if status == WAITING_FOR_CONFIRMATION: break
        if budget_exceeded and status != FINISHED:
            emit(MaxBudgetReached); break
        if iteration >= max_iteration_per_run:
            if status == FINISHED: break  # 保留 FINISHED
            emit(MaxIterationsReached); break
```

**FINISHED 状态再发消息能复活**（`local_conversation.py:1647-1650`）：

```python
if status in (FINISHED, STUCK):
    status = IDLE  # 新消息重置 terminal 状态
```

`is_terminal()`（`state.py:96-114`）：`FINISHED` / `ERROR` / `STUCK` 是 terminal（`IDLE` 不是）。

---

### Q5. Ask 模式

**没有"问用户问题"的专用工具**——OpenHands 的设计哲学是：**agent 问问题就是发普通 user message**，但有些机制实现"问而不执行"：

#### 5.1 显式 ask 模板

`openhands-sdk/openhands/sdk/context/prompts/templates/ask_agent_template.j2`：

```jinja
<QUESTION>
Based on the activity so far answer the following question

## Question
{{ question }}

<IMPORTANT>
This is a question, do not make any tool call and just answer my question.
</IMPORTANT>
</QUESTION>
```

这是给 `ask_agent` 类工具用的——通过 prompt 强制 LLM 只回答不调工具。

#### 5.2 实际行为：主要靠 **confirmation policy**

当用户开启 `ConfirmRisky` 或 `AlwaysConfirm` 策略（`security/confirmation_policy.py`）：

- 高风险 action（`HIGH` 或 `UNKNOWN`）会触发 `WAITING_FOR_CONFIRMATION` 状态
- 前端显示弹窗，**用户可以**：
  - 同意（`ALLOW`）→ 继续 run loop
  - 拒绝（`REJECT`）→ emit `UserRejectObservation` + 切 `FINISHED`（`agent.py:_handle_tool_calls` 的 confirmation 分支）
  - 改 action 文本后批准 → 用修改后的 action 重跑
- 这是 OpenHands 的"中断式 HITL"模式

#### 5.3 Plan agent 隐式 ask

规划 agent preset（Q2）就是**专门用来问问题**的子 agent——它没 terminal / file_editor 写权限，只能看代码 + 写 PLAN.md。父 agent 可以 spawn 一个 planning 子 agent 来"问规划问题"。

#### 5.4 任务上下文中的"问"语义

在主对话中 agent 想问用户，**做法是：发 MessageEvent（`source=agent`）+ 期待用户下一条 user message 进来**。`send_message()`（`local_conversation.py:1629`）会重置 `FINISHED` 状态为 `IDLE`，run loop 继续。

---

### Q6. Human-in-the-Loop (HITL)

**OpenHands 提供了非常完整的 HITL 体系**，从底层事件到 UI 都打通：

#### 6.1 6 个 hook 触发点（`hooks/config.py:25-30`）

```python
HOOK_EVENT_FIELDS = frozenset({
    "pre_tool_use",      # 工具执行前（可拒绝/改写 action）
    "post_tool_use",     # 工具执行后（可加上下文/拒绝 observation）
    "user_prompt_submit",  # 用户消息提交（可拒绝/改写）
    "session_start",     # 会话开始
    "session_end",       # 会话结束
    "stop",              # agent 想停时（可拒绝停）
})
```

每种 hook 支持 3 种执行类型（`hooks/config.py:40-50` `HookType`）：
- `COMMAND` —— 子进程跑 shell 命令（**Claude Code 风格**，stdio JSON）
- `PROMPT` —— LLM 评估
- `AGENT` —— 起子 agent 评估

#### 6.2 Web UI 交互

- 前端通过 WebSocket 订阅 EventService（`agent_server/sockets.py`）
- `MessageEvent`、`ActionEvent`、`ObservationEvent` 实时推送
- 用户操作：
  - **暂停** → `pause()` → 状态变 `PAUSED` → run loop 在下一轮 break
  - **恢复** → `resume()` → 状态切回 `IDLE` → 重新调 `run()`
  - **中断** → `interrupt()` → cancel current arun task → emit `InterruptEvent`
  - **导航/回滚** → `event_service.navigate_to(event_id)` → 重置 `leaf_event_id` → 重新跑从该点之后的步骤（**支持 conversation tree + 任意时间点回滚**）
  - **confirm/reject** → 走 confirmation policy
  - **新建消息并发** → `send_message(run=False)` 在 run 期间也能入队（`local_conversation.py:1703` `_released_state_lock_during_io`）

#### 6.3 event_service.run 包装

`event_service.py:905-1055` `_run_and_publish`：

```python
async def _run_and_publish():
    try:
        if has_native_arun:
            await conversation.arun()         # 异步 LLM I/O
        else:
            await loop.run_in_executor(self._run_executor, conversation.run)  # 线程池
    except Exception:
        # backstop
        await loop.run_in_executor(None, self._mark_error_status_sync)
    finally:
        # 等所有 pending callback 完成（避免 race）
        if self._callback_wrapper:
            await loop.run_in_executor(None, self._callback_wrapper.wait_for_pending, 30.0)
        self._run_task = None
        await self._publish_state_update()
        # 自动重启（如果 send_message 时设了 _rerun_requested）
        ...
```

`has_native_arun` 检查（`event_service.py:961-967`）—— 4 个条件必须都满足才走异步：
1. `iscoroutinefunction(arun)`
2. `type(conversation).arun is not BaseConversation.arun`（不能是基类默认）
3. `type(conversation.agent).astep is not AgentBase.astep`（agent 必须 override astep）
4. （implicit）coroutine function

#### 6.4 Conversation Tree + 回滚

**OpenHands 的杀手锏**——**支持任意点回滚并重放**（不像大多数 agent 只能 forward）：

- `Event.parent_id`（`event/base.py:34-37`）—— 每个事件有父事件 ID
- `ConversationState.leaf_event_id`（`state.py:139-145`）—— 当前活动分支的 HEAD
- `ConversationState.head_is_empty`（`state.py:148-150`）—— 显式空 HEAD 标记
- `navigate_to(event_id)` —— 把 HEAD 设到任意过去事件，从那里重跑
- `_resolve_active_leaf`（`state.py:181-198`）—— 解析真实 HEAD，traverse 树回 root
- `path_to_root(leaf, limit)`（`event_store.py:108-127`）—— 取活动分支的所有事件

#### 6.5 LLM 运行中可注入

- `_released_state_lock_during_io`（`local_conversation.py:1700-1718`）—— `arun()` 在 LLM I/O await 时**主动释放** state lock
- 这意味着用户可以**在 LLM thinking 时**发新消息、调 `switch_llm` 切模型、触发新 hook
- LLM 响应回来后再 re-acquire lock

---

### Q7. 工具调用权限

**三层权限机制，层层递进**：

#### 7.1 Layer 1: 静态 annotation

每个 tool 在定义时声明（`tool/tool.py:ToolAnnotations`）：
```python
ToolAnnotations(
    title="terminal",
    readOnlyHint=False,
    destructiveHint=True,      # 是否破坏性
    idempotentHint=False,        # 幂等
    openWorldHint=True,          # 是否接触外部世界（网络/文件）
)
```

#### 7.2 Layer 2: 风险等级 + SecurityAnalyzer

- LLM 必须**对每个 action 主动声明 `security_risk`**（`agent.py:_extract_security_risk`）
- 4 个等级：`LOW` / `MEDIUM` / `HIGH` / `UNKNOWN`（`security/risk.py:18`）
- SecurityAnalyzer 子类：
  - **default**（`security/analyzer.py`）—— 直接看 LLM 声明的 risk
  - **`PatternSecurityAnalyzer`**（`security/defense_in_depth/pattern.py:75`）—— regex 签名扫描：rm -rf / curl|sh / eval/exec / sudo rm / mkfs / dd raw disk / override / mode_switch / identity injection 等
  - **`PolicyRailSecurityAnalyzer`**（`security/defense_in_depth/policy_rails.py`）—— 复合条件规则
  - **`EnsembleSecurityAnalyzer`**（`security/ensemble.py`）—— 多 analyzer 求 max
  - **`LLMSecurityAnalyzer`**（`security/llm_analyzer.py`）—— 用 LLM 评估
  - **`ToolShield`**（`security/toolshield_helpers.py`）—— 多 LLM 投票

#### 7.3 Layer 3: Confirmation Policy（用户决策）

`security/confirmation_policy.py` 三种内置策略：

```python
class AlwaysConfirm:    # 所有都确认
class NeverConfirm:     # 都不确认
class ConfirmRisky:     # threshold (default HIGH) 以上才确认,UNKNOWN 单独配
```

判断逻辑（`agent.py:_requires_user_confirmation:992-1024`）：
```python
def _requires_user_confirmation(state, action_events):
    if len(actions) == 1 and isinstance(actions[0], (FinishAction, ThinkAction)):
        return False
    if not actions: return False
    if state.security_analyzer:
        risks = [r for _, r in analyzer.analyze_pending_actions(actions)]
    else:
        risks = [UNKNOWN] * len(actions)
    if any(state.confirmation_policy.should_confirm(r) for r in risks):
        state.execution_status = WAITING_FOR_CONFIRMATION
        return True
    return False
```

**FinishAction 和 ThinkAction 永远不需要确认**（agent 完工 / 思考不需要打扰用户）。

#### 7.4 拒绝处理

如果用户拒绝 confirmation（`event/llm_convertible/observation.py:UserRejectObservation`）：
- emit `UserRejectObservation` 注入 LLM
- agent 下一步看到 "user rejected your action" 继续
- 不会自动 FINISHED

#### 7.5 Multi-action 批次确认

一次 LLM 响应可能 emit 多个 tool calls（parallel function calling）—— **统一评估 + 任一风险高则全部 confirm**（`agent.py:_handle_tool_calls`）。

---

### Q8. 上下文压缩和摘要

#### 8.1 两种触发方式

1. **软触发**（resource limit）——`LLMSummarizingCondenser`（`context/condenser/llm_summarizing_condenser.py`）：
   - `max_size`（默认 120）+ `keep_first`（保留最早的 N 个）
   - 超过则把**前一半事件**压缩成 1 个 `Condensation` 事件（"tombstone"，类似 Cassandra/Kafka）
2. **硬触发**（显式 request）—— `Conversation.condense()`（`local_conversation.py:2655`）或 `CondensationRequest` 事件：
   - `LLMContextWindowExceedError` 抛错时自动 emit
   - 用户手动调用

#### 8.2 Condensation 策略（`context/condenser/README.md`）

- **默认策略**：用 LLM 把"前一半"event 流压缩成 summary，**后半部分完整保留**
- 优势：保留近期上下文，破坏 prompt cache 但可控
- 4 个阶段叠加（`PipelineCondenser` `pipeline_condenser.py`）：可串多个 condenser

#### 8.3 View + 增量维护

**性能优化亮点**——`ConversationState.view`（`state.py:308-340`）：

```python
@property
def view(self) -> View:
    with self._view_lock:
        leaf = self._resolve_active_leaf()
        if leaf == self._view_branch_leaf: return self._view  # 缓存命中

        # Fast path: 线性 append → 只 replay tail
        try:
            cur_id = leaf
            while cur_id and cur_id != self._view_branch_leaf:
                idx = self._events.get_index(cur_id)
                tail.append(self._events[idx])
                cur_id = self._events._effective_parent_id(idx, self._events[idx])
            if cur_id == self._view_branch_leaf:
                for evt in reversed(tail): self._view.append_event(evt)
                return self._view
        except Exception:
            ...

        # Slow path: 分支切换 / 首次 / 错误恢复 → 全量 rebuild + enforce_properties
        self._view = View.from_events(self._events.path_to_root(leaf))
        return self._view
```

- 链式追加：O(k)，其中 k 是新事件数
- 分支切换：O(n)，触发 `enforce_properties`（保证 LLM 消息对合规：tool_use/tool_result 配对、id 匹配等）

#### 8.4 Per-Event JSON 存储

**`EventLog`**（`conversation/event_store.py:42`）—— append-only per-event JSON：

```python
# persistence_const.py
BASE_STATE = "base_state.json"    # 状态/agent config
EVENTS_DIR = "events"
EVENT_FILE_PATTERN = "event-{idx:05d}-{event_id}.json"
EVENT_NAME_RE = re.compile(r"^event-(?P<idx>\d{5,})-(?P<event_id>[0-9a-fA-F\-]{8,})\.json$")
```

**event_id 管理**（`event/base.py:29-32`）：
```python
class Event(DiscriminatedUnionMixin, ABC):
    id: EventID = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    source: SourceType  # "agent" / "user" / "environment"
    parent_id: EventID | None  # 父事件 ID
```

- 每次 `append(event)` 加文件锁 `filelock.FileLock(lock_path, timeout=30s)`（`event_store.py:198-204`）
- 文件名格式 `event-{idx:05d}-{uuid}.json`（保证排序 + 唯一性）
- `id` 不可与 `ROOT_PARENT_ID`（保留 sentinel）相同
- 进程间一致性：启动时 `_scan_and_build_index` 扫描整个目录建索引

**没用 compaction / delta encoding**——纯追加，靠 LLM-side condenser 做语义压缩。

#### 8.5 事件类型

`event/__init__.py`：
- `ActionEvent`（agent 动作）
- `MessageEvent`（user/agent 消息 + extended_content / activated_skills）
- `ObservationEvent`（工具结果）
- `SystemPromptEvent`（系统提示）
- `AgentErrorEvent`（错误）
- `UserRejectObservation`（用户拒绝）
- `PauseEvent` / `InterruptEvent`（控制事件）
- `ConversationErrorEvent`（run 失败）
- `Condensation` / `CondensationRequest` / `CondensationSummaryEvent`（压缩）
- `ACPToolCallEvent`（外部 ACP agent 工具调用）
- `TokenEvent`（vLLM token_ids 流）

#### 8.6 状态压缩（resume_transcript.py）

为 resume/导出场景提供**纯文本 transcript 渲染**（`event/resume_transcript.py`）—— 但仅用于 UI 显示，不替代真实事件流。

---

### Q9. 其他亮点

#### 9.1 多 LLM 支持 + Router

- **底层用 LiteLLM**（`llm/llm.py:49-64`）—— 100+ provider 开箱
- **RouterLLM**（`llm/router/base.py:36`）—— 多个 LLM 抽象成 1 个
  - `MultimodalRouter`（`llm/router/impl/multimodal.py:18`）—— 有图片/超 token → 切到 primary (vision)，否则 secondary
  - `RandomRouter`（`llm/router/impl/random.py`）—— 随机切
- **FallbackStrategy**（`llm/fallback_strategy.py:39`）—— 主 LLM 失败自动 fallback 到 `LLMProfileStore` 里的备选 profile
- **LLMProfileStore**（`llm/llm_profile_store.py`）—— 命名 profile（"claude-opus" / "gpt-5" / "local-llama"）持久化在 `.openhands/profiles/`
- **SwitchLLM 工具**（`tool/builtins/switch_llm.py`）—— agent 可**在 run 中**切 profile：`SwitchLLMAction(profile_name="claude-opus", reason="需要更长上下文")`

#### 9.2 隔离沙箱（4 种 backend）

`openhands/app_server/sandbox/`：
- `docker_sandbox_service.py` —— Docker 容器
- `remote_sandbox_service.py` —— 远程 SSH/VM
- `process_sandbox_service.py` —— 本地进程（开发用）
- `sandbox_service.py` —— 抽象

每个 sandbox 暴露：
- 独立 `working_dir`（默认 `/workspace/project`）
- 独立 `tmux` 终端（agent-server 端，`tmux_pane_pool.py` 默认 4 pane 池）
- session_api_key（`session_auth.py`）鉴权

#### 9.3 企业级编码场景落地

- 完整 `enterprise/` 目录：Keycloak SSO + Stripe 订阅 + GitHub/GitLab/Jira/Linear/Slack 集成 + Alembic DB migration + Posthog telemetry
- `/api/v1/settings` + `/api/v1/conversations` + `/api/v1/file/upload` + WebSocket `/sockets/{conversation_id}/events`
- MCP server 端（`mcp_router.py`）—— 暴露 `create_pr` / `create_mr` 等企业工具
- workspace archive（`workspace_archive.py`）—— 删 sandbox 前 git-delta 归档到对象存储

#### 9.4 原 OpenDevin 历史

- 项目 2024-03 由 Cognition AI 发布 Devin 后由社区 fork → 改名 OpenDevin
- 2024-Q4 改名 OpenHands
- 2025 进入 OpenHands 公司化
- 2026 重大拆分：`agent-sdk` 仓库独立，定位为通用 Agent SDK
- `OpenHands/` 仓库主要承担 **app_server + 企业版 + 旧 V0 兼容**

#### 9.5 Skills / Plugin / Marketplace 系统

- **Skills**（V1）—— `openhands-sdk/openhands/sdk/skills/`
  - 4 类 trigger：`KeywordTrigger` / `PathTrigger` / `TaskTrigger` / 隐式 AgentSkills
  - 加载顺序：project > user > public
  - **支持 Anthropic Agent Skills 格式**（`SKILL.md` + frontmatter + `references/` 子目录，progressive disclosure）
- **Plugins**（`sdk/plugin/`）—— 第三方包，可包含 skills / hooks / MCP / agents / commands
- **Marketplaces**（`sdk/marketplace/`）—— 类似 Claude Code marketplace，`marketplace.json` 声明可装插件
- **Installed skills/plugins**（`installed.py`）—— 用户级，存 `~/.openhands/{plugins,skills}/installed/`
- **CLI skill**（`skills/skill.py:utils`）：`discover_skill_resources` 自动找 `scripts/` `references/` `assets/` 子目录

#### 9.6 Hooks（Claude Code 风格）

完整复刻 Claude Code 的 hook 协议：
- 6 个事件（pre/post tool use / user prompt submit / session start/end / stop）
- 3 种类型（command / prompt / agent）
- shell 命令通过 stdin/stdout 传 JSON
- 可拒绝/改写/添加上下文

#### 9.7 Checkpoints / Shadow Git

**OpenHands 没有显式 "checkpoint" 系统**——但**等价物是 conversation tree**：

- `Event.parent_id` 树结构 + `navigate_to(event_id)` 任意点回滚 = "time travel checkpoint"
- 每次 `append_event` 自动 `git commit` 不是 OpenHands 做法（依赖 workspace 自身 git）
- `workspace_archive.py:archive_workspace()` 在删 sandbox 前会 `git diff` 存成 patch

#### 9.8 多 LLM 优化 / Observability

- **Laminar 集成**（`observability/laminar.py:59`）—— 全部 step / tool / LLM call 走 OpenTelemetry OTLP
  - `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` 启用
  - 自动 span：`conversation.run` / `agent.step` / `tool.{name}`
- **Metrics 跟踪**（`conversation_stats.py`）—— 每个 LLM 的 token 用量、cost、延迟
- **Budget 控制**（`_budget_exceeded_detail`）—— 跨 agent + condenser 所有 LLM 的总 USD 花费

#### 9.9 Secrets 注入

- `secrets.py:SecretSource` ABC
- `StaticSecret(value=SecretStr)` —— 静态
- `LookupSecret(url, headers)` —— 运行时通过 agent-server `/api/secrets/{name}` HTTP 获取（不回显到 LLM）
- 自动注入到工具参数（`_secret_registry`）
- 红化（`utils/redact.py`）—— 日志里 secret 全替换成 `***`

#### 9.10 ACP（Agent Client Protocol）

- 可作为 **ACP client**（`sdk/agent/acp_agent.py`）—— 用 Claude Code / Gemini CLI 等外部 agent 当主循环
- 也可作为 **ACP server**（`agent_server/openai/router.py`）—— 暴露 OpenAI 兼容 API（`/v1/chat/completions`）
- 关键代码：`acp_agent.py:3236` `ACPAgent.step()` 把整个外部 turn 包成 1 个 step

---

## 3. 关键代码片段

### 3.1 run loop 主循环

```python
# openhands-sdk/openhands/sdk/conversation/impl/local_conversation.py:1740-1885
@observe(name="conversation.run")
def run(self) -> None:
    """Runs the conversation until the agent finishes."""
    self._ensure_agent_ready()
    self._cancel_token = CancellationToken()

    with self._state:
        if self._state.execution_status in [IDLE, PAUSED, ERROR, STUCK]:
            self._state.execution_status = RUNNING

    iteration = 0
    _run_start_event_count = len(self._state.events)
    try:
        while True:
            logger.debug(f"Conversation run iteration {iteration}")
            with self._state:
                # 1. PAUSED / STUCK → break
                if status in (PAUSED, STUCK): break

                # 2. FINISHED → run stop hook
                if status == FINISHED:
                    if self._hook_processor:
                        should_stop, feedback = self._hook_processor.run_stop(
                            reason="agent_finished"
                        )
                        if not should_stop:
                            # emit 反馈, 继续
                            if feedback:
                                self._on_event(MessageEvent(
                                    source="environment",
                                    llm_message=Message(role="user", content=[TextContent(text=...)])
                                ))
                            status = RUNNING; continue
                    break

                # 3. Stuck detection
                if self._stuck_detector and self._stuck_detector.is_stuck():
                    status = STUCK; continue

                # 4. 用户已确认 (WAITING_FOR_CONFIRMATION → RUNNING)
                if status == WAITING_FOR_CONFIRMATION:
                    status = RUNNING

                # 5. Agent step
                self._step_holds_state_lock = True
                try:
                    self.agent.step(self, on_event=self._on_event, on_token=self._on_token)
                finally:
                    self._step_holds_state_lock = False
                iteration += 1

                # 6. WAITING_FOR_CONFIRMATION 跳出
                if status == WAITING_FOR_CONFIRMATION: break

                # 7. Budget 超限
                if (budget_detail := self._budget_exceeded_detail()) and status != FINISHED:
                    self._emit_run_limit_error("MaxBudgetReached", budget_detail)
                    break

                # 8. Iteration 上限
                if iteration >= self.max_iteration_per_run:
                    if status == FINISHED: break
                    self._emit_run_limit_error("MaxIterationsReached", ...)
                    break
    except Exception as e:
        ...
```

### 3.2 Agent.step 主流程

```python
# openhands-sdk/openhands/sdk/agent/agent.py:613-795
@observe(name="agent.step", ignore_inputs=["state", "on_event"])
def step(self, conversation, on_event, on_token=None):
    state = conversation.state

    # 1. 处理 pending actions (confirmation mode 第二轮)
    pending = ConversationState.get_unmatched_actions(state.active_branch())
    if pending:
        self._execute_actions(conversation, pending, on_event)
        return

    # 2. UserPromptSubmit hook 拒绝 → FINISHED
    if state.last_user_message_id is not None:
        reason = state.pop_blocked_message(state.last_user_message_id)
        if reason is not None:
            state.execution_status = FINISHED
            return

    # 3. 准备 LLM messages (view + condenser)
    call_context = conversation.get_llm_call_context()
    _result = prepare_llm_messages(state.view, condenser=self.condenser, llm=self.llm)
    if isinstance(_result, Condensation):
        on_event(_result); return
    _messages = _result

    # 4. 非多模态 LLM 收到图片
    if _should_handle_non_multimodal_image_input(self.llm, _messages):
        if VISION_INSPECT_TOOL_NAME in self.tools_map:
            _messages = _replace_latest_user_images_with_references(_messages)
        else:
            on_event(MessageEvent(source="agent", llm_message=_non_multimodal_image_message(self.llm.model)))
            state.execution_status = FINISHED
            return

    # 5. LLM completion
    try:
        llm_response = make_llm_completion(
            self.llm, _messages,
            tools=list(self.tools_map.values()),
            on_token=on_token, call_context=call_context,
        )
    except FunctionCallValidationError as e:
        on_event(MessageEvent(source="user", content=[TextContent(text=str(e))])); return
    except LLMContentPolicyViolationError as e:
        # 不退出, nudge 重试
        on_event(MessageEvent(source="user", content=[TextContent(text="Rephrase to avoid the flagged content.")]))
        return
    except LLMContextWindowExceedError:
        if self.condenser.handles_condensation_requests():
            on_event(CondensationRequest()); return
        raise
    except LLMMalformedConversationHistoryError:
        if self.condenser.handles_condensation_requests():
            state.rebuild_view()
            on_event(CondensationRequest()); return
        raise

    # 6. 分类 + 分发
    message = llm_response.message
    response_type = classify_response(message)
    match response_type:
        case LLMResponseType.TOOL_CALLS:
            self._handle_tool_calls(message, llm_response, conversation, state, on_event)
        case LLMResponseType.CONTENT:
            self._handle_content_response(message, llm_response, conversation, state, on_event)
        case LLMResponseType.REASONING_ONLY | LLMResponseType.EMPTY:
            self._handle_no_content_response(...)
```

### 3.3 FileStore ABC

```python
# openhands-sdk/openhands/sdk/io/base.py
class FileStore(ABC):
    @abstractmethod
    def write(self, path, contents): ...
    @abstractmethod
    def read(self, path) -> str: ...
    @abstractmethod
    def list(self, path) -> list[str]: ...
    @abstractmethod
    def delete(self, path): ...
    @abstractmethod
    def exists(self, path) -> bool: ...
    @abstractmethod
    def get_absolute_path(self, path) -> str: ...
    @abstractmethod
    @contextmanager
    def lock(self, path, timeout=30.0) -> Iterator[None]: ...
```

### 3.4 Event per-JSON 存储

```python
# openhands-sdk/openhands/sdk/conversation/persistence_const.py
BASE_STATE = "base_state.json"
EVENTS_DIR = "events"
EVENT_NAME_RE = re.compile(r"^event-(?P<idx>\d{5,})-(?P<event_id>[0-9a-fA-F\-]{8,})\.json$")
EVENT_FILE_PATTERN = "event-{idx:05d}-{event_id}.json"

# openhands-sdk/openhands/sdk/conversation/event_store.py:198-222
def append(self, event):
    evt_id = event.id
    try:
        with self._fs.lock(self._lock_path, timeout=LOCK_TIMEOUT_SECONDS):
            disk_length = self._count_events_on_disk()
            if disk_length > self._length:
                self._sync_from_disk(disk_length)
            if evt_id in self._id_to_idx:
                raise ValueError(f"Event with ID '{evt_id}' already exists")

            payload = event.model_dump_json(exclude_none=True)
            with self._write_guard if self._write_guard else nullcontext():
                target_path = self._path(self._length, event_id=evt_id)
                self._fs.write(target_path, payload)
            self._idx_to_id[self._length] = evt_id
            self._id_to_idx[evt_id] = self._length
            self._event_cache[self._length] = event
            self._length += 1
```

### 3.5 Confirmation 决策

```python
# openhands-sdk/openhands/sdk/agent/agent.py:992-1024
def _requires_user_confirmation(self, state, action_events):
    # 1. 单一 FinishAction / ThinkAction 永不确认
    if len(action_events) == 1 and isinstance(action_events[0], (FinishAction, ThinkAction)):
        return False
    if len(action_events) == 0: return False

    # 2. Security analyzer 评估
    if state.security_analyzer is not None:
        risks = [risk for _, risk in state.security_analyzer.analyze_pending_actions(action_events)]
    else:
        risks = [SecurityRisk.UNKNOWN] * len(action_events)

    # 3. 任一 risk 触发 policy
    if any(state.confirmation_policy.should_confirm(risk) for risk in risks):
        state.execution_status = ConversationExecutionStatus.WAITING_FOR_CONFIRMATION
        return True
    return False
```

### 3.6 Plan 模板

```python
# openhands-tools/openhands/tools/preset/planning.py:23-69
PLAN_STRUCTURE: list[tuple[str, str]] = [
    ("OBJECTIVE", "Summarize the goal of the plan in one or two sentences..."),
    ("CONTEXT SUMMARY", "Briefly describe the relevant system components..."),
    ("APPROACH OVERVIEW", "Outline the chosen approach at a high level..."),
    ("IMPLEMENTATION STEPS", "Provide a step-by-step plan for execution..."),
    ("TESTING AND VALIDATION", "Describe how the implementation can be verified..."),
]

# openhands-tools/openhands/tools/planning_file_editor/definition.py:73-145
class PlanningFileEditorTool(ToolDefinition):
    """A planning file editor tool with read-all, edit-PLAN.md-only access."""
    # 限制: 只能 edit PLAN.md, 其他 view 全部允许
```

### 3.7 Sub-agent 注册

```python
# openhands-sdk/openhands/sdk/subagent/AGENTS.md:20-22
# discovery order (highest to lowest):
# 1. Programmatic register_agent()
# 2. Plugin agents
# 3. Project: {project}/.agents/agents/*.md > {project}/.openhands/agents/*.md
# 4. User: ~/.agents/agents/*.md > ~/.openhands/agents/*.md
# 5. SDK built-ins: openhands-tools/.../preset/subagents/*.md

# openhands-tools/openhands/tools/preset/subagents/default.md
---
name: general-purpose
model: inherit
description: |
   General-purpose subagent. Can read, write, and edit code, run shell commands...
tools:
  - terminal
  - file_editor
  - task_tracker
---
You are a general-purpose agent. You can read and write code, run shell commands,
and track tasks to solve tasks end-to-end.
```

### 3.8 Workflow 动态编排

```python
# openhands-tools/openhands/tools/workflow/impl.py:100+
class WorkflowContext:
    """Small capability object exposed to generated workflow scripts."""

    def __init__(self, parent_conversation, max_concurrency, manager=None):
        ...
        self._manager = manager or self._default_manager()
        self._semaphore: asyncio.Semaphore | None = None

    async def run_agent(self, prompt, subagent_type="general-purpose", description=None): ...
    async def map_agents(self, items, prompt, subagent_type="general-purpose", max_concurrency=None, description=None): ...
    async def reduce_agent(self, items, prompt, subagent_type="general-purpose", description=None): ...
    async def pipeline(self, items, *stages): ...

# _UNSAFE_CALLS = {breakpoint, compile, delattr, dir, eval, exec, getattr,
#                  globals, input, locals, open, setattr, vars, __import__}
# _UNSAFE_ATTRIBUTE_ROOTS = {"os", "subprocess"}
# 脚本沙箱化: AST 校验 + 注入 globals + 限制 max_concurrency (1-64)
```

### 3.9 app_server 启动对话

```python
# openhands/app_server/app_conversation/live_status_app_conversation_service.py:400-660
async def start_app_conversation(self, request):
    return await self._start_app_conversation(request)

async def _start_app_conversation(self, request):
    # 1. 启动/复用 sandbox
    sandbox = await self._find_or_start_sandbox(request)

    # 2. 组装 agent (with skills + hooks + MCP)
    agent = self._build_agent_for_request(request)

    # 3. 创建 RemoteWorkspace (HTTP gateway to agent-server)
    remote_workspace = AsyncRemoteWorkspace(
        host=agent_server_url,        # http://agent-server:8000
        api_key=sandbox.session_api_key,
        working_dir=working_dir,      # /workspace/project
    )

    # 4. 创建 RemoteConversation
    conversation = Conversation(
        agent=agent,
        workspace=remote_workspace,
        ...
    )
    return conversation
```

---

## 4. 与 Onion Agent 设计的关联

> Onion Agent 是用户正在开发的、基于"洋葱架构"的 ReAct 智能体。本节对照 OpenHands 的设计，给出可借鉴 / 需注意的点。

### 4.1 ✅ OpenHands 值得借鉴的设计

| 维度 | OpenHands 做法 | Onion 可借鉴点 |
|---|---|---|
| **Event 存储** | per-event JSON + 序号 + uuid 文件名 + filelock 进程级锁 | Onion 可用 `event-{idx:05d}-{uuid}.json` 同样的命名规范，天然支持 append-only + 任意点回滚 |
| **Conversation Tree** | `parent_id` + `leaf_event_id` + `navigate_to(event_id)` 任意点回滚 | Onion 可在 event 层加 `parent_id` 字段实现 time-travel checkpoint |
| **View 增量维护** | O(k) 增量 append + O(n) 全量 rebuild + branch 切换检测 | Onion 的 context 拼装可以借鉴 `view_branch_leaf` 缓存策略 |
| **状态机驱动** | 7 种 `ConversationExecutionStatus` (IDLE/RUNNING/PAUSED/WAITING/FINISHED/ERROR/STUCK) 显式枚举 | Onion 应该把 agent loop 状态做成显式 enum，避免隐式 boolean |
| **Stuck detection** | 最近 20 事件 + 4 种模式 (action-obs repeat / action-error / monologue / alternating) | Onion 可直接借鉴 `StuckDetector` 算法 |
| **Hook 系统** | Claude Code 风格的 pre/post tool use + user prompt submit + stop 等 6 个 hook 点 | Onion 若想兼容 Claude Code 用户，可实现同样 hook 协议 |
| **Confirmation Policy** | risk 等级 (LOW/MED/HIGH/UNKNOWN) + policy (Always/Never/ConfirmRisky) 解耦 | Onion 工具权限可参考这种 risk + policy 分离设计 |
| **Parallel tool execution** | `ParallelToolExecutor` 用 thread pool 并行跑多个 tool | Onion 如果一次响应有多个 tool call，可以并行执行 |
| **LLM Fallback** | `FallbackStrategy` 主 LLM 失败自动试备选 | Onion 可加 provider fallback 提升可用性 |
| **LLM Router** | `MultimodalRouter` / `RandomRouter` 按消息内容路由 | Onion 可加 cheap model + expensive model 路由 |
| **Sub-agent 复用父 LLM** | `parent_llm.model_copy()` + `reset_metrics()` | Onion sub-agent 可以继承父 agent 的 LLM 配置，省 token |
| **Async + sync 双 API** | `step()` / `astep()` + `run()` / `arun()`，自动降级到 thread pool | Onion 可考虑同样的双 API 设计 |
| **Budget 控制** | USD 成本上限 + iteration 上限 双保险 | Onion 一定要做 budget 控制，OpenHands 是行业最佳实践 |
| **MCP 双身份** | Client + Server 都能 | Onion 可考虑做 MCP server 把自有能力暴露出去 |
| **Skill 渐进式披露** | Anthropic Agent Skills 格式（SKILL.md + references/） | Onion 若想兼容 Claude，可采用同样格式 |

### 4.2 ⚠️ OpenHands 复杂的部分（Onion 可简化）

| 维度 | OpenHands 复杂度 | 简化建议 |
|---|---|---|
| **3 套 sub-agent 抽象** | delegate / task / workflow | Onion 选 1 套即可，建议从 `Task` 工具（最简单）开始 |
| **Plan 是独立 agent preset** | 没用"主 agent 内 plan 字段" | Onion 可直接在主 agent 加一个"plan 工具"，更轻量 |
| **V0/V1 双套术语** | microagents / skills 并存 | Onion 直接选新名字 |
| **2 套 FileStore** | SDK + app_server 各自实现 | Onion 可以 1 套 |
| **5 个 LLM 路由策略** | Router + Fallback + Profile + SwitchLLM | Onion 先做最简单的 Fallback |
| **6 种 SecurityAnalyzer** | Pattern / Policy / LLM / Ensemble / ToolShield / default | Onion 默认（让 LLM 自己声明 risk）即可 |
| **ACP 双角色** | Client + Server | Onion 短期不需要 |

### 4.3 🎯 关键借鉴决策建议

1. **Per-event JSON append-only**——选这个存储格式（OpenHands 验证过，可应对 4-8 小时的长任务）
2. **状态机 enum**—— `IDLE / RUNNING / PAUSED / WAITING_FOR_CONFIRMATION / FINISHED / ERROR / STUCK` 7 个状态足够覆盖大部分情况
3. **Stuck detector 早期集成**——防止 token 烧光
4. **Budget 双保险**——`max_iterations` + `max_cost_usd` 同时设
5. **Confirmation policy 从 day 1 接入**——避免后期改造
6. **Sub-agent 共享父 workspace**——别学 LangGraph 的 Send API 那套，OpenHands 简单很多
7. **Context condenser 别从 0 写**——直接抄 `LLMSummarizingCondenser` 即可

---

## 5. 不确定 / 未找到

| 编号 | 未知点 | 说明 |
|---|---|---|
| 1 | OpenHands 的原 V0 controller (旧 `agent_controller.py`) | 已被 v1.36 拆分到 agent-sdk 仓库，本仓库 V0 兼容代码藏在 `openhands/server/` (deprecated 兼容层) |
| 2 | OpenHands 是否对 V0 旧用户保留完整 backward compatibility | `openhands/server/` 仍存在但 `AGENTS.md:166` 说 "deprecated"——具体哪些接口保留未深挖 |
| 3 | `workspace_archive.py` 的 git-delta 与 .tar.gz 双格式选择逻辑 | 报告前文提及但未深入读 |
| 4 | Litellm provider prefix `_JOINT_BUDGET_PROVIDER_PREFIXES = ("bedrock",)` 完整推导 | Bedrock 的 input/output 共池，未确认是否还有其他 provider |
| 5 | OpenHands V0 的 `Runtime` (旧 docker runtime / local runtime / remote runtime) 抽象 | 已迁移到 `agent-server` 内，新架构下 `sandbox_service` 是更细粒度的抽象 |
| 6 | OpenHands 是否支持多个 agent 同时跑一个 task（team） | 调研发现 `add-multi-agent-delegation` 分支在 agent-sdk git log 里出现，**主线未包含** |
| 7 | `ACP` 协议完整 spec 文档 | `acp_agent.py` 引用了 agentclientprotocol.com 但本仓库没 vendored spec |
| 8 | OpenHands 的 secret 注入（`LookupSecret`）如何跟 LLM 通信 | `secrets.py:LookupSecret` 通过 `OH_INTERNAL_SERVER_URL` 拉取，但 LLM 端怎么 inject 没看到完整链路 |
| 9 | `Multi-step retry / 错误恢复` 跨 step 的实现 | 看到 `_released_state_lock_during_io` 但没看到完整的 error recovery strategy |
| 10 | `PauseEvent` / `InterruptEvent` 在 tool 执行中如何打断 long-running bash | 有 `cancel_token` 但具体跟 tmux / subprocess 怎么联动未看 `terminal/terminal/` 全部实现 |
| 11 | OpenHands V1 (agent-sdk) 的 git history 中"删 V0 旧 controller"的提交 | 想知道 OpenHands 走完 V0→V1 改造花了多久 commit, 需深挖 git log |
| 12 | V1 的 "skill progressive disclosure" 跟 Anthropic Agent Skills 协议完全对齐吗 | 看到 `is_agentskills_format: bool` 字段，但 references/ 子目录的语义是否跟 Anthropic 一致未确认 |

---

**报告完。**
