# Gemini CLI — 工作区(File Backend)调研报告

> 调研对象:`google-gemini/gemini-cli`(v0.52.0-nightly.20260715,本仓库 snapshot)
> 调研维度:**File Backend** — 即工作区(workspace)是怎么识别的、目录长什么样、谁负责初始化。
> 调研路径:`C:\workspace\github\onionagent\harness\01_market_research\clone\gemini-cli`

---

## 0. 智能体一句话定位

Google 官方终端 Agent;`gemini` 二进制 + 互动 TUI;基于 Gemini 3 / Gemini 2.5 系列,1M 上下文,免费档 60 req/min + 1000 req/day,内置 Google Search / 文件 / Shell / Web Fetch 工具,MCP 协议完整支持,Extension / Hooks / Skills / Agents / Slash Command / Policy / Trusted-Folder 全套工程化机制。

---

## 1. 调研依据

### 1.1 仓库结构(只读,确认 packages 布局)

```
gemini-cli/
├── packages/
│   ├── cli/         ← yargs 入口、TUI、settings 加载、命令注册
│   ├── core/        ← Config、Storage、Agent Loop、Tools、MCP、Memory
│   ├── a2a-server/  ← A2A 协议服务端(server 包已合并)
│   ├── devtools/    ← 开发者调试 UI
│   ├── sdk/         ← 嵌入式 SDK
│   └── vscode-ide-companion/
├── docs/
├── .gemini/         ← 本仓库自身的项目级配置(本仓库在用)
│   ├── settings.json
│   ├── config.yaml
│   ├── commands/*.toml
│   └── skills/
└── GEMINI.md        ← 项目级 context file
```

> **注意**:用户 prompt 提到的 `packages/server/` 实际不存在;`packages/a2a-server/` 才是 a2a 服务入口。`server` 模式已被合并或重命名。`packages/cli/src/nonInteractiveCli.ts` 才是当前 server 模式入口(同时支持 `ADK agent session` 路径)。

### 1.2 关键源码定位

| 主题 | 关键文件 |
|---|---|
| 常量与路径工具 | `packages/core/src/utils/paths.ts` |
| Storage / 目录 API | `packages/core/src/config/storage.ts` |
| Config 主类 | `packages/core/src/config/config.ts` |
| WorkspaceContext | `packages/core/src/utils/workspaceContext.ts` |
| CLI 入口 / loadCliConfig | `packages/cli/src/config/config.ts` |
| Settings 加载 | `packages/cli/src/config/settings.ts` |
| ProjectRegistry | `packages/core/src/config/projectRegistry.ts` |
| Memory 加载 | `packages/core/src/utils/memoryDiscovery.ts` |
| Memory 文件名常量 | `packages/core/src/tools/memoryTool.ts` |
| Session 记录 | `packages/core/src/services/chatRecordingService.ts` |
| Shell 历史 | `packages/cli/src/ui/hooks/useShellHistory.ts` |
| Command 加载 | `packages/cli/src/services/FileCommandLoader.ts` |
| Skills 加载 | `packages/core/src/skills/skillManager.ts` |
| Trusted Folders | `packages/cli/src/config/trustedFolders.ts` + `packages/core/src/utils/trust.ts` |
| Worktree | `packages/cli/src/utils/worktreeSetup.ts` |
| Extension 存储 | `packages/cli/src/config/extensions/storage.ts` |
| `init` slash 命令 | `packages/cli/src/ui/commands/initCommand.ts` |
| Trust 检查 | `packages/core/src/services/FolderTrustDiscoveryService.ts` |

---

## 2. 三个核心问题的回答

### Q1. 工作区路径来源

**结论:Gemini CLI 的"工作区" = `process.cwd()`,没有显式 `--workspace` 参数,但有 4 层覆盖机制。**

#### 路径解析链路

| 优先级 | 来源 | 代码位置 | 行为 |
|---|---|---|---|
| 1 | `process.cwd()` | `packages/cli/src/gemini.tsx:377` → `loadSettings()` | **默认**,函数默认参数 `workspaceDir: string = process.cwd()` |
| 2 | `GEMINI_CLI_HOME` 环境变量 | `packages/core/src/utils/paths.ts:24-29` | **重写 `homedir()`** — 影响所有 `~/.gemini/...` 路径(用户态全局) |
| 3 | `--include-directories <dir>` | `packages/cli/src/config/config.ts:459` | **追加**额外可访问目录(不改 root) |
| 4 | `--worktree / -w <name>` | `packages/cli/src/utils/worktreeSetup.ts:34` `process.chdir(worktreeInfo.path)` | **切换 cwd 到新建 git worktree**,然后 `GEMINI_CLI_WORKTREE_HANDLED=1` 防递归 |
| 5 | `GEMINI_CLI_IDE_WORKSPACE_PATH` | `packages/cli/src/config/config.ts:637-651` | VSCode 多 workspace 场景,自动追加其他工作区目录 |

**关键代码证据:**

```typescript
// packages/core/src/utils/paths.ts:22-29
export function homedir(): string {
  const envHome = process.env['GEMINI_CLI_HOME'];
  if (envHome) {
    return envHome;
  }
  return os.homedir();
}
```

