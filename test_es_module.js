// ES 模块兼容的 CommandService 测试
import fs from 'fs';
import path from 'path';
import { spawn } from 'child_process';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

console.log('开始测试 CommandService (ES 模块)...');

try {
    // 检查文件是否存在
    const servicePath = path.join(__dirname, 'src', 'main', 'services', 'commandService.js');
    console.log('检查文件路径:', servicePath);
    
    if (fs.existsSync(servicePath)) {
        console.log('✓ CommandService 文件存在');
        
        // 读取文件内容检查
        const content = fs.readFileSync(servicePath, 'utf8');
        console.log('文件大小:', content.length, '字符');
        
        // 检查关键类是否存在
        if (content.includes('class ProcessManager')) {
            console.log('✓ ProcessManager 类存在');
        }
        if (content.includes('class CommandService')) {
            console.log('✓ CommandService 类存在');
        }
        if (content.includes('class CommandBuilder')) {
            console.log('✓ CommandBuilder 类存在');
        }
        
        // 检查导出
        if (content.includes('export')) {
            console.log('✓ 包含 ES 模块导出');
        }
        
        // 尝试动态导入模块
        console.log('\n尝试导入 CommandService 模块...');
        try {
            const module = await import('./src/main/services/commandService.js');
            console.log('✓ 模块导入成功');
            console.log('导出的内容:', Object.keys(module));
            
            // 测试 CommandService 类
            if (module.CommandService) {
                console.log('✓ CommandService 类可用');
                
                // 创建实例
                const commandService = new module.CommandService();
                console.log('✓ CommandService 实例创建成功');
                
                // 测试基本方法
                if (typeof commandService.execute === 'function') {
                    console.log('✓ execute 方法存在');
                }
                if (typeof commandService.executeSimple === 'function') {
                    console.log('✓ executeSimple 方法存在');
                }
                
                // 测试简单命令
                console.log('\n测试简单命令执行...');
                try {
                    const result = await commandService.executeSimple('echo "Hello CommandService"');
                    console.log('✓ 命令执行成功，输出:', result.trim());
                } catch (error) {
                    console.log('✗ 命令执行失败:', error.message);
                }
                
                // 清理
                commandService.cleanup();
                console.log('✓ 清理完成');
            }
            
            // 测试 ProcessManager 类
            if (module.ProcessManager) {
                console.log('✓ ProcessManager 类可用');
                const processManager = new module.ProcessManager();
                console.log('✓ ProcessManager 实例创建成功');
            }
            
            // 测试 CommandBuilder
            if (module.createCommandBuilder) {
                console.log('✓ createCommandBuilder 函数可用');
                const builder = module.createCommandBuilder('echo').arg('test');
                console.log('✓ CommandBuilder 创建成功，命令:', builder.toString());
            }
            
        } catch (importError) {
            console.log('✗ 模块导入失败:', importError.message);
            console.log('错误详情:', importError.stack);
        }
        
    } else {
        console.log('✗ CommandService 文件不存在');
    }
    
    // 测试基本的 Node.js 功能
    console.log('\n测试基本功能:');
    console.log('Node.js 版本:', process.version);
    console.log('当前工作目录:', process.cwd());
    
    // 测试子进程
    console.log('\n测试子进程功能:');
    
    const child = spawn('echo', ['Hello from ES module'], { shell: true });
    
    child.stdout.on('data', (data) => {
        console.log('子进程输出:', data.toString().trim());
    });
    
    child.on('close', (code) => {
        console.log('子进程退出，代码:', code);
        console.log('\n✓ ES 模块测试完成');
    });
    
} catch (error) {
    console.error('测试过程中发生错误:', error.message);
    console.error('错误堆栈:', error.stack);
}