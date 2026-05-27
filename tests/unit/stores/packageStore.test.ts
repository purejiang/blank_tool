import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { usePackageStore } from '@/renderer/stores/packageStore'

describe('packageStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  describe('initial state', () => {
    it('has null selected files', () => {
      const store = usePackageStore()
      expect(store.selectedAnalysisFile).toBeNull()
      expect(store.selectedInstallFile).toBeNull()
      expect(store.selectedDecompileFile).toBeNull()
      expect(store.selectedProjectDir).toBeNull()
    })

    it('has null analysis results', () => {
      const store = usePackageStore()
      expect(store.apkAnalysisResult).toBeNull()
      expect(store.decompileResult).toBeNull()
      expect(store.recompileResult).toBeNull()
    })

    it('has null output paths', () => {
      const store = usePackageStore()
      expect(store.decompileOutputPath).toBeNull()
      expect(store.recompileOutputPath).toBeNull()
    })

    it('has false processing flags', () => {
      const store = usePackageStore()
      expect(store.isAnalyzing).toBe(false)
      expect(store.isInstalling).toBe(false)
      expect(store.isDecompiling).toBe(false)
      expect(store.isRecompiling).toBe(false)
    })

    it('has progress at 0', () => {
      const store = usePackageStore()
      expect(store.installProgress.value).toBe(0)
      expect(store.decompileProgress.value).toBe(0)
      expect(store.recompileProgress.value).toBe(0)
    })
  })

  describe('setSelectedAnalysisFile', () => {
    it('sets analysis file', () => {
      const store = usePackageStore()
      store.setSelectedAnalysisFile('/path/to/app.apk')
      expect(store.selectedAnalysisFile).toBe('/path/to/app.apk')
    })
  })

  describe('setSelectedInstallFile', () => {
    it('sets install file', () => {
      const store = usePackageStore()
      store.setSelectedInstallFile('/path/to/install.apk')
      expect(store.selectedInstallFile).toBe('/path/to/install.apk')
    })
  })

  describe('setSelectedDecompileFile', () => {
    it('sets decompile file', () => {
      const store = usePackageStore()
      store.setSelectedDecompileFile('/path/to/decompile.apk')
      expect(store.selectedDecompileFile).toBe('/path/to/decompile.apk')
    })
  })

  describe('setSelectedProjectDir', () => {
    it('sets project directory', () => {
      const store = usePackageStore()
      store.setSelectedProjectDir('/path/to/project')
      expect(store.selectedProjectDir).toBe('/path/to/project')
    })
  })

  describe('setApkAnalysisResult', () => {
    it('sets analysis result', () => {
      const store = usePackageStore()
      const result = { packageName: 'com.test' }
      store.setApkAnalysisResult(result)
      expect(store.apkAnalysisResult).toEqual(result)
    })
  })

  describe('reset', () => {
    it('resets file selections and results', () => {
      const store = usePackageStore()
      store.setSelectedAnalysisFile('/test.apk')
      store.setSelectedInstallFile('/install.apk')
      store.setApkAnalysisResult({ pkg: 'test' })
      store.installProgress.value = 50

      store.reset()

      expect(store.selectedAnalysisFile).toBeNull()
      expect(store.selectedInstallFile).toBeNull()
      expect(store.apkAnalysisResult).toBeNull()
      expect(store.installProgress.value).toBe(0)
    })

    it('resets progress indicators', () => {
      const store = usePackageStore()
      store.installProgress.value = 75
      store.decompileProgress.value = 50
      store.recompileProgress.value = 25
      store.installProgress.show = true
      store.decompileProgress.show = true
      store.recompileProgress.show = true

      store.reset()

      expect(store.installProgress.value).toBe(0)
      expect(store.decompileProgress.value).toBe(0)
      expect(store.recompileProgress.value).toBe(0)
      expect(store.installProgress.show).toBe(false)
      expect(store.decompileProgress.show).toBe(false)
      expect(store.recompileProgress.show).toBe(false)
    })

    it('resets output paths', () => {
      const store = usePackageStore()
      store.setDecompileOutputPath('/tmp/decompiled')
      store.setRecompileOutputPath('/tmp/recompiled')

      store.reset()

      expect(store.decompileOutputPath).toBeNull()
      expect(store.recompileOutputPath).toBeNull()
    })
  })

  describe('decompileOptions', () => {
    it('has default decompile options', () => {
      const store = usePackageStore()
      expect(store.decompileOptions.resources).toBe(true)
      expect(store.decompileOptions.sources).toBe(true)
      expect(store.decompileOptions.manifest).toBe(true)
    })
  })

  describe('recompileOptions', () => {
    it('has default recompile options', () => {
      const store = usePackageStore()
      expect(store.recompileOptions.sign).toBe(true)
      expect(store.recompileOptions.align).toBe(true)
      expect(store.recompileOptions.optimize).toBe(false)
      expect(store.recompileOptions.v2).toBe(true)
    })
  })
})
