# SuperAGI — 工作区(File Backend)调研报告

> 对象: `TransformerOptimus/SuperAGI` (commit: 本地 clone 快照)
> 调研范围: 工作区路径、目录结构、初始化方式
> 调研方式: 静态阅读 clone 快照(只读),重点查看 `superagi/config/`、`superagi/resource_manager/`、`superagi/models/`、`superagi/vector_store/`、`docker-compose*.yaml`、`config_template.yaml`、`entrypoint*.sh`、`migrations/`

---

## 0. 智能体一句话定位

**dev-first 自主 Agent 平台**,带 Web 仪表盘、Agent Marketplace、Tools Marketplace、并发多 Agent 运行 + 监控的 GUI/CLI 双形态企业级 ReAct 框架,围绕"组织 (Organisation) → 项目 (Project) → Agent → AgentExecution → Feed"多租户数据模型运转。

---

## 1. 调研依据

### 1.1 仓库结构概览

```
SuperAGI/
├── main.py                       # FastAPI 后端入口(8001 端口)
├── run.sh / run.bat / run_gui.py / ui.py / cli2.py   # 多套启动脚本
├── test.py                       # CLI 模式 agent 创建脚本
├── config_template.yaml          # 配置模板(用户复制为 config.yaml)
├── alembic.ini                   # DB 迁移工具
├── docker-compose.yaml           # 生产 docker-compose
├── docker-compose-dev.yaml       # 开发 docker-compose
├── Dockerfile / DockerfileCelery / DockerfileRedis
├── entrypoint.sh / entrypoint_celery.sh   # 容器启动脚本
├── requirements.txt
├── tools.json                    # 工具注册表(由 tool_manager.py 维护)
├── superagi/                     # 核心 Python 包
│   ├── config/                   # 配置加载
│   ├── resource_manager/         # 资源/文件管理
│   ├── vector_store/             # 向量库适配
│   ├── models/                   # SQLAlchemy ORM(38 个模型)
│   ├── agent/                    # Agent Loop 核心
│   ├── controllers/              # FastAPI 路由
│   ├── worker.py                 # Celery worker
│   ├── jobs/agent_executor.py    # Agent 执行调度
│   ├── apm/                      # 事件/调用日志
│   ├── lib/logger.py             # 统一 logger
│   ├── types/                    # 枚举(StorageType, VectorStoreType 等)
│   ├── tools/                    # 内置 + 外部 + 集市工具
│   ├── helper/                   # 工具函数
│   └── llms/                     # LLM 适配层
├── migrations/                   # Alembic 迁移
│   └── versions/                 # 40+ 个迁移文件
├── workspace/                    # ★ 运行时工作区(资源/文件)
│   ├── input/.temp/
│   └── output/.temp/
├── gui/                          # Next.js 前端(独立 Docker 服务,3000 端口)
├── nginx/                        # 反向代理(80 → 3000/8001)
├── tgwui/                        # 可选: oobabooga text-generation-webui
├── local-llm / local-llm-gpu     # 本地 LLM docker-compose
├── static/                       # 静态资源
└── tests/                        # 单元测试
```

### 1.2 关键发现摘要

- SuperAGI 是**多服务架构**: PostgreSQL(主库) + Redis(向量库+LTM) + Celery(异步任务调度) + FastAPI(API) + Next.js(GUI) + Nginx(反向代理)。
- **不存在 `~/.superagi/` 用户属主目录**;全部数据走**项目相对路径**(`workspace/`) + **数据库** + **环境变量配置**。
- 配置文件 `config.yaml` 位于**项目根目录**,gitignored,从 `config_template.yaml` 复制而来。
- 工作区目录**不需要显式 init**,但 `workspace/` 已在仓库中预留了 `.temp/` 占位子目录;真正的 agent 目录由运行时**懒加载**。

---

## 2. 三个核心问题的回答

### Q1. 工作区路径:相对 cwd + YAML 模板变量

**答:不写死 `~/.superagi/`;不跟当前目录默认值;路径完全由 `config.yaml` 驱动,默认模板用相对路径。**

#### 2.1.1 配置文件位置

| 项 | 值 | 证据 |
|---|---|---|
| 配置加载入口 | `superagi/config/config.py` | `config.py:11-43` |
| `ROOT_DIR` 计算 | `os.path.dirname(Path(__file__).parent.parent)` | `config.py:38` |
| 配置文件名 | `config.yaml` (常量) | `config.py:7` |
| 加载方式 | 1) 读 `config.yaml`;2) 与 `os.environ` 合并;3) env 覆盖 yaml | `config.py:13-30` |
| 用户首次创建 | 配置文件不存在时自动创建空文件并提示 | `config.py:18-23` |
| 是否 git 跟踪 | **否**,gitignored | `.gitignore:5` `config.yaml` |
| 模板来源 | `config_template.yaml` (已跟踪) | repo root |

**关键代码 `superagi/config/config.py:38-42`:**

```python
ROOT_DIR = os.path.dirname(Path(__file__).parent.parent)
_config_instance = Config(ROOT_DIR + "/" + CONFIG_FILE)

def get_config(key: str, default: str = None) -> str:
    return _config_instance.get_config(key, default)
```

→ 所有 `get_config("XXX")` 调用从 `ROOT_DIR/config.yaml` 读 + 环境变量覆盖。

#### 2.1.2 资源目录(workspace)路径

**关键代码 `config_template.yaml:32-40`:**

```yaml
#STORAGE TYPE ("FILE" or "S3")
STORAGE_TYPE: "FILE"

#TOOLS
TOOLS_DIR: "superagi/tools"

#STORAGE INFO FOR FILES
RESOURCES_INPUT_ROOT_DIR: workspace/input/{agent_id}
RESOURCES_OUTPUT_ROOT_DIR: workspace/output/{agent_id}/{agent_execution_id} # For keeping resources at agent execution level
#RESOURCES_OUTPUT_ROOT_DIR: workspace/output/{agent_id}  # For keeping resources at agent level
```

