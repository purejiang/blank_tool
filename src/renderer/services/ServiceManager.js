/**
 * 服务管理器 - 统一管理所有应用服务
 * 为Vue 3组合式API提供服务注入和管理
 */
import ConfigService from './ConfigService.js';
import ToolService from './ToolService.js';
import ErrorService from './ErrorService.js';
import NotificationService from './NotificationService.js';
import DeviceService from './DeviceService.js';

class ServiceManager {
    constructor() {
        this.services = new Map();
        this.isInitialized = false;
        this.initializationOrder = [
            'error',
            'config',
            'notification', 
            'device',
            'tools'
        ];
        this.serviceDependencies = {
        };
    }

    /**
     * 初始化所有服务
     */
    async initialize() {
        if (this.isInitialized) {
            return this.services;
        }

        try {
            console.log('正在初始化服务管理器...');

            // 按照依赖顺序初始化服务
            for (const serviceName of this.initializationOrder) {
                await this.initializeService(serviceName);
            }

            this.isInitialized = true;
            console.log('服务管理器初始化完成');

            return this.services;
        } catch (error) {
            console.error('服务管理器初始化失败:', error);
            throw error;
        }
    }

    /**
     * 初始化单个服务
     * @param {string} serviceName - 服务名称
     */
    async initializeService(serviceName) {
        try {
            // 检查依赖是否已初始化
            const dependencies = this.serviceDependencies[serviceName] || [];
            for (const dep of dependencies) {
                if (!this.services.has(dep)) {
                    throw new Error(`服务 ${serviceName} 的依赖 ${dep} 尚未初始化`);
                }
            }

            let service;
            switch (serviceName) {
                case 'error':
                    service = new ErrorService();
                    service.initialize();
                    break;
                case 'config':
                    service = new ConfigService();
                    await service.initialize();
                    break;
                case 'device':
                    service = new DeviceService();
                    await service.initialize();
                    break;
                case 'tools':
                    service = new ToolService();
                    await service.initialize();
                    break;
                case 'notification':
                    service = new NotificationService();
                    await service.initialize();
                    break;
                default:
                    throw new Error(`未知的服务: ${serviceName}`);
            }

            this.services.set(serviceName, service);
            console.log(`${serviceName}服务初始化成功`);
        } catch (error) {
            console.error(`${serviceName}服务初始化失败:`, error);
            throw error;
        }
    }

    /**
     * 获取指定服务
     * @param {string} serviceName - 服务名称
     * @returns {Object|null} 服务实例，如果不存在则返回 null
     */
    getService(serviceName) {
        if (!this.isInitialized) {
            throw new Error('服务管理器尚未初始化');
        }
        
        const service = this.services.get(serviceName);
        if (!service) {
            console.warn(`服务 "${serviceName}" 不存在`);
            return null;
        }
        
        return service;
    }

    /**
     * 获取所有服务
     * @returns {Map} 所有服务的Map
     */
    getAllServices() {
        return this.services;
    }

    /**
     * 检查服务是否存在
     * @param {string} serviceName - 服务名称
     * @returns {boolean} 是否存在
     */
    hasService(serviceName) {
        return this.services.has(serviceName);
    }

    /**
     * 销毁所有服务
     */
    destroy() {
        console.log('正在销毁服务管理器...');
        
        for (const [name, service] of this.services) {
            try {
                if (typeof service.destroy === 'function') {
                    service.destroy();
                }
                console.log(`服务 "${name}" 已销毁`);
            } catch (error) {
                console.error(`销毁服务 "${name}" 时出错:`, error);
            }
        }
        
        this.services.clear();
        this.isInitialized = false;
        console.log('服务管理器已销毁');
    }

    /**
     * 重启服务管理器
     */
    async restart() {
        this.destroy();
        await this.initialize();
    }

    /**
     * 获取服务状态信息
     */
    getServiceStatus() {
        const status = {
            initialized: this.isInitialized,
            serviceCount: this.services.size,
            services: {}
        };

        for (const [name, service] of this.services) {
            status.services[name] = {
                name,
                type: service.constructor.name,
                initialized: true
            };
        }

        return status;
    }
}

// 创建全局服务管理器实例
const serviceManager = new ServiceManager();

export default serviceManager;