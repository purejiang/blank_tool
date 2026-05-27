<template>
  <div class="package-page">
    <div class="page-header">
      <div>
        <h1 class="page-title">Package Manager</h1>
        <p class="page-subtitle">Analyze, install, decompile, recompile, and resign APK/AAB packages</p>
      </div>
    </div>

    <n-grid :cols="1" :x-gap="16" responsive="screen" item-responsive>
      <!-- Left Column -->
      <n-grid-item span="1 800:1">
        <!-- APK Analysis -->
        <n-card title="APK Analysis" :bordered="false" size="small" class="pkg-card">
          <div class="drop-zone" @drop="handleDrop($event, handleApkFileSelect)" @dragover.prevent
            @dragenter.prevent @click="!isAnalyzing && selectApkFile()">
            <n-icon size="32" color="#475569"><Package /></n-icon>
            <p>Drop APK file here or click to browse</p>
            <input ref="apkFileInput" type="file" accept=".apk" class="hidden-input"
              @change="handleFileInputChange($event, handleApkFileSelect)">
          </div>
          <div v-if="selectedAnalysisFile" class="file-info">
            <n-tag type="info" size="small">{{ selectedAnalysisFile.name }}</n-tag>
            <span class="file-size">{{ formatFileSize(selectedAnalysisFile.size) }}</span>
          </div>
          <div v-if="apkAnalysisResult" class="analysis-result" v-html="apkAnalysisResult" />
          <template #action>
            <n-button type="primary" size="small" :loading="isAnalyzing"
              :disabled="!selectedAnalysisFile || isAnalyzing" @click="analyzeApk">
              <template #icon><n-icon><Search /></n-icon></template>
              Analyze
            </n-button>
          </template>
        </n-card>

        <!-- Install -->
        <n-card title="Install" :bordered="false" size="small" class="pkg-card">
          <div class="drop-zone" :class="{ disabled: isInstalling }"
            @drop="!isInstalling && handleDrop($event, handleInstallFileSelect)" @dragover.prevent @dragenter.prevent
            @click="!isInstalling && selectInstallFile()">
            <n-icon size="32" color="#475569"><Download /></n-icon>
            <p>Drop APK/AAB file to install</p>
            <input ref="installFileInput" type="file" accept=".apk,.aab" class="hidden-input"
              @change="handleFileInputChange($event, handleInstallFileSelect)">
          </div>
          <div v-if="selectedInstallFile" class="file-info">
            <n-tag type="info" size="small">{{ selectedInstallFile.name }}</n-tag>
            <span class="file-size">{{ formatFileSize(selectedInstallFile.size) }}</span>
          </div>
          <template #action>
            <n-button type="success" size="small" :loading="isInstalling"
              :disabled="!selectedInstallFile || isInstalling" @click="installApp">
              <template #icon><n-icon><Download /></n-icon></template>
              Install
            </n-button>
          </template>
        </n-card>

        <!-- Signature Configs -->
        <n-card title="Signatures" :bordered="false" size="small" class="pkg-card">
          <template #header-extra>
            <n-button size="tiny" @click="openSignatureModal()">
              <template #icon><n-icon><Plus /></n-icon></template>
              Add
            </n-button>
          </template>
          <n-list v-if="signatureConfigs.length > 0" hoverable>
            <n-list-item v-for="config in signatureConfigs" :key="config.id">
              <n-thing :title="config.name" :description="config.alias">
                <template #action>
                  <n-space>
                    <n-button size="tiny" quaternary @click="openSignatureModal(config)">
                      <template #icon><n-icon><Edit /></n-icon></template>
                    </n-button>
                    <n-button size="tiny" quaternary type="error" @click="deleteSignature(config.id)">
                      <template #icon><n-icon><Trash2 /></n-icon></template>
                    </n-button>
                  </n-space>
                </template>
              </n-thing>
            </n-list-item>
          </n-list>
          <div v-else class="empty-state">No signature configurations</div>
        </n-card>
      </n-grid-item>

      <!-- Right Column -->
      <n-grid-item span="1 800:1">
        <!-- Decompile -->
        <n-card title="Decompile" :bordered="false" size="small" class="pkg-card">
          <div class="drop-zone" @drop="handleDrop($event, handleDecompileFileSelect)" @dragover.prevent
            @dragenter.prevent @click="selectDecompileFile()">
            <n-icon size="32" color="#475569"><Unlock /></n-icon>
            <p>Drop APK file to decompile</p>
            <input ref="decompileFileInput" type="file" accept=".apk" class="hidden-input"
              @change="handleFileInputChange($event, handleDecompileFileSelect)">
          </div>
          <div v-if="selectedDecompileFile" class="file-info">
            <n-tag type="info" size="small">{{ selectedDecompileFile.name }}</n-tag>
            <span class="file-size">{{ formatFileSize(selectedDecompileFile.size) }}</span>
          </div>
          <div v-if="decompileResult" class="analysis-result" v-html="decompileResult" />
          <template #action>
            <n-space>
              <n-button type="primary" size="small" :loading="isDecompiling"
                :disabled="!selectedDecompileFile || isDecompiling" @click="startDecompile">
                <template #icon><n-icon><Unlock /></n-icon></template>
                Decompile
              </n-button>
              <n-button size="small" :disabled="!decompileOutputPath" @click="openDecompileOutput">
                <template #icon><n-icon><FolderOpen /></n-icon></template>
                Open
              </n-button>
            </n-space>
          </template>
        </n-card>

        <!-- Recompile -->
        <n-card title="Recompile" :bordered="false" size="small" class="pkg-card">
          <div class="drop-zone">
            <n-icon size="32" color="#475569"><Lock /></n-icon>
            <p>Select decompiled project directory to recompile</p>
            <n-button size="small" quaternary @click="selectProjectDir">
              <template #icon><n-icon><FolderOpen /></n-icon></template>
              Select Directory
            </n-button>
          </div>
          <div v-if="selectedProjectDir" class="file-info">
            <n-tag type="info" size="small">{{ selectedProjectDir }}</n-tag>
          </div>
          <div v-if="selectedProjectDir" class="options-panel">
            <n-space align="center">
              <n-checkbox v-model:checked="recompileOptions.sign">Sign</n-checkbox>
              <n-select v-if="recompileOptions.sign" v-model:value="recompileSignatureId"
                :options="signatureConfigs.map(c => ({ label: c.name, value: c.id }))"
                placeholder="Select signature" style="width: 160px" size="tiny" />
              <n-checkbox v-if="recompileOptions.sign" v-model:checked="recompileOptions.v2">V2 Sign</n-checkbox>
              <n-checkbox v-model:checked="recompileOptions.align">ZipAlign</n-checkbox>
            </n-space>
          </div>
          <div v-if="recompileProgress && recompileProgress.show" style="margin-top: 12px">
            <n-progress type="line" :percentage="recompileProgress.value" color="#22C55E" />
          </div>
          <template #action>
            <n-space>
              <n-button type="primary" size="small" :disabled="!selectedProjectDir" @click="startRecompile">
                <template #icon><n-icon><Lock /></n-icon></template>
                Recompile
              </n-button>
              <n-button size="small" :disabled="!recompileOutputPath" @click="openRecompileOutput">
                <template #icon><n-icon><FolderOpen /></n-icon></template>
                Open
              </n-button>
            </n-space>
          </template>
        </n-card>

        <!-- Resign -->
        <n-card title="Resign" :bordered="false" size="small" class="pkg-card">
          <div class="drop-zone" @drop="handleDrop($event, handleResignFileSelect)" @dragover.prevent
            @dragenter.prevent @click="selectResignFile()">
            <n-icon size="32" color="#475569"><PenTool /></n-icon>
            <p>Drop APK file to resign</p>
            <input type="file" accept=".apk" class="hidden-input"
              @change="handleFileInputChange($event, handleResignFileSelect)">
          </div>
          <div v-if="selectedResignFile" class="file-info">
            <n-tag type="info" size="small">{{ selectedResignFile.name }}</n-tag>
            <span class="file-size">{{ formatFileSize(selectedResignFile.size) }}</span>
          </div>
          <div class="options-panel" v-if="selectedResignFile">
            <n-space align="center">
              <n-select v-model:value="selectedSignatureId"
                :options="signatureConfigs.map(c => ({ label: c.name, value: c.id }))"
                placeholder="Select signature" style="width: 200px" size="small" />
              <n-checkbox v-model:checked="resignOptions.v2">V2 Sign</n-checkbox>
            </n-space>
          </div>
          <div v-if="resignResult" class="analysis-result" v-html="resignResult" />
          <template #action>
            <n-space>
              <n-button type="primary" size="small" :loading="isResigning"
                :disabled="!selectedResignFile || !selectedSignatureId || isResigning" @click="resignApk">
                <template #icon><n-icon><PenTool /></n-icon></template>
                Resign
              </n-button>
              <n-button size="small" :disabled="!resignOutputPath" @click="openResignOutput">
                <template #icon><n-icon><FolderOpen /></n-icon></template>
                Open
              </n-button>
            </n-space>
          </template>
        </n-card>
      </n-grid-item>
    </n-grid>

    <!-- Signature Edit Modal -->
    <SignatureEditModal
      v-model:visible="showSignatureModal"
      :data="editingSignature"
      @save="handleSaveSignature"
    />
  </div>
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
  components: { SignatureEditModal },
  setup() {
    const packageStore = usePackageStore()
    const signatureStore = useSignatureStore()

    const {
      selectedAnalysisFile, selectedInstallFile, selectedDecompileFile,
      selectedProjectDir, isInstalling, isDecompiling, isRecompiling,
      isAnalyzing, apkAnalysisResult, decompileResult, recompileResult,
      decompileOutputPath, recompileOutputPath, installProgress,
      decompileProgress, recompileProgress, decompileOptions,
      recompileOptions, resignOptions
    } = storeToRefs(packageStore)

    const { configs: signatureConfigs } = storeToRefs(signatureStore)

    const selectedResignFile = ref(null)
    const selectedSignatureId = ref('')
    const recompileSignatureId = ref('')
    const isResigning = ref(false)
    const resignResult = ref(null)
    const resignOutputPath = ref(null)
    const showSignatureModal = ref(false)
    const editingSignature = ref(null)

    const { showLoading, completeLoading, failLoading } = useNotification()
    const errorServiceRef = ref(null)
    const apkServiceRef = ref(null)

    const getErrorService = async () => {
      if (!errorServiceRef.value) errorServiceRef.value = await serviceManager.getService('error')
      return errorServiceRef.value
    }

    const getApkService = async () => {
      if (!apkServiceRef.value) apkServiceRef.value = await serviceManager.getService('apk')
      return apkServiceRef.value
    }

    const handleDrop = (event, callback) => {
      event.preventDefault()
      if (event.dataTransfer.files && event.dataTransfer.files.length > 0) {
        callback(event.dataTransfer.files[0])
      }
    }

    const handleFileInputChange = (event, callback) => {
      const file = event.target.files[0]
      if (file) callback(file)
      event.target.value = ''
    }

    const selectFileWithStats = async (targetRef, extensions = ['apk']) => {
      try {
        const systemSvc = await serviceManager.getService('system')
        const res = await systemSvc.selectFile({
          title: 'Select file',
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
            } catch (error) { console.error('File stats error:', error) }
            targetRef.value = { name, path: p, size }
          }
        }
      } catch (error) {
        const svc = await getErrorService()
        if (svc) svc.reportError(error)
      }
    }

    const selectApkFile = () => selectFileWithStats(selectedAnalysisFile)
    const selectInstallFile = () => selectFileWithStats(selectedInstallFile, ['apk', 'aab'])
    const selectDecompileFile = () => selectFileWithStats(selectedDecompileFile)
    const selectResignFile = () => selectFileWithStats(selectedResignFile)

    const handleApkFileSelect = async (file) => {
      if (file && file.name.toLowerCase().endsWith('.apk')) selectedAnalysisFile.value = file
      else { const svc = await getErrorService(); if (svc) svc.reportError(new Error('Please select a valid APK file'), { category: 'ui', severity: 'low' }) }
    }

    const handleInstallFileSelect = async (file) => {
      const name = file.name.toLowerCase()
      if (file && (name.endsWith('.apk') || name.endsWith('.aab'))) selectedInstallFile.value = file
      else { const svc = await getErrorService(); if (svc) svc.reportError(new Error('Please select a valid APK or AAB file'), { category: 'ui', severity: 'low' }) }
    }

    const handleDecompileFileSelect = async (file) => {
      if (file && file.name.toLowerCase().endsWith('.apk')) selectedDecompileFile.value = file
      else { const svc = await getErrorService(); if (svc) svc.reportError(new Error('Please select a valid APK file'), { category: 'ui', severity: 'low' }) }
    }

    const handleResignFileSelect = async (file) => {
      if (file && file.name.toLowerCase().endsWith('.apk')) selectedResignFile.value = file
      else { const svc = await getErrorService(); if (svc) svc.reportError(new Error('Please select a valid APK file'), { category: 'ui', severity: 'low' }) }
    }

    const analyzeApk = async () => {
      if (!selectedAnalysisFile.value) return
      let loadingId = null
      try {
        isAnalyzing.value = true
        loadingId = showLoading('Analyzing APK...')
        const apkService = await getApkService()
        const result = await apkService.analyzeApk(selectedAnalysisFile.value.path)
        if (result.success) {
          apkAnalysisResult.value = displayApkAnalysisResult(result.data)
          if (loadingId) completeLoading(loadingId, 'Analysis complete', '')
        } else {
          if (loadingId) failLoading(loadingId, 'Analysis failed', String(result.error || ''))
        }
      } catch (error) {
        if (loadingId) failLoading(loadingId, 'Analysis failed', error.message || String(error))
        const svc = await getErrorService(); if (svc) svc.reportError(error, { category: 'ui', severity: 'low' })
      } finally { isAnalyzing.value = false }
    }

    const installApp = async () => {
      if (!selectedInstallFile.value) return
      let loadingId = null
      try {
        isInstalling.value = true
        loadingId = showLoading('Installing...')
        const deviceSvc = await serviceManager.getService('device')
        const result = await deviceSvc.installApp(selectedInstallFile.value.path)
        if (result.success) {
          if (loadingId) completeLoading(loadingId, 'Install complete', '')
        } else {
          if (loadingId) failLoading(loadingId, 'Install failed', String(result.error || ''))
        }
      } catch (error) {
        if (loadingId) failLoading(loadingId, 'Install failed', error.message || String(error))
        const svc = await getErrorService(); if (svc) svc.reportError(error, { category: 'device', context: 'device.install' })
      } finally { isInstalling.value = false }
    }

    const startDecompile = async () => {
      if (!selectedDecompileFile.value) return
      let loadingId = null
      try {
        isDecompiling.value = true
        if (decompileProgress && decompileProgress.value) {
          decompileProgress.value.show = true; decompileProgress.value.value = 0
        }
        loadingId = showLoading('Decompiling APK...')
        const options = {
          resources: decompileOptions.value.resources,
          sources: decompileOptions.value.sources,
          manifest: decompileOptions.value.manifest
        }
        const apkService = await getApkService()
        const result = await apkService.decompileApk(selectedDecompileFile.value.path, options)
        if (result.success) {
          if (decompileProgress?.value) decompileProgress.value.value = 100
          decompileOutputPath.value = result.outputPath
          decompileResult.value = `<div class="apk-info-grid"><div class="info-row"><span class="label">Status:</span><span class="value highlight text-success">Success</span></div><div class="info-row"><span class="label">Output:</span><span class="value code">${result.outputPath}</span></div></div>`
          if (loadingId) completeLoading(loadingId, 'Decompile complete', `Output: ${result.outputPath}`)
        } else {
          if (loadingId) failLoading(loadingId, 'Decompile failed', String(result.error || ''))
        }
      } catch (error) {
        if (loadingId) failLoading(loadingId, 'Decompile failed', String(error || ''))
        const svc = await getErrorService(); if (svc) svc.reportError(error, { category: 'tool', context: 'apk.decompile' })
      } finally {
        isDecompiling.value = false
        setTimeout(() => { if (decompileProgress?.value) { decompileProgress.value.show = false; decompileProgress.value.value = 0 } }, 2000)
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
        if (result && !result.canceled) selectedProjectDir.value = result.filePaths[0]
      } catch (error) {
        const svc = await getErrorService(); if (svc) svc.reportError(error, { category: 'system', context: 'system.selectDirectory' })
      }
    }

    const startRecompile = async () => {
      if (!selectedProjectDir.value) return
      if (recompileOptions.value.sign && !recompileSignatureId.value) {
        const svc = await getErrorService(); if (svc) svc.reportError(new Error('Please select a signature config'), { category: 'ui', severity: 'low' })
        return
      }
      let loadingId = null
      try {
        recompileProgress.show = true; recompileProgress.value = 0
        loadingId = showLoading('Recompiling APK...')
        const options = { sign: recompileOptions.value.sign, align: recompileOptions.value.align, optimize: recompileOptions.value.optimize, v2: recompileOptions.value.v2 }
        if (options.sign) {
          const config = signatureStore.getConfigById(recompileSignatureId.value)
          if (config) options.keystore = { path: config.path, alias: config.alias, storepass: config.storepass, keypass: config.keypass }
        }
        const apkService = await getApkService()
        const result = await apkService.recompileApk(selectedProjectDir.value, options)
        if (result.success) {
          recompileProgress.value = 100; recompileOutputPath.value = result.outputPath
          recompileResult.value = `<p>Recompile complete! Output: ${result.outputPath}</p>`
          if (loadingId) completeLoading(loadingId, 'Recompile complete', `Output: ${result.outputPath}`)
        } else {
          if (loadingId) failLoading(loadingId, 'Recompile failed', String(result.error || ''))
        }
      } catch (error) {
        if (loadingId) failLoading(loadingId, 'Recompile failed', String(error || ''))
        const svc = await getErrorService(); if (svc) svc.reportError(error, { category: 'tool', context: 'apk.recompile' })
      } finally {
        setTimeout(() => { recompileProgress.show = false; recompileProgress.value = 0 }, 2000)
      }
    }

    const openRecompileOutput = async () => {
      if (recompileOutputPath.value) {
        const svc = await serviceManager.getService('system')
        await svc.openPath(recompileOutputPath.value)
      }
    }

    const resignApk = async () => {
      if (!selectedResignFile.value) return
      const config = signatureStore.getConfigById(selectedSignatureId.value)
      if (!config) {
        const svc = await getErrorService(); if (svc) svc.reportError(new Error('Please select a signature config'), { category: 'ui', severity: 'low' })
        return
      }
      let loadingId = null
      try {
        isResigning.value = true
        loadingId = showLoading('Resigning APK...')
        const apkService = await getApkService()
        const keystore = { path: config.path, alias: config.alias, storepass: config.storepass, keypass: config.keypass }
        const options = { v2: resignOptions.value.v2 }
        const result = await apkService.signApk(selectedResignFile.value.path, keystore, options)
        if (result.success) {
          resignOutputPath.value = result.outputPath
          resignResult.value = `<p>Resign complete! Output: ${result.outputPath}</p>`
          if (loadingId) completeLoading(loadingId, 'Resign complete', `Output: ${result.outputPath}`)
        } else {
          if (loadingId) failLoading(loadingId, 'Resign failed', String(result.error || ''))
        }
      } catch (error) {
        if (loadingId) failLoading(loadingId, 'Resign failed', String(error || ''))
        const svc = await getErrorService(); if (svc) svc.reportError(error, { category: 'tool', context: 'apk.resign' })
      } finally { isResigning.value = false }
    }

    const openResignOutput = async () => {
      if (resignOutputPath.value) {
        const svc = await serviceManager.getService('system')
        await svc.openPath(resignOutputPath.value)
      }
    }

    const openSignatureModal = (config = null) => {
      editingSignature.value = config ? { ...config } : null
      showSignatureModal.value = true
    }

    const handleSaveSignature = async (formData) => {
      if (formData.id) await signatureStore.updateConfig({ ...formData })
      else await signatureStore.addConfig({ ...formData })
      if (signatureConfigs.value.length === 1) {
        selectedSignatureId.value = signatureConfigs.value[0].id
        recompileSignatureId.value = signatureConfigs.value[0].id
      }
    }

    const deleteSignature = async (id) => {
      if (confirm('Delete this signature config?')) {
        await signatureStore.removeConfig(id)
        if (selectedSignatureId.value === id) selectedSignatureId.value = signatureConfigs.value.length > 0 ? signatureConfigs.value[0].id : ''
        if (recompileSignatureId.value === id) recompileSignatureId.value = signatureConfigs.value.length > 0 ? signatureConfigs.value[0].id : ''
      }
    }

    const formatFileSize = (bytes) => {
      if (bytes === 0) return '0 Bytes'
      const k = 1024
      const sizes = ['Bytes', 'KB', 'MB', 'GB']
      const i = Math.floor(Math.log(bytes) / Math.log(k))
      return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
    }

    const displayApkAnalysisResult = (data) => {
      if (!data) return ''
      let permissionsHtml = ''
      if (data.permissions && data.permissions.length > 0) {
        const visiblePerms = data.permissions.slice(0, 5)
        const hiddenPerms = data.permissions.slice(5)
        permissionsHtml = '<div class="permissions-list">'
        visiblePerms.forEach(p => {
          const name = p.name || p
          permissionsHtml += `<div class="perm-tag">${name.split('.').pop()}</div>`
        })
        if (hiddenPerms.length > 0) permissionsHtml += `<div class="perm-tag more">+${hiddenPerms.length}</div>`
        permissionsHtml += '</div>'
      }
      return `<div class="apk-info-grid">
        <div class="info-row"><span class="label">App Name:</span><span class="value highlight">${data.applicationLabel || 'N/A'}</span></div>
        <div class="info-row"><span class="label">Package:</span><span class="value code">${data.packageName || 'N/A'}</span></div>
        <div class="info-group"><div class="info-col"><span class="label">Version:</span><span class="value">${data.versionName || 'N/A'}</span></div><div class="info-col"><span class="label">Code:</span><span class="value">${data.versionCode || 'N/A'}</span></div></div>
        <div class="info-group"><div class="info-col"><span class="label">Min SDK:</span><span class="value">${data.minSdkVersion || 'N/A'}</span></div><div class="info-col"><span class="label">Target SDK:</span><span class="value">${data.targetSdkVersion || 'N/A'}</span></div></div>
        <div class="info-row"><span class="label">Permissions:</span><span class="value">${permissionsHtml || 'None'}</span></div>
      </div>`
    }

    onMounted(async () => {
      try { apkServiceRef.value = await serviceManager.getService('apk') } catch { }
      await signatureStore.loadConfigs()
      if (signatureConfigs.value.length > 0) {
        selectedSignatureId.value = signatureConfigs.value[0].id
        recompileSignatureId.value = signatureConfigs.value[0].id
      }
    })

    return {
      selectedAnalysisFile, selectedInstallFile, selectedDecompileFile, selectedProjectDir,
      isInstalling, isDecompiling, isRecompiling, isAnalyzing, apkAnalysisResult,
      decompileResult, recompileResult, decompileOutputPath, recompileOutputPath,
      installProgress, decompileProgress, recompileProgress, decompileOptions,
      recompileOptions, resignOptions, signatureConfigs,
      selectedResignFile, selectedSignatureId, recompileSignatureId,
      isResigning, resignResult, resignOutputPath,
      showSignatureModal, editingSignature,
      handleDrop, handleFileInputChange, handleApkFileSelect, handleInstallFileSelect,
      selectApkFile, selectInstallFile, selectDecompileFile, handleDecompileFileSelect,
      analyzeApk, installApp, startDecompile, openDecompileOutput,
      selectProjectDir, startRecompile, openRecompileOutput,
      selectResignFile, handleResignFileSelect, resignApk, openResignOutput,
      openSignatureModal, handleSaveSignature, deleteSignature, formatFileSize
    }
  }
}
</script>