```typescript
// packages/cli/src/config/settings.ts:754-760
export function loadSettings(
  workspaceDir: string = process.cwd(),
): LoadedSettings {
  const normalizedWorkspaceDir = path.resolve(workspaceDir);
  return settingsCache.getOrCreate(normalizedWorkspaceDir, () =>
    _doLoadSettings(normalizedWorkspaceDir),
  );
}
```

```typescript
// packages/cli/src/config/config.ts:585-591
export async function loadCliConfig(
  settings: MergedSettings,
  sessionId: string,
  argv: CliArgs,
  options: LoadCliConfigOptions = {},
): Promise<Config> {
  const {
    cwd = process.cwd(),                  // ← 默认 cwd
    projectHooks,
    skipExtensions = false,
    loadedSettings,
  } = options;
```

```typescript
// packages/cli/src/config/config.ts:966
return new Config({
  ...
  targetDir: cwd,                         // ← Config 收到的 workspace
  ...
});
```

```typescript
// packages/core/src/config/config.ts:1015-1017
this.targetDir = path.resolve(params.targetDir);
this.folderTrust = params.folderTrust ?? false;
this.workspaceContext = new WorkspaceContext(this.targetDir, []);
```

```typescript
// packages/cli/src/utils/worktreeSetup.ts:30-35
const worktreeInfo = await service.setup(worktreeName || undefined);
process.chdir(worktreeInfo.path);          // ← 切换 cwd,后续 loadSettings 拿到的就是 worktree
process.env['GEMINI_CLI_WORKTREE_HANDLED'] = '1';
```

#### 完整覆盖矩阵

| 你想让 workspace 指向哪里 | 怎么做 |
|---|---|
| 当前 shell 所在目录 | 直接 `cd /path && gemini`(默认) |
| 另一个目录跑,但 shell 不想 cd | `cd /path && gemini` 或 `--worktree my-branch`(自动 chdir 到 worktree) |
| 把用户级 config 整个搬到共享盘 | `export GEMINI_CLI_HOME=/shared/gemini-config` |
| 在 TUI 里访问额外目录 | `gemini --include-directories /extra/path1,/extra/path2` |
| 在 VSCode 里多 workspace | 自动通过 `GEMINI_CLI_IDE_WORKSPACE_PATH` 注入 |
| Headless / CI | `gemini -p "..."` 自动 nonInteractive,无 cwd 切换 |

#### 边界:workspaceDir 就是 home 时的特殊处理

当 `cwd === homedir()`(用户直接在 `~` 下跑),有 3 个特殊处理:
1. `loadSettings` 会 **跳过 workspace settings**(`packages/cli/src/config/settings.ts:865`)— `if (!storage.isWorkspaceHomeDir()) { workspaceResult = load(workspaceSettingsPath); }`
2. `loadSettings` 的 workspace `path` 置空 + `readOnly: true`(`settings.ts:946-955`)
3. `FileCommandLoader` 跳过项目级 `commands/` 加载(`packages/cli/src/services/FileCommandLoader.ts:218-220`)— 避免 `~/.gemini/commands/` 被当成项目级再扫一次

代码:
```typescript
// packages/core/src/config/storage.ts:118-122
isWorkspaceHomeDir(): boolean {
  return (
    normalizePath(resolveToRealPath(this.targetDir)) ===
    normalizePath(resolveToRealPath(homedir()))
  );
}
```

---

### Q2. 目录结构

**结论:Gemini CLI 严格区分"全局用户态"`(`~/.gemini/`)和"项目态"`(`<cwd>/`),并把会话/历史/记忆全部隔离到全局 tmp 下的 `<shortId>/` 桶里。**

#### 2.1 全局用户目录:`~/.gemini/`(可通过 `GEMINI_CLI_HOME` 改)

