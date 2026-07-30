import { execSync } from 'child_process';
import { readFileSync } from 'fs';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const root = resolve(__dirname, '..');
const pkgPath = resolve(root, 'package.json');

async function main() {
  const args = process.argv.slice(2);
  // Platform is the first non-flag argument, defaults to 'win'
  const platformIdx = args.findIndex(a => !a.startsWith('--'));
  const platform = platformIdx >= 0 ? args[platformIdx] : 'win';
  const extraArgs = args.filter(a => a !== platform).join(' ');

  const pkg = JSON.parse(readFileSync(pkgPath, 'utf8'));
  console.log(`[build] Version: ${pkg.version}`);
  console.log(`[build] Platform: ${platform}`);

  // Step 1: Build Vite (main + preload + renderer)
  console.log('[build] Building Vite...');
  execSync('npx vite build', { cwd: root, stdio: 'inherit' });

  // Step 2: Package with electron-builder
  const cmd = `npx electron-builder --${platform}${extraArgs ? ' ' + extraArgs : ''}`;
  console.log(`[build] Running: ${cmd}`);
  execSync(cmd, { cwd: root, stdio: 'inherit' });

  console.log('[build] Done!');
}

main().catch(e => {
  console.error('[build] Error:', e.message);
  process.exit(1);
});
