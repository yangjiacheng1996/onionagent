# AutoGen — 工作区(File Backend)调研报告

> 调研对象:`microsoft/autogen` (Python monorepo,`pyautogen` 旧名已废弃,迁移到 `autogen-core` / `autogen-agentchat` / `autogen-ext` / `autogen-studio` 多包结构)
> 调研时间:基于当前 `main` 分支快照(`python/packages/`)
> 关注点:AutoGen 的工作区(cache / workdir / state / db / 共享文件系统)如何配置、如何落盘、有没有 init 流程

---

## 0. 智能体一句话定位

微软系、对话驱动的多 Agent 编排框架,以"消息流 + Component 配置 + Code Executor"为内核,把"代码生成 → 执行 → 验证"做成 Agent Loop 闭环;支持 `RoundRobinGroupChat` / `SelectorGroupChat` / `MagenticOneGroupChat` / `Swarm` 等拓扑,内置本地 / Docker / Jupyter 三种代码执行后端,Web UI 用 AutoGen Studio。

---

## 1. 调研依据

| 文件 | 角色 |
|---|---|
| `python/packages/autogen-ext/src/autogen_ext/code_executors/local/__init__.py` | `LocalCommandLineCodeExecutor` 主类(代码执行工作区) |
| `python/packages/autogen-ext/src/autogen_ext/code_executors/docker/_docker_code_executor.py` | `DockerCommandLineCodeExecutor` 主类(容器化代码执行) |
| `python/packages/autogen-ext/src/autogen_ext/code_executors/jupyter/_jupyter_code_executor.py` | Jupyter 代码执行后端(临时目录) |
| `python/packages/autogen-ext/src/autogen_ext/cache_store/diskcache.py` | `DiskCacheStore` — LLM response 缓存落盘 |
| `python/packages/autogen-ext/src/autogen_ext/cache_store/redis.py` | `RedisCacheStore` — 远程缓存 |
| `python/packages/autogen-ext/src/autogen_ext/memory/chromadb/_chromadb.py` | `ChromaDBVectorMemory` — 默认持久化到 `~/.chromadb_autogen` |
| `python/packages/autogen-ext/src/autogen_ext/memory/chromadb/_chroma_configs.py` | `PersistentChromaDBVectorMemoryConfig` — 持久化路径 |
| `python/packages/autogen-ext/src/autogen_ext/memory/canvas/_text_canvas.py` | `TextCanvas` — 纯内存文件画布,无默认落盘 |
| `python/packages/autogen-ext/src/autogen_ext/agents/file_surfer/_markdown_file_browser.py` | `MarkdownFileBrowser` — 沙箱化文件浏览,基于 `base_path` |
| `python/packages/autogen-ext/src/autogen_ext/agents/file_surfer/_file_surfer.py` | `FileSurfer` Agent — `base_path` 默认 `os.getcwd()` |
| `python/packages/autogen-ext/src/autogen_ext/agents/web_surfer/_multimodal_web_surfer.py` | `MultimodalWebSurfer` — `downloads_folder` 可选 |
| `python/packages/autogen-ext/src/autogen_ext/teams/magentic_one.py` | `MagenticOne` 团队工厂(无内置工作区) |
| `python/packages/autogen-ext/src/autogen_ext/models/cache/_chat_completion_cache.py` | `ChatCompletionCache` — LLM 调用缓存(可挂 DiskCache) |
| `python/packages/magentic-one-cli/src/magentic_one_cli/_m1.py` | Magentic-One CLI — `config.yaml` 跟随当前目录 |
| `python/packages/autogen-studio/autogenstudio/cli.py` | AutoGen Studio CLI — `autogenstudio ui --appdir <path>` |
| `python/packages/autogen-studio/autogenstudio/web/config.py` | Studio `Settings` — `AUTOGENSTUDIO_*` 环境变量前缀 |
| `python/packages/autogen-studio/autogenstudio/web/initialization.py` | `AppInitializer` — **自动建目录**(无 init 命令) |
| `python/packages/autogen-studio/autogenstudio/web/app.py` | FastAPI 入口 — 启动时隐式初始化 |
| `python/packages/autogen-studio/autogenstudio/database/db_manager.py` | `DatabaseManager` — Alembic 迁移 + SQLModel |
| `python/packages/autogen-studio/autogenstudio/gallery/builder.py` | Gallery 默认配置 — `work_dir=".coding"` 等 |
| `python/packages/autogen-studio/.gitignore` | 目录黑名单 — `.cache/`、`coding/`、`workdir/`、`files/user/` |

