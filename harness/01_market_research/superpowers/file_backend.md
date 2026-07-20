# obra/superpowers — 工作区(File Backend)调研报告

## 0. 智能体一句话定位

**superpowers 不是 agent 本身,而是"给 coding agent 用的 SDLC 方法论 + 可组合技能库插件"** —— 一套装在 Claude Code / Codex / Cursor / OpenCode / Pi / Kimi Code / Gemini CLI / Antigravity / Copilot CLI / Factory Droid 等多端 agent 之上的"流程约束 + skills 集合",强制 agent 在写代码前先 brainstorming、出 plan、按 TDD 执行、用 subagent 做两阶段 review。代码量极轻(零运行时依赖),核心资产是 `skills/` 下的 14 个 SKILL.md + bootstrap 注入器(hook 或 in-process 插件)。

## 1. 调研依据

### 源码路径

- `C:\workspace\github\onionagent\harness\01_market_research\clone\superpowers\`

### 关键文件 / 关键代码片段

1. `clone/superpowers/skills/subagent-driven-development/scripts/sdd-workspace:14-20` — 唯一创建项目级 `.superpowers/sdd/` 的脚本(在 git worktree 内隐式创建)
2. `clone/superpowers/skills/brainstorming/scripts/start-server.sh:117-121` — 创建 `.superpowers/brainstorm/<SESSION_ID>/` 作为视觉伴侣的工作区
3. `clone/superpowers/hooks/session-start:1-65` — 整个 superpowers 唯一的"bootstrap 入口",被 Claude Code/Cursor/Copilot CLI 共用
4. `clone/superpowers/.opencode/plugins/superpowers.js:48-58` — OpenCode 的 in-process 插件,显式读取 `OPENCODE_CONFIG_DIR` 环境变量
5. `clone/superpowers/.pi/extensions/superpowers.ts:14-23` — Pi 的 in-process 扩展,显式计算 `packageRoot` 并把 `skills/` 路径注册到 `resources_discover`
6. `clone/superpowers/.gitignore:1-9` — 仓库根 `.gitignore` 已经把 `.superpowers/` 和 `.worktrees/` 列入黑名单
7. `clone/superpowers/skills/subagent-driven-development/scripts/sdd-workspace:21-22` — 创建 `.superpowers/sdd/.gitignore` 内容为 `*`(自屏蔽)
8. `clone/superpowers/skills/subagent-driven-development/SKILL.md:254` — 显式指示 "在 `<repo>/.superpowers/sdd/progress.md` 找进度 ledger,被 compaction 丢失后从这里恢复"
9. `clone/superpowers/package.json:13-19` — Pi 包清单,声明 `skills: ["./skills"]` 和 `pi.extensions`
10. `clone/superpowers/.claude-plugin/plugin.json` / `.cursor-plugin/plugin.json` / `.codex-plugin/plugin.json` / `.kimi-plugin/plugin.json` / `gemini-extension.json` — 10 个不同 agent 框架的 manifest,但**没有一个**包含 init/setup 命令

### 文档 / README 引用

1. `clone/superpowers/README.md:31-180` — 10 个 harness 的安装命令(`/plugin install`, `agy plugin install`, `pi install git:...` 等),**没有 superpowers 自己的 init 命令**
2. `clone/superpowers/docs/porting-to-a-new-harness.md:1-700` — 700 行"如何为新 agent 框架 port"指南,核心信条是 "Bootstrap rides the install mechanism, never edit the user's files"(Part 1 rule 2)
3. `clone/superpowers/CLAUDE.md:160-176` — 维护者铁律 "These are not real integrations: Manually copying skill files into the harness" 会被立刻关 PR

## 2. 三个核心问题的回答

### Q1. 工作区路径:固定位置 vs 可自定义?

**答:三层,每层都通过不同机制配置,但都不允许 superpowers 自己"全局写死"**。

#### 第 1 层 · 插件自身所在目录(全局 skills 库)

**没有 `~/.superpowers/` 这种 superpowers 自己定义的固定目录**。Skills 不放在 superpowers 名下,而是**装进宿主 agent 的 plugin/extension 安装位置** —— 由宿主决定,superpowers 完全顺从:

| 宿主 | Skills 落点 | 决定方式 |
|---|---|---|
| Claude Code | `${CLAUDE_PLUGIN_ROOT}/skills/`(plugin 根) | `plugin install` 命令装到 marketplace 指定目录 |
| Cursor | 同上 | `.cursor-plugin/plugin.json` 的 `"skills": "./skills/"` |
| OpenCode | `$OPENCODE_CONFIG_DIR/superpowers/skills/`(默认在 `~/.config/opencode/superpowers/skills/`) | `tests/opencode/setup.sh:14-22` 显式 `cp -r skills/ $OPENCODE_CONFIG_DIR/superpowers/` |
| Pi | 通过 `pi.skills: ["./skills"]` 字段注册 | `package.json:18` |
| Codex | `.codex-plugin/plugin.json` 用 `skills: "./skills/"`,由 codex 自己的 plugin loader 处理 |  |

证据:
- `clone/superpowers/.opencode/plugins/superpowers.js:50` — `const superpowersSkillsDir = path.resolve(__dirname, '../../skills');`(从插件自身位置反推)
- `clone/superpowers/.opencode/plugins/superpowers.js:58` — `const envConfigDir = normalizePath(process.env.OPENCODE_CONFIG_DIR, homeDir);`(尊重宿主环境变量,fallback 到 `~/.config/opencode`)
- `clone/superports/docs/porting-to-a-new-harness.md:117-118` — 铁律 "Bootstrap rides the install mechanism, never edit the user's files"

注意:测试代码 `clone/superpowers/tests/hooks/test-session-start.sh:194` 提到 `~/.config/superpowers/skills` 这个路径,但明确写 "obsolete legacy custom-skill warning" —— 是**已废弃**的旧布局。

#### 第 2 层 · 项目级工作区 `<repo>/.superpowers/`

**完全没有配置项**,由 skills 自己按需创建,固定写在每个 skill 的脚本里:

- `skills/subagent-driven-development/scripts/sdd-workspace:14-20`:
  ```bash
  root=$(git rev-parse --show-toplevel)
  dir="$root/.superpowers/sdd"
  mkdir -p "$dir"
  ```
- `skills/brainstorming/scripts/start-server.sh:117`:
  ```bash
  SESSION_DIR="${PROJECT_DIR}/.superpowers/brainstorm/${SESSION_ID}"
  ```

**不可改写**:从这两个脚本的代码看,`$root` 和 `${PROJECT_DIR}` 唯一决定落点,没有 `SUPERPOWERS_DIR` 之类的环境变量 override。

#### 第 3 层 · Worktree 目录

由 `skills/using-git-worktrees/SKILL.md:80-90` 决定 —— 优先级:显式用户指令 > 现有项目内 `.worktrees/` > 现有 `worktrees/` > 默认 `.worktrees/`。**这是 skill 行为(由 agent 读 SKILL.md 后做决策),不是 hardcoded 代码**。

证据:`clone/superpowers/skills/using-git-worktrees/SKILL.md:75-78`
> Directory Selection: 1. Check your instructions for a declared worktree directory preference. 2. Check for an existing project-local worktree directory. 3. If there is no other guidance available, default to `.worktrees/` at the project root.

#### 跟随当前目录(在项目根自动识别)?

**是,完全跟随。** 因为:
- `sdd-workspace:15` 用 `git rev-parse --show-toplevel` 找 git 根,等价于"cd 到项目根的语义"
- `start-server.sh --project-dir <path>` 把任意 path 当作项目根使用
- `tests/claude-code/test-sdd-workspace.sh:114-116` 测试 "linked worktree resolves its own distinct workspace" —— 证明每个 worktree 一个独立 `.superpowers/sdd/`

### Q2. 工作区目录结构

#### 仓库根(`clone/superpowers/`,superpowers 自身开发时)

| 路径 | 类型 | 作用 | 在哪段代码 / 命令被使用 |
|---|---|---|---|
| `skills/` | 目录(14 个 skill 子目录) | **核心资产**,所有 skill 定义,被 10 个宿主 agent 共享 | 全部 manifest 都引用 `./skills/`;OpenCode `superpowers.js:50`、`Pi` `superpowers.ts:17` |
| `hooks/` | 目录 | Shape A 宿主(Claude Code/Cursor/Copilot CLI)的 session-start 入口 | `hooks/hooks.json`(Claude)、`hooks/hooks-cursor.json`(Cursor),`run-hook.cmd` polyglot 包装器,`session-start` bash 脚本 |
| `.claude-plugin/`, `.codex-plugin/`, `.cursor-plugin/`, `.kimi-plugin/`, `gemini-extension.json`, `package.json`(pi) | 10 个 manifest | 每个宿主框架一个 | `package.json:9` `main` 指向 OpenCode 插件;`package.json:13-19` 声明 pi 扩展 + skills |
| `.opencode/plugins/superpowers.js` | JS 文件 | Shape B 宿主(OpenCode)in-process 插件 | `package.json:9 main` 字段;`tests/opencode/setup.sh:33-36` symlink 到 `$OPENCODE_CONFIG_DIR/plugins/` |
| `.pi/extensions/superpowers.ts` | TS 文件 | Shape B 宿主(Pi)in-process 扩展 | `package.json:14 pi.extensions` |
| `.agents/plugins/marketplace.json` | JSON | Claude Code 官方 marketplace 元数据 | `README.md:79` 引用 |
| `scripts/` | 4 个 shell | `bump-version.sh`(版本管理)、`sync-to-codex-plugin.sh`(codex fork 同步)、`package-codex-plugin.sh`、`lint-shell.sh` |  |
| `docs/`, `docs/superpowers/plans/`, `docs/superpowers/specs/` | markdown | 项目自身的设计文档和 plan(spec 是设计、plan 是实施) | `docs/porting-to-a-new-harness.md` 700 行 |
| `tests/` | 大量测试 | per-harness 集成测试(Claude Code/Cursor/OpenCode/Pi/Kimi/Codex/Antigravity/hooks) | `tests/run-all.sh` 顶层入口 |
| `GEMINI.md` | markdown | Shape C 宿主(Gemini)的 `@`-include bootstrap 文件 | `gemini-extension.json:5` `contextFileName: "GEMINI.md"` |
| `AGENTS.md`, `CLAUDE.md`, `gemini-extension.json`, `package.json` | 根 metadata | 项目元数据 | `AGENTS.md` 一行引用 `CLAUDE.md`;`CLAUDE.md` 100+ 行是贡献者铁律 |
| `assets/` | 图片 | logo/icon | `.codex-plugin/plugin.json:38-39` 引用 |
| `.gitignore` | 5 行 | 把 `.superpowers/`、`.worktrees/`、`.private-journal/` 等都排除 | `clone/superpowers/.gitignore:1-9` |
| `.version-bump.json` | JSON | 7 个 manifest 文件的版本号同步管理 | `scripts/bump-version.sh` |

#### 项目级 `<repo>/.superpowers/`(运行时由 skills 隐式创建)

| 路径 | 创建者 | 用途 | git 状态 |
|---|---|---|---|
| `.superpowers/sdd/` | `skills/subagent-driven-development/scripts/sdd-workspace:14-20`(SDD 流程开始时) | SDD 的工作目录,装 task brief / implementer report / review diff / progress ledger | git-ignored(脚本自动写 `.gitignore: *` 在该目录内) |
| `.superpowers/sdd/progress.md` | SDD skill 主动写入(`SKILL.md:254`) | 跨 compaction 的进度 ledger | 同上 |
| `.superpowers/sdd/task-<N>-brief.md` | `scripts/task-brief:31-33` | 从 plan.md 抽出来的单个 task 文本,给 implementer subagent 读 | 同上 |
| `.superpowers/sdd/review-<base7>..<head7>.diff` | `scripts/review-package:43-45` | 给 reviewer subagent 读的 diff 包 | 同上 |
| `.superpowers/sdd/task-<N>-report.md` | implementer 写(`SKILL.md:243-245`) | implementer 的回执报告 | 同上 |
| `.superpowers/brainstorm/<SESSION_ID>/` | `skills/brainstorming/scripts/start-server.sh:117` | 视觉伴侣(visual companion)的服务端状态/HTML mockup 存储 | git-ignored(README 提示用户加 `.superpowers/` 到 `.gitignore`) |
| `.superpowers/brainstorm/.last-port`, `.last-token` | `start-server.sh:120-121` | 持久化绑定端口和会话 token,支持重启 | 同上 |

证据链:
- `tests/claude-code/test-sdd-workspace.sh:39-58` 测试 `.superpowers/sdd/` 的存在、自屏蔽、git 不可见
- `tests/claude-code/test-sdd-workspace.sh:80-105` 测试 task-brief 和 review-package 默认写入 `.superpowers/sdd/`
- `RELEASE-NOTES.md:36` 解释为什么从 `.git/sdd/` 搬到 `.superpowers/sdd/`:Claude Code 把 `.git/` 当受保护路径,implementer subagent 写不进去

#### 项目根其他被 superpowers 影响的目录

| 路径 | 作用 | 证据 |
|---|---|---|
| `.worktrees/<branch>/` | git worktree fallback 目录(`using-git-worktrees` skill 用) | `using-git-worktrees/SKILL.md:75-78` |
| `.private-journal/` | superpowers 自身仓库开发时 Jesse 的私有笔记(已 git-ignore) | `.gitignore:2` |
| `docs/superpowers/specs/`, `docs/superpowers/plans/` | superpowers 自身仓库的设计 spec + 实施 plan(用 writing-plans skill 产出) | `docs/superpowers/specs/2026-*.md` |

### Q3. 工作区创建:init 显式初始化 vs 隐式创建?

**答:完全隐式,没有任何 `superpowers init` 命令**。

#### 安装(全局 skills 库)阶段 —— 由宿主 agent 触发

用户**只跑宿主 agent 的安装命令**,从不动 superpowers 的文件:

| 宿主 | 用户实际输入的命令 | 证据 |
|---|---|---|
| Claude Code | `/plugin install superpowers@claude-plugins-official` | `README.md:81-83` |
| Cursor | `/add-plugin superpowers` | `README.md:121-123` |
| Factory Droid | `droid plugin marketplace add https://github.com/obra/superpowers` + `droid plugin install superpowers@superpowers` | `README.md:135-140` |
| OpenCode | 在 `opencode.json` 注册 plugin URL,或 `pi install git:github.com/obra/superpowers` | `README.md:163-172`、`docs/README.opencode.md` |
| Kimi Code | `/plugins install https://github.com/obra/superpowers` | `README.md:151-155` |
| Pi | `pi install git:github.com/obra/superpowers` | `README.md:177-180` |
| Antigravity | `agy plugin install https://github.com/obra/superpowers` | `README.md:99-105` |
| Codex | `/plugins` → 搜 `superpowers` → Install | `README.md:111-117` |
| Gemini | `gemini extensions install https://github.com/obra/superpowers` | `docs/porting-to-a-new-harness.md:11-15` |

