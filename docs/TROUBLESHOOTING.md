# 疑难排查记录

记录那些**症状极具误导性、排查代价高**的问题。每条都附「已排除的错误方向」，避免下次重走一遍。

---

## 工作区被注入 Low 完整性标签，导致 Electron / esbuild 静默失效

### 症状（两个看似无关的现象，同一个根因）

**A. Electron 静默秒退。** `npm run dev` 构建全部正常，但 `starting electron app...` 之后 Electron 无声无息地退出：

- 没有窗口
- 没有任何输出（stdout / stderr 全空）
- `%LOCALAPPDATA%\blank_tool\logs\electron.log` 无新增行
- `%APPDATA%\blank_tool\` 无任何文件被写入、`app-config.json` 的 mtime 不变（说明主进程代码**根本没被执行到**）
- Application 事件日志里没有 Application Error 记录

直接跑二进制同样如此，退出码恒为 `-2147483645`：

```powershell
node_modules\electron\dist\electron.exe --version
"exit=$LASTEXITCODE"     # exit=-2147483645，且一个字都不打印
```

`-2147483645` = `0x80000003` = `STATUS_BREAKPOINT`，是 Chromium 内部 `IMMEDIATE_CRASH()`（`__debugbreak`/`int3`）的签名：某个 `CHECK` 断言失败后 fail-fast，**不打任何日志**。

**B. esbuild 删不掉自己的临时文件。**

```
ERROR  [vite:esbuild-transpile] remove C:\Users\<user>\AppData\Local\Temp\esbuild-<64hex>: Access is denied.
```

那个临时文件会**留在原地删不掉**，但**手动 `Remove-Item` 却能删掉**（这个反差是关键线索）。

### 根因

DSH 沙箱会把 `Mandatory Label\Low Mandatory Level:(OI)(CI)(NW)` 打在**工作区根目录**上，整棵目录树继承——`node_modules/` 下的可执行文件也在内。

Windows 的规则（本机实测）：**镜像文件带 Low 强制完整性标签时，由它启动的进程同样被降级为 Low 完整性**：

| 被测 `whoami.exe` 的文件标签 | 进程实际完整性 |
|---|---|
| 无标签 | High（跟随父令牌） |
| Low | **Low**（`S-1-16-4096`） |
| Medium | Medium（`S-1-16-8192`） |

于是低完整性进程受 no-write-up 约束，**写不了 Medium 完整性的对象**：

- `node_modules\electron\dist\electron.exe` 以 Low 启动 → Chromium 初始化要写 `%TEMP%`（创建 crashpad 注册文件、`scoped_dir`）和 `%APPDATA%`（profile）→ 全被拒 → `CHECK` fail-fast → `0x80000003`。
- `node_modules\@esbuild\win32-x64\esbuild.exe` 以 Low 启动 → 它的 Go 服务删不掉 `%TEMP%` 里那个由 Medium 进程（Node/Vite）创建的临时文件 → `ERROR_ACCESS_DENIED`。而 PowerShell 是 Medium，Medium 删 Medium 合法，所以手动能删。

### 修复

```powershell
# 在项目根目录执行
icacls . /setintegritylevel Medium
```

**只改根目录即可**，子项会自动继承更新，不需要 `/T`（`node_modules` 很大，递归很慢）。改完用下面两步验证：

```powershell
icacls . | Select-String Mandatory                    # 不再出现 Low Mandatory Level
node_modules\electron\dist\electron.exe --version     # 期望打印 v38.3.0
```

### 会复发

只要 DSH 再以受限模式在这个工作区跑会话，标签就会被重新打上，A、B 两个症状一起回来。复发后重跑上面那条 `icacls` 即可。

### 30 秒自我确认

```powershell
icacls . | Select-String Mandatory
```

看到 `Low Mandatory Level` 就是它，不用再查别的。

### 已排除的错误方向（都实测排除过，别再走一遍）

| 曾被怀疑 | 实测结论 |
|---|---|
| 安全软件（360「主动防御」）拦截 `node.exe` | **无关**。手动删同目录、同权限的残留文件成功；隔离实验里单独加上 `Everyone Deny DeleteSubdirectoriesAndFiles`，Electron 照样正常启动 |
| `%TEMP%` 被防护软件盯防 | **无关**。把 TEMP 指到工作区内的 `.tmp/` 反而「修好」了 esbuild——只是因为临时文件也继承了 Low 标签，Low 删 Low 合法。**不是 TEMP 位置的问题** |
| Electron 安装损坏 | `dist/` 与另一份可用的 Electron 副本**逐文件同尺寸**，`version` 文件为 38.3.0 |
| userData / profile 损坏 | `app-config.json`、`Local State`、`Preferences` 均为合法 JSON，无 `SingletonLock` 残留 |
| ESM `__dirname` shim / 模块格式 | `dist/main/main.js` 头部有 `import.meta.dirname` / `createRequire` shim，与 `package.json` 的 `"type": "module"` 一致 |
| IFEO / 兼容性 shim / Exploit Protection | `electron.exe`、`node.exe` 均无 IFEO 条目，无 AppCompat Layers，无系统级 MitigationOptions |
| 单实例锁冲突 | `src/main/main.ts` 没有 `requestSingleInstanceLock()` |

### 隔离实验（结论的唯一依据）

把**同一份** `electron.exe` 拷到工作区外，只改一个变量：

| 条件 | 退出码 | stdout |
|---|---|---|
| 干净拷贝（工作区外，无标签） | `0` | `v38.3.0` |
| 仅给 `electron.exe` 打 Low 标签 | `-2147483645` | 空 |
| 整棵目录递归打 Low 标签 | `-2147483645` | 空 |
| 撤销标签、改为只加 `Everyone Deny DeleteSubdirectoriesAndFiles` | `0` | `v38.3.0` |

**判据**：把 `electron.exe` 拷到工作区外再跑，能打印 `v38.3.0` 就说明问题出在工作区的标签上，**不是**二进制或系统层面的问题。

---

## `runtime/python/` 缺失（打包风险）

`AGENTS.md` 描述打包时 `runtime/` 应包含 `python/`，但本机 `runtime/` 下只有 `aapt/ adb/ android/ apktool/ bundletool/ jre/ mitmproxy/`，**没有 `python/`**（`runtime/` 不入库，见 `.gitignore`）。

dev 下 `src/main/python/paths.ts` 会回退到系统 `python`，启动日志里能看到：

```
Python runtime not found at <root>\runtime\python\python.exe, falling back to system python
```

开发期不受影响（有系统 Python 即可跑通），但**打包前必须把 `python/` 补齐**：`electron-builder` 会把整个 `runtime/` 作为 `extraResources` 拷进安装包，目标机器上没装 Python 时后端起不来。
