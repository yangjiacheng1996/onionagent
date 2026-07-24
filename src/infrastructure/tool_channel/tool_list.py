# -*- coding: utf-8 -*-
"""
================================================================================
Tool Channel - 工具列表汇总模块 (L5 - Infrastructure / tool_channel)
================================================================================

# 开发计划

Onion Agent 走 OpenAI Chat Completions tool 通道调用工具。tool_channel 的职责
是把 tool_shell 的三大 client(buildin / mcp / skills)暴露的工具**汇总成一份
统一 schema 列表**,给 L4 openai_tool_engine 塞进 `tools=[...]` 参数。

详细设计见:
  harness/03_SRS/infrastructure/tool_channel/design.md

## 模块边界

- **本模块不调 LLM**——只产出 tools 列表
- **本模块不解析 tool_calls**——那是 tool_router.py 的事
- **本模块不写 tools.jsonl**——SDK 阶段(L3)再做,本阶段只 in-memory

## 三类工具来源 + 1 类预留

| Tag     | 来源                                              | 函数名格式                            |
|---------|---------------------------------------------------|---------------------------------------|
| buildin | src/infrastructure/buildin_tools/*.py            | onion.buildin.<toolkit>.<tool>        |
| mcp     | mcp_servers.json 配置的远程 MCP Server           | onion.mcp.<server>.<tool>             |
| skill   | skills/<slug>/SKILL.md(渐进式披露 L1 元数据)    | onion.skill.<slug>                    |
| agent   | 预留:update_plan / finish_loop / record_memory  | onion.agent.<tool>                    |

## CLI 用法(所见即所得)

```powershell
# 注册表健康检查
python tool_list.py --status

# 汇总所有 tag 的工具(OpenAI 风格,已按名字排序)
python tool_list.py --to-openai

# 按 tag 筛选
python tool_list.py --tag buildin --to-openai
python tool_list.py --tag mcp --to-openai
python tool_list.py --tag skill --to-openai

# 详细模式:含每个工具的 inputSchema
python tool_list.py --to-openai --detail

# 关闭 MCP 自动连接(快速查看本地 buildin + skill)
python tool_list.py --no-mcp --to-openai

# 看单个工具的 schema
python tool_list.py --tool-info onion.buildin.file_system.list_dir
```

================================================================================
依赖
================================================================================
# src/infrastructure/tool_shell/buildin_client.py(已实现)
# src/infrastructure/tool_shell/mcp_client.py(已实现,async)
# src/infrastructure/tool_shell/agent_skills_client.py(已实现)
# PyYAML(agent_skills_client 已依赖)

================================================================================
退出码
================================================================================
0  - 成功
2  - 参数错误
7  - 工具/工具集不存在
99 - 内部异常
"""

from __future__ import annotations

import argparse
import asyncio
import inspect
import json
import os
import sys
import traceback
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional


# Windows 终端 cp936 默认编码下中文会乱码,统一在脚本入口把 stdout/stderr 切到 UTF-8
if sys.platform == "win32":
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except Exception:
            pass
    del _stream


# ============================================================================
# 常量
# ============================================================================

# 工具名前缀固定为 "onion.",整体三段式 onion.<tag>.<scope>.<tool>
# 详见 design.md §4.2
ONION_PREFIX = "onion"
TOOL_NAME_MAX_LEN = 192  # 整体不超过这个,留余量

# 排序时排除 #开头的注释行(CLI 输出用)
_COMMENT_PREFIX = "#"


# ============================================================================
# Tag 枚举(4 类工具来源)
# ============================================================================
class Tag(str, Enum):
    """
    4 类工具来源标签。继承 str 让它直接可被 json.dumps / 用作 dict key。
    """
    BUILDIN = "buildin"
    MCP = "mcp"
    SKILL = "skill"
    AGENT = "agent"  # 预留


