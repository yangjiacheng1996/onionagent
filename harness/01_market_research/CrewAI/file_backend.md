# CrewAI — 工作区(File Backend)调研报告

> 调研对象:`crewAIInc/crewAI` (本机快照 `clone/crewAI`)
> 调研时间:2026-07
> 报告版本:v1.0
> 调研范围:工作区路径、目录结构、初始化方式

---

## 0. 智能体一句话定位

**Role + Goal + Tools + Process 编排的"角色化团队"框架** —— `Agent`/`Crew`/`Task` 三件套定义"谁、用什么工具、做什么任务",通过 `Process.sequential`(顺序) / `Process.hierarchical`(带 manager agent 的分层委派)驱动多 Agent 协作;与 LangChain 生态深度集成(`BaseTool` 兼容、`crewai_tools` 大量封装),记忆(LanceDB 向量库)与知识(ChromaDB 向量库)分开存储,主打"给员工写任务书"一样的开发者体验。

---

## 1. 调研依据

### 1.1 源码版本

- 工作区根:`C:\workspace\github\onionagent\harness\01_market_research\clone\crewAI`
- 单仓多包结构(monorepo):
  - `lib/crewai/` — 核心 SDK(`src/crewai/` 真正源码)
  - `lib/crewai-core/` — 跨包共享(路径、用户数据、token、锁)
  - `lib/crewai-cli/` — `crewai` 命令行(`src/crewai_cli/`)
  - `lib/crewai-tools/`、`lib/crewai-files/` — 工具与文件生态

### 1.2 关键代码路径

| 模块 | 路径 | 作用 |
|---|---|---|
| CLI 入口 | `lib/cli/src/crewai_cli/cli.py` | `crewai create / run / chat / memory / checkpoint / reset_memories` |
| 项目脚手架 | `lib/cli/src/crewai_cli/create_crew.py` `create_json_crew.py` | 显式初始化项目 |
| 模板 | `lib/cli/src/crewai_cli/templates/crew/`, `templates/json_crew/`, `templates/flow/` | `crewai create` 拷的样板 |
| Crew 核心 | `lib/crewai/src/crewai/crew.py` | `Crew` 类的 Pydantic 模型 |
| Task | `lib/crewai/src/crewai/task.py` | `Task` 类 + `output_file` 落盘逻辑 |
| 装饰器基类 | `lib/crewai/src/crewai/project/crew_base.py` | `@CrewBase` + `base_directory` 解析 |
| 统一记忆 | `lib/crewai/src/crewai/memory/unified_memory.py` | `Memory` 类 |
| 记忆存储 | `lib/crewai/src/crewai/memory/storage/lancedb_storage.py` | LanceDB 后端 + 路径解析 |
| Knowledge | `lib/crewai/src/crewai/knowledge/knowledge.py` | `Knowledge` 类 |
| Knowledge 源 | `lib/crewai/src/crewai/knowledge/source/base_file_knowledge_source.py` | 文件路径解析 |
| 文件日志 | `lib/crewai/src/crewai/utilities/file_handler.py` | `output_log_file` 落盘 |
| Pickle 训练 | 同上 `PickleHandler` | `trained_agents_data.pkl` |
| 路径工具 | `lib/crewai-core/src/crewai_core/paths.py` | `db_storage_path()` = `appdirs.user_data_dir(Path.cwd().name, "CrewAI")` |
| 常量 | `lib/crewai-core/src/crewai_core/constants.py` | `KNOWLEDGE_DIRECTORY = "knowledge"` |
| 全局设置 | `lib/crewai-core/src/crewai_core/settings.py` | `~/.config/crewai/settings.json` |
| 用户数据 | `lib/crewai-core/src/crewai_core/user_data.py` | `db_storage_path()/.crewai_user.json` |
| 记忆 TUI | `lib/cli/src/crewai_cli/memory_tui.py` | `crewai memory` 浏览器 |

---

## 2. 三个核心问题的回答

### Q1. 工作区路径

**核心结论:CrewAI 没有"工作区"显式概念,而是按"数据类别"分散在三类位置 —— ① 用户级平台设置(`~/.config/crewai/`)、② 项目级 CWD 派生数据(`./knowledge/`、`./.checkpoints/`、`./logs.txt`)、③ 全局按当前项目名命名的用户目录(`appdirs.user_data_dir(Path.cwd().name, "CrewAI")`,承载 memory/knowledge 向量库与 SQLite)。**

