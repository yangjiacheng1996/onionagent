# MetaGPT — 工具调用（Tool Channel）调研报告

> 调研对象:`geekan/MetaGPT`(`C:\workspace\github\onionagent\harness\01_market_research\clone\MetaGPT`)
> 调研者:deepcode · general agent
> 配套:`harness/01_market_research/MetaGPT/file_backend.md`(已交付,关注工作区维度)

## 0. 智能体一句话定位

**多角色软件公司模拟(PM / Architect / Engineer / QA / Searcher ……),用 SOP 流水线 + 项目级 Git 仓库做"团队级 ReAct",把"一句话需求"拆解为 PRD → 系统设计 → 任务 → 代码 + 测试。**

核心特点:**不走 OpenAI/Anthropic 标准 `tools` / `function calling` 协议**,而是用 **XML 标签 + Markdown 标题 + pydantic 动态模型** 这套"prompt-as-tool" 协议,配合 **ToolRegistry 中央注册表 + ActionNode schema 编译 + ToolRecommender(BM25 召回 + LLM rank)** 完成工具调用。

## 1. 调研依据

| 文件 | 关键作用 |
| --- | --- |
| `metagpt/tools/tool_registry.py:1-200` | **核心**:`ToolRegistry` 中央注册表 + `@register_tool` decorator + `TOOL_REGISTRY` 单例 |
| `metagpt/tools/tool_convert.py:1-180` | **schema 生成**:GoogleDocstringParser + AST 解析 |
| `metagpt/tools/tool_recommend.py:1-260` | ToolRecommender:TypeMatch / BM25 / Embedding 三种召回 + LLM rank |
| `metagpt/actions/action_node.py:1-700` | **ActionNode** — XML/Markdown 解析主战场,`fill` / `xml_fill` / `code_fill` / `simple_fill` |
| `metagpt/utils/common.py:73-220` | `OutputParser.parse_blocks` / `parse_code` / `parse_data_with_mapping` |
| `metagpt/utils/repair_llm_raw_output.py:1-400` | 4 类 repair,`tenacity` retry 上限 6×3 |
| `metagpt/roles/role.py:1-450` | `Role` 状态机 + `STATE_TEMPLATE` 用 LLM 选 action state(数字) |
| `metagpt/environment/base_env.py:200-280` | `Environment.publish_message` — 跨角色 Message Bus 协议 |
| `metagpt/environment/mgx/mgx_env.py:1-100` | MGXEnv 集中分发(TeamLeader Mike 中转) |
| `metagpt/schema.py:194-330` | `Message` / `Documents` — `send_to` + `cause_by` 订阅路由 |
| `metagpt/provider/base_llm.py:1-380` | `BaseLLM`,`tenacity` retry(3 次,ConnectionError) |
| `metagpt/provider/openai_api.py:189-290` | `_achat_completion_function` 走 OpenAI `tools` 协议(**仅 `aask_code` 一处用**) |
| `metagpt/provider/anthropic_api.py:1-90` | AnthropicLLM,**不传 `tools` 参数**,只走 messages + system |
| `metagpt/provider/constant.py:3-22` | `GENERAL_FUNCTION_SCHEMA` 唯一的 hard-coded OpenAI 格式 tool |
| `metagpt/tools/libs/{terminal,editor,browser,git,data_preprocess,feature_engineering}.py` | 30+ `@register_tool` 标注的内置工具类 |
| `metagpt/skills/WriterSkill/Translate/{config.json, skprompt.txt}` | Semantic Kernel 风格 Skills(`{{$variable}}` 模板) |
| `metagpt/tools/swe_agent_commands/*.sh` | SWE-Agent 风格的 bash 命令式工具(老路径) |
| `metagpt/team.py:59-80` | `Team.serialize/deserialize` 整公司状态 JSON |
| `metagpt/const.py:65, 39, 41, 49` | `TOOL_SCHEMA_PATH`(预留,实际不存在)/ `CONFIG_ROOT` / `SERDESER_PATH` / `SKILL_DIRECTORY` |

