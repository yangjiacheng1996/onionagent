# -*- coding: utf-8 -*-
"""
================================================================================
Non-Head Browser 工具 - 内置工具集 (L5 - Infrastructure / buildin_tools)
================================================================================

# 开发计划

Onion Agent 内置工具之三:**完整的浏览器自动化工具集**。
本模块提供 LLM 充分调用 Playwright 操作 Chromium 所需的所有核心能力 —— 0 依赖、免安装、自动化测试友好。

# 设计哲学(对照 product_manager.md + standard/playwright.md)

按产品经理的规划,Onion Agent 的内置工具要 **免安装、高效、稳定**,所以:
- **不依赖**外部 npm/yarn,只用 `playwright` Python SDK
- **内置 Chromium** 路径:`buildin_tools/chromium/chrome-{win,linux,mac}*/` 优先,Playwright 缓存兜底,`browser_install` 联网安装
- **单例 BrowserManager** —— 首次操作启动,后续共享 page,避免反复启停 Chromium(每次 1-3s 浪费)
- **错误透明** —— 所有 handler 入口包 try/except,错误分类(URL 错误 / 元素没找到 / 超时 / JS 异常),不抛 Python traceback
- **超时控制** —— 每个操作独立 timeout(默认 15-30s),可配最大 120s
- **所见即所得** —— 每个工具都暴露 CLI,产品经理跑一下就能验证

# 工具集(共 28 个工具)

  ┌────────────────────────────────────────────────────────────────────────┐
  │  HTTP 路线(零浏览器依赖,毫秒级)                                       │
  │    1. web_search         - 多搜索引擎并行(自动判断墙内/墙外)            │
  │    2. web_search_diag    - 诊断当前系统区域 + 生效引擎                  │
  │    3. fetch_url          - HTTP 抓单 URL(Readability + Markdown)       │
  │    4. fetch_urls         - HTTP 并行抓多 URL(并发 5)                    │
  ├────────────────────────────────────────────────────────────────────────┤
  │  Playwright 路线(JS 渲染,需 Chromium)                                  │
  │  ── 导航类 ──                                                            │
  │    5. browser_navigate        - 导航(等渲染 + wait_for_selector)       │
  │    6. browser_navigate_back   - 后退                                    │
  │    7. browser_navigate_forward - 前进                                   │
  │    8. browser_navigate_reload - 刷新                                    │
  │    9. browser_close           - 关闭浏览器,释放资源                    │
  │  ── 安装/配置 ──                                                        │
  │   10. browser_install         - 联网下载 Chromium                       │
  │  ── 交互类 ──                                                            │
  │   11. browser_click           - 点击元素                                │
  │   12. browser_dblclick        - 双击                                    │
  │   13. browser_hover           - 悬停                                    │
  │   14. browser_fill            - 设置 input/textarea 值                   │
  │   15. browser_type            - 逐字输入(触发键盘事件)                 │
  │   16. browser_press           - 按键(Enter/Tab/Escape/方向键)          │
  │   17. browser_select          - select 下拉选择                        │
  │   18. browser_checkbox        - checkbox/radio 勾选/取消              │
  │   19. browser_drag            - 拖拽(从源 selector 到目标 selector)    │
  │   20. browser_upload          - 文件上传(input[type=file])              │
  │  ── 提取类 ──                                                            │
  │   21. browser_query_dom       - CSS selector 提取(text/html/attr/count)│
  │   22. browser_evaluate        - 执行任意 JS                             │
  │   23. browser_console_logs    - 获取浏览器 console 日志                 │
  │  ── 资源类 ──                                                            │
  │   24. browser_screenshot      - 截图(base64)                            │
  │   25. browser_pdf_save        - 页面另存为 PDF                          │
  │   26. browser_cookies         - Cookie 管理(get/set/clear)              │
  │  ── 等待类 ──                                                            │
  │   27. browser_wait_for_text   - 等某段文字出现                          │
  │   28. browser_wait_for_url    - 等 URL 变化(支持 glob 模式)            │
  └────────────────────────────────────────────────────────────────────────┘

# 区域自动判断(中国本土特色)

`web_search` 工具自动判断当前系统处于中国大陆还是自由网络,选不同引擎组合:
  中国大陆:并行调用 百度 + 搜狗 + 360 搜索
  自由网络:并行调用 Google + Bing + Yahoo
判定维度(全部本地启发式,无网络):时区/语言/TZ 环境变量/Win32 GeoID。
开发者可传 `region="cn"/"global"/"auto"` 强制覆盖。

# 内置 Chromium 路径(信创场景)

查找顺序(优先级高 → 低):
  1. 参数 `executable_path` / 环境变量 `ONION_CHROMIUM_PATH`
  2. 内置 `<buildin_tools>/chromium/chrome-{win,linux,mac}*/chrome`
  3. Playwright 默认缓存
`browser_install` 工具(联网下载)作为兜底。

# 行业标准对照(harness/01_market_research/standard/playwright.md)

- 抓取层与提取层分离 (§1.4)
- 协议中立(OpenAI Chat Completions 风格) (§1.5)
- 错误透明(不抛 traceback) (§1.6)
- SSRF 防护 3 道关(协议 + 主机名 + DNS IP) (§3.3)
- 头+尾截断(保留前 50% + 后 50%) (§5.2)
- 响应体字节上限 10MB (§5.3)
- 反爬虫指纹(隐藏 webdriver + 屏蔽 media) (§4.6 / §4.7)
- 懒加载 BrowserManager(首次操作才启 Chromium) (§11.1)
- 浏览器自愈回路(没装时引导调 browser_install) (§6.4)
- executable_path / channel 支持(信创场景) (§2.4)

# 可选依赖(优雅降级)

核心: requests
可选:
  - playwright       → 浏览器路线不可用,但 fetch_* / web_search 仍可用
  - readability-lxml → 降级到内置 _html_to_text
  - markdownify      → 降级到内置 _html_to_markdown_simple

# CLI 测试示例

```powershell
# 0. 查看所有 28 个工具 schema
python non_head_browser.py --list-tools

# 0.1 区域诊断
python non_head_browser.py search-diag
python non_head_browser.py search-diag --region global
python non_head_browser.py search-diag --reset  # VPN 切换后,重置降级状态重新判断

# 1. HTTP 路线
python non_head_browser.py search --query "Onion Agent"
python non_head_browser.py search --query "小龙虾 智能体" --region cn
python non_head_browser.py fetch --url "https://example.com" --max-chars 5000
python non_head_browser.py fetch-urls --urls "https://a.com,https://b.com"

# 2. 浏览器路线 - 导航
python non_head_browser.py browser-navigate --url "https://example.com"
python non_head_browser.py browser-navigate --url "https://weatherol.cn/..." \\
    --wait-until networkidle --wait-for-selector ".citySkWeather"
python non_head_browser.py browser-back
python non_head_browser.py browser-forward
python non_head_browser.py browser-reload

# 3. 浏览器路线 - 交互
python non_head_browser.py browser-click --selector "button.submit"
python non_head_browser.py browser-fill --selector "input[name=q]" --value "Onion Agent"
python non_head_browser.py browser-type --selector "input[name=q]" --text "Hello World"
python non_head_browser.py browser-press --key "Enter"
python non_head_browser.py browser-select --selector "select.city" --value "上海"
python non_head_browser.py browser-checkbox --selector "input[type=checkbox]" --checked true
python non_head_browser.py browser-drag --source "#src" --target "#dst"

# 4. 浏览器路线 - 提取
python non_head_browser.py browser-query-dom --selector "#wendu" --extract text
python non_head_browser.py browser-evaluate --expression "document.title"
python non_head_browser.py browser-console-logs

# 5. 浏览器路线 - 资源
python non_head_browser.py browser-screenshot --url "https://example.com" --type jpeg
python non_head_browser.py browser-pdf-save --url "https://example.com" --path C:/tmp/page.pdf
python non_head_browser.py browser-cookies --action get
python non_head_browser.py browser-cookies --action set --cookies '[{"name":"token","value":"abc","domain":".example.com"}]'

# 6. 浏览器路线 - 等待
python non_head_browser.py browser-wait-for-text --text "登录成功" --timeout 30
python non_head_browser.py browser-wait-for-url --pattern "**/dashboard"

# 7. 安装 + 关闭
python non_head_browser.py browser-install
python non_head_browser.py browser-close
```

# 退出码

0  - 成功
2  - 参数错误
3  - URL/路径安全拒绝(SSRF / 黑名单)
4  - 网络/HTTP 错误(URL 不可达 / DNS 失败 / 4xx/5xx)
5  - 超时
6  - 浏览器未安装
7  - 元素未找到(selector 无匹配)
8  - JS 执行异常
99 - 内部异常
"""

from __future__ import annotations

import argparse
import base64
import concurrent.futures
import html
import json
import locale
import os
import re
import socket
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path
from typing import Any, Optional

# Windows 终端 cp936 默认编码下中文会乱码,统一在脚本入口把 stdout/stderr 切到 UTF-8
if sys.platform == "win32":
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except Exception:
            pass
    del _stream

import requests
from requests.exceptions import RequestException, Timeout, ConnectionError, HTTPError

# ----------------------------------------------------------------------------
# 可选依赖 - 优雅降级
# ----------------------------------------------------------------------------
try:
    from playwright.sync_api import (
        sync_playwright,
        TimeoutError as PlaywrightTimeoutError,
        Error as PlaywrightError,
    )
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    PlaywrightTimeoutError = Exception  # type: ignore[assignment,misc]
    PlaywrightError = Exception  # type: ignore[assignment,misc]

try:
    from readability import Document as ReadabilityDocument
    READABILITY_AVAILABLE = True
except ImportError:
    READABILITY_AVAILABLE = False

try:
    from markdownify import markdownify as _md_convert
    MARKDOWNIFY_AVAILABLE = True
except ImportError:
    MARKDOWNIFY_AVAILABLE = False


# ============================================================================
# 常量
# ============================================================================
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
DEFAULT_TIMEOUT = 15
MAX_TIMEOUT = 60
DEFAULT_MAX_CHARS = 20000
DEFAULT_NUM_RESULTS = 10
MAX_NUM_RESULTS = 30

# 响应字节上限 10MB
MAX_RESPONSE_BYTES = 10 * 1024 * 1024

# 浏览器安装超时 2 分钟
BROWSER_INSTALL_TIMEOUT = 120

# 截图 base64 size 硬上限 1MB
SCREENSHOT_MAX_SIZE_MB = 1.0

# 搜索引擎 timeout
SEARCH_ENGINE_TIMEOUT = 10
SEARCH_MAX_CONCURRENT = 4

# 默认操作超时(浏览器交互类)
DEFAULT_ACTION_TIMEOUT = 15
MAX_ACTION_TIMEOUT = 120

# ----------------------------------------------------------------------------
# 搜索引擎配置(中国本土特色:墙内 / 墙外分流)
# ----------------------------------------------------------------------------
SEARCH_ENGINES_CN = [
    {"name": "百度", "url": "https://www.baidu.com/s?wd={query}&rn={num_results}", "weight": 1.0, "kind": "baidu"},
    {"name": "搜狗", "url": "https://www.sogou.com/web?query={query}&num={num_results}", "weight": 0.85, "kind": "sogou"},
    {"name": "360搜索", "url": "https://www.so.com/s?q={query}&num={num_results}", "weight": 0.75, "kind": "so360"},
]

SEARCH_ENGINES_GLOBAL = [
    {"name": "Google", "url": "https://www.google.com/search?q={query}&num={num_results}", "weight": 1.0, "kind": "google"},
    {"name": "Bing", "url": "https://www.bing.com/search?q={query}&count={num_results}", "weight": 0.9, "kind": "bing"},
    {"name": "Yahoo", "url": "https://search.yahoo.com/search?p={query}&n={num_results}", "weight": 0.75, "kind": "yahoo"},
]


# ============================================================================
# Handler 工具返回契约
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
# Surrogate / lone surrogate 清洗
# ============================================================================
def _sanitize(text: str) -> str:
    if not text:
        return text
    try:
        return text.encode("utf-8", errors="replace").decode("utf-8", errors="replace")
    except Exception:
        return text


# ============================================================================
# 头+尾截断
# ============================================================================
def _truncate_middle(text: str, max_chars: int) -> tuple[str, bool]:
    if len(text) <= max_chars:
        return text, False
    half = max_chars // 2
    head = text[:half]
    tail = text[-half:]
    skip_chars = len(text) - max_chars
    truncated = (
        head
        + f"\n\n[... output truncated: 共 {len(text)} 字符,截断 {skip_chars} 字符 ...]\n\n"
        + tail
    )
    return truncated, True


# ============================================================================
# 区域检测:中国大陆 vs 自由网络
# ============================================================================
_CACHED_REGION: Optional[str] = None


def _is_china_mainland() -> bool:
    """启发式判断当前系统是否处于中国大陆(全本地检测,无网络请求)。"""
    reasons: list[str] = []
    try:
        tzname = time.tzname[1] if time.daylight else time.tzname[0]
        if tzname and ("CST" in tzname or "China" in tzname or "上海" in tzname or "Beijing" in tzname):
            reasons.append(f"tzname={tzname!r}")
        if time.timezone == -28800:
            reasons.append(f"tz_offset=+8h(timezone={time.timezone})")
    except Exception:
        pass
    try:
        loc = locale.getlocale()[0] or ""
        if loc and ("zh_CN" in loc or "zh-CN" in loc or "Chinese_China" in loc):
            reasons.append(f"locale={loc!r}")
    except Exception:
        pass
    tz_env = os.environ.get("TZ", "")
    if tz_env and any(kw in tz_env for kw in (
        "Asia/Shanghai", "Asia/Chongqing", "Asia/Harbin", "Asia/Urumqi",
        "CST-8", "CST8", "UTC-8", "+0800", "+08:00",
    )):
        reasons.append(f"TZ={tz_env!r}")
    if sys.platform == "win32":
        try:
            import ctypes
            geoid = ctypes.windll.kernel32.GetUserGeoID(0)
            if geoid == 45 or geoid == 0x2D:
                reasons.append(f"win32_geo_id={geoid}(China)")
        except Exception:
            pass
        try:
            import ctypes
            buf = ctypes.create_unicode_buffer(16)
            ctypes.windll.kernel32.GetUserDefaultLocaleName(buf, 16)
            loc_name = buf.value or ""
            if "zh-CN" in loc_name or "zh_CN" in loc_name:
                reasons.append(f"win32_locale_name={loc_name!r}")
        except Exception:
            pass
    return len(reasons) > 0


def detect_region(force: Optional[str] = None) -> str:
    if force in ("cn", "global"):
        return force
    global _CACHED_REGION
    if _CACHED_REGION is None:
        _CACHED_REGION = "cn" if _is_china_mainland() else "global"
    return _CACHED_REGION


def detect_region_with_reasons(force: Optional[str] = None) -> tuple[str, list[str]]:
    if force in ("cn", "global"):
        return force, [f"force={force}"]
    if _is_china_mainland():
        return "cn", ["系统处于中国大陆"]
    return "global", ["系统不在中国大陆"]


# ============================================================================
# 自适应降级:启发式判断失误时,自动切换到另一组引擎重试
# ----------------------------------------------------------------------------
# 设计思路(用户决策 2026-07-24):不做预探活,改为"试探 + 自动回退"
#   1. 启发式判断选引擎组(0 额外延迟)
#   2. 跑该组三个引擎
#   3. 如果全部 ok=False 且 error 属于网络层(超时/连接失败/DNS)
#      → 自动切到另一组重试
#   4. 切换结果缓存到进程级,后续搜索直接走新组
#   5. 已降级过则不再二次切换(避免来回抖动)
# ============================================================================
_REGION_FALLBACK_APPLIED: bool = False
_REGION_FALLBACK_REASON: str = ""


def _is_network_error(engine_output: dict) -> bool:
    """判断单引擎输出是否属于"网络层失败"(应触发降级)。

    判定范围:Timeout / ConnectionError / DNS 失败 → 网络层
    HTTP 4xx/5xx 不算(说明网络可达,只是被拒,不属于墙)
    """
    if engine_output.get("ok"):
        return False
    err = (engine_output.get("error") or "").lower()
    if "超时" in err or "网络连接失败" in err or "dns" in err:
        return True
    return False


def _all_engines_network_failed(outputs: list[dict]) -> bool:
    """是否所有引擎都网络失败(可触发降级)。空输出不触发。"""
    if not outputs:
        return False
    return all(_is_network_error(o) for o in outputs)


def _try_region_fallback(current_region: str, outputs: list[dict]) -> tuple[str, bool, str]:
    """尝试把 region 切换到另一组,用于启发式判断失误时的自适应。

    Returns:
        (新 region, 是否切换, 切换原因)
        已切换过则不再二次切换;未全部网络失败也不切换。
    """
    global _REGION_FALLBACK_APPLIED, _REGION_FALLBACK_REASON
    if _REGION_FALLBACK_APPLIED:
        return current_region, False, "本进程内已降级过,不再二次切换"
    if not _all_engines_network_failed(outputs):
        return current_region, False, "未全部网络失败,不触发降级"
    fallback = "global" if current_region == "cn" else "cn"
    _REGION_FALLBACK_APPLIED = True
    _REGION_FALLBACK_REASON = (
        f"启发式判断 {current_region} 全部引擎网络失败,自动降级到 {fallback}"
    )
    return fallback, True, _REGION_FALLBACK_REASON


