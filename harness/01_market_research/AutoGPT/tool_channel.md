# AutoGPT — 工具调用（Tool Channel）调研报告

> 调研对象：`Significant-Gravitas/AutoGPT`（2026-07-13 时 185,496 ⭐）
> 调研时间：2026-07-19
> 调研方式：Read / Grep 静态分析（仅源码），不执行构建/运行命令
> 关注目录：`autogpt_platform/backend/`（新版 platform 平台）+ `classic/original_autogpt/`（老 monolithic 模式，仅作历史对照）
>
> **重要前提**：AutoGPT 仓库是 monorepo,内含两套完全不同的实现：
> 1. `autogpt_platform/backend/` —— 2024+ 重写的新版,基于 **graph + blocks** 的多 agent 平台(本报告主体)
> 2. `classic/original_autogpt/` —— 2023 年的初代 monolithic,基于 forge 库的 Command/CommandProvider(只列对照,详见 prompt_strategies/one_shot.py:280-323)
>
> 任务说明要求"关注 platform/ 和 autogpt/agent_server/",但**本仓库没有 `autogpt/agent_server/`**,实际是 `autogpt_platform/backend/`(把 platform 当成 agent server 看待)。

---

## 0. 智能体一句话定位

鼻祖级自主 AI Agent(2023-03 发布引爆 GitHub),2024+ 重写为多 agent 编排平台(`autogpt_platform`),**graph-based blocks 架构** + **双层工具体系**(blocks graph node + chat tool function calling)+ **MCP / Skills / Workspace** 三类工具来源 + 多 Provider(OpenAI / Anthropic / Groq / Ollama / OpenRouter)。

---

## 1. 调研依据

| 文件 | 作用 |
| --- | --- |
| `autogpt_platform/backend/backend/blocks/__init__.py:18-110` | `load_all_blocks()` —— 动态 importlib 扫描 `blocks/**/*.py` 注册所有 `*Block` 子类 |
| `autogpt_platform/backend/backend/blocks/_base.py:43-65` | `BlockType` 枚举(含 `MCP_TOOL`、`AGENT`)+ `BlockCategory` 枚举(20+ 类别) |
| `autogpt_platform/backend/backend/blocks/mcp/block.py:50-260` | `MCPToolBlock` —— 连接任意 MCP server、`list_tools` 后动态 schema |
| `autogpt_platform/backend/backend/blocks/agent.py:24-142` | `AgentExecutorBlock` —— 在 graph 中嵌套子 agent(共享 `parent_execution_id`) |
| `autogpt_platform/backend/backend/copilot/tools/base.py:115-200` | `BaseTool` + `as_openai_tool()` —— chat 工具转 OpenAI `ChatCompletionToolParam` |
| `autogpt_platform/backend/backend/copilot/tools/base.py:38-117` | 大输出处理:`_LARGE_OUTPUT_THRESHOLD=80_000` + workspace 持久化 + middle-out preview |
| `autogpt_platform/backend/backend/copilot/tools/skills.py:42-105` | Skills 注册表 + Anthropic Agent Skills 协议(`/skills/{slug}/SKILL.md`) |
| `autogpt_platform/backend/backend/copilot/tools/skills.py:248-250` | `SKILL_FOLDER = "/skills"` + path 构造 `f"{SKILL_FOLDER}/{name}/SKILL.md"` |
| `autogpt_platform/backend/backend/copilot/sdk/agent_generation_guide.md` | 内置 seed skill 示例(Anthropic Agent Skills 协议) |
| `autogpt_platform/backend/backend/util/llm/providers.py:133-328` | `ProviderResponse` 标准化 + `call_provider()` 6-provider 调度(openai / anthropic / groq / ollama / openrouter / ...) |
| `autogpt_platform/backend/backend/util/llm/conversions.py:50-160` | `convert_openai_tool_fmt_to_anthropic()` + `extract_openai_tool_calls()`(从 `response.choices[0].message.tool_calls` 提取) |
| `autogpt_platform/backend/backend/util/llm/tool_use.py:1-100` | `pydantic_to_anthropic_tool()` + `force_tool_choice()` —— Pydantic 模型 → 强制 tool_choice |
| `autogpt_platform/backend/backend/util/prompt.py:323-470` | `_extract_tool_call_ids_from_message` / `_remove_orphan_tool_responses` / `validate_and_remove_orphan_tool_responses` 三件套(orphan 校验 + 修复) |
| `autogpt_platform/backend/backend/util/prompt.py:619-660` | `_ensure_tool_pairs_intact()` —— 上下文压缩时保证 tool_call/tool_response 配对完整 |
| `autogpt_platform/backend/backend/util/retry.py:170-215` | `create_retry_decorator` + `func_retry` —— tenacity-based retry(max_attempts=5 / max_wait=30s / jitter) |
| `autogpt_platform/backend/backend/util/retry.py:285-345` | `_StopOnShutdown` + `_interruptible_async_sleep` —— SIGINT/SIGTERM 即时中断 retry |
| `classic/original_autogpt/autogpt/agents/agent.py:285, 382` | classic 版 `CommandProvider.get_commands` 走 forge 库 pipeline |
| `classic/original_autogpt/autogpt/agents/prompt_strategies/one_shot.py:280-323` | classic 版 native tool calling 解析:`response.tool_calls[0].function` |

文档 / README 引用：
- `autogpt_platform/backend/backend/copilot/tools/skills.py:1-25`(docstring)—— Skills 协议说明(YAML frontmatter + `references/` `scripts/` `assets/`)
- `autogpt_platform/backend/backend/copilot/sdk/agent_generation_guide.md` + `mcp_tool_guide.md` —— 内置 2 个 seed skills,说明 Skills 即 SKILL.md

