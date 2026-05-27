import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import DeviceList from '@/renderer/components/device/DeviceList.vue'

describe('DeviceList', () => {
  const mockDevices = [
    { id: 'abc123', name: 'Pixel 6', status: 'online' },
    { id: 'def456', name: 'Nexus 5', status: 'offline' },
  ]

  it('renders device items', () => {
    const wrapper = mount(DeviceList, {
      props: { devices: mockDevices, selectedId: '' },
    })
    const items = wrapper.findAll('.device-item')
    expect(items).toHaveLength(2)
    expect(items[0].text()).toContain('Pixel 6')
    expect(items[0].text()).toContain('abc123')
  })

  it('shows empty state when no devices', () => {
    const wrapper = mount(DeviceList, {
      props: { devices: [], selectedId: '' },
    })
    expect(wrapper.find('.empty-state').exists()).toBe(true)
    expect(wrapper.find('.empty-state').text()).toBe('No devices connected')
  })

  it('emits select event on click', async () => {
    const wrapper = mount(DeviceList, {
      props: { devices: mockDevices, selectedId: '' },
    })
    await wrapper.find('.device-item').trigger('click')
    expect(wrapper.emitted('select')).toBeTruthy()
    expect(wrapper.emitted('select')![0]).toEqual(['abc123'])
  })

  it('applies active class to selected device', () => {
    const wrapper = mount(DeviceList, {
      props: { devices: mockDevices, selectedId: 'abc123' },
    })
    const activeItems = wrapper.findAll('.device-item.active')
    expect(activeItems).toHaveLength(1)
    expect(activeItems[0].text()).toContain('Pixel 6')
  })

  it('renders device status class', () => {
    const wrapper = mount(DeviceList, {
      props: { devices: mockDevices, selectedId: '' },
    })
    const statusSpans = wrapper.findAll('.device-status')
    expect(statusSpans[0].classes()).toContain('online')
    expect(statusSpans[1].classes()).toContain('offline')
  })

  it('renders unknown status when no status provided', () => {
    const wrapper = mount(DeviceList, {
      props: {
        devices: [{ id: 'test', name: 'Test' }],
        selectedId: '',
      },
    })
    expect(wrapper.find('.device-status').text()).toBe('unknown')
  })

  it('uses device id as name fallback', () => {
    const wrapper = mount(DeviceList, {
      props: {
        devices: [{ id: 'serial-only', status: 'online' }],
        selectedId: '',
      },
    })
    expect(wrapper.find('.device-name').text()).toBe('serial-only')
  })
})
