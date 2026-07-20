# AutoGPT — 工作区(File Backend)调研报告

> 调研对象:`Significant-Gravitas/AutoGPT`
> 调研时间:2026-07-17
> 调研方式:Read / Grep 静态分析,未执行构建/运行命令
> 关注目录:`autogpt_platform/backend/`(新 platform 版)+ `classic/original_autogpt/`(老 monolithic 版)
>
> **重要前提**:本仓库是 monorepo,内含**两套完全不同的实现**:
> 1. `classic/original_autogpt/` — 2023 年的初代 monolithic,有自己的 workspace 概念
> 2. `autogpt_platform/backend/` — 2024+ 重写的新版,基于多 agent graph 平台,workspace 概念彻底重做
>
> 任务说明要求"关注 platform/ 和 autogpt/agent_server/"(`autogpt/agent_server/` 不存在,实际是 `autogpt_platform/backend/`)。下文以**新版 platform 为主**展开,classic 版作为历史参照补充。

---

## 0. 智能体一句话定位

鼻祖级自主 AI Agent,`思考 → 行动 → 观察 → 评估` 循环,2023 年发布引爆行业。2024+ 重写为多 agent 编排平台(`autogpt_platform`),graph-based blocks 架构,CLI + Electron/React GUI 双前端,内置 plugin/block 市场、Agent Protocol Server、`workspace://` URI 跨 block 传参。

---

## 1. 调研依据

| 文件 | 作用 |
| --- | --- |
| `autogpt_platform/backend/schema.prisma:176-249` | `UserWorkspace` / `UserWorkspaceFile` / `UserWorkspaceFolder` 三张表的 schema 定义 |
| `autogpt_platform/backend/backend/data/workspace.py` | workspace DB CRUD:`get_or_create_workspace` / `create_workspace_file` / `list_workspace_files` / `soft_delete_workspace_file` |
| `autogpt_platform/backend/backend/data/workspace_folder.py` | folder DB CRUD(folder 是纯 DB 组织层,不影响 storage 路径) |
| `autogpt_platform/backend/backend/util/workspace.py` | `WorkspaceManager` 高层门面:read/write/list/delete,支持 session-scoped 路径 |
| `autogpt_platform/backend/backend/util/workspace_storage.py` | **真正的存储抽象层**:`WorkspaceStorageBackend` 抽象类 + `GCSWorkspaceStorage` / `LocalWorkspaceStorage` 两实现 + 工厂 `get_workspace_storage()` |
| `autogpt_platform/backend/backend/util/data.py:18-25` | `get_data_path()`:决定 Local 存储的根目录 |
| `autogpt_platform/backend/backend/util/settings.py:347-356` | Config 中 `media_gcs_bucket_name` 与 `workspace_storage_dir` 字段 |
| `autogpt_platform/backend/backend/util/file.py:23-44` | `WorkspaceUri` 与 `parse_workspace_uri()`:`workspace://<id>` / `workspace:///path` URI 方案 |
| `autogpt_platform/backend/backend/api/features/workspace/routes.py` | 5 个核心 HTTP 端点:upload / list / download / delete / storage-usage |
| `autogpt_platform/backend/backend/api/features/workspace/folder_routes.py` | folder 路由(创建/列表/移动/重命名/删除) |
| `autogpt_platform/backend/backend/executor/utils.py:1325-1330` | `ExecutionContext.workspace_id` 注入点:graph 执行时把 user workspace id 传给 runtime |
| `autogpt_platform/backend/backend/copilot/rate_limit.py:131-141` | tier-based 存储配额表(NO_TIER 250MB / PRO 1GB / MAX 5GB / BUSINESS 15GB / ENTERPRISE 15GB) |
| `autogpt_platform/backend/.env.default` | 部署模板,`MEDIA_GCS_BUCKET_NAME=` 留空即走 Local |
| `classic/original_autogpt/autogpt/app/cli.py:120-128` | classic CLI `-w / --workspace` 参数 |
| `classic/original_autogpt/autogpt/app/main.py:90-114` | classic 启动:workspace 默认为 `Path.cwd()`,`app_data_dir = workspace / ".autogpt"` |

> 主调研对象 = `autogpt_platform/backend/`(产品定位的"现在"与"未来"),classic 仅作对照(初代的"过去")。

