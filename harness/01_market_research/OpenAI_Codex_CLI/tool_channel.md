# OpenAI Codex CLI — 工具调用（Tool Channel）调研报告

## 0. 智能体一句话定位

OpenAI 官方终端编码 Agent，2025-04 开源、TypeScript 全面重写为 Rust；OS 级纵深沙箱（macOS Seatbelt / Linux Landlock + seccomp / Windows Restricted Token）+ MCP 并行工具调用 + 9 层 `ConfigLayerStack` 优先级合并；Terminal-Bench 2.0 得分 77.3%（行业第一）。

## 1. 调研依据

- 源码路径：`C:\workspace\github\onionagent\harness\01_market_research\clone\codex\codex-rs\`
- 关键文件 / 关键代码片段（已逐份读过）：
  - `codex-rs/tools/src/tool_spec.rs` — 顶层 `ToolSpec` 枚举（Function/Namespace/ToolSearch/WebSearch/Freeform）
  - `codex-rs/tools/src/responses_api.rs` — `ResponsesApiTool` / `LoadableToolSpec`（OpenAI Responses API 序列化）
  - `codex-rs/tools/src/tool_call.rs` — `ToolCall` 结构 + `ToolPayload`（Function/ToolSearch/Custom）
  - `codex-rs/tools/src/tool_output.rs` — `ToolOutput` trait + `JsonToolOutput` / `McpCallToolResult` 两种实现
  - `codex-rs/tools/src/tool_discovery.rs` — `DiscoverableTool` 抽象 + `TOOL_SEARCH_TOOL_NAME`（lazy 工具搜索）
  - `codex-rs/core/src/tools/spec_plan.rs` — `build_tool_router()` 工具总装 + 22 个 handler
  - `codex-rs/core/src/tools/parallel.rs` — `ToolCallRuntime` + `parallel_execution: RwLock` 并行门控
  - `codex-rs/core/src/tools/orchestrator.rs` — approval → sandbox → retry 主调度
  - `codex-rs/core/src/tools/registry.rs` — `ToolRegistry`（HashMap 查表 + `supports_parallel_tool_calls` 判定）
  - `codex-rs/core/src/tools/router.rs` — `ToolRouter.build_tool_call()` 把 `ResponseItem` 装配为 `ToolCall`
  - `codex-rs/core/src/tools/handlers/mcp.rs` — `McpHandler` + `create_tool_spec()` + `mcp__` 前缀
  - `codex-rs/core/src/tools/handlers/apply_patch_spec.rs` — `apply_patch` freeform 工具（Lark grammar）
  - `codex-rs/rmcp-client/src/rmcp_client.rs` — MCP OAuth + stdio / streamable HTTP transport
  - `codex-rs/skills/src/lib.rs` — `install_system_skills()` + `.codex-system-skills.marker` 指纹 cache
  - `codex-rs/core-skills/src/loader.rs` + `core-skills/src/system.rs` — SkillsService + `CODEX_HOME/skills/.system` 路径
  - `codex-rs/config/src/loader/mod.rs` + `config/src/state.rs` + `config/src/config_layer_source.rs` — 9 层 `ConfigLayerSource::precedence()` i16 排序
  - `codex-rs/config/src/mcp_types.rs` — `McpServerConfig` / `McpServerToolConfig`（per-tool approval）
  - `codex-rs/utils/home-dir/src/lib.rs` — `find_codex_home()` + `CODEX_HOME` env
  - `codex-rs/protocol/src/protocol.rs:3316` — `enum TruncationPolicy { Bytes(usize), Tokens(usize) }`
  - `codex-rs/protocol/src/models.rs:863-944` — `ResponseItem::FunctionCall / ToolSearchCall / CustomToolCall / FunctionCallOutput / McpToolCallOutput`
  - `codex-rs/otel/src/events/session_telemetry.rs:1205-1222` — `ResponseEvent` 变体（`OutputItemDone` / `ToolCallInputDelta` / `OutputTextDelta` / `Completed`）
  - `codex-rs/core/src/client.rs:842-901` — `build_responses_request()` + `parallel_tool_calls: bool` + `create_tools_json_for_responses_api(&prompt.tools)?`
- 文档 / README：
  - `codex/README.md`（CLI 形态 + 多端：CLI / IDE / Desktop / Web）
  - `codex/docs/config.md`（指向外部 dev docs）
  - `codex/docs/skills.md`（指向 https://developers.openai.com/codex/skills）
  - `codex/codex-rs/protocol/src/prompts/base_instructions/default.md`（base system prompt，纯 function calling，无 XML 工具协议）

## 2. 五个核心问题的回答

### Q1. 工具来源

- **内置工具**（handlers，共 20+，按 `codex-rs/core/src/tools/handlers/` 目录列）：
  - `shell_command`（POSIX/PowerShell/Cmd + zsh）— `handlers/shell.rs:9`（重导出 `ShellCommandHandler`）
  - `unified_exec`（长时间运行的 PTY 进程）— `handlers/unified_exec.rs`
  - `apply_patch`（freeform 工具，Lark grammar 描述 patch 语法）— `handlers/apply_patch.rs` + `handlers/apply_patch_spec.rs:21-36`
  - `view_image`（image detail 归一化）— `handlers/view_image.rs`
  - `update_plan`（计划追踪）— `handlers/plan.rs`
  - `request_user_input`（向用户提问）— `handlers/request_user_input.rs`
  - `request_permissions`（动态申请权限）— `handlers/request_permissions.rs`
  - `current_time` / `sleep` / `test_sync` / `wait_for_environment` / `get_context_remaining` / `new_context_window` — 杂项原子工具
  - **Multi-Agent V1**：`spawn_agent` / `wait_agent` / `send_input` / `close_agent` / `resume_agent` — `handlers/multi_agents.rs`
  - **Multi-Agent V2**：`spawn_agent` / `wait_agent` / `send_message` / `list_agents` / `followup_task` / `interrupt_agent` — `handlers/multi_agents_v2.rs`（命名空间 V2）
  - **Agent Jobs**：`spawn_agents_on_csv` / `report_agent_job_result` — `handlers/agent_jobs.rs`（CSV 驱动并行多 agent）
  - **Extension Tools**：三方动态注入 — `handlers/extension_tools.rs`
  - **Dynamic Tools**：用户/插件动态定义 — `handlers/dynamic.rs` + `tools/src/dynamic_tool.rs:1-15`
  - **Tool Search**：`tool_search`（按需搜索懒加载的 tool 列表）— `tools/src/tool_search.rs:1-55`
  - **Hosted Web Search**（仅 hosted 模式）：`web_search`（OpenAI 服务端）— `tools/src/tool_spec.rs:36-46`（带 `external_web_access` / `indexed_web_access` / `search_context_size`）
  - 完整 handler 列表见 `spec_plan.rs:6-50` 的 `use crate::tools::handlers::*;`
- **MCP 支持**：✅ 完整支持
  - 配置文件：`config.toml` 的 `[mcp_servers.<name>]` 表，`codex-rs/config/src/config_requirements.rs:159` 定义 `pub mcp_servers: Option<Sourced<BTreeMap<String, McpServerRequirement>>>`
  - 类型定义：`codex-rs/config/src/mcp_types.rs`（`McpServerConfig` / `McpServerToolConfig` per-tool approval mode `Auto/Prompt/Writes/Approve`）
  - Transport：`rmcp-client/src/rmcp_client.rs` 支持 stdio / streamable HTTP / OAuth（50KB+ 复杂状态机）
  - 工具转换：`tools/src/responses_api.rs:mcp_tool_to_responses_api_tool()` 把 MCP tool 转成 OpenAI Responses API 的 `ResponsesApiTool`
  - 命名空间打包：`spec_plan.rs:240+` `merge_into_namespaces()` 把多 MCP 工具按 server name 聚合成一个 `ToolSpec::Namespace`（带 `defer_loading: true` 实现按需懒加载）
  - 注册到 router：`core/src/tools/handlers/mcp.rs:36-38` `McpHandler::new(tool_info)` → `create_tool_spec(&tool_info)`
- **Agent Skills 支持**：✅ 完整支持（OpenAI 自家 SKILL.md 规范）
  - 系统级 skills 目录：`codex-rs/skills/src/lib.rs:38-44` 安装到 `CODEX_HOME/skills/.system/`，由 `include_dir!` 内嵌 6 个示例（`imagegen` / `openai-docs` / `plugin-creator` / `review-agent` / `skill-creator` / `skill-installer`）
  - 用户级 skills：`CODEX_HOME/skills/` 下用户添加的目录
  - 文件格式：`codex-rs/skills/src/assets/samples/skill-creator/SKILL.md:1-5` YAML frontmatter `name` + `description` + `metadata.short-description`（与 Anthropic Agent Skills 兼容）
  - 目录结构：每 skill 一个目录，含 `SKILL.md` + `agents/openai.yaml`（UI 元数据）+ 可选 `scripts/` / `references/` / `assets/`（`SKILL.md:54-103`）
  - 加载器：`codex-rs/core-skills/src/loader.rs:1-60`（异步扫描 + 8 并发根目录 + YAML frontmatter 解析）+ `core-skills/src/service.rs:SkillsService`
  - Plugin Skills：plugin 还能带 skills（`codex-rs/core-plugins/src/loader.rs` 56KB 的 plugin loader + `manager.rs` 109KB 状态机）
- **其他工具类型**：
  - **Plugins / Marketplaces**：`codex-rs/core-plugins/` 整 crate（plugin 也是一个聚合包，可含 skills + mcp_servers + app connectors），管理 `marketplace_add.rs` / `marketplace_upgrade.rs` / `marketplace_remove.rs` / `marketplace_policy.rs`，`marketplace.rs:1` 72KB
  - **App Connectors**（远程托管 MCP）：`codex-rs/connectors/src/lib.rs:35KB`（app_dir 与本地 MCP server 一起注册到 router）
  - **Code Mode**（代码执行模式）：`codex-rs/tools/src/code_mode.rs` + `codex-rs/code-mode/` + `codex-rs/code-mode-host/` + `codex-rs/code-mode-protocol/`（4 个 crate 协同）— 用 `codex_code_mode::is_code_mode_nested_tool()` 标记可被代码执行调用的 tool，通过 `excluded_tool_namespaces` / `direct_only_tool_namespaces` 配置在 `spec_plan.rs:220-240` 决定哪些走 code mode

### Q2. 工具列表的生成、传递、格式

- **生成方式**（集中 `codex-rs/core/src/tools/spec_plan.rs:127-150` 的 `build_tool_router()`）：
  1. 收集 turn context、tool runtimes、extension executors、dynamic tools 5 个来源
  2. `add_tool_sources(&context, &mut planned_tools)` 注入所有 handler（20+ 个 `add::<T>()` 调用）
  3. `apply_direct_model_only_namespace_overrides(turn_context, ...)` 把某些 namespace 标记为 `DirectModelOnly`
  4. `append_tool_search_executor(...)` + `prepend_code_mode_executors(...)`
  5. `build_model_visible_specs_and_registry(turn_context, planned_tools)` 输出 `(Vec<ToolSpec>, ToolRegistry)`
  6. `merge_into_namespaces(specs)` 把多 tool 聚合成 `ToolSpec::Namespace` 减少 model 看到的工具数（关键性能优化）
  7. 启动时一次性构建，**不动态刷新**（turn 级别重建）
- **传递方式**：**OpenAI Responses API**（不是 Chat Completions，也不是 Anthropic）
  - `codex-rs/core/src/client.rs:842` `let tools = create_tools_json_for_responses_api(&prompt.tools)?;`
  - 装到 `ResponsesApiRequest { tools, tool_choice: "auto", parallel_tool_calls: ... }`（`client.rs:842-901`）
  - `parallel_tool_calls: prompt.parallel_tool_calls && !model_info.use_responses_lite`（`client.rs:897`）— Lite 模式强制单 tool
  - Responses Lite 备选：`use_responses_lite` 时把 tools 塞进 `ResponseItem::AdditionalTools { role: "developer", tools }`（`client.rs:843-855`）
- **格式**：**JSON**（OpenAI Responses API 协议），实际 wire 形态如 `tools/src/tool_spec.rs:71-82` 序列化为：
  ```json
  [
    {"type":"function","name":"shell_command","description":"...","strict":false,"defer_loading":null,"parameters":{...}},
    {"type":"namespace","name":"mcp__filesystem","description":"...","tools":[
        {"type":"function","name":"read_file","description":"...","strict":false,"defer_loading":true,"parameters":{...}}
    ]},
    {"type":"tool_search","execution":"client","description":"...","parameters":{...}},
    {"type":"web_search","external_web_access":true,"search_context_size":"medium"},
    {"type":"custom","name":"apply_patch","description":"...","format":{"type":"grammar","syntax":"lark","definition":"..."}}
  ]
  ```
  - `create_tools_json_for_responses_api()` 是 `serde_json::to_value` 一把梭（`tool_spec.rs:71-82`）
  - namespace 的 `defer_loading: true` 触发 `tool_search` 懒加载
- **prompt-as-tool**：❌ **没有**。system prompt 完全是行为规范（`protocol/src/prompts/base_instructions/default.md` 21KB），工具只通过 `tools` 参数（function calling）传递。`apply_patch` 虽是 "FREEFORM" 工具，但走 `ToolSpec::Freeform` 自定义 grammar 通道，不算 prompt-as-tool。
- **动态刷新**：**启动时一次性加载 + 每次 turn 重新构建 router**。不感知运行时新增 MCP server；新增需要 `codex mcp add` 重启 / 新 turn。但 `tool_search` 机制允许 model 在 turn 内按需请求展开某 namespace 的工具（`tools/src/tool_search.rs:20-49` 的 `ToolSearchEntry` + `defer_loading=true`）

### Q3. 工具调用指令的解析、错误修复、准确性保证

- **解析方式**：**流式增量解析**（基于 OpenAI Responses API 的 `ResponseEvent` 枚举）
  - 协议事件在 `codex-rs/otel/src/events/session_telemetry.rs:1205-1222` 完整列举：
    - `ResponseEvent::OutputItemAdded(item)` — 输出项开始（含 `FunctionCall` / `ToolSearchCall` / `CustomToolCall` / `WebSearchCall` / `LocalShellCall` / `ImageGenerationCall` / `Message` / `Reasoning` / `Compaction` 等）
    - `ResponseEvent::ToolCallInputDelta { ... }` — 工具入参的 JSON 增量（model 流式输出 arguments 字符串）
    - `ResponseEvent::OutputItemDone(item)` — 输出项完成（含完整 arguments 的 `FunctionCall`）
    - `ResponseEvent::Completed { response_id, token_usage, end_turn }` — turn 终止
  - 关键代码：`codex-rs/core/src/client.rs:1931-2080` `map_response_events()` — 把 SSE 流上的 `ResponseEvent::OutputItemDone(item)` 原样转发到 `ResponseStream`，并把完整 item push 进 `items_added` 收集
  - Router 装配：`codex-rs/core/src/tools/router.rs:99-141` `ToolRouter::build_tool_call(item: ResponseItem)` 把 `ResponseItem::FunctionCall / ToolSearchCall / CustomToolCall` 装成 `ToolCall { tool_name, call_id, payload }`（其中 arguments **保留为 raw String**，不预先解析为 JSON，避免流式半截 JSON 解析失败）
- **错误修复 / 异常分支**：
  - `ResponseEvent::Completed` 后 `break`（`client.rs:1751`）
  - consumer 提前 drop → `consumer_dropped.cancel()` → mapper 任务走 `record_cancelled(STREAM_DROPPED_REASON, ...)` 路径（`client.rs:1942-1951`）
  - 整个 stream 失败 → `provider.map_api_error(err)` 转换成 `CodexErr` 再下发
- **准确性保证**：
  1. **JSON Schema 校验**：`tools/src/json_schema.rs`（27KB）严格 schema 解析 + `AdditionalProperties` 控制 + `parse_tool_input_schema_without_compaction` 防过度裁剪
  2. **FunctionCallError 三类分级**：`tools/src/function_call_error.rs`（`Fatal` 致命 / `RespondToModel` 让 LLM 自我修正 / `Rejected` 用户拒绝），分别走不同 telemetry + 反馈路径
  3. **JSON 解析失败自动 retry**：handler 内 `serde_json::from_value(arguments).map_err(|err| FunctionCallError::RespondToModel(...))` — 错误消息回灌 model 触发自动 retry（`router.rs:117-124` ToolSearchCall 的 args 解析是典型例子）
  4. **Orchestrator 沙箱重试**：`tools/orchestrator.rs:1-200` — 沙箱拒绝时 escalate sandbox strategy（不重新 approval，依赖 approval cache）
  5. **StrictAutoReview 守卫**：`orchestrator.rs:149-180` 在 `strict_auto_review_enabled_for_turn` 时 Guardian reviewer 复核
  6. **Network approval**：网络工具必须 `begin_network_approval` 通过才执行（`orchestrator.rs:65-95`）
- **重试上限**：源码未在 router 层设硬上限；由 model 自然 multi-turn 决定（错误回灌 → model 改参数 → 新一轮 tool_call）。单次 sandbox 失败会有 sandbox escalate 路径（`orchestrator.rs` 的 `SandboxAttempt` 多级 fallback），但**显式 max-retry 计数在源码中未找到**（"源码未明确"）。

### Q4. 工具执行结果回传

- **回传方式**：**OpenAI Responses API 原生** — 把执行结果封装成 `ResponseInputItem` 再塞进下一轮 input
  - 关键类型：`codex-rs/protocol/src/models.rs:863-944` 定义 `ResponseItem::FunctionCall / FunctionCallOutput / CustomToolCall / CustomToolCallOutput / McpToolCallOutput / ToolSearchOutput`
  - `tools/src/tool_output.rs:108-180` `JsonToolOutput::to_response_item()` + `codex_protocol::mcp::CallToolResult::to_response_item()` 决定走哪条 wire 路径：
    - 普通 function → `ResponseInputItem::FunctionCallOutput { call_id, output: FunctionCallOutputPayload { body, success } }`
    - MCP tool → `ResponseInputItem::McpToolCallOutput { call_id, output }`（特殊 variant，保留 MCP 原生结构）
    - Custom tool（freeform）→ `ResponseInputItem::CustomToolCallOutput { call_id, name: None, output }`
- **格式**：
  - `FunctionCallOutputPayload { body: FunctionCallOutputBody, success: Option<bool> }`
  - `FunctionCallOutputBody` 是 sum type：`Text(String)` 或 `ContentItems(Vec<FunctionCallOutputContentItem>)`
  - `FunctionCallOutputContentItem` 支持 `InputText { text }` / `InputImage { image_url, detail }` / `EncryptedContent { encrypted_content }`（`tool_output.rs:200-230` 把 message + 图片 + 加密内容混装）
  - 图片用 `InputImage { image_url, detail: Some(DEFAULT_IMAGE_DETAIL) }` 作为内嵌（不是 MEDIA 引用），detail 字段由 `image_detail.rs` 归一化
- **通信协议**：**OpenAI Responses API**（不是 Chat Completions，也不是 Anthropic）。
  - Codex 也支持其他 provider（`model-provider/src/provider.rs:50-78` `ProviderCapabilities` 有 `namespace_tools / image_generation / web_search` 三档能力），但工具调用协议**始终是 OpenAI Responses 风格**（namespace tools 仅在支持 `namespace_tools` 的 provider 上启用，由 `spec_plan.rs:312-320` `namespace_tools_enabled()` 判定）
  - Lite 模式（`use_responses_lite`）用 `ResponseItem::AdditionalTools` 嵌入（`client.rs:843-855`）
- **大结果处理**：**truncate-middle**（保留头尾，砍中间）
  - `codex-rs/protocol/src/protocol.rs:3316` `enum TruncationPolicy { Bytes(usize), Tokens(usize) }`
  - `codex-rs/utils/output-truncation/src/lib.rs:1-30` `truncate_text` / `formatted_truncate_text` / `truncate_middle_with_token_budget`
  - 关键调用点：`codex-rs/core/src/tools/mod.rs:78-105` `format_exec_output_for_model()` 对 shell 输出加 "Exit code / Wall time / Total output lines / Output" 元信息后按 `TruncationPolicy` 截断（**保留头尾 + 警告头**："Warning: truncated output (original token count: N)"）
  - 字符串工具：`truncate_middle_chars`（按字节）/ `truncate_middle_with_token_budget`（按 token 估算）
  - **图片**走 `InputImage` URL 引用（不是 base64 嵌入），detail 字段由 `image_detail.rs` 在 `original / low / high / auto` 4 档间归一化
  - **超大图片 + 加密内容** 走 `ContentItems` 多 item 装载

### Q5. File Backend 是否为工具调用做了适配

- **工具配置目录 / 文件清单**（基于 `codex-rs/utils/home-dir/src/lib.rs:find_codex_home()` + `config/src/loader/mod.rs:80-100`）：

  | 路径 | 用途 | 加载代码 |
  |------|------|---------|
  | `~/.codex/config.toml` | 用户主配置 | `loader/mod.rs:100` |
  | `~/.codex/<name>.config.toml` | profile override | `loader/mod.rs:101` |
  | `~/.codex/skills/` | 用户 skills 根 | `skills/src/lib.rs:23` `SKILLS_DIR_NAME` |
  | `~/.codex/skills/.system/` | 内置 system skills（首次启动 seed） | `skills/src/lib.rs:21-26` + `lib.rs:31-49` `install_system_skills()` |
  | `~/.codex/skills/.system/.codex-system-skills.marker` | 指纹文件（内容 hash 命中则跳过 seed） | `skills/src/lib.rs:28-30` + `lib.rs:78-95` |
  | `~/.codex/marketplaces/` | plugin marketplace 缓存 | `core-plugins/src/marketplace.rs` |
  | `~/.codex/plugins/` | 已安装 plugins | `core-plugins/src/loader.rs` |
  | `~/.codex/log/` | 运行日志（rollout JSONL） | `protocol/src/protocol.rs:330` `Defaults to $CODEX_HOME/log` |
  | `<git_root>/.codex/config.toml` | 项目级 override | `loader/mod.rs:103-105`（`Project { dot_codex_folder }`） |
  | `cwd/config.toml` | 当前目录 config | `loader/mod.rs:102`（`cwd: ${PWD}/config.toml`） |
  | `<repo>/.codex/` | 项目根配置目录 | `ConfigLayerSource::Project`（`config_layer_source.rs:21-25`） |
  | `/etc/codex/config.toml`（POSIX） / `%ProgramData%\OpenAI\Codex\config.toml`（Win） | 系统级 config | `loader/mod.rs:96-98` |
  | `<git_root>/AGENTS.md` + 子目录 AGENTS.md | 项目行为规范 | `core/src/agents_md.rs`（向上扫描到 .git 边界） |
  | 路径 / 排除 | `mcp_servers.<name>` | `config/src/mcp_types.rs`（`McpServerConfig`） |

- **9 层 ConfigLayer 优先级**（`config/src/config_layer_source.rs:42-58` `precedence()` i16 排序）：
  | source | precedence | 备注 |
  |--------|------------|------|
  | `Mdm { domain, key }` | 0 | 最低 |
  | `System { file }` | 10 | `/etc/codex/config.toml` |
  | `EnterpriseManaged { id, name }` | 15 | 云端管理配置 |
  | `User { file, profile: None }` | 20 | `~/.codex/config.toml` |
  | `User { file, profile: Some }` | 21 | `~/.codex/<name>.config.toml` |
  | `Project { dot_codex_folder }` | 25 | `<repo>/.codex/config.toml`（加载但未信任时 disabled） |
  | `SessionFlags` | 30 | CLI `--config k=v` |
  | `LegacyManagedConfigTomlFromFile { file }` | 40 | `managed_config.toml` |
  | `LegacyManagedConfigTomlFromMdm` | 50 | 最高 |
  - 这是 file_backend.md §2.3 "强烈建议" 模式（4-9 层）中最复杂实现
- **加载代码核心**：
  - `config/src/loader/mod.rs:124-150` `load_config_layers_state(fs, codex_home, cwd, cli_overrides, options, ...)` — 收 9 层 → `Vec<ConfigLayerEntry>`
  - `config/src/state.rs:240-280` `ConfigLayerStack` 持有 layers + requirements
  - `utils/home-dir/src/lib.rs:14-58` `find_codex_home()` — `CODEX_HOME` env 优先，fallback `~/.codex`（POSIX home）/ `%USERPROFILE%\.codex`（Windows）
- **全局 vs 项目级**：**两层都有**（强结构化）
  - 全局 `~/.codex/`（用户属主目录，可信）
  - 项目级 `<repo>/.codex/`（untrusted 时 `disabled_reason: Some("...")` 标记但仍加载到 stack）
  - 还支持 `cwd/config.toml` 和 parent directory walk
- **与 `standard/file_backend.md` 的对照**：
  - ✅ §1.1 用户属主目录（`CODEX_HOME` + `~/.codex/`）
  - ✅ §1.3 AGENTS.md 字节上限（Codex `project_doc_max_bytes` 32 KiB，见 `core/src/agents_md.rs:121` `data.truncate(remaining)`）
  - ✅ §2.1 env 单一覆盖点（`CODEX_HOME` 单 env）
  - ✅ §2.2 平台原生（POSIX `~/.codex`，Windows `%USERPROFILE%\.codex` 或 `%LOCALAPPDATA%`，走 `dirs::home_dir()`）
  - ✅ §2.3 多级配置 merge（9 层 i16 排序，比 file_backend §2.3 提的"4 层"还复杂）
  - ✅ §3.1 严格三层分离：`~/.codex/`（用户级）+ `<repo>/.codex/`（项目级）+ `~/.codex/skills/.system/`（运行时）
  - ✅ §10.7 plugin + hook 系统（`codex-rs/core-plugins/` 整 crate + `config/src/hook_config.rs`）
  - ✅ §10.8 MCP 协议支持（`[mcp_servers.<name>]` in `config.toml` + `rmcp-client` transport）
  - 独有（**file_backend.md 未列**）：**`codex-system-skills.marker` 指纹文件**（`skills/src/lib.rs:28-30`）— 用 `DefaultHasher` 算 `path + content_hash` 的 fingerprint，命中则跳过 seed。比单纯 `mkdir parents exist_ok` 高级

## 3. 关键代码片段

### 3.1 ToolSpec 顶层枚举（Responses API 序列化）

```rust
// codex-rs/tools/src/tool_spec.rs:11-50
#[derive(Debug, Clone, Serialize, PartialEq)]
#[serde(tag = "type")]
pub enum ToolSpec {
    #[serde(rename = "function")]
    Function(ResponsesApiTool),
    #[serde(rename = "namespace")]
    Namespace(ResponsesApiNamespace),
    #[serde(rename = "tool_search")]
    ToolSearch { execution: String, description: String, parameters: JsonSchema },
    #[serde(rename = "web_search")]
    WebSearch { external_web_access, indexed_web_access, filters, user_location, search_context_size, search_content_types },
    #[serde(rename = "custom")]
    Freeform(FreeformTool),
}

