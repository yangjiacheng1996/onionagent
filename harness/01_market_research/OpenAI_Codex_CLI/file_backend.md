# OpenAI Codex CLI — 工作区(File Backend)调研报告

> 调研对象:`openai/codex`(commit 取自 `C:\workspace\github\onionagent\harness\01_market_research\clone\codex`)
> 调研日期:2026-07-17
> 调研者:Onion Agent 自我反思小组
> 行号格式:源文件路径 `:行号`

---

## 0. 智能体一句话定位

OpenAI 出品的**终端原生 ReAct 编码 Agent**。Rust 重写(原 TypeScript 版本于 2025-04 开源),OS 级纵深防御沙箱(macOS Seatbelt + Linux Landlock/bubblewrap + Windows Restricted Token),三种权限模式(默认/auto-edit/full-auto),围绕 `~/.codex/` 全局目录 + 项目内 `.codex/` 双层目录,通过 JSONL rollout 文件追加累积会话历史,Multi-Agent V2 走 `sub-agent` 协议而非 git worktree 隔离。

---

## 1. 调研依据

| 维度 | 证据 |
|---|---|
| CLI 入口与子命令 | `codex-rs/cli/src/main.rs:106-180`(`Subcommand` 枚举,无 `init` 子命令) |
| 共享 CLI 选项 | `codex-rs/utils/cli/src/shared_options.rs:51-71`(`--cd`/`-C`、`--add-dir`、`--sandbox`、`-p profile` 等) |
| 全局配置目录解析 | `codex-rs/utils/home-dir/src/lib.rs:1-100`(`find_codex_home` 读取 `CODEX_HOME` 或 fallback 到 `~/.codex`) |
| Config Loader 入口 | `codex-rs/config/src/loader/mod.rs:88-99`(完整 layering 文档注释) |
| 多层 Config 优先级 | `codex-rs/config/src/config_layer_source.rs:32-51`(`precedence()` i16 排序) |
| Project 层级加载逻辑 | `codex-rs/config/src/loader/mod.rs:794-925`(`load_project_layers` 沿 cwd 向上扫 `.codex/config.toml`) |
| 平台系统 config 路径 | `codex-rs/config/src/loader/mod.rs:108-117`(`/etc/codex/config.toml` 或 `%ProgramData%\OpenAI\Codex\config.toml`) |
| Windows ProgramData 解析 | `codex-rs/config/src/loader/mod.rs:519-587`(`SHGetKnownFolderPath(FOLDERID_ProgramData)`) |
| AGENTS.md 默认文件名 | `codex-rs/core/src/agents_md.rs:38-40`(`AGENTS.md` + `AGENTS.override.md`) |
| AGENTS.md 向上扫描 | `codex-rs/core/src/agents_md.rs:153-220`(找 `project_root_markers` 默认为 `.git`) |
| Project root markers 默认 | `codex-rs/config/src/project_root_markers.rs:5-7`(`DEFAULT_PROJECT_ROOT_MARKERS = &[".git"]`) |
| 项目配置目录定位 | `codex-rs/config/src/state.rs:207-215`(`ConfigLayerEntry::config_folder()` 返回 `.codex/` 父目录) |
| Session 存储 layout | `codex-rs/rollout/src/list.rs:420`(`~/.codex/sessions/YYYY/MM/DD/rollout-…-<uuid>.jsonl`) |
| Session 文件名构造 | `codex-rs/rollout/src/recorder.rs:1517-1555`(`precompute_log_file_info`) |
| 状态库文件名 | `codex-rs/state/src/lib.rs:100-104`(`state_5.sqlite`/`logs_2.sqlite`/`memories_1.sqlite` 等) |
| History jsonl | `codex-rs/message-history/src/lib.rs:46`(`HISTORY_FILENAME = "history.jsonl"`) |
| Shell snapshot dir | `codex-rs/core/src/shell_snapshot.rs:50`(`SNAPSHOT_DIR = "shell_snapshots"`) |
| Windows sandbox dir | `codex-rs/windows-sandbox-rs/src/setup.rs:183-197`(`.sandbox`/`.sandbox-bin`/`.sandbox-secrets`) |
| Login 凭证 | `codex-rs/login/src/auth/storage.rs:150-152`(`auth.json`) |
| Secrets 加密 | `codex-rs/secrets/src/local.rs:37-39,138-152`(`secrets/{local,codex_auth,mcp_oauth}.age`) |
| Skills 根目录 | `codex-rs/core-skills/src/loader.rs:135-138`(`AGENTS_DIR_NAME=".agents"`,`SKILLS_DIR_NAME="skills"`) |
| Memories 根 | `codex-rs/memories/read/src/lib.rs:13`(`codex_home/memories/`) |
| Exec policy 规则 | `codex-rs/core/src/exec_policy.rs:50-53`(`RULES_DIR_NAME="rules"`、`DEFAULT_POLICY_FILE="default.rules"`) |
| Hooks 声明 | `codex-rs/hooks/src/engine/discovery.rs:116-118,304-307`(`<config_folder>/hooks.json`) |
| MCP 服务 | `codex-rs/config/src/mcp_types.rs`(完整 MCP config 类型) |
| 沙箱 backends | `codex-rs/sandboxing/src/lib.rs:1-14`(seatbelt/landlock/bwrap/windows) |
| Seatbelt profile | `codex-rs/sandboxing/src/seatbelt.rs:21-22`(`include_str!` 的 `*.sbpl`) |
| Landlock/bwrap | `codex-rs/linux-sandbox/README.md`(整篇说明 bwrap 优先 + 内置 fallback) |
| /init slash command | `codex-rs/tui/src/chatwidget/slash_dispatch.rs:252-256` |
| /init 提示词 | `codex-rs/tui/prompt_for_init_command.md` |
| 信任模型 | `codex-rs/core/src/config/mod.rs:2166-2180`(`set_project_trust_level`) |
| 多 Agent spawn | `codex-rs/core/src/agent/control/spawn.rs:200-241`(`spawn_agent` / `spawn_agent_with_metadata`) |
| 沙箱可写根 | `codex-rs/core/src/config/mod.rs:520-548`(`workspace_roots` 注入 `cwd` + `--add-dir`) |
| 文档基础 | `codex-rs/config.md`、`docs/install.md`、`docs/agents_md.md`、`docs/sandbox.md` |