---

## 2. 三个核心问题的回答

### Q1. 工作区路径如何确定?

**结论:AutoGen 没有统一的"全局工作区"概念;每个子系统各自有一套"用户属主 / 可配置 / 临时"三态路径,没有显式的 init 流程。**

#### 1.1 路径决定方式汇总表

| 子系统 | 路径语义 | 默认值 | 可配置方式 | 证据 |
|---|---|---|---|---|
| 代码执行 (`LocalCommandLineCodeExecutor`) | 写入脚本 + `cwd` | `tempfile.TemporaryDirectory()`(用户未传时) | `__init__(work_dir=...)`;Pydantic `LocalCommandLineCodeExecutorConfig.work_dir` | `local/__init__.py:40` 配置字段;`:175-178` 解析逻辑;`:248-254` 懒创建 `temp_dir` |
| 代码执行 (`DockerCommandLineCodeExecutor`) | 主机侧写脚本,挂到容器 `/workspace` | `tempfile.TemporaryDirectory()`(用户未传时);容器内 `working_dir="/workspace"` | `__init__(work_dir=..., bind_dir=...)`;`extra_volumes` 额外挂载 | `docker/_docker_code_executor.py:164-200` 解析;`:546` 容器 `volumes` 挂载;`:547` `working_dir="/workspace"` |
| 代码执行 (`JupyterCodeExecutor`) | 临时目录(只放 output) | `tempfile.mkdtemp()` | `__init__(output_dir=...)` | `_jupyter_code_executor.py:148` |
| LLM 响应缓存 (`DiskCacheStore` / `ChatCompletionCache`) | 任意目录(用户给什么用什么) | 无(必须显式传 `diskcache.Cache`) | `DiskCacheStoreConfig.directory` | `cache_store/diskcache.py:13` `directory: str` |
| 长期记忆 (`ChromaDBVectorMemory` 持久化) | 显式持久化目录 | `os.path.join(Path.home(), ".chromadb_autogen")`(docstring 示例) / `"./chroma_db"`(config 默认) | `PersistentChromaDBVectorMemoryConfig.persistence_path` | `chromadb/_chromadb.py:93,103,114`;`chromadb/_chroma_configs.py:120` `persistence_path: str = "./chroma_db"` |
| AutoGen Studio 数据根 | App-wide 全局工作区 | `Path.home() / ".autogenstudio"` | 环境变量 `AUTOGENSTUDIO_APPDIR` 或 `autogenstudio ui --appdir <path>` | `web/initialization.py:41-45`;`cli.py:32,58-59` |
| AutoGen Studio 数据库 | SQLite/PG | `sqlite:///<app_root>/autogen04203.db` | 环境变量 `AUTOGENSTUDIO_DATABASE_URI` 或 `--database-uri` | `web/config.py:7`;`web/initialization.py:47-52` |
| AutoGen Studio 用户文件 | 上传/产出文件 | `<app_root>/files/user/` | 跟随 `AUTOGENSTUDIO_APPDIR` | `web/initialization.py:58-59` |
| AutoGen Studio 配置目录 | Gallery/团队 JSON 模板 | `<app_root>/configs/` | 跟随 `AUTOGENSTUDIO_APPDIR` | `web/config.py:11`;`web/initialization.py:61` |
| FileSurfer Agent | 文件浏览沙箱根 | `os.getcwd()` | `FileSurfer(base_path=...)` | `file_surfer/_file_surfer.py:79` |
| MultimodalWebSurfer | 浏览器下载目录 | `None`(不下落盘) | `MultimodalWebSurfer(downloads_folder=...)` | `web_surfer/_multimodal_web_surfer.py:75,213,245` |
| Magentic-One CLI | 配置 + 任务 | CWD 找 `config.yaml`;`work_dir=os.getcwd()` | `--config <yaml>` CLI flag | `magentic-one-cli/_m1.py:15,77,113` |
| AGBench (benchmark harness) | 每个 scenario 一个工作目录 | 临时目录 | CLI 传入 `work_dir`;`HOST_WORKSPACE` 环境变量 | `agbench/run_cmd.py:379,483,581,612,614,630` |
| `pyautogen` 旧版 `OAI_CONFIG_LIST` | API key 配置 | CWD 下文件 | 环境变量 `OAI_CONFIG_LIST` 或当前目录文件 | `agbench/README.md:35,40,43` |

