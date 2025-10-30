<template>
  <div class="page apk-page">
    <div class="page-content responsive-two-column">
      <div class="left-panel">
        <!-- APK 解析区域 -->
        <div class="section responsive-section">
          <h2><span class="section-icon">📦</span>APK 解析</h2>
          <div 
            class="file-drop-zone" 
            @drop="handleDrop($event, handleApkFileSelect)"
            @dragover.prevent
            @dragenter.prevent
            @click="$refs.apkFileInput.click()"
          >
            <p>拖拽 APK 文件到此处，或点击选择文件</p>
            <input 
              ref="apkFileInput" 
              type="file" 
              accept=".apk" 
              style="display: none;"
              @change="handleFileInputChange($event, handleApkFileSelect)"
            >
          </div>
          <div v-if="selectedApkFile" class="file-info">
            <p><strong>文件名:</strong> {{ selectedApkFile.name }}</p>
            <p><strong>大小:</strong> {{ formatFileSize(selectedApkFile.size) }}</p>
          </div>
          <div class="btn-group">
            <button 
              class="btn btn-primary" 
              :disabled="!selectedApkFile"
              @click="analyzeApk"
            >
              <span>🔍</span>解析 APK
            </button>
            <button 
              class="btn btn-secondary" 
              :disabled="!selectedApkFile"
              @click="extractApk"
            >
              <span>📂</span>提取资源
            </button>
          </div>
          <div v-if="apkAnalysisResult" class="analysis-result">
            <div v-html="apkAnalysisResult"></div>
          </div>
        </div>

        <!-- APK/AAB 安装 -->
        <div class="section responsive-section" >
          <h2><span class="section-icon">⬇️</span>应用安装</h2>
          <div 
            class="file-drop-zone"
            @drop="handleDrop($event, handleInstallFileSelect)"
            @dragover.prevent
            @dragenter.prevent
            @click="$refs.installFileInput.click()"
          >
            <p>拖拽 APK/AAB 文件到此处安装</p>
            <input 
              ref="installFileInput" 
              type="file" 
              accept=".apk,.aab" 
              style="display: none;"
              @change="handleFileInputChange($event, handleInstallFileSelect)"
            >
          </div>
          <div v-if="selectedInstallFile" class="file-info">
            <p><strong>文件名:</strong> {{ selectedInstallFile.name }}</p>
            <p><strong>大小:</strong> {{ formatFileSize(selectedInstallFile.size) }}</p>
          </div>
          <div v-if="installProgress.show" class="progress-bar">
            <div class="progress-fill" :style="{ width: installProgress.value + '%' }"></div>
          </div>
          <div class="btn-group">
            <button 
              class="btn btn-success" 
              :disabled="!selectedInstallFile"
              @click="installApp"
            >
              <span>📲</span>安装应用
            </button>
          </div>
        </div>
      </div>

      <div class="right-panel">
        
        <!-- APK 反编译 -->
        <div class="section responsive-section">
          <h2><span class="section-icon">🔓</span>APK 反编译</h2>
          <div 
            class="file-drop-zone"
            @drop="handleDrop($event, handleDecompileFileSelect)"
            @dragover.prevent
            @dragenter.prevent
            @click="$refs.decompileFileInput.click()"
          >
            <p>拖拽 APK 文件到此处进行反编译</p>
            <input 
              ref="decompileFileInput" 
              type="file" 
              accept=".apk" 
              style="display: none;"
              @change="handleFileInputChange($event, handleDecompileFileSelect)"
            >
          </div>
          <div v-if="selectedDecompileFile" class="file-info">
            <p><strong>文件名:</strong> {{ selectedDecompileFile.name }}</p>
            <p><strong>大小:</strong> {{ formatFileSize(selectedDecompileFile.size) }}</p>
          </div>
          <div class="btn-group">
            <button 
              class="btn btn-primary" 
              :disabled="!selectedDecompileFile"
              @click="startDecompile"
            >
              <span>🔓</span>开始反编译
            </button>
            <button 
              class="btn btn-secondary" 
              :disabled="!decompileOutputPath"
              @click="openDecompileOutput"
            >
              <span>📂</span>打开输出目录
            </button>
          </div>
          <div v-if="decompileProgress.show" class="progress-bar">
            <div class="progress-fill" :style="{ width: decompileProgress.value + '%' }"></div>
          </div>
          <div v-if="decompileResult" class="analysis-result">
            <div v-html="decompileResult"></div>
          </div>
        </div>

        <!-- APK 回编译 -->
        <div class="section responsive-section" >
          <h2><span class="section-icon">🔒</span>APK 回编译</h2>
          <div class="file-drop-zone">
            <p>选择反编译后的项目目录进行回编译</p>
            <button class="btn btn-secondary" @click="selectProjectDir">
              <span>📁</span>选择项目目录
            </button>
          </div>
          <div v-if="selectedProjectDir" class="file-info">
            <p><strong>项目目录:</strong> {{ selectedProjectDir }}</p>
          </div>
          <div class="btn-group">
            <button 
              class="btn btn-success" 
              :disabled="!selectedProjectDir"
              @click="startRecompile"
            >
              <span>🔒</span>开始回编译
            </button>
            <button 
              class="btn btn-secondary" 
              :disabled="!recompileOutputPath"
              @click="openRecompileOutput"
            >
              <span>📂</span>打开输出目录
            </button>
          </div>
          <div v-if="recompileProgress.show" class="progress-bar">
            <div class="progress-fill" :style="{ width: recompileProgress.value + '%' }"></div>
          </div>
          <div v-if="recompileResult" class="analysis-result">
            <div v-html="recompileResult"></div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, reactive, inject } from 'vue'