模板支持**占位符替换**:
- `{agent_id}` → 实际运行时被替换为 `{agent_name}_{agent.id}` (即 `agent_name` 去空格后拼接 `id`)
- `{agent_execution_id}` → 替换为 `{agent_execution_name}_{agent_execution.id}`

**关键代码 `superagi/helper/resource_helper.py:80-90, 99-124`:**

```python
@classmethod
def get_formatted_agent_level_path(cls, agent: Agent, path) -> object:
    formatted_agent_name = agent.name.replace(" ", "")
    return path.replace("{agent_id}", formatted_agent_name + '_' + str(agent.id))

@classmethod
def get_formatted_agent_execution_level_path(cls, agent_execution: AgentExecution, path):
    formatted_agent_execution_name = agent_execution.name.replace(" ", "")
    return path.replace("{agent_execution_id}", (formatted_agent_execution_name + '_' + str(agent_execution.id)))

@classmethod
def get_root_output_dir(cls):
    root_dir = get_config('RESOURCES_OUTPUT_ROOT_DIR')
    if root_dir is not None:
        root_dir = root_dir if root_dir.startswith("/") else os.getcwd() + "/" + root_dir
        root_dir = root_dir if root_dir.endswith("/") else root_dir + "/"
    else:
        root_dir = os.getcwd() + "/"
    return root_dir
```

→ **非绝对路径时,统一用 `os.getcwd()` 拼接**;绝对路径(`/xxx`)时直接使用。

#### 2.1.3 数据库路径

**关键代码 `config_template.yaml:22-28`:**

```yaml
#DATABASE INFO
# redis details
DB_NAME: super_agi_main
DB_HOST: super__postgres
DB_USERNAME: superagi
DB_PASSWORD: password
DB_URL: postgresql://superagi:password@super__postgres:5432/super_agi_main
REDIS_URL: "super__redis:6379"
```

→ PostgreSQL 主机名 `super__postgres` 是 **docker-compose 服务名**,不是 IP/域名。

**关键代码 `superagi/models/db.py:14-28` & `main.py:75-93`:**

```python
db_host = get_config('DB_HOST', 'super__postgres')
db_username = get_config('DB_USERNAME')
db_password = get_config('DB_PASSWORD')
db_name = get_config('DB_NAME')
db_url = get_config('DB_URL', None)
if db_url is None:
    if db_username is None:
        db_url = f'postgresql://{db_host}/{db_name}'
    else:
        db_url = f'postgresql://{db_username}:{db_password}@{db_host}/{db_name}'
```

→ Docker 部署时直接连 `super__postgres:5432`;本地裸跑可通过环境变量覆盖为 `localhost`。

#### 2.1.4 向量库路径

**关键代码 `superagi/resource_manager/llama_vector_store_factory.py:24-50` & `superagi/vector_store/vector_factory.py:62-66`:**

```python
# LlamaIndex 向量库
if self.vector_store_name == VectorStoreType.REDIS:
    redis_url = get_config("REDIS_VECTOR_STORE_URL") or "redis://super__redis:6379"
    ...

# SuperAGI 自有向量库(LTM 用)
if vector_store == VectorStoreType.REDIS:
    index_name = "super-agent-index1"
    redis = Redis(index_name, embedding_model)
    redis.create_index()
    return redis
```

→ 默认走 `redis://super__redis:6379`;可换 Pinecone/Qdrant/Weaviate/Chroma(`config_template.yaml:121-141`)。

#### 2.1.5 Tools 目录

**关键代码 `superagi/agent/tool_builder.py:62-67`:**

```python
tool_paths = ["superagi/tools", "superagi/tools/external_tools", "superagi/tools/marketplace_tools"]
for tool_path in tool_paths:
    if os.path.exists(os.path.join(os.getcwd(), tool_path) + '/' + tool.folder_name):
        tools_dir = tool_path
        break
```

→ Tools 解析时**搜索三个相对路径**(都是 `os.getcwd()` 起跳);Tools 不会安装到 `~/.superagi/`。

#### 2.1.6 路径策略对比表

| 数据维度 | 默认路径 | 来源 | 是否写死 | 是否可自定义 |
|---|---|---|---|---|
| 配置文件 | `config.yaml` (项目根) | `config.py:38` `ROOT_DIR` | 否 | 否(走 ROOT_DIR 硬编码) |
| Input 资源目录 | `workspace/input/{agent_id}/` | `config_template.yaml:38` | 否 | ✅ `RESOURCES_INPUT_ROOT_DIR` |
| Output 资源目录 | `workspace/output/{agent_id}/{agent_execution_id}/` | `config_template.yaml:39` | 否 | ✅ `RESOURCES_OUTPUT_ROOT_DIR` |
| 内置 Tools | `superagi/tools/` | `config_template.yaml:35` `TOOLS_DIR` + `tool_builder.py:62-67` | 否 | ✅ `TOOLS_DIR` |
| 外部 Tools | `superagi/tools/external_tools/{tool_name}/` | `tool_manager.py:117-122` | 相对路径 | ❌ 路径硬编码 |
| Marketplace Tools | `superagi/tools/marketplace_tools/` | `tool_manager.py:113-116` | 相对路径 | ❌ 路径硬编码 |
| PostgreSQL | `super__postgres:5432` (Docker 服务名) | `config_template.yaml:24` `DB_HOST` | 否 | ✅ `DB_URL` / `DB_HOST` |
| Redis (向量库) | `super__redis:6379` (Docker 服务名) | `config_template.yaml:28` + `llama_vector_store_factory.py:24` | 否 | ✅ `REDIS_VECTOR_STORE_URL` |
| LTM 向量索引 | `super-agent-index1` | `vector_factory.py:65` 写死 | **是** | ❌ |
| Resource 向量索引 | `super-agent-index` (默认) | `resource_manager.py:78-79` | 否 | ✅ `RESOURCE_VECTOR_STORE_INDEX_NAME` |
| 临时目录 | `workspace/output/.temp/` 和 `workspace/input/.temp/` | 仓库预置 | 否 | ❌ |
| 用户属主目录 | **不存在** `~/.superagi/` | — | — | — |