#### 1.2 关键发现:AutoGen 是"多工作区、零统一"

- **没有 `~/.autogen/` 风格的用户属主全局目录**(只有 AutoGen Studio 的 `~/.autogenstudio/` 和 ChromaDB 记忆的 `~/.chromadb_autogen/`,前者是 Web 产品,后者是文档示例,都不是核心运行时必须的)。
- **每个 Executable 子系统都是"参数优先,临时目录兜底"**:`work_dir=None` 时一律 `tempfile.TemporaryDirectory()`,`stop()` 时清理 — 这是显式设计(`local/__init__.py:248-254`,`docker/_docker_code_executor.py:502-505`)。
- **没有 `AUTOGEN_WORKSPACE` / `AUTOGEN_HOME` 这种全局环境变量**(有 `AUTOGENSTUDIO_*` 四个,但只服务于 Studio web app,不影响 `autogen-core`/`autogen-agentchat`/`autogen-ext` 的纯 Python 库调用)。
- **路径优先级(代码侧)**:`用户传值` > `Pydantic Config 字段` > `tempfile.TemporaryDirectory()`。环境变量在底层 Core/Ext 库中**不起作用**,只有 Studio 这种 Web 外壳才读环境变量。

#### 1.3 路径硬编码 vs 可配置 — 一句话总结

> **所有"可配置"都是"参数可配置",不是"环境变量可配置"。** 环境变量只存在于 Studio 的 `AUTOGENSTUDIO_*` 家族,且唯一控制的是 app_root(及其下推到 `files/`, `configs/`, 数据库路径)。
> 
> **CWD(当前目录)被显式视为 deprecated 行为**:`LocalCommandLineCodeExecutor.__init__` 在 `work_dir == Path.cwd()` 时会发 `DeprecationWarning`(`local/__init__.py:178-183`)。

---

### Q2. 工作区目录结构

#### 2.1 AutoGen Studio(最完整的"工作区")

参考 `web/initialization.py:55-67`,App 启动时自动创建:

```
<app_root>                              # 默认 ~/.autogenstudio ; AUTOGENSTUDIO_APPDIR 可覆盖
├── .env                                # 可选,启动时 load_dotenv() 加载
├── autogen04203.db                     # SQLite 默认数据库,文件名硬编码; 写死 ./autogen04203.db 然后 str.replace 替换前缀
├── database.sqlite                     # 次要/旧版 SQLite,可能在 dev mode
├── database/
│   ├── alembic.ini                     # Alembic 配置(被 .gitignore)
│   ├── alembic/                        # Alembic 迁移目录(被 .gitignore)
│   └── versions/
├── files/                              # 静态文件根
│   └── user/                           # 用户上传/产出的文件,被 FastAPI StaticFiles 挂到 /files
│       └── ...
├── configs/                            # 团队配置 JSON 模板目录,启动时 import_teams_from_directory 导入
│   └── *.json                          # Gallery JSON;默认从仓库 autogenstudio/gallery/ 复制
├── ui/                                 # 前端 SPA 静态资源(随包)
├── workdir/                            # 旧版子目录(被 .gitignore,现状未用)
└── skills/user/                        # 用户自定义技能(被 .gitignore,现状未用)
```

