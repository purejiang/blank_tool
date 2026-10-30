# 白包打包（white-label-packer）

可分发插件 `white-label-packer`：从一份**基础 APK**（可选再给一份**同版本 AAB**）批量生成渠道白包——
**其他包**（通用）、三星、谷歌，以及任意自定义渠道。渠道本身不绑定任何商店，三星、谷歌只是预置模板，
右侧「＋ 其他包」可继续添加任意自定义渠道。每个渠道独立设置包名、应用名、版本号、图标、签名密钥与渠道标识。

- 插件 id：`white-label-packer`（`plugin.run` / `plugin.export` / `plugin.delete` 都用它；display name 只是标签）
- 源码目录：`plugins-dist/white-label-packer/`（`manifest.json` / `main.py` / `ui/index.html`）
- 分发压缩包：`plugins-dist/white-label-packer-1.3.0.zip`，在插件页点「导入」选择该 zip 即可安装到
  `<BT_PLUGINS_DIR>/white-label-packer/`；**不是内建插件**，没有「内建」标签，可独立删除/更新
- 包格式与 UI 桥规范见 `docs/PLUGIN_PACKAGE.md`

## 功能

| 能力 | 说明 |
|---|---|
| 批量出包 | 一次运行按启用的渠道逐个产出 |
| 改 applicationId | aapt2 `--rename-manifest-package`；资源包名保持原值、Java/Kotlin 类名不动 |
| 改应用名 | 改写 manifest 的 `android:label` **字面量**（见「图标与应用名」） |
| 换图标 | 可选；替换**已存在**的 launcher 图标栅格文件（同资源 ID / 同路径） |
| 改版本号 | 按渠道覆盖 versionCode / versionName |
| 独立签名 | 每个渠道用自己的 keystore；APK 用 apksigner，AAB 用 jarsigner |
| 额外权限 | 每渠道追加 `<uses-permission>`（如 `com.android.vending.BILLING`），已存在不重复；APK/AAB 都生效 |
| 渠道标识 | manifest `<meta-data>`、可选 `assets/` 渠道文件、占位符 |
| 渠道文件 | 每个渠道可向 `assets/<path>` 注入一个文本文件（APK 写 zip，AAB 写 `base/assets/`） |
| 配置记忆 | 非机密配置存 `profiles.json`，口令不落盘 |

不做的事：dex 改名、keystore 生成、商店合规、AAB-only 输入——见「限制与排错」。

### 身份模型（改哪些、不改哪些）

| 项 | 默认 | 开关 |
|---|---|---|
| applicationId（包名） | 改成渠道包名（`--rename-manifest-package`），资源包名与类名不变 | — |
| `provider` authorities | **保持原样** | 「重命名 provider authority」开启后按新包名改写 |
| 自定义权限（`<permission>` / `uses-permission`） | **保持原样** | 「重命名自定义权限」开启后按新包名改写 |
| 额外权限（`uses-permission`） | **不添加** | 「额外权限」每行一个，追加到 manifest；已存在不重复 |
| `sharedUserId` | **移除**（改包名后共享 uid 会冲突） | 「移除 sharedUserId」默认开启，关掉即保留 |
| versionCode / versionName | 按渠道覆盖 | — |

## 渠道预置与自定义渠道

| 渠道 | 默认产物 | 流程 |
|---|---|---|
| `other` 其他包 | 签名 APK | apktool 解码 → aapt2 重链接 → zip 重组 → zipalign → apksigner |
| `samsung` 三星 | 签名 APK | 同上；默认 APK，也可切 AAB / 两者 |
| `google` 谷歌 | 签名 AAB（可附带测试 APK） | 优先直改源 AAB；无 AAB 或 guard 不满足时重建 |
| 自定义（如 `partner`） | 由格式选择决定 | 与普通渠道完全一致；渠道名/包名/签名独立 |

