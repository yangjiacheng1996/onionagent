# OpenHands — 工作区（File Backend）调研报告

> 调研对象：`All-Hands-AI/OpenHands`（原 OpenDevin，2026 年的 "Agent Canvas"）
> 调研日期：2026-07
> 调研范围：`openhands/app_server/`（V1 主体）、`openhands/server/`（已 deprecated 的 V0 兼容层）、`containers/`、`docker-compose.yml`、`config.template.toml`、`enterprise/server/sharing/`

---

## 0. 智能体一句话定位

OpenHands（原 OpenDevin，Devin 复刻项目）是一个 **自主软件工程 Agent**——在隔离的 Docker / 远程沙箱里执行代码、修改文件、跑测试、提交 PR。它有两套并存的运行时架构：

- **V0（legacy，已冻结）**：单进程 + 直接 `localhost` 跑 sandbox，用 `WORKSPACE_BASE` / `WORKSPACE_MOUNT_PATH` 挂载宿主机目录到 `/workspace`。
- **V1（当前主线 / "Agent Canvas"）**：App Server + 独立 agent-server 进程（Docker / remote / process），用 `persistence_dir`（`~/.openhands`）+ `sandbox_spec.working_dir`（`/workspace/project`）解耦"控制平面持久化"和"runtime workspace"。

---

## 1. 调研依据

| 维度 | 关键文件 |
|---|---|
| 持久化根目录解析 | `openhands/app_server/config.py:75-89` `get_default_persistence_dir()` |
| FileStore 抽象与四种实现 | `openhands/app_server/file_store/files.py`、`local.py`、`memory.py`、`s3.py`、`google_cloud.py`、`__init__.py` |
| 事件服务（按用户/对话分目录） | `openhands/app_server/event/filesystem_event_service.py`、`event_service_base.py:66-82` `get_conversation_path()` |
| 对话路径 helper | `openhands/app_server/conversation_paths.py` |
| AppConversation 标签（workspace path pinning） | `openhands/app_server/app_conversation/app_conversation_models.py:39-42` `ARCHIVE_WORKSPACE_PATH_TAG_KEY` |
| SandboxSpec 默认 working_dir / 环境变量 | `openhands/app_server/sandbox/docker_sandbox_spec_service.py:34-51`、`remote_sandbox_spec_service.py:21-39`、`process_sandbox_spec_service.py:18-34` |
| Sandbox 启动（Docker） | `openhands/app_server/sandbox/docker_sandbox_service.py:385-516` `start_sandbox()` |
| Sandbox 启动（process 模式） | `openhands/app_server/sandbox/process_sandbox_service.py:83-110` `_create_sandbox_directory()` |
| Sandbox 启动（remote 模式） | `openhands/app_server/sandbox/remote_sandbox_service.py` |
| 工作区分组（grouping）策略 | `openhands/app_server/settings/settings_models.py:609-633` `SandboxGroupingStrategy` / `grouped_workspace_dir()` |
| 创建对话时组装 working_dir | `openhands/app_server/app_conversation/live_status_app_conversation_service.py:462-498` |
| Project 根解析（`{working_dir}/{repo_name}`） | `openhands/app_server/app_conversation/app_conversation_service_base.py:55-83` `get_project_dir()` |
| 启动时 git init（空 workspace） | `openhands/app_server/app_conversation/app_conversation_service_base.py:342-395` `clone_or_init_git_repo()`、`live_status_app_conversation_service.py:2749-2751` |
| Workspace archive（删除前） | `openhands/app_server/sandbox/workspace_archive.py:355-490` `archive_workspace()` |
| 容器构建与卷挂载 | `containers/app/Dockerfile:45-69`、`containers/app/entrypoint.sh:21-23`、`docker-compose.yml:8-23`、`containers/dev/compose.yml:14-26` |
| 设置存储（File / SaaS） | `openhands/app_server/settings/file_settings_store.py:13-65`、enterprise 版 `enterprise/storage/saas_settings_store.py` |
| 全局技能 / 用户技能 | `openhands/app_server/user/skills_router.py:33-34` `GLOBAL_SKILLS_DIR`、`USER_SKILLS_DIR` |
| 前端默认上传/读取路径 | `frontend/src/api/conversation-service/v1-conversation-service.api.ts:324,333,422,427`、`frontend/src/utils/get-git-path.ts` |
| `.openhands-state`（企业版保留） | `enterprise/enterprise_local/README.md:203,236` |

---

## 2. 三个核心问题的回答

### Q1. 工作区路径怎么决定？

**结论：双层路径设计**

1. **控制平面持久化（persistence_dir）**——`~/.openhands/`（可由环境变量覆盖）。存的是 app-server 的元数据、对话事件、设置、加密密钥。
2. **运行时工作区（runtime workspace）**——`/workspace/project`（V1 默认，可由 `sandbox_spec.working_dir` 改写）。这是真正被 agent 读写代码的目录，存在 sandbox 容器里。

控制平面的 `persistence_dir` **不**是用户/对话的"工作区"——它是 OpenHands 自己管理会话状态、事件、文件存储的"数据库等价物"。