**数据库表结构**:`autogenstudio/datamodel/db.py` 定义 `BaseDBModel` 体系(SQLModel),包括 Team / Session / Run / Message / User / Gallery / Setting / Validation 等 8 个表(`__table_args__ = {"sqlite_autoincrement": True}` 用于 SQLite 序列自增)。

#### 2.2 单 Agent / 库的"工作区"

**A. `LocalCommandLineCodeExecutor` 典型目录** (`work_dir=Path("coding")` 例):

```
coding/
├── .venv/                              # 可选,venv_builder 创建,自包含 Python 环境
├── functions.py                        # 自动生成的辅助函数模块,functions_module 字段控制
├── tmp_code_<sha256>.py                # 每个代码块一个临时脚本
├── tmp_code_<sha256>.sh                # bash 代码块
└── ...                                 # 用户代码产出的 artifact(无清理)
```

> `cleanup_temp_files=True` 会在执行后 unlink `tmp_code_*.py/sh`(`local/__init__.py:470-477`),但用户代码写入的副产物**不清理**。

**B. `DockerCommandLineCodeExecutor` 典型目录** (`work_dir=Path("coding")` 例):

```
coding/                                 # 主机侧,与 work_dir 同名
├── (同 LocalCommandLineCodeExecutor 的内容,但文件实际写到容器 /workspace 下)
└── ...

[Container]
/workspace/                             # bind_dir.resolve() 挂到这里,默认 work_dir
/venv 或 /usr/local/lib/...              # 容器内 Python 环境,init_command 可定制
```

> **关键设计**:`work_dir`(代码写出的位置)和 `bind_dir`(挂载到容器的位置)**可以分离** — 用户可以让 Agent 写脚本到 `/secure-area/`,只把 `/readonly-share/` 挂到容器(`docker/_docker_code_executor.py:208-214`)。

**C. ChromaDB Memory 持久化** (`PersistentChromaDBVectorMemoryConfig`):

```
<persistence_path>                      # 默认 ./chroma_db ;示例 ~/.chromadb_autogen
├── chroma.sqlite3                      # 元数据
├── <collection-uuid>/                  # 每个 collection 一个目录
│   ├── data_level0.bin                 # 向量数据
│   ├── header.bin
│   ├── length.bin
│   ├── link_lists.bin                  # HNSW 索引
│   └── ...
```

> 路径是**纯字符串透传**给 `chromadb.PersistentClient(path=...)`,没有任何 AutoGen 自己的封装。

**D. LLM 响应缓存 (`DiskCacheStore`)**:

```
<directory>                             # 用户传,无默认
├── cache.db                            # SQLite 索引
├── 00/                                 # 哈希分桶
│   └── <key>.cache
├── 01/
└── ...
```

> `diskcache.Cache(directory)` 标准 layout,AutoGen 只包了一层 `get/set` 泛型接口(`cache_store/diskcache.py:38-46`)。

**E. MultimodalWebSurfer 下载目录**:

```
<downloads_folder>                      # 默认 None(不下载)
└── <suggested_filename>                # 浏览器原文件名
```

#### 2.3 顶层目录树(本次 clone 实际布局)

```
python/
├── packages/
│   ├── agbench/                        # AutoGenBench: 评估 harness
│   ├── autogen-agentchat/              # 高级 Agent API(AssistantAgent, GroupChat, MagenticOneGroupChat)
│   ├── autogen-core/                   # 运行时 + Component 抽象(CacheStore, Memory, CodeExecutor 接口)
│   ├── autogen-ext/                    # 扩展实现(OpenAI/Azure/Anthropic/Redis, ChromaDB, code_executors)
│   ├── autogen-magentic-one/           # 空 package(只有 README,实际代码在 autogen-ext)
│   ├── autogen-studio/                 # Web UI(FastAPI + React frontend + SQLite)
│   ├── autogen-test-utils/
│   ├── component-schema-gen/           # JSON Schema 生成器(给 Studio 序列化用)
│   ├── magentic-one-cli/               # Magentic-One CLI
│   └── pyautogen/                      # 旧 meta-package(只导出空 __init__,引导到新包)
├── docs/
├── samples/                            # 示例 notebook
├── templates/new-package/              # cookiecutter 模板
├── shared_tasks.toml
└── pyproject.toml                      # uv workspace 根
```

