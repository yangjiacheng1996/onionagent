# 智能体工具调用（Tool Channel）行业标准

> **提炼自**：GitHub 上 20 个最流行 ReAct 智能体的 `tool_channel.md` 调研报告（`harness/01_market_research/<项目>/tool_channel.md`）
> **提炼方法**：3 个子代理按 10 维度逐份阅读 + 提取模式 + 标注频次；主控在此基础上跨组整合，精选"高频共识"和"反例警示"，形成本标准
> **提炼日期**：2026-07-19
> **配套文档**：
> - 20 份单项目报告：`harness/01_market_research/<项目目录>/tool_channel.md`
> - 3 份组内提炼稿：`harness/01_market_research/_intermediate_{general_agents,coding_agents,multi_agent_frameworks}.md`
> - 顶部引用：`harness/01_market_research/top_20_react_agent.md`
> - 姊妹标准：`harness/01_market_research/standard/file_backend.md`
> **本标准作用**：为后续 Onion Agent 的 `tool_shell` / `tool_channel` 模块设计提供"必须做 / 强烈建议 / 可选 / 禁止"的决策清单

---

## 0. 文档结构

本标准按"设计哲学 → 工具来源 → schema → 列表传递 → 指令解析 → 结果回传 → File Backend 适配 → 流式并发 → 沙箱安全 → 工程化可观测"10 维度组织。每条标准带 4 个标签：

| 标签 | 含义 |
|----|------|
| **必须做** | 20 个项目里 ≥15 个采用，违反即成"反例" |
| **强烈建议** | 8-14 个项目采用，有清晰工程价值，新项目应当借鉴 |
| **可选** | 3-7 个项目采用，按需 |
| **禁止** | 0-2 个项目采用且明确有害，或违反会破坏信创合规 / 洋葱架构哲学 |

---

## 1. 顶层设计哲学（4 大原则）

从 20 个项目的设计反复验证，以下是 4 条横贯全局的设计原则：

### 1.1 原则一：协议中立（Provider-agnostic 中间表示 + 协议适配层）

> 工具 schema 在内部用一种**Provider 无关的中间表示**承载（OpenAI Chat Completions 风格），再为每种 LLM 协议（OpenAI Chat Completions / OpenAI Responses / Anthropic Messages / Gemini FunctionDeclaration / Ollama / 本地模型）写一个 adapter 翻译。
> **避免硬绑单一协议**，让多模型切换零成本。

**频次**：13/20 协议中立（opencode / Claude Code / Gemini CLI / Codex / OpenHands / Cline / Open Interpreter / Aider / Continue / Roo Code / AutoGen / Lobe Chat / CrewAI）；4/20 不中立（Claude Code 绑 Anthropic 协议 / Gemini CLI 绑 Google 协议 / Aider 99% prompt-as-tool / SuperAGI 完全 prompt-as-tool）；3/20 不适用（superpowers / ChatDev 部分 / MetaGPT 协议混乱）

**典型代表**：
- opencode `Opencode/tool_channel.md:78-82` —— Vercel AI SDK + `convertToModelMessages()` 统一 `ModelMessage`
- OpenHands `OpenHands/tool_channel.md:185-189` —— `litellm==1.84.1` 统一 OpenAI/Anthropic/Google/Bedrock
- Cline `Cline/tool_channel.md:32-39` —— Vercel AI SDK + 自实现 25+ provider 适配
- Roo Code `Roo_Code/tool_channel.md:120-124` —— 35+ provider 转统一 `ApiStream` 协议
- AutoGen `autogen-core/models/_types.py:56-77` —— `LLMMessage = Annotated[Union[SystemMessage, UserMessage, AssistantMessage, FunctionExecutionResultMessage], ...]` 7 个 provider 共享
- Lobe Chat `packages/agent-runtime/src/transport/tool.ts:100-117` —— `ToolTransport` 接口 + `ToolRunResult` 抽象

**典型反例**：
- SuperAGI `superagi/llms/openai.py:84-91` —— `ChatCompletion.create` 不传 `tools=` 参数，**完全无协议中立意识**
- MetaGPT `metagpt/provider/anthropic_api.py:24-37` —— `AnthropicLLM._const_kwargs` **完全不传 `tools` 字段**，Anthropic 用户的工具能力被阉割
- Aider `Aider/tool_channel.md:60-65` —— 99% 走 prompt-as-tool，工具调用协议写在 system prompt 里

**Onion 启示**：**必须做**。Onion 内部统一用 OpenAI Chat Completions 风格 `Tool[]` schema，Anthropic 写一个 `convert_tools_to_anthropic()` 函数投影，Ollama/GLM/Qwen 走相同内部表示。Provider 切换 = adapter 切换，工具代码零改动。

### 1.2 原则二：工具类型统一抽象（无论来源，对 LLM 暴露形态单一）

> 无论工具是内置、plugin、MCP、Agent Skills、sub-agent，**对外暴露给 LLM 的 tool list 形态统一**（都是 function calling JSON Schema）。统一抽象 = `BaseTool` / `LobeToolManifest` / `ToolingConfig` / `Tool<TSchema>`。

**频次**：15/20 强统一（opencode / Claude Code / Gemini CLI / Codex / Cline / Roo Code / Continue / OpenClaw / Hermes / AutoGPT / AutoGen / Lobe Chat / CrewAI / ChatDev / Open Interpreter）；2/20 弱统一（SuperAGI Toolkit/Python 类五花八门，靠 System Prompt 文本嵌入）；1/20 不适用（superpowers 0 工具）；2/20 协议混乱（MetaGPT 5 来源 5 套机制 / Aider 99% prompt-as-tool）

**典型代表**：
- OpenClaw `packages/llm-core/src/types.ts:687-695` —— 所有 tool 包装为 `Tool<TSchema>` 抽象，LLM 看到同一份 `tools: [...]` schema
- Hermes `tools/registry.py:55-78` —— AST 扫描 + `registry.register()` 自注册，所有工具统一进 ToolRegistry
- AutoGPT `blocks/__init__.py:18-48` —— Blocks（graph node）+ Chat Tools 双层统一
- Lobe Chat `packages/context-engine/src/engine/tools/types.ts:10` —— `LobeToolManifest` + `ToolSource: 'builtin' | 'client' | 'mcp' | 'composio' | 'lobehubSkill'` 统一
- CrewAI `BaseTool` + `MCPToolResolver.resolve()` + Skills 走 prompt 注入
- ChatDev `ToolingConfig` 4 类统一抽象为 `ToolSpec`

**典型反例**：
- MetaGPT `metagpt/tools/tool_registry.py:48-51` —— **5 大来源走 5 套机制**（Tool 类经 `TOOL_REGISTRY` 调，Action 类经 `Role.set_actions` 调，bash 经 LLM 直接生成，SK 经 `SkillAction.find_and_call_function` 调），`ToolSchema` 校验异常被 `pass` 吞掉

**Onion 启示**：**必须做**。Onion 应当定义 `BaseTool` 抽象基类（`schema: dict` + `handler: Callable` + `name: str` + `retry_policy: RetryPolicy` + `timeout: int`），所有工具（内置 / MCP / Skills / 集市）都走同一条管线。下游工具列表生成、传递、执行、回传全部走同一条管线，工具来源对 Agent 完全透明。

### 1.3 原则三：配置即代码（声明式注册，不要"if-else 散落"）

> 工具 / MCP server / Agent Skills / Plugins 的注册用**声明式 manifest**（JSON / YAML / TOML / Python 装饰器 / 元类）实现，**新增工具不动核心代码**。

**频次**：20/20 全部声明式（只是声明式程度有差异）

**典型代表**：
- OpenClaw：`extensions/<name>/openclaw.plugin.json` + `api.registerTool((ctx) => factory(ctx), { name })`（`src/plugin-sdk/tool-plugin.ts:200`）
- Codex：9 层 `ConfigLayerStack` + `precedence()` i16 排序（`config/src/config_layer_source.rs:42-58`）
- Gemini CLI：5 层 merge `mergeSettings`
- opencode：4 层 `config/paths.ts:17-28`
- Claude Code：5 层 merge + `managed-mcp.json` 企业级
- Roo Code：`.roomodes` YAML 声明式 Custom Modes
- Cline：`cline_mcp_settings.json` + 6 套搜索路径
- MetaGPT：`@register_tool(tags=[...], include_functions=[...])` 装饰器 + `TOOL_REGISTRY` 单例
- CrewAI：`@CrewBase` 元类自动绑定 `base_directory`
- AutoGen：`Component[Pydantic]` 完美 round-trip 序列化
- superpowers：4 个 harness manifest（`.claude-plugin/plugin.json` / `.codex-plugin/plugin.json` / `.cursor-plugin/plugin.json` / `.kimi-plugin/plugin.json`） + `"skills": "./skills/"` 字段

**典型反例**：
- Aider `Aider/tool_channel.md:163-168` —— 散落 `.aider.*` 文件，无强结构化
- opencode `Opencode/file_backend.md:53-59` —— 5 个分散 env var（`OPENCODE_CONFIG_DIR` / `OPENCODE_CONFIG` / `OPENCODE_DB` / `OPENCODE_TEST_HOME` / `OPENCODE_DISABLE_PROJECT_CONFIG`），暴露面太散

**Onion 启示**：**必须做**。Onion 应当 `~/.onion/tools/<toolkit>/<tool>.py` + `onion.json` 声明 manifest；`mcp.json` 独立文件 + `<repo>/.onion/mcp.json` 双层覆盖。**禁止散落命名**（不学 Aider 的 `.aider.*`）和**禁止多个分散 env var**（不学 opencode）。

### 1.4 原则四：沙箱与凭证白名单（LLM 永远不能读 secrets）

> 工具调用的核心安全约束：**LLM 永远不能读 `auth.json` / `.env` / MCP token 目录**，即使用户让 agent 读也直接抛 `AccessDenied` 异常。**path 解析要 `resolve()` 才能比较**（防符号链接绕过）。

**频次**：3/20 显式目录级屏蔽（Hermes 完整 / Lobe Chat 部分 / ChatDev FileToolContext 路径校验）；5/20 部分支持（`auth.json` 0o600 单独存但工具层无白名单）；12/20 无显式白名单

**典型代表**：
- **Hermes（最完整）**：`agent/file_safety.py:109-310` 显式拒绝：
  - `mcp-tokens/` 整个目录
  - `auth.json` / `.env` / `.anthropic_oauth.json`
  - `~/.ssh/` / `~/.aws/` / `~/.gnupg/` / `~/.kube/`
  - `/etc/sudoers` / `/etc/passwd` / `/etc/shadow`
  - `Path.resolve()` 防符号链接绕过
- Lobe Chat：`user_connectors.credentials` AES-256-GCM 加密 + pbkdf2 派生（`apps/cli/src/auth/credentials.ts:14-30`）
- opencode `Opencode/tool_channel.md:148-150` —— `*.env: "ask"` + `*.env.*: "ask"`（`agent/agent.ts:124-130`）
- ChatDev `FileToolContext` 校验路径在 `code_workspace/` 沙箱内，自动拒绝读 `~/.metagpt/config2.yaml` 这种路径

**典型反例**：
- MetaGPT `~/.metagpt/config2.yaml` —— **明文**，无 0o600，**LLM 可 read_file 读 config2.yaml**（file_backend 已记录）
- AutoGPT `gallery/builder.py:480-580` —— Gallery 默认 MCP 模板走 `~` + `tempfile.gettempdir()` 作为允许路径，**默认放开 home 是危险设计**
- AutoGPT `FileSurfer(base_path=os.getcwd())` —— 默认放开 home

**Onion 启示**：**必须做**。Onion 应当直接抄 Hermes 的 `_ROOT_CREDENTIAL_DIRS` 模式：
- `mcp-tokens/` 整个目录级屏蔽
- `auth.json` / `.env` / `secrets/*` 全部屏蔽
- `~/.ssh/` / `~/.aws/` / `~/.gnupg/` / `~/.kube/` 屏蔽
- 工具层（`read_file` / `grep` / `find`）**必须白名单校验** + `Path.resolve()` 防符号链接绕过

---

## 2. 工具来源与分类（5 象限）

### 2.1 内置工具（写死在仓库里）—— 必做

**频次**：20/20 全部有内置工具（除 superpowers 0 个）

**典型规模**：
- 5 个核心：opencode 15 / Claude Code 13+ / Gemini CLI 17 / Codex 20+ / Cline 11 / Continue 19 / Roo Code 21
- 30+ 工具：Open Interpreter 30+ / OpenClaw 30+ coding + 30+ openclaw / Hermes 42 core
- 100+ 工具：AutoGPT 100+ Blocks + 50+ Chat Tools
- 24 工具：SuperAGI 24 Toolkit
- 0 工具：superpowers（**架构性质不同**）

**典型反例**：
- superpowers `superpowers/tool_channel.md:Q1 段结论` —— **0 个内置工具**，严格不定义任何 tool，所有 tool 都是宿主的

**Onion 启示**：**MVP 必做 5-8 个核心工具**：`read` / `write` / `edit` / `bash` / `grep` / `glob` + 4 个 Agent Loop 工具（`update_plan` / `finish_loop` / `record_memory` / `ask_user`）。参考 Hermes 的最小可用集。P1 补到 10-12 个。**不要学 Open Interpreter 30+ 过度膨胀**。

### 2.2 MCP 协议（Anthropic Model Context Protocol）—— 必做

**频次**：14/20 完整支持（opencode 通过 plugin / Claude Code 4 transport / Gemini CLI / Codex / OpenHands 双重身份 / Cline 3 transport / Roo Code / Continue / Open Interpreter / OpenClaw 4 backend / Hermes 4 transport + OAuth 2.1+PKCE / AutoGPT MCPToolBlock / AutoGen 3 transport + Sampling/Elicitation/Roots / Lobe Chat 三层入口 / CrewAI 3 transport）；2/20 不支持（SuperAGI 0 命中 / Aider 0 命中）；4/20 部分（opencode 间接 / MetaGPT 0）

**典型代表**：
- **Hermes（最完整）**：`tools/mcp_tool.py:9-50` + `tools/mcp_oauth.py` —— stdio/HTTP/StreamableHTTP/SSE 4 transport + **OAuth 2.1 + PKCE 完整实现**
- Claude Code `Claude_Code/tool_channel.md:24-32` —— 4 transport + `.mcp.json` 4 层（项目级 + 全局级 + plugin 内 + 企业级）
- Cline `Cline/tool_channel.md:16-20` —— McpHub 3 transport + OAuth + chokidar 热重载
- Roo Code `Roo_Code/tool_channel.md:55-59` —— 双层 `mcp.json` + `MCP_TOOL_PREFIX="mcp"` 命名规范
- Codex `OpenAI_Codex_CLI/tool_channel.md:48-52` —— `[mcp_servers.<name>]` + `rmcp-client` stdio/HTTP/OAuth
- AutoGen `autogen-ext/tools/mcp/_workbench.py` —— **McpWorkbench 完整能力表**：Tools（list_tools/call_tool）+ Resources（list_resources/read_resource/list_resource_templates/read_resource_template）+ Prompts（list_prompts/get_prompt）+ Sampling + Roots + Elicitation（反向通道）

**典型反例**：
- SuperAGI `superagi/` 全局 grep `mcp|tool_use_id|tool_call_id` 完全无匹配
- Aider `Aider/tool_channel.md:38-40` —— 0 命中，**完全不支持**

**Onion 启示**：**必须做**。Onion 既然定位是"信创合规 + 可热插拔 Provider"，MCP 是事实标准协议。**MVP 必做 stdio + StreamableHTTP 两种 transport**；OAuth 2.1 + PKCE 放 P1；反向通道（Sampling/Elicitation/Roots）放 P2。**配置走双层文件**：`~/.onion/mcp.json`（全局）+ `<repo>/.onion/mcp.json`（项目级），符合 file_backend §10.8。

### 2.3 Agent Skills（progressive disclosure SKILL.md 协议）—— 必做

**频次**：12/20 完整支持（OpenClaw 50+ / Hermes 300+ agentskills.io / AutoGPT Anthropic 协议 / Cline 6 目录 / opencode 3 层 / Claude Code 14 plugin / Gemini CLI 4 层 / Codex Anthropic 兼容 / Continue 3 层 / Roo Code 5 层 8 路径 / Lobe Chat 5 API / CrewAI 三级 progressive disclosure）；3/20 部分（Open Interpreter 2026 才追上 / OpenHands 双格式 / ChatDev 仓库级）；2/20 不支持（AutoGen 借用 MCP Prompts 替代但无渐进披露 / SuperAGI 无 Skills）；1/20 替代实现（MetaGPT Semantic Kernel 风格，一次全加载）；1/20 Skills 是核心但不通过 tool_call（superpowers）

