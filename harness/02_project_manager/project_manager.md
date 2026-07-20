# 为什么会有harness/soul/这个目录？
需求来自用户，技术偏好来自产品经理。
产品经理的经验和喜好会投射到产品开发过程中的方方面面，影响着软件架构的设计和代码的实现，是一个产品的魂。
产品经理的魂（经验和喜好）是早于项目启动的，所以它早于瀑布式开发流程，如果从瀑布流程的第一步“需求收集”才开始记录harness，会丢失很多关于产品经理的信息。

比如产品经理擅长哪种结构，喜欢什么框架，喜欢什么样的代码实现方式？
为什么会有这个项目，是客户要求，还是产品经理的灵光一闪？产品经理对这个项目的构思有哪些？产品经理对这个项目的红线有哪些？
所以soul/目录就是为了对产品经理进行画像，尽可能多的描述产品经理，以及产品经理对本项目的一些想法。

# 产品经理画像的两种方法
1. 历史工作经历蒸馏进大模型。公司可以导出某个产品经理的所有聊天记录、工作成果，微调进大模型，这样大模型能一次掌握这个人。
2. 通过结构化文档，系统性描述产品经理，效果不如直接蒸馏。

# 产品经理画像。
产品经理（本人）是资深Python算法工程师，主要从事Python自动化脚本开发，包括运维脚本开发（Linux自动化、Kubernetes自动化）和功能测试自动化与RPA机器人。
做过自动化的人都喜欢把一些高度可复用的，原子化的动作封装成库函数，类似RPA中的每条指令。然后基于指令开发测试用例和自动化脚本。
库函数作为核心、基础设施、引擎，供业务脚本调用，库函数不依赖项目中的任何上层业务代码，所以有自动化经验的项目经理倾向于使用洋葱架构，详见harness/01_market_research/onion_architecture.md。

# 产品经理对本项目的看法

### openai库是智能体设计的核心
一个智能体中，什么最重要？是Agent Loop？是大模型？是MCP工具？是Agent Skill？
答案是：都不是，最重要的是openai协议。
我的理解：一个智能体一直在做两件事：拼命调用大模型理解和生成上下文，拼命调用工具丰富上下文。
那么，调用大模型的库函数是什么？openai库。大模型调用工具的方式中，质量最高的是方式是什么？function calling（参考harness/01_market_research/tool_accuracy.md）。
function calling的本质是什么？是openai库中的tool通道，说白了还是openai库。

### 我如何看待大模型
大模型只是一个理解智能体事件历史，并进行决策和内容生成的工具，是智能体中最重要的基础设施。
虽然大模型非常重要，但是不是不可替代，没了大模型，天塌不下来。只要遵守openai库协议的文本处理程序，都可以视为“大模型”。在某些特殊行业，比如智能制造、无人驾驶，其处理核心依赖强化学习神经网络。
如果将强化神经网络通过openai库暴露出去，也可视作大模型。最极端的情况，我把一篇500字小作文暴露成了大模型，参考harness/02_project_manager/sample/openai_server_sse.py。
大模型只能一问一答，没有记忆。openai协议的只能发送和接收三种信息角色信息：system、user、assistant。详见harness/01_market_research/openai_three_role.md。
大模型获取记忆的两种方式：将记忆写入messages，并将messages持久化到本地的jsonl文件中，然后读取jsonl内容塞进大模型的上下文窗口。使用Nvidia显卡和cuda算子，将记忆使用微调进大模型。

### 洋葱架构
本项目智能体以openai库为核心，开发进度计划如下：