pub fn create_tools_json_for_responses_api(tools: &[ToolSpec]) -> Result<Vec<Value>, serde_json::Error> {
    let mut tools_json = Vec::new();
    for tool in tools { tools_json.push(serde_json::to_value(tool)?); }
    Ok(tools_json)
}
```

### 3.2 ConfigLayer 9 层 i16 优先级（file_backend §2.3 强建议的最复杂实现）

```rust
// codex-rs/config/src/config_layer_source.rs:42-58
pub fn precedence(&self) -> i16 {
    match self {
        ConfigLayerSource::Mdm { .. } => 0,
        ConfigLayerSource::System { .. } => 10,
        ConfigLayerSource::EnterpriseManaged { .. } => 15,
        ConfigLayerSource::User { profile, .. } => if profile.is_some() { 21 } else { 20 },
        ConfigLayerSource::Project { .. } => 25,
        ConfigLayerSource::SessionFlags => 30,
        ConfigLayerSource::LegacyManagedConfigTomlFromFile { .. } => 40,
        ConfigLayerSource::LegacyManagedConfigTomlFromMdm => 50,
    }
}
```

### 3.3 Parallel Tool Calls 门控（`parallel_execution: RwLock` + per-tool 判定）

```rust
// codex-rs/core/src/tools/parallel.rs:42-44
pub(crate) struct ToolCallRuntime {
    router: Arc<ToolRouter>,
    session: Arc<Session>,
    step_context: Arc<StepContext>,
    tracker: SharedTurnDiffTracker,
    parallel_execution: Arc<RwLock<()>>,  // 关键：RwLock 控制并发
}