---

### Q2. 工作区目录结构:workspace/ + Postgres + Redis + 容器卷

**答:SuperAGI 把"工作区"拆成 4 类物理后端 —— (1) 工作区文件目录 (2) PostgreSQL 元数据 (3) 向量库 (4) Docker 命名卷。**

#### 2.2.1 物理目录树(本地 clone 实测)

```
SuperAGI/
├── workspace/                        # ★ 应用工作区(运行时文件)
│   ├── input/                        # Agent INPUT 资源根
│   │   └── .temp/                    # 临时占位(空,仓库预置)
│   └── output/                       # Agent OUTPUT 资源根
│       ├── .temp/                    # 临时占位(空,仓库预置)
│       └── testing.txt               # 示例残留(只有 "Hello World")
├── config.yaml                       # ★ 用户私有配置(gitignored,本地无)
├── superagi/
│   ├── tools/
│   │   ├── marketplace_tools/        # 集市下载的工具(gitignored)
│   │   └── external_tools/           # 外部工具(gitignored)
│   ├── resource_manager/             # FileManager / ResourceManager 实现
│   ├── vector_store/                 # 6 种向量库适配
│   ├── models/                       # 38 个 SQLAlchemy 模型
│   ├── apm/                          # 事件埋点
│   ├── agent/                        # Agent Loop 核心 + 10 个 prompt 模板
│   ├── controllers/                  # 30+ FastAPI 路由
│   ├── helper/                       # 资源/S3/auth/encryption 等工具
│   ├── jobs/agent_executor.py        # Celery 异步执行
│   ├── worker.py                     # Celery app 配置
│   ├── types/                        # 枚举定义
│   └── lib/logger.py                 # 自定义 logger
├── migrations/versions/              # 40+ Alembic 迁移
├── gui/                              # Next.js 前端
├── nginx/default.conf                # 反向代理
├── tgwui/                            # 可选 text-generation-webui
├── local-llm / local-llm-gpu         # 可选本地 LLM compose
├── static/                           # 静态资源
└── tests/                            # 单元测试
```

#### 2.2.2 Docker Compose 命名卷(`docker-compose.yaml:7-87`)

```yaml
volumes:
  superagi_postgres_data:    # PostgreSQL 数据卷(/var/lib/postgresql/data/)
  redis_data:                # Redis 数据卷(/data/)

services:
  backend:
    volumes:
      - "./:/app"            # 整个项目根挂到容器 /app
  celery:
    volumes:
      - "./:/app"
      - "${EXTERNAL_RESOURCE_DIR:-./workspace}:/app/ext"  # workspace 挂到 /app/ext(可选覆盖)
  super__postgres:
    volumes:
      - superagi_postgres_data:/var/lib/postgresql/data/
  super__redis:
    volumes:
      - redis_data:/data
```

→ **关键发现**:Celery 容器把 `workspace/` 挂到 `/app/ext`,但代码里**没有任何引用 `/app/ext`**;看似是为未来外部化资源预留的钩子,目前**实际资源仍由代码用 `os.getcwd() + workspace/...` 写到 backend 容器里**。

#### 2.2.3 PostgreSQL 数据模型(38 个表)

**关键代码 `superagi/models/` 目录**:38 个 `DBBaseModel` 子类。

核心表(`migrations/versions/44b0d6f2d1b3_init_models.py` 初始化 + 后续迁移):

| 表 | 模型 | 关键字段 | 作用 |
|---|---|---|---|
| `organisations` | `Organisation` | id, name | 多租户顶层 |
| `projects` | `Project` | id, name, organisation_id | 组织下的项目 |
| `agents` | `Agent` | id, name, project_id, description, agent_workflow_id, is_deleted | Agent 定义 |
| `agent_executions` | `AgentExecution` | id, status, name, agent_id, num_of_calls/tokens, current_agent_step_id, current_feed_group_id, last_shown_error_id | 每次 run 实例 |
| `agent_execution_feeds` | `AgentExecutionFeed` | id, agent_execution_id, agent_id, feed (Text), role, extra_info, feed_group_id, error_message | ★ Agent 上下文历史(= Onion 的 session.json 等价物,但存 DB) |
| `agent_configurations` | `AgentConfiguration` | id, agent_id, key, value (Text) | Agent 级 KV 配置(goal/instruction/constraints/tools/model/LTM_DB/memory_window 等) |
| `agent_execution_config` | `AgentExecutionConfiguration` | id, agent_execution_id, key, value | 每次 run 的临时配置 |
| `agent_workflows` | `AgentWorkflow` | id, name, description | 模板级工作流定义 |
| `agent_workflow_steps` | `AgentWorkflowStep` | id, agent_workflow_id, step_type, action_type, action_reference_id, prompt, completion_prompt, history_enabled | 工作流步骤 |
| `iteration_workflows` | `IterationWorkflow` | id, name, description | 内部迭代循环(Goal Based/Task Based/Action Based) |
| `iteration_workflow_steps` | `IterationWorkflowStep` | id, iteration_workflow_id, step_type, prompt | 内部循环步骤 |
| `resources` | `Resource` | id, name, storage_type (FILE/S3), path, size, type, channel (INPUT/OUTPUT), agent_id, agent_execution_id, summary | Agent 资源元数据 |
| `agent_templates` | `AgentTemplate` | id, organisation_id (-1=public), agent_workflow_id, name, description, marketplace_template_id | Agent 模板(可来自 marketplace) |
| `knowledges` | `Knowledges` | id, name, description, vector_db_index_id, organisation_id, contributed_by | 知识库 |
| `vector_dbs` | `Vectordbs` | id, name, db_type, organisation_id | 用户的向量库实例 |
| `vector_db_indices` | `VectorDbIndices` | — | 向量库索引 |
| `vector_db_configs` | `VectorDbConfigs` | — | 向量库连接配置 |
| `toolkits` | `Toolkit` | — | 工具包(可来自 marketplace) |
| `tools` | `Tool` | — | 单个工具 |
| `tool_configs` | `ToolConfig` | id, name, value, toolkit_id | 工具级配置(API key 等) |
| `configurations` | `Configuration` | id, organisation_id, key, value | 组织级配置(可加密的 model_api_key 等) |
| `models` / `models_config` | `Models` / `ModelsConfig` | — | LLM provider 注册 |
| `budgets` | `Budget` | budget, cycle | 预算控制 |
| `users` / `api_key` | `User` / `ApiKey` | — | 用户/API key |
| `oauth_tokens` | `OauthToken` | — | GitHub/Google OAuth |
| `events` | `Event` | event_name, event_value, event_property (JSONB), agent_id, org_id | APM 事件埋点 |
| `agent_execution_permissions` | `AgentExecutionPermission` | — | 工具执行权限审批 |
| `webhooks` / `webhook_events` | `WebHook` / `WebHookEvent` | — | 状态变更回调 |
| `agent_schedules` | `AgentSchedule` | — | 定时任务(Celery beat) |
| `call_logs` | `CallLog` | — | LLM 调用日志 |
| `marketplace_stats` | `MarketplaceStats` | — | 集市使用统计 |