def reset_region_fallback() -> None:
    """重置区域降级状态 + 重新启发式判断(供 VPN 切换后手动刷新)。"""
    global _REGION_FALLBACK_APPLIED, _REGION_FALLBACK_REASON, _CACHED_REGION
    _REGION_FALLBACK_APPLIED = False
    _REGION_FALLBACK_REASON = ""
    _CACHED_REGION = None


# ============================================================================
# SSRF 防护 3 道关
# ============================================================================
_BLOCKED_HOSTNAMES = frozenset({
    "localhost", "localhost.localdomain", "broadcasthost",
    "ip6-localhost", "ip6-loopback",
})


def _ip_is_private(ip_str: str) -> bool:
    try:
        if "." in ip_str and ":" not in ip_str:
            parts = ip_str.split(".")
            if len(parts) != 4:
                return False
            try:
                octets = [int(p) for p in parts]
            except ValueError:
                return False
            if octets[0] == 0 or octets[0] == 10 or octets[0] == 127:
                return True
            if octets[0] == 100 and 64 <= octets[1] <= 127:
                return True
            if octets[0] == 169 and octets[1] == 254:
                return True
            if octets[0] == 172 and 16 <= octets[1] <= 31:
                return True
            if octets[0] == 192 and octets[1] == 168:
                return True
            if octets[0] == 192 and octets[1] == 0 and octets[2] == 0:
                return True
            if (octets[0] == 192 and octets[1] == 0 and octets[2] == 2) or \
               (octets[0] == 198 and octets[1] == 51 and octets[2] == 100) or \
               (octets[0] == 203 and octets[1] == 0 and octets[2] == 113):
                return True
            if 224 <= octets[0] <= 239 or 240 <= octets[0] <= 255:
                return True
            return False
        if ":" in ip_str:
            lower = ip_str.lower()
            if lower == "::1" or lower.startswith("::1"):
                return True
            if lower.startswith(("fe8", "fe9", "fea", "feb")):
                return True
            if lower.startswith(("fc", "fd")):
                return True
            if lower.startswith("ff"):
                return True
            if "::ffff:" in lower:
                v4 = lower.split("::ffff:")[-1]
                return _ip_is_private(v4)
            return False
    except Exception:
        return False
    return False


def _validate_url(url: str) -> tuple[bool, str, str]:
    if not url or not url.strip():
        return False, "URL 不能为空", ""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False, f"只支持 http/https,当前 scheme: {parsed.scheme!r}", ""
    host = parsed.hostname
    if not host:
        return False, f"URL 缺少 host: {url}", ""
    if host.lower() in _BLOCKED_HOSTNAMES:
        return False, f"host 命中黑名单: {host}", ""
    if re.match(r"^\d{1,3}(\.\d{1,3}){3}$", host) or ":" in host:
        if _ip_is_private(host):
            return False, f"host 是内网 IP: {host}", ""
        return True, "", host
    try:
        infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror as e:
        return False, f"DNS 解析失败: {host} ({e})", ""
    for info in infos:
        sockaddr = info[4]
        ip = sockaddr[0]
        if _ip_is_private(ip):
            return False, f"DNS 解析到内网 IP: {host} → {ip}", ""
    first_ip = infos[0][4][0] if infos else ""
    return True, "", first_ip


# ============================================================================
# HTML 处理
# ============================================================================
_RE_SCRIPT = re.compile(r"<script\b[^>]*>.*?</script>", re.IGNORECASE | re.DOTALL)
_RE_STYLE = re.compile(r"<style\b[^>]*>.*?</style>", re.IGNORECASE | re.DOTALL)
_RE_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_RE_TAG = re.compile(r"<[^>]+>")
_RE_BLANK_LINE = re.compile(r"\n\s*\n+")


def _html_to_text(raw_html: str) -> str:
    text = raw_html
    text = _RE_SCRIPT.sub(" ", text)
    text = _RE_STYLE.sub(" ", text)
    text = _RE_COMMENT.sub(" ", text)
    text = re.sub(r"<(br|hr)\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(
        r"</?(p|div|li|ul|ol|tr|h[1-6]|pre|blockquote|section|article|header|footer|nav|aside)\b[^>]*>",
        "\n", text, flags=re.IGNORECASE,
    )
    text = _RE_TAG.sub(" ", text)
    text = html.unescape(text)
    text = _RE_BLANK_LINE.sub("\n\n", text)
    lines = [line.rstrip() for line in text.splitlines()]
    return "\n".join(lines).strip()


