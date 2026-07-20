# CrewAI — 工具调用（Tool Channel）调研报告

## 0. 智能体一句话定位

CrewAI 是基于"角色（Role）+ 目标（Goal）+ 工具（Tools）+ 流程（Process）"的多 Agent 编排框架，把每个 Agent 视作"给员工写任务书"，通过 YAML/Python 声明式装配多 Agent 协作（Crew / Flow / LiteAgent 三形态）。

## 1. 调研依据

- 源码路径：`C:\workspace\github\onionagent\harness\01_market_research\clone\crewAI\`
- 关键文件：
  - `lib/crewai/src/crewai/mcp/` — 原生 MCP 客户端实现（client.py / config.py / filters.py / tool_resolver.py / transports/）
  - `lib/crewai/src/crewai/skills/` — Anthropic Agent Skills 标准实现（loader.py / models.py / parser.py / validation.py）
  - `lib/crewai/src/crewai/tools/` — BaseTool、CrewStructuredTool、ToolUsage、MCPToolResolver
  - `lib/crewai/src/crewai/tools/agent_tools/` — 内置 5 个 Agent 工具
  - `lib/crewai/src/crewai/agents/step_executor.py` — Plan-and-Act 单步执行器（双模式：native + text 解析）
  - `lib/crewai/src/crewai/agents/parser.py` — ReAct 格式文本解析
  - `lib/crewai/src/crewai/llms/providers/anthropic/completion.py` — Anthropic 协议实现（含 input_json_delta 流式解析）
  - `lib/crewai/src/crewai/llms/providers/openai_compatible/completion.py` — OpenAI / Ollama / DeepSeek / vLLM 等 7 个兼容 provider
  - `lib/crewai/src/crewai/project/crew_base.py` — `@CrewBase` 元类（`base_directory` 自动绑定）
- 文档：源码内 docstring + 目录注释，README 未在此 snapshot 中包含完整功能列表

## 2. 五个核心问题的回答

### Q1. 工具来源

**内置工具**（crewai 核心包内）：
- `DelegateWorkTool`（`tools/agent_tools/delegate_work_tool.py:16`）— 把子任务委派给 crew 内其它 agent
- `AskQuestionTool`（`tools/agent_tools/ask_question_tool.py:14`）— 向其它 agent 提问
- `ReadFileTool`（`tools/agent_tools/read_file_tool.py:24`）— 读 kickoff 时传入的 input files（PDF 自动抽文本，binary 走 base64）
- `AddImageTool`（`tools/agent_tools/add_image_tool.py:16`）— 把图片注入上下文（用 `VISION_IMAGE:<media>:<b64>` sentinel）
- `RecallMemoryTool` / `RememberTool`（`tools/memory_tools.py:30/73`）— 长期记忆读写
- `CacheTools`（`tools/cache_tools/cache_tools.py:8`）— 工具结果缓存查询（`Hit Cache`）

外置工具包 `crewai-tools`（独立子仓库）提供 100+ 第三方工具（SerperDevTool / FileReadTool / BrowserbaseTool / CodeInterpreterTool 等），通过 `module:ClassName` 字符串引用（`json_loader.py:1880` `lookup_crewai_tool_class`）。

**MCP 支持**：✅ **完整支持**，三档入口：
- 原生核心：`crewai/mcp/client.py:50` `MCPClient` + `tool_resolver.py:35` `MCPToolResolver`，支持 **stdio / HTTP(streamable) / SSE** 三种 transport（`transports/stdio.py`、`http.py`、`sse.py`）
- 配置：`MCPServerStdio` / `MCPServerHTTP` / `MCPServerSSE` 三个 Pydantic 模型（`mcp/config.py:20-110`）
- 外置：`crewai-tools.MCPServerAdapter`（`crew_base.py:324`）— 旧版入口
- 引用方式：支持 **HTTPS URL**（`mcp.tool_resolver.py:225`）、**AMP 引用**（`notion` / `notion#search`，`tool_resolver.py:139`）、**原生 config 对象**（`tool_resolver.py:101`）
- **Tool filter**（`mcp/filters.py`）：静态 allow/block list（`StaticToolFilter`）和动态 context-aware（`ToolFilterContext` 注入 agent、server、run_context）

