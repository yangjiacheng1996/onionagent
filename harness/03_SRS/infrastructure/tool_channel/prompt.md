# tool_channel设计
【背景】
我现在正在开发一个Onion Agent，基于洋葱架构。

【已有文档】
- 在github上寻找20个最流行开源的React智能体进。根据Star数量降序排列，列出了20个开源React智能体，内容放到了harness/01_market_research/top_20_react_agent.md。
- 我已为这20个智能体在harness/01_market_research中各自建立了独立目录，用于存放调研报告。现已有file_backend.md、tool_channel.md和agent_loop.md 。
- 行业标准总结。写入harness/01_market_research/standard 目录中，内含file_backend.md、tool_channel.md和agent_loop.md 。
- 我的洋葱架构设计哲学写入了harness/02_project_manager/project_manager.md 。
- function calling对智能体工具指令准确性的影响：harness/01_market_research/tool_accuracy.md 。
全文阅读standard/行业标准文档和project_manager.md，其他文件选择阅读。

【已开发代码】
- 基于harness/03_SRS/infrastructure/file_backend/prompt.md，开发了src/infrastructure/file_backend/init_workspace.py 。
- src/infrastructure/tool_shell/中，mcp_client.py可以调用mcp server。agent_skills_client.py可以读取skill的L1、L2、L3级别提示词。buildin_client.py可以调用buildin_tools中的三大内置工具。
- src/infrastructure/buildin_tools/中file_system.py是文件系统工具包，command_line.py是本地命令行执行工具包，non_head_browser.py是无头浏览器工具包。

【任务】
1. 根据tool_accuracy.md的指导，为使大模型能够调用工具，本项目采用OpenAI的 tool通道。需要将所有工具（mcp、skills、buildin）的schema整合成一个tool_list传入到tool通道中。
所以在我的项目中，会有src/infrastructure/tool_channel这个模块，这个模块包含两个脚本。tool_list.py是将buildin、mcp、skills三种工具汇总成一份tool_list的json对象（后续将tool_list传给openai_tool_engine中的tool通道的这部分代码放到SDK，SDK属于项目架构的第三层），大模型发出的json工具指令，由tool_router.py做正则解析、json-repair修复，并路由调用对应的client。
现在需要建立一套路由规则。我的设计是在tool_list中为不同类型的工具添加标签（schema中添加tag字段或者函数名之前添加mcp_或skills_之类的前缀），然后大模型发出的工具调用指令携带标签，指令解析成json后，再根据标签调用对应的Client拿到工具调用结果。
请你阅读已有文档和已开发代码，在harness/03_SRS/infrastructure/tool_channel/design.md，设计一套工具列表上报大模型、指令解析与路由机制。
这套机制需要符合OpenAI function calling标准格式，明确Input Schema（给大模型看）和Input handler（给工具传参）。


【后续】
生成的harness/03_SRS/infrastructure/tool_channel/design.md我看过了，暂时没有发现什么问题。
请你按照design.md开发src/infrastructure/tool_channel/tool_list.py和src/infrastructure/tool_channel/tool_router.py，并将这两个py文件命令行化，使得代码可视化，所见即所得，供我后期手动测试。代码编写完成后再tests/tool_channel中进行充分的测试。
通过python tool_list.py，可以直接pretty print 工具列表json list对象。通过python tool_router.py --command <json字符串指令> ，就可以修复json字符串指令然后调用对应的工具，pretty print工具执行结果，工具执行结果必须是OpenAI标准格式。
在harness/01_market_research/tool_accuracy.md中有这一段内容：
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
所以tool_router.py返回的工具执行结果请保持这个格式。
目前暂不需要将tool list写入工作区的tools.jsonl文件，那是SDK中的Agent Loop需要实现的功能。还没有开发到SDK。