# ============================================================================
# Surrogate 字符清洗(防止 Ollama / 部分 Provider crash)
# 详见 standard/tool_channel.md §5.6
# ============================================================================
def clean_surrogate(text: str) -> str:
    """strip U+D800-U+DFFF 范围孤立的 surrogate,防止下游解码崩溃。"""
    if not text:
        return text
    try:
        return text.encode("utf-8", errors="replace").decode("utf-8", errors="replace")
    except Exception:
        return text


# ============================================================================
# 工具名解析(按 onion.<tag>.<scope>.<tool> 三段切分)
# 详见 design.md §4.2
# ============================================================================
import re

TOOL_NAME_PATTERN = re.compile(
    r"^onion\."
    r"(?P<tag>buildin|mcp|skill|agent)\."
    r"(?P<scope>[a-z0-9_][a-z0-9_-]{0,63})\."
    r"(?P<tool>[a-z0-9_][a-z0-9_-]{0,127})$",
    re.IGNORECASE,
)


def parse_tool_name(name: str) -> Optional[tuple[str, str, str]]:
    """
    解析 onion.<tag>.<scope>.<tool>。
    失败返回 None。

    §4.6 / §5.4:大小写不敏感(LLM 偶尔大写),内部统一转小写。
    """
    if not name:
        return None
    m = TOOL_NAME_PATTERN.match(clean_surrogate(name).strip())
    if not m:
        return None
    # 全部小写化,保证下游 Tag 枚举能识别
    return m.group("tag").lower(), m.group("scope").lower(), m.group("tool").lower()


def make_tool_name(tag: Tag | str, scope: str, tool: str) -> str:
    """组装 onion.<tag>.<scope>.<tool>。"""
    tag_str = tag.value if isinstance(tag, Tag) else str(tag)
    return f"{ONION_PREFIX}.{tag_str}.{scope}.{tool}"


# ============================================================================
# 统一抽象:ToolEntry
# 详见 design.md §8.2
# ============================================================================
@dataclass
class ToolEntry:
    """
    tool_channel 的统一工具条目,跨 buildin / mcp / skill / agent 通用。
    """
    tag: Tag                       # 来源标签
    scope: str                     # toolkit / server / skill slug
    tool: str                      # 工具短名
    full_name: str                 # onion.<tag>.<scope>.<tool>(全局唯一)
    description: str               # 给 LLM 看
    input_schema: dict             # JSON Schema (parameters 字段)
    handler: Optional[Callable] = None       # buildin 直接调 Python 函数;mcp/skill 留 None
    timeout: int = 60
    max_retries: int = 0
    metadata: dict = field(default_factory=dict)  # 额外元数据

    def __post_init__(self):
        if isinstance(self.tag, str) and not isinstance(self.tag, Tag):
            self.tag = Tag(self.tag)
        if not self.full_name:
            self.full_name = make_tool_name(self.tag, self.scope, self.tool)
        # 二次保险:清理 description 中的 surrogate
        if self.description:
            self.description = clean_surrogate(self.description)

    def to_openai_dict(self) -> dict:
        """转 OpenAI Chat Completions tool 格式。"""
        return {
            "type": "function",
            "function": {
                "name": self.full_name,
                "description": self.description or "",
                "parameters": self.input_schema or {"type": "object", "properties": {}},
                "strict": True,
            },
        }


