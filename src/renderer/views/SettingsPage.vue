<template>
  <div class="page settings-page">
    <div class="page-content responsive-two-column">
      <div class="left-panel">
        <!-- 常规设置 -->
        <div class="section responsive-section">
          <div class="section-header">
            <h2><span class="section-icon">⚙️</span>常规设置</h2>
            <div class="section-actions">
              <button class="btn btn-sm btn-primary" @click="saveGeneralSettings" data-tooltip="保存当前设置">
                <span>💾</span>
              </button>
              <button class="btn btn-sm btn-secondary" @click="resetGeneralSettings" data-tooltip="重置为默认值">
                <span>🔄</span>
              </button>
            </div>
          </div>
          <div class="settings-group">
            <div class="form-group">
              <label class="form-label" for="language">界面语言</label>
              <select id="language" class="form-control" v-model="settings.language" @change="onSettingChange">
                <option value="zh-CN">简体中文</option>
                <option value="en-US">English</option>
              </select>
              <p class="form-text">选择应用界面显示语言</p>
            </div>
            <div class="form-group">
              <label class="form-label" for="theme">主题设置</label>
              <select id="theme" class="form-control" v-model="settings.theme" @change="onSettingChange">
                <option value="auto">跟随系统</option>
                <option value="light">浅色主题</option>
                <option value="dark">深色主题</option>
              </select>
              <p class="form-text">选择应用主题外观</p>
            </div>
            <div class="form-group">
              <div class="form-check">
                <input type="checkbox" id="autoSave" class="form-check-input" v-model="settings.autoSave"
                  @change="onSettingChange">
                <label class="form-check-label" for="autoSave">
                  自动保存
                </label>
              </div>
              <p class="form-text">自动保存配置和工作状态</p>
            </div>
            <div class="form-group">
              <div class="form-check">
                <input type="checkbox" id="enableNotifications" class="form-check-input"
                  v-model="settings.enableNotifications" @change="onSettingChange">
                <label class="form-check-label" for="enableNotifications">
                  启用通知
                </label>
              </div>
              <p class="form-text">显示操作完成和错误通知</p>
            </div>
          </div>
        </div>

        <!-- 环境设置 -->
        <div class="section responsive-section">
          <div class="section-header">
            <h2><span class="section-icon">🔧</span>环境设置</h2>
            <div class="section-actions">
              <button class="btn btn-sm btn-primary" @click="saveEnvironmentSettings" data-tooltip="保存环境设置">
                <span>💾</span>
              </button>
              <button class="btn btn-sm btn-secondary" @click="resetEnvironmentSettings" data-tooltip="重置为默认值">
                <span>🔄</span>
              </button>
            </div>
          </div>
          <div class="settings-group">
            <div class="form-group">
              <label class="form-label" for="runtime">Python 运行时路径 (Runtime)</label>
              <div class="input-group">
                <input type="text" id="runtime" class="form-control" :value="displayPaths.runtime" readonly
                  placeholder="默认: .\runtime" :title="settings.runtime">
                <button class="btn btn-secondary path-browse-btn" @click="browseDirectory('runtime')">
                  浏览
                </button>
              </div>
              <p class="form-text">指定 Python 运行时环境目录。当前配置: {{ settings.runtime }}</p>
            </div>
            <div class="form-group">
              <label class="form-label" for="server">服务端入口路径 (Server)</label>
              <div class="input-group">
                <input type="text" id="server" class="form-control" :value="displayPaths.server" readonly
                  placeholder="默认: .\backend" :title="settings.server">
                <button class="btn btn-secondary path-browse-btn" @click="browseDirectory('server')">
                  浏览
                </button>
              </div>
              <p class="form-text">指定后端服务代码目录 (包含 main.py)。当前配置: {{ settings.server }}</p>
            </div>
          </div>
        </div>

        <!-- 开发工具 -->
        <div class="section">
          <div class="section-header">
            <h2><span class="section-icon">🛠️</span>开发工具</h2>
            <div class="section-actions">
              <span class="toggle-desc">系统查找</span>
              <div class="toggle-switch-container" :data-tooltip="systemSearchEnabled ? '关闭系统查找' : '开启系统查找'">
                <label class="toggle-switch">
                  <input type="checkbox" :checked="systemSearchEnabled" @change="toggleSystemSearch">
                  <span class="toggle-slider"></span>
                </label>
              </div>
              <button class="btn btn-sm btn-secondary" @click="refreshTools" :disabled="isLoadingTools"
                data-tooltip="重新检测工具">
                <span>🔄</span>
              </button>
            </div>
          </div>
          <div class="tool-grid">
            <div class="tool-card" v-for="tool in tools" :key="tool.key">
              <div class="tool-card-header">
                <div class="tool-header-left">
                  <div class="tool-name">{{ tool.fullName }}</div>
                  <div class="tool-status">
                    <span :class="['status-badge', tool.status === 'available' ? 'status-ok' : 'status-bad']">
                      {{ tool.status === 'available' ? '可用' : '不可用' }}
                    </span>
                    <span v-if="tool.needsUpdate" class="update-badge">需要更新</span>
                  </div>
                </div>
                <div class="tool-header-right">
                  <span class="version-text" v-if="tool.version">{{ tool.version }}</span>
                  <span class="version-text text-muted" v-else>未知版本</span>
                </div>
              </div>
              <div class="tool-card-body">
                <div class="tool-field path-field">
                  <div class="path-input-wrapper">
                    <span class="path-label">路径：</span>
                    <input type="text" class="form-control path-input" :value="tool.path || '未配置'" readonly :title="tool.path || '未配置'">
                    <div class="action-buttons">
                      <button class="btn btn-sm btn-secondary btn-icon" @click="browseToolExecutable(tool.key)" data-tooltip="更改路径">
                        <span>✏️</span>
                      </button>
                      <button class="btn btn-sm btn-secondary btn-icon" @click="checkVersion(tool.key)" data-tooltip="刷新状态">
                        <span>🔄</span>
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 存储管理 -->
        <div class="section">
          <div class="section-header">
            <h2><span class="section-icon">🧹</span>存储管理</h2>
            <div class="section-actions">
              <button class="btn btn-sm btn-secondary" @click="refreshCacheInfo" :disabled="isLoadingCacheInfo" data-tooltip="刷新存储信息">
                <span v-if="!isLoadingCacheInfo">🔄</span>
                <span v-else class="btn-spinner"></span>
              </button>
            </div>
          </div>
          <div class="settings-group">
             <div class="info-grid" style="margin-bottom: 15px;">
                <div class="info-item">
                  <p class="info-label">缓存大小</p>
                  <span class="info-value">{{ formatFileSize(cacheInfo.cache.size) }} ({{ cacheInfo.cache.files }} 文件)</span>
                </div>
                <div class="info-item">
                  <p class="info-label">输出大小</p>
                  <span class="info-value">{{ formatFileSize(cacheInfo.output.size) }} ({{ cacheInfo.output.files }} 文件)</span>
                </div>
                <div class="info-item">
                  <p class="info-label">总计占用</p>
                  <span class="info-value">{{ formatFileSize(cacheInfo.total.size) }}</span>
                </div>
             </div>
             <div class="form-group">
                <p class="form-text">管理应用产生的临时文件和输出文件。</p>
                <div class="btn-group">
                  <button class="btn btn-warning" :class="{ 'loading': isClearingCache }" @click="clearStorage('cache')" 
                    :disabled="isClearingCache || isLoadingCacheInfo">
                    <span v-if="!isClearingCache">🗑️</span>
                    <span v-if="isClearingCache" class="btn-spinner"></span>
                    {{ isClearingCache ? '正在清理...' : '清理缓存' }}
                  </button>
                  <button class="btn btn-warning" :class="{ 'loading': isClearingOutput }" @click="clearStorage('output')" 
                    :disabled="isClearingOutput || isLoadingCacheInfo">
                    <span v-if="!isClearingOutput">📂</span>
                    <span v-if="isClearingOutput" class="btn-spinner"></span>
                    {{ isClearingOutput ? '正在清理...' : '清理输出' }}
                  </button>
                </div>
             </div>
          </div>
        </div>
      </div>

      <div class="right-panel">
        <!-- 构建信息 -->
        <div class="section">
          <h2><span class="section-icon">🔧</span>构建信息</h2>
          <div class="settings-group">
            <div class="info-category">
              <h3>应用信息</h3>
              <div class="info-grid">
                <div class="info-item">
                  <p class="info-label">应用名称</p>
                  <span class="info-value">{{ buildInfo.appName || '加载中...' }}</span>
                </div>
                <div class="info-item">
                  <p class="info-label">应用版本</p>
                  <span class="info-value">{{ buildInfo.appVersion || '加载中...' }}</span>
                </div>
                <div class="info-item">
                  <p class="info-label">应用描述</p>
                  <span class="info-value">{{ buildInfo.appDescription || '加载中...' }}</span>
                </div>
              </div>
            </div>

            <div class="info-category">
              <h3>运行环境</h3>
              <div class="info-grid">
                <div class="info-item">
                  <p class="info-label">Electron版本</p>
                  <span class="info-value">{{ buildInfo.electronVersion}}</span>
                </div>
                <div class="info-item">
                  <p class="info-label">Node.js版本</p>
                  <span class="info-value">{{ buildInfo.nodeVersion}}</span>
                </div>
                <div class="info-item">
                  <p class="info-label">Chrome版本</p>
                  <span class="info-value">{{ buildInfo.chromeVersion }}</span>
                </div>
                <div class="info-item">
                  <p class="info-label">Java版本</p>
                  <span class="info-value">{{ buildInfo.javaVersion}}</span>
                </div>
                <div class="info-item">
                  <p class="info-label">Python版本</p>
                  <span class="info-value">{{ buildInfo.pythonVersion}}</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 系统信息 -->
        <div class="section">
          <div class="section-header">
            <h2><span class="section-icon">💻</span>系统信息</h2>
            <div class="section-actions">
              <button class="btn btn-sm btn-secondary" @click="refreshSystemInfo" :disabled="isLoadingSystemInfo"
                data-tooltip="刷新系统信息">
                <span v-if="isLoadingSystemInfo">🔄</span>
                <span v-else>🔄</span>
              </button>
              <button class="btn btn-sm btn-secondary" @click="exportSystemInfo" data-tooltip="导出系统信息">
                <span>📤</span>
              </button>
            </div>
          </div>
          <div class="settings-group">
            <div class="info-category">
              <h3>操作系统</h3>
              <div class="info-grid">
                <div class="info-item">
                  <p class="info-label">
                    <span class="info-icon">🖥️</span>平台
                  </p>
                  <span class="info-value">{{ systemInfo.platform || '加载中...' }}</span>
                </div>
                <div class="info-item">
                  <p class="info-label">
                    <span class="info-icon">📋</span>版本
                  </p>
                  <span class="info-value">{{ systemInfo.platform_version || '加载中...' }}</span>
                </div>
                <div class="info-item">
                  <p class="info-label">
                    <span class="info-icon">🏗️</span>架构
                  </p>
                  <span class="info-value">{{ systemInfo.architecture || '加载中...' }}</span>
                </div>
                <div class="info-item">
                  <p class="info-label">
                    <span class="info-icon">🏠</span>主机名
                  </p>
                  <span class="info-value">{{ systemInfo.hostname || '加载中...' }}</span>
                </div>
              </div>
            </div>

            <div class="info-category">
              <h3>硬件信息</h3>
              <div class="info-grid">
                <div class="info-item">
                  <p class="info-label">
                    <span class="info-icon">🔧</span>处理器
                  </p>
                  <span class="info-value">{{ systemInfo.processor || '加载中...' }}</span>
                </div>
                <div class="info-item">
                  <p class="info-label">
                    <span class="info-icon">⚙️</span>CPU核心数
                  </p>
                  <span class="info-value">{{ systemInfo.cpuCount || '加载中...' }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, reactive, onMounted, computed } from 'vue'