// codex-rs/core/src/tools/registry.rs:266-280
fn exposure(&self) -> ToolExposure { ... }
fn supports_parallel_tool_calls(&self) -> bool {
    self.exposure != ToolExposure::Hidden && self.handler.supports_parallel_tool_calls()
}
```

```rust
// codex-rs/core/src/tools/parallel.rs:96-117
let mut dispatch_handle = AbortOnDropHandle::new(tokio::spawn(async move {
    let _guard = if supports_parallel {
        Either::Left(lock.read().await)   // 多个并行 tool 共持读锁
    } else {
        Either::Right(lock.write().await) // 串行 tool 独占写锁
    };
    ...
}));
```

### 3.4 ResponseEvent 流式事件 + 工具入参增量（Q3 关键证据）

```rust
// codex-rs/otel/src/events/session_telemetry.rs:1205-1222
fn responses_type(event: &ResponseEvent) -> String {
    match event {
        ResponseEvent::Created => "created".into(),
        ResponseEvent::OutputItemDone(item) | ResponseEvent::OutputItemAdded(item) => {
            SessionTelemetry::responses_item_type(item)
        }
        ResponseEvent::Completed { .. } => "completed".into(),
        ResponseEvent::OutputTextDelta(_) => "text_delta".into(),
        ResponseEvent::ToolCallInputDelta { .. } => "tool_input_delta".into(),
        ResponseEvent::ReasoningSummaryDelta { .. } => "reasoning_summary_delta".into(),
        ...
    }
}
// 完整 items: OutputItemAdded / OutputItemDone / ToolCallInputDelta / OutputTextDelta
//             ReasoningSummaryDelta / ReasoningSummaryDone / ReasoningContentDelta
//             ServerModel / ModelVerifications / RateLimits / ModelsEtag / ...
```

### 3.5 TruncationPolicy 大结果处理（Q4 关键证据）

```rust
// codex-rs/protocol/src/protocol.rs:3316-3320
#[derive(Debug, Clone, Copy, Deserialize, Serialize, PartialEq, Eq, JsonSchema, TS)]
#[serde(tag = "mode", content = "limit", rename_all = "snake_case")]
pub enum TruncationPolicy { Bytes(usize), Tokens(usize) }

