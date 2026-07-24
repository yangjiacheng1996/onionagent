# -*- coding: utf-8 -*-
"""
================================================================================
Buildin Tools Client - 内置工具统一调用客户端 (L5 - Infrastructure / tool_shell)
================================================================================

# 开发计划

Onion Agent 的内置工具(三大基础工具集:filesystem / command_line / non_head_browser)各自
提供原子化函数,直接 import 即可使用。但对于上层的 tool_channel(汇总工具列表)和
Agent Loop(按名字路由工具调用)来说,需要一个**统一调用入口**——这就是 buildin_client
的职责。

## 设计哲学(对照 harness/01_market_research/standard/tool_channel.md)

按照行业标准(tool_channel.md §1.2 原则二:工具类型统一抽象、§4.4 集中式 ToolRegistry、
§4.5 工具名排序 for prompt cache hit、§3.1 JSON Schema 强制标准、§6.4 错误标记 isError)
buildin_client 必须做到:

- **协议中立 + Provider 无关**: 内部用 OpenAI Chat Completions 风格 schema(由 source
  端的 TOOL_SCHEMAS 透传),Anthropic / Ollama / GLM 切换零改动
- **集中式 ToolRegistry**: 一个 BuildinClient 实例管理所有 buildin tool(自动发现 +
  收集),不再"if-else 散落"
- **工具名前缀化**: 用 `toolkit.tool` 格式(如 `file_system.read_file`)防重名,
  与 mcp_client 的 `server.tool` 命名一致
- **OpenAI function calling 标准**: TOOL_SCHEMAS 已经是 OpenAI 风格,client 透传不做修改
- **工具名排序**: 输出给 LLM 的工具列表按 full_name 排序,保证 OpenAI prompt cache hit
- **所见即所得 CLI**: 每个功能都能命令行化,产品经理跑一下就能验证(参考
  harness/02_project_manager/project_manager.md §所见即所得)

## 与 mcp_client / agent_skills_client 的关系

三个 client 共同构成 Onion Agent 的 tool_shell 模块(参考 project_manager.md §洋葱架构
L5 tool_shell):
  - mcp_client.py        : 远程 MCP Server 客户端(异步、stdio/sse/streamable_http)
  - agent_skills_client.py : 本地 Agent Skills 客户端(目录扫描 + 渐进式披露)
  - **buildin_client.py**  : **同进程内置工具客户端(动态 import,无网络)**

三者都遵守**同一个对外形状**:
  1. 一个主类(MCPClient / ProgressiveDisclosureEngine / BuildinClient)
  2. 列出所有工具 + 跨源查找 + 按名调用 + 获取 schema 详情
  3. CLI 化(--list / --list-tools / --tool-info / --call-tool)

这层"形状对齐"让上游 tool_channel 可以用统一的方式聚合三类工具。

## 内置工具的约定接口(duck typing)

每个 buildin 工具模块必须暴露两个全局变量:

  TOOL_SCHEMAS: list[dict]    # OpenAI 风格 schema 列表
      每项形如:
        {
          "type": "function",
          "function": {
            "name": "read_file",
            "description": "...",
            "parameters": {"type": "object", "properties": {...}, "required": [...]}
          }
        }

  TOOL_HANDLERS: dict[str, Callable]    # 工具名 → 处理函数
      例: {"read_file": <function read_file>, "write_file": <function write_file>}

目前已实现:
  - file_system.py       (8 工具:read/write/edit/copy/move/delete/list/get_properties)
  - command_line.py      (1 工具:run_command)
  - non_head_browser.py  (28 工具:web_search/fetch/browser_*/...)

后续将扩展(参考 project_manager.md):
  - update_plan.py       (Agent Loop 工具)
  - finish_loop.py       (Agent Loop 工具)
  - record_memory.py     (长期记忆工具)
  - ask_user.py          (用户交互工具)

只要新模块放在 buildin_tools/ 下,导出 TOOL_SCHEMAS + TOOL_HANDLERS,buildin_client
**零改动**自动发现。

## CLI 测试示例

```powershell
# 0. 查看所有 toolkits
python buildin_client.py --list

# 1. 列出所有工具(简要:toolkit.tool + description)
python buildin_client.py --list-tools

# 2. 列出所有工具(详细:含 inputSchema 人类可读 + 原始 JSON)
python buildin_client.py --list-tools --detail

# 3. 查看单个工具的完整 schema
python buildin_client.py --tool-info file_system.read_file

# 4. 调用工具(SPEC 格式 toolkit.tool_name,与 mcp_client 对齐)
python buildin_client.py --call-tool file_system.read_file --arguments '{"path": "C:/workspace/README.md"}'
python buildin_client.py --call-tool command_line.run_command --arguments '{"command": "echo hello", "timeout": 5}'
python buildin_client.py --call-tool non_head_browser.web_search --arguments '{"query": "Onion Agent", "num_results": 3}'

# 5. 跨 toolkit 查找工具(只给 tool_name,不指定 toolkit)
python buildin_client.py --tool-info read_file

# 6. 输出 OpenAI 风格 schema 列表(给 tool_channel / LLM 使用,按名字排序)
python buildin_client.py --to-openai

# 7. 指定非默认 buildin_tools 路径
python buildin_client.py --config C:/other/path/buildin_tools --list-tools
```

## 退出码

0  - 成功
2  - 参数错误
7  - 工具/工具集不存在
8  - 参数校验失败
9  - 工具调用异常
99 - 内部异常
"""