---

## 2. 三个核心问题的回答

### Q1. 工作区路径

**platform 版答案:不是文件系统路径,是 DB row。** AutoGPT 新版完全抛弃了"用户在磁盘上有一个 workspace 目录"这个模型,改为**用户级**、**会话级**两级虚拟路径,实际文件存在 storage backend(GCS 或 Local)里,DB 表只存元数据。

| 维度 | platform 版 | classic 版(对照) |
| --- | --- | --- |
| 模型 | DB row + 远端 storage | 本地目录 |
| 入口 | `UserWorkspace` 表(1:1 with `User`) | `--workspace <path>` CLI 参数 |
| 默认位置 | **无默认路径** — workspace 与 `user_id` 一一对应,首次访问时 `get_or_create_workspace()` upsert 创建 | `Path.cwd()`(命令行当前目录) |
| 数据存放 | GCS bucket(`MEDIA_GCS_BUCKET_NAME` 配置),或 Local: `{get_data_path()}/workspaces/{workspace_id}/{file_id}/{filename}` | `workspace / .autogpt/agents/{id}/`(agent state);文件直接在工作区根目录 |
| 自定义 | env `MEDIA_GCS_BUCKET_NAME`(切到 GCS)或 `WORKSPACE_STORAGE_DIR`(覆盖 Local 根) | `-w / --workspace` 直接给路径;env `RESTRICT_TO_WORKSPACE` 控制是否锁在工作区 |
| CLI 命令 | 无(平台通过 FastAPI HTTP/REST 暴露,前端是 Web) | `autogpt run -w /path/to/workspace` 或 `autogpt serve -w /path` |
| 跟随当前目录 | ❌ 否 | ✅ 默认就是 cwd |

**关键代码证据 — platform 版 Config 字段**:

```python
# autogpt_platform/backend/backend/util/settings.py:347-356
media_gcs_bucket_name: str = Field(
    default="",
    description="The name of the Google Cloud Storage bucket for media files",
)

workspace_storage_dir: str = Field(
    default="",
    description="Local directory for workspace file storage when GCS is not configured. "
    "If empty, defaults to {app_data}/workspaces. Used for self-hosted deployments.",
)
```

**关键代码证据 — platform 版 factory 选择 backend**:

```python
# autogpt_platform/backend/backend/util/workspace_storage.py:412-435
async def get_workspace_storage() -> WorkspaceStorageBackend:
    config = Config()
    # --- Local storage (shared) ---
    if not config.media_gcs_bucket_name:
        if _local_storage is None:
            storage_dir = (
                config.workspace_storage_dir if config.workspace_storage_dir else None
            )
            logger.info(f"Using local workspace storage: {storage_dir or 'default'}")
            _local_storage = LocalWorkspaceStorage(storage_dir)
        return _local_storage
    # --- GCS storage (per event loop) ---
    loop_id = id(asyncio.get_running_loop())
    if loop_id not in _gcs_storages:
        _gcs_storages[loop_id] = GCSWorkspaceStorage(config.media_gcs_bucket_name)
    return _gcs_storages[loop_id]
```

→ 决策树:**有 `MEDIA_GCS_BUCKET_NAME` → GCS;无 → Local**(`WORKSPACE_STORAGE_DIR` 可覆盖 Local 根目录)。

**Local 默认根目录推导**(关键 3 跳):

```python
# autogpt_platform/backend/backend/util/data.py:18-25
def get_data_path() -> pathlib.Path:
    if getattr(sys, "frozen", False):
        datadir = os.path.dirname(sys.executable)        # PyInstaller 冻结
    else:
        filedir = os.path.dirname(__file__)              # .../backend/backend/util/
        datadir = pathlib.Path(filedir).parent.parent    # 跳 2 层 → .../backend/backend/
    return pathlib.Path(datadir)

# workspace_storage.py:228-234
class LocalWorkspaceStorage(WorkspaceStorageBackend):
    def __init__(self, base_dir: Optional[str] = None):
        if base_dir:
            self.base_dir = Path(base_dir)
        else:
            self.base_dir = Path(get_data_path()) / "workspaces"
        self.base_dir.mkdir(parents=True, exist_ok=True)
```