def _html_to_markdown_simple(raw_html: str) -> str:
    text = raw_html
    text = _RE_SCRIPT.sub("", text)
    text = _RE_STYLE.sub("", text)
    text = _RE_COMMENT.sub("", text)
    for level in range(1, 7):
        pattern = rf"<h{level}[^>]*>(.*?)</h{level}>"
        text = re.sub(pattern, lambda m, lvl=level: f"\n\n{'#' * lvl} {_html_to_text(m.group(1))}\n\n",
                     text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'<a\s+[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
                  lambda m: f"[{_html_to_text(m.group(2))}]({m.group(1)})",
                  text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<(br|hr)\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(
        r"</?(p|div|li|ul|ol|tr|pre|blockquote|section|article|header|footer|nav|aside)\b[^>]*>",
        "\n", text, flags=re.IGNORECASE,
    )
    text = re.sub(r"<(strong|b)\b[^>]*>(.*?)</\1>", r"**\2**", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<(em|i)\b[^>]*>(.*?)</\1>", r"*\2*", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<code\b[^>]*>(.*?)</code>", r"`\1`", text, flags=re.IGNORECASE | re.DOTALL)
    text = _RE_TAG.sub(" ", text)
    text = html.unescape(text)
    text = _RE_BLANK_LINE.sub("\n\n", text)
    lines = [line.rstrip() for line in text.splitlines()]
    return "\n".join(lines).strip()


def _html_to_markdown(raw_html: str) -> str:
    if MARKDOWNIFY_AVAILABLE:
        try:
            return _md_convert(raw_html, heading_style="ATX", bullets="-").strip()
        except Exception:
            pass
    return _html_to_markdown_simple(raw_html)


def _extract_title(raw_html: str) -> Optional[str]:
    m = re.search(r"<title[^>]*>(.*?)</title>", raw_html, re.IGNORECASE | re.DOTALL)
    if m:
        return html.unescape(m.group(1).strip())
    return None


def _extract_content_readability(raw_html: str) -> tuple[str, dict]:
    if not READABILITY_AVAILABLE:
        return raw_html, {}
    try:
        doc = ReadabilityDocument(raw_html)
        summary = doc.summary()
        meta = {"title": doc.short_title() or doc.title() or ""}
        return summary, meta
    except Exception:
        return raw_html, {}


# ============================================================================
# 搜索引擎结果解析
# ============================================================================
_ENGINE_PARSERS = {
    "duckduckgo": {
        "url": "https://html.duckduckgo.com/html/?q={query}",
        "result_block": re.compile(
            r'<div[^>]*class="[^"]*result\s+(?:result--html|result--standard)[^"]*"[^>]*>(.*?)(?=<div[^>]*class="[^"]*result\s|<div[^>]*class="[^"]*pagination|$)',
            re.IGNORECASE | re.DOTALL,
        ),
        "link": re.compile(
            r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
            re.IGNORECASE | re.DOTALL,
        ),
        "snippet": re.compile(
            r'class="result__snippet"[^>]*>(.*?)</(?:a|td|div|span)',
            re.IGNORECASE | re.DOTALL,
        ),
    },
    "baidu": {
        "url": "https://www.baidu.com/s?wd={query}&rn={num_results}",
        "result_block": re.compile(
            r'<div[^>]*class="[^"]*\bresult\b[^"]*"[^>]*>(.*?)(?=<div[^>]*class="[^"]*\bresult\b|</body|$)',
            re.IGNORECASE | re.DOTALL,
        ),
        "link": re.compile(
            r'<a[^>]*class="[^"]*\bresult-(?:title|a|op)[^"]*"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
            re.IGNORECASE | re.DOTALL,
        ),
        "snippet": re.compile(
            r'class="[^"]*(?:c-abstract|content-right_8Zs40|result-content|abstract)[^"]*"[^>]*>(.*?)</(?:div|span|td)',
            re.IGNORECASE | re.DOTALL,
        ),
    },
    "sogou": {
        "url": "https://www.sogou.com/web?query={query}&num={num_results}",
        "result_block": re.compile(
            r'<div[^>]*class="[^"]*\bvrwrap\b[^"]*"[^>]*>(.*?)(?=<div[^>]*class="[^"]*\bvrwrap\b|</body|$)',
            re.IGNORECASE | re.DOTALL,
        ),
        "link": re.compile(r'<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL),
        "snippet": re.compile(r'class="[^"]*\bstr_info\b[^"]*"[^>]*>(.*?)</div>', re.IGNORECASE | re.DOTALL),
    },
    "so360": {
        "url": "https://www.so.com/s?q={query}&num={num_results}",
        "result_block": re.compile(
            r'<li[^>]*class="[^"]*\bres\b[^"]*"[^>]*>(.*?)(?=<li[^>]*class="[^"]*\bres\b|</ul|$)',
            re.IGNORECASE | re.DOTALL,
        ),
        "link": re.compile(r'<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL),
        "snippet": re.compile(r'class="[^"]*\bres-desc\b[^"]*"[^>]*>(.*?)</p>', re.IGNORECASE | re.DOTALL),
    },
    "google": {
        "url": "https://www.google.com/search?q={query}&num={num_results}",
        "result_block": re.compile(
            r'<div[^>]*class="[^"]*\bg\b[^"]*"[^>]*>(.*?)(?=<div[^>]*class="[^"]*\bg\b|</body|$)',
            re.IGNORECASE | re.DOTALL,
        ),
        "link": re.compile(r'<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL),
        "snippet": re.compile(r'class="[^"]*\bVwiC3b\b[^"]*"[^>]*>(.*?)</span>', re.IGNORECASE | re.DOTALL),
    },
    "bing": {
        "url": "https://www.bing.com/search?q={query}&count={num_results}",
        "result_block": re.compile(
            r'<li[^>]*class="[^"]*\bb_algo\b[^"]*"[^>]*>(.*?)(?=<li[^>]*class="[^"]*\bb_algo\b|</ol|$)',
            re.IGNORECASE | re.DOTALL,
        ),
        "link": re.compile(r'<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL),
        "snippet": re.compile(r'class="[^"]*\bb_caption\b[^>]*>.*?<p[^>]*>(.*?)</p>', re.IGNORECASE | re.DOTALL),
    },
    "yahoo": {
        "url": "https://search.yahoo.com/search?p={query}&n={num_results}",
        "result_block": re.compile(
            r'<div[^>]*class="[^"]*\bdd\b[^"]*\balgo\b[^"]*"[^>]*>(.*?)(?=<div[^>]*class="[^"]*\bdd\b[^"]*\balgo\b|</body|$)',
            re.IGNORECASE | re.DOTALL,
        ),
        "link": re.compile(r'<a[^>]*class="[^"]*\bd-ib\b[^"]*"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL),
        "snippet": re.compile(r'class="[^"]*\bfz-ms\b[^"]*"[^>]*>(.*?)</span>', re.IGNORECASE | re.DOTALL),
    },
}


def _parse_engine_html(html_text: str, engine_kind: str, max_results: int) -> list[dict]:
    results: list[dict] = []
    parser = _ENGINE_PARSERS.get(engine_kind)
    if parser:
        blocks = parser["result_block"].findall(html_text)
        for block in blocks:
            if len(results) >= max_results:
                break
            a_match = parser["link"].search(block)
            if not a_match:
                continue
            url = html.unescape(a_match.group(1).strip())
            title = _html_to_text(a_match.group(2))
            title = re.sub(r"\s+", " ", title).strip()
            if not url.startswith(("http://", "https://")):
                continue
            snippet = ""
            snip_match = parser["snippet"].search(block)
            if snip_match:
                snippet = _html_to_text(snip_match.group(1))
                snippet = re.sub(r"\s+", " ", snippet).strip()
            if not title:
                continue
            results.append({
                "title": title[:200],
                "url": url,
                "snippet": snippet[:500],
            })
    if not results:
        for a_match in re.finditer(
            r'<a[^>]+href="(https?://[^"]+)"[^>]*>(.*?)</a>',
            html_text, re.IGNORECASE | re.DOTALL,
        ):
            if len(results) >= max_results:
                break
            url = a_match.group(1)
            if any(skip in url for skip in (
                "javascript:", "#", "mailto:",
                "baidu.com/", "so.com/", "sogou.com/",
                "google.com/", "bing.com/", "yahoo.com/",
            )):
                continue
            title = _html_to_text(a_match.group(2))
            title = re.sub(r"\s+", " ", title).strip()
            if not title or len(title) < 4:
                continue
            results.append({
                "title": title[:200],
                "url": url,
                "snippet": "",
            })
    return results


def _search_single_engine(
    engine_name: str,
    engine_url: str,
    engine_kind: str,
    query: str,
    num_results: int,
    timeout: int,
) -> dict:
    encoded_query = urllib.parse.quote(query)
    full_url = engine_url.format(query=encoded_query, num_results=num_results)
    headers = {
        "User-Agent": DEFAULT_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8" if engine_kind in (
            "duckduckgo", "baidu", "sogou", "so360"
        ) else "en-US,en;q=0.9",
    }
    start = time.time()
    try:
        resp = requests.get(full_url, headers=headers, timeout=timeout, allow_redirects=True)
        resp.raise_for_status()
        html_text = _sanitize(resp.text)
        results = _parse_engine_html(html_text, engine_kind, num_results)
        duration_ms = int((time.time() - start) * 1000)
        return {
            "engine": engine_name, "kind": engine_kind, "ok": True,
            "results": results, "count": len(results),
            "duration_ms": duration_ms, "url": full_url, "error": None,
        }
    except Timeout:
        return {"engine": engine_name, "kind": engine_kind, "ok": False, "results": [],
                "count": 0, "duration_ms": int((time.time() - start) * 1000),
                "url": full_url, "error": f"超时({timeout}s)"}
    except ConnectionError as e:
        return {"engine": engine_name, "kind": engine_kind, "ok": False, "results": [],
                "count": 0, "duration_ms": int((time.time() - start) * 1000),
                "url": full_url, "error": f"网络连接失败: {e}"}
    except HTTPError as e:
        return {"engine": engine_name, "kind": engine_kind, "ok": False, "results": [],
                "count": 0, "duration_ms": int((time.time() - start) * 1000),
                "url": full_url, "error": f"HTTP {resp.status_code if resp else '?'}: {e}"}
    except Exception as e:
        return {"engine": engine_name, "kind": engine_kind, "ok": False, "results": [],
                "count": 0, "duration_ms": int((time.time() - start) * 1000),
                "url": full_url, "error": f"{type(e).__name__}: {e}"}


def _merge_search_results(
    engine_outputs: list[dict],
    weights: dict[str, float],
    num_results: int,
) -> list[dict]:
    scored: dict[str, dict] = {}
    for output in engine_outputs:
        engine_name = output["engine"]
        w = weights.get(engine_name, 1.0)
        for rank, r in enumerate(output["results"]):
            url = r["url"]
            if url not in scored:
                scored[url] = {
                    "title": r["title"], "url": url, "snippet": r["snippet"],
                    "score": 0.0, "sources": [],
                }
            scored[url]["score"] += w / (rank + 1)
            if engine_name not in scored[url]["sources"]:
                scored[url]["sources"].append(engine_name)
            if len(r.get("snippet", "")) > len(scored[url]["snippet"]):
                scored[url]["snippet"] = r["snippet"]
            if len(r.get("title", "")) > len(scored[url]["title"]):
                scored[url]["title"] = r["title"]
    sorted_results = sorted(scored.values(), key=lambda x: x["score"], reverse=True)[:num_results]
    return sorted_results


# ============================================================================
# 并发跑一组搜索引擎(供 web_search 主流程 + 降级回退共用)
# ============================================================================
def _run_engine_group(
    engines: list[dict],
    query: str,
    num_results: int,
    timeout: int,
) -> list[dict]:
    """并发跑一组搜索引擎,返回 outputs 列表(按引擎名排序)。"""
    outputs: list[dict] = []
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=min(len(engines), SEARCH_MAX_CONCURRENT)
    ) as executor:
        future_to_engine = {
            executor.submit(
                _search_single_engine,
                engine_name=e["name"], engine_url=e["url"], engine_kind=e["kind"],
                query=query, num_results=num_results, timeout=timeout,
            ): e["name"]
            for e in engines
        }
        for future in concurrent.futures.as_completed(future_to_engine):
            try:
                output = future.result()
            except Exception as e:
                engine_name = future_to_engine[future]
                output = {
                    "engine": engine_name, "ok": False, "results": [], "count": 0,
                    "duration_ms": 0, "url": "", "error": f"future 异常: {type(e).__name__}: {e}",
                }
            outputs.append(output)
    outputs.sort(key=lambda o: o["engine"])
    return outputs


# ============================================================================
# 工具 1: web_search
# ============================================================================
def web_search(
    query: str,
    num_results: int = DEFAULT_NUM_RESULTS,
    region: str = "auto",
    timeout: int = SEARCH_ENGINE_TIMEOUT,
) -> dict:
    if not query or not query.strip():
        return _err("query 不能为空")
    if num_results <= 0:
        num_results = DEFAULT_NUM_RESULTS
    if num_results > MAX_NUM_RESULTS:
        num_results = MAX_NUM_RESULTS
    if timeout <= 0:
        timeout = SEARCH_ENGINE_TIMEOUT
    if timeout > 60:
        timeout = 60
    if region not in ("auto", "cn", "global"):
        return _err(f"region 必须是 auto/cn/global,当前: {region!r}")
    actual_region, region_reasons = detect_region_with_reasons(
        force=region if region != "auto" else None
    )
    engines = SEARCH_ENGINES_CN if actual_region == "cn" else SEARCH_ENGINES_GLOBAL
    weights = {e["name"]: e["weight"] for e in engines}

    start = time.time()
    engine_outputs = _run_engine_group(engines, query, num_results, timeout)

    # 自适应降级:启发式判断失误时,自动切到另一组引擎重试
    # 触发条件:启发式选的那组**全部引擎**都"网络层失败"(超时/连接失败/DNS)
    # 不触发:HTTP 4xx/5xx(说明网络可达,只是被拒)、单引擎失败
    fallback_note = ""
    if _all_engines_network_failed(engine_outputs):
        new_region, did_fallback, msg = _try_region_fallback(actual_region, engine_outputs)
        if did_fallback:
            fallback_engines = (
                SEARCH_ENGINES_GLOBAL if new_region == "global" else SEARCH_ENGINES_CN
            )
            fallback_outputs = _run_engine_group(fallback_engines, query, num_results, timeout)
            engine_outputs = fallback_outputs
            engines = fallback_engines
            weights = {e["name"]: e["weight"] for e in engines}
            actual_region = new_region
            region_reasons = region_reasons + [f"fallback: {msg}"]
            fallback_note = msg

    merged = _merge_search_results(engine_outputs, weights, num_results)
    duration_ms = int((time.time() - start) * 1000)

    if not merged:
        lines = [
            f"# 搜索: {query}",
            f"# 区域: {actual_region}  引擎: {[e['name'] for e in engines]}  数量: 0/{num_results}  duration: {duration_ms}ms",
        ]
        if fallback_note:
            lines.append(f"# 自适应降级: {fallback_note}")
        lines.append("")
        lines.append("[所有搜索引擎均未返回结果]")
        lines.append("")
        lines.append("# 各引擎状态:")
        for out in engine_outputs:
            status = "OK" if out["ok"] else f"ERR({out.get('error', '?')})"
            lines.append(f"  - {out['engine']}: {status}  count={out.get('count', 0)}  duration={out.get('duration_ms', 0)}ms")
        return _ok("\n".join(lines), data={
            "query": query, "region": actual_region,
            "engines": [e["name"] for e in engines], "results": [], "count": 0,
            "duration_ms": duration_ms, "engine_outputs": engine_outputs,
            "region_reasons": region_reasons,
            "fallback_applied": bool(fallback_note),
            "fallback_note": fallback_note,
        })

    lines = [
        f"# 搜索: {query}",
        f"# 区域: {actual_region}  引擎: {[o['engine'] for o in engine_outputs]}  "
        f"数量: {len(merged)}/{num_results}  duration: {duration_ms}ms",
        f"# 区域判定: {'; '.join(region_reasons)}",
    ]
    if fallback_note:
        lines.append(f"# 自适应降级: {fallback_note}")
    lines.append("")
    for i, r in enumerate(merged, 1):
        lines.append(f"## {i}. {r['title']}")
        lines.append(f"   URL: {r['url']}")
        if r.get("snippet"):
            lines.append(f"   {r['snippet']}")
        sources = ", ".join(r.get("sources", []))
        if sources:
            lines.append(f"   [来源: {sources}  score: {r['score']:.2f}]")
        lines.append("")
    lines.append("## 引擎汇总")
    for out in engine_outputs:
        status = "OK" if out["ok"] else "ERR"
        err_msg = f" ({out.get('error', '')})" if not out["ok"] else ""
        lines.append(f"  - {out['engine']}: {status}  count={out.get('count', 0)}  "
                     f"duration={out.get('duration_ms', 0)}ms{err_msg}")
    content = "\n".join(lines).rstrip()
    content, truncated = _truncate_middle(content, DEFAULT_MAX_CHARS)
    return _ok(content, data={
        "query": query, "region": actual_region,
        "engines": [e["name"] for e in engines], "results": merged, "count": len(merged),
        "duration_ms": duration_ms, "engine_outputs": engine_outputs,
        "region_reasons": region_reasons, "truncated": truncated,
        "fallback_applied": bool(fallback_note),
        "fallback_note": fallback_note,
    })


# ============================================================================
# 工具 2: web_search_diag
# ============================================================================
def web_search_diag(force_region: Optional[str] = None, reset: bool = False) -> dict:
    """区域诊断工具。

    Args:
        force_region: 强制 region(cn/global),传 None 走自动判断
        reset: 是否先重置降级状态 + 重新启发式判断(VPN 切换后用)
    """
    if reset:
        reset_region_fallback()
    sys_info = {
        "platform": sys.platform,
        "tzname_day": time.tzname[0] if time.tzname else None,
        "tzname_no_day": time.tzname[1] if time.tzname and len(time.tzname) > 1 else None,
        "timezone_offset_sec": time.timezone,
        "timezone_offset_human": (
            f"UTC{'-' if time.timezone > 0 else '+'}{abs(time.timezone) // 3600}"
            if time.timezone else "UTC+0"
        ),
        "locale": None,
        "tz_env": os.environ.get("TZ", ""),
    }
    try:
        sys_info["locale"] = locale.getlocale()[0]
    except Exception:
        pass
    if sys.platform == "win32":
        try:
            import ctypes
            sys_info["win32_geo_id"] = ctypes.windll.kernel32.GetUserGeoID(0)
        except Exception:
            sys_info["win32_geo_id"] = None
        try:
            import ctypes
            buf = ctypes.create_unicode_buffer(16)
            ctypes.windll.kernel32.GetUserDefaultLocaleName(buf, 16)
            sys_info["win32_locale_name"] = buf.value
        except Exception:
            sys_info["win32_locale_name"] = None
    actual_region, reasons = detect_region_with_reasons(force=force_region)
    engines = SEARCH_ENGINES_CN if actual_region == "cn" else SEARCH_ENGINES_GLOBAL
    engine_names = [e["name"] for e in engines]
    fallback_status = "已降级" if _REGION_FALLBACK_APPLIED else "未降级"
    fallback_detail = _REGION_FALLBACK_REASON or "-"
    content_lines = [
        "# 区域诊断", f"# 判定结果: {actual_region}",
        f"# 判定理由: {'; '.join(reasons)}",
        f"# 生效引擎: {', '.join(engine_names)}",
        f"# 降级状态: {fallback_status} ({fallback_detail})",
        "", "# 系统信息:",
    ]
    for k, v in sys_info.items():
        content_lines.append(f"  - {k}: {v!r}")
    return _ok("\n".join(content_lines), data={
        "detected_region": actual_region, "reasons": reasons,
        "engines_in_use": engine_names, "system_info": sys_info,
        "force_region": force_region,
        "fallback_applied": _REGION_FALLBACK_APPLIED,
        "fallback_reason": _REGION_FALLBACK_REASON,
    })


# ============================================================================
# 工具 3/4: fetch_url / fetch_urls
# ============================================================================
def _http_fetch(
    url: str, format: str = "markdown", extract_content: bool = True,
    max_chars: int = DEFAULT_MAX_CHARS, timeout: int = DEFAULT_TIMEOUT,
    headers: Optional[dict] = None,
) -> dict:
    if not url or not url.strip():
        return _err("url 不能为空")
    if format not in ("html", "markdown", "text", "json"):
        return _err(f"format 必须是 html/markdown/text/json,当前: {format!r}")
    ok, reason, _resolved_ip = _validate_url(url)
    if not ok:
        return _err(f"SSRF 防护拒绝: {reason}")
    if max_chars <= 0:
        max_chars = DEFAULT_MAX_CHARS
    if timeout <= 0:
        timeout = DEFAULT_TIMEOUT
    if timeout > MAX_TIMEOUT:
        timeout = MAX_TIMEOUT
    req_headers = {
        "User-Agent": DEFAULT_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/json;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
    }
    if headers:
        for k, v in headers.items():
            req_headers[str(k)] = str(v)
    start = time.time()
    try:
        try:
            head_resp = requests.head(url, headers=req_headers, timeout=min(timeout, 5), allow_redirects=True)
            cl = head_resp.headers.get("Content-Length")
            if cl and int(cl) > MAX_RESPONSE_BYTES:
                return _err(f"响应体过大(HEAD 预检): Content-Length={cl},上限 {MAX_RESPONSE_BYTES} bytes")
        except RequestException:
            pass
        resp = requests.get(url, headers=req_headers, timeout=timeout, allow_redirects=True)
        resp.raise_for_status()
        content_length = resp.headers.get("Content-Length")
        if content_length and int(content_length) > MAX_RESPONSE_BYTES:
            return _err(f"响应体过大: Content-Length={content_length},上限 {MAX_RESPONSE_BYTES} bytes")
        raw_bytes = resp.content
        if len(raw_bytes) > MAX_RESPONSE_BYTES:
            return _err(f"响应体超过 {MAX_RESPONSE_BYTES} bytes 上限(实际 {len(raw_bytes)} bytes)")
        if resp.encoding is None or resp.encoding == "ISO-8859-1":
            resp.encoding = resp.apparent_encoding or "utf-8"
        try:
            raw_html = raw_bytes.decode(resp.encoding, errors="replace")
        except (LookupError, TypeError):
            raw_html = raw_bytes.decode("utf-8", errors="replace")
        raw_html = _sanitize(raw_html)
        duration_ms = int((time.time() - start) * 1000)
        content_type = resp.headers.get("Content-Type", "")
        title = _extract_title(raw_html) or ""
        if format == "json":
            content = raw_html
            extracted_meta = {}
        elif extract_content and READABILITY_AVAILABLE:
            cleaned_html, extracted_meta = _extract_content_readability(raw_html)
            if format == "html":
                content = cleaned_html
            elif format == "markdown":
                content = _html_to_markdown(cleaned_html)
            else:
                content = _html_to_text(cleaned_html)
        else:
            if format == "html":
                content = raw_html
            elif format == "markdown":
                content = _html_to_markdown(raw_html)
            else:
                content = _html_to_text(raw_html)
            extracted_meta = {}
        truncated_text, was_truncated = _truncate_middle(content, max_chars)
        response_lines = [
            f"# {url}",
            f"# status={resp.status_code}  content-type={content_type}  duration={duration_ms}ms",
            f"# format={format}  extract_content={extract_content}  readable={READABILITY_AVAILABLE}",
        ]
        if title:
            response_lines.append(f"# title: {title}")
        if extracted_meta.get("title"):
            response_lines.append(f"# readable_title: {extracted_meta['title']}")
        response_lines.append(
            f"# bytes={len(raw_bytes)}  content_chars={len(content)}  truncated={was_truncated}"
        )
        response_lines.append("")
        response_lines.append(truncated_text)
        return _ok("\n".join(response_lines), data={
            "url": url, "title": title or extracted_meta.get("title", ""),
            "format": format, "content": content, "truncated_content": truncated_text,
            "status_code": resp.status_code, "content_type": content_type,
            "bytes": len(raw_bytes), "duration_ms": duration_ms,
            "truncated": was_truncated, "max_chars": max_chars,
            "extract_content": extract_content,
        })
    except Timeout:
        return _err(f"抓取超时({timeout}s): {url}")
    except ConnectionError as e:
        return _err(f"网络连接失败(可能无网络或 DNS 失败): {e}")
    except HTTPError as e:
        return _err(f"HTTP {resp.status_code if resp else '?'}: {e}")
    except RequestException as e:
        return _err(f"HTTP 请求失败: {type(e).__name__}: {e}")
    except Exception as e:
        return _err(f"抓取异常: {type(e).__name__}: {e}")


def fetch_url(
    url: str, format: str = "markdown", extract_content: bool = True,
    max_chars: int = DEFAULT_MAX_CHARS, timeout: int = DEFAULT_TIMEOUT,
    headers: Optional[dict] = None,
) -> dict:
    return _http_fetch(url=url, format=format, extract_content=extract_content,
                       max_chars=max_chars, timeout=timeout, headers=headers)


def fetch_urls(
    urls: list[str], format: str = "markdown", extract_content: bool = True,
    max_chars: int = DEFAULT_MAX_CHARS, timeout: int = DEFAULT_TIMEOUT,
    max_concurrent: int = 5,
) -> dict:
    if not urls:
        return _err("urls 不能为空列表")
    if max_concurrent <= 0:
        max_concurrent = 5
    start = time.time()
    results: list[dict] = []
    success_count = 0
    error_count = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_concurrent) as executor:
        future_to_url = {
            executor.submit(_http_fetch, url=u, format=format, extract_content=extract_content,
                            max_chars=max_chars, timeout=timeout, headers=None): u
            for u in urls
        }
        for future, url in future_to_url.items():
            try:
                r = future.result()
            except Exception as e:
                r = _err(f"并发执行异常: {type(e).__name__}: {e}", data={"url": url})
            results.append({"url": url, **r})
            if r.get("success"):
                success_count += 1
            else:
                error_count += 1
    duration_ms = int((time.time() - start) * 1000)
    lines = [
        f"# 批量抓取: {len(urls)} URLs",
        f"# success={success_count}  error={error_count}  max_concurrent={max_concurrent}  "
        f"duration={duration_ms}ms",
        "",
    ]
    for i, r in enumerate(results, 1):
        status = "[OK]" if r.get("success") else "[ERR]"
        title = (r.get("data") or {}).get("title", "")
        title_part = f"  title={title}" if title else ""
        lines.append(f"## {i}. {status} {r['url']}{title_part}")
        if not r.get("success"):
            lines.append(f"   {r.get('content', '')}")
        lines.append("")
    return _ok("\n".join(lines), data={
        "total": len(urls), "success_count": success_count, "error_count": error_count,
        "results": results, "duration_ms": duration_ms,
    })


# ============================================================================
# Chromium 路径查找(内置优先)
# ============================================================================
def _find_builtin_chromium() -> Optional[str]:
    env_path = os.environ.get("ONION_CHROMIUM_PATH", "").strip()
    if env_path and os.path.isfile(env_path):
        return env_path
    chromium_dir = Path(__file__).resolve().parent / "chromium"
    if not chromium_dir.exists():
        return None
    if sys.platform == "win32":
        candidates = [chromium_dir / "chrome-win64" / "chrome.exe", chromium_dir / "chrome-win" / "chrome.exe"]
    elif sys.platform == "darwin":
        candidates = [
            chromium_dir / "chrome-mac-x64" / "Chromium.app" / "Contents" / "MacOS" / "Chromium",
            chromium_dir / "chrome-mac-arm64" / "Chromium.app" / "Contents" / "MacOS" / "Chromium",
            chromium_dir / "chrome-mac" / "Chromium.app" / "Contents" / "MacOS" / "Chromium",
        ]
    else:
        candidates = [chromium_dir / "chrome-linux64" / "chrome", chromium_dir / "chrome-linux" / "chrome"]
    for c in candidates:
        if c.exists() and c.is_file():
            return str(c)
    for pattern in ("**/chrome.exe", "**/chrome", "**/chromium"):
        for found in chromium_dir.glob(pattern):
            if found.is_file():
                return str(found)
    return None


def _find_playwright_chromium() -> Optional[str]:
    if not PLAYWRIGHT_AVAILABLE:
        return None
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))) / "ms-playwright"
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Caches" / "ms-playwright"
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache"))) / "ms-playwright"
    if not base.exists():
        return None
    if sys.platform == "win32":
        rel_paths = [
            ("chromium-*", "chrome-win64", "chrome.exe"),
            ("chromium-*", "chrome-win", "chrome.exe"),
            ("chromium_headless_shell-*", "chrome-headless-shell-win64", "chrome-headless-shell.exe"),
            ("chromium_headless_shell-*", "chrome-headless-shell-win", "chrome-headless-shell.exe"),
        ]
    elif sys.platform == "darwin":
        rel_paths = [
            ("chromium-*", "chrome-mac-x64", "Chromium.app/Contents/MacOS/Chromium"),
            ("chromium-*", "chrome-mac-arm64", "Chromium.app/Contents/MacOS/Chromium"),
            ("chromium-*", "chrome-mac", "Chromium.app/Contents/MacOS/Chromium"),
            ("chromium_headless_shell-*", "chrome-headless-shell-mac", "Chromium.app/Contents/MacOS/Chromium"),
        ]
    else:
        rel_paths = [
            ("chromium-*", "chrome-linux64", "chrome"),
            ("chromium-*", "chrome-linux", "chrome"),
            ("chromium_headless_shell-*", "chrome-headless-shell-linux64", "chrome-headless-shell"),
            ("chromium_headless_shell-*", "chrome-headless-shell-linux", "chrome-headless-shell"),
        ]
    for dir_glob, subdir, filename in rel_paths:
        matched_dirs = sorted(base.glob(dir_glob), reverse=True)
        for cd in matched_dirs:
            exe = cd / subdir / filename
            if exe.exists() and exe.is_file():
                return str(exe)
    return None


