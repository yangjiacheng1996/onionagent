# Onion Agent 产品经理定版（v_final）

> **本文件是 PM 视角的定版蓝图。**
> 它不与 `project_manager.md` 做 v1/v2 对比。原文里的设计哲学我继续遵守；不符合调研共识 / 内部标准的地方，以本文为准。
> 上游依据：
> - `harness/market_research/onion_architecture.md`、`openai_three_role.md`、`top_20_react_agent.md`、`tool_accuracy.md`
> - `harness/market_research/deep_dive/*`（20 份）
> - `harness/market_research/standard/agent_loop_standard.md`、`plan_standard.md`、`file_backend_standard.md`、`tool_standard.md`
> - `harness/market_research/standard/difference.md`、`other_common.md`
> - `harness/demo/` 已写的 5 个脚本

---

## 0. 一句话原则

> **session.json 是唯一状态机；洋葱的核；其他都是围着它的壳。**
> 一切研发动作要回答 3 件事：
> 1. 这个动作在 `session.json` 里新增了哪条记录？
> 2. 这个动作能不能被一个 `python tools/demo_xxx.py` 直接看到效果？
> 3. 这个动作遵守 6 个 role 的边界吗？

---

## 1. 我是谁（PM 画像，决定整套设计哲学）

- 资深 Python 算法工程师，Python 自动化脚本出身（Linux 自动化、K8s 自动化、测试自动化、RPA）
- 习惯把"高度复用、原子化"的动作封装成库函数
- 倾向于洋葱架构：核心=session.json；外层=围着它的可替换模块
- 一人开发全栈，吃得下 demo CLI 的开发节奏

**这个画像直接决定 3 件事**：
- 一切皆字符串，py 文件原子化、CLI 化（→ 详见第 10 节"所见即所得"）
- 不依赖无法自托管的模型（→ 详见第 5 节"工具调用范式"的双路径）
- session.json 用纯 JSON 不用数据库（→ 详见第 7 节"File Backend"）

---

## 2. 洋葱架构落 Onin Agent 的最终映射

```
┌──────────────────────────────────────────────────────────┐
│ L1 表现层（onion cli / onion qt / HTTP / IM）            │  ← 只读 session.json
├──────────────────────────────────────────────────────────┤
│ L2 业务层（Agent Loop、Plan、Compactor、Compressor）     │  ← 唯一能写 session.json 的层
├──────────────────────────────────────────────────────────┤
│ L3 接口层（LLM Client、Tool Channel、Tool Shell）        │  ← 把外部协议翻译成内部 role
├──────────────────────────────────────────────────────────┤
│ L4 持久层（session.json 读写、JSONL 落盘、Checkpoint）   │  ← append-only + 原子写
├──────────────────────────────────────────────────────────┤
│ L5 基础设施（pathlib、asyncio、pydantic、json、requests）│  ← 纯标准库/常用库
└──────────────────────────────────────────────────────────┘
```

**关键约束**：
- **L2 唯一写**：L1/L3 都不能改 session.json。L1 想加 user 消息必须调 L2 的入口
- **append-only**：每条新记录都是 append，从不 mutate 历史（保护 prompt cache，详见第 8 节"反模式"）
- **L3 可替换**：换模型 / 换 MCP 实现不影响 L2

---

## 3. session.json：唯一状态机

### 3.1 session.json 不是"消息列表"，是状态机

每一行都是一个**确定的状态转移**。每条记录都有：
- `id`：唯一标识（uuid）
- `state`：`openai` / `tool` / `loop`（基础设施协议 = 状态机的"维度"）
- `role`：该 state 下的具体消息类型
- `timestamp`：ISO 8601 UTC
- `content` / `tool_calls` / `tool_call_id` / `metadata` 等字段按 role 决定

### 3.2 状态（state）= 基础设施协议

只有 3 个状态，奥卡姆剃刀：

| state | 对应基础设施 | 协议 |
|---|---|---|
| `openai` | LLM 通信 | OpenAI Chat Completions 协议（含 Anthropic / Gemini 兼容通道） |
| `tool` | 工具通道 | OpenAI Native FC 主路径 + Cline 风格 XML 降级路径 |
| `loop` | 循环控制 | 内部协议（plan / 压缩 / 中断 / 元数据） |