## 2. 五个核心问题的回答

### Q1. 工具来源

**MetaGPT 的"工具" = `TOOL_REGISTRY` 注册的工具 + `Action` 类 + SWE-Bench bash + Semantic Kernel Skills** 五大来源。

#### 1.1 内置工具(`@register_tool` 标注,共 ~30 个)

`metagpt/tools/libs/__init__.py:1-30` 一次性 import 触发所有装饰器,注册到 `TOOL_REGISTRY` 单例(`tool_registry.py:91`)。关键工具:

| 工具类 / 函数 | 文件 | 功能 |
| --- | --- | --- |
| `Terminal` / `Bash` | `tools/libs/terminal.py:16,184` | shell 命令(Windows `cmd.exe` / POSIX `bash`) |
| `Editor` | `tools/libs/editor.py:84-101` | 文件读写改,`include_functions` 暴露 11 个方法 |
| `Browser` | `tools/libs/browser.py:32-46` | Playwright / Selenium 浏览器自动化 |
| `Git` 异步函数 | `tools/libs/git.py:15,95` | `git_create_pull` / `git_create_issue` |
| `Deployer` | `tools/libs/deployer.py:5` | 部署到公网(预留) |
| `DataPreprocessTool` ×8 | `tools/libs/data_preprocess.py:88-187` | 缺失值填充、标准化、编码 |
| `MLProcess` ×10+ | `tools/libs/feature_engineering.py:26-405` | 多项式展开、目标编码、特征选择 |
| `SearchEngine` × 6 后端 | `tools/search_engine.py:20-90` | SerpAPI / Serper / Google / DDG / Bing / Custom |
| `WebBrowserEngine` × 2 后端 | `tools/web_browser_engine.py:20-80` | Playwright / Selenium |
| `CodeReview` | `tools/libs/cr.py:19` | 代码 review + fix |

> ⚠️ 这些工具是给 **RoleZero / SWE 流程** 用的,标准 MetaGPT 软件公司 SOP **不走** 这些工具——SOP 走"角色 → Action → FileRepository"。

#### 1.2 MCP 支持:**❌ 不支持**

全代码库 `grep -r "MCP\|mcp_server\|mcp.json"` 零命中。`metagpt/provider/llm_provider_registry.py` 注册的 LLM 类型(OpenAI / Anthropic / Ollama / Bedrock / 智谱 / 月之暗面 / 阿里 / 字节 …)无 MCP 客户端。

#### 1.3 Agent Skills 支持:**部分(SK 风格,不是 Anthropic Skills)**

- 技能目录:`metagpt/skills/`(~30 个 `*Skill/*/` 目录)
- 每个技能 = `config.json` + `skprompt.txt`,**是 Microsoft Semantic Kernel 风格**(`{{$variable}}` 模板),**不是 Anthropic 的 `SKILL.md` + progressive disclosure**
- 调用:`metagpt/actions/skill_action.py:55-89` `SkillAction.find_and_call_function()` 动态 import
- **不是渐进式披露**——一次全加载,无按需 disclosure

#### 1.4 其他工具类型

- **SWE-Bench bash**:`metagpt/tools/swe_agent_commands/*.sh`,LLM 直接生成 `open file.py` / `edit 1:5 <<EOF` bash 命令
- **Action 类本身就是工具**:每个 Action 的 `run()` 等价一个工具——`WritePRD` / `WriteDesign` / `WriteCode` / `WriteTest` / `RunCode` / `DebugError` 等 50+ 个,**这是 MetaGPT 工具调用主战场**
- **DI/RoleZero 命令**:`metagpt/actions/di/{run_command,write_plan,execute_nb_code,ask_review}.py`

### Q2. 工具列表的生成、传递、格式

#### 2.1 生成方式:**双层注册**

- **代码层(主)**:`@register_tool(tags=[...], include_functions=[...])` 装饰器,模块 import 时自动注册
- **AST 层(运行时热加载)**:`register_tools_from_path()` 扫描目录用 `ast.parse` 注册(`tool_registry.py:165-200`)