from __future__ import annotations

import argparse
import importlib.util
import inspect
import json
import os
import sys
import time
import traceback
from dataclasses import dataclass, field
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
# 默认 buildin_tools 目录:与本文件同级的 ../../buildin_tools/
# 即 src/infrastructure/buildin_tools/
_DEFAULT_TOOLS_DIR = Path(__file__).resolve().parent.parent / "buildin_tools"

# 工具默认超时(秒)
DEFAULT_TOOL_TIMEOUT = 60

# 工具调用结果最大字符数(超过则 middle-out 截断)
MAX_TOOL_RESULT_CHARS = 50_000

# 排除扫描的目录/文件(避免 import 子目录、缓存、私有模块)
_EXCLUDE_DIRS = frozenset({
    "__pycache__",        # Python 缓存
    "chromium",           # Playwright Chromium 二进制目录(非 Python 模块)
    ".git", ".svn", ".hg",
    "node_modules",
})
_EXCLUDE_FILE_PREFIXES = ("_", ".")  # _print_schemas、__init__、.gitignore 等

# 需要过滤掉的标准库 / 第三方模块属性(toolkit 不应当 re-export 这些)
_RESERVED_ATTRS = frozenset({
    "Any", "Callable", "Optional", "List", "Dict", "Tuple", "Set", "Union",
    "Path", "dataclass", "field",
    "annotations", "final",
})


# ============================================================================
# 异常类
# ============================================================================
class BuildinClientError(Exception):
    """所有 buildin client 相关异常的基类。"""
    pass


class ToolkitNotFoundError(BuildinClientError):
    """找不到指定的 toolkit。"""
    pass


class ToolNotFoundError(BuildinClientError):
    """在指定 toolkit 或全范围内找不到工具。"""
    pass


class ArgumentValidationError(BuildinClientError):
    """参数校验失败(JSON Schema 校验不通过)。"""
    pass


# ============================================================================
# 数据类
# ============================================================================
@dataclass
class BuildinToolkit:
    """一个内置工具集(对应 buildin_tools/<name>.py 一个文件)。"""
    name: str                                  # "file_system"
    module_path: Path                          # /path/to/file_system.py
    module: Any                                # 已 import 的模块对象
    description: str = ""                      # 取自模块 __doc__ 摘要
    handlers: dict[str, Callable] = field(default_factory=dict)   # 来自 TOOL_HANDLERS
    schemas: list[dict] = field(default_factory=list)             # 来自 TOOL_SCHEMAS

    def get_tool_names(self) -> list[str]:
        return list(self.handlers.keys())


@dataclass
class BuildinTool:
    """单个工具(已加上 toolkit 前缀)。"""
    toolkit: str                               # "file_system"
    name: str                                  # "read_file"
    full_name: str                             # "file_system.read_file"
    description: str
    input_schema: dict                         # JSON Schema (parameters 字段)
    handler: Callable
    timeout: int = DEFAULT_TOOL_TIMEOUT
    max_retries: int = 0                       # 内置工具默认 0(原子化,极少需要重试)

    def to_openai_dict(self) -> dict:
        """转成 OpenAI Chat Completions tool 格式。"""
        return {
            "type": "function",
            "function": {
                "name": self.full_name,
                "description": self.description,
                "parameters": self.input_schema,
            },
        }


# ============================================================================
# 从模块 docstring 提取第一行有意义的描述(过滤掉 banner 装饰)
# ============================================================================
def _extract_description(doc: str) -> str:
    """
    从 docstring 提取一句话描述。

    过滤规则:
      - 跳过空行
      - 跳过以 === / --- / ### / *** 开头或纯由这些字符组成的"装饰行"
      - 跳过以 # 开头的注释行
      - 返回第一个有意义的非空行(最多截 120 字符)
    """
    if not doc:
        return ""
    for line in doc.splitlines():
        s = line.strip()
        if not s:
            continue
        # 过滤纯装饰行(== --- ### ***)和单行注释
        if all(c in "=-*# \t" for c in s):
            continue
        if s.startswith("#"):
            continue
        return s[:120]
    return ""


# ============================================================================
# 工具名解析(支持 toolkit.tool / toolkit.tool@timeout / 跨 toolkit 查找)
# ============================================================================
def parse_tool_spec(spec: str) -> tuple[Optional[str], str]:
    """
    解析 "server.tool" / "tool" 格式的 spec。

    Returns:
        (toolkit_name_or_None, tool_name)
        - "file_system.read_file" -> ("file_system", "read_file")
        - "read_file"             -> (None, "read_file")
    """
    if "." in spec:
        toolkit, tool = spec.split(".", 1)
        return toolkit.strip() or None, tool.strip()
    return None, spec.strip()


