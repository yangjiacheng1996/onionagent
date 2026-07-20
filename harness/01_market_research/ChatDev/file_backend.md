# ChatDev — 工作区(File Backend)调研报告

> 调研对象:`OpenBMB/ChatDev` 仓库 `main` 分支的当前 `HEAD`(`README.md` 自报为 **ChatDev 2.0 (DevAll)**,2026-01-07 发布;**不是经典的 ChatDev 1.0 "CEO/CTO/Programmer"**)。
> 经典 ChatDev 1.0 已迁到 `chatdev1.0` 分支(`README.md:7-9`),本调研的代码证据来自 `main` 分支。

---

## 0. 智能体一句话定位

**"ChatDev 2.0 (DevAll)":一个 Zero-Code 多智能体编排平台**。原先 ChatDev 1.0 的"CEO/CTO/程序员/测试员"角色已抽象为通用 `agent` 节点,用户用 YAML DAG 自由拼装节点(图、`python` 工具、`tooling`、`human` 节点),每次运行写一个 `WareHouse/<session>/` 目录作为完整沙箱与产物仓库。设计哲学从"模拟公司"升级为"模拟 IDE"。

---

## 1. 调研依据

| 文件/目录 | 用途 |
| --- | --- |
| `run.py:1-105` | CLI 入口(`--path`、`--name`、无 `--output-root`) |
| `runtime/sdk.py:1-126` | Python SDK 入口(`run_workflow`) |
| `server_main.py:1-115` | FastAPI/uvicorn 启动入口,定义 `RELOAD_EXCLUDE_DIRS = ("WareHouse", ...)` |
| `server/settings.py:5` | 共享常量 `WARE_HOUSE_DIR = Path("WareHouse")` |
| `entity/graph_config.py:1-93` | `GraphConfig` dataclass,持有 `output_root` |
| `workflow/graph_context.py:43-86` | `GraphContext.__init__` 是 **真正创建工作区的地方** |
| `utils/attachments.py:50-99` | `AttachmentStore`,把附件写到 `root/<attachment_id>/<file>` + `attachments_manifest.json` |
| `workflow/runtime/result_archiver.py:1-25` | 运行结束归档:`token_usage_<session>.json`、`execution_logs.json` |
| `runtime/node/executor/python_executor.py:69-83` | Python 节点:`code_workspace` 是 `<graph_dir>/code_workspace`,每次写 `<node_id>.py` / `<node_id>_run-N.py` |
| `workflow/hooks/workspace_artifact.py:1-260` | 节点执行前后对 workspace 做快照,自动把变更文件注册为附件 |
| `server/services/workflow_run_service.py:144-155` | Server 端 `GraphConfig.from_definition(name=f"session_{session_id}", output_root=WARE_HOUSE_DIR, ...)` |
| `server/services/batch_run_service.py:163-217` | 批量模式:每个任务用 `metadata["fixed_output_dir"] = True` 锁住目录 |
| `docs/user_guide/zh/index.md:22-40` | 官方术语:`Session`、`code_workspace` |
| `docs/user_guide/zh/attachments.md:21-65` | 附件落盘规则 + `attachments_manifest.json` 描述 |
| `frontend/public/tutorial-zh.md:642-649` | 完整目录结构说明表 |
| `.gitignore:29` | `WareHouse/` 进 ignore,**不进版本控制** |

> **关键观察**:虽然仓库 README 自称 DevAll(零代码),但工作区核心理念没变 —— 仍是"`WareHouse/<session>/` 是一切产物的根,GraphContext 隐式创建它"。

---

## 2. 三个核心问题的回答

### Q1. 工作区路径

**结论**:`WareHouse` 写死为**相对于 cwd 的路径**,跟随当前目录;**没有任何 CLI 参数、环境变量可改**;**不支持写死用户属主目录**。

#### 代码证据

| 位置 | 代码 | 说明 |
| --- | --- | --- |
| `run.py:17` | `OUTPUT_ROOT = Path("WareHouse")` | CLI 入口硬编码相对路径 |
| `runtime/sdk.py:21` | `OUTPUT_ROOT = Path("WareHouse")` | SDK 入口硬编码相对路径 |
| `server/settings.py:5` | `WARE_HOUSE_DIR = Path("WareHouse")` | Server 端共享常量 |
| `entity/graph_config.py:35` | `output_root=Path(output_root) if output_root else Path("WareHouse")` | `GraphConfig.from_dict` 兜底默认 |
| `entity/graph_config.py:55` | `output_root=Path(output_root) if output_root else Path("WareHouse")` | `GraphConfig.from_definition` 兜底默认 |