| 路径 | 来源 API | 用途 |
|---|---|---|
| `settings.json` | `Storage.getGlobalSettingsPath()` `storage.ts:67` | 用户级 merged settings(可被 workspace 覆盖) |
| `projects.json` | `storage.ts:241-247` | **项目注册表**:`<absPath> -> shortId`,带 `.project_root` 所有权 marker 防冲突 |
| `installation_id` | `storage.ts:71` | 安装 ID(用户级) |
| `google_accounts.json` | `storage.ts:75` | 登录账号列表 |
| `oauth_creds.json` | `OAUTH_FILE`, `storage.ts:34, 202` | OAuth token 持久化 |
| `mcp-oauth-tokens.json` | `storage.ts:57` | MCP OAuth tokens |
| `a2a-oauth-tokens.json` | `storage.ts:61` | A2A OAuth tokens |
| `trustedFolders.json` | `TRUSTED_FOLDERS_FILENAME`, `storage.ts:35, 80` | 已信任目录列表(可被 `GEMINI_CLI_TRUSTED_FOLDERS_PATH` 覆盖) |
| `policy_integrity.json` | `storage.ts:107` | 策略完整性签名 |
| `acknowledgments/agents.json` | `storage.ts:103` | Agent 风险确认记录 |
| `trusted_hooks.json` | `packages/core/src/hooks/trustedHooks.ts:30` | 项目级 hook 信任白名单 |
| `commands/*.toml` | `Storage.getUserCommandsDir()` `storage.ts:84` | 用户自定义 slash 命令 |
| `commands/<group>/<name>.toml` | `FileCommandLoader.ts:215` | 同上,支持子目录分组 |
| `skills/<name>/SKILL.md` | `Storage.getUserSkillsDir()` `storage.ts:88` | 用户自定义 skill |
| `agents/*.md` | `Storage.getUserAgentsDir()` `storage.ts:96` | 用户自定义 agent(非 `_` 开头) |
| `policies/*.toml` | `Storage.getUserPoliciesDir()` `storage.ts:92` | 用户级 policy |
| `keybindings.json` | `storage.ts:99` | 自定义快捷键 |
| `extensions/<name>/` | `ExtensionStorage.getUserExtensionsDir()` `extensions/storage.ts:38` | 安装的扩展 |
| `extensions/<name>/gemini-extension.json` | `variables.ts:22` | 扩展清单 |
| `extensions/<name>/.env` | `variables.ts:24` | 扩展环境变量 |
| `extensions/<name>/commands/` | `extension-manager.ts:1058` | 扩展自带命令 |
| `extensions/<name>/hooks/hooks.json` | `extension-manager.ts:1058` | 扩展自带 hooks |
| `extensions/<name>/agents/*.md` | `extension-manager.ts:947` | 扩展自带 agent |
| `extensions/<name>/skills/` | `extension-manager.ts:921` | 扩展自带 skill |
| `extensions/<name>/policies/` | `extension-manager.ts:933` | 扩展自带 policy |
| `tmp/<shortId>/` | `Storage.getProjectTempDir()` `storage.ts:181-185` | **项目级临时数据** |
| `history/<shortId>/` | `Storage.getHistoryDir()` `storage.ts:273-280` | 已废弃,迁移保留 |

> `shortId` 由 `ProjectRegistry.slugify(basename(<absPath>))` 生成,`storage.ts:236-251`;默认 `cwd` 的 basename,例如 `/Users/x/myapp` → `myapp`;若冲突追加 `-1`, `-2`。所有 baseDir(项目 tmp、历史)下写 `<shortId>/.project_root` 所有权 marker,启动时校验,防别的工作区抢占同一个 shortId。

#### 2.2 项目级 tmp 目录:`~/.gemini/tmp/<shortId>/`

> 之所以放全局 tmp 而不是项目下,是因为:
> 1. **避免污染用户 git** — `.gitignore` 也难管
> 2. **多 workspace 共享同一个项目** — 同一 shortId 不同 cwd 命中同一桶
> 3. **项目可以只读挂载**(sandbox 模式)

| 路径 | API | 说明 |
|---|---|---|
| `chats/session-YYYY-MM-DDTHH-MM-<sessionId8>.jsonl` | `chatRecordingService.ts:468-512` | **主会话**记录,JSONL 流式追加 |
| `chats/<parentSessionId>/<sessionId>.jsonl` | `chatRecordingService.ts:482-486` | **子 agent** 会话记录,嵌套在父目录 |
| `memory/MEMORY.md` | `Storage.getProjectMemoryDir()` `storage.ts:285-287` | **项目自动记忆**(`PROJECT_MEMORY_INDEX_FILENAME` = `'MEMORY.md'`) |
| `memory/skills/` | `Storage.getProjectSkillsMemoryDir()` `storage.ts:290` | Skill 训练出来的项目记忆 |
| `checkpoints/` | `getProjectTempCheckpointsDir()` `storage.ts:313` | 撤销/rewind 用的文件快照 |
| `logs/logs.json` | `getProjectTempLogsDir()` `storage.ts:317` + `core/logger.ts:149` | 会话事件日志 |
| `plans/<sessionId>/` 或 `plans/` | `getProjectTempPlansDir()` `storage.ts:321-326` | Plan Mode 计划文件(可被 `setCustomPlansDir` 重定向到项目内) |
| `tracker/<sessionId>/` | `getProjectTempTrackerDir()` `storage.ts:328-333` | 任务追踪 |
| `tasks/<sessionId>/` | `getProjectTempTasksDir()` `storage.ts:355-360` | 任务分解 |
| `shell_history` | `getHistoryFilePath()` `storage.ts:425` | **Shell 命令历史**,纯文本(由 `useShellHistory.ts` 维护,最多 100 条) |

代码:
```typescript
// packages/core/src/services/chatRecordingService.ts:468-512
let chatsDir = path.join(
  this.context.config.storage.getProjectTempDir(),
  'chats',
);
if (this.kind === 'subagent' && this.context.parentSessionId) {
  const safeParentId = sanitizeFilenamePart(this.context.parentSessionId);
  chatsDir = path.join(chatsDir, safeParentId);
}
fs.mkdirSync(chatsDir, { recursive: true });
const timestamp = new Date().toISOString().slice(0, 16).replace(/:/g, '-');
const safeSessionId = sanitizeFilenamePart(this.sessionId);
this.conversationFile = path.join(chatsDir,
  `${SESSION_FILE_PREFIX}${timestamp}-${safeSessionId.slice(0, 8)}.jsonl`);
// 其中 SESSION_FILE_PREFIX = 'session-' (chatRecordingTypes.ts:12)
```

#### 2.3 项目级目录:`<cwd>/`