→ 源码运行:`<repo>/autogpt_platform/backend/backend/workspaces/`
→ Docker 运行(`Dockerfile:144` WORKDIR = `/app/autogpt_platform/backend`):`/app/autogpt_platform/backend/backend/workspaces/`

**classic 版对照**(行 120-128, cli.py):

```python
# classic/original_autogpt/autogpt/app/cli.py:120-128
@click.option(
    "-w",
    "--workspace",
    help=(
        "Workspace directory for AutoGPT to operate in. Defaults to current "
        "directory. Agent data will be stored in .autogpt/ subdirectory."
    ),
)
```

---

### Q2. 工作区目录结构

**platform 版**:workspace **不是目录**。它由三张 DB 表 + 一个 storage blob 池组成。结构如下:

#### 2.1 DB schema(`schema.prisma:176-249`)

| 表 | 主键 | 关键字段 | 作用 |
| --- | --- | --- | --- |
| `UserWorkspace` | `id` (UUID) | `userId` (unique, 1:1) | 每个登录用户自动拥有一个 workspace |
| `UserWorkspaceFile` | `id` (UUID) | `workspaceId` FK, `path` (虚拟路径, 唯一), `storagePath` (GCS object key 或 local 相对路径), `mimeType`, `sizeBytes` (BigInt), `checksum` (SHA256), `isDeleted`/`deletedAt` (软删除), `metadata` (JSON, 默认 `{}`), `folderId` (FK) | 一行 = 一个文件 |
| `UserWorkspaceFolder` | `id` (UUID) | `workspaceId` FK, `name`, `icon`, `parentId` (forward-compat 嵌套,v1 不用,恒为 null), `isDeleted` (软删除) | 纯 DB 组织层,不影响 storage 路径 |

```prisma
// autogpt_platform/backend/schema.prisma:191-220 (UserWorkspaceFile 摘录)
model UserWorkspaceFile {
  id          String   @id @default(uuid())
  workspaceId String
  name        String   // 用户可见文件名
  path        String   // 虚拟路径,如 "/documents/report.pdf" 或 "/sessions/abc/file.png"
  storagePath String   // GCS 或 local 的实际存储路径
  mimeType    String
  sizeBytes   BigInt
  checksum    String?  // SHA256
  isDeleted   Boolean  @default(false)
  deletedAt   DateTime?
  metadata    Json     @default("{}")
  folderId    String?  // 关联 UserWorkspaceFolder;null = 根目录
  @@unique([workspaceId, path])         // 同一 workspace 内路径唯一
  @@index([workspaceId, isDeleted])
  @@index([folderId])
}
```

#### 2.2 虚拟路径命名空间

工作区内部按"虚拟路径"组织,不是物理目录:

| 路径前缀 | 用途 | 创建者 |
| --- | --- | --- |
| `/<filename>` 或 `/<dir>/<file>` | 用户上传文件(非 session)、builder 写出的 artifact | `WorkspaceManager.write_file()`(当 `session_id=None`) |
| `/sessions/{session_id}/<filename>` | 单次 chat/turn 期间产生的临时文件,**默认随 session_id 作用域** | 默认行为(`WorkspaceManager(session_id=...)`);`bot/handler.py:178-180` 显式说明:附件上传要落到 `sessions/<id>/` 才能被 turn 读到 |
| `/skills/{slug}/SKILL.md`(+ 可选 `references/` `scripts/` `assets/`) | 用户自蒸馏的 skill(Anthropic Agent Skills 协议) | `store_skill` 工具,经 skills registry ACL 强约束 |
| (其他) | 由 block 工具/能力自由写入(图片生成、视频、PDF、代码产物等) | 各种 block |

→ **重要设计**:虚拟路径(`/...`)和物理路径(storage backend 里的 key)解耦。`path` 是用户视角;`storagePath` 是 backend 视角。`PathNotFoundError` 在 DB 层抛,**blob 数据仍可保留**直至下次软删除清理。

**代码证据 — session-scoped 路径解析**:

```python
# autogpt_platform/backend/backend/util/workspace.py:90-100
def _resolve_path(self, path: str) -> str:
    if path.startswith("/sessions/"):
        return path
    if self.session_path:
        if not path.startswith("/"):
            path = f"/{path}"
        return f"{self.session_path}{path}"
    return path if path.startswith("/") else f"/{path}"

# workspace.py:71-77
def __init__(self, user_id, workspace_id, session_id=None):
    self.user_id = user_id
    self.workspace_id = workspace_id
    self.session_id = session_id
    # Session path prefix for file isolation
    self.session_path = f"/sessions/{session_id}" if session_id else ""
```