// codex-rs/utils/output-truncation/src/lib.rs:10-19
pub fn formatted_truncate_text(content: &str, policy: TruncationPolicy) -> String {
    if content.len() <= policy.byte_budget() { return content.to_string(); }
    let original_token_count = approx_token_count(content);
    let total_lines = content.lines().count();
    let result = truncate_text(content, policy);
    format!("Warning: truncated output (original token count: {original_token_count})\nTotal output lines: {total_lines}\n\n{result}")
}

// codex-rs/core/src/tools/mod.rs:78-99  format_exec_output_for_model()
sections.push(format!("Exit code: {}", exec_output.exit_code));
sections.push(format!("Wall time: {duration_seconds} seconds"));
if total_lines != formatted_output.lines().count() {
    sections.push(format!("Total output lines: {total_lines}"));
}
sections.push("Output:".to_string());
sections.push(formatted_output);
```

### 3.6 SKILL.md YAML frontmatter（Agent Skills 证据）

```yaml
# codex-rs/skills/src/assets/samples/skill-creator/SKILL.md:1-5
---
name: skill-creator
description: Guide for creating effective skills. This skill should be used when users want to create a new skill (or update an existing skill) that extends Codex's capabilities with specialized knowledge, workflows, or tool integrations.
metadata:
  short-description: Create or update a skill