def _find_chromium_executable(executable_path: Optional[str] = None) -> Optional[str]:
    if executable_path and os.path.isfile(executable_path):
        return executable_path
    builtin = _find_builtin_chromium()
    if builtin:
        return builtin
    playwright = _find_playwright_chromium()
    if playwright:
        return playwright
    return None


# ============================================================================
# BrowserManager - 单例 + 懒加载(共享 page)
# ============================================================================
class BrowserManager:
    """
    浏览器单例 + 懒加载 + 共享 page。

    所有操作类工具(click/fill/...)都复用同一 page,避免每次操作都启停 Chromium。
    """

    def __init__(self) -> None:
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._console_logs: list[str] = []
        self._page_logs: list[dict] = []  # 详细 console 事件

    def is_running(self) -> bool:
        return self._page is not None

    def ensure_browser(
        self,
        executable_path: Optional[str] = None,
        channel: Optional[str] = None,
        proxy: Optional[str] = None,
        headless: bool = True,
    ):
        if not PLAYWRIGHT_AVAILABLE:
            raise RuntimeError(
                "playwright 未安装。请先 `pip install playwright` 然后 `playwright install chromium`。"
                "也可调 browser_install 工具自动安装。"
            )
        if self._page is not None:
            return self._page
        try:
            self._playwright = sync_playwright().start()
        except Exception as e:
            raise RuntimeError(f"playwright 启动失败: {e}") from e
        launch_kwargs: dict = {"headless": headless}
        resolved_executable = _find_chromium_executable(executable_path)
        if resolved_executable:
            launch_kwargs["executable_path"] = resolved_executable
        if channel:
            launch_kwargs["channel"] = channel
        if proxy:
            launch_kwargs["proxy"] = {"server": proxy}
        try:
            self._browser = self._playwright.chromium.launch(**launch_kwargs)
        except Exception as e:
            error_msg = str(e)
            if "Executable doesn't exist" in error_msg or "browserType.launch" in error_msg:
                raise RuntimeError(
                    f"Chromium 浏览器二进制未安装: {error_msg}。"
                    f"请调 browser_install 工具自动安装,或下载 Chromium 到 buildin_tools/chromium/ 内置目录。"
                ) from e
            raise RuntimeError(f"Chromium 启动失败: {e}") from e
        self._context = self._browser.new_context(
            user_agent=DEFAULT_USER_AGENT,
            viewport={"width": 1280, "height": 720},
        )
        # 反爬虫指纹
        self._context.add_init_script(
            """
            Object.defineProperty(navigator, 'webdriver', { get: () => false });
            (function() {
                try { delete window.cdc_adoQpoasnfa76pfcZLmcfl_Array; } catch (e) {}
                try { delete window.cdc_adoQpoasnfa76pfcZLmcfl_Promise; } catch (e) {}
                try { delete window.cdc_adoQpoasnfa76pfcZLmcfl_Symbol; } catch (e) {}
            })();
            window.chrome = { runtime: {} };
            Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en', 'zh-CN', 'zh'] });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
            """
        )
        # 默认屏蔽图片/CSS/字体(省 80% 带宽,可通过 context.route 改)
        self._context.route(
            "**/*.{png,jpg,jpeg,gif,webp,svg,ico,css,woff,woff2,ttf,otf,mp3,mp4,webm,ogg,wav,pdf}",
            lambda route: route.abort(),
        )
        self._console_logs = []
        self._page_logs = []
        self._page = self._context.new_page()
        self._page.on("console", self._on_console)
        return self._page

    def _on_console(self, msg) -> None:
        text = f"[{msg.type}] {msg.text}"[:500]
        self._console_logs.append(text)
        try:
            loc = msg.location or {}
            self._page_logs.append({
                "type": msg.type,
                "text": msg.text[:500],
                "url": loc.get("url"),
                "line": loc.get("lineNumber"),
            })
        except Exception:
            pass

    def close(self) -> None:
        try:
            if self._context is not None:
                self._context.close()
        except Exception:
            pass
        try:
            if self._browser is not None:
                self._browser.close()
        except Exception:
            pass
        try:
            if self._playwright is not None:
                self._playwright.stop()
        except Exception:
            pass
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None

    def get_console_logs(self) -> list[str]:
        return list(self._console_logs)

    def clear_console_logs(self) -> None:
        self._console_logs = []
        self._page_logs = []


_BROWSER = BrowserManager()


def _ensure_browser_for_browser_tools(
    executable_path: Optional[str] = None,
    channel: Optional[str] = None,
    proxy: Optional[str] = None,
) -> tuple[Any, Optional[dict]]:
    try:
        page = _BROWSER.ensure_browser(
            executable_path=executable_path, channel=channel, proxy=proxy,
        )
        return page, None
    except RuntimeError as e:
        return None, _err(str(e))


# ============================================================================
# 工具 5-9: 浏览器导航类
# ============================================================================
def _normalize_timeout(timeout: int, default: int = DEFAULT_ACTION_TIMEOUT, max_v: int = MAX_ACTION_TIMEOUT) -> int:
    if timeout <= 0:
        timeout = default
    return min(timeout, max_v)


def browser_navigate(
    url: str,
    wait_until: str = "load",
    timeout: int = 30,
    disable_media: bool = True,
    executable_path: Optional[str] = None,
    channel: Optional[str] = None,
    proxy: Optional[str] = None,
    headers: Optional[dict] = None,
    wait_for_selector: Optional[str] = None,
    wait_for_selector_timeout: int = 10,
) -> dict:
    """浏览器导航(支持 wait_for_selector 等 SPA 异步数据进 DOM)。"""
    if not url or not url.strip():
        return _err("url 不能为空")
    if wait_until not in ("load", "domcontentloaded", "networkidle", "commit"):
        return _err(f"wait_until 必须是 load/domcontentloaded/networkidle/commit,当前: {wait_until!r}")
    timeout = _normalize_timeout(timeout, default=30, max_v=120)
    ok, reason, _ = _validate_url(url)
    if not ok:
        return _err(f"SSRF 防护拒绝: {reason}")
    page, err = _ensure_browser_for_browser_tools(
        executable_path=executable_path, channel=channel, proxy=proxy,
    )
    if err is not None:
        return err
    if disable_media:
        try:
            page.route(
                "**/*.{png,jpg,jpeg,gif,webp,svg,ico,css,woff,woff2,ttf,otf,mp3,mp4,webm,ogg,wav,pdf}",
                lambda route: route.abort(),
            )
        except Exception:
            pass
    if headers:
        try:
            page.set_extra_http_headers(headers)
        except Exception:
            pass
    start = time.time()
    selector_waited = False
    try:
        resp = page.goto(url, timeout=timeout * 1000, wait_until=wait_until)
        duration_ms = int((time.time() - start) * 1000)
        if wait_for_selector:
            try:
                page.wait_for_selector(
                    wait_for_selector, timeout=wait_for_selector_timeout * 1000, state="visible",
                )
                selector_waited = True
            except PlaywrightTimeoutError:
                selector_waited = False
            except Exception:
                selector_waited = False
        try:
            title = page.title()
        except Exception:
            title = ""
        try:
            page_content = page.content()
        except Exception:
            page_content = ""
        status = resp.status if resp else 0
        if page_content:
            truncated_content, was_truncated = _truncate_middle(page_content, DEFAULT_MAX_CHARS)
        else:
            truncated_content = ""
            was_truncated = False
        wait_info = (
            f"  wait_for_selector={wait_for_selector}({wait_for_selector_timeout}s, "
            f"{'ok' if selector_waited else 'timeout'})"
            if wait_for_selector else ""
        )
        response_lines = [
            f"# {url}",
            f"# status={status}  wait_until={wait_until}  disable_media={disable_media}  "
            f"duration={duration_ms}ms{wait_info}",
            f"# title: {title}" if title else "# title: (无)",
            f"# html_chars={len(page_content)}  truncated={was_truncated}",
            "",
            truncated_content,
        ]
        return _ok("\n".join(response_lines), data={
            "url": url, "title": title, "status": status, "html": page_content,
            "truncated_html": truncated_content, "duration_ms": duration_ms,
            "truncated": was_truncated, "wait_until": wait_until,
            "wait_for_selector": wait_for_selector, "selector_waited": selector_waited,
        })
    except PlaywrightTimeoutError:
        duration_ms = int((time.time() - start) * 1000)
        try:
            title = page.title()
        except Exception:
            title = ""
        try:
            page_content = page.content()
        except Exception:
            page_content = ""
        return _ok(
            f"[TIMEOUT] 导航超时({timeout}s)但已部分加载\n"
            f"url={url}  duration={duration_ms}ms\n"
            f"title={title}  html_chars={len(page_content)}",
            data={"url": url, "title": title, "status": 0, "html": page_content,
                  "duration_ms": duration_ms, "timeout_rescued": True},
        )
    except Exception as e:
        return _err(f"导航异常: {type(e).__name__}: {e}", data={"duration_ms": int((time.time() - start) * 1000)})


def browser_navigate_back(timeout: int = DEFAULT_ACTION_TIMEOUT) -> dict:
    """浏览器后退。"""
    page, err = _ensure_browser_for_browser_tools()
    if err is not None:
        return err
    timeout = _normalize_timeout(timeout)
    start = time.time()
    try:
        page.go_back(timeout=timeout * 1000, wait_until="load")
        duration_ms = int((time.time() - start) * 1000)
        try:
            url = page.url
            title = page.title()
        except Exception:
            url = "(unknown)"
            title = ""
        return _ok(f"后退成功  url={url}  title={title}  duration={duration_ms}ms", data={
            "url": url, "title": title, "duration_ms": duration_ms,
        })
    except PlaywrightTimeoutError:
        return _err(f"后退超时({timeout}s)")
    except Exception as e:
        return _err(f"后退异常: {type(e).__name__}: {e}")


def browser_navigate_forward(timeout: int = DEFAULT_ACTION_TIMEOUT) -> dict:
    """浏览器前进。"""
    page, err = _ensure_browser_for_browser_tools()
    if err is not None:
        return err
    timeout = _normalize_timeout(timeout)
    start = time.time()
    try:
        page.go_forward(timeout=timeout * 1000, wait_until="load")
        duration_ms = int((time.time() - start) * 1000)
        try:
            url = page.url
            title = page.title()
        except Exception:
            url = "(unknown)"
            title = ""
        return _ok(f"前进成功  url={url}  title={title}  duration={duration_ms}ms", data={
            "url": url, "title": title, "duration_ms": duration_ms,
        })
    except PlaywrightTimeoutError:
        return _err(f"前进超时({timeout}s)")
    except Exception as e:
        return _err(f"前进异常: {type(e).__name__}: {e}")


def browser_navigate_reload(
    wait_until: str = "load",
    timeout: int = DEFAULT_ACTION_TIMEOUT,
) -> dict:
    """浏览器刷新。"""
    page, err = _ensure_browser_for_browser_tools()
    if err is not None:
        return err
    timeout = _normalize_timeout(timeout)
    start = time.time()
    try:
        page.reload(timeout=timeout * 1000, wait_until=wait_until)
        duration_ms = int((time.time() - start) * 1000)
        try:
            url = page.url
            title = page.title()
        except Exception:
            url = "(unknown)"
            title = ""
        return _ok(f"刷新成功  url={url}  title={title}  duration={duration_ms}ms", data={
            "url": url, "title": title, "duration_ms": duration_ms,
        })
    except PlaywrightTimeoutError:
        return _err(f"刷新超时({timeout}s)")
    except Exception as e:
        return _err(f"刷新异常: {type(e).__name__}: {e}")


def browser_close() -> dict:
    """关闭浏览器,释放 Playwright 资源。"""
    if not _BROWSER.is_running():
        return _ok("浏览器未启动,无需关闭")
    try:
        _BROWSER.close()
        return _ok("浏览器已关闭", data={"was_running": True})
    except Exception as e:
        return _err(f"关闭浏览器异常: {type(e).__name__}: {e}")


def browser_install(
    with_deps: bool = False,
    force: bool = False,
    timeout: int = BROWSER_INSTALL_TIMEOUT,
) -> dict:
    """联网下载 Chromium(2 分钟超时,失败时可设 PLAYWRIGHT_DOWNLOAD_HOST 国内镜像)。"""
    if not PLAYWRIGHT_AVAILABLE:
        return _err(
            "playwright 未安装。请先 `pip install playwright`,然后再调本工具。\n"
            "Windows: `pip install playwright` 后跑 `playwright install chromium`\n"
            "Linux:   `playwright install --with-deps chromium` (需 root)"
        )
    if timeout <= 0:
        timeout = BROWSER_INSTALL_TIMEOUT
    cmd = ["playwright", "install", "chromium"]
    if with_deps:
        cmd.append("--with-deps")
    if force:
        cmd.append("--force")
    start = time.time()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, shell=False)
        duration_ms = int((time.time() - start) * 1000)
        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
        if proc.returncode == 0:
            _BROWSER.close()
            installed = _find_playwright_chromium() or "(未找到)"
            return _ok(
                f"Chromium 安装成功\ncommand: {' '.join(cmd)}\n"
                f"installed_path: {installed}\nduration: {duration_ms}ms\n"
                f"stdout(last 500): {stdout[-500:]}",
                data={"command": cmd, "returncode": proc.returncode, "duration_ms": duration_ms,
                      "stdout": stdout, "stderr": stderr, "installed_path": installed},
            )
        return _err(
            f"Chromium 安装失败 (returncode={proc.returncode})\nstderr: {stderr[-1000:]}",
            data={"command": cmd, "returncode": proc.returncode, "duration_ms": duration_ms,
                  "stdout": stdout, "stderr": stderr},
        )
    except subprocess.TimeoutExpired:
        return _err(
            f"安装超时({timeout}s)。请检查网络(可设 PLAYWRIGHT_DOWNLOAD_HOST="
            f"https://npmmirror.com/mirrors/playwright 走国内镜像)后重试。",
            data={"command": cmd, "duration_ms": int((time.time() - start) * 1000)},
        )
    except FileNotFoundError as e:
        return _err(f"playwright 可执行文件不在 PATH 中: {e}。请先 `pip install playwright`。")
    except Exception as e:
        return _err(f"安装异常: {type(e).__name__}: {e}")


# ============================================================================
# 工具 11-20: 浏览器交互类
# ============================================================================
def _resolve_locator(page, selector: str, timeout_ms: int):
    """
    把 selector 转成 Playwright locator(支持 strict mode 重试)。

    Raises:
        PlaywrightTimeoutError: 超时
        Exception: 元素没找到(strict mode 违反等)
    """
    locator = page.locator(selector)
    # strict mode 检查:如果匹配 > 1 个,默认会报错,这里自动降级到 .first
    count = locator.count()
    if count == 0:
        raise PlaywrightTimeoutError(
            f"selector 匹配元素数 = 0: {selector!r}"
        )
    if count > 1:
        return locator.first
    return locator.first  # 即使只有 1 个,也用 .first 保持行为一致


def browser_click(
    selector: str,
    button: str = "left",
    modifiers: Optional[list[str]] = None,
    timeout: int = DEFAULT_ACTION_TIMEOUT,
    wait_after: bool = False,
    wait_for_selector: Optional[str] = None,
    wait_for_selector_timeout: int = 10,
) -> dict:
    """点击元素(支持左键/右键/中键 + modifier 键)。"""
    if not selector or not selector.strip():
        return _err("selector 不能为空")
    page, err = _ensure_browser_for_browser_tools()
    if err is not None:
        return err
    timeout = _normalize_timeout(timeout)
    # 可选:先等 selector 出现
    if wait_for_selector:
        try:
            page.wait_for_selector(wait_for_selector, timeout=wait_for_selector_timeout * 1000, state="visible")
        except PlaywrightTimeoutError:
            return _err(f"等待 wait_for_selector 超时: {wait_for_selector}")
    start = time.time()
    try:
        loc = _resolve_locator(page, selector, timeout * 1000)
        kwargs = {"button": button, "timeout": timeout * 1000}
        if modifiers:
            kwargs["modifiers"] = modifiers
        loc.click(**kwargs)
        duration_ms = int((time.time() - start) * 1000)
        if wait_after:
            try:
                page.wait_for_load_state("load", timeout=timeout * 1000)
            except Exception:
                pass
        return _ok(
            f"点击成功  selector={selector}  button={button}  "
            f"modifiers={modifiers or '[]'}  duration={duration_ms}ms",
            data={"selector": selector, "button": button, "modifiers": modifiers or [],
                  "duration_ms": duration_ms, "current_url": page.url},
        )
    except PlaywrightTimeoutError:
        return _err(f"点击超时({timeout}s): selector={selector!r}")
    except Exception as e:
        return _err(f"点击失败: {type(e).__name__}: {e}")


