<template>
  <div id="app">
    <!-- 加载屏幕 -->
    <div v-if="isLoading" id="loading-screen" class="loading-screen">
      <div class="loading-container">
        <div class="loading-logo">
          <div class="logo-icon">📱</div>
          <h1>Android开发工具</h1>
        </div>
        <div class="loading-progress">
          <div class="progress-bar">
            <div class="progress-fill" :style="{ width: loadingProgress + '%' }"></div>
          </div>
          <div class="loading-text">{{ loadingStep }}</div>
          <div v-if="loadingMessage" class="loading-detail">{{ loadingMessage }}</div>
        </div>
        <div class="loading-version">
          版本 1.0.0
        </div>
        <!-- 错误信息显示 -->
        <div v-if="initError" class="loading-error">
          <div class="error-icon">⚠️</div>
          <div class="error-message">{{ initError }}</div>
          <button v-if="showRetryButton" @click="retryInitialization" class="retry-button">
            重试 ({{ retryCount }}/{{ maxRetries }})
          </button>
        </div>
      </div>
    </div>

    <!-- 主应用界面 -->
    <div v-else class="app-container">
      <AppHeader />
      <main class="main-content">
        <router-view />
      </main>
      <StatusBar />
    </div>

    <!-- 全局通知组件 -->
    <Notification />
  </div>
</template>

<script>
import { ref, onMounted, provide, getCurrentInstance } from 'vue'
import AppHeader from './components/common/Header.vue'
import StatusBar from './components/common/StatusBar.vue'
import Notification from './components/common/Notification.vue'
import serviceManager from './services/ServiceManager.js'

