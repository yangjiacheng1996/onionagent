# ChatDev — 工具调用（Tool Channel）调研报告

> 调研对象：`OpenBMB/ChatDev` 仓库 `main` 分支的当前 `HEAD`（README 自报为 **ChatDev 2.0 (DevAll)**，2026-01-07 发布）。
> 经典 ChatDev 1.0 已迁到 `chatdev1.0` 分支；本报告所有代码证据来自 `main`。

---

## 0. 智能体一句话定位

**ChatDev 2.0 (DevAll)**：一个 Zero-Code 多智能体编排平台。用 YAML DAG 自由拼装 `agent` / `python` / `tooling` / `human` / `literal` / `loop_counter` / `loop_timer` / `passthrough` / `subgraph` 节点；每次运行在 `WareHouse/<session>/` 里建沙箱；**核心循环是"agent → function call → tool 反馈 → 回到 agent"**，tool 协议走 OpenAI Chat Completions / OpenAI Responses / Gemini FunctionDeclaration 三种 provider 的原生 function calling。**不是 Anthropic XML 协议，不是 Cline 风格 XML 解析，是纯 function calling**。

---

## 1. 调研依据

| 文件 / 目录 | 用途 |
| --- | --- |
| `runtime/node/agent/tool/tool_manager.py:1-95` | `ToolManager` 主类，统一 function / mcp_remote / mcp_local 三类工具 |
| `entity/configs/node/tooling.py:1-140` | `ToolingConfig` / `FunctionToolConfig` / `McpRemoteConfig` / `McpLocalConfig` 四类配置 dataclass |
| `entity/tool_spec.py:1-32` | `ToolSpec` provider-agnostic 抽象 + `to_openai_dict` / `to_gemini_function` 转换 |
| `entity/configs/node/agent.py:1-120` | `AgentConfig` dataclass（每个 agent 节点持有 `tooling: List[ToolingConfig]`） |
| `runtime/node/executor/agent_executor.py:1-180` | agent 节点主循环、tool loop limit、retry、parse 错误处理 |
| `runtime/node/agent/providers/openai_provider.py:1-300` | OpenAI 工具调用协议构造 + 解析（含 `tool_calls` 字段、`function_call` output） |
| `runtime/node/agent/providers/gemini_provider.py:1-220` | Gemini `FunctionDeclaration` + `function_call` part 解析 + `FunctionResponsePart` 回传 |
| `runtime/node/agent/skills/manager.py:1-100` | `AgentSkillManager`：扫描 `.agents/skills/<name>/SKILL.md`，暴露 `activate_skill` / `read_skill_file` 工具 |
| `entity/configs/node/skills.py:1-60` | `AgentSkillsConfig`（`enabled: bool` + `allow: List[str]` allowlist） |
| `functions/function_calling/*.py` | 全部内置 Python 工具实现（11 个文件，~50+ 工具） |
| `utils/function_manager.py:1-60` | `FunctionManager`：动态 `importlib` 加载 `functions/function_calling/**/*.py` |
| `utils/function_catalog.py:1-150` | `FunctionCatalog`：从 Python type annotations + docstring 自动生成 JSON Schema |
| `entity/messages.py:130-220` | `ToolCallPayload` / `FunctionCallOutputEvent` 内部统一数据结构 |
| `entity/configs/node/agent.py:100-130` | `AgentRetryConfig` 模型层 retry（5 次 / 指数退避） |
| `yaml_instance/ChatDev_v1.yaml` | CEO / CTO / Programmer / Reviewer / Tester 多角色工具列表实例 |
| `yaml_instance/demo_mcp.yaml` | MCP 工具（`type: mcp_remote`）使用样例 |
| `yaml_instance/demo_function_call.yaml` | function tool 使用样例 |
| `docs/user_guide/zh/modules/tooling/function.md` | 函数工具配置文档 |
| `docs/user_guide/zh/modules/tooling/mcp.md` | MCP 工具配置文档 |
| `.agents/skills/python-scratchpad/SKILL.md` | 一个实际 Skill 样本（YAML frontmatter + markdown body） |
| `mcp_example/mcp_server.py:1-30` | FastMCP 示例 server |

---

## 2. 五个核心问题的回答

### Q1. 工具来源

ChatDev 2.0 有 **三类工具源**，每类独立配置、独立加载、独立暴露给 LLM。

#### 1.1 内置工具（`functions/function_calling/`，**11 个文件 / 50+ 函数**）

| 模块 | 关键函数 | 用途 | 代码位置 |
| --- | --- | --- | --- |
| `file.py` | `describe_available_files` / `list_directory` / `create_folder` / `delete_path` / `load_file` / `save_file` / `read_text_file_snippet` / `read_file_segment` / `apply_text_edits` / `rename_path` / `copy_path` / `move_path` / `search_in_files` | **完整的 workspace 文件系统工具集**（11 个），全部走 `FileToolContext` 校验路径在 `code_workspace/` 沙箱内 | `functions/function_calling/file.py:100-360` |
| `uv_related.py` | `init_python_env` / `install_python_packages` / `uv_run` | uv 进程内 Python 环境管理 + 代码执行 | `functions/function_calling/uv_related.py:108-280` |
| `code_executor.py` | `execute_code` | 单文件代码执行（基于 `subprocess`） | `functions/function_calling/code_executor.py:1-50` |
| `web.py` | `web_search`（Serper API） / `read_webpage_content`（Jina reader） | 网页搜索 + 抓取 | `functions/function_calling/web.py:4-140` |
| `video.py` | `render_manim` / `concat_videos` | Manim 视频渲染 + ffmpeg 合并 | `functions/function_calling/video.py:8-100` |
| `user.py` | `call_user` | 通过 `HumanPromptService.request()` 触发人工确认 | `functions/function_calling/user.py:1-30` |
| `weather.py` | `get_weather` / `get_city_num` | 天气样例（mock） | `functions/function_calling/weather.py:1-30` |
| `deep_research.py` | `search_save_result` / `report_create_chapter` / `report_rewrite_chapter` / `report_continue_chapter` / `report_reorder_chapters` / `report_del_chapter` / `report_outline` / `report_read` / `report_export_pdf` | 9 个深度研究/报告工具（带 `filelock` 写锁） | `functions/function_calling/deep_research.py:1-540` |
| `utils.py` | 工具辅助 | 通用 helper | `functions/function_calling/utils.py:1-50` |

