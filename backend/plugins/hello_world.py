DESCRIPTION = "一个示例插件，打印 Hello World"
VERSION = "1.0.0"
AUTHOR = "Trae"

def run(context, **kwargs):
    context.log("Hello from Plugin!")
    
    name = kwargs.get("name", "Guest")
    context.log(f"Welcome, {name}!")
    
    # 演示使用 context 获取工具
    try:
        # 尝试获取 ADB 工具
        adb = context.adb
        if adb:
            context.log("ADB 工具已就绪")
            # 这里可以调用 adb 的方法，例如 adb.get_devices()
            # devices = adb.get_devices()
            # context.log(f"当前设备: {devices}")
    except Exception as e:
        context.log(f"ADB 工具检查跳过: {e}")
        
    return {"message": f"Hello {name}, plugin executed successfully!"}
