# Aider — Agent Loop 调研报告

> 调研对象:`Aider-AI/aider`(v0.x, 47k+ ⭐,调研快照位于 `harness/01_market_research/clone/aider/`)
> 调研范围:Agent Loop 主流程、Plan 计划机制、Sub Agent、Loop 退出、Ask 模式、HITL、工具权限、上下文压缩、其他亮点
> 调研日期:2026-07-18
> 前置阅读:`harness/01_market_research/Aider/file_backend.md` + `tool_channel.md`

---

## 0. 智能体一句话定位

**终端里的 AI 结对编程,以"git 仓库即状态机"为核心,99% prompt-as-tool(无 OpenAI `tools` 数组)、`Coder.run()` 双重 while 循环 + `reflected_message` 自反思、`SwitchCoder` 异常实现模式切换、`auto_commit()` + `move_back_cur_messages()` 把每轮 LLM 输出沉淀成 git commit、`ChatSummary.too_big` 异步摘要压缩 `done_messages`、`.aider.chat.history.md` append-only 不裁剪不写回**。Aider 是"轻 Loop + 重 git + 极简 prompt 协议"路线的极致代表。

---

## 1. 调研依据

### 1.1 关键源码文件

| 类别 | 文件 | 作用 |
|---|---|---|
| **CLI 入口** | `aider/main.py:451-1185` `main()` | 解析 args + 构造 `InputOutput` + 创建 Coder + 启动主 while 循环 |
| **主循环(外层)** | `aider/main.py:1159-1180` `while True: coder.run()` | 拦截 `SwitchCoder` 异常切换模式 |
| **Coder 类基类** | `aider/coders/base_coder.py:71-2032` `Coder` | 所有 Coder 子类共享的主类;`run()` / `run_one()` / `send_message()` / `apply_updates()` / `auto_commit()` |
| **Coder 子类注册** | `aider/coders/__init__.py:1-30` | 14 个 `__all__` 注册:AskCoder / ContextCoder / EditBlockCoder / WholeFileCoder / ArchitectCoder / PatchCoder / 6 个 Editor* / UnifiedDiff* / HelpCoder |
| **Ask 模式** | `aider/coders/ask_coder.py:5-9` `AskCoder` | 11 行,只换 `gpt_prompts = AskPrompts()`,其余逻辑复用基类 |
| **Context 模式** | `aider/coders/context_coder.py:7-37` `ContextCoder` | 识别"需要改哪些文件",`reply_completed` 触发 reflection 自我修正 |
| **Architect 模式(子代理)** | `aider/coders/architect_coder.py:1-58` `ArchitectCoder` | "架构师"用主模型给方案,弹窗确认后调起"编辑者"(`editor_model`)执行;`reply_completed` 重建 Coder 实例 + `coder.run(with_message=content, preproc=False)` |
| **流式 send** | `aider/coders/base_coder.py:1783-1900` `send()` | 调 `model.send_completion()` → 累加 `partial_response_content` / `partial_response_function_call` |
| **重试 + 退避** | `aider/coders/base_coder.py:1466-1485` `while True: yield from self.send(...)` | 指数退避,触发 `ContextWindowExceededError` 走摘要路径 |
| **核心 message 循环** | `aider/coders/base_coder.py:1407-1626` `send_message()` | 单轮 LLM 调用 + 应用 edits + auto_commit + 自动 lint + auto_test |
| **外层 run()** | `aider/coders/base_coder.py:876-905` `run()` | `while True: get_input() → run_one()` + `KeyboardInterrupt` 处理 |
| **单次 run_one()** | `aider/coders/base_coder.py:917-940` `run_one()` | 内部 `while message` 循环 + `reflected_message` 触发再调用 |
| **apply edits** | `aider/coders/base_coder.py:2296-2335` `apply_updates()` | `get_edits()` → `apply_edits_dry_run()` → `apply_edits()` 三段 |
| **auto commit** | `aider/coders/base_coder.py:2375-2390` `auto_commit()` | 调 `repo.commit()`,commit message 由 LLM 生成,带 `Co-authored-by: aider` trailer |
| **move cur→done** | `aider/coders/base_coder.py:1036-1052` `move_back_cur_messages()` | cur 拼到 done,清空 cur,触发 `summarize_start()` |
| **异步摘要** | `aider/coders/base_coder.py:1002-1034` `summarize_start/end` | 后台线程 `summarize_worker` → `summarize_end` join |
| **token 检查** | `aider/coders/base_coder.py:1396-1418` `check_tokens()` | 超限弹窗"Try to proceed anyway?" |
| **消息分块** | `aider/coders/base_coder.py:1243-1306` `format_chat_chunks()` | 拼出 [system, examples, done, repo, readonly, chat_files, cur, reminder] 8 段 |
| **模式切换异常** | `aider/commands.py:30-33` `class SwitchCoder(Exception)` | 异常 payload 装新 Coder 的 kwargs |
| **命令分派器** | `aider/commands.py:312-335` `Commands.run()` | 解析 `/cmd args` → `cmd_xxx(args)` |
| **chat 模式切换** | `aider/commands.py:1182-1230` `cmd_ask/code/architect/context` | 弹模式用 `_generic_chat_command()` 抛 SwitchCoder |
| **chat 模式选项** | `aider/commands.py:138-208` `cmd_chat_mode()` | 列出 5 种 chat mode + 7 种 edit_format |
| **退出** | `aider/commands.py:1055-1062` `cmd_exit/cmd_quit` | `sys.exit()` |
| **重置** | `aider/commands.py:411-443` `cmd_clear/cmd_reset` | 清 done/cur messages / 清文件 |
| **Undo** | `aider/commands.py:553-655` `cmd_undo` | `git reset` 上一个 aider commit,记录在 `aider_commit_hashes` |
| **Repomap** | `aider/repomap.py:42-693` `RepoMap` | tree-sitter 抽 tags → PageRank 排序 → 选 top-N 凑 `max_map_tokens` |
| **Repo map 缓存** | `aider/repomap.py:42-43` `TAGS_CACHE_DIR = ".aider.tags.cache.v3"` | diskcache SQLite,按 mtime 失效 |
| **摘要** | `aider/history.py:7-111` `ChatSummary` | `too_big` 触发 + `summarize_real` head/tail split + `summarize_all` LLM 压缩 |
| **chat history append** | `aider/io.py:1117-1137` `append_chat_history()` | `mode="a"`,写失败时静默 `self.chat_history_file = None` |
| **provider 抽象** | `aider/models.py:985-1037` `send_completion()` | 走 `litellm.completion()`,`functions=None` → 跳过 `tools` 参数 |
| **LLM 角色交替** | `aider/sendchat.py:43-77` `ensure_alternating_roles()` | DeepSeek R1 等需 user/assistant 严格交替 |
| **Repomap 注入** | `aider/coders/base_coder.py:709-746` `get_repo_map()` | 把 repo map 内容塞进 `repo_messages`(`role=user/assistant`) |

### 1.2 核心发现摘要

