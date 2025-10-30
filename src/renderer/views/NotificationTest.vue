<template>
  <div class="notification-test">
    <div class="test-header">
      <h2>通知系统测试</h2>
      <p>测试重构后的通知系统功能</p>
    </div>
    
    <div class="test-controls">
      <div class="control-group">
        <h3>基础通知</h3>
        <div class="button-group">
          <button @click="showSuccess" class="btn btn-success">成功通知</button>
          <button @click="showError" class="btn btn-error">错误通知</button>
          <button @click="showWarning" class="btn btn-warning">警告通知</button>
          <button @click="showInfo" class="btn btn-info">信息通知</button>
        </div>
      </div>
      
      <div class="control-group">
        <h3>加载通知</h3>
        <div class="button-group">
          <button @click="showLoading" class="btn btn-primary">显示加载</button>
          <button @click="completeLoading" class="btn btn-success" :disabled="!loadingId">完成加载</button>
          <button @click="failLoading" class="btn btn-error" :disabled="!loadingId">失败加载</button>
        </div>
      </div>
      
      <div class="control-group">
        <h3>批量操作</h3>
        <div class="button-group">
          <button @click="showMultiple" class="btn btn-primary">显示多个通知</button>
          <button @click="clearAll" class="btn btn-secondary">清除所有</button>
        </div>
      </div>
    </div>
    
    <div class="test-status">
      <h3>通知服务状态</h3>
      <div class="status-info">
        <p><strong>服务状态:</strong> {{ serviceStatus.isInitialized ? '已初始化' : '未初始化' }}</p>
        <p><strong>通知数量:</strong> {{ serviceStatus.notificationCount }}</p>
        <p><strong>监听器数量:</strong> {{ serviceStatus.listenerCount }}</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import serviceManager from '../services/ServiceManager.js'

// 响应式数据
const loadingId = ref(null)
const serviceStatus = ref({
  isInitialized: false,
  notificationCount: 0,
  listenerCount: 0
})

// 获取通知服务
const getNotificationService = () => {
  return serviceManager.getService('notification')
}

// 更新服务状态
const updateServiceStatus = () => {
  const notificationService = getNotificationService()
  if (notificationService) {
    serviceStatus.value = notificationService.getStatus()
  }
}

// 基础通知测试
const showSuccess = () => {
  const notificationService = getNotificationService()
  if (notificationService) {
    notificationService.success('操作成功', '这是一个成功通知的示例')
    updateServiceStatus()
  }
}

const showError = () => {
  const notificationService = getNotificationService()
  if (notificationService) {
    notificationService.error('操作失败', '这是一个错误通知的示例，不会自动关闭')
    updateServiceStatus()
  }
}

const showWarning = () => {
  const notificationService = getNotificationService()
  if (notificationService) {
    notificationService.warning('注意事项', '这是一个警告通知的示例')
    updateServiceStatus()
  }
}

const showInfo = () => {
  const notificationService = getNotificationService()
  if (notificationService) {
    notificationService.info('提示信息', '这是一个信息通知的示例')
    updateServiceStatus()
  }
}

// 加载通知测试
const showLoading = () => {
  const notificationService = getNotificationService()
  if (notificationService) {
    loadingId.value = notificationService.loading('正在处理', '请稍候，正在执行操作...')
    updateServiceStatus()
  }
}

const completeLoading = () => {
  const notificationService = getNotificationService()
  if (notificationService && loadingId.value) {
    notificationService.completeLoading(loadingId.value, '处理完成', '操作已成功完成')
    loadingId.value = null
    updateServiceStatus()
  }
}

const failLoading = () => {
  const notificationService = getNotificationService()
  if (notificationService && loadingId.value) {
    notificationService.failLoading(loadingId.value, '处理失败', '操作执行失败，请重试')
    loadingId.value = null
    updateServiceStatus()
  }
}