#### 路径属性矩阵

| 维度 | 结论 | 证据 |
| --- | --- | --- |
| 写死用户属主目录(`~/`、`%USERPROFILE%`)? | ❌ 否 | 全是 `Path("WareHouse")` 相对路径 |
| CLI 参数可改? | ❌ 否 | `run.py:34-67` 的 `argparse` 只接受 `--path`/`--name`/`--fn-module`/`--inspect-schema`/`--schema-breadcrumbs`/`--attachment`,**无 `--output-root`** |
| 环境变量可改? | ❌ 否 | 全部 `grep` 没找到 `os.environ.get` / `os.getenv` 读取仓库根相关的键 |
| `GraphConfig` 参数可改? | ✅ 是(代码层) | `from_definition(...output_root=...)` 接受,但 `run.py` / `runtime/sdk.py` 调用点都把 `OUTPUT_ROOT` 写死 |
| 跟随当前目录(默认)? | ✅ 是 | `Path("WareHouse")` 是相对路径,以 Python 进程的 `cwd` 为基准 |
| `graph_config.py` 之外的覆盖点? | 有 | `server/services/workflow_run_service.py:152` 显式 `output_root=WARE_HOUSE_DIR`;`server/services/batch_run_service.py:212` 用 `WARE_HOUSE_DIR / f"session_{session_id}"` 作任务子目录 |

#### 一句话总结
**`WareHouse/` 是 cwd 相对路径,全仓库硬编码 3 处**(`run.py`、`runtime/sdk.py`、`server/settings.py`);GraphConfig 留了 `output_root` 形参,但所有官方入口都不传,直接用全局变量。

---

### Q2. 工作区目录结构

**结论**:`WareHouse/<session>/` 是单次运行沙箱;`code_workspace/` 是 Python 节点共享目录;`attachments/` 是用户上传/运行期文件;`node_outputs.yaml` / `workflow_summary.yaml` / `execution_logs.json` / `token_usage_<session>.json` 是运行结束生成的 4 件套审计文件。

#### 目录布局(官方文档 + 代码双证)

| 路径 | 角色 | 代码 / 文档证据 |
| --- | --- | --- |
| `WareHouse/` | 所有 Session 的根目录 | `frontend/public/tutorial-zh.md:642-649`、`docs/user_guide/zh/index.md:39` |
| `WareHouse/<session>/` | 单个 Session 运行时数据 | `frontend/public/tutorial-zh.md:643` |
| `WareHouse/<session>/code_workspace/` | Python 节点共享代码/产物目录 | `frontend/public/tutorial-zh.md:644`、`docs/user_guide/zh/index.md:40`、`runtime/node/executor/python_executor.py:74-80`(`root = (Path(graph_dir) / "code_workspace").resolve()`) |
| `WareHouse/<session>/code_workspace/attachments/` | 用户上传文件 + 运行期注册文件 | `frontend/public/tutorial-zh.md:645`、`docs/user_guide/zh/attachments.md:21` |
| `WareHouse/<session>/code_workspace/attachments/<attachment_id>/<file>` | 单个附件(每个 ID 一个子目录) | `utils/attachments.py:116-120`(`target_dir = self.root / attachment_id; target_dir.mkdir(...)`) |
| `WareHouse/<session>/code_workspace/attachments/attachments_manifest.json` | 附件清单 | `utils/attachments.py:55-58`(`self.manifest_path = self.root / "attachments_manifest.json"`) |
| `WareHouse/<session>/code_workspace/<node_id>.py` 或 `<node_id>_run-N.py` | Python 节点每次执行的脚本 | `runtime/node/executor/python_executor.py:96-105` |
| `WareHouse/<session>/node_outputs.yaml` | 节点输出记录(运行后) | `workflow/graph_context.py:88-93`(`outputs_path = self.directory / "node_outputs.yaml"`) |
| `WareHouse/<session>/workflow_summary.yaml` | 工作流摘要(运行后) | `workflow/graph_context.py:95-102`(`summary_path = self.directory / "workflow_summary.yaml"`) |
| `WareHouse/<session>/execution_logs.json` | 执行日志(运行后) | `workflow/runtime/result_archiver.py:21-24`(`log_file_path = self.graph.directory / "execution_logs.json"`) |
| `WareHouse/<session>/token_usage_<session>.json` | Token 使用统计(运行后) | `workflow/runtime/result_archiver.py:17-18`(`f"token_usage_{self.graph.name}.json"`) |
| `WareHouse/session_<session_id>/` | Server 端 batch 任务的输出根 | `server/services/batch_run_service.py:163-167`(`output_root = WARE_HOUSE_DIR / f"session_{session_id}"`) |
| `WareHouse/session_<session_id>/batch_results.csv` | 批量任务结果 CSV | `server/services/batch_run_service.py:166` |
| `WareHouse/session_<session_id>/batch_manifest.json` | 批量任务 manifest | `server/services/batch_run_service.py:167` |

