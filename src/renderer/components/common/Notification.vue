<template>
  <Teleport to="body">
    <div class="notification-container" v-if="notifications.length > 0">
      <TransitionGroup name="notification" tag="div">
        <div
          v-for="notification in notifications"
          :key="notification.id"
          :class="[
            'notification',
            `notification-${notification.type}`,
            { 'notification-loading': notification.type === 'loading' }
          ]"
        >
          <!-- 通知图标 -->
          <div class="notification-icon">
            <div v-if="notification.type === 'loading'" class="loading-spinner"></div>
            <span v-else class="notification-icon-symbol">{{ getIcon(notification.type) }}</span>
          </div>
          
          <!-- 通知内容 -->
          <div class="notification-content">
            <div v-if="notification.title" class="notification-title">
              {{ notification.title }}
            </div>
            <div v-if="notification.message" class="notification-message">
              {{ notification.message }}
            </div>
          </div>
          
          <!-- 关闭按钮 -->
          <button 
            v-if="notification.type !== 'loading'"
            class="notification-close" 
            @click="hideNotification(notification.id)"
            aria-label="Close notification"
          >
            <span class="close-icon">×</span>
          </button>
        </div>
      </TransitionGroup>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import serviceManager from '@services/ServiceManager'

// 响应式数据
const notifications = ref([])

// 通知图标映射
const iconMap = {
  success: '✓',
  error: '✕',
  warning: '⚠',
  info: 'ℹ'
}

/**
 * 获取通知图标
 */
const getIcon = (type) => {
  return iconMap[type] || iconMap.info
}

/**
 * 显示通知
 */
const showNotification = (notificationData) => {
  const notification = {
    id: notificationData.id,
    type: notificationData.type || 'info',
    title: notificationData.title || '',
    message: notificationData.message || '',
    duration: notificationData.duration || 5000
  }
  
  notifications.value.push(notification)
  
  // 自动关闭（除了loading和error类型）
  if (notification.duration > 0 && notification.type !== 'loading' && notification.type !== 'error') {
    setTimeout(() => {
      hideNotification(notification.id)
    }, notification.duration)
  }
}

/**
 * 隐藏通知
 */
const hideNotification = (id) => {
  const index = notifications.value.findIndex(n => n.id === id)
  if (index > -1) {
    notifications.value.splice(index, 1)
  }
}

/**
 * 更新通知内容（主要用于loading类型）
 */
const updateNotification = (id, updates) => {
  const notification = notifications.value.find(n => n.id === id)
  if (notification) {
    Object.assign(notification, updates)
  }
}

/**
 * 清除所有通知
 */
const clearAllNotifications = () => {
  notifications.value = []
}

// 生命周期钩子
let notificationService = null

onMounted(async () => {
  try {
    // 尝试同步获取
    notificationService = serviceManager.getServiceSync('notification')
    
    // 如果同步获取失败，尝试异步获取
    if (!notificationService) {
      notificationService = await serviceManager.getService('notification')
    }
    
    if (notificationService) {
      setupListeners(notificationService)
    }
  } catch (error) {
    console.error('Failed to get notification service:', error)
  }
  console.log('Notification component mounted')
})

const setupListeners = (service) => {
  service.addListener('show', showNotification)
  service.addListener('hide', hideNotification)
  service.addListener('update', updateNotification)
  service.addListener('clear', clearAllNotifications)
}

const removeListeners = (service) => {
  service.removeListener('show', showNotification)
  service.removeListener('hide', hideNotification)
  service.removeListener('update', updateNotification)
  service.removeListener('clear', clearAllNotifications)
}

onUnmounted(() => {
  if (notificationService) {
    removeListeners(notificationService)
  }
})

// 暴露方法给外部使用
defineExpose({
  showNotification,
  hideNotification,
  updateNotification,
  clearAllNotifications
})
</script>

<style scoped>
.notification-container {
  position: fixed;
  bottom: 20px;
  right: 20px;
  z-index: 9999;
  pointer-events: none;
  display: flex;
  flex-direction: column-reverse;
}

.notification {
  display: flex;
  align-items: flex-start;
  min-width: 320px;
  max-width: 480px;
  margin-top: 12px;
  padding: 16px;
  background: var(--bg-color, #ffffff);
  border: 1px solid var(--border-color, #e1e5e9);
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  pointer-events: auto;
  position: relative;
  overflow: hidden;
}

.notification::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 4px;
  background: var(--accent-color, #007acc);
}

/* 通知类型样式 */
.notification-success::before {
  background: #52c41a;
}

.notification-error::before {
  background: #ff4d4f;
}

.notification-warning::before {
  background: #faad14;
}

.notification-info::before {
  background: #1890ff;
}

.notification-loading::before {
  background: #1890ff;
}

/* 图标样式 */
.notification-icon {
  flex-shrink: 0;
  width: 24px;
  height: 24px;
  margin-right: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.notification-icon-symbol {
  font-size: 16px;
  font-weight: bold;
}

.notification-success .notification-icon-symbol {
  color: #52c41a;
}

.notification-error .notification-icon-symbol {
  color: #ff4d4f;
}

.notification-warning .notification-icon-symbol {
  color: #faad14;
}

.notification-info .notification-icon-symbol {
  color: #1890ff;
}

/* 加载动画 */
.loading-spinner {
  width: 16px;
  height: 16px;
  border: 2px solid #f3f3f3;
  border-top: 2px solid #1890ff;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

/* 内容样式 */
.notification-content {
  flex: 1;
  min-width: 0;
}

.notification-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-color, #333333);
  margin-bottom: 4px;
  line-height: 1.4;
}

.notification-message {
  font-size: 13px;
  color: var(--text-color-secondary, #666666);
  line-height: 1.4;
  word-wrap: break-word;
}

/* 关闭按钮 */
.notification-close {
  flex-shrink: 0;
  width: 20px;
  height: 20px;
  margin-left: 8px;
  background: none;
  border: none;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  color: var(--text-color-secondary, #999999);
  transition: all 0.2s ease;
}

.notification-close:hover {
  background: var(--hover-bg-color, #f5f5f5);
  color: var(--text-color, #333333);
}

.close-icon {
  font-size: 18px;
  line-height: 1;
}

/* 过渡动画 */
.notification-enter-active {
  transition: all 0.3s ease-out;
}

.notification-leave-active {
  transition: all 0.3s ease-in;
}

.notification-enter-from {
  opacity: 0;
  transform: translateX(100%);
}

.notification-leave-to {
  opacity: 0;
  transform: translateX(100%);
}

.notification-move {
  transition: transform 0.3s ease;
}

/* 深色主题适配 */
@media (prefers-color-scheme: dark) {
  .notification {
    background: var(--bg-color-dark, #2d2d2d);
    border-color: var(--border-color-dark, #404040);
    color: var(--text-color-dark, #ffffff);
  }
  
  .notification-title {
    color: var(--text-color-dark, #ffffff);
  }
  
  .notification-message {
    color: var(--text-color-secondary-dark, #cccccc);
  }
  
  .notification-close {
    color: var(--text-color-secondary-dark, #999999);
  }
  
  .notification-close:hover {
    background: var(--hover-bg-color-dark, #404040);
    color: var(--text-color-dark, #ffffff);
  }
}

/* 响应式设计 */
@media (max-width: 768px) {
  .notification-container {
    left: 20px;
    right: 20px;
    bottom: 20px;
    top: auto;
  }
  
  .notification {
    min-width: auto;
    max-width: none;
  }
}
</style>
