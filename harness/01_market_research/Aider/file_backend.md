# Aider — 工作区(File Backend)调研报告

> 对象:`Aider-AI/aider` (v3.x, 47k+ ⭐, 调研快照位于 `harness/01_market_research/clone/aider/`)
> 调研时间:2026-07
> 目的:为 Onion Agent 的"洋葱架构 / session.json 中心化"设计,提取 Aider 在 **工作区路径 / 目录结构 / 初始化策略** 三个维度的可借鉴点与避坑点。

---

## 0. 智能体一句话定位

**终端里的 AI 结对编程,自动生成 commit message / 自动建分支,与 git 仓库直接交互,兼容 Claude / GPT / DeepSeek / OpenRouter / Ollama / 本地模型**。Aider 没有持久化的"会话文件"概念,而是把 **git 仓库本身** 作为状态容器(commit hash 是上下文边界,`.aider*` 散落文件是辅助元数据)。

---

## 1. 调研依据

- 源码:`harness/01_market_research/clone/aider/aider/`(已 Read-Only)
- 关键文件:
  - `aider/main.py` — CLI 入口,负责 git_root 探测、config 加载、gitignore 检查
  - `aider/args.py` — `configargparse` 实现的全部 CLI/Config/Env 三态参数
  - `aider/repo.py` — `GitRepo` 封装,基于 GitPython
  - `aider/io.py` — prompt_toolkit + FileHistory
  - `aider/analytics.py` — 全局状态文件 `~/.aider/analytics.json`
  - `aider/repomap.py` — RepoMap 标签缓存 `.aider.tags.cache.v{3|4}/`
  - `aider/models.py` / `aider/openrouter.py` — `~/.aider/caches/` 模型缓存
  - `aider/versioncheck.py` — `~/.aider/caches/versioncheck`
  - `aider/onboarding.py` — `~/.aider/oauth-keys.env`
  - `aider/help.py` — `~/.aider/caches/help.<version>/`
  - `aider/watch.py` — FileWatcher 内置 ignore 模式
  - `aider/args_formatter.py` — 生成 `.aider.conf.yml` / `.env` 样例
  - `aider/resources/model-metadata.json` / `model-settings.yml` — 包内置默认配置
  - `docker/Dockerfile` — 容器化部署对工作区的影响
  - `aider/.gitignore` — 仓库自身的 `.aider*` 忽略模式

---

## 2. 三个核心问题的回答

### Q1. 工作区路径

| 维度 | 结论 | 代码证据 |
|---|---|---|
| **核心工作区** | **跟随当前 git 仓库**。Aider 必须在 git 仓库内运行(`--git` 默认 `True`);仓库根目录就是它的工作区"基底",所有要编辑的文件都从该根解析相对路径。 | `args.py:405-409` `--git` 默认 `True`;<br>`main.py:454-462` `get_git_root()` 用 `git.Repo(search_parent_directories=True)` 自动向上递归查找;用户给 `aider .` 也会触发相同的 `git.Repo().working_tree_dir` 探测(`main.py:101-105`) |
| **仓库内辅助文件** | 默认全部放在 **git 仓库根目录**:`.aider.chat.history.md`、`.aider.input.history`、`.aider.model.metadata.json`、`.aider.model.settings.yml`、`.aiderignore`、`.aider.llm.history`(可选)、`.aider.tags.cache.v3/`(SQLite cache)等。 | `args.py:272-276` `default_input_history_file` / `default_chat_history_file` 拼上 `git_root`;<br>`args.py:121-130` 默认值 `.aider.model.settings.yml` / `.aider.model.metadata.json`;<br>`repomap.py:42-43` `TAGS_CACHE_DIR = f".aider.tags.cache.v{CACHE_VERSION}"`,`repomap.py:186-188` `Path(self.root) / self.TAGS_CACHE_DIR` |
| **全局配置 / 缓存** | **写死用户属主目录 `~/.aider/`**:`~/.aider.conf.yml`(配置)、`~/.aider/analytics.json`(UUID & opt-in 状态)、`~/.aider/installs.json`(版本追踪)、`~/.aider/oauth-keys.env`(OAuth 凭据)、`~/.aider/caches/*`(模型/版本/帮助缓存)。 | `analytics.py:138-141` `Path.home() / ".aider" / "analytics.json"`;<br>`main.py:370-372` `~/.aider/oauth-keys.env`;<br>`main.py:1185` `~/.aider/installs.json`;<br>`models.py:169` / `openrouter.py:34` `~/.aider/caches/`;<br>`versioncheck.py:12` `~/.aider/caches/versioncheck`;<br>`help.py:93` `~/.aider/caches/help.<version>/` |
| **自定义路径能力** | ✅ **强**。每个工作区文件都有独立 CLI 参数 + env 变量 + 配置文件 key,三层可覆盖:<br>• CLI: `--input-history-file`、`--chat-history-file`、`--llm-history-file`、`--model-settings-file`、`--model-metadata-file`、`--aiderignore`、`--config`、`--env-file`<br>• Env: `AIDER_INPUT_HISTORY_FILE`、`AIDER_CHAT_HISTORY_FILE`、`AIDER_LLM_HISTORY_FILE`、`AIDER_MODEL_SETTINGS_FILE`、`AIDER_MODEL_METADATA_FILE`、`AIDER_AIDERIGNORE`、`AIDER_GITIGNORE` 等(`auto_env_var_prefix="AIDER_"`)<br>• 配置文件:`.aider.conf.yml` 同样的 key | `args.py:38-42` `auto_env_var_prefix="AIDER_"`;<br>`args.py:120-130`、`278-300` 各 `--*-file` 参数;<br>`args.py:422-432` `--aiderignore` 支持 `resolve_aiderignore_path`(绝对/相对 git_root) |
| **无 git 仓库时** | 不硬性要求,但强烈引导。可选 `--no-git` 进入"纯文件编辑"模式;否则会询问是否 `git init`。在 home 目录运行会**直接警告**(避免误把 home 目录 git 化)。 | `main.py:107-141` `setup_git()` 三分支:`git_root` 已存在 / cwd == home 警告 / 无 git 询问 `git init`;<br>`main.py:85-95` `make_new_repo()` 实际执行 `git.Repo.init` + `check_gitignore` |

