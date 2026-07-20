# Lobe Chat — 工作区(File Backend)调研报告

## 0. 智能体一句话定位

"首席 Agent 运营官":Web (Next.js) + Desktop (Electron) + CLI (`lh`) 三端共栈,**数据库**用 PostgreSQL+pgvector,**对象存储**用 S3-兼容 (Cloudflare R2 / RustFS / MinIO) 模拟,**缓存/队列**用 Redis;Chat UI + 多 Agent 调度 (chat_groups) + 知识库 (knowledge_bases) + 插件市场 (PLUGINS_INDEX_URL) + Agent 市场 (AGENTS_INDEX_URL),深度集成 MCP 协议。

---

## 1. 调研依据

- 仓库路径:`C:\workspace\github\onionagent\harness\01_market_research\clone\lobe-chat` (snapshot,只读)
- 仓库类型:pnpm workspace monorepo,3 个 app + 80+ 个 package
- 关键代码定位:
  - `apps/desktop/src/main/const/dir.ts` — 桌面端 userData 派生目录
  - `apps/desktop/src/main/pre-app-init.ts` — 桌面端 userData 覆写入口
  - `apps/desktop/src/main/core/infrastructure/StoreManager.ts` — electron-store 初始化
  - `apps/desktop/src/main/services/fileSrv.ts` — 桌面端"模拟 S3"文件服务
  - `apps/desktop/src/main/const/heteroAgent.ts` — 异构 Agent 子目录约定
  - `apps/desktop/src/main/controllers/LocalFileCtr.ts` — 桌面端 skill 缓存根
  - `apps/cli/src/settings/index.ts` — CLI 主目录 `~/.lobehub/`
  - `apps/cli/src/auth/credentials.ts` — CLI 凭证存储
  - `packages/database/src/core/web-server.ts` — 服务端 DB Pool 工厂
  - `packages/database/src/schemas/*` — 40+ 张表 schema (Drizzle)
  - `packages/database/migrations/0000_init.sql` ~ `0122_*.sql` — 129 个 SQL 迁移
  - `packages/env/src/file.ts` / `app.ts` / `redis.ts` — 服务端 env 入口
  - `packages/app-config/src/db.ts` — `serverDBEnv` 校验
  - `docker-compose/deploy/docker-compose.yml` — 生产部署编排
  - `scripts/migrateServerDB/index.ts` — 迁移命令 `pnpm db:migrate`
- 调研深度:逐文件 Read/Glob/Grep,无重型操作 (未 `pnpm install`)。

---

## 2. 三个核心问题的回答

> **重要前提**:Lobe Chat 是一个**三端产品**(Web / Desktop / CLI),三者**共用同一份 PostgreSQL schema**,但**文件系统侧完全独立**。下文按端分别回答 Q1/Q2/Q3。

### Q1. 工作区路径(按端分述)

#### 1) Web / 服务端模式(自托管 / Vercel)

| 项目 | 路径 / 端点 | 证据 |
|---|---|---|
| **关系数据库 (PG)** | 由 `DATABASE_URL` 决定,`drizzle.config.ts:13` 直读 `process.env.DATABASE_URL` | `drizzle.config.ts:13` |
| **PG 驱动** | `DATABASE_DRIVER ∈ {neon, node}`,默认 `neon` (Neon serverless over WebSocket) | `packages/app-config/src/db.ts:8,20` |
| **pgvector 扩展** | `CREATE EXTENSION IF NOT EXISTS vector` (在首个迁移 0005 中) | `packages/database/migrations/0005_pgvector.sql:2` |
| **对象存储 (S3)** | 必填 `S3_ENDPOINT` / `S3_BUCKET` / `S3_ACCESS_KEY_ID` / `S3_SECRET_ACCESS_KEY` | `.env.example:148-156` |
| **文件路径前缀** | `NEXT_PUBLIC_S3_FILE_PATH`,默认 `files` (在 S3 桶内) | `packages/env/src/file.ts:4,31` |
| **缓存/队列 (Redis)** | `REDIS_URL`,默认 prefix `lobechat` | `packages/env/src/redis.ts:25` |
| **加密密钥** | `KEY_VAULTS_SECRET` (32 字节 base64),用于加密用户 API key | `packages/app-config/src/db.ts:23` |
| **市场索引 (Agent)** | `AGENTS_INDEX_URL`,默认 `https://registry.npmmirror.com/@lobehub/agents-index/...` | `packages/env/src/app.ts:36,94-96` |
| **市场索引 (Plugin)** | `PLUGINS_INDEX_URL`,默认 `https://registry.npmmirror.com/@lobehub/plugins-index/...` | `packages/env/src/app.ts:34,101-103` |

**Q1 结论 (Web)**:数据库、缓存、对象存储**全部走远程服务,通过 env 注入连接串**;**没有任何"属主目录"或"CWD"概念**。即:`~/.lobechat/` 在 Web 模式不存在。

#### 2) Desktop 模式(Electron 客户端)

