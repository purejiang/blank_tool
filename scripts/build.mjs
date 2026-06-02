import { execSync } from 'child_process';
import { readFileSync, writeFileSync, unlinkSync } from 'fs';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const root = resolve(__dirname, '..');
const pkgPath = resolve(root, 'package.json');
const pkgBakPath = resolve(root, 'package.json.bak');

function getTagVersion() {
  try {
    const tag = execSync('git describe --tags --abbrev=0', { cwd: root, encoding: 'utf8' }).trim();
    return tag.replace(/^v/, '');
  } catch {
    const pkg = JSON.parse(readFileSync(pkgPath, 'utf8'));
    return pkg.version || '0.0.0';
  }
}

async function main() {
  const args = process.argv.slice(2);
  const platformArg = args.find(a => a.startsWith('--'));
  const platform = platformArg ? platformArg.replace('--', '') : 'win';

  const gitVersion = getTagVersion();
  const pkg = JSON.parse(readFileSync(pkgPath, 'utf8'));
  const origVersion = pkg.version;

  // Backup package.json, inject git tag version
  writeFileSync(pkgBakPath, JSON.stringify(pkg, null, 2));
  pkg.version = gitVersion;
  writeFileSync(pkgPath, JSON.stringify(pkg, null, 2) + '\n');

  console.log(`[build] Version: ${origVersion} -> ${gitVersion}`);
  console.log(`[build] Platform: ${platform}`);

  try {
    // Step 1: Build Vite (main + preload + renderer)
    console.log('[build] Building Vite...');
    execSync('npx vite build', { cwd: root, stdio: 'inherit' });

    // Step 2: Package with electron-builder
    const cmd = `npx electron-builder --${platform}`;
    console.log(`[build] Running: ${cmd}`);
    execSync(cmd, { cwd: root, stdio: 'inherit' });

    console.log('[build] Done!');
  } finally {
    // Restore original package.json
    writeFileSync(pkgPath, readFileSync(pkgBakPath, 'utf8'));
    try { unlinkSync(pkgBakPath); } catch {}
    console.log(`[build] Restored package.json version to ${origVersion}`);
  }
}

main().catch(e => {
  console.error('[build] Error:', e.message);
  process.exit(1);
});
