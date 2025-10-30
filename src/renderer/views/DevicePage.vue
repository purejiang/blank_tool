<template>
  <div class="page device-page">
    <div class="page-content responsive-two-column">
      <div class="left-panel">
        <!-- ADB 设备管理 -->
        <div class="section responsive-section">
          <h2><span class="section-icon">📱</span>ADB 设备管理</h2>
          <div class="form-group">
            <label>连接状态</label>
            <div class="status-row">
              <span 
                class="status-indicator" 
                :class="connectionStatus.connected ? 'status-connected' : 'status-disconnected'"
              ></span>
              <span>{{ connectionStatus.text }}</span>
            </div>
          </div>
          <div class="btn-group">
            <button class="btn btn-secondary" @click="refreshDevices">
              <span>🔄</span>手动刷新
            </button>
            <button class="btn btn-primary" @click="toggleMonitoring">
              <span>👁️</span>{{ isMonitoring ? '停止监听' : '开启实时监听' }}
            </button>
          </div>
          <div class="form-group">
            <label>选择设备</label>
            <select 
              class="form-control" 
              v-model="selectedDeviceId"
              :disabled="devices.length === 0"
              @change="handleDeviceSelection"
            >
              <option value="">{{ devices.length === 0 ? '请先刷新设备列表' : '请选择设备' }}</option>
              <option 
                v-for="device in devices" 
                :key="device.id" 
                :value="device.id"
              >
                {{ device.name}} ({{ device.id }}) - {{ device.status }}
              </option>
            </select>
          </div>
          
          <!-- 设备信息 -->
          <div class="form-group">
            <label>设备信息</label>
            <div class="device-info compact">
              <div v-if="!selectedDevice">
                <p class="placeholder">请选择设备以查看详细信息</p>
              </div>
              <div v-else>
                <div class="device-info-grid">
                  <div class="info-item">
                    <span class="info-label">设备ID:</span>
                    <span class="info-value">{{ selectedDevice.id }}</span>
                  </div>
                  <div class="info-item">
                    <span class="info-label">状态:</span>
                    <span class="info-value">{{ selectedDevice.status }}</span>
                  </div>
                  <div class="info-item" v-if="deviceInfo.model">
                    <span class="info-label">型号:</span>
                    <span class="info-value">{{ deviceInfo.model }}</span>
                  </div>
                  <div class="info-item" v-if="deviceInfo.brand">
                    <span class="info-label">品牌:</span>
                    <span class="info-value">{{ deviceInfo.brand }}</span>
                  </div>
                  <div class="info-item" v-if="deviceInfo.androidVersion">
                    <span class="info-label">Android版本:</span>
                    <span class="info-value">{{ deviceInfo.androidVersion }}</span>
                  </div>
                  <div class="info-item" v-if="deviceInfo.apiLevel">
                    <span class="info-label">API级别:</span>
                    <span class="info-value">{{ deviceInfo.apiLevel }}</span>
                  </div>
                  <div class="info-item" v-if="deviceInfo.batteryLevel !== undefined">
                    <span class="info-label">电池电量:</span>
                    <span class="info-value">{{ deviceInfo.batteryLevel }}%</span>
                  </div>
                  <div class="info-item" v-if="deviceInfo.screenResolution">
                    <span class="info-label">屏幕分辨率:</span>
                    <span class="info-value">{{ deviceInfo.screenResolution }}</span>
                  </div>
                  <div class="info-item" v-if="deviceInfo.architecture">
                    <span class="info-label">架构:</span>
                    <span class="info-value">{{ deviceInfo.architecture }}</span>
                  </div>
                  <div class="info-item" v-if="deviceInfo.totalMemory">
                    <span class="info-label">总内存:</span>
                    <span class="info-value">{{ deviceInfo.totalMemory }}</span>
                  </div>
                  <div class="info-item" v-if="deviceInfo.totalStorage">
                    <span class="info-label">总存储:</span>
                    <span class="info-value">{{ deviceInfo.totalStorage }}</span>
                  </div>
                  <div class="info-item" v-if="deviceInfo.availableStorage">
                    <span class="info-label">可用存储:</span>
                    <span class="info-value">{{ deviceInfo.availableStorage }}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 设备操作 -->
        <div class="section">
          <h2><span class="section-icon">⚙️</span>设备操作</h2>
          <div class="btn-group">
            <button 
              class="btn btn-secondary" 
              :disabled="!selectedDevice"
              @click="rebootDevice('normal')"
            >
              <span>🔄</span>重启设备
            </button>
            <button 
              class="btn btn-warning" 
              :disabled="!selectedDevice"
              @click="rebootDevice('recovery')"
            >
              <span>🛠️</span>重启到Recovery
            </button>
            <button 
              class="btn btn-danger" 
              :disabled="!selectedDevice"
              @click="rebootDevice('bootloader')"
            >
              <span>⚡</span>重启到Bootloader
            </button>
          </div>
          <div class="form-group">
            <label>Shell 命令</label>
            <div class="shell-input-group">
              <input 
                type="text" 
                class="form-control" 
                v-model="shellCommand"
                placeholder="输入 ADB shell 命令" 
                :disabled="!selectedDevice"
                @keyup.enter="executeShellCommand"
              >
              <button 
                class="btn btn-primary" 
                :disabled="!selectedDevice || !shellCommand.trim()"
                @click="executeShellCommand"
              >
                <span>▶️</span>执行
              </button>
            </div>
          </div>
          <div v-if="shellOutput" class="shell-output">
            <pre>{{ shellOutput }}</pre>
          </div>
        </div>
      </div>

      <div class="right-panel">
        <!-- 应用管理 -->
        <div class="section">
          <h2><span class="section-icon">📦</span>应用管理</h2>
          <div class="form-group">
            <label>应用类型</label>
            <select 
              class="form-control" 
              v-model="appType"
              :disabled="!selectedDevice"
              @change="refreshAppList"
            >
              <option value="all">所有应用</option>
              <option value="system">系统应用</option>
              <option value="user">用户应用</option>
              <option value="enabled">已启用应用</option>
              <option value="disabled">已禁用应用</option>
            </select>
          </div>
          <div class="btn-group">
            <button 
              class="btn btn-secondary" 
              :disabled="!selectedDevice"
              @click="refreshAppList"
            >
              <span>🔄</span>刷新应用列表
            </button>
            <button 
              class="btn btn-primary" 
              :disabled="!selectedDevice || apps.length === 0"
              @click="exportAppList"
            >
              <span>📄</span>导出应用列表
            </button>
          </div>
          <div class="app-list" v-if="apps.length > 0">
            <div class="app-list-header">
              <span>包名</span>
              <span>操作</span>
            </div>
            <div class="app-list-content">
              <div 
                 v-for="app in apps" 
                 :key="app" 
                 class="app-item"
               >
                 <div class="app-package" :title="app">
                   {{ app }}
                   <span 
                     v-if="appExportStatus[app]" 
                     class="export-status"
                     :class="appExportStatus[app].status"
                     @click="openExportPath(app)"
                   >
                     <span v-if="appExportStatus[app].status === 'exporting'">⏳</span>
                     <span v-else-if="appExportStatus[app].status === 'exported'">✅</span>
                     {{ appExportStatus[app].text }}
                   </span>
                 </div>
                 <div class="app-actions">
                   <button 
                     class="btn btn-sm btn-secondary" 
                     @click="copyPackageName(app)"
                     title="复制包名"
                   >
                     📋
                   </button>
                   <button 
                     class="btn btn-sm btn-primary" 
                     @click="exportApk(app)"
                     title="导出APK"
                     :disabled="appExportStatus[app]?.status === 'exporting'"
                   >
                     <span v-if="appExportStatus[app]?.status === 'exporting'">⏳</span>
                     <span v-else>📦</span>
                   </button>
                   <button 
                     class="btn btn-sm btn-danger" 
                     @click="uninstallApp(app)"
                     title="卸载应用"
                     v-if="app.type !== 'system'"
                   >
                     🗑️
                   </button>
                 </div>
               </div>
            </div>
          </div>
          <div v-else-if="selectedDevice" class="placeholder">
            <p>暂无应用数据，请点击刷新应用列表</p>
          </div>
        </div>

        <!-- 设备日志 -->
        <div class="section">
          <h2><span class="section-icon">📋</span>设备日志</h2>
          <div class="btn-group">
            <button 
              class="btn btn-primary" 
              :disabled="!selectedDevice"
              @click="isLogcatRunning ? stopLogcat() : startLogcat()"
            >
              <span>{{ isLogcatRunning ? '⏹️' : '▶️' }}</span>
              {{ isLogcatRunning ? '停止日志' : '开始日志' }}
            </button>
            <button 
              class="btn btn-secondary" 
              :disabled="deviceLogs.length === 0"
              @click="clearDeviceLog"
            >
              <span>🗑️</span>清空日志
            </button>
            <button 
              class="btn btn-secondary" 
              :disabled="deviceLogs.length === 0"
              @click="exportDeviceLog"
            >
              <span>📄</span>导出日志
            </button>
          </div>
          <div class="log-container">
            <div 
              v-for="(log, index) in displayedLogs" 
              :key="index"
              class="log-entry"
              :class="'log-' + log.level.toLowerCase()"
            >
              <span class="log-time">{{ log.time }}</span>
              <span class="log-level">{{ log.level }}</span>
              <span class="log-tag">{{ log.tag }}</span>
              <span class="log-message">{{ log.message }}</span>
            </div>
          </div>
        </div>
      </div>
     </div>
     
     <!-- 导出成功弹窗 -->
     <div v-if="showExportModal" class="export-success-modal" @click="closeExportModal">
       <div class="export-success-content" @click.stop>
         <div class="export-success-header">
           <span class="export-success-icon">✅</span>
           <h3 class="export-success-title">导出成功</h3>
         </div>
         <div class="export-success-body">
           <p>APK文件已成功导出到以下路径：</p>
           <div class="export-path">{{ exportModalData.path }}</div>
         </div>
         <div class="export-success-actions">
           <button class="btn btn-secondary" @click="closeExportModal">关闭</button>
           <button class="btn btn-primary" @click="openExportFolder">打开文件夹</button>
         </div>
       </div>
     </div>
   </div>
 </template>