| 子目录 / 文件 | 绝对路径 | 证据 |
|---|---|---|
| **userData 根** | `app.getPath('userData')`(由 Electron 按 OS 决定) | `apps/desktop/src/main/const/dir.ts:21` |
| **应用存储根** | `<userData>/lobehub-storage/` | `apps/desktop/src/main/const/dir.ts:23` |
| **electron-store 配置** | `<userData>/lobehub-settings.json`(store name = `lobehub-settings`) | `apps/desktop/src/main/const/store.ts:18` |
| **"模拟 S3" 文件目录** | `<appStorageDir>/file-storage/...` | `apps/desktop/src/main/const/dir.ts:31`,`services/fileSrv.ts:54,78` |
| **旧版文件 uploads** | `<appStorageDir>/file-storage/uploads/...` (已标 deprecated) | `apps/desktop/src/main/services/fileSrv.ts:51-55` |
| **Skill 归档缓存** | `<appStorageDir>/file-storage/skills/...` | `apps/desktop/src/main/controllers/LocalFileCtr.ts:607` |
| **异构 Agent 下载缓存** | `<appStorageDir>/heteroAgent/files/...` | `apps/desktop/src/main/const/heteroAgent.ts:3,7` |
| **异构 Agent trace** | `<appStorageDir>/heteroAgent/tracing/...` | `apps/desktop/src/main/const/heteroAgent.ts:8` |
| **本地数据库 (legacy)** | `<appStorageDir>/lobehub-local-db/...`(只用于"是否用过旧版"探测) | `apps/desktop/src/main/const/dir.ts:26`,`controllers/SystemCtr.ts:237` |
| **Managed 二进制** | `<userData>/bin/<name>/<version>/` (lazy download) | `apps/desktop/src/main/core/infrastructure/BinaryManager.ts:173` |
| **应用日志** | `<userData>/logs/server.log` (NODE_ENV=development) | `src/instrumentation.ts:3-5` |
| **HTTP 文件服务 URL 前缀** | `/lobe-desktop-file/<rel-path>`(在 `app://` origin) | `apps/desktop/src/main/const/dir.ts:36` |
| **desktop:// 协议** | URL 形如 `desktop://<rel-path>`,映射到 `appStorageDir/file-storage/<rel-path>` | `apps/desktop/src/main/services/fileSrv.ts:120-127` |

**userData 在各 OS 的实际位置** (由 Electron `app.getPath('userData')` 决定,默认名 = `package.json#name` = `lobehub-desktop-dev`):

| OS | 路径 |
|---|---|
| Windows | `%APPDATA%\lobehub-desktop-dev\` |
| macOS | `~/Library/Application Support/lobehub-desktop-dev/` |
| Linux | `~/.config/lobehub-desktop-dev/` |

**支持自定义路径** ✅,优先级:
1. 环境变量 `LOBE_DESKTOP_USER_DATA_DIR` (绝对路径覆写,`apps/desktop/src/main/pre-app-init.ts:20-23`)
2. 否则 dev 模式 = `app.getPath('appData') + '/lobehub-desktop-dev'` (`pre-app-init.ts:23`)
3. prod 模式 = Electron 决定的 userData (基于 `package.json#name` / `appId=com.lobehub.lobehub-desktop`)

`apps/desktop/src/main/pre-app-init.ts:4-25` 关键代码:
```ts
if (electronIs.dev()) {
  app.setName('lobehub-desktop-dev');  // 固定 appname, dev/prod cookie 加密 key 一致
  const userDataOverride = process.env.LOBE_DESKTOP_USER_DATA_DIR;
  app.setPath('userData', userDataOverride || path.join(app.getPath('appData'), 'lobehub-desktop-dev'));
}
```

**Q1 结论 (Desktop)**:写死 Electron userData(`<appData>/lobehub-desktop[-dev]/`),子目录 `lobehub-storage/` 是事实上的"工作区根",**支持 `LOBE_DESKTOP_USER_DATA_DIR` 环境变量完全覆写**,**不跟随 CWD**。

#### 3) CLI 模式(`lh` 命令,Node 脚本)

| 文件 | 绝对路径 | 证据 |
|---|---|---|
| **CLI 主目录** | `~/.lobehub/` (由 `LOBEHUB_CLI_HOME` 覆写) | `apps/cli/src/settings/index.ts:21`,`apps/cli/src/tools/heteroTask.ts:16`,`apps/cli/src/auth/credentials.ts:12` |
| **settings.json** | `<CLI_HOME>/settings.json` (mode 0600) | `apps/cli/src/settings/index.ts:23` |
| **credentials.json** (加密) | `<CLI_HOME>/credentials.json` (AES-256-GCM, 密钥派生 `lobehub-cli:<hostname>:<username>`) | `apps/cli/src/auth/credentials.ts:14-30` |
| **connection-id** | `<CLI_HOME>/connection-id` (UUID, `lh connect` 路由 key) | `apps/cli/src/settings/index.ts:26,68-83` |
| **workspace-enrollments.json** | `<CLI_HOME>/workspace-enrollments.json` (已加入的工作区 id 列表) | `apps/cli/src/settings/index.ts:30,114-145` |

**支持自定义路径** ✅,仅一个环境变量:`LOBEHUB_CLI_HOME` (默认 `.lobehub`)。**跟随 `os.homedir()`,不跟随 CWD**。

**Q1 结论 (CLI)**:写死 `~/.lobehub/`,由 `LOBEHUB_CLI_HOME` 覆写,**不跟随 CWD**。

#### Q1 一句话总览

| 端 | 工作区根 | 自定义方式 | 跟随 CWD? |
|---|---|---|---|
| Web | 远程 PG / S3 / Redis (env 注入) | `DATABASE_URL` / `S3_*` / `REDIS_URL` 等 env | ❌ |
| Desktop | `<userData>/lobehub-storage/` | `LOBE_DESKTOP_USER_DATA_DIR` (绝对路径) | ❌ |
| CLI | `~/.lobehub/` | `LOBEHUB_CLI_HOME` (相对 `$HOME`) | ❌ |

**所有三端都不跟随当前工作目录**;Lobe Chat 完全没有"per-project workspace"概念,所有数据都是按 `user_id` (用户级) / `workspace_id` (多租户级别) 在数据库里**逻辑隔离**。

---

### Q2. 工作区目录结构

#### A. Web / 服务端 — **数据库表结构** (40+ 张表,Drizzle ORM + PostgreSQL)

源码:`packages/database/src/schemas/`