**没有**任何 superpowers 自己的二进制 / CLI / 安装脚本(除了 `scripts/` 下 4 个用于**自身开发**的 shell 工具)。

#### 项目级 `<repo>/.superpowers/` —— 完全按需隐式创建

```bash
# 调用方从来不写 mkdir -p .superpowers,是 skill 脚本自己做:
skills/subagent-driven-development/scripts/sdd-workspace:19-22
  mkdir -p "$dir"
  printf '*\n' > "$dir/.gitignore"     # 顺便自屏蔽

skills/brainstorming/scripts/start-server.sh:117-132
  SESSION_DIR="${PROJECT_DIR}/.superpowers/brainstorm/${SESSION_ID}"
  mkdir -p "${SESSION_DIR}/content" "$STATE_DIR"
```

调用链路:
1. 用户说 "Let's make a react todo list" 触发 brainstorming skill
2. brainstorming 内部可能调用 `start-server.sh --project-dir .` 创建 `.superpowers/brainstorm/`
3. 后续 SDD 流程时,sdd-workspace 创建 `.superpowers/sdd/`
4. **整个过程用户不需要也不应该预先 mkdir .superpowers**

#### "我 git clone 之后是不是要手动 cp skills 到 ~/.superpowers/?"

**绝对不要**。`CLAUDE.md:170-175` 明确说这是 "not a real integration":
> These are not real integrations and will be closed:
> - Manually copying skill files into the harness
> - Wrapping with `npx skills` or similar at-runtime shims
> - Anything that requires the user to opt in to skills per-session
> - Anything where `brainstorming` does not auto-trigger on the acceptance test above

