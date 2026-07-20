# Claude Code — 工具调用（Tool Channel）调研报告

## 0. 智能体一句话定位

Anthropic 官方终端编码 Agent，绑定 Claude 模型生态，靠 **30+ 官方 plugin + 12 种 hook 事件 + Agent Skills 渐进式披露 + MCP 协议** 构建了"可插拔的工具通道"——这是本报告的核心差异化。

## 1. 调研依据

- 源码路径：`C:\workspace\github\onionagent\harness\01_market_research\clone\claude-code\`
- 关键文件：
  - `plugins/README.md` — 14 个官方 plugin 目录索引
  - `plugins/plugin-dev/skills/plugin-structure/SKILL.md` — plugin 目录结构与自动发现规则
  - `plugins/plugin-dev/skills/plugin-structure/references/manifest-reference.md` — `plugin.json` 完整字段
  - `plugins/plugin-dev/skills/hook-development/SKILL.md` — hook 事件清单与输出协议
  - `plugins/plugin-dev/skills/hook-development/scripts/validate-hook-schema.sh:41` — 9 个标准 hook 事件硬编码列表
  - `plugins/plugin-dev/skills/mcp-integration/SKILL.md` — MCP 4 种 transport + 工具命名规范
  - `plugins/hookify/hooks/hooks.json` — 4 种 hook 事件实战配置
  - `plugins/hookify/core/config_loader.py` — 动态扫描 `.claude/hookify.*.local.md` 的核心 loader
  - `plugins/security-guidance/hooks/hooks.json` — 7 个 hook 事件实战（含 `if` / `asyncRewake` 高级特性）
  - `plugins/feature-dev/agents/code-architect.md:4` — Agent 用 `tools:` 字段声明内置工具
  - `plugins/feature-dev/commands/feature-dev.md` — 7 阶段 ReAct 工作流范本
  - `examples/hooks/bash_command_validator_example.py` — PreToolUse 钩子标准实现（JSON stdin / exit code）
  - `examples/settings/settings-{lax,strict,bash-sandbox}.json` — 3 档 settings.json 范例
  - `examples/mdm/managed-settings.json` — MDM 企业级托管配置
  - `CHANGELOG.md` — 50+ 条 tool/hook/MCP 演进记录（含 input_json_delta、tool_use_id 等协议细节）
- 文档/README：`README.md`、`plugins/README.md`、`.claude-plugin/marketplace.json`

> ⚠️ **重要事实**：本仓库（`anthropics/claude-code`）是 **plugin 市场 + 范例代码** 仓库，**不是** 主 CLI 源码（CLI 主仓是闭源）。所以 Q3 流式解析、Q4 协议层（Anthropic `tool_use` 块、`input_json_delta` 等）的**实现细节不在本仓库内**——这些证据从 CHANGELOG、agent-sdk-dev 文档、hook 协议反推。

## 2. 五个核心问题的回答

### Q1. 工具来源

#### 内置工具（通过 Agent 的 `tools:` 字段反推）

Claude Code 没有公开的工具清单文件，但从各 plugin 的 agent frontmatter 中提取到的内置工具名（agent 级别 `tools:` 字段就是该 agent 允许调用的内置工具白名单）：

| 工具名 | 出现位置 | 推断用途 |
|-------|---------|--------|
| `Read` | `feature-dev/agents/code-architect.md:4`、`pr-review-toolkit` 多处 | 读文件 |
| `Write` | `commit-commands/commands/commit.md`、`security-guidance` 引用 | 写文件 |
| `Edit` / `MultiEdit` | `security-guidance/hooks/hooks.json:14` 显式匹配 | 单点/多点编辑 |
| `Bash` | `ralph-wiggum/commands/ralph-loop.md:4`、`commit-commands` 多处 | 本地命令执行 |
| `Grep` / `Glob` | `feature-dev/agents/code-architect.md:4`、`hookify/agents/conversation-analyzer.md:6` | 内容/路径搜索 |
| `LS` | `feature-dev/agents/code-architect.md:4` | 列目录 |
| `NotebookRead` / `NotebookEdit` | `code-architect.md:4`、`security-guidance/hooks/hooks.json` | Jupyter notebook |
| `WebFetch` / `WebSearch` | `code-architect.md:4`、`feature-dev/commands/feature-dev.md` | 网络 |
| `TodoWrite` | `code-architect.md:4`、`feature-dev.md` 多处 | 任务清单管理 |
| `BashOutput` / `KillShell` | `code-architect.md:4` | 后台进程管理 |
| `Task` | `pr-review-toolkit/commands/review-pr.md:4` | 派发子 agent（多 Agent 并行核心） |
| `AskUserQuestion` | `plugin-dev/skills/plugin-settings/examples/create-settings-command.md:3` | 反问用户 |

**证据**：`plugins/feature-dev/agents/code-architect.md:1-6`
```yaml
---
name: code-architect
description: ...
tools: Glob, Grep, LS, Read, NotebookRead, WebFetch, TodoWrite, WebSearch, KillShell, BashOutput
model: sonnet
color: green
---
```

格式两种：JSON 数组（`tools: ["Read", "Grep"]`）或 YAML 标量逗号分隔（`tools: Glob, Grep, ...`）。

#### MCP 支持 ✅

- **配置位置**：
  1. 用户级：`~/.claude.json`（main 仓库证据，CHANGELOG 多条引用）
  2. 项目级：`<repo>/.mcp.json`（CHANGELOG 反复出现，例如 `:219`、`:426`、`:1010`、`:1373`、`:4999`）
  3. Plugin 级：plugin 根目录的 `.mcp.json` 或内联到 `.claude-plugin/plugin.json` 的 `mcpServers` 字段（`plugins/plugin-dev/skills/mcp-integration/SKILL.md:44-58`）
  4. 企业级：`managed-mcp.json`（CHANGELOG:1124）
- **4 种 transport**（`mcp-integration/SKILL.md:65-110`）：
  - `stdio`（本地进程，默认）
  - `sse`（Server-Sent Events，OAuth）
  - `http`（REST，token）
  - `ws`（WebSocket，实时）
- **工具命名约定**（`mcp-integration/SKILL.md:130`）：`mcp__plugin_<plugin-name>_<server-name>__<tool-name>`（如 `mcp__plugin_asana_asana__asana_create_task`）
- **MCP 信任门控**：CHANGELOG:426 提到"`.mcp.json` 服务器从 self-approved 状态改为 `⏸ Pending approval`"——首启动时按服务器粒度弹信任窗

#### Agent Skills 支持 ✅

- **目录位置**：每个 plugin 自己的 `skills/<skill-name>/SKILL.md`（**不是** 在 `<repo>/.skills/` 或 `~/.skills/`）
- **SKILL.md 格式**（YAML frontmatter + Markdown body）：
  - `name` / `description` / `version` 三个标准字段
  - `description` 决定 **Claude 自动激活时机**（`plugin-dev/skills/plugin-structure/SKILL.md` 中"Claude Code autonomously activates skills based on task context matching the description"）
- **渐进式披露**：skill 子目录可放 `scripts/` `references/` `examples/` 等子文件，main 上下文**只加载 SKILL.md**；LLM 按需 `Read` 引用文件
- **官方范例**（已实现 4 个 skill）：
  - `frontend-design/skills/frontend-design/SKILL.md`（1.1 版本，含 LICENSE）
  - `claude-opus-4-5-migration/skills/...`
  - `hookify/skills/writing-rules/SKILL.md`
  - `plugin-dev/skills/{agent-development,command-development,hook-development,mcp-integration,plugin-settings,plugin-structure,skill-development}/`（7 个开发类 skill）
- **动态刷新**：CHANGELOG:1084 提到 `SessionStart` 钩子可返回 `reloadSkills: true` 重扫 skill 目录

#### 其他工具类型

- **Plugin / Marketplace 系统**（见 Q5）
- **Hook 体系**（事件驱动，可拦截 / 修改 / 重写工具调用，见 Q3）
- **Sub-Agent 并行**：`Task` 工具 + `pr-review-toolkit/agents/` 6 个并行 reviewer
- **Plan/Act 双模式**（README 隐含，CHANGELOG 多次出现 `plan` / `build` agent）

### Q2. 工具列表的生成、传递、格式

#### 生成方式

工具列表由 **三层叠加** 动态生成（`plugin-dev/skills/plugin-structure/SKILL.md:55-89`）：

1. **Agent 内置**（硬编码白名单）：每个 agent 的 `tools:` 字段是该 agent 的子集
2. **Plugin 注入**（`.claude-plugin/plugin.json` 显式声明或默认扫描）：
   - `commands: ./custom-commands`（补充默认 `commands/`）
   - `agents: [./agents, ./specialized-agents]`（支持多路径）
   - `hooks: ./config/hooks.json`（指向 hooks.json）
   - `mcpServers: ./.mcp.json` 或内联
3. **项目/用户级**（运行时累加）：
   - `<repo>/.mcp.json` → MCP 工具
   - `<repo>/.claude/hookify.*.local.md` → 用户动态 hook 规则
   - `~/.claude/settings.json` → permission allow/deny/ask 列表

#### 传递方式

**Anthropic `messages` API 协议**（`tools` 参数 + `tool_use` 块）。证据：

- 仓库名 `anthropics/claude-code` + CHANGELOG 多处引用 `tool_use_id`（`:651`、`:662`、`:2079`、`:2086`）—— 这是 Anthropic 协议独有字段（OpenAI 用 `tool_call_id`）
- `agent-sdk-dev/commands/new-sdk-app.md:18` 引用官方 Python/TypeScript SDK 文档
- `agent-sdk-dev/agents/agent-sdk-verifier-py.md` 提到"Streaming vs Single mode"—— 即 Anthropic `stream=True` 协议
- **CHANGELOG 隐含流式**：`input_json_delta` 是 Anthropic 流式协议字段名（虽未在本仓库直接出现，但 Anthropic SDK 标准字段）

#### 格式：JSON

Anthropic 原生 `tools` 数组（不是 OpenAI `chat.completions` 的 `tools`）。简化示意（基于 `feature-dev/agents/code-architect.md` 的 `tools:` 字段推导）：

```json
{
  "tools": [
    {"name": "Read", "description": "...", "input_schema": {...}},
    {"name": "Bash",  "description": "...", "input_schema": {"command": "string"}},
    {"name": "mcp__plugin_asana_asana__asana_create_task", "description": "...", "input_schema": {...}}
  ]
}
```

MCP 工具完整名示例（`mcp-integration/SKILL.md:129-133`）：
```
mcp__plugin_asana_asana__asana_create_task
        ^^^^^^  ^^^^^^  ^^^^^^^^^^^^^^^
        plugin  server  tool-name
