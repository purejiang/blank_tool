import { setupAppConfigHandlers } from './configHandlers.js';
import { setupCommandHandlers } from './commandHandlers.js';
import { setupElectronHandlers } from './electronHandlers.js';

export function setupAllHandlers(pythonProcess) {
    setupAppConfigHandlers();
    setupElectronHandlers();
    
    if (pythonProcess) {
        setupCommandHandlers(pythonProcess);
    }
}