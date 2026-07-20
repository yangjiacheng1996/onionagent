# Cline — 工作区(File Backend)调研报告

> 调研对象: `cline/cline` (本仓库路径 `clone/cline/`)
> 调研时间: 2026-07
> 仓库定位: monorepo,主分支已重构为 `apps/{cli, vscode, cline-hub, examples, vscode-rollout}` + `sdk/packages/{shared, core, llms, ...}` + `docs/ evals/ assets/`,本报告聚焦工作区 / 文件后端层。

---

## 0. 智能体一句话定位

**Cline = 自主编码 Agent 的三形态 SDK/IDE/CLI** —— Plan/Act 双模式、任何 OpenAI 兼容 API + 本地模型、文件后端存储统一在 `~/.cline/data/`,跨 VSCode / JetBrains / CLI / Desktop 共享。

---

## 1. 调研依据

### 1.1 主要源码文件(行号 `path:line`,相对仓库根 `clone/cline/`)

| 主题 | 文件 | 说明 |
|---|---|---|
| 存储架构文档 | `.clinerules/storage.md` | 顶层 storage 设计要点 |
| 路径解析 SDK | `sdk/packages/shared/src/storage/paths.ts` | 全部 CLINE_*_DIR 环境变量、`.clinerules/.cline/.agents` 搜索路径 |
| StorageContext 入口 | `apps/vscode/src/shared/storage/storage-context.ts` | `createStorageContext()` 跨平台统一 |
| 文件后端实现 | `apps/vscode/src/shared/storage/ClineFileStorage.ts` | 同步 JSON 键值,原子写 |
| VSCode 启动 | `apps/vscode/src/extension.ts` | `activate()` 流程:HostProvider → createStorageContext → exportVSCodeStorageToSharedFiles |
| VSCode → 文件迁移 | `apps/vscode/src/hosts/vscode/vscode-to-file-migration.ts` | 老 ExtensionContext → `~/.cline/data/` |
| 通用 init | `apps/vscode/src/common.ts` | `initialize(storageContext)` |
| StateManager | `apps/vscode/src/core/storage/StateManager.ts` | 内存缓存 + 500ms debounce 落盘 |
| 旧 disk.ts | `apps/vscode/src/core/storage/disk.ts` | 兼容 `globalStorageFsPath/tasks/` 和 `~/Documents/Cline/` |
| 旧 path setup | `apps/vscode/src/standalone/vscode-context.ts` | CLI 形态下也走 `~/.cline/data/` |
| CLI 入口 | `apps/cli/src/main.ts` | `--config` / `--data-dir` / `--cwd` / `--acp-mode` / `--worktree` 全部 CLI 选项 |
| CLI 沙箱环境 | `apps/cli/src/utils/helpers.ts` | `resolveWorkspaceRoot`(git toplevel) + `configureSandboxEnvironment` |
| CLI Session 抽象 | `apps/cli/src/session/session.ts` | 调用 `ClineCore.create()`,走 `~/.cline/data/db/sessions.db` |
| Session store | `sdk/packages/core/src/services/storage/sqlite-session-store.ts` | SQLite 会话存储 |
| Team store | `sdk/packages/core/src/services/storage/sqlite-team-store.ts` | 团队状态 |
| 状态键注册 | `apps/vscode/src/shared/storage/state-keys.ts` | 全部 globalState / secrets / localState 键名 |

### 1.2 仓库内项目级配置(`.clinerules/`)

```
.clinerules/
├── hooks/README.md
├── workflows/{address-pr-comments, find-pr-reviewers, git-branch-analysis,
│              hotfix-release, pr-review, release, writing-documentation}.md
├── bun-and-node.md
├── cline-overview.md
├── debug-harness.md
├── general.md
├── network.md
├── protobuf-development.md
├── sdk-migration.md
└── storage.md          ← 本报告核心参考
```

Cline **自己用 `.clinerules/` 作为项目级 rules 目录**,相当于它**自己也是 .clinerules 的遵循者**,起到了 self-dogfooding 作用。

---

## 2. 三个核心问题的回答

### Q1. 工作区路径

Cline 的"工作区"概念在 **3 个平台** 上分别处理,统一收敛到 `~/.cline/data/` 文件后端。

#### 1.1 各形态的工作区路径来源

| 形态 | 工作区路径如何确定 | 关键代码 |
|---|---|---|
| **VSCode 扩展** | 来自 VSCode 自身的 `vscode.workspace.workspaceFolders[0].uri.fsPath`(多根工作区时取第一个);为空时回退到 `process.cwd()` | `apps/vscode/src/extension.ts:81` `const workspacePath = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath` |
| **JetBrains 插件** | 通过 `WORKSPACE_STORAGE_DIR` 环境变量 **直接覆盖** workspaceStorage 路径(不参与 hash 计算) | `apps/vscode/src/shared/storage/storage-context.ts:18-23` `if (opts.workspaceStorageDir) { workspaceDir = opts.workspaceStorageDir }` |
| **CLI 形态** | 三种来源按优先级:① `--cwd <path>` ② `--worktree` 创建后的新路径 ③ `process.cwd()`;然后调 `resolveWorkspaceRoot()` 跑 `git rev-parse --show-toplevel` 找到 git 根 | `apps/cli/src/utils/helpers.ts:43-54` `git -C cwd rev-parse --show-toplevel` |
| **Desktop 示例** | 跟 VSCode 走相同 SDK | `apps/examples/desktop-app/sidecar/...` |

> 注意: Cline 的工作区存储 **不是写死在 `~/.cline/`**,而是用 **8 字符 hash** 编码到 `~/.cline/data/workspaces/<hash>/workspaceState.json`,hash 来自工作区绝对路径(见 Q2.1)。

