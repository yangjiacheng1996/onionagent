# OpenHands — 工具调用（Tool Channel）调研报告

> 调研日期：2026-07-18
> 调研对象：[All-Hands-AI/OpenHands](https://github.com/All-Hands-AI/OpenHands) v1.36.0（转型期，正在向 `OpenHands/software-agent-sdk` 迁移）
> 调研方法：阅读 clone 下的源码 + `pyproject.toml` 依赖清单 + skills/README.md 文档

## 0. 智能体一句话定位

**OpenHands（原 OpenDevin）**：开源自主软件工程 Agent，**在隔离 Docker 沙箱里执行编码任务**（改文件、跑测试、提交 PR），由 LiteLLM 统一适配 OpenAI / Anthropic / Google / Bedrock 等多 Provider；2026 年正在从"单体 OpenDevin"转型为"OpenHands Agent Canvas（控制中心） + openhands-sdk（核心） + openhands-tools（工具集） + openhands-agent-server（沙箱运行时）"的四包架构。

## 1. 调研依据

### 1.1 源码路径

- `C:\workspace\github\onionagent\harness\01_market_research\clone\OpenHands\`

### 1.2 关键代码 / 配置文件

- `pyproject.toml` —— 顶层依赖（litellm / openhands-sdk / openhands-tools / openhands-agent-server / mcp / fastmcp / json-repair / tenacity）
- `openhands/app_server/config.py:75-92` —— `get_default_persistence_dir()`，`OH_PERSISTENCE_DIR` + `FILE_STORE_PATH` 双 env，默认 `~/.openhands/`
- `openhands/app_server/sandbox/sandbox_spec_service.py:120-141` —— `get_agent_server_image()`，沙箱镜像解析
- `openhands/app_server/sandbox/docker_sandbox_spec_service.py:39-58` —— Docker 沙箱 `working_dir='/workspace/project'`
- `openhands/app_server/sandbox/process_sandbox_service.py:429-444` —— Process 沙箱 `base_working_dir=tempfile.gettempdir()/openhands-sandboxes/`
- `openhands/app_server/file_store/{files,local,memory,s3,google_cloud}.py` —— `FileStore` 抽象（local/S3/GCS/memory 4 后端）+ atomic write
- `openhands/app_server/conversation_paths.py:11-79` —— `v1_conversations/{conversation_id_hex}/` 路径构造
- `openhands/app_server/user/skills_router.py:36-37` —— `GLOBAL_SKILLS_DIR` / `USER_SKILLS_DIR` 全局+用户级 skills 目录
- `openhands/app_server/app_conversation/skill_loader.py:32-49,455-540` —— `SkillInfo` 包含 `is_agentskills_format` 字段，**支持 Anthropic Agent Skills 格式**
- `openhands/app_server/app_conversation/app_conversation_service_base.py:100-170` —— `load_and_merge_all_skills()` 5 类 source 合并（public / user / project / org / marketplace）
- `openhands/app_server/app_conversation/live_status_app_conversation_service.py:1292-1352` —— `_add_system_mcp_servers()` + `_merge_custom_mcp_config()`，系统+用户 MCP 合并
- `openhands/app_server/app_conversation/live_status_app_conversation_service.py:1820-1840` —— `get_default_tools(enable_browser=True, enable_sub_agents=...)` 工具集装配
- `openhands/app_server/mcp/mcp_router.py:1-50` —— **OpenHands 自己实现的 MCP server**（FastMCP），把 `create_pr` / `create_mr` 暴露为 MCP 工具
- `openhands/app_server/settings/settings_models.py:20-39` —— `MCPConfig`（来自 fastmcp）+ `MCPServer`（来自 SDK）双导入

### 1.3 文档引用

- `README.md:1-50` —— "The source code for OpenHands Agent and Agent Server lives in OpenHands/software-agent-sdk" 确认核心代码正在迁出本仓库
- `skills/README.md:1-50` —— V0 microagents / V1 skills 双套术语；5 类 source（public / user / repo / org / marketplace）
- `skills/default-tools.md:1-15` —— `default-tools` skill 演示 `mcp_tools.stdio_servers` 配置方式
- `.agents/skills/cross-repo-testing/SKILL.md` —— **Anthropic Agent Skills 渐进式披露格式**（`SKILL.md` + frontmatter + `references/` 子目录）

## 2. 五个核心问题的回答

### Q1. 工具来源（内置 / MCP / Agent Skills）

#### 内置工具

- **核心工具集在 `openhands-tools==1.36.0` PyPI 包内**（本仓库未 vendor，依赖外部包），通过 `get_default_tools(enable_browser, enable_sub_agents)` 装配（`live_status_app_conversation_service.py:1829-1836`）
- 已知内置工具类别：
  - **Bash** —— `BashTool` 沙箱内 shell 执行
  - **FileEditor**（str_replace_editor）—— 文件读写/编辑
  - **Browser**（`browsergym-core==0.13.3` + `playwright==1.58.0`）—— 无头浏览器自动化
  - **IPythonKernel**（`jupyter-kernel-gateway==3.0.1`）—— 交互式 Python
  - **Planning** —— `get_planning_tools(plan_path=plan_path)` 单独的 plan agent 工具集（`live_status_app_conversation_service.py:1827`）
  - **Sub-agents** —— 多个内置子 agent（`get_registered_agent_definitions()`）
- 来源证据：`pyproject.toml:49` (`browsergym-core==0.13.3`), `pyproject.toml:57` (`playwright==1.58.0`), `pyproject.toml:46` (`jupyter-kernel-gateway==3.0.1`)

#### MCP 支持

- **是**。OpenHands 是 MCP 的**双重身份**：
  - **MCP Client**：通过 `agent_settings.mcp_config: MCPConfig` 字段接受用户配置（`settings_models.py:1060`），合并流程在 `live_status_app_conversation_service.py:1322-1352` 的 `_merge_custom_mcp_config()`
  - **MCP Server**：自建 FastMCP server（`mcp_router.py:1-50`），把 `create_pr` / `create_mr` / `create_bitbucket_pr` / `create_azure_devops_pr` 暴露为 MCP 工具供沙箱调用
- 配置：用户通过 settings API 注入 `mcp_config: {server_name: {url|command, ...}}`；运行时合并 `default`（系统级，proxy 到 Tavily search）+ 用户自定义
- 依赖：`mcp>=1.25` + `fastmcp>=3.2,<4`（`pyproject.toml:54-55`）

#### Agent Skills 支持

- **是**，且支持**两层格式**：
  1. **OpenHands 原生 microagent / skills 格式**：YAML frontmatter + markdown body，触发器 `triggers: [keyword, ...]` 或 `triggers: [/command, ...]`
     - 三层加载（`skills/README.md:55-58`）：公共 `OpenHands/skills/` + 用户 `~/.openhands/microagents/` + 仓库 `.openhands/microagents/` 或 `.openhands/skills/`
  2. **Anthropic Agent Skills 渐进式披露格式**：`SKILL.md` + `references/` 子目录，字段 `is_agentskills_format: bool`（`skill_loader.py:61`）
     - 本仓库示例：`.agents/skills/{cross-repo-testing,upcoming-release,update-sdk}/SKILL.md`
- 完整加载管线：5 个 source 合并（public / user / project / org / marketplace）走 `app_conversation_service_base.py:104-170` 的 `load_and_merge_all_skills()`，**单次 HTTP 调到 agent-server `/api/skills` endpoint**（`skill_loader.py:455-540`）

#### 其他工具类型

- **Hooks**（Pre/Post 事件钩子）—— `hook_loader.py` 从工作区 `.openhands/hooks/` 加载（`live_status_app_conversation_service.py:1872-1886`）
- **Marketplace plugins** —— 通过 `MarketplaceRegistration` 注册市场，plugin 按需加载（`settings_models.py` 全文件）
- **Provider 集成**（GitHub / GitLab / Bitbucket / Azure DevOps）—— `integrations/` 目录下

### Q2. 工具列表的生成、传递、格式

- **生成方式**：
  - 内置工具：`get_default_tools(enable_browser, enable_sub_agents)` 从 `openhands-tools` 包拉取
  - MCP 工具：`mcp_servers` dict 合并 `default`（系统 Tavily proxy）+ `user_mcp`（用户 settings）
  - Skills 工具：5 source 合并后注入 `agent_context.skills`
  - **总入口**：`live_status_app_conversation_service.py:1820-1850` 集中装配 `tools: list[Tool]`
- **传递方式**：**OpenAI `tools` 参数**（通过 LiteLLM 统一转换为 Anthropic / Google / Bedrock 等格式）
  - LiteLLM `litellm==1.84.1`（`pyproject.toml:60`）作为 Provider 无关 LLM 客户端
  - **不直接调用 OpenAI SDK** —— 走 LiteLLM，所以**多协议同时支持**（OpenAI / Anthropic / Google / Bedrock）
- **格式**：**JSON**（OpenAI function calling 标准）
  - MCP server 端点示例（`mcp_router.py:140-180`）：FastMCP `@mcp_server.tool()` 装饰器，参数用 `Annotated[T, Field(description=...)]`，符合 OpenAI 协议
- **prompt-as-tool**：**否**。OpenHands 走标准 function calling，**不混 XML 协议**
- **动态刷新**：**部分**。启动时一次性 `get_default_tools()` + 加载 `agent_settings.mcp_config`；用户可通过 settings API 改 `mcp_config` 字段，下次新建 conversation 生效；运行时新增 MCP 需重启 sandbox

#### 工具列表片段（MCP server 暴露的 create_pr）

```python
# mcp_router.py:140-180
@mcp_server.tool()
async def create_pr(
    repo_name: Annotated[str, Field(description='GitHub repository ({{owner}}/{{repo}})')],
    source_branch: Annotated[str, Field(description='Source branch on repo')],
    target_branch: Annotated[str, Field(description='Target branch on repo')],
    title: Annotated[str, Field(description='PR Title')],
    body: Annotated[str | None, Field(description='PR body')],
    draft: Annotated[bool, Field(description='Whether PR opened is a draft')] = True,
    labels: Annotated[list[str] | None, Field(description='...')] = None,
) -> str:
    """Open a PR in GitHub"""
```

#### `default-tools.md` Skill 演示 MCP stdio 配置

```yaml
# skills/default-tools.md
name: default-tools
type: repo
version: 1.0.0
agent: CodeActAgent
mcp_tools:
  stdio_servers:
    - name: "fetch"
      command: "uvx"
      args: ["mcp-server-fetch"]
```

### Q3. 工具调用指令的解析、错误修复、准确性

- **解析方式**：**OpenAI `tool_calls` 数组流式增量解析**（标准协议）
  - 实际解析逻辑在 `openhands-sdk` + `litellm==1.84.1` 内（**本仓库不持有这部分代码**）
  - 但本仓库通过 `from openhands.sdk import Agent` 和 `from openhands.sdk.llm import LLM`（`app_conversation_service_base.py:36-38`）使用 SDK 的 Agent/LLM 类
- **错误修复机制**：
  - `json-repair` 库被显式声明为依赖（`pyproject.toml:42`）—— 修复 LLM 返回的不完整/残缺 JSON
  - LiteLLM 内置 retry（`LLM_NUM_RETRIES` 通过 `AUTO_FORWARD_PREFIXES = ('LLM_', 'LMNR_')` 自动转发到沙箱，证据：`sandbox_spec_service.py:148-181`）
  - Pydantic v2 schema 校验（`base_model_config` 大量使用 `ConfigDict(extra='forbid')` 防止 schema drift）
- **准确性保证**：
  - Pydantic `BaseModel` + `Field(description=...)` 强 schema 约束
  - `Annotated[T, Field(description=...)]` 在 MCP 工具和 SDK 工具中广泛使用
  - `extra='forbid'` 配置（`file_store/files.py:13`）防止额外字段污染
  - **plan-then-act 模式**：`AgentType.PLAN` 用 `get_planning_tools(plan_path=plan_path)` 单独工具集，先规划后执行（`live_status_app_conversation_service.py:1826-1827`）
- **重试机制**：
  - LiteLLM 内部 retry（`tenacity==9.1.4` 在 `pyproject.toml:88`）
  - `LLM_NUM_RETRIES` 通过 env 注入到 sandbox
  - 工具执行失败时返回结构化 error message，LLM 看到后自动 retry（OpenAI 协议标准行为）
  - 工具重试上限由 LiteLLM 默认 + 用户 env 决定，**未在源码中显式 hardcode**

### Q4. 工具执行结果回传

- **回传方式**：
  - **OpenAI 协议**：`role: "tool"` + `tool_call_id` 关联（通过 LiteLLM 适配所有 provider）
  - **多协议同时支持**：LiteLLM 把 `tool_call_id` 翻译为 Anthropic `tool_use_id` / Google function call id / Bedrock 对应字段
- **格式**：**JSON / 结构化对象**
  - MCP 工具返回 `str`（FastMCP 自动 JSON 序列化）
  - 内置工具通过 Pydantic `ObservationEvent` 序列化（SDK 内实现）
- **通信协议**：**OpenAI 标准** + **多协议适配**（LiteLLM 抽象层）
  - `from openhands.sdk.llm import LLM`（`app_conversation_service_base.py:38`）确认走 SDK LLM
  - SDK LLM 内部走 LiteLLM → 适配 OpenAI / Anthropic / Google / Bedrock
- **大结果处理**：
  - **FileStore 抽象层**：工具输出大对象（trajectory、log、archive）不直接进 message，**先存 FileStore 再返回引用**（`file_store/files.py` 全文件）
  - 4 后端：`LocalFileStore`（atomic write） / `S3FileStore` / `GoogleCloudFileStore` / `InMemoryFileStore`
  - **事件存储独立**：`v1_conversations/{conversation_id_hex}/{event_id}.json` per-event JSON（`conversation_paths.py:11-79`）
  - 控制平面路径：`OH_PERSISTENCE_DIR` / `FILE_STORE_PATH` / 默认 `~/.openhands/`

### Q5. File Backend 是否为工具调用做了适配

**OpenHands 是 file_backend.md 中明确点名的"双层解耦"范例**（§3.2 控制平面 vs 工作区）：

#### 工具配置目录 / 文件清单

| 路径 | 作用 | 证据 |
|------|------|------|
| `~/.openhands/`（控制平面） | 用户 settings / conversation / 缓存 | `config.py:75-92` |
| `~/.openhands/microagents/` | 用户级 Skills / Microagents | `skills_router.py:37` |
| `~/.openhands/v1_conversations/{conv_id}/` | conversation 事件存储 | `conversation_paths.py:40-75` |
| `/workspace/project`（Docker 沙箱） | Agent 操作的代码 | `docker_sandbox_spec_service.py:50` |
| `<tempfile.gettempdir()>/openhands-sandboxes/<sandbox_id>/`（Process 沙箱） | Process 模式工作区 | `process_sandbox_service.py:429-435` |
| `<repo>/.openhands/microagents/` 或 `<repo>/.openhands/skills/` | 仓库级 skills | `skills/README.md:50-58` |
| `<repo>/.agents/skills/<name>/SKILL.md` | Anthropic Agent Skills 渐进式披露 | `.agents/skills/cross-repo-testing/SKILL.md` |
| `{org}/.openhands` GitHub 仓库 | org 级 skills（需用户授权） | `skill_loader.py:99-111` |

#### 加载代码（file:line）

- 控制平面 env 解析：`openhands/app_server/config.py:75-92`
- FileStore 抽象工厂：`openhands/app_server/file_store/__init__.py:11-22`
- atomic write（temp+rename）：`openhands/app_server/file_store/local.py:32-44`
- 沙箱 working_dir 解析：`openhands/app_server/sandbox/sandbox_spec_service.py`、`docker_sandbox_spec_service.py:50`
- 用户级 skills 加载：`openhands/app_server/user/skills_router.py:34-37, 78-141`
- 五源 skills 合并：`openhands/app_server/app_conversation/app_conversation_service_base.py:104-170`

#### 全局 vs 项目级 vs 两者

- **两者都有**（这是 OpenHands 的核心架构特征）
  - **控制平面（全局）**：`~/.openhands/` —— 配置、secrets、microagents、conversation 事件
  - **运行时（项目级 / 沙箱）**：`/workspace/project`（Docker）或 `<temp>/openhands-sandboxes/<id>/`（Process）—— Agent 实际操作的代码
- **项目级 skills**（`<repo>/.openhands/skills/`）独立于用户全局 skills
- **org 级 skills**（`{org}/.openhands` GitHub 仓库）是第三层（用户登录 + 加入的 org 都自动加载）

#### 与 `standard/file_backend.md` 对照

| 条款 | OpenHands 实践 | 一致性 |
|------|---------------|--------|
| §1.1 用户属主目录 + env 单一覆盖点 | `OH_PERSISTENCE_DIR`（新）+ `FILE_STORE_PATH`（旧 legacy fallback）| ✅ 略有冗余（2 个 env）|
| §1.2 控制平面 vs 工作区分离 | 显式：`~/.openhands/` vs `/workspace/project` | ✅ **典范** |
| §1.3 AGENTS.md 向上扫描到 .git | ❌ **未明确**（走 `.openhands/microagents/` 而不是 AGENTS.md） | ❌ 反例 |
| §1.4 secrets 独立 + 0o600 | 部分（`secrets_store_serializer` 在 `settings_models.py:1018` 排除 secret 值） | ⚠️ 不够严格 |
| §3.2 双层解耦 | ✅ 显式 | ✅ 典范 |
| §3.8 Bootstrap 种子文件 | ❌ 不自动 seed 任何文件 | ❌ |
| §3.9 项目级 scratch + .gitignore | ❌ 不主动 .gitignore | ❌ |
| §4.5 自动 git init | ✅ **默认开**（`init_git_in_empty_workspace=True`，`live_status_app_conversation_service.py:2749-2752`）| ❌ **反例**（file_backend.md §4.5 明确禁止）|
| §10.8 MCP 协议支持 | ✅ 双重身份（Client + Server） | ✅ |

## 3. 关键代码片段

### 3.1 工具集装配入口（5 source 合并）

```python
# openhands/app_server/app_conversation/live_status_app_conversation_service.py:1820-1850
# --- tools ----------------------------------------------------------
agent_definitions: list[Any] = []
tools: list[Tool]
if agent_type == AgentType.PLAN:
    plan_path = self._compute_plan_path(project_dir, git_provider)
    tools = get_planning_tools(plan_path=plan_path)
else:
    register_builtins_agents(enable_browser=True)
    profile_tools = user.agent_settings.tools
    if profile_tools is None:
        tools = get_default_tools(enable_browser=True,
                                  enable_sub_agents=user.agent_settings.enable_sub_agents)
    else:
        tools = profile_tools
```

### 3.2 MCP 双重身份（Client + Server）

```python
# openhands/app_server/mcp/mcp_router.py:1-50
import os
from fastmcp import Client, FastMCP
from fastmcp.client.transports import StreamableHttpTransport
from fastmcp.server import create_proxy

mcp_server = FastMCP('mcp', mask_error_details=True)  # 自身作为 MCP server

# 系统 MCP server 注入（Tavily proxy + create_pr 等）
async def _add_system_mcp_servers(self, mcp_servers, conversation_id):
    mcp_servers['default'] = MCPServer(
        url=f'{self.web_url}/mcp/mcp',
        headers={'X-OpenHands-ServerConversation-ID': SecretStr(str(conversation_id))},
    )
```

### 3.3 FileStore atomic write（file_backend §8.3 典范）

```python
# openhands/app_server/file_store/local.py:31-44
def write(self, path: str, contents: str | bytes) -> None:
    full_path = self.get_full_path(path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    mode = 'w' if isinstance(contents, str) else 'wb'
    # temp+rename atomic write
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

### 3.4 控制平面路径解析（双 env fallback）

```python
# openhands/app_server/config.py:75-92
def get_default_persistence_dir() -> Path:
    persistence_dir = os.getenv('OH_PERSISTENCE_DIR')      # 新 env
    if persistence_dir is None:
        persistence_dir = os.getenv('FILE_STORE_PATH')    # 旧 env（V0 兼容）
    if persistence_dir:
        result = Path(persistence_dir)
    else:
        result = Path.home() / '.openhands'               # 默认
    result.mkdir(parents=True, exist_ok=True)
    return result
```

### 3.5 Agent Skills 渐进式披露（`is_agentskills_format` 标志）

```python
# openhands/app_server/app_conversation/skill_loader.py:53-65
class SkillInfo(BaseModel):
    """Skill information from agent-server API response."""
    name: str
    content: str
    triggers: list[str] = []
    source: str | None = None
    description: str | None = None
    is_agentskills_format: bool = False   # ← 支持 Anthropic Agent Skills 格式
```

## 4. 与 Onion Agent 设计的关联

**Onion 可以学 OpenHands 的 5 个点**：

1. **双层解耦（控制平面 vs 沙箱）** —— OpenHands 用 `~/.openhands/` + `/workspace/project` 严格分离元数据与代码；Onion 应借鉴，把 `~/.onion/`（控制平面）和 `<repo>/.onion/scratch/`（项目级 scratch，file_backend.md §3.1 已采纳）落地为强约束。
2. **5 源 Skills 合并 + `is_agentskills_format` 标志** —— OpenHands 同时支持自家 microagent 格式 + Anthropic Agent Skills 渐进式披露；Onion 的 `memory/skills/` 目录可借鉴（`AGENTS.md` 优先 + `ONION.md` 备选 + `~/.agents/skills/<name>/SKILL.md` 三层）。
3. **MCP 双重身份（Client + Server）** —— OpenHands 把 `create_pr` / `create_mr` 暴露为 MCP server 供沙箱调用，Onion 可以把内部工具（如 `secret_get_api_key`）也暴露为 MCP server，给未来的多 agent / 多 runtime 留扩展点。
4. **FileStore 抽象 + atomic write** —— OpenHands 的 `FileStore` 4 后端 + `temp+rename` 是工业级实现，Onion `session.json` 写盘应强制走此模式（file_backend §8.3 已列入 P0）。
5. **Plan-then-Act 工具集分离** —— `AgentType.PLAN` 用 `get_planning_tools(plan_path=plan_path)` 单独工具集，先规划后执行，Onion 的 `update_plan` 工具可以借鉴这种"主 agent 工具 vs 规划工具"分组。

**Onion 应避免的 3 个反例**：

1. **`init_git_in_empty_workspace=True` 默认开**（file_backend §4.5 已明确禁止）—— OpenHands 这条反例要标注
2. **2 个 env（`OH_PERSISTENCE_DIR` + `FILE_STORE_PATH`）共存** —— Onion 应只保留 1 个 `ONION_HOME`，避免认知负担
3. **核心代码外迁到独立 PyPI**（`openhands-sdk` / `openhands-tools` / `openhands-agent-server`）—— 这导致本仓库只是"控制中心"，**工具调用细节全部丢失**；Onion 应保持核心代码 in-tree，便于研究和定制

## 5. 不确定 / 未找到

- **Q3 工具调用的实际解析代码**：本仓库不持有 —— `openhands-sdk` / `openhands-tools` / `litellm` 都是外部依赖。Onion 想研究 OpenHands 的"流式增量解析"细节，需要去 `OpenHands/software-agent-sdk` 独立仓库（README 提到正在迁出）
- **Q4 大结果的具体截断阈值**：源码未明确（应在 SDK `ObservationEvent` 内，本仓库不可见）
- **Q3 重试上限 hardcode**：LiteLLM `LLM_NUM_RETRIES` 通过 env 转发，但**默认值未在本仓库声明**，需查 LiteLLM 文档
- **`auto_load` marketplace 注册语义**：源码出现但**没有详细解释自动加载哪些 plugin**，需要进一步翻 `Marketplace` SDK 类
- **企业版（`enterprise/`）的特殊工具**：未调研，可能是定制化 MCP servers 或 skills

---

**报告完**。本调研侧重"V1 app_server + SDK 工具调用 + Skills 5 源合并"三条主线；OpenHands 转型期代码正在外迁，部分核心逻辑已不可见，已在第 5 节明确标注。