# ============================================================================
# JSON Schema 人类可读格式化(参考 mcp_client._format_input_schema_human)
# ============================================================================
def _format_input_schema_human(schema: dict) -> str:
    """
    把 JSON Schema 格式化成人类可读形式。

    输出示例:
        Parameters (3):
          - path        string  [required]
                要读取的文件路径
          - head        integer  [optional]
                只读取前 N 行
          - encoding    string  [optional]  enum: "utf-8", "gbk"

        Required: path
        Additional properties: 不允许
    """
    if not schema:
        return "    (无参数)"

    properties = schema.get("properties", {}) or {}
    required = set(schema.get("required", []) or [])
    additional = schema.get("additionalProperties", True)
    schema_type = schema.get("type", "object")

    if schema_type != "object" or not properties:
        # 退化情况:直接 dump
        return "    " + json.dumps(schema, ensure_ascii=False, indent=4).replace("\n", "\n    ")

    lines = [f"    Parameters ({len(properties)}):"]
    max_name_len = max(len(name) for name in properties)
    # 描述行缩进:与参数行第一个字符对齐("      - " = 6 字符) + name 宽度 + 2 空格
    desc_indent = " " * (6 + max_name_len + 2)

    for name, prop in properties.items():
        prop_type = prop.get("type", "any")
        # 数组类型可能用 items 表示元素类型
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

        desc = (prop.get("description") or "").strip()
        if desc:
            for i, desc_line in enumerate(desc.splitlines()):
                lines.append(f"{desc_indent}{desc_line}")

    if required:
        lines.append(f"    Required: {', '.join(sorted(required))}")
    if additional is False:
        lines.append("    Additional properties: 不允许")

    return "\n".join(lines)


# ============================================================================
# 简易 JSON Schema 校验(避免引入 jsonschema 依赖)
# ----------------------------------------------------------------------------
# 内置工具的参数都比较简单(基本是 object + 几个 string/int/bool),
# 用一个轻量级校验器足够。后续如果工具变复杂,可以替换成 jsonschema 库。
# ============================================================================
_BASIC_TYPE_MAP = {
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "array": list,
    "object": dict,
    "null": type(None),
}


def _validate_arguments(schema: dict, arguments: dict) -> tuple[bool, str]:
    """
    简易 JSON Schema 校验。

    覆盖:
      - type (基本类型)
      - required
      - additionalProperties (strict 模式,防止 LLM 幻觉字段)
      - enum
      - 数组元素类型(items.type)

    不覆盖(够用就行):
      - oneOf / anyOf / allOf
      - $ref
      - 复杂 format 校验(email / uri 等)
    """
    if not schema:
        return True, ""

    schema_type = schema.get("type", "object")
    if schema_type != "object":
        return True, ""  # 简单类型不深入校验

    if not isinstance(arguments, dict):
        return False, f"参数应当是 object 类型,实际是 {type(arguments).__name__}"

    # required
    required = schema.get("required", []) or []
    missing = [k for k in required if k not in arguments]
    if missing:
        return False, f"缺少必填参数: {', '.join(missing)}"

    # additionalProperties
    properties = schema.get("properties", {}) or {}
    additional = schema.get("additionalProperties", True)
    if additional is False:
        extras = set(arguments.keys()) - set(properties.keys())
        if extras:
            return False, f"不允许额外参数(违反 strict 模式): {', '.join(sorted(extras))}"

    # type / enum
    for key, value in arguments.items():
        if key not in properties:
            continue  # 上面已校验 additionalProperties
        prop = properties[key] or {}
        prop_type = prop.get("type")
        if prop_type and prop_type in _BASIC_TYPE_MAP:
            expected = _BASIC_TYPE_MAP[prop_type]
            # boolean 是 int 的子类,要排除
            if prop_type == "boolean" and not isinstance(value, bool):
                return False, f"参数 '{key}' 应为 boolean,实际是 {type(value).__name__}: {value!r}"
            if prop_type == "integer" and isinstance(value, bool):
                # True/False 也满足 int 校验,但语义不对
                return False, f"参数 '{key}' 应为 integer,实际是 boolean: {value!r}"
            if not isinstance(value, expected):
                return False, f"参数 '{key}' 应为 {prop_type},实际是 {type(value).__name__}: {value!r}"

        # 数组元素类型
        if prop_type == "array" and isinstance(value, list):
            items = (prop.get("items") or {})
            item_type = items.get("type")
            if item_type and item_type in _BASIC_TYPE_MAP:
                expected = _BASIC_TYPE_MAP[item_type]
                for idx, item in enumerate(value):
                    if not isinstance(item, expected):
                        return False, f"参数 '{key}[{idx}]' 应为 {item_type},实际是 {type(item).__name__}"

        # enum
        enum_vals = prop.get("enum")
        if enum_vals is not None and value not in enum_vals:
            return False, f"参数 '{key}' 值 {value!r} 不在允许范围: {enum_vals}"

    return True, ""


# ============================================================================
# 大结果截断(middle-out,保留前 50% + 后 50%)
# ============================================================================
def _truncate_middle(text: str, max_chars: int) -> tuple[str, bool]:
    """参考 mcp_client / non_head_browser 的头+尾截断。"""
    if len(text) <= max_chars:
        return text, False
    half = max_chars // 2
    skip_chars = len(text) - max_chars
    truncated = (
        text[:half]
        + f"\n\n[... output truncated: 共 {len(text)} 字符,截断 {skip_chars} 字符 ...]\n\n"
        + text[-half:]
    )
    return truncated, True