---

## 2. 三个核心问题的回答

### Q1. 工作区路径(Codex CLI 的"cwd / project root / .codex/"语义)

**简短回答**:Codex CLI **没有单一根路径**,而是由 `CODEX_HOME`(全局)+ `--cd/-C`(项目 cwd)+ 向上扫到的"project root"(默认 `.git` 父目录)三个量叠加。`AGENTS.md` 在 project root 与 cwd 之间逐层加载。

#### Q1.1 全局配置目录(CODEX_HOME)

| 平台 | 默认路径 | 覆盖方式 | 验证 |
|---|---|---|---|
| Unix(未设环境变量) | `~/.codex` | `CODEX_HOME` 环境变量(必须存在,否则报错) | `codex-rs/utils/home-dir/src/lib.rs:38-74` |
| macOS(未设) | `$HOME/.codex`(`dirs::home_dir()`) | 同上 | `codex-rs/utils/home-dir/src/lib.rs:65-72` |
| Windows(未设) | `%USERPROFILE%\.codex` | `CODEX_HOME` | `codex-rs/utils/home-dir/src/lib.rs:1-100` |

要点(`codex-rs/utils/home-dir/src/lib.rs:48-64`):
- `CODEX_HOME` **必须指向已存在的目录**;不自动创建。
- 当 `CODEX_HOME` 已设置时,会 `canonicalize()`;非目录会报 `InvalidInput`。
- 多个 CODEX 进程(如本地+容器隔离)可指向不同 `CODEX_HOME` 互不干扰。

#### Q1.2 项目工作目录(cwd)

| 来源 | 优先级 | 备注 |
|---|---|---|
| `--cd <DIR>` / `-C <DIR>` | 1(最高) | `codex-rs/utils/cli/src/shared_options.rs:55-58` |
| 进程当前 cwd | 2(默认) | `current_dir()` |
| AppServer `cwd` 字段 | 3(从外部传入) | `codex-rs/app-server-protocol/src/protocol/v2/turn.rs` |
| exec-server `cwd` 环境变量 | 4(远端执行) | `codex-rs/exec-server-protocol/` |

`--cd` 同时影响 sandbox 可写根和 AGENTS.md 扫描起点(`codex-rs/core/src/config/mod.rs:523-540`)。

#### Q1.3 Project Root(.git 父目录)

- 默认 marker 列表 = `[" .git"]`(`codex-rs/config/src/project_root_markers.rs:5-7`)。
- 用户可在 `config.toml` 用 `project_root_markers = [".hg", "package.json"]` 自定义(`codex-rs/config/src/project_root_markers.rs:14-30`)。
- 向上扫描到第一个匹配 marker 的祖先目录(找不到则回退 cwd)(`codex-rs/core/src/agents_md.rs:175-188`)。
- 这与 Onion Agent 的"洋葱根"概念接近 — Codex 称之为 `project_root`。

#### Q1.4 AGENTS.md 加载规则(`codex-rs/core/src/agents_md.rs:30-60,153-220`)

```
1. 从 cwd 向上找到 project_root(默认 .git 父目录)
2. 在 project_root → cwd 之间每一层,优先尝试 AGENTS.override.md,再尝试 AGENTS.md
3. 用户可在 config.toml 用 project_doc_fallback_filenames 添加更多候选文件名
4. 所有命中的文件按"由根到叶"顺序拼接,加 "\n\n--- project-doc ---\n\n" 分隔
5. 总字节数受 project_doc_max_bytes(默认 32 KiB) 硬限制,超出会截断
6. 全部内容拼成 model-visible user instructions
```

**关键洞见**:与 Onion Agent 的 `session.json` 自动累加器不同,Codex 的 `AGENTS.md` 是**只读静态上下文**;真正可累加的载体是 `~/.codex/sessions/…jsonl` rollout 文件。

#### Q1.5 子进程 cwd

每次 `spawn_agent` 都会**继承父 `config.cwd`**(`codex-rs/core/src/agent/control/spawn.rs:215-280`),除非调用方通过 `PermissionProfileSnapshot` 或 role layer 显式覆盖。换句话说,**Codex 的 Multi-Agent V2 不为子 Agent 创建隔离目录**;它假设子 Agent 共享同一文件系统视角(只靠 permission profile 限制可写范围)。

#### Q1.6 工作区路径总表

| 路径 | 含义 | 由谁决定 | 是否可自定义 |
|---|---|---|---|
| `CODEX_HOME` (默认 `~/.codex`) | 全局配置/状态/历史/SQLite | `find_codex_home()` | 环境变量 + 唯一 |
| `cwd` (`-C/--cd` 或进程 cwd) | 当前任务根、AGENTS 扫描起点、沙箱 cwd | CLI / 环境 | 命令行 |
| `project_root` | AGENTS.md 向上扫描的边界 | `project_root_markers`(`[".git"]` 默认) | config.toml |
| 沙箱可写根 `workspace_roots` | sandbox 内可写的目录集合 | `cwd` + `--add-dir` + `SandboxPolicy::WorkspaceWrite` | 多源 |
| 项目级 `.codex/` | `<dir>/.codex/config.toml` + 子目录 | 由 loader 沿 cwd 向上收集 | 无,固定名 |

---

### Q2. 工作区目录结构

Codex 维护**两个并列的目录**:全局 `CODEX_HOME` 和项目级 `.codex/`。所有路径**绝对**,不存在"模糊相对"。

#### Q2.1 全局目录 `CODEX_HOME`(`~/.codex/` 默认为例)