#### 1.2 全局数据目录(`~/.cline/`)的可配置入口

Cline 用了**三套并列的覆盖机制**,优先级从高到低:

| 来源 | 代码位置 | 生效时机 |
|---|---|---|
| `--config <dir>` CLI 参数 → `setClineDir(dir)`(全局变量) | `apps/cli/src/main.ts:140-143` | 早于任何 storage 读取 |
| `CLINE_DIR` 环境变量 | `sdk/packages/shared/src/storage/paths.ts:80-83` | 兜底默认 |
| `~/` 来自 `setHomeDir()` / `HOME` / `USERPROFILE` / `HOMEDRIVE+HOMEPATH` | `sdk/packages/shared/src/storage/paths.ts:24-50` | 终极兜底 |
| **JetBrains**:`WORKSPACE_STORAGE_DIR` | `storage-context.ts:18-23` | 跳过 hash,直接用 |
| **CLI 沙箱模式**:`--data-dir <dir>` 或 `CLINE_SANDBOX=1` | `apps/cli/src/utils/helpers.ts:382-399` | 同时设置 `CLINE_SANDBOX_DATA_DIR / CLINE_DATA_DIR / CLINE_DB_DATA_DIR / CLINE_SESSION_DATA_DIR / CLINE_TEAM_DATA_DIR / CLINE_PROVIDER_SETTINGS_PATH / CLINE_HOOKS_LOG_PATH` |

> `resolveClineDir()` 实现 (`paths.ts:79`): `if (CLINE_DIR) return CLINE_DIR; if (process.env.CLINE_DIR) return env; return join(HOME_DIR, ".cline")` — **三层兜底**。

#### 1.3 JetBrains 形态的差异

JetBrains 没有同仓库代码(`.gitmodules` 仅 `evals/cline-bench` 一个 submodule),但**协议层面**已抽象:
- 走 `WORKSPACE_STORAGE_DIR` 环境变量传 workspace 路径,绕过 hash
- 共享 `StorageContext` / `ClineFileStorage` 文件后端
- 注释里明说: `// TODO: Unify JetBrains workspace path scheme with the hash-based approach once the JetBrains client side is cleaned up.` (`storage-context.ts:23`)

#### 1.4 工作区路径解析流程图

```
┌─────────────────────────────────────────────────────────────────────┐
│ 启动形态判断(Host type)                                              │
│   VSCode ext  → vscode.workspace.workspaceFolders[0].uri.fsPath     │
│   JetBrains   → WORKSPACE_STORAGE_DIR env (跳过 hash)                │
│   CLI         → args.cwd ?? process.cwd() → resolveWorkspaceRoot()  │
│                 └─ git -C <cwd> rev-parse --show-toplevel           │
│ Desktop       → 跟 VSCode 走 SDK                                     │
└──────────────────┬──────────────────────────────────────────────────┘
                   │
                   ▼
        createStorageContext({ workspacePath, clineDir, workspaceStorageDir? })
                   │
        ┌──────────┴──────────────┐
        ▼                         ▼
 clineDir 解析              workspaceDir 解析
  ① opts.clineDir           ① opts.workspaceStorageDir (JetBrains)
  ② CLINE_DIR env           ② hash(workspacePath) [8 chars hex]
  ③ HOME/.cline             ③ 路径 = ${dataDir}/workspaces/${hash}
        │                         │
        └─────────┬───────────────┘
                  ▼
        mkdirSync(dataDir, recursive)
        mkdirSync(workspaceDir, recursive)
                  │
                  ▼
   ┌──────────────────────────────────┐
   │ ~/.cline/data/                   │  ← 全局共享
   │   globalState.json               │
   │   secrets.json  (mode 0o600)     │
   │   workspaces/<hash>/             │  ← per-workspace
   │     workspaceState.json          │
   └──────────────────────────────────┘
```

---

### Q2. 工作区目录结构

Cline 有 **两套并存** 的目录约定:① **新** `~/.cline/data/` 文件后端(共享层) ② **旧** `~/Documents/Cline/` 兼容层(给老用户)。加上 **项目级** `.clinerules` / `.cline` / `.agents`。

#### 2.1 完整文件布局表

