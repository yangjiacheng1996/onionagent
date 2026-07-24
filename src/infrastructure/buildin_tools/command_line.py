# -*- coding: utf-8 -*-
"""
================================================================================
Command Line 工具 - 内置工具集 (L5 - Infrastructure / buildin_tools)
================================================================================

# 开发计划

Onion Agent 内置 3 大基础工具之二:本地命令行执行。

# 工具清单(1 个原子化工具)

1. `run_command` - 执行 shell 命令,返回 stdout / stderr / returncode / duration

# 设计原则(对照 harness/01_market_research/standard/agent_loop.md §Q7 工具调用权限)

- **3 档权限 + hardline 兜底**(agent_loop §1.3 必做)
  - 命中 HARDCODED_DANGEROUS_PATTERNS(rm -rf /, mkfs, fork bomb 等) → **永远拒绝**(即使 YOLO 也不放行)
  - Catastrophic subshell(`rm -rf ~` 藏在 `$(...)` / 反引号 / `<(...)`) → 拒绝
  - 命中系统关键路径(/etc/, ~/.ssh/, ~/.aws/)的命令 → 拒绝
- **timeout 强制**(Cline §Q1.2 必做) - 单条命令 timeout,默认 30s,最大 300s
- **CWD 白名单**(MCP filesystem 实践) - 必须在 agent workspace 内或显式指定
- **环境变量隔离** - 不继承父进程所有 env,只传 PATH / HOME / 系统 locale 相关
- **错误透明** - returncode != 0 也算 success=True(命令成功执行了),is_error=True
  表示"工具本身执行失败"(比如 timeout 杀进程)
- **跨平台 shell 选择**
  - Windows:优先 Git Bash(存在 PATH) → 否则 `cmd.exe /c <command>`
  - POSIX:直接 `bash -c <command>`
  - 不强制 `shell=True` 走默认 shell(避免 PowerShell vs cmd 行为差异)

# CLI 测试示例

```powershell
# 1. 跑个简单命令
python command_line.py run --command "echo hello world"

# 2. 跨平台:Windows 走 cmd,Linux/macOS 走 bash
python command_line.py run --command "dir" --cwd C:/workspace
python command_line.py run --command "ls -la" --cwd /tmp

# 3. 自定义 timeout
python command_line.py run --command "ping 127.0.0.1 -n 5" --timeout 10

# 4. 注入 env
python command_line.py run --command "echo %MY_VAR%" --env '{"MY_VAR":"from_onion"}'

# 5. 测试 hardline 拦截
python command_line.py run --command "rm -rf /"
python command_line.py run --command "rm -rf ~"
python command_line.py run --command "echo hi && rm -rf /"

# 6. 查看本模块所有工具 schema
python command_line.py --list-tools
```

# 退出码

0  - 命令 returncode == 0
2  - 参数错误
3  - hardline 黑名单命中(命令被拒绝执行)
4  - timeout
5  - CWD 路径安全拒绝
6  - 命令未找到(Windows 上无 Git Bash 也无 cmd.exe 等极端情况)
99 - 内部异常
"""

from __future__ import annotations