预置只是模板：每个渠道的包名、应用名、版本、keystore、渠道标识互不影响。**所有渠道**的格式都可在
`APK` / `AAB` / `两者` 之间选择（默认其他包/三星 APK、谷歌 AAB；选「两者」时额外产出一个可安装的测试 APK）。

自定义渠道在 UI 右侧「＋ 其他包」添加，自动分配 `other1`、`other2`… 的渠道标识（只用于产物文件名和报告），
渠道名可任意改（支持中文）。「其他包」预置本身也是普通渠道，可直接改包名/签名。

## 输入要求

| 输入 | 必需 | 要求 |
|---|---|---|
| 基础 APK | ✅ | 完整 APK（release 包，未加固或已脱壳）；split APK 会被直接拒绝（提示用 base/universal APK）。也可由插件自带 `assets/base.apk` 提供默认值 |
| 源 AAB | 可选 | 与基础 APK **同一次构建**、单 `base` 模块、同包名同版本；用于谷歌渠道直改，缺省则重建。也可由插件自带 `assets/base.aab` 提供默认值 |
| 图标 PNG | 可选 | 必须是受支持的 8-bit、非交错 PNG（RGB / 调色板 / RGBA），否则直接报错；尺寸任意 |
| keystore | ✅（每个出包渠道） | JKS/PKCS12 均可，需 path + alias + storepass（keypass 可选）；插件**不**生成密钥 |
| 渠道文件 | 可选 | `{path, content}`：`path` 是产物内目标路径（相对路径，自动补 `assets/`，禁止绝对路径和 `..`），`content` 是文本内容 |

versionCode / versionName 不填时继承源 APK 的值（versionCode 优先取渠道配置，其次 apktool.yml / 源包）。

## 插件自带默认 APK / AAB

插件包本身可以携带任意资源；白包插件约定两个默认输入（都可选）：

```text
white-label-packer/
  manifest.json
  main.py
  ui/index.html
  assets/
    base.apk     # 可选：默认基础 APK
    base.aab     # 可选：默认源 AAB（与 base.apk 同构建时优先直改）
```

- 导入 zip 时资源原样解压到 `<BT_PLUGINS_DIR>/white-label-packer/assets/`；插件后端用
  `os.path.dirname(__file__)` 读取，不依赖当前工作目录。
- UI 在 presets 返回后自动把 `base.apk` / `base.aab` 填进路径框，并在路径旁显示「插件内置」标记；
  填好后会自动触发一次解析，用户不必再点「解析」。用户仍可改选外部文件，AAB 旁的「清除」按钮
  可显式不用 AAB（即使插件自带）。
- 后端 `inspect` / `pack` 也支持省略 `apk_path` / `aab_path` 键时回退到这两个文件（显式传空串表示不用 AAB）。
- **keystore 不要打进 zip**：插件包是可读文件，口令/私钥放进去等于公开；每个渠道在 UI 里选外部 keystore。
- APK/AAB 会让 zip 变大（导入会复制到用户插件目录）；第三方包随插件分发前请确认授权。
- 注意区分：这里的 `assets/base.apk` 是**插件自己的资源**；渠道文件里的 `asset.path` 是**注入目标 APK 的 `assets/`**。
- iframe UI 不能 `fetch` 插件目录里的相对资源；插件 UI 的图片/样式必须内联在 `ui/index.html`，
  而 APK/AAB 这种二进制资源由后端读取。

源 AAB 的一致性 guard（`bundletool dump manifest` 只用于这里）：

- 同包名、同 versionCode / versionName；
- 只含一个 `base` 模块（无 dynamic feature / asset pack；`BUNDLE-METADATA/`、`META-INF/` 等标准顶层目录不算模块）；
- 清单是否含 `dist:*`（含则提示：直改用 APK 清单，可能丢失 bundle 专属元素）。

硬条件不满足时：`google_mode=auto` 自动降级为重建，`google_mode=splice` 直接报错（不静默出坏包），
`google_mode=reconstruct` 一律重建。另有「严格校验 AAB」开关（UI 默认开启），会额外跑 `bundletool build-apks`。

