# -*- coding: utf-8 -*-
"""
开发计划：

MCP官方项目针对多种语言实现了SDK，SDK中包含了Client和Server的实现。
Python SDK官方项目地址 https://github.com/modelcontextprotocol/python-sdk 。
Python SDK 中，Client 的核心类型位于 `mcp` 包中，主要使用方式：

```python
# 官方 Python SDK 中的 MCP Client 用法示例
import asyncio
from mcp.client.stdio import stdio_client
from mcp import ClientSession, StdioServerParameters

async def main():
    # 1. 定义 Server 参数（通过 STDIO 连接）
    server_params = StdioServerParameters(
        command='python3',
        args=['my_mcp_server.py'],
    )

    # 2. 创建 stdio 客户端
    async with stdio_client(server_params) as (stdio, write):
        # 3. 创建 ClientSession
        async with ClientSession(stdio, write) as session:
            # 4. 初始化连接
            await session.initialize()
            # 5. 获取工具列表
            response = await session.list_tools()
            print(f"tools={response}")
            # 6. 调用工具
            result = await session.call_tool('my_tool', {'arg': 'value'})
```
讲解：
stdio_client 返回的是一个包含两个异步内存对象流（Memory Object Stream）的元组，代码中分别被解包赋值给了 stdio 和 write。
具体来说：
第一个元素 stdio（即 read_stream）：
这是一个读取流。它用于接收来自 MCP 服务器的响应。stdio_client 会在后台启动一个异步任务，持续从服务器子进程的标准输出（stdout）中读取数据，将其按行分割并反序列化为 JSON-RPC 消息，然后放入这个流中供你的 ClientSession 消费。
第二个元素 write（即 write_stream）：
这是一个写入流。它用于向 MCP 服务器发送请求。当你的 ClientSession 需要发送消息（如 list_tools 或 call_tool）时，会将消息序列化后写入这个流。后台的另一个异步任务会从这个流中取出消息，并将其写入到服务器子进程的标准输入（stdin）中。
总结来说，stdio_client 的核心作用是：
在本地以子进程的方式启动 MCP 服务器。
在客户端与服务器之间建立基于标准输入/输出（stdio）的通信管道。
返回一对内存流（读流和写流），作为底层传输通道。
随后，你将这对读写流传递给 ClientSession，ClientSession 会基于这两个流封装出更高级的 MCP 协议交互接口（如初始化、调用工具等），让你无需手动处理底层的 JSON-RPC 消息序列化与反序列化。


Python SDK 支持三种传输方式：
StdioClientTransport,
SSEClientTransport,
StreamableHTTPClientTransport,

Cline 案例：
**Cline 明确使用了官方 `@modelcontextprotocol/sdk` 包**：

```typescript
// Cline 源码中的 MCP Client 初始化（简化版）
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import {
  StdioClientTransport,
  SSEClientTransport,
  StreamableHTTPClientTransport,
} from '@modelcontextprotocol/sdk/client/transport.js';

// 创建 Client
const client = new Client(
  { name: "Cline", version: this.clientVersion },
  { capabilities: {} }
);

// 根据配置类型选择 Transport
let transport;
if (config.type === 'stdio') {
  transport = new StdioClientTransport({ command, args, env });
} else if (config.type === 'sse') {
  transport = new SSEClientTransport(new URL(config.url));
} else if (config.type === 'streamableHttp') {
  transport = new StreamableHTTPClientTransport(new URL(config.url));
}

// 连接并初始化
await client.connect(transport);

// 获取工具和资源
connection.server.tools = await this.fetchToolsList(name);
connection.server.resources = await this.fetchResourcesList(name);
connection.server.resourceTemplates = await this.fetchResourceTemplatesList(name);
```

#### Cline MCP 工具调用流程

1. **System Prompt 拼接**：Cline 将已连接的 MCP Server 的 tools 信息格式化后拼接到 System Prompt 中，供大模型理解可用的工具
2. **模型输出解析**：当模型输出 `<use_mcp_tool>` 标签时，Cline 解析出 server_name、tool_name 和 arguments
3. **实际调用**：调用 `McpHub.callTool()` 方法，最终通过 SDK 的 `client.callTool()` 发起 JSON-RPC 请求
4. **结果返回**：工具调用结果返回给模型，模型据此生成最终回复

#### 特色功能

- **智能安装**：Cline 维护了一个 MCP 市场，用户点击安装时，Cline 会**调用大模型自动完成从阅读文档到安装到验证的全流程**（代码位于 `src/core/controller/mcp/downloadMcp.ts`）
- **Auto-Approve**：支持对特定工具设置自动批准，无需用户手动确认
- **多种传输方式**：支持 STDIO、SSE、StreamableHTTP 三种传输方式

### 4.3 结论

**Cline 明确使用官方 `@modelcontextprotocol/sdk` TypeScript SDK**，在此基础上封装了 `McpHub` 管理器，负责连接管理、工具缓存、调用路由等工作。


我需要开发一个MCP Client客户端程序，并对这个客户端提出如下要求：
1. JSON可配置。在mcp_client.py的相同位置创建一个mcp_servers.json，用于配置多个 MCP Server 的连接信息。JSON结构和字段请与Cline保持一致。
2. 支持多种传输方式。根据配置文件中的 type 字段，自动选择 StdioClientTransport、SSEClientTransport 或 StreamableHTTPClientTransport。
3. 异步初始化。客户端在启动时，应异步初始化与各 MCP Server 的连接，确保工具列表和资源信息可用。
4. 错误处理。客户端应对连接失败、工具调用失败等情况进行适当的错误处理，确保程序的健壮性。
5. 命令行化。在MCP Client开发完成后，仿照openai_client.py，将mcp_client.py封装为命令行工具。
6. 命令行测试。我开发了一个mcp_server_uuid32.py用于测试。请你将这个工具配置到mcp_servers.json中。我会手动进行测试。

现在开始编写代码，将代码追加写入本文件下方，不要破坏开发计划。

"""

