import { inject } from 'vue'

export function useNotification() {
  const notificationServiceRef = inject('notificationService', null)

  // Helper to access the service instance safely
  const getService = () => {
    return notificationServiceRef ? notificationServiceRef.value : null
  }

  const showSuccess = (title, message = '', duration = 3000) => {
    const service = getService()
    if (service) {
      return service.show('success', title, message, duration)
    }
    console.warn('NotificationService not available')
    return null
  }

  const showError = (title, message = '', duration = 5000) => {
    const service = getService()
    if (service) {
      return service.show('error', title, message, duration)
    }
    console.error('NotificationService not available', title, message)
    return null
  }

  const showWarning = (title, message = '', duration = 5000) => {
    const service = getService()
    if (service) {
      return service.show('warning', title, message, duration)
    }
    console.warn('NotificationService not available', title, message)
    return null
  }

  const showInfo = (title, message = '', duration = 3000) => {
    const service = getService()
    if (service) {
      return service.show('info', title, message, duration)
    }
    return null
  }

  const showLoading = (title, message = '') => {
    const service = getService()
    if (service) {
      return service.show('loading', title, message, 0)
    }
    return null
  }

  const hide = (id) => {
    const service = getService()
    if (service) {
      service.hide(id)
    }
  }

  const updateLoading = (id, title, message) => {
    const service = getService()
    if (service) {
      service.update(id, { title, message })
    }
  }

  const completeLoading = (id, title, message = '', duration = 3000) => {
    const service = getService()
    if (service) {
      // First update content
      service.update(id, { title, message, type: 'success', duration })
      // Then set a timeout to hide it, since changing type doesn't automatically trigger auto-close if it was 0 before
      setTimeout(() => {
        service.hide(id)
      }, duration)
    }
  }

  const failLoading = (id, title, message = '', duration = 5000) => {
    const service = getService()
    if (service) {
      service.update(id, { title, message, type: 'error', duration })
      setTimeout(() => {
        service.hide(id)
      }, duration)
    }
  }

  return {
    showSuccess,
    showError,
    showWarning,
    showInfo,
    showLoading,
    hide,
    updateLoading,
    completeLoading,
    failLoading
  }
}
