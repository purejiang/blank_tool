<template>
  <div class="package-page">
    <div class="page-header">
      <div>
        <h1 class="page-title">{{ t('package.title') }}</h1>
        <p class="page-subtitle">{{ t('package.subtitle') }}</p>
      </div>
    </div>

    <n-tabs type="line" animated :default-value="'analyze'" class="pkg-tabs">
      <!-- Tab 1: Analyze & Install -->
      <n-tab-pane name="analyze" :tab="t('package.analysisInstall')">
        <n-grid :cols="2" :x-gap="16" responsive="screen">
          <!-- APK Analysis -->
          <n-grid-item span="1 800:1">
            <n-card :bordered="false" size="small" class="pkg-card">
              <div class="card-header-row">
                  <n-icon size="18" color="#3B82F6"><Search /></n-icon>
                  <span class="card-title">{{ t('package.apkAnalysis') }}</span>
                </div>
              <div class="drop-zone" @drop="handleDrop($event, handleApkFileSelect)" @dragover.prevent
                @dragenter.prevent @click="!isAnalyzing && selectApkFile()">
                <n-icon size="28" color="#475569"><Package /></n-icon>
                <p class="drop-text">{{ t('package.dropApkHere') }}</p>
                <input ref="apkFileInput" type="file" accept=".apk" class="hidden-input"
                  @change="handleFileInputChange($event, handleApkFileSelect)">
              </div>
              <div v-if="selectedAnalysisFile" class="file-info-row">
                <n-icon size="14" color="#64748B"><File /></n-icon>
                <span class="file-name">{{ selectedAnalysisFile.name }}</span>
                <span class="file-size">{{ formatFileSize(selectedAnalysisFile.size) }}</span>
              </div>
              <div v-if="apkAnalysisResult" class="analysis-result" v-html="apkAnalysisResult" />
              <div class="card-actions">
                <n-button type="primary" size="small" :loading="isAnalyzing"
                  :disabled="!selectedAnalysisFile || isAnalyzing" @click="analyzeApk" block>
                  <template #icon><n-icon><Search /></n-icon></template>
                  {{ t('package.analyze') }}
                </n-button>
              </div>
            </n-card>
          </n-grid-item>

          <!-- Install -->
          <n-grid-item span="1 800:1">
            <n-card :bordered="false" size="small" class="pkg-card">
              <div class="card-header-row">
                  <n-icon size="18" color="#22C55E"><Download /></n-icon>
                  <span class="card-title">{{ t('package.install') }}</span>
                </div>
              <div class="drop-zone" :class="{ disabled: isInstalling }"
                @drop="!isInstalling && handleDrop($event, handleInstallFileSelect)" @dragover.prevent @dragenter.prevent
                @click="!isInstalling && selectInstallFile()">
                <n-icon size="28" color="#475569"><Download /></n-icon>
                <p class="drop-text">{{ t('package.dropToInstall') }}</p>
                <input ref="installFileInput" type="file" accept=".apk,.aab" class="hidden-input"
                  @change="handleFileInputChange($event, handleInstallFileSelect)">
              </div>
              <div v-if="selectedInstallFile" class="file-info-row">
                <n-icon size="14" color="#64748B"><File /></n-icon>
                <span class="file-name">{{ selectedInstallFile.name }}</span>
                <span class="file-size">{{ formatFileSize(selectedInstallFile.size) }}</span>
              </div>
              <div class="card-actions">
                <n-button type="success" size="small" :loading="isInstalling"
                  :disabled="!selectedInstallFile || isInstalling" @click="installApp" block>
                  <template #icon><n-icon><Download /></n-icon></template>
                  {{ t('package.install') }}
                </n-button>
              </div>
            </n-card>
          </n-grid-item>
        </n-grid>
      </n-tab-pane>

      <!-- Tab 2: Decompile & Recompile -->
      <n-tab-pane name="decompile" :tab="t('package.decompileRecompile')">
        <n-grid :cols="2" :x-gap="16" responsive="screen">
          <!-- Decompile -->
          <n-grid-item span="1 800:1">
            <n-card :bordered="false" size="small" class="pkg-card">
              <div class="card-header-row">
                  <n-icon size="18" color="#8B5CF6"><Unlock /></n-icon>
                  <span class="card-title">{{ t('package.decompile') }}</span>
                </div>
              <div class="drop-zone" @drop="handleDrop($event, handleDecompileFileSelect)" @dragover.prevent
                @dragenter.prevent @click="selectDecompileFile()">
                <n-icon size="28" color="#475569"><Unlock /></n-icon>
                <p class="drop-text">{{ t('package.dropToDecompile') }}</p>
                <input ref="decompileFileInput" type="file" accept=".apk" class="hidden-input"
                  @change="handleFileInputChange($event, handleDecompileFileSelect)">
              </div>
              <div v-if="selectedDecompileFile" class="file-info-row">
                <n-icon size="14" color="#64748B"><File /></n-icon>
                <span class="file-name">{{ selectedDecompileFile.name }}</span>
                <span class="file-size">{{ formatFileSize(selectedDecompileFile.size) }}</span>
              </div>
              <div v-if="decompileResult" class="analysis-result" v-html="decompileResult" />
              <div class="card-actions">
                <n-button type="primary" size="small" :loading="isDecompiling"
                  :disabled="!selectedDecompileFile || isDecompiling" @click="startDecompile" block>
                  <template #icon><n-icon><Unlock /></n-icon></template>
                  {{ t('package.decompile') }}
                </n-button>
                <n-button v-if="decompileOutputPath" size="small" @click="openDecompileOutput">
                  <template #icon><n-icon><FolderOpen /></n-icon></template>
                  {{ t('package.open') }}
                </n-button>
              </div>
            </n-card>
          </n-grid-item>

          <!-- Recompile -->
          <n-grid-item span="1 800:1">
            <n-card :bordered="false" size="small" class="pkg-card">
              <div class="card-header-row">
                  <n-icon size="18" color="#EF4444"><Lock /></n-icon>
                  <span class="card-title">{{ t('package.recompile') }}</span>
                </div>
              <div class="drop-zone" @click="selectProjectDir">
                <n-icon size="28" color="#475569"><Lock /></n-icon>
                <p class="drop-text">{{ t('package.selectProjectDir') }}</p>
                <n-button size="small" quaternary @click.stop="selectProjectDir">
                  <template #icon><n-icon><FolderOpen /></n-icon></template>
                  {{ t('package.browse') }}
                </n-button>
              </div>
              <div v-if="selectedProjectDir" class="file-info-row">
                <n-icon size="14" color="#64748B"><Folder /></n-icon>
                <span class="file-name">{{ selectedProjectDir }}</span>
              </div>
              <div v-if="selectedProjectDir" class="options-panel">
                <n-space align="center" wrap>
                  <n-checkbox v-model:checked="recompileOptions.sign" size="small">{{ t('package.sign') }}</n-checkbox>
                  <n-select v-if="recompileOptions.sign" v-model:value="recompileSignatureId"
                    :options="signatureConfigs.map(c => ({ label: c.name, value: c.id }))"
                    :placeholder="t('package.signature')" style="width: 150px" size="tiny" />
                  <n-checkbox v-if="recompileOptions.sign" v-model:checked="recompileOptions.v2" size="small">{{ t('package.v2') }}</n-checkbox>
                  <n-checkbox v-model:checked="recompileOptions.align" size="small">{{ t('package.zipAlign') }}</n-checkbox>
                </n-space>
              </div>
              <div v-if="recompileProgress && recompileProgress.show" style="margin-top: 12px">
                <n-progress type="line" :percentage="recompileProgress.value" color="#22C55E" />
              </div>
              <div class="card-actions">
                <n-button type="primary" size="small" :disabled="!selectedProjectDir" @click="startRecompile" block>
                  <template #icon><n-icon><Lock /></n-icon></template>
                  {{ t('package.recompile') }}
                </n-button>
                <n-button v-if="recompileOutputPath" size="small" @click="openRecompileOutput">
                  <template #icon><n-icon><FolderOpen /></n-icon></template>
                  {{ t('package.open') }}
                </n-button>
              </div>
            </n-card>
          </n-grid-item>
        </n-grid>
      </n-tab-pane>

      <!-- Tab 3: Resign & Signatures -->
      <n-tab-pane name="resign" :tab="t('package.resignSignatures')">
        <n-grid :cols="2" :x-gap="16" responsive="screen">
          <!-- Resign -->
          <n-grid-item span="1 800:1">
            <n-card :bordered="false" size="small" class="pkg-card">
              <div class="card-header-row">
                  <n-icon size="18" color="#EC4899"><PenTool /></n-icon>
                  <span class="card-title">{{ t('package.resign') }}</span>
                </div>
              <div class="drop-zone" @drop="handleDrop($event, handleResignFileSelect)" @dragover.prevent
                @dragenter.prevent @click="selectResignFile()">
                <n-icon size="28" color="#475569"><PenTool /></n-icon>
                <p class="drop-text">{{ t('package.dropToResign') }}</p>
                <input type="file" accept=".apk" class="hidden-input"
                  @change="handleFileInputChange($event, handleResignFileSelect)">
              </div>
              <div v-if="selectedResignFile" class="file-info-row">
                <n-icon size="14" color="#64748B"><File /></n-icon>
                <span class="file-name">{{ selectedResignFile.name }}</span>
                <span class="file-size">{{ formatFileSize(selectedResignFile.size) }}</span>
              </div>
              <div class="options-panel" v-if="selectedResignFile">
                <n-space align="center">
                  <n-select v-model:value="selectedSignatureId"
                    :options="signatureConfigs.map(c => ({ label: c.name, value: c.id }))"
                    :placeholder="t('package.selectSignature')" style="width: 180px" size="small" />
                  <n-checkbox v-model:checked="resignOptions.v2" size="small">{{ t('package.v2sign') }}</n-checkbox>
                </n-space>
              </div>
              <div v-if="resignResult" class="analysis-result" v-html="resignResult" />
              <div class="card-actions">
                <n-button type="primary" size="small" :loading="isResigning"
                  :disabled="!selectedResignFile || !selectedSignatureId || isResigning" @click="resignApk" block>
                  <template #icon><n-icon><PenTool /></n-icon></template>
                  {{ t('package.resign2') }}
                </n-button>
                <n-button v-if="resignOutputPath" size="small" @click="openResignOutput">
                  <template #icon><n-icon><FolderOpen /></n-icon></template>
                  {{ t('package.open') }}
                </n-button>
              </div>
            </n-card>
          </n-grid-item>

          <!-- Signature Configs -->
          <n-grid-item span="1 800:1">
            <n-card :bordered="false" size="small" class="pkg-card">
              <div class="card-header-row">
                  <n-icon size="18" color="#F59E0B"><Key /></n-icon>
                  <span class="card-title">{{ t('package.signatureConfigs') }}</span>
                </div>
                <n-button size="tiny" quaternary @click="openSignatureModal()">
                  <template #icon><n-icon><Plus /></n-icon></template>
                  {{ t('package.add') }}
                </n-button>
              <div v-if="signatureConfigs.length > 0" class="sig-list">
                <div v-for="config in signatureConfigs" :key="config.id" class="sig-item">
                  <div class="sig-info">
                    <span class="sig-name">{{ config.name }}</span>
                    <span class="sig-alias">{{ config.alias }}</span>
                  </div>
                  <n-space size="small">
                    <n-button size="tiny" quaternary @click="openSignatureModal(config)">
                      <template #icon><n-icon size="14"><Edit /></n-icon></template>
                    </n-button>
                    <n-button size="tiny" quaternary type="error" @click="deleteSignature(config.id)">
                      <template #icon><n-icon size="14"><Trash2 /></n-icon></template>
                    </n-button>
                  </n-space>
                </div>
              </div>
              <div v-else class="empty-state">
                <n-icon size="24" color="#475569"><Key /></n-icon>
                <p>{{ t('package.noSignatureConfigs') }}</p>
              </div>
            </n-card>
          </n-grid-item>
        </n-grid>
      </n-tab-pane>
    </n-tabs>

    <!-- Signature Edit Modal -->
    <SignatureEditModal
      v-model:visible="showSignatureModal"
      :data="editingSignature"
      @save="handleSaveSignature"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { storeToRefs } from 'pinia'
