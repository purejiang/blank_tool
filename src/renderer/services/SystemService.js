import unifiedAPI from '../api/unifiedApi.js'

class SystemService {
    constructor() {

    }

    async getSystemInfo() {
        const direct = await unifiedAPI.safeCall('getSystemInfo')
        if (direct && direct.platform) return { system_info: direct }
        const resp = await unifiedAPI.call('system.info')
        return resp || { system_info: {} }
    }

    async getBuildInfo() {
        const resp = await unifiedAPI.call('build.info')
        return resp || { build_info: {} }
    }

    async getAppVersion() {
        const direct = await unifiedAPI.safeCall('getAppVersion')
        return direct
    }

    async getElectronVersion() {
        return await unifiedAPI.safeCall('getElectronVersion')
    }

    async selectDirectory(options = {}) {
        return await unifiedAPI.safeCall('selectDirectory', options)
    }

    async selectFile(options = {}) {
        // 优先使用自定义的 selectFile，如果不可用则回退到系统对话框
        const api = unifiedAPI.getAPI()
        if (api && typeof api.selectFile === 'function') {
            console.log('selectFile', options)
            return await api.selectFile(options)
        }
        if (api && typeof api.showOpenDialog === 'function') {
            console.log('showOpenDialog', api.showOpenDialog)
            const dialogOptions = {
                title: (options && options.title) || '选择文件',
                properties: ['openFile'],
                filters: options && options.filters ? options.filters : undefined
            }
            try {
                const res = await api.showOpenDialog(dialogOptions)
                return res
            } catch (e) {
                return { canceled: true }
            }
        }
        return { canceled: true }
    }

    async openPath(path) {
        return await unifiedAPI.safeCall('openPath', path)
    }

    async copyText(text) {
        if (!text) return false
        try {
            if (navigator.clipboard && navigator.clipboard.writeText) {
                await navigator.clipboard.writeText(text)
                return true
            }
            const api = unifiedAPI.getAPI()
            if (api && typeof api.writeClipboardText === 'function') {
                await api.writeClipboardText(text)
                return true
            }
        } catch { }
        return false
    }

    async getFileStats(path) {
        return await unifiedAPI.safeCall('getFileStats', path)
    }
}

export default SystemService
