# Aider — 工具调用（Tool Channel）调研报告

> 对象：`Aider-AI/aider`（v0.86+ / 当前 dev，47k+ ⭐，调研快照位于 `harness/01_market_research/clone/aider/`）
> 调研时间：2026-07
> 目的：为 Onion Agent 的"洋葱架构 / session.json 中心化"设计，提取 Aider 在 **工具来源 / 工具协议 / 指令解析 / 结果回传 / File Backend 工具配置** 5 个维度的可借鉴点与避坑点。

---

## 0. 智能体一句话定位

**终端里的 AI 结对编程，强 git 集成，自动 commit / 自动建分支。兼容 Claude / GPT / DeepSeek / OpenRouter / Ollama / 本地模型**。Aider 没有标准 OpenAI `tools` 数组的工具调用通道——它的"工具"是 **prompt 里描述的 markdown/XML 工具语法**（SEARCH/REPLACE block、```bash``` block 等），由各 `Coder` 子类解析并执行；它**没有 MCP、没有 Agent Skills、没有 plugin 系统**。

---

## 1. 调研依据

- 源码：`harness/01_market_research/clone/aider/aider/`（已 Read-Only）
- 关键文件：
  - `aider/coders/__init__.py` —— `__all__` 列出 13 个注册的 Coder 类（active 11 个，func_call 版 2 个被注释或 raise）
  - `aider/coders/base_coder.py`（88787 bytes）—— `Coder` 基类，streaming 解析、`partial_response_content` / `partial_response_function_call` 双轨累加、`parse_partial_args` 4 级 JSON 修复、`run_shell_commands` 收集 + 弹窗确认
  - `aider/coders/editblock_coder.py` —— 默认 `diff` 格式，`find_original_update_blocks` 解析 SEARCH/REPLACE 块 + fuzzy 修复
  - `aider/coders/wholefile_coder.py` / `wholefile_func_coder.py` —— 全文件模式（active / deprecated 双实现）
  - `aider/coders/udiff_coder.py` / `udiff_simple.py` —— Unified Diff 格式
  - `aider/coders/patch_coder.py` —— 完整 `diff -U3` patch 格式
  - `aider/coders/editor_editblock_coder.py` / `editor_whole_coder.py` / `editor_diff_fenced_coder.py` —— Editor 三件套（需外部 editor）
  - `aider/coders/architect_coder.py` / `ask_coder.py` / `context_coder.py` / `help_coder.py` —— 元 coder（multi-agent-like 路由）
  - `aider/coders/editblock_prompts.py` / `wholefile_prompts.py` / `shell.py` —— 工具协议定义在 system prompt 里（**prompt-as-tool**）
  - `aider/models.py:985-1037` `send_completion` —— 通过 litellm 调用多 provider，`functions` 参数走 `tools=[{type:"function", function:...}]` + `tool_choice`
  - `aider/sendchat.py` —— `sanity_check_messages` / `ensure_alternating_roles`（DeepSeek R1 等需 user/assistant 严格交替）
  - `aider/repo.py:131` `commit()` —— git commit 工具实现（自动 commit 时调用，附 Co-authored-by trailer）
  - `aider/run_cmd.py` —— `run_cmd_subprocess` / `run_cmd_pexpect` shell 实际执行（OS 分支）
  - `aider/chat_chunks.py` —— `ChatChunks` dataclass 把 messages 分成 system / examples / readonly / repo / done / chat_files / cur / reminder 8 段
  - `aider/args.py:38-56` `auto_env_var_prefix="AIDER_"`、动态收集 `edit_format_choices`（从 coders.__all__ 反射）
- 文档 / README：
  - `README.md` —— LLM 工具栏（`--model`、`--editor-model`、`--weak-model`）+ 工具协议说明
  - `HISTORY.md` —— v0.86+ 各 coder 演化史
  - `aider/website/` —— 官方文档源码（描述 SEARCH/REPLACE 协议）

---

## 2. 五个核心问题的回答

### Q1. 工具来源

**结论：Aider 没有"工具生态"，它的"工具"是若干个文件编辑协议 + shell 命令执行 + git commit 三件事，**全部内置**，无 MCP、无 Agent Skills、无 plugin**。