def browser_dblclick(
    selector: str,
    timeout: int = DEFAULT_ACTION_TIMEOUT,
) -> dict:
    """双击元素。"""
    if not selector or not selector.strip():
        return _err("selector 不能为空")
    page, err = _ensure_browser_for_browser_tools()
    if err is not None:
        return err
    timeout = _normalize_timeout(timeout)
    start = time.time()
    try:
        loc = _resolve_locator(page, selector, timeout * 1000)
        loc.dblclick(timeout=timeout * 1000)
        duration_ms = int((time.time() - start) * 1000)
        return _ok(
            f"双击成功  selector={selector}  duration={duration_ms}ms",
            data={"selector": selector, "duration_ms": duration_ms, "current_url": page.url},
        )
    except PlaywrightTimeoutError:
        return _err(f"双击超时({timeout}s): selector={selector!r}")
    except Exception as e:
        return _err(f"双击失败: {type(e).__name__}: {e}")


def browser_hover(
    selector: str,
    timeout: int = DEFAULT_ACTION_TIMEOUT,
) -> dict:
    """悬停元素(触发 hover 效果:下拉菜单 / tooltip / 懒加载)。"""
    if not selector or not selector.strip():
        return _err("selector 不能为空")
    page, err = _ensure_browser_for_browser_tools()
    if err is not None:
        return err
    timeout = _normalize_timeout(timeout)
    start = time.time()
    try:
        loc = _resolve_locator(page, selector, timeout * 1000)
        loc.hover(timeout=timeout * 1000)
        duration_ms = int((time.time() - start) * 1000)
        return _ok(
            f"悬停成功  selector={selector}  duration={duration_ms}ms",
            data={"selector": selector, "duration_ms": duration_ms, "current_url": page.url},
        )
    except PlaywrightTimeoutError:
        return _err(f"悬停超时({timeout}s): selector={selector!r}")
    except Exception as e:
        return _err(f"悬停失败: {type(e).__name__}: {e}")


def browser_fill(
    selector: str,
    value: str,
    timeout: int = DEFAULT_ACTION_TIMEOUT,
    clear_first: bool = True,
) -> dict:
    """设置 input/textarea 值(直接 .fill() 替换,会清空旧值)。"""
    if not selector or not selector.strip():
        return _err("selector 不能为空")
    page, err = _ensure_browser_for_browser_tools()
    if err is not None:
        return err
    timeout = _normalize_timeout(timeout)
    start = time.time()
    try:
        loc = _resolve_locator(page, selector, timeout * 1000)
        kwargs = {"timeout": timeout * 1000}
        # value 为空且 clear_first=True:等价于清空
        loc.fill(value, **kwargs)
        duration_ms = int((time.time() - start) * 1000)
        return _ok(
            f"fill 成功  selector={selector}  value_len={len(value)}  "
            f"clear_first={clear_first}  duration={duration_ms}ms",
            data={"selector": selector, "value": value, "value_len": len(value),
                  "duration_ms": duration_ms, "current_url": page.url},
        )
    except PlaywrightTimeoutError:
        return _err(f"fill 超时({timeout}s): selector={selector!r}")
    except Exception as e:
        return _err(f"fill 失败: {type(e).__name__}: {e}")


def browser_type(
    selector: str,
    text: str,
    delay_ms: int = 30,
    timeout: int = DEFAULT_ACTION_TIMEOUT,
) -> dict:
    """逐字输入(触发键盘事件,适合 IME / autocomplete / 实时校验场景)。"""
    if not selector or not selector.strip():
        return _err("selector 不能为空")
    page, err = _ensure_browser_for_browser_tools()
    if err is not None:
        return err
    timeout = _normalize_timeout(timeout)
    start = time.time()
    try:
        loc = _resolve_locator(page, selector, timeout * 1000)
        loc.press_sequentially(text, delay=delay_ms, timeout=timeout * 1000)
        duration_ms = int((time.time() - start) * 1000)
        return _ok(
            f"type 成功  selector={selector}  chars={len(text)}  "
            f"delay={delay_ms}ms  duration={duration_ms}ms",
            data={"selector": selector, "text": text, "chars": len(text),
                  "delay_ms": delay_ms, "duration_ms": duration_ms,
                  "current_url": page.url},
        )
    except PlaywrightTimeoutError:
        return _err(f"type 超时({timeout}s): selector={selector!r}")
    except Exception as e:
        return _err(f"type 失败: {type(e).__name__}: {e}")


def browser_press(
    key: str,
    selector: Optional[str] = None,
    timeout: int = DEFAULT_ACTION_TIMEOUT,
) -> dict:
    """
    按键(Enter/Tab/Escape/方向键等)。
    如果传 selector,先 focus 该元素再按;否则按当前焦点。
    """
    if not key or not key.strip():
        return _err("key 不能为空")
    page, err = _ensure_browser_for_browser_tools()
    if err is not None:
        return err
    timeout = _normalize_timeout(timeout)
    start = time.time()
    try:
        if selector:
            loc = _resolve_locator(page, selector, timeout * 1000)
            loc.press(key, timeout=timeout * 1000)
        else:
            page.keyboard.press(key)
        duration_ms = int((time.time() - start) * 1000)
        return _ok(
            f"按键成功  key={key!r}  selector={selector or '(focus)'}  "
            f"duration={duration_ms}ms",
            data={"key": key, "selector": selector, "duration_ms": duration_ms,
                  "current_url": page.url},
        )
    except PlaywrightTimeoutError:
        return _err(f"按键超时({timeout}s): key={key!r} selector={selector!r}")
    except Exception as e:
        return _err(f"按键失败: {type(e).__name__}: {e}")


def browser_select(
    selector: str,
    value: Optional[str] = None,
    label: Optional[str] = None,
    index: Optional[int] = None,
    timeout: int = DEFAULT_ACTION_TIMEOUT,
) -> dict:
    """选择 <select> 下拉框的选项(三种方式:value / label / index)。"""
    if not selector or not selector.strip():
        return _err("selector 不能为空")
    if value is None and label is None and index is None:
        return _err("value / label / index 必须传一个")
    page, err = _ensure_browser_for_browser_tools()
    if err is not None:
        return err
    timeout = _normalize_timeout(timeout)
    start = time.time()
    try:
        loc = _resolve_locator(page, selector, timeout * 1000)
        kwargs = {"timeout": timeout * 1000}
        if value is not None:
            kwargs["value"] = value
            sel_type = "value"
        elif label is not None:
            kwargs["label"] = label
            sel_type = "label"
        else:
            kwargs["index"] = index
            sel_type = "index"
        selected = loc.select_option(**kwargs)
        duration_ms = int((time.time() - start) * 1000)
        return _ok(
            f"select 成功  selector={selector}  type={sel_type}  "
            f"{sel_type}={kwargs[sel_type]!r}  selected={selected}  duration={duration_ms}ms",
            data={"selector": selector, "select_type": sel_type,
                  "value": value, "label": label, "index": index,
                  "selected_values": selected, "duration_ms": duration_ms,
                  "current_url": page.url},
        )
    except PlaywrightTimeoutError:
        return _err(f"select 超时({timeout}s): selector={selector!r}")
    except Exception as e:
        return _err(f"select 失败: {type(e).__name__}: {e}")


def browser_checkbox(
    selector: str,
    checked: bool = True,
    timeout: int = DEFAULT_ACTION_TIMEOUT,
) -> dict:
    """勾选/取消 checkbox 或 radio(checked=True 勾选,False 取消)。"""
    if not selector or not selector.strip():
        return _err("selector 不能为空")
    page, err = _ensure_browser_for_browser_tools()
    if err is not None:
        return err
    timeout = _normalize_timeout(timeout)
    start = time.time()
    try:
        loc = _resolve_locator(page, selector, timeout * 1000)
        if checked:
            loc.check(timeout=timeout * 1000)
            action = "check"
        else:
            loc.uncheck(timeout=timeout * 1000)
            action = "uncheck"
        duration_ms = int((time.time() - start) * 1000)
        return _ok(
            f"{action} 成功  selector={selector}  duration={duration_ms}ms",
            data={"selector": selector, "checked": checked, "action": action,
                  "duration_ms": duration_ms, "current_url": page.url},
        )
    except PlaywrightTimeoutError:
        return _err(f"checkbox {('check' if checked else 'uncheck')} 超时({timeout}s): "
                    f"selector={selector!r}")
    except Exception as e:
        return _err(f"checkbox 失败: {type(e).__name__}: {e}")


def browser_drag(
    source: str,
    target: str,
    source_position: Optional[dict] = None,
    target_position: Optional[dict] = None,
    timeout: int = DEFAULT_ACTION_TIMEOUT,
) -> dict:
    """拖拽(从 source selector 拖到 target selector)。"""
    if not source or not source.strip():
        return _err("source 不能为空")
    if not target or not target.strip():
        return _err("target 不能为空")
    page, err = _ensure_browser_for_browser_tools()
    if err is not None:
        return err
    timeout = _normalize_timeout(timeout)
    start = time.time()
    try:
        src_loc = _resolve_locator(page, source, timeout * 1000)
        tgt_loc = _resolve_locator(page, target, timeout * 1000)
        kwargs = {"timeout": timeout * 1000}
        if source_position:
            kwargs["source_position"] = source_position
        if target_position:
            kwargs["target_position"] = target_position
        src_loc.drag_to(tgt_loc, **kwargs)
        duration_ms = int((time.time() - start) * 1000)
        return _ok(
            f"drag 成功  {source} → {target}  duration={duration_ms}ms",
            data={"source": source, "target": target, "source_position": source_position,
                  "target_position": target_position, "duration_ms": duration_ms,
                  "current_url": page.url},
        )
    except PlaywrightTimeoutError:
        return _err(f"drag 超时({timeout}s): {source} → {target}")
    except Exception as e:
        return _err(f"drag 失败: {type(e).__name__}: {e}")


def browser_upload(
    selector: str,
    files: list[str],
    timeout: int = DEFAULT_ACTION_TIMEOUT,
) -> dict:
    """
    上传文件(给 input[type=file] 设文件路径)。
    files: 绝对路径列表(可多选)。
    """
    if not selector or not selector.strip():
        return _err("selector 不能为空")
    if not files:
        return _err("files 不能为空(至少一个文件绝对路径)")
    # 检查文件存在
    missing = [f for f in files if not os.path.isfile(f)]
    if missing:
        return _err(f"文件不存在: {missing}")
    page, err = _ensure_browser_for_browser_tools()
    if err is not None:
        return err
    timeout = _normalize_timeout(timeout)
    start = time.time()
    try:
        loc = _resolve_locator(page, selector, timeout * 1000)
        loc.set_input_files(files, timeout=timeout * 1000)
        duration_ms = int((time.time() - start) * 1000)
        return _ok(
            f"upload 成功  selector={selector}  files={len(files)}  duration={duration_ms}ms",
            data={"selector": selector, "files": files, "file_count": len(files),
                  "duration_ms": duration_ms, "current_url": page.url},
        )
    except PlaywrightTimeoutError:
        return _err(f"upload 超时({timeout}s): selector={selector!r}")
    except Exception as e:
        return _err(f"upload 失败: {type(e).__name__}: {e}")


# ============================================================================
# 工具 21-23: 浏览器提取类
# ============================================================================
def browser_query_dom(
    url: Optional[str] = None,
    selector: Optional[str] = None,
    extract: str = "text",
    attribute: Optional[str] = None,
    all_matches: bool = False,
    wait_for_selector: Optional[str] = None,
    wait_for_selector_timeout: int = 10,
    timeout: int = 30,
    executable_path: Optional[str] = None,
) -> dict:
    """用 CSS selector 从页面提取 DOM 内容(4 种 extract 模式)。"""
    if not selector or not selector.strip():
        return _err("selector 不能为空")
    if extract not in ("text", "html", "attribute", "count"):
        return _err(f"extract 必须是 text/html/attribute/count,当前: {extract!r}")
    if extract == "attribute" and not attribute:
        return _err("extract='attribute' 时必须指定 attribute 参数")
    page, err = _ensure_browser_for_browser_tools(executable_path=executable_path)
    if err is not None:
        return err
    if url and url.strip():
        ok, reason, _ = _validate_url(url)
        if not ok:
            return _err(f"SSRF 防护拒绝: {reason}")
        try:
            page.goto(url, timeout=timeout * 1000, wait_until="networkidle")
        except Exception as e:
            return _err(f"导航失败: {type(e).__name__}: {e}", data={"url": url})
    actual_wait = wait_for_selector or selector
    try:
        page.wait_for_selector(
            actual_wait, timeout=wait_for_selector_timeout * 1000, state="visible",
        )
    except PlaywrightTimeoutError:
        return _err(
            f"等待 selector 超时({wait_for_selector_timeout}s): {actual_wait}",
            data={"selector": actual_wait, "url": url or "(使用现有 page)"},
        )
    except Exception as e:
        return _err(f"等待 selector 失败: {type(e).__name__}: {e}")
    try:
        if extract == "count":
            count = page.locator(selector).count()
            return _ok(
                f"匹配数量: {count}  (selector: {selector})",
                data={"selector": selector, "extract": extract, "count": count,
                      "result": count, "url": url or page.url},
            )
        if all_matches:
            locators = page.locator(selector).all()
            results: list[str] = []
            for loc in locators:
                if extract == "text":
                    val = loc.inner_text()
                elif extract == "html":
                    val = loc.evaluate("el => el.innerHTML")
                else:
                    val = loc.get_attribute(attribute) or ""
                results.append(val)
            content = "\n---\n".join(results)
            return _ok(
                f"# {len(results)} 个匹配  (selector: {selector})\n\n{content}",
                data={"selector": selector, "extract": extract, "attribute": attribute,
                      "count": len(results), "result": results,
                      "url": url or page.url},
            )
        locator = page.locator(selector).first
        if extract == "text":
            val = locator.inner_text()
        elif extract == "html":
            val = locator.evaluate("el => el.innerHTML")
        else:
            val = locator.get_attribute(attribute) or ""
        return _ok(
            f"# selector: {selector}\n# extract: {extract}"
            f"{f'  attribute: {attribute}' if attribute else ''}\n\n{val}",
            data={"selector": selector, "extract": extract, "attribute": attribute,
                  "count": 1, "result": val, "url": url or page.url},
        )
    except Exception as e:
        return _err(f"DOM 提取失败: {type(e).__name__}: {e}", data={"selector": selector})


def browser_evaluate(
    expression: str,
    arg: Optional[Any] = None,
    url: Optional[str] = None,
    timeout: int = 30,
    wait_for_selector: Optional[str] = None,
    wait_for_selector_timeout: int = 10,
    executable_path: Optional[str] = None,
) -> dict:
    """
    在浏览器上下文执行任意 JS(返回 JSON 可序列化的结果)。

    Args:
        expression: JS 表达式或函数(字符串)
        arg: 可选参数,会作为 page.evaluate(expression, arg) 第二个参数传入
        url: 可选;先导航
        timeout: 导航超时(秒)
        wait_for_selector: 等 selector 出现再执行(SPA 异步场景)
        wait_for_selector_timeout: 等待 selector 超时(秒)
        executable_path: 本机 Chrome 路径
    """
    if not expression or not expression.strip():
        return _err("expression 不能为空")
    page, err = _ensure_browser_for_browser_tools(executable_path=executable_path)
    if err is not None:
        return err
    if url and url.strip():
        ok, reason, _ = _validate_url(url)
        if not ok:
            return _err(f"SSRF 防护拒绝: {reason}")
        try:
            page.goto(url, timeout=timeout * 1000, wait_until="networkidle")
        except Exception as e:
            return _err(f"导航失败: {type(e).__name__}: {e}", data={"url": url})
    if wait_for_selector:
        try:
            page.wait_for_selector(wait_for_selector, timeout=wait_for_selector_timeout * 1000, state="visible")
        except PlaywrightTimeoutError:
            return _err(f"等待 wait_for_selector 超时: {wait_for_selector}")
    start = time.time()
    try:
        if arg is None:
            result = page.evaluate(expression)
        else:
            result = page.evaluate(expression, arg)
        duration_ms = int((time.time() - start) * 1000)
        # 序列化结果(确保 JSON 可序列化)
        try:
            result_repr = json.loads(json.dumps(result, ensure_ascii=False, default=str))
        except Exception:
            result_repr = str(result)
        # 单值 vs 多值
        if isinstance(result_repr, (str, int, float, bool, type(None))):
            content = f"# 表达式: {expression[:200]!r}\n# 结果: {result_repr!r}\n"
        else:
            content = (
                f"# 表达式: {expression[:200]!r}\n# 结果(type={type(result_repr).__name__}):\n"
                f"{json.dumps(result_repr, ensure_ascii=False, indent=2)}"
            )
        return _ok(content, data={
            "expression": expression, "arg": arg, "result": result_repr,
            "duration_ms": duration_ms, "url": page.url,
        })
    except Exception as e:
        return _err(f"JS 执行异常: {type(e).__name__}: {e}")