#### Session 目录命名规则(`workflow/graph_context.py:79-85`)

```python
timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
fixed_output_dir = bool(config.metadata.get("fixed_output_dir"))
if fixed_output_dir or "session_" in config.name:
    self.directory = config.output_root / config.name
else:
    self.directory = config.output_root / f"{config.name}_{timestamp}"
self.directory.mkdir(parents=True, exist_ok=True)
```

| 触发条件 | 命名结果 | 例子 |
| --- | --- | --- |
| 默认(`name="myapp"`) | `WareHouse/myapp_20260108120000/` | CLI `python run.py --name myapp` |
| 名字含 `session_` 前缀 | `WareHouse/session_xxx/`(无时间戳) | Server `name=f"session_{session_id}"` |
| `metadata["fixed_output_dir"]=True` | 固定目录(可被 batch 复用) | `server/services/batch_run_service.py:215` |
| SDK 不指定 `session_name` | `WareHouse/sdk_<yaml_stem>_<timestamp>/` | `runtime/sdk.py:40-43`(`_normalize_session_name`) |

#### 重要观察
- **没有 ChatDev 1.0 那套"CEO/CTO/Programmer 各一目录"**。`entity/configs/node/agent.py` 把所有角色统一为 `agent` 节点,产物路径与角色无关。
- **没有"商品/软件/文档"这种业务子目录**。`code_workspace/` 是事实上的"商品目录",Python 节点产生的代码/数据/报告/图片/视频都写在这里,由 `WorkspaceArtifactHook` 自动注册为附件。
- **没有"共享知识库"**。Agent 间通信走 `workflow/graph.py` 的 `outputs` 字典和 `workflow/runtime/runtime_context.py` 的 `global_state`,**不落盘**。Memory 是单独概念(`runtime/node/agent/memory/`),可独立持久化(如 `simple` / `file` / `blackboard` / `mem0`)。

---

### Q3. 工作区创建

**结论**:**完全隐式** —— `GraphContext.__init__` 在被构造时直接 `mkdir(parents=True, exist_ok=True)`,**没有 `init` / `setup` / `bootstrap` 子命令**。第一次 `python run.py` / `POST /api/workflow/execute` / `runtime.sdk.run_workflow()` 调用时,**工作区自动出现**。

#### 核心证据:`GraphContext.__init__` 一锤定音

`workflow/graph_context.py:60-86`:
```python
def __init__(self, config: GraphConfig) -> None:
    self.config = config
    ...
    # Output directory
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    fixed_output_dir = bool(config.metadata.get("fixed_output_dir"))
    if fixed_output_dir or "session_" in config.name:
        self.directory = config.output_root / config.name
    else:
        self.directory = config.output_root / f"{config.name}_{timestamp}"
    self.directory.mkdir(parents=True, exist_ok=True)   # ← 隐式创建
```

#### 触发链(谁调用 `GraphContext` → 触发隐式创建)