<script>
import { ref, reactive, computed, inject, onMounted, onUnmounted, watch } from 'vue'
import { useDeviceStore } from '../stores'

export default {
  name: 'DevicePage',
  setup() {
    // 注入服务
    const deviceService = inject('deviceService')
    const notificationService = inject('notificationService')

    // 初始化设备 store
    const deviceStore = useDeviceStore()

    // 使用全局设备状态
    const devices = computed(() => deviceStore.devices.value)
    const selectedDevice = computed(() => deviceStore.currentDevice.value)
    const deviceInfo = computed(() => deviceStore.deviceInfo)
    const isMonitoring = computed(() => deviceStore.isMonitoring.value)
    const selectedDeviceId = ref('')

    // 本地状态
     const isLogcatRunning = ref(false)
     const deviceLogs = ref([])
     const apps = ref([])
     const appType = ref('all')
     const shellCommand = ref('')
     const shellOutput = ref('')
     const appExportStatus = ref({}) // 应用导出状态
     const showExportModal = ref(false) // 导出成功弹窗
     const exportModalData = ref({ path: '', packageName: '' }) // 弹窗数据

    const connectionStatus = reactive({
      connected: false,
      text: '未连接'
    })

    // 计算属性
    const displayedLogs = computed(() => {
      return deviceLogs.value.slice(-100) // 只显示最新的100条日志
    })

    // 监听全局设备状态变化
    watch(() => deviceStore.currentDevice.value, (newDevice) => {
      if (newDevice) {
        selectedDeviceId.value = newDevice.id
        // 自动获取设备详细信息
        getAndDisplayDeviceInfo(newDevice.id)
      } else {
        selectedDeviceId.value = ''
      }
    }, { immediate: true })

    // 工具方法
    const updateConnectionStatus = (connected, text) => {
      connectionStatus.connected = connected
      connectionStatus.text = text
    }

    const showSuccess = (title, message = '') => {
      if (notificationService) {
        notificationService.success(title, message)
      }
    }

    const showError = (title, message = '') => {
      if (notificationService) {
        notificationService.error(title, message)
      }
    }

    // 监听设备列表变化，更新连接状态
    watch(() => deviceStore.devices.value, (newDevices) => {
      updateConnectionStatus(
        newDevices.length > 0, 
        newDevices.length > 0 ? `已连接 ${newDevices.length} 个设备` : '未发现设备'
      )
    }, { immediate: true })

    // 设备管理方法
    const refreshDevices = async () => {
      try {
        await deviceService.getAdbDevices()
      } catch (error) {
        console.error('刷新设备列表错误:', error)
        showError('刷新设备列表失败', error.message)
      }
    }

    const selectDevice = async (device) => {
      try {
        await deviceService.selectDevice(device.id)
        await getAndDisplayDeviceInfo(device.id)
      } catch (error) {
        console.error('选择设备错误:', error)
        showError('选择设备失败', error.message)
      }
    }

    const handleDeviceSelection = async (event) => {
      const deviceId = event.target.value
      if (!deviceId) {
        return
      }
      
      try {
        const device = devices.value.find(d => d.id === deviceId)
        if (device) {
          await selectDevice(device)
        } else {
          showError('设备未找到', `无法找到设备ID: ${deviceId}`)
        }
      } catch (error) {
        console.error('处理设备选择错误:', error)
        showError('选择设备失败', error.message)
      }
    }

    const getAndDisplayDeviceInfo = async (deviceId) => {
      if (!deviceId) return
      
      try {
        await deviceService.getDeviceInfo(deviceId)
      } catch (error) {
        console.error('获取设备信息错误:', error)
        showError('获取设备信息失败', error.message)
      }
    }

    const toggleMonitoring = async () => {
      try {
        if (isMonitoring.value) {
          await deviceService.stopDeviceMonitoring()
        } else {
          await deviceService.startDeviceMonitoring()
        }
      } catch (error) {
        console.error('切换监控状态错误:', error)
        showError('切换监控状态失败', error.message)
      }
    }

    // 设备操作方法
    const rebootDevice = async () => {
      if (!selectedDevice.value) {
        showError('请先选择设备')
        return
      }

      try {
        const result = await deviceService.callBackendAPI('device.reboot', {
          device_id: selectedDevice.value.id
        })
        
        if (result.success) {
          showSuccess('设备重启命令已发送')
        } else {
          showError('设备重启失败', result.error)
        }
      } catch (error) {
        console.error('设备重启错误:', error)
        showError('设备重启失败', error.message)
      }
    }

    const executeShellCommand = async () => {
      if (!selectedDevice.value || !shellCommand.value.trim()) {
        showError('请先选择设备并输入命令')
        return
      }

      try {
        const result = await deviceService.callBackendAPI('device.shell', {
          device_id: selectedDevice.value.id,
          command: shellCommand.value
        })
        
        if (result.success) {
          shellOutput.value = result.output || '命令执行完成'
          showSuccess('命令执行成功')
        } else {
          shellOutput.value = result.error || '命令执行失败'
          showError('命令执行失败', result.error)
        }
      } catch (error) {
        console.error('执行Shell命令错误:', error)
        shellOutput.value = error.message
        showError('命令执行失败', error.message)
      }
    }

    // 应用管理方法
    const refreshAppList = async () => {
      if (!selectedDevice.value) {
        showError('请先选择设备')
        return
      }

      try {
        const result = await deviceService.getInstalledApps(selectedDevice.value.id, appType.value)
        if (result.success) {
          apps.value = result.packages || []
          console.log('获取到的应用列表:', apps.value)
          showSuccess(`已获取 ${apps.value.length} 个应用`)
        } else {
          showError('获取应用列表失败', result.error)
        }
      } catch (error) {
        console.error('获取应用列表错误:', error)
        showError('获取应用列表失败', error.message)
      }
    }

    const copyPackageName = (packageName) => {
      navigator.clipboard.writeText(packageName).then(() => {
        showSuccess('包名已复制到剪贴板')
      }).catch(error => {
        console.error('复制失败:', error)
        showError('复制失败')
      })
    }

    const exportApk = async (packageName) => {
       if (!selectedDevice.value) {
         showError('请先选择设备')
         return
       }

       try {
         // 设置导出状态为进行中
         appExportStatus.value[packageName] = {
           status: 'exporting',
           text: '导出中...'
         }

         const result = await deviceService.exportApk(
           packageName, 
           selectedDevice.value.id, 
           './exports'
         )
         
         if (result.success) {
           // 设置导出状态为已完成
           appExportStatus.value[packageName] = {
             status: 'exported',
             text: '已导出',
             path: result.output_path
           }
           
           // 显示导出成功弹窗
           exportModalData.value = {
             path: result.output_path,
             packageName: packageName
           }
           showExportModal.value = true
           
           showSuccess('APK导出成功', result.output_path)
         } else {
           // 清除导出状态
           delete appExportStatus.value[packageName]
           showError('APK导出失败', result.error)
         }
       } catch (error) {
         // 清除导出状态
         delete appExportStatus.value[packageName]
         console.error('导出APK错误:', error)
         showError('APK导出失败', error.message)
       }
     }

     // 导出弹窗相关方法
     const closeExportModal = () => {
       showExportModal.value = false
       exportModalData.value = { path: '', packageName: '' }
     }

     const openExportFolder = async () => {
       try {
         // 使用 Electron API 打开文件夹
         if (electronAPIService.isAvailable && electronAPIService.api.openPath) {
           await electronAPIService.api.openPath(exportModalData.value.path)
         } else {
           // 备用方案：复制路径到剪贴板
           await navigator.clipboard.writeText(exportModalData.value.path)
           showSuccess('文件路径已复制到剪贴板')
         }
         closeExportModal()
       } catch (error) {
         console.error('打开文件夹错误:', error)
         showError('无法打开文件夹', error.message)
       }
     }

     const openExportPath = (packageName) => {
       const exportStatus = appExportStatus.value[packageName]
       if (exportStatus && exportStatus.status === 'exported' && exportStatus.path) {
         exportModalData.value = {
           path: exportStatus.path,
           packageName: packageName
         }
         showExportModal.value = true
       }
     }

    const uninstallApp = async (packageName) => {
      if (!selectedDevice.value) {
        showError('请先选择设备')
        return
      }

      try {
        const result = await deviceService.uninstallApp(packageName, selectedDevice.value.id)
        if (result.success) {
          showSuccess('应用卸载成功')
          // 刷新应用列表
          await refreshAppList()
        } else {
          showError('应用卸载失败', result.error)
        }
      } catch (error) {
        console.error('卸载应用错误:', error)
        showError('卸载应用失败', error.message)
      }
    }

    const exportAppList = async () => {
      if (!selectedDevice.value || apps.value.length === 0) {
        showError('请先选择设备并获取应用列表')
        return
      }

      try {
        const appListText = apps.value.map(app => 
          `${app}`
        ).join('\n')
        
        await navigator.clipboard.writeText(appListText)
        showSuccess('应用列表已复制到剪贴板')
      } catch (error) {
        console.error('导出应用列表错误:', error)
        showError('导出应用列表失败', error.message)
      }
    }

    // 日志管理方法
    const startLogcat = async () => {
      if (!selectedDevice.value) {
        showError('请先选择设备')
        return
      }

      try {
        const result = await deviceService.startLogcat({
          device_id: selectedDevice.value.id,
          filter: '',
          clear: true
        })
        
        if (result.success) {
          isLogcatRunning.value = true
          showSuccess('Logcat已启动')
        } else {
          showError('启动Logcat失败', result.error)
        }
      } catch (error) {
        console.error('启动Logcat错误:', error)
        showError('启动Logcat失败', error.message)
      }
    }

    const stopLogcat = async () => {
      try {
        const result = await deviceService.stopLogcat()
        if (result.success) {
          isLogcatRunning.value = false
          showSuccess('Logcat已停止')
        } else {
          showError('停止Logcat失败', result.error)
        }
      } catch (error) {
        console.error('停止Logcat错误:', error)
        showError('停止Logcat失败', error.message)
      }
    }

    const clearDeviceLog = () => {
      deviceLogs.value = []
      showSuccess('日志已清空')
    }

    const exportDeviceLog = async () => {
      if (deviceLogs.value.length === 0) {
        showError('没有日志可导出')
        return
      }

      try {
        const logText = deviceLogs.value.map(log => 
          `${log.time} ${log.level}/${log.tag}: ${log.message}`
        ).join('\n')
        
        await navigator.clipboard.writeText(logText)
        showSuccess('日志已复制到剪贴板')
      } catch (error) {
        console.error('导出日志错误:', error)
        showError('导出日志失败', error.message)
      }
    }

    // 生命周期
    onMounted(async () => {
      try {
        // 获取设置服务
        const settingsService = inject('settingsService')
        if (settingsService) {
          const settings = await settingsService.loadSettings()
          
          // 根据设置决定是否自动刷新设备列表
          if (settings.autoDetectDevices) {
            console.log('启动时自动刷新设备已启用')
            await refreshDevices()
          } else {
            console.log('启动时自动刷新设备未启用')
          }
          
          // 根据设置决定是否启用设备监控
          if (settings.enableDeviceMonitoring) {
            console.log('设备监控已启用')
            // 监听设备变化事件
            deviceService.onDeviceChange((eventData) => {
                console.log('设备状态变化:', eventData)
                refreshDevices()
              })
            }
          
        } else {
          // 如果无法获取设置服务，使用默认行为
          console.warn('无法获取设置服务，使用默认行为')
          await refreshDevices()
        }
      } catch (error) {
        console.error('加载设置失败，使用默认行为:', error)
        await refreshDevices()
      }
      
      // 页面加载时自动获取当前选中设备的详细信息
      if (selectedDevice.value) {
        await getAndDisplayDeviceInfo(selectedDevice.value.id)
      }

      // 监听日志输出事件
      deviceService.onLogcatOutput((logData) => {
          deviceLogs.value.push({
            time: new Date().toLocaleTimeString(),
            level: logData.level || 'I',
            tag: logData.tag || 'Unknown',
            message: logData.message || ''
          })
          
          // 限制日志数量，避免内存溢出
          if (deviceLogs.value.length > 1000) {
            deviceLogs.value = deviceLogs.value.slice(-500)
          }
        })
    })

    // 生命周期
    onMounted(async () => {
      // 页面加载时自动获取当前选中设备的详细信息
      if (selectedDevice.value) {
        await getAndDisplayDeviceInfo(selectedDevice.value.id)
      }
      
      // 监听设备变化事件
      deviceService.onDeviceChange((eventData) => {
          console.log('设备状态变化:', eventData)
          refreshDevices()
        })
      

      // 监听日志输出事件
      deviceService.onLogcatOutput((logData) => {
          deviceLogs.value.push({
            time: new Date().toLocaleTimeString(),
            level: logData.level || 'I',
            tag: logData.tag || 'Unknown',
            message: logData.message || ''
          })
          
          // 限制日志数量，避免内存溢出
          if (deviceLogs.value.length > 1000) {
            deviceLogs.value = deviceLogs.value.slice(-500)
          }
        })
    })

    onUnmounted(() => {
      // 清理监听器
      if (isLogcatRunning.value) {
        stopLogcat()
      }
    })

    return {
       devices,
       selectedDeviceId,
       selectedDevice,
       deviceInfo,
       isMonitoring,
       isLogcatRunning,
       deviceLogs,
       displayedLogs,
       apps,
       appType,
       shellCommand,
       shellOutput,
       connectionStatus,
       appExportStatus,
       showExportModal,
       exportModalData,
       refreshDevices,
       selectDevice,
       handleDeviceSelection,
       toggleMonitoring,
       rebootDevice,
       executeShellCommand,
       refreshAppList,
       copyPackageName,
       exportApk,
       uninstallApp,
       exportAppList,
       startLogcat,
       stopLogcat,
       clearDeviceLog,
       exportDeviceLog,
       closeExportModal,
       openExportFolder,
       openExportPath
     }
  }
}
</script>