**Agent Skills 支持**：✅ **完整实现 Anthropic Agent Skills 标准**（`crewai/skills/`）：
- 三级 progressive disclosure：`METADATA=1` / `INSTRUCTIONS=2` / `RESOURCES=3`（`skills/models.py:24-46`）
- 目录结构：`<skills_dir>/<skill_name>/SKILL.md` + 可选 `scripts/` / `references/` / `assets/`（`skills/parser.py:30-150`）
- 加载：扫描目录 → 解析 YAML frontmatter → 按需 `activate_skill()` 提升到 INSTRUCTIONS 级
- 注入格式：用 `<skill name="...">...</skill>` XML 标签（`skills/loader.py:format_skill_context`）
- frontmatter 字段：`name` / `description` / `license` / `compatibility` / `metadata` / `allowed-tools`（`skills/models.py:50-100`）

**其他工具类型**：
- `BaseTool` 装饰器（`tools/base_tool.py:500+` `@tool`）— 任意 Python 函数 + docstring + type hints 一行变工具
- `from_langchain`（`base_tool.py:380`）— LangChain 工具适配
- `LLMTool` / 自定义 `StructuredTool` 等

### Q2. 工具列表的生成、传递、格式

**生成方式**：
- 核心函数 `setup_native_tools()`（`utilities/agent_utils.py:1321`）→ `convert_tools_to_openai_schema()` 把 `list[BaseTool]` 转成 OpenAI 协议 JSON
- 工具来源三路汇合（`step_executor.py:88-93`）：`original_tools`（BaseTool 实例）+ MCP 工具（`MCPToolResolver.resolve()`）+ Skills（prompt 注入，不进 tools 列表）
- MCP 工具在 Agent 启动时通过 `_resolve_native()`（`tool_resolver.py:280`）懒连接 → 列出 tools → 转 `MCPNativeTool` → 加入到 original_tools 列表

**传递方式**：
- 通过 `BaseLLM.call(messages, tools=self._openai_tools, ...)` 传递（`step_executor.py:447`）
- 同一份 `tools` 列表会被 **Provider 适配层自动转换**：
  - **OpenAI / OpenAI-Compat / Ollama / vLLM** → 原样 `tools=[…]`
  - **Anthropic** → `_prepare_completion_params`（`completion.py:421`）转 `{"name": ..., "description": ..., "input_schema": ...}` 三段式
  - **Gemini** → 通过 `raw_tool_call_parts` 保留 raw parts 适配 Gemini 协议（`agent_utils.py:1371`）

**格式（JSON 片段）**：
```json
[
  {
    "type": "function",
    "function": {
      "name": "Delegate work to coworker",
      "description": "Useful to delegate a specific task...",
      "parameters": {
        "type": "object",
        "properties": {"task": {...}, "coworker": {...}, "context": {...}},
        "required": ["task", "coworker"]
      }
    }
  }
]
```
（来源：`BaseTool.to_structured_tool()` → `CrewStructuredTool.args_schema.model_json_schema()`，`tools/structured_tool.py:185`）

**是否 prompt-as-tool**：❌ **不是**。CrewAI 走纯 function calling；text-parsed 模式是"fallback"路径（当 LLM 不支持 native tool calling 时降级），不是首选。fallback 时用 ReAct 格式（Thought/Action/Action Input）作为 prompt 里的"伪工具协议"（`agents/parser.py:60-86`）。

**动态刷新**：✅ **支持**。MCP 每次 tool invocation 都用 `client_factory()` 创建全新 `MCPClient` + transport（`mcp_native_tool.py:127-135`），避免 shared state 导致并发 cancel-scope 错误。Skill `activate_skill()` 可运行时提升 disclosure level（`skills/loader.py:107`）。

### Q3. 工具调用指令的解析、错误修复、准确性