**L5-Infrastructure基础设施层**
这一层基本上提供一些基本的json数据对象，重点把控数据类型，编程范式以散装函数式编程为主。
1. file_backend模块。交付物init_file_backend.py用于初始化一个agent目录。后续内置工具buildin_tool每多一个，file_backend可能就要添加目录和文件。
2. buildin_tool模块。优先开发三大内置工具，包括文件系统、本地命令执行、无头浏览器上网。后续会增加Agent Loop相关工具，比如update_plan更新计划看板、finish_loop结束循环、record_memory添加长期记忆。
3. system_prompt模块。交付物update_system_prompt.py和各种template.md（编程类提示词、联网调研类提示词、），其中update_system_prompt.py返回一个符合openai库格式的json对象。
4. tool_shell模块。这个模块适配各种工具协议，调用各种工具。交付物buildin_client.py、mcp_client.py 、 agent_skills_client.py。未来可以适配其他工具协议比如 a2a_client.py。
5. tool_channel模块。负责将所有tool_shell所有client封装成openai库的tool工具，提供统一的工具列表和调用路由规则。交付物tool_list.py和tool_router.py，update_tool_list.py将工具列表写入session.jsonl中。

**L4-Openai引擎层**
这一层就是本项目洋葱架构的核心。只关注大模型的调用。
参考harness/02_project_manager/sample/openai_vlm_client.py ， 将openai库封装成qa引擎（无法调用工具）。参考harness/01_market_research/tool_accuracy.md，开发tool引擎（可调用引擎）。引擎本质上是一个class，接受messages和tool_list，返回assistant信息。
交付物：openai_qa_engine.py 和 openai_tool_engine.py

**L3-SDK接口层**
由于L5基础设施层只返回数据，L4引擎层只调用大模型，都是一些散装的功能。从L3 SDK开始，需要整合L4和L5的功能，封装成智能体常用的功能，编程范式以类class为主。Agent Loop就是在这一层实现的。
1. 初始化工作目录。智能体运行需要工作目录。需要一个函数。执行工作目录初始化结束后，人工向里面放入系统提示词模板、mcp server配置、agent skills。初始化过程遵循“无则增，有则修复”的原则。
2. 创建React智能体。可以效仿Langchain，封装一个create_react_agent()函数，这个函数传入file_backend总路径（用于加载内部文件）、session_id、系统提示词模板名称等参数。

**L2-业务层**
1. 组装L3的类库与函数库，完成智能体流程脚本。这些脚本可以同时被cli命令行客户端、web客户端、QT桌面客户端同时控制。所有后端算法入口在这一层，我不希望L1表现层出现任何后端代码。

**L1-表现层**
这一层主要是客户端，包括cli命令行客户端、web客户端、QT桌面客户端。


### 智能体的几个角色role
1. 系统提示词（"role": "system"）。属于openai三大角色之一，详见harness/01_market_research/openai_three_role.md。
为了构建系统提示词，OpenClaw小龙虾和QwenPaw都有bootstrap程序，询问用户的身份信息，用户希望智能体做什么，有什么行为约束之类的。大模型总结这些信息变成系统提示词。通过bootstrap程序构造系统提示词，以后用户每次使用这个智能体时，提前加载系统提示词。可以不用bootstrap程序，太麻烦，直接写系统提示词就行了，
2. 用户提示词（"role":"user"）。属于openai三大角色之一。在一个上下文历史中，第一个用户提示词和最后一个用户提示词最重要，对日后上下文裁剪有参考作用。
3. 助手提示词（"role":"assistant"）。属于openai三大角色之一。大模型思考、回答、后续工具调用结果都应该是assistant角色。
4. 工具列表（"role":"tool_list"）。这是我自定义的一种角色。目前智能体中一般有三类工具：buildin内置工具（文件系统工具、执行本地命令工具、无头浏览器工具、更新Plan、写入上下文、结束Loop等工具）、MCP Client工具、Agent Skills Client工具。智能体启动后，需要将这些工具汇总成工具列表，传入openai的chat.completion中的tool通道中，工具类型需要区分，以便使用不同Client去调用工具。如果session.jsonl文件中开头是系统提示词，紧接着就应该是tool_list。
5. 计划看板（"role":"plan"）。很多智能体都有计划看板，将用户提示词中的任务拆解成若干子任务，通过内置工具update_plan写入和更新session.jsonl。口诀：一系统，二工具，三用户，四计划，五循环。一个用户提示词后紧跟一个plan。
......更多角色等待规划