| 数据类别 | 默认路径(无任何 env/参数覆盖时) | 来源 | 可自定义? |
|---|---|---|---|
| **CLI 全局设置**(组织、token、enterprise URL) | `~/.config/crewai/settings.json`(Linux) / `%USERPROFILE%\.config\crewai\settings.json`(Windows) | `lib/crewai-core/src/crewai_core/settings.py:11` | ❌(硬编码 `Path.home() / ".config" / "crewai" / "settings.json"`),有 fallback 链(temp、cwd) |
| **CLI 用户数据**(trace consent 等) | `appdirs.user_data_dir(Path.cwd().name, "CrewAI")/.crewai_user.json` | `lib/crewai-core/src/crewai_core/user_data.py:21` | ❌(跟随 CWD 项目名) |
| **Memory 统一记忆(LanceDB)** | `appdirs.user_data_dir(Path.cwd().name, "CrewAI")/memory/` | `lib/crewai/src/crewai/memory/storage/lancedb_storage.py:68-74` | ✅ 通过 `Memory(storage="<path>")` 或环境变量 `CREWAI_STORAGE_DIR`(覆写) |
| **Knowledge 向量库(ChromaDB)** | `appdirs.user_data_dir(Path.cwd().name, "CrewAI")/`(作为 `persist_directory`) | `lib/crewai/src/crewai/rag/chromadb/constants.py:11` `chromadb/config.py:46` | ✅ 通过 `Knowledge(storage=KnowledgeStorage(...))` 注入自定义 |
| **Kickoff task outputs(SQLite)** | `appdirs.user_data_dir(Path.cwd().name, "CrewAI")/latest_kickoff_task_outputs.db` | `lib/crewai/src/crewai/memory/storage/kickoff_task_outputs_storage.py:26` | ✅ 通过 `TaskOutputStorageHandler(storage=KickoffTaskOutputsSQLiteStorage(db_path=...))` |
| **Flow 状态(SQLite)** | `appdirs.user_data_dir(Path.cwd().name, "CrewAI")/flow_states.db` | `lib/crewai/src/crewai/flow/persistence/sqlite.py:55` | ✅ 通过 `SQLiteFlowPersistence(db_path=...)` |
| **Knowledge source 源文件**(用户文件) | `<CWD>/knowledge/<filename>`(相对 CWD) | `lib/crewai/src/crewai/knowledge/source/base_file_knowledge_source.py:78` `convert_to_path = Path("knowledge/" + path)` | ❌(硬编码前缀 `KNOWLEDGE_DIRECTORY = "knowledge"`) |
| **Crew 配置 YAML** | `src/<name>/config/agents.yaml`、`src/<name>/config/tasks.yaml`(相对 `base_directory = inspect.getfile(cls).parent`) | `lib/crewai/src/crewai/project/crew_base.py:135-143, 351` | ❌(`@CrewBase` 自动绑定 `base_directory = crew.py 所在目录`) |
| **Task output 落盘** | `Task.output_file` 字段(默认 `None`,路径校验严格) | `lib/crewai/src/crewai/task.py:1233-1270` `_save_file` | ✅ 任意用户路径(有 `..`/shell 字符校验) |
| **Crew 日志** | `logs.txt`(`output_log_file=True` 时)或 `output_log_file="x.json"`(用户路径) | `lib/crewai/src/crewai/utilities/file_handler.py:48-59` | ✅ bool 或 string |
| **Checkpoint** | `./.checkpoints/`(目录)或 `./.checkpoints.db`(SQLite),在 CWD 下 | `lib/cli/src/crewai_cli/checkpoint_cli.py:61-62, 1103` | ✅ 通过 `crewai checkpoint --location <path>` 或 `@persist(SQLiteFlowPersistence(db_path=...))` |
| **训练数据 pickle** | `os.getcwd()/<file_name>.pkl`(默认 `trained_agents_data.pkl`) | `lib/crewai/src/crewai/utilities/file_handler.py:130-138` `PickleHandler.__init__` | ✅ 通过 `crewai train -f <path>` 或 `Crew(trained_agents_file=...)` |

**关键发现 —— 三层路径策略**:
1. **绝对用户级(硬编码 `Path.home()`)** — 平台设置(settings.json)
2. **跨项目用户级(用 CWD 项目名 namespace)** — 所有向量库与 SQLite(`appdirs.user_data_dir(<cwd-name>, "CrewAI")`)。**这是 CrewAI 最重要的"工作区"约定:把 CWD 目录名当成命名空间,放进跨项目的全局用户数据目录。**
3. **项目内 CWD 派生** — 配置文件(`base_directory`)、`./knowledge/`、`./.checkpoints/`、`./logs.txt`、`./report.md`(由 `task.output_file` 落盘)

**自定义覆盖方式**:
- 全局 env:`CREWAI_STORAGE_DIR` 改写 memory 路径(`lancedb_storage.py:68`)
- 代码注入:`Memory(storage=...)`、`Knowledge(storage=...)`、`SQLiteFlowPersistence(db_path=...)`
- CLI 参数:`crewai memory --storage-path <path>`(只影响 TUI 显示,不改实际 storage)

### Q2. 工作区目录结构

**核心结论:CrewAI 没有"工作区 = 一个根目录"的统一结构,而是按"职责"分散。`crewai create` 显式脚手架出的项目目录 + CWD 派生目录 + 用户全局目录,共同构成 CrewAI 项目的文件系统拓扑。**

#### 2.1 `crewai create crew <name>` 生成的经典项目结构(classic / YAML 风格)

