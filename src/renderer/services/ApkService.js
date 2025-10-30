/**
 * APK服务 - 处理APK相关操作
 */

class ApkService {
    constructor() {
        this.currentApk = null;
        this.analysisResults = new Map();
        this.listeners = new Set();
    }

    /**
     * 分析APK文件
     * @param {string} apkPath - APK文件路径
     */
    async analyzeApk(apkPath) {
        try {
            const result = await window.electronAPI.analyzeApk(apkPath);
            
            if (result.success) {
                const analysis = result.analysis;
                
                // 缓存分析结果
                this.analysisResults.set(apkPath, {
                    analysis,
                    timestamp: Date.now(),
                    path: apkPath
                });
                
                this.currentApk = apkPath;
                this.notifyListeners('apk-analyzed', { apkPath, analysis });
                
                return analysis;
            } else {
                throw new Error(result.error);
            }
        } catch (error) {
            throw error;
        }
    }

    /**
     * 提取APK资源
     * @param {string} apkPath - APK文件路径
     * @param {string} outputDir - 输出目录
     */
    async extractApkResources(apkPath, outputDir) {
        try {
            const result = await window.electronAPI.extractApkResources(apkPath, outputDir);
            if (result.success) {
                return result;
            } else {
                throw new Error(result.error);
            }
        } catch (error) {
            throw error;
        }
    }

    /**
     * 获取APK基本信息
     */
    getApkBasicInfo(analysis) {
        if (!analysis) return null;

        return {
            packageName: analysis.package_name || 'Unknown',
            versionName: analysis.version_name || 'Unknown',
            versionCode: analysis.version_code || 'Unknown',
            minSdkVersion: analysis.min_sdk_version || 'Unknown',
            targetSdkVersion: analysis.target_sdk_version || 'Unknown',
            compileSdkVersion: analysis.compile_sdk_version || 'Unknown',
            applicationLabel: analysis.application_label || 'Unknown',
            fileSize: analysis.file_size || 0,
            installLocation: analysis.install_location || 'auto'
        };
    }

    /**
     * 获取APK权限信息
     */
    getApkPermissions(analysis) {
        if (!analysis || !analysis.permissions) return [];

        return analysis.permissions.map(permission => ({
            name: permission.name || permission,
            level: this.getPermissionLevel(permission.name || permission),
            description: this.getPermissionDescription(permission.name || permission)
        }));
    }

    /**
     * 获取APK组件信息
     */
    getApkComponents(analysis) {
        if (!analysis) return null;

        return {
            activities: analysis.activities || [],
            services: analysis.services || [],
            receivers: analysis.receivers || [],
            providers: analysis.providers || []
        };
    }

    /**
     * 获取APK资源信息
     */
    getApkResources(analysis) {
        if (!analysis || !analysis.resources) return null;

        return {
            drawables: analysis.resources.drawables || [],
            layouts: analysis.resources.layouts || [],
            values: analysis.resources.values || [],
            raw: analysis.resources.raw || [],
            assets: analysis.resources.assets || []
        };
    }

    /**
     * 获取权限级别
     */
    getPermissionLevel(permission) {
        const dangerousPermissions = [
            'android.permission.READ_CONTACTS',
            'android.permission.WRITE_CONTACTS',
            'android.permission.READ_CALENDAR',
            'android.permission.WRITE_CALENDAR',
            'android.permission.CAMERA',
            'android.permission.READ_EXTERNAL_STORAGE',
            'android.permission.WRITE_EXTERNAL_STORAGE',
            'android.permission.ACCESS_FINE_LOCATION',
            'android.permission.ACCESS_COARSE_LOCATION',
            'android.permission.RECORD_AUDIO',
            'android.permission.READ_PHONE_STATE',
            'android.permission.CALL_PHONE',
            'android.permission.READ_CALL_LOG',
            'android.permission.WRITE_CALL_LOG',
            'android.permission.SEND_SMS',
            'android.permission.RECEIVE_SMS',
            'android.permission.READ_SMS'
        ];

        if (dangerousPermissions.includes(permission)) {
            return 'dangerous';
        } else if (permission.startsWith('android.permission.')) {
            return 'normal';
        } else {
            return 'custom';
        }
    }

    /**
     * 获取权限描述
     */
    getPermissionDescription(permission) {
        const descriptions = {
            'android.permission.INTERNET': '访问网络',
            'android.permission.ACCESS_NETWORK_STATE': '获取网络状态',
            'android.permission.ACCESS_WIFI_STATE': '获取WiFi状态',
            'android.permission.WRITE_EXTERNAL_STORAGE': '写入外部存储',
            'android.permission.READ_EXTERNAL_STORAGE': '读取外部存储',
            'android.permission.CAMERA': '使用摄像头',
            'android.permission.RECORD_AUDIO': '录制音频',
            'android.permission.ACCESS_FINE_LOCATION': '获取精确位置',
            'android.permission.ACCESS_COARSE_LOCATION': '获取大概位置',
            'android.permission.READ_PHONE_STATE': '读取手机状态',
            'android.permission.CALL_PHONE': '拨打电话',
            'android.permission.SEND_SMS': '发送短信',
            'android.permission.READ_SMS': '读取短信',
            'android.permission.READ_CONTACTS': '读取联系人',
            'android.permission.WRITE_CONTACTS': '写入联系人'
        };

        return descriptions[permission] || '自定义权限';
    }

