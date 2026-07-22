# 现有agent_skills_client.py评估
【背景】
我现在正在开发一个Onion Agent，基于洋葱架构。

【已有文档】
- 在github上寻找20个最流行开源的React智能体进。根据Star数量降序排列，列出了20个开源React智能体，内容放到了harness/01_market_research/top_20_react_agent.md。
- 我已为这20个智能体在harness/01_market_research中各自建立了独立目录，用于存放调研报告。现已有file_backend.md、tool_channel.md和agent_loop.md 。
- 行业标准总结。写入harness/01_market_research/standard 。
- 我的洋葱架构设计哲学写入了harness/02_project_manager/project_manager.md
全文阅读standard/和project_manager.md，其他文件选择阅读。

【已开发代码】
- 基于harness/03_SRS/infrastructure/file_backend/prompt.md，开发了src/infrastructure/file_backend/init_workspace.py 。
- src/infrastructure/tool_shell/mcp_client.py已通过测试。


【任务】
- src\infrastructure\tool_shell\agent_skills_client.py命令行中，read-properties将L1信息转成json，to-prompt将L1信息转化成xml。能不能换成通俗易懂的词汇，比如to-json或to-xml等等。
- 根据agent_skills_client.py中的开发提示词，请你评估一下agent skills client还缺少哪些功能？我记得Agent skilll中还有reference目录和script目录。这两个目录中的内容加载是否可以添加为新命令，需要评估。

# MCP schema
在tests\mcp_client\README.md中，我展示了一些tests\mcp_client\mcp_client.py的命令行结果。
--list和--list-tool我能看到，但是基于list-tool的结果，我还是没法得知每个工具的调用方式，需要传哪些参数。在开发MCP过程中，我只知道python的sdk要求工具调用信息写入函数注释中。其他编程语言的mcp SDK的工具信息不知道写在哪里。如何获取mcp server中每个函数的传参信息？如果可以获得，请给tests\mcp_client\mcp_client.py添加这个功能。

--list和--status两个参数是否重复？
--verbose和--detail是否重复？
请你移除tests\mcp_client\mcp_client.py中的重复参数和功能。

我认为--help返回中，options和快捷参数说明存在重复描述。请你修改help提示，既要简明，又要给出示例。
