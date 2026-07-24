# tool_channel 设计

> **项目**:Onion Agent —— 基于洋葱架构的 ReAct 智能体
> **模块**:`src/infrastructure/tool_channel/`(L5 - Infrastructure / tool_channel)
> **姊妹文档**:
> - 设计哲学:`harness/02_project_manager/project_manager.md` §洋葱架构 L5 §5
> - 行业标准:`harness/01_market_research/standard/tool_channel.md`
> - FC 准确率:`harness/01_market_research/tool_accuracy.md`
> - 工作区:`harness/01_market_research/standard/file_backend.md` + `harness/03_SRS/infrastructure/file_backend/prompt.md`
> **依赖模块**(已实现):
> - `src/infrastructure/buildin_tools/`(file_system / command_line / non_head_browser,各自暴露 `TOOL_SCHEMAS` + `TOOL_HANDLERS`)
> - `src/infrastructure/tool_shell/buildin_client.py`(同进程工具统一调用入口)
> - `src/infrastructure/tool_shell/mcp_client.py`(MCP 协议 stdio/sse/streamable_http)
> - `src/infrastructure/tool_shell/agent_skills_client.py`(Agent Skills 渐进式披露 L1/L2/L3)
> **版本**:v1.0 / 2026-07-24

---

## 0. 文档结构

按"为什么 → 是什么 → 怎么用 → 怎么落地"组织:

1. 目标与边界
2. 设计原则(5 条,全部映射到行业标准)
3. 整体架构
4. 核心概念:Tag 标签系统(4 类)
5. 工具命名规范
6. **Input Schema**(给大模型看)
7. **Input Handler**(给工具传参)
8. `tool_list.py` 详细设计
9. `tool_router.py` 详细设计
10. Skill 的特殊处理(因为它不是函数调用)
11. 错误处理与质量防线(7 层兜底)
12. 持久化:工具列表写入 `tools.jsonl`
13. 协议中立:OpenAI / Anthropic 适配点
14. CLI(所见即所得)
15. P0/P1/P2 优先级
16. 行业标准映射清单

---

## 1. 目标与边界

### 1.1 一句话目标

把 `tool_shell` 三大 client(buildin / mcp / skills)暴露的工具**合并为一份 OpenAI Chat Completions 风格**的 `tools` 参数,让大模型通过原生 function calling 通道使用;并把大模型返回的 `tool_calls` 解析、修复、路由回对应 client。

### 1.2 不做什么

- **不做 LLM 调用本身**——那是 L4 `openai_tool_engine.py` 的事,本模块只产出/消费 `tools` 列表和 `tool_calls` 消息
- **不做工具执行权限审批**——那是 L3 SDK + `approval_mode` 的事(参考 `standard/agent_loop.md` §Q6/Q7)
- **不做工具结果截断/持久化**——每个 client 自己负责(参考 `buildin_client._truncate_middle` 等)
- **不做工具自动发现/扫描**——每个 client 自己负责,tool_channel 只负责"汇总"
- **不做 skill 的语义匹配/embedding 检索**——skill 已经走 Anthropic progressive disclosure 范式(LLM 看 L1 description 自行判断),不引入 RAG

### 1.3 模块边界

```
┌────────────────────────────────────────────────────────────────────────┐
│  L4 Openai Engine  (openai_tool_engine.py)                            │
│     接收 messages + tools → 调 openai SDK → 返回 assistant + tool_calls│
└──────────────────────────────┬─────────────────────────────────────────┘
                               │  tools=[...]   ↑ tool_calls=[{...}]
                               ▼
┌────────────────────────────────────────────────────────────────────────┐
│  L5 Tool Channel   ← 本模块                                            │
│  ┌──────────────────┐    ┌──────────────────┐                          │
│  │   tool_list.py   │    │  tool_router.py  │                          │
│  │   汇总 + 排序    │    │  解析 + 修复 + 路由│                          │
│  └────────┬─────────┘    └─────────┬────────┘                          │
│           │ to_openai_schema()     │ call_tool()                      │
└───────────┼────────────────────────┼──────────────────────────────────┘
            ▼                        ▼
┌─────────────────────┐  ┌─────────────────────┐  ┌──────────────────┐
│  L5 Tool Shell      │  │  L5 Tool Shell      │  │  L5 Tool Shell   │
│  buildin_client.py  │  │  mcp_client.py      │  │  agent_skills_   │
│                     │  │                     │  │  client.py       │
└──────────┬──────────┘  └──────────┬──────────┘  └─────────┬────────┘
           ▼                        ▼                       ▼
   ┌──────────────┐         ┌──────────────┐          ┌──────────────┐
   │ buildin_tools│         │ MCP Server   │          │ skills/*/    │
   │ file_system  │         │ stdio / sse  │          │ SKILL.md     │
   │ command_line │         │ streamable_  │          │ references/  │
   │ non_head_    │         │ http         │          │ scripts/     │
   │ browser      │         └──────────────┘          └──────────────┘
   └──────────────┘
```

---

## 2. 设计原则(5 条,全部映射到行业标准)

| # | 原则 | 行业标准 | 落地策略 |
|---|------|---------|---------|
| **P1** | **协议中立 + Provider 热插拔** | §1.1(13/20) | 内部统一用 OpenAI Chat Completions 风格 `Tool[]`;Anthropic 写一个 `to_anthropic_tools()` adapter 翻译;`Ollama/GLM/Qwen` 走 OpenAI 兼容层 |
| **P2** | **统一抽象 + 集中注册** | §1.2(15/20) + §4.4 | 定义 `ToolEntry` 抽象;`tool_list.ToolRegistry` 单例;三类 client 通过 `register(tag, client)` 注入;`tool_router` 拿同一份 registry 路由 |
| **P3** | **声明式注册 + 自动发现** | §1.3(20/20) | 每个 client 自己负责"扫描"和"注册 schema";tool_channel 只"汇总",不"实现" |
| **P4** | **质量第一 + 7 层兜底** | tool_accuracy §四 + §5.1-5.12 | `json.loads` → `json-repair` → `jsonschema` 校验 → tag 路由 → client 异常捕获 → `is_error=True` 回灌 → `max_retries` 限次 |
| **P5** | **所见即所得 + CLI 化** | project_manager.md §所见即所得 | 每个函数都能命令行跑;产品经理能直接 `python tool_list.py` 看 `tools.jsonl` 内容;`python tool_router.py` 模拟一次 LLM 调用 |

> 编号与 `project_manager.md` §洋葱架构 L5 §5 完全对齐:tool_shell 负责"产出工具",tool_channel 负责"汇总+路由"。

---

## 3. 整体架构

### 3.1 数据流(单次 Agent Loop 一圈)

```
       ┌──────────────┐
       │  L4 Engine   │
       └──────┬───────┘
              │  ① build_tools_payload()
              │     ├─ tool_list.collect_tools()        # 三类 client 各自报
              │     ├─ tool_list.sort_by_name()         # 排序保 cache hit
              │     └─ tool_list.assign_tool_call_ids() # 准备 router
              │  ② chat.completions.create(tools=payload, messages=...)
              │
              │  ③ response.tool_calls
              │     [{id, type:"function", function:{name, arguments:str}}]
              ▼
       ┌──────────────┐
       │  L5 Router   │
       └──────┬───────┘
              │  ④ tool_router.dispatch_one(call)
              │     ├─ parse_name()           → (tag, scope, tool)
              │     ├─ parse_arguments()      → (args, error)   # 7 层兜底
              │     ├─ validate_arguments()   → (ok, error)     # JSON Schema
              │     ├─ route_to_client()      → (result, error) # tag → client
              │     └─ format_tool_result()   → {success, content, is_error, ...}
              │
              │  ⑤ tool_router.dispatch_many(calls) → [result_1, result_2, ...]
              │     (并行:asyncio.gather / 串行:顺序)
              │
              │  ⑥ role:"tool" messages 写回 history(messages.append)
              │
              │  回到 ②,直到 model 返回空 tool_calls = 任务完成
              ▼
```

### 3.2 关键不变量(贯穿整个 tool_channel)