import electronAPIService from '../services/ElectronAPIService.js'

export default {
  name: 'ApkPage',
  setup() {
    // 注入服务
    const apkService = inject('apkService')
    const deviceService = inject('deviceService')
    const notificationService = inject('notificationService')

    // 响应式数据
    const selectedApkFile = ref(null)
    const selectedInstallFile = ref(null)
    const selectedDecompileFile = ref(null)
    const selectedProjectDir = ref(null)
    
    const apkAnalysisResult = ref(null)
    const decompileResult = ref(null)
    const recompileResult = ref(null)
    
    const decompileOutputPath = ref(null)
    const recompileOutputPath = ref(null)

    const installProgress = reactive({ show: false, value: 0 })
    const decompileProgress = reactive({ show: false, value: 0 })
    const recompileProgress = reactive({ show: false, value: 0 })

    const decompileOptions = reactive({
      resources: true,
      sources: true,
      manifest: true
    })

    const recompileOptions = reactive({
      sign: true,
      align: true,
      optimize: false
    })

    // 文件处理方法
    const handleDrop = (event, callback) => {
      event.preventDefault()
      const files = event.dataTransfer.files
      if (files.length > 0) {
        callback(files[0])
      }
    }

    const handleFileInputChange = (event, callback) => {
      const files = event.target.files
      if (files.length > 0) {
        callback(files[0])
      }
    }

    const handleApkFileSelect = (file) => {
      if (file && file.name.endsWith('.apk')) {
        selectedApkFile.value = file
        console.log('选择APK文件:', file.name)
      } else {
        showError('文件格式错误', '请选择有效的APK文件')
      }
    }

    const handleInstallFileSelect = (file) => {
      if (file && (file.name.endsWith('.apk') || file.name.endsWith('.aab'))) {
        selectedInstallFile.value = file
        console.log('选择安装文件:', file.name)
      } else {
        showError('文件格式错误', '请选择有效的APK或AAB文件')
      }
    }

    const handleDecompileFileSelect = (file) => {
      if (file && file.name.endsWith('.apk')) {
        selectedDecompileFile.value = file
        console.log('选择反编译文件:', file.name)
      } else {
        showError('文件格式错误', '请选择有效的APK文件')
      }
    }

    // APK操作方法
    const analyzeApk = async () => {
      if (!selectedApkFile.value) return

      try {
        showLoading('正在解析APK...')
        const result = await apkService.analyzeApk(selectedApkFile.value.path)
        
        if (result.success) {
          apkAnalysisResult.value = displayApkAnalysisResult(result.data)
          showSuccess('APK解析完成')
        } else {
          showError('APK解析失败', result.error)
        }
      } catch (error) {
        console.error('APK解析错误:', error)
        showError('APK解析失败', error.message)
      }
    }

    const extractApk = async () => {
      if (!selectedApkFile.value) return

      try {
        showLoading('正在提取APK资源...')
        const result = await apkService.extractApkResources(selectedApkFile.value.path)
        
        if (result.success) {
          showSuccess('APK资源提取完成', `输出目录: ${result.outputPath}`)
        } else {
          showError('APK资源提取失败', result.error)
        }
      } catch (error) {
        console.error('APK提取错误:', error)
        showError('APK提取失败', error.message)
      }
    }

    const installApp = async () => {
      if (!selectedInstallFile.value) return

      try {
        installProgress.show = true
        installProgress.value = 0

        const result = await deviceService.installApp(selectedInstallFile.value.path)
        
        if (result.success) {
          installProgress.value = 100
          showSuccess('应用安装完成')
        } else {
          showError('应用安装失败', result.error)
        }
      } catch (error) {
        console.error('应用安装错误:', error)
        throw error
      } finally {
        setTimeout(() => {
          installProgress.show = false
          installProgress.value = 0
        }, 2000)
      }
    }

    const startDecompile = async () => {
      if (!selectedDecompileFile.value) return

      try {
        decompileProgress.show = true
        decompileProgress.value = 0

        const options = {
          resources: decompileOptions.resources,
          sources: decompileOptions.sources,
          manifest: decompileOptions.manifest
        }

        const result = await apkService.decompileApk(selectedDecompileFile.value.path, options)
        
        if (result.success) {
          decompileProgress.value = 100
          decompileOutputPath.value = result.outputPath
          decompileResult.value = `<p>反编译完成！输出目录: ${result.outputPath}</p>`
          showSuccess('APK反编译完成')
        } else {
          showError('APK反编译失败', result.error)
        }
      } catch (error) {
        console.error('APK反编译错误:', error)
        showError('APK反编译失败', error.message)
      } finally {
        setTimeout(() => {
          decompileProgress.show = false
          decompileProgress.value = 0
        }, 2000)
      }
    }

    const openDecompileOutput = async () => {
      if (decompileOutputPath.value) {
        await electronAPIService.api.openPath(decompileOutputPath.value)
      }
    }

    const selectProjectDir = async () => {
      try {
        const result = await electronAPIService.api.selectDirectory()
        if (result && !result.canceled) {
          selectedProjectDir.value = result.filePaths[0]
        }
      } catch (error) {
        console.error('选择目录错误:', error)
        showError('选择目录失败', error.message)
      }
    }

    const startRecompile = async () => {
      if (!selectedProjectDir.value) return

      try {
        recompileProgress.show = true
        recompileProgress.value = 0

        const options = {
          sign: recompileOptions.sign,
          align: recompileOptions.align,
          optimize: recompileOptions.optimize
        }

        const result = await apkService.recompileApk(selectedProjectDir.value, options)
        
        if (result.success) {
          recompileProgress.value = 100
          recompileOutputPath.value = result.outputPath
          recompileResult.value = `<p>回编译完成！输出文件: ${result.outputPath}</p>`
          showSuccess('APK回编译完成')
        } else {
          showError('APK回编译失败', result.error)
        }
      } catch (error) {
        console.error('APK回编译错误:', error)
        showError('APK回编译失败', error.message)
      } finally {
        setTimeout(() => {
          recompileProgress.show = false
          recompileProgress.value = 0
        }, 2000)
      }
    }

    const openRecompileOutput = async () => {
      if (recompileOutputPath.value) {
        await electronAPIService.api.openPath(recompileOutputPath.value)
      }
    }

    // 工具方法
    const formatFileSize = (bytes) => {
      if (bytes === 0) return '0 Bytes'
      const k = 1024
      const sizes = ['Bytes', 'KB', 'MB', 'GB']
      const i = Math.floor(Math.log(bytes) / Math.log(k))
      return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
    }

    const displayApkAnalysisResult = (data) => {
      return `
        <h3>APK 信息</h3>
        <p><strong>包名:</strong> ${data.packageName || 'N/A'}</p>
        <p><strong>版本名:</strong> ${data.versionName || 'N/A'}</p>
        <p><strong>版本号:</strong> ${data.versionCode || 'N/A'}</p>
        <p><strong>最小SDK:</strong> ${data.minSdkVersion || 'N/A'}</p>
        <p><strong>目标SDK:</strong> ${data.targetSdkVersion || 'N/A'}</p>
        <p><strong>权限数量:</strong> ${data.permissions?.length || 0}</p>
      `
    }

    const showSuccess = (title, message = '') => {
      if (notificationService) {
        notificationService.success(title, message)
      }
    }

    const showError = (title, message = '') => {
      if (notificationService) {
        notificationService.error(title, message)
      }
    }

    const showLoading = (message) => {
      console.log('Loading:', message)
    }

    return {
      selectedApkFile,
      selectedInstallFile,
      selectedDecompileFile,
      selectedProjectDir,
      apkAnalysisResult,
      decompileResult,
      recompileResult,
      decompileOutputPath,
      recompileOutputPath,
      installProgress,
      decompileProgress,
      recompileProgress,
      decompileOptions,
      recompileOptions,
      handleDrop,
      handleFileInputChange,
      handleApkFileSelect,
      handleInstallFileSelect,
      handleDecompileFileSelect,
      analyzeApk,
      extractApk,
      installApp,
      startDecompile,
      openDecompileOutput,
      selectProjectDir,
      startRecompile,
      openRecompileOutput,
      formatFileSize
    }
  }
}
</script>