**Q1 一句话总结**:Aider 是个 **"git 仓库即工作区"** 的设计——主目录是 git 仓库根,辅助文件按 `~/.aider/`(全局缓存)+ `git 根/.aider*`(项目级)双层布局;路径被三个机制完全开放(CLI / env / `.aider.conf.yml`)。

---

### Q2. 工作区目录结构(完整清单)

#### 2.1 项目级(Git 仓库根目录)

| 路径 | 类型 | 作用 | 是否可关 | 来源 |
|---|---|---|---|---|
| `.aider.chat.history.md` | 文件 | Chat 历史(markdown 格式,追加写) | ✅ `--no-chat-history` / `--chat-history-file` | `io.py:1130-1132` 追加写;`args.py:274-275` |
| `.aider.input.history` | 文件 | 用户输入历史(给 prompt_toolkit 用) | ✅ `--no-fancy-input` / `--input-history-file` | `io.py:313` 自动创建父目录;`io.py:355-356` `FileHistory(...)` |
| `.aider.llm.history` | 文件 | LLM 完整对话日志(role+timestamp+content,**默认 None**) | 默认未启用,需 `--llm-history-file` | `args.py:296-300`;`io.py:754-765` `log_llm_history` |
| `.aider.model.settings.yml` | 文件 | 用户/项目级 model 自定义参数 | ✅ `--model-settings-file` | `args.py:121-125` |
| `.aider.model.metadata.json` | 文件 | 用户/项目级 model metadata | ✅ `--model-metadata-file` | `args.py:127-131` |
| `.aiderignore` | 文件 | `.gitignore` 风格,但只对 Aider 生效(`pathspec.GitWildMatchPattern`) | ✅ `--aiderignore` | `repo.py:500-524` `refresh_aider_ignore()` |
| `.aider.tags.cache.v3/` | 目录(`diskcache.Cache` = SQLite) | RepoMap 的 tag 缓存,按文件名 hash + mtime 索引 | ❌ 必须有,自动管理(TSL 时 v4) | `repomap.py:42-43`、`repomap.py:217-220` `Cache(path)` |
| `.env` | 文件 | dotenv 配置文件,**Aider 会加载**(优先级 1) | ✅ `--env-file` | `main.py:357-365` `generate_search_path_list` |
| `.gitignore` | 文件 | git 自身的忽略;**Aider 会自动追加 `.aider*` 和 `.env`** | ✅ `--no-gitignore` | `main.py:155-198` `check_gitignore` |

#### 2.2 全局级(`~/.aider/`)