# ============================================================================
# BuildinClient - 主类
# ============================================================================
class BuildinClient:
    """
    内置工具统一调用客户端。

    核心职责:
      1. 自动发现 buildin_tools/ 下的 .py 模块(duck typing:有 TOOL_SCHEMAS + TOOL_HANDLERS)
      2. 收集并包装成 BuildinTool(full_name = toolkit.tool)
      3. 提供 list / get / find / call / to_openai_schema 统一 API
      4. 简易 JSON Schema 校验(middleware 在 source 模块前)
      5. 错误透明:handler 异常不抛 traceback,统一返回 {success, content, error, data}

    与 mcp_client / agent_skills_client 的对等 API:
      MCPClient            BuildinClient         说明
      -----------          ------------          ----
      list_servers()       list_toolkits()       列出所有"源"
      list_tools()         list_tools()          列出所有工具(简要 schema)
      get_tool_info()      get_tool_info()       看单个工具的完整 schema
      find_tool()          find_tool()           跨源查找
      call_tool()          call_tool()           调用工具
      get_server_status()  get_client_status()   客户端状态摘要
    """

    def __init__(self, tools_dir: Optional[Path] = None, auto_load: bool = True):
        """
        Args:
            tools_dir: buildin_tools 目录路径。None 时用默认(_DEFAULT_TOOLS_DIR)
            auto_load: 是否在构造时自动扫描加载。False 时需要手动调 load_all()
        """
        self.tools_dir = Path(tools_dir) if tools_dir else _DEFAULT_TOOLS_DIR
        self.toolkits: dict[str, BuildinToolkit] = {}  # name -> BuildinToolkit
        self.tools: dict[str, BuildinTool] = {}        # full_name -> BuildinTool
        self._load_errors: list[dict] = []            # 加载失败的工具集(不致命)
        if auto_load:
            self.load_all()

    # ------------------------------------------------------------------ 加载

    def load_all(self) -> dict[str, bool]:
        """
        扫描 tools_dir,加载所有 .py 模块。

        Returns:
            toolkit_name -> 是否加载成功 的字典
        """
        if not self.tools_dir.exists():
            raise BuildinClientError(f"buildin_tools 目录不存在: {self.tools_dir}")

        self.toolkits.clear()
        self.tools.clear()
        self._load_errors.clear()

        results: dict[str, bool] = {}
        for py_file in sorted(self.tools_dir.glob("*.py")):
            name = py_file.stem
            # 跳过 _xx / .xx 私有模块
            if py_file.name.startswith(_EXCLUDE_FILE_PREFIXES):
                continue

            try:
                toolkit = self._load_one_toolkit(name, py_file)
            except Exception as e:
                self._load_errors.append({
                    "toolkit": name,
                    "path": str(py_file),
                    "error": f"{type(e).__name__}: {e}",
                })
                results[name] = False
                continue

            # 必须有 TOOL_SCHEMAS + TOOL_HANDLERS,否则认为不是工具模块
            if not toolkit.handlers or not toolkit.schemas:
                continue

            self.toolkits[name] = toolkit
            results[name] = True

            # 包装成 BuildinTool(加 toolkit 前缀)
            for schema in toolkit.schemas:
                func = schema.get("function", {}) or {}
                tool_name = func.get("name", "")
                if not tool_name or tool_name not in toolkit.handlers:
                    # schema 里有但 handler 里没有 → 跳过(避免运行时崩)
                    continue
                full_name = f"{name}.{tool_name}"
                self.tools[full_name] = BuildinTool(
                    toolkit=name,
                    name=tool_name,
                    full_name=full_name,
                    description=func.get("description", "") or "",
                    input_schema=func.get("parameters", {}) or {},
                    handler=toolkit.handlers[tool_name],
                )

        return results

    def _load_one_toolkit(self, name: str, path: Path) -> BuildinToolkit:
        """动态 import 一个 buildin 工具模块,提取 TOOL_SCHEMAS + TOOL_HANDLERS。"""
        # 用 importlib.util 动态加载(避免污染 sys.modules 的全局命名空间)
        spec = importlib.util.spec_from_file_location(
            f"onion_buildin_toolkit_{name}", str(path),
        )
        if spec is None or spec.loader is None:
            raise BuildinClientError(f"无法构造 import spec: {path}")

        module = importlib.util.module_from_spec(spec)
        # 临时加入 sys.modules(让模块内可能的相对 import 也能工作)
        sys.modules[spec.name] = module
        try:
            spec.loader.exec_module(module)
        except Exception as e:
            # 加载失败要从 sys.modules 移除
            sys.modules.pop(spec.name, None)
            raise BuildinClientError(f"import 失败: {e}") from e

        # 提取约定接口
        handlers: dict[str, Callable] = getattr(module, "TOOL_HANDLERS", {}) or {}
        schemas: list[dict] = getattr(module, "TOOL_SCHEMAS", []) or []

        # 模块 docstring 的第一个非空、非装饰行作为描述
        doc = (getattr(module, "__doc__", "") or "").strip()
        description = _extract_description(doc)

        return BuildinToolkit(
            name=name,
            module_path=path,
            module=module,
            description=description,
            handlers=dict(handlers),
            schemas=list(schemas),
        )

    # ------------------------------------------------------------------ 列出

    def list_toolkits(self) -> list[dict]:
        """
        列出所有已加载的 toolkit 摘要。

        Returns:
            [{name, description, path, tool_count, error?}, ...]
        """
        result = []
        for name, toolkit in sorted(self.toolkits.items()):
            entry: dict[str, Any] = {
                "name": name,
                "description": toolkit.description,
                "path": str(toolkit.module_path),
                "tool_count": len(toolkit.handlers),
            }
            result.append(entry)
        # 加载失败的也附带(可见性)
        for err in self._load_errors:
            result.append({
                "name": err["toolkit"],
                "description": "",
                "path": err["path"],
                "tool_count": 0,
                "error": err["error"],
            })
        return result

    def list_tools(self, toolkit: Optional[str] = None) -> dict[str, list[dict]]:
        """
        列出工具的简要信息(name + description)。

        Args:
            toolkit: 指定 toolkit 名,只列该 toolkit 的工具。None 列出所有。

        Returns:
            {toolkit_name: [{"name", "full_name", "description"}, ...]}
        """
        result: dict[str, list[dict]] = {}
        if toolkit is not None:
            if toolkit not in self.toolkits:
                raise ToolkitNotFoundError(f"toolkit 不存在: {toolkit!r}")
            result[toolkit] = self._format_tools(self.toolkits[toolkit].schemas)
            return result

        for name, tk in sorted(self.toolkits.items()):
            result[name] = self._format_tools(tk.schemas)
        return result

    def _format_tools(self, schemas: list[dict]) -> list[dict]:
        """把 TOOL_SCHEMAS 格式化成简表。"""
        formatted = []
        for schema in schemas:
            func = schema.get("function", {}) or {}
            tool_name = func.get("name", "")
            full_name = self._find_full_name(tool_name) or tool_name
            formatted.append({
                "name": tool_name,
                "full_name": full_name,
                "description": func.get("description", "") or "",
            })
        return formatted

    def _find_full_name(self, tool_name: str) -> Optional[str]:
        """已知 tool_name,反查它的 full_name。"""
        for full_name, tool in self.tools.items():
            if tool.name == tool_name:
                return full_name
        return None

    # ------------------------------------------------------------------ 查找

    def get_tool_info(self, spec: str) -> Optional[dict]:
        """
        获取单个工具的完整信息(包含 inputSchema)。

        Args:
            spec: 两种格式
                - "toolkit.tool_name":精确查找
                - "tool_name":跨 toolkit 查找(唯一时返回,多个时返回列表)

        Returns:
            工具信息 dict(name/full_name/description/inputSchema/toolkit/timeout),
            找不到返回 None。
            如果"跨 toolkit 找到多个",返回 {"ambiguous": True, "matches": [...]}
        """
        toolkit_name, tool_name = parse_tool_spec(spec)

        if toolkit_name is not None:
            # 精确查找
            full_name = f"{toolkit_name}.{tool_name}"
            tool = self.tools.get(full_name)
            if tool is None:
                return None
            return self._tool_info_dict(tool)

        # 跨 toolkit 查找
        matches = [
            tool for full_name, tool in self.tools.items() if tool.name == tool_name
        ]
        if len(matches) == 0:
            return None
        if len(matches) == 1:
            return self._tool_info_dict(matches[0])
        # 多个匹配:返回 ambiguous 标记
        return {
            "ambiguous": True,
            "matches": [
                {
                    "full_name": t.full_name,
                    "toolkit": t.toolkit,
                    "name": t.name,
                    "description": t.description,
                }
                for t in sorted(matches, key=lambda x: x.full_name)
            ],
        }

    def find_tool(self, tool_name: str) -> list[tuple[str, dict]]:
        """
        跨所有 toolkit 查找指定 tool_name。

        Returns:
            (full_name, tool_info_dict) 元组列表
        """
        results = []
        for full_name, tool in sorted(self.tools.items()):
            if tool.name == tool_name:
                results.append((full_name, self._tool_info_dict(tool)))
        return results

    def _tool_info_dict(self, tool: BuildinTool) -> dict:
        """把 BuildinTool 转成对外的 info dict。"""
        return {
            "name": tool.name,
            "full_name": tool.full_name,
            "toolkit": tool.toolkit,
            "description": tool.description,
            "inputSchema": tool.input_schema,
            "timeout": tool.timeout,
            "max_retries": tool.max_retries,
        }

    # ------------------------------------------------------------------ OpenAI schema 输出

    def to_openai_schema(self, sort: bool = True) -> list[dict]:
        """
        输出 OpenAI Chat Completions 风格的工具列表(给 LLM 调用)。

        Args:
            sort: 是否按 full_name 字母排序。True 保证 OpenAI prompt cache hit
                  (参考 tool_channel.md §4.5 强烈建议)

        Returns:
            [{"type": "function", "function": {"name", "description", "parameters"}}, ...]
        """
        tools = list(self.tools.values())
        if sort:
            tools.sort(key=lambda t: t.full_name)
        return [t.to_openai_dict() for t in tools]

    # ------------------------------------------------------------------ 调用

    def call_tool(
        self,
        spec: str,
        arguments: Optional[dict] = None,
        timeout: Optional[int] = None,
        skip_validation: bool = False,
    ) -> dict:
        """
        调用指定工具。

        Args:
            spec: "toolkit.tool_name" 或 "tool_name"
            arguments: 工具参数字典
            timeout: 覆盖工具默认 timeout(秒)。None 用工具自己的值
            skip_validation: 跳过 JSON Schema 校验(慎用,仅调试用)

        Returns:
            统一返回格式:
            {
                "success": bool,
                "is_error": bool,        # 对应 tool_channel.md §6.4 isError
                "content": str,          # LLM 看到的文本
                "error": Optional[str],  # 错误消息
                "data": {                # 结构化数据(供程序用)
                    "toolkit": str,
                    "tool": str,
                    "full_name": str,
                    "arguments": dict,
                    "duration_ms": int,
                    "truncated": bool,
                    "raw_result": Any,    # handler 的原始返回
                }
            }
        """
        toolkit_name, tool_name = parse_tool_spec(spec)

        # 定位工具
        if toolkit_name is not None:
            full_name = f"{toolkit_name}.{tool_name}"
            tool = self.tools.get(full_name)
        else:
            # 跨 toolkit 找
            matches = [t for t in self.tools.values() if t.name == tool_name]
            if len(matches) == 0:
                return self._call_err(
                    f"工具不存在: {spec!r}",
                    full_name=spec, toolkit=toolkit_name or "?", tool=tool_name,
                )
            if len(matches) > 1:
                names = ", ".join(sorted(t.full_name for t in matches))
                return self._call_err(
                    f"工具名 {tool_name!r} 在多个 toolkit 中存在,请明确指定: {names}",
                    full_name=spec, toolkit="?", tool=tool_name,
                )
            tool = matches[0]
            full_name = tool.full_name

        if tool is None:
            return self._call_err(
                f"工具不存在: {full_name}",
                full_name=full_name, toolkit=toolkit_name or "?", tool=tool_name,
            )

        arguments = arguments or {}
        effective_timeout = timeout if timeout is not None else tool.timeout

        # 参数校验
        if not skip_validation:
            ok, err = _validate_arguments(tool.input_schema, arguments)
            if not ok:
                return self._call_err(
                    f"参数校验失败: {err}",
                    full_name=full_name, toolkit=tool.toolkit, tool=tool.name,
                )

        # 实际调用(用 inspect.signature 判定是否要传 timeout)
        start = time.time()
        try:
            sig = inspect.signature(tool.handler)
            params = sig.parameters
            # 如果 handler 接受 timeout 或 **kwargs,传 timeout
            call_kwargs = dict(arguments)
            supports_timeout = (
                "timeout" in params
                or any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())
            )
            if supports_timeout:
                call_kwargs["timeout"] = effective_timeout
            raw_result = tool.handler(**call_kwargs)
            duration_ms = int((time.time() - start) * 1000)
        except Exception as e:
            duration_ms = int((time.time() - start) * 1000)
            return self._call_err(
                f"工具执行异常: {type(e).__name__}: {e}",
                full_name=full_name, toolkit=tool.toolkit, tool=tool.name,
                duration_ms=duration_ms,
            )

        # 标准化返回
        return self._format_call_result(
            raw_result=raw_result,
            full_name=full_name,
            toolkit=tool.toolkit,
            tool=tool.name,
            arguments=arguments,
            duration_ms=duration_ms,
        )

    def _format_call_result(
        self,
        raw_result: Any,
        full_name: str,
        toolkit: str,
        tool: str,
        arguments: dict,
        duration_ms: int,
    ) -> dict:
        """
        把 handler 返回值(约定:{"success": bool, "content": str, "error": ..., "data": ...})
        统一成对外格式。

        容错:handler 不一定遵守约定(可能直接 return 字符串/dict)——做兼容:
          - dict 且有 success 字段:按约定解析
          - dict 无 success:整个当 data,content 取 str(dict)
          - str:content=str,success 启发式判断(以 [ERROR] 开头 → False)
          - 其他:repr
        """
        is_error = False
        error_msg: Optional[str] = None
        content: str = ""
        data: Any = None

        if isinstance(raw_result, dict):
            # 检查是否遵守 _ok/_err 约定
            if "success" in raw_result and "content" in raw_result:
                is_error = bool(raw_result.get("is_error", not raw_result.get("success", False)))
                error_msg = raw_result.get("error")
                content = str(raw_result.get("content", ""))
                data = raw_result.get("data")
            else:
                # 裸 dict 当作 data
                data = raw_result
                content = json.dumps(raw_result, ensure_ascii=False, indent=2)
                is_error = content.startswith("[ERROR]")
        elif isinstance(raw_result, str):
            content = raw_result
            is_error = content.startswith("[ERROR]")
            if is_error:
                # 尝试从 [ERROR] xxx 中提取 error
                error_msg = content[len("[ERROR]"):].strip()
        else:
            content = repr(raw_result)
            data = raw_result

        # 截断(content 太长会撑爆 LLM context)
        truncated_content, was_truncated = _truncate_middle(content, MAX_TOOL_RESULT_CHARS)

        return {
            "success": not is_error,
            "is_error": is_error,
            "content": truncated_content,
            "error": error_msg,
            "data": {
                "toolkit": toolkit,
                "tool": tool,
                "full_name": full_name,
                "arguments": arguments,
                "duration_ms": duration_ms,
                "truncated": was_truncated,
                "raw_result": data,
            },
        }

    def _call_err(
        self,
        msg: str,
        full_name: str = "",
        toolkit: str = "",
        tool: str = "",
        duration_ms: int = 0,
    ) -> dict:
        return {
            "success": False,
            "is_error": True,
            "content": f"[ERROR] {msg}",
            "error": msg,
            "data": {
                "toolkit": toolkit,
                "tool": tool,
                "full_name": full_name,
                "arguments": {},
                "duration_ms": duration_ms,
                "truncated": False,
                "raw_result": None,
            },
        }

    # ------------------------------------------------------------------ 状态

    def get_client_status(self) -> dict:
        """获取客户端状态摘要。"""
        return {
            "tools_dir": str(self.tools_dir),
            "tools_dir_exists": self.tools_dir.exists(),
            "toolkit_count": len(self.toolkits),
            "tool_count": len(self.tools),
            "load_errors": list(self._load_errors),
            "toolkits": {
                name: {
                    "tool_count": len(tk.handlers),
                    "path": str(tk.module_path),
                }
                for name, tk in sorted(self.toolkits.items())
            },
        }


