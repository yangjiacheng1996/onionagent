# Hermes Agent — 工作区(File Backend)调研报告

> 调研对象:NousResearch/hermes-agent
> 调研时间:2026-07-17
> 调研目的:为 Onion Agent(洋葱架构,围绕 `session.json` 自动累加)提取工作区设计标准

---

## 0. 智能体一句话定位

**"the agent that grows with you"** — 自改进 + 长期记忆 + Multi-Agent Kanban。
核心理念是"核心是窄腰、能力活在边缘"(`The core is a narrow waist; capability lives at the edges`)——`AGENTS.md:35`,通过 plugin / skill 扩展能力,核心 agent + 工具集尽可能保持稳定,以保护 per-conversation prompt caching。

---

## 1. 调研依据

主要源文件(均为只读快照,未修改):

| 文件 | 行数 | 关键作用 |
|------|------|----------|
| `hermes_constants.py` | 1193 | **核心**:`get_hermes_home()` / `get_default_hermes_root()` 单一真实来源 + 所有 well-known 路径定义 |
| `hermes_state.py` | 7503+ | SessionDB(SQLite + FTS5,WAL,有自愈 schema repair) |
| `hermes_cli/config.py` | 7847+ | `ensure_hermes_home()` —— 显式 init 流程 |
| `hermes_cli/main.py` | 14609+ | `_apply_profile_override()` —— Profile override 在 import 前生效 |
| `hermes_cli/checkpoints.py` | 245 | `hermes checkpoints` CLI 子命令 |
| `tools/checkpoint_manager.py` | 1526+ | Checkpoint v2(单共享 shadow git store) |
| `hermes_cli/kanban_db.py` | 9097+ | Multi-board Kanban SQLite + workspaces/attachments |
| `agent/memory_manager.py` | 1082+ | MemoryProvider 抽象,`hermes_home` 通过 kwargs 注入 |
| `hermes_cli/backup.py` | 1933+ | `hermes backup` —— 明确列出所有持久化文件 |
| `hermes_cli/profile_distribution.py` | 588+ | `USER_OWNED_EXCLUDE` —— 完整列出用户数据白/黑名单 |
| `hermes_cli/profiles.py` | ~1300+ | Named profiles 隔离(`<root>/profiles/<name>/`) |
| `hermes_cli/auth.py` | ~1100+ | `~/.hermes/auth.json` —— OAuth/API key 持久化 |
| `hermes_cli/cron.py` + `cron/jobs.py` + `cron/executions.py` | 多个 | `<root>/cron/{jobs.json, executions.db, output/, ticker_*}` |
| `hermes_cli/kanban.py` | ~3000+ | Kanban CLI + dispatcher |
| `cron/jobs.py` | 多 | `HERMES_DIR` = `get_hermes_home().resolve()` |
| `agent/file_safety.py` | ~600 | `_ROOT_CREDENTIAL_DIRS = ("pairing", "mcp-tokens")` |
| `hermes_cli/web_server.py` | 13200+ | Dashboard / API server |
| `agent/curator.py` | 多 | 自学习后台 curator,`skills/.curator_state` + `logs/curator/` |

辅助:
- `hermes_cli/setup.py:138-148` —— setup 流程,`get_hermes_home` / `ensure_hermes_home` 导入
- `cli.py:170,180` —— CLI 入口在 import 时立即 `get_hermes_home()`
- `hermes` wrapper —— 仅 8 行,直接 `from hermes_cli.main import main`
- `cli-config.yaml.example` —— 配置文件示例
- `AGENTS.md` —— 项目 intent 层

---

## 2. 三个核心问题的回答

### Q1. 工作区路径(HERMES_HOME)

**结论:既不是单纯写死,也不是单纯跟随当前目录 —— 是一个**四层优先级的链式解析**,且**为每条子系统链路分别提供专用 env override**。

#### 1.1 `get_hermes_home()` 单一真实来源

`hermes_constants.py:69-117` 是工作区路径的**唯一权威**:

```python
# hermes_constants.py:69-117
def get_hermes_home() -> Path:
    override = get_hermes_home_override()    # (1) ContextVar 进程内 override
    if override:
        return Path(override)
    val = os.environ.get("HERMES_HOME", "").strip()  # (2) env var
    if val:
        return Path(val)
    return _get_platform_default_hermes_home()       # (3) 平台默认值
```

| 优先级 | 来源 | 说明 | 证据 |
|--------|------|------|------|
| 1 | ContextVar `_HERMES_HOME_OVERRIDE` | **进程内、per-task 作用域**;通过 `set_hermes_home_override(token)` 显式设置,**不污染 os.environ**(因为 os.environ 是进程共享) | `hermes_constants.py:30-58` |
| 2 | `HERMES_HOME` 环境变量 | 显式 override;Docker / 自定义部署 / 测试常用 | `hermes_constants.py:96-97` |
| 3 | 平台原生默认值 | Windows: `%LOCALAPPDATA%\hermes`;POSIX: `~/.hermes` | `hermes_constants.py:62-67` |

**关键设计**:不写死 `~/.hermes`、不跟随 cwd。

#### 1.2 平台原生默认值的探测

```python
# hermes_constants.py:62-67
def _get_platform_default_hermes_home() -> Path:
    if sys.platform == "win32":
        local_appdata = os.environ.get("LOCALAPPDATA", "").strip()
        base = Path(local_appdata) if local_appdata else Path.home() / "AppData" / "Local"
        return base / "hermes"             # Windows: %LOCALAPPDATA%\hermes
    return Path.home() / ".hermes"          # POSIX: ~/.hermes
```