| 层级 | 路径 | 由谁决定 | 谁来读/写 |
|---|---|---|---|
| 控制平面（host / app-server） | `~/.openhands` | `OH_PERSISTENCE_DIR` > `FILE_STORE_PATH` > `~/.openhands` | app-server 本地存事件 JSON、设置、SQLite、加密密钥 |
| 运行时 workspace（sandbox 容器内） | `/workspace/project`（默认） | `SandboxSpecInfo.working_dir`（来自 `docker_sandbox_spec_service.py:50`、`remote_sandbox_spec_service.py:35`） | agent 在沙箱内执行 shell / 编辑文件 |
| Grouping 后的子目录 | `{working_dir}/{conversation_id_hex}` | `Settings.sandbox_grouping_strategy` ≠ `NO_GROUPING` 时启用 | 让一个 sandbox 跑多个对话时互不污染 |
| 宿主机用户项目目录（V0 / CLI） | `$WORKSPACE_BASE` | `containers/app/entrypoint.sh:21` 通过 env 注入 | legacy V0 模式下挂到 `/opt/workspace_base` |

#### 1.1 路径决定代码（关键证据）

```python
# openhands/app_server/config.py:75-89
def get_default_persistence_dir() -> Path:
    persistence_dir = os.getenv('OH_PERSISTENCE_DIR')
    if persistence_dir is None:
        persistence_dir = os.getenv('FILE_STORE_PATH')        # V0 legacy fallback
    if persistence_dir:
        result = Path(persistence_dir)
    else:
        result = Path.home() / '.openhands'                    # ★ 主机属主默认
    result.mkdir(parents=True, exist_ok=True)                  # ★ 隐式创建
    return result
```

```python
# openhands/app_server/sandbox/sandbox_spec_models.py:15-19
class SandboxSpecInfo(BaseModel):
    id: str
    command: list[str] | None
    initial_env: dict[str, str] = Field(default_factory=dict)
    working_dir: str = '/home/openhands/workspace'              # ★ 沙箱内默认 working_dir
```

```python
# openhands/app_server/sandbox/docker_sandbox_spec_service.py:34-51  (V1 默认值)
def get_default_sandbox_specs():
    return [
        SandboxSpecInfo(
            id=get_agent_server_image(),
            command=['--port', '8000'],
            initial_env={
                'OPENVSCODE_SERVER_ROOT': '/openhands/.openvscode-server',
                'OH_ENABLE_VNC': '0',
                'LOG_JSON': 'true',
                'OH_CONVERSATIONS_PATH': '/workspace/conversations',  # 事件在沙箱内
                'OH_BASH_EVENTS_DIR': '/workspace/bash_events',       # bash 事件
                'PYTHONUNBUFFERED': '1',
                'ENV_LOG_LEVEL': '20',
                **get_agent_server_env(),
            },
            working_dir='/workspace/project',                         # ★ V1 实际默认
        )
    ]
```

> 注意到 `SandboxSpecInfo` 字段的默认是 `/home/openhands/workspace`（`sandbox_spec_models.py:18`），但 V1 的 docker / remote spec service 都把它显式覆写成 `/workspace/project`。这个不一致是历史包袱——V0 用 `openhands` 用户的 home，V1 用统一的 `/workspace/project`。

#### 1.2 容器层如何把工作区挂进去

```bash
# containers/app/Dockerfile:45, 50, 52
ENV WORKSPACE_BASE=/opt/workspace_base      # 容器内路径
ENV INIT_GIT_IN_EMPTY_WORKSPACE=1
RUN mkdir -p $WORKSPACE_BASE
```

```yaml
# docker-compose.yml:13-23
environment:
  - WORKSPACE_MOUNT_PATH=${WORKSPACE_BASE:-$PWD/workspace}    # 注入给 agent-server
volumes:
  - ${WORKSPACE_BASE:-$PWD/workspace}:/opt/workspace_base   # 挂载点
```

```bash
# containers/app/entrypoint.sh:21-24  —— 重要的"取消挂载"逻辑
if [ -z "$WORKSPACE_MOUNT_PATH" ]; then
  # 用户不挂载时，主动 unset WORKSPACE_BASE，否则 OpenHands 会尝试挂一个不存在的目录
  unset WORKSPACE_BASE
fi
```

> 这段注释说明了：V0 设计上"工作区必须存在 + 必须挂载"，V1 已不需要 host 挂载（因为工作区是 sandbox 容器内 `/workspace/project`）。

#### 1.3 Grouping（多对话共享 sandbox）

```python
# openhands/app_server/settings/settings_models.py:619-633
def grouped_workspace_dir(
    base_working_dir: str,
    grouping_strategy: SandboxGroupingStrategy,
    conversation_id_hex: str,
) -> str:
    if grouping_strategy == SandboxGroupingStrategy.NO_GROUPING:
        return base_working_dir                          # 直接 = /workspace/project
    return f'{base_working_dir}/{conversation_id_hex}'   # /workspace/project/{conv_id}
```

```python
# openhands/app_server/app_conversation/live_status_app_conversation_service.py:467-481
sandbox_grouping_strategy = await self._get_sandbox_grouping_strategy()
working_dir = grouped_workspace_dir(
    sandbox_spec.working_dir,
    sandbox_grouping_strategy,
    conversation_id.hex,
)
remote_workspace = AsyncRemoteWorkspace(
    host=agent_server_url,
    api_key=sandbox.session_api_key,
    working_dir=working_dir,
)
```

#### 1.4 选择题答案

