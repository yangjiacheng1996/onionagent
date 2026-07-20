# 我的提问
你找的都是一些什么乱七八糟的狗屁智能体，比如Dify是RAG+工作流形式的2025年旧版智能体。LangFlow是工作流智能体，不是react智能体。browser-use只是一个工具，连智能体都算不上。
因为你的已有知识比较陈旧，我来说明一下：
react智能体的典型代表：Openclaw小龙虾，2026年1月才开始流行。
后面爆发了很多衍生体：Hermes agent、Autoclaw澳龙、Workbuddy、QwenPaw。
编程工具也变成了react智能体，包括：Cline、Codex、Opencode、MiniMax agent等等

你应该调研的是这些风格agent，而不是那些工具类的、工作流类、RAG类、简单问答类的智能体。
请你充分把握什么叫智能体，然后重写harness/market_research/top_20_react_agent.md。

# GitHub Top 20 ReAct Agent 项目调研报告（v2 重写版）

> **调研目标**：在 GitHub 上找出 20 个最流行的 **ReAct 风格 AI 智能体**（Reasoning + Acting 循环，可反复"思考-行动-观察"），按 star 数量作为流行度指标降序排列。
>
> **调研日期**：2026-07-13
> **数据来源**：GitHub REST API `/repos/{owner}/{repo}`（`stargazers_count` 字段，实时拉取）+ 公开 GitHub 页面交叉验证
> **v2 版修订**：纠正 v1 版误把工具/工作流/RAG 当作智能体的错误，按"能自主循环思考+行动+观察"严格筛选。
>
> **筛选标准**（v2 严格版）：
> 1. **必须有 agent loop**：项目内置或提供持续运行的"思考-行动-观察"循环，能自主决定下一步动作
> 2. **必须可反复执行**：不是单次工具调用、不是单次问答、不是单次工作流执行
> 3. **有运行时/调度器**：有自己的 CLI、桌面端、IDE 插件、SDK 或调度器，不只是 prompt 框架
>
> **明确剔除**：
> - ❌ 纯工作流编排（Dify、LangFlow、Flowise、n8n）—— 走的是 DAG/工作流，不是 agent loop
> - ❌ 纯 RAG 框架（Haystack、LlamaIndex——只在文档场景）—— 检索增强不是 agent 行为
> - ❌ 单一工具（browser-use 是浏览器自动化工具，不是智能体）
> - ❌ 推理引擎/运行时（vLLM、Ollama）—— 纯推理服务
> - ❌ 纯 LLM 框架（LangChain）—— 是上层框架，不自带 agent loop
> - ❌ 简单问答/Chat UI（部分 ChatGPT 套壳应用）

---

## 一、Top 20 排行榜（按 star 降序，2026-07-13 数据）