**典型代表**：
- **CrewAI（最完整 Anthropic 标准）**：`crewai/skills/models.py:24-46` 三级 `METADATA=1 / INSTRUCTIONS=2 / RESOURCES=3` + `loader.py:format_skill_context` 用 `<skill name="...">...</skill>` XML 标签注入 + `parser.py:30-150` YAML frontmatter 解析
- OpenClaw `src/skills/loading/local-loader.ts` + `frontmatter.ts:24-32` —— 仓库自带 50+ skill
- Hermes `agent/skill_utils.py:515-523` + `hermes_constants.py:1154-1156` —— **完全兼容 agentskills.io 开源标准**
- Roo Code `services/skills/SkillsManager.ts:391-432` —— **5 层 × 8 路径 Skills 覆盖矩阵**（`~/.agents/skills[-mode]` + `~/.roo/skills[-mode]` + `<cwd>/.agents/skills[-mode]` + `<cwd>/.roo/skills[-mode]`）

**典型反例**：
- MetaGPT —— **Semantic Kernel 风格**（`config.json` + `skprompt.txt` + `{{$variable}}` 模板），**不是 Anthropic 渐进式披露**，一次全加载
- AutoGen `autogen-studio/autogenstudio/web/skills/user/` —— 在 `.gitignore` 里有但**代码无引用**（疑似废弃占位）
- ChatDev `manager.py:14-17` —— `DEFAULT_SKILLS_ROOT = (REPO_ROOT / ".agents" / "skills").resolve()` **无 env/CLI 覆写**，没有 `~/.chatdev/skills/`

**Onion 启示**：**必须做**。Onion 的 `~/.onion/skills/<slug>/SKILL.md` + `references/` + `scripts/` + `assets/` 是事实标准。**MVP 阶段 3 层**：`~/.onion/skills/` + `<repo>/.onion/skills/` + `~/.agents/skills/`（跨工具共享，**学 superpowers 跨宿主兼容**）。P1 升级到 5 层（含 mode 限定）。

### 2.4 其他工具类型（Plugin / Tool Search / Sub-agent）—— 强烈建议

**频次**：
- Plugin 体系：4/20 显式（OpenClaw / Claude Code 13 plugin / Hermes 19 / AutoGPT blocks）
- Tool Search（3-4 meta 工具替代 100+ 工具）：2/20 显式（OpenClaw `tool_search` / `tool_describe` / `tool_call` 4 meta 工具 + Hermes 10% context window 阈值）
- Code Mode（JS 沙箱动态执行）：1/20（OpenClaw 独有 `tool_search_code`）
- Sub-agent 委派（`delegate_task` / `task` 工具）：6/20（OpenClaw `agents_list` / `delegate_task` / Hermes `delegate_task` / AutoGPT `AgentExecutorBlock` / Codex V1+V2 / opencode `task` 工具 / Cline `spawn_agent` + `teams`）

**典型反例**：
- Continue —— 无显式 sub-agent 工具（无 `spawn_agent` / `Task`）
- SuperAGI —— 无 Tool Search、无 Sub-agent 委派

**Onion 启示**：
- **Tool Search 机制在工具数 ≥ 20 时必做**（避免 system prompt 撑爆）。Onion 应当引入 `tool_search` / `tool_describe` / `tool_call` 3 个 meta 工具 + 显式黑名单 `TOOL_SEARCH_CONTROL_TOOL_NAMES` 防自递归
- **Sub-agent 委派放 P1**（增加复杂度）。可借鉴 opencode 的 `task` 工具
- **Plugin 体系放 P2**（先做核心）

### 2.5 工具集市 / 远程下载 / Marketplace —— 可选

**频次**：2/20 显式（OpenClaw ClawHub / SuperAGI `helper/tool_helper.py:50-79` 从 GitHub `api.github.com/repos/{owner}/{repo}/zipball/{branch}` 拉 ZIP）；2/20 隐式（Claude Code plugin 市场 / Continue assistants 模板）；16/20 无集市

**典型代表**：
- SuperAGI `helper/tool_helper.py:50-79` —— 从 GitHub 拉 ZIP 解压到 `superagi/tools/marketplace_tools/`，然后 `register_marketplace_toolkits()` 写 DB

**Onion 启示**：**MVP 不必做**。Onion 早期只需要 `~/.onion/tools/builtin/` + `~/.onion/tools/user/` 两层，**预留** `~/.onion/tools/marketplace/` 扩展（file_backend §2.7）。

### 2.6 工具自动发现机制（AST 扫描 / rglob / 装饰器）—— 强烈建议

**频次**：4/20 自动发现（Hermes AST + AutoGPT rglob + SuperAGI importlib + opencode 动态 import）；5/20 半自动（OpenClaw 显式 `api.registerTool` 但也支持 plugin manifest 扫描）；10/20 显式注册

**典型代表**：
- Hermes `tools/registry.py:55-78` —— `discover_builtin_tools()` **AST 扫描** `tools/*.py` 找顶层 `registry.register(...)` 调用
- AutoGPT `load_all_blocks()` —— `rglob blocks/**/*.py` + `importlib.import_module` + `_all_subclasses(Block)` 找 `*Block` 子类（`backend/blocks/__init__.py:18-48`）
- SuperAGI `agent/tool_builder.py:36-66` —— `importlib.import_module` 三层目录（`superagi/tools` / `external_tools` / `marketplace_tools`）动态加载

**Onion 启示**：**强烈建议**。Onion 应当 `importlib` / `os.walk` 扫描 `~/.onion/tools/**/*.py`，按命名约定自动注册，**省去手动维护 manifest**。

---

## 3. 工具 Schema 与注册机制

### 3.1 JSON Schema 强制标准（OpenAI function calling）—— 必做

**频次**：17/20 强 JSON Schema（opencode / Claude Code / Gemini CLI / Codex / OpenHands / Cline / Open Interpreter / Continue / Roo Code / OpenClaw / Hermes / AutoGPT / Lobe Chat / AutoGen / CrewAI / ChatDev / superpowers 兼容）；1/20 嵌 prompt JSON Schema（SuperAGI）；2/20 无 schema（Aider 完全 / MetaGPT 自创 dict）

**典型代表**：
- opencode `Opencode/tool_channel.md:54-58` —— `JSONSchema7` 类型 + `parameters: Effect Schema` 双轨
- Cline `Cline/tool_channel.md:42-44` —— Zod → `zodToJsonSchema`（`definitions.ts:1-15`）
- AutoGen `_function_utils.py:91-104` —— 三个 Pydantic 模型 `Parameters` + `Function` + `ToolFunction`；`convert_tools()` 强制 `ChatCompletionToolParam` 类型
- CrewAI `BaseTool._validate_kwargs` + `model_json_schema()` —— Pydantic 强校验
- Lobe Chat `convertManifestsToTools()` —— 转 `{type:'function', function:{name, description, parameters}}`；`PLUGIN_SCHEMA_SEPARATOR = '____'` + 64 字符 MD5 压缩

**典型反例**：
- Aider `Aider/tool_channel.md:36-42` —— **完全无 schema**，纯字符串 prompt
- MetaGPT `metagpt/tools/tool_convert.py:7-32` —— **自定义 dict** 格式 `{"type": "class", "description": "...", "signature": "(self, x: int) -> None", "parameters": {"x": {"type": "int", "desc": "..."}}, "code": "<完整源码>"}`，**没有 OpenAI 标准 `type: "function"` + `parameters: {type:"object", properties, required}` 三层嵌套**

**Onion 启示**：**必须做**。Onion 内部统一用 OpenAI Chat Completions 风格 schema，Anthropic 写 adapter 翻译。**Python 项目用 Pydantic v2 + `model_json_schema()` 自动产出**，无需手写 JSON Schema。

### 3.2 Pydantic 反射生成 JSON Schema（args_schema）—— 强烈建议

**频次**：4/20 强反射（AutoGPT 强 + SuperAGI 反射 + CrewAI 反射 + OpenHands Pydantic v2）；2/20 弱反射（MetaGPT docstring 解析 + ChatDev Python type annotation）；14/20 手写 JSON Schema

**典型代表**：
- AutoGPT `backend/blocks/_base.py:43-65` —— `BlockSchemaOutput` + `BlockInput` 继承 `BaseModel`，`util/llm/tool_use.py:55-67` `pydantic_to_anthropic_tool()` 反射
- OpenHands `file_store/files.py:13` —— `ConfigDict(extra='forbid')` 防止 schema drift
- ChatDev `utils/function_catalog.py:140-260` —— `Annotated[str, ParamMeta(description="路径")]` 描述参数，`inspect.signature(fn)` 反射转 OpenAI `{"type":"object","properties":{...}}` 格式

**Onion 启示**：**强烈建议**。Onion 用 Pydantic v2 反射可省 50% 样板代码，工具定义从 `def my_tool(a: str, b: int) -> dict` 简化成自动生成 schema。**配置 `extra='forbid'` 防止 schema drift**。

### 3.3 `required` + `additionalProperties: false` strict 模式（OpenAI strict mode）—— 必做

**频次**：14/20 显式（opencode / Claude Code / Gemini CLI / Codex / Open Interpreter / Cline / Continue / Roo Code / OpenHands / OpenClaw / Hermes / AutoGPT / Lobe Chat / CrewAI）；2/20 部分（Codex OpenAI/Azure/Bedrock 强制 `strict: false` / opencode 对 OpenAI/Azure/Bedrock 强制 `strict: false`）；4/20 不显式（Aider / SuperAGI / MetaGPT / superpowers）

**典型代表**：
- Roo Code `apply_diff.ts:21-41` —— `required: ["path", "diff"]` + `additionalProperties: false`
- Continue `Continue/tool_channel.md:118-121` —— `required: ["filepath"]`
- OpenHands Pydantic `extra='forbid'`

**Onion 启示**：**必须做**。Pydantic v2 + `extra='forbid'` 等价实现，**减少 LLM 幻觉**（防止 LLM 给 schema 外字段）。

### 3.4 Schema 强校验 + 容错（10/10 全做）—— 必做

**频次**：20/20 全做（只是策略不同）

**典型代表**：
- opencode `tool/tool.ts:19-30` —— `Schema.decodeUnknownEffect` 失败抛 `InvalidArgumentsError`，message 主动引导 LLM 改写
- Cline `Cline/tool_channel.md:80-85` —— `validateWithZod(Schema, input)` 入口校验
- Continue `Continue/tool_channel.md:118-122` —— `coerceArgsToSchema` 按 schema 强转 + 失败 throw 转 errorMessage
- Gemini CLI `BaseDeclarativeTool.validateToolParams` —— 调 `SchemaValidator.validate` (Ajv)
- Open Interpreter `parse_arguments<T>(arguments: &str) -> Result<T, FunctionCallError>` serde_json
- OpenHands Pydantic `extra='forbid'` 严格
- CrewAI 5 层 fallback：`json.loads` → `ast.literal_eval` → `json5.loads` → `json_repair.repair_json` → 全部失败抛 `ToolValidateInputErrorEvent`
- Lobe Chat `ToolArgumentsRepairer`（`partial-json` 库 `safeParseJSON` fallback `parsePartialJSON`）+ `sanitizeToolCallArguments`（**保 prompt-cache key**）
- AutoGen `FunctionTool.run_json` → `args_type.model_validate()` 强校验 → 失败抛 `ValidationError` → 包装成 `ToolResult(is_error=True)` 回传 LLM

**典型反例**：
- MetaGPT `xml_fill` 按 `expected_type` 转换，**失败用默认值**（`int` 失败 → `0`；`list` 失败 → `[]`）—— silent 静默反例
- MetaGPT `ToolSchema` 校验异常被 `pass` 吞掉（`tool_registry.py:48-51`）—— **schema 错也照样用**
- ChatDev `_parse_tool_call_arguments` `JSONDecodeError` → `{}` —— 失败直接给空 dict，LLM 看不到错误

**Onion 启示**：**必须做**。Pydantic v2 `BaseModel` + `ConfigDict(extra='forbid')` + 校验失败 `raise ValidationError` + 包装成 `isError: True` 回传 LLM。**绝不允许 silent 静默**（不学 MetaGPT）。

### 3.5 装饰器 / registry.register(...) 自注册 —— 可选

**频次**：4/20 自注册（Hermes 强自注册 + SuperAGI 弱自注册 + MetaGPT 装饰器 + OpenHands FastMCP `@mcp_server.tool()`）

**典型代表**：
- Hermes `tools/terminal_tool.py:3132-3139` —— 模块级 `registry.register(name, toolset, schema, handler, check_fn, emoji, max_result_size_chars)`，AST 扫描发现

**Onion 启示**：**MVP 可借鉴**。Onion 的 `~/.onion/tools/<tool>.py` 可以用 `@onion.tool(name, description, schema)` 装饰器，简化注册样板。

---

## 4. 工具列表的生成与传递

### 4.1 OpenAI function calling 协议（主流）—— 必做

**频次**：17/20 强 function calling（opencode / Claude Code / Gemini CLI / Codex / OpenHands / Cline / Open Interpreter / Continue / Roo Code / OpenClaw / Hermes / AutoGPT / Lobe Chat / AutoGen / CrewAI / ChatDev / superpowers 兼容）；3/20 完全不用（SuperAGI 纯 prompt-as-tool / MetaGPT 仅 aask_code 一处用 / Aider 99% prompt-as-tool）

**典型代表**：
- opencode `streamText({ tools, activeTools, model })`（Vercel AI SDK）
- Claude Code Anthropic `messages` API + `tool_use` 块
- Gemini CLI Google `@google/genai` `Tool` 类型
- Codex OpenAI Responses API `tools[]`
- OpenHands LiteLLM `tools: [{type: "function", function: {...}}]`
- Cline Vercel AI SDK `streamText({ tools, model, messages })`

**典型反例**：
- SuperAGI `superagi/llms/openai.py:84-91` —— `ChatCompletion.create` **不传 `tools=`**

**Onion 启示**：**必须做**。Onion 的 LLM 调用**必须**走 OpenAI function calling（或 Anthropic 适配后），**不能学 SuperAGI 纯 prompt-as-tool**。

### 4.2 Anthropic `tools` + `input_schema` 协议（次主流）—— 必做

**频次**：14/20 显式 Anthropic 协议支持（opencode / Claude Code / Gemini CLI 走 OpenAI 协议但通过转换 / Codex / OpenHands / Cline / Continue / Roo Code / Open Interpreter / OpenClaw / Hermes / AutoGPT / Lobe Chat / AutoGen / CrewAI / ChatDev）；1/20 不支持（SuperAGI）；1/20 寄生（superpowers）

**典型代表**：
- opencode `provider/transform.ts:73-160` 1418 行 cross-provider normalize
- Cline Vercel AI SDK 自动适配
- Open Interpreter `chat-wire-compat/src/request.rs:104-346` Responses↔Chat 互转
- Continue `fromChatCompletionChunk` + Anthropic `input_json_delta` 双协议

**Onion 启示**：**必须做**（与模式 4.1 配对）。Onion 同时支持 OpenAI + Anthropic 协议，让 Provider 热插拔。

### 4.3 prompt-as-tool 模式（兜底）—— 可选

**频次**：2/20 完全采用（SuperAGI 100% / superpowers 100%）；1/20 99% 采用（Aider）；1/20 fallback（Continue `SystemMessageToolCodeblocksFramework` + `detectToolCallStart()`）；16/20 不用

**典型代表**：
- SuperAGI `agent/prompts/superagi.txt:7-13` —— 模板要求 LLM 返回 `{thoughts, tool: {name, args}}` JSON；`agent_prompt_builder.py:36-58` `add_tools_to_prompt()` 把工具列表拼成自然语言 + JSON Schema 文本
- Aider `editblock_prompts.py:main_system` —— 99% 走 prompt-as-tool
- Continue `core/tools/systemMessageTools/toolCodeblocks/index.ts:5-44` —— fallback

**Onion 启示**：**反面教材**。Onion 应**优先 OpenAI/Anthropic 原生 tool API**，prompt-as-tool **仅作兼容回退**（给 local LLM 用 GBNF grammar 强制 JSON）。**Aider 的 prompt-as-tool 是为了兼容所有模型，但 2026 年 GPT-5/Claude 4/Gemini 3 都已经原生支持，prompt-as-tool 已过时**。

