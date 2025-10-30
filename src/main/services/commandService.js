import { spawn } from 'child_process';
import { EventEmitter } from 'events';

/**
 * 进程管理器 - 用于跟踪和管理正在运行的进程
 */
class ProcessManager extends EventEmitter {
  constructor() {
    super();
    this.processes = new Map(); // 存储进程ID和进程对象的映射
    this.processCounter = 0;
    this.maxProcesses = 50; // 最大进程数限制
  }

  /**
   * 添加进程到管理器
   * @param {ChildProcess} childProcess - 子进程对象
   * @param {string} command - 命令字符串
   * @param {object} metadata - 进程元数据
   * @returns {string} - 进程ID
   */
  addProcess(childProcess, command, metadata = {}) {
    // 检查进程数量限制
    if (this.processes.size >= this.maxProcesses) {
      throw new Error(`进程数量已达到最大限制 (${this.maxProcesses})`);
    }

    const processId = `proc_${++this.processCounter}_${Date.now()}`;
    const processInfo = {
      process: childProcess,
      command,
      startTime: Date.now(),
      status: 'running',
      pid: childProcess.pid,
      ...metadata
    };

    this.processes.set(processId, processInfo);

    // 监听进程结束事件，自动清理
    childProcess.on('close', (code, signal) => {
      this.removeProcess(processId, { code, signal });
    });

    childProcess.on('error', (error) => {
      this.removeProcess(processId, { error });
    });

    this.emit('processAdded', { processId, processInfo });
    return processId;
  }

  /**
   * 从管理器中移除进程
   * @param {string} processId - 进程ID
   * @param {object} exitInfo - 退出信息
   */
  removeProcess(processId, exitInfo = {}) {
    if (this.processes.has(processId)) {
      const processInfo = this.processes.get(processId);
      processInfo.status = 'finished';
      processInfo.endTime = Date.now();
      processInfo.duration = processInfo.endTime - processInfo.startTime;
      processInfo.exitInfo = exitInfo;
      
      this.processes.delete(processId);
      this.emit('processRemoved', { processId, processInfo });
    }
  }

  /**
   * 终止指定进程
   * @param {string} processId - 进程ID
   * @param {string} signal - 终止信号，默认为 'SIGTERM'
   * @returns {boolean} - 是否成功终止
   */
  killProcess(processId, signal = 'SIGTERM') {
    if (!this.processes.has(processId)) {
      console.warn(`[PROCESS_MANAGER] 进程 ${processId} 不存在或已结束`);
      return false;
    }

    const processInfo = this.processes.get(processId);
    const childProcess = processInfo.process;

    try {
      console.log(`[PROCESS_MANAGER] 正在终止进程 ${processId} (${processInfo.command})`);
      
      if (process.platform === 'win32') {
        // Windows 平台使用更强制的终止方式
        childProcess.kill('SIGKILL');
      } else {
        // Unix-like 系统先尝试优雅终止
        childProcess.kill(signal);
        
        // 如果 3 秒后进程仍未结束，使用 SIGKILL 强制终止
        setTimeout(() => {
          if (this.processes.has(processId) && !childProcess.killed) {
            console.log(`[PROCESS_MANAGER] 强制终止进程 ${processId}`);
            childProcess.kill('SIGKILL');
          }
        }, 3000);
      }

      processInfo.status = 'terminating';
      this.emit('processKilled', { processId, signal });
      return true;
    } catch (error) {
      console.error(`[PROCESS_MANAGER] 终止进程失败:`, error);
      this.emit('processKillError', { processId, error });
      return false;
    }
  }

