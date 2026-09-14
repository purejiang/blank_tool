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
            <!-- 进度条 -->
            <div v-if="notification.progress !== undefined" class="notification-progress">
              <div class="notification-progress-track">
                <div
                  class="notification-progress-fill"
                  :style="{ width: Math.min(100, Math.max(0, notification.progress)) + '%' }"
                ></div>
              </div>
            </div>
            <!-- 操作按钮 -->
            <div v-if="notification.actions && notification.actions.length > 0" class="notification-actions">
              <button
                v-for="(action, idx) in notification.actions"
                :key="idx"
                :class="['notification-action-btn', action.type === 'primary' ? 'primary' : 'default']"
                @click="action.onClick"
              >
                {{ action.label }}
              </button>
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
import { log } from '@utils/logger'

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
    duration: notificationData.duration ?? 5000,
    progress: notificationData.progress,
    actions: notificationData.actions,
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
    log.error('Failed to get notification service:', error)
  }

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
  background: var(--app-card-bg);
  border: 1px solid var(--app-card-border);
  border-radius: var(--app-radius-md);
  box-shadow: var(--app-shadow-md);
  pointer-events: auto;
  position: relative;
  overflow: hidden;
}

/* 左侧色条：由通知类型决定，默认信息蓝 */
.notification::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 4px;
  background: var(--app-blue);
}

/* 通知类型样式 */
.notification-success::before { background: var(--app-green); }
.notification-error::before { background: var(--app-red); }
.notification-warning::before { background: var(--app-yellow); }
.notification-info::before { background: var(--app-blue); }
.notification-loading::before { background: var(--app-blue); }

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

.notification-success .notification-icon-symbol { color: var(--app-green); }
.notification-error .notification-icon-symbol { color: var(--app-red); }
.notification-warning .notification-icon-symbol { color: var(--app-yellow); }
.notification-info .notification-icon-symbol { color: var(--app-blue); }

/* 加载动画 */
.loading-spinner {
  width: 16px;
  height: 16px;
  border: 2px solid var(--app-card-border);
  border-top: 2px solid var(--app-blue);
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
  color: var(--app-text-primary);
  margin-bottom: 4px;
  line-height: 1.4;
}

.notification-message {
  font-size: 13px;
  color: var(--app-text-muted);
  line-height: 1.4;
  word-wrap: break-word;
}

/* 进度条 */
.notification-progress {
  margin-top: 10px;
}

.notification-progress-track {
  width: 100%;
  height: 4px;
  background: var(--app-storage-bg);
  border-radius: 2px;
  overflow: hidden;
}

.notification-progress-fill {
  height: 100%;
  background: var(--app-blue);
  border-radius: 2px;
  transition: width 0.3s ease;
}

/* 操作按钮 */
.notification-actions {
  display: flex;
  gap: 8px;
  margin-top: 10px;
  justify-content: flex-end;
}

.notification-action-btn {
  padding: 5px 14px;
  font-size: 12px;
  border-radius: 4px;
  border: 1px solid transparent;
  cursor: pointer;
  transition: all 0.2s ease;
  font-weight: 500;
}

.notification-action-btn.default {
  background: transparent;
  border-color: var(--app-card-border);
  color: var(--app-text-primary);
}

.notification-action-btn.default:hover {
  background: var(--app-hover);
}

.notification-action-btn.primary {
  background: var(--app-blue);
  color: #fff;
}

.notification-action-btn.primary:hover {
  background: var(--app-blue-hover);
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
  color: var(--app-text-dim);
  transition: all 0.2s ease;
}

.notification-close:hover {
  background: var(--app-hover);
  color: var(--app-text-primary);
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

/* 深色适配由 --app-* token 在 themes.css 里统一切换，
   这里不再用 prefers-color-scheme —— 应用主题跟随的是 data-theme，
   两者不一致时通知会跟界面撞色。 */

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