`Tool` 数据结构(`tool_data_type.py:11-13`):
```python
class Tool(BaseModel):
    name: str; path: str; schemas: dict = {}; code: str = ""; tags: list[str] = []
```

#### 2.2 工具 schema 格式:**JSON dict(自定义,不是 OpenAI 标准)**

`convert_code_to_tool_schema`(`tool_convert.py:7-32`)用 Google docstring + `inspect.signature`:
```json
{
  "type": "class", "description": "...", "signature": "(self, x: int) -> None",
  "parameters": {"x": {"type": "int", "desc": "..."}}, "code": "<完整源码>"
}
```

**关键差异**:
- ✅ 包含函数签名 + **完整源码**(`code` 字段,LLM 可看实现)
- ❌ **没有 OpenAI 标准的 `type: "function"` + `parameters: {type:"object", properties, required}` 三层嵌套**(`provider/constant.py:3-22` 的 `GENERAL_FUNCTION_SCHEMA` 才是 OpenAI 格式,但只有 `aask_code` 一处用)
- `ToolSchema(**schemas)` 校验**被 silent 吞掉异常**(`tool_registry.py:48-51`),**schema 错也照样用**

#### 2.3 传递给 LLM 的方式:**prompt-as-tool 模式(不传 `tools` 字段)**

- **标准 Action 路径**:`ActionNode.compile` 把 schema 编译成 **Markdown prompt**(`action_node.py:415-421`),用 `[CONTENT][\/CONTENT]` 标签约束输出
- **Tool 推荐路径**:`ToolRecommender.get_recommended_tool_info`(`tool_recommend.py:113-124`)把工具 schema 拼成 Markdown 文字塞 prompt
- **SWE-Bench 路径**:bash 函数定义在 `.sh` 里,LLM 直接生成 bash 命令
- **OpenAI 协议**:**仅 `OpenAILLM.aask_code` 一处用**(`openai_api.py:189-203`),**特例**
- **Anthropic 协议**:`AnthropicLLM._const_kwargs`(`anthropic_api.py:24-37`)**完全不传 `tools` 字段**——**Anthropic function calling 协议在 MetaGPT 里根本没启用**

#### 2.4 ToolRecommender 召回+排序

- **召回**:TypeMatch(按 tag 精确)/ BM25(默认)/ Embedding(预留)
- **排序**:LLM rank,`TOOL_RECOMMENDATION_PROMPT` 选 top-5
- **容错**:JSON 解析失败时 fallback 调一次 LLM 修(`tool_recommend.py:142-160`)

#### 2.5 动态刷新:**是(支持热加载目录)**

`register_tools_from_path(path)`(`tool_registry.py:186-200`)支持 `os.walk` 扫描任意目录运行时新增工具;**但实际无人调用**,MetaGPT 走"启动时一次性 import 全部"的隐式模式。

### Q3. 工具调用指令的解析、错误修复、准确性

#### 3.1 解析方式:**四种范式混合**

| 范式 | 位置 | 方式 |
| --- | --- | --- |
| A. ActionNode XML/Markdown(**主**) | `action_node.py:1-700` | 5 种 FillMode:CODE_FILL(``` ```代码块)/ XML_FILL(`<field>...</field>` 正则) / SINGLE_FILL / simple_fill(按 `##` 切块) / complex_fill(逐 children) |
| B. RoleZero JSON 命令 | `prompts/di/role_zero.py` `CMD_PROMPT` | LLM 输出 `{"command_name":..., "args":...}` 列表,`ast.literal_eval` 解析 |
| C. OpenAI tool_calls(**仅 aask_code**) | `base_llm.py:266-294` | 读 `rsp.choices[0].message.tool_calls[0].function.arguments` |
| D. Role 状态机数字选择 | `role.py:73-93` + `repair_llm_raw_output.py:342-357` | LLM 输出**数字**当 state,`extract_state_value_from_output` 从长文本抽数字 |