**所以旧版可能存在的 `~/.superpowers/` 路径(以及 `~/.config/superpowers/skills/`)是已废弃的遗留布局**,`tests/hooks/test-session-start.sh:194` 在测试 "obsolete legacy custom-skill warning" 时专门断言它**不应该**出现在 session-start 输出里。

## 3. 关键代码片段(可选)

### 3.1 单一 bootstrap 入口(Claude Code/Cursor/Copilot CLI 共用)

`clone/superpowers/hooks/session-start:1-65` —— 整个 superpowers 的灵魂:读 `skills/using-superpowers/SKILL.md`,按宿主环境变量选 JSON 形状,塞进 `<EXTREMELY_IMPORTANT>` 包装输出。

```bash
# 行 9-10:plugin 根从 hook 自身位置反推(不依赖宿主环境变量)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# 行 12:读 using-superpowers 的内容
using_superpowers_content=$(cat "${PLUGIN_ROOT}/skills/using-superpowers/SKILL.md" 2>&1 || echo "Error reading using-superpowers skill")

# 行 39-50:三选一,根据环境变量切 JSON 形状
if [ -n "${CURSOR_PLUGIN_ROOT:-}" ]; then
  printf '{\n  "additional_context": "%s"\n}\n' "$session_context" | cat
elif [ -n "${CLAUDE_PLUGIN_ROOT:-}" ] && [ -z "${COPILOT_CLI:-}" ]; then
  printf '{\n  "hookSpecificOutput": { "hookEventName": "SessionStart", "additionalContext": "%s" }\n}\n' "$session_context" | cat
else
  printf '{\n  "additionalContext": "%s"\n}\n' "$session_context" | cat
fi
```