Gemini CLI 不会自动创建任何项目级目录。**项目级文件全靠用户手写或 `/init` 触发**。

| 路径 | 用途 | 创建方式 |
|---|---|---|
| `GEMINI.md` | **核心 context 文件**(默认) | 手动 / `/init` slash 命令 |
| `MEMORY.md` | 旧版私有项目记忆(legacy) | 手动,已迁到 `~/.gemini/tmp/<shortId>/memory/MEMORY.md` |
| `.geminiignore` | 类似 `.gitignore`,控制工具对文件的可见性 | 手动,见 `constants.ts:13` |
| `.gitignore` | 标准 git ignore(被 `FileDiscoveryService` 读) | git 自身 |
| `.gemini/settings.json` | 工作区级配置(覆盖 user) | 手动,或 `gemini extensions configure` 等 |
| `.gemini/commands/*.toml` | 工作区级 slash 命令 | 手动 |
| `.gemini/skills/<name>/SKILL.md` | 工作区级 skill | 手动 |
| `.gemini/agents/*.md` | 工作区级 agent | 手动 |
| `.gemini/policies/*.toml` | 工作区级 policy | 手动 |
| `.gemini/extensions/<name>/...` | 本地扩展(罕见) | 手动 / `gemini extensions link` |

**发现扫描器**(`FolderTrustDiscoveryService`)在 workspace **未信任**之前会先扫一遍,告诉用户项目里有什么:
- `.gemini/commands/*.toml` → 命令列表
- `.gemini/skills/<name>/SKILL.md` → skill 列表
- `.gemini/agents/*.md`(非 `_` 开头)→ agent 列表
- `.gemini/settings.json` → 设置 key 列表 + 收集 security warnings
- `.gemini/hooks`(已通过 settings.json 中的 `hooks` 字段) → hook 列表
- `.gemini/extensions/.../mcp.json` → MCP server 列表

代码:`packages/core/src/services/FolderTrustDiscoveryService.ts:38-77`

> ⚠️ 钩子不通过独立 `.gemini/hooks/hooks.json` 文件,只通过 `settings.json` 的 `hooks` 字段配置。`extension.ts:1058` 处的 `hooks/hooks.json` 是**扩展**内的(非项目 `.gemini/`)。

#### 2.4 系统级目录(只读,管理员)

```typescript
// packages/cli/src/config/settings.ts:104-115
export function getSystemSettingsPath(): string {
  if (process.env['GEMINI_CLI_SYSTEM_SETTINGS_PATH']) {
    return process.env['GEMINI_CLI_SYSTEM_SETTINGS_PATH'];
  }
  if (platform() === 'darwin') {
    return '/Library/Application Support/GeminiCli/settings.json';
  } else if (platform() === 'win32') {
    return 'C:\\ProgramData\\gemini-cli\\settings.json';
  } else {
    return '/etc/gemini-cli/settings.json';
  }
}
```

同级还有 `system-defaults.json`、`policies/`。

#### 2.5 设置加载顺序(4 层 merge)

| 层级 | 路径 | 优先级 |
|---|---|---|
| 1. `getDefaultsFromSchema()` | 内置 | 最低 |
| 2. `system-defaults.json` | `getSystemDefaultsPath()` | 低 |
| 3. `systemSettings.json` | `getSystemSettingsPath()` | 中 |
| 4. `USER_SETTINGS_PATH` = `~/.gemini/settings.json` | `storage.ts:80` | 中高 |
| 5. `workspaceSettings.json` = `<cwd>/.gemini/settings.json` | `storage.getWorkspaceSettingsPath()` `storage.ts:294` | 最高 |

代码:`packages/cli/src/config/settings.ts:904-908` 的 `mergeSettings(systemSettings, systemDefaultSettings, userSettings, workspaceSettings, isTrusted)`,**晚到覆盖早到**。

> 注意:`settings.ts:874-878` 还区分 `systemOriginalSettings`(去掉 `systemSettings` 之外的原始值)— 用来支持 `writeSettings` 时只回写到正确层。

#### 2.6 Memory 文件加载(4 类 context)

```typescript
// packages/core/src/context/memoryContextManager.ts:46-64
const [global, extension, project, userProjectMemory] = await Promise.all([
  getGlobalMemoryPaths(),                                        // ~/.gemini/GEMINI.md
  Promise.resolve(getExtensionMemoryPaths(...)),                 // extension 各自的 contextFiles
  this.config.isTrustedFolder()
    ? getEnvironmentMemoryPaths(...)                              // 向上遍历到 .git 边界
    : Promise.resolve([]),
  getUserProjectMemoryPaths(this.config.storage.getProjectMemoryDir()),  // ~/.gemini/tmp/<shortId>/memory/MEMORY.md
]);
```

| 类别 | 路径 | 关键常量 |
|---|---|---|
| `global` | `~/.gemini/GEMINI.md`(可配多文件名) | `DEFAULT_CONTEXT_FILENAME = 'GEMINI.md'` `memoryTool.ts:11` |
| `extension` | 各 extension 的 `contextFiles` 列表 | `memoryDiscovery.ts:383` |
| `project` | 从 `cwd` 向上找,直到 `.git` 边界 | `getEnvironmentMemoryPaths()` `memoryDiscovery.ts:405` |
| `userProjectMemory` | `~/.gemini/tmp/<shortId>/memory/MEMORY.md`(旧:`<cwd>/MEMORY.md`) | `PROJECT_MEMORY_INDEX_FILENAME = 'MEMORY.md'` `memoryTool.ts:12` |

