/**
 * RunConfigDialog unit tests — 运行配置弹窗（两栏：抓包 / 输入 / 执行 / 异常处理）。
 *
 * 锁住的规则：
 *   - 左栏四个面板，默认「抓包」
 *   - 没有抓包工具时不能开启抓包（开关禁用 + 提示），状态行与「检测」/「安装」入口都在
 *   - 证书未生成 → 只给引导文案（不给安装按钮）；已生成但设备未装 → 给安装按钮
 *   - 输入面板：中文输入开关 + ADBKeyBoard 状态/检测/安装（无设备时禁用）
 *   - 执行面板：步骤间隔（ms，0 = 不等待）
 *   - 异常处理面板：失败后继续 / 崩溃即中止
 *
 * 所有后端调用都在页面侧，这里只断言事件（detect / openTools / installCa / resetTraffic）。
 * vue-i18n 被替换为恒等 t()（key 原样渲染）。
 */
import { describe, it, expect, vi } from 'vitest'
import { mount, type VueWrapper } from '@vue/test-utils'

vi.mock('vue-i18n', async (importOriginal) => {
  const actual = await importOriginal<typeof import('vue-i18n')>()
  return { ...actual, useI18n: () => ({ t: (k: string) => k }) }
})

import RunConfigDialog from '@/renderer/components/automation/RunConfigDialog.vue'

const TRAFFIC_READY = {
  installed: true,
  ready: true,
  lib_path: 'C:/runtime/mitmproxy/lib',
  python_mismatch: null,
  ca_cert_exists: true,
}

const IME_OK = { device_id: 'dev-1', package: 'com.android.adbkeyboard/.AdbIME', installed: true, active: false }

function mountDialog(props: Record<string, unknown> = {}) {
  return mount(RunConfigDialog, {
    props: {
      show: true,
      deviceId: 'dev-1',
      captureTraffic: false,
      trafficHostFilter: '',
      continueOnError: false,
      abortOnCrash: true,
      enableChineseInput: true,
      stepIntervalMs: 300,
      trafficStatus: TRAFFIC_READY,
      imeStatus: IME_OK,
      ...props,
    },
    global: { stubs: { teleport: true } },
  })
}

function navItems(w: VueWrapper) {
  return w.findAll('.rcfg-nav .app-nav-item')
}

async function openTab(w: VueWrapper, index: number) {
  await navItems(w)[index].trigger('click')
  await w.vm.$nextTick()
}

function buttonByText(w: VueWrapper, text: string) {
  return w.findAll('button').find((b) => b.text() === text)
}

describe('RunConfigDialog — 两栏布局', () => {
  it('左栏是抓包 / 输入 / 执行 / 异常处理，默认展示抓包', () => {
    const w = mountDialog()
    const items = navItems(w)
    expect(items.map((i) => i.text())).toEqual([
      'automation.runConfigCapture',
      'automation.runConfigInput',
      'automation.runConfigExec',
      'automation.runConfigErrors',
    ])
    expect(items[0].classes()).toContain('active')
    // 默认面板里能看到抓包过滤条件（列表 + 添加按钮）
    expect(w.find('.rcfg-add').exists()).toBe(true)
  })

  it('切换左栏换面板', async () => {
    const w = mountDialog()
    await openTab(w, 1)
    expect(navItems(w)[1].classes()).toContain('active')
    expect(w.find('.rcfg-add').exists()).toBe(false)

    await openTab(w, 3)
    expect(w.findAll('.rcfg-row .n-switch').length).toBe(2)
  })

  it('没有底部「关闭」按钮：关闭只靠右上角的 X（避免同一件事画两遍）', () => {
    const w = mountDialog()
    expect(buttonByText(w, 'common.close')).toBeUndefined()
  })

  it('左栏是 tablist：role / aria-selected / roving tabindex 都正确', () => {
    const w = mountDialog()
    expect(w.get('.rcfg-nav').attributes('role')).toBe('tablist')

    const items = navItems(w)
    expect(items[0].attributes('role')).toBe('tab')
    expect(items[0].attributes('aria-selected')).toBe('true')
    expect(items[0].attributes('tabindex')).toBe('0')
    expect(items[1].attributes('aria-selected')).toBe('false')
    expect(items[1].attributes('tabindex')).toBe('-1')
  })

  it('方向键可以在页签之间切换（焦点跟随）', async () => {
    const w = mountDialog()
    await navItems(w)[0].trigger('keydown', { key: 'ArrowDown' })
    expect(navItems(w)[1].classes()).toContain('active')
    expect(navItems(w)[1].attributes('aria-selected')).toBe('true')
    expect(navItems(w)[0].attributes('tabindex')).toBe('-1')
  })
})

