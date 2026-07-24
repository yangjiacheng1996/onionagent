# -*- coding: utf-8 -*-
"""
================================================================================
Tool Channel - 工具调用路由模块 (L5 - Infrastructure / tool_channel)
================================================================================

# 开发计划

Onion Agent 走 OpenAI Chat Completions tool 通道。LLM 返回的 tool_calls
是 `[{id, type:"function", function:{name, arguments:JSON字符串}}, ...]` 格式。

tool_router 的职责是:
  1. 解析 name(必须符合 onion.<tag>.<scope>.<tool> 格式)
  2. 解析 arguments(JSON 字符串 → dict,7 层兜底)
  3. 用对应工具的 JSON Schema 校验参数
  4. 按 tag 路由到对应 client(buildin/mcp/skill/agent)
  5. 执行工具
  6. 把结果统一格式化成 OpenAI role:tool 消息(给 L4 engine 写回 history)

详细设计见:
  harness/03_SRS/infrastructure/tool_channel/design.md
  harness/01_market_research/tool_accuracy.md(原生 FC 6 阶段)

## CLI 用法(所见即所得)

```powershell
# 单条指令
python tool_router.py --workspace D:\\onion\\andy \\
    --command '{"id":"call_1","type":"function","function":{"name":"onion.buildin.file_system.list_dir","arguments":"{\\"path\\":\\".\\"}"}}'

# 多条指令(从文件读,JSON 数组)
python tool_router.py --workspace D:\\onion\\andy \\
    --command-file calls.json

# 关闭 MCP 连接(只用本地 buildin + skill)
python tool_router.py --no-mcp \\
    --command '{"id":"call_1","type":"function","function":{"name":"onion.buildin.file_system.read_file","arguments":"{\\"path\\":\\"README.md\\"}"}}'

# dry-run:不真调工具,只校验参数
python tool_router.py --workspace D:\\onion\\andy \\
    --command '...' --dry-run

# 看 router 健康状态
python tool_router.py --workspace D:\\onion\\andy --status
```

## 输出格式

每个 tool_call 都会产出一个 OpenAI role:tool 消息(JSON object):
{
  "role": "tool",
  "tool_call_id": "call_abc123",
  "name": "onion.buildin.file_system.read_file",
  "content": "..."  # 工具返回内容(LLM 看到)
}

如果出错(解析/校验/执行失败),content 以 "[ERROR] xxx" 开头,L4 engine
收到后会塞回 messages 让 LLM 自我修正。

================================================================================
退出码
================================================================================
0  - 成功(可能部分 tool_call 失败,看 status 字段)
2  - 参数错误
3  - JSON 解析彻底失败(7 层兜底都没救)
99 - 内部异常
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
import time
import traceback
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

# 复用 tool_list.py 的基础组件
# 用直接 import 形式(而不是相对 import),这样 python tool_router.py 也能跑
# tool_list.py 跟本文件同目录,把当前目录加入 sys.path 即可
_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

from tool_list import (  # noqa: E402
    ONION_PREFIX,
    Tag,
    TOOL_NAME_PATTERN,
    ToolEntry,
    ToolRegistry,
    _ensure_project_root_on_path,
    clean_surrogate,
    collect_all,
    collect_buildin_tools,
    collect_mcp_tools,
    collect_skill_tools,
    make_tool_name,
    parse_tool_name,
)


# Windows 终端 cp936 默认编码下中文会乱码
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

# 默认 tool_call_id 前缀
CALL_ID_PREFIX = "call_"
CALL_ID_HASH_LEN = 12  # §5.11 MD5 兜底时取 12 位 hex

# 工具结果默认最大字符数(超过 middle-out 截断,见 design.md §6.7 必做)
MAX_TOOL_RESULT_CHARS = 50_000


# ============================================================================
# §9.3 6 层 JSON 解析兜底
# 详见 standard/tool_channel.md §5.5 + tool_accuracy.md §四-④
# ============================================================================
def parse_arguments(raw_args: str) -> tuple[Optional[dict], Optional[str]]:
    """
    6 层 JSON 解析兜底。

    Returns:
        (args, None) 成功
        (None, error_msg) 失败
    """
    if raw_args is None:
        return {}, None
    raw_args = clean_surrogate(raw_args)
    s = raw_args.strip()
    if not s:
        return {}, None
    # 如果不是 dict(是 list/str/number),按约定参数必须是 dict,这里直接报错
    if not (s.startswith("{") or s.lower().startswith("{") or s == "{}"):
        # 兜底:有些模型会输出 {key:value} 没引号,试 ast.literal_eval
        pass

    # Layer 1: 标准 JSON
    try:
        v = json.loads(s)
        if isinstance(v, dict):
            return v, None
        return None, f"Expected JSON object, got {type(v).__name__}"
    except json.JSONDecodeError:
        pass

    # Layer 2: 补全截断(末尾缺失括号)
    fixed = s.rstrip().rstrip(",")
    for tail in ("}", "}}", "}}}", "]\"", "\"]"):
        try:
            v = json.loads(fixed + tail)
            if isinstance(v, dict):
                return v, None
        except json.JSONDecodeError:
            continue

    # Layer 3: json-repair 库(若装了)
    try:
        from json_repair import repair_json
        v = json.loads(repair_json(s))
        if isinstance(v, dict):
            return v, None
    except (ImportError, Exception):
        pass

    # Layer 4: ast.literal_eval(单引号 dict 兜底)
    try:
        import ast
        v = ast.literal_eval(s)
        if isinstance(v, dict):
            return v, None
    except Exception:
        pass

    # Layer 5: smart quote 替换
    sq = (s
          .replace("“", '"').replace("”", '"')
          .replace("‘", "'").replace("’", "'"))
    if sq != s:
        try:
            v = json.loads(sq)
            if isinstance(v, dict):
                return v, None
        except json.JSONDecodeError:
            pass

    # Layer 6: 重新编码清洗 surrogate
    try:
        cleaned = s.encode("utf-8", errors="replace").decode("utf-8", errors="replace")
        v = json.loads(cleaned)
        if isinstance(v, dict):
            return v, None
    except json.JSONDecodeError:
        pass

    return None, f"Arguments not parseable as JSON object after 6-layer repair: {s[:200]!r}"


# ============================================================================
# §5.11 Tool call ID 兜底(MD5 合成)
# ============================================================================
def fallback_tool_call_id(tool_call: dict) -> str:
    """
    provider 漏给 tool_call_id 时,MD5 合成。
    """
    fn = tool_call.get("function", {}) or {}
    seed = f"{fn.get('name', '')}|{fn.get('arguments', '')}"
    return CALL_ID_PREFIX + hashlib.md5(seed.encode("utf-8", errors="replace")).hexdigest()[:CALL_ID_HASH_LEN]


def extract_tool_call_id(tool_call: dict) -> str:
    """优先用 provider 给的 id,缺失则 MD5 兜底。"""
    tid = tool_call.get("id")
    if tid and isinstance(tid, str) and tid.strip():
        return clean_surrogate(tid)
    return fallback_tool_call_id(tool_call)


# ============================================================================
# §3.4 JSON Schema 校验
# 用 jsonschema 库(若没装,降级到 buildin_client 的轻量校验器)
# ============================================================================
def validate_arguments(args: dict, schema: dict) -> Optional[str]:
    """
    JSON Schema 校验。失败返回错误消息(可执行,"哪个字段错"),成功返回 None。
    """
    if not schema:
        return None
    if not isinstance(args, dict):
        return f"Arguments must be a JSON object, got {type(args).__name__}"

    schema_type = schema.get("type", "object")
    if schema_type != "object":
        # 简单类型不深入校验
        return None

    # 尝试 jsonschema 库
    try:
        from jsonschema import ValidationError, validate
        try:
            validate(instance=args, schema=schema)
            return None
        except ValidationError as e:
            path = ".".join(str(p) for p in e.absolute_path) or "(root)"
            return f"参数 `{path}` 校验失败: {e.message}"
    except ImportError:
        pass

    # 降级:用 buildin_client 的轻量校验器
    try:
        _ensure_project_root_on_path()
        from src.infrastructure.tool_shell.buildin_client import _validate_arguments
        ok, err = _validate_arguments(schema, args)
        return None if ok else err
    except Exception as e:
        # 校验器自身崩了,先放过(避免 router 自己 crash)
        return None


# ============================================================================
# 大结果截断(middle-out)
# ============================================================================
def _truncate_middle(text: str, max_chars: int = MAX_TOOL_RESULT_CHARS) -> tuple[str, bool]:
    """保留前 50% + 后 50%(参考 buildin_client._truncate_middle)。"""
    if not text or len(text) <= max_chars:
        return text or "", False
    half = max_chars // 2
    skip = len(text) - max_chars
    return (
        text[:half]
        + f"\n\n[... output truncated: 共 {len(text)} 字符,截断 {skip} 字符 ...]\n\n"
        + text[-half:]
    ), True


# ============================================================================
# RouterResult:路由单条 tool_call 的统一返回
# 详见 design.md §9.2
# ============================================================================
@dataclass
class RouterResult:
    """
    tool_router 的统一返回。
    对应 OpenAI role:"tool" 消息的字段(§6.1 必做)。
    """
    tool_call_id: str
    name: str
    success: bool
    is_error: bool
    content: str
    error: Optional[str] = None
    data: dict = field(default_factory=dict)

    def to_tool_message(self) -> dict:
        """转 OpenAI role:tool 消息(L4 engine 直接用这个写回 history)。"""
        return {
            "role": "tool",
            "tool_call_id": self.tool_call_id,
            "name": self.name,
            "content": self.content,
        }

    def to_dict(self) -> dict:
        """完整可观测字段(给 CLI / 日志看,不全进 LLM context)。"""
        d = asdict(self)
        d["data"] = dict(self.data)
        return d


# ============================================================================
# §10 Skill 的特殊处理(不是函数调用,加载 L2 提示词回灌)
# ============================================================================
def _dispatch_skill(
    call_id: str,
    name: str,
    scope: str,
    args: dict,
    start_ts: float,
    skills_engine: Any,
) -> RouterResult:
    """
    Skill 特殊路径:
      - 不执行任何函数
      - 加载 SKILL.md 的 L2 正文
      - 包装成 # Activated Skill: xxx 的 markdown,作为 content 回灌
    """
    if skills_engine is None:
        return _err_result(
            call_id, name, "No skills engine registered",
            tag="skill", scope=scope, tool="__load__",
            arguments=args, duration_ms=_elapsed_ms(start_ts),
        )

    skill_name = scope
    try:
        skill = skills_engine.load_skill_instruction(skill_name)
    except Exception as e:
        return _err_result(
            call_id, name, f"Skill load failed: {type(e).__name__}: {e}",
            tag="skill", scope=scope, tool="__load__",
            arguments=args, duration_ms=_elapsed_ms(start_ts),
        )

    body = skill.body or "(skill body is empty)"
    body = clean_surrogate(body)
    content = (
        f"# Activated Skill: {skill.properties.name}\n\n"
        f"{body}\n\n"
        f"---\n"
        f"[Skill {skill_name!r} activated via {name}. "
        f"Follow the skill instructions above to complete the user's request. "
        f"Use available tools (e.g. file operations, MCP servers) to execute the workflow. "
        f"Do NOT call {name} again in this turn — the skill is now active.]"
    )

    # 大 body 截断(SKILL.md 可能很长)
    content, was_truncated = _truncate_middle(content, MAX_TOOL_RESULT_CHARS)

    return RouterResult(
        tool_call_id=call_id,
        name=name,
        success=True,
        is_error=False,
        content=content,
        data={
            "tag": "skill",
            "scope": skill_name,
            "tool": "__load__",
            "arguments": args,
            "duration_ms": _elapsed_ms(start_ts),
            "truncated": was_truncated,
            "disclosure_level": "L2",
            "skill_name": skill_name,
        },
    )


# ============================================================================
# _dispatch_buildin:同步,直接调 BuildinClient.call_tool
# ============================================================================
def _dispatch_buildin(
    call_id: str,
    name: str,
    scope: str,
    tool: str,
    args: dict,
    start_ts: float,
    buildin_client: Any,
) -> RouterResult:
    if buildin_client is None:
        return _err_result(
            call_id, name, "No buildin client registered",
            tag="buildin", scope=scope, tool=tool,
            arguments=args, duration_ms=_elapsed_ms(start_ts),
        )

    spec = f"{scope}.{tool}"
    try:
        result = buildin_client.call_tool(spec, args)
    except Exception as e:
        return _err_result(
            call_id, name, f"Buildin tool exception: {type(e).__name__}: {e}",
            tag="buildin", scope=scope, tool=tool,
            arguments=args, duration_ms=_elapsed_ms(start_ts),
        )

    return _format_client_result(
        call_id, name, result, "buildin", scope, tool, args, start_ts,
    )


# ============================================================================
# _dispatch_mcp:async,在 sync wrapper 里跑 event loop
# ============================================================================
def _dispatch_mcp(
    call_id: str,
    name: str,
    scope: str,
    tool: str,
    args: dict,
    start_ts: float,
    mcp_client: Any,
) -> RouterResult:
    if mcp_client is None:
        return _err_result(
            call_id, name, "No MCP client registered",
            tag="mcp", scope=scope, tool=tool,
            arguments=args, duration_ms=_elapsed_ms(start_ts),
        )

    try:
        coro = mcp_client.call_tool(scope, tool, args)
        # MCP client.call_tool 返回的是 Any(原始 MCP content 列表)
        result_raw = _run_async_safely(coro)
    except Exception as e:
        return _err_result(
            call_id, name, f"MCP tool exception: {type(e).__name__}: {e}",
            tag="mcp", scope=scope, tool=tool,
            arguments=args, duration_ms=_elapsed_ms(start_ts),
        )

    # MCP 返回的是 content 列表(每个 item 有 .text / .data 等属性)
    # 统一格式化
    if isinstance(result_raw, list):
        text_parts = []
        for item in result_raw:
            if hasattr(item, "text"):
                text_parts.append(str(item.text))
            elif hasattr(item, "data"):
                text_parts.append(f"[data: {item.data}]")
            else:
                text_parts.append(str(item))
        content = "\n".join(text_parts) if text_parts else "(empty result)"
    else:
        content = str(result_raw)

    content = clean_surrogate(content)
    content, was_truncated = _truncate_middle(content, MAX_TOOL_RESULT_CHARS)

    return RouterResult(
        tool_call_id=call_id,
        name=name,
        success=True,
        is_error=False,
        content=content,
        data={
            "tag": "mcp",
            "scope": scope,
            "tool": tool,
            "arguments": args,
            "duration_ms": _elapsed_ms(start_ts),
            "truncated": was_truncated,
            "raw_result_type": type(result_raw).__name__,
        },
    )


def _run_async_safely(coro):
    """
    在 sync 上下文里跑 async coroutine。
    优先用 running loop(没的话建一个),不再做轮询。
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError("loop closed")
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