import serviceManager from '@services/ServiceManager.js'
import { useNotification } from '@composables/useNotification.js'
import { useToolStore, useAppConfigStore, useSystemStore } from '@stores'

export default {
  name: 'SettingsPage',
  setup() {
    // 注入服务
    const { showSuccess, showError: showNotifyError } = useNotification()
    const errorService = serviceManager.getServiceSync('error')
    const settingsServiceRef = ref(null)
    const systemServiceRef = ref(null)

    const toolStore = useToolStore()
    const appConfigStore = useAppConfigStore()
    const systemStore = useSystemStore()
    
    // 响应式数据
    const hasUnsavedChanges = ref(false)
    const isLoadingSystemInfo = ref(false)
    const isLoadingTools = ref(false)
    
    // 显示用的路径数据（绝对路径）
    const displayPaths = reactive({
      runtime: '',
      server: ''
    })

    const settings = reactive({
      // 常规设置
      language: 'zh-CN',
      theme: 'auto',
      autoSave: true,
      enableNotifications: true,

      // 环境设置
      runtime: '.\\runtime',
      server: '.\\backend',

      // 工具路径设置
      adbPath: '',
      aaptPath: '',
      apktoolPath: '',
      bundletoolPath: '',
      javaPath: ''
    })

    const systemInfo = systemStore.systemInfo
    const buildInfo = systemStore.buildInfo
    
    const systemSearchEnabled = ref(false)
    const isClearingCache = ref(false)
    const isClearingOutput = ref(false)
    const isLoadingCacheInfo = ref(false)
    const cacheInfo = ref({
      cache: { size: 0, files: 0 },
      output: { size: 0, files: 0 },
      total: { size: 0, files: 0 }
    })
    const recommendedVersions = {
      java: '11',
      adb: '1.0.41',
      aapt: '30.0.3',
      apktool: '2.7.0',
      bundletool: '1.15.5'
    }

    const checkNeedsUpdate = (key, version) => {
      if (!version) return false
      const min = recommendedVersions[key]
      if (!min) return false
      const normalize = v => String(v).replace(/[^0-9.]/g, '')
      const cmp = (a, b) => {
        const pa = normalize(a).split('.').map(n => parseInt(n || '0', 10))
        const pb = normalize(b).split('.').map(n => parseInt(n || '0', 10))
        const len = Math.max(pa.length, pb.length)
        for (let i = 0; i < len; i++) {
          const da = pa[i] || 0
          const db = pb[i] || 0
          if (da < db) return -1
          if (da > db) return 1
        }
        return 0
      }
      return cmp(version, min) < 0
    }

    const tools = computed(() => {
      const fullNameMap = {
        adb: 'Android Debug Bridge',
        aapt: 'Android Asset Packaging Tool',
        apktool: 'APKTool',
        java: 'Java',
        bundletool: 'BundleTool',
        apksigner: 'Apk Signer',
        zipalign: 'Zipalign',
        jarsigner: 'JAR Signer'
      }
      
      return toolStore.tools.map(item => {
        const key = item.name || item.key
        const fullName = fullNameMap[key] || key
        const version = item.version || ''
        const needsUpdate = checkNeedsUpdate(key, version)
        return {
          key,
          fullName,
          status: item.status || (item.available ? 'available' : 'unavailable'),
          version,
          path: item.path || item.tool_path || '',
          source: item.source || 'unknown',
          needsUpdate
        }
      })
    })

    // 设置变更处理
    const onSettingChange = () => {
      hasUnsavedChanges.value = true
    }

    // 更新显示路径
    const updateDisplayPaths = async () => {
      try {
        if (settings.runtime) {
          displayPaths.runtime = await window.electronAPI.resolvePath(settings.runtime)
        }
        if (settings.server) {
          displayPaths.server = await window.electronAPI.resolvePath(settings.server)
        }
      } catch (e) {
        console.error('解析路径失败:', e)
      }
    }

    // 加载设置
    const loadSettings = async () => {
      try {
        // 从 store 中获取配置，如果没有则初始化
        // (App初始化时已经加载过，这里可以直接使用)
        if (Object.keys(appConfigStore.config).length === 0) {
          await appConfigStore.initialize()
        }
        
        const result = appConfigStore.config

        if (result) {
          // 更新设置对象
          Object.keys(settings).forEach(key => {
            if (result.hasOwnProperty(key)) {
              settings[key] = result[key]
            }
          })
          // 更新显示路径
          await updateDisplayPaths()
        }
      } catch (error) {
        console.error('加载设置失败:', error)
        showError('加载设置失败', error.message)
      }
    }

    // 保存设置
    const saveSettings = async () => {
      try {
        const svc = settingsServiceRef.value || await serviceManager.getService('settings')
        settingsServiceRef.value = svc
        await svc.saveSettings(settings)
        hasUnsavedChanges.value = false
        showSuccess('设置保存成功')
      } catch (error) {
        console.error('保存设置失败:', error)
        showError('保存设置失败', error.message)
      }
    }

    // 重置设置
    const resetSettings = async () => {
      if (!confirm('确定要重置所有设置为默认值吗？此操作不可撤销。')) {
        return
      }

      try {
        const svc = settingsServiceRef.value || await serviceManager.getService('settings')
        settingsServiceRef.value = svc
        await svc.resetSettings()
        await loadSettings() // 重新加载设置
        hasUnsavedChanges.value = false
        showSuccess('设置已重置为默认值')
      } catch (error) {
        console.error('重置设置失败:', error)
        showError('重置设置失败', error.message)
      }
    }

    // 导出设置
    const exportSettings = async () => {
      try {
        const exportData = {
          timestamp: new Date().toISOString(),
          settings: { ...settings }
        }
        const dataStr = JSON.stringify(exportData, null, 2)
        const blob = new Blob([dataStr], { type: 'application/json' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `settings-${new Date().toISOString().split('T')[0]}.json`
        document.body.appendChild(a)
        a.click()
        document.body.removeChild(a)
        URL.revokeObjectURL(url)
        showSuccess('设置导出成功')
      } catch (error) {
        console.error('导出设置失败:', error)
        showError('导出设置失败', error.message)
      }
    }

    // 导入设置
    const importSettings = async () => {
      try {
        const svc = systemServiceRef.value || await serviceManager.getService('system')
        systemServiceRef.value = svc
        const result = await svc.selectFile({ filters: [{ name: 'JSON', extensions: ['json'] }] })
        if (result && result.filePath) {
          showSuccess('设置导入成功')
        }
        await loadSettings() // 重新加载设置
        hasUnsavedChanges.value = false
      } catch (error) {
        console.error('导入设置失败:', error)
        showError('导入设置失败', error.message)
      }
    }

    const refreshCacheInfo = async () => {
      isLoadingCacheInfo.value = true
      try {
        const svc = await serviceManager.getService('cache')
        const info = await svc.getCacheInfo(true)
        if (info) {
          cacheInfo.value = info
        }
      } catch (error) {
        console.error('刷新存储信息失败:', error)
      } finally {
        isLoadingCacheInfo.value = false
      }
    }

    const clearStorage = async (target) => {
      if (target === 'cache') isClearingCache.value = true
      if (target === 'output') isClearingOutput.value = true
      
      try {
        const svc = await serviceManager.getService('cache')
        const result = await svc.clearStorage(target)
        if (result.success) {
          showSuccess('存储清理成功')
          await refreshCacheInfo()
        } else {
          showError('存储清理失败', result.error)
        }
      } catch (error) {
        showError('存储清理失败', error.message)
      } finally {
        if (target === 'cache') isClearingCache.value = false
        if (target === 'output') isClearingOutput.value = false
      }
    }

    // 浏览工具路径
    const browseToolPath = async (target) => {
      try {
        const svc = systemServiceRef.value || await serviceManager.getService('system')
        systemServiceRef.value = svc
        const result = await svc.selectFile({
          title: '选择工具文件',
          filters: [
            { name: '可执行文件', extensions: ['exe', 'jar'] },
            { name: '所有文件', extensions: ['*'] }
          ]
        })

        if (result && result.filePath) {
          settings[target] = result.filePath
          onSettingChange()
        }
      } catch (error) {
        console.error('选择文件失败:', error)
        showError('选择文件失败', error.message)
      }
    }

    // 浏览目录
    const browseDirectory = async (target) => {
      try {
        const svc = systemServiceRef.value || await serviceManager.getService('system')
        systemServiceRef.value = svc
        const result = await svc.selectDirectory({
          title: '选择目录'
        })

        if (result && result.directoryPath) {
          settings[target] = result.directoryPath
          onSettingChange()
          await updateDisplayPaths()
        }
      } catch (error) {
        console.error('选择目录失败:', error)
        showError('选择目录失败', error.message)
      }
    }
    
    // 声明 loadBuildInfo 和 loadSystemInfo 之前，确保 store 已经定义
    // 在 setup 顶部已经定义了 toolStore, appConfigStore, systemStore
    
    const loadBuildInfo = async () => {
      try {
        // 从 store 获取
        if (!systemStore.buildInfo.appName) {
          await systemStore.fetchBuildInfo()
        }
      } catch (error) {
        console.error('加载构建信息失败:', error)
        showError('加载构建信息失败', error.message)
      }
    }

    // 加载系统信息
    const loadSystemInfo = async (forceRefresh = false) => {
      try {
        isLoadingSystemInfo.value = true
        
        // 如果是强制刷新，或者 store 中没有数据，则调用接口获取
        if (forceRefresh || !systemStore.systemInfo.platform) {
          await systemStore.fetchSystemInfo()
        }
      } catch (error) {
        console.error('加载系统信息失败:', error)
        showError('加载系统信息失败', error.message)
      } finally {
        isLoadingSystemInfo.value = false
      }
    }

    // 刷新系统信息
    const refreshSystemInfo = async () => {
      await loadSystemInfo(true)
      showSuccess('系统信息已刷新')
    }

    const toolServiceRef = ref(null)

    const initializeToolView = async () => {
      try {
        isLoadingTools.value = true
        // 初始加载，如果已有数据则不强制刷新
        await toolStore.fetchTools(false)
      } catch (e) {
        console.error('初始化工具视图失败:', e)
        showError('初始化工具视图失败')
      } finally {
        isLoadingTools.value = false
      }
    }

    const refreshTools = async () => {
      try {
        console.log('refreshTools函数被调用')
        isLoadingTools.value = true
        await toolStore.fetchTools(true)
        showSuccess('工具状态已刷新')
      } catch (e) {
        console.error('刷新工具状态失败:', e)
        showError('刷新工具状态失败')
      } finally {
        isLoadingTools.value = false
      }
    }

    const toggleSystemSearch = async () => {
      try {
        const next = !systemSearchEnabled.value
        const toolService = await serviceManager.getService('tools')
        const payload = await toolService.setSystemSearchMode(next)
        if (payload) {
          systemSearchEnabled.value = !!payload.system_search
          showSuccess(`系统查找已${next ? '开启' : '关闭'}`)
          await toolStore.fetchTools(true)
        }
      } catch (e) {
        console.error('切换系统工具优先失败:', e)
        showError('切换系统工具优先失败')
      }
    }

    const checkVersion = async (key) => {
      try {
        const toolService = await serviceManager.getService('tools')
        // 只检查单个工具，不要触发全局列表的重新渲染
        const info = await toolService.checkTool(key, true)
        if (info) {
          // 只更新 store 中对应工具的状态，而不触发整个列表的重新计算
          toolStore.updateTool({
            ...info,
            key: info.name // 确保 key 字段存在
          })
          showSuccess(`${info.name} 状态已更新`)
        } else {
          showError('版本检测失败')
        }
      } catch (e) {
        console.error('版本检测失败:', e)
        showError('版本检测失败')
      }
    }

    const copyText = async (text) => {
      try {
        if (!text) return
        const svc = systemServiceRef.value || await serviceManager.getService('system')
        systemServiceRef.value = svc
        const ok = await svc.copyText(text)
        if (ok) showSuccess('已复制到剪贴板')
        else showError('复制失败')
      } catch (e) {
        showError('复制失败')
      }
    }

    const browseToolExecutable = async (key) => {
      try {
        const svc = systemServiceRef.value || await serviceManager.getService('system')
        systemServiceRef.value = svc
        const result = await svc.selectFile({
          title: '选择工具文件',
          filters: [
            { name: '可执行文件', extensions: ['exe', 'jar'] },
            { name: '所有文件', extensions: ['*'] }
          ]
        })
        if (result && result.filePath) {
            const path = result.filePath
            const t = tools.value.find(t => t.key === key)
            if (t) {
            // 通过 computed 自动更新，无需手动修改
            // t.path = path 
          }
          const dotKey = `tools.${key}`
          // 这里仍然使用 settingsService 保存设置
          const settingsSvc = settingsServiceRef.value || await serviceManager.getService('settings')
          settingsServiceRef.value = settingsSvc
          await settingsSvc.saveSettings({ [dotKey]: path })
          showSuccess('工具路径已保存')
          await refreshTools()
        }
      } catch (e) {
        console.error('选择工具文件失败:', e)
        showError('选择工具文件失败')
      }
    }

    // 导出系统信息
    const exportSystemInfo = async () => {
      try {
        const exportData = {
          timestamp: new Date().toISOString(),
          systemInfo: systemInfo,
          buildInfo: buildInfo
        }

        const dataStr = JSON.stringify(exportData, null, 2)
        const blob = new Blob([dataStr], { type: 'application/json' })
        const url = URL.createObjectURL(blob)

        const a = document.createElement('a')
        a.href = url
        a.download = `system-info-${new Date().toISOString().split('T')[0]}.json`
        document.body.appendChild(a)
        a.click()
        document.body.removeChild(a)
        URL.revokeObjectURL(url)

        showSuccess('系统信息已导出')
      } catch (error) {
        console.error('导出系统信息失败:', error)
        showError('导出系统信息失败')
      }
    }

    // 分类级别的保存和重置方法
    const saveGeneralSettings = async () => {
      try {
        const generalSettings = {
          language: settings.language,
          theme: settings.theme,
          autoUpdate: settings.autoUpdate,
          startMinimized: settings.startMinimized,
          closeToTray: settings.closeToTray
        }
        const svc = settingsServiceRef.value || await serviceManager.getService('settings')
        settingsServiceRef.value = svc
        await svc.saveSettings(generalSettings)
        showSuccess('常规设置保存成功')
      } catch (error) {
        console.error('保存常规设置失败:', error)
        showError('保存常规设置失败', error.message)
      }
    }

    const resetGeneralSettings = async () => {
      if (!confirm('确定要重置常规设置为默认值吗？')) return

      try {
        settings.language = 'zh-CN'
        settings.theme = 'auto'
        settings.autoUpdate = true
        settings.startMinimized = false
        settings.closeToTray = false
        await saveGeneralSettings()
        showSuccess('常规设置已重置')
      } catch (error) {
        showError('重置常规设置失败', error.message)
      }
    }

    const saveEnvironmentSettings = async () => {
      try {
        const environmentSettings = {
          runtime: settings.runtime,
          server: settings.server
        }
        const svc = settingsServiceRef.value || await serviceManager.getService('settings')
        settingsServiceRef.value = svc
        await svc.saveSettings(environmentSettings)
        showSuccess('环境设置保存成功')
      } catch (error) {
        console.error('保存环境设置失败:', error)
        showError('保存环境设置失败', error.message)
      }
    }

    const resetEnvironmentSettings = async () => {
      if (!confirm('确定要重置环境设置为默认值吗？')) return

      try {
        settings.runtime = '.\\runtime'
        settings.server = '.\\backend'
        await saveEnvironmentSettings()
        showSuccess('环境设置已重置')
      } catch (error) {
        showError('重置环境设置失败', error.message)
      }
    }

    // 工具方法
    const formatFileSize = (bytes) => {
      if (!bytes) return '0 B'
      const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
      const i = Math.floor(Math.log(bytes) / Math.log(1024))
      return `${(bytes / Math.pow(1024, i)).toFixed(2)} ${sizes[i]}`
    }

    const showError = (title, message = '') => {
      if (errorService) {
        const err = new Error(message || title || '未知错误')
        // errorService might be a ref too if we changed App.vue to provide errorServiceRef
        const es = errorService.value || errorService
        if (es && typeof es.reportError === 'function') {
          es.reportError(err, { category: 'service', context: title || '操作失败' })
        }
      }
      showNotifyError(title, message)
    }

    // 生命周期
    onMounted(async () => {
      console.log('SettingsPage组件已挂载')
      try {
        settingsServiceRef.value = await serviceManager.getService('settings')
      } catch { }
      await loadSettings()
      await loadSystemInfo()
      await loadBuildInfo()
      await initializeToolView()
      refreshCacheInfo()
    })

    return {
      settings,
      systemInfo,
      buildInfo,
      tools,
      systemSearchEnabled,
      isLoadingTools,
      hasUnsavedChanges,
      isLoadingSystemInfo,
      onSettingChange,
      saveSettings,
      resetSettings,
      exportSettings,
      importSettings,
      browseToolPath,
      browseDirectory,
      refreshSystemInfo,
      exportSystemInfo,
      refreshTools,
      toggleSystemSearch,
      copyText,
      checkVersion,
      browseToolExecutable,
      // 分类级别的方法
      saveGeneralSettings,
      resetGeneralSettings,
      saveEnvironmentSettings,
      resetEnvironmentSettings,
      displayPaths,
      clearStorage,
      isClearingCache,
      isClearingOutput,
      cacheInfo,
      isLoadingCacheInfo,
      refreshCacheInfo,
      formatFileSize
    }
  }
}
</script>