## 使用步骤（插件页操作）

1. 进「插件」页，先点右上角「导入」选择 `plugins-dist/white-label-packer-1.3.0.zip`；导入后左侧出现
   **白包打包（多渠道）**（v1.3.0，用户插件，无「内建」标签）。
2. 右侧是插件自带 UI（沙箱 iframe，经 `window.pluginBridge` 调后端插件）：
   选**基础 APK** → 自动解析包名/版本/图标；可选选**同版本 AAB** → 自动带一致性校验状态；
   选 AAB 模式（`auto` / `splice` / `reconstruct`）。解析按钮仍保留，用于手动重新解析。
3. 预置三张渠道卡（`other` / `samsung` / `google`），可点「＋ 其他包」继续添加任意自定义渠道。
   逐项填：启用、包名、应用名、versionCode、versionName、图标、keystore（路径 / alias / storepass / keypass）、
   格式（APK / AAB / 两者）、渠道 meta-data（多行 `name=value`，空行与 `#` 注释忽略）、额外权限
   （每行一个 `<uses-permission>`，如 `com.android.vending.BILLING`）、渠道文件
   （`assets` 目标路径 + 文本内容，沙箱 iframe 读不了本地文件，所以没有文件选择框），以及
   「重命名 provider authority」「重命名自定义权限」「移除 sharedUserId」三个开关。
   APK / AAB / 图标 / 输出目录的选择框由宿主代弹原生对话框。
   包名不能与源 APK 相同，渠道之间也不能重复（UI 会直接标红）；自定义渠道可随时删除。
4. 底部设输出目录（默认 `<BT_OUTPUT_DIR>/white-label/`），按需勾选「严格校验 AAB」和「记住配置」。
5. 点「开始打包」：日志控制台实时输出解码 / aapt2 链接 / zip 重组 / 对齐 / 签名 / bundletool 校验各步骤；
   运行中可「取消」（协作式取消，终止当前子进程）。
6. 完成后结果卡片列出每个渠道的产物路径，可直接打开所在目录；失败时给出错误与报告路径。

> 插件页对带 `ui` 的插件只渲染 iframe：运行按钮、日志、结果都由插件 UI 自己画，宿主只转发
> log/result/error 事件并代发 toast/confirm（机制见 `docs/PLUGIN_PACKAGE.md`）。

## 两种 AAB 模式

### 直改（splice / direct patch）

源 AAB 可用且 guard 通过时，只动 manifest、图标、assets 与签名，bundle 其余结构原样保留：

```text
bundletool dump manifest --bundle=<aab>        # 只用于一致性 guard：
                                               # 包名 / versionCode / versionName / 单 base / dist:*
  → apktool 解码出的文本 AndroidManifest.xml    # 真正改身份（包名/应用名/版本/meta-data/authorities）
  → aapt2 link --proto-format                  # 生成 proto 格式的 AndroidManifest.xml
  → 替换 AAB 内 base/manifest/AndroidManifest.xml
  → 替换 base/res/ 下图标文件（同资源路径）
  → 注入 base/assets/ 渠道文件
  → 删除旧 META-INF 签名条目（残留旧签名会导致重签/校验失败）
  → jarsigner 重签 → bundletool validate →（严格校验时）bundletool build-apks
```

注意：`bundletool dump manifest` 出来的清单里枚举属性是 `0x...` 数值，aapt2 不认，所以它**只做 guard**；
编进 AAB 的 proto 清单来自 apktool 解码出的文本清单。直改完成后会按 SHA-256 对比未改动条目
（`base/resources.pb`、`BundleConfig.pb`、`base/dex/`、`base/lib/`），发现被破坏立即报错。

### 重建（reconstruct）

没有源 AAB（或直改 guard 失败）时，从基础 APK 的资源重建一个 AAB：