# ============================================================================
# _format_client_result:把 client 统一返回 dict → RouterResult
# ============================================================================
def _format_client_result(
    call_id: str, name: str,
    client_result: dict,
    tag: str, scope: str, tool: str,
    args: dict, start_ts: float,
) -> RouterResult:
    """
    client 统一返回 {success, content, is_error, error, data} → RouterResult。
    容错:client_result 不是 dict 时也尽量不崩。
    """
    if not isinstance(client_result, dict):
        # 不是 dict,整个当 content
        content = clean_surrogate(str(client_result))
        is_error = content.startswith("[ERROR]")
        return RouterResult(
            tool_call_id=call_id, name=name,
            success=not is_error, is_error=is_error,
            content=content,
            data={"tag": tag, "scope": scope, "tool": tool,
                  "arguments": args, "duration_ms": _elapsed_ms(start_ts),
                  "raw_result_type": type(client_result).__name__},
        )

    is_error = bool(client_result.get("is_error", not client_result.get("success", False)))
    content = clean_surrogate(str(client_result.get("content", "")))
    error_msg = client_result.get("error")
    inner_data = client_result.get("data") or {}

    content, was_truncated = _truncate_middle(content, MAX_TOOL_RESULT_CHARS)

    data = {
        "tag": tag,
        "scope": scope,
        "tool": tool,
        "arguments": args,
        "duration_ms": _elapsed_ms(start_ts),
        "truncated": was_truncated,
        "raw_result": inner_data.get("raw_result") if isinstance(inner_data, dict) else inner_data,
    }

    return RouterResult(
        tool_call_id=call_id, name=name,
        success=not is_error, is_error=is_error,
        content=(f"[ERROR] {content}" if is_error and not content.startswith("[ERROR]") else content),
        error=error_msg,
        data=data,
    )