| 路径 | 内容 | 用途 | 出现位置 |
|---|---|---|---|
| `~/.cline/` | 根目录 | 全部 Cline 状态的根 | `paths.ts:79-83` |
| `~/.cline/data/` | 主数据目录 | 跨平台共享文件后端 | `storage-context.ts:88` |
| `~/.cline/data/globalState.json` | 全局 KV | 应用设置、provider 配置、task 索引、UI 状态、远端配置等 | `storage-context.ts:94` |
| `~/.cline/data/secrets.json` | 密文 KV(`mode 0o600`) | API keys / OAuth tokens | `storage-context.ts:96-99` |
| `~/.cline/data/state/taskHistory.json` | 任务历史 | 单条记录(迁移自 VSCode legacy) | `legacy-state-reader.ts:31` |
| `~/.cline/data/settings/cline_mcp_settings.json` | MCP servers | 用户/远程 MCP 配置 | `paths.ts:228-231` `disk.ts:14` |
| `~/.cline/data/settings/providers.json` | provider 凭证 | CLI 启动时 `ProviderSettingsManager` 用 | `paths.ts:217-220` `helpers.ts:395` |
| `~/.cline/data/settings/global-settings.json` | 全局设置 | (CLI 沙箱模式覆盖用) | `paths.ts:223-225` |
| `~/.cline/data/workspaces/<hash>/workspaceState.json` | **per-workspace** 状态 | `localClineRulesToggles` / `localCursorRulesToggles` / `localWindsurfRulesToggles` / `localAgentsRulesToggles` / `localSkillsToggles` / `workflowToggles` | `storage-context.ts:108` `state-keys.ts:357-363` |
| `~/.cline/data/db/sessions.db` | SQLite | 会话元数据 + 消息 | `sqlite-session-store.ts:33-39` |
| `~/.cline/data/db/cron.db` | SQLite | cron / 计划任务 | `paths.ts:175-179` |
| `~/.cline/data/teams/` | 团队状态(legacy?) | 多 agent 协作 | `paths.ts:147-150` |
| `~/.cline/data/logs/hooks.jsonl` | 钩子日志 | Hooks 审计 trail | `helpers.ts:393` `paths.ts:540-546` |
| `~/.cline/cron/` | 定时任务文件 | `*.md` / `*.cron.md` / `events/*.event.md` | `paths.ts:181-183` |
| `~/.cline/agents/` | 全局 agent 配置 | 插件式 agent 定义 | `paths.ts:444` `disk.ts:159` |
| `~/.cline/hooks/` | 全局 hooks | 旧版 hooks 全局目录 | `paths.ts:451-453` |
| `~/.cline/skills/` | 全局 skills | skill 包 | `paths.ts:479-482` |
| `~/.cline/rules/` | 全局 rules | `.md` 格式 | `paths.ts:506-512` |
| `~/.cline/workflows/` | 全局 workflows | `.md` 格式 | `paths.ts:528-534` |
| `~/.cline/plugins/` | 全局 plugins | `package.json` manifest 驱动 | `paths.ts:540-542` |
| `~/.agents/` | **legacy** skills 目录 | 老 `~/.agents/skills/` | `paths.ts:18` |
| `~/.agents/AGENTS.md` | **legacy** 全局 rules | 老 `~/.agents/AGENTS.md` | `paths.ts:497-499` |
| `${globalStorageFsPath}/tasks/<taskId>/` | **VSCode legacy** 任务目录 | `api_conversation_history.json` / `ui_messages.json` / `context_history.json` / `task_metadata.json` | `disk.ts:9-18, 69-73` |
| `${globalStorageFsPath}/checkpoints/` | **VSCode legacy** git checkpoint | CLI 默认开启,Core 默认关闭 | `utils/storage.ts:11-17` |
| `${globalStorageFsPath}/settings/` | **VSCode legacy** 旧 settings | 旧版 `cline_mcp_settings.json` | `disk.ts:152-154` |
| `${globalStorageFsPath}/cache/` | **VSCode legacy** 缓存 | 推荐模型、网关模型等 | `disk.ts:213-215` |
| `~/Documents/Cline/Rules/` | **legacy 兼容** 旧全局 rules | `ensureRulesDirectoryExists` | `disk.ts:75-83` |
| `~/Documents/Cline/Workflows/` | **legacy 兼容** 旧全局 workflows | `ensureWorkflowsDirectoryExists` | `disk.ts:85-93` |
| `~/Documents/Cline/MCP/` | **legacy 兼容** 旧 MCP servers | `ensureMcpServersDirectoryExists` | `disk.ts:95-103` |
| `~/Documents/Cline/Hooks/` | **legacy 兼容** 旧 hooks | `ensureHooksDirectoryExists` | `disk.ts:105-113` |
| `<workspace>/.clinerules/` | **项目级** rules/skills/workflows/hooks (deprecated) | 兼容老格式,新格式已迁移到 `.cline/` | `disk.ts:15-22` `paths.ts:17` |
| `<workspace>/.clinerules/AGENTS.md` | 项目级 rules(单文件) | | `paths.ts:24` `disk.ts:25` |
| `<workspace>/.clinerules/rules/` | 项目级 rules 目录 | | `paths.ts:17` |
| `<workspace>/.clinerules/workflows/` | 项目级 workflows | | `disk.ts:16` `paths.ts:527` |
| `<workspace>/.clinerules/hooks/` | 项目级 hooks | | `disk.ts:17` `paths.ts:447-453` |
| `<workspace>/.clinerules/skills/` | 项目级 skills (deprecated) | | `disk.ts:18` `paths.ts:471-477` |
| `<workspace>/.cline/` | **新项目级** 目录 | 替代 `.clinerules/` | `paths.ts:18` |
| `<workspace>/.cline/skills/` | 新项目级 skills | | `disk.ts:19` `paths.ts:473` |
| `<workspace>/.cline/rules/` | 新项目级 rules | | `paths.ts:503-509` |
| `<workspace>/.cline/workflows/` | 新项目级 workflows | | `paths.ts:530-533` |
| `<workspace>/.cline/agents/` | 新项目级 agent | | `paths.ts:441-445` |
| `<workspace>/.cline/plugins/` | 新项目级 plugins | | `paths.ts:540-541` |
| `<workspace>/.cline/cron/` | 项目级 cron(预留) | | `paths.ts:188-190` |
| `<workspace>/AGENTS.md` | 项目级 rules(顶级单文件) | | `paths.ts:24, 499-502` |
| `<workspace>/.claude/skills/` | Claude skills 兼容 | | `disk.ts:20` |
| `<workspace>/.agents/skills/` | legacy 项目级 skills | | `disk.ts:21` `paths.ts:18` |
| `<workspace>/.cursor/rules/` | Cursor rules 兼容 | | `disk.ts:22` |
| `<workspace>/.cursorrules` | Cursor rules 兼容(单文件) | | `disk.ts:23` |
| `<workspace>/.windsurfrules` | Windsurf rules 兼容 | | `disk.ts:24` |

#### 2.2 关键 `globalState.json` 字段(节选)

来源: `apps/vscode/src/shared/storage/state-keys.ts`