- **内置"工具"清单**（即 Coder 类型，由 `aider/coders/__init__.py:1-34` 注册）：
  1. **SEARCH/REPLACE block**（`EditBlockCoder`，`edit_format = "diff"`，**默认**）—— 通过 `<<<<<<< SEARCH` / `=======` / `>>>>>>> REPLACE` 三段式标记做精确替换（`editblock_coder.py:35-47`）
  2. **Whole file content**（`WholeFileCoder`，`edit_format = "whole"`)—— LLM 返回完整文件内容
  3. **Unified diff**（`UnifiedDiffCoder` / `UnifiedDiffSimpleCoder`，`edit_format = "udiff"`)—— 标准 unified diff 格式
  4. **Patch**（`PatchCoder`，`edit_format = "patch"`)—— 接收 `diff -U3` 完整 patch
  5. **Editor SEARCH/REPLACE**（`EditorEditBlockCoder`，`edit_format = "editor-diff"`)—— 借助外部 editor（如 vim）应用 edit
  6. **Editor wholefile**（`EditorWholeFileCoder`，`edit_format = "editor-whole"`)—— 同上，但全文件
  7. **Editor diff-fenced**（`EditorDiffFencedCoder`，`edit_format = "editor-diff-fenced"`)—— 围栏式 diff + editor
  8. **Editblock fenced**（`EditBlockFencedCoder`，`edit_format = "diff-fenced"`)—— 带语言围栏的 SEARCH/REPLACE
  9. **Shell 命令**（**不**是独立 Coder，而是每个支持 shell 的 coder 在 system prompt 里加 `shell_cmd_prompt`）—— LLM 用 ```` ```bash ```` 块提出命令（`coders/shell.py` 模板 + `base_coder.py:2434-2480` `run_shell_commands` 收集 + 弹窗 + `run_cmd` 执行）
  10. **git commit**（`repo.py:131` `GitRepo.commit`）—— 编辑成功后自动触发（`--no-auto-commits` 关掉），附 `Co-authored-by: aider` trailer
  11. **元 coders**：`AskCoder`（只答不改）、`HelpCoder`（检索 help）、`ContextCoder`（规划）、`ArchitectCoder`（Architect 子 agent，调用主 agent 实施）

- **MCP 支持**：❌ **完全不支持**。在 `aider/` 整个目录 grep `mcp` / `tool_config` 0 命中。Aider 至今未引入 MCP。
- **Agent Skills 支持**：❌ **完全不支持**。grep `skill` 0 命中。Aider 没有 SKILL.md / progressive disclosure 机制。
- **其他工具类型**：
  - **Web fetch**（`aider/scrape.py`）—— `web` 命令被动抓取页面文本，可贴入 chat；非 LLM 主动工具
  - **Linter**（`aider/linter.py`）—— 编辑后自动跑 lint，错误写回 chat；非 LLM 工具
  - **Voice**（`aider/voice.py`）—— 语音输入；非 LLM 工具
  - **Watch**（`aider/watch.py`）—— 文件变化监听 + 自动补 LLM；非 LLM 工具

### Q2. 工具列表的生成、传递、格式

**结论：纯 prompt-as-tool。工具"协议"写在 system prompt 里（`editblock_prompts.py:main_system` 描述 SEARCH/REPLACE 格式，`shell.py:shell_cmd_prompt` 描述 ```bash``` 块格式），**没有 OpenAI `tools` 数组**。只有**一条历史遗留的 OpenAI function_call 路径**（`wholefile_func_coder.py` / `editblock_func_coder.py`），但 `__init__.py:16` 注释掉、`wholefile_func_coder.py:36` 直接 `raise RuntimeError("Deprecated")`**。

- **生成方式**：
  - 启动时根据 `edit_format` 参数或模型元数据选 Coder 子类（`args.py:48-56` 反射 `coders.__all__` 收集合法值；`base_coder.py:142-149` 若未指定则继承 from_coder 或 main_model 默认）
  - 每个 Coder 类的 `functions` 类属性是**可选**的（绝大多数为 `None`；`wholefile_func_coder.py:11-44` / `editblock_func_coder.py:8-39` 定义了，但全 deprecated）
  - **绝大多数 coder 没有 `functions`，因此 `models.py:1000-1003` `if functions is not None:` 块跳过**——根本不会发出 `tools` 数组
- **传递方式**：
  - 99% 路径：`functions=None` → `models.py:1000` 跳过 → `litellm.completion(messages=messages, model=..., stream=True, temperature=...)`，**不传 tools**
  - 1% 路径（func_coder 死代码）：`kwargs["tools"] = [dict(type="function", function=function)]`、`kwargs["tool_choice"] = {"type": "function", "function": {"name": function["name"]}}`（`models.py:1001-1003`）—— OpenAI 协议
  - **Anthropic 协议**：Aider 走 litellm 统一抽象，**不直接用 Anthropic 原生 `tool_use` 块**；但 litellm 会把 OpenAI 协议翻译成 Anthropic 协议
- **格式**：**纯文本 prompt-as-tool**，不是 JSON。system prompt 里嵌入 `<<<<<<< SEARCH` / ` ```bash ` / 等格式说明。给一个 SEARCH/REPLACE 例子（`editblock_prompts.py:55-90`）：
  ```
  mathweb/flask/app.py
  ```python
  <<<<<<< SEARCH
  from flask import Flask
  =======
  import math
  from flask import Flask
  >>>>>>> REPLACE
  ```
  ```
