# 开源智能体工作区调研
我现在正在开发一个Onion Agent，基于洋葱架构。
我的洋葱架构设计哲学写入了harness/02_project_manager/project_manager.md
所以我对github上开源的React智能体进行深度调研，根据Star数量降序排列，列出了20个开源React智能体，内容放到了harness/01_market_research/top_20_react_agent.md。

现在请你针对harness/market_research/top_20_react_agent.md中的20个开源React智能体，将其源码通过git clone到harness/01_market_research/clone目录中，并进行更深层次的调研。搞清楚以下问题：
- 每个智能体都需要工作区（一般称为workspace或file backend），该智能体的工作区是在用户属主目录下的还是可自定义路径的？
- 该智能体的工作区的目录结构是什么样的，工作区中每个文件或目录的功能是什么？
- 工作区的创建，是需要用户init初始化，还是伴随agent的创建而创建的。

我已为这20个智能体在harness/01_market_research中各自建立了独立目录，用于存放调研报告。
请你对每个智能体进行深度调研，必须clone源代码到本地后进行研究，回答以上问题，将功能特性总结成file_backend.md报告放到各自的独立目录中。
由于工程量浩大，你可以为每个智能体启动一个子代理进行调研，要充分告诉代理们，它的任务背景和任务是什么，防止子agent跑偏。

后续：现在20个智能体的工作区调研已经完成，请你阅读20份报告，总结20个智能体工作区设计的相同功能，作为智能体工作区行业标准写入harness/01_market_research/standard/file_backend.md。后期我会根据standard行业标准设计我的智能体。


# 开源智能体工具调用调研
【背景】
我现在正在开发一个Onion Agent，基于洋葱架构。

【已有文档】
- 我的洋葱架构设计哲学写入了harness/02_project_manager/project_manager.md
- 在github上寻找20个最流行开源的React智能体进。根据Star数量降序排列，列出了20个开源React智能体，内容放到了harness/01_market_research/top_20_react_agent.md。
- 我已为这20个智能体在harness/01_market_research中各自建立了独立目录，用于存放调研报告。现已有file_backend.md 。
- 行业标准总结。写入harness/01_market_research/standard 。

【任务】
现在请你针对harness/market_research/top_20_react_agent.md中的20个开源React智能体，将其源码通过git clone到harness/01_market_research/clone目录中，并进行更深层次的调研。搞清楚以下问题：
- 每个智能体是否有内置工具，是否支持调用MCP、Agent SKills？
- 工具列表是如何生成的？如何传递给大模型的？工具列表的格式是json还是xml？
- 如何解析大模型发出的工具调用指令？指令出错或残缺时如何修复？如何保证工具指令的准确性？
- 工具执行结果如何传递给大模型？格式是json还是role，通信协议采用openai还是其他协议？
- 我已经调研了file backend，所以想知道20个智能体的file backend是否为工具调用进行适配，比如添加特定的目录和文件来存放工具和配置。

请你对每个智能体进行深度调研，必须clone源代码到本地后进行研究，回答以上问题，将功能特性总结成tool_channel.md报告放到20个智能体各自的独立目录中。
由于工程量浩大，你可以为每个智能体启动一个子代理进行调研，要充分告诉代理们，它的任务背景和任务是什么，防止子agent跑偏。

后续：现在20个智能体的工具调用调研已经完成，请你阅读20份工具调用报告，总结20个智能体工具调用设计的相同功能，作为智能体工具调用行业标准写入harness/01_market_research/standard/tool_channel.md。后期我会根据standard行业标准设计我的智能体。

# 开源智能体Agent Loop调研
【背景】
我现在正在开发一个Onion Agent，基于洋葱架构。

【已有文档】
- 我的洋葱架构设计哲学写入了harness/02_project_manager/project_manager.md
- 在github上寻找20个最流行开源的React智能体进。根据Star数量降序排列，列出了20个开源React智能体，内容放到了harness/01_market_research/top_20_react_agent.md。
- 我已为这20个智能体在harness/01_market_research中各自建立了独立目录，用于存放调研报告。现已有file_backend.md报告和tool_channel.md报告 。
- 行业标准总结。写入harness/01_market_research/standard 。

【任务】
现在请你针对harness/market_research/top_20_react_agent.md中的20个开源React智能体，将其源码通过git clone到harness/01_market_research/clone目录中，并进行更深层次的调研。搞清楚以下问题：
- 这个智能体是否具备Agent Loop，其Agent Loop的主流程是怎样的？需要画出流程图。
- Agent Loop中是否有plan计划，生成的计划被存放到了哪里？大模型如何更新计划，加载计划，是否存在update plan内置工具。
- 是否有sub agent功能。我在MiniMax Code和Langchain中发现了sub agent功能。当智能体遇到繁重而重复的工作，可以创建多个sub agent子智能体来处理。如果有sub agent功能，是如何实现的？内置工具还是第三方skill。
- Agent Loop是如何结束的，有哪几种Loop退出机制。
- ask模式。当智能体运行到一半，突然发现有几个问题至关重要，需要用户确认。可以发出几个选项让用户进行选择。这个智能体是否有ask模式，如何实现的？内置工具还是第三方skill？
- human in the loop（HITL）。智能体如何与用户进行交互，用户如何干预智能体的行为。
- permissions工具调用权限。一般是三种权限：永远同意调用、大模型自动判断是否可调用、永远不允许调用。这个智能体是如何控制权限的？
- 上下文压缩和摘要。当上下文过长时，如何裁剪信息，或者将信息提炼总结成摘要。
- 其他我没想到的问题。

请你对每个智能体进行深度调研，必须clone源代码到本地后进行研究，回答以上问题，将功能特性总结成agent_loop.md报告放到20个智能体各自的独立目录中。
由于工程量浩大，你可以为每个智能体启动一个子代理进行调研，要充分告诉代理们，它的任务背景和任务是什么，防止子agent跑偏。

后续：现在20个智能体的Agent Loop调研已经完成，请你阅读20份Agent Loop报告，总结20个智能体Agent Loop设计的相同功能，作为智能体Agent Loop行业标准写入harness/01_market_research/standard/agent_loop.md。后期我会根据standard行业标准设计我的智能体。
