import { CommandService, ProcessManager, createCommandBuilder } from './src/main/services/commandService.js';

/**
 * CommandService 测试脚本
 */
async function testCommandService() {
    console.log('=== CommandService 功能测试开始 ===\n');

    // 创建 CommandService 实例
    const commandService = new CommandService({
        timeout: 10000, // 10秒超时
        cwd: process.cwd()
    });

    // 监听事件
    commandService.on('commandStart', (data) => {
        console.log(`[事件] 命令开始: ${data.command}`);
    });

    commandService.on('commandComplete', (data) => {
        console.log(`[事件] 命令完成: ${data.command}, 耗时: ${data.result.duration}ms`);
    });

    commandService.on('commandError', (data) => {
        console.log(`[事件] 命令错误: ${data.command}, 错误: ${data.error.message}`);
    });

    try {
        // 测试 1: 基本命令执行
        console.log('测试 1: 基本命令执行');
        console.log('执行命令: echo "Hello World"');
        const result1 = await commandService.execute('echo "Hello World"');
        console.log('输出:', result1.stdout);
        console.log('成功:', result1.success);
        console.log('耗时:', result1.duration + 'ms');
        console.log('进程ID:', result1.processId);
        console.log('');

        // 测试 2: 检查命令是否存在
        console.log('测试 2: 检查命令是否存在');
        const nodeExists = await commandService.commandExists('node');
        const fakeExists = await commandService.commandExists('nonexistentcommand123');
        console.log('node 命令存在:', nodeExists);
        console.log('假命令存在:', fakeExists);
        console.log('');

        // 测试 3: 获取命令路径
        console.log('测试 3: 获取命令路径');
        const nodePath = await commandService.getCommandPath('node');
        console.log('node 命令路径:', nodePath);
        console.log('');

        // 测试 4: 简化执行
        console.log('测试 4: 简化执行');
        const simpleOutput = await commandService.executeSimple('node --version');
        console.log('Node.js 版本:', simpleOutput);
        console.log('');

        // 测试 5: 命令构建器
        console.log('测试 5: 命令构建器');
        const builder = createCommandBuilder('echo')
            .arg('测试')
            .arg('命令构建器');
        
        console.log('构建的命令:', builder.toString());
        const builderResult = await builder.execute(commandService);
        console.log('输出:', builderResult.stdout);
        console.log('');

        // 测试 6: 进程管理
        console.log('测试 6: 进程管理');
        console.log('当前运行的进程数量:', commandService.getRunningProcessCount());
        const allProcesses = commandService.getAllProcesses();
        console.log('所有进程信息:');
        allProcesses.forEach(proc => {
            console.log(`  - ID: ${proc.id}, 命令: ${proc.command}, 状态: ${proc.status}`);
        });
        console.log('');

        // 测试 7: 错误处理
        console.log('测试 7: 错误处理');
        try {
            await commandService.execute('nonexistentcommand123');
        } catch (error) {
            console.log('预期的错误:', error.message);
        }
        console.log('');

        // 测试 8: 多命令串行执行
        console.log('测试 8: 多命令串行执行');
        const commands = [
            'echo "第一个命令"',
            'echo "第二个命令"',
            'echo "第三个命令"'
        ];
        const results = await commandService.executeCommands(commands);
        results.forEach((result, index) => {
            console.log(`命令 ${index + 1} 输出:`, result.stdout);
        });
        console.log('');

        // 测试 9: 实时回调执行
        console.log('测试 9: 实时回调执行');
        await commandService.executeWithCallback('echo "实时输出测试"', {
            onStdout: (data) => console.log('[实时输出]', data.trim()),
            onComplete: (result) => console.log('[完成] 耗时:', result.duration + 'ms')
        });
        console.log('');

        console.log('=== 所有测试完成 ===');

    } catch (error) {
        console.error('测试过程中发生错误:', error);
    } finally {
        // 清理
        commandService.cleanup();
        console.log('测试清理完成');
    }
}

/**
 * ProcessManager 独立测试
 */
async function testProcessManager() {
    console.log('\n=== ProcessManager 独立测试 ===\n');

    const processManager = new ProcessManager();

    // 监听事件
    processManager.on('processAdded', (data) => {
        console.log(`[事件] 进程添加: ${data.processId}`);
    });

    processManager.on('processRemoved', (data) => {
        console.log(`[事件] 进程移除: ${data.processId}`);
    });

    try {
        // 创建一个简单的子进程用于测试
        const { spawn } = await import('child_process');
        const childProcess = spawn('echo', ['ProcessManager测试'], { shell: true });

        // 添加到管理器
        const processId = processManager.addProcess(childProcess, 'echo ProcessManager测试');
        console.log('添加的进程ID:', processId);

        // 获取进程信息
        const processInfo = processManager.getProcessInfo(processId);
        console.log('进程信息:', processInfo);

        // 等待进程结束
        await new Promise((resolve) => {
            childProcess.on('close', resolve);
        });

        console.log('进程管理器测试完成');

    } catch (error) {
        console.error('ProcessManager 测试错误:', error);
    }
}

// 运行测试
async function runAllTests() {
    try {
        await testCommandService();
        await testProcessManager();
    } catch (error) {
        console.error('测试运行失败:', error);
        process.exit(1);
    }
}

// 如果直接运行此文件，则执行测试
if (import.meta.url === `file://${process.argv[1]}`) {
    runAllTests();
}

export { testCommandService, testProcessManager, runAllTests };