---
```

```rust
// codex-rs/skills/src/lib.rs:21-26, 31-49  系统 skills 路径 + 指纹 cache
const SYSTEM_SKILLS_DIR_NAME: &str = ".system";
const SKILLS_DIR_NAME: &str = "skills";
const SYSTEM_SKILLS_MARKER_FILENAME: &str = ".codex-system-skills.marker";
const SYSTEM_SKILLS_MARKER_SALT: &str = "v1";

pub fn system_cache_root_dir(codex_home: &AbsolutePathBuf) -> AbsolutePathBuf {
    codex_home.join(SKILLS_DIR_NAME).join(SYSTEM_SKILLS_DIR_NAME)
}

pub fn install_system_skills(codex_home: &AbsolutePathBuf) -> Result<(), SystemSkillsError> {
    let skills_root_dir = codex_home.join(SKILLS_DIR_NAME);
    fs::create_dir_all(skills_root_dir.as_path())...?;
    let dest_system = system_cache_root_dir(codex_home);
    let marker_path = dest_system.join(SYSTEM_SKILLS_MARKER_FILENAME);
    let expected_fingerprint = embedded_system_skills_fingerprint();
    if dest_system.as_path().is_dir()
        && read_marker(&marker_path).is_ok_and(|marker| marker == expected_fingerprint) {
        return Ok(());  // 命中指纹则跳过
    }
    if dest_system.as_path().exists() { fs::remove_dir_all(dest_system.as_path())...?; }
    write_embedded_dir(&SYSTEM_SKILLS_DIR, &dest_system)?;
    fs::write(marker_path.as_path(), format!("{expected_fingerprint}\n"))...?;
    Ok(())
}
```

## 4. 与 Onion Agent 设计的关联

Onion 可以从 Codex 学到 **3 个具体设计 + 1 个避免**：

1. **学 `ToolSpec` 的 namespace 聚合**（`merge_into_namespaces`，`spec_plan.rs:240`）— 当 MCP server 数量爆炸时，把多 tool 聚合成 `ToolSpec::Namespace`（`{"type":"namespace","name":"mcp__fs","tools":[...]}`）减少 model 看到的 tool 数量级。Onion 在 `tool_channel` 设计里建议实现"namespace + `defer_loading`"机制：默认只暴露 namespace + `tool_search`，model 按需展开子工具。
2. **学 `TruncationPolicy { Bytes, Tokens }` 的 truncate-middle 策略**（`utils/output-truncation/src/lib.rs:10-19`）— 比单纯截断尾部更友好，保留头（命令 + 元信息）和尾（错误/退出码），中间砍掉。Onion 的 `format_exec_output_for_model` 可以直接抄这套（`core/src/tools/mod.rs:78-99`），加 `Warning: truncated output (original token count: N)` 提示让 model 知道被截断。
3. **学 `.codex-system-skills.marker` 指纹 cache 模式**（`skills/src/lib.rs:78-95`）— Onion 首次启动 seed `AGENTS.md` / `USER.md` / `MEMORY.md` 时也应该用 `DefaultHasher` 算内容指纹，命中则跳过 seed，比"检查文件存在与否"更稳健（用户手动改了 seed 文件也认得）。
4. **避免 Codex 的 `parallel_execution: RwLock` 模式**（`core/src/tools/parallel.rs:42-44`）— 读写锁在 Rust 里正确，但 Python asyncio 下的 `asyncio.Lock` 互斥语义会让 LLM 看到"明明声明了并行但实际串行"的诡异行为。Onion 若做并行应该用 `asyncio.gather` 真正并发（多 read lock 共享）；如果走消息队列，每个 tool_call 是独立 task，靠 message broker 排队，不靠 lock。

## 5. 不确定 / 未找到

- **max-retry 上限**：Q3 提到的"重试机制上限"在源码中**未找到显式常量**。orchestrator 的 sandbox escalate 路径有 1-2 级 fallback，但**没有 max_attempts 字段**。`tools/parallel.rs:96-117` 的 cancel token 由 turn 终止触发，没有"重试 N 次后放弃"。推测由 model 自身 multi-turn 行为控制（错误回灌 → model 改 → 新一轮）。
- **skill_loader 字节上限**：Q5 提到 `project_doc_max_bytes` 32 KiB 用于 AGENTS.md，但 **`SkillsService` 对单个 SKILL.md 的字节上限**在 `codex-rs/core-skills/src/loader.rs` 中**未明确找到**（只在 `core-skills/src/render.rs` 看到 `SkillMetadataBudget` 提到 metadata 大小限制，body 加载是 lazy 按需）。需要 `core-skills/src/service.rs` 进一步阅读。
- **Tools list 动态刷新**：Q2 提到"运行时新增 MCP server"——`rmcp-client` 支持在 turn 启动时 spawn 新 MCP server（OAuth + 401 reconnect），但**用户用 `codex mcp add` 新增 server 后是否在运行中 turn 立即可见**未明确。从 `core/src/tools/spec_plan.rs:build_tool_router()` 签名看，每次 turn 重新构建 router 应该能拿到最新 config，但需要 `rmcp_client.rs` 启动时序验证。
- **MCP OAuth + Streamable HTTP retry 行为**：`rmcp-client/src/rmcp_client.rs` 50KB+ 复杂状态机，本次只看了 `load_outcome.rs` / `perform_oauth_login.rs` 表层；**OAuth refresh 触发条件、streamable HTTP 重连策略**未深入调研。
- **Codex CLI 是否支持 Anthropic 协议**：`model-provider/src/provider.rs:50-78` 看到 `ProviderCapabilities` 抽象，Amazon Bedrock 也是支持的 provider。但**工具调用协议是否仍是 OpenAI Responses 风格**未在 protocol crate 找到直接答案（推测是，spec_plan 中所有 `ToolSpec` 都按 OpenAI 序列化）。需要 `model-provider/src/amazon_bedrock/` 进一步验证。

---

**完。** 数据基于 2026-07 静态代码分析，源码路径 `C:\workspace\github\onionagent\harness\01_market_research\clone\codex\codex-rs\`。