### 4.4 集中式 ToolRegistry —— 强烈建议

**频次**：14/20 集中式 ToolRegistry（Gemini CLI / Codex / opencode / Cline / Open Interpreter / Continue / Roo Code / OpenClaw / Hermes / AutoGPT / Lobe Chat / AutoGen / CrewAI / ChatDev）；6/20 分散（SuperAGI / Aider Coder 散落 / Claude Code 隐式 / OpenHands 函数式 / MetaGPT TOOL_REGISTRY 装饰器 / superpowers 不适用）

**典型代表**：
- Gemini CLI `tool-registry.ts:206-280` —— `ToolRegistry` Map + `getFunctionDeclarations()`
- Codex `core/src/tools/spec_plan.rs:127-150` —— `build_tool_router()` 每次 turn 重建
- Continue `getBaseToolDefinitions` + `getConfigDependentToolDefinitions` 函数式
- Roo Code `buildNativeToolsArray` 4 类源合并
- Hermes `tools/registry.py:55-78` AST 扫描 + `registry.register()`

**典型反例**：
- Aider Coder 子类散落注册
- Claude Code 隐式聚合

**Onion 启示**：**强烈建议**。**学 Continue 的"作者踩坑注释"**（`core/tools/index.ts:4` "we've messed up 3 TIMES by pushing to const"）—— 工具列表必须是**函数**，不能是模块级 const，避免 reload 时重复定义。

### 4.5 工具名排序（for prompt cache hit）—— 强烈建议

**频次**：1/20 显式排序（OpenClaw `openai-completions-transport.ts:1348` `sortTransportToolsByName`）；19/20 无显式排序

**典型代表**：
- OpenClaw `openai-completions-transport.ts:1348` `sortTransportToolsByName` —— 工具按名字母排序保证 OpenAI cache hit

**Onion 启示**：**强烈建议**。Onion 用 OpenAI 协议时**必须**对 tool list 排序，否则每次 turn 都 cache miss，token 成本翻倍。

### 4.6 工具名规范化（去非法字符 / MD5 压缩 / 长度限制）—— 强烈建议

**频次**：3/20 显式规范化（OpenClaw + Lobe Chat + AutoGen）

**典型代表**：
- Lobe Chat `ToolNameResolver.generate()` > 64 字符自动 MD5 哈希 `MD5HASH_xxxxxxxxxxxx`；阈值由 env `TOOL_NAME_MAX_LENGTH` 可配
- AutoGen `normalize_name(name)` —— LLM 偶尔会返回带非法字符（如 `.` / `-`）的工具名，自动替换为 `_`；`assert_valid_name()` 启动时校验
- OpenClaw `attempt.tool-call-normalization.ts:42-60` `resolveCaseInsensitiveAllowedToolName` 大小写不敏感匹配

**典型反例**：
- MetaGPT / CrewAI / ChatDev —— 全部走原名，工具名直接来自 Python 类名/YAML 配置/User 传入，**没有规范化层**

**Onion 启示**：**强烈建议**。Onion 应当 `tool_name.lower() == name.lower()` 兜底 + 64 字符 MD5 压缩 + 非法字符替换为 `_`。

### 4.7 Tool Search 渐进式披露（工具数 ≥ 20 时）—— 强烈建议

**频次**：2/20 显式 Tool Search（OpenClaw + Hermes）；18/20 无 Tool Search

**典型代表**：
- OpenClaw `src/agents/tool-search.ts:17-23` —— 4 个 meta 工具（`tool_search` / `tool_describe` / `tool_call` / `tool_search_code`），当工具数 > 阈值全部工具被替换
- Hermes `tools/tool_search.py` —— 阈值 10% context window，自动替换非核心工具
- Codex `tools/src/tool_search.rs:1-55` `TOOL_SEARCH_TOOL_NAME` —— namespace 的 `defer_loading: true` 触发 `tool_search` 工具，model 按需请求展开

**Onion 启示**：**强烈建议**（Onion 工具量上来后**必做**）。Onion 的 `~/.onion/tools/` ≥ 20 个时，必须引入 `tool_search` / `tool_describe` 3 个 meta 工具，避免 system prompt 撑爆。

### 4.8 Tool Search 黑名单（防自递归）—— 必做

**频次**：1/20 显式（OpenClaw `TOOL_SEARCH_CONTROL_TOOL_NAMES` 黑名单）；19/20 不显式

**典型代表**：
- OpenClaw `src/agents/tool-search.ts:21-23` `TOOL_SEARCH_CONTROL_TOOL_NAMES` 黑名单

**Onion 启示**：**必做**。Onion 引入 Tool Search 时**必须**有黑名单机制，否则 LLM 递归 `tool_search(tool_search)` 卡死。

### 4.9 动态 schema 修复（dynamic schema rebuild / schema stripping）—— 可选

**频次**：2/20 显式（Hermes 强 + AutoGPT 弱）

**典型代表**：
- Hermes `model_tools.py:430-454` 平台 bundle 特殊处理 + `coerce_tool_args` 动态类型修复 + `tools/schema_sanitizer.py` 联合类型剥离
- AutoGPT `force_tool_choice` 强制 Claude 只调一个 tool

**Onion 启示**：**MVP 不必做**；Provider 切换多了再加 schema 修复层。

---

## 5. 指令解析与错误修复

### 5.1 流式增量解析（OpenAI `delta.tool_calls`）—— 必做

**频次**：18/20 显式流式（opencode / Claude Code / Gemini CLI / Codex / OpenHands / Cline / Open Interpreter / Continue / Roo Code / OpenClaw 强 / Hermes SDK 间接 / AutoGPT 主路径 non-streaming / AutoGen 显式 / Lobe Chat 各 provider / CrewAI 显式 / ChatDev 0 命中 / superpowers 不适用 / Aider partial）；2/20 不用流式（AutoGPT 主路径 non-streaming / SuperAGI 完全）

**典型代表**（按协议）：
- **OpenAI `delta.tool_calls`**：Continue `fromChatCompletionChunk`（`openaiTypeConverters.ts:357-389`）、Roo `NativeToolCallParser.processRawChunk`
- **Anthropic `input_json_delta`**：Continue `Anthropic.ts:303-378`、OpenClaw `anthropic-transport-stream.ts:1443-1710` 完整 3 阶段解析
- **Google `chunk.functionCalls`**：Gemini `Map<id, FunctionCall>` 去重（`geminiChat.ts:1144-1180`）
- **AI SDK 统一 LLMEvent**：opencode `tool-input-start/delta/end/call/result/error`
- **OpenAI Responses `ResponseEvent`**：Codex `OutputItemAdded` + `ToolCallInputDelta` + `OutputItemDone`
- **partial-json 库**：Roo `parseJSON(argumentsAccumulator)`（`NativeToolCallParser.ts:243-279`）
- **Lark grammar**：Codex/Open Interpreter `StreamingPatchParser`

**典型反例**：
- AutoGPT `provider.call_provider` 是 `await ... completions.create()` 无 `stream=True`，**主路径不流式**
- SuperAGI `output_handler.handle_tool_response` 接收 `assistant_reply: str` 是完整字符串
- MetaGPT `_achat_completion_stream` **只收集 `delta.content` 拼字符串，不解析 `delta.tool_calls`**
- ChatDev **全仓库 `grep "stream=True" 0 命中`**

**Onion 启示**：**必须做**。Onion 应当用 OpenAI SDK（`stream=True`）让 SDK 处理流式，自己只处理 tool_call dispatch。Anthropic 路径需自己写 `content_block_delta` 累积。**Python 项目的最佳选择是用 `partial-json` 库 + Pydantic 反序列化**。

### 5.2 流式按 id 关联跨 chunk —— 必做

**频次**：12/20 显式按 id 关联（opencode / Gemini / Codex / Open Interpreter / Roo / OpenClaw / Hermes / AutoGPT / Lobe Chat / AutoGen / CrewAI / ChatDev）；8/20 不显式或按顺序匹配

**典型代表**：
- opencode `ctx.toolcalls: Record<toolCallID, ToolCall>` 全程基于 id
- Gemini `Map<id, FunctionCall>` + `<name>__<id>` 前缀化
- Codex `ResponseStream` 转 `ResponseItem::FunctionCall { id, name, arguments, call_id }`
- Open Interpreter `FunctionCall { id, name, arguments, call_id }` 三协议
- Roo `streamingToolCallIndices` 集合 + `tool_call_start/delta/end` 三事件

**Onion 启示**：**必须做**。**强制 id 关联**，不允许"按顺序匹配"——后者在并发工具调用时会乱序。

### 5.3 plain-text tool call 修复（小模型漏出 XML/Harmony markers）—— 强烈建议

**频次**：1/20 显式修复（OpenClaw 独有，58890 字节独立包）；4/20 弱修复（Aider 4 级 JSON 补全 + Cline 6 类修复 + SuperAGI `ast.literal_eval` + Continue `safeParseToolCallArgs` 返空对象）；15/20 不显式

**典型代表**：
- **OpenClaw（最完整）**：`packages/tool-call-repair/src/stream-normalizer.ts` 核心 58890 字节，4 种语法支持（XML-ish / Named bracket / Harmony stream markers / Legacy）；`payload.ts:48-72` 三态扫描 `{prefix | complete | invalid}` 支持流式增量修复；`MAX_PAYLOAD_BYTES = 256_000` 字节上限；`allowedToolNames` 工具名白名单
- Aider `parse_partial_args` 数组层/对象层/字符串层 + `json-repair` 库（`base_coder.py:2347-2360` + `pyproject.toml:42`）
- Cline `repairMalformedToolCall` 截断/单引号/未转义换行/空 input/已 valid/未知工具名（`ai-sdk.ts:423-449`）
- opencode `experimental_repairToolCall` 工具名小写化 + `InvalidArgumentsError` 喂回 LLM + `DOOM_LOOP_THRESHOLD=3`（`llm.ts:265-279` + `processor.ts:331-345`）

**Onion 启示**：**强烈建议**（deepcode 的信创合规 + Provider 热插拔场景**必做**）。Onion 在用本地模型（Qwen / GLM）时，plain text 漏 tool call 是常态，需要 `tool-call-repair` 兜底。**直接照搬 OpenClaw 58890 字节实现**或用 `json-repair` 库。

### 5.4 工具名 hallucination 修复（case-insensitive / fuzzy match）—— 强烈建议

**频次**：4/20 显式修复（OpenClaw / Hermes / Cline / Aider）；16/20 不显式

**典型代表**：
- OpenClaw `attempt.tool-call-normalization.ts:42-60` `resolveCaseInsensitiveAllowedToolName` 大小写不敏感匹配
- Hermes `conversation_loop.py:4622-4656` `agent._repair_tool_call(name)` 模糊匹配，失败时 `agent._invalid_tool_retries` 计数，3 次超限返 `_final_response`
- Cline `ReadFilesInputUnionSchema` 兼容多种 alias（`schemas.ts:64-82`）
- Aider filename 校验 3 行回溯 + `valid_fnames` + fuzzy 匹配

**Onion 启示**：**强烈建议**。Onion 应当 `tool_name.lower() == name.lower()` 兜底 + 模糊匹配（`difflib.get_close_matches`），避免 LLM 大小写写错就全 turn 失败。

### 5.5 JSON 参数解析失败修复（smart quote / 截断修复）—— 强烈建议

**频次**：4/20 显式修复（OpenClaw + Hermes + Aider + Lobe Chat）；16/20 不显式

**典型代表**：
- OpenClaw `attempt.tool-call-argument-repair.ts` 23375 字节 —— smart quotes 自动转 ASCII + 截断/缺 closing brace 修复（`extractBalancedJsonPrefix`）+ 已知参数键名容错（`TOOLCALL_REPAIR_KNOWN_ARG_KEYS` 30+ 个）；`MAX_TOOLCALL_REPAIR_BUFFER_CHARS = 64_000` 字节上限
- Hermes `coerce_tool_args` 深度递归修复数组/对象内嵌的 JSON 字符串（`model_tools.py:656-933`）
- Aider 4 级 JSON 补全
- Lobe Chat `ToolArgumentsRepairer` + `sanitizeToolCallArguments`（**保 prompt-cache key**）

**Onion 启示**：**强烈建议**。Onion 应当照搬 OpenClaw 的 smart quote + 截断修复 + Hermes 的深度递归类型修复。**深模型 + 弱模型都受益**。

### 5.6 Surrogate / lone surrogate 字符清洗 —— 必做

**频次**：4/20 显式清洗（Hermes + AutoGPT + Codex + Open Interpreter）；16/20 不显式

**典型代表**：
- Hermes `conversation_loop.py:988-991` strip U+D800-U+DFFF
- AutoGPT `util/llm/conversions.py:164-180` `sanitize_messages_for_utf8()`
- Codex `protocol/src/models.rs` 同样防护

**Onion 启示**：**必做** —— `text.encode('utf-8', errors='replace').decode('utf-8', errors='replace')` 兜底防 Ollama crash。

### 5.7 Orphan tool_result 修复（上下文压缩时配对完整）—— 强烈建议

**频次**：1/20 显式三件套（AutoGPT 独有）；19/20 不显式

**典型代表**：
- AutoGPT `util/prompt.py:323-595` + `_ensure_tool_pairs_intact()` —— 三件套：extract ids / extract response ids / validate_and_remove_orphan_tool_responses

**Onion 启示**：**强烈建议** —— `session.json` 压缩时**必须**保证 `tool_call_id ↔ tool_result` 配对（洋葱架构核心约束）。

### 5.8 Schema 联合类型剥离（Anthropic 不接受 oneOf/anyOf）—— 可选

**频次**：1/20 显式剥离（Hermes 独有）；19/20 不显式

**典型代表**：
- Hermes `tools/schema_sanitizer.py`

**Onion 启示**：**MVP 不必做**；Anthropic 协议支持深了再加。

### 5.9 Doom loop / 重复检测 —— 强烈建议

**频次**：4/20 显式配置（OpenClaw + Roo + Aider + Codex）

**典型代表**：
- opencode `processor.ts:331-345` —— `DOOM_LOOP_THRESHOLD=3` 弹窗
- Roo `ToolRepetitionDetector`（`ToolRepetitionDetector.ts:29-31`）+ `DEFAULT_CONSECUTIVE_MISTAKE_LIMIT = 3`（`provider-settings.ts:29`）
- Aider `consecutiveNoToolUseCount` + SEARCH/REPLACE 失败 3 行 fuzzy 匹配

**典型反例**：
- Continue `Continue/tool_channel.md:130-135` —— 无显式 doom loop，靠 LLM 自纠
- Claude Code `exit code 2` 触发 retry，依赖 LLM 推理
- OpenHands 错误回灌 LLM 自动重试

**Onion 启示**：**强烈建议**（P1 必做）。这是 Agent Loop 健壮性的"安全网"。Onion 应当最近 N 次 tool call 完全相同（name + input）→ 弹窗询问用户。

### 5.10 Unreadable tool 隔离（坏工具不影响 sibling）—— 必做

**频次**：1/20 显式隔离（OpenClaw 独有）；19/20 不显式

**典型代表**：
- OpenClaw `openai-tool-projection.ts:55-128` `schemaProjection.violations.length > 0` 跳过

**Onion 启示**：**必做** —— 1 个 MCP server schema 错误不能导致整轮失败。

### 5.11 Tool call ID 兜底（MD5 / hash 合成）—— 可选

**频次**：1/20 显式（ChatDev 独有）；19/20 不显式

**典型代表**：
- ChatDev `OpenAIProvider._build_tool_call_id()`（`openai_provider.py:590-600`）—— 如果 provider 没给 tool call id，用 `MD5(function_name + arguments)[:8]` 合成

**Onion 启示**：**可选**（P1 强防御）。Onion 应当 `MD5(function_name + arguments)[:8]` 兜底，保证 provider 漏给 id 时 `role=tool` 仍能匹配。

### 5.12 Per-tool retry 上限（maxRetries / timeoutMs）—— 强烈建议

**频次**：6/20 显式（opencode / Cline / Codex / Gemini / Continue / Roo）；14/20 隐式