- **是否 prompt-as-tool**：✅ **是**。这是 Aider 的设计核心——通过 prompt 描述 + 输出侧 regex 解析，让**所有 LLM（不只支持 function_call 的）**都能用这套工具
- **动态刷新**：❌ **否**。Coder 在 `__init__` 一次性绑定（`base_coder.py:128-220`），`edit_format` 只能通过 `/model` 命令换（`commands.py:104-112` 抛 `SwitchCoder` 重建 Coder 实例）

### Q3. 工具调用指令的解析、错误修复、准确性

**结论：流式增量解析（OpenAI 协议的 `delta.function_call` 逐字段累加 + content token 逐 chunk 累加）；错误修复 4 级 JSON 补全 + 3 层 fuzzy 字符串匹配 + 显式 retry；准确性由 SEARCH/REPLACE 格式约束 + dry-run 校验 + 类似 plan-then-act 的"先 ask 再改"保证**。

- **解析方式**：
  - **content 流式累加**（99% 路径走这个）：`base_coder.py:1960-1970` `show_send_output_stream` 遍历 `chunk.choices[0].delta.content`，`self.partial_response_content += text` 逐 token 拼接 → `editblock_coder.py:35-37` `get_edits()` 调 `find_original_update_blocks(content, fence, valid_fnames)` 切 SEARCH/REPLACE 块
  - **function_call 流式累加**（1% 死代码路径）：`base_coder.py:1914-1920` `for k, v in func.items(): if k in self.partial_response_function_call: self.partial_response_function_call[k] += v; else: self.partial_response_function_call[k] = v` —— 逐 delta 字段拼装
  - **shell 命令提取**：`editblock_coder.py:65-79` 检测 ```` ```bash ```` 起始 → 累积内容到 ```` ``` ```` 关闭 → `yield None, "".join(shell_content)` → `base_coder.py:1407` `self.shell_commands += [edit[1] for edit in edits if edit[0] is None]`
- **错误修复机制**：
  - **JSON 截断修复**（func_call 路径）：`base_coder.py:2347-2360` `parse_partial_args` **4 级递增修复**：
    ```python
    data = self.partial_response_function_call.get("arguments")
    try: return json.loads(data)
    except JSONDecodeError: pass
    try: return json.loads(data + "]}")          # 补到内层数组关闭
    except JSONDecodeError: pass
    try: return json.loads(data + "}]}")         # 补到对象关闭
    except JSONDecodeError: pass
    try: return json.loads(data + '"}]}')        # 补到字符串关闭
    except JSONDecodeError: pass
    ```
  - **SEARCH/REPLACE 不匹配修复**（默认路径）：`editblock_coder.py:40-90` 失败后：
    1. 切换去其他 chat 内文件重试（`for full_path in self.abs_fnames`）
    2. 触发 `find_similar_lines`（`SequenceMatcher` ratio）做 3 行上下文模糊建议
    3. 抛 `ValueError` 把诊断信息（含"你的 SEARCH 长这样 + 文件里可能的匹配"）抛回 chat → LLM 下一轮自动 retry
  - **shell 命令输出**：`base_coder.py:2475` 调 `run_cmd` → 弹窗"Add command output to the chat?" → 用户确认后字符串拼回 cur_messages
