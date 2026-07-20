# Open Interpreter — 后端工作区（file_backend）调研报告

> 调研对象：`github.com/openinterpreter/open-interpreter`（本地 clone：`C:\workspace\github\onionagent\harness\01_market_research\clone\open-interpreter`）
> 调研时间：2026-07-17
> 调研方式：本地 git tag 检视（`v0.4.2` = Python 时代最后一个 release tag；`rust-v0.0.12` = Rust 重写后第一个 release tag；`main` = 当前 HEAD = `5ce1320`）+ 文件树静态分析
> 输出人：general worker（按洋葱头项目 `harness/01_market_research/` 模板输出）

---

## 0. 智能体一句话定位

Open Interpreter 是一款**让 LLM 在本机"自然语言驱动"执行任意代码的本地 code interpreter** —— 用户用自然语言下指令，LLM 生成 Python / Shell / JavaScript 等多语言代码块，本地执行并把输出回灌给 LLM，循环直到任务完成。

---

## 0.5 项目当前状态（重要：仓库已被重写）

**关键发现**：`openinterpreter/open-interpreter` 这个仓库的 `main` 分支已经**完全重写为 Rust 实现**，与原始的 Python 项目几乎是两个完全不同的产品；本调研的代码树对照必须分两段看。

### 时间线证据（基于 `git ls-remote --tags origin` 实证）

| Tag 范围 | 含义 | 状态 |
|----------|------|------|
| `v0.1.0` – `v0.1.18` | Python 早期迭代 | 史 |
| `v0.2.0` – `v0.2.6` | Python 中期 | 史 |
| `v0.3.0` – `v0.3.14` | Python 成熟期 | 史 |
| **`v0.4.0` / `v0.4.1` / `v0.4.2`** | **最后一个 Python tag** | **Python 时代终点** |
| （空档） | 仓库历史被 force-push 清洗 | — |
| **`rust-v0.0.12`** | **第一个 Rust tag** | **Rust 时代起点** |
| `rust-v0.0.12` – `rust-v0.0.29` | Rust 持续迭代到当前 `main` (`5ce1320`) | 现行 |

- 仓库根目录当前存在 `AGENTS.md`（**22.8 KB**，项目级 AGENTS 规范，说明这是一个为 agent-first 设计的工程）、`codex-rs/`、`codex-cli/`、`sdk/`、`docs/`、`bazel/`、`MODULE.bazel` 等纯 Rust / Bazel 化资产，**没有任何 `interpreter/`、`pyproject.toml`、`poetry.lock` 等 Python 资产**。
- 根 `README.md` 明文写道：

  > **This is the new Rust version of Open Interpreter, based on Codex.** Looking for the original Python project? It lives on as a community-maintained fork at `endolith/open-interpreter`.

  并以 `[!NOTE]` 块标注当前焦点是 "Kimi K3 is here"，即把 OpenAI Codex 的 harness 移植为针对低成本模型优化的 Kimi Code harness。