| 子项 | 类型 | 路径 | 用途 | 关键源 |
|---|---|---|---|---|
| **配置** | TOML | `config.toml` | 主用户配置(可被 profile 覆盖) | `codex-rs/config/src/lib.rs:24`(`CONFIG_TOML_FILE`) |
| **Profile** | TOML | `<name>.config.toml` | 通过 `--profile/-p <name>` 选用的配置层 | `codex-rs/config/src/loader/mod.rs:179-189` |
| **认证** | JSON | `auth.json` | ChatGPT/API key 凭证(明文 0600) | `codex-rs/login/src/auth/storage.rs:150-152` |
| **MCP OAuth** | JSON | `.credentials.json`(可选 keyring) | MCP OAuth token | `codex-rs/config/src/config_toml.rs:825-835` |
| **加密 secrets** | age | `secrets/local.age` `secrets/codex_auth.age` `secrets/mcp_oauth.age` | age 加密托管 secret | `codex-rs/secrets/src/local.rs:37-39,138-152` |
| **历史** | JSONL | `history.jsonl` | 全局消息历史(原子追加,带 advisory lock) | `codex-rs/message-history/src/lib.rs:46,115-145` |
| **日志** | 文件 | `log/codex-tui.log` 等 | TUI 诊断日志(默认 bounded,需 `log_dir=` 打开 plaintext) | `codex-rs/core/src/config/mod.rs:3772-3774`、`docs/install.md:55-60` |
| **会话** | JSONL(+ 可选 `.zst`) | `sessions/YYYY/MM/DD/rollout-YYYY-MM-DDThh-mm-ss-<uuid>.jsonl` | 每次 thread 完整消息流;可压缩 | `codex-rs/rollout/src/lib.rs:24-25`、`codex-rs/rollout/src/recorder.rs:1517-1555` |
| **归档会话** | JSONL | `archived_sessions/…` | 被 archive 的 thread | `codex-rs/rollout/src/lib.rs:25`、`codex-rs/rollout/src/recorder.rs:1335` |
| **Shell snapshot** | sh/ps1 | `shell_snapshots/<thread_id>.<nonce>.{sh,ps1}` | 执行 shell 前的 alias/function/export 快照,3 天清理 | `codex-rs/core/src/shell_snapshot.rs:50,121-150` |
| **SQLite 状态库** | sqlite | `state_5.sqlite`、`logs_2.sqlite`、`goals_1.sqlite`、`memories_1.sqlite`、`thread_history_1.sqlite` | thread 索引、telemetry、目标、记忆、压缩历史 | `codex-rs/state/src/lib.rs:100-104`、`codex-rs/state/src/runtime.rs:117-160` |
| **Skills** | 目录 | `skills/<name>/SKILL.md` | 用户安装的 skill(已被 `$HOME/.agents/skills` 取代) | `codex-rs/core-skills/src/loader.rs:135-138,329-353` |
| **系统 skills 缓存** | 目录 | `skills/.system/<name>/SKILL.md` | 内置 skill 的运行时解压 | `codex-rs/skills/src/lib.rs:13-22` |
| **Rules (execpolicy)** | starlark | `rules/default.rules` + 其他 `*.rules` | 命令执行前的策略匹配(approval/deny) | `codex-rs/core/src/exec_policy.rs:50-53,609-642` |
| **Hooks** | JSON | `hooks.json`(顶层,非子目录) | lifecycle hook 声明(`PreToolUse`/`PostToolUse`/`SessionStart` 等) | `codex-rs/hooks/src/engine/discovery.rs:304-307`、`codex-rs/external-agent-migration/src/service.rs:591` |
| **Memories(workspace)** | git | `memories/`(内置 `.git`) | 跨 thread 的"长期记忆"工作目录,Phase 1/2 pipeline | `codex-rs/memories/README.md`、`codex-rs/memories/read/src/lib.rs:13` |
| **Plugins / Marketplaces** | git | `marketplaces/<name>/…`、`.agents/plugins/` | 外部 plugin/marketplace 拉取的目录 | `codex-rs/config/src/marketplace_edit.rs`、tests 中 `codex_home/marketplace` |
| **Connectors cache** | JSON | `cache/codex_app_directory/<hash>.json` | 远程 app 目录缓存 | `codex-rs/connectors/src/directory_cache.rs:13-35` |
| **AppServer control socket** | unix socket | (OS 决定;Windows 用 named pipe) | app-server 多进程 IPC | `codex-rs/app-server/` |
| **Windows 沙箱** | dir | `.sandbox/` `.sandbox-bin/` `.sandbox-secrets/` `.sandbox/setup_marker.json` `.sandbox/logs/` `.sandbox/sandbox_users.json` | Windows Restricted Token 沙箱持久化目录、log 目录、用户映射 | `codex-rs/windows-sandbox-rs/src/setup.rs:183-197,311,693` |
| **Trust 标记** | TOML 字段 | 内嵌在 `config.toml` 的 `[projects]` map | 项目级 trust level(`trusted`/`untrusted`),影响 hooks/exec-policy/`.codex/config.toml` 是否加载 | `codex-rs/core/src/config/mod.rs:2166-2180`、`codex-rs/config/src/loader/mod.rs:819-925` |
| **云 bundle 缓存** | JSON/TOML | (由 `CloudConfigBundleLoader` 决定) | 企业云端配置 + requirements | `codex-rs/config/src/cloud_config_bundle.rs`、`docs/config.md` |

#### Q2.2 项目级 `.codex/` 目录(每个项目一个,可嵌套)