> **关键观察**:AutoGen 的 monorepo **没有"全局配置/工作区目录"模式**。每个子包都靠 Component 配置对象 + 各自的环境变量边界来管理自己的状态,共享态只通过 FastAPI 进程内的全局单例(`deps.py:138-140` 的 `_db_manager` 等)实现。

#### 2.4 多 Agent 协作的"共享工作区"是怎么实现的?

**没有"原生多 Agent 共享工作区"**。三种变通:

1. **同一个 `CodeExecutor` 实例传给多个 Agent** — `CodeExecutorAgent` 可以共享一个 `LocalCommandLineCodeExecutor` 实例,所以 `work_dir` 自然就是共享空间(`tests/test_group_chat_nested.py:52,103,274,330`)。
2. **MCP Filesystem Workbench** — `gallery/builder.py:561-570` 的默认 Gallery 提供 `@modelcontextprotocol/server-filesystem`,把 `~` 和 `tempfile.gettempdir()` 作为允许访问的路径,多 Agent 通过同一个 workbench 实例共享。
3. **`bind_dir` + `extra_volumes`** — Docker Executor 允许多个容器共享主机的同一目录(`docker/_docker_code_executor.py:546`)。

---

### Q3. 工作区创建(init 显式 vs 隐式)

**结论:AutoGen 是典型的"零 init 命令,纯隐式懒创建"模式 — 启动即建、首次访问即建。**

#### 3.1 是否有 `autogen init` 命令?

**没有**。`autogenstudio` CLI 只有 4 个 subcommand(`cli.py`):

| subcommand | 证据 | 作用 |
|---|---|---|
| `ui` | `cli.py:25-83` | 启动 Web UI,`--appdir` `--database-uri` `--auth-config` `--upgrade-database` |
| `serve` | `cli.py:87-121` | 服务化某个团队 JSON |
| `version` | `cli.py:124-129` | 打印版本 |
| `lite` | `cli.py:134-170` | 轻量模式(内存数据库) |

`agbench` CLI 同样没有 init,只 `run` 和 lint。

#### 3.2 隐式创建的"路径"

| 子系统 | 触发点 | 实际动作 | 证据 |
|---|---|---|---|
| AutoGen Studio 全局目录 | **第一次 `autogenstudio ui`** | `AppInitializer.__init__` → `_create_directories()` → `app_root.mkdir(parents=True, exist_ok=True)` | `web/initialization.py:65-67` |
| AutoGen Studio 数据库 | `AppInitializer` → `lifespan` → `init_managers` → `DatabaseManager.initialize_database` | 调 SQLAlchemy `metadata.create_all` + Alembic 初始化;**没有表则全量创建** | `web/app.py:34`;`database/db_manager.py:74-86`;`database/schema_manager.py:47` |
| AutoGen Studio 默认 teams | `init_managers` → `import_teams_from_directory(config_dir, ...)` | 从 `<app_root>/configs/*.json` 导入到 SQLite | `web/deps.py:156`;`database/db_manager.py:312-356` |
| `~/.autogenstudio/temp_env_vars.env` | 每次 `autogenstudio ui/lite` | CLI `get_env_file_path()` 主动 `os.makedirs(exist_ok=True)` | `cli.py:18-23`;`lite/studio.py:132-135` |
| LocalCodeExecutor `work_dir` | 用户传 `work_dir=...` 时 | `self._work_dir.mkdir(exist_ok=True)`(只在构造时) | `local/__init__.py:178-180` |
| LocalCodeExecutor `temp_dir` | `work_dir` property 第一次被访问 | `tempfile.TemporaryDirectory()` 懒创建;`start()` 时也建 | `local/__init__.py:248-254`;`:482-490` |
| DockerCodeExecutor `temp_dir` | `start()` 第一次 | `tempfile.TemporaryDirectory()` + `mkdir(exist_ok=True)` | `docker/_docker_code_executor.py:502-505` |
| ChromaDB Memory | 第一次 `add()` / `query()` → `_ensure_client` | 调 `chromadb.PersistentClient(path=...)`,ChromaDB 自己 `mkdir` | `chromadb/_chromadb.py:248-251` |
| FileSurfer `base_path` | 构造时 | **不创建**;不存在的路径会 `open_path` 失败 | `file_surfer/_markdown_file_browser.py:39` |
| MultimodalWebSurfer `downloads_folder` | 构造时 | **不创建**;首次下载时 `os.path.join` 后由 Playwright 写入 | `web_surfer/_multimodal_web_surfer.py:774-775` |
| AGBench scenario | `run` 子命令 | 复制 scenario 目录到临时目录,然后 `os.chdir(work_dir)` | `agbench/run_cmd.py:395` |