  /**
   * 终止所有正在运行的进程
   * @param {string} signal - 终止信号，默认为 'SIGTERM'
   * @returns {number} - 被终止的进程数量
   */
  killAllProcesses(signal = 'SIGTERM') {
    const runningProcesses = Array.from(this.processes.keys());
    let killedCount = 0;

    console.log(`[PROCESS_MANAGER] 正在终止所有进程 (${runningProcesses.length} 个)`);

    for (const processId of runningProcesses) {
      if (this.killProcess(processId, signal)) {
        killedCount++;
      }
    }

    this.emit('allProcessesKilled', { killedCount, signal });
    return killedCount;
  }

  /**
   * 获取进程信息
   * @param {string} processId - 进程ID
   * @returns {object|null} - 进程信息
   */
  getProcessInfo(processId) {
    if (!this.processes.has(processId)) {
      return null;
    }

    const processInfo = this.processes.get(processId);
    return {
      id: processId,
      command: processInfo.command,
      startTime: processInfo.startTime,
      status: processInfo.status,
      duration: Date.now() - processInfo.startTime,
      pid: processInfo.pid,
      metadata: processInfo.metadata || {}
    };
  }

  /**
   * 获取所有进程信息
   * @returns {Array} - 所有进程信息数组
   */
  getAllProcesses() {
    return Array.from(this.processes.keys()).map(processId => 
      this.getProcessInfo(processId)
    );
  }

  /**
   * 检查进程是否存在
   * @param {string} processId - 进程ID
   * @returns {boolean} - 进程是否存在
   */
  hasProcess(processId) {
    return this.processes.has(processId);
  }

  /**
   * 获取运行中的进程数量
   * @returns {number} - 运行中的进程数量
   */
  getRunningProcessCount() {
    return this.processes.size;
  }

  /**
   * 清理已结束的进程记录
   */
  cleanup() {
    const toRemove = [];
    for (const [processId, processInfo] of this.processes) {
      if (processInfo.status === 'finished' || processInfo.process.killed) {
        toRemove.push(processId);
      }
    }
    
    toRemove.forEach(processId => this.processes.delete(processId));
    this.emit('cleanup', { removedCount: toRemove.length });
  }
}

/**
 * 命令服务类 - 提供统一的命令执行接口
 */
class CommandService extends EventEmitter {
  constructor(options = {}) {
    super();
    this.processManager = new ProcessManager();
    this.defaultOptions = {
      timeout: 60000, // 60秒超时
      encoding: 'utf8',
      cwd: process.cwd(),
      env: process.env,
      shell: process.platform === 'win32' ? true : false,
      trackProcess: true,
      ...options
    };

    // 转发进程管理器事件
    this.processManager.on('processAdded', (data) => this.emit('processAdded', data));
    this.processManager.on('processRemoved', (data) => this.emit('processRemoved', data));
    this.processManager.on('processKilled', (data) => this.emit('processKilled', data));
  }

  /**
   * 解析命令字符串，分离命令和参数
   * @param {string} command - 完整的命令字符串
   * @returns {object} - 包含 cmd 和 args 的对象
   */
  parseCommand(command) {
    if (typeof command !== 'string') {
      throw new Error('命令必须是字符串类型');
    }

    const trimmed = command.trim();
    if (!trimmed) {
      throw new Error('命令不能为空');
    }

    // 简单的命令解析，支持引号包围的参数
    const args = [];
    let current = '';
    let inQuotes = false;
    let quoteChar = '';

    for (let i = 0; i < trimmed.length; i++) {
      const char = trimmed[i];
      
      if ((char === '"' || char === "'") && !inQuotes) {
        inQuotes = true;
        quoteChar = char;
      } else if (char === quoteChar && inQuotes) {
        inQuotes = false;
        quoteChar = '';
      } else if (char === ' ' && !inQuotes) {
        if (current) {
          args.push(current);
          current = '';
        }
      } else {
        current += char;
      }
    }

    if (current) {
      args.push(current);
    }

    if (args.length === 0) {
      throw new Error('无效的命令格式');
    }

    return {
      cmd: args[0],
      args: args.slice(1)
    };
  }