`GEMINI.md` 加载支持 `importFormat: 'flat' | 'tree'` 和 `boundaryMarkers: ['.git']`(可改写)。

---

### Q3. 工作区创建

**结论:零 onboarding,零 CLI `init` 子命令,首次运行直接进 TUI 弹认证。**

#### 3.1 没有 `gemini init` CLI 子命令

```bash
$ gemini init
# → 不存在,会报 yargs 错误
```

CLI 入口是 yargs + 默认走 interactive 模式:
- `gemini`(无参数) → interactive TUI
- `gemini -p "..."` → non-interactive(单轮)
- `gemini -p "..." --output-format json` → headless
- `gemini --list-sessions` / `--delete-session` / `--resume` / `--session-id` → 会话元操作
- `gemini --worktree` → 创建/切换 worktree

**所有"配置"都是隐式的** — 没有 `gemini config init` / `gemini workspace init` 之类的命令。

#### 3.2 `/init` 是 slash 命令而非 CLI 子命令

`/init` 是内置 slash 命令,触发方式:**在 TUI 输入框输入 `/init` 回车**。

代码:`packages/cli/src/ui/commands/initCommand.ts:13-47`
```typescript
export const initCommand: SlashCommand = {
  name: 'init',
  description: 'Analyzes the project and creates a tailored GEMINI.md file',
  kind: CommandKind.BUILT_IN,
  autoExecute: true,
  action: async (context, _args) => {
    const targetDir = context.services.agentContext.config.getTargetDir();
    const geminiMdPath = path.join(targetDir, 'GEMINI.md');
    const result = performInit(fs.existsSync(geminiMdPath));
    if (result.type === 'submit_prompt') {
      fs.writeFileSync(geminiMdPath, '', 'utf8');   // 创建空 GEMINI.md
      context.ui.addItem({ type: 'info', text: 'Empty GEMINI.md created...' }, Date.now());
    }
    return result;  // submit_prompt 触发 LLM 读取工程并填充
  },
};
```

`performInit` 的核心(`packages/core/src/commands/init.ts:11-66`):返回一个 prompt,告诉 LLM"读 README、读若干文件、识别项目类型、生成 GEMINI.md"。**这个 prompt 是动态构造的,不是静态模板**。

> 真正的 init 工作不是 Gemini CLI 做的,而是 LLM 根据 prompt 读工程 → 写 `GEMINI.md`。**Gemini CLI 本身只创建空文件**。

#### 3.3 首次 `gemini` 启动流程

```
gemini
  └─ gemini.tsx
       └─ loadSettings()              // 读 settings.json 四层,创建 ~/.gemini/ (mkdir -p)
       └─ (可选) setupWorktree()      // --worktree 时,git worktree add + chdir
       └─ loadCliConfig(...)
            └─ new Config({ targetDir: cwd })
                 └─ this.storage = new Storage(targetDir)
                 └─ (lazy) storage.initialize()           // 第一次 session 触发
                       └─ ProjectRegistry.initialize()    // 读 ~/.gemini/projects.json (或创建空)
                       └─ getShortId(<absPath>)           // 计算/注册 shortId
                       └─ storageMigration                // 老 hash 桶迁移到 shortId
            └─ new WorkspaceContext(cwd, includeDirs)
       └─ initializeApp()              // 认证 + 主题 + IDE(无 onboarding UI)
            └─ performInitialAuth()    // 弹 auth dialog(shouldOpenAuthDialog)
            └─ validateTheme()
       └─ getUserStartupWarnings()     // 三个检查:home-dir / root-dir / folder-trust
       └─ (folder trust 开启时)弹信任确认框 — 首次陌生项目会问"trust this folder?"
       └─ TUI 渲染
```

#### 3.4 目录创建时机

| 目录 | 何时创建 | 触发 API |
|---|---|---|
| `~/.gemini/` | `loadSettings()` 第一次读 settings.json 时 | `settings.ts:773-844`(隐式,`fs.existsSync` 检测后跳过,实际是 `ProjectRegistry.save` 时 `mkdirSync({recursive:true})` `projectRegistry.ts:99-101`) |
| `~/.gemini/tmp/<shortId>/` | `storage.initialize()` 第一次为项目调 shortId 时 | `projectRegistry.ts:128-135` 的 `ensureOwnershipMarkers` |
| `~/.gemini/tmp/<shortId>/chats/` | 第一次会话开始 | `chatRecordingService.ts:488` `fs.mkdirSync(chatsDir, { recursive: true })` |
| `~/.gemini/tmp/<shortId>/memory/` | 第一次写 MEMORY.md 时(LLM 用 memory tool) | `memoryService` 懒创建 |
| `~/.gemini/tmp/<shortId>/logs/` | logger.initialize() | `core/logger.ts:152` `await fs.mkdir(this.geminiDir, { recursive: true })` |
| `<cwd>/.gemini/` | **永不自动创建** | 用户手写 / `gemini extensions link` |
| `<cwd>/GEMINI.md` | 手动 / `/init` | `initCommand.ts:42` `fs.writeFileSync(geminiMdPath, '', 'utf8')` |
| `<cwd>/.geminiignore` | **永不自动创建** | 用户手写 |