# ============================================================================
# _err_result / _elapsed_ms 辅助
# ============================================================================
def _err_result(
    call_id: str, name: str, msg: str,
    tag: Optional[str] = None, scope: Optional[str] = None,
    tool: Optional[str] = None, arguments: Optional[dict] = None,
    duration_ms: int = 0,
) -> RouterResult:
    return RouterResult(
        tool_call_id=call_id, name=name,
        success=False, is_error=True,
        content=f"[ERROR] {msg}",
        error=msg,
        data={"tag": tag, "scope": scope, "tool": tool,
              "arguments": arguments or {}, "duration_ms": duration_ms},
    )


def _elapsed_ms(start_ts: float) -> int:
    return int((time.time() - start_ts) * 1000)


# ============================================================================
# ToolRouter 主类
# 详见 design.md §9.4
# ============================================================================
class ToolRouter:
    """
    tool_router.py 的主类。
    接收 ToolRegistry,提供 dispatch_one / dispatch_many 同步 API。
    """

    def __init__(self, registry: ToolRegistry):
        self.registry = registry

    def dispatch_one(
        self,
        tool_call: dict,
        *,
        dry_run: bool = False,
    ) -> RouterResult:
        """
        同步路由单条 tool_call(详见 design.md §7.2 七步)。

        Args:
            tool_call: LLM 返回的 tool_call dict
                {id?, type:"function", function:{name, arguments:str}}
            dry_run: True 时不真调工具,只校验参数(给调试用)

        Returns:
            RouterResult(tool_call_id, name, success, is_error, content, error, data)
        """
        start_ts = time.time()

        # ── Step 1: tool_call_id 兜底 ──────────────────────────────────────
        call_id = extract_tool_call_id(tool_call)
        raw_name = (tool_call.get("function", {}) or {}).get("name", "") or ""
        name = clean_surrogate(raw_name)
        raw_args = (tool_call.get("function", {}) or {}).get("arguments", "") or ""

        # ── Step 2: 解析 name ──────────────────────────────────────────────
        parsed = parse_tool_name(name)
        if parsed is None:
            return _err_result(
                call_id, name,
                f"Invalid tool name format. Expected onion.<tag>.<scope>.<tool>, got: {name!r}",
                duration_ms=_elapsed_ms(start_ts),
            )
        tag, scope, tool = parsed

        # ── Step 3: 解析 arguments(7 层 JSON 修复) ─────────────────────────
        args, parse_err = parse_arguments(raw_args)
        if parse_err:
            return _err_result(
                call_id, name, f"Argument parse failed: {parse_err}",
                tag=tag, scope=scope, tool=tool,
                arguments=raw_args, duration_ms=_elapsed_ms(start_ts),
            )

        # ── Step 4: 查 entry 拿 schema ─────────────────────────────────────
        entry = self.registry.lookup(name)
        if entry is None:
            # 模糊匹配提示
            hint = self._fuzzy_hint(name)
            msg = f"Unknown tool: {name!r}"
            if hint:
                msg += f". Did you mean: {hint}"
            return _err_result(
                call_id, name, msg,
                tag=tag, scope=scope, tool=tool,
                arguments=args, duration_ms=_elapsed_ms(start_ts),
            )

        # ── Step 5: schema 校验 ────────────────────────────────────────────
        validation_err = validate_arguments(args, entry.input_schema)
        if validation_err:
            return _err_result(
                call_id, name, f"Argument schema validation failed: {validation_err}",
                tag=tag, scope=scope, tool=tool,
                arguments=args, duration_ms=_elapsed_ms(start_ts),
            )

        if dry_run:
            return RouterResult(
                tool_call_id=call_id, name=name,
                success=True, is_error=False,
                content="[DRY-RUN] arguments parsed and validated; tool not executed",
                data={"tag": tag, "scope": scope, "tool": tool,
                      "arguments": args, "duration_ms": _elapsed_ms(start_ts),
                      "dry_run": True},
            )

        # ── Step 6: 按 tag 路由 ────────────────────────────────────────────
        if tag == "skill":
            engine = self.registry.clients.get(Tag.SKILL)
            return _dispatch_skill(call_id, name, scope, args, start_ts, engine)
        elif tag == "buildin":
            client = self.registry.clients.get(Tag.BUILDIN)
            return _dispatch_buildin(call_id, name, scope, tool, args, start_ts, client)
        elif tag == "mcp":
            client = self.registry.clients.get(Tag.MCP)
            return _dispatch_mcp(call_id, name, scope, tool, args, start_ts, client)
        elif tag == "agent":
            return _err_result(
                call_id, name,
                "Tag 'agent' is reserved for P1 (update_plan/finish_loop/record_memory/ask_user). "
                "Not implemented yet.",
                tag=tag, scope=scope, tool=tool,
                arguments=args, duration_ms=_elapsed_ms(start_ts),
            )
        else:
            return _err_result(
                call_id, name, f"Unsupported tag: {tag}",
                tag=tag, scope=scope, tool=tool,
                arguments=args, duration_ms=_elapsed_ms(start_ts),
            )

    def _fuzzy_hint(self, name: str, n: int = 3) -> str:
        """模糊匹配提示(§5.4 强烈建议)。"""
        try:
            import difflib
            all_names = list(self.registry.entries.keys())
            close = difflib.get_close_matches(name, all_names, n=n, cutoff=0.4)
            return ", ".join(close) if close else ""
        except Exception:
            return ""

    def dispatch_many(
        self,
        tool_calls: list[dict],
        *,
        parallel: bool = False,
        dry_run: bool = False,
    ) -> list[RouterResult]:
        """
        批量路由。默认串行(parallel=False),因为:
          1. CLI 场景下,串行更易调试
          2. asyncio.gather 在 sync 上下文里有点别扭
        SDK 阶段(被 L4 engine 调用)可以传 parallel=True
        """
        if not tool_calls:
            return []
        if not parallel or len(tool_calls) == 1:
            return [self.dispatch_one(tc, dry_run=dry_run) for tc in tool_calls]
        # 并行版本(预留)
        async def _gather():
            return await asyncio.gather(
                *(self._dispatch_one_async(tc, dry_run=dry_run) for tc in tool_calls),
                return_exceptions=True,
            )
        raws = _run_async_safely(_gather())
        out: list[RouterResult] = []
        for tc, r in zip(tool_calls, raws):
            if isinstance(r, BaseException):
                out.append(_err_result(
                    extract_tool_call_id(tc),
                    (tc.get("function", {}) or {}).get("name", ""),
                    f"Dispatcher crashed: {type(r).__name__}: {r}",
                ))
            else:
                out.append(r)
        return out

    async def _dispatch_one_async(self, tool_call: dict, *, dry_run: bool = False) -> RouterResult:
        """async 版本,被 dispatch_many(parallel=True) 使用。"""
        # 简单起见,async 版本走相同的 sync 路径
        # (MCP 内部已是 async,会自动调度)
        return self.dispatch_one(tool_call, dry_run=dry_run)