| 路径 | 含义 | 来源 |
|---|---|---|
| `.codex/config.toml` | 项目本地配置;被信任后才生效 | `codex-rs/config/src/loader/mod.rs:794-925` |
| `.codex/skills/<name>/SKILL.md` | 项目级 skill(优先级高于 user/system) | `codex-rs/core-skills/src/loader.rs:315-330` |
| `.codex/hooks.json` | 项目级 hook 声明 | `codex-rs/hooks/src/engine/discovery.rs:116-118,304-307` |
| `.codex/rules/default.rules` 等 | 项目级 execpolicy 规则 | `codex-rs/core/src/exec_policy.rs:609-642` |
| `.codex/AGENTS.override.md` | 本地 override(优先于 AGENTS.md) | `codex-rs/core/src/agents_md.rs:40-42` |
| `.codex/AGENTS.md` | 项目级 agent 指令(被信任时) | `codex-rs/core/src/agents_md.rs:38` |
| `.codex/marketplaces/<name>/…` | 项目级 plugin marketplace 引用 | `codex-rs/config/src/marketplace_edit.rs` |

`.codex/` 子目录会**沿 cwd 向上递归收集**(最多到 project_root),越靠 cwd 优先级越高(`codex-rs/config/src/loader/mod.rs:817-830`)。

#### Q2.3 多层 Config Layer(同目录多份配置)

Codex 的 `ConfigLayerStack` 维护 9 种 layer,按 `precedence` 排序(`codex-rs/config/src/config_layer_source.rs:32-51`):

```
precedence  0: Mdm (managed preferences, macOS only)
precedence 10: System (/etc/codex/config.toml or %ProgramData%\OpenAI\Codex\config.toml)
precedence 15: EnterpriseManaged (云 bundle 切片)
precedence 20: User ($CODEX_HOME/config.toml)
precedence 21: User with active profile ($CODEX_HOME/<name>.config.toml)
precedence 25: Project (从 cwd 向上找到的所有 .codex/config.toml)
precedence 30: SessionFlags (CLI -c key=value)
precedence 40: LegacyManagedConfigTomlFromFile
precedence 50: LegacyManagedConfigTomlFromMdm
```

**注意**:`Project` 类型的 layer,**位置越靠 cwd 优先级越高**(子目录覆盖父目录);`System`/`User`/`Mdm` 则按固定顺序覆盖。详见 `codex-rs/config/src/loader/mod.rs:817-870`。

#### Q2.4 requirements.toml(管理员强制约束)

| 平台 | 路径 | 含义 |
|---|---|---|
| Unix | `/etc/codex/requirements.toml` | 限制可用 sandbox 模式、approval 策略、network 域、plugin source |
| Windows | `%ProgramData%\OpenAI\Codex\requirements.toml` | 同上 |
| MDM(macOS) | managed preferences domain | 同样语义 |

(`codex-rs/config/src/loader/mod.rs:97-103,510-517`)

#### Q2.5 OS 沙箱 Profile 路径(嵌入可执行文件)

| OS | profile 来源 | 路径 |
|---|---|---|
| macOS Seatbelt | 内嵌 .sbpl | `codex-rs/sandboxing/src/seatbelt.rs:21-22`(通过 `include_str!` 编译进二进制) |
| macOS Seatbelt base | 基础策略 | `codex-rs/sandboxing/src/seatbelt_base_policy.sbpl` |
| macOS Seatbelt network | 网络策略 | `codex-rs/sandboxing/src/seatbelt_network_policy.sbpl` |
| Linux Landlock | 内嵌 Rust | `codex-rs/sandboxing/src/landlock.rs` + `codex-rs/linux-sandbox/`(独立 `codex-linux-sandbox` 二进制) |
| Linux bubblewrap | 系统 `bwrap` 或内置 `codex-resources/bwrap` | `codex-rs/linux-sandbox/README.md:1-25` |
| Windows | Restricted Token + Job Object | `codex-rs/windows-sandbox-rs/`(独立 DLL + setup service) |

`/usr/bin/sandbox-exec` 是 macOS 上唯一信任的 seatbelt 可执行文件(`codex-rs/sandboxing/src/seatbelt.rs:30`)。

#### Q2.6 MCP 配置

MCP server 配置分两类:
- **全局**:`$CODEX_HOME/config.toml` 的 `[mcp_servers.<name>]`(`codex-rs/config/src/mcp_types.rs`)。
- **项目级**:由 `[projects.<path>]` trust 决定是否加载(待查 — 主要在云 bundle / requirements 中)。
- **运行时编辑**:`codex mcp add/list/get/remove` 子命令(`codex-rs/cli/src/main.rs:132` 触发的 `McpCli`)。

#### Q2.7 Rules 目录(execpolicy)

| 路径 | 含义 | 来源 |
|---|---|---|
| `$CODEX_HOME/rules/*.rules` | 用户级 execpolicy(starlark 语法) | `codex-rs/core/src/exec_policy.rs:609-642` |
| `<project>/.codex/rules/*.rules` | 项目级 execpolicy | 同上 |
| `requirements.toml` 里的 `[exec_policy]` | 管理员强制规则 | `codex-rs/config/src/requirements_exec_policy.rs` |

#### Q2.8 Hooks 目录

- **项目 hooks**:`<project>/.codex/hooks.json`(单文件,非目录)
- **plugin hooks**:`<plugin_root>/hooks/hooks.json`
- **legacy**:`$CODEX_HOME/hooks.json`(单文件,迁移自 Claude Code)

(`codex-rs/hooks/src/engine/discovery.rs:116-118,304-307`、`codex-rs/external-agent-migration/src/service.rs:591`)

---

### Q3. 工作区创建(init 流程)

#### Q3.1 没有 `codex init` 子命令

`codex-rs/cli/src/main.rs:106-180` 的 `Subcommand` 枚举**没有 `Init` 变体**。Codex CLI 的"首次运行"是**隐式引导**而非显式 init:

1. 首次 `codex` 启动 → `find_codex_home()` 检查 `CODEX_HOME` 或 fallback `~/.codex`。
2. `~/.codex` 不必预先存在(`find_codex_home` 在无 `CODEX_HOME` 时不验证;`codex-rs/utils/home-dir/src/lib.rs:38-46`)。
3. 任何子目录(`sessions/`、`skills/`、`shell_snapshots/`、`rules/`、`memories/` 等)都是**按需自动创建**,写文件前 `fs::create_dir_all(parent)`。
4. SQLite 状态库在 `StateRuntime::init()` 时创建(`codex-rs/agent-graph-store/src/local.rs:145`、`codex-rs/state/src/runtime.rs`)。
5. Windows 沙箱在首次需要时通过 `setup_main` 写入 `.sandbox/`(`codex-rs/windows-sandbox-rs/src/bin/setup_main/win.rs:413`)。