# ============================================================================
# 集中式 ToolRegistry
# 详见 design.md §8.2 + standard/tool_channel.md §4.4
# ============================================================================
@dataclass
class ToolRegistry:
    """
    集中式 Tool Registry。
    关键: 必须是 class 实例,不是模块级 const(避免 reload 重复定义,
    参考 standard/tool_channel.md §4.4 "作者踩坑注释")。
    """
    entries: dict[str, ToolEntry] = field(default_factory=dict)  # full_name -> entry
    clients: dict[Tag, Any] = field(default_factory=dict)        # tag -> client 实例
    _load_errors: list[dict] = field(default_factory=list)       # 加载失败(不致命)
    _register_log: list[dict] = field(default_factory=list)      # 注册流水(给 debug 看)

    def register(self, entry: ToolEntry) -> None:
        """注册一个工具。full_name 重复时后者覆盖前者,记 warning。"""
        if entry.full_name in self.entries:
            self._load_errors.append({
                "type": "duplicate_tool_name",
                "full_name": entry.full_name,
                "message": f"Tool {entry.full_name!r} already registered, overwriting",
            })
        self.entries[entry.full_name] = entry
        self._register_log.append({
            "full_name": entry.full_name,
            "tag": entry.tag.value,
            "scope": entry.scope,
            "tool": entry.tool,
        })

    def register_client(self, tag: Tag | str, client: Any) -> None:
        """注册一个 client 实例,供 router 用。"""
        if isinstance(tag, str):
            tag = Tag(tag)
        self.clients[tag] = client

    def collect_tools(self) -> list[dict]:
        """
        汇总所有 entry → OpenAI tool 列表,按 name 排序。
        §4.5 强烈建议:排序保证 OpenAI prompt cache hit。
        """
        items = sorted(self.entries.values(), key=lambda e: e.full_name)
        return [e.to_openai_dict() for e in items]

    def lookup(self, full_name: str) -> Optional[ToolEntry]:
        """
        按 full_name 查 entry(大小写不敏感,§4.6 工具名规范化)。
        失败再试 case-insensitive 匹配。
        """
        if not full_name:
            return None
        full_name = clean_surrogate(full_name).strip()
        if full_name in self.entries:
            return self.entries[full_name]
        # case-insensitive fallback
        lower = full_name.lower()
        for k, v in self.entries.items():
            if k.lower() == lower:
                return v
        return None

    def by_tag(self, tag: Tag | str) -> list[ToolEntry]:
        """按 tag 筛选 entry。"""
        if isinstance(tag, str):
            tag = Tag(tag)
        return [e for e in self.entries.values() if e.tag == tag]

    def status(self) -> dict:
        """健康检查输出(给 CLI 和 doctor 命令用)。"""
        by_tag_count: dict[str, int] = {t.value: 0 for t in Tag}
        for e in self.entries.values():
            by_tag_count[e.tag.value] += 1
        return {
            "tool_count": len(self.entries),
            "by_tag": by_tag_count,
            "load_errors": list(self._load_errors),
            "clients": {
                tag.value: type(client).__name__ if client else None
                for tag, client in self.clients.items()
            },
        }


# ============================================================================
# 三个收集函数(每个对应一个 client)
# 详见 design.md §8.3
# ============================================================================
def collect_buildin_tools(buildin_client: Any) -> list[ToolEntry]:
    """
    从 BuildinClient 收集工具,注入 onion.buildin.<toolkit>.<tool> 前缀。

    buildin_client.to_openai_schema() 返回的 schema 已经有 "<toolkit>.<tool>" 格式,
    我们只需把前缀 "onion.buildin." 拼到 function.name 前面。
    """
    entries: list[ToolEntry] = []
    # to_openai_schema(sort=False) - 这里自己排,避免重复排序
    schemas = buildin_client.to_openai_schema(sort=False)
    for schema in schemas:
        try:
            raw_name = schema["function"]["name"]  # "toolkit.tool"
            if "." not in raw_name:
                continue
            toolkit, tool = raw_name.split(".", 1)
            full_name = make_tool_name(Tag.BUILDIN, toolkit, tool)

            # 从 buildin_client.tools 拿 handler 和 timeout
            tool_obj = buildin_client.tools.get(f"{toolkit}.{tool}")
            handler = tool_obj.handler if tool_obj else None
            timeout = tool_obj.timeout if tool_obj else 60
            max_retries = getattr(tool_obj, "max_retries", 0) if tool_obj else 0

            entries.append(ToolEntry(
                tag=Tag.BUILDIN,
                scope=toolkit,
                tool=tool,
                full_name=full_name,
                description=schema["function"].get("description", "") or "",
                input_schema=schema["function"].get("parameters", {}) or {},
                handler=handler,
                timeout=timeout,
                max_retries=max_retries,
            ))
        except Exception as e:
            # 任何 schema 异常都跳过(§5.10 unreadable tool 隔离)
            continue
    return entries


