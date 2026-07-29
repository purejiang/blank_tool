// ==================== APK相关 ====================
import { callBackendAPI } from '../core/callBackend';
import type { DecompileOptions, KeystoreConfig, RecompileOptions, SignOptions } from '../../shared/ipc/protocol';

export const apkApi = {
  // APK分析
  analyzeApk: (apkPath: string) => callBackendAPI('apk.analyze', { apk_path: apkPath }),
  // APK信息获取
  getApkInfo: (filePath: string) => callBackendAPI('apk.getInfo', { file_path: filePath }),
  // APK反编译
  decompileApk: (filePath: string, options?: DecompileOptions) =>
    callBackendAPI('apk.decompile', { file_path: filePath, options }),
  // APK重新编译
  recompileApk: (projectPath: string, options?: RecompileOptions) =>
    callBackendAPI('apk.recompile', { project_path: projectPath, options }),
  // APK签名
  signApk: (apkPath: string, keystore?: KeystoreConfig, options?: SignOptions) =>
    callBackendAPI('apk.sign', { apk_path: apkPath, keystore, options }),
  // APK任务进度获取
  getApkProgress: (taskId?: string) => callBackendAPI('apk.getProgress', { task_id: taskId }),
  // APK任务取消
  cancelApkTask: (taskId?: string) => callBackendAPI('apk.cancelTask', { task_id: taskId }),
};
