# 我的提问
阅读harness/research/popular_agent_loop.md ，我想开发的React智能体，以质量第一，工具调用过程中指令正确，解析正确，返回正确。你帮我评估一下，哪一种工具调用方式能够达到最高的准确率？
我原先设想将工具列表放到系统提示词里，但是我害怕影响大模型调用工具的准确性，并且导致大模型把注意力都放到工具调用上，而不是解决用户任务。

# 二次提问
把以上你的判断结果写入harness/research/tool_accuracy.md中，然后重点介绍原生FC调用工具的全过程，为我今后的开发工作提供demo支持。


# 工具调用准确率评估与原生 FC 全过程 Demo

> 编写日期：2026-07-10
> 目的：为 ReAct 智能体（质量第一：指令正确、解析正确、返回正确）选定工具调用范式，并给出原生 FC 的完整落地 demo。
> 上游依据：`harness/research/popular_agent_loop.md`（10 个主流开源 Agent Loop 的横向调研）。

---

## 一、核心结论

**最高准确率方案：Provider 原生 Function Calling（走 `tools` 通道），不要把工具列表塞进系统提示词。**

行业已用脚投票——见上游报告「洞察 5」：框架越新，越倾向把工具定义从系统提示词剥离到原生 `tools` 通道。Cline、AutoGen、DeepAgents 全部如此，系统提示词只保留「你是谁 + 行为约束」。

### 六种范式准确率排序（源自上游报告 B 表）

| 范式 | 准确率 | 关键原因 | 代表框架 |
|---|---|---|---|
| **Provider 原生 FC** | 最高 | 模型专门训练过 + provider 侧约束解码（grammar-constrained）+ schema 强校验 + 解析几乎零正则 | Cline, AutoGen, DeepAgents, Letta(现代), OpenHands(原生) |
| 自定义 XML（`<function=>`） | 次高 | 比 ReAct 严格，适合约束输出；但模型要先学会这套 schema | OpenHands(非原生), Letta(legacy) |
| ReAct 文本 | 中 | 任何 chat 模型可用，但解析靠一堆正则，`Action:`/`Action Input:` 易错 | CrewAI(默认) |
| Markdown 代码块 | 中低 | 内容与控制信令混在一起，解析要很小心 | Open Interpreter, SWE-Agent(bash), Aider |
| Python 代码 | 高表达力但工程重 | 需 AST sandbox，不能跑 untrusted code | Smolagents(CodeAgent) |
| 纯 JSON | 低 | 模型输出 JSON 易截断/语法错 | SWE-Agent(JsonParser) |

---

## 二、澄清一个关键误解：「工具进系统提示词会分散注意力」

这里其实是两件事混在一起：

1. **工具定义放哪（schema 的位置）**
   走原生 FC 时，schema 依然会发给模型，只是放在一个**模型被训练识别为「可用工具」的结构化槽位**里，而不是当成「现在必须执行的指令文本」。原生 FC 的优势不只是「不占系统提示词」，更是**模型对这块内容的处理模式不同** + provider 侧有约束解码兜底。这才是准确率差距的真正来源。

2. **系统提示词怎么写（行为诱导）**
   真正让模型「过度调用工具」的，往往不是工具列表本身，而是像 Cline 那句
   `IMPORTANT: Always includes tool calls until the task is completed`
   这种硬性诱导。这个完全可控——把系统提示词聚焦在角色和约束上，别写「每轮都必须调工具」。

**结论：原生 FC 通道 + 干净的系统提示词，注意力稀释问题基本消解。**

---

## 三、双轨设计（对信创/Provider 热插拔场景必需）

上游报告「洞察 1」：**所有**主流框架都是双轨，按模型能力自动切换。信创环境里的国产/本地模型很多原生 FC 支持不完整甚至没有，纯原生 FC 会在关键场景翻车。

推荐架构：