#### 2.3 物理存储布局

| Backend | 路径格式 | 关键代码 |
| --- | --- | --- |
| **GCS** | `gcs://{bucket}/workspaces/{workspace_id}/{file_id}/{filename}` | `workspace_storage.py:194-201` |
| **Local** | `local://{workspace_id}/{file_id}/{filename}` 写入 `{base_dir}/{workspace_id}/{file_id}/{filename}` | `workspace_storage.py:271-279` |

注意:**Local 路径里没有 `workspaces/` 这一层**,因为 `base_dir` 本身就是 `.../workspaces/`(见 Q1 的 get_data_path 推导)。即 `LocalWorkspaceStorage` 把 `base_dir` 当作 `workspaces/` 根,内部直接用 `workspace_id/...` 分隔。GCS 反过来,把 `workspaces/` 拼进 blob name 防止和其他用途的 bucket 内容冲突。

#### 2.4 `workspace://` URI 方案

Block 之间传文件**不传字节**,传 URI。Graph executor 和 LLM prompt 都用这套:

```python
# autogpt_platform/backend/backend/util/file.py:23-44
class WorkspaceUri(BaseModel):
    file_ref: str   # File ID 或 path
    mime_type: str | None
    is_path: bool   # True 当 file_ref 以 "/" 开头

def parse_workspace_uri(uri: str) -> WorkspaceUri:
    raw = uri.removeprefix("workspace://")
    # workspace://abc123            → WorkspaceUri(file_ref="abc123", is_path=False)
    # workspace://abc123#video/mp4  → WorkspaceUri(file_ref="abc123", mime_type="video/mp4")
    # workspace:///path/to/file.txt → WorkspaceUri(file_ref="/path/to/file.txt", is_path=True)
```

> 实战注意:`workspace://<uuid>#<mime>` 形式是 CoPilot 提示 LLM 输出的标准格式(详见 `chat.py` / `chat_artifact.py`),后端 `extract_artifact_links()` 用 regex 把它从 markdown 里剥出来。

#### 2.5 AI 设置 / 记忆 / 向量库 / agent 日志 / 插件市场

| 用途 | 实现位置 | 备注 |
| --- | --- | --- |
| **AI 设置**(LLM provider、模型选择) | 平台层:用户配置存在 `User` / `Profile` / `APIKey` 表;block 内部用 `credentials_field()` + `CredentialsMetaInput` | 走 OAuth 或 env key,与 workspace 解耦 |
| **记忆**(语义记忆、对话历史) | 短期:PostgreSQL `ChatSession` / `ChatMessage`;长期记忆:`graphiti` (FalkorDB 图存储)+ mem0(pgvector) | 都不是文件 |
| **向量库** | 嵌入:`api/features/search/service.py` + `api/features/workspace/embeddings.py`(file 全文搜索用,fire-and-forget 调度);`pgvector`/`pinecone` 供 mem0/graphiti | 文件元数据本身不进向量库,只对 name 做嵌入 |
| **agent 日志** | 后端 stdlib `logging` + Docker 日志;无独立文件 | Execution 日志走 `AgentGraphExecution` 表 |
| **插件/Block 市场** | `blocks/`(代码内置,300+ 块)+ `StoreAgent` / `LibraryAgent`(用户发布/安装的 graph) | 插件即"代码",不是"文件"。Block 通过 `pyproject.toml` 依赖被加载 |
| **graph 模板** | `autogpt_platform/graph_templates/*.json`(仓库顶层,运行时从 DB 读) | 系统初始化时 seed 进 DB |
| **skill 仓库** | `workspace://skills/{slug}/SKILL.md`(用户自己蒸馏的);`backend/copilot/skills.py` 维护一份 `DEFAULT_SKILLS` 内置清单(代码内,DB 不可改) | 用户的 skill 持久化在 workspace 本身,系统 skill 是代码 |

#### 2.6 软删除 / 配额 / 病毒扫描