<style scoped>
/* DevicePage组件特殊样式 */
.device-page .section h2 {
  border-bottom: 1px solid var(--border-light);
  padding-bottom: var(--spacing-sm);
}

.device-page .section-icon {
  font-size: var(--font-size-xl);
}

/* 设备选择下拉框特殊样式 */
#deviceSelect {
  background-image: url("data:image/svg+xml,%3csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 20 20'%3e%3cpath stroke='%236b7280' stroke-linecap='round' stroke-linejoin='round' stroke-width='1.5' d='m6 8 4 4 4-4'/%3e%3c/svg%3e");
  background-position: right 0.5rem center;
  background-repeat: no-repeat;
  background-size: 1.5em 1.5em;
  padding-right: 2.5rem;
  appearance: none;
  cursor: pointer;
}

#deviceSelect:disabled {
  cursor: not-allowed;
  background-image: url("data:image/svg+xml,%3csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 20 20'%3e%3cpath stroke='%9ca3af' stroke-linecap='round' stroke-linejoin='round' stroke-width='1.5' d='m6 8 4 4 4-4'/%3e%3c/svg%3e");
}

#deviceSelect option {
  padding: var(--spacing-sm);
  background-color: var(--bg-primary);
  color: var(--text-primary);
}

#deviceSelect:focus {
  border-color: var(--primary-color);
  box-shadow: 0 0 0 0.2rem rgba(var(--primary-color-rgb), 0.25);
}

