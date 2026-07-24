# chromium/

预留目录，用于放置内置的 Chromium 浏览器二进制（内网/信创场景）。

## 为什么需要内置 Chromium

Onion Agent 经常运行在**内网/信创环境**，无法通过 `playwright install chromium` 下载 Chromium。
所以我们把 Chromium 二进制直接放在代码仓库里，随项目分发。

## 目录约定

把解压后的 Chromium 放在 `chromium/chrome-win/chrome.exe`（Windows）或
`chromium/chrome-linux/chrome`（Linux），目录结构对应 Playwright 官方的解压后布局：

```
chromium/
├── README.md
├── INSTALL.md                 # 详细安装说明
├── .gitkeep
├── chrome-win/                # Windows 二进制（按需 git lfs 或外部挂载）
│   └── chrome.exe
├── chrome-linux/              # Linux 二进制
│   └── chrome
├── chrome-mac/                # macOS 二进制
│   └── Chromium.app/...
└── version.json               # 记录 Chromium 版本号（用于 sanity check）
```

> **注意**：Chromium 二进制总大小约 150-200MB，通常**不进 git 仓库**，而是通过：
>   1. CI/CD 构建时下载到本目录
>   2. 部署时通过内部包管理源同步
>   3. Docker 镜像构建层 COPY 进去
>
> 本目录保留 `.gitkeep` 和 `README.md` 作为占位，开发者需要时手动放二进制进来。

## non_head_browser.py 的查找顺序

`non_head_browser.py` 启动浏览器时按以下顺序查找 Chromium：

1. **环境变量** `ONION_CHROMIUM_PATH` —— 用户显式指定的绝对路径
2. **本目录** `<buildin_tools>/chromium/chrome-{win,linux,mac}/...` —— 内置二进制
3. **Playwright 默认缓存** `%LOCALAPPDATA%\ms-playwright\chromium-*/` —— 联网安装的
4. **executable_path 参数** —— 工具调用时显式传入的本机浏览器

如果以上全部找不到，抛清晰错误并提示调 `browser_install` 工具。

## 版本管理

`version.json` 记录版本号和下载来源（方便运维追溯）：

```json
{
  "version": "120.0.6099.109",
  "download_url": "https://playwright.azureedge.net/builds/chromium/...",
  "installed_at": "2026-07-23T12:00:00Z",
  "channel": "chromium",
  "compatible_playwright_version": ">=1.40.0"
}
```

## 更多信息

- Playwright 浏览器路径规范：<https://playwright.dev/docs/browsers>
- 内置 Chromium 的 CI/CD 集成：见项目根 `Dockerfile` 和 `harness/04_deployment/`