---

## 2. 五个核心问题的回答

### Q1. 工具来源

**AutoGPT 平台把工具分成三大类,每类都有专门的"工具客户端"适配**:

#### 1.1 内置工具:Blocks(graph node)+ Chat Tools(function calling)

**Blocks(在 graph 中作为节点)—— 100+ 个,分布在 36 个子目录**:

| 类别 | 数量级 | 关键子目录 | 代表 Block |
| --- | --- | --- | --- |
| **AI / LLM** | 多个 | `blocks/llm.py` + `blocks/ai_condition.py` | `AITextGeneratorBlock` `AIConditionBlock` `LLMCallBlock`(支持 7 个 LLM provider) |
| **MCP** | 1 个通用 + 按 server 动态 | `blocks/mcp/` | `MCPToolBlock` —— 连接任意 MCP server,前端 dropdown 选 tool |
| **Social** | 多平台 | `discord/` `slack/` `twitter/` `telegram/` | `DiscordSendMessageBlock` `SlackPostMessageBlock` |
| **Productivity** | 多 SaaS | `github/` `notion/` `linear/` `todoist/` `hubspot/` `airtable/` | 8 个 GitHub block(issues / PR / commits / reviews)+ Notion / Linear blocks |
| **Search** | 6+ | `exa/` `jina/` `firecrawl/` `dataforseo/` | `ExaSearchBlock` `JinaScrapeBlock` `FirecrawlCrawlBlock` |
| **Multimedia** | 多个 | `video/` `replicate/` `fal/` `nvidia/` `bannerbear/` | 视频生成 / 图像生成 / TTS |
| **Communication** | 多个 | `agent_mail/` `smartlead/` `discord/` | `AgentMailInboxBlock` `SendEmailBlock` |
| **Code** | 1+ | `blocks/codex.py` | `CodexBlock`(对接 OpenAI Codex) |
| **System** | 2+ | `blocks/system/` | `FileStoreBlock` `BlockInstallationBlock` |
| **Agent** | 2+ | `blocks/agent.py` `blocks/orchestrator.py` | `AgentExecutorBlock`(嵌套子 agent)+ `OrchestratorBlock`(循环 agent) |

**Chat Tools(直接 function calling 给 LLM)—— 50+ 个,集中在 `copilot/tools/`**:

| 类别 | 数量 | 典型 tool |
| --- | --- | --- |
| **Agent 构造 / 编辑** | 6+ | `create_agent` `edit_agent` `fix_agent` `customize_agent` `validate_agent` `find_agent` |
| **Block 发现 / 测试** | 4+ | `find_block` `run_block` `test_dry_run` `continue_run_block` |
| **代码执行 / 沙箱** | 3+ | `bash_exec`(本地)+ `e2b_sandbox`(云端 e2b)+ `sandbox` |
| **Web 抓取** | 2+ | `web_search` `web_fetch` `get_doc_page` |
| **Skill 管理** | 4+ | `store_skill` `read_skill` `list_skills` `delete_skill` |
| **文件 / 工作区** | 4+ | `read_workspace_file` `write_workspace_file` `workspace_files` `manage_folders` |
| **MCP 调用** | 1+ | `run_mcp_tool`(运行时连接 MCP server 调用单个 tool) |
| **MCP / Skill 发现** | 2 | `get_mcp_guide` `get_agent_building_guide` |
| **子 session / graphiti 知识** | 5+ | `run_sub_session` `get_sub_session_result` `graphiti_search` `graphiti_store` `graphiti_forget` |
| **IDEAS / 杂项** | 5+ | `ask_question` `decompose_goal` `add_understanding` `agent_output` `IDEAS` `todo_write` |

**关键代码证据**(`backend/blocks/__init__.py:18-48`):

```python
@cached(ttl_seconds=3600)
def load_all_blocks() -> dict[str, type["AnyBlockSchema"]]:
    # ...
    modules = []
    for f in current_dir.rglob("*.py"):
        if not f.is_file() or f.name == "__init__.py" or f.name.startswith("test_"):
            continue
        module_path = str(relative_path)[:-3].replace(os.path.sep, ".")
        modules.append(module_path)
    for module in modules:
        importlib.import_module(f".{module}", package=__name__)
    # Load all Block instances from the available modules
    available_blocks: dict[str, type["AnyBlockSchema"]] = {}
    for block_cls in _all_subclasses(Block):
        if not block_cls.__name__.endswith("Block"):
            raise ValueError(...)
        block = block_cls()
        if not isinstance(block.id, str) or len(block.id) != 36:
            raise ValueError(...)
        available_blocks[block.id] = block_cls
    return available_blocks
```

→ **全程序启动时 rglob 扫一遍 `blocks/**/*.py`**,自动注册所有 `*Block` 结尾的类(必须以 `Block` 结尾、必须 36 字符 UUID id),1 小时 `@cached` 缓存。

#### 1.2 MCP 支持:有,但不是传统 `.mcp.json` 配置文件

**MCP 接入方式有两种**:

1. **`MCPToolBlock`**(`blocks/mcp/block.py:50-260`)—— graph 节点型:
   - 用户在 builder UI 提供 `server_url` + 可选 OAuth credentials
   - 后端 `MCPClient.initialize()` 列工具 → 前端 dropdown 选 tool
   - 选完后 `tool_input_schema` 动态注入 → block 自动校验 required 字段
   - 一次 graph 节点 = 一个 MCP tool call(可执行多次)
   - **关键代码**:`block.py:80-85` `get_input_schema()` 返回 `data["tool_input_schema"]`,实现 input schema 动态化