以下是session.jsonl的一个案例，仅供参考，后续设计不需要遵从案例。
```json
[
    {"role": "system", "content": "你是一个客服助手，回答简洁不超过5句"},
    {"role": "tool_list", "content": [{tool1},{tool2},{tool3}]},
    // this is png
    {"role": "user", "content":"base64:asoffb32ih34kjb35g3i345346hvgh45c734577c5h123fgfhgfjhg6i"}
    {"role": "user", "content": "订单无法支付怎么办？"},
    // now, start agent loop
    {"role": "plan", "content": "1. 请检查银行卡余额或联系银行确认支付限额。2. 交易平台是否绑定银行卡。"}
    {"role": "assistant", "content": "请检查银行卡余额或联系银行确认支付限额。tool_call:打开手机银行。"}
]

```


### 具身机器人的事件编排器
威尔·史密斯拍摄过一部电影《I,Robot》，又名《机械公敌》，让我第一次知道三大定律（The 3 Laws）。
第一定律：机器人不得伤害人类整体或人类个体，或因不作为而使人类整体或个体受到伤害。
第二定律：机器人必须服从人类的命令，除非这些命令与第一定律相冲突。
第三定律：机器人必须保护自身的存在，只要这种保护不与第一或第二定律相冲突。
如此前卫的电影对于还在上小学的我冲击有多大。

人的生理活动是24小时不间断的，断了就嗝屁了。具身机器需要模仿人类这种生理不间断的特性。通过事件编排器来催动机器人一直存活。
事件编排器（Event Scheduler）：当机器人没有接受到用户指令时，需要持续执行三大定律，机器人公司需要围绕三大定律设计一系列的事件，比如保持自身电量，监听是否有主人的命令，周围是否有人类即将受到伤害。这些机器人待机状态时需要执行的事件称为“基础事件”。
一旦用户（主人）发出指令，先将三大定律注入到system prompt系统提示词中，然后接受用户指令作为一个“用户事件”。
我将神经元信号强度分为10级，则事件编排器应该为每个事件分发一个信号强度，高信号强度的事件优先处理，机器人一次只处理一个事件。比如某个用户事件的信号强度是5，当电量低于20%时，电量事件信号强度从3升到8，8>5，则用户事件中断，自己先去充电。
机器人处理一个事件时，就会启动一个智能体，也就是现在的小龙虾。任务完成时将事件处理结果报告给事件调度器。


## 所见即所得
- 一切皆为字符串，所见即所得。大模型输入和输出都是字符串，命令行也是输入和输出都是字符串，所以在开发智能体的过程中，每个脚本完成一个原子化最小功能，可以直接通过命令行传参测试这个脚本的功能，每次py脚本完成，开发者立刻就能见到效果，否则一口气开发一个大功能，而每个阶段都是黑箱，开发者不知道AI编程的效果，往往在某个致命环境没有及时纠正AI，导致后续大面积返工，一定要让每个程序py文件命令行化，所见即所得。每个py文件的功能原子化。
每个脚本都是围绕session的增删改查，所以项目根目录tests目录中为每个src源码脚本构造一个测试用的session.jsonl文件，并执行测试，调用src源码，将测试后的session文件也放到tests目录中，程序员通过beyond compare这类diff工具就能直观的对比session前后的变化，看到Agent loop每一步的效果，及时调整需求。
举例：
harness/demo/mcp_client.py和harness/demo/agent_skills_client.py 是我之前写的代码，通过命令行可以调用mcp server。这就是我想要的所见即所得，脚本中留有开发计划、有测试用的命令，让产品经理快速知道脚本功能，并手动测试，印象深刻。
我想项目中的任何一个py文件都要做到所见即所得，第一时间让产品经理跑一下，知道功能后及时调整架构，发现问题。