// 批量操作测试
const showMultiple = () => {
  const notificationService = getNotificationService()
  if (notificationService) {
    notificationService.info('通知 1', '第一个通知')
    setTimeout(() => {
      notificationService.success('通知 2', '第二个通知')
    }, 500)
    setTimeout(() => {
      notificationService.warning('通知 3', '第三个通知')
    }, 1000)
    updateServiceStatus()
  }
}

const clearAll = () => {
  const notificationService = getNotificationService()
  if (notificationService) {
    notificationService.clear()
    loadingId.value = null
    updateServiceStatus()
  }
}

// 生命周期
onMounted(() => {
  // 定期更新服务状态
  const interval = setInterval(updateServiceStatus, 1000)
  
  onUnmounted(() => {
    clearInterval(interval)
  })
  
  // 初始状态更新
  updateServiceStatus()
})
</script>

<style scoped>
.notification-test {
  padding: 20px;
  max-width: 800px;
  margin: 0 auto;
}

.test-header {
  text-align: center;
  margin-bottom: 30px;
}

.test-header h2 {
  color: var(--text-color, #333);
  margin-bottom: 8px;
}

.test-header p {
  color: var(--text-color-secondary, #666);
  font-size: 14px;
}

.test-controls {
  margin-bottom: 30px;
}

.control-group {
  margin-bottom: 25px;
  padding: 20px;
  border: 1px solid var(--border-color, #e1e5e9);
  border-radius: 8px;
  background: var(--bg-color, #ffffff);
}

.control-group h3 {
  margin: 0 0 15px 0;
  color: var(--text-color, #333);
  font-size: 16px;
}

.button-group {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.btn {
  padding: 8px 16px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  transition: all 0.2s ease;
  min-width: 100px;
}

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-success {
  background: #52c41a;
  color: white;
}

.btn-success:hover:not(:disabled) {
  background: #389e0d;
}

.btn-error {
  background: #ff4d4f;
  color: white;
}

.btn-error:hover:not(:disabled) {
  background: #cf1322;
}

.btn-warning {
  background: #faad14;
  color: white;
}

.btn-warning:hover:not(:disabled) {
  background: #d48806;
}

.btn-info {
  background: #1890ff;
  color: white;
}

.btn-info:hover:not(:disabled) {
  background: #096dd9;
}

.btn-primary {
  background: #1890ff;
  color: white;
}

.btn-primary:hover:not(:disabled) {
  background: #096dd9;
}

.btn-secondary {
  background: #f5f5f5;
  color: #333;
  border: 1px solid #d9d9d9;
}

.btn-secondary:hover:not(:disabled) {
  background: #e6f7ff;
  border-color: #91d5ff;
}

.test-status {
  padding: 20px;
  border: 1px solid var(--border-color, #e1e5e9);
  border-radius: 8px;
  background: var(--bg-color-light, #fafafa);
}

.test-status h3 {
  margin: 0 0 15px 0;
  color: var(--text-color, #333);
  font-size: 16px;
}

.status-info p {
  margin: 8px 0;
  color: var(--text-color, #333);
  font-size: 14px;
}

.status-info strong {
  color: var(--text-color-primary, #1890ff);
}

/* 深色主题适配 */
@media (prefers-color-scheme: dark) {
  .control-group {
    background: var(--bg-color-dark, #2d2d2d);
    border-color: var(--border-color-dark, #404040);
  }
  
  .test-status {
    background: var(--bg-color-dark-light, #3a3a3a);
    border-color: var(--border-color-dark, #404040);
  }
  
  .control-group h3,
  .test-status h3,
  .status-info p {
    color: var(--text-color-dark, #ffffff);
  }
  
  .btn-secondary {
    background: #404040;
    color: #ffffff;
    border-color: #595959;
  }
  
  .btn-secondary:hover:not(:disabled) {
    background: #595959;
    border-color: #73d13d;
  }
}
</style>