- `clineVersion` / `cline.generatedMachineId` — 机器指纹
- `lastShownAnnouncementId` — 公告
- `taskHistory` (async) — `HistoryItem[]`
- `userInfo` / `favoritedModelIds`
- `mcpMarketplaceEnabled` / `mcpResponsesCollapsed`
- `terminalReuseEnabled` / `vscodeTerminalExecutionMode`
- `isNewUser` / `welcomeViewCompleted`
- `mcpDisplayMode` / `workspaceRoots` / `primaryRootIndex` / `multiRootEnabled`
- `lastDismissedInfoBannerVersion` / `lastDismissedModelBannerVersion` / `lastDismissedCliBannerVersion`
- `remoteRulesToggles` / `remoteWorkflowToggles` / `remoteSkillsToggles`
- `worktreeAutoOpenPath`
- 全套 `planMode*` / `actMode*` 配置(每个 provider × mode 各一组模型/思考预算/推理强度,见 `state-keys.ts:147-300+`)

#### 2.3 关键 `secrets.json` 字段(节选)

`SecretKeys` 包括: `apiKey`(各 provider) / `openAiApiKey` / `anthropicApiKey` / `openRouterApiKey` / `awsAccessKey` / `awsSecretKey` / `geminiApiKey` / `clineAccountId` / `openai-codex-oauth-credentials`(JSON blob) / `wandbApiKey` / ...

#### 2.4 关键 `workspaceState.json` 字段

`LocalStateKeys` (`state-keys.ts:357-363`):

```typescript
export const LocalStateKeys = [
    "localClineRulesToggles",    // .clinerules 内每个 rules 的启用/禁用
    "localCursorRulesToggles",   // .cursor/rules
    "localWindsurfRulesToggles", // .windsurfrules
    "localAgentsRulesToggles",   // AGENTS.md
    "localSkillsToggles",        // .cline/skills, .clinerules/skills
    "workflowToggles",           // .clinerules/workflows
] as const
```

> **重要洞察**: `localClineRulesToggles` / `localSkillsToggles` / `workflowToggles` 是用 workspace hash 隔离开的。**这意味着 plan/act 切换**、**rules 启用/禁用** 等都是 per-workspace 状态,不同的 git 仓库不会互相污染。

#### 2.5 任务历史 + 任务数据文件

每个 task 在 `${globalStorageFsPath}/tasks/<taskId>/` 下:
- `api_conversation_history.json` — Anthropic 格式
- `ui_messages.json` — UI 消息
- `context_history.json` — 上下文窗口历史
- `task_metadata.json` — `TaskMetadata { files_in_context, model_usage, environment_history }`

`taskHistory.json` 在 `~/.cline/data/state/` 下存索引(列表),实际数据在 `tasks/<id>/`。
> **注意**: `vscode-to-file-migration.ts:39-44` 明确说 `taskHistory` **还没** 迁移到 `~/.cline/data/`,目前仍是 per-VSCode 隔离的(有 `// TODO: Migrate taskHistory.json and task data files to ~/.cline/data/` 注释)。

#### 2.6 Plan/Act 模式如何存储

Cline **没有** 单一的 `mode` 全局字段;模式的状态分散在 `globalState` 的 per-provider × per-mode 字段(每个 provider 都有 `planModeXxxModelId/Info` 和 `actModeXxxModelId/Info` 一对字段)。运行时的"当前 mode"由 webview / TUI session 自身维护,不落盘。

`state-keys.ts:18` 显式声明:

```typescript
export type Mode = "plan" | "act"
```

这是"逻辑模式",不是存储字段。**plan/act 切换不直接写 `globalState.json`**;它只更新内存中的 `Mode` 状态,真正的差异是 system prompt 模板 + 工具策略(plan 模式禁写工具)。

#### 2.7 MCP / Skills / Hooks / Plugins 配置搜索路径

`paths.ts:430-540` 给出了非常详尽的搜索路径优先级(同名字段取首次命中、去重):

**Hooks**:
1. `~/Documents/Cline/Hooks`
2. `~/.cline/hooks`
3. `<workspace>/.clinerules/hooks`
4. `<workspace>/.cline/hooks`

**Skills**:
1. `<workspace>/.clinerules/skills` (deprecated)
2. `<workspace>/.cline/skills`
3. `<workspace>/.agents/skills` (legacy)
4. `~/.cline/skills`
5. `~/.agents/skills` (legacy)

**Rules**:
1. `<workspace>/AGENTS.md`(单文件,优先级最高)
2. `<workspace>/.clinerules`
3. `<workspace>/.cline/rules`
4. `~/.agents/AGENTS.md`
5. `~/.cline/rules`
6. `~/Documents/Cline/Rules`

**Workflows**:
1. `<workspace>/.clinerules/workflows`
2. `~/Documents/Cline/Workflows`
3. `~/.cline/workflows`
4. `<workspace>/.cline/workflows`

**Plugins**:
1. `<workspace>/.cline/plugins`
2. `~/.cline/plugins`
3. `~/Documents/Cline/Plugins`

**Agents**:
1. `<workspace>/.cline/agents`
2. `~/.cline/agents`

#### 2.8 整套目录结构一图