| 域 | 表 | 关键字段 | 证据 |
|---|---|---|---|
| **用户/认证** | `users` | `id`, `email`, `preference jsonb`, `banned`, `role` | `schemas/user.ts:9-50` |
| **用户偏好** | `user_settings` | `tts`, `hotkey`, `keyVaults`, `general`, `languageModel`, `systemAgent`, `defaultAgent`, `market`, `memory`, `tool`, `image`, `notification` (全部 jsonb) | `schemas/user.ts:69-86` |
| **多租户/工作区** | `workspaces` | `id`, `slug`, `name`, `primaryOwnerId`, `frozen` | `schemas/workspace.ts:18-44` |
| | `workspace_members` | `(workspace_id, user_id)` 复合主键,`role` | `schemas/workspace.ts:55-79` |
| | `workspace_user_settings` | `(workspace_id, user_id)` 唯一索引,`preference jsonb` | `schemas/workspace.ts:156-184` |
| **Agent (单 agent)** | `agents` | `id`, `slug`, `title`, `model`, `provider`, `systemRole`, `chatConfig jsonb`, `agencyConfig jsonb`, `params jsonb`, `plugins jsonb[]`, `tts`, `marketIdentifier`, `workspaceId`, `visibility` | `schemas/agent.ts:35-117` |
| | `agents_knowledge_bases` | (agent ↔ knowledge_base) 关联表 | `schemas/agent.ts:119-141` |
| | `agents_files` | (agent ↔ file) 关联表 | `schemas/agent.ts:145-167` |
| **多 Agent 群组** | `chat_groups` | `id`, `title`, `config jsonb` (调度规则) | `schemas/chatGroup.ts:24-77` |
| | `chat_groups_agents` | `(chat_group_id, agent_id)` 复合主键,`enabled`, `order`, `role` | `schemas/chatGroup.ts:79-111` |
| **会话** | `sessions` | `slug`, `title`, `type ∈ {agent, group}`, `pinned`, `groupId`, `workspaceId` | `schemas/session.ts:74-113` |
| | `session_groups` | 用户分组的 session 文件夹 | `schemas/session.ts:33-58` |
| **话题 (历史消息)** | `topics` | `title`, `sessionId`, `agentId`, `groupId`, `historySummary`, `status`, `metadata`, `model`, `provider`, `totalCost`, `totalTokens`, `workspaceId` | `schemas/topic.ts:25-125` |
| | `threads` | 子任务 / 子话题分支 | `schemas/topic.ts:127-196` |
| **消息** | `messages` | (text + 引用) | `schemas/message.ts:95-176` |
| | `message_groups`, `messages_files`, `message_plugins`, `message_tts`, `message_translates`, `message_queries`, `message_query_chunks`, `message_chunks` | 消息周边 | `schemas/message.ts` |
| **文件 (DB 元数据)** | `global_files` | `hashId` (sha256 PK), `fileType`, `size`, `url`, `creator` | `schemas/file.ts:47-63` |
| | `files` | `id`, `name`, `size`, `url` (S3 URL), `fileType`, `fileHash → globalFiles`, `parentId` (folder), `clientId`, `workspaceId`, `visibility` | `schemas/file.ts:172-243` |
| | `documents` | (Page 文档) `id`, `fileType`, `source`, `parentId` (folder), `editorData jsonb`, `slug`, `workspaceId`, `visibility` | `schemas/file.ts:70-170` |
| **知识库** | `knowledge_bases` | `id`, `name`, `type`, `isPublic`, `settings jsonb`, `workspaceId`, `visibility` | `schemas/file.ts:250-305` |
| | `knowledge_base_files` | (kb ↔ file) 关联表 | `schemas/file.ts:307-326` |
| **RAG / 向量** | `chunks` | `text`, `abstract`, `metadata jsonb`, `compositeId`, `clientId`, `workspaceId` | `schemas/rag.ts:19-42` |
| | `unstructured_chunks` | `parentId` (parent chunk), `compositeId`, `fileId` | `schemas/rag.ts:44-74` |
| | `embeddings` | `chunkId` (unique), `embeddings vector(1024)`, `model`, `clientId`, `workspaceId` | `schemas/rag.ts:76-103` |
| | `document_chunks` | (document ↔ chunk) 关联 | `schemas/rag.ts:105-130` |
| **异步任务** | `async_tasks` | 后台任务表 (embedding / chunking) | `schemas/asyncTask.ts:7` |
| **LLM 调用追踪** | `llm_generation_tracing` | 完整请求 / 响应 / usage 落库 | `schemas/llmGenerationTracing.ts:33` |
| **AI Provider / Model** | `ai_providers`, `ai_models` | 私有 provider 配置 | `schemas/aiInfra.ts:20,75` |
| **RAG 评测** | `eval_datasets`, `eval_evaluation`, `evaluation_records` | 评测集与结果 | `schemas/ragEvals.ts:12,40,70,107` |
| **生成式历史** | `generations`, `generation_batches`, `generation_topics` | 批量生成记录 | `schemas/generation.ts:16,64,122` |
| **API Key 加密** | `api_keys` | (用 `KEY_VAULTS_SECRET` 加密) | `schemas/apiKey.ts:9` |
| **Notebook / 笔记** | `notebook`(在 userMemory schema) | 长期记忆 | `packages/database/src/schemas/userMemories/` |
| **任务管理** | `tasks`, `task_dependencies`, `task_documents`, `task_topics`, `briefs`, `task_comments` | 任务系统 | `schemas/task.ts` |
| **文档历史 / 分享** | `document_histories`, `document_shares`, `topic_shares`, `agent_share` | 历史/分享 | `schemas/documentHistory.ts`, `documentShare.ts`, `topic.ts:231`, `agentShare.ts` |
| **消息 / 通知** | `notifications`, `notification_deliveries` | 通知系统 | `schemas/notification.ts` |
| **设备 / 推送** | `devices`, `push_tokens` | 桌面 / 移动端 | `schemas/device.ts:18`, `pushToken.ts:16` |
| **工作流 (Works)** | `works`, `work_versions` | work registry | `schemas/work.ts:25,143` |
| **Agent 操作审计** | `agent_operations` | 操作流水 | `schemas/agentOperations.ts` |
| **Agent 定时任务** | `agent_cron_jobs` | 定时任务 | `schemas/agentCronJob.ts:17` |
| **Bot / 平台账号** | `agent_bot_providers`, `messenger_installations`, `messenger_account_links`, `system_bot_providers` | 多 IM 平台桥接 | `schemas/agentBotProvider.ts:24`, `messengerInstallation.ts:24`, `messengerAccountLink.ts:20`, `systemBotProvider.ts` |
| **Skill** | `agent_skills` | 技能绑定到 agent | `schemas/agentSkill.ts:11` |
| **RAG Skill 索引** | `chunks` + `unstructured_chunks` | SKILL.md 内容向量化 | `schemas/rag.ts` |
| **Verify (评估)** | `verify_criteria`, `verify_rubrics`, `verify_rubric_criteria`, `verify_check_results`, `verify_evidence`, `acceptances`, `verify_reports`, `verify_runs` | 验证体系 | `schemas/verify.ts:60,113,145,182,299,355,436,514` |
| **OAuth / SSO** | `nextauth_*`, `oidc_*`, `oauth_handoffs`, `rbac_*` | NextAuth + OIDC provider + RBAC | `schemas/nextauth.ts`, `oidc.ts`, `rbac.ts` |
| **BetterAuth** | `session`, `account`, `verification`, `twoFactor`, `passkey` | Better-Auth 套件 | `schemas/betterAuth.ts:27,47,71,87,103` |
| **Market 部署** | (用 `marketDeployments` 路由,无独立表) |  | `packages/business-server/src/lambda-routers/marketDeployments.ts` |