1. **单一工具命名空间**——任何工具的 `function.name` 在 `tools` 数组中**全局唯一**;`onion.<tag>.<scope>.<tool>` 三段保证
2. **tool_call_id 精确对应**——assistant 消息的 `tool_calls[i].id` ↔ tool 消息的 `tool_call_id` 一一对应(§6.1 必做)
3. **错误不静默**——任何解析/校验/执行异常,统一转 `is_error=True` 的 `role:"tool"` 消息,让 LLM 自我修正(§5.3 / §6.4)
4. **schema 排序稳定**——每次返回的 `tools` 列表按 `function.name` 字母排序(§4.5,保 OpenAI prompt cache hit)
5. **Client 失败不互踩**——一个 MCP server 挂掉,不能导致整个 tool list 为空(§5.10)

---

## 4. 核心概念:Tag 标签系统(4 类)

### 4.1 4 个 Tag 枚举

| Tag | 含义 | 工具来源 | 路由 client | 函数名格式 | 调用方式 | P0/P1 |
|---|---|---|---|---|---|---|
| **`buildin`** | 同进程内置工具包 | `src/infrastructure/buildin_tools/*.py` | `BuildinClient` | `onion.buildin.<toolkit>.<tool>` | 同步(直接调 Python 函数) | **P0** |
| **`mcp`** | MCP Server(远程 / 进程) | `mcp_servers.json` 配置 | `MCPClient` | `onion.mcp.<server>.<tool>` | 异步(MCP JSON-RPC),router 包装成同步语义 | **P0** |
| **`skill`** | Agent Skills(progressive disclosure) | `skills/<slug>/SKILL.md` | `AgentSkillsClient` | `onion.skill.<skill-slug>` | **非函数调用**——加载 L2 提示词注入上下文(见 §10) | **P0** |
| **`agent`** | Agent Loop 工具 | 待开发:`update_plan` / `finish_loop` / `record_memory` / `ask_user` | TBD(后续在 tool_shell 增 `agent_client.py`) | `onion.agent.<tool>` | 同步 | **P1** |

> 选择 "函数名前缀化" 而不是 "schema 中加 tag 字段",**核心原因**:
> 1. OpenAI strict mode 对未知字段容忍度低,加 `tag` 字段可能触发 schema 校验告警
> 2. 函数名前缀**对 LLM 完全透明**——LLM 看到的 name 包含完整路由信息(可以用 prompt 引导它选 `onion.mcp.searxng.search` 而不是 `search`)
> 3. 跨 Provider 稳定(Anthropic / Gemini / Ollama 都识别 `function.name`,不识别自定义字段)
> 4. 解析零歧义:`name.split(".")` 三段切分,正则一行搞定
> 5. 与现有 `server.tool` / `toolkit.tool` 命名自然衔接——只是在前面加了个 `onion.tag.` 防止重名

### 4.2 标签解析正则

```python
import re

# 函数名必须符合:onion.<tag>.<scope>.<tool>
# tag: buildin / mcp / skill / agent
# scope: 小写字母/数字/下划线(MCP server / buildin toolkit / skill slug)
# tool: 小写字母/数字/下划线
TOOL_NAME_PATTERN = re.compile(
    r"^onion\."
    r"(?P<tag>buildin|mcp|skill|agent)\."
    r"(?P<scope>[a-z0-9_][a-z0-9_-]{0,63})\."
    r"(?P<tool>[a-z0-9_][a-z0-9_-]{0,127})$"
)
```

**scope 命名**:
- buildin:toolkit 名(如 `file_system` / `command_line` / `non_head_browser`)
- mcp:MCP server 配置名(如 `searxng` / `filesystem` / `github`)
- skill:skill slug(如 `pdf-processing` / `mcp-builder`)

**tool 命名**:
- 与 client 内 `TOOL_SCHEMAS` 中 `function.name` 完全一致
- 不允许 `.`(避免解析歧义)
- 不允许大写(避免 case-insensitive 反复;§4.6 工具名规范化)

### 4.3 命名示例(必看,后续 router 路由的依据)

| 原始 client 中的 `function.name` | 注入 tool_channel 后给 LLM 看的 `function.name` |
|----------------------------------|------------------------------------------------|
| `file_system.read_file`          | `onion.buildin.file_system.read_file`          |
| `command_line.run_command`       | `onion.buildin.command_line.run_command`       |
| `non_head_browser.web_search`    | `onion.buildin.non_head_browser.web_search`    |
| `searxng_web_search`             | `onion.mcp.searxng.searxng_web_search`         |
| `github.create_issue`            | `onion.mcp.github.create_issue`                |
| `pdf-processing`                 | `onion.skill.pdf-processing`                   |
| `mcp-builder`                    | `onion.skill.mcp-builder`                      |
| _(预留)_                         | `onion.agent.update_plan`                      |
| _(预留)_                         | `onion.agent.finish_loop`                      |

---

## 5. 工具命名规范(给所有 client 的"硬性契约")

为了让 tool_channel 工作,三个 client **必须**遵守的命名契约——这是写进 `tool_channel` 的硬性要求,后续如果新增 client 也必须遵守:

### 5.1 BuildinClient 输出契约

```python
# 在 BuildinClient._load_one_toolkit / BuildinTool.to_openai_dict 中
# 已实现:full_name = "<toolkit>.<tool>" → tool_channel 注入前缀 "onion.buildin."
# 不需要改 buildin_client.py 任何代码
```

### 5.2 MCPClient 输出契约

```python
# MCPClient.list_tools() / _format_tools() 返回:
#   {"searxng": [{"name": "searxng_web_search", ...}, ...], ...}
# tool_channel 在收集时注入前缀 "onion.mcp.<server>."
# 不需要改 mcp_client.py 任何代码
```

### 5.3 AgentSkillsClient 输出契约

```python
# 关键: skill 不是"函数",但要让 LLM 看到它可"调用"
# 注入一个虚拟 schema: function.name = "onion.skill.<slug>"
# function.description = "<skill description from L1>"
# function.parameters = {} (空 schema,无参数)
# router 收到这个虚拟 call → 走 skill 特殊路径(§10)
```

### 5.4 名称规范化(防 LLM 幻觉)

参照 `standard/tool_channel.md §4.6`:
- LLM 返回的 `name` 先 `name.lower()` 再匹配
- 用 `TOOL_NAME_PATTERN` 校验格式,不通过就 `is_error=True` 回灌
- `tool_call_id` 为空时(某些 provider 漏给),用 `MD5(function_name + arguments)[:12]` 兜底(§5.11)

---

## 6. Input Schema(给大模型看)

### 6.1 OpenAI Chat Completions 风格(标准)

```json
{
  "type": "function",
  "function": {
    "name": "onion.buildin.file_system.read_file",
    "description": "读取本地文件内容(文本文件)。返回文件内容字符串(UTF-8)。当需要查看源代码、配置文件、日志等文本内容时调用。",
    "parameters": {
      "type": "object",
      "properties": {
        "path": {
          "type": "string",
          "description": "文件的绝对路径,如 C:\\workspace\\README.md"
        },
        "start_line": {
          "type": "integer",
          "description": "起始行(1-indexed,默认 1)",
          "default": 1
        },
        "end_line": {
          "type": "integer",
          "description": "结束行(包含,可选)"
        }
      },
      "required": ["path"],
      "additionalProperties": false
    },
    "strict": true
  }
}
```

**关键点**:
- `type: "function"`(OpenAI 必填,Anthropic adapter 去掉)
- `function.name` 三段式 `onion.<tag>.<scope>.<tool>`,**全局唯一**
- `function.description` 写清"做什么 + 返回什么 + 何时调用"——这是 LLM 选工具的唯一依据
- `function.parameters` 严格 JSON Schema
  - `type: "object"`
  - `required: [...]` 准确(provider 用约束解码强制)
  - `additionalProperties: false`(§3.3 必做,防 LLM 给 schema 外字段)
  - 每个 `property` 都有 `description`(LLM 才知道怎么填)
- `function.strict: true`(OpenAI 2024 新增,server 侧再校验一次,降低参数幻觉)

### 6.2 Skill 的"伪 schema"(给 LLM 看,告诉它可以加载)

