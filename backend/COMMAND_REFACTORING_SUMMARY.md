# 命令行执行方法重构总结

## 重构目标
将backend目录中所有命令行执行方法解耦并抽象为公共基础方法，实现全局调用。

## 完成的工作

### 1. 分析现有代码结构
- 分析了所有服务文件中的命令行执行方法
- 识别出三种主要的命令执行模式：
  - `BaseService.run_command()` - 基础系统命令执行
  - `ToolService.run_tool_command()` - 工具特定命令执行
  - 各服务使用 `tool_service.run_tool_command()` - 间接工具命令执行

### 2. 设计统一的命令执行架构
创建了抽象的命令执行器架构：
- `CommandExecutor` - 抽象基类
- `SystemCommandExecutor` - 系统命令执行器
- `ToolCommandExecutor` - 工具命令执行器
- `CommandService` - 统一的命令服务管理器

### 3. 创建公共命令执行服务
创建了 `services/command_service.py`，包含：
- 统一的命令执行接口
- 执行前后钩子机制
- 错误处理和日志记录
- 全局单例访问模式

### 4. 重构各个服务文件
更新了以下文件以使用新的命令执行服务：

#### 核心服务文件
- `core/base_service.py` - 更新 `run_command` 方法使用 `CommandService`
- `services/tool_service.py` - 集成命令服务，重构工具命令执行
- `services/device_service.py` - 添加命令服务支持
- `services/apk_service.py` - 添加命令服务支持
- `services/log_service.py` - 添加命令服务支持

#### 工具函数
- `utils/system_utils.py` - 重构系统命令执行函数，优先使用命令服务

### 5. 实现的功能特性

#### 统一接口
```python
from services.command_service import get_command_service

command_service = get_command_service()

# 执行系统命令
result = command_service.execute_system_command(['cmd', '/c', 'echo hello'])

# 执行工具命令
result = command_service.execute_tool_command('adb', ['version'])
```

#### 全局便捷函数
```python
from services.command_service import execute_system_command, execute_tool_command

# 直接调用
result = execute_system_command(['cmd', '/c', 'echo hello'])
result = execute_tool_command('adb', ['version'])
```

#### 钩子机制
- 支持执行前后钩子，便于日志记录、监控等
- 可扩展的架构设计

#### 错误处理
- 统一的错误处理和异常管理
- 详细的日志记录
- 超时控制和资源管理

### 6. 向后兼容性
- 保持了原有API的兼容性
- 现有代码可以无缝迁移到新的命令执行服务
- 提供了回退机制，确保在命令服务不可用时仍能正常工作

## 架构优势

### 1. 解耦和抽象
- 将命令执行逻辑从具体服务中分离
- 提供了统一的抽象接口
- 便于维护和扩展

### 2. 可扩展性
- 支持添加新的命令执行器类型
- 钩子机制支持功能扩展
- 配置化的执行参数

### 3. 可测试性
- 独立的命令执行逻辑便于单元测试
- 模拟和存根支持
- 清晰的接口定义

### 4. 性能优化
- 单例模式避免重复初始化
- 工具路径缓存
- 资源复用

## 使用示例

### 基本使用
```python
# 获取命令服务
from services.command_service import get_command_service
command_service = get_command_service()

# 执行系统命令
result = command_service.execute_system_command(
    command=['cmd', '/c', 'dir'],
    cwd='C:\\',
    timeout=30
)

# 执行工具命令
result = command_service.execute_tool_command(
    tool_name='adb',
    args=['devices'],
    timeout=10
)
```

### 在服务中使用
```python
class MyService(BaseService):
    def __init__(self):
        super().__init__("MyService")
        self.command_service = get_command_service()
    
    def my_method(self):
        # 使用统一的命令执行接口
        result = self.command_service.execute_system_command(['echo', 'hello'])
        return result
```

## 总结
成功完成了命令行执行方法的解耦和抽象化重构，实现了：
- ✅ 统一的命令执行接口
- ✅ 全局可访问的命令服务
- ✅ 向后兼容的API设计
- ✅ 可扩展的架构模式
- ✅ 完整的错误处理和日志记录

重构后的代码结构更加清晰，维护性更强，为后续功能扩展奠定了良好的基础。