**统一的外键归一**:几乎每张业务表都带 `userId` + `workspaceId` + `clientId`,`workspaceId` 软外键到 `workspaces.id`,在 0106~0108 三次迁移中统一加列加索引加 FK (`add_workspace_id_columns.sql` / `add_workspace_id_fk.sql` / `add_workspace_id_indexes.sql`)。

**PG 扩展依赖**:
- `vector` (pgvector) — 必装,首迁移启用 (`0005_pgvector.sql`)
- HNSW 索引于所有 vector 列(见 `0037_add_user_memory.sql:100-111`,`0070_add_user_memory_activities.sql:30` 等多处)
- 生产部署用 `paradedb/paradedb:latest-pg17` 镜像(`docker-compose/deploy/docker-compose.yml:42`),预装 `pg_search`

**S3 对象存储目录约定**(桶内):

| 前缀 | 用途 | 证据 |
|---|---|---|
| `files/<date>/<uuid>.<ext>` | 通用上传 (用户头像、附件) | `src/services/upload.ts:34-41` |
| `files/mcp/<segment>/<date>/<uuid>.<ext>` | MCP 上传内容 | `apps/server/src/services/mcp/contentProcessor.ts:73` |
| `files/generations/<date>/<uuid>.<ext>` | AI 生成结果 (image) | `apps/server/src/modules/AgentRuntime/adapters/serverCallLlmStreamSink.ts:228` |

#### B. Desktop 端 — **文件系统 + electron-store**

```
<userData>/                                              # 由 app.getPath('userData') 决定
├── lobehub-settings.json                                # electron-store 全局配置 (STORE_NAME = "lobehub-settings")
├── lobehub-settings.json.bak / .tmp                     # electron-store 自动备份
├── bin/                                                  # 托管二进制缓存 (lazy download)
│   └── <name>/<version>/<bin>                            # 见 BinaryManager.ts:173
├── Network/                                              # Chromium 网络缓存 (devtools)
├── Cache/                                                # Chromium HTTP 缓存
├── Code Cache/                                           # Chromium V8 字节码缓存
├── Preferences                                           # Chromium/electron 偏好
├── Local State                                           # Chromium session state
├── logs/                                                 # 仅 NODE_ENV=development
│   └── server.log                                        # 见 instrumentation.ts:3-5
└── lobehub-storage/                                      # ★ 应用自有"工作区根" (appStorageDir)
    ├── lobehub-local-db/                                 # legacy: 仅用于探测"是否用过旧版本地 DB"
    ├── file-storage/                                     # ★ "模拟 S3" 文件目录 (FILE_STORAGE_DIR)
    │   ├── uploads/<timestamp>/<hash>.<ext>             # 旧版上传 (deprecated, 见 fileSrv.ts:51-55)
    │   ├── skills/<hash>/                                # skill zip 解压缓存 (见 LocalFileCtr.ts:607)
    │   └── <任意相对路径>                                # 新路径: 任意自定义, e.g. "user_uploads/images/photo.png"
    └── heteroAgent/                                      # 异构 Agent 协同 (const/heteroAgent.ts)
        ├── files/                                        # 下载/产出的文件
        └── tracing/                                      # CLI trace (packaged/ opted-in)
```

**desktop:// URL 协议**:`desktop://<rel-path>` → 映射到 `<appStorageDir>/file-storage/<rel-path>`,由 `StaticFileServerManager` 在 `127.0.0.1:<33xxx>` 起 HTTP server,URL 前缀 `/lobe-desktop-file/<rel-path>`(`StaticFileServerManager.ts:169`)。

