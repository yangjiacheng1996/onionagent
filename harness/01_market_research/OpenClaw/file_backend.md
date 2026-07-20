# OpenClaw — 工作区(File Backend)调研报告

> 调研对象:`github.com/openclaw/openclaw` 仓库 `main` 分支(`git clone --depth 1` 快照,2026-07-17)
> 调研范围:仅 `OpenClaw` 一个智能体,聚焦"工作区 / File Backend"维度
> 调研日期:2026-07-17

---

## 0. 智能体一句话定位

持续运行的个人 AI 助手,"agent loop + 多渠道接入";支持 20+ 即时通讯渠道(WhatsApp / Telegram / Slack / Discord / Signal / iMessage / 飞书 / 微信 / QQ / Matrix 等),语音唤醒 + Talk Mode,多 Agent 路由,沙箱默认 Docker,跨平台(macOS / Linux / Windows WSL2 + Windows Hub)。

> 备注:OpenClaw **明确区分了"工作区(workspace)"和"状态目录(state dir)"两个概念**——前者是 agent 的"家"(用户记忆 / SOUL / 笔记 / skills),后者是系统级配置和会话数据存放地。**默认情况下两者都落在 `~/.openclaw/` 下,但语义完全分离**。这是本次调研最重要的发现,下面所有路径解析都要注意这一点。

---

## 1. 调研依据

### 1.1 源码路径

```
C:\workspace\github\onionagent\harness\01_market_research\clone\openclaw\
```

(只读快照,未做任何修改。)

### 1.2 关键文件(已重点阅读)

| # | 文件 | 说明 |
|---|------|------|
| 1 | `src/agents/workspace-default.ts` | **核心**——默认 agent workspace 路径解析器(完整读完 32 行) |
| 2 | `src/agents/workspace-dir.ts` | workspace 路径规范化(`normalizeWorkspaceDir` / `resolveWorkspaceRoot`) |
| 3 | `src/agents/agent-dirs.ts` | agent 级 `agentDir` 解析(共享 state 子目录) |
| 4 | `src/config/paths.ts` | **核心**——`resolveStateDir` / `resolveConfigPath` / `resolveOAuthDir`(完整读完 400+ 行) |
| 5 | `src/agents/workspace.ts` | workspace bootstrap / template / state 助手(AGENTS.md / SOUL.md 等 seed) |
| 6 | `src/agents/workspace-state-store.ts` | workspace 状态 SQLite 存储 |
| 7 | `src/agents/workspace-templates.ts` | bootstrap 模板文件(AGENTS.md / SOUL.md / USER.md / IDENTITY.md 等) |
| 8 | `src/agents/workspace-legacy-state.ts` | 旧版 workspace state 迁移(`.openclaw/workspace-state.json` → SQLite) |
| 9 | `src/agents/workspace-run.ts` | workspace 运行时(执行 session 时的 workspace 解析) |
| 10 | `src/agents/sandbox/workspace-authority.ts` + `workspace-mounts.ts` | 沙箱 workspace 挂载 |
| 11 | `src/commands/setup/` 目录(空但存在)+ `onboard-non-interactive/` | setup / onboard 命令实现位置 |
| 12 | `src/cli/profile.ts` + `profile-utils.ts` | `OPENCLAW_PROFILE` 隔离 profile 机制 |
| 13 | `src/cli/program.ts` + `argv.ts` | commander 程序根 |
| 14 | `openclaw.mjs` (23 KB) | 根级 CLI 入口(`node openclaw.mjs gateway --port 18789 --verbose`) |

### 1.3 关键文档(已重点阅读)

| # | 文档 | 说明 |
|---|------|------|
| 1 | `docs/concepts/agent-workspace.md` | **核心**——workspace 概念、默认位置、覆盖机制、文件清单、备份策略 |
| 2 | `docs/concepts/multi-agent.md` | 多 agent workspace 隔离 |
| 3 | `docs/concepts/session.md` | session 存储位置(workspace 之外) |
| 4 | `docs/start/setup.md` | 显式 setup 命令说明 |
| 5 | `docs/start/wizard.md` | `openclaw onboard` 交互式向导 |
| 6 | `docs/start/getting-started.md` | 快速上手 |
| 7 | `docs/start/onboarding.md` | macOS 桌面端 onboarding 流程 |
| 8 | `README.md`(第 266-270 行) | 官方对 workspace 的 3 行概要 |
| 9 | `docs/install/nix.md` + `config.nix-integration-u3-u5-u9.test.ts` | Nix 模式 / 状态目录覆盖测试 |

