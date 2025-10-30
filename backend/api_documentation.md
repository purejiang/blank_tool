# Android开发工具 - API文档

## 概述

本文档描述了重构后的Android开发工具的API接口。重构后的架构采用了统一的Python API设计，提供了更好的模块化、错误处理和扩展性。

## 架构概述

### 核心组件

1. **主进程 (main.js)** - Electron主进程，负责窗口管理和IPC通信
2. **渲染进程 (src/)** - 前端界面和用户交互
3. **Python后端 (backend/)** - 核心业务逻辑和工具集成

### 统一API设计

所有Python后端功能通过统一的`callPythonAPI(action, params)`函数调用：

```javascript
// 主进程中的统一API调用
async function callPythonAPI(action, params = {}) {
  // 构建命令行参数
  const args = ['--action', action];
  if (Object.keys(params).length > 0) {
    args.push('--params', JSON.stringify(params));
  }
  
  // 执行Python脚本并返回结果
  const pythonProcess = spawn(pythonPath, [scriptPath, ...args]);
  // ... 处理输出和错误
}
```

## API接口列表

### 系统信息相关

#### system.info
获取系统基本信息

**参数：** 无

**返回值：**
```json
{
  "success": true,
  "system_info": {
    "platform": "Windows-10-10.0.19045-SP0",
    "python_version": "3.12.0",
    "hostname": "DESKTOP-ABC123",
    "cpu_count": 8,
    "memory": "16.0 GB",
    "disk_usage": "512.5 GB / 1.0 TB"
  }
}
```

#### system.dependencies
检查系统依赖项

**参数：** 无

**返回值：**
```json
{
  "success": true,
  "dependencies": {
    "python": { "available": true, "version": "3.12.0" },
    "java": { "available": true, "version": "11.0.0" }
  }
}
```

#### system.status
获取所有服务的状态信息

**参数：** 无

**返回值：**
```json
{
  "success": true,
  "status": {
    "ToolService": {
      "name": "ToolService",
      "project_root": "F:\\cyanrain\\electron\\blank_tool",
      "tools_dir": "F:\\cyanrain\\electron\\blank_tool\\tools",
      "cached_tools": 5,
      "tools_status": {
        "adb": { "available": true, "path": "F:\\cyanrain\\electron\\blank_tool\\tools\\adb\\adb.exe" },
        "apktool": { "available": true, "path": "F:\\cyanrain\\electron\\blank_tool\\tools\\apktool\\apktool_2.12.1.jar" }
      }
    },
    "DeviceService": {
      "name": "DeviceService",
      "adb_available": true,
      "monitoring": false,
      "connected_devices": 1
    }
  }
}
```

### 工具管理相关

#### tool.check
检查指定工具的可用性

**参数：**
```json
{
  "tool_name": "adb",
  "tool_type": "adb"
}
```

**返回值：**
```json
{
  "available": true,
  "path": "F:\\cyanrain\\electron\\blank_tool\\tools\\adb\\adb.exe",
  "version": "Android Debug Bridge version 1.0.41",
  "tool_name": "adb"
}
```

#### tool.run
运行工具命令

**参数：**
```json
{
  "tool_name": "adb",
  "args": ["devices"],
  "tool_type": "adb"
}
```

**返回值：**
```json
{
  "success": true,
  "stdout": "List of devices attached\nemulator-5554\tdevice\n",
  "stderr": "",
  "exit_code": 0
}
```

### 设备管理相关

#### device.list
获取连接的Android设备列表

**参数：** 无

**返回值：**
```json
{
  "success": true,
  "devices": [
    {
      "id": "172bf045",
      "status": "device",
      "model": "Redmi Note 8 Pro",
      "device": "begonia",
      "transport_id": "1",
      "product": "begonia",
      "android_version": "11",
      "api_level": "30",
      "manufacturer": "Xiaomi",
      "brand": "Redmi"
    }
  ],
  "count": 1
}
```

#### device.info
获取指定设备的详细信息

**参数：**
```json
{
  "device_id": "172bf045"
}
```

**返回值：**
```json
{
  "success": true,
  "device": {
    "id": "172bf045",
    "status": "device",
    "model": "Redmi Note 8 Pro",
    "android_version": "11",
    "api_level": "30",
    "manufacturer": "Xiaomi",
    "brand": "Redmi",
    "build_id": "RKQ1.200928.002",
    "build_number": "V12.5.3.0.RGGCNXM"
  }
}
```

#### device.install.apk
安装APK文件到设备

**参数：**
```json
{
  "apk_path": "/path/to/app.apk"
}
```

**返回值：**
```json
{
  "success": true,
  "message": "APK安装成功",
  "package_name": "com.example.app"
}
```

#### device.install.aab
安装AAB文件到默认设备

**参数：**
```json
{
  "aab_path": "/path/to/app.aab"
}
```

**返回值：**
```json
{
  "success": true,
  "message": "AAB安装成功"
}
```

#### device.install.apks
安装APKS文件到默认设备

