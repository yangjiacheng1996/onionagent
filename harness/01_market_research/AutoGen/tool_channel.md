# AutoGen — 工具调用（Tool Channel）调研报告

> **调研对象**：`microsoft/autogen`（v0.4+ 主分支，Python monorepo）
> **核心定位**：微软系、对话驱动的多 Agent 编排框架。工具调用的"中枢神经"是 `autogen-core` 里的 `Workbench` 抽象 + `BaseTool` 协议 + 多种 `MCP*` 实现，上层 `autogen-agentchat.AssistantAgent` 把工具暴露成 OpenAI/Anthropic 兼容的 `tools` 数组。
> **调研时间**：基于当前 `main` 分支快照（`python/packages/`）
> **特别注意**：AutoGen v0.4+ 是 Rust + Python 混合架构；工具调用核心全部在 `autogen-core` + `autogen-ext`，不依赖旧版 `pyautogen` 的 `register_function` 模式。

---

## 0. 智能体一句话定位

微软系、对话驱动的多 Agent 编排框架，以"消息流 + Component 配置 + Code Executor"为内核；把"代码生成 → 执行 → 验证"做成 Agent Loop 闭环，支持 `RoundRobinGroupChat` / `SelectorGroupChat` / `MagenticOneGroupChat` / `Swarm` 等拓扑，内置本地 / Docker / Jupyter 三种代码执行后端，Web UI 用 AutoGen Studio。

---

## 1. 调研依据

| 文件 / 模块 | 角色 |
|---|---|
| `python/packages/autogen-core/src/autogen_core/tools/_base.py` | `BaseTool` / `Tool` Protocol / `ToolSchema` / `ToolOverride` 定义 |
| `python/packages/autogen-core/src/autogen_core/tools/_workbench.py` | `Workbench` 抽象（`list_tools` / `call_tool` / `start` / `stop` / `reset` / `save_state` / `load_state`）+ `ToolResult` / `ResultContent` |
| `python/packages/autogen-core/src/autogen_core/tools/_function_tool.py` | `FunctionTool`：把 Python 函数包成 `BaseTool`（用 Pydantic 反射函数签名） |
| `python/packages/autogen-core/src/autogen_core/tools/_static_workbench.py` | `StaticWorkbench` / `StaticStreamWorkbench`：固定工具集的 Workbench |
| `python/packages/autogen-core/src/autogen_core/_function_utils.py` | OpenAI function calling 协议的 Pydantic 模型（`Parameters` / `Function` / `ToolFunction`） |
| `python/packages/autogen-agentchat/src/autogen_agentchat/agents/_assistant_agent.py` | `AssistantAgent`：工具注册、Tool Loop、`max_tool_iterations`、`reflect_on_tool_use`、并发执行 |
| `python/packages/autogen-ext/src/autogen_ext/tools/mcp/__init__.py` | MCP 模块入口（`McpWorkbench` / `mcp_server_tools` / 3 种 Server Params） |
| `python/packages/autogen-ext/src/autogen_ext/tools/mcp/_workbench.py` | `McpWorkbench`：`list_tools` / `call_tool` / `tool_overrides` / `host`（Sampling/Elicitation/Roots） |
| `python/packages/autogen-ext/src/autogen_ext/tools/mcp/_config.py` | `StdioServerParams` / `SseServerParams` / `StreamableHttpServerParams`（Pydantic discriminated union） |
| `python/packages/autogen-ext/src/autogen_ext/tools/mcp/_factory.py` | `mcp_server_tools(server_params, session)`：把 MCP 工具批量注册成 AutoGen 工具 |
| `python/packages/autogen-ext/src/autogen_ext/tools/http/_http_tool.py` | `HttpTool`：把 HTTP endpoint 包成 `BaseTool` |
| `python/packages/autogen-ext/src/autogen_ext/agents/file_surfer/_tool_definitions.py` | `FileSurfer` 的 5 个内置工具 schema（`TOOL_OPEN_PATH` 等） |
| `python/packages/autogen-ext/src/autogen_ext/agents/web_surfer/_multimodal_web_surfer.py` | `MultimodalWebSurfer`（Playwright 浏览器） |
| `python/packages/autogen-ext/src/autogen_ext/models/openai/_openai_client.py` | OpenAI 客户端：`convert_tools` + 流式 `tool_calls` 增量解析 |
| `python/packages/autogen-ext/src/autogen_ext/models/anthropic/_anthropic_client.py` | Anthropic 客户端：原生 `tools` 协议 + `input_json_delta` 流式解析 + `tool_result` 块回传 |
| `python/packages/autogen-studio/autogenstudio/gallery/builder.py` | Studio Gallery：`calculator_tool` / `fetch_webpage_tool` 默认模板 |
| `python/packages/autogen-studio/autogenstudio/gallery/tools/` | 5 个内置 gallery 工具（calculator / fetch_webpage / bing_search / google_search / generate_image） |
| `README.md`（仓库根） | 用 `McpWorkbench` + `StdioServerParams` 调用 `@playwright/mcp` 的官方示例 |

**文档/架构参考**：
- 仓库根 `README.md`（示例 + 安装说明）
- `autogen-core.tools` 抽象（`Tool` Protocol / `Workbench` ABC）
- `McpWorkbench` docstring 自带 capability 表（Tools / Resources / ResourceTemplates / Prompts / Sampling / Roots / Elicitation）

---

## 2. 五个核心问题的回答

### Q1. 工具来源

**AutoGen 的工具来源体系是"Workbench 抽象 + 多后端实现"，没有任何"中心化工具配置文件"**。

