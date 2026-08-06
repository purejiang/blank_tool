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

- **需导入描述符**：`tools/android/` 下的 7 个工具描述符（aapt, adb, apksigner, apktool, bundletool, jarsigner, zipalign）必须通过工具管理页导入后，对应的工作流才能运行。
- **需自备二进制**：Android 工具链（ADB、Apktool、Bundletool、JDK 等）需放置在 `runtime/` 目录或通过工具管理页配置自定义路径。
- 当前包含 6 个工作流：download-install、decompile、recompile、sign、aab-install、decompile-edit-sign（反编译 APK，正则替换文件内容，重编译，zipalign 对齐，apksigner 签名）。

## 导入方式

### 工作流

1. 打开应用 → 工作流管理页（Phase 4）
2. 点击"导入"按钮
3. 选择 `examples/workflows/generic/` 或 `examples/workflows/android/` 下的 `.json` 文件
4. 导入后即可在任务中心选择模板执行

### 工具描述符

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
```