**亮点**：所有工具函数通过 Python `inspect` 反射 + 类型注解 + `ParamMeta(description=...)` 自动生成 OpenAI / Gemini 兼容的 JSON Schema —— **零手动维护 schema**（`utils/function_catalog.py:140-220`）。用户用 `Annotated[str, ParamMeta(description="路径")]` 描述参数即可，运行时 `inspect.signature(fn)` + `_build_parameters_schema()` 自动转换为 OpenAI `{"type":"object","properties":{...}}` 格式。

#### 1.2 MCP 支持（**两种模式**）

`entity/configs/node/tooling.py:430-475` 注册了两类 MCP 配置：

| 类型 | 配置 dataclass | 传输 | 关键字段 | 代码位置 |
| --- | --- | --- | --- | --- |
| `function` | `FunctionToolConfig` | 仓库内置 Python 函数 | `tools: List[Dict]` / `auto_load: bool` / `timeout: float` | `entity/configs/node/tooling.py:95-260` |
| `mcp_remote` | `McpRemoteConfig` | HTTP/SSE MCP server | `server: str` / `headers: Dict[str,str]` / `timeout: float` / `cache_ttl: float` | `entity/configs/node/tooling.py:265-380` |
| `mcp_local` | `McpLocalConfig` | stdio MCP server（进程内） | `command: str` / `args: List[str]` / `cwd: str` / `env: Dict[str,str]` / `inherit_env: bool` / `startup_timeout: float` / `wait_for_log: str` (regex) | `entity/configs/node/tooling.py:385-500` |

MCP 客户端用 `fastmcp.Client`（`tool_manager.py:7-9` + `:53-83`）。`mcp_local` 模式**长期驻留进程**：`_StdioClientWrapper` 用 `asyncio.new_event_loop()` + `threading.Thread` 在独立线程里跑 `client.__aenter__()` 初始化，保持 stdio 通道常驻（`tool_manager.py:412-480`），关闭调用 `keep_alive=False` 才退出。

**配置入口**：`yaml_instance/demo_mcp.yaml:14-18`：
```yaml
tooling:
  - type: mcp_remote
    config:
      server: http://127.0.0.1:8001/mcp
```

**反例**：**没有全局 `~/.chatdev/mcp.json` 配置文件**。MCP server 注册完全在 YAML DAG 节点内声明，**没有用户级 MCP 注册表**。仓库内只有一个参考 MCP server 在 `mcp_example/mcp_server.py:1-30`。

#### 1.3 Agent Skills 支持（**progressive disclosure，YAML frontmatter**）

`runtime/node/agent/skills/manager.py:14-17` 写死 `DEFAULT_SKILLS_ROOT = (REPO_ROOT / ".agents" / "skills").resolve()` —— **扫描 `<仓库根>/.agents/skills/<skill_name>/SKILL.md`**。

每个 Skill 是一个目录 + `SKILL.md`（YAML frontmatter + markdown body），例：`.agents/skills/python-scratchpad/SKILL.md:1-3`：
```yaml
---
name: python-scratchpad
description: Use the existing Python execution tools as a scratchpad for calculations...
allowed-tools: execute_code
---
```

- **`name` / `description` frontmatter 必填**（`manager.py:38-42`）
- **`allowed-tools` 列出该 skill 允许使用的外部工具名**（`manager.py:43-44`），不兼容的 skill 在 `_is_skill_compatible()` 里被过滤（`manager.py:230-250`）
- **目录名必须与 `name` 字段一致**（`manager.py:40-42`）
- **MAX_SKILL_FILE_BYTES = 128 KiB**（`manager.py:18`，单文件读取上限）

启用后，`AgentSkillManager.build_tool_specs()` 暴露两个内置 tool 给 LLM（`manager.py:200-230`）：
1. `activate_skill(skill_name)` — 加载完整 `SKILL.md` markdown 内容
2. `read_skill_file(skill_name, relative_path)` — 读取 skill 目录下的引用文件（≤128 KiB）

**system prompt 注入**：`_build_system_prompt()` 注入 `<available_skills>` XML 列表（`agent_executor.py:215-235`），格式：
```xml
<available_skills>
  <skill>
    <name>python-scratchpad</name>
    <description>...</description>
    <location>.../SKILL.md</location>
    <allowed_tools>
      <tool>execute_code</tool>
    </allowed_tools>
  </skill>
</available_skills>
```

**反例**：**技能目录是仓库级，不是用户级 / 项目级**。跟 OpenClaw 的 `~/.openclaw/workspace/skills/` 或 superpowers 的 `<repo>/.superpowers/skills/` 都不一样 —— ChatDev **没有 `~/.chatdev/skills/`**。