#### 1.1 内置工具（按场景分）

| 工具 / Agent | 位置 | 关键能力 |
|---|---|---|
| `FileSurfer` | `autogen-ext/agents/file_surfer/_file_surfer.py:79` | 5 个工具：`open_path` / `page_up` / `page_down` / `find_on_page_ctrl_f` / `find_next`，基于 `MarkdownFileBrowser(base_path=os.getcwd())` 做沙箱化文件预览 |
| `MultimodalWebSurfer` | `autogen-ext/agents/web_surfer/_multimodal_web_surfer.py` | Playwright 浏览器自动化（点击 / 截图 / 提取元素 / 下载） |
| `VideoSurfer` | `autogen-ext/agents/video_surfer/_video_surfer.py` | 视频内容理解（`tools.py` 定义 3 个工具） |
| `OpenAIAssistantAgent` | `autogen-ext/agents/openai/_openai_assistant_agent.py` | 包装 OpenAI Assistants API（`code_interpreter` / `file_search` / `function` 三大类） |
| `AzureAIAgent` | `autogen-ext/agents/azure/_azure_ai_agent.py` | 包装 Azure AI Foundry Agent Service |
| `MagenticOneCoderAgent` | `autogen-ext/agents/magentic_one/_magentic_one_coder_agent.py` | Magentic-One 团队的程序员工种 |
| `CodeExecutorAgent` | `autogen-agentchat/agents/_code_executor_agent.py` | 把 `CodeExecutor` 包成可对话的 Agent（执行 Python / bash） |
| `CodeExecutor` 家族 | `autogen-ext/code_executors/{local,docker,jupyter,azure}/` | 本地 / Docker / Jupyter / Azure 4 种代码执行后端 |
| Studio Gallery 工具 | `autogen-studio/autogenstudio/gallery/tools/` | `calculator` / `fetch_webpage` / `bing_search` / `google_search` / `generate_image` 5 个开箱即用工具 |

#### 1.2 自定义工具（用户编写）

- `FunctionTool(func, description, ...)`（`_function_tool.py:81-110`）：把任意 Python 函数包成 `BaseTool`（**强制要求全部参数 + 返回值带 type hint**，否则 `TypeError`）
- `HttpTool`（`tools/http/_http_tool.py`）：把 HTTP endpoint 包成工具（用 `json_schema_to_pydantic` 生成 args model）
- `GraphRAG` 工具族（`tools/graphrag/{_local_search,_global_search}.py`）：基于 `graphrag` 库的 RAG 检索工具
- `AzureAISearchTool`（`tools/azure/_ai_search.py`）：Azure AI Search 检索
- `LangChain` / `SemanticKernel` 适配器（`tools/langchain/_langchain_adapter.py`、`tools/semantic_kernel/_kernel_function_from_tool.py`）：把 LangChain / SK 的工具映射到 AutoGen 的 `BaseTool`

#### 1.3 MCP 支持

**AutoGen 对 MCP 的支持是 v0.4+ 的核心能力，地位类似 Claude Code 的"插件市场"**。源码实证：

- **3 种传输协议**（`_config.py:14-46`）：
  - `StdioServerParams`（继承自 `mcp.StdioServerParameters`，加 `read_timeout_seconds=5`）
  - `SseServerParams`（HTTP + Server-Sent Events）
  - `StreamableHttpServerParams`（新版 streamable HTTP，`terminate_on_close=True`）
- **`McpWorkbench`（`_workbench.py`）**：实现 `Workbench` ABC + `Component` 序列化，支持：
  - `list_tools()` / `call_tool()` — 工具
  - `list_prompts()` / `get_prompt()` — prompt 模板
  - `list_resources()` / `read_resource()` / `list_resource_templates()` — Resources
  - 通过 `McpSessionHost`（`_host/_session_host.py`）支持反向通道：Sampling / Elicitation / Roots
- **`mcp_server_tools(server_params)`（`_factory.py`）**：工厂函数，一次性连接 MCP server 并把所有工具适配成 AutoGen `BaseTool` 列表
- **`tool_overrides`（`_workbench.py:67-71`）**：可以在工具被 LLM 看到时改 `name` / `description`（不改底层 MCP server 的工具）

**MCP 配置方式：完全在代码里**，没有 `~/.autogen/mcp.json` 之类的配置文件：

```python
# _workbench.py docstring 第 95-106 行示例
params = StdioServerParams(
    command="uvx",
    args=["mcp-server-fetch"],
    read_timeout_seconds=60,
)
async with McpWorkbench(server_params=params) as workbench:
    tools = await workbench.list_tools()
```

#### 1.4 Agent Skills 支持

**❌ 不支持** Anthropic Agent Skills / OpenClaw Skills / obra-superpowers 那种"渐进式披露的 SKILL.md 模式"。

- 仓库中无 `skills/` 目录
- 无 `SKILL.md` / progressive disclosure 相关代码
- AutoGen Studio 的 `.gitignore` 里出现过 `autogenstudio/web/skills/user/*` 路径（`autogen-studio/.gitignore`），但代码里**没有任何引用** — `file_backend.md` 已记录为"疑似废弃占位"
- "Skill" 在 AutoGen 里指的是 `McpWorkbench.list_prompts()` 返回的 **MCP Prompt**（`_workbench.py:288-314`），是 MCP 协议原生的 prompt 模板，不是 Anthropic Agent Skills

#### 1.5 其他工具类型