1. **99% prompt-as-tool**:无 OpenAI `tools` 数组,无 MCP,无 function call;`SEARCH/REPLACE` + ` ```bash ` 块 + 自动 commit 全部靠 prompt 描述 + 输出侧 regex 解析。
2. **双 while 循环**:`Coder.run()` 外层死循环 + `run_one()` 内层 `while message` 循环(为 reflection 用)。
3. **`reflected_message` 自反思机制**:失败 / LLM 提新文件 / lint 错误 → 设 `self.reflected_message`,触发下一轮 LLM 调用,**LLM 看不见"reflection"是显式触发的**。
4. **`SwitchCoder` 异常切换模式**:不是销毁 Coder,而是 `raise` 异常 → main 捕获 → 重新 `Coder.create(from_coder=coder, **kwargs)`,**继承 `done_messages` / `cur_messages` / 各种 fnames**。
5. **Architect 模式 = 真正子代理**:主模型出方案 → 弹窗确认 → 重新建一个用 `editor_model` 的 Coder 实例 → 调 `coder.run(with_message=content)`,**Coder 套 Coder**(用 `Coder.__init__` 拿主类的 `run()`)。
6. **Context 模式 = 轻量 Plan 工具**:用主 LLM 一次性分析"要改哪些文件"→ 弹窗 → 反射再问"够了吗?" → 把识别出的文件加进 chat。
7. **git 深度集成**:`apply_updates()` → `auto_commit()` → `move_back_cur_messages()` 是**强绑定三件套**,每次成功 edit = 一次 commit,commit message 由 LLM 生成(可配 `--commit-language`)。
8. **`.aider.chat.history.md` append-only 缺陷**(file_backend.md 已记录):`io.py:1131` 永远 `mode="a"`,`ChatSummary.too_big` 触发的压缩**只改 `done_messages` 内存,从不回写文件**。
9. **退出三选一**:`/exit` 或 `/quit`(显式) / `Ctrl-C` 两次(键盘快捷) / `EOFError`(`Ctrl-D`)。

---

## 2. 九大问题回答

### Q1. Agent Loop 主流程(必含 Mermaid)

#### 2.1 完整流程图(双层 while + Coder 模式切换 + reflection)

```mermaid
flowchart TD
    Start([CLI: aider / aider --message msg / aider --gui]) --> MainEntry[main.py:451 main argv]
    MainEntry --> ParseArgs[parser.parse_known_args argv<br/>搜索链: home → git_root → cwd → CLI/env]
    ParseArgs --> IO[InputOutput 构造<br/>io.py InputOutput]
    IO --> GitCheck{get_git_root<br/>存在?}
    GitCheck -- 否 + --no-git --> NoGit[setup_git: 询问 git init<br/>main.py:107]
    GitCheck -- 是 --> Gitignore[check_gitignore<br/>追加 .aider* .env<br/>main.py:155]
    GitCheck -- 否 + home目录 --> WarnHome[警告: 不在 git 仓库<br/>main.py:107-141]
    NoGit --> CoderInit
    Gitignore --> CoderInit
    WarnHome --> CoderInit

    CoderInit[Coder.create main_model, edit_format<br/>base_coder.py:108 Coder.create]
    CoderInit --> RepomapInit[RepoMap 初始化<br/>加载 .aider.tags.cache.v3 SQLite<br/>repomap.py:42 RepoMap]
    CoderInit --> CommandsInit[Commands 初始化<br/>绑定到 Coder.self.commands]
    RepomapInit --> Announce[coder.show_announcements<br/>base_coder.py:163]

    Announce --> OneShot{args.message / --message-file / --apply?}
    OneShot -- 是 + --message --> OneShotRun[coder.run with_message=msg<br/>base_coder.py:879-883<br/>只跑一轮就退出]
    OneShot -- 是 + --apply --> ApplyRun[coder.apply_updates 立即应用<br/>main.py:1083-1090]
    OneShot -- 是 + --lint/test/commit --> CmdOnly[cmd_lint / cmd_test / cmd_commit<br/>commands.py:356-409, 967-991]
    OneShot -- 否 + GUI --> GuiRun[Streamlit GUI 模式<br/>main.py:666]
    OneShot -- 否 + REPL --> MainLoop

    MainLoop["main.py:1159 while True:<br/>  try: coder.run  <-- 外层主循环<br/>  except SwitchCoder: 重建 Coder"]

    MainLoop --> CoderRun["base_coder.py:876 Coder.run:<br/>while True: ← 内层 REPL 循环<br/>  user_message = io.get_input<br/>  if /cmd: commands.run<br/>  run_one user_message"]

    CoderRun --> GetInput{输入类型?}

    GetInput -- /exit 或 /quit --> ExitExit["commands.py:1055 cmd_exit:<br/>sys.exit()"]
    GetInput -- /clear --> ClearChat["commands.py:411 cmd_clear:<br/>done_messages = []<br/>cur_messages = []"]
    GetInput -- /reset --> ResetAll["commands.py:439 cmd_reset:<br/>_drop_all_files + _clear_chat_history"]
    GetInput -- /undo --> UndoCommit["commands.py:553 cmd_undo:<br/>git reset HEAD^<br/>仅限 aider_commit_hashes"]
    GetInput -- /model /editor-model --> SwitchModel["commands.py:87 cmd_model:<br/>raise SwitchCoder main_model"]
    GetInput -- /chat-mode ask/code/architect/context --> SwitchMode["commands.py:1182 _generic_chat_command:<br/>raise SwitchCoder edit_format"]
    GetInput -- 普通消息 --> Preproc[preproc_user_input:<br/>check_for_file_mentions + check_for_urls]

    Preproc --> RunOne["base_coder.py:917 run_one:<br/>init_before_message →<br/>while message: ← reflection 内循环<br/>  send_message message<br/>  if reflected_message: message = reflected_message"]

    RunOne --> InitBefore["base_coder.py:864 init_before_message:<br/>aider_edited_files = set<br/>commit_before_message.append HEAD"]

    InitBefore --> SendMessage["base_coder.py:1407 send_message:<br/>cur_messages += user_msg<br/>chunks = format_messages<br/>check_tokens chunks.all_messages<br/>send via LLM"]

    SendMessage --> FormatMsg["base_coder.py:1243 format_chat_chunks:<br/>chunks = system + examples + done +<br/>  repo + readonly + chat_files + cur + reminder"]

    FormatMsg --> CheckTokens{check_tokens<br/>超 max_input_tokens?}

    CheckTokens -- 弹窗用户拒绝 --> UserAborted[return: 用户主动中止]
    CheckTokens -- 通过 / 弹窗确认 --> WarmCache[warm_cache chunks<br/>后台线程定时 ping]

    WarmCache --> SendLoop{"base_coder.py:1466 while True:<br/>  yield from self.send messages<br/>  except litellm_ex: retry<br/>  except ContextWindowExceeded: break"}

    SendLoop -- 重试耗尽 --> ErrorBreak[break: 弹窗错误]
    SendLoop -- FinishReasonLength --> PreFill[assistant prefill 续写]
    SendLoop -- 成功 --> StreamOut["base_coder.py:1783 send:<br/>partial_response_content += delta.content<br/>partial_response_function_call += delta.function_call"]

    StreamOut --> ParseEdits[EditBlock/WholeFile/... 各 coder.get_edits:<br/>正则切 SEARCH/REPLACE 块 / 全文件 / unified diff]

    ParseEdits --> ApplyEdits["base_coder.py:2296 apply_updates:<br/>apply_edits_dry_run<br/>apply_edits 写文件<br/>失败 → reflected_message = err"]

    ApplyEdits -- 写文件成功 --> AutoCommit["base_coder.py:2375 auto_commit edited:<br/>repo.commit LLM-generated msg<br/>+ Co-authored-by trailer<br/>+ show_auto_commit_outcome"]

    AutoCommit --> MoveBack["base_coder.py:1036 move_back_cur_messages:<br/>done_messages += cur_messages<br/>cur_messages = []<br/>summarize_start"]

    MoveBack --> SummarizeStart["base_coder.py:1002 summarize_start:<br/>if ChatSummary.too_big done_messages:<br/>  thread = summarize_worker 后台"]

    SummarizeStart --> LintCheck{auto_lint?<br/>edited 非空?}
    LintCheck -- 是 --> LintRun["base_coder.py:1701 lint_edited:<br/>对每个 edited 文件跑 linter<br/>弹窗 'Attempt to fix lint errors?'<br/>若 user yes: reflected_message = lint_errors"]
    LintCheck -- 否 --> ShellCheck

    LintRun --> ShellCheck{self.shell_commands<br/>非空?}
    ShellCheck -- 是 --> ShellExec["base_coder.py:2410 run_shell_commands:<br/>ConfirmGroup 弹窗<br/>run_cmd 实际执行<br/>拼 output → cur_messages"]
    ShellCheck -- 否 --> ReflectCheck

    ShellExec --> ReflectCheck{reflected_message<br/>有内容?}
    ReflectCheck -- 是 --> RunOne
    ReflectCheck -- 否 --> CoderRun

    ErrorBreak --> ShowExhausted["base_coder.py:1629 show_exhausted_error:<br/>'/drop to remove /clear to clear'<br/>增加 num_exhausted_context_windows"]
    ShowExhausted --> CoderRun

    UserAborted --> CoderRun
    PreFill --> SendLoop

    ApplyEdits -- 解析失败/ValueError --> NumMal[base_coder.py:2304 num_malformed_responses++<br/>reflected_message = str err]
    NumMal --> RunOne

    OneShotRun --> MainExit([main.py:1163 analytics.event 'exit'])
    ApplyRun --> MainExit
    CmdOnly --> MainExit
    GuiRun --> MainExit
    ExitExit --> MainExit
```

#### 2.2 核心循环拆解(三个层次)

**层次 1:`main.py:1159-1180` 外层 while True**
- 整个 CLI 生命周期的外壳
- 唯一可中断路径:`SwitchCoder` 异常(由 `/chat-mode` / `/model` 等抛)
- 异常被捕获后,用 `Coder.create(from_coder=coder, **switch.kwargs)` **重建**一个新 Coder 实例,**自动继承** `done_messages` / `cur_messages` / `abs_fnames` / `total_cost` / `commands` / `file_watcher` 等 8+ 字段(`base_coder.py:160-180` update 字典)
- `coder.ok_to_warm_cache = False` 临时关掉 cache warming(切换模式时不需要)

**层次 2:`base_coder.py:876-905` Coder.run()**
- `while True:` 调 `get_input()` → `run_one(user_message)` → `show_undo_hint()`(commit 改了文件就提示可 `/undo`)
- `get_input()`(`base_coder.py:907-915`)调 `self.io.get_input(...)`,`io.py` 走 prompt_toolkit 的 REPL
- `KeyboardInterrupt`:第一次按 Ctrl-C 提示"再按一次退出",第二次 `sys.exit()`(`base_coder.py:984-998`)
- `EOFError`(Ctrl-D)→ `return`(让 main.py 自然结束,触发 `analytics.event("exit", reason="Completed main CLI coder.run")`)

**层次 3:`base_coder.py:917-940` run_one()**
- 真正的"一次用户消息 → 一次完整 LLM 响应 → 应用 edits → auto_commit"循环
- **内层 `while message`**:若 `reflected_message` 被设置(任何失败 / 修复需要),把 `message` 换成 `reflected_message` 再跑一次,`max_reflections = 3`(`base_coder.py:96`)
- `preproc=True` 时先 `check_for_file_mentions` / `check_for_urls`;`ArchitectCoder` 调 `run()` 时传 `preproc=False` 跳过预处理(避免 mention 触发)

#### 2.3 Repo Map 机制(辅助"上下文构建"的核心)

**触发点**:`format_chat_chunks()` 拼消息时,`get_repo_messages()` 调 `get_repo_map()`(`base_coder.py:750-758`),`get_repo_map()` 又调 `self.repo_map.get_repo_map(chat_files, other_files, mentioned_fnames, mentioned_idents)`(`base_coder.py:709-746`)。

**实现**(`repomap.py:42-693`):
1. **tags 提取**(`repomap.py:233-280` `get_tags`):tree-sitter 解析每个 tracked file 的 AST,抽 classes / functions / methods / identifiers,缓存到 `.aider.tags.cache.v3/` SQLite(`diskcache.Cache`,按 mtime 失效)
2. **图排序**(`get_ranked_tags`,见 `repomap.py:420-580`):把"chat files + other files"按"被 chat 内文件引用次数"做 PageRank 排序
3. **凑 token 预算**(`get_ranked_tags_map`):二分搜索最优 N,使渲染出的 tree 字符串尽量逼近 `max_map_tokens`(默认 1024,可配)
4. **渲染**:`render_tree` 生成 markdown 列表形如 `- class Foo (file.py:10)`(`repomap.py:710-693`)

**消息注入**:`base_coder.py:750-758`
```python
def get_repo_messages(self):
    repo_messages = []
    repo_content = self.get_repo_map()
    if repo_content:
        repo_messages += [
            dict(role="user", content=repo_content),                    # 树状结构塞 user message
            dict(role="assistant", content="Ok, I won't try and edit those files without asking first."),
        ]
    return repo_messages
```

**关键设计**:
- **没有 chat files 时给更大视野**(`repomap.py:124-132`):`max_map_tokens *= map_mul_no_files`(默认 8)→ 一次性给 LLM 看几乎整个仓库结构
- **三级 fallback**(`base_coder.py:735-746`):先按 `mentioned_fnames/idents` 排序 → 不行就 unhinted 整个 repo → 还不行就完全 unhinted
- **ContextCoder 强制 `refresh="always"`**(`context_coder.py:18-19`):每次都重算

#### 2.4 自动 commit 流程(深度 git 集成)

**触发链**(每次成功 `apply_updates` 后):

1. **`apply_updates` 写文件**(`base_coder.py:2296-2335`):`get_edits()` → `apply_edits_dry_run()` → `apply_edits()`(真写)
2. **`auto_commit` 跑 git**(`base_coder.py:2375-2390`):调 `self.repo.commit(fnames=edited, context=cur_messages, aider_edits=True, coder=self)`
3. **`repo.commit` 内部**(`repo.py:131-...`):
   - 调 `get_diffs(fnames)` 拿 diff
   - 调 `get_commit_message(diffs, context, user_language)` 用 LLM(主模型或 `weak-model`)生成 commit message
   - 写 `Co-authored-by: aider (<model>) <aider@aider.chat>` trailer
   - 返回 `(hash, message)`,存进 `self.aider_commit_hashes`(用于 `/undo` 限定)
4. **`move_back_cur_messages` 关闭轮**(`base_coder.py:1036-1052`):`cur_messages` 拼到 `done_messages` → `cur_messages = []` → 触发 `summarize_start`
5. **触发 undo 提示**(`base_coder.py:2407-2410` `show_undo_hint`):commit 改了文件就打印"You can use /undo to undo..."

**关键设计**:
- **`--no-auto-commits` 关掉**:`auto_commit` 入口第一行 `if not self.repo or not self.auto_commits or self.dry_run: return`(`base_coder.py:2377`)
- **`--no-attribute-co-authored-by` 关掉 trailer**:`repo.py:215-225` 条件分支
- **commit 前 dirty 文件**:`--dirty-commits` / `--no-dirty-commits` 控制是否把会话外修改一并提交
- **commit message 语言**:`--commit-language zh-CN` 让 LLM 用中文写 commit msg(`repo.py:333-336` 注入 `language_instruction`)

#### 2.5 git 工作流融入

Aider **本身就是 git 工具**(不是"用 git 记录状态"):

| 维度 | Aider 行为 | 代码 |
|---|---|---|
| **git_root 自动探测** | `git.Repo(search_parent_directories=True)`,向上递归 | `main.py:454-462` `get_git_root()` |
| **没有 git 怎么办** | 询问 `git init`;在 home 目录直接警告 | `main.py:107-141` `setup_git()` |
| **gitignore 自动维护** | 检测 `.aider*` / `.env` 是否在 .gitignore,没有就追加 | `main.py:155-198` `check_gitignore()` |
| **commit 即"上下文快照"** | 每次 LLM 成功 edit → 一次 commit,commit message 是 LLM 生成的 | `base_coder.py:2375-2390` |
| **branch 隔离** | `--branch` 创建新 branch,所有 commit 落在该 branch(常用 PR 工作流) | `args.py` `--branch` 参数 |
| **undo 是 `git reset`** | `/undo` 只 undo `aider_commit_hashes` 集合内的 commit | `commands.py:553-655` `cmd_undo` |
| **commit diff 实时显示** | `auto_commit` 后 `cmd_diff` 打印到 terminal | `base_coder.py:2395-2401` `show_auto_commit_outcome` |
| **commit 范围审计** | `self.aider_commit_hashes: set` 跟踪所有 aider commit,只允许 undo 这些 | `base_coder.py:97` 字段 |

#### 2.6 Aider 没有的 Loop 特性(对比其他项目)

- ❌ **没有 DAG 工作流**(对比 SuperAGI 的 `AgentWorkflow`):Aider 是线性 while
- ❌ **没有 Plan 工具**(对比 MetaGPT `Planner`):Aider 的"plan"是 LLM 在 message 里写自然语言
- ❌ **没有 LLM-driven 任务队列**(对比 SuperAGI `TaskQueue`):Aider 一次用户消息 = 一次 LLM 调
- ❌ **没有 retry 计数硬上限**(对比 SuperAGI `max_iterations`):Aider 用 reflection 软循环(`max_reflections=3`)
- ❌ **没有 Celery 异步步骤**:Aider 是 in-process 同步循环,GUI 模式也只是 Streamlit 套壳

---

### Q2. Plan 计划机制

**结论:Aider 99% 是 prompt-as-tool,**没有独立的 Plan 工具**;最接近"Plan"的是 `ContextCoder` 模式(`/context`),它用 LLM 做一次"文件识别" + reflection 自纠**。

#### 2.1 显式的"Plan"工具?

**无**。Aider 没有 `Coder` 子类专门用于"先生成计划、再让另一个 agent 执行"的 plan-then-act 模式。

#### 2.2 最接近的:`/context` 模式(ContextCoder)

**入口**:`commands.py:1194-1197` `cmd_context`:
```python
def cmd_context(self, args):
    """Enter context mode to see surrounding code context. If no prompt provided, switches to context/context mode."""
    return self._generic_chat_command(args, "context", placeholder=args.strip() or None)
