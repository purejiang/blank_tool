# Blank Tool (Android 开发工具箱)

Blank Tool 是一个基于 Electron + Vue 3 + Python 构建的现代化 Android 开发辅助工具。它集成了常用的 Android 开发工具（ADB、Apktool 等），提供了一个直观的图形化界面，旨在简化开发者的日常工作流程。

## ✨ 功能特性

### 📱 设备管理
- **设备连接**: 自动检测并连接 USB/Wi-Fi Android 设备
- **设备控制**: 提供常用的 ADB 命令快捷操作（如重启、截屏、投屏等）
- **文件管理**: 浏览和管理设备文件系统
- **Logcat**: 实时查看设备日志，支持过滤和搜索

### 📦 应用管理 (APK/AAB)
- **应用安装**: 支持 APK 和 AAB (Android App Bundle) 格式文件的安装
- **应用分析**: 深度解析 APK 信息（包名、版本号、权限列表、签名信息等）
- **反编译/回编译**: 
    - 集成 Apktool，一键反编译 APK 资源
    - 支持修改后回编译生成新的 APK
- **签名工具**: 支持 V1/V2/V3 签名方案

### 🛠️ 核心架构
- **双进程通信**: 采用 JSON-RPC 风格的标准输入/输出 (Stdin/Stdout) 进行 Electron 主进程与 Python 后端的通信，确保高效稳定。
- **内置环境**: 
    - 内置 Python 运行时，无需用户单独配置 Python 环境
    - 内置 ADB、AAPT2、Apktool 等常用二进制工具

## 🏗️ 技术栈

- **前端 (Renderer)**: Vue 3, Vite, Pinia, Vue Router
- **桌面框架 (Main)**: Electron
- **后端 (Backend)**: Python 3 (负责处理复杂的业务逻辑和工具调用)
- **构建工具**: Electron Builder

## 🚀 快速开始

### 开发环境要求
- Node.js (v16+)
- Python 3.10+ (如果需要修改后端代码)

### 1. 安装依赖

```bash
# 安装前端和 Electron 依赖
npm install
```

### 2. 启动开发模式

```bash
npm run dev
```
此命令将同时启动：
- Vite 开发服务器 (前端热重载)
- Electron 主进程 (带开发者工具)

### 3. 构建打包

```bash
# 构建 Windows 版本 (生成 .exe)
npm run build:win

# 构建 macOS 版本
npm run build:mac

# 构建 Linux 版本
npm run build:linux
```

## 📂 项目结构

```
blank_tool/
├── backend/                # Python 后端代码
│   ├── app/                # 核心业务逻辑 (ADB, APK handlers)
│   ├── plugins/            # 插件系统
│   ├── tools/              # 外部工具封装 (adb.py, apktool.py 等)
│   └── main.py             # Python 进程入口
├── src/
│   ├── main/               # Electron 主进程
│   └── renderer/           # Vue 3 前端页面
├── runtime/                # 运行时依赖 (打包后的 Python 环境、二进制工具等)
├── dist/                   # 构建输出目录
├── package.json            # 项目配置
└── README.md               # 项目说明
```

## 📝 许可证

ISC License