→ **关键判断**:SuperAGI 持久化层**严重依赖 Postgres** —— 上下文历史(feeds)、资源元数据、配置、工作流定义、模板、向量化索引注册、事件日志全部入 DB;**没有任何 "session.json" 这类单文件累加器**。

#### 2.2.4 文件 backend 元数据表

**关键代码 `superagi/models/resource.py:18-39`:**

```python
class Resource(DBBaseModel):
    __tablename__ = 'resources'
    id = Column(Integer, primary_key=True)
    name = Column(String)
    storage_type = Column(String)  # FILESERVER,S3
    path = Column(String)          # need for S3
    size = Column(Integer)
    type = Column(String)          # application/pdf etc
    channel = Column(String)       # INPUT,OUTPUT
    agent_id = Column(Integer)
    agent_execution_id = Column(Integer)
    summary = Column(Text)
```

→ 每个资源文件对应一条 `resources` 记录;`storage_type` 决定物理存储是 `FILE` 还是 `S3`;**资源元数据 + 文件路径**在 Postgres,文件本体在 `workspace/output/{agent}/{exec}/...`。

#### 2.2.5 Tools 三层目录

| 层级 | 路径 | 来源 | gitignore |
|---|---|---|---|
| 内置 Tools | `superagi/tools/{toolkit}/` | 仓库自带 19 个 toolkit | 否(已跟踪) |
| 外部 Tools | `superagi/tools/external_tools/{tool_name}/` | `tool_manager.py:118-122` 从 GitHub 任意 URL 下载 | 是 |
| Marketplace Tools | `superagi/tools/marketplace_tools/` | `tool_manager.py:113-116` 从 `TransformerOptimus/SuperAGI-Tools` 下载 | 是 |

**关键代码 `superagi/tool_manager.py:113-126`:**

```python
for tool_name, tool_url in tools_config.items():
    if is_marketplace_url(tool_url):
        tool_folder = os.path.join("superagi/tools/marketplace_tools")
        if not os.path.exists(tool_folder):
            os.makedirs(tool_folder)
        download_marketplace_tool(tool_url, tool_folder)
    else:
        tool_folder = os.path.join("superagi/tools/external_tools", tool_name)
        if not os.path.exists(tool_folder):
            os.makedirs(tool_folder)
        download_tool(tool_url, tool_folder)
```

#### 2.2.6 日志 / 运行历史

- **不写文件** —— `superagi/lib/logger.py` 全部走 `logging.StreamHandler` 输出到 stdout/stderr(容器里就是 docker logs)。
- **Agent run history** 在 `agent_executions` + `agent_execution_feeds` 表里,前端通过 REST API 拉取(`controllers/agent_execution.py` + `controllers/agent_execution_feed.py`)。
- **APM 事件** 走 `events` 表(JSONB),`superagi/apm/event_handler.py`。

#### 2.2.7 前端工作区

**关键代码 `gui/pages/_app.js:66-69` & `utils/utils.js:240-280`:**

```javascript
const toolkitName = localStorage.getItem('toolkit_to_install') || null;
const agentTemplateId = localStorage.getItem('agent_to_install') || null;
const knowledgeTemplateName = localStorage.getItem('knowledge_to_install') || null;
// ...还有 20+ 个 localStorage 项(agi_internal_ids, agent_name_*, agent_goals_* 等表单草稿)
```

→ 前端**只把表单草稿、临时选择放到浏览器 localStorage**;**业务数据全走后端 API + Postgres**,不存 IndexedDB / localStorage。

---

### Q3. 工作区创建:不显式 init,全部隐式 + 容器启动钩子

**答:不存在 `superagi init` 命令;workspace/ 目录结构在仓库预置 `.temp/` 占位;真正的 agent 目录由 FileManager 运行时懒加载;数据库表由 Alembic 容器启动时自动迁移。**

#### 2.3.1 启动流程时间线

| 阶段 | 动作 | 触发位置 |
|---|---|---|
| 1. 仓库克隆 | 已有空 `workspace/input/.temp/` + `workspace/output/.temp/` | 仓库预置 |
| 2. 用户配置 | 复制 `config_template.yaml` → `config.yaml`,填 API key 等 | 用户手动 |
| 3. Docker 启动 | `entrypoint.sh` 在 backend 容器跑 | `docker-compose.yaml:7-15` |
| 4. 工具下载 | `python superagi/tool_manager.py` → 下载 marketplace + external tools | `entrypoint.sh:4` |
| 5. 工具依赖安装 | `./install_tool_dependencies.sh` | `entrypoint.sh:7` |
| 6. **DB 迁移** | `alembic upgrade head` → 创建/升级 40+ 张表 | `entrypoint.sh:10` |
| 7. Web 服务 | `uvicorn main:app --host 0.0.0.0 --port 8001` | `entrypoint.sh:13` |
| 8. 启动钩子 | `main.py` `@app.on_event("startup")` 注册默认组织/项目/工作流/工具 | `main.py:198-260` |
| 9. Celery 启动 | `entrypoint_celery.sh` 启 worker + beat | `docker-compose.yaml:16-25` |
| 10. 前端启动 | `gui` 容器跑 `npm run dev` (3000) | `docker-compose.yaml:27-37` |
| 11. 首次创建 Agent | 用户通过 GUI 创建 → 写 `agents`/`agent_configurations` 表 → Celery 调度 `execute_agent` → Agent Loop 调 FileManager → `os.makedirs(workspace/output/...)` 隐式创建 | 运行时 |