- `README.md` 中 "Harness Emulation" 章节明确 `Use /harness to switch the active harness` 列出：`native / claude-code / claude-code-bare / zcode / kimi-code / kimi-cli / qwen-code / deepseek-tui / swe-agent / minimal`，共 10 个 harness。
- 根 `CHANGELOG.md`（rust-v0.0.12 起）只有一行：*The changelog can be found on the [releases page](https://github.com/openai/codex/releases).* —— **直接指向 OpenAI Codex 的 releases**，印证 "Open Interpreter 是 OpenAI Codex 的 fork"。
- 当前 `main` HEAD 提交说明："Fix provider model catalog caching and prepare 0.0.29"，确认仍在 rust-v 序列。

### 重写对本次调研的影响

| 维度 | 处理方式 |
|------|----------|
| Python 时代设计 | **必须通过历史 tag 还原**：本报告 §1 / §2 / §3 主要基于 `v0.4.2` 标签的代码树（最后且最完整的 Python release）。 |
| Rust 时代设计 | **直接读 `main` 分支**（与 `rust-v0.0.29` 几乎一致）。 |
| 两者关系 | 不是"升级"，是"换核 + 改产品定位"。详见 §3 末尾"设计差异"对比表。 |
| 对 onionagent 的启示 | Python 时代那份"自然语言 → 本地多语言代码执行"的极简心智模型仍然有借鉴价值（见 §4），但要做产品级 codegen agent，Rust 时代（即 OpenAI Codex）的设计是当前工程标准答案。 |

---

## 1. 整体目录结构

### 1.1 Python 时代（`git show v0.4.2:...` 还原）

```
open-interpreter/                       (v0.4.2, 2024 中期)
├── interpreter/                       # 主包（"interpreter" 既是目录名也是 PyPI 包名）
│   ├── __init__.py                    # 导出 OpenInterpreter 单例
│   ├── core/                          # 核心 Agent 引擎
│   │   ├── core.py                    # OpenInterpreter 类（grand central station）
│   │   ├── async_core.py              # AsyncInterpreter（继承 OpenInterpreter，加 FastAPI/WS）
│   │   ├── respond.py                 # 核心循环 respond() 迭代器
│   │   ├── render_message.py          # 消息渲染（system / user / code / output）
│   │   ├── default_system_message.py  # 默认 system prompt
│   │   ├── llm/                       # LLM 调用层
│   │   │   ├── llm.py                 # Llm 类（包装 LiteLLM）
│   │   │   ├── run_text_llm.py        # 纯文本 LLM（无 function call）
│   │   │   ├── run_tool_calling_llm.py# tool-calling LLM
│   │   │   ├── run_function_calling_llm.py
│   │   │   └── utils/                 # convert_to_openai_messages / merge_deltas / parse_partial_json
│   │   ├── computer/                  # "Computer" = 用户机器的语义抽象
│   │   │   ├── computer.py            # Computer 类（聚合所有子系统）
│   │   │   ├── terminal/              # 多语言 REPL 容器
│   │   │   │   ├── terminal.py        # Terminal 类
│   │   │   │   ├── base_language.py
│   │   │   │   ├── languages/         # 9 种语言实现
│   │   │   │   │   ├── python.py      # 基于 Jupyter 内核
│   │   │   │   │   ├── shell.py       # 基于 subprocess
│   │   │   │   │   ├── javascript.py
│   │   │   │   │   ├── html.py
│   │   │   │   │   ├── powershell.py
│   │   │   │   │   ├── ruby.py / r.py / react.py / java.py / applescript.py
│   │   │   │   │   ├── subprocess_language.py  # 共享基类
│   │   │   │   │   └── jupyter_language.py    # Jupyter 共享基类
│   │   │   ├── mouse.py / keyboard.py / display.py / clipboard.py
│   │   │   ├── browser.py / browser_next.py
│   │   │   ├── mail.py / sms.py / calendar.py / contacts.py
│   │   │   ├── os.py / vision.py / skills.py / docs.py / ai.py / files.py
│   │   │   └── utils/
│   │   └── utils/                     # telemetry / truncate_output / 等
│   └── terminal_interface/            # CLI / TUI 层
│       ├── start_terminal_interface.py  # argparse + 启动入口
│       ├── terminal_interface.py     # 主循环
│       ├── conversation_navigator.py
│       ├── contributing_conversations.py  # 上传对话训练数据
│       ├── magic_commands.py          # 内置 magic
│       ├── render_past_conversation.py
│       ├── validate_llm_settings.py
│       ├── local_setup.py             # 向导式配置
│       ├── profiles/                  # profile = 可分享的 preset
│       ├── components/                # TUI 组件
│       └── utils/                     # display_markdown_message / oi_dir / local_storage_path
├── docs/                              # 面向用户的文档
├── examples/
├── installers/                        # 各平台安装脚本
├── scripts/
├── tests/
├── Dockerfile                         # 单镜像容器
├── pyproject.toml                     # Poetry 包（name = "open-interpreter"）
└── poetry.lock
```

**总结**：Python 时代的 Open Interpreter = **单进程单体架构**，核心抽象是"一个 `OpenInterpreter` 单例 + 一个 `Computer` 聚合根 + 一个 LiteLLM 包装的 `Llm`"。

### 1.2 Rust 时代（当前 `main` 分支）

```
open-interpreter/                       (main, 5ce1320 / rust-v0.0.29)
├── codex-rs/                          # Rust workspace，主体实现
│   ├── Cargo.toml                     # 28K+ bytes，多 crate workspace
│   ├── Cargo.lock
│   ├── core/                          # 主 crate：codex-core
│   │   └── src/                       # 100+ .rs 文件，分层明显
│   │       ├── lib.rs                 # 模块导出表
│   │       ├── codex_thread.rs        # CodexThread：会话线程抽象（旧 ConversationManager）
│   │       ├── thread_manager.rs      # ThreadManager：会话管理（旧 ConversationManager）
│   │       ├── client.rs              # ModelClient：模型 HTTP/SSE 客户端
│   │       ├── client_common.rs
│   │       ├── session/               # 单会话内部
│   │       │   ├── mod.rs             # Session（最大单文件 164KB）
│   │       │   ├── session.rs         # Session struct + SessionConfiguration
│   │       │   ├── turn.rs            # 单轮逻辑
│   │       │   ├── turn_context.rs    # TurnContext（每轮上下文）
│   │       │   ├── input_queue.rs     # 用户输入队列
│   │       │   ├── handlers.rs
│   │       │   ├── mcp.rs / mcp_runtime.rs
│   │       │   └── ...
│   │       ├── tools/                 # 工具调度系统
│   │       │   ├── mod.rs / context.rs / events.rs / registry.rs
│   │       │   ├── orchestrator.rs / parallel.rs / router.rs
│   │       │   ├── spec_plan.rs       # 工具规约
│   │       │   └── handlers/          # 每个工具一个文件
│   │       │       ├── shell.rs / apply_patch.rs / plan.rs
│   │       │       ├── mcp.rs / mcp_resource.rs
│   │       │       ├── agent_jobs.rs  # 子 agent 任务
│   │       │       ├── request_user_input.rs
│   │       │       ├── request_permissions.rs
│   │       │       ├── multi_agents.rs / multi_agents_v2.rs
│   │       │       ├── view_image.rs / sleep.rs / current_time.rs
│   │       │       ├── harness_aliases.rs (198KB!)  # 10 个 harness 的工具别名表
│   │       │       ├── kimi_code_aliases.rs / kimi_code_skill.rs
│   │       │       └── ...
│   │       ├── harness/               # 10 个 harness 的实现
│   │       │   ├── mod.rs             # 只是 export 列表
│   │       │   ├── routing.rs         # 路由表（WireApi × Harness → 行为）
│   │       │   ├── request.rs / guidance.rs
│   │       │   ├── native/ minimal/ little_coder/ claude_code/ claude_code_prompt
│   │       │   ├── deepseek_tui (+ prompts/)
│   │       │   ├── kimi_cli (+ kimi_cli_prompt.md / kimi_cli_compaction_prompt.md)
│   │       │   ├── kimi_code (+ kimi_code_system_prompt.md / kimi_code_tools.json)
│   │       │   ├── qwen_code (+ qwen_code_prompt.md)
│   │       │   ├── opencode (+ opencode_system_prompt.md)
│   │       │   ├── swe_agent / mini_swe_agent / terminus_2 / zcode / pi
│   │       │   └── session_skills.rs
│   │       ├── context/ context_manager/  # 上下文管理
│   │       ├── agent/                  # Agent 运行时（plan/exec/review/...）
│   │       ├── guardian/               # 守护（人审 / 守门）
│   │       ├── harness/
│   │       ├── hooks/ hook_runtime.rs  # 事件钩子
│   │       ├── sandboxing/             # 沙箱策略
│   │       ├── config/                 # 配置 schema / 加载 / profile
│   │       ├── exec/                   # 进程执行原语
│   │       ├── exec_policy/            # exec policy 引擎
│   │       ├── shell.rs / shell_snapshot.rs
│   │       ├── file_system/ file_search/ file-watcher/ git-utils/
│   │       ├── mcp.rs / mcp_tool_call.rs / mcp_openai_file.rs (79KB)
│   │       ├── skills.rs / core-skills/    # skills 引擎
│   │       ├── agents_md.rs (16KB) / agents_md_manager.rs
│   │       ├── memories/               # 跨会话记忆（Phase 1/2 流水线）
│   │       ├── message-history/
│   │       ├── rollout.rs / rollout-trace/   # 会话持久化
│   │       ├── thread-store/           # 会话元数据
│   │       ├── state_db_bridge.rs      # 嵌入式 state DB 桥
│   │       ├── model-provider/ models-manager/ ollama/ lmstudio/
│   │       ├── prompt-debug/ build_prompt_input.rs
│   │       ├── realtime_context.rs / realtime_conversation.rs / realtime_prompt.rs
│   │       ├── compact.rs / compact_remote.rs / compact_v2.rs   # 上下文压缩
│   │       ├── connectors.rs / plugins/ ext/
│   │       ├── analytics/ otel/        # 可观测
│   │       ├── keyring-store/ secrets/ login/ chatgpt/
│   │       └── ...
│   ├── exec/ exec-server/ exec-server-protocol/   # 独立 exec 服务
│   ├── tui/                            # Ratatui 终端 UI
│   ├── cli/                            # CLI 解析
│   ├── app-server/ app-server-client/ app-server-protocol/
│   │   app-server-transport/ app-server-daemon/ app-server-test-client/
│   ├── acp-server/                     # Agent Client Protocol 服务
│   ├── codex-api/ codex-mcp/ codex-home/
│   ├── chat-wire-compat/               # Chat ↔ Responses 兼容层
│   ├── responses-api-proxy/            # Responses API 反代
│   ├── cloud-tasks/ cloud-tasks-client/
│   ├── code-mode/ code-mode-host/ code-mode-protocol/   # code-mode 子 agent
│   ├── mcp-server/ rmcp-client/
│   ├── memories/                       # 跨会话记忆 crate
│   │   ├── README.md                   # 详细描述 Phase 1/2 流水线
│   │   ├── read/   (codex-memories-read)
│   │   └── write/  (codex-memories-write)
│   ├── skills/ core-skills/ ext/ plugins/
│   ├── linux-sandbox/                  # Linux 沙箱（landlock + bwrap）
│   ├── windows-sandbox-rs/             # Windows 沙箱
│   ├── apply-patch/                    # apply_patch 工具（Codex "V4A" patch 协议）
│   ├── process-hardening/              # 进程硬化
│   ├── bwrap/                          # bubblewrap 包装
│   ├── realtime-webrtc/                # 实时 WebRTC
│   ├── websocket-client/
│   ├── utils/ async-utils/ ansi-escape/ ...  # 通用工具 crate
│   ├── tools/ features/ models-manager/ ...
│   ├── .cargo/ .config/                # cargo / rustc 配置
│   ├── rust-toolchain.toml
│   ├── rustfmt.toml / clippy.toml
│   ├── deny.toml                       # 依赖审计
│   └── config.md                       # 嵌入式配置说明
│
├── codex-cli/                         # Node 启动器：下载正确平台的 Rust 二进制
│   ├── package.json                   # name = "@openai/codex"  ← 这就是 OpenAI Codex
│   └── bin/codex.js
│
├── sdk/                               # 多语言 SDK
│   ├── python/                        # openai-codex Python SDK
│   │   ├── pyproject.toml
│   │   ├── README.md                  # "OpenAI Codex Python SDK (Beta)"
│   │   ├── src/ tests/ docs/ examples/ notebooks/
│   │   └── uv.lock
│   ├── python-runtime/                # Python 嵌入运行时
│   └── typescript/                    # TS SDK（@openai/codex SDK）
│
├── docs/                              # 面向用户的中英文档
│   ├── config.md / config-reference.md / example-config.md
│   ├── agents_md.md                   # AGENTS.md 机制说明
│   ├── acp.md / app-server.md / daemon.md
│   ├── exec.md                        # interpreter exec 非交互模式
│   ├── cli-reference.md / authentication.md
│   ├── providers.md ... zh/           # 中文翻译
│   └── ...
│
├── docs-site/                         # Mintlify 站点源码
│   ├── terminal-index.mdx / LOCALIZATION.md
│   ├── assets/ / zh/
│
├── bazel/                             # Bazel 构建系统
├── tools/                             # 工具脚本
├── scripts/                           # 运维 / 目录生成
│   └── write_provider_catalog.py      # 自动化生成 provider 目录
├── patches/                           # 第三方 patch
├── third_party/                       # 第三方源码
├── vendor/                            # 供应商资产
├── AGENTS.md                          # 22.8 KB，codex-rs 工程规范
├── BUILD.bazel / MODULE.bazel / MODULE.bazel.lock / defs.bzl / rbe.bzl
├── flake.nix / flake.lock / default.nix
├── justfile / cliff.toml              # cliff = 自动生成 changelog
├── announcement_tip.toml
├── package.json / pnpm-lock.yaml / pnpm-workspace.yaml
├── docs.json / docs.zh.json
├── style.css / logo/
└── README.md / README_ES.md / README_ZH.md / SECURITY.md / NOTICE / LICENSE
```

**总结**：Rust 时代的 Open Interpreter = **OpenAI Codex 的 fork 仓库**，Cargo workspace（多 crate + Bazel 双构建），主体是 `codex-core`（核心 agent runtime）+ `codex-tui`（Ratatui TUI）+ `codex-cli`（Node 启动器）+ 多语言 `sdk/` + `app-server`（进程内 app-server 协议）+ `acp-server`（Agent Client Protocol）+ `linux-sandbox` / `windows-sandbox-rs`（平台沙箱）+ `memories/`（跨会话记忆 pipeline）。

---

## 2. 核心工作区（运行时架构）

> 描述对象分别是：Python 时代运行时 vs. Rust 时代运行时。

### 2.1 Python 时代：`OpenInterpreter` 单例 + 同步生成器循环

#### 2.1.1 入口与核心对象

| 文件 | 类 / 函数 | 职责 |
|------|----------|------|
| `interpreter/core/core.py` | `class OpenInterpreter` | **grand central station** —— 持有 `messages`、`llm`、`computer`、`system_message`、`loop_message` 等所有状态；提供 `.chat()` 公开 API。`from interpreter import interpreter` 导出**单例**。 |
| `interpreter/core/core.py` | `OpenInterpreter.chat()` | 主入口：根据 `display` / `stream` / `blocking` 派发到 `_streaming_chat()`。支持 threading 后台模式。 |
| `interpreter/core/core.py` | `OpenInterpreter._streaming_chat()` | 把用户消息 append 到 `self.messages` → 调 `self._respond_and_store()` → 可选落盘 JSON 对话历史。 |
| `interpreter/core/core.py` | `OpenInterpreter._respond_and_store()` | 包装 `respond()` 迭代器，按 `chunk['type']` 拆分为不同 `Message` 并塞回 `self.messages`。 |
| `interpreter/core/respond.py` | `respond(interpreter)` | **核心生成器循环**（v0.4.2 的关键代码）：`while True: → 渲染 system → llm.run() → 若输出 type=code 则 computer.run() → 检查 loop_breakers 决定是否继续`。 |

#### 2.1.2 三层职责划分

```
┌──────────────────────────────────────────────────────────────────┐
│            OpenInterpreter (core.py, 单例)                        │
│   状态: messages / system_message / loop / max_budget / ...      │
│                                                                  │
│   ┌──────────────────────┐        ┌────────────────────────┐    │
│   │  Llm                 │        │  Computer               │    │
│   │  (core/llm/llm.py)   │        │  (core/computer/        │    │
│   │  - LiteLLM 包装      │        │   computer.py)          │    │
│   │  - run_text_llm      │        │  - 聚合 14 个子系统     │    │
│   │  - run_tool_calling  │        │  - mouse/keyboard/      │    │
│   │  - convert_to_oa_msg │        │    display/browser/...  │    │
│   │  - merge_deltas      │        │  - terminal.languages[] │    │
│   └──────────────────────┘        │    [python, shell,      │    │
│                                   │     js, html, ruby,     │    │
│                                   │     java, r, react,     │    │
│                                   │     powershell,         │    │
│                                   │     applescript]        │    │
│                                   └────────────────────────┘    │
│                                                                  │
│   respond()  ←  Python generator，循环:                          │
│     1) 渲染 system_message (含 custom_instructions / language)  │
│     2) 调 llm.run(messages_for_llm) → 流式 yield chunks         │
│     3) 若最后一条 message.type == "code":                       │
│        computer.terminal.run(language, code) → yield chunks     │
│     4) 若 assistant 末条不含 loop_breakers → 注入 loop_message   │
│     5) else break                                               │
└──────────────────────────────────────────────────────────────────┘
```

#### 2.1.3 `respond()` 的核心循环（v0.4.2 实证代码）

```python
# interpreter/core/respond.py (节选)
def respond(interpreter):
    last_unsupported_code = ""
    insert_loop_message = False

    while True:
        # 1) 渲染 system message（叠加 language-specific + custom + computer API）
        system_message = interpreter.system_message
        for language in interpreter.computer.terminal.languages:
            if hasattr(language, "system_message"):
                system_message += "\n\n" + language.system_message
        if interpreter.custom_instructions:
            system_message += "\n\n" + interpreter.custom_instructions
        if interpreter.computer.import_computer_api and interpreter.computer.system_message not in system_message:
            system_message = system_message + "\n\n" + interpreter.computer.system_message

        # 2) messages_for_llm = [system] + interpreter.messages
        messages_for_llm = [rendered_system_message] + interpreter.messages.copy()

        # 3) 调 LLM
        if interpreter.messages[-1]["type"] != "code":
            for chunk in interpreter.llm.run(messages_for_llm):
                yield {"role": "assistant", **chunk}
            # 各种异常处理：BudgetExceeded / Auth / RateLimit / Not Have Access

        # 4) 若 type == code：执行代码
        if interpreter.messages[-1]["type"] == "code":
            language = interpreter.messages[-1]["format"].lower().strip()
            code = interpreter.messages[-1]["content"]
            # ... 各种 hallucination 矫正（"functions.execute(" / "{language:..." ...）
            # 校验 language 支持 / 非空 / yield confirmation
            for line in interpreter.computer.run(language, code, stream=True):
                yield {"role": "computer", **line}

        # 5) loop 终止判断
        loop_breakers = interpreter.loop_breakers
        if interpreter.loop and interpreter.messages[-1].get("role") == "assistant" and \
           not any(s in interpreter.messages[-1].get("content", "") for s in loop_breakers):
            # 合并相邻 assistant message，注入 loop_message，继续
            insert_loop_message = True
            continue
        break
```

**关键设计特征**：
1. **纯生成器循环** —— `respond()` 是一个 Python `Generator`，每次 `yield` 推进状态。TUI 通过 `for chunk in interpreter.chat(stream=True): ...` 拉取增量。
2. **"code as a message"** —— LLM 不走 function call 协议，而是输出 ```python ... ``` markdown 块，解析后把 `type=code` 消息写回 `interpreter.messages`，下一轮再交给 `computer.run()` 执行。响应也是 `type=console / format=output` 的消息写回。这就是所谓的 **LMC（Language Model Computer）Messages** 协议。
3. **`computer` API 内嵌** —— 通过 `import computer` 暴露鼠标 / 键盘 / 截图 / 浏览器等 14 个子系统（`Computer.to_dict()` 序列化后注入用户 Python 命名空间）。
4. **多语言并行 REPL** —— `Terminal.languages` 是 `[Python, Shell, JavaScript, HTML, AppleScript, R, PowerShell, React, Java, Ruby]`，每种 `BaseLanguage` 子类自己实现 `start_process()` / `run()`。
5. **safe_mode = "off" | "ask" | "auto-run"** —— `auto_run=False` 时 yield `type=confirmation` 给上层 TUI 弹"运行/拒绝"。
6. **loop 自续** —— 若 LLM 没产出 `loop_breakers` 之一的终止短语，就注入固定 `loop_message = "Proceed. You CAN run code on my machine..."` 让它继续。

#### 2.1.4 `AsyncInterpreter` 扩展（`core/async_core.py`）

继承 `OpenInterpreter`，叠加：
- FastAPI + WebSocket + Uvicorn HTTP 服务（`/openai/...` 兼容端点）
- `input(chunk)` 异步流式接收器（按 `start / content / end` 三个 flag 累积 chunk）
- 后台 `respond_thread`，`stop_event` 中断
- `require_acknowledge` 模式（类似 Anthropic prompt caching 的"确认收到"）

#### 2.1.5 持久化与配置

- **会话**：`conversation_history=True` 时写到 `~/.openinterpreter/conversations/{first_words}__{date}.json`。
- **profile**：YAML，存于 `~/.openinterpreter/profiles/`，通过 `--profile <name>` 加载。
- **配置目录**：`get_storage_path()` → `~/.openinterpreter/`（Linux/macOS）/ `%APPDATA%/Open Interpreter/`（Windows）。

### 2.2 Rust 时代：Codex 多 crate 工作区 + ThreadManager + 沙箱 + Harness 路由

> 跟 Python 时代相比，是"工业级操作系统"级别的工程：单 `codex-core/src/session/mod.rs` 一个文件就有 164KB（≈ 4000 行）。

#### 2.2.1 进程拓扑

```
用户终端
  └─ $ interpreter
       │
       ├─ codex-cli (Node, codex-cli/bin/codex.js)        ← 平台分流器
       │   └─ spawn @openai/codex-{linux,darwin,win32}-{x64,arm64}
       │       │
       │       └─ interpreter (Rust 二进制)
       │           ├─ codex-tui  (Ratatui 终端 UI)
       │           └─ codex-app-server (stdio:// / ws:// 协议)   ← 也可独立 daemon
       │               │
       │               └─ codex-core (核心)
       │                   ├─ ThreadManager  (多 thread / 多 turn)
       │                   ├─ CodexThread × N (单 thread)
       │                   ├─ ModelClient    (HTTP/SSE 调上游 OpenAI / Anthropic / Ollama / ...)
       │                   ├─ Tools orchestrator (registry / parallel / router)
       │                   ├─ MCP manager    (stdio 子进程 + tools 接入)
       │                   ├─ Sandbox        (linux-sandbox / windows-sandbox-rs / landlock / bwrap)
       │                   ├─ Memories       (memories/read + memories/write, Phase 1/2)
       │                   ├─ Hooks          (hook_runtime.rs)
       │                   ├─ Skills / AGENTS.md / Rollout / ThreadStore
       │                   └─ Harness router (10 个 harness: native / claude-code / ...)
       │
       ├─ sdk/python (openai-codex)         ← Python 客户端 SDK（pip install openai-codex）
       ├─ sdk/typescript (@openai/codex)    ← TS 客户端 SDK
       └─ acp-server (Agent Client Protocol)  ← 给 Zed / JetBrains / VS Code 之类的编辑器用
```

#### 2.2.2 `codex-core` 内部模块地图（lib.rs 实证）

按 `lib.rs` 的 `mod xxx;` 声明顺序：

| 模块 | 关键文件 | 职责 |
|------|---------|------|
| `codex_thread` | `codex_thread.rs` (25KB) | `CodexThread`：单会话线程（旧的 `CodexConversation` 别名已 `#[deprecated]`）。 |
| `thread_manager` | `thread_manager.rs` (76KB) | `ThreadManager`：所有 thread 的管理者；负责 start / fork / shutdown。 |
| `session` | `session/mod.rs` (164KB) / `session.rs` (63KB) / `turn.rs` (104KB) / `turn_context.rs` (36KB) | 内部 `Session` struct + `SessionConfiguration`：单会话状态、provider 配置、approval、permissions、workspace roots、environments。 |
| `client` | `client.rs` (149KB) | `ModelClient`：调 OpenAI Responses / Chat / Anthropic Messages API；SSE 流；429/5xx 重试。 |
| `tools` | `tools/mod.rs` / `registry.rs` / `orchestrator.rs` / `parallel.rs` / `router.rs` / `spec_plan.rs` | 工具系统：注册表、并发执行、工具 router、spec plan。 |
| `tools/handlers/` | `shell.rs` / `apply_patch.rs` / `plan.rs` / `mcp.rs` / `view_image.rs` / `request_user_input.rs` / `request_permissions.rs` / `agent_jobs.rs` / `multi_agents*.rs` / `harness_aliases.rs` (198KB) / `kimi_code_*.rs` | 每个工具一个文件。`harness_aliases.rs` 是把 10 个 harness 的工具定义集中重定向。 |
| `harness` | `harness/mod.rs` / `routing.rs` | 10 个 harness 的实现 + 路由表（`(wire_api, harness) → 行为`）。 |
| `context` / `context_manager` | | 上下文管理与 token 预算。 |
| `compact` | `compact.rs` (36KB) / `compact_remote.rs` / `compact_remote_v2.rs` (31KB) | 上下文压缩（远程 LLM 辅助压缩 + 失败回退到 v2）。 |
| `memories` | `codex-rs/memories/{read,write}/` + `core/src/memories/` | 跨会话记忆：Phase 1（rollout → raw_memory）+ Phase 2（global consolidation → workspace diff + MEMORY.md）。 |
| `agents_md` | `agents_md.rs` (16KB) / `agents_md_manager.rs` | `AGENTS.md` 发现与加载：项目根 → cwd 路径上每个 `AGENTS.md` 拼接。`AGENTS.override.md` 临时覆盖。 |
| `skills` | `skills.rs` / `core-skills/` | skills 引擎：filesystem-backed skills（与 Anthropic Skills 协议风格一致）。 |
| `hooks` | `hooks/` / `hook_runtime.rs` (33KB) | 事件钩子：on_turn_start / on_tool_call / on_error / ... |
| `sandboxing` | `sandboxing/mod.rs` (8KB) | 沙箱策略（`read-only` / `workspace-write` / `danger-full-access`）。 |
| `exec` / `exec_policy` | `exec.rs` (43KB) / `exec_policy.rs` (41KB) | 进程执行 + 策略（policy.toml 规则 + 启发式检查）。 |
| `rollout` | `rollout.rs` / `rollout_reconstruction.rs` (22KB) | 会话持久化（写到 `~/.codex/.../sessions/<date>/<thread_id>.jsonl`）。 |
| `thread-store` | `thread-store/` | thread 元数据（轻量 KV）。 |
| `state_db_bridge` | `state_db_bridge.rs` | 嵌入式 state DB（SQLite？）的 bridge，用于记忆 pipeline 协调。 |
| `mcp` | `mcp.rs` (8KB) / `session/mcp.rs` (33KB) / `mcp_tool_call.rs` (79KB) / `mcp_openai_file.rs` (21KB) | MCP 客户端 + 工具暴露策略。 |
| `model-provider` | | Provider 配置（openai / openrouter / anthropic / ollama / lmstudio / ...）。 |
| `models-manager` | `models_manager.rs` (49KB) | 模型目录与降级。 |
| `chat-wire-compat` | | Chat ↔ Responses wire 转换。 |
| `realtime_*` | `realtime_context.rs` (20KB) / `realtime_conversation.rs` (67KB) / `realtime_prompt.rs` (3KB) | 实时语音/多模态会话。 |
| `connectors` / `plugins` / `ext` | | 第三方 connector 协议。 |
| `app-server` / `app-server-protocol` | codex-rs/app-server/ | 进程内 app-server 协议（SDK 调用 Codex 的标准方式）。 |
| `acp-server` | codex-rs/acp-server/ | Agent Client Protocol 端点（给编辑器用）。 |
| `tui` | codex-rs/tui/ | Ratatui 终端 UI。 |
| `cli` | codex-rs/cli/ | CLI 解析。 |
| `codex-mcp` | codex-rs/codex-mcp/ | 把 Codex 自身暴露为 MCP server。 |
| `linux-sandbox` / `windows-sandbox-rs` | | 平台原生沙箱。 |
| `apply-patch` | apply-patch/ | Codex V4A patch 协议（结构化 diff）。 |
| `process-hardening` | | 进程硬化（no-new-privileges 等）。 |
| `keyring-store` / `secrets` / `login` | | 凭证管理 + OAuth + ChatGPT 登录。 |
| `analytics` / `otel_init` | | 可观测。 |
| `mcp-server` / `rmcp-client` | | MCP 服务端 + 客户端。 |

#### 2.2.3 关键运行时对象

- **`ThreadManager`** (`thread_manager.rs`)：管理所有 `CodexThread`，对外接口是 `NewThread`、`StartThreadOptions`、`ForkSnapshot`、`ThreadShutdownReport`。
- **`CodexThread`** (`codex_thread.rs`)：单 thread 的句柄，配置通过 `ThreadConfigSnapshot` 捕获（model / provider / approval / permissions / workspace_roots / environments / personality / collaboration_mode ...）。
- **`Session`** (`session/session.rs`, 63KB)：进程内"会话"——但**和 `CodexThread` 1:1 对应**；`SessionConfiguration` 持有 provider / 协作模式 / 工作区根 / 持久化目录。
- **`TurnContext`** (`session/turn_context.rs`, 36KB)：**单轮**的上下文快照，每 turn 重新生成。包含 model、tools、prompt、shell_snapshot、environment、approvals reviewer、permission profile。
- **`InputQueue`** (`session/input_queue.rs`, 14KB)：用户输入队列，turn 与 turn 之间的 steering。
- **`ActiveTurn`** (`state.rs`)：当前正在跑的 turn 句柄（可取消）。
- **`ModelClient`** (`client.rs`, 149KB)：上游 HTTP 客户端，支持 OpenAI Responses / Chat / Anthropic Messages 多种 wire。
- **`Harness`**（枚举）：10 个 harness（`native` / `claude-code` / `claude-code-bare` / `zcode` / `kimi-code` / `kimi-cli` / `qwen-code` / `deepseek-tui` / `swe-agent` / `minimal` / `pi` / `opencode` / `little_coder` / `mini-swe-agent` / `terminus-2`）。
- **`StreamTransportRoute`** (`harness/routing.rs`)：`(wire_api, harness) → 行为` 的二维路由表，决定走原生 Responses / Chat / Messages / Claude-Code shaping / Kimi shaping / ...
- **Tools registry + orchestrator** (`tools/`)：工具注册 + 并行调用 + router + spec plan；每个 tool 的"在某个 harness 下的别名"放在 `tools/handlers/harness_aliases.rs`（198KB）。
- **AGENTS.md Manager**：`AGENTS.md` 自动发现 + 加载（global + project tree）。
- **Memories Pipeline**（`codex-rs/memories/`）：Phase 1 把每个 thread rollout 抽成 `raw_memory` + `rollout_summary`，写到 state DB；Phase 2 锁定全局 phase2 lock 后做 `~/.codex/memories/.git` 基线 + workspace diff，spawn 内部 consolidation sub-agent 生成 `MEMORY.md` / `memory_summary.md` / `skills/`。
- **Sandboxing**：按 `sandbox_mode = "read-only" | "workspace-write" | "danger-full-access"` 三档，Linux 用 `landlock` + `bwrap`（`linux-sandbox/src/bwrap.rs` 105KB），Windows 用 `windows-sandbox-rs`，进程级还有 `process-hardening`。
- **Approvals**：`approval_policy = "untrusted" | "on-request" | "never"` + `approvals_reviewer`（人类/AI Guardian/auto）；`request_permissions.rs` 是 tool-time 拦截器。
- **Rollout** (`rollout.rs` / `rollout_reconstruction.rs`)：每 turn 写一行 JSONL 到 `~/.codex/sessions/<date>/<thread_id>.jsonl`，可回放。
- **ThreadStore** (`thread-store/`)：thread 元数据（in-memory + 本地），支持 fork / resume。
- **State DB** (`state_db_bridge.rs`)：嵌入式 KV/SQL，给 memories pipeline 用，含 startup claim 锁、phase-2 全局锁、`selected_for_phase2` 字段。
- **Hook runtime** (`hook_runtime.rs`, 33KB)：事件订阅 + dispatch。
- **Skills** (`skills.rs` / `core-skills/`)：filesystem-based skills（与 Anthropic Skills 协议同款：`SKILL.md` frontmatter + 文件夹）。
- **MCP** (`mcp.rs` / `session/mcp.rs` / `mcp_tool_call.rs`)：stdio 子进程拉 MCP server，工具注册进 tools registry；并可以把 Codex 自身作为 MCP server 暴露（`codex-mcp` / `mcp-server`）。
- **App Server** (`app-server/`)：进程内服务，stdio:// 或 ws://，SDK 通过它和 Codex 交互。
- **ACP Server** (`acp-server/`)：让编辑器（Zed / JetBrains / VS Code / Claude Code / Cursor / ...）通过 Agent Client Protocol 调 Codex。
- **SDK**：Python (`openai-codex`, `sdk/python/`) + TypeScript (`@openai/codex`, `sdk/typescript/`)。
- **Providers**：`scripts/write_provider_catalog.py` 自动生成 provider 目录；支持 openai / anthropic / ollama / lmstudio / kimi / moonshot / zai / glm / deepseek / qwen / ...

#### 2.2.4 关键运行时数据流（与 Python 时代对应）

| 阶段 | Python 时代 | Rust 时代 |
|------|------------|----------|
| 用户输入 | `interpreter.chat("...")` → append to `self.messages` | TUI / app-server 收 `Op::UserTurn` → `ThreadManager.start_thread` → `CodexThread.submit(Op)` → `InputQueue` |
| 系统提示构造 | `system_message` + `language.system_message` + `custom_instructions` + `computer.system_message` 字符串拼接 | `TurnContext` 内构造：base instructions + developer instructions + `AGENTS.md` (project_doc) + skills 注入 + personality + collaboration_mode + harness-specific prompt (`kimi_code_system_prompt.md` / `qwen_code_prompt.md` / ...)。**`~/.openinterpreter/AGENTS.md` 优先级 + `<cwd>/AGENTS.md` 文件覆盖**。 |
| LLM 调用 | LiteLLM → 任意 OpenAI 兼容 endpoint | `ModelClient` → 4 种 wire（OpenAI Responses / Chat / Anthropic Messages）+ harness shaping（kimi/claude-code/zcode/... 各自的工具协议） |
| 工具调用协议 | 不用原生 tool call：LLM 输出 ```python``` markdown 块，解析成 `type=code` message | 原生 tool call：tools registry 通过 `apply_patch`（Codex V4A 协议）+ `shell` + `mcp` + 多种；输出是结构化 `ResponseItem::FunctionCall`。 |
| 执行 | `computer.terminal.run(language, code)` → Jupyter / subprocess REPL | `exec` crate + `unified_exec`（统一 exec 抽象）+ `shell_snapshot`（命令快照可回滚）+ sandbox |
| 上下文压缩 | 没有自动压缩，只 truncate_output 限制单次输出 | `compact.rs` / `compact_remote.rs` / `compact_remote_v2.rs`：本地启发式 + 远程 LLM 压缩 + v2 失败回退 |
| 持久化 | JSON 文件（`~/.openinterpreter/conversations/*.json`） | JSONL rollout（`~/.codex/sessions/<date>/<thread_id>.jsonl`）+ ThreadStore 元数据 + State DB |
| 记忆 | 没有跨会话记忆 | `codex-rs/memories/` 两阶段 pipeline，Phase 1 + Phase 2，最终生成 `MEMORY.md` / `memory_summary.md` / `skills/` |
| 配置 | profile YAML + 环境变量 + 命令行 | `~/.openinterpreter/config.toml` + `.openinterpreter/config.toml`（项目级）+ `profiles.<name>` + `-c key=value` |
| 安全 | safe_mode + auto_run 弹窗 | sandbox (3 档) + approval (3 档) + exec policy (rules) + hooks + Guardian 复核 + 网络策略 |
| 客户端集成 | `interpreter --server` 启 FastAPI | `interpreter acp` (Agent Client Protocol) + `interpreter app-server` (stdio/WS) + 多语言 SDK + `interpreter mcp-server`（把 Codex 本身当 MCP server） |

#### 2.2.5 配置 / 文档实证（`docs/`、`docs-site/`、`AGENTS.md`）

- **`AGENTS.md`（仓库根，22.8 KB）**：是 `codex-rs/` 工程的"agent-first"规范（rust-clippy 规则、bazel 锁更新、PR 约定、tracing 习惯 ...）。**这就是用户在自己项目根写 `AGENTS.md` 时的模板级范例**。
- **`docs/agents_md.md`**：明确 `AGENTS.md` 优先级
  - `~/.openinterpreter/AGENTS.md`（global）
  - `<repo_root>/AGENTS.md` → ... → `<cwd>/AGENTS.md`（project 沿路径拼接）
  - `AGENTS.override.md` 临时覆盖
  - 大小上限 `project_doc_max_bytes`（靠近 cwd 的优先）
- **`docs/config.md`**：配置 precedence = built-in defaults < system/managed < user < trusted project < profile < CLI；常见配置：`model` / `model_provider` / `model_reasoning_effort` / `model_reasoning_summary` / `sandbox_mode` / `approval_policy` / `personality` / `web_search` / `log_dir`。
- **`docs/cli-reference.md`**：`interpreter` 公开命令的 19 个 global flag + 9 个 subcommand（`interpreter` / `resume` / `fork` / `exec` / `acp` / `app-server` / `app-server daemon` / `mcp` / `mcp-server` / `update`）。
- **`docs/exec.md`**：`interpreter exec "..."` 非交互模式（CI / 脚本友好）。
- **`docs/acp.md`**：以 ACP 服务端形式嵌入 Zed / JetBrains / VS Code 之类的编辑器。
- **`docs-site/terminal-index.mdx`**：Mintlify 站点首页，定位："Open Interpreter is a coding agent that lives in your terminal. It is built on top of Codex and stays provider agnostic." —— **明文"on top of Codex"**。

---

## 3. 设计差异（Python 时代 vs. Rust 时代）

> Python 时代是 2023–2024 年的"自然语言驱动本地代码执行"极简原型；
> Rust 时代是 2025–2026 年的"工业级 coding agent"完整产品。
> 两者**不属于"前后版本"关系，而属于"换赛道"关系**。

| 维度 | Python 时代 (v0.4.2, 2024) | Rust 时代 (main / rust-v0.0.29, 2026) | 对 onionagent 的启示 |
|------|---------------------------|---------------------------------------|----------------------|
| **产品定位** | "本地 code interpreter"——LLM 写代码，本地执行，循环 | "Coding agent"——多 turn、多 agent、沙箱安全、生产级 harness 仿真 | onionagent（个人/小团队）选 Python 风格更轻；要做产品级 codegen 走 Rust 风格 |
| **目标场景** | 个人脚本、数据分析、自动化 | 开发者 IDE agent、CI/PR agent、editor agent、多 agent 协同 | 看目标用户 |
| **语言/部署** | Python + pip + Docker + Poetry | Rust + Cargo + Bazel + Node 启动器；产物是单二进制 | 单二进制更易分发；Python 更易改 |
| **架构** | 单进程单体：`OpenInterpreter` 单例 + `Computer` 聚合根 | Cargo workspace 80+ crate + app-server / acp-server / SDK | Rust 模式可水平扩展（独立 app-server、独立 sandbox），但复杂度高一个数量级 |
| **LLM 调用** | LiteLLM 单一抽象（统一 OpenAI 协议），无 wire 概念 | `ModelClient` 抽象 4 种 wire（OpenAI Responses / Chat / Anthropic Messages / 自定义）+ harness shaping | Rust 模式更适合多 provider；Python 模式假设大家都是 OpenAI 协议 |
| **工具协议** | **不用原生 tool call**——LLM 输出 ```python``` markdown 块，解析为 `type=code` message，下一轮送给 REPL 执行。**LMC 协议**。 | **原生 tool call**——`tools/registry.rs` 注册、`tools/orchestrator.rs` 调度、`apply_patch.rs` 走 Codex V4A patch 协议 | onionagent 当前 `standalone_scripts/agent_client.py` 走的是 Cline 风格 XML 协议 + 自定义 finish 标签，介于两者之间 |
| **执行抽象** | 9 种语言各自的 `BaseLanguage`（Python = Jupyter 内核，其他 = subprocess） | 单一 `exec` 抽象 + `unified_exec`（沙箱化、可快照、可回滚） + `shell_snapshot` | 单一 exec 更可控；多语言 REPL 体验更"开放" |
| **持久化** | JSON 文件（conversation history） | JSONL rollout + ThreadStore + State DB（嵌入式 SQLite） + Memories pipeline（Phase1/2） | Rust 模式的"可回放 / 可压缩 / 可记忆"远超 Python 模式 |
| **记忆** | 无跨会话记忆 | 跨会话 Memories（Phase1 rollout→raw_memory / Phase2 global consolidation→MEMORY.md）+ AGENTS.md + skills | onionagent 的"三层记忆 namespace"灵感完全可对齐 |
| **沙箱 / 安全** | safe_mode (off/ask/auto-run)，基本无沙箱 | 三档 sandbox（read-only / workspace-write / danger-full-access）+ 三档 approval（untrusted / on-request / never）+ exec policy 规则 + Guardian 复核 + 进程硬化 + 网络策略 | 信创 / 内网场景必须 Rust 风格；Python 风格几乎裸奔 |
| **配置** | profile YAML + 命令行 + 环境变量 | `~/.openinterpreter/config.toml` + `.openinterpreter/config.toml`（项目级）+ `[profiles.<name>]` + `-c key=value` + feature flags | Rust 模式更体系化 |
| **可观测** | 匿名 telemetry（`disable_telemetry`） | OTel + 完整 rollouts + `~/.openinterpreter/log` + `analytics` crate | Rust 模式生产可用 |
| **客户端集成** | `interpreter --server` 启 FastAPI WebSocket | `interpreter acp` (Agent Client Protocol) + `interpreter app-server` (stdio/WS) + 多语言 SDK + `interpreter mcp-server`（把 Codex 自身当 MCP server） | Rust 模式提供"agent 标准接口"，可被任何编辑器 / orchestrator 嵌入 |
| **多 agent** | 无 | `multi_agents.rs` / `multi_agents_v2.rs` / `agent_jobs.rs`（sub-agent jobs、collaboration mode templates、Guardian review） | Rust 模式原生多 agent |
| **Harness 仿真** | 无 | 10 个 harness：`native / claude-code / claude-code-bare / zcode / kimi-code / kimi-cli / qwen-code / deepseek-tui / swe-agent / minimal`（+ 隐式的 `pi / opencode / little_coder / mini-swe-agent / terminus-2`） | 关键差异化：让同一份产品适配不同模型的"最优"调用协议，**open-interpreter 不是一个 agent，而是 10 个 agent 的 switcher** |
| **平台支持** | 跨平台，但 OS-control 模式仅 macOS（AppleScript） | macOS + Linux（landlock + bwrap）+ Windows（`windows-sandbox-rs`） | Rust 模式 Windows 沙箱是真做了的 |
| **可扩展性** | 改 `interpreter/computer/` 子类即可 | 改 tool handler / harness / skill / connector / plugin / MCP server | Rust 模式更结构化 |
| **测试覆盖** | `tests/` 几个 pytest 文件 | 每个核心文件旁 `xxx_tests.rs`，规模等同实现（如 `mcp_tool_call_tests.rs` 108KB / `multi_agents_tests.rs` 161KB / `client_tests.rs` 33KB / `rollout_reconstruction_tests.rs` 74KB） | Rust 模式测试是产品级 |
| **代码量** | 数千行 Python | 数十万行 Rust（`codex-core/src/session/mod.rs` 一个文件 164KB） | 数量级差异 |
| **对 Codex 的归属** | 原始项目，Killian Lucas 主导 | **直接 fork OpenAI Codex**（CHANGELOG 指向 openai/codex/releases，README 写 "based on Codex"） | Rust 时代 = OpenAI Codex 的开源 / 弱化版 |
| **License** | AGPL | Apache-2.0 | 更宽松 |
| **Python 原项目去哪了** | 仍在 PyPI / GitHub main，但不再有更新 | **README 明文指引到 community fork `endolith/open-interpreter`** | 不要去 PyPI 找新版 Open Interpreter，它就是 rust-v0.0.x |

---

## 4. 对 onionagent / deepcode 的可借鉴要点

> onionagent 当前在跑的项目：
> - 旧方向：人形机器人"感知-计划-执行"三层闭环（已搁置）
> - 新方向：`github.com/openclaw/deepcode`——基于 LangChain Deep Agents 框架复刻 MiniMax Code v3.0.47 的开源信创合规 Vibe Coding 智能体
> - 用户角色：Python 算法工程师，单人全栈，K8s / Docker 熟练
> - 选型倾向：流派 A（Cline 风格 XML 协议 + 自定义 finish 标签）

### 4.1 Python 时代值得复用的极简模式

1. **`respond()` 单生成器循环 + 双向消息流** 是教科书级的"主循环"实现——LLM chunks → assistant message → code message → computer run → computer message → 再喂给 LLM。可以用 Python 协程轻松复刻，deepcode 选 LangChain Deep Agents 的话可参考其 agent loop 怎么写。
2. **LMC 协议（code as a message）** 是"不用 tool call 也能让 LLM 干活"的经典思路——对不支持原生 tool call 的模型（如早期本地小模型）依然有效。deepcode 走 Cline 风格 XML 协议是这条路的演进。
3. **Computer 聚合根**（一个对象聚合 mouse/keyboard/display/browser/...）是"把 OS 当 API"的好范式，open-interpreter 后来 `interpreter/computer/os.py` 这种设计很直接。deepcode 如果要做"computer use"可以借鉴。
4. **multi-language REPL** (`Terminal.languages[]`) 启发：如果 deepcode 要让 LLM 跑 Python 之外的代码（shell / SQL / R / ...），可以参考 `BaseLanguage` + `SubprocessLanguage` 的接口设计。

### 4.2 Rust 时代必须抄的"产品级"模式

1. **沙箱 + approval 分离**——`sandbox_mode`（资源隔离） × `approval_policy`（决策时机） × `approvals_reviewer`（人/AI 审）三轴正交。信创 / 内网场景必须做到这个粒度。
2. **AGENTS.md 机制**——global + 项目路径拼接 + override 的三段式优先级，`docs/agents_md.md` 是最佳实践。deepcode 应该原生支持用户在自己项目写 `AGENTS.md`。
3. **Harness 切换**（10 个 harness 路由）——同一个产品适配不同模型的最优调用协议。deepcode 如果要支持 MiniMax / OpenAI / Anthropic / Ollama / 国产模型混合，必须有这个抽象层（open-interpreter 用 `WireApi × Harness → StreamTransportRoute` 二维路由表实现，参考 `harness/routing.rs`）。
4. **Rollout JSONL + ThreadStore + State DB** 三层持久化——单 turn JSONL 适合回放，ThreadStore KV 适合元数据，State DB 适合 pipeline 协调（带 claim 锁 / watermark）。deepcode 的记忆 pipeline 可以照搬。
5. **Memories 两阶段**：Phase 1 (rollout → raw_memory) + Phase 2 (global consolidation → workspace diff → MEMORY.md / skills/)，用水位 + 锁做协调，避免并发写。完全对齐 onionagent 计划的"三层记忆 namespace"。
6. **app-server + acp-server + SDK + mcp-server** 四种客户端接入姿势——把 agent 当成可被任何编辑器 / orchestrator 调用的"服务"。deepcode 至少要做 `mcp-server` 暴露，让自己能被 Claude Code / Cursor / Zed 调用。
7. **MCP 原生支持**——`mcp.rs` / `mcp_tool_call.rs` 79KB 实测是真做了 MCP 客户端+服务器双向。deepcode 必须原生 MCP。
8. **配置 precedence 6 级** + profile + feature flag + `-c key=value` TOML 行覆盖——参考 `docs/config.md`。
9. **TUI / 非交互 / 编辑器 / CI** 四种入口分开（`interpreter` / `interpreter exec` / `interpreter acp` / `interpreter app-server`）——避免把所有逻辑塞进一个 TUI 入口。
10. **Codex V4A patch 协议**（`apply_patch.rs`）——LLM 输出结构化 diff，比自然语言 patch 更稳。deepcode 写文件 / 改文件应该用类似协议。
11. **Harness 别名表（`harness_aliases.rs` 198KB）**——给同一份工具在 10 个 harness 下定义不同 schema，是 deepcode 多模型适配要抄的核心。
12. **回放/调试**——`rollout_reconstruction.rs` 可以从 JSONL 重放整个 turn，调试 / 复现时极其重要。
13. **Otel + analytics + log_dir** 三件套——生产级可观测。

### 4.3 不建议照搬的

- Rust 时代**单 crate 单文件 100+ KB**（`session/mod.rs` 164KB、`tools/handlers/harness_aliases.rs` 198KB）——工程上 OK，但 deepcode 用 Python 复刻的话应保持每个模块 < 1000 行。
- `Bazel` + `Cargo` + `pnpm` 三套构建系统同时存在——过工程化，单人项目用 Cargo 就够了（如果做 Rust 版）。
- 实时多模态（`realtime_context.rs` / `realtime_webrtc/`）——和"coding agent"目标不符，不必投入。

### 4.4 一个值得提问洋葱头的事

> **open-interpreter 已经在做的事情，跟 MiniMax Code v3.0.47 + deepcode SRS 是不是高度重合？**
>
> - `interpreter exec` ≈ MiniMax Code 的非交互模式
> - `interpreter acp` ≈ deepcode 的编辑器集成
> - `interpreter app-server` ≈ deepcode 的 app-server
> - `interpreter mcp-server` ≈ deepcode 的 MCP server
> - 10 个 harness 切换 ≈ 多 provider 切换
> - AGENTS.md / skills / memories ≈ deepcode SRS 的"项目记忆"+"技能库"
> - sandbox + approval + exec policy ≈ 信创合规的安全栈
>
> 这意味着 deepcode 完全可以以 open-interpreter (Rust 版) 为**最大单一参考实现**（甚至直接 fork），而不是从零复刻 MiniMax Code。**但需要先确认**：用户是否接受 fork OpenAI Codex 的法律风险（Apache-2.0 OK，但 OpenAI 商标 / 命名要小心），以及 fork 后能否真正做到"信创合规 + 模型可热插拔"。

---

## 5. 一句话总结

**Open Interpreter 1.x (Python) 是 2024 年极简的"自然语言 → 本地多语言代码执行"原型，单例 `OpenInterpreter` + 9 种语言 REPL + LMC 协议；Open Interpreter 2.x (Rust) 是 2025–2026 年把 OpenAI Codex fork 过来改造的工业级 coding agent，80+ Cargo crate + 10 个 harness 路由 + 沙箱/approval/exec policy 三层安全 + 跨会话 memories pipeline + app-server / ACP / SDK / MCP 四种客户端集成姿势。** 对 deepcode 来说，Python 时代是"主循环怎么写"的范本，Rust 时代是"产品级 coding agent 长什么样"的范本，**建议把 Rust 版当成 deepcode 的最大单一参考实现，而不是从零复刻 MiniMax Code**——前提是法务和信创合规两个条件可接受。