### 3.2 显式随项目根走的 SDD workspace

`clone/superpowers/skills/subagent-driven-development/scripts/sdd-workspace:1-22`

```bash
root=$(git rev-parse --show-toplevel)   # 跟随当前 git 仓库
dir="$root/.superpowers/sdd"             # 路径写死,没环境变量 override
mkdir -p "$dir"
printf '*\n' > "$dir/.gitignore"         # 自屏蔽,不污染 git status
cd "$dir" && pwd
```

### 3.3 跨 worktree 隔离

`tests/claude-code/test-sdd-workspace.sh:113-125` 验证:
> linked worktree resolves its own distinct workspace — `wt_dir == "$wt_root/.superpowers/sdd" && "$wt_dir" != "$dir"`

意味着 git worktree 切分支时,每个 worktree 都有自己的 `.superpowers/sdd/`,互不串扰。

## 4. 与 Onion Agent 设计的关联

(按 Onion Agent "session.json 为核心,围绕它的多模型 + sub-agent + 工具" 哲学评估)

### 4.1 superpowers 给 Onion Agent 的**反例**(避坑)

| 维度 | superpowers 做法 | Onion Agent 应该怎么做 | 原因 |
|---|---|---|---|
| **session 上下文存储** | 没有 session.json,所有"状态"散落在 `<repo>/.superpowers/sdd/{progress.md, task-N-brief.md, task-N-report.md, review-X..Y.diff}` 等多个文件 | Onion Agent 的 session.json 应该**单一文件**累加器,所有状态(state machine: system/user/assistant/tool/plan/loop)在一个文件里 | superpowers 的多文件导致"progress ledger 可能在 compaction 后与 git log 错位"(`RELEASE-NOTES.md:36` 警告 `git clean -fdx` 会删 ledger),Onion Agent 的单文件更稳 |
| **sub-agent 上下文传递** | sub-agent 通过**文件交接**(`task-brief.md` 抽出来,`review-package.diff` 抽出来)而不是粘贴进 dispatch prompt | 借鉴 superpowers 的"文件 handoff"思想,但 Onion Agent 可以更优雅 —— sub-agent 直接读主 session.json 的某个 namespace 切片 | 减少"controller 上下文污染"(`subagent-driven-development/SKILL.md:8-12` 反复强调) |
| **bootstrap 注入** | 每个宿主一个 manifest,workaround 10 种注入方式 | 如果 Onion Agent 限定为单一宿主,可以做到一次性 `session_init` 注入,无需 multi-harness 抽象 | superpowers 的复杂度来自 10 个宿主适配,Onion Agent 没这负担 |
| **progress ledger vs todos** | 用 markdown 文件 `progress.md` 持久化 + `git log` 双源,避免 compaction 丢失 | 借鉴 —— session.json 里"持久化 todo 区"和"短期 todo 区"分离,前者永不被压缩 | `subagent-driven-development/SKILL.md:251-263` 解释了为什么单一信源(对话)不够 |