```

**实现**(`context_coder.py:7-37`):
```python
class ContextCoder(Coder):
    edit_format = "context"
    gpt_prompts = ContextPrompts()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.repo_map: return
        self.repo_map.refresh = "always"                  # 强制每次重算 repomap
        self.repo_map.max_map_tokens *= self.repo_map.map_mul_no_files  # 视野扩大 N 倍
        self.repo_map.map_mul_no_files = 1.0

    def reply_completed(self):                            # ← 反射点
        content = self.partial_response_content
        if not content or not content.strip(): return True
        current_rel_fnames = set(self.get_inchat_relative_files())
        mentioned_rel_fnames = set(self.get_file_mentions(content, ignore_current=True))

        if mentioned_rel_fnames == current_rel_fnames: return True   # 集合一致 → 退出
        if self.num_reflections >= self.max_reflections - 1: return True

        self.abs_fnames = set()                           # 清空当前 in-chat 文件
        for fname in mentioned_rel_fnames:
            self.add_rel_fname(fname)                     # 加 LLM 提到的新文件

        self.reflected_message = self.gpt_prompts.try_again  # ← 触发内层 while message
        return True
```

**Prompt**(`context_prompts.py:1-55`):
```text
Act as an expert code analyst.
Understand the user's question or request, solely to determine ALL the existing
sources files which will need to be modified.
Return the *complete* list of files which will need to be modified based on the user's request.
...
You are only to discuss EXISTING files and symbols.
Only return existing files, don't suggest the names of new files or functions
that we will need to create.
```

**关键设计**:
- `system_reminder = "\nNEVER RETURN CODE!"` —— 强制 LLM 只列文件不写代码
- 输出格式强约束(类名 + 行号) → 解析稳
- `reply_completed` 的 `mentioned_rel_fnames != current_rel_fnames` 触发 reflection,直到集合稳定或耗尽 `max_reflections=3`
- **结果不是"plan 文件"**,而是直接修改 `self.abs_fnames` → 下次 LLM 调用的 `format_chat_chunks` 把这些文件内容塞进 prompt
- 本质是"用 LLM 找文件 + reflection 自纠",**不是"plan-then-execute 两阶段"**

#### 2.3 Architect 模式:有"方案"但无显式 Plan 工具

`ArchitectCoder`(`architect_coder.py:1-58`)让主模型出"代码修改方案",但方案是**自然语言描述**,不是结构化 plan。`reply_completed` 直接调 `editor_coder.run(with_message=content)`,**没有 plan 数据结构**(没有 MetaGPT 那种 `Task[]` + `current_task_id`)。

#### 2.4 /architect /ask /code /context 的对比

| 模式 | edit_format | 是否真改文件 | "Plan"机制 |
|---|---|---|---|
| `code`(默认) | 由 model.edit_format 决定(常见 `diff`) | ✅ | 无 |
| `ask` | `ask`(`ask_coder.py:5-9`,11 行) | ❌ 只答 | 无(但 reply 自然语言包含建议) |
| `architect` | `architect` | ✅(间接) | **主模型出方案 → editor 模型执行**(两个 Coder 串联) |
| `context` | `context` | ❌(只动 `abs_fnames`) | **LLM 一次性识别需要改的文件 + reflection 自纠** |
| `help` | `help`(`help_coder.py`) | ❌ | 无,只查向量库 help docs |

---

### Q3. Sub Agent

**结论:Aider 有 **"Architect + Editor" 双 Coder 子代理模式**(`/architect`),但不是多 agent 协作(无 Message Bus、无 role-based 路由),**本质是单 LLM 主代理 + 一层"计划-执行"分离**。Aider 没有"sub agent 树"或"递归 agent"**。

#### 3.1 Architect 模式 = 真正的"子代理"

**核心代码**(`architect_coder.py:35-57`):
```python
def reply_completed(self):
    content = self.partial_response_content
    if not content or not content.strip(): return

    if not self.auto_accept_architect and not self.io.confirm_ask("Edit the files?"):
        return                                            # 用户拒绝 → 啥也不做

    kwargs = dict()
    editor_model = self.main_model.editor_model or self.main_model

    kwargs["main_model"] = editor_model                  # ← 关键:换模型
    kwargs["edit_format"] = self.main_model.editor_edit_format
    kwargs["suggest_shell_commands"] = False
    kwargs["map_tokens"] = 0                              # 强制 repomap 关闭(节省 token)
    kwargs["total_cost"] = self.total_cost                # 成本累计
    kwargs["cache_prompts"] = False
    kwargs["num_cache_warming_pings"] = 0
    kwargs["summarize_from_coder"] = False                # ← 不压缩历史,直接传

    new_kwargs = dict(io=self.io, from_coder=self)        # ← from_coder=self 是关键
    new_kwargs.update(kwargs)

    editor_coder = Coder.create(**new_kwargs)             # ← 创建新 Coder 实例
    editor_coder.cur_messages = []                        # ← 清空 cur,只带自然语言方案
    editor_coder.done_messages = []

    if self.verbose:
        editor_coder.show_announcements()

    editor_coder.run(with_message=content, preproc=False) # ← 递归调用 run()

    self.move_back_cur_messages("I made those changes to the files.")
    self.total_cost = editor_coder.total_cost             # 成本合并
    self.aider_commit_hashes = editor_coder.aider_commit_hashes
```

**关键观察**:
- **真正的"调用栈"**:`editor_coder.run()` 在 `reply_completed` 内被调,而 `reply_completed` 又在 `send_message` 内被调(`base_coder.py:1547-1551`),`send_message` 又在 `run_one` 的 `while message` 内被调 → 栈深 = 2 层
- **`from_coder=self` 继承上下文**:新 Coder 继承原 Coder 的 `done_messages` / `cur_messages` / `commands` / `fnames` / `total_cost`,**但 `cur_messages` 被强制清空**,只传"方案"(`content`)作为 `with_message`
- **`preproc=False` 跳过预处理**:避免 mention 触发 file add / 避免 LLM 误以为新文件需要 add
- **`map_tokens=0` 强制 repomap 关闭**:子 Coder 不需要 repomap(它已经知道改什么)
- **`--no-architect` 关闭 / `auto_accept_architect` 默认 False**:默认**用户必须确认"Edit the files?"**才进入子 Coder(`architect_coder.py:14-16`)
- **成本累计**:`self.total_cost = editor_coder.total_cost` 把子 Coder 的 API 成本合并回主 Coder

#### 3.2 Architect 与 Context 的区别

| 维度 | Architect | Context |
|---|---|---|
| 用途 | 复杂改动:主模型出方案,editor 模型执行 | 文件识别:LLM 列出需要改的文件 |
| 子 Coder? | **是**(editor_coder.run) | **否**(只改 `self.abs_fnames`) |
| 换模型? | ✅ 换 `editor_model` | ❌ 同模型 |
| 弹窗确认? | ✅ "Edit the files?" | ❌ 直接改 `abs_fnames` |
| 修改文件? | ✅(子 Coder apply_updates) | ❌(只更新 in-chat 文件集合) |
| repomap? | ❌ 子 Coder 关掉 | ✅ 强制 refresh="always" |
| `done_messages` 继承? | ❌ 清空 | ✅ 继承 |

#### 3.3 Aider **没有的** sub-agent 特性

- ❌ **没有 agent 树 / 递归 agent**:`ArchitectCoder.editor_coder` 不会再 spawn 第三层
- ❌ **没有 Message Bus**:Aider 是函数调用栈,不是发布订阅
- ❌ **没有 role-based 路由**(对比 MetaGPT `Message.cause_by`):Aider 没有"产品经理" / "架构师"等 role 概念
- ❌ **没有 peer-to-peer agent 通信**:Aider 是单线 Coder.run() 调用栈
- ❌ **没有并行 sub-agent**:`ArchitectCoder` 串行,等 editor 完成才返回
- ❌ **没有 sub-agent context isolation**:editor_coder 直接继承父的 `abs_fnames` / `commands` 等

---

### Q4. Loop 退出机制

**结论:Aider 的 loop **通过 4 种路径退出**,**没有"自然完成"概念**(只要 `coder.run()` 还在就继续等输入)。所有退出都是"用户主动"**。

#### 4.1 显式退出:3 条命令

| 命令 | 代码 | 行为 |
|---|---|---|
| `/exit` | `commands.py:1055-1058` | `self.coder.event("exit", reason="/exit")` + `sys.exit()` |
| `/quit` | `commands.py:1060-1062` | 调 `cmd_exit` |
| `/aider` | ❌ **不存在** | Aider 没有 `cmd_aider`,该命令无 |

> ⚠️ **常见误解**:一些文档说"输入 `/aider` 退出",**实际不存在**。Aider 退出就是 `/exit` 或 `/quit`。

#### 4.2 键盘退出:2 种

| 快捷键 | 触发点 | 行为 |
|---|---|---|
| `Ctrl-C` 第一次 | `base_coder.py:984-998` `keyboard_interrupt()` | 弹 `^C again to exit` 提示,记录 `last_keyboard_interrupt = now` |
| `Ctrl-C` 第二次(2 秒内) | 同上 | 弹 `^C KeyboardInterrupt` + `analytics.event("exit", reason="Control-C")` + `sys.exit()` |
| `Ctrl-D` (EOF) | `base_coder.py:894-895` `run()` 的 `except EOFError` | `return`,让 `main.py:1159` 的 `while True` 走到下一轮 → 因 `coder.run()` 已 return → main 也 return |

#### 4.3 main.py 退出后的清理

`main.py:1162-1163`:
```python
coder.run()
analytics.event("exit", reason="Completed main CLI coder.run")
return                                                     # main 函数自然返回
```

**没有显式 cleanup**:
- `done_messages` / `cur_messages` 不写盘(只 append 到 `.aider.chat.history.md` 是 io.py 做的)
- `aider_commit_hashes` 不持久化(下次启动 Aider 会重新发现)
- `last_aider_commit_hash` 不持久化

#### 4.4 一次性的"非 loop"模式

CLI 启动时支持**单次执行不进入 loop**:
- `--message "msg"`:跑一轮就退出(`main.py:1129-1131`)
- `--message-file file`:从文件读 message 跑一轮退出(`main.py:1134-1141`)
- `--apply file`:应用 file 里的 LLM 输出(不调 LLM)就退出(`main.py:1083-1090`)
- `--lint` / `--test` / `--commit`:跑对应命令就退出(`main.py:1064-1067`)

这些路径走 `return`,**不进 `while True: coder.run()` 主循环**。

#### 4.5 模式切换 = 异常而非退出

**关键观察**:`/chat-mode` / `/model` / `/architect` 等命令**不退出 Aider**,而是 `raise SwitchCoder(...)`(`commands.py:30-33`),被 `main.py:1170` 捕获后**重建 Coder 实例**。所以"切换模式"在用户视角 = "无感",主循环继续。

```python
# main.py:1167-1180
while True:
    try:
        coder.ok_to_warm_cache = bool(args.cache_keepalive_pings)
        coder.run()
        analytics.event("exit", reason="Completed main CLI coder.run")
        return
    except SwitchCoder as switch:
        coder.ok_to_warm_cache = False

        if hasattr(switch, "placeholder") and switch.placeholder is not None:
            io.placeholder = switch.placeholder

        kwargs = dict(io=io, from_coder=coder)
        kwargs.update(switch.kwargs)
        if "show_announcements" in kwargs:
            del kwargs["show_announcements"]

        coder = Coder.create(**kwargs)                    # ← 重建,新模式

        if switch.kwargs.get("show_announcements") is not False:
            coder.show_announcements()