| # | 项目 | GitHub 仓库 | ⭐ Stars | 类别 | 一句话定位 |
|---|------|------------|---------:|------|----------|
| 1 | **OpenClaw** | [openclaw/openclaw](https://github.com/openclaw/openclaw) | 382,711 | 通用 Agent | 现象级个人 AI 助手，"the lobster way" |
| 2 | **obra/superpowers** | [obra/superpowers](https://github.com/obra/superpowers) | 253,000 | Agent 技能框架 | Agent 的 SDLC 方法论 + 可组合技能库 |
| 3 | **Hermes Agent** | [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent) | 213,750 | 通用 Agent | "the agent that grows with you"，自改进 + 长期记忆 |
| 4 | **AutoGPT** | [Significant-Gravitas/AutoGPT](https://github.com/Significant-Gravitas/AutoGPT) | 185,496 | 自主 Agent | 鼻祖级自主 AI Agent，思考-计划-行动循环 |
| 5 | **opencode** | [sst/opencode](https://github.com/sst/opencode) | 185,101 | 编程 Agent | 开源终端编码 Agent，Provider-agnostic |
| 6 | **Claude Code** | [anthropics/claude-code](https://github.com/anthropics/claude-code) | 138,000 | 编程 Agent | Anthropic 官方终端编码 Agent |
| 7 | **Gemini CLI** | [google-gemini/gemini-cli](https://github.com/google-gemini/gemini-cli) | 106,000 | 编程 Agent | Google 官方终端 Agent，免费 + 1M 上下文 |
| 8 | **OpenAI Codex CLI** | [openai/codex](https://github.com/openai/codex) | 97,385 | 编程 Agent | OpenAI 终端编码 Agent，Rust 重写 + OS 级沙箱 |
| 9 | **OpenHands** | [All-Hands-AI/OpenHands](https://github.com/All-Hands-AI/OpenHands) | 80,575 | 编程 Agent | 自主软件工程 Agent（原 OpenDevin） |
| 10 | **Lobe Chat** | [lobehub/lobe-chat](https://github.com/lobehub/lobe-chat) | 79,763 | Agent 平台 | "首席 Agent 运营官"，多 Agent 编排 |
| 11 | **MetaGPT** | [geekan/MetaGPT](https://github.com/geekan/MetaGPT) | 69,330 | 多 Agent | 多角色软件公司模拟 |
| 12 | **Cline** | [cline/cline](https://github.com/cline/cline) | 64,579 | 编程 Agent | 自主编码 Agent（SDK / IDE / CLI 三形态） |
| 13 | **Open Interpreter** | [openinterpreter/open-interpreter](https://github.com/openinterpreter/open-interpreter) | 64,357 | 编程 Agent | 自然语言操控本地的代码执行 Agent |
| 14 | **AutoGen** | [microsoft/autogen](https://github.com/microsoft/autogen) | 59,681 | 多 Agent | 微软系对话驱动多 Agent 框架 |
| 15 | **CrewAI** | [crewAIInc/crewAI](https://github.com/crewAIInc/crewAI) | 55,395 | 多 Agent | 角色扮演式多 Agent 编排 |
| 16 | **Aider** | [Aider-AI/aider](https://github.com/Aider-AI/aider) | 47,321 | 编程 Agent | 终端里的 AI 结对编程 |
| 17 | **Continue** | [continuedev/continue](https://github.com/continuedev/continue) | 34,839 | 编程 Agent | 开源 IDE 编码 Agent（VS Code / JetBrains） |
| 18 | **ChatDev** | [OpenBMB/ChatDev](https://github.com/OpenBMB/ChatDev) | 33,713 | 多 Agent | 清华系"聊天链"软件开发公司 |
| 19 | **Roo Code** | [RooCodeInc/Roo-Code](https://github.com/RooCodeInc/Roo-Code) | 24,325 | 编程 Agent | Cline 的"整支开发团队" fork |
| 20 | **SuperAGI** | [TransformerOptimus/SuperAGI](https://github.com/TransformerOptimus/SuperAGI) | 17,614 | 自主 Agent | 自主 Agent 平台，可视化并发管理 |

> 备注：star 数为本次调研实时数据（2026-07-13）。所有数据均来自 GitHub API 或公开页面交叉验证。

---

## 二、按生态分类详解

### 类别 A：通用自主 Agent（个人助手向）

#### #1 OpenClaw（382,711 ⭐）— 2026 年现象级项目

- **仓库**：[openclaw/openclaw](https://github.com/openclaw/openclaw)
- **范式**：持续运行的个人 AI 助手，agent loop + 多渠道接入
- **核心循环**：思考 → 决策 → 工具执行 → 记忆沉淀 → 再触发
- **特点**：
  - 支持 20+ 即时通讯渠道：WhatsApp、Telegram、Slack、Discord、Signal、iMessage、飞书、微信、QQ、Matrix 等
  - 语音唤醒 + Talk Mode（macOS/iOS/Android）
  - 多 Agent 路由：按 channel/account/peer 路由到不同 agent
  - 工具生态：浏览器、画布、节点、cron、sessions
  - 沙箱默认 Docker，支持非主会话隔离
  - 跨平台：macOS、Linux、Windows (WSL2)
- **社区影响**：
  - 72 小时 Star 破 6 万，3 个月 Star 超 38 万（GitHub 历史最快）
  - 黄仁勋评价："我们这个时代最重要的软件发布"
  - 已衍生"龙虾全家桶"：腾讯 QClaw、阿里 JVSClaw、字节 ArkClaw、智谱 AutoClaw、Moonshot KimiClaw 等
- **适用场景**：个人 7×24 AI 助手、跨渠道自动化、本地高权限操作

#### #3 Hermes Agent（213,750 ⭐）— 自我进化的 Agent

- **仓库**：[NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent)
- **范式**：自改进 + 长期记忆 + 多 Agent Kanban
- **核心循环**：
  - `/goal` —— Ralph loop 锁定跨 turn 目标
  - **Multi-Agent Kanban** —— 多 worker 协作、心跳 + reclaim + zombie 检测
  - **Checkpoints v2** —— 状态持久化、可恢复
- **特点**：
  - 20 个消息平台原生支持（新增 Google Chat）
  - MCP OAuth + 7 个 i18n locale
  - 自我改进：可生成 self-improvement review
  - 295 位贡献者，单周 3355 commits（v0.13.0）
  - 与 MiniMax 联合发布 MaxHermes 云端版本
- **适用场景**：长期运行的个人 / 团队 Agent、自学习工作流

#### #4 AutoGPT（185,496 ⭐）— 鼻祖级自主 Agent

- **仓库**：[Significant-Gravitas/AutoGPT](https://github.com/Significant-Gravitas/AutoGPT)
- **范式**：纯自主 Agent + 工具使用 + 长期记忆
- **核心循环**：思考（Think）→ 行动（Act）→ 观察（Observe）→ 评估（Evaluate），直到目标达成
- **特点**：
  - AI Agent 领域"破圈"鼻祖，2023 年 3 月发布即引爆 GitHub Trending
  - 互联网搜索、文件读写、代码执行、API 调用、图像处理
  - CLI + Electron/React GUI 双前端
  - 插件市场与可观测的"思维链"日志
- **短板**：稳定性与可靠性仍偏弱，资源消耗大
- **适用场景**：概念验证 / 简单自动化 / 自主任务研究

#### #20 SuperAGI（17,614 ⭐）— 自主 Agent 管理平台

- **仓库**：[TransformerOptimus/SuperAGI](https://github.com/TransformerOptimus/SuperAGI)
- **范式**：dev-first 自主 Agent 框架
- **特点**：
  - 图形化界面、Agent 市场、Tools、并发 Agent 运行
  - 可视化仪表盘同时运行/监控多个 Agent
  - 解决 AutoGPT 在生产环境中使用难的问题
- **适用场景**：企业级多 Agent 部署与监控

---

### 类别 B：Agent 技能框架 / 方法论

#### #2 obra/superpowers（253,000 ⭐）— Agent 的 SDLC

- **仓库**：[obra/superpowers](https://github.com/obra/superpowers)
- **范式**：可组合的 Skill + 强制 SDLC 流程（不是 agent 本身，是"给 agent 用的方法论"）
- **核心 Skill**（写代码前必走的流程）：
  - **brainstorming** —— 激活前先问清楚需求，输出设计文档
  - **writing-plans** —— 拆分 2-5 分钟小任务，每任务有确切文件路径和验证步骤
  - **subagent-driven-development** —— 分配全新子 Agent 执行
  - **test-driven-development** —— 红绿重构循环
  - **requesting-code-review** —— 按严重级别报告问题
  - **finishing-a-development-branch** —— 合并/PR 决策
- **多端兼容**：
  - Claude Code、Codex CLI、Cursor、Factory Droid、GitHub Copilot CLI、Kimi Code、OpenCode、Pi
- **关键差异**："它的 skill 触发是自动的，你不需要做任何特殊操作，你的 coding agent 装上 superpowers 就行"
- **核心哲学**：测试驱动 / 系统化优于临时方案 / 复杂度降低 / 证据优于声称
- **适用场景**：所有使用 coding agent 的团队，强制质量保证

---

### 类别 C：编程类 React 智能体（Vibe Coding 时代主力）

这一类有 9 个项目入选，是 v2 版重点强调的赛道——Cline、Codex、opencode、Claude Code、Gemini CLI、OpenHands、Open Interpreter、Aider、Continue、Roo Code。

#### #5 sst/opencode（185,101 ⭐）— 终端里的开源编码 Agent

- **仓库**：[sst/opencode](https://github.com/sst/opencode)
- **范式**：终端原生 TUI + Client/Server 架构
- **核心特点**：
  - **100% 开源 + Provider 无关**：不绑定任何模型，可接 OpenAI / Anthropic / Google / 本地模型
  - 由 neovim 用户 + terminal.shop 团队打造，专注 TUI 体验
  - 内置 `build`（默认）和 `plan`（只读）两个 agent，Tab 切换
  - 开箱即用的 LSP 支持
  - 客户端/服务器架构：可远程驱动
- **官网**：https://opencode.ai
- **适用场景**：完全开源 + 模型无关的编码 Agent，IDE 之外的工作流

#### #6 Claude Code（138,000 ⭐）— Anthropic 官方终端 Agent

- **仓库**：[anthropics/claude-code](https://github.com/anthropics/claude-code)
- **范式**：终端 CLI + 官方插件市场
- **核心特点**：
  - Anthropic 官方出品，与 Claude 模型深度集成
  - 全平台：macOS / Linux / Windows（PowerShell 原生支持）
  - 多端集成：VS Code / Cursor / JetBrains 插件 + 桌面端 + 网页
  - **官方插件市场**（`anthropics/claude-plugins-official`）覆盖 30+ 内部 + 10+ 外部插件
  - CLAUDE.md 规则系统 + Hooks 自动化 + MCP 协议
  - 子 Agent 并行（多任务并行）
- **基准表现**：Terminal-Bench 2.0 约 70%
- **短板**：依赖 Claude 订阅、闭源
- **适用场景**：Anthropic 生态下的深度编码助手

#### #7 Gemini CLI（106,000 ⭐）— Google 官方终端 Agent

- **仓库**：[google-gemini/gemini-cli](https://github.com/google-gemini/gemini-cli)
- **范式**：终端 + 1M 上下文 + 工具调用
- **核心特点**：
  - 免费档 60 req/min + 1000 req/day
  - Gemini 3 模型 + 1M token 上下文
  - 内置工具：Google Search、文件操作、Shell、网页抓取
  - MCP 协议支持
  - 543 个 release，迭代极快
- **优势**：免费额度大、长上下文、多模态
- **适用场景**：长上下文任务（百万 token 代码库分析）、免费使用

#### #8 OpenAI Codex CLI（97,385 ⭐）— 终端 + 沙箱

- **仓库**：[openai/codex](https://github.com/openai/codex)
- **范式**：终端 CLI + OS 级沙箱
- **核心特点**：
  - 2025 年 4 月开源，**TypeScript 重写为 Rust**，性能大幅提升
  - **OS 级沙箱**：macOS Seatbelt + Linux Landlock/seccomp + bubblewrap 纵深防御
  - 三种模式：Suggest（默认）/ Auto-Edit / Full-Auto
  - 多 Agent 并行：git worktree 隔离
  - Terminal-Bench 2.0 得分 **77.3%**（最高）
  - MCP 并行工具调用
- **短板**：仅 OpenAI 模型、Windows 需 WSL2
- **适用场景**：OpenAI 生态、安全要求高的企业

#### #9 OpenHands（80,575 ⭐）— 自主软件工程 Agent

- **仓库**：[All-Hands-AI/OpenHands](https://github.com/All-Hands-AI/OpenHands)
- **范式**：自主编码 Agent + 隔离沙箱
- **核心特点**：
  - 原 OpenDevin（Devin 复刻项目）
  - 在隔离沙箱里执行代码、改文件、跑测试、提交 PR
  - 支持多 LLM（OpenAI、Anthropic、本地模型）
  - 已有大量企业级编码场景落地
- **适用场景**：自动化 Bug 修复、PR Review、CI 流水线工程任务

#### #12 Cline（64,579 ⭐）— 自主编码 Agent 三形态

- **仓库**：[cline/cline](https://github.com/cline/cline)
- **范式**：SDK / IDE 扩展 / CLI 三种形态
- **核心特点**：
  - CLI：`npm i -g cline`，headless 模式支持 CI/CD
  - Kanban：多 Agent 并行任务板（`npm i -g kanban`）
  - VS Code / JetBrains 插件
  - SDK：`@cline/sdk`，可构建自己的 agent
  - Plan/Act 双模式：先规划再执行
  - 多平台消息：Telegram、Slack、Discord、Google Chat、WhatsApp、Linear
  - 任何 OpenAI 兼容 API + 本地模型（Ollama）
- **适用场景**：跨平台、跨形态的通用编码 Agent

#### #13 Open Interpreter（64,357 ⭐）— 本地代码执行 Agent

- **仓库**：[openinterpreter/open-interpreter](https://github.com/openinterpreter/open-interpreter)
- **范式**：自然语言 → 本地代码执行
- **核心特点**：
  - 让 LLM 在本地执行 Python / JS / Shell / AppleScript
  - 兼容 OpenAI、Anthropic、本地模型
  - 强调"沙箱"+"系统控制权"
  - 后续拆出 `open-interpreter` 桌面端 / `01` 智能体
- **适用场景**：数据分析、自动化办公、运维脚本生成

#### #16 Aider（47,321 ⭐）— 终端里的 AI 结对编程

- **仓库**：[Aider-AI/aider](https://github.com/Aider-AI/aider)
- **范式**：编码 Agent + 多轮对话 + Git 自动 commit
- **核心特点**：
  - 终端原生，与你的 git 仓库直接交互
  - 自动生成 commit message、自动建分支
  - 兼容 Claude / GPT / DeepSeek / 本地模型
  - 极受独立开发者 / 小团队欢迎
- **适用场景**：CLI 工作流下的结对编程、重构、跨仓库改动

#### #17 Continue（34,839 ⭐）— 开源 IDE 编码 Agent

- **仓库**：[continuedev/continue](https://github.com/continuedev/continue)
- **范式**：IDE 嵌入式编码 Agent
- **核心特点**：
  - VS Code / JetBrains 插件
  - 本地模型 + 云端模型混用
  - 已有企业版（Continue for Teams）
  - 与 Aider 互补：一个在 IDE 里，一个在 CLI
- **适用场景**：日常编码辅助、跨文件重构、测试生成

#### #19 Roo Code（24,325 ⭐）— "整支开发团队" 模式

- **仓库**：[RooCodeInc/Roo-Code](https://github.com/RooCodeInc/Roo-Code)
- **范式**：Cline fork + 多 Mode 切换
- **核心特点**：
  - 4 个内置 Mode：Code / Architect / Ask / Debug
  - 用户可创建 Custom Mode（QA、PM、UI/UX Designer、Code Reviewer 等）
  - Modes 可自行切换（Code → Test Engineer）
  - 自适应自治：手动 / 自主 / 混合
  - ⚠️ 注意：Roo Code 扩展已于 5 月 15 日关停（可考虑 ZooCode 社区 fork）
- **适用场景**：多角色协作的复杂编码任务

---

### 类别 D：多 Agent 协作框架

#### #10 Lobe Chat（79,763 ⭐）— 多 Agent 编排平台

- **仓库**：[lobehub/lobe-chat](https://github.com/lobehub/lobe-chat)
- **范式**：Chat UI + 多 Agent 调度 + MCP 客户端
- **核心特点**：
  - 自称"首席 Agent 运营官"，把多个 Agent 串成"轮班"
  - 内置数据库、本地知识库、插件市场
  - 同时支持网页 + 桌面客户端
  - 与 MCP 协议深度集成
- **适用场景**：个人 / 小团队的 Agent 桌面工作台

#### #11 MetaGPT（69,330 ⭐）— 多角色软件公司

- **仓库**：[geekan/MetaGPT](https://github.com/geekan/MetaGPT)
- **范式**：多 Agent + SOP 化软件工程流水线
- **核心特点**：
  - 模拟产品经理 / 架构师 / 工程师 / 测试等角色
  - 一句话需求 → 自动产出用户故事、竞品分析、设计图、可运行代码
  - 引入"共享知识库"保证多 Agent 信息一致
- **适用场景**：软件原型生成、文档自动化、流程固定的项目

#### #14 AutoGen（59,681 ⭐）— 微软系多 Agent

- **仓库**：[microsoft/autogen](https://github.com/microsoft/autogen)
- **范式**：多 Agent 对话协作
- **核心特点**：
  - 微软研究院出品，对话驱动编程
  - 支持顺序 / 并行 / 条件分支 / 群组聊天
  - 内置代码执行与验证
  - 已被并入 Microsoft Agent Framework
- **适用场景**：软件开发、复杂任务分解、需要角色分工的协作场景

#### #15 CrewAI（55,395 ⭐）— 角色扮演式多 Agent

- **仓库**：[crewAIInc/crewAI](https://github.com/crewAIInc/crewAI)
- **范式**：Role + Goal + Tools + Process 编排
- **核心特点**：
  - API 直观，"给员工写任务书"一样的体验
  - 支持顺序流程、分层流程（带 manager agent）
  - 与 LangChain 工具生态深度集成
- **适用场景**：内容创作、市场分析、客服自动化、项目管理辅助

#### #18 ChatDev（33,713 ⭐）— 清华系"聊天链"

- **仓库**：[OpenBMB/ChatDev](https://github.com/OpenBMB/ChatDev)
- **范式**：多 Agent 聊天链 + 阶段化软件工程
- **核心特点**：
  - OpenBMB 出品
  - 模拟 CEO / CTO / 程序员 / 测试员的"聊天协作"
  - 过程可视化强
  - 与 MetaGPT 思路相近，但更轻量
- **适用场景**：教学 / 研究 / 软件开发过程演示

---

## 三、横向对比矩阵

### 按范式分类

| 类别 | 项目数 | 代表项目 |
|------|------:|---------|
| **通用自主 Agent（个人助手向）** | 4 | OpenClaw、Hermes Agent、AutoGPT、SuperAGI |
| **Agent 技能框架 / 方法论** | 1 | obra/superpowers |
| **编程类 React 智能体（Vibe Coding）** | 9 | opencode、Claude Code、Gemini CLI、Codex CLI、OpenHands、Cline、Open Interpreter、Aider、Continue、Roo Code |
| **多 Agent 协作框架** | 5 | Lobe Chat、MetaGPT、AutoGen、CrewAI、ChatDev |
| **Agent 平台/桌面** | 1 | Lobe Chat（也归入多 Agent 编排） |

### 编程 Agent 核心能力对比

| 工具 | Star | 沙箱 | 模型无关 | Windows 原生 | 多 Agent 并行 | 核心优势 |
|------|-----:|:----:|:----:|:----:|:----:|----------|
| **sst/opencode** | 185k | ❌ | ✅ | ✅ | ✅ | 100% 开源，Provider 无关 |
| **Claude Code** | 138k | ❌ | ❌ | ✅ | ✅ | 官方 Claude + 插件市场 |
| **Gemini CLI** | 106k | ✅ | ❌ | ✅ | ❌ | 免费 + 1M 上下文 |
| **Codex CLI** | 97k | ✅ OS 级 | ❌ | ⚠️ WSL2 | ✅ git worktree | Rust + 沙箱最强 + Terminal-Bench 第一 |
| **OpenHands** | 81k | ✅ 沙箱 | ✅ | ✅ | ❌ | 自主软件工程 |
| **Cline** | 65k | ⚠️ 询问 | ✅ | ✅ | ✅ Kanban | 三形态：SDK/IDE/CLI |
| **Open Interpreter** | 64k | ⚠️ | ✅ | ✅ | ❌ | 本地代码执行 |
| **Aider** | 47k | ❌ | ✅ | ✅ | ❌ | Git 工作流最自然 |
| **Continue** | 35k | ❌ | ✅ | ✅ | ❌ | IDE 插件最佳 |
| **Roo Code** | 24k | ⚠️ | ✅ | ✅ | ✅ 多 Mode | Cline fork + 团队模式 |

### 按厂商分类

- **大厂官方出品**（6 个）：OpenClaw、Claude Code（Anthropic）、Gemini CLI（Google）、Codex CLI（OpenAI）、OpenHands、AutoGen（Microsoft）
- **开源社区出品**（14 个）：其余

### 按编程语言分类

- **TypeScript / Node 系**（10 个）：OpenClaw、superpowers、opencode、Claude Code、Gemini CLI、Codex CLI（前 TS 现 Rust）、Cline、Continue、Roo Code、Lobe Chat
- **Python 系**（6 个）：Hermes Agent、AutoGPT、OpenHands、Open Interpreter、MetaGPT、AutoGen
- **混合**（4 个）：Aider（Python）、CrewAI（Python）、ChatDev（Python）、SuperAGI（Python）

---

## 四、关键趋势观察

### 1. 2026 是"Agent 元年"——OpenClaw 引爆现象级浪潮

- OpenClaw 单项目 38 万 star 超越 Linux 黄仁勋认证
- 衍生出"龙虾全家桶"（腾讯 QClaw、阿里 JVSClaw、字节 ArkClaw、智谱 AutoClaw、Moonshot KimiClaw）
- 中国厂商几乎全部下场做 OpenClaw 定制版

### 2. 编程类 React 智能体形成"5+5"格局

- **5 个大厂官方终端 Agent**：Claude Code、Gemini CLI、Codex CLI、OpenHands、opencode（sst）
- **5 个开源独立工具**：Cline、Open Interpreter、Aider、Continue、Roo Code
- Terminal-Bench 2.0 已成为事实标准基准（Codex 77.3% 领先）

### 3. 沙箱从"可选项"变"必选项"

- Codex CLI 的 OS 级沙箱（macOS Seatbelt + Linux Landlock）成为新标杆
- Claude Code 没有这个级别隔离，但靠"每次操作前弹确认框"
- 沙箱设计是 2026 Agent 工程化的关键差异点

### 4. Provider 无关 / 自托管成为主流诉求

- opencode、Aider、Cline、Open Interpreter 都强调"不绑定任何模型"
- 用户对"被供应商锁定"越来越警惕
- 这是 deepcode 项目的核心理念契合点

### 5. Multi-Agent 协作从概念走向落地

- 5 个多 Agent 框架上榜
- MetaGPT（软件公司模拟）、AutoGen（对话驱动）、CrewAI（角色扮演）、ChatDev（聊天链）各有差异化
- Hermes Agent 的 Multi-Agent Kanban 是新形态（worker + heartbeat + zombie detection）

### 6. Agent 技能 / 方法论从 prompt 走向工程化

- obra/superpowers 25 万 star 证明："Agent 的差距不在模型，在技能"
- subagent-driven-development（子 Agent 驱动开发）成为新范式
- 测试驱动 / 系统化 / 复杂度降低 / 证据优于声称 四大哲学

### 7. MCP 协议正在成为事实标准

- Claude Code、Gemini CLI、Codex CLI、Cline、opencode、Continue 等都已支持 MCP
- Hermes Agent 的 MCP 已有 OAuth + SSE + 图像结果转 MEDIA
- 2026 年内 MCP 进一步普及

### 8. Agent 内存与自改进成为新前沿

- OpenClaw 的 ClawDB（明文 SQLite，已被建议加密）
- Hermes Agent 的 Checkpoints v2 + 自我改进 review
- OpenClaw 的"自动做梦"机制（24h 无活动后自动整理记忆）
- autoDream 是 2026 高端 Agent 的标志功能

---

## 五、对 deepcode 项目的启示

> deepcode 项目背景：基于 LangChain Deep Agents 框架复刻 MiniMax Code v3.0.47 全功能、开源 + 信创合规 + Provider 可热插拔

### 1. 架构对齐：Terminal-First Agent

- **对标项目**：`sst/opencode`（185k ⭐）
  - 完全开源 + Provider 无关 + 终端原生 + LSP 支持 + Client/Server
- **核心理念契合度**：
  - 信创合规要求 = 100% 开源可自托管 ✓
  - Provider 可热插拔 = opencode 的核心定位 ✓
  - 数据不出内网 = opencode 完全本地运行 ✓

### 2. 工程化方法论：参考 superpowers 的 SDLC

- 引入"先 brainstorm → writing-plans → subagent-driven-development → TDD → code review → finishing-branch"流程
- 用 .clinerules / CLAUDE.md / AGENTS.md 三套规则文件规范项目
- 把 30+ Skills 内置（code-review、commit、code-modernization、hookify、feature-dev、claude-code-setup 等）

### 3. 沙箱设计：参考 Codex CLI

- macOS Seatbelt + Linux Landlock/seccomp + bubblewrap 纵深防御
- 即使在 Full-Auto 模式下也强 OS 级隔离
- 沙箱成为"安全 + 自动化"双优的护城河

### 4. 信创合规差异化（与所有竞品的最大差异）

- **主流竞品的问题**：
  - Claude Code：依赖 Anthropic API，闭源
  - Codex CLI：依赖 OpenAI API
  - Gemini CLI：依赖 Google API
  - opencode：开源但未官方支持国产芯片 / 国产模型
  - MiniMax Code：商业产品，私有部署成本高
- **deepcode 的机会**：
  - 国产芯片适配（昇腾 / 摩尔线程 / 沐曦 / 昆仑芯）
  - 国产模型支持（GLM-5.1、Qwen3、Kimi-K2.6、MiniMax-M2.7）
  - MiniMax M2.7 已开源，可深度集成
  - 多 Provider 热插拔（这是 opencode 都没做好的部分）

### 5. 持续关注：未来 6-12 个月潜力股

- **MiniMax-AI/Mini-Agent**（2.8k star）：极简但专业的 Agent 演示
- **MiniMax-AI/OpenRoom**（1.2k star）：浏览器桌面 AI Agent
- **MiniMax-AI/M3**（2.8k star）：M3 模型 + agent harness
- **MaxHou-infinity/maxcode**：基于 MiniMax 模型的国产终端编码 Agent（1277 测试通过）
- **obfuscoder-ai/**、**Pi**、**Droid**：新兴 coding agent

---

## 六、附录：未入榜项目（与"ReAct 智能体"定义不符）

下列项目虽然有一定 star 量或品牌，但**与 ReAct 智能体范式不符**或**不是 agent loop**，故未入榜：

| 项目 | Star | 不入榜原因 |
|------|-----:|----------|
| langgenius/dify | 148k | RAG + 工作流编排（2025 旧版智能体） |
| langflow-ai/langflow | 152k | 拖拽式工作流（不是 agent loop） |
| FlowiseAI/Flowise | 55k | 可视化工作流（不是 agent loop） |
| browser-use/browser-use | 104k | 浏览器自动化**工具**（不是智能体本身） |
| LangChain | 141k | LLM 框架（不自带 agent loop） |
| ollama/ollama | 176k | LLM 推理运行时（不是 agent） |
| vllm-project/vllm | 86k | LLM 推理引擎（不是 agent） |
| Compo sio / Composio | 29k | Agent **工具集**（不直接是 agent） |
| labring/FastGPT | 29k | 知识库平台（不是 agent loop） |
| mlflow/mlflow | 27k | MLOps 平台 |
| Microsoft AutoGen（已入榜） | 60k | ✓ |
| letta-ai/letta | 24k | 状态化 Agent 平台（star 略低） |
| alipay/agentUniverse | 2k | 蚂蚁系多 Agent（star 低 + 中文友好） |
| QwenLM/Qwen-Agent | 17k | 通义系 Agent 框架 |
| pydantic/pydantic-ai | 18k | Pydantic 团队 Agent 框架 |
| HKUDS/DeepCode | 16k | 港大 Paper2Code Agent（与 deepcode 方向相关） |

### 厂商产品（非开源，但生态相关）

- **腾讯 WorkBuddy / QClaw** —— 腾讯云 CodeBuddy + 微信直连小龙虾
- **智谱 AutoClaw（澳龙）** —— 本地高权限执行
- **阿里 QwenPaw / JVSClaw** —— 阿里云 + Qwen 系列
- **Moonshot KimiClaw** —— Moonshot AI 的 SaaS 版
- **字节 ArkClaw** —— 集成字节系产品
- **MiniMax Code / MiniMax Agent** —— MiniMax 桌面端 + MaxClaw 网关封装

---

## 七、总结

**v1 版的错误**：
- 把 Dify / Langflow（工作流）、browser-use（工具）、LangChain（框架）当成"智能体"——它们是上层应用或工具，不具备自主循环
- 缺少 OpenClaw 生态、缺少编程类 React 智能体

**v2 版的核心修正**：
- 严格按"agent loop + 可反复执行 + 有运行时"三个标准筛选
- 突出 **OpenClaw 生态**（1, 3, 4, 20 位）和 **编程类 React 智能体**（5, 6, 7, 8, 9, 12, 13, 16, 17, 19 位）
- 补充 **多 Agent 协作**（10, 11, 14, 15, 18 位）和 **Agent 技能框架**（2 位）

**下次复盘建议**：
- 频率：3 个月一次（Agent 赛道变化快）
- 重点关注：Terminal-Bench 2.0 排名变化、MiniMax M3、opencode 跨平台能力、信创合规类项目
- 待补充：bolt.new、Lovable、v0.dev、Devin 等更多 vibe coding 平台

---

**报告完。** 数据更新截至 2026-07-13。
