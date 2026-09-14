import { Tray, Menu, nativeImage, app } from 'electron';
import path from 'path';
import { getMainWindow, setTray } from '../state';

// electron-vite 的 ESM shim 注入 __dirname（指向 bundle 所在的 dist/main/）
const __iconPath = path.join(__dirname, 'assets', 'images', 'icon.png');

export function createTray(): Tray {
  const iconImage = nativeImage.createFromPath(__iconPath);
  const isZh = app.getLocale().startsWith('zh');

  const trayInstance = new Tray(iconImage.isEmpty() ? nativeImage.createEmpty() : iconImage);
  trayInstance.setToolTip('Blank Tool');

  const contextMenu = Menu.buildFromTemplate([
    {
      label: isZh ? '显示主窗口' : 'Show Window',
      click: () => {
        const mw = getMainWindow();
        if (mw) {
          mw.show();
          mw.focus();
        }
      }
    },
    {
      label: isZh ? '隐藏窗口' : 'Hide Window',
      click: () => {
        const mw = getMainWindow();
        if (mw) {
          mw.hide();
        }
      }
    },
    { type: 'separator' },
    {
      label: isZh ? '退出' : 'Quit',
      click: () => {
        app.quit();
      }
    }
  ]);

  trayInstance.setContextMenu(contextMenu);

  trayInstance.on('double-click', () => {
    const mw = getMainWindow();
    if (mw) {
      if (mw.isVisible()) {
        mw.hide();
      } else {
        mw.show();
        mw.focus();
      }
    }
  });

  setTray(trayInstance);
  return trayInstance;
}
