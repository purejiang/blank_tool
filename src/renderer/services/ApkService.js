/**
 * APK服务 - 处理APK相关操作
 */
import unifiedAPI from '../api/unifiedApi.js';

class ApkService {
    constructor() {
        this.currentApk = null;
        this.analysisResults = new Map();
        this.listeners = new Set();
        this.initialize();
    }

    /**
     * 初始化
     */
    async initialize() {
        try {
            // 初始化APK服务

            console.log('APK服务初始化完成');
        } catch (error) {
            console.error('APK服务初始化失败:', error);
            throw error;
        }
    }

    /**
     * 分析APK文件
     * @param {string} apkPath - APK文件路径
     */
    async analyzeApk(apkPath) {
        try {
            const rawResult = await unifiedAPI.call('apk.analyze_apk', { apk_path: apkPath });

            // Normalize response
            let analysis = null;
            if (rawResult && rawResult.type === 'success' && rawResult.payload) {
                const p = rawResult.payload;
                analysis = {
                    packageName: p.package_name,
                    versionCode: p.version_code,
                    versionName: p.version_name,
                    minSdkVersion: p.min_sdk_version,
                    targetSdkVersion: p.target_sdk_version,
                    permissions: p.permissions,
                    applicationLabel: p.application_label,
                    // Keep original payload just in case
                    ...p
                };
            }

            // Construct the result expected by UI
            const result = {
                success: rawResult && rawResult.type === 'success',
                data: analysis,
                error: rawResult && rawResult.type === 'error' ? (rawResult.payload ? rawResult.payload.message : '未知错误') : null
            };

            if (result.success) {
                // 缓存分析结果
                this.analysisResults.set(apkPath, {
                    analysis,
                    timestamp: Date.now(),
                    path: apkPath
                });
                this.currentApk = { analysis, path: apkPath };
                this.notifyListeners('apk-analyzed', { apkPath, analysis });
            }

            return result;
        } catch (error) {
            console.error(`分析APK失败: ${apkPath}`, error);
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
            const rawResult = await unifiedAPI.call('apk.extract_resources', { apk_path: apkPath, output_dir: outputDir });
            
            const result = {
                success: rawResult && rawResult.type === 'success',
                outputPath: rawResult && rawResult.payload ? rawResult.payload.output_dir : null,
                error: rawResult && rawResult.type === 'error' ? (rawResult.payload ? rawResult.payload.message : '未知错误') : null
            };
            
            return result;
        } catch (error) {
            console.error(`提取APK资源失败: ${apkPath}`, error);
            throw error;
        }
    }

    /**
     * 获取APK基本信息
     */
    getApkBasicInfo(analysis) {
        if (!analysis) return null;

        return {
            packageName: analysis.packageName || analysis.package_name || 'Unknown',
            versionName: analysis.versionName || analysis.version_name || 'Unknown',
            versionCode: analysis.versionCode || analysis.version_code || 'Unknown',
            minSdkVersion: analysis.minSdkVersion || analysis.min_sdk_version || 'Unknown',
            targetSdkVersion: analysis.targetSdkVersion || analysis.target_sdk_version || 'Unknown',
            compileSdkVersion: analysis.compileSdkVersion || analysis.compile_sdk_version || 'Unknown',
            applicationLabel: analysis.applicationLabel || analysis.application_label || 'Unknown',
            fileSize: analysis.fileSize || analysis.file_size || 0,
            installLocation: analysis.installLocation || analysis.install_location || 'auto'
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
            // 直接调用 callBackendAPI
            const result = await unifiedAPI.call('apk.decompile', {
                file_path: filePath,
                options
            });
            
            const normalizedResult = {
                success: result && result.type === 'success',
                outputPath: result && result.payload ? result.payload.output_dir : null,
                error: result && result.type === 'error' ? (result.payload ? result.payload.message : '未知错误') : null
            };

            this.notifyListeners('decompile-progress', normalizedResult);
            return normalizedResult;
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
             const rawResult = await unifiedAPI.safeCall('recompileApk', projectPath, options);
            
             // 如果safeCall返回失败，尝试直接调用callBackendAPI
             if (rawResult && rawResult.success === false && rawResult.error && rawResult.error.includes('不可用')) {
                 const fallbackResult = await unifiedAPI.call('apk.recompile', {
                    project_path: projectPath,
                    options
                });
                
                const result = {
                    success: fallbackResult && fallbackResult.type === 'success',
                    outputPath: fallbackResult && fallbackResult.payload ? fallbackResult.payload.output_apk : null,
                    error: fallbackResult && fallbackResult.type === 'error' ? (fallbackResult.payload ? fallbackResult.payload.message : '未知错误') : null
                };
                
                this.notifyListeners('recompile-progress', result);
                return result;
            }
            
            const result = {
                success: rawResult && rawResult.type === 'success',
                outputPath: rawResult && rawResult.payload ? rawResult.payload.output_apk : null,
                error: rawResult && rawResult.type === 'error' ? (rawResult.payload ? rawResult.payload.message : '未知错误') : null
            };

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
            const rawResult = await unifiedAPI.safeCall('signApk', apkPath, keystore, options);
            
            // 如果safeCall返回失败，尝试直接调用callBackendAPI
            if (rawResult && rawResult.success === false && rawResult.error && rawResult.error.includes('不可用')) {
                 const fallbackResult = await unifiedAPI.call('apk.sign', {
                    apk_path: apkPath,
                    keystore,
                    options
                });
                
                 const result = {
                    success: fallbackResult && fallbackResult.type === 'success',
                    outputPath: fallbackResult && fallbackResult.payload ? fallbackResult.payload.apk_path : null,
                    error: fallbackResult && fallbackResult.type === 'error' ? (fallbackResult.payload ? fallbackResult.payload.message : '未知错误') : null
                };
                
                this.notifyListeners('sign-progress', result);
                return result;
            }

             const result = {
                success: rawResult && rawResult.type === 'success',
                outputPath: rawResult && rawResult.payload ? rawResult.payload.apk_path : null,
                error: rawResult && rawResult.type === 'error' ? (rawResult.payload ? rawResult.payload.message : '未知错误') : null
            };

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
            return await unifiedAPI.call('apk.get_progress', { task_id: taskId });
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
            return await unifiedAPI.call('apk.cancel_task', { task_id: taskId });
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