**electron-store 内容**(`STORE_DEFAULTS`,`const/store.ts:43-58`):
```ts
{
  appTrayVisible: true,
  dataSyncConfig: { storageMode: 'cloud' },          // 'cloud' | 'selfHost' (dataSync.ts:13)
  encryptedTokens: {},
  gatewayDeviceDescription: '',
  gatewayDeviceId: '',
  gatewayDeviceName: '',
  gatewayEnabled: true,
  gatewayUrl: 'https://device-gateway.lobehub.com',
  gatewayWorkspaceEnrollments: [],
  heteroTracingEnabled: false,
  imessageBridgeConfigs: [],
  locale: 'auto',
  localFileWorkspaceRoots: [],                       // 用户授权的本地工作区根
  networkProxy: { ... defaultProxySettings },
  pendingRestoreRoute: '',
  shortcuts: DEFAULT_ELECTRON_DESKTOP_SHORTCUTS,
  storagePath: appStorageDir,                         // ★ 工作区根, 默认 <userData>/lobehub-storage
  themeMode: 'system',
  updateChannel: UPDATE_CHANNEL,
}
```

**插件 / Agent / 知识库** 在 Desktop 端**不落盘**:
- 自定义 MCP 插件 (`type='customPlugin'`) 走 tRPC `lambdaClient.plugin.createPlugin.mutate(...)` 写到 PG `plugin` 表(`services/plugin/index.ts:14-19`)
- Agent 配置、市场插件元数据全部从 `AGENTS_INDEX_URL` / `PLUGINS_INDEX_URL` 在线拉取(`packages/env/src/app.ts:36,34`)
- 知识库向量在云端 PG(pgvector),desktop 端只持有 PG 连接 (`DATABASE_URL` 走 selfHost)

#### C. CLI 端 — `~/.lobehub/`

```
~/.lobehub/                                              # LOBEHUB_CLI_HOME 可改
├── settings.json                # 服务地址配置 (mode 0600)
├── credentials.json             # OAuth tokens, AES-256-GCM 加密
├── connection-id                # UUID, lh connect 路由 key
└── workspace-enrollments.json   # 已加入的 workspace id 列表
```

**关键证据**:`apps/cli/src/settings/index.ts:21-31`:
```ts
const LOBEHUB_DIR_NAME = process.env.LOBEHUB_CLI_HOME || '.lobehub';
const SETTINGS_DIR = path.join(os.homedir(), LOBEHUB_DIR_NAME);
const SETTINGS_FILE = path.join(SETTINGS_DIR, 'settings.json');
const CONNECTION_ID_FILE = path.join(SETTINGS_DIR, 'connection-id');
const WORKSPACE_ENROLLMENTS_FILE = path.join(SETTINGS_DIR, 'workspace-enrollments.json');
```

**加密**:credentials.json 走 `crypto.createCipheriv('aes-256-gcm')`,密钥派生自 `pbkdf2Sync('lobehub-cli:' + hostname + ':' + username, 'lobehub-cli-salt', 100_000, 32, 'sha256')`(`apps/cli/src/auth/credentials.ts:14-30`)。文件权限 `mode: 0o600`。

#### Q2 一句话总览

| 端 | 数据存储 | 关键位置 |
|---|---|---|
| Web | **PostgreSQL + pgvector + S3-兼容对象存储 + Redis** | env 全部可配,无属主目录 |
| Desktop | `electron-store` 配置 (JSON) + 本地 `file-storage/` 目录 + 远程 PG/S3 | `<userData>/lobehub-storage/`,可 `LOBE_DESKTOP_USER_DATA_DIR` 覆写 |
| CLI | `~/.lobehub/` 下 4 个 JSON 文件 (credentials 加密) | `LOBEHUB_CLI_HOME` 可改 |

---

### Q3. 工作区创建

#### A. Web / 服务端

| 步骤 | 行为 | 证据 |
|---|---|---|
| **PG Schema 创建** | **隐式**,`pnpm db:migrate` → `scripts/migrateServerDB/index.ts` → `drizzle-orm/node-postgres/migrator` 跑 `packages/database/migrations/0000_init.sql ~ 0122_*.sql` 共 129 个迁移 | `package.json:58`,`scripts/migrateServerDB/index.ts:25-32` |
| **何时跑迁移** | `next build:vercel` 阶段 (`build:vercel` 脚本调用 `bun run db:migrate`),或 CI 独立跑 | `package.json:53` |
| **首次启动是否自动 migrate** | **否**!脚本是"启动前显式跑";`serverDB` 初始化 (`web-server.ts:14-22`) 只校验 `DATABASE_URL` + `KEY_VAULTS_SECRET`,**不跑迁移** | `packages/database/src/core/web-server.ts:14-25` |
| **S3 bucket 初始化** | 显式:`docker-compose/deploy/docker-compose.yml` 中 `rustfs-init` 容器跑 `mc mb "rustfs/lobe" --ignore-existing` | `docker-compose/deploy/docker-compose.yml:95-103` |
| **Redis** | `redis-server --save 60 1000 --appendonly yes`,数据持久化到 `redis_data` named volume | `docker-compose/deploy/docker-compose.yml:64-83` |
| **首用户** | Better-Auth 注册时自动 insert,无显式 seed | `schemas/betterAuth.ts:47` (account) |
| **数据库缺 migration** | 报 `extension "vector" is not available` 或 `users_email_unique` 时打印 hint | `scripts/migrateServerDB/errorHint.js` |

**Q3 结论 (Web)**:**显式 + 命令式初始化**,不在应用启动时自动建表;Postgres 16+ + pgvector 扩展必须预装;S3 桶和 Redis 持久化也是显式编排。

#### B. Desktop 端

