<template>
  <div class="page apk-page">
    <div class="page-content responsive-two-column">
      <div class="left-panel">
        <!-- APK 解析区域 -->
        <div class="section responsive-section">
          <h2><span class="section-icon">📦</span>APK 解析</h2>
          <div class="file-drop-zone" @drop="handleDrop($event, handleApkFileSelect)" @dragover.prevent
            @dragenter.prevent @click="!isAnalyzing && selectApkFile()">
            <p>拖拽 APK 文件到此处，或点击选择文件</p>
            <input ref="apkFileInput" type="file" accept=".apk" style="display: none;"
              @change="handleFileInputChange($event, handleApkFileSelect)">
          </div>
          <div v-if="selectedAnalysisFile" class="file-info">
            <p><strong>文件名:</strong> {{ selectedAnalysisFile.name }}</p>
            <p><strong>大小:</strong> {{ formatFileSize(selectedAnalysisFile.size) }}</p>
          </div>
          <div v-if="apkAnalysisResult" class="analysis-result">
            <div v-html="apkAnalysisResult"></div>
          </div>
          <div class="actions-bottom-right">
            <div class="btn-group">
              <button class="btn btn-primary" :disabled="!selectedAnalysisFile" @click="analyzeApk">
                <span>🔍</span>解析 APK
              </button>
              <button class="btn btn-secondary" :disabled="!selectedAnalysisFile" @click="extractApk">
                <span>📂</span>提取资源
              </button>
            </div>
          </div>
        </div>

        <!-- 包体安装 -->
        <div class="section responsive-section">
          <h2><span class="section-icon">⬇️</span>包体安装</h2>
          <div class="file-drop-zone" :class="{ 'disabled': isInstalling }"
            @drop="!isInstalling && handleDrop($event, handleInstallFileSelect)" @dragover.prevent @dragenter.prevent
            @click="!isInstalling && selectInstallFile()">
            <p>拖拽 APK/AAB 文件到此处安装</p>
            <input ref="installFileInput" type="file" accept=".apk,.aab" style="display: none;" :disabled="isInstalling"
              @change="handleFileInputChange($event, handleInstallFileSelect)">
          </div>
          <div v-if="selectedInstallFile" class="file-info">
            <p><strong>文件名:</strong> {{ selectedInstallFile.name }}</p>
            <p><strong>大小:</strong> {{ formatFileSize(selectedInstallFile.size) }}</p>
          </div>
          <div class="actions-bottom-right">
            <div class="btn-group">
              <button class="btn btn-success" :class="{ 'loading': isInstalling }"
                :disabled="!selectedInstallFile || isInstalling" @click="installApp">
                <span v-if="!isInstalling">📲</span>
                <span v-if="isInstalling" class="btn-spinner"></span>
                {{ isInstalling ? '安装中...' : '安装' }}
              </button>
            </div>
          </div>
        </div>
      </div>

      <div class="right-panel">

        <!-- APK 反编译 -->
        <div class="section responsive-section">
          <h2><span class="section-icon">🔓</span>APK 反编译</h2>
          <div class="file-drop-zone" @drop="handleDrop($event, handleDecompileFileSelect)" @dragover.prevent
            @dragenter.prevent @click="selectDecompileFile()">
            <p>拖拽 APK 文件到此处进行反编译</p>
            <input ref="decompileFileInput" type="file" accept=".apk" style="display: none;"
              @change="handleFileInputChange($event, handleDecompileFileSelect)">
          </div>
          <div v-if="selectedDecompileFile" class="file-info">
            <p><strong>文件名:</strong> {{ selectedDecompileFile.name }}</p>
            <p><strong>大小:</strong> {{ formatFileSize(selectedDecompileFile.size) }}</p>
          </div>
          <div v-if="decompileResult" class="analysis-result">
            <div v-html="decompileResult"></div>
          </div>
          <div class="actions-bottom-right">
            <div class="btn-group">
              <button class="btn btn-primary" :class="{ 'loading': isDecompiling }"
                :disabled="!selectedDecompileFile || isDecompiling" @click="startDecompile">
                <span v-if="!isDecompiling">🔓</span>
                <span v-if="isDecompiling" class="btn-spinner"></span>
                {{ isDecompiling ? '反编译中...' : '开始反编译' }}
              </button>
              <button class="btn btn-secondary" :disabled="!decompileOutputPath" @click="openDecompileOutput">
                <span>📂</span>打开输出
              </button>
            </div>
          </div>
        </div>

        <!-- APK 回编译 -->
        <div class="section responsive-section">
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
          <div v-if="recompileProgress && recompileProgress.show" class="progress-bar">
            <div class="progress-fill" :style="{ width: recompileProgress.value + '%' }"></div>
          </div>
          <div v-if="recompileResult" class="analysis-result">
            <div v-html="recompileResult"></div>
          </div>
          <div class="actions-bottom-right">
            <div class="btn-group">
              <button class="btn btn-success" :disabled="!selectedProjectDir" @click="startRecompile">
                <span>🔒</span>开始回编译
              </button>
              <button class="btn btn-secondary" :disabled="!recompileOutputPath" @click="openRecompileOutput">
                <span>📂</span>打开输出
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, inject, onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import serviceManager from '@services/ServiceManager.js'
import { useNotification } from '@composables/useNotification.js'
import { usePackageStore } from '@stores/packageStore.js'

