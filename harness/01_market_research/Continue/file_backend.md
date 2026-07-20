# Continue — 工作区(File Backend)调研报告

> 调研对象:[continuedev/continue](https://github.com/continuedev/continue) `@ v1.3.40`(package.json 声明版本)
> 调研范围:`core/`、`extensions/vscode/`、`extensions/intellij/`、`extensions/cli/`、`binary/`、`packages/config-yaml/`、`docs/`
> 调研日期:2026-07

---

## 0. 智能体一句话定位

Continue 是**开源 IDE 编码 Agent**(VS Code / JetBrains 插件 + `cn` CLI),在 IDE 侧边栏与 TUI 中提供 Chat / Edit / Apply / Autocomplete / Agent 五种工作模式,支持本地模型(Ollama / Transformers.js)与云端模型混用,已有企业版 Continue for Teams(共享 config + RBAC)。它不是一个独立的"对话智能体",而是一个**深度嵌入 IDE 工具链的智能体运行时**——其工作区结构天然分为 **「全局」(`~/.continue/`,跨项目共享)** 和 **「项目级」(`<workspace>/.continue/` 与 `<workspace>/.continueignore`,随仓库走 Git)** 两层。

---

## 1. 调研依据

主要源码证据路径(全部位于 `C:\workspace\github\onionagent\harness\01_market_research\clone\continue\`):

| 关注点 | 文件 |
|---|---|
| 全局路径解析 + 目录创建 | `core/util/paths.ts` |
| 跨项目持久化 key/value | `core/util/GlobalContext.ts` |
| 跨工作区 ignore 解析 | `core/indexing/continueignore.ts` |
| 工作区级规则 / 提示 / agent / assistant 加载 | `core/config/loadLocalAssistants.ts`、`core/config/markdown/loadCodebaseRules.ts`、`core/config/markdown/loadMarkdownRules.ts`、`core/promptFiles/getPromptFiles.ts` |
| VS Code 端 workspace 概念 | `extensions/vscode/src/VsCodeIde.ts:293`(`getWorkspaceDirs`)、`extensions/vscode/src/util/ideUtils.ts` |
| VS Code 端 secret 存储(独立于 `~/.continue/`) | `extensions/vscode/src/stubs/SecretStorage.ts` |
| JetBrains 端全局路径 | `extensions/intellij/src/main/kotlin/com/github/continuedev/continueintellijextension/constants/ServerConstants.kt:74` |
| CLI 端 session 与 workspace | `extensions/cli/src/session.ts:50-67` |
| 官方文档(ignore / config / 目录约定) | `docs/reference/deprecated-codebase.mdx:114`、`docs/customize/deep-dives/configuration.mdx:14-37`、`docs/faqs.mdx:285-291`、`docs/customize/rules.mdx:20-22` |
| 自家使用 `.continue/` 的范例 | 仓库根目录 `.continue/`(含 `agents/` `rules/` `prompts/` `environment.json`)|

---

## 2. 三个核心问题的回答

### Q1. 工作区路径

**Continue 的「工作区」分三个独立维度,互不冲突:**

| 维度 | 路径 | 作用 | 写死 / 可配置 | 证据 |
|---|---|---|---|---|
| **全局存储**(用户主目录) | `~/.continue/`(Windows: `%USERPROFILE%\.continue\`) | config、index、session、log、dev data、secret、ignore、rules、prompts | 默认写死,可被环境变量 `CONTINUE_GLOBAL_DIR` 覆盖(相对路径基于 cwd 解析) | `core/util/paths.ts:27-35`、`extensions/intellij/.../ServerConstants.kt:74-80`、`extensions/cli/src/session.ts:48-50`、`.vscode/launch.json:24,43`、`binary/test/binary.test.ts:161-166` |
| **VS Code 扩展 globalState** | `context.globalStorageUri.fsPath`(标准 VS Code 约定,通常 `<user-data-dir>/User/globalStorage/Continue.continue/`) | 仅存**加密 API key 二进制文件**(SecretStorage) | VS Code 自己决定 | `extensions/vscode/src/stubs/SecretStorage.ts:19-22, 100` |
| **项目级工作区** | `vscode.workspace.workspaceFolders` → 转换为 URI 列表 | 当前 IDE 打开的项目根;`.continueignore`、`.continuerules`、`AGENTS.md`、项目级 `.continue/` 都在这层 | 跟随 IDE,**没有**项目级 `CONTINUE_GLOBAL_DIR` 概念 | `extensions/vscode/src/VsCodeIde.ts:293-295` |
| **CLI 工作区** | `process.cwd()` | TUI / Headless 模式下的"项目根",session 里记为 `workspaceDirectory` | 跟随当前目录,**没有** `cn --workspace` 参数(截至调研时) | `extensions/cli/src/session.ts:103, 344, 567` |

**关键结论:Continue 没有任何"项目级 override 全局路径"的设计**。所有"跨项目共享"的状态(配置、索引、session、log)都集中在 `~/.continue/`;`CONTINUE_GLOBAL_DIR` 这个 env var 主要是为**测试与本地开发**留的(`.vscode/launch.json:24`、JetBrains 单元测试 `build.gradle.kts:128`、binary 集成测试 `binary/test/binary.test.ts:161` 都把它指到沙箱目录)。

**与 Onion Agent 设计的关联**:
- 单一 `~/.continue/` 全局目录 + 多个项目级 `.continue/` 子目录 = **"全局共享 + 项目覆盖"** 的经典两级模型,Onion Agent 的 `~/.onion/` + `<workspace>/.onion/` 可直接对齐。
- Continue 选择在 `core/util/paths.ts:27` 用**模块加载期 IIFE** 而非每次调用读 env var——一次求值、整进程不变;Onion Agent 如果想在测试/多租户场景下动态切换,需要改成按调用读或显式 invalidate。
- 没有 `--workspace-dir` CLI flag 是个设计取舍:它强制 `cwd()` = 项目根,简化了"哪个项目归属哪个 session"的判断;Onion Agent 可以参考,但若支持多 workspace 复合,需要补这个能力。

---

### Q2. 工作区目录结构

#### 2.1 全局 `~/.continue/` 完整布局(由 `core/util/paths.ts:37-460` 拼装)

| 路径 | 创建时机 | 内容 | 证据 |
|---|---|---|---|
| `~/.continue/config.yaml` | **首次 `getConfigYamlPath()`** 时(且 `config.json` 不存在) | 主配置(YAML 格式,主推) | `core/util/paths.ts:119-130` |
| `~/.continue/config.json` | **不自动创建**(返回路径,等用户/UI 写入) | 旧版 JSON 配置(已被 YAML 取代) | `core/util/paths.ts:114-117` |
| `~/.continue/config.ts` | **首次 `getConfigTsPath()`** 时 | 高级用户 TS 配置(运行时编译) | `core/util/paths.ts:140-167` |
| `~/.continue/tsconfig.json` | 同上 | TS 配置编译用 | `core/util/paths.ts:176-197` |
| `~/.continue/types/`、`types/core/index.d.ts` | 同上 | 自定义 TS 配置的类型声明 | `core/util/paths.ts:146-153` |
| `~/.continue/package.json` | 同上 | 给 TS 配置兜底用,name 固定 `continue-config` | `core/util/paths.ts:154-166` |
| `~/.continue/out/config.js` | **不自动创建** | TS 编译产物,需用户执行 `cn` 或扩展触发 | `core/util/paths.ts:171-174` |
| `~/.continue/.continuerc.json` | **首次 `getContinueRcPath()`** 时,内容固定 `{ "disableIndexing": true }` | 关键作用:**禁止 Continue 索引自己的配置目录**,防止无限循环 | `core/util/paths.ts:210-224` |
| `~/.continue/.continueignore` | **首次 `getGlobalContinueIgnorePath()`** 时,初始为空文件 | 全局 ignore 规则,跨所有 workspace 生效 | `core/util/paths.ts:58-67`、`core/indexing/continueignore.ts:6-9` |
| `~/.continue/sharedConfig.json` | 不自动创建 | 加密 / 共享的次要配置 | `core/util/paths.ts:98-100` |
| `~/.continue/index/` | **首次 `getIndexFolderPath()`** 时 | 代码库索引根目录 | `core/util/paths.ts:86-91` |
| ↳ `index.sqlite` | 不自动创建 | 代码库元数据 / chunk 缓存 | `core/util/paths.ts:339-341`、`core/indexing/refreshIndex.ts:90-99` |
| ↳ `lancedb/` | 不自动创建 | 向量索引 | `core/util/paths.ts:343-345` |
| ↳ `autocompleteCache.sqlite` | 不自动创建 | tab 补全缓存 | `core/util/paths.ts:347-349` |
| ↳ `docs.sqlite` | 不自动创建 | 文档索引 | `core/util/paths.ts:351-353` |
| ↳ `globalContext.json` | **不自动创建**(GlobalContext.update 触发) | **跨项目持久化 key/value**(模型选择、上次 profile、OAuth token 等) | `core/util/GlobalContext.ts:34-58`、`core/util/paths.ts:93-95` |
| `~/.continue/sessions/` | **首次 `getSessionsFolderPath()`** 时 | 会话存储根 | `core/util/paths.ts:78-83` |
| ↳ `<sessionId>.json` | 调用 `getSessionFilePath()` 时 | 单个会话内容 | `core/util/paths.ts:102-104` |
| ↳ `sessions.json` | **首次 `getSessionsListPath()`** 时,初始 `[]` | 会话元数据列表 | `core/util/paths.ts:106-111` |
| `~/.continue/.utils/` | **首次 `getContinueUtilsPath()`** 时 | 工具资源(Chromium 快照、esbuild 二进制、repo_map) | `core/util/paths.ts:50-55` |
| ↳ `.chromium-browser-snapshots/` | 不自动创建 | 用于爬取文档站点的 Chromium | `core/util/paths.ts:46-48` |
| ↳ `esbuild` | 不自动创建 | TS config 编译用 | `core/util/paths.ts:457-459` |
| ↳ `repo_map.txt` | 不自动创建 | 仓库结构缓存 | `core/util/paths.ts:453-455` |
| `~/.continue/.migrations/` | **首次 `getMigrationsFolderPath()`** 时 | 版本迁移标记(空文件 = 已跑过) | `core/util/paths.ts:292-302` |
| `~/.continue/.configs/<hostname>/` | **首次 `getRemoteConfigsFolderPath()` / `getPathToRemoteConfig()`** 时 | 团队共享配置缓存,按 `remoteConfigServerUrl` 的 hostname 分目录 | `core/util/paths.ts:342-370` |
| ↳ `config.json` / `config.js` | 不自动创建 | 远端拉下来的 config | 同上 |
| `~/.continue/.diffs/` | **首次 `getDiffsDirectoryPath()`** 时,`{ recursive: true }` | diff 历史(看起来是 JetBrains 用的) | `core/util/paths.ts:470-478` |
| `~/.continue/dev_data/` | **首次 `getDevDataPath()`** 时 | 遥测 / 本地开发数据根 | `core/util/paths.ts:228-236` |
| ↳ `devdata.sqlite` | 不自动创建 | token 用量、chat feedback、autocomplete 统计 | `core/util/paths.ts:238-240`、`core/data/devdataSqlite.ts:75-79` |
| ↳ `<schema>/<eventName>.jsonl` | 不自动创建 | 按 schema 版本分目录的 jsonl 事件流 | `core/util/paths.ts:242-249` |
| `~/.continue/logs/` | **首次 `getLogsDirPath()`** 时 | 日志根 | `core/util/paths.ts:385-391` |
| ↳ `core.log` | 不自动创建 | Core 进程日志 | `core/util/paths.ts:393-395`、`binary/src/index.ts:13` |
| ↳ `prompt.log` | 不自动创建 | LLM 提示日志 | `core/util/paths.ts:397-399` |
| `~/.continue/prompts/` | **不自动创建** | 全局 prompt 文件(`.prompt` 递归) | `core/util/paths.ts:401-411`、`core/promptFiles/getPromptFiles.ts:66` |
| `~/.continue/rules/` | **不自动创建** | 全局规则 markdown(被 `getAllPromptFiles` 兜底扫) | `core/promptFiles/getPromptFiles.ts:69-71`、`extensions/vscode/src/extension/VsCodeExtension.ts:451`(watch 此目录) |
| `~/.continue/agents/` `assistants/` `configs/` | **不自动创建** | 7 个 BLOCK_TYPES(`models` `context` `data` `mcpServers` `rules` `prompts` `docs`)+ `agents` `assistants` `configs` 三个子目录可放可拆分的 YAML 块 | `core/config/loadLocalAssistants.ts:18-33`、`packages/config-yaml/src/load/getBlockType.ts:4-12`、`core/config/yaml/loadYaml.ts:57-71` |
| `~/.continue/permissions.yaml` | TUI 模式下用户"approve + don't ask again"时更新 | 工具调用持久授权 | `docs/cli/tool-permissions.mdx:50-57` |
| `~/.continue/.env` | 不自动创建 | 全局环境变量,被 `${{ secrets.X }}` 解析时回退使用 | `core/util/paths.ts:377-382`、`docs/faqs.mdx:289` |
| `~/.continue/.local` / `.staging` | 不自动创建 | 标记本地 / staging 环境的哨兵文件 | `core/util/paths.ts:462-468` |
| **加密 secret 单独放** | VS Code 扩展:**不**走 `~/.continue/`,而是 `context.globalStorageUri/<key>.bin`;CLI 走 `~/.continue/.env` 或 OS keychain | 解释:VS Code 端用自己的加密机制避免读旧值 | `extensions/vscode/src/stubs/SecretStorage.ts:19-23, 96-101` |

#### 2.2 项目级 `<workspace>/` 布局

| 路径 | 创建者 | 说明 | 证据 |
|---|---|---|---|
| `<workspace>/.continueignore` | **用户手动创建** | 同步 `.gitignore` 语法,VS Code 端会被 `findFiles('**/.continueignore')` 收集后转译成 `vscode.workspace.findFiles` 的 exclude glob;本地非 VS Code 路径会被 ripgrep 的 `--ignore-file .continueignore` 直接使用 | `core/indexing/continueignore.ts:11-25`、`extensions/vscode/src/VsCodeIde.ts:485-540, 562-610`、`docs/reference/deprecated-codebase.mdx:114-118` |
| `<workspace>/.continuerules` | **用户手动创建** | 单文件,内容是 system prompt 追加的 rule;只在根目录读一次 | `core/config/getWorkspaceContinueRuleDotFiles.ts:1-29` |
| `<workspace>/.continue/` | **用户手动创建** | 整体不自动创建;`createNewAssistantFile` 只在用户**点"新建 assistant"按钮**时往 `.continue/agents/` 写一个 `new-config.yaml` | `core/config/createNewAssistantFile.ts:46-66` |
| ↳ `.continue/prompts/` | 用户手动 | 项目级 prompt 文件,V2 约定;V1 用根目录 `.prompts/` | `core/promptFiles/index.ts:2-3`、`core/promptFiles/getPromptFiles.ts:13-67` |
| ↳ `.continue/rules/` | 用户手动 | 项目级规则 markdown,会被 `loadMarkdownRules` 读取 | `core/promptFiles/index.ts:4`、`core/config/markdown/loadMarkdownRules.ts:97-111` |
| ↳ `.continue/agents/<name>.yaml` | 用户手动 / 新建按钮 | 项目级 agent,会被 `loadLocalAssistants` 当作 block 拆分加载 | `core/config/createNewAssistantFile.ts:46-66`、`core/config/loadLocalAssistants.ts:78-95` |
| ↳ `.continue/assistants/`, `.continue/configs/` | 用户手动 | 同上,`assistants` / `configs` 视为 `agents` 的别名 | `core/config/loadLocalAssistants.ts:35-43` |
| ↳ `.continue/{models,context,data,mcpServers,prompts,docs}/` | 用户手动 | 任意 BLOCK_TYPE 都可拆,作为主 `config.yaml` 的 `uses:` 引用 | `core/config/yaml/loadYaml.ts:54-71`、`core/config/loadLocalAssistants.ts:18-33`、`packages/config-yaml/src/load/getBlockType.ts:4-12` |
| `<workspace>/.env` / `<workspace>/.continue/.env` | 用户手动 | secret 解析顺序:#1 workspace `.env` → #2 workspace `.continue/.env` → #3 `~/.continue/.env` → #4 process env | `docs/faqs.mdx:285-291` |
| `<workspace>/AGENTS.md` / `AGENT.md` / `CLAUDE.md` | 用户手动 | 工作区级"agent file",`loadMarkdownRules` **只读第一个找到的**,并标 `alwaysApply: true` | `core/config/markdown/loadMarkdownRules.ts:1-66` |
| `<workspace>/<任意子目录>/rules.md` | 用户手动 | 共置规则(coleset rules),`loadCodebaseRules` 用 `walkDirs` 扫整个 workspace | `core/config/markdown/loadCodebaseRules.ts:67-103`、`core/llm/rules/constants.ts`(`RULES_MARKDOWN_FILENAME`) |
| `<workspace>/.continuerc.json` | **首次 `getContinueRcPath()`** 时(但 `getContinueRcPath` 用的是全局路径,所以**项目级**的这个文件只在文档里出现,实际不在路径解析里) | 文档说"workspace-level configuration",但代码里实际**没有专门的加载路径**——只通过 VS Code 自己的 settings 序列化生效 | `docs/customize/deep-dives/configuration.mdx:34`、`core/util/paths.ts:210-224` |

#### 2.3 VS Code 扩展专属(非 `~/.continue/`,非项目级)

| 路径 | 来源 | 内容 |
|---|---|---|
| `<vscode-globalStorageDir>/Continue.continue/` | `context.globalStorageUri.fsPath` | **仅** 加密 secret 二进制文件,其他都在 `~/.continue/` |
| `context.globalState["hasBeenInstalled"]` | VS Code memento API | 仅用于激活后写"已安装"标志位(`extensions/vscode/src/activation/activate.ts:37-39`),**不**用于业务数据 |
| `context.globalState` 上的其他 key | VS Code memento API | 几乎不用,业务状态都走 `~/.continue/index/globalContext.json` |

#### 2.4 CLI 专属(`cn` 命令)

| 路径 | 证据 |
|---|---|
| `~/.continue/sessions/<uuid>.json`(主 session 存储,**复用** core 的路径) | `extensions/cli/src/session.ts:48-55` |
| `process.cwd()` 写入 session 的 `workspaceDirectory` 字段 | `extensions/cli/src/session.ts:103, 344, 567` |
| CLI 自己**不**在 cwd 下创建任何 `.continue/` 目录 | `extensions/cli/src/session.ts:48-55` 全程只引用 `~/.continue/` |

---

### Q3. 工作区创建

**结论:Continue 是「懒创建 + 显式引导」混合模型。**

#### 3.1 `~/.continue/` —— 纯懒创建,没有任何"init"命令

证据 (`core/util/paths.ts`):
- `getContinueGlobalPath()`(`paths.ts:69-76`):被任意业务函数首次调用时 `fs.mkdirSync`。
- 11 个子目录(`getIndexFolderPath`、`getSessionsFolderPath`、`getLogsDirPath`、`getDevDataPath`、`getMigrationsFolderPath`、`getRemoteConfigsFolderPath`、`getDiffsDirectoryPath`、`getContinueUtilsPath`、`getConfigTsPath`、`getContinueRcPath`、`getGlobalContinueIgnorePath`)都遵循 "**路径返回时 if-not-exists then mkdir**" 模式,没有 `init`/`setup` 入口。
- 重要的几个**关键目录**会在扩展激活时**首次**被触达:
  - `getTsConfigPath()` + `getContinueRcPath()` → 由 `extensions/vscode/src/activation/activate.ts:23-24` 显式调用,这是 VS Code 扩展启动后**最早**会落盘的全局动作。
  - `getConfigYamlPath()` → 第一次 `loadConfig` 时被调,若 `config.json` 不存在则写一份 `defaultConfig` 的 YAML。
  - `getGlobalContinueIgnorePath()` → 第一次有 ignore 解析请求时建一个空文件。
- 没有任何 `continue init`、`cn init`、`continue workspace init`、`continue setup` 之类的命令存在(全仓 grep 无结果)。

#### 3.2 项目级 `.continue/` —— **不自动创建,完全用户驱动**

证据:
- `core/config/createNewAssistantFile.ts:46-66` 是**唯一**会向 `.continue/` 写文件的代码路径,但它只在用户**点击 UI 按钮("New assistant")**时执行;默认 base 目录是 `<workspace>/.continue/agents/`。
- 没有任何代码扫描到 `<workspace>/.continue/` 不存在就自动 `mkdirSync`。
- 加载侧(`core/config/loadLocalAssistants.ts:80-83`)用 `ide.fileExists(dir)` 探测,**不存在就当空集**,不会触发创建。

#### 3.3 `.continueignore` —— **需要用户手动创建**

证据:
- `core/indexing/continueignore.ts:11-25` `getWorkspaceContinueIgArray`:try-catch 读 `${dir}/.continueignore`,失败 catch 后返回空数组,**不**创建文件。
- `core/indexing/continueignore.ts:6-9` `getGlobalContinueIgArray`:**这是唯一一个**会**主动创建**的 ignore 文件,但它是**全局** `~/.continue/.continueignore`,**不是**项目级。
- VS Code 扩展端 `VsCodeIde.ts:485-498` 用 `vscode.workspace.findFiles('**/.continueignore')` 收集,**只读不写**。
- ripgrep 路径 `VsCodeIde.ts:565, 597` 通过 `--ignore-file .continueignore` 参数使用,**依赖文件存在**;不存在 ripgrep 自动跳过,不报错。

#### 3.4 `.continuerules` —— 同样需用户手动创建

证据:
- `core/config/getWorkspaceContinueRuleDotFiles.ts:6-29` 一次 `fileExists` + `readFile`,**不**写。

#### 3.5 引导流程

唯一存在的"引导"是**模型配置引导**,不是工作区引导:
- 触发:VS Code 首次激活 + 用户开 Chat(实际入口是 `core/commands/slash/built-in-legacy/onboard.ts`,或 GUI 端的"Quickstart"按钮)。
- 行为:写 `~/.continue/config.yaml` 注入默认 provider,写 `~/.continue/prompts/` 放示例 prompt(`extensions/cli/AGENTS.md` 也提示此流程)。
- **不**创建项目级 `.continue/`、**不**创建 `.continueignore`、**不**创建 `.continuerules`。

#### 3.6 总结表

| 路径 | 创建者 | 创建时机 | 自动? |
|---|---|---|---|
| `~/.continue/` | 任意业务首次调用 | 懒 | ✅ |
| `~/.continue/config.yaml` | `getConfigYamlPath()` 首次调用且无 `config.json` | 懒 | ✅ |
| `~/.continue/.continueignore` | `getGlobalContinueIgnorePath()` 首次调用 | 懒(初始空) | ✅ |
| `~/.continue/.continuerc.json` | `getContinueRcPath()` 首次调用 | 懒(扩展激活时立即触发) | ✅ |
| `~/.continue/tsconfig.json` | `getTsConfigPath()` 首次调用 | 懒(扩展激活时立即触发) | ✅ |
| `~/.continue/{index,sessions,logs,dev_data,...}/` | 各自 getter 首次调用 | 懒 | ✅ |
| `~/.continue/.migrations/` | `migrate()` 首次调用 | 懒 | ✅ |
| 项目级 `<workspace>/.continue/` | 用户手动 | — | ❌ |
| `<workspace>/.continueignore` | 用户手动 | — | ❌ |
| `<workspace>/.continuerules` | 用户手动 | — | ❌ |
| `<workspace>/AGENTS.md` 等 | 用户手动 | — | ❌ |
| `<workspace>/.continue/agents/new-config.yaml` | UI "New assistant" 按钮 | 用户点击时 | 半自动(用户触发) |

---

## 3. 关键代码片段(可选)

### 3.1 全局路径解析(单点定义)

```typescript
// core/util/paths.ts:27-35
const CONTINUE_GLOBAL_DIR = (() => {
  const configPath = process.env.CONTINUE_GLOBAL_DIR;
  if (configPath) {
    return path.isAbsolute(configPath)
      ? configPath
      : path.resolve(process.cwd(), configPath);
  }
  return path.join(os.homedir(), ".continue");
})();
```

### 3.2 懒创建模式的标准实现

```typescript
// core/util/paths.ts:69-76  (其他 getter 全部复制此模式)
export function getContinueGlobalPath(): string {
  const continuePath = CONTINUE_GLOBAL_DIR;
  if (!fs.existsSync(continuePath)) {
    fs.mkdirSync(continuePath);
  }
  return continuePath;
}
```

### 3.3 `.continueignore` 解析

```typescript
// core/indexing/continueignore.ts
export const getGlobalContinueIgArray = () => {
  const contents = fs.readFileSync(getGlobalContinueIgnorePath(), "utf8");
  return gitIgArrayFromFile(contents);
};

export const getWorkspaceContinueIgArray = async (ide: IDE) => {
  const dirs = await ide.getWorkspaceDirs();
  return await dirs.reduce(/* 逐 workspace 读 .continueignore,容错 */);
};
```

### 3.4 工作区级定义文件统一加载

```typescript
// core/config/loadLocalAssistants.ts:78-95
export function getDotContinueSubDirs(
  ide: IDE, options: LoadAssistantFilesOptions,
  workspaceDirs: string[], subDirName: string,
): string[] {
  let fullDirs: string[] = [];
  if (options.includeWorkspace) {
    fullDirs = workspaceDirs.map((dir) =>
      joinPathsToUri(dir, ".continue", subDirName));
  }
  if (options.includeGlobal) {
    fullDirs.push(localPathToUri(getGlobalFolderWithName(subDirName)));
  }
  return fullDirs;
}
```

---

## 4. 与 Onion Agent 设计的关联

| Continue 做法 | Onion Agent 可借鉴 / 需警惕的点 |
|---|---|
| **两级目录**:`~/.continue/`(全局) + `<workspace>/.continue/`(项目) | Onion Agent 同样有"全局 + 项目"诉求,目录命名直接对齐(`.onion/` 即可);但**避免**为每个子目录各写一个 getter,参考 `paths.ts:69-460` 单文件集中定义。 |
| **纯懒创建**:`if (!exists) mkdirSync(parent)`,**零** `init` 命令 | 借鉴:Onion Agent 可以走纯懒创建;但 Onion 的"洋葱 session.json"是核心,如果它**也是懒创建**,用户首次开 agent 可能撞到空文件——可以保留"懒创建 + 模板初始内容"两段式(参考 `getConfigYamlPath` 在创建时直接写 default YAML 的做法)。 |
| **项目级 `.continue/` 完全用户驱动**,只有 UI 按钮会触发创建 `.continue/agents/new-config.yaml` | Onion Agent 如果想"开箱即用"项目级规则,可以提供一个 `onion init` 命令(Continue 没做,**是个空缺**);至少需要让"新建项目级规则/agent"有一个显式入口,避免"我写了 `.onion/rules/xxx.md` 怎么没生效"的困惑。 |
| **`CONTINUE_GLOBAL_DIR` env var 作为测试与多租户的扩展点** | Onion Agent 可以保留同样机制,支持 `ONION_HOME` env var;但要注意 `paths.ts:27` 是**模块加载时一次性求值**,无法中途切换——若需要多租户动态切换,需要改造成显式 context 注入。 |
| **`.continuerc.json { disableIndexing: true }` 防自索引** | 经典好做法,Onion Agent 若会索引自己的全局目录,**必须**做这个;否则会扫到 `~/.onion/index/` 触发无限递归。 |
| **`.continueignore` 双层**(全局 + 项目)+ gitignore 语法 | 借鉴;但 Continue 的 ignore 解析在 VS Code 端需要把项目级 ignore 转译成 `vscode.workspace.findFiles` 的 glob(因为 VS Code 远程模式不支持原生 ripgrep,见 `VsCodeIde.ts:485-540`)。Onion Agent 若不强依赖 VS Code,直接用 ripgrep 的 `--ignore-file` 就够。 |
| **`<workspace>/.continuerules` 单文件** vs **`<workspace>/.continue/rules/` 目录** | Continue 同时支持两种,V1→V2 平滑迁移;Onion Agent 一开始就定 V2 即可(只用目录,单文件不存在)。 |
| **`AGENTS.md` / `AGENT.md` / `CLAUDE.md` 兼容三种命名** | 非常好的兼容性设计;Onion Agent 可以一开始就支持 `AGENTS.md` + `ONION.md`,不要做单一强约定。 |
| **配置 / secret / 状态 / 索引 / 缓存** 五个不同生命周期的内容**混在同一个 `~/.continue/` 下** | Onion Agent 应当**主动分组**,比如 `~/.onion/{config,secrets,state,index,cache}/`,各组用不同的备份/清理策略(secret 加密、cache 可重建、state 重要、index 可重建);Continue 这种"一锅端"在企业部署时会带来备份/迁移麻烦。 |
| **JetBrains 端是 Kotlin 独立实现,代码注释明说"out of sync with core/util/paths.ts"**(见 `ServerConstants.kt:1-3`) | 强烈警示:多端实现统一路径解析是**巨大**的维护负担;Onion Agent 如果只做 CLI + 一个 IDE,**不要**复刻这种 fork,直接用一种语言实现核心 + 薄薄的 IDE 适配层。 |
| **VS Code 端把 secret 单独放 `globalStorageUri/`,不放 `~/.continue/`** | 合理:VS Code 的 `globalStorage` 在多机同步、卸载清理、远程开发场景下的行为比 `~/.continue/` 更可控;Onion Agent 若支持 VS Code,跟随同样约定。 |

---

## 5. 不确定 / 未找到

1. **`<workspace>/.continuerc.json` 的实际加载路径未在代码里找到**——文档说它是"workspace-level configuration"(`docs/customize/deep-dives/configuration.mdx:34`),但 `core/util/paths.ts:210-224` 的 `getContinueRcPath` 只返回 `~/.continue/.continuerc.json`,没看到任何代码扫描工作区级的同名文件。可能是文档与实现脱节,或由 VS Code `jsonValidation` schema 提供者(`extensions/vscode/package.json:451-453`)独立处理 JSON 编辑体验,并不参与运行时配置加载。
2. **`~/.continue/agents/` `assistants/` `configs/` 的语义差异未在代码注释中找到**——`core/config/loadLocalAssistants.ts:26` 用 `BLOCK_TYPES` + 这三个名字做 `isContinueConfigRelatedUri` 判定,但**没有**代码说明三者的功能差异;推测是历史遗留 + 用户习惯(文档多次出现 `~/.continue/agents/simple-agent.yaml`)。
3. **JetBrains 端 `CONTINUE_GLOBAL_DIR` 兼容性**——`extensions/intellij/src/main/kotlin/.../ServerConstants.kt:74-80` 的 Kotlin 实现**只**支持 `~/.continue/`,**没有**读 `CONTINUE_GLOBAL_DIR`,而 IntelliJ 测试配置 `build.gradle.kts:128` 反而设了这个 env var,**会失效**(这是注释自承的 "out of sync" 问题)。意味着 Continue 在 JetBrains 端无法支持自定义全局路径。
4. **`~/.continue/dev_data/` 在新版本里被拆成 `devdata.sqlite`(全量)+ `<schema>/<eventName>.jsonl`(legacy)**,迁移逻辑在 `migrateV1DevDataFiles()`(`paths.ts:433-444`);Onion Agent 若做类似分层存储,**最好**从一开始就用 SQLite,不要 jsonl。
5. **CLI 的 `cn` 命令行参数里没有发现 `--global-dir` 或 `--workspace` 之类覆盖 flag**——`extensions/cli/src/session.ts:50` 只读 `CONTINUE_GLOBAL_DIR` env var,意味着 CLI 用户的全局路径只能通过 env 配置,无法通过命令行临时指定。
6. **`activateExtension` 中 `context.globalState.get("hasBeenInstalled")`(`activate.ts:37-39`)实际没有 if 分支分支**——只是"set 而已",所以严格来说**没有"首次安装"的引导分支**;真正的引导在 GUI / 第一次 chat 时的 onboarding slash command 里。