| 步骤 | 行为 | 证据 |
|---|---|---|
| **首次启动** | `App.bootstrap()` → `StoreManager` 构造 → `new Store({name: 'lobehub-settings', defaults: STORE_DEFAULTS})` | `apps/desktop/src/main/core/infrastructure/StoreManager.ts:23-36` |
| **electron-store 文件创建** | 隐式,electron-store 首次 `get('storagePath')` 时若不存在,自动 `writeFile` 整个 JSON | `StoreManager.ts:30-34` |
| **appStorageDir 创建** | 显式:`makeSureDirExist(storagePath)`(递归 mkdir) | `StoreManager.ts:36`,`utils/file-system.ts:3-22` |
| **file-storage 子目录** | 隐式,首次 `uploadFile()` 时 `makeSureDirExist(targetDir)` 递归创建 | `services/fileSrv.ts:84-87`,`utils/file-system.ts` |
| **PG 初始化** | 桌面端通常**连远程 selfHost PG**;Desktop app **不内置本地 DB**,但保留 `lobehub-local-db/` 旧目录用于探测 | `controllers/SystemCtr.ts:234-247` |
| **二进制 (git / ffmpeg / claude)** | lazy download,`BinaryManager` 在首次 `installIfMissing` 时下载到 `<userData>/bin/<name>/<version>/` | `core/infrastructure/BinaryManager.ts:168-173,528-545` |
| **CLI 嵌入** | 构建期把 `apps/cli/dist/index.js` 复制为 `resources/bin/lobe-cli.js` | `electron-builder.mjs:121-124` |
| **Skill 缓存** | `prepareSkillDirectory()` lazy 创建 `<appStorageDir>/file-storage/skills/...` | `LocalFileCtr.ts:607,615` |
| **heteroAgent 目录** | lazy,首次 `getCacheDir()` / `getTracingDir()` 时创建 | `controllers/HeterogeneousAgentCtr.ts:680-690,1002` |

**Q3 结论 (Desktop)**:electron-store 隐式创建,**子目录按需 `mkdirSync({recursive:true})`**;PG 远程,无本地;**不跑 migration**。整体是 "**lazy 隐式创建**"。

#### C. CLI 端

| 步骤 | 行为 | 证据 |
|---|---|---|
| **首次调用** | `loadOrCreateConnectionId()` → `mkdirSync(SETTINGS_DIR, {mode:0o700, recursive:true})` + `writeFileSync(id, {mode:0o600})` | `apps/cli/src/settings/index.ts:73-82` |
| **首次设置** | `saveSettings()` 检测到全部默认 URL → `unlinkSync(SETTINGS_FILE)` (而不是创建空文件) | `apps/cli/src/settings/index.ts:52-67` |
| **首次登录** | `mkdirSync(CREDENTIALS_DIR, {mode:0o700, recursive:true})` + 加密写入 `credentials.json` | `apps/cli/src/auth/credentials.ts:30-46` |
| **首次 enroll workspace** | 同上,`workspace-enrollments.json` 首次写入 | `apps/cli/src/settings/index.ts:114-145` |
| **空目录** | 若全部是默认(没自定义 URL,没加入 workspace,没登录)→ `settings.json` 不存在,只保留一个 `connection-id` | `apps/cli/src/settings/index.ts:52-67,107-111` |

**Q3 结论 (CLI)**:**完全隐式,按需创建**;所有文件都 `mode: 0o600` (connection-id) 或 `0o700` (目录),credentials 加密。

#### Q3 一句话总览

| 端 | 初始化方式 | 自动建表? |
|---|---|---|
| Web | **显式**:`pnpm db:migrate` + 编排 S3 桶 + Redis volume | ❌ 必须在构建/部署时显式 migrate |
| Desktop | **隐式 + lazy**:electron-store 自动 JSON,子目录 `mkdirSync({recursive:true})` | N/A (不内置 DB) |
| CLI | **完全隐式**:首次调用时 `mkdirSync` + `writeFileSync` | N/A |

---

## 3. 关键代码片段

### 3.1 Desktop 端工作区根派生链

```ts
// apps/desktop/src/main/pre-app-init.ts:18-23
app.setName('lobehub-desktop-dev');
const userDataOverride = process.env.LOBE_DESKTOP_USER_DATA_DIR;
app.setPath('userData', userDataOverride || path.join(app.getPath('appData'), 'lobehub-desktop-dev'));

// apps/desktop/src/main/const/dir.ts:21-36
export const userDataDir = app.getPath('userData');
export const appStorageDir = path.join(userDataDir, 'lobehub-storage');
export const legacyLocalDbDir = path.join(appStorageDir, 'lobehub-local-db');
export const FILE_STORAGE_DIR = 'file-storage';
export const INSTALL_PLUGINS_DIR = 'plugins';                  // 注: 实际代码中未被使用 (仅测试引用)
export const LOCAL_STORAGE_URL_PREFIX = '/lobe-desktop-file';

// apps/desktop/src/main/const/store.ts:42-58
export const STORE_DEFAULTS: ElectronMainStore = {
  ...
  dataSyncConfig: { storageMode: 'cloud' },                   // 'cloud' (官方) | 'selfHost' (用户自托管)
  ...
  storagePath: appStorageDir,                                 // electron-store 中持久化"工作区根"
  ...
};

// apps/desktop/src/main/core/infrastructure/StoreManager.ts:23-36
this.store = new Store<ElectronMainStore>({ defaults: STORE_DEFAULTS, name: STORE_NAME });
runStoreMigrations(this.store);
const storagePath = this.store.get('storagePath');
makeSureDirExist(storagePath);                                // 递归 mkdir
```

### 3.2 PG 工厂 (服务端)