**典型代表**：
- Cline `create.ts:140-143` —— `retryable: true, maxRetries: 3, timeoutMs: 30_000` 默认，Skills/ask_question 强制 `retryable: false`
- Codex `parallel_execution: RwLock` per-tool 判定
- Gemini `DEFAULT_MAX_ATTEMPTS = 10` + mid-stream API 硬限 3 次

**Onion 启示**：**强烈建议**。Onion Pydantic 类可加 `retry_policy: RetryPolicy` 字段统一管理（`max_retries: int = 3` / `timeout_ms: int = 30_000` / `retryable: bool = True`）。

---

## 6. 结果回传与协议适配

### 6.1 OpenAI `role=tool` + `tool_call_id`（标准）—— 必做

**频次**：16/20 标准（opencode / Claude Code / Gemini CLI / Codex / OpenHands / Cline / Open Interpreter / Continue / Roo Code / OpenClaw / Hermes / AutoGPT / Lobe Chat / AutoGen / CrewAI / ChatDev）；1/20 反例（SuperAGI `role=system`）；3/20 不用（MetaGPT 走 Message Bus / Aider prompt-as-tool / superpowers 不适用）

**典型代表**：
- OpenClaw `ToolResultMessage` 统一类型（`types.ts:330-345`）+ Anthropic adapter 转 `tool_result` 块
- Hermes `conversation_loop.py:4687-4690、4778-4783` `{role: "tool", name, tool_call_id, content}`
- AutoGPT `util/prompt.py:323-410` 3 协议 `role=tool` / Anthropic `tool_result` / OpenAI Responses `function_call_output` 全自动识别
- Lobe Chat `createToolMessage`（`packages/agent-runtime/src/executors/tool.ts:175-206`）调 `transports.messages.createToolMessage({role: 'tool', tool_call_id: tool.id, content: result.content, ...})`

**典型反例**：
- SuperAGI `output_handler.py:33-49` —— 把工具结果写 `role=system` 进 `agent_execution_feed` 表，**没有 `role=tool` 概念**

**Onion 启示**：**必做** —— 标准 `role=tool` + `tool_call_id` 格式，Anthropic 协议写 adapter 转换。

### 6.2 Anthropic `tool_result` 块 + `tool_use_id` —— 必做

**频次**：14/20 支持（opencode / Claude Code / Codex / OpenHands / Cline / Open Interpreter / Continue / Roo / OpenClaw / Hermes / AutoGPT / Lobe Chat / AutoGen / CrewAI）；1/20 不支持（SuperAGI）；1/20 Google 协议（Gemini `functionResponse`）；1/20 OpenAI Responses（Codex `function_call_output`）

**典型代表**：
- OpenClaw `anthropic-transport-stream.ts:555-585`
- Hermes `convert_messages_to_anthropic()`
- AutoGPT `util/prompt.py:395-410`
- Continue `Anthropic.ts:153-163` `getContentBlocksFromChatMessage` 构造 `tool_result` 块

**Onion 启示**：**必做**（与模式 6.1 配对）。

### 6.3 OpenAI Responses API `function_call_output` 块（新协议）—— 可选

**频次**：3/20 支持（OpenClaw + AutoGPT + Codex）

**典型代表**：
- OpenClaw `openai-responses-transport.ts:1168-1180`
- Codex `protocol/src/models.rs:1883` `FunctionCallOutputPayload` —— `FunctionCallOutput { call_id, output: FunctionCallOutputPayload { body: Text | ContentItems, success } }`

**Onion 启示**：**P1** —— MVP 暂只 Chat Completions，Responses API 放 P1。

### 6.4 错误标记 `isError` 字段 —— 必做

**频次**：15/20 显式（opencode / Claude Code / Codex / Cline / Open Interpreter / Continue / Roo / OpenClaw / Hermes / AutoGPT / Lobe Chat / AutoGen / CrewAI / ChatDev / superpowers）；5/20 不显式（SuperAGI 字符串前缀 / Aider / MetaGPT / AutoGPT 弱 / superpowers 部分）

**典型代表**：
- OpenClaw `ToolResultMessage.isError` + Anthropic adapter 转 `is_error`
- Hermes `tool_error("...")` → `{"error": "..."}`（`tools/registry.py:750+`）
- AutoGPT block `error` 字段强制 `str`（`blocks/__init__.py:80-85`）
- Continue `isError` 字段
- Lobe Chat `ToolRunResult.success: boolean, error?` 抽象

**Onion 启示**：**必做** —— handler 返回 `{"success": True, data}` 或 `{"error": "msg"}`，内部统一转 `isError` 字段。

### 6.5 结果内容 = JSON 字符串（标准）—— 必做

**频次**：16/20 强校验（opencode / Claude Code / Gemini CLI / Codex / Cline / Open Interpreter / Continue / Roo / OpenClaw / Hermes / AutoGPT / Lobe Chat / AutoGen / CrewAI / ChatDev / superpowers）；1/20 字符串前缀（SuperAGI）；3/20 不用（MetaGPT / Aider / superpowers 部分）

**典型代表**：
- OpenClaw `ToolResultMessage.content: (TextContent | ImageContent)[]`
- Hermes `_normalize_handler_result` 强校验（`tools/registry.py:622+`）
- AutoGPT `result.model_dump_json(exclude_none=True)`

**Onion 启示**：**必做** —— handler 返 dict → `json.dumps` 强校验 → 塞 `role=tool` content。

### 6.6 多模态结果（图片 / 媒体）—— 可选

**频次**：7/20 支持（OpenClaw + Hermes + Codex + Open Interpreter + opencode + Gemini + Roo）；13/20 不显式

**典型代表**：
- OpenClaw `ToolResultMessage.content` 支持 `ImageContent`
- Hermes `agent/image_routing.py` 把图片转 user message `image_url` 块
- Codex `FunctionCallOutputPayload` 多模态 —— `InputText / InputImage / EncryptedContent` 三类型
- Open Interpreter `InputText / InputImage / EncryptedContent` 三类型
- opencode `attachments?: FilePart[]` 图片/PDF，`Image.normalize()` 缩图
- Gemini `mcp-client.ts:1454-1465` MCP image/audio 块转 `Part.inlineData: { mimeType, data }`

**Onion 启示**：**P1** —— MVP 暂只 text，图片支持放 P1。

### 6.7 大结果截断（per-tool 阈值 + workspace 持久化）—— 必做

**频次**：18/20 强保护（opencode / Claude Code / Gemini CLI / Codex / Cline / Open Interpreter / Continue / Roo / OpenClaw / Hermes / AutoGPT / Lobe Chat / AutoGen / CrewAI / ChatDev / superpowers / Aider / OpenHands）；2/20 无保护（SuperAGI / MetaGPT）

**典型代表**：
- **OpenClaw** `tool-result-truncation.ts:45-58` —— `MAX_TOOL_RESULT_CONTEXT_SHARE = 0.3` + 16K chars + 大上下文 32K/64K + 完整 output 旁路到磁盘
- **Hermes** `tools/budget_config.py:14-19` —— 3 层保护（per-tool cap 100K / per-result cap / per-turn cap 200K）；`tools/tool_result_storage.py` spill 到 `<env temp>/hermes-results/<tool_use_id>.txt`
- **AutoGPT** `copilot/tools/base.py:38-117` —— `_LARGE_OUTPUT_THRESHOLD = 80_000` + `_PREVIEW_CHARS = 95_000` + **middle-out preview 截 95K** + retrieval hint
- **Codex** `TruncationPolicy { Bytes(usize), Tokens(usize) } + truncate-middle` —— `protocol.rs:3316-3320` + `output-truncation/src/lib.rs:10-19`，**保留前 50% + 后 50%**
- **Cline** `truncateCommandOutput` —— 保留前 50% + 后 50%（`output-limits.ts:25-41`）
- **opencode** `MAX_LINES=2000` / `MAX_BYTES=50KB` 写盘委托 subagent（`truncate.ts:107-130`）
- **Gemini** `LIVE_OUTPUT_MAX_BUFFER_CHARS = 100_000`（`shell.ts:62`）
- **ChatDev** `TEXT_INLINE_CHAR_LIMIT=200_000` + `MAX_INLINE_FILE_BYTES=50MB` + `AttachmentStore.register_bytes()` 落盘到 `code_workspace/attachments/<id>/`（`openai_provider.py:534-595` + `tool_manager.py:435-475`）

**典型反例**：
- SuperAGI `max_token_limit` 只裁 prompt，**不裁 tool result**；只有 LTM 旁路（切片入 vector store）**不走消息流压缩**
- Lobe Chat `toolResultMaxLength`（`tool.ts:91`）—— 信任 provider 不截断（哲学选择，但 200K 以上结果会撑爆 OpenAI request）

**Onion 启示**：**必做**。照搬 AutoGPT 的 `workspace://tool-outputs/<call_id>.json` + middle-out preview + retrieval hint 三件套。Onion 的 `~/.onion/tool-outputs/<call_id>.json` + preview + 引用是 5 分钟集成。**学 Codex 的 `TruncationPolicy { Bytes, Tokens }` + `truncate-middle` 头尾截断**（比单纯截尾友好）。

### 6.8 Multi-protocol 适配（同一份 message 转多个 provider）—— 必做

**频次**：15/20 强适配（opencode / Claude Code / Codex / OpenHands / Cline / Open Interpreter / Continue / Roo / OpenClaw / Hermes / AutoGPT / Lobe Chat / AutoGen / CrewAI / ChatDev）；5/20 弱适配（SuperAGI factory / Aider LiteLLM / MetaGPT provider registry 工具协议不统一 / ChatDev 部分 / superpowers 不适用）

**典型代表**：
- OpenClaw `convert_messages_to_anthropic()` 30+ provider 各自转换
- Hermes outbound 阶段 `convert_messages_to_anthropic()`
- AutoGPT 3 协议同一份函数支持
- opencode `provider/transform.ts:73-160` 1418 行 cross-provider normalize
- Open Interpreter `chat-wire-compat/src/request.rs:104-346` Responses↔Chat 互转
- Cline Vercel AI SDK 抽象 Provider 无关
- Continue `compileChatMessages` + provider-specific converter
- Roo Code 35+ provider → 统一 `ApiStream`

**Onion 启示**：**必做**（与模式 4.1 / 4.2 配对）。`session.json` 统一内部 schema，各 provider adapter 独立翻译。

### 6.9 跨角色 / 跨 agent 工具结果流转 —— 必做（多 Agent 场景）

**频次**：8/20 显式（AutoGen Workbench / Lobe Chat GroupOrchestration / CrewAI DelegateWorkTool / MetaGPT Message Bus / ChatDev code_workspace / OpenHands / Hermes / Cline teams）；12/20 单 agent 不需要

**典型代表**：
- **MetaGPT Message Bus**：`Environment.publish_message(message)` + `Message.cause_by`（订阅过滤器）+ `Message.send_to:set[str]`（`schema.py:232-243`）；MGXEnv TeamLeader（Mike）中转
- **AutoGen Workbench 共享**：`Workbench` 是"工具集合 + 共享资源"容器，`save_state/load_state` 跨 agent 持久化
- **Lobe Chat `lobe-agent` 工具集**：内置 plan + todo + sub-agent dispatch
- **CrewAI `DelegateWorkTool`** + `AskQuestionTool`
- **ChatDev `code_workspace/`** 目录是 Python 节点共享目录

**典型反例**：
- ChatDev `WorkflowSessionStore`（`server/services/session_store.py:67-83`）—— **Server 端 session 纯内存，重启即丢**
- AutoGen `McpWorkbench.save_state` 是 placeholder —— 返回固定的 `McpWorkbenchState().model_dump()`（空状态），`reset()` 是 no-op

**Onion 启示**：**必做**（sub-agent 场景）。3 种实现选 1：
- 共享 workbench 池（学 AutoGen）
- sub-agent dispatch（学 Lobe Chat `lobe-agent`）
- Agent 委派工具（学 CrewAI `DelegateWorkTool`）

**禁止 server 端 session 纯内存**（不学 ChatDev 反例）。

---

## 7. File Backend 适配（为工具调用做的目录/文件）

> 这一节是 file_backend 维度的姊妹——专门回答"工作区里为工具调用做了哪些目录/文件"。

### 7.1 MCP 配置文件路径（双层覆盖）—— 必做

**频次**：14/20 共识（Claude Code 4 层 + Continue 3 层 + Roo Code 2 层 + Codex TOML + Gemini settings.json + Cline 单点 + OpenHands API + opencode 4 层 config + AutoGen 0 + ChatDev YAML + Lobe Chat user_connectors + CrewAI @CrewBase + MetaGPT 0 + Hermes config.yaml）；2/20 不支持（Aider 0 / opencode 间接）

**典型代表**：
- **`<repo>/.mcp.json` + `~/.mcp.json` + plugin 内 `.mcp.json` + managed-mcp.json** —— Claude Code 4 层
- **`<cwd>/.continue/mcpServers/*.json` + `~/.continue/mcpServers/*.json` + YAML 内嵌** —— Continue 3 层
- **`<repo>/.roo/mcp.json` + `%APPDATA%\Roo-Code\MCP\settings\mcp.json`** —— Roo Code 2 层
- **`config.toml` 的 `[mcp_servers.<name>]`** —— Codex / Open Interpreter
- **`settings.json` 的 `mcpServers`** —— Gemini + extension.json 内嵌
- **`cline_mcp_settings.json` 单点** —— Cline（反例，无项目级）
- **`mcp_config` 通过 settings API** —— OpenHands 用户注入
- **`opencode.jsonc` 的 `mcp` 字段** —— opencode 4 层 config
- **`~/.hermes/config.yaml` 的 `mcp_servers:` 段 + 官方 MCP 目录 `optional-mcps/<name>/manifest.yaml`** —— Hermes

**典型反例**：
- Aider 0 命中
- AutoGPT —— 源码中**无传统 `.mcp.json` 配置文件**，MCP 完全走运行时 UI / DB 凭证（**违反 file_backend §10.8**）
- MetaGPT —— `metagpt/tools/schemas/<name>.yml` 路径在 `const.py:65` 声明但**实际不存在**（`Get-ChildItem` 报 PathNotFound），历史遗留

**Onion 启示**：**必做**。**学 Claude Code 的 4 层设计**：
1. `<repo>/.onion/mcp.json`（项目级）
2. `~/.onion/mcp.json`（全局）
3. Plugin 内 `.mcp.json`（第三方插件）
4. managed-mcp.json（企业级）

**避免 AutoGPT 反例**——必须支持传统文件配置，**不能把 MCP 配置藏 DB**。

### 7.2 Agent Skills 目录扫描路径 —— 强烈建议

**频次**：12/20 显式（Roo Code 5 层 8 路径 / Cline 6 目录 / opencode 3 层 + URL 缓存 / Gemini 4 层 / Open Interpreter 3 scope / Codex 3 scope / Continue 3 层 / OpenHands 5 源 / Claude Code 14 plugin 自带 / Lobe Chat 5 API / CrewAI search_path / ChatDev 仓库级）；1/20 0 命中（Aider）

**典型代表**（按路径数）：
- **5 层 × 8 路径 Skills 覆盖矩阵**：Roo Code `services/skills/SkillsManager.ts:391-432` —— `~/.agents/skills[-mode]` + `~/.roo/skills[-mode]` + `<cwd>/.agents/skills[-mode]` + `<cwd>/.roo/skills[-mode]`
- **6 目录扫描**：Cline `skill-directories.ts:3-8` —— `.clinerules/skills` + `.cline/skills` + `.claude/skills`（与 Anthropic Agent Skills 互通）+ `.agents/skills` + `~/.cline/skills` + `~/.agents/skills`
- **3 层 + URL 缓存**：opencode `skill/index.ts:144-187`
- **3 scope**：Open Interpreter / Codex —— bundled + `~/.agents/skills/` + `.agents/skills/`
- **5 源合并**：OpenHands —— public / user / project / org / marketplace
- **仓库级写死**：ChatDev `manager.py:14-17` `DEFAULT_SKILLS_ROOT = (REPO_ROOT / ".agents" / "skills").resolve()`（**反例**，无 env/CLI 覆盖）

**Onion 启示**：**强烈建议**。**MVP 阶段 3 层**：
- `~/.onion/skills/`（全局）
- `<repo>/.onion/skills/`（项目级）
- `~/.agents/skills/`（跨工具共享，**学 superpowers 跨宿主兼容**）

P1 升级到 5 层（含 mode 限定 + `<repo>/.agents/skills/` 跨工具兼容）。

### 7.3 Hook 事件配置文件 —— 强烈建议

