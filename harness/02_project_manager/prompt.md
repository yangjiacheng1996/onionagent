
# 改良
【背景】
我现在正在使用Python语言（不是Typescript！），开发一个Onion Agent，基于洋葱架构。
我的洋葱架构设计哲学是：智能体的一切活动围绕session.json上下文历史文件，用户发出任务后，智能体创建主session文件，记录智能体之后的一切活动历史。大模型被视作session文件内容的理解器和生成器，围绕session文件的还有压缩器（上下文过长后压缩内容）、工具通道（从session文件中的大模型回答assistant信息中获取工具调用指令，并将工具执行结果写入session文件），sub agent会创建子session文件，并与主session文件相关联。Agent Loop被视作围绕session文件的一种上下文自动累加器。session是唯一的状态机，并规定3种状态：openai状态与大模型交互，tool状态解析指令调用工具回传结果，loop状态执行循环和plan。每个状态之下有多个角色。

【已有文档】
我就是产品经理，一人开发一个智能体，我已经把我的想法放到harness/soul/project_manager.md。

我已经完成了开源React智能体的市场调研。产生了以下文档：
- 什么是洋葱架构。harness/market_research/onion_architecture.md 。
- Openai的三种信息角色。harness/market_research/openai_three_role.md 。
- 最流行的前20名开源React智能体名单。harness/market_research/top_20_react_agent.md 。
- 最流行的前20名开源React智能体深度调研。harness/market_research/deep_dive/ 内含20个md文件。
- 智能体工具调用方式对指令准确性的影响。harness/market_research/tool_accuracy.md 。
- demo程序。我之前简单的开发过智能体，但是没有按照洋葱架构编排，最后烂尾。但是其中有一些代码可以借鉴。全部放到了harness/demo/目录中。
- 通用智能体设计标准。harness/market_research/standard/目录中的几个md文件。

【任务】
你可以阅读harness/market_research已有的调研报告和标准standard报告，对我的project_manager.md进行可行性分析和改良，将改良结果写入harness/soul/better_manager.md。改良结果不应该是v1和v2的对比，而是直接写入改良结果的定版。我重点关注“所见即所得”，这是我后续能否管理这个项目的唯一指标。