```

#### prompt-as-tool？❌ 否

- 命令（commands）通过 YAML frontmatter + Markdown body 描述，但**调用方式仍是 function calling**，不是 prompt-as-tool
- 例外：sub-agent 通过 markdown prompt 描述其角色（`code-architect.md`），但 agent 本身仍是 function calling 模式
- 唯一"prompt-as-hook"特例：`hooks.json` 支持 `type: "prompt"` 的钩子（hookify 示例），那是 hook 不是 tool

#### 动态刷新 ✅

- Plugin 启动后 `SessionStart` 可触发 `reloadSkills: true`（CHANGELOG:1084）
- `/mcp` reconnect 可热加载 `.mcp.json`（CHANGELOG:1418）
- `hookify.*.local.md` 是**实时扫描**：`hookify/core/config_loader.py:159` 用 `glob.glob(pattern)` 每次工具调用前重扫

### Q3. 工具调用指令的解析、错误修复、准确性

> ⚠️ **Q3 限制**：CLI 主循环 + 流式解析代码在闭源主仓，**本仓库只见 hook 协议层**。

#### 解析方式

- **Anthropic 原生流式**（推断）：LLM 发出 `tool_use` 块，参数 JSON 通过流式 `input_json_delta` 增量累积
- **Hook 协议层（实测）**：`PreToolUse` 钩子通过 **stdin 接收 JSON**，格式（`bash_command_validator_example.py:62-68`）：
  ```python
  input_data = json.load(sys.stdin)
  tool_name = input_data.get("tool_name", "")
  tool_input = input_data.get("tool_input", {})
  command = tool_input.get("command", "")
  ```
- **命令级白名单（更细粒度）**：`allowed-tools` 支持 `Bash(git add:*)` / `Bash(test -f .claude/ralph-loop.local.md:*)` 这种**带 glob 模式的工具名 + 参数前缀**双重白名单（`ralph-wiggum/commands/ralph-loop.md:4`、`cancel-ralph.md:3`）

#### 错误修复 / 阻断机制

- **Exit code 协议**（`hook-development/SKILL.md:265-268`）：
  - `0` — 成功（stdout 显示在 transcript）
  - `2` — **Blocking error**（stderr 内容**喂回给 Claude** 当作"工具错误提示"，触发自动 retry）
  - 其他 — 非阻塞错误
- **Decision 输出**（`hook-development/SKILL.md:189-194`）：
  ```json
  {"decision": "approve|block", "reason": "...", "systemMessage": "..."}
  ```
- **PreToolUse 的 `permissionDecision`**（CHANGELOG:58、:2147）：`"allow" | "ask" | "deny"`，**hook 的 `ask` 优先级高于 settings.json 的 `deny`**（floor 语义）
- **PostToolUse 改写**（CHANGELOG:1714）：`hookSpecificOutput.updatedToolOutput` **替换**整个工具输出（不仅 MCP，所有工具）
- **PreCompact 阻断压缩**（CHANGELOG:2087）：钩子退出码 2 或返回 `{"decision":"block"}` 可阻止 context 压缩
- **asyncRewake 异步唤醒**（`security-guidance/hooks/hooks.json:24-27`）：Stop 钩子后台跑 LLM review，跑完用 `rewakeMessage` 把反馈**自动喂回 Claude**——这是"Ralph Wiggum 自循环"和"security-guidance"的核心机制
- **Sentinel 防重入**（`security-guidance/hooks/security_reminder_hook.py:651-666`）：`.git/sg-hook-once-<tool_use_id>` 每个 tool_use_id 只触发一次，避免多 spawn 竞态

#### 准确性保证

- **Agent 级白名单**（`tools:` 字段）：每个 sub-agent 只能调用其 `tools:` 列表内的工具
- **命令级 `allowed-tools` glob 模式**（如 `Bash(git add:*)`）：参数前缀匹配防止命令注入
- **PreToolUse `permissionDecision`**：弹窗询问 + 决策持久化到 settings.json
- **Pattern 校验**（`hookify` plugin）：用户写 `.local.md` 规则，正则匹配 `command` / `new_text` / `file_path` 等字段
- **多维 confidence 评分**（`code-review/agents/code-reviewer.md`）：子 agent 自评 0-100 置信度，**只报 ≥80 分的问题**——这是 review 任务的精度保证
- **重试上限**：未在源码中明文规定；exit code 2 触发自动 retry，依赖 LLM 自身推理终止

### Q4. 工具执行结果回传

> ⚠️ **Q4 限制**：CLI 主循环不在本仓库。从 CHANGELOG、hook 协议反推。

#### 回传方式

- **Anthropic 协议**：`messages` 数组中的 **`tool_result` 块**，与上一轮的 `tool_use` 块通过 `tool_use_id` 配对
- **证据**：CHANGELOG:651-666 显式提到 "SAME `tool_use_id`"
- **结构**（推断）：`{"type": "tool_result", "tool_use_id": "...", "content": "..."}`

#### 格式

- 钩子看到的 `tool_input` 是**结构化 JSON**（hook bash 校验器可直接 `.get("command")`）
- 用户视角的结果是**字符串**（来自 stdout/stderr 拼装）
- **结构化改写机制**（CHANGELOG:1714）：PostToolUse 钩子可返回 `updatedToolOutput` **整体替换**回传内容——这是结构化扩展点

#### 协议

- **Anthropic `messages` 协议为主**（绑定 Claude 模型）
- **Agent SDK 暴露多 Provider 抽象**（`agent-sdk-dev/commands/new-sdk-app.md:18` 引用 TypeScript/Python SDK 文档），但**官方 SDK 也是 Anthropic 协议优先**
- **不支持 OpenAI 协议直接对接**（与 opencode 的"Provider-agnostic"相反）

#### 大结果处理

- **PostToolUse 截断**（`hook-development/SKILL.md` 提到"out of context bounds"机制）；CHANGELOG:1187 "bounds total bytes downstream so this can't blow context"——这是经验证的"大结果硬截断"
- **MCP 图像/MEDIA 转换**：本仓库未直接出现（属于 Hermes / OpenClaw 生态特性）
- **Exit code 2 反馈**：工具报错时，stderr 自动作为"工具错误消息"喂回给 Claude，触发自动 retry / plan-then-act

### Q5. File Backend 是否为工具调用做了适配

**有，且是 Claude Code 工具通道的核心物理层**。

#### 工具配置目录/文件清单

| 路径 | 作用 | 加载位置 |
|------|------|--------|
| `~/.claude/`（用户级） | 用户全局配置 + skills/agents/commands | `CLAUDE_CONFIG_DIR` env 可重定向 |
| `<repo>/.claude/`（项目级） | 项目级 `settings.json` / `settings.local.json` / 命令 / hook 规则 | 启动时 cwd 向上扫描 |
| `<repo>/.mcp.json` | 项目级 MCP Server 注册 | CHANGELOG 多处 |
| `~/.claude/hookify.*.local.md` | **用户动态 hook 规则** | `hookify/core/config_loader.py:158-160` 实时 glob |
| `<plugin-root>/.claude-plugin/plugin.json` | **plugin 清单** | `plugin-structure/SKILL.md:36-89` |
| `<plugin-root>/.claude-plugin/marketplace.json` | **marketplace 索引** | `marketplace.json`（本仓库根 `.claude-plugin/marketplace.json`） |
| `<plugin-root>/.mcp.json` | **plugin 私有 MCP** | `mcp-integration/SKILL.md:18-26` |
| `<plugin-root>/hooks/hooks.json` | **plugin 私有 hook 事件** | `hookify/hooks/hooks.json` 范例 |
| `<plugin-root>/commands/*.md` | **slash 命令** | 自动发现 |
| `<plugin-root>/agents/*.md` | **sub-agent 定义** | 自动发现 |
| `<plugin-root>/skills/<name>/SKILL.md` | **Agent Skill** | 自动发现 + description 触发激活 |
| `<plugin-root>/${CLAUDE_PLUGIN_ROOT}/...` | **plugin 内部路径** | `${CLAUDE_PLUGIN_ROOT}` 模板变量自动展开 |

#### 加载代码证据

- **Hook 规则动态加载**（`plugins/hookify/core/config_loader.py:157-184`）：
  ```python
  def load_rules(event: Optional[str] = None) -> List[Rule]:
      pattern = os.path.join('.claude', 'hookify.*.local.md')
      files = glob.glob(pattern)  # ← 每次工具调用前重扫
      for file_path in files:
          rule = load_rule_file(file_path)
          ...
  ```
  → **关键洞见**：Claude Code 的用户级 hook 规则是**纯文件系统 + YAML frontmatter**——不写代码也能扩展工具通道（这是 Onion 可学的"DSL-as-config"范式）。

- **Settings 5 层合并**（README + 范例文件）：`managed > CLI > user > project > local`（`settings-lax.json` 标注 "may be applied at any level of the [settings hierarchy](https://code.claude.com/docs/en/settings#settings-files)"）
- **Plugin manifest 自动发现**（`plugin-structure/SKILL.md:55-89`）：默认扫 `commands/` `agents/` `skills/` `hooks/`，外加 manifest 字段可加自定义路径
- **Marketplace 加载**（`.claude-plugin/marketplace.json`）：列 14 个 plugin，每个 plugin 有 `source: ./plugins/<name>` 指明物理路径

#### 全局 vs 项目级 vs 两者

**两者都有，且 plugin 体系是第三层叠加**：

1. 用户全局：`~/.claude/settings.json`、`~/.claude/hookify.*.local.md`
2. 项目级：`<repo>/.claude/settings.json`、`<repo>/.claude/settings.local.json`、`<repo>/.mcp.json`
3. Plugin 级：每个 plugin 自带 `commands/` `agents/` `skills/` `hooks/` `.mcp.json`

#### 与 `standard/file_backend.md` 对照

| standard 条款 | Claude Code 行为 | 一致性 |
|--------------|----------------|--------|
| §1.1 用户属主目录 + env 覆盖 | `~/.claude/` + `CLAUDE_CONFIG_DIR` env | ✅ 完全一致 |
| §1.3 AGENTS.md 向上扫描到 .git | `CLAUDE.md` 向上扫描（README + CHANGELOG 引用）| ✅ 一致 |
| §1.4 secrets 0o600 | `auth.json` 0o600（CHANGELOG + file_backend.md 记录） | ✅ 一致 |
| §3.1 严格三层分离（全局/项目/临时） | `~/.claude/` + `<repo>/.claude/` + `~/.claude/tasks/<id>/` | ✅ 一致 |
| §3.4 强结构化 | plugin 目录极强结构化（commands/agents/skills/hooks/.mcp.json）| ✅ 比 file_backend 标准还强 |
| §3.8 Bootstrap 种子文件 | 无自动 seed，但 `<repo>/.claude/` + `CLAUDE.md` 是隐式 bootstrap | ⚠️ 半一致 |
| §5.1 配置文件 JSON | `settings.json` / `plugin.json` / `.mcp.json` 全是 JSON | ✅ 一致 |
| §5.4 LLM 不可读凭证白名单 | 显式 `allowed-tools` 字段做工具级白名单 | ✅ 一致（工具级更细） |
| §10.7 plugin + hook 系统 | 14 plugin + 12 hook 事件，**行业最完整** | ✅ 远超标准（参考） |
| §10.8 MCP 协议支持 | `.mcp.json`（用户级 / 项目级 / plugin 级 / managed 四层）| ✅ 最完整实现 |

## 3. 关键代码片段

### 片段 1：Hook 协议层（PreToolUse 完整范例）

`examples/hooks/bash_command_validator_example.py:60-79`：
```python
def main():
    try:
        input_data = json.load(sys.stdin)        # ← 钩子从 stdin 收 JSON
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON input: {e}", file=sys.stderr)
        sys.exit(1)

    tool_name = input_data.get("tool_name", "")
    if tool_name != "Bash":
        sys.exit(0)                              # ← 0 = 放行
    tool_input = input_data.get("tool_input", {})
    command = tool_input.get("command", "")
    if not command:
        sys.exit(0)

    issues = _validate_command(command)
    if issues:
        for message in issues:
            print(f"• {message}", file=sys.stderr)
        sys.exit(2)                              # ← 2 = 阻断 + 把 stderr 喂回给 Claude
```

### 片段 2：Plugin manifest + MCP 集成

`plugins/plugin-dev/skills/mcp-integration/SKILL.md:18-26`：
```json
{
  "database-tools": {
    "command": "${CLAUDE_PLUGIN_ROOT}/servers/db-server",
    "args": ["--config", "${CLAUDE_PLUGIN_ROOT}/config.json"],
    "env": {"DB_URL": "${DB_URL}"}
  }
}
```
工具命名规范（`:129-133`）：`mcp__plugin_<plugin-name>_<server-name>__<tool-name>`

### 片段 3：hook 事件清单（9 种标准事件）

`plugins/plugin-dev/skills/hook-development/scripts/validate-hook-schema.sh:41`：
```bash
VALID_EVENTS=("PreToolUse" "PostToolUse" "UserPromptSubmit" "Stop" "SubagentStop"
              "SessionStart" "SessionEnd" "PreCompact" "Notification")
```
+ CHANGELOG 提到另有 `Setup` / `SubagentStart` / `PostToolUseFailure` / `InstructionsLoaded` / `MessageDisplay`（共 12+）

### 片段 4：Agent 内置工具声明

`plugins/feature-dev/agents/code-architect.md:1-6`：
```yaml
---
name: code-architect
description: Designs feature architectures...
tools: Glob, Grep, LS, Read, NotebookRead, WebFetch, TodoWrite, WebSearch, KillShell, BashOutput
model: sonnet
color: green
---
```

### 片段 5：Hookify 规则动态加载（用户级 hook 范式）

`plugins/hookify/core/config_loader.py:157-168`：
```python
def load_rules(event: Optional[str] = None) -> List[Rule]:
    rules = []
    pattern = os.path.join('.claude', 'hookify.*.local.md')
    files = glob.glob(pattern)              # ← 每次工具调用前重扫
    for file_path in files:
        try:
            rule = load_rule_file(file_path)
            ...
```

## 4. 与 Onion Agent 设计的关联

1. **学 Claude Code 的 plugin 体系作为 Onion 的 P2 扩展点**：`.claude-plugin/plugin.json` + `commands/agents/skills/hooks/.mcp.json` 的强结构化目录是**最成熟的"可插拔工具通道"范本**。Onion 建议 `~/.onion/plugins/<name>/` 复用同结构。

2. **学 hookify 范式做 Onion 的"用户可配置 hook"**：`hookify.*.local.md` 这种 **YAML frontmatter + Markdown body + 正则模式** 的纯配置文件，可让用户**不写 Python** 就能扩展工具通道——这是 80% 用户的痛点解药。Onion 可做 `<repo>/.onion/hookify.*.local.md` 复用相同 loader。

3. **学 `allowed-tools` glob 模式做 Onion 的"细粒度权限"**：`Bash(git add:*)` 这种**工具名 + 参数前缀**双重白名单，比 settings.json 的 `allow/deny` 三档精细一个数量级。Onion 的 `read_file` / `write_file` 工具建议支持 `Bash(git:*)` / `Read(/path/*)` 模式。

4. **学 hook 12 事件做 Onion 的"事件驱动拦截"**：尤其是 `PreToolUse.permissionDecision: "ask" | "allow" | "deny"` 三态决策 + `PostToolUse.updatedToolOutput` 改写——这两个机制让 Onion 的工具层成为**可观察可修改的管道**，而不是"LLM 一调就走"的暗箱。

5. **避免 Claude Code 的"绑定 Claude 协议"反模式**：Claude Code 用 Anthropic 协议 + Claude-only 模型，Onion 是信创合规 + Provider-agnostic，应**通过抽象 Protocol 层隔离**。可学 opencode 的"Provider 热插拔"模式，但保留 Claude Code 的 plugin 目录范式。

## 5. 不确定 / 未找到

- **CLI 主循环源码**：CLI 主仓在闭源 Anthropic 内部，**流式解析（`input_json_delta` 增量累积）、工具调用 retry 次数上限、tool_result 结构**等无法在本仓库直接读源码确认。本报告从 CHANGELOG + hook 协议反推。
- **官方 plugin 数量**：本仓库 `marketplace.json` 列了 **14 个 plugin**（不是 30+）。README 提到"30+ 内部 + 10+ 外部插件"——30+ 部分在闭源内部仓库。
- **工具指令解析的内部实现**：`input_json_delta` 在 CHANGELOG 全文未直接出现（CHANGELOG 引用 `tool_use_id`、但未引用 `input_json_delta`），是 Anthropic 协议默认字段的推断。建议核实官方 SDK 文档。
- **大结果 MEDIA 引用机制**：本仓库未见图像/二进制大结果的 MEDIA 引用代码（与 Hermes / OpenClaw 不同）。
- **Plugin 启动时的工具列表缓存策略**：`reloadSkills: true` 显式重扫，但默认是否缓存、缓存 TTL、并发安全**未明文规定**。
- **重试机制上限**：源码未显式定义"工具调用失败后 LLM 最多 retry 几次"——依赖 Anthropic SDK 默认值或 LLM 自身推理。
