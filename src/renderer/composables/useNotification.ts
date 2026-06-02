import { ref } from 'vue'
import { useNotification as useNaiveNotification } from 'naive-ui'

const idCounter = ref(0)
const loadingMap = new Map<number, { destroy: () => void }>()

export function useNotification() {
  const notify = useNaiveNotification()

  const showSuccess = (title: string, message = '', duration = 5000) => {
    notify.success({ title, content: message, duration })
    return 0
  }

  const showError = (title: string, message = '', duration = 8000) => {
    notify.error({ title, content: message, duration })
    return 0
  }

  const showWarning = (title: string, message = '', duration = 8000) => {
    notify.warning({ title, content: message, duration })
    return 0
  }

  const showInfo = (title: string, message = '', duration = 5000) => {
    notify.info({ title, content: message, duration })
    return 0
  }

  const showLoading = (title: string, message = '') => {
    const id = ++idCounter.value
    const n = notify.info({ title, content: message, duration: 0 })
    loadingMap.set(id, n)
    return id
  }

  const hide = (id?: number) => {
    if (id !== undefined && loadingMap.has(id)) {
      loadingMap.get(id)!.destroy()
      loadingMap.delete(id)
    } else {
      notify.destroyAll()
    }
  }

  const updateLoading = (id: number, title?: string, message?: string) => {
    if (loadingMap.has(id)) {
      loadingMap.get(id)!.destroy()
    }
    const n = notify.info({ title: title || '', content: message || '', duration: 0 })
    loadingMap.set(id, n)
  }

  const completeLoading = (id: number, title: string, message = '', duration = 5000) => {
    if (loadingMap.has(id)) {
      loadingMap.get(id)!.destroy()
      loadingMap.delete(id)
    }
    notify.success({ title, content: message, duration })
    return 0
  }

  const failLoading = (id: number, title: string, message = '', duration = 8000) => {
    if (loadingMap.has(id)) {
      loadingMap.get(id)!.destroy()
      loadingMap.delete(id)
    }
    notify.error({ title, content: message, duration })
    return 0
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
    failLoading,
  }
}