- **LSP 工具**：❌ 不内置
- **本地 API / Webhook**：❌ 不内置
- **HTTP 工具**：`HttpTool`（见 1.2）
- **LangChain / SemanticKernel 工具生态**：通过适配器可继承（见 1.2）
- **MCP Resources + Prompts**（不是工具）：`_workbench.py:288-363` 暴露了 `list_resources` / `read_resource` / `list_prompts` / `get_prompt`，但这些是"被读取的资产"，不是 LLM 可调用的 function calling 工具

---

### Q2. 工具列表的生成、传递、格式

#### 2.1 工具列表如何生成

**三种生成路径，按抽象层级递减**：

1. **代码注册（最主流）**：用户在 `AssistantAgent(tools=[...])` 直接传 `BaseTool` 子类 / Python 函数
   - `AssistantAgent.__init__`（`_assistant_agent.py:802-816`）遍历 `tools` 列表：
     - `BaseTool` → 直接 `self._tools.append(tool)`
     - `callable` → 包成 `FunctionTool(tool, description=tool.__doc__ or "")`
     - **强制 `function_calling` 模型能力检查**（`_assistant_agent.py:804`）：`model_client.model_info["function_calling"] is False` → `ValueError`
2. **MCP 注册**：`mcp_server_tools(server_params)` 工厂函数（`_factory.py:106-127`）→ 连接 MCP server → `list_tools` → 每条包成 `StdioMcpToolAdapter` / `SseMcpToolAdapter` / `StreamableHttpMcpToolAdapter` → 交给 `AssistantAgent(tools=...)`
3. **Workbench 注册**：`AssistantAgent(workbench=[mcp_workbench, static_workbench])`（`_assistant_agent.py:858-865`）→ Workbench 的 `list_tools()` 在每次 LLM 调用前被查询

**Workbench 抽象允许"运行时动态"**：McpWorkbench 的 docstring（`_workbench.py:71-72`）明确写 "The list of tools may be dynamic, and their content may change after tool execution" — 工具列表是**每次 `list_tools()` 实时查询**的，不是启动时一次性缓存。

#### 2.2 工具列表如何传递给大模型

**`AssistantAgent._call_llm()`（`_assistant_agent.py:~1090`）→ `model_client.create(llm_messages, tools=tools, ...)` → 模型客户端把 `BaseTool` / `ToolSchema` 列表转成协议对应的 `tools` 数组**。

OpenAI 客户端流程（`_openai_client.py:244-280`）：
```python
def convert_tools(tools: Sequence[Tool | ToolSchema]) -> List[ChatCompletionToolParam]:
    for tool in tools:
        if isinstance(tool, Tool):
            tool_schema = tool.schema   # Tool protocol 的 .schema property
        else:
            tool_schema = tool          # 已经是 dict
        result.append(ChatCompletionToolParam(
            type="function",
            function=FunctionDefinition(
                name=tool_schema["name"],
                description=tool_schema.get("description", ""),
                parameters=cast(FunctionParameters, tool_schema.get("parameters", {})),
                strict=tool_schema.get("strict", False),
            ),
        ))
```

最终调用（`_openai_client.py:683-700`）：
```python
self._client.chat.completions.create(
    messages=create_params.messages,
    stream=False,
    tools=(create_params.tools if len(create_params.tools) > 0 else NOT_GIVEN),
    **create_params.create_args,
)
```

Anthropic 客户端流程（`_anthropic_client.py:622-631`）：
```python
if len(tools) > 0:
    converted_tools = convert_tools(tools)        # 转成 Anthropic 格式
    self._last_used_tools = converted_tools       # 缓存,用于回传 tool_result 时补 tools
    request_args["tools"] = converted_tools
elif has_tool_results:
    # anthropic requires tools to be present even if there is any tool use
    request_args["tools"] = self._last_used_tools
```

#### 2.3 格式：JSON（OpenAI 协议为主）

**AutoGen 的"工具 schema 格式"完整遵循 OpenAI function calling 协议**，由 Pydantic 模型严格定义（`_function_utils.py:91-104`）：

```python
# _function_utils.py:91-115
class Parameters(BaseModel):
    type: Literal["object"] = "object"
    properties: Dict[str, Dict[str, Any]]
    required: List[str]

class Function(BaseModel):
    description: Annotated[str, Field(description="Description of the function")]
    name: Annotated[str, Field(description="Name of the function")]
    parameters: Annotated[Parameters, Field(description="Parameters of the function")]

class ToolFunction(BaseModel):
    type: Literal["function"] = "function"
    function: Annotated[Function, Field(description="Function under tool")]
```

**实际 `tools` 列表片段（来自 `file_surfer/_tool_definitions.py:1-20` 的 `TOOL_OPEN_PATH`）**：

```json
{
  "type": "function",
  "function": {
    "name": "open_path",
    "description": "Open a local file or directory at a path in the text-based file browser and return current viewport content.",
    "parameters": {
      "type": "object",
      "properties": {
        "path": {
          "type": "string",
          "description": "The relative or absolute path of a local file to visit."
        }
      },
      "required": ["path"]
    }
  }
}
```

#### 2.4 是否 prompt-as-tool

**❌ 否**。AutoGen 是**纯 function calling**，没有任何"用 prompt 描述工具让 LLM 自己选"的 XML / 伪 XML 模式。所有工具都通过 OpenAI / Anthropic 原生 `tools` 数组传递。

#### 2.5 动态刷新