### 3.3 角色（role）= 状态内的具体消息类型

**LLM 可见 4 种**（会作为 `messages` 发给大模型）：

| role | state | content | 用途 |
|---|---|---|---|
| `system` | openai | 字符串 | 系统提示词（启动时注入） |
| `user` | openai | 字符串 | 用户输入 |
| `assistant` | openai | 字符串 / null | 大模型回答 |
| `tool` | tool | 字符串 | 工具执行结果（必带 `tool_call_id`） |

**LLM 不可见，磁盘可见 N 种**（用于诊断 / 调试 / 错题本 / resume）：

| role | state | 用途 | 是否可省略 |
|---|---|---|---|
| `tool_list` | tool | 工具 schema 快照（startup 一次） | 条件 |
| `call_mcp` | tool | MCP 工具调用解析留痕 | 条件 |
| `call_skills` | tool | Agent Skills 调用留痕 | 条件 |
| `call_buildin` | tool | 内置工具调用留痕 | 条件 |
| `call_loop` | tool | loop 自身工具调用留痕（如 update_plan） | 条件 |
| `plan` | loop | plan 看板快照（每次 update_plan 写一条） | 条件 |
| `show_plan` | loop | 用户在 UI 主动拉取 plan | 条件 |
| `update_plan` | loop | LLM 调 update_plan 工具的留痕 | 条件 |
| `compaction_needed` | loop | 压缩触发标记 | 条件 |
| `compaction_summary` | loop | 压缩后的摘要 | 条件 |
| `interrupted_by_user` | loop | 中断标记 | 条件 |
| `max_iterations_reached` | loop | 硬上限触达 | 条件 |
| `budget_exhausted` | loop | 预算耗尽 | 条件 |
| `tool_error` | loop | 工具错误不可恢复 | 条件 |
| `subagent_result` | loop | sub-agent 结果回灌 | 条件 |

**奥卡姆边界**：
- LLM 永远只看 4 种 role
- 磁盘落 N 种 role（够用即可，不预设上限）
- 新增 role 必须回答：这个 role 不能由现有 role + metadata 表达吗？

### 3.4 落盘 vs 可见矩阵（PM 自查表）

| role | 落 session.json | 发 LLM | 用途 |
|---|:---:|:---:|---|
| system | ✅ | ✅ | 启动时注入 |
| user | ✅ | ✅ | 用户消息 |
| assistant | ✅ | ✅ | LLM 回答 |
| tool | ✅ | ✅ | 工具结果 |
| tool_list | ✅ | ❌ | 启动时工具快照 |
| call_mcp / call_skills / call_buildin / call_loop | ✅ | ❌ | 工具调用留痕 |
| plan / show_plan / update_plan | ✅ | ❌ | plan 留痕 |
| compaction_needed / compaction_summary | ✅ | ❌ | 压缩 |
| interrupted_by_user / max_iterations / budget_exhausted / tool_error | ✅ | ❌ | 退出标记 |
| subagent_result | ✅ | ❌ | sub-agent 结果 |

### 3.5 物理落盘

**单 session 目录**：

```
<workspace>/agents/<agent_name>/sessions/<session_id>/
├── session.json          # 主文件（append-only，每条记录一行 JSON）
├── session.json.lock     # 同 session 互斥锁（防并发写）
├── metadata.json         # 循环元数据（cost / tokens / time / exit_reason）
├── attachments/          # 用户上传的二进制附件
├── checkpoints/          # resume 用的检查点（每 N 步一份）
└── subagents/            # sub-agent 的 session（与主 session 关联）
```

**写盘的 5 条铁律**（每个写文件的 py 文件都必须遵守）：
1. 每次 append 后立即 `fsync`
2. lock file 互斥（`fcntl.flock` / Windows 下的 `msvcrt`）
3. 临时文件 + atomic rename（`session.json.tmp` → `session.json`）
4. `schema_version` 必填
5. **绝对不允许 per-message mutation**（append-only）

---

## 4. 工具调用范式（v_final：双路径）

### 4.1 范式选择（基于 `tool_accuracy.md` 与 20 项目共识）