```json
{
  "type": "function",
  "function": {
    "name": "onion.skill.pdf-processing",
    "description": "加载 PDF 处理技能。激活后,智能体将获得 PDF 文本提取/表单填写/合并文件的完整指令。触发时机:用户提到 PDF、表单、文档提取、PDF 合并等场景。无需任何参数——调用即激活。",
    "parameters": {
      "type": "object",
      "properties": {},
      "required": [],
      "additionalProperties": false
    },
    "strict": true
  }
}
```

**特点**:
- `parameters` 为空对象(`required: []`)
- `description` 强调"激活后获得什么 + 触发时机"——L1 提示词的角色
- router 收到此 call → 不传任何参数,直接读 SKILL.md 的 L2 正文,以 `role:"tool"` 回传

### 6.3 工具列表的最终形态(传给 OpenAI)

```python
# 由 tool_list.collect_tools() 产出
tools = [
    {"type": "function", "function": {"name": "onion.buildin.command_line.run_command", ...}},
    {"type": "function", "function": {"name": "onion.buildin.file_system.read_file", ...}},
    ...
    {"type": "function", "function": {"name": "onion.mcp.searxng.searxng_web_search", ...}},
    ...
    {"type": "function", "function": {"name": "onion.skill.pdf-processing", ...}},
]

# 已按 function.name 排序(§4.5 强烈建议)
# 任何 schema 校验失败的 client(§5.10 unreadable tool 隔离)被静默跳过,不进 list
```

---

## 7. Input Handler(给工具传参)

### 7.1 输入:大模型返回的 `tool_calls`

```json
{
  "role": "assistant",
  "content": null,
  "tool_calls": [
    {
      "id": "call_abc123",
      "type": "function",
      "function": {
        "name": "onion.buildin.file_system.read_file",
        "arguments": "{\"path\": \"C:\\\\workspace\\\\README.md\"}"
      }
    },
    {
      "id": "call_def456",
      "type": "function",
      "function": {
        "name": "onion.mcp.searxng.searxng_web_search",
        "arguments": "{\"query\": \"MCP protocol\"}"
      }
    }
  ]
}
```

**注意**:`function.arguments` 是 **JSON 字符串**,**不是** dict——必须 `json.loads`(§5.1 行业标准)。

### 7.2 处理流程(7 步)

```python
def dispatch_one(tool_call: dict) -> dict:
    """
    Input Handler:把一个 tool_call 路由到对应 client 并执行。
    
    返回统一格式(给 L4 Engine 写回 role:"tool" 消息用):
    {
        "tool_call_id": str,
        "name": str,             # 原始 name,echo 给 LLM
        "success": bool,
        "is_error": bool,
        "content": str,          # 给 LLM 看的文本
        "error": Optional[str],  # 给人/日志看
        "data": {                # 给程序用
            "tag": str,
            "scope": str,
            "tool": str,
            "arguments": dict,
            "duration_ms": int,
            "raw_result": Any,
        }
    }
    """
    call_id = tool_call.get("id") or _fallback_tool_call_id(tool_call)  # §5.11
    name = tool_call.get("function", {}).get("name", "")
    raw_args = tool_call.get("function", {}).get("arguments", "{}")
    
    # Step 1: 解析 name
    parsed_name = parse_tool_name(name)
    if parsed_name is None:
        return _err_result(call_id, name, "Invalid tool name format. Expected onion.<tag>.<scope>.<tool>")
    tag, scope, tool = parsed_name
    
    # Step 2: 解析 arguments(JSON 字符串 → dict,7 层兜底)
    args, parse_err = parse_arguments(raw_args)
    if parse_err:
        return _err_result(call_id, name, f"Argument parse failed: {parse_err}", tag=tag, scope=scope, tool=tool)
    
    # Step 3: 查 schema 校验参数(防 LLM 幻觉字段)
    schema = _lookup_schema(tag, scope, tool)
    if schema is None:
        return _err_result(call_id, name, f"Unknown tool: {name}", tag=tag, scope=scope, tool=tool)
    validation_err = validate_arguments(args, schema)
    if validation_err:
        return _err_result(call_id, name, f"Argument schema validation failed: {validation_err}", tag=tag, scope=scope, tool=tool)
    
    # Step 4: 按 tag 路由
    if tag == "skill":
        # Skill 走特殊路径(§10)
        return _dispatch_skill(call_id, scope, tool, name)
    
    # Step 5: buildin / mcp / agent 调对应 client
    client = _registry.get_client(tag)
    if client is None:
        return _err_result(call_id, name, f"No client registered for tag: {tag}", tag=tag, scope=scope, tool=tool)
    
    # Step 6: 执行(捕获所有异常)
    start = time.time()
    try:
        spec = f"{scope}.{tool}"  # client 用 'scope.tool' 形式
        if tag == "mcp":
            # mcp 是 async,需要在 sync wrapper 里跑
            result = asyncio.run(client.call_tool(spec, args))
        else:
            result = client.call_tool(spec, args)
    except Exception as e:
        duration_ms = int((time.time() - start) * 1000)
        return _err_result(call_id, name, f"Tool execution failed: {type(e).__name__}: {e}",
                            tag=tag, scope=scope, tool=tool, arguments=args, duration_ms=duration_ms)
    
    duration_ms = int((time.time() - start) * 1000)
    
    # Step 7: 统一格式化输出
    return _format_result(call_id, name, result, tag, scope, tool, args, duration_ms)
```

### 7.3 多 tool_call 并行处理

```python
def dispatch_many(tool_calls: list[dict], parallel: bool = True) -> list[dict]:
    """
    Input Handler(批量):并行执行多个 tool_call。
    
    Args:
        tool_calls: assistant message 中的 tool_calls 列表
        parallel: True(默认)= asyncio.gather 并行,False = 顺序
    
    Returns:
        结果列表,**顺序与 tool_calls 严格一致**(§5.2 流式按 id 关联,不允许乱序)
    """
    if not tool_calls:
        return []
    if not parallel or len(tool_calls) == 1:
        return [dispatch_one(tc) for tc in tool_calls]
    
    # 并行:asyncio.gather + return_exceptions=True(单条失败不影响其他)
    # 注意: openai SDK 的 tool_calls 是 sync 字段,但 mcp_client 是 async,
    # 路由层需要把 sync dispatch 包装成 async dispatch
    async def _gather():
        return await asyncio.gather(
            *(dispatch_one_async(tc) for tc in tool_calls),
            return_exceptions=True,
        )
    raw = asyncio.run(_gather())
    
    # 处理异常(被 return_exceptions 转为 BaseException)
    out = []
    for tc, r in zip(tool_calls, raw):
        if isinstance(r, BaseException):
            out.append(_err_result(tc.get("id", ""), tc.get("function", {}).get("name", ""),
                                  f"Dispatcher crashed: {r}"))
        else:
            out.append(r)
    return out
```

### 7.4 输出:写回 `role:"tool"` 消息(§6.1 必做)

```python
# L4 Engine 拿 router 结果写回 history
for r in results:
    messages.append({
        "role": "tool",
        "tool_call_id": r["tool_call_id"],
        "name": r["name"],
        "content": r["content"],  # LLM 看的文本(已被 client 截断)
    })
```

---

## 8. `tool_list.py` 详细设计

### 8.1 职责

1. **汇总**——调三个 client 的 `to_openai_schema()` / `list_tools()` / `scan_skills()`,注入 `onion.<tag>.<scope>.<tool>` 前缀
2. **排序**——按 `function.name` 字母升序(§4.5 保 prompt cache hit)
3. **隔离**——任何 client / 任何工具加载失败,**静默跳过该条**,不影响其他(§5.10)
4. **持久化**——产出 `tools.jsonl` 写到工作区(参考 `file_backend/prompt.md` 的目录结构)
5. **CLI**——`python tool_list.py` 看汇总结果

### 8.2 核心数据结构

