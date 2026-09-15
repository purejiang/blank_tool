/**
 * ToolInstallModal unit tests.
 *
 * The modal is the one-stop installer for the automation feature's two
 * optional dependencies: mitmproxy (PC side, traffic capture) and
 * ADBKeyBoard (device side, Chinese input).
 *
 * vue-i18n is mocked to an identity t() (keys render as themselves); both
 * DI services (automation / system) are mocked through ServiceManager —
 * the same DI path the component uses. The teleport stub keeps n-modal's
 * content inside the wrapper so it is queryable without document.body.
 *
 * Terminal-promise contract (review M1): install* resolves with the
 * `complete` payload (including the degraded form) and rejects on the
 * `error` event — the UI here is driven exclusively by that promise.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises, type VueWrapper, type DOMWrapper } from '@vue/test-utils'
import { NProgress, NTooltip } from 'naive-ui'

// ---------------------------------------------------------------- mocks --
const mockAutomation = {
  getTrafficStatus: vi.fn(),
  getImeStatus: vi.fn(),
  installMitmproxy: vi.fn(),
  installIme: vi.fn(),
  installCa: vi.fn(),
  clearTrafficCache: vi.fn(),
}
const mockSystem = {
  selectFile: vi.fn(),
  openPath: vi.fn(),
  copyText: vi.fn(),
}

vi.mock('@services/ServiceManager', () => ({
  default: {
    getService: vi.fn(async (name: string) =>
      name === 'automation' ? mockAutomation : mockSystem),
  },
}))

vi.mock('vue-i18n', async (importOriginal) => {
  const actual = await importOriginal<typeof import('vue-i18n')>()
  return { ...actual, useI18n: () => ({ t: (k: string) => k }) }
})

import ToolInstallModal from '@/renderer/components/automation/ToolInstallModal.vue'

const TRAFFIC_READY = {
  installed: true, ready: true, lib_path: 'D:/rt/mitmproxy/lib',
  python_mismatch: null, ca_cert_exists: true,
}
const TRAFFIC_MISSING = {
  installed: false, ready: false, lib_path: '',
  python_mismatch: null, ca_cert_exists: false,
}
const TRAFFIC_MISMATCH = {
  installed: true, ready: false, lib_path: 'D:/rt/mitmproxy/lib',
  python_mismatch: '3.11 vs 3.12', ca_cert_exists: false,
}
const IME_OK = {
  device_id: 'emulator-5554', package: 'com.android.adbkeyboard/.AdbIME',
  installed: true, active: true,
}
const IME_MISSING = {
  device_id: 'emulator-5554', package: '', installed: false, active: false,
}
const DEGRADED = {
  success: false,
  degraded: true,
  manual_command: '"C:/rt/python/python.exe" -m pip install --target "D:/rt/mitmproxy/lib" --upgrade mitmproxy',
  lib_path: 'D:/rt/mitmproxy/lib',
  python_bin: 'C:/rt/python/python.exe',
}

// ------------------------------------------------------------- helpers --
function mountModal(props: Record<string, unknown> = {}) {
  return mount(ToolInstallModal, {
    props: { show: false, deviceId: 'emulator-5554', ...props },
    global: { stubs: { teleport: true } },
  })
}

async function open(w: VueWrapper) {
  await w.setProps({ show: true })
  await flushPromises()
}

/** naive-ui marks disabled buttons with the native attr or the class */
function isDisabled(btn: DOMWrapper<Element>): boolean {
  return btn.attributes('disabled') !== undefined
    || btn.classes().includes('n-button--disabled')
}

/** Flat text of a vnode tree (slot render result). */
function vnodeText(nodes: unknown[]): string {
  let out = ''
  const walk = (ns: unknown[]) => {
    for (const v of ns ?? []) {
      if (v == null || v === '') continue
      if (typeof v === 'string') { out += v; continue }
      if (Array.isArray(v)) { walk(v); continue }
      const anyV = v as any
      if (typeof anyV.children === 'string') out += anyV.children
      else if (Array.isArray(anyV.children)) walk(anyV.children)
    }
  }
  walk(nodes)
  return out
}

