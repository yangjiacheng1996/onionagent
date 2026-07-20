# sst/opencode — 工作区(File Backend)调研报告

> 调研对象:[sst/opencode](https://github.com/sst/opencode)(已迁移至 `anomalyco/opencode`,v1.18.3)
> 调研时间:2026-07-17
> 源码路径:`C:\workspace\github\onionagent\harness\01_market_research\clone\opencode\`
> 报告路径:`C:\workspace\github\onionagent\harness\01_market_research\Opencode\file_backend.md`

---

## 0. 智能体一句话定位

**100% 开源 + Provider 无关的终端编码 Agent**:TypeScript + Effect 框架,Client/Server 架构,内置 `build` 和 `plan` 两个原生 primary agent(以及 `general`、`explore` 两个 subagent),通过 SQLite 持久化 session/项目状态,通过 XDG Base Directory 规范管理全局/缓存/数据,工作区默认**跟随当前工作目录**(这一点与 Cline/Aider 一致,与 AutoGPT 的固定 `~/auto-gpt.json` 形成关键差异)。

---

## 1. 调研依据

| 类型 | 路径 | 关键内容 |
| --- | --- | --- |
| 全局路径常量 | `packages/core/src/global.ts` | XDG data / cache / config / state / tmp 路径,模块加载时 `mkdir -p` 全部建好 |
| 项目解析 | `packages/core/src/project.ts` | `Project.resolve()` 根据 git remote / commit hash / 缓存文件计算项目 ID |
| 项目 Service | `packages/opencode/src/project/project.ts` | `Project.fromDirectory()` 是 entry point,SQLite upsert |
| 工作区路径解析 | `packages/opencode/src/cli/cmd/tui.ts` | `resolveThreadDirectory()` 决定 TUI 启动目录 |
| 配置路径 | `packages/opencode/src/config/paths.ts` | `directories()` 返回 4 层配置搜索路径 |
| 配置加载 | `packages/opencode/src/config/config.ts` | 按 4 层目录顺序 merge 配置文件 + agent/command/skill/plugin |
| 环境变量开关 | `packages/core/src/flag/flag.ts` | `OPENCODE_CONFIG_DIR` / `OPENCODE_CONFIG` / `OPENCODE_DB` / `OPENCODE_TEST_HOME` / `OPENCODE_DISABLE_PROJECT_CONFIG` 等 |
| 数据库 | `packages/core/src/database/database.ts` | SQLite 文件路径,可被 `OPENCODE_DB` 覆盖 |
| 旧版文件存储 | `packages/opencode/src/storage/storage.ts` | 历史 JSON 文件存储,有迁移机制(已逐步迁移到 SQLite) |
| Server 路由 | `packages/server/src/location.ts` | HTTP API 的多实例支持:`x-opencode-directory` header 或 `?location[directory]=` |
| 原生 agent 定义 | `packages/opencode/src/agent/agent.ts` | `build` / `plan` / `general` / `explore` / `compaction` |
| 实例上下文 | `packages/opencode/src/project/instance-context.ts` | `{ directory, worktree, project }` 三元组 |
| Git worktree | `packages/opencode/src/worktree/index.ts` | `git worktree` 存放在 `Global.Path.data + "/worktree/<projectID>"` |
| LSP server 二进制 | `packages/opencode/src/lsp/server.ts` | 全部下载到 `Global.Path.bin` |
| Snapshot | `packages/opencode/src/snapshot/index.ts` | `<data>/snapshot/<projectID>/<worktree-hash>/` |
| 项目实例 `.opencode/` 实物 | `clone/opencode/.opencode/` | 真实样例,展示该目录的所有子目录 |
| `acp` 命令 | `packages/opencode/src/cli/cmd/acp.ts` | 唯一带 `--cwd` flag 的命令(默认 `process.cwd()`) |
| 命令加载 | `packages/opencode/src/config/command.ts` | `Glob.scan("{command,commands}/**/*.md", { cwd: dir })` |
| Agent 加载 | `packages/opencode/src/config/agent.ts` | `Glob.scan("{agent,agents}/**/*.md", { cwd: dir })` |
| Skill 发现 | `packages/opencode/src/skill/discovery.ts` | 远程 skill 缓存到 `Global.Path.cache + "/skills"` |
| Agent 创建(用户视角) | `packages/opencode/src/cli/cmd/agent.ts` | 交互式创建 agent,目标路径:项目 `<worktree>/.opencode/agents/` 或全局 `~/.config/opencode/agents/` |

---

## 2. 三个核心问题的回答

### Q1. 工作区路径

**结论:opencode 默认跟随当前工作目录**(关键设计),可通过多种方式自定义。

#### 1.1 默认行为:`process.cwd()`

| 入口 | 代码位置 | 行为 |
| --- | --- | --- |
| TUI 命令 | `packages/opencode/src/cli/cmd/tui.ts:66` | `export function resolveThreadDirectory(project?: string, envPWD = process.env.PWD, cwd = process.cwd())` — 当未传入 `project` 参数时,直接返回 `Filesystem.resolve(cwd)` |
| HTTP Server | `packages/server/src/location.ts:34` | `(request.headers["x-opencode-directory"] ? decode(...) : process.cwd())` — 每次请求若未携带 header,默认 `cwd` |
| ACP 命令 | `packages/opencode/src/cli/cmd/acp.ts:14` | `.option("cwd", { ..., default: process.cwd() })` |

**核心调用链**:
```
TUI [project] arg
  └─> tui.ts:164  resolveThreadDirectory(args.project)
        └─> tui.ts:66  cwd = process.cwd()
        └─> InstanceRuntime.load({ directory })
              └─> bootstrap.ts:4
                    └─> bootstrap.ts:3  context.provide(ctx, cb)
                          └─> InstanceContext { directory, worktree, project }
```

#### 1.2 自定义方式

| 优先级 | 方式 | 代码 | 效果 |
| --- | --- | --- | --- |
| 1 | TUI 位置参数 | `tui.ts:54` `command: "$0 [project]"` | `opencode /path/to/project` → 工作区为该绝对路径(或相对 `cwd` 的相对路径) |
| 2 | `--cwd` 标志 | `acp.ts:14` `.option("cwd", ...)` | **仅 `acp` 子命令支持**,主 TUI 没有 |
| 3 | `OPENCODE_CONFIG_DIR` | `global.ts:71` `config: Flag.OPENCODE_CONFIG_DIR ?? Path.config` | 覆盖**全局**配置目录(不影响项目根) |
| 4 | `OPENCODE_CONFIG` | `config.ts:21, 256, 401` | 指定**单文件**配置(可与目录配置叠加) |
| 5 | `OPENCODE_DB` | `database.ts:30` | 覆盖**数据库**文件路径(支持 `:memory:`、绝对路径、或相对 `data` 目录) |
| 6 | `OPENCODE_TEST_HOME` | `global.ts:18` | 覆盖 `home` 目录(测试用) |
| 7 | `OPENCODE_DISABLE_PROJECT_CONFIG=1` | `flag.ts:54` + `paths.ts:21` | 禁用项目级配置搜索,只用全局 |
| 8 | HTTP 头 `x-opencode-directory` | `server/src/location.ts:32-35` | **server 模式下**每个请求指定不同工作区(多实例并发) |
| 9 | Query 参数 `?location[directory]=...` | `server/src/location.ts:33` | 同上,优先级高于 header |

#### 1.3 与"固定属主目录"模式的对比

| 智能体 | 模式 | 路径 |
| --- | --- | --- |
| **opencode** | **跟随 cwd**(默认) | `process.cwd()` 或 `args.project` |
| AutoGPT | 固定属主目录 | `~/.auto-gpt/` |
| Cline | 跟随 cwd(IDE 内) | VSCode 当前工作区 |
| Aider | 跟随 cwd | `git rev-parse --show-toplevel` |
| Claude Code | 跟随 cwd | `process.cwd()` |

> **核心洞察**:opencode 的 "workspace" 实际上是**项目目录**(`directory`),不是 "opencode 自己的属主目录"。所有 agent 操作、权限边界、LSP root、snapshot 都基于这个 `directory` 派生(详见 Q2.2 实例上下文)。

---

### Q2. 工作区目录结构

opencode 区分**项目级**(跟 cwd 走)、**全局级**(XDG 标准)、**数据级**(SQLite)三层。下面按层次列出。

#### 2.1 项目级(跟 cwd 走)

**搜索算法**:`FSUtil.up({ targets: [".opencode"], start: directory, stop: worktree })`(`paths.ts:23-27`)— 从 `directory` 向上逐层找 `.opencode/`,直到 `worktree`(即 git root)或文件系统根。

| 路径(相对项目根) | 来源 | 作用 | 加载方式 |
| --- | --- | --- | --- |
| `opencode.json` / `opencode.jsonc` | 实物:项目根可有可无 | 主配置文件(项目级 override) | `ConfigPaths.files("opencode", directory, worktree)`(`paths.ts:9-16`)向上搜索,合并到全局配置 |
| `.opencode/opencode.json` / `.opencode.jsonc` | 实物:`clone/opencode/.opencode/opencode.jsonc` | 同上的另一种位置 | 同上 |
| `.opencode/agent/*.md` 或 `.opencode/agents/*.md` | 实物:`clone/opencode/.opencode/agent/{duplicate-pr,triage}.md` | 自定义 agent 定义(markdown + frontmatter) | `ConfigAgent.load(dir)` → `agent.ts:13` `Glob.scan("{agent,agents}/**/*.md", { cwd: dir })` |
| `.opencode/command/*.md` 或 `.opencode/commands/*.md` | 实物:`clone/opencode/.opencode/command/{commit,changelog,...}.md` | 自定义 slash command | `ConfigCommand.load(dir)` → `command.ts:12` `Glob.scan("{command,commands}/**/*.md", { cwd: dir })` |
| `.opencode/skill/<name>/SKILL.md` | 实物:`clone/opencode/.opencode/skills/effect/SKILL.md` | Skills 入口(可附其他文件) | `Skill.Service` 加载,详见 `skill/discovery.ts:104` |
| `.opencode/plugin/*` 或 `.opencode/plugins/*` | 实物:`clone/opencode/.opencode/plugins/{smoke-theme.json,tui-smoke.tsx}` | 插件 JS/TS 文件 | `ConfigPlugin.load(dir)`,由 `npm install @opencode-ai/plugin` 自动安装运行时依赖 |
| `.opencode/tool/*` | 实物:`clone/opencode/.opencode/tool/{github-pr-search,github-triage}.ts` | 自定义 tool(TS 文件) | 插件机制加载 |
| `.opencode/theme/*` 或 `.opencode/themes/*` | 实物:`clone/opencode/.opencode/themes/mytheme.json` | TUI 主题 | 主题加载器 |
| `.opencode/glossary/<lang>.md` | 实物:`clone/opencode/.opencode/glossary/zh-cn.md` 等 18 种语言 | 多语言术语表 | 翻译相关 |
| `.opencode/.gitignore` | 实物存在 | 由 opencode 自动写入(包含 `node_modules` 等) | `config.ts:441` `ensureGitignore(dir)` |
| `.opencode/env.d.ts` | 实物存在 | TypeScript 类型声明(给插件用) | — |
| `<git-root>/opencode`(无扩展名) | — | **项目 ID 缓存文件** | `project.ts:73-80` `cached()` 读此文件,内容是项目 ID |
| `<git-root>/.git/` | 系统 | git 仓库;opencode 通过 `git.repo.discover(directory)` 探测 | `project.ts:101` `yield* git.repo.discover(input)` |

**实物 `.opencode/` 目录样例**(直接来自 clone):
```
.opencode/
├── .gitignore
├── env.d.ts
├── opencode.jsonc           # 项目级配置
├── tui.json                 # TUI 配置
├── agent/                   # 原生 agent
│   ├── duplicate-pr.md
│   └── triage.md
├── command/                 # 原生 slash command
│   ├── ai-deps.md
│   ├── changelog.md
│   ├── commit.md
│   ├── issues.md
│   ├── learn.md
│   ├── rmslop.md
│   ├── spellcheck.md
│   └── translate.md
├── glossary/                # 18 种语言的术语表
│   ├── README.md
│   ├── zh-cn.md, zh-tw.md, ja.md, ko.md, ...
├── plugins/
│   ├── smoke-theme.json
│   └── tui-smoke.tsx
├── skills/
│   └── effect/
│       └── SKILL.md
├── themes/
│   ├── .gitignore
│   └── mytheme.json
└── tool/
    ├── github-pr-search.ts
    └── github-triage.ts
```

#### 2.2 实例上下文(运行时核心)

`packages/opencode/src/project/instance-context.ts:3-7` 定义:
```typescript
export interface InstanceContext {
  directory: string   // 用户启动时的 cwd(或 [project] 参数)
  worktree: string    // git root;非 git 项目时 = "/"
  project: Project.Info  // { id, worktree, vcs, sandboxes, ... }
}
```

**作用域**:通过 Effect 的 `LocalContext` 在整个 instance 内可见(`instance-context.ts:9`),所有 service(LSP / Agent / Snapshot / Worktree ...) 都通过 `InstanceState.context` 拿到(`instance-state.ts:18-22`)。

#### 2.3 全局级(XDG Base Directory)

依据 `packages/core/src/global.ts:5-9`:
```typescript
const data = path.join(xdgData!, app)    // XDG_DATA_HOME/opencode 或 ~/.local/share/opencode
const cache = path.join(xdgCache!, app)  // XDG_CACHE_HOME/opencode 或 ~/.cache/opencode
const config = path.join(xdgConfig!, app) // XDG_CONFIG_HOME/opencode 或 ~/.config/opencode
const state = path.join(xdgState!, app)  // XDG_STATE_HOME/opencode 或 ~/.local/state/opencode
const tmp = path.join(os.tmpdir(), app)  // $TMPDIR/opencode
```

| 路径(相对 HOME) | 关键文件/子目录 | 用途 | 来源 |
| --- | --- | --- | --- |
| `~/.config/opencode/` | `config.json`(legacy)、`opencode.json`、`opencode.jsonc`、`.opencode/{agent,command,skill,...}/` | **全局配置** + **全局 agent/command/skill/tool 覆盖** | `config.ts:258-260, 399` + `paths.ts:24` + `agent.ts:111` |
| `~/.config/opencode/agents/` | 自定义全局 agent(由 `opencode agent create` 创建) | `agent.ts:111` `targetPath = path.join(scope === "global" ? Global.Path.config : ..., "agents")` |
| `~/.local/share/opencode/` | 全部持久化数据(下面展开) | `global.ts:5` |
| `~/.local/share/opencode/auth.json` | 认证凭证 | `auth/index.ts:10` `path.join(Global.Path.data, "auth.json")` |
| `~/.local/share/opencode/opencode.db` | **主 SQLite 数据库** | `database.ts:43-46` `join(Global.Path.data, "opencode.db")`(channel 不同时为 `opencode-<channel>.db`) |
| `~/.local/share/opencode/log/` | 日志 | `global.ts:13` `log: path.join(data, "log")` |
| `~/.local/share/opencode/storage/` | **旧版** JSON 文件存储(`session/<id>.json`、`message/<id>/<msgId>.json`、`part/<msgId>/<partId>.json`、`session_diff/<id>.json`),有迁移机制 | `storage.ts:151` `path.join(Global.Path.data, "storage")`,迁移走 `MIGRATIONS[0..]` |
| `~/.local/share/opencode/plans/` | plan mode 写入的 markdown 计划 | `agent.ts:169` `[path.join(Global.Path.data, "plans", "*")]: "allow"` |
| `~/.local/share/opencode/snapshot/<projectId>/<worktree-hash>/` | 文件快照(roll back 用) | `snapshot/index.ts:71` `path.join(Global.Path.data, "snapshot", ctx.project.id, Hash.fast(ctx.worktree))` |
| `~/.local/share/opencode/worktree/<projectId>/` | git worktree 临时目录 | `worktree/index.ts:208` `path.join(Global.Path.data, "worktree", ctx.project.id)` |
| `~/.local/share/opencode/repos/` | 用于 share 功能的 git clone 缓存 | `global.ts:14` `repos: path.join(data, "repos")` |
| `~/.local/state/opencode/` | flock 状态 | `global.ts:6, 16` `Flock.setGlobal({ state })` |
| `~/.cache/opencode/bin/` | LSP server 二进制:`vscode-eslint/`、`gopls`、`rubocop`、`elixir-ls` | `lsp/server.ts:180, 186, 382, 405, 414, 536` `path.join(Global.Path.bin, ...)` |
| `~/.cache/opencode/skills/<name>/` | 远程下载的 skill(`.opencode-version` 标记版本) | `skill/discovery.ts:35, 79, 80, 105` |
| `$TMPDIR/opencode/` | 临时文件 | `global.ts:7, 15` |

#### 2.4 配置层级合并(4 层,后覆盖前)

依据 `packages/opencode/src/config/paths.ts:18-31` 的 `directories()`:
```typescript
unique([
  Global.Path.config,                                 // (1) 全局配置 ~/.config/opencode
  ...(yield* afs.up({                                  // (2) 从 cwd 向上到 worktree 的所有 .opencode/
    targets: [".opencode"],
    start: directory,
    stop: worktree,
  })),
  ...(yield* afs.up({                                  // (3) HOME 下的 .opencode/
    targets: [".opencode"],
    start: Global.Path.home,
    stop: Global.Path.home,
  })),
  ...(Flag.OPENCODE_CONFIG_DIR ? [Flag.OPENCODE_CONFIG_DIR] : []),  // (4) env 覆盖
])
```

合并顺序见 `config.ts:415-444`(注意是**后加载的覆盖先加载的**),merge 算法用 `mergeDeep`(`config.ts:18`)。

#### 2.5 SQLite 表结构(项目元数据)

依据 `packages/core/src/project/sql.ts:7-26` + `database.ts:24-39`:
```sql
-- 主项目表
project (
  id            TEXT PRIMARY KEY,    -- 来自 git remote hash / root commit / 缓存
  worktree      TEXT NOT NULL,        -- 绝对路径,git root
  vcs           TEXT,                 -- "git" 或 NULL
  name          TEXT,
  icon_url      TEXT,
  icon_url_override TEXT,
  icon_color    TEXT,
  time_created  INTEGER,
  time_updated  INTEGER,
  time_initialized INTEGER,           -- 首次 /init 命令触发
  sandboxes     TEXT NOT NULL,        -- JSON 数组
  commands      TEXT                  -- JSON
)

-- 项目目录(multi-checkout 支持)
project_directory (
  project_id    TEXT REFERENCES project(id) ON DELETE CASCADE,
  directory     TEXT NOT NULL,        -- 绝对路径
  type          TEXT,                 -- 'main' | 'root' | 'git_worktree'
  strategy      TEXT,
  time_created  INTEGER NOT NULL,
  PRIMARY KEY (project_id, directory)
)
```

**项目 ID 解析规则**(`packages/core/src/project.ts:99-109`):
1. 若 `git.repo.discover(input)` 成功 → 走 git 模式
2. 缓存文件 `<git-common-dir>/opencode` 中的 ID(`cached()`,line 73-80)
3. `git remote get-url` → `host/pathname` 标准化 → `Hash.fast("git-remote:" + normalized)`(`remote()`,line 82-88)
4. `git rev-list --max-parents=0 --all` 取最小 root commit hash(`root()`,line 101-104)
5. 非 git 目录 → `ID.global`(单例)和 `directory = filesystem root("/")`

**Session 表**(`packages/core/src/session/sql.ts`,精简):
```sql
session (
  id            TEXT PRIMARY KEY,
  project_id    TEXT REFERENCES project(id),
  parent_id     TEXT,                 -- fork 时链接到父 session
  title         TEXT,
  agent         TEXT,                 -- 'build' | 'plan' | 'general' | ... 或自定义
  model         TEXT,                 -- JSON
  directory     TEXT NOT NULL,        -- session 起始目录
  workspace_id  TEXT,
  path          TEXT,                 -- subpath
  revert        TEXT,                 -- JSON
  time_created  INTEGER, time_updated INTEGER, time_archived INTEGER,
  tokens_*, cost, ...
)
```

#### 2.6 多 Agent 存储

**原生 5 个 agent**(硬编码在 `packages/opencode/src/agent/agent.ts:138-218`):

| Name | Mode | Native | Hidden | 关键行为 |
| --- | --- | --- | --- | --- |
| `build` | `primary` | ✓ | — | **默认 agent**,所有工具可执行 |
| `plan` | `primary` | ✓ | — | **只读模式**,所有 `edit` 工具 deny,允许写 `.opencode/plans/*.md` |
| `general` | `subagent` | ✓ | — | 通用子 agent,`todowrite` deny |
| `explore` | `subagent` | ✓ | — | 只读探索,`*` deny 但 `grep`/`glob`/`list`/`bash`/`webfetch`/`websearch`/`read` allow |
| `compaction` | `primary` | ✓ | ✓ | 上下文压缩专用,UI 隐藏 |

> 用户在 TUI 中通过 **Tab 键**在 `build` ↔ `plan` 之间切换(README.md:96-104)。

**用户自定义 agent 存储位置**(`agent.ts:111`):
- 项目级:`<worktree>/.opencode/agents/<name>.md`
- 全局级:`<Global.Path.config>/agents/<name>.md`(即 `~/.config/opencode/agents/`)

**Provider 配置**:`provider/provider.ts`(由 `Config` 加载,无独立目录,走 `~/.config/opencode/opencode.jsonc` 里的 `provider` 字段)。

**LSP 配置**:无独立文件,语言→server 映射内置在 `lsp/server.ts`(如 TypeScript→typescript-language-server、Go→gopls、Ruby→rubocop、Elixir→elixir-ls,二进制全部下载到 `~/.cache/opencode/bin/`)。

---

### Q3. 工作区创建

**结论:opencode 没有任何 `opencode init` 命令;项目/工作区是**完全隐式创建**的**,由 `Project.fromDirectory` 触发。

#### 3.1 没有 `init` 子命令

证据:全代码库 grep `command: "init"` 和 `describe: "init"` **0 命中**。所有 CLI 子命令见 `packages/opencode/src/cli/cmd/`:

```
acp, agent, attach, db, export, generate, github, import, mcp, models,
plug, pr, providers, run, serve, session, stats, tui, uninstall, upgrade, web
```

唯一接近"init"语义的是 `agent.ts` 子命令 `opencode agent create`(`agent.ts:255` `command: "agent"`),但它创建的是 agent 定义文件,不是工作区。

#### 3.2 隐式创建的工作流

**触发点**:任何 CLI 命令入口都会经过 `bootstrap(directory, cb)`(`cli/bootstrap.ts:3-5`):
```typescript
export async function bootstrap<T>(directory: string, cb: () => Promise<T>) {
  const ctx = await InstanceRuntime.load({ directory })
  try { return await context.provide(ctx, cb) }
  finally { await InstanceRuntime.disposeInstance(ctx) }
}
```

**步骤分解**(`project.ts:171-260` `Project.fromDirectory`):

| # | 动作 | 代码 | 说明 |
| --- | --- | --- | --- |
| 1 | **Git 探测** | `project.ts:101` `git.repo.discover(input)` | 若失败,ID = `global`,`directory = "/"`(此时 worktree = "/") |
| 2 | **ID 计算** | `project.ts:101-109` | 优先 remote hash → 缓存文件 → root commit |
| 3 | **DB upsert** | `project.ts:224-241` | 写入/更新 `project` + `project_directory` 表 |
| 4 | **Sandbox 维护** | `project.ts:205-218` | 同一项目多 checkout 路径自动登记为 sandbox |
| 5 | **Session 重绑** | `project.ts:243-250` | 历史上以 `global` 写入的 session,自动迁移到新 projectID |
| 6 | **Git 缓存写入** | `project.ts:255-257` | `<git-common-dir>/opencode` 写 ID 缓存(仅 git 仓库) |
| 7 | **首次初始化标记** | `project.ts:265-275` `setInitialized` | 监听 `Command.Default.INIT` 事件(用户执行 `/init` slash command),写 `time_initialized` |
| 8 | **依赖自动安装** | `config.ts:447-461` | 在每个 `.opencode/` 目录**后台** `npm install @opencode-ai/plugin`,失败仅 warning |
| 9 | **`.gitignore` 自动写入** | `config.ts:441` `ensureGitignore(dir)` | 让 `.opencode/node_modules` 等不入版本控制 |
| 10 | **TUI/server bootstrap** | `bootstrap.ts:23-30` | 拉起 LSP / Snapshot / VCS / Project / Share / Format / Plugin |

**显式入口**:`opencode agent create`(可选)— 在没有 `.opencode/` 的项目里也会先 `mkdir -p` 目标目录,这是**唯一**会"显式创建项目级 `.opencode/` 子目录"的用户操作(但仍然不创建工作区本身)。

**`.opencode/` 目录本身**也是**隐式创建**的:首次 `opencode /path/to/project` 启动后,`config.ts:441` `ensureGitignore` 会创建,加上 `config.ts:447` 触发 `npm install` 时也会创建。**用户从未运行过任何 `init` 命令**。

#### 3.3 显式 git init(可选用)

`Project.initGit`(`project.ts:277-285`)提供"把当前目录变成 git 仓库并重新解析项目"的能力,但需要**显式调用**(目前仅供 server API 或未来 `opencode init --git` 使用,CLI 没暴露)。

#### 3.4 关键约束

- **多 cwd = 多项目**:同一个用户,从 `~/repos/foo` 和 `~/repos/bar` 启动 opencode,会得到**两个独立项目**(即便 git remote 相同,因 `directory` 不同 → 走 `project_directory` 表区分)。
- **删除项目**:`Project.removeSandbox` 存在但 CLI 没暴露,只能直接 `sqlite3 ~/.local/share/opencode/opencode.db "DELETE FROM project WHERE id = '...'"`。
- **禁用项目配置**:`OPENCODE_DISABLE_PROJECT_CONFIG=1` → `paths.ts:21` 直接跳过 `.opencode/` 搜索,只用全局。
- **清空全局状态**:删除 `~/.config/opencode` + `~/.local/share/opencode` + `~/.cache/opencode` 三件套即可重置。

---

## 3. 关键代码片段(摘录)

### 3.1 全局路径(XDG 规范 + 启动时全建好)

```typescript
// packages/core/src/global.ts:5-9
const app = "opencode"
const data = path.join(xdgData!, app)    // ~/.local/share/opencode
const cache = path.join(xdgCache!, app)  // ~/.cache/opencode
const config = path.join(xdgConfig!, app) // ~/.config/opencode
const state = path.join(xdgState!, app)  // ~/.local/state/opencode
const tmp = path.join(os.tmpdir(), app)  // $TMPDIR/opencode
```

```typescript
// packages/core/src/global.ts:35-42  (顶层 await,模块加载即建好)
await Promise.all([
  fs.mkdir(Path.data, { recursive: true }),
  fs.mkdir(Path.config, { recursive: true }),
  fs.mkdir(Path.state, { recursive: true }),
  fs.mkdir(Path.tmp, { recursive: true }),
  fs.mkdir(Path.log, { recursive: true }),
  fs.mkdir(Path.bin, { recursive: true }),
  fs.mkdir(Path.repos, { recursive: true }),
])
```

### 3.2 工作区路径解析(TUI 入口)

```typescript
// packages/opencode/src/cli/cmd/tui.ts:66-69
export function resolveThreadDirectory(project?: string, envPWD = process.env.PWD, cwd = process.cwd()) {
  const root = Filesystem.resolve(envPWD ?? cwd)
  if (project) return Filesystem.resolve(path.isAbsolute(project) ? project : path.join(root, project))
  return Filesystem.resolve(cwd)
}
```

### 3.3 Server 模式多实例(每个请求一个 cwd)

```typescript
// packages/server/src/location.ts:32-39
const directory =
  query.get("location[directory]") ||
  (request.headers["x-opencode-directory"] ? decode(request.headers["x-opencode-directory"]) : process.cwd())
return Location.Ref.make({
  directory: AbsolutePath.make(directory),
  workspaceID: workspaceID ? WorkspaceV2.ID.make(workspaceID) : undefined,
})
```

### 3.4 配置目录搜索(4 层)

```typescript
// packages/opencode/src/config/paths.ts:18-31
export const directories = Effect.fn("ConfigPaths.directories")(function* (directory: string, worktree?: string) {
  const afs = yield* FSUtil.Service
  return unique([
    Global.Path.config,                                            // (1) 全局
    ...(!Flag.OPENCODE_DISABLE_PROJECT_CONFIG
      ? yield* afs.up({ targets: [".opencode"], start: directory, stop: worktree })  // (2) 项目级(向上)
      : []),
    ...(yield* afs.up({ targets: [".opencode"], start: Global.Path.home, stop: Global.Path.home })),  // (3) HOME
    ...(Flag.OPENCODE_CONFIG_DIR ? [Flag.OPENCODE_CONFIG_DIR] : []),  // (4) env 覆盖
  ])
})
```

### 3.5 原生双 agent(CLI 视角)

```typescript
// packages/opencode/src/agent/agent.ts:141-181
const agents: Record<string, Info> = {
  build: {
    name: "build",
    description: "The default agent. Executes tools based on configured permissions.",
    mode: "primary",  // 用户在 TUI 中 Tab 切到 plan
    native: true,
  },
  plan: {
    name: "plan",
    description: "Plan mode. Disallows all edit tools.",
    mode: "primary",
    native: true,
  },
  general: { mode: "subagent", native: true },  // @general
  explore: { mode: "subagent", native: true },  // @explore
  compaction: { mode: "primary", native: true, hidden: true },
}
```

---

## 4. 与 Onion Agent 设计的关联

Onion Agent 哲学是"**一切围绕 session.json 上下文历史文件**",Agent Loop 是其"自动累加器"。基于 opencode 的实现,以下是值得参考 / 避坑的点。

### 4.1 可借鉴的设计

| opencode 实践 | Onion Agent 可借鉴 |
| --- | --- |
| **XDG Base Directory 标准**(`global.ts:5-9`) | Onion Agent 也应分 `~/.config/onion/`(配置/全局 state) + `~/.local/share/onion/`(数据) + `~/.cache/onion/`(缓存),跨平台一致(Linux 遵循 XDG,Windows/Mac 自动 fallback 到 HOME 子目录) |
| **项目 ID 三段式**(git remote → 缓存文件 → root commit) | Onion Agent 也可用类似 `git remote URL` 派生 ID,让同一仓库在不同机器上的 project_id 一致,便于跨设备 session 同步 |
| **配置多层 merge**(全局 → 项目 .opencode/ → HOME → env) | Onion Agent 的"洋葱层"非常适合这个:从最外层(全局)到最内层(项目)层层 override。env 变量作为最后覆盖层也合理 |
| **隐式 bootstrap**(`bootstrap.ts:3-5`) | Onion Agent 不必强制 `init`,首次进入项目即"发现"项目。降低用户认知负担 |
| **per-instance 上下文**(`instance-context.ts`) | Onion Agent 也可以把 `directory` 提升为一等公民,整个 Agent Loop 围绕它派生 worktree / sandboxes / 权限边界 |
| **命令/agent/plugin 通过文件目录动态发现**(`agent.ts:13` `Glob.scan`) | Onion Agent 的 "Onion Layers" 完全可以映射到文件系统目录:每层一个目录,层内文件是 plugin 入口 |
| **SQLite 单文件 + WAL 模式**(`database.ts:24-28`) | Onion Agent 的 session 持久化如果用 SQLite + WAL,既快又便于备份(`cp opencode.db backup.db`) |
| **数据/缓存/配置严格分离** | Onion Agent 的 "session 文件" 应该放 `data`,**绝不**和 `config` 混;skill/plugin 缓存放 `cache` |

### 4.2 需要规避的问题

| opencode 的痛点 | Onion Agent 教训 |
| --- | --- |
| **配置层级 4 层 + 5 个 env 变量**(`flag.ts:21-64`) | 不要让用户记 5 个 env var。Onion Agent 应收敛到 1-2 个,如 `ONION_HOME`(改 HOME) + `ONION_PROJECT`(改 cwd) |
| **`opencode` 二进制名冲突**:`core/src/global.ts:5` `const app = "opencode"` 与 npm 包同名 | Onion Agent 的内部目录名应避免和包名相同,例如 `~/.local/share/onion-agent/` |
| **项目 ID 解析有歧义**(`project.ts:99-109`):git 失败时 → `ID.global`,directory = `/`,导致 `containsPath` 必须特殊处理(`instance-context.ts:18-22`) | Onion Agent 应**强制**要求项目根(用 git 根或 `.onion/` 标记),不要 fallback 到文件系统根 |
| **`.opencode/` 名字冲突**:很多项目已经用 `.opencode/`(OpenAPI 的标准目录名) | Onion Agent 推荐用 `.onion/` 或更独特的名字(避免和 OpenAPI 规范冲突) |
| **每个 `.opencode/` 都要 `npm install`**:首启慢 + 离线不能用(`config.ts:447-461`) | Onion Agent 的 plugin 加载不要依赖 npm,要么 pre-bundle 要么走 git submodule |
| **TUI 命令 `[project]` 位置参数 + `cwd` 兜底**:`tui.ts:164` vs `tui.ts:200` vs `tui.ts:208` 多处重复 `resolveThreadDirectory` | Onion Agent 应在 entry point 一次确定 `directory`,后续所有 service 直接拿,不要每次重新解析 |
| **Server 模式用 header 传 cwd**(`server/src/location.ts:34`)导致前端必须知道 header 名 | Onion Agent 如果做 server 模式,API 设计上建议用 URL path(`/projects/{path}/...`)而非 header,可读性更好 |
| **没有 `init` 命令,但 `ensureGitignore` + `npm install` 副作用很重** | Onion Agent 如果要 init,应该**显式 opt-in**(`onion init`),不要让首次启动就 `npm install` |

### 4.3 关键对比表

| 维度 | opencode | Onion Agent 建议 |
| --- | --- | --- |
| 工作区 = ? | `process.cwd()`(默认) | 同 opencode,跟随 cwd(底层一致) |
| 配置目录 | `~/.config/opencode/` | `~/.config/onion-agent/`(避免冲突) |
| 数据目录 | `~/.local/share/opencode/opencode.db` | `~/.local/share/onion-agent/sessions/`(存真正的 `session.json`) |
| 项目标记目录 | `.opencode/` | `.onion/` |
| 项目 ID 派生 | git remote hash | 同(可加 onion 自己的 manifest 文件) |
| 多 agent | `build` + `plan` + 2 subagent(硬编码 + `.opencode/agents/*.md`) | 同(可考虑加 `explore` 之外更多 subagent) |
| 显式 init | ❌ 不需要 | 同(隐式创建) |
| 持久化 | SQLite + WAL | **JSON Lines + 定期 snapshot**(更符合"洋葱"哲学)或 SQLite 视情况 |
| 上下文历史 | session 表(message/part 子表) | `session.json` 单文件,Agent Loop 即累加器 |

---

## 5. 不确定 / 未找到

1. **`x-opencode-directory` header 之外的备用方式**:`location.ts:32-39` 列了 `?location[directory]=`、header、`process.cwd()` 三层,但没找到 cookie / body 形式 — 推测不需要。
2. **`<git-common-dir>/opencode` 缓存文件的创建时机**:`project.ts:255-257` `projectV2.commit` 在每次 `fromDirectory` 都执行,但只有在 `vcs?.type === "git"` 才调用,所以非 git 仓库不写。无显式 `commit` 命令。
3. **`storage/` 旧版目录何时被完全淘汰**:`storage.ts:151` 还在用,`MIGRATIONS` 只到 index 1(迁移到 SQLite 已完成),推测新版本逐步退役,本次调研时间点(v1.18.3)应该已经完全可走 SQLite,但代码里仍保留 `MIGRATIONS[1]`(`session_diff` 拆分)。
4. **CLI v2 重构**:`packages/cli/src/commands/commands.ts` 已经定义新 `api` / `migrate` / `service` / `serve` 子命令,推测 v1 命令(`tui` 等)即将废弃。本次调研以 v1 路径(`packages/opencode/src/cli/cmd/`)为权威。
5. **`OPENCODE_EXPERIMENTAL_WORKSPACES`**(`flag.ts:50`)暗示未来会有 "workspace" 概念(不只是 project),可能是 worktree 的 UI 化抽象,但本次未深挖。
6. **首次 `time_initialized` 触发**(`project.ts:275`):监听 `Command.Default.INIT` 事件,即用户在 TUI 输入 `/init` slash command 时触发,但**未找到** `/init` 的 command 定义文件 — 推测是内置命令(类似 `/init` 触发 AGENTS.md / CLAUDE.md 生成,但 opencode 走的是 `setInitialized` 仅打时间戳)。

---

> **调研完成时间**:2026-07-17
> **下一步**:如需把 opencode 的 4 层配置 + SQLite + Tab 切换双 agent 模式映射到 Onion Agent 的"洋葱层"设计中,可基于本报告的 §4.1 / §4.2 提炼具体 schema。
