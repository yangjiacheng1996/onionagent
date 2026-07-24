# -*- coding: utf-8 -*-
"""
================================================================================
File System 工具 - 内置工具集 (L5 - Infrastructure / buildin_tools)
================================================================================

# 开发计划

Onion Agent 内置 3 大基础工具之一:文件系统。

# 工具清单(8 个原子化工具,每个都遵循 OpenAI Chat Completions 风格 schema)

1. `read_file`      - 读文件(支持行范围 + max_chars 截断)
2. `write_file`     - 写文件(支持 append,atomic write 防半写)
3. `edit_file`      - 受控编辑(Claude Code 风格:old_string → new_string)
4. `list_dir`       - 列目录(支持 glob 模式 + recursive)
5. `delete_file`    - 删除文件 / 空目录(防误删)
6. `copy_file`      - 复制文件或目录(支持 overwrite)
7. `move_file`      - 移动 / 重命名文件或目录(支持 overwrite)
8. `get_properties` - 查询文件 / 目录属性(type / size / mtime / atime / ctime / mode / symlink)

# 设计原则(对照 harness/01_market_research/standard/file_backend.md 和 tool_channel.md)

- **L5 基础设施层** - 只暴露"原子函数 + schema",不耦合 LLM 协议
- **Pydantic v2 反射**(§3.2 强烈建议) - handler 用 Pydantic 校验 args,杜绝字段漂移
- **atomic write**(file_backend §8.3) - 写盘 temp + rename,防半写状态
- **Path.resolve()**(tool_channel §1.4) - 解析后比较,防符号链接绕过
- **错误透明** - handler 返回 {success, content, is_error, error} 统一契约,
  LLM 看到错误能自我修正,绝不允许 silent 静默(对照 tool_channel §3.4 反例)
- **JSON Schema strict**(tool_channel §3.3) - required + additionalProperties: false
- **所见即所得**(project_manager §所见即所得) - 每个工具都暴露 CLI,
  产品经理跑一下就能知道效果,不用等到 LLM 调起来再调试

# CLI 测试示例

```powershell
# 1. 读文件(整文件)
python file_system.py read --path C:/workspace/README.md

# 2. 读文件(行范围)
python file_system.py read --path C:/workspace/main.py --start-line 10 --end-line 30

# 3. 写文件
python file_system.py write --path C:/tmp/test.txt --content "hello world"

# 4. 追加写
python file_system.py write --path C:/tmp/test.txt --content " more" --append

# 5. 受控编辑
python file_system.py edit --path C:/tmp/test.txt --old-string "hello" --new-string "hi"

# 6. 列目录
python file_system.py list --path C:/workspace --pattern "*.py"

# 7. 递归列目录
python file_system.py list --path C:/workspace --recursive --max-entries 50

# 8. 删文件
python file_system.py delete --path C:/tmp/test.txt

# 9. 复制文件
python file_system.py copy --src C:/tmp/a.txt --dst C:/tmp/b.txt
python file_system.py copy --src C:/tmp/src_dir --dst C:/tmp/dst_dir

# 10. 移动 / 重命名
python file_system.py move --src C:/tmp/a.txt --dst C:/tmp/sub/b.txt
python file_system.py move --src C:/tmp/old_name.txt --dst C:/tmp/new_name.txt

# 11. 查文件 / 目录属性
python file_system.py properties --path C:/tmp/test.txt
python file_system.py properties --path C:/tmp/

# 12. 查看本模块所有工具 schema
python file_system.py --list-tools
```

# 退出码

0  - 成功
2  - 参数错误
3  - 路径安全拒绝(命中黑名单)
4  - 文件 / 目录不存在
5  - 权限拒绝
6  - 编辑失败(old_string 不唯一且未指定 replace_all)
99 - 内部异常
"""

from __future__ import annotations

import argparse
import os
import re
import stat
import sys
import tempfile
from pathlib import Path
from typing import Optional

# Windows 终端 cp936 默认编码下中文会乱码,统一在脚本入口把 stdout/stderr 切到 UTF-8
if sys.platform == "win32":
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except Exception:
            pass
    del _stream


# ============================================================================
# 路径安全:基础黑名单(MVP 阶段,buildin_client 还会再加一层)
# ============================================================================
# 对照 harness/01_market_research/standard/tool_channel.md §1.4 / §5.4
# LLM 永远不能读 ~/.ssh/ ~/.aws/ ~/.gnupg/ ~/.kube/ /etc/sudoers 等
# 这里只做"绝对路径前缀"粗筛,buildin_client 会做更严格的 resolve() 比较
_BASIC_FORBIDDEN_PREFIXES = (
    # Windows 系统关键路径
    "C:\\Windows\\System32",
    "C:\\Windows\\SysWOW64",
    "C:\\Program Files",
    "C:\\Program Files (x86)",
    "C:\\ProgramData",
    # POSIX 系统关键路径(转义反斜杠)
    "/etc/sudoers",
    "/etc/passwd",
    "/etc/shadow",
    "/etc/sudoers.d",
    "/boot",
    "/sys",
    "/proc",
)