#### 1.4 其他工具类型

- **Python 节点（独立于 function tool）**：`entity/configs/node/python_runner.py` 定义的 `python` 节点是**完整的 Python 脚本执行节点**（不是 LLM 调用的 tool），每次执行写 `<graph_dir>/code_workspace/<node_id>.py` 或 `<node_id>_run-N.py`（`runtime/node/executor/python_executor.py:60-100`）。**它不进入 LLM tool 列表**，而是 DAG 中的一个节点类型。
- **记忆节点（memory）**：`entity/configs/node/memory.py` 定义的 `memory` 节点也是 DAG 节点类型，不进入 LLM tool 列表。
- **Human 节点**：`human` 节点通过 `HumanPromptService` 把 prompt 发到前端让真人回复，是 DAG 节点类型。

**结论**：LLM 可见的工具列表只有 3 类（function / mcp_remote / mcp_local + skill 内置 2 个）。其他 7 种节点类型是 DAG 编排元素，**不是 LLM 工具**。

---

### Q2. 工具列表的生成、传递、格式

#### 2.1 生成方式

**YAML 静态声明 + 启动时一次性加载**。`AgentConfig.from_dict()` 在 DAG 解析时把每个 agent 节点的 `tooling: List[Dict]` 列表解析为 `List[ToolingConfig]`（`entity/configs/node/agent.py:230-245`）。运行时通过 `ToolManager.get_tool_specs(tool_configs)` 一次性产出 `List[ToolSpec]`（`tool_manager.py:118-180`）。

**生成逻辑**（按 `tool_config.type` 分发）：
- `function` → `FunctionCatalog` 查 `functions/function_calling/` 里的函数元数据，自动生成 schema（`tool_manager.py:215-250`）
- `mcp_remote` → 第一次调用 `await client.list_tools()` HTTP 拉取工具列表，结果**按 `cache_key()` 缓存在 `_mcp_tool_cache`**（`tool_manager.py:252-275`）
- `mcp_local` → 第一次调用 stdio 客户端的 `list_tools()`，同样缓存（`tool_manager.py:277-300`）

**`module_name:All` 语法**：YAML 里写 `name: uv_related:All` 会展开为该模块下全部函数（`entity/configs/node/tooling.py:220-260`），批量引入，**禁止同时填 `description` / `parameters` / `auto_fill`**。

**prefix 防冲突**：`ToolingConfig.prefix` 给该工具源所有 tool 加前缀（`tool_manager.py:175-185`），避免多个 MCP server 工具名撞车。

#### 2.2 传递给 LLM

通过 **OpenAI Chat Completions 的 `tools` 数组 / OpenAI Responses API 的 `tools` 数组 / Gemini 的 `tool.function_declarations`**，三种 protocol 互斥（按 `AgentConfig.provider` 选一种）。

**OpenAI Chat Completions 构造**（`openai_provider.py:226-280`）：
```python
merged_tools: List[Any] = []
if tool_specs:
    for spec in tool_specs:
        merged_tools.append({
            "type": "function",
            "function": {
                "name": spec.name,
                "description": spec.description,
                "parameters": spec.parameters or {"type": "object", "properties": {}},
            }
        })
if merged_tools:
    payload["tools"] = merged_tools
if tool_specs:
    payload.setdefault("tool_choice", "auto")
```

**OpenAI Responses API 构造**（`openai_provider.py:170-220`）：直接用 `spec.to_openai_dict()` 产出 `{"type":"function","name":...,"description":...,"parameters":...}`（`entity/tool_spec.py:17-23`）。

**Gemini 构造**（`gemini_provider.py:550-580`）：
```python
for spec in tool_specs:
    fn_payload = spec.to_gemini_function()  # {"name":..., "description":..., "parameters":...}
    declarations.append(
        genai_types.FunctionDeclaration(
            name=fn_payload.get("name", ""),
            description=fn_payload.get("description") or "",
            parameters=parameters,
        )
    )
return [genai_types.Tool(function_declarations=declarations)]
```

#### 2.3 实际 JSON 片段

来自 `yaml_instance/demo_function_call.yaml:14-22` 的 `tooling`：
```yaml
tooling:
  - type: function
    config:
      auto_load: true
      tools:
        - name: get_weather
        - name: get_city_num
```

运行时展开为 OpenAI `tools` 数组（简化）：
```json
[
  {
    "type": "function",
    "function": {
      "name": "get_weather",
      "description": "Fetch weather information for the city represented by ``city_num``.",
      "parameters": {
        "type": "object",
        "properties": {
          "city_num": {"type": "integer"},
          "unit": {"type": "string", "enum": ["celsius", "fahrenheit"], "default": "celsius"}
        },
        "required": ["city_num"]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "get_city_num",
      "description": "Fetch the city code for a given city name.",
      "parameters": {
        "type": "object",
        "properties": {"city": {"type": "string"}},
        "required": ["city"]
      }
    }
  }
]
```

#### 2.4 格式

**JSON Schema（OpenAI 风格） / FunctionDeclaration（Gemini 风格）**。**不是 XML 协议**，**不是 Cline 风格 prompt-as-tool**。是纯 native function calling。

#### 2.5 动态刷新

- **MCP 工具列表**：有 `cache_ttl` 字段（`entity/configs/node/tooling.py:330-345` + `:480-495`），`cache_ttl=0` 表示不缓存（热更新），否则按秒缓存。`_mcp_tool_cache: Dict[str, List[Any]]`（`tool_manager.py:34`）
- **Function 工具列表**：**启动时一次性 `FunctionManager.load_functions()` 加载到内存**（`utils/function_manager.py:55-95`），不热重载（除非显式 `reload_functions()`）
- **Skills 列表**：**每个 agent 节点启动时 `AgentSkillManager.discover()` 扫描**（`manager.py:130-145`），缓存在 `_skills_by_name: Dict[str, SkillMetadata]`

