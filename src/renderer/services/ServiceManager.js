
class ServiceManager {
  constructor() {
    this.services = new Map()
    this.serviceConstructors = new Map()
    this.serviceDependencies = new Map()
  }

  register(name, constructor, dependencies = []) {
    this.serviceConstructors.set(name, constructor)
    this.serviceDependencies.set(name, dependencies)
  }

  async getService(name) {
    if (this.services.has(name)) {
      return this.services.get(name);
    }

    const constructor = this.serviceConstructors.get(name);
    if (!constructor) {
      throw new Error(`Service ${name} not registered`);
    }

    const dependencies = this.serviceDependencies.get(name) || [];
    const dependencyInstances = await Promise.all(
      dependencies.map(depName => this.getService(depName))
    );

    const service = new constructor(...dependencyInstances);
    this.services.set(name, service);

    if (typeof service.initialize === 'function') {
      await service.initialize();
    }

    return service;
  }

  async initialize() {
    // The initialize method is now much simpler.
    // We can pre-initialize some services if needed, or just let them be lazy-loaded.
    console.log('Service manager initialized.')
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