```
<name>/                              ← 项目根(由 `name` 决定,`folder_name = name.lower().replace(' ','_').replace('-','_')`)
├── tests/                           ← 测试目录(空)
├── knowledge/                       ← Knowledge source 源文件目录
│   └── user_preference.txt          ← 模板默认放的样例
├── src/<name>/                      ← Python 包根(`base_directory` 由 `@CrewBase` 自动绑定到此)
│   ├── tools/                       ← 用户自定义工具
│   │   ├── custom_tool.py
│   │   └── __init__.py
│   ├── config/                      ← YAML 配置(相对 `base_directory` 解析)
│   │   ├── agents.yaml              ← `agents_config` 默认指向此处
│   │   └── tasks.yaml               ← `tasks_config` 默认指向此处
│   ├── __init__.py
│   ├── main.py                      ← 入口(`run / train / replay / test / run_with_trigger`)
│   └── crew.py                      ← `@CrewBase` 装饰的 crew 类
├── .gitignore                       ← 仅忽略 .env / __pycache__ / .DS_Store
├── pyproject.toml                   ← 含 [tool.crewai] type = "crew" 和 [project.scripts] 注册的 run_crew/train/replay/test
├── README.md
└── AGENTS.md                        ← AI 编码助手文档(2025+ 新增)

```

来源:`lib/cli/src/crewai_cli/create_crew.py:97-200`、`templates/crew/`。

#### 2.2 `crewai create crew <name>` 默认 JSON 风格(2025+ 新版,`create_json_crew.py`)

```
<name>/                              ← 直接平铺,无 src/ 包装
├── agents/                          ← 每 agent 一个 .jsonc
│   ├── researcher.jsonc
│   └── ...
├── tools/                           ← 自定义工具
├── skills/                          ← skills
├── knowledge/
│   └── user_preference.txt
├── crew.jsonc                       ← 主配置(替代 crew.py)
├── pyproject.toml                   ← [tool.crewai] type = "crew", definition = "crew.jsonc"
├── .env
├── .gitignore                       ← + report.md
└── README.md
```

来源:`lib/cli/src/crewai_cli/create_json_crew.py:694-790`、`templates/json_crew/`。

#### 2.3 运行时由 CWD 自动创建的文件/目录(用户级 + 项目级混合)

| 路径(相对 CWD) | 何时创建 | 作用 | 来源 |
|---|---|---|---|
| `<CWD>/knowledge/` | 用户放置 source 文件;`convert_to_path` 硬编码前缀 `"knowledge/"` | Knowledge source 源数据 | `base_file_knowledge_source.py:78` |
| `<CWD>/logs.txt` 或 `<CWD>/<custom>.json` | `Crew(output_log_file=True/路径)` 时,`_file_handler.log()` 追加写 | Crew 全局运行日志 | `file_handler.py:48-59, 75-118` |
| `<CWD>/report.md`(典型) | `Task(output_file="report.md")` 时 `_save_file()` 写入 | Task 产物 | `task.py:1233-1270` |
| `<CWD>/trained_agents_data.pkl` | `Crew.train()` 训练时 | 训练数据 | `file_handler.py:130-138` `PickleHandler` |
| `<CWD>/.checkpoints/` 或 `<CWD>/.checkpoints.db` | `crewai checkpoint` 命令 / flow `@persist()` 时 | Flow checkpoint | `checkpoint_cli.py:61-62` |
| `<CWD>/.crewai_user.json` 副本?否,实际在用户目录 | `crewai traces enable/disable` 时 | trace consent | `user_data.py:21` |
| `<CWD>/.env` | `crewai create` 时由 CLI 写入;或用户自备 | API key / MODEL 等环境变量 | `create_crew.py:303` `write_env_file` |

#### 2.4 跨项目用户级目录(`appdirs.user_data_dir(Path.cwd().name, "CrewAI")`)

按平台:
- Linux:`~/.local/share/<cwd-name>/`
- macOS: `~/Library/Application Support/<cwd-name>/`
- Windows: `C:\Users\<User>\AppData\Local\<cwd-name>\`

```
<user_data_dir>/                     ← 注意:目录名 = `Path.cwd().name`,所以每个项目一个隔离目录
├── .crewai_user.json                ← trace consent、user_id
├── memory/                          ← LanceDB(unified Memory)
│   └── *.lance/                     ← LanceDB 内部
├── flow_states.db                   ← SQLite(Flow 持久化)
├── latest_kickoff_task_outputs.db   ← SQLite(latest kickoff 的 task outputs,replay 用)
├── flow_states.db-wal / -shm        ← SQLite WAL 辅助文件
└── <chromadb_dir>/                  ← ChromaDB 持久化目录(知识库)
    └── ...
```

来源:
- `lib/crewai-core/src/crewai_core/paths.py:16-22` —— `db_storage_path()` 实现
- `lancedb_storage.py:60-75` —— memory 路径
- `flow/persistence/sqlite.py:55` —— flow_states.db
- `memory/storage/kickoff_task_outputs_storage.py:26` —— kickoff task outputs
- `rag/chromadb/constants.py:11` —— knowledge 向量库

#### 2.5 全局用户级(硬编码 `Path.home()`)

```
~/.config/crewai/                    ← Linux/macOS
%USERPROFILE%\.config\crewai\        ← Windows
└── settings.json                    ← 0o600 权限,CLI 全局配置

