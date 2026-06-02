# Blank Tool (Android 开发工具箱)

Blank Tool 是一个基于 Electron + Vue 3 + Python 构建的现代化 Android 开发辅助工具。集成了常用的 Android 开发工具（ADB、Apktool、Bundletool 等），提供直观的图形化界面，简化开发者的日常工作流程。

## 功能特性

### 任务管理
- **远程下载**: 输入 URL 自动下载 APK，支持流式进度显示
- **一键操作**: 下载后自动执行分析、安装、反编译、重编译、重签名
- **任务队列**: 支持多任务并行，每个任务独立展开查看日志和输出
- **历史记录**: 任务记录本地持久化，重启不丢失

### 设备管理
- **设备连接**: 自动检测 USB 设备，支持 ADB TCP/IP 远程连接
- **设备控制**: 重启系统 / 恢复模式 / Bootloader，Shell 命令执行
- **应用管理**: 安装 APK/AAB/APKS，卸载、导出应用
- **Logcat**: 实时日志输出，支持按设备过滤

### APK 工具
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
- **构建**: electron-builder + git-tag 版本自动同步

## 快速开始

### 环境要求
- Node.js 18+
- Python 3.10+ (开发后端时)
- Git (版本号管理)

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

版本号自动从 `git describe --tags` 读取，打包时注入 `package.json`，完成后还原。

### 打 Tag 发布

```bash
git tag -a v2.0.0 -m "Release v2.0.0"
git push origin v2.0.0
```

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
├── runtime/                    # 内置运行时 (Python, ADB, JDK, Apktool...)
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