/** The NTooltip wrapping the given button (tooltip content is slot-only,
 *  so hover-free assertions read the default slot render result). */
function tooltipOf(w: VueWrapper, btn: DOMWrapper<Element>): VueWrapper | undefined {
  return w.findAllComponents(NTooltip)
    .find((t) => t.element === btn.element || t.element.contains(btn.element))
}

function tooltipContent(tip: VueWrapper | undefined): string {
  if (!tip) return ''
  const slots = (tip.vm as any).$slots ?? {}
  const fn = slots.default
  return typeof fn === 'function' ? vnodeText(fn() ?? []) : ''
}

beforeEach(() => {
  vi.clearAllMocks()
  mockAutomation.getTrafficStatus.mockResolvedValue(TRAFFIC_READY)
  mockAutomation.getImeStatus.mockResolvedValue(IME_MISSING)
})

// --------------------------------------------------------------- tests --
describe('ToolInstallModal — status rendering', () => {
  it('force-probes BOTH statuses on open (getTrafficStatus(true) + getImeStatus(deviceId))', async () => {
    const w = mountModal()
    await open(w)
    expect(mockAutomation.getTrafficStatus).toHaveBeenCalledTimes(1)
    expect(mockAutomation.getTrafficStatus).toHaveBeenCalledWith(true)
    expect(mockAutomation.getImeStatus).toHaveBeenCalledWith('emulator-5554')
  })

  it('renders the ready state in both sections when both tools are installed', async () => {
    mockAutomation.getImeStatus.mockResolvedValue(IME_OK)
    const w = mountModal()
    await open(w)

    const traffic = w.get('[data-testid="traffic-section"]')
    expect(traffic.text()).toContain('automation.tools.statusReady')
    expect(traffic.text()).toContain('D:/rt/mitmproxy/lib')

    const ime = w.get('[data-testid="ime-section"]')
    expect(ime.text()).toContain('automation.tools.imeInstalled')
    expect(ime.text()).toContain('automation.tools.imeActive')
  })

  it('renders not-installed / missing-cert states and the auto-generate hint', async () => {
    mockAutomation.getTrafficStatus.mockResolvedValue(TRAFFIC_MISSING)
    mockAutomation.getImeStatus.mockResolvedValue(IME_MISSING)
    const w = mountModal()
    await open(w)

    const traffic = w.get('[data-testid="traffic-section"]')
    expect(traffic.text()).toContain('automation.tools.statusNotInstalled')
    expect(traffic.text()).toContain('automation.tools.caAutoHint')
    // no cert → the derived cert path must not render
    expect(traffic.text()).not.toContain('mitmproxy-ca-cert.pem')

    const ime = w.get('[data-testid="ime-section"]')
    expect(ime.text()).toContain('automation.tools.imeNotInstalled')
    expect(ime.text()).not.toContain('automation.tools.imeActive')
  })

  it('renders the version-mismatch state and the reinstall label', async () => {
    mockAutomation.getTrafficStatus.mockResolvedValue(TRAFFIC_MISMATCH)
    const w = mountModal()
    await open(w)

    const traffic = w.get('[data-testid="traffic-section"]')
    expect(traffic.text()).toContain('automation.tools.statusVersionMismatch')
    expect(traffic.text()).toContain('automation.tools.reinstall')
  })

  it('renders an unknown state without crashing when the probe fails (null)', async () => {
    mockAutomation.getTrafficStatus.mockResolvedValue(null)
    const w = mountModal()
    await open(w)

    expect(w.get('[data-testid="tool-install-modal"]').exists()).toBe(true)
    expect(w.get('[data-testid="traffic-section"]').text())
      .toContain('automation.tools.statusUnknown')
  })
})