```python
from dataclasses import dataclass, field
from typing import Callable, Optional, Any
from enum import Enum


class Tag(str, Enum):
    """4 类工具来源标签。"""
    BUILDIN = "buildin"
    MCP = "mcp"
    SKILL = "skill"
    AGENT = "agent"  # 预留


@dataclass
class ToolEntry:
    """
    工具条目:tool_channel 的统一抽象。
    
    任何来源的工具都被包装成这个类,再转 OpenAI schema。
    """
    tag: Tag                       # 来源标签
    scope: str                     # toolkit / server / skill slug
    tool: str                      # 工具短名
    full_name: str                 # onion.<tag>.<scope>.<tool>(全局唯一)
    description: str               # 给 LLM 看
    input_schema: dict             # JSON Schema (parameters 字段)
    handler: Optional[Callable] = None       # buildin/agent 用,mcp 是 async client method
    timeout: int = 60
    max_retries: int = 0
    metadata: dict = field(default_factory=dict)  # 额外元数据(server config / skill slug / 等)
    
    def to_openai_dict(self) -> dict:
        """转 OpenAI Chat Completions tool 格式。"""
        return {
            "type": "function",
            "function": {
                "name": self.full_name,
                "description": self.description,
                "parameters": self.input_schema,
                "strict": True,
            },
        }


@dataclass
class ToolRegistry:
    """
    集中式 Tool Registry(§4.4 强烈建议)。
    
    关键:必须是 class 实例,不是模块级 const(避免 reload 重复定义)
    """
    entries: dict[str, ToolEntry] = field(default_factory=dict)  # full_name -> entry
    clients: dict[Tag, Any] = field(default_factory=dict)        # tag -> client 实例
    _load_errors: list[dict] = field(default_factory=list)       # 加载失败(不致命)
    
    def register(self, entry: ToolEntry) -> None:
        """注册一个工具。full_name 重复时后者覆盖前者,记 warning。"""
        if entry.full_name in self.entries:
            self._load_errors.append({
                "type": "duplicate_tool_name",
                "full_name": entry.full_name,
                "message": f"Tool {entry.full_name} already registered, overwriting",
            })
        self.entries[entry.full_name] = entry
    
    def register_client(self, tag: Tag, client: Any) -> None:
        """注册一个 client 实例,供 router 用。"""
        self.clients[tag] = client
    
    def collect_tools(self) -> list[dict]:
        """
        汇总所有 entry → OpenAI tool 列表,按 name 排序。
        
        Returns:
            OpenAI Chat Completions 风格的 tools 数组
        """
        items = sorted(self.entries.values(), key=lambda e: e.full_name)
        return [e.to_openai_dict() for e in items]
    
    def lookup(self, full_name: str) -> Optional[ToolEntry]:
        """按 full_name 查 entry(大小写不敏感,§4.6 工具名规范化)。"""
        if full_name in self.entries:
            return self.entries[full_name]
        # case-insensitive fallback
        lower = full_name.lower()
        for k, v in self.entries.items():
            if k.lower() == lower:
                return v
        return None
    
    def status(self) -> dict:
        """健康检查输出(给 CLI 和 doctor 命令用)。"""
        return {
            "tool_count": len(self.entries),
            "by_tag": {
                tag.value: sum(1 for e in self.entries.values() if e.tag == tag)
                for tag in Tag
            },
            "load_errors": list(self._load_errors),
            "clients": {
                tag.value: type(client).__name__ if client else None
                for tag, client in self.clients.items()
            },
        }
```

### 8.3 三个收集函数(每个对应一个 client)

```python
def collect_buildin_tools(buildin_client: BuildinClient) -> list[ToolEntry]:
    """
    从 BuildinClient 收集工具,注入 onion.buildin.<toolkit>.<tool> 前缀。
    
    buildin_client.to_openai_schema() 返回的 schema 已经有 "<toolkit>.<tool>" 格式,
    我们只需把前缀 "onion.buildin." 拼到 function.name 前面。
    """
    entries = []
    for schema in buildin_client.to_openai_schema(sort=False):
        full_name = "onion.buildin." + schema["function"]["name"]
        toolkit, tool = schema["function"]["name"].split(".", 1)
        # 拿到 handler
        tool_obj = buildin_client.tools.get(f"{toolkit}.{tool}")
        entries.append(ToolEntry(
            tag=Tag.BUILDIN,
            scope=toolkit,
            tool=tool,
            full_name=full_name,
            description=schema["function"].get("description", ""),
            input_schema=schema["function"].get("parameters", {}),
            handler=tool_obj.handler if tool_obj else None,
            timeout=tool_obj.timeout if tool_obj else 60,
        ))
    return entries


async def collect_mcp_tools(mcp_client: MCPClient) -> list[ToolEntry]:
    """
    从 MCPClient 收集工具,注入 onion.mcp.<server>.<tool> 前缀。
    
    注意: MCPClient 需要先 connect_all(),否则拿不到 tools。
    """
    entries = []
    for server_name in mcp_client.list_servers():
        connection = mcp_client.servers.get(server_name)
        if not connection or not connection.is_connected:
            continue
        for tool in connection.tools:
            full_name = f"onion.mcp.{server_name}.{tool.name}"
            entries.append(ToolEntry(
                tag=Tag.MCP,
                scope=server_name,
                tool=tool.name,
                full_name=full_name,
                description=tool.description or "",
                input_schema=tool.inputSchema or {},
                handler=None,  # MCP 通过 client.call_tool() 调,不需要存 handler
                timeout=60,
                metadata={"server_type": connection.config.type},
            ))
    return entries


def collect_skill_tools(skills_client: AgentSkillsClient) -> list[ToolEntry]:
    """
    从 AgentSkillsClient 收集 skill,转成"伪 schema"让 LLM 可以"调用"。
    
    关键: skill 不是函数,所以 parameters={} + description 强调"激活后获得什么"。
    router 收到 onion.skill.* 的 call → 走特殊路径(§10),不传 args。
    """
    entries = []
    for skill_name, props in sorted(skills_client.scan_all().items()):
        full_name = f"onion.skill.{skill_name}"
        entries.append(ToolEntry(
            tag=Tag.SKILL,
            scope=skill_name,  # skill 的 scope 就是它自己
            tool="__load__",   # skill 没有 tool 概念,固定占位
            full_name=full_name,
            description=f"[Agent Skill] {props.description}",
            input_schema={"type": "object", "properties": {}, "required": [], "additionalProperties": False},
            handler=None,
            timeout=10,
            metadata={"skill_name": skill_name, "compatibility": props.compatibility},
        ))
    return entries
```

### 8.4 主流程(`tool_list.collect_all`)

```python
async def collect_all(
    workspace_dir: Path,
    auto_connect_mcp: bool = True,
) -> ToolRegistry:
    """
    汇总所有来源的工具,返回 ToolRegistry。
    
    Args:
        workspace_dir: agent 工作区根目录(从 file_backend init)
        auto_connect_mcp: 是否自动连接 MCP server(False 时 mcp tag 无工具)
    
    Returns:
        ToolRegistry 实例,含 entries + clients(供 router 用)
    """
    registry = ToolRegistry()
    
    # 1) Buildin(同步,直接扫描)
    try:
        from src.infrastructure.tool_shell.buildin_client import BuildinClient
        buildin = BuildinClient(auto_load=True)
        for entry in collect_buildin_tools(buildin):
            registry.register(entry)
        registry.register_client(Tag.BUILDIN, buildin)
    except Exception as e:
        registry._load_errors.append({"source": "buildin", "error": str(e)})
    
    # 2) MCP(异步,需要 connect_all)
    try:
        from src.infrastructure.tool_shell.mcp_client import MCPClient
        mcp_config = workspace_dir / "mcp_servers.json"
        if mcp_config.exists():
            mcp = MCPClient(config_path=str(mcp_config))
            if auto_connect_mcp:
                await mcp.connect_all()
            for entry in collect_mcp_tools(mcp):
                registry.register(entry)
            registry.register_client(Tag.MCP, mcp)
    except Exception as e:
        registry._load_errors.append({"source": "mcp", "error": str(e)})
    
    # 3) Skill(扫描本地 skills/ 目录)
    try:
        from src.infrastructure.tool_shell.agent_skills_client import (
            ProgressiveDisclosureEngine,
        )
        skills_root = workspace_dir / "skills"
        if skills_root.exists():
            engine = ProgressiveDisclosureEngine(skills_root)
            for entry in collect_skill_tools(engine):
                registry.register(entry)
            registry.register_client(Tag.SKILL, engine)
    except Exception as e:
        registry._load_errors.append({"source": "skill", "error": str(e)})
    
    # 4) Agent(预留,P1 阶段)
    # TODO: 接入 update_plan / finish_loop / record_memory / ask_user
    
    return registry
```