describe('RunConfigDialog — 抓包面板', () => {
  it('没有抓包工具时开关禁用并给出原因', () => {
    const w = mountDialog({ trafficStatus: { ...TRAFFIC_READY, installed: false, ready: false } })
    const sw = w.get('.rcfg-row .n-switch')
    expect(sw.classes()).toContain('n-switch--disabled')
    expect(w.text()).toContain('automation.captureDisabledHint')
  })

  it('工具就绪时可以开启，并向上抛 update:captureTraffic', async () => {
    const w = mountDialog()
    const sw = w.get('.rcfg-row .n-switch')
    expect(sw.classes()).not.toContain('n-switch--disabled')
    await sw.trigger('click')
    expect(w.emitted('update:captureTraffic')).toEqual([[true]])
  })

  it('已开启但本机不可用时保留关闭能力，并显示既有警告', () => {
    const w = mountDialog({
      captureTraffic: true,
      captureUnavailable: true,
      trafficStatus: { ...TRAFFIC_READY, installed: false, ready: false },
    })
    expect(w.get('.rcfg-row .n-switch').classes()).not.toContain('n-switch--disabled')
    expect(w.get('.rcfg-warn').text()).toBe('automation.captureTrafficUnavailable')
  })

  it('工具行给出状态、检测与安装入口', async () => {
    const w = mountDialog()
    const detect = buttonByText(w, 'automation.detect')
    const install = buttonByText(w, 'automation.tools.reinstall')
    expect(detect).toBeTruthy()
    expect(install).toBeTruthy()

    await detect!.trigger('click')
    await install!.trigger('click')
    expect(w.emitted('detect')).toEqual([['traffic']])
    expect(w.emitted('openTools')).toEqual([['traffic']])
  })

  it('未安装时安装按钮文案是「安装工具」而不是「重新安装」', () => {
    const w = mountDialog({ trafficStatus: { ...TRAFFIC_READY, installed: false, ready: false } })
    expect(buttonByText(w, 'automation.installTool')).toBeTruthy()
    expect(buttonByText(w, 'automation.tools.reinstall')).toBeUndefined()
  })

  it('证书未生成时只引导，不给安装按钮', () => {
    const w = mountDialog({ trafficStatus: { ...TRAFFIC_READY, ca_cert_exists: false } })
    expect(w.text()).toContain('automation.certNotReady')
    expect(buttonByText(w, 'automation.tools.caInstall')).toBeUndefined()
  })

  it('证书已生成但设备未装 → 可安装（需要设备），点击抛 installCa', async () => {
    const w = mountDialog({ trafficStatus: { ...TRAFFIC_READY, ca_on_device: false, device_state: 'device' } })
    const btn = buttonByText(w, 'automation.tools.caInstall')
    expect(btn).toBeTruthy()
    expect(btn!.attributes('disabled')).toBeUndefined()
    await btn!.trigger('click')
    expect(w.emitted('installCa')).toHaveLength(1)
  })

  it('设备已装证书 / 没选设备时安装按钮禁用', () => {
    const installed = mountDialog({ trafficStatus: { ...TRAFFIC_READY, ca_on_device: true } })
    expect(buttonByText(installed, 'automation.tools.caInstall')!.attributes('disabled')).toBeDefined()

    const noDevice = mountDialog({ deviceId: '', trafficStatus: { ...TRAFFIC_READY, ca_on_device: false } })
    expect(buttonByText(noDevice, 'automation.tools.caInstall')!.attributes('disabled')).toBeDefined()
  })

  it('抓包关闭时过滤条件禁用', async () => {
    const off = mountDialog({ captureTraffic: false })
    expect(off.find('.rcfg-block.is-off').exists()).toBe(true)

    const on = mountDialog({ captureTraffic: true })
    expect(on.find('.rcfg-block.is-off').exists()).toBe(false)
  })

  it('修复设备代理按钮抛 resetTraffic', async () => {
    const w = mountDialog()
    await buttonByText(w, 'automation.repairProxy')!.trigger('click')
    expect(w.emitted('resetTraffic')).toHaveLength(1)
  })
})