```
$HOME
├── .cline/                                    ← Cline 主目录
│   ├── data/                                  ← 文件后端(共享层)
│   │   ├── globalState.json                   ← 全局 KV
│   │   ├── secrets.json                       ← 0o600
│   │   ├── state/taskHistory.json
│   │   ├── settings/
│   │   │   ├── cline_mcp_settings.json
│   │   │   ├── providers.json
│   │   │   └── global-settings.json
│   │   ├── workspaces/<hash>/                 ← per-workspace (8 字符 hash)
│   │   │   └── workspaceState.json
│   │   ├── db/
│   │   │   ├── sessions.db                    ← SQLite
│   │   │   └── cron.db
│   │   ├── sessions/                          ← (legacy?)
│   │   ├── teams/                             ← 团队状态
│   │   └── logs/hooks.jsonl
│   ├── cron/                                  ← 定时任务规范文件
│   ├── agents/                                ← 全局 agent 配置
│   ├── hooks/                                 ← 全局 hooks
│   ├── skills/                                ← 全局 skills
│   ├── rules/                                 ← 全局 rules
│   ├── workflows/                             ← 全局 workflows
│   └── plugins/                               ← 全局 plugins
├── .agents/                                   ← legacy 全局层
│   ├── skills/
│   └── AGENTS.md
└── Documents/Cline/                           ← legacy 兼容层
    ├── Rules/
    ├── Workflows/
    ├── MCP/
    ├── Hooks/
    ├── Agents/                                ← 文档目录式
    └── Plugins/

${WORKSPACE_PATH}                              ← 用户的项目
├── .clinerules/                               ← deprecated 项目级
│   ├── AGENTS.md
│   ├── rules/
│   ├── workflows/
│   ├── hooks/
│   └── skills/
├── .cline/                                    ← 新项目级
│   ├── skills/
│   ├── rules/
│   ├── workflows/
│   ├── agents/
│   ├── plugins/
│   └── cron/
├── AGENTS.md                                  ← 顶级单文件 rules
├── .agents/skills/                            ← legacy 项目级
├── .claude/skills/                            ← Claude 兼容
├── .cursor/rules/                             ← Cursor 兼容
├── .cursorrules                               ← Cursor 兼容(单文件)
└── .windsurfrules                             ← Windsurf 兼容
```

---

### Q3. 工作区创建

Cline 的"工作区"不是被显式 init 的(没有 `cline init` 之类的命令);它**完全隐式创建** —— 每次启动根据 platform 决定路径,`mkdirSync({ recursive: true })` 即用即建。

#### 3.1 三种形态的 init 触发

| 形态 | 触发点 | 行为 |
|---|---|---|
| **VSCode 扩展** | ① VSCode 启动 → ② `activate(context)` → ③ `createStorageContext({ workspacePath })` → ④ `mkdirSync(dataDir, recursive)` + `mkdirSync(workspaceDir, recursive)` → ⑤ `exportVSCodeStorageToSharedFiles` 做一次性迁移(版本 sentinel 守护) | `extension.ts:79-83` |
| **CLI** | ① 命令行启动 → ② `runCli()` 解析 `--config` 调 `setClineDir(dir)` ③ `setHomeDir(homedir())` ④ `--data-dir` 调 `configureSandboxEnvironment` 设环境变量 ⑤ 各种 `resolve*Dir()` 在第一次读/写时 mkdir | `apps/cli/src/main.ts:138-147` `helpers.ts:382-399` |
| **JetBrains** | ① IDE 启动 → ② 设 `WORKSPACE_STORAGE_DIR` env ③ 走 `createStorageContext({ workspaceStorageDir: env })` 跳过 hash | `storage-context.ts:18-23` |

#### 3.2 隐式创建 vs 显式 init

- **没有** `cline init` 这种命令(`apps/cli/src/commands/` 下没有 init 子命令)
- **没有** `cline workspace create` 这种命令
- **没有** bootstrap / scaffold / setup wizard
- **唯一**显式"初始化"动作:VSCode 启动时的一次性迁移 `exportVSCodeStorageToSharedFiles`,由 sentinel `__vscodeMigrationVersion` 防重入
- **配置入口**在 CLI 是 `cline auth`、`cline config`、`cline mcp install`、`cline plugin install` —— 全部是 lazy 创建:执行到具体 `ensureXxxDirectoryExists` 时 `mkdir -p`

#### 3.3 关键代码:`createStorageContext` 的 mkdir 路径

```typescript
// apps/vscode/src/shared/storage/storage-context.ts:88-110
const clineDir = opts.clineDir || process.env.CLINE_DIR || path.join(os.homedir(), ".cline")
const dataDir = path.join(clineDir, SETTINGS_SUBFOLDER)  // SETTINGS_SUBFOLDER = "data"

let workspaceDir: string
if (opts.workspaceStorageDir) {
    workspaceDir = opts.workspaceStorageDir           // JetBrains 跳过 hash
} else {
    const workspacePath = opts.workspacePath || process.cwd()
    const workspaceHash = hashString(workspacePath)   // 8 字符 hex
    workspaceDir = path.join(dataDir, "workspaces", workspaceHash)
}

fsSync.mkdirSync(dataDir, { recursive: true })
fsSync.mkdirSync(workspaceDir, { recursive: true })
```

`hashString` 是个简单 32-bit Java-style hash(`storage-context.ts:54-65`),`Math.abs(hash).toString(16).substring(0, 8)`。**没有用 sha256 / md5**,好处是快、不依赖 crypto 模块,坏处是**有理论碰撞可能**(8 hex = 32 bits,空间 4.29B,但生日悖论下 65k 个 workspace 就有 50% 概率碰撞)。

#### 3.4 Sentinel 防重入机制

VSCode → `~/.cline/data/` 的一次性迁移用 **sentinel 守护**:

```typescript
// vscode-to-file-migration.ts:65-67
const MIGRATION_VERSION_KEY = "__vscodeMigrationVersion"   // 旧 key 名 "__migrationVersion"
const FILE_BACKED_STORAGE_EXPORT_VERSION = 1
const MCP_SETTINGS_MIGRATION_VERSION = 2
```