# ============================================================================
# CLI 工具函数
# ============================================================================
def _print_toolkits(client: BuildinClient) -> int:
    """--list:列出所有 toolkit。"""
    toolkits = client.list_toolkits()
    if not toolkits:
        print("未找到任何 toolkit")
        return 7

    print("Buildin Toolkits:")
    print("-" * 60)
    for tk in toolkits:
        if "error" in tk:
            print(f"  [X] {tk['name']}: 加载失败")
            print(f"      path: {tk['path']}")
            print(f"      error: {tk['error']}")
        else:
            print(f"  [OK] {tk['name']} ({tk['tool_count']} 个工具)")
            if tk["description"]:
                print(f"      {tk['description'][:80]}")
            print(f"      path: {tk['path']}")
        print()
    print("-" * 60)
    print(f"共 {len([t for t in toolkits if 'error' not in t])} 个 toolkit "
          f"/ {sum(t['tool_count'] for t in toolkits if 'error' not in t)} 个工具")
    return 0


def _print_tools(client: BuildinClient, detail: bool) -> int:
    """--list-tools [--detail]:列出所有工具。"""
    tools_map = client.list_tools()
    if not tools_map:
        print("未找到任何工具")
        return 7

    for toolkit_name, tools in sorted(tools_map.items()):
        print(f"\nToolkit '{toolkit_name}' 的工具 ({len(tools)}):")
        if not tools:
            print("  (无工具)")
            continue
        for t in tools:
            if detail:
                info = client.get_tool_info(t["full_name"])
                print(f"\n  ╭─ {t['full_name']}")
                desc = info["description"] or "(无描述)"
                print(f"  │  Description: {desc}")
                print(f"  │")
                human_lines = _format_input_schema_human(info["inputSchema"]).splitlines()
                for line in human_lines:
                    print(f"  │  {line}")
                print(f"  │")
                print(f"  │  Raw inputSchema (JSON Schema):")
                raw = json.dumps(info["inputSchema"], ensure_ascii=False, indent=2)
                for line in raw.splitlines():
                    print(f"  │    {line}")
                print(f"  ╰─")
            else:
                print(f"  - {t['full_name']}: {t['description'] or '(无描述)'}")

    total = sum(len(ts) for ts in tools_map.values())
    print(f"\n共 {total} 个工具")
    return 0


