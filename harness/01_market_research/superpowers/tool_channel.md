# obra/superpowers — 工具调用（Tool Channel）调研报告

> ⚠️ **关键前提**：superpowers **不是 agent 本身**，它是**寄生在宿主 agent 里的 Skills 框架/方法论插件**（README.md:1-2 "a complete software development methodology for your coding agents"）。所以"工具调用"调研必须**严格区分两层**：
> - **superpowers 自己实现的部分**：bootstrap 注入、技能注册、sub-agent 调度脚本
> - **由宿主 agent 提供的部分**：内置工具集、function calling 协议、JSON 流式解析、role=tool 回传

---

## 0. 智能体一句话定位

**superpowers** = "给 coding agent 用的 SDLC 方法论 + 可组合 Skills 库"，装进 Claude Code / Codex / Cursor / OpenCode / Pi / Kimi / Antigravity / Copilot CLI / Factory Droid 等 9 个宿主 agent，强制在写代码前先 brainstorming / 出 plan / TDD / 两阶段 review。

---

## 1. 调研依据

### 源码路径
`C:\workspace\github\onionagent\harness\01_market_research\clone\superpowers\`

### 关键文件
1. `hooks/session-start:1-65` — 单一 bootstrap 入口（Shape A），向宿主注入 `using-superpowers` 全文
2. `hooks/hooks.json` / `hooks/hooks-cursor.json` / `hooks/run-hook.cmd` — Shape A 宿主（Claude Code / Cursor / Copilot CLI）的 hook manifest 与 Windows polyglot 包装
3. `.opencode/plugins/superpowers.js:1-119` — Shape B 宿主（OpenCode）的 in-process JS 插件，含 `config.skills.paths` 自动注册 + `experimental.chat.messages.transform` bootstrap 注入
4. `.pi/extensions/superpowers.ts:1-130` — Shape B 宿主（Pi）的 in-process TS 扩展，监听 `session_start` / `session_compact` / `agent_end` / `context` 4 个事件
5. `gemini-extension.json` + `GEMINI.md` — Shape C 宿主（Gemini），靠 `contextFileName` + `@`-include 实现零代码注入
6. `.claude-plugin/plugin.json` / `.codex-plugin/plugin.json` / `.cursor-plugin/plugin.json` / `.kimi-plugin/plugin.json` — 4 个 harness 的 manifest，都通过 `"skills": "./skills/"` 声明技能目录
7. `skills/using-superpowers/SKILL.md:1-50` — 注入到模型的"必读规则"，强制"先 invoke skill 再做反应"
8. `skills/using-superpowers/references/{codex,pi,antigravity}-tools.md` — 各宿主的 tool-name 翻译表（superpowers 自己**不定义**工具，**只翻译**宿主工具名）
9. `docs/porting-to-a-new-harness.md:1-700` — "如何为新 agent 框架 port" 的 700 行设计指南，明确三大集成 Shape
10. `package.json:9-19` — Pi 包清单，`main` 指向 OpenCode 插件 + `pi.skills: ["./skills"]` + `pi.extensions: ["./.pi/extensions/superpowers.ts"]`

### 文档引用
- `README.md:1-50` — 整体定位与"How it works"
- `README.md:60-180` — 9 个宿主各自的 install 命令
- `docs/porting-to-a-new-harness.md:108-280` — Shape A/B/C 三大集成模式详解

---

## 2. 五个核心问题的回答

### Q1. 工具来源：内置工具 / MCP / Agent Skills

**superpowers 自己**：**0 个内置工具**（这是关键！它**不提供**任何可被模型直接调用的 function）。
**由宿主 agent 提供**（superpowers 通过 tool-name 翻译表借用宿主工具，证据见 `references/*-tools.md`）：

| 工具类别 | superpowers 暴露的方式 | 证据 |
|---|---|---|
| **内置工具**（read / write / edit / bash / grep / glob / webfetch / todowrite / skill / task / subagent） | **全部由宿主 agent 实现**，superpowers 只在 `using-superpowers/SKILL.md` 里告诉模型"调用 Read / Write / Edit / Bash / Grep / Glob / Skill 这些**宿主原生工具**" | `.opencode/plugins/superpowers.js:64-79` 显式列出 OpenCode 工具映射；`.pi/extensions/superpowers.ts:79-92` 列出 Pi 工具映射；`references/codex-tools.md` / `references/pi-tools.md` / `references/antigravity-tools.md` 列出各宿主工具名 |
| **MCP 协议支持** | **不直接支持**。`docs/porting-to-a-new-harness.md:182` 提到 MCP 只是作为新宿主调查的"探索清单"项之一。`skills/writing-skills/anthropic-best-practices.md:1053-1071` 提到"MCP tools should use fully qualified tool names"，但**superpowers 自身不注册任何 MCP server**。MCP 工具的注册完全交给宿主 agent（README.md:200 提到 Copilot/Cursor/Kimi 都通过宿主原生支持 MCP） | `grep -r "MCP" clone/superpowers/` 0 个 manifest 包含 mcp 字段 |
| **Agent Skills 支持** | **核心**。14 个 skill 全部以 `SKILL.md + frontmatter` 形式存放在 `skills/`，由各宿主 manifest 暴露：Claude Code / Cursor / Codex / Kimi 走 `"skills": "./skills/"` 字段（`.codex-plugin/plugin.json:23` / `.kimi-plugin/plugin.json:21` / `.cursor-plugin/plugin.json:21`），OpenCode 走 `config.skills.paths.push(superpowersSkillsDir)`（`.opencode/plugins/superpowers.js:91-95`），Pi 走 `pi.skills: ["./skills"]` + `resources_discover` 事件返回 `skillPaths`（`package.json:19` + `.pi/extensions/superpowers.ts:30-32`） | 14 个 skill 目录：`skills/{brainstorming,test-driven-development,systematic-debugging,writing-plans,subagent-driven-development,dispatching-parallel-agents,requesting-code-review,receiving-code-review,using-git-worktrees,finishing-a-development-branch,writing-skills,executing-plans,verification-before-completion,using-superpowers}` |
| **其他工具类型** | **零**。无 LSP、无 HTTP client、无 Webhook、无 browser。唯一一个非宿主工具是 brainstorming 的 **visual companion**（`skills/brainstorming/scripts/start-server.sh:117-121` 起一个本地 HTTP server 给用户开浏览器预览），但这是给**用户**用的，不是给 LLM 调的 | `start-server.sh:117-121` |

**结论**：superpowers 是**纯 Skills 框架**，工具调用**完全依赖宿主 agent**。MCP 是宿主 agent 提供的，不是 superpowers 提供的。

---

### Q2. 工具列表的生成、传递、格式

**superpowers 自己不生成"OpenAI 协议 tools 列表"**。它生成的是**prompt 上下文**（即 `using-superpowers/SKILL.md` 全文），把"工具应该怎么用"以**自然语言规则**塞进 LLM 的 system message。

#### 生成方式（由 superpowers 自己）

| Shape | 文件 | 输出 |
|---|---|---|
| **Shape A**（Claude Code / Cursor / Copilot CLI） | `hooks/session-start:35-50` | 一个 **JSON 对象**，三选一格式，根据 `${CURSOR_PLUGIN_ROOT}` / `${CLAUDE_PLUGIN_ROOT}` / `${COPILOT_CLI}` 环境变量决定 field 名 |
| **Shape B in-process**（OpenCode） | `.opencode/plugins/superpowers.js:99-119` | **直接 `unshift` 到 `output.messages[0].parts` 数组**，作为 user message 的第一段 |
| **Shape B in-process**（Pi） | `.pi/extensions/superpowers.ts:42-52` | **重新构造 `messages` 数组**，在 compaction summary 之后插入 `role: "user"` 消息 |
| **Shape C**（Gemini） | `GEMINI.md:1-2` | 静态文件，靠 `@./skills/using-superpowers/SKILL.md` 和 `@./...gemini-tools.md` 两条 `@`-include 引用 |

**关键代码片段（Shape A 的 JSON 输出）**：
```bash
# hooks/session-start:35-50
if [ -n "${CURSOR_PLUGIN_ROOT:-}" ]; then
  printf '{\n  "additional_context": "%s"\n}\n' "$session_context" | cat
elif [ -n "${CLAUDE_PLUGIN_ROOT:-}" ] && [ -z "${COPILOT_CLI:-}" ]; then
  printf '{\n  "hookSpecificOutput": {\n    "hookEventName": "SessionStart",\n    "additionalContext": "%s"\n  }\n}\n' "$session_context" | cat
else
  printf '{\n  "additionalContext": "%s"\n}\n' "$session_context" | cat
fi
```

`session_context` 是被 `<EXTREMELY_IMPORTANT>...</EXTREMELY_IMPORTANT>` 标签包起来的 `using-superpowers` 全文 + 工具翻译表（`hooks/session-start:25-32`）。

#### 传递给大模型

- **不是 OpenAI 协议的 `tools` 参数**
- **不是 Anthropic 协议的 `tools` 参数**
- **是 system message / user message / context 字符串** —— **纯 prompt-as-tool 模式**

证据：
- `.opencode/plugins/superpowers.js:88-93`（OpenCode）：`firstUser.parts.unshift({ ...ref, type: 'text', text: bootstrap })` —— 把 bootstrap 文本塞进第一条 user message 的开头
- `.pi/extensions/superpowers.ts:42-52`（Pi）：`return { messages: [..., bootstrapMessage, ...] }` —— 同理
- `skills/using-superpowers/SKILL.md:8-15` 直接以 markdown 写规则，**没有 JSON schema 描述**

#### 格式：JSON 还是 XML？

- **超外层**（Shape A hook 输出）：**JSON**（`{"hookSpecificOutput": ...}` 三选一）
- **内层注入内容**：`using-superpowers` SKILL.md 全文（Markdown），用 `<EXTREMELY_IMPORTANT>...</EXTREMELY_IMPORTANT>` XML 风格标签包起来（`hooks/session-start:30-32`）
- **工具描述**：Markdown 表格（在 `references/{codex,pi,antigravity}-tools.md` 里）
- **不是 function calling 的 JSON tools 数组**

#### 是否有 prompt-as-tool 模式？

**是，100% prompt-as-tool**。没有一行 OpenAI/Anthropic protocol 的 tools schema。`grep -r "json_schema\|input_schema\|parameters:\|inputSchema" clone/superpowers/` **只在 git hook sample 文件和测试 shell 里**匹配，**不在 superpowers 业务代码里**。

#### 动态刷新

- **Shape A**：每次 session start 重新读 `using-superpowers/SKILL.md`（没有 cache，因为是 bash 一次性脚本）
- **Shape B (OpenCode)**：**有 module-level cache**（`.opencode/plugins/superpowers.js:33-34` 注释明确说 "SKILL.md file does not change during a session"，缓存到 `_bootstrapCache`）
- **Shape B (Pi)**：**有缓存**（`.pi/extensions/superpowers.ts:24` `cachedBootstrap`）

---

### Q3. 工具调用指令的解析、错误修复、准确性

**superpowers 自己的部分**：**不解析任何 tool call**。所有 tool call 解析由**宿主 agent** 完成。
**superpowers 关注的部分**：在 Skills 中告诉 LLM "如何**正确书写** tool call" + "如何**判断调用错误**"。

#### 解析

- **不涉及**。superpowers 没有自己的 LLM client、不调用 OpenAI/Anthropic SDK、不处理 `tool_calls` 数组
- 唯一的"解析"是 bootstrap 文本本身的 JSON 转义（`hooks/session-start:18-23` 的 `escape_for_json` 函数，转义 `\\` / `"` / 换行）

#### 错误修复机制

- **subagent 状态机重试**：`skills/subagent-driven-development/SKILL.md:123-145` 定义 implementer 的 4 种返回状态（DONE / DONE_WITH_CONNERNS / NEEDS_CONTEXT / BLOCKED），每种状态有明确处理路径：
  ```markdown
  # SKILL.md:131-145
  **BLOCKED:** The implementer cannot complete the task. Assess the blocker:
  1. If it's a context problem, provide more context and re-dispatch with the same model
  2. If the task requires more reasoning, re-dispatch with a more capable model
  3. If the task is too large, break it into smaller pieces
  4. If the plan itself is wrong, escalate to the human
  ```
- **审查 sub-agent 两阶段 review**（spec compliance + code quality），见 `subagent-driven-development/SKILL.md:48-58`

#### 准确性保证

- **不依赖 schema 校验**（因为没有 JSON tools schema）
- **不依赖 retry loop**（因为不调用 LLM）
- **依赖 LLM 行为约束**：通过 `using-superpowers/SKILL.md:8-15` 的 `<EXTREMELY-IMPORTANT>` 块强制 LLM "invoke skills BEFORE any response or action"
- **依赖 sub-agent 模式**（`subagent-driven-development`）降低单次任务复杂度 → 提高单次工具调用准确性
- **"red flags" 列表**（`using-superpowers/SKILL.md:21-37`）告诉 LLM "下列 12 种想法 = 你在为自己找借口不 invoke skill" —— 用 prompt 约束行为

#### 重试上限

- **没有显式的"N 次重试"概念**
- sub-agent 失败时由主 agent 重新 dispatch（无次数上限，但 dispatcher SKILL.md 强调"never force the same model to retry without changes"）

---

### Q4. 工具执行结果回传、格式、协议

**superpowers 自己的部分**：**不处理 tool result**。完全交给宿主 agent。
**superpowers 关注的部分**：**把 sub-agent 的执行结果保存为可被主 agent 复读的文件**，实现"用文件做 handoff"。

#### 回传方式

- **不涉及** —— tool result 回传给 LLM 是宿主 agent 的事（OpenAI 的 `role: "tool"` / Anthropic 的 `tool_result` 块）
- 唯一与之相关的是**测试代码**：`tests/opencode/test-priority.sh:146` 用 `awk '/"type":"tool_use"/ ... /"tool":"skill"/'` 检查 tool_use 流，证明宿主传出来的就是标准 `tool_use` 块

#### 通信协议

- **不实现**。superpowers 严格宿主无关（README.md 强调兼容 9 个不同宿主）
- 各宿主走各自协议：Claude Code / Cursor 走 Anthropic 协议，OpenCode 走 OpenAI 协议，Kimi 走 OpenAI 协议等

#### 大结果处理

- **核心机制：sub-agent 通过**文件 handoff**而不是"context 注入"传递结果**
- 证据：`skills/subagent-driven-development/scripts/{sdd-workspace,task-brief,review-package}` 三件套：
  - `sdd-workspace:14-20` — 创建 `<repo>/.superpowers/sdd/`
  - `task-brief:31-33` — 把 plan.md 抽成单个 task 的 markdown 文件给 implementer 读
  - `review-package:43-45` — `git diff` 输出到 `<repo>/.superpowers/sdd/review-<base7>..<head7>.diff` 给 reviewer 读
- 优势：**避免主 session context 被大 diff / 大 plan 撑爆**（subagent-driven-development/SKILL.md:8-12 "preserve your own context for coordination work"）

#### 格式

- implementer 回执：`task-<N>-report.md`（`subagent-driven-development/SKILL.md:243-245`）
- reviewer 回执：标准结构化报告（critical / important / minor 三级）
- progress ledger：`<repo>/.superpowers/sdd/progress.md`（`subagent-driven-development/SKILL.md:251-263`）

---

### Q5. File Backend 是否为工具调用做了适配

| 工具配置目录/文件 | 路径 | 作用 | 加载代码 |
|---|---|---|---|
| **项目级 skill workspace** | `<repo>/.superpowers/sdd/` | SDD 流程的工作目录（task brief / review diff / progress ledger） | `skills/subagent-driven-development/scripts/sdd-workspace:14-22` |
| **brainstorming 工作区** | `<repo>/.superpowers/brainstorm/<SESSION_ID>/` | 视觉伴侣的服务端状态/HTML mockup | `skills/brainstorming/scripts/start-server.sh:117-121` |
| **worktree 目录** | `<repo>/.worktrees/<branch>/` | git worktree fallback 目录 | `skills/using-git-worktrees/SKILL.md:75-78` |
| **10 个宿主 manifest** | 仓库根的 `.claude-plugin/` / `.codex-plugin/` / `.cursor-plugin/` / `.kimi-plugin/` / `gemini-extension.json` / `package.json` 等 | 每个宿主一个，声明 skills 路径 + hook 入口 | 见上 Q1 / Q2 证据 |
| **bootstrap hook** | `hooks/session-start` + `hooks/hooks.json` + `hooks/hooks-cursor.json` + `hooks/run-hook.cmd` | Shape A 宿主的 session-start 注入器 | `hooks/session-start:1-65` |
| **in-process 插件** | `.opencode/plugins/superpowers.js` + `.pi/extensions/superpowers.ts` | Shape B 宿主的注册器 + bootstrap 注入 | 见上 |
| **self-mask gitignore** | `<repo>/.superpowers/sdd/.gitignore`（内容 `*`）+ 仓库根 `.gitignore` 第 4 行 `.superpowers/` | 防止 superpowers 工作区污染 git | `sdd-workspace:21-22` + `.gitignore:4` |
| **持久化端口/token** | `<repo>/.superpowers/brainstorm/.last-port` + `.last-token` | brainstorming visual companion 重启后绑定同一端口 | `start-server.sh:120-121` |

**全局 vs 项目级**：
- **没有 `~/.superpowers/` 全局配置目录**（10 个宿主 manifest 都不写全局配置）
- **全局 skills 库** 落在宿主 agent 自己的 plugin 安装目录（如 `~/.claude/plugins/superpowers/` 或 `~/.config/opencode/superpowers/`），由宿主决定
- **项目级** `.superpowers/` 由 skill 脚本按需 `mkdir -p` 创建
- `tests/hooks/test-session-start.sh:194` 提到 `~/.config/superpowers/skills` 路径并标注 **obsolete legacy**（已废弃）

**与 standard/file_backend.md 对照**：
- ✅ 符合 §3.9 "项目级 scratch 目录 + 自屏蔽 .gitignore"
- ✅ 符合 §2.1 "用户可改存储根"（虽然 superpowers 本身不定义根，但支持通过宿主的 env 覆盖）
- ❌ **违反** §1.2 "控制平面与工作区分离"——superpowers 完全寄生宿主，不定义自己的控制平面
- ❌ **违反** §10.8 "MCP 协议支持"——superpowers 自身**不注册任何 MCP server**
- ✅ 符合 §1.3 "AGENTS.md 向上扫描"——`AGENTS.md` 一行引用 `CLAUDE.md`（`clone/superpowers/AGENTS.md:1`）

---

## 3. 关键代码片段

### 3.1 Shape A 单一 bootstrap 入口（Claude Code / Cursor / Copilot CLI）

`hooks/session-start:1-65` —— 读 `using-superpowers/SKILL.md` 全文，按宿主 env 切 JSON 形状：
```bash
# 行 9-10:plugin 根从 hook 自身位置反推
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# 行 25-32:组装 session_context,用 <EXTREMELY_IMPORTANT> 包起来
session_context="<EXTREMELY_IMPORTANT>\nYou have superpowers.\n\n**Below is the full content of your 'superpowers:using-superpowers' skill...**\n\n${using_superpowers_escaped}\n</EXTREMELY_IMPORTANT>"

# 行 35-50:三选一 JSON 形状
if [ -n "${CURSOR_PLUGIN_ROOT:-}" ]; then
  printf '{\n  "additional_context": "%s"\n}\n' "$session_context" | cat
elif [ -n "${CLAUDE_PLUGIN_ROOT:-}" ] && [ -z "${COPILOT_CLI:-}" ]; then
  printf '{\n  "hookSpecificOutput": { "hookEventName": "SessionStart", "additionalContext": "%s" }}\n' "$session_context" | cat
else
  printf '{\n  "additionalContext": "%s"\n}\n' "$session_context" | cat
fi
```

### 3.2 Shape B (OpenCode) in-process 注入

`.opencode/plugins/superpowers.js:88-119` —— 直接 unshift 到第一条 user message：
```javascript
'experimental.chat.messages.transform': async (_input, output) => {
  const bootstrap = getBootstrapContent();
  if (!bootstrap || !output.messages.length) return;
  const firstUser = output.messages.find(m => m.info.role === 'user');
  if (!firstUser || !firstUser.parts.length) return;
  if (firstUser.parts.some(p => p.type === 'text' && p.text.includes('EXTREMELY_IMPORTANT'))) return;

  const ref = firstUser.parts[0];
  firstUser.parts.unshift({ ...ref, type: 'text', text: bootstrap });
}
```

### 3.3 Tool name 翻译表（OpenCode 例子）

`.opencode/plugins/superpowers.js:64-79` —— superpowers **不定义工具，只翻译**宿主工具名：
```javascript
const toolMapping = `**Tool Mapping for OpenCode:**
When skills request actions, substitute OpenCode equivalents:
- Create or update todos → \`todowrite\`
- \`Subagent (general-purpose):\` → \`task\` with \`subagent_type: "general"\`
- Invoke a skill → OpenCode's native \`skill\` tool
- Read files → \`read\`
- Create, edit, or delete files → \`apply_patch\`
- Run shell commands → \`bash\`
- Search files → \`grep\`, \`glob\`
- Fetch a URL → \`webfetch\``;
```

### 3.4 sub-agent 文件 handoff（核心"伪大结果处理"）

`skills/subagent-driven-development/scripts/sdd-workspace:14-22` + `task-brief` + `review-package` 三件套，让大 diff / 大 plan 走文件而不是 context 注入：
```bash
# sdd-workspace:14-22
root=$(git rev-parse --show-toplevel)
dir="$root/.superpowers/sdd"
mkdir -p "$dir"
printf '*\n' > "$dir/.gitignore"   # 自屏蔽
cd "$dir" && pwd
```

---

## 4. 与 Onion Agent 设计的关联

### 4.1 superpowers 给 Onion Agent 的**反例/避坑**

1. **"完全依赖宿主"是双刃剑** —— superpowers 把所有工具调用逻辑都甩给宿主 agent，意味着它**完全没有**自己的 tool protocol 抽象层；如果宿主 API 变更，superpowers 必须重新适配（已有 9 个 manifest + 3 个 Shape 的复杂维护成本）。Onion Agent 既然是**自研单一产品**，可以走"自己的 tools schema + provider 适配器"模式，避免 manifest 膨胀。
2. **`<EXTREMELY_IMPORTANT>` 标签的脆弱性** —— 用 XML 风格标签 + 强烈语气词约束 LLM 行为，本质是"prompt 黑客"。LLM 不保证 100% 遵守（实测在长 context 后会被忽略）。Onion Agent 应当用**结构化 system prompt 段**（如 `<system priority="critical">...</system>`）+ 工具层的**实际权限校验**（参考 Hermes 的 `_ROOT_CREDENTIAL_DIRS`）双轨。

### 4.2 superpowers 给 Onion Agent 的**可借鉴模式**

1. **"大结果走文件而不是 context"** —— `task-brief.md` / `review-package.diff` / `progress.md` 三件套，避免主 session context 撑爆。Onion Agent 的 `session.json` 可以借鉴：在 sub-agent 边界上**不把完整 transcript 写回主 session**，而是用 `<reference target="file://..."/>` 占位。
2. **`<EXTREMELY_IMPORTANT>` 注入 + 工具名翻译表** —— superpowers 的 `using-superpowers/SKILL.md` 注入后模型立刻知道自己该用什么工具。Onion Agent 的 system prompt 可以有专门的 `<tool-protocol>` 段，告诉 LLM "你只能调以下 N 个工具，每个工具的 schema 如下"，避免模型乱发 tool_call。
3. **"三大 Shape 集成模式"是教科书级抽象** —— `docs/porting-to-a-new-harness.md:108-280` 把集成方式分为 **Shell-hook / In-process plugin / Instructions-file** 三大类。Onion Agent 未来如果做"嵌入到其他 host 里"的副模式，可以直接借鉴这个分类。
4. **"polyglot 脚本" (run-hook.cmd)** —— `hooks/run-hook.cmd:1-32` 用 `: << 'CMDBLOCK' ... CMDBLOCK` heredoc 让同一个文件在 Windows cmd 和 Unix bash 下都能跑。Onion Agent 跨平台 shell hook 可以直接复用这个模式。
5. **sub-agent 状态机**（DONE / DONE_WITH_CONCERNS / NEEDS_CONTEXT / BLOCKED）—— `subagent-driven-development/SKILL.md:127-145` 的 4 态设计比单一"成功/失败"丰富得多。Onion Agent 的 sub-agent 协议可以采用。
6. **自屏蔽 `.gitignore` 写在子目录里** —— `.superpowers/sdd/.gitignore` 内容只有 `*`，一个文件就让整个目录对 git 不可见。比修改仓库根 `.gitignore` 更优雅。Onion Agent 的 `<repo>/.onion/scratch/.gitignore` 可以直接复用。

### 4.3 superpowers 给 Onion Agent 的**关键差异**

superpowers 是"**寄生插件**"，所有工具调用协议都是宿主的；Onion Agent 是"**自研产品**"，必须有**自己的 tool protocol + 自己的 provider 适配器**（参考 deepcode 的"Provider 可热插拔"定位）。这意味着：

- Onion Agent **不能**像 superpowers 一样用"工具翻译表"绕过协议设计 —— 必须自己定义 `tools: [...]` 的 JSON schema
- Onion Agent **应当**学 superpowers 的"把 using-superpowers 这种元提示注入 session start"做法，作为 session.json 的 `<system priority="critical">` 段
- Onion Agent **可以省掉** superpowers 的 10 个 manifest 维护成本（因为单一产品），但**应当学** superpowers 的 Shape A/B/C 抽象以便未来扩展（比如做 IDE 插件或 web 端）

---

## 5. 不确定 / 未找到

1. **superpowers 是否注册任何 OpenAI/Anthropic SDK 调用** —— 0 匹配。源码 100% 是 prompt 注入 + bash 脚本 + JS/TS 插件，**不调用任何 LLM SDK**。所有"调用 LLM"的动作都由宿主 agent 完成。
2. **MCP 工具的具体注册路径** —— superpowers **自身不注册 MCP server**；MCP 支持完全靠宿主 agent 提供（README.md:200 提到 Copilot/Cursor/Kimi 都"通过宿主原生支持"）。所以 superpowers 能不能用 MCP 工具，**取决于宿主 agent**，**与 superpowers 无关**。
3. **大结果处理（如图片、二进制）的具体策略** —— 没找到 superpowers 自己定义的二进制处理逻辑。图片等场景完全交给宿主 agent（依赖宿主的 vision / multimodal 能力）。
4. **流式增量解析的细节** —— superpowers 不做 LLM 流式解析。`tests/explicit-skill-requests/run-test.sh:75` 用了 `--output-format stream-json` 跑测试，但那只是测试代码用 Claude Code 的 CLI 模式跑回归，**不是 superpowers 业务代码**。
5. **9 个宿主工具的"实际调用协议"清单** —— 各宿主走各自协议，没有 superpowers 自己统一的 `tools: [...]` 列表。如果要做"Onion Agent 的工具标准"，需要分别读各宿主的源码（Claude Code / Codex / OpenCode / Cursor / Kimi / Pi / Antigravity / Copilot CLI / Factory Droid）——**这超出本次调研范围**。

---

**调研完成时间**：基于 `clone/superpowers` 当前 `main` 分支（版本 6.1.1，见 `.claude-plugin/plugin.json:4`）。
**对比基线**：`harness/01_market_research/standard/file_backend.md` §1.1 / §2.7 / §3.9 / §10.8 / §11。