export default {
  name: 'PackagePage',
  setup() {
    const packageStore = usePackageStore()
    const {
      selectedAnalysisFile,
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
      recompileOptions
    } = storeToRefs(packageStore)

    const isInstalling = ref(false)
    const isDecompiling = ref(false)
    const isRecompiling = ref(false)
    const isAnalyzing = ref(false)

    // Notification composable
    const { showSuccess, showError, showLoading, completeLoading, failLoading } = useNotification()
    const errorService = inject('errorService', null)

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
        selectedAnalysisFile.value = file
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

    const selectApkFile = async () => {
      await selectFileWithStats(selectedAnalysisFile)
    }

    const selectInstallFile = async () => {
      await selectFileWithStats(selectedInstallFile, ['apk', 'aab'])
    }

    const selectDecompileFile = async () => {
      await selectFileWithStats(selectedDecompileFile)
    }

    const selectFileWithStats = async (targetRef, extensions = ['apk']) => {
      try {
        const systemSvc = await serviceManager.getService('system')
        const res = await systemSvc.selectFile({
          title: '选择文件',
          filters: [{ name: 'Android Packages', extensions }]
        })
        if (res && !res.canceled) {
          const p = (res.filePath || (res.filePaths && res.filePaths[0]) || '').trim()
          if (p) {
            const name = p.split(/[/\\]/).pop()
            let size = 0
            try {
              const stats = await systemSvc.getFileStats(p)
              if (stats && stats.size) size = stats.size
            } catch { }
            targetRef.value = { name, path: p, size }
          }
        }
      } catch (error) {
        console.error('选择文件错误:', error)
        showError('选择文件失败', error.message || '')
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
    const apkServiceRef = ref(null)

    const analyzeApk = async () => {
      if (!selectedAnalysisFile.value) return

      try {
        const loadingId = showLoading('正在解析APK...')
        const apkService = apkServiceRef.value || await serviceManager.getService('apk')
        apkServiceRef.value = apkService
        console.log('分析APK:', selectedAnalysisFile.value)
        const result = await apkService.analyzeApk(selectedAnalysisFile.value.path)

        if (result.success) {
          apkAnalysisResult.value = displayApkAnalysisResult(result.data)
          if (loadingId) {
            completeLoading(loadingId, 'APK解析完成', '')
            return
          }
          showSuccess('APK解析完成')
        } else {
          if (loadingId) {
            failLoading(loadingId, 'APK解析失败', String(result.error || ''))
            return
          }
          showError('APK解析失败', result.error)
        }
      } catch (error) {
        const es = errorService && errorService.value
        if (es) es.reportError(error, { category: 'tool', context: 'apk.analyze' })

        if (loadingId) {
          failLoading(loadingId, 'APK解析失败', error.message || '')
          return
        }
        showError('APK解析失败', error.message)
      }
    }

    const extractApk = async () => {
      if (!selectedAnalysisFile.value) return

      try {
        const loadingId = showLoading('正在提取APK资源...')
        const apkService = apkServiceRef.value || await serviceManager.getService('apk')
        apkServiceRef.value = apkService
        const result = await apkService.extractApkResources(selectedAnalysisFile.value.path)

        if (result.success) {
          showSuccess('APK资源提取完成', `输出目录: ${result.outputPath}`)
          if (loadingId) completeLoading(loadingId, '提取完成', `输出目录: ${result.outputPath}`)
        } else {
          showError('APK资源提取失败', result.error)
          if (loadingId) failLoading(loadingId, '提取失败', String(result.error || ''))
        }
      } catch (error) {
        console.error('APK提取错误:', error)
        showError('APK提取失败', error.message)
        const es = errorService && errorService.value
        if (es) es.reportError(error, { category: 'tool', context: 'apk.extract' })
      }
    }

    const installApp = async () => {
      if (!selectedInstallFile.value) return

      try {
        isInstalling.value = true
        const loadingId = showLoading('正在安装应用...')

        const deviceSvc = await serviceManager.getService('device')
        console.log('installApp', selectedInstallFile.value)
        const result = await deviceSvc.installApp(selectedInstallFile.value.path)

        if (result.success) {
          console.log('应用安装成功:', result)
          if (loadingId) {
            completeLoading(loadingId, '安装完成', '')
            return
          } else {
            showSuccess('应用安装完成')
          }
        } else {
          if (loadingId) {
            failLoading(loadingId, '安装失败', String(result.error || ''))
            return
          }
          showError('应用安装失败', result.error)
        }
      } catch (error) {

        showError('应用安装失败', error.message)
        const es = errorService && errorService.value
        if (es) es.reportError(error, { category: 'device', context: 'device.install' })
      } finally {
        isInstalling.value = false
      }
    }

    const startDecompile = async () => {
      if (!selectedDecompileFile.value) return

      try {
        isDecompiling.value = true
        if (decompileProgress && decompileProgress.value) {
            decompileProgress.value.show = true
            decompileProgress.value.value = 0
        }
        const loadingId = showLoading('正在反编译APK...')

        const options = {
          resources: decompileOptions.value.resources,
          sources: decompileOptions.value.sources,
          manifest: decompileOptions.value.manifest
        }

        const apkService = apkServiceRef.value || await serviceManager.getService('apk')
        apkServiceRef.value = apkService
        const result = await apkService.decompileApk(selectedDecompileFile.value.path, options)

        if (result.success) {
          if (decompileProgress && decompileProgress.value) {
              decompileProgress.value.value = 100
          }
          decompileOutputPath.value = result.outputPath

          const outputPath = result.outputPath
          decompileResult.value = `
            <div class="apk-info-grid">
              <div class="info-row">
                <span class="label">状态:</span>
                <span class="value highlight text-success">反编译成功</span>
              </div>
              <div class="info-row">
                <span class="label">输出目录:</span>
                <span class="value code">${outputPath}</span>
              </div>
              <div class="info-group">
                <div class="info-col">
                  <span class="label">资源文件:</span>
                  <span class="value">${options.resources ? '已提取' : '跳过'}</span>
                </div>
                <div class="info-col">
                  <span class="label">源代码:</span>
                  <span class="value">${options.sources ? '已反编译' : '跳过'}</span>
                </div>
              </div>
            </div>
          `

          if (loadingId) {
            completeLoading(loadingId, '反编译完成', `输出目录: ${result.outputPath}`)
            return
          }
          showSuccess('APK反编译完成')
        } else {
          if (loadingId) {
            failLoading(loadingId, '反编译失败', String(result.error || ''))
            return
          }
          showError('APK反编译失败', result.error)
        }
      } catch (error) {
        console.error('APK反编译错误:', error)
        showError('APK反编译失败', error.message)
        const es = errorService && errorService.value
        if (es) es.reportError(error, { category: 'tool', context: 'apk.decompile' })
      } finally {
        isDecompiling.value = false
        setTimeout(() => {
          if (decompileProgress && decompileProgress.value) {
            decompileProgress.value.show = false
            decompileProgress.value.value = 0
          }
        }, 2000)
      }
    }

    const openDecompileOutput = async () => {
      if (decompileOutputPath.value) {
        const svc = await serviceManager.getService('system')
        await svc.openPath(decompileOutputPath.value)
      }
    }

    const selectProjectDir = async () => {
      try {
        const svc = await serviceManager.getService('system')
        const result = await svc.selectDirectory()
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
          sign: recompileOptions.value.sign,
          align: recompileOptions.value.align,
          optimize: recompileOptions.value.optimize
        }

        const apkService = apkServiceRef.value || await serviceManager.getService('apk')
        apkServiceRef.value = apkService
        const result = await apkService.recompileApk(selectedProjectDir.value, options)

        if (result.success) {
          recompileProgress.value = 100
          recompileOutputPath.value = result.outputPath
          recompileResult.value = `<p>回编译完成！输出文件: ${result.outputPath}</p>`
          showSuccess('APK回编译完成')
          console.log('APK回编译成功:', result)
          if (loadingId) completeLoading(loadingId, '回编译完成', `输出文件: ${result.outputPath}`)
        } else {
          showError('APK回编译失败', result.error)
          console.error('APK回编译失败:', result.error)
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
        const svc = await serviceManager.getService('system')
        await svc.openPath(recompileOutputPath.value)
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
      if (!data) return ''

      // 格式化权限列表
      let permissionsHtml = ''
      if (data.permissions && data.permissions.length > 0) {
        // 只显示前5个权限，其他的折叠
        const visiblePerms = data.permissions.slice(0, 5)
        const hiddenPerms = data.permissions.slice(5)

        permissionsHtml = `<div class="permissions-list">`
        visiblePerms.forEach(p => {
          // 提取权限名称的最后一部分
          const name = p.name || p
          const shortName = name.split('.').pop()
          permissionsHtml += `<div class="perm-tag" title="${name}">${shortName}</div>`
        })

        if (hiddenPerms.length > 0) {
          permissionsHtml += `<div class="perm-tag more" title="还有 ${hiddenPerms.length} 个权限">+${hiddenPerms.length}</div>`
        }
        permissionsHtml += `</div>`
      } else {
        permissionsHtml = '<span class="text-muted">无权限信息</span>'
      }

      return `
        <div class="apk-info-grid">
          <div class="info-row">
            <span class="label">应用名称:</span>
            <span class="value highlight">${data.applicationLabel || 'N/A'}</span>
          </div>
          <div class="info-row">
            <span class="label">包名:</span>
            <span class="value code">${data.packageName || 'N/A'}</span>
          </div>
          <div class="info-group">
            <div class="info-col">
              <span class="label">版本名:</span>
              <span class="value">${data.versionName || 'N/A'}</span>
            </div>
            <div class="info-col">
              <span class="label">版本号:</span>
              <span class="value">${data.versionCode || 'N/A'}</span>
            </div>
          </div>
          <div class="info-group">
            <div class="info-col">
              <span class="label">Min SDK:</span>
              <span class="value">${data.minSdkVersion || 'N/A'}</span>
            </div>
            <div class="info-col">
              <span class="label">Target SDK:</span>
              <span class="value">${data.targetSdkVersion || 'N/A'}</span>
            </div>
          </div>
          <div class="info-row perm-row">
            <span class="label">权限 (${data.permissions?.length || 0}):</span>
            <div class="value perm-container">${permissionsHtml}</div>
          </div>
        </div>
      `
    }

    onMounted(async () => {
      console.log('PackagePage 组件已挂载')
      try {
        apkServiceRef.value = await serviceManager.getService('apk')
      } catch { }
    })
    return {
      selectedAnalysisFile,
      selectedInstallFile,
      selectedDecompileFile,
      selectedProjectDir,
      isInstalling,
      isDecompiling,
      isRecompiling,
      isAnalyzing,
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
      selectApkFile,
      selectInstallFile,
      selectDecompileFile,
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

:deep(.text-success) {
  color: var(--success-color);
}
</style>
<style scoped>
.actions-bottom-right {
  display: flex;
  justify-content: flex-end;
  padding-top: 16px;
  margin-top: auto;
}

.file-drop-zone.disabled {
  opacity: 0.6;
  cursor: not-allowed;
  pointer-events: none;
}

.section.responsive-section {
  display: flex;
  flex-direction: column;
  min-height: 200px;
  /* 给个最小高度，避免内容太少时太扁 */
}

.btn-group {
  display: flex;
  gap: 10px;
  flex-direction: row-reverse;
  /* Reverse order so primary actions are on the right */
}

/* APK Info Grid Styles - 全局生效，因为内容是 v-html 注入的 */
:deep(.apk-info-grid) {
  display: flex;
  flex-direction: column;
  gap: 8px;
  font-size: 13px;
}

:deep(.info-row) {
  display: flex;
  align-items: baseline;
  gap: 8px;
}

:deep(.info-group) {
  display: flex;
  gap: 16px;
}

:deep(.info-col) {
  display: flex;
  align-items: baseline;
  gap: 6px;
  flex: 1;
}

:deep(.label) {
  color: var(--text-secondary);
  font-weight: 500;
  white-space: nowrap;
  min-width: 60px;
}

:deep(.value) {
  color: var(--text-primary);
  word-break: break-all;
}

:deep(.value.code) {
  font-family: 'Consolas', monospace;
  color: var(--primary-color);
}

:deep(.value.highlight) {
  font-weight: 600;
  font-size: 14px;
}

:deep(.permissions-list) {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 4px;
}

:deep(.perm-tag) {
  background: var(--bg-secondary);
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 11px;
  color: var(--text-secondary);
  border: 1px solid var(--border-color);
  cursor: help;
}

:deep(.perm-tag.more) {
  background: var(--primary-bg-light);
  color: var(--primary-color);
  border-color: var(--primary-color-alpha);
}
</style>