**解析方式**（双模式）：
- **Native mode**（LLM 支持 function calling 时）：
  - OpenAI：`tool_calls` 数组直接读（`build_tool_calls_assistant_message`，`agent_utils.py:1339`）
  - Anthropic 流式：监听 `content_block_start`（`tool_use` block）+ `content_block_delta`（`input_json_delta`）增量累加 partial_json（`completion.py:1093-1140`）
  - 增量解析关键代码（`completion.py:1121-1125`）：
    ```python
    if event.delta.type == "input_json_delta":
        block_index = event.index
        partial_json = event.delta.partial_json
        if block_index in current_tool_calls and partial_json:
            current_tool_calls[block_index]["arguments"] += partial_json
    ```
- **Text-parsed mode**（fallback）：ReAct 格式 regex 解析（`agents/parser.py:60` `parse()`）
  - 三种格式：`Action: search\nAction Input: ...` → `AgentAction`；`Final Answer: ...` → `AgentFinish`；缺字段抛 `OutputParserError`

**错误修复机制**（`tools/tool_usage.py:540-595` `_validate_tool_input`）：
1. 先 `json.loads` 试严格 JSON
2. 失败 → `ast.literal_eval` 试 Python literal
3. 失败 → `json5.loads` 试 JSON5
4. 失败 → `json_repair.repair_json(skip_json_loads=True)` 修复后重试
5. 全部失败 → 抛 `ToolValidateInputErrorEvent` + 让 LLM 看到 "Failed to parse JSON" 错误

工具名容错：`SequenceMatcher` 模糊匹配（`_select_tool`，`tool_usage.py:580`），相似度 > 0.85 即可命中。

**准确性保证**：
- **Pydantic schema 校验**：`BaseTool._validate_kwargs`（`base_tool.py:230`）每次 invoke 跑 `args_schema.model_validate()`，失败抛 `ValueError` 并附 `build_schema_hint`（`structured_tool.py:160`）显示期望字段
- **重试**：`ToolUsage._max_parsing_attempts = 3`（默认）/ `2`（OpenAI big models，`tool_usage.py:81-90`）
- **重复调用防护**：`_check_tool_repeated_usage`（`tool_usage.py:570`）同一 tool+args 连续触发直接终止
- **max_usage_count**：`BaseTool._claim_usage`（`base_tool.py:250`）原子锁 + thread-safe 计数，达上限拒绝
- **Tool 选择错误事件**：`ToolSelectionErrorEvent` 发出"Action don't exist, these are the only available Actions"提示

### Q4. 工具执行结果回传

**回传方式**（双协议，Provider 适配）：
- **OpenAI 协议**：assistant message + 多个 `role: tool` message，每个带 `tool_call_id` 对应前一轮 `tool_calls[i].id`（`agent_utils.py:1339-1410`）
- **Anthropic 协议**：assistant content blocks 包含 `tool_use` + 后续 user message 包含 `tool_result` blocks，每个带 `tool_use_id`（`completion.py:1262-1268`）
- **Text 模式**：append `{"role": "user", "content": "Observation: {tool_result}"}`（`step_executor.py:_build_observation_message`）

**格式**：默认 `str(result)`，若工具定义了 `result_schema`（Pydantic）则用 `model_dump_json()` 序列化（`tools/structured_tool.py:50-75` `_format_tool_output_for_agent`）。

**协议适配代码**（Anthropic 结果组装，`completion.py:1262`）：
```python
tool_result = {
    "type": "tool_result",
    "tool_use_id": tool_use.id,
    "content": str(result) if result is not None else "Tool execution completed",
}
```

**大结果处理**：
- **未发现显式截断**（与 Cline/Aider 不同），但 base_llm 提供 `stop` / `max_tokens` 控制
- **图片专门走 sentinel 通道**：`VISION_IMAGE:<media>:<b64>`（`step_executor.py:331`）→ 转 Anthropic `image_url` block 或 OpenAI `image_url` data URI，**避免 base64 污染文本**
- Anthropic `tool_result` 支持内嵌 `image` block（`completion.py:733-738`）
- `result_as_answer` 标志（`base_tool.py:148`）— 工具结果直接作为最终答案，截断后续 loop

### Q5. File Backend 是否为工具调用做了适配

