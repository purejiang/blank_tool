// ==================== 设备相关API ====================
import { callBackendAPI } from '../core/callBackend';
import type { JsonObject } from '../../shared/ipc/protocol';

export const deviceApi = {
  // 设备列表获取
  getAdbDevices: () => callBackendAPI('adb.devices'),
  // ADB 远程连接
  adbConnect: (address: string) => callBackendAPI('adb.connect', { address }),
  adbDisconnect: (address?: string) => callBackendAPI('adb.disconnect', { address }),
  // 设备重启
  rebootDevice: (deviceId: string, mode?: string) => callBackendAPI('device.reboot', { device_id: deviceId, mode }),
  // 设备Shell命令执行
  executeShell: (deviceId: string, command: string) => callBackendAPI('device.shell', { device_id: deviceId, command }),
  // Logcat
  startLogcat: (deviceId: string) => callBackendAPI('adb.logcat', { device_id: deviceId }),
  stopLogcat: (processId: string) => callBackendAPI('adb.stop_logcat', { process_id: processId }),
  // 设备监控启动 (not in ApiMethodMap — string fallback)
  startDeviceMonitoring: () => callBackendAPI('device.monitor.start'),
  // 设备实时监控启动 (not in ApiMethodMap — string fallback)
  startRealtimeDeviceMonitoring: () => callBackendAPI('device.monitor.realtime'),
  // 设备实时监控停止 (not in ApiMethodMap — string fallback)
  stopRealtimeDeviceMonitoring: () => callBackendAPI('device.monitor.stop'),
  // 设备信息获取
  getDeviceInfo: (deviceId: string) => callBackendAPI('device.get_device_info', { device_id: deviceId }),
  // 设备安装apk、aab、apks
  installApk: (apkPath: string, deviceId: string, taskId?: string) => callBackendAPI('device.install_apk', { apk_path: apkPath, device_id: deviceId, task_id: taskId }),
  installAab: (aabPath: string, deviceId: string, taskId?: string) => callBackendAPI('device.install_aab', { aab_path: aabPath, device_id: deviceId, task_id: taskId }),
  installApks: (apksPath: string, deviceId: string, taskId?: string) => callBackendAPI('device.install_apks', { apks_path: apksPath, device_id: deviceId, task_id: taskId }),
  // 设备转换aab为apks
  convertAabToApks: (aabPath: string, deviceId: string) => callBackendAPI('device.convert_aab_to_apks', { aab_path: aabPath, device_id: deviceId }),
  // 设备卸载应用 (not in ApiMethodMap — string fallback)
  uninstallApp: (packageName: string, deviceId: string) => callBackendAPI('device.uninstall_app', { package_name: packageName, device_id: deviceId }),
  // 设备获取已安装应用 (param name mismatch: backend expects 'type', wrapper passes 'app_type')
  getInstalledApps: (deviceId: string, appType: string) =>
    callBackendAPI('device.get_installed_packages', { device_id: deviceId, type: appType }),
  // 设备导出应用APK 到指定目录
  exportApk: (packageName: string, deviceId: string, outputDir?: string) =>
    callBackendAPI('device.export_apk', { package_name: packageName, device_id: deviceId, output_dir: outputDir }),
  // 设备日志导出 (not in ApiMethodMap — string fallback)
  exportDeviceLog: (params: JsonObject) => callBackendAPI('log.export', params),
};