#### 3.3 启动时序图(Studio 模式)

```
$ autogenstudio ui
    ↓
typer main → ui() command  (cli.py:25)
    ↓
写 ~/.autogenstudio/temp_env_vars.env  (cli.py:18-23, 隐式)
    ↓
uvicorn.run("autogenstudio.web.app:app", env_file=...)  (cli.py:75-83)
    ↓
import web.app  (web/app.py:22)
    ↓
AppInitializer(settings, app_file_path)  (web/initialization.py:26-67, 隐式)
    ├─ _get_app_root()  → 读 AUTOGENSTUDIO_APPDIR 或 ~/.autogenstudio
    ├─ _init_paths()    → 计算 app_root / static_root / user_files / config_dir / database_uri
    ├─ _create_directories()  → mkdir -p 全部路径
    └─ _load_environment()    → load <app_root>/.env (可选)
    ↓
FastAPI lifespan
    ↓
init_managers(database_uri, config_dir, app_root)  (web/deps.py:134-208, 隐式)
    ├─ DatabaseManager(engine_uri, base_dir=app_root)
    ├─ _db_manager.initialize_database(auto_upgrade=False, force_init_alembic=True)
    │      └─ 表不存在 → create_all + Alembic init
    ├─ import_teams_from_directory(config_dir, ...)  ← 导入 Gallery JSON
    ├─ init_lite_mode(...)  ← 仅 lite
    ├─ WebSocketManager(db_manager=...)
    └─ TeamManager()  ← 进程内单例,无状态
    ↓
HTTP server ready
```

**全程没有"我先问你一句'是否要初始化'"**。

#### 3.4 反例 / 主动干预的入口

- **`--upgrade-database`** (`cli.py:43,68`):手动触发 Alembic 迁移升级,绕过自动检测。
- **`AUTOGENSTUDIO_UPGRADE_DATABASE=1`**:同上,环境变量形式。
- **`--appdir <new_path>`**:错误信息里建议用新路径重新初始化(`schema_manager.py:453`)。
- **`force_init_alembic=True`**:默认就是 True,启动时强制重置 Alembic 目录。
- **AGBench 行为**:`run` 子命令时如果 scenario 目录已存在,会报错要求先 `clean`(`agbench/README.md` 中的子命令约定,代码细节未深入)。

---

## 3. 关键代码片段

### 3.1 `LocalCommandLineCodeExecutor.work_dir` 懒创建模式(`local/__init__.py:246-256`)

```python
@property
def work_dir(self) -> Path:
    """(Experimental) The working directory for the code execution."""
    if self._work_dir is not None:
        return self._work_dir
    else:
        # Automatically create temp directory if not exists
        if self._temp_dir is None:
            self._temp_dir = tempfile.TemporaryDirectory()
            self._started = True
        return Path(self._temp_dir.name)
```

**意图很清晰**:`work_dir` property 是 lazy 的,只在第一次 `execute_code_blocks()` 触发时分配 `tempfile.TemporaryDirectory()`;用户传了 `work_dir` 就用用户的,没传就走 temp。

### 3.2 Studio `AppInitializer._create_directories`(`web/initialization.py:64-67`)