async def collect_mcp_tools(mcp_client: Any) -> list[ToolEntry]:
    """
    从 MCPClient 收集工具,注入 onion.mcp.<server>.<tool> 前缀。

    注意: 调用前必须已 connect_all(),否则 connection.tools 为空。
    """
    entries: list[ToolEntry] = []
    for server_name in mcp_client.list_servers():
        connection = mcp_client.servers.get(server_name)
        if not connection or not connection.is_connected:
            continue
        for tool in connection.tools:
            try:
                full_name = make_tool_name(Tag.MCP, server_name, tool.name)
                # MCP tool 对象有 .name / .description / .inputSchema 三个属性
                desc = clean_surrogate(tool.description or "")
                schema = tool.inputSchema or {}
                entries.append(ToolEntry(
                    tag=Tag.MCP,
                    scope=server_name,
                    tool=tool.name,
                    full_name=full_name,
                    description=desc,
                    input_schema=schema,
                    handler=None,  # MCP 通过 client.call_tool() 调,不需要存 handler
                    timeout=60,
                    metadata={"server_type": connection.config.type},
                ))
            except Exception:
                continue
    return entries


def collect_skill_tools(skills_engine: Any) -> list[ToolEntry]:
    """
    从 ProgressiveDisclosureEngine 收集 skill,转成"伪 schema"让 LLM 可以"调用"。

    关键: skill 不是函数,parameters={} + description 强调"激活后获得什么"。
    router 收到 onion.skill.* 的 call → 走特殊路径(详见 tool_router.py §10),
    不传 args,直接读 SKILL.md 的 L2 正文,以 role:tool 回传。
    """
    entries: list[ToolEntry] = []
    try:
        # scan_skills 返回 dict[str, SkillProperties]
        skills_dict = skills_engine.scan_skills()
    except Exception:
        return entries
    for skill_name, props in sorted(skills_dict.items()):
        try:
            full_name = make_tool_name(Tag.SKILL, skill_name, "__load__")
            desc = (
                f"[Agent Skill] 加载 {props.name} 技能,激活后智能体将获得: "
                f"{props.description}\n"
                f"触发:description 中描述的场景出现时调用。无需任何参数——调用即激活。"
            )
            entries.append(ToolEntry(
                tag=Tag.SKILL,
                scope=skill_name,  # skill 的 scope 就是它自己
                tool="__load__",   # skill 没有 tool 概念,固定占位
                full_name=full_name,
                description=clean_surrogate(desc),
                input_schema={"type": "object", "properties": {}, "required": [], "additionalProperties": False},
                handler=None,
                timeout=10,
                metadata={
                    "skill_name": skill_name,
                    "compatibility": props.compatibility,
                    "license": props.license,
                },
            ))
        except Exception:
            continue
    return entries