2. **`run_mcp_tool`** chat tool(`copilot/tools/`)—— function calling 型:
   - LLM 在 chat 中调用,直接传 `server_url` + `tool_name` + `arguments`
   - 用 `parse_mcp_content()` 解析 MCP 内容(支持 `text` / `image` / `embedded resource`)
   - 输出错误时 yield `"error"` 字段给 LLM

**MCP 凭证发现**:`block.py:209-213` `_auto_lookup_credential()` 按 `normalize_mcp_url(server_url)` 在 user 的 credentials 库里自动查找 OAuth2 token。

**配置方式**:无传统 `.mcp.json` 文件。MCP server 是用户每次用时**动态配置**(UI 表单或 LLM 透传),凭证存数据库(`OAuth2Credentials` 表)。**`ProviderName.MCP`** 是 provider 名(`blocks/mcp/block.py:73`)。

#### 1.3 Agent Skills 支持:有,Anthropic Agent Skills 协议

**完全按 Anthropic Agent Skills 协议实现**(YAML frontmatter + markdown body + 渐进式披露):

**文件位置**:`workspace://skills/{slug}/SKILL.md`(`copilot/tools/skills.py:248-250`)

**目录结构**(每个 skill 一个文件夹):
```
workspace://skills/
├── agent_building_guide/        # 内置 seed skill
│   ├── SKILL.md                 # 必有,YAML frontmatter + markdown
│   ├── references/              # 可选
│   ├── scripts/                 # 可选
│   └── assets/                  # 可选
├── oauth_flow/                  # 用户自蒸馏
└── ...
```

**关键代码证据**(`copilot/tools/skills.py:1-25` docstring):

```
Skills follow the Anthropic Agent Skills protocol — each skill is a
folder under workspace://skills/{slug}/ containing a SKILL.md file
with YAML frontmatter (name, description, optional triggers/version)
plus a markdown body. Optional sibling references/, scripts/, and
assets/ files live in the same folder and are reachable via
read_workspace_file.
```

**关键代码证据**(`copilot/tools/skills.py:248-250`):

```python
SKILL_FOLDER = "/skills"
# ...
def skill_md_path(name: str) -> str:
    return f"{SKILL_FOLDER}/{name}/SKILL.md"
```

**Schema 校验**(`copilot/tools/skills.py:130-145`):

| 限制 | 值 | 作用 |
| --- | --- | --- |
| `MAX_USER_SKILLS` | 50 | 单用户 skill 上限 |
| `MAX_NAME_CHARS` | 64 | skill name 长度 |
| `MAX_DESCRIPTION_CHARS` | 250 | skill 描述长度 |
| `MAX_BODY_CHARS` | 20_000 | SKILL.md body 长度 |
| `MAX_TRIGGERS` | 10 | triggers 数量 |
| `MAX_TRIGGER_CHARS` | 64 | 每个 trigger 长度 |
| `SKILLS_INDEX_CACHE_TTL_S` | 60s | Redis 索引缓存 |

**Skill 发现机制**(`backend/copilot/service.py:inject_user_context`):
- 每个 turn 第一个 user message 注入 `<available_skills>...</available_skills>` 块
- 包含全部 skill 的 name + description + triggers
- 模型调用 `read_skill(name=...)` 读完整 body
- 写入用 `store_skill`

**默认 seed skills**(`copilot/sdk/agent_generation_guide.md` + `mcp_tool_guide.md`):
- `agent_building_guide` —— 教模型如何构建 agent
- `mcp_tool_guide` —— 教模型如何用 MCP tools
- 都是只读,`store_skill` 拒绝覆盖

**关键证据**(`copilot/tools/skills.py:227-242`):

```python
# /skills/{slug}/SKILL.md.  We construct a *session-less*
# WorkspaceManager so the skill lives at the user level (not scoped
# to any chat session) — deleting the chat shouldn't lose user skills.
# Redis lock key for serialising store_skill writes per user. A per-user
# lock prevents two concurrent store_skill calls from both passing the
# MAX_USER_SKILLS check.
```

#### 1.4 其他工具类型

- **Graph 嵌套 agent**:`AgentExecutorBlock`(`blocks/agent.py`)在 graph 里执行子 graph,共享 `parent_execution_id`
- **Orchestrator**:`OrchestratorBlock`(循环 agent 模式,plan + execute 循环)
- **Webhooks**:`BlockType.WEBHOOK` + `BlockType.WEBHOOK_MANUAL`(共 2 种),`get_webhook_block_ids()` 识别
- **Human-in-the-loop**:`BlockType.HUMAN_IN_THE_LOOP`,`get_human_in_the_loop_block_ids()` 识别
- **AI 条件**:`AIConditionBlock`(`blocks/ai_condition.py`)—— LLM 判断 true/false,用于 graph 分支
- **Generic webhook**:`blocks/generic_webhook/`(接收外部 HTTP)

---

### Q2. 工具列表的生成、传递、格式

#### 2.1 工具列表生成:动态 + 缓存

**Blocks 端**:
- `load_all_blocks()`(`blocks/__init__.py:18-48`)启动期扫 `blocks/**/*.py` 注册所有 `*Block` 类
- `@cached(ttl_seconds=3600)` 缓存 1 小时
- 验证项:类名以 `Block` 结尾、`id` 是 36 字符 UUID、id 唯一、`error` 字段类型是 `str`

