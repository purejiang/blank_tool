# 示例包

本目录提供可导入的示例工作流与工具描述符，**不随应用打包分发**（examples/ 仅为仓库参考）。导入入口见下文。

## 包分类

### 通用示例 (`workflows/generic/`)

- **零外部依赖**：仅使用内置原子工具（`file.*`、`dir.*`、`text.grep`、`text.replace`、`flow.*` 等），无需任何外部二进制或系统工具。
- **导入即跑**：直接通过 CLI 或工作流管理页导入后即可运行，不依赖任何描述符或运行时配置。
- 当前包含：
  - `dir-report.json` — 扫描目录并生成摘要报告。
  - `text-scanner.json` — 递归搜索目录中的文本模式，输出匹配结果。

### Android 示例 (`workflows/android/` + `tools/android/`)

- **需导入描述符**：`tools/android/` 下的 12 个工具描述符（aapt, adb, apk-audit, apk-resolve, apk-signature, apksigner, apktool, bundletool, jarsigner, validate-entry, validate-report, zipalign）必须通过工具管理页导入后，对应的工作流才能运行。其中 `apk-audit`、`apk-resolve`、`apk-signature`、`validate-entry`、`validate-report` 是 `python_script` 类型（依赖 Python 环境），其余 7 个是 `java_jar`/`binary` 类型。
- **需自备二进制**：Android 工具链（ADB、Apktool、Bundletool、JDK 等）需放置在 `runtime/` 目录或通过工具管理页配置自定义路径。`apk-audit` 脚本会自动搜索 `runtime/apktool/apktool.jar` 和 Java 路径（`BT_JAVA_BIN` / `JAVA_HOME` / PATH）；`apk-signature` 先用 keytool 读 v1 签名，v2/v3-only 包回退到 `runtime/android/apksigner.jar`。
- 当前包含 9 个工作流：download-install、decompile、recompile、sign、aab-install、decompile-edit-sign（反编译→修改→重编译→签名）、apk-audit（批量反编译多个 APK，提取关键信息，生成 HTML + Markdown 对比报告）、apk-validate + apk-validate-entry（APK 参数验证，见下）。

#### APK 参数验证（apk-validate）

按映射表逐条验证 APK 内容并生成 Markdown 报告。三个入参：`apk_path`（本地路径或 http(s) 链接，远程自动下载）、`mapping`（映射表，JSON 列表）、`output_path`（报告输出路径）。映射表每条 entry：

```json
{"name": "login", "type": "file", "path": "assets/login.png", "value": "http://xxxx/login.png", "md5": "xxxxxx"}
```

- `type: "file"` — 验证文件 md5。`path` 可以是本地文件或 **APK 包内路径**（先查磁盘，再查 APK zip）；`value` 为 http(s) 链接时下载作为参考文件。有 `md5` 时**所有**来源都必须一致（all-match）；无 `md5` 且有两个来源时两者互比。
- `type: "text"` — 文本匹配：`key` 提取 properties 键值（支持 `=`/`:`），`match` 取 `equals`（默认）/ `exact` / `regex` / `absent`，如验证 `assets/channel.properties` 中 `channel=huawei`。
- `type: "apk"` — APK 整包 md5。
- `type: "signature"` — 签名证书 MD5 指纹比对。

任一 entry 失败时 `flow.assert` 使整个工作流失败（报告仍会生成）。**注意**：`apk-validate` 依赖 `apk-validate-entry` 子模板，两个模板都必须导入（GUI 分别导入两个 JSON；CLI 需先把 `apk-validate-entry.json` 放入模板目录）。

## 导入方式

### 批量导入（推荐）

```bash
# 一次导入整个 Android 工具包（12 个描述符，两阶段校验，任一坏文件整体不写）
python cli/cli.py import-pack examples/tools/android

# 一次导入整个工作流目录（含 apk-validate 与其子模板 apk-validate-entry）
python cli/cli.py import-templates examples/workflows/android
python cli/cli.py import-templates examples/workflows/generic
```

后端 API 同样可用：`tool.import_pack {path}` / `template.import_path {path}`（目录或单文件）。

### 工作流（单个）

1. 打开应用 → 工作流管理页（Phase 4）
2. 点击"导入"按钮
3. 选择 `examples/workflows/generic/` 或 `examples/workflows/android/` 下的 `.json` 文件
4. 导入后即可在任务中心选择模板执行

### 工具描述符（单个）

1. 打开应用 → 工具管理页（Phase 4）
2. 点击"导入描述符"按钮
3. 选择 `examples/tools/android/` 下的 `.json` 文件
4. 导入的工具将出现在工具列表中，可在工作流中引用

## CLI 快速验证

```bash
# 通用示例（无需任何准备）
python cli/cli.py run examples/workflows/generic/dir-report.json --input target_dir=.
python cli/cli.py run examples/workflows/generic/text-scanner.json --input target_dir=./src --input pattern="import"

# Android 示例（需先导入描述符 + 自备二进制）
python cli/cli.py run examples/workflows/android/decompile.json --input apk_path=app.apk --input output_dir=./decompiled
python cli/cli.py run examples/workflows/android/recompile.json --input source_dir=./decompiled --input output_apk=./rebuilt.apk

# Android 全流程（反编译→修改→重编译→签名）
python cli/cli.py run examples/workflows/android/decompile-edit-sign.json \
    --tool-dir examples/tools/android \
    --input apk_path=app.apk \
    --input decompile_dir=./decompiled \
    --input edit_file_path=./decompiled/AndroidManifest.xml \
    --input edit_pattern="versionName" \
    --input edit_replacement="versionName-modified" \
    --input rebuilt_apk=./rebuilt.apk \
    --input aligned_apk=./aligned.apk \
    --input signed_apk=./signed.apk \
    --input ks_path=your.jks \
    --input ks_key_alias=testkey \
    --input ks_pass=pass:test12345

# APK 批量审计与对比（反编译多个 APK，提取关键信息，生成报告）
python cli/cli.py run examples/workflows/android/apk-audit.json \
    --tool-dir examples/tools/android \
    --input apk_paths="app-v1.apk,app-v2.apk" \
    --input output_dir=./audit-report
# 也支持传入目录（自动扫描 .apk 文件）：
python cli/cli.py run examples/workflows/android/apk-audit.json \
    --tool-dir examples/tools/android \
    --input apk_paths=./apks \
    --input output_dir=./audit-report

# APK 参数验证（需先把 apk-validate-entry 子模板放入模板目录）：
#   方式一（推荐）：用 import-templates 导入整个工作流目录（主模板+子模板一次到位）
python cli/cli.py import-templates examples/workflows/android
#   方式二：设置 BT_TEMPLATES_DIR 指向包含 apk-validate-entry.json 的目录
mkdir .templates && cp examples/workflows/android/apk-validate-entry.json .templates/
export BT_TEMPLATES_DIR=.templates
python cli/cli.py run examples/workflows/android/apk-validate.json \
    --tool-dir examples/tools/android \
    --input apk_path=app.apk \
    --input 'mapping=[{"name":"login","type":"file","path":"assets/login.png","md5":"xxxxxx"},{"name":"channel","type":"text","path":"assets/channel.properties","key":"channel","value":"huawei","match":"equals"},{"name":"whole","type":"apk","md5":"yyyyyy"},{"name":"sig","type":"signature","md5":"zzzzzz"}]' \
    --input output_path=./validation-report.md
```