# ============================================================================
# 主流程:collect_all
# 详见 design.md §8.4
# ============================================================================
async def collect_all(
    workspace_dir: Optional[Path] = None,
    auto_connect_mcp: bool = True,
    tools_dir: Optional[Path] = None,
) -> ToolRegistry:
    """
    汇总所有来源的工具,返回 ToolRegistry。

    Args:
        workspace_dir: agent 工作区根目录(从 file_backend init),
                       用于定位 mcp_servers.json 和 skills/
                       传 None 时 MCP/skill 都跳过,只剩 buildin
        auto_connect_mcp: 是否自动连接 MCP server(False 时 mcp tag 无工具)
        tools_dir: buildin_tools 目录路径(覆盖 buildin_client 默认)

    Returns:
        ToolRegistry 实例,含 entries + clients(供 router 用)
    """
    registry = ToolRegistry()

    # ── 1) Buildin ──────────────────────────────────────────────────────────
    try:
        # 把项目根加入 sys.path,这样可以直接 from src.xxx import
        _ensure_project_root_on_path()
        from src.infrastructure.tool_shell.buildin_client import BuildinClient
        buildin = BuildinClient(tools_dir=tools_dir, auto_load=True)
        for entry in collect_buildin_tools(buildin):
            registry.register(entry)
        registry.register_client(Tag.BUILDIN, buildin)
    except Exception as e:
        registry._load_errors.append({
            "source": "buildin",
            "error": f"{type(e).__name__}: {e}",
            "traceback": traceback.format_exc(),
        })

    # ── 2) MCP(需要 workspace_dir) ──────────────────────────────────────────
    if workspace_dir is not None:
        try:
            from src.infrastructure.tool_shell.mcp_client import MCPClient
            mcp_config = Path(workspace_dir) / "mcp_servers.json"
            if mcp_config.exists():
                mcp = MCPClient(config_path=str(mcp_config))
                if auto_connect_mcp:
                    try:
                        await mcp.connect_all()
                    except Exception as e:
                        registry._load_errors.append({
                            "source": "mcp",
                            "stage": "connect_all",
                            "error": f"{type(e).__name__}: {e}",
                        })
                for entry in collect_mcp_tools(mcp):
                    registry.register(entry)
                registry.register_client(Tag.MCP, mcp)
        except Exception as e:
            registry._load_errors.append({
                "source": "mcp",
                "stage": "import_or_collect",
                "error": f"{type(e).__name__}: {e}",
                "traceback": traceback.format_exc(),
            })

    # ── 3) Skill(需要 workspace_dir/skills/) ───────────────────────────────
    if workspace_dir is not None:
        try:
            from src.infrastructure.tool_shell.agent_skills_client import (
                ProgressiveDisclosureEngine,
            )
            skills_root = Path(workspace_dir) / "skills"
            if skills_root.exists():
                engine = ProgressiveDisclosureEngine(skills_root)
                for entry in collect_skill_tools(engine):
                    registry.register(entry)
                registry.register_client(Tag.SKILL, engine)
        except Exception as e:
            registry._load_errors.append({
                "source": "skill",
                "error": f"{type(e).__name__}: {e}",
                "traceback": traceback.format_exc(),
            })

    # ── 4) Agent(预留,P1 阶段) ─────────────────────────────────────────────
    # TODO: 接入 update_plan / finish_loop / record_memory / ask_user

    return registry


# ============================================================================
# 辅助:把项目根加入 sys.path
# ============================================================================
def _ensure_project_root_on_path() -> None:
    """
    把 onionagent 项目根(本文件在 src/infrastructure/tool_channel/,上 3 级)
    加入 sys.path,这样可以 `from src.infrastructure.tool_shell.xxx import`。
    """
    try:
        # tool_list.py 位于 src/infrastructure/tool_channel/,上 3 级是 onionagent/
        project_root = Path(__file__).resolve().parents[3]
        if str(project_root) not in sys.path:
            sys.path.insert(0, str(project_root))
    except Exception:
        pass


# ============================================================================
# 辅助:JSON Schema 人类可读格式化(参考 buildin_client)
# ============================================================================
def _format_input_schema_human(schema: dict) -> str:
    """与 mcp_client / buildin_client 风格对齐,用于 CLI --tool-info。"""
    if not schema:
        return "    (无参数)"
    properties = schema.get("properties", {}) or {}
    required = set(schema.get("required", []) or [])
    additional = schema.get("additionalProperties", True)
    schema_type = schema.get("type", "object")

    if schema_type != "object" or not properties:
        return "    " + json.dumps(schema, ensure_ascii=False, indent=4).replace("\n", "\n    ")

    lines = [f"    Parameters ({len(properties)}):"]
    max_name_len = max(len(name) for name in properties)
    desc_indent = " " * (6 + max_name_len + 2)

    for name, prop in properties.items():
        prop_type = prop.get("type", "any")
        if prop_type == "array" and "items" in prop:
            item = prop["items"] or {}
            if "$ref" in item:
                prop_type = f"array<{item['$ref'].split('/')[-1]}>"
            else:
                prop_type = f"array<{item.get('type', 'any')}>"
        enum_vals = prop.get("enum")
        enum_hint = ""
        if enum_vals:
            enum_hint = "  enum: " + ", ".join(repr(v) for v in enum_vals)
        default_val = prop.get("default")
        default_hint = ""
        if default_val is not None:
            default_hint = f"  default: {default_val!r}"
        req_mark = "[required]" if name in required else "[optional]"
        lines.append(f"      - {name:<{max_name_len}}  {prop_type}  {req_mark}{enum_hint}{default_hint}")
        desc = (prop.get("description", "") or "").strip()
        if desc:
            for i, desc_line in enumerate(desc.splitlines()):
                lines.append(f"{desc_indent}{desc_line}")
    if required:
        lines.append(f"    Required: {', '.join(sorted(required))}")
    if additional is False:
        lines.append("    Additional properties: 不允许")
    return "\n".join(lines)


