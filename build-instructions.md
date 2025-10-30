# Electron + Python 应用打包说明

## 概述

本文档说明如何将包含Python脚本的Electron应用打包成独立的可执行文件。

## 打包准备

### 1. 确保所有依赖已安装

```bash
npm install
```

### 2. 验证Python运行时环境

确保 `python_runtime` 目录包含完整的Python 3.12.4 Embeddable Package：

```
python_runtime/
├── python.exe
├── pythonw.exe
├── python312.dll
├── python312.zip
├── python312._pth
└── ... (其他必要文件)
```

### 3. 验证Python脚本

确保 `backend` 目录包含所有需要的Python脚本：

```
backend/
├── hello.py
└── data_processor.py
```

## 打包命令

### Windows 平台

```bash
# 构建Windows安装包 (NSIS)
npm run build:win

# 或者使用通用构建命令
npm run build
```

### macOS 平台

```bash
npm run build:mac
```

### Linux 平台

```bash
npm run build:linux
```

## 打包配置说明

### package.json 配置

```json
{
  "build": {
    "appId": "com.example.blank_tool",
    "productName": "Blank Tool",
    "directories": {
      "output": "dist"
    },
    "files": [
      "main.js",
      "index.html",
      "package.json",
      "backend/**/*",
      "python_runtime/**/*"
    ],
    "extraResources": [
      {
        "from": "backend",
        "to": "backend"
      },
      {
        "from": "python_runtime",
        "to": "python_runtime",
        "filter": ["**/*"]
      }
    ]
  }
}
```

### 关键配置说明

1. **files**: 指定要包含在应用包中的文件
2. **extraResources**: 将Python运行时和脚本复制到资源目录
3. **打包后路径处理**: main.js中的路径处理逻辑会自动检测是否为打包环境

## 路径处理机制

### 开发环境
- Python路径: `./python_runtime/python.exe`
- 脚本路径: `./backend/script.py`

### 打包后环境
- Python路径: `process.resourcesPath/python_runtime/python.exe`
- 脚本路径: `process.resourcesPath/backend/script.py`

## 测试打包结果

### 1. 构建应用

```bash
npm run build:win
```

### 2. 查看输出

打包完成后，在 `dist` 目录中会生成：
- `Blank Tool Setup 1.0.0.exe` (安装程序)
- `win-unpacked/` (未打包的应用文件)

### 3. 测试安装程序

1. 运行生成的安装程序
2. 安装应用到目标目录
3. 启动应用并测试Python功能

## 故障排除

### 常见问题

1. **Python脚本无法执行**
   - 检查 `python_runtime` 目录是否完整
   - 确认Python脚本语法正确
   - 查看控制台日志中的路径信息

2. **打包失败**
   - 确认所有依赖已安装
   - 检查 `package.json` 配置
   - 查看构建日志中的错误信息

3. **应用启动失败**
   - 检查主进程代码是否有语法错误
   - 确认资源文件路径正确

### 调试技巧

1. **开启开发者工具**
   ```javascript
   // 在 main.js 中取消注释
   mainWindow.webContents.openDevTools();
   ```

2. **查看控制台日志**
   - Python路径和脚本路径会在控制台中显示
   - 错误信息会包含详细的路径信息

3. **测试便携式Python**
   ```bash
   cd tools\python_runtime
   .\python.exe ..\backend\hello.py hello
   ```

## 优化建议

### 1. 减小包体积

- 移除不必要的Python模块
- 使用更小的Python发行版
- 压缩资源文件

### 2. 提高启动速度

- 预编译Python脚本为.pyc文件
- 优化Python脚本加载逻辑

### 3. 增强兼容性

- 测试不同Windows版本
- 包含必要的Visual C++运行时

## 部署注意事项

1. **目标系统要求**
   - Windows 10 或更高版本
   - 64位系统（如使用64位Python）

2. **安全考虑**
   - 代码签名证书（可选）
   - 防病毒软件白名单

3. **用户体验**
   - 提供详细的安装说明
   - 包含卸载程序
   - 支持自动更新（可选）

## 更新和维护

### Python版本更新

1. 下载新版本的Python Embeddable Package
2. 替换 `python_runtime` 目录内容
3. 测试兼容性
4. 重新打包

### 应用更新

1. 修改版本号（package.json）
2. 更新变更日志
3. 重新构建和测试
4. 发布新版本