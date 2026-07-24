# tests/tool_channel - tool_channel 模块测试套件

> 用于 `src/infrastructure/tool_channel/tool_list.py` + `tool_router.py` 的手动测试
> 所有 fixture 都是 JSON / JSONL 格式,直接 `--command-file` 喂给 router
> 详见:`harness/03_SRS/infrastructure/tool_channel/design.md`

## 测试文件清单

| 文件 | 场景 | 预期 |
|------|------|------|
| `01_basic_buildin.json` | 单条 buildin 调用(list_dir) | 成功,返回目录列表 |
| `02_multi_calls.jsonl` | JSONL 格式多条调用(read_file + run_command + get_properties) | 3 个全部成功 |
| `03_error_zoo.json` | 7 种错误场景 | 6 个失败 + 1 个意外成功(JSON 修复) |
| `04_truncation.json` | 大结果截断(读整个 tool_list.py) | success,content 被 middle-out 截断 |
| `05_dry_run.json` | dry-run 模式(不真调工具) | 参数校验但跳过执行 |
| `06_case_insensitive.json` | tool name 全大写 + 路径不存在 | 路由成功(执行失败) |
| `06b_case_insensitive_ok.json` | tool name 全大写 + 路径存在 | 全部成功 |
| `07_id_fallback.json` | 1 条带 id + 1 条无 id | MD5 兜底 id 格式 `call_<12hex>` |

## 快速跑全部测试

```powershell
cd C:\workspace\github\onionagent\src

# 1) tool_list: 状态 / 汇总
python infrastructure\tool_channel\tool_list.py --status
python infrastructure\tool_channel\tool_list.py --to-openai

# 2) tool_router: 每个 fixture 跑一次
foreach ($f in Get-ChildItem ..\tests\tool_channel\*.json, ..\tests\tool_channel\*.jsonl) {
    Write-Output "===== $($f.Name) ====="
    python infrastructure\tool_channel\tool_router.py --no-mcp --command-file $f.FullName 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) { Write-Output "FAIL exit=$LASTEXITCODE" } else { Write-Output "OK" }
}
```

## 各场景期望行为详解

### 01_basic_buildin.json
- **input**: 调 `onion.buildin.file_system.list_dir`,path 是 tool_channel 目录
- **预期**: 成功,content 是目录列表(3 项,含 `__pycache__/tool_list.py/tool_router.py`)
- **验证点**: tool_call_id=`call_basic_1` echo 回来

### 02_multi_calls.jsonl
- **input**: 3 个 call
  1. `read_file` tool_list.py 前 500 字符
  2. `run_command` 跑 `echo hello-from-router`
  3. `get_properties` tool_channel 目录
- **预期**: 3 个全部成功,call_id 顺序保留(call_multi_1/2/3)
- **验证点**: JSONL 格式(JSON Lines)被正确解析,顺序保持

### 03_error_zoo.json
7 种错误场景,每种对应一个错误兜底层:

| # | call_id | 错误类型 | 期望 is_error | 期望 content 前缀 |
|---|---------|---------|---------------|------------------|
| 1 | call_err_unknown_tool | 未知工具 | True | `[ERROR] Unknown tool: ... Did you mean: ...` |
| 2 | call_err_bad_name | name 格式错 | True | `[ERROR] Invalid tool name format ...` |
| 3 | call_err_missing_required | 缺 required 字段 | True | `[ERROR] Argument schema validation failed: 'path' is a required property` |
| 4 | call_err_extra_field | additionalProperties: false 拒绝 | True | `[ERROR] Argument schema validation failed: Additional properties are not allowed ...` |
| 5 | call_err_wrong_type | path 类型错(int) | True | `[ERROR] Argument schema validation failed: 12345 is not of type 'string'` |
| 6 | call_err_broken_json | 截断 JSON `{"path": "C:` | **False** | 目录列表(6 层 JSON 修复成功) |
| 7 | call_err_unknown_after_json_repair | list 不是 object | True | `[ERROR] Argument parse failed: Expected JSON object, got list` |

### 04_truncation.json
- **input**: 读 tool_list.py(27928 字符)
- **预期**: content 中间包含 `[... output truncated: 共 27928 字符, 截断 27828 字符 ...]`,summary 中 `truncated: True`
- **验证点**: 50K 中间截断(头+尾)而不是单纯截尾

### 05_dry_run.json
- **input**: 2 个 call
  1. 合法 read_file
  2. 错的 path 类型
- **预期**: 
  - call 1: success=True, content=`[DRY-RUN] arguments parsed and validated; tool not executed`
  - call 2: 仍然走 schema 校验 → [ERROR]
- **验证点**: dry-run 跳过执行但不跳校验

### 06 / 06b: 大小写不敏感
- **input**: tool name 全大写 `ONION.BUILDIN.FILE_SYSTEM.READ_FILE`
- **预期**: parse_tool_name 把 tag/scope/tool 全部转小写后匹配上
- **验证点**: §4.6 / §5.4 工具名规范化要求 case-insensitive

### 07_id_fallback.json
- **input**: 1 条带 `id="call_with_id_1"`,1 条没 `id` 字段
- **预期**: 
  - call 1: `tool_call_id=call_with_id_1`
  - call 2: `tool_call_id=call_<12位hex>`(MD5(name+arguments))
- **验证点**: §5.11 兜底机制

## 工具使用速查

```powershell
# 健康状态
python infrastructure\tool_channel\tool_list.py --status
python infrastructure\tool_channel\tool_router.py --no-mcp --status

# 工具列表(OpenAI 风格)
python infrastructure\tool_channel\tool_list.py --to-openai
python infrastructure\tool_channel\tool_list.py --tag buildin --to-openai
python infrastructure\tool_channel\tool_list.py --to-openai --detail

# 单个工具 schema
python infrastructure\tool_channel\tool_list.py --tool-info onion.buildin.file_system.read_file

# 单条 / 多条 router 调用
python infrastructure\tool_channel\tool_router.py --no-mcp --command '<json>'
python infrastructure\tool_channel\tool_router.py --no-mcp --command-file path\to\fixture.json

# dry-run
python infrastructure\tool_channel\tool_router.py --no-mcp --command-file path\to\fixture.json --dry-run

# 纯 JSON 输出(管道友好)
python infrastructure\tool_channel\tool_router.py --no-mcp --no-pretty --command-file ...
```
