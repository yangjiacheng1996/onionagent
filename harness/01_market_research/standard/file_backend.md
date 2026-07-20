# 智能体工作区(File Backend)行业标准

> **提炼自**:GitHub 上 20 个最流行 ReAct 智能体的 file_backend 调研报告(`harness/01_market_research/<项目>/file_backend.md`)
> **提炼方法**:3 个子代理按 8-9 维度逐份阅读 + 提取模式 + 标注频次;主控在此基础上跨组整合,精选"15-20/20 高频共识"和"0-2/20 反例",形成本标准
> **提炼日期**:2026-07-18
> **配套文档**:
> - 20 份单项目报告:`harness/01_market_research/<项目目录>/file_backend.md`
> - 3 份组内提炼稿:`harness/01_market_research/_intermediate_{general_agents,coding_agents,multi_agent_frameworks}.md`
> - 顶部引用:`harness/01_market_research/top_20_react_agent.md`
> **本标准作用**:为后续 Onion Agent 工作区设计提供"必须做 / 强烈建议 / 可选 / 禁止"的决策清单

---

## 0. 文档结构

本标准按"路径策略 → 目录结构 → 创建方式 → 配置管理 → session 存储 → multi-agent → 工程化 → 沙箱安全 → 隐性约定"9 维度组织。每条标准带 4 个标签:

| 标签 | 含义 |
|----|------|
| **必须做** | 20 个项目里 ≥15 个采用,违反即成"反例" |
| **强烈建议** | 7-14 个项目采用,有清晰工程价值,新项目应当借鉴 |
| **可选** | 3-6 个项目采用,按需 |
| **禁止** | 0-2 个项目采用且明确有害,或违反会破坏信创合规 / 洋葱架构哲学 |

---

## 1. 顶层设计哲学(4 大原则)

从 20 个项目的设计反复验证,以下是**4 条横贯全局的设计原则**:

### 1.1 原则一:用户的"家"是固定的、可改的、平台原生的

