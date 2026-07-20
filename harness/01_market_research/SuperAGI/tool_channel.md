# SuperAGI — 工具调用（Tool Channel）调研报告

> 对象:`TransformerOptimus/SuperAGI`(本地 clone 快照)
> 调研维度:工具来源 / 工具列表生成与传递 / 指令解析与错误修复 / 结果回传 / File Backend 适配

---

## 0. 智能体一句话定位

**dev-first 自主 Agent 平台**:`Toolkit + Tool` 分组 + DB 注册,带 Web 仪表盘 + 远程工具集市,支持并发多 Agent 运行 + 监控的 GUI/CLI 双形态企业级 ReAct 框架(来自 `top_20_react_agent.md` #20)。

---

## 1. 调研依据

**关键文件**:

| 类别 | 文件 | 作用 |
|-----|-----|-----|
| 协议 | `superagi/agent/prompts/superagi.txt` | **system prompt 嵌入工具列表**,要求 LLM 返回 `{thoughts, tool}` JSON |
| 协议 | `superagi/agent/prompts/agent_tool_input.txt` | 单 tool step 的 prompt 模板 |
| 协议 | `superagi/agent/output_parser.py:34-50` | `AgentSchemaOutputParser` 解析 LLM JSON 输出 |
| 协议 | `superagi/agent/agent_prompt_builder.py:36-58` | `add_tools_to_prompt()` 把工具列表拼成自然语言 + JSON Schema 文本 |
| 协议 | `superagi/agent/agent_message_builder.py:24-50` | LLM messages 构造,**无 `tools` 参数** |
| 执行 | `superagi/agent/tool_executor.py:22-52` | 工具执行 + 错误处理 + `retry` 标记 |
| 执行 | `superagi/agent/output_handler.py:33-49` | 写 `assistant_reply` + `tool_response` 到 `agent_execution_feed` 表 |
| 构建 | `superagi/agent/tool_builder.py:36-66` | `importlib` 动态加载 tool class(三层目录搜索) |
| 基类 | `superagi/tools/base_tool.py:78-93` | `BaseTool.args` 用 pydantic 反射生成 JSON Schema |
| 错误 | `superagi/helper/json_cleaner.py:6-89` | `clean_boolean` + `extract_json_section` + `balance_braces` |
| LLM | `superagi/llms/openai.py:84-91` | `chat_completion` — **不传 `tools=`** |
| LLM | `superagi/llms/local_llm.py:51-58` | local LLaMA + GBNF grammar 强制 JSON |
| 路径 | `config_template.yaml:24-28` | `RESOURCES_INPUT_ROOT_DIR: workspace/input/{agent_id}` 路径模板 |
| 路径 | `superagi/helper/resource_helper.py:75-87` | `get_formatted_agent_level_path` 字符串 replace |
| 数据 | `superagi/models/tool.py:14-25` | Tool ORM(name/folder_name/class_name/file_name/toolkit_id) |
| 数据 | `superagi/models/toolkit.py:13-25` | Toolkit ORM(name/description/organisation_id/tool_code_link) |

**文档**:`README.MD:79-85`(Toolkit + Marketplace 集市介绍);`README.MD:17`(`marketplace.superagi.com` 入口)。

---

## 2. 五个核心问题的回答

### Q1. 工具来源:内置 Toolkit + 集市 Toolkit(无 MCP / 无 Agent Skills)

**内置 Toolkit**(24 个,`superagi/tools/<toolkit>/`):

- **File** — Read/Write/Append/Delete/ListFile(`tools/file/file_toolkit.py:11-19`)
- **Code** — WriteCode / WriteSpec / WriteTest / ImproveCode(`tools/code/coding_toolkit.py`)
- **Email / GitHub / Jira / Google Calendar / Slack / Twitter / Instagram** — 平台集成
- **Search 系列** — Google / Serp / DuckDuckGo / SearXNG / Knowledge / Apollo
- **Image Generation** — DALL-E / StableDiffusion(`tools/image_generation/`)
- **Resource / Thinking** — QueryResource(RAG 检索) / ThinkingTool(结构化思考)
- **WebScraper** — 通用网页抓取
- **基类** `BaseTool`(`tools/base_tool.py:78-93`):继承 Pydantic `BaseModel`,通过 `args_schema` 反射或 `_execute` 函数签名自动生成 JSON Schema。

**MCP 支持**:**否**。`superagi/` 全局 grep `mcp|tool_use_id|tool_call_id` 完全无匹配。工具调度是**纯字符串匹配**:`tool_executor.py:30` `tools = {t.name.lower().replace(" ", ""): t for t in self.tools}`。

**Agent Skills 支持**:**否**。无 `.skills/` / `SKILL.md` / 任何渐进式披露痕迹。

**集市**:Python 模块级而非协议级——`helper/tool_helper.py:50-79` 从 GitHub `api.github.com/repos/{owner}/{repo}/zipball/{branch}` 拉 ZIP 解压到 `superagi/tools/marketplace_tools/`,然后 `register_marketplace_toolkits()` 写入 DB。需要**重启或 import 刷新**才能被新代码生效,无 MCP 那种"运行时零重启"动态性。

---

### Q2. 工具列表的生成、传递、格式

**核心结论:纯 prompt-as-tool(流派 A 原始形态)**,**不调 OpenAI `tools=` 参数**。

#### 2.1 工具列表生成:DB 查询 → prompt 字符串

`agent_iteration_step_handler.py:175-188`(`_build_tools`):
```python
agent_tools = [ThinkingTool()]
user_tools = self.session.query(Tool).filter(
    and_(Tool.id.in_(agent_execution_config["tools"]), Tool.file_name is not None)).all()
for tool in user_tools:
    agent_tools.append(tool_builder.build_tool(tool))
```

**Tool / Toolkit** 是双表 ORM(`models/tool.py` + `models/toolkit.py`)。Toolkit 是分组容器(带 `organisation_id` 多租户隔离),Tool 通过 `toolkit_id` 关联。

**动态加载**(`agent/tool_builder.py:36-66`):
```python
tool_paths = ["superagi/tools", "superagi/tools/external_tools", "superagi/tools/marketplace_tools"]
for tool_path in tool_paths:
    if os.path.exists(os.path.join(os.getcwd(), tool_path) + '/' + tool.folder_name):
        tools_dir = tool_path; break
module_name = ".".join(parsed_tools_dir.split("/") + [tool.folder_name, file_name])
module = importlib.import_module(module_name)
obj_class = getattr(module, tool.class_name)
new_object = obj_class()
```

#### 2.2 传递方式:**System Prompt 文本**(非 OpenAI `tools` 数组)

**关键证据 `superagi/llms/openai.py:84-91`**:
```python
response = openai.ChatCompletion.create(
    n=self.number_of_results, model=self.model, messages=messages,
    temperature=self.temperature, max_tokens=max_tokens,
    top_p=self.top_p, frequency_penalty=self.frequency_penalty,
    presence_penalty=self.presence_penalty
)
```
→ **不传 `tools` / `functions` / `tool_choice`**。LLaMA 本地后端亦然:`local_llm.py:51` `functions=None, function_call=None, ..., grammar=self.llm_grammar`。

#### 2.3 格式:工具描述嵌入 prompt 的 TOOLS 段

`agent_prompt_builder.py:36-56`:
```python
for i, item in enumerate(tools):
    final_string += f"{i + 1}. {cls._generate_tool_string(item)}\n"
finish_string = (f"{len(tools) + 1}. \"{FINISH_NAME}\": ...")

def _generate_tool_string(cls, tool: BaseTool) -> str:
    output = f"\"{tool.name}\": {tool.description}"
    output += f", args json schema: {json.dumps(tool.args)}"
    return output
```

`agent/prompts/superagi.txt:7-13` 模板:
```
TOOLS:
{tools}
...
Respond with only valid JSON conforming to the following schema:
{ "thoughts": { "text|reasoning|plan|criticism|speak": ... },
  "tool": { "name": "<tool name>", "args": { ... } } }
```

#### 2.4 prompt-as-tool? **是**。

✅ 工具列表 + args schema 全部塞 system prompt,LLM 须按 `{thoughts, tool}` JSON 输出。
❌ 不是 OpenAI function calling 或 Anthropic `tool_use` 块。

单 tool step 模板(`prompts/agent_tool_input.txt`,被 `agent_tool_step_handler.py:130-139` 使用):只装"一个 tool 的 schema + 一个 instruction",要求 LLM 返回 `{name, args}` JSON。

#### 2.5 动态刷新:**DB 层支持,代码层需重启**

DB 侧 `Toolkit.add_or_update()` + 集市 ZIP 下载可运行时增删;下一轮 LLM 调用前 `_build_tools()` 重新从 DB 读 → **新加的 tool 立刻生效**。但 `.py` 文件需落盘,LLM 协议层没有任何"运行时新增 tool"的支持。

---

### Q3. 工具调用指令的解析、错误修复、准确性

**结论**:**非流式(全量响应解析)+ 暴力 JSON 清理 + Pydantic 校验 + retry 写回 history**。

#### 3.1 解析方式:**全量字符串 → JSON 抽取**

`output_parser.py:34-50`(`AgentSchemaOutputParser.parse`):
```python
if response.startswith("```") and response.endswith("```"):
    response = "```".join(response.split("```")[1:-1])
response = JsonCleaner.extract_json_section(response)   # 提取 {...}
response = JsonCleaner.clean_boolean(response)          # true/false → True/False
try:
    response_obj = ast.literal_eval(response)           # ast 而非 json
    args = response_obj['tool']['args'] if 'args' in response_obj['tool'] else {}
    return AgentGPTAction(name=response_obj['tool']['name'], args=args)
```

关键点:
- **不用 OpenAI `tool_calls` 增量解析**——SuperAGI 调用 `chat_completion` 时**不传 `stream=True`**(grep `stream` in llms/ 无结果)。
- **用 `ast.literal_eval` 而非 `json.loads`**:更宽容(单引号、True/False、None)。
- **`JsonCleaner.extract_json_section`**(`json_cleaner.py:25-41`):**首 `{` 到末 `}`** 之间内容,剥离前后散文。

#### 3.2 错误修复

| 错误类型 | 修复 | 证据 |
|-----|-----|-----|
| JSON 截断 / 不完整 | LLM retry(抛 `RuntimeError` → Celery 任务重发完整 prompt) | `agent_tool_step_handler.py:80-86` |
| `true/false` JSON 兼容 | `clean_boolean` regex | `json_cleaner.py:6-15` |
| ``` ```json``` ``` 包裹 | split on ``` ` ``` | `output_parser.py:35-37` |
| 大括号嵌套 / 散文中夹 JSON | 找首 `{` 到末 `}` | `extract_json_section:25-41` |
| Pydantic 校验失败 | `ValidationError` 捕获 + 错误写回 history | `tool_executor.py:32-38` |
| 未知 tool 名 | 返回 "Unknown tool, refer to TOOLS list" 触发 retry | `tool_executor.py:46-51` |
| 工具执行异常 | `except Exception`:status=ERROR, retry=True, observation 写回 | `tool_executor.py:38-42` |

#### 3.3 准确性保证

- **Pydantic `args_schema` 校验**(`base_tool.py:117-128`)
- **"retry 写回 history"**:错误作为 `ToolExecutorResponse(result=...)` 写回 `agent_execution_feed`(`role="system"`),下一轮 `build_agent_messages` 重新喂给 LLM → LLM "看到"自己的错误并自我修正。
- **Local LLM 强制 JSON**:`local_llm.py:51` + `grammar/json.gbnf` 用 llama.cpp GBNF grammar **约束采样 100% 输出合法 JSON**——适配非 GPT 模型的关键。

#### 3.4 重试上限

- **OpenAI API 层**:`tenacity` 装饰器 `stop=stop_after_attempt(5)`(openai.py:13),只针对 RateLimitError / Timeout / TryAgain,指数退避 30-300s。
- **工具层**:**没有显式 max_retry**。`retry=True` 只把错误写回 history,**没有 retry counter**——理论上 LLM 可在一次 execution 中无限循环修复,直到 context 撑爆或外层 workflow 推进到 COMPLETE。

---

### Q4. 工具执行结果回传

**结论**:**结果写入 `agent_execution_feed` 表(Polymorphic Feed 流),下一轮 LLM 看到 `role=system` 的工具结果**;**不走 OpenAI `role=tool` / `tool_call_id` 或 Anthropic `tool_use_id` 块**。

#### 4.1 回传方式:DB 持久化 → 下一轮 messages

`output_handler.py:33-43`(`ToolOutputHandler.handle`):
```python
agent_execution_feed = AgentExecutionFeed(..., feed=assistant_reply, role="assistant", ...)
session.add(agent_execution_feed)
tool_response_feed = AgentExecutionFeed(..., feed=tool_response.result, role="system", ...)
session.add(tool_response_feed)
session.commit()
...
self.add_text_to_memory(assistant_reply, tool_response.result)
```

→ LLM 的 `assistant_reply` 和 tool 的 `result` 分别作为**两行**写进同一张 feed 表,**所有 tool 结果都标 `role=system`**。下一轮 `build_agent_messages` 读所有 feed 拼成 `messages=[{role, content}, ...]`。

#### 4.2 格式:**纯字符串 + 包裹前缀**

`tool_executor.py:34`:
```python
output = ToolExecutorResponse(status=status,
    result=f"Tool {tool.name} returned: {observation}", retry=retry)
```
→ 结果被包成 `f"Tool {name} returned: {observation}"` 字符串,无结构化 `{success, content, error}` 对象。

#### 4.3 通信协议:**自定义 + Provider 无关**

- 没有 OpenAI `role=tool` / `tool_call_id`(没传 `tools=` 参数)
- 没有 Anthropic `tool_use_id` 块
- 多 Provider 适配:`llms/llm_model_factory.py` 工厂方法支持 OpenAI / Google PaLM / Replicate / HuggingFace / Local LLaMA,统一 `chat_completion(messages, max_tokens)` 接口

#### 4.4 大结果处理

- **无 MEDIA 引用**:`tools.json` 空 `{"tools": {}}`,无 image/file 引用机制
- **无截断**:`max_token_limit` 只对 prompt 侧裁剪(LTM summary),**不裁剪 tool result**
- **LTM 旁路**:`output_handler.py:50-69` 把 assistant_reply + tool_response 切片(1024 token / 10 overlap)写入 vector store(Redis/Pinecone/Chroma),但**不走消息流压缩**
- **S3 大文件**:`tools/file/read_file.py:36-50` 大于 S3 阈值分块/直接返回二进制,避免整文件进 LLM

---

### Q5. File Backend 是否为工具调用做了适配

**结论**:**是,SuperAGI 是"路径模板化占位符"的代表**。`{agent_id}` / `{agent_execution_id}` + `STORAGE_TYPE=FILE|S3` 切换,但**没有用户级 home**,用项目相对路径 + 容器化部署。

#### 5.1 工具配置目录/文件清单

| 路径 | 作用 | 证据 |
|---|---|---|
| `config.yaml`(仓库根,gitignored) | 主配置(LLM keys / DB / STORAGE_TYPE / 路径模板) | `config_template.yaml:1-160` + `config/config.py:11-43` |
| `config_template.yaml` | 配置模板(跟踪) | 仓库根 |
| `superagi/tools/<toolkit>/<tool>.py` | 单个 tool 实现 | 24 个 toolkit 子包 |
| `superagi/tools/<toolkit>/prompts/*.txt` | **Toolkit 专属 LLM prompt** | `tools/code/prompts/write_code.txt` |
| `superagi/tools/external_tools/` | 外部 zip 解压的 tool | `tool_builder.py:42-44` |
| `superagi/tools/marketplace_tools/` | 集市下载的 tool | 同上 |
| `workspace/input/{agent_id}/` | **运行时 input 目录** | `config_template.yaml:24-26` |
| `workspace/output/{agent_id}/{agent_execution_id}/` | **运行时 output 目录** | `config_template.yaml:27-28` |
| `migrations/versions/` | Alembic DB 迁移 | 仓库根 |
| `tools.json` | 占位空文件 `{"tools": {}}` | 仓库根 |
| `~/.superagi/` | **不存在** | 反例,无 home |

#### 5.2 路径模板化加载代码

**配置声明**(`config_template.yaml:24-28`):
```yaml
RESOURCES_INPUT_ROOT_DIR: workspace/input/{agent_id}
RESOURCES_OUTPUT_ROOT_DIR: workspace/output/{agent_id}/{agent_execution_id}
```

**运行时替换**(`helper/resource_helper.py:75-87`):
```python
@classmethod
def get_formatted_agent_level_path(cls, agent: Agent, path) -> object:
    formatted_agent_name = agent.name.replace(" ", "")
    return path.replace("{agent_id}", formatted_agent_name + '_' + str(agent.id))

@classmethod
def get_formatted_agent_execution_level_path(cls, agent_execution, path):
    return path.replace("{agent_execution_id}",
                        (agent_execution.name.replace(" ", "") + '_' + str(agent_execution.id)))
```

**FileManager 注入**(`resource_manager/file_manager.py:11-15`):
```python
def __init__(self, session, agent_id=None, agent_execution_id=None):
    self.session, self.agent_id, self.agent_execution_id = session, agent_id, agent_execution_id
```

#### 5.3 全局 vs 项目级

- **项目级**:`config.yaml` 在仓库根(`config.py:38` `ROOT_DIR = os.path.dirname(...parent.parent)`)
- **没有 `~/.superagi/` home**(20/20 共识的反例)
- **没有 env 单点 override**(用 `os.environ` 覆盖 yaml,但无 `SUPERAGI_HOME`)

#### 5.4 与 `standard/file_backend.md` 对照

| 标准条款 | SuperAGI | 备注 |
|-----|---|---|
| §1.1 用户属主目录 + env 覆盖 | ❌ | 没有 home,只用 `os.getcwd()` |
| §1.4 secrets 独立 + 0o600 | ⚠️ | Fernet 加密 + `ToolConfig.is_secret`,但不强制 0o600 |
| §3.4 强结构化 | ✅ | `superagi/tools/<category>/<tool>.py` + Toolkit 分组 |
| §5.5 加密 secrets(企业级) | ✅ | Fernet + `ENCRYPTION_KEY` env + `is_encrypted` |
| §6.2 SQLite + WAL | ⚠️ | **PostgreSQL + Redis**(更重,38 表) |
| §8.2 跨平台路径 | ❌ | `os.getcwd() + "/"` 字符串拼接 |
| §8.3 atomic write | ❌ | 普通 `with open(..., 'w')` |
| §8.6 容器化部署 | ✅ | `docker-compose.yaml` 8 服务编排 |
| §9.1 OS 沙箱 | ❌ | 无沙箱,靠 `RESTRICTED` 模式 + GUI 询问 |
| §10.1 路径模板化占位符 | ✅ **是** | `{agent_id}` / `{agent_execution_id}` |
| §10.8 MCP 协议 | ❌ | 无 MCP |

**与 `file_backend.md` §10.1 引用一致**:SuperAGI 是"路径模板化"的**正例**,但用 `name_id` 拼路径(改名即破坏)是脆弱设计。

---

## 3. 关键代码片段(精简)

### 3.1 工具列表注入 prompt(`agent_prompt_builder.py:36-58` + `prompts/superagi.txt:7-13`)

```python
def add_tools_to_prompt(cls, tools, add_finish=True):
    final_string = ""
    for i, item in enumerate(tools):
        final_string += f"{i+1}. {cls._generate_tool_string(item)}\n"
    return final_string + finish_string + "\n\n"

def _generate_tool_string(cls, tool):
    return f"\"{tool.name}\": {tool.description}, args json schema: {json.dumps(tool.args)}"
```

### 3.2 JSON 解析 + 工具执行(`output_parser.py:34-50` + `tool_executor.py:22-52`)

```python
# parser
response = JsonCleaner.extract_json_section(response)
response = JsonCleaner.clean_boolean(response)
response_obj = ast.literal_eval(response)         # ast 替代 json
return AgentGPTAction(name=response_obj['tool']['name'],
                      args=response_obj['tool'].get('args', {}))

# executor
tools = {t.name.lower().replace(" ", ""): t for t in self.tools}
try:
    observation = tool.execute(self.clean_tool_args(tool_args))
except ValidationError as e:
    return ToolExecutorResponse(status="ERROR",
        result=f"Validation Error: {e}", retry=True)
except Exception as e:
    return ToolExecutorResponse(status="ERROR",
        result=f"Error1: {e}", retry=True)
```

### 3.3 路径模板 + 错误回写(`resource_helper.py:75-87` + `output_handler.py:33-49`)

```python
# path templating
path.replace("{agent_id}", formatted_agent_name + '_' + str(agent.id))
path.replace("{agent_execution_id}", formatted_agent_execution_name + '_' + str(agent_execution.id))

# error retry
agent_execution_feed = AgentExecutionFeed(..., feed=assistant_reply, role="assistant", ...)
tool_response_feed  = AgentExecutionFeed(..., feed=tool_response.result, role="system", ...)
session.add(agent_execution_feed); session.add(tool_response_feed); session.commit()
# → 下一轮 LLM 在 messages 里"看到"自己的错误并自我修正
```

---

## 4. 与 Onion Agent 设计的关联

**值得借鉴**:
1. **Toolkit 分组 + DB 注册**:Onion 可把 `~/.onion/tools/<toolkit>/<tool>.py` 同步注册进 state.db,支持 `toolkit_id` 多租户隔离 + SQL 查"agent 可用 tool 列表"。
2. **错误写回 history**(LTM-style retry) 简单有效,Onion 的 `session.json` 累加器天然支持。
3. **Local LLM 的 GBNF grammar 强制 JSON**(`local_llm.py:51` + `grammar/json.gbnf`):适配本地模型比纯 prompt-as-tool 更可靠。Onion 的 Provider 抽象应给本地后端一个 grammar 钩子。
4. **单 tool step 模式**(`agent_tool_step_handler.py`):每次只让 LLM 决定"一个 tool",prompt 简单稳健。Onion 可让用户/系统选择"一次一 tool"或"一次多 tool 并行"。

**应避免**:
1. **完全 prompt-as-tool 不传 `tools=`**:Onion 应**优先 OpenAI/Anthropic 原生 tool API**,prompt-as-tool 仅作兼容回退。
2. **`name + id` 拼路径**(`resource_helper.py:79`):改名/重建 agent 路径会变。Onion 用 `pure_uuid` 或 `sha256(id)`。
3. **无 retry 上限**:Onion 应该有 `max_tool_retry=5` 硬上限,防止 LLM 死循环。
4. **大结果不裁剪**:Onion 需 `MAX_TOOL_RESULT_TOKEN=4000` 硬上限 + 截断/摘要回写。
5. **普通 `with open('w')` 写**:`file_manager.py:42-44`:Onion 必须用 `temp+rename` 原子化。
6. **`os.getcwd() + "/" + path` 字符串拼接**:Onion 用 `pathlib.Path` 或 `platformdirs`。

---

## 5. 不确定 / 未找到

1. **streaming 增量解析**:`llms/` grep `stream|chunk|delta` 全部无结果,确认**完全没有流式**。`output_handler.handle_tool_response` 接收 `assistant_reply: str` 是完整字符串。
2. **MCP 协议**:全 `superagi/` grep `mcp` 无任何匹配,**无 MCP 集成代码**。
3. **Agent Skills(progressive disclosure)**:无 `SKILL.md` / `skills/` / 任何类似物。
4. **Tool 调用 max_retry 上限**:`tool_executor.py` 的 `retry=True` 只写回 history,**无 retry counter**,理论上 LLM 可无限循环修复直到 token 撑爆。
5. **Tool 集市 HTTPS API 客户端**:`helper/tool_helper.py:60-79` 用 GitHub `api.github.com/.../zipball/{branch}` 拉 ZIP,但**未找到 `marketplace.superagi.com/api` 官方集市 API 客户端**——可能在前端 GUI 侧。
6. **Tool args 深层 schema 错误的 fallback**:`clean_tool_args` 只处理一层 `{value:...}` 嵌套,深层错误可能直接 `ValidationError` 返回。

---

**报告完。** 基于本地 clone 快照(2026-07)。