<style scoped>

/* 应用列表特殊样式 */
.app-list-container {
  max-height: 300px;
  overflow-y: auto;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--card-bg);
  margin-top: 10px;
}

.app-list {
  padding: 0;
}

.app-list .placeholder {
  text-align: center;
  color: var(--text-secondary);
  padding: 20px;
  margin: 0;
}

.app-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border-color);
  transition: background-color 0.2s ease;
}

.app-item:last-child {
  border-bottom: none;
}

.app-item:hover {
  background-color: var(--hover-bg);
}

.app-package-name {
  flex: 1;
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 14px;
  color: var(--text-primary);
  word-break: break-all;
  margin-right: 16px;
}

.app-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

.app-actions .btn-small {
  padding: 6px 12px;
  font-size: 12px;
  min-width: auto;
  white-space: nowrap;
  transition: all 0.2s ease;
}

.app-actions .btn-small.loading {
  opacity: 0.7;
  cursor: not-allowed;
}

.app-actions .btn-small.success {
  background-color: var(--success-color);
  border-color: var(--success-color);
  color: white;
}

.app-actions .btn-small.error {
  background-color: var(--danger-color);
  border-color: var(--danger-color);
  color: white;
}

.app-actions .btn-small:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.app-actions .btn-small:disabled:hover {
  transform: none;
}
</style>