import { ChildProcessWithoutNullStreams } from 'child_process';
import { setupAppConfigHandlers } from './configHandlers';
import { setupCommandHandlers } from './commandHandlers';
import { setupElectronHandlers } from './electronHandlers';
import appStore from '../stores/appStore';

export function setupAllHandlers(
    getPythonProcess: () => ChildProcessWithoutNullStreams | null,
    ensurePythonProcess?: () => Promise<ChildProcessWithoutNullStreams | null>
): void {
    setupAppConfigHandlers();
    setupElectronHandlers();

    const stored = appStore.get('commands.timeout') as number | undefined
    const timeout = (stored && stored > 30000 ? stored : 300000)
    setupCommandHandlers(getPythonProcess, ensurePythonProcess, timeout);
}
