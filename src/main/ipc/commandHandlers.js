import { ipcMain } from 'electron';
import path from 'path';
import { fileURLToPath } from 'url';
import { CommandService } from '../services/commandService.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

export function setupCommandHandlers() {
    const commandService = new CommandService({
        timeout: 10000, // 10秒超时
        cwd: process.cwd()
    });
    // 统一的后端API调用处理器
    ipcMain.handle('call-backend-api', async (event, action, params = {}, options = {}) => {
        console.log(`[IPC] 执行call-backend-api: action=${action}, params= ${JSON.stringify(params)}, options= ${JSON.stringify(options)}`);
        const projectRoot = path.resolve(__dirname, '../../..');
        const backendMainPath = path.join(projectRoot, 'backend', 'main.py');
        const pythonPath = options.python_path+"\\python.exe";
        const command = `${pythonPath} ${backendMainPath} --action=${action} --params=${JSON.stringify(params)}`;

        const result = await commandService.execute(command, options);
        console.log(`[IPC] call-backend-api 执行结果: ${JSON.stringify(result)}`);
        return result;       
    });

    // 统一的命令行调用处理器
    ipcMain.handle('call-command', async (event, command, options = {}) => {
        console.log(`[IPC] 执行call-command: command=${command}, options=`, options);
        const result = await commandService.execute(command, options);
        console.log(`[IPC] call-command 执行结果: ${JSON.stringify(result)}`);
        return result;
    });
}