```python
def _create_directories(self) -> None:
    """Create all required directories"""
    self.app_root.mkdir(parents=True, exist_ok=True)
    dirs = [self.static_root, self.user_files, self.ui_root, self.config_dir]
    for path in dirs:
        path.mkdir(parents=True, exist_ok=True)
```

**没有 `if not exists` 分支** — 一律 `exist_ok=True`,启动幂等。

### 3.3 Studio `app_root` 解析(`web/initialization.py:41-45`)

```python
def _get_app_root(self) -> Path:
    """Determine application root directory"""
    if app_dir := os.getenv("AUTOGENSTUDIO_APPDIR"):
        return Path(app_dir)
    return Path.home() / ".autogenstudio"
```

**优先级**:`AUTOGENSTUDIO_APPDIR` 环境变量 > `~/.autogenstudio`(注意:**CLI `--appdir` 本身不直接生效**,它只是把值写进 `temp_env_vars.env` 临时文件,然后 uvicorn 用 `env_file=...` 把它"喂"给子进程的环境)。

### 3.4 Docker Executor 容器挂载(`docker/_docker_code_executor.py:546-547`)

```python
volumes={str(self.bind_dir.resolve()): {"bind": "/workspace", "mode": "rw"}, **self._extra_volumes},
working_dir="/workspace",
```

**`bind_dir` ≠ `work_dir`**:bind_dir 是挂载源(主机侧),work_dir 是脚本实际写入位置(默认 = bind_dir),容器里 cwd 是 `/workspace`。

### 3.5 Magentic-One CLI 配置加载(`magentic-one-cli/_m1.py:99-105`)

```python
if os.path.isfile(DEFAULT_CONFIG_FILE):                # "config.yaml"
    with open(DEFAULT_CONFIG_FILE, "r") as f:
        config = yaml.safe_load(f)
else:
    config = yaml.safe_load(DEFAULT_CONFIG_CONTENTS)   # 内置默认配置
...
async with DockerCommandLineCodeExecutor(work_dir=os.getcwd()) as code_executor:
```

**典型 CLI 风格**:配置在 CWD,work_dir 在 CWD,没有用户属主配置目录。

### 3.6 ChromaDB Memory 默认路径约定(`chromadb/_chromadb.py:93`)

```python
persistence_path=os.path.join(str(Path.home()), ".chromadb_autogen"),
```

**注意**:这只是 docstring 示例的硬编码,不是 config 默认值。`PersistentChromaDBVectorMemoryConfig.persistence_path` 的真实默认值是 `"./chroma_db"`(`chromadb/_chroma_configs.py:120`)。换句话说:**有约定(`~/.chromadb_autogen`),但只有 docstring 示范**,没有"找不到就自动建在 home"这种回退逻辑。

---

## 4. 与 Onion Agent 设计的关联

| Onion Agent 设计点 | AutoGen 的对应 | 可借鉴 / 警惕 |
|---|---|---|
| `session.json` 是单一真相源 | 没有 — AutoGen 状态分裂在 SQLite(team/session/run/message) + ChromaDB(memory) + 各种 work_dir | 警惕:**统一落盘 ≠ 多 backend 拼凑**。AutoGen 的多 backend 在跨 session 恢复时是噩梦 |
| 工作区路径可配置 | `work_dir` 是参数,可 Pydantic Config 持久化 | 借鉴:`Pydantic Config` 是序列化"工作区"参数的好容器,Onion Agent 的 `OnionConfig` 可以照搬 |
| init 流程 | 完全隐式,启动即建 | **Onion Agent 应该比 AutoGen 严格** — 提供 `onion init` 命令,显式建 `~/.onion-agent/{sessions,cache,logs,workspace}` |
| 用户属主目录 | `~/.autogenstudio/`(Studio only)、`~/.chromadb_autogen/`(memory only) | 借鉴:用 `XDG_DATA_HOME` / `dirs` 库,Windows / Linux / macOS 跨平台 |
| 多 Agent 共享 work_dir | "传同一个 Executor 实例" + Docker bind_dir | 借鉴:Onion Agent 的 sub-agent 想要共享工作区,直接传同一个 `OnionWorkspace` 实例,避免 CWD 抖动 |
| CWD 当 work_dir | 显式 deprecated | 警惕:**永远不要让 Agent 默默修改 CWD** — AutoGen 现在发 warning 是因为太多人这么干 |
| `cleanup_temp_files` | 局部清理(只清自己写的 tmp_code_*) | 借鉴:Onion Agent 应该提供"会话级 GC"和"产物级 GC"两档 |
| MCP Filesystem Workbench | `~` + `tempfile.gettempdir()` 拼接 | 警惕:**默认就开放 home 是危险设计**,Onion Agent 默认应该是 `<workspace>/sandbox/` 之类的子目录 |
| Gallery 模板在 `<app_root>/configs/` | 启动时 `import_teams_from_directory` 注入 | 借鉴:"模板/示例"和"用户数据"分离目录是个好习惯 |
| `--upgrade-database` Alembic 迁移 | 单进程 + SQLite | 警惕:AutoGen Studio 的 SQLite 单文件设计在多副本/多用户场景会立刻坏掉。Onion Agent 应当默认走 PostgreSQL |
| `tempfile.TemporaryDirectory()` 兜底 | 永不创建真实文件,只在 temp 跑 | 借鉴:**这种"无副作用开发模式"对 debugging 不友好**,Onion Agent 应该默认有持久目录,临时目录是显式 opt-in |