**主路径：OpenAI Native Function Calling**
- 工具 schema 走 `tools=[...]` 通道，**不进 system prompt**
- `tool_choice="auto"`（**禁止**用 `"required"` 诱导过度调用）
- 17/20 项目共识，准确率最高

**降级路径：Cline 风格 XML（已实现）**
- 当模型不支持 FC 时降级
- `<use_mcp_tool>` / `<skill_disclosure>` 等 XML 标签
- `harness/demo/agent_client.py` 已有完整实现

**绝对禁用**：
- 纯 JSON 文本块（解析错误率高）
- ReAct 文本格式（`Thought/Action/Observation`，不支持并行工具）
- 把工具列表塞进 system prompt（注意力分散）

### 4.2 终止信号（关键修正）

| 路径 | 终止信号 | 备注 |
|---|---|---|
| **FC 主路径** | assistant 消息 `tool_calls` 为空 | 自然终止，**首选** |
| **XML 降级路径** | assistant 文本中出现 `</agent_loop_finish>` | 显式标志，**降级** |

> 修正点：原 `project_manager.md` 写的"必须有 agent_loop_finish 标志才能结束"——这是降级路径的逻辑。主路径是"无 tool_calls = 完成"，更优雅。两条路径要共存。

### 4.3 3 级容错（每次工具调用都过）

```
tool call 接收
    ↓
{tool 存在?}
├── NO → is_error=True，"Tool not found: {name}. Available: {list}" 回灌 LLM
└── YES
    ↓
    {args 解析 OK?}
    ├── NO → json.loads → json-repair → jsonschema 三层兜底，全部失败回灌错误
    └── YES
        ↓
        {执行 OK?}
        ├── NO → exception 转 is_error=True 回灌
        └── YES → 写 tool result
```

**给 LLM 的错误信息**要写得像"人话"（带 hint），不是 dev-facing 报错。

### 4.4 Doom Loop 守卫（防死循环）

| 阈值 | 行为 |
|---|---|
| 连续 3 次同 tool call（name + args 完全一致） | 注入 user 警告，给 LLM 1 次自我修复机会 |
| 连续 5 次 | 硬停，loop exit_reason = `tool_error` |

参考实现：`harness/quality_audit_v1.md` §3 demo 11 已有计划。

### 4.5 4 种 ToolClient 分层

```
ToolShell
├── BuiltinToolClient    # read_file / write_file / edit_file / bash / update_plan / activate_skill
├── MCPClient            # stdio / SSE / Streamable HTTP 三种 transport
├── AgentSkillClient     # 渐进式披露（L1 元数据 / L2 指令 / L3 资源）
└── SubAgentToolClient   # sub-agent 委派（v2+）
```

`harness/demo/mcp_client.py` 与 `harness/demo/agent_skills_client.py` 已有可复用代码，**直接 import**。

### 4.6 工具描述 token 预算

- 总 context window - system prompt - history 50% = 工具描述预算
- 最近用过的工具必暴露
- 未暴露的工具 LLM 仍可通过 `tool_search` 主动搜索
- 禁止 hard-cap 600 字符（superagi 教训）

### 4.7 权限 wildcard

```toml
[tools.permissions]
default = "ask"   # ask / allow / deny

[tools.permissions.rules]
read_file = "allow"
write_file = "ask"
"bash:rm *" = "deny"
"bash:git *" = "allow"
"write_file:*.env" = "deny"
```

- 拒绝时不消耗 LLM 调用，直接 deny
- ask 时**暂停 loop**等用户响应
- 响应可"允许一次 / 总是允许 / 拒绝并附 feedback"

---

## 5. Agent Loop（基于 standard + 6 出口）

### 5.1 骨架：双层 while

```python
# 外层 while：决定"还要不要再调 LLM"
while iteration < max_iterations:
    outcome = self._single_step()
    if outcome == "completed": break
    if outcome == "compaction_needed": compress(); continue
    if outcome == "blocked": break   # 等人类

# 内层 single-step：一次 LLM + 一次 tool（原子）
def _single_step(self):
    assistant = self.llm.call(ctx)
    self.session.append(assistant)
    if not assistant.tool_calls: return "completed"
    if self.token_overflow(): return "compaction_needed"
    results = self.tool_shell.execute_batch(assistant.tool_calls)
    for r in results: self.session.append(r)
    return "tool_calls"
```