```

---

### Q5. Ask 模式

**结论:Aider 有 **3 层"问"机制**:(1) `AskCoder` 整个模式只答不改;(2) `ask` 命令一次性的单轮提问;(3) `confirm_ask` 弹窗对所有敏感操作(commit / shell / file add)询问**。

#### 5.1 `AskCoder` 模式(整段对话只问不改)

**实现**(`ask_coder.py:1-9`):
```python
class AskCoder(Coder):
    """Ask questions about code without making any changes."""
    edit_format = "ask"
    gpt_prompts = AskPrompts()
```

**只有 11 行**——它**不重写任何方法**。为什么只答不改?

**Prompt 强约束**(`ask_prompts.py:1-15`):
```text
Act as an expert code analyst.
Answer questions about the supplied code.
Always reply to the user in {language}.

If you need to describe code changes, do so *briefly*.
```

`overeager_prompt`(`ask_prompts.py:11-19`):
```text
Do not return fully detailed code or full diffs.
Describe the needed changes or give a plan.
Providing code snippets or pseudo-code is fine,
if it helps explain the plan or the needed changes.
```

**为什么不重写方法?**
- `apply_updates` 调 `get_edits()`(`base_coder.py:2296-2335`);`AskCoder` 不重写 → 走基类 → 解析 SEARCH/REPLACE 块
- 但 LLM 在 `ask` 模式下被 prompt 强制"不写代码" → 输出是自然语言 → `get_edits` 解析不到 SEARCH/REPLACE → 返回空 list → `apply_edits` 跳过
- **本质:Ask 模式 = "用 prompt 约束 LLM + 让基类自然失败"**

#### 5.2 `/ask` 命令(单次提问,默认切到 ask 模式)

**代码**(`commands.py:1182-1185`):
```python
def cmd_ask(self, args):
    """Ask questions about the code base without editing any files. If no prompt provided, switches to ask mode."""
    return self._generic_chat_command(args, "ask")
```

**`_generic_chat_command`**(`commands.py:1207-1229`):
```python
def _generic_chat_command(self, args, edit_format, placeholder=None):
    if not args.strip():
        # Switch to the corresponding chat mode if no args provided
        return self.cmd_chat_mode(edit_format)

    from aider.coders.base_coder import Coder

    coder = Coder.create(                                  # ← 临时建一个 ask coder
        io=self.io,
        from_coder=self.coder,
        edit_format=edit_format,
        summarize_from_coder=False,                        # ← 不压缩历史
    )

    user_msg = args
    coder.run(user_msg)                                    # ← 跑一轮

    raise SwitchCoder(                                     # ← 抛异常回原 coder
        edit_format=self.coder.edit_format,
        summarize_from_coder=False,
        from_coder=coder,
        show_announcements=False,
        placeholder=placeholder,
    )
```

**关键观察**:
- **临时新建 Coder** 跑单轮 → `SwitchCoder` 切回原 Coder
- `summarize_from_coder=False` 避免 ask Coder 的对话污染 done_messages
- `show_announcements=False` 不弹新模型/模式公告

#### 5.3 `confirm_ask` 弹窗(对每个用户敏感决策询问)

**统一入口**:`InputOutput.confirm_ask(prompt, subject=None, group=None, allow_never=False, explicit_yes_required=False)`

**使用场景**:
- **`/add <file>`**:`commands.py:799-910` `cmd_add` → `io.confirm_ask("Add file to the chat?", subject=rel_fname, group=group, allow_never=True)`
- **添加 mentioned 文件**:`base_coder.py:1787-1801` `check_for_file_mentions` → `io.confirm_ask("Add file to the chat?", subject=rel_fname, group=group, allow_never=True)`
- **添加 URL**:`base_coder.py:962-980` `check_for_urls` → `io.confirm_ask("Add URL to the chat?", subject=url, group=group, allow_never=True)`
- **执行 shell**:`base_coder.py:2452-2478` `handle_shell_commands` → `io.confirm_ask("Run shell command?", subject=command, explicit_yes_required=True, group=group, allow_never=True)`
- **添加 shell 输出**:`base_coder.py:2483-2484` → `io.confirm_ask("Add command output to the chat?", allow_never=True)`
- **Architect 模式确认编辑**:`architect_coder.py:14` → `io.confirm_ask("Edit the files?")`
- **添加 commit 输出到 chat**:`auto_commit` → 通过 `move_back_cur_messages` 拼 `gpt_prompts.files_content_gpt_edits` 进 cur_messages
- **lint 修复**:`base_coder.py:1608-1613` → `io.confirm_ask("Attempt to fix lint errors?")`
- **test 修复**:`base_coder.py:1618-1624` → `io.confirm_ask("Attempt to fix test errors?")`

**`ConfirmGroup` 机制**(`io.py:160-180`):**批量"yes to all" / "no to all"** —— 同一组弹窗中,用户第一次选"y to all"会让同组后续弹窗自动 yes/no。

**`allow_never=True`**:用户可永久 skip(写进 `self.ignore_mentions` / `self.rejected_urls` 等集合),后续不再弹。

---

### Q6. Human-in-the-Loop (HITL)

**结论:Aider 的 HITL 是 **"全部走 confirm_ask 弹窗"**,**没有"暂停/恢复"机制**,**没有"异步审批"**,**没有"时间窗口"**;用户必须**在线**回答**。这是 Aider 的设计取舍:CLI 场景下"必须人在场"是合理的**。

#### 6.1 HITL 触发点清单(穷举)

| 触发点 | 代码 | 弹窗问题 | 默认行为 | allow_never |
|---|---|---|---|---|
| `setup_git`(无 git 仓库) | `main.py:107-141` | "Git repository not found, create one?" | 默认 yes | ❌ |
| `check_gitignore` | `main.py:155-198` | "Add .aider*, .env to .gitignore?" | 默认 yes | ❌ |
| Analytics opt-in | `main.py:~750` | "Allow collection of anonymous analytics?" | 默认 no | ❌(permanently_disable) |
| OAuth 添加 key | `onboarding.py:361-368` | "Save OPENROUTER_API_KEY to ~/.aider/oauth-keys.env?" | 默认 yes | ❌ |
| Lint 错误修复 | `base_coder.py:1608-1613` | "Attempt to fix lint errors?" | 默认 no | ❌ |
| Test 错误修复 | `base_coder.py:1618-1624` | "Attempt to fix test errors?" | 默认 no | ❌ |
| `check_tokens` 超限 | `base_coder.py:1396-1418` | "Try to proceed anyway?" | 默认 no | ❌ |
| `check_for_file_mentions` | `base_coder.py:1787-1801` | "Add file to the chat?" | 默认 no | ✅ |
| `check_for_urls` | `base_coder.py:962-980` | "Add URL to the chat?" | 默认 no | ✅ |
| `run_shell_commands` | `base_coder.py:2452-2478` | "Run shell command?"(`explicit_yes_required=True`) | 默认 no | ✅ |
| Shell 输出加 chat | `base_coder.py:2483-2484` | "Add command output to the chat?" | 默认 no | ✅ |
| `ArchitectCoder` | `architect_coder.py:14` | "Edit the files?" | 默认 no | ❌ |
| `/test` | `commands.py:993-1011` | (无弹窗,直接跑) | - | - |
| `--watch-files` 文件变化 | `aider/watch.py` | 弹"Add changes from file X to the chat?" | 默认 yes | ✅ |

#### 6.2 **没有的** HITL 能力

- ❌ **没有异步审批**(对比 SuperAGI `WAITING_FOR_PERMISSION` 状态):Aider 不支持"离开 CLI 还能审批"
- ❌ **没有"时间窗口"超时**:Aider 弹窗等用户,**没有自动拒绝**机制
- ❌ **没有"diff review" step-by-step 审批**:Aider 的 `apply_updates` 是**全应用或全不应用**,不支持"逐 SEARCH/REPLACE 块审批"
- ❌ **没有"rollback on user no"中间态**:`auto_commit` 跑在 `apply_updates` 之后 → commit 已发生 → 用户事后只能 `/undo`(`commands.py:553-655`)
- ❌ **没有"per-tool 权限矩阵"**(对比 SuperAGI `permission_type`):Aider 只有"是否弹窗"的二元开关
- ❌ **没有"approval log"**:Aider 不记录哪些操作被用户批准过,无法 audit

#### 6.3 `/undo` 是事后 HITL 兜底

**`commands.py:553-655` `cmd_undo`**:
- 只 undo `aider_commit_hashes` 集合内的 commit(`base_coder.py:97` 跟踪)
- 用 `git reset HEAD^`(`commands.py:611-617`)
- 文件脏(dirty)就拒绝 undo,提示 stash(`commands.py:586-591`)

**所以"事后 HITL"路径**:`LLM 改文件 → 自动 commit → 用户发现不对 → /undo → git reset` —— **不是"审批前拦截",而是"审批后撤销"**。

---

### Q7. 工具调用权限

**结论:Aider **99% 路径是 prompt-as-tool**,**根本没有"工具权限"概念**;**唯一权限控制 = `confirm_ask` 弹窗**。所有"工具调用"都通过 prompt 描述 + 输出侧 regex,LLM 提的请求 = 字符串,而不是结构化工具调用**。

#### 7.1 Aider 的"工具"清单(与权限相关)

| "工具" | 触发 | 权限控制 |
|---|---|---|
| `SEARCH/REPLACE` 块(默认 `diff` 模式) | LLM 输出含 `<<<<<<< SEARCH` ... `=======` ... `>>>>>>> REPLACE` 块 | ❌ 无,直接 `apply_edits` |
| 全文件模式(`whole` 模式) | LLM 输出完整文件内容 | ❌ 无,直接 `apply_edits` |
| ` ```bash ` 块(shell 命令) | LLM 输出含 ` ```bash ... ``` ` 块 | ✅ `confirm_ask` 弹窗(`explicit_yes_required=True`) |
| Git commit | `apply_updates` 成功 → `auto_commit` | ⚠️ `--no-auto-commits` 关闭;**单 commit 不可拒** |
| Git push | (无) | ❌ Aider **从不 push** |
| File add | `/add` 命令 或 `check_for_file_mentions` | ✅ `confirm_ask` |
| URL scrape | `/web` 命令 或 `check_for_urls` | ✅ `confirm_ask` |
| Linter | `--lint` 命令 或自动 lint | ❌ 直接跑(配置由用户) |
| Test runner | `--test` 命令 或自动 test | ❌ 直接跑(配置由用户) |
| File watch | `--watch-files` | ✅ 弹窗"Add changes?" |