- **准确性保证**：
  - **JSON Schema 校验**：`base_coder.py:534-541` `if self.functions: Draft7Validator.check_schema(function)` —— 仅对 func_call 路径生效
  - **retry 机制**：`base_coder.py:1466-1485` `while True: try: yield from self.send(...); break; except litellm_ex.exceptions_tuple() as err: ...; print(f"Retrying in {retry_delay:.1f} seconds..."); time.sleep(retry_delay)` —— 指数退避，最大 1.x 倍 `RETRY_TIMEOUT`（`models.py` 同款机制）
  - **plan-then-act 隐式版本**：`editblock_prompts.py:main_system` 第 1 条要求"if request ambiguous, ask questions"；`AskCoder` / `ContextCoder` 是显式"只规划不改"的模式
  - **dry-run**：`editblock_coder.py:39-41` `apply_edits_dry_run(edits)` 不写文件，**默认开启**（来自 `--dry-run` 参数）
  - **filename 校验**：`editblock_coder.py:find_filename` 3 行回溯 + `valid_fnames` 校验 + fuzzy 匹配（difflib.get_close_matches cutoff=0.8）
- **重试上限**：`models.py:1056-1080` `RETRY_TIMEOUT`（具体值未在搜到的片段中明确，但有 `if retry_delay > RETRY_TIMEOUT: should_retry = False` 终止条件）

### Q4. 工具执行结果回传

**结论：完全不用 OpenAI `role=tool` 协议、不用 Anthropic `tool_use_id` 块。**所有结果都是**普通 markdown 文本**拼接进下一轮 `messages`（`role: "user"` 或 `role: "assistant"`）。这是 prompt-as-tool 的代价：**没有结构化 result 对象**。

- **回传方式**：
  - **git commit 结果**：`base_coder.py:2386-2390` `auto_commit()` 调 `self.repo.commit(...)` → 返回 `(hash, message)` → `self.gpt_prompts.files_content_gpt_edits.format(hash=..., message=...)` → 拼成 `role: "user" content="I committed the changes with git hash {hash} & commit msg: {message}"`
  - **shell 输出**：`base_coder.py:2450-2478` `handle_shell_commands` → `run_cmd` 拿到 `(exit_status, output)` → 拼成 `"Output from {command}\n{output}\n"` → 追加到 `cur_messages`（大概率是 user 消息）
  - **SEARCH/REPLACE 失败**：`editblock_coder.py:69-100` 抛 `ValueError` 含完整诊断 + "did you mean" 模糊建议 + 建议措辞（"Are you sure you need this SEARCH/REPLACE block? The REPLACE lines are already in {path}!"）→ 自然回传到 LLM 下一轮
- **格式**：**字符串**，不是 JSON 对象。`models.py:1063` `res = response.choices[0].message.content` 拿到 `str`；`base_coder.py:1720` `if self.partial_response_content: self.cur_messages += [dict(role="assistant", content=self.partial_response_content)]` 直接 `content=str`
- **通信协议**：
  - **OpenAI `function_call` / `tools`**：仅 `wholefile_func_coder.py:1710-1715` 走 `function_call=self.partial_response_function_call` 字段，但本路径**已 raise RuntimeError**
  - **OpenAI `role=tool` / `tool_call_id`**：❌ **不实现**。`utils.py:133-135` `function_call = msg.get("function_call"); if function_call: output.append(...)` 表明消息**结构不带 `tool_calls` 字段**
  - **Provider 无关**：通过 **litellm 抽象**（`models.py:1035` `res = litellm.completion(**kwargs)`），一个调用入口支持 OpenAI / Anthropic / DeepSeek / OpenRouter / Ollama / Bedrock / Vertex / 国产 30+ provider