  /**
   * 执行命令
   * @param {string|object} command - 命令字符串或包含 cmd 和 args 的对象
   * @param {object} options - 执行选项
   * @returns {Promise} - 返回包含输出结果和进程ID的 Promise
   */
  async execute(command, options = {}) {
    return new Promise((resolve, reject) => {
      try {
        let cmd, args;
        
        // 解析命令
        if (typeof command === 'string') {
          const parsed = this.parseCommand(command);
          cmd = parsed.cmd;
          args = parsed.args;
        } else if (command && typeof command === 'object') {
          cmd = command.cmd;
          args = command.args || [];
        } else {
          throw new Error('无效的命令格式');
        }

        const spawnOptions = { ...this.defaultOptions, ...options };
        
        // 详细的命令行调用日志输出
        const commandString = `${cmd} ${args.join(' ')}`;
        console.log(`[COMMAND_SERVICE] 执行命令: ${commandString}`);
        console.log(`[COMMAND_SERVICE] 工作目录: ${spawnOptions.cwd}`);

        // 启动子进程
        const childProcess = spawn(cmd, args, spawnOptions);

        // 将进程添加到管理器中（如果启用跟踪）
        let processId = null;
        if (spawnOptions.trackProcess) {
          processId = this.processManager.addProcess(childProcess, commandString, {
            options: spawnOptions,
            type: 'execute'
          });
          console.log(`[COMMAND_SERVICE] 进程已添加到管理器，ID: ${processId}`);
        }

        let stdout = '';
        let stderr = '';
        let isResolved = false;
        const startTime = Date.now();

        // 设置超时
        const timeoutId = setTimeout(() => {
          if (!isResolved) {
            isResolved = true;
            console.log(`[COMMAND_SERVICE] 命令执行超时，正在终止进程...`);
            
            // 使用进程管理器终止进程
            if (processId) {
              this.processManager.killProcess(processId, 'SIGKILL');
            } else {
              // 直接终止进程
              if (process.platform === 'win32') {
                childProcess.kill('SIGKILL');
              } else {
                childProcess.kill('SIGTERM');
                setTimeout(() => {
                  if (!childProcess.killed) {
                    childProcess.kill('SIGKILL');
                  }
                }, 2000);
              }
            }
            
            const result = {
              success: false,
              code: null,
              signal: 'TIMEOUT',
              stdout: stdout.trim(),
              stderr: stderr.trim(),
              command: commandString,
              duration: spawnOptions.timeout,
              processId
            };
            
            const error = new Error(`命令执行超时 (${spawnOptions.timeout}ms): ${commandString}`);
            error.result = result;
            this.emit('commandTimeout', { command: commandString, processId, result });
            reject(error);
          }
        }, spawnOptions.timeout);

        // 捕获标准输出
        if (childProcess.stdout) {
          childProcess.stdout.setEncoding(spawnOptions.encoding);
          childProcess.stdout.on('data', (data) => {
            stdout += data;
            console.log(`[STDOUT] ${data.toString().trim()}`);
            this.emit('stdout', { processId, data: data.toString() });
          });
        }

        // 捕获错误输出
        if (childProcess.stderr) {
          childProcess.stderr.setEncoding(spawnOptions.encoding);
          childProcess.stderr.on('data', (data) => {
            stderr += data;
            console.error(`[STDERR] ${data.toString().trim()}`);
            this.emit('stderr', { processId, data: data.toString() });
          });
        }

        // 处理进程退出
        childProcess.on('close', (code, signal) => {
          clearTimeout(timeoutId);
          
          if (isResolved) return;
          isResolved = true;

          console.log(`[COMMAND_SERVICE] 命令执行完成，退出码: ${code}, 信号: ${signal}`);

          const result = {
            success: code === 0,
            code,
            signal,
            stdout: stdout.trim(),
            stderr: stderr.trim(),
            command: commandString,
            duration: Date.now() - startTime,
            processId
          };

          this.emit('commandComplete', { command: commandString, processId, result });

          if (code === 0) {
            resolve(result);
          } else {
            const error = new Error(`命令执行失败 (退出码: ${code}): ${commandString}`);
            error.result = result;
            this.emit('commandError', { command: commandString, processId, result, error });
            reject(error);
          }
        });

        // 处理进程错误
        childProcess.on('error', (error) => {
          clearTimeout(timeoutId);
          
          if (isResolved) return;
          isResolved = true;

          console.error(`[COMMAND_SERVICE] 命令执行错误:`, error);
          
          const enhancedError = new Error(`命令执行失败: ${error.message}`);
          enhancedError.originalError = error;
          enhancedError.command = commandString;
          enhancedError.processId = processId;
          
          this.emit('commandError', { command: commandString, processId, error: enhancedError });
          reject(enhancedError);
        });

        this.emit('commandStart', { command: commandString, processId, childProcess });

      } catch (error) {
        console.error(`[COMMAND_SERVICE] 命令解析错误:`, error);
        this.emit('commandParseError', { command, error });
        reject(error);
      }
    });
  }