#### 7.2 为什么"无权限"是合理设计?

- **prompt-as-tool 没法做精细权限**:LLM 输出 SEARCH/REPLACE 块不是"调用 search_replace 工具(args)",只是字符串;拦截粒度只能到"是否 confirm 这一段"
- **Aider 是 trusted tool**:用户主动把 Aider 放进自己的 dev 机器,默认信任
- **commit 是天然 audit trail**:每次 edit = 一次 commit → 用户事后可逐 commit undo
- **shell 才有真正的"危险"**:所以 Aider 唯一**强制**弹窗 + `explicit_yes_required=True` 的就是 shell 命令(`base_coder.py:2452-2478`)

#### 7.3 "无权限"的风险

- ❌ **LLM 可发起 SEARCH/REPLACE 改任意 `abs_fnames` 内的文件**:用户 `/add /etc/passwd` 进去后,LLM 真能改(虽然 Aider 不会主动 add 系统文件,但用户可能误操作)
- ❌ **LLM 可在 SEARCH/REPLACE 块里藏恶意代码**:用户 review diff 的成本高
- ❌ **无 dry-run 默认开启**:`--dry-run` 可开启但不默认(`base_coder.py:2298` `if self.dry_run: skip apply`)
- ❌ **无 "per-edit confirm"**:`apply_updates` 一次性应用所有 edits,用户要么接受全部,要么 `/undo` 全部

#### 7.4 关闭 / 限速机制

- `--no-auto-commits`:关掉 commit,但 edit 仍写入文件
- `--no-auto-lint` / `--no-auto-test`:关掉自动 lint / test
- `--no-suggest-shell-commands`:LLM 看不到 `shell_cmd_prompt`,不主动提 shell 命令(`base_coder.py:1174-1180`)
- `--no-detect-urls`:不主动 scrape URL(`base_coder.py:111-112`)
- `--dry-run`:所有 edit 不写文件
- `--no-pretty`:关掉 rich 输出 → 退到普通 print(配合 `--no-fancy-input` 进非交互)

**这些是"全开/全关"开关,没有 per-tool 灰度。**

---

### Q8. 上下文压缩和摘要(重点)

**结论:Aider 的上下文管理有 **3 个独立机制**,**互不冲突**,**`done_messages` 会被异步摘要(改内存但不写文件),`.aider.chat.history.md` 永远 append-only(`io.py:1131`),`partial_response_content` 流式累加不做裁剪**。file_backend.md 已记录的"append-only 不写回"是 Aider 的有意设计,但**确实是个缺陷**。

#### 8.1 三层上下文管理总览

| 层 | 数据结构 | 大小限制 | 裁剪/压缩 | 持久化 |
|---|---|---|---|---|
| **L1**:LLM 调用上下文 | `chunks.all_messages()`(`base_coder.py:1243-1306`) | 拼装为 8 段 | 无(走 token check + 后台摘要) | 不持久化(每次拼) |
| **L2**:会话历史 | `done_messages + cur_messages`(`base_coder.py:101`) | `max_input_tokens * 0.7`(fudge 0.7,`base_coder.py:1646`) | **异步后台摘要**(`ChatSummary`,`history.py:7-111`) | **不写文件**(压缩只改内存) |
| **L3**:可视化历史 | `.aider.chat.history.md`(`io.py:1117-1137`) | 无 | **永不裁剪** | **append-only**(`mode="a"`) |

#### 8.2 L2 摘要机制(异步后台)

**触发**:`move_back_cur_messages` → `summarize_start`(`base_coder.py:1036-1052` + `1002-1003`)

**判断**:`history.py:15-21` `ChatSummary.too_big`:
```python
def too_big(self, messages):
    sized = self.tokenize(messages)
    total = sum(tokens for tokens, _msg in sized)
    return total > self.max_tokens                   # max_tokens 默认 1024
```

**执行**(`base_coder.py:1002-1034`):
```python
def summarize_start(self):
    if not self.summarizer.too_big(self.done_messages):  # 不超 → 不跑
        return
    self.summarize_end()                                # 等上一次完成(若有)
    if self.verbose:
        self.io.tool_output("Starting to summarize chat history.")
    self.summarizer_thread = threading.Thread(target=self.summarize_worker)  # ← 后台线程
    self.summarizer_thread.start()

def summarize_worker(self):
    self.summarizing_messages = list(self.done_messages)
    try:
        self.summarized_done_messages = self.summarizer.summarize(self.summarizing_messages)
    except ValueError as err:
        self.io.tool_warning(err.args[0])
    if self.verbose:
        self.io.tool_output("Finished summarizing chat history.")

def summarize_end(self):
    if self.summarizer_thread is None: return
    self.summarizer_thread.join()
    if self.summarizing_messages == self.done_messages:    # 防止 race
        self.done_messages = self.summarized_done_messages
    self.summarizing_messages = None
    self.summarized_done_messages = []
```

**摘要算法**(`history.py:33-95` `summarize_real`):
1. `tokenize(messages)` 给每条 message 算 token
2. **head/tail split**:从后往前累加 token,凑到 `max_tokens // 2` → 找到 split_index
3. **head 部分**:`summarize_all(keep)` —— LLM 调一次把所有 head 压成一段总结(`history.py:98-111`)
4. **summary + tail** 若仍超 `max_tokens` → 递归 `summarize_real(summary + tail, depth + 1)`,depth 上限 3
5. `summarize_all` 失败抛 `ValueError`,`base_coder.py:1019-1021` catch 后只 warning,**不 raise**

**关键设计**:
- **后台线程,不等**:`summarize_start` 直接 `start()`,不等完成;`summarize_end` 在下次 `move_back_cur_messages` 才 join → 用户无感
- **race 防护**:`summarizing_messages == self.done_messages` 才覆盖,防止"摘要过程中新消息已 append"导致覆盖新消息
- **小窗口不摘要**:`too_big` False 时 `summarize_start` 立即 return
- **可换模型**:`ChatSummary(models=[weak_model, main_model])` —— 优先用 weak_model 节省成本
- **失败不阻断**:`ValueError` 只 warning,继续跑

#### 8.3 L3 append-only 缺陷(与 file_backend.md 呼应)

**代码**(`io.py:1117-1137`):
```python
def append_chat_history(self, text, linebreak=False, blockquote=False, strip=True):
    if blockquote:
        if strip: text = text.strip()
        text = "> " + text
    if linebreak:
        if strip: text = text.rstrip()
        text = text + "  \n"
    if not text.endswith("\n"):
        text += "\n"
    if self.chat_history_file is not None:
        try:
            self.chat_history_file.parent.mkdir(parents=True, exist_ok=True)
            with self.chat_history_file.open("a", encoding=self.encoding, errors="ignore") as f:
                f.write(text)                          # ← 永远 append
        except (PermissionError, OSError) as err:
            print(f"Warning: Unable to write to chat history file {self.chat_history_file}.")
            print(err)
            self.chat_history_file = None              # 静默关闭后续写入
```

**为什么是缺陷**:
- ❌ **L2 摘要只改内存不写回**:`done_messages` 摘要后 `.aider.chat.history.md` 仍是原文 → 下次启动 Aider 不读该文件(用 `done_messages` 内存)
- ❌ **chat_history_file 是"次要可视化"**:用于用户在 IDE / terminal 里 cat 看历史,**不参与 LLM 调用**
- ❌ **崩溃时无持久化**:Aider 退出后 `done_messages` 丢光,只剩 `.aider.chat.history.md`(内容完整但 LLM 不会读)
- ❌ **写失败静默**:`PermissionError` / `OSError` 时只 `print` warning,`self.chat_history_file = None`,用户**不知道** chat history 关闭了

**实际使用场景**:
- 多数用户 `cat .aider.chat.history.md` 回看历史(纯 markdown,人读)
- 或者 `tail -f .aider.chat.history.md` 跟看 LLM 输出
- **不参与 LLM 上下文**(对比 LangChain `ConversationBufferMemory` 那种回放)

#### 8.4 L1 token check + ContextWindowExceeded 处理

**主动检查**(`base_coder.py:1396-1418` `check_tokens`):
```python
def check_tokens(self, messages):
    input_tokens = self.main_model.token_count(messages)
    max_input_tokens = self.main_model.info.get("max_input_tokens") or 0

    if max_input_tokens and input_tokens >= max_input_tokens:
        self.io.tool_error(f"Your estimated chat context of {input_tokens:,} tokens exceeds the ...")
        self.io.tool_output("- Use /drop to remove unneeded files from the chat")
        self.io.tool_output("- Use /clear to clear the chat history")
        if not self.io.confirm_ask("Try to proceed anyway?"):
            return False                              # ← 用户拒绝 → 中断
    return True
```

**被动 catch**(`base_coder.py:1466-1505` `send_message` 的重试循环):
```python
while True:
    try:
        yield from self.send(messages, functions=self.functions)
        break
    except litellm_ex.exceptions_tuple() as err:
        ex_info = litellm_ex.get_ex_info(err)
        if ex_info.name == "ContextWindowExceededError":
            exhausted = True                          # ← 触发 show_exhausted_error
            break
        ...
```

**`show_exhausted_error`**(`base_coder.py:1629-1680`):打印 token 报告 + 建议(`/drop` / `/clear` / 拆小文件)

**后续处理**(`base_coder.py:1535-1543`):
```python
if exhausted:
    if self.cur_messages and self.cur_messages[-1]["role"] == "user":
        self.cur_messages += [dict(role="assistant", content="FinishReasonLength exception: you sent too many tokens")]
    self.show_exhausted_error()
    self.num_exhausted_context_windows += 1
    return                                              # ← 静默 return,等用户 /clear 或 /drop
```

**关键观察**:
- ❌ **没有自动触发 ChatSummary 摘要**:`send_message` catch `ContextWindowExceededError` 后**不调 `summarize_start`**,只让用户手动 `/clear` 或 `/drop`
- ❌ **没有"重试一次"**:exhausted 直接 return,用户必须主动干预
- ✅ **累计计数**:`num_exhausted_context_windows` 记录,用户可用 `/tokens` 看到压力

#### 8.5 其他上下文管理