- **软删除**(`workspace.py:280-316`):`isDeleted=true` + `path` 改成 `{原路径}__deleted__{ts}`(腾出唯一约束,允许同名新文件)
- **每文件大小**:`Config().max_file_size_mb`,默认 100MB(`settings.py:504-509`)
- **每用户配额**:`copilot/rate_limit.py:131-141`,按 Stripe 订阅 tier:
  - NO_TIER / BASIC: 250MB
  - PRO: 1GB
  - MAX: 5GB
  - BUSINESS / ENTERPRISE: 15GB
  - 可被 LaunchDarkly flag `copilot-tier-workspace-storage-limits` 在线覆写
- **病毒扫描**:`WorkspaceManager.write_file()` 必走 `scan_content_safe()`(ClamAV),命中抛 `VirusDetectedError`(`workspace.py:251`)

---

### Q3. 工作区创建

**platform 版答案:无需显式 init,首次访问隐式创建。**

```python
# autogpt_platform/backend/backend/data/workspace.py:82-99
async def get_or_create_workspace(user_id: str) -> Workspace:
    """
    Get user's workspace, creating one if it doesn't exist.
    Uses upsert to atomically handle concurrent creation attempts.
    """
    try:
        workspace = await UserWorkspace.prisma().upsert(
            where={"userId": user_id},
            data={
                "create": {"userId": user_id},
                "update": {},  # No-op update; workspace already exists
            },
        )
    except UniqueViolationError:
        # Defense-in-depth: should not happen with upsert, but handle gracefully
        workspace = await UserWorkspace.prisma().find_unique(where={"userId": user_id})
        if workspace is None:
            raise
    return Workspace.from_db(workspace)
```

→ **触发时机**:
- 用户首次调任何 `/api/workspace/*` 端点(list/upload/storage-usage)→ FastAPI 注入 `get_user_id` → handler 调 `get_or_create_workspace()`
- 用户首次跑 graph → `executor/utils.py:1325-1330` 把 `workspace_id` 注入 `ExecutionContext`,触发创建
- 用户首次开 CoPilot session → `bot/handler.py:178-180` 在解析 session 时创建

→ **DB 必须在前面跑起来**:`docker compose up -d` 起 PostgreSQL + Redis + RabbitMQ + Supabase。**workspace 自己没有任何 bootstrap 步骤**。也不需要 `mkdir`、不需要 schema 初始化(Prisma migrate 会建表,见 `migrations/` 目录)。

→ **Storage backend 的目录是 lazy 建的**:
```python
# workspace_storage.py:230-231
self.base_dir.mkdir(parents=True, exist_ok=True)
# workspace_storage.py:274
file_path.parent.mkdir(parents=True, exist_ok=True)
```

即:**没有任何前置准备工作**。`git clone → docker compose up -d → 浏览器开 3000` 就完事。

**classic 版对照**(对照参考,**不在 platform 调研范围**):classic 的 workspace 是 `Path.cwd()` 上的物理目录,首次 `autogpt run -w /path` 时若不存在会**自动创建**(via `Path.mkdir(parents=True, exist_ok=True)`),agent 自己的 state 落到 `{workspace}/.autogpt/agents/{id}/`。

---

## 3. 关键代码片段

### 3.1 WorkspaceManager 写入全流程(端到端,核心 35 行)