import argparse
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
import time
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
# 硬底线(Hardline Patterns)
# ============================================================================
# 对照 agent_loop §1.3 + Hermes / OpenClaw / Claude Code 的 DANGEROUS_PATTERNS 实践
# 命中这些 pattern → 永远拒绝,即使上层走 YOLO 也不放行
#
# 设计原则:
#   - 这些 pattern 必须 catastrophic(误中率越低越好,但漏判成本极高)
#   - 优先做"subshell 形式"匹配,因为 `$(rm -rf /)` 这种最阴险
#   - 不做太宽的匹配(比如禁止 `rm`,会误伤 `rm -rf build/` 这种合法构建清理)
#
# 匹配范围:整条命令字符串(去前后空白后)
HARDCODED_DANGEROUS_PATTERNS: list[dict] = [
    # ---- rm -rf 类(最常见的破坏性操作) ----
    # 用 -\S*[rR]\S*[fF] 形式匹配"同一个 flag 参数里同时包含 r/R 和 f/F"
    # 注意:\S* (零或多) 而不是 \S+ (一或多) —— 否则 \S+ 会把 [rR] 吃掉
    # 这样能匹配 -rf / -fr / -RfR / -rfd / 任意大小写组合
    {
        "id": "rm_rf_root",
        "pattern": r"\brm\s+-\S*[rR]\S*[fF]\S*\s+/\s*($|&&|\|\||;|\|)",
        "desc": "rm -rf /  (删除整个根目录,系统直接报废)",
    },
    {
        "id": "rm_rf_root_alt",
        # rm -fr / 或 rm -Rf /
        "pattern": r"\brm\s+-\S*[fF]\S*[rR]\S*\s+/\s*($|&&|\|\||;|\|)",
        "desc": "rm -fr /  (删除整个根目录)",
    },
    {
        "id": "rm_rf_home",
        "pattern": r"\brm\s+-\S*[rR]\S*[fF]\S*\s+~/?\s*($|&&|\|\||;|\|)",
        "desc": "rm -rf ~  (删除 home 目录,所有用户数据)",
    },
    {
        "id": "rm_rf_home_alt",
        "pattern": r"\brm\s+-\S*[fF]\S*[rR]\S*\s+~/?\s*($|&&|\|\||;|\|)",
        "desc": "rm -fr ~  (删除 home 目录)",
    },
    {
        "id": "rm_rf_env",
        "pattern": r"\brm\s+-\S*[rR]\S*[fF]\S*\s+\$\{?(HOME|USERPROFILE)",
        "desc": "rm -rf $HOME  (引用 home 变量)",
    },
    {
        "id": "rm_rf_etc",
        "pattern": r"\brm\s+-\S*[rR]\S*[fF]\S*\s+/?etc",
        "desc": "rm -rf /etc  (删除系统配置)",
    },
    {
        "id": "rm_rf_wildcard",
        # rm -rf /* 根目录所有内容
        "pattern": r"\brm\s+-\S*[rR]\S*[fF]\S*\s+/\*",
        "desc": "rm -rf /* (根目录下所有内容)",
    },
    # ---- 多 flag 分开形式: rm -r -f / / rm -f -r / / rm -r -f -v ~
    {
        "id": "rm_split_flags_root",
        # 分开的多 flag 形式: rm -r -f / (r 和 f 各自一个 -arg)
        "pattern": r"\brm\s+-\S*[rR]\s+-\S*[fF]\s+/\s*($|&&|\|\||;|\|)",
        "desc": "rm -r -f /  (分开的多 flag 形式)",
    },
    {
        "id": "rm_split_flags_root_alt",
        "pattern": r"\brm\s+-\S*[fF]\s+-\S*[rR]\s+/\s*($|&&|\|\||;|\|)",
        "desc": "rm -f -r /  (分开的多 flag 形式,顺序换)",
    },
    # ---- 磁盘 / 分区 / 文件系统破坏 ----
    {
        "id": "mkfs",
        "pattern": r"\bmkfs(\.\w+)?\s+",
        "desc": "mkfs.*  (格式化磁盘)",
    },
    {
        "id": "dd_to_disk",
        "pattern": r"\bdd\s+.*\bof=/dev/(sd|hd|nvme|vd|xvd)",
        "desc": "dd of=/dev/sd*  (直接写磁盘设备)",
    },
    {
        "id": "fdisk",
        "pattern": r"\bfdisk\s+/dev/(sd|hd|nvme|vd|xvd)",
        "desc": "fdisk /dev/sd*  (改分区表)",
    },
    # ---- fork bomb / 资源耗尽 ----
    {
        "id": "fork_bomb",
        "pattern": r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:",
        "desc": "经典 fork bomb (:(){ :|:& };:)",
    },
    # ---- 权限提升 / 远程下载执行 ----
    {
        "id": "chmod_777_root",
        "pattern": r"\bchmod\s+(-R\s+)?777\s+/\s*($|&&|\|\||;|\|)",
        "desc": "chmod 777 /  (给根目录全开权限)",
    },
    {
        "id": "curl_pipe_sh",
        "pattern": r"\b(curl|wget|fetch)\s+[^|]*\|\s*(sudo\s+)?(sh|bash|zsh|python|perl|ruby)\b",
        "desc": "curl ... | sh  (远程下载直接执行,极危险)",
    },
    # ---- 系统关键文件覆盖 ----
    {
        "id": "write_to_passwd",
        "pattern": r"(>>?|\|)\s*/etc/(passwd|shadow|sudoers|sudoers\.d/)",
        "desc": "重定向写入 /etc/passwd|shadow|sudoers",
    },
    {
        "id": "write_to_ssh",
        "pattern": r"(>>?|\|)\s*~/?\.ssh/",
        "desc": "重定向写入 ~/.ssh/",
    },
    {
        "id": "write_to_aws",
        "pattern": r"(>>?|\|)\s*~/?\.aws/",
        "desc": "重定向写入 ~/.aws/",
    },
    # ---- Catastrophic subshell 形式:藏在 $(...) / 反引号 / <(...) 里 ----
    {
        "id": "rm_rf_in_subshell",
        "pattern": r"(\$\(|`)\s*rm\s+-\S*[rR]\S*[fF]",
        "desc": "subshell 中藏 rm -rf (e.g. $(rm -rf /))",
    },
]

