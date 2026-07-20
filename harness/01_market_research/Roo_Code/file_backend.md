# Roo Code — 工作区(File Backend)调研报告

> **调研对象**:`Roo-Code` (RooCodeInc/Roo-Code),v3.53.0(本地 clone 快照,2026-07-17)
> **调研时间**:2026-07-17
> **调研焦点**:工作区/文件后端(workspace path、目录结构、初始化/创建)

---

## 0. 智能体一句话定位

**Cline 的"整支开发团队" fork,4 个内置 Mode(Code / Architect / Ask / Debug)+ Orchestrator(共 5 个内置),用户可创建 Custom Mode;支持 `.roomodes` 项目级声明式配置 + `.roo/` 目录式 rules/skills/commands,可在 Mode 之间自动切换。**

- **仓库结构**:`pnpm` monorepo(`apps/`、`packages/`、`src/`),源码同时存在 `src/`(主 bundle,VS Code 扩展)和 `packages/{core,types,ipc}/`(子包,ESM)
- **核心运行时入口**:`src/extension.ts:90` → `activate(context)` → `ContextProxy.getInstance(context)` → `ClineProvider`
- **版本状态**:⚠️ 5 月 15 日 Roo Code 母公司已关停 VS Code 扩展(社区 fork 仍在维护,如 ZooCode)

---

## 1. 调研依据

| 来源 | 用途 |
|---|---|
| `src/services/roo-config/index.ts` | 路径工具:`getGlobalRooDirectory` / `getProjectRooDirectoryForCwd` / `getRooDirectoriesForCwd` / `discoverSubfolderRooDirectories` |
| `src/utils/storage.ts` | 任务/设置/缓存目录解析 + `customStoragePath` 可配置项 |
| `src/utils/globalContext.ts` | 桥接:`ensureSettingsDirectoryExists(context)` |
| `src/core/config/ContextProxy.ts` | `vscode.ExtensionContext` 包装,暴露 `globalStorageUri` |
| `src/core/config/CustomModesManager.ts` | Custom Modes 加载 + `.roomodes` 文件监听 |
| `src/core/task-persistence/TaskHistoryStore.ts` | 任务历史 per-task 文件 + 索引 |
| `src/core/prompts/sections/custom-instructions.ts` | Rules / AGENTS.md / 模式化 rules 加载 |
| `src/services/skills/SkillsManager.ts` | Skills(类似 Claude Skills)发现与调度 |
| `src/services/command/commands.ts` | Commands(斜杠命令)扫描 |
| `src/services/mcp/McpHub.ts` | MCP 全局/项目级配置管理 |
| `src/core/checkpoints/index.ts` | Checkpoint 影子 git 仓库 |
| `src/core/environment/getMcpServersPath.ts` | MCP servers 目录(平台特定) |
| `src/core/webview/ClineProvider.ts` | ClineProvider 持有路径资源 |
| `src/shared/globalFileNames.ts` | 持久化文件名常量 |
| `src/core/protect/RooProtectedController.ts` | 写保护文件清单(`.roomodes` / `.roo/**` 等) |
| 实际 repo `.roo/` 目录与 `.roomodes` 文件 | 验证项目级配置实际形态 |

---

## 2. 三个核心问题的回答

### Q1. 工作区路径 — Roo Code 的多源、可配置、跟随工作区的混合模型

Roo Code **不是单一写死路径**,而是采用 **"全局 home + 项目 workspace + 平台特定 + VS Code 扩展" 四层并行** 的复合工作区模型。

#### 路径分类表

