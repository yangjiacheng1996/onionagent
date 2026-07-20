# Hermes Agent — 工具调用（Tool Channel）调研报告

> 调研对象:NousResearch/hermes-agent ｜ 调研时间:2026-07-18
> 上游报告:`harness/01_market_research/Hermes_Agent/file_backend.md`(工作区维度)
> 本报告焦点:工具调用通道(注册 → 列表生成 → 指令解析 → 结果回传 → 持久化)

---

## 0. 智能体一句话定位

**"the agent that grows with you"** —— 自改进 + 长期记忆 + Multi-Agent Kanban。工具能力分三层:**窄腰核心(`_HERMES_CORE_TOOLS`)+ 工具集(toolset)按场景组合 + 插件/MCP/技能边缘扩展**。这一哲学直接决定工具通道设计 —— **核心稳定、边缘可换、所有能力最终"扁平化"成 OpenAI function calling schema 喂给 LLM**。

---

## 1. 调研依据

| 文件 | 关键作用 |
|------|----------|
| `toolsets.py` | 工具集(TOOLSETS 字典)+ `_HERMES_CORE_TOOLS` 共享列表 + `resolve_toolset()` 解析 |
| `tools/registry.py` | **ToolRegistry 单例** + `registry.register()` 自注册 API + check_fn TTL 缓存 + dynamic generation 计数 |
| `model_tools.py` | `get_tool_definitions()` 公开 API + `coerce_tool_args()` 类型修复 + `handle_function_call()` 派发 + LRU 缓存 |
| `tools/mcp_tool.py` | **MCP 客户端**(stdio / HTTP / StreamableHTTP / SSE) + 动态注册到 registry |
| `tools/mcp_oauth.py` | **MCP OAuth 2.1 + PKCE** + `HermesTokenStorage` 持久化到 `~/.hermes/mcp-tokens/<server>.json` |
| `tools/skills_tool.py` + `agent/skill_utils.py` | **Agent Skills(progressive disclosure)** — `skills_list` 只返元数据,`skill_view` 按需加载 SKILL.md |
| `agent/conversation_loop.py:4600+` | **流式 tool call 解析 + 错误修复 + 重试** 核心 |
| `agent/auxiliary_client.py` + `agent/anthropic_adapter.py` | **多协议**(OpenAI / Anthropic / Bedrock / Gemini / Azure / Vertex) |
| `tools/tool_result_storage.py` + `tools/budget_config.py` | **3 层大结果保护**(per-tool / per-result / per-turn) |
| `agent/file_safety.py:109-310` | **LLM 不可读目录白名单** —— `mcp-tokens/`、`auth.json`、`.env`、`.ssh/`、`.aws/` |
| `run_agent.py:5915+` | `_execute_tool_calls()` —— **并行/串行 segment 规划器** |
| `tools/kanban_tools.py:1917+` | Multi-Agent Kanban 工具集(12 个,默认只在 `HERMES_KANBAN_TASK` env 启用) |
| `optional-mcps/*/manifest.yaml` | 官方 MCP 目录(blender / linear / n8n / unreal-engine) |
| `skills/*/SKILL.md` + `optional-skills/*/SKILL.md` | 20+ 类目、300+ 技能,完全 agentskills.io 兼容 |

---

## 2. 五个核心问题的回答

### Q1. 工具来源:内置 / MCP / Agent Skills / 其他

#### 1.1 内置工具(自注册模式)

Hermes **不维护写死工具字典**;每个工具文件在模块级调用 `registry.register(...)` 自注册。`tools/registry.py:55-78` 的 `discover_builtin_tools()` 用 **AST 扫描** `tools/*.py`,自动发现哪些文件含顶层 `registry.register(...)` 调用并 import。典型结尾(`tools/terminal_tool.py:3132-3139`):

```python
registry.register(
    name="terminal", toolset="terminal", schema=TERMINAL_SCHEMA,
    handler=_handle_terminal, check_fn=check_terminal_requirements,
    emoji="💻", max_result_size_chars=100_000,
)
```

**核心工具 42 个**(`_HERMES_CORE_TOOLS`,所有平台共享):`terminal` / `process` / `read_file` / `write_file` / `patch` / `search_files` / `web_search` / `web_extract` / `vision_analyze` / `browser_navigate` / `image_generate` / `text_to_speech` / `skills_list` / `skill_view` / `skill_manage` / `todo` / `memory` / `session_search` / `clarify` / `execute_code` / `delegate_task` / `cronjob` / `ha_*`(Home Assistant)/ `kanban_*` / `read_terminal` / `close_terminal` / `browser_*` / `computer_use` 等。

