import { ChildProcessWithoutNullStreams } from 'child_process';
import { setupAppConfigHandlers } from './configHandlers';
import { setupCommandHandlers } from './commandHandlers';
import { setupElectronHandlers } from './electronHandlers';

export function setupAllHandlers(
    getPythonProcess: () => ChildProcessWithoutNullStreams | null,
    ensurePythonProcess?: () => Promise<ChildProcessWithoutNullStreams | null>
): void {
    setupAppConfigHandlers();
    setupElectronHandlers();
    
    setupCommandHandlers(getPythonProcess, ensurePythonProcess);
}