**Chat tools 端**:
- 手动注册在 `copilot/tools/` 目录,每个 tool 是 `BaseTool` 子类
- `requires_auth` / `is_available` 控制 LLM 可见性(认证失败或环境变量缺失 → 不暴露给 LLM)
- **关键证据**(`copilot/tools/base.py:135-150`):
  ```python
  @property
  def is_available(self) -> bool:
      """Override to check required env vars, binaries, or other dependencies.
      Unavailable tools are excluded from the LLM tool list so the model is
      never offered an option that will immediately fail."""
      return True
  ```

#### 2.2 传递方式:多 provider / 多协议

**AutoGPT 是 Provider 无关的**,通过 `util/llm/providers.py:133-328` 统一调度:

```python
# providers.py:181-330(摘录)
async def call_provider(
    *, provider: ProviderLiteral, model: str, api_key: str,
    messages: list[dict], max_tokens: int, temperature: float | None = None,
    execution_mode: ExecutionMode = "sync",
    tools: list[dict] | None = None,
    tool_choice: dict | None = None,
    force_json_output: bool = False,
    parallel_tool_calls: bool | openai.Omit = openai.omit,
    ...
) -> ProviderResponse | BatchSubmissionRef:
```

支持的 7 种 provider(`util/llm/providers.py:1-50` + `blocks/llm.py:60-78`):

| Provider | 调用 SDK | 工具格式 |
| --- | --- | --- |
| `openai` | `AsyncOpenAI.responses.create()`(Responses API) | OpenAI Responses tool |
| `anthropic` | `AsyncAnthropic.messages.create()` | Anthropic `input_schema` |
| `groq` | `AsyncOpenAI` (兼容 endpoint) | OpenAI tool |
| `ollama` | 本地 HTTP | OpenAI tool(兼容) |
| `openrouter` | `AsyncOpenAI(base_url=OPENROUTER)` | OpenAI tool + 转发 |
| `llama_api` | OpenAI 兼容 | OpenAI tool |
| `v0` | OpenAI 兼容 | OpenAI tool |
| `aiml_api` | OpenAI 兼容 | OpenAI tool |

**所有 provider 用同一份 `ProviderResponse` 标准化**(`util/llm/providers.py:133-165`):

```python
@dataclass(slots=True)
class ProviderResponse:
    content: str
    prompt_tokens: int
    completion_tokens: int
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    tool_calls: list[ToolContentBlock] | None = None
    reasoning: str | None = None
    cost_usd: float | None = None
    raw_response: Any = Field(default=None, repr=False, exclude=True)
```

#### 2.3 格式:JSON(OpenAI Chat Completions 协议)

**所有 chat tool 走 OpenAI 协议**(`copilot/tools/base.py:131-140`):

```python
def as_openai_tool(self) -> ChatCompletionToolParam:
    """Convert to OpenAI tool format."""
    return ChatCompletionToolParam(
        type="function",
        function={
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        },
    )
```

**OpenAI → Anthropic 自动转换**(`util/llm/conversions.py:50-87`):

```python
def convert_openai_tool_fmt_to_anthropic(
    openai_tools: list[dict] | None = None,
) -> Iterable[ToolParam] | anthropic.NotGiven:
    if not openai_tools or len(openai_tools) == 0:
        return anthropic.NOT_GIVEN  # Anthropic 拒绝空 tools 数组
    anthropic_tools: list[ToolParam] = []
    for tool in openai_tools:
        function_data = tool["function"] if "function" in tool else tool
        anthropic_tool: ToolParam = {
            "name": function_data["name"],
            "description": function_data.get("description", ""),
            "input_schema": {
                "type": "object",
                "properties": function_data.get("parameters", {}).get("properties", {}),
                "required": function_data.get("parameters", {}).get("required", []),
            },
        }
```

**Pydantic → Anthropic 强制 tool_choice**(`util/llm/tool_use.py:55-67`):

```python
def force_tool_choice(tool_name: str) -> dict[str, Any]:
    return {
        "type": "tool",
        "name": tool_name,
        "disable_parallel_tool_use": True,
    }
```

→ 用法:Pydantic 模型 → `pydantic_to_anthropic_tool()` 转 tool 定义 → `force_tool_choice()` 强制 Claude **只调用这一个 tool**,**不输出任何 prose / markdown**(`tool_use.py:11-15` docstring)。

**简化 tool 列表片段示例**(基于 `as_openai_tool` 转换):

```json
[
  {
    "type": "function",
    "function": {
      "name": "bash_exec",
      "description": "Execute a shell command on the user's local machine",
      "parameters": {
        "type": "object",
        "properties": {
          "command": {"type": "string", "description": "Shell command to run"},
          "timeout": {"type": "integer", "default": 30}
        },
        "required": ["command"]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "read_skill",
      "description": "Load a skill's full SKILL.md body by name",
      "parameters": {
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "required": ["name"]
      }
    }
  }
]
```

#### 2.4 prompt-as-tool:否

**AutoGPT 不走 prompt-as-tool 模式**(无 XML 协议 + 无 finish 标签)。所有工具通过标准 function calling 协议(JSON 格式 `tools` 参数),符合 OpenAI / Anthropic / Groq 标准。

但有两个边界:
- **block 的 `description`** 字段可写很长的 markdown 提示,让 LLM 知道何时调用(`SchemaField(description=...)` 在 `block.py:73-110` 随处可见)
- **Skill 的 `description`** 注入到 `<available_skills>` 块(`copilot/service.py:inject_user_context`),提示词式暴露

#### 2.5 动态刷新:部分