```python
# autogpt_platform/backend/backend/util/workspace.py:169-256 (write_file 摘)
async def write_file(
    self, content: bytes, filename: str, path: Optional[str] = None,
    mime_type: Optional[str] = None, overwrite: bool = False,
    metadata: Optional[dict] = None,
) -> WorkspaceFile:
    # 1. 单文件大小硬上限
    max_file_size = Config().max_file_size_mb * 1024 * 1024
    if len(content) > max_file_size:
        raise ValueError(f"File too large: {len(content)} bytes exceeds ...")

    # 2. 路径归一化 + session 作用域注入
    if path is None: path = f"/{filename}"
    elif not path.startswith("/"): path = f"/{path}"
    path = self._resolve_path(path)

    # 3. 配额(覆盖写时扣回旧文件大小)
    storage_limit, current_usage = await asyncio.gather(
        get_workspace_storage_limit_bytes(self.user_id),
        workspace_db().get_workspace_total_size(self.workspace_id),
    )
    if overwrite:
        existing = await db.get_workspace_file_by_path(self.workspace_id, path)
        if existing is not None:
            current_usage = max(0, current_usage - existing.size_bytes)
    if storage_limit > 0 and current_usage + len(content) > storage_limit:
        raise ValueError(f"Storage limit exceeded. ...")

    # 4. 冲突预检(只在 !overwrite)
    if not overwrite:
        existing = await db.get_workspace_file_by_path(self.workspace_id, path)
        if existing is not None:
            raise ValueError(f"File already exists at path: {path}")

    # 5. 病毒扫描(在 storage 前)
    await scan_content_safe(content, filename=filename)

    # 6. MIME 自动嗅探 + SHA256 + file_id(uuid4)
    if mime_type is None:
        mime_type, _ = mimetypes.guess_type(filename)
        mime_type = mime_type or "application/octet-stream"
    checksum = compute_file_checksum(content)
    file_id = str(uuid.uuid4())

    # 7. 写 storage(GCS 或 Local)
    storage = await get_workspace_storage()
    storage_path = await storage.store(
        workspace_id=self.workspace_id, file_id=file_id,
        filename=filename, content=content,
    )

    # 8. 写 DB row,UniqueViolation 时回滚 storage 并重试
    async def _persist_db_record(retries=2 if overwrite else 0) -> WorkspaceFile:
        try:
            return await db.create_workspace_file(...)
        except UniqueViolationError:
            if retries > 0:
                existing = await db.get_workspace_file_by_path(...)
                if existing: await self.delete_file(existing.id)
                return await _persist_db_record(retries - 1)
            raise ValueError("File already exists at path: ...") from None
    try:
        file = await _persist_db_record()
    except Exception:
        try: await storage.delete(storage_path)
        except Exception as e: logger.warning(...)
        raise
    # 9. fire-and-forget 写嵌入索引
    schedule_workspace_file_embedding(file.id, self.user_id, file.name, file.path)
    return file
```

### 3.2 Storage backend 抽象(5 个 method)

```python
# autogpt_platform/backend/backend/util/workspace_storage.py:46-97
class WorkspaceStorageBackend(ABC):
    @abstractmethod
    async def store(self, workspace_id, file_id, filename, content) -> str: ...
    @abstractmethod
    async def retrieve(self, storage_path) -> bytes: ...
    @abstractmethod
    async def retrieve_partial(self, storage_path, max_bytes) -> bytes: ...  # Range request
    @abstractmethod
    async def delete(self, storage_path) -> None: ...
    @abstractmethod
    async def get_download_url(self, storage_path, expires_in=3600) -> str: ...
```

### 3.3 GCS 实现的关键约束

```python
# workspace_storage.py:188-200
async def store(self, workspace_id, file_id, filename, content):
    client = await self._get_async_client()
    blob_name = self._build_blob_name(workspace_id, file_id, filename)  # workspaces/{ws}/{id}/{name}
    await client.upload(self.bucket_name, blob_name, content, metadata={
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "workspace_id": workspace_id,
        "file_id": file_id,
    })
    return f"gcs://{self.bucket_name}/{blob_name}"
```

```python
# workspace_storage.py:225-241 (download URL)
async def get_download_url(self, storage_path, expires_in=3600):
    bucket_name, blob_name = parse_gcs_path(storage_path)
    try:
        sync_client = self._get_sync_client()
        return await generate_signed_url(sync_client, bucket_name, blob_name, expires_in)
    except AttributeError as e:
        # 本地用 OAuth 凭证跑,无法签 URL → fallback 到 API 代理
        if "private key" in str(e) and file_id:
            return f"/api/workspace/files/{file_id}/download"
        raise
```

### 3.4 Local 实现的 path traversal 防护

```python
# workspace_storage.py:235-265
def _build_file_path(self, workspace_id, file_id, filename) -> Path:
    from backend.util.file import sanitize_filename
    safe_filename = sanitize_filename(filename)
    file_path = (self.base_dir / workspace_id / file_id / safe_filename).resolve()
    if not file_path.is_relative_to(self.base_dir.resolve()):
        raise ValueError("Invalid filename: path traversal detected")
    return file_path
```

### 3.5 HTTP 端点(workspace routes 共 5 个)

