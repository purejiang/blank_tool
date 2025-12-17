<template>
  <div class="page settings-page">
    <div class="page-content responsive-two-column">
      <div class="left-panel">
        <!-- 常规设置 -->
        <div class="section responsive-section">
          <div class="section-header">
            <h2><span class="section-icon">⚙️</span>常规设置</h2>
            <div class="section-actions">
              <button class="btn btn-sm btn-primary" @click="saveGeneralSettings" data-tooltip="保存当前设置">
                <span>💾</span>
              </button>
              <button class="btn btn-sm btn-secondary" @click="resetGeneralSettings" data-tooltip="重置为默认值">
                <span>🔄</span>
              </button>
            </div>
          </div>
          <div class="settings-group">
            <div class="form-group">
              <label class="form-label" for="language">界面语言</label>
              <select id="language" class="form-control" v-model="settings.language" @change="onSettingChange">
                <option value="zh-CN">简体中文</option>
                <option value="en-US">English</option>
              </select>
              <p class="form-text">选择应用界面显示语言</p>
            </div>
            <div class="form-group">
              <label class="form-label" for="theme">主题设置</label>
              <select id="theme" class="form-control" v-model="settings.theme" @change="onSettingChange">
                <option value="auto">跟随系统</option>
                <option value="light">浅色主题</option>
                <option value="dark">深色主题</option>
              </select>
              <p class="form-text">选择应用主题外观</p>
            </div>
            <div class="form-group">
              <div class="form-check">
                <input type="checkbox" id="autoSave" class="form-check-input" v-model="settings.autoSave"
                  @change="onSettingChange">
                <label class="form-check-label" for="autoSave">
                  自动保存
                </label>
              </div>
              <p class="form-text">自动保存配置和工作状态</p>
            </div>
            <div class="form-group">
              <div class="form-check">
                <input type="checkbox" id="enableNotifications" class="form-check-input"
                  v-model="settings.enableNotifications" @change="onSettingChange">
                <label class="form-check-label" for="enableNotifications">
                  启用通知
                </label>
              </div>
              <p class="form-text">显示操作完成和错误通知</p>
            </div>
          </div>
        </div>

        <!-- 开发工具 -->
        <div class="section">
          <div class="section-header">
            <h2><span class="section-icon">🛠️</span>开发工具</h2>
            <div class="section-actions">
              <span class="toggle-desc">系统查找</span>
              <div class="toggle-switch-container" :data-tooltip="systemSearchEnabled ? '关闭系统查找' : '开启系统查找'">
                <label class="toggle-switch">
                  <input type="checkbox" :checked="systemSearchEnabled" @change="toggleSystemSearch">
                  <span class="toggle-slider"></span>
                </label>
              </div>
              <button class="btn btn-sm btn-secondary" @click="refreshTools" :disabled="isLoadingTools"
                data-tooltip="重新检测工具">
                <span>🔄</span>
              </button>
            </div>
          </div>
          <div class="tool-grid">
            <div class="tool-card" v-for="tool in tools" :key="tool.key">
              <div class="tool-card-header">
                <div class="tool-name">{{ tool.fullName }}</div>
                <div class="tool-status">
                  <span :class="['status-badge', tool.status === 'available' ? 'status-ok' : 'status-bad']">
                    {{ tool.status === 'available' ? '可用' : '不可用' }}
                  </span>
                  <span v-if="tool.needsUpdate" class="update-badge">需要更新</span>
                </div>
              </div>
              <div class="tool-card-body">
                <div class="tool-field">
                  <span class="field-label">版本</span>
                  <span class="field-value">{{ tool.version || '未知' }}</span>
                  <button class="btn btn-sm btn-secondary" @click="checkVersion(tool.key)"
                    data-tooltip="手动刷新">🔄</button>
                </div>
                <div class="tool-field">
                  <span class="field-label">路径</span>
                  <span class="field-value path-text" :title="tool.path || '未配置'">
                    {{ tool.path || '未配置' }}
                  </span>
                  <button class="btn btn-sm btn-secondary" @click="copyText(tool.path)"
                    :disabled="!tool.path">复制</button>
                  <button class="btn btn-sm btn-secondary" @click="browseToolExecutable(tool.key)">更改</button>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 输出设置 -->
        <div class="section">
          <div class="section-header">
            <h2><span class="section-icon">📁</span>输出设置</h2>
            <div class="section-actions">
              <button class="btn btn-sm btn-primary" @click="saveOutputSettings" data-tooltip="保存输出设置">
                <span>💾</span>
              </button>
              <button class="btn btn-sm btn-secondary" @click="resetOutputSettings" data-tooltip="重置输出设置">
                <span>🔄</span>
              </button>
            </div>
          </div>
          <div class="settings-group">
            <div class="form-group">
              <label class="form-label" for="outputDirectory">输出目录</label>
              <div class="path-input-group">
                <input type="text" id="outputDirectory" class="form-control" v-model="settings.outputDirectory"
                  placeholder="选择输出目录" @change="onSettingChange">
                <button class="btn btn-secondary path-browse-btn" @click="browseDirectory('outputDirectory')">
                  浏览
                </button>
              </div>
              <p class="form-text">APK分析和处理结果的输出目录</p>
            </div>
            <div class="form-group">
              <div class="form-check">
                <input type="checkbox" id="keepOriginalStructure" class="form-check-input"
                  v-model="settings.keepOriginalStructure" @change="onSettingChange">
                <label class="form-check-label" for="keepOriginalStructure">
                  保持原始目录结构
                </label>
              </div>
              <p class="form-text">在输出时保持APK的原始目录结构</p>
            </div>
            <div class="form-group">
              <div class="form-check">
                <input type="checkbox" id="compressOutput" class="form-check-input" v-model="settings.compressOutput"
                  @change="onSettingChange">
                <label class="form-check-label" for="compressOutput">
                  压缩输出文件
                </label>
              </div>
              <p class="form-text">自动压缩输出的文件和目录</p>
            </div>
          </div>
        </div>

        <!-- 设备连接设置 -->
        <div class="section">
          <div class="section-header">
            <h2><span class="section-icon">📱</span>设备连接设置</h2>
            <div class="section-actions">
              <button class="btn btn-sm btn-primary" @click="saveDeviceSettings" data-tooltip="保存设备连接设置">
                <span>💾</span>
              </button>
              <button class="btn btn-sm btn-secondary" @click="resetDeviceSettings" data-tooltip="重置设备连接设置">
                <span>🔄</span>
              </button>
            </div>
          </div>
          <div class="settings-group">
            <div class="form-group">
              <label class="form-label" for="connectionTimeout">连接超时时间 (毫秒)</label>
              <input type="number" id="connectionTimeout" class="form-control"
                v-model.number="settings.connectionTimeout" min="1000" max="60000" step="1000"
                @change="onSettingChange">
              <p class="form-text">ADB设备连接的超时时间，建议设置为10-30秒</p>
            </div>
            <div class="form-group">
              <label class="form-label" for="commandTimeout">命令超时时间 (毫秒)</label>
              <input type="number" id="commandTimeout" class="form-control" v-model.number="settings.commandTimeout"
                min="5000" max="120000" step="5000" @change="onSettingChange">
              <p class="form-text">ADB命令执行的超时时间，建议设置为30-60秒</p>
            </div>
            <div class="form-group">
              <label class="form-label" for="retryCount">重试次数</label>
              <input type="number" id="retryCount" class="form-control" v-model.number="settings.retryCount" min="0"
                max="10" @change="onSettingChange">
              <p class="form-text">连接失败时的重试次数，0表示不重试</p>
            </div>
            <div class="form-group">
              <label class="form-label" for="retryDelay">重试间隔 (毫秒)</label>
              <input type="number" id="retryDelay" class="form-control" v-model.number="settings.retryDelay" min="500"
                max="10000" step="500" @change="onSettingChange">
              <p class="form-text">重试之间的等待时间</p>
            </div>
            <div class="form-group">
              <label class="form-label" for="monitorInterval">监控间隔 (毫秒)</label>
              <input type="number" id="monitorInterval" class="form-control" v-model.number="settings.monitorInterval"
                min="1000" max="30000" step="1000" @change="onSettingChange">
              <p class="form-text">设备状态监控的刷新间隔</p>
            </div>
            <div class="form-group">
              <div class="form-check">
                <input type="checkbox" id="autoDetectDevices" class="form-check-input"
                  v-model="settings.autoDetectDevices" @change="onSettingChange">
                <label class="form-check-label" for="autoDetectDevices">
                  自动检测设备
                </label>
              </div>
              <p class="form-text">启动时自动检测并连接ADB设备</p>
            </div>
            <div class="form-group">
              <div class="form-check">
                <input type="checkbox" id="enableDeviceMonitoring" class="form-check-input"
                  v-model="settings.enableDeviceMonitoring" @change="onSettingChange">
                <label class="form-check-label" for="enableDeviceMonitoring">
                  启用设备监控
                </label>
              </div>
              <p class="form-text">实时监控设备连接状态变化</p>
            </div>
            <div class="form-group">
              <div class="form-check">
                <input type="checkbox" id="autoReconnect" class="form-check-input" v-model="settings.autoReconnect"
                  @change="onSettingChange">
                <label class="form-check-label" for="autoReconnect">
                  自动重连
                </label>
              </div>
              <p class="form-text">设备断开连接时自动尝试重新连接</p>
            </div>
          </div>
        </div>
      </div>

      <div class="right-panel">
        <!-- 工具超时设置 -->
        <div class="section">
          <div class="section-header">
            <h2><span class="section-icon">⏱️</span>工具超时设置</h2>
            <div class="section-actions">
              <button class="btn btn-sm btn-primary" @click="saveTimeoutSettings" data-tooltip="保存超时设置">
                <span>💾</span>
              </button>
              <button class="btn btn-sm btn-secondary" @click="resetTimeoutSettings" data-tooltip="重置超时设置">
                <span>🔄</span>
              </button>
            </div>
          </div>
          <div class="settings-group">
            <div class="form-group">
              <label class="form-label" for="adbTimeout">ADB 超时时间 (毫秒)</label>
              <input type="number" id="adbTimeout" class="form-control" v-model.number="settings.adbTimeout" min="10000"
                max="300000" step="5000" @change="onSettingChange">
              <p class="form-text">ADB操作的超时时间</p>
            </div>
            <div class="form-group">
              <label class="form-label" for="apktoolTimeout">APKTool 超时时间 (毫秒)</label>
              <input type="number" id="apktoolTimeout" class="form-control" v-model.number="settings.apktoolTimeout"
                min="30000" max="600000" step="10000" @change="onSettingChange">
              <p class="form-text">APKTool反编译/重打包的超时时间</p>
            </div>
            <div class="form-group">
              <label class="form-label" for="bundletoolTimeout">BundleTool 超时时间 (毫秒)</label>
              <input type="number" id="bundletoolTimeout" class="form-control"
                v-model.number="settings.bundletoolTimeout" min="30000" max="600000" step="10000"
                @change="onSettingChange">
              <p class="form-text">BundleTool操作的超时时间</p>
            </div>
            <div class="form-group">
              <label class="form-label" for="javaHeapSize">Java 堆内存大小</label>
              <select id="javaHeapSize" class="form-control" v-model="settings.javaHeapSize" @change="onSettingChange">
                <option value="1g">1GB</option>
                <option value="2g">2GB</option>
                <option value="4g">4GB</option>
                <option value="8g">8GB</option>
              </select>
              <p class="form-text">Java工具使用的最大堆内存</p>
            </div>
          </div>
        </div>

        <!-- 分析设置 -->
        <div class="section">
          <div class="section-header">
            <h2><span class="section-icon">🔍</span>分析设置</h2>
            <div class="section-actions">
              <button class="btn btn-sm btn-primary" @click="saveAnalysisSettings" data-tooltip="保存分析设置">
                <span>💾</span>
              </button>
              <button class="btn btn-sm btn-secondary" @click="resetAnalysisSettings" data-tooltip="重置分析设置">
                <span>🔄</span>
              </button>
            </div>
          </div>
          <div class="settings-group">
            <div class="form-group">
              <label class="form-label" for="maxFileSize">最大文件大小</label>
              <select id="maxFileSize" class="form-control" v-model="settings.maxFileSize" @change="onSettingChange">
                <option value="200MB">200MB</option>
                <option value="500MB">500MB</option>
                <option value="1GB">1GB</option>
                <option value="2GB">2GB</option>
              </select>
              <p class="form-text">允许分析的最大APK文件大小</p>
            </div>
            <div class="form-group">
              <div class="form-check">
                <input type="checkbox" id="enableDeepScan" class="form-check-input" v-model="settings.enableDeepScan"
                  @change="onSettingChange">
                <label class="form-check-label" for="enableDeepScan">
                  启用深度扫描
                </label>
              </div>
              <p class="form-text">进行更详细的APK内容分析（耗时较长）</p>
            </div>
            <div class="form-group">
              <div class="form-check">
                <input type="checkbox" id="extractResources" class="form-check-input"
                  v-model="settings.extractResources" @change="onSettingChange">
                <label class="form-check-label" for="extractResources">
                  提取资源文件
                </label>
              </div>
              <p class="form-text">分析时提取APK中的资源文件</p>
            </div>
            <div class="form-group">
              <div class="form-check">
                <input type="checkbox" id="analyzePermissions" class="form-check-input"
                  v-model="settings.analyzePermissions" @change="onSettingChange">
                <label class="form-check-label" for="analyzePermissions">
                  分析权限使用
                </label>
              </div>
              <p class="form-text">详细分析APK的权限声明和使用情况</p>
            </div>
          </div>
        </div>

        <!-- 性能设置 -->
        <div class="section">
          <div class="section-header">
            <h2><span class="section-icon">⚡</span>性能设置</h2>
            <div class="section-actions">
              <button class="btn btn-sm btn-primary" @click="savePerformanceSettings" data-tooltip="保存性能设置">
                <span>💾</span>
              </button>
              <button class="btn btn-sm btn-secondary" @click="resetPerformanceSettings" data-tooltip="重置性能设置">
                <span>🔄</span>
              </button>
            </div>
          </div>
          <div class="settings-group">
            <div class="form-group">
              <label class="form-label" for="maxConcurrentTasks">最大并发任务数</label>
              <input type="number" id="maxConcurrentTasks" class="form-control"
                v-model.number="settings.maxConcurrentTasks" min="1" max="10" @change="onSettingChange">
              <p class="form-text">同时执行的最大任务数量</p>
            </div>
            <div class="form-group">
              <div class="form-check">
                <input type="checkbox" id="enableCache" class="form-check-input" v-model="settings.enableCache"
                  @change="onSettingChange">
                <label class="form-check-label" for="enableCache">
                  启用缓存
                </label>
              </div>
              <p class="form-text">缓存分析结果以提高性能</p>
            </div>
            <div class="form-group">
              <label class="form-label" for="cacheExpiry">缓存过期时间 (小时)</label>
              <input type="number" id="cacheExpiry" class="form-control" v-model.number="settings.cacheExpiry" min="1"
                max="168" @change="onSettingChange">
              <p class="form-text">缓存数据的有效期</p>
            </div>
            <div class="form-group">
              <label class="form-label" for="maxLogSize">最大日志大小 (MB)</label>
              <input type="number" id="maxLogSize" class="form-control" v-model.number="settings.maxLogSize" min="1"
                max="100" @change="onSettingChange">
              <p class="form-text">单个日志文件的最大大小</p>
            </div>
          </div>
        </div>

        <!-- 高级设置 -->
        <div class="section">
          <div class="section-header">
            <h2><span class="section-icon">🔬</span>高级设置</h2>
            <div class="section-actions">
              <button class="btn btn-sm btn-primary" @click="saveAdvancedSettings" data-tooltip="保存高级设置">
                <span>💾</span>
              </button>
              <button class="btn btn-sm btn-secondary" @click="resetAdvancedSettings" data-tooltip="重置高级设置">
                <span>🔄</span>
              </button>
            </div>
          </div>
          <div class="settings-group">
            <div class="form-group">
              <div class="form-check">
                <input type="checkbox" id="enableDevTools" class="form-check-input" v-model="settings.enableDevTools"
                  @change="onSettingChange">
                <label class="form-check-label" for="enableDevTools">
                  启用开发者工具
                </label>
              </div>
              <p class="form-text">允许打开开发者工具进行调试</p>
            </div>
            <div class="form-group">
              <div class="form-check">
                <input type="checkbox" id="enableLogging" class="form-check-input" v-model="settings.enableLogging"
                  @change="onSettingChange">
                <label class="form-check-label" for="enableLogging">
                  启用日志记录
                </label>
              </div>
              <p class="form-text">记录应用运行日志用于调试</p>
            </div>
            <div class="form-group">
              <label class="form-label" for="logLevel">日志级别</label>
              <select id="logLevel" class="form-control" v-model="settings.logLevel" @change="onSettingChange">
                <option value="error">错误</option>
                <option value="warn">警告</option>
                <option value="info">信息</option>
                <option value="debug">调试</option>
              </select>
              <p class="form-text">设置记录日志的详细程度</p>
            </div>
          </div>
        </div>

        <!-- 系统信息 -->
        <div class="section">
          <div class="section-header">
            <h2><span class="section-icon">💻</span>系统信息</h2>
            <div class="section-actions">
              <button class="btn btn-sm btn-secondary" @click="refreshSystemInfo" :disabled="isLoadingSystemInfo"
                data-tooltip="刷新系统信息">
                <span v-if="isLoadingSystemInfo">🔄</span>
                <span v-else>🔄</span>
              </button>
              <button class="btn btn-sm btn-secondary" @click="exportSystemInfo" data-tooltip="导出系统信息">
                <span>📤</span>
              </button>
            </div>
          </div>
          <div class="settings-group">
            <div class="info-category">
              <h3>操作系统</h3>
              <div class="info-grid">
                <div class="info-item">
                  <p class="info-label">
                    <span class="info-icon">🖥️</span>平台
                  </p>
                  <span class="info-value">{{ systemInfo.platform || '加载中...' }}</span>
                </div>
                <div class="info-item">
                  <p class="info-label">
                    <span class="info-icon">📋</span>版本
                  </p>
                  <span class="info-value">{{ systemInfo.platform_version || '加载中...' }}</span>
                </div>
                <div class="info-item">
                  <p class="info-label">
                    <span class="info-icon">🏗️</span>架构
                  </p>
                  <span class="info-value">{{ systemInfo.architecture || '加载中...' }}</span>
                </div>
                <div class="info-item">
                  <p class="info-label">
                    <span class="info-icon">🏠</span>主机名
                  </p>
                  <span class="info-value">{{ systemInfo.hostname || '加载中...' }}</span>
                </div>
              </div>
            </div>

            <div class="info-category">
              <h3>硬件信息</h3>
              <div class="info-grid">
                <div class="info-item">
                  <p class="info-label">
                    <span class="info-icon">🔧</span>处理器
                  </p>
                  <span class="info-value">{{ systemInfo.processor || '加载中...' }}</span>
                </div>
                <div class="info-item">
                  <p class="info-label">
                    <span class="info-icon">⚙️</span>CPU核心数
                  </p>
                  <span class="info-value">{{ systemInfo.cpuCount || '加载中...' }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 构建信息 -->
        <div class="section">
          <h2><span class="section-icon">🔧</span>构建信息</h2>
          <div class="settings-group">
            <div class="info-category">
              <h3>应用信息</h3>
              <div class="info-grid">
                <div class="info-item">
                  <p class="info-label">应用名称</p>
                  <span class="info-value">{{ buildInfo.appName || '加载中...' }}</span>
                </div>
                <div class="info-item">
                  <p class="info-label">应用版本</p>
                  <span class="info-value">{{ buildInfo.appVersion || '加载中...' }}</span>
                </div>
                <div class="info-item">
                  <p class="info-label">应用描述</p>
                  <span class="info-value">{{ buildInfo.appDescription || '加载中...' }}</span>
                </div>
              </div>
            </div>

            <div class="info-category">
              <h3>运行环境</h3>
              <div class="info-grid">
                <div class="info-item">
                  <p class="info-label">Electron版本</p>
                  <span class="info-value">{{ buildInfo.electronVersion || '加载中...' }}</span>
                </div>
                <div class="info-item">
                  <p class="info-label">Node.js版本</p>
                  <span class="info-value">{{ buildInfo.nodeVersion || '加载中...' }}</span>
                </div>
                <div class="info-item">
                  <p class="info-label">Chrome版本</p>
                  <span class="info-value">{{ buildInfo.chromeVersion || '加载中...' }}</span>
                </div>
                 <div class="info-item">
                  <p class="info-label">Java版本</p>
                  <span class="info-value">{{ buildInfo.javaVersion || '加载中...' }}</span>
                </div>
                 <div class="info-item">
                  <p class="info-label">Python版本</p>
                  <span class="info-value">{{ buildInfo.javaVersion || '加载中...' }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, reactive, inject, onMounted } from 'vue'
import serviceManager from '@services/ServiceManager.js'
import { useNotification } from '@composables/useNotification.js'

export default {
  name: 'SettingsPage',
  setup() {
    // 注入服务
    const { showSuccess, showError: showNotifyError } = useNotification()
    const errorService = inject('errorService', null)
    const settingsServiceRef = ref(null)
    const systemServiceRef = ref(null)

    // 响应式数据
    const hasUnsavedChanges = ref(false)
    const isLoadingSystemInfo = ref(false)
    const isLoadingTools = ref(false)

    const settings = reactive({
      // 常规设置
      language: 'zh-CN',
      theme: 'auto',
      autoSave: true,
      enableNotifications: true,

      // 工具路径设置
      adbPath: '',
      aaptPath: '',
      apktoolPath: '',
      bundletoolPath: '',
      javaPath: '',

      // 工具超时设置
      adbTimeout: 30000,
      apktoolTimeout: 60000,
      bundletoolTimeout: 60000,
      javaHeapSize: '2g',

      // 输出设置
      outputDirectory: '',
      exportApkDirectory: '',
      keepOriginalStructure: true,
      compressOutput: false,

      // 分析设置
      maxFileSize: '100MB',
      enableDeepScan: false,
      extractResources: true,
      analyzePermissions: true,

      // 设备设置
      connectionTimeout: 10000,
      commandTimeout: 30000,
      retryCount: 3,
      retryDelay: 1000,
      monitorInterval: 5000,
      autoDetectDevices: true,
      enableDeviceMonitoring: true,
      autoReconnect: true,

      // 高级设置
      enableDevTools: false,
      enableLogging: true,
      logLevel: 'info',
      maxLogSize: 10,

      // 性能设置
      maxConcurrentTasks: 3,
      enableCache: true,
      cacheExpiry: 24
    })

    const systemInfo = reactive({
      platform: '',
      platform_version: '',
      platform_release: '',
      architecture: '',
      hostname: '',
      cpuCount: '',
      processor: ''
    })
    const buildInfo = reactive({
      appName: '',
      appVersion: '',
      appDescription: '',
      electronVersion: '',
      nodeVersion: '',
      chromeVersion: '',
      javaVersion: '',
      pythonVersion: ''
    })

    const tools = reactive([])
    const systemSearchEnabled = ref(false)
    const recommendedVersions = {
      java: '11',
      adb: '1.0.41',
      aapt: '30.0.3',
      apktool: '2.7.0',
      bundletool: '1.15.5'
    }

    // 设置变更处理
    const onSettingChange = () => {
      hasUnsavedChanges.value = true
    }

    // 加载设置
    const loadSettings = async () => {
      try {
        const svc = settingsServiceRef.value || await serviceManager.getService('settings')
        settingsServiceRef.value = svc
        const result = await svc.loadSettings()

        if (result) {
          // 更新设置对象
          Object.keys(settings).forEach(key => {
            if (result.hasOwnProperty(key)) {
              settings[key] = result[key]
            }
          })
        }
      } catch (error) {
        console.error('加载设置失败:', error)
        showError('加载设置失败', error.message)
      }
    }

    // 保存设置
    const saveSettings = async () => {
      try {
        const svc = settingsServiceRef.value || await serviceManager.getService('settings')
        settingsServiceRef.value = svc
        await svc.saveSettings(settings)
        hasUnsavedChanges.value = false
        showSuccess('设置保存成功')
      } catch (error) {
        console.error('保存设置失败:', error)
        showError('保存设置失败', error.message)
      }
    }

    // 重置设置
    const resetSettings = async () => {
      if (!confirm('确定要重置所有设置为默认值吗？此操作不可撤销。')) {
        return
      }

      try {
        const svc = settingsServiceRef.value || await serviceManager.getService('settings')
        settingsServiceRef.value = svc
        await svc.resetSettings()
        await loadSettings() // 重新加载设置
        hasUnsavedChanges.value = false
        showSuccess('设置已重置为默认值')
      } catch (error) {
        console.error('重置设置失败:', error)
        showError('重置设置失败', error.message)
      }
    }

    // 导出设置
    const exportSettings = async () => {
      try {
        const exportData = {
          timestamp: new Date().toISOString(),
          settings: { ...settings }
        }
        const dataStr = JSON.stringify(exportData, null, 2)
        const blob = new Blob([dataStr], { type: 'application/json' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `settings-${new Date().toISOString().split('T')[0]}.json`
        document.body.appendChild(a)
        a.click()
        document.body.removeChild(a)
        URL.revokeObjectURL(url)
        showSuccess('设置导出成功')
      } catch (error) {
        console.error('导出设置失败:', error)
        showError('导出设置失败', error.message)
      }
    }

    // 导入设置
    const importSettings = async () => {
      try {
        const svc = systemServiceRef.value || await serviceManager.getService('system')
        systemServiceRef.value = svc
        const result = await svc.selectFile({ filters: [{ name: 'JSON', extensions: ['json'] }] })
        if (result && result.filePath) {
          showSuccess('设置导入成功')
        }
        await loadSettings() // 重新加载设置
        hasUnsavedChanges.value = false
      } catch (error) {
        console.error('导入设置失败:', error)
        showError('导入设置失败', error.message)
      }
    }

    // 浏览工具路径
    const browseToolPath = async (target) => {
      try {
        const svc = systemServiceRef.value || await serviceManager.getService('system')
        systemServiceRef.value = svc
        const result = await svc.selectFile({
          title: '选择工具文件',
          filters: [
            { name: '可执行文件', extensions: ['exe', 'jar'] },
            { name: '所有文件', extensions: ['*'] }
          ]
        })

        if (result && result.filePath) {
          settings[target] = result.filePath
          onSettingChange()
        }
      } catch (error) {
        console.error('选择文件失败:', error)
        showError('选择文件失败', error.message)
      }
    }

    // 浏览目录
    const browseDirectory = async (target) => {
      try {
        const svc = systemServiceRef.value || await serviceManager.getService('system')
        systemServiceRef.value = svc
        const result = await svc.selectDirectory({
          title: '选择目录'
        })

        if (result && result.directoryPath) {
          settings[target] = result.directoryPath
          onSettingChange()
        }
      } catch (error) {
        console.error('选择目录失败:', error)
        showError('选择目录失败', error.message)
      }
    }

    // 加载系统信息
    const loadSystemInfo = async () => {
      try {
        isLoadingSystemInfo.value = true
        const svc = systemServiceRef.value || await serviceManager.getService('system')
        systemServiceRef.value = svc
        const systemResult = await svc.getSystemInfo()
        if (systemResult && systemResult.system_info) {
          const sysInfo = systemResult.system_info

          systemInfo.platform = sysInfo.platform || '未知'
          systemInfo.platform_version = sysInfo.platform_version || '未知'
          systemInfo.platform_release = sysInfo.platform_release || '未知'
          systemInfo.architecture = sysInfo.architecture || '未知'
          systemInfo.hostname = sysInfo.hostname || '未知'
          systemInfo.cpuCount = sysInfo.cpu_count || '未知'
          systemInfo.processor = sysInfo.processor || '未知'

          // 内存信息处理
          if (sysInfo.memoryTotal) {
            systemInfo.memoryTotal = formatFileSize(sysInfo.memoryTotal)
          }
          if (sysInfo.memoryUsed) {
            systemInfo.memoryUsed = formatFileSize(sysInfo.memoryUsed)
          }
          if (sysInfo.memoryPercent !== undefined) {
            systemInfo.memoryPercent = `${sysInfo.memoryPercent.toFixed(1)}%`
          }

          // 磁盘信息处理
          if (sysInfo.diskTotal) {
            systemInfo.diskTotal = formatFileSize(sysInfo.diskTotal)
          }
          if (sysInfo.diskUsed) {
            systemInfo.diskUsed = formatFileSize(sysInfo.diskUsed)
          }
          if (sysInfo.diskPercent !== undefined) {
            systemInfo.diskPercent = `${sysInfo.diskPercent.toFixed(1)}%`
          }

          // 系统状态信息
          if (sysInfo.uptime) {
            systemInfo.uptime = formatUptime(sysInfo.uptime)
          }
          if (sysInfo.loadAverage && Array.isArray(sysInfo.loadAverage)) {
            systemInfo.loadAverage = sysInfo.loadAverage.map(avg => avg.toFixed(2)).join(', ')
          }
        }

        const buildResult = await svc.getBuildInfo()
        const electronVer = await svc.getElectronVersion()

        if (buildResult && buildResult.build_info) {
          const build = buildResult.build_info

          buildInfo.appName = build.app_name || '未知'
          buildInfo.appVersion = build.app_version || '未知'
          buildInfo.appDescription = build.app_description || '无描述'
          buildInfo.electronVersion = electronVer || build.electron_version || '未知'
          buildInfo.nodeVersion = build.node_version || '未知'
          buildInfo.chromeVersion = build.chrome_version || '未知'
          buildInfo.javaVersion = build.java_version || '未知'
          buildInfo.pythonVersion = build.python_version || '未知'
        }
      } catch (error) {
        console.error('加载系统信息失败:', error)
      } finally {
        isLoadingSystemInfo.value = false
      }
    }

    // 刷新系统信息
    const refreshSystemInfo = async () => {
      await loadSystemInfo()
      showSuccess('系统信息已刷新')
    }

    const toolServiceRef = ref(null)
    const mapToolsFromCache = (list) => {
      const fullNameMap = {
        adb: 'Android Debug Bridge',
        aapt: 'Android Asset Packaging Tool',
        apktool: 'APKTool',
        java: 'Java',
        bundletool: 'BundleTool',
        apksigner: 'Apk Signer',
        zipalign: 'Zipalign',
        jarsigner: 'JAR Signer'
      }
      tools.splice(0, tools.length)
      list.forEach(item => {
        const key = item.name || item.key
        const fullName = fullNameMap[key] || key
        const version = item.version || ''
        const needsUpdate = checkNeedsUpdate(key, version)
        tools.push({
          key,
          fullName,
          status: item.status || (item.available ? 'available' : 'unavailable'),
          version,
          path: item.path || item.tool_path || '',
          source: item.source || 'unknown',
          needsUpdate
        })
      })
    }

    const initializeToolView = async () => {
      try {
        isLoadingTools.value = true
        toolServiceRef.value = await serviceManager.getService('tools')
        const cached = toolServiceRef.value.getAllToolsStatus()
        if (cached && cached.length) {
          mapToolsFromCache(cached)
        }
        toolServiceRef.value.addListener((event, data) => {
          if (event === 'tools_updated' && Array.isArray(data)) {
            mapToolsFromCache(data)
          }
        })
      } catch (e) {
        console.error('初始化工具视图失败:', e)
        showError('初始化工具视图失败')
      } finally {
        isLoadingTools.value = false
      }
    }

    const refreshTools = async () => {
      try {
        console.log('refreshTools函数被调用')
        isLoadingTools.value = true
        if (!toolServiceRef.value) {
          toolServiceRef.value = await serviceManager.getService('tools')
        }
        await toolServiceRef.value.refreshToolsStatus()
        showSuccess('工具状态已刷新')
      } catch (e) {
        console.error('刷新工具状态失败:', e)
        showError('刷新工具状态失败')
      } finally {
        isLoadingTools.value = false
      }
    }

    const toggleSystemSearch = async () => {
      try {
        const next = !systemSearchEnabled.value
        if (!toolServiceRef.value) {
          toolServiceRef.value = await serviceManager.getService('tools')
        }
        const payload = await toolServiceRef.value.setSystemSearchMode(next)
        if (payload) {
          systemSearchEnabled.value = !!payload.system_search
          showSuccess(`系统查找已${next ? '开启' : '关闭'}`)
        }
      } catch (e) {
        console.error('切换系统工具优先失败:', e)
        showError('切换系统工具优先失败')
      }
    }

    const checkNeedsUpdate = (key, version) => {
      if (!version) return false
      const min = recommendedVersions[key]
      if (!min) return false
      const normalize = v => String(v).replace(/[^0-9.]/g, '')
      const cmp = (a, b) => {
        const pa = normalize(a).split('.').map(n => parseInt(n || '0', 10))
        const pb = normalize(b).split('.').map(n => parseInt(n || '0', 10))
        const len = Math.max(pa.length, pb.length)
        for (let i = 0; i < len; i++) {
          const da = pa[i] || 0
          const db = pb[i] || 0
          if (da < db) return -1
          if (da > db) return 1
        }
        return 0
      }
      return cmp(version, min) < 0
    }

    const checkVersion = async (key) => {
      try {
        if (!toolServiceRef.value) {
          toolServiceRef.value = await serviceManager.getService('tools')
        }
        const info = await toolServiceRef.value.checkTool(key, true)
        if (info) {
          const ver = info.version || ''
          const t = tools.find(t => t.key === key)
          if (t) {
            t.version = ver || t.version
            t.status = info.status || t.status
            t.path = info.path || t.path
            t.needsUpdate = checkNeedsUpdate(key, t.version)
          }
          showSuccess('版本检测完成')
        } else {
          showError('版本检测失败')
        }
      } catch (e) {
        console.error('版本检测失败:', e)
        showError('版本检测失败')
      }
    }

    const copyText = async (text) => {
      try {
        if (!text) return
        const svc = systemServiceRef.value || await serviceManager.getService('system')
        systemServiceRef.value = svc
        const ok = await svc.copyText(text)
        if (ok) showSuccess('已复制到剪贴板')
        else showError('复制失败')
      } catch (e) {
        showError('复制失败')
      }
    }

    const browseToolExecutable = async (key) => {
      try {
        const svc = systemServiceRef.value || await serviceManager.getService('system')
        systemServiceRef.value = svc
        const result = await svc.selectFile({
          title: '选择工具文件',
          filters: [
            { name: '可执行文件', extensions: ['exe', 'jar'] },
            { name: '所有文件', extensions: ['*'] }
          ]
        })
        if (result && result.filePath) {
          const path = result.filePath
          const t = tools.find(t => t.key === key)
          if (t) t.path = path
          const dotKey = `tools.${key}`
          // 这里仍然使用 settingsService 保存设置
          const settingsSvc = settingsServiceRef.value || await serviceManager.getService('settings')
          settingsServiceRef.value = settingsSvc
          await settingsSvc.saveSettings({ [dotKey]: path })
          showSuccess('工具路径已保存')
          await refreshTools()
        }
      } catch (e) {
        console.error('选择工具文件失败:', e)
        showError('选择工具文件失败')
      }
    }

    // 导出系统信息
    const exportSystemInfo = async () => {
      try {
        const exportData = {
          timestamp: new Date().toISOString(),
          systemInfo: systemInfo,
          buildInfo: buildInfo
        }

        const dataStr = JSON.stringify(exportData, null, 2)
        const blob = new Blob([dataStr], { type: 'application/json' })
        const url = URL.createObjectURL(blob)

        const a = document.createElement('a')
        a.href = url
        a.download = `system-info-${new Date().toISOString().split('T')[0]}.json`
        document.body.appendChild(a)
        a.click()
        document.body.removeChild(a)
        URL.revokeObjectURL(url)

        showSuccess('系统信息已导出')
      } catch (error) {
        console.error('导出系统信息失败:', error)
        showError('导出系统信息失败')
      }
    }

    // 格式化运行时间
    const formatUptime = (seconds) => {
      const days = Math.floor(seconds / 86400)
      const hours = Math.floor((seconds % 86400) / 3600)
      const minutes = Math.floor((seconds % 3600) / 60)

      if (days > 0) {
        return `${days}天 ${hours}小时 ${minutes}分钟`
      } else if (hours > 0) {
        return `${hours}小时 ${minutes}分钟`
      } else {
        return `${minutes}分钟`
      }
    }

    // 获取内存使用率样式类
    const getMemoryUsageClass = (percent) => {
      if (!percent) return ''
      const value = parseFloat(percent)
      if (value >= 90) return 'usage-critical'
      if (value >= 70) return 'usage-warning'
      return 'usage-normal'
    }

    // 获取磁盘使用率样式类
    const getDiskUsageClass = (percent) => {
      if (!percent) return ''
      const value = parseFloat(percent)
      if (value >= 95) return 'usage-critical'
      if (value >= 80) return 'usage-warning'
      return 'usage-normal'
    }

    // 分类级别的保存和重置方法
    const saveGeneralSettings = async () => {
      try {
        const generalSettings = {
          language: settings.language,
          theme: settings.theme,
          autoUpdate: settings.autoUpdate,
          startMinimized: settings.startMinimized,
          closeToTray: settings.closeToTray
        }
        const svc = settingsServiceRef.value || await serviceManager.getService('settings')
        settingsServiceRef.value = svc
        await svc.saveSettings(generalSettings)
        showSuccess('常规设置保存成功')
      } catch (error) {
        console.error('保存常规设置失败:', error)
        showError('保存常规设置失败', error.message)
      }
    }

    const resetGeneralSettings = async () => {
      if (!confirm('确定要重置常规设置为默认值吗？')) return

      try {
        settings.language = 'zh-CN'
        settings.theme = 'auto'
        settings.autoUpdate = true
        settings.startMinimized = false
        settings.closeToTray = false
        await saveGeneralSettings()
        showSuccess('常规设置已重置')
      } catch (error) {
        showError('重置常规设置失败', error.message)
      }
    }

    const saveToolPathSettings = async () => {
      try {
        const toolPathSettings = {
          adbPath: settings.adbPath,
          apktoolPath: settings.apktoolPath,
          javaPath: settings.javaPath,
          aaptPath: settings.aaptPath
        }
        const svc = settingsServiceRef.value || await serviceManager.getService('settings')
        settingsServiceRef.value = svc
        await svc.saveSettings(toolPathSettings)
        showSuccess('工具路径设置保存成功')
      } catch (error) {
        console.error('保存工具路径设置失败:', error)
        showError('保存工具路径设置失败', error.message)
      }
    }

    const resetToolPathSettings = async () => {
      if (!confirm('确定要重置工具路径设置为默认值吗？')) return

      try {
        settings.adbPath = ''
        settings.apktoolPath = ''
        settings.javaPath = ''
        settings.aaptPath = ''
        await saveToolPathSettings()
        showSuccess('工具路径设置已重置')
      } catch (error) {
        showError('重置工具路径设置失败', error.message)
      }
    }

    const saveOutputSettings = async () => {
      try {
        const outputSettings = {
          outputDirectory: settings.outputDirectory,
          keepOriginalStructure: settings.keepOriginalStructure,
          compressOutput: settings.compressOutput,
          includeMetadata: settings.includeMetadata
        }
        const svc = settingsServiceRef.value || await serviceManager.getService('settings')
        settingsServiceRef.value = svc
        await svc.saveSettings(outputSettings)
        showSuccess('输出设置保存成功')
      } catch (error) {
        console.error('保存输出设置失败:', error)
        showError('保存输出设置失败', error.message)
      }
    }

    const resetOutputSettings = async () => {
      if (!confirm('确定要重置输出设置为默认值吗？')) return

      try {
        settings.outputDirectory = ''
        settings.keepOriginalStructure = true
        settings.compressOutput = false
        settings.includeMetadata = true
        await saveOutputSettings()
        showSuccess('输出设置已重置')
      } catch (error) {
        showError('重置输出设置失败', error.message)
      }
    }

    const saveDeviceSettings = async () => {
      try {
        const deviceSettings = {
          retryDelay: settings.retryDelay,
          monitorInterval: settings.monitorInterval,
          autoDetectDevices: settings.autoDetectDevices,
          enableDeviceMonitoring: settings.enableDeviceMonitoring,
          autoReconnect: settings.autoReconnect
        }
        const svc = settingsServiceRef.value || await serviceManager.getService('settings')
        settingsServiceRef.value = svc
        await svc.saveSettings(deviceSettings)
        showSuccess('设备连接设置保存成功')
      } catch (error) {
        console.error('保存设备连接设置失败:', error)
        showError('保存设备连接设置失败', error.message)
      }
    }

    const resetDeviceSettings = async () => {
      if (!confirm('确定要重置设备连接设置为默认值吗？')) return

      try {
        settings.retryDelay = 3000
        settings.monitorInterval = 5000
        settings.autoDetectDevices = true
        settings.enableDeviceMonitoring = true
        settings.autoReconnect = true
        await saveDeviceSettings()
        showSuccess('设备连接设置已重置')
      } catch (error) {
        showError('重置设备连接设置失败', error.message)
      }
    }

    const saveTimeoutSettings = async () => {
      try {
        const timeoutSettings = {
          adbTimeout: settings.adbTimeout,
          apktoolTimeout: settings.apktoolTimeout
        }
        await settingsService.saveSettings(timeoutSettings)
        showSuccess('工具超时设置保存成功')
      } catch (error) {
        console.error('保存工具超时设置失败:', error)
        showError('保存工具超时设置失败', error.message)
      }
    }

    const resetTimeoutSettings = async () => {
      if (!confirm('确定要重置工具超时设置为默认值吗？')) return

      try {
        settings.adbTimeout = 30000
        settings.apktoolTimeout = 300000
        await saveTimeoutSettings()
        showSuccess('工具超时设置已重置')
      } catch (error) {
        showError('重置工具超时设置失败', error.message)
      }
    }

    const saveAnalysisSettings = async () => {
      try {
        const analysisSettings = {
          maxFileSize: settings.maxFileSize,
          enableDeepScan: settings.enableDeepScan,
          extractResources: settings.extractResources,
          analyzePermissions: settings.analyzePermissions
        }
        const svc = settingsServiceRef.value || await serviceManager.getService('settings')
        settingsServiceRef.value = svc
        await svc.saveSettings(analysisSettings)
        showSuccess('分析设置保存成功')
      } catch (error) {
        console.error('保存分析设置失败:', error)
        showError('保存分析设置失败', error.message)
      }
    }

    const resetAnalysisSettings = async () => {
      if (!confirm('确定要重置分析设置为默认值吗？')) return

      try {
        settings.maxFileSize = '200MB'
        settings.enableDeepScan = false
        settings.extractResources = true
        settings.analyzePermissions = true
        await saveAnalysisSettings()
        showSuccess('分析设置已重置')
      } catch (error) {
        showError('重置分析设置失败', error.message)
      }
    }

    const savePerformanceSettings = async () => {
      try {
        const performanceSettings = {
          maxConcurrentTasks: settings.maxConcurrentTasks,
          enableCache: settings.enableCache,
          cacheExpiry: settings.cacheExpiry,
          maxLogSize: settings.maxLogSize
        }
        const svc = settingsServiceRef.value || await serviceManager.getService('settings')
        settingsServiceRef.value = svc
        await svc.saveSettings(performanceSettings)
        showSuccess('性能设置保存成功')
      } catch (error) {
        console.error('保存性能设置失败:', error)
        showError('保存性能设置失败', error.message)
      }
    }

    const resetPerformanceSettings = async () => {
      if (!confirm('确定要重置性能设置为默认值吗？')) return

      try {
        settings.maxConcurrentTasks = 3
        settings.enableCache = true
        settings.cacheExpiry = 24
        settings.maxLogSize = 10
        await savePerformanceSettings()
        showSuccess('性能设置已重置')
      } catch (error) {
        showError('重置性能设置失败', error.message)
      }
    }

    const saveAdvancedSettings = async () => {
      try {
        const advancedSettings = {
          enableDevTools: settings.enableDevTools,
          enableLogging: settings.enableLogging,
          logLevel: settings.logLevel
        }
        const svc = settingsServiceRef.value || await serviceManager.getService('settings')
        settingsServiceRef.value = svc
        await svc.saveSettings(advancedSettings)
        showSuccess('高级设置保存成功')
      } catch (error) {
        console.error('保存高级设置失败:', error)
        showError('保存高级设置失败', error.message)
      }
    }

    const resetAdvancedSettings = async () => {
      if (!confirm('确定要重置高级设置为默认值吗？')) return

      try {
        settings.enableDevTools = false
        settings.enableLogging = true
        settings.logLevel = 'info'
        await saveAdvancedSettings()
        showSuccess('高级设置已重置')
      } catch (error) {
        showError('重置高级设置失败', error.message)
      }
    }

    // 工具方法
    const formatFileSize = (bytes) => {
      if (!bytes) return '0 B'
      const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
      const i = Math.floor(Math.log(bytes) / Math.log(1024))
      return `${(bytes / Math.pow(1024, i)).toFixed(2)} ${sizes[i]}`
    }

    const showError = (title, message = '') => {
      if (errorService) {
        const err = new Error(message || title || '未知错误')
        // errorService might be a ref too if we changed App.vue to provide errorServiceRef
        const es = errorService.value || errorService
        if (es && typeof es.reportError === 'function') {
          es.reportError(err, { category: 'service', context: title || '操作失败' })
        }
      }
      showNotifyError(title, message)
    }

    // 生命周期
    onMounted(async () => {
      console.log('SettingsPage组件已挂载')
      try {
        settingsServiceRef.value = await serviceManager.getService('settings')
      } catch { }
      await loadSettings()
      await loadSystemInfo()
      await initializeToolView()
    })

    return {
      settings,
      systemInfo,
      buildInfo,
      tools,
      systemSearchEnabled,
      isLoadingTools,
      hasUnsavedChanges,
      isLoadingSystemInfo,
      onSettingChange,
      saveSettings,
      resetSettings,
      exportSettings,
      importSettings,
      browseToolPath,
      browseDirectory,
      refreshSystemInfo,
      exportSystemInfo,
      refreshTools,
      toggleSystemSearch,
      copyText,
      checkVersion,
      browseToolExecutable,
      getMemoryUsageClass,
      getDiskUsageClass,
      // 分类级别的方法
      saveGeneralSettings,
      resetGeneralSettings,
      saveToolPathSettings,
      resetToolPathSettings,
      saveOutputSettings,
      resetOutputSettings,
      saveDeviceSettings,
      resetDeviceSettings,
      saveTimeoutSettings,
      resetTimeoutSettings,
      saveAnalysisSettings,
      resetAnalysisSettings,
      savePerformanceSettings,
      resetPerformanceSettings,
      saveAdvancedSettings,
      resetAdvancedSettings
    }
  }
}
</script>

<style scoped>
/* SettingsPage组件特殊样式 */
.settings-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-bottom: 20px;
  padding: 0 20px;
}

.path-input-group {
  display: flex;
  gap: 8px;
}

.path-input-group input {
  flex: 1;
}

.path-browse-btn {
  flex-shrink: 0;
  white-space: nowrap;
}

/* 开发工具卡片 */
.tool-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 12px;
}

.tool-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 10px 12px;
  overflow: hidden;
}