<style scoped>
.package-page {
  max-width: 1200px;
  margin: 0 auto;
}
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 20px;
}
.page-title {
  font-family: Inter, sans-serif;
  font-size: 22px;
  font-weight: 700;
  color: #F8FAFC;
  margin: 0;
  letter-spacing: -0.02em;
}
.page-subtitle {
  font-size: 13px;
  color: #94A3B8;
  margin: 4px 0 0;
}
.pkg-card {
  background: #1E293B;
  border-radius: 10px;
  margin-bottom: 16px;
}
.drop-zone {
  border: 2px dashed #334155;
  border-radius: 10px;
  padding: 24px;
  text-align: center;
  cursor: pointer;
  transition: all 0.2s;
  color: #64748B;
  font-size: 14px;
}
.drop-zone:hover {
  border-color: #22C55E;
  background: rgba(34,197,94,0.04);
}
.drop-zone.disabled {
  opacity: 0.5;
  cursor: not-allowed;
  pointer-events: none;
}
.file-info {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
}
.file-size {
  font-size: 12px;
  color: #94A3B8;
}
.analysis-result {
  margin-top: 12px;
  padding: 12px;
  background: #0C1322;
  border-radius: 8px;
  font-size: 13px;
}
.options-panel {
  margin-top: 12px;
  padding: 12px;
  background: #0C1322;
  border-radius: 8px;
}
.empty-state {
  padding: 24px;
  text-align: center;
  color: #64748B;
  font-size: 14px;
}
.hidden-input { display: none; }
:deep(.text-success) { color: #22C55E; }
:deep(.apk-info-grid) { display: flex; flex-direction: column; gap: 8px; }
:deep(.info-row) { display: flex; align-items: baseline; gap: 8px; }
:deep(.info-group) { display: flex; gap: 16px; }
:deep(.info-col) { display: flex; align-items: baseline; gap: 6px; flex: 1; }
:deep(.label) { color: #94A3B8; font-weight: 500; min-width: 80px; }
:deep(.value) { color: #E2E8F0; word-break: break-all; }
:deep(.value.code) { font-family: 'Fira Code', monospace; color: #3B82F6; }
:deep(.value.highlight) { font-weight: 600; font-size: 14px; }
:deep(.permissions-list) { display: flex; flex-wrap: wrap; gap: 4px; }
:deep(.perm-tag) { background: #1E293B; padding: 2px 8px; border-radius: 4px; font-size: 11px; color: #94A3B8; border: 1px solid #334155; }
:deep(.perm-tag.more) { background: rgba(34,197,94,0.12); color: #22C55E; border-color: rgba(34,197,94,0.3); }
</style>