**ChatDev 没有 stream 增量解析**：全仓库 `grep "stream=True"` 0 命中，所有 model 调用都是 `client.chat.completions.create(**payload)` / `client.responses.create(**payload)` 同步调用。**不是流式**。

---

### Q3. 工具调用指令的解析、错误修复、准确性

#### 3.1 解析方式

内部统一数据结构 `ToolCallPayload`（`entity/messages.py:155-175`），三个 provider 各自反序列化为 `ToolCallPayload(id, function_name, arguments, type="function")`。

**OpenAI Chat Completions 解析**（`openai_provider.py:325-355`）：
```python
for idx, tc in enumerate(tc_data):
    f_data = self._get_attr(tc, "function") or {}
    function_name = self._get_attr(f_data, "name") or ""
    arguments = self._get_attr(f_data, "arguments") or ""   # 一定是字符串
    call_id = self._get_attr(tc, "id")
    if not call_id:
        call_id = self._build_tool_call_id(function_name, arguments, fallback_prefix=f"tool_call_{idx}")
    tool_calls.append(ToolCallPayload(id=call_id, function_name=function_name, arguments=arguments, type="function"))
```

**OpenAI Responses API 解析**（`openai_provider.py:530-570`）：遍历 `response.output[]` 找 `type=tool_call` 或 `type=function_call` 的 item，调 `_parse_tool_call()`。

**Gemini 解析**（`gemini_provider.py:665-700`）：
```python
function_call = getattr(part, "function_call", None)
if function_call:
    tool_calls.append(self._build_tool_call_payload(function_call, ...))
```

`ToolCallPayload.arguments` **统一是字符串**（不是 dict），由 `agent_executor._parse_tool_call_arguments()` 延迟 JSON 解析（`agent_executor.py:1080-1100`）：
```python
def _parse_tool_call_arguments(self, raw_arguments: Any) -> Dict[str, Any]:
    if isinstance(raw_arguments, dict):
        return raw_arguments
    if not raw_arguments:
        return {}
    if isinstance(raw_arguments, str):
        try:
            parsed = json.loads(raw_arguments)
        except json.JSONDecodeError:
            return {}    # ← JSON 残缺时直接返回空 dict
        return parsed if isinstance(parsed, dict) else {}
    return {}
```

**ID 兜底**：如果 provider 没给 tool call id（`tc.id` 为空），`OpenAIProvider._build_tool_call_id()` 用 `MD5(function_name + arguments)[:8]` 合成 `f"{function_name}_{digest}"`（`openai_provider.py:590-600`）。**这样即使 provider 失忆工具调用 id，下一轮 `role=tool` 仍能匹配**。

#### 3.2 错误修复 / 重试

- **模型 API 错误（HTTP 429 / 5xx / timeout）**：`AgentRetryConfig` 提供指数退避重试（`entity/configs/node/agent.py:100-130` + `agent_executor.py:430-470`），`max_attempts=5` 默认，`retry_on_status_codes=[408,409,425,429,500,502,503,504]`，`retry_on_exception_types=["RateLimitError","APITimeoutError",...]`（前 14 行代码常量），退避 `min_wait=1s, max_wait=6s`。**用 tenacity 库实现**（`from tenacity import ...`，`agent_executor.py:30`）。
- **Tool 执行错误**：`agent_executor._execute_tool_batch` 用 try/except 捕获，**错误以 `role=tool` 消息返回给 LLM**（`agent_executor.py:680-720`），**不终止循环**。LLM 看到错误描述后**自行决定**是否重试。
- **工具名不识别**：`tool_config not found` → 同样以 `role=tool, content="Error: Tool 'xxx' configuration not found."` 回传给 LLM（`agent_executor.py:680-705`）。
- **工具名有 prefix 但 LLM 调用没带 prefix**：`spec.metadata["original_name"]` 记录原始名，`execution_name = spec.metadata.get("original_name", tool_name)` 用于实际调用（`agent_executor.py:580-590`）。
- **Tool call id 缺失**：见 3.1 的 MD5 兜底。

**Tool loop 上限**：`_get_tool_loop_limit()` 默认 **50**（`agent_executor.py:1110-1120`），可通过 `params.tool_loop_limit` 自定义。超限则**返回最后一次 assistant 消息 + warning 日志**（`agent_executor.py:540-555`），**不强制失败**。

#### 3.3 准确性保证

| 机制 | 代码位置 | 说明 |
| --- | --- | --- |
| **Schema 校验**（启动时） | `entity/configs/node/tooling.py:165-220`（`FunctionToolConfig.from_dict`） | 启动时强制校验 `name` 必须在 `FunctionCatalog` 里，否则 `ConfigError`，**保证 LLM 看到的 tool name 一定可执行** |
| **不重复 tool name** | `tool_manager.py:175-180` | prefix 机制 + 重复检测 `ConfigError("Duplicate tool name...")` |
| **Plan-then-act** | 不支持 | **没有 plan / act 模式**；agent 直接 function call |
| **Refusal 提示** | 间接（`provider=openai` 时 `tool_choice="auto"`） | 由 provider 行为决定，不由 ChatDev 控制 |
| **Schema 自动生成** | `utils/function_catalog.py:140-260` | Python type annotation + `ParamMeta(description=...)` 反射成 JSON Schema，**人工错误率低** |
| **Gemini 兼容性修复** | `gemini_provider.py:560-575` | 把 `parameters.title` 改成 `description`、把 `title` 字段剥掉，**因为 Gemini FunctionDeclaration 不支持 `title`** |

