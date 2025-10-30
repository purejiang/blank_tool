# Electron 桌面应用

这是一个基于 Electron 构建的桌面应用程序模板。

## 项目结构

```
blank_tool/
├── main.js          # 主进程文件
├── index.html       # 渲染进程页面
├── package.json     # 项目配置文件
└── README.md        # 项目说明文档
```

## 功能特性

- ✅ 基础的 Electron 应用框架
- ✅ 现代化的 UI 界面设计
- ✅ 版本信息显示
- ✅ 开发者工具集成
- ✅ 跨平台支持 (Windows, macOS, Linux)

## 快速开始

### 安装依赖

```bash
npm install
```

### 启动应用

```bash
npm start
```

### 开发模式

```bash
npm run dev
```

## 开发说明

### 主要文件说明

- **main.js**: Electron 主进程文件，负责创建和管理应用窗口
- **index.html**: 应用的主界面，包含 UI 和交互逻辑
- **package.json**: 项目配置文件，包含依赖和脚本

### 自定义配置

你可以在 `main.js` 中修改以下配置：

- 窗口大小：修改 `width` 和 `height` 属性
- 窗口图标：设置 `icon` 属性
- 开发者工具：取消注释 `openDevTools()` 行

## 构建打包

要构建应用程序，你可以使用 electron-builder 或 electron-packager：

```bash
# 安装 electron-builder
npm install electron-builder --save-dev

# 添加构建脚本到 package.json
# "build": "electron-builder"

# 构建应用
npm run build
```

## 技术栈

- [Electron](https://www.electronjs.org/) - 跨平台桌面应用框架
- [Node.js](https://nodejs.org/) - JavaScript 运行时
- [Chromium](https://www.chromium.org/) - 渲染引擎

## 许可证

ISC License