| 入口 | 调用链 | 证据 |
| --- | --- | --- |
| **CLI** `python run.py --path x --name y` | `run.py:97-99` → `graph_context = GraphContext(config=graph_config)` | `run.py:97-99` |
| **SDK** `runtime.sdk.run_workflow(yaml_file, task_prompt=...)` | `runtime/sdk.py:97-98` → `graph_context = GraphContext(config=graph_config)` | `runtime/sdk.py:97-98` |
| **Server 单跑** `POST /api/workflow/execute` | `server/services/workflow_run_service.py:149-152` → `GraphContext(config=graph_config)` | `workflow_run_service.py:149-152` |
| **Server 同步** `POST /api/execute_sync` | `server/routes/execute_sync.py:95-98` → `GraphConfig.from_definition(...,output_root=OUTPUT_ROOT,...)` | `execute_sync.py:95-98` |
| **Batch** 批量任务 | `server/services/batch_run_service.py:208-213` → 显式 `output_root = WARE_HOUSE_DIR / f"session_{session_id}"` + `graph_config.metadata["fixed_output_dir"] = True` | `batch_run_service.py:208-215` |
| **Server 启动** | 仅创建 `logs/` 目录,**不创建 WareHouse** | `server_main.py:81-83`(`log_dir = Path("logs"); log_dir.mkdir(exist_ok=True)`) |

#### 子目录的隐式创建链

| 子目录 | 何时创建 | 证据 |
| --- | --- | --- |
| `code_workspace/` | Python 节点第一次执行时 | `runtime/node/executor/python_executor.py:74-80`(`root.mkdir(parents=True, exist_ok=True)`) |
| `code_workspace/attachments/` | `AttachmentStore.__init__` / 任务输入构造 | `utils/attachments.py:57`(`self.root.mkdir(parents=True, exist_ok=True)`) + `runtime/sdk.py:54-55` + `run.py:24-27` |
| `code_workspace/attachments/<attachment_id>/` | `AttachmentStore.register_file` | `utils/attachments.py:116-120` |
| 4 件套审计文件 | 运行结束(`graph_context.record()` + `ResultArchiver.export()`) | `workflow/graph_context.py:88-102` + `workflow/runtime/result_archiver.py:17-24` |

#### 是否有 init 命令?

**没有**。`grep` 仓库找不到任何 `init`、`setup`、`create-workspace`、`bootstrap-workspace` 之类的子命令(只有 `runtime/bootstrap/schema.py` 跟 schema registry 有关,不是工作区)。

#### 一句话总结
**隐式创建 + 跟随 cwd**。第一次跑就建好,`mkdir(parents=True, exist_ok=True)` 保证幂等。`metadata["fixed_output_dir"]=True` 是唯一显式控制目录命名的小开关。

---

## 3. 关键代码片段

### 3.1 `GraphContext.__init__` —— 工作区的"诞生点"

`workflow/graph_context.py:60-86`:

```python
def __init__(self, config: GraphConfig) -> None:
    self.config = config
    self.vars: Dict[str, Any] = dict(config.vars)

    # Graph structure
    self.nodes: Dict[str, Node] = {}
    self.edges: List[Dict[str, Any]] = []
    ...

    # Output directory
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    fixed_output_dir = bool(config.metadata.get("fixed_output_dir"))
    if fixed_output_dir or "session_" in config.name:
        self.directory = config.output_root / config.name
    else:
        self.directory = config.output_root / f"{config.name}_{timestamp}"
    self.directory.mkdir(parents=True, exist_ok=True)
    # Voting mode flag
    self.is_majority_voting: bool = config.is_majority_voting
```

> **设计点**:`GraphConfig`(不可变配置)和 `GraphContext`(可变运行时状态)分离。`GraphContext.directory` 一旦确定就作为整个图、所有节点、所有附件、所有日志的根 —— 后续 `code_workspace`、`attachments/<id>/<file>`、`node_outputs.yaml`、`token_usage_<session>.json` 全部以它为锚点。

### 3.2 `AttachmentStore` —— 附件落盘 + 清单

`utils/attachments.py:50-60, 105-145`:

```python
class AttachmentStore:
    def __init__(self, root_dir: Path | str, inline_size_limit: int = DEFAULT_INLINE_LIMIT) -> None:
        self.root = Path(root_dir)
        self.inline_size_limit = inline_size_limit
        self.root.mkdir(parents=True, exist_ok=True)                # ← 隐式
        self.manifest_path = self.root / "attachments_manifest.json"
        ...

    def register_file(self, file_path, *, copy_file=True, ...):
        ...
        if copy_file:
            target_dir = self.root / attachment_id                # ← 每个附件一个子目录
            target_dir.mkdir(parents=True, exist_ok=True)
            target_path = target_dir / source.name
            shutil.copy2(source, target_path)
        ...
        self._save_manifest()                                     # ← 写清单
```