- **McpWorkbench**：✅ 每次 `call_tool()` 前后都可重新 `list_tools()`（`Workbench` 协议设计如此，docstring 明确支持）
- **AssistantAgent 工具列表**：⚠️ 构造时确定，但通过 Workbench 间接支持动态（`_assistant_agent.py:_call_llm` 每次都从 workbench 拉新列表）
- **Studio Gallery**：❌ 启动时 `import_teams_from_directory` 一次性导入，运行时不变

---

### Q3. 工具调用指令的解析、错误修复、准确性保证

#### 3.1 解析方式

**OpenAI 客户端：流式增量解析 `tool_calls` 数组**（`_openai_client.py:1057-1077`）：

```python
# _openai_client.py:1057-1077 (流式 chunk 循环里)
if choice.delta.tool_calls is not None:
    for tool_call_chunk in choice.delta.tool_calls:
        idx = tool_call_chunk.index
        if idx not in full_tool_calls:
            full_tool_calls[idx] = FunctionCall(id="", arguments="", name="")
        if tool_call_chunk.id is not None:
            full_tool_calls[idx].id += tool_call_chunk.id
        if tool_call_chunk.function is not None:
            if tool_call_chunk.function.name is not None:
                full_tool_calls[idx].name += tool_call_chunk.function.name
            if tool_call_chunk.function.arguments is not None:
                full_tool_calls[idx].arguments += tool_call_chunk.function.arguments
```

**关键点**：
- 用 `index` 字段做多 tool call 的并发分桶（`Dict[int, FunctionCall]`）
- `id` / `name` / `arguments` 全部用**字符串拼接**累积（不是 buffer 复用）
- 解析时机：流式结束后**一次性组装**为 `List[FunctionCall]`（`_openai_client.py:1176-1182`）

**Anthropic 客户端：解析 `input_json_delta` 增量**（`_anthropic_client.py:956-980`）：

```python
elif hasattr(chunk.delta, "type") and chunk.delta.type == "input_json_delta":
    if current_tool_id is not None and hasattr(chunk.delta, "partial_json"):
        # Accumulate partial JSON for the current tool
        tool_calls[current_tool_id]["partial_json"] += chunk.delta.partial_json
```

`content_block_start` 时初始化 `{id, name, input=json.dumps(...), partial_json=""}`，`content_block_delta` 累积 `partial_json`，`content_block_stop` 时把累积的 partial_json 覆盖到 `input` 字段（`_anthropic_client.py:978-981`）。

#### 3.2 错误修复机制

| 错误类型 | 修复机制 | 代码位置 |
|---|---|---|
| 工具名含非法字符 | `normalize_name()` 替换为 `_`（`_openai_client.py:299-303`） | OpenAI 解析前 |
| 工具名校验（启动时） | `assert_valid_name()` 抛错（`tools/_utils/assert_valid_name.py`，在 `convert_tools` 末尾调用） | `_openai_client.py:280` |
| Args 缺失 / 类型错 | **Pydantic `args_type.model_validate(args)` 强校验**（`_function_tool.py:103-107`） → 失败抛 `ValidationError` | `run_json` 入口 |
| 工具执行异常 | `try/except` 包住整个 `call_tool`，把异常 message 塞进 `ToolResult(is_error=True)` | `_static_workbench.py:115-138`、`_workbench.py:296-299` |
| **LLM 看到错误后能否自动修复** | ✅ 通过 `FunctionExecutionResult(is_error=True)` 回到 messages，LLM 下次推理可调整 | `_assistant_agent.py:_process_model_result` 整段 |
| 工具未找到 | 静态 Workbench 返回 `ToolResult(is_error=True, result="Tool {name} not found.")` | `_static_workbench.py:115-119` |
| 必填参数缺失（启动时） | `get_missing_annotations` 在 `FunctionTool` 构造时抛 `TypeError` | `_function_utils.py:201-213` |

**注：AutoGen 没有"截断 / token 超限"专门修复** — 那是模型客户端的事，不是工具调用层。

#### 3.3 准确性保证

- **Pydantic schema 强校验**（`args_type.model_validate(args)`）：LLM 给了不合法 JSON → `ValidationError` → 包装成 `is_error=True` 回到 LLM
- **`strict` 模式**：`FunctionTool(strict=True)` 强制要求所有参数无 default（`_base.py:78-83`），`BaseTool.schema` property 会检查并抛 `ValueError`
- **`tool_choice` 参数**：`convert_tool_choice()` 支持 `auto` / `required` / `none` / 强制某个 Tool（`_openai_client.py:274-296`）
- **Tool name unique check**：`AssistantAgent.__init__` 强制 `len(tool_names) == len(set(tool_names))`（`_assistant_agent.py:817-820`）
- **MCP tool override**：MCP server 改工具名后，AutoGen 可在 `McpWorkbench(tool_overrides={...})` 层改回去（`_workbench.py:67-71`）
- **没有 plan-then-act 模式**（这是 Cline 风格，AutoGen 不走这条路）— AutoGen 是纯 react loop，依赖 `max_tool_iterations` 控制循环

#### 3.4 重试机制与上限

- **`max_tool_iterations`（默认 1，≥1）**（`_assistant_agent.py:85, 852-856`）：**外层循环上限**，控制"LLM → tool → LLM → tool"能反复几次
- **并发执行**（`_assistant_agent.py:1257`）：多个 tool call 用 `asyncio.gather(...)` 同时执行，不串行
- **`parallel_tool_calls=False`**：在 OpenAI client 配置里关闭并发（`_assistant_agent.py:145` 注释里说明）
- **没有"重试 N 次"硬编码** — 错误回到 LLM 是一种隐式 retry，但显式上限就是 `max_tool_iterations`

#### 3.5 工具名清洗细节