  /**
   * 执行命令并只返回输出结果（简化版本）
   * @param {string|object} command - 命令字符串或包含 cmd 和 args 的对象
   * @param {object} options - 执行选项
   * @returns {Promise<string>} - 返回标准输出内容
   */
  async executeSimple(command, options = {}) {
    try {
      const result = await this.execute(command, options);
      return result.stdout;
    } catch (error) {
      throw error;
    }
  }

  /**
   * 执行命令并实时获取输出
   * @param {string|object} command - 命令字符串或包含 cmd 和 args 的对象
   * @param {object} callbacks - 回调函数对象
   * @param {object} options - 执行选项
   * @returns {Promise} - 返回执行结果和进程ID
   */
  async executeWithCallback(command, callbacks = {}, options = {}) {
    return new Promise((resolve, reject) => {
      try {
        let cmd, args;
        
        // 解析命令
        if (typeof command === 'string') {
          const parsed = this.parseCommand(command);
          cmd = parsed.cmd;
          args = parsed.args;
        } else if (command && typeof command === 'object') {
          cmd = command.cmd;
          args = command.args || [];
        } else {
          throw new Error('无效的命令格式');
        }

        const spawnOptions = { ...this.defaultOptions, timeout: 30000, ...options };
        
        const commandString = `${cmd} ${args.join(' ')}`;
        console.log(`[COMMAND_SERVICE] 执行命令: ${commandString}`);

        // 启动子进程
        const childProcess = spawn(cmd, args, spawnOptions);

        // 将进程添加到管理器中（如果启用跟踪）
        let processId = null;
        if (spawnOptions.trackProcess) {
          processId = this.processManager.addProcess(childProcess, commandString, {
            options: spawnOptions,
            type: 'executeWithCallback'
          });
          console.log(`[COMMAND_SERVICE] 进程已添加到管理器，ID: ${processId}`);
        }

        let stdout = '';
        let stderr = '';
        let isResolved = false;
        const startTime = Date.now();

        // 设置超时
        const timeoutId = setTimeout(() => {
          if (!isResolved) {
            isResolved = true;
            
            // 使用进程管理器终止进程
            if (processId) {
              this.processManager.killProcess(processId, 'SIGKILL');
            } else {
              childProcess.kill('SIGTERM');
            }
            
            reject(new Error(`命令执行超时 (${spawnOptions.timeout}ms): ${commandString}`));
          }
        }, spawnOptions.timeout);

        // 捕获标准输出
        if (childProcess.stdout) {
          childProcess.stdout.setEncoding(spawnOptions.encoding);
          childProcess.stdout.on('data', (data) => {
            stdout += data;
            if (callbacks.onStdout) {
              callbacks.onStdout(data.toString());
            }
          });
        }

        // 捕获错误输出
        if (childProcess.stderr) {
          childProcess.stderr.setEncoding(spawnOptions.encoding);
          childProcess.stderr.on('data', (data) => {
            stderr += data;
            if (callbacks.onStderr) {
              callbacks.onStderr(data.toString());
            }
          });
        }

        // 处理进程退出
        childProcess.on('close', (code, signal) => {
          clearTimeout(timeoutId);
          
          if (isResolved) return;
          isResolved = true;

          const result = {
            success: code === 0,
            code,
            signal,
            stdout: stdout.trim(),
            stderr: stderr.trim(),
            command: commandString,
            duration: Date.now() - startTime,
            processId
          };

          if (callbacks.onComplete) {
            callbacks.onComplete(result);
          }

          if (code === 0) {
            resolve(result);
          } else {
            const error = new Error(`命令执行失败 (退出码: ${code}): ${commandString}`);
            error.result = result;
            reject(error);
          }
        });

        // 处理进程错误
        childProcess.on('error', (error) => {
          clearTimeout(timeoutId);
          
          if (isResolved) return;
          isResolved = true;

          if (callbacks.onError) {
            callbacks.onError(error);
          }
          
          const enhancedError = new Error(`命令执行失败: ${error.message}`);
          enhancedError.originalError = error;
          enhancedError.command = commandString;
          enhancedError.processId = processId;
          reject(enhancedError);
        });

        // 返回子进程对象，允许外部控制
        if (callbacks.onStart) {
          callbacks.onStart(childProcess, processId);
        }

      } catch (error) {
        console.error(`[COMMAND_SERVICE] 命令解析错误:`, error);
        reject(error);
      }
    });
  }

