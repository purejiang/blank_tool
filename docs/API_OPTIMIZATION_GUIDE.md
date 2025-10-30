# 前后端API调用逻辑优化指南

## 概述

本文档记录了基于 `/backend/main.py` 文档标准对前后端调用逻辑的优化改进。

## 优化内容

### 1. 统一后端API调用接口

#### 优化前
- 每个功能都有独立的IPC处理器
- 重复的错误处理和配置传递逻辑
- 不一致的参数传递方式

#### 优化后
- 引入统一的 `call-backend-api` IPC处理器
- 集中化的错误处理和响应格式标准化
- 统一的参数传递结构

```javascript
// 新的统一调用方式
const result = await callBackendAPI(action, params);
```

### 2. 标准化响应格式

#### 成功响应
```javascript
{
    success: true,
    data: {...},
    message: "操作成功"
}
```

#### 错误响应
```javascript
{
    success: false,
    error: "错误信息",
    action: "操作名称",
    timestamp: "2024-01-01T00:00:00.000Z"
}
```

### 3. 错误处理优化

#### 新增ErrorHandler工具类
- 统一的错误处理逻辑
- 自动重试机制
- 用户友好的错误提示
- 错误统计和日志记录

```javascript
// 使用示例
const result = await window.errorHandler.withRetry(
    async () => {
        return await window.electronAPI.analyzeApk(filePath);
    },
    'APK分析',
    { 
        showNotification: true,
        userMessage: 'APK分析失败，请检查文件是否有效'
    }
);
```

### 4. 主要修改文件

#### 后端文件
- `src/main/main.js` - 添加统一的 `callBackendAPI` 函数

#### 前端文件
- `src/renderer/utils/ErrorHandler.js` - 新增错误处理工具类
- `src/renderer/components/pages/ApkPage.js` - 更新使用新的错误处理
- `src/renderer/app.js` - 初始化错误处理器
- `src/renderer/index.html` - 引入错误处理工具类

### 5. 优化效果

1. **代码复用性提升** - 统一的API调用和错误处理逻辑
2. **维护性增强** - 集中化的配置和错误处理
3. **用户体验改善** - 更友好的错误提示和自动重试
4. **开发效率提高** - 标准化的响应格式和调用方式

### 6. 使用指南

#### 添加新的API调用
1. 在后端 `main.py` 中添加对应的action处理
2. 前端直接使用 `window.electronAPI` 对应方法
3. 使用 `window.errorHandler.withRetry` 包装需要错误处理的调用

#### 错误处理最佳实践
1. 使用统一的ErrorHandler工具类
2. 为用户提供友好的错误信息
3. 记录详细的错误日志用于调试
4. 合理使用重试机制

## 兼容性说明

- 保持了原有API接口的兼容性
- 现有功能无需修改即可使用新的错误处理
- 逐步迁移到新的调用方式

## 后续改进建议

1. 添加API调用性能监控
2. 实现更智能的重试策略
3. 增加离线模式支持
4. 优化大文件传输处理