**参数：**
```json
{
  "apks_path": "/path/to/app.apks"
}
```

**返回值：**
```json
{
  "success": true,
  "message": "APKS安装成功"
}
```

#### device.uninstall
从默认设备卸载应用

**参数：**
```json
{
  "package_name": "com.example.app"
}
```

**返回值：**
```json
{
  "success": true,
  "message": "应用卸载成功"
}
```

#### device.packages
获取设备上已安装的应用包列表

**参数：**
```json
{
  "device_id": "172bf045"
}
```

**返回值：**
```json
{
  "success": true,
  "packages": [
    "com.example.app1",
    "com.example.app2"
  ],
  "count": 2
}
```

#### device.export
从设备导出APK文件

**参数：**
```json
{
  "package_name": "com.example.app",
  "device_id": "172bf045",
  "output_dir": "/path/to/output"
}
```

**返回值：**
```json
{
  "success": true,
  "message": "APK导出成功",
  "apk_path": "/path/to/output/com.example.app.apk"
}
```

#### device.reboot
重启设备

**参数：**
```json
{
  "device_id": "172bf045",
  "mode": "normal"
}
```

**返回值：**
```json
{
  "success": true,
  "message": "设备重启命令已发送"
}
```

#### device.shell
在设备上执行shell命令

**参数：**
```json
{
  "device_id": "172bf045",
  "command": "ls /sdcard"
}
```

**返回值：**
```json
{
  "success": true,
  "stdout": "Download\nPictures\nMusic\n",
  "stderr": "",
  "exit_code": 0
}
```

#### device.monitor.start
开始设备监控

**参数：** 无

**返回值：**
```json
{
  "success": true,
  "message": "设备监控已启动"
}
```

#### device.monitor.stop
停止设备监控

**参数：** 无

**返回值：**
```json
{
  "success": true,
  "message": "设备监控已停止"
}
```

#### device.monitor.realtime
开始实时设备监控

**参数：** 无

**返回值：**
```json
{
  "success": true,
  "message": "实时设备监控已启动"
}
```

### APK分析相关

#### apk.analyze
分析APK文件并提取信息

**参数：**
```json
{
  "apk_path": "/path/to/app.apk"
}
```

**返回值：**
```json
{
  "success": true,
  "analysis": {
    "package_name": "com.example.app",
    "version_name": "1.0.0",
    "version_code": 1,
    "min_sdk_version": 21,
    "target_sdk_version": 30,
    "permissions": ["android.permission.INTERNET"],
    "activities": ["MainActivity"],
    "services": [],
    "receivers": [],
    "file_size": 5242880
  }
}
```

#### apk.info
获取APK基本信息

**参数：**
```json
{
  "apk_path": "/path/to/app.apk"
}
```

**返回值：**
```json
{
  "success": true,
  "apk_info": {
    "package_name": "com.example.app",
    "version_name": "1.0.0",
    "version_code": 1,
    "min_sdk_version": 21,
    "target_sdk_version": 30,
    "app_name": "Example App",
    "file_size": 5242880,
    "install_location": "auto"
  }
}
```

#### apk.extract
提取APK资源文件

**参数：**
```json
{
  "apk_path": "/path/to/app.apk",
  "output_dir": "/path/to/output"
}
```

**返回值：**
```json
{
  "success": true,
  "message": "APK资源提取成功",
  "output_dir": "/path/to/output",
  "extracted_files": [
    "AndroidManifest.xml",
    "resources.arsc",
    "classes.dex"
  ]
}
```

### AAB转换相关

#### aab.convert
将AAB文件转换为APKS文件

**参数：**
```json
{
  "aab_path": "/path/to/app.aab"
}
```

**返回值：**
```json
{
  "success": true,
  "message": "AAB转换为APKS成功",
  "apks_path": "/temp/app.apks"
}
```

### 日志管理相关

#### log.start
开始logcat日志监控

**参数：**
```json
{
  "deviceId": "172bf045",
  "logLevel": "V",
  "tagFilter": ""
}
```

**返回值：**
```json
{
  "success": true,
  "message": "Logcat已启动",
  "device_id": "172bf045",
  "log_level": "V"
}
```

#### log.stop
停止logcat日志监控

**参数：**
```json
{
  "deviceId": "172bf045"
}
```

**返回值：**
```json
{
  "success": true,
  "message": "Logcat已停止",
  "device_id": "172bf045"
}
```

#### log.export
导出设备日志到文件

**参数：**
```json
{
  "deviceId": "172bf045",
  "outputPath": "/path/to/output.log",
  "logLevel": "V",
  "tagFilter": "",
  "maxLines": 1000
}
```

**返回值：**
```json
{
  "success": true,
  "message": "日志导出成功",
  "output_path": "/path/to/output.log",
  "lines_exported": 856
}
```

#### log.preview
获取日志预览

**参数：**
```json
{
  "deviceId": "172bf045",
  "maxLines": 100
}
```