  /**
   * 检查命令是否存在
   * @param {string} command - 要检查的命令名
   * @returns {Promise<boolean>} - 命令是否存在
   */
  async commandExists(command) {
    try {
      const checkCmd = process.platform === 'win32' 
        ? `where ${command}` 
        : `which ${command}`;
      
      await this.execute(checkCmd);
      return true;
    } catch (error) {
      return false;
    }
  }

  /**
   * 获取命令的完整路径
   * @param {string} command - 命令名
   * @returns {Promise<string|null>} - 命令的完整路径，如果不存在则返回 null
   */
  async getCommandPath(command) {
    try {
      const checkCmd = process.platform === 'win32' 
        ? `where ${command}` 
        : `which ${command}`;
      
      const result = await this.execute(checkCmd);
      return result.stdout.split('\n')[0].trim();
    } catch (error) {
      return null;
    }
  }

  /**
   * 执行多个命令（串行执行）
   * @param {Array<string|object>} commands - 命令数组
   * @param {object} options - 执行选项
   * @returns {Promise<Array>} - 返回所有命令的执行结果
   */
  async executeCommands(commands, options = {}) {
    const results = [];
    
    for (const command of commands) {
      try {
        const result = await this.execute(command, options);
        results.push(result);
      } catch (error) {
        if (options.continueOnError) {
          results.push({ 
            success: false, 
            error: error.message,
            command: typeof command === 'string' ? command : `${command.cmd} ${command.args?.join(' ') || ''}`
          });
        } else {
          throw error;
        }
      }
    }
    
    return results;
  }

  /**
   * 执行多个命令（并行执行）
   * @param {Array<string|object>} commands - 命令数组
   * @param {object} options - 执行选项
   * @returns {Promise<Array>} - 返回所有命令的执行结果
   */
  async executeCommandsParallel(commands, options = {}) {
    const promises = commands.map(command => 
      this.execute(command, options).catch(error => {
        if (options.continueOnError) {
          return { 
            success: false, 
            error: error.message,
            command: typeof command === 'string' ? command : `${command.cmd} ${command.args?.join(' ') || ''}`
          };
        } else {
          throw error;
        }
      })
    );
    
    return Promise.all(promises);
  }