#### Q3.2 `codex doctor` 是诊断而非 init

- `codex-rs/cli/src/main.rs:155-156` 注册 `Doctor(DoctorCommand)`,实现 `codex-rs/cli/src/doctor.rs`。
- 仅检查 CODEX_HOME 路径、auth.json、log_dir 等健康度,不写入。

#### Q3.3 TUI 内 `/init` 斜杠命令

虽然 CLI 没有 init,但 **TUI 内有 `/init` 斜杠命令**:

- 入口:`codex-rs/tui/src/chatwidget/slash_dispatch.rs:252-256`:
  ```rust
  SlashCommand::Init => {
      const INIT_PROMPT: &str = include_str!("../../prompt_for_init_command.md");
      self.submit_user_message(INIT_PROMPT.to_string().into());
  }
  ```
- 提示词全文:`codex-rs/tui/prompt_for_init_command.md`
  - 让模型生成名为 `AGENTS.md` 的文件,标题"Repository Guidelines"。
  - 若已存在则不覆盖。
  - 推荐 5 段:Project Structure、Build/Test Commands、Coding Style、Testing Guidelines、Commit & PR。
- `/init` 实质是 **prompt injection → 模型用 `apply_patch` 写文件**,不是 CLI 显式脚手架。
- TUI `command_popup` 默认条目也展示该命令(`codex-rs/tui/src/bottom_pane/snapshots/...command_popup_default_items.snap:24`)。

#### Q3.4 AGENTS.md 的来源

| 来源 | 谁创建 | 何时 |
|---|---|---|
| 项目仓库自带 | 项目作者 | 随项目 commit |
| Codex `/init` 斜杠命令 | 模型基于 prompt 模板自动写 | 用户在 TUI 内首次启动时 |
| `external-agent-migration` 工具 | Codex 内置迁移工具 | 从 Claude Code / Cursor 等导入 |
| 用户手动 `Write`/`apply_patch` | 用户或子 Agent | 任意时刻 |

#### Q3.5 多 Agent 隔离 — 不是 git worktree

**重要更正**:任务描述里的"git worktree 多 Agent 隔离"在当前 Codex 主线**并不存在**。

- **没有自动 git worktree 克隆**。搜索 `git worktree` 仅在 `codex-rs/git-utils/src/errors.rs:8` 的注释和 `.git/hooks/sendemail-validate.sample`(git 自带样例)中出现。
- **Multi-Agent V2 的隔离**完全靠 **permission profile + approval policy + role config layer**:
  - 父 Agent 调用 `spawn_agent` → `codex-rs/core/src/agent/control/spawn.rs:200-365`。
  - 子 Agent 继承 `config.cwd`、`approval_policy`、`approvals_reviewer`、`permission_profile`(`codex-rs/core/src/agent/control/spawn.rs:280-305`)。
  - 子 Agent 的文件系统可写范围 = 父的 `workspace_roots`(`codex-rs/core/src/agent/control/spawn.rs:293-298`)。
  - 子 Agent 的 execpolicy = 父的 execpolicy + 自身的 role layer(`codex-rs/core/src/agent/role.rs:30-90`)。
- **父/子共享同一 SQLite**(`state_5.sqlite`、rollout 都在 `~/.codex/` 下),通过 `parent_thread_id` 字段链接(`codex-rs/core/src/agent/control/control.rs:69`)。
- **会话隔离**:`codex resume <thread_id>` / `codex fork <thread_id>` / `codex archive` / `codex delete` 都是**按 thread_id 维度**操作(`codex-rs/cli/src/main.rs:160-180`)。

#### Q3.6 worktree 相关的极少量代码

唯一涉及"git worktree"的工作流是 **`config_folder()` 函数**对 linked worktree 做了特殊处理(`codex-rs/config/src/loader/mod.rs:895-905,1287-1356`):

```rust
// 普通 checkout:worktree 与主仓同根,.codex 仍在 worktree 里
// linked worktree:worktree 在别处,但希望 hook 仍从主仓 .codex 加载
fn root_checkout_hooks_folder_for_dir(...) {
    let checkout_root = self.checkout_root.as_ref()?;
    let repo_root = self.repo_root.as_ref()?;
    if checkout_root == repo_root { return None; }  // 普通
    // linked: 用主仓的 .codex 目录作为 hook 源
    Some(repo_root.join(relative_dir).join(".codex"))
}
```

这只是**配置加载时的路径解析小技巧**,不是为多 Agent 隔离而生。

#### Q3.7 项目 trust level — 隐式安全 init

Codex 在执行每个 cwd 时,会:
1. 沿 cwd 向上找 `.codex/config.toml`。
2. 在 `config_layer_stack` 中将其标为 `disabled_reason`(未受信任)(`codex-rs/config/src/loader/mod.rs:819-925`)。
3. TUI 弹窗提示用户:是否要把这个 project 加到 `$CODEX_HOME/config.toml` 的 `[projects.<path>]` 并设 `trust_level = "trusted"`(`codex-rs/app-server/tests/suite/v2/thread_start.rs:1505-1600`)。
4. 用户确认后,`set_project_trust_level(codex_home, project_path, TrustLevel::Trusted)` 写入 config.toml(`codex-rs/core/src/config/mod.rs:2166-2180`)。

这是 Codex 的"项目首次引导"机制 — **不是 init 子命令,而是 lazy trust 流程**。

#### Q3.8 init 总结表