> 智能体需要一个**用户属主目录**(agent's home),该目录:
> - 写死默认值(如 `~/.onion/` 或 `%LOCALAPPDATA%\onion\`)
> - 可被 **env var 一键重定向**(信创合规要求"数据不出内网"或换盘)
> - 跨平台用平台原生路径(Windows `%APPDATA%` / `LOCALAPPDATA%`,POSIX `~/.config` / `~/.local/share`)

**频次**:20/20 全部采用"用户属主目录"概念(只是有的叫 `~/.xxx/`,有的叫 `%APPDATA%/xxx/`,有的叫 IDE userData)

**典型代表**:OpenClaw(`~/.openclaw/`)/ Hermes(`~/.hermes` + `HERMES_HOME`)/ Codex(`~/.codex` + `CODEX_HOME`)/ Claude Code(`~/.claude/` + `CLAUDE_CONFIG_DIR`)/ Cline(`~/.cline/data/` + `CLINE_DIR`)

**典型反例**:
- AutoGPT platform:workspace 完全在 DB row + 远端 storage(GCS / Local),**没有本地 home**——失去 `ls` / `cat` 调试性
- Lobe Chat Desktop:生产 build **不可 env override**,信创场景反模式

**Onion 启示**:`ONION_HOME` env 必做,`~/.onion/` 默认,Windows 用 `%LOCALAPPDATA%\onion\`(Onion 不在 AppData\Roaming,而是 Local,因为 Local 不漫游、适合大文件)

### 1.2 原则二:"控制平面"与"工作区"必须分离

> 智能体的**自身元数据**(配置、secrets、state、memory、history)和**智能体操作的项目代码**应当**严格分开**,原因:
> - 智能体的"家"可以长期保留,但项目代码可以被 agent 修改/删除
> - 备份/迁移/容器化时,只备份"家"就够了
> - 信创合规要求"agent 元数据"和"项目数据"权限可能不同

**频次**:3/20 显式双层分离(OpenClaw / OpenHands / 部分 Hermes),其他 17 个混在一起(隐含的"控制平面 = 隐含的全局目录",但没显式说)

**典型代表**:
- OpenClaw:状态目录 `~/.openclaw/`(openclaw.json / SQLite / OAuth / auth-profiles)与工作区 `~/.openclaw/workspace/`(AGENTS.md / SOUL.md / memory / skills)**显式分离**
- OpenHands:控制平面 `~/.openhands/`(`OH_PERSISTENCE_DIR` 可覆盖)+ 运行时 `/workspace/project`(`sandbox_spec.working_dir` 决定)

**Onion 启示**:`~/.onion/` = 控制平面(配置/secrets/state.db/MEMORY.md 等),`<repo>/.onion/scratch/` = 项目级 scratch 目录(写入但不污染 git)——**借鉴 OpenClaw + superpowers 模式**

### 1.3 原则三:"AGENTS.md 向上扫描到 .git 边界"是行业事实标准

> 用 markdown 写项目规则,智能体启动时**从 cwd 向上扫描到 .git / 第一个 .git 父目录**,把所有 AGENTS.md / CLAUDE.md / GEMINI.md 全部加载(可设字节上限,默认 32 KiB,防 context 爆炸)。

**频次**:9/20 显式支持(Claude Code / Codex / Gemini CLI / Continue / Roo Code / Cline / Aider / opencode / superpowers)

**典型代表**:
- Codex:`project_doc_max_bytes` 默认 32 KiB,超出截断告警
- Claude Code:CLAUDE.md 可放项目根、子目录、`~/.claude/CLAUDE.md` 用户级
- Continue:`AGENTS.md` / `AGENT.md` / `CLAUDE.md` 三种命名都兼容

**典型反例**:
- opencode:只支持 `.opencode/` 目录,不直接读 AGENTS.md
- 部分项目:`.claude/` 命名污染(分支名和官方 CLI 重名)

**Onion 启示**:Onion 必须支持 `ONION.md` + `AGENTS.md` 兼容(`AGENTS.md` 优先,`ONION.md` 备选),扫描范围 cwd 向上到 `.git` 边界,字节上限 32 KiB。

### 1.4 原则四:secrets 必须独立文件 + 0o600 权限,绝不进 session

> API key / OAuth token / DB 密码 / SSH key 等**敏感凭据**必须:
> - 存**独立文件**(如 `auth.json` / `.env` / `secrets/`)
> - **chmod 0o600**(仅 owner 可读写)
> - **绝不写入 session.json / session.db**(session 是 LLM 可读的,session 泄漏 = secrets 泄漏)
> - **LLM 不可读凭证白名单**(agent 永远不能 `read` `auth.json`)

**频次**:7/20 显式独立存储(Cline / Continue / Claude Code / Hermes / AutoGPT / Lobe Chat / SuperAGI)

**典型代表**:
- Cline:`secrets.json` 0o600 单独存放,`globalState.json` 存应用设置,**两文件分离**
- Hermes:`_ROOT_CREDENTIAL_DIRS = ("pairing", "mcp-tokens")` — LLM 永远不能 read 这两个目录
- Lobe Chat:AES-256-GCM 加密 credentials

**典型反例**:
- Aider:OAuth keys 放 `~/.aider/oauth-keys.env` 但**文件权限未声明 0o600**
- 部分项目:API key 直接进 .env,被 chat history 引用

**Onion 启示**:`~/.onion/secrets/auth.json` chmod 0o600,工具层(读 secrets 的工具)要白名单验证 + 沙箱防护,LLM 永远不能 `read` `auth.json`(除非显式 invoke 工具)。

---

## 2. 路径策略(7 模式)

### 2.1 固定用户属主目录 + env 单一覆盖点【必须做】

**频次**:20/20,无一例外(但具体路径和 env 名称各异)

**典型代表**:
- Codex:`CODEX_HOME`(单一 env 覆盖点)
- Claude Code:`CLAUDE_CONFIG_DIR`(单一 env 覆盖点)
- Hermes:`HERMES_HOME`(单一 env 覆盖点)
- Cline:`CLINE_DIR`(单一 env 覆盖点)+ `--data-dir` CLI 标志
- Roo Code:`customStoragePath`(VS Code 配置项,等价 env 覆盖)
- Continue:`CONTINUE_GLOBAL_DIR`(单一 env 覆盖点)
- OpenClaw:`OPENCLAW_WORKSPACE_DIR`(env 覆盖 workspace 根)
- OpenHands:`OH_PERSISTENCE_DIR` / `FILE_STORE_PATH`(两 env 优先级)
- Gemini CLI:`GEMINI_CLI_HOME`(env 改写 `homedir()`)
- Lobe Chat CLI:`LOBEHUB_CLI_HOME`(env 覆盖)

**典型反例**:
- opencode:**5 个分散 env**(`OPENCODE_CONFIG_DIR` / `OPENCODE_CONFIG` / `OPENCODE_DB` / `OPENCODE_TEST_HOME` / `OPENCODE_DISABLE_PROJECT_CONFIG`)——用户认知负担大
- Lobe Chat Desktop:生产 build **不可 env override**——信创反模式

**Onion 启示**:`ONION_HOME` 单一 env 覆盖点,值是 Path,Windows 用 `%LOCALAPPDATA%\onion\`,POSIX 用 `~/.onion/`。**禁止用多个分散 env 替代**。

### 2.2 平台原生默认值【必须做】

**频次**:20/20

**典型实现**:
- POSIX(macOS / Linux):`~/.config/`(XDG_CONFIG_HOME)或 `~/.<app>/`(传统)
- Windows:`%APPDATA%\<app>\`(Roaming)或 `%LOCALAPPDATA%\<app>\`(Local)
- 优先级:`LOCALAPPDATA` > `APPDATA` > `$HOME/AppData/Local`

**典型反例**:
- SuperAGI:仓库根相对路径 + `os.getcwd()` 拼接,Windows 上路径分隔符会是 `/`(能跑但不符合 Windows 习惯)
- ChatDev:3 处硬编码 `Path("WareHouse")`,**完全无 env/cli 覆写**

**Onion 启示**:Onion 必须用 `platformdirs` 或 `appdirs` 库跨平台(参考 Continue / CrewAI),不要自己写分支。

### 2.3 多级覆盖链(CLI → env → 配置文件 → 默认)【强烈建议】

**频次**:13/20(2-3 层到 9 层都见过,核心是"显式优先级")

**典型代表**:
- Hermes:ContextVar per-task > `HERMES_HOME` env > 平台默认(**进程内 per-task override**,最高级)
- OpenClaw:`OPENCLAW_WORKSPACE_DIR` env > `OPENCLAW_PROFILE` > `agents.defaults.workspace` > 默认
- Codex:9 层 ConfigLayerStack(i16 排序,数字越小优先级越高)
- Gemini CLI:5 层 merge(默认 < 系统默认 < 系统 < 用户 < workspace)
- opencode:4 层 merge(config dirs + .opencode.jsonc)
- Claude Code:5 层(managed > CLI > user > project > local)

**Onion 启示**:Onion 建议 **4 层**:
1. `ONION_HOME` env(单点 override)
2. `~/.onion/onion.json` 字段
3. 项目级 `<repo>/.onion/onion.json`(项目级覆盖)
4. CLI 标志(`--home <path>`)

### 2.4 Profile 隔离(同一根下多份)【可选,按需】

**频次**:2/20 显式(OpenClaw、Hermes)

**典型代表**:
- OpenClaw:`OPENCLAW_PROFILE=work` → `~/.openclaw/workspace-work`(或 `~/.openclaw/profiles/work/`)
- Hermes:`HERMES_HOME=~/.hermes/profiles/<name>/`,**且每个子系统的"是否跨 profile 共享"是细粒度决定的**(state.db 隔离,kanban 共享)

**Onion 启示**:Onion 可选 `ONION_PROFILE=work` → `~/.onion/profiles/work/`,简化版本(不学 Hermes 的细粒度共享/隔离决策表)。

### 2.5 跟随当前目录(per-project workspace)【禁止默认,作为补充】

**频次**:8/20 默认(编程 Agent 6/7 默认跟随 cwd),12/20 不跟随(通用 Agent 7/7 不跟随 + 多 Agent/框架 1/2 跟随)

**典型代表**:
- opencode / Claude Code / Gemini CLI / Codex / Cline / Aider:默认 `process.cwd()`(CLI 形态)
- superpowers:`git rev-parse --show-toplevel` 跟随 git 根

**典型反例**:
- OpenClaw:**明确不跟随 cwd**(源码注释 + docs 都说明)
- Hermes:不写死 `~/.hermes`、**也不跟随 cwd**
- Lobe Chat:三端都不跟随 cwd

**Onion 启示**:
- Onion 是"个人助手"定位,**默认不跟随 cwd**(用户属主目录 + 项目级 scratch 目录作为补充)
- 借鉴 superpowers:`<repo>/.onion/scratch/` 作为项目级 scratch(写入但不污染 git)

### 2.6 三端隔离(Web / Desktop / CLI 各一套)【可选,按产品形态】

**频次**:1/20 显式三端(Lobe Chat)

**典型代表**:
- Lobe Chat:Web 走远程 PG/S3/Redis env,Desktop 走 Electron userData(`<appData>/lobehub-desktop/`),CLI 走 `~/.lobehub/`,**文件系统侧完全独立**

**Onion 启示**:Onion 是"CLI + Desktop"双端,**不需要 Lobe Chat 那么复杂**;建议两端共享同一 `~/.onion/`(避免跨端数据不一致)。

### 2.7 寄生于宿主 agent / DB row / 远程服务【禁止,除非特殊场景】

**频次**:3/20 部分采用(superpowers 100%、AutoGPT platform 100%、Lobe Chat Web 100%)

**典型代表**:
- superpowers:把自己装进 10 个宿主 agent 的 plugin 目录
- AutoGPT platform:workspace = `UserWorkspace` DB row,文件存 GCS bucket

**典型反例**:OpenClaw / Hermes / Codex / Claude Code / Cline / opencode:都坚持有"用户的家"

**Onion 启示**:Onion 是"自研单一产品",**必须有完整的属主目录**;不能走 superpowers 寄生模式或 AutoGPT 纯 DB 模式(失去 `ls` 调试性)。

---

## 3. 目录结构(8 模式)

### 3.1 严格三层分离(全局用户级 / 项目级 / 运行时临时)【必须做】

**频次**:10/20 显式三层,8/20 隐式(两层 + 临时),2/20 扁平

**典型代表**:
- opencode:XDG 严格四层(data / cache / config / state)+ 临时 `$TMPDIR/opencode/<shortId>/`
- Gemini CLI:`~/.gemini/`(全局)+ `<cwd>/.gemini/`(项目级,永不自动创建)+ `~/.gemini/tmp/<shortId>/`(运行时临时)
- OpenClaw:state dir + workspace + per-agent agentDir
- Claude Code:`~/.claude/`(用户级)+ `<cwd>/.claude/`(项目级)+ `~/.claude/tasks/<id>/`(运行时)

**Onion 启示**:`~/.onion/`(全局用户级)+ `<repo>/.onion/scratch/`(项目级 scratch,gitignore)+ `~/.onion/tmp/<shortId>/`(运行时临时)——三层各管各的,临时目录用 `~/.onion/tmp/<session_shortId>/`。

### 3.2 "控制平面"与"工作区"双层解耦【强烈建议】

**频次**:3/20 显式(OpenClaw、OpenHands、部分 Hermes)

**典型代表**:
- OpenClaw:状态目录 `~/.openclaw/`(openclaw.json / SQLite / OAuth)与工作区 `~/.openclaw/workspace/`(AGENTS.md / SOUL.md / memory)**显式命名分离**
- OpenHands:控制平面 `~/.openhands/`(events / settings)与运行时 `/workspace/project`(sandbox 内的代码)

**Onion 启示**:Onion 建议:
- 控制平面 `~/.onion/`(onion.json / state.db / auth.json / MEMORY.md / skills/)
- 项目级 scratch `<repo>/.onion/scratch/`(agent 在项目里写的中间产物)

### 3.3 "四类空间"按生命周期分组(活跃/缓存/快照/凭证)【强烈建议】

**频次**:1/20 显式(Hermes),其他 19 个混合

**典型代表**:
- Hermes:根布局分四类:
  - **活跃**(并发保护):`state.db`、`config.yaml`
  - **缓存**(可重生成):`image_cache/`、`logs/`
  - **快照**(永不删):`backups/`、`state-snapshots/`
  - **只读凭证**(LLM 不可写):`auth.json`、`.env`

**Onion 启示**:`~/.onion/` 内分四类:
- `state/`(活跃:state.db / session.json 镜像)
- `cache/`(可重生成:image cache / log / 临时)
- `snapshot/`(永不删:旧 session.json 备份)
- `secrets/`(只读凭证:auth.json / .env,chmod 0o600,LLM 不可读)

### 3.4 强结构化(按角色 / 数据类别 / 生命周期)【强烈建议】

**频次**:5/20 强结构化(MetaGPT / Continue / SuperAGI / CrewAI / Lobe Chat),2/20 扁平(ChatDev / Open Interpreter Python)

**典型代表**:
- MetaGPT:`<workspace>/<project>/{docs/ + resources/ + tests/ + test_outputs/ + <project_name>/源码}`
- Continue:`~/.continue/{index/ + sessions/ + logs/ + dev_data/ + .utils/ + .migrations/ + .configs/ + .diffs/ + prompts/ + rules/ + agents/}`
- CrewAI:`memory/ + knowledge/ + .checkpoints/ + logs/ + output/ + flow_states/ + base_directory/`

**Onion 启示**:Onion 建议固定结构:
```
~/.onion/
├── onion.json           # 主配置
├── onion.local.json     # 本地 override
├── state/               # 活跃 state
│   ├── session.json     # 当前 session
│   └── state.db         # SQLite(可选)
├── cache/               # 可重生成
├── snapshot/            # 旧 session 备份
├── secrets/             # 0o600,LLM 不可读
│   ├── auth.json
│   └── .env
├── memory/              # 长期记忆
│   ├── MEMORY.md
│   ├── skills/
│   └── rules/
└── tmp/<shortId>/       # 运行时临时
```

### 3.5 扁平单层(单根 + 直接子文件)【禁止】

**频次**:1/20(ChatDev)

**典型代表**:
- ChatDev:`WareHouse/<session>/{4 件套}`,扁平 1 层
- Open Interpreter Python:单例对象,几乎无文件布局

**反例原因**:扁平结构难以做备份/迁移/分类管理,违背 §3.3 四类空间原则。

**Onion 启示**:不要走扁平路线。

### 3.6 per-workspace hash 隔离【可选,多 workspace 场景】

**频次**:1/20 显式(Cline),3/20 隐式(隐式依赖 IDE 隔离)

**典型代表**:
- Cline:`workspaces/<8-char hash>/workspaceState.json`(`hashString(workspacePath)` 8 位 hex)
- Roo Code:隐式依赖 `context.globalStorageUri` 隔离(VS Code 决定)

**风险提示**:Cline 8 hex 是 32-bit,生日悖论 65k 个 workspace 就有 50% 概率碰撞

**Onion 启示**:
- Onion 建议 sha256 前 16 hex(64-bit,几乎不碰撞)
- 如果 Onion 设计为"单 user 单 workspace",可以不要这个隔离层(简化)

### 3.7 控制平面路径内嵌 user_id 隔离【强烈建议,多用户场景】

**频次**:1/20 显式(OpenHands)

**典型代表**:
- OpenHands:`~/.openhands/{user_id}/v1_conversations/{conv_hex}/{event_id}.json`

**Onion 启示**:Onion 是"单用户多 profile"模型(MVP 阶段),可以**先不做 user_id 内嵌**;P1 阶段做 `~/.onion/profiles/<profile_name>/` 就够了。

### 3.8 Bootstrap 种子文件(3-5 个最小 .md)【强烈建议】

**频次**:2/20 显式(OpenClaw、Open Interpreter Rust)

**典型代表**:
- OpenClaw:首次创建 workspace 自动 seed 9 个文件(AGENTS.md / SOUL.md / USER.md / IDENTITY.md / TOOLS.md / HEARTBEAT.md / BOOT.md / BOOTSTRAP.md / MEMORY.md),**缺失文件注入"missing file" 标记**
- Open Interpreter Rust:`AGENTS.md`(22.8 KB 工程规范)

**Onion 启示**:Onion 建议 seed **3 个最小文件**:
- `AGENTS.md`(指令 / 行为约束)
- `USER.md`(用户画像 / 偏好)
- `MEMORY.md`(长期记忆索引)

**全部大写 .md 命名**(AGENTS / USER / MEMORY)— 与 AGENTS.md 行业标准一致。

### 3.9 项目级 scratch 目录 + 自屏蔽 .gitignore【强烈建议】

**频次**:2/20 显式(superpowers、Aider 部分)

**典型代表**:
- superpowers:`.superpowers/sdd/` 和 `.superpowers/brainstorm/`,**都自屏蔽进 .gitignore**
- Aider:`check_gitignore()` 函数主动询问用户添加 + 仓库自身 `.gitignore` 双层防护

**Onion 启示**:`<repo>/.onion/scratch/` 必须在 README / setup 时主动 `.gitignore` 提示,避免污染用户 commit。

---

## 4. 工作区创建(5 模式)

### 4.1 完全隐式懒创建 + 零 init 命令【强烈建议】

**频次**:18/20 完全隐式(所有编程 Agent + 多数通用 Agent),2/20 显式 init(OpenClaw setup/onboard、CrewAI create)

**典型代表**:
- 编程 Agent:opencode / Claude Code / Gemini CLI / Codex / Cline / Roo Code / Aider / Continue / OpenHands **9/9 全部零 init**
- 通用 Agent:Hermes / AutoGPT platform / Lobe Chat Desktop / SuperAGI 多数无 init

**实现模式**:`mkdir(parents=True, exist_ok=True)`(Python)/ `fs.mkdirSync({recursive: true})`(Node.js)/ `mkdir -p`(Shell)

**典型反例**:
- OpenClaw:`openclaw setup --baseline` 显式(但**也有隐式作为 fallback**)
- CrewAI:`crewai create` 显式(但有 `~/.crewai/memory/` 隐式作为补充)
- Lobe Chat Web:`pnpm db:migrate` 显式(因为走 PG)

**Onion 启示**:`mkdir(parents=True, exist_ok=True)` 是绝对主流,Onion 走纯隐式 + 首次启动引导(认证 / folder-trust / on-boarding)。

### 4.2 IDE 扩展迁移 sentinel【可选,IDE 形态项目】

**频次**:1/20(Cline)

**典型代表**:
- Cline:VSCode `ExtensionContext.globalState` → `~/.cline/data/` 的一次性迁移用 `__vscodeMigrationVersion` sentinel 防重入

**Onion 启示**:如果 Onion 后续做 IDE 形态(目前不做),可以考虑这个;MVP 阶段不需要。

### 4.3 启动钩子注入默认数据【强烈建议】

**频次**:4/20 显式(Aider、SuperAGI、Continue、Lobe Chat Desktop)

**典型代表**:
- Aider:首次启动 `is_first_run_of_new_version` 检测,主动询问 `.aider*` 写入 `.gitignore`
- SuperAGI:`startup_event` 注入默认 user / org / workflow / toolkit
- Continue:首次 `getConfigYamlPath()` 写 default YAML
- Lobe Chat Desktop:electron-store 首次启动注入默认配置

**Onion 启示**:Onion 首次启动可以自动 seed 3 个最小文件(§3.8) + 写 `.gitignore` 提示。

### 4.4 显式 init(setup / onboard)【可选,产品向】

**频次**:2/20 显式(OpenClaw 双档、CrewAI create)

**典型代表**:
- OpenClaw:`openclaw setup --baseline`(极简,3 步)+ `openclaw onboard`(完整,含认证/folder-trust/on-boarding)
- CrewAI:`crewai create crew|flow|tool|skill <name>`,两种风格(YAML / JSON)+ 交互式 provider 选择

**Onion 启示**:Onion 可以**两步走**:
- MVP:`onion` 隐式首次启动引导(认证 + folder-trust 弹窗)
- P1:`onion onboard`(完整 onboarding,适合信创企业部署)

### 4.5 自动 `git init`【禁止默认,作为可选项】

**频次**:3/20 默认开启(MetaGPT、OpenHands、superpowers 部分)

**典型反例**:
- MetaGPT:`ProjectRepo` → `GitRepository` 触发 `git init` + 写 `.gitignore` + 初始 commit,**每个项目自动 git init**——**破坏性副作用**
- OpenHands:`init_git_in_empty_workspace=True` 默认开——**信创场景反模式**(用户可能在非 git 目录跑)

**Onion 启示**:**Onion 不要默认 `git init`**;如有需要,显式 `onion init --git` 子命令。

---

## 5. 配置与密钥管理(6 模式)

### 5.1 配置文件格式【强烈建议,JSON5/TOML/YAML 之一】

**频次**:20/20,但格式分散

**典型分布**:
- JSON / JSONC:opencode / Claude Code / Cline / Roo Code / Aider(部分) / OpenClaw(部分) / Open Interpreter Rust
- TOML:Codex / OpenHands
- YAML:Hermes / MetaGPT / CrewAI / Continue / AutoGen
- ENV:Aider 部分 / SuperAGI 部分

**Onion 启示**:Onion 建议 **JSON5**(支持注释 + 尾逗号,人机友好)+ `.local.json` 覆盖机制(参考 Claude Code 的 `settings.local.json`)。

### 5.2 多级配置 merge + 优先级排序【强烈建议】

**频次**:13/20 显式多层,7/20 单层

**典型代表**:
- Codex:9 层 ConfigLayerStack(i16 排序,数字越小优先级越高)
- Gemini CLI:5 层 merge
- opencode:4 层 merge
- Claude Code:5 层

**Onion 启示**:4 层够了(见 §2.3)。

### 5.3 secrets 独立文件 + 0o600 权限【必须做】

**频次**:7/20 显式,见 §1.4

**典型代表**:Cline / Continue / Claude Code / Hermes / AutoGPT / Lobe Chat / SuperAGI

**Onion 启示**:`~/.onion/secrets/auth.json` 0o600,**绝不进 session.json**。

### 5.4 LLM 不可读凭证白名单【必须做】

**频次**:1/20 显式(Hermes),其他 19 个通过"工具不暴露"间接实现

**典型代表**:
- Hermes:`_ROOT_CREDENTIAL_DIRS = ("pairing", "mcp-tokens")` — LLM 永远不能 read

**Onion 启示**:Onion 的 `read_file` / `write_file` 工具要**白名单校验**:`/secrets/`、`/auth.json`、`.env` 等路径 LLM 永远不能 read,需要专门工具(如 `secret_get_api_key("openai")`)。

### 5.5 加密 secrets(企业级)【可选,信创场景】

**频次**:3/20(AutoGPT、SuperAGI、Lobe Chat)

**典型代表**:
- Lobe Chat:AES-256-GCM 加密 credentials
- SuperAGI:`ENCRYPTION_KEY` env + Fernet 加密

**Onion 启示**:Onion P2 阶段可以加 AES-256-GCM 加密 secrets(参考 Lobe Chat);MVP 阶段 chmod 0o600 够了。

### 5.6 配置版本迁移 + schema 自愈【强烈建议】

**频次**:2/20 显式(Hermes 3 阶段 + Lobe Chat 129 个 migration)

**典型代表**:
- Hermes:`repair_state_db_schema` 三阶段策略(FTS rebuild → sqlite_master dedup → drop+VACUUM)+ `apply_wal_with_fallback`(NFS/SMB 自动降级)
- Lobe Chat:129 个 migration 文件(典型 Alembic 风格)

**Onion 启示**:Onion P1 阶段可以加:
- `state.db` schema 版本号 + 启动时校验
- 失败时 3 阶段自愈(FTS → dedup → VACUUM)
- WAL 不可用时降级到 rollback journal

---

## 6. session / 状态存储(6 模式)

### 6.1 单文件 session.json(append-only)【Onion 核心,强烈建议】

**频次**:3/20 部分(Aider、MetaGPT `team.json`、ChatDev 4 件套)

**典型代表**:
- Aider:`.aider.chat.history.md` 永远 append(只 chat summary 压缩,但**不写回文件**)
- MetaGPT:`Team.serialize` 全公司状态 JSON 化
- ChatDev:`<session>/{4 件套}`(node_outputs.yaml + workflow_summary.yaml + execution_logs.json + token_usage_<session>.json)

**典型反例**:
- Aider:append-only 但**不裁剪**,只影响 LLM 调用,**不写回文件**——chat history 文件越来越大
- 多数项目:不用单文件,改用 SQLite / JSONL / per-event JSON

**Onion 启示**:**`session.json` 是 Onion 的核心**(洋葱架构哲学),`session.json` 是**洋葱核心层**,SQLite / 向量库 / 状态数据库都是**基础设施层**(围绕 session.json 服务的存储后端)。具体:
- `session.json` 必做:append-only,行号定位,首尾 user prompt 标记(上下文裁剪关键)
- SQLite / JSONL 是**可选镜像**,用 `temp+rename` 原子化写盘
- chat history **必须设上限**(Lobe Chat 100 条 / Codex 软硬 cap 修剪)

### 6.2 SQLite + WAL 主流【强烈建议】

**频次**:6/20 显式 SQLite(Hermes / opencode / OpenHands / AutoGPT / SuperAGI / Lobe Chat)

**典型代表**:
- Hermes:state.db(SQLite + FTS5 + WAL,带 self-heal)
- opencode:opencode.db(SQLite + WAL,`OPENCODE_DB` 可覆盖)
- OpenHands:`v1_conversations/{conv_hex}/{event_id}.json` + 元数据 SQLite
- AutoGPT:PostgreSQL 38 表

**Onion 启示**:
- 活跃 state 走 SQLite(state.db + WAL)
- `session.json` 是"可读 + 可移植的镜像",真正活的累加仍在 SQLite(Hermes 模式)
- Onion 的"洋葱核心"是 session.json(单一文件,可读),SQLite 是镜像(快速查询)

### 6.3 per-task 文件 + index【可选,多 workspace 场景】

**频次**:2/20(Cline、Roo Code)

**典型代表**:
- Cline:`workspaces/<8-char hash>/workspaceState.json` + 隐式 index
- Roo Code:`tasks/<taskId>/*.json` + `_index.json` 显式

**Onion 启示**:如果 Onion 设计为"多任务并行",可以考虑 per-task + index;MVP 阶段单文件 session.json 够用。

### 6.4 JSONL 流式 session【可选,大 session 场景】

**频次**:4/20(Codex rollout、Continue、Gemini CLI、opencode 部分)

**典型代表**:
- Codex:`sessions/YYYY/MM/DD/rollout-...jsonl`(`O_APPEND` 原子写)
- Gemini CLI:`chats/session-YYYY-MM-DDTHH-MM-<id8>.jsonl`,子 agent 嵌套在 `<parentSessionId>/<id>.jsonl`

**Onion 启示**:Onion MVP 阶段不要走 JSONL(违反"单一 session.json"哲学);如果 session 太大,拆分为 `session_<id>.jsonl` 但保留 `session.json` 作为索引入口。

### 6.5 checkpoints / shadow git 仓库【强烈建议】

**频次**:3/20(OpenHands、Roo Code、Hermes)

**典型代表**:
- OpenHands:`FileStore` 抽象(local / S3 / GCS / memory)+ `LocalFileStore` 的 atomic write(`.tmp.{pid}.{tid}` → `fsync` → `os.replace`)
- Roo Code:`checkpoints/<taskId>/.git/`(基于 git 自然 diff)
- Hermes:Checkpoints v2 单共享 git store(`checkpoints/store/`)

**Onion 启示**:
- Onion checkpoint 可以**直接基于 session.json 自身做 snapshot**(旧版本归档到 `snapshot/session_<timestamp>.json`)
- **不基于 git**(因为 session.json 是 Onion 的"洋葱核心",不是项目代码)
- atomic write:`temp+rename`(`Path(session.json + ".tmp").write_text(...)` + `Path.replace(...)`)

### 6.6 多 Agent 状态关联【按需】

**频次**:5/20 显式多 agent 状态关联

**典型代表**:
- Codex:`spawn_agent` 共享 `state_5.sqlite` + `parent_thread_id` 串成 tree
- Gemini CLI:子 agent 嵌套在 `<parentSessionId>/<id>.jsonl`
- Roo Code:`rootTaskId` / `parentTaskId` 隐式
- Hermes:Multi-board Kanban(`<root>/kanban/boards/<slug>/` + `default board` 共享)

**Onion 启示**:
- Onion sub-agent 创建子 session 文件,与主 session 关联(`session_id` + `parent_session_id`)
- 子 session 文件可以放在 `~/.onion/sessions/<main_id>/<sub_id>.json` 形成树
- 主 session 只记录"sub-agent 的 start/end 时间 + result 摘要",完整 transcript 在子 session

---

## 7. multi-agent 协作与隔离(5 模式)

### 7.1 角色分工型(每角色 = 固定目录)【可选,固定 SOP 场景】

**频次**:2/20 显式(MetaGPT、ChatDev 1.0)

**典型代表**:
- MetaGPT:ProductManager / Architect / Engineer / QA 各角色专属子目录,共享 ProjectRepo

**Onion 启示**:如果 Onion 后续做 multi-agent 协作,可以让每个 agent 角色有独立子目录(`~/.onion/agents/<role>/`)。

### 7.2 动态编排型(YAML DAG / 拓扑配置)【可选】

**频次**:3/20(ChatDev 2.0、AutoGen、SuperAGI 部分)

**典型代表**:
- ChatDev 2.0:YAML DAG 编排(`agent` / `python` / `tooling` / `human` 4 节点类型)
- AutoGen:`RoundRobinGroupChat` / `SelectorGroupChat` / `MagenticOneGroupChat` / `Swarm` 4 种拓扑

**Onion 启示**:Onion 不预设 multi-agent 拓扑,留扩展点。

### 7.3 Manager / Hierarchical 分层委派【可选】

**频次**:2/20(CrewAI、AutoGen SelectorGroupChat)

**典型代表**:
- CrewAI:Process.hierarchical(带 manager agent)
- AutoGen:SelectorGroupChat(选下一个发言者)

**Onion 启示**:Onion 的"洋葱"哲学认为 Agent Loop 是自动累加器,不预设 manager;P2 阶段可加。

### 7.4 多 board / 多 panel(同项目多独立工作区)【可选】

**频次**:3/20(Lobe Chat workspaces、Continue assistants、SuperAGI 4 层、**Hermes Multi-board Kanban**)

**典型代表**:
- Hermes:`<root>/kanban/boards/<slug>/`(default board 共享,命名 board 隔离)
- Lobe Chat:`workspaces` 多租户

**Onion 启示**:`~/.onion/profiles/<profile>/` 作为多 board 隔离(简化的 Hermes 模式)。

### 7.5 跨 Agent 共享目录【按需】

**频次**:4/20(AutoGen、ChatDev、SuperAGI、CrewAI)

**典型代表**:
- AutoGen:共享 work_dir 靠"传同一 Executor 实例"或 Docker `bind_dir`
- ChatDev:`code_workspace/` 多 Python 节点共享
- SuperAGI:容器把项目根 `./:/app` 整个挂载

**Onion 启示**:`~/.onion/scratch/` 作为跨 sub-agent 共享目录(写时锁保护)。

### 7.6 git worktree 隔离【禁止(基于 Codex 反例)】

**频次**:1/20 误传(top_20_react_agent.md 我之前认为 Codex CLI 有,**子代理调研后纠正:没有**)

**调研纠正**:**Codex CLI 并没有"git worktree 多 Agent 隔离"**。`spawn_agent` 让子 Agent 继承父 `config.cwd` + `approval_policy` + `permission_profile`,共享同一 `state_5.sqlite`,只靠 `parent_thread_id` 串成 tree。"worktree" 在 Codex 里只出现在 `load_project_layers` 解析 linked worktree hook 路径的小技巧里。

**Onion 启示**:
- **不要基于 git worktree 做 multi-agent 隔离**(Codex 已经验证不可行)
- Onion 可以**基于 session.json 子文件做 sub-agent 隔离**(洋葱核心层的天然优势)

### 7.7 自循环模式(Stop hook 阻断 + 喂回原 prompt)【按需】

**频次**:1/20(Claude Code Ralph Wiggum)

**典型代表**:
- Claude Code:Ralph Wiggum — Stop hook 阻断 session 退出,把原 prompt 喂回,实现 session 累加器的自循环

**Onion 启示**:
- Onion 的 Agent Loop 是 session.json 自动累加器,**天然支持自循环**(不需要 hook 干预)
- sub-agent 完成时,把 result 写回主 session.json 的下一行,继续主 Agent Loop

---

## 8. 信创合规与工程化(6 模式)

### 8.1 用户可改存储根(信创合规关键)【必须做】

**频次**:19/20(只有 ChatDev 是反例,硬编码 `Path("WareHouse")`)

**典型代表**:见 §2.1

**Onion 启示**:`ONION_HOME` env 必须做。

### 8.2 跨平台路径策略【必须做】

**频次**:19/20(同 §8.1)

**典型反例**:SuperAGI 的 `os.getcwd() + "/" + path` 字符串拼接,Windows 上路径分隔符会是 `/`;ChatDev 完全不跨平台。

**Onion 启示**:用 `pathlib.Path` 或 `appdirs` / `platformdirs` 库,**绝不手写路径字符串拼接**。

### 8.3 atomic write / proper-lockfile / safeWriteJson【必须做】

**频次**:6/20 显式(Lobe Chat、AutoGen、Aider、CrewAI、OpenHands、Roo Code)

**典型代表**:
- OpenHands:`LocalFileStore` 的 atomic write(`.tmp.{pid}.{tid}` → `fsync` → `os.replace`)
- Lobe Chat:`electron-store` 自动备份 `lobehub-settings.json.bak / .tmp`
- CrewAI:路径校验防 shell 注入 + 路径穿越(禁 `..` / `~` / `$` / `| > < & ;`)

**典型反例**:
- MetaGPT `shutil.rmtree(path)` 清空旧项目(无备份,无回收站)
- ChatDev `mkdir(parents=True, exist_ok=True)` 不报错可能覆盖
- Continue `paths.ts:27` IIFE **模块加载期一次性求值**,无法中途切换全局路径

**Onion 启示**:
- `session.json` 写盘:`Path(session + ".tmp").write_text(...)` + `Path.replace(...)`
- 工具层 path traversal 防护:写文件时校验 path 必须在 `~/.onion/` 内
- 多进程:advisory lock + SQLite WAL

### 8.4 IDE 扩展迁移【可选,IDE 形态】

**频次**:2/20(Continue、Lobe Chat)

**典型代表**:Cline 的 `__vscodeMigrationVersion` sentinel 防重入

**Onion 启示**:Onion MVP 阶段不做 IDE 形态,不需要。

### 8.5 文档与代码一致性【必须做】

**频次**:典型反例 4/20(Lobe Chat、Aider、CrewAI、ChatDev)

**典型反例**:
- CrewAI:`crewai memory --storage-path` 的 help 写 "uses ./.crewai/memory",但实际走 `appdirs.user_data_dir(...)` —— **help 与代码脱节**
- ChatDev:`workflow_authoring.md:245` 提到 `context.json`,但 `GraphContext.record()` 只写 `node_outputs.yaml`
- Aider:无 `aider --init` 命令,虽然部分文档暗示有
- Lobe Chat:`INSTALL_PLUGINS_DIR = 'plugins'` 在 `apps/desktop/src/main/const/dir.ts:33` 定义但**无生产代码使用**

**Onion 启示**:**Onion 的 help 字符串必须和代码 100% 一致**,任何"显示给用户看"的字符串都从单一来源生成(常量或函数)。

### 8.6 容器化部署【按需,信创场景】

**频次**:4/20(OpenClaw、OpenHands、AutoGPT platform、SuperAGI)

**典型代表**:
- OpenClaw:沙箱默认 Docker,支持非主会话隔离
- OpenHands:Docker 沙箱,`init_git_in_empty_workspace` 等
- SuperAGI:`docker-compose.yml` 8 服务编排

**Onion 启示**:
- MVP 阶段不做容器化(Python 直接跑)
- P2 阶段加 `Dockerfile` + `docker-compose.yml`,适合信创企业部署

---

## 9. 沙箱与安全(5 模式)

### 9.1 OS 级纵深防御沙箱【可选,安全要求高的企业】

**频次**:1/20(Codex CLI)

**典型代表**:
- Codex CLI:macOS Seatbelt + Linux Landlock/seccomp + Windows Restricted Token + bubblewrap,**根据 OS 自动选 backend**,profile 不可改
- 三种权限模式:`WorkspaceWrite` / `ReadOnly` / `DangerFullAccess` / `ExternalSandbox`
- 沙箱可写根 = `cwd` + `--add-dir` 追加

**Onion 启示**:
- MVP 阶段不做 OS 沙箱(只靠 approval 询问)
- P2 阶段:借鉴 Codex 设计,Windows Restricted Token + Linux Landlock/seccomp + macOS Seatbelt

### 9.2 Docker 沙箱隔离【可选,云端部署】

**频次**:1/20(OpenHands)

**典型代表**:OpenHands 在隔离 Docker 沙箱里执行代码

**Onion 启示**:P2 阶段做,适合企业级自动化场景。

### 9.3 folder-trust 弹窗【强烈建议】

**频次**:3/20(Gemini CLI、Codex、Claude Code)

**典型代表**:
- Gemini CLI:`folderTrust.enabled` 默认 true,headless 模式阻塞报错
- Codex:`set_project_trust_level` 写入 `config.toml [projects]`
- Claude Code:`.claude/settings.json` 加载时弹信任对话框

**典型反例**:opencode / Cline / Roo Code / OpenHands 没有 folder-trust 弹窗

**Onion 启示**:**Onion 必须有 folder-trust 弹窗**(`folderTrust.enabled` 默认 true,headless 模式阻塞报错,类似 Gemini CLI)。

### 9.4 AGENTS.md 字节上限(防 context 爆炸)【必须做】

**频次**:1/20 显式(Codex `project_doc_max_bytes` 默认 32 KiB),1/20 隐式(Claude Code)

**典型反例**:**5/20 无字节上限**,AGENTS.md 写几 MB,直接吃光模型 context。

**Onion 启示**:**AGENTS.md 字节上限 32 KiB**,超出截断告警(借鉴 Codex)。

### 9.5 `/doctor` 自检命令【强烈建议】

**频次**:1/20(Codex `codex doctor` 诊断 CODEX_HOME / auth.json / log_dir),1/20 隐式(Claude Code `/doctor` slash command)

**Onion 启示**:`onion doctor` 子命令,扫描:
- ONION_HOME 路径是否可写
- auth.json 是否 0o600
- state.db 是否能正常打开
- AGENTS.md 是否超出 32 KiB
- 关键依赖(模型 API、SQLite、MCP)是否健康

---

## 10. 涌现的隐性约定(8 模式)

### 10.1 路径模板化 + 占位符替换【可选,multi-tenant 场景】

**频次**:2/20(SuperAGI、ChatDev 部分)

**典型代表**:
- SuperAGI:`workspace/input/{agent_id}/`、`workspace/output/{agent_id}/{agent_execution_id}/`,运行时 `path.replace("{agent_id}", formatted_agent_name + '_' + str(agent.id))` 替换

**典型反例**:**用 `name + id` 拼路径是脆弱设计**,改名即破坏

**Onion 启示**:Onion 不要走 `name_id` 拼路径,**只用纯 UUID / sha256 hash**。

### 10.2 `name + timestamp` 命名【可选,人类可读场景】

**频次**:2/20(ChatDev、MetaGPT)

**典型代表**:
- ChatDev:`WareHouse/<name>_<YYYYMMDDhhmmss>/`
- MetaGPT:`<METAGPT_ROOT>/workspace/<timestamp>/`(默认全新模式)

**Onion 启示**:Onion 的 session 可以用 `<session_name>_<timestamp>.json` 而非纯 UUID(人类可读 + 时间排序)。

### 10.3 gitignore 自动检查 / 防自索引【强烈建议】

**频次**:2/20(Aider、Continue)

**典型代表**:
- Aider `check_gitignore`:启动时通过 `repo.ignored(".aider")` 测试当前 `.gitignore` 是否覆盖,没覆盖就询问并自动追加
- Continue `~/.continue/.continuerc.json { disableIndexing: true }`:防止 Continue 索引自己的配置目录

**Onion 启示**:
- Onion 启动时检查 `<repo>/.onion/scratch/` 是否被 gitignore,没有就提示用户
- Onion 的 RAG 索引要**排除 `~/.onion/` 自身**,避免自索引无限递归

### 10.4 包内嵌 default config + user override【强烈建议】

**频次**:2/20(Aider、Continue)

**典型代表**:
- Aider:`aider/resources/model-metadata.json`(29057 bytes 只读默认)+ `aider/resources/model-settings.yml`(89498 bytes)+ 用户/项目覆盖文件
- Continue:`~/.continue/config.yaml` 若 `config.json` 不存在,首次 `getConfigYamlPath()` 时直接写一份 `defaultConfig` 的 YAML

**典型反例**:MetaGPT 包内只有 `config/config2.example.yaml`,用户必须**手动复制**才会生效

**Onion 启示**:**Onion 仓库放 `onion.example.json`,首次启动 cp 为 `~/.onion/onion.json`**(借鉴 OpenClaw docs 范式)。

### 10.5 多级配置/数据搜索链【强烈建议】

**频次**:2/20(Aider、Continue)

**典型代表**:
- Aider `generate_search_path_list`(`main.py:305-330`):home → git_root → cwd → command_line 的反转合并去重
- Continue:项目级 `<workspace>/.continue/` + 全局 `~/.continue/`,同名块项目级覆盖全局

**Onion 启示**:
- 配置搜索链:包内置 → `~/.onion/` → `<repo>/.onion/` → CLI/env
- 数据搜索链(AGENTS.md / skills / rules):`<repo>/` 向上到 `.git` 边界 → `~/.onion/` → 包内置默认

### 10.6 Server 端 session 持久化【按需,Web/Server 形态】

**频次**:3/20(ChatDev、Lobe Chat、AutoGen Studio)

**典型代表**:
- ChatDev **反例**:`server/services/session_store.py:67-83` 的 `WorkflowSessionStore` 是**纯内存**的,服务重启即丢
- Lobe Chat:`sessions` / `topics` / `messages` 全 PG,Server 重启无影响,支持多副本
- AutoGen Studio:`TeamManager` 进程内单例无状态(靠 DB),`WebSocketManager` 进程内单例

**Onion 启示**:Onion 是 CLI 形态,**不需要 Server 端 session**(不需要考虑这个问题)。

### 10.7 plugin / extension 系统 + hook 事件系统【按需】

**频次**:plugin 3/20(Claude Code、Codex、Cline),hook 3/20(Claude Code、Codex、Gemini CLI)

**典型代表**:
- Claude Code:13 个官方 plugin + 12 种 hook 事件(PreToolUse / PostToolUse / SessionStart / Stop / UserPromptSubmit / SubagentStop / PreCompact / Notification / InstructionsLoaded / MessageDisplay)
- Codex:`marketplaces/<name>/` + `.agents/plugins/`

**Onion 启示**:
- Onion MVP 不做 plugin 系统(先做核心)
- P2 阶段可以做 `~/.onion/plugins/`(类似 Cline 模式)

### 10.8 MCP 协议支持【强烈建议】

**频次**:6/20(Claude Code、Codex、Gemini CLI、Cline、Roo Code 等),几乎成了行业标准

**典型代表**:
- Claude Code `.mcp.json`(项目级)+ `.mcp.json` 嵌入 plugin
- Codex `config.toml [mcp_servers.<name>]`

**Onion 启示**:**Onion 必须支持 MCP 协议**,参考 Cline / Roo Code 的双层 mcp 配置:
- 用户级:`~/.onion/mcp.json`(全局)
- 项目级`<repo>/.onion/mcp.json`(项目级覆盖)

---

## 11. 20 个项目总览对照表

| 项目 | 类别 | 路径策略 | 目录层数 | 显式 init? | session 存储 | multi-agent | 沙箱 | 信创支持 | 核心差异化 |
|------|------|--------|---------|----------|-------------|------------|------|---------|----------|
| **OpenClaw** | 通用 | 固定 `~/.openclaw/`(双根分离) | 3 | setup/onboard | SQLite | per-agent agentDir | Docker | ✅ OPENCLAW_WORKSPACE_DIR | **state dir vs workspace 分离**;profile 隔离 |
| **superpowers** | 通用 | 寄生宿主 + `<repo>/.superpowers/` | 3 | ❌(零) | 多文件 | n/a | n/a | 由宿主决定 | **零运行时依赖**;10 个宿主 manifest |
| **Hermes Agent** | 通用 | 4 层链式解析(ContextVar/env/平台/profile) | 4 | `ensure_hermes_home()` | SQLite+FTS5+WAL | 共享 Kanban | 凭证白名单 | ✅ HERMES_HOME + 5 子系统 env | **细粒度 profile 共享/隔离**;ContextVar per-task override |
| **AutoGPT** | 通用 | DB row + 远端 storage(GCS/Local) | DB-only | ❌(完全隐式) | PG 38 表 | per-user | path traversal 防护 | ⚠ env 决定 backend 而非根 | **虚拟路径 vs 物理路径解耦** |
| **Lobe Chat** | 通用 | **三端隔离**(Web/Desktop/CLI) | 3 端各 3 | pnpm db:migrate(显式)/隐式 | PG+pgvector+S3 | 多租户 | AES-256-GCM | ⚠ 桌面端生产 build 不可 override | **三端隔离**;129 个 migration |
| **SuperAGI** | 通用 | 跟随 CWD + `workspace/{input,output}/` | 3 | ❌(零,容器启动 alembic) | PG 38 表 | Celery 异步并发 | n/a | ✅ config.yaml + env | **路径模板化占位符** |
| **Open Interpreter** | 通用 | Python 时代 `~/.openinterpreter/`;Rust 时代 `~/.codex/` | 2 | ❌ | JSON / JSONL rollout + State DB | 10 个 harness 切换 | n/a | ✅ env 完整 | **Python→Rust fork OpenAI Codex** 演进 |
| **opencode** | 编程 | 跟随 cwd + XDG 5 层 | 5 | ❌(零) | SQLite+WAL | build/plan/general/explore | ❌ | ⚠ 5 env 散 | **XDG 严格分层**;100% 开源 + Provider 无关 |
| **Claude Code** | 编程 | 跟随 cwd + 三层叠加(managed/user/project) | 3 | ❌(只有 `/init` slash) | hook 事件 + 命令式 | plan/build(2) | ❌(靠 approval) | ✅ CLAUDE_CONFIG_DIR | **13 个官方 plugin + 12 种 hook 事件**;Ralph Wiggum 自循环 |
| **Gemini CLI** | 编程 | 跟随 cwd(无显式 CLI 参数) | 3 | ❌(只有 `/init` slash) | JSONL 流式(per-session) | 1 个 + spawn_agent | ❌(靠 approval) | ✅ GEMINI_CLI_HOME | **folder-trust 弹窗**;4 类 memory |
| **OpenAI Codex CLI** | 编程 | `CODEX_HOME` + `--cd` + project_root | 2 | ❌(只有 `/init` slash) | 7 种 SQLite + JSONL rollout | spawn_agent(共享 state.db) | ✅ OS 级纵深 | ✅ CODEX_HOME | **Terminal-Bench 77.3% 第一**;9 层 ConfigLayer |
| **OpenHands** | 编程 | 双层(控制+运行时) | 2 | ❌(完全隐式) | per-event JSON | 1 个 + 多 workspace | ✅ Docker | ✅ OH_PERSISTENCE_DIR | **控制平面 vs 运行时工作区解耦**;FileStore 抽象(local/S3/GCS) |
| **Cline** | 编程 | `~/.cline/data/` 三层 + `CLINE_DIR` | 2 | ❌(完全隐式) | per-workspace 8-char hash | Plan/Act(2) | ❌(靠 approval) | ✅ CLINE_DIR / --data-dir | **IDE 扩展迁移 sentinel**;per-workspace 隔离 |
| **Roo Code** | 编程 | 4 层并行(VS Code + `~/.roo/` + `<cwd>/.roo/` + 平台 MCP) | 5 | ❌(完全隐式) | per-task 4 文件 + index | 4 内置 + Orchestrator + Custom | ❌(靠 approval) | ✅ customStoragePath | **5 层并行复合**;8 路径 Skills 覆盖矩阵;写保护清单 |
| **Aider** | 编程 | 跟随 git 仓库根 + `~/.aider/` | 2 | ❌(零) | `.aider.chat.history.md` append | n/a | ❌ | ✅ AIDER_* 全覆盖 | **git 强依赖**;`check_gitignore` |
| **Continue** | 编程 | `~/.continue/` + `<workspace>/.continue/` | 2 | ❌(完全隐式) | `~/.continue/sessions/<uuid>.json` | n/a(单 agent) | ❌ | ✅ CONTINUE_GLOBAL_DIR | **AGENTS.md/AGENT.md/CLAUDE.md 兼容 3 种命名**;`.continuerc.json disableIndexing` |
| **MetaGPT** | 多 Agent | 跟随项目根 + `<workspace>/<timestamp>/` | 4 | ❌(隐式 SOP 触发) | 强结构化目录 + git diff | 角色分工(PM/Arch/Eng/QA) | n/a | ⚠ env 部分 | **ProjectRepo**;SOP 顺序角色分工 |
| **AutoGen** | 多 Agent | **多工作区、零统一** | 每子系统独立 | ❌(纯隐式) | SQLite + ChromaDB + DiskCache | 4 种拓扑(RoundRobin/Selector/MagenticOne/Swarm) | MCP Filesystem Workbench | ⚠ env 部分 | **`Pydantic Component` 完美序列化**;`work_dir == cwd` deprecated |
| **CrewAI** | 多 Agent | **三层分散**(`~/.config/crewai/` + `appdirs(cwd-name)` + CWD 派生) | 5+ | ✅ `crewai create` | SQLite + LanceDB + ChromaDB | sequential / hierarchical | path traversal 防护 | ✅ env 部分 | **`@CrewBase` 自动绑定 `base_directory`**;`Task.output_file` 路径校验 |
| **ChatDev** | 多 Agent | **跟随 CWD**(硬编码 `WareHouse`) | 1 | ❌(完全隐式) | YAML+JSON 4 件套 | YAML DAG 编排 | n/a | ❌ **反例**(无 env/cli 覆写) | **扁平结构**;`fixed_output_dir=True` 复用;**Server 端 session 纯内存反例** |

---

## 12. Onion Agent 推荐组合(P0/P1/P2)

> 这一节是**给用户后续设计 Onion Agent 工作区的具体行动清单**。基于本标准 11 个维度 + 用户洋葱架构哲学,优先级如下。

### 12.1 P0(MVP 必做)

| 维度 | 具体实现 | 依据标准 |
|-----|---------|---------|
| **路径** | `ONION_HOME` env 单一覆盖点 + `~/.onion/` 默认 + Windows `%LOCALAPPDATA%\onion\` | §1.1 / §2.1 / §2.2 |
| **目录结构** | 三层分离:`~/.onion/`(全局)+ `<repo>/.onion/scratch/`(项目级 scratch,gitignore)+ `~/.onion/tmp/<shortId>/`(运行时) | §3.1 / §3.2 |
| **生命周期分组** | `~/.onion/` 内分四类:`state/`、`cache/`、`snapshot/`、`secrets/` | §3.3 |
| **创建方式** | `mkdir(parents=True, exist_ok=True)` 纯隐式 + 零 init 命令 | §4.1 |
| **配置** | JSON5 + 4 层覆盖链(ONION_HOME env → `~/.onion/onion.json` → `<repo>/.onion/onion.json` → CLI 标志) | §2.3 / §5.1 / §5.2 |
| **密钥** | `~/.onion/secrets/auth.json` chmod 0o600 + 工具层白名单(LLM 不可 read) | §1.4 / §5.3 / §5.4 |
| **session 核心** | `session.json` append-only + `temp+rename` 原子化 + 首尾 user prompt 标记 | §6.1 / §8.3 |
| **AGENTS.md 兼容** | 扫描 cwd 向上到 `.git` 边界 + 字节上限 32 KiB + `AGENTS.md` / `ONION.md` 多命名兼容 | §1.3 / §9.4 |
| **MCP 支持** | `~/.onion/mcp.json`(全局)+ `<repo>/.onion/mcp.json`(项目级) | §10.8 |
| **首启动引导** | folder-trust 弹窗(默认 true,headless 阻塞报错) + seed 3 个最小文件(AGENTS.md / USER.md / MEMORY.md) | §4.3 / §9.3 / §3.8 |
| **自检命令** | `onion doctor` 扫描 ONION_HOME / auth.json / state.db / AGENTS.md / 关键依赖 | §9.5 |
| **平台原生** | 用 `platformdirs` 库,绝不手写路径字符串拼接 | §2.2 / §8.2 |
| **避免模块级常量** | `os.getenv` + 函数返回 Path,避免 `_HERMES_HOME` 模块级缓存(导致 profile 切换失效) | §4 反对(参照 Hermes 教训) |
| **禁用功能** | 不默认 `git init`(不学 OpenHands/MetaGPT);不写死 cwd(不学 AutoGPT/ChatDev);不靠纯内存 Server session(不学 ChatDev 反例);help 字符串必须 100% 一致(不学 CrewAI) | §4.5 / §2.5 / §10.6 / §8.5 |

### 12.2 P1(MVP 后期)

| 维度 | 具体实现 | 依据标准 |
|-----|---------|---------|
| **Profile 隔离** | `ONION_PROFILE=work` → `~/.onion/profiles/work/`(简化版,学 OpenClaw) | §2.4 |
| **Bootstrap 种子** | 启动时主动检查 `<repo>/.onion/scratch/` 是否被 gitignore,没有就提示用户 | §3.9 / §10.3 |
| **schema 自愈** | `state.db` schema 版本号 + 启动时校验,失败 3 阶段自愈(FTS rebuild → dedup → VACUUM) | §5.6 |
| **WAL fallback** | `apply_wal_with_fallback`(NFS/SMB 不可用时降级到 rollback journal) | §5.6(参照 Hermes) |
| **配置版本迁移** | Alembic 风格 migration 文件,逐版本升级 | §5.6(参照 Lobe Chat 129 个 migration) |
| **多 sub-agent** | sub-agent 创建子 session 文件,与主 session 关联,放在 `~/.onion/sessions/<main_id>/<sub_id>.json` 形成树 | §6.6 |
| **路径编码** | `name + timestamp` 命名(如 `session_<name>_<timestamp>.json`),人类可读 + 时间排序 | §10.2 |
| **onion.example.json** | 仓库内放 `onion.example.json`,首次启动 cp 为 `~/.onion/onion.json` | §10.4 |
| **自循环模式** | Agent Loop 是 session.json 自动累加器,天然支持自循环(不学 Claude Code Ralph hook) | §7.7 |
| **配置搜索链** | AGENTS.md / skills / rules 搜索链:包内置 → `~/.onion/` → `<repo>/` 向上到 `.git` 边界 → CLI/env | §10.5 |
| **缺失文件 marker** | `<repo>/.onion/` 里缺失文件时注入"missing file"标记(不自动创建,等用户填) | §3.8(参照 OpenClaw) |

### 12.3 P2(信创增强 / 长期演进)

| 维度 | 具体实现 | 依据标准 |
|-----|---------|---------|
| **三端隔离** | CLI + Desktop 各端,共享 `~/.onion/`(避免跨端数据不一致) | §2.6 |
| **加密 secrets** | AES-256-GCM 加密 `auth.json`(参照 Lobe Chat) | §5.5 |
| **OS 沙箱** | Windows Restricted Token + Linux Landlock/seccomp + macOS Seatbelt(参照 Codex) | §9.1 |
| **Docker 沙箱** | `Dockerfile` + `docker-compose.yml`,适合企业级部署(参照 OpenClaw / OpenHands) | §9.2 |
| **plugin 系统** | `~/.onion/plugins/` + manifest.json + 第三方 marketplace(参照 Cline 模式) | §10.7 |
| **多 board** | `~/.onion/profiles/<profile>/` 模式,允许多 board 隔离(简化版 Hermes Multi-board) | §7.4 |
| **per-workspace hash 隔离** | sha256 前 16 hex(64-bit)而非 8 hex(32-bit,避免生日悖论) | §3.6 |
| **病毒扫描** | 写文件时走 `scan_content_safe()`(企业版对接杀毒引擎) | 参照 AutoGPT |
| **凭证白名单硬编码** | `_ROOT_CREDENTIAL_DIRS = ("secrets", "auth.json", ".env")` LLM 永远不能 read | §5.4(参照 Hermes) |
| **路径模板化** | Onion 不要走 `name_id` 拼路径(SuperAGI 反例),**只用纯 UUID / sha256** | §10.1 反对 |
| **chat history 压缩回写** | Aider 反例:`.aider.chat.history.md` 压缩后不写回文件,只影响 LLM。Onion 要**主动写回 session.json**,保持单一真实来源 | §6.1 |
| **完整 schema 迁移** | 借鉴 Lobe Chat 129 个 migration,Alembic 风格 | §5.6 |

---

## 13. 文档说明

### 13.1 本标准的不变性与演进

- **不变性**:`session.json` 是洋葱核心,SQLite 等是基础设施层镜像(此为用户哲学,本标准不挑战)
- **演进原则**:
  - 新模式出现 ≥5/20 项目采用,纳入"必须做"
  - 现有"必须做"如果 <5/20 采用,降级为"强烈建议"
  - 反例(0-2/20 且明确有害)升级为"禁止"

### 13.2 与其他标准的关系

未来还要写的姊妹文档(参考用户 prompt.md):
- `harness/01_market_research/standard/agent_loop_standard.md` — Agent Loop 设计标准
- `harness/01_market_research/standard/plan_standard.md` — Plan 看板设计标准
- `harness/01_market_research/standard/tool_standard.md` — Tool shell / Tool channel 设计标准
- `harness/01_market_research/standard/difference.md` — 新颖设计对比
- `harness/01_market_research/standard/other_common.md` — 其他共同点

本文档(file_backend.md)与其他 5 份是**并列关系**,关注点不同(本标准只关注"工作区"维度)。

### 13.3 引用规范

- 所有证据引用格式:`<项目名>/file_backend.md:行号或段落`
- 20 份单项目报告:`harness/01_market_research/<项目目录>/file_backend.md`
- 3 份组内提炼稿:`harness/01_market_research/_intermediate_{general_agents,coding_agents,multi_agent_frameworks}.md`
- 顶部引用:`harness/01_market_research/top_20_react_agent.md`

### 13.4 调研局限

- 调研基于 2026-07-13 实时 GitHub 数据,star 数有变动,不影响工作区设计结论
- 部分项目(如 Open Interpreter)主仓库已被重写,采用 `git tag` + 历史 release 还原方式补充调研
- 2 个项目已废弃/移交(superpowers 寄生模式、Open Interpreter 转向 Rust)
- 调研时间:2026-07-17 ~ 2026-07-18

---

**报告完。** 整合自 20 份 `file_backend.md` + 3 份 `_intermediate_*.md`,所有路径断言均基于 `git clone --depth 1` 快照(2026-07-17),源码以只读方式访问,未做任何修改。