**关键发现 — `base_directory` 自动绑定**：
- `@CrewBase` 元类（`project/crew_base.py:193-200` `CrewBaseMeta`）在类创建时调 `_set_base_directory`（`crew_base.py:135-144`）：
  ```python
  cls.base_directory = Path(inspect.getfile(cls)).parent  # Crew 类所在目录
  ```
- 所有 config 路径都基于 `base_directory` 解析（`crew_base.py:351` `full_path = self.base_directory / config_path`），tools.yaml / agents.yaml / tasks.yaml 都用相对路径
- `_set_mcp_params` + `get_mcp_tools`（`crew_base.py:159` / `290`）允许在 `@CrewBase` 子类里声明 `mcp_server_params`，adapter 自动 lazy 启动

**其他工具配置目录**：
- 凭证独立：`tool_credentials.py`（`crewai-core/src/crewai_core/`）— 工具 API key 单独管理
- 缓存：`agents/cache/cache_handler.py` + `tools/cache_tools/cache_tools.py` — SQLite 工具结果缓存
- 工作区结构（项目级）：`<project>/<base_directory>/{agents.yaml, tasks.yaml, tools/}`
- 全局（`~/.crewai/`，由 `appdirs.user_data_dir`）：
  - `memory/` — 长期记忆存储
  - `knowledge/` — RAG 知识库
  - `.checkpoints/` — crew flow 检查点
  - `logs/` — 日志
  - `output/` — `Task.output_file` 写入位置（path traversal 防护：禁 `.. ~ $ | > < & ;`）

**加载代码**：
- `@CrewBase` 启动时（`crew_base.py:770-775`）→ `_set_base_directory` → `_set_config_paths` → `_set_mcp_params` 顺序执行
- Agent 启动 → `MCPToolResolver.resolve(agent.mcps)` 懒连接 MCP server + 拉 tools

**全局 vs 项目级**：
- **项目级**：`@CrewBase.base_directory`（自动绑定到 crew 类文件所在目录），用于 YAML config + MCP server params
- **全局级**：`~/.crewai/`（memory、knowledge、output、logs、checkpoints）— 用 `appdirs` 跨平台

**与 `standard/file_backend.md` 对照**：
- §1.1 用户属主目录 ✅：`appdirs` 跨平台 + `~/.crewai/`
- §1.4 secrets 独立文件 ✅：`tool_credentials.py` 独立模块
- §3.4 强结构化 ✅：`memory/ + knowledge/ + .checkpoints/ + logs/ + output/ + flow_states/ + base_directory/`
- §8.3 atomic write / path traversal 防护 ✅：output_file 禁 `.. ~ $ | > < & ;`
- §10.8 MCP 支持 ✅：原生 MCP client + tool filter
- ⚠️ **不完整**：help 字符串与代码脱节（如 `crewai memory --storage-path` 文档说走 `~/.crewai/memory` 但实际走 `appdirs.user_data_dir`），属 file_backend 标准中明确点名的"反例"特征

## 3. 关键代码片段

**片段 1 — MCP 工具解析（`mcp/tool_resolver.py:280-320`）**：原生 MCP config 转 CrewAI BaseTool
```python
def _resolve_native(self, mcp_config):
    discovery_transport, server_name = self._create_transport(mcp_config)
    discovery_client = MCPClient(transport=discovery_transport, ...)
    # asyncio.run() 拉 tools_list → 过滤 → 每个 tool 包成 MCPNativeTool
    for tool_def in tools_list:
        args_schema = self._json_schema_to_pydantic(tool_name, tool_def["inputSchema"])
        native_tool = MCPNativeTool(
            client_factory=_client_factory,  # 每次调用创建新 client
            tool_name=tool_name, ...
        )
```

**片段 2 — Anthropic 流式 tool_use 解析（`llms/providers/anthropic/completion.py:1120-1140`）**：
```python
elif event.type == "content_block_delta":
    if event.delta.type == "input_json_delta":
        block_index = event.index
        partial_json = event.delta.partial_json
        if block_index in current_tool_calls and partial_json:
            current_tool_calls[block_index]["arguments"] += partial_json
```