| 问题 | 答案 |
|---|---|
| 写死用户属主目录（`~/.openhands`、`~/Documents/openhands`）？ | **控制平面是**（`~/.openhands` 默认）。**运行时工作区不是**——它在沙箱里。 |
| 支持自定义路径？ | **是**：`OH_PERSISTENCE_DIR`（V1 新）/ `FILE_STORE_PATH`（V0 兼容）/ `WORKSPACE_BASE`（V0 CLI） |
| 跟随当前目录（默认）？ | **部分**：控制平面是固定 `~/.openhands`（除非 env 覆盖）；运行时工作区是沙箱内固定 `/workspace/project`（除非 sandbox_spec 改写） |
| `SANDBOX_USER` / `SANDBOX_USER_ID`？ | 来自 `containers/app/Dockerfile:47`：`ENV SANDBOX_USER_ID=0`（默认 root）。当 `SANDBOX_USER_ID != 0` 时，`containers/app/entrypoint.sh:38-65` 会在容器里 `useradd -l -m -u $SANDBOX_USER_ID enduser` 并 `su enduser` 运行 |
| `WORKSPACE_MOUNT_PATH`？ | 仅 V0 / CLI docker 部署：`docker-compose.yml:13` 通过 `WORKSPACE_BASE` 注入；V1 不再用 |

---

### Q2. 工作区目录结构

OpenHands 的"工作区"实际上由**两块不同语义的存储**组成，在调研时需要分开看：

#### 2.1 控制平面：`persistence_dir`（默认 `~/.openhands`）

来源：`openhands/app_server/config.py:75-89`、`openhands/app_server/file_store/local.py:14-17`、`openhands/app_server/event/event_service_base.py:66-82`、`openhands/app_server/services/db_session_injector.py:202`、`openhands/app_server/utils/encryption_key.py:50-56`

```
~/.openhands/                                  # OH_PERSISTENCE_DIR / FILE_STORE_PATH
├── settings.json                              # FileSettingsStore: 用户设置 (file_settings_store.py:15)
├── .keys                                      # 加密密钥 (encryption_key.py:50)
├── .jwt_secret                                # JWT secret 兜底 (encryption_key.py:57)
├── openhands.db                               # SQLite (V0 兼容 / 默认存储；V1 走 Postgres)
│
├── {user_id}/                                 # ── 用户隔离
│   └── v1_conversations/                      # ── conversation_paths.py:11
│       └── {conversation_id_hex}/             #     V1_CONVERSATIONS_DIR + conv.hex
│           ├── {event_id_1}.json              #     事件 1
│           ├── {event_id_2}.json              #     事件 2
│           └── ...                            #     (filesystem_event_service.py 写入)
│
├── microagents/                               # USER_SKILLS_DIR = ~/.openhands/microagents
│   └── *.md                                   # 用户级 skills/microagents (skills_router.py:34)
│
└── workspace-archives/                        # 默认: workspace_archive.py:131  RUNTIME_FILE_ARCHIVE_PREFIX
    └── {sandbox_id}/
        └── {conversation_id}/
            └── {YYYYMMDDTHHMMSSZ}.patch       # git-delta 归档
            └── {YYYYMMDDTHHMMSSZ}.patch.manifest.json
            └── {YYYYMMDDTHHMMSSZ}.tar.gz      # 完整归档
            └── {YYYYMMDDTHHMMSSZ}.tar.gz.manifest.json
```

> **注**：当用 S3 / GCS 模式时，`FileStore` 后端会把同样的目录结构平铺到 bucket 里（`file_store/s3.py`、`file_store/google_cloud.py`）。`AwsEventService` 显式从 `Path('users')` 开始前缀（`event/aws_event_service.py:96`），所以 S3 模式等价于 `s3://bucket/users/{user_id}/v1_conversations/...`。

#### 2.2 运行时工作区：sandbox 容器内 `/workspace/project`（默认）

来源：`docker_sandbox_spec_service.py:34-51`、`live_status_app_conversation_service.py:1144-1162`、`app_conversation_service_base.py:55-83`

```
/workspace/                                    # 沙箱内根 (Dockerfile WORKDIR=app，但 sandbox 用 /workspace)
├── project/                                   # ← working_dir 根
│   ├── (空时)                                 # 若 init_git_in_empty_workspace=True → git init
│   ├── <repo_name>/                           # selected_repository 选中时 → git clone --depth 1
│   ├── .openhands/
│   │   ├── setup.sh                           # 项目级 setup (live_status_..._service.py:278)
│   │   ├── pre-commit.sh                      # pre-commit hook
│   │   ├── skills/                            # 仓库级 V1 skills
│   │   └── microagents/                       # 仓库级 V0 microagents (V1 也兼容)
│   └── .agents_tmp/PLAN.md                    # 规划 agent 的 PLAN (live_status_..._service.py:1156-1162)
│
├── conversations/                             # OH_CONVERSATIONS_PATH
│   └── {conversation_id_hex}/                 # agent-server 写入
│       └── *.json                             # 事件
│
├── bash_events/                               # OH_BASH_EVENTS_DIR
│   └── {conversation_id_hex}/
│       └── *.json
│
└── ... 用户实际编辑的代码、依赖、运行产物
```