### 3.3 `PythonNodeExecutor` —— Python 节点用 workspace

`runtime/node/executor/python_executor.py:69-105`:

```python
def _ensure_workspace_root(self) -> Path:
    root = self.context.global_state.setdefault(self.WORKSPACE_KEY, None)
    if root is None:
        graph_dir = self.context.global_state.get("graph_directory")
        if not graph_dir:
            raise RuntimeError("graph_directory missing from execution context")
        root = (Path(graph_dir) / "code_workspace").resolve()
        root.mkdir(parents=True, exist_ok=True)
        self.context.global_state[self.WORKSPACE_KEY] = str(root)
    else:
        root = Path(root).resolve()
        root.mkdir(parents=True, exist_ok=True)
    return root

def _write_script_file(self, node: Node, workspace: Path, code: str) -> Path:
    counters = self.context.global_state.setdefault(self.COUNTER_KEY, {})
    safe_node_id = re.sub(r"[^0-9A-Za-z_\-]", "_", node.id)
    run_count = counters.get(node.id, 0) + 1
    counters[node.id] = run_count
    suffix = f"_run-{run_count}" if run_count > 1 else ""
    filename = f"{safe_node_id}{suffix}.py"
    path = (workspace / filename).resolve()
    path.write_text(code + ("\n" if not code.endswith("\n") else ""), encoding="utf-8")
    return path
```

> **亮点**:同一节点重跑时,会保留前几次的 `<node_id>.py` / `<node_id>_run-2.py` / `<node_id>_run-3.py` —— **全审计、可重放**。

### 3.4 `WorkspaceArtifactHook` —— workspace 变更自动注册附件

`workflow/hooks/workspace_artifact.py:65-130` 节选:

```python
def before_node(self, node: Node, workspace: Path) -> None:
    if not self.can_handle(node):
        return
    snapshot, _ = self._snapshot(workspace)          # 拍 before 快照
    self._snapshots[node.id] = snapshot

def after_node(self, node: Node, workspace: Path, *, success: bool) -> None:
    if not success or not self.can_handle(node):
        self._snapshots.pop(node.id, None)
        return
    before = self._snapshots.pop(node.id, {})
    after, truncated = self._snapshot(workspace)      # 拍 after 快照
    changed_paths = [
        Path(path_str)
        for path_str, signature in after.items()
        if path_str not in before or before[path_str].sha256 != signature.sha256
    ]
    # 把 changed_paths 全部 register_file 到 AttachmentStore
    # → 触发 WorkspaceArtifact → WebSocket 推送
```

> **亮点**:Python / agent 节点跑完,**workspace 里新增/修改的文件**自动以 `<attachment_id>/<file>` 形式入库,**无需节点显式调 `register_file`**。这是"workspace 即真相"的设计。

### 3.5 `run.py` CLI 入口

`run.py:16-99`:

```python
OUTPUT_ROOT = Path("WareHouse")
...
def main() -> None:
    args = parse_arguments()
    ...
    task_prompt = input("Please enter the task prompt: ")   # 交互式 prompt
    graph_config = GraphConfig.from_definition(
        design.graph,
        name=args.name,
        output_root=OUTPUT_ROOT,                             # 写死的 WareHouse
        source_path=str(args.path),
        vars=design.vars,
    )
    graph_context = GraphContext(config=graph_config)        # 隐式 mkdir
    ...
    GraphExecutor.execute_graph(graph_context, task_input)
    print(graph_context.final_message())
```

### 3.6 `.gitignore`

`.gitignore:29`:
```
WareHouse/
```

工作区**不进版本控制**。`server_main.py:24` 还把 `WareHouse`、`logs`、`data`、`temp`、`node_modules` 一并加入 uvicorn `--reload` 的白名单排除,防止 agent 写文件触发服务重启(`README-zh.md:139`)。

---

## 4. 与 Onion Agent 设计的关联

### 4.1 借鉴(对 Onion Agent 有价值的部分)