| 类别 | 路径 | 来源 | 写死? | 跨平台? |
|---|---|---|---|---|
| **VS Code 扩展全局存储** | `context.globalStorageUri.fsPath` | VS Code ExtensionContext(由 VS Code 决定,如 `%APPDATA%\Code\User\globalStorage\roo-cline.rooveterinaryinc` ) | ✗ VS Code 决定 | 自动 |
| **全局用户级 `.roo/`** | `~/.roo/`(`%USERPROFILE%\.roo\` on Win) | `os.homedir()` | ✓ 写死 home | 由 Node 决定 |
| **项目级 `.roo/`** | `{cwd}/.roo/` | `vscode.workspace.workspaceFolders[0].uri.fsPath` | ✗ 跟随 VS Code 打开的工作区 | 自动 |
| **MCP servers 安装目录** | Windows:`%APPDATA%\Roo-Code\MCP` / macOS:`~/Documents/Cline/MCP` / Linux:`~/.local/share/Roo-Code/MCP` | `os.homedir()` + 平台分支 | ✓ 写死,但**残留 Cline 命名** | 三平台分支 |
| **Checkpoint shadow dir** | 复用 `context.globalStorageUri.fsPath` | 同上 | ✗ 跟随 VS Code | 自动 |
| **Code index cache** | `context.globalStorageUri/roo-index-cache-<sha256>.json` | 同上 | ✗ | 自动 |
| **可配置用户存储根** | `customStoragePath`(用户设置)→ 覆盖 task/settings/cache 三大子目录的 base | VS Code `ConfigurationTarget.Global` | 用户可改 | 由用户决定 |

#### 关键代码证据

**1) 全局 `.roo/` 路径(写死 `os.homedir()`)**

`src/services/roo-config/index.ts:21-27`:

```typescript
export function getGlobalRooDirectory(): string {
    const homeDir = os.homedir()
    return path.join(homeDir, ".roo")
}
```

> 这是 **Roo Code 对 Cline 模型的扩展**:Cline 把所有自定义配置塞进 VS Code `context.globalState`;Roo Code 把它**外置到 `~/.roo/`** 普通文件系统,便于用户直接编辑、跨 IDE 同步、跨机器备份。

**2) 项目级 `.roo/` 路径(跟随 workspace)**

`src/services/roo-config/index.ts:104`:

```typescript
export function getProjectRooDirectoryForCwd(cwd: string): string {
    return path.join(cwd, ".roo")
}
```

调用点几乎都基于 `getWorkspacePath()`(`src/utils/path.ts:106`):

```typescript
export const getWorkspacePath = (defaultCwdPath = "") => {
    const cwdPath = vscode.workspace.workspaceFolders?.map((folder) => folder.uri.fsPath).at(0) || defaultCwdPath
    const currentFileUri = vscode.window.activeTextEditor?.document.uri
    if (currentFileUri) {
        const workspaceFolder = vscode.workspace.getWorkspaceFolder(currentFileUri)
        return workspaceFolder?.uri.fsPath || cwdPath
    }
    return cwdPath
}
```

**3) 解析顺序:[global, project]( + 可选 subfolders)**

`src/services/roo-config/index.ts:274-282`:

```typescript
export function getRooDirectoriesForCwd(cwd: string): string[] {
    const directories: string[] = []
    // Add global directory first
    directories.push(getGlobalRooDirectory())
    // Add project-local directory second
    directories.push(getProjectRooDirectoryForCwd(cwd))
    return directories
}
```

**4) MCP servers 目录(平台特定,残留 Cline 命名)**

`src/core/webview/ClineProvider.ts:1544-1565`:

```typescript
async ensureMcpServersDirectoryExists(): Promise<string> {
    let mcpServersDir: string
    if (process.platform === "win32") {
        // Windows: %APPDATA%\Roo-Code\MCP
        mcpServersDir = path.join(os.homedir(), "AppData", "Roaming", "Roo-Code", "MCP")
    } else if (process.platform === "darwin") {
        // macOS: ~/Documents/Cline/MCP    ← 残留 Cline 命名!
        mcpServersDir = path.join(os.homedir(), "Documents", "Cline", "MCP")
    } else {
        // Linux: ~/.local/share/Roo-Code/MCP
        mcpServersDir = path.join(os.homedir(), ".local", "share", "Roo-Code", "MCP")
    }
    ...
}
```

> **注意**:macOS 路径仍叫 "Cline",**这是 fork 没清理干净的历史包袱**。

**5) `customStoragePath` 可配置(用户可全局覆盖)**

`src/utils/storage.ts:14-48` + `src/package.json:334-337`:

```typescript
export async function getStorageBasePath(defaultPath: string): Promise<string> {
    let customStoragePath = ""
    try {
        const config = vscode.workspace.getConfiguration(Package.name)
        customStoragePath = config.get<string>("customStoragePath", "")
    } catch (error) { return defaultPath }
    if (!customStoragePath) return defaultPath
    try {
        await fs.mkdir(customStoragePath, { recursive: true })
        await fs.access(customStoragePath, fsConstants.R_OK | fsConstants.W_OK | fsConstants.X_OK)
        return customStoragePath
    } catch (error) {
        if (vscode.window) {
            vscode.window.showErrorMessage(t("common:errors.custom_storage_path_unusable", { path: customStoragePath }))
        }
        return defaultPath
    }
}
```

`package.json:334` 声明:`roo-cline.customStoragePath`,string 类型,默认空字符串,描述 "Custom storage path. Leave empty to use the default location."

设置命令:`roo-cline.setCustomStoragePath`(`src/package.json:139-141`),通过 `promptForCustomStoragePath()`(`src/utils/storage.ts:84-150`)弹出输入框,要求**绝对路径**,`ConfigurationTarget.Global` 持久化。

#### 路径优先级与覆盖关系

| 优先级 | 类型 | 说明 |
|---|---|---|
| **L0** | `customStoragePath` 用户设置 | 完全覆盖 task/settings/cache 三大子目录的 base(在 `getStorageBasePath` 决策) |
| **L1** | VS Code `globalStorageUri` | L0 未设时使用,决定 tasks/settings/cache/code-index cache |
| **L2** | `~/.roo/` 全局用户目录 | 与 L3 并行,被 L3 覆盖(merge 时 project 优先) |
| **L3** | `{workspace}/.roo/` 项目级目录 | 跟随当前打开的工作区;**未打开工作区时不可用** |
| **L4** | `{workspace}/.roo/` 子文件夹 | 当 `enableSubfolderRules = true` 时通过 ripgrep 扫描发现 |
| **L5** | `AGENTS.md` / `AGENT.md` / `AGENTS.local.md` | 项目根和带 `.roo/` 的子目录;`AGENTS.local.md` 永远 personal override |
| **L6** | 平台特定 MCP servers dir | 与 L0/L1 完全独立(不受 customStoragePath 影响) |

---

### Q2. 工作区目录结构 — 三层并行的"洋葱式"文件后端

Roo Code 的文件后端有 **5 个并行存储层次**,**没有统一的工作区根目录**(不同于 Cline 完全依赖 `context.globalState`),而是把配置显式落到文件系统。

#### 总览表(根据实际代码与目录列举)

| 层次 | 位置 | 形态 | 创建者 |
|---|---|---|---|
| **A. VS Code 扩展全局存储** | `%APPDATA%\Code\User\globalStorage\roo-cline.rooveterinaryinc\`(Win) | `tasks/`、`settings/`、`cache/`、`roo-index-cache-<hash>.json` | Roo 运行时 |
| **B. 用户全局 `.roo/`** | `~/.roo/` | `custom_modes.yaml`、`mcp_settings.json`、`commands/*.md`、`skills/<skill>/SKILL.md`、`rules/*.md`、`rules-<mode>/*.md`、`tools/`(预留) | 用户/Roo |
| **C. 项目级 `.roo/`** | `{workspace}/.roo/` | `mcp.json`、`commands/*.md`、`skills/<skill>/SKILL.md`、`rules/*.md`、`rules-<mode>/*.md` | 用户/Roo |
| **D. 项目级 `.roomodes`** | `{workspace}/.roomodes` | 单个 YAML 文件,`customModes` 字段 | 用户/UI |
| **E. 用户全局 `.agents/`** | `~/.agents/` | `skills/<skill>/SKILL.md`(跨 agent 共享) | 用户/Roo |
| **F. 项目级 `.agents/`** | `{workspace}/.agents/` | `skills/<skill>/SKILL.md`(跨 agent 共享) | 用户/Roo |
| **G. 平台特定 MCP** | 见 Q1 表 | MCP server 安装目录 | Roo/Roo 用户 |
| **H. 写保护文件** | `{workspace}/` | `.rooignore` / `.roomodes` / `.roorules*` / `.clinerules*` / `.roo/**` / `.vscode/**` / `AGENTS.md` | 各种来源 |

#### A. VS Code 扩展全局存储(`context.globalStorageUri`)

由 `getStorageBasePath(globalStoragePath)` 决定 base,然后是三个子目录:

```
<globalStorageUri>/                    ← 由 VS Code 决定
├── tasks/                             ← getTaskDirectoryPath
│   ├── _index.json                    ← 任务历史索引(debounced 2s 写)
│   ├── <taskId-1>/
│   │   ├── api_conversation_history.json   ← Anthropic 格式消息
│   │   ├── ui_messages.json                 ← Webview 消息
│   │   ├── task_metadata.json               ← 元数据(timestamp/tokens/...)
│   │   └── history_item.json                ← HistoryItem 单条记录
│   └── <taskId-N>/...
├── settings/                          ← getSettingsDirectoryPath
│   ├── custom_modes.yaml              ← 全局 Custom Modes
│   └── mcp_settings.json              ← 全局 MCP 配置
├── cache/                             ← getCacheDirectoryPath
│   └── (model provider endpoint cache)
├── roo-index-cache-<sha256>.json      ← Code Index 文件 hash 缓存
└── checkpoints/<taskId>/.git/         ← Git shadow 仓库(每任务一个)
```

文件名常量(`src/shared/globalFileNames.ts:3-11`):

```typescript
export const GlobalFileNames = {
    apiConversationHistory: "api_conversation_history.json",
    uiMessages: "ui_messages.json",
    mcpSettings: "mcp_settings.json",
    customModes: "custom_modes.yaml",
    taskMetadata: "task_metadata.json",
    historyItem: "history_item.json",
    historyIndex: "_index.json",
}
```

#### B + C. 全局/项目级 `.roo/` 对照(本调研 clone 实际目录)

```
.roo/                                 ← (本仓库自己的项目级 .roo)
├── commands/                          ← 斜杠命令(全局+项目都支持)
│   ├── cli-release.md
│   ├── commit.md
│   ├── release.md
│   ├── roo-resolve-conflicts.md
│   └── roo-translate.md
├── guidance/                          ← 提示词辅助(预留)
│   └── roo-translator.md
├── rules/                             ← 通用 rules(全局+项目都支持)
│   └── rules.md
├── rules-<mode>/                      ← 模式化 rules,每 mode 一目录
│   ├── rules-code/use-safeWriteJson.md
│   ├── rules-debug/cli.md
│   ├── rules-translate/001-general-rules.md
│   ├── rules-issue-fixer/1_Workflow.xml ... 9_pr_template.xml
│   ├── rules-issue-investigator/1_workflow.xml ... 6_communication.xml
│   ├── rules-issue-writer/1_workflow.xml ... 5_examples.xml
│   ├── rules-merge-resolver/1_workflow.xml ... 5_communication.xml
│   ├── rules-pr-fixer/1_workflow.xml ... 5_examples.xml
│   ├── rules-docs-extractor/1_extraction_workflow.xml ... 3_output_format.xml
├── skills/                            ← Skills(类 Claude Skills)
│   ├── evals-context/SKILL.md         ← 通用 skill
│   ├── roo-conflict-resolution/SKILL.md
│   └── roo-translation/SKILL.md
└── roomotes.yml                       ← 房间机器人(外部自动化配置,非本调研重点)
```

> **注意**:上面的目录是 Roo-Code 仓库**自己作为工作区**的 `.roo/` 内容,展示 Roo-Code 是"自己吃自己狗粮"。

#### B. 全局用户级 `~/.roo/`(用户机器上)

```text
~/.roo/
├── custom_modes.yaml              ← 全局 Custom Modes(用户本人所有项目共享)
├── mcp_settings.json              ← 全局 MCP servers
├── commands/                      ← 全局斜杠命令
│   └── *.md(frontmatter:description, argument-hint, mode)
├── skills/                        ← 全局 Skills(frontmatter:name, description, modeSlugs)
│   └── <skill-name>/SKILL.md
├── rules/                         ← 全局通用 rules
│   └── *.md
└── rules-<mode>/                  ← 全局 mode-specific rules
    └── *.md
```

#### C. 项目级 `{workspace}/.roo/`(每个工作区)

```text
{workspace}/.roo/
├── mcp.json                       ← 项目级 MCP 配置(被全局覆盖)
├── commands/                      ← 项目级斜杠命令(覆盖全局同名)
│   └── *.md
├── skills/                        ← 项目级 Skills(覆盖全局同名)
│   └── <skill-name>/SKILL.md
├── rules/                         ← 项目级通用 rules
│   └── *.md
└── rules-<mode>/                  ← 项目级 mode-specific rules
    └── *.md
```

#### D. `.roomodes` 单文件(项目级 Custom Modes)

实际内容示例(节选,`C:\workspace\github\onionagent\harness\01_market_research\clone\Roo-Code\.roomodes`):

```yaml
customModes:
  - slug: translate
    name: 🌐 Translate
    roleDefinition: |
      You are Roo, a linguistic specialist focused on translating and managing localization files...
    whenToUse: Translate and manage localization files.
    description: Translate and manage localization files.
    groups:
      - read
      - command
      - - edit
        - fileRegex: (.*\.(md|ts|tsx|js|jsx)$|.*\.json$)
          description: Source code, translation files, and documentation
    source: project         # ← 标记为 project 来源
  - slug: issue-fixer
    name: 🔧 Issue Fixer
    roleDefinition: |-
      You are a GitHub issue resolution specialist focused on fixing bugs...
    whenToUse: Use this mode when you have a GitHub issue (bug report or feature request)...
    groups:
      - read
      - edit
      - command
    source: project
  ...
```

#### E + F. `.agents/`(跨 agent 共享,新引入)

`src/services/roo-config/index.ts:51-78` 引入 `~/.agents/` 和 `{cwd}/.agents/`,**专门给 Skills 用的跨 agent 共享目录**(`SkillsManager` 同时扫描 `.roo/skills` 和 `.agents/skills`):

```typescript
export function getGlobalAgentsDirectory(): string {
    return path.join(os.homedir(), ".agents")
}
export function getProjectAgentsDirectoryForCwd(cwd: string): string {
    return path.join(cwd, ".agents")
}
```

Skills 解析优先级(`src/services/skills/SkillsManager.ts:567-624`):

```
global .agents/skills  <  global .agents/skills-<mode>
   <  project .agents/skills  <  project .agents/skills-<mode>
   <  global .roo/skills     <  global .roo/skills-<mode>
   <  project .roo/skills     <  project .roo/skills-<mode>     ← 最高
```

#### G. 平台特定 MCP servers 安装目录(见 Q1 表)

#### H. 写保护文件清单

`src/core/protect/RooProtectedController.ts:14-24`:

```typescript
private static readonly PROTECTED_PATTERNS = [
    ".rooignore",
    ".roomodes",
    ".roorules*",
    ".clinerules*",
    ".roo/**",
    ".vscode/**",
    "*.code-workspace",
    ".rooprotected",
    "AGENTS.md",
    "AGENT.md",
]
```

> Agent 修改这些文件时**必须经用户批准**,无视 auto-approval 设置。这是 Roo 对 Cline 的额外加固。

#### 关键代码证据:Skills 发现

`src/services/skills/SkillsManager.ts:567-624`(`getSkillsDirectories`)展示了完整 8 路径并行扫描,实现"**project 覆盖 global,`.roo/` 覆盖 `.agents/`,mode-specific 覆盖通用**"的层次覆盖。

#### 关键代码证据:Rules / AGENTS.md 加载

`src/core/prompts/sections/custom-instructions.ts:209` 和 `407`:

```typescript
const rooDirectories = enableSubfolderRules
    ? await getAllRooDirectoriesForCwd(cwd)
    : getRooDirectoriesForCwd(cwd)

for (const rooDir of rooDirectories) {
    const modeRulesDir = path.join(rooDir, `rules-${mode}`)
    if (await directoryExists(modeRulesDir)) {
        const files = await readTextFilesFromDirectory(modeRulesDir)
        ...
    }
}
```

加载顺序:
1. `~/.roo/rules/`
2. `{workspace}/.roo/rules/`
3. (可选)子文件夹 `.roo/rules/`
4. 如果上面都没有,回退到 `.roorules` / `.clinerules` 旧文件

AGENTS.md 加载(`custom-instructions.ts:331-353`):根目录 + 启用 subfolder 时所有含 `.roo/` 的子目录,**且永远加载 `AGENTS.local.md` 作为个人 override**(即使 `AGENTS.md` 不存在)。

#### 关键代码证据:MCP 双层配置

`src/services/mcp/McpHub.ts:594-604`:

```typescript
private async getProjectMcpPath(): Promise<string | null> {
    const workspacePath = this.providerRef.deref()?.cwd ?? getWorkspacePath()
    const projectMcpDir = path.join(workspacePath, ".roo")
    const projectMcpPath = path.join(projectMcpDir, "mcp.json")
    try {
        await fs.access(projectMcpPath)
        return projectMcpPath
    } catch {
        return null
    }
}
```

**项目 MCP 文件路径是 `{workspace}/.roo/mcp.json`(不是 `.mcp.json` 也不是根目录的 `.roo/mcp.json` 之外的路径)。**

全局 MCP 在 `{settings}/mcp_settings.json`(`McpHub.ts:487-509`):

```typescript
async getMcpSettingsFilePath(): Promise<string> {
    const mcpSettingsFilePath = path.join(
        await provider.ensureSettingsDirectoryExists(),     // ← {settings} = getSettingsDirectoryPath()
        GlobalFileNames.mcpSettings,                       // = "mcp_settings.json"
    )
    ...
}
```

加载时**先全局后项目,项目可以追加到全局**(`McpHub.ts:549`、`410-413`):

```typescript
const configPath = source === "global" ? await this.getMcpSettingsFilePath() : await this.getProjectMcpPath()
```

#### 关键代码证据:Custom Modes 双源

`src/core/config/CustomModesManager.ts:356-405`(`getCustomModes`):
1. 读 `{settings}/custom_modes.yaml`(全局)
2. 读 `{workspace}/.roomodes`(项目)
3. 合并:**项目 modes 优先**(相同 slug 覆盖),标记 `source: "project"` 或 `"global"`

`customModes: source` 字段语义:`src/core/config/CustomModesManager.ts:215`:

```typescript
const source = isRoomodes ? ("project" as const) : ("global" as const)
return result.data.customModes.map((mode) => ({ ...mode, source }))
```

文件监听(`CustomModesManager.ts:308-352`):`onDidChange` / `onDidCreate` / `onDidDelete` 三件套同时监听 `custom_modes.yaml` 和 `.roomodes`,改动后**重新 merge 并写入 `globalState.customModes` cache**。

#### 关键代码证据:Task History per-task 文件

`src/core/task-persistence/TaskHistoryStore.ts:9-23`:

```typescript
/**
 * Each task's HistoryItem is stored as an individual JSON file in its
 * existing task directory (`globalStorage/tasks/<taskId>/history_item.json`).
 * A single index file (`globalStorage/tasks/_index.json`) is maintained
 * as a cache for fast list reads at startup.
 */
```

文件:
- `globalStorage/tasks/<taskId>/api_conversation_history.json` — API 消息(Anthropic.MessageParam 数组)
- `globalStorage/tasks/<taskId>/ui_messages.json` — Webview UI 消息
- `globalStorage/tasks/<taskId>/task_metadata.json` — TaskMetadata(number, ts, tokensIn/Out, totalCost, size, workspace, mode, apiConfigName, status)
- `globalStorage/tasks/<taskId>/history_item.json` — HistoryItem(id, rootTaskId, parentTaskId, number, ts, task, tokensIn/Out, cacheWrites/Reads, totalCost, size, workspace, mode, apiConfigName, status)
- `globalStorage/tasks/_index.json` — 全量 HistoryItem 数组(version=1, updatedAt, entries)

#### 关键代码证据:Checkpoints

`src/core/checkpoints/index.ts:55-75`:

```typescript
const workspaceDir = task.cwd || getWorkspacePath()
const globalStorageDir = provider?.context.globalStorageUri.fsPath
const options: CheckpointServiceOptions = {
    taskId: task.taskId,
    workspaceDir,
    shadowDir: globalStorageDir,    // ← shadowDir = globalStorage
    log,
}
```

→ 每个 task 在 `globalStorage/checkpoints/<taskId>/.git/` 下维护一个 git 影子仓库,通过 git 提交/恢复实现 checkpoint。

---

### Q3. 工作区创建 — **隐式创建,首次访问时落盘**

Roo Code **没有显式 init 命令**(`roo-cline.init` 之类),所有目录和文件都是 **首次访问时按需创建**(lazy / on-demand)。这与 Cline 一致,但比 Cline 多出 `~/.roo/` 一层。

#### 创建时机表

| 路径/文件 | 何时创建 | 证据 |
|---|---|---|
| `context.globalStorageUri/` | VS Code 第一次激活扩展时自动建 | 由 VS Code 决定 |
| `<globalStorage>/tasks/` | 第一次创建 task 时 `getTaskDirectoryPath` 调 `fs.mkdir(taskDir, { recursive: true })` | `src/utils/storage.ts:53-58` |
| `<globalStorage>/settings/` | `ensureSettingsDirectoryExists` → `getSettingsDirectoryPath` → `fs.mkdir({ recursive: true })` | `src/utils/storage.ts:62-69`、`src/utils/globalContext.ts:5-7` |
| `<globalStorage>/cache/` | 首次 `getCacheDirectoryPath` 调用 | `src/utils/storage.ts:72-78` |
| `<globalStorage>/settings/custom_modes.yaml` | `CustomModesManager.getCustomModesFilePath`:文件不存在时 `fs.writeFile(filePath, yaml.stringify({ customModes: [] }))` | `src/core/config/CustomModesManager.ts:249-257` |
| `<globalStorage>/settings/mcp_settings.json` | `McpHub.getMcpSettingsFilePath`:文件不存在时写入 `{"mcpServers":{}}` | `src/services/mcp/McpHub.ts:487-509` |
| `~/.roo/` | **不主动创建**;只在用户/扩展写文件时由 `fs.mkdir({ recursive: true })` 顺带建 | `src/services/skills/SkillsManager.ts:412` 等多处 |
| `~/.roo/commands/` 等 | 扫描时不存在不会报错,只是没有 commands | `src/services/command/commands.ts:301-302` |
| `{workspace}/.roomodes` | **不主动创建**;只有用户通过 UI/手写才存在 | 无创建代码,只有读取+监听 |
| `{workspace}/.roo/mcp.json` | 同上 | `getProjectMcpPath:594-604` 只 `fs.access` 检查 |
| `{workspace}/.roo/commands/` / `skills/` / `rules/` / `rules-<mode>/` | **不主动创建**;扫描时不存在正常返回空 | 多处 `try { readdir } catch {}` 模式 |
| `{workspace}/.rooignore` | **不主动创建**;用户手写 | 无创建代码 |
| `<globalStorage>/checkpoints/<taskId>/.git/` | 第一次 checkpoint 时 `RepoPerTaskCheckpointService.create` 初始化 | `src/core/checkpoints/index.ts:96-101` |
| `<globalStorage>/roo-index-cache-<hash>.json` | 第一次 `CacheManager.initialize()` 写入;**初始为 `{}`** | `src/services/code-index/cache-manager.ts:32-46` |
| **MCP servers 安装目录** | `ensureMcpServersDirectoryExists` 第一次调用时 `fs.mkdir({ recursive: true })` | `src/core/webview/ClineProvider.ts:1544-1565` |

#### 关键代码证据:`custom_modes.yaml` 隐式创建

`src/core/config/CustomModesManager.ts:248-257`:

```typescript
public async getCustomModesFilePath(): Promise<string> {
    const settingsDir = await ensureSettingsDirectoryExists(this.context)
    const filePath = path.join(settingsDir, GlobalFileNames.customModes)
    const fileExists = await fileExistsAtPath(filePath)
    if (!fileExists) {
        await this.queueWrite(() => fs.writeFile(filePath, yaml.stringify({ customModes: [] }, { lineWidth: 0 })))
    }
    return filePath
}
```

→ **不是 init 命令触发**,而是第一次**任何人读 Custom Modes**时:`getCustomModes` → `getCustomModesFilePath` → 文件不存在就写一个空的 `{customModes: []}`。

#### 关键代码证据:`mcp_settings.json` 隐式创建

`src/services/mcp/McpHub.ts:487-509`:

```typescript
async getMcpSettingsFilePath(): Promise<string> {
    ...
    const mcpSettingsFilePath = path.join(
        await provider.ensureSettingsDirectoryExists(),
        GlobalFileNames.mcpSettings,
    )
    const fileExists = await fileExistsAtPath(mcpSettingsFilePath)
    if (!fileExists) {
        await fs.writeFile(
            mcpSettingsFilePath,
            `{
  "mcpServers": {

  }
}`,
        )
    }
    return mcpSettingsFilePath
}
```

→ 第一次任何 MCP 操作时,自动建空配置。

#### 关键代码证据:`globalStorage/settings/` 目录

`src/utils/storage.ts:62-69`:

```typescript
export async function getSettingsDirectoryPath(globalStoragePath: string): Promise<string> {
    const basePath = await getStorageBasePath(globalStoragePath)
    const settingsDir = path.join(basePath, "settings")
    await fs.mkdir(settingsDir, { recursive: true })
    return settingsDir
}
```

→ **任何写 settings 的操作都先 mkdir -p**,所以 `settings/` 目录第一次访问时自动建。

#### 关键代码证据:`customStoragePath` 用户引导

`src/package.json:139-141` 注册命令 `roo-cline.setCustomStoragePath`,由 `promptForCustomStoragePath()`(`src/utils/storage.ts:84-150`)实现:
- 弹输入框
- 验证必须**绝对路径**
- `ConfigurationTarget.Global` 持久化
- 测试可写性,失败时回退到默认路径并报错

→ 这是 Roo 给用户的"**显式改变 backend 位置**"的入口,**但没有 init 流程**。

#### 关键代码证据:`.roomodes` 不主动创建

`getWorkspaceRoomodes`(`CustomModesManager.ts:96-103`):

```typescript
private async getWorkspaceRoomodes(): Promise<string | undefined> {
    const workspaceFolders = vscode.workspace.workspaceFolders
    if (!workspaceFolders || workspaceFolders.length === 0) {
        return undefined
    }
    const workspaceRoot = getWorkspacePath()
    const roomodesPath = path.join(workspaceRoot, ROOMODES_FILENAME)
    const exists = await fileExistsAtPath(roomodesPath)
    return exists ? roomodesPath : undefined
}
```

→ 只检查文件是否存在,**绝不创建**。`watchCustomModesFiles` 中有 `roomodesWatcher = vscode.workspace.createFileSystemWatcher(roomodesPath)`,**监听的是还不存在的路径**,一旦用户手写或 UI 写入就能立即反应。

#### `.clinerules` 兼容(回退)

`src/core/prompts/sections/custom-instructions.ts:228-237`:

```typescript
// Fall back to existing behavior for legacy .roorules/.clinerules files
const ruleFiles = [".roorules", ".clinerules"]
for (const file of ruleFiles) {
    const content = await safeReadFile(path.join(cwd, file))
    if (content) {
        return `\n# Rules from ${file}:\n${content}\n`
    }
}
```

模式化也有:`.roorules-${mode}` → `.clinerules-${mode}` 回退链(`custom-instructions.ts:425-435`)。

#### 关键代码证据:子文件夹自动发现

`src/services/roo-config/index.ts:170-230`:`discoverSubfolderRooDirectories` 用 **ripgrep 扫描 `**/.roo/**`** 自动发现工作区下任意层级的子项目 `.roo/`(默认禁用,需 `enableSubfolderRules = true` 启用)。

> 这是一个**真正的"工作区即配置源"**设计:monorepo 子包各自有 `.roo/`,无需用户配置即可被 Roo 加载。

#### 总结:工作区创建流程图

```
VS Code 启动
    │
    ▼
activate(context) [src/extension.ts:90]
    │
    ├── ContextProxy.getInstance(context)  [src/core/config/ContextProxy.ts]
    │     └─ globalState/secrets 预热
    │
    ├── ClineProvider 构造
    │     ├─ ensureMcpServersDirectoryExists() ─→ 平台特定 MCP 目录
    │     └─ taskHistoryStore.initialize() ─→ tasks/_index.json
    │
    ├── CodeIndexManager (每个 workspace folder)
    │     └─ cacheManager.initialize() ─→ roo-index-cache-*.json
    │
    └── 用户第一次操作触发:
          │
          ├── 打开/创建 task
          │     └─ getTaskDirectoryPath ─→ tasks/<taskId>/(*.json)
          │
          ├── 切换/查看 Mode
          │     ├─ CustomModesManager.getCustomModes()
          │     │     └─ getCustomModesFilePath ─→ settings/custom_modes.yaml(空)
          │     └─ getWorkspaceRoomodes ─→ .roomodes(只读,不创建)
          │
          ├── 配置 MCP
          │     └─ McpHub.getMcpSettingsFilePath ─→ settings/mcp_settings.json(空)
          │
          ├── 使用 Skill
          │     └─ SkillsManager.createSkill ─→ {global,project}/.roo/skills/<name>/SKILL.md
          │
          ├── 写 Command
          │     └─ (UI 操作) ─→ {global,project}/.roo/commands/<name>.md
          │
          └── 触发 Checkpoint
                └─ RepoPerTaskCheckpointService.create ─→ globalStorage/checkpoints/<taskId>/.git/
```

---

## 3. 关键代码片段(摘录)

### 3.1 全局 `.roo/` 路径解析

`src/services/roo-config/index.ts:21-27`:

```typescript
export function getGlobalRooDirectory(): string {
    const homeDir = os.homedir()
    return path.join(homeDir, ".roo")
}
```

### 3.2 工作区路径(跟随 VS Code)

`src/utils/path.ts:106-113`:

```typescript
export const getWorkspacePath = (defaultCwdPath = "") => {
    const cwdPath = vscode.workspace.workspaceFolders?.map((folder) => folder.uri.fsPath).at(0) || defaultCwdPath
    const currentFileUri = vscode.window.activeTextEditor?.document.uri
    if (currentFileUri) {
        const workspaceFolder = vscode.workspace.getWorkspaceFolder(currentFileUri)
        return workspaceFolder?.uri.fsPath || cwdPath
    }
    return cwdPath
}
```

### 3.3 `customStoragePath` 接管 base

`src/utils/storage.ts:14-48`:

```typescript
export async function getStorageBasePath(defaultPath: string): Promise<string> {
    let customStoragePath = ""
    try {
        const config = vscode.workspace.getConfiguration(Package.name)
        customStoragePath = config.get<string>("customStoragePath", "")
    } catch (error) { return defaultPath }
    if (!customStoragePath) return defaultPath
    try {
        await fs.mkdir(customStoragePath, { recursive: true })
        await fs.access(customStoragePath, fsConstants.R_OK | fsConstants.W_OK | fsConstants.X_OK)
        return customStoragePath
    } catch (error) { return defaultPath }
}
```

### 3.4 Custom Modes 双源合并(项目优先)

`src/core/config/CustomModesManager.ts:356-405`(`getCustomModes` 关键逻辑):

```typescript
public async getCustomModes(): Promise<ModeConfig[]> {
    const settingsPath = await this.getCustomModesFilePath()
    const settingsModes = await this.loadModesFromFile(settingsPath)
    const roomodesPath = await this.getWorkspaceRoomodes()
    const roomodesModes = roomodesPath ? await this.loadModesFromFile(roomodesPath) : []

    const projectModes = new Map<string, ModeConfig>()
    const globalModes = new Map<string, ModeConfig>()

    for (const mode of roomodesModes) {
        projectModes.set(mode.slug, { ...mode, source: "project" as const })
    }
    for (const mode of settingsModes) {
        if (!projectModes.has(mode.slug)) {
            globalModes.set(mode.slug, { ...mode, source: "global" as const })
        }
    }

    const mergedModes = [
        ...roomodesModes.map((mode) => ({ ...mode, source: "project" as const })),
        ...settingsModes
            .filter((mode) => !projectModes.has(mode.slug))
            .map((mode) => ({ ...mode, source: "global" as const })),
    ]
    await this.context.globalState.update("customModes", mergedModes)
    ...
}
```

### 3.5 Task History per-task 文件 + 索引

`src/core/task-persistence/TaskHistoryStore.ts:56-90`(`initialize`):

```typescript
async initialize(): Promise<void> {
    try {
        const tasksDir = await this.getTasksDir()
        await fs.mkdir(tasksDir, { recursive: true })
        await this.loadIndex()                  // 读 _index.json
        await this.reconcile()                  // 校准 cache vs 磁盘
        this.startWatcher()                     // fs.watch 监听
        this.startPeriodicReconciliation()      // 5 分钟兜底
    } finally {
        this.resolveInitialized()
    }
}
```

`src/core/task-persistence/TaskHistoryStore.ts:367-374`(`getTasksDir`):

```typescript
private async getTasksDir(): Promise<string> {
    const basePath = await getStorageBasePath(this.globalStoragePath)
    return path.join(basePath, "tasks")
}
```

### 3.6 Skills 8 路径优先级

`src/services/skills/SkillsManager.ts:567-624`(`getSkillsDirectories`,节选):

```typescript
// Global .agents (lowest priority)
dirs.push({ dir: path.join(globalAgentsDir, "skills"), source: "global" })
for (const mode of modesList) {
    dirs.push({ dir: path.join(globalAgentsDir, `skills-${mode}`), source: "global", mode })
}

// Project .agents
if (projectAgentsDir) {
    dirs.push({ dir: path.join(projectAgentsDir, "skills"), source: "project" })
    for (const mode of modesList) {
        dirs.push({ dir: path.join(projectAgentsDir, `skills-${mode}`), source: "project", mode })
    }
}

// Global .roo (higher than .agents)
dirs.push({ dir: path.join(globalRooDir, "skills"), source: "global" })
for (const mode of modesList) {
    dirs.push({ dir: path.join(globalRooDir, `skills-${mode}`), source: "global", mode })
}

// Project .roo (highest)
if (projectRooDir) {
    dirs.push({ dir: path.join(projectRooDir, "skills"), source: "project" })
    for (const mode of modesList) {
        dirs.push({ dir: path.join(projectRooDir, `skills-${mode}`), source: "project", mode })
    }
}
```

### 3.7 写保护文件清单

`src/core/protect/RooProtectedController.ts:14-24`:

```typescript
private static readonly PROTECTED_PATTERNS = [
    ".rooignore",
    ".roomodes",
    ".roorules*",
    ".clinerules*",
    ".roo/**",
    ".vscode/**",
    "*.code-workspace",
    ".rooprotected",
    "AGENTS.md",
    "AGENT.md",
]
```

### 3.8 `enableSubfolderRules` 启用 ripgrep 子文件夹扫描

`src/core/prompts/sections/custom-instructions.ts:209`:

```typescript
const rooDirectories = enableSubfolderRules
    ? await getAllRooDirectoriesForCwd(cwd)        // 包含子文件夹
    : getRooDirectoriesForCwd(cwd)                  // 仅 global + project root
```

`src/services/roo-config/index.ts:215-228`(ripgrep 扫描核心):

```typescript
const args = [
    "--files", "--hidden", "--follow",
    "-g", "**/.roo/**",
    "-g", "!node_modules/**",
    "-g", "!.git/**",
    cwd,
]
const results = await executeRipgrep({ args, workspacePath: cwd })
```

---

## 4. 与 Onion Agent 设计的关联

> Onion Agent 的"洋葱架构":智能体一切活动围绕 `session.json` 上下文历史文件,Agent Loop 是围绕 session 文件的自动累加器。

### 4.1 可以借鉴的设计

| Roo Code 设计 | 价值 | Onion Agent 可借鉴点 |
|---|---|---|
| **`~/.roo/` 全局用户目录** | 跨项目共享配置(global rules / commands / skills / modes) | Onion Agent 可设 `~/.onion-agent/` 全局配置目录,放置 global rules / global commands |
| **`.roomodes` 单文件声明式 Custom Modes** | 极简,git-friendly,跨机器复制 | Onion Agent 的 `~/.onion-agent/session.md`(类比) + 项目级 `.onion-modes.yaml`(类比 `.roomodes`) |
| **双层覆盖:项目优先于全局,合并而非替换** | 单源真相 + 多级 override | Onion Agent 的 session.md 应是项目级(跟 `git`),但允许 `~/.onion-agent/global-session.md` 提供 baseline |
| **per-task 文件 + 索引缓存** | 单 task 失败不影响全局,可并发写 | Onion Agent 的 `session.json` 可拆为 `sessions/<taskId>/context.json` + `sessions/_index.json`,避免单文件膨胀 |
| **`safeWriteJson` + `proper-lockfile` 跨进程锁** | 防止多窗口写入冲突 | Onion Agent 多窗口打开同一 session 时必须防止 race,需 `proper-lockfile` 或文件锁 |
| **写保护文件清单** | 自动拒绝 agent 自我修改配置 | Onion Agent 应保护 `session.md` / `.onion-modes.yaml` / `.onion/` 整树,要求用户显式批准 |
| **Skills(类 Claude Skills)+ 8 路径优先级** | skills 可重载、可按 mode 限定、可跨 agent 共享 | Onion Agent 可借 `~/.onion-agent/skills/` + `{cwd}/.onion-agent/skills/`(命名规则 `.onion-agent` 而非 `.agents`) |
| **AGENTS.md + AGENTS.local.md 双层** | 项目规则共享 + 个人 override 不入 git | Onion Agent 可兼容此模式(`AGENTS.md` 是行业标准) |
| **`.clinerules` 兼容回退** | 老用户无感迁移 | Onion Agent 可不提供旧兼容,但应预留 1-2 个"通用规则文件名"hook |
| **mcp.json / mcp_settings.json 双层** | 全局 MCP + 项目 MCP,项目可追加 | Onion Agent 的 MCP 配置可直接复用此模式 |
| **`customStoragePath` 用户可改 base** | 用户自选 backend 位置(信创合规、外接网盘、加密卷) | Onion Agent 应有等价 `customStoragePath`(`onionAgent.storagePath`),信创场景强需求 |
| **ripgrep 子文件夹发现** | monorepo 子包自动识别 | Onion Agent 的 `enableSubfolderRules` 可借鉴 |
| **Checkpoint 用 git shadow 仓库** | 不污染用户工作区,基于 git 自然 diff | Onion Agent 可用 `sessions/<taskId>/.git/` 影子仓库,与 Cline/Roo 兼容 |
| **跨 agent `.agents/` 共享** | 同一个项目的 rules/skills 跨 Cursor/Cline/Roo 共享 | Onion Agent 应主动 follow 此规范,把"项目规则"放在 `.agents/` 行业标准路径 |

### 4.2 应该规避的坑

| Roo Code 的坑 | 描述 | Onion Agent 应规避 |
|---|---|---|
| **macOS MCP dir 残留 "Cline" 命名** | fork 没清理,`~/Documents/Cline/MCP` | 新项目从第一天起就用一致命名,不混用历史包袱 |
| **MCP servers 目录与 `customStoragePath` 不联动** | 设置 `customStoragePath` 后 MCP servers 仍装在原位置 | MCP servers 目录也应受 `customStoragePath` 控制,或至少有独立 `customMcpPath` |
| **8 路径 Skills 优先级** | 用户搞不清"我加了 skill 为啥没生效" | 文档必须明确"覆盖矩阵",UI 要显示"实际生效来源" |
| **`.roomodes` + `custom_modes.yaml` 两份配置** | 用户不知道哪个生效 | Onion Agent 的 Custom Modes 应该有 **单源** 设计,或明确 UI 提示 |
| **每 mode 一目录 `rules-<mode>/`** | 文件数量爆炸,管理成本高 | 评估用 frontmatter 单文件分块 vs 多目录;以易管理为先 |
| **`globalState` 与 per-task 文件双写** | 历史原因(per-task 是源,globalState 是降级兼容) | Onion Agent 第一天就上 per-task,**不要混入 `context.globalState` 存 session** |
| **写保护清单不包含 `.roomotes.yml`**(虽 `.roomodes` 在内) | 容易把同名变体遗漏 | Onion Agent 的写保护清单应由 `git ls-files` + 显式声明共同决定 |
| **`.agents/` 同时支持全局和项目** | 多了一层路径,加剧用户认知负担 | Onion Agent 初期可只支持 `{cwd}/.onion-agent/`,后续再加全局 |

### 4.3 与 Onion 哲学对齐

- **Roo 的 per-task 文件 + index** 与 Onion 的 "session 自动累加器" 哲学 **高度一致**:Roo 把"每个 task = 一棵文件树",Onion 把"每个 session = 一个 `session.json`"。Roo 的 per-task 拆分是 Onion 单文件哲学的**演进方向**——当单文件过大时必须拆分。
- **Roo 的双层 `~/.roo/` + `{cwd}/.roo/`** 是 Onion "session 是 single source of truth" 的扩展:**user-level + project-level 双源真相**。Onion Agent 可保持单源(session),但允许 user-level baseline(类似 `git config --global`)覆盖。
- **Roo 的写保护** 与 Onion 的"agent 不可改 session"哲学一致:但 Onion 应该更严——**session 文件本身**也应受保护,任何修改都需 explicit `commit`(类似 git)。

---

## 5. 不确定 / 未找到

| 项 | 说明 |
|---|---|
| **`.rooignore` 的实际作用** | `RooProtectedController.PROTECTED_PATTERNS` 里有 `.rooignore`,但未找到"读取并过滤文件读取"的实现。推测用于 LLM 工具过滤,但**未在本调研中确认**。建议在 Agent Loop 工具执行层搜索。 |
| **`.roo/roomotes.yml` 的实际用途** | 本仓库有该文件,内容是 `commands: - name: ... run: pnpm install`,但**未在源码中看到对 `roomotes.yml` 的读取逻辑**。可能属于外部 CI/发布工具,非 Roo 运行时使用,或已废弃。 |
| **`roomotes.yml` 与 `commands/` 的关系** | 是否为 commands 的 manifest?未确认。 |
| **`AGENTS.md` 是否受 `enableSubfolderRules` 控制** | 在 `loadAllAgentRulesFiles` 中,默认不启用 subfolder 时只读根目录;启用后扫描所有含 `.roo/` 的子目录(通过 `getAgentsDirectoriesForCwd`)。**这点很微妙**——子目录必须有 `.roo/` 才会被扫到,与 rules/skills 的"任意子文件夹"扫描不同。 |
| **`commands/` 的 frontmatter `mode` 字段** | 看到 `commit.md` 的 `mode: code`,但未在 commands.ts 中找到"按当前 mode 过滤可用 commands"的逻辑。猜测是 UI 标记用,实际匹配由 LLM 自行判断。 |
| **`.rooignore` 加载与使用** | `RooProtectedController` 只列出文件名,**未找到读取并应用到工具过滤的实现**。可能通过其他 ignore 模块(如 `ignore` npm)加载,需要进一步 grep `.rooignore` 关键字。 |
| **monorepo 多 workspace folder 的处理** | `extension.ts` 给每个 folder 创建 `CodeIndexManager`,但 `ClineProvider` 似乎只用 `workspaceFolders[0]`(即 `getWorkspacePath()` 返回第一个)。**多 workspace folder 场景可能只对第一个生效**。 |
| **CLI mode(`apps/cli`)的工作区** | 仓库有 `apps/cli/`,可能命令行模式有独立工作区模型,**未在本调研中确认**。CLI 可能不依赖 VS Code ExtensionContext,直接用 `~/.roo/` + `{cwd}/.roo/`。 |
| **`getModeBySlug` 缓存失效** | `CustomModesManager.cachedModes` 缓存 10s,文件监听会 `clearCache()`,但 `enableSubfolderRules` 切换是否触发 cache 失效未确认。 |
| **`setCustomStoragePath` 对历史数据的迁移** | 用户修改 `customStoragePath` 后,旧数据是否自动迁移?代码中只看到 "fallback to default if path unusable",**未发现迁移代码**。 |

---

## 附:关键路径速查表

| 路径 | 用途 | 写? |
|---|---|---|
| `~/.roo/` | 全局用户级配置(rules/commands/skills/custom_modes) | 用户 + Roo |
| `~/.agents/` | 全局跨 agent 共享(只放 skills) | 用户 + Roo |
| `{cwd}/.roo/` | 项目级配置(rules/commands/skills/mcp.json) | 用户 + Roo |
| `{cwd}/.roomodes` | 项目级 Custom Modes 单文件 | 用户 |
| `{cwd}/.rooignore` | (推测)项目级文件过滤 | 用户 |
| `{cwd}/AGENTS.md` | 行业标准项目规则(优先 Roo 私有) | 用户 |
| `{cwd}/AGENTS.local.md` | 个人 override(不入 git) | 用户 |
| `{cwd}/.roorules` / `.clinerules` | 旧兼容,fallback | 用户 |
| `<globalStorage>/tasks/<taskId>/*.json` | per-task 持久化 | Roo |
| `<globalStorage>/tasks/_index.json` | 任务历史索引 | Roo |
| `<globalStorage>/settings/custom_modes.yaml` | 全局 Custom Modes | Roo 隐式创建 |
| `<globalStorage>/settings/mcp_settings.json` | 全局 MCP 配置 | Roo 隐式创建 |
| `<globalStorage>/cache/` | model endpoint 缓存 | Roo |
| `<globalStorage>/roo-index-cache-<sha256>.json` | Code Index 文件 hash | Roo |
| `<globalStorage>/checkpoints/<taskId>/.git/` | git shadow 仓库 | Roo |
| `%APPDATA%\Roo-Code\MCP`(Win) / `~/Documents/Cline/MCP`(macOS) / `~/.local/share/Roo-Code/MCP`(Linux) | MCP servers 安装目录 | 用户 + Roo |

---

*本调研基于 `Roo-Code` v3.53.0 本地 clone(2026-07-17),仅作 Onion Agent 设计参考。*