`_openai_client.py:299-303` 的 `normalize_name()`：
```python
def normalize_name(name: str) -> str:
    """
    LLMs sometimes ask functions while ignoring their own format requirements, this function should be used to replace invalid characters with "_".
    """
```
**AutoGen 假设 LLM 偶尔会返回带非法字符（如 `.` / `-`）的工具名**，通过这个函数容错（**这是一个值得借鉴的"防御性设计"**）。

---

### Q4. 工具执行结果回传

#### 4.1 回传方式

**统一用 `FunctionExecutionResult` + `FunctionExecutionResultMessage` 抽象**（`autogen-core/models/_types.py:56-77`）：

```python
# _types.py:56-77
class FunctionExecutionResult(BaseModel):
    """Function execution result contains the output of a function call."""
    content: str
    call_id: str
    is_error: bool
    name: str


class FunctionExecutionResultMessage(BaseModel):
    """Function execution result message contains the output of multiple function calls."""
    content: List[FunctionExecutionResult]
    type: Literal["FunctionExecutionResultMessage"] = "FunctionExecutionResultMessage"


LLMMessage = Annotated[
    Union[SystemMessage, UserMessage, AssistantMessage, FunctionExecutionResultMessage],
    Field(discriminator="type")
]
```

`Workbench.call_tool()` 返回 `ToolResult`（`_workbench.py:48-66`）：

```python
class ToolResult(BaseModel):
    type: Literal["ToolResult"] = "ToolResult"
    name: str
    result: List[ResultContent]   # TextResultContent | ImageResultContent
    is_error: bool = False
```

**关键链**：`Tool.run_json()` → `Workbench.call_tool()` → `ToolResult` → `FunctionExecutionResult`（用 `tool.return_value_as_string()` 把 `result` 数组拼成字符串）→ 累积成 `FunctionExecutionResultMessage` → 加进 `model_context` → 下次 `model_client.create()` 时由各 provider 翻译成协议格式。

#### 4.2 格式：JSON（结构化）→ 字符串（送 LLM）

- **`ToolResult` 是 Pydantic 结构化**：`{name, result: List[TextResultContent|ImageResultContent], is_error}`
- **但送 LLM 时是字符串**：`FunctionExecutionResult.content: str`（`_types.py:56-66`）— 用 `BaseTool.return_value_as_string()` 把结构化结果 JSON 化（`_base.py:142-150`）

```python
# _base.py:142-150
def return_value_as_string(self, value: Any) -> str:
    if isinstance(value, BaseModel):
        dumped = value.model_dump()
        if isinstance(dumped, dict):
            return json.dumps(dumped)
        return str(dumped)
    return str(value)
```

`ToolResult.to_text()`（`_workbench.py:68-83`）负责把多内容（text + image）拼成单字符串或加 `replace_image` 占位符。

#### 4.3 通信协议：多协议 Provider 无关

**AutoGen 的核心承诺就是"Provider 无关"** — `LLMMessage` 是抽象层，每个 provider 客户端做翻译：

| Provider | 入口 | 工具回传格式 |
|---|---|---|
| OpenAI / Azure OpenAI | `autogen-ext/models/openai/_openai_client.py` | `role: "tool"`, `tool_call_id`（通过 `_transformation/` 下的 transformer） |
| Anthropic Claude | `autogen-ext/models/anthropic/_anthropic_client.py:289-298` | `{"role": "user", "content": [{"type": "tool_result", "tool_use_id": result.call_id, "content": result.content}]}` |
| Ollama | `autogen-ext/models/ollama/_ollama_client.py` | 兼容 OpenAI 协议 |
| llama.cpp | `autogen-ext/models/llama_cpp/_llama_cpp_completion_client.py` | OpenAI 兼容 |
| Azure AI Foundry | `autogen-ext/models/azure/_azure_ai_client.py` | Azure 协议 |
| Semantic Kernel | `autogen-ext/models/semantic_kernel/` | SK 协议 |

**Anthropic 的 `tool_result` 翻译**（`_anthropic_client.py:289-298`）：
```python
for result in message.content:
    content_blocks.append(
        ToolResultBlockParam(
            type="tool_result",
            tool_use_id=result.call_id,
            content=result.content,
        )
    )
```

**Anthropic 的关键约束**（`_anthropic_client.py:625-634`）：如果当前 turn 包含 `FunctionExecutionResultMessage`，**必须重新带上 `tools` 列表**（"anthropic requires tools to be present even if there is any tool use"）— AutoGen 用 `self._last_used_tools` 缓存上一次的工具定义来解决。

#### 4.4 大结果处理

| 场景 | 机制 | 证据 |
|---|---|---|
| 图片结果 | `ImageResultContent` 包 `Image`，`to_text()` 用 `replace_image` 占位符或 `[Image: <base64>]` 字符串 | `_workbench.py:68-83` |
| 长结果截断 | **默认不截断**，由用户用 `tool_call_summary_format` / `tool_call_summary_formatter` 自定义 | `_assistant_agent.py:740-741, 857-858` |
| 非视觉模型 | `remove_images` 工具函数自动剥离 image | `_assistant_agent.py:46` 引用 |
| 自定义摘要 | `tool_call_summary_format: str = "{result}"`（占位符 `{tool_name}` / `{arguments}` / `{result}` / `{is_error}`） | `_assistant_agent.py:740, 224-227` |
| 完全自定义 | `tool_call_summary_formatter: Callable[[FunctionCall, FunctionExecutionResult], str]`，**不可序列化**（用 in-code） | `_assistant_agent.py:741, 228-238` |
| 大结果回传 | 直接塞进 `FunctionExecutionResultMessage` → `model_context.add_message` → 下次 `create()` 整段进 messages | `_assistant_agent.py:_process_model_result` |

