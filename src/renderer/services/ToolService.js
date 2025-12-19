/**
 * 工具服务 - 管理工具状态和操作
 */
import unifiedAPI from '../api/unifiedAPI.js';

class ToolService {
    constructor() {
        this.tools = new Map();
        this.isPolling = false;
        this.pollingInterval = null;
        this.pollingIntervalMs = 30000; // 30秒轮询间隔
        this.maxRetries = 3;
        this.retryDelay = 2000; // 2秒重试延迟
        this.listeners = new Set();
    }

    /**
     * 初始化工具服务
     */
    async initialize() {
        try {
            console.log('初始化工具服务...');
            console.log('工具服务初始化成功');
        } catch (error) {
            console.error('工具服务初始化失败:', error);
            throw error;
        }
    }

    async checkTool(toolName, refresh = true) {
        return this.checkTools({ toolName, refresh });
    }

    /**
     * 加载工具状态
     */
    async checkTools(params = {}) {
        try {
            const { toolName, refresh } = params || {};
            const api = unifiedAPI.getAPI();

            if (toolName) {
                if (api && typeof api.checkTool === 'function') {
                    const data = await api.checkTool(toolName, refresh);
                    const info = {
                        name: data.name || toolName,
                        status: data.status || 'unknown',
                        version: data.version || 'unknown',
                        path: data.path || '',
                        source: data.source || 'none',
                        lastChecked: new Date(),
                        available: data.status === 'available',
                        ...data
                    };
                    this.tools.set(info.name, info);
                    this.notifyListeners('tool_updated', info);
                    return info;
                }
                throw new Error('checkTool API not implemented');
            }
            
            if (api && typeof api.getTools === 'function') {
                const toolsData = await api.getTools({ refresh });
                
                this.tools.clear();
                for (const [name, info] of Object.entries(toolsData || {})) {
                    this.tools.set(name, {
                        name,
                        status: info.status || 'unknown',
                        version: info.version || 'unknown',
                        path: info.path || '',
                        source: info.source || 'none',
                        lastChecked: new Date(),
                        available: info.status === 'available',
                        ...info
                    });
                }
                this.notifyListeners('tools_refreshed', this.tools);
                return Array.from(this.tools.values());
            }
            throw new Error('getTools API not implemented');
        } catch (error) {
            this.notifyListeners('tools_error', error);
            throw error;
        }
    }

    /**
     * 获取特定工具的状态
     * @param {string} toolName - 工具名称
     */
    getToolStatus(toolName) {
        return this.tools.get(toolName) || null;
    }

    /**
     * 获取所有工具状态
     */
    getAllToolsStatus() {
        return Array.from(this.tools.values());
    }

    /**
     * 检查工具是否可用
     * @param {string} toolName - 工具名称
     */
    isToolAvailable(toolName) {
        const tool = this.tools.get(toolName);
        return tool ? tool.available : false;
    }

    /**
     * 获取可用工具列表
     */
    getAvailableTools() {
        return Array.from(this.tools.values()).filter(tool => tool.available);
    }

    /**
     * 获取不可用工具列表
     */
    getUnavailableTools() {
        return Array.from(this.tools.values()).filter(tool => !tool.available);
    }

    /**
     * 开始轮询工具状态
     */
    startPolling() {
        if (this.isPolling) {
            console.log('工具状态轮询已在运行');
            return;
        }

        console.log(`开始工具状态轮询，间隔: ${this.pollingIntervalMs / 1000}秒`);
        this.isPolling = true;

        this.pollingInterval = setInterval(async () => {
            try {
                await this.checkTools();
            } catch (error) {
                console.error('轮询工具状态时发生错误:', error);
            }
        }, this.pollingIntervalMs);
    }

    /**
     * 停止轮询工具状态
     */
    stopPolling() {
        if (!this.isPolling) {
            return;
        }

        console.log('停止工具状态轮询');
        this.isPolling = false;

        if (this.pollingInterval) {
            clearInterval(this.pollingInterval);
            this.pollingInterval = null;
        }
    }

    /**
     * 设置轮询间隔
     * @param {number} intervalMs - 轮询间隔（毫秒）
     */
    setPollingInterval(intervalMs) {
        this.pollingIntervalMs = intervalMs;

        if (this.isPolling) {
            this.stopPolling();
            this.startPolling();
        }
    }

    /**
     * 手动刷新工具状态
     */
    async refreshToolsStatus() {
        try {
            console.log('手动刷新工具状态...');
            await this.checkTools();
            return true;
        } catch (error) {
            console.error('刷新工具状态失败:', error);
            return false;
        }
    }

    async setSystemSearchMode(systemSearch) {
        try {
            const api = unifiedAPI.getAPI()
            if (api && typeof api.setToolSearchMode === 'function') {
                const resp = await api.setToolSearchMode(systemSearch)
                // preload.js 已解包
                return resp;
            }
            throw new Error('setToolSearchMode API not implemented');
        } catch (error) {
            throw error;
        }
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
     * 通知所有监听器
     * @param {string} event - 事件类型
     * @param {any} data - 事件数据
     */
    notifyListeners(event, data) {
        this.listeners.forEach(listener => {
            try {
                listener(event, data);
            } catch (error) {
                console.error('监听器执行错误:', error);
            }
        });
    }

    /**
     * 延迟函数
     * @param {number} ms - 延迟毫秒数
     */
    delay(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    /**
     * 销毁服务
     */
    destroy() {
        this.stopPolling();
        this.tools.clear();
        this.listeners.clear();
        console.log('工具服务已销毁');
    }

    /**
     * 获取服务状态
     */
    getStatus() {
        return {
            initialized: this.tools.size > 0,
            polling: this.isPolling,
            toolsCount: this.tools.size,
            availableToolsCount: this.getAvailableTools().length,
            lastUpdate: this.tools.size > 0 ? Math.max(...Array.from(this.tools.values()).map(t => t.lastChecked?.getTime() || 0)) : null
        };
    }
}

export default ToolService;
