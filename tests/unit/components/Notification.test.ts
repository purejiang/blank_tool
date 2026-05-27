import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'

// Use vi.hoisted so the variable is available when the hoisted vi.mock runs
const { mockNotificationService } = vi.hoisted(() => ({
  mockNotificationService: {
    addListener: vi.fn(),
    removeListener: vi.fn(),
  },
}))

vi.mock('@services/ServiceManager', () => ({
  default: {
    getServiceSync: vi.fn(() => mockNotificationService),
    getService: vi.fn().mockResolvedValue(mockNotificationService),
    register: vi.fn(),
  },
}))

import Notification from '@/renderer/components/common/Notification.vue'

describe('Notification', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('mounts and registers listeners', async () => {
    const wrapper = mount(Notification, {
      global: {
        stubs: {
          Teleport: { template: '<div><slot /></div>' },
          TransitionGroup: { template: '<div><slot /></div>' },
        },
      },
    })
    await nextTick()
    await nextTick()

    expect(mockNotificationService.addListener).toHaveBeenCalledWith('show', expect.any(Function))
    expect(mockNotificationService.addListener).toHaveBeenCalledWith('hide', expect.any(Function))
    expect(mockNotificationService.addListener).toHaveBeenCalledWith('update', expect.any(Function))
    expect(mockNotificationService.addListener).toHaveBeenCalledWith('clear', expect.any(Function))
  })

  it('shows notification when showNotification is called', async () => {
    const wrapper = mount(Notification, {
      global: {
        stubs: {
          Teleport: { template: '<div><slot /></div>' },
          TransitionGroup: { template: '<div><slot /></div>' },
        },
      },
    })
    await nextTick()
    await nextTick()

    // Call show via exposed method
    wrapper.vm.showNotification({
      id: 'notif-1',
      type: 'success',
      title: 'Test Title',
      message: 'Test Message',
    })
    await nextTick()

    expect(wrapper.text()).toContain('Test Title')
    expect(wrapper.text()).toContain('Test Message')
  })

  it('shows notification icon based on type', async () => {
    const wrapper = mount(Notification, {
      global: {
        stubs: {
          Teleport: { template: '<div><slot /></div>' },
          TransitionGroup: { template: '<div><slot /></div>' },
        },
      },
    })
    await nextTick()
    await nextTick()

    wrapper.vm.showNotification({
      id: 'notif-2',
      type: 'error',
      title: 'Error',
      message: 'Something went wrong',
    })
    await nextTick()

    expect(wrapper.find('.notification-error').exists()).toBe(true)
  })

  it('hides notification when hideNotification is called', async () => {
    const wrapper = mount(Notification, {
      global: {
        stubs: {
          Teleport: { template: '<div><slot /></div>' },
          TransitionGroup: { template: '<div><slot /></div>' },
        },
      },
    })
    await nextTick()
    await nextTick()

    wrapper.vm.showNotification({
      id: 'notif-3',
      type: 'info',
      title: 'Info',
      message: 'Information',
    })
    await nextTick()
    expect(wrapper.text()).toContain('Info')

    wrapper.vm.hideNotification('notif-3')
    await nextTick()
    expect(wrapper.text()).not.toContain('Info')
  })

  it('updates notification content', async () => {
    const wrapper = mount(Notification, {
      global: {
        stubs: {
          Teleport: { template: '<div><slot /></div>' },
          TransitionGroup: { template: '<div><slot /></div>' },
        },
      },
    })
    await nextTick()
    await nextTick()

    wrapper.vm.showNotification({
      id: 'notif-4',
      type: 'info',
      title: 'Loading',
      message: 'Please wait...',
    })
    await nextTick()

    wrapper.vm.updateNotification('notif-4', {
      title: 'Complete',
      message: 'Done!',
    })
    await nextTick()

    expect(wrapper.text()).toContain('Complete')
    expect(wrapper.text()).toContain('Done!')
  })

  it('clears all notifications', async () => {
    const wrapper = mount(Notification, {
      global: {
        stubs: {
          Teleport: { template: '<div><slot /></div>' },
          TransitionGroup: { template: '<div><slot /></div>' },
        },
      },
    })
    await nextTick()
    await nextTick()

    wrapper.vm.showNotification({ id: 'n1', type: 'info', title: 'One', message: '' })
    wrapper.vm.showNotification({ id: 'n2', type: 'info', title: 'Two', message: '' })
    await nextTick()
    expect(wrapper.text()).toContain('One')
    expect(wrapper.text()).toContain('Two')

    wrapper.vm.clearAllNotifications()
    await nextTick()
    expect(wrapper.text()).not.toContain('One')
    expect(wrapper.text()).not.toContain('Two')
  })

  it('renders close button for non-loading notifications', async () => {
    const wrapper = mount(Notification, {
      global: {
        stubs: {
          Teleport: { template: '<div><slot /></div>' },
          TransitionGroup: { template: '<div><slot /></div>' },
        },
      },
    })
    await nextTick()
    await nextTick()

    wrapper.vm.showNotification({
      id: 'notif-5',
      type: 'success',
      title: 'Success',
      message: 'Done',
    })
    await nextTick()

    expect(wrapper.find('.notification-close').exists()).toBe(true)
  })
})