describe('ToolInstallModal — degraded manual command (review M1 consumer)', () => {
  it('renders the manual-command block with the EXACT command; no changed emit', async () => {
    mockAutomation.getTrafficStatus.mockResolvedValue(TRAFFIC_MISSING)
    mockAutomation.installMitmproxy.mockResolvedValue(DEGRADED)
    const w = mountModal()
    await open(w)

    await w.get('[data-testid="install-mitmproxy-btn"]').trigger('click')
    await flushPromises()

    const block = w.get('[data-testid="manual-command"]')
    expect(block.text()).toContain(DEGRADED.manual_command)
    expect(w.emitted('changed')).toBeUndefined()
  })

  it('degraded block offers copy + open-runtime-folder via SystemService', async () => {
    mockAutomation.getTrafficStatus.mockResolvedValue(TRAFFIC_MISSING)
    mockAutomation.installMitmproxy.mockResolvedValue(DEGRADED)
    const w = mountModal()
    await open(w)

    await w.get('[data-testid="install-mitmproxy-btn"]').trigger('click')
    await flushPromises()

    const btn = w.get('[data-testid="copy-command-btn"]')
    await btn.trigger('click')
    expect(mockSystem.copyText).toHaveBeenCalledWith(DEGRADED.manual_command)

    await w.get('[data-testid="open-runtime-folder-btn"]').trigger('click')
    // parent dir of lib_path (reveal semantics when openPath resolves it)
    expect(mockSystem.openPath).toHaveBeenCalledWith('D:/rt/mitmproxy')
  })
})

describe('ToolInstallModal — terminal promise drives the UI', () => {
  it('reject → error surfaced, button re-enabled, changed NOT emitted (mitmproxy)', async () => {
    mockAutomation.getTrafficStatus.mockResolvedValue(TRAFFIC_MISSING)
    mockAutomation.installMitmproxy.mockRejectedValue(new Error('capture is active'))
    const w = mountModal()
    await open(w)

    await w.get('[data-testid="install-mitmproxy-btn"]').trigger('click')
    await flushPromises()

    expect(w.get('[data-testid="mitm-error"]').text()).toContain('capture is active')
    const btn = w.get('[data-testid="install-mitmproxy-btn"]')
    expect(isDisabled(btn)).toBe(false)
    expect(w.emitted('changed')).toBeUndefined()
  })

  it('reject → error surfaced, button re-enabled, changed NOT emitted (ADBKeyBoard)', async () => {
    mockAutomation.installIme.mockRejectedValue(new Error('download failed'))
    const w = mountModal()
    await open(w)

    await w.get('[data-testid="install-ime-btn"]').trigger('click')
    await flushPromises()

    expect(w.get('[data-testid="ime-error"]').text()).toContain('download failed')
    expect(isDisabled(w.get('[data-testid="install-ime-btn"]'))).toBe(false)
    expect(w.emitted('changed')).toBeUndefined()
  })

  it('mitmproxy success → changed emitted + FORCE re-probe (not cache)', async () => {
    mockAutomation.getTrafficStatus.mockResolvedValue(TRAFFIC_MISSING)
    mockAutomation.installMitmproxy.mockResolvedValue({
      success: true, ready: true, lib_path: 'D:/rt/mitmproxy/lib',
      python_mismatch: null, ca_cert_exists: false,
    })
    const w = mountModal()
    await open(w)
    expect(mockAutomation.getTrafficStatus).toHaveBeenCalledTimes(1)

    await w.get('[data-testid="install-mitmproxy-btn"]').trigger('click')
    await flushPromises()

    expect(w.emitted('changed')).toHaveLength(1)
    expect(mockAutomation.getTrafficStatus).toHaveBeenCalledTimes(2)
    expect(mockAutomation.getTrafficStatus).toHaveBeenNthCalledWith(2, true)
  })

  it('ADBKeyBoard success → changed emitted + re-probe', async () => {
    mockAutomation.installIme.mockResolvedValue({ success: true, installed: true })
    const w = mountModal()
    await open(w)

    await w.get('[data-testid="install-ime-btn"]').trigger('click')
    await flushPromises()

    expect(w.emitted('changed')).toHaveLength(1)
    expect(mockAutomation.getImeStatus).toHaveBeenCalledTimes(2)
  })

  it('CA install success → changed emitted', async () => {
    mockAutomation.installCa.mockResolvedValue({ success: true, already_installed: false })
    const w = mountModal()
    await open(w)

    await w.get('[data-testid="install-ca-btn"]').trigger('click')
    await flushPromises()

    expect(mockAutomation.installCa).toHaveBeenCalledWith('emulator-5554')
    expect(w.emitted('changed')).toHaveLength(1)
  })

  it('CA install reject → error surfaced, no changed', async () => {
    mockAutomation.installCa.mockRejectedValue(new Error('no su'))
    const w = mountModal()
    await open(w)

    await w.get('[data-testid="install-ca-btn"]').trigger('click')
    await flushPromises()

    expect(w.get('[data-testid="ca-error"]').text()).toContain('no su')
    expect(w.emitted('changed')).toBeUndefined()
  })
})

