<template>
  <div id="app">
    <!-- 加载屏幕 -->
    <div v-if="isLoading" id="loading-screen" class="loading-screen">
      <div class="loading-container">
        <div class="loading-logo">
          <img :src="logoIcon" alt="Logo" class="logo-icon-img" />
          <h1>Blank Tool</h1>
        </div>
        <div class="loading-progress">
          <div class="progress-bar">
            <div class="progress-fill" :style="{ width: loadingProgress + '%' }"></div>
          </div>
          <div class="loading-text">{{ loadingStep }}</div>
          <div v-if="loadingMessage" class="loading-detail">{{ loadingMessage }}</div>
        </div>
        <div class="loading-timer">
          已耗时: {{ loadingTime }}s
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
      
      <!-- 全局通知组件 -->
      <Notification />
    </div>
  </div>
</template>

<script>
import { ref, onMounted, onUnmounted, getCurrentInstance } from 'vue'
import AppHeader from '@components/common/Header.vue'
import StatusBar from '@components/common/StatusBar.vue'
import Notification from '@components/common/Notification.vue'
import serviceManager from '@services/ServiceManager'
import { ThemeService } from '@services/ThemeService'
import ToolService from '@services/ToolService'
import NotificationService from '@services/NotificationService'
import unifiedApi from './api/unifiedApi'
import ErrorService from '@services/ErrorService'
import { ConfigService } from '@services/ConfigService'
import ApkService from '@services/ApkService'
import CacheService from '@services/CacheService'
import DeviceService from '@services/DeviceService'
import SystemService from '@services/SystemService'
import { useToolStore, useAppConfigStore, useSystemStore } from '@stores'