### 8.5 持久化到 `tools.jsonl`

```python
def write_tools_jsonl(registry: ToolRegistry, workspace_dir: Path) -> None:
    """
    把汇总后的 tool list 持久化到 <workspace>/tools.jsonl。
    
    每行一个 JSON object,符合 file_backend/prompt.md 目录约定。
    用途:断点恢复时,直接读 tools.jsonl 即可重建 tool_list,不用重新 connect MCP。
    """
    tools_path = workspace_dir / "tools.jsonl"
    with open(tools_path, "w", encoding="utf-8") as f:
        for entry in sorted(registry.entries.values(), key=lambda e: e.full_name):
            line = {
                "tag": entry.tag.value,
                "scope": entry.scope,
                "tool": entry.tool,
                "full_name": entry.full_name,
                "description": entry.description,
                "input_schema": entry.input_schema,
                "timeout": entry.timeout,
                "metadata": entry.metadata,
            }
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
```

---

## 9. `tool_router.py` 详细设计

### 9.1 职责

1. **解析 name**——按 `onion.<tag>.<scope>.<tool>` 切分
2. **解析 arguments**——`json.loads` → `json-repair` 兜底
3. **校验参数**——用对应工具的 `input_schema` 做 JSON Schema 校验
4. **路由执行**——按 tag 调对应 client
5. **格式化输出**——返回 `{success, content, is_error, error, data}` 统一格式
6. **错误兜底**——任何异常都转 `is_error=True`,不静默吞

### 9.2 核心数据结构

```python
@dataclass
class RouterResult:
    """tool_router 的统一返回(对应 §7.4 写回 role:"tool" 的字段)。"""
    tool_call_id: str
    name: str
    success: bool
    is_error: bool
    content: str
    error: Optional[str] = None
    data: dict = field(default_factory=dict)
    
    def to_tool_message(self) -> dict:
        """转 OpenAI role:"tool" 消息。"""
        return {
            "role": "tool",
            "tool_call_id": self.tool_call_id,
            "name": self.name,
            "content": self.content,
        }
```

### 9.3 关键函数(伪代码)

```python
import re
import json
import time
import hashlib
import asyncio
from typing import Optional

# §4.2 标签解析正则
TOOL_NAME_PATTERN = re.compile(
    r"^onion\."
    r"(?P<tag>buildin|mcp|skill|agent)\."
    r"(?P<scope>[a-z0-9_][a-z0-9_-]{0,63})\."
    r"(?P<tool>[a-z0-9_][a-z0-9_-]{0,127})$"
)


def parse_tool_name(name: str) -> Optional[tuple[str, str, str]]:
    """
    解析 onion.<tag>.<scope>.<tool>。
    失败返回 None(交由上层构造 is_error 结果)。
    """
    m = TOOL_NAME_PATTERN.match(name.strip())
    if not m:
        return None
    return m.group("tag"), m.group("scope"), m.group("tool")


def parse_arguments(raw_args: str) -> tuple[Optional[dict], Optional[str]]:
    """
    §5.5 + tool_accuracy §四-④:7 层 JSON 解析兜底。
    
    1. 标准 json.loads
    2. 补全常见截断(末尾 "}"、"\"]" 等)
    3. json-repair 库(若安装)
    4. ast.literal_eval(单引号 dict 兜底)
    5. smart quote 替换(OpenClaw §5.5)
    6. surrogate 字符清洗(§5.6)
    7. 仍失败 → 返回 (None, error_msg)
    """
    if not raw_args or not raw_args.strip():
        return {}, None
    
    # Layer 1: 标准 JSON
    try:
        v = json.loads(raw_args)
        if isinstance(v, dict):
            return v, None
    except json.JSONDecodeError:
        pass
    
    # Layer 2: 补全截断
    fixed = raw_args.rstrip().rstrip(",")
    for tail in ("}", "]", "}}", "}}]", "\"]"):
        try:
            v = json.loads(fixed + tail)
            if isinstance(v, dict):
                return v, None
        except json.JSONDecodeError:
            continue
    
    # Layer 3: json-repair
    try:
        from json_repair import repair_json
        v = json.loads(repair_json(raw_args))
        if isinstance(v, dict):
            return v, None
    except (ImportError, Exception):
        pass
    
    # Layer 4: ast.literal_eval
    try:
        import ast
        v = ast.literal_eval(raw_args)
        if isinstance(v, dict):
            return v, None
    except Exception:
        pass
    
    # Layer 5: smart quote 替换
    sq = raw_args.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
    try:
        v = json.loads(sq)
        if isinstance(v, dict):
            return v, None
    except json.JSONDecodeError:
        pass
    
    # Layer 6: surrogate 清洗
    try:
        cleaned = raw_args.encode("utf-8", errors="replace").decode("utf-8", errors="replace")
        v = json.loads(cleaned)
        if isinstance(v, dict):
            return v, None
    except json.JSONDecodeError:
        pass
    
    return None, f"Arguments not parseable as JSON object after 6-layer repair: {raw_args[:200]!r}"


def validate_arguments(args: dict, schema: dict) -> Optional[str]:
    """
    JSON Schema 校验(§3.4 必做)。
    
    用 jsonschema 库(若没装,用 buildin_client 的轻量校验器)。
    失败返回错误消息,成功返回 None。
    """
    if not schema or schema.get("type") != "object":
        return None
    
    try:
        from jsonschema import validate, ValidationError
        validate(instance=args, schema=schema)
        return None
    except ImportError:
        # Fallback: buildin_client 的轻量校验
        from src.infrastructure.tool_shell.buildin_client import _validate_arguments
        ok, err = _validate_arguments(schema, args)
        return None if ok else err
    except ValidationError as e:
        return f"{list(e.path)}: {e.message}"
    except Exception as e:
        return f"Schema validation crashed: {e}"


def fallback_tool_call_id(tool_call: dict) -> str:
    """
    §5.11:provider 漏给 tool_call_id 时,MD5 合成。
    """
    fn = tool_call.get("function", {})
    seed = f"{fn.get('name', '')}|{fn.get('arguments', '')}"
    return "call_" + hashlib.md5(seed.encode()).hexdigest()[:12]
```

### 9.4 路由主函数(单条 + 批量)