### 5.2 6 个显式 exit state（写回 session.json）

| exit state | 触发 | session.json 记录 |
|---|---|---|
| `completed` | LLM 返回无 tool_calls（主）/ 检测到 `</agent_loop_finish>`（降级） | 正常的最后一条 assistant |
| `max_iterations_reached` | 外层 while 计数器超 | 写 `loop/max_iterations_reached` |
| `interrupted_by_user` | 用户 Ctrl-C / UI 按钮 | 写 `loop/interrupted_by_user` |
| `compaction_needed` | 上下文超 80% 阈值 | 触发 compressor 后继续 |
| `budget_exhausted` | 用户配置了 `max_cost` / `max_tokens` | 写 `loop/budget_exhausted` |
| `tool_error` | 连续 5 次同 tool call（Doom Loop 硬停） | 写 `loop/tool_error` |

**6 个都必须实现**——这是 18/20 项目的硬共识。

### 5.3 软收尾（graceful shutdown）

达到 `max_iterations` 时**不抛异常**，而是：
1. 注入 user 消息"请总结已完成和未完成"
2. 让 LLM 跑一次（不调 tool）
3. 拿到 final answer 后写回 session
4. 退出，exit_reason = `max_iterations_reached`

### 5.4 Streaming 必备

- LLM 流式调用（`stream=True`）
- 流式 chunk 落库（每个 delta 持久化，不是只存 final）
- 流式 chunk 也算 token 计数
- 必须支持中途 abort（CancellationToken）

---

## 6. Plan 看板（基于 plan_standard）

### 6.1 数据结构

```python
class TodoStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
```

### 6.2 三条铁律

1. **严格状态转换**（pending → in_progress → completed 单向；允许 cancelled；completed 可回 pending）
2. **at most one in_progress**（强制，违反时 LLM 收到错误）
3. **plan 是 session.json 中的一种消息**（不是独立数据库表）

### 6.3 工具定义

单一工具 `update_plan`：

```json
{
  "name": "update_plan",
  "description": "Update the task plan. Provide explanation and full plan list. At most one item can be in_progress at a time.",
  "parameters": {
    "explanation": { "type": "string" },
    "plan": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "content": { "type": "string" },
          "status": { "enum": ["pending", "in_progress", "completed", "failed", "cancelled"] },
          "priority": { "enum": ["low", "medium", "high"] }
        },
        "required": ["content", "status"]
      }
    }
  },
  "required": ["plan"]
}
```

### 6.4 压缩保护

plan 消息**永远不被压缩**（与 system / first_user 同级保护）。压缩后 plan 自动 re-inject。

### 6.5 Markdown Checklist 渲染

工具返回内容渲染为：

```
Plan updated:
- [x] 分析用户需求
- [-] 设计 API schema
- [ ] 实现 CRUD
- [ ] 写测试
```

`[ ] / [-] / [x]` 三符号，git diff 友好。

---

## 7. File Backend（基于 file_backend_standard）

### 7.1 强制工作区