| 路径 | 类型 | 作用 | 来源 |
|---|---|---|---|
| `~/.aider.conf.yml` | 文件 | **全局配置**(等价于项目级但作用于所有项目) | `main.py:464-476` config 搜索路径之一 |
| `~/.aider/analytics.json` | 文件 | UUID + opt-in 状态 + permanently_disable | `analytics.py:138-141` |
| `~/.aider/installs.json` | 文件 | 记录 `(version, executable)` 是否首次运行,用于弹"新版本说明" | `main.py:1183-1216` |
| `~/.aider/oauth-keys.env` | 文件 | OpenRouter OAuth 凭据,优先级最高 | `main.py:370-372`、`onboarding.py:361-368` |
| `~/.aider/caches/versioncheck` | 文件 | 24h TTL 的版本检查时间戳 | `versioncheck.py:12` |
| `~/.aider/caches/model_prices_and_context_window.json` | 文件 | 24h TTL,缓存 litellm 模型价格/上下文 | `models.py:168-170` |
| `~/.aider/caches/openrouter_models.json` | 文件 | 24h TTL,OpenRouter 模型目录 | `openrouter.py:33-35` |
| `~/.aider/caches/help.<version>/` | 目录 | `/help` 命令的 llama_index 向量索引 | `help.py:93` |

#### 2.3 包内置(Python 包内只读)

| 路径 | 作用 |
|---|---|
| `aider/resources/model-metadata.json` | 默认模型元数据(29057 bytes) |
| `aider/resources/model-settings.yml` | 默认模型设置(89498 bytes) |

`main.py:393-395` 把 `importlib_resources.files("aider.resources").joinpath("model-metadata.json")` 放在搜索链最前面,然后叠加 home / git root / cwd 的覆盖文件。

#### 2.4 配置 / 数据搜索链(优先级从低到高)

1. **包内置**(`aider/resources/model-metadata.json` 等,只读默认)
2. **home**:`~/.aider.conf.yml`、`~/.aider/caches/*`、`~/.aider/analytics.json`
3. **git root**:`.aider.conf.yml`、`.aider.model.settings.yml`、`.aider.model.metadata.json`、`.aider.chat.history.md` 等
4. **cwd**:同名文件(cwd 覆盖 git root)
5. **命令行 `-c <file>` / `--config <file>`**(`is_config_file=True` 在 args.py:790)
6. **命令行 `--*` 参数** 和 **环境变量 `AIDER_*`**(最高)

`main.py:305-330` `generate_search_path_list` 实现"home → git_root → cwd → command_line"的反转合并去重;`main.py:482-490` `parser.parse_known_args(argv)` 跑两轮是为了让 dotenv 里的 env 影响后续解析。

#### 2.5 RepoMap 缓存内部

`.aider.tags.cache.v3/` 是 `diskcache.Cache` 创建的 SQLite,key 是 `fname`(完整路径),value 是 `{"mtime": int, "data": [Tag, ...]}`。
- `repomap.py:241-258` 读时检查 mtime 命中,未命中调用 `get_tags_raw` 重算
- 版本号 `CACHE_VERSION = 3`(默认)、`4`(用 tree-sitter-language-pack 时自动升),**用户改 tree-sitter 模式会触发缓存重建**(`repomap.py:36-39`)

---

### Q3. 工作区创建

#### 3.1 显式初始化?

**没有 `aider --init` 命令**。全局搜索 `aider --init` / `cmd_init` / `init_repo` 均无匹配。

Aider 的"初始化"是**事件驱动**的,首次运行时按需懒创建。

#### 3.2 隐式创建(全部自动)

| 时机 | 动作 | 代码 |
|---|---|---|
| 启动检测到 cwd 无 git 仓库 | 询问 `git init` + `check_gitignore`(不需要先确认) | `main.py:107-141` `setup_git`;`main.py:85-95` `make_new_repo` |
| 启动检测到 git 仓库但 `.aider*` 没被忽略 | 询问 `Add .aider* to .gitignore (recommended)?`(`--no-gitignore` 跳过) | `main.py:155-198` `check_gitignore`;调用 `repo.ignored(".aider")` 测试是否已覆盖 |
| 首次写 input history | 自动 `mkdir(parents=True, exist_ok=True)` | `io.py:312-316` |
| 首次写 chat history | 同上,append 模式 | `io.py:1128-1136` |
| 首次写 llm history(若启用) | 同上 | `io.py:759-765` |
| 首次访问 `~/.aider/analytics.json` | `mkdir(parents=True, exist_ok=True)` | `analytics.py:138-141` |
| 首次访问 `~/.aider/caches/*` | 同上 | 多处 |
| 首次 RepoMap 计算 | `Cache(path)` 创建 `.aider.tags.cache.v3/` | `repomap.py:217-220` |
| 首次 OAuth 流程 | 追加到 `~/.aider/oauth-keys.env`(`mode="a"`) | `onboarding.py:361-368` |
| 首次启动新 `(version, executable)` | 同步加载重型 imports + 弹新版本说明;之后异步后台加载 | `main.py:1183-1224` `is_first_run_of_new_version` + `check_and_load_imports` |