```python
class ToolRouter:
    """
    tool_router.py 的主类。
    
    接收 ToolRegistry,提供 dispatch_one / dispatch_many 同步 API。
    """
    
    def __init__(self, registry: ToolRegistry):
        self.registry = registry
    
    def dispatch_one(self, tool_call: dict) -> RouterResult:
        """同步路由单条 tool_call。"""
        # Step 1: tool_call_id 兜底
        call_id = tool_call.get("id") or fallback_tool_call_id(tool_call)
        name = tool_call.get("function", {}).get("name", "")
        raw_args = tool_call.get("function", {}).get("arguments", "") or "{}"
        
        # Step 2: 解析 name
        parsed = parse_tool_name(name)
        if parsed is None:
            return RouterResult(
                tool_call_id=call_id, name=name, success=False, is_error=True,
                content=f"[ERROR] Invalid tool name format. Expected onion.<tag>.<scope>.<tool>, got: {name!r}",
                error="invalid_tool_name",
            )
        tag, scope, tool = parsed
        
        # Step 3: 解析 arguments
        args, parse_err = parse_arguments(raw_args)
        if parse_err:
            return RouterResult(
                tool_call_id=call_id, name=name, success=False, is_error=True,
                content=f"[ERROR] Argument parse failed: {parse_err}",
                error="argument_parse_failed",
                data={"tag": tag, "scope": scope, "tool": tool},
            )
        
        # Step 4: 查 schema
        entry = self.registry.lookup(name)
        if entry is None:
            return RouterResult(
                tool_call_id=call_id, name=name, success=False, is_error=True,
                content=f"[ERROR] Unknown tool: {name}",
                error="unknown_tool",
                data={"tag": tag, "scope": scope, "tool": tool},
            )
        
        # Step 5: schema 校验
        validation_err = validate_arguments(args, entry.input_schema)
        if validation_err:
            return RouterResult(
                tool_call_id=call_id, name=name, success=False, is_error=True,
                content=f"[ERROR] Argument schema validation failed: {validation_err}",
                error="argument_validation_failed",
                data={"tag": tag, "scope": scope, "tool": tool, "arguments": args},
            )
        
        # Step 6: 按 tag 路由
        start = time.time()
        if tag == "skill":
            return self._dispatch_skill(call_id, name, scope, args, start)
        elif tag == "mcp":
            return self._dispatch_mcp(call_id, name, scope, tool, args, start)
        elif tag == "buildin":
            return self._dispatch_buildin(call_id, name, scope, tool, args, start)
        elif tag == "agent":
            return self._dispatch_agent(call_id, name, scope, tool, args, start)
        else:
            return RouterResult(
                tool_call_id=call_id, name=name, success=False, is_error=True,
                content=f"[ERROR] Unsupported tag: {tag}",
                error="unsupported_tag",
            )
    
    def _dispatch_buildin(self, call_id, name, scope, tool, args, start):
        client = self.registry.clients.get(Tag.BUILDIN)
        if client is None:
            return _err(call_id, name, "No buildin client registered")
        spec = f"{scope}.{tool}"
        try:
            result = client.call_tool(spec, args)
        except Exception as e:
            return _err(call_id, name, f"Buildin tool exception: {e}", duration_ms=_elapsed(start))
        return _from_client_result(call_id, name, result, "buildin", scope, tool, args, _elapsed(start))
    
    def _dispatch_mcp(self, call_id, name, scope, tool, args, start):
        client = self.registry.clients.get(Tag.MCP)
        if client is None:
            return _err(call_id, name, "No MCP client registered")
        spec = f"{scope}.{tool}"
        try:
            # MCP 是 async,在 sync wrapper 里跑 event loop
            coro = client.call_tool(scope, tool, args)
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            if loop.is_running():
                # 已经在 event loop 里(异步调用方),返回 coroutine 给上层
                # 上层应该用 dispatch_many_async
                result_raw = coro  # caller will await
            else:
                result_raw = loop.run_until_complete(coro)
        except Exception as e:
            return _err(call_id, name, f"MCP tool exception: {e}", duration_ms=_elapsed(start))
        return _from_client_result(call_id, name, result_raw, "mcp", scope, tool, args, _elapsed(start))
    
    # ... 详见代码实现
    
    def dispatch_many(self, tool_calls: list[dict], parallel: bool = True) -> list[RouterResult]:
        """
        批量路由,默认并行(asyncio.gather)。
        """
        if not tool_calls:
            return []
        if not parallel or len(tool_calls) == 1:
            return [self.dispatch_one(tc) for tc in tool_calls]
        # 并行:这里简化用顺序,并行版本放 dispatch_many_async
        # 真正用 async 时由 L4 Engine 在 asyncio 上下文里调 dispatch_one_async
        return [self.dispatch_one(tc) for tc in tool_calls]
```

### 9.5 错误封装工具函数

```python
def _err(call_id, name, msg, tag=None, scope=None, tool=None, arguments=None, duration_ms=0):
    return RouterResult(
        tool_call_id=call_id, name=name, success=False, is_error=True,
        content=f"[ERROR] {msg}", error=msg,
        data={"tag": tag, "scope": scope, "tool": tool,
              "arguments": arguments or {}, "duration_ms": duration_ms},
    )


def _from_client_result(call_id, name, result, tag, scope, tool, args, duration_ms):
    """
    把 client 统一返回的 {success, content, is_error, error, data} 转 RouterResult。
    """
    return RouterResult(
        tool_call_id=call_id, name=name,
        success=result.get("success", False),
        is_error=result.get("is_error", True),
        content=result.get("content", ""),
        error=result.get("error"),
        data={
            "tag": tag, "scope": scope, "tool": tool,
            "arguments": args, "duration_ms": duration_ms,
            "raw_result": result.get("data"),
        },
    )
```

---

## 10. Skill 的特殊处理(因为它不是函数调用)

### 10.1 为什么特殊

Skills 是 **prompt-as-tool**——不是"执行一个函数",而是"加载一段 L2 提示词到 LLM 上下文"。

### 10.2 三种实现方案

| 方案 | 描述 | 优点 | 缺点 | 选 |
|------|------|------|------|---|
| **A. `role:tool` 回灌** | router 收到 `onion.skill.<slug>` 的 call → 读 SKILL.md 的 L2 正文 → 返 `content = "# Skill正文..."` 走 role:tool 通道 | 实现简单、符合 OpenAI 标准、LLM 自然看到 skill 指令 | 占用 role:tool 配额(同一次 tool_call_id) | ✅ **选这个** |
| **B. 拼到 system prompt** | router 加载 skill 正文 → 拼到 system message(用"## Active Skills"段) | 长期生效,不占 tool 配额 | 改 system prompt 击穿 OpenAI prompt cache(Hermes 反例);多次激活可能重复 | ❌ |
| **C. 拼到最近 user message** | 加载 skill 正文 → 拼到最近 user message 末尾 | cache 命中好 | 实现复杂、需要管 message 列表;并发多 skill 时顺序难定 | ❌ |

### 10.3 方案 A 的实现

```python
def _dispatch_skill(self, call_id, name, scope, args, start):
    """
    Skill 特殊路径:不执行函数,加载 L2 提示词,返 role:tool。
    """
    engine = self.registry.clients.get(Tag.SKILL)
    if engine is None:
        return _err(call_id, name, "No skills client registered")
    
    skill_name = scope  # skill 的 scope 就是 slug
    try:
        skill = engine.load_skill_instruction(skill_name)
    except Exception as e:
        return _err(call_id, name, f"Skill load failed: {e}", duration_ms=_elapsed(start))
    
    # 格式化 L2 内容(用 markdown 包装,告诉 LLM 这是 skill 指令)
    body = skill.body
    content = (
        f"# Activated Skill: {skill.properties.name}\n\n"
        f"{body}\n\n"
        f"---\n"
        f"[Activated via {name}. Follow the skill instructions above to complete the user's request. "
        f"Use available tools (e.g. update_plan, file operations, MCP servers) to execute the workflow. "
        f"Do NOT call {name} again in this turn — the skill is now active.]"
    )
    
    return RouterResult(
        tool_call_id=call_id, name=name, success=True, is_error=False,
        content=content,
        data={
            "tag": "skill", "scope": skill_name, "tool": "__load__",
            "arguments": args, "duration_ms": _elapsed(start),
            "skill_name": skill_name, "disclosure_level": "L2",
        },
    )
```

### 10.4 Skill 标签的 description 怎么写

为了让 LLM 知道**何时调用 skill**(而不是直接调函数),description 必须:
- 用第一人称("我")描述 skill 提供的**能力**,而不是 skill **是什么**
- 列出**触发场景**(用数字编号)
- 强调"无需参数,调用即激活"

```python
description = (
    "[Agent Skill] 加载 PDF 处理技能,激活后我获得: "
    "(1) 文本提取(pdfplumber);"
    "(2) 表格解析;"
    "(3) 表单填写(PyPDF2/pdftk);"
    "(4) PDF 合并/拆分。"
    "触发:用户提到 PDF、表单、文档提取、PDF 合并等场景。"
    "无需任何参数——调用即激活,激活后我会按 skill 指令执行。"
)
```

---

## 11. 错误处理与质量防线(7 层兜底)

| 层 | 出错位置 | 处理策略 | 对应标准 |
|----|---------|---------|---------|
| **L1** | name 不符合 `onion.<tag>.<scope>.<tool>` 格式 | `is_error=True` 回灌,提示"Expected onion.<tag>.<scope>.<tool>" | §5.4 |
| **L2** | `function.arguments` 不是合法 JSON | 6 层 JSON 修复(§9.3)→ 仍失败则 `is_error=True` 回灌 | §5.5 / tool_accuracy §四-④ |
| **L3** | arguments 通过 JSON 解析但违反 schema | `jsonschema` 校验→ 失败则 `is_error=True` 回灌,message 明确"哪个参数错" | §3.4 |
| **L4** | 工具在 registry 中找不到 | `is_error=True` 回灌,列出"类似工具"提示(用 `difflib.get_close_matches`) | §5.4 |
| **L5** | client 抛出异常(BusinessError) | `try/except BaseException` 包住,转 `is_error=True` 回灌,content 含 `type(e).__name__` | §5.10 + tool_accuracy §四-⑤ |
| **L6** | 工具返回结果非 dict / 缺 success 字段 | `_format_call_result` 容错:str 视为 content;dict 走约定解析 | buildin_client 已实现 |
| **L7** | 连续 N 次同 tool_call 重复 | `DOOM_LOOP_THRESHOLD=3` 计数,超限返 `finish_loop` 提示(由 L3 SDK 做,本模块只是触发) | §5.9 |