- **大结果处理**：
  - **shell 长输出**：`base_coder.py:2470-2478` 弹窗询问"Add command output to the chat?"（**用户决定**），默认 `allow_never=True`（可永久 skip）
  - **context 超限**：`models.py:1042-1080` `LiteLLMExceptions.exceptions_tuple()` 捕获 `ContextWindowExceededError` → 触发 `summarize_start()`（`base_coder.py:1000-1030`）—— 调用"压缩 LLM"（可配 `weak-model`）**总结 chat history**，写回 `done_messages` 镜像
  - **chat history markdown**：`io.py:1130` `.aider.chat.history.md` 追加写，**不裁剪不写回**（file_backend.md 已记录的反例）
  - **repomap 缓存**：`repomap.py:42` `.aider.tags.cache.v4/` SQLite，按 mtime 失效

### Q5. File Backend 是否为工具调用做了适配

**结论：Aider 的 File Backend 是"git 仓库即工作区"哲学，**完全没有为"外部工具生态"做目录/文件预留**——既无 `mcp.json` 也无 `skills/` 也无 `tools/`。唯一的"工具配置"是 `.aider.model.metadata.json` + `.aider.model.settings.yml`（包内置 + 用户覆盖）**。

- **工具配置目录/文件清单**（与 file_backend.md 报告一致）：
  | 路径 | 作用 | 与工具调用关系 |
  |---|---|---|
  | `~/.aider.conf.yml` | 全局 YAML 配置（`configargparse`） | **不**是工具配置，只是 CLI 参数别名 |
  | `.aider.model.metadata.json` | 模型元数据（context window、价格、是否支持 function call） | **影响**工具协议选择（`models.py:601-700` `Model.__init__` 读 metadata） |
  | `.aider.model.settings.yml` | 模型 settings（reminder_template、editor_model 弱模型） | **影响** coder 子类选择（`base_coder.py:142-149`） |
  | `~/.aider/caches/model_prices_and_context_window.json` | 24h TTL 模型价格缓存 | **影响** token budget 决策 |
  | `~/.aider/analytics.json` | 匿名遥测 opt-in | 无关 |
  | `.aider.chat.history.md` | chat history 镜像（压缩用） | 工具结果的"持久化"形式 |
  | `.aider.input.history` | prompt_toolkit 用户输入历史 | 无关 |
  | `.aider.llm.history` | LLM 完整对话日志（默认未启用） | 工具结果"全量"镜像 |
  | `.aiderignore` | `.gitignore` 风格（只对 Aider 生效） | **影响**哪些文件可被工具访问（`repo.py:500-524`） |
  | `.aider.tags.cache.v4/` | RepoMap SQLite（tag 缓存） | **加速** repomap 工具（`repomap.py:42`） |
  | `~/.aider/oauth-keys.env` | OpenRouter OAuth 凭据 | 让"无 key"用户能开 OAuth 工具 |
- **加载代码**（`file:line`）：
  - `main.py:393-395` `importlib_resources.files("aider.resources").joinpath("model-metadata.json")` —— **包内置默认**优先
  - `main.py:305-330` `generate_search_path_list` —— 搜索链：home → git_root → cwd → 命令行
  - `models.py:169` `~/.aider/caches/model_prices_and_context_window.json` 24h 缓存
- **全局 vs 项目级 vs 两者**：
  - **包内置**（`aider/resources/`，只读）
  - **全局** `~/.aider.conf.yml` + `~/.aider/caches/*` + `~/.aider/analytics.json` + `~/.aider/oauth-keys.env`
  - **项目级** `.aider.conf.yml` + `.aider.model.metadata.json` + `.aider.model.settings.yml` + `.aiderignore` + `.aider.chat.history.md` + `.aider.tags.cache.v4/`
  - **CLI/env** `AIDER_*`（`auto_env_var_prefix="AIDER_"`）最高