#### 1.2 MCP 支持(深入)

**配置文件**:`~/.hermes/config.yaml` 的 `mcp_servers:` 段(`tools/mcp_tool.py:9-50`),支持 stdio / HTTP / StreamableHTTP / SSE 4 种 transport。启动时 `_discover_and_register_server()` 连接每个 server,列出 tools,`registry.register(toolset="mcp-<server>", ...)` 注入(`tools/mcp_tool.py:5076-5126`)。

**官方 MCP 目录**:`optional-mcps/<name>/manifest.yaml`,4 个预置:blender / linear / n8n / unreal-engine,用 `uvx` 启动,版本钉死(2 周冷却期)。

**MCP OAuth 2.1(项目最特别的亮点)**:`tools/mcp_oauth.py` 完整实现 Authorization Code + PKCE + 动态 client 注册 + loopback callback server,token 持久化到 `~/.hermes/mcp-tokens/<server>.{json,client.json,meta.json}`。带 `expires_at` 绝对时间戳 + 文件 mtime fallback(防进程重启后 `is_token_valid()` 误判)。**整个 `mcp-tokens/` 目录被 `file_safety.py:298-310` 加入 LLM 不可读白名单**。

#### 1.3 Agent Skills(progressive disclosure)

**完全兼容 [agentskills.io](https://agentskills.io) 开源标准**。SKILL.md YAML frontmatter:`name`(≤64)、`description`(≤1024)、`version`、`license`、`platforms`、`metadata.hermes.tags`。3 tier 渐进披露:

1. **Tier 1 元数据**:`skills_list` 只返 name + description(降 token)
2. **Tier 2 全量**:`skill_view(name)` 加载 SKILL.md
3. **Tier 3 链接**:`skill_view(name, file_path="references/api.md")` 按需

**多源扫描**(`agent/skill_utils.py:515-523`):`~/.hermes/skills/`(local)→ `config.yaml:skills.external_dirs`(外部)→ `HERMES_BUNDLED_SKILLS` env → 打包的 `<data>/skills` → `HERMES_OPTIONAL_SKILLS` env。**Meta / VCS 目录自动排除**(`EXCLUDED_SKILL_DIRS = {.git, .github, .hub, .archive, references/, templates/, assets/}`)。

#### 1.4 其他工具类型

- **LSP**(`agent/lsp/`):独立子模块 162K,给 sub-agent 用,**不暴露给 LLM**(和 OpenCode 不同)
- **Plugin 系统**(`plugins/`):19 个插件 —— kanban(多 Agent)、memory(holographic 全息)、model-providers/browser/image_gen/video_gen/cron_providers(可替换实现)、security-guidance/dashboard_auth/disk-cleanup/spotify/teams_pipeline/observability
- **Kanban 工具集**(`tools/kanban_tools.py:1917+`):12 个 tool,**默认只在 `HERMES_KANBAN_TASK` env 启用**(`model_tools.py:368-373`)
- **Home Assistant / Spotify / Feishu / Discord / Yuanbao**:各自一套工具,详细列表见 `toolsets.py:325-360`

---

### Q2. 工具列表的生成、传递、格式

#### 2.1 生成方式 —— 4 步流水线

`model_tools.py:279-479` 的 `get_tool_definitions()`:

1. **解析 enabled/disabled toolsets** → `toolsets.resolve_toolset(name)` 展开成 tool name 列表
2. **平台 bundle 特殊处理**(`model_tools.py:430-454`):`hermes-*` 平台 bundle 和 `coding` posture toolset 只减"非 core"工具
3. **向 registry 取 schemas**:`registry.get_definitions(tools_to_include, quiet=quiet_mode)` 按 check_fn 过滤
4. **动态 schema 修复**:execute_code 的 `SANDBOX_ALLOWED_TOOLS` 重新生成、discord 的 `intent allowlist` 重新生成

**8 entry LRU 缓存** + registry **generation 计数 + config mtime fingerprint**(`model_tools.py:279-329`)—— 长跑 gateway 不会无限增长,但 config 改动或 MCP 动态刷新立即失效。

#### 2.2 传递方式 —— **真正多协议 Provider 无关**

**不是单一协议** —— 同一个 `tool_defs` 列表被多个 adapter 转给不同 LLM:

- **OpenAI / chat_completions**:`agent/auxiliary_client.py:3527、7162、7716` 等,直接 `client.chat.completions.create(tools=tools)`
- **Anthropic / messages**:`agent/anthropic_adapter.py:1668` `convert_tools_to_anthropic()` 把 `{"type":"function","function":{...}}` 转 `[{"name","description","input_schema"}]`
- **Anthropic Bedrock / Vertex / Azure**:`auxiliary_client.py:1351` 同一转换路径
- **Gemini 原生**:`agent/gemini_native_adapter.py`(独立 adapter)
- **Codex Responses**:`agent/codex_responses_adapter.py`

#### 2.3 格式 —— OpenAI 风格 JSON(无 XML,无 prompt-as-tool)

**标准 schema 形态**(`tools/terminal_tool.py:3073-3130`):

```json
{
  "name": "terminal",
  "description": "...",
  "parameters": {
    "type": "object",
    "properties": {
      "command": {"type": "string"},
      "background": {"type": "boolean", "default": false},
      "timeout": {"type": "integer", "minimum": 1}
    },
    "required": ["command"]
  }
}
```

包装成 `{"type":"function","function":{...}}` 传给 LLM。**没有 XML / prompt-as-tool 模式**(和 Cline 形成对比)。

#### 2.4 动态刷新 —— ✅ 完整支持

- **MCP 运行时新增/移除**:`registry._generation` 单调递增 + `invalidate_check_fn_cache()` 显式失效
- **Plugin load**:`register_plugin_override_policy()` 绑定到 `handler.__globals__["__name__"]`
- **Tool Search 渐进式披露**(`tools/tool_search.py`):当 tools 列表 > 10% context window,**自动替换非核心工具为 3 个 bridge 工具** `tool_search` / `tool_describe` / `tool_call` —— LLM 主动按需发现

#### 2.5 toolset alias 二级寻址

20 个平台 bundle(`hermes-cli` / `hermes-telegram` / `hermes-discord` 等)基于 `_HERMES_CORE_TOOLS` 共享核心,只增删平台特有工具。**按场景拼装**,非一长串 enabled_tools 列表。

---

### Q3. 工具调用指令的解析、错误修复、准确性

#### 3.1 解析方式 —— OpenAI `tool_calls` 数组,SDK 直接处理

Hermes **不自己写流式 parser** —— 用 OpenAI Python SDK 的 `client.chat.completions.create(..., stream=True)`,SDK 内部已把 `delta.tool_calls` 增量解析成完整 list(`agent/conversation_loop.py:4610+` 直接消费 `assistant_message.tool_calls`)。**Anthropic 路径**:`anthropic_adapter.py` 把 `content_block_delta.input_json_delta` 流式事件累积成完整 `tool_use` 块,转换回 OpenAI 格式再走同一段 `handle_function_call()`。

#### 3.2 错误修复 —— 6 层防御

**(1) 工具名 hallucination 修复**(`conversation_loop.py:4622-4656`):
```python
for tc in assistant_message.tool_calls:
    if tc.function.name not in agent.valid_tool_names:
        repaired = agent._repair_tool_call(tc.function.name)   # 模糊匹配
        if repaired: tc.function.name = repaired
        else: agent._invalid_tool_retries += 1
        if agent._invalid_tool_retries >= 3: return _final_response
```

**(2) JSON 参数解析失败**(`conversation_loop.py:4696-4715`):修复 `dict`/`list` → 强制 `json.dumps()`,失败时收集到 `invalid_json_args`,**注入 `{"error": "..."}` 作为 tool result**(不破坏 role 交替)。

**(3) 流式截断检测**(`conversation_loop.py:4723-4784`):args 不以 `}` 或 `]` 结尾 → **注入 recovery tool result 让模型自己重发**,不返回部分结果。

**(4) 类型强制修复**(`model_tools.py:656-933` 的 `coerce_tool_args`):
- `"42"` → `42`(int)、`"true"` → `true`(bool)
- `["https://a.com"]`(string) → `["https://a.com"]`(array),**深度递归修复数组/对象内嵌的 JSON 字符串**
- 注释:`# Ported from cline/cline#11803, adapted to hermes-agent's coercion layer.`

**(5) Schema 联合类型剥离**:`tools/schema_sanitizer.py` 把 Anthropic 不接受的顶层 `oneOf`/`allOf`/`anyOf` 剥掉,降级成 `{"type":"object","properties":{}}`。

**(6) Surrogate / lone surrogate 字符清洗**(`conversation_loop.py:988-991`):API 调用前 strip U+D800-U+DFFF,防 Ollama 服务的模型返回 crash `json.dumps()`。

**总结**:**核心哲学是"宁可让模型 agent-correct 下一轮,也不要因为一个 tool call 失败就炸整个 turn"**。

#### 3.3 准确性保证 + 重试上限

| 错误类型 | 上限 | 引用 |
|------|-----|------|
| 无效工具名 | **3 次** | `conversation_loop.py:4642` |
| JSON 解析失败 | 注入 recovery tool result | `conversation_loop.py:4716-4784` |
| 流式截断 | **4 次** continuation | `conversation_loop.py:2010` |
| 普通 length 错误 | **4 次** continuation | `conversation_loop.py:1946` |
| 外层 API 错误 | fallback provider 链 | `auxiliary_client.py:3774+` |

**外层 API 异常自动补 tool error**(`conversation_loop.py:5536-5561`):即使整个 API 轮挂了,所有未回应的 `tool_call_id` 都注入 `{role: "tool", tool_call_id, content: "Error: ..."}`,保证下一轮 messages 满足硬性交替要求。

**Plugin pre-tool hook**(`model_tools.py:1180+` 的 `resolve_pre_tool_block`):插件可在执行前 block/approve,加 1 道防护。

**execute_code 特殊**:`tools/code_execution_tool.py` 允许 LLM 写 Python 脚本**编程式调用其它工具**,**整 turn 只算 1 次 iteration**(`conversation_loop.py:4955-4957` budget refund)。

---

### Q4. 工具执行结果回传

#### 4.1 回传方式 —— OpenAI `role=tool` + `tool_call_id`(`conversation_loop.py:4687-4690、4778-4783`)

```python
messages.append({
    "role": "tool",
    "name": tc.function.name,
    "tool_call_id": tc.id,
    "content": tool_result,    # str
})
```

`tool_call_id` 严格匹配 `tc.id` —— OpenAI 协议要求。**Anthropic 路径**:`convert_messages_to_anthropic()` 在 outbound 阶段把 `role: tool` 转 Anthropic 的 `tool_result` 块(`type: "tool_result"`, `tool_use_id: <tc.id>`)。

#### 4.2 格式 —— JSON 字符串(几乎所有工具)

每个工具 handler 必须返回 **`json.dumps(...)` 字符串**(`tools/registry.py:622+` 的 `_normalize_handler_result` 强校验):
- 成功:`tool_result({"success": True, "data": ...})` → `{"success": true, "data": ...}`
- 失败:`tool_error("file not found")` → `{"error": "file not found"}`(`tools/registry.py:750+`)

**多模态信封**支持(`tools/registry.py:610+`),但 `_normalize_handler_result` 仍转 str。

#### 4.3 通信协议 —— **多协议 Provider 无关**

如 Q2.2 所述,`model_tools.py` 输出 OpenAI 格式 `tools`,**每个 provider adapter 独立负责转换**。`auxiliary_client.py` 里搜 `tools=` 关键字,OpenAI 直接传,Anthropic 先 `convert_tools_to_anthropic()` 再传。

#### 4.4 大结果处理 —— **3 层保护**(`tools/budget_config.py:14-19`)

```python
PINNED_THRESHOLDS = {"read_file": float("inf")}  # 防 persist→read 循环
DEFAULT_RESULT_SIZE_CHARS = 100_000
DEFAULT_TURN_BUDGET_CHARS = 200_000
DEFAULT_PREVIEW_SIZE_CHARS = 1_500
```

- **Layer 1**:工具内部截断(terminal 100K / web_search 100K)
- **Layer 2**:`maybe_persist_tool_result()` 把超出 `max_result_size_chars` 的结果写到 sandbox temp dir(`<env temp>/hermes-results/<tool_use_id>.txt`),LLM 看到 `<persisted-output>...preview...<persisted-output>` 引用
- **Layer 3**:`enforce_turn_budget()` 把单 turn 累计 > 200K 的最大结果也 spill 到磁盘

**图片**:`agent/image_routing.py` 把图片从 tool result 提取,转成下一轮 user message 的 `image_url` 块(多模态喂回)。

---

### Q5. File Backend 是否为工具调用做了适配

**答:做了,而且是"工具调用维度的强结构化"。** 与 `standard/file_backend.md` 高度一致。

| 适配点 | 路径 / 机制 | 证据 |
|------|----------|------|
| **Skills 根目录** | `~/.hermes/skills/` + 外部 dirs + bundled + optional | `hermes_constants.py:1154-1156` |
| **MCP OAuth token 目录** | `~/.hermes/mcp-tokens/<server>.{json,client.json,meta.json}` | `tools/mcp_oauth.py:381-396` |
| **MCP servers 配置** | `~/.hermes/config.yaml` `mcp_servers:` 段 | `tools/mcp_tool.py:9-15` |
| **官方 MCP 目录** | `optional-mcps/<name>/manifest.yaml` | repo 内置 |
| **大结果持久化** | `<env temp dir>/hermes-results/<tool_use_id>.txt` | `tools/tool_result_storage.py:43-45` |
| **可写白名单** | `HERMES_WRITE_SAFE_ROOT` env(多路径,POSIX `:` / Windows `;` 分隔) | `agent/file_safety.py:74-86` |
| **不可读 LLM 凭据目录** | `~/.hermes/mcp-tokens/`、`auth.json`、`.env`、`.anthropic_oauth.json` | `agent/file_safety.py:109-310` |
| **凭证文件权限** | `os.open(..., 0o600)` 主动 chmod 防 race | `agent/anthropic_adapter.py:1179-1184` |
| **Skill auto-exclude** | `.git/`、`.github/`、`.hub/`、`.archive/`、`references/`、`templates/`、`assets/` | `agent/skill_utils.py:27-37` |
| **check_fn 缓存** | 30s TTL + 60s "last-good" grace 防 flake | `tools/registry.py:114-200` |

**全局 vs 项目级**:
- **全局**:`~/.hermes/skills/`、`~/.hermes/mcp-tokens/`、`~/.hermes/config.yaml` —— 主要
- **项目级**:**无**(Hermes 是"个人助手"定位,不跟随 cwd,**没有 `<repo>/.hermes/` 概念** —— 这一点和 Codex/Cline/Gemini CLI 都不一样)
- **外部**:`config.yaml:skills.external_dirs` 声明任意路径

**与 `standard/file_backend.md` 对照**:

| 标准条款 | Hermes 实现 | 对照结果 |
|---------|-----------|------|
| §1.1 用户属主目录 `~/.hermes/` | ✅ | 一致 |
| §1.4 secrets 0o600 + 不可读 | ✅ + LLM 不可读白名单 | **超出** |
| §5.3 secrets 独立 + 0o600 | ✅ + `mcp-tokens/` 0o600 + **目录级** 屏蔽 | **超出** |
| §5.4 LLM 不可读白名单 | ✅(file_safety.py) | **超出标准**(20 项目里只有 Hermes 显式做) |
| §10.8 MCP 协议支持 | ✅(stdio / HTTP / SSE / OAuth 2.1 + PKCE) | **远超** 大多数项目 |

**Onion Agent 启示**:**直接抄 `mcp-tokens/` 目录级 LLM 不可读白名单** —— 这是 Hermes 最强的安全设计细节。

---

## 3. 关键代码片段

### 3.1 工具自注册(`tools/terminal_tool.py:3073-3139`)

```python
TERMINAL_SCHEMA = {
    "name": "terminal",
    "description": TERMINAL_TOOL_DESCRIPTION,
    "parameters": {
        "type": "object",
        "properties": {
            "command": {"type": "string"},
            "background": {"type": "boolean", "default": False},
            "timeout": {"type": "integer", "minimum": 1},
        },
        "required": ["command"]
    }
}

registry.register(
    name="terminal", toolset="terminal", schema=TERMINAL_SCHEMA,
    handler=_handle_terminal, check_fn=check_terminal_requirements,
    emoji="💻", max_result_size_chars=100_000,
)
```

### 3.2 工具名 hallucination 修复(`conversation_loop.py:4622-4656`)

```python
for tc in assistant_message.tool_calls:
    if tc.function.name not in agent.valid_tool_names:
        repaired = agent._repair_tool_call(tc.function.name)  # 模糊匹配
        if repaired:
            tc.function.name = repaired
        else:
            agent._invalid_tool_retries += 1
            if agent._invalid_tool_retries >= 3:
                return _final_response
```

### 3.3 LLM 不可读目录白名单(`agent/file_safety.py:298-310` 摘)

```python
mcp_tokens_dir_name = "mcp-tokens"
hermes_dirs = [_hermes_home_path(), _hermes_root_path()]
for hd in hermes_dirs:
    mcp_tokens = (hd / "mcp-tokens").resolve()
    if resolved == mcp_tokens:
        return f"Access denied: {path} is the Hermes MCP token directory ..."
# 同时拒绝:auth.json, .env, .anthropic_oauth.json
# + ~/.ssh, ~/.aws, ~/.gnupg, ~/.kube, /etc/sudoers, /etc/passwd, /etc/shadow
```

### 3.4 MCP OAuth token 持久化(`tools/mcp_oauth.py:381-396`)

```python
class HermesTokenStorage:
    """File layout:
        HERMES_HOME/mcp-tokens/<server_name>.json         -- tokens
        HERMES_HOME/mcp-tokens/<server_name>.client.json   -- client info
        HERMES_HOME/mcp-tokens/<server_name>.meta.json     -- oauth server metadata
    """
```

---

## 4. 与 Onion Agent 设计的关联

1. **抄 `mcp-tokens/` 目录级 LLM 不可读白名单**(`file_safety.py:298-310`):20 项目中**唯一明确做目录级屏蔽**的方案。Onion 必须把 `~/.onion/secrets/` 和 `~/.onion/mcp-tokens/` 加入 `read_file` 工具的路径白名单拒绝列表,**且 path 解析要 `resolve()` 才能比较**(防符号链接绕过)。

2. **抄 `coerce_tool_args` 类型修复**(`model_tools.py:656-933`):弱模型(DeepSeek、Qwen、GLM)把数字写字符串、把数组 JSON-encode 成字符串是普遍问题。Onion 在 Tool channel 一开始就要把这层 fix 做好。

3. **抄工具集 "narrow waist + edge" 哲学**(`_HERMES_CORE_TOOLS`):核心工具集 30-50 个稳定,所有平台共享;其他按 toolset 增量。**prompt caching 友好**,防止每加 1 个工具就重置 prompt cache。

4. **抄 check_fn TTL + last-good grace 防 flake**(`tools/registry.py:114-200`):任何 `docker version` / `playwright --version` 探测都可能短时挂。30s TTL + 60s last-good grace 是 Hermes production 学到的血泪经验。

5. **简化 3 层持久化**:`tool_result_storage.py` 的 per-tool + per-result + per-turn 三层 spill 看似优雅实际很重。**Onion 可简化成"per-tool cap + 把超出写临时目录 + result 里加引用"两层**。

6. **避免 Hermes 的 OpenAI 协议单边**。Hermes 全押 OpenAI function calling,Anthropic 事后转。**Onion 想做 Provider 无关**,应一开始就让 Tool schema 是 OpenAI 风格,内部用 Adapter pattern 翻译成各 provider 原生格式 —— 抄 Hermes 的 `convert_tools_to_anthropic()` 模式,但**别抄它把 Anthropic 当二等公民**。

7. **Agent Skills(progressive disclosure)直接抄**:`skills/<category>/<name>/SKILL.md` 布局 + `skills_list` 返元数据 + `skill_view` 按需加载,**完全开源的 agentskills.io 标准**。Onion 5 分钟能集成。

---

## 5. 不确定 / 未找到

1. **没有 prompt-as-tool 模式** —— Hermes 全是 OpenAI function calling,XML/Cline-style 完全没有。和 Cline 形成对比。Onion 需不需要 XML 协议?未在源码找到答案。

2. **MCP OAuth 的"非交互环境"行为**未完全确认:`tools/mcp_oauth.py:1163` 提到非交互且无 cached token 时 raise `OAuthNonInteractiveError`,**具体 fallback 路径**(请求人工 vs 直接 fail)没读完。

3. **Tool Search(threshold 10% context window)的真实触发频率**没找到量化数据 —— 实际什么时候进 progressive disclosure 模式?需要 telemetry 才能确认。

4. **不写回 AGENTS.md 字节上限 32 KiB** —— 这点和 Codex / Cline 不同(标准 §9.4)。`file_backend.md` 里已标注这个偏离。

5. **Kanban 工具集的"强制注入"逻辑**(`model_tools.py:368-373`)只在 `HERMES_KANBAN_TASK` env 存在时强制加,但**sub-agent 启 kanban toolset 的具体 dispatcher 路径**没读完。

6. **"动态 schema 修复"的覆盖率**有限:`execute_code` 和 `discord` 有 dynamic rebuild,其它工具(如 kanban 12 个)的 schema 看起来写死。disable 某些 tool 后,kanban schema 里**还会描述已不存在的工具** —— 这个不一致未在源码中找到修复证据。

---

**报告完。** 数据基于 2026-07-13 实时 clone 快照,行号可能在下一次 release 偏移,引用文件名 + 上下文已足够定位。