/* 日志容器样式 - 使用全局样式变量 */
.log-container {
  max-height: 300px;
  overflow-y: auto;
  border: 1px solid var(--border-color);
  padding: var(--spacing-md);
  background: var(--bg-secondary);
  font-family: var(--font-family-monospace);
  font-size: var(--font-size-sm);
  border-radius: var(--border-radius);
}

.log-entry {
  margin-bottom: 2px;
  padding: 2px 0;
}

.log-time {
  color: var(--text-muted);
  margin-right: var(--spacing-sm);
}

.log-level {
  margin-right: var(--spacing-sm);
  font-weight: 500;
}

.log-verbose { color: var(--text-muted); }
.log-debug { color: var(--info-color); }
.log-info { color: var(--success-color); }
.log-warn { color: var(--warning-color); }
.log-error { color: var(--danger-color); }
.log-fatal { 
  color: var(--danger-color); 
  font-weight: bold; 
}

.log-tag {
  color: var(--primary-color);
  margin-right: var(--spacing-sm);
  font-weight: 500;
}

.log-message {
  color: var(--text-primary);
}

/* 设备信息网格 - 使用全局样式变量 */
.device-info-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: var(--spacing-md);
  margin-top: var(--spacing-md);
}

.info-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-sm) 0;
  border-bottom: 1px solid var(--border-light);
}