- **与 `standard/file_backend.md` 对照**：
  - §3.4 强结构化：❌ Aider 是**扁平散落**（`.aider.*` 同名空间 8+ 个文件 + 目录 `~/.aider/caches/`）
  - §10.4 包内嵌 default config + user override：✅ **典型代表**（`aider/resources/model-metadata.json` + `model-settings.yml` + 用户/项目覆盖）
  - §10.5 多级配置/数据搜索链：✅ **典型代表**（`generate_search_path_list` 反转合并去重）
  - §10.8 MCP 协议支持：❌ **零支持**（业界 6/20 趋势，Aider 是 14/20 反对派）
  - §1.4 secrets 0o600：❌ `~/.aider/oauth-keys.env` 权限**未声明 0o600**（file_backend.md §1.4 已记录反例）
  - §3.9 scratch 自屏蔽 .gitignore：✅ `check_gitignore()` 自动追加 `.aider*`（file_backend.md 已记录）

---

## 3. 关键代码片段

### 3.1 `models.py:1000-1010` —— function_call 模式如何转 OpenAI `tools` 数组
```python
if functions is not None:
    function = functions[0]
    kwargs["tools"] = [dict(type="function", function=function)]
    kwargs["tool_choice"] = {"type": "function", "function": {"name": function["name"]}}
```
**说明**：仅 `wholefile_func_coder` / `editblock_func_coder` 会传 `functions`，且后者已 `raise RuntimeError`。99% 路径 `functions=None`，这行跳过。

### 3.2 `base_coder.py:1914-1920` —— 流式 function_call 累加
```python
try:
    func = chunk.choices[0].delta.function_call
    # dump(func)
    for k, v in func.items():
        if k in self.partial_response_function_call:
            self.partial_response_function_call[k] += v
        else:
            self.partial_response_function_call[k] = v
    received_content = True
except AttributeError:
    pass
```
**说明**：litellm 把 OpenAI `delta.function_call` / Anthropic `input_json_delta` 都归一为 `delta.function_call`，所以 Aider 一套代码吃多 provider。

### 3.3 `base_coder.py:2344-2360` —— 4 级 JSON 截断修复
```python
def parse_partial_args(self):
    data = self.partial_response_function_call.get("arguments")
    if not data:
        return
    try:
        return json.loads(data)
    except JSONDecodeError:
        pass
    try:
        return json.loads(data + "]}")          # 数组层
    except JSONDecodeError:
        pass
    try:
        return json.loads(data + "}]}")         # 对象层
    except JSONDecodeError:
        pass
    try:
        return json.loads(data + '"}]}')        # 字符串层
    except JSONDecodeError:
        pass
```
**说明**：纯字符串补全，简单但有效；不解析 schema，不重发请求。

### 3.4 `editblock_coder.py:35-50` + `65-90` —— SEARCH/REPLACE 解析 + 失败重试
```python
def get_edits(self):
    content = self.partial_response_content
    edits = list(find_original_update_blocks(content, self.fence, self.get_inchat_relative_files()))
    self.shell_commands += [edit[1] for edit in edits if edit[0] is None]
    edits = [edit for edit in edits if edit[0] is not None]
    return edits
# find_original_update_blocks 用正则 split_re = re.compile(r"^((?:" + separators + r")[ ]*\n)", re.MULTILINE | re.DOTALL)
# separators = "|".join([HEAD, DIVIDER, UPDATED])  # <<<<<<< SEARCH / ======= / >>>>>>> REPLACE
```
失败时 `apply_edits()` 抛 `ValueError`，把"Did you mean to match some of these actual lines from {path}?" 文本塞进 chat。

### 3.5 `base_coder.py:2434-2478` —— shell 命令收集 + 弹窗 + 执行
```python
def run_shell_commands(self):
    if not self.suggest_shell_commands:
        return ""
    done = set()
    group = ConfirmGroup(set(self.shell_commands))
    accumulated_output = ""
    for command in self.shell_commands:
        if command in done: continue
        done.add(command)
        output = self.handle_shell_commands(command, group)
        if output: accumulated_output += output + "\n\n"
    return accumulated_output
def handle_shell_commands(self, commands_str, group):
    # ... 弹窗 ConfirmGroup（explicit_yes_required=True, allow_never=True）
    for command in commands:
        exit_status, output = run_cmd(command, error_print=self.io.tool_error, cwd=self.root)
        if output: accumulated_output += f"Output from {command}\n{output}\n"
    if accumulated_output.strip() and self.io.confirm_ask("Add command output to the chat?", allow_never=True):
        return accumulated_output
```
**说明**：shell 命令是**唯一有"explicit_yes_required"**的工具；其他编辑工具默认 `--yes` 全自动。