# ============================================================================
# CLI 工具函数
# ============================================================================
def _parse_command_arg(command_str: Optional[str], command_file: Optional[str]) -> list[dict]:
    """
    解析 --command 或 --command-file 输入为 tool_call 列表。
    接受:
      - 单个 dict(JSON object)
      - 列表 of dicts(JSON array)
      - JSONL(每行一个 dict)
    """
    if not command_str and not command_file:
        return []
    raw_text = ""
    if command_file:
        p = Path(command_file)
        if not p.is_file():
            print(f"错误: --command-file 路径不存在: {p}", file=sys.stderr)
            sys.exit(2)
        raw_text = p.read_text(encoding="utf-8")
    else:
        raw_text = command_str

    raw_text = raw_text.strip()
    if not raw_text:
        return []

    # 试 1: 整个文本是 JSON 数组
    try:
        v = json.loads(raw_text)
        if isinstance(v, list):
            return [x for x in v if isinstance(x, dict)]
        if isinstance(v, dict):
            return [v]
    except json.JSONDecodeError:
        pass

    # 试 2: JSONL
    calls: list[dict] = []
    for line_no, line in enumerate(raw_text.splitlines(), start=1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            obj = json.loads(line)
            if isinstance(obj, dict):
                calls.append(obj)
        except json.JSONDecodeError as e:
            print(f"错误: --command-file 第 {line_no} 行不是合法 JSON: {e}", file=sys.stderr)
            sys.exit(2)
    return calls


def _print_router_status(registry: ToolRegistry) -> int:
    s = registry.status()
    print("Tool Router Status")
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


def _print_results(results: list[RouterResult], pretty: bool = True) -> int:
    """
    pretty print 路由结果。
    每个结果:
      1) 先 print OpenAI role:tool 消息(L4 engine 直接用)
      2) 再 print 摘要(给人/debug 看)
    """
    overall_ok = True
    for idx, r in enumerate(results, start=1):
        # ─── 1) OpenAI role:tool 消息(主要交付物) ──────────────────────
        msg = r.to_tool_message()
        if pretty:
            print(f"\n[{idx}/{len(results)}] ── OpenAI role:tool ────────────────")
            print(json.dumps(msg, ensure_ascii=False, indent=2))
        else:
            print(json.dumps(msg, ensure_ascii=False))

        # ─── 2) 摘要(成功/失败、耗时、tag/scope/tool) ──────────────────
        data = r.data
        if pretty:
            print(f"\n  Summary:")
            status_str = "✓ OK" if r.success else "✗ ERROR"
            print(f"    status:        {status_str}  (is_error={r.is_error})")
            if r.error:
                print(f"    error:         {r.error}")
            print(f"    tool_call_id:  {r.tool_call_id}")
            print(f"    name:          {r.name}")
            print(f"    tag:           {data.get('tag', '?')}")
            print(f"    scope:         {data.get('scope', '?')}")
            print(f"    tool:          {data.get('tool', '?')}")
            print(f"    arguments:     {json.dumps(data.get('arguments', {}), ensure_ascii=False)}")
            print(f"    duration_ms:   {data.get('duration_ms', 0)}")
            if data.get("truncated"):
                print(f"    truncated:     True  (result > {MAX_TOOL_RESULT_CHARS} chars)")
            if "disclosure_level" in data:
                print(f"    disclosure:    {data['disclosure_level']}")
            if "raw_result_type" in data:
                print(f"    raw_type:      {data['raw_result_type']}")

        if not r.success:
            overall_ok = False

    if pretty:
        print(f"\n{'─' * 60}")
        print(f"  Overall: {len(results)} call(s), "
              f"{sum(1 for r in results if r.success)} ok, "
              f"{sum(1 for r in results if not r.success)} failed")

    return 0 if overall_ok else 0  # 注意: 退出码不因为部分失败而变成非 0,
                                    # 让上层能继续处理。但用户 --strict 时可以传非 0。


# ============================================================================
# argparse + 主入口
# ============================================================================
def main():
    parser = argparse.ArgumentParser(
        description="Onion Agent 工具调用路由(parse → validate → dispatch → OpenAI role:tool)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 单条指令(注意 JSON 内引号要转义)
  python tool_router.py --workspace D:\\onion\\andy \\
      --command '{"id":"call_1","type":"function","function":{"name":"onion.buildin.file_system.list_dir","arguments":"{\\"path\\":\\".\\"}"}}'

  # 多条指令(从文件读,JSON 数组或 JSONL)
  python tool_router.py --workspace D:\\onion\\andy --command-file calls.json

  # 不连 MCP
  python tool_router.py --no-mcp \\
      --command '{"id":"call_1","type":"function","function":{"name":"onion.buildin.file_system.read_file","arguments":"{\\"path\\":\\"README.md\\"}"}}'

  # dry-run:只校验不执行
  python tool_router.py --workspace D:\\onion\\andy \\
      --command '...' --dry-run

  # router 健康状态
  python tool_router.py --workspace D:\\onion\\andy --status
        """,
    )
    parser.add_argument(
        "--workspace", "-w", default=None,
        help="agent 工作区根目录",
    )
    parser.add_argument(
        "--tools-dir", default=None,
        help="buildin_tools 目录路径(覆盖默认)",
    )
    parser.add_argument(
        "--no-mcp", dest="auto_connect_mcp", action="store_false",
        help="不自动连接 MCP server",
    )
    parser.set_defaults(auto_connect_mcp=True)
    parser.add_argument(
        "--command", "-c", default=None,
        help='单条或 JSON 数组 tool_call 字符串,如 \'{"id":"call_1",...}\'',
    )
    parser.add_argument(
        "--command-file", "-f", default=None,
        help="tool_call 文件路径(支持 JSON 数组 / JSONL)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="只解析和校验,不真调工具",
    )
    parser.add_argument(
        "--pretty", dest="pretty", action="store_true", default=True,
        help="人类可读输出(默认开启)",
    )
    parser.add_argument(
        "--no-pretty", dest="pretty", action="store_false",
        help="纯 JSON 输出(每行一个 role:tool 消息,适合管道处理)",
    )
    parser.add_argument(
        "--status", "-s", action="store_true",
        help="输出 router 状态摘要",
    )

    args = parser.parse_args()

    # 解析 tool_call 列表
    tool_calls = _parse_command_arg(args.command, args.command_file)

    # 收集工具
    workspace_dir = Path(args.workspace) if args.workspace else None
    tools_dir = Path(args.tools_dir) if args.tools_dir else None
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
        print(f"内部异常(collect_all): {type(e).__name__}: {e}", file=sys.stderr)
        traceback.print_exc()
        return 99

    # 状态命令
    if args.status:
        return _print_router_status(registry)

    # 没有 command 时,只跑状态
    if not tool_calls:
        if not args.status:
            print("未提供 --command 或 --command-file;显示 router 状态:", file=sys.stderr)
        return _print_router_status(registry)

    # 路由执行
    router = ToolRouter(registry)
    try:
        results = router.dispatch_many(tool_calls, parallel=False, dry_run=args.dry_run)
    except KeyboardInterrupt:
        print("\n已取消", file=sys.stderr)
        return 130
    except Exception as e:
        print(f"内部异常(dispatch): {type(e).__name__}: {e}", file=sys.stderr)
        traceback.print_exc()
        return 99

    return _print_results(results, pretty=args.pretty)


if __name__ == "__main__":
    sys.exit(main())