```python
# autogpt_platform/backend/backend/api/features/workspace/routes.py
POST   /api/workspace/files/upload      # 用户/Builder/CoPilot 上传(session_id 走 query)
GET    /api/workspace/files              # 列文件(支持 ?session_id= ?origin= ?q= ?folder_id= ?root_only=)
GET    /api/workspace/files/{id}/download  # 下载(local 直接流式,GCS 302 重定向 signed URL,失败回退)
GET    /api/workspace/files/{id}/preview   # 缩略图/文本预览(用于 Artifacts 网格)
DELETE /api/workspace/files/{id}           # 软删除
GET    /api/workspace/storage/usage        # 配额用量
# + folder_routes.py: folder CRUD
```

---

## 4. 与 Onion Agent 设计的关联

> Onion Agent 理念:Agent Loop 围绕 `session.json` 上下文文件做自动累加器,洋葱架构分层。
> AutoGPT 的方案对 Onion 有 **3 个直接可借鉴的精华** 和 **1 个明显短板**:

### 4.1 ✅ 可借鉴:把"虚拟路径"和"物理存储"解耦

AutoGPT 用 `path` (虚拟) + `storagePath` (物理) 双字段,二者**可以独立变化**。这意味着:
- 同一份字节数据可以被多个虚拟路径"指"向(复制是 0 字节,只改 `path` 列)
- 物理层可以无缝从 Local 迁到 GCS(改 storagePath + 改 backend 实现),虚拟层 API 不动
- 软删除只动 `path` 字段 → 允许同名新文件,不必立即清 blob(防误删)

**Onion 启示**:`session.json` 这种"上下文历史文件"在分布式场景下应该按这思路拆 — 写时只追加 `append-only log`,内部路径(`sessions/001/`)可以重命名,但存储层是 immutable 的(类似 git 的 content-addressed)。文件即日志的思路在这里找到了参照。

### 4.2 ✅ 可借鉴:session-scoped 路径做"逻辑作用域"

```python
self.session_path = f"/sessions/{session_id}" if session_id else ""
```

→ 当 manager 带 `session_id` 时,所有未指明 `/sessions/.../` 的写自动落到 `sessions/{id}/` 下;读取默认只读当前 session,显式用 `/sessions/other-id/...` 跨 session。

**Onion 启示**:Onion 的 Agent Loop 天然是 session 化的。给 Onion 加一个 `OnionFile` 抽象,自动让"思考上下文"写到一个 session-scoped 路径(如 `.onion/sessions/{sid}/think.md`)。这样:
- session 重启时,文件天然按 session 分桶
- 跨 session 检索靠显式前缀,不会无脑 merge
- LLM prompt 中可以放心使用相对路径,不会被其他 session 干扰

### 4.3 ✅ 可借鉴:配额 / 大小 / 病毒扫描 / 软删除的纵深防御

`write_file()` 6 步预检(大小→配额→冲突→病毒→MIME→checksum),任何一步 fail 都抛结构化错误,FastAPI 层映射到 400/409/413/500。失败时**主动清理 storage** (`storage.delete(storage_path)`),不留孤儿。

**Onion 启示**:Onion 的 `session.json` 没有"大小上限"概念,长期跑下去会无限膨胀。可以借鉴:
- 每 session 单独上限(如 50MB),超限强制分卷
- write-then-cleanup 模式(先写再删旧)防止半成品
- 软删除而非硬删除,允许"撤销 step"

### 4.4 ⚠️ 短板:不依赖显式 workspace 目录,初始化零成本

AutoGPT 的 workspace 概念对终端用户"完全隐藏"。这对 C 端 SaaS 友好,但对 Onion 这种"开发者工具 + 命令行"场景是个**反模式**:
- 用户在文件系统里找不到 workspace,无法用 `ls` / `find` / IDE 直接看 agent 在干什么
- `git diff` 不到任何东西,无法做 code review 风格的 agent 行为审计
- 出问题调试时,只能查 DB,不能 cat 一个文件

**Onion 启示**:**保留显式 `.onion/` 工作区目录**。Onion 的核心价值是"agent 行为可追溯",这点靠文件系统能直接读出来,比靠 DB query 友好得多。AutoGPT 的"一切在 DB"是 SaaS 取舍,Onion 作为 CLI/开发者工具应当反过来。

### 4.5 ⚠️ 短板:过度设计 folder / sharing / soft-delete 体系