### 1.4 README 关键引用(原文)

```text
## Agent workspace + skills

- Workspace root: `~/.openclaw/workspace` (configurable via `agents.defaults.workspace`).
- Injected prompt files: `AGENTS.md`, `SOUL.md`, `TOOLS.md`.
- Skills: `~/.openclaw/workspace/skills/<skill>/SKILL.md`.
```

—— `README.md:266-270`

---

## 2. 三个核心问题的回答

### Q1. 工作区路径:固定 vs 可自定义

**结论:OpenClaw 同时支持「固定默认」和「完全可自定义」,通过四层优先级叠加。**

#### 1.1 默认位置

```typescript
// src/agents/workspace-default.ts:7-23
export function resolveDefaultAgentWorkspaceDir(
  env: NodeJS.ProcessEnv = process.env,
  homedir: () => string = os.homedir,
): string {
  const workspaceDir = env.OPENCLAW_WORKSPACE_DIR?.trim();
  if (workspaceDir) {
    return path.resolve(workspaceDir);                  // 1. 环境变量覆盖
  }
  const home = resolveRequiredHomeDir(env, homedir);
  const profile = env.OPENCLAW_PROFILE?.trim();
  if (profile && normalizeOptionalLowercaseString(profile) !== "default") {
    return path.join(home, ".openclaw", `workspace-${profile}`);  // 2. profile 隔离
  }
  return path.join(home, ".openclaw", "workspace");    // 3. 默认
}
```

**默认是 `~/.openclaw/workspace`(home 目录下的固定子目录),不是 `cwd`,不是 `~/Documents`,不是 `%APPDATA%`**。

#### 1.2 四层覆盖机制(从高到低)

| 优先级 | 方式 | 代码 / 文档证据 | 适用场景 |
|:---:|------|------|---------|
| 1 | 环境变量 `OPENCLAW_WORKSPACE_DIR=<path>` | `src/agents/workspace-default.ts:11-13`<br>`src/agents/workspace.defaults.test.ts:25-36`(测试 "uses OPENCLAW_WORKSPACE_DIR before OPENCLAW_HOME") | 临时切换、容器/CI 部署 |
| 2 | 环境变量 `OPENCLAW_PROFILE=<name>`(非 default) | `src/agents/workspace-default.ts:15-19` | 多环境隔离(工作/个人/test) |
| 3 | 配置文件 `agents.defaults.workspace`(`~/.openclaw/openclaw.json`) | `docs/concepts/agent-workspace.md`:<br>> `Override in ~/.openclaw/openclaw.json`<br>`{ agents: { defaults: { workspace: "~/.openclaw/workspace" } } }` | 持久化自定义(官方推荐方式) |
| 4 | 配置文件 `agents.list[].workspace`(每 agent 独立) | `docs/concepts/agent-workspace.md`:<br>> `Per-agent override: agents.list[].workspace.` | 多 agent 不同 workspace |
| 5 | 默认 `~/.openclaw/workspace` | 同上 | 全新安装 |

#### 1.3 配置示例(`docs/concepts/agent-workspace.md` 原文)

```json5
{
  agents: {
    defaults: {
      workspace: "~/.openclaw/workspace",
    },
  },
}
```

#### 1.4 关于"跟随当前目录"

**OpenClaw 不支持 `cd myproject && openclaw` 默认就把 myproject 当 workspace**。但 `src/agents/workspace-dir.ts:31-33` 有一个回退机制:

```typescript
/** Resolves the effective workspace root, falling back to cwd. */
export function resolveWorkspaceRoot(workspaceDir?: string): string {
  return normalizeWorkspaceDir(workspaceDir) ?? process.cwd();
}
```

这个 **cwd 回退仅在调用方传入的 workspace 为 `undefined`/`null` 时**才生效,不是默认行为。文档和 README 都没说"跟随当前目录",所以这个分支是给"调用者没传 workspace"的内部代码用的,**不算 Q1 里的第三种模式**。