import serviceManager from '@services/ServiceManager'
import { useNotification } from '@composables/useNotification'
import { usePackageStore } from '@stores/packageStore'
import { useSignatureStore } from '@stores/signatureStore'
import SignatureEditModal from '@components/package/SignatureEditModal.vue'
import { NIcon } from 'naive-ui'
import {
  Package, Download, Unlock, Lock, PenTool, Search, FolderOpen,
  Plus, Edit, Trash2, File, Folder, Key
} from 'lucide-vue-next'

const { t } = useI18n()

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

const selectedResignFile = ref<any>(null)
const selectedSignatureId = ref('')
const recompileSignatureId = ref('')
const isResigning = ref(false)
const resignResult = ref<any>(null)
const resignOutputPath = ref<any>(null)
const showSignatureModal = ref(false)
const editingSignature = ref<any>(null)

const { showLoading, completeLoading, failLoading } = useNotification()
const errorServiceRef = ref<any>(null)
const apkServiceRef = ref<any>(null)

const getErrorService = async () => {
  if (!errorServiceRef.value) errorServiceRef.value = await serviceManager.getService('error')
  return errorServiceRef.value
}

const getApkService = async () => {
  if (!apkServiceRef.value) apkServiceRef.value = await serviceManager.getService('apk')
  return apkServiceRef.value
}