- **Blocks**:`@cached(ttl_seconds=3600)`,1 小时 TTL,期间新增 block 需重启
- **Chat tools**:`is_available` 是 `property`,每次 chat turn 重新求值(`base.py:142-150`)
- **Skills**:60s Redis 缓存 + store/delete 时显式失效(`SKILLS_INDEX_CACHE_TTL_S = 60`)
- **MCP tools**:`MCPToolBlock.run()` 每次执行都重新 `MCPClient.initialize()` 列工具,**完全动态**

---

### Q3. 工具调用指令的解析、错误修复、准确性

#### 3.1 解析方式

**OpenAI Chat Completions / Responses**:`util/llm/conversions.py:139-160`:

```python
def extract_openai_tool_calls(response: Any) -> list[ToolContentBlock] | None:
    if not response.choices:
        logger.warning("LLM response has empty choices in extract_openai_tool_calls")
        return None
    if response.choices[0].message.tool_calls:
        return [
            ToolContentBlock(
                id=tool.id,
                type=tool.type,
                function=ToolCall(
                    name=tool.function.name,
                    arguments=tool.function.arguments,
                ),
            )
            for tool in response.choices[0].message.tool_calls
        ]
    return None
```

**Anthropic Messages**(`util/llm/providers.py:580-605`):

```python
for content_block in resp.content:
    if content_block.type == "tool_use":
        if tool_calls is None:
            tool_calls = []
        tool_calls.append(
            ToolContentBlock(
                id=content_block.id,
                type=content_block.type,
                function=ToolCall(
                    name=content_block.name,
                    arguments=json_module.dumps(content_block.input),
                ),
            )
        )
```

→ 全部统一为 `ToolContentBlock(id, type, function: ToolCall(name, arguments))`(Pydantic 模型)。

**流式解析**:**当前主路径走 non-streaming**(`provider.call_provider` 是 `await ... completions.create()` 无 `stream=True`),但**流式能力已具备**:
- `blocks/codex.py:6` 导入 `from openai.types.responses import Response as OpenAIResponse` 表明支持 Responses API 流式
- `clients.py:283-289` 注释提到 `cache_control, tool-use forced structured output` 配套
- 暂无 `stream=True` 的 chat tool 主流程,推断 streaming 主要用于 SSE 推送进度给前端(`executor/activity_status_generator.py`)

#### 3.2 错误修复机制

**多层修复链**:

1. **JSON schema 校验** —— **MCP 工具**:`blocks/mcp/block.py:99-104` `get_mismatch_error()` 调 `validate_with_jsonschema()` 验证参数
   ```python
   @classmethod
   def get_mismatch_error(cls, data: BlockInput) -> str | None:
       tool_schema = cls.get_input_schema(data)
       if not tool_schema:
           return None
       tool_arguments = data.get("tool_arguments", {})
       return validate_with_jsonschema(tool_schema, tool_arguments)
   ```
2. **Orphan tool_result 修复** —— `util/prompt.py:323-595` 三件套:
   - `_extract_tool_call_ids_from_message` —— 从 assistant 消息提取所有 tool_call id
   - `_extract_tool_response_ids_from_message` —— 从 tool_response 提取 tool_call_id
   - `validate_and_remove_orphan_tool_responses` —— 移除无对应 tool_call 的孤儿 tool_response
   - `_ensure_tool_pairs_intact` —— 上下文压缩时,把孤立的 tool_call/tool_response 配对保留(从历史里向前找 assistant)
3. **UTF-8 sanitize** —— `util/llm/conversions.py:164-180` `sanitize_messages_for_utf8()` 修 unpaired surrogate
4. **Anthropic 温度兼容** —— `util/llm/providers.py:122-130` `_is_temperature_deprecation_error` 自我修复:新模型去掉 `temperature` 重试
5. **空 tools 数组** —— `convert_openai_tool_fmt_to_anthropic()` 返 `anthropic.NOT_GIVEN` 而非空 list
6. **空 content 防御** —— `classic/one_shot.py:280-292` GPT-5 无 content 时只返 tool_calls → 用默认 thoughts 字典

#### 3.3 准确性保证

| 机制 | 文件:行 | 说明 |
| --- | --- | --- |
| **schema 校验** | `blocks/mcp/block.py:99-104`、`blocks/agent.py:62-68` | JSonschema 校验 tool args / agent input |
| **required 字段检查** | `blocks/mcp/block.py:227-237` | 缺 required 字段 → yield `"error"` 提前 return |
| **force tool_choice** | `util/llm/tool_use.py:55-67` | 强制 Claude 只调一个 tool,无 prose 干扰 |
| **plan-then-act** | `OrchestratorBlock` | plan + execute 两阶段 |
| **tool_choice="auto" 默认** | `provider.call_provider` | 让模型自由选 tool |

#### 3.4 重试机制

**tenacity-based retry,默认值 max_attempts=5**(`util/retry.py:170-215`):

```python
def create_retry_decorator(
    max_attempts: int = 5,
    exclude_exceptions: tuple[type[BaseException], ...] = (),
    max_wait: float = 30.0,
    context: str = "",
    reraise: bool = True,
):
    stop = stop_after_attempt(max_attempts) | _StopOnShutdown()
    wait = wait_exponential_jitter(max=max_wait)
```

- **`func_retry = create_retry_decorator(max_attempts=5)`**(默认 5 次)
- **`conn_retry`**(infra 连接,默认 100 次)用于 Redis/RabbitMQ/DB
- **`continuous_retry`**(无限循环,常用于 RabbitMQ consumer)
- **`_StopOnShutdown`** + `_interruptible_async_sleep` —— SIGINT/SIGTERM 立即中断
- **`EXCESSIVE_RETRY_THRESHOLD = 50`** 触发 Discord 告警(`retry.py:18`)
- **LLM 看到错误后 retry**:`func_retry` 装饰 LLM 调用函数,error 自动重抛 → LLM 下一轮看到 error 自行调别的 tool

