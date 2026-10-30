# 可分发插件

本目录存放**不随应用内建**、通过插件页导入的插件包。

## white-label-packer（白包打包）

- 源码：`white-label-packer/`（`manifest.json` + `main.py` + `ui/index.html`）
- 可直接导入：`white-label-packer-1.3.0.zip`
- 安装：打开 Blank Tool → 插件页 → 右上角「导入」→ 选择上面的 zip → 左侧出现
  **白包打包（多渠道）**（用户插件，无「内建」标签）。
- 更新：重新导入 zip，弹窗选覆盖即可；删除走插件页的「删除」。
- 卸载/清理：删除 `%LOCALAPPDATA%\blank_tool\plugins\white-label-packer\`（macOS/Linux 对应缓存目录）。

## 自带默认 APK / AAB

插件包可以携带资源。把默认输入放到源码目录：

```text
white-label-packer/assets/base.apk
white-label-packer/assets/base.aab
```

重新打包后，导入的用户不用再选文件；UI 会自动填入路径，仍可改选外部文件。后端在
`apk_path` / `aab_path` 缺省时也会回退到这两个文件。**不要把 keystore / 口令打进 zip**。
资源会显著增大 zip（APK/AAB 体积 + 解压复制），第三方包分发前请确认授权。

## 重新打包

修改插件源码后，在仓库根执行：

```powershell
python scripts\pack_plugin.py plugins-dist\white-label-packer
```

脚本会读取 `manifest.json` 的 `version`，生成
`plugins-dist/white-label-packer-<version>.zip`（zip 根目录直接是
`manifest.json` / `main.py` / `ui/`，不带外层文件夹）。

> 插件运行在 Blank Tool 后端进程内，依赖应用的 `PluginContext`、`app.utils.png_image`
> 等接口；请使用与插件版本匹配的 Blank Tool（本插件自 2.5.1 起可用）。