    /**
     * 格式化文件大小
     */
    formatFileSize(bytes) {
        if (bytes === 0) return '0 B';
        
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }

    /**
     * 生成APK分析报告
     */
    generateAnalysisReport(analysis) {
        if (!analysis) return null;

        const basicInfo = this.getApkBasicInfo(analysis);
        const permissions = this.getApkPermissions(analysis);
        const components = this.getApkComponents(analysis);
        const resources = this.getApkResources(analysis);

        return {
            basicInfo,
            permissions,
            components,
            resources,
            summary: {
                totalPermissions: permissions.length,
                dangerousPermissions: permissions.filter(p => p.level === 'dangerous').length,
                totalActivities: components.activities.length,
                totalServices: components.services.length,
                formattedFileSize: this.formatFileSize(basicInfo.fileSize)
            }
        };
    }

    /**
     * 获取当前APK
     */
    getCurrentApk() {
        return this.currentApk;
    }

    /**
     * 获取分析历史
     */
    getAnalysisHistory() {
        return Array.from(this.analysisResults.values()).sort((a, b) => 
            b.analyzedAt.getTime() - a.analyzedAt.getTime()
        );
    }

    /**
     * 清除分析历史
     */
    clearAnalysisHistory() {
        this.analysisResults.clear();
        this.currentApk = null;
        this.notifyListeners('history-cleared');
    }

    /**
     * 导出分析结果
     */
    async exportAnalysisResult(filePath, format = 'json') {
        if (!this.currentApk) {
            throw new Error('没有可导出的分析结果');
        }

        try {
            const report = this.generateAnalysisReport(this.currentApk.analysis);
            let content;

            switch (format) {
                case 'json':
                    content = JSON.stringify(report, null, 2);
                    break;
                case 'txt':
                    content = this.formatReportAsText(report);
                    break;
                default:
                    throw new Error('不支持的导出格式');
            }

            import('fs').then(fs => {
                fs.writeFileSync(filePath, content, 'utf8');
            });
            
            return true;
        } catch (error) {
            return false;
        }
    }

    /**
     * 格式化报告为文本
     */
    formatReportAsText(report) {
        let text = 'APK分析报告\n';
        text += '='.repeat(50) + '\n\n';

        // 基本信息
        text += '基本信息:\n';
        text += `-包名: ${report.basicInfo.packageName}\n`;
        text += `-版本名: ${report.basicInfo.versionName}\n`;
        text += `-版本号: ${report.basicInfo.versionCode}\n`;
        text += `-文件大小: ${report.summary.formattedFileSize}\n`;
        text += `-最小SDK: ${report.basicInfo.minSdkVersion}\n`;
        text += `-目标SDK: ${report.basicInfo.targetSdkVersion}\n\n`;

        // 权限信息
        text += '权限信息:\n';
        text += `-总权限数: ${report.summary.totalPermissions}\n`;
        text += `-危险权限数: ${report.summary.dangerousPermissions}\n`;
        report.permissions.forEach(perm => {
            text += `  - ${perm.name} (${perm.level})\n`;
        });
        text += '\n';

        // 组件信息
        text += '组件信息:\n';
        text += `-Activity数: ${report.summary.totalActivities}\n`;
        text += `-Service数: ${report.summary.totalServices}\n`;

        return text;
    }

    /**
     * 反编译APK
     */
    async decompileApk(filePath, options = {}) {
        try {
            const result = await window.electronAPI.callBackendAPI('apk.decompile', {
                filePath,
                options
            });
            
            this.notifyListeners('decompile-progress', result);
            return result;
        } catch (error) {
            console.error('反编译APK失败:', error);
            throw error;
        }
    }

    /**
     * 回编译APK
     */
    async recompileApk(projectPath, options = {}) {
        try {
            const result = await window.electronAPI.callBackendAPI('apk.recompile', {
                projectPath,
                options
            });
            
            this.notifyListeners('recompile-progress', result);
            return result;
        } catch (error) {
            console.error('回编译APK失败:', error);
            throw error;
        }
    }

    /**
     * 签名APK
     */
    async signApk(apkPath, keystore, options = {}) {
        try {
            const result = await window.electronAPI.callBackendAPI('apk.sign', {
                apkPath,
                keystore,
                options
            });
            
            this.notifyListeners('sign-progress', result);
            return result;
        } catch (error) {
            console.error('签名APK失败:', error);
            throw error;
        }
    }

    /**
     * 获取反编译进度
     */
    async getDecompileProgress(taskId) {
        try {
            return await window.electronAPI.callBackendAPI('apk.getProgress', { taskId });
        } catch (error) {
            console.error('获取反编译进度失败:', error);
            throw error;
        }
    }

    /**
     * 取消反编译任务
     */
    async cancelDecompileTask(taskId) {
        try {
            return await window.electronAPI.callBackendAPI('apk.cancelTask', { taskId });
        } catch (error) {
            console.error('取消反编译任务失败:', error);
            throw error;
        }
    }

    /**
     * 添加监听器
     */
    addListener(callback) {
        this.listeners.add(callback);
    }

    /**
     * 移除监听器
     */
    removeListener(callback) {
        this.listeners.delete(callback);
    }

    /**
     * 通知监听器
     */
    notifyListeners(event, data) {
        this.listeners.forEach(callback => {
            try {
                callback(event, data);
            } catch (error) {
                console.error('APK服务监听器错误:', error);
            }
        });
    }
}
export default ApkService;