> 也就是说,Gemini CLI 真正"隐式写盘"的只有 `~/.gemini/` 这一个全局目录。所有项目内文件都是用户产物。

#### 3.5 首次启动"引导"是什么

**严格说没有 onboarding**。顺序是:
1. **认证弹窗**(`shouldOpenAuthDialog` = true) — 因为没选 auth method,或 oauth 失败
2. **Folder Trust 检查** — `folderTrust.enabled` 默认 `true`(`trustedFolders.ts:33`),遇到不在 `trustedFolders.json` 中的目录会**阻塞**:
   - Headless:`FatalUntrustedWorkspaceError`,要 `--skip-trust` 或 `GEMINI_CLI_TRUST_WORKSPACE=true`
   - Interactive:弹确认框("Trust this folder?")
3. **3 个 startup warning**:
   - **Home-dir warning**:`cwd === ~` 时提示(可关)
   - **Root-dir warning**:`cwd === /` 时**强提示**(因为整个文件系统会成为 context)
   - **Folder-trust warning**:未信任时
4. TUI 渲染完成,可以输入 prompt

代码:`packages/cli/src/utils/userStartupWarnings.ts`

#### 3.6 init 总结

| 操作 | 行为 |
|---|---|
| `gemini`(首次) | 弹认证 + folder trust 确认 + home/root warning → 进 TUI |
| `/init`(TUI 内) | 创建空 `GEMINI.md`,LLM 读工程填充(不是 CLI 自己写) |
| `gemini --worktree mybranch` | `git worktree add` + `process.chdir`,等价于"在 worktree 下 init" |
| `gemini -p "..."`(headless) | 跳过所有 onboarding,跑完即退 |

---

## 3. 关键代码片段(精选)

### 3.1 Storage 的 path API 总览(`storage.ts`)

```typescript
// packages/core/src/config/storage.ts:50-77
static getGlobalGeminiDir(): string {
  return path.join(homedir(), GEMINI_DIR);                // ~/.gemini
}
static getGlobalSettingsPath(): string {
  return path.join(Storage.getGlobalGeminiDir(), 'settings.json');
}
static getTrustedFoldersPath(): string {
  return process.env['GEMINI_CLI_TRUSTED_FOLDERS_PATH']
    ?? path.join(Storage.getGlobalGeminiDir(), TRUSTED_FOLDERS_FILENAME);
}
static getUserCommandsDir(): string {
  return path.join(Storage.getGlobalGeminiDir(), 'commands');
}
static getUserSkillsDir(): string {
  return path.join(Storage.getGlobalGeminiDir(), 'skills');
}
static getUserAgentSkillsDir(): string {
  return path.join(Storage.getGlobalAgentsDir(), 'skills');  // ~/.agents/skills alias
}
static getUserAgentsDir(): string {
  return path.join(Storage.getGlobalGeminiDir(), 'agents');
}
static getSystemSettingsPath(): string {
  return process.env['GEMINI_CLI_SYSTEM_SETTINGS_PATH']
    ?? path.join(getSystemConfigDir(), 'settings.json');
}
```

### 3.2 Storage 实例 API(项目级)

```typescript
// packages/core/src/config/storage.ts:162-358
getGeminiDir(): string { return path.join(this.targetDir, GEMINI_DIR); }     // <cwd>/.gemini
getWorkspaceSettingsPath(): string { return path.join(this.getGeminiDir(), 'settings.json'); }
getProjectCommandsDir(): string { return path.join(this.getGeminiDir(), 'commands'); }
getProjectSkillsDir(): string { return path.join(this.getGeminiDir(), 'skills'); }
getProjectAgentsDir(): string { return path.join(this.getGeminiDir(), 'agents'); }
getProjectMemoryDir(): string { return this.getProjectMemoryTempDir(); }
getProjectMemoryTempDir(): string { return path.join(this.getProjectTempDir(), 'memory'); }
getHistoryFilePath(): string { return path.join(this.getProjectTempDir(), 'shell_history'); }
getProjectTempDir(): string { return path.join(Storage.getGlobalTempDir(), identifier); }
getHistoryDir(): string { return path.join(historyBase, identifier); }
getExtensionsDir(): string { return path.join(this.getGeminiDir(), 'extensions'); }
```

### 3.3 ProjectRegistry 短 ID 计算

```typescript
// packages/core/src/config/projectRegistry.ts:339-345
private slugify(text: string): string {
  return (
    text.toLowerCase()
        .replace(/[^a-z0-9]/g, '-')
        .replace(/-+/g, '-')
        .replace(/^-|-$/g, '') || 'project'
  );
}
```

冲突时 `claimNewSlug` 会尝试 `myapp-1`, `myapp-2`,...,并用 `~/.gemini/tmp/<slug>/.project_root` 所有权 marker 防止抢占。

### 3.4 设置加载(settings.ts 四层)

