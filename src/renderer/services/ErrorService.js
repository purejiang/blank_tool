/**
 * 错误服务 - 统一错误处理、日志记录和恢复机制
 */
class ErrorService {
    constructor(notificationService) {
        this.notificationService = notificationService || null;
        this.errorHandlers = new Map();
        this.errorLog = [];
        this.maxLogSize = 1000;
        this.listeners = new Set();
        this.recoveryStrategies = new Map();
        this.errorCategories = {
            NETWORK: 'network',
            CONFIG: 'config',
            SERVICE: 'service',
            DEVICE: 'device',
            TOOL: 'tool',
            UI: 'ui',
            UNKNOWN: 'unknown'
        };
    }

    /**
     * 初始化错误服务
     */
    initialize() {
        console.log('正在初始化错误服务...');
        
        // 设置全局错误处理
        this.setupGlobalErrorHandlers();
        
        // 注册默认恢复策略
        this.registerDefaultRecoveryStrategies();
        
        console.log('错误服务初始化成功');
    }

    async reportError(error, context = {}) {
        return await this.handleError(error, context)
    }

    /**
     * 设置全局错误处理器
     */
    setupGlobalErrorHandlers() {
        // 捕获未处理的Promise拒绝
        window.addEventListener('unhandledrejection', (event) => {
            this.handleError(event.reason, {
                category: this.errorCategories.UNKNOWN,
                context: 'unhandledrejection',
                severity: 'high'
            });
        });

        // 捕获全局JavaScript错误
        window.addEventListener('error', (event) => {
            this.handleError(event.error, {
                category: this.errorCategories.UI,
                context: 'global_error',
                severity: 'high',
                filename: event.filename,
                lineno: event.lineno,
                colno: event.colno
            });
        });
    }

    /**
     * 注册默认恢复策略
     */
    registerDefaultRecoveryStrategies() {
        // 网络错误恢复策略
        this.registerRecoveryStrategy(this.errorCategories.NETWORK, async (error, context) => {
            console.log('执行网络错误恢复策略...');
            
            // 检查网络连接
            if (!navigator.onLine) {
                return {
                    success: false,
                    message: '网络连接不可用，请检查网络设置'
                };
            }
            
            // 重试网络请求
            if (context.retryFunction && context.retryCount < 3) {
                try {
                    await new Promise(resolve => setTimeout(resolve, 2000 * (context.retryCount + 1)));
                    await context.retryFunction();
                    return {
                        success: true,
                        message: '网络请求重试成功'
                    };
                } catch (retryError) {
                    return {
                        success: false,
                        message: `重试失败: ${retryError.message}`
                    };
                }
            }
            
            return {
                success: false,
                message: '网络错误无法自动恢复'
            };
        });

        // 服务错误恢复策略
        this.registerRecoveryStrategy(this.errorCategories.SERVICE, async (error, context) => {
            console.log('执行服务错误恢复策略...');
            
            if (context.serviceName && context.serviceManager) {
                try {
                    // 尝试重启服务
                    await context.serviceManager.restartService(context.serviceName);
                    return {
                        success: true,
                        message: `服务 ${context.serviceName} 重启成功`
                    };
                } catch (restartError) {
                    return {
                        success: false,
                        message: `服务重启失败: ${restartError.message}`
                    };
                }
            }
            
            return {
                success: false,
                message: '服务错误无法自动恢复'
            };
        });

        // 配置错误恢复策略
        this.registerRecoveryStrategy(this.errorCategories.CONFIG, async (error, context) => {
            console.log('执行配置错误恢复策略...');
            
            if (context.configService) {
                try {
                    // 重置为默认配置
                    await context.configService.resetToDefault();
                    return {
                        success: true,
                        message: '配置已重置为默认值'
                    };
                } catch (resetError) {
                    return {
                        success: false,
                        message: `配置重置失败: ${resetError.message}`
                    };
                }
            }
            
            return {
                success: false,
                message: '配置错误无法自动恢复'
            };
        });
    }