---

### Q4. 工具执行结果回传

#### 4.1 回传方式:OpenAI `role=tool` + Anthropic `tool_result` block(都支持)

**OpenAI Chat Completions 格式**(`util/prompt.py:378-410`):

```python
def _extract_tool_response_ids_from_message(msg: dict) -> set[str]:
    """OpenAI Chat Completions: {"role": "tool", "tool_call_id": "..."}"""
    # OpenAI Chat Completions format: role=tool with tool_call_id
    if msg.get("role") == "tool":
        tc_id = msg.get("tool_call_id")
        if tc_id:
            ids.add(tc_id)
```

**Anthropic Messages 格式**(`util/prompt.py:395-410`):

```python
# Anthropic format: content list with tool_result blocks
content = msg.get("content")
if isinstance(content, list):
    for block in content:
        if isinstance(block, dict) and block.get("type") == "tool_result":
            tc_id = block.get("tool_use_id")
            if tc_id:
                ids.add(tc_id)
```

**OpenAI Responses API 格式**(`util/prompt.py:358-365`):

```python
# Responses API: standalone function_call_output item
if msg.get("type") == "function_call_output":
    if call_id := msg.get("call_id"):
        ids.add(call_id)
    return ids
```

→ **三种协议全自动识别、互转**(同一份 `validate_and_remove_orphan_tool_responses` 函数同时处理三种格式)。

#### 4.2 格式:JSON 字符串(`model_dump_json`)

**关键证据**(`copilot/tools/base.py:175-180`):

```python
try:
    result = await self._execute(user_id, session, **kwargs)
    raw_output = result.model_dump_json(exclude_none=True)
    if (len(raw_output) > _LARGE_OUTPUT_THRESHOLD and user_id and session.session_id):
        raw_output = await _persist_and_summarize(...)
```

→ **默认 result 是 Pydantic BaseModel**,`model_dump_json(exclude_none=True)` 转 JSON 字符串塞回 message content。

**Output 类型**(`backend/blocks/_base.py:43-65`):`BlockSchemaOutput` 也是 Pydantic,统一序列化。

#### 4.3 通信协议:多协议并行

| 协议 | 输入 | 输出 | 适用 |
| --- | --- | --- | --- |
| **OpenAI Chat Completions** | `tools=[ChatCompletionToolParam]` `tool_choice=auto` | `response.choices[0].message.tool_calls` | GPT-4o / GPT-5 / OpenRouter 兼容 |
| **OpenAI Responses API** | `tools=[Tool]` | `response.output` 含 `function_call` | OpenAI 新版(`blocks/codex.py`) |
| **Anthropic Messages** | `tools=[ToolParam]` `tool_choice={type, name}` | `resp.content` 含 `tool_use` block | Claude 全系 |
| **Groq** | OpenAI 兼容 | OpenAI 兼容 | Llama / Mixtral |
| **Ollama** | OpenAI 兼容 | OpenAI 兼容 | 本地模型 |

**统一抽象**:`ProviderResponse.tool_calls: list[ToolContentBlock]` —— 不管上游什么协议,下游一律按 `ToolContentBlock(id, type, function: ToolCall(name, arguments))` 处理。

#### 4.4 大结果处理:**workspace 持久化 + middle-out preview**(非常优雅)

**关键证据**(`copilot/tools/base.py:26-37`):

```python
# Persist full tool output to workspace when it exceeds this threshold.
_LARGE_OUTPUT_THRESHOLD = 80_000

# Character budget for the middle-out preview.  The total preview + wrapper
# must stay below BOTH:
#   - _MAX_TOOL_OUTPUT_SIZE (100K) in response_model.py (our own truncation)
#   - Claude SDK's ~100 KB tool-result spill-to-disk threshold
_PREVIEW_CHARS = 95_000
```

**处理流程**(`base.py:84-117`):

1. `raw_output = result.model_dump_json(...)`
2. 如果 `len(raw_output) > 80_000`:
   - 写到 workspace:`tool-outputs/{tool_call_id}.json`(`workspace://` 协议)
   - 用 `truncate()` middle-out 截 95K preview
   - 末尾追加 retrieval 提示:`Use read_workspace_file(path="tool-outputs/{tool_call_id}.json", offset=<char_offset>, length=50000) to read any section`
3. 包成 `<tool-output-truncated total_chars=N workspace_path="...">{preview}{retrieval}</tool-output-truncated>`

**二进制字段特殊处理**(`base.py:46-66`):

```python
_BINARY_FIELD_NAMES = {"content_base64"}
# Replace with size summary so truncate() doesn't produce garbled base64
data[key] = f"<binary, ~{byte_size:,} bytes>"
```

→ **这是 AutoGPT 最优雅的设计之一**:不让长 output 撑爆 context,而是用 workspace 作为外存 + 检索式读取。

#### 4.5 错误回传

- block `error` 字段必须是 `str`(`blocks/__init__.py:80-85` 强制)
- 输出 `{"error": "<message>"}` 流到下一节点 / 下一 turn
- LLM 看到 error 自行 retry 或换 tool

---

### Q5. File Backend 是否为工具调用做了适配

**AutoGPT 平台**的 file backend 已经在 `file_backend.md` 详细记录。**专门为工具调用做的目录/文件适配**:

