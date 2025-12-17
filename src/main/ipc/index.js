import { setupAppConfigHandlers, setupUserConfigHandlers } from './configHandlers.js';
import { setupCommandHandlers } from './commandHandlers.js';
import { setupElectronHandlers } from './electronHandlers.js';

export function setupAllHandlers(pythonProcess) {
    setupAppConfigHandlers();
    setupUserConfigHandlers();
    setupElectronHandlers();
    
    if (pythonProcess) {
        setupCommandHandlers(pythonProcess);
    }
}