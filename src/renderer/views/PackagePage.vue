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
            <input ref="apkFileInput" type="file" accept=".apk" class="hidden-input"
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
              <button class="btn btn-primary" :class="{ 'loading': isAnalyzing }"
                :disabled="!selectedAnalysisFile || isAnalyzing" @click="analyzeApk">
                <span v-if="!isAnalyzing">🔍</span>
                <span v-if="isAnalyzing" class="btn-spinner"></span>
                {{ isAnalyzing ? '解析中...' : '解析 APK' }}
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
            <input ref="installFileInput" type="file" accept=".apk,.aab" class="hidden-input" :disabled="isInstalling"
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

        <!-- 签名配置 -->
        <div class="section responsive-section">
          <h2><span class="section-icon">🔑</span>签名配置</h2>
          <div class="signature-list">
             <div v-for="config in signatureConfigs" :key="config.id" class="signature-item">
                <div class="signature-info">
                   <div class="signature-name">{{ config.name }}</div>
                   <div class="signature-alias" :title="config.alias">{{ config.alias }}</div>
                </div>
                <div class="signature-actions">
                   <button class="btn btn-small" @click="openSignatureModal(config)" title="编辑">✏️</button>
                   <button class="btn btn-small error" @click="deleteSignature(config.id)" title="删除">🗑️</button>
                </div>
             </div>
             <div v-if="signatureConfigs.length === 0" class="placeholder">
                暂无签名配置
             </div>
          </div>
          <div class="actions-bottom-right">
             <button class="btn btn-primary" @click="openSignatureModal()">
                <span>➕</span>新增配置
             </button>
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
            <input ref="decompileFileInput" type="file" accept=".apk" class="hidden-input"
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
          
          <div v-if="selectedProjectDir" class="options-panel">
             <div class="option-row">
                <label class="checkbox-label">
                   <input type="checkbox" v-model="recompileOptions.sign"> 启用签名
                </label>
                <select v-if="recompileOptions.sign" v-model="recompileSignatureId" class="form-control inline-select">
                   <option value="" disabled>请选择签名配置</option>
                   <option v-for="config in signatureConfigs" :key="config.id" :value="config.id">
                      {{ config.name }}
                   </option>
                </select>
                <label v-if="recompileOptions.sign" class="checkbox-label recompile-v2-checkbox">
                   <input type="checkbox" v-model="recompileOptions.v2"> V2签名
                </label>
             </div>
             <div class="option-row">
                <label class="checkbox-label">
                   <input type="checkbox" v-model="recompileOptions.align"> ZipAlign优化
                </label>
             </div>
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

        <!-- APK 重签 -->
        <div class="section responsive-section">
          <h2><span class="section-icon">✍️</span>APK 重签</h2>
          <div class="file-drop-zone" @drop="handleDrop($event, handleResignFileSelect)" @dragover.prevent
            @dragenter.prevent @click="selectResignFile()">
            <p>拖拽 APK 文件到此处进行重签</p>
            <input type="file" accept=".apk" class="hidden-input"
              @change="handleFileInputChange($event, handleResignFileSelect)">
          </div>
          <div v-if="selectedResignFile" class="file-info">
            <p><strong>文件名:</strong> {{ selectedResignFile.name }}</p>
            <p><strong>大小:</strong> {{ formatFileSize(selectedResignFile.size) }}</p>
          </div>
          
          <div class="form-group resign-form" v-if="selectedResignFile">
             <label>选择签名:</label>
             <div class="resign-row">
               <select v-model="selectedSignatureId" class="form-control resign-select">
                  <option value="" disabled>请选择签名配置</option>
                  <option v-for="config in signatureConfigs" :key="config.id" :value="config.id">
                     {{ config.name }}
                  </option>
               </select>
               <label class="checkbox-label resign-v2-checkbox">
                  <input type="checkbox" v-model="resignOptions.v2"> V2签名
               </label>
             </div>
          </div>

          <div v-if="resignResult" class="analysis-result">
            <div v-html="resignResult"></div>
          </div>
          <div class="actions-bottom-right">
            <div class="btn-group">
              <button class="btn btn-primary" :class="{ 'loading': isResigning }"
                :disabled="!selectedResignFile || !selectedSignatureId || isResigning" @click="resignApk">
                <span v-if="!isResigning">✍️</span>
                <span v-if="isResigning" class="btn-spinner"></span>
                {{ isResigning ? '重签中...' : '开始重签' }}
              </button>
              <button class="btn btn-secondary" :disabled="!resignOutputPath" @click="openResignOutput">
                <span>📂</span>打开输出
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
  
  <!-- 签名配置弹窗 -->
  <SignatureEditModal 
    v-model:visible="showSignatureModal"
    :data="editingSignature"
    @save="handleSaveSignature"
  />
