// 简单的 CommandService 测试
console.log('开始测试 CommandService...');

try {
    // 使用 require 导入 (CommonJS)
    const fs = require('fs');
    const path = require('path');
    
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
        
    } else {
        console.log('✗ CommandService 文件不存在');
    }
    
    // 测试基本的 Node.js 功能
    console.log('\n测试基本功能:');
    console.log('Node.js 版本:', process.version);
    console.log('当前工作目录:', process.cwd());
    
    // 测试子进程
    const { spawn } = require('child_process');
    console.log('\n测试子进程功能:');
    
    const child = spawn('echo', ['Hello from spawn'], { shell: true });
    
    child.stdout.on('data', (data) => {
        console.log('子进程输出:', data.toString().trim());
    });
    
    child.on('close', (code) => {
        console.log('子进程退出，代码:', code);
        console.log('\n✓ 基本测试完成');
    });
    
} catch (error) {
    console.error('测试过程中发生错误:', error.message);
    console.error('错误堆栈:', error.stack);
}