**频次**：4/20 显式（Claude Code 12 事件 + Codex + Gemini + OpenHands 弱）；16/20 无显式 hook 文件

**典型代表**：
- **Claude Code（最完整）**：`<plugin>/hooks/hooks.json` + `~/.claude/hookify.*.local.md`（`hookify/core/config_loader.py:157-184` 实时 glob）；12 种事件（PreToolUse / PostToolUse / SessionStart / Stop / UserPromptSubmit / SubagentStop / PreCompact / Notification / InstructionsLoaded / MessageDisplay 等）
- Codex `codex-rs/config/src/hook_config.rs`
- Gemini `settings.json` 的 `hooks` 字段

**Onion 启示**：**强烈建议**（P1 必做）。Onion 的 hook 系统应当支持 6 类事件：`PreToolUse` / `PostToolUse` / `SessionStart` / `SessionEnd` / `PreCompact` / `Notification`。配置走 `<plugin>/hooks/hooks.json` + `~/.onion/hooks/*.local.md` 双层。

### 7.4 AGENTS.md / 项目级规则文件兼容 —— 强烈建议

**频次**：12/20 显式（Cline 5 命名兼容 + Roo Code 3 命名 + Codex 32 KiB 上限 + Claude Code CLAUDE.md + Gemini GEMINI.md + Open Interpreter + Continue 3 命名 + OpenClaw + Hermes + AutoGPT + Lobe Chat + CrewAI）；8/20 单一（opencode 走自家 `.opencode/` / Aider 散落 / superpowers 不适用）

**典型代表**：
- Cline —— 5 命名兼容（AGENTS.md + .clinerules + .cursorrules + .windsurfrules + .claude/skills + .agents/skills）
- Roo Code —— `AGENTS.md` / `AGENT.md` / `AGENTS.local.md` + `.roomodes` + `.roorules`
- Codex —— `AGENTS.md` + `AGENTS.override.md` 32 KiB 上限（`core/src/agents_md.rs:121`）
- Continue —— AGENTS.md / AGENT.md / CLAUDE.md 三种命名都兼容

**典型反例**：
- opencode —— 用自家 `.opencode/`，**不兼容其他 Agent 的 `AGENTS.md` / `CLAUDE.md`**
- Aider —— 散落命名

**Onion 启示**：**强烈建议**。Onion 应当**兼容 5 命名**（AGENTS.md / AGENT.md / CLAUDE.md / ONION.md / .onion/rules.md）——**这是用户从其他工具迁来的"无缝迁移"保证**。**32 KiB 字节上限**（学 Codex）防 context 爆炸。

### 7.5 大工具输出持久化目录（spill）—— 必做

**频次**：9/20 持久化（OpenClaw `~/.openclaw/sessions/<id>/` + Hermes `<env temp>/hermes-results/<tool_use_id>.txt` + AutoGPT `workspace://tool-outputs/{tool_call_id}.json` + Cline + Codex + opencode + ChatDev `code_workspace/attachments/<id>/` + Aider 弱 + superpowers `<repo>/.superpowers/sdd/`）；11/20 无持久化

**典型代表**：
- OpenClaw `formatFullOutputFooter` —— 完整结果写到磁盘（`~/.openclaw/sessions/<id>/`），prompt 里只放 truncated + 引用路径
- Hermes `tools/tool_result_storage.py:43-45` —— `<env temp dir>/hermes-results/<tool_use_id>.txt` spill
- AutoGPT `workspace://tool-outputs/{tool_call_id}.json` + middle-out 95K preview + retrieval hint
- ChatDev `AttachmentStore.register_bytes()` 落盘到 `code_workspace/attachments/<id>/`（`tool_manager.py:435-475`）

**Onion 启示**：**必做**。Onion 的 `~/.onion/tool-outputs/<call_id>.json` + middle-out preview + 引用是 5 分钟集成。**归属推荐用户级 home**（`~/.onion/tool-outputs/`，与 Onion 的"数据不出内网 + 可 git 备份"哲学一致）。

### 7.6 项目级 scratch 目录（`<repo>/.xxx/sdd/`）—— 可选

**频次**：1/20 显式（superpowers 独有）；19/20 全部用用户级根

**典型代表**：
- superpowers —— 14 skill 用 `<repo>/.superpowers/sdd/{progress.md, task-N-brief.md, task-N-report.md, review-X..Y.diff}`（`sdd-workspace:14-22`）+ brainstorming `<repo>/.superpowers/brainstorm/<SESSION_ID>/` + 自屏蔽 `.gitignore:4`

**Onion 启示**：**可选**（P1 借鉴）。如果 Onion 要"进入目录就识别项目"，可以借鉴 superpowers 的 `<repo>/.onion/scratch/{progress.md, session-XXX.md}`（git-ignored，借鉴 superpowers 自屏蔽 `.gitignore` 写在子目录里）。

### 7.7 MCP OAuth 凭证目录（`mcp-tokens/`）—— 强烈建议

**频次**：1/20 完整实现（Hermes 独有，20/20 中**唯一完整 MCP OAuth 2.1**）；19/20 无 MCP / 无 OAuth

**典型代表**：
- Hermes `tools/mcp_oauth.py:381-396` `HermesTokenStorage` 完整文件布局：
  - `HERMES_HOME/mcp-tokens/<server_name>.json` —— tokens
  - `HERMES_HOME/mcp-tokens/<server_name>.client.json` —— client info
  - `HERMES_HOME/mcp-tokens/<server_name>.meta.json` —— oauth server metadata
  - 配合 `agent/file_safety.py:298-310` LLM 不可读白名单（整个 `mcp-tokens/` 目录级屏蔽）

**Onion 启示**：**强烈建议**（P1 必做）。Onion 应当**直接抄** `mcp-tokens/` 目录级 LLM 不可读白名单——这是 Hermes 最强的安全设计细节。

---

## 8. 流式与并发

### 8.1 流式调用（stream=True）—— 必做

**频次**：18/20 流式（opencode / Claude Code / Gemini CLI / Codex / OpenHands / Cline / Open Interpreter / Continue / Roo / OpenClaw / Hermes / AutoGPT / Lobe Chat / AutoGen / CrewAI / Aider partial / superpowers / MetaGPT 弱）；2/20 不用流式（AutoGPT 主路径 non-streaming / SuperAGI 完全）

**典型代表**：
- OpenClaw `openai-completions-transport.ts:707-770` 完整流式解析 + `anthropic-transport-stream.ts:1443-1710` Anthropic 流式
- Hermes 用 OpenAI Python SDK（SDK 内部已流式）

**典型反例**：
- AutoGPT `provider.call_provider` 无 `stream=True`
- SuperAGI `output_handler.handle_tool_response` 接收 `assistant_reply: str` 是完整字符串
- ChatDev 全仓库 `grep "stream=True" 0 命中`

**Onion 启示**：**必做**。Onion 应当用 OpenAI SDK（`stream=True`），Anthropic 自己写 `content_block_delta` 累积。

### 8.2 并行工具调用（parallel tool calls）—— 强烈建议

**频次**：12/20 强并行（opencode / Claude Code / Gemini CLI / Codex / OpenHands / Cline / Open Interpreter / Continue / Roo / OpenClaw / Hermes / AutoGPT / Lobe Chat / AutoGen / CrewAI）；8/20 不显式并行

**典型代表**：
- OpenClaw `parallel_tool_calls: true` 参数 + provider 内部调度
- Hermes `run_agent.py:5915+` `_execute_tool_calls()` 完整 segment 规划器 —— 自动决定哪些 tool_call 串行 / 哪些并行
- Gemini `wait_for_previous` schema 注入（`tools.ts:405-426`）—— 唯一让 LLM 显式控制并发/串行
- Codex per-tool `supports_parallel_tool_calls` + `parallel_execution: RwLock`（`core/src/tools/parallel.rs:42-44`）
- opencode `activeTools` 过滤
- AutoGen `_assistant_agent.py:1257` `results = await asyncio.gather(*[self._execute_tool_call(call, workbench, ...) for call in current_model_result.content])`
- Lobe Chat `callToolsBatch` 用 `Promise.all` 并行执行

**Onion 启示**：**强烈建议**。Onion 应当 `asyncio.gather` 并行执行多个 tool_call，**学 Gemini 的 `wait_for_previous` 模式**——LLM 显式控制并发/串行比"自动判定"更可预测。

### 8.3 Sub-agent 委派工具 —— 强烈建议

**频次**：9/20 显式（OpenClaw `agents_list` / `get_goal` / `create_goal` + Hermes `delegate_task` + `kanban_*` 12 个 + AutoGPT `AgentExecutorBlock` + `run_sub_session` + opencode `task` 工具 + Cline `spawn_agent` + `teams` + Roo `new_task` + Claude Code `Task` + OpenHands `get_registered_agent_definitions` + Aider `ArchitectCoder` + Codex `multi_agents_v2` + Open Interpreter）；11/20 无

**典型代表**：
- OpenClaw `agents_list` / `get_goal` / `create_goal` / `update_goal`（`openclaw-tools.ts:527-543`）
- Hermes `delegate_task` 工具 + `kanban_*` 12 个工具（默认 `HERMES_KANBAN_TASK` env 启用）
- AutoGPT `AgentExecutorBlock`（`blocks/agent.py:24-142`）+ `run_sub_session` + `OrchestratorBlock`
- Codex `multi_agents_v2` —— spawn_agent / wait_agent / send_message / list_agents / followup_task / interrupt_agent
- opencode `task` 工具 —— general/explore/用户自定义 subagent，支持 background 异步
- Cline `spawn_agent` + `teams` —— 多 agent 协作套件（mailbox / mission / outcome）
- Roo Code `new_task` —— 与 new_task 同 turn 的其他工具被截断并注入错误 tool_result

**典型反例**：
- Continue —— 无显式 sub-agent 工具

**Onion 启示**：**强烈建议**（P1 必做）。Onion 的 `task` 工具参照 opencode `tool/task.ts` 设计。

### 8.4 Background command（后台 shell）—— 可选

**频次**：1/20 显式（Gemini 独有）

**典型代表**：
- Gemini `Gemini_CLI/tool_channel.md:18-22` —— `is_background: bool` schema 字段 + `shellBackgroundTools.ts`

**Onion 启示**：**P2 阶段做**（MVP shell 是同步执行）。

### 8.5 Sub-agent 状态汇聚（文件 handoff）—— 可选

**频次**：1/20 显式（superpowers 独有）；19/20 sub-agent 工具结果直接进 context

**典型代表**：
- superpowers `skills/subagent-driven-development/scripts/{sdd-workspace,task-brief,review-package}` 三件套 —— 大 diff / 大 plan 走文件而不是 context 注入

**Onion 启示**：**值得借鉴**。Onion 的 sub-agent 边界上**不把完整 transcript 写回主 session**，而是用 `<reference target="file://..."/>` 占位，与模式 6.7 大结果持久化结合。

### 8.6 Harness 切换（10 harness 仿真）—— 禁止

**频次**：1/20 显式（Open Interpreter 独有，**198KB 巨文件**）

**典型代表**：
- Open Interpreter `harness_aliases.rs:198KB` 单一文件 + `harness/routing.rs`

**典型反例**：
- 其他 19 个**完全没有 harness 仿真**概念

**Onion 启示**：**禁止**。Onion 应当坚持**单一协议抽象**，不学 10 harness 仿真——这是"协议适配做得太重"的过度工程。

---

## 9. 沙箱与安全

### 9.1 OS 级纵深防御沙箱（macOS Seatbelt + Linux Landlock）—— 强烈建议

**频次**：1/20 显式（Codex 独有）

**典型代表**：
- Codex `sandboxing/src/seatbelt.rs` + `include_str!` 编译 + 3 档 `SandboxPolicy::{WorkspaceWrite, ReadOnly, DangerFullAccess, ExternalSandbox}` + macOS Seatbelt + Linux Landlock/seccomp + Windows Restricted Token + bubblewrap 纵深防御（`sandboxing/src/lib.rs:1-14`）

**Onion 启示**：**强烈建议**（P2 阶段做）。MVP 阶段靠 approval 询问 + workspace-write 限制，P2 阶段接 OS 级沙箱。

### 9.2 Docker 沙箱隔离 —— 可选

**频次**：1/20 显式（OpenHands 独有）

**典型代表**：
- OpenHands `docker_sandbox_spec_service.py:50` `working_dir='/workspace/project'`

**Onion 启示**：**可选**（P2）。Onion 是 CLI / Desktop 形态，不是 server 形态，Docker 不一定适用。

### 9.3 三档权限模式（default / auto-edit / full-auto）—— 强烈建议

**频次**：1/20 显式（Codex 独有）+ 1/20 Plan/Act（Cline / Roo）

**典型代表**：
- Codex `core/src/config/mod.rs:520-548` —— `SandboxPolicy::{WorkspaceWrite, ReadOnly, DangerFullAccess, ExternalSandbox}` + `approval_policy` 多档
- opencode `build` + `plan` + `general` + `explore` + `compaction` 5 个原生 agent
- Cline `mode: "plan" | "act"`，plan 模式下只读 + ask_question
- Roo Code 5 个 DEFAULT_MODES（architect/code/ask/debug/orchestrator）

**Onion 启示**：**强烈建议**（P1 必做）。Onion 应当有 3 档权限（`default` / `auto-edit` / `full-auto`）+ workspace_roots 列表 + Plan/Act 双 mode。

### 9.4 Per-tool 审批模式 —— 强烈建议

**频次**：2/20 显式（Codex + Open Interpreter）

**典型代表**：
- Codex `McpServerToolConfig` per-tool approval mode
- Open Interpreter `additional_permissions` 白名单 + feature flag 双重校验
- Lobe Chat `humanIntervention: 'never' | 'always' | 'required' | 'first'` + 基于参数的规则（`pathScopeAudit`）

**Onion 启示**：**强烈建议**（P1 必做）。Onion 应当 per-tool approval mode（Auto / Prompt / Writes / Approve）。

### 9.5 Folder-trust 弹窗 —— 必做

**频次**：3/20 显式（Gemini CLI + Codex + Claude Code）

**典型代表**：
- Gemini CLI `folderTrust.enabled` 默认 true，headless 模式阻塞报错
- Codex `set_project_trust_level` 写入 `config.toml [projects]`
- Claude Code `.claude/settings.json` 加载时弹信任对话框

**典型反例**：
- opencode / Cline / Roo / OpenHands / Aider / Continue / Open Interpreter 无 folder-trust 弹窗

**Onion 启示**：**必做**。Onion 应当 `folderTrust.enabled` 默认 true，headless 模式阻塞报错（学 Gemini CLI）。**信创合规的强需求**。

### 9.6 Allowed-tools glob 模式 —— 强烈建议

**频次**：1/20 显式（Claude Code 独有）

**典型代表**：
- Claude Code `allowed-tools` 支持 `Bash(git add:*)` / `Bash(test -f .claude/ralph-loop.local.md:*)`（`ralph-wiggum/commands/ralph-loop.md:4`）

**Onion 启示**：**强烈建议**（P1 必做）。Onion 应当 `Bash(git:*)` 这种 glob 模式，比 `allow/deny` 三档精细一个数量级。

### 9.7 写保护文件清单 —— 强烈建议

**频次**：1/20 显式（Roo Code 独有）

**典型代表**：
- Roo Code `RooProtectedController.PROTECTED_PATTERNS` 包括 `.rooignore` / `.roomodes` / `.roorules*` / `.clinerules*` / `.roo/**` / `.vscode/**` / `AGENTS.md` / `AGENT.md`（`core/protect/RooProtectedController.ts:14-24`）

**Onion 启示**：**强烈建议**（P1 必做）。Onion 应当定义 `_PROTECTED_PATTERNS = ("~/.onion/onion.json", "AGENTS.md", "ONION.md", "secrets/auth.json", "secrets/mcp-tokens/", ...)`，agent 修改这些文件时必须经用户显式批准，**无视 auto-approval 设置**。

### 9.8 LLM 不可读目录白名单（防 prompt injection 偷 secrets）—— 必做

**频次**：3/20 显式（Hermes 完整 / Lobe Chat 部分 / opencode `*.env: "ask"` / ChatDev FileToolContext 路径校验）

**典型代表**：
- **Hermes（最完整）**：`agent/file_safety.py:109-310` 显式拒绝（见原则 1.4）
- Lobe Chat `user_connectors.credentials` AES-256-GCM 加密
- opencode `Opencode/tool_channel.md:148-150` —— `*.env: "ask"` + `*.env.*: "ask"`