### 11.1 关键原则(从 standard/tool_channel.md 提炼)

- **绝不静默吞**——任何错误都必须以 `is_error=True` 形式回灌,让 LLM 自我修正(§3.4 + tool_accuracy §四-④)
- **绝不修改 input_arguments**——LLM 传啥就校验啥,改写是 silent 静默反例(§3.4 反例)
- **错误信息要可执行**——不是"参数错了",而是"`path` 应为 string,实际是 int: 123"——LLM 才能自我修正

### 11.2 Surrogate 字符清洗(§5.6 必做)

```python
def clean_surrogate(text: str) -> str:
    """防 Ollama crash。"""
    return text.encode("utf-8", errors="replace").decode("utf-8", errors="replace")
```

在 router 收到 `function.name` / `function.arguments` / client 返回的 `content` 时,**全部走一遍**。

---

## 12. 持久化:工具列表写入 `tools.jsonl`

参考 `file_backend/prompt.md` 目录约定,工作区有 `tools.jsonl` 文件,每行一个 JSON 对象(参考 `session.jsonl` 同款 append-only):

```jsonl
{"tag":"buildin","scope":"file_system","tool":"read_file","full_name":"onion.buildin.file_system.read_file","description":"...","input_schema":{...},"timeout":60,"metadata":{}}
{"tag":"buildin","scope":"command_line","tool":"run_command","full_name":"onion.buildin.command_line.run_command","description":"...","input_schema":{...},"timeout":60,"metadata":{}}
{"tag":"mcp","scope":"searxng","tool":"searxng_web_search","full_name":"onion.mcp.searxng.searxng_web_search","description":"...","input_schema":{...},"timeout":60,"metadata":{"server_type":"stdio"}}
{"tag":"skill","scope":"pdf-processing","tool":"__load__","full_name":"onion.skill.pdf-processing","description":"[Agent Skill] ...","input_schema":{"type":"object","properties":{},"required":[],"additionalProperties":false},"timeout":10,"metadata":{"skill_name":"pdf-processing"}}
```

**用途**:
- 断点恢复:Agent Loop 重启时,直接读 `tools.jsonl` 重建 tool list(不需要重新 connect MCP)
- 调试:产品经理可以 `cat tools.jsonl | jq` 看所有工具
- 审计:记录某次 session 用了哪些工具

**注意**:`tools.jsonl` 是 **session 启动时**写一次,运行期间 MCP 工具可能动态变化(暂不考虑,MVP 用静态 snapshot)。

---

## 13. 协议中立:OpenAI / Anthropic 适配点

### 13.1 OpenAI Chat Completions(本设计默认)

```json
{
  "type": "function",
  "function": {
    "name": "onion.buildin.file_system.read_file",
    "description": "...",
    "parameters": { "type": "object", "properties": {...}, "required": [...] }
  }
}
```

→ 直接用 `tools=[...]` 参数(本设计的目标格式)

### 13.2 Anthropic Messages API(预留 adapter)

```json
{
  "name": "onion.buildin.file_system.read_file",
  "description": "...",
  "input_schema": { "type": "object", "properties": {...}, "required": [...] }
}
```

→ 关键差异:Anthropic 用 `input_schema` 不用 `parameters`;无 `type: "function"` 外层;`strict` 字段不存在
→ adapter 位置:未来在 `src/infrastructure/tool_shell/anthropic_adapter.py`(L5 infra)或 L3 SDK 里
→ **本设计不影响**:tool_channel 内部统一用 OpenAI 风格,adapter 是上层的事

### 13.3 路由侧的协议中立

router 不依赖协议——只消费 `tool_calls[i].function.{name, arguments}` 这种"逻辑结构":
- OpenAI:`{type:"function", function:{name, arguments}}` ✓
- Anthropic:`{type:"tool_use", name, input}` → 在 L4 engine 内部转 OpenAI 风格给 router
- Gemini:`{functionCall:{name, args}}` → 同样在 L4 内部转

→ **router 只看 L4 引擎给它的统一 OpenAI 风格**——这是 §1.1 原则一"协议中立"的落地

---

## 14. CLI(所见即所得)

### 14.1 `tool_list.py` CLI

```powershell
# 看 tool registry 状态(不展开 schema)
python tool_list.py --workspace D:\onion\andy --status

# 输出 OpenAI 风格 tools 列表(给 LLM 用,已排序)
python tool_list.py --workspace D:\onion\andy --to-openai

# 按 tag 筛选
python tool_list.py --workspace D:\onion\andy --tag buildin --to-openai
python tool_list.py --workspace D:\onion\andy --tag mcp --to-openai
python tool_list.py --workspace D:\onion\andy --tag skill --to-openai

# 写入 tools.jsonl
python tool_list.py --workspace D:\onion\andy --write

# 看某个 tool 的 schema
python tool_list.py --workspace D:\onion\andy --tool-info onion.buildin.file_system.read_file

# 详细 schema(可读)
python tool_list.py --workspace D:\onion\andy --tool-info onion.buildin.file_system.read_file --detail
```

**输出示例**(`--status`):
```
Tool Registry Status
─────────────────────────────────────
Total tools: 41
  - buildin: 37
  - mcp:     3
  - skill:   1
  - agent:   0

Clients:
  - buildin: BuildinClient
  - mcp:     MCPClient (3 servers connected, 0 failed)
  - skill:   ProgressiveDisclosureEngine (1 skill)

Load errors: 0
```

### 14.2 `tool_router.py` CLI

```powershell
# 模拟一次 LLM 调用:解析一段 tool_calls JSON,路由执行
python tool_router.py --workspace D:\onion\andy \
    --call '{"id":"call_1","type":"function","function":{"name":"onion.buildin.file_system.list_dir","arguments":"{\"path\":\".\"}"}}'

# 多条 tool_call(测试并行路由)
python tool_router.py --workspace D:\onion\andy --call-file calls.json

# 看 router 解析的中间结果(不真调工具,只校验)
python tool_router.py --workspace D:\onion\andy --call '...' --dry-run

# 看 router 健康状态
python tool_router.py --workspace D:\onion\andy --status
```

**输出示例**(`--call`):
```
[1/1] Parsing call: call_1 → onion.buildin.file_system.list_dir
      Parsed: tag=buildin scope=file_system tool=list_dir
      Args parsed: {'path': '.'}
      Schema validation: OK
      Routing to: BuildinClient
      Executing... 12ms
      Result:
{
  "success": true,
  "is_error": false,
  "content": "AGENT.md\nMEMORY.md\nsession.jsonl\n...",
  "data": {
    "tag": "buildin",
    "scope": "file_system",
    "tool": "list_dir",
    "duration_ms": 12,
    "truncated": false
  }
}
```

---

## 15. P0 / P1 / P2 优先级