- 写 `globalState.__vscodeMigrationVersion = 2` 后,下次启动检测到 >= 当前版本即跳过
- workspace 状态有**独立 sentinel**,新工作区首次打开时会单独跑迁移
- **VSCode 旧 storage 不清除**(`vscode-to-file-migration.ts:23-25` 注释: "VSCode storage is NOT cleared, so older extension versions still work") —— 这是典型的**安全降级** 设计

#### 3.5 CLI 沙箱模式(sandbox)

最显式的"创建"动作是 `--data-dir` + `CLINE_SANDBOX=1`,会一次性设置 **6 个环境变量** (`helpers.ts:382-399`):

```typescript
process.env.CLINE_SANDBOX = "1"
process.env.CLINE_SANDBOX_DATA_DIR = dataDir
process.env.CLINE_DATA_DIR = dataDir
process.env.CLINE_DB_DATA_DIR = join(dataDir, "db")
process.env.CLINE_SESSION_DATA_DIR = join(dataDir, "sessions")
process.env.CLINE_TEAM_DATA_DIR = join(dataDir, "teams")
process.env.CLINE_PROVIDER_SETTINGS_PATH = join(dataDir, "settings", "providers.json")
process.env.CLINE_HOOKS_LOG_PATH = join(dataDir, "logs", "hooks.jsonl")
```

> 注释说: "Sandbox mode is enabled implicitly whenever --data-dir is provided, or when CLINE_SANDBOX=1 is set in the environment (in which case the data dir falls back to $CLINE_SANDBOX_DATA_DIR or /tmp/cline-sandbox)." —— **隐式** 行为。

#### 3.6 init 时序图

```
VSCode 启动
  ↓
extension.activate(context)            [extension.ts:74]
  ↓
setupHostProvider(context)             [extension.ts:75]
  │  └─ HostProvider.globalStorageFsPath = context.globalStorageUri.fsPath (legacy)
  ↓
cleanupLegacyVSCodeStorage(context)    [extension.ts:77]
  ↓
createStorageContext({ workspacePath }) [extension.ts:82]
  │  ├─ 读 opts.clineDir || CLINE_DIR || ~/.cline
  │  ├─ 读 opts.workspacePath || process.cwd()
  │  ├─ hash workspacePath
  │  └─ mkdirSync(dataDir), mkdirSync(workspaces/<hash>/)
  ↓
exportVSCodeStorageToSharedFiles       [extension.ts:83]
  │  ├─ 检查 __vscodeMigrationVersion
  │  ├─ if (无 sentinel) → batch 复制 globalState / secrets / workspaceState
  │  └─ 写 sentinel (FILE_BACKED_STORAGE_EXPORT_VERSION)
  ↓
initialize(storageContext)             [extension.ts:85, common.ts:38]
  │  ├─ Logger 订阅
  │  ├─ ClineEndpoint.initialize
  │  └─ StateManager.initialize(storageContext)  [StateManager.ts:120]
  │      ├─ readGlobalStateFromStorage
  │      ├─ readSecretsFromStorage
  │      ├─ readWorkspaceStateFromStorage
  │      └─ populateCache(...)
  ↓
WebviewProvider 创建 + 命令注册
```

---

## 3. 关键代码片段(摘录)

### 3.1 路径解析 SDK(单一权威)

```typescript
// sdk/packages/shared/src/storage/paths.ts:79-83
export function resolveClineDir(): string {
    if (CLINE_DIR) return CLINE_DIR;                  // ① setClineDir() 注入
    const envDir = process.env.CLINE_DIR?.trim();
    if (envDir) return envDir;                         // ② 环境变量
    return join(HOME_DIR, ".cline");                   // ③ 兜底
}
```

### 3.2 createStorageContext(三平台统一)

```typescript
// apps/vscode/src/shared/storage/storage-context.ts:84-110
export function createStorageContext(opts: StorageContextOptions = {}): StorageContext {
    const clineDir = opts.clineDir || process.env.CLINE_DIR || path.join(os.homedir(), ".cline")
    const dataDir = path.join(clineDir, SETTINGS_SUBFOLDER)   // "data"

    let workspaceDir: string
    if (opts.workspaceStorageDir) {
        workspaceDir = opts.workspaceStorageDir                // JetBrains 直传
    } else {
        const workspacePath = opts.workspacePath || process.cwd()
        const workspaceHash = hashString(workspacePath)        // 8 hex
        workspaceDir = path.join(dataDir, "workspaces", workspaceHash)
    }

    fsSync.mkdirSync(dataDir, { recursive: true })
    fsSync.mkdirSync(workspaceDir, { recursive: true })

    const globalState = new ClineFileStorage(path.join(dataDir, "globalState.json"), "GlobalState")
    return {
        globalState, globalStateBackingStore: globalState,
        secrets: new ClineFileStorage<string>(path.join(dataDir, "secrets.json"), "Secrets", { fileMode: 0o600 }),
        workspaceState: new ClineFileStorage(path.join(workspaceDir, "workspaceState.json"), "WorkspaceState"),
        dataDir, workspaceStoragePath: workspaceDir,
    }
}
```

### 3.3 CLI 工作区解析(git toplevel)

```typescript
// apps/cli/src/utils/helpers.ts:43-54
export function resolveWorkspaceRoot(cwd: string): string {
    const result = spawnSync("git", ["-C", cwd, "rev-parse", "--show-toplevel"], { encoding: "utf8" })
    if (result.status === 0) {
        const value = result.stdout.trim()
        if (value) return value
    }
    return cwd   // 非 git 仓库就回退到原 cwd
}
```

### 3.4 CLI 沙箱环境变量一次性注入