def browser_console_logs(
    action: str = "get",
    clear: bool = False,
) -> dict:
    """
    获取浏览器 console 日志(action: get | clear)。

    日志是 BrowserManager 在 console 事件时自动收集的(从浏览器启动开始累积)。
    clear=True 时清空累积。
    """
    if action not in ("get", "clear"):
        return _err(f"action 必须是 get/clear,当前: {action!r}")
    if action == "clear":
        _BROWSER.clear_console_logs()
        return _ok("console 日志已清空", data={"action": "clear", "count_before": 0})
    logs = _BROWSER.get_console_logs()
    if clear:
        _BROWSER.clear_console_logs()
    if not logs:
        return _ok("(无 console 日志 — 浏览器可能未启动,或访问的页面没产生 console)", data={
            "logs": [], "count": 0, "url": _BROWSER._page.url if _BROWSER.is_running() else None,
        })
    content = f"# {len(logs)} 条 console 日志\n\n" + "\n".join(logs)
    content, truncated = _truncate_middle(content, DEFAULT_MAX_CHARS)
    return _ok(content, data={
        "logs": logs, "count": len(logs), "truncated": truncated,
        "url": _BROWSER._page.url if _BROWSER.is_running() else None,
    })


# ============================================================================
# 工具 24-26: 浏览器资源类
# ============================================================================
def browser_screenshot(
    url: Optional[str] = None,
    selector: Optional[str] = None,
    full_page: bool = True,
    image_type: str = "jpeg",
    quality: int = 80,
    max_size_mb: float = SCREENSHOT_MAX_SIZE_MB,
    wait_until: str = "load",
    timeout: int = 30,
    wait_for_selector: Optional[str] = None,
    wait_for_selector_timeout: int = 10,
    executable_path: Optional[str] = None,
) -> dict:
    """
    浏览器截图(返回 base64,默认 jpeg quality 80,size 上限 1MB)。
    url 可选 — 不传则截当前 page(可先 browser_navigate 一下)。
    """
    if image_type not in ("png", "jpeg"):
        return _err(f"image_type 必须是 png/jpeg,当前: {image_type!r}")
    if not (1 <= quality <= 100):
        quality = 80
    if max_size_mb <= 0:
        max_size_mb = SCREENSHOT_MAX_SIZE_MB
    page, err = _ensure_browser_for_browser_tools(executable_path=executable_path)
    if err is not None:
        return err
    # 如果传了 url,先导航
    if url and url.strip():
        ok, reason, _ = _validate_url(url)
        if not ok:
            return _err(f"SSRF 防护拒绝: {reason}")
        try:
            page.goto(url, timeout=timeout * 1000, wait_until=wait_until)
        except Exception as e:
            return _err(f"导航失败: {type(e).__name__}: {e}", data={"url": url})
    # wait_for_selector
    if wait_for_selector:
        try:
            page.wait_for_selector(
                wait_for_selector, timeout=wait_for_selector_timeout * 1000, state="visible",
            )
        except PlaywrightTimeoutError:
            return _err(f"等待 wait_for_selector 超时: {wait_for_selector}")
    start = time.time()
    try:
        kwargs: dict = {
            "type": image_type,
            "full_page": full_page and not selector,
        }
        if image_type == "jpeg":
            kwargs["quality"] = quality
        if selector:
            try:
                locator = page.locator(selector)
                if locator.count() > 1:
                    locator = locator.first
                buf = locator.screenshot(**kwargs)
            except Exception:
                locator = page.locator(selector).first
                buf = locator.screenshot(**kwargs)
        else:
            buf = page.screenshot(**kwargs)
        b64 = base64.b64encode(buf).decode("ascii")
        size_mb = len(b64) / (1024 * 1024)
        duration_ms = int((time.time() - start) * 1000)
        if size_mb > max_size_mb:
            return _err(
                f"截图 base64 超过 size 上限: {size_mb:.2f}MB > {max_size_mb}MB。"
                f"请用 selector 截区域 / 改用 jpeg + 低 quality / 降低 max_size_mb。"
            )
        response_lines = [
            f"# {url or page.url}",
            f"# screenshot: type={image_type}  quality={quality}  size={size_mb:.2f}MB  "
            f"duration={duration_ms}ms",
            f"# base64_chars={len(b64)}  full_page={full_page and not selector}  "
            f"selector={selector or '(none)'}",
            "",
            f"[Screenshot base64 in data.image_base64 字段,长度 {len(b64)} 字符]",
        ]
        return _ok("\n".join(response_lines), data={
            "url": url or page.url, "image_type": image_type, "quality": quality,
            "size_mb": round(size_mb, 3), "image_base64": b64, "selector": selector,
            "full_page": full_page and not selector, "duration_ms": duration_ms,
        })
    except PlaywrightTimeoutError:
        return _err(f"截图超时({timeout}s): {url or page.url}")
    except Exception as e:
        return _err(f"截图异常: {type(e).__name__}: {e}")