**AutoGen 的"结果回传"哲学**：**完全交给用户控制**，既不截断也不引用文件，所有简化逻辑都通过 formatter 暴露。

---

### Q5. File Backend 是否为工具调用做了适配

**结论：AutoGen 对工具调用没有"中心化目录"支持；MCP 配置完全在代码里；Studio Gallery 是产品层的"模板市场"**。与 `standard/file_backend.md` 的"3.8 Bootstrap 种子文件" / "10.8 MCP 协议支持"条款**部分吻合但不完全**。

#### 5.1 工具配置目录 / 文件清单

| 路径 | 角色 | 备注 |
|---|---|---|
| **无** `~/.autogen/mcp.json` | ❌ | **不读取任何 MCP 配置文件**。MCP server 完全由用户在 Python 代码里 `StdioServerParams(command=..., args=[...])` 构造 |
| `~/.autogenstudio/configs/*.json` | Studio Gallery 模板目录 | 启动时 `import_teams_from_directory(config_dir, ...)` 导入（`web/deps.py:156`） |
| `~/.autogenstudio/files/user/` | Studio 用户上传/产出文件 | `web/initialization.py:58-59` |
| `python/packages/autogen-studio/autogenstudio/gallery/builder.py` | **默认 Gallery 模板**（含 1 个 MCP workbench：`@modelcontextprotocol/server-filesystem` + `mcp-server-fetch`） | 编译期内置，**用户修改需要改源码** |
| `python/packages/magentic-one-cli/src/magentic_one_cli/_m1.py:99-105` | Magentic-One CLI 找 `config.yaml`（**CWD 下**） | `if os.path.isfile("config.yaml")` 模式，没有"用户属主配置目录" |
| `python/packages/autogen-studio/autogenstudio/web/skills/user/` | `.gitignore` 里有，代码里**无引用** | 疑似废弃占位（`file_backend.md` 已记录） |

**Gallery 默认 MCP 模板**（`gallery/builder.py:561-570`）：
```python
mcp_workbench = McpWorkbench(server_params=fetch_server_params)
builder.add_workbench(mcp_workbench.dump_component(), ...)
```
**走 `@modelcontextprotocol/server-filesystem` + `~` + `tempfile.gettempdir()` 作为允许路径**（参考 `file_backend.md` §2.4）— **这与"10.8 MCP 协议支持"强相关，但默认放开 home 是危险设计**。

#### 5.2 加载代码（`file:line`）

| 加载点 | 代码位置 |
|---|---|
| Studio `app_root` 解析 | `autogen-studio/autogenstudio/web/initialization.py:41-45`（`AUTOGENSTUDIO_APPDIR` env → `~/.autogenstudio`） |
| Studio `configs/` 目录创建 | `autogen-studio/autogenstudio/web/initialization.py:64-67`（`mkdir(parents=True, exist_ok=True)`） |
| Studio Gallery 导入 | `autogen-studio/autogenstudio/web/deps.py:156`（`import_teams_from_directory`） |
| Studio env 写入 | `autogen-studio/autogenstudio/cli.py:18-23`（`temp_env_vars.env`） |
| Magentic-One CLI config | `python/packages/magentic-one-cli/src/magentic_one_cli/_m1.py:99-105`（`if os.path.isfile("config.yaml")`） |
| Gallery 默认 tools 注册 | `autogen-studio/autogenstudio/gallery/builder.py:480-580` |

#### 5.3 全局 vs 项目级

- **全局生效**：`~/.autogenstudio/{configs,files/user,autogen04203.db}` — Studio 模式
- **项目级生效**：`Magentic-One CLI` 找 CWD 下的 `config.yaml` — **CWD 模式**
- **代码级**（编译期）：`autogenstudio/gallery/builder.py` 的默认模板 — **没有用户可改的入口**
- **MCP server 路径**：**没有文件，完全在 Python 代码** — **这是 AutoGen 与其他 Agent 最大的差异点**

#### 5.4 与 `standard/file_backend.md` 的对照

| 标准条款 | AutoGen 现状 | 评分 |
|---|---|---|
| §3.1 严格三层分离 | **部分支持** — Studio 有全局 `~/.autogenstudio/`，CLI 走 CWD，但 Core/Ext 库无统一 home | ⚠️ |
| §3.8 Bootstrap 种子文件 | ❌ — `gallery/builder.py` 是编译期内置，用户首次启动看不到任何"种子" | ❌ |
| §5.4 LLM 不可读凭证白名单 | ❌ — `FileSurfer(base_path=os.getcwd())` 默认 CWD，**默认放开 home** | ❌ |
| §8.5 文档与代码一致性 | ⚠️ — 文档写"用户可配置"，但路径只能在代码里改 | ⚠️ |
| §10.8 MCP 协议支持 | ✅ — `McpWorkbench` + 3 种 transport + `tool_overrides` + 完整 capability 覆盖 | ✅✅ |
| §10.4 包内嵌 default config + user override | ❌ — 没有 `~/.autogen/mcp.json` 机制，default 走 Gallery 编译期 | ❌ |
| §5.1 配置文件格式 | ✅ — Pydantic `Component` 模型（`McpServerParams`）完美序列化 | ✅✅ |
| §5.6 配置版本迁移 | ❌ — 旧 `pyautogen` 配置不自动迁移，新版只走 `Component` 序列化 | ❌ |