```text
aapt2 compile + link --proto-format            # 生成 base/manifest/、resources.pb、res/
  → 组装模块目录：manifest/ resources.pb res/ dex/ lib/ assets/ root/
  → bundletool build-bundle --modules=<module.zip> --output=<aab>
  → jarsigner 重签 → bundletool validate
```

`dex/`、`lib/`、`assets/` 从基础 APK 取，`resources.pb` 由 aapt2 重新生成，`build-bundle` 带 `--overwrite`。
重建产物与源 AAB 不是字节级等价；Play 侧只关心同包名 + 递增的 versionCode。

### 模式选择

| `google_mode` | 行为 |
|---|---|
| `auto`（默认） | 有 AAB 且 guard 通过 → 直改；否则静默回退重建 |
| `splice` | 强制直改；guard 失败直接报错（避免"以为是直改"） |
| `reconstruct` | 强制重建，完全不使用源 AAB |

没选源 AAB 时，`auto` / `splice` 都没有可改的对象，UI 只允许 `reconstruct`（另两项置灰）。
后端兼容旧值 `rebuild`（内部映射为 `reconstruct`），文档与 UI 统一用 `reconstruct`。

## APK 与 AAB 的签名差异（关键）

| 产物 | 对齐 | 签名工具 | 格式 | 校验 |
|---|---|---|---|---|
| APK | `zipalign -f -P 16 4` | `apksigner` | APK 签名（v1/v2/v3） | `apksigner verify --print-certs` |
| AAB | **不** zipalign | `jarsigner` | JAR 签名（v1） | `bundletool validate` + `build-apks` 跑通 |

AAB 是 JAR 容器，**必须**用 `jarsigner` 做 v1 签名；对它跑 zipalign / apksigner 会破坏 bundle 结构或被
bundletool 拒绝。AAB 重签命令：

```bash
runtime/jre/bin/jarsigner.exe -keystore <channel.keystore> -storepass <pass> [-keypass <kp>] -digestalg SHA-256 <output.aab> <alias>
```

不强制 `-sigalg`：JDK 会按 key 类型自动选 `SHA256withRSA` / `SHA256withECDSA`，digest 固定 SHA-256；
如果你只允许 RSA，可显式加 `-sigalg SHA256withRSA`。

AAB 重签时旧的 `META-INF` 签名条目会先被删除，再写入新的 `META-INF/MANIFEST.MF` + `*.SF` + `*.RSA`。
产物里出现这套新条目是正常的（JAR 签名的必然结果），不是残留旧签名。

**Play 上传密钥**：上架 Google Play 的 AAB 必须用你的 **upload key** 签名；Play App Signing 会用发布密钥
重签最终分发给用户的 APK。所以：

- 插件不生成、不托管密钥；keystore 丢失就无法更新已上架应用；
- 上传前确认用的是 Play 后台登记的那把 upload keystore；
- 谷歌渠道可选同时导出**测试 APK**（由 `bundletool build-apks` 从新 AAB 生成并 apksigner 签名），
  只用于真机安装验证，不能上架。

## 图标与应用名规则与限制

**应用名**：只改 manifest 的 `android:label` 字面量。

- 桌面/启动器显示新名字；
- 应用内读取 `R.string.app_name` 或"关于"页等处的名字**不变**（不改 `strings.xml`）；
- 原本指向 `@string/xxx` 的 label 会被替换为字面量，资源本身不新增/不删除。

**图标**：替换**已存在**的 launcher 图标栅格文件，按目标 density 缩放后写回原资源路径（资源 ID 不变）。

- 尺寸任意，插件按目标尺寸双线性重采样（`backend/app/utils/png_image.py`，纯 stdlib，无 PIL）；
- 用户提供的图标必须是受支持的 8-bit PNG（colour type 2/3/6、非交错），否则直接报错（不会静默跳过）；
- 目标是 WebP 文件时直接写入 PNG 字节（Android 按内容解码），并给 warning——插件不做 WebP 编码；
- 自适应图标优先替换 `foreground` 引用的位图（`background` 保留原样）；前景/背景层是矢量（vector XML）时跳过并 warning，
  Android 8.0+ 可能仍显示旧图标；