# ============================================================================
# CLI 工具函数
# ============================================================================
def _print_status(registry: ToolRegistry) -> int:
    s = registry.status()
    print("Tool Registry Status")
    print("-" * 60)
    print(f"Total tools: {s['tool_count']}")
    for tag_name, count in s["by_tag"].items():
        print(f"  - {tag_name:<8s} {count}")
    print()
    print("Clients:")
    for tag_name, client_name in s["clients"].items():
        print(f"  - {tag_name:<8s} {client_name or '(not registered)'}")
    print()
    errs = s["load_errors"]
    if errs:
        print(f"Load errors: {len(errs)}")
        for e in errs:
            print(f"  - {e.get('source', '?')}: {e.get('error', '?')}")
    else:
        print("Load errors: 0")
    return 0


def _print_openai(registry: ToolRegistry, tag: Optional[Tag] = None, detail: bool = False) -> int:
    """--to-openai:输出 OpenAI 风格 schema 列表(已按 full_name 排序)。"""
    if tag is not None:
        entries = sorted(registry.by_tag(tag), key=lambda e: e.full_name)
    else:
        entries = sorted(registry.entries.values(), key=lambda e: e.full_name)

    if not entries:
        print(f"未找到任何工具(tag={tag.value if tag else 'all'})", file=sys.stderr)
        return 7

    if not detail:
        # 简要模式:直接 dump OpenAI dict 列表
        out = [e.to_openai_dict() for e in entries]
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        # 详细模式:每个工具单独展示 name/description/parameters
        for e in entries:
            print(f"\n  ╭─ {e.full_name}")
            print(f"  │  Tag: {e.tag.value}  Scope: {e.scope}  Tool: {e.tool}")
            print(f"  │  Timeout: {e.timeout}s  MaxRetries: {e.max_retries}")
            print(f"  │  Description: {e.description or '(无描述)'}")
            print(f"  │")
            human_lines = _format_input_schema_human(e.input_schema).splitlines()
            for line in human_lines:
                print(f"  │  {line}")
            print(f"  │")
            print(f"  │  Raw inputSchema (JSON Schema):")
            raw = json.dumps(e.input_schema, ensure_ascii=False, indent=2)
            for line in raw.splitlines():
                print(f"  │    {line}")
            print(f"  ╰─")
        print()
    print(f"# 共 {len(entries)} 个工具(已按 full_name 排序保证 prompt cache hit)", file=sys.stderr)
    return 0


def _print_tool_info(registry: ToolRegistry, full_name: str) -> int:
    info = registry.lookup(full_name)
    if info is None:
        print(f"错误: 找不到工具 {full_name!r}", file=sys.stderr)
        # 模糊匹配提示
        try:
            import difflib
            all_names = list(registry.entries.keys())
            close = difflib.get_close_matches(full_name, all_names, n=3, cutoff=0.4)
            if close:
                print("你可能想找:", file=sys.stderr)
                for c in close:
                    print(f"  {c}", file=sys.stderr)
        except Exception:
            pass
        return 7

    print(f"工具: {info.full_name}")
    print(f"Tag: {info.tag.value}")
    print(f"Scope: {info.scope}")
    print(f"Tool: {info.tool}")
    print(f"Timeout: {info.timeout}s")
    print(f"MaxRetries: {info.max_retries}")
    print(f"Handler: {'present' if info.handler else 'None(走 client.call_tool)'}")
    if info.metadata:
        print(f"Metadata: {json.dumps(info.metadata, ensure_ascii=False)}")
    print(f"Description: {info.description or '(无描述)'}")
    print()
    print(_format_input_schema_human(info.input_schema))
    print()
    print("Raw inputSchema (JSON Schema):")
    print(json.dumps(info.input_schema, ensure_ascii=False, indent=2))
    print()
    print("OpenAI tool 格式:")
    print(json.dumps(info.to_openai_dict(), ensure_ascii=False, indent=2))
    return 0