| ChatDev 做法 | 对 Onion Agent 的启示 |
| --- | --- |
| **Config 不可变 + Context 可变**(分离) | Onion Agent 当前"围绕 session.json 累加"的哲学很好,但可考虑在 session.json 之上加一层 `SessionMeta`(创建时间、project_name、output_root 等不可变元数据),session.json 只存可变状态。 |
| **隐式 `mkdir(parents=True, exist_ok=True)`** | Onion Agent 可在 `Session.__init__` 里同样做,**不要 init 子命令**。降低用户心智负担。 |
| **`<project_name>_<YYYYMMDDhhmmss>` 命名** | 比 Onion Agent 当前的 `<uuid>` 命名对人类更友好;时间戳可排序,uuid 不行。**建议 Onion Agent 改用 `name_timestamp` 或 `name_short-uuid` 混合**。 |
| **`code_workspace/` 子目录集中放代码/附件产物** | Onion Agent 当前如果把代码、报告、附件都直接散在 session 根,会混乱。建议引入 `code_workspace/` / `attachments/` / `artifacts/` 三个子目录。 |
| **`metadata.fixed_output_dir=True` 开关** | Onion Agent 可加 `Session.fixed_dir` 标志,让 batch / 增量场景复用同一目录。 |
| **`attachments_manifest.json` 显式清单** | 比单纯扫文件可靠;`sha256`+`size` 字段可做去重和增量。 |
| **运行结束 4 件套**:`node_outputs.yaml`、`workflow_summary.yaml`、`execution_logs.json`、`token_usage_<session>.json` | Onion Agent 当前只靠 session.json 做单一真相源,审计能力弱。建议保留 session.json 主线,再补 4 件套作为"派生视图"(可由 session.json 派生,但物化下来便于排查)。 |
| **`WorkspaceArtifactHook`(节点前后做快照,自动注册变更文件为附件)** | 杀手锏 —— **无需节点显式调 `attach()`**,agent 写到 workspace 的文件自动可下载。Onion Agent 必须有等价机制;否则每次写完都要手动 `agent.write_artifact(path)`,用户负担重。 |
| **Python 节点每次执行写 `<node_id>_run-N.py`,旧文件不删** | 极简但强 —— **全审计、可重放**。Onion Agent 工具调用应当同等保留执行历史(尤其 `exec_python` / `exec_bash`)。 |
| **`.gitignore` 排除 workspace** | 显然。但 Onion Agent 应当提醒用户:在 `.gitignore` 也要写上 `.onion/` / `onion_workspace/` / `session_*` 等。 |
| **Server 端 reload 排除 workspace** | 如果 Onion Agent 也做 server(API + Web UI),`uvicorn --reload` 必须排除 workspace,否则每写一次文件就重启。 |

### 4.2 规避(ChatDev 的坑)

| ChatDev 坑 | Onion Agent 应规避 |
| --- | --- |
| **写死 `Path("WareHouse")` 相对路径**(3 处硬编码) | Onion Agent 应当用**单一配置入口**:`Settings.output_root`(支持环境变量 `ONION_OUTPUT_ROOT`、CLI `--output-root`、默认 `~/.onion/workspace`),**全代码只读一处**。 |
| **CLI 无 `--output-root` 参数** | Onion Agent CLI 必须有 `--output-root` 和 `ONION_OUTPUT_ROOT` 环境变量;否则用户改不了。 |
| **没有"用户属主目录"概念** | Onion Agent 在用户级配置时应默认 `~/.onion/workspace/<project>`,而不是 cwd 相对 —— 后者对 IDE / 远程服务器 / Docker 容器场景都不友好。 |
| **`session_` 前缀触发固定目录**(隐式契约) | Onion Agent 不要做这种"看字符串前缀"的隐式行为;改用显式 `SessionConfig.fixed_dir: bool` 字段。 |
| **3 处硬编码 `OUTPUT_ROOT`/`WARE_HOUSE_DIR`**(run.py / runtime/sdk.py / server/settings.py) | Onion Agent 用 `from onion.config import settings; settings.output_root` 单点访问。 |
| **Server 端 `session_store` 是纯内存的**(`server/services/session_store.py:67-83`) | Onion Agent 如果做 server,必须把 session 状态落盘(否则重启即丢失)。 |
| **`workflow_authoring.md:245` 提到 `context.json`,但 `record()` 只写 `node_outputs.yaml` 和 `workflow_summary.yaml`** | 文档与代码脱节 —— Onion Agent 必须用同一份 schema / 自动生成的文档,不要人工维护。 |
| **没有"工作区清理"机制**(文档 `attachments.md:65` 明确说 "WareHouse 打包下载不会删除原文件,需要额外策略") | Onion Agent 要内置 retention policy(按 age / size / count 自动归档或清理)。 |
| **没有"工作区 dry-run / preview"**(用户首次跑前不知道会创建什么路径) | Onion Agent CLI 可加 `--dry-run` 打印将要创建的路径。 |