**核心结论**：AutoGen 在 **"工具调用协议 + Workbench 抽象"** 上是行业顶尖（✅✅），但在 **"工具配置目录 / File Backend 支持"** 上是反面教材（❌）— **它假设"工具是程序员在代码里编排的资产"，不假设"工具是用户可改的配置文件"**。

---

## 3. 关键代码片段

### 3.1 Workbench 抽象（`autogen-core/tools/_workbench.py:82-141`）

```python
class Workbench(ABC, ComponentBase[BaseModel]):
    component_type = "workbench"

    @abstractmethod
    async def list_tools(self) -> List[ToolSchema]:
        """List the currently available tools in the workbench as ToolSchema objects."""
        ...

    @abstractmethod
    async def call_tool(
        self,
        name: str,
        arguments: Mapping[str, Any] | None = None,
        cancellation_token: CancellationToken | None = None,
        call_id: str | None = None,
    ) -> ToolResult:
        ...
```

**意图**：Workbench 是"工具集合 + 共享资源" 的容器；支持 `start/stop/reset/save_state/load_state` 的全生命周期管理。**这是 AutoGen 的"Tool Channel"核心抽象**。

### 3.2 McpWorkbench 能力表（`autogen-ext/tools/mcp/_workbench.py:75-100`）

```python
.. list-table:: MCP Support
   :header-rows: 1
   :widths: 30 70
   * - MCP Capability
     - Supported Features
   * - Tools
     - list_tools, call_tool
   * - Resources
     - list_resources, read_resource
   * - ResourceTemplates
     - list_resource_templates, read_resource_template
   * - Prompts
     - list_prompts, get_prompt
   * - Sampling
     - Optional support via McpSessionHost
   * - Roots
     - Optional support via McpSessionHost
   * - Ellicitation
     - Optional support via McpSessionHost
```

**意图**：MCP 全能力覆盖（不只是 Tools），反向通道（Sampling/Elicitation/Roots）通过 `McpSessionHost` 暴露 — **这是 v0.4+ 的设计亮点**。

### 3.3 OpenAI 流式 tool_calls 增量解析（`_openai_client.py:1057-1077`）

```python
if choice.delta.tool_calls is not None:
    for tool_call_chunk in choice.delta.tool_calls:
        idx = tool_call_chunk.index
        if idx not in full_tool_calls:
            full_tool_calls[idx] = FunctionCall(id="", arguments="", name="")
        if tool_call_chunk.id is not None:
            full_tool_calls[idx].id += tool_call_chunk.id
        if tool_call_chunk.function is not None:
            if tool_call_chunk.function.name is not None:
                full_tool_calls[idx].name += tool_call_chunk.function.name
            if tool_call_chunk.function.arguments is not None:
                full_tool_calls[idx].arguments += tool_call_chunk.function.arguments
```

**意图**：用 `index` 做分桶、`+=` 做字符串累积 — 标准的 OpenAI 协议增量解析。**Onion Agent 可以直接照搬**。

### 3.4 AssistantAgent Tool Loop（`_assistant_agent.py:_process_model_result` 关键骨架）

```python
for loop_iteration in range(max_tool_iterations):
    if isinstance(current_model_result.content, str):
        # 直接文本响应 → 结束
        yield Response(chat_message=TextMessage(...))
        return

    # 工具调用 → 并发执行
    results = await asyncio.gather(
        *[self._execute_tool_call(call, workbench, ...) for call in current_model_result.content]
    )

    # 累积结果到 model_context
    await model_context.add_message(
        FunctionExecutionResultMessage(content=[r for _, r in results])
    )

    # 继续下一轮 LLM 调用
    next_model_result = await model_client.create(...)
```

**意图**：**外层 `for` 循环 + 每次 `model_client.create()` 的标准 react loop** — Onion Agent 的"洋葱核心层 session.json 自动累加器"可以借鉴这个循环结构。

### 3.5 McpServerParams discriminated union（`_config.py:51-53`）

```python
McpServerParams = Annotated[
    StdioServerParams | SseServerParams | StreamableHttpServerParams,
    Field(discriminator="type")
]
```

**意图**：用 Pydantic discriminated union 表达 3 种 transport — 比"配置文件里靠 type 字段"更安全，**Onion Agent 的 MCP 配置可以借鉴这种 discriminated union 而非 YAML 自由格式**。

---

## 4. 与 Onion Agent 设计的关联

