# MetaGPT — 工作区(File Backend)调研报告

> 调研对象:`geekan/MetaGPT` 仓库(`C:\workspace\github\onionagent\harness\01_market_research\clone\MetaGPT`)
> 调研者:deepcode · general agent
> 任务来源:Onion Agent 工作区 / File Backend 横向对比

## 0. 智能体一句话定位

**模拟软件公司多角色(产品经理 / 架构师 / 工程师 / QA),用 SOP 流水线把"一句话需求"自动拆解为 PRD → 系统设计 → 任务列表 → 可运行代码 + 测试。**

核心特点是引入"**项目级 Git 仓库**"作为多 Agent 的共享知识库:每个产物都是仓里的一个文件,由后一个 Agent 通过读 git diff / 文件依赖图来消费前一个 Agent 的输出。

## 1. 调研依据

| 文件 | 关键作用 |
| --- | --- |
| `metagpt/const.py:1-138` | 全局路径常量,`DEFAULT_WORKSPACE_ROOT`、`*_FILE_REPO` 全部从这里出 |
| `metagpt/configs/workspace_config.py:11-39` | `WorkspaceConfig`,定义 `path` / `use_uid` / `uid`,自带 `mkdir` |
| `metagpt/config2.py:31-140` | `Config` 总入口,把 CLI 参数、`yaml` 配置、环境变量合并到 `workspace` |
| `metagpt/software_company.py:14-93` | `metagpt` CLI 的 typer 入口,所有 `--project-*` 参数在这里定义 |
| `metagpt/actions/prepare_documents.py:23-89` | **整个工作区生命周期真正的入口** — `PrepareDocuments._init_repo()` 决定工作区怎么建 |
| `metagpt/utils/project_repo.py:23-145` | `ProjectRepo`,把"项目根"包成 `docs/` + `resources/` + `tests/` + `test_outputs/` + `srcs` |
| `metagpt/utils/file_repository.py:1-270` | `FileRepository`,所有 `repo.docs.prd.save(...)` 的底层 |
| `metagpt/utils/git_repository.py:1-200` | `GitRepository`,自动 `git init` + 提交 + diff 跟踪 |
| `metagpt/utils/common.py:961-973` | `get_project_srcs_path` 决定源码子目录名(`<project_path>/<project_name>/`) |
| `metagpt/environment/base_env.py:244-248` | `env.archive()` 在最后 `git commit` 一份"快照" |
| `metagpt/team.py:59-79` | `Team.serialize/deserialize`,把整个 Team 状态写到 `<workspace>/storage/team/team.json` |
| `metagpt/actions/write_prd.py:139-294` | 示例:`self.repo.docs.prd.save(...)`、`self.repo.resources.prd.save_pdf(...)` |
| `metagpt/roles/qa_engineer.py:62-230` | 示例:`self.repo.tests.save_doc(...)`、`self.repo.test_outputs.save(...)` |
| `metagpt/roles/engineer.py:142-272` | 示例:`self.repo.srcs.save(...)` 把代码写到 `<project_path>/<project_name>/` |
| `config/config2.example.yaml` | 用户配置示例,**没有 workspace 段** — workspace 全靠默认值 + CLI |
| `metagpt/document_store/` (注意:这是 RAG) | **不是多 Agent 共享知识库**,是给 RAG 用的 faiss/chroma/milvus 向量库,与本调研无关 |

## 2. 三个核心问题的回答

### Q1. 工作区路径(写死 / 可配置 / 跟随当前目录?)