---

### Q4. 工具执行结果回传

#### 4.1 回传方式

**两种 model-protocol 各一套**：

**OpenAI Chat Completions**（`openai_provider.py:320-325`）：
```python
return {
    "role": "tool",
    "tool_call_id": event.call_id or "tool_call",
    "content": text,
}
```

**OpenAI Responses API**（`openai_provider.py:730-745`）：
```python
payload = {
    "type": event.type,  # "function_call_output"
    "call_id": event.call_id or event.function_name or "tool_call",
    "output": [{"type": "input_text", "text": text}],   # or output_blocks
}
```

**Gemini**（`gemini_provider.py:170-205`）：
```python
function_part = genai_types.Part.from_function_response(
    name=function_name,
    response=payload or {"result": ""},
    parts=function_result_parts or None
)
return genai_types.Content(role="user", parts=[function_part])
```

**多模态回传**：OpenAI Gemini 都用 `parts=[FunctionResponsePart(...)]` 携带 binary inline_data（`gemini_provider.py:225-245`）。OpenAI Responses 用 `output: [{type: "input_image", image_url: ...}]`。

#### 4.2 格式

**JSON 优先，字符串兜底**。`_normalize_mcp_result()`（`tool_manager.py:380-415`）按优先级返回：
1. `result.structured_content` （MCP 协议） → dict
2. `result.content[0].text` → str
3. 整个 `result.content[0]` → str(content)
4. None

Function tool 返回任意 Python 对象，**经 `_build_tool_message()` 序列化**（`agent_executor.py:870-940`）：
- `Message` → 克隆并 `role=TOOL`
- `AttachmentRecord` → 序列化为 `MessageBlock` 列表
- `list[MessageBlock]` → 保持原样
- `dict` → `json.dumps(..., ensure_ascii=False, indent=2)`
- 其他 → `str(result)`

#### 4.3 通信协议

**Provider-specific，每个 provider 内部一套序列化**：
- `provider=openai` → OpenAI Chat Completions / Responses 二选一（由 `params.protocol` 决定，`openai_provider.py:60-75`）
- `provider=gemini` → Gemini `generate_content`
- **没有"同时支持 OpenAI + Anthropic 协议"的多协议适配器**。**Provider 决定 protocol，tool 协议随之固定**。

#### 4.4 大结果处理

| 类型 | 策略 | 代码 |
| --- | --- | --- |
| **图片/音频/视频（base64）** | `AttachmentStore.register_bytes()` 落盘到 `code_workspace/attachments/<id>/`，返回 attachment reference | `tool_manager.py:435-475` |
| **CSV 大文件（>3MB）** | 内联为 `text`（`gemini_provider.py:330-380` 截断到 200K 字符） | `gemini_provider.py:343-380` |
| **纯文本文件** | 200K 字符 inline（`openai_provider.py:534-595` `TEXT_INLINE_CHAR_LIMIT=200_000`），超限加截断提示 | `openai_provider.py:534-595` |
| **二进制文件** | 如果 `AttachmentStore` 不可用 → `[binary content omitted: filename.png]` 占位文本（`tool_manager.py:445-460`） | `tool_manager.py:445-460` |
| **超大 inline 错误** | 50MB 上限 `MAX_INLINE_FILE_BYTES`，超限 raise `ValueError`（`openai_provider.py:765-790`） | `openai_provider.py:765-790` |

**没有 MEDIA 引用协议**。ChatDev 直接 inline 文本/图片到 `messages`，**或者**用 `AttachmentStore` 落盘 + 在 messages 里用 attachment reference（base64 data URI 或 remote_file_id），跟 OpenAI Responses 的 `input_image.image_url` / `input_file.file_id` 等价。

---

### Q5. File Backend 是否为工具调用做了适配

**简短结论**：**几乎没有**。ChatDev 2.0 的"file backend"是为 YAML DAG 运行设计的工作区（`WareHouse/<session>/`），**与工具调用系统是两套正交设计**。**没有为"工具配置"做专门的全局目录**。

#### 5.1 工具配置目录 / 文件清单

| 配置 | 实际位置 | 覆盖机制 | 全局/项目/仓库级 | 代码 |
| --- | --- | --- | --- | --- |
| **内置 function tool 注册** | `<仓库根>/functions/function_calling/*.py`（**写死**） | `MAC_FUNCTIONS_DIR` env 变量 | **仓库级**（env 可重定向，但**不是 `~/.chatdev/`**） | `utils/function_manager.py:30-38` |
| **Agent Skills** | `<仓库根>/.agents/skills/<name>/SKILL.md`（**写死**） | **无 env / 无 CLI 覆盖** | **仓库级**（无任何覆盖） | `runtime/node/agent/skills/manager.py:14-17` |
| **MCP server 注册** | YAML DAG 节点内 `tooling.config.server` 字段 | **无独立 mcp.json 配置文件** | **DAG 级**（每个工作流独立） | `yaml_instance/demo_mcp.yaml:14-18` |
| **Provider 凭据** | YAML `api_key: ${API_KEY}` 或 `params` env 变量 | env | **环境级** | `yaml_instance/demo_function_call.yaml:11-12` |
| **运行时工作区** | `<cwd>/WareHouse/<session>/` | **硬编码，相对 cwd** | **cwd 级**（无任何覆盖） | `server/settings.py:5` / `run.py:17` |