```typescript
// apps/cli/src/utils/helpers.ts:382-399
export function configureSandboxEnvironment(options: { enabled: boolean; cwd: string; explicitDir?: string }): string | undefined {
    if (!options.enabled) return undefined
    const dataDir = resolveSandboxDataDir(options.cwd, options.explicitDir)
    process.env.CLINE_SANDBOX = "1"
    process.env.CLINE_SANDBOX_DATA_DIR = dataDir
    process.env.CLINE_DATA_DIR = dataDir
    process.env.CLINE_DB_DATA_DIR = join(dataDir, "db")
    process.env.CLINE_SESSION_DATA_DIR = join(dataDir, "sessions")
    process.env.CLINE_TEAM_DATA_DIR = join(dataDir, "teams")
    process.env.CLINE_PROVIDER_SETTINGS_PATH = join(dataDir, "settings", "providers.json")
    process.env.CLINE_HOOKS_LOG_PATH = join(dataDir, "logs", "hooks.jsonl")
    return dataDir
}
```

### 3.5 VSCode 一次性迁移 sentinel

```typescript
// apps/vscode/src/hosts/vscode/vscode-to-file-migration.ts:65-67, 93-99
const MIGRATION_VERSION_KEY = "__vscodeMigrationVersion"
const FILE_BACKED_STORAGE_EXPORT_VERSION = 1
const MCP_SETTINGS_MIGRATION_VERSION = 2

const globalVersion = storage.globalState.get<number>(MIGRATION_VERSION_KEY)
const workspaceVersion = storage.workspaceState.get<number>(MIGRATION_VERSION_KEY)
const needGlobalMigration = globalVersion === undefined || globalVersion < FILE_BACKED_STORAGE_EXPORT_VERSION
// 策略: file store wins(已存在不覆盖),VSCode 旧 storage 不清(可降级)
```

### 3.6 StateManager 内存缓存 + 500ms debounce

```typescript
// apps/vscode/src/core/storage/StateManager.ts:60, 102-104
private workspaceStateCache: LocalState = {} as LocalState
private pendingWorkspaceState = new Set<LocalStateKey>()
private persistenceTimeout: NodeJS.Timeout | null = null
private readonly PERSISTENCE_DELAY_MS = 500
```

> **关键设计**: 单进程内存缓存,跨进程不感知 —— "If you have multiple VS Code windows open, each has its own StateManager instance with its own cache. Changing a setting (like plan/act mode) in Window A writes to disk, but Window B keeps using its cached value. Window B only sees the change after restart." (注释 `StateManager.ts:39-46`)

---

## 4. 与 Onion Agent 设计的关联

> Onion Agent 哲学: 一切围绕一个 `session.json` 上下文历史文件,Agent Loop 是 session 文件的自动累加器。

### 4.1 对 Onion 的可借鉴点

| Onion 当前 | Cline 的做法 | 借鉴建议 |
|---|---|---|
| 单 `session.json` 累加 | **5 层文件后端**:`globalState` / `secrets` / `workspaceState` / `tasks/<id>/` / `db/sessions.db` | Onion 可以在 session.json 旁边维护一个 `index.json` 索引,避免 session.json 过度膨胀 |
| 单一全局状态 | **per-workspace 状态 hash 隔离**:`workspaces/<8-hex-hash>/workspaceState.json` | Onion 应允许**多项目同时进行**,可以引入 `~/.onion/workspaces/<hash>/session-link.json` |
| 显式 init? | **完全隐式创建**:`mkdirSync({recursive:true})` + sentinel 防重入迁移 | Onion 可以采用同样策略:首次运行时 `mkdir ~/.onion/{data,sessions,logs,workspaces}`,sentinel 用 `~/.onion/.version` |
| 用户属主 `~/.onion/` | **三层兜底** `setClineDir()` > `CLINE_DIR` > `HOME/.cline` | Onion 同款设计,优先级: `setOnionDir()` 注入 > `ONION_DIR` env > `~/.onion` |
| 没有沙箱模式 | `--data-dir` 一键沙箱 + 6 个环境变量 | Onion 应原生支持"一次性会话"模式(`onion --ephemeral /tmp/xxx`) |
| 凭据混在 session.json | **`secrets.json` 独立 + 0o600 权限** | Onion 强烈建议拆分,API key 单独 `secrets.json` 0o600 |
| plan/act 状态全局 | Cline 把 mode 状态放在内存 + provider×mode 字段分散存储 | Onion 如果引入多模式,可以采用**同样的分散存储** |
| 老的项目级 `.clinerules/` + 新的 `.cline/` 并存 | Cline 维护了**3 套路径搜索**:`.clinerules` / `.cline` / `~/.agents` | Onion 不要走"双套"路线,启动时就强制**单一目录约定**(如 `.onion/`) |

### 4.2 Cline 的可规避问题