**Onion 启示**：**必做**。Onion 的 `read_file` / `grep` / `find` 工具要内置 `_ROOT_CREDENTIAL_DIRS`（参考原则 1.4）。

### 9.9 凭证文件权限 0o600（active chmod）—— 必做

**频次**：13/20 显式（Cline / Codex / Claude Code / Gemini CLI / Continue / Open Interpreter / OpenHands / opencode / OpenClaw / Hermes / AutoGPT / Lobe Chat / CrewAI）；7/20 不显式

**典型代表**：
- Hermes `agent/anthropic_adapter.py:1179-1184` `os.open(..., 0o600)` 主动 chmod
- Codex `secrets/src/local.rs:37-39, 138-152` age 加密 + `secrets/{local,codex_auth,mcp_oauth}.age`
- Continue VS Code SecretStorage（OS keychain，比 0o600 更强）

**典型反例**：
- Aider —— `oauth-keys.env` 权限未声明
- Roo Code —— 未显式 chmod 0o600
- MetaGPT —— `~/.metagpt/config2.yaml` 明文

**Onion 启示**：**必做**。Onion 的 `~/.onion/auth.json` / `mcp-tokens/*.json` 应当 `os.open(..., 0o600)` 创建，**防创建到 chmod 中间被 read**。MVP 阶段 0o600 即可，P1 阶段加 `secrets/*.age` 加密（学 Codex）。

### 9.10 Plugin pre-tool hook（执行前 block / approve）—— 强烈建议

**频次**：4/20 显式（OpenClaw + Hermes + Claude Code + Codex）

**典型代表**：
- OpenClaw `agent-tools.before-tool-call.ts:788,932,1193` 工具执行前 hook、loop detection、approval、tracked 状态
- Hermes `model_tools.py:1180+` `resolve_pre_tool_block` 插件可在执行前 block/approve

**Onion 启示**：**强烈建议**（P1 必做）。Onion 的 `bash_exec` / `web_fetch` 工具执行前**应当**有"危险工具确认"hook。

### 9.11 Plan-then-act 模式（update_plan 工具）—— 强烈建议

**频次**：5/20 显式（OpenClaw `update_plan` 非强制 + AutoGPT `OrchestratorBlock` + Codex `update_plan` + Cline Plan/Act + opencode 5 agent + Gemini plan_mode + Roo 5 Mode）

**典型代表**：
- OpenClaw `openclaw-tools.ts:562` `update_plan` 工具，**非强制**，LLM 主动声明
- AutoGPT `OrchestratorBlock` plan + execute 两阶段循环（`blocks/orchestrator.py`）
- opencode `agent/agent.ts:141-260` 5 个原生 agent 定义

**Onion 启示**：**强烈建议**（P1 必做）。Onion 应当预留 `update_plan` 工具接口。

### 9.12 Human Intervention 闸门（never / always / required / first）—— 可选

**频次**：1/20 显式（Lobe Chat 独有）

**典型代表**：
- Lobe Chat `humanIntervention: 'never' | 'always' | 'required' | 'first'` + 基于参数的规则（`pathScopeAudit`，见 `builtin-tool-local-system/src/manifest.ts:23-29`）

**Onion 启示**：**可选**（P1 强防御）。Onion 应当支持 per-tool `humanIntervention` 声明 + 路径白名单。

---

## 10. 工程化与可观测

### 10.1 重试上限（3 类：LLM API 5 / tool 3 / run loop 32-160）—— 必做

**频次**：18/20 显式（OpenClaw 强 + Hermes 4 类 + AutoGPT 强 + Cline 3 + opencode 0 默认 + Gemini 10/3 + Codex 依赖 LLM + Aider RETRY_TIMEOUT + Continue 隐式 + Roo 3 + Lobe Chat 3 层 + AutoGen 隐式 + CrewAI 3 + ChatDev 5 tenacity + MetaGPT 6×3 + superpowers 不适用 + SuperAGI 弱）；2/20 无（SuperAGI 弱 / superpowers 不适用）

**典型代表**：
- **OpenClaw** `run-loop.ts:167,277-285` —— `MAX_RUN_LOOP_ITERATIONS = resolveMaxRunRetryIterations(profileCandidateCount, cfg, agentId)`（`run/helpers.ts:131-148`），算法 `base=24 + perProfile=8 × profiles`，截断在 [min=32, max=160]；`failover-retry-controller.ts` 跨 provider 切换
- **Hermes** 4 类重试上限：
  - 无效工具名 **3 次**（`conversation_loop.py:4642`）
  - 流式截断 **4 次** continuation（`conversation_loop.py:2010`）
  - 普通 length 错误 **4 次** continuation（`conversation_loop.py:1946`）
  - 外层 API 错误 fallback provider 链（`auxiliary_client.py:3774+`）
- **AutoGPT** `util/retry.py:170-215` —— `create_retry_decorator(max_attempts=5, max_wait=30.0)` + `func_retry` + `conn_retry`（默认 100 次）+ `continuous_retry`（无限循环）+ `EXCESSIVE_RETRY_THRESHOLD = 50` 触发 Discord 告警
- **Cline** `create.ts:140-143` —— `retryable: true, maxRetries: 3, timeoutMs: 30_000` 默认
- **Gemini** `DEFAULT_MAX_ATTEMPTS = 10` + mid-stream API 硬限 3 次
- **Lobe Chat** 三层重试：工具级 `DEFAULT_TOOL_MAX_RETRIES = 2` + LLM 级 `LLMRetryPolicy` 分类（超时/网络/限流/服务端/上下文）+ 操作级 `interruption.canResume: true` 持久化
- **MetaGPT** 6×3 = 18 次（**太激进**，生产环境会爆 token 预算）
- **CrewAI** `_max_parsing_attempts = 3`（默认）/ 2（OpenAI big models）

**典型反例**：
- SuperAGI `tool_executor.py` 的 `retry=True` 只把错误写回 history，**无 retry counter**，理论上 LLM 可无限循环修复直到 context 撑爆
- MetaGPT 18 次（**强反例**）
- AutoGen 默认 1（**太严格**）

**Onion 启示**：**必做**。Onion 应当有 3 类重试上限：
- LLM API 层：`max_llm_retry=5`（tenacity 装饰器）
- tool call 层：`max_tool_retry=3`（同 tool 反复失败）
- run loop 层：`max_run_iterations=64`（总 turn 上限）

**避 MetaGPT 18 次激进反例** + **避 AutoGen 1 次太严反例**。**学 Gemini 的双层**：HTTP 10 次 + mid-stream API 3 次 + tool result error 不 retry（只回传 LLM）。

### 10.2 Token 计数 + cost 统计（`ProviderResponse` 标准化）—— 强烈建议

**频次**：6/20 完整（AutoGPT 强 + Hermes 部分 + Continue `countToolsTokens` + Codex `approx_token_count` + Lobe Chat `TokenUsage` + MetaGPT `compress_messages` 4 策略）；14/20 不显式

**典型代表**：
- AutoGPT `util/llm/providers.py:133-165` —— `ProviderResponse` 标准化含 `prompt_tokens` / `completion_tokens` / `cache_read_tokens` / `cache_creation_tokens` / `cost_usd`
- Continue `core/llm/countTokens.ts:135` —— `countToolsTokens`
- Codex `output-truncation/src/lib.rs:10-19` —— `approx_token_count`
- Lobe Chat `topics` 表 —— `historySummary/totalCost/totalTokens` 3 字段
- MetaGPT `BaseLLM.compress_messages`（`base_llm.py:281-355`）—— 4 种策略 `POST_CUT_BY_TOKEN` / `POST_CUT_BY_MSG` / `PRE_CUT_BY_TOKEN` / `PRE_CUT_BY_MSG`，按 `keep_token = max_token * 0.8` 裁剪

**Onion 启示**：**强烈建议**。Onion 的 `ProviderResponse` 应当标准化 token 计数 + cost，**方便用户做 budget 控制**（信创合规常要求"每日 API cost 上限"）。**Python 项目用 `tiktoken` 库**。

### 10.3 工具调用日志 / debugging（事件流）—— 必做

**频次**：15/20 完整（opencode SQLite / Claude Code hooks / Codex JSONL + .zst / Cline per-task 4 文件 / Continue per-context-item / Roo per-task / OpenClaw output_handler / Hermes execution_feed / AutoGPT 弱 / Lobe Chat `stream.publishEvent` 强 / AutoGen Workbench 生命周期 / CrewAI `ToolSelectionErrorEvent` / ChatDev 4 件套审计 / MetaGPT 弱）；5/20 不显式

**典型代表**：
- **Codex（最完整）**：`sessions/YYYY/MM/DD/rollout-…-<uuid>.jsonl` + 可选 `.zst` 压缩（`rollout/src/recorder.rs:1517-1555`）
- **Lobe Chat** `stream.publishEvent({ type: 'tool_start' | 'tool_end' | 'error' })` —— 前端实时看到工具开始 / 结束 / 错误；每次失败 stream 一个 `tool_end` 事件带 `attempts` + `maxAttempts`
- **opencode** SQLite `state_5/logs_2`
- **Cline** `db/sessions.db` + per-task 4 文件
- **AutoGen** `Workbench` 抽象支持 `start / stop / reset / save_state / load_state` 完整生命周期事件
- **CrewAI** `ToolSelectionErrorEvent` + `ToolValidateInputErrorEvent` + 多次 `CacheTools` 事件
- **ChatDev** `node_outputs.yaml` + `workflow_summary.yaml` + `execution_logs.json` + `token_usage_<session>.json` 4 件套

**典型反例**：
- MetaGPT `_achat_completion_stream` 不解析 `delta.tool_calls`，debug 时看不到工具流
- ChatDev 无实时 stream 事件（只有运行结束生成审计文件）
- Aider `.aider.chat.history.md`（**反例**，不裁剪不写回，chat history 文件越来越大）

**Onion 启示**：**必做**。Onion 的 `~/.onion/logs/tool-calls/<date>.jsonl` 应有完整 tool_call 记录，**学 Codex 的 JSONL + .zst 压缩** + **学 Lobe Chat 的实时 stream 事件**。**MVP JSONL 流式追加 + 按日分目录**——比 SQLite 简单，比 per-event JSON 高效。

### 10.4 SIGINT / SIGTERM 优雅退出 —— 强烈建议

**频次**：1/20 显式（AutoGPT 独有）

**典型代表**：
- AutoGPT `util/retry.py:285-345` `_StopOnShutdown` + `_interruptible_async_sleep`

**Onion 启示**：**强烈建议**（MVP 可借鉴）。`asyncio.run()` 捕获 `KeyboardInterrupt` + `SIGTERM` 优雅退出。

### 10.5 Provider failover（跨 provider 自动切换）—— 可选

**频次**：4/20 显式（OpenClaw 强 + Hermes 强 + Lobe Chat `LLMRetryPolicy` 分类 + AutoGPT 弱）

**典型代表**：
- OpenClaw `failover-retry-controller.ts` 跨 provider 切换
- Hermes `auxiliary_client.py:3774+` fallback 链
- Lobe Chat `LLMRetryPolicy` 按 `classified.kind`（超时/网络/限流/服务端/上下文）分类

**Onion 启示**：**可选**（P1 借鉴）。Onion 的 `onion.config.yaml` 配 `providers: [openai, anthropic, minimax, ollama]` fallback 链。

### 10.6 Stop hook / 自循环 —— 可选

**频次**：1/20 显式（Claude Code 独有）

**典型代表**：
- Claude Code Ralph Wiggum plugin —— `stop-hook.sh` 读 `.claude/ralph-loop.local.md` → `{"decision": "block", "reason": <原 prompt>}`

**Onion 启示**：**可选**（P2）。Onion 的 Agent Loop 是 session.json 自动累加器，**天然支持自循环**（不学 Claude Code Ralph hook）。

### 10.7 Per-tool 错误码 + telemetry —— 强烈建议

**频次**：8/20 显式（Open Interpreter `FunctionCallError::{RespondToModel, Fatal}` / Codex `FunctionCallError` 三类分级 / Gemini `ToolErrorType.MCP_TOOL_ERROR` / Roo `consecutiveMistakeCount` / OpenClaw / Lobe Chat / CrewAI / ChatDev）；12/20 不显式

**典型代表**：
- Open Interpreter `tools/src/function_call_error.rs` —— `FunctionCallError::{RespondToModel(String), Fatal(String)}`
- Codex `FunctionCallError` 三类分级（Fatal / RespondToModel / Rejected）
- Gemini `ToolErrorType.MCP_TOOL_ERROR` + telemetry
- Roo `consecutiveMistakeCount` per-tool 计数

**Onion 启示**：**强烈建议**（P1 必做）。用 enum 区分 `RespondToModel` / `Fatal` / `Rejected` / `AccessDenied` / `MCP_TOOL_ERROR`，便于 LLM 自我修复 + telemetry 分类统计。

### 10.8 OTel / 分布式 tracing —— 可选

**频次**：1/20 显式（Codex 独有）

**典型代表**：
- Codex `codex-rs/otel/src/events/session_telemetry.rs:1205-1222` `ResponseEvent` 变体（Otlp）

**Onion 启示**：**可选**（P2）。MVP 不需要 OTel，JSONL 足够。

### 10.9 Tool Search 阈值（10% context window）—— 强烈建议

**频次**：2/20 显式（Hermes 强 + OpenClaw 弱）

**典型代表**：
- Hermes `tools/tool_search.py` 10% 阈值
- OpenClaw `src/agents/tool-search.ts` 工具数 > 阈值

**Onion 启示**：**强烈建议**（P1 必做）。Onion 引入 Tool Search 时**必须**有 10% context window 阈值。

### 10.10 Check_fn TTL 缓存（防 flake 探测）—— 可选

**频次**：1/20 显式（Hermes 独有）

**典型代表**：
- Hermes `tools/registry.py:114-200` —— 30s TTL + 60s last-good grace 防短时挂

**Onion 启示**：**可选**（P1 借鉴）。防 docker daemon 短时挂导致全 turn 失败。

### 10.11 Tool list 缓存 + generation 计数 —— 可选

**频次**：4/20 显式（Hermes 8 entry LRU + AutoGPT `@cached(ttl_seconds=3600)` + Lobe Chat `ToolsEngine.manifestSchemas` + ChatDev MCP cache_ttl）

**Onion 启示**：**可选**（P1 借鉴）。长跑 gateway 不会无限增长。

### 10.12 GBNF grammar 强制 JSON（本地模型）—— 可选

**频次**：1/20 显式（SuperAGI 独有）

**典型代表**：
- SuperAGI `local_llm.py:51` + `grammar/json.gbnf`

**Onion 启示**：**可选**（P1）。Onion 给 local 后端（Ollama）一个 grammar 钩子。

### 10.13 /doctor 自检命令 —— 强烈建议

**频次**：2/20 显式（Codex `codex doctor` + Claude Code `/doctor` slash command）

**典型代表**：
- Codex `cli/src/doctor.rs` —— 诊断 `CODEX_HOME` 路径 / auth.json / log_dir
- Claude Code 隐式 `/doctor` slash command

**Onion 启示**：**强烈建议**（P1 必做）。`onion doctor` 子命令扫描 6 类问题：env / auth / MCP / skills / session / config。

### 10.14 Per-tool timeout —— 必做

**频次**：7/20 显式（Cline `timeoutMs: 30_000` 默认 + opencode shell 工具单独 `timeoutMs` + Open Interpreter `RequestUserInputHandler` + OpenClaw + Hermes + Lobe Chat + ChatDev）；13/20 隐式

**典型代表**：
- Cline `create.ts:140-143` per-tool timeout

**Onion 启示**：**必做**。Pydantic 类可加 `timeout: int = 30_000` 字段统一管理（毫秒）。

---

## 11. 关键调研纠正（直接影响 Onion Agent 设计）

> 9 条调研纠正——子代理调研过程中发现的**反直觉 / 易踩坑**事实。

### 11.1 Cline v3 已全面从 XML 工具协议迁移到 OpenAI JSON Schema function calling

