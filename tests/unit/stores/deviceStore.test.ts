import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useDeviceStore } from '@/renderer/stores/deviceStore'

describe('deviceStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  describe('initial state', () => {
    it('has empty devices array', () => {
      const store = useDeviceStore()
      expect(store.devices).toEqual([])
    })

    it('has empty selectedDeviceId', () => {
      const store = useDeviceStore()
      expect(store.selectedDeviceId).toBe('')
    })

    it('has null selectedDevice', () => {
      const store = useDeviceStore()
      expect(store.selectedDevice).toBeNull()
    })

    it('has deviceCount of 0', () => {
      const store = useDeviceStore()
      expect(store.deviceCount).toBe(0)
    })

    it('has disconnected connectionStatus', () => {
      const store = useDeviceStore()
      expect(store.connectionStatus.connected).toBe(false)
    })

    it('has empty logcat output', () => {
      const store = useDeviceStore()
      expect(store.logcatOutput).toEqual([])
    })

    it('is not monitoring', () => {
      const store = useDeviceStore()
      expect(store.isMonitoring).toBe(false)
    })

    it('logcat is not running', () => {
      const store = useDeviceStore()
      expect(store.isLogcatRunning).toBe(false)
    })
  })

  describe('setDevices / updateDevices', () => {
    it('updates devices with valid device objects', () => {
      const store = useDeviceStore()
      const devices = [
        { id: 'abc', name: 'Pixel', status: 'online' },
        { id: 'def', name: 'Nexus', status: 'offline' },
      ]
      store.updateDevices(devices)
      expect(store.devices).toHaveLength(2)
      expect(store.devices[0].id).toBe('abc')
      expect(store.deviceCount).toBe(2)
      expect(store.connectionStatus.connected).toBe(true)
    })

    it('handles string-only device list', () => {
      const store = useDeviceStore()
      store.updateDevices(['serial1', 'serial2'])
      expect(store.devices).toHaveLength(2)
      expect(store.devices[0].id).toBe('serial1')
      expect(store.devices[0].name).toBe('serial1')
      expect(store.devices[0].status).toBe('online')
    })

    it('filters out null/undefined entries', () => {
      const store = useDeviceStore()
      store.updateDevices([null, undefined, { id: 'abc' }])
      expect(store.devices).toHaveLength(1)
      expect(store.devices[0].id).toBe('abc')
    })

    it('handles empty array', () => {
      const store = useDeviceStore()
      store.updateDevices([])
      expect(store.devices).toEqual([])
    })

    it('handles non-array input', () => {
      const store = useDeviceStore()
      store.updateDevices(null as unknown as unknown[])
      expect(store.devices).toEqual([])
    })

    it('clears selection when selected device removed', () => {
      const store = useDeviceStore()
      store.updateDevices([{ id: 'abc' }])
      store.selectDevice('abc')
      expect(store.selectedDeviceId).toBe('abc')
      store.updateDevices([{ id: 'xyz' }])
      expect(store.selectedDeviceId).toBe('')
    })
  })

  describe('selectDevice', () => {
    it('sets selectedDeviceId', () => {
      const store = useDeviceStore()
      store.updateDevices([{ id: 'abc' }])
      store.selectDevice('abc')
      expect(store.selectedDeviceId).toBe('abc')
      expect(store.selectedDevice).toEqual({ id: 'abc' })
    })

    it('handles empty string', () => {
      const store = useDeviceStore()
      store.selectDevice('')
      expect(store.selectedDeviceId).toBe('')
    })
  })

  describe('updateDeviceInfo', () => {
    it('updates device info fields', () => {
      const store = useDeviceStore()
      store.updateDeviceInfo({
        model: 'Pixel 6',
        brand: 'Google',
        androidVersion: '13',
      })
      expect(store.deviceInfo.model).toBe('Pixel 6')
      expect(store.deviceInfo.brand).toBe('Google')
      expect(store.deviceInfo.androidVersion).toBe('13')
    })

    it('handles snake_case keys', () => {
      const store = useDeviceStore()
      store.updateDeviceInfo({
        android_version: '12',
        api_level: '31',
      })
      expect(store.deviceInfo.androidVersion).toBe('12')
      expect(store.deviceInfo.apiLevel).toBe('31')
    })

    it('handles null input gracefully', () => {
      const store = useDeviceStore()
      store.updateDeviceInfo(null)
      // All deviceInfo values should remain empty
      expect(store.deviceInfo.model).toBe('')
    })
  })

  describe('clearLogcat', () => {
    it('clears logcat output', () => {
      const store = useDeviceStore()
      store.logcatOutput = ['line1', 'line2']
      store.clearLogcat()
      expect(store.logcatOutput).toEqual([])
    })
  })
})