#### 1.5 Profile 隔离(隐性的第二种固定位置)

- `OPENCLAW_PROFILE=work` → workspace 解析为 `~/.openclaw/workspace-work`
- `OPENCLAW_PROFILE=test` → `~/.openclaw/workspace-test`
- 这等同于"用同一个根 `~/.openclaw/` 下的多个固定子目录",**不算用户自由指定路径**,但属于一种"内置多 workspace 隔离"机制。

---

### Q2. 工作区目录结构

**结论:OpenClaw 严格区分"状态目录(state dir)"和"工作区(workspace)"两个根。两者默认都在 `~/.openclaw/` 下,但语义和内容完全不同。下表分别列出。**

#### 2.1 「状态目录」`$STATE_DIR` 默认 `~/.openclaw/`

> 此处**不是**工作区,是系统级数据。`docs/concepts/agent-workspace.md` 明确说:"This is separate from `~/.openclaw/`, which stores config, credentials, and sessions."

| 路径 | 内容 | 来源 / 作用 |
|------|------|------------|
| `$STATE_DIR/openclaw.json` | 主配置文件(JSON5) | `src/config/paths.ts:107-120`(`resolveConfigPath`, `CONFIG_FILENAME = "openclaw.json"`) |
| `$STATE_DIR/state/openclaw.sqlite` | 共享 workspace setup 状态 + attestations | `docs/concepts/agent-workspace.md` 明确列出 |
| `$STATE_DIR/credentials/` | channel/provider 状态 + legacy OAuth import | `src/config/paths.ts:184-198`(`resolveOAuthDir`, `OAUTH_FILENAME = "oauth.json"`) |
| `$STATE_DIR/credentials/oauth.json` | OAuth 凭据 | `src/config/paths.ts:191-198`(`resolveOAuthPath`) |
| `$STATE_DIR/skills/` | managed skills(管理级) | `docs/concepts/agent-workspace.md` "What is NOT in the workspace" 段 |
| `$STATE_DIR/agents/<agentId>/agent/auth-profiles.json` | 模型认证(OAuth + API key) | `docs/concepts/agent-workspace.md` 列出 |
| `$STATE_DIR/agents/<agentId>/agent/openclaw-agent.sqlite` | session 行 / 转录 / 每 agent runtime 状态 | 同上 |
| `$STATE_DIR/agents/<agentId>/agent/codex-home/` | per-agent Codex runtime(account, config, skills, plugins, native thread state) | 同上 |
| `$STATE_DIR/agents/<agentId>/sessions/` | 旧版 session 迁移源 + archive/support artifacts | 同上 |
| `$STATE_DIR/agents/<agentId>/agent/` | per-agent 默认目录(共享 state,区分 auth/session) | `src/agents/agent-dirs.ts:62-77`(`resolveEffectiveAgentDir`):<br>`return path.join(root, "agents", id, "agent")` |
| `$STATE_DIR/delivery-queue-media/` | 待发送附件副本(避 media TTL sweep) | `src/config/paths.ts:172-174`(`resolveDeliveryQueueMediaDir`) |
| `$STATE_DIR/.env` | state-dir 级 `.env` 变量 | `src/config/env-vars.test.ts:564-578`(测试 "loads ${VAR} substitutions from ~/.openclaw/.env") |
| `$STATE_DIR/sandboxes/` | 沙箱 workspace 根(`workspaceAccess != "rw"` 时) | `docs/concepts/agent-workspace.md` 警告段 |
| `os.tmpdir()/openclaw-<uid>/` | Gateway lock 目录(ephemeral) | `src/config/paths.ts:160-166`(`resolveGatewayLockDir`) |
| **旧版(已迁移)** `$STATE_DIR/.clawdbot/` | pre-rebrand 状态目录 | `src/config/paths.ts:35`(`LEGACY_STATE_DIRNAMES = [".clawdbot"]`) |
| **旧版(已迁移)** `$STATE_DIR/clawdbot.json` | pre-rebrand 配置文件 | `src/config/paths.ts:37`(`LEGACY_CONFIG_FILENAMES = ["clawdbot.json"]`) |
| **旧版(已迁移)** `openclaw-workspace-state.json` / `.openclaw/workspace-state.json` / `.attested` | 旧版 workspace sidecars | `docs/concepts/agent-workspace.md` 末尾 "What is NOT in the workspace" 段说明已迁移到 SQLite,`openclaw doctor --fix` 可清理 |