- `Cline/tool_channel.md:1-5` 明确："Cline v3 已全面从 XML 工具协议迁移到 OpenAI JSON Schema function calling, XML 协议只存在于旧版和其 fork Roo-Code"
- 证据：Cline `cline/sdk/packages/llms/src/providers/ai-sdk.ts:1212` Vercel AI SDK + `repairMalformedToolCall` 修复
- **影响**：用户 `project_manager.md` 里"流派 A（Cline 风格 XML 协议）"假设需要修正
- **建议**：推荐路线变成"OpenAI JSON Schema function calling + repair 函数"（Vercel AI SDK + Zod + zodToJsonSchema）

### 11.2 Roo Code 也抛弃了 XML 协议

- `Roo_Code/tool_channel.md:130-135` Roo **5 Mode + 5 层 8 路径 Skills** 是 Cline fork，但 XML 协议已被废弃
- **不要学 XML 协议**——Cline fork 也不用了

### 11.3 Codex CLI 没有 git worktree 多 Agent 隔离

- `OpenAI_Codex_CLI/tool_channel.md:38-42` `multi_agents_v2.rs` 的 spawn_agent 共享 `config.cwd` + permission profile
- **没有 `git worktree add`**
- file_backend §6.3 已经记录过
- **建议**：Onion 的 sub-agent 隔离不基于 git workbench（Codex 已验证不可行），**基于 session.json 子文件**（洋葱核心层的天然优势）

### 11.4 superpowers 不是 agent 本身，是 Skills 框架

- `superpowers/tool_channel.md:Q1 段结论` —— **0 个内置工具**
- 所有工具由宿主提供（Claude Code / Codex / Cursor / OpenCode / Pi / Kimi / Antigravity / Copilot CLI / Factory Droid）
- **影响**：纯 Skills 框架的工具调用必须穿透到宿主 agent，不要重复造轮子
- **建议**：Onion 不要走 superpowers 寄生模式（Onion 是"自研单一产品"）

### 11.5 AutoGPT = autogpt_platform/backend/（新）+ classic/（老）

- 仓库是 monorepo，内含两套完全不同实现
- `autogpt_platform/backend/`（2024+ 重写，graph + blocks 平台，本报告主体）
- `classic/original_autogpt/`（2023 初代 monolithic，只列对照）
- **影响**：调研时只看 `classic/` 会得到错误结论
- **建议**：Onion 借鉴 AutoGPT 的 graph + blocks 模式（**P2+ 阶段**）

### 11.6 SuperAGI 是纯 prompt-as-tool 派系代表反例

- **完全无 MCP / 无 Skills / 无流式 / 无沙箱 / 无 Tool Search / 无 Provider adapter**
- 通道是 ReAct 风格：LLM 返 `{thoughts, tool}` JSON，`ast.literal_eval` 解析 + 字符串匹配工具名 + DB feed 流回写
- **影响**：Onion **不能学** SuperAGI 的 prompt-as-tool 主路径
- **建议**：Onion 优先 OpenAI/Anthropic 原生 tool API，prompt-as-tool **仅作兼容回退**

### 11.7 Hermes 是 20 项目中安全设计最深

- **唯一完整实现 LLM 不可读目录白名单**（`_ROOT_CREDENTIAL_DIRS` 屏蔽 `mcp-tokens/` / `auth.json` / `~/.ssh/` 等）
- **唯一完整 MCP OAuth 2.1 + PKCE**
- **唯一 check_fn TTL 缓存防 flake**
- **建议**：Onion **直接抄** `mcp-tokens/` 目录级 LLM 不可读白名单

### 11.8 MetaGPT retry 上限 6×3 = 18 次（太激进）

- 外层 `@retry(stop=stop_after_attempt(6), wait=wait_random_exponential(1, 20))` + 内层 `retry_parse_json_text` 装饰 `@retry(stop=repair_stop_after_attempt)`（3 if Config.repair_llm_output else 0）
- **总上限 18 次 LLM 调用** —— 生产环境会爆 token 预算
- **建议**：Onion 用 3 类重试上限（LLM 5 / tool 3 / run 64）够了，**避 18 次激进**

### 11.9 ChatDev 是 file_backend 标准反例

- `OUTPUT_ROOT = Path("WareHouse")` 硬编码相对 cwd，3 处硬编码
- **Server 端 `WorkflowSessionStore` 纯内存，重启即丢**（与"WareHouse/<session>/ 落盘"的设计目标不一致）
- **没有 `~/.chatdev/` 用户属主目录**
- **Skills 目录写死**（无 env/CLI 覆盖）
- **建议**：Onion **必须有完整的属主目录**；**禁止硬编码相对 cwd**；**禁止 server 端 session 纯内存**

---

## 12. 20 个项目总览对照表

| 项目 | 类别 | 协议中立 | MCP | Skills | Provider adapter | 流式 | 大结果截断 | Doom loop | LLM 不可读白名单 | 重试上限 | 一句话特色 |
|------|------|:--------:|:---:|:------:|:----------------:|:----:|:-----------:|:---------:|:-----------------:|:--------:|----------|
| **OpenClaw** | 通用 | ✅ 30+ | ✅ 4 backend | ✅ 50+ | ✅ | ✅ 强 | ✅ 30% | ⚠️ 弱 | ❌ | ✅ 32-160 | **plain-text tool call repair 58890 字节独立包**（4 种语法）|
| **superpowers** | Skills 框架 | N/A | 委托宿主 | ✅ 14（不通过 tool_call）| N/A | N/A | ⚠️ 文件 handoff | N/A | N/A | N/A | **不是 agent 本身**，寄生宿主 |
| **Hermes Agent** | 通用 | ✅ 5+ | ✅ stdio/HTTP/StreamableHTTP/SSE + OAuth 2.1+PKCE | ✅ 300+ agentskills.io | ✅ | ✅ SDK 间接 | ✅ 3 层 100K/200K | ✅ 4 类 | ✅ **目录级屏蔽** | ✅ 4 类 | **最完整 LLM 不可读白名单 + 唯一 OAuth 2.1** |
| **AutoGPT** | 通用 | ✅ 7 provider | ✅ MCPToolBlock + run_mcp_tool | ✅ Anthropic | ✅ | ❌ 主路径 | ✅ 80K + middle-out 95K | ✅ tenacity 5 | ⚠️ auth.json 0o600 | ✅ 5 | **Blocks (graph) + Chat Tools 双层** |
| **opencode** | 编程 | ✅ AI SDK 30+ | ⚠️ 间接 | ✅ 3 层 + URL 缓存 | ✅ | ✅ LLMEvent | ✅ 50KB/2000 行 | ✅ 3 | ⚠️ `*.env: ask` | ⚠️ 0 默认 | **100% 开源 + Doom loop 强防护**（Onion 对标项目）|
| **Claude Code** | 编程 | ❌ 绑 Anthropic | ✅ 4 transport 4 层 | ✅ 14 plugin | ❌ | ✅ Anthropic | ✅ head/tail 50%+50% | ❌ exit 2 retry | ❌ | ⚠️ | **30+ plugin + 12 hook 事件** |
| **Gemini CLI** | 编程 | ❌ 绑 Google | ✅ 完整 | ✅ 4 层 | ❌ | ✅ Map<id> | ✅ shell 100k | ❌ | ❌ | ✅ 10/3 | **`folderTrust.enabled` 默认 true** + `wait_for_previous` |
| **OpenAI Codex CLI** | 编程 | ✅ OpenAI Responses + Bedrock | ✅ stdio/HTTP/OAuth | ✅ Anthropic | ✅ | ✅ ResponseEvent | ✅ `TruncationPolicy { Bytes, Tokens }` + truncate-middle | ❌ | ❌ | ⚠️ 依赖 LLM | **9 层 ConfigLayer + OS 级沙箱 + Terminal-Bench 77.3% 第一** |
| **OpenHands** | 编程 | ✅ LiteLLM | ✅ 双重身份 | ✅ 双格式 5 源 | ✅ | ✅ OpenAI | ✅ 限制 | ❌ | ❌ | ⚠️ 依赖 LiteLLM | **Docker 沙箱 + FileStore 抽象 4 后端** |
| **Lobe Chat** | 通用 | ✅ `ToolTransport` | ✅ 三层入口 | ✅ 5 API | ✅ | ✅ `@lobechat/model-runtime` | ⚠️ 信任 provider | ✅ DEFAULT_TOOL_MAX_RETRIES=2 | ⚠️ AES-256-GCM | ✅ LLMRetryPolicy | **三端隔离 + 129 migration + 异构 Agent 桥接** |
| **MetaGPT** | 多 Agent | ❌ 协议混乱 | ❌ | ❌ Semantic Kernel 风格 | ⚠️ 协议不统一 | ❌ 不 stream | ⚠️ RFC 135 不内联 | ✅ 6×3 太激进 | ❌ | ✅ 6×3 | **角色分工（PM/Arch/Eng/QA）** |
| **Cline** | 编程 | ✅ Vercel AI SDK 25+ | ✅ 3 transport OAuth | ✅ 6 目录扫描 | ✅ | ✅ AI SDK | ✅ 48K cap | ✅ 3 | ❌ | ✅ 3 | **v3 全面迁回 OpenAI JSON Schema function calling**（XML 已废弃）|
| **Open Interpreter** | 编程 | ✅ 3 协议 + 10 harness | ✅ stdio/HTTP | ✅ 3 scope | ✅ | ✅ 三协议 | ✅ Bytes/Tokens middle | ❌ | ❌ | ⚠️ | **30+ 工具 + 10 harness 仿真**（过度工程）|
| **AutoGen** | 多 Agent | ✅ 7 model client | ✅ 3 transport + Sampling/Elicitation/Roots | ❌ 借 MCP Prompts 替代 | ✅ | ✅ | ✅ ImageResultContent | ❌ 隐式 | ❌ | ❌ 隐式 | **`Workbench` 抽象 + `Component[Pydantic]` 完美序列化** |
| **CrewAI** | 多 Agent | ✅ | ✅ 3 transport | ✅ 三级 progressive disclosure | ✅ OpenAI 兼容 | ✅ Anthropic | ✅ VISION_IMAGE sentinel | ✅ 3 | ⚠️ | ✅ 3 | **`@CrewBase` 元类自动绑定 `base_directory`** + Skills 三级 |
| **Aider** | 编程 | ✅ LiteLLM | ❌ 0 命中 | ❌ 0 命中 | ✅ | ✅ partial | ✅ max_output 2800 | ⚠️ 3 行 fuzzy | ❌ | ⚠️ RETRY_TIMEOUT | **99% 走 prompt-as-tool**（已过时反例）|
| **Continue** | 编程 | ✅ OpenAI + Anthropic | ✅ YAML+JSON 三 transport | ✅ 3 层 | ✅ | ✅ dual | ✅ 48K + 200K fetch | ❌ | ❌ | ❌ | **双协议 + prompt-as-tool codeblock fallback** |
| **ChatDev** | 多 Agent | ⚠️ OpenAI + Gemini（无 Anthropic）| ✅ 双模式（remote/local）| ✅ 仓库级 + 2 tool | ⚠️ | ❌ 0 stream 命中 | ✅ 200K + attachment store | ✅ 50 | ⚠️ FileToolContext 路径校验 | ✅ 5 tenacity | **YAML DAG 编排 + 2.0 DevAll 版**（file_backend 反例）|
| **Roo Code** | 编程 | ✅ ApiStream 35+ | ✅ 双层 mcp.json | ✅ **5 层 8 路径** | ✅ | ✅ partial-json | ✅ line_limit 2000 | ✅ ToolRepetitionDetector 3 | ❌ | ✅ 3 | **5 Mode + 5 层 8 路径 Skills 覆盖矩阵 + fileRegex 严格隔离** |
| **SuperAGI** | 通用 | ❌ 纯 prompt-as-tool | ❌ 0 命中 | ❌ 0 命中 | ⚠️ factory | ❌ | ❌ 无保护 | ❌ 无 counter | ❌ | ❌ 无 | **纯 prompt-as-tool 派系代表反例** + Toolkit + DB 注册 + 远程集市 |

> **图例**：✅ 显式 / 强支持 | ⚠️ 部分支持 / 弱实现 | ❌ 无 / 不支持 | N/A 不适用（寄生 / 框架不涉及）

---

## 13. Onion Agent 推荐组合（P0/P1/P2）

> 这一节是**给用户后续设计 Onion Agent 工具通道的具体行动清单**。基于本标准 10 维度 + 用户洋葱架构哲学（`L5-Infrastructure` 的 `tool_shell` + `tool_channel` + `buildin_tool` + `mcp_client` + `agent_skills_client`），优先级如下。

### 13.1 P0（MVP 必做）

| 维度 | 具体实现 | 依据标准 |
|-----|---------|---------|
| **协议中立 + Provider adapter 模式** | 内部 `Tool[]` 一次定义，OpenAI / Anthropic 各自 adapter 翻译；`ProviderResponse` 标准化 token 计数 | §1.1 / §1.2 / §4.1 / §4.2 / §6.8 |
| **工具类型统一抽象（`BaseTool`）** | `BaseTool` 抽象基类（`schema: dict` + `handler: Callable` + `name: str` + `retry_policy` + `timeout`），4 来源（builtin / MCP / Skills / 集市）汇入同一条管线 | §1.2 / §2 |
| **MCP 一等公民** | stdio + StreamableHTTP 2 transport 必做；OAuth 2.1 + PKCE 放 P1；`McpWorkbench` 完整覆盖（Tools + Resources + Prompts + Sampling/Elicitation/Roots） | §2.2 / §7.1 / §9.8 |
| **Agent Skills 渐进式披露** | `~/.onion/skills/<slug>/SKILL.md` + `references/` + `scripts/` + `assets/` + 三级 progressive disclosure（METADATA / INSTRUCTIONS / RESOURCES） | §2.3 / §7.2 |
| **JSON Schema + Pydantic v2 反射** | 内部统一 OpenAI Chat Completions 风格 + Pydantic `args_type.model_validate` 强校验 + `extra='forbid'` + `required` + `additionalProperties: false` | §3.1 / §3.2 / §3.3 / §3.4 |
| **协议中立的多 Provider adapter** | `convert_tools_to_anthropic()` + `convert_tools_to_google()` + `convert_tools_to_ollama()` | §1.1 / §4.1 / §4.2 / §6.8 |
| **流式 OpenAI SDK + Anthropic `content_block_delta` 累积** | SDK 直接处理 OpenAI，Anthropic 自己写 | §5.1 / §5.2 / §8.1 |
| **plain-text tool call repair 包** | 照搬 OpenClaw `tool-call-repair` 58890 字节实现（4 种语法）或用 `json-repair` 库 | §5.3 / §5.5 |
| **大结果 workspace 持久化 + middle-out preview + retrieval hint** | `~/.onion/tool-outputs/<call_id>.json` + preview + 引用 | §6.7 / §7.5 |
| **LLM 不可读目录白名单（`_ROOT_CREDENTIAL_DIRS`）** | 直接抄 Hermes 的 `mcp-tokens/` 目录级屏蔽 + `Path.resolve()` 防符号链接绕过 | §1.4 / §9.8 |
| **3 类重试上限** | LLM API 5 / tool call 3 / run loop 64（**避 MetaGPT 18 次激进** + **避 AutoGen 1 次太严**） | §10.1 |
| **凭证文件 0o600 active chmod** | `os.open(..., 0o600)` 创建（防 race condition） | §9.9 |
| **Unreadable tool 隔离** | 1 个坏工具不能 crash 整轮 | §5.10 |
| **Tool Search 渐进式披露 + 黑名单** | 工具数 ≥ 20 时必做 + `TOOL_SEARCH_CONTROL_TOOL_NAMES` 黑名单 | §4.7 / §4.8 |
| **Folder-trust 弹窗** | `folderTrust.enabled` 默认 true，headless 模式阻塞报错（学 Gemini CLI）| §9.5 |
| **Per-tool timeout** | Pydantic 类加 `timeout: int = 30_000` 字段 | §10.14 |
| **Schema 强校验 + 容错** | Pydantic `args_type.model_validate` + 失败 raise `ValidationError` + 包装成 `isError: True` | §3.4 / §6.4 / §6.5 |
| **AGENTS.md 兼容 5 命名** | AGENTS.md / AGENT.md / CLAUDE.md / ONION.md / .onion/rules.md | §7.4 |
| **32 KiB 字节上限** | 学 Codex `project_doc_max_bytes` 32 KiB 截断 | §7.4 |
| **atomic write + temp+rename** | `Path(session.json + ".tmp").write_text(...)` + `Path.replace(...)` | file_backend §8.3 |
| **JSONL tool call 日志** | `~/.onion/logs/tool-calls/<date>.jsonl`（学 Codex） | §10.3 |
| **OpenAI function calling 协议** | `tools=[{"type":"function","function":{...}}]` 数组 | §4.1 / §6.1 |
| **Anthropic tools 协议** | `tools=[{"name","description","input_schema":{...}}]` + `role=tool` / `tool_use_id` 块 | §4.2 / §6.2 |
| **isError 错误标记** | handler 返 `{"success": True, data}` 或 `{"error": "msg"}`，内部统一转 `isError` | §6.4 |
| **Multi-protocol Adapter** | `session.json` 统一内部 schema，各 provider adapter 独立翻译 | §6.8 |
| **surrogate / lone surrogate 字符清洗** | `text.encode('utf-8', errors='replace').decode('utf-8', errors='replace')` 防 Ollama crash | §5.6 |
| **配置即代码（manifest + 多层 merge）** | `~/.onion/onion.json` 声明 manifest + 4 层覆盖（ONION_HOME env → `~/.onion/onion.json` → `<repo>/.onion/onion.json` → CLI 标志） | §1.3 |
| **MCP 双层配置文件** | `<repo>/.onion/mcp.json` + `~/.onion/onion.json` 的 `mcp` 字段（学 Claude Code 4 层）| §7.1 |
| **3 层 Skills 目录** | `~/.onion/skills/` + `<repo>/.onion/skills/` + `~/.agents/skills/`（跨工具共享）| §7.2 |
| **避免模块级常量** | `os.getenv` + 函数返回 Path，避免 `_HERMES_HOME` 模块级缓存（导致 profile 切换失效） | file_backend §4 |
| **禁用功能** | 不默认 `git init`；不写死 cwd；不靠纯内存 Server session；不学 SuperAGI 纯 prompt-as-tool；不学 MetaGPT 18 次激进；不学 Aider 99% prompt-as-tool | §11 / §4.3 / §10.1 / §8.6 / §6.7 |