### 4.2 superpowers 给 Onion Agent 的**可借鉴模式**

1. **git worktree 跟随**:`sdd-workspace` 用 `git rev-parse --show-toplevel` 自动找 git 根 —— 跟 Onion Agent "进入目录就识别"的需求天然契合,不需要 init
2. **自屏蔽目录**:`.superpowers/sdd/.gitignore` 内容是 `*`,一个文件就让整个目录对 git 不可见,简单优雅
3. **plugin 化的 skills 注册**:skills 不放在 superpowers 名下,而是装进宿主位置 —— 但 Onion Agent 既然是单一产品,可以更直接 —— skill 目录是 Onion Agent 自己仓库的固定路径(比如 `~/.onion/skills/`),不抽象成 "plugin"
4. **零运行时依赖**:superpowers 整个项目零 npm 依赖(只有 4 个 dev 工具脚本),纯 markdown + bash + 单个 JS/TS 文件 —— 这与 Onion Agent 想要"奥卡姆剃刀"哲学一致
5. **测试驱动 + 进度 ledger 双轨**:`test-driven-development` skill + `progress.md` ledger,避免 "compaction 后重做已完成任务" —— Onion Agent 的 session.json 天然可以做这件事,无需额外文件

### 4.3 关键差异:superpowers 是"插件",Onion Agent 是"产品"