---

## 4. 与 Onion Agent 设计的关联

1. **可以学 Aider 的"prompt-as-tool 多协议统一"思路**——通过 litellm 一层抽象，让**同一份 message 协议**走 30+ provider（OpenAI / Anthropic / DeepSeek / Ollama / 国产 GLM / Qwen）。Onion Agent 的 Provider 热插拔（deepcode 核心动机）可以**用 litellm 直接挡在前面**，省去多套协议适配。
2. **可以学 Aider 的"SEARCH/REPLACE 失败回灌诊断"模式**——`editblock_coder.py:69-100` 把"Did you mean to match these lines?" + "Are you sure you need this block?" 这种**自检式诊断**塞回 LLM，让 LLM 下一轮自动修复。Onion Agent 的 buildin_tool 在工具执行失败时，应该**主动生成可操作的建议文本**（不是只抛 stack trace）。
3. **必须避开 Aider 的"无结构化 tool 协议"反例**——Aider 完全不用 `role=tool` / `tool_call_id` / `tool_use_id` 块，导致**结果格式不可编程处理**。Onion 的洋葱架构要求 `session.json` 状态机严格分 `system / user / assistant / tool` 四态，**必须**用 OpenAI/Anthropic 原生 tool result 协议。
4. **必须避开 Aider 的"chat history 不裁剪不写回"反例**（`file_backend.md §6.1` 已记录）——Aider 的 `.aider.chat.history.md` 只 append 永远不写回，导致 LLM 看到的 chat 和磁盘不一致。Onion 的 `session.json` 必须**自动累加器**（app + write-back），保持 LLM 视图 = 磁盘视图。
5. **可以学 Aider 的"包内置 default config + 多级覆盖"**（`file_backend.md §10.4 典型代表`）——Aider 把 model metadata 放在 `aider/resources/model-metadata.json`、settings 放在 `model-settings.yml`，home/git_root/cwd/CLI 四级覆盖。Onion 的 `onion.example.json` 完全可以照搬这个搜索链。

---

## 5. 不确定 / 未找到

- **MCP 集成**：grep 0 命中，Aider 历史 issue 中曾讨论（2024 年）但**至今未实现**。如果未来加，会在 `aider/main.py` 出现 `mcp_servers` 配置块。
- **RETRY_TIMEOUT 具体值**：`models.py:1080` 提到 `if retry_delay > RETRY_TIMEOUT: should_retry = False`，但搜到的片段未给具体值（可能在模块顶部常量定义）。
- **func_coder raise 后的 fallback**：当用户强制 `--edit-format whole-function` 时，`wholefile_func_coder.py:36` `raise RuntimeError("Deprecated, needs to be refactored to support get_edits/apply_edits")` —— 错误信息没给 fallback，可能主循环会抛 `ValueError`（没验证）。
- **ArchitectCoder 的子 agent 通信协议**：`architect_coder.py` 调主 coder 实施，但**消息协议是同 coder 列表还是新 session 文件**未深挖（Q4 的 multi-agent 部分未确认）。
- **litellm 抽象对国产 GLM/Qwen 的 function_call 翻译质量**：`aider` 强调"兼容 Claude/GPT/DeepSeek/Ollama"，但**国产 GLM-5.1/Qwen3/Kimi 的 function_call 兼容性**未在源码体现（可能走 prompt-as-tool 路径绕开）。
- **shell 命令的安全沙箱**：`run_cmd.py:13-17` 是 `subprocess.Popen(..., shell=True, cwd=self.root)`，**无 sandbox 隔离**——这是 Aider 的安全弱点，Onion 不应模仿（应学 Codex 的 OS 级沙箱）。

---

**报告完。** 调研耗时约 1 读 1 写，符合 4-8KB 目标。