# 依赖：pip install mcp

import asyncio
import argparse
import json
import sys
import os
from typing import Optional, Any
from dataclasses import dataclass, field
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamable_http_client
from mcp import ClientSession, StdioServerParameters

# ========== 配置 ==========
CONFIG_FILE = "mcp_servers.json"


# ========== 数据结构 ==========
@dataclass
class MCPServerConfig:
    """MCP服务器配置"""
    name: str
    description: str = ""
    baseUrl: str = ""
    command: str = ""
    args: list = field(default_factory=list)
    env: dict = field(default_factory=dict)
    isActive: bool = True
    type: str = "stdio"  # stdio, sse, streamableHttp
    provider: str = ""
    providerUrl: str = ""
    logoUrl: str = ""
    tags: list = field(default_factory=list)

    @classmethod
    def from_dict(cls, name: str, data: dict) -> "MCPServerConfig":
        return cls(
            name=name,
            description=data.get("description", ""),
            baseUrl=data.get("baseUrl", ""),
            command=data.get("command", ""),
            args=data.get("args", []),
            env=data.get("env", {}),
            isActive=data.get("isActive", True),
            type=data.get("type", "stdio"),
            provider=data.get("provider", ""),
            providerUrl=data.get("providerUrl", ""),
            logoUrl=data.get("logoUrl", ""),
            tags=data.get("tags", [])
        )


@dataclass
class MCPServerConnection:
    """MCP服务器连接状态"""
    config: MCPServerConfig
    session: Optional[ClientSession] = None
    tools: list = field(default_factory=list)
    resources: list = field(default_factory=list)
    resource_templates: list = field(default_factory=list)
    is_connected: bool = False
    error: Optional[str] = None
    # Streamable HTTP 需要保持这些流和回调以保持连接活跃
    read_stream: Any = None
    write_stream: Any = None
    get_session_id: Any = None
    # 保存传输层的 context manager，确保连接保持活跃
    transport_context: Any = None


