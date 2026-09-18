import { ChildProcessWithoutNullStreams } from 'child_process';
import { setupAppConfigHandlers } from './configHandlers';
import { setupCommandHandlers } from './commandHandlers';
import { setupElectronHandlers } from './electronHandlers';
import { setupUpdateHandlers } from './updateHandlers';
import appStore from '../stores/appStore';

export function setupAllHandlers(
    getPythonProcess: () => ChildProcessWithoutNullStreams | null,
    ensurePythonProcess?: () => Promise<ChildProcessWithoutNullStreams | null>
): void {
    setupAppConfigHandlers();
    setupElectronHandlers();
    setupUpdateHandlers();

    // Per-request timeout (ms), read dynamically so settings-page changes
    // take effect without restart. `timeout` is in seconds (settings page,
    // 10-600s); falls back to legacy `commands.timeout` (ms) then 5 minutes.
    const getRequestTimeout = (): number => {
        const sec = Number(appStore.get('timeout'));
        if (Number.isFinite(sec) && sec > 0) return sec * 1000;
        const legacy = Number(appStore.get('commands.timeout'));
        return legacy && legacy > 30000 ? legacy : 300000;
    };
    setupCommandHandlers(getPythonProcess, ensurePythonProcess, getRequestTimeout);
}