# ============================================================================
# argparse + 主入口
# ============================================================================
def main():
    parser = argparse.ArgumentParser(
        description="Onion Agent 工具列表汇总(OpenAI function calling schema 格式)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 健康检查
  python tool_list.py --status

  # 汇总所有 tag 的 OpenAI 风格工具列表
  python tool_list.py --to-openai

  # 按 tag 筛选
  python tool_list.py --tag buildin --to-openai
  python tool_list.py --tag mcp --to-openai
  python tool_list.py --tag skill --to-openai

  # 详细模式:每个工具的 inputSchema 完整展示
  python tool_list.py --to-openai --detail

  # 关闭 MCP 自动连接(快速查看本地 buildin + skill)
  python tool_list.py --no-mcp --to-openai

  # 指定 workspace 和 buildin_tools 路径
  python tool_list.py --workspace D:\\onion\\andy --to-openai
  python tool_list.py --tools-dir D:\\other\\buildin_tools --status
        """,
    )
    parser.add_argument(
        "--workspace", "-w", default=None,
        help="agent 工作区根目录(从 file_backend init),用于找 mcp_servers.json 和 skills/",
    )
    parser.add_argument(
        "--tools-dir", default=None,
        help="buildin_tools 目录路径(覆盖 buildin_client 默认)",
    )
    parser.add_argument(
        "--no-mcp", dest="auto_connect_mcp", action="store_false",
        help="不自动连接 MCP server(只看本地 buildin + skill)",
    )
    parser.set_defaults(auto_connect_mcp=True)
    parser.add_argument(
        "--tag", choices=[t.value for t in Tag], default=None,
        help="按 tag 筛选(buildin / mcp / skill / agent)",
    )
    parser.add_argument(
        "--to-openai", action="store_true",
        help="输出 OpenAI Chat Completions 风格 schema 列表(JSON)",
    )
    parser.add_argument(
        "--detail", dest="to_openai_detail", action="store_true",
        help="与 --to-openai 联用,每个工具展示完整 inputSchema",
    )
    parser.add_argument(
        "--tool-info", metavar="FULL_NAME",
        help="查看单个工具的完整 schema,例如 onion.buildin.file_system.read_file",
    )
    parser.add_argument(
        "--status", "-s", action="store_true",
        help="输出工具注册表健康状态",
    )

    args = parser.parse_args()

    workspace_dir = Path(args.workspace) if args.workspace else None
    tools_dir = Path(args.tools_dir) if args.tools_dir else None

    # 收集工具
    try:
        registry = asyncio.run(collect_all(
            workspace_dir=workspace_dir,
            auto_connect_mcp=args.auto_connect_mcp,
            tools_dir=tools_dir,
        ))
    except KeyboardInterrupt:
        print("\n已取消", file=sys.stderr)
        return 130
    except Exception as e:
        print(f"内部异常: {type(e).__name__}: {e}", file=sys.stderr)
        traceback.print_exc()
        return 99

    # 分发命令
    if args.tool_info:
        return _print_tool_info(registry, args.tool_info)
    if args.status:
        return _print_status(registry)
    if args.to_openai:
        tag = Tag(args.tag) if args.tag else None
        return _print_openai(registry, tag=tag, detail=args.to_openai_detail)

    # 默认:列状态
    return _print_status(registry)


if __name__ == "__main__":
    sys.exit(main())