- 目标文件尺寸无法识别 / 缩放失败 / 不在源 APK 或解码项目里 → 跳过该文件并 warning（不写坏资源）；
- **源 APK 的 manifest 没有声明 `android:icon` / `roundIcon` 时无法替换**（插件不凭空新增图标资源），
  会给出 warning；要换图标请用本身声明了 launcher icon 的源包；
- 不新增 drawable、不改资源 ID、不改应用内 `app_name` 字符串；
- 图标替换是可选步骤，不选则保留原图标。

## 渠道标识注入

1. **meta-data**：每行 `name=value`，在 manifest `<application>` 下写/覆盖渠道键值
   （`<meta-data android:name="name" android:value="value"/>`）；要改已有键填同名即可。
2. **渠道文件**：字段是 `{path, content}`——`path` 是**产物内目标路径**（相对路径，自动补 `assets/` 前缀，
   禁止绝对路径和 `..`），`content` 是直接写入的**文本**（沙箱 iframe 读不了本地文件，没有文件选择框）。
   最终按该路径写入 `assets/`（APK 走 zip 重组写入，AAB 直改注入 `base/assets/`）。
3. **占位符**：渠道 meta-data 的 `value`（`name` 也会同样替换）与渠道文件 `content` 支持占位符，
   运行前替换为当前渠道的实际值：

   | token | 替换为 |
   |---|---|
   | `{channel}` | 渠道标识（`other` / `samsung` / `google` / 自定义 id） |
   | `{package}` | 该渠道的新包名 |
   | `{app_name}` | 该渠道的应用名 |
   | `{version_name}` | 该渠道的 versionName |
   | `{version_code}` | 该渠道的 versionCode |

   未知 token 原样保留；应用名本身是 manifest 字面量，不做占位符替换。

> 占位符只做文本替换，不会改 dex / 二进制内容。

## 额外权限（uses-permission）

- 每行一个权限名，例如 `com.android.vending.BILLING`；插件把它作为 `<uses-permission>` 追加到 manifest
  （APK 与 AAB 都生效，AAB 直改时写入新的 manifest）。
- 已存在的同名权限不会重复添加；不会删除源包已有权限。
- `com.android.vending.BILLING` 只表示声明结算权限，Google Play 后台仍需配置商品/结算；它不是“开通内购”的开关。
- 权限名必须是合法包名形式（`com.android.vending.BILLING`、`android.permission.XXX`），否则该渠道报错。

## profiles 与产物 / 报告

- **profiles**：`<BT_OUTPUT_DIR>/white-label/profiles.json`，勾「记住配置」时写入，只含非机密字段
  （就是单渠道配置去掉 `keystore.storepass` / `keystore.keypass`）。结构示意：

  ```json
  {
    "schema": 1,
    "output_dir": "<BT_OUTPUT_DIR>/white-label",
    "google_mode": "auto",
    "channels": {
      "other": {
        "label": "其他包",
        "enabled": true,
        "package_name": "com.example.other",
        "app_name": "示例-其他包",
        "version_code": 7,
        "version_name": "1.2.3",
        "icon_path": "",
        "format": "apk",
        "keystore": { "path": "...", "alias": "..." },
        "metadata": [{ "name": "channel_id", "value": "other" }],
        "asset": { "path": "assets/channel.json", "content": "{\"channel\":\"{channel}\"}" },
        "rename_authorities": false,
        "rename_permissions": false,
        "remove_shared_uid": true
      },
      "partner": {
        "label": "合作方",
        "enabled": true,
        "package_name": "com.example.partner",
        "app_name": "示例-合作方",
        "version_code": 8,
        "version_name": "1.2.4",
        "icon_path": "",
        "format": "aab",
        "keystore": { "path": "...", "alias": "..." },
        "metadata": [],
        "permissions": ["com.android.vending.BILLING"],
        "asset": { "path": "", "content": "" },
        "rename_authorities": true,
        "rename_permissions": true,
        "remove_shared_uid": true
      }
    }
  }
  ```

  口令**不落盘**，每次运行在界面输入；换机器/重装后只需重新填口令。