### 4.3 直接可落地到 Onion Agent 的 3 条

1. **隐式创建 + 命名规则**:
   ```python
   # onion/session.py
   class Session:
       def __init__(self, name: str, output_root: Path):
           ts = datetime.now().strftime("%Y%m%d%H%M%S")
           self.directory = output_root / f"{name}_{ts}"
           self.directory.mkdir(parents=True, exist_ok=True)
           # 子目录
           (self.directory / "code_workspace").mkdir(exist_ok=True)
           (self.directory / "attachments").mkdir(exist_ok=True)
           # session.json —— Onion 的"洋葱核"
           (self.directory / "session.json").write_text(json.dumps({"name": name, "ts": ts}))
   ```

2. **WorkspaceArtifactHook 等价物**:
   ```python
   # onion/hooks.py
   class WorkspaceArtifactHook:
       def before_node(self, workspace: Path): self._snapshot_before(workspace)
       def after_node(self, workspace: Path):
           changed = diff(self._before, snapshot(workspace))
           for path in changed:
               register_artifact(workspace / path)  # 写到 attachments/<id>/
               emit_event("artifact_created", ...)
   ```

3. **4 件套审计文件**(可由 session.json 派生):
   - `node_outputs.yaml` —— 每个节点最终输出
   - `workflow_summary.yaml` —— 元数据(project、design_path、duration)
   - `execution_logs.json` —— 完整执行流(便于回放)
   - `token_usage_<session>.json` —— 计费/成本数据

---

## 5. 不确定 / 未找到

| 项 | 说明 |
| --- | --- |
| 文档 `workflow_authoring.md:245` 提到 `context.json`,但 `GraphContext.record()` 只写 `node_outputs.yaml` + `workflow_summary.yaml` | 可能是文档滞后,或 `context.json` 在别处生成(本调研未深挖) |
| `WorkflowSessionStore`(`server/services/session_store.py:67-83`)是**纯内存**的,服务重启即丢 | 与"`WareHouse/<session>/` 落盘"的设计目标不一致;可能是显式 trade-off(短期会话),需要查 PR / issue 确认 |
| 没有 "workspace 清理" / "retention policy" 实现,只有文档建议自己写 cron | 是已知缺口,不是 bug |
| 经典 ChatDev 1.0 的 `chatdev/chat_chain.py`、`chatdev/company.py` 在本仓库不存在 —— 已迁到 `chatdev1.0` 分支 | 本调研结论对 1.0 不一定适用,需另开调研 |
| `tutorial-zh.md:646-649` 表格里的 `execution_logs.json` / `token_usage_<session>.json` 是"运行结束后生成",但 batch 模式(`batch_run_service.py:163-167`)只写 `batch_results.csv` / `batch_manifest.json`,**不写** 4 件套 | 行为不一致;可能 batch 任务是另一种生命周期 |
| 没有 `init` / `setup` / `bootstrap` 工作区的子命令是**设计选择**还是**缺漏**? | 从 `mkdir(parents=True, exist_ok=True)` 的反复使用看,是**显式设计选择**(零摩擦) |
| `metadata.fixed_output_dir=True` 是否会与"`<name>_<timestamp>`"产生冲突(`mkdir(exist_ok=True)` 会复用旧目录) | 是!如果同 name 二次跑 + fixed_output_dir=True,**会写到同一个目录**而不会报错 —— 行为上类似"resume",但没有任何保护或提示 |

---

## 6. 一句话结论

**ChatDev 2.0 的 workspace 是一个"零摩擦、隐式创建、单一根、扁平会话"的设计** —— `WareHouse/<session>/` 一锤定音,所有产物(code / attachments / logs / token / summary)都挂在这棵树下;`GraphContext.__init__` 是隐式创建的"魔法时刻",`WorkspaceArtifactHook` 是把 workspace 变成"可下载资产库"的关键 hook。**优点是简单,缺点是配置入口死板、Server 端无持久化、清理策略缺失** —— 借鉴时必须把"用户级工作区根 + 显式配置入口 + 落盘 session 状态 + retention policy"这四件事补上。