```
                    ┌─ supports_function_calling() == True
   能力检测 ────────┤     └─→ 主路径：原生 FC（tools 通道）          ← 本文档重点
                    │
                    └─ False
                          └─→ 降级路径：XML DSL（学 OpenHands <function=>）
                                （别用 ReAct——XML 更严格，解析错误率更低）
```

- **主路径**：`supports_function_calling()` → 原生 FC
- **降级路径**：不支持 FC 的模型 → **XML DSL**（`<function=NAME><parameter=K>V</parameter></function>`），不用 ReAct

---

## 四、原生 FC 调用工具的全过程

一次完整的原生 FC 调用横跨 6 个阶段，构成 Agent Loop 的一圈：

```
① 定义工具 schema           (开发期：Python 函数 → JSON Schema)
        │
② 组装请求                   (system prompt + messages + tools=[...])
        │
③ 模型返回 tool_calls        (assistant message，content 可能为 null)
        │
④ 解析 + 校验参数            (JSON.parse → schema 校验 → 兜底修复)
        │
⑤ 执行工具                   (dispatch by name → 捕获异常)
        │
⑥ 结果回传                   (role:"tool" + tool_call_id + is_error)
        │
        └──→ 回到 ②，直到模型返回「空 tool_calls」= 任务完成（终止信号）
```

### 阶段①：定义工具 schema

原生 FC 的工具是一个 JSON Schema 对象，OpenAI 兼容格式：

```json
{
  "type": "function",
  "function": {
    "name": "read_file",
    "description": "Read a file from the local filesystem. Returns file content as text.",
    "parameters": {
      "type": "object",
      "properties": {
        "path": { "type": "string", "description": "Absolute path to the file." },
        "start_line": { "type": "integer", "description": "1-indexed start line.", "default": 1 }
      },
      "required": ["path"]
    }
  }
}
```

要点：
- `description` 是模型选工具的唯一依据——写清楚「做什么 + 返回什么」，别省。
- `required` 要准确；provider 的约束解码会据此强制参数出现。
- 支持 `"strict": true`（OpenAI）时开启，强制 schema 一致性，进一步降低参数幻觉。

### 阶段②：组装请求

```python
resp = client.chat.completions.create(
    model=model,
    messages=[{"role": "system", "content": SYSTEM_PROMPT}, *history],
    tools=tools,              # ← 工具走这里，不进 system prompt
    tool_choice="auto",       # auto / required / none / {"type":"function",...}
)
```

`tool_choice` 语义：
- `"auto"`（默认）：模型自己决定调不调工具——**质量第一场景推荐**。
- `"required"`：强制至少调一个工具（谨慎用，会诱导过度调用）。
- `"none"`：禁止调工具（用于最终总结那一轮）。

### 阶段③：模型返回 tool_calls

assistant message 结构（`content` 常为 `null`，`tool_calls` 是数组，可并行多个）：

```json
{
  "role": "assistant",
  "content": null,
  "tool_calls": [
    {
      "id": "call_abc123",
      "type": "function",
      "function": { "name": "read_file", "arguments": "{\"path\": \"/etc/hosts\"}" }
    }
  ]
}
```

注意：`arguments` 是 **JSON 字符串**，不是对象——必须自己 parse。

### 阶段④：解析 + 校验参数（准确率关键防线）

多层兜底（学 Cline / Letta）：

1. `json.loads(arguments)` —— 正常路径
2. 失败 → `jsonrepair` / 补全截断括号（`+ "}"` / `+ "\"}"`）
3. schema 校验（jsonschema），缺 required / 类型不符 → 生成明确错误
4. 工具名不存在 → 返回 `is_error=True` 的结果，让模型下轮自我修正
5. 仍失败 → 把错误文本回灌，限重试 3 次，防死循环

### 阶段⑤：执行工具

按 `name` dispatch 到实际函数，**必须捕获异常**——任何异常都转成 `is_error=True` 的结果回传，绝不让 loop 崩掉。

### 阶段⑥：结果回传（统一契约）