#### 3.2 流式增量解析:**❌ 不用**

`OpenAILLM._achat_completion_stream`(`openai_api.py:100-140`)只收集 `delta.content` 拼字符串,**不解析 `delta.tool_calls`**。**没有 Cline 那种 XML 流式增量解析**。

#### 3.3 错误修复:**4 类 repair + 双层 retry**

`utils/repair_llm_raw_output.py`:
- `repair_case_sensitivity` / `repair_special_character_missing` / `repair_required_key_pair_missing` / `repair_json_format` / `repair_invalid_json`(按 JSONDecodeError 行号删行)

**双层 retry**:
- **外层**:`action_node._aask_v1` 装饰 `@retry(stop=stop_after_attempt(6), wait=wait_random_exponential(1, 20))`——**6 次**
- **内层**:`retry_parse_json_text` 装饰 `@retry(stop=repair_stop_after_attempt)`——`3 if Config.repair_llm_output else 0`
- **BaseLLM 底座**:`@retry(stop=stop_after_attempt(3), wait=wait_random_exponential(1, 60))`,仅对 `ConnectionError`
- **总上限**:**6×3 = 18 次 LLM 调用**(如果开了 repair)

#### 3.4 准确性保证

- **schema 校验**:`ToolSchema(**schemas)` 校验但**异常被吞掉**(`tool_registry.py:48-51` 整段 `pass`),形同虚设
- **dynamic pydantic model**:`create_model_class`(`action_node.py:255-305`)动态创建 pydantic 模型,`check_missing_fields_validator` 必填字段校验,**`Unrecognized fields: ...` 只警告不报错**
- **Type hint 转换**:`xml_fill`(`action_node.py:558-595`)按 `expected_type`(`str`/`int`/`bool`/`list`/`dict`)转换,失败用默认值(`int` 失败 → `0`;`list` 失败 → `[]`)
- **plan-then-act**:`RoleReactMode.PLAN_AND_ACT`(`role.py:181-198`)用 `Planner` 先 plan 再 act

### Q4. 工具执行结果回传

#### 4.1 跨角色通信协议:**Message Bus(不是 role=tool)**

**核心协议**:`Environment.publish_message(message)` + `Message.cause_by` / `Message.send_to` 订阅。

`environment/base_env.py:200-220`:
```python
def publish_message(self, message: Message, peekable: bool = True) -> bool:
    for role, addrs in self.member_addrs.items():
        if is_send_to(message, addrs):
            role.put_message(message)   # 放进 Role.msg_buffer
    self.history.add(message)
```

**`Message` 路由字段**(`schema.py:232-243`):
- `content`:文本(可能含 instruct_content)
- `instruct_content`:Optional `BaseModel`(动态 pydantic 强 schema 校验)
- `cause_by`:Action 类名,**订阅过滤器**——Role 只处理它 `rc.watch` 里的 Action 产出的消息
- `sent_from`:发送者角色 ID
- `send_to:set[str]`:**`{<all>}` 默认广播**;可指定 `{Alex, Mike}`;`<self>` 自循环;`<none>` 丢弃
- `role`:`"user" | "assistant" | "system"`(给 LLM 用,发送时被 MGXEnv 转成 `"assistant"` 附 `[Message] from X to Y:` 前缀)
- `metadata`:dict,存图片、token、cost

**MGXEnv 集中分发**(`environment/mgx/mgx_env.py:24-66`):常规消息先发给 TeamLeader(Mike),由 TL 决定转发;支持 human `direct_chat` 直达某个角色;消息被 `move_message_info_to_content` 改造。

**结论**:**MetaGPT 的"工具执行结果回传" = Action.run() 返回 `Message` → `Environment.publish_message` → 订阅匹配的 Role 把消息塞 `msg_buffer` → 下次 `_observe` 时读进 `rc.memory`**

#### 4.2 格式:**结构化 pydantic + 文本双轨**

