
/**
 * 自动化能力探测服务
 *
 * Read-only probes for the two optional dependencies of the automation
 * feature — mitmproxy (PC side, traffic capture) and ADBKeyBoard (device
 * side, non-ASCII text input). Neither ever mutates anything: the settings
 * page renders the result and the automation page turns it into non-blocking
 * run hints.
 */
import { log } from '@utils/logger'
import { requireApiMethod } from '../api/apiAccess';

export interface TrafficStatus {
    installed: boolean
    ready: boolean
    lib_path: string
    python_mismatch: string | null
}

export interface ImeStatus {
    device_id: string
    package: string
    installed: boolean
    active: boolean
}

class AutomationService {
    /**
     * mitmproxy availability. `null` means the probe itself failed — the UI
     * shows an "unknown" state instead of pretending it is missing.
     */
    async getTrafficStatus(force = false): Promise<TrafficStatus | null> {
        if (!force && this.trafficStatus) {
            return this.trafficStatus;
        }
        try {
            this.trafficStatus = await requireApiMethod('callBackendAPI')(
                'automation.traffic_status', {}
            ) as TrafficStatus;
            return this.trafficStatus;
        } catch (error) {
            log.error('获取流量抓取组件状态失败:', error);
            return null;
        }
    }

    /**
     * ADBKeyBoard availability on ONE device. Device side, hence the id.
     */
    async getImeStatus(deviceId: string): Promise<ImeStatus | null> {
        if (!deviceId) {
            return null;
        }
        try {
            return await requireApiMethod('callBackendAPI')(
                'automation.ime_status', { device_id: deviceId }
            ) as ImeStatus;
        } catch (error) {
            log.error('获取输入法状态失败:', error);
            return null;
        }
    }

    private trafficStatus: TrafficStatus | null = null;
}

export default AutomationService;