```typescript
// packages/cli/src/config/settings.ts:768-908
let systemSettings: Settings = {};
let systemDefaultSettings: Settings = {};
let userSettings: Settings = {};
let workspaceSettings: Settings = {};
const systemSettingsPath = getSystemSettingsPath();
const systemDefaultsPath = getSystemDefaultsPath();
const storage = new Storage(workspaceDir);
const workspaceSettingsPath = storage.getWorkspaceSettingsPath();
// load() 各自读 + Zod 校验 + 展开 env vars
// isWorkspaceHomeDir() 时跳过 workspaceResult
const tempMergedSettings = mergeSettings(
  systemSettings, systemDefaultSettings, userSettings, workspaceSettings, isTrusted,
);
loadEnvironment(tempMergedSettings, workspaceDir);
```

### 3.5 会话记录文件命名

```typescript
// packages/core/src/services/chatRecordingService.ts:498-512
const timestamp = new Date().toISOString().slice(0, 16).replace(/:/g, '-');
const safeSessionId = sanitizeFilenamePart(this.sessionId);
if (this.kind === 'subagent') {
  filename = `${safeSessionId}.jsonl`;
} else {
  filename = `${SESSION_FILE_PREFIX}${timestamp}-${safeSessionId.slice(0, 8)}.jsonl`;
}
this.conversationFile = path.join(chatsDir, filename);
// SESSION_FILE_PREFIX = 'session-' (chatRecordingTypes.ts:12)
```

实际文件名例:`session-2026-07-15T14-30-1a2b3c4d.jsonl`

### 3.6 Worktree 切换

```typescript
// packages/cli/src/utils/worktreeSetup.ts:30-35
const worktreeInfo = await service.setup(worktreeName || undefined);
process.chdir(worktreeInfo.path);
process.env['GEMINI_CLI_WORKTREE_HANDLED'] = '1';
```

`service.setup` 调 `git worktree add`(默认分支)或 `git worktree add -b mybranch HEAD`。`process.chdir` 后,`loadSettings()` 拿到的 `workspaceDir` 就是 worktree 路径,后续一切以 worktree 为锚。

---

## 4. 与 Onion Agent 设计的关联

> 假设 Onion Agent 的设计哲学:**Agent Loop = 围绕 `session.json` 的自动累加器**,即上下文历史即文件、文件即状态。

| Gemini CLI 的做法 | Onion Agent 可借鉴 / 规避点 |
|---|---|
| **三段式目录**:`~/.gemini/`(全局) + `<cwd>/` 显式(项目) + `~/.gemini/tmp/<shortId>/`(运行时) | ✅ **强烈推荐**。全局态(账号、扩展)与项目态(配置)与运行时态(chats、memory)解耦,避免污染 git。Onion 的 `session.json` 应该放 `~/.onion/tmp/<shortId>/session.json` 而不是 `<cwd>/.onion/session.json`。 |
| **`process.cwd()` 作为 workspace**,无显式 CLI 参数 | ✅ **跟随 cwd 即可**,只在 `GEMINI_CLI_HOME`/`ONION_HOME` 这种环境变量上提供"用户态重定位"层。Onion 不需要 `--workspace` 参数。 |
| **`ProjectRegistry` + `shortId`**:同一项目多个 cwd 命中同一桶 | ✅ **值得抄**。Onion 的 session 应该用 `<shortId>` 而不是 `<absPath hash>`,可读、可分享、避免泄漏路径。`/data/user/myapp/session-1.json` 比 `/data/<sha256>/session-1.json` 友好。 |
| **短 ID 用 `slugify(basename)` + 冲突追加 `-N`**,且每个 baseDir 下放 `.project_root` 所有权 marker | ✅ 防止同名项目互相覆盖是关键。Onion 也应该做 `~/.onion/tmp/<slug>/.project_root`(内容 = 规范化 absPath),启动时校验。 |
| **Settings 4 层 merge**:`defaults < system-defaults < system < user < workspace` | ✅ **标准做法**,Onion 可以抄,但要明确每层的 readOnly 语义(Gemini 的 system 层是 `readOnly: true`)。 |
| **Folder Trust 机制**:未信任的 workspace 默认拒绝 MCP/Hooks | ⚠️ **谨慎借鉴**。Onion 可能在信创内网环境跑,信任模型可能更简单(默认全信,或基于 git remote)。但 sandbox 设计可以参考 — `isWorkspaceHomeDir()` 跳过 workspace 层的判断是必要的。 |
| **会话文件是 `JSONL` 流式追加,不是单一 `session.json`** | ⚠️ **架构分歧**。Gemini 因为会话可长达数小时 + 多 subagent,JSONL 流式比单 JSON 更友好(可恢复、可分块)。**但 Onion 的核心承诺是"`session.json` 是单一真相源 + 自动累加"**——这是一个**有意为之的简化**,可读性 > 性能。**建议 Onion 维持单文件,但写盘用 `temp + rename` 原子化(参考 `ProjectRegistry.save` `projectRegistry.ts:103-148` 的写法)。** |
| **Memory 分 4 类**:`global` / `extension` / `project` / `userProjectMemory` | ✅ **抄**。Onion 可以简化为 3 类:`~/.onion/GEMINI.md`(全局) + `<cwd>/GEMINI.md`(项目) + `~/.onion/tmp/<shortId>/memory/MEMORY.md`(自动学习)。`extension` 层可以省。 |
| **`/init` slash 命令生成 `GEMINI.md`,由 LLM 填充** | ✅ **抄**。Onion 的 `onion init` 应该做同样的事:创建空 context file + 提交 prompt 让 LLM 读工程填充。**而且 init 不应该自动写 `~/.onion/`** — 把全局和项目解耦。 |
| **首次启动无 onboarding**,直接 TUI + 弹认证 | ✅ **抄**。Onion 应该同样"零 onboarding",首次直接进 TUI,认证失败才弹。 |
| **3 个 startup warning**(home-dir / root-dir / folder-trust) | ✅ **抄其中 1 个**。Onion 可以保留 home-dir 警告(root-dir 警告对 Onion 没意义,因为 Onion 可能就是给单用户跑的)。 |
| **Sandbox 自动开**,默认 `toolSandboxing: false` 但 `sandbox.enabled` 可被 `--sandbox` 打开 | ✅ **抄默认关闭**。Onion 可以有 `--sandbox` 走 `bubblewrap` / `firejail` / 容器。 |
| **`--worktree` 自动 chdir 到 worktree** | ❌ **不抄**。Onion 应该在 `<cwd>` 上做多 session 隔离(不同 `<shortId>/session-<id>.json`),而不是用 git worktree 物理隔离。 |
| **Hook 通过 `settings.json` 配置,不通过 `.gemini/hooks/hooks.json`** | ✅ **抄**。把 hook 集中到 settings.json 比散落多个文件好,版本控制、merge 都更简单。 |
| **Trusted Hooks Manager**(`trusted_hooks.json`) | ⚠️ **看场景**。信创内网可能不需要这个,直接默认全部允许。 |
| **Shell History = `<tmp>/shell_history` 纯文本 100 条** | ✅ **抄**。Onion 应该有 `~/.onion/tmp/<shortId>/shell_history`,纯文本行,简单可靠。 |
| **Memory 中"向上找 GEMINI.md 直到 .git 边界"** | ✅ **抄**。Onion 的 Onion-MD 加载也应该遵循同样的 hierarchy 规则。 |
| **默认 `folderTrust.enabled = true`**(默认不信任) | ❌ **反着来**。信创内网环境 Onion 应该默认全信任 + 可选 `--require-trust`。 |
| **`.geminiignore` 类似 `.gitignore`** | ✅ **抄**。Onion 应该有 `.onionignore`,优先级同 `.gitignore`。 |