| 优先级 | 内容 | 状态 |
|-------|------|------|
| **P0** | 4 类 tag(budin / mcp / skill / agent 占位) | ✅ 本设计 |
| **P0** | `onion.<tag>.<scope>.<tool>` 命名规范 | ✅ 本设计 |
| **P0** | `ToolRegistry` + `ToolEntry` 统一抽象 | ✅ 本设计 |
| **P0** | 7 层 JSON 解析兜底 | ✅ 本设计 |
| **P0** | 3 类 client 集成(buildin / mcp / skill) | ✅ 本设计 |
| **P0** | `tools.jsonl` 持久化 | ✅ 本设计 |
| **P0** | Skill 特殊路径(方案 A:role:tool 回灌 L2) | ✅ 本设计 |
| **P0** | CLI(状态/汇总/单条调用) | ✅ 本设计 |
| **P0** | 错误信息可执行(`<field> 应当 X,实际是 Y`) | ✅ 本设计 |
| **P0** | Surrogate 字符清洗 | ✅ 本设计 |
| **P1** | `agent` tag 接入(`update_plan` / `finish_loop` / `record_memory` / `ask_user`) | ⏳ P1 |
| **P1** | Anthropic Messages adapter | ⏳ P1 |
| **P1** | Doom loop 检测(连续 N 次同 tool_call 计数) | ⏳ P1 |
| **P1** | Parallel tool execution(asyncio.gather 真正并行) | ⏳ P1 |
| **P1** | Streaming tool_calls 增量解析(OpenAI `delta.tool_calls`) | ⏳ P1 |
| **P1** | Tool Search 渐进披露(`tool_search` / `tool_describe` meta 工具) | ⏳ P1(工具数 ≥ 20 触发) |
| **P2** | Per-tool retry policy / timeout 配置(`@tool(retry=3, timeout=30)`) | ⏳ P2 |
| **P2** | 多模态结果(图/音/视频) | ⏳ P2 |
| **P2** | Tool call 审计 log(`~/.onion/logs/tool_calls_<session>.jsonl`) | ⏳ P2 |
| **P2** | Tool Search 黑名单(防自递归 `tool_search(tool_search)`) | ⏳ P2(配套 Tool Search) |

---

## 16. 行业标准映射清单(自我验证)

按 `standard/tool_channel.md` 的"必做/强烈建议/可选"标签,**本设计已覆盖**的项目:

| 编号 | 标准 | 必做度 | 本设计落地位置 |
|------|------|--------|---------------|
| §1.1 | 协议中立 | **必做** | §13 适配点;router 只看 L4 引擎给的统一 OpenAI 风格 |
| §1.2 | 工具类型统一抽象 | **必做** | §8.2 `ToolEntry` dataclass |
| §1.3 | 配置即代码 | **必做** | §8.4 `collect_all` 调三个 client 的 `to_openai_schema` / `list_tools` / `scan_skills`(声明式) |
| §1.4 | 沙箱与凭证白名单 | **必做** | **未直接做**——这是 buildin 工具自己的事(file_system 的路径白名单);router 只调工具,不管白名单 |
| §2.1 | 内置工具 | **必做** | §8.3 `collect_buildin_tools` |
| §2.2 | MCP | **必做** | §8.3 `collect_mcp_tools` |
| §2.3 | Agent Skills | **必做** | §8.3 `collect_skill_tools` + §10 特殊处理 |
| §3.1 | JSON Schema 强制 | **必做** | §6.1 + §8.3 schema 透传 |
| §3.3 | `required` + `additionalProperties: false` | **必做** | §6.1 + buildin_client 已实现 |
| §3.4 | Schema 强校验 + 容错 | **必做** | §9.3 `validate_arguments` |
| §4.1 | OpenAI function calling | **必做** | §6 + §7 |
| §4.4 | 集中式 ToolRegistry | 强烈建议 | §8.2 `ToolRegistry` |
| §4.5 | 工具名排序 for prompt cache hit | 强烈建议 | §8.2 `collect_tools` 排序 |
| §4.6 | 工具名规范化 | 强烈建议 | §4.2 正则 + §5.4 + §9.3 case-insensitive lookup |
| §4.8 | Tool Search 黑名单(防自递归) | **必做** | ⏳ P2(配套 Tool Search 实现) |
| §5.1 | 流式增量解析 | **必做** | ⏳ P1(由 L4 engine 处理 streaming,router 接的是完整 tool_calls) |
| §5.2 | 流式按 id 关联 | **必做** | §7.3 `dispatch_many` 严格保序;§9.4 `tool_call_id` 精确对应 |
| §5.3 | plain-text tool call 修复 | 强烈建议 | ⏳ P1(目前依赖 OpenAI strict mode 减少 plain-text;LLM 真出错时走 §9.3 6 层修复) |
| §5.4 | 工具名 hallucination 修复 | 强烈建议 | §4.2 正则 + §5.4 `name.lower()` + §9.4 模糊匹配提示 |
| §5.5 | JSON 参数解析失败修复 | 强烈建议 | §9.3 6 层 JSON 修复 |
| §5.6 | Surrogate 字符清洗 | **必做** | §11.2 `clean_surrogate`(在 router 入口和出口都洗) |
| §5.9 | Doom loop 检测 | 强烈建议 | ⏳ P1(由 L3 SDK `agent_loop.py` 做,tool_channel 不管) |
| §5.10 | Unreadable tool 隔离 | **必做** | §8.4 每个 client `try/except` 包住,失败不互踩 |
| §5.11 | Tool call ID 兜底 | 可选 | §9.3 `fallback_tool_call_id`(MD5 合成) |
| §5.12 | Per-tool retry 上限 | 强烈建议 | §6.1 `ToolEntry.timeout` + §6.1 P2 `max_retries` |
| §6.1 | OpenAI `role=tool` + `tool_call_id` | **必做** | §7.4 `to_tool_message()` |
| §6.4 | 错误标记 `isError` | **必做** | §7.2 / §9.2 `is_error` 字段 |
| §6.5 | 结果内容 = JSON 字符串 | **必做** | §7.4 `content: str`(由 client 自己负责 json.dumps) |
| §6.8 | Multi-protocol 适配 | **必做** | §13(由 L4 engine 转,router 不管) |

**未覆盖项总结**:P0 已 100% 覆盖;P1/P2 主要是 streaming / doom loop / tool search / multi-modal,合理延期。

---

## 17. 与其他 SRS 模块的对接

| 上游模块 | 下游消费本模块的方式 |
|---------|-------------------|
| `src/infrastructure/file_backend/init_workspace.py` | 初始化时创建 `tools.jsonl`(空);L3 SDK 启动时调 `tool_list.collect_all(workspace_dir)` 重新填充 |
| `src/infrastructure/buildin_tools/*.py` | 不动,只需遵守 `TOOL_SCHEMAS` + `TOOL_HANDLERS` 约定(已实现) |
| `src/infrastructure/tool_shell/*.py` | 不动,三个 client 接口对齐(已实现) |
| `src/openai_engine/openai_tool_engine.py`(L4) | 调 `tool_list.collect_all(workspace_dir)` 拿 `tools`;调 `tool_router.ToolRouter(registry).dispatch_many(calls)` 处理 tool_calls;把结果写回 `role:"tool"` 消息 |
| `src/sdk/create_react_agent.py`(L3,未来) | 在 session 启动时构造 `ToolRegistry`,挂到 L4 engine;session 退出时写回 `tools.jsonl` |

---

## 18. 给后续开发者的注意事项

1. **永远不要破坏 OpenAI 风格 schema 透传**——client 的 `to_openai_schema()` 是单一真相源,tool_channel 只加前缀,不改字段
2. **加新 tag 必须同步**——`Tag` 枚举、§4.1 表格、`collect_all` 入口、`dispatch_*` 路由函数
3. **加新 client 必须实现 4 个接口**:`to_openai_schema()` / `list_tools()` / `call_tool(spec, args)` / 统一返回 `{success, content, is_error, error, data}`
4. **router 抛异常要尽可能保留堆栈**——`traceback.format_exc()` 写到 router 的 debug log,不要进 LLM 上下文(LLM 看到 stacktrace 会乱)
5. **skills 不是函数**——加新"非函数型"工具时,参考 §10 模式,新加 tag 类别,不要硬塞进 buildin
6. **tool name 是 cache key**——改 tool 名就是改 prompt cache key,会击穿所有用户的 cache;tool 重命名要走 P1 migration

---

## 19. 总结

`tool_channel` 的核心职责可以压缩成 4 句话:

1. **收集**——`tool_list.collect_all(workspace_dir)` 从三个 client 拿 schema,加 `onion.<tag>.<scope>.<tool>` 前缀
2. **上报**——返回 OpenAI Chat Completions 风格的 `tools` 列表(已排序)给 L4 engine
3. **解析**——`tool_router` 收到 LLM 的 `tool_calls`,按 7 层兜底解析 name + arguments + schema 校验
4. **路由**——按 tag 调对应 client,把结果统一格式化成 `{success, content, is_error, ...}` 回灌 LLM

让 LLM **用一把 tools 就能调用所有来源的工具**——这就是 tool_channel 的存在价值。