.info-item:last-child {
  border-bottom: none;
}

.info-label {
  font-weight: 500;
  color: var(--text-secondary);
}

.info-value {
  color: var(--text-primary);
  font-family: var(--font-family-monospace);
  font-size: var(--font-size-sm);
}

/* 应用列表优化布局 */
.app-list {
  margin-top: var(--spacing-md);
  border: 1px solid var(--border-color);
  border-radius: var(--border-radius);
  overflow: hidden;
}

/* 应用列表头部 - 优化对齐 */
.app-list-header {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: var(--spacing-md);
  padding: var(--spacing-md);
  background: var(--bg-tertiary);
  border-bottom: 1px solid var(--border-color);
  font-weight: 500;
  color: var(--text-secondary);
  font-size: var(--font-size-sm);
  align-items: center;
}

/* 应用列表内容 */
.app-list-content {
  max-height: 400px;
  overflow-y: auto;
}

/* 应用项 - 优化布局和对齐 */
.app-item {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: var(--spacing-md);
  padding: var(--spacing-md);
  border-bottom: 1px solid var(--border-light);
  align-items: center;
  transition: background-color 0.2s ease;
}

.app-item:last-child {
  border-bottom: none;
}

.app-item:hover {
  background: var(--bg-hover);
}

.app-package {
  font-family: var(--font-family-monospace);
  font-size: var(--font-size-sm);
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}

