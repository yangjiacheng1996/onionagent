# sst/opencode — 工具调用（Tool Channel）调研报告

> 调研对象：[sst/opencode](https://github.com/sst/opencode)（v1.18.3）
> 调研时间：2026-07-18
> 源码路径：`C:\workspace\github\onionagent\harness\01_market_research\clone\opencode\`
> 报告路径：`C:\workspace\github\onionagent\harness\01_market_research\Opencode\tool_channel.md`

---

## 0. 智能体一句话定位

**100% 开源 + Provider 无关的终端编码 Agent**：TypeScript + Effect,通过 Vercel AI SDK `streamText` 把 30+ Provider（OpenAI / Anthropic / Google / Bedrock / 任意 OpenAI 兼容端点）适配成统一 `ModelMessage` 流,在 `tool/registry.ts` 把 **14 个内置工具 + MCP 工具 + 自定义 TS 插件工具 + Agent Skills** 汇成 JSON-Schema tools 列表交给模型。**多 Provider 协议适配是核心设计目标**。

---

## 1. 调研依据

| 路径 | 关键内容 |
| --- | --- |
| `packages/opencode/src/tool/registry.ts` | `Service` Effect Service,`tools()` 按 model/agent 过滤后返回 `Tool.Def[]` |
| `packages/opencode/src/tool/tool.ts` | `Tool.define()` + `InvalidArgumentsError` schema-tagged 错误 |
| `packages/opencode/src/tool/json-schema.ts` | Effect `Schema` → `JSONSchema7`(`fromSchema` WeakMap 缓存) |
| `packages/opencode/src/session/llm/ai-sdk.ts` | AI SDK `fullStream` → `LLMEvent`（tool-input-start/delta/end, tool-call, tool-result, tool-error） |
| `packages/opencode/src/session/llm/request.ts` | `resolveTools()` 按权限 + user 偏好过滤;`activeTools` 告诉 AI SDK 哪些工具可用 |
| `packages/opencode/src/provider/transform.ts` | `normalizeMessages` + `applyCaching` + `sanitizeOpenAISchema` 跨 Provider 翻译(1418 行) |
| `packages/opencode/src/session/llm.ts:265-279` | `experimental_repairToolCall` 工具名小写化 + invalid 兜底 |
| `packages/opencode/src/session/processor.ts` | `ensureToolCall/updateToolCall/completeToolCall/failToolCall`,`DOOM_LOOP_THRESHOLD=3` |
| `packages/opencode/src/session/message-v2.ts:417` | `convertToModelMessages` 把 SQLite `WithParts[]` → AI SDK `ModelMessage[]` |
| `packages/opencode/src/session/retry.ts:26-30` | `RETRY_INITIAL_DELAY=2000` / `BACKOFF_FACTOR=2` / `MAX_DELAY=30s` |
| `packages/opencode/src/agent/agent.ts:141-260` | `build` / `plan` / `general` / `explore` / `compaction` 5 个原生 agent |
| `packages/opencode/src/mcp/index.ts` | stdio / SSE / StreamableHTTP + OAuth |
| `packages/opencode/src/skill/index.ts:144-187` | `discoverSkills` 扫描 `.opencode/skills/` + `.claude/skills/` + `.agents/skills/` + `cfg.skills.paths` + `cfg.skills.urls` |
| `packages/opencode/src/tool/truncate.ts` | `MAX_LINES=2000` / `MAX_BYTES=50KB`,溢出写到 `Global.Path.data/tool-output/` |
| `packages/core/src/global.ts` | XDG 5 层(data / cache / config / state / tmp),`OPENCODE_TEST_HOME` 覆盖 |
| `clone/opencode/.opencode/tool/github-pr-search.ts` | 自定义工具样例（`tool()` Zod 风格） |

---

## 2. 五个核心问题的回答

### Q1. 工具来源

#### 内置工具（15 个，`tool/registry.ts:155-175`）

| 工具 | 路径 | 备注 |
| --- | --- | --- |
| `read` | `tool/read.ts` | 读文件/目录,2000 行/50KB 上限,自动 PDF/Image attachment |
| `write` / `edit` | `tool/write.ts` / `tool/edit.ts` | 写入 / 精确字符串替换（与 Cline/Gemini 同一套 diff 算法） |
| `apply_patch` | `tool/apply_patch.ts` | GPT-OSS patch 协议,仅 `gpt-` 且非 `oss` 非 `gpt-4` 时启用 |
| `glob` / `grep` | `tool/glob.ts` / `tool/grep.ts` | ripgrep 文件名/内容搜索 |
| `shell` | `tool/shell.ts` | 跨平台 shell,PowerShell `get-content`/`copy-item` 等白名单 |
| `task` | `tool/task.ts` | 启动 subagent（general/explore/用户自定义）；支持 background 异步 |
| `todowrite` | `tool/todo.ts` | 会话级 todo 列表 |
| `webfetch` / `websearch` | `tool/webfetch.ts` / `tool/websearch.ts` | URL fetch + Exa/Parallel 双 provider |
| `skill` | `tool/skill.ts` | 按需加载 skill 内容 |
| `question` | `tool/question.ts` | 弹窗问答(多选/单选/自定义) |
| `plan_exit` | `tool/plan.ts` | plan agent 完成后切到 build agent |
| `lsp` | `tool/lsp.ts` | 9 种 LSP 操作,需 `experimentalLspTool` 旗标 |
| `invalid` | `tool/invalid.ts` | 兜底（工具名错/参数错时 AI SDK 路由到这里） |

#### MCP 支持 ✅
- **客户端**：`packages/opencode/src/mcp/index.ts`,基于官方 `@modelcontextprotocol/sdk`,支持 stdio / SSE / StreamableHTTP + OAuth(`oauth-provider.ts`)
- **配置路径**：`opencode.jsonc` 的 `mcp` 字段,4 层 config 目录（`config/paths.ts:17-28`）：`~/.config/opencode/` → `<repo>/.opencode/`（向上扫到 git 边界）→ `~/.opencode/` → `OPENCODE_CONFIG_DIR` env
- **动态刷新**：订阅 `ToolListChangedNotificationSchema`（`mcp/index.ts:18`）,server push 时**立即生效**

#### Agent Skills 支持 ✅
- **规范**：`SKILL.md` + YAML frontmatter,兼容 Anthropic 风格
- **扫描路径**（`skill/index.ts:144-187`）：
  1. `~/.claude/skills/**/SKILL.md` + `~/.agents/skills/**/SKILL.md`（**外部兼容**）
  2. `<cwd>` 向上到 `<worktree>` 的 `.claude/skills/` + `.agents/skills/`
  3. 4 层 config 目录下的 `.opencode/skills/**/SKILL.md`
  4. `cfg.skills.paths` 显式列表
  5. `cfg.skills.urls` 远程 HTTP 索引（**缓存到 `<cache>/skills/<name>/`**,带版本号原子更新 + 7 天清理）
- **暴露方式**：`tool/skill.ts` 的 `SkillTool`,模型主动调 `skill(name="...")`,返回 `<skill_content>` XML 块
- **内置 skill**：`customize-opencode`（**优先级低于磁盘同名 skill**）

#### 其他工具类型
- **LSP 工具**（`tool/lsp.ts`）：9 种 LSP 操作,需实验旗标
- **Code Mode 工具**（`tool/code-mode.ts`）：实验性,模型用 `execute` 跑 JS 沙箱循环调用多个 MCP 工具
- **自定义插件工具**（`registry.ts:135-160`）：`Glob.scanSync("{tool,tools}/*.{js,ts}", { cwd: dir })` 动态 import

---

### Q2. 工具列表的生成、传递、格式

#### 生成方式
`tool/registry.ts:130-180` 三层组合：
1. **builtin 15 个**：`Effect.all({...tool.init(...)})` 立即初始化
2. **custom 0+ 个**：扫描 4 层 config 目录的 `{tool,tools}/*.{js,ts}`,`config.waitForDependencies()` 等文件就绪后 `import(pathToFileURL(match).href)` 动态加载
3. **plugin 工具**：`Plugin.Service.list()` 取所有加载的插件

每个 tool **同时持有 `parameters`(Effect `Schema`)和 `jsonSchema`(`JSONSchema7`)**,**双协议**支持。

#### 传递方式
- **AI SDK `streamText({ tools, activeTools, model })`**（`session/llm.ts:310-320`）
- **Provider 无关**：`registry.ts:236-244` 按 `model.providerID` / `modelID` 过滤（`websearch` 只在 opencode provider / Exa/Parallel 旗标下出现;`apply_patch` 只在 `gpt-` 非 `oss` 下出现）
- **activeTools**：`session/llm/request.ts:112` 把 `Object.keys(prepared.tools).filter(x => x !== "invalid")` 喂给 AI SDK
- **OpenAI 兼容硬编码**：`session/llm/request.ts:106-109` 对 `@ai-sdk/openai` / `@ai-sdk/azure` / `@ai-sdk/amazon-bedrock/mantle` 强制 `strict: false`

#### 格式：**JSON**
```ts
// tool/tool.ts:55-65
export interface Def<...> {
  id: string
  description: string
  parameters: Parameters                    // Effect Schema
  jsonSchema?: JSONSchema7                  // 同时给 LLM
  execute(args, ctx): Effect.Effect<ExecuteResult<M>>
}
```
AI SDK 内部转 OpenAI `tools[].function.parameters` 或 Anthropic `tools[].input_schema`。

#### prompt-as-tool？**否**
工具描述放 `description` 字段（每个 tool 自带 `*.txt`,如 `tool/read.txt` 13 行 usage,`tool/edit.txt` 14 行）,AI SDK 走纯 function calling,**无 system prompt 描述工具列表**。

唯一例外：**`describeTask`**（`registry.ts:210-222`）把 subagent 列表注入到 `task` 工具的 description。

#### 动态刷新：**部分**
- **MCP**：`ToolListChangedNotificationSchema` 监听,**立即生效**
- **Plugin 工具**：`plugin.list()` 每次都查
- **Custom 工具**：启动时一次性扫描,运行时新增需重启

---

### Q3. 工具调用指令的解析、错误修复、准确性

#### 解析方式：AI SDK 流式增量 + 统一 LLMEvent
`session/llm/ai-sdk.ts:60-200` 把 `fullStream` 映射：
```ts
case "tool-input-start": → LLMEvent.toolInputStart({ id, name })
case "tool-input-delta": → LLMEvent.toolInputDelta({ id, name, text: delta })
case "tool-input-end":   → LLMEvent.toolInputEnd({ id, name })
case "tool-call":        → LLMEvent.toolCall({ id, name, input: object })  // JSON 已就绪
case "tool-result":      → LLMEvent.toolResult({ id, name, result })
case "tool-error":       → LLMEvent.toolError({ id, name, message, error })
```
`session/processor.ts:115-180` 维护 `ctx.toolcalls: Record<toolCallID, ToolCall>`,**全程基于 toolCallID 关联**——Anthropic 协议核心约定,OAI 协议也兼容。`tool-input-delta` 聚合为完整 input,`tool-call` 拿到最终 `input: object`。

#### 错误修复机制
1. **AI SDK 自动修复**（`session/llm.ts:265-279` `experimental_repairToolCall`）：
   - 工具名小写化（常见于 GPT 大写误用）
   - 仍不匹配 → 路由到内置 `invalid` 工具,input 改为 `{ tool, error }`,**让 LLM 看到错误自动重试**
2. **Schema 校验**（`tool/tool.ts:67-77`）：`Schema.decodeUnknownEffect` 失败抛 `InvalidArgumentsError`（`tool.ts:19-30`）,message 格式：`"The {tool} tool was called with invalid arguments: {detail}. Please rewrite the input so it satisfies the expected schema."`,**主动引导 LLM 改写**
3. **Doom loop 检测**（`processor.ts:331-345`）：最近 3 个 part 完全相同 tool + input 连续出现 3 次 → `permission.ask({ permission: "doom_loop" })` 弹窗确认
4. **HTTP 重试**（`retry.ts:26-65`）：`2000ms × 2^attempt`,cap `30s`,按 `Retry-After` HTTP header 走 server hint
5. **Anthropic toolCallId 清洗**（`transform.ts:172-186`）：非 `[a-zA-Z0-9_-]` → `_`;Mistral 限制 9 字符

#### 准确性保证
- ✅ **Schema 校验**（Effect Schema 编译时 + 运行时）
- ✅ **错误回灌重试**（`InvalidArgumentsError` 喂回 LLM,自动改写）
- ✅ **Plan-then-act 模式**：`plan` agent（`agent/agent.ts:156-181`）禁所有 edit 工具,只读 + plan_exit
- ✅ **Doom loop 防护**（3 次同 input 弹窗）

#### 重试上限
- **HTTP**：`maxRetries: input.retries ?? 0`（`llm.ts:308`），默认 0,调用方控制
- **ValidationError**：无显式上限,LLM 一直改不对就持续重发（依赖 `maxRetries` 兜底）
- **Doom loop**：3 次触发弹窗（不阻断,仅询问）

---

### Q4. 工具执行结果回传

#### 回传方式：AI SDK `tool-result` part 嵌入 assistant 消息
`session/processor.ts:384-418` 的 `case "tool-result"`：AI SDK 在下一轮 `messages` 把 `tool-result` part 放进上一条 assistant 消息（**OAI:role=tool;Anthropic:tool_use_id 对应 tool_result 块;AI SDK 抽象成 `tool-call` + `tool-result` pair**）。

#### 格式：**结构化对象**
```ts
// tool/tool.ts:42-52
export interface ExecuteResult<M> {
  title: string                              // 短标题
  metadata: M                                // 结构化元数据
  output: string                             // 主输出(LLM 可见)
  attachments?: FilePart[]                   // 图片/PDF
}
```
成功/失败都作为 `tool-result` part 喂回 LLM；失败单独走 `tool-error`（`ai-sdk.ts:212-224`）。

#### 通信协议：**Provider 无关,统一 `ModelMessage`**
`session/message-v2.ts:417` 用 `convertToModelMessages()` 把 SQLite `WithParts[]` → AI SDK `ModelMessage[]`,**AI SDK 内部按 provider 转各自协议**。

`provider/transform.ts:73-160` 的 `normalizeMessages` 处理跨 Provider 差异：
- **Anthropic 拒绝空 content** → 过滤
- **DeepSeek 必须有 reasoning part** → 没就塞空 reasoning
- **interleaved reasoning** 按 `capabilities.interleaved.field` 塞到 `providerOptions.openaiCompatible[reasoning_content]`

#### 大结果处理：**截断 + 落盘 + 委托 subagent**
- `MAX_LINES=2000` / `MAX_BYTES=50KB`
- 溢出写到 **`Global.Path.data/tool-output/tool_<id>`**（`truncation-dir.ts:3`）
- 提示："Use the Task tool to have explore agent process this file with Grep and Read (with offset/limit). Do NOT read the full file yourself - delegate to save context."（`truncate.ts:118-122`）
- 7 天自动清理

图片/PDF 走 `attachments`,`processor.ts:390-405` 还会过 `Image.normalize()` 缩图,失败时换 `[image omitted: could not be resized]` 文本。

---

### Q5. File Backend 是否为工具调用做了适配

#### 工具配置目录清单
| 路径 | 内容 | 加载位置 |
| --- | --- | --- |
| `~/.config/opencode/opencode.jsonc` | 用户级 MCP + skills.paths/urls + permission | `config/paths.ts:23-26` |
| `<repo>/.opencode/opencode.jsonc` | 项目级 MCP + 工具配置 | `config/paths.ts:21-22` |
| `<repo>/.opencode/tool/*.ts` | 自定义 TS 工具 | `tool/registry.ts:135-150` |
| `<repo>/.opencode/skills/<name>/SKILL.md` | 项目级 skills | `skill/index.ts:180-185` |
| `<repo>/.opencode/agent/*.md` | 自定义 agent | `config/agent.ts` |
| `<repo>/.opencode/command/*.md` | 自定义 slash command | `config/command.ts` |
| `~/.claude/skills/`, `~/.agents/skills/` | 外部 skill 兼容 | `skill/index.ts:43-45, 154-164` |
| `<data>/tool-output/tool_<id>` | 大结果溢出文件 | `tool/truncation-dir.ts:3` |
| `<cache>/skills/<name>/` | 远程 skill 缓存 | `skill/discovery.ts:32-60` |
| `<data>/plans/*.md` | plan agent 写的 plan 文件 | `agent/agent.ts:169-174` |

#### 关键加载代码
```ts
// tool/registry.ts:134-150
const dirs = yield* config.directories()
const matches = dirs.flatMap((dir) =>
  Glob.scanSync("{tool,tools}/*.{js,ts}", { cwd: dir, absolute: true, ... })
)
for (const match of matches) {
  const mod = yield* Effect.promise(() => import(pathToFileURL(match).href))  // 动态 import
  for (const [id, def] of Object.entries(mod)) { custom.push(fromPlugin(...)) }
}

// skill/index.ts:144-187
for (const dir of externalDirs) yield* scan(state, path.join(global.home, dir), EXTERNAL_SKILL_PATTERN)
const upDirs = yield* fsys.up({ targets: externalDirs, start: directory, stop: worktree })
for (const dir of configDirs) yield* scan(state, dir, OPENCODE_SKILL_PATTERN)
for (const url of cfg.skills?.urls ?? []) yield* discovery.pull(url)
```

#### 全局 vs 项目级：**双层,全局 + 项目级覆盖**
`~/.config/opencode/opencode.jsonc`（用户级）+ `<repo>/.opencode/opencode.jsonc`（项目级,`afs.up()` 向上扫到 git 边界）+ `OPENCODE_CONFIG_DIR` env。

#### 与 `standard/file_backend.md` 对照
- ✅ **§3.1 三层分离**：`<config>/` + `<repo>/.opencode/` + `<data>/tool-output/`
- ✅ **§10.8 MCP 支持**：4 层配置 + 动态 ToolListChanged + OAuth
- ✅ **§5.3 secrets 0o600**（file_backend 已述）
- ✅ **§5.4 LLM 不可读凭证白名单**：`*.env: "ask"` + `*.env.*: "ask"`（`agent/agent.ts:124-130`）
- ❌ **§9.4 AGENTS.md 字节上限**：无上限（file_backend 反例）
- ❌ **§3.8 Bootstrap 种子**：缺文件不报错,不 seed AGENTS.md

---

## 3. 关键代码片段

### 3.1 Doom loop 检测（`processor.ts:331-345`）
```ts
const recentParts = parts.slice(-DOOM_LOOP_THRESHOLD)  // 3
if (recentParts.length !== DOOM_LOOP_THRESHOLD ||
    !recentParts.every((p) => p.type === "tool" && p.tool === value.name &&
      p.state.status !== "pending" && JSON.stringify(p.state.input) === JSON.stringify(input))) return
yield* permission.ask({ permission: "doom_loop", patterns: [value.name], ... })
```

### 3.2 工具名自动修复（`llm.ts:265-280`）
```ts
async experimental_repairToolCall(failed) {
  const lower = failed.toolCall.toolName.toLowerCase()
  if (lower !== failed.toolCall.toolName && prepared.tools[lower]) return { ...failed.toolCall, toolName: lower }
  return { ...failed.toolCall, input: JSON.stringify({ tool: failed.toolCall.toolName, error: failed.error.message }), toolName: "invalid" }
}
```

### 3.3 大结果截断委托（`truncate.ts:107-130`）
```ts
const hint = hasTaskTool(agent)
  ? `The tool call succeeded but the output was truncated. Full output saved to: ${file}
Use the Task tool to have explore agent process this file with Grep and Read (with offset/limit).
Do NOT read the full file yourself - delegate to save context.`
  : `The tool call succeeded but the output was truncated. Full output saved to: ${file}
Use Grep to search the full content or Read with offset/limit to view specific sections.`
```

### 3.4 Skill 加载 XML 注入（`tool/skill.ts:34-55`）
```ts
return {
  title: `Loaded skill: ${info.name}`,
  output: [
    `<skill_content name="${info.name}">`, `# Skill: ${info.name}`, "", info.content.trim(), "",
    `Base directory for this skill: ${base}`,
    `<skill_files>${files.map(f => `<file>${path.resolve(dir, f.path)}</file>`).join("\n")}</skill_files>`,
    `</skill_content>`,
  ].join("\n"),
}
```

---

## 4. 与 Onion Agent 设计的关联

1. **Provider 无关 + 协议统一中间表示是核心**：opencode 走 AI SDK + `ModelMessage` 统一中间表示,Onion 应当**学**——选 AI SDK 或自实现 `ModelMessage` Schema 作为"内部协议",在 Adapter 层转 OpenAI / Anthropic / Google / 国产模型,避免每加一个 provider 改 Agent Loop。`tool/registry.ts` 的**双轨**（`parameters` Effect Schema + `jsonSchema` JSON Schema7）值得直接抄。

2. **Doom loop 检测 + 截断后委托 subagent** 是 opencode 最值得借鉴的工程化设计:Onion 应当实现 `DOOM_LOOP_THRESHOLD=3` + 截断后写 `<ONION_HOME>/cache/tool-output/`,并在 hint 里**主动引导 LLM 调 sub-agent**（不要自己 read）——既节省 context 又复用 sub-agent 的并行能力。

3. **Skill 渐进式披露值得学,但要简化**:复用"按需加载 SKILL.md"模式,**不要照搬多命名兼容**（`.claude/skills` / `.agents/skills` 兼容是 opencode 生态包袱,Onion 是新项目只走 `<repo>/.onion/skills/` + `~/.onion/skills/`）。

4. **不该学的反例**：①`flags.experimentalLspTool` 这类运行时分支参数,Onion 应该在 tool registry 注册期决定；②5 个分散 env 覆盖点（file_backend §2.1 反例）；③`AGENTS.md` 无字节上限（file_backend §9.4 反例）。

5. **Onion 应当学 `apply_patch` 按 model 切换工具**（`registry.ts:240-245`）：GPT-OSS 用 patch,其他模型用 edit——**Provider 切换工具而非切换 system prompt**,model-aware tool routing 的好范式。

---

## 5. 不确定 / 未找到

- **Plugin 工具的 sandbox 隔离**：`registry.ts:154-160` 把 plugin tool 包装成 `Tool.Def`,但 `import(pathToFileURL(match).href)` 是**无沙箱动态 import**,用户写的 ts 工具能直接读任意文件,未发现显式沙箱保护。
- **Code Mode 沙箱**：`tool/code-mode.ts` 实验性功能,本次未深读(vm2/isolated-vm 未在源码验证)。
- **`maxRetries` 调用方传值**：`llm.ts:308` `input.retries ?? 0` 默认 0,推测由 session config 注入（通常 3-5）但**未在本调研范围追全**。
- **MCP merge 优先级**：源码未发现独立 `.opencode/mcp.json`,MCP 跟随 4 层 config merge,具体 merge 顺序需查 `config/config.ts` 进一步核实。

---

**报告完。** 数据基于 v1.18.3 源码,2026-07-18 调研。