| 问题 | Cline 表现 | Onion 应规避 |
|---|---|---|
| **8-char hash 碰撞** | 32-bit Java hash,生日悖论 65k workspace 50% 碰撞 | 用 sha256 前 16 hex(64-bit)或 `nanoid(10)` |
| **历史包袱**: 6 套目录并存 | `~/.cline` / `~/.cline/data` / `~/.cline/cron` / `~/.cline/{agents,hooks,skills,rules,workflows,plugins}` + `~/Documents/Cline/` + `<workspace>/.clinerules` + `<workspace>/.cline` + `<workspace>/.agents` + `<workspace>/.claude` + `<workspace>/.cursor` + `<workspace>/.windsurfrules` + `<workspace>/AGENTS.md` | Onion 只保 **1 套**:`~/.onion/`(全局) + `<workspace>/.onion/`(项目) |
| **多实例 cache 不感知** | "Window B sees the change after restart" (`StateManager.ts:39-46`) | Onion session.json 是文件级真相源,内存只是 cache,启动时 reload |
| **taskHistory 没迁移** | `vscode-to-file-migration.ts:39-44` 明确 TODO | Onion 从 day-1 就把任务历史统一到 `~/.onion/data/tasks.json` |
| **AC 兼容乱** | 同时认 `.clinerules` / `.claude` / `.agents` / `.cursor` / `.windsurfrules` | Onion 不要兼容别人,自洽即可 |
| **State 字段过多** | `state-keys.ts` 单文件 600+ 行,LocalState + GlobalState + Secret + Settings 4 套并列 | Onion 用一个 `~/.onion/state.json` + 类型化 schema 即可 |
| **Plan/Act 模式无落盘** | mode 是运行时变量,关闭后丢失 | Onion 可以提供"模式持久化" 写到 `state.json.mode` |
| **`globalStorageFsPath` 残留** | VSCode 还在用旧 `context.globalStorageUri.fsPath` 存 tasks/ 和 checkpoints/ | Onion 不要做这种"半迁移"状态 |

### 4.3 关键架构洞察

1. **Cline 已经是事实上的"洋葱架构"** —— session + state + secrets + workspace 各自分文件,Agent Loop 是 state 的累加器(尽管实现是 in-memory cache + debounce)。
2. **Cline 把"工作区"概念彻底解耦** —— VSCode / JetBrains / CLI / Desktop 用不同方式传 workspace path,但全部走同一份 `StorageContext`。Onion 应学习这种"**接口稳定、实现可换**"的设计。
3. **Cline 在做"统一文件后端"** —— 把所有原来 VSCode 内部 SQLite 状态(`ExtensionContext` 背后是 `~/.vscode/...state.vscdb`) 抽到 `~/.cline/data/*.json`,跨平台共享。Onion 如果想跨 CLI / Web / IDE,这是必经之路。
4. **Cline 自己 dogfood `.clinerules/`** —— 仓库内的 `.clinerules/` 既是项目级 rules,也是给 AI 看的项目说明文档。Onion 也可以让 AI 维护自己的 `~/.onion/AGENT.md`。

---

## 5. 不确定 / 未找到

| # | 不确定点 | 备注 |
|---|---|---|
| 1 | JetBrains 形态的完整仓库代码 | 本仓库无 jetbrains/ 目录,只在注释里说 `WORKSPACE_STORAGE_DIR` 协议,推测是独立 repo |
| 2 | Desktop 形态(`apps/examples/desktop-app`)的工作区行为 | 仅看了 sidecar 入口,实际桌面端通过 electron context 走 StorageContext,未深挖 |
| 3 | Plan/Act 模式在 `globalState.json` 中是否有"上次模式" 字段 | 未发现 `mode` / `lastMode` 字段,推断 mode 仅运行时,重启不保留 |
| 4 | `~/.cline/data/tasks/<id>/` 实际是 legacy 还是新版路径 | 注释里明确 TODO migrate,但当前 VSCode 还在用 `globalStorageFsPath/tasks/`,没合到一起 |
| 5 | workspace hash 冲突实测 | 32-bit 空间,理论 65k workspace 50% 碰撞,但实际可能用了更长截断,需对照 hash 函数确认 |
| 6 | `~/.cline/cron/` 的实际触发机制 | 找到了路径解析,没找到 cron runner 入口;应该在 `sdk/packages/core/src/services/cron/` |
| 7 | CLI `--worktree` 的 worktree 数据是否落 `~/.cline/data/` | worktree 是 git 概念,临时分支在 `<workspace>/.git/worktrees/`,但 Cline 是否额外存状态未确认 |
| 8 | VSCode legacy `globalStorageFsPath` 完整内容 | `HostProvider.get().globalStorageFsPath` 是 VSCode 给的,实际是 `${HOME}/.config/Code/User/globalStorage/cline.cline/`(Linux) 或 `%APPDATA%/Code/User/globalStorage/cline.cline/`(Windows) |
| 9 | SDK 的 `cline/` npm package 与本仓库 cli/ vscode/ 的发布关系 | `sdk/packages/{core, shared, llms}` 是发布单元,vscode 和 cli 是消费者,需查根 `package.json` workspaces |
| 10 | `cline-hub` 的工作区 | 发现了 `apps/cline-hub`,是本地 daemon 形式,未深挖它和 CLI 的关系 |

---

## 附录:仓库根目录速览

```
Cline 仓库根 (clone/cline/)
├── .agents/                ← legacy 兼容
├── .changeset/             ← changesets
├── .claude/                ← Claude 相关
├── .cline/                 ← Cline 本地配置
│   └── skills/publish-cli/SKILL.md
├── .clinerules/            ← 项目级 AI rules ←← Cline 自己用
│   ├── hooks/README.md
│   ├── workflows/*.md (7 个)
│   └── *.md (8 个主题)
├── .codex/
├── .git/
├── .github/
├── .greptile/
├── .husky/
├── .kanban/                ← Kanban 多 agent 协作
├── .vscode/
├── apps/
│   ├── cli/                ← CLI 形态 (npm i -g cline)
│   ├── cline-hub/          ← 本地 daemon
│   ├── examples/           ← desktop-app, vscode 等示例
│   ├── vscode/             ← VSCode 扩展主包
│   └── vscode-rollout/     ← 发布版本切换
├── assets/                 ← 文档资源
├── docs/                   ← 文档
├── evals/                  ← 评估 (含 cline-bench submodule)
└── sdk/
    └── packages/
        ├── core/           ← ClineCore 核心运行时
        ├── shared/         ← storage / paths / config 等共享工具
        └── llms/           ← LLM 抽象
```
