/**
 * 系统通知的唯一入口。
 *
 * 规则集中在这里，避免每个调用方各判一次配置：
 *   - 设置里的 `enableNotifications`（「系统通知」）为 true 才发
 *   - 缺少 IPC 能力（老 preload / 非 Electron 环境）时静默跳过
 *   - 永不抛错：通知失败不该影响任务/运行本身的流程
 */
import { log } from '@utils/logger'

export async function notifySystem(title: string, body: string): Promise<boolean> {
  const api = window.electronAPI as any
  const notify = api?.showSystemNotification
  if (!api?.appConfig?.get || typeof notify !== 'function') return false
  try {
    const enabled = await api.appConfig.get('enableNotifications')
    if (enabled !== true) return false
    await notify(title, body)
    return true
  } catch (err) {
    log.error('[systemNotify] notify failed', err)
    return false
  }
}
