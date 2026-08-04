# Blank Tool

Blank Tool 是本地工作流编排桌面应用（Electron + Vue 3 + Python）：把本地命令行工具、脚本与运行时封装为**带类型化出入参的工具**，用**线性工作流**编排成可保存、可复用的模板，在任务中心或无头 CLI（`backend/cli.py`）中执行。模型通用、领域无关。

应用本体**不包含任何领域内容**：不内置工作流、工具描述符或二进制。仓库提供 `examples/` 可导入示例包（Android 工作流 + 工具描述符），经工作流/工具导入功能引入；二进制由用户自行准备（本地 `runtime/` 目录、自定义路径或系统 PATH）。该调整**已决策**，在分期计划中实施（见 [docs/05-分期开发计划.md](./docs/05-分期开发计划.md)）。

## 功能特性

通用核心是**工作流引擎与任务中心**：任何本地工具、脚本或运行时，封装为带类型化出入参的工具后，就能用线性工作流编排成可保存、可复用的模板，在任务中心或无头 CLI 中执行。下面的设备管理、APK 工具是内置便捷页面，依赖用户导入的工具描述符与自备二进制；导入前应用仍可完整使用通用工作流能力。

### 工作流与任务管理
- **远程下载**: 输入 URL 自动下载 APK，支持流式进度显示
- **一键操作**: 下载后自动执行分析、安装、反编译、重编译、重签名
- **任务队列**: 支持多任务并行，每个任务独立展开查看日志和输出
- **历史记录**: 任务记录本地持久化，重启不丢失

### 设备管理（需导入工具）
- **设备连接**: 自动检测 USB 设备，支持 ADB TCP/IP 远程连接
- **设备控制**: 重启系统 / 恢复模式 / Bootloader，Shell 命令执行
- **应用管理**: 安装 APK/AAB/APKS，卸载、导出应用
- **Logcat**: 实时日志输出，支持按设备过滤

### APK 工具（需导入工具）
- **应用分析**: 解析包名、版本、权限、SDK 信息
- **反编译/重编译**: 集成 Apktool，支持资源/源码选择性反编译
- **签名工具**: 支持自定义签名配置管理，V2 签名方案

### 主题系统
- **三模式切换**: 浅色 / 深色 / 自动（跟随系统）
- **CSS 变量驱动**: 全局统一配色，无缝切换

## 技术栈

- **前端**: Vue 3, Vite, Pinia, Vue Router, Naive UI
- **桌面框架**: Electron
- **后端**: Python 3 (JSON-RPC over stdin/stdout)
- **构建**: electron-builder（版本号由 package.json 驱动，发版脚本统一维护）

## 快速开始

### 环境要求
- Node.js 18+
- Python 3.10+（主进程先尝试 `runtime/python`，缺省回退系统 Python，实际以系统 Python 为准）
- Git (版本号管理)

> Android 相关能力需先导入 `examples/` 中的工作流与工具描述符，并自备二进制（本地 `runtime/`、自定义工具路径或系统 PATH）；导入前通用工作流能力不受影响。

### 开发

```bash
npm install          # 安装依赖
npm run dev          # 启动开发模式 (Vite HMR + Electron)
npm run lint         # 类型检查
npm run test         # 契约测试
npm run check        # lint + typecheck + test
```

### 打包

```bash
npm run build:win    # Windows (.exe)
npm run build:mac    # macOS (.dmg)
npm run build:linux  # Linux (AppImage)
```

版本号直接读取 package.json.version；发版时由 `npm run release` 自动 bump。

### 发布

```bash
npm run release                # 一键发布：质量门禁 + bump + tag + 构建 + GitHub Release
npm run release -- --dry-run   # 仅预览版本号与 release notes，不做修改
```

详细用法与失败恢复方法见 `.agents/rules/RELEASE_GUIDE.md`。

## 项目结构

```
blank_tool/
├── backend/                    # Python 后端
│   ├── app/
│   │   ├── handlers/           # API 处理器 (adb, apk, download, cache...)
│   │   ├── tools/              # 工具封装 (adb, apktool, bundletool...)
│   │   └── common/             # 公共模块 (decorators, exceptions...)
│   ├── plugins/                # 插件系统
│   └── main.py                 # 后端入口
├── src/
│   ├── main/                   # Electron 主进程
│   │   └── ipc/                # IPC 处理 (command, config, electron)
│   ├── preload/                # contextBridge 预加载
│   ├── renderer/               # Vue 3 前端
│   │   ├── views/              # 页面 (PackagePage, DevicePage, Settings...)
│   │   ├── components/         # 组件 (DeviceManager, StatusBar...)
│   │   ├── stores/             # Pinia 状态 (task, signature, index...)
│   │   ├── services/           # 服务层 (ServiceManager DI 容器)
│   │   ├── composables/        # 组合式函数
│   │   ├── i18n/               # 国际化 (zh-CN, en-US)
│   │   └── assets/styles/      # 样式 (themes, components)
│   └── shared/                 # 共享代码 (IPC channels, config)
├── scripts/                    # 构建脚本 (build.mjs)
├── examples/                   # 可导入示例（tracked，不随包分发）：Android 工作流 + 工具描述符
├── runtime/                    # 本地可选（gitignored，不随仓库/不随包分发）：ADB, JDK, Apktool 等自备二进制
└── dist/                       # 构建输出
```

## 架构

```
Renderer (Vue 3)  ←→  Main (Electron)  ←→  Python Backend
  window.electronAPI    IPC handlers        stdin/stdout JSON-RPC
```

- **Renderer → Main**: `contextBridge` 暴露 `electronAPI`，调用 IPC handler
- **Main → Python**: 主进程 spawn Python 子进程，通过 stdin 发送 JSON-RPC 请求，stdout 读取响应
- **流式传输**: 后端 `@streaming` 处理器在独立线程运行，通过 `stream-event` IPC 通道推送数据
- **服务发现**: 后端自动扫描 `app/handlers/` 下的 `API_MAP`，前端通过 `ServiceManager` DI 容器管理服务

## 配置

- **超时时间**: 设置 → 请求超时 (10-600s)
- **签名管理**: 设置 → 签名配置 (添加 keystore 路径、别名、密码)
- **主题**: 右上角切换浅色/深色/自动

## 许可证

ISC License