**所有平台统一 `~/.onion/`**（XDG 风格但不走平台特定路径）
- Windows：`C:\Users\<user>\.onion\`
- macOS：`/Users/<user>/.onion/`
- Linux：`/home/<user>/.onion/`

> **修订记录（2026-07-16）**：曾经按 XDG 规范用平台特定路径（Windows: `%LOCALAPPDATA%\onion\`；macOS: `~/Library/Application Support/onion/`；Linux: `$XDG_DATA_HOME/onion/`），但与 `cli/init.py` 的 `Path.home() / ".onion"` 实际取值分叉，导致 `init` 创建的工作区与 `agent list` / `agent create` 等命令操作的工作区不在同一目录。已统一为 `~/.onion/`。  
> 理由：跨平台一致、用户查找方便、备份迁移简单。

**API_KEY 明文放 `config.toml`**（不拆 .env，详见第 7.4 节"配置原则"）。

### 7.2 目录结构

```
~/.onion/
├── config.toml                   # 全局配置（明文，含 API_KEY）
├── agents/                       # 智能体目录
│   ├── default/                  # 默认智能体
│   │   ├── SOUL.md               # 人设/角色
│   │   ├── memory.md             # 长期记忆
│   │   ├── rules/                # 规则（自动注入 system prompt）
│   │   ├── skills/               # 项目级 skills
│   │   ├── hooks/                # 项目级 hooks
│   │   └── sessions/             # 该 agent 的所有 session
│   │       └── ses_xxx/
│   │           ├── session.json
│   │           ├── metadata.json
│   │           ├── attachments/
│   │           ├── checkpoints/
│   │           └── subagents/
│   ├── lucy/                     # 用户创建的其他 agent
│   └── ...
├── skills_market/                # 全局 skills 池
├── mcp_market/                   # 全局 MCP server 池
├── plugins/                      # 第三方插件
├── logs/                         # 日志
└── cache/                        # 缓存（可重建）
```

### 7.3 项目级 vs 全局

| 元素 | 全局位置 | 项目级位置 | 优先级 |
|---|---|---|---|
| `config.toml` | `~/.onion/config.toml` | `<project>/.onion/config.toml` | project > user |
| `AGENTS.md` | — | `<project>/AGENTS.md` | project 唯一 |
| `AGENTS.override.md` | — | `<project>/AGENTS.override.md` | 优先 AGENTS.md |
| `SOUL.md` | — | `<agent>/SOUL.md` | agent 唯一 |
| skills | `~/.onion/skills_market/` | `<agent>/skills/` | agent > global |
| rules | — | `<agent>/rules/` | agent 唯一 |
| hooks | `~/.onion/hooks/` | `<agent>/hooks/` | agent > global |

### 7.4 配置原则（重要：移除 .env）

**`config.toml` 是唯一配置入口**，明文包含 API_KEY。

原因：
- `.env` 在系统多个地方存在（shell、IDE、各 framework），反而降低安全性
- API_KEY 在 `config.toml` 中路径固定、权限可控制（`chmod 600`）
- 简化 UX（用户改一次就够）

```toml
# ~/.onion/config.toml

[model]
default = "gpt-4o"
providers = { openai = "...", anthropic = "..." }

[model.api_keys]
openai = "sk-xxx"        # 明文，文件权限 600
anthropic = "sk-ant-xxx"

[loop]
max_iterations = 100
compaction_threshold = 0.8

[plan]
enabled = true

[tools]
builtin = ["read_file", "write_file", "edit_file", "bash"]
mcp_servers = ["filesystem", "sequentialthinking"]
```

**敏感字段脱敏规则**（参考 `tool_standard.md` §8.3）：
- 写入 session.json 之前脱敏
- 写入 log 之前脱敏
- **不脱敏 LLM 调用**（LLM 需要看到真实内容工作）

### 7.5 压缩（3 层策略）

```python
# 1. 截断超大 tool result
MAX_TOOL_RESULT_CHARS = 100_000   # 100KB
TRUNCATE_HEAD_RATIO = 0.3

# 2. 总结老消息
SUMMARY_TARGET_TOKENS = 2000
KEEP_RECENT_MESSAGES = 20

# 3. 永远保护
PROTECTED_KINDS = {
    "system",
    "plan",                 # 关键！plan 不可压
    "first_user_message",   # 用户原始任务
}
```

**触发阈值**：80% of context window（与 Continue / Aider 一致）。

---

## 8. 内脑 / 外脑 / 小脑（保留并对齐）

> 原文的比喻很贴切，保留。但要明确每个脑区**对应到哪个 Onin Agent 模块**。

| 脑区 | 速度 | 功能 | 模型 | MCP | Onin Agent 模块 |
|---|---|---|---|---|---|
| 内脑 | 10 bit/s | 决策与逻辑 | LLM + Prompt | Prompt MCP（Rule / Soul） | `core/loop/agent_loop.py` |
| 外脑 | 500 MB/s | 感知与压缩 | VLM / ASR / 多模态 | Resource MCP（filesystem / web） | `infrastructure/mcp/` + `core/compactor/` |
| 小脑 | 500 MB/s | 执行 | LLM（轻量） | Tool MCP（bash / browser） | `infrastructure/tools/builtin/` + `tool_shell` |

**关键设计约束**：
- 每个脑区都是"模型 + MCP"组合——所以 **MCP Client 必做**
- 三个脑区对应三种数据流：感知-思考-执行、定时触发 FIFO、事件驱动
- session.json 是三个脑区的**共同上下文**（无论哪个脑区，都从 session 读历史、向 session 写结果）

---

## 9. 错误处理与重试（基于 other_common §3）

### 9.1 三类错误

```python
class ErrorCategory(str, Enum):
    RETRYABLE = "retryable"      # 网络 / 5xx / 429 → 指数回退
    FATAL = "fatal"              # 参数 / schema / 401 → fail-fast
    USER_DENIED = "user_denied"  # 用户拒绝 → 注入 feedback