| 阶段 | 谁触发 | 创建什么 | 在哪 |
|---|---|---|---|
| 首次 `codex` 启动 | 用户命令 | 仅当 `CODEX_HOME` 存在时不创建;运行时按需 `create_dir_all` | `~/.codex/` |
| 首次需要 sessions | `RolloutRecorder` | `sessions/YYYY/MM/DD/` | `~/.codex/sessions/` |
| 首次需要 skills | `SkillsService` | `skills/.system/<name>/`(解压内置) | `~/.codex/skills/.system/` |
| 首次需要 shell snapshot | `ShellSnapshot::try_create` | `shell_snapshots/<thread_id>.<nonce>.sh` | `~/.codex/shell_snapshots/` |
| 首次需要 state DB | `StateRuntime::init` | `state_5.sqlite` 等 | `~/.codex/` |
| 首次需要 memories | `Memories` 流程 | `memories/`(含 `.git`) | `~/.codex/memories/` |
| 首次需要 Windows 沙箱 | `setup_main` | `.sandbox/` `.sandbox-bin/` `.sandbox-secrets/` | `~/.codex/.sandbox/` |
| 首次需要 rules | `load_exec_policy` | 不会自动创建,只读取 | 用户/项目 `rules/` |
| 首次进入未信任项目 | 运行时 trust prompt | (无文件创建,只是把 `config.toml` 的 `[projects]` 加一行) | `~/.codex/config.toml` |
| 用户 `/init` | TUI slash | 调模型写 `AGENTS.md` | 当前 cwd |

---

## 3. 关键代码片段(精华)

### 3.1 CODEX_HOME 解析(`codex-rs/utils/home-dir/src/lib.rs:14-74`)

```rust
pub fn find_codex_home() -> std::io::Result<AbsolutePathBuf> {
    let codex_home_env = std::env::var("CODEX_HOME")
        .ok()
        .filter(|val| !val.is_empty());
    find_codex_home_from_env(codex_home_env.as_deref())
}

fn find_codex_home_from_env(codex_home_env: Option<&str>) -> std::io::Result<AbsolutePathBuf> {
    match codex_home_env {
        Some(val) => {
            let path = PathBuf::from(val);
            let metadata = std::fs::metadata(&path).map_err(|err| match err.kind() {
                std::io::ErrorKind::NotFound => std::io::Error::new(
                    std::io::ErrorKind::NotFound,
                    format!("CODEX_HOME points to {val:?}, but that path does not exist"),
                ),
                _ => /* 包装其他错误 */,
            })?;
            if !metadata.is_dir() { /* Err InvalidInput */ }
            let canonical = path.canonicalize() /* ... */?;
            AbsolutePathBuf::from_absolute_path(canonical)
        }
        None => {
            let mut p = home_dir().ok_or_else(|| /* 找不到 home */)?;
            p.push(".codex");
            AbsolutePathBuf::from_absolute_path(p)
        }
    }
}
```

要点:
- 唯一入口是 `CODEX_HOME`;没有 macOS `~/Library/Application Support/codex/` 这种平台特定 fallback。
- 行为更像"工作区级开关"而不是"用户级默认"。

### 3.2 Config Layer 优先级(`codex-rs/config/src/config_layer_source.rs:32-51`)

```rust
pub fn precedence(&self) -> i16 {
    match self {
        ConfigLayerSource::Mdm { .. } => 0,
        ConfigLayerSource::System { .. } => 10,
        ConfigLayerSource::EnterpriseManaged { .. } => 15,
        ConfigLayerSource::User { profile, .. } => {
            if profile.is_some() { 21 } else { 20 }
        }
        ConfigLayerSource::Project { .. } => 25,    // 关键
        ConfigLayerSource::SessionFlags => 30,       // CLI -c
        ConfigLayerSource::LegacyManagedConfigTomlFromFile { .. } => 40,
        ConfigLayerSource::LegacyManagedConfigTomlFromMdm => 50,
    }
}
```

注意 **Project 优先级 (25) 低于 CLI (30),低于 legacy managed (40,50)**;这是"项目本地不能篡夺企业策略"的安全设计。

### 3.3 Project layers 沿 cwd 向上收集(`codex-rs/config/src/loader/mod.rs:817-870`)

```rust
let mut dirs = cwd
    .ancestors()
    .scan(false, |done, a| {
        if *done { None } else {
            if &a == project_root { *done = true; }
            Some(a)
        }
    })
    .collect::<Vec<_>>();
dirs.reverse();  // 由根到叶

for dir in dirs {
    let dot_codex_abs = dir.join(".codex");
    if !fs.get_metadata(&dot_codex_abs).await?.is_directory { continue; }
    // ...加载 config.toml,叠加成新 layer
}
```

这是"项目级洋葱"实现 — 与 Onion Agent 的设计哲学非常接近。

### 3.4 Session 文件名(`codex-rs/rollout/src/recorder.rs:1517-1555`)

```rust
// Resolve ~/.codex/sessions/YYYY/MM/DD path.
let timestamp = OffsetDateTime::now_local()
    .map_err(|e| IoError::other(format!("failed to get local time: {e}")))?;
let mut dir = config.codex_home().to_path_buf();
dir.push(SESSIONS_SUBDIR);  // "sessions"
dir.push(timestamp.year().to_string());
dir.push(format!("{:02}", u8::from(timestamp.month())));
dir.push(format!("{:02}", timestamp.day()));
// ...
let filename = format!("rollout-{date_str}-{conversation_id}.jsonl");
let path = dir.join(filename);
```

注意:
- 时间戳是**本地时间**(`now_local()`),不是 UTC。
- 文件名用 `-` 替 `:` 避免 Windows reserved chars。
- `conversation_id` 是 UUID,等价于 `thread_id`。

### 3.5 /init slash command 实现(`codex-rs/tui/src/chatwidget/slash_dispatch.rs:252-256`)

```rust
SlashCommand::Init => {
    const INIT_PROMPT: &str = include_str!("../../prompt_for_init_command.md");
    self.submit_user_message(INIT_PROMPT.to_string().into());
}
```

**Trick**:用 `include_str!` 把 prompt 模板编译进二进制,运行时把模板内容当成用户消息发给模型 — 让模型自己写 AGENTS.md。