</template>

<script>
import { ref, inject, onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import serviceManager from '@services/ServiceManager'
import { useNotification } from '@composables/useNotification'
import { usePackageStore } from '@stores/packageStore'
import { useSignatureStore } from '@stores/signatureStore'
import SignatureEditModal from '@components/package/SignatureEditModal.vue'

export default {
  name: 'PackagePage',
  components: {
    SignatureEditModal
  },
  setup() {
    const packageStore = usePackageStore()
    const signatureStore = useSignatureStore()
    
    // 从 store 中获取状态
    const {
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
      resignOptions
    } = storeToRefs(packageStore)

    const { configs: signatureConfigs } = storeToRefs(signatureStore)


    // Signature & Resign State
    const selectedResignFile = ref(null)
    const selectedSignatureId = ref('')
    const recompileSignatureId = ref('')
    const isResigning = ref(false)
    const resignResult = ref(null)
    const resignOutputPath = ref(null)
    const showSignatureModal = ref(false)
    const editingSignature = ref(null)

    // Notification composable
    const { showLoading, completeLoading, failLoading } = useNotification()
    const errorServiceRef = ref(null)
    const apkServiceRef = ref(null)

    // Helper to get error service
    const getErrorService = async () => {
      if (!errorServiceRef.value) {
        errorServiceRef.value = await serviceManager.getService('error')
      }
      return errorServiceRef.value
    }
    
    // Helper to get apk service
    const getApkService = async () => {
      if (!apkServiceRef.value) {
        apkServiceRef.value = await serviceManager.getService('apk')
      }
      return apkServiceRef.value
    }
    
    // Event Handlers
    const handleDrop = (event, callback) => {
      event.preventDefault()
      if (event.dataTransfer.files && event.dataTransfer.files.length > 0) {
        const file = event.dataTransfer.files[0]
        callback(file)
      }
    }

    const handleFileInputChange = (event, callback) => {
      const file = event.target.files[0]
      if (file) {
        callback(file)
      }
      event.target.value = ''
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
            } catch (error) {
              console.error('获取文件信息错误:', error)
            }
            targetRef.value = { name, path: p, size }
          }
        }
      } catch (error) {
        const svc = await getErrorService()
        if (svc) svc.reportError(error)
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

    const handleApkFileSelect = async (file) => {
      if (file && file.name.toLowerCase().endsWith('.apk')) {
        selectedAnalysisFile.value = file
      } else {
        const svc = await getErrorService()
        if (svc) svc.reportError(new Error('请选择有效的APK文件'), { category: 'ui', severity: 'low' })
      }
    }

    const handleInstallFileSelect = async (file) => {
      const name = file.name.toLowerCase()
      if (file && (name.endsWith('.apk') || name.endsWith('.aab'))) {
        selectedInstallFile.value = file
      } else {
        const svc = await getErrorService()
        if (svc) svc.reportError(new Error('请选择有效的APK或AAB文件'), { category: 'ui', severity: 'low' })
      }
    }

    const handleDecompileFileSelect = async (file) => {
      if (file && file.name.toLowerCase().endsWith('.apk')) {
        selectedDecompileFile.value = file
      } else {
        const svc = await getErrorService()
        if (svc) svc.reportError(new Error('请选择有效的APK文件'), { category: 'ui', severity: 'low' })
      }
    }

    // APK操作方法
    // const apkServiceRef = ref(null)

    const analyzeApk = async () => {
      if (!selectedAnalysisFile.value) return
      let loadingId = null
      try {
        isAnalyzing.value = true
        loadingId = showLoading('正在解析APK...')
        const apkService = await getApkService()

        const result = await apkService.analyzeApk(selectedAnalysisFile.value.path)
        if (result.success) {
          apkAnalysisResult.value = displayApkAnalysisResult(result.data)
          if (loadingId) completeLoading(loadingId, 'APK解析完成', '')
        } else {
          if (loadingId) failLoading(loadingId, 'APK解析失败', String(result.error || ''))
        }
      } catch (error) {
        if (loadingId) failLoading(loadingId, 'APK解析失败', error.message || String(error))
        const svc = await getErrorService()
        if (svc) svc.reportError(error, { category: 'ui', severity: 'low' })
      } finally {
        isAnalyzing.value = false
      }
    }
    
    // 恢复状态检查
    const checkRunningTasks = async () => {
        // 这里可以添加逻辑来检查是否有后台任务正在运行
        // 目前主要依靠 store 中的状态保持
        const notificationService = serviceManager.getServiceSync('notification')
        if (notificationService) {
            const notifications = notificationService.getAllNotifications()
            
            // 检查是否有对应的 loading 通知
            const hasInstallLoading = notifications.some(n => n.type === 'loading' && n.title.includes('安装'))
            if (hasInstallLoading && !isInstalling.value) {
                isInstalling.value = true
            } else if (!hasInstallLoading && isInstalling.value) {
                 // 如果没有通知但状态是 installing，说明可能异常退出了或者通知没了，重置状态
                 isInstalling.value = false
            }
            
            const hasAnalyzeLoading = notifications.some(n => n.type === 'loading' && n.title.includes('解析'))
            if (hasAnalyzeLoading && !isAnalyzing.value) {
                isAnalyzing.value = true
            } else if (!hasAnalyzeLoading && isAnalyzing.value) {
                 isAnalyzing.value = false
            }
            
            const hasDecompileLoading = notifications.some(n => n.type === 'loading' && n.title.includes('反编译'))
            if (hasDecompileLoading && !isDecompiling.value) {
                isDecompiling.value = true
            } else if (!hasDecompileLoading && isDecompiling.value) {
                isDecompiling.value = false
            }

            const hasRecompileLoading = notifications.some(n => n.type === 'loading' && n.title.includes('回编译'))
            if (hasRecompileLoading && !isRecompiling.value) {
                isRecompiling.value = true
            } else if (!hasRecompileLoading && isRecompiling.value) {
                isRecompiling.value = false
            }
        }
    }

    const installApp = async () => {
      if (!selectedInstallFile.value) return
      let loadingId = null
      try {
        isInstalling.value = true
        loadingId = showLoading('正在安装应用...')

        const deviceSvc = await serviceManager.getService('device')
        console.log('installApp', selectedInstallFile.value)
        const result = await deviceSvc.installApp(selectedInstallFile.value.path)

        if (result.success) {
          if (loadingId) completeLoading(loadingId, '安装完成', '')
        } else {
          if (loadingId) failLoading(loadingId, '安装失败', String(result.error || ''))
        }
      } catch (error) {
        if (loadingId) failLoading(loadingId, '安装失败', error.message || String(error))
        const svc = await getErrorService()
        if (svc) svc.reportError(error, { category: 'device', context: 'device.install' })
      } finally {
        isInstalling.value = false
      }
    }

    const startDecompile = async () => {
      if (!selectedDecompileFile.value) return
      let loadingId = null
      try {
        isDecompiling.value = true
        if (decompileProgress && decompileProgress.value) {
          decompileProgress.value.show = true
          decompileProgress.value.value = 0
        }
        loadingId = showLoading('正在反编译APK...')

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

          if (loadingId) completeLoading(loadingId, '反编译完成', `输出目录: ${result.outputPath}`)
        } else {
          if (loadingId) failLoading(loadingId, '反编译失败', String(result.error || ''))
        }
      } catch (error) {
        if (loadingId) failLoading(loadingId, '反编译失败', String(error || ''))
        const svc = await getErrorService()
        if (svc) svc.reportError(error, { category: 'tool', context: 'apk.decompile' })
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
        const systemSvc = await serviceManager.getService('system')
        await systemSvc.openPath(decompileOutputPath.value)
      }
    }

    const selectProjectDir = async () => {
      try {
        const systemSvc = await serviceManager.getService('system')
        const result = await systemSvc.selectDirectory()
        if (result && !result.canceled) {
          selectedProjectDir.value = result.filePaths[0]
        }
      } catch (error) {
        const svc = await getErrorService()
        if (svc) svc.reportError(error, { category: 'system', context: 'system.selectDirectory' })
      }
    }

    const startRecompile = async () => {
      if (!selectedProjectDir.value) return
      
      // Check signature config if sign is enabled
      if (recompileOptions.value.sign && !recompileSignatureId.value) {
         const svc = await getErrorService()
         if (svc) svc.reportError(new Error('请选择签名配置'), { category: 'ui', severity: 'low' })
         return
      }

      let loadingId = null
      try {
        recompileProgress.show = true
        recompileProgress.value = 0
        
        loadingId = showLoading('正在回编译APK...')
        const options = {
          sign: recompileOptions.value.sign,
          align: recompileOptions.value.align,
          optimize: recompileOptions.value.optimize,
          v2: recompileOptions.value.v2
        }
        
        if (options.sign) {
             const config = signatureStore.getConfigById(recompileSignatureId.value)
             if (config) {
                 options.keystore = {
                    path: config.path,
                    alias: config.alias,
                    storepass: config.storepass,
                    keypass: config.keypass
                 }
             }
        }

        const apkService = apkServiceRef.value || await serviceManager.getService('apk')
        apkServiceRef.value = apkService
        const result = await apkService.recompileApk(selectedProjectDir.value, options)

        if (result.success) {
          recompileProgress.value = 100
          recompileOutputPath.value = result.outputPath
          recompileResult.value = `<p>回编译完成！输出文件: ${result.outputPath}</p>`
          if (loadingId) completeLoading(loadingId, '回编译完成', `输出文件: ${result.outputPath}`)
        } else {
          if (loadingId) failLoading(loadingId, '回编译失败', String(result.error || ''))
        }
      } catch (error) {
        if (loadingId) failLoading(loadingId, '回编译失败', String(error || ''))
        const svc = await getErrorService()
        if (svc) svc.reportError(error, { category: 'tool', context: 'apk.recompile' })
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

    // Resign Methods
    const selectResignFile = async () => {
      await selectFileWithStats(selectedResignFile)
    }

    const handleResignFileSelect = async (file) => {
      if (file && file.name.toLowerCase().endsWith('.apk')) {
        selectedResignFile.value = file
      } else {
        const svc = await getErrorService()
        if (svc) svc.reportError(new Error('请选择有效的APK文件'), { category: 'ui', severity: 'low' })
      }
    }

    const resignApk = async () => {
      if (!selectedResignFile.value) return
      const config = signatureStore.getConfigById(selectedSignatureId.value)
      if (!config) {
        const svc = await getErrorService()
        if (svc) svc.reportError(new Error('请选择签名配置'), { category: 'ui', severity: 'low' })
        return
      }

      let loadingId = null
      try {
        isResigning.value = true
        loadingId = showLoading('正在重签APK...')
        
        const apkService = apkServiceRef.value || await serviceManager.getService('apk')
        apkServiceRef.value = apkService
        
        const keystore = {
            path: config.path,
            alias: config.alias,
            storepass: config.storepass,
            keypass: config.keypass
        }

        const options = {
            v2: resignOptions.value.v2
        }

        const result = await apkService.signApk(selectedResignFile.value.path, keystore, options)

        if (result.success) {
          // 更新输出路径为实际生成的路径
          resignOutputPath.value = result.outputPath
          resignResult.value = `<p>重签完成！输出文件: ${result.outputPath}</p>`
          if (loadingId) completeLoading(loadingId, '重签完成', `输出文件: ${result.outputPath}`)
        } else {
          if (loadingId) failLoading(loadingId, '重签失败', String(result.error || ''))
        }
      } catch (error) {
        if (loadingId) failLoading(loadingId, '重签失败', String(error || ''))
        const svc = await getErrorService()
        if (svc) svc.reportError(error, { category: 'tool', context: 'apk.resign' })
      } finally {
        isResigning.value = false
      }
    }

    const openResignOutput = async () => {
      if (resignOutputPath.value) {
        const svc = await serviceManager.getService('system')
        await svc.openPath(resignOutputPath.value)
      }
    }

    // Signature Config Methods
    const openSignatureModal = (config = null) => {
      editingSignature.value = config ? { ...config } : null
      showSignatureModal.value = true
    }

    const handleSaveSignature = async (formData) => {
        if (formData.id) {
            await signatureStore.updateConfig({ ...formData })
        } else {
            await signatureStore.addConfig({ ...formData })
        }
        
        // Auto select if it's the first one
        if (signatureConfigs.value.length === 1) {
            selectedSignatureId.value = signatureConfigs.value[0].id
            recompileSignatureId.value = signatureConfigs.value[0].id
        }
    }

    const deleteSignature = async (id) => {
        if (confirm('确定要删除该配置吗？')) {
            await signatureStore.removeConfig(id)
            if (selectedSignatureId.value === id) {
                selectedSignatureId.value = signatureConfigs.value.length > 0 ? signatureConfigs.value[0].id : ''
            }
             if (recompileSignatureId.value === id) {
                recompileSignatureId.value = signatureConfigs.value.length > 0 ? signatureConfigs.value[0].id : ''
            }
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
      
      await signatureStore.loadConfigs()
      if (signatureConfigs.value.length > 0) {
        selectedSignatureId.value = signatureConfigs.value[0].id
        recompileSignatureId.value = signatureConfigs.value[0].id
      }
      
      // 检查并同步状态
      checkRunningTasks()
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
      resignOptions,
      signatureConfigs,
      selectedResignFile,
      selectedSignatureId,
      recompileSignatureId,
      isResigning,
      resignResult,
      resignOutputPath,
      showSignatureModal,
      editingSignature,
      handleDrop,
      handleFileInputChange,
      handleApkFileSelect,
      handleInstallFileSelect,
      selectApkFile,
      selectInstallFile,
      selectDecompileFile,
      handleDecompileFileSelect,
      analyzeApk,
      installApp,
      startDecompile,
      openDecompileOutput,
      selectProjectDir,
      startRecompile,
      openRecompileOutput,
      selectResignFile,
      handleResignFileSelect,
      resignApk,
      openResignOutput,
      openSignatureModal,
      handleSaveSignature,
      deleteSignature,
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

.signature-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 200px;
  overflow-y: auto;
  border: 1px solid var(--border-color);
  border-radius: 6px;
  padding: 8px;
  background: var(--bg-secondary);
}

.signature-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px;
  background: var(--card-bg);
  border: 1px solid var(--border-color);
  border-radius: 4px;
}

.signature-info {
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.signature-name {
  font-weight: 600;
  color: var(--text-primary);
}

.signature-alias {
  font-size: 12px;
  color: var(--text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.signature-actions {
  display: flex;
  gap: 4px;
}

.options-panel {
  margin-top: 10px;
  padding: 10px;
  background: var(--bg-secondary);
  border-radius: 4px;
}

.option-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 5px;
}

.option-row:last-child {
  margin-bottom: 0;
}

.checkbox-label {
  display: flex;
  align-items: center;
  gap: 5px;
  cursor: pointer;
  user-select: none;
}

.inline-select {
  width: auto;
  padding: 4px 8px;
  font-size: 13px;
}

.hidden-input {
  display: none;
}

.resign-form {
  margin-top: var(--space-md);
}

.resign-row {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
}

.resign-select {
  flex: 1;
}

.resign-v2-checkbox {
  white-space: nowrap;
}

.recompile-v2-checkbox {
  margin-left: var(--space-sm);
}
</style>
