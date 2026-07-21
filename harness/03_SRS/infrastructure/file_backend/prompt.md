# File backend设计
【背景】
我现在正在开发一个Onion Agent，基于洋葱架构。

【已有文档】
- 在github上寻找20个最流行开源的React智能体进。根据Star数量降序排列，列出了20个开源React智能体，内容放到了harness/01_market_research/top_20_react_agent.md。
- 我已为这20个智能体在harness/01_market_research中各自建立了独立目录，用于存放调研报告。现已有file_backend.md、tool_channel.md和agent_loop.md 。
- 行业标准总结。写入harness/01_market_research/standard 。
- 我的洋葱架构设计哲学写入了harness/02_project_manager/project_manager.md

【任务】
阅读全部的已有文档，根据project_manager.md中我的设计，本项目分为5层。首先要实现的就是infrastructure基础设施层的File Backend，有了工作区才好开展智能体开发。
我对agent的工作区有如下要求：
- 一键创建。实现一个src/infrastructure/file_backend/init_workspace.py ,通过python init_workspace.py命令行工具可以在指定目录中初始化一个agent工作区。
命令行参数包括：
```powershell
python init_workspace.py --help

    -n , --name      智能体名称agent name，命名只能以“小写字母/数字/下划线_”组成且不能以数字开头。
    -d , --dir       工作区父目录。如果智能体名称为andy，父目录为D:\onion，则最终初始化的工作区路径为D:\onion\andy 。
    -u , --url       大模型连接地址。
    -k , --key       大模型认证秘钥。
    -m , --model     大模型名称。
    -c , --context   大模型上下文长度。1 M Token就填1000000 。
    -i , --image     大模型能理解图片VLM, yes/y/true表示支持图片理解，no/n/false表示不支持图片理解,默认值default=no
    -s , --system    从命令行接收系统提示词写入AGENT.md中

```
- 最小化原则。我通读了harness/01_market_research/standard/file_backend.md的行业标准，知道应该建立全局工作区、项目工作区、临时工作区三个级别文件后端。但是我现在不需要实现这么复杂的文件后端，开发起来难度也很大。
我计划先创建一个最小化的agent工作区，工作区的目录结构尽可能简单，每个智能体独占一个工作区，每个工作区只有一个jsonl会话文件（每行一个json对象）,会话文件不采用json。
我设计的工作区结构如下，所有的jsonl文件名全小写，所有md文件名全大写。已经经过严格论证，所以请完全遵循如下设计。
```
workspace/
    |—— session.jsonl         唯一会话文件
    |—— provider.toml         模型配置文件
    |—— AGENT.md              系统提示词（行为约束）
    |—— SOUL.md               灵魂（智能体身份、性格、主人信息，只有认证通过的人员才能对智能体发号施令）
    |—— MEMORY.md             从每日记忆中精炼的长期记忆，必须加载，不超过10000 Token。
    |—— heartbeat.jsonl       定时任务，按时序排列的json list
    |—— plan.jsonl            计划看板
    |—— tools.jsonl           工具列表
    |—— memory/YYYYMMDD.md    每日记忆（grep加载到上下文，每次加载不超过10000 Token）
    |—— skills/               存放多个Agent Skills
    |—— mcp_servers.json      mcp server配置文件，需要系统本地安装uv和nodeJS

```
这样一个最小化工作区，单agent单session，有两个好处：第一，麻雀虽小五脏俱全，能跑循环、能调用工具。第二，机动性高，一个路径就能加载，复制粘贴到另一台机器又能运行。
- 无则增，有则修。如果init_workspace.py指向的目录路径不存在，那就创建目录并初始化。但如果工作区目录已存在，则需要智能判断以下几种情况：
1. 如果这个工作区目录为空。直接初始化。
2. 如果这个工作区目录内已有内容。测试provider.toml中的模型（采用openai库，不采用requests库）。尝试加载所有的jsonl为json list，加载json为对象，确保格式正确，能正常加载。包括session.jsonl、heartbeat.jsonl、plan.jsonl、tools.jsonl。如果是空的jsonl文件，就加载成[]空列表，不要报错说加载失败。
工作区中其他md文件和目录只做存活检查，保证有文件或目录即可，不做就绪检查（检查其中内容）。


---

以上是我对File Backend的设计，请你评价我的设计，完成src/infrastructure/file_backend/init_workspace.py的开发


以上是我对File Backend的设计，请你评价我的设计，给出修改意见到harness/03_SRS/infrastructure/file_backend/srs.md