#### 3.3 `.aider*` 是用户手动 .gitignore 还是自动忽略?

**两层防护**:

1. **仓库自身 `.gitignore`**:Aider 官方仓库的 `.gitignore:9` 写死了 `.aider*`(防止开发 Aider 时误提交);
2. **运行期自动检查 + 添加**:`check_gitignore()`(`main.py:155-198`)通过 `repo.ignored(".aider")` 测试当前 `.gitignore` 是否覆盖 `.aider*`,**没覆盖就询问并自动追加**(默认 `--gitignore=True`,可 `--no-gitignore` 关闭)。

`check_gitignore` 同时把 `.env` 一并加入(因为 Aider 也会读它),逻辑很周到。

```python
# main.py:155-198 核心逻辑(节选)
def check_gitignore(git_root, io, ask=True):
    if not git_root: return
    repo = git.Repo(git_root)
    patterns_to_add = []
    if not repo.ignored(".aider"):
        patterns_to_add.append(".aider*")
    env_path = Path(git_root) / ".env"
    if env_path.exists() and not repo.ignored(".env"):
        patterns_to_add.append(".env")
    if not patterns_to_add: return
    # ... 读 .gitignore → 追加 → 写回
    if ask and not io.confirm_ask(f"Add {', '.join(patterns_to_add)} to .gitignore?"):
        return
```

#### 3.4 Docker 模式的特殊处理

`docker/Dockerfile:32` `ENV HOME=/app` —— **容器里 `~/.aider` 直接落到挂载的 git 仓库根目录**(`/app` 是项目挂载点),所以 Docker 模式下"全局缓存"和"项目级文件"会**混在一起**,但依然靠 `.aider*` gitignore 模式自动隐藏。`HISTORY.md:427` 注释:"Docker containers now set `HOME=/app` ... to persist `~/.aider`."

---

## 3. 关键代码片段(摘录)

### 3.1 git_root 自动探测 + config 搜索链(`main.py:454-490`)

```python
def get_git_root():
    """Try and guess the git repo, since the conf.yml can be at the repo root"""
    try:
        repo = git.Repo(search_parent_directories=True)  # ← 向上递归
        return repo.working_tree_dir
    except (git.InvalidGitRepositoryError, FileNotFoundError):
        return None

# main()
conf_fname = Path(".aider.conf.yml")
default_config_files = []
default_config_files += [conf_fname.resolve()]                # CWD
if git_root:
    git_conf = Path(git_root) / conf_fname
    default_config_files.append(git_conf)                    # git root
default_config_files.append(Path.home() / conf_fname)        # home
# ... 之后 reverse(),再 parse 两遍(第二轮让 dotenv 里的 env 生效)
```

### 3.2 自动 gitignore 检查 + 添加(`main.py:155-198`)

(见 3.3 节)

### 3.3 RepoMap SQLite 缓存创建(`repomap.py:42-43, 186-220`)

```python
class RepoMap:
    TAGS_CACHE_DIR = f".aider.tags.cache.v{CACHE_VERSION}"  # v3 默认,v4 用 TSL

    def load_tags_cache(self):
        path = Path(self.root) / self.TAGS_CACHE_DIR
        self.TAGS_CACHE = Cache(path)   # diskcache.Cache = SQLite + lockfile
```

### 3.4 全局 OAuth 凭据持久化(`onboarding.py:361-368`)

```python
config_dir = os.path.expanduser("~/.aider")
os.makedirs(config_dir, exist_ok=True)
key_file = os.path.join(config_dir, "oauth-keys.env")
with open(key_file, "a", encoding="utf-8") as f:
    f.write(f'OPENROUTER_API_KEY="{api_key}"\n')
```

### 3.5 chat/input history 写入(`io.py:1128-1136, 312-316`)

