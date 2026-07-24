# buildin工具设计
【背景】
我现在正在开发一个Onion Agent，基于洋葱架构。

【已有文档】
- 在github上寻找20个最流行开源的React智能体进。根据Star数量降序排列，列出了20个开源React智能体，内容放到了harness/01_market_research/top_20_react_agent.md。
- 我已为这20个智能体在harness/01_market_research中各自建立了独立目录，用于存放调研报告。现已有file_backend.md、tool_channel.md和agent_loop.md 。
- 行业标准总结。写入harness/01_market_research/standard 目录中，内含file_backend.md、tool_channel.md和agent_loop.md 。
- 我的洋葱架构设计哲学写入了harness/02_project_manager/project_manager.md 。
- function calling对智能体工具指令准确性的影响：harness/01_market_research/tool_accuracy.md 。
全文阅读standard/和project_manager.md，其他文件选择阅读。

【已开发代码】
- 基于harness/03_SRS/infrastructure/file_backend/prompt.md，开发了src/infrastructure/file_backend/init_workspace.py 。
- src/infrastructure/tool_shell/mcp_client.py已通过测试，可以调用mcp server。
- src/infrastructure/tool_shell/agent_skills_client.py已通过测试，可以读取skill的L1、L2、L3级别提示词。

【任务】
根据project_manager.md我的设计，智能体需要内置工具，包括三大基本工具：文件系统工具、本地命令行执行、无头浏览器。
可能还有Agent Loop内置工具：update_plan更新计划看板、finish_loop结束智能体循环。有的智能体不需要Loop工具，所以后续再讨论。
1. 请你帮我实现buildin三大工具，通过调用函数即可:
操作文件系统src/infrastructure/buildin_tools/file_system.py、
执行命令src/infrastructure/buildin_tools/command_line.py、
无头浏览器联网搜索src/infrastructure/buildin_tools/non_head_browser.py。
这三个工具的开发可以参考已有的智能体harness/01_market_research/clone。每个工具的py文件需要支持命令行测试，所见即所得。
2. 仿照mcp_client.py和agent_skills_client.py，为内置工具也开发一个src/infrastructure/tool_shell/buildin_client.py ，统一调用内置工具。

【后续】
我认为当前的file system工具是针对文本文件的。还差3个命令
1. copy，复制文件或文件夹
2. mv ，剪切或重命名
3. properties ， 文件或文件夹的属性（比如判断是文件还是文件夹、文件或文件夹大小、最近修改时间、权限等等）

我执行了python non_head_browser.py --help，发现你目前实现了两个功能，第一个是search，专门搜索DuckDuckGO。第二个是fetch，抓取网页内容。
首先评价第一个search。我需要的是一个browser automation工具，而不是单一的search工具。给出一个url，工具能打开网页并给出html，或者markdown化的网页。
我保存了一堆browser Automation浏览器自动化相关的MCP工具，参考 https://github.com/yangjiacheng1996/awesome-mcp-servers/blob/main/README-zh.md#browser-automation
可以发现出现了一个高频词“Playwright”，这是一个无头浏览器。
再评价fetch。
我之前在Cline中安装过fetch的mcp server，配置是这样的：
```json
"fetch": {
			"command": "npx",
			"args": [
				"mcp-fetch-server"
			],
			"env": {
				"DEFAULT_LIMIT": "50000"
			},
			"alwaysAllow": [
				"fetch_markdown",
				"fetch_txt",
				"fetch_html",
				"fetch_readable"
			]
		},

```
MCP官方的fetch工具已经移除了，所以你可以参考其他fetch工具的实现，我给出两个项目：
1. https://github.com/zcaceres/fetch-mcp
2. https://github.com/jae-jae/fetcher-mcp
其中fetcher-mcp是基于Playwright实现的。
所以，我计划以Playwright为核心打造non_head_browser.py，你先将Playwright相关的MCP server项目clone到本项目的harness/01_market_research/clone 中，然后每个mcp项目创建一个子agent进行深度分析几个问题：
1. 是否需要在系统中额外安装Playwright无头浏览器？
2. 实现了哪些浏览器自动化功能？URL网页访问如何实现的？网页HTML过大怎么处理？如何压缩？
3. fetch功能如何实现的。
提炼Playwright工具的相似功能，作为行业标准，写入harness/01_market_research/standard/playwright.md


# non_head_browser
【背景】
我现在正在开发一个Onion Agent，基于洋葱架构。

【已有文档】
- 在github上寻找20个最流行开源的React智能体进。根据Star数量降序排列，列出了20个开源React智能体，内容放到了harness/01_market_research/top_20_react_agent.md。
- 我已为这20个智能体在harness/01_market_research中各自建立了独立目录，用于存放调研报告。现已有file_backend.md、tool_channel.md和agent_loop.md 。
- 行业标准总结。写入harness/01_market_research/standard 目录中，内含file_backend.md、tool_channel.md、agent_loop.md、playwright.md 。
- 我的洋葱架构设计哲学写入了harness/02_project_manager/project_manager.md 。
- function calling对智能体工具指令准确性的影响：harness/01_market_research/tool_accuracy.md 。
全文阅读standard/和project_manager.md，其他文件选择阅读。

【已开发代码】
- 基于harness/03_SRS/infrastructure/file_backend/prompt.md，开发了src/infrastructure/file_backend/init_workspace.py 。
- src/infrastructure/tool_shell/mcp_client.py已通过测试，可以调用mcp server。
- src/infrastructure/tool_shell/agent_skills_client.py已通过测试，可以读取skill的L1、L2、L3级别提示词。
- src/infrastructure/buildin_tools/中file_system.py是文件系统工具包，command_line.py是本地命令行执行工具包，non_head_browser.py是无头浏览器工具包。

【任务】
根据project_manager.md我的设计，智能体需要内置工具，包括三大基本工具：文件系统工具、本地命令行执行、无头浏览器。
1. 根据harness/01_market_research/standard/playwright.md的行业标准，重写 src/infrastructure/buildin_tools/non_head_browser.py 使其成为内置浏览器工具。
由于行业标准中推荐双模式：http零浏览器模式+PW的JS渲染模式。所以脚本就按照双模式开发。但是本人处于中国大陆，所以我建议non_head_browser.py中的http模式的web_search工具，可以根据系统时区来选择搜索引擎。
如果系统时区是东八区北京，或者系统语言是简体中文，或者其他现象能够证明系统处于中国大陆，则并行调用Baidu百度、Sougou搜狗、360搜索这三大墙内（Great Fire Wall）搜索引擎，降序排列最相关结果，我常用的SearXNG就支持多搜索引擎同时搜索时。
如果判断系统不处于中国大陆，则在自由网络中，请并行调用Google谷歌、Bing必应、Yahoo雅虎三大搜索引擎，降序排列最相关搜索结果。
关于browser_install，由于我的这个智能体使用场景大部分是内网，所以无法联网下载Chromium，并且无头浏览器不是很大，请在src/infrastructure/buildin_tools目录中内置一个Chromium并让脚本适配这个Chromium。browser_install功能依然保留，适配联网环境。
2. 仿照mcp_client.py和agent_skills_client.py，为内置工具也开发一个src/infrastructure/tool_shell/buildin_client.py ，统一调用内置工具。
3. 按照我的计划Onion agent这个产品的内置工具是免安装、高效稳定的。所以non_head_browser.py需要实现完整的浏览器自动化功能，不能因为功能缺失导致大模型无法充分调用Playwright操作Chromium浏览器。请你从P0、P1、P2中挑选功能，重写src/infrastructure/buildin_tools/non_head_browser.py，以实现这些功能