  // 进程管理相关方法的代理
  killProcess(processId, signal = 'SIGTERM') {
    return this.processManager.killProcess(processId, signal);
  }

  killAllProcesses(signal = 'SIGTERM') {
    return this.processManager.killAllProcesses(signal);
  }

  getProcessInfo(processId) {
    return this.processManager.getProcessInfo(processId);
  }

  getAllProcesses() {
    return this.processManager.getAllProcesses();
  }

  hasProcess(processId) {
    return this.processManager.hasProcess(processId);
  }

  getRunningProcessCount() {
    return this.processManager.getRunningProcessCount();
  }

  cleanup() {
    return this.processManager.cleanup();
  }
}

/**
 * 命令构建器类
 */
class CommandBuilder {
  constructor(baseCommand) {
    this._cmd = baseCommand;
    this._args = [];
  }
  
  arg(value) {
    this._args.push(value);
    return this;
  }
  
  args(...values) {
    this._args.push(...values);
    return this;
  }
  
  flag(flag, value = null) {
    this._args.push(flag);
    if (value !== null) {
      this._args.push(value);
    }
    return this;
  }
  
  option(option, value) {
    this._args.push(option, value);
    return this;
  }
  
  build() {
    return {
      cmd: this._cmd,
      args: [...this._args]
    };
  }
  
  toString() {
    return `${this._cmd} ${this._args.join(' ')}`;
  }
  
  async execute(commandService, options = {}) {
    return commandService.execute(this.build(), options);
  }
  
  async executeSimple(commandService, options = {}) {
    return commandService.executeSimple(this.build(), options);
  }
}

// 创建默认的命令服务实例
const defaultCommandService = new CommandService();

// 常用命令构建器工厂函数
export const git = (args = []) => new CommandBuilder('git').args(...args);
export const npm = (args = []) => new CommandBuilder('npm').args(...args);
export const node = (args = []) => new CommandBuilder('node').args(...args);
export const python = (args = []) => new CommandBuilder('python').args(...args);
export const pip = (args = []) => new CommandBuilder('pip').args(...args);

// 平台相关命令
export const ls = process.platform === 'win32' ? 'dir' : 'ls';
export const copy = process.platform === 'win32' ? 'copy' : 'cp';
export const move = process.platform === 'win32' ? 'move' : 'mv';
export const remove = process.platform === 'win32' ? 'del' : 'rm';

// 工具函数
export const isWindows = () => process.platform === 'win32';
export const isMac = () => process.platform === 'darwin';
export const isLinux = () => process.platform === 'linux';

// 导出类和默认实例
export { CommandService, ProcessManager, CommandBuilder };
export default defaultCommandService;

// 兼容性导出 - 保持与原 commandUtils 的接口兼容
export const executeCommand = (command, options) => defaultCommandService.execute(command, options);
export const executeCommandSimple = (command, options) => defaultCommandService.executeSimple(command, options);
export const executeCommandWithCallback = (command, callbacks, options) => defaultCommandService.executeWithCallback(command, callbacks, options);
export const executeCommands = (commands, options) => defaultCommandService.executeCommands(commands, options);
export const executeCommandsParallel = (commands, options) => defaultCommandService.executeCommandsParallel(commands, options);
export const commandExists = (command) => defaultCommandService.commandExists(command);
export const getCommandPath = (command) => defaultCommandService.getCommandPath(command);
export const killProcess = (processId, signal) => defaultCommandService.killProcess(processId, signal);
export const killAllProcesses = (signal) => defaultCommandService.killAllProcesses(signal);
export const getProcessInfo = (processId) => defaultCommandService.getProcessInfo(processId);
export const getAllProcesses = () => defaultCommandService.getAllProcesses();
export const hasProcess = (processId) => defaultCommandService.hasProcess(processId);

// 创建命令构建器的工厂函数
export const createCommandBuilder = (baseCommand) => new CommandBuilder(baseCommand);