(由 `get_writable_config_path()` 链:home → tempdir → CWD → in-memory)
```

来源:`lib/crewai-core/src/crewai_core/settings.py:11, 81-95`。

#### 2.6 Crew 类关键字段(对应"工作区配置")

```python
# lib/crewai/src/crewai/crew.py:208-368
class Crew(BaseModel):
    name: str | None = "crew"
    agents: list[BaseAgent]
    tasks: list[Task]
    process: Process = Process.sequential
    memory: bool | Memory | MemoryScope | MemorySlice = False   # ← 记忆开关/对象
    embedder: EmbedderConfig | None = None                       # ← 向量化配置
    output_log_file: bool | str | None = None                    # ← 日志文件路径
    knowledge_sources: list[BaseKnowledgeSource] | None = None   # ← knowledge 源
    chat_llm: str | BaseLLM | None = None
    # 不存在:working_directory / workspace_dir / project_root 字段
```

Task 关键字段:

```python
# lib/crewai/src/crewai/task.py:199-204
class Task(BaseModel):
    output_file: str | None = None         # ← 任务产物输出路径(可任意,带校验)
    create_directory: bool = False         # ← 父目录不存在时是否创建
    # 不存在:working_directory 字段
```

#### 2.7 Memory 的 scope 命名空间(逻辑结构,而非文件系统)

Crew 启用 `memory=True` 时,自动设置 `root_scope = "/crew/<sanitized_name>"`,所有记忆按 scope 树形组织:

```
/crew/<crew_name>/                   ← root_scope(每个 crew 一个)
├── <llm_inferred_scope>/
│   └── MemoryRecord
└── ...
```

来源:`crew.py:640-666` `create_crew_memory` + `sanitize_scope_name`(`memory/utils.py`)。

#### 2.8 表格:CrewAI 文件后端全景

| 类别 | 子类别 | 默认位置 | 是否项目级 | 是否用户级 | 跨平台代码常量 |
|---|---|---|---|---|---|
| 平台设置 | enterprise URL/token/org | `~/.config/crewai/settings.json` | ❌ | ✅(绝对 home) | `DEFAULT_CONFIG_PATH` |
| 用户数据 | trace consent | `appdirs.user_data_dir(<cwd>, "CrewAI")/.crewai_user.json` | ❌(按 cwd name) | ✅ | `_user_data_file()` |
| **统一记忆** | 短/长/实体/关系记忆(已合并) | `appdirs/.../<cwd>/memory/` | ❌(按 cwd name) | ✅ | `LanceDBStorage` 默认 |
| **Knowledge** | 向量库(ChromaDB) | `appdirs/.../<cwd>/` | ❌(按 cwd name) | ✅ | `DEFAULT_STORAGE_PATH` |
| Knowledge 源文件 | 源数据 | `<CWD>/knowledge/<filename>` | ✅ | ❌ | `KNOWLEDGE_DIRECTORY = "knowledge"` |
| Kickoff task outputs | replay 数据 | `appdirs/.../<cwd>/latest_kickoff_task_outputs.db` | ❌(按 cwd name) | ✅ | SQLite |
| Flow 状态 | checkpoint/持久化 | `appdirs/.../<cwd>/flow_states.db` | ❌(按 cwd name) | ✅ | SQLite |
| 配置文件 | agents.yaml/tasks.yaml | `src/<name>/config/`(相对 `base_directory`) | ✅ | ❌ | `@CrewBase._set_base_directory` |
| Task output | 任务产物 | `<CWD>/<output_file>`(用户指定) | ✅ | ❌ | `Task._save_file` |
| Crew log | 运行日志 | `<CWD>/logs.txt` 或用户路径 | ✅ | ❌ | `FileHandler` |
| Checkpoint | flow | `<CWD>/.checkpoints/` 或 `<CWD>/.checkpoints.db` | ✅ | ❌ | `checkpoint_cli` |
| 训练数据 | agent feedback | `<CWD>/<name>.pkl` | ✅ | ❌ | `PickleHandler` |
| 工具缓存 | 内存字典 | RAM | ❌ | ❌ | `CacheHandler._cache` |
| Tool 凭证 | API key(运行时 env) | 进程 env | ❌ | ❌ | `crewai_core.tool_credentials` |
| 文件 store | 跨 task 文件传递 | RAM(aiocache) | ❌ | ❌ | `file_store.py` |

### Q3. 工作区创建

**核心结论:CrewAI 工作区是**显式 + 隐式混合**。项目脚手架必须显式 `crewai create`,但运行时数据目录(memory、knowledge、kickoff outputs、flow states)是**首次访问时隐式创建**。**

#### 3.1 显式初始化路径(`crewai create`)

| 命令 | 生成什么 | 来源 |
|---|---|---|
| `crewai create crew <name>` | 交互式向导选 provider → classic 风格项目(`create_crew.py`) | `cli.py:131-178`,`create_crew.py:201-309` |
| `crewai create crew <name> --classic` | 强制 classic(YAML)风格 | `cli.py:155-158` |
| `crewai create crew <name> --provider openai` | 指定 LLM provider | `cli.py:147` |
| `crewai create crew <name> --skip_provider` | 跳过 provider 选择 | `cli.py:151-153` |
| `crewai create flow <name>` | Flow 项目模板(`crews/`,`tools/`,`skills/`) | `create_flow.py` |
| `crewai create flow <name> --declarative` | Declarative(YAML 风格)Flow | `cli.py:161-164` |
| `crewai tool create <handle>` | 自定义工具包脚手架(独立项目) | `cli.py:961-976` `tools/main.py:64-104` |
| `crewai skill create <name>` | (实验)skill 脚手架 | `cli.py:1004-1020` |
| `crewai template add <name>` | 从模板市场拉一个项目模板 | `cli.py:1036-1048` |

`create_crew.py:118-160` 的目录创建逻辑:

```python
folder_path.mkdir(parents=True)
(folder_path / "tests").mkdir(exist_ok=True)
(folder_path / "knowledge").mkdir(exist_ok=True)        # ← Knowledge 目录在 create 时就建好
if not parent_folder:
    (folder_path / "src" / folder_name).mkdir(parents=True)
    (folder_path / "src" / folder_name / "tools").mkdir(parents=True)
    (folder_path / "src" / folder_name / "config").mkdir(parents=True)