#### 2.3.2 显式 vs 隐式

| 数据后端 | 显式 init? | 隐式创建? | 证据 |
|---|---|---|---|
| `workspace/` 目录 | ❌ 无 `superagi init` | ✅ 仓库预置 `.temp/` | `workspace/input/.temp/`(空)、`workspace/output/.temp/`(空) |
| `config.yaml` | ❌ 无 init | ✅ 缺失时自动创建空文件 | `config.py:18-23` |
| `superagi/tools/marketplace_tools/` | ❌ | ✅ `os.makedirs(..., exist_ok=True)` | `tool_manager.py:113-116` |
| `superagi/tools/external_tools/{tool}/` | ❌ | ✅ `os.makedirs(..., exist_ok=True)` | `tool_manager.py:118-122` |
| `workspace/output/{agent_id}/{exec_id}/` | ❌ | ✅ `os.makedirs(directory, exist_ok=True)` | `resource_helper.py:145-146` |
| PostgreSQL 表 | ❌ 无 init | ✅ Alembic 容器启动时自动跑 | `entrypoint.sh:10` `alembic upgrade head` |
| Redis 向量索引 | ❌ | ✅ `redis.create_index()` 首次连接时 | `vector_factory.py:65-66` |
| 临时文件 `.temp` | ❌ | ✅ `tools/file/read_file.py:55` `os.makedirs(directory, exist_ok=True)` | `read_file.py:54-55` |
| 首个 user/org/project | ❌ | ✅ startup_event 注册默认 `super6@agi.com` | `main.py:200-260` |
| 默认 workflows | ❌ | ✅ `IterationWorkflowSeed` / `AgentWorkflowSeed` 启动时种入 | `main.py:233-244` |
| 默认 toolkits | ❌ | ✅ `register_toolkits(session, organisation)` 启动时注册 | `main.py:213-220` |

#### 2.3.3 关键隐式创建代码

**A. 配置文件缺失时(`superagi/config/config.py:13-23`):**

```python
@classmethod
def load_config(cls, config_file: str) -> dict:
    if os.path.exists(config_file):
        with open(config_file, "r") as file:
            config_data = yaml.safe_load(file)
        ...
    else:
        logger.info("\033[91m\033[1m"
            + "\nConfig file not found. Enter required keys and values."
            + "\033[0m\033[0m")
        config_data = {}
        with open(config_file, "w") as file:
            yaml.dump(config_data, file, default_flow_style=False)
```

**B. Agent output 目录懒加载(`superagi/helper/resource_helper.py:140-147`):**

```python
@classmethod
def get_agent_write_resource_path(cls, file_name: str, agent: Agent, agent_execution: AgentExecution):
    root_dir = ResourceHelper.get_root_output_dir()
    if agent is not None and "{agent_id}" in root_dir:
        root_dir = ResourceHelper.get_formatted_agent_level_path(agent, root_dir)
        if agent_execution is not None and "{agent_execution_id}" in root_dir:
            root_dir = ResourceHelper.get_formatted_agent_execution_level_path(agent_execution, root_dir)
        directory = os.path.dirname(root_dir)
        os.makedirs(directory, exist_ok=True)   # ★ 隐式创建
    final_path = root_dir + file_name
    return final_path
```

**C. DB 迁移在容器启动时自动跑(`entrypoint.sh`):**

```bash
#!/bin/bash
python superagi/tool_manager.py
./install_tool_dependencies.sh
alembic upgrade head                # ★ 容器每次启动都会跑(幂等)
exec uvicorn main:app --host 0.0.0.0 --port 8001 --reload
```

**D. 启动时种入默认数据(`main.py:198-260`):**

```python
@app.on_event("startup")
async def startup_event():
    ...
    default_user = session.query(User).filter(User.email == "super6@agi.com").first()
    if default_user is not None:
        organisation = session.query(Organisation).filter_by(id=default_user.organisation_id).first()
        register_toolkits(session, organisation)

    IterationWorkflowSeed.build_single_step_agent(session)
    IterationWorkflowSeed.build_task_based_agents(session)
    ...
    AgentWorkflowSeed.build_goal_based_agent(session)
    ...
    register_toolkit_for_all_organisation()
```

→ 容器第一次启动时会**自动建表 + 自动注入默认 user (super6@agi.com) + 默认 organisation + 5 套 iteration workflows + 6 套 agent workflows + 19 个内置 toolkits**;用户打开 `http://localhost:3000` 即可登录使用。

#### 2.3.4 vs Onion Agent 的对照

| 维度 | SuperAGI | Onion Agent (待对齐) |
|---|---|---|
| 用户属主目录 | ❌ 不用 | ❌ 不用 |
| 显式 init | ❌ | 待定 |
| 配置文件 | `config.yaml` 仓库根 + env | 同样思路可行 |
| 上下文历史 | **Postgres `agent_execution_feeds` 表** (DB row 累加) | `session.json` 单文件累加 |
| 资源元数据 | **Postgres `resources` 表** | 单文件内嵌 / 旁挂 JSONL |
| 资源本体 | `workspace/output/{agent}/{exec}/...` | 同样思路 |
| 模板/工作流 | **Postgres** 5 套 iteration + 6 套 agent | 文件化更友好(信创) |
| Tool 库 | `superagi/tools/` + 下载的 marketplace/external | 类似思路 |
| 日志 | stdout + 容器 | 同样思路 |
| 多租户 | `organisations → projects → agents` 强模型 | 简化掉 |
| Vector DB | Postgres + Redis(可换 Pinecone/Qdrant 等) | 同样思路 |
| LTM 记忆 | `agent_execution_feeds` (短期) + 向量库 (长期) | 三层 namespace 思路 |
| Celery 任务队列 | ✅ 异步 agent 调度 + beat 定时 | 可选(信创内网可能不需要) |