### 关键设计 takeaway

1. **路径分层**:全局(`~`) + 项目(`cwd`) + 运行时(`~/tmp/<shortId>/`)三层目录,缺一不可。
2. **Workspace 即 cwd**,不要试图用 CLI 参数控制。
3. **Session 不放项目内**,放 `~/.onion/tmp/<shortId>/`,靠 slugify 防冲突。
4. **配置 4 层 merge**,workspace 覆盖 user,user 覆盖 system,每层 readOnly 语义不同。
5. **零 onboarding**,只有认证 + folder trust 弹框。
6. **`/init` 是 LLM 驱动的**,不是 CLI 自己生成文件 — 这是 Gemini 把"智能"做到位的关键,值得抄。

---

## 5. 不确定 / 未找到

| 疑问 | 备注 |
|---|---|
| `server` 包到底存在不存在? | **确认不存在**。`packages/a2a-server/` 是 a2a 服务;`packages/cli/src/nonInteractiveCli.ts` 是当前 server 模式入口(同时支持 ADK agent session 路径)。 |
| `.gemini/tmp/<shortId>/<sessionId>/plans/` 中的 session 维度目录何时创建? | 推测:当 session 第一次进入 plan mode 时;但代码 `storage.ts:321-326` 只是 getter,实际创建由 `PlanModeService` 负责,本次未深入。 |
| `memory/skills/` 子目录用途 | `storage.ts:290` 有 `getProjectSkillsMemoryDir()`,但具体存什么需要看 `memoryService.ts`,本次只扫到 `MEMORY.md` 的逻辑。 |
| Hooks 是否支持项目级 `.gemini/hooks/hooks.json` 独立文件? | **不支持**。hooks 必须通过 `settings.json` 的 `hooks` 字段配置;扩展可以自带 `hooks/hooks.json`(`extension.ts:1058`)。代码注释和测试都确认。 |
| Worktree 路径是否写回 `projects.json` 作为短 ID 的一部分? | **不写**。`process.chdir` 之后 shortId 用 worktree 的 `basename`(`myapp-worktree`),`projectRegistry` 会作为新 shortId 注册。 |
| `installation_id` 是首次启动就创建还是 settings 加载时? | 代码 `storage.ts:71` 暴露路径,但创建逻辑未深查;推测在 telemetry 初始化时。 |
| `.gemini/config.yaml` 是什么? | 本仓库 snapshot 里 `.gemini/config.yaml` 存在,内容是 PR Review Bot 配置 — 看起来是 `gcloud` 工具读的配置,**不是** Gemini CLI 自己读。 |

---

**调研人**:general(子代理)
**调研范围**:仅 `C:\workspace\github\onionagent\harness\01_market_research\clone\gemini-cli`,未做修改
**引用行号格式**:`path:line`,所有代码均来自该 snapshot