```

### 9.2 重试矩阵

| 错误 | 是否重试 | 重试次数 | 退避 |
|---|:---:|---|---|
| 网络错误 / 5xx / 429 | ✅ | 3-5 | 指数回退 + jitter + 尊重 `Retry-After` |
| 401 / 403 | ❌ | 0 | fail-fast |
| 400（参数错） | ❌ | 0 | fail-fast |
| Tool 内部错误 | ✅ | 2-3 | 短间隔 |
| Tool not found | ❌ | 0 | 立即告诉 LLM |

### 9.3 指数回退

```python
class ExponentialBackoff:
    base = 0.5
    max_delay = 32.0
    max_retries = 5

    def get_delay(self, attempt):
        delay = min(self.base * (2 ** attempt), self.max_delay)
        return delay + random.uniform(0, delay * 0.1)
```

---

## 10. 所见即所得（核心可执行指标 ⭐⭐⭐）

> **这是本项目 PM 视角的"唯一指标"。**
> 每个 PR、每个模块、每条 PR 描述都必须能回答：跑哪个 demo 能看见效果？

### 10.1 三条总则

1. **每个 py 文件都能独立跑**——`python tools/demo_xxx.py` 直接看到效果
2. **每个模块都有 CLI 入口**——`--help` 必须可用
3. **每个 PR 必带 demo 输出**——CI 跑 demo，PR 描述附 demo 输出片段

### 10.2 12 个强制 demo CLI 脚本（沿用 quality_audit_v1.md §3）

每个脚本**独立可跑**、**所见即所得**、**跑通即 `=== DEMO PASSED ===`**。

| # | 脚本 | 演示内容 | 依赖 | 优先级 |
|---|---|---|---|:---:|
| 1 | `tools/demo_message.py` | 6 种 role 构造、JSONL 序列化、provider 转换 | 无 | P0 |
| 2 | `tools/demo_session.py` | session 创建 / append / 状态转换校验 / save+load | 无 | P0 |
| 3 | `tools/demo_loop.py` | AgentLoop 单步 + 多步（mock LLM） | mock | P0 |
| 4 | `tools/demo_compactor.py` | 压缩前后 session 大小对比 | mock | P1 |
| 5 | `tools/demo_plan.py` | update_plan 工具 + Markdown 渲染 + 5 态校验 | 无 | P1 |
| 6 | `tools/demo_tool_channel.py` | 3 级容错（json.loads → json_repair → jsonschema） | 无 | P0 |
| 7 | `tools/demo_skill.py` | skill 加载 / 激活 / 读 reference / 跑 script | skills_market | P1 |
| 8 | `tools/demo_mcp.py` | MCP server 配置加载 + 异步桥 | mcp_market | P0 |
| 9 | `tools/demo_doom_loop.py` | 连续 3 次同 tool 触发警告 + 5 次退路 | mock | P0 |
| 10 | `tools/demo_subagent.py` | fork 子 session + 3 道护栏 | mock | P2 |
| 11 | `tools/demo_workspace.py` | workspace 初始化 + agent CRUD + active session | 无 | P0 |
| 12 | `tools/demo_e2e.py` | 端到端（mock LLM，从 init 到 finish_run） | mock | P0 |

**统一 demo 模板**（每个 demo 必须长这样）：

```python
"""
<模块名> 演示 — <一句话描述>

Usage:
    python tools/demo_<name>.py
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from onion.core.<...>


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keep", action="store_true", help="保留 demo 产生的临时文件")
    args = parser.parse_args()
    try:
        demo()
        print("\n=== DEMO PASSED ===")
        return 0
    except Exception as e:
        print(f"\n=== DEMO FAILED: {e} ===", file=sys.stderr)
        raise


def demo() -> None:
    """演示逻辑，打印关键状态，最后断言结果。"""
    ...


if __name__ == "__main__":
    raise SystemExit(main())
```

### 10.3 PM 的 PR 验收三问

每次 PR / 每次任务完成，必须回答：

1. **这个动作在 `session.json` 里新增了哪条记录？**（哪个 role？哪个 state？）
2. **这个动作有对应的 `tools/demo_xxx.py` 吗？**（不新加 demo 不准合入）
3. **跑完 demo 后，我能"看见"什么？**（贴 demo 输出片段到 PR 描述）

### 10.4 demo 与真 LLM 的隔离原则

- **demo 默认 mock LLM**（CI 跑得起来、不烧钱）
- 真 LLM 调用通过环境变量 `ONION_LIVE=1` 启用
- demo 不依赖外网（除非 demo 8 mcp / demo 12 e2e 显式声明）

---

## 11. MVP 范围（PM 视角的"砍掉什么"决策）

### P0（必须做，不做不准发版）

- session.json 6 role 状态机 + 落盘 + 可见性矩阵
- File Backend 最小集（`~/.onion/` + `config.toml` + agent/sessions）
- Agent Loop 双层 while + 6 显式 exit state
- OpenAI FC 主路径 + Cline XML 降级
- 3 级容错 + Doom Loop
- 内置工具：read_file / write_file / edit_file / bash
- MCP Client（stdio / SSE / Streamable HTTP）
- Agent Skills Client（渐进式披露 L1/L2/L3）
- `onion init`（workspace 引导 + 配置大模型 + 创建第一个 agent）
- `onion run`（主 CLI）
- 6 个 demo CLI（demo 1/2/3/6/8/11）

### P1（强烈推荐，进 v1.0 之前做）

- Plan 看板（`update_plan` 工具 + 5 态）
- 流式输出
- 压缩（80% 触发 + 保护 plan）
- Resume 协议（checkpoint + restore）
- 错误处理 + 指数回退
- 进度展示（iteration / token / cost / plan 实时）
- 4 个 demo CLI（demo 4/5/7/9/12）

### P2（v2+）

- Sub-agent（深度 ≤ 3，禁用部分工具）
- 长期 memory（vector store）
- OS 级沙箱（Landlock / Seatbelt / bubblewrap）
- OTel 兼容 trace
- QT 桌面客户端
- IM bridge（飞书 / 微信 / Telegram）
- Provider failover（多 provider 热切换）
- 2 个 demo CLI（demo 10）

### 砍掉清单（PM 拍板不做）

- ❌ ReAct 文本格式工具调用（已过时）
- ❌ 工作流/DAG 编排（不是 ReAct agent 的本职）
- ❌ 纯 RAG 框架（已不归本项目）
- ❌ Plan 独立数据库表（plan 就是 session.json 里的一种 message）
- ❌ per-message state mutation（破坏 prompt cache）
- ❌ 工具列表塞进 system prompt（注意力分散）
- ❌ .env 配置文件（统一到 config.toml）
- ❌ `max_iterations` 默认值 < 25（退化为单步）

---

## 12. 反模式与红线（PM 视角的"不能做"）

| # | 红线 | 触发后果 | 来自 |
|---|---|---|---|
| 1 | 工具列表塞进 system prompt | 准确率下降 | 18/20 共识 |
| 2 | 用 `ast.literal_eval` 解析 LLM 输出 | 慢、无法处理复杂 JSON | superagi 教训 |
| 3 | `max_iterations` 默认 < 25 | 退化为单步 agent | autogen 0.4+ 教训 |
| 4 | 巨无霸单文件（>1000 行） | 难维护、难测试 | roo-code Task.ts 4619 行 |
| 5 | per-message state mutation | 破坏 prompt cache | hermes-agent 哲学 |
| 6 | 任何 py 文件不能独立跑 CLI | "所见即所得" 失败 | PM 本人红线 |
| 7 | session.json 不原子写 | 丢消息 | 工业级基线 |
| 8 | 工具执行不捕获异常 | loop 崩溃 | opencode / cline 共识 |
| 9 | `tool_choice="required"` 默认 | 诱导过度调用 | tool_accuracy.md §六 |
| 10 | plan 在压缩时被丢 | 任务进度丢失 | opencode 教训 |
| 11 | config 走 .env 拆出去 | 安全 + UX 双输 | PM 本人决定 |
| 12 | Doom Loop 不检测 | 真实生产死循环 | opencode 必做 |

---

## 13. 验收标准（PM 视角）

### 13.1 每次发版前必过

- [ ] 12 个 demo CLI 全过（`python tools/demo_*.py`，每个打印 `=== DEMO PASSED ===`）
- [ ] `tests/run_all.py` 全绿
- [ ] 至少 1 个 E2E demo（demo 12）跑通从 init 到 finish_run
- [ ] 没有 P0 红线违规
- [ ] README 演示 GIF 或动图更新（让用户能"看见"效果）

### 13.2 每次 PR 必过

- [ ] PR 描述回答 10.3 节三问
- [ ] 新增/修改的模块有对应 demo CLI 更新
- [ ] 没有 P0 红线违规
- [ ] CI 全绿

### 13.3 每个季度复盘

- [ ] 复盘 top 20 开源智能体的新进展
- [ ] 检查 12 个 demo 是否还能跑
- [ ] 检查 P0/P1/P2 范围是否调整
- [ ] 重大版本升级前更新本定版

---

## 14. 持续优化机制

- **每周**：检查 12 个 demo 是否有失败
- **每月**：检查 quality_audit 评分是否下降
- **每季度**：复盘 top 20 智能体
- **每年**：重写本定版（如有重大架构调整）

---

## 附录 A：本定版的核心约束（PM 速记卡）

```
┌──────────────────────────────────────────────────────────────┐
│                                                              │
│  session.json 是唯一状态机                                    │
│  ├── 3 个 state: openai / tool / loop                        │
│  ├── 4 个 LLM 可见 role: system / user / assistant / tool   │
│  └── N 个 LLM 不可见 role: 用于诊断/调试/留痕                │
│                                                              │
│  工具调用：主路径 FC + 降级 XML                              │
│  终止信号：主路径空 tool_calls / 降级 agent_loop_finish     │
│  容错：3 级 + Doom Loop                                      │
│                                                              │
│  Loop：双层 while + 6 显式 exit state + 软收尾               │
│  Plan：5 态 + at most one in_progress + 压缩保护              │
│  File：~/.onion/ + config.toml 明文 + session append-only    │
│                                                              │
│  所见即所得：12 个 demo CLI + 每次 PR 必跑 + 每次 PR 必答三问 │
│                                                              │
│  唯一不允许：.env / 巨无霸文件 / 工具塞 system / mutation    │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

---

## 附录 B：与现有 demo 代码的对应关系

| demo 文件 | 复用现有 demo | 改造点 |
|---|---|---|
| `tools/demo_message.py` | 无 | 从 0 写 |
| `tools/demo_session.py` | 无 | 从 0 写 |
| `tools/demo_loop.py` | `harness/demo/agent_client.py` | 抽离 FastAPI/uvicorn，纯 loop 逻辑 |
| `tools/demo_compactor.py` | 无 | 从 0 写 |
| `tools/demo_plan.py` | 无 | 从 0 写 |
| `tools/demo_tool_channel.py` | `harness/demo/agent_client.py` XML 解析部分 | 抽出 3 级容错 |
| `tools/demo_skill.py` | `harness/demo/agent_skills_client.py` | 复用 ProgressiveDisclosureEngine |
| `tools/demo_mcp.py` | `harness/demo/mcp_client.py` | 复用 MCPClient |
| `tools/demo_doom_loop.py` | `harness/demo/agent_client.py` LoopDetectionTracker | 抽出独立 demo |
| `tools/demo_subagent.py` | `harness/demo/deep_agent.py` 概念 | 从 0 写 |
| `tools/demo_workspace.py` | `harness/demo/agent_client.py` 初始化逻辑 | 抽出 init 流程 |
| `tools/demo_e2e.py` | 综合 | 串起所有模块 |

---

**Onion Agent 产品经理定版（v_final）完。**

本文件是后续所有 `harness/SRS/`、`src/`、`tests/`、`doc/` 变更的**唯一总依据**。任何与之冲突的设计决策，要么更新本文件，要么写明偏离理由。