describe('ToolInstallModal — streaming wiring', () => {
  it('onLog lines appear in the mitmproxy log window', async () => {
    mockAutomation.getTrafficStatus.mockResolvedValue(TRAFFIC_MISSING)
    let emitLog: ((line: string) => void) | undefined
    let resolveInstall!: (v: unknown) => void
    mockAutomation.installMitmproxy.mockImplementation((cb?: { onLog?: (l: string) => void }) => {
      emitLog = cb?.onLog
      return new Promise((res) => { resolveInstall = res })
    })
    const w = mountModal()
    await open(w)

    await w.get('[data-testid="install-mitmproxy-btn"]').trigger('click')
    emitLog!('pip Looking in indexes: https://pypi.org/simple')
    emitLog!('pip Collecting mitmproxy')
    await flushPromises()

    const log = w.get('[data-testid="mitm-log"]')
    expect(log.text()).toContain('pip Looking in indexes: https://pypi.org/simple')
    expect(log.text()).toContain('pip Collecting mitmproxy')

    resolveInstall({ success: true })
    await flushPromises()
    expect(w.emitted('changed')).toHaveLength(1)
  })

  it('onProgress drives the download progress bar', async () => {
    let emitProgress: ((p: unknown) => void) | undefined
    let resolveInstall!: (v: unknown) => void
    mockAutomation.installIme.mockImplementation(
      (_dev: string, cb?: { onProgress?: (p: unknown) => void }) => {
        emitProgress = cb?.onProgress
        return new Promise((res) => { resolveInstall = res })
      },
    )
    const w = mountModal()
    await open(w)

    await w.get('[data-testid="install-ime-btn"]').trigger('click')
    emitProgress!({ progress: 42, downloaded: 4200, total: 10000, speed: '1.2MB/s' })
    await flushPromises()

    const bar = w.findComponent(NProgress)
    expect(bar.exists()).toBe(true)
    expect(bar.props('percentage')).toBe(42)

    resolveInstall({ success: true })
    await flushPromises()
  })
})

describe('ToolInstallModal — guards & disabled states', () => {
  it('empty deviceId → install-ime-btn and install-ca-btn disabled, no IME probe', async () => {
    const w = mountModal({ deviceId: '' })
    await open(w)

    expect(mockAutomation.getImeStatus).not.toHaveBeenCalled()
    expect(isDisabled(w.get('[data-testid="install-ime-btn"]'))).toBe(true)
    expect(isDisabled(w.get('[data-testid="install-ca-btn"]'))).toBe(true)
    expect(isDisabled(w.get('[data-testid="local-apk-btn"]'))).toBe(true)
  })

  it('missing cert → install-ca-btn disabled even with a device', async () => {
    mockAutomation.getTrafficStatus.mockResolvedValue(TRAFFIC_MISSING)
    const w = mountModal()
    await open(w)

    expect(isDisabled(w.get('[data-testid="install-ca-btn"]'))).toBe(true)
  })

  it('an in-flight install cannot be re-entered (double-click starts ONE install)', async () => {
    mockAutomation.getTrafficStatus.mockResolvedValue(TRAFFIC_MISSING)
    let resolveInstall!: (v: unknown) => void
    mockAutomation.installMitmproxy.mockImplementation(
      () => new Promise((res) => { resolveInstall = res }),
    )
    const w = mountModal()
    await open(w)

    const btn = w.get('[data-testid="install-mitmproxy-btn"]')
    await btn.trigger('click')
    // while in flight the button reads as disabled/loading
    expect(isDisabled(btn)).toBe(true)
    await btn.trigger('click')

    expect(mockAutomation.installMitmproxy).toHaveBeenCalledTimes(1)
    resolveInstall({ success: true })
    await flushPromises()
  })
})