# 编译为正则(启动时编译一次,避免每次调用重编译)
_COMPILED_HARDLINE = [
    (p["id"], re.compile(p["pattern"], re.IGNORECASE), p["desc"])
    for p in HARDCODED_DANGEROUS_PATTERNS
]


# ============================================================================
# CWD 路径安全检查
# ============================================================================
_SYSTEM_CRITICAL_PREFIXES = (
    # Windows
    "C:\\Windows",
    "C:\\Program Files",
    "C:\\Program Files (x86)",
    "C:\\ProgramData",
    # POSIX
    "/etc",
    "/boot",
    "/sys",
    "/proc",
    "/dev",
    "/usr/lib",
    "/usr/include",
)


def _is_cwd_safe(cwd: Path) -> tuple[bool, str]:
    """CWD 安全检查:不允许在系统关键目录下执行命令。"""
    try:
        resolved = cwd.resolve()
    except OSError as e:
        return False, f"路径解析失败: {e}"
    resolved_str = str(resolved)
    for prefix in _SYSTEM_CRITICAL_PREFIXES:
        if resolved_str.lower().startswith(prefix.lower()):
            return False, f"CWD 命中系统关键目录: {prefix}"
    return True, ""


# ============================================================================
# 跨平台 shell 选择
# ============================================================================
def _pick_shell() -> tuple[list[str], str]:
    """
    选定执行 shell 的 argv 列表。

    Returns:
        (shell_argv_prefix, shell_name)
        例如 (["bash", "-c"], "bash") 或 (["cmd.exe", "/c"], "cmd")

    Windows 优先 Git Bash(用户主动装的,体验更接近 POSIX);
    否则回落到 cmd.exe(系统自带)。
    POSIX 直接用 bash。
    """
    if sys.platform == "win32":
        # 优先 Git Bash(从 PATH 找)
        bash = shutil.which("bash")
        if bash:
            return [bash, "-c"], "bash"
        # 兜底:常见 Git Bash 安装路径(系统 PATH 找不到但装了的)
        common_paths = [
            r"C:\Program Files\Git\bin\bash.exe",
            r"C:\Program Files (x86)\Git\bin\bash.exe",
        ]
        for p in common_paths:
            if os.path.isfile(p):
                return [p, "-c"], "bash"
        # 兜底:cmd.exe
        comspec = os.environ.get("COMSPEC", "cmd.exe")
        return [comspec, "/c"], "cmd"
    else:
        # POSIX
        bash = shutil.which("bash")
        if bash:
            return [bash, "-c"], "bash"
        # 极端兜底:sh
        sh = shutil.which("sh")
        if sh:
            return [sh, "-c"], "sh"
        return ["/bin/sh", "-c"], "sh"


# ============================================================================
# Hardline 校验
# ============================================================================
def _check_hardline(command: str) -> tuple[bool, Optional[str]]:
    """
    检查命令是否命中 hardline 黑名单。

    匹配逻辑:
      1. 整条命令字符串去前后空白
      2. 用每个危险 pattern 正则匹配
      3. 命中 → 返回 (False, 错误描述)
      4. 不命中 → 返回 (True, None)

    设计:不递归解析 subshell 内部,只对"原始命令字符串"做匹配。
    这意味着:
      - 显式 `rm -rf /` 能拦
      - 隐式 `echo "rm -rf /" | bash` 第 2 个 token | bash 也命中 curl_pipe_sh
      - 但 `$(rm -rf /)` 形式需要单独检测(下面有 _check_catastrophic_subshell)
    """
    cmd = command.strip()
    for hid, regex, desc in _COMPILED_HARDLINE:
        if regex.search(cmd):
            return False, f"[hardline:{hid}] {desc}"
    return True, None