- `Message.instruct_content` 是 `BaseModel` 子类实例(ActionNode 编译时动态创建),**有强 schema 校验**
- `Message.content` 是 str(自由文本,LLM 可见)
- **没有 `role=tool` / `tool_use_id` 块**——MetaGPT 不用 OpenAI/Anthropic 协议字段

#### 4.3 通信协议对照

| 协议 | 支持情况 | 用法 |
| --- | --- | --- |
| **OpenAI `tools` API** | 仅 1 处用 | `aask_code` 强制 function calling 拿代码(`openai_api.py:189-203`) |
| **OpenAI 通用 `chat.completions`** | 默认 | `messages: list[dict]` 角色循环 |
| **Anthropic `messages`** | 支持 | 不传 `tools`,只 messages+system(`anthropic_api.py:24-37`) |
| **MetaGPT Message Bus** | 默认 | `Message` 跨角色,`cause_by` + `send_to` 路由 |

#### 4.4 大结果处理

- **大文件不内联**:`metagpt/roles/engineer.py` 注释 "According to Section 2.2.3.1 of RFC 135, replace file data in the message with the file name"——**只传文件名,内容从 FileRepository 读**
- **图片**:`MGXEnv.attach_images`(`mgx_env.py:84-89`)提取转 base64 放 `metadata[IMAGES]`
- **Base64 脱敏**:`BaseLLM.mask_base64_data`(`base_llm.py:177-204`)把 log 里的 base64 替换成 `<Image base64 data has been omitted>`
- **上下文压缩**:`BaseLLM.compress_messages`(`base_llm.py:281-355`)4 种策略 `POST_CUT_BY_TOKEN` / `POST_CUT_BY_MSG` / `PRE_CUT_BY_TOKEN` / `PRE_CUT_BY_MSG`,按 `keep_token = max_token * 0.8` 裁剪
- **Memory TTL**:`const.MEM_TTL = 24 * 30 * 3600`(30 天)

### Q5. File Backend 是否为工具调用做了适配

#### 5.1 工具配置目录/文件清单

| 路径 | 作用 | 代码 |
| --- | --- | --- |
| `metagpt/tools/libs/*.py` | 内置工具类(用 `@register_tool` 装饰) | `libs/__init__.py:1-30` 一次性 import 触发注册 |
| `metagpt/tools/schemas/<name>.yml` | **预留路径,实际不存在** | `const.py:65` 声明但源码里没真实文件 |
| `metagpt/skills/<Category>/<SkillName>/{config.json, skprompt.txt}` | Semantic Kernel 风格 Skills | `metagpt/skills/`(30 个 Skill 目录) |
| `metagpt/tools/swe_agent_commands/*.sh` | SWE-Bench bash 命令式工具 | 6 个 sh 文件 |
| `~/.metagpt/config2.yaml` | 用户级 LLM/API key 配置 | `metagpt/config2.py:88-92` |
| `<METAGPT_ROOT>/config/config2.yaml` | 项目级 LLM 配置覆盖 | `metagpt/config2.py:95-103` |
| `<METAGPT_ROOT>/metagpt/prompts/<role>.py` | **prompt-as-tool 模板**——把工具调用格式注入到 prompt | `metagpt/prompts/`(8 个 role 模板) |
| `metagpt/ext/**/settings/*.yaml` | SPO / AFLOW 扩展 settings | `metagpt/ext/spo/settings/Navigate.yaml` |
| `<workspace>/storage/team/team.json` | **Team 序列化**(serialize 整公司状态,可 `--recover-path` 恢复) | `metagpt/team.py:59-64` |

#### 5.2 加载代码

- 启动时隐式 import:`metagpt/tools/__init__.py:9` → `from metagpt.tools import libs`
- 运行时 hot-reload:`metagpt/tools/tool_registry.py:186-200` `register_tools_from_path()`
- 用户配置:`metagpt/config2.py:31-140` 合并 CLI + yaml + env
- Skills 动态 import:`metagpt/actions/skill_action.py:55-89`