describe('ToolInstallModal — local APK fallback', () => {
  it('selectFile (apk filter) → installIme(deviceId, undefined, path) + changed', async () => {
    mockAutomation.installIme.mockResolvedValue({ success: true, installed: true })
    mockSystem.selectFile.mockResolvedValue({ canceled: false, filePaths: ['D:/offline/ADBKeyBoard.apk'] })
    const w = mountModal()
    await open(w)

    await w.get('[data-testid="local-apk-btn"]').trigger('click')
    await flushPromises()

    expect(mockSystem.selectFile).toHaveBeenCalledWith(
      expect.objectContaining({
        filters: [expect.objectContaining({ extensions: ['apk'] })],
      }),
    )
    expect(mockAutomation.installIme).toHaveBeenCalledWith(
      'emulator-5554', undefined, 'D:/offline/ADBKeyBoard.apk',
    )
    expect(w.emitted('changed')).toHaveLength(1)
  })

  it('canceled picker installs nothing', async () => {
    mockSystem.selectFile.mockResolvedValue({ canceled: true, filePaths: [] })
    const w = mountModal()
    await open(w)

    await w.get('[data-testid="local-apk-btn"]').trigger('click')
    await flushPromises()

    expect(mockAutomation.installIme).not.toHaveBeenCalled()
    expect(w.emitted('changed')).toBeUndefined()
  })
})

describe('ToolInstallModal — D8 accessibility', () => {
  it('GitHub repo is selectable text + a copy button; no external link', async () => {
    const w = mountModal()
    await open(w)

    const ime = w.get('[data-testid="ime-section"]')
    expect(ime.text()).toContain('https://github.com/senzhk/ADBKeyBoard')
    // no external-link surface at all
    expect(w.find('a[href]').exists()).toBe(false)

    const btn = w.get('[data-testid="copy-repo-btn"]')
    await btn.trigger('click')
    expect(mockSystem.copyText).toHaveBeenCalledWith('https://github.com/senzhk/ADBKeyBoard')
  })

  it('every icon-only button: non-empty aria-label AND tooltip content from the same key', async () => {
    mockAutomation.getTrafficStatus.mockResolvedValue(TRAFFIC_MISSING)
    mockAutomation.installMitmproxy.mockResolvedValue(DEGRADED)
    const w = mountModal()
    await open(w)
    await w.get('[data-testid="install-mitmproxy-btn"]').trigger('click')
    await flushPromises()

    for (const testId of ['copy-repo-btn', 'copy-command-btn']) {
      const btn = w.get(`[data-testid="${testId}"]`)
      const label = btn.attributes('aria-label')
      expect(label, testId).toBeTruthy()
      const tip = tooltipOf(w, btn)
      expect(tip, testId).toBeTruthy()
      expect(tooltipContent(tip), testId).toBe(label)
    }
  })
})

describe('ToolInstallModal — tutorials', () => {
  it('renders bilingual tutorial step keys for both sections', async () => {
    const w = mountModal()
    await open(w)

    const traffic = w.get('[data-testid="traffic-section"]')
    expect(traffic.text()).toContain('automation.tools.tutorial.traffic.s1')
    expect(traffic.text()).toContain('automation.tools.tutorial.traffic.s4')

    const ime = w.get('[data-testid="ime-section"]')
    expect(ime.text()).toContain('automation.tools.tutorial.ime.s1')
    expect(ime.text()).toContain('automation.tools.tutorial.ime.s3')
  })
})