| 维度 | 答案 | 代码证据 |
| --- | --- | --- |
| **默认根路径** | `METAGPT_ROOT / "workspace"`,其中 `METAGPT_ROOT` 由 `get_metagpt_root()` 决定(优先级 **环境变量 `METAGPT_PROJECT_ROOT` > 包根目录(含 `.git`/`.project_root`/`.gitignore` 之一)> `Path.cwd()`**) | `metagpt/const.py:19-44` |
| **配置入口** | `Config.workspace: WorkspaceConfig`,字段 `path: Path = DEFAULT_WORKSPACE_ROOT` | `metagpt/config2.py:74`、`metagpt/configs/workspace_config.py:14` |
| **CLI 自定义** | 4 个 CLI 参数控制:<br>· `--project-path` 指定**已有项目**(同时强制 `inc=True`)<br>· `--project-name` 指定**新项目名**(子目录名)<br>· `--inc` 增量模式(老项目继续迭代)<br>· `--recover-path` 从 `<workspace>/storage/team` 反序列化恢复 | `metagpt/software_company.py:67-91`、`metagpt/config2.py:48-58,111-123` |
| **绝对路径支持** | `path` 字段可以是任意 `Path`,`@field_validator` 把 `str` 转成 `Path` | `metagpt/configs/workspace_config.py:17-21` |
| **UID 子目录(已废弃)** | `WorkspaceConfig.use_uid: bool = False`、`uid: str = ""`,**但全代码库无任何调用点**(只在自己文件里出现两次) | `metagpt/configs/workspace_config.py:14-15,23-31` |
| **是否写死 `~/.metagpt/`?** | 配置文件 `config2.yaml` 写在 `~/.metagpt/config2.yaml`;但**工作区不在 `~/.metagpt/`,在 `<METAGPT_ROOT>/workspace/`** | `metagpt/const.py:39`、`metagpt/const.py:41` |
| **是否支持环境变量?** | `METAGPT_PROJECT_ROOT` 改 `METAGPT_ROOT`;`METAGPT_REPORTER_URL` 改报告服务地址;workspace 本身无独立环境变量 | `metagpt/const.py:23-37,93` |

**结论**:
- MetaGPT 工作区根**不是写死的 `~/.metagpt/`**,而是 **跟随项目根**(`METAGPT_PROJECT_ROOT` env > 包根 > `cwd`,然后拼 `/workspace`)。
- **典型 80% 用法**:`metagpt "做一个 2048 游戏"`,不传任何参数 → 工作区落在 **当前终端的 `pwd/workspace/<timestamp>/`**。
- 进阶用法 1:`--project-path ./myrepo` → 落到 `<myrepo>`,同时开 `inc` 模式(不会清空)。
- 进阶用法 2:`--project-name snake --project-path /tmp/work` → 落到 `/tmp/work/snake/`(但**这条路径会被覆盖回 `<workspace>/snake/`** 见 Q3 `_init_repo` 的判断逻辑,见 `metagpt/actions/prepare_documents.py:42-44`)。

### Q2. 工作区目录结构

MetaGPT 的"工作区"有两层概念,必须分清:

#### 2.1 工作区根目录 `<METAGPT_ROOT>/workspace/`

```
<METAGPT_ROOT>/workspace/
├── <project_name_or_timestamp>/        # ← 真正的"项目根",是一个 git 仓
│   ├── .git/                            # 自动 git init
│   ├── .gitignore                       # 内容: __pycache__, *.pyc, .vs
│   ├── .src_workspace                   # 内容: 源码子目录名(默认 = project_name)
│   ├── requirement.txt                  # 在 docs/ 下,原始用户需求
│   ├── requirements.txt                 # 在根,Python 依赖(pip)
│   ├── docs/                            # 文本制品
│   ├── resources/                       # PDF / 图表制品
│   ├── tests/                           # 测试代码
│   ├── test_outputs/                    # 测试运行结果
│   └── <project_name>/                  # ← 源码(被 srcs.workdir 指向)
└── storage/                             # SERDESER_PATH,跨项目 Team 状态
    └── team/team.json                   # Team.serialize 写出,可被 --recover-path 反序列化
```