原生 FC 的结果一律用 `role:"tool"`，且 `tool_call_id` 必须与阶段③的 `id` 精确对应：

```json
{
  "role": "tool",
  "tool_call_id": "call_abc123",
  "name": "read_file",
  "content": "127.0.0.1 localhost\n..."
}
```

错误也要回传（不要静默吞）：

```json
{
  "role": "tool",
  "tool_call_id": "call_abc123",
  "name": "read_file",
  "content": "[ERROR] FileNotFoundError: /etc/hosts not found"
}
```

### 终止信号

模型返回 **空 tool_calls（纯文本回复）** = 任务完成，退出 loop。这是最自然的终止方式，别依赖 `Final Answer:` 文本标记。

---

## 五、可运行 Demo（Python / OpenAI 兼容 / 贴合 deepcode Provider 热插拔）

> 依赖：`pip install openai jsonschema json-repair`
> 兼容任何 OpenAI 协议端点（MiniMax / OpenAI / vLLM / Ollama 的 `/v1` 等），改 `base_url` + `api_key` 即可。

```python
"""
native_fc_demo.py — 原生 Function Calling 最小可用 Agent Loop
质量第一：schema 强校验 + 多层解析兜底 + 统一 role:"tool" 回传 + 空 tool_calls 终止。
"""
import json
import os
from typing import Any, Callable

from openai import OpenAI
from jsonschema import validate, ValidationError
from json_repair import repair_json

# ── Provider 热插拔：只改这两行即可切换 MiniMax / OpenAI / vLLM / Ollama ──
client = OpenAI(
    base_url=os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1"),
    api_key=os.environ.get("LLM_API_KEY", "sk-..."),
)
MODEL = os.environ.get("LLM_MODEL", "gpt-4o-mini")

SYSTEM_PROMPT = (
    "You are a coding assistant. Use the available tools to accomplish the "
    "user's task. When the task is complete, reply with a plain text answer "
    "and do not call any tool."
)  # ← 注意：不枚举工具、不写「必须调工具」，只描述角色与终止约定


# ═══════════════ ① 工具实现 + schema ═══════════════
def read_file(path: str, start_line: int = 1) -> str:
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    return "".join(lines[start_line - 1:])


def list_dir(path: str = ".") -> str:
    return "\n".join(sorted(os.listdir(path)))


# 每个工具 = (可调用函数, JSON Schema)
TOOLS: dict[str, tuple[Callable, dict]] = {
    "read_file": (
        read_file,
        {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to the file."},
                "start_line": {"type": "integer", "description": "1-indexed start line.", "default": 1},
            },
            "required": ["path"],
        },
    ),
    "list_dir": (
        list_dir,
        {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "Directory path.", "default": "."}},
            "required": [],
        },
    ),
}

TOOL_DESCRIPTIONS = {
    "read_file": "Read a file from local filesystem, returns text content.",
    "list_dir": "List entries under a directory.",
}


def build_tools_payload() -> list[dict]:
    """② 组装成 provider 的 tools=[...] 结构。"""
    return [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": TOOL_DESCRIPTIONS[name],
                "parameters": schema,
            },
        }
        for name, (_, schema) in TOOLS.items()
    ]


# ═══════════════ ④ 解析 + 校验（准确率关键防线）═══════════════
def parse_and_validate(name: str, raw_args: str) -> tuple[dict | None, str | None]:
    """返回 (args, error)。error 非 None 时表示解析/校验失败。"""
    if name not in TOOLS:
        return None, f"Unknown tool '{name}'. Available: {list(TOOLS)}"

    # 第 1 层：标准 JSON 解析
    try:
        args = json.loads(raw_args or "{}")
    except json.JSONDecodeError:
        # 第 2 层：json-repair 兜底（修复截断 / 单引号 / 缺闭合）
        try:
            args = json.loads(repair_json(raw_args))
        except Exception as e:
            return None, f"Arguments are not valid JSON even after repair: {e}"

    # 第 3 层：JSON Schema 强校验
    _, schema = TOOLS[name]
    try:
        validate(instance=args, schema=schema)
    except ValidationError as e:
        return None, f"Argument schema validation failed: {e.message}"

    return args, None


# ═══════════════ ⑤ 执行工具 ═══════════════
def execute_tool(name: str, args: dict) -> tuple[str, bool]:
    """返回 (content, is_error)。任何异常都转成 is_error=True。"""
    fn, _ = TOOLS[name]
    try:
        return str(fn(**args)), False
    except Exception as e:
        return f"[ERROR] {type(e).__name__}: {e}", True


# ═══════════════ Agent Loop ═══════════════
def run(user_task: str, max_iterations: int = 15) -> str:
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_task},
    ]
    tools_payload = build_tools_payload()

    for _ in range(max_iterations):
        # ② 组装请求
        resp = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=tools_payload,
            tool_choice="auto",
        )
        msg = resp.choices[0].message

        # ③ 无 tool_calls = 终止信号（任务完成）
        if not msg.tool_calls:
            return msg.content or ""

        # 把 assistant 的 tool_calls 消息压回历史（必须，否则 tool 结果无法关联）
        messages.append(
            {
                "role": "assistant",
                "content": msg.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in msg.tool_calls
                ],
            }
        )

        # 逐个处理 tool_call（原生 FC 支持并行多个）
        for tc in msg.tool_calls:
            name = tc.function.name
            args, err = parse_and_validate(name, tc.function.arguments)  # ④

            if err:
                content, is_error = err, True
            else:
                content, is_error = execute_tool(name, args)             # ⑤

            # ⑥ 统一 role:"tool" 回传，tool_call_id 精确对应
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": name,
                    "content": f"[ERROR] {content}" if is_error and not content.startswith("[ERROR]") else content,
                }
            )

    return "[loop terminated: max_iterations reached]"


if __name__ == "__main__":
    print(run("列出当前目录，然后读取其中的 README 文件的前 20 行"))
```