---

## 3. 关键代码片段

### 3.1 配置加载(Pydantic Settings)

**`superagi/config/config.py:11-43`:**

```python
class Config(BaseSettings):
    class Config:
        env_file_encoding = "utf-8"
        extra = "allow"  # Allow extra fields

    @classmethod
    def load_config(cls, config_file: str) -> dict:
        if os.path.exists(config_file):
            with open(config_file, "r") as file:
                config_data = yaml.safe_load(file)
            if config_data is None:
                config_data = {}
        else:
            logger.info("\033[91m\033[1m" + "\nConfig file not found. ..." + "\033[0m\033[0m")
            config_data = {}
            with open(config_file, "w") as file:
                yaml.dump(config_data, file, default_flow_style=False)
        env_vars = dict(os.environ)
        config_data = {**config_data, **env_vars}    # ★ env 覆盖 yaml
        return config_data
```

→ 优先级:**环境变量 > config.yaml > 代码默认值**。

### 3.2 资源路径生成

**`superagi/helper/resource_helper.py:80-124`:**

```python
@classmethod
def get_formatted_agent_level_path(cls, agent: Agent, path) -> object:
    formatted_agent_name = agent.name.replace(" ", "")
    return path.replace("{agent_id}", formatted_agent_name + '_' + str(agent.id))

@classmethod
def get_formatted_agent_execution_level_path(cls, agent_execution: AgentExecution, path):
    formatted_agent_execution_name = agent_execution.name.replace(" ", "")
    return path.replace("{agent_execution_id}", (formatted_agent_execution_name + '_' + str(agent_execution.id)))

@classmethod
def get_root_output_dir(cls):
    root_dir = get_config('RESOURCES_OUTPUT_ROOT_DIR')
    if root_dir is not None:
        root_dir = root_dir if root_dir.startswith("/") else os.getcwd() + "/" + root_dir
        root_dir = root_dir if root_dir.endswith("/") else root_dir + "/"
    else:
        root_dir = os.getcwd() + "/"
    return root_dir
```

### 3.3 Agent Loop 上下文(feeds 表)

**`superagi/models/agent_execution_feed.py:50-66`:**

```python
@classmethod
def fetch_agent_execution_feeds(cls, session, agent_execution_id: int):
    agent_execution = AgentExecution.find_by_id(session, agent_execution_id)
    agent_feeds = session.query(AgentExecutionFeed.role, AgentExecutionFeed.feed, AgentExecutionFeed.id) \
        .filter(AgentExecutionFeed.agent_execution_id == agent_execution_id,
                AgentExecutionFeed.feed_group_id == agent_execution.current_feed_group_id) \
        .order_by(asc(AgentExecutionFeed.created_at)) \
        .all()
    if agent_execution.current_feed_group_id != "DEFAULT":
        return agent_feeds
    else:
        return agent_feeds[2:]  # 跳过前 2 条 system prompt
```

→ **每次 run 维护一组 feeds(role=system/user/assistant)**,这就是 SuperAGI 的"洋葱芯" —— 但用 `feed_group_id` 实现 memory window / 上下文压缩分组,而不是文件累加器。

### 3.4 FileManager 写入(隐式 mkdir)

**`superagi/resource_manager/file_manager.py:11-21`:**

```python
class FileManager:
    def __init__(self, session: Session, agent_id: int = None, agent_execution_id: int = None):
        self.session = session
        self.agent_id = agent_id
        self.agent_execution_id = agent_execution_id

    def write_binary_file(self, file_name: str, data):
        if self.agent_id is not None:
            final_path = ResourceHelper.get_agent_write_resource_path(file_name, ...)   # 内含 os.makedirs
        else:
            final_path = ResourceHelper.get_resource_path(file_name)
        try:
            with open(final_path, mode="wb") as img:
                img.write(data)
                ...
            self.write_to_s3(file_name, final_path)  # S3 时双写
            return f"Binary {file_name} saved successfully"
        except Exception as err:
            return f"Error write_binary_file: {err}"
```

### 3.5 Celery Worker(异步 Agent Loop)

**`superagi/worker.py:60-80`:**

```python
@app.task(name="execute_agent", autoretry_for=(Exception,), retry_backoff=2, max_retries=5)
def execute_agent(agent_execution_id: int, time):
    """Execute an agent step in background."""
    from superagi.jobs.agent_executor import AgentExecutor
    handle_tools_import()
    logger.info("Execute agent:" + str(time) + "," + str(agent_execution_id))
    AgentExecutor().execute_next_step(agent_execution_id=agent_execution_id)
```

→ **单步异步执行** —— `execute_next_step` 走一步 LLM/tool,然后**写回 `agent_executions.current_agent_step_id`** 由前端或 beat 触发下一步;不是真"循环",是**事件驱动 + 状态机**。

### 3.6 启动钩子种入默认数据

**`main.py:198-260`:**

```python
@app.on_event("startup")
async def startup_event():
    logger.info("Running Startup tasks")
    Session = sessionmaker(bind=engine)
    session = Session()
    default_user = session.query(User).filter(User.email == "super6@agi.com").first()
    if default_user is not None:
        organisation = session.query(Organisation).filter_by(id=default_user.organisation_id).first()
        register_toolkits(session, organisation)
    ...
    IterationWorkflowSeed.build_single_step_agent(session)
    IterationWorkflowSeed.build_task_based_agents(session)
    IterationWorkflowSeed.build_action_based_agents(session)
    IterationWorkflowSeed.build_initialize_task_workflow(session)
    AgentWorkflowSeed.build_goal_based_agent(session)
    AgentWorkflowSeed.build_task_based_agent(session)
    AgentWorkflowSeed.build_fixed_task_based_agent(session)
    AgentWorkflowSeed.build_sales_workflow(session)
    AgentWorkflowSeed.build_recruitment_workflow(session)
    AgentWorkflowSeed.build_coding_workflow(session)
    ...
    register_toolkit_for_all_organisation()
```