**证据:多 agent 时 `agentDir` 必须唯一**——`src/agents/agent-dirs.ts:32-49` (`DuplicateAgentDirError`) 明确说:"Each agent must have a unique agentDir; sharing it causes auth/session state collisions and token invalidation."

#### 2.2 「工作区」`$WORKSPACE` 默认 `~/.openclaw/workspace`

| 路径 | 内容 | 加载时机 | 证据 |
|------|------|---------|------|
| `AGENTS.md` | **操作指令**(rules, priorities, "how to behave") | 每次 session 开始 | `docs/concepts/agent-workspace.md`: "Loaded at the start of every session." |
| `SOUL.md` | **人格 + 语气** | 每次 session | 同上;与 `concepts/soul` 文档关联 |
| `USER.md` | **用户是谁** + 怎么称呼 | 每次 session | 同上 |
| `IDENTITY.md` | **名字、vibe、emoji** | bootstrap ritual 时创建/更新 | 同上 |
| `TOOLS.md` | **本地工具约定**(指导用,不控制可用性) | 每次 session | 同上 |
| `HEARTBEAT.md` | heartbeat 清单(可选) | heartbeat 运行时 | 同上 |
| `BOOT.md` | 启动清单(可选,内部 hooks 启用时) | gateway restart 时 | 同上 |
| `BOOTSTRAP.md` | **首次运行仪式**(用后即删) | 仅 brand-new workspace 首次创建 | 同上:"Only created for a brand-new workspace. Delete it after the ritual is complete." |
| `memory/YYYY-MM-DD.md` | 每日 memory log(每天一个文件) | session 开始读"今天 + 昨天" | 同上;与 `docs/concepts/memory.md` 关联 |
| `MEMORY.md` | **精心策划的长期记忆**(可选) | 仅在 main private session 中加载 | 同上:"Only load MEMORY.md in the main, private session (not shared/group contexts)." |
| `skills/<skill>/SKILL.md` | workspace 级 skills(**最高优先级**) | skill 名称冲突时 | 同上;`README.md:270` 也明确 |
| `canvas/index.html` | Canvas UI 文件(可选,node displays) | canvas 工具触发时 | 同上 |
| `.git/`(建议) | 私有 git 仓库,备份用 | 推荐用户初始化 | `docs/concepts/agent-workspace.md` "Git backup (recommended, private)" 段 |

**Bootstrap 注入的体量控制**(源码中显式定义):

- `agents.defaults.bootstrapMaxChars`(默认 `20000`)——单文件截断阈值
- `agents.defaults.bootstrapTotalMaxChars`(默认 `60000`)——所有 bootstrap 文件总阈值

证据:`docs/concepts/agent-workspace.md` 末尾 "If a bootstrap file is missing, OpenClaw injects a 'missing file' marker into the session and continues. Large bootstrap files are truncated when injected; adjust limits with `agents.defaults.bootstrapMaxChars` (default: `20000`) and `agents.defaults.bootstrapTotalMaxChars` (default: `60000`)."

#### 2.3 「状态目录 vs 工作区」的核心边界

| 维度 | 状态目录 `$STATE_DIR` | 工作区 `$WORKSPACE` |
|------|---------------------|---------------------|
| **默认路径** | `~/.openclaw/` | `~/.openclaw/workspace` |
| **核心功能** | 配置 + 凭据 + 会话 + runtime state | agent 的"记忆"和"工作副本" |
| **包含 SQLite** | ✅ `openclaw.sqlite` / `openclaw-agent.sqlite` | ❌ |
| **应提交到 git** | ❌(含 secrets) | ✅(推荐 private git repo) |
| **备份策略** | 文件级(配置 + sqlite) | git 仓库级 |
| **修改方式** | 配置文件 / 环境变量 | 用户手动编辑 .md / 通过 agent 写入 |
| **文档原话** | "config, credentials, and sessions" | "memory"、"the agent's home" |

---

### Q3. 工作区创建方式

**结论:OpenClaw 同时支持「隐式」和「显式」,且两者都触发 workspace 文件的 seed。日常使用以显式 onboarding 为主,隐式 init 仅为兜底。**