    /**
     * 处理错误
     * @param {Error} error - 错误对象
     * @param {Object} context - 错误上下文
     */
    async handleError(error, context = {}) {
        const errorInfo = {
            id: this.generateErrorId(),
            timestamp: new Date(),
            error: error,
            message: error?.message || '未知错误',
            stack: error?.stack,
            category: context.category || this.categorizeError(error),
            severity: context.severity || 'medium',
            context: context,
            handled: false
        };

        // 记录错误日志
        this.logError(errorInfo);

        // 通知监听器
        this.notifyListeners('error_occurred', errorInfo);

        if (this.notificationService && typeof this.notificationService.error === 'function') {
            const title = '发生错误';
            const message = errorInfo.message;
            this.notificationService.error(title, message);
        }

        // 尝试自动恢复
        const recoveryResult = await this.attemptRecovery(errorInfo);
        if (recoveryResult.success) {
            errorInfo.handled = true;
            errorInfo.recoveryResult = recoveryResult;
            this.notifyListeners('error_recovered', errorInfo);
        }

        // 执行自定义错误处理器
        await this.executeErrorHandlers(errorInfo);

        return errorInfo;
    }

    /**
     * 尝试错误恢复
     * @param {Object} errorInfo - 错误信息
     */
    async attemptRecovery(errorInfo) {
        const strategy = this.recoveryStrategies.get(errorInfo.category);
        if (strategy) {
            try {
                console.log(`尝试恢复 ${errorInfo.category} 类型错误...`);
                return await strategy(errorInfo.error, errorInfo.context);
            } catch (recoveryError) {
                console.error('错误恢复失败:', recoveryError);
                return {
                    success: false,
                    message: `恢复策略执行失败: ${recoveryError.message}`
                };
            }
        }
        
        return {
            success: false,
            message: '没有可用的恢复策略'
        };
    }

    /**
     * 执行自定义错误处理器
     * @param {Object} errorInfo - 错误信息
     */
    async executeErrorHandlers(errorInfo) {
        const handlers = this.errorHandlers.get(errorInfo.category) || [];
        for (const handler of handlers) {
            try {
                await handler(errorInfo);
            } catch (handlerError) {
                console.error('错误处理器执行失败:', handlerError);
            }
        }
    }

    /**
     * 错误分类
     * @param {Error} error - 错误对象
     */
    categorizeError(error) {
        const message = error?.message?.toLowerCase() || '';
        
        if (message.includes('network') || message.includes('fetch') || message.includes('timeout')) {
            return this.errorCategories.NETWORK;
        }
        
        if (message.includes('config') || message.includes('setting')) {
            return this.errorCategories.CONFIG;
        }
        
        if (message.includes('service') || message.includes('initialize')) {
            return this.errorCategories.SERVICE;
        }
        
        if (message.includes('device') || message.includes('adb')) {
            return this.errorCategories.DEVICE;
        }
        
        if (message.includes('tool') || message.includes('command')) {
            return this.errorCategories.TOOL;
        }
        
        return this.errorCategories.UNKNOWN;
    }

    /**
     * 记录错误日志
     * @param {Object} errorInfo - 错误信息
     */
    logError(errorInfo) {
        // 添加到内存日志
        this.errorLog.push(errorInfo);
        
        // 限制日志大小
        if (this.errorLog.length > this.maxLogSize) {
            this.errorLog.shift();
        }

        // 控制台输出
        const logLevel = this.getLogLevel(errorInfo.severity);
        console[logLevel](`[${errorInfo.category.toUpperCase()}] ${errorInfo.message}`, {
            id: errorInfo.id,
            timestamp: errorInfo.timestamp,
            context: errorInfo.context,
            stack: errorInfo.stack
        });

        // 发送到后端日志服务（如果可用）
        this.sendToBackendLogger(errorInfo);
    }