#### 5.3 全局 vs 项目级 vs 两者

- **配置**:两者都有(`~/.metagpt/config2.yaml` 全局 + `<METAGPT_ROOT>/config/config2.yaml` 项目级覆盖)
- **工具包**:**包内置**(`metagpt/tools/`),跟随 `pip install metagpt`
- **工作区**:**项目级**(`<METAGPT_ROOT>/workspace/<project>/`),由 `METAGPT_PROJECT_ROOT` env 决定根
- **Skills**:**包内置**(`metagpt/skills/`),用户不可扩展(除非改包源码)

#### 5.4 与 `standard/file_backend.md` 的对照

| file_backend 标准条款 | MetaGPT 表现 | 评价 |
| --- | --- | --- |
| §3.4 强结构化(按角色/数据类别/生命周期) | ✅ `<workspace>/<project>/{docs/, resources/, tests/, test_outputs/, <project_name>/}` + `storage/team/team.json` | **符合** |
| §3.8 Bootstrap 种子文件 | ❌ 无自动 seed | 不符合 |
| §5.3 secrets 独立 + 0o600 | ❌ `~/.metagpt/config2.yaml` **明文**,无 0o600 | **反例** |
| §5.4 LLM 不可读凭证白名单 | ❌ LLM 可 `read_file` 读 `config2.yaml` | **反例** |
| §8.3 atomic write | ✅ `Team.serialize` 用 `write_json_file(use_fallback=True)` | 部分符合 |
| §10.7 plugin / extension 系统 | ⚠️ `metagpt/ext/`(spo/aflow/...)是"扩展包",**不是 plugin**——无 manifest.json / 动态加载 | 弱符合 |
| §10.8 MCP 协议支持 | ❌ **完全不支持** | **反例** |
| §3.2 "控制平面" vs "工作区" 双层解耦 | ⚠️ `storage/team/team.json` 反而在工作区里 | 不符合 |
| §6.1 单文件 session.json (append-only) | ❌ `Memory` 用 list,不是 append-only 文件 | **反例** |
| §6.6 多 Agent 状态关联 | ✅ `Message.cause_by` + `send_to` + `team.json` 序列化 | 符合 |
| §7.1 角色分工型 | ✅ PM/Arch/PMgr/Eng/QA 各自固定 Action | 符合(Multi-Agent 标准) |

## 3. 关键代码片段

### 3.1 `TOOL_REGISTRY` 注册(`metagpt/tools/tool_registry.py:23-91`,节选)

```python
class ToolRegistry(BaseModel):
    tools: dict = {}
    tools_by_tags: dict = defaultdict(dict)

    def register_tool(self, tool_name, tool_path, schemas=None, ...,
                      tool_source_object=None, include_functions=None, verbose=False):
        if self.has_tool(tool_name): return
        if not schemas: schemas = make_schema(tool_source_object, include_functions, schema_path)
        if not schemas: return
        schemas["tool_path"] = tool_path
        try: ToolSchema(**schemas)   # 校验,但异常被吞
        except Exception: pass
        tool = Tool(name=tool_name, path=tool_path, schemas=schemas, code=tool_code, tags=tags)
        self.tools[tool_name] = tool
        for tag in tags: self.tools_by_tags[tag].update({tool_name: tool})

TOOL_REGISTRY = ToolRegistry()   # 全局单例

def register_tool(tags=None, schema_path="", **kwargs):
    def decorator(cls):
        file_path = inspect.getfile(cls)
        if "metagpt" in file_path: file_path = "metagpt" + file_path.split("metagpt")[-1]
        TOOL_REGISTRY.register_tool(tool_name=cls.__name__, tool_path=file_path,
            tool_code=inspect.getsource(cls), tags=tags, tool_source_object=cls, **kwargs)
        return cls
    return decorator
```

### 3.2 OpenAI `aask_code`(唯一的 function calling 使用点,`openai_api.py:189-203`)