### 3.6 沙箱可写根(`codex-rs/core/src/config/mod.rs:520-548`)

```rust
self.workspace_roots = match &sandbox_policy {
    SandboxPolicy::WorkspaceWrite { writable_roots, .. } => {
        let mut workspace_roots = vec![AbsolutePathBuf::from_absolute_path(cwd)?];
        for root in writable_roots {
            if !workspace_roots.iter().any(|existing| existing == root) {
                workspace_roots.push(root.clone());
            }
        }
        workspace_roots
    }
    SandboxPolicy::DangerFullAccess
    | SandboxPolicy::ExternalSandbox { .. }
    | SandboxPolicy::ReadOnly { .. } => vec![AbsolutePathBuf::from_absolute_path(cwd)?],
};
```

`--add-dir <DIR>` 的值合入 `writable_roots` 集合,与 cwd 一起作为 sandbox 内可写范围。`ReadOnly` 模式下 cwd 也只是"可读根",不是可写根。

### 3.7 Shell snapshot 创建(`codex-rs/core/src/shell_snapshot.rs:121-150`)

```rust
let extension = match shell.shell_type {
    ShellType::PowerShell => "ps1",
    _ => "sh",
};
let nonce = SystemTime::now()
    .duration_since(SystemTime::UNIX_EPOCH)
    .map(|duration| duration.as_nanos())
    .unwrap_or(0);
let path = codex_home
    .join(SNAPSHOT_DIR)  // "shell_snapshots"
    .join(format!("{session_id}.{nonce}.{extension}"));
let temp_path = codex_home
    .join(SNAPSHOT_DIR)
    .join(format!("{session_id}.tmp-{nonce}"));
```

要点:
- 每个 thread 一次,临时文件 → rename 原子化。
- 3 天自动清理(`SNAPSHOT_RETENTION = Duration::from_secs(60 * 60 * 24 * 3)`)。
- Drop 时删除(`impl Drop` → `fs::remove_file`)。

### 3.8 沙箱默认 Seatbelt profile(`codex-rs/sandboxing/src/seatbelt.rs:21-30`)

```rust
const MACOS_SEATBELT_BASE_POLICY: &str = include_str!("seatbelt_base_policy.sbpl");
const MACOS_SEATBELT_NETWORK_POLICY: &str = include_str!("seatbelt_network_policy.sbpl");

/// When working with `sandbox-exec`, only consider `sandbox-exec` in `/usr/bin`
/// PATH. If /usr/bin/sandbox-exec has been tampered with, then the attacker
/// has already won.
pub const MACOS_PATH_TO_SEATBELT_EXECUTABLE: &str = "/usr/bin/sandbox-exec";
```

Seatbelt profile 编译进二进制,**用户不能改**;运行时通过 `build_seatbelt_access_policy` 把 cwd / --add-dir 注入策略。

---

## 4. 与 Onion Agent 设计的关联

> Onion Agent 的核心设计哲学:Agent Loop 是围绕 `session.json` 上下文历史文件的**自动累加器**。对比 Codex CLI 提取可借鉴/可避免的设计点。

### 4.1 可借鉴的设计

| Onion Agent 痛点 | Codex 的解法 | 借鉴价值 |
|---|---|---|
| 多源配置谁覆盖谁 | 9 层 ConfigLayer 显式 precedence(i16 排序 + 来源标签) | ⭐⭐⭐ 直接借用 precedence 模型;Onion 应至少有 USER/PROJECT/SESSION/CLI 四层 |
| 配置在哪存太散 | 单一 `CODEX_HOME` 全局 + 项目 `.codex/` 局部,无 macOS 平台差异 | ⭐⭐⭐ Onion 可统一"global config dir = ~/.onion" + per-project `<cwd>/.onion/`,与 Codex 形态一致 |
| AGENTS.md 散落多份 | 沿 project_root → cwd 全部收集 + `project_doc_max_bytes` 硬上限 + 字节截断告警 | ⭐⭐⭐ Onion 必学:模型上下文是有限资源,**必须**有 per-file 字节上限和总字节上限 |
| 用户消息全量写盘会导致爆盘 | `history.jsonl` 用 `O_APPEND` + 单 write 原子 + advisory lock + soft/hard cap 修剪 | ⭐⭐⭐ 借鉴 JSONL + 软/硬 cap 修剪;Onion 的 session.json 累计应分块 + 软截断 |
| shell exec 不可重现 | `shell_snapshots/<thread_id>.<nonce>.sh` 记录 alias/function/export,3 天清理 | ⭐⭐ Onion 的"小脑执行器"应当记录 shell 状态快照,确保 exec 可回放 |
| Rules 散落 | 每层 config 自带 `rules/<name>.rules`,按层 precedence 叠加 | ⭐⭐ 借鉴"execpolicy 跟着 config 层走"的设计 |
| 命令行覆盖散乱 | `-c key=value` dot-path 写 SessionFlags layer(precendence 30) | ⭐⭐ Onion CLI 也应支持 `-c key=value` |
| Hooks 在哪 | 每个 config 目录的 `hooks.json` 单文件,自动按层叠加 | ⭐⭐ Onion 的事件 hook 应当也按 config 目录组织 |
| 信任模型 | Project 信任与否决定是否加载 `.codex/config.toml`、`hooks.json`、`rules/*.rules` | ⭐⭐⭐ Onion 应当引入同款"项目首次访问"trust prompt,避免静默加载恶意配置 |

### 4.2 应避免的设计