    /**
     * 发送日志到后端
     * @param {Object} errorInfo - 错误信息
     */
    async sendToBackendLogger(errorInfo) {
        try {
            if (window.electronAPI && window.electronAPI.callBackendAPI) {
                // await window.electronAPI.callBackendAPI('/api/logs/error', {
                //     id: errorInfo.id,
                //     timestamp: errorInfo.timestamp.toISOString(),
                //     category: errorInfo.category,
                //     severity: errorInfo.severity,
                //     message: errorInfo.message,
                //     stack: errorInfo.stack,
                //     context: errorInfo.context
                // });
            }
        } catch (logError) {
            console.warn('发送错误日志到后端失败:', logError);
        }
    }

    /**
     * 获取日志级别
     * @param {string} severity - 严重程度
     */
    getLogLevel(severity) {
        switch (severity) {
            case 'low': return 'info';
            case 'medium': return 'warn';
            case 'high': return 'error';
            default: return 'log';
        }
    }

    /**
     * 注册错误处理器
     * @param {string} category - 错误类别
     * @param {Function} handler - 处理器函数
     */
    registerErrorHandler(category, handler) {
        if (!this.errorHandlers.has(category)) {
            this.errorHandlers.set(category, []);
        }
        this.errorHandlers.get(category).push(handler);
    }

    /**
     * 注册恢复策略
     * @param {string} category - 错误类别
     * @param {Function} strategy - 恢复策略函数
     */
    registerRecoveryStrategy(category, strategy) {
        this.recoveryStrategies.set(category, strategy);
    }

    /**
     * 添加事件监听器
     * @param {Function} listener - 监听器函数
     */
    addListener(listener) {
        this.listeners.add(listener);
    }

    /**
     * 移除事件监听器
     * @param {Function} listener - 监听器函数
     */
    removeListener(listener) {
        this.listeners.delete(listener);
    }

    /**
     * 通知监听器
     * @param {string} event - 事件类型
     * @param {any} data - 事件数据
     */
    notifyListeners(event, data) {
        this.listeners.forEach(listener => {
            try {
                listener(event, data);
            } catch (error) {
                console.error('错误监听器执行失败:', error);
            }
        });
    }

    /**
     * 生成错误ID
     */
    generateErrorId() {
        return `error_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    }

    /**
     * 获取错误日志
     * @param {Object} filters - 过滤条件
     */
    getErrorLog(filters = {}) {
        let logs = [...this.errorLog];
        
        if (filters.category) {
            logs = logs.filter(log => log.category === filters.category);
        }
        
        if (filters.severity) {
            logs = logs.filter(log => log.severity === filters.severity);
        }
        
        if (filters.startTime) {
            logs = logs.filter(log => log.timestamp >= filters.startTime);
        }
        
        if (filters.endTime) {
            logs = logs.filter(log => log.timestamp <= filters.endTime);
        }
        
        return logs.sort((a, b) => b.timestamp - a.timestamp);
    }

    /**
     * 清除错误日志
     */
    clearErrorLog() {
        this.errorLog = [];
        console.log('错误日志已清除');
    }

    /**
     * 获取错误统计
     */
    getErrorStats() {
        const stats = {
            total: this.errorLog.length,
            byCategory: {},
            bySeverity: {},
            handled: 0,
            unhandled: 0
        };

        this.errorLog.forEach(log => {
            // 按类别统计
            stats.byCategory[log.category] = (stats.byCategory[log.category] || 0) + 1;
            
            // 按严重程度统计
            stats.bySeverity[log.severity] = (stats.bySeverity[log.severity] || 0) + 1;
            
            // 按处理状态统计
            if (log.handled) {
                stats.handled++;
            } else {
                stats.unhandled++;
            }
        });

        return stats;
    }

    /**
     * 销毁服务
     */
    destroy() {
        this.errorHandlers.clear();
        this.recoveryStrategies.clear();
        this.listeners.clear();
        this.errorLog = [];
        console.log('错误服务已销毁');
    }
}

export default ErrorService;