// CSS variable tokens
import './assets/variables.css'
// const logoIcon = 'images/icon.png'
import logoUrl from '@/assets/images/icon.png';
// 然后在模板或响应式数据中使用
const logoIcon = ref(logoUrl);

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
    
    // 计时器相关
    const loadingTime = ref('0.0')
    let timerInterval = null
    const startTime = ref(0)

    /**
     * 服务注册
     */
    function registerServices() {
      // Core services
      serviceManager.register('config', ConfigService)
      serviceManager.register('notification', NotificationService)

      // Feature services
      serviceManager.register('device', DeviceService)
      serviceManager.register('theme', ThemeService)
      serviceManager.register('tools', ToolService, ['config'])
      serviceManager.register('error', ErrorService, ['notification'])
      serviceManager.register('system', SystemService)
      serviceManager.register('apk', ApkService, ['config'])
      serviceManager.register('cache', CacheService, ['config'])
    }

    /**
     * 创建错误处理器
     */    function createErrorHandler() {
      return (error, instance, info) => {
        console.error('全局错误:', error)
        console.error('错误实例:', instance)
        console.error('错误信息:', info)

        // 获取错误服务并报告错误
        serviceManager.getService('error')
          .then((errorService) => {
            if (errorService && typeof errorService.reportError === 'function') {
              errorService.reportError(error, { context: 'Vue全局错误处理', info })
            }
          })
          .catch((serviceError) => {
            console.error('获取错误服务失败:', serviceError)
          })
      }
    }

    /**
     * 启动计时器
     */
    function startTimer() {
      startTime.value = Date.now()
      if (timerInterval) clearInterval(timerInterval)
      
      timerInterval = setInterval(() => {
        const diff = Date.now() - startTime.value
        loadingTime.value = (diff / 1000).toFixed(1)
      }, 100)
    }

    /**
     * 停止计时器
     */
    function stopTimer() {
      if (timerInterval) {
        clearInterval(timerInterval)
        timerInterval = null
      }
    }

    /**
     * 应用初始化流程 - 顺序执行，失败时抛出异常
     */
    async function initializeApplication() {
      startTimer()
      try {
        initError.value = ''
        loadingProgress.value = 0

        // 定义初始化任务，按依赖关系顺序执行
        const initTasks = [
          { name: '加载服务', task: initializeServices, weight: 40, critical: true },
          { name: '加载配置', task: loadApplicationData, weight: 30, critical: true },
          { name: '工具检查', task: checkToolsStatus, weight: 20, critical: false },
          { name: '界面准备', task: prepareUI, weight: 10, critical: true }
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
        stopTimer()
        console.log('应用初始化完成')

      } catch (error) {
        console.error('应用初始化失败:', error)
        stopTimer()

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
     * 加载应用数据
     */
    async function loadApplicationData() {
      updateProgress('加载配置...', '正在加载应用配置和系统信息', 45)
      
      const appConfigStore = useAppConfigStore()
      const systemStore = useSystemStore()

      try {
        await Promise.all([
          appConfigStore.initialize(),
          systemStore.fetchSystemInfo(),
          systemStore.fetchBuildInfo()
        ])
        console.log('应用数据加载完成')
      } catch (error) {
        console.error('应用数据加载失败:', error)
        // 非关键错误，继续执行
      }
    }

    /**
     * 工具状态检查 - 同步阻塞
     */
    async function checkToolsStatus() {
      updateProgress('检查工具状态...', '正在检查开发工具可用性', 35)

      const toolStore = useToolStore()

      try {
        // 同步等待检查结果，force=true 确保启动时刷新
        await toolStore.fetchTools(true)
        
        const availableTools = toolStore.availableTools
        const tools = toolStore.tools
        const unavailableTools = tools.filter(t => t.status !== 'available')

        console.log(`工具状态检查完成: ${availableTools.length}个可用, ${unavailableTools.length}个不可用`)

        if (availableTools.length > 0) {
          console.log('以下工具可用:', availableTools.map(t => t.name))
        }
        if (unavailableTools.length > 0) {
          console.warn('以下工具不可用:', unavailableTools.map(t => t.name))
        }

      } catch (error) {
        console.warn('工具状态检查失败，但不影响应用启动:', error)
      }
      
      updateProgress('工具检查完成', '工具检查已完成', 50)
    }

    /**
     * 服务初始化
     */
    async function initializeServices() {
      updateProgress('初始化服务...', '正在启动应用服务', 65)

      try {
        // 注册服务
        registerServices()

        // 在服务初始化完成后设置全局错误处理器
        const instance = getCurrentInstance()
        if (instance && instance.appContext.app) {
          instance.appContext.app.config.errorHandler = createErrorHandler()
          console.log('全局错误处理器已设置')
        }


        updateProgress('服务初始化完成', '所有应用服务已启动', 80)
        console.log('服务初始化完成')

      } catch (error) {
        console.error('服务初始化失败:', error)
        throw new Error(`服务初始化失败: ${error.message}`)
      }
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
      const cacheService = await serviceManager.getService('cache')
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
        let attempts = 0;
        const maxAttempts = 50; // 5 seconds timeout

        const checkDOM = () => {
          attempts++;
          // 检查关键元素是否存在
          const loadingScreen = document.querySelector('.loading-screen')

          if (loadingScreen) {
            console.log('DOM已准备就绪')
            resolve()
          } else if (attempts >= maxAttempts) {
            console.warn('等待DOM就绪超时，强制继续')
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
      document.addEventListener('mouseover', showTooltip)
      document.addEventListener('mouseout', hideTooltip)
      document.addEventListener('mousedown', hideTooltip)
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
          const api = unifiedApi.getAPI()
          if (api && typeof api.openDevTools === 'function') {
            api.openDevTools()
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
      const themeService = await serviceManager.getService('theme')
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
      const el = event.target && event.target.closest ? event.target.closest('[data-tooltip]') : null
      if (!el || el._tooltip) return
      const tooltip = el.getAttribute('data-tooltip')
      if (!tooltip) return
      const tooltipElement = document.createElement('div')
      tooltipElement.className = 'tooltip show'
      tooltipElement.textContent = tooltip
      tooltipElement.style.position = 'absolute'
      tooltipElement.style.zIndex = '9999'
      tooltipElement.style.background = 'var(--tooltip-bg, #000000)'
      tooltipElement.style.color = 'var(--tooltip-color, #ffffff)'
      tooltipElement.style.opacity = 'var(--tooltip-opacity, 0.9)'
      tooltipElement.style.padding = '4px 8px'
      tooltipElement.style.borderRadius = '4px'
      tooltipElement.style.fontSize = '12px'
      tooltipElement.style.pointerEvents = 'none'
      const rect = el.getBoundingClientRect()
      tooltipElement.style.left = rect.left + 'px'
      tooltipElement.style.top = (rect.top - 30) + 'px'
      document.body.appendChild(tooltipElement)
      el._tooltip = tooltipElement
    }

    /**
     * 隐藏工具提示
     */
    function hideTooltip(event) {
      const el = event.target && event.target.closest ? event.target.closest('[data-tooltip]') : null
      if (!el || !el._tooltip) return
      document.body.removeChild(el._tooltip)
      delete el._tooltip
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
      console.log('App已挂载，开始初始化应用')
      initializeApplication()
    })

    onUnmounted(() => {
      stopTimer()
    })

    return {
      isLoading,
      loadingProgress,
      loadingStep,
      loadingMessage,
      initError,
      showRetryButton,
      retryCount,
      maxRetries,
      loadingTime,
      retryInitialization,
      logoIcon
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

.logo-icon-img {
  width: 80px; /* Adjust size as needed */
  height: 80px;
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

.loading-timer {
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