| Codex 缺点 | Onion 应当怎么做 |
|---|---|
| **没有 `codex init`**,用户首次用要记 `mkdir ~/.codex` 或 `login`(隐式) | 提供显式 `onion init` 子命令,创建 `~/.onion/` 骨架目录 + 写入 README |
| 9 层 config 优先级对用户认知负担极重;`precedence` i16 数字不是给人看的 | Onion 用名字化优先级(USER/PROJECT/SESSION/CLI),文档化 |
| `AGENTS.override.md` 与 `AGENTS.md` 双文件名容易混淆 | Onion 用单一文件名 + 显式 include 指令 |
| Sandbox policy 与 config 高度耦合,改权限必须重启 | Onion 把"权限"与"上下文"解耦,支持热改 |
| 历史/会话/rollout 重复数据(同一条消息可能同时在 rollout + history + sqlite) | Onion 的 session.json 是唯一 source of truth,其他视图都派生 |
| Project trust 写入 `config.toml` 的 `[projects]` map,大型项目会很乱 | Onion 用独立 `trust.toml` 或 sqlite,避免污染主 config |
| 7 种 sqlite 库(state/logs/goals/memories/thread_history/...)分裂严重 | Onion 单 sqlite + namespaced tables |
| Cloud bundle / MDM / legacy managed / requirements 多源管理太复杂 | Onion 暂不考虑 enterprise 管理,只 USER + PROJECT + SESSION + CLI 四层 |
| 沙箱 profile 编译进二进制,用户不能调 | Onion 让用户能写 `.onion/sandbox/permission.rules` |
| 12 种斜杠命令(`/init`/`/compact`/`/review`/...)+ 12 种 tool(`spawn_agent`/`send_input`/`close_agent`/`wait_agent`/...) | Onion 用更小的 command 集,核心命令 ≤ 5 个 |

### 4.3 关于"git worktree 隔离多 Agent"的判定

任务描述提到 Codex 用 git worktree 隔离多 Agent。**经过代码级搜索,我没有发现这条路径**。当前 Codex 的多 Agent 模型是:

1. **共享 cwd**:子 Agent 继承父 cwd,不创建新 worktree。
2. **共享文件视图**:所有 Agent 操作同一文件系统,通过 permission profile 控制可写范围。
3. **共享状态库**:都在同一个 `state_5.sqlite` 里,靠 `parent_thread_id` 串成 tree。
4. **历史隔离**:rollout 独立,但写到同一 `~/.codex/sessions/` 下。

如果 Onion Agent 想做"git worktree 隔离的多 Agent",**需要自己实现**;不能从 Codex 学到。建议把这条作为 Onion 差异化特性。

### 4.4 Onion Agent 建议的最小可借鉴改造清单

1. **配置目录**:统一 `~/.onion/` + `<cwd>/.onion/`,与 Codex 形态对齐。
2. **ConfigLayerStack**:4 层显式 precedence(USER < PROJECT < SESSION < CLI),不要 MDM/cloud。
3. **session.json 自动累加器**借鉴 Codex `rollout-…jsonl` 的"分片"思想:超过 N 字节就 rotate,旧的归档到 `sessions/YYYY/MM/DD/`。
4. **AGENTS.md 加载**:沿 cwd 向上收集,设 `project_doc_max_bytes` 默认 32 KiB。
5. **历史文件 `history.jsonl`**:O_APPEND + advisory lock + soft/hard cap。
6. **execpolicy rules**:在 `<cwd>/.onion/rules/*.rules` 用 starlark 或更简单的 JSON 规则,按层叠加。
7. **项目 trust prompt**:首次进入 `<cwd>/.onion/` 弹窗确认,信任后写入 `~/.onion/trust.toml`。
8. **斜杠命令**:`/init`(生成 AGENTS.md)、`/compact`(累积 session.json 截断)、`/review`、不学 12 个,只学 3 个。
9. **不要 git worktree 多 Agent**:Onion 应该坚持"洋葱根"模型,所有 Agent 共享同一 session.json,差异化在 role/prompt 而不是工作目录。

---

## 5. 不确定 / 未找到

| 项 | 状态 | 备注 |
|---|---|---|
| `~/.codex` 完整子目录清单是否还有遗漏 | 中 | 已覆盖 config/auth/sessions/shell_snapshots/skills/rules/hooks/memories/state/sqlite/secrets/.sandbox/marketplaces/cache;可能还有 plugins/connectors 子目录细节未深挖 |
| cloud bundle 的实际缓存位置 | 低 | `CloudConfigBundleLoader` 实现分散,未追到具体路径常量 |
| TUI 历史文件 vs rollout 关系 | 中 | `history.jsonl` 是用户消息层(全局),rollout 是 thread 完整消息流(per-thread);两者用途不同但字段重叠 |
| Windows sandbox 详细目录结构 | 中 | `.sandbox/setup_marker.json` `.sandbox/sandbox_users.json` `.sandbox/logs/` 已确认;helper binary 在 `.sandbox-bin/` 确认;secrets 在 `.sandbox-secrets/` 确认 |
| `external-agent-migration` 的目标路径 | 中 | `codex-rs/external-agent-migration/src/service.rs:591` 显示 `MigrationScope::Home => self.codex_home.join("hooks.json")`,但其他 import target 路径未完整追溯 |
| Skills 在 `$HOME/.agents/skills` 的具体优先级 | 中 | 看到 `home_dir.join(".agents").join("skills")`(`codex-rs/core-skills/src/loader.rs:343-347`),但与 `$CODEX_HOME/skills/` 的合并顺序需进一步验证 |
| 平台特定 config 路径是否存在 `Library/Application Support/codex/` | 已否 | Codex 完全不依赖 macOS 标准应用数据目录,只用 `~/.codex`,这是与多数 macOS app 的差异 |
| Multi-Agent V2 是否引入 worktree 隔离 | 已否 | 当前没有;`spawn_agent` 全部继承父 cwd + permission profile |

---

> 报告完。
> 核心结论:Codex CLI 的"工作区"概念是**全局 CODEX_HOME + 项目 .codex + cwd 三元组**,配置文件按 9 层 precedence 合并,session 用 JSONL 分片按日归档,沙箱 profile 编译进二进制,**没有 git worktree 隔离,没有显式 init 命令**。Onion Agent 可借鉴其配置 precedence 模型和 JSONL 历史策略,但应保留自己"单 session.json 自动累加器"的差异化。