- **产物目录**：默认 `<BT_OUTPUT_DIR>/white-label/`（可在界面改）。命名固定：
  `<output_dir>/{package}-{channel}.apk`、`<output_dir>/{package}-{channel}.aab`
  （如 `com.example.other-other.apk`、`com.example.partner-partner.aab`）。`BT_OUTPUT_DIR` 来自 `backend/server.config.json` /
  环境变量，默认 `output/`（相对 `backend/` 解析）。
- **报告**：`white-label-report-YYYYmmdd-HHMMSS.json`（每次运行一份，时间戳带时分秒），顶层含
  `source`、`aab`（guard 结果）、`google_mode`、`output_dir`、`items`、`errors`、`warnings`。
  每个 `items[]` 记录：`apk_path` / `aab_path` / `aab_mode`（splice|reconstruct）、`size_*`、`sha256_*`、
  `signer_sha256`、`icon`（replaced / skipped）、`warnings`、`error`、`duration_ms`。
- **verify 字段**（`items[].verify`）：值为 `"ok"` 或错误文本。
  | 产物 | 字段 |
  |---|---|
  | APK | `badging`、`apksigner`、`zipalign`、`resource_ids` |
  | AAB | `jarsigner`、`keytool`、`bundletool_validate`、`bundletool_build_apks` |

  `bundletool_build_apks` 只在「严格校验 AAB」（`strict_aab_check`，默认 `true`）时执行，命令必须带
  `--aapt2=<runtime/aapt/aapt2.exe>`（精简 JRE 缺 jar provider，见下文）。
- **中间文件**：解码目录、编译产物等在插件任务工作目录（`context.work_dir(task_id)`），不污染输出目录。

## 限制与排错

**已知限制**

- **加固包**：360 / 腾讯乐固 / 梆梆等加固包必须先脱壳；加固壳的完整性自校验会在改包名/签名后崩溃。
- **dex 不改**：硬编码旧包名的代码（反射、字符串比较、`BuildConfig.APPLICATION_ID`）不会被改写，
  `BuildConfig` 是编译期常量。
- **第三方 SDK 白名单**：地图/支付/推送/统计等按"包名 + 签名"校验的 SDK 会失败，需在对应后台为新包名、
  新签名登记（每个渠道一套）。
- **无 AAB-only 输入**：基础 APK 必填，只给 AAB 无法出包。
- **多模块 AAB 不直改**：存在 dynamic feature / asset pack 时只能重建，分发形态可能与源包不同。
- **不生成 keystore**，也不做商店资质/隐私政策/合规审核，不保证任何商店过审。
- split APK / `.apks` 不能作为基础包（会直接报错，资源不完整）。

**常见问题**

| 现象 | 常见原因 | 处理 |
|---|---|---|
| 白包启动闪退 / 弹校验失败 | 加固壳、SDK 签名校验、dex 硬编码包名 | 换非加固包；在 SDK 后台登记新包名/签名 |
| 谷歌直改失败或自动回退 | AAB 与 APK 包名/versionCode/versionName 不一致、多模块 | 用同一构建的 APK + AAB；或显式选 `reconstruct` |
| `bundletool validate` 失败 | 直改后结构或签名被破坏（残留 META-INF、manifest 不对） | 改用 `reconstruct`；检查是否误用 apksigner 签 AAB |
| `apksigner verify` 失败 | keystore/alias/口令错、签名方案配置 | 核对 alias 与口令，必要时显式指定 v1/v2 |
| 图标没变 | 自适应图标 vector 层未处理、启动器缓存 | 换非自适应图标包，或卸载重装清缓存 |
| WebP 图标 warning | 原图标是 WebP，写入的是 PNG 字节 | 正常现象（Android 按内容解码）；需要 WebP 自行转码 |
| 安装报签名冲突 | 与已装版本签名不同 | 先卸载旧包 |
| Play 拒收 AAB | 不是 upload key、versionCode 未递增 | 用 Play 后台登记的 upload keystore；提高 versionCode |