.tool-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}

.tool-name {
  font-weight: 600;
  color: var(--text-color);
  font-size: 14px;
}

.tool-status {
  display: flex;
  gap: 6px;
  align-items: center;
}

.status-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 12px;
  font-size: 11px;
}

.status-ok {
  background: #e6fffb;
  color: #08979c;
  border: 1px solid #87e8de;
}

.status-bad {
  background: #fff1f0;
  color: #cf1322;
  border: 1px solid #ffa39e;
}

.update-badge {
  background: #fffbe6;
  color: #d48806;
  border: 1px solid #ffe58f;
  border-radius: 12px;
  font-size: 11px;
  padding: 2px 8px;
}

.tool-card-body {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.tool-field {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.field-label {
  color: var(--text-color-secondary);
  font-size: 12px;
  min-width: 72px;
}

.field-value {
  color: var(--text-color);
  font-weight: 600;
  font-size: 12px;
}

.path-text {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-family: monospace;
  max-width: none;
}

.info-category {
  margin-bottom: 20px;
}

.info-category h3 {
  margin-bottom: 10px;
  color: #666;
  font-size: 14px;
  font-weight: bold;
}

.info-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

.info-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 0;
}

.info-label {
  font-weight: bold;
  color: #666;
  margin: 0;
}

.info-value {
  color: #333;
  font-family: monospace;
  font-size: 12px;
}

/* 系统信息样式 */
.section-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 20px;
  position: relative;
}

.section-actions {
  display: flex;
  gap: 8px;
  position: absolute;
  top: 0;
  right: 0;
}

.section-actions .btn {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  padding: 6px 12px;
}


.info-category {
  margin-bottom: 24px;
}

.info-category h3 {
  color: var(--text-color);
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--border-color);
}

.info-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 16px;
}

.info-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  transition: all 0.2s ease;
}

.info-item:hover {
  border-color: var(--primary-color);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.info-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 500;
  color: var(--text-color-secondary);
  margin: 0;
  font-size: 14px;
}

.info-icon {
  font-size: 16px;
  width: 20px;
  text-align: center;
}

.info-value {
  font-weight: 600;
  color: var(--text-color);
  font-size: 14px;
  text-align: right;
  max-width: 50%;
  word-break: break-all;
}

/* 使用率状态指示器 */
.usage-normal {
  color: #52c41a;
}

.usage-warning {
  color: #faad14;
}

.usage-critical {
  color: #ff4d4f;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .section-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 12px;
  }

  .info-grid {
    grid-template-columns: 1fr;
  }

  .tool-grid {
    grid-template-columns: 1fr;
  }

  .info-item {
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
  }

  .info-value {
    max-width: 100%;
    text-align: left;
  }
}
</style>