| 子目录/文件 | 来源 | 用途 |
|---|---|---|
| `/workspace/project/` | `SandboxSpecInfo.working_dir` | agent 工作目录（默认） |
| `/workspace/project/<repo_name>/` | `get_project_dir()` (`app_conversation_service_base.py:78`) | 选中 repo 时，git clone 到这里 |
| `/workspace/project/.openhands/setup.sh` | `live_status_app_conversation_service.py:281-285` | 项目级 setup（如果存在） |
| `/workspace/conversations/` | `docker_sandbox_spec_service.py:44` | agent-server 把 V1 事件流写到这里 |
| `/workspace/bash_events/` | `docker_sandbox_spec_service.py:45` | agent-server bash 命令事件流 |
| `/workspace/project/.agents_tmp/PLAN.md` | `live_status_app_conversation_service.py:1162` | planning-agent 的计划文件 |

> **关键点**：运行时工作区**不在 `~/.openhands` 里**。它活在 sandbox 容器里，容器被销毁时也一起没了。删除 sandbox 之前，OpenHands Cloud 模式会通过 `workspace_archive.py` 把工作区打成 tar.gz 推到对象存储（仅当 `RUNTIME_FILE_ARCHIVE_ENABLED=true`，默认关闭）。

#### 2.3 全局配置 / 设置存储

```python
# openhands/app_server/settings/file_settings_store.py:13-65
class FileSettingsStore(SettingsStore):
    file_store: FileStore
    path: str = 'settings.json'                  # 在 file_store 里的固定文件名

    async def load(self) -> Settings | None:
        json_str = await call_sync_from_async(self.file_store.read, self.path)
        ...
    async def store(self, settings: Settings) -> None:
        json_str = settings.model_dump_json(...)
        await call_sync_from_async(self.file_store.write, self.path, json_str)
```

> 也就是说 V1 OSS 模式下，**整个 app-server 的"用户设置"只是一个 JSON 文件**，没有数据库 schema。SaaS 模式用 `SaasSettingsStore` 改走 `conversation_metadata` / `org_member` SQL 表（`enterprise/storage/saas_settings_store.py`）。

#### 2.4 plugins / microagents / skills

| 类别 | 路径 | 作用域 | 来源 |
|---|---|---|---|
| 全局 skills（仓库自带） | `<repo>/skills/*.md`（打包进 `openhands` 包） | 所有用户 | `skills_router.py:33` `GLOBAL_SKILLS_DIR = Path(openhands.__file__).parent.parent / 'skills'` |
| 用户级 skills | `~/.openhands/microagents/*.md` | 当前用户所有对话 | `skills_router.py:34` `USER_SKILLS_DIR = Path.home() / '.openhands' / 'microagents'` |
| 仓库级 skills（V1） | `{repo}/.openhands/skills/*.md` | 该仓库 | 随 git clone 进来 |
| 仓库级 microagents（V0 兼容） | `{repo}/.openhands/microagents/*.md` | 该仓库 | 同上，V1 兼容读取 |
| Marketplaces | 通过 `git clone <url>` 临时克隆 | 用户级，按 `MarketplaceRegistration.source` 解析 | `skill_loader.py`、`skills_router.py:215+` |
| Hooks | `{repo}/.openhands/hooks.json` | 该仓库 | `app_conversation/hook_loader.py` |

> **注意**：OpenHands 12-15 改过命名——V0 叫 "microagents"，V1 改叫 "skills"；但**底下的目录布局完全一样**（V1 同时支持 `.openhands/microagents/` 和 `.openhands/skills/`，见 `skills/README.md:54-66`）。这是 V0 → V1 迁移期的兼容策略。

#### 2.5 文件系统操作路径

OpenHands 的"文件操作"有两种路径：

1. **App-server 端（管理控制平面）**——`FileStore` 抽象（`app_server/file_store/files.py`）：
   - `LocalFileStore`（`local.py:9-78`）：`write` / `write_from_path`（**先写临时文件再 atomic rename + fsync**，并发安全）、`read` / `list` / `delete`；`~` 自动 expand
   - `S3FileStore`（`s3.py:23+`）
   - `GoogleCloudFileStore`（`google_cloud.py:13+`）
   - `InMemoryFileStore`（`memory.py`，**仅文本**，二进制会 corrupt）
   - 选择由 `OH_FILE_STORE`（V0）/`OH_FILE_STORE_KIND`（V1）通过 `DiscriminatedUnionMixin` 决定（`file_store/__init__.py:7-23`）

2. **Agent-server 端（沙箱里执行用户任务）**——`AsyncRemoteWorkspace`，调用方：
   - 文件下载：`app_conversation_router.py:1182-1188` `remote_workspace.file_download(source_path, destination_path)`
   - 文件上传：前端 → `v1-conversation-service.api.ts:329-347` → `POST /api/file/upload?path=...`
   - Bash 执行：`live_status_app_conversation_service.py:1634-1639` `remote_workspace.execute_command(...)`
   - 归档：`workspace_archive.py:417-435` `GET /api/file/archive`

> 这两层是**完全独立**的：`FileStore` 只在 app-server 主机上工作；沙箱里的文件操作走 agent-server 暴露的 REST 端点（`/api/file/...`、`/api/bash/...`），通过 `X-Session-API-Key` 头鉴权。

#### 2.6 evaluation 评估存储