#### 3.1 显式 init / setup(官方推荐路径)

OpenClaw 提供了 **三条显式创建路径**,都可以 seed workspace:

| 命令 | 作用 | 代码 / 文档证据 |
|------|------|----------------|
| `openclaw onboard` | **完整交互式向导**——检测 AI 访问、验证推理、配置 workspace + gateway + channels + skills(推荐) | `docs/start/wizard.md`: "CLI onboarding is the recommended terminal setup path on macOS, Linux, and Windows"<br>`docs/start/getting-started.md`: "Step 2: Run onboarding: `openclaw onboard --install-daemon`" |
| `openclaw setup` | **与 `onboard` 等价**(同一流程的别名) | `docs/start/setup.md`: "Bare `openclaw setup`, without `--baseline`, is an alias for `openclaw onboard` and runs the full interactive wizard." |
| `openclaw setup --baseline` | **极简模式**——只创建 config/workspace 文件夹,**不跑完整 wizard** | `docs/start/setup.md`: "Bootstrap the config/workspace folders once, without running the full onboarding wizard"<br>代码:`openclaw setup --baseline` |
| `openclaw configure` | 后续非推理配置(返回调整 settings) | `docs/start/wizard.md`: "To reconfigure non-inference settings later: `openclaw configure`" |
| `openclaw agents add <name>` | 添加新 agent(创建对应 agentDir) | `docs/start/wizard.md` 末尾 |

**关键文档原话**(`docs/concepts/agent-workspace.md`):

> `openclaw onboard`, `openclaw configure`, or `openclaw setup` create the workspace and seed the bootstrap files if they are missing.

#### 3.2 隐式创建(自动 fallback)

OpenClaw 也提供两种隐式创建机制:

**(1) Brand-new workspace 自动 git init**——`docs/concepts/agent-workspace.md` "Git backup" 段:

> If git is installed, brand-new workspaces are initialized automatically. If this workspace is not already a repo, run:
>
> ```bash
> cd ~/.openclaw/workspace
> git init
> git add AGENTS.md SOUL.md TOOLS.md IDENTITY.md USER.md HEARTBEAT.md memory/
> git commit -m "Add agent workspace"
> ```

(2) **Missing file 注入**——如果 bootstrap 文件不存在,**OpenClaw 不报错,只注入 "missing file" 标记到 session 并继续**:

> If a bootstrap file is missing, OpenClaw injects a "missing file" marker into the session and continues.

这意味着:**用户甚至可以手动 `mkdir ~/.openclaw/workspace` 然后让 agent 在第一次跑时自动 seed**——只要 `agents.defaults.skipBootstrap !== true`。

#### 3.3 关闭 bootstrap seed 的开关

```json5
{ agents: { defaults: { skipBootstrap: true } } }
```

—— `docs/concepts/agent-workspace.md` "If you already manage the workspace files yourself, disable bootstrap file creation"

**这意味着 Q3 的"隐式 vs 显式"边界是模糊的**:
- 显式 onbording 是**官方推荐**;
- 隐式创建在**没有配置文件阻挡**时**也会发生**(git init + missing file marker);
- `skipBootstrap: true` 是**最严格的隐式 / 显式分流开关**。

#### 3.4 macOS 桌面端的特殊 onboarding

- 桌面 app 有自己的 onboarding assistant,带 7 步流程图(`docs/start/onboarding.md`)
- 桌面端和 CLI 端是两条不同路径(CLI 端也可以 `--classic` 切回老式 wizard)
- 桌面端会**从其他 AI 工具(Claude Code / Codex / Hermes)导入 memory 到 `memory/imports/`**——`docs/start/onboarding.md` "Import memories" 段

---

## 3. 关键代码片段

### 片段 1:`resolveDefaultAgentWorkspaceDir` 完整逻辑