```python
# input history
Path(self.input_history_file).parent.mkdir(parents=True, exist_ok=True)
session_kwargs["history"] = FileHistory(self.input_history_file)

# chat history (append, 不会清空旧内容)
self.chat_history_file.parent.mkdir(parents=True, exist_ok=True)
with self.chat_history_file.open("a", encoding=self.encoding, errors="ignore") as f:
    f.write(text)
```

### 3.6 首次运行识别(`main.py:1183-1216`)

```python
def is_first_run_of_new_version(io, verbose=False):
    installs_file = Path.home() / ".aider" / "installs.json"
    key = (__version__, sys.executable)
    if Path(installs_file).exists():
        installs = json.load(open(installs_file))
    else:
        installs = {}
    is_first_run = str(key) not in installs
    if is_first_run:
        installs[str(key)] = True
        installs_file.parent.mkdir(parents=True, exist_ok=True)
        json.dump(installs, open(installs_file, "w"), indent=4)
    return is_first_run
```

---

## 4. 与 Onion Agent 设计的关联

> Onion Agent = "围绕 `session.json` 自动累加的 Agent Loop"。本节对照 Aider,提炼可借鉴 / 需规避的设计决策。

### 4.1 ✅ 值得借鉴

| 借鉴点 | Aider 的做法 | 在 Onion Agent 中的映射 |
|---|---|---|
| **多级配置/数据搜索链** | home → git root → cwd → CLI/Env,key 重名时后写覆盖前写 | Onion Agent 可以做"global config → project root → cwd → CLI",把 `session.json` 路径、模型配置、Redis 连接信息等分层。 |
| **懒加载 + 自动创建父目录** | 第一次访问 history/caches 时 `mkdir(parents=True, exist_ok=True)` | Onion Agent 写 `session.json` / 上下文缓存时也用同样模式,避免要求用户"先建目录"。 |
| **每个数据文件独立 CLI 参数 + AIDER_* env 变量** | `--chat-history-file`、`AIDER_CHAT_HISTORY_FILE`、`.aider.conf.yml` 三层 | Onion Agent 给 `session.json` 路径、`memory_backend`、`vector_db_url` 等关键参数都做"CLI + env + config"三态,降低切换成本。 |
| **package-internal defaults + user overrides** | `aider/resources/model-metadata.json` 兜底 + 用户 `.aider.model.metadata.json` 覆盖 | Onion Agent 在包内放一份 `default_session_template.json`,用户/项目可覆盖关键字段。 |
| **首次运行探测** | `~/.aider/installs.json` + `(version, executable)` key 弹新版本说明 | Onion Agent 可以用 `~/.onion_agent/upgrade_log.json` 实现"v0.3 → v0.4 数据迁移提示"等升级场景。 |
| **gitignore 自动检查** | `check_gitignore()` 主动询问 | 如果 Onion Agent 也要在 git 仓库里写 `.onion_session/` 之类,可以照搬这个交互(避免污染用户的 commit)。 |
| **Docker 模式 HOME=项目根** | 让 `~/.aider/caches` 跨容器生命周期持久化 | Onion Agent 在容器化部署时同样可以把 `~/.onion_agent/` 重定向到持久卷。 |

### 4.2 ⚠️ 需要规避的坑