```python
async def aask_code(self, messages: list[dict], timeout: int = USE_CONFIG_TIMEOUT, **kwargs) -> dict:
    """Use function of tools to ask a code."""
    if "tools" not in kwargs:
        configs = {"tools": [{"type": "function", "function": GENERAL_FUNCTION_SCHEMA}]}
        kwargs.update(configs)
    rsp = await self._achat_completion_function(messages, **kwargs)
    return self.get_choice_function_arguments(rsp)
```

### 3.3 跨角色 Message 路由(`environment/base_env.py:200-220`)

```python
def publish_message(self, message: Message, peekable: bool = True) -> bool:
    """Distribute the message to the recipients..."""
    found = False
    for role, addrs in self.member_addrs.items():
        if is_send_to(message, addrs):
            role.put_message(message)   # 放进 Role.msg_buffer
            found = True
    if not found: logger.warning(f"Message no recipients: {message.dump()}")
    self.history.add(message)          # 全局 history,用于 debug
    return True
```

### 3.4 ActionNode XML 解析 + 类型转换(`action_node.py:558-595`,节选)

```python
async def xml_fill(self, context: str, images=None) -> Dict[str, Any]:
    field_names = self.get_field_names()
    field_types = self.get_field_types()
    extracted_data: Dict[str, Any] = {}
    content = await self.llm.aask(context, images=images)
    for field_name in field_names:
        pattern = rf"<{field_name}>(.*?)</{field_name}>"
        match = re.search(pattern, content, re.DOTALL)
        if match:
            raw_value = match.group(1).strip()
            field_type = field_types.get(field_name)
            if field_type == int:
                try: extracted_data[field_name] = int(raw_value)
                except ValueError: extracted_data[field_name] = 0     # 失败默认值
            elif field_type == list:
                try: extracted_data[field_name] = eval(raw_value)
                except: extracted_data[field_name] = []
            # ... str/bool/dict 类似
    return extracted_data
```

### 3.5 ToolRecommender BM25 召回(`tool_recommend.py:178-200`,节选)

```python
class BM25ToolRecommender(ToolRecommender):
    bm25: Any = None
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._init_corpus()
    def _init_corpus(self):
        corpus = [f"{tool.name} {tool.tags}: {tool.schemas['description']}"
                  for tool in self.tools.values()]
        tokenized_corpus = [self._tokenize(doc) for doc in corpus]
        self.bm25 = BM25Okapi(tokenized_corpus)
    async def recall_tools(self, context="", plan=None, topk=20):
        query = plan.current_task.instruction if plan else context
        doc_scores = self.bm25.get_scores(self._tokenize(query))
        top_indexes = np.argsort(doc_scores)[::-1][:topk]
        return [list(self.tools.values())[i] for i in top_indexes]
```

## 4. 与 Onion Agent 设计的关联

### 4.1 可借鉴

1. **`@register_tool` 装饰器 + 中央 `TOOL_REGISTRY` 单例** 是优雅设计。Onion 可以把 `read_file` / `write_file` / `bash` / `update_plan` / `record_memory` / `finish_loop` 全部用装饰器挂载,Registry 单例做"工具来源"真相源,避免 `if tool_name == "..."` 散落各处。
2. **ToolRecommender(BM25 召回 + LLM rank)** 是面对"工具集 30+" 的必备能力。Onion MVP 5-10 个工具不需要,但 P1 扩展到 MCP + Skills 几十个时,这套 two-stage 架构是现成模板。
3. **`Tool.schemas` 含 `code` 字段(完整源码)** 让 LLM 选工具时能看到实现细节,比 OpenAI `tools` 协议的"只给 JSON schema" 更强大,适合复杂内部工具。
4. **ActionGraph + Role 数字状态机** 把 ReAct 用数字而非自然语言表达,可靠性高很多。Onion sub-agent 编排可借鉴:LLM 输出 `next_agent_id` 而不是"接下来该做什么"的自由文本。
5. **`FileRepository.docs.prd.save(filename, content)` + `repo.docs.prd.get(filename)` 跨角色文件总线**——比纯 Message 通信更适合大结果。Onion sub-agent 共享中间产物走 `<repo>/.onion/scratch/<task_id>/` + `temp+rename` 原子化,**不用 session.json 内联**。
6. **大文件不内联 Message,只传文件名**(`engineer.py` 注释 RFC 135 2.2.3.1)是反 LLM context 爆炸的关键工程实践。Onion 必须从 day 1 贯彻。