```ts
// packages/database/src/core/web-server.ts:14-48
if (!serverDBEnv.KEY_VAULTS_SECRET) {
  throw new Error(`KEY_VAULTS_SECRET is not set...`);
}
const connectionString = serverDBEnv.DATABASE_URL;
if (!connectionString) {
  throw new Error(`"DATABASE_URL" is not set correctly`);
}
if (serverDBEnv.DATABASE_DRIVER === 'node') {
  const client = new NodePool({ connectionString, ...timeoutConfig });
  client.on('error', (err) => { /* swallow to prevent crash */ });
  return nodeDrizzle(client, { schema });
}
// 默认走 Neon (WebSocket over edge / Vercel)
const client = new NeonPool({ connectionString, ...timeoutConfig });
return neonDrizzle(client, { schema });
```

### 3.3 pgvector 启用

```sql
-- packages/database/migrations/0005_pgvector.sql
CREATE EXTENSION IF NOT EXISTS vector;

-- 后续迁移在多个 vector 列上加 HNSW 索引
-- 例: packages/database/migrations/0037_add_user_memory.sql:100-111
CREATE INDEX "user_memories_summary_vector_1024_index"
  ON "user_memories" USING hnsw ("summary_vector_1024" vector_cosine_ops);
```

### 3.4 S3 路径生成

```ts
// src/services/upload.ts:22-45
const DEFAULT_S3_FILE_PATH = 'files';  // packages/env/src/file.ts:4
const generateFilePathMetadata = (originalFilename, options) => {
  const extension = originalFilename.split('.').at(-1);
  const filename = `${uuid()}.${extension}`;
  const date = (Date.now() / 1000 / 60 / 60).toFixed(0);
  const dirname = `${options.directory || fileEnv.NEXT_PUBLIC_S3_FILE_PATH}/${date}`;
  const pathname = options.pathname ?? `${dirname}/${filename}`;
  return { date, dirname, filename, pathname };
};
// 上传到 S3: pathname = "files/4945123/abc-uuid.png"
```

### 3.5 迁移命令

```jsonc
// package.json:53-58
"build:vercel": "cross-env-shell NODE_OPTIONS=--max-old-space-size=8192 \"bun run build:raw && bun run db:migrate\"",
"db:generate": "drizzle-kit generate && npm run workflow:dbml",
"db:migrate": "cross-env MIGRATION_DB=1 tsx ./scripts/migrateServerDB/index.ts",

// scripts/migrateServerDB/index.ts:25-32
const runMigrations = async () => {
  const { serverDB } = await import('../../packages/database/src/server');
  if (process.env.DATABASE_DRIVER === 'node') {
    await nodeMigrate(serverDB, { migrationsFolder });
  } else {
    await neonMigrate(serverDB, { migrationsFolder });
  }
  process.exit(0);
};
```

### 3.6 docker-compose 部署

```yaml
# docker-compose/deploy/docker-compose.yml (节选)
services:
  lobe:
    image: lobehub/lobehub
    environment:
      - 'DATABASE_URL=postgresql://postgres:${POSTGRES_PASSWORD}@postgresql:5432/${LOBE_DB_NAME}'
      - 'S3_ENDPOINT=${S3_ENDPOINT}'
      - 'S3_BUCKET=${RUSTFS_LOBE_BUCKET}'
      - 'REDIS_URL=redis://redis:6379'
      - 'REDIS_PREFIX=lobechat'
  postgresql:
    image: paradedb/paradedb:latest-pg17          # 必须带 pg_search
    volumes:
      - './data:/var/lib/postgresql/data'         # PG 数据持久化
    command: ['postgres', '-c', 'shared_preload_libraries=pg_search']
  rustfs:                                          # S3 兼容
    image: rustfs/rustfs:latest
    volumes:
      - 'rustfs-data:/data'                        # 对象存储持久化
  redis:
    image: redis:7-alpine
    volumes:
      - 'redis_data:/data'                         # AOF 持久化
```

---

## 4. 与 Onion Agent 设计的关联