- **`/tokens` 命令**(`commands.py:445-551`):打印 system / chat history / repo map / per-file 的 token 估算,提示哪里能省
- **`/drop <file>`**(`commands.py:912-965`):把文件从 `abs_fnames` 移走 → 下次 LLM 调用 prompt 不带它
- **`/clear`**:清 done + cur messages
- **`/reset`**:清文件 + 清 messages
- **provider 适配**:`sendchat.py:43-77` `ensure_alternating_roles` 在 DeepSeek R1 等"严格 user/assistant 交替"模型上插入空消息
- **prompt cache 预热**(`base_coder.py:1340-1395` `warm_cache`):后台线程定时 ping LLM 保持 prompt cache 不过期(Anthropic / OpenAI 部分模型支持)

---

### Q9. 其他亮点

#### 9.1 git 自动 commit 深度集成

- **每次成功 edit = 一次 commit**:commit message 由 LLM 生成(可配 `--commit-language`),带 `Co-authored-by: aider` trailer
- **`aider_commit_hashes: set` 跟踪**:只能 `/undo` 自己产生的 commit(防止误 undo 用户自己 commit)
- **commit 前自动 diff 显示**:`auto_commit` 后调 `cmd_diff` 把 diff 打印到 terminal
- **branch 隔离**:`--branch feature/xxx` 把所有 commit 落在该 branch(常用 PR 工作流)
- **commit message 失败兜底**:`get_commit_message` 多个 model 顺序尝试,都失败 `tool_error("Failed to generate commit message!")`
- **dirty 文件处理**:`--dirty-commits` / `--no-dirty-commits` 控制是否把会话外的修改一并提交

#### 9.2 兼容多 provider(32+)

- **统一入口**:`litellm.completion()`(`models.py:1035`),OpenAI / Anthropic / DeepSeek / OpenRouter / Ollama / Bedrock / Vertex / Azure / GitHub Copilot / 国产 30+ provider 全部走同一条路径
- **provider 特定**:`is_deepseek_r1()` 强制 `ensure_alternating_roles`、`is_ollama()` 自动加 `num_ctx`、GitHub Copilot 加 `Editor-Version` header
- **模型元数据**:`aider/resources/model-metadata.json`(29057 字节) + 用户/项目级 `.aider.model.metadata.json` 覆盖
- **OAuth 0 摩擦**:`~/.aider/oauth-keys.env` 自动写入 OpenRouter key
- **model 列表**:`/models <query>` 模糊搜索支持的模型

#### 9.3 Repo Map 设计(graph ranking + token-aware tree)

- **核心算法**:tree-sitter 抽 tags → PageRank 排序(基于"被 chat 内文件引用"图) → 二分搜索最优 N → 渲染 tree 字符串
- **三级 fallback**(`base_coder.py:735-746`):先按 mentioned_fnames/idents 排序 → 不行就 unhinted 整个 repo → 还不行就完全 unhinted
- **视野自适应**(`repomap.py:124-132`):没有 chat files 时 `max_map_tokens *= map_mul_no_files`(默认 8)→ 一次性给 LLM 看几乎整个仓库
- **mtime 缓存**:`.aider.tags.cache.v3/` SQLite,按 mtime 失效,自动重建
- **batch tree 缓存**:`tree_cache: dict` / `map_cache: dict`(`repomap.py:78-82`)避免重复计算
- **可关闭**:`--map-tokens 0` 完全关掉,节省 token

#### 9.4 极受独立开发者欢迎(数据)

- **GitHub 47k+ ⭐**(2026 调研时),仅次于少数几个 50k+ 项目
- **生产维护频率高**:CHANGELOG 月级发版,功能迭代快
- **CLI-first**:无需 IDE 插件、无需 GUI,直接 `pip install aider-chat` 就能用
- **"我能让 LLM 改我自己仓库"是杀手锏**:Aider 把"LLM + 真实代码仓库"绑得最紧密,独立开发者天然喜欢

#### 9.5 99% prompt-as-tool 的"反例"价值

**为什么 Aider 这么设计**:

1. **兼容所有 LLM**:很多老模型 / 本地模型(7B/13B)/ Ollama 不支持 OpenAI `tools`;prompt-as-tool 任何 LLM 都能用
2. **流式友好**:`partial_response_content` 逐 token 累加,无需等完整 function call JSON(后者要等 `delta.tool_calls` 完整)
3. **简单**:`SEARCH/REPLACE` 块 = 三个 sentinel,正则好写;function call JSON = 要 `parse_partial_args` 4 级修复(`base_coder.py:2347-2360`)
4. **"LLM 看得懂"**:用户能直接 cat LLM 输出看为什么失败,不用解码 function call 结构
5. **debug 容易**:LLM 提错 SEARCH → 错误信息直接拼回 prompt → 下轮自动 retry,用户可见

**代价**:

1. ❌ **无结构化 result**:`role=tool` 协议缺失,工具结果都是字符串拼接
2. ❌ **无并发工具调用**:LLM 一次输出多 SEARCH/REPLACE 块顺序应用,不能并行
3. ❌ **解析脆弱**:SEARCH/REPLACE 块语法错误 → `num_malformed_responses++` 触发 reflection,可能死循环
4. ❌ **MCP / Skills 完全不兼容**:无任何"tool list"机制,无法加新工具
5. ❌ **shell 命令无 sandbox**:用户 confirm 后直接 `run_cmd` 子进程,无白名单 / 黑名单

#### 9.6 其他细节

- **prompt cache 预热**(`base_coder.py:1340-1395`):后台线程定时 ping Anthropic / OpenAI,保持 cache 5 分钟不过期
- **reasoning tag 处理**(`reasoning_tags.py`):DeepSeek R1 / o1 等"思考链"模型自动剥离 `<think>...</think>` 标签
- **deepseek 角色交替**(`sendchat.py:43-77`):`ensure_alternating_roles` 在 strict-alternation 模型上插入空消息
- **voice input**(`aider/voice.py` + `commands.py:1252-1276` `cmd_voice`):按住录音 → whisper 转写 → 塞进 input(需 `OPENAI_API_KEY`)
- **multiline mode**(`commands.py:1524-1526`):Alt-Enter 提交,Enter 换行
- **copy-paste mode**(`aider/copypaste.py` + `main.py:1043-1047`):监听剪贴板,自动 add 剪贴板里的 diff
- **file watch**(`aider/watch.py` + `--watch-files`):后台监听文件变化,弹窗"Add changes?"
- **GUI mode**(`aider/gui.py` + `--gui`):Streamlit 套壳,浏览器里跑
- **model context caching**:`add_cache_headers=True` 时给 Anthropic / OpenAI 关键 message 段加 `cache_control` 标记
- **token / cost 实时统计**:`/tokens` 命令 + 每次 send 后 `show_usage_report`(输入/输出 token + 累计 cost)
- **multilingual commit msg**:`--commit-language zh-CN` 让 commit message 用中文(`repo.py:333-336` 注入 prompt)
- **slash 命令补全**(`commands.py:255-296`):`get_completions` / `get_raw_completions` 提供 prompt_toolkit 自动补全

---

## 3. 关键代码片段

### 3.1 `main.py:1159-1180` —— 外层主循环 + SwitchCoder 异常处理

```python
while True:
    try:
        coder.ok_to_warm_cache = bool(args.cache_keepalive_pings)
        coder.run()
        analytics.event("exit", reason="Completed main CLI coder.run")
        return
    except SwitchCoder as switch:
        coder.ok_to_warm_cache = False

        if hasattr(switch, "placeholder") and switch.placeholder is not None:
            io.placeholder = switch.placeholder

        kwargs = dict(io=io, from_coder=coder)
        kwargs.update(switch.kwargs)
        if "show_announcements" in kwargs:
            del kwargs["show_announcements"]

        coder = Coder.create(**kwargs)               # ← 重建,继承 done/cur/fnames/cost

        if switch.kwargs.get("show_announcements") is not False:
            coder.show_announcements()
```

**说明**:`SwitchCoder` 不是"退出",是"换模式"。`Coder.create(from_coder=coder, **kwargs)` 走 `base_coder.py:108-180`,`from_coder` 路径会用 `dict(from_coder.original_kwargs) + update(fnames, read_only_fnames, done_messages, cur_messages, aider_commit_hashes, commands, total_cost, ...)` 继承所有状态。

### 3.2 `base_coder.py:876-905` —— Coder.run() 内层 REPL

```python
def run(self, with_message=None, preproc=True):
    try:
        if with_message:
            self.io.user_input(with_message)
            self.run_one(with_message, preproc)
            return self.partial_response_content
        while True:                                    # ← 真·内层循环
            try:
                if not self.io.placeholder:
                    self.copy_context()
                user_message = self.get_input()       # ← io.get_input REPL
                self.run_one(user_message, preproc)   # ← 跑一轮 + 反射
                self.show_undo_hint()
            except KeyboardInterrupt:
                self.keyboard_interrupt()              # ← 第一次提示"再按一次"
    except EOFError:                                  # ← Ctrl-D 优雅退出
        return
```

### 3.3 `base_coder.py:917-940` —— run_one() reflection 循环

```python
def run_one(self, user_message, preproc):
    self.init_before_message()

    if preproc:
        message = self.preproc_user_input(user_message)
    else:
        message = user_message

    while message:                                    # ← reflection 内循环
        self.reflected_message = None
        list(self.send_message(message))

        if not self.reflected_message:                # ← 没人触发 reflection → 退出
            break

        if self.num_reflections >= self.max_reflections:
            self.io.tool_warning(f"Only {self.max_reflections} reflections allowed, stopping.")
            return

        self.num_reflections += 1
        message = self.reflected_message              # ← 用反思内容重发 LLM
```

**`reflected_message` 触发点**:
- `apply_updates` 解析失败:`base_coder.py:2304-2306`
- `check_for_file_mentions` 加了新文件:`base_coder.py:1547-1553`
- `auto_lint` 有错误且用户 confirm 修复:`base_coder.py:1608-1613`
- `auto_test` 有错误且用户 confirm 修复:`base_coder.py:1618-1624`
- `ContextCoder.reply_completed`:`context_coder.py:32-35`

### 3.4 `base_coder.py:1407-1626` —— send_message 核心(message→LLM→edits→commit)