export default {
  name: 'App',
  components: {
    AppHeader,
    StatusBar,
    Notification
  },
  setup() {
    const isLoading = ref(true)
    const loadingProgress = ref(0)
    const loadingStep = ref('正在初始化...')
    const loadingDetail = ref('')
    const loadingMessage = ref('')
    const initError = ref('')
    const showRetryButton = ref(false)
    const retryCount = ref(0)
    const maxRetries = 3

    // 提供服务管理器给子组件
    provide('serviceManager', serviceManager)

    /**
     * 应用初始化流程 - 顺序执行，失败时抛出异常
     */
    async function initializeApplication() {
      try {
        initError.value = ''
        loadingProgress.value = 0

        // 定义初始化任务，按依赖关系顺序执行
        const initTasks = [
          { name: '初始化服务', task: initializeServices, weight: 25, critical: true },
          { name: '工具检查', task: checkToolsStatus, weight: 25, critical: true },
          { name: '设备连接', task: checkDeviceConnection, weight: 25, critical: false },
          { name: '界面准备', task: prepareUI, weight: 25, critical: false }
        ]

        let completedWeight = 0

        // 顺序执行所有初始化任务
        for (let i = 0; i < initTasks.length; i++) {
          const taskInfo = initTasks[i]
          
          try {
            console.log(`开始执行: ${taskInfo.name}`)
            loadingStep.value = taskInfo.name
            loadingProgress.value = completedWeight

            const startTime = Date.now()
            await taskInfo.task()
            const endTime = Date.now()

            completedWeight += taskInfo.weight
            loadingProgress.value = completedWeight

            console.log(`${taskInfo.name} 完成，耗时: ${endTime - startTime}ms`)

          } catch (error) {
            console.error(`${taskInfo.name} 执行失败:`, error)
            
            // 如果是关键任务失败，立即抛出异常
            if (taskInfo.critical) {
              throw new Error(`关键任务 "${taskInfo.name}" 执行失败: ${error.message}`)
            } else {
              // 非关键任务失败，记录警告但继续执行
              console.warn(`非关键任务 "${taskInfo.name}" 执行失败，继续执行后续任务:`, error.message)
              completedWeight += taskInfo.weight
              loadingProgress.value = completedWeight
            }
          }
        }

        // 初始化完成
        updateProgress('初始化完成', '所有初始化任务已完成', 100)
        await new Promise(resolve => setTimeout(resolve, 500))

        isLoading.value = false
        console.log('应用初始化完成')

      } catch (error) {
        console.error('应用初始化失败:', error)
        
        // 设置错误信息并显示重试按钮
        initError.value = error.message || '初始化失败，请重试'
        showRetryButton.value = true
        
        // 抛出异常，让调用方知道初始化失败
        throw error
      }
    }

    /**
     * 更新加载进度
     */
    function updateProgress(step, message, progress) {
      loadingStep.value = step
      loadingMessage.value = message
      loadingProgress.value = Math.min(progress, 100)
    }

    /**
     * 工具状态检查
     */
    async function checkToolsStatus() {
      updateProgress('检查工具状态...', '正在检查开发工具可用性', 35)

      const toolService = serviceManager.getService('tools')
      if (!toolService) {
        throw new Error('工具服务未初始化')
      }

      // 获取工具状态
      toolService.checkTools()
      const availableTools = toolService.getAvailableTools()
      const unavailableTools = toolService.getUnavailableTools()

      console.log(`工具状态检查完成: ${availableTools.length}个可用, ${unavailableTools.length}个不可用`)

      if (unavailableTools.length > 0) {
        console.warn('以下工具不可用:', unavailableTools.map(t => t.name))
      }

      // 开始工具状态轮询
      //toolService.startPolling()

      const performanceService = serviceManager.getService('performance')
      if (performanceService) {
        performanceService.mark('tools-check-end')
        performanceService.measure('tools-check-duration', 'tools-check-start', 'tools-check-end')
      }

      updateProgress('工具检查完成', '开发工具状态检查完成', 50)
    }

    /**
     * 服务初始化
     */
    async function initializeServices() {
      updateProgress('初始化服务...', '正在启动应用服务', 65)

      try {
        // 使用ServiceManager初始化所有服务
        await serviceManager.initialize()

        // 在服务初始化完成后设置全局错误处理器
        const instance = getCurrentInstance()
        if (instance && instance.appContext.app) {
          instance.appContext.app.config.errorHandler = createErrorHandler()
          console.log('全局错误处理器已设置')
        }

        // 提供服务给全局使用
        const services = serviceManager.getAllServices()
        for (const [name, service] of services) {
          provide(`${name}Service`, service)
        }

        updateProgress('服务初始化完成', '所有应用服务已启动', 80)
        console.log('服务初始化完成')

      } catch (error) {
        console.error('服务初始化失败:', error)
        throw new Error(`服务初始化失败: ${error.message}`)
      }
    }

    /**
     * 设备连接检查
     */
    async function checkDeviceConnection() {
      updateProgress('检查设备连接...', '检查设备服务状态', 85)

      const deviceService = serviceManager.getService('device')

      if (!deviceService) {
        throw new Error('设备服务未初始化')
      }

      console.log('设备服务已初始化，跳过自动连接检查')

      // 暂时跳过自动连接逻辑，直接完成设备检查
      // TODO: 后续可以添加设置服务来支持自动连接配置

      updateProgress('设备检查完成', '设备连接检查完成', 95)
    }

    /**
     * 界面准备
     */
    async function prepareUI() {
      updateProgress('准备界面...', '正在准备用户界面', 98)

      // 确保Vue组件已完全挂载
      await new Promise(resolve => setTimeout(resolve, 100))

      // 检查关键DOM元素是否已渲染
      await waitForDOMReady()

      // 初始化UI组件
      await initializeUIComponents()

      // 设置主题
      await applyTheme()

      // 预加载关键数据
      const cacheService = serviceManager.getService('cache')
      if (cacheService) {
        // 预热缓存
        await cacheService.getCacheInfo().catch(() => { })
      }

      updateProgress('界面准备完成', '用户界面已就绪', 99)
    }

    /**
     * 等待DOM准备就绪
     */
    async function waitForDOMReady() {
      console.log('等待DOM准备就绪...')
      return new Promise((resolve) => {
        const checkDOM = () => {
          // 检查关键元素是否存在
          const loadingScreen = document.querySelector('.loading-screen')

          if (loadingScreen) {
            console.log('DOM已准备就绪')
            resolve()
          } else {
            setTimeout(checkDOM, 100)
          }
        }
        checkDOM()
      })
    }

    /**
     * 初始化UI组件
     */
    async function initializeUIComponents() {
      // 初始化工具提示
      initializeTooltips()

      // 初始化快捷键
      initializeKeyboardShortcuts()

      // 初始化拖拽功能
      initializeDragAndDrop()
    }

    /**
     * 初始化工具提示
     */
    function initializeTooltips() {
      console.log('初始化工具提示...')
      // 为所有带有data-tooltip属性的元素添加工具提示
      const tooltipElements = document.querySelectorAll('[data-tooltip]')
      tooltipElements.forEach(element => {
        element.addEventListener('mouseenter', showTooltip)
        element.addEventListener('mouseleave', hideTooltip)
      })
    }

    /**
     * 初始化键盘快捷键
     */
    function initializeKeyboardShortcuts() {
      console.log('初始化快捷键...')
      // 注册全局快捷键
      document.addEventListener('keydown', (event) => {
        // Ctrl+R: 刷新应用
        if (event.ctrlKey && event.key === 'r') {
          event.preventDefault()
          retryInitialization()
        }

        // F12: 打开开发者工具
        if (event.key === 'F12') {
          if (electronAPIService.isAvailable && electronAPIService.api.openDevTools) {
            electronAPIService.api.openDevTools()
          }
        }
      })
    }

    /**
     * 初始化拖拽功能
     */
    function initializeDragAndDrop() {
      console.log('初始化拖拽功能...')
      // 防止默认的拖拽行为
      document.addEventListener('dragover', (event) => {
        event.preventDefault()
      })

      document.addEventListener('drop', (event) => {
        event.preventDefault()
        // 处理文件拖拽
        const files = Array.from(event.dataTransfer.files)
        if (files.length > 0) {
          handleDroppedFiles(files)
        }
      })
    }

    /**
     * 应用主题
     */
    async function applyTheme() {
      console.log('应用主题...')
      const themeService = serviceManager.getService('theme')
      if (themeService) {
        // 应用当前主题
        await themeService.applyTheme()
      }
    }

    /**
     * 处理拖拽文件
     */
    function handleDroppedFiles(files) {
      console.log('拖拽文件:', files)
      // 这里可以处理拖拽的APK文件等
    }

    /**
     * 显示工具提示
     */
    function showTooltip(event) {
      const tooltip = event.target.getAttribute('data-tooltip')
      if (tooltip) {
        // 创建工具提示元素
        const tooltipElement = document.createElement('div')
        tooltipElement.className = 'tooltip'
        tooltipElement.textContent = tooltip
        tooltipElement.style.position = 'absolute'
        tooltipElement.style.zIndex = '9999'
        tooltipElement.style.background = '#333'
        tooltipElement.style.color = 'white'
        tooltipElement.style.padding = '4px 8px'
        tooltipElement.style.borderRadius = '4px'
        tooltipElement.style.fontSize = '12px'
        tooltipElement.style.pointerEvents = 'none'

        // 定位工具提示
        const rect = event.target.getBoundingClientRect()
        tooltipElement.style.left = rect.left + 'px'
        tooltipElement.style.top = (rect.top - 30) + 'px'

        document.body.appendChild(tooltipElement)
        event.target._tooltip = tooltipElement
      }
    }

    /**
     * 隐藏工具提示
     */
    function hideTooltip(event) {
      if (event.target._tooltip) {
        document.body.removeChild(event.target._tooltip)
        delete event.target._tooltip
      }
    }

    /**
     * 重试初始化
     */
    function retryInitialization() {
      if (retryCount.value >= maxRetries) {
        console.warn('已达到最大重试次数，停止重试')
        showRetryButton.value = false
        return
      }

      retryCount.value++
      console.log(`开始第 ${retryCount.value} 次重试初始化`)

      // 重置状态
      initError.value = ''
      showRetryButton.value = false
      isLoading.value = true

      // 延迟重试，避免频繁重试
      setTimeout(() => {
        initializeApplication()
      }, 1000)
    }

    // 组件挂载时开始初始化
    onMounted(() => {
      console.log('App组件已挂载，开始初始化应用')
      initializeApplication()
    })

    return {
      isLoading,
      loadingProgress,
      loadingStep,
      loadingDetail,
      loadingMessage,
      initError,
      showRetryButton,
      retryCount,
      maxRetries,
      retryInitialization
    }
  }
}
</script>