# ========== MCP Client 类 ==========
class MCPClient:
    """
    MCP Client - 支持多种传输方式的MCP客户端
    
    支持的传输方式：
    - stdio: 通过子进程的标准输入/输出通信
    - sse: 通过HTTP + Server-Sent Events通信
    - streamableHttp: 通过Streamable HTTP通信
    """
    
    def __init__(self, config_path: str = CONFIG_FILE):
        self.config_path = config_path
        self.servers: dict[str, MCPServerConnection] = {}
        self._load_config()
    
    def _load_config(self) -> None:
        """加载配置文件"""
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f"配置文件不存在: {self.config_path}")
        
        with open(self.config_path, 'r', encoding='utf-8') as f:
            config_data = json.load(f)
        
        mcp_servers = config_data.get("mcpServers", {})
        for name, data in mcp_servers.items():
            server_config = MCPServerConfig.from_dict(name, data)
            self.servers[name] = MCPServerConnection(config=server_config)
        
        print(f"已加载 {len(self.servers)} 个MCP服务器配置")
    
    async def connect_server(self, name: str) -> bool:
        """
        连接单个MCP服务器
        
        Args:
            name: 服务器名称
        
        Returns:
            连接是否成功
        """
        if name not in self.servers:
            print(f"错误: 未找到服务器 '{name}'", file=sys.stderr)
            return False
        
        connection = self.servers[name]
        config = connection.config
        
        if not config.isActive:
            print(f"跳过非活跃服务器: {name}")
            return False
        
        print(f"正在连接服务器: {name} (type: {config.type})")
        
        try:
            if config.type == "stdio":
                success = await self._connect_stdio(connection)
            elif config.type == "sse":
                success = await self._connect_sse(connection)
            elif config.type == "streamableHttp":
                success = await self._connect_streamable_http(connection)
            else:
                print(f"错误: 不支持的传输类型 '{config.type}'", file=sys.stderr)
                return False
            
            if success:
                connection.is_connected = True
                connection.error = None
                print(f"[OK] 服务器 {name} 连接成功")
                print(f"     工具数量: {len(connection.tools)}")
                print(f"     资源数量: {len(connection.resources)}")
            else:
                connection.is_connected = False
            
            return success
            
        except Exception as e:
            connection.error = str(e)
            connection.is_connected = False
            print(f"[X] 服务器 {name} 连接失败: {e}", file=sys.stderr)
            return False
    
    async def _connect_stdio(self, connection: MCPServerConnection) -> bool:
        """通过STDIO方式连接"""
        config = connection.config
        
        if not config.command:
            print(f"错误: STDIO连接需要指定command", file=sys.stderr)
            return False
        
        server_params = StdioServerParameters(
            command=config.command,
            args=config.args,
            env=config.env if config.env else None
        )
        
        # 创建 transport context manager 并保存
        transport = stdio_client(server_params)
        connection.transport_context = transport
        
        # 进入 context manager 获取流
        stdio, write = await transport.__aenter__()
        connection.read_stream = stdio
        connection.write_stream = write
        
        # 创建 session
        session = ClientSession(stdio, write)
        await session.__aenter__()
        connection.session = session
        
        await session.initialize()
        
        # 获取工具、资源等信息
        tools_response = await session.list_tools()
        connection.tools = tools_response.tools
        
        try:
            resources_response = await session.list_resources()
            connection.resources = resources_response.resources
        except Exception:
            connection.resources = []
        
        try:
            templates_response = await session.list_resource_templates()
            connection.resource_templates = templates_response.resource_templates
        except Exception:
            connection.resource_templates = []
        
        return True
    
    async def _connect_sse(self, connection: MCPServerConnection) -> bool:
        """通过SSE方式连接"""
        config = connection.config
        
        if not config.baseUrl:
            print(f"错误: SSE连接需要指定baseUrl", file=sys.stderr)
            return False
        
        url = config.baseUrl
        if not url.startswith(('http://', 'https://')):
            url = 'http://' + url
        
        headers = {}
        if config.env:
            headers = config.env
        
        # 保存 transport context manager，不退出它以保持连接活跃
        transport = sse_client(url, headers=headers)
        connection.transport_context = transport
        
        # 进入 context manager 获取流
        stdio, write = await transport.__aenter__()
        
        # 保存传输层引用，防止它们在连接后被垃圾回收
        connection.read_stream = stdio
        connection.write_stream = write
        
        # 创建 session
        session = ClientSession(stdio, write)
        await session.__aenter__()
        connection.session = session
        
        await session.initialize()
        
        # 获取工具、资源等信息
        tools_response = await session.list_tools()
        connection.tools = tools_response.tools
        
        try:
            resources_response = await session.list_resources()
            connection.resources = resources_response.resources
        except Exception:
            connection.resources = []
        
        try:
            templates_response = await session.list_resource_templates()
            connection.resource_templates = templates_response.resource_templates
        except Exception:
            connection.resource_templates = []
        
        return True
    
    async def _connect_streamable_http(self, connection: MCPServerConnection) -> bool:
        """通过Streamable HTTP方式连接"""
        import httpx
        
        config = connection.config
        
        if not config.baseUrl:
            print(f"错误: Streamable HTTP连接需要指定baseUrl", file=sys.stderr)
            return False
        
        url = config.baseUrl
        if not url.startswith(('http://', 'https://')):
            url = 'http://' + url
        
        # Streamable HTTP 协议需要客户端声明 Accept: application/json, text/event-stream
        # 服务器要求同时支持 application/json 和 text/event-stream
        headers = {"Accept": "application/json, text/event-stream"}
        
        # 如果配置了 env，合并到 headers 中
        if config.env:
            headers.update(config.env)
        
        http_client = httpx.AsyncClient(headers=headers)
        
        # 保存 transport context manager，不退出它以保持连接活跃
        transport = streamable_http_client(url, http_client=http_client)
        connection.transport_context = transport
        
        # 进入 context manager 获取流
        read, write, get_session_id = await transport.__aenter__()
        
        # 保存传输层引用，防止它们在连接后被垃圾回收
        connection.read_stream = read
        connection.write_stream = write
        connection.get_session_id = get_session_id
        
        # 创建 session
        session = ClientSession(read, write)
        await session.__aenter__()
        connection.session = session
        
        await session.initialize()
        
        # 获取工具、资源等信息
        tools_response = await session.list_tools()
        connection.tools = tools_response.tools
        
        try:
            resources_response = await session.list_resources()
            connection.resources = resources_response.resources
        except Exception:
            connection.resources = []
        
        try:
            templates_response = await session.list_resource_templates()
            connection.resource_templates = templates_response.resource_templates
        except Exception:
            connection.resource_templates = []
        
        return True
    
    async def connect_all(self) -> dict[str, bool]:
        """
        连接所有MCP服务器
        
        Returns:
            各服务器的连接结果字典
        """
        results = {}
        for name in self.servers:
            results[name] = await self.connect_server(name)
        return results
    
    async def call_tool(self, server_name: str, tool_name: str, arguments: dict = None) -> Any:
        """
        调用指定服务器的tool
        
        Args:
            server_name: 服务器名称
            tool_name: 工具名称
            arguments: 工具参数
        
        Returns:
            工具调用结果
        
        Raises:
            ValueError: 服务器不存在或未连接
        """
        if server_name not in self.servers:
            raise ValueError(f"服务器 '{server_name}' 不存在")
        
        connection = self.servers[server_name]
        
        if not connection.is_connected or connection.session is None:
            raise ValueError(f"服务器 '{server_name}' 未连接或会话无效")
        
        try:
            result = await connection.session.call_tool(tool_name, arguments or {})
            return result.content
        except Exception as e:
            raise RuntimeError(f"调用工具 '{tool_name}' 失败: {e}") from e
    
    def list_servers(self) -> list[str]:
        """列出所有已配置的服务器名称"""
        return list(self.servers.keys())
    
    def list_tools(self, server_name: str = None) -> dict[str, list]:
        """
        列出服务器的工具信息
        
        Args:
            server_name: 服务器名称，如果为None则列出所有服务器的工具
        
        Returns:
            服务器名称到工具列表的字典
        """
        if server_name:
            if server_name not in self.servers:
                return {}
            return {server_name: self._format_tools(self.servers[server_name].tools)}
        
        result = {}
        for name, conn in self.servers.items():
            result[name] = self._format_tools(conn.tools)
        return result
    
    def _format_tools(self, tools: list) -> list[dict]:
        """格式化工具列表"""
        formatted = []
        for tool in tools:
            formatted.append({
                "name": tool.name,
                "description": tool.description or "",
                "inputSchema": tool.inputSchema
            })
        return formatted

    def get_tool_info(self, server_name: str, tool_name: str) -> Optional[dict]:
        """
        获取单个工具的完整信息（含 inputSchema）

        inputSchema 是 MCP 协议规定的标准 JSON Schema，
        所有语言的 SDK 都会通过 tools/list 响应这个字段。

        Args:
            server_name: 服务器名称
            tool_name: 工具名称

        Returns:
            工具信息字典，包含 name / description / inputSchema；
            找不到返回 None
        """
        if server_name not in self.servers:
            return None

        connection = self.servers[server_name]
        if not connection.is_connected:
            return None

        for tool in connection.tools:
            if tool.name == tool_name:
                return {
                    "name": tool.name,
                    "description": tool.description or "",
                    "inputSchema": tool.inputSchema or {},
                }
        return None

    def find_tool(self, tool_name: str) -> list[tuple[str, dict]]:
        """
        跨所有服务器查找指定名称的工具

        Args:
            tool_name: 工具名称

        Returns:
            (server_name, tool_info) 元组列表
        """
        results = []
        for server_name, conn in self.servers.items():
            if not conn.is_connected:
                continue
            for tool in conn.tools:
                if tool.name == tool_name:
                    results.append((server_name, {
                        "name": tool.name,
                        "description": tool.description or "",
                        "inputSchema": tool.inputSchema or {},
                    }))
        return results

    @staticmethod
    def _format_input_schema_human(schema: dict) -> str:
        """
        把 JSON Schema 格式化成人类可读形式

        输出示例:
          Parameters:
            - path: string  [required]
                要读取的文件路径
            - head: integer  [optional]
                只读取前 N 行
        """
        if not schema:
            return "    (无参数)"

        properties = schema.get("properties", {}) or {}
        required = set(schema.get("required", []) or [])
        additional = schema.get("additionalProperties", True)
        schema_type = schema.get("type", "object")

        if schema_type != "object" or not properties:
            # 退化情况：直接 dump
            return "    " + json.dumps(schema, ensure_ascii=False, indent=4).replace("\n", "\n    ")

        lines = [f"    Parameters ({len(properties)}):"]
        max_name_len = max(len(name) for name in properties)
        # 描述行的缩进：与参数行第一个字符对齐（"      - " = 8 字符）+ name 宽度 + 2 空格
        desc_indent = " " * (8 + max_name_len + 2)

        for name, prop in properties.items():
            prop_type = prop.get("type", "any")
            # 数组类型可能用 items 表示元素类型
            if prop_type == "array" and "items" in prop:
                item = prop["items"] or {}
                if "$ref" in item:
                    prop_type = "array<{}>".format(item["$ref"].split("/")[-1])
                else:
                    prop_type = "array<{}>".format(item.get("type", "any"))

            # enum 提示
            enum_vals = prop.get("enum")
            enum_hint = ""
            if enum_vals:
                enum_hint = "  enum: " + ", ".join(repr(v) for v in enum_vals)

            # default 提示
            default_val = prop.get("default")
            default_hint = ""
            if default_val is not None:
                default_hint = f"  default: {default_val!r}"

            # 必需标识
            req_mark = "[required]" if name in required else "[optional]"

            lines.append(f"      - {name:<{max_name_len}}  {prop_type}  {req_mark}{enum_hint}{default_hint}")

            # 描述（如果有）
            desc = prop.get("description", "").strip()
            if desc:
                for i, desc_line in enumerate(desc.splitlines()):
                    lines.append(f"{desc_indent}{desc_line}")

        if required:
            lines.append(f"    Required: {', '.join(sorted(required))}")
        if additional is False:
            lines.append("    Additional properties: 不允许")

        return "\n".join(lines)
    
    def get_server_status(self) -> dict[str, dict]:
        """获取所有服务器的状态"""
        status = {}
        for name, conn in self.servers.items():
            status[name] = {
                "connected": conn.is_connected,
                "tools_count": len(conn.tools),
                "resources_count": len(conn.resources),
                "error": conn.error,
                "type": conn.config.type
            }
        return status
    
    async def close(self) -> None:
        """关闭所有连接。

        关闭顺序很关键：先 transport，再 session。

        原因：mcp.BaseSession 的 _receive_loop 子 task 内部对 read_stream 用了
        ``async with``，stream 的 cancel scope 绑在子 task 上。如果先关 session，
        session.__aexit__ 会触发 stream aclose，cancel scope 跨 task 退出，anyio
        抛 ``RuntimeError: Attempted to exit cancel scope in a different task``。

        改成先关 transport：stdio_client 的 __aexit__ 会关掉子进程 stdin、wait
        进程退出、aclose 四个 memory stream；read_stream 被 aclose 后，
        _receive_loop 收到 ClosedResourceError 自然退出，子 task 内任何 cancel
        scope 都在它自己 task 里正常清理。这时再关 session._task_group，里面
        已经没活任务了，__aexit__ 顺滑通过。

        关闭阶段所有异常一律静默：这是 mcp + anyio + Windows 的已知交互问题，
        不会影响业务正确性。
        """
        for name, conn in self.servers.items():
            # 1) 先关 transport context（stdio / sse / streamable_http）
            if conn.transport_context is not None:
                try:
                    await conn.transport_context.__aexit__(None, None, None)
                except BaseException:  # noqa: BLE001 - 关闭期静默
                    pass
                conn.transport_context = None

            # 2) 再关 session（此时 _receive_loop 应该已经因 stream 关闭而退出）
            if conn.session is not None:
                try:
                    await conn.session.__aexit__(None, None, None)
                except BaseException:  # noqa: BLE001 - 关闭期静默
                    pass
                conn.session = None

            conn.is_connected = False
            conn.read_stream = None
            conn.write_stream = None
            conn.get_session_id = None