```python
def send_message(self, inp):
    self.event("message_send_starting")
    self.io.llm_started()
    self.cur_messages += [dict(role="user", content=inp)]

    chunks = self.format_messages()                   # ← 拼 8 段消息
    messages = chunks.all_messages()
    if not self.check_tokens(messages):               # ← 超限弹窗
        return
    self.warm_cache(chunks)                            # ← 后台 ping 保 cache

    self.multi_response_content = ""
    if self.show_pretty():
        self.waiting_spinner = WaitingSpinner("Waiting for " + self.main_model.name)
        self.waiting_spinner.start()
        ...

    retry_delay = 0.125
    litellm_ex = LiteLLMExceptions()
    self.usage_report = None
    exhausted = False
    interrupted = False
    try:
        while True:                                    # ← 重试循环
            try:
                yield from self.send(messages, functions=self.functions)
                break
            except litellm_ex.exceptions_tuple() as err:
                ex_info = litellm_ex.get_ex_info(err)
                if ex_info.name == "ContextWindowExceededError":
                    exhausted = True
                    break
                should_retry = ex_info.retry
                if should_retry:
                    retry_delay *= 2
                    if retry_delay > RETRY_TIMEOUT:
                        should_retry = False
                if not should_retry:
                    self.mdstream = None
                    self.check_and_open_urls(err, ex_info.description)
                    break
                ...
                self.io.tool_output(f"Retrying in {retry_delay:.1f} seconds...")
                time.sleep(retry_delay)
                continue
            except KeyboardInterrupt:
                interrupted = True
                break
            except FinishReasonLength:
                if not self.main_model.info.get("supports_assistant_prefill"):
                    exhausted = True
                    break
                self.multi_response_content = self.get_multi_response_content_in_progress()
                if messages[-1]["role"] == "assistant":
                    messages[-1]["content"] = self.multi_response_content
                else:
                    messages.append(dict(role="assistant", content=self.multi_response_content, prefix=True))
            except Exception as err:
                ...
                return
    finally:
        if self.mdstream:
            self.live_incremental_response(True)
            self.mdstream = None
        self._stop_waiting_spinner()
        self.partial_response_content = self.get_multi_response_content_in_progress(True)
        ...

    self.add_assistant_reply_to_cur_messages()

    if exhausted:
        ...
        return

    # ... (解析 partial_response_content / function_call)

    if not interrupted:
        add_rel_files_message = self.check_for_file_mentions(content)  # ← 触发 reflection
        if add_rel_files_message:
            if self.reflected_message:
                self.reflected_message += "\n\n" + add_rel_files_message
            else:
                self.reflected_message = add_rel_files_message
            return

        try:
            if self.reply_completed():                 # ← ContextCoder / ArchitectCoder / AskCoder 钩子
                return
        except KeyboardInterrupt:
            interrupted = True

    if interrupted:
        ...

    edited = self.apply_updates()                      # ← 解析 SEARCH/REPLACE → 写文件
    if edited:
        self.aider_edited_files.update(edited)
        saved_message = self.auto_commit(edited)       # ← git commit
        if not saved_message and hasattr(self.gpt_prompts, "files_content_gpt_edits_no_repo"):
            saved_message = self.gpt_prompts.files_content_gpt_edits_no_repo
        self.move_back_cur_messages(saved_message)     # ← cur → done + 触发 summarize

    if self.reflected_message:
        return

    if edited and self.auto_lint:
        lint_errors = self.lint_edited(edited)
        self.auto_commit(edited, context="Ran the linter")
        if lint_errors:
            ok = self.io.confirm_ask("Attempt to fix lint errors?")
            if ok:
                self.reflected_message = lint_errors
                return

    shared_output = self.run_shell_commands()         # ← 跑 LLM 提的 shell 命令
    if shared_output:
        self.cur_messages += [
            dict(role="user", content=shared_output),
            dict(role="assistant", content="Ok"),
        ]

    if edited and self.auto_test:
        ...
```

### 3.5 `architect_coder.py:35-57` —— Architect 子代理

```python
def reply_completed(self):
    content = self.partial_response_content
    if not content or not content.strip(): return

    if not self.auto_accept_architect and not self.io.confirm_ask("Edit the files?"):
        return

    kwargs = dict()
    editor_model = self.main_model.editor_model or self.main_model

    kwargs["main_model"] = editor_model
    kwargs["edit_format"] = self.main_model.editor_edit_format
    kwargs["suggest_shell_commands"] = False
    kwargs["map_tokens"] = 0
    kwargs["total_cost"] = self.total_cost
    kwargs["cache_prompts"] = False
    kwargs["num_cache_warming_pings"] = 0
    kwargs["summarize_from_coder"] = False

    new_kwargs = dict(io=self.io, from_coder=self)   # ← from_coder 继承
    new_kwargs.update(kwargs)

    editor_coder = Coder.create(**new_kwargs)
    editor_coder.cur_messages = []                   # ← 清空 cur
    editor_coder.done_messages = []

    if self.verbose:
        editor_coder.show_announcements()

    editor_coder.run(with_message=content, preproc=False)  # ← 递归调用!

    self.move_back_cur_messages("I made those changes to the files.")
    self.total_cost = editor_coder.total_cost
    self.aider_commit_hashes = editor_coder.aider_commit_hashes
```

### 3.6 `base_coder.py:1036-1052` —— move_back_cur_messages(cur→done+触发摘要)

```python
def move_back_cur_messages(self, message):
    self.done_messages += self.cur_messages           # ← cur 拼到 done
    self.summarize_start()                            # ← 后台摘要

    if message:
        self.done_messages += [
            dict(role="user", content=message),       # ← 拼 commit 结果
            dict(role="assistant", content="Ok."),
        ]
    self.cur_messages = []
```

### 3.7 `history.py:33-95` —— ChatSummary 摘要算法

```python
def summarize_real(self, messages, depth=0):
    if not self.models:
        raise ValueError("No models available for summarization")

    sized = self.tokenize(messages)
    total = sum(tokens for tokens, _msg in sized)
    if total <= self.max_tokens and depth == 0:
        return messages

    min_split = 4
    if len(messages) <= min_split or depth > 3:
        return self.summarize_all(messages)           # ← 太短或太深 → 全压

    # 从后往前凑 tail = max_tokens // 2
    tail_tokens = 0
    split_index = len(messages)
    half_max_tokens = self.max_tokens // 2
    for i in range(len(sized) - 1, -1, -1):
        tokens, _msg = sized[i]
        if tail_tokens + tokens < half_max_tokens:
            tail_tokens += tokens
            split_index = i
        else:
            break

    # 确保 head 结尾是 assistant
    while messages[split_index - 1]["role"] != "assistant" and split_index > 1:
        split_index -= 1

    if split_index <= min_split:
        return self.summarize_all(messages)

    tail = messages[split_index:]

    # head 部分不能超过模型 max_input_tokens
    sized_head = sized[:split_index]
    model_max_input_tokens = self.models[0].info.get("max_input_tokens") or 4096
    model_max_input_tokens -= 512  # reserve buffer
    keep = []
    total = 0
    for tokens, msg in sized_head:
        total += tokens
        if total > model_max_input_tokens:
            break
        keep.append(msg)

    summary = self.summarize_all(keep)                # ← LLM 压 head

    summary_tokens = self.token_count(summary)
    tail_tokens = sum(tokens for tokens, _ in sized[split_index:])
    if summary_tokens + tail_tokens < self.max_tokens:
        return summary + tail                         # ← summary + tail 拼回去

    return self.summarize_real(summary + tail, depth + 1)  # ← 还超 → 递归
```

### 3.8 `io.py:1117-1137` —— chat history append-only(缺陷)

```python
def append_chat_history(self, text, linebreak=False, blockquote=False, strip=True):
    if blockquote:
        if strip: text = text.strip()
        text = "> " + text
    if linebreak:
        if strip: text = text.rstrip()
        text = text + "  \n"
    if not text.endswith("\n"):
        text += "\n"
    if self.chat_history_file is not None:
        try:
            self.chat_history_file.parent.mkdir(parents=True, exist_ok=True)
            with self.chat_history_file.open("a", encoding=self.encoding, errors="ignore") as f:
                f.write(text)                         # ← 永远 append,永不裁剪
        except (PermissionError, OSError) as err:
            print(f"Warning: Unable to write to chat history file {self.chat_history_file}.")
            print(err)
            self.chat_history_file = None             # ← 静默关闭
```

### 3.9 `base_coder.py:1396-1418` —— check_tokens 主动检查

```python
def check_tokens(self, messages):
    """Check if the messages will fit within the model's token limits."""
    input_tokens = self.main_model.token_count(messages)
    max_input_tokens = self.main_model.info.get("max_input_tokens") or 0

    if max_input_tokens and input_tokens >= max_input_tokens:
        self.io.tool_error(
            f"Your estimated chat context of {input_tokens:,} tokens exceeds the"
            f" {max_input_tokens:,} token limit for {self.main_model.name}!"
        )
        self.io.tool_output("To reduce the chat context:")
        self.io.tool_output("- Use /drop to remove unneeded files from the chat")
        self.io.tool_output("- Use /clear to clear the chat history")
        self.io.tool_output("- Break your code into smaller files")
        self.io.tool_output(
            "It's probably safe to try and send the request, most providers won't charge if"
            " the context limit is exceeded."
        )
        if not self.io.confirm_ask("Try to proceed anyway?"):
            return False                              # ← 用户拒绝 → 中断
    return True
```

### 3.10 `base_coder.py:2296-2335` —— apply_updates(解析→dry-run→写文件)

```python
def apply_updates(self):
    edited = set()
    try:
        edits = self.get_edits()                       # ← EditBlock/WholeFile/... 解析
        edits = self.apply_edits_dry_run(edits)        # ← dry-run 校验
        edits = self.prepare_to_edit(edits)
        edited = set(edit[0] for edit in edits)
        self.apply_edits(edits)                        # ← 写文件
    except ValueError as err:
        self.num_malformed_responses += 1
        err = err.args[0]
        self.io.tool_error("The LLM did not conform to the edit format.")
        self.io.tool_output(urls.edit_errors)
        self.io.tool_output()
        self.io.tool_output(str(err))
        self.reflected_message = str(err)              # ← 触发 reflection
        return edited
    except ANY_GIT_ERROR as err:
        self.io.tool_error(str(err))
        return edited
    except Exception as err:
        self.io.tool_error("Exception while updating files:")
        self.io.tool_error(str(err), strip=False)
        traceback.print_exc()
        self.reflected_message = str(err)
        return edited

    for path in edited:
        if self.dry_run:
            self.io.tool_output(f"Did not apply edit to {path} (--dry-run)")
        else:
            self.io.tool_output(f"Applied edit to {path}")

    return edited
```

---

## 4. 与 Onion Agent 设计的关联

> Onion Agent = "围绕 `session.json` 自动累加的 Agent Loop"。本节对照 Aider,提炼可借鉴 / 需规避的设计决策。

### 4.1 ✅ 值得借鉴

| 借鉴点 | Aider 的做法 | 在 Onion Agent 中的映射 |
|---|---|---|
| **双层 while 循环 + `reflected_message` 自反思** | `Coder.run()` 外层 REPL + `run_one()` 内层 reflection 循环,失败时 `self.reflected_message = err` 触发下一轮 | Onion Agent 可以用同款结构,reflection 触发可挂"工具解析失败" / "用户拒绝" / "lint 错误" 等 |
| **异常切换模式(SwitchCoder)** | `class SwitchCoder(Exception)` 装 kwargs → main 捕获 → `Coder.create(from_coder=old, **kwargs)` 继承 8+ 字段重建 | Onion Agent 可以定义 `SwitchMode` 异常,实现"主 agent / 计划 agent / 反思 agent"模式切换,继承 done/cur/工具集 |
| **Architect 模式 = 双 Coder 子代理** | 主模型出方案 → 弹窗 → editor 模型执行;`from_coder=self` 继承上下文,`cur_messages=[]` 只传方案 | Onion Agent 应当借鉴"主 LLM 规划 + 强 LLM 执行"分层,主备模型可以不同(provider 可热插拔) |
| **Context 模式 = LLM 找文件 + reflection 自纠** | 用 LLM 一次性识别"要改哪些文件" → 反射修正直到集合稳定或 `max_reflections=3` | Onion Agent 可以做"用 LLM 找工具" / "用 LLM 选子任务",有 reflection 兜底 |
| **异步后台摘要** | `summarize_start` 在 `move_back_cur_messages` 后台线程跑,`summarize_end` 在下次 join,用户无感 | Onion Agent 在 `session.json` 更新前可启动后台摘要,避免"压缩时 LLM 停摆" |
| **commit 即审计** | 每次 LLM 成功 edit = 一次 git commit,带 Co-authored-by trailer,`aider_commit_hashes` 跟踪,`/undo` 只 undo 这些 | Onion Agent 如果有"checkpoint"概念(对比 git commit),可借鉴 hash 跟踪 + selective undo |
| **`/tokens` 实时统计** | system / chat history / repo map / per-file token 估算 + cost | Onion Agent `/onion tokens` 同样显示,加上"工具调用"维度 |
| **provider 统一抽象** | `litellm.completion()` 单一入口 + `model-metadata.json` 配元数据 + user override | Onion Agent 应当用 litellm / Vercel AI SDK 等统一抽象,支持 32+ provider 热切换 |
| **prompt cache 预热** | 后台线程定时 ping LLM 保持 cache,`AIDER_CACHE_KEEPALIVE_DELAY` 可配 | Onion Agent 同款,Anthropic / OpenAI / DeepSeek 都有 cache 机制 |
| **multilingual commit msg** | `--commit-language zh-CN` 注入 prompt | Onion Agent 多语言 prompt 注入 |
| **pathspec .aiderignore** | 复用 `pathspec.GitWildMatchPattern`,支持 `.gitignore` 语法 | Onion Agent 同款 |
| **model-metadata.json 多级覆盖** | `aider/resources/model-metadata.json`(包内置) → `~/.aider/caches/...` → 项目级 `.aider.model.metadata.json` → CLI/Env | Onion Agent `ONION.md` / `~/.onion/model-metadata.json` / `<repo>/.onion/model-metadata.json` 三级 |