superpowers 的设计目标是**作为 plugin 嫁接到已有 agent**,所以所有 manifest/install 机制都围绕"宿主 agent 怎么发现我"展开,这是**多宿主兼容性**的代价。Onion Agent 是**自研单一产品**,可以直接:
- `~/.onion/session.json` 作为全局活跃 session
- `<repo>/.onion/` 作为项目级 scratch(借鉴 superpowers 的 `.superpowers/sdd/` 模式)
- `~/.onion/skills/` 作为全局 skills 库(自己说了算,不需要 10 个 manifest)

## 5. 不确定 / 未找到

1. **是否存在"全局 settings.json"** —— 没找到 superpowers 自己的 `~/.superpowers/config.yaml` 或类似配置入口;所有配置都是宿主 agent 提供的(比如 OpenCode 的 `OPENCODE_CONFIG_DIR`)
2. **多宿主并存时,skills 优先级如何** —— 看到 `tests/opencode/test-priority.sh` 这个测试名,但没深挖;推测是 harness 自管,不是 superpowers 自己处理
3. **legacy 路径 `~/.config/superpowers/skills/`** 在新版是否还有兼容逻辑 —— 测试断言"不应出现在 warning 里",但没看到"如果存在则忽略"之类的 fallback 代码
4. **`.superpowers/` 在多 host(Claude Code + Cursor 同时跑同一项目)并发写** 是否会冲突 —— 没看到文件锁逻辑,推测依赖 OS 文件系统行为或 git worktree 隔离

---

**调研完成时间**:基于 `clone/superpowers` 当前 `main` 分支(版本 6.1.1,见 `package.json:3`)