**片段 3 — 工具调用 JSON 解析多层 fallback（`tools/tool_usage.py:540-595`）**：
```python
try:    arguments = json.loads(tool_input)
except (JSONDecodeError, TypeError): pass
try:    arguments = ast.literal_eval(tool_input)
except (ValueError, SyntaxError): repaired_input = repair_json(tool_input)
try:    arguments = json5.loads(tool_input)
except: pass
try:    repaired_input = repair_json(tool_input, skip_json_loads=True)
        arguments = json.loads(repaired_input)
except: raise Exception("Tool input must be a valid dictionary...")
```

**片段 4 — Skill progressive disclosure（`skills/loader.py:format_skill_context`）**：
```python
if skill.disclosure_level >= INSTRUCTIONS and skill.instructions:
    parts = [f'<skill name="{skill.name}">', skill.description, "", skill.instructions, ...]
return f'<skill name="{skill.name}">\n{skill.description}\n</skill>'
```

**片段 5 — `@CrewBase` 自动绑定 base_directory（`project/crew_base.py:135-144`）**：
```python
def _set_base_directory(cls):
    try:    cls.base_directory = Path(inspect.getfile(cls)).parent
    except (TypeError, OSError): cls.base_directory = Path.cwd()
```

## 4. 与 Onion Agent 设计的关联

1. **Onion 应学 — `client_factory` 每次新建 MCP client 模式**（`mcp_native_tool.py:127`）：CrewAI 验证了"每次 invoke 独立 client/transport"是支持并发调用的关键（避免 anyio cancel-scope 错误）。Onion 的 MCP channel 应照搬，不要做"长连接池"假设。

2. **Onion 应学 — `@CrewBase` 风格的目录自动绑定**：用 `inspect.getfile(cls).parent` 把"项目根"绑到类所在文件，是**零配置工作区**的优雅实现。Onion 可以做 `@OnionAgent base_directory = Path(__file__).parent` 让用户写 `tools/foo.py` 就能被自动发现。

3. **Onion 应学 — Skills progressive disclosure + XML 标签注入**（`skills/loader.py`）：`<skill name="...">` 包装的 prompt 注入是稳定的（cache anchor 友好），Onion 的 skills 工具可以照搬这个格式。

4. **Onion 应避免 — ToolUsage 巨类反例**（`tools/tool_usage.py` 1000+ 行）：把 schema 校验、JSON 修复、缓存、telemetry、retry 全部塞一个类。Onion 应按 Tool Channel 设计哲学拆成"Tool shell"层（每类工具一个客户端）+ 真正统一的"Tool channel"。

5. **Onion 应避免 — help 与代码脱节**（file_backend 标准明确点名）：CrewAI 的 `crewai memory --storage-path` 文档说走 `~/.crewai/memory` 实际走 `appdirs.user_data_dir`，这是 20 个项目里 4 个典型反例之一。Onion 严格遵循"help 字符串必须和代码 100% 一致"。

## 5. 不确定 / 未找到

- **大结果截断策略**未在源码中显式发现（base_llm 提供 `stop` / `max_tokens` 但 tool result 这层无截断）—— 推测依赖 LLM provider 自身的 input 长度限制
- **tool_calls 流式解析（OpenAI delta.tool_calls 增量）** 在源码里**没有显式找到**（grep "delta" 未匹配），可能 LiteLLM / OpenAI SDK 已封装；只确认了 Anthropic 的 `input_json_delta` 处理
- **MCP `cache_tools_list=True` 的实际使用** 在 `tool_resolver.py:185` 定义但**未在 `_resolve_native` 主路径启用**（只有 `_resolve_external` HTTPS 路径用了），存在代码不一致
- **Agent Skills 的 skill 文件发现目录**（`search_path`）**未在源码找到全局默认路径**—— 推测依赖 agent/crew 显式传入，但缺少文档
- **`@CrewBase` MCP params** 是 `mcp_server_params` 单一字段，但 `MCPToolResolver` 支持多 server；推测实际用法是 dict-style 但源码未明示