def _print_tool_info(client: BuildinClient, spec: str) -> int:
    """--tool-info <spec>:查看单个工具。"""
    info = client.get_tool_info(spec)
    if info is None:
        # 提示:列出所有可用工具
        print(f"错误: 找不到工具 {spec!r}", file=sys.stderr)
        print("\n所有可用工具:", file=sys.stderr)
        for toolkit_name, tools in client.list_tools().items():
            for t in tools:
                print(f"  {t['full_name']}", file=sys.stderr)
        return 7

    if "ambiguous" in info:
        print(f"工具 '{spec}' 在多个 toolkit 中存在:", file=sys.stderr)
        for m in info["matches"]:
            print(f"  - {m['full_name']}: {m['description']}", file=sys.stderr)
        print(f"\n请明确指定: --tool-info <toolkit>.<tool>", file=sys.stderr)
        return 7

    print(f"工具: {info['full_name']}")
    print(f"Toolkit: {info['toolkit']}")
    print(f"Description: {info['description'] or '(无描述)'}")
    print()
    print(_format_input_schema_human(info["inputSchema"]))
    print()
    print("Raw inputSchema (JSON Schema):")
    print(json.dumps(info["inputSchema"], ensure_ascii=False, indent=2))
    return 0


def _call_tool_cli(
    client: BuildinClient,
    spec: str,
    arguments_str: Optional[str],
    arguments_file: Optional[str] = None,
) -> int:
    """--call-tool <spec> --arguments <json>:调用工具。"""
    arguments: dict = {}
    if arguments_str and arguments_file:
        print("错误: --arguments 和 --arguments-file 互斥,只能用一个", file=sys.stderr)
        return 2
    if arguments_str:
        try:
            parsed = json.loads(arguments_str)
        except json.JSONDecodeError as e:
            print(f"错误: --arguments 应当是 JSON 字符串,解析失败: {e}", file=sys.stderr)
            return 2
        if not isinstance(parsed, dict):
            print(f"错误: --arguments 应当是 JSON object,实际是 {type(parsed).__name__}", file=sys.stderr)
            return 2
        arguments = parsed
    elif arguments_file:
        path = Path(arguments_file)
        if not path.is_file():
            print(f"错误: --arguments-file 不存在: {path}", file=sys.stderr)
            return 2
        try:
            parsed = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(f"错误: --arguments-file 不是合法 JSON,解析失败: {e}", file=sys.stderr)
            return 2
        if not isinstance(parsed, dict):
            print(f"错误: --arguments-file 应当是 JSON object,实际是 {type(parsed).__name__}", file=sys.stderr)
            return 2
        arguments = parsed

    result = client.call_tool(spec, arguments=arguments)

    # 输出 content 给人看,data 给程序
    print(result["content"])
    print()
    print("# ── 调用摘要 ────────────────────────────────────────────────")
    d = result["data"]
    print(f"# toolkit: {d['toolkit']}")
    print(f"# tool: {d['tool']}")
    print(f"# full_name: {d['full_name']}")
    print(f"# duration: {d['duration_ms']}ms")
    print(f"# truncated: {d['truncated']}")
    print(f"# success: {result['success']}  is_error: {result['is_error']}")
    if result["error"]:
        print(f"# error: {result['error']}")
    return 0 if result["success"] else 9


