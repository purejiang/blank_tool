import unifiedApi from '../api/unifiedApi'

class SystemService {
    constructor() { }

    async getSystemInfo() {
        const api = unifiedApi.getAPI()
        if (api && typeof api.getSystemInfo === 'function') {
            console.log('getSystemInfo')
            return await api.getSystemInfo()
        }
        throw new Error('getSystemInfo 方法未实现')
    }

    async getBackendBuildInfo() {
        const api = unifiedApi.getAPI()
        if (api && typeof api.getBackendBuildInfo === 'function') {
            console.log('getBackendBuildInfo')
            return await api.getBackendBuildInfo()
        }
        throw new Error('getBackendBuildInfo 方法未实现')
    }

    async getBuildInfo() {
        const api = unifiedApi.getAPI()
        if (api && typeof api.getBuildInfo === 'function') {
            console.log('getBuildInfo')
            return await api.getBuildInfo()
        }
        throw new Error('getBuildInfo 方法未实现')
    }

    async getAppInfo() {
        const api = unifiedApi.getAPI()
        if (api && typeof api.getAppInfo === 'function') {
            console.log('getAppInfo')
            return await api.getAppInfo()
        }
        throw new Error('getAppInfo 方法未实现')
    }

    async getBackendInfo() {
        const api = unifiedApi.getAPI()
        if (api && typeof api.getBackendInfo === 'function') {
            console.log('getBackendInfo')
            return await api.getBackendInfo()
        }
        throw new Error('getBackendInfo 方法未实现')
    }

    async getFontendBuildInfo() {
        const api = unifiedApi.getAPI()
        if (api && typeof api.getFontendBuildInfo === 'function') {
            console.log('getFontendBuildInfo')
            return await api.getFontendBuildInfo()
        }
        throw new Error('getFontendBuildInfo 方法未实现')
    }

    async selectDirectory(options = {}) {
        const api = unifiedApi.getAPI()
        if (api && typeof api.selectDirectory === 'function') {
            console.log('selectDirectory', options)
            return await api.selectDirectory(options)
        }
        throw new Error('selectDirectory 方法未实现')
    }

    async selectFile(options = {}) {
        // 优先使用自定义的 selectFile，如果不可用则回退到系统对话框
        const api = unifiedApi.getAPI()
        if (api && typeof api.selectFile === 'function') {
            console.log('selectFile', options)
            return await api.selectFile(options)
        }
        throw new Error('selectFile 方法未实现')
    }

    async openPath(path) {
        const api = unifiedApi.getAPI()
        if (api && typeof api.openPath === 'function') {
            console.log('openPath', path)
            return await api.openPath(path)
        }
        throw new Error('openPath 方法未实现')
    }

    async copyText(text) {
        if (!text) return false

        if (navigator.clipboard && navigator.clipboard.writeText) {
            await navigator.clipboard.writeText(text)
            return true
        }
        const api = unifiedApi.getAPI()
        if (api && typeof api.writeClipboardText === 'function') {
            console.log('writeClipboardText', text)
            return await api.writeClipboardText(text)
        }
        throw new Error('writeClipboardText 方法未实现')
    }

    async getFileStats(path) {
        const api = unifiedApi.getAPI()
        if (api && typeof api.getFileStats === 'function') {
            console.log('getFileStats', path)
            return await api.getFileStats(path)
        }
        throw new Error('getFileStats 方法未实现')
    }
}

export default SystemService