**返回值：**
```json
{
  "success": true,
  "logs": [
    {
      "timestamp": "2024-01-01 12:00:00.123",
      "level": "I",
      "tag": "ActivityManager",
      "message": "Starting activity..."
    }
  ],
  "count": 100
}
```

### 缓存管理相关

#### cache.info
获取缓存信息

**参数：** 无

**返回值：**
```json
{
  "success": true,
  "cache_info": {
    "total_size": "256MB",
    "temp_files": 45,
    "log_files": 12,
    "apk_cache": "128MB",
    "last_cleanup": "2024-01-01 10:00:00"
  }
}
```

#### cache.clear
清理缓存

**参数：**
```json
{
  "cache_type": "all"
}
```

**返回值：**
```json
{
  "success": true,
  "message": "缓存清理完成",
  "freed_space": "128MB",
  "files_deleted": 32
}
```

#### cache.set
设置缓存数据

**参数：**
```json
{
  "key": "cache_key",
  "value": "cache_value",
  "ttl": 3600
}
```

**返回值：**
```json
{
  "success": true,
  "message": "缓存设置成功"
}
```

#### cache.get
获取缓存数据

**参数：**
```json
{
  "key": "cache_key"
}
```

**返回值：**
```json
{
  "success": true,
  "value": "cache_value",
  "exists": true
}
```

#### cache.delete
删除缓存数据

**参数：**
```json
{
  "key": "cache_key"
}
```

**返回值：**
```json
{
  "success": true,
  "message": "缓存删除成功"
}
```

#### cache.stats
获取缓存统计信息

**参数：** 无

**返回值：**
```json
{
  "success": true,
  "statistics": {
    "total_keys": 15,
    "memory_usage": "2.5MB",
    "hit_rate": 0.85,
    "miss_rate": 0.15
  }
}
```

## 工具管理相关

### check_dependencies
检查依赖工具

**参数：** 无

**返回值：**
```json
{
  "success": true,
  "dependencies": {
    "adb": {
      "available": true,
      "version": "1.0.41",
      "path": "F:\\tools\\adb\\adb.exe"
    },
    "aapt2": {
      "available": true,
      "version": "8.1.0",
      "path": "F:\\tools\\aapt2\\aapt2.exe"
    }
  }
}
```

### check_tool_availability
检查特定工具可用性

**参数：**
```json
{
  "tool_name": "adb"
}
```

**返回值：**
```json
{
  "success": true,
  "available": true,
  "tool_info": {
    "name": "adb",
    "version": "1.0.41",
    "path": "F:\\tools\\adb\\adb.exe"
  }
}
```

### run_tool_command
执行工具命令

**参数：**
```json
{
  "tool_name": "adb",
  "command": "devices",
  "args": ["-l"]
}
```

**返回值：**
```json
{
  "success": true,
  "stdout": "List of devices attached\n172bf045\tdevice\n",
  "stderr": "",
  "exit_code": 0
}
```

## 错误处理

所有API调用都遵循统一的错误处理格式：

```json
{
  "success": false,
  "error": "错误描述",
  "error_code": "ERROR_CODE",
  "details": {
    "additional": "error details"
  }
}
```

## IPC通信接口

### 主进程到渲染进程

所有IPC处理程序都使用`ipcMain.handle()`注册，支持异步操作：

```javascript
// APK分析
ipcMain.handle('analyze-apk', async (event, apkPath) => {
  return await callPythonAPI('analyze_apk', { apk_path: apkPath });
});

// 设备管理
ipcMain.handle('get-adb-devices', async () => {
  return await callPythonAPI('get_device_list');
});
```

### 渲染进程到主进程

渲染进程通过`ipcRenderer.invoke()`调用主进程功能：

```javascript
// 获取设备列表
const result = await ipcRenderer.invoke('get-adb-devices');

// 分析APK
const analysis = await ipcRenderer.invoke('analyze-apk', apkPath);
```

## 服务架构

### 渲染进程服务

1. **DeviceService** - 设备管理服务
2. **ApkService** - APK分析服务
3. **LogService** - 日志管理服务
4. **CacheService** - 缓存管理服务
5. **NotificationService** - 通知服务
6. **ThemeService** - 主题服务

### Python后端管理器

1. **DeviceManager** - 设备管理
2. **ApkManager** - APK分析
3. **ToolManager** - 工具管理
4. **LogManager** - 日志管理
5. **CacheManager** - 缓存管理

## 配置和部署

### 开发环境

```bash
# 安装依赖
npm install

# 启动开发服务器
npm start

# 测试Python后端
cd backend
python main.py --action get_system_info
```

### 生产环境

```bash
# 构建应用
npm run build

# 打包分发
npm run dist
```

## 更新日志

### v2.0.0 (重构版本)
- 重构为统一的Python API架构
- 改进错误处理和日志记录
- 优化模块化设计
- 增强代码可维护性
- 添加完整的API文档

### v1.0.0 (初始版本)
- 基础APK分析功能
- ADB设备管理
- 简单的日志系统
- 基础缓存管理