def browser_pdf_save(
    url: Optional[str] = None,
    path: Optional[str] = None,
    format: str = "A4",
    margin: Optional[dict] = None,
    timeout: int = 30,
    wait_for_selector: Optional[str] = None,
    wait_for_selector_timeout: int = 10,
    executable_path: Optional[str] = None,
) -> dict:
    """
    把当前 page(或 url)另存为 PDF。
    注意:headless=True 模式才能用 page.pdf()(Chrome 限制)。
    """
    if not path:
        return _err("path 不能为空(目标文件绝对路径)")
    if format not in ("Letter", "Legal", "Tabloid", "Ledger", "A0", "A1", "A2", "A3", "A4", "A5", "A6"):
        return _err(f"format 不支持: {format!r}")
    if margin and not all(k in margin for k in ("top", "bottom", "left", "right")):
        return _err("margin 必须是 {top, bottom, left, right} 字典(或 None)")
    page, err = _ensure_browser_for_browser_tools(executable_path=executable_path)
    if err is not None:
        return err
    if url and url.strip():
        ok, reason, _ = _validate_url(url)
        if not ok:
            return _err(f"SSRF 防护拒绝: {reason}")
        try:
            page.goto(url, timeout=timeout * 1000, wait_until="networkidle")
        except Exception as e:
            return _err(f"导航失败: {type(e).__name__}: {e}", data={"url": url})
    if wait_for_selector:
        try:
            page.wait_for_selector(
                wait_for_selector, timeout=wait_for_selector_timeout * 1000, state="visible",
            )
        except PlaywrightTimeoutError:
            return _err(f"等待 wait_for_selector 超时: {wait_for_selector}")
    target_path = Path(path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    start = time.time()
    try:
        pdf_kwargs = {
            "path": str(target_path),
            "format": format,
        }
        if margin:
            pdf_kwargs["margin"] = margin
        page.pdf(**pdf_kwargs)
        duration_ms = int((time.time() - start) * 1000)
        size_bytes = target_path.stat().st_size if target_path.exists() else 0
        return _ok(
            f"PDF 保存成功  path={target_path}  size={size_bytes}  format={format}  "
            f"duration={duration_ms}ms",
            data={"path": str(target_path), "size_bytes": size_bytes, "format": format,
                  "duration_ms": duration_ms, "url": page.url},
        )
    except Exception as e:
        return _err(f"PDF 保存失败: {type(e).__name__}: {e}", data={"path": str(target_path)})


def browser_cookies(
    action: str = "get",
    cookies: Optional[list[dict]] = None,
    urls: Optional[list[str]] = None,
    timeout: int = 30,
    url: Optional[str] = None,
    wait_for_selector: Optional[str] = None,
    wait_for_selector_timeout: int = 10,
    executable_path: Optional[str] = None,
) -> dict:
    """
    Cookie 管理(action: get | set | clear)。

    get: 获取所有 cookies(或指定 urls 的)
    set: 设置 cookies(必须传 cookies 参数,格式 [{name, value, domain, path, ...}])
    clear: 清空所有 cookies
    """
    if action not in ("get", "set", "clear"):
        return _err(f"action 必须是 get/set/clear,当前: {action!r}")
    if action == "set" and not cookies:
        return _err("action='set' 时必须传 cookies 参数")
    page, err = _ensure_browser_for_browser_tools(executable_path=executable_path)
    if err is not None:
        return err
    # 导航(让 context 有 origin)
    if url and url.strip():
        ok, reason, _ = _validate_url(url)
        if not ok:
            return _err(f"SSRF 防护拒绝: {reason}")
        try:
            page.goto(url, timeout=timeout * 1000, wait_until="domcontentloaded")
        except Exception as e:
            return _err(f"导航失败: {type(e).__name__}: {e}", data={"url": url})
    if wait_for_selector:
        try:
            page.wait_for_selector(wait_for_selector, timeout=wait_for_selector_timeout * 1000, state="visible")
        except PlaywrightTimeoutError:
            return _err(f"等待 wait_for_selector 超时: {wait_for_selector}")
    start = time.time()
    try:
        if action == "get":
            if urls:
                # 验证 URL
                for u in urls:
                    ok, reason, _ = _validate_url(u)
                    if not ok:
                        return _err(f"URL 拒绝: {reason}")
                cookie_list = page.context.cookies(*urls)
            else:
                cookie_list = page.context.cookies()
            duration_ms = int((time.time() - start) * 1000)
            if not cookie_list:
                return _ok(
                    "(无 cookie)", data={"cookies": [], "count": 0,
                                          "duration_ms": duration_ms, "url": page.url},
                )
            content = f"# {len(cookie_list)} 个 cookie\n\n"
            for c in cookie_list:
                content += (
                    f"- {c.get('name')}={c.get('value')}  domain={c.get('domain')}  "
                    f"path={c.get('path')}  "
                    f"{'httpOnly' if c.get('httpOnly') else ''}  "
                    f"{'secure' if c.get('secure') else ''}\n"
                )
            return _ok(content, data={"cookies": cookie_list, "count": len(cookie_list),
                                      "duration_ms": duration_ms, "url": page.url})
        if action == "set":
            # 验证 cookies 格式
            for ck in cookies:
                if "name" not in ck or "value" not in ck:
                    return _err("每个 cookie 必须含 name 和 value 字段")
                # 如果有 url,验证 SSRF
                if "url" in ck:
                    ok, reason, _ = _validate_url(ck["url"])
                    if not ok:
                        return _err(f"cookie url 拒绝: {reason}")
                elif "domain" not in ck:
                    return _err("cookie 必须含 url 或 domain 之一")
            page.context.add_cookies(cookies)
            duration_ms = int((time.time() - start) * 1000)
            return _ok(
                f"已设置 {len(cookies)} 个 cookie",
                data={"count": len(cookies), "duration_ms": duration_ms, "url": page.url},
            )
        # action == "clear"
        page.context.clear_cookies()
        duration_ms = int((time.time() - start) * 1000)
        return _ok("cookie 已清空", data={"action": "clear", "duration_ms": duration_ms,
                                          "url": page.url})
    except Exception as e:
        return _err(f"cookie 操作失败: {type(e).__name__}: {e}")


# ============================================================================
# 工具 27-28: 浏览器等待类
# ============================================================================
def browser_wait_for_text(
    text: str,
    url: Optional[str] = None,
    timeout: int = 30,
    exact: bool = False,
    case_sensitive: bool = False,
    wait_for_selector: Optional[str] = None,
    wait_for_selector_timeout: int = 10,
    executable_path: Optional[str] = None,
) -> dict:
    """
    等某段文字出现在 page 上(对登录成功跳转、AJAX 响应等场景很常用)。

    Args:
        text: 要等的文字
        url: 可选;先导航
        timeout: 等待超时秒数
        exact: True=完全匹配,False=子串匹配(默认)
        case_sensitive: True=大小写敏感(默认 False)
    """
    if not text or not text.strip():
        return _err("text 不能为空")
    page, err = _ensure_browser_for_browser_tools(executable_path=executable_path)
    if err is not None:
        return err
    if url and url.strip():
        ok, reason, _ = _validate_url(url)
        if not ok:
            return _err(f"SSRF 防护拒绝: {reason}")
        try:
            page.goto(url, timeout=timeout * 1000, wait_until="networkidle")
        except Exception as e:
            return _err(f"导航失败: {type(e).__name__}: {e}", data={"url": url})
    # 如果传了 wait_for_selector,先等这个;但 browser_wait_for_text 主要靠文字,所以 wait_for_selector 可选
    if wait_for_selector:
        try:
            page.wait_for_selector(
                wait_for_selector, timeout=wait_for_selector_timeout * 1000, state="visible",
            )
        except PlaywrightTimeoutError:
            return _err(f"等待 wait_for_selector 超时: {wait_for_selector}")
    timeout_ms = timeout * 1000
    start = time.time()
    try:
        # 用 JS 在 page.evaluate 里 wait 文字
        expr = """
        ([text, exact, caseSensitive, timeoutMs]) => {
            return new Promise((resolve, reject) => {
                const target = text;
                const start = Date.now();
                function check() {
                    const body = document.body ? document.body.innerText : '';
                    const haystack = caseSensitive ? body : body.toLowerCase();
                    const needle = caseSensitive ? target : target.toLowerCase();
                    let found;
                    if (exact) {
                        found = haystack === needle;
                    } else {
                        found = haystack.includes(needle);
                    }
                    if (found) {
                        resolve({found: true, elapsed_ms: Date.now() - start});
                        return;
                    }
                    if (Date.now() - start > timeoutMs) {
                        resolve({found: false, elapsed_ms: Date.now() - start});
                        return;
                    }
                    setTimeout(check, 100);
                }
                check();
            });
        }
        """
        result = page.evaluate(expr, [text, exact, case_sensitive, timeout_ms])
        duration_ms = int((time.time() - start) * 1000)
        if result and result.get("found"):
            return _ok(
                f"等到了文字  text={text!r}  elapsed={result['elapsed_ms']}ms  "
                f"duration={duration_ms}ms",
                data={"text": text, "found": True,
                      "elapsed_ms": result["elapsed_ms"], "duration_ms": duration_ms,
                      "url": page.url},
            )
        return _err(
            f"等待文字超时({timeout}s): {text!r}",
            data={"text": text, "found": False, "duration_ms": duration_ms, "url": page.url},
        )
    except Exception as e:
        return _err(f"wait_for_text 失败: {type(e).__name__}: {e}")


def browser_wait_for_url(
    pattern: str,
    url: Optional[str] = None,
    timeout: int = 30,
    wait_until: str = "load",
    executable_path: Optional[str] = None,
) -> dict:
    """
    等 URL 变化(支持 glob 模式: ** 任意路径段, * 任意字符)。

    Args:
        pattern: URL glob 模式,例如 "**/dashboard" / "https://example.com/success*"
        url: 可选;先导航到这个 URL
        timeout: 等待超时秒数
        wait_until: 导航 wait_until 策略
    """
    if not pattern or not pattern.strip():
        return _err("pattern 不能为空")
    page, err = _ensure_browser_for_browser_tools(executable_path=executable_path)
    if err is not None:
        return err
    if url and url.strip():
        ok, reason, _ = _validate_url(url)
        if not ok:
            return _err(f"SSRF 防护拒绝: {reason}")
        try:
            page.goto(url, timeout=timeout * 1000, wait_until=wait_until)
        except Exception as e:
            return _err(f"导航失败: {type(e).__name__}: {e}", data={"url": url})
    timeout_ms = timeout * 1000
    start = time.time()
    try:
        page.wait_for_url(pattern, timeout=timeout_ms, wait_until="commit")
        duration_ms = int((time.time() - start) * 1000)
        return _ok(
            f"URL 匹配  pattern={pattern!r}  url={page.url}  duration={duration_ms}ms",
            data={"pattern": pattern, "url": page.url, "duration_ms": duration_ms,
                  "matched": True},
        )
    except PlaywrightTimeoutError:
        duration_ms = int((time.time() - start) * 1000)
        return _err(
            f"等待 URL 超时({timeout}s): pattern={pattern!r}  current={page.url}",
            data={"pattern": pattern, "url": page.url, "duration_ms": duration_ms,
                  "matched": False},
        )
    except Exception as e:
        return _err(f"wait_for_url 失败: {type(e).__name__}: {e}")


# ============================================================================
# 工具 schema (OpenAI Chat Completions 风格) — 28 个工具
# ============================================================================
TOOL_SCHEMAS: list[dict] = [
    # ===== HTTP 路线 (4) =====
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "多搜索引擎并行搜索(自动判断墙内/墙外)。"
                "中国大陆:百度+搜狗+360;非中国大陆:Google+Bing+Yahoo。"
                "region='auto'/'cn'/'global'。返回 Markdown 文本 + 结构化 results 数组。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词"},
                    "num_results": {"type": "integer", "description": "每个引擎结果数(默认 10,最大 30)"},
                    "region": {"type": "string", "enum": ["auto", "cn", "global"],
                               "description": "区域(默认 auto)"},
                    "timeout": {"type": "integer", "description": "单个引擎超时秒数(默认 10)"},
                },
                "required": ["query"], "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search_diag",
            "description": (
                "诊断当前系统区域(中国大陆/全球)和生效的搜索引擎。"
                "返回系统信息(tzname/locale/TZ/Win32 GeoID)和判定理由。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "force_region": {"type": "string", "enum": ["cn", "global", "auto"]},
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_url",
            "description": "HTTP 抓单 URL(零浏览器依赖)。Readability 抽正文 + Markdown 转换。SSRF 防护 3 道关。",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "http/https URL"},
                    "format": {"type": "string", "enum": ["html", "markdown", "text", "json"]},
                    "extract_content": {"type": "boolean"},
                    "max_chars": {"type": "integer"},
                    "timeout": {"type": "integer"},
                    "headers": {"type": "object"},
                },
                "required": ["url"], "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_urls",
            "description": "HTTP 并行抓多 URL(并发 5)。单个失败不影响整体。",
            "parameters": {
                "type": "object",
                "properties": {
                    "urls": {"type": "array", "items": {"type": "string"}},
                    "format": {"type": "string", "enum": ["html", "markdown", "text", "json"]},
                    "extract_content": {"type": "boolean"},
                    "max_chars": {"type": "integer"},
                    "timeout": {"type": "integer"},
                    "max_concurrent": {"type": "integer"},
                },
                "required": ["urls"], "additionalProperties": False,
            },
        },
    },
    # ===== 导航类 (5) =====
    {
        "type": "function",
        "function": {
            "name": "browser_navigate",
            "description": (
                "Playwright 浏览器导航。支持 wait_for_selector(等数据进 DOM,适合 SPA 异步 fetch)。"
                "默认 disable_media=True(屏蔽图片/CSS/字体)。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "wait_until": {"type": "string", "enum": ["load", "domcontentloaded", "networkidle", "commit"]},
                    "timeout": {"type": "integer", "description": "导航超时秒数(默认 30,最大 120)"},
                    "disable_media": {"type": "boolean"},
                    "executable_path": {"type": "string"},
                    "channel": {"type": "string", "enum": ["chrome", "msedge", "chrome-beta", "msedge-beta", "msedge-dev"]},
                    "proxy": {"type": "string"},
                    "headers": {"type": "object"},
                    "wait_for_selector": {"type": "string",
                        "description": "等指定 CSS selector 出现再抓 content(SPA 异步 fetch)"},
                    "wait_for_selector_timeout": {"type": "integer"},
                },
                "required": ["url"], "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_navigate_back",
            "description": "浏览器后退。",
            "parameters": {
                "type": "object",
                "properties": {"timeout": {"type": "integer"}},
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_navigate_forward",
            "description": "浏览器前进。",
            "parameters": {
                "type": "object",
                "properties": {"timeout": {"type": "integer"}},
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_navigate_reload",
            "description": "浏览器刷新。",
            "parameters": {
                "type": "object",
                "properties": {
                    "wait_until": {"type": "string", "enum": ["load", "domcontentloaded", "networkidle", "commit"]},
                    "timeout": {"type": "integer"},
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_close",
            "description": "关闭浏览器,释放 Playwright 进程和内存。",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_install",
            "description": "联网下载 Chromium(2 分钟超时)。失败时可设 PLAYWRIGHT_DOWNLOAD_HOST 走国内镜像。",
            "parameters": {
                "type": "object",
                "properties": {
                    "with_deps": {"type": "boolean"},
                    "force": {"type": "boolean"},
                    "timeout": {"type": "integer"},
                },
                "additionalProperties": False,
            },
        },
    },
    # ===== 交互类 (10) =====
    {
        "type": "function",
        "function": {
            "name": "browser_click",
            "description": "点击元素(支持左/右/中键 + modifiers: Alt/Control/Meta/Shift 列表)。",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS selector"},
                    "button": {"type": "string", "enum": ["left", "right", "middle"], "description": "鼠标键(默认 left)"},
                    "modifiers": {"type": "array", "items": {"type": "string", "enum": ["Alt", "Control", "Meta", "Shift"]},
                                  "description": "modifier 键(按住时点击)"},
                    "timeout": {"type": "integer", "description": "默认 15,最大 120"},
                    "wait_after": {"type": "boolean", "description": "点击后等 load 事件(默认 False)"},
                    "wait_for_selector": {"type": "string"},
                    "wait_for_selector_timeout": {"type": "integer"},
                },
                "required": ["selector"], "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_dblclick",
            "description": "双击元素。",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string"},
                    "timeout": {"type": "integer"},
                },
                "required": ["selector"], "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_hover",
            "description": "悬停元素(触发 hover 效果:下拉菜单/tooltip/懒加载)。",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string"},
                    "timeout": {"type": "integer"},
                },
                "required": ["selector"], "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_fill",
            "description": "设置 input/textarea 值(直接 .fill() 替换,会清空旧值)。",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string"},
                    "value": {"type": "string", "description": "要填的值(空字符串=清空)"},
                    "timeout": {"type": "integer"},
                    "clear_first": {"type": "boolean", "description": "填之前先清空(默认 True)"},
                },
                "required": ["selector", "value"], "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_type",
            "description": "逐字输入(触发键盘事件,适合 IME / autocomplete / 实时校验场景)。",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string"},
                    "text": {"type": "string"},
                    "delay_ms": {"type": "integer", "description": "每字间隔毫秒(默认 30)"},
                    "timeout": {"type": "integer"},
                },
                "required": ["selector", "text"], "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_press",
            "description": (
                "按键(Enter/Tab/Escape/方向键等)。"
                "传 selector=先 focus 该元素再按;不传=按当前焦点。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "按键名,例如 'Enter' / 'Tab' / 'Escape' / 'ArrowDown'"},
                    "selector": {"type": "string"},
                    "timeout": {"type": "integer"},
                },
                "required": ["key"], "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_select",
            "description": "选择 <select> 下拉框的选项(三种方式:value / label / index)。",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string"},
                    "value": {"type": "string", "description": "按 value 属性选"},
                    "label": {"type": "string", "description": "按可见文本选"},
                    "index": {"type": "integer", "description": "按 index 选(0-based)"},
                    "timeout": {"type": "integer"},
                },
                "required": ["selector"], "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_checkbox",
            "description": "勾选/取消 checkbox 或 radio。",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string"},
                    "checked": {"type": "boolean", "description": "True=勾选,False=取消(默认 True)"},
                    "timeout": {"type": "integer"},
                },
                "required": ["selector"], "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_drag",
            "description": "拖拽(从 source selector 拖到 target selector)。",
            "parameters": {
                "type": "object",
                "properties": {
                    "source": {"type": "string", "description": "源元素 selector"},
                    "target": {"type": "string", "description": "目标元素 selector"},
                    "source_position": {"type": "object", "description": "{x, y} 源元素内位置偏移"},
                    "target_position": {"type": "object", "description": "{x, y} 目标元素内位置偏移"},
                    "timeout": {"type": "integer"},
                },
                "required": ["source", "target"], "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_upload",
            "description": "上传文件(给 input[type=file] 设文件路径,files 是绝对路径列表)。",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string"},
                    "files": {"type": "array", "items": {"type": "string"}, "description": "文件绝对路径列表"},
                    "timeout": {"type": "integer"},
                },
                "required": ["selector", "files"], "additionalProperties": False,
            },
        },
    },
    # ===== 提取类 (3) =====
    {
        "type": "function",
        "function": {
            "name": "browser_query_dom",
            "description": (
                "用 CSS selector 从页面提取 DOM 内容。extract 模式:"
                "text(可见文本) / html(内部 HTML) / attribute(属性,需 attribute 参数) / count(数量)。"
                "all_matches=True 返回所有匹配。wait_for_selector 让工具等数据进 DOM 再抓。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "可选;不传则用当前 page"},
                    "selector": {"type": "string"},
                    "extract": {"type": "string", "enum": ["text", "html", "attribute", "count"]},
                    "attribute": {"type": "string"},
                    "all_matches": {"type": "boolean"},
                    "wait_for_selector": {"type": "string"},
                    "wait_for_selector_timeout": {"type": "integer"},
                    "timeout": {"type": "integer"},
                    "executable_path": {"type": "string"},
                },
                "required": ["selector"], "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_evaluate",
            "description": (
                "在浏览器上下文执行任意 JS(返回 JSON 可序列化结果)。"
                "拿 JS 变量、调前端函数、复杂提取都能用。arg 可选,作为 evaluate 第二个参数传入。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {"type": "string", "description": "JS 表达式或函数"},
                    "arg": {"description": "可选参数(JSON 可序列化)"},
                    "url": {"type": "string"},
                    "timeout": {"type": "integer"},
                    "wait_for_selector": {"type": "string"},
                    "wait_for_selector_timeout": {"type": "integer"},
                    "executable_path": {"type": "string"},
                },
                "required": ["expression"], "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_console_logs",
            "description": "获取浏览器 console 日志(action=get|clear)。日志从浏览器启动开始累积。",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["get", "clear"], "description": "默认 get"},
                    "clear": {"type": "boolean", "description": "读取后清空(默认 False)"},
                },
                "additionalProperties": False,
            },
        },
    },
    # ===== 资源类 (3) =====
    {
        "type": "function",
        "function": {
            "name": "browser_screenshot",
            "description": "浏览器截图(返回 base64,默认 jpeg quality 80,size 上限 1MB)。",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "可选;不传则截当前 page"},
                    "selector": {"type": "string"},
                    "full_page": {"type": "boolean"},
                    "image_type": {"type": "string", "enum": ["png", "jpeg"]},
                    "quality": {"type": "integer"},
                    "max_size_mb": {"type": "number"},
                    "wait_until": {"type": "string", "enum": ["load", "domcontentloaded", "networkidle", "commit"]},
                    "timeout": {"type": "integer"},
                    "wait_for_selector": {"type": "string"},
                    "wait_for_selector_timeout": {"type": "integer"},
                    "executable_path": {"type": "string"},
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_pdf_save",
            "description": "把当前 page(或 url)另存为 PDF(headless 必须 True)。",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "path": {"type": "string", "description": "目标 PDF 绝对路径"},
                    "format": {"type": "string", "enum": ["Letter", "Legal", "Tabloid", "Ledger",
                                                        "A0", "A1", "A2", "A3", "A4", "A5", "A6"]},
                    "margin": {"type": "object", "description": "{top, bottom, left, right} 字符串(带单位如 '1cm')"},
                    "timeout": {"type": "integer"},
                    "wait_for_selector": {"type": "string"},
                    "wait_for_selector_timeout": {"type": "integer"},
                    "executable_path": {"type": "string"},
                },
                "required": ["path"], "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_cookies",
            "description": "Cookie 管理(action=get|set|clear)。get 返回当前 context 所有 cookies;set 需要 cookies 列表。",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["get", "set", "clear"]},
                    "cookies": {"type": "array", "items": {"type": "object"},
                                "description": "action=set 时传:[{name, value, url|domain, path?, ...}]"},
                    "urls": {"type": "array", "items": {"type": "string"},
                             "description": "action=get 时可选:指定 URL 列表(只取这些 URL 的 cookie)"},
                    "url": {"type": "string", "description": "可选;先导航到 URL(给 context 一个 origin)"},
                    "timeout": {"type": "integer"},
                    "wait_for_selector": {"type": "string"},
                    "wait_for_selector_timeout": {"type": "integer"},
                    "executable_path": {"type": "string"},
                },
                "required": ["action"], "additionalProperties": False,
            },
        },
    },
    # ===== 等待类 (2) =====
    {
        "type": "function",
        "function": {
            "name": "browser_wait_for_text",
            "description": (
                "等某段文字出现在 page(对登录成功跳转、AJAX 响应等场景非常有用)。"
                "exact=True 完全匹配,False 子串匹配。case_sensitive 控制大小写。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "url": {"type": "string"},
                    "timeout": {"type": "integer", "description": "等待超时秒数(默认 30)"},
                    "exact": {"type": "boolean", "description": "完全匹配(默认 False 子串)"},
                    "case_sensitive": {"type": "boolean", "description": "大小写敏感(默认 False)"},
                    "wait_for_selector": {"type": "string"},
                    "wait_for_selector_timeout": {"type": "integer"},
                    "executable_path": {"type": "string"},
                },
                "required": ["text"], "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_wait_for_url",
            "description": "等 URL 变化(支持 glob 模式:** 任意路径段,* 任意字符)。",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "URL glob,例如 '**/dashboard' / 'https://example.com/success*'"},
                    "url": {"type": "string"},
                    "timeout": {"type": "integer"},
                    "wait_until": {"type": "string", "enum": ["load", "domcontentloaded", "networkidle", "commit"]},
                    "executable_path": {"type": "string"},
                },
                "required": ["pattern"], "additionalProperties": False,
            },
        },
    },
]


# ============================================================================
# 工具 dispatch 表
# ============================================================================
TOOL_HANDLERS = {
    # HTTP
    "web_search": web_search,
    "web_search_diag": web_search_diag,
    "fetch_url": fetch_url,
    "fetch_urls": fetch_urls,
    # 导航
    "browser_navigate": browser_navigate,
    "browser_navigate_back": browser_navigate_back,
    "browser_navigate_forward": browser_navigate_forward,
    "browser_navigate_reload": browser_navigate_reload,
    "browser_close": browser_close,
    "browser_install": browser_install,
    # 交互
    "browser_click": browser_click,
    "browser_dblclick": browser_dblclick,
    "browser_hover": browser_hover,
    "browser_fill": browser_fill,
    "browser_type": browser_type,
    "browser_press": browser_press,
    "browser_select": browser_select,
    "browser_checkbox": browser_checkbox,
    "browser_drag": browser_drag,
    "browser_upload": browser_upload,
    # 提取
    "browser_query_dom": browser_query_dom,
    "browser_evaluate": browser_evaluate,
    "browser_console_logs": browser_console_logs,
    # 资源
    "browser_screenshot": browser_screenshot,
    "browser_pdf_save": browser_pdf_save,
    "browser_cookies": browser_cookies,
    # 等待
    "browser_wait_for_text": browser_wait_for_text,
    "browser_wait_for_url": browser_wait_for_url,
}


# ============================================================================
# CLI
# ============================================================================
def _print_schemas() -> None:
    print(json.dumps(TOOL_SCHEMAS, ensure_ascii=False, indent=2))


def _print_result(result: dict) -> int:
    if result["success"]:
        print(result["content"])
    else:
        print(result["content"], file=sys.stderr)
    return 0 if result["success"] else 1