**生成项目时的目录树**(以 `metagpt "Create a 2048 game"` 为例,假设工作区落到 `D:\proj\workspace\20260717203500\`):

| 路径 | 内容 | 谁写 | 代码证据 |
| --- | --- | --- | --- |
| `.git/` | 自动 `git init` + 初始 `.gitignore` commit | `GitRepository._init` | `metagpt/utils/git_repository.py:88-101` |
| `.gitignore` | `__pycache__`, `*.pyc`, `.vs` | `GitRepository._init` | `metagpt/utils/git_repository.py:94-99` |
| `.src_workspace` | 1 行文本,记录源码子目录名 | `get_project_srcs_path` 读 / `init_python_folder` 写 | `metagpt/utils/common.py:961-970,973-980` |
| `docs/requirement.txt` | 用户原始需求文本 | `PrepareDocuments.run` | `metagpt/actions/prepare_documents.py:75` |
| `docs/bugfix.txt` | 增量模式下的问题清单 | `WritePRD._handle_bugfix` | `metagpt/actions/write_prd.py:193` |
| `docs/prd/<timestamp>.json` | PRD JSON 原文 | `WritePRD._new_prd` | `metagpt/actions/write_prd.py:222-226` |
| `docs/prd/<timestamp>.md` | PRD 的人类可读版 | `WritePRD._new_prd` 调用 `save_pdf` | `metagpt/actions/write_prd.py:228`、`metagpt/utils/file_repository.py:220-237` |
| `docs/system_design/<file>.json` | 系统设计 JSON | `DesignAPI._update_system_design` | `metagpt/actions/design_api.py:190-202` |
| `docs/task/<file>.json` | WBS 任务列表 | `ProjectManagement._update_tasks` | `metagpt/actions/project_management.py:137-152` |
| `docs/code_summary/<file>.json` | 代码摘要 | `SummarizeCode` action | (见 `metagpt/actions/summarize_code.py`) |
| `docs/code_plan_and_change/<file>.json` | 代码规划与变更 | `WriteCodePlanAndChange` | `metagpt/actions/write_code_plan_and_change_an.py:214` |
| `docs/class_view/...` | 类视图 | `RebuildClassView` | `metagpt/const.py:84-110` |
| `docs/graph_repo/...` | 图仓库 | `RebuildSequenceView` 等 | `metagpt/const.py:108` |
| `resources/prd/<file>.md` | PRD 的 PDF/MD 报告 | `repo.resources.prd.save_pdf` | `metagpt/actions/write_prd.py:228` |
| `resources/system_design/<file>.md` | 系统设计报告 | `repo.resources.system_design.save_pdf` | `metagpt/actions/design_api.py:205` |
| `resources/competitive_analysis/<file>.svg` | 竞品分析四象限图(Mermaid) | `WritePRD._save_competitive_analysis` | `metagpt/actions/write_prd.py:275-280` |
| `resources/data_api_design/<file>.svg` | 数据 API 设计图 | `DesignAPI._save_data_api_design` | `metagpt/actions/design_api.py:209-218` |
| `resources/seq_flow/<file>.svg` | 时序图 | `DesignAPI._save_seq_flow` | `metagpt/actions/design_api.py:220-229` |
| `resources/code_plan_and_change/...` | 代码规划与变更的可视化 | `ProjectManagement` | `metagpt/actions/project_management.py:151` |
| `resources/api_spec_and_task/...` | 任务 PDF 报告 | `ProjectManagement` | `metagpt/actions/project_management.py:151` |
| `resources/graph_db/...` | 知识图谱 | `graph_repository` | `metagpt/const.py:109` |
| `tests/test_<module>.py` | QA 写的测试 | `QaEngineer._write_test` | `metagpt/roles/qa_engineer.py:62-103` |
| `test_outputs/test_<module>.py.json` | 测试运行结果 | `QaEngineer._run_code` | `metagpt/roles/qa_engineer.py:115-119` |
| `<project_name>/main.py` 等 | **真正的源代码**,由 `repo.srcs.save` 写 | `Engineer._act` | `metagpt/roles/engineer.py:142-145` |
| `requirements.txt` | pip 依赖 | `ProjectManagement._update_requirements` | `metagpt/actions/project_management.py:166-176` |
| `<workspace_root>/storage/team/team.json` | Team 序列化(全公司状态) | `Team.serialize` | `metagpt/team.py:59-64` |

#### 2.2 配置 / 共享数据(在工作区外)

| 路径 | 用途 | 代码证据 |
| --- | --- | --- |
| `~/.metagpt/config2.yaml` | **用户级 LLM 配置** (API key 等) | `metagpt/config2.py:88-92`、`metagpt/const.py:39` |
| `<METAGPT_ROOT>/config/config2.yaml` | 项目级配置覆盖 | `metagpt/config2.py:95-103` |
| `<workspace>/storage/team/team.json` | Team 状态快照(可 `--recover-path` 恢复) | `metagpt/team.py:60-64` |
| `data/research/`、`data/tutorial_docx/` 等 | MetaGPT 自带的 demo / 测评数据 | `metagpt/const.py:48-50` |

#### 2.3 各角色 → 写到哪里(角色 × 路径 矩阵)

| 角色 | 调用的 Action | 写入的 FileRepository | 物理路径(相对项目根) |
| --- | --- | --- | --- |
| TeamLeader | `PrepareDocuments` | `repo.docs` | `docs/requirement.txt` |
| ProductManager | `WritePRD` | `repo.docs.prd` + `repo.resources.prd` + `repo.resources.competitive_analysis` | `docs/prd/*.json` + `resources/prd/*.md` + `resources/competitive_analysis/*.svg` |
| Architect | `DesignAPI` | `repo.docs.system_design` + `repo.resources.system_design` + `repo.resources.data_api_design` + `repo.resources.seq_flow` | `docs/system_design/*.json` + `resources/system_design/*.md` + `resources/data_api_design/*.svg` + `resources/seq_flow/*.svg` |
| ProjectManager | `ProjectManagement` | `repo.docs.task` + `repo.resources.api_spec_and_task` + 项目根 `requirements.txt` | `docs/task/*.json` + `resources/api_spec_and_task/*.md` + `requirements.txt` |
| Engineer | `WriteCode` / `WriteCodePlanAndChange` / `WriteCodeReview` | `repo.srcs` | `<project_name>/*.py` |
| QaEngineer | `WriteTest` | `repo.tests` + `repo.test_outputs` | `tests/test_*.py` + `test_outputs/*.json` |
| DataAnalyst | (读 `docs/`) | 仅消费 | — |
| SummarizeCode | `SummarizeCode` | `repo.docs.code_summary` + `repo.resources.code_summary` | `docs/code_summary/*.json` + `resources/code_summary/*.md` |

### Q3. 工作区创建(init 显式 / 隐式 / 自动?)

**答:隐式创建,由 `PrepareDocuments` action 在 SOP 第一步自动建。**

调用链如下:

```
CLI: metagpt "Create a 2048 game"
  ↓
metagpt/software_company.py:27 startup(...)          # typer 入口
  ↓ generate_repo(...)
metagpt/software_company.py:14 generate_repo(...)    # 加载 config, build Team, hire 角色
  ↓ config.update_via_cli(...)  ← project_path / project_name / inc 被注入 config
metagpt/config2.py:111-123 update_via_cli(...)
  ↓ Context(config=config), Team(context=ctx)
metagpt/team.py:31 Team.__init__(...)                 # 选 MGXEnv(默认) 或 Environment
  ↓ asyncio.run(company.run(n_round, idea))
metagpt/team.py:101 run(...)                          # n 轮 env.run(), 直到所有角色 idle
  ↓
MGXEnv 收到 UserRequirement,转发给 TeamLeader
TeamLeader 触发 PrepareDocuments action
  ↓
metagpt/actions/prepare_documents.py:40 _init_repo()  ★ 真正的"建工作区" ★
  ↓
  1. name = config.project_name or FileRepository.new_filename()  # 没名字就时间戳
  2. path = Path(config.workspace.path) / name                     # 拼出项目根
  3. if path.exists() and not config.inc: shutil.rmtree(path)       # 非增量模式 → 清空
  4. self.context.kwargs.project_path = path                       # 写回 ctx
  5. return ProjectRepo(path)                                       # 这一行触发 git init
  ↓
metagpt/utils/project_repo.py:79 ProjectRepo.__init__(...)
  ↓ GitRepository(local_path=Path(root))   (auto_init=True 默认)
metagpt/utils/git_repository.py:81 GitRepository.open(...)
  ↓ 不是 git 仓? → _init(local_path)
metagpt/utils/git_repository.py:88 _init(...)
  ↓
  - Repo.init(path=...)          # git init
  - 写 .gitignore (__pycache__, *.pyc, .vs)
  - git add .gitignore + 初始 commit "Add .gitignore"
  ↓
返回 → PrepareDocuments 写 docs/requirement.txt → 发消息给 WritePRD
```

**三种创建模式的对比**:

| 模式 | 触发方式 | 物理路径 | 是否清空旧内容 |
| --- | --- | --- | --- |
| **默认(全新)** | `metagpt "做一个 X"` | `<METAGPT_ROOT>/workspace/<timestamp>/`(如 `20260717203500/`) | 是,`shutil.rmtree` 见 `metagpt/actions/prepare_documents.py:47-48` |
| **指定项目名(全新)** | `metagpt "做一个 X" --project-name snake` | `<METAGPT_ROOT>/workspace/snake/` | 是(若存在) |
| **增量(老项目继续)** | `metagpt "加个 Y 功能" --inc --project-path ./snake` | `./snake/`(直接使用) | **否**,复用 `.git/` 和所有文件,基于 `git diff` 增量改 |
| **恢复暂停的会话** | `metagpt --recover-path <workspace>/storage/team` | 序列化里写死的 `project_path` | **否**,但这跟"建工作区"无关,是反序列化 Team 状态 |

**`use_uid` 字段是"半成品"**:定义了但**没有任何地方使用**(`grep -r use_uid metagpt/` 只在 `workspace_config.py` 出现两次),看起来是为"每次跑自动加个时间戳-UUID 子目录"留的接口但没接上。**实际默认行为是 `use_uid=False`**,`path` 字段直接当工作区根用,项目名/时间戳由 `PrepareDocuments._init_repo` 在 path 后面再拼一层子目录。

## 3. 关键代码片段(摘录)

### 3.1 `WorkspaceConfig` 自动建目录

```python
# metagpt/configs/workspace_config.py:11-39
class WorkspaceConfig(YamlModel):
    path: Path = DEFAULT_WORKSPACE_ROOT      # = METAGPT_ROOT / "workspace"
    use_uid: bool = False                    # 死代码,见全文 grep
    uid: str = ""

    @field_validator("path")
    @classmethod
    def check_workspace_path(cls, v):
        if isinstance(v, str):
            v = Path(v)
        return v

    @model_validator(mode="after")
    def check_uid_and_update_path(self):
        if self.use_uid and not self.uid:
            self.uid = f"{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid4().hex[-8:]}"
            self.path = self.path / self.uid
        # Create workspace path if not exists
        self.path.mkdir(parents=True, exist_ok=True)   # ★ 第一次实例化就 mkdir
        return self
```

### 3.2 `PrepareDocuments._init_repo` — 工作区真正诞生的地方

```python
# metagpt/actions/prepare_documents.py:40-51
def _init_repo(self) -> ProjectRepo:
    """Initialize the Git environment."""
    if not self.config.project_path:
        name = self.config.project_name or FileRepository.new_filename()  # 时间戳
        path = Path(self.config.workspace.path) / name                    # ★ 工作区根 + 项目名
    else:
        path = Path(self.config.project_path)                             # --project-path 模式
    if path.exists() and not self.config.inc:                             # 增量模式不清空
        shutil.rmtree(path)
    self.context.kwargs.project_path = path                               # 写回 ctx,后续 action 都用这个
    self.context.kwargs.inc = self.config.inc
    return ProjectRepo(path)                                              # 触发 git init
```

### 3.3 `ProjectRepo` 拼装 docs / resources / tests / srcs

```python
# metagpt/utils/project_repo.py:23-93
class DocFileRepositories(FileRepository):
    prd: FileRepository
    system_design: FileRepository
    task: FileRepository
    code_summary: FileRepository
    graph_repo: FileRepository
    class_view: FileRepository
    code_plan_and_change: FileRepository

    def __init__(self, git_repo):
        super().__init__(git_repo=git_repo, relative_path=DOCS_FILE_REPO)   # DOCS_FILE_REPO = "docs"
        self.prd             = git_repo.new_file_repository(relative_path=PRDS_FILE_REPO)             # "docs/prd"
        self.system_design   = git_repo.new_file_repository(relative_path=SYSTEM_DESIGN_FILE_REPO)   # "docs/system_design"
        self.task            = git_repo.new_file_repository(relative_path=TASK_FILE_REPO)            # "docs/task"
        # ...

class ResourceFileRepositories(FileRepository):
    # 同结构,根是 "resources"
    def __init__(self, git_repo):
        super().__init__(git_repo=git_repo, relative_path=RESOURCES_FILE_REPO)   # "resources"
        self.competitive_analysis = git_repo.new_file_repository(COMPETITIVE_ANALYSIS_FILE_REPO)   # "resources/competitive_analysis"
        self.data_api_design      = git_repo.new_file_repository(DATA_API_DESIGN_FILE_REPO)        # "resources/data_api_design"
        # ...

class ProjectRepo(FileRepository):
    def __init__(self, root: str | Path | GitRepository):
        git_repo_ = GitRepository(local_path=Path(root))   # auto_init=True → git init
        super().__init__(git_repo=git_repo_, relative_path=Path("."))   # 自己 = 项目根
        self.docs         = DocFileRepositories(self._git_repo)
        self.resources    = ResourceFileRepositories(self._git_repo)
        self.tests        = self._git_repo.new_file_repository(TEST_CODES_FILE_REPO)        # "tests"
        self.test_outputs = self._git_repo.new_file_repository(TEST_OUTPUTS_FILE_REPO)     # "test_outputs"
        self._srcs_path   = None
        self.code_files_exists()
```

### 3.4 各 Action 一致地通过 `self.repo.xxx.save(...)` 写

```python
# metagpt/actions/write_prd.py:222-229 (产品经理)
node = await self._new_prd(req.content)
await self._rename_workspace(node)
new_prd_doc = await self.repo.docs.prd.save(
    filename=FileRepository.new_filename() + ".json",
    content=node.instruct_content.model_dump_json(),
)
await self._save_competitive_analysis(new_prd_doc)
md = await self.repo.resources.prd.save_pdf(doc=new_prd_doc)
```

```python
# metagpt/roles/engineer.py:142-145 (工程师)
await self.repo.srcs.save(
    filename=coding_context.filename,          # main.py / game.py ...
    dependencies=list(dependencies),           # 写依赖图,供下一次 diff
    content=coding_context.code_doc.content,
)
```

```python
# metagpt/roles/qa_engineer.py:86-89 (QA)
doc = await self.repo.tests.save_doc(
    doc=context.test_doc,
    dependencies={context.code_doc.root_relative_path},
)
```

```python
# metagpt/environment/base_env.py:244-248 (最终 git 提交一次)
def archive(self, auto_archive=True):
    if auto_archive and self.context.kwargs.get("project_path"):
        git_repo = GitRepository(self.context.kwargs.project_path)
        git_repo.archive()                      # add all changed + commit "Archive"
```

### 3.5 路径常量一览(`metagpt/const.py:81-110`)

```python
DOCS_FILE_REPO                  = "docs"
PRDS_FILE_REPO                  = "docs/prd"
SYSTEM_DESIGN_FILE_REPO         = "docs/system_design"
TASK_FILE_REPO                  = "docs/task"
CODE_PLAN_AND_CHANGE_FILE_REPO  = "docs/code_plan_and_change"
COMPETITIVE_ANALYSIS_FILE_REPO  = "resources/competitive_analysis"
DATA_API_DESIGN_FILE_REPO       = "resources/data_api_design"
SEQ_FLOW_FILE_REPO              = "resources/seq_flow"
SYSTEM_DESIGN_PDF_FILE_REPO     = "resources/system_design"
PRD_PDF_FILE_REPO               = "resources/prd"
TASK_PDF_FILE_REPO              = "resources/api_spec_and_task"
CODE_PLAN_AND_CHANGE_PDF_FILE_REPO = "resources/code_plan_and_change"
TEST_CODES_FILE_REPO            = "tests"
TEST_OUTPUTS_FILE_REPO          = "test_outputs"
CODE_SUMMARIES_FILE_REPO        = "docs/code_summary"
CODE_SUMMARIES_PDF_FILE_REPO    = "resources/code_summary"
RESOURCES_FILE_REPO             = "resources"
GRAPH_REPO_FILE_REPO            = "docs/graph_repo"
VISUAL_GRAPH_REPO_FILE_REPO     = "resources/graph_db"
CLASS_VIEW_FILE_REPO            = "docs/class_view"
```

## 4. 与 Onion Agent 设计的关联

Onion Agent 的设计哲学:**一切活动围绕 `session.json` 上下文历史文件**,Agent Loop 是围绕 session 文件的自动累加器。MetaGPT 给我们的对照和启发:

### 4.1 强对照点(值得借鉴)

| Onion Agent 元素 | MetaGPT 对应 | 启发 |
| --- | --- | --- |
| `session.json` 单文件 | `ProjectRepo` 整棵目录树 + git | MetaGPT **不是**单文件,而是"一个 git 仓 = 一次会话"。Onion 的单文件假设在简单场景更轻量,但 **MetaGPT 暴露了一个真问题**:角色之间需要可寻址的产物(`docs/prd/<ts>.json`),单 session.json 装不下时怎么办。**可考虑的折中**:`session.jsonl`(每行一个事件/制品引用),或 `session.json` 引用外部制品路径。 |
| 隐式自动累加 | `PrepareDocuments` 自动 `mkdir + git init` | ✅ **值得直接借鉴**。Onion Agent 应该有一个等价的"建工作区"动作,在 `session.json` 第一次出现时自动建工作区(可放 `~/.onion/workspaces/<session_id>/` 或 `cwd/.onion/`)。 |
| 显式 init 命令 | `metagpt --init-config` 仅初始化 LLM 配置,没单独 `--init-workspace` | MetaGPT **没有**独立的 `init workspace` 命令 — 它是流程第一步隐式做。**Onion Agent 可以更显式**:提供 `onion init [path]` 创建空工作区 + 空 `session.json`。 |

### 4.2 弱对照 / 反例(可规避)

| 问题 | MetaGPT 的表现 | Onion Agent 的设计建议 |
| --- | --- | --- |
| **路径隐式跟随 cwd** | `METAGPT_ROOT` 在没有 `METAGPT_PROJECT_ROOT` env 时回退到 `Path.cwd()`,意味着**用户从哪个目录跑 `metagpt`,产物就丢在哪** | Onion Agent **必须显式**有 `--workspace` 参数,默认走 `~/.onion/workspaces/`(用户属主目录),不跟随 cwd。这点 MetaGPT 没做好,我们要反向操作。 |
| **`--project-path` 既能当"新项目"又能当"老项目"** | `metagpt/actions/prepare_documents.py:42-44` 在 `project_path` 存在时直接覆盖,容易误删用户数据(虽然有 `if not inc: rmtree` 兜底) | Onion Agent 的 "open vs init" 应该用**两个不同的子命令**:`onion open <path>`(只读打开现有项目) vs `onion init <path>`(强制创建新)。 |
| **配置与工作区不在一处** | LLM 配置 `~/.metagpt/config2.yaml`,工作区 `<METAGPT_ROOT>/workspace/`,Team 状态 `<workspace>/storage/team.json` — **三处分散** | Onion Agent 应该把"工作区根"和"配置根"**统一**为 `~/.onion/<workspace_id>/`,所有文件都在一棵树下,便于打包/迁移/清理。 |
| **`use_uid` 死代码** | `WorkspaceConfig.use_uid` 定义了但全库没调用 | **不要给 Onion Agent 留"定义但未使用"的字段**,要么上线要么删,否则半年后没人记得为什么。 |
| **git 强依赖** | `GitRepository.__init__` 默认 `auto_init=True`,**每个项目都 git init** | Onion Agent 不一定要 git。Onion 的"上下文历史累加"天然就是 append-only,git 价值有限;反而增加依赖体积。可以把 git 做成**可选 backend**(`file_backend=git | sqlite | jsonl`)。 |
| **vector store 与工作区混淆命名** | `metagpt/document_store/` 目录是 RAG faiss 库,**与"多 Agent 共享知识库"无关**;真正的共享知识库是 `ProjectRepo` | Onion Agent 命名要小心:**别把 "context" 和 "knowledge base" 混**。建议 Onion 用 `session.json` = context,`artifacts/` = 制品,**不要**再起一个 "shared memory" 名词。 |
| **`<workspace>/storage/team/team.json` 全量序列化** | `Team.serialize` 把整个 company 状态 JSON 化,反序列化时 `Context` 重建 | Onion 的 `session.json` 如果想做类似"暂停-恢复",**只存可重建的最小信息**(消息历史 + 当前 todo),不要存 LLM 对象、cost manager 内部状态这些。 |

### 4.3 MetaGPT 没做但 Onion 可加的(增量价值)

1. **版本化(session 自带 diff)**:MetaGPT 用 git 做版本化,Onion 的 `session.jsonl` 可以自带 `(seq, parent_seq, patch)` 三元组,比 git 轻。
2. **工作区"快照 + 回放"**:`session.json` + `artifacts/` + 一个 `onion replay <seq>` 就能复现任意时刻,比 MetaGPT 重新跑整个公司轻。
3. **跨会话引用**:`session-A` 完成的工作可以作为 `session-B` 的 `context_from: session-A@seq-42`,MetaGPT 没有等价物。

## 5. 不确定 / 未找到

| 项 | 状态 | 备注 |
| --- | --- | --- |
| `use_uid` 是否有外部配置文件覆盖路径? | 未找到。`grep -r use_uid metagpt/` 仅在 `workspace_config.py` 出现两次,且代码外层 `Config` 也没有把 `use_uid` 写入 yaml schema(只有 `path` 一个字段在 `WorkspaceConfig` 顶层,`use_uid` 似乎定义后从未被 yaml 加载过) | 可能是有意保留的"未来开关" |
| `WorkspaceConfig` 是否在 `config/config2.example.yaml` 中有文档说明? | 否。整个 yaml 里**完全没有 `workspace:` 段**,用户也无需配置;YAML 只负责 LLM/embedding/roles 等 | 用户是隐式接受默认 |
| `--project-name` vs `--project-path` 同时传入时哪个生效? | 看了 `update_via_cli` 实现,两者**都会被 set**,但 `_init_repo` 优先用 `project_path`(`metagpt/actions/prepare_documents.py:42-44`);`project_name` 在 `project_path` 模式下被忽略 | 但 `_rename_workspace` 会在 `WritePRD` 之后把项目重命名,这行为怪,见 `metagpt/actions/write_prd.py:288-294` |
| `metagpt/document_store/` 是不是多 Agent 共享知识库? | **不是**。它是 RAG 向量检索后端(给 `Researcher`、`Searcher` 等角色查资料用),底层是 faiss/chroma/milvus/lancedb/qdrant | 不要被目录名误导;真正的"多 Agent 共享知识库"是 `ProjectRepo` |
| Team 状态(`storage/team/team.json`)和 `session.json` 怎么映射? | 简单回答:MetaGPT 没有任何 session.json 概念,Team 状态是"整个公司一次完整跑",不可拆分 | 这正是 Onion Agent 的切入点 |
| `metagpt/context_mixin.py` 是否也是 workspace 相关? | 已读,只是 `Context` 的一个 mixin,**与 workspace 无关** | 排除 |

---

**总结一句话**:MetaGPT 的工作区是 **"git 仓 + 强结构化目录"** 的硬约束模式 — 每次跑 = 一个新项目,所有产物按角色→子目录的固定 mapping 落到仓里,跨角色通过 `git diff` + `dependency_file` 做增量。对 Onion Agent 来说,**硬约束目录结构是值得抄的,但 git 强依赖、cwd 隐式跟随、配置/工作区分离** 这三处是反例,要在设计上显式矫正。