## 工具链与版本

全部随应用分发（`runtime/`），插件**不做任何下载**：

| 用途 | 版本 | 路径 |
|---|---|---|
| apktool（解码 APK，`-s` 不反编译 dex） | 2.12.1 | `runtime/apktool/apktool.jar` |
| aapt2（compile / link / `--rename-manifest-package` / `--stable-ids` / `--proto-format`） | 2.20 | `runtime/aapt/aapt2.exe` |
| bundletool（dump manifest / build-bundle / validate / build-apks） | 1.18.1 | `runtime/bundletool/bundletool.jar` |
| JRE（java / jarsigner / keytool） | — | `runtime/jre/bin/` |
| android.jar（aapt2 `-I`） | — | `runtime/android/android.jar` |
| zipalign（仅 APK） | — | `runtime/android/zipalign.exe` |
| apksigner（仅 APK） | — | `runtime/android/apksigner.jar` |
| zip 读写 | Python stdlib `zipfile` | 后端自带 |

关键命令（`<...>` 为占位；路径/参数以实际实现为准）：

```bash
# APK：解码（-s 保留原 dex，只反编译资源/manifest）
runtime/jre/bin/java.exe -jar runtime/apktool/apktool.jar d <base.apk> -s -f -o <work>/decoded

# aapt2：编译 + 链接（改 applicationId，资源包名不变；--stable-ids 由源 APK 生成）
runtime/aapt/aapt2.exe compile --dir <work>/decoded/res -o <work>/compiled.zip
runtime/aapt/aapt2.exe link -o <work>/unsigned.apk -I runtime/android/android.jar \
  --manifest <work>/decoded/AndroidManifest.xml \
  --rename-manifest-package <new.package.name> \
  --stable-ids <work>/stable-ids.txt

# APK：对齐 → 签名 → 校验
runtime/android/zipalign.exe -f -P 16 4 <work>/unsigned.apk <work>/aligned.apk
runtime/jre/bin/java.exe -jar runtime/android/apksigner.jar sign --ks <channel.keystore> --ks-key-alias <alias> --out <output.apk> <work>/aligned.apk
runtime/jre/bin/java.exe -jar runtime/android/apksigner.jar verify --verbose --print-certs <output.apk>

# AAB：JAR 重签（v1）→ 校验（-sigalg 交给 JDK 按 key 类型选 RSA/EC）
runtime/jre/bin/jarsigner.exe -keystore <channel.keystore> -storepass <pass> [-keypass <kp>] -digestalg SHA-256 <output.aab> <alias>
runtime/jre/bin/java.exe -jar runtime/bundletool/bundletool.jar validate --bundle=<output.aab>

# AAB → 测试 APK：bundletool 内部要用 aapt2，精简 JRE 缺 jar:// provider，必须显式 --aapt2
runtime/jre/bin/java.exe -jar runtime/bundletool/bundletool.jar build-apks --bundle=<output.aab> --output=<output.apks> --aapt2=runtime/aapt/aapt2.exe
```

注意：打包版 `runtime/` 是精简 JRE，调用 bundletool 时显式传 `--aapt2 runtime/aapt/aapt2.exe`，
否则可能报 `Provider "jar" not found`（与 `backend/app/handlers/aab_handler.py` 的处理一致）。

## 测试与开发

```bash
# 全部后端契约测试（pytest，不在 npm scripts 里；从仓库根跑）
pytest tests/contracts/

# 只跑本插件 + PNG 工具
pytest tests/contracts/test_white_label_packer.py tests/contracts/test_png_image.py
```