### Demo 里体现的「质量第一」设计点

| 关注点 | 落地做法 | 对应阶段 |
|---|---|---|
| 指令正确 | 工具走 `tools=[...]`，系统提示词不枚举工具、不写「必须调工具」 | ①② |
| 解析正确 | `json.loads` → `json-repair` → jsonschema 三层兜底 | ④ |
| 返回正确 | 统一 `role:"tool"` + `tool_call_id` 精确对应 + 错误也回传 | ⑥ |
| 不崩溃 | 工具执行全异常捕获转 `is_error` | ⑤ |
| 防死循环 | `max_iterations` + 空 tool_calls 自然终止 | Loop |

---

## 六、进一步的准确率杠杆（工程经验）

1. **工具数量本身就是杠杆**：超过 ~20 个工具，不管走哪个通道准确率都会掉。描述写清、参数别过度设计、必要时按场景分组只暴露子集。
2. **`tool_choice` 保持 `auto`**：`required` 会诱导过度调用，伤害「解决任务」而非「用工具」的目标。
3. **错误回灌胜过静默重试**：把校验/执行错误以 `role:"tool"` 回传，让模型自我修正（上游报告「洞察 4」的通用模式）。
4. **prompt caching**：工具 schema 稳定时放在稳定前缀，改动工具会击穿缓存——热插拔工具时注意分层。
5. **降级路径用 XML 不用 ReAct**：非 FC 模型走 `<function=>` DSL，解析错误率显著低于 ReAct。

---

## 参考

- 上游调研：`harness/research/popular_agent_loop.md`（洞察 1 / 4 / 5 是本结论的直接依据）
- OpenAI Function Calling 文档：https://platform.openai.com/docs/guides/function-calling
- 代表实现：Cline（`agent-runtime.ts`）、AutoGen（`_assistant_agent.py`）、DeepAgents（`graph.py` + `ToolNode`）
```