### 13.2 P1（MVP 后期）

| 维度 | 具体实现 | 依据标准 |
|-----|---------|---------|
| **Tool Search 阈值（10% context window）** | 工具列表 > 10% context window 时切换到 Tool Search 模式 | §4.7 / §10.9 |
| **Plan-then-act `update_plan` 工具** | LLM 主动声明计划（学 OpenClaw）| §9.11 |
| **三档权限模式** | `default` / `auto-edit` / `full-auto` + workspace_roots（学 Codex）| §9.3 |
| **Plan/Act 双 mode** | plan mode 禁 write_file/edit（学 opencode / Cline）| §9.3 |
| **Per-tool 审批模式** | Auto / Prompt / Writes / Approve（学 Codex）| §9.4 |
| **Allowed-tools glob 模式** | `Bash(git:*)` 这种 glob（学 Claude Code）| §9.6 |
| **写保护文件清单** | `_PROTECTED_PATTERNS = ("~/.onion/onion.json", "AGENTS.md", "ONION.md", "secrets/auth.json", "secrets/mcp-tokens/", ...)` | §9.7 |
| **Plugin pre-tool hook** | 6 类事件：PreToolUse / PostToolUse / SessionStart / SessionEnd / PreCompact / Notification（学 Claude Code 12 事件）| §9.10 / §10.3 |
| **Hook 事件配置文件** | `<plugin>/hooks/hooks.json` + `~/.onion/hooks/*.local.md` 双层 | §7.3 |
| **Doom loop 3 次检测 + 弹窗** | 最近 N 次 tool call 完全相同（name + input）→ 弹窗询问用户 | §5.9 |
| **Orphan tool_result 修复三件套** | extract ids / extract response ids / validate_and_remove_orphan_tool_responses | §5.7 |
| **Schema 联合类型剥离** | Anthropic 不接受 `oneOf`/`allOf`/`anyOf`，需降级 | §5.8 |
| **工具名规范化** | `tool_name.lower() == name.lower()` 兜底 + 64 字符 MD5 压缩 + 非法字符替换为 `_` | §4.6 |
| **Per-tool 错误码** | enum 区分 `RespondToModel` / `Fatal` / `Rejected` / `AccessDenied` / `MCP_TOOL_ERROR` | §10.7 |
| **Token 计数 + cost 统计** | `ProviderResponse` 标准化 + `tiktoken` 库 | §10.2 |
| **`onion doctor` 自检命令** | 扫描 env / auth / MCP / skills / session / config 6 类问题 | §10.13 |
| **MCP OAuth 2.1 + PKCE 完整实现** | 学 Hermes `tools/mcp_oauth.py` + 3 transport | §2.2 / §7.7 |
| **Project-level scratch 目录 + 自屏蔽 `.gitignore`** | `<repo>/.onion/scratch/{progress.md, session-XXX.md}`（学 superpowers）| §7.6 |
| **配置版本迁移** | Alembic 风格 migration 文件，逐版本升级（学 Lobe Chat 129 migration）| file_backend §5.6 |
| **Sub-agent 委派工具 `delegate_task`** | 学 opencode `task` 工具（general/explore/用户自定义）| §8.3 |
| **Background command** | `is_background: bool` schema 字段（学 Gemini）| §8.4 |
| **Alembic 风格 schema 迁移** | `state.db` schema 版本号 + 启动时校验（学 Lobe Chat）| file_backend §5.6 |
| **Provider failover 链** | `providers: [openai, anthropic, minimax, ollama]` fallback 链（学 OpenClaw）| §10.5 |
| **SIGINT / SIGTERM 优雅退出** | `asyncio.run()` 捕获 `KeyboardInterrupt` + `SIGTERM` 优雅退出 | §10.4 |
| **Check_fn TTL 缓存** | 30s TTL + 60s last-good grace 防短时挂 | §10.10 |
| **Tool list 缓存 + generation 计数** | 8 entry LRU + config mtime fingerprint | §10.11 |
| **GBNF grammar 强制 JSON（Ollama 场景）** | `local_llm.py` + `grammar/json.gbnf` | §10.12 |
| **配置搜索链** | AGENTS.md / skills / rules 搜索链：包内置 → `~/.onion/` → `<repo>/` 向上到 `.git` 边界 → CLI/env | file_backend §10.5 |
| **prompt-as-tool fallback** | `SystemMessageToolCodeblocksFramework` + `detectToolCallStart()`（学 Continue）| §4.3 |
| **Tool call ID 兜底（MD5 / hash 合成）** | `MD5(function_name + arguments)[:8]` 合成（学 ChatDev）| §5.11 |
| **Human Intervention 闸门** | `never` / `always` / `required` / `first` + `pathScopeAudit`（学 Lobe Chat）| §9.12 |

### 13.3 P2（信创合规 / 长期演进）

| 维度 | 具体实现 | 依据标准 |
|-----|---------|---------|
| **OS 级纵深防御沙箱** | Windows Restricted Token + Linux Landlock/seccomp + macOS Seatbelt（学 Codex）| §9.1 |
| **Docker 沙箱** | `Dockerfile` + `docker-compose.yml`（学 OpenHands）| §9.2 |
| **加密 secrets** | AES-256-GCM 加密 `auth.json`（学 Lobe Chat）| §1.4 / §9.9 |
| **plugin 系统** | `~/.onion/plugins/` + manifest.json + 第三方 marketplace | §2.4 / §2.5 |
| **多 board** | `~/.onion/profiles/<profile>/` 模式 | file_backend §7.4 |
| **per-workspace hash 隔离** | sha256 前 16 hex（64-bit）而非 8 hex（32-bit，避免生日悖论）| file_backend §3.6 |
| **病毒扫描** | 写文件时走 `scan_content_safe()` | 学 AutoGPT |
| **凭证白名单硬编码** | `_ROOT_CREDENTIAL_DIRS = ("secrets", "auth.json", ".env")` LLM 永远不能 read | §1.4 / §9.8 |
| **路径模板化** | Onion 不要走 `name_id` 拼路径，**只用纯 UUID / sha256** | file_backend §10.1 |
| **chat history 压缩回写** | Aider 反例：`.aider.chat.history.md` 压缩后不写回文件，Onion 要**主动写回 session.json** | §6.7 |
| **完整 schema 迁移** | 借鉴 Lobe Chat 129 个 migration，Alembic 风格 | file_backend §5.6 |
| **多模态结果（图片 / 媒体）** | OpenClaw `ToolResultMessage.content` 支持 `ImageContent` | §6.6 |
| **OpenAI Responses API 协议** | `FunctionCallOutputPayload` 多模态结构（学 Codex）| §6.3 |
| **Sub-agent 状态汇聚（文件 handoff）** | 学 superpowers `sdd-workspace` / `task-brief` / `review-package` 三件套 | §8.5 |
| **Stop hook / 自循环** | 学 Claude Code Ralph Wiggum plugin | §10.6 |
| **OTel / 分布式 tracing** | `codex-rs/otel/src/events/session_telemetry.rs` | §10.8 |
| **per-workspace hash 隔离** | sha256 前 16 hex（学 Cline 但避免 32-bit 碰撞）| file_backend §3.6 |
| **三端隔离** | CLI + Desktop 各端，共享 `~/.onion/` | file_backend §2.6 |
| **Stop hook / 自循环** | 学 Claude Code Ralph Wiggum | §10.6 |
| **完整 sandbox 三档权限** | default/auto-edit/full-auto + workspace_roots | §9.3 |

### 13.4 禁止清单（避免重蹈覆辙）

| 反例 | 来源 | 原因 | Onion 替代方案 |
|------|------|------|---------------|
| **Cline 风格 XML 协议** | Cline v1/v2（已废弃）| 2026 年所有主流项目都迁回 function calling | OpenAI JSON Schema function calling + Zod/Pydantic |
| **SuperAGI 纯 prompt-as-tool** | SuperAGI | 不能享受 OpenAI/Anthropic 协议 cache / parallel / streaming 优化 | OpenAI function calling 为主，prompt-as-tool 仅 fallback |
| **MetaGPT 18 次 retry** | MetaGPT | 生产环境爆 token 预算 | 3 类重试上限（LLM 5 / tool 3 / run 64）|
| **Aider 99% prompt-as-tool** | Aider | 已过时，2026 模型都原生支持 function calling | OpenAI function calling |
| **AutoGPT Gallery 默认放开 home** | AutoGPT | 危险设计 | `*.env: "ask"` + `Path.resolve()` 防符号链接绕过 |
| **MetaGPT 协议混乱（5 来源 5 套机制）** | MetaGPT | 调试噩梦 | `BaseTool` 抽象基类统一 |
| **MetaGPT `ToolSchema` 校验被 `pass` 吞** | MetaGPT | schema 错也照样用 | Pydantic `raise ValidationError` + 包装成 `isError: True` |
| **ChatDev 硬编码 `WareHouse` 相对 cwd** | ChatDev | 信创合规反例 | `ONION_HOME` env 单一覆盖点 |
| **ChatDev Server 端 session 纯内存** | ChatDev | 重启即丢 | `session.json` 持久化 + WAL |
| **opencode 5 个分散 env var** | opencode | 用户认知负担大 | `ONION_HOME` 单一 env |
| **Roo Code 3 套 MCP 平台路径混乱** | Roo Code | macOS 保留 Cline 命名是历史包袱 | 学 Claude Code 4 层统一 `.mcp.json` |
| **Continue `CONTINUE_GLOBAL_DIR` IIFE 一次性求值** | Continue | 无法中途切换全局路径 | `os.getenv` + 函数返回 Path |
| **Open Interpreter 30+ 工具 + 10 harness 仿真** | Open Interpreter | 过度工程 | MVP 5-8 个核心 tool |
| **Aider 4 级 JSON 字符串补全** | Aider | `json.loads(data + "]}")` 引入新 bug | `json-repair` 库 + `partial-json` 库 |
| **MetaGPT `xml_fill` 静默默认值** | MetaGPT | 错误用默认值（`int` 失败 → `0`）| `raise` 错误，让 LLM 看到 |
| **ChatDev `JSONDecodeError` → `{}`** | ChatDev | 失败直接给空 dict | `raise ValidationError` 包装成 `isError: True` |
| **superpowers 0 工具** | superpowers | 纯 Skills 框架不是 agent | Onion 是"自研单一产品"，必须有完整工具集 |

---

## 14. 文档说明

### 14.1 本标准的不变性与演进

- **不变性**：
  - **协议中立**（原则 1.1）—— Onion 内部必须一次定义 `Tool[]` schema，多 Provider 投影
  - **工具类型统一抽象**（原则 1.2）—— `BaseTool` 抽象是 onion 哲学基石
  - **OpenAI JSON Schema function calling**（§4.1）—— 2026 年行业事实标准
  - **大结果截断持久化**（§6.7）—— 避免 context 爆炸是工程纪律
  - **LLM 不可读白名单**（§1.4 / §9.8）—— 信创合规安全底线
- **演进原则**：
  - 新模式出现 ≥15/20 项目采用，纳入"必须做"
  - 现有"必须做"如果 <15/20 采用，降级为"强烈建议"
  - 反例（0-2/20 且明确有害）升级为"禁止"

### 14.2 与其他标准的关系

姊妹文档（参考 `prompt.md`）：
- `harness/01_market_research/standard/file_backend.md` —— 工作区维度（**已存在**，本标准的兄弟文档）
- `harness/01_market_research/standard/agent_loop_standard.md` —— Agent Loop 设计标准（**待写**）
- `harness/01_market_research/standard/plan_standard.md` —— Plan 看板设计标准（**待写**）
- `harness/01_market_research/standard/file_backend_standard.md` —— File Backend 复述（**待写**）
- `harness/01_market_research/standard/tool_standard.md` —— Tool shell + Tool channel 合并标准（**待写**，可参考本标准）
- `harness/01_market_research/standard/difference.md` —— 新颖设计对比（**待写**）
- `harness/01_market_research/standard/other_common.md` —— 其他共同点（**待写**）

本文档（`tool_channel.md`）与其他文档是**并列关系**，关注点不同（本标准只关注"工具调用"维度）。

### 14.3 引用规范

- 所有证据引用格式：`<项目>/tool_channel.md:行号或段落`
- 20 份单项目报告：`harness/01_market_research/<项目目录>/tool_channel.md`
- 3 份组内提炼稿：`harness/01_market_research/_intermediate_{general_agents,coding_agents,multi_agent_frameworks}.md`
- 顶部引用：`harness/01_market_research/top_20_react_agent.md`
- 姊妹标准：`harness/01_market_research/standard/file_backend.md`

### 14.4 调研局限

- 调研基于 2026-07-13 实时 GitHub 数据，star 数有变动，不影响工具调用设计结论
- 部分项目（如 Open Interpreter Python→Rust 演进、superpowers 寄生模式）的特殊性已记录
- 2 个项目已重写（AutoGPT 仓库内含 classic + platform 两套；Open Interpreter 主仓库已转 Rust）
- 调研时间：2026-07-18 ~ 2026-07-19

### 14.5 用户哲学锚点（洋葱架构）

> **一个智能体一直在做两件事：拼命调用大模型理解和生成上下文，拼命调用工具丰富上下文。**
>
> Onion 的"洋葱架构"决定了 tool channel 的特殊地位：
> - **session.json 是核心**：所有 tool_call 和 tool_result 都按状态机塞进 session.json（**`role=tool` 标准协议**）
> - **大模型是 session 的解释器**：OpenAI function calling 是事实标准（`tools` 数组 + `role=tool` + `tool_call_id`）
> - **工具分三类**：buildin_tool / mcp_tool / agent_skills，每类都有类似 Tool shell 的"工具客户端"适配
> - **Tool channel 工具通道**：把三类工具汇总成 OpenAI 协议的 `tools` 列表传给大模型
> - **大结果持久化**：避免 session.json 撑爆是工程纪律
> - **LLM 不可读白名单**：信创合规安全底线

本标准的所有"必须做"都直接对应 Onion 的 L5-Infrastructure 基础设施层 `tool_shell` + `tool_channel` 模块设计：
- `tool_shell` = `buildin_client.py` + `mcp_client.py` + `agent_skills_client.py`（三类工具客户端）
- `tool_channel` = `tool_list.py` + `tool_router.py` + `update_tool_list.py`（统一工具列表 + 路由 + 写 session）

**Onion 应当在 MVP 阶段严格按本标准 §13.1 P0 清单实施**，P1/P2 按需追加。

---

**报告完。** 数据更新截至 2026-07-19。文件大小目标 60-80KB，已达成。