**没有 `pwd` fallback、没有 snap/flatpak 探测**——比 Cline / Aider 更简单。

#### 1.3 与 Profiles 的关系

Hermes 有**多 Profile** 隔离机制,`HERMES_HOME` 既可以是:
- root(默认):`~/.hermes`
- named profile:`~/.hermes/profiles/<name>/`

```python
# hermes_constants.py:121-159
def get_default_hermes_root() -> Path:
    """profile-aware 的根解析:
       - 标准部署:返回 ~/.hermes
       - Docker(/opt/hermes):返回 HERMES_HOME 本身
       - profile 模式(HOME=<root>/profiles/<name>):返回 <root>
    """
```

**Profile 解析在 CLI 入口的最早期**(必须在 import 任何 hermes 模块之前):
```python
# hermes_cli/main.py:347-528
def _apply_profile_override() -> None:
    """Pre-parse --profile/-p and set HERMES_HOME before imports.
    Many modules cache HERMES_HOME at import time (module-level constants)."""
```

⚠️ 这是**"必须环境变量不能放任何后置步骤"**的强制设计——因为有 30+ 模块在 import 时就把 `HERMES_HOME` 缓存为模块级常量(`main.py:350`)。

#### 1.4 跨 profile 共享 vs 隔离

| 子系统 | 路径根 | 跨 profile? | 证据 |
|--------|--------|-------------|------|
| `state.db`(session/message) | `get_hermes_home() / "state.db"` | **隔离**(per-profile) | `hermes_state.py:78-79` |
| `kanban.db` | `get_default_hermes_root() / "kanban.db"`(default board) | **共享**(by design) | `kanban_db.py:6-7,371-396` |
| `cron/jobs.json` | `get_hermes_home() / "cron/jobs.json"` | **隔离**(per-profile,security #4707) | `cron/jobs.py:55-66` |
| `projects.db` | `get_hermes_home() / "projects.db"` | **隔离** | `projects_db.py:14-50` |
| `gateway_state.json` | per-profile home | **隔离** | `service_manager.py:374`,`web_server.py:2573` |
| `auth.json` | `get_hermes_home() / "auth.json"` | **隔离**(但 default 可见性可 fall back) | `auth.py:894-931` |
| `checkpoints/store/` | `get_hermes_home() / "checkpoints/store"` | **隔离** | `checkpoint_manager.py:72` |
| `.env` | `get_hermes_home() / ".env"` | **隔离** | `hermes_constants.py:1160-1162` |

**设计哲学**:每个 profile 拥有独立的 config / .env / memory / skills / sessions / cron / logs / **state.db**,但**共享 Kanban 板**(因为 Kanban 是 cross-profile coordination primitive)。

#### 1.5 子系统的专用 env overrides

Hermes 不会用一个全局 env var 解决所有问题——而是为**关键子系统**提供专用 override:

| Env Var | 作用 | 证据 |
|---------|------|------|
| `HERMES_HOME` | 工作区根 | `hermes_constants.py:96` |
| `HERMES_KANBAN_HOME` | Kanban 根覆盖 | `kanban_db.py:372-389` |
| `HERMES_KANBAN_DB` | Kanban DB 文件路径 | `kanban_db.py:520-538` |
| `HERMES_KANBAN_BOARD` | 当前 board slug | `kanban_db.py:425-450` |
| `HERMES_KANBAN_WORKSPACES_ROOT` | workspaces 根 | `kanban_db.py:541-560` |
| `HERMES_KANBAN_ATTACHMENTS_ROOT` | 附件根 | `kanban_db.py:563-587` |
| `HERMES_BUNDLED_SKILLS` | Nix wrapper 技能根 | `hermes_constants.py:206-220` |
| `HERMES_OPTIONAL_SKILLS` | 打包 install 的 skills | `hermes_constants.py:170-184` |
| `HERMES_OPTIONAL_MCPS` | 打包 install 的 MCP | `hermes_constants.py:187-203` |
| `HERMES_LAZY_INSTALL_TARGET` | Docker 不可变镜像的 writable 目录 | `hermes_bootstrap.py:194-218` |
| `HERMES_REAL_HOME` | 真实 OS user home(非 profile HOME) | `hermes_constants.py:339-355` |
| `TERMINAL_HOME_MODE` | 子进程 HOME 模式(`auto`/`real`/`profile`) | `hermes_constants.py:392-429` |
| `HERMES_CHECKPOINT_TIMEOUT` | checkpoint git subprocess timeout | `checkpoint_manager.py:91` |
| `HERMES_PYTHON_SRC_ROOT` | hermes 源码根(防 cwd shadowing) | `hermes_bootstrap.py:144-169` |
| `HERMES_QUIET` | 静默启动 | `cli.py:67` |
| `HERMES_S6_SUPERVISED_CHILD` | s6 监督子进程标记 | `main.py:478` |
| `HERMES_REDACT_SECRETS` | 日志脱敏 | `main.py:540+` |
| `HERMES_NODE_TARGET_MAJOR` | 管理的 Node 主版本 | `hermes_constants.py:271` |

**这条设计直接回应了你的问题**——工作区路径"既写死又可配",因为最常见路径是 default,需要迁移/测试时通过 env var 显式覆盖,且**子系统的路径根相互独立**(Kanban 跨 profile 共享,state.db 隔离)。

---

### Q2. 工作区目录结构

> ⚠️ **Hermes 不像 Onion Agent 那样把 session 历史塞进一个 `session.json`** —— 而是用 **SQLite(state.db) + FTS5** 存 session/message 历史,文件系统只存**大对象/快照/配置/状态文件**。这是"数据布局 vs 存储后端"的明确分工。

#### 2.1 根布局(`get_hermes_home()`)

| 路径 | 类型 | 作用 | 关键文件/Schema | 证据 |
|------|------|------|-----------------|------|
| `config.yaml` | file | 主配置(YAML,~240 KB,32 个 section) | `hermes_constants.py:1146-1150` | config.py:1300+ |
| `.env` | file | 密钥/凭证(API key、token) | `hermes_constants.py:1159-1162`,`AGENTS.md:69-70` | dotenv |
| `auth.json` | file | OAuth/API key 持久化(带 file lock) | `auth.py:891-920` | |
| `state.db` (+ `-wal`/`-shm`) | SQLite | Session 索引 + FTS5 + 元数据 | `hermes_state.py:78-79,SCHEMA_VERSION=22` | |
| `state.db-wal`/`-shm` | sidecar | SQLite WAL 模式 | `hermes_state.py:325-375` | |
| `cron/` | dir | Cron 调度 | `cron/jobs.py:70-101` | |
| `sessions/` | dir | Session legacy JSON(被 state.db 取代) | `cli.py:1791,1818` | |
| `logs/` | dir | 日志(`agent.log`/`errors.log`/`gateway.log`/`gui.log`/`desktop.log`/`mcp-stderr.log`) | `logs.py:32-39` | |
| `logs/curator/` | dir | 后台 curator 报告 | `config.py:969` | |
| `memories/` | dir | 长期记忆存储(per-profile,见 2.3) | `config.py:943-944` | |
| `pairing/` | dir(legacy) | 平台 pairing 旧位 | `backup.py:791` | |
| `platforms/pairing/` | dir | 平台 pairing 新位 | `pairing.py:92`,`backup.py:792` | |
| `hooks/` | dir | 用户 shell hooks | `config.py:944` | |
| `image_cache/` | dir(legacy) | 旧 image cache | `config.py:944` | |
| `audio_cache/` | dir(legacy) | 旧 audio cache | `config.py:944` | |
| `video_cache/` | dir | video cache | `image_source.py:223` | |
| `document_cache/` | dir(legacy) | 旧 document cache | `tests:413` | |
| `cache/` | dir(consolidated) | 新 cache 根:`cache/{images,vision,video,audio}` | `image_source.py:221`,`get_hermes_dir()` | |
| `skills/` | dir | 用户创建的 skills(per-profile) | `hermes_constants.py:1154-1156` | |
| `skills/.curator_state` | file | 后台 curator 状态机 | `agent/curator.py:85-86` | |
| `checkpoints/` | dir | **Checkpoints v2** — 单共享 shadow git store | `checkpoint_manager.py:72` | |
| `checkpoints/store/` | git-store | 共享 git objects + per-project refs/indexes | `checkpoint_manager.py:75-83` | |
| `checkpoints/.last_prune` | file | 自动 prune 幂等性 marker | `checkpoint_manager.py:84` | |
| `checkpoints/legacy-<ts>/` | dir | 迁移的旧 per-project shadow repos | `checkpoint_manager.py:85-87` | |
| `kanban.db` | SQLite | **Kanban default board**(back-compat,放在 root 而非 boards/default) | `kanban_db.py:516-538` | |
| `kanban/` | dir | Kanban 根(`<root>/kanban/`) | `kanban_db.py:394-403` | |
| `kanban/boards/<slug>/` | dir | non-default boards;每个 board 独立 kanban.db + workspaces/ + logs/ + attachments/ | `kanban_db.py:485-499` | |
| `kanban/boards/<slug>/kanban.db` | SQLite | 命名板的 DB | `kanban_db.py:516-538` | |
| `kanban/boards/<slug>/workspaces/` | dir | scratch workspace 根 | `kanban_db.py:541-560` | |
| `kanban/boards/<slug>/attachments/` | dir | task 附件根 | `kanban_db.py:563-587` | |
| `kanban/current` | file | 当前 board 选择的 pointer | `kanban_db.py:405-412` | |
| `kanban/workspaces/` | dir | default board 的 workspaces(legacy 路径) | `kanban_db.py:548-559` | |
| `kanban/attachments/` | dir | default board 的 attachments | `kanban_db.py:585+` | |
| `projects.db` | SQLite | Project store(per-profile,root-anchored) | `projects_db.py:14-50` | |
| `response_store.db` | SQLite | gateway 对话历史 / tool payloads | `backup.py:785`,`profile_distribution.py:105` | |
| `memory_store.db` | SQLite | 全息记忆 facts/entities(plugins/memory/holographic) | `backup.py:786`,`plugins/memory/holographic/__init__.py:11` | |
| `verification_evidence.db` | SQLite | agent verification 审计轨迹 | `backup.py:787` | |
| `gateway_state.json` | file | gateway 当前/期望状态(running/stopped) | `web_server.py:2573`,`backup.py:773` | |
| `channel_directory.json` | file | 平台频道目录 | `backup.py:774` | |
| `channel_aliases.json` | file | 频道别名 | `backup.py:775` | |
| `processes.json` | file | 进程注册表 | `backup.py:776` | |
| `cron/jobs.json` | file | cron 作业定义(file lock 保护) | `cron/jobs.py:71` | |
| `cron/executions.db` | SQLite | cron 执行历史 | `cron/executions.py:21` | |
| `cron/output/<job_id>/<ts>.md` | file | cron 作业输出 | `cron/jobs.py:5,101` | |
| `cron/ticker_heartbeat` | file | in-process ticker 心跳 | `cron/jobs.py:77` | |
| `cron/ticker_last_success` | file | ticker 成功时间戳 | `cron/jobs.py:80` | |
| `cron/.tick.lock` | file | cron tick 跨进程 file lock | `web_server.py:151` | |
| `auth.lock` | file | auth.json 跨进程 file lock | `profile_distribution.py:108` | |
| `active_profile` | file | sticky 当前 profile 名称 | `hermes_constants.py:84-115`,`main.py:491` | |
| `hermes_history` | file | TUI 命令历史 | `cli.py:4013` | |
| `images/` | dir | 桌面 image 粘贴 | `cli.py:6312` | |
| `screenshots/` | dir | 桌面 screenshot | `web_server.py:1591` | |
| `chrome-debug/` | dir | Chrome 远程调试数据 | `browser_connect.py:128-129` | |
| `temp_vision_images/` | dir | 临时视觉输入 | `image_source.py:224` | |
| `temp_video_files/` | dir | 临时视频文件 | `image_source.py:225` | |
| `runtime/` | dir | active session PID 跟踪 | `active_sessions.py:80-81` | |
| `state-snapshots/` | dir | `/snapshot` CLI 的时间戳快照 | `backup.py:796-797` | |
| `backups/` | dir | 预 update 自动备份 | `backup.py:1281-1285` | |
| `mcp-tokens/` | dir | MCP OAuth 令牌存储(整个子树被 file_safety 屏蔽) | `file_safety.py:107-150` | |
| `home/` | dir | profile `HOME={HERMES_HOME}/home` 模式下的 OS user 沙箱 | `hermes_constants.py:325-355` | |
| `local/` | dir | 用户自定义 namespace(更新保留) | `profile_distribution.py:139` | |
| `node/` | dir | Hermes-managed portable Node.js(Nix/Windows) | `hermes_constants.py:262-265` | |
| `provider_models_cache.json` | file | 模型目录缓存 | `models.py:2666-2684` | |
| `cache/nous_recommended_cache.json` | file | 推荐模型 last-known-good | `models.py:835` | |
| `cache/model_catalog.json` | file | 模型 catalog 缓存 | `model_catalog.py:114-117` | |
| `models_dev_cache.json` | file | models.dev 缓存 | `models.py:117` | |
| `hermes-agent/` | dir | 源码仓库(wheel install 时是 venv/embed) | `AGENTS.md` | |
| `profiles/` | dir | 命名 profiles 容器(`<root>/profiles/<name>/`) | `hermes_cli/profiles.py:265-275` | |
| `bin/` | dir | user local bin(managed tools) | `profile_distribution.py:110` | |
| `.update_check` | file | 升级检查 marker | `profile_distribution.py:108` | |
| `plans/` | dir | 工作计划(用户在 CLI 内创建) | `profile_distribution.py:111` | |
| `workspace/` | dir | (旧)工作区,被 sessions/ 取代 | `profile_distribution.py:111` | |
| `browser_screenshots/` | dir | browser tool 截图 | `profile_distribution.py:112` | |
| `sandboxes/` | dir | code execution sandboxes | `profile_distribution.py:112` | |
| `SOUL.md` | file | (managed mode 必备) 灵魂 manifest | `config.py:843-913` | |

#### 2.2 Checkpoints v2 内部结构

`checkpoints/store/` 是一个**单共享 bare-ish git repo**(不是 per-project,见 `checkpoint_manager.py:30-46`):

```
~/.hermes/checkpoints/
    store/                          ← 单共享 git store
        HEAD, config, objects/     ← 标准 git internals(跨项目去重)
        refs/hermes/<hash16>       ← 每个 working_dir 的 branch tip
        indexes/<hash16>           ← 每个 working_dir 的 git index
        projects/<hash16>.json     ← {workdir, created_at, last_touch}
        info/exclude               ← 默认 exclude 规则
    .last_prune                     ← 自动 prune 幂等性
    legacy-<timestamp>/             ← 旧 per-project shadow repos(已迁移)
```

**v1 → v2 迁移原因**:`checkpoint_manager.py:34-46` 解释 v1 每个工作目录一个独立 shadow repo,12 个 worktree 烧 ~500MB 重复存储;v2 共享 objects 树后接近零边际成本。

#### 2.3 长期记忆存储路径

记忆存储有**两层**:

**(a) 持久化文件系统记忆**(`memories/`)
- 位置:`~/.hermes/memories/`
- 由 `ensure_hermes_home()` 预创建(`config.py:943-944`)
- **但本身**:**没有现成代码主动写它**——`grep -r 'home / "memories"' hermes-agent/` 显示没有任何 `get_hermes_home() / "memories" / x` 的写入路径
- 这是一个**为插件/未来扩展保留的目录**(可由 memory_provider 自己写)

**(b) 记忆 provider 的数据库**(典型):
- `memory_store.db`(全息 / holographic 插件)
- `~/.honcho/`、`~/.hindsight/`、`~/.openviking/` 等(provider external,需要 backup_paths() 声明)

**关键设计**:`agent/memory_provider.py:69-72` 显式要求每个 provider 接受 `hermes_home` 作为 kwargs:

```python
# agent/memory_manager.py:1218-1224
def initialize_all(self, session_id: str, **kwargs) -> None:
    if "hermes_home" not in kwargs:
        from hermes_constants import get_hermes_home
        kwargs["hermes_home"] = str(get_hermes_home())
```

这让 provider 可以"profile-scoped 写自己的目录"而不用硬编码 `~/.hermes`。

#### 2.4 Kanban Multi-Board 结构

```
<root>/                              ← get_default_hermes_root()
├── kanban.db                        ← default board(back-compat, 不在 boards/)
├── kanban/
│   ├── current                      ← pointer: "default" 或其他 slug
│   ├── boards/
│   │   ├── atm10-server/            ← 命名 board
│   │   │   ├── kanban.db
│   │   │   ├── board.json
│   │   │   ├── workspaces/
│   │   │   ├── attachments/
│   │   │   └── logs/
│   │   └── default/                 ← metadata only(DB 不在这)
│   │       ├── board.json
│   │       ├── workspaces/
│   │       ├── attachments/
│   │       └── logs/
│   ├── workspaces/                  ← default 的 workspaces(legacy path)
│   ├── attachments/                 ← default 的 attachments
│   └── logs/                        ← default 的 logs
```

**关键设计**:`default` board 的 DB 在 `<root>/kanban.db`(根而不是 boards/default/kanban.db)以**保持向后兼容**;其它 board 都在 `boards/<slug>/kanban.db`(`kanban_db.py:20-23, 485-499`)。

#### 2.5 OAuth / MCP Token 结构

- `~/.hermes/auth.json` —— 主要 OAuth/API key(`auth.py:894-895`,带 file lock)
- `~/.hermes/mcp-tokens/<server>.json` —— MCP OAuth access token(动态)
- `~/.hermes/mcp-tokens/<server>.client.json` —— 动态注册的 client credentials
- `~/.hermes/.anthropic_oauth.json` —— Anthropic OAuth
- `~/.hermes/auth/google_oauth.json` —— Google OAuth
- `~/.hermes/auth.lock` —— 跨进程锁

**安全设计**:`file_safety.py:107-150` 和 `gateway/platforms/base.py:1193-1210` 显式把 `mcp-tokens/`、`pairing/`、`auth.json`、`auth.lock` 列为**整个子树凭证,LLM 不可读**。

#### 2.6 不进 `~/.hermes` 的例外(显式声明)

- 真实 OS user HOME:`~/.bashrc`、外部 CLI 凭证等(由 `get_real_home()` 处理,`hermes_constants.py:339-355`)
- Container 镜像的 Node.js、apt packages(由 `hermes-managed node` 处理)
- lazy install 持久化目录:`HERMES_LAZY_INSTALL_TARGET`(Docker 不可变镜像的可写挂载)

---

### Q3. 工作区创建

**结论:三种模式都存在,以"隐式 + 显式按需"为主,`ensure_hermes_home()` 是统一入口。**

#### 3.1 显式 init:`ensure_hermes_home()`

```python
# hermes_cli/config.py:915-947
def ensure_hermes_home():
    """Ensure ~/.hermes directory structure exists with secure permissions."""
    home = get_hermes_home()
    # Named profiles must be created explicitly (e.g. ``hermes profile create``).
    if home.parent.name == "profiles" and not home.exists():
        raise FileNotFoundError(
            f"Named profile home does not exist: {home}. "
            "Create the profile explicitly before using it."
        )
    if is_managed():
        old_umask = os.umask(0o007)
        try:
            _ensure_hermes_home_managed(home)  # Nix 模式(已 activation)
        finally:
            os.umask(old_umask)
    else:
        home.mkdir(parents=True, exist_ok=True)
        _secure_dir(home)  # chmod 0o700
        for subdir in (
            "cron", "sessions", "logs", "logs/curator", "memories",
            "pairing", "hooks", "image_cache", "audio_cache", "skills",
        ):
            d = home / subdir
            d.mkdir(parents=True, exist_ok=True)
            _secure_dir(d)
        _ensure_default_soul_md(home)
```

**关键设计**:
- 预创建 **10 个子目录**:`cron/`, `sessions/`, `logs/`, `logs/curator/`, `memories/`, `pairing/`, `hooks/`, `image_cache/`, `audio_cache/`, `skills/`
- 全部 `chmod 0o700` 安全模式
- **.env、`auth.json`、`state.db`、`kanban.db`、`checkpoints/`、`cache/`、`projects.db` 等不在 pre-create 列表**——它们按需首次使用时由各自模块隐式创建

#### 3.2 隐式创建(由各模块首次使用时自创建)

| 模块 | 创建路径 | 证据 |
|------|----------|------|
| `hermes_state.SessionDB` | `state.db` + WAL sidecar | `hermes_state.py:824-825(self.db_path.parent.mkdir)` |
| `kanban_db.connect` | `kanban.db` + WAL | `kanban_db.py` 中 `connect()` |
| `projects_db.connect` | `projects.db` | `projects_db.py:50` |
| `checkpoint_manager` | `checkpoints/store/`, `checkpoints/legacy-*/` | `checkpoint_manager.py:_init_store` |
| `cron.jobs.HERMES_DIR` | `cron/jobs.json`、首次 lock 时创建 | `cron/jobs.py:66-101` |
| `cron.executions.EXECUTIONS_FILE` | `cron/executions.db` | `cron/executions.py:21` |
| `auth._auth_file_path` | `auth.json` | `auth.py:894-895` |
| `cli._state_dir` | `runtime/` | `active_sessions.py:80-81` |
| `cli image paste` | `images/` | `cli.py:6312` |
| `kanban_db workspaces_root` | `kanban/workspaces/` 或 `kanban/boards/<slug>/workspaces/` | `kanban_db.py:541-560` |
| `kanban_db attachments_root` | `kanban/attachments/` 或 `kanban/boards/<slug>/attachments/` | `kanban_db.py:563-587` |
| `kanban_db current_board_path` | `kanban/current` | `kanban_db.py:405-412` |
| `model_catalog._cache_path` | `cache/model_catalog.json` | `model_catalog.py:114-117` |
| `agent/curator._state_file` | `skills/.curator_state` | `agent/curator.py:85-86` |

#### 3.3 Bootstrap 流程(完整启动链)

```python
# 入口顺序(关键 — 顺序错了会 ImportError)
# 1. hermes_bootstrap (Windows UTF-8 + sys.path 防护)
import hermes_bootstrap
# 2. Profile override 必须在 import 任何 hermes 模块之前
_apply_profile_override()  # 设置 HERMES_HOME
# 3. .env 加载(load ~/.hermes/.env first, then project root)
load_hermes_dotenv(...)
# 4. Security flag bridge (config.yaml → env var)
# 5. hermes_constants 全局可访问
from hermes_cli.config import get_hermes_home
# 6. CLI 主循环 — ensure_hermes_home() 在 setup() 期间调用
```

**Setup 流程**(`hermes_cli/setup.py:2709-2891`):
- 第一次运行:quick setup / blank slate / full setup
- 现有 install:detect 现有 config → 备份 → 增量更新
- 调 `ensure_hermes_home()` 创建目录骨架
- 写 `config.yaml`、`.env`、`auth.json`(可选)
- 提示"📁 All your files are in `~/.hermes/`:"(`setup.py:633-640`)

**profile 子命令 bootstrap**(`hermes_cli/profiles.py:520-531`):
```python
token = set_hermes_home_override(str(profile_dir))
try:
    current_ver, latest_ver = check_config_version()
    if current_ver < latest_ver:
        migrate_config(interactive=False, quiet=True)
finally:
    reset_hermes_home_override(token)
```

#### 3.4 升级 / 迁移机制

`hermes_cli/backup.py:1281-1285` 定义 `_PRE_UPDATE_BACKUPS_DIR = "backups"`,即每次 `hermes update` 前自动 snapshot 关键文件到 `backups/pre-update-<ts>/`(类似 `state-snapshots/`)。

Checkpoint v1→v2 自动迁移:`checkpoint_manager.py:373-379` 自动 rename 旧 per-project repos 到 `legacy-<ts>/`。

Profile export/import:`hermes_cli/profile_distribution.py:91-130` 定义哪些路径**用户拥有**(不进入 distribution),哪些是**distribution owned**。

`backup.py:765-794` 完整列出 quick snapshot 要备份的 STATE_FILES(22 个核心文件 + 3 个 db)。

#### 3.5 Schema 版本化与 self-heal

`state.db` 有显式的 schema 版本:
- `SCHEMA_VERSION = 22`(`hermes_state.py:82`)
- `kanban.db` 也有自己的 schema 演进
- `state.db` 有**自动 schema repair**:`repair_state_db_schema()`(`hermes_state.py:529+`)3 阶段策略:
  1. FTS in-place rebuild
  2. sqlite_master 去重
  3. drop FTS + VACUUM(让下次 open 重建)
- **WAL 自动 fallback**:`apply_wal_with_fallback()`(`hermes_state.py:319+`)在 NFS/SMB 检测到 SQLITE_PROTOCOL 时降级到 `journal_mode=DELETE`
- **macOS 强制 synchronous=FULL**:`_enforce_macos_synchronous_full()`(`hermes_state.py:259+`)防 launchd 关机时 btree 损坏

**这是 Hermes 的"运行时不变量"哲学**:`repair_state_db_schema`、`apply_wal_with_fallback`、`enforce_macos_synchronous_full` 三件套确保 SQLite 在任何文件系统上"能开就能用"。

---

## 3. 关键代码片段(精选)

### 3.1 `get_hermes_home()` —— 单点真相

`hermes_constants.py:69-117` 的完整 4 层解析(见 Q1.1)。

### 3.2 `ensure_hermes_home()` —— 显式 init

`hermes_cli/config.py:915-947`(见 Q3.1)。

### 3.3 Checkpoint v2 layout(单共享 store)

```python
# tools/checkpoint_manager.py:72-87
CHECKPOINT_BASE = get_hermes_home() / "checkpoints"

# Single shared store directory under CHECKPOINT_BASE.
_STORE_DIRNAME = "store"
_REFS_PREFIX = "refs/hermes"
_INDEXES_DIRNAME = "indexes"
_PROJECTS_DIRNAME = "projects"
_LEGACY_PREFIX = "legacy-"
```

### 3.4 Kanban 跨 profile 共享 + default board 兼容

```python
# hermes_cli/kanban_db.py:516-538
def kanban_db_path(board: Optional[str] = None) -> Path:
    override = os.environ.get("HERMES_KANBAN_DB", "").strip()
    if override:
        return Path(override).expanduser()
    slug = _normalize_board_slug(board)
    if slug is None:
        slug = get_current_board()
    if slug == DEFAULT_BOARD:
        return kanban_home() / "kanban.db"     # back-compat root
    return board_dir(slug) / "kanban.db"       # named board
```

### 3.5 ContextVar HERMES_HOME 覆盖(per-task,非全局)

```python
# hermes_constants.py:19-58
_HERMES_HOME_OVERRIDE: ContextVar[str | object] = ContextVar(
    "_HERMES_HOME_OVERRIDE", default=_UNSET
)

def set_hermes_home_override(path: str | Path | None) -> Token:
    """This is for in-process, per-task scoping.  It deliberately does not
    mutate os.environ because that is shared by every thread in the process."""
```

### 3.6 SessionDB 自愈

```python
# hermes_state.py:807-820
try:
    _connect_and_init()
except sqlite3.DatabaseError as exc:
    # The malformed-schema class fails on the very first statement —
    # before _init_schema can run — so it can't be caught at the
    # FTS-rebuild layer. Recover by repairing sqlite_master in place.
    if not is_malformed_db_error(exc) or not _claim_repair_attempt(self.db_path):
        raise
    # ... repair + reopen once
```

### 3.7 `_apply_profile_override` 必须在 import 之前

```python
# hermes_cli/main.py:347-356
# Profile override — MUST happen before any hermes module import.
#
# Many modules cache HERMES_HOME at import time (module-level constants).
# We intercept --profile/-p from sys.argv here and set the env var so that
# every subsequent ``os.getenv("HERMES_HOME", ...)`` resolves correctly.
```

### 3.8 `_ROOT_CREDENTIAL_DIRS`(LLM 不可读)

```python
# gateway/platforms/base.py:1193-1210
_ROOT_CREDENTIAL_DIRS = (
    "pairing",
    ...
)
# agent/file_safety.py:298-313
# mcp-tokens/: directory prefix match — anything inside is OAuth token material.
for hd in hermes_dirs:
    try:
        mcp_tokens = (hd / "mcp-tokens").resolve()
    ...
    if resolved == mcp_tokens or resolved.startswith(mcp_tokens + os.sep):
        return "Access denied: mcp-tokens/ ..."
```

---

## 4. 与 Onion Agent 设计的关联

Onion Agent 的核心哲学是 **"智能体一切活动围绕 `session.json`,Agent Loop 是自动累加器"**。Hermes 的工作区设计与此**存在结构性差异**,但有 5 条可借鉴的设计原则。

### 4.1 关键差异:Hermes 不用单一 `session.json`

Hermes 的做法:
- session/messages 存 **SQLite + FTS5**(`state.db`),不是 JSON 文件
- 长历史能分块查询、能 FTS、能压缩
- 跨 turn 元数据(模型、token、成本、cwd、git_branch、parent_session_id)结构化
- 文件系统只存**配置 / 凭证 / 大对象 / 状态文件 / 日志**

**给 Onion Agent 的反思**:
- 如果 Onion Agent 真的把"全部上下文"塞一个 `session.json`,到 1MB+ 后 token 检索效率会急剧下降
- 但如果你坚持 JSON-as-累加器,**至少要像 Hermes 一样**:定义 schema version(`SCHEMA_VERSION=22`)、写 auto-repair、写 WAL-friendly atomic write、定义 parent/branch/compression child 关系(`hermes_state.py:36-60`)
- 更实际:可以把 `session.json` 当作**可读的、可移植的、人类友好的镜像/导出格式**,把真正的"活的"会话状态放到 SQLite,这与 Hermes 的设计并不冲突

### 4.2 借鉴 1:三层空间("活跃 vs 缓存 vs 备份")

Hermes 把工作区分成清晰的"圈层":

```
活跃(进程修改): state.db, kanban.db, jobs.json, auth.json, gateway_state.json
缓存(可重生成): cache/, image_cache/, audio_cache/, logs/, sessions/*.json (legacy)
快照(永不删): backups/pre-update-*/, state-snapshots/, checkpoints/store/
只读/凭证(LLM 不可写): auth.json, auth.lock, .env, mcp-tokens/, pairing/
```

**Onion Agent 可借鉴**:定义 `session.json` 的"不可变快照目录"(`onion_home/snapshots/<sid>.json`)+ "活跃累加目录"(`onion_home/sessions/<sid>.json`)+ "FTS 索引"(`onion_home/state.db`)。Onion 的"累加器"哲学与 Hermes 的"snapshot 可恢复 + 活对象 fast"是可以调和的。

### 4.3 借鉴 2:Schema 版本 + 自愈

Hermes 的 `repair_state_db_schema` 3 阶段策略(`hermes_state.py:529+`):
1. FTS in-place rebuild(最不破坏)
2. sqlite_master 去重
3. drop FTS + VACUUM(让下次 init 重建)

**Onion Agent 可借鉴**:如果 `session.json` 写坏了,不要让用户手动 `rm session.json` 重来——加一个"读到损坏 JSON 时的修复策略":保留消息、丢 metadata、标记 `recovery_level=2` 写回。

### 4.4 借鉴 3:平台原生 + env override 链

Hermes 的路径解析(`hermes_constants.py:69-117`):
1. ContextVar override(per-task)
2. env var(跨进程)
3. 平台默认(`%LOCALAPPDATA%\hermes` / `~/.hermes`)

**Onion Agent 可借鉴**:不要写死 `~/.onion/`。在 Windows 用 `%LOCALAPPDATA%\onion`、允许 `ONION_HOME` env override、profile-scoped 用 `set_hermes_home_override` 类的 per-task override。

### 4.5 借鉴 4:Cross-cutting 子系统独立 env override

Hermes 给 Kanban 单独 5 个 env vars(KANBAN_HOME / KANBAN_DB / KANBAN_BOARD / KANBAN_WORKSPACES_ROOT / KANBAN_ATTACHMENTS_ROOT),而不用全局覆盖。

**Onion Agent 可借鉴**:如果以后加"工作区外的协作能力"(类似 Kanban),不要用 `ONION_HOME=...` 覆盖全部——给每个子系统独立 override,符合 Unix 哲学"做一件事做好"。

### 4.6 借鉴 5:Profile 隔离 + 共享根(细粒度)

Hermes 决定**每个子系统的根是否跨 profile 共享**(Q1.4 表格):
- `state.db` 隔离
- `kanban.db` 共享
- `cron/jobs.json` 隔离
- `auth.json` 隔离 + 可见性 fall back

**Onion Agent 可借鉴**:`session.json` 应该**默认隔离**(每 profile 一份),但**协作 metadata**(如果做 Kanban / dispatch)放在**profile-共享**的根。这避免了"profile 切换后无法跨 profile 协调"的问题。

### 4.7 借鉴 6:确保 LLM 不可读凭证

Hermes 的 `_ROOT_CREDENTIAL_DIRS`(`file_safety.py:107-150`,`gateway/platforms/base.py:1193-1210`)是**显式白名单**+**LLM 工具级拒绝**。

**Onion Agent 可借鉴**:即使用户说"我所有上下文都在 `session.json`",也要在文件工具层**强制拒绝读取 `~/.onion/auth.json`、`~/.onion/.env`、MCP token 目录**——这是 Hermes 用真实漏洞(#50502, #47111)换来的工程纪律。

### 4.8 借鉴 7:Profile override 必须在 import 之前

`hermes_cli/main.py:347-528` 的 `_apply_profile_override()` 是个**反模式示范**——但它存在的原因是因为代码已经写出来了,只能"在最早的时间点插桩"。如果 Onion Agent 早期就**约定"HERMES_HOME 类常量不能用模块级缓存"**,就不需要这种 hack。

**Onion Agent 可借鉴**:**在第一行 import 中就用 `os.getenv("ONION_HOME")` + 函数返回 `Path`**,而不是 `HOME = Path("~/.onion").expanduser()`(模块级常量)。

---

## 5. 不确定 / 未找到

| 项 | 状态 | 说明 |
|----|------|------|
| `~/.hermes/memories/` 的实际写入方 | ⚠️ 未明确 | `ensure_hermes_home()` 预创建此目录但 `grep` 找不到任何 `home / "memories"` 的写入路径;推测是给第三方 memory provider 用的(可参考 `plugins/memory/*`) |
| `~/.hermes/workspace/` 用途 | ⚠️ 已废弃 | `profile_distribution.py:111` 列为"旧"工作区,被 `sessions/` 取代 |
| `~/.hermes/plans/` 用途 | ❓ 未找到定义 | 出现在 `USER_OWNED_EXCLUDE`,但具体由谁写?可能在 CLI `/plan` slash command 或某个 skill |
| `~/.hermes/scripts/` | ⚠️ 部分 | `web_server.py:10467` 提到 `profile_home / "scripts"`,似乎是 web_server 的可选脚本目录 |
| Hermes 对 Onion-style "session.json 累加器" 的态度 | ❓ 未涉及 | Hermes 用 SQLite,没有 jsonl/json 作为主会话存储的先例;不能直接对比 |
| `~/.hermes/sessions/` 实际使用情况 | ⚠️ 混合 | 旧 JSON 会话格式 + 新 SQLite(state.db)+ 一些 CLI 内部 cache(`status.py:566` 还读 `sessions/sessions.json`) |
| `~/.hermes/hooks/` 默认内容 | ❓ 未确认 | `config.py:944` 预创建,但具体 hook 文件格式未在主代码中发现 |
| 单进程多 task 的 per-task HERMES_HOME override 实际使用 | ⚠️ 推测 | `set_hermes_home_override`(`hermes_constants.py:30-58`)有完整实现,但只在 `profiles.py:525` 和 `memory_oauth.py:50` 两处被调;在多 agent 并发场景的覆盖度未确认 |

---

## 6. 关键经验教训(TL;DR)

1. **不写死 `~/.xxx`** —— 用 `get_xxx_home()` + env var + 平台默认三层
2. **不要单一 `session.json`** —— 至少要 SQLite;JSON 当"可读快照/导出"用
3. **子系统的根路径要独立** —— Kanban 不应该用全局 HOME 覆盖
4. **Profile 隔离要细粒度决定** —— 哪些隔离(`state.db`)哪些共享(`kanban.db`)要明确写在代码注释里
5. **LLM 永远不能读凭证** —— 显式 `file_safety` 白名单 + 工具层强制拒绝
6. **Schema 版本 + 自愈是必须的** —— `repair_state_db_schema()` 这种 3 阶段 fallback 在生产环境是刚需
7. **Cross-process file lock** —— `auth.lock` / `cron/jobs.json lock` / `state.db WAL` 都是为了让"多个 Hermes 进程 + cron + 用户的 IDE 插件" 都能安全写
8. **Secure by default** —— `chmod 0o700`、`secure_parent_dir`、`_secure_file` 全套;managed mode (NixOS) 还用 setgid 2770
9. **"核心是窄腰,能力活在边缘"** —— `AGENTS.md:35` 的设计哲学决定了 90% 的能力(平台、provider、memory backend、browser)都是 plugin / skill / 外部 service,核心只有 state.db + agent loop

---

**报告完。**