---

## 4. 与 Onion Agent 设计的关联

### 4.1 可借鉴的设计点

1. **路径模板化 + 占位符替换**(`{agent_id}` / `{agent_execution_id}`)
   - SuperAGI 用 `pathlib`-like 字符串替换,而不是 jinja 模板,简单粗暴但够用。
   - Onion Agent 可以照搬这套机制,定义 `{session_id}` / `{iteration_id}` / `{branch_id}` 等占位符,让用户配置 `ONION_WORKSPACE_ROOT: onion_workspace/{session_id}`。

2. **配置 + 环境变量优先级**(env > yaml > default)
   - SuperAGI 的 `Config(BaseSettings)` 用 pydantic 的合并 + 手动 `os.environ` 覆盖,既支持文件又支持 12-factor。
   - Onion Agent 信创场景下,可以**优先 env**,因为部署在 K8s/Docker 里 Secret 直接走 env,不需要 yaml 文件。

3. **`STORAGE_TYPE` 抽象层**(FILE vs S3)
   - `superagi/types/storage_types.py` 用 enum 抽象,FileManager 在写本地的同时调 S3Helper 双写,无侵入切换。
   - Onion Agent 如果将来要支持对象存储(信创 NAS / MinIO),可参考这种**"主存 + 镜像存"**模式。

4. **隐式懒创建 + 容器启动时 idempotent init**
   - 没有 init 命令,所有路径 `os.makedirs(..., exist_ok=True)`,容器起来 `alembic upgrade head` 自动建表,种入默认数据。
   - Onion Agent 信创场景应该完全照搬 —— 用户不应该需要手动 init,部署上来 `docker compose up` 就跑起来。

5. **Tools 三层目录**(内置 / 外部 / marketplace)
   - `tool_builder.py` 搜索三个相对路径,运行时按 `tool.folder_name` 动态 import。
   - Onion Agent 如果要做工具市场,可以参考,但**gitignore 外部工具目录**这个细节很关键(避免污染仓库)。

6. **`Configuration` 加密存储**(`helper/encyption_helper.py` + `Configuration.fetch_configuration` 中 `decrypt_data`)
   - LLM API key 在 DB 里加密存;Onion Agent 如果走"配置即文件"模式,可以参考 `ENCRYPTION_KEY` 这个 env var(`config_template.yaml:64`)做对称加密。

7. **APM 事件埋点**(`superagi/apm/event_handler.py` + `events` 表 JSONB)
   - Agent 执行的每一步 LLM/tool 调用都写一条 event,前端可做时序回放。
   - Onion Agent 信创场景如果要做"审计追溯"满足合规,这种结构化事件流是必备的。

### 4.2 应该规避的问题

1. **过度依赖 Postgres(38 张表)**
   - SuperAGI 把所有东西(feeds/resources/templates/workflows/configurations/events)都入 DB,**单文件复盘/迁移/版本控制完全不可能**。
   - 信创场景下 DB 往往是企业既有库(达梦/人大金仓/神舟通用),schema 迁移成本高,且"agent 上下文"这种高吞吐数据不应该进关系库。
   - → **Onion Agent 必须坚持 session.json 单文件累加器哲学**;DB 只存"轻量元数据"(user/project/agent 定义),历史/资源/事件全走文件。

2. **Celery 强依赖 Redis broker + 多 worker 调度**
   - 适合大型平台,但信创内网常常**不允许 Redis / 不允许 Celery 集群**。
   - → Onion Agent MVP 可以走"单进程 + 同步 agent loop",后续再异步化。

3. **`{agent_id}` 用 `name_id` 拼接而非纯 ID**
   - `formatted_agent_name = agent.name.replace(" ", "")` —— 用户改名/重命名会破坏路径,实际非常脆弱。
   - → Onion Agent **只准用纯 UUID/ULID**,绝不允许 name 出现在路径里。

4. **`workspace/{input,output}/` 用相对路径(`os.getcwd()` 拼接)**
   - 不同 cwd 启动会指向不同目录,容易误操作写到错误位置。
   - → Onion Agent 应该**强制要求绝对路径**或**相对项目根**(`Path(__file__).parents[2]`),不允许运行时 cwd 影响。

5. **容器把整个项目根 `./:/app` 挂到容器**
   - 改代码不用重启容器很爽,但**生产环境这样挂载会泄露代码、影响性能**。
   - → Onion Agent 生产部署应该 COPY 而不是挂载。

6. **前后端混合 Docker + 8 个服务**
   - 8 个容器 + 3 个命名卷,启动链长,出错难调试。
   - → Onion Agent 信创场景应该**单二进制/单容器优先**,前端可独立部署。

7. **Marketplace 远程调用硬编码 URL**(`marketplace_url = "https://app.superagi.com/api"`)
   - 大量模型文件里写死 `https://app.superagi.com/api`(`knowledges.py:8` / `vector_dbs.py:8` / `agent_template.py:11`),**国内访问困难 + 单点故障 + 厂商绑定**。
   - → Onion Agent **绝不允许硬编码云端 URL**,所有外部依赖走用户配置。

8. **没有 "session" 概念,只有 "run"**
   - `agent_execution` 是一次性 run,没有跨 run 的状态恢复(session resume);context 全靠 `feed_group_id` 切片。
   - → Onion Agent 的 `session.json` 自动累加器天然支持断点续传 / 中断恢复 / 跨进程接力,这是 SuperAGI 缺少的关键能力。

### 4.3 信创场景适配建议