| Onion Agent 关注点 | Lobe Chat 的做法 | 可借鉴 / 可规避 |
|---|---|---|
| **"工作区根"概念** | 三端独立,全部写死(桌面 `<userData>/lobehub-storage/`,CLI `~/.lobehub/`),**不跟随 CWD** | ✅ 可借鉴:明确区分"用户主目录"和"项目工作区";**规避 Lobe 缺"per-project workspace"**,Onion Agent 可以加 `--cwd` 或 `.onion/` 项目级状态 |
| **数据库** | 强绑定 PostgreSQL+pgvector,**没有 SQLite fallback**;129 个 migration,启动前必须显式跑 | ✅ 借鉴:schema 集中 (`packages/database/src/schemas/`) + migration 集中 (`packages/database/migrations/`);**规避 Lobe 重,Onion 可考虑 SQLite+vec 或文件式历史 (`session.json`)** |
| **文件存储** | Web 完全外置 S3(支持任意 S3 兼容:Cloudflare R2 / RustFS / MinIO / AWS S3);**Desktop 端不写 S3 而是写本地 `file-storage/` 模拟 S3** | ✅ 借鉴:统一文件接口,S3 路径约定 `files/<date>/<uuid>`;**规避 Lobe 双轨制,Onion 可统一"本地=S3 路径"** |
| **会话 / 历史** | `sessions` + `session_groups`(文件夹) + `topics`(多轮) + `threads`(分支) + `messages` 五张表,关系复杂 | ✅ 借鉴:session_group 是好设计(类似 ChatGPT 的 Projects);**规避 Lobe 的多表关联复杂,Onion 可考虑"session.json = 一切"的洋葱哲学** |
| **多 Agent** | `chat_groups` 表 + `chat_groups_agents` 关联表 + `chatGroupConfig jsonb`(调度规则) | ✅ 借鉴:用 join 表 + role 字段(`role: 'moderator' / 'participant'`, `order: 0/1/2`) + `enabled: boolean` |
| **Agent 配置** | `agents` 表 (单 agent) + `plugins jsonb[]` + `knowledge_bases_files` 关联;`chatConfig` / `agencyConfig` / `tts` 全部 `jsonb` | ✅ 借鉴:用 jsonb 存复杂子配置,避免表膨胀;**值得借鉴的细节: `marketIdentifier` 字段用于市场分发** |
| **知识库 (RAG)** | `knowledge_bases` → `files` (多对多) → `chunks` → `unstructured_chunks` → `embeddings vector(1024)`;`CHUNKS_AUTO_EMBEDDING=1` 默认开 | ✅ 借鉴:文件 → chunks → embeddings 三段,异步任务表 `async_tasks` 跟踪进度(`chunkTaskId`, `embeddingTaskId`) |
| **多租户** | `workspaces` + `workspace_members` + `workspace_user_settings` + 每张业务表带 `workspaceId` + `visibility ∈ {private, public}` | ⚠️ 多租户很重,Onion 如果做单机/单用户,**不需要**这一层;若做企业版可参考 |
| **初始化方式** | Web 显式 `pnpm db:migrate`;Desktop 隐式 lazy mkdir;CLI 隐式 lazy write | ✅ 借鉴三段:Database 显式 / 目录隐式 / 配置隐式;**Onion Agent 可以"init" 命令显式建 + 自动检测补全** |
| **环境变量 vs 配置文件** | 全 env(用 `@t3-oss/env-core` 强校验 + 12+ 个 env 模块),桌面额外用 `electron-store` JSON 持久化用户偏好 | ✅ 借鉴 `t3-oss/env-core` 这种集中校验;Desktop 用 store 而非 .env 是对的 |
| **市场数据** | Agent / Plugin 列表走**远端 URL**(`AGENTS_INDEX_URL`, `PLUGINS_INDEX_URL`) + **不在本地持久化** | ✅ 借鉴:市场数据是"流",不是"存";本地只 cache 选中项 |
| **加密** | API Key 走 `KEY_VAULTS_SECRET` AES 加密存 `user_settings.keyVaults`;CLI credentials 走 `aes-256-gcm` + pbkdf2 派生 | ✅ 借鉴:用户敏感数据用 master key 加密;CLI 派生用 hostname+username |
| **设备路径** | `app.getPath('userData' | 'appData' | 'home' | 'documents' | 'downloads' | 'pictures' | 'videos' | 'music' | 'desktop' | 'logs')` 全部透传到 renderer(`SystemCtr.ts:50-65`) | ✅ 借鉴:把 OS 路径作为 IPC 接口给 agent 调用,**给 agent"看见"用户机器**的能力 |
| **临时文件** | `<appStorageDir>/file-storage/uploads/` (legacy) + `heteroAgent/files/` | ✅ 借鉴:按用途分子目录 |

---

## 5. 不确定 / 未找到

1. **`@electric-sql/pglite` 仅出现在 `packages/database/src/core/getTestDB.ts:46` (测试用) 和 `packages/types/src/message/ui/chat.ts:226` (注释"待迁移到 pglite")**,**生产环境没有用 PGlite** — Lobe Chat 是 100% 远程 PG。
2. **`INSTALL_PLUGINS_DIR = 'plugins'`** 在 `apps/desktop/src/main/const/dir.ts:33` 定义,但 grep 全工程无生产代码使用 (只 `core/__tests__/App.test.ts:100` 和 `const/dir.ts` 本身),**桌面端"插件"实际由 tRPC 写到云端 PG,不在本地**。
3. **Desktop 端"工作区根"** 在 `STORE_DEFAULTS.storagePath` 默认 `appStorageDir = <userData>/lobehub-storage`,**但没找到 UI 允许用户改** `storagePath` 的入口(可能是预留 API),需要进一步确认。
4. **`LOBE_DESKTOP_USER_DATA_DIR` 是否被生产代码读取**:仅在 `pre-app-init.ts:20` 读取,但仅当 `electronIs.dev()` 为 true 时生效。**生产 build 下 userData 完全由 Electron 决定**,无法用 env 覆写 — 实际生产可能需要改 `package.json#name` 或 `electron-builder.mjs` 的 `appId`。
5. **`initClientDBStage` / `initClientDBMigrations`** 在 `src/store/global/initialState.ts:394-496` 定义,但 **未找到对应的 migration 加载逻辑** (估计在打包到 SPA 的 worker / IndexedDB 中,可能在 `apps/desktop` 之外的构建产物中)。
6. **`localFileWorkspaceRoots`** 在 `STORE_DEFAULTS` 中定义但未深入追代码 — 推测是 desktop 给 agent 工具调用授权的本地文件夹白名单。
7. **129 个 migration 文件** 完整列表未全部阅读,但从文件命名看涵盖 0000~0122,跨多个大版本迭代;**没有找到回滚机制**(`drizzle-orm` 默认不回滚)。
8. **Desktop 端是否支持 self-host 模式连本地 PG**:`dataSyncConfig.storageMode = 'selfHost'` 路径存在(`hooks/useUserAvatar.test.ts:132-139`),但具体自托管部署文档未深入调研。
9. **`agent_runtime_end` 事件** 在 `__tests__/HeterogeneousAgentCtr.test.ts:1481` 出现,异构 Agent (Codex / Claude Code) 协同机制存在,工作目录由 `apps/desktop/src/main/controllers/HeterogeneousAgentCtr.ts:1126` 的 `session.cwd || app.getPath('desktop')` 决定 — **这是桌面端唯一接近"跟随 CWD" 的设计**。
10. **没有 `init` / `setup` 之类的 CLI 子命令**,CLI 端是纯"运行-就创建"的纯 lazy 模式。