| 工具类型 | File Backend 路径 | 加载代码 | 作用 |
| --- | --- | --- | --- |
| **Skills** | `workspace://skills/{slug}/SKILL.md`(+ 可选 `references/` `scripts/` `assets/`) | `copilot/tools/skills.py:248-250` `SKILL_FOLDER="/skills"` | Anthropic Agent Skills 协议完整实现 |
| **大工具输出** | `workspace://tool-outputs/{tool_call_id}.json` | `copilot/tools/base.py:38-117` `_persist_and_summarize()` | 超 80K 自动持久化 + middle-out preview |
| **Block artifact** | `workspace://sessions/{session_id}/{filename}`(默认 session-scoped) | `util/workspace.py:90-100` `_resolve_path()` | block 写入默认进 session scope |
| **MCP 配置** | **无 `.mcp.json` 文件** | `blocks/mcp/block.py:209-213` `_auto_lookup_credential()` | MCP server 凭证存 DB,无配置文件 |
| **用户上传** | `workspace://{filename}` | `WorkspaceManager.write_file()` | 文件存 DB row + GCS/Local storage backend |
| **内置 seed skills** | `copilot/sdk/agent_generation_guide.md` + `mcp_tool_guide.md` | `copilot/tools/skills.py:227-242` | 仓库内 MD,启动时注入 |

**全局 vs 项目级**:
- **全局生效**:`workspace://skills/` 是 user-level(单用户全局),`workspace://tool-outputs/` 也是 user-level
- **项目级**:`workspace://sessions/{session_id}/` 是 session-scoped(随 session 隔离)
- **MCP**:无文件级配置,全在 DB(`OAuth2Credentials` 表)

**与 `standard/file_backend.md` 对照**:

| file_backend.md 条款 | AutoGPT 一致性 |
| --- | --- |
| §3.4 强结构化(按角色/数据类别) | ✅ `workspace://` 有清晰命名空间(skills/ / tool-outputs/ / sessions/) |
| §5.3 secrets 独立文件 + 0o600 | ✅ `auth.json` 0o600 单独存,LLM 不可 read(`file_backend.md` 详述) |
| §10.8 MCP 协议支持 | ⚠ **部分支持**——MCP 走运行时动态配置,无传统 `.mcp.json` 文件 |
| §3.8 Bootstrap 种子文件 | ✅ 启动 seed 2 个 skill(agent_building_guide + mcp_tool_guide) |
| §3.3 四类空间分组 | ✅ `skills/` 算 cache/可重生成,`tool-outputs/` 算 cache,`secrets/` 独立 |
| §8.3 atomic write | ✅ `WorkspaceManager` 有 atomic write(`file_backend.md` 详述) |

**与 Onion Agent 启示**:

- **Onion 可以学**:workspace 路径 + skills 协议 + tool-output 持久化 + middle-out preview 这套组合拳,优雅解决 context 爆炸
- **Onion 应当避免**:
  - 不要把 MCP server 配在代码里 / DB 里 —— 应当支持传统 `.mcp.json` 文件(类 Claude Code / Cline),用户更友好
  - 不要把 Skills 也存 DB —— 应当走文件式 SKILL.md,渐进式披露更直接
  - 不要每个 tool output 都走 workspace 持久化(80K 阈值合理,但应该做配置)

---

## 3. 关键代码片段(贴 4 段,每段 ≤ 30 行)

### 片段 1:Blocks 动态加载(`blocks/__init__.py:18-48`)

```python
@cached(ttl_seconds=3600)
def load_all_blocks() -> dict[str, type["AnyBlockSchema"]]:
    from backend.blocks._base import Block
    from backend.util.settings import Config
    config = Config()
    load_examples = config.enable_example_blocks
    current_dir = Path(__file__).parent
    modules = []
    for f in current_dir.rglob("*.py"):
        if not f.is_file() or f.name == "__init__.py" or f.name.startswith("test_"):
            continue
        relative_path = f.relative_to(current_dir)
        if not load_examples and relative_path.parts[0] == "examples":
            continue
        module_path = str(relative_path)[:-3].replace(os.path.sep, ".")
        modules.append(module_path)
    for module in modules:
        importlib.import_module(f".{module}", package=__name__)
    available_blocks: dict[str, type["AnyBlockSchema"]] = {}
    for block_cls in _all_subclasses(Block):
        if block_cls.__name__.endswith("Base"):
            continue
        if not block_cls.__name__.endswith("Block"):
            raise ValueError(...)
        block = block_cls()
        available_blocks[block.id] = block_cls
    return available_blocks
```

### 片段 2:Tool 输出大结果处理(`copilot/tools/base.py:60-117`)

```python
async def _persist_and_summarize(
    raw_output: str, user_id: str, session_id: str, tool_call_id: str,
) -> str:
    file_path = f"tool-outputs/{tool_call_id}.json"
    try:
        workspace = await workspace_db().get_or_create_workspace(user_id)
        manager = WorkspaceManager(user_id, workspace.id, session_id)
        await manager.write_file(
            content=raw_output.encode("utf-8"),
            filename=f"{tool_call_id}.json", path=file_path,
            mime_type="application/json", overwrite=True,
        )
    except Exception:
        return raw_output  # fall back to normal truncation
    total = len(raw_output)
    preview = truncate(_summarize_binary_fields(raw_output), _PREVIEW_CHARS)
    retrieval = (
        f"\nFull output ({total:,} chars) saved to workspace. "
        f'Use read_workspace_file(path="{file_path}", '
        f'offset=<char_offset>, length=50000) to read any section.'
    )
    return (
        f'<tool-output-truncated total_chars={total} workspace_path="{file_path}">\n'
        f"{preview}\n{retrieval}\n</tool-output-truncated>"
    )
```