def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="non_head_browser.py",
        description=(
            "Onion Agent 内置工具 - 无头浏览器 + 联网搜索 (28 个原子工具)\n"
            "HTTP 路线: web_search / web_search_diag / fetch_url / fetch_urls\n"
            "Playwright 路线:\n"
            "  导航: browser_navigate / browser_navigate_back / _forward / _reload / browser_close / browser_install\n"
            "  交互: click / dblclick / hover / fill / type / press / select / checkbox / drag / upload\n"
            "  提取: browser_query_dom / browser_evaluate / browser_console_logs\n"
            "  资源: browser_screenshot / browser_pdf_save / browser_cookies\n"
            "  等待: browser_wait_for_text / browser_wait_for_url"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--list-tools", action="store_true",
                   help="列出本模块所有 28 工具 schema")

    sub = p.add_subparsers(dest="cmd", metavar="<command>")

    # ===== HTTP 路线 =====
    s = sub.add_parser("search", help="多搜索引擎并行搜索")
    s.add_argument("--query", required=True)
    s.add_argument("--num-results", type=int, default=DEFAULT_NUM_RESULTS)
    s.add_argument("--region", choices=["auto", "cn", "global"], default="auto")
    s.add_argument("--timeout", type=int, default=SEARCH_ENGINE_TIMEOUT)

    d = sub.add_parser("search-diag", help="诊断当前系统区域 + 生效引擎")
    d.add_argument("--region", choices=["cn", "global", "auto"], default="auto", dest="force_region")
    d.add_argument("--reset", action="store_true", help="重置降级状态 + 重新启发式判断(VPN 切换后用)")

    f = sub.add_parser("fetch", help="HTTP 抓单 URL")
    f.add_argument("--url", required=True)
    f.add_argument("--format", choices=["html", "markdown", "text", "json"], default="markdown")
    f.add_argument("--extract-content", type=lambda v: v.lower() == "true", default=True)
    f.add_argument("--max-chars", type=int, default=DEFAULT_MAX_CHARS)
    f.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    f.add_argument("--headers", default=None, help="JSON 字符串")

    fu = sub.add_parser("fetch-urls", help="HTTP 并行抓多 URL")
    fu.add_argument("--urls", required=True, help='逗号分隔,例如 "https://a.com,https://b.com"')
    fu.add_argument("--format", choices=["html", "markdown", "text", "json"], default="markdown")
    fu.add_argument("--extract-content", type=lambda v: v.lower() == "true", default=True)
    fu.add_argument("--max-chars", type=int, default=DEFAULT_MAX_CHARS)
    fu.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    fu.add_argument("--max-concurrent", type=int, default=5)

    # ===== 导航 =====
    n = sub.add_parser("browser-navigate", help="Playwright 浏览器导航")
    n.add_argument("--url", required=True)
    n.add_argument("--wait-until", choices=["load", "domcontentloaded", "networkidle", "commit"], default="load")
    n.add_argument("--timeout", type=int, default=30)
    n.add_argument("--disable-media", type=lambda v: v.lower() == "true", default=True)
    n.add_argument("--executable-path", default=None)
    n.add_argument("--channel", default=None)
    n.add_argument("--proxy", default=None)
    n.add_argument("--headers", default=None, help="JSON 字符串")
    n.add_argument("--wait-for-selector", default=None)
    n.add_argument("--wait-for-selector-timeout", type=int, default=10)

    sub.add_parser("browser-back", help="浏览器后退")
    sub.add_parser("browser-forward", help="浏览器前进")
    nr = sub.add_parser("browser-reload", help="浏览器刷新")
    nr.add_argument("--wait-until", choices=["load", "domcontentloaded", "networkidle", "commit"], default="load")
    nr.add_argument("--timeout", type=int, default=15)
    sub.add_parser("browser-close", help="关闭浏览器")
    bi = sub.add_parser("browser-install", help="联网下载 Chromium")
    bi.add_argument("--with-deps", action="store_true")
    bi.add_argument("--force", action="store_true")
    bi.add_argument("--timeout", type=int, default=BROWSER_INSTALL_TIMEOUT)

    # ===== 交互 =====
    bc = sub.add_parser("browser-click", help="点击元素")
    bc.add_argument("--selector", required=True)
    bc.add_argument("--button", choices=["left", "right", "middle"], default="left")
    bc.add_argument("--modifiers", default=None, help='逗号分隔,例如 "Alt,Shift"')
    bc.add_argument("--timeout", type=int, default=DEFAULT_ACTION_TIMEOUT)
    bc.add_argument("--wait-after", action="store_true")
    bc.add_argument("--wait-for-selector", default=None)
    bc.add_argument("--wait-for-selector-timeout", type=int, default=10)

    bdc = sub.add_parser("browser-dblclick", help="双击元素")
    bdc.add_argument("--selector", required=True)
    bdc.add_argument("--timeout", type=int, default=DEFAULT_ACTION_TIMEOUT)

    bh = sub.add_parser("browser-hover", help="悬停元素")
    bh.add_argument("--selector", required=True)
    bh.add_argument("--timeout", type=int, default=DEFAULT_ACTION_TIMEOUT)

    bf = sub.add_parser("browser-fill", help="填 input/textarea 值")
    bf.add_argument("--selector", required=True)
    bf.add_argument("--value", required=True, help="要填的值(空字符串=清空)")
    bf.add_argument("--timeout", type=int, default=DEFAULT_ACTION_TIMEOUT)
    bf.add_argument("--clear-first", type=lambda v: v.lower() == "true", default=True)

    bt = sub.add_parser("browser-type", help="逐字输入(触发键盘事件)")
    bt.add_argument("--selector", required=True)
    bt.add_argument("--text", required=True)
    bt.add_argument("--delay-ms", type=int, default=30)
    bt.add_argument("--timeout", type=int, default=DEFAULT_ACTION_TIMEOUT)

    bp = sub.add_parser("browser-press", help="按键")
    bp.add_argument("--key", required=True)
    bp.add_argument("--selector", default=None)
    bp.add_argument("--timeout", type=int, default=DEFAULT_ACTION_TIMEOUT)

    bsel = sub.add_parser("browser-select", help="选择 <select> 下拉框选项")
    bsel.add_argument("--selector", required=True)
    bsel.add_argument("--value", default=None)
    bsel.add_argument("--label", default=None)
    bsel.add_argument("--index", type=int, default=None)
    bsel.add_argument("--timeout", type=int, default=DEFAULT_ACTION_TIMEOUT)

    bcb = sub.add_parser("browser-checkbox", help="勾选/取消 checkbox/radio")
    bcb.add_argument("--selector", required=True)
    bcb.add_argument("--checked", type=lambda v: v.lower() == "true", default=True)
    bcb.add_argument("--timeout", type=int, default=DEFAULT_ACTION_TIMEOUT)

    bdr = sub.add_parser("browser-drag", help="拖拽 source → target")
    bdr.add_argument("--source", required=True)
    bdr.add_argument("--target", required=True)
    bdr.add_argument("--source-position", default=None, help='JSON 字符串,例如 "{\"x\":10,\"y\":10}"')
    bdr.add_argument("--target-position", default=None, help='JSON 字符串')
    bdr.add_argument("--timeout", type=int, default=DEFAULT_ACTION_TIMEOUT)

    bu = sub.add_parser("browser-upload", help="上传文件")
    bu.add_argument("--selector", required=True)
    bu.add_argument("--files", required=True, help='JSON 列表字符串,例如 "[\"C:/a.txt\"]"')
    bu.add_argument("--timeout", type=int, default=DEFAULT_ACTION_TIMEOUT)

    # ===== 提取 =====
    qd = sub.add_parser("browser-query-dom", help="CSS selector 提取 DOM")
    qd.add_argument("--url", default=None)
    qd.add_argument("--selector", required=True)
    qd.add_argument("--extract", choices=["text", "html", "attribute", "count"], default="text")
    qd.add_argument("--attribute", default=None)
    qd.add_argument("--all-matches", action="store_true")
    qd.add_argument("--wait-for-selector", default=None)
    qd.add_argument("--wait-for-selector-timeout", type=int, default=10)
    qd.add_argument("--timeout", type=int, default=30)
    qd.add_argument("--executable-path", default=None)

    ev = sub.add_parser("browser-evaluate", help="执行任意 JS")
    ev.add_argument("--expression", required=True)
    ev.add_argument("--arg", default=None, help="可选参数(JSON 字符串)")
    ev.add_argument("--url", default=None)
    ev.add_argument("--timeout", type=int, default=30)
    ev.add_argument("--wait-for-selector", default=None)
    ev.add_argument("--wait-for-selector-timeout", type=int, default=10)
    ev.add_argument("--executable-path", default=None)

    cl = sub.add_parser("browser-console-logs", help="获取/清空浏览器 console 日志")
    cl.add_argument("--action", choices=["get", "clear"], default="get")
    cl.add_argument("--clear", action="store_true", help="读取后清空")

    # ===== 资源 =====
    bs = sub.add_parser("browser-screenshot", help="浏览器截图")
    bs.add_argument("--url", default=None)
    bs.add_argument("--selector", default=None)
    bs.add_argument("--full-page", type=lambda v: v.lower() == "true", default=True)
    bs.add_argument("--type", dest="image_type", choices=["png", "jpeg"], default="jpeg")
    bs.add_argument("--quality", type=int, default=80)
    bs.add_argument("--max-size-mb", type=float, default=SCREENSHOT_MAX_SIZE_MB)
    bs.add_argument("--wait-until", choices=["load", "domcontentloaded", "networkidle", "commit"], default="load")
    bs.add_argument("--timeout", type=int, default=30)
    bs.add_argument("--wait-for-selector", default=None)
    bs.add_argument("--wait-for-selector-timeout", type=int, default=10)
    bs.add_argument("--executable-path", default=None)

    bp2 = sub.add_parser("browser-pdf-save", help="页面另存为 PDF")
    bp2.add_argument("--url", default=None)
    bp2.add_argument("--path", required=True, help="目标 PDF 绝对路径")
    bp2.add_argument("--format", default="A4")
    bp2.add_argument("--margin", default=None, help='JSON 字符串,例如 "{\"top\":\"1cm\",\"bottom\":\"1cm\"}"')
    bp2.add_argument("--timeout", type=int, default=30)
    bp2.add_argument("--wait-for-selector", default=None)
    bp2.add_argument("--wait-for-selector-timeout", type=int, default=10)
    bp2.add_argument("--executable-path", default=None)

    bc2 = sub.add_parser("browser-cookies", help="Cookie 管理")
    bc2.add_argument("--action", choices=["get", "set", "clear"], default="get")
    bc2.add_argument("--cookies", default=None, help="action=set 时:JSON 列表")
    bc2.add_argument("--urls", default=None, help="action=get 时:JSON 列表")
    bc2.add_argument("--url", default=None, help="可选:先导航")
    bc2.add_argument("--timeout", type=int, default=30)
    bc2.add_argument("--wait-for-selector", default=None)
    bc2.add_argument("--wait-for-selector-timeout", type=int, default=10)
    bc2.add_argument("--executable-path", default=None)

    # ===== 等待 =====
    wft = sub.add_parser("browser-wait-for-text", help="等某段文字出现")
    wft.add_argument("--text", required=True)
    wft.add_argument("--url", default=None)
    wft.add_argument("--timeout", type=int, default=30)
    wft.add_argument("--exact", action="store_true")
    wft.add_argument("--case-sensitive", action="store_true")
    wft.add_argument("--wait-for-selector", default=None)
    wft.add_argument("--wait-for-selector-timeout", type=int, default=10)
    wft.add_argument("--executable-path", default=None)

    wfu = sub.add_parser("browser-wait-for-url", help="等 URL 变化(支持 glob)")
    wfu.add_argument("--pattern", required=True)
    wfu.add_argument("--url", default=None)
    wfu.add_argument("--timeout", type=int, default=30)
    wfu.add_argument("--wait-until", choices=["load", "domcontentloaded", "networkidle", "commit"], default="load")
    wfu.add_argument("--executable-path", default=None)

    return p


def _parse_json_arg(s, default=None):
    if s is None:
        return default
    try:
        return json.loads(s)
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON 解析失败: {e}: {s!r}")


def main(argv: Optional[list] = None) -> int:
    parser = _build_argparser()
    args = parser.parse_args(argv)

    if args.list_tools:
        _print_schemas()
        return 0
    if not args.cmd:
        parser.print_help()
        return 0

    try:
        # ===== HTTP 路线 =====
        if args.cmd == "search":
            result = web_search(query=args.query, num_results=args.num_results,
                                region=args.region, timeout=args.timeout)
        elif args.cmd == "search-diag":
            result = web_search_diag(force_region=args.force_region, reset=args.reset)
        elif args.cmd == "fetch":
            headers_dict = None
            if args.headers:
                try:
                    headers_dict = _parse_json_arg(args.headers)
                except ValueError as e:
                    print(f"[ERROR] {e}", file=sys.stderr); return 2
            result = fetch_url(url=args.url, format=args.format, extract_content=args.extract_content,
                               max_chars=args.max_chars, timeout=args.timeout, headers=headers_dict)
        elif args.cmd == "fetch-urls":
            urls_list = [u.strip() for u in args.urls.split(",") if u.strip()]
            if not urls_list:
                print("[ERROR] --urls 至少要有一个 URL", file=sys.stderr); return 2
            result = fetch_urls(urls=urls_list, format=args.format, extract_content=args.extract_content,
                                max_chars=args.max_chars, timeout=args.timeout, max_concurrent=args.max_concurrent)
        # ===== 导航 =====
        elif args.cmd == "browser-navigate":
            headers_dict = None
            if args.headers:
                try:
                    headers_dict = _parse_json_arg(args.headers)
                except ValueError as e:
                    print(f"[ERROR] {e}", file=sys.stderr); return 2
            result = browser_navigate(
                url=args.url, wait_until=args.wait_until, timeout=args.timeout,
                disable_media=args.disable_media, executable_path=args.executable_path,
                channel=args.channel, proxy=args.proxy, headers=headers_dict,
                wait_for_selector=args.wait_for_selector,
                wait_for_selector_timeout=args.wait_for_selector_timeout,
            )
        elif args.cmd == "browser-back":
            result = browser_navigate_back()
        elif args.cmd == "browser-forward":
            result = browser_navigate_forward()
        elif args.cmd == "browser-reload":
            result = browser_navigate_reload(wait_until=args.wait_until, timeout=args.timeout)
        elif args.cmd == "browser-close":
            result = browser_close()
        elif args.cmd == "browser-install":
            result = browser_install(with_deps=args.with_deps, force=args.force, timeout=args.timeout)
        # ===== 交互 =====
        elif args.cmd == "browser-click":
            modifiers_list = None
            if args.modifiers:
                modifiers_list = [m.strip() for m in args.modifiers.split(",") if m.strip()]
            result = browser_click(selector=args.selector, button=args.button,
                                   modifiers=modifiers_list, timeout=args.timeout,
                                   wait_after=args.wait_after,
                                   wait_for_selector=args.wait_for_selector,
                                   wait_for_selector_timeout=args.wait_for_selector_timeout)
        elif args.cmd == "browser-dblclick":
            result = browser_dblclick(selector=args.selector, timeout=args.timeout)
        elif args.cmd == "browser-hover":
            result = browser_hover(selector=args.selector, timeout=args.timeout)
        elif args.cmd == "browser-fill":
            result = browser_fill(selector=args.selector, value=args.value,
                                   timeout=args.timeout, clear_first=args.clear_first)
        elif args.cmd == "browser-type":
            result = browser_type(selector=args.selector, text=args.text,
                                  delay_ms=args.delay_ms, timeout=args.timeout)
        elif args.cmd == "browser-press":
            result = browser_press(key=args.key, selector=args.selector, timeout=args.timeout)
        elif args.cmd == "browser-select":
            if args.value is None and args.label is None and args.index is None:
                print("[ERROR] value/label/index 必须传一个", file=sys.stderr); return 2
            result = browser_select(selector=args.selector, value=args.value, label=args.label,
                                    index=args.index, timeout=args.timeout)
        elif args.cmd == "browser-checkbox":
            result = browser_checkbox(selector=args.selector, checked=args.checked, timeout=args.timeout)
        elif args.cmd == "browser-drag":
            sp = _parse_json_arg(args.source_position) if args.source_position else None
            tp = _parse_json_arg(args.target_position) if args.target_position else None
            result = browser_drag(source=args.source, target=args.target,
                                  source_position=sp, target_position=tp, timeout=args.timeout)
        elif args.cmd == "browser-upload":
            try:
                files_list = _parse_json_arg(args.files, default=[])
            except ValueError as e:
                print(f"[ERROR] {e}", file=sys.stderr); return 2
            if not files_list:
                print("[ERROR] --files 至少要有一个文件", file=sys.stderr); return 2
            result = browser_upload(selector=args.selector, files=files_list, timeout=args.timeout)
        # ===== 提取 =====
        elif args.cmd == "browser-query-dom":
            result = browser_query_dom(url=args.url, selector=args.selector, extract=args.extract,
                                       attribute=args.attribute, all_matches=args.all_matches,
                                       wait_for_selector=args.wait_for_selector,
                                       wait_for_selector_timeout=args.wait_for_selector_timeout,
                                       timeout=args.timeout, executable_path=args.executable_path)
        elif args.cmd == "browser-evaluate":
            arg_value = _parse_json_arg(args.arg) if args.arg else None
            result = browser_evaluate(expression=args.expression, arg=arg_value, url=args.url,
                                      timeout=args.timeout, wait_for_selector=args.wait_for_selector,
                                      wait_for_selector_timeout=args.wait_for_selector_timeout,
                                      executable_path=args.executable_path)
        elif args.cmd == "browser-console-logs":
            result = browser_console_logs(action=args.action, clear=args.clear)
        # ===== 资源 =====
        elif args.cmd == "browser-screenshot":
            result = browser_screenshot(url=args.url, selector=args.selector, full_page=args.full_page,
                                        image_type=args.image_type, quality=args.quality,
                                        max_size_mb=args.max_size_mb, wait_until=args.wait_until,
                                        timeout=args.timeout, wait_for_selector=args.wait_for_selector,
                                        wait_for_selector_timeout=args.wait_for_selector_timeout,
                                        executable_path=args.executable_path)
        elif args.cmd == "browser-pdf-save":
            margin_dict = _parse_json_arg(args.margin) if args.margin else None
            result = browser_pdf_save(url=args.url, path=args.path, format=args.format,
                                      margin=margin_dict, timeout=args.timeout,
                                      wait_for_selector=args.wait_for_selector,
                                      wait_for_selector_timeout=args.wait_for_selector_timeout,
                                      executable_path=args.executable_path)
        elif args.cmd == "browser-cookies":
            cookies_list = _parse_json_arg(args.cookies) if args.cookies else None
            urls_list = _parse_json_arg(args.urls) if args.urls else None
            result = browser_cookies(action=args.action, cookies=cookies_list, urls=urls_list,
                                     url=args.url, timeout=args.timeout,
                                     wait_for_selector=args.wait_for_selector,
                                     wait_for_selector_timeout=args.wait_for_selector_timeout,
                                     executable_path=args.executable_path)
        # ===== 等待 =====
        elif args.cmd == "browser-wait-for-text":
            result = browser_wait_for_text(text=args.text, url=args.url, timeout=args.timeout,
                                           exact=args.exact, case_sensitive=args.case_sensitive,
                                           wait_for_selector=args.wait_for_selector,
                                           wait_for_selector_timeout=args.wait_for_selector_timeout,
                                           executable_path=args.executable_path)
        elif args.cmd == "browser-wait-for-url":
            result = browser_wait_for_url(pattern=args.pattern, url=args.url, timeout=args.timeout,
                                          wait_until=args.wait_until,
                                          executable_path=args.executable_path)
        else:
            parser.print_help()
            return 2

        return _print_result(result)
    except KeyboardInterrupt:
        print("\n[已取消]", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())