### 4.2 ⚠️ 需要规避的坑

| 问题 | Aider 的具体表现 | Onion Agent 的应对 |
|---|---|---|
| **99% prompt-as-tool,无结构化 result** | tool result 是字符串拼接,无 OpenAI `role=tool` 协议,LLM 兼容性"广但不深" | Onion Agent **必须做**协议中立,统一 `BaseTool` 抽象 + OpenAI `tools=` 协议 + 多 provider 适配 |
| **append-only chat history 不写回** | `io.py:1131` 永远 `mode="a"`,`ChatSummary.too_big` 触发的压缩**只改 `done_messages` 内存,从不回写文件**;`PermissionError` 时静默 `self.chat_history_file = None` | Onion Agent `session.json` 应当**主动维护** `summary_checkpoint` 指针,压缩结果写回;失败必须 raise,不能静默 disable |
| **失败 `self.io.tool_warning` 不 raise** | `summarize_worker` 失败时只 warning,继续跑 → 用户不知道摘要失败 | Onion Agent 在 `session.json` 写入失败 / 摘要失败 / 工具调用失败时**必须显式** `tool_error` + 提示用户 |
| **没有自动重试压缩** | `ContextWindowExceededError` 后 `send_message` 只 `exhausted = True; return`,**不调 `summarize_start`**,等用户 `/clear` 或 `/drop` | Onion Agent 应当在 `ContextWindowExceeded` 后**自动**触发 `session.json` 压缩 + retry |
| **没有"per-tool 权限矩阵"** | 只有 `confirm_ask` 弹窗 + 全开/全关开关(`--no-auto-commits` / `--no-suggest-shell-commands` 等),无细粒度 | Onion Agent 应当做"per-tool allow/deny/ask"白名单 + 持久化(写到 `session.json` 顶层 `permissions`) |
| **Architect 模式无沙箱** | `editor_coder.run()` 跑的是普通 Coder,无 sandbox,editor 可改任意 `abs_fnames` | Onion Agent Architect 子 agent **必须 sandbox**(Docker / seccomp / 限制路径),或者用最小权限 agent 模板 |
| **shell 命令无白名单** | `confirm_ask(explicit_yes_required=True)` 弹窗,用户 yes 就 `subprocess.run(command)`,无命令白名单 / 路径限制 | Onion Agent shell 工具必须做"path 限制 + command 模板"(`shell_cmd_allowlist.json`),避免 `rm -rf /` 风险 |
| **`--attribute-*` 默认 co-authored-by** | Aider 默认 commit 加 `Co-authored-by: aider` trailer,合规场景可能不希望 | Onion Agent 可借鉴"可配置 attribution"模式,默认不写 |
| **多项目并发启动无 isolation** | 同一台机器两个 Aider 跑同一 git 仓库会竞争 `diskcache.Cache`(SQLite 锁) + chat history `mode="a"` 写交错 | Onion Agent 应当有 PID file lock,`session.json` 加 `<pid>.lock` 防并发 |
| **`setup_git` 误 git init 风险** | 在 home 目录运行 Aider 会警告,但其他 cwd 无 git 会自动 `git init`(某些 CI 场景不希望) | Onion Agent **不要**自动 `git init`,明确要求"在已 git 化的目录里运行",或用独立项目级目录(`.onion/`) |
| **`cache_version` 硬编码不迁移** | `TAGS_CACHE_DIR = ".aider.tags.cache.v3"`,v3→v4 时**不迁移老缓存** | Onion Agent schema 升级要有显式 migration 路径(读老 → 转 → 写新) |
| **Docker `HOME=/app` 混淆全局/项目级** | `~/.aider/caches` 和 `.aider*` 在容器里都落 `/app` | Onion Agent 容器化时**显式分开**挂载 `~/.onion/`(控制平面)与 `<repo>/.onion/`(项目级) |
| **没有"会话文件"概念,崩溃无状态** | 5+ 文件散落(`.aider.chat.history.md` / `.aider.input.history` / `.aider.llm.history` / `.aider.model.settings.yml` / `.aiderignore` / `.aider.tags.cache.v3/`),**崩溃无原子快照** | Onion Agent `session.json` 单一真相源,易于备份/恢复/迁移 |
| **tool_channel.md 已记录反例:OAuth key 权限未 0o600** | `~/.aider/oauth-keys.env` 文件权限未声明 0o600 | Onion Agent `~/.onion/secrets/auth.json` **必须 chmod 0o600** |
| **mode="a" 写 chat history 多进程交错** | 两个 aider 跑同一仓库 → `mode="a"` 无锁,可能行交错 | Onion Agent `session.json` 写必须 lock + 完整行(atomic write) |

### 4.3 关键启发

1. **"git 仓库即状态机"是 Aider 的灵魂**:Onion Agent 不需要绑死 git,但可以借鉴"commit hash = 上下文边界"的思维方式,把 `session.json` 顶端维护 `commit_id` / `summary_checkpoint` / `version` 三个指针
2. **"异常即控制流" = SwitchCoder 模式**:用 `class ModeSwitch(Exception)` 装新模式 kwargs,主循环捕获后重建 agent,继承 done/cur/cost/fnames 8+ 字段。这是比"对象池"更轻量的多模式实现
3. **Architect / Context / Ask 是 3 个"模式化"的 Coder**:Onion Agent 可以做 3 个"模式化" agent:Planner(只规划不改) / Executor(只改不规划) / Reflector(只反思不执行),用 SwitchMode 异常切换
4. **"reflection 软循环" 优于 "硬 max_iterations"**:Aider `max_reflections=3` 兜底,平时靠 `reflected_message` 自由重试;对比 SuperAGI 硬 `max_iterations=50` 更符合"自然对话"直觉
5. **99% prompt-as-tool 是个**反例警示**:`SEARCH/REPLACE` 块虽然简单,但**没有 MCP / Skills / 结构化 result**;Onion Agent 应当做 OpenAI `tools=` 协议 + BaseTool 抽象,**兼容** prompt-as-tool 但不依赖它
6. **append-only + 异步摘要 是 47k ⭐ 项目的"次要"设计**:`.aider.chat.history.md` 是给用户看的 markdown,**不参与 LLM**;Onion Agent `session.json` 必须**参与 LLM** + 主动维护 + 失败 raise
7. **"git commit 即 audit trail" 是 Aider 的核心 UX**:`/undo` 只 undo 自己 commit,git log 自动审计;Onion Agent 应当有"操作历史"概念,所有用户/LLM/工具行为记录,可 selective undo

---

## 5. 不确定 / 未找到

| 编号 | 项 | 说明 |
|---|---|---|
| U-1 | `/aider` 命令是否存在 | 全局搜 `cmd_aider` / "aider" 在 commands.py 找不到,Aider 没有 `cmd_aider`。可能社区 PR 提供,本次未追溯。 |
| U-2 | `ContextWindowExceeded` 后的自动压缩路径 | `send_message` catch 后只 `exhausted = True; return`,**不调 `summarize_start`**;但 Aider 历史上是否曾有自动触发未确认(`base_coder.py:1466-1505` 现状明确不自动) |
| U-3 | `num_exhausted_context_windows` 的实际使用 | 字段在 `base_coder.py:96` 定义,`base_coder.py:1542` 累加,`base_coder.py:1543` 后**无任何代码读它**;只是埋点,不会主动触发任何动作 |
| U-4 | Architect 模式 `auto_accept_architect = False` 是否可配 | `architect_coder.py:15` 类属性硬编码,可能 `--auto-accept-architect` CLI 标志覆盖但本次未找到 |
| U-5 | `warm_cache` 对非 Anthropic / OpenAI 模型的实际效果 | `base_coder.py:1340-1395` 走 `litellm.completion(max_tokens=1)`,依赖 litellm 把 `cache_control` 头翻译;Ollama / Bedrock 等是否真有 cache 未确认 |
| U-6 | `aider_commit_hashes` 跨会话持久化 | 只在 `Coder` 实例内存,退出后丢;`/undo` 在新 Aider 启动后**不能用**,因为新 Coder 实例的 `aider_commit_hashes` 是空的(`base_coder.py:97` 字段) |
| U-7 | `confirm_ask` 在 Streamlit GUI 模式下的实现 | `gui.py` + `io.py` GUI 路径未深查;理论上 `ConfirmGroup` 在 GUI 下应该是 button 组件,本次未确认 |
| U-8 | multi-response content(`multi_response_content`)的用途 | `base_coder.py:1516-1521` 用于 `FinishReasonLength` 时拼接已生成 content + assistant prefill 续写,但是否所有 provider 都支持 `prefix=True` 未确认 |
| U-9 | `partial_response_function_call` 死代码 | 99% 路径 `functions=None`,`base_coder.py:1900-1920` 累加逻辑**几乎不会跑**;只有 `wholefile_func_coder.py:36 raise RuntimeError` 那条死路径可能触发 |
| U-10 | `check_for_file_mentions` 与 `/add` 的去重逻辑 | `check_for_file_mentions` 通过 `self.ignore_mentions` 跳过被拒的,但 `ignore_mentions` 是否在 `/add` 后重置未确认 |
| U-11 | `num_malformed_responses` 的实际使用 | `base_coder.py:2304` 累加,但后续**无任何代码读它**;只是埋点,不会主动触发任何动作(类似 U-3) |
| U-12 | `process_messages_for_DeepSeek_R1` 等 provider 特化的完整列表 | `models.py:990` `is_deepseek_r1()` 调 `ensure_alternating_roles`;`models.py:1014` `is_ollama()` 加 `num_ctx`;其他 provider 是否有特化未深查 |
| U-13 | `History.arch` 在 `move_back_cur_messages` 后的实际大小 | 用户跑 100 轮后 `done_messages` 有多少条?是否自动摘要足够?实际数据未观测,本次只看代码不跑 Aider |
| U-14 | Coder 套 Coder 的栈深上限 | `ArchitectCoder.reply_completed` 调 `editor_coder.run()`,如果 `editor_coder.edit_format` 也是 `architect`(配置错误),会无限套娃?`base_coder.py:108-180` 没看到栈深保护 |
| U-15 | `setup_git` 在 docker 容器里的行为 | 容器内 `HOME=/app` 挂项目根,`get_git_root()` 会找到 `/app/.git`;但 `mkdir(parents=True, exist_ok=True)` 权限可能不够,失败时行为未深查 |