# ========== 命令行接口 ==========
async def async_main(args):
    """异步主函数"""
    client = MCPClient(args.config)
    
    try:
        # 列出所有服务器状态（需要先连接）
        if args.list:
            print("正在初始化MCP客户端...")
            await client.connect_all()

            status = client.get_server_status()
            print("\nMCP 服务器状态:")
            print("-" * 60)
            for name, info in status.items():
                status_str = "[OK] 已连接" if info["connected"] else "[X] 未连接"
                print(f"  {name}: {status_str} ({info['type']})")
                print(f"    工具数: {info['tools_count']}, 资源数: {info['resources_count']}")
                if info["error"]:
                    print(f"    错误: {info['error']}")
            print("-" * 60)
            return

        # 连接所有服务器
        print("正在初始化MCP客户端...")
        results = await client.connect_all()

        # 输出连接结果
        success_count = sum(1 for v in results.values() if v)
        print(f"\n连接完成: {success_count}/{len(results)} 个服务器成功")
        
        # 调用工具
        if args.call_tool:
            parts = args.call_tool.split('.', 1)
            if len(parts) != 2:
                print("错误: --call-tool 参数格式应为 server_name.tool_name", file=sys.stderr)
                sys.exit(1)
            
            server_name, tool_name = parts
            arguments = {}
            
            # 解析JSON参数
            if args.arguments:
                try:
                    arguments = json.loads(args.arguments)
                except json.JSONDecodeError as e:
                    print(f"错误: 无效的JSON参数: {e}", file=sys.stderr)
                    sys.exit(1)
            
            try:
                print(f"\n调用工具: {server_name}.{tool_name}")
                print(f"参数: {arguments}")
                result = await client.call_tool(server_name, tool_name, arguments)
                print(f"\n结果:")
                for item in result:
                    print(item.text if hasattr(item, 'text') else str(item))
            except Exception as e:
                import traceback
                print(f"错误: {e}", file=sys.stderr)
                traceback.print_exc()
                sys.exit(1)
        
        # 列出工具
        if args.list_tools:
            tools = client.list_tools()
            for server_name, server_tools in tools.items():
                print(f"\n服务器 '{server_name}' 的工具:")
                if not server_tools:
                    print("  (无工具)")
                else:
                    for tool in server_tools:
                        if args.list_tools_detail:
                            # 详细模式：展示 name + description + inputSchema（人类可读 + JSON）
                            print(f"\n  ╭─ {tool['name']}")
                            desc = tool['description'] or '(无描述)'
                            print(f"  │  Description: {desc}")
                            print(f"  │")
                            # 人类可读的 schema（每行都加上 │  前缀对齐）
                            human_lines = MCPClient._format_input_schema_human(tool['inputSchema']).splitlines()
                            for line in human_lines:
                                print(f"  │  {line}")
                            print(f"  │")
                            print(f"  │  Raw inputSchema (JSON Schema):")
                            raw = json.dumps(tool['inputSchema'], ensure_ascii=False, indent=2)
                            for line in raw.splitlines():
                                print(f"  │    {line}")
                            print(f"  ╰─")
                        else:
                            print(f"  - {tool['name']}: {tool['description'] or '(无描述)'}")
            return

        # 查看单个工具的详细信息
        if args.tool_info:
            spec = args.tool_info

            if '.' in spec:
                # 格式: server_name.tool_name
                server_name, tool_name = spec.split('.', 1)
                tool_info = client.get_tool_info(server_name, tool_name)
                if tool_info is None:
                    # 再确认下：是不是连 server 都不存在
                    if server_name not in client.servers:
                        print(f"错误: 服务器 '{server_name}' 不存在", file=sys.stderr)
                    elif not client.servers[server_name].is_connected:
                        print(f"错误: 服务器 '{server_name}' 未连接", file=sys.stderr)
                    else:
                        print(f"错误: 在 '{server_name}' 中找不到工具 '{tool_name}'", file=sys.stderr)
                        # 提示一下该 server 有哪些工具
                        names = [t['name'] for t in client.list_tools(server_name).get(server_name, [])]
                        if names:
                            print(f"提示: '{server_name}' 上的工具: {', '.join(names)}", file=sys.stderr)
                    sys.exit(1)

                print(f"工具: {server_name}.{tool_name}")
                print(f"Description: {tool_info['description'] or '(无描述)'}")
                print()
                print(MCPClient._format_input_schema_human(tool_info['inputSchema']))
                print()
                print("Raw inputSchema (JSON Schema):")
                print(json.dumps(tool_info['inputSchema'], ensure_ascii=False, indent=2))
            else:
                # 只给 tool_name：跨所有 server 查找
                tool_name = spec
                matches = client.find_tool(tool_name)
                if not matches:
                    print(f"错误: 在任何已连接服务器上找不到工具 '{tool_name}'", file=sys.stderr)
                    print("\n所有可用工具:", file=sys.stderr)
                    for server_name, server_tools in client.list_tools().items():
                        names = [t['name'] for t in server_tools]
                        if names:
                            print(f"  {server_name}: {', '.join(names)}", file=sys.stderr)
                    sys.exit(1)

                if len(matches) > 1:
                    print(f"工具 '{tool_name}' 在多个服务器上存在，输出全部匹配:", file=sys.stderr)
                    for s, _ in matches:
                        print(f"  - {s}.{tool_name}", file=sys.stderr)
                    print(f"请用 --tool-info <server_name>.<tool_name> 指定具体服务器", file=sys.stderr)
                    print(file=sys.stderr)

                for server_name, tool_info in matches:
                    print(f"工具: {server_name}.{tool_name}")
                    print(f"Description: {tool_info['description'] or '(无描述)'}")
                    print()
                    print(MCPClient._format_input_schema_human(tool_info['inputSchema']))
                    print()
                    print("Raw inputSchema (JSON Schema):")
                    print(json.dumps(tool_info['inputSchema'], ensure_ascii=False, indent=2))
                    if len(matches) > 1:
                        print("\n" + "─" * 60)
    finally:
        await client.close()