def _print_to_openai(client: BuildinClient) -> int:
    """--to-openai:输出 OpenAI 风格 schema 列表(给 tool_channel 用)。"""
    schemas = client.to_openai_schema(sort=True)
    if not schemas:
        print("未找到任何工具")
        return 7
    print(json.dumps(schemas, ensure_ascii=False, indent=2))
    print()
    print(f"# 共 {len(schemas)} 个工具(已按 full_name 排序保证 prompt cache hit)", file=sys.stderr)
    return 0


def _print_status(client: BuildinClient) -> int:
    """--status:输出客户端状态摘要(给程序用)。"""
    print(json.dumps(client.get_client_status(), ensure_ascii=False, indent=2))
    return 0


# ============================================================================
# 命令行入口
# ============================================================================
def main():
    parser = argparse.ArgumentParser(
        description="Onion Agent 内置工具统一调用客户端",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 列出所有 toolkit
  python buildin_client.py --list

  # 列出所有工具(简要)
  python buildin_client.py --list-tools

  # 列出所有工具(详细,含每个 tool 的 inputSchema)
  python buildin_client.py --list-tools --detail

  # 查看单个工具
  python buildin_client.py --tool-info file_system.read_file
  python buildin_client.py --tool-info read_file            # 跨 toolkit 查找

  # 调用工具(SPEC 格式 toolkit.tool_name)
  python buildin_client.py --call-tool file_system.list_dir --arguments '{"path": "."}'
  python buildin_client.py --call-tool command_line.run_command --arguments '{"command": "echo hi"}'
  python buildin_client.py --call-tool non_head_browser.web_search --arguments '{"query": "test", "num_results": 3}'

  # 输出 OpenAI 风格 schema 列表(给 tool_channel / LLM 使用)
  python buildin_client.py --to-openai

  # 客户端状态摘要
  python buildin_client.py --status

  # 指定非默认 buildin_tools 目录
  python buildin_client.py --config C:/other/buildin_tools --list-tools
        """,
    )
    parser.add_argument(
        "--config", "-c", default=None,
        help="buildin_tools 目录路径(默认:与 buildin_client.py 同级的 ../../buildin_tools/)",
    )
    parser.add_argument(
        "--list", "-l", action="store_true",
        help="列出所有已加载的 toolkit",
    )
    parser.add_argument(
        "--list-tools", action="store_true",
        help="列出所有工具(name + description)",
    )
    parser.add_argument(
        "--list-tools-detail", "--detail", dest="list_tools_detail",
        action="store_true",
        help="与 --list-tools 联用,输出每个 tool 的 inputSchema",
    )
    parser.add_argument(
        "--tool-info", metavar="SPEC",
        help="查看单个工具的完整 schema。SPEC: toolkit.tool_name 或 tool_name",
    )
    parser.add_argument(
        "--call-tool", metavar="SPEC",
        help="调用指定工具。SPEC 格式同 --tool-info",
    )
    parser.add_argument(
        "--arguments", metavar="JSON",
        help="传给 tool 的参数(JSON 字符串,简单参数用这个)",
    )
    parser.add_argument(
        "--arguments-file", metavar="PATH",
        help="从文件读取参数(JSON object,避免 shell 转义,复杂参数用这个)",
    )
    parser.add_argument(
        "--to-openai", action="store_true",
        help="输出 OpenAI Chat Completions 风格 schema 列表(按 full_name 排序,给 LLM 用)",
    )
    parser.add_argument(
        "--status", action="store_true",
        help="输出客户端状态摘要(JSON)",
    )

    args = parser.parse_args()

    # 构造 client
    try:
        tools_dir = Path(args.config) if args.config else None
        client = BuildinClient(tools_dir=tools_dir, auto_load=True)
    except BuildinClientError as e:
        print(f"错误: {e}", file=sys.stderr)
        return 99

    # 分发
    try:
        if args.list:
            return _print_toolkits(client)
        if args.list_tools:
            return _print_tools(client, detail=args.list_tools_detail)
        if args.tool_info:
            return _print_tool_info(client, args.tool_info)
        if args.call_tool:
            return _call_tool_cli(client, args.call_tool, args.arguments, args.arguments_file)
        if args.to_openai:
            return _print_to_openai(client)
        if args.status:
            return _print_status(client)

        # 默认:列 toolkit
        return _print_toolkits(client)
    except BuildinClientError as e:
        print(f"错误: {e}", file=sys.stderr)
        return 99
    except KeyboardInterrupt:
        print("\n已取消", file=sys.stderr)
        return 130
    except Exception as e:
        traceback.print_exc()
        print(f"内部异常: {type(e).__name__}: {e}", file=sys.stderr)
        return 99


if __name__ == "__main__":
    sys.exit(main())