当前 OpenHands 仓库**没有独立的 `evaluation/` 目录**——这是相对早期 V0 时的差异，V1 把 eval 工具移到了 [OpenHands/evaluation-harness](https://github.com/OpenHands/evaluation-harness) 等外部仓库。源码里能看到的"评估"痕迹：

- `save_trajectory_path`（`config.template.toml:29`）—— V0 兼容
- `browsergym_eval_env`（`config.template.toml`）—— V0 BrowserGym
- V1 的 trajectory 通过 `iter_events_for_export()`（`event_service_base.py:108-119`）直接流式导出 + `/api/v1/app-conversations/{id}/download`（`app_conversation_router.py:1598-1636`）打成 zip

---

### Q3. 工作区创建

**结论：完全的"懒创建" + "首次对话触发"**——OpenHands **没有 `openhands init` 命令**。工作区不是用户显式声明的，是**第一次创建 conversation 时由 app-server 协调 sandbox + agent-server 隐式建出来**。

| 阶段 | 触发 | 行为 | 代码 |
|---|---|---|---|
| 1. 持久化目录 | `get_default_persistence_dir()` | 第一次访问时 `mkdir(parents=True, exist_ok=True)` | `app_server/config.py:75-89` |
| 2. 全局 SQLite | alembic upgrade | `OssAppLifespanService.run_alembic()` 启动时跑 `alembic upgrade head` | `app_server/app_lifespan/oss_app_lifespan_service.py:23-40` |
| 3. Sandbox | `start_sandbox(sandbox_spec_id)` | Docker 模式：`docker_client.containers.run(...)`；process 模式：`_create_sandbox_directory()` 创 `{base_working_dir}/{sandbox_id}/` | `sandbox/docker_sandbox_service.py:478-516`、`sandbox/process_sandbox_service.py:108-110,329-345` |
| 4. Runtime workspace | sandbox 启动后 agent-server 进入 `working_dir` | 容器内 `/workspace/project/` 由镜像本身保证存在（agent-server 镜像 ENTRYPOINT 会准备好） | `docker_sandbox_spec_service.py:50` |
| 5. 实际工作区内容 | 第一次 `start_app_conversation` | 调 `_build_start_conversation_request_for_user()` → 触发 `clone_or_init_git_repo()` | `app_conversation_service_base.py:342-395`、`live_status_app_conversation_service.py:462-498` |
| 6. 用户级 skills 目录 | skills 列表请求触发 | 不预创建；`USER_SKILLS_DIR.exists()` 检查；缺则视为空 | `skills_router.py:34, 110-113, 175` |
| 7. Workspace 归档目录 | 仅当 `RUNTIME_FILE_ARCHIVE_ENABLED=true` + 删 sandbox | 写到对象存储（默认 GCS），不预创建 | `workspace_archive.py:131-141` |

#### 3.1 `init_git_in_empty_workspace`（关键细节）

```python
# openhands/app_server/app_conversation/app_conversation_service_base.py:342-395
async def clone_or_init_git_repo(self, task, workspace, sandbox):
    request = task.request

    # Create the projects directory if it does not exist yet
    parent = Path(workspace.working_dir).parent
    result = await workspace.execute_command(
        f'mkdir -p {workspace.working_dir}', parent
    )
    if result.exit_code:
        _logger.warning(f'mkdir failed: {result.stderr}')

    # Configure git user settings from user preferences
    await self._configure_git_user_settings(workspace)

    if not request.selected_repository:
        if self.init_git_in_empty_workspace:                    # 默认 True
            _logger.debug('Initializing a new git repository in the workspace.')
            cmd = (
                'git init && git config --global '
                f'--add safe.directory {workspace.working_dir}'
            )
            ...
        else:
            _logger.info('Not initializing a new git repository.')
        return

    # 否则走 git clone --depth 1
    ...
```

```python
# openhands/app_server/app_conversation/live_status_app_conversation_service.py:2749-2751
init_git_in_empty_workspace: bool = Field(
    default=True,
    description='Whether to initialize a git repo when the workspace is empty',
)
```

> **这是 OpenHands 的"自动 init"行为**：当用户不指定 repo 时，agent-server 进 sandbox 后会**自动 `git init`** 当前 working_dir。这与 Onion Agent 的设计哲学（围绕 session.json 累加、不主动操作仓库）有出入——OpenHands 默认把工作区假设为"git 仓库"，所有改文件/历史逻辑都依赖这个假设。

#### 3.2 没有 `openhands init` CLI

```bash
$ grep -rn "openhands init\|init_workspace\b" C:\workspace\github\onionagent\harness\01_market_research\clone\OpenHands\openhands
# 仅找到 init_git_in_empty_workspace 字段，没有 CLI init 命令
```

```python
# 前端的 DEFAULT_SETTINGS 也不要求"工作区"作为输入:
# frontend/src/services/settings.ts
# 没有 workspace_path / workspace_base 字段 —— 工作区是 server 端按需生成
```

> V0 时代的"workspace_base" 写在 `config.toml` (`config.template.toml:16`) 和 `setup-config-prompts` Makefile 目标 (`Makefile:321-323`) 里——但这只是 V0 启动配置，不是工作流命令。

#### 3.3 创建流程时序图（V1 一次 conversation 启动）

```
用户点"New Conversation"
  │
  ▼
POST /api/v1/app-conversations        (app_conversation_router.py:107-117)
  │
  ▼
AppConversationService → 创建 AppConversationStartTask
  │ (LiveStatusAppConversationService.live_status_app_conversation_service.py)
  ▼
启动或复用 sandbox ──→ SandboxSpec.working_dir = /workspace/project
  │ (DockerSandboxService.start_sandbox)
  ▼
get_sandbox_grouping_strategy() 决定 working_dir
  │ = /workspace/project   (NO_GROUPING)
  │ = /workspace/project/{conv_hex}  (其他)
  ▼
调 agent-server POST /api/conversations，body.working_dir = working_dir
  │
  ▼ (agent-server 端)
mkdir -p {working_dir}
git init || git clone --depth 1 {selected_repository}   ←  init_git_in_empty_workspace 控制
  │
  ▼
task.status = AppConversationStartTaskStatus.READY
  │
  ▼
ConversationInfo 返回
  │
  ▼
前端跳到 /conversations/{id}，WebSocket 连 agent-server
```

---

## 3. 关键代码片段

### 3.1 persistence_dir 解析（V0/V1 兼容）

```python
# openhands/app_server/config.py:75-89
def get_default_persistence_dir() -> Path:
    persistence_dir = os.getenv('OH_PERSISTENCE_DIR')     # V1 优先
    if persistence_dir is None:
        persistence_dir = os.getenv('FILE_STORE_PATH')     # V0 兼容
    if persistence_dir:
        result = Path(persistence_dir)
    else:
        result = Path.home() / '.openhands'                # 兜底
    result.mkdir(parents=True, exist_ok=True)              # ★ 隐式创建
    return result
```

### 3.2 FileStore 工厂

```python
# openhands/app_server/file_store/__init__.py:7-23
def get_file_store(file_store_type: str, file_store_path: str | None = None) -> FileStore:
    if file_store_type == 'local':
        if file_store_path is None:
            raise ValueError('file_store_path is required for local file store')
        return LocalFileStore(root=file_store_path)
    elif file_store_type == 's3':
        return S3FileStore(bucket_name=file_store_path or '')
    elif file_store_type == 'google_cloud':
        return GoogleCloudFileStore(bucket_name=file_store_path or '')
    else:
        return InMemoryFileStore()
```

### 3.3 LocalFileStore 原子写（防并发覆盖）

```python
# openhands/app_server/file_store/local.py:24-46
def write(self, path: str, contents: str | bytes) -> None:
    full_path = self.get_full_path(path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    mode = 'w' if isinstance(contents, str) else 'wb'

    # 写临时文件 → fsync → atomic rename
    temp_path = f'{full_path}.tmp.{os.getpid()}.{threading.get_ident()}'
    try:
        with open(temp_path, mode) as f:
            f.write(contents)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, full_path)
    except Exception:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise
```

### 3.4 conversation 路径生成（按 user_id 隔离）

```python
# openhands/app_server/event/event_service_base.py:66-82
async def get_conversation_path(self, conversation_id: UUID) -> Path:
    """Get a path for a conversation. Ensure user_id is included if possible."""
    path = self.prefix
    if self.user_id:
        path /= self.user_id
    elif self.app_conversation_info_service:
        task = self.app_conversation_info_load_tasks.get(conversation_id)
        if task is None:
            task = asyncio.create_task(
                self.app_conversation_info_service.get_app_conversation_info(
                    conversation_id
                )
            )
            self.app_conversation_info_load_tasks[conversation_id] = task
        conversation_info = await task
        if conversation_info and conversation_info.created_by_user_id:
            path /= conversation_info.created_by_user_id
    path = path / V1_CONVERSATIONS_DIR / conversation_id.hex    # ~/.openhands/{user}/v1_conversations/{hex}
    return path
```

### 3.5 sandbox 容器启动（Docker 模式）

```python
# openhands/app_server/sandbox/docker_sandbox_service.py:478-516
container = self.docker_client.containers.run(
    image=sandbox_spec.id,
    command=sandbox_spec.command,
    remove=False,
    name=container_name,
    environment=env_vars,
    ports=port_mappings,
    volumes=volumes,                          # ← mount 来自 self.mounts
    working_dir=sandbox_spec.working_dir,     # ← /workspace/project
    labels=labels,
    network_mode=network_mode,
    devices=devices,
    ...
)
```

### 3.6 ARCHIVE_WORKSPACE_PATH_TAG_KEY（防 misroute 的"路径钉死"）

```python
# openhands/app_server/app_conversation/app_conversation_models.py:39-42
ARCHIVE_WORKSPACE_PATH_TAG_KEY = 'archiveworkspacepath'

# openhands/app_server/app_conversation/live_status_app_conversation_service.py:571
tags[ARCHIVE_WORKSPACE_PATH_TAG_KEY] = working_dir    # 启动时钉死

# openhands/app_server/app_conversation/app_conversation_router.py:1005-1014
# 删除时读这个 tag，避开"用户改 grouping 后归档到错目录"
workspace_path = app_conversation_info.tags.get(ARCHIVE_WORKSPACE_PATH_TAG_KEY)
asyncio.create_task(
    _finalize_sandbox_delete(
        sandbox_service, app_conversation_info_service,
        sandbox_id, db_session, httpx_client,
        conversation_id=conversation_uuid,
        workspace_path=workspace_path,        # ← 钉死的路径
    )
)
```

> **这是个非常聪明的设计**：归档路径在 conversation 创建时就写进 `tags`（DB 里），删除时不再根据当前 settings 重新推导——避免用户中途改 grouping strategy 造成归档到错目录。

### 3.7 archive 触发（删除时）

```python
# openhands/app_server/sandbox/workspace_archive.py:355-490
async def archive_workspace(
    httpx_client, runtime, sandbox_id, *,
    archive_path, conversation_id=None,
) -> bool:
    # 调 agent-server 的 GET /api/file/archive
    # 默认两种格式: git-delta (.patch) + tar.gz
    # 推送到对象存储（GCS 默认）
    ...
```

---

## 4. 与 Onion Agent 设计的关联

| Onion Agent 设计要点 | OpenHands 的做法 | 借鉴 / 规避 |
|---|---|---|
| 围绕 `session.json` 上下文历史文件累加 | `~/.openhands/{user_id}/v1_conversations/{conv_hex}/{event_id}.json`——每个事件单独文件 | ⚠️ **不直接借鉴**：把每个 event 拆成单独文件导致 IO 放大，导出时全量扫描；Onion 走单文件追加更简单，但 OpenHands 的好处是天然支持分布式 event 服务（S3/GCS） |
| 全局工作区在哪 | 沙箱内 `/workspace/project`，**主机持久层是控制平面** | ✅ **完全一致**：把"用户的工作区"和"agent 系统的工作区"分开，OpenHands 也明确分离了 control plane（`~/.openhands`）和 runtime plane（`/workspace/project`） |
| 路径是 `~/.onion-agent/`？还是跟随当前目录？ | 默认 `~/.openhands`（**不**跟随 cwd），可通过 `OH_PERSISTENCE_DIR` 覆盖 | ✅ **借鉴**：固定一个隐式目录，避免用户每次启动都要指定。但 Onion 的命名应避免和 OpenHands 撞车 |
| `openhands init` 风格显式初始化？ | **没有**——完全隐式 + 首次对话触发 | ✅ **借鉴**：Onion 也应避免"必须 init 才能用"的强引导；首次启动时 `mkdir(parents=True, exist_ok=True)` 即可 |
| 显式 init_git 假设工作区是 git 仓库？ | `init_git_in_empty_workspace=True` 默认 | ⚠️ **规避**：Onion 围绕 session.json 累加，不需要 git 假设；如要支持"在已有 repo 上工作"，让用户显式提供 repo URL，别默认 `git init` |
| 沙箱还是本机？ | Docker / remote / process 三种 sandbox 后端 | ✅ **借鉴**：`SandboxService` 抽象 + 三种实现是干净的策略模式；Onion 早期可只支持 process，但保留接口 |
| 工作区分组（sandbox_grouping_strategy） | 一个 sandbox 跑 N 个 conversation 时，每个 conv 拿自己的子目录 | ✅ **可借鉴**：当 Onion 引入"workspace 复用"时（多 session 共享同一代码目录），用 `session_id` 做子目录隔离 |
| 多用户隔离 | `~/.openhands/{user_id}/...` | ✅ **借鉴**：多用户场景按 user_id 划分子目录 |
| FileStore 抽象（local / S3 / GCS / memory） | `LocalFileStore`（带 atomic write + fsync）、`S3FileStore`、`GoogleCloudFileStore`、`InMemoryFileStore` | ✅ **强烈借鉴**：尤其是 atomic write 模式（先写 `.tmp.{pid}.{tid}` → `fsync` → `os.replace`），Onion 的 `session.json` 也需要这种并发安全 |
| Settings 是 JSON 文件 | `FileSettingsStore` 存 `settings.json` | ✅ **借鉴**：V1 OSS 模式用 JSON 存用户设置，简单可靠；Sass 模式才升级到 SQL |
| workspace 归档（删除前） | `RUNTIME_FILE_ARCHIVE_ENABLED=true` 时，删 sandbox 前 `git diff` / `tar.gz` → 对象存储 | ✅ **借鉴**：Onion 的"session 结束后保留上下文"可以学这个；V0 V1 区别在于 OpenHands 的归档在 OSS 模式默认关闭，cloud 模式才需要 |
| 命名空间（V0 microagents → V1 skills） | 同一份文件两种命名，V1 兼容 V0 路径 | ✅ **借鉴**：Onion 的 V0→V1 迁移也可以做这种"路径兼容 + 内部统一模型" |
| 用户级 plugins | `~/.openhands/microagents/*.md` | ✅ **借鉴**：Onion 可以有 `~/.onion-agent/agents/*.md`（"内脑"/"外脑"/"小脑"的分角色定义） |
| 没有显式 `init` CLI | 完全懒创建 | ✅ **强化**：Onion 的"无 init 设计"和 Onion 哲学一致——只要 session.json 能创建，agent 就能跑 |

### 4.1 直接可抄的代码模式

1. **FileStore 抽象 + atomic write**（`local.py:24-46`）—— Onion 的 `session.json` 写入完全可以照搬这个模式，特别是并发场景下。
2. **路径解析函数**（`get_default_persistence_dir()`）—— `OH_PERSISTENCE_DIR` > `FILE_STORE_PATH` > `~/.openhands`，用 env 变量层层 fallback，最后默认到 `~/.onion-agent/`。
3. **conversation 路径拼接**（`conversation_paths.py`）—— 干净的 `get_conversation_dir(conv_id)` helper，避免在业务代码里硬编码 `"v1_conversations"`。
4. **`ARCHIVE_WORKSPACE_PATH_TAG_KEY` 的"路径钉死"模式**—— 创建时就钉死关键路径，删除时不再推导。这是 Onion 在做"session 结束归档"时应该学的：避免后续 settings 变化导致归档错位。
5. **Sandbox 工作区分组**（`grouped_workspace_dir`）—— Onion 引入"workspace 复用"机制时直接拿这个函数用即可。

### 4.2 需要规避的坑

1. **V0/V1 双轨制**——OpenHands 现在还在维护两套路径语义（`WORKSPACE_BASE` V0 vs `OH_PERSISTENCE_DIR` V1），导致 Dockerfile 里同时设两个 env 变量，spec 默认 working_dir 还有不一致。Onion 启动时就应确定唯一路径语义。
2. **`SandboxSpecInfo.working_dir` 默认值是 `/home/openhands/workspace`（`sandbox_spec_models.py:18`），但所有 V1 spec 实现都覆写成 `/workspace/project`**——**字段默认值不可信**。Onion 不要依赖 Pydantic 字段默认值，所有用到的地方都显式传。
3. **`init_git_in_empty_workspace=True` 默认开**——会"惊喜地"在用户工作目录里 `git init`，可能搞乱用户预期。Onion 不应自动做这种破坏性操作。
4. **每个 event 单独 JSON 文件**（`{event_id}.json`）—— V1 高频事件下 IO 数爆炸。Onion 的单文件追加设计在这点上更优。
5. **"控制平面"和"运行时工作区"两个完全独立的位置**——对用户解释成本高。Onion 文档要明确"工作区"指的是 sandbox 内，还是 Onion 的元数据目录。

---

## 5. 不确定 / 未找到

| 主题 | 不确定点 | 建议补充调研 |
|---|---|---|
| `evaluation/` 目录 | 当前仓库**没有独立 `evaluation/` 目录**——`glob 'evaluation/**'` 完全空。V0 时代有，现在移到外部仓库（OpenHands/evaluation-harness） | 需查外部仓库；如需"评估存储"章节只能给出"无" |
| `~/.openhands-state` 命名 | 旧的企业版 README 提到 `FILE_STORE_PATH=$HOME/.openhands-state`（`enterprise/enterprise_local/README.md:203`），但 `get_default_persistence_dir` 只回退到 `~/.openhands` | 这个 `.openhands-state` 可能是企业版历史约定，现已弃用；V1 默认走 `~/.openhands` |
| `microagents` vs `skills` 完整迁移图 | skills/README.md 提到 V0→V1 兼容，但代码里 `app_conversation_service_base.py:115` 还在引用 `.openhands/microagents/` | 需查 OpenHands/software-agent-sdk 仓库了解最新 agent-sdk 的真实 storage 模型——本调研以 OpenHands 仓库为限 |
| `Agent Server` 内部 storage | `from openhands.agent_server.env_parser` 提示 agent-server 是个**外部 SDK**（[OpenHands/software-agent-sdk](https://github.com/OpenHands/software-agent-sdk)），沙箱里跑的真实 agent-server 不在 `openhands/agent_server/` 里 | OpenHands 仓库 README:147 也明说"agent-server 源代码在 software-agent-sdk 仓库"——本次只调研了 OpenHands 仓库，沙箱内 agent-server 的实际存储行为需要去 software-agent-sdk 仓库确认 |
| `init` CLI 是否在企业版存在 | 未在 `enterprise/` 下找到 `cli.py` 或 `init` 子命令 | 如需确认，跑 `find . -name "*.py" -path "*/enterprise/*" -exec grep -l "init_workspace" {} +` 复查 |
| 多用户隔离的强制力 | 路径拼接是 `if self.user_id:`，**如果 user_id 为 None 会 fall through 到全局**（`event_service_base.py:69-82`） | 单用户 OSS 模式 OK；多租户部署必须确保 `user_context.get_user_id()` 不为 None |
| `DefaultSandboxSpec` 的几个 env 变量语义 | `OPENVSCODE_SERVER_ROOT`、`OH_VSCODE_PORT`、`OH_ENABLE_VNC`、`OH_WEBHOOKS_0_BASE_URL` 等来自 agent-server SDK，不在 OpenHands 仓库内 | 见 software-agent-sdk 仓库 |

---

> **TL;DR 给 Onion Agent**：OpenHands 的"工作区"实际是**控制平面**（`~/.openhands`，存元数据/事件/设置）和**运行时工作区**（`/workspace/project`，沙箱内，被 agent 读写）**两层解耦**。前者由 `get_default_persistence_dir()` 决定、可 env 覆盖、**隐式创建**；后者由 `SandboxSpec.working_dir` 决定、**首次创建 conversation 时由 agent-server 隐式建出**。Onion 应直接借鉴这种"控制平面 + 运行时解耦"的设计 + `FileStore` 抽象（特别是 atomic write）+ `ARCHIVE_WORKSPACE_PATH_TAG_KEY` 的"路径钉死"模式；同时规避 `init_git_in_empty_workspace=True` 这种默认破坏性操作、避免 V0/V1 双轨制带来的命名混乱。
