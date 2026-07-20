# Claude Code — 工作区(File Backend)调研报告

> 调研对象: `anthropics/claude-code` 公开仓库(plugin marketplace + 官方插件集)
> 调研时间: 2026-07-17
> 调研人: general worker(子代理)
> 源码位置: `C:\workspace\github\onionagent\harness\01_market_research\clone\claude-code`(只读)

---

## 0. 智能体一句话定位

Anthropic 官方终端编码 Agent,**CLAUDE.md 规则系统 + Hooks 自动化 + MCP 协议 + 子 Agent 并行** 的全平台(macOS/Linux/Windows)命令行 Agent,工作区遵循"项目级 `.claude/` + 用户级 `~/.claude/` + 企业级 `managed-settings`"三层叠加模型,所有"工作区"是文件系统(`.claude/`、rules、commands、agents、hooks、skills、plugins 全部落地为目录/文件),状态由 Claude Code 主进程解析、自动加载、自动合并。

---

## 1. 调研依据

### 1.1 源码性质澄清
`anthropics/claude-code` 仓库**不是** Claude Code 主二进制源码(主二进制是闭源 npm 包 `@anthropic-ai/claude-code`),而是:
- **官方插件市场清单** `.claude-plugin/marketplace.json`(13 个 plugin 全部列出)
- **13 个官方 plugin 完整实现**(每个 plugin 包含 commands、agents、hooks、skills 完整目录)
- **配置示例集** `examples/`(settings、hooks、MDM)
- **一份 454KB 的 CHANGELOG.md**(从 v1.0.4 至今约 5000 行版本历史)

通过这些公开资料,可以逆向得到 Claude Code 完整工作区设计:
- 目录布局(commands/agents/hooks/skills 各是什么)
- 加载机制(自动发现、路径解析、合并优先级)
- 配置文件 schema(settings.json、hooks.json、plugin.json)
- 钩子事件(PreToolUse/PostToolUse/SessionStart/Stop/UserPromptSubmit/SubagentStop/PreCompact/Notification/InstructionsLoaded/MessageDisplay)
- 环境变量注入(`$CLAUDE_PROJECT_DIR`、`$CLAUDE_PLUGIN_ROOT`、`$CLAUDE_ENV_FILE`、`$CLAUDE_SKILL_DIR`、`$CLAUDE_CONFIG_DIR`)

### 1.2 已读取的关键文件
- `README.md:1-72` — 定位 & 安装
- `CHANGELOG.md:1-5060` — 5000+ 行版本历史(精华)
- `.claude-plugin/marketplace.json:1-160` — 插件市场清单
- `.claude/commands/commit-push-pr.md`, `dedupe.md`, `triage-issue.md` — 项目级 slash command 范例
- `examples/settings/settings-lax.json`, `settings-strict.json`, `settings-bash-sandbox.json` — 三档权限配置
- `examples/mdm/managed-settings.json` + `macos/com.anthropic.claudecode.plist` + `windows/Set-ClaudeCodePolicy.ps1` — 企业级 managed settings
- `examples/hooks/bash_command_validator_example.py` — PreToolUse hook Python 范例
- `plugins/README.md:1-130` — 13 个 plugin 总览
- `plugins/plugin-dev/skills/plugin-structure/SKILL.md:1-150` — **目录结构与加载机制官方说明**
- `plugins/plugin-dev/skills/hook-development/SKILL.md:1-500` — **钩子事件与 schema 官方说明**
- `plugins/plugin-dev/skills/plugin-settings/SKILL.md:1-150` — `.claude/<plugin>.local.md` 模式
- `plugins/security-guidance/hooks/hooks.json:1-50` — 真实 hook 配置范例
- `plugins/feature-dev/agents/code-explorer.md`, `code-architect.md` — subagent frontmatter 范例
- `plugins/feature-dev/commands/feature-dev.md` — 命令 frontmatter 范例
- `plugins/ralph-wiggum/scripts/setup-ralph-loop.sh:1-200` — **真实状态文件 `.claude/ralph-loop.local.md` 写入逻辑**
- `plugins/ralph-wiggum/hooks/stop-hook.sh:1-200` — **真实 stop hook 读取状态文件并阻断 session 退出**
- `plugins/frontend-design/skills/frontend-design/SKILL.md:1-15` — Skill frontmatter 范例
- `plugins/claude-opus-4-5-migration/skills/claude-opus-4-5-migration/SKILL.md:1-15` — Skill with references 范例
- `.devcontainer/devcontainer.json:1-40` — 容器级 `CLAUDE_CONFIG_DIR` 注入

---

## 2. 三个核心问题的回答

### Q1. 工作区路径 — 跟随当前目录 + 三层叠加

**结论**: Claude Code 是**跟随当前目录**(进入项目目录就用它)的"项目根 + 用户主目录 + 企业策略"三层叠加架构,**没有写死 `~/.claude/`**,也**有自定义路径手段**(`CLAUDE_CONFIG_DIR` 环境变量覆盖)。

#### 1.1 三层路径来源(从高到低)