| 问题 | Aider 的具体表现 | Onion Agent 的应对 |
|---|---|---|
| **没有"会话文件"概念** | Aider 把状态散落在 5+ 个文件:`.aider.chat.history.md`、`.aider.input.history`、`.aider.llm.history`、`.aider.model.settings.yml`、`.aiderignore`、`.aider.tags.cache.v3/`,**没有"原子性"快照**。崩溃或并发启动容易留垃圾。 | Onion Agent 的核心设计("一切围绕 `session.json`")正好解决这个:单一文件 = 单一真相源,易于备份/恢复/迁移。 |
| **chat history 永远 append,不裁剪** | `io.py:1128-1136` 用 `mode="a"`,只在 `ChatSummary.too_big` 触发时压缩,**压缩结果不回写文件**,只影响下次 LLM 调用 | Onion Agent 如果有类似 `session.json`,要明确"压缩是事件还是文件操作",建议在 `session.json` 顶端维护 `summary_checkpoint` 指针。 |
| **chat_history_file.parent.mkdir 失败 = 静默 disable** | `io.py:1136` 写失败时只是 `self.chat_history_file = None` 关闭后续写入,**不告警用户** | Onion Agent 写 `session.json` 失败应当 raise / 弹显眼错误,不能静默丢失用户上下文。 |
| **`~/.aider/` 跨用户/跨项目共享** | 同一台机器上多个 git 项目用 aider,共享 `~/.aider/caches/`,理论上 cache key 是文件路径所以安全,但版本/analytics 状态会被一起改 | Onion Agent 全局数据(版本/UI 偏好)可以放 `~/.onion_agent/`,**但 session 状态必须项目级**(默认 `./.onion/session.json`)。 |
| **check_gitignore 是 best-effort** | `main.py:176-180` 读 `.gitignore` 出 OSError 就直接 `return`,用户不会得到任何提示 | Onion Agent 写项目级状态前要"原子校验"——失败就明确告诉用户"git 仓库读不到,无法持久化" |
| **`make_new_repo` 自动 git init 风险** | 某些 CI/容器场景下会被意外 git 化 | Onion Agent **不要**自动 `git init`,应该明确要求"在已 git 化的目录里运行",或用独立的项目级目录(如 `.onion/`)避免冲突。 |
| **cache 版本号硬编码** | `CACHE_VERSION = 3` 写死在 `repomap.py:39`,升级 tree-sitter 包会自动切到 v4,**老缓存不会自动迁移** | Onion Agent 在 `session.json` schema 升级时,要有显式 migration 路径(读老格式 → 转换 → 写新格式),不要依赖"删了重建"。 |
| **Docker 模式 HOME=APP 混淆全局/项目级** | `~/.aider/caches` 和 `.aider*` 在容器里都落 `/app`,路径层面是项目级,**但语义是全局** | Onion Agent 容器化时,要把 `~/.onion_agent/`(全局缓存)和 `./.onion/`(项目级 session)显式分开挂载。 |

### 4.3 关键启发

1. **"git 仓库即工作区"是 Aider 的灵魂**:Onion Agent 不需要绑死 git 仓库,但可以借鉴"项目根目录 = 真相源"的思维。
2. **多级覆盖 + 懒创建** 是 47k ⭐ 项目的核心 UX 哲学:用户开箱即用,高级用户可深度定制。
3. **"散落多个 .aider* 文件" 是历史包袱**,不是 Aider 想做的——它本意是一个"无状态 CLI",git 是它的状态机。Onion Agent 反向操作:用 `session.json` 把所有状态收敛,**学习 Aider 的"自动 .gitignore"机制防止污染**,但用更聚合的 schema。
4. **包内置 default + 用户 override** 这一对是减少"用户必须先写配置"摩擦的关键,可直接抄。

---

## 5. 不确定 / 未找到

| 编号 | 项 | 说明 |
|---|---|---|
| U-1 | `aider --init` 是否完全不存在? | 全局搜索 `init` 仅在 `git.Repo.init`、`SwitchCoder.__init__`、`install_help_extra` 等位置出现,**没有 CLI `--init` 也没有 `/init` slash 命令**。但 GitHub 上是否有 community PR 提供 `aider --init` 未追溯。 |
| U-2 | 多项目并发启动的 isolation 机制 | Aider 似乎没有 PID / file lock 机制,理论上两个 `aider` 跑在同一个 git 仓库会同时写 `.aider.chat.history.md` 和竞争 `.aider.tags.cache.v3/cache.db`。`diskcache.Cache` 自带 SQLite 锁,但 chat history 是裸 `mode="a"` 写,可能交错。 |
| U-3 | GUI 模式(`--gui`)在浏览器中运行时,文件路径 | `gui.py:50` `for root, _, files in os.walk("aider"):` 硬编码搜索 `aider/` 子目录,**没看到额外的 GUI 专属工作区文件**。可能 Streamlit 自己有 `.streamlit/` 目录(见 `main.py:230-237` `write_streamlit_credentials()` 写到 `get_streamlit_file_path()`),与 Aider 关系不大。 |
| U-4 | `.aider.tags.cache.v3/` 在极小仓库是否会跳過? | 看到 `repomap.py:391-395` "if `len(fnames) - cache_size > 100` 提示清缓存",但**没看到** 主动 prune 旧 key 的代码,缓存可能无限增长。 |
| U-5 | 完整 .aiderignore 语法文档 | 代码用 `pathspec.GitWildMatchPattern`(`repo.py:519`),等同于 .gitignore 语法,但 Aider 没单独文档化可用语法。 |