platform 的 `UserWorkspaceFolder` 软删除 + `parentId` forward-compat + `SharedExecutionFile` / `SharedChatFile` 多表分享机制,加上 Prisma 28 个相关表(`data/` 目录近 100 个 workspace 相关测试文件),对一个"文件存储"功能来说**复杂度爆炸**。Onion 不需要这些 — 一个 `session.json` 加 `memory/` 子目录足矣。

**Onion 启示**:**保持最小文件 schema**。`{ path, content, mtime, session_id }` 四字段起步,够用到 80% 场景。Folder/分享/嵌入/搜索这些都后置,等真用户提需求再加。AutoGPT 选 GCS 当默认 backend 也暗示了一个问题:**他们大概率后悔把 Local 当 first-class**(因为 Local 和 GCS 在并发/一致性上行为差异巨大,代码里到处是"if backend is GCS..."的判断)。

---

## 5. 不确定 / 未找到

1. **classic 版的 `--workspace-directory` 参数名**:任务原话提到"AutoGPT 早就有显式 workspace directory 参数"。**classic 版 CLI 用的是 `-w / --workspace`**,不是 `--workspace-directory`。可能是不同版本,或者任务描述与最新代码不完全吻合。本调研以 `cli.py:120-128` 的 `click.option("-w", "--workspace", ...)` 为准。

2. **classic 版的 storage backend 配置项**:`forge/file_storage/__init__.py:7-9` 确认有 `FileStorageBackendName` 枚举,值为 `LOCAL = "local"` / `GCS = "gcs"`;后续 case 分支还有 `S3 = "s3"`(`__init__.py:26-31`)。`forge/config/base.py:14-15` 的配置项 `file_storage_backend` 默认 LOCAL,env 变量 `FILE_STORAGE_BACKEND`。Backend 选 Local/S3/GCS 三选一。

3. **`workspace_storage_dir` 是否支持多 workspace 共享同一 Local 根**:未在代码中找到显式约束,但 `LocalWorkspaceStorage.__init__()` 接受 `base_dir` 并 `mkdir(parents=True, exist_ok=True)`,**理论上多实例**可以共用同一根,通过 `workspace_id` 子目录区分;但缺少文档化保证。

4. **`WORKSPACE_STORAGE_DIR` 路径配置的代码层入口**:`settings.py:352-356` 的字段名是 `workspace_storage_dir`(小写),env 变量名在 Pydantic Settings 中通常为 `WORKSPACE_STORAGE_DIR`(大写),但未在 `.env.default` 中找到对应模板行 — 可能是默认行为(留空用 `{get_data_path()}/workspaces`)足够用,环境变量名字假设需运行验证。

5. **GCS backend 的 `aiohttp.ClientSession` per-loop 实例的生命周期**:`shutdown_workspace_storage()` 由 REST API lifespan hook 调,但 copilot executor 跑在独立 worker 线程 / 独立 event loop 上,**每个 loop 必须自己调一次**。代码注释里写明了这点(`workspace_storage.py:381-386`),但实际是否每个 worker 都正确调了,需要看 `executor/` 的具体实现 — 本次未深入。

6. **AutoGPT 的"插件市场"具体形态**:`blocks/` 内置 300+ 块是代码,不是用户安装的;用户间共享的是 `StoreAgent`(保存为 graph)和 `LibraryAgent`。**"插件"在 AutoGPT 语境里更接近"block 模块"**,不是传统 plugin manifest。`plugins/` 目录在 classic 还在(`classic/original_autogpt/plugins/`),但新版 platform 似乎已废弃该目录。

7. **graph templates 加载时机**:`autogpt_platform/graph_templates/*.json` 是初始化 seed,具体由 `migrations/` 中哪个 migration 写入 `AgentGraph` 表,未在调研范围内验证。

---

> **调研结论一句话**:AutoGPT 新版 platform 把 workspace 从"用户磁盘目录"重构为"DB row + 远端 storage + workspace:// URI 方案",通过 `UserWorkspace` 一户一行 + `UserWorkspaceFile` 虚实解耦 + session-scoped 路径实现 SaaS 级多租户。对 Onion 的最大启示是"虚实路径解耦"和"session-scoped 写入作用域",最大反启示是"不要把一切藏到 DB 里"。
