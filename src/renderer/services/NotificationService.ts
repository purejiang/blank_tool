/**
 * 通知服务 - 管理应用内的通知显示
 */
type NotificationType = 'success' | 'error' | 'warning' | 'info' | 'loading' | string;

interface NotificationData {
    id: number;
    type: NotificationType;
    title: string;
    message: string;
    duration: number;
    timestamp: number;
}

type NotificationCallback = (...args: unknown[]) => void;

class NotificationService {
    private listeners: Map<string, Set<NotificationCallback>>;
    private nextId: number;
    private notifications: Map<number, NotificationData>;
    private isInitialized: boolean;

    constructor() {
        this.listeners = new Map();
        this.nextId = 1;
        this.notifications = new Map(); // 存储通知数据，用于状态管理
        this.isInitialized = false;
        this.initialize();
    }

    /**
     * 初始化服务
     */
    async initialize() {
        try {
            console.log('正在初始化通知服务...');
            this.isInitialized = true;
            console.log('通知服务初始化完成');
        } catch (error) {
            console.error('通知服务初始化失败:', error);
            throw error;
        }
    }

    /**
     * 显示通知
     * @param {string} type - 通知类型: success, error, warning, info, loading
     * @param {string} title - 通知标题
     * @param {string} message - 通知消息
     * @param {number} duration - 显示时长(毫秒)，0表示不自动关闭
     * @returns {number} 通知ID
     */
    show(type: NotificationType = 'info', title = '', message = '', duration = 5000) {
        const id = this.nextId++;
        
        const notificationData = {
            id,
            type,
            title,
            message,
            duration,
            timestamp: Date.now()
        };
        
        // 存储通知数据
        this.notifications.set(id, notificationData);
        
        // 触发显示事件
        this.emit('show', notificationData);
        
        return id;
    }

    /**
     * 隐藏通知
     * @param {number} id - 通知ID
     */
    hide(id: number) {
        if (!this.notifications.has(id)) {
            return;
        }
        
        // 移除通知数据
        this.notifications.delete(id);
        
        // 触发隐藏事件
        this.emit('hide', id);
    }

    /**
     * 更新通知内容
     * @param {number} id - 通知ID
     * @param {Object} updates - 更新的数据
     */
    update(id: number, updates: Partial<NotificationData>) {
        const notification = this.notifications.get(id);
        if (!notification) {
            return;
        }
        
        // 更新通知数据
        Object.assign(notification, updates);
        
        // 触发更新事件
        this.emit('update', id, updates);
    }

    /**
     * 清除所有通知
     */
    clear() {
        this.notifications.clear();
        this.emit('clear');
    }

    /**
     * 显示成功通知
     */
    success(title: string, message: string, duration = 3000) {
        return this.show('success', title, message, duration);
    }

    /**
     * 显示错误通知
     */
    error(title: string, message: string, duration = 0) {
        return this.show('error', title, message, duration);
    }

    /**
     * 显示警告通知
     */
    warning(title: string, message: string, duration = 5000) {
        return this.show('warning', title, message, duration);
    }

    /**
     * 显示信息通知
     */
    info(title: string, message: string, duration = 5000) {
        return this.show('info', title, message, duration);
    }

    /**
     * 显示加载通知
     */
    loading(title: string, message: string) {
        return this.show('loading', title, message, 0);
    }

    /**
     * 更新加载通知
     */
    updateLoading(id: number, title: string, message: string) {
        this.update(id, { title, message });
    }

    /**
     * 完成加载通知（转换为成功通知）
     */
    completeLoading(id: number, title: string, message: string, duration = 3000) {
        this.update(id, { 
            type: 'success', 
            title, 
            message, 
            duration 
        });
        
        // 自动关闭
        if (duration > 0) {
            setTimeout(() => {
                this.hide(id);
            }, duration);
        }
    }

    /**
     * 失败加载通知（转换为错误通知）
     */
    failLoading(id: number, title: string, message: string, duration = 0) {
        this.update(id, { 
            type: 'error', 
            title, 
            message, 
            duration 
        });
        
        // 自动关闭
        if (duration > 0) {
            setTimeout(() => {
                this.hide(id);
            }, duration);
        }
    }

    /**
     * 添加事件监听器
     * @param {string} event - 事件名称
     * @param {Function} callback - 回调函数
     */
    addListener(event: string, callback: NotificationCallback) {
        if (!this.listeners.has(event)) {
            this.listeners.set(event, new Set());
        }
        this.listeners.get(event).add(callback);
    }

    /**
     * 移除事件监听器
     * @param {string} event - 事件名称
     * @param {Function} callback - 回调函数
     */
    removeListener(event: string, callback: NotificationCallback) {
        if (this.listeners.has(event)) {
            this.listeners.get(event).delete(callback);
        }
    }

    /**
     * 触发事件
     * @param {string} event - 事件名称
     * @param {...any} args - 事件参数
     */
    emit(event: string, ...args: unknown[]) {
        if (this.listeners.has(event)) {
            this.listeners.get(event).forEach(callback => {
                try {
                    callback(...args);
                } catch (error) {
                    console.error(`通知服务事件监听器执行失败 (${event}):`, error);
                }
            });
        }
    }

    /**
     * 获取所有通知
     */
    getAllNotifications() {
        return Array.from(this.notifications.values());
    }

    /**
     * 获取指定通知
     */
    getNotification(id: number) {
        return this.notifications.get(id);
    }

    /**
     * 获取通知数量
     */
    getNotificationCount() {
        return this.notifications.size;
    }

    /**
     * 检查是否有指定类型的通知
     */
    hasNotificationType(type: NotificationType) {
        return Array.from(this.notifications.values()).some(n => n.type === type);
    }

    /**
     * 获取服务状态
     */
    getStatus() {
        return {
            isInitialized: this.isInitialized,
            notificationCount: this.notifications.size,
            listenerCount: Array.from(this.listeners.values()).reduce((total, set) => total + set.size, 0)
        };
    }

    /**
     * 销毁服务
     */
    destroy() {
        this.clear();
        this.listeners.clear();
        this.isInitialized = false;
        console.log('通知服务已销毁');
    }
}

export default NotificationService;
