
class ServiceManager {
  private services: Map<string, any>
  private serviceConstructors: Map<string, new (...args: any[]) => any>
  private serviceDependencies: Map<string, string[]>
  private isInitialized: boolean

  constructor() {
    this.services = new Map()
    this.serviceConstructors = new Map()
    this.serviceDependencies = new Map()
    this.isInitialized = false
  }

  register(name: string, constructor: new (...args: any[]) => any, dependencies: string[] = []) {
    this.serviceConstructors.set(name, constructor)
    this.serviceDependencies.set(name, dependencies)
  }

  async getService(name: string) {
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

  /**
   * Synchronously get an already-initialized service
   */
  getServiceSync(name: string) {
    return this.services.get(name);
  }

  async initialize() {
    this.isInitialized = true
    console.log('Service manager initialized.')
  }

  /**
   * Get all services
   */
  getAllServices() {
    return this.services;
  }

  /**
   * Check if a service exists
   */
  hasService(serviceName: string) {
    return this.services.has(serviceName);
  }

  /**
   * Destroy all services
   */
  destroy() {
    console.log('Destroying service manager...');

    for (const [name, service] of this.services) {
      try {
        if (typeof service.destroy === 'function') {
          service.destroy();
        }
        console.log(`Service "${name}" destroyed`);
      } catch (error) {
        console.error(`Error destroying service "${name}":`, error);
      }
    }

    this.services.clear();
    this.isInitialized = false;
    console.log('Service manager destroyed');
  }

  /**
   * Restart service manager
   */
  async restart() {
    this.destroy();
    await this.initialize();
  }

  /**
   * Get service status information
   */
  getServiceStatus() {
    const status: {
      initialized: boolean
      serviceCount: number
      services: Record<string, { name: string; type: string; initialized: boolean }>
    } = {
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

// Create global service manager instance
const serviceManager = new ServiceManager();

export default serviceManager;