| SuperAGI 组件 | 信创替代方案 |
|---|---|
| PostgreSQL | 达梦 DM / 人大金仓 KingbaseES / 神舟通用 OSCAR;或**完全去掉,只走文件** |
| Redis (向量库) | 信创无 Redis → 走 Chroma 嵌入式 / LanceDB 文件向量库 / 自建 Faiss 索引文件 |
| Celery + Redis broker | 去掉;Onion Agent 同步 agent loop 即可 |
| `app.superagi.com` Marketplace | 全部去掉,只保留"内置 toolkits + 用户本地工具目录" |
| Nginx + 多容器编排 | 去掉;单进程 FastAPI + 静态前端文件 + 1 反代即可 |
| `pip install` 大量依赖 | 收敛到最小依赖集(llama-index / openai / sqlalchemy 可选) |

---

## 5. 不确定 / 未找到

1. **workspace 目录的运行时创建日志** —— 没看到 `os.mkdir(workspace)` 之类的显式调用,只看到 `os.makedirs(directory, exist_ok=True)` 隐式创建(在 `resource_helper.py:145-146` 和 `tool_manager.py:113-122`)。如果用户**手动删掉整个 workspace/ 目录**,第一次创建 Agent 时才会被重建 —— 这个行为没看到测试覆盖。

2. **`EXTERNAL_RESOURCE_DIR` 环境变量** —— `docker-compose.yaml:22` 把 `${EXTERNAL_RESOURCE_DIR:-./workspace}:/app/ext` 挂到 Celery 容器,但**代码里完全没有引用 `/app/ext`**;这个卷似乎是为未来预留,目前是死配置。

3. **`superagi_postgres_data` 卷在容器外** —— Docker 命名卷,不在 `./workspace` 树里;本地 clone 看不到 DB 实际内容。

4. **`LTM_DB` 在 agent_configurations 表里**(`test.py:78` `"LTM_DB": "Pinecone"`) —— 默认值是 Pinecone 而非 Redis,但实际启动时 `vector_factory.py:62-66` 走 `Redis` 分支,可能是个**遗留 bug** 或配置覆盖逻辑没理清楚。

5. **`workspace/output/.temp/` 和 `workspace/input/.temp/` 的 `.temp` 文件夹** —— 仓库预置但是空的,没看到任何代码**写到这里**;可能 `ListFilesTool` / `ReadFileTool` 处理临时下载时用,但要进一步追。

6. **多 Agent 并发跑同一 workspace** —— SuperAGI 通过 `{agent_id}` 路径隔离,但 Celery worker `worker_concurrency=10`(`worker.py:24`)下同一 agent 的多次 execution 会竞争 `current_agent_step_id`,没看到分布式锁 —— 可能在 `assign_next_step_id` 里有数据库行锁,但没仔细验证。

7. **Marketplace 工具版本管理** —— `tools.json` 被 `.gitignore` (`/tools.json`),所以 `tool_manager.py` 会**自动重写**这个文件;用户对 tools.json 的本地修改会被覆盖。

8. **`config_template.yaml` 与 `config.yaml` 同步** —— 没有 `superagi config-template-update` 之类的命令;用户手动 diff。

---

## 附:核心文件行号速查

| 文件 | 行 | 关键内容 |
|---|---|---|
| `superagi/config/config.py:38` | ROOT_DIR 路径计算 |
| `superagi/config/config.py:13-30` | 配置加载(env 覆盖 yaml) |
| `config_template.yaml:32-40` | STORAGE_TYPE / RESOURCES 路径模板 |
| `config_template.yaml:22-28` | DB / Redis 连接配置 |
| `config_template.yaml:64` | ENCRYPTION_KEY |
| `config_template.yaml:121-141` | 向量库配置(Pinecone/Qdrant/Chroma) |
| `superagi/helper/resource_helper.py:80-90` | agent_id / agent_execution_id 路径格式化 |
| `superagi/helper/resource_helper.py:99-124` | get_root_output_dir / get_root_input_dir |
| `superagi/helper/resource_helper.py:140-147` | get_agent_write_resource_path (含 os.makedirs) |
| `superagi/resource_manager/file_manager.py:11-21` | FileManager 类签名 |
| `superagi/resource_manager/llama_vector_store_factory.py:24-50` | 向量库工厂(Redis/Pinecone/Chroma/Qdrant) |
| `superagi/vector_store/vector_factory.py:62-66` | LTM Redis 索引默认名 super-agent-index1 |
| `superagi/models/agent_execution_feed.py:50-66` | fetch_agent_execution_feeds (上下文历史读) |
| `superagi/models/resource.py:18-39` | Resource 模型 (storage_type FILE/S3) |
| `superagi/models/base_model.py:1-15` | DBBaseModel (created_at/updated_at 基类) |
| `superagi/types/storage_types.py:1-15` | StorageType 枚举 |
| `superagi/types/vector_store_types.py:1-15` | VectorStoreType 枚举 |
| `superagi/tool_manager.py:113-126` | download_and_extract_tools 三层目录 |
| `superagi/agent/tool_builder.py:62-67` | Tools 路径搜索三个相对目录 |
| `superagi/worker.py:60-80` | Celery execute_agent task |
| `main.py:75-93` | DB engine 创建 |
| `main.py:198-260` | startup_event 种入默认数据 |
| `entrypoint.sh:4-13` | 容器启动流程(tool download → migrate → uvicorn) |
| `docker-compose.yaml:7-37` | 多服务编排 + 命名卷 |
| `docker-compose.yaml:22` | EXTERNAL_RESOURCE_DIR 占位(目前未用) |
| `nginx/default.conf:1-30` | 反代 80 → 3000(gui) / /api → 8001(backend) |
| `migrations/versions/44b0d6f2d1b3_init_models.py` | 初始 schema(20+ 表) |
| `alembic.ini:23` | sqlalchemy.url = postgresql://superagi:password@super__postgres:5432/super_agi_main |
| `.dockerignore:1-19` | Docker 上下文白名单(migrations/nginx/superagi/tgwui/tools/workspace/main.py/...) |
| `.gitignore:5,27-30` | config.yaml / workspace/output / workspace/input / tools.json / marketplace_tools / external_tools 都 ignore |
| `gui/pages/_app.js:66-69` | localStorage 表单草稿 |
| `gui/utils/utils.js:240-280` | localStorage 工具函数 |
