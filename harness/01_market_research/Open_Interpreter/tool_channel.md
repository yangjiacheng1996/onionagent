# Open Interpreter — 工具调用（Tool Channel）调研报告

> 调研对象：`github.com/openinterpreter/open-interpreter`（本地 clone `clone\open-interpreter`，main = `5ce1320`；**仓库已被重写为 OpenAI Codex 的 Rust fork**，原 Python 项目 tag 在 `v0.4.2`）
> 调研时间：2026-07-18，调研方式：源码静态分析 + `git show v0.4.2:...` 还原 Python 时代

---

## 0. 智能体一句话定位

**Open Interpreter** = "自然语言 → 本地代码执行 Agent"。**Python 时代**（v0.4.2, 2024-10）是基于 LiteLLM + 9 语言 REPL 的极简本地 code interpreter；**Rust 时代**（rust-v0.0.29, 2026）是基于 OpenAI Codex 的产品级 coding agent，自带 30+ 内置工具 + 完整 MCP + Skills + 10 个 harness 仿真 + OS 级沙箱 + 跨协议 wire。本报告以 Rust 时代（当前 main）为主，Python 时代仅作 LMC 协议对照。

---

## 1. 调研依据

- **源码**：`C:\workspace\github\onionagent\harness\01_market_research\clone\open-interpreter\`
- **关键文件**：
  - `codex-rs/core/src/tools/spec_plan.rs:142-145`（工具路由装配 + 30+ handler 注册）
  - `codex-rs/core/src/tools/handlers/{mod.rs,shell.rs,apply_patch.rs,plan.rs,mcp.rs,harness_aliases.rs(198KB),kimi_code_aliases.rs}`
  - `codex-rs/core/src/tools/{registry.rs,orchestrator.rs,context.rs}` —— CoreToolRuntime trait / approval+沙箱 retry / ToolPayload
  - `codex-rs/core-skills/src/{loader.rs(42KB),model.rs,render.rs}` —— SkillMetadata / 三 scope
  - `codex-rs/protocol/src/models.rs:1883` —— `FunctionCallOutputPayload` 结构化多模态
  - `codex-rs/utils/output-truncation/src/lib.rs` + `codex-rs/protocol/src/protocol.rs:3278` —— TruncationPolicy
  - `codex-rs/chat-wire-compat/src/{request.rs,client.rs}` —— Responses ↔ Chat 互转
  - `codex-rs/config/src/config_toml.rs:267-271` —— `mcp_servers: HashMap<String, McpServerConfig>`
  - `codex-rs/tools/src/function_call_error.rs` —— `FunctionCallError::{RespondToModel, Fatal}`
  - Python 时代：`git show v0.4.2:interpreter/core/llm/run_tool_calling_llm.py`（流式 partial JSON 解析）
- **文档**：`docs/mcp.md`、`docs/skills.md`、`docs/agents_md.md`、`docs/harness.md`、`docs/config.md`

---

## 2. 五个核心问题的回答

### Q1. 工具来源

#### 1.1 内置工具（30+，按 handler 列）

- **基础执行（4）**：`ShellCommandHandler`（`shell.rs`）/ `ExecCommandHandler` + `WriteStdinHandler`（`unified_exec.rs`）/ **`ApplyPatchHandler`（`apply_patch.rs`）—— Codex V4A freeform patch 协议（Lark grammar + 结构化 diff，不是 JSON）**
- **文件 / 上下文（5）**：`ViewImageHandler` / `CurrentTimeHandler` / `SleepHandler` / `GetContextRemainingHandler` / `NewContextWindowHandler`
- **交互 / 权限（4）**：`RequestUserInputHandler`（让用户做选择题）/ `RequestPermissionsHandler`（追加 network/file_system 权限）/ `PlanHandler`（`update_plan` 工具，类似 Anthropic 协议）/ `WaitForEnvironmentHandler`
- **插件（2）**：`ListAvailablePluginsToInstallHandler` / `RequestPluginInstallHandler`
- **MCP（4）**：`McpHandler` + `ListMcpResourcesHandler` + `ListMcpResourceTemplatesHandler` + `ReadMcpResourceHandler`（`mcp.rs` / `mcp_resource.rs` / `mcp_tool_call.rs:79KB`）
- **Multi-Agent（≥8）**：`multi_agents.rs` 的 SpawnAgent / WaitAgent / SendInput / ResumeAgent / CloseAgent（V1）+ `multi_agents_v2.rs` 的 V2 全套 + `agent_jobs.rs` 的 SpawnAgentsOnCsv / ReportAgentJobResult
- **Harness 仿真（≥15）**：`harness_aliases.rs` 的 `HarnessAliasHandler::{Agent, Bash, Read, Write, Edit, Glob, Grep, AskUserQuestion, TaskOutput/Stop/List, ReadMediaFile, DeepSeek*, ZCode*, OpenCode*, ClaudeCode*}` + `kimi_code_aliases.rs` 的 `CreateGoal/GetGoal/SetGoalBudget/TodoList/UpdateGoal` + `kimi_code_extra.rs` 的 `AgentSwarm/FetchUrl`
- **Hosted 工具**：`create_web_search_tool`（`hosted_spec.rs`，由 OpenAI provider 端执行）

#### 1.2 MCP 支持

**完整支持**。证据：
- 配置层 `config_toml.rs:267-271`：`mcp_servers: HashMap<String, McpServerConfig>`，支持 stdio（`command`+`args`+`env`）+ HTTP（`url`+`bearer_token_env_var`）两种 transport
- CLI：`interpreter mcp add/remove/list/get/login/logout`（`docs/mcp.md`）
- 运行时：通用 `McpHandler` 动态为每个 MCP tool 生成 `mcp__<server>__<tool>` spec
- OAuth：`cli_auth_credentials_store` + `mcp_oauth_credentials_store`（keyring / file backend）
- 自我暴露：`codex-rs/codex-mcp/` + `codex-rs/mcp-server/` 把 Codex 自身作为 MCP server 暴露

#### 1.3 Agent Skills 支持

**完整支持**（Anthropic Skills 协议风格）。证据：
- `core-skills/src/loader.rs:42KB` + `render.rs:64KB` 实现 `SkillMetadata { name, description, interface, dependencies, policy, path_to_skills_md, scope, plugin_id }`（`model.rs:14-29`）
- 3 scope：`bundled` / `~/.agents/skills/` / `.agents/skills/`，local 优先（`docs/skills.md`）
- SKILL.md frontmatter（`---\nname:\ndescription:\n---`），目录结构 `cut-release/{SKILL.md, scripts/, references/, assets/}`
- 渐进式披露：先 load metadata（name + description），匹配时再 load full skill
- 隐式调用检测：`detect_implicit_skill_invocation_for_command`（`invocation_utils.rs`）

#### 1.4 其他工具类型

- **Freeform tool**（`apply_patch`）：Lark grammar 描述，**不强制 JSON 包装**——LLM 输出 patch 字符串，`StreamingPatchParser` 增量解析
- **Hooks 系统**（`codex-rs/hooks/` + `hook_runtime.rs:33KB`）：PreToolUse / PostToolUse / PermissionRequest 事件钩子
- **Dynamic tools**（`tools/dynamic.rs` + `protocol/dynamic_tools.rs`）：运行时注册
- **Harness 别名系统**（`harness_aliases.rs:198KB`）：同一份逻辑在 10 harness 下不同 schema 暴露
- **MCP resources**（`mcp_resource.rs`）：MCP server 暴露的 resource（文件 / 数据）也可读
- **Extension tool executor**（`extension-api` + `extension_tools.rs:20KB`）：第三方扩展

### Q2. 工具列表的生成、传递、格式

#### 2.1 生成

**运行时按 turn 动态装配**，非启动时一次性。`spec_plan.rs:142-145` 的 `build_tool_router()` → `add_tool_sources()`（600+ 行）按顺序添加：(1) harness aliases (2) multi-agent (3) agent jobs (4) 基础执行 (5) MCP resources + per-tool handlers (6) Plan/Wait/Permissions/Time (7) ApplyPatch/ViewImage/TestSync (8) dynamic + extension。每个 handler 实现 `CoreToolRuntime` trait（`registry.rs:54-176`），`spec()` 返回 `ToolSpec::Function(ResponsesApiTool{...})` / `ToolSpec::Freeform(...)` / `ToolSpec::Namespace(...)`。

#### 2.2 传递

**三协议并行**：
- **OpenAI Responses API**（原生）：`ResponseInputItem::FunctionCall { id, name, namespace, arguments, call_id }`（`models.rs:996-1012`）
- **OpenAI Chat Completions**（兼容）：`chat-wire-compat/src/request.rs:104-346` 的 `convert_request()` 把 Responses → Chat
- **Anthropic Messages**：通过 `claude-code` / `zcode` harness shaping

#### 2.3 格式

**JSON + JSON Schema**（OpenAI Responses 风格）。apply_patch 例（`apply_patch_spec.rs:9-29`）：
```rust
ToolSpec::Freeform(FreeformTool {
    name: "apply_patch".to_string(),
    description: "Use the `apply_patch` tool to edit files. This is a FREEFORM tool, so do not wrap the patch in JSON.",
    format: FreeformToolFormat { r#type: "grammar".to_string(), syntax: "lark".to_string(), definition: APPLY_PATCH_LARK_GRAMMAR },
})
```

#### 2.4 Prompt-as-Tool？

**部分**——只用于 harness 仿真：apply_patch 是 freeform（lark grammar）；10 个 harness 的 `kimi_code_system_prompt.md` / `qwen_code_prompt.md` 是 prompt-as-tool 风格（LLM 在文本里写"调用 Bash"标签，alias handler 解析回结构化 call）。**主流程走纯 function calling**。

#### 2.5 动态刷新

**是**。MCP server 运行时增删（`interpreter mcp add/remove`）；Dynamic tools 运行时注册；Harness 切换（`/harness` slash）触发整套工具列表重算。

### Q3. 工具调用指令的解析、错误修复、准确性保证

#### 3.1 解析方式

- **Rust 时代**（当前 main）：wire-level 增量解析，由 `client.rs:1567-1705` 的 `stream_chat_completions_compat()` / `stream_chat_harness_api()` 处理流式 `tool_calls` delta，聚合为 `ResponseItem::FunctionCall { id, name, arguments, call_id }`
- **Python 时代**（v0.4.2）：`run_tool_catching_llm.py` 用 `merge_deltas()` + `parse_partial_json()` 增量解析——靠括号栈 + 转义状态机把残缺 JSON 补到能解析的位置

#### 3.2 错误修复

**两层**：
1. **沙箱层 retry**（`orchestrator.rs:144-451` 的 `ToolOrchestrator::run()`）：第一次 `workspace-write` 沙箱跑 → 失败 escalate 到 `danger-full-access`（**不再次用户审批**，靠 `already_approved` 缓存）→ `Guardian` AI 复核 / `NetworkApprovalMode::Deferred`
2. **回灌给模型**（`tools/src/function_call_error.rs`）：
   ```rust
   pub enum FunctionCallError {
       RespondToModel(String),  // 错误回灌给 LLM 让它自己修
       Fatal(String),           // 真 fatal，停止
   }
   ```

#### 3.3 准确性保证

- `parse_arguments<T>(arguments: &str) -> Result<T, FunctionCallError>`（`handlers/mod.rs:104-112`）serde_json 类型校验
- apply_patch 用 Lark grammar `StreamingPatchParser` 强约束
- 每个 tool spec 显式 `strict: true/false`（`shell_spec.rs:215`）
- `RequestUserInputHandler` 让模型对模糊参数主动问用户
- `additional_permissions` 白名单 + feature flag 双重校验（`handlers/mod.rs:201-249`）

#### 3.4 重试上限

**没有硬性全局上限**。沙箱 escalate 有 3 档（read-only / workspace-write / danger-full-access）；LLM auto-retry 由模型看到 `RespondToModel` 错误若干次后自己决定是否放弃。`request_user_input` 是软上限。

### Q4. 工具执行结果回传

#### 4.1 回传方式

OpenAI Responses 协议（`models.rs:1033-1044`）：
```rust
FunctionCallOutput {
    call_id: String,
    output: FunctionCallOutputPayload,  // body: Text | ContentItems(Vec<InputText|InputImage|EncryptedContent>)
}
```
还有 `McpToolCallOutput` / `CustomToolCallOutput`（freeform）/ `ToolSearchOutput`。Anthropic Messages 走 `tool_use_id` + `tool_result` block（harness 仿真）。Chat Completions 走 `role:"tool"` + `tool_call_id`（`chat-wire-compat` 反向转换）。

#### 4.2 格式

**结构化**（`FunctionCallOutputPayload`，`models.rs:1883`）：
- `body: FunctionCallOutputBody::Text(String)` —— 纯文本
- `body: FunctionCallOutputBody::ContentItems(Vec<FunctionCallOutputContentItem>)` —— **多模态结构化**（`InputText` / `InputImage { image_url, detail }` / `EncryptedContent`）
- `success: Option<bool>` —— 内部元数据，不上 wire
- 自定义序列化（`models.rs:1963-1986`）把 body 序列化为**字符串**（文本）或**结构化数组**（多模态）—— wire 上是两种形态之一

#### 4.3 通信协议

**三协议 + 10 harness 仿真**（`harness/routing.rs` + `docs/harness.md`）：OpenAI Responses / Chat Completions / Anthropic Messages + 10 harness：native / claude-code / claude-code-bare / zcode / kimi-code / kimi-cli / qwen-code / deepseek-tui / swe-agent / minimal。`docs/harness.md` 明文："Harness mode is an Open Interpreter addition. It changes the model-facing prompt, tool schema, message conversion, and response handling while keeping the native Open Interpreter runtime."

#### 4.4 大结果处理

**多层**：
1. `TruncationPolicy::{Bytes(usize), Tokens(usize)}`（`protocol.rs:3278-3282`）
2. `format_exec_output_for_model()` 拼接 `Exit code: N\nWall time: Xs\nTotal output lines: N\nOutput:\n<截断内容>`（`tools/mod.rs:77-100`）
3. `formatted_truncate_text()` 超 budget 时插入告警 `Warning: truncated output (original token count: N)`
4. **`truncate_middle_chars` / `truncate_middle_with_token_budget` —— 从中间截断，保留头尾**（关键决策，比 Python 时代只截尾部更稳）
5. 图片走 `FunctionCallOutputContentItem::InputImage { image_url, detail }`（不塞进文本）
6. 加密内容走 `EncryptedContent`
7. `tool_output_token_limit` 配置项硬上限

Python 时代（v0.4.2）：无 `TruncationPolicy`，只有 `truncate_output` 把长 stdout 截到 `interpreter.max_output`（默认 2800 chars）。

### Q5. File Backend 是否为工具调用做了适配

#### 5.1 工具配置目录 / 文件清单

| 路径 | 作用 | 加载代码 |
|------|------|----------|
| `~/.openinterpreter/config.toml` | 全局 config（`[mcp_servers.xxx]` / `[profiles.xxx]` / `web_search`） | `config_toml.rs:267-271` 加载 `mcp_servers` |
| `.openinterpreter/config.toml` | 项目级 config 覆盖 | 同上（trusted project layer） |
| `~/.openinterpreter/AGENTS.md` | 全局 AGENTS.md 指令 | `core/src/agents_md.rs:16KB` + `agents_md_manager.rs` |
| `~/.openinterpreter/AGENTS.override.md` | 临时覆盖全局 AGENTS.md | `docs/agents_md.md` |
| `<repo>/AGENTS.md` (项目根到 cwd) | 项目级 AGENTS.md 沿路径拼接 | `core/src/agents_md.rs`（`docs/agents_md.md` "Scope and Precedence" 段） |
| `~/.agents/skills/` / `.agents/skills/` / `bundled` | Skills（3 scope，local 优先） | `core-skills/src/loader.rs:42KB` |
| `~/.openinterpreter/log/` (`log_dir` 默认) | 工具调用日志 | `config.md:57` |
| `~/.openinterpreter/state.db` + `sessions/<date>/<thread_id>.jsonl` | 状态 DB + JSONL rollout | `state_db_bridge.rs` + `rollout.rs` |
| `<repo>/.codex/` 内的 `config.toml` / `AGENTS.md` | 项目级 overrides | `config_toml.rs` |

#### 5.2 加载代码（关键引用）

- **MCP 配置加载**：`config/src/config_toml.rs:267-271` 声明 `mcp_servers`；`config_requirements.rs:159/224/871/953/...` 多层 merge（实测 30+ 处引用）
- **Skills 加载**：`codex-rs/core-skills/src/loader.rs:42KB` 完整 loader（`SkillMetadata` / `SkillScope::Bundled/User/Project` / `SkillLoadOutcome`）
- **AGENTS.md 加载**：`codex-rs/core/src/agents_md.rs:16KB` 路径扫描 + 字节上限（"combined project instructions are capped by `project_doc_max_bytes`"）
- **Hook 配置**：`codex-rs/config/src/hook_config.rs:6.3KB`

#### 5.3 全局 vs 项目级

**两者都有**。`docs/config.md:8-19` 显式：`~/.openinterpreter/config.toml`（layer 3 user）+ `.openinterpreter/config.toml`（layer 4 trusted project）。配合 **6 级 precedence**（`config.md:30-37`）：(1) built-in defaults < (2) system/managed < (3) user < (4) trusted project < (5) selected profile < (6) CLI overrides (`-c key=value`)。`docs/skills.md` 也说："Local skills take priority over personal and bundled skills when names collide"。

#### 5.4 与 `standard/file_backend.md` 对照

| 标准条款 | Open Interpreter 表现 | 一致性 |
|----------|----------------------|--------|
| §1.1 固定用户属主目录 + env override | `~/.openinterpreter/` + `CODEX_HOME` env | ✅ |
| §1.3 AGENTS.md 向上扫描到 .git 边界 | "AGENTS.md files from the repository root down to the current working directory" | ✅ |
| §1.3 AGENTS.md 字节上限 | `project_doc_max_bytes`（`config_toml.rs:285-289`） | ✅ |
| §3.1 严格三层分离 | `~/.openinterpreter/` + `.openinterpreter/` + 运行时 tmp | ✅ |
| §3.8 Bootstrap 种子文件 | `/init` slash 自动生成 `AGENTS.md` | ✅ |
| §5.3 secrets 独立 + 0o600 | `cli_auth_credentials_store` (keyring/file) + `mcp_oauth_credentials_store` | ✅（强于 0o600） |
| §6.5 atomic write / checkpoints | `state.db` SQLite + `rollout` JSONL | ✅ |
| §9.5 `/doctor` 自检命令 | `interpreter doctor` | ✅ |
| §10.8 MCP 协议支持 | `[mcp_servers.xxx]` 双层 | ✅ |

**结论**：Open Interpreter（Rust 时代）是 `file_backend.md` 标准的**顶级参考实现**，几乎全部维度命中，是 Onion Agent 工作区设计的最强参照。

---

## 3. 关键代码片段

### 3.1 apply_patch freeform tool spec（`handlers/apply_patch_spec.rs:9-29`）

```rust
pub fn create_apply_patch_freeform_tool(include_environment_id: bool) -> ToolSpec {
    let definition = if include_environment_id {
        APPLY_PATCH_LARK_GRAMMAR.replace(/* multi-env variant */)
    } else { APPLY_PATCH_LARK_GRAMMAR.to_string() };
    ToolSpec::Freeform(FreeformTool {
        name: "apply_patch".to_string(),
        description: "Use the `apply_patch` tool to edit files. This is a FREEFORM tool, so do not wrap the patch in JSON.",
        format: FreeformToolFormat { r#type: "grammar".to_string(), syntax: "lark".to_string(), definition },
    })
}
```

### 3.2 FunctionCallOutputPayload 多模态（`protocol/src/models.rs:1882-1886`）

```rust
/// The payload we send back to OpenAI when reporting a tool call result.
#[derive(Debug, Default, Clone, PartialEq, JsonSchema, TS)]
pub struct FunctionCallOutputPayload {
    pub body: FunctionCallOutputBody,  // Text | ContentItems(Vec<InputText|InputImage|EncryptedContent>)
    pub success: Option<bool>,         // 内部元数据，不上 wire
}
```

### 3.3 FunctionCallError 二元错误（`tools/src/function_call_error.rs`）

```rust
pub enum FunctionCallError {
    #[error("{0}")] RespondToModel(String),  // 回灌给 LLM 让它自己修
    #[error("Fatal error: {0}")] Fatal(String),  // 真 fatal，停止
}
```

### 3.4 Python 时代 partial JSON 容错（v0.4.2 `interpreter/core/llm/utils/parse_partial_json.py`）

```python
def parse_partial_json(s):
    new_s, stack, is_inside_string, escaped = "", [], False, False
    for char in s:  # 逐字符扫描
        if is_inside_string:
            if char == '"' and not escaped: is_inside_string = False
            elif char == "\n" and not escaped: char = "\\n"  # 容错未转义换行
            ...
        else:
            if char == '{': stack.append('}')
            if char == '[': stack.append(']')
        new_s += char
    if is_inside_string: new_s += '"'  # 关闭未完成字符串
    # ... 补全 + 解析
```

---

## 4. 与 Onion Agent 设计的关联

1. **Onion 可以学：沙箱 × approval 二维矩阵**——`sandbox_mode`（3 档）× `approval_policy`（3 档）× `approvals_reviewer`（人 / Guardian AI / auto）三轴正交，是信创内网场景的**最强参考**，Onion 应直接抄。
2. **Onion 可以学：`TruncationPolicy::{Bytes, Tokens}` + `truncate_middle_chars` 中间截断**——保留头尾对模型"看错误"和"看结论"同样重要，Onion 的 `exec` 工具应在 tool channel 层内置。
3. **Onion 可以学：`FunctionCallOutputPayload { body: Text | ContentItems }` 结构化结果**——不要把图片 / HTML / 长日志全塞字符串里，`session.json` 应有原生多模态支持。
4. **Onion 应当避免：30+ 内置工具 + 10 harness 别名表**——`harness_aliases.rs:198KB` 是过度工程。Onion MVP 只保留 5-8 个核心 tool（read / write / edit / shell / plan / finish_loop / record_memory / web_search），harness 仿真留 P2。
5. **Onion 应当避免：Python 时代的"LMC 协议" partial JSON 解析**——为旧模型设计的复杂度，2026 年的 GPT-5 / Claude 4 / Gemini 3 走**原生 tool call** 即可，不做 partial JSON。
6. **Onion 应当抄：6 级 config precedence + `[mcp_servers.xxx]` TOML + `project_doc_max_bytes` + `AGENTS.override.md`**——三机制都该直接移植。

---

## 5. 不确定 / 未找到

1. Python 时代 `convert_to_openai_messages.py` 没深读（只确认存在），不影响 Rust 时代结论。
2. `FunctionCallOutputPayload` 在 Chat Completions wire 上的精确 JSON 字节细节没追（`models.rs:1963-1986`），但"结构化多模态"结论明确。
3. 10 个 harness shaping 内部差异（如 `kimi_code_system_prompt.md` 具体内容）只看了目录，Onion 是否复刻 10 harness 仿真留 P2 评估。
4. Rust 时代"工具 retry 上限"无全局硬性数字，LLM 看到 `RespondToModel` 错误后由模型自己决定是否重试。Onion 是否加硬性 retry 上限留评估。
5. `Memories` 模块（`codex-rs/memories/` Phase 1/2 pipeline）属持久化层，与工具调用关联不大，未深入。

---

**报告完。** 基于 `5ce1320` HEAD 与 `v0.4.2` tag 双时代对照。