/* 导出状态指示器 */
.export-status {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: var(--font-size-xs);
  padding: 2px 6px;
  border-radius: 12px;
  font-weight: 500;
}

.export-status.exporting {
  background: var(--warning-color-light);
  color: var(--warning-color);
}

.export-status.exported {
  background: var(--success-color-light);
  color: var(--success-color);
  cursor: pointer;
}

.export-status.exported:hover {
  background: var(--success-color);
  color: white;
}

/* 应用操作按钮组 - 优化对齐和间距 */
.app-actions {
  display: flex;
  gap: 6px; /* 小按钮间距稍小 */
  align-items: center;
  justify-content: flex-end;
}

.app-actions .btn {
  min-width: 32px;
  height: 32px;
  padding: 4px 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--border-radius-sm);
}

/* Shell输入组 */
.shell-input-group {
  display: flex;
  gap: var(--spacing-sm);
  margin-top: var(--spacing-md);
}

.shell-input-group input {
  flex: 1;
}

/* Shell输出 */
.shell-output {
  margin-top: var(--spacing-md);
  max-height: 200px;
  overflow-y: auto;
  border: 1px solid var(--border-color);
  border-radius: var(--border-radius);
  background: var(--bg-secondary);
}

.shell-output pre {
  margin: 0;
  padding: var(--spacing-md);
  font-family: var(--font-family-monospace);
  font-size: var(--font-size-sm);
  color: var(--text-primary);
  white-space: pre-wrap;
  word-break: break-all;
}
</style>