**结论**：**没有任何 `~/.chatdev/` 用户属主目录**。**没有 `~/.chatdev/mcp.json` / `~/.chatdev/skills/` / `~/.chatdev/tools.yaml` 等独立配置文件**。所有配置要么写死在仓库里，要么写在 YAML DAG 里。

#### 5.2 加载代码

- Function tool：`FunctionManager.load_functions()` 扫描 `MAC_FUNCTIONS_DIR`（`utils/function_manager.py:55-95`）
- Skills：`AgentSkillManager.discover()` 扫描 `REPO_ROOT / ".agents" / "skills"`（`manager.py:130-145`）
- MCP：`ToolManager._build_mcp_remote_specs()` 调 `client.list_tools()` HTTP 拉取（`tool_manager.py:252-275`）

#### 5.3 与 `standard/file_backend.md` 的对照

| 标准条款 | ChatDev 是否符合 | 证据 |
| --- | --- | --- |
| §2.1 固定用户属主目录 + env 单一覆盖点 | ❌ **反例** | 无 `~/.chatdev/`，无 `CHATDEV_HOME` env |
| §2.2 平台原生默认值 | ❌ **反例** | 全部硬编码 `Path("WareHouse")` 相对 cwd，不跨平台 |
| §2.3 多级覆盖链（CLI → env → 配置 → 默认） | ❌ **反例** | 无 CLI / env 覆盖 |
| §2.5 跟随当前目录 | ⚠️ **隐式跟随** | `Path("WareHouse")` 是 cwd 相对 |
| §3.1 严格三层分离（全局/项目/运行时） | ❌ **反例** | 只有运行时 `WareHouse/<session>/`，无全局/项目级 |
| §3.5 扁平单层 | ❌ **反例** | `WareHouse/<session>/{code_workspace,attachments,node_outputs.yaml,...}` 有 2 层 |
| §3.8 Bootstrap 种子文件 | ❌ | 无 |
| §8.1 用户可改存储根（信创合规） | ❌ **反例** | 硬编码 `WareHouse` |
| §8.2 跨平台路径策略 | ❌ **反例** | 全部 `Path("...")` 不走 `appdirs` |
| §10.8 MCP 协议支持 | ✅ | 强项，但只通过 YAML 内联（见 Q1.2） |
| §10.6 Server 端 session 持久化 | ❌ **反例** | `WorkflowSessionStore` 纯内存，重启即丢（参考 `file_backend.md` 第 5 节） |

**整体一致性**：**与 §8.1 / §8.2 反例完全吻合**（参见 `file_backend.md` 的"信创支持 ❌"和"反例"标注），是 20 个项目里**信创合规最差**的之一。

---

## 3. 关键代码片段

### 3.1 `ToolManager.get_tool_specs` —— 工具列表统一入口

`runtime/node/agent/tool/tool_manager.py:118-185`：

```python
def get_tool_specs(self, tool_configs: List[ToolingConfig] | None) -> List[ToolSpec]:
    """Return provider-agnostic tool specifications for the given config list."""
    if not tool_configs:
        return []

    specs: List[ToolSpec] = []
    seen_tools: set[str] = set()

    for idx, tool_config in enumerate(tool_configs):
        current_specs: List[ToolSpec] = []
        if tool_config.type == "function":
            config = tool_config.as_config(FunctionToolConfig)
            current_specs = self._build_function_specs(config)
        elif tool_config.type == "mcp_remote":
            config = tool_config.as_config(McpRemoteConfig)
            current_specs = self._build_mcp_remote_specs(config)
        elif tool_config.type == "mcp_local":
            config = tool_config.as_config(McpLocalConfig)
            current_specs = self._build_mcp_local_specs(config)
        # ...

        prefix = tool_config.prefix
        for spec in current_specs:
            final_name = f"{prefix}_{spec.name}" if prefix else spec.name
            if final_name in seen_tools:
                raise ConfigError(f"Duplicate tool name '{final_name}' detected.")
            seen_tools.add(final_name)
            spec.name = final_name
            spec.metadata["_config_index"] = idx
            spec.metadata["original_name"] = original_name
            specs.append(spec)

    return specs
```

### 3.2 `ToolCallPayload` —— Provider 无关的统一数据结构

`entity/messages.py:155-180`：

```python
@dataclass
class ToolCallPayload:
    """Unified representation of a tool call request."""

    id: str
    function_name: str
    arguments: str   # 统一是字符串
    type: str = "function"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_openai_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "function": {
                "name": self.function_name,
                "arguments": self.arguments,
            },
        }
```

### 3.3 `_handle_tool_calls` —— Tool loop 主循环（含 50 次上限 + tool 错误注入）

`runtime/node/executor/agent_executor.py:520-570`：

```python
def _handle_tool_calls(self, node, provider, client, conversation, timeline,
                       call_options, initial_response, tool_specs, skill_manager):
    assistant_message = initial_response.message
    trace_messages: List[Message] = []
    loop_limit = self._get_tool_loop_limit(node)   # default 50
    iteration = 0

    while True:
        self._ensure_not_cancelled()
        cloned_assistant = self._clone_with_source(assistant_message, node.id)
        conversation.append(cloned_assistant)
        trace_messages.append(cloned_assistant)

        if not assistant_message.tool_calls:
            return self._finalize_tool_trace(...)

        if iteration >= loop_limit:
            self.log_manager.warning(f"[Node: {node.id}] Tool call limit {loop_limit} reached...")
            return self._finalize_tool_trace(...)

        iteration += 1

        tool_call_messages, tool_events = self._execute_tool_batch(...)
        conversation.extend(tool_call_messages)
        timeline.extend(tool_events)

        follow_up_response = self._invoke_provider(...)
        assistant_message = follow_up_response.message
```