<style scoped>
/* 加载屏幕样式 */
.loading-screen {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
  color: white;
}

.loading-container {
  text-align: center;
  max-width: 400px;
  padding: 2rem;
}

.loading-logo {
  margin-bottom: 2rem;
}

.logo-icon {
  font-size: 4rem;
  margin-bottom: 1rem;
  animation: pulse 2s infinite;
}

.loading-logo h1 {
  font-size: 2rem;
  font-weight: 300;
  margin: 0;
  opacity: 0.9;
}

.loading-progress {
  margin-bottom: 2rem;
}

/* 加载屏幕专用进度条样式 */
.loading-screen .progress-bar {
  background: rgba(255, 255, 255, 0.2);
  height: 4px;
  margin-bottom: 1rem;
  border-radius: 2px;
  overflow: hidden;
}

.loading-screen .progress-fill {
  background: rgba(255, 255, 255, 0.8);
  height: 100%;
  transition: width 0.3s ease;
  border-radius: 2px;
}

.loading-text {
  font-size: 1rem;
  opacity: 0.9;
  margin-bottom: 0.5rem;
}

.loading-detail {
  font-size: 0.8rem;
  opacity: 0.7;
}

.loading-version {
  font-size: 0.8rem;
  opacity: 0.6;
}

/* 错误信息样式 */
.loading-error {
  margin-top: 2rem;
  padding: 1rem;
  background: rgba(255, 255, 255, 0.1);
  border-radius: 8px;
  border: 1px solid rgba(255, 255, 255, 0.2);
}

.error-icon {
  font-size: 2rem;
  margin-bottom: 0.5rem;
}

.error-message {
  font-size: 0.9rem;
  margin-bottom: 1rem;
  opacity: 0.9;
}

.retry-button {
  background: rgba(255, 255, 255, 0.2);
  border: 1px solid rgba(255, 255, 255, 0.3);
  color: white;
  padding: 0.5rem 1rem;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.9rem;
  transition: all 0.3s ease;
}

.retry-button:hover {
  background: rgba(255, 255, 255, 0.3);
  border-color: rgba(255, 255, 255, 0.5);
}

@keyframes pulse {

  0%,
  100% {
    transform: scale(1);
  }

  50% {
    transform: scale(1.1);
  }
}

.app-container {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--bg-primary);
}

.main-content {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  padding: var(--spacing-lg);
  padding-bottom: calc(var(--spacing-lg) + 28px);
  /* 为状态栏留出空间 */
}
</style>