```

注意:`memory/`、`.crewai/`、`.checkpoints/` 这些**不在** `create` 阶段创建,是运行时隐式建。

#### 3.2 隐式创建路径(运行时首访)

| 数据 | 触发点 | 创建代码 |
|---|---|---|
| `appdirs/.../<cwd>/memory/`(LanceDB) | `Memory(model_post_init)` 或首次 `remember()` | `lancedb_storage.py:62-75` `self._path.mkdir(parents=True, exist_ok=True)` |
| `appdirs/.../<cwd>/`(ChromaDB) | `KnowledgeStorage._init_client` 或首次 `query()` | `chromadb/factory.py:18-22` `os.makedirs(persist_dir, exist_ok=True)` |
| `appdirs/.../<cwd>/latest_kickoff_task_outputs.db` | `TaskOutputStorageHandler` 实例化时 | `kickoff_task_outputs_storage.py:27-34` |
| `appdirs/.../<cwd>/flow_states.db` | `SQLiteFlowPersistence` 实例化时 | `flow/persistence/sqlite.py:55, 71-78` |
| `<CWD>/logs.txt` | `Crew(output_log_file=True).kickoff()` 首次写日志 | `file_handler.py:48-54`(append 模式) |
| `<CWD>/report.md` 等 | `Task(output_file="report.md")` 首次执行 | `task.py:1256-1270` |
| `<CWD>/.checkpoints.db` | `crewai checkpoint` 或 `@persist()` 首次 | `checkpoint_cli.py:_detect_location` |
| `<CWD>/.crewai_user.json` 副本 | `crewai traces enable/disable` | `user_data.py:21-32` |

#### 3.3 引导命令(运行/管理)

| 命令 | 作用 |
|---|---|
| `crewai run` | 自动检测 `pyproject.toml` 中的 `[tool.crewai]` type,跑对应 crew/flow/declarative |
| `crewai chat` | 进入交互式对话模式(`crew_chat.py:load_crew_and_name` 从 CWD 找 `pyproject.toml`) |
| `crewai memory [--storage-path <path>]` | 打开记忆 TUI 浏览器(只读) |
| `crewai reset_memories -m / -kn / -akn / -k / -a` | 按类型重置(memory/knowledge/agent_knowledge/kickoff_outputs/all) |
| `crewai log_tasks_outputs` | 读取 `latest_kickoff_task_outputs.db` |
| `crewai checkpoint list/info/resume/diff/prune` | 检视/操作 `.checkpoints` |
| `crewai train -n 5 -f <pkl>` | 训练(pickle 存 CWD) |
| `crewai test -n 3 -m <model>` | 测试 |
| `crewai replay -t <task_id>` | 从指定 task 重放 |
| `crewai install` | `uv add` 安装依赖 |
| `crewai update` | 升级 `pyproject.toml` 到 uv |
| `crewai env view` | 列出 tracing 相关 env 与 `.env` 状态 |

#### 3.4 没有"init"概念

CrewAI **没有** `crewai init`(像 `git init` 那种在已有目录里就地初始化的命令)。`crewai create` 必须指定 `<name>`,且:
- `classic` 模式 → 必须在空目录(已存在会 `shutil.rmtree`)
- `json` 模式 → 同上
- `--parent_folder <dir>` → 把项目作为子目录加到 flow 项目里(`create_crew.py:107-108, 122-124`)

**注意**:从已存在目录运行 `crewai run` 时,CLI 通过 `pyproject.toml` 检测 `type` 字段,加载对应的 `crew.py` / `crew.jsonc` / flow 定义 —— 不需要"初始化"步骤,而是基于约定。

---

## 3. 关键代码片段

### 3.1 `db_storage_path()` —— CrewAI"工作区"的核心路径解析

```python
# lib/crewai-core/src/crewai_core/paths.py:8-22
import os
from pathlib import Path
import appdirs


def get_project_directory_name() -> str:
    """Return the current project directory name (or ``CREWAI_STORAGE_DIR``)."""
    return os.environ.get("CREWAI_STORAGE_DIR", Path.cwd().name)


def db_storage_path() -> str:
    """Return the path for SQLite database / app-data storage.

    Creates the directory if it does not exist.
    """
    app_name = get_project_directory_name()
    app_author = "CrewAI"
    data_dir = Path(appdirs.user_data_dir(app_name, app_author))
    data_dir.mkdir(parents=True, exist_ok=True)
    return str(data_dir)