### 4.2 应避免

1. **不用 OpenAI/Anthropic `tools` 协议**——MetaGPT 选 XML+Markdown+JSON prompt-as-tool,虽简单但**牺牲 schema 强校验**(`ToolSchema` 校验异常被吞),且**多协议不统一**。Onion 应当**坚持走标准 `tools` API + Provider 适配**,**不要再发明自己的解析协议**。
2. **不能 silent 吞掉 schema 校验异常**(`tool_registry.py:48-51` 整段 `pass`)。Onion 校验失败应当 raise,让 Agent Loop 知道"这个工具坏了",而非继续用脏数据。
3. **`include_functions=[...]` 白名单模式**值得借鉴,但应当**强制默认暴露所有 public method 的反面**——每个 method 独立成 tool,不嵌套类(`Browser.click_element` 改成 `browser_click_element`)。
4. **SWE-Agent bash 工具集**看似优雅但实际脆弱——LLM 生成 bash 容易语法错、路径错、EOF 不匹配。Onion 不要走"LLM 直接输出 shell 命令"路径,坚持走"标准 tool_calls API + Python function execution"。
5. **secrets 明文 + 没 0o600**(`~/.metagpt/config2.yaml`)是信创场景反例。Onion 必须 `~/.onion/secrets/auth.json` + chmod 0o600 + 工具层白名单(`read_file` 拒绝读 `auth.json`)。
6. **retry 上限 6×3 = 18 次**太激进,生产环境会爆 token 预算。Onion 用 **3 次** 够了,失败就上报用户,不要让 Agent Loop 静默重试。
7. **Anthropic 走纯文本(不传 `tools`)** 是个大倒退——Anthropic `messages` 协议原生支持 `tools`,MetaGPT 没启用。Onion 走 OpenAI / Anthropic **统一 tool channel**,不要做 Provider-specific 工具协议。

## 5. 不确定 / 未找到

1. **`TOOL_SCHEMA_PATH = METAGPT_ROOT / "metagpt/tools/schemas"`**(`const.py:65`)声明的目录**实际不存在**(`Get-ChildItem` 报 PathNotFound)——可能是历史遗留或未完成的迁移。
2. **MCP 客户端**源码中**零引用**——MetaGPT 完全没有 MCP 概念,无 `mcp_servers` 配置、无 `mcp.ClientSession` 引用。
3. **`ActionNode.FillMode.XML_FILL` 实际使用频率**未统计——`xml_fill` 是个独立方法,但 MetaGPT 主流程用 `simple_fill`(走 `OutputParser.parse_blocks` 按 `##` 切分)而不是 XML。
4. **`metagpt/ext/spo/app.py`** 看起来是 SPO 优化入口,代码里没看到 `register_tool` / `TOOL_REGISTRY` 引用,但有 `SPO_LLM` 单例——SPO 扩展可能走自己的 LLM 客户端而非统一 Registry。
5. **流式增量解析**——`_achat_completion_stream` 只收集 `delta.content`,**完全不解析 `delta.tool_calls`**(因为走 prompt-as-tool)。长工具输出需要等 stream 结束才解析,**没有 Claude Code 那种"边生成边触发"的能力**。
6. **Tool 选择 + 调用的统一入口函数**(类似 `Tool.run(tool_name, args)`)在 MetaGPT 里**没有**——每个 Role 自己 `set_actions([WritePRD])` 然后 `self.rc.todo.run(...)`,没有"LLM 一次性选多个工具 + 并行执行"的能力。**Onion 设计时可以填补这个空白**。