### 3.4 Agent Skills progressive disclosure

`runtime/node/agent/skills/manager.py:155-175`（`activate_skill` 实现）：

```python
def activate_skill(self, skill_name: str) -> Dict[str, str | List[str]]:
    skill = self._get_skill(skill_name)
    cached = self._skill_content_cache.get(skill.name)
    if cached is None:
        cached = skill.skill_file.read_text(encoding="utf-8")    # 整篇 markdown 注入
        self._skill_content_cache[skill.name] = cached
    self._activation_state[skill.name] = True
    self._current_skill_name = skill.name
    return {
        "skill_name": skill.name,
        "path": str(skill.skill_file),
        "instructions": cached,
        "allowed_tools": list(skill.allowed_tools),
    }
```

> LLM 调用 `activate_skill` 后，**`agent_executor._build_skill_followup_message()` 会把 SKILL.md 全文作为 `role=system` 消息注入 conversation**（`agent_executor.py:780-820`），让 LLM"消化"Skill 指令后继续工作。

### 3.5 `AgentRetryConfig` —— 模型层 retry（5 次指数退避）

`entity/configs/node/agent.py:100-130`：

```python
@dataclass
class AgentRetryConfig(BaseConfig):
    enabled: bool = True
    max_attempts: int = 5
    min_wait_seconds: float = 1.0
    max_wait_seconds: float = 6.0
    retry_on_status_codes: List[int] = field(default_factory=lambda: list(DEFAULT_RETRYABLE_STATUS_CODES))
    retry_on_exception_types: List[str] = field(default_factory=lambda: [name.lower() for name in DEFAULT_RETRYABLE_EXCEPTION_TYPES])
    non_retry_exception_types: List[str] = field(default_factory=list)
    retry_on_error_substrings: List[str] = field(default_factory=lambda: list(DEFAULT_RETRYABLE_MESSAGE_SUBSTRINGS))
```

触发器（`agent.py:50-80`）：
```python
DEFAULT_RETRYABLE_STATUS_CODES = [408, 409, 425, 429, 500, 502, 503, 504]
DEFAULT_RETRYABLE_EXCEPTION_TYPES = [
    "RateLimitError", "APITimeoutError", "APIError", "APIConnectionError",
    "ServiceUnavailableError", "TimeoutError", "InternalServerError",
    "RemoteProtocolError", "TransportError", "ConnectError",
    "ConnectTimeout", "ReadError", "ReadTimeout",
]
DEFAULT_RETRYABLE_MESSAGE_SUBSTRINGS = [
    "rate limit", "temporarily unavailable", "timeout",
    "server disconnected", "connection reset",
]
```

---

## 4. 与 Onion Agent 设计的关联

### 4.1 借鉴（对 Onion Agent 有价值的部分）

1. **`ToolSpec` provider-agnostic 中间表示**：ChatDev 的 `entity/tool_spec.py` 用一个 dataclass 持有 `name/description/parameters`，再分发到 `to_openai_dict()` / `to_gemini_function()`。Onion Agent 可以抄 —— 单一 source of truth 写 schema，多协议派生，避免每加一个 provider 就重写一遍 OpenAI/Anthropic/Gemini 转换。
2. **JSON Schema 从 Python 注解自动生成**：`utils/function_catalog.py:140-260` 用 `inspect.signature()` + `typing.Annotated[..., ParamMeta(description=...)]` 自动生成 OpenAI 风格 schema。Onion Agent 可以照搬，让 `from typing import Annotated` + `ParamMeta` 成为 "Onion tool 的标准签名风格"。
3. **`module_name:All` 批量引入机制**：`yaml_instance/ChatDev_v1.yaml:115-122` 的 `name: uv_related:All` 一行引入整模块 8 个工具，避免长 YAML 列表。Onion Agent 如果在 YAML 配 tool，可以引入 `onion.tools.files:all` 这种语法。
4. **Tool call ID 的 MD5 兜底**：`OpenAIProvider._build_tool_call_id()` 在 provider 漏给 id 时合成 `MD5(name+args)[:8]`。Onion Agent 应同等设计 —— **id 缺失不能崩**，必须保证下一轮 `role=tool` 能 match。
5. **MCP remote / local 双模式**：`McpRemoteConfig`（HTTP/SSE） + `McpLocalConfig`（stdio 长驻进程）的拆法非常清晰，**Onion Agent 必须**提供这两种 mode（不是只 stdio 或只 HTTP）。
6. **Agent Skills progressive disclosure + XML 注入 system prompt**：`AgentSkillManager.build_available_skills_xml()` 在 system prompt 注入 `<available_skills>` 列表，LLM 主动 `activate_skill` 才加载全文。Onion Agent 应该用同一个模式 —— **不要把全部 SKILL.md 都塞进 system prompt**，让 LLM 按需 lazy load。
7. **Tool loop 50 次上限 + warning 日志（不抛错）**：`tool_loop_limit=50` 是"工具调用循环"的安全阀，**不能无限循环**。Onion Agent 的 Agent Loop 必须有相同硬上限。
8. **`execute_skill_tool` 错误也注入到 conversation**：激活 skill 后工具调用错也以 `role=tool` 回传，让 LLM 看到错误决定下一步。Onion Agent 应同等设计 —— **tool 错不静默**。