- `tests/contracts/test_white_label_packer.py`：单元测试（渠道配置解析、包名/应用名改写、meta-data 注入、
  图标替换决策、AAB guard 判定、报告结构）+ **可跳过的运行时集成测试**（真正调用 apktool/aapt2/bundletool）。
- `tests/contracts/test_png_image.py`：`backend/app/utils/png_image.py` 的编解码 / 缩放测试
  （纯 stdlib，无外部依赖）。
- 集成测试的跳过条件：用例带 `pytest.mark.skipif(not _runtime_ready(), reason="runtime tools missing")`，
  `_runtime_ready()` 检查仓库 `runtime/` 下这些工具是否存在——`apktool/apktool.jar`、
  `aapt/aapt2.exe`、`android/{zipalign.exe, apksigner.jar, android.jar, smali-2.5.2.jar}`、
  `bundletool/bundletool.jar`、`jre/bin/{java.exe, jarsigner.exe, keytool.exe}`。
  **没有环境变量开关**；`runtime/` 不入库（`.gitignore`），缺任一工具就 skip。集成用例耗时约 1~2 分钟。
- **真实包验收清单**（手动，自动化测试不覆盖）：
  - [ ] 其他包渠道 APK 安装启动正常，桌面名/图标/包名正确
  - [ ] 三星渠道 APK 同上，且与其他包可共存
  - [ ] 自定义渠道（如 `partner`）APK/AAB 产物命名、签名、包名正确
  - [ ] 谷歌渠道 AAB：`bundletool validate` 通过，`build-apks` 出的测试 APK 可安装启动
  - [ ] 所有产物签名校验通过（APK 用 `apksigner verify`，AAB 用 `jarsigner -verify`）
  - [ ] 渠道 meta-data 与 `assets/` 文件确实在产物里（解包 / `aapt2 dump` 确认）
  - [ ] 额外权限（如 `com.android.vending.BILLING`）在产物 manifest 和 `dumpsys package` 的 requested permissions 里
  - [ ] 带 launcher icon 的源包：图标替换后桌面图标确实变化（源包未声明 icon 时只会 warning，不新增图标）
  - [ ] 直改模式产物与源 AAB 的 `resources.pb`、dex 一致（结构未被破坏）
  - [ ] 改过版本号的包 versionCode 生效（`aapt2 dump badging`）

## 文件索引

| 文件 | 作用 |
|---|---|
| `plugins-dist/white-label-packer/manifest.json` | 插件元数据（id / name / entry / ui / params） |
| `plugins-dist/white-label-packer/main.py` | 插件入口 `run(context, **params)`：APK / AAB 两条打包流水线 |
| `plugins-dist/white-label-packer/ui/index.html` | 自定义 UI（沙箱 iframe，单文件内联） |
| `plugins-dist/white-label-packer-1.3.0.zip` | 可直接在插件页「导入」的分发包 |
| `plugins-dist/README.md` | 分发/导入说明 |
| `backend/app/utils/png_image.py` | stdlib PNG 解码 / 缩放 / 编码（图标替换） |
| `backend/app/plugins/manager.py` | 插件扫描与加载（内置 + 用户目录、平铺 + 包目录） |
| `backend/app/plugins/context.py` | `PluginContext`：工具、`run_command`、`work_dir` |
| `backend/app/handlers/plugin_handler.py` | `plugin.list` / `run` / `reload` / `delete` |
| `backend/app/handlers/aab_handler.py` | AAB 签名/转换的既有实现，bundletool 调用可参照 |
| `tests/contracts/test_white_label_packer.py` | 本插件契约 + 运行时集成测试 |
| `tests/contracts/test_png_image.py` | PNG 工具单测 |
| `docs/PLUGIN_PACKAGE.md` | 插件包格式与 iframe UI 桥规范 |
| `<BT_OUTPUT_DIR>/white-label/` | 默认产物目录（含 `profiles.json`、`white-label-report-YYYYmmdd-HHMMSS.json`） |
