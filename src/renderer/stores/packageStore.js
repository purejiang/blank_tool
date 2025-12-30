import { defineStore } from 'pinia'
import { ref, reactive } from 'vue'

export const usePackageStore = defineStore('package', () => {
  // 状态
  const selectedAnalysisFile = ref(null)
  const selectedInstallFile = ref(null)
  const selectedDecompileFile = ref(null)
  const selectedProjectDir = ref(null)
  
  // 结果缓存
  const apkAnalysisResult = ref(null)
  const decompileResult = ref(null)
  const recompileResult = ref(null)
  
  const decompileOutputPath = ref(null)
  const recompileOutputPath = ref(null)

  // 进度状态 (通常不需要持久化，但为了保持视图状态也可以保留)
  const isAnalyzing = ref(false)
  const isInstalling = ref(false)
  const isDecompiling = ref(false)
  const isRecompiling = ref(false)
  
  const installProgress = reactive({ show: false, value: 0 })
  const decompileProgress = reactive({ show: false, value: 0 })
  const recompileProgress = reactive({ show: false, value: 0 })

  // 选项配置
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

  // Actions
  function setSelectedAnalysisFile(file) {
    selectedAnalysisFile.value = file
  }

  function setSelectedInstallFile(file) {
    selectedInstallFile.value = file
  }

  function setSelectedDecompileFile(file) {
    selectedDecompileFile.value = file
  }

  function setSelectedProjectDir(path) {
    selectedProjectDir.value = path
  }

  function setApkAnalysisResult(result) {
    apkAnalysisResult.value = result
  }

  function setDecompileResult(result) {
    decompileResult.value = result
  }

  function setRecompileResult(result) {
    recompileResult.value = result
  }

  function setDecompileOutputPath(path) {
    decompileOutputPath.value = path
  }

  function setRecompileOutputPath(path) {
    recompileOutputPath.value = path
  }
  
  function reset() {
    selectedAnalysisFile.value = null
    selectedInstallFile.value = null
    selectedDecompileFile.value = null
    selectedProjectDir.value = null
    apkAnalysisResult.value = null
    decompileResult.value = null
    recompileResult.value = null
    decompileOutputPath.value = null
    recompileOutputPath.value = null
    
    installProgress.show = false
    installProgress.value = 0
    decompileProgress.show = false
    decompileProgress.value = 0
    recompileProgress.show = false
    recompileProgress.value = 0
  }

  return {
    selectedAnalysisFile,
    selectedInstallFile,
    selectedDecompileFile,
    selectedProjectDir,
    apkAnalysisResult,
    decompileResult,
    recompileResult,
    decompileOutputPath,
    recompileOutputPath,
    isAnalyzing,
    isInstalling,
    isDecompiling,
    isRecompiling,
    installProgress,
    decompileProgress,
    recompileProgress,
    decompileOptions,
    recompileOptions,
    setSelectedAnalysisFile,
    setSelectedInstallFile,
    setSelectedDecompileFile,
    setSelectedProjectDir,
    setApkAnalysisResult,
    setDecompileResult,
    setRecompileResult,
    setDecompileOutputPath,
    setRecompileOutputPath,
    reset
  }
}, {
  persist: false // 启用持久化
})
