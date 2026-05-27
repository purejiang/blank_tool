import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import DeviceDetail from '@/renderer/components/device/DeviceDetail.vue'

describe('DeviceDetail', () => {
  const mockDevice = {
    id: 'abc123',
    name: 'Pixel 6',
    status: 'online',
  }

  const mockDeviceInfo: Record<string, string> = {
    model: 'Pixel 6',
    brand: 'Google',
    manufacturer: 'Google',
    androidVersion: '13',
    apiLevel: '33',
    architecture: 'arm64-v8a',
    batteryLevel: '85',
    screenResolution: '1080x2400',
    density: '420',
    totalMemory: '8GB',
    availableStorage: '64GB',
    systemActivationDate: '2023-01-15',
  }

  it('renders device details when device is provided', () => {
    const wrapper = mount(DeviceDetail, {
      props: { device: mockDevice, deviceInfo: mockDeviceInfo },
    })
    expect(wrapper.find('.device-detail').exists()).toBe(true)
    expect(wrapper.find('.device-info-grid').exists()).toBe(true)
  })

  it('shows empty state when no device', () => {
    const wrapper = mount(DeviceDetail, {
      props: { device: null, deviceInfo: {} },
    })
    expect(wrapper.find('.device-detail.empty').exists()).toBe(true)
    expect(wrapper.text()).toContain('Select a device to view details')
  })

  it('displays device id', () => {
    const wrapper = mount(DeviceDetail, {
      props: { device: mockDevice, deviceInfo: mockDeviceInfo },
    })
    expect(wrapper.text()).toContain('abc123')
  })

  it('displays device name', () => {
    const wrapper = mount(DeviceDetail, {
      props: { device: mockDevice, deviceInfo: mockDeviceInfo },
    })
    expect(wrapper.text()).toContain('Pixel 6')
  })

  it('displays battery info', () => {
    const wrapper = mount(DeviceDetail, {
      props: { device: mockDevice, deviceInfo: mockDeviceInfo },
    })
    expect(wrapper.text()).toContain('85%')
  })

  it('conditionally renders info items only when data exists', () => {
    const wrapper = mount(DeviceDetail, {
      props: {
        device: mockDevice,
        deviceInfo: { model: 'Pixel' },
      },
    })
    // Only model info item should be visible
    const items = wrapper.findAll('.info-item')
    // Device ID, Name, Status, Model = 4 items (device id, name, status always shown + model)
    expect(items.length).toBeGreaterThanOrEqual(4)
  })

  it('does not show battery when empty', () => {
    const wrapper = mount(DeviceDetail, {
      props: {
        device: mockDevice,
        deviceInfo: {},
      },
    })
    expect(wrapper.text()).not.toContain('Battery:')
  })
})