def main():
    parser = argparse.ArgumentParser(
        description='MCP Client 命令行客户端',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
使用示例:
  # 默认：连接 mcp_servers.json 中所有 server，输出连接摘要
  python mcp_client.py

  # --list：查看每个 server 的连接状态、传输类型、工具/资源数、错误信息
  python mcp_client.py --list

  # --list-tools：列出所有 server 的全部工具（name + description）
  python mcp_client.py --list-tools

  # --list-tools --detail：额外输出每个 tool 的 inputSchema（参数表 + 原始 JSON）
  python mcp_client.py --list-tools --detail

  # --tool-info server.tool_name：查看某个 server 上某个 tool 的完整 schema
  python mcp_client.py --tool-info searxng.searxng_web_search

  # --tool-info tool_name：跨所有 server 搜索（自动定位到唯一的那个）
  python mcp_client.py --tool-info searxng_web_search

  # --call-tool：调用工具（SPEC 格式同 --tool-info）
  python mcp_client.py --call-tool filesystem.read_text_file
  python mcp_client.py --call-tool filesystem.read_text_file --arguments '{"path": "C:/workspace/README.md"}'
  python mcp_client.py --call-tool searxng.searxng_web_search --arguments '{"query": "MCP protocol", "num_results": 5}'

  # --config：使用非默认配置文件
  python mcp_client.py --config my_servers.json --list-tools

inputSchema 说明:
  MCP 协议规定所有 server 在 tools/list 响应中必须为每个 tool 携带
  inputSchema (标准 JSON Schema) 字段。客户端不依赖 server 端的代码注释
  就能拿到完整的参数定义，本命令就是把这个 schema 印出来。
        '''
    )

    parser.add_argument('--config', '-c', default=CONFIG_FILE,
                        help='配置文件路径（默认 mcp_servers.json）')
    parser.add_argument('--list', '-l', action='store_true',
                        help='列出所有服务器状态')
    parser.add_argument('--list-tools', action='store_true',
                        help='列出所有工具')
    parser.add_argument(
        '--list-tools-detail', '--detail', dest='list_tools_detail',
        action='store_true',
        help='与 --list-tools 联用，输出每个 tool 的 inputSchema'
    )
    parser.add_argument(
        '--tool-info', metavar='SPEC',
        help='查看单个 tool 的完整 schema。SPEC: server.tool_name 或 tool_name'
    )
    parser.add_argument('--call-tool', metavar='SPEC',
                        help='调用指定工具。SPEC 格式同 --tool-info')
    parser.add_argument('--arguments', metavar='JSON',
                        help='传给 tool 的参数（JSON 字符串）')
    
    args = parser.parse_args()
    
    try:
        asyncio.run(async_main(args))
    except FileNotFoundError as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n已取消", file=sys.stderr)
        sys.exit(130)


if __name__ == '__main__':
    main()