/**
 * 过滤条件是**列表**（一条一行 + 行内删除 + 添加按钮），不是标签云：
 * 标签云在弹窗里会跟过滤说明抢高度，条件一多就放不下。
 */
describe('RunConfigDialog — 过滤条件列表', () => {
  function rowValues(w: VueWrapper): string[] {
    return w.findAll('.rcfg-list-row input').map((i) => (i.element as HTMLInputElement).value)
  }

  it('初始把逗号分隔的字符串拆成每行一条', () => {
    const w = mountDialog({ captureTraffic: true, trafficHostFilter: 'a.com, b.com' })
    expect(rowValues(w)).toEqual(['a.com', 'b.com'])
    expect(w.find('.rcfg-empty').exists()).toBe(false)
  })

  it('没有条件时给空态提示而不是空列表', () => {
    const w = mountDialog({ captureTraffic: true, trafficHostFilter: '' })
    expect(w.findAll('.rcfg-list-row')).toHaveLength(0)
    expect(w.get('.rcfg-empty').text()).toBe('automation.captureFilterEmpty')
  })

  it('「添加条件」追加一行；空行不写回（不产生空的过滤条件）', async () => {
    const w = mountDialog({ captureTraffic: true, trafficHostFilter: '' })
    await w.get('.rcfg-add').trigger('click')
    expect(w.findAll('.rcfg-list-row')).toHaveLength(1)
    expect(w.emitted('update:trafficHostFilter')).toBeUndefined()
  })

  it('在某行回车也在末尾追加一行', async () => {
    const w = mountDialog({ captureTraffic: true, trafficHostFilter: 'a.com' })
    await w.get('.rcfg-list-row').trigger('keyup.enter')
    expect(w.findAll('.rcfg-list-row')).toHaveLength(2)
  })

  it('编辑某一行按逗号格式写回（含新增行）', async () => {
    const w = mountDialog({ captureTraffic: true, trafficHostFilter: 'a.com' })
    await w.get('.rcfg-add').trigger('click')
    await w.findAll('.rcfg-list-row input')[1].setValue('api.example.com')
    expect(w.emitted('update:trafficHostFilter')?.at(-1)).toEqual(['a.com,api.example.com'])
  })

  it('删除某一行后写回剩余条件', async () => {
    const w = mountDialog({ captureTraffic: true, trafficHostFilter: 'a.com,b.com' })
    await w.findAll('.rcfg-list-row button')[0].trigger('click')
    expect(w.findAll('.rcfg-list-row')).toHaveLength(1)
    expect(w.emitted('update:trafficHostFilter')?.at(-1)).toEqual(['b.com'])
  })

  it('条件里的逗号被替换成空格（逗号是 wire 分隔符）', async () => {
    const w = mountDialog({ captureTraffic: true, trafficHostFilter: 'a.com' })
    await w.findAll('.rcfg-list-row input')[0].setValue('a.com,b.com')
    expect(w.emitted('update:trafficHostFilter')?.at(-1)).toEqual(['a.com b.com'])
  })

  it('抓包关闭时输入框、删除与添加都禁用', () => {
    const w = mountDialog({ captureTraffic: false, trafficHostFilter: 'a.com' })
    expect((w.get('.rcfg-list-row input').element as HTMLInputElement).disabled).toBe(true)
    expect(w.get('.rcfg-list-row button').attributes('disabled')).toBeDefined()
    expect(w.get('.rcfg-add').attributes('disabled')).toBeDefined()
  })

  it('外部改值（页面/持久化）会重建行', async () => {
    const w = mountDialog({ captureTraffic: true, trafficHostFilter: 'a.com' })
    await w.setProps({ trafficHostFilter: 'x.com,y.com' })
    expect(rowValues(w)).toEqual(['x.com', 'y.com'])
  })
})

