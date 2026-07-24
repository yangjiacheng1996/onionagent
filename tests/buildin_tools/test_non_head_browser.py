"""SSRF 防护单元测试 - 不依赖网络"""
import sys
from pathlib import Path

# 路径 hack:让 import 找得到
ROOT = Path(__file__).resolve().parents[2]  # tests/buildin_tools/ -> tests -> 项目根
sys.path.insert(0, str(ROOT / "src" / "infrastructure" / "buildin_tools"))

import non_head_browser as m  # noqa: E402

print("=== SSRF 防护测试 ===")
tests = [
    ("http://localhost/foo", False),
    ("http://127.0.0.1/foo", False),
    ("http://10.0.0.1/foo", False),
    ("http://169.254.169.254/latest/meta-data/", False),  # AWS metadata
    ("http://192.168.1.1/foo", False),
    ("http://example.com", True),
    ("https://www.google.com", True),
    ("file:///etc/passwd", False),
    ("javascript:alert(1)", False),
    ("ftp://example.com", False),
    ("http://[::1]/foo", False),  # IPv6 loopback
    ("http://172.16.0.1/foo", False),  # 私网
    ("http://100.64.0.1/foo", False),  # CGN
    ("http://0.0.0.0/foo", False),  # 全零
    ("", False),  # 空
    ("not-a-url", False),  # 无 scheme
]
passed = 0
failed = 0
for url, should_pass in tests:
    ok, reason, _ = m._validate_url(url)
    actual_pass = ok
    mark = "OK" if actual_pass == should_pass else "FAIL"
    if actual_pass == should_pass:
        passed += 1
    else:
        failed += 1
    expected = "PASS" if should_pass else "BLOCK"
    actual = "PASS" if actual_pass else "BLOCK"
    print(f"  [{mark}] {url!r:50s} expected={expected:5s} got={actual:5s}  {reason if not ok else ''}")
print(f"\n=== {passed} passed, {failed} failed ===")
sys.exit(0 if failed == 0 else 1)
