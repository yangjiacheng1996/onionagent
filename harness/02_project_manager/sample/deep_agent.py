# -*- coding: utf-8 -*-

'''
开发计划：
由于目前市面上的大模型对xml格式的处理能力低下，在生成工具调用指令和理解历史上下文xml数据时，经常出现“遗忘”、“误解”、“指令不全”等问题，
导致生成工具的输出结果不准确，导致智能体大概率无法正常结束，无法完成用户任务，影响了用户的使用体验。
目前市面上所有的智能体都是基于function calling进行工具调用的，工具调用指令被封装成tool_call或者tool_use指令。
客户端解析大模型回答中的tool_call或者tool_use指令后，调用工具，将工具调用添加到大模型调用请求body中。
这种方式的智能体效果比纯xml解析的智能体效果要好很多。Cline过去采用纯xml解析，2025年也放弃这种方式，转而采用function calling。

AI智能体开发，目前有两种主流语言：Python和TypeScript。
针对这两种语言，LangChain提供了领包入住的智能体框架Deep Agent。还有高度可定制化的create_react_agent函数。
前者像整车，开箱即用，上车就走。后者像发动机，可以根据用户需求进行定制，灵活配置，满足用户需求。
Deepagent文档地址 https://docs.langchain.com/oss/python/deepagents/customization

```
'''