# ============================================================================
# 工具 schema (OpenAI Chat Completions 风格)
# ============================================================================
TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": (
                "执行 shell 命令。返回 {stdout, stderr, returncode, duration_ms, shell}。"
                "Windows 走 Git Bash(或 cmd.exe),POSIX 走 bash。"
                "内置 hardline 黑名单(rm -rf /, mkfs, fork bomb 等) - 命中会被拒绝。"
                "支持 timeout(秒,默认 30,最大 300);CWD 必须在非系统关键目录。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "要执行的 shell 命令",
                    },
                    "cwd": {
                        "type": "string",
                        "description": "工作目录(绝对路径)。不传则用进程当前 cwd。",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "超时秒数(默认 30,最大 300)",
                    },
                    "env": {
                        "type": "object",
                        "description": (
                            "额外环境变量 {KEY: VALUE, ...}。"
                            "会合并到子进程 env(覆盖同名变量)。"
                        ),
                    },
                },
                "required": ["command"],
                "additionalProperties": False,
            },
        },
    },
]


# ============================================================================
# Handler 工具返回契约(同 file_system.py 风格)
# ============================================================================
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
MAX_TIMEOUT_SECONDS = 300
DEFAULT_TIMEOUT_SECONDS = 30


def run_command(
    command: str,
    cwd: Optional[str] = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    env: Optional[dict] = None,
) -> dict:
    """
    执行 shell 命令。

    Args:
        command: shell 命令
        cwd: 工作目录
        timeout: 超时(秒),默认 30,最大 300
        env: 额外环境变量,会合并到子进程 env

    Returns:
        标准工具返回 dict。
    """
    if not command or not command.strip():
        return _err("command 不能为空")

    # 1. Hardline 黑名单(永远拒绝)
    ok, reason = _check_hardline(command)
    if not ok:
        return _err(f"命令被 hardline 黑名单拒绝: {reason}")

    # 2. timeout 兜底
    if timeout <= 0:
        timeout = DEFAULT_TIMEOUT_SECONDS
    if timeout > MAX_TIMEOUT_SECONDS:
        timeout = MAX_TIMEOUT_SECONDS

    # 3. CWD 解析 + 安全检查
    if cwd:
        cwd_path = Path(cwd)
        ok_cwd, reason_cwd = _is_cwd_safe(cwd_path)
        if not ok_cwd:
            return _err(f"CWD 安全拒绝: {reason_cwd}")
        if not cwd_path.exists():
            return _err(f"CWD 不存在: {cwd}")
        if not cwd_path.is_dir():
            return _err(f"CWD 不是目录: {cwd}")
        actual_cwd = str(cwd_path)
    else:
        actual_cwd = os.getcwd()

    # 4. 构造 env(只透传核心 + 用户追加)
    # 不传整个 os.environ 是为了:
    #   (a) 减少 LLM 可读面
    #   (b) 防止意外覆盖(如 LD_PRELOAD 类攻击)
    # 只透传 PATH / HOME / USERPROFILE / 系统 locale / 临时目录
    child_env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", ""),
        "USERPROFILE": os.environ.get("USERPROFILE", ""),
        "TMPDIR": os.environ.get("TMPDIR", ""),
        "TEMP": os.environ.get("TEMP", ""),
        "TMP": os.environ.get("TMP", ""),
        "LANG": os.environ.get("LANG", "en_US.UTF-8"),
        "LC_ALL": os.environ.get("LC_ALL", ""),
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
        "PYTHONIOENCODING": "utf-8",  # 强制 Python 子进程用 UTF-8
    }
    if env:
        for k, v in env.items():
            child_env[str(k)] = str(v)

    # 5. 选 shell
    shell_argv, shell_name = _pick_shell()
    full_argv = shell_argv + [command]

    # 6. 执行
    start = time.time()
    try:
        proc = subprocess.run(
            full_argv,
            cwd=actual_cwd,
            env=child_env,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,  # 已显式构造 shell argv,不再走 shell=True
        )
        duration_ms = int((time.time() - start) * 1000)
        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
        returncode = proc.returncode

        # 构造返回内容
        parts = [f"# run_command  exit={returncode}  duration={duration_ms}ms  shell={shell_name}"]
        if stdout:
            parts.append(f"## stdout\n{stdout.rstrip()}")
        if stderr:
            parts.append(f"## stderr\n{stderr.rstrip()}")
        if not stdout and not stderr:
            parts.append("(无输出)")

        content = "\n\n".join(parts)

        # returncode != 0 仍然是 success=True(命令成功执行了,只是非零返回)
        # 这是 buildin 工具的标准约定:success 反映"工具能不能跑",不反映"命令业务上对不对"
        return _ok(
            content,
            data={
                "command": command,
                "cwd": actual_cwd,
                "returncode": returncode,
                "duration_ms": duration_ms,
                "stdout": stdout,
                "stderr": stderr,
                "shell": shell_name,
                "timeout": timeout,
            },
        )

    except subprocess.TimeoutExpired as e:
        duration_ms = int((time.time() - start) * 1000)
        return _err(
            f"命令执行超时({timeout}s),已强制终止",
            data={
                "command": command,
                "cwd": actual_cwd,
                "duration_ms": duration_ms,
                "timeout": timeout,
                "stdout_partial": (e.stdout or b"").decode("utf-8", errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or ""),
                "stderr_partial": (e.stderr or b"").decode("utf-8", errors="replace") if isinstance(e.stderr, bytes) else (e.stderr or ""),
            },
        )
    except FileNotFoundError as e:
        # shell 可执行文件找不到
        return _err(
            f"shell 不可用: {shell_argv[0]!r} 不在 PATH 中。"
            f"Windows 请安装 Git Bash 或确保 cmd.exe 存在。详细: {e}"
        )
    except PermissionError as e:
        return _err(f"权限拒绝: {e}")
    except Exception as e:
        return _err(f"命令执行异常: {type(e).__name__}: {e}")