---

## 5. 不确定 / 未找到

1. **`autogen-studio/autogenstudio/web/skills/`** 目录虽然在 `.gitignore` 出现(`autogenstudio/web/skills/user/*`),但代码里没找到任何引用 — **可能是个被废弃/未实现的功能**,或前端占位。
2. **`workdir/`** 子目录在 `.gitignore` 中也出现,但当前代码没看到创建它的逻辑 — 疑似残留。
3. **`database.sqlite`** 和 **`autogen04203.db`** 是两个不同的数据库文件?从 `web/config.py:7` 看主数据库是 `autogen04203.db`,`database.sqlite` 可能是 `import_team` 等子操作的临时库,需要进一步确认。
4. **`pyautogen/src/pyautogen/__init__.py`** 是空文件,只起 package 占位作用 — 旧版用户 import `pyautogen` 实际上 import 的是 `autogen-agentchat` 路径,需要看历史 commit 确认过渡策略。
5. **AGBench 的 `work_dir` 和 `HOST_WORKSPACE`** 行为只看了部分,完整 benchmark 启动流程没深入。
6. **`autogen-magentic-one` 包当前是空壳**(`README.md` + `LICENSE-CODE`),真正的 `MagenticOneGroupChat` 实现已迁移到 `autogen-agentchat`,包保留可能是为 pip 兼容。
7. **autogen 0.6+ 是否引入了新的统一工作区抽象** — 调研时只看到 `autogen-core` 的 `Component` 抽象和 `CacheStore`/`Memory` 接口,**没有** "Workspace" 这种顶级概念,如果是用户想做的"洋葱工作区"语义,AutoGen 完全没有可对照实现。

---

## 6. 总结

| 维度 | 评分(1-5) | 评注 |
|---|---|---|
| **统一性** | ⭐⭐ | 多 backend 拼凑,没有"全局工作区"概念 |
| **可配置性** | ⭐⭐⭐⭐ | `work_dir` 等关键路径都是参数;但环境变量支持有限 |
| **隐式 vs 显式 init** | ⭐⭐(隐式倾向) | 完全没有 `init` 命令,启动即建 |
| **路径可序列化** | ⭐⭐⭐⭐⭐ | Pydantic `Component` 模型完美支持 `to_config` / `from_config` 序列化 |
| **跨平台性** | ⭐⭐⭐ | 用 `pathlib.Path` 主流,但 `os.getcwd()` 和 home 硬编码穿插 |
| **沙箱安全** | ⭐⭐ | FileSurfer 有 `base_path` 限制,但默认就放开 home |
| **Onion Agent 可借鉴度** | — | **反面教材居多**;最有价值的点是 `Component` 序列化模型 + `work_dir` 懒创建语义 |