def _is_basic_path_safe(path: Path) -> tuple[bool, str]:
    """
    基础路径安全检查(在 buildin_client 之前)。

    规则:
      1. 路径必须能 resolve()
      2. 命中绝对路径黑名单前缀 → 拒绝
      3. 不做"必须在白名单内"判断 - 这是 buildin_client 的事

    返回 (ok, reason)。
    """
    try:
        resolved = path.resolve()
    except OSError as e:
        return False, f"路径解析失败: {e}"

    resolved_str = str(resolved)
    # 兼容 Windows: 路径前缀比较时不区分大小写
    for prefix in _BASIC_FORBIDDEN_PREFIXES:
        if resolved_str.lower().startswith(prefix.lower()):
            return False, f"路径命中系统关键区域黑名单: {prefix}"

    return True, ""


# ============================================================================
# 原子化写文件(temp + rename,防半写)
# ============================================================================
def atomic_write_text(path: Path, content: str, encoding: str = "utf-8") -> None:
    """
    原子化写文本文件(temp + fsync + rename)。

    为什么 atomic:
      - 写一半进程被 kill,文件会变成半写状态,session.jsonl 损坏会导致整个工作区不可用
      - 任何 .md/.jsonl/.json 写盘都应该走这里,不能直接 path.write_text()

    实现:
      1. 在目标目录创建 .<name>.XXXXXX.tmp
      2. 写完 flush + fsync
      3. os.replace() 原子替换
      4. Windows 跨盘时 os.replace 失败 → 降级到 shutil.move
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline="\n") as f:
            f.write(content)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                # Windows 某些 fs 实现不支持 fsync,降级
                pass
        try:
            os.replace(tmp_path, path)
        except OSError:
            # Windows 跨盘时 os.replace 会失败,降级
            import shutil
            shutil.move(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


# ============================================================================
# 工具 schema (OpenAI Chat Completions 风格)
# ============================================================================
# 对照 tool_channel.md §3.3 / §3.4
# - type:"object" 强制 object top-level
# - required 必填字段
# - additionalProperties: false 强制 strict
# - description 写清楚"做什么 + 返回什么",这是 LLM 选工具的唯一依据
TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": (
                "读取文件内容。返回文本内容、文件总行数、读取的行范围。"
                "支持行范围分页(start_line/end_line)以避免单次返回过大。"
                "如需读取二进制文件请用 VLM 工具,本工具只处理文本。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "文件的绝对路径",
                    },
                    "start_line": {
                        "type": "integer",
                        "description": "起始行(1-indexed,包含)。不传则从头开始。",
                    },
                    "end_line": {
                        "type": "integer",
                        "description": "结束行(1-indexed,包含)。不传则读到文件末尾。",
                    },
                    "max_chars": {
                        "type": "integer",
                        "description": "返回内容的最大字符数,默认 50000。超过会被截断并在末尾标注。",
                    },
                },
                "required": ["path"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": (
                "写文件。默认覆盖;append=true 时追加。"
                "自动创建父目录。写盘采用 atomic write(temp+rename),"
                "半写状态不会损坏目标文件。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "文件的绝对路径",
                    },
                    "content": {
                        "type": "string",
                        "description": "要写入的文本内容",
                    },
                    "append": {
                        "type": "boolean",
                        "description": "是否追加写入(默认 false = 覆盖)。",
                    },
                },
                "required": ["path", "content"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": (
                "受控编辑文件:把文件中第一处出现的 old_string 替换为 new_string。"
                "old_string 必须在文件中唯一(否则需要 replace_all=true)。"
                "对大文件做『小范围精确编辑』比 write_file 更安全 - 不会不小心覆盖全文。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "文件的绝对路径",
                    },
                    "old_string": {
                        "type": "string",
                        "description": "要被替换的原始文本(必须完全匹配,包括缩进和换行)",
                    },
                    "new_string": {
                        "type": "string",
                        "description": "替换后的新文本",
                    },
                    "replace_all": {
                        "type": "boolean",
                        "description": "替换全部出现的位置(默认 false = 只替换第一处)",
                    },
                },
                "required": ["path", "old_string", "new_string"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_dir",
            "description": (
                "列目录内容。返回 [{name, type, size, mtime}, ...]。"
                "支持 glob 模式(如 '*.py'、'test_*.json')和 recursive 递归。"
                "max_entries 限制返回数量,防止一次返回太多。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "目录的绝对路径",
                    },
                    "pattern": {
                        "type": "string",
                        "description": "glob 模式,如 '*.py'。不传或空字符串 = 全部。",
                    },
                    "recursive": {
                        "type": "boolean",
                        "description": "是否递归子目录(默认 false)",
                    },
                    "max_entries": {
                        "type": "integer",
                        "description": "最大返回条目数,默认 500。超过会被截断并标注。",
                    },
                },
                "required": ["path"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_file",
            "description": (
                "删除文件或目录。"
                "默认拒绝删除非空目录(防误删),需要 recursive=true 才允许递归删。"
                "删除前会做安全检查(参考 file_system._is_basic_path_safe)。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要删除的文件或目录的绝对路径",
                    },
                    "recursive": {
                        "type": "boolean",
                        "description": "递归删除(用于非空目录)。默认 false,非空目录会拒绝。",
                    },
                },
                "required": ["path"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "copy_file",
            "description": (
                "复制文件或目录(src → dst)。"
                "文件用 shutil.copy2(保留 mtime);目录用 shutil.copytree(递归)。"
                "默认 overwrite=false(目标存在直接报错),"
                "需要覆盖显式 overwrite=true。"
                "src 路径不存在 / dst 是 src 的子路径 / 跨盘复制等情况会返回错误。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "src": {
                        "type": "string",
                        "description": "源文件或目录的绝对路径",
                    },
                    "dst": {
                        "type": "string",
                        "description": "目标路径(绝对路径)。若 dst 是已存在的目录,文件会复制进该目录。",
                    },
                    "overwrite": {
                        "type": "boolean",
                        "description": "目标已存在时是否覆盖(默认 false)",
                    },
                },
                "required": ["src", "dst"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "move_file",
            "description": (
                "移动或重命名文件 / 目录(src → dst)。"
                "同盘走 rename(原子,瞬间完成);跨盘走 copy + delete 源,可能慢。"
                "默认 overwrite=false,目标已存在报错。"
                "常用于:重命名(同一目录,改 dst 文件名)、移动(改 dst 父目录)。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "src": {
                        "type": "string",
                        "description": "源文件或目录的绝对路径",
                    },
                    "dst": {
                        "type": "string",
                        "description": "目标路径(绝对路径)",
                    },
                    "overwrite": {
                        "type": "boolean",
                        "description": "目标已存在时是否覆盖(默认 false)",
                    },
                },
                "required": ["src", "dst"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_properties",
            "description": (
                "查询文件 / 目录属性(不读内容)。"
                "返回 type / size / mtime / atime / ctime / mode(octal) / nlink / inode / is_symlink / symlink_target。"
                "符号链接用 lstat(不跟随),所以报告的是链接本身不是目标。"
                "常用于:决策前先看一眼(文件还是目录?多大?多久没改了?)。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "文件或目录的绝对路径",
                    },
                    "follow_symlinks": {
                        "type": "boolean",
                        "description": "是否跟随符号链接查目标属性(默认 false 报告链接本身;true 时 stat 而非 lstat)",
                    },
                },
                "required": ["path"],
                "additionalProperties": False,
            },
        },
    },
]


# ============================================================================
# Handler 工具返回契约
# ============================================================================
# 所有 handler 返回 dict,统一契约:
#   {
#     "success": bool,        # 总体成功
#     "is_error": bool,       # OpenAI role=tool 兼容(成功也可能是"内容是错误消息")
#     "content": str,         # 给 LLM 看的主要文本
#     "error": Optional[str], # 错误描述(成功时为 None)
#     "data": dict,           # 结构化数据(给上层 tool_router 用)
#   }
def _ok(content: str, data: Optional[dict] = None) -> dict:
    return {
        "success": True,
        "is_error": False,
        "content": content,
        "error": None,
        "data": data or {},
    }


def _err(error_msg: str, data: Optional[dict] = None) -> dict:
    return {
        "success": False,
        "is_error": True,
        "content": f"[ERROR] {error_msg}",
        "error": error_msg,
        "data": data or {},
    }


# ============================================================================
# 工具实现
# ============================================================================
def read_file(
    path: str,
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
    max_chars: int = 50000,
) -> dict:
    """
    读取文件。

    Args:
        path: 文件绝对路径
        start_line: 起始行(1-indexed,包含)
        end_line: 结束行(1-indexed,包含)
        max_chars: 返回最大字符数,默认 50000

    Returns:
        标准工具返回 dict。
    """
    p = Path(path)
    ok, reason = _is_basic_path_safe(p)
    if not ok:
        return _err(f"路径安全拒绝: {reason}")

    if not p.exists():
        return _err(f"文件不存在: {path}")
    if not p.is_file():
        return _err(f"路径不是文件(可能是目录): {path}")

    try:
        # 用 utf-8-sig 兼容 Windows 工具写入的 BOM
        with open(p, "r", encoding="utf-8-sig", errors="replace") as f:
            text = f.read()
    except PermissionError as e:
        return _err(f"权限拒绝: {e}")
    except OSError as e:
        return _err(f"读取失败: {e}")

    # 行范围分页
    total_lines = text.count("\n") + (0 if text.endswith("\n") else 1)
    lines = text.splitlines()  # 不保留末尾 \n,索引 0-based

    if start_line is not None or end_line is not None:
        s = (start_line or 1) - 1  # 1-indexed → 0-indexed
        e = end_line if end_line is not None else len(lines)
        if s < 0:
            s = 0
        if e > len(lines):
            e = len(lines)
        if s >= len(lines):
            return _ok(
                f"[空范围] 第 {s+1} 行到第 {e} 行(文件只有 {len(lines)} 行)",
                data={
                    "path": str(p),
                    "total_lines": total_lines,
                    "start_line": s + 1,
                    "end_line": e,
                    "truncated": False,
                },
            )
        chunk = "\n".join(lines[s:e])
        range_info = f"第 {s+1}-{e} 行 / 共 {total_lines} 行"
    else:
        chunk = text
        range_info = f"全文 / 共 {total_lines} 行"

    # max_chars 截断(head+tail 模式参考 tool_channel §6.7)
    truncated = False
    if len(chunk) > max_chars:
        half = max_chars // 2
        head = chunk[:half]
        tail = chunk[-half:]
        skip_chars = len(chunk) - max_chars
        chunk = (
            head
            + f"\n\n[... output truncated: 共 {len(chunk)} 字符, 截断 {skip_chars} 字符 ...]\n\n"
            + tail
        )
        truncated = True

    content = f"# {p}\n# {range_info}\n\n{chunk}"
    return _ok(
        content,
        data={
            "path": str(p),
            "total_lines": total_lines,
            "truncated": truncated,
            "max_chars": max_chars,
        },
    )


def write_file(path: str, content: str, append: bool = False) -> dict:
    """
    写文件(atomic write)。

    Args:
        path: 文件绝对路径
        content: 要写入的文本
        append: True=追加,False=覆盖

    Returns:
        标准工具返回 dict。
    """
    p = Path(path)
    ok, reason = _is_basic_path_safe(p)
    if not ok:
        return _err(f"路径安全拒绝: {reason}")

    try:
        if append:
            # 追加模式:读已有内容,拼接,再 atomic 写
            # 注意:如果并发写同一文件仍有竞态,这里靠 OS 原子 rename 兜底
            existing = ""
            if p.exists():
                if not p.is_file():
                    return _err(f"路径存在但不是文件(可能是目录): {path}")
                try:
                    existing = p.read_text(encoding="utf-8-sig", errors="replace")
                except OSError as e:
                    return _err(f"读已有内容失败: {e}")
            new_content = existing + content
            atomic_write_text(p, new_content)
            return _ok(
                f"追加写入成功: {path} (新文件大小 {len(new_content)} 字符)",
                data={"path": str(p), "bytes_written": len(content), "total_size": len(new_content), "mode": "append"},
            )
        else:
            # 覆盖模式:atomic write
            atomic_write_text(p, content)
            return _ok(
                f"写入成功: {path} ({len(content)} 字符)",
                data={"path": str(p), "bytes_written": len(content), "mode": "overwrite"},
            )
    except PermissionError as e:
        return _err(f"权限拒绝: {e}")
    except OSError as e:
        return _err(f"写文件失败: {e}")


def edit_file(
    path: str,
    old_string: str,
    new_string: str,
    replace_all: bool = False,
) -> dict:
    """
    受控编辑:把 old_string 替换为 new_string。

    安全策略(对照 standard/tool_channel §3.4 校验):
      - old_string 为空 → 拒绝(避免误删全文)
      - old_string 不存在 → 报错
      - 出现 >1 次且未指定 replace_all → 拒绝,要求 LLM 提供更精确的 old_string

    Args:
        path: 文件绝对路径
        old_string: 原文
        new_string: 替换后
        replace_all: 是否替换全部

    Returns:
        标准工具返回 dict。
    """
    p = Path(path)
    ok, reason = _is_basic_path_safe(p)
    if not ok:
        return _err(f"路径安全拒绝: {reason}")

    if not old_string:
        return _err("old_string 不能为空(防止误删全文,请用 write_file 覆盖)")

    if not p.exists():
        return _err(f"文件不存在: {path}")
    if not p.is_file():
        return _err(f"路径不是文件: {path}")

    try:
        original = p.read_text(encoding="utf-8-sig", errors="replace")
    except OSError as e:
        return _err(f"读取失败: {e}")

    count = original.count(old_string)
    if count == 0:
        return _err(
            f"old_string 在文件中未找到。请检查内容(包含缩进、换行、空格是否完全匹配)。\n"
            f"old_string 前 200 字符: {old_string[:200]!r}"
        )
    if count > 1 and not replace_all:
        return _err(
            f"old_string 在文件中出现 {count} 次,但 replace_all=false。"
            f"请提供更精确的 old_string,或显式设置 replace_all=true。"
        )

    if replace_all:
        new_text = original.replace(old_string, new_string)
        replacements = count
    else:
        new_text = original.replace(old_string, new_string, 1)
        replacements = 1

    try:
        atomic_write_text(p, new_text)
    except OSError as e:
        return _err(f"写文件失败: {e}")

    return _ok(
        f"编辑成功: {path} (替换 {replacements} 处)",
        data={
            "path": str(p),
            "replacements": replacements,
            "old_length": len(old_string),
            "new_length": len(new_string),
            "replace_all": replace_all,
        },
    )


def list_dir(
    path: str,
    pattern: str = "",
    recursive: bool = False,
    max_entries: int = 500,
) -> dict:
    """
    列目录内容。

    Args:
        path: 目录绝对路径
        pattern: glob 模式(如 '*.py'),空 = 全部
        recursive: 是否递归
        max_entries: 最大返回条目数

    Returns:
        标准工具返回 dict。
    """
    p = Path(path)
    ok, reason = _is_basic_path_safe(p)
    if not ok:
        return _err(f"路径安全拒绝: {reason}")

    if not p.exists():
        return _err(f"目录不存在: {path}")
    if not p.is_dir():
        return _err(f"路径不是目录: {path}")

    try:
        if recursive:
            if pattern:
                iterator = p.rglob(pattern)
            else:
                iterator = p.rglob("*")
        else:
            if pattern:
                iterator = p.glob(pattern)
            else:
                iterator = p.iterdir()
    except OSError as e:
        return _err(f"列目录失败: {e}")

    entries = []
    truncated = False
    for item in iterator:
        if len(entries) >= max_entries:
            truncated = True
            break
        try:
            stat_result = item.stat()
            entry_type = "dir" if item.is_dir() else "file"
            # 在 Windows 上,符号链接 stat().st_mode 不一定带 S_ISLNK,简化处理
            if item.is_symlink():
                entry_type = "symlink"
            entries.append({
                "name": item.name,
                "type": entry_type,
                "size": stat_result.st_size if entry_type == "file" else None,
                "mtime": stat_result.st_mtime,
                "rel_path": str(item.relative_to(p)) if item.is_relative_to(p) else item.name,
            })
        except OSError:
            # 跳过无法 stat 的条目(权限不足等)
            continue

    # 按"目录优先 + 名称升序"排序(符合 LLM 习惯)
    entries.sort(key=lambda e: (0 if e["type"] == "dir" else 1, e["name"].lower()))

    # 渲染为人类可读文本
    lines = [f"# {p}", f"# 共 {len(entries)} 项" + (" (已截断)" if truncated else "")]
    lines.append("")
    for e in entries:
        type_mark = {"dir": "[D]", "file": "[F]", "symlink": "[L]"}.get(e["type"], "[?]")
        size_str = f"  {e['size']:>10}" if e["size"] is not None else "          -"
        lines.append(f"{type_mark} {size_str}  {e['rel_path']}")

    return _ok(
        "\n".join(lines),
        data={
            "path": str(p),
            "entries": entries,
            "count": len(entries),
            "truncated": truncated,
            "pattern": pattern,
            "recursive": recursive,
        },
    )


def delete_file(path: str, recursive: bool = False) -> dict:
    """
    删除文件或目录。

    安全策略:
      - 路径安全检查(同 _is_basic_path_safe)
      - 默认拒绝删除非空目录(防止 rm -rf 误操作)
      - recursive=true 时允许递归删除非空目录

    Args:
        path: 文件或目录绝对路径
        recursive: 是否递归删除

    Returns:
        标准工具返回 dict。
    """
    p = Path(path)
    ok, reason = _is_basic_path_safe(p)
    if not ok:
        return _err(f"路径安全拒绝: {reason}")

    if not p.exists():
        return _err(f"路径不存在: {path}")

    try:
        if p.is_file() or p.is_symlink():
            p.unlink()
            return _ok(
                f"文件已删除: {path}",
                data={"path": str(p), "type": "file"},
            )
        elif p.is_dir():
            # 试图列一下,看是否非空
            try:
                contents = list(p.iterdir())
            except OSError as e:
                return _err(f"列目录失败: {e}")
            if contents and not recursive:
                return _err(
                    f"目录非空,拒绝删除(需要 recursive=true): {path} "
                    f"(共 {len(contents)} 个条目)"
                )
            if recursive:
                import shutil
                shutil.rmtree(p)
                return _ok(
                    f"目录已递归删除: {path}",
                    data={"path": str(p), "type": "dir", "recursive": True},
                )
            else:
                p.rmdir()
                return _ok(
                    f"空目录已删除: {path}",
                    data={"path": str(p), "type": "dir", "recursive": False},
                )
        else:
            return _err(f"路径既不是文件也不是目录: {path}")
    except PermissionError as e:
        return _err(f"权限拒绝: {e}")
    except OSError as e:
        return _err(f"删除失败: {e}")


def copy_file(
    src: str,
    dst: str,
    overwrite: bool = False,
) -> dict:
    """
    复制文件或目录。

    行为:
      - src 是文件 → 用 shutil.copy2(保留 mtime / atime)
      - src 是目录 → 用 shutil.copytree(递归整个子树,非空目录会失败)
      - src 是符号链接 → 跟随链接复制目标(shutil.copy2 默认行为)
      - 默认 overwrite=False(目标存在 → 报错);True 时先删目标再复制(目录用 rmtree)

    Args:
        src: 源绝对路径
        dst: 目标绝对路径
        overwrite: 目标已存在时是否覆盖

    Returns:
        标准工具返回 dict。
    """
    src_path = Path(src)
    dst_path = Path(dst)

    # src + dst 都要做基础安全检查(防止从 system 关键区读 / 写到 system 关键区)
    ok, reason = _is_basic_path_safe(src_path)
    if not ok:
        return _err(f"src 路径安全拒绝: {reason}")
    ok, reason = _is_basic_path_safe(dst_path)
    if not ok:
        return _err(f"dst 路径安全拒绝: {reason}")

    if not src_path.exists():
        return _err(f"src 不存在: {src}")

    # overwrite 检查
    # 注意:dst 是已存在的"目录"不算冲突(把文件/目录复制进目录是正常用法)
    # 只有 dst 是已存在的"文件"才走 overwrite 校验
    if dst_path.exists() and dst_path.is_file() and not overwrite:
        return _err(
            f"目标已存在(文件),拒绝覆盖 (dst={dst})。"
            f"如需覆盖请显式传 overwrite=true。"
        )

    # 防止把目录复制到自己的子目录(无限递归)
    try:
        if src_path.is_dir():
            try:
                src_resolved = src_path.resolve()
                dst_resolved = dst_path.resolve() if dst_path.exists() else dst_path.absolute()
            except OSError:
                src_resolved = src_path.absolute()
                dst_resolved = dst_path.absolute()
            if str(dst_resolved).startswith(str(src_resolved) + os.sep) or dst_resolved == src_resolved:
                return _err(f"不能把目录复制到自身或其子目录中: src={src}, dst={dst}")
    except OSError:
        pass

    try:
        if src_path.is_dir():
            # 目录复制
            import shutil
            # copytree 不允许 dst 已存在(除非 dirs_exist_ok=True,Python 3.8+)
            if dst_path.exists() and overwrite:
                if not dst_path.is_dir():
                    return _err(f"dst 已存在但不是目录,无法作为 copytree 目标: {dst}")
                shutil.rmtree(dst_path)
            if dst_path.exists():
                return _err(f"目标目录已存在: {dst}")
            shutil.copytree(src_path, dst_path)
            return _ok(
                f"目录已复制: {src} -> {dst}",
                data={
                    "src": str(src_path),
                    "dst": str(dst_path),
                    "type": "dir",
                    "overwrite": overwrite,
                },
            )
        elif src_path.is_file() or src_path.is_symlink():
            import shutil
            # copy2 保留元数据
            if dst_path.is_dir():
                # dst 是已存在目录 → 把文件复制进该目录
                final_dst = dst_path / src_path.name
                if final_dst.exists() and not overwrite:
                    return _err(
                        f"目标目录中已存在同名文件: {final_dst}。"
                        f"如需覆盖请显式传 overwrite=true。"
                    )
                shutil.copy2(src_path, final_dst)
                return _ok(
                    f"文件已复制到目录: {src} -> {final_dst}",
                    data={
                        "src": str(src_path),
                        "dst": str(final_dst),
                        "type": "file",
                        "overwrite": overwrite,
                        "copy_into_dir": True,
                    },
                )
            else:
                # dst 不是目录 → 直接作为目标路径
                dst_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_path, dst_path)
                return _ok(
                    f"文件已复制: {src} -> {dst}",
                    data={
                        "src": str(src_path),
                        "dst": str(dst_path),
                        "type": "file",
                        "overwrite": overwrite,
                        "copy_into_dir": False,
                    },
                )
        else:
            return _err(f"src 既不是文件也不是目录(可能是 socket / FIFO 等): {src}")
    except PermissionError as e:
        return _err(f"权限拒绝: {e}")
    except FileNotFoundError as e:
        return _err(f"文件不存在(src 复制过程中消失?): {e}")
    except shutil.SameFileError:
        return _err(f"src 和 dst 指向同一个文件: {src}")
    except OSError as e:
        return _err(f"复制失败: {e}")


def move_file(
    src: str,
    dst: str,
    overwrite: bool = False,
) -> dict:
    """
    移动或重命名文件 / 目录。

    行为:
      - shutil.move:同盘走 rename(原子),跨盘走 copy+delete
      - overwrite=False(默认):dst 已存在报错
      - overwrite=True:dst 是文件 → 删后再移;dst 是目录 → 删空目录后再移;跨设备时 sh_util.copy2 不会覆盖

    Args:
        src: 源绝对路径
        dst: 目标绝对路径
        overwrite: 目标已存在时是否覆盖

    Returns:
        标准工具返回 dict。
    """
    import shutil

    src_path = Path(src)
    dst_path = Path(dst)

    # 安全检查
    ok, reason = _is_basic_path_safe(src_path)
    if not ok:
        return _err(f"src 路径安全拒绝: {reason}")
    ok, reason = _is_basic_path_safe(dst_path)
    if not ok:
        return _err(f"dst 路径安全拒绝: {reason}")

    if not src_path.exists():
        return _err(f"src 不存在: {src}")

    # overwrite 检查
    # 同 copy_file:dst 是已存在的"目录"不算冲突(把 src 移进目录是正常用法)
    if dst_path.exists() and dst_path.is_file() and not overwrite:
        return _err(
            f"目标已存在(文件),拒绝覆盖 (dst={dst})。"
            f"如需覆盖请显式传 overwrite=true。"
        )

    # 检查 src 和 dst 关系
    try:
        if src_path.is_dir() and dst_path.exists():
            # 移动目录到目标目录里(目标目录已存在)
            if dst_path.is_dir():
                final_dst = dst_path / src_path.name
                if final_dst.exists() and not overwrite:
                    return _err(
                        f"目标目录中已存在同名项: {final_dst}。"
                        f"如需覆盖请显式传 overwrite=true。"
                    )
                dst_path = final_dst
        if src_path.is_dir() and dst_path.exists() and overwrite:
            # 强制覆盖目录
            if dst_path.is_dir():
                shutil.rmtree(dst_path)
            else:
                dst_path.unlink()
    except OSError as e:
        return _err(f"覆盖前清理失败: {e}")

    try:
        if src_path.is_file() and dst_path.is_dir():
            # 移动文件到目标目录里
            final_dst = dst_path / src_path.name
            if final_dst.exists() and not overwrite:
                return _err(
                    f"目标目录中已存在同名文件: {final_dst}。"
                    f"如需覆盖请显式传 overwrite=true。"
                )
            shutil.move(str(src_path), str(final_dst))
            return _ok(
                f"文件已移动到目录: {src} -> {final_dst}",
                data={
                    "src": str(src_path),
                    "dst": str(final_dst),
                    "type": "file",
                    "overwrite": overwrite,
                    "moved_into_dir": True,
                },
            )
        else:
            dst_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src_path), str(dst_path))
            return _ok(
                f"已移动: {src} -> {dst}",
                data={
                    "src": str(src_path),
                    "dst": str(dst_path),
                    "type": "dir" if src_path.is_dir() else "file",
                    "overwrite": overwrite,
                    "moved_into_dir": False,
                },
            )
    except PermissionError as e:
        return _err(f"权限拒绝: {e}")
    except FileNotFoundError as e:
        return _err(f"src 在移动过程中消失: {e}")
    except OSError as e:
        return _err(f"移动失败: {e}")


def get_properties(path: str, follow_symlinks: bool = False) -> dict:
    """
    查询文件 / 目录属性(不读内容)。

    Args:
        path: 绝对路径
        follow_symlinks: True → stat(跟随链接查目标);False(默认) → lstat(报告链接本身)

    Returns:
        标准工具返回 dict。data 字段含完整属性字典。
    """
    p = Path(path)
    ok, reason = _is_basic_path_safe(p)
    if not ok:
        return _err(f"路径安全拒绝: {reason}")

    if not p.exists() and not p.is_symlink():
        return _err(f"路径不存在: {path}")

    # lstat / stat 选择
    try:
        if follow_symlinks:
            stat_result = p.stat()
            stat_method = "stat"
        else:
            stat_result = p.lstat()
            stat_method = "lstat"
    except OSError as e:
        return _err(f"stat 失败: {e}")

    # type 判断
    is_symlink = p.is_symlink()
    is_dir = p.is_dir() if follow_symlinks or not is_symlink else False
    is_file = p.is_file() if follow_symlinks or not is_symlink else False
    if is_symlink and not follow_symlinks:
        # lstat 后 is_file / is_dir 会因符号链接"没有 dir/file" 返回 False,要单独判
        type_str = "symlink"
    elif is_dir:
        type_str = "dir"
    elif is_file:
        type_str = "file"
    else:
        type_str = "other"  # socket / fifo / block device 等

    # mode 解析(从 0o644 → "0o644 (rw-r--r--)" 形式)
    mode_int = stat_result.st_mode
    mode_octal = oct(mode_int & 0o7777)  # 只保留 permission + setuid/setgid/sticky bit
    mode_str = stat.filemode(mode_int)

    # 人类可读 size
    size_bytes = stat_result.st_size
    size_human = _humanize_size(size_bytes)

    # 时间戳(ISO 格式)
    from datetime import datetime, timezone
    def _to_iso(ts: float) -> str:
        try:
            return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
        except (OSError, ValueError, OverflowError):
            return f"<invalid timestamp: {ts}>"

    mtime_iso = _to_iso(stat_result.st_mtime)
    atime_iso = _to_iso(stat_result.st_atime)
    ctime_iso = _to_iso(stat_result.st_ctime)

    # 符号链接目标(若有)
    symlink_target = None
    if is_symlink:
        try:
            symlink_target = str(p.readlink())
        except OSError as e:
            symlink_target = f"<readlink failed: {e}>"

    # owner(Windows 上 uid/gid 无意义,标 N/A)
    owner_str = None
    try:
        if hasattr(stat_result, "st_uid"):
            import getpass
            try:
                owner_str = getpass.getuser()
            except Exception:
                owner_str = f"uid={stat_result.st_uid}"
    except Exception:
        pass

    # 渲染
    lines = [
        f"# {p}",
        f"# type: {type_str}    stat_method: {stat_method}",
        f"# size: {size_bytes} bytes ({size_human})",
        f"# mode: {mode_octal} ({mode_str})",
        f"# mtime: {mtime_iso}  (修改时间)",
        f"# atime: {atime_iso}  (访问时间)",
        f"# ctime: {ctime_iso}  (元数据修改时间 / Windows 创建时间)",
        f"# nlink: {stat_result.st_nlink}  inode: {stat_result.st_ino}",
    ]
    if owner_str:
        lines.append(f"# owner: {owner_str}")
    if symlink_target is not None:
        lines.append(f"# symlink target: {symlink_target}")
    if is_dir and not is_symlink:
        try:
            child_count = sum(1 for _ in p.iterdir())
            lines.append(f"# dir children: {child_count}")
        except (OSError, PermissionError):
            lines.append("# dir children: <无法枚举>")

    return _ok(
        "\n".join(lines),
        data={
            "path": str(p),
            "type": type_str,
            "is_symlink": is_symlink,
            "is_dir": type_str == "dir",
            "is_file": type_str == "file",
            "size_bytes": size_bytes,
            "size_human": size_human,
            "mode_octal": mode_octal,
            "mode_str": mode_str,
            "mtime": stat_result.st_mtime,
            "atime": stat_result.st_atime,
            "ctime": stat_result.st_ctime,
            "mtime_iso": mtime_iso,
            "atime_iso": atime_iso,
            "ctime_iso": ctime_iso,
            "nlink": stat_result.st_nlink,
            "inode": stat_result.st_ino,
            "owner": owner_str,
            "symlink_target": symlink_target,
            "stat_method": stat_method,
        },
    )


def _humanize_size(size_bytes: int) -> str:
    """字节数 → 人类可读(B / KB / MB / GB / TB)。"""
    if size_bytes < 0:
        return f"{size_bytes} B"
    units = ("B", "KB", "MB", "GB", "TB", "PB")
    size = float(size_bytes)
    for unit in units:
        if size < 1024.0:
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} {unit}"
        size /= 1024.0
    return f"{size:.1f} EB"


# ============================================================================
# 工具 dispatch 表
# ============================================================================
TOOL_HANDLERS = {
    "read_file": read_file,
    "write_file": write_file,
    "edit_file": edit_file,
    "list_dir": list_dir,
    "delete_file": delete_file,
    "copy_file": copy_file,
    "move_file": move_file,
    "get_properties": get_properties,
}


# ============================================================================
# CLI
# ============================================================================
def _print_schemas() -> None:
    """打印本模块所有工具的 schema(JSON 格式)。"""
    import json
    print(json.dumps(TOOL_SCHEMAS, ensure_ascii=False, indent=2))


def _print_result(result: dict) -> int:
    """统一打印 handler 返回结果。返回进程退出码。"""
    if result["success"]:
        print(result["content"])
        if result.get("data"):
            import json
            # data 仅在 --verbose 时打印
            pass
        return 0
    else:
        print(result["content"], file=sys.stderr)
        return 1


def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="file_system.py",
        description=(
            "Onion Agent 内置工具 - 文件系统 (8 个原子工具)\n"
            "每个 subcommand 都是一个原子化工具,所见即所得。"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--list-tools",
        action="store_true",
        help="列出本模块所有工具 schema (OpenAI Chat Completions 格式)",
    )
    sub = p.add_subparsers(dest="cmd", metavar="<command>")

    # read
    read_p = sub.add_parser("read", help="读文件(支持行范围)")
    read_p.add_argument("--path", required=True, help="文件绝对路径")
    read_p.add_argument("--start-line", type=int, default=None, help="起始行(1-indexed)")
    read_p.add_argument("--end-line", type=int, default=None, help="结束行(1-indexed)")
    read_p.add_argument("--max-chars", type=int, default=50000, help="最大返回字符数(默认 50000)")

    # write
    write_p = sub.add_parser("write", help="写文件(atomic write)")
    write_p.add_argument("--path", required=True, help="文件绝对路径")
    write_p.add_argument("--content", required=True, help="写入内容")
    write_p.add_argument("--append", action="store_true", help="追加模式(默认覆盖)")

    # edit
    edit_p = sub.add_parser("edit", help="受控编辑(old_string → new_string)")
    edit_p.add_argument("--path", required=True, help="文件绝对路径")
    edit_p.add_argument("--old-string", required=True, help="原文")
    edit_p.add_argument("--new-string", required=True, help="替换后")
    edit_p.add_argument("--replace-all", action="store_true", help="替换全部出现的位置")

    # list
    list_p = sub.add_parser("list", help="列目录")
    list_p.add_argument("--path", required=True, help="目录绝对路径")
    list_p.add_argument("--pattern", default="", help="glob 模式(默认全部)")
    list_p.add_argument("--recursive", action="store_true", help="递归列子目录")
    list_p.add_argument("--max-entries", type=int, default=500, help="最大返回条目(默认 500)")

    # delete
    del_p = sub.add_parser("delete", help="删除文件/目录")
    del_p.add_argument("--path", required=True, help="文件或目录绝对路径")
    del_p.add_argument("--recursive", action="store_true", help="递归删除(用于非空目录)")

    # copy
    copy_p = sub.add_parser("copy", help="复制文件/目录")
    copy_p.add_argument("--src", required=True, help="源文件/目录绝对路径")
    copy_p.add_argument("--dst", required=True, help="目标绝对路径(目录则复制进去)")
    copy_p.add_argument("--overwrite", action="store_true", help="目标已存在时覆盖")

    # move
    move_p = sub.add_parser("move", help="移动/重命名文件/目录")
    move_p.add_argument("--src", required=True, help="源文件/目录绝对路径")
    move_p.add_argument("--dst", required=True, help="目标绝对路径(目录则移进去)")
    move_p.add_argument("--overwrite", action="store_true", help="目标已存在时覆盖")

    # properties
    prop_p = sub.add_parser("properties", help="查询文件/目录属性")
    prop_p.add_argument("--path", required=True, help="文件/目录绝对路径")
    prop_p.add_argument(
        "--follow-symlinks",
        action="store_true",
        help="跟随符号链接查目标属性(默认 lstat 报告链接本身)",
    )

    return p


def main(argv: Optional[list] = None) -> int:
    parser = _build_argparser()
    args = parser.parse_args(argv)

    if args.list_tools:
        _print_schemas()
        return 0

    if not args.cmd:
        parser.print_help()
        return 0

    # dispatch
    if args.cmd == "read":
        result = read_file(
            path=args.path,
            start_line=args.start_line,
            end_line=args.end_line,
            max_chars=args.max_chars,
        )
    elif args.cmd == "write":
        result = write_file(path=args.path, content=args.content, append=args.append)
    elif args.cmd == "edit":
        result = edit_file(
            path=args.path,
            old_string=args.old_string,
            new_string=args.new_string,
            replace_all=args.replace_all,
        )
    elif args.cmd == "list":
        result = list_dir(
            path=args.path,
            pattern=args.pattern,
            recursive=args.recursive,
            max_entries=args.max_entries,
        )
    elif args.cmd == "delete":
        result = delete_file(path=args.path, recursive=args.recursive)
    elif args.cmd == "copy":
        result = copy_file(src=args.src, dst=args.dst, overwrite=args.overwrite)
    elif args.cmd == "move":
        result = move_file(src=args.src, dst=args.dst, overwrite=args.overwrite)
    elif args.cmd == "properties":
        result = get_properties(path=args.path, follow_symlinks=args.follow_symlinks)
    else:
        parser.print_help()
        return 2

    return _print_result(result)


if __name__ == "__main__":
    sys.exit(main())