const handleDrop = (event: DragEvent, callback: (file: File) => void) => {
  event.preventDefault()
  if (event.dataTransfer?.files && event.dataTransfer.files.length > 0) {
    callback(event.dataTransfer.files[0])
  }
}

const handleFileInputChange = (event: Event, callback: (file: File) => void) => {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  if (file) callback(file)
  target.value = ''
}

const selectFileWithStats = async (targetRef: any, extensions = ['apk']) => {
  try {
    const systemSvc = await serviceManager.getService('system') as any
    const res = await systemSvc.selectFile({
      title: t('package.selectFile'),
      filters: [{ name: t('package.androidPackages'), extensions }]
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

const handleApkFileSelect = async (file: File) => {
  if (file && file.name.toLowerCase().endsWith('.apk')) selectedAnalysisFile.value = file as any
  else { const svc = await getErrorService(); if (svc) svc.reportError(new Error(t('package.pleaseSelectApk')), { category: 'ui', severity: 'low' }) }
}

const handleInstallFileSelect = async (file: File) => {
  const name = file.name.toLowerCase()
  if (file && (name.endsWith('.apk') || name.endsWith('.aab'))) selectedInstallFile.value = file as any
  else { const svc = await getErrorService(); if (svc) svc.reportError(new Error(t('package.pleaseSelectApkAab')), { category: 'ui', severity: 'low' }) }
}

const handleDecompileFileSelect = async (file: File) => {
  if (file && file.name.toLowerCase().endsWith('.apk')) selectedDecompileFile.value = file as any
  else { const svc = await getErrorService(); if (svc) svc.reportError(new Error(t('package.pleaseSelectApk')), { category: 'ui', severity: 'low' }) }
}

const handleResignFileSelect = async (file: File) => {
  if (file && file.name.toLowerCase().endsWith('.apk')) selectedResignFile.value = file as any
  else { const svc = await getErrorService(); if (svc) svc.reportError(new Error(t('package.pleaseSelectApk')), { category: 'ui', severity: 'low' }) }
}

const analyzeApk = async () => {
  if (!selectedAnalysisFile.value) return
  let loadingId: any = null
  try {
    isAnalyzing.value = true
    loadingId = showLoading(t('package.analyzing'))
    const apkService = await getApkService()
    const result = await apkService.analyzeApk(selectedAnalysisFile.value.path)
    if (result.success) {
      apkAnalysisResult.value = displayApkAnalysisResult(result.data)
      if (loadingId) completeLoading(loadingId, t('package.analysisComplete'), '')
    } else {
      if (loadingId) failLoading(loadingId, t('package.analysisFailed'), String(result.error || ''))
    }
  } catch (error: any) {
    if (loadingId) failLoading(loadingId, t('package.analysisFailed'), error.message || String(error))
    const svc = await getErrorService(); if (svc) svc.reportError(error, { category: 'ui', severity: 'low' })
  } finally { isAnalyzing.value = false }
}

const installApp = async () => {
  if (!selectedInstallFile.value) return
  let loadingId: any = null
  try {
    isInstalling.value = true
    loadingId = showLoading(t('package.installing'))
    const deviceSvc = await serviceManager.getService('device') as any
    const result = await deviceSvc.installApp(selectedInstallFile.value.path)
    if (result.success) {
      if (loadingId) completeLoading(loadingId, t('package.installComplete'), '')
    } else {
      if (loadingId) failLoading(loadingId, t('package.installFailed'), String(result.error || ''))
    }
  } catch (error: any) {
    if (loadingId) failLoading(loadingId, t('package.installFailed'), error.message || String(error))
    const svc = await getErrorService(); if (svc) svc.reportError(error, { category: 'device', context: 'device.install' })
  } finally { isInstalling.value = false }
}

const startDecompile = async () => {
  if (!selectedDecompileFile.value) return
  let loadingId: any = null
  try {
    isDecompiling.value = true
    if (decompileProgress && decompileProgress.value) {
      decompileProgress.value.show = true; decompileProgress.value.value = 0
    }
    loadingId = showLoading(t('package.decompiling'))
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
      decompileResult.value = `<div class="apk-info-grid"><div class="info-row"><span class="label">${t('package.status')}:</span><span class="value highlight text-success">${t('package.success')}</span></div><div class="info-row"><span class="label">${t('package.output')}:</span><span class="value code">${result.outputPath}</span></div></div>`
      if (loadingId) completeLoading(loadingId, t('package.decompileComplete'), `${t('package.output')}: ${result.outputPath}`)
    } else {
      if (loadingId) failLoading(loadingId, t('package.decompileFailed'), String(result.error || ''))
    }
  } catch (error: any) {
    if (loadingId) failLoading(loadingId, t('package.decompileFailed'), String(error || ''))
    const svc = await getErrorService(); if (svc) svc.reportError(error, { category: 'tool', context: 'apk.decompile' })
  } finally {
    isDecompiling.value = false
    setTimeout(() => { if (decompileProgress?.value) { decompileProgress.value.show = false; decompileProgress.value.value = 0 } }, 2000)
  }
}

const openDecompileOutput = async () => {
  if (decompileOutputPath.value) {
    const systemSvc = await serviceManager.getService('system') as any
    await systemSvc.openPath(decompileOutputPath.value)
  }
}

const selectProjectDir = async () => {
  try {
    const systemSvc = await serviceManager.getService('system') as any
    const result = await systemSvc.selectDirectory()
    if (result && !result.canceled) selectedProjectDir.value = result.filePaths[0]
  } catch (error) {
    const svc = await getErrorService(); if (svc) svc.reportError(error, { category: 'system', context: 'system.selectDirectory' })
  }
}

const startRecompile = async () => {
  if (!selectedProjectDir.value) return
  if (recompileOptions.value.sign && !recompileSignatureId.value) {
    const svc = await getErrorService(); if (svc) svc.reportError(new Error(t('package.pleaseSelectSignature')), { category: 'ui', severity: 'low' })
    return
  }
  let loadingId: any = null
  try {
    recompileProgress.value.show = true; recompileProgress.value.value = 0
    loadingId = showLoading(t('package.recompiling'))
    const options: any = { sign: recompileOptions.value.sign, align: recompileOptions.value.align, optimize: recompileOptions.value.optimize, v2: recompileOptions.value.v2 }
    if (options.sign) {
      const config = signatureStore.getConfigById(recompileSignatureId.value)
      if (config) options.keystore = { path: config.path, alias: config.alias, storepass: config.storepass, keypass: config.keypass }
    }
    const apkService = await getApkService()
    const result = await apkService.recompileApk(selectedProjectDir.value, options)
    if (result.success) {
      recompileProgress.value.value = 100; recompileOutputPath.value = result.outputPath
      recompileResult.value = `<p>${t('package.recompileComplete')}! ${t('package.output')}: ${result.outputPath}</p>`
      if (loadingId) completeLoading(loadingId, t('package.recompileComplete'), `${t('package.output')}: ${result.outputPath}`)
    } else {
      if (loadingId) failLoading(loadingId, t('package.recompileFailed'), String(result.error || ''))
    }
  } catch (error: any) {
    if (loadingId) failLoading(loadingId, t('package.recompileFailed'), String(error || ''))
    const svc = await getErrorService(); if (svc) svc.reportError(error, { category: 'tool', context: 'apk.recompile' })
  } finally {
    setTimeout(() => { recompileProgress.value.show = false; recompileProgress.value.value = 0 }, 2000)
  }
}

const openRecompileOutput = async () => {
  if (recompileOutputPath.value) {
    const svc = await serviceManager.getService('system') as any
    await svc.openPath(recompileOutputPath.value)
  }
}

const resignApk = async () => {
  if (!selectedResignFile.value) return
  const config = signatureStore.getConfigById(selectedSignatureId.value)
  if (!config) {
    const svc = await getErrorService(); if (svc) svc.reportError(new Error(t('package.pleaseSelectSignature')), { category: 'ui', severity: 'low' })
    return
  }
  let loadingId: any = null
  try {
    isResigning.value = true
    loadingId = showLoading(t('package.resigning'))
    const apkService = await getApkService()
    const keystore = { path: config.path, alias: config.alias, storepass: config.storepass, keypass: config.keypass }
    const options = { v2: resignOptions.value.v2 }
    const result = await apkService.signApk(selectedResignFile.value.path, keystore, options)
    if (result.success) {
      resignOutputPath.value = result.outputPath
      resignResult.value = `<p>${t('package.resignComplete')}! ${t('package.output')}: ${result.outputPath}</p>`
      if (loadingId) completeLoading(loadingId, t('package.resignComplete'), `${t('package.output')}: ${result.outputPath}`)
    } else {
      if (loadingId) failLoading(loadingId, t('package.resignFailed'), String(result.error || ''))
    }
  } catch (error: any) {
    if (loadingId) failLoading(loadingId, t('package.resignFailed'), String(error || ''))
    const svc = await getErrorService(); if (svc) svc.reportError(error, { category: 'tool', context: 'apk.resign' })
  } finally { isResigning.value = false }
}

const openResignOutput = async () => {
  if (resignOutputPath.value) {
    const svc = await serviceManager.getService('system') as any
    await svc.openPath(resignOutputPath.value)
  }
}

const openSignatureModal = (config: any = null) => {
  editingSignature.value = config ? { ...config } : null
  showSignatureModal.value = true
}

const handleSaveSignature = async (formData: any) => {
  if (formData.id) await signatureStore.updateConfig({ ...formData })
  else await signatureStore.addConfig({ ...formData })
  if (signatureConfigs.value.length === 1) {
    selectedSignatureId.value = signatureConfigs.value[0].id
    recompileSignatureId.value = signatureConfigs.value[0].id
  }
}

const deleteSignature = async (id: string) => {
  if (confirm(t('package.deleteSignatureConfirm'))) {
    await signatureStore.removeConfig(id)
    if (selectedSignatureId.value === id) selectedSignatureId.value = signatureConfigs.value.length > 0 ? signatureConfigs.value[0].id : ''
    if (recompileSignatureId.value === id) recompileSignatureId.value = signatureConfigs.value.length > 0 ? signatureConfigs.value[0].id : ''
  }
}

const formatFileSize = (bytes: number) => {
  if (bytes === 0) return '0 ' + t('package.bytes')
  const k = 1024
  const sizes = [t('package.bytes'), t('package.kb'), t('package.mb'), t('package.gb')]
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
}

const displayApkAnalysisResult = (data: any) => {
  if (!data) return ''
  let permissionsHtml = ''
  if (data.permissions && data.permissions.length > 0) {
    const visiblePerms = data.permissions.slice(0, 5)
    const hiddenPerms = data.permissions.slice(5)
    permissionsHtml = '<div class="permissions-list">'
    visiblePerms.forEach((p: any) => {
      const name = p.name || p
      permissionsHtml += `<div class="perm-tag">${name.split('.').pop()}</div>`
    })
    if (hiddenPerms.length > 0) permissionsHtml += `<div class="perm-tag more">+${hiddenPerms.length}</div>`
    permissionsHtml += '</div>'
  }
  return `<div class="apk-info-grid">
    <div class="info-row"><span class="label">${t('package.appName')}:</span><span class="value highlight">${data.applicationLabel || t('package.n_a')}</span></div>
    <div class="info-row"><span class="label">${t('package.packageName')}:</span><span class="value code">${data.packageName || t('package.n_a')}</span></div>
    <div class="info-group"><div class="info-col"><span class="label">${t('package.version')}:</span><span class="value">${data.versionName || t('package.n_a')}</span></div><div class="info-col"><span class="label">${t('package.code')}:</span><span class="value">${data.versionCode || t('package.n_a')}</span></div></div>
    <div class="info-group"><div class="info-col"><span class="label">${t('package.minSdk')}:</span><span class="value">${data.minSdkVersion || t('package.n_a')}</span></div><div class="info-col"><span class="label">${t('package.targetSdk')}:</span><span class="value">${data.targetSdkVersion || t('package.n_a')}</span></div></div>
    <div class="info-row"><span class="label">${t('package.permissions')}:</span><span class="value">${permissionsHtml || t('package.none')}</span></div>
  </div>`
}

onMounted(async () => {
  try { apkServiceRef.value = await serviceManager.getService('apk') } catch { /* ignore */ }
  await signatureStore.loadConfigs()
  if (signatureConfigs.value.length > 0) {
    selectedSignatureId.value = signatureConfigs.value[0].id
    recompileSignatureId.value = signatureConfigs.value[0].id
  }
})
</script>

<style scoped>
.package-page {
  max-width: 1100px;
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
.pkg-tabs {
  margin-top: 4px;
}
.pkg-card {
  background: #1E293B;
  border-radius: 10px;
  margin-bottom: 16px;
}
.card-header-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.card-title {
  font-family: Inter, sans-serif;
  font-size: 14px;
  font-weight: 600;
  color: #F8FAFC;
}
.drop-zone {
  border: 2px dashed #334155;
  border-radius: 10px;
  padding: 28px 16px;
  text-align: center;
  cursor: pointer;
  transition: all 0.2s;
  color: #64748B;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}
.drop-zone:hover {
  border-color: #22C55E;
  background: rgba(34,197,94,0.04);
  color: #94A3B8;
}
.drop-zone.disabled {
  opacity: 0.5;
  cursor: not-allowed;
  pointer-events: none;
}
.drop-text {
  font-size: 13px;
  margin: 0;
}
.file-info-row {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 12px;
  padding: 8px 12px;
  background: #0C1322;
  border-radius: 6px;
  font-size: 13px;
}
.file-name {
  flex: 1;
  color: #E2E8F0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.file-size {
  font-family: 'Fira Code', monospace;
  font-size: 11px;
  color: #94A3B8;
  flex-shrink: 0;
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
  padding: 10px 12px;
  background: #0C1322;
  border-radius: 8px;
}
.card-actions {
  margin-top: 14px;
  display: flex;
  gap: 8px;
}
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 24px;
  text-align: center;
  color: #64748B;
  font-size: 13px;
}
.empty-state p { margin: 0; }
.sig-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.sig-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  background: #0C1322;
  border-radius: 8px;
  transition: background 0.15s;
}
.sig-item:hover {
  background: #162032;
}
.sig-info {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
}
.sig-name {
  font-size: 13px;
  font-weight: 500;
  color: #E2E8F0;
}
.sig-alias {
  font-size: 11px;
  color: #64748B;
  font-family: 'Fira Code', monospace;
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