describe('RunConfigDialog — 输入面板', () => {
  it('第一行是中文输入开关，切换时抛 update:enableChineseInput', async () => {
    const w = mountDialog()
    await openTab(w, 1)
    const sw = w.get('.rcfg-row .n-switch')
    await sw.trigger('click')
    expect(w.emitted('update:enableChineseInput')).toEqual([[false]])
  })

  it('关闭中文输入时给出后果说明', async () => {
    const w = mountDialog({ enableChineseInput: false })
    await openTab(w, 1)
    expect(w.get('.rcfg-warn').text()).toBe('automation.inputDisabledHint')
  })

  it('ADBKeyBoard 行给检测与安装入口', async () => {
    const w = mountDialog()
    await openTab(w, 1)
    await buttonByText(w, 'automation.detect')!.trigger('click')
    await buttonByText(w, 'automation.tools.imeDownloadInstall')!.trigger('click')
    expect(w.emitted('detect')).toEqual([['ime']])
    expect(w.emitted('openTools')).toEqual([['ime']])
  })

  it('没选设备时检测与安装都禁用', async () => {
    const w = mountDialog({ deviceId: '', imeStatus: null })
    await openTab(w, 1)
    expect(buttonByText(w, 'automation.detect')!.attributes('disabled')).toBeDefined()
    expect(buttonByText(w, 'automation.tools.imeDownloadInstall')!.attributes('disabled')).toBeDefined()
  })
})

/**
 * 「执行」面板：步骤间隔。
 *
 * 长脚本不该靠手写 wait 步骤来获得节奏，所以在运行配置里给一个默认间隔；
 * 单个步骤可以用自己的 delay_ms 覆盖它（见 StepEditForm / stepTypes.delay_ms）。
 */
describe('RunConfigDialog — 执行面板', () => {
  it('显示当前间隔，并在改动时抛 update:stepIntervalMs', async () => {
    const w = mountDialog({ stepIntervalMs: 300 })
    await openTab(w, 2)
    const input = w.get('.rcfg-interval input')
    expect((input.element as HTMLInputElement).value).toBe('300')
    expect(w.text()).toContain('automation.stepIntervalHint')
    // 从中途开始跑的入口也在这一页提示（行菜单里操作）
    expect(w.text()).toContain('automation.stepIntervalStartHint')
  })

  it('清空输入 = 0（不插入等待），不会抛 NaN', async () => {
    const w = mountDialog({ stepIntervalMs: 300 })
    await openTab(w, 2)
    const nInputNumber = w.findComponent({ name: 'InputNumber' })
    nInputNumber.vm.$emit('update:value', null)
    await w.vm.$nextTick()
    expect(w.emitted('update:stepIntervalMs')).toEqual([[0]])
  })

  it('该面板没有开关，只有间隔输入（不再是异常处理的第三行）', async () => {
    const w = mountDialog()
    await openTab(w, 2)
    expect(w.find('.rcfg-interval').exists()).toBe(true)
    expect(w.findAll('.rcfg-row .n-switch').length).toBe(0)
  })
})

describe('RunConfigDialog — 异常处理面板', () => {
  it('两个开关分别是失败后继续 / 崩溃即中止', async () => {
    const w = mountDialog({ continueOnError: false, abortOnCrash: true })
    await openTab(w, 3)
    const switches = w.findAll('.rcfg-row .n-switch')
    expect(switches.length).toBe(2)
    expect(switches[0].classes()).not.toContain('n-switch--active')
    expect(switches[1].classes()).toContain('n-switch--active')

    await switches[0].trigger('click')
    await switches[1].trigger('click')
    expect(w.emitted('update:continueOnError')).toEqual([[true]])
    expect(w.emitted('update:abortOnCrash')).toEqual([[false]])
  })
})