### 片段 3:Multi-protocol tool call 提取(`util/prompt.py:323-380`)

```python
def _extract_tool_call_ids_from_message(msg: dict) -> set[str]:
    """Supports all formats:
    - OpenAI Chat Completions: {"role": "assistant", "tool_calls": [{"id": "..."}]}
    - Anthropic: {"role": "assistant", "content": [{"type": "tool_use", "id": "..."}]}
    - OpenAI Responses API: {"type": "function_call", "call_id": "..."}
    """
    ids: set[str] = set()
    if msg.get("type") == "function_call":  # Responses API
        if call_id := msg.get("call_id"):
            ids.add(call_id)
        return ids
    if msg.get("role") != "assistant":
        return ids
    if msg.get("tool_calls"):  # OpenAI Chat Completions
        for tc in msg["tool_calls"]:
            tc_id = tc.get("id")
            if tc_id:
                ids.add(tc_id)
    content = msg.get("content")
    if isinstance(content, list):  # Anthropic
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                tc_id = block.get("id")
                if tc_id:
                    ids.add(tc_id)
    return ids
```

### 片段 4:force_tool_choice(`util/llm/tool_use.py:30-67`)

```python
def pydantic_to_anthropic_tool(
    response_model: type[BaseModel], *, tool_name: str, description: str,
) -> dict[str, Any]:
    """Convert a Pydantic model class to an Anthropic tool definition."""
    schema = response_model.model_json_schema()
    inlined = _inline_refs(schema)
    inlined.pop("$defs", None)
    inlined.pop("title", None)
    return {"name": tool_name, "description": description, "input_schema": inlined}

def force_tool_choice(tool_name: str) -> dict[str, Any]:
    """Force Claude to call exactly this tool — no preamble, no parallel calls.
    Eliminates JSON-parse failures from chain-of-thought prose."""
    return {"type": "tool", "name": tool_name, "disable_parallel_tool_use": True}
```

---

## 4. 与 Onion Agent 设计的关联

1. **Onion 可以学** `workspace://tool-outputs/` + **middle-out preview**:AutoGPT 把 80K+ 的工具输出自动落盘到 workspace,返回 95K preview + retrieval hint(用 `read_workspace_file(offset=, length=)` 增量读)。Onion 应当借鉴这套机制——把 `session.json` 周边加 `~/.onion/tool-outputs/<call_id>.json` 外存,避免 context 爆炸。
2. **Onion 可以学** **Skills 协议(Anthropic Agent Skills)**:YAML frontmatter + markdown body + `references/` `scripts/` `assets/` 渐进式披露。Onion 的 `~/.onion/skills/<slug>/SKILL.md` 完全照搬即可,工具层只需一个 `read_skill(name=)` + `store_skill(name=, content=)`,**不要把 Skills 放 DB**(放文件 + frontmatter 解析更直接)。
3. **Onion 可以学** **多协议 tool_call 自动识别**:`util/prompt.py:323-595` 同时支持 OpenAI / Anthropic / Responses API 3 种协议,且 orphan tool_result 自动修复。Onion 的 session.json 如果要 provider 无关(OpenAI / Anthropic / MiniMax / Ollama 切换),这套三件套是必备。
4. **Onion 应当避免** **MCP 配置藏在 DB 里**:AutoGPT MCP server 只能运行时 UI 配置,没有 `.mcp.json` 文件,CLI / 自动化场景很难用。Onion 应当遵循 §10.8 —— 用户级 `~/.onion/mcp.json` + 项目级 `<repo>/.onion/mcp.json` 双层覆盖。
5. **Onion 应当避免** **Blocks 1 小时 `@cached`**:AutoGPT 启动后加新 block 需重启,违反"动态可插拔"。Onion 应当支持 `register_tool()` 运行时注册(或文件改动自动 reload)。

---

## 5. 不确定 / 未找到

1. **stream=True 流式 tool_call 解析**:在主 chat tool 路径中没有找到 `stream=True` 的调用。推断 streaming 主要用于 SSE 进度推送(`executor/activity_status_generator.py`)而非工具解析。`blocks/codex.py:6` 表明支持 Responses API 流式但未深入使用。
2. **Classic 版 forge 库**:`classic/original_autogpt/autogpt/agents/agent.py:285, 382` 调用 `CommandProvider.get_commands`,但 `forge` 库在仓库中找不到(可能是 pypi 依赖,未 clone 进来)。Classic 版的 tool list 实际生成路径未能完整追踪。
3. **`.mcp.json` 配置**:源码中无传统 `.mcp.json` 配置文件,MCP 完全走运行时 UI / DB 凭证。如果实际部署有人用 MCP,需要看 `OAuth2Credentials` 表的具体数据(schema 复杂,本报告未深入)。
4. **tool list 实际大小**:LLM 一次性看到的 tool 数量取决于 `is_available` + 用户角色 + feature flag。本报告未统计实际 production 中一个 turn 看到的 tool 数量级。
5. **provider 切换 demo**:`util/llm/providers.py` 7 个 provider 都支持,但实际多 provider 并发(同时调多个)的代码路径未在本报告追踪。
6. **Skills default seed 具体内容**:`copilot/sdk/agent_generation_guide.md` 是 Markdown,不是 SKILL.md 格式。实际如何被 `store_skill` 包装成 SKILL.md 未在源码中找到明确路径(推断是 `skills.py:227-242` 的内置加载逻辑,本报告未深挖)。