| Onion Agent 设计点 | AutoGen 的对应 | 启发 |
|---|---|---|
| **Onion 三层 Tool 分类**（buildin / mcp / agent_skills） | AutoGen 也有 `BaseTool`（用户自定义） + `McpWorkbench`（MCP） + `McpWorkbench.list_prompts`（MCP Prompts，**不是** Agent Skills） | **借鉴**：Onion 的 `buildin_tool` 走 `BaseTool` 抽象，`mcp_tool` 走 Workbench，`agent_skills` 走 MCP Prompts（或后续自己实现 SKILL.md 加载） — **三层是合理的，但要明确 Agent Skills 不等同于 MCP Prompts** |
| **tool list 协议** | OpenAI `ChatCompletionToolParam` + Anthropic 原生 `tools` + Pydantic `Parameters` 模型 | **强借鉴**：Onion 的 `ToolChannel` 应该直接照搬 `Parameters` / `Function` / `ToolFunction` 这套 Pydantic 模型，**自动序列化 + Provider 无关** |
| **流式解析** | OpenAI `delta.tool_calls[].index` 累积 + Anthropic `input_json_delta.partial_json` 累积 | **强借鉴**：Onion 的 `ToolChannel.parse_stream()` 应该按 provider 分支，**统一封装成 `FunctionCall(id, name, arguments)` 对象** |
| **Pydantic 强校验** | `args_type.model_validate(args)` 在 `BaseTool.run_json()` 入口 | **强借鉴**：Onion 的工具执行器必须在入口校验 args，**LLM 给了错 JSON 不应该直接崩** — 应该 catch ValidationError → 包装成 `ToolResult(is_error=True)` 回传 LLM |
| **normalize_name()** | LLM 偶尔给带非法字符的工具名，AutoGen 自动替换为 `_` | **借鉴**：Onion Agent 也应该做这一步，**作为防御性设计** |
| **max_tool_iterations 循环** | `_assistant_agent.py:1186` 的 `for loop_iteration in range(max_tool_iterations)` | **借鉴**：Onion 的 `Agent Loop` 是 session.json 自动累加器，**但循环上限必须显式**，避免无限循环 |
| **tool_call_summary_format / formatter** | `{result}` 占位符 + 自定义 Callable | **借鉴**：Onion 的大结果处理可以分两档：**默认截断 4KB / formatter 完全自定义** |
| **MCP Filesystem Workbench 默认放开 home** | Gallery 默认 `~` + `tempfile.gettempdir()` | **警惕**：Onion Agent **绝不能默认放开 home**，必须白名单校验 |
| **Pydantic `Component` 序列化** | 每个 `BaseTool` / `Workbench` 都是 `Component[Config]`，`dump_component()` / `load_component()` 完美 round-trip | **强借鉴**：Onion 的工具配置应该全部走 Pydantic `Component`，**避免 YAML / JSON 手写解析** |
| **Workbench 抽象** | `list_tools / call_tool / start / stop / reset / save_state / load_state` 全生命周期 | **强借鉴**：Onion 的 `Tool Channel` 应该是 `Workbench` 列表（而非散落的 tool list），**支持多后端统一管理** |
| **3 种 MCP transport 抽象** | `StdioServerParams` / `SseServerParams` / `StreamableHttpServerParams` discriminated union | **借鉴**：Onion 的 MCP 客户端应该至少支持 stdio + streamable_http，**用 discriminated union 而非 if-else 路由** |
| **反向通道**（Sampling / Elicitation / Roots） | `McpSessionHost` 让 MCP server 调起 host 的 LLM / 询问用户 | **P2 借鉴**：Onion 的 MCP 集成可以先只做"正向调用"，反向通道留 P2 阶段 |
| **MCP config 不读文件** | 完全在 Python 代码里 `StdioServerParams(...)` | **警惕**：Onion 应当**支持 `<repo>/.onion/mcp.json`**（参考 standard §10.8），**比 AutoGen 走得更远** — 用户期望"改配置文件就能加 MCP server" |

**一句话总结**：**AutoGen 的"Tool Channel"是行业最强（Workbench 抽象 + Pydantic Component 序列化 + 多协议 Provider 无关），但"Tool 配置管理"是反面教材（无 mcp.json / 无 folder-trust / 无 LLM 凭证白名单）**。Onion Agent **学 AutoGen 的"工具运行时"，避开 AutoGen 的"工具配置面"**。

---

## 5. 不确定 / 未找到

1. **Agent Skills（Anthropic-style SKILL.md）**：源码确认**不支持**。`autogen-studio/autogenstudio/web/skills/user/` 在 `.gitignore` 里有但代码无引用，疑似废弃占位。
2. **`McpServerParams` 的反序列化支持**：`tool_overrides: Dict[str, ToolOverride]` 字段已支持，但 `McpWorkbench._from_config()` 不读 `host` 字段的全部能力（仅基本反序列化），复杂的 `McpSessionHost` 配置项可能 round-trip 丢失。
3. **`max_tool_iterations` 的默认行为变化**：源码里看到注释"default 1"，但 CLI / Studio UI 里是否有不同的默认（如 CLI 默认 10，Studio 默认 1）— 未深查。
4. **`tool_choice` 在 Anthropic 协议下的限制**：`_anthropic_client.py:660-664` 注释说 "According to Anthropic API, tool_choice may only be specified while providing tools" — Anthropic 不支持 `tool_choice: "none"` 关掉 tool use，但 `_assistant_agent.py:1467` 的 reflection flow 用 `tool_choice="none"` 强制关闭 — **这个差异是否真的兼容，未实测**。
5. **并行 tool call 的取消语义**：`asyncio.gather(...)` 默认是"all or none"，如果 4 个 tool call 中 1 个超时取消，其他 3 个会怎样？— `_workbench.py:294-296` 有 `cancellation_token.link_future(result_future)`，但 gather 自身的取消传播未深查。
6. **McpWorkbench 的 `save_state` / `load_state` 实际意义**：`_workbench.py:457-464` 返回固定的 `McpWorkbenchState().model_dump()`（空状态），`reset()` 是 no-op — **MCP session 本身没有"状态持久化"概念**，这个实现是 placeholder。
7. **`pyautogen` 旧版 `register_function` / `register_for_execution` 模式**：v0.2 时代的 tool registration，**在 v0.4+ 已废弃**，但用户从 v0.2 迁移时会问"工具怎么注册" — 答案就是 `FunctionTool(func, description=...)` 包装，但文档未明确写迁移指南。
8. **Azure AI Search 工具的认证模型**：`tools/azure/_ai_search.py:30+` 的认证 token 来源（默认 Azure CLI？Managed Identity？）— 未深查。

---

**报告完。**