```typescript
// src/agents/workspace-default.ts:1-32

/**
 * Default agent workspace resolver.
 *
 * Derives the process workspace directory from env, profile, and home-directory state.
 */
import os from "node:os";
import path from "node:path";
import { normalizeOptionalLowercaseString } from "@openclaw/normalization-core/string-coerce";
import { resolveRequiredHomeDir } from "../infra/home-dir.js";

/** Resolve the default agent workspace directory from env/profile/home state. */
export function resolveDefaultAgentWorkspaceDir(
  env: NodeJS.ProcessEnv = process.env,
  homedir: () => string = os.homedir,
): string {
  const workspaceDir = env.OPENCLAW_WORKSPACE_DIR?.trim();
  if (workspaceDir) {
    return path.resolve(workspaceDir);
  }
  const home = resolveRequiredHomeDir(env, homedir);
  const profile = env.OPENCLAW_PROFILE?.trim();
  if (profile && normalizeOptionalLowercaseString(profile) !== "default") {
    return path.join(home, ".openclaw", `workspace-${profile}`);
  }
  return path.join(home, ".openclaw", "workspace");
}
```

### 片段 2:State dir 解析(含 legacy fallback)

```typescript
// src/config/paths.ts:25-78(节选)

const LEGACY_STATE_DIRNAMES = [".clawdbot"] as const;
const NEW_STATE_DIRNAME = ".openclaw";
const CONFIG_FILENAME = "openclaw.json";
const LEGACY_CONFIG_FILENAMES = ["clawdbot.json"] as const;

export function resolveStateDir(
  env: NodeJS.ProcessEnv = process.env,
  homedir: () => string = envHomedir(env),
): string {
  const effectiveHomedir = () => resolveRequiredHomeDir(env, homedir);
  const override = env.OPENCLAW_STATE_DIR?.trim();
  if (override) {
    return resolveUserPath(override, env, effectiveHomedir);
  }
  const newDir = newStateDir(effectiveHomedir);
  if (env.OPENCLAW_TEST_FAST === "1") {
    return newDir;
  }
  const legacyDirs = legacyStateDirs(effectiveHomedir);
  const hasNew = fs.existsSync(newDir);
  if (hasNew) {
    return newDir;
  }
  const existingLegacy = legacyDirs.find((dir) => {
    try { return fs.existsSync(dir); } catch { return false; }
  });
  if (existingLegacy) {
    return existingLegacy;  // 旧版 .clawdbot 自动 fallback
  }
  return newDir;
}
```

### 片段 3:per-agent agentDir(共享 state 子目录,但 workspace 仍可独立)

```typescript
// src/agents/agent-dirs.ts:62-77

function resolveEffectiveAgentDir(
  cfg: OpenClawConfig,
  agentId: string,
  deps?: { env?: NodeJS.ProcessEnv; homedir?: () => string },
): string {
  const id = normalizeAgentId(agentId);
  const configured = Array.isArray(cfg.agents?.list)
    ? cfg.agents?.list.find((agent) => normalizeAgentId(agent.id) === id)?.agentDir
    : undefined;
  const trimmed = configured?.trim();
  if (trimmed) {
    return resolveUserPath(trimmed);
  }
  const env = deps?.env ?? process.env;
  const root = resolveStateDir(
    env,
    deps?.homedir ?? (() => resolveRequiredHomeDir(env, os.homedir)),
  );
  return path.join(root, "agents", id, "agent");  // 默认 <state>/agents/<id>/agent
}
```

### 片段 4:文档原话(workspace 与 state dir 的边界)

```markdown
# docs/concepts/agent-workspace.md(节选)

The workspace is the agent's home: the working directory used for file tools
and workspace context. Keep it private and treat it as memory.

This is separate from `~/.openclaw/`, which stores config, credentials, and sessions.

## Default location

- Default: `~/.openclaw/workspace`
- If `OPENCLAW_PROFILE` is set and not `"default"`, the default becomes `~/.openclaw/workspace-<profile>`.
- `OPENCLAW_WORKSPACE_DIR` overrides both of the above when set.
- Non-default agents (`agents.list[]`) without an explicit workspace resolve to `<state-dir>/workspace-<agentId>`, not the shared default workspace.
```

### 片段 5:Workspace bootstrap 缺失文件 fallback 行为

```markdown
# docs/concepts/agent-workspace.md(节选)

If a bootstrap file is missing, OpenClaw injects a "missing file" marker
into the session and continues. Large bootstrap files are truncated when
injected; adjust limits with `agents.defaults.bootstrapMaxChars` (default:
`20000`) and `agents.defaults.bootstrapTotalMaxChars` (default: `60000`).
`openclaw setup` can recreate missing defaults without overwriting existing
files.
```