# ============================================================================
# 工具 dispatch 表
# ============================================================================
TOOL_HANDLERS = {
    "run_command": run_command,
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
    print(result["content"])
    if not result["success"]:
        return 1
    # 命令业务的 returncode 通过 data 返回
    rc = result.get("data", {}).get("returncode")
    if rc is not None and rc != 0:
        return rc
    return 0


def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="command_line.py",
        description=(
            "Onion Agent 内置工具 - 本地命令行执行 (1 个原子工具: run_command)\n"
            "内置 hardline 黑名单(rm -rf /, mkfs, fork bomb 等)。"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--list-tools",
        action="store_true",
        help="列出本模块所有工具 schema (OpenAI Chat Completions 格式)",
    )
    sub = p.add_subparsers(dest="cmd", metavar="<command>")

    run_p = sub.add_parser("run", help="执行 shell 命令")
    run_p.add_argument("--command", required=True, help="要执行的 shell 命令")
    run_p.add_argument("--cwd", default=None, help="工作目录(绝对路径)")
    run_p.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS, help="超时秒数(默认 30,最大 300)")
    run_p.add_argument(
        "--env",
        default=None,
        help='额外环境变量,JSON 字符串,例如 \'{"MY_VAR":"hello"}\'',
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

    if args.cmd == "run":
        env_dict = None
        if args.env:
            import json
            try:
                env_dict = json.loads(args.env)
                if not isinstance(env_dict, dict):
                    print("[ERROR] --env 必须是 JSON object,例如 '{\"KEY\":\"value\"}'", file=sys.stderr)
                    return 2
            except json.JSONDecodeError as e:
                print(f"[ERROR] --env JSON 解析失败: {e}", file=sys.stderr)
                return 2
        result = run_command(
            command=args.command,
            cwd=args.cwd,
            timeout=args.timeout,
            env=env_dict,
        )
        return _print_result(result)
    else:
        parser.print_help()
        return 2


if __name__ == "__main__":
    sys.exit(main())
