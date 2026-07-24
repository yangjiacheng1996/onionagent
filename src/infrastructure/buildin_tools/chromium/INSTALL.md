# 内置 Chromium 安装指南

## 适用场景

- 内网/信创环境：无法访问 Playwright 默认下载源
- 离线环境：完全没网络
- 容器化部署：希望 Chromium 跟代码一起打包

## 方法 1：从其他机器复制（推荐）

在任何有网络的机器上跑：

```bash
# Windows
python -m playwright install chromium
# Chromium 默认安装到: %LOCALAPPDATA%\ms-playwright\chromium-<rev>\chrome-win\chrome.exe

# Linux
python -m playwright install --with-deps chromium
# Chromium 默认安装到: ~/.cache/ms-playwright/chromium-<rev>/chrome-linux/chrome

# macOS
python -m playwright install chromium
# Chromium 默认安装到: ~/Library/Caches/ms-playwright/chromium-<rev>/chrome-mac/Chromium.app
```

把整个 `chrome-win/`（或 `chrome-linux/`、`chrome-mac/`）目录复制到本项目的：

```
<project>/src/infrastructure/buildin_tools/chromium/
```

> ⚠️ 不要复制最外层 `chromium-<rev>/` 目录，只复制里面的 `chrome-win/` 等子目录。

## 方法 2：国内镜像（推荐墙内用户）

```bash
# 设置国内镜像（阿里云）
export PLAYWRIGHT_DOWNLOAD_HOST=https://npmmirror.com/mirrors/playwright

# 安装
python -m playwright install chromium
```

复制步骤同上。

## 方法 3：Docker 构建时安装

在 `Dockerfile` 中：

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
    libdrm2 libdbus-1-3 libxkbcommon0 libxcomposite1 libxdamage1 \
    libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 libcairo2 libasound2 \
    && rm -rf /var/lib/apt/lists/*

RUN pip install playwright && playwright install --with-deps chromium
```

## 方法 4：CI/CD 自动下载

在 CI pipeline 中跑：

```yaml
- name: Install Chromium
  run: |
    python -m playwright install chromium
    cp -r ~/.cache/ms-playwright/chromium-*/chrome-linux src/infrastructure/buildin_tools/chromium/
```

## 验证安装

跑以下命令，确认 non_head_browser 能找到内置 Chromium：

```powershell
python -c "import non_head_browser; print(non_head_browser._find_chromium_executable())"
```

如果返回 `None`，说明内置 Chromium 没装好；返回路径则正常。

## 版本兼容性

内置 Chromium 需要跟 Playwright Python SDK 版本兼容。建议：

| Playwright 版本 | Chromium 版本 |
|---------------|-------------|
| 1.40.x        | 120.0.x     |
| 1.45.x        | 125.0.x     |
| 1.50.x        | 130.0.x     |

完整对应表见：<https://github.com/microsoft/playwright/blob/main/packages/playwright-core/browsers.json>