```

→ **关键设计哲学**:用 `Path.cwd().name` 当 `app_name`,所以**每个项目一个隔离目录**,但都放在用户级 `appdirs` 路径下。设 `CREWAI_STORAGE_DIR` 可整体覆写。

### 3.2 LanceDB memory 路径解析(支持 `CREWAI_STORAGE_DIR` env 覆写)

```python
# lib/crewai/src/crewai/memory/storage/lancedb_storage.py:54-75
def __init__(
    self,
    path: str | Path | None = None,
    table_name: str = "memories",
    vector_dim: int | None = None,
    compact_every: int = 100,
) -> None:
    if path is None:
        storage_dir = os.environ.get("CREWAI_STORAGE_DIR")
        if storage_dir:
            path = Path(storage_dir) / "memory"
        else:
            from crewai_core.paths import db_storage_path
            path = Path(db_storage_path()) / "memory"
    self._path = Path(path)
    self._path.mkdir(parents=True, exist_ok=True)  # ← 隐式创建
    self._db = lancedb.connect(str(self._path))
```

### 3.3 `@CrewBase` 自动绑定 `base_directory`

```python
# lib/crewai/src/crewai/project/crew_base.py:135-144
def _set_base_directory(cls: type[CrewClass]) -> None:
    try:
        cls.base_directory = Path(inspect.getfile(cls)).parent
    except (TypeError, OSError):
        cls.base_directory = Path.cwd()
```

```python
# lib/crewai/src/crewai/project/crew_base.py:339-355
def _load_config(
    self: CrewInstance, config_path: str | None, config_type: Literal["agent", "task"]
) -> dict[str, Any]:
    if isinstance(config_path, str):
        full_path = self.base_directory / config_path   # ← 相对 base_directory 解析
        try:
            return self.load_yaml(full_path)
        except FileNotFoundError:
            ...
```

→ 经典项目里 `base_directory = src/<name>/`,所以 `config/agents.yaml` 解析为 `src/<name>/config/agents.yaml`。

### 3.4 Knowledge source 路径解析(注意:与 `base_directory` 不一致!)

```python
# lib/crewai/src/crewai/knowledge/source/base_file_knowledge_source.py:74-79
def convert_to_path(self, path: Path | str) -> Path:
    """Convert a path to a Path object."""
    return Path(KNOWLEDGE_DIRECTORY + "/" + path) if isinstance(path, str) else path
```

```python
# lib/crewai-core/src/crewai_core/constants.py:11
KNOWLEDGE_DIRECTORY: Final[str] = "knowledge"
```

→ `TextFileKnowledgeSource(file_path="user_preference.txt")` 解析为 `Path("knowledge/user_preference.txt")` —— **CWD 相对,不是 `base_directory` 相对**。这是经典项目里 `src/<name>/knowledge/` 与 `CWD/knowledge/` 的潜在冲突点(但因为 `crewai run` 在项目根跑,实际一致)。

### 3.5 `Crew.memory=True` 触发统一记忆初始化 + scope 命名

```python
# lib/crewai/src/crewai/crew.py:640-672
@model_validator(mode="after")
def create_crew_memory(self) -> Crew:
    from crewai.memory.utils import sanitize_scope_name
    crew_name = sanitize_scope_name(self.name or "crew")
    crew_root_scope = f"/crew/{crew_name}"

    if self.memory is True:
        from crewai.memory.unified_memory import Memory
        memory_kwargs: dict[str, Any] = {
            "embedder": embedder,
            "root_scope": crew_root_scope,    # ← 按 crew 命名
        }
        ...
        self._memory = Memory(**memory_kwargs)
```

### 3.6 `Task.output_file` 落盘(带 `..` / shell 字符校验)

```python
# lib/crewai/src/crewai/task.py:1233-1270
def _save_file(self, result: dict[str, Any] | str | Any) -> None:
    if self.output_file is None:
        raise ValueError("output_file is not set.")
    try:
        resolved_path = Path(self.output_file).expanduser().resolve()
        directory = resolved_path.parent
        if self.create_directory and not directory.exists():
            directory.mkdir(parents=True, exist_ok=True)
        elif not self.create_directory and not directory.exists():
            raise RuntimeError(...)
        with resolved_path.open("w", encoding="utf-8") as file:
            ...
```

### 3.7 `FileHandler.output_log_file` 默认 CWD

```python
# lib/crewai/src/crewai/utilities/file_handler.py:48-59
def _initialize_path(self, file_path: bool | str) -> None:
    if file_path is True:
        self._path = os.path.join(os.curdir, "logs.txt")     # ← CWD/logs.txt
    elif isinstance(file_path, str):
        if file_path.endswith((".json", ".txt")):
            self._path = file_path
        else:
            self._path = file_path + ".txt"
    else:
        raise ValueError("file_path must be a string or boolean.")
```

### 3.8 `get_crews()` —— 从 CWD 扫描 `crew.py`

```python
# lib/crewai/src/crewai/utilities/project_utils.py:55-100
def get_crews(crew_path: str = "crew.py", require: bool = False) -> list[Crew]:
    crew_instances = []
    try:
        current_dir = os.getcwd()
        if current_dir not in sys.path:
            sys.path.insert(0, current_dir)
        src_dir = os.path.join(current_dir, "src")
        if os.path.isdir(src_dir) and src_dir not in sys.path:
            sys.path.insert(0, src_dir)
        search_paths = [".", "src"] if os.path.isdir("src") else ["."]
        for search_path in search_paths:
            for root, _, files in os.walk(search_path):
                if crew_path in files and "cli/templates" not in root:
                    ...
