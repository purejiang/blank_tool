import { requireApiMethod } from '../api/apiAccess'

class SystemService {
    constructor() { }

    async getSystemInfo() {
        return await requireApiMethod('getSystemInfo')()
    }

    async getBackendBuildInfo() {
        return await requireApiMethod('getBackendBuildInfo')()
    }

    async getAppInfo() {
        return await requireApiMethod('getAppInfo')()
    }

    async getBackendInfo() {
        return await requireApiMethod('getBackendInfo')()
    }

    async getFontendBuildInfo() {
        return await requireApiMethod('getFontendBuildInfo')()
    }

    async selectDirectory(options = {}) {
        return await requireApiMethod('selectDirectory')(options)
    }

    async selectFile(options = {}) {
        // 优先使用自定义的 selectFile，如果不可用则回退到系统对话框
        return await requireApiMethod('selectFile')(options)
    }

    async openPath(path) {
        return await requireApiMethod('openPath')(path)
    }

    async copyText(text) {
        if (!text) return false

        if (navigator.clipboard && navigator.clipboard.writeText) {
            await navigator.clipboard.writeText(text)
            return true
        }
        return await requireApiMethod('writeClipboardText')(text)
    }

    async getFileStats(path) {
        return await requireApiMethod('getFileStats')(path)
    }
}

export default SystemService