---

## 4. 与 Onion Agent 设计的关联

**OpenClaw 对 Onion Agent 最值得借鉴的 3 个点:**

1. **「状态目录」与「工作区」语义分离**——Onion Agent 目前把 `session.json` 和所有记忆/历史混在一个 `~/.onion/` 下。OpenClaw 用 `state dir`(配置+凭据+SQLite)和 `workspace`(agent 记忆/技能)两个独立根,值得借鉴。**session.json 应该明确归到"工作区"侧而不是"状态目录"侧**,这样可以让用户把工作区放进 private git 仓库备份,而把状态目录留在 `~/.onion/`。

2. **「环境变量 → 配置文件 → 路径模板」三层覆盖**——OpenClaw 没有把路径"焊死",而是提供 `OPENCLAW_WORKSPACE_DIR` 环境变量 + `agents.defaults.workspace` 配置文件 + `agents.list[].workspace` per-agent 覆盖。Onion Agent 至少应该提供 `ONION_WORKSPACE_DIR` 和 `~/.onion/onion.json` 里的 `workspace` 字段。

3. **「官方 onboarding + bootstrap seed」显式创建路径**——OpenClaw 通过 `openclaw setup --baseline`(极简)和 `openclaw onboard`(完整)显式触发 workspace 初始化,并 seed AGENTS.md / SOUL.md / USER.md / IDENTITY.md 等标准文件。Onion Agent 的首次运行可以借鉴这种"标准文件模板"机制,降低用户首次使用的迷茫感。

**额外可借鉴**:`OPENCLAW_PROFILE=work` → `~/.openclaw/workspace-work` 这种 profile 隔离机制——为 Onion Agent 的"多环境"提供了最小可行方案。

---

## 5. 不确定 / 未找到

1. **「跟随当前目录」是否真的不存在**:`src/agents/workspace-dir.ts:31-33` 有一个 `process.cwd()` 回退,但只在调用方未传 workspace 时生效,**不能**确认是否有 CLI 入口会从 `process.cwd()` 推断 workspace。**没有找到 `cd myproject && openclaw` 默认把 myproject 当 workspace 的明确证据**——可能不存在,可能仅限某些子命令。

2. **init 行为在最新版本是否仍"自动 git init"**:文档说"If git is installed, brand-new workspaces are initialized automatically",但**没有在源码中直接定位到 `git init` 调用**——可能在 `workspace.ts` / `workspace-state-store.ts` 内的某个分支调用了 `child_process.spawn('git', ['init'])`,需要进一步看。**不能完全肯定**这条路径是"首次访问 workspace 目录时自动执行"还是"仅在 `openclaw setup` 时执行"。

3. **Workspace 内 `memory/` 子目录的写入机制**:`docs/concepts/memory.md` 提到 daily memory 写入,但**没有仔细阅读 `src/memory/` 下的代码**。从目录结构看,`src/memory/`(独立模块,非 `src/agents/workspace.ts` 内部)负责 memory 写入,但与 workspace 的关系没完全搞清。

4. **macOS 桌面端 onboarding 流程**:`docs/start/onboarding.md` 描述了完整流程,但本次只看了一部分,桌面端和 CLI 端的 workspace 同步机制(`memory/imports/`)未深入研究。

5. **沙箱 workspace(sandbox workspace)**:文档说"non-main sessions can use per-session sandbox workspaces under `agents.defaults.sandbox.workspaceRoot`",本次**没读** `src/agents/sandbox/workspace-authority.ts` 和 `workspace-mounts.ts` 的完整代码,只能确认存在但未深入分析。

6. **workspace-templates.ts** 的内容——只知道是 bootstrap 模板源,**没有仔细读**里面定义的 8+ 个标准模板的具体内容,只知道文件列表。

7. **`agents.defaults.skipBootstrap` 关闭后,workspace 是否还能隐式创建**:没有看到 `skipBootstrap: true` 时缺失文件的 fallback 行为测试,需要看 `workspace.ts` 源码确认。

---

**报告完。** 所有路径断言均基于 `git clone --depth 1` 快照(2026-07-17),源码以只读方式访问,未做任何修改。