```

→ `crewai run` 通过这个发现 `crew.py` / `src/<name>/crew.py`,不需要显式注册。

### 3.9 `create_crew.py` 显式脚手架(YAML 风格)

```python
# lib/cli/src/crewai_cli/create_crew.py:201-309
def create_crew(name, provider=None, skip_provider=False, parent_folder=None):
    folder_path, folder_name, class_name = create_folder_structure(name, parent_folder)
    # ... 交互式 provider 选择 ...
    root_template_files = (
        [".gitignore", "pyproject.toml", "README.md", "knowledge/user_preference.txt"]
        if not parent_folder else []
    )
    tools_template_files = ["tools/custom_tool.py", "tools/__init__.py"]
    config_template_files = ["config/agents.yaml", "config/tasks.yaml"]
    src_template_files = (
        ["__init__.py", "main.py", "crew.py"] if not parent_folder else ["crew.py"]
    )
    # ... 复制模板到目标目录 ...
    if not parent_folder:
        initialize_if_git_available(folder_path)
    click.secho(f"Crew {name} created successfully!", fg="green", bold=True)
```

---

## 4. 与 Onion Agent 设计的关联

### 4.1 CrewAI 的可借鉴之处

1. **`base_directory` 自动绑定到源码所在目录**(`@CrewBase`)
   - 让 `agents.yaml` / `tasks.yaml` 这种声明式配置与代码同包,降低"配置文件在哪找"的认知负担。
   - **Onion Agent 启发**:如果 Onion 也用装饰器定义 agent/task,`@OnionAgent` 可自动绑定 `session.json` 所在目录为 base。

2. **`crewai create` 的 `name → folder` 命名规则**
   - `name.replace(' ', '_').replace('-', '_').lower()` + `re.sub(r'[^a-zA-Z0-9_]', '')`(Python module 合法)
   - **Onion Agent 启发**:CLI `onion create <name>` 沿用同一套规则,直接 `uv tool install` 风格。

3. **`crewai reset_memories` 按类型细分**
   - `-m` (memory) / `-kn` (knowledge) / `-akn` (agent knowledge) / `-k` (kickoff outputs) / `-a` (all)
   - **Onion Agent 启发**:`onion reset session` / `onion reset context` / `onion reset cache` / `onion reset all`,按生命周期分层管理。

4. **Memory scope 命名空间树**
   - `/crew/<crew-name>/<inferred-scope>/<record>`
   - LLM 自动推断 scope + importance + categories,`root_scope` 由 crew 名派生
   - **Onion Agent 启发**:Onion 的 session.json 累加器如果用类似 scope 树,能更好隔离多项目(避免 `/session/<project>/<topic>` 冲突)。

5. **三层记忆分类型**
   - 旧版:short-term / long-term / entity / relationship(分四种)
   - 新版(unified Memory):**合并为一种,靠 scope + metadata 区分** + LLM 自动提取 + 重要度打分 + consolidation 去重
   - **Onion Agent 启发**:如果 Onion 也有"上下文历史"概念,统一存储(一种文件 / 一种数据库)比四套独立存储更易管理。

6. **`crewai memory --storage-path` TUI 浏览器**
   - 即使路径不可配置到 CLI 全局,也能交互式查看 scope 树、recall 查询
   - **Onion Agent 启发**:`onion inspect <session>` 提供 session.json 的可视化检查 / 时间线 / 折叠展开。

7. **`output_file` 校验策略**
   - 禁止 `..` / `~` / `$` / `| > < & ;`(路径穿越 + shell 注入)
   - `create_directory` 显式开关
   - **Onion Agent 启发**:任何让 LLM 写文件的操作都要走类似校验,即使 Onion 自身不写文件,task 产物落到 Onion 管辖目录也该校验。

8. **LanceDB 默认存储 + Qdrant 插件**
   - `storage="lancedb"` / `storage="qdrant-edge"` / `storage=<path>` / 自定义 backend
   - **Onion Agent 启发**:如果未来 Onion 需要 RAG,用 LanceDB 默认 + 可插拔 Qdrant 是个好起点(本地优先,需要时换云端)。

### 4.2 CrewAI 的可规避之处

1. **路径分散在 5+ 个位置** —— 用户级(绝对 home)、跨项目用户级(按 cwd 命名)、CWD 派生、`base_directory` 派生、用户显式 —— 排查"我的数据去哪了"非常困难。
   - **Onion 改进**:**统一一个 `OnionAgent` 工作区根目录**,所有派生路径(`memory/`、`knowledge/`、`logs/`、`traces/`、`artifacts/`)都从它计算,可用 `onion root` 打印当前解析。

2. **`appdirs.user_data_dir(Path.cwd().name, "CrewAI")` 的 cwd-name 命名空间** —— 项目改名 → 记忆丢失。`mv my_project my_project_v2` 之后 LLM 完全"失忆",用户毫无感知。
   - **Onion 改进**:项目根放一个 `onion.lock` 或 `pyproject.toml [tool.onion] workspace_id = "..."`,workspace_id 与目录名解耦。

3. **`base_directory` 与 `KNOWLEDGE_DIRECTORY` 不一致** —— YAML 配置走 `base_directory`(源码目录),knowledge 走 `KNOWLEDGE_DIRECTORY = "knowledge"`(CWD 目录)。如果用 `python src/<name>/main.py` 在非项目根跑,knowledge 解析就会 404。
   - **Onion 改进**:所有相对路径都从**单一 root**(工作区根)解析,避免双重基准。

4. **没有"工作区"显式概念** —— `Crew` 类没有 `workspace` / `project_dir` / `working_dir` 字段,只有零散的 `output_log_file` / `output_file` / `trained_agents_file`。
   - **Onion 改进**:`OnionAgent(workspace=Path("./my_agent"))` 作为顶级配置,所有路径派生从它出。

5. **`crewai create` 不可在已有目录里 init** —— 必须指定 name 且目录不能存在(已存在会 rmtree 覆盖)
   - **Onion 改进**:`onion init` 支持在已有空目录(或已有 pyproject 目录)就地初始化。

6. **三个 gitignore 模板几乎相同** —— `classic` 与 `json` 风格只差一行 `report.md` 忽略。重复。
   - **Onion 改进**:统一一份 .gitignore 模板,不分风格。

7. **`output_log_file=True` 写 `CWD/logs.txt`** —— 没有 `.crewai/logs/` 这种结构化组织。日志/产物/记忆混在 CWD 顶层,容易污染项目。
   - **Onion 改进**:`<workspace>/.onion/logs/<date>.log`,带日期轮转。

8. **CLI help 描述与实际行为不一致** —— `crewai memory --storage-path` 的 help 写 "uses ./.crewai/memory",但代码默认是 `appdirs.user_data_dir(Path.cwd().name, "CrewAI")/memory`(`cli.py:368` vs `lancedb_storage.py:68-74`)。
   - **Onion 改进**:`onion --help` 与代码逻辑必须用同一份数据驱动生成。

9. **`reset_memories` 没有 dry-run** —— 一删就全删,没有"先看哪些会被删"的预览。
   - **Onion 改进**:`onion reset session --dry-run` 列出受影响的范围,二次确认。

10. **Flow 与 Crew 的存储耦合** —— `flow_states.db` 与 `latest_kickoff_task_outputs.db` 都用 `db_storage_path()`,Flow 与 Crew 状态混在一个目录,容易冲突。
    - **Onion 改进**:Flow / Crew / Skill 各自独立子目录。

### 4.3 一句话总结

> **CrewAI 的工作区是"约定大于配置"的散点式设计 —— 用户级、跨项目用户级、CWD 派生、源码目录派生 4 类路径交织,适合"快速原型 + 跨项目共享记忆",但不适合"信创合规 + 数据隔离"场景。Onion Agent 应当采用单一显式 `workspace` 根 + 派生子目录,所有路径从这一个根解析,避开 cwd 命名空间陷阱。**

---

## 5. 不确定 / 未找到

1. **CLI `--storage-path` 文档与代码不一致**:`crewai memory --storage-path` 的 help 说 "uses ./.crewai/memory",但 `LanceDBStorage.__init__(path=None)` 实际走 `appdirs.user_data_dir(Path.cwd().name, "CrewAI")/memory`。`cli.py:368-371` 的 help 字符串与 `lancedb_storage.py:60-75` 实际行为矛盾。需要在最新版本中确认 help 是否已更新。

2. **`crewai init` 不存在**:用户描述中提到 "crewai create / crewai init",但实际只有 `crewai create <type> <name>` 一种方式。`crewai init` 在 `cli.py` 的 click group 中未注册。

3. **Lite Agent 的工作区行为未深查**:`lib/crewai/src/crewai/lite_agent.py` 是更轻量级的 agent 抽象(无 Crew 包裹),其 memory / knowledge / storage 行为与 Crew 类可能有差异,本次未深入。

4. **A2A (Agent-to-Agent) 协议的存储**:`lib/crewai/src/crewai/a2a/` 目录存在,但未调研其持久化是否引入新的文件系统后端。

5. **多平台路径示例**:`appdirs.user_data_dir()` 在 Windows / macOS / Linux 的实际路径未在文档中明确说明,本报告基于 `appdirs` 库的官方约定推断。

6. **Flow `@persist` 装饰器的实际使用率**:本次只看到 `SQLiteFlowPersistence` 默认实现,但 Flow 模板里 `lib/cli/src/crewai_cli/templates/declarative_flow/AGENTS.md:336` 提到 "checkpoint optional",说明 Flow 也有 checkpoint 机制,是否与 `crewai checkpoint` 命令同源,需进一步确认。

7. **CrewAI 商业版(AMP)对工作区的影响**:`enterprise/main.py`、`deploy/main.py`、`plus_api.py` 等模块涉及 SaaS 集成,可能引入云端工作区概念,本次未深入。

8. **`trained_agents_data.pkl` 是否会上传或跨项目共享**:`PickleHandler` 只存 CWD,但 `crewai train` 与 `crewai run` 之间通过 `CREWAI_TRAINED_AGENTS_FILE` env 传递路径,机制清晰但行为未实测。