### 4.2 规避（ChatDev 的坑）

1. **写死 `Path("WareHouse")` + 无 env/cli 覆盖**：Onion Agent 必须在 P0 阶段就把 `ONION_HOME` 单点覆盖做掉（参见 `file_backend.md` §12.1 P0 清单）。
2. **没有用户级工作区**：`~/.chatdev/` 不存在。Onion Agent 必须有 `~/.onion/`（参见 `file_backend.md` §1.1 / §2.1）。
3. **无流式输出（`stream=True`）**：ChatDev 全仓库 0 命中。**用户体验差** —— 大响应时用户看到一片空白。Onion Agent 必须支持流式（SSE / WebSocket / stdout 实时刷新）。
4. **Tool 错误无 retry 机制**（仅靠 LLM 自觉）：`_execute_tool_batch` 的 try/except 只是把错误注入 `role=tool` 让 LLM 处理。**没有"自动重试 N 次后再交给 LLM"**。Onion Agent 可以做"transient error（timeout / 5xx）自动重试 3 次"的硬策略。
5. **Skills 目录写死 `<repo>/.agents/skills/`**：Onion Agent 应该是 `~/.onion/skills/`（用户级）+ `<repo>/.onion/skills/`（项目级），**双层**。
6. **MCP server 注册在 YAML 内**（无独立 `mcp.json`）：Onion Agent 应该**全局 `~/.onion/mcp.json` + 项目级 `<repo>/.onion/mcp.json`** 双层（参考 `file_backend.md` §10.8）。
7. **`grep "stream=True" 0 命中`**：所有 model 调用都是同步阻塞。Onion Agent 至少要支持 `stream=True`（OpenAI + Anthropic 协议都需要）。
8. **Server 端 session 纯内存**（`server/services/session_store.py:67-83`）：重启即丢，**与"`WareHouse/<session>/` 落盘"的设计目标不一致**。Onion Agent 如果做 server，session 必须落盘。
9. **provider 切换不灵活**：`AgentConfig.provider` 是单选。Onion Agent 应该允许同一节点多 provider fallback（参考 opencode 的 provider-agnostic）。
10. **没有 `update_plan` / `record_memory` 这种"工具调用辅助机制"**：ChatDev 工具集都是"动作型"（读、写、跑、搜），**没有"计划工具"**。Onion Agent 可以加 `update_plan` / `record_memory` 这类"反思型"工具来支持 plan-then-act。

---

## 5. 不确定 / 未找到

| 项 | 说明 |
| --- | --- |
| **stream 增量解析** | 全仓库 `grep "stream=True"` **0 命中**。所有 model 调用都是同步阻塞（`client.chat.completions.create()` 不带 stream）。**ChatDev 2.0 没有流式输出**。这是与 MiniMax Code / Claude Code / Cline 的最大差异之一。 |
| **function tool 错误自动重试** | 源码里**没有**"tool 失败自动 retry N 次"的逻辑。错误直接以 `role=tool` 注入让 LLM 决定（`agent_executor.py:680-720`）。如果 LLM 一直给出错的参数，**会一直循环到 `tool_loop_limit=50` 才返回**。 |
| **Anthropic 协议支持** | `runtime/node/agent/providers/` 下只有 `openai_provider.py` / `gemini_provider.py` / `builtin_providers.py`，**没有 `anthropic_provider.py`**。**ChatDev 2.0 不支持 Anthropic 原生 protocol**（Claude 模型走 `base_url` 兼容 OpenAI 协议，但 tool call 协议仍是 OpenAI 风格）。 |
| **多协议适配层** | 工具调用的多协议适配是**隐式按 provider 走的**（`provider=openai` → OpenAI Chat / Responses；`provider=gemini` → Gemini），**没有"OpenAI vs Anthropic vs Gemini 共存"的适配层**。 |
| **Skills 路径覆盖** | `manager.py:14-17` 写死 `REPO_ROOT / ".agents" / "skills"`，**没有 env / CLI 覆盖**。如果用户想把 skills 放 `~/.chatdev/skills/`，必须改源码。 |
| **tool call 增量解析的 `delta.tool_calls`** | 既然 ChatDev 不 stream，**就没有 OpenAI 的 `delta.tool_calls` 流式拼接代码**。这部分**不适用**。 |
| **`~/.chatdev/` 用户级配置** | **不存在**。这是 ChatDev 在 20 个项目里信创合规最差的体现之一。 |
| **`refresh_tools` / `reload_tools` 热加载** | **没有**。MCP `cache_ttl=0` 可以热拿 tool list，但**function 工具 hot reload 不可用**。 |
| **是否支持图像/视频/音频 tool** | 工具是**文字结果**（file path 或 base64），**没有"多模态 tool"**（如 tool 返回图片给 LLM 看）。MCP `ImageContent` / `AudioContent` 会被自动转 `AttachmentStore` 落盘 + reference 引用（`tool_manager.py:410-475`），但**不是 inline base64 给 LLM**。 |

---

**报告完**。核心结论：ChatDev 2.0 的工具调用是**成熟的 OpenAI / Gemini function calling + MCP 双模式 + Skills progressive disclosure** 三件套，**但完全无流式、无 user-level config、无 tool error retry**，是**"功能完整但生产化弱"**的代表。Onion Agent 应借鉴其 schema 自动生成、Skills lazy load、MCP 双模式拆分；规避其无流式、无 `~/.onion/`、无 tool error retry。
