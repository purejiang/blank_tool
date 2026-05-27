import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import DeviceActionBar from '@/renderer/components/device/DeviceActionBar.vue'

describe('DeviceActionBar', () => {
  const createWrapper = (props = {}) =>
    mount(DeviceActionBar, {
      props: {
        hasSelection: true,
        isMonitoring: false,
        connectionText: 'Connected 2 devices',
        connectionConnected: true,
        ...props,
      },
    })

  it('renders connection status', () => {
    const wrapper = createWrapper()
    expect(wrapper.text()).toContain('Connected 2 devices')
  })

  it('shows connected indicator when connected', () => {
    const wrapper = createWrapper()
    expect(wrapper.find('.status-connected').exists()).toBe(true)
  })

  it('shows disconnected indicator when not connected', () => {
    const wrapper = createWrapper({ connectionConnected: false })
    expect(wrapper.find('.status-disconnected').exists()).toBe(true)
    expect(wrapper.find('.status-connected').exists()).toBe(false)
  })

  it('emits refresh on button click', async () => {
    const wrapper = createWrapper()
    const btn = wrapper.find('.btn')
    await btn.trigger('click')
    expect(wrapper.emitted('refresh')).toBeTruthy()
  })

  it('emits toggleMonitoring on toggle change', async () => {
    const wrapper = createWrapper()
    const checkbox = wrapper.find('input[type="checkbox"]')
    await checkbox.trigger('change')
    expect(wrapper.emitted('toggleMonitoring')).toBeTruthy()
  })

  it('renders auto toggle correctly when monitoring', () => {
    const wrapper = createWrapper({ isMonitoring: true })
    const checkbox = wrapper.find('input[type="checkbox"]')
    expect((checkbox.element as HTMLInputElement).checked).toBe(true)
  })

  it('renders auto toggle correctly when not monitoring', () => {
    const wrapper = createWrapper({ isMonitoring: false })
    const checkbox = wrapper.find('input[type="checkbox"]')
    expect((checkbox.element as HTMLInputElement).checked).toBe(false)
  })

  it('displays Auto label', () => {
    const wrapper = createWrapper()
    expect(wrapper.text()).toContain('Auto')
  })

  it('displays Refresh button', () => {
    const wrapper = createWrapper()
    expect(wrapper.text()).toContain('Refresh')
  })
})
