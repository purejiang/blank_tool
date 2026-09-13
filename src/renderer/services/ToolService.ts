/**
 * 工具服务 - 管理工具状态和操作
 */
import { requireApiMethod } from '../api/apiAccess';
import { log } from '@utils/logger'

type ToolStatus = 'available' | 'unknown' | string;

interface ToolInfo {
    name: string;
    status: ToolStatus;
    version: string;
    path: string;
    source: string;
    lastChecked: Date;
    available: boolean;
    [key: string]: unknown;
}

interface ToolCheckParams {
    toolName?: string;
    refresh?: boolean;
}

type ToolListener = (event: string, data: unknown) => void;

class ToolService {
    private tools: Map<string, ToolInfo>;
    private isPolling: boolean;
    private pollingInterval: ReturnType<typeof setInterval> | null;
    private pollingIntervalMs: number;
    private maxRetries: number;
    private retryDelay: number;
    private listeners: Set<ToolListener>;

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
            log.debug('工具服务初始化完成')
        } catch (error) {
            log.error('工具服务初始化失败:', error);
            throw error;
        }
    }

    async checkTool(toolName: string, refresh = true) {
        return this.checkTools({ toolName, refresh });
    }

    /**
     * 加载工具状态
     */
    async checkTools(params: ToolCheckParams = {}) {
        try {
            const { toolName, refresh } = params || {};

            if (toolName) {
                const data = await requireApiMethod('checkTool')(toolName, refresh) as Record<string, unknown>;
                const status = typeof data.status === 'string' ? data.status : 'unknown';
                const info: ToolInfo = {
                    name: typeof data.name === 'string' ? data.name : toolName,
                    status,
                    version: typeof data.version === 'string' ? data.version : 'unknown',
                    path: typeof data.path === 'string' ? data.path : '',
                    source: typeof data.source === 'string' ? data.source : 'none',
                    lastChecked: new Date(),
                    available: status === 'available',
                    ...data
                };
                this.tools.set(info.name, info);
                this.notifyListeners('tool_updated', info);
                return info;
            }

            const toolsData = await requireApiMethod('getTools')({ refresh }) as Record<string, Record<string, unknown>>;

            this.tools.clear();
            for (const [name, info] of Object.entries(toolsData || {})) {
                const status = typeof info.status === 'string' ? info.status : 'unknown';
                this.tools.set(name, {
                    name,
                    status,
                    version: typeof info.version === 'string' ? info.version : 'unknown',
                    path: typeof info.path === 'string' ? info.path : '',
                    source: typeof info.source === 'string' ? info.source : 'none',
                    lastChecked: new Date(),
                    available: status === 'available',
                    ...info
                });
            }
            this.notifyListeners('tools_refreshed', this.tools);
            return Array.from(this.tools.values());
        } catch (error) {
            this.notifyListeners('tools_error', error);
            throw error;
        }
    }

    /**
     * 获取特定工具的状态
     * @param {string} toolName - 工具名称
     */
    getToolStatus(toolName: string) {
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
    isToolAvailable(toolName: string) {
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
            return;
        }

        this.isPolling = true;

        this.pollingInterval = setInterval(async () => {
            try {
                await this.checkTools();
            } catch (error) {
                log.error('轮询工具状态时发生错误:', error);
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
    setPollingInterval(intervalMs: number) {
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
            await this.checkTools();
            return true;
        } catch (error) {
            log.error('刷新工具状态失败:', error);
            return false;
        }
    }

    async setSystemSearchMode(systemSearch: boolean) {
        // preload.js 已解包
        return await requireApiMethod('setToolSearchMode')(systemSearch);
    }

    /**
     * 添加事件监听器
     * @param {Function} listener - 监听器函数
     */
    addListener(listener: ToolListener) {
        this.listeners.add(listener);
    }

    /**
     * 移除事件监听器
     * @param {Function} listener - 监听器函数
     */
    removeListener(listener: ToolListener) {
        this.listeners.delete(listener);
    }

    /**
     * 通知所有监听器
     * @param {string} event - 事件类型
     * @param {any} data - 事件数据
     */
    notifyListeners(event: string, data: unknown) {
        this.listeners.forEach(listener => {
            try {
                listener(event, data);
            } catch (error) {
                log.error('监听器执行错误:', error);
            }
        });
    }

    /**
     * 延迟函数
     * @param {number} ms - 延迟毫秒数
     */
    delay(ms: number) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    /**
     * 销毁服务
     */
    destroy() {
        this.stopPolling();
        this.tools.clear();
        this.listeners.clear();
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