| 层级 | 路径 | 用途 | 关键证据 |
|---|---|---|---|
| **企业托管策略** | macOS: `com.anthropic.claudecode` plist(`/Library/Managed Preferences/...`)<br>Windows: `C:\Program Files\ClaudeCode\managed-settings.json` 或 `HKLM\SOFTWARE\Policies\ClaudeCode\Settings`<br>Linux: `/etc/claude-code/managed-settings.json`(推测) | IT 管理员统一下发,不可被用户覆盖 | `examples/mdm/README.md:21-24`<br>`examples/mdm/windows/Set-ClaudeCodePolicy.ps1:5-8`<br>`CHANGELOG.md:2824`(Windows path 迁移) |
| **用户级** | macOS/Linux: `~/.claude/`<br>Windows: `%USERPROFILE%\.claude\`<br>**可用 `CLAUDE_CONFIG_DIR` 环境变量覆盖** | 全局配置、主题、历史、API 凭据 | `CHANGELOG.md:160` `~/.claude/workflows/`<br>`CHANGELOG.md:4847` "Respect CLAUDE_CONFIG_DIR everywhere"<br>`.devcontainer/devcontainer.json:36-37` `CLAUDE_CONFIG_DIR=/home/node/.claude` |
| **项目级** | 当前工作目录(由用户 `cd` 决定),在 cwd 下查找:<br>• `CLAUDE.md`(项目根)<br>• 子目录中的 `CLAUDE.md`(递归注入)<br>• `.claude/`(项目级配置目录)<br>• `.mcp.json`(项目级 MCP)<br>• `.claude/rules/*.md`(条件规则) | 项目成员共享的规则、命令、代理、钩子 | `CHANGELOG.md:2400` "nested CLAUDE.md files being re-injected"<br>`CHANGELOG.md:3054` ".claude/rules/*.md files... nested CLAUDE.md files"<br>`CHANGELOG.md:2440` "`~/.claude/CLAUDE.md`" 也合法(可放用户主目录) |
| **CLI 标志覆盖** | `--settings <file>`, `--mcp-config <file>`, `--plugin-dir <path>`, `--add-dir <path>`, `--setting-sources user|project|local|...` | 临时覆盖、SDK 模式 | `CHANGELOG.md:1286`, `1292`, `1613`(`--plugin-dir` 支持 zip)<br>`CHANGELOG.md:3028` `--setting-sources user` |

#### 1.2 "工作区"语义
- **没有显式 `init` 命令**:`README.md:50` 写的是 "Navigate to your project directory and run `claude`" — 工作区就是 `pwd`,Claude Code 不做"工作区创建"动作。
- **隐式创建**: `.claude/`、`CLAUDE.md` 都是**按需创建**,由 Claude Code 写出的子目录(如 `.claude/ralph-loop.local.md` 由 `setup-ralph-loop.sh:108-120` 用 `mkdir -p .claude` 创建)说明**运行时第一次需要才建**。
- **CLAUDE.md 来源**:
  - 用户手动创建(最常见,committable,进入 git)
  - `/init` 内置命令(Changelog 提到 `/init` 是 bundled skill,见 `CHANGELOG.md:2057`,实际由模型"反推项目结构"生成)
  - `~/.claude/CLAUDE.md`(用户级规则,跨项目生效,见 `CHANGELOG.md:2440`)

#### 1.3 关键代码证据

```bash
# .claude/ 状态文件是 Claude Code 主进程+插件协作产生的真实产物
$plugins/ralph-wiggum/scripts/setup-ralph-loop.sh:108$
mkdir -p .claude
cat > .claude/ralph-loop.local.md <<EOF
---
active: true
iteration: 1
max_iterations: $MAX_ITERATIONS
completion_promise: $COMPLETION_PROMISE_YAML
started_at: "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
---
$PROMPT
EOF
```
**关键发现**:`.claude/` 不一定代表"配置目录",它同时是**运行时状态目录**(任何 plugin 都可以往里写 `.local.md`、状态机、缓存)。

```powershell
# .devcontainer/devcontainer.json:36-37
"CLAUDE_CONFIG_DIR": "/home/node/.claude"
```
**关键发现**:`CLAUDE_CONFIG_DIR` 是**唯一已知的"工作区路径自定义"手段**,默认指向用户主目录,容器场景下可指向容器内任意位置。

### Q2. 工作区目录结构 — 文件系统即一切

#### 2.1 项目级 `.claude/`(仓库内)

| 子项 | 类型 | 路径 | 内容 | 关键证据 |
|---|---|---|---|---|
| **slash commands** | 目录 | `.claude/commands/*.md` | 每个 `.md` 是一个 `/foo` 命令,带 YAML frontmatter | `plugins/README.md:78-81`<br>`.claude/commands/commit-push-pr.md:1-15` |
| **subagents** | 目录 | `.claude/agents/*.md` | 每个 `.md` 是一个可委派子 Agent,带 YAML frontmatter(`name/description/tools/model`) | `plugins/README.md:83-86`<br>`plugins/feature-dev/agents/code-explorer.md:1-15` |
| **skills** | 目录 | `.claude/skills/<name>/SKILL.md` | 每个 skill 一个子目录,SKILL.md 是入口,支持 `references/`、`examples/`、`scripts/` 子目录 | `plugins/README.md:88-91`<br>`plugins/plugin-dev/skills/plugin-structure/SKILL.md:62-70`<br>`plugins/frontend-design/skills/frontend-design/SKILL.md:1-15` |
| **hooks** | 文件 | `.claude/settings.json`(内嵌 `hooks` 键) | 事件 → 命令数组的映射,直接写在 settings.json 顶层,没有 `hooks/hooks.json` 独立文件 | `plugins/plugin-dev/skills/hook-development/SKILL.md:120-126` |
| **MCP** | 文件 | `.mcp.json` | MCP 服务器定义(`mcpServers` 键) | `CHANGELOG.md:219,426,735`<br>`plugins/plugin-dev/skills/plugin-structure/SKILL.md:73-78` |
| **rules** | 目录 | `.claude/rules/*.md` | 条件规则文件,frontmatter `paths:` 可控制触发范围 | `CHANGELOG.md:3991` "Added support for .claude/rules/"<br>`CHANGELOG.md:63,404,3054` |
| **plugin state** | 文件 | `.claude/<plugin>.local.md` | 任意 plugin 在项目下的运行时状态(YAML frontmatter + markdown body) | `plugins/plugin-dev/skills/plugin-settings/SKILL.md:14-23` |
| **CLI 工作区** | 目录 | `.claude/worktrees/` | git worktree 集成(隔离子任务) | `CHANGELOG.md:12` |
| **总配置** | 文件 | `.claude/settings.json` | 项目级 settings(被 `.claude/settings.local.json` 覆盖,被 `~/.claude/settings.json` 覆盖) | `CHANGELOG.md:203,206,1619,2955` |
| **本地用户覆盖** | 文件 | `.claude/settings.local.json` | 单个用户在本项目的私有覆盖(写"Always allow"用) | `CHANGELOG.md:1619,2955` |
| **CLAUDE.md** | 文件 | `./CLAUDE.md` 或 `<any-subdir>/CLAUDE.md` | 自然语言规则文件,递归加载 | `CHANGELOG.md:2400,2440,2890,3029,3054` |

#### 2.2 用户级 `~/.claude/`(默认 `CLAUDE_CONFIG_DIR`)

| 项 | 类型 | 路径 | 关键证据 |
|---|---|---|---|
| **总配置** | 文件 | `~/.claude/settings.json` | `CHANGELOG.md:624,1431,1773,1778,1860` |
| **凭据** | 文件 | `~/.claude/.credentials.json` | `CHANGELOG.md:1852,1878` |
| **主题** | 目录 | `~/.claude/themes/*.json` | `CHANGELOG.md:1834` |
| **键位** | 文件 | `~/.claude/keybindings.json` | `CHANGELOG.md:2167,2551` |
| **历史** | 文件 | `~/.claude/history.jsonl` | `CHANGELOG.md:2391` |
| **task cache** | 目录 | `~/.claude/tasks/` | `CHANGELOG.md:1878` |
| **shell 快照** | 目录 | `~/.claude/shell-snapshots/` | `CHANGELOG.md:1878` |
| **backups** | 目录 | `~/.claude/backups/` | `CHANGELOG.md:1878` |
| **workflows** | 目录 | `~/.claude/workflows/` | `CHANGELOG.md:160` |
| **daemon** | 目录 | `~/.claude/daemon/` | `CHANGELOG.md:697` |
| **CLAUDE.md** | 文件 | `~/.claude/CLAUDE.md` | `CHANGELOG.md:2440` |
| **per-project 元数据** | 文件 | `~/.claude.json`(信任、history 列表) | `CHANGELOG.md:4547` |

#### 2.3 完整 `.claude/` 目录样例(基于 `plugins/README.md:75-93` + `plugins/plugin-dev/skills/plugin-structure/SKILL.md:18-32` + 真实 plugin 实现)

```
project-root/
├── CLAUDE.md                       # 项目根规则(可 git 提交)
├── CLAUDE.local.md                 # (推测,基于 rules/ 命名规律)单用户本地覆盖
├── .mcp.json                       # 项目级 MCP 服务器
├── .claude/
│   ├── settings.json               # 项目级 settings(committed)
│   ├── settings.local.json         # 单用户本地覆盖(not committed)
│   ├── commands/                   # slash commands (子 .md)
│   │   ├── commit.md               # → /commit
│   │   ├── review.md               # → /review
│   │   └── ...
│   ├── agents/                     # subagents
│   │   ├── code-reviewer.md        # 带 frontmatter: name/description/tools/model
│   │   └── ...
│   ├── skills/                     # skills(子目录)
│   │   ├── api-testing/
│   │   │   ├── SKILL.md            # 入口
│   │   │   ├── scripts/            # 可执行脚本
│   │   │   ├── references/         # 参考文档
│   │   │   └── examples/           # 示例
│   ├── hooks/                      # (plugin 内,非 .claude/ 根)
│   ├── rules/                      # 条件规则,带 paths: frontmatter
│   │   ├── frontend.md             # paths: ["src/components/**"]
│   │   └── backend.md              # paths: ["src/api/**"]
│   ├── worktrees/                  # git worktree 集成
│   ├── <plugin-name>.local.md      # 任意 plugin 的项目级状态
│   └── ralph-loop.local.md         # 实际产物(由 ralph-wiggum 插件创建)
└── plugins/                        # (本仓库)本地 plugin 源码,作为 marketplace 源
    └── <name>/
        ├── .claude-plugin/
        │   └── plugin.json         # plugin 元数据
        ├── commands/
        ├── agents/
        ├── skills/<skill-name>/SKILL.md
        ├── hooks/hooks.json
        ├── .mcp.json
        └── scripts/
```

#### 2.4 关键代码证据(目录约定)

`plugins/plugin-dev/skills/plugin-structure/SKILL.md:18-32`(官方目录约定说明):

```
plugin-name/
├── .claude-plugin/
│   └── plugin.json          # Required: Plugin manifest
├── commands/                 # Slash commands (.md files)
├── agents/                   # Subagent definitions (.md files)
├── skills/                   # Agent skills (subdirectories)
│   └── skill-name/
│       └── SKILL.md         # Required for each skill
├── hooks/
│   └── hooks.json           # Event handler configuration
├── .mcp.json                # MCP server definitions
└── scripts/                 # Helper scripts and utilities
```

**Critical rules**(`SKILL.md:35-39`):
1. The `plugin.json` manifest **MUST** be in `.claude-plugin/` directory
2. All component directories (commands, agents, skills, hooks) **MUST** be at plugin root level, **NOT** nested inside `.claude-plugin/`
3. Only create directories for components the plugin actually uses
4. Use **kebab-case** for all directory and file names

`plugins/plugin-dev/skills/plugin-structure/SKILL.md:96-115`(自动发现):

> **Auto-Discovery Mechanism**
> Claude Code automatically discovers and loads components:
> 1. Plugin manifest: Reads `.claude-plugin/plugin.json` when plugin enables
> 2. Commands: Scans `commands/` directory for `.md` files
> 3. Agents: Scans `agents/` directory for `.md` files
> 4. Skills: Scans `skills/` for subdirectories containing `SKILL.md`
> 5. Hooks: Loads configuration from `hooks/hooks.json` or manifest
> 6. MCP servers: Loads configuration from `.mcp.json` or manifest

### Q3. 工作区创建 — 隐式 + 多机制并存

#### 3.1 创建机制矩阵

| 元素 | 创建方式 | 是否显式命令 | 是否运行时自动 | 关键证据 |
|---|---|---|---|---|
| **项目根 (cwd)** | 用户 `cd` | n/a | 用户主动 | `README.md:50` "Navigate to your project directory and run `claude`" |
| **CLAUDE.md** | 用户手写 或 `/init` 引导 | `/init` 是 bundled skill(可被模型通过 Skill tool 调用) | n/a | `CHANGELOG.md:2057` "The model can now discover and invoke built-in slash commands like `/init`..." |
| **`.claude/` 目录** | Claude Code 主进程或 plugin 按需 `mkdir -p` | 无 | ✅ 运行时隐式 | `plugins/ralph-wiggum/scripts/setup-ralph-loop.sh:108` `mkdir -p .claude` |
| **`.claude/settings.json`** | 用户手写 或 "Always allow" 自动追加 | 无(无 `claude init`) | 部分(`settings.local.json` 在 SDK 模式下自动建议) | `CHANGELOG.md:1619` "SDK hosts now receive a persistent `localSettings` suggestion... so 'Always allow' writes to `.claude/settings.local.json`" |
| **`.claude/commands/*.md`** | 用户手写 | 无 | n/a | `plugins/README.md:99-104` "These plugins are included in the Claude Code repository. To use them in your own projects: ... `claude`" |
| **`.claude/agents/*.md`** | 用户手写 或 plugin 自动 | 无 | 部分(某些 plugin 的 agents 由 plugin 加载时出现) | `CHANGELOG.md:346` "Fixed `claude agents --plugin-dir <dir>` not showing the plugin's agents" |
| **`.claude/skills/`** | 用户手写 或 plugin 安装 | 无 | 部分 | `CHANGELOG.md:653,2057` |
| **`.mcp.json`** | 用户手写 | 无 | n/a | `CHANGELOG.md:1010,3015`(信任对话框处理) |
| **`.claude/rules/*.md`** | 用户手写 | 无 | n/a | `CHANGELOG.md:3991` |
| **`.claude/<plugin>.local.md`** | plugin 命令/hook 主动写 | 视 plugin 而定(如 `/ralph-loop`) | ✅ 运行时隐式 | `plugins/ralph-wiggum/scripts/setup-ralph-loop.sh:108-120` |
| **`~/.claude/settings.json`** | 用户通过 `/config` 或 `claude` CLI 交互 | `/config` | ✅ 运行时隐式 | `CHANGELOG.md:1778` "`/config` settings... now persist to `~/.claude/settings.json`" |
| **`~/.claude/.credentials.json`** | 登录 OAuth 时自动 | `/login` 触发 | ✅ 运行时隐式 | `CHANGELOG.md:1852` |
| **`~/.claude/history.jsonl`** | 每次 prompt 自动 append | n/a | ✅ 运行时隐式 | `CHANGELOG.md:2391` |
| **`~/.claude/themes/*.json`** | 用户 `/theme` 或手编辑 | `/theme` | 部分 | `CHANGELOG.md:1834` |
| **`~/.claude/keybindings.json`** | 用户手编辑 | 无 | n/a | `CHANGELOG.md:2167` |
| **`~/.claude/tasks/`** | 自动(session 任务) | 无 | ✅ 运行时隐式 | `CHANGELOG.md:1878` |

#### 3.2 `CLAUDE.md` 的创建细节
- **不是**由 Claude Code 主进程自动创建
- **可以**由 `/init` 内置 skill 引导模型"反推项目结构"生成
- **可放多处**:
  - `<project-root>/CLAUDE.md`(最常见,committable)
  - `<project-root>/<sub-dir>/CLAUDE.md`(递归注入)
  - `~/.claude/CLAUDE.md`(用户级,跨项目)
- **HTML 注释**在自动注入时被隐藏,只在 Read 工具调用时可见
  - 证据: `CHANGELOG.md:2890` "Changed CLAUDE.md HTML comments (`<!-- ... -->`) to be hidden from Claude when auto-injected. Comments remain visible when read with the Read tool"
- **大小阈值警告**:
  - 证据: `CHANGELOG.md:792` "The 'CLAUDE.md is too long' warning threshold now scales with the model's context window"

#### 3.3 Settings 优先级(从高到低)

| 优先级 | 来源 | 路径 | 关键证据 |
|---|---|---|---|
| **0(最高)** | Enterprise managed(MDM/系统策略) | `C:\Program Files\ClaudeCode\managed-settings.json`(Win) / `com.anthropic.claudecode.plist`(macOS) | `CHANGELOG.md:2824`,`examples/mdm/README.md:21-24` |
| **1** | CLI 标志 | `--settings <file>`, `--mcp-config <file>`, `--plugin-dir` | `CHANGELOG.md:1286,1292,2801,1613` |
| **2** | `~/.claude/settings.json`(用户全局) | 由 `CLAUDE_CONFIG_DIR` 覆盖 | `CHANGELOG.md:160,203,1778,1860` |
| **3** | `.claude/settings.json`(项目级,committed) | 不读 `pluginConfigs`(只读 user/--settings/managed) | `CHANGELOG.md:206` "Plugin option values (`pluginConfigs`) are no longer read from project-level `.claude/settings.json`; only user, `--settings`, and managed settings are honored" |
| **4(最低)** | `.claude/settings.local.json`(项目级单用户) | SDK "Always allow" 自动写这里 | `CHANGELOG.md:203,1619,2955` |

#### 3.4 关键代码证据(运行时隐式创建)

```bash
# plugins/ralph-wiggum/scripts/setup-ralph-loop.sh:108-120
# Ralph Wiggum plugin 在用户调用 /ralph-loop 时隐式创建 .claude/ 与状态文件
mkdir -p .claude
cat > .claude/ralph-loop.local.md <<EOF
---
active: true
iteration: 1
max_iterations: $MAX_ITERATIONS
completion_promise: $COMPLETION_PROMISE_YAML
started_at: "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
---
$PROMPT
EOF
```

```bash
# plugins/ralph-wiggum/hooks/stop-hook.sh:8-17
# Stop hook 读取状态文件判断是否阻断 session 退出
HOOK_INPUT=$(cat)
RALPH_STATE_FILE=".claude/ralph-loop.local.md"
if [[ ! -f "$RALPH_STATE_FILE" ]]; then
  # No active loop - allow exit
  exit 0
fi
```

```powershell
# .devcontainer/devcontainer.json:36-37
# 容器场景下用 CLAUDE_CONFIG_DIR 覆盖用户主目录默认值
"containerEnv": {
  "CLAUDE_CONFIG_DIR": "/home/node/.claude"
},
"mounts": [
  "source=claude-code-config-${devcontainerId},target=/home/node/.claude,type=volume"
]
```

---

## 3. 关键代码片段

### 3.1 Hook 事件 Schema(完整)

来源: `plugins/security-guidance/hooks/hooks.json`(真实 plugin hook 配置)

```json
{
  "description": "Security guidance plugin — pattern-based warnings on edits, git-diff-based LLM review on stop",
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "bash \"${CLAUDE_PLUGIN_ROOT}/hooks/sg-python.sh\" \"${CLAUDE_PLUGIN_ROOT}/hooks/ensure_agent_sdk.py\"",
            "timeout": 180
          }
        ]
      }
    ],
    "UserPromptSubmit": [...],
    "PostToolUse": [
      {
        "hooks": [...],
        "matcher": "Edit|Write|MultiEdit|NotebookEdit"
      },
      {
        "hooks": [...],
        "matcher": "Bash",
        "if": "Bash(git commit:*)",
        "asyncRewake": true,
        "rewakeMessage": "...",
        "rewakeSummary": "..."
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "...",
            "asyncRewake": true,
            "rewakeMessage": "...",
            "rewakeSummary": "..."
          }
        ]
      }
    ]
  }
}
```

### 3.2 Hook 事件类型(从 `plugins/plugin-dev/skills/hook-development/SKILL.md:163-200`)

| 事件 | 触发时机 | 关键能力 |
|---|---|---|
| `PreToolUse` | 工具运行前 | approve/deny/ask + 修改 `tool_input`(`hookSpecificOutput.updatedInput`) |
| `PostToolUse` | 工具完成后 | stdout 写入 transcript,exit 2 时 stderr 回给 Claude |
| `Stop` | 主 Agent 试图停止 | approve/block + 输出 `systemMessage`(配合 asyncRewake 实现后台持续审阅) |
| `SubagentStop` | 子 Agent 完成 | 同 Stop |
| `UserPromptSubmit` | 用户提交 prompt | 添加上下文、validate、block |
| `SessionStart` | Session 开始 | 通过 `$CLAUDE_ENV_FILE` 持久化 env 变量,设 session title |
| `SessionEnd` | Session 结束 | 清理、日志、状态保存 |
| `PreCompact` | 上下文压缩前 | 注入必须保留的信息 |
| `Notification` | 通知事件 | 反应用户通知 |
| `InstructionsLoaded` | CLAUDE.md / `.claude/rules/*.md` 加载时 | 拦截规则注入 |
| `MessageDisplay` | 助手消息显示前 | 转换或隐藏消息文本 |
| `TeammateIdle`, `TaskCompleted` | 团队 Agent 协议 | 同 Stop 的 continue/stopReason 行为 |

### 3.3 Hook 命令可用的环境变量(`plugins/plugin-dev/skills/hook-development/SKILL.md:340-345`)

- `$CLAUDE_PROJECT_DIR` — 项目根路径
- `$CLAUDE_PLUGIN_ROOT` — Plugin 目录(用于可移植路径)
- `$CLAUDE_ENV_FILE` — SessionStart 专用,持久化 env 变量
- `$CLAUDE_CODE_REMOTE` — 若在远程上下文中运行则被设置
- `$CLAUDE_SKILL_DIR` — Skill 自己的目录(SKILL.md 内容中引用)

### 3.4 Hook 命令的标准输入 JSON(`plugins/plugin-dev/skills/hook-development/SKILL.md:319-336`)

```json
{
  "session_id": "abc123",
  "transcript_path": "/path/to/transcript.txt",
  "cwd": "/current/working/dir",
  "permission_mode": "ask|allow",
  "hook_event_name": "PreToolUse"
}
```
事件特定字段:
- `PreToolUse/PostToolUse`: `tool_name`, `tool_input`, `tool_result`
- `UserPromptSubmit`: `user_prompt`
- `Stop/SubagentStop`: `reason`

### 3.5 Subagent Frontmatter(从 `plugins/feature-dev/agents/code-explorer.md:1-7`)

```yaml
---
name: code-explorer
description: Deeply analyzes existing codebase features...
tools: Glob, Grep, LS, Read, NotebookRead, WebFetch, TodoWrite, WebSearch, KillShell, BashOutput
model: sonnet
color: yellow
---
```

### 3.6 Skill Frontmatter(从 `plugins/frontend-design/skills/frontend-design/SKILL.md:1-5`)

```yaml
---
name: frontend-design
description: Guidance for distinctive, intentional visual design...
license: Complete terms in LICENSE.txt
---
```

### 3.7 Plugin Manifest(从 `plugins/feature-dev/.claude-plugin/plugin.json:1-10`)

```json
{
  "name": "feature-dev",
  "version": "1.0.0",
  "description": "Comprehensive feature development workflow...",
  "author": {
    "name": "Sid Bidasaria",
    "email": "sbidasaria@anthropic.com"
  }
}
```

### 3.8 Plugin 配置可覆盖路径(`plugins/plugin-dev/skills/plugin-structure/SKILL.md:62-70`)

```json
{
  "name": "plugin-name",
  "commands": "./custom-commands",
  "agents": ["./agents", "./specialized-agents"],
  "hooks": "./config/hooks.json",
  "mcpServers": "./.mcp.json"
}
```
> Custom paths supplement defaults — they don't replace them.

### 3.9 `${CLAUDE_PLUGIN_ROOT}` 可移植性(`plugins/plugin-dev/skills/plugin-structure/SKILL.md:128-145`)

```json
{
  "command": "bash ${CLAUDE_PLUGIN_ROOT}/scripts/run.sh"
}
```
**Why it matters**: Plugins install in different locations depending on:
- User installation method (marketplace, local, npm)
- Operating system conventions
- User preferences

---

## 4. 与 Onion Agent 设计的关联

> Onion Agent 的设计哲学:智能体的一切活动围绕一个 `session.json` 上下文历史文件,Agent Loop 是围绕 session 文件的自动累加器。
> 以下仅提取**与 Onion Agent 直接相关**的设计启示,不做空泛比较。

### 4.1 Claude Code 给 Onion Agent 的关键启示

| 启示 | 来源 | 对 Onion Agent 的具体建议 |
|---|---|---|
| **三路径叠加模型** | `Q1.3` 优先级表 | Onion Agent 也可采用 `cwd/.onion/`(项目级) + `~/.onion/`(用户级) + 系统级(企业级)三层,而不是只写 `~/.onion/`,这样符合"Vibe Coding 跟随项目目录"的用户心智。 |
| **`CLAUDE_CONFIG_DIR` 单一覆盖点** | `.devcontainer/devcontainer.json:36-37` | Onion Agent 应支持单一 `ONION_CONFIG_DIR` 环境变量覆盖用户级路径,容器/SDK 场景极其有用。 |
| **CLAUDE.md 递归加载** | `CHANGELOG.md:2400,2890,3029,3054` | Onion Agent 若要做"规则文件",应支持 `<cwd>/RULE.md` + `<cwd>/<sub-dir>/RULE.md` 递归,而不是只在 cwd 找。HTML 注释在自动注入时隐藏(RULE 维护者常用注释做注解)是一个可借鉴的细节。 |
| **`.claude/rules/*.md` 条件规则** | `CHANGELOG.md:3991,3054,404,63` | Onion Agent 可以支持"按 paths: 条件加载的规则文件",例如 `*.test.md` 只在修改测试文件时注入。 |
| **`.local.md` plugin 状态文件模式** | `plugins/plugin-dev/skills/plugin-settings/SKILL.md:1-200` | 任意 plugin/子模块可在 `.onion/<plugin>.local.md` 写自己的运行时状态,frontmatter 是结构化数据,markdown body 是可读上下文 — 非常适合 Onion Agent 的"session.json 上下文历史"哲学的延伸。Ralph Wiggum 的实现是教科书级范例(`setup-ralph-loop.sh:108-120`)。 |
| **Auto-Discovery 不需要 init** | `plugins/plugin-dev/skills/plugin-structure/SKILL.md:96-115` | Onion Agent 可以采用"约定优于配置"——`commands/`、`agents/`、`skills/` 这些目录扫到就用,而不是要求显式注册。 |
| **Hook 事件 + 单一 stdin JSON** | `plugins/plugin-dev/skills/hook-development/SKILL.md:319-336` | Onion Agent 应支持"Pre/Post/SessionStart/Stop"等 hook 事件,stdin 喂统一 JSON,命令可执行。这与 session.json 的 append-only 设计天然契合:hook 可以监听 session 变更并触发外部动作。 |
| **Hook 输出 `decision: block` + `reason` 阻断** | `plugins/ralph-wiggum/hooks/stop-hook.sh:160-170` | 借鉴 Ralph Wiggum 的"自我迭代"模式:Stop hook 可以 block 退出并喂回同一个 prompt,实现 Onion Agent 的"自循环"。这是**与 Onion Agent "session 文件累加器"哲学最匹配**的设计模式。 |
| **Plugin `${CLAUDE_PLUGIN_ROOT}` 路径抽象** | `plugins/plugin-dev/skills/plugin-structure/SKILL.md:128-145` | Onion Agent 的 plugin 路径应该用 `${ONION_PLUGIN_ROOT}` 而不是硬编码,让 plugin 可以从 marketplace、local、npm 等多种来源安装。 |
| **Plugin 依赖解耦: hooks.json 用 `{"hooks": {...}}` 包装,settings.json 用直接键** | `plugins/plugin-dev/skills/hook-development/SKILL.md:120-126` | 这是个非常聪明的设计 —— 单一 hook 事件在两个上下文(用户级 vs plugin 级)用不同 schema,避免歧义。Onion Agent 也应区分"plugin 配置"和"用户配置"的格式。 |
| **Settings 优先级 0/1/2/3/4 五层** | `Q3.3` 优先级表 | Onion Agent 若要做"团队/企业级管控",应直接照搬这套优先级:enterprise → CLI → 用户 → 项目 → 项目-local。 |
| **CHANGELOG 显示 `.claude/*.local.md` 推荐加进 .gitignore** | `plugins/plugin-dev/skills/plugin-settings/examples/example-settings.md:132-135` | Onion Agent 的运行时状态文件应该明确建议用户加入 `.gitignore`。 |
| **Plugin 验证 `/plugin validate`** | `CHANGELOG.md:2755` | Onion Agent 可以提供 `onion plugin validate`,在加载前校验 plugin 结构 + YAML frontmatter,提高开发者体验。 |
| **信任对话框(trust dialog)** | `CHANGELOG.md:426,735,783,2679,3189,3653,3732` | Onion Agent 加载项目级 `.onion/settings.json` 时,应弹出"信任此项目?"对话框,防止仓库偷偷加恶意 hook(Claude Code 也是这么做的)。 |
| **`--setting-sources` 显式禁用 project** | `CHANGELOG.md:3028,2148,4231` | Onion Agent 可以提供 `onion --setting-sources user` 标志,完全禁用项目级配置(类似 Claude Code 的 `--safe-mode` 标志)。 |
| **`/doctor` 自检** | `CHANGELOG.md:212,1826,1397` | 借鉴:提供 `onion doctor`,扫描 CLAUDE.md 过长、`.mcp.json` 配置冲突、plugin 缓存过期等常见问题。 |

### 4.2 特别推荐给 Onion Agent 借鉴的 3 个设计模式

1. **`.local.md` Plugin 状态模式**(`plugins/plugin-dev/skills/plugin-settings/SKILL.md`)
   - 任何子模块/plugin 可在 `.onion/<name>.local.md` 写自己的持久状态
   - YAML frontmatter 是结构化配置,markdown body 是可读 prompt/上下文
   - 这是 Claude Code 把"plugin 状态"与"用户配置"解耦的精髓
   - 适合 Onion Agent:让每个子能力(如代码审查、测试运行、部署)有自己的状态文件,而 session.json 只关心对话流

2. **Ralph Wiggum 自循环模式**(`plugins/ralph-wiggum/`)
   - Stop hook 检查状态文件 → 若有任务未完成 → 输出 `{"decision": "block", "reason": <原 prompt>, "systemMessage": "..."}` 阻断退出
   - **与 Onion Agent "session 文件累加器"哲学完美匹配**:Agent 不会因为"完成 turn"就结束,而是 session.json 没完就不停
   - 状态文件 `.claude/ralph-loop.local.md` 的 YAML frontmatter 控制 `iteration`/`max_iterations`/`completion_promise` 三个核心元数据,Onion Agent 完全可以照搬

3. **三层叠加 + 单一覆盖点**
   - 企业 managed > CLI flags > `~/.onion/` > `<cwd>/.onion/` > `<cwd>/.onion/settings.local.json`
   - 用单一 `ONION_CONFIG_DIR` 环境变量覆盖用户级路径
   - 这是 Claude Code 在 macOS/Linux/Windows 跨平台 + IDE/CLI/Slack/Desktop 多端集成能稳定运行的根本原因

---

## 5. 不确定 / 未找到

### 5.1 二进制源码不可见导致的不确定
以下信息只能从公开仓库与 CHANGELOG 间接推断,Claude Code 主进程内部的具体解析顺序、合并策略、缓存失效逻辑无法直接验证:

| 问题 | 已知证据 | 不确定 |
|---|---|---|
| **`.claude/` 中 files 加载的具体顺序** | `plugins/plugin-dev/skills/hook-development/SKILL.md:241-251` 只说"Plugin hooks merge with user's hooks and run in parallel",没说项目级 + 用户级 + managed 的精确 merge 顺序 | 优先级细节(谁覆盖谁、数组如何合并) |
| **`.claude/` 路径解析的递归终止条件** | `CHANGELOG.md:2400,3029,3025` 提到"嵌套 CLAUDE.md"被加载和"worktree 嵌套"重复 | 多深算嵌套、是否每个子目录都扫、symlink 是否跟随(`CHANGELOG.md:684` 提到 `.claude/settings.json` 跟随 symlink,但其他文件行为未知) |
| **`<cwd>/.claude/settings.json` 字段全集** | `CHANGELOG.md:1778,1293,1236,1773` 等间接提到 `model`, `effortLevel`, `env`, `permissions`, `autoMode`, `strictKnownMarketplaces`, `allowManagedHooksOnly`, `allowManagedPermissionRulesOnly`, `respondToBashCommands`, `forceRemoteSettingsRefresh`, `disableBundledSkills`, `requiredMinimumVersion/MaximumVersion`, `forceLoginOrgUUID/Method`, `allowAllClaudeAiMcps`, `allowedMcpServers/deniedMcpServers`, `pluginSuggestionMarketplaces`, `pluginTrustMessage`, `cleanupPeriodDays`, `includeGitInstructions`, `statusLine`, `fileSuggestion`, `otelHeadersHelper` | 完整字段列表(应该有几十个) |
| **`claude init` 命令是否存在** | `CHANGELOG.md:2057` 提到 `/init` 是 bundled slash command,无 `claude init` CLI 标志的证据 | 是否还有 `claude init` 作为外层命令(推测无,因为 README 写的是 "navigate + run `claude`") |
| **`<cwd>/CLAUDE.local.md` 是否存在** | 未在仓库任何文件或 CHANGELOG 找到直接证据;`settings.local.json` 模式存在 | `CHANGELOG.md:2440` 提到 `~/.claude/CLAUDE.md`,但项目级 CLAUDE.md 的本地覆盖机制不明确 |
| **Plugin 安装到磁盘的位置** | `CHANGELOG.md:1875,1255,1236,1236,1875` 多次提到"plugin cache"、"MCPB plugin cache"在 Windows 上被"re-extraction",说明 plugin 是 zipped/distributed 形态 | 具体缓存目录路径(可能 `~/.claude/plugins/` 或 `~/.claude/cache/plugins/`,但无直接证据) |
| **`~/.claude/` 中 tasks/、backups/、shell-snapshots/ 实际内容** | 仅在 `CHANGELOG.md:1878` 一处被提到 | 这些目录的内部文件结构 |
| **CLAUDE.md 的精确 size warning 阈值** | `CHANGELOG.md:792` 只说"now scales with the model's context window" | 精确计算公式 |
| **enterprise managed settings 在 Linux 的路径** | 只看到 macOS plist + Windows `C:\Program Files\ClaudeCode\managed-settings.json` 证据 | Linux 路径(可能是 `/etc/claude-code/managed-settings.json` 或 `/Library/Managed Preferences/...`,未直接见到) |

### 5.2 本次调研未深入的项
- **`<cwd>/.claude/agents/` 中的 subagent 如何被 `Agent` tool 调用**(上下文管理、超时、并发上限 `CHANGELOG.md:8` `CLAUDE_CODE_MAX_SUBOUTPUT_TOKENS_PER_SESSION` 之类)
- **Hook 失败时 Claude Code 的 fallback 行为**(CHANGELOG 提到 hook 错误会"stderr 喂回 Claude",但完整 fallback 矩阵未知)
- **Plugin 之间冲突解决机制**(命名空间、prefix 机制)
- **`.claude/skills/` 中 SKILL.md 的精确发现算法**(匹配 description 的 embedding 距离阈值)

### 5.3 推荐下一步调研
- 在 sandbox 中实际运行 `npm install -g @anthropic-ai/claude-code` 然后 `cd <test-project> && claude` 验证 `.claude/` 是否在第一次 session 后被自动创建(以及创建什么)
- 查阅 https://code.claude.com/docs/en/settings 官方文档(settings 完整 schema 一定在这里)
- 查阅 https://code.claude.com/docs/en/plugins 官方文档(plugin 系统权威说明)
- 查阅 https://code.claude.com/docs/en/memory 官方文档(CLAUDE.md / rules 完整说明)
- 抓取 https://docs.claude.com/en/docs/claude-code/hooks 官方 hook 文档
