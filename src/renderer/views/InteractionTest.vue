<template>
  <div class="test-page">
    <h2>交互测试</h2>
    <div class="controls">
      <button @click="runAll">运行全部</button>
      <label class="toggle">
        <input type="checkbox" v-model="systemSearch" @change="applySearchToggle" />
        <span>系统工具查找开关</span>
      </label>
    </div>
    <div class="groups">
      <section>
        <h3>系统 IPC</h3>
        <div class="actions">
          <button @click="runGroup('system')">运行本组</button>
        </div>
        <ul>
          <li v-for="t in results.system" :key="t.id" class="item">
            <span class="label">{{ t.label }}</span>
            <span class="status" :class="t.status">{{ t.status }}</span>
            <span class="time">{{ t.time }}</span>
            <pre v-if="t.output">{{ formatOutput(t.output) }}</pre>
          </li>
        </ul>
      </section>
      <section>
        <h3>后端工具</h3>
        <div class="actions">
          <button @click="runGroup('tools')">运行本组</button>
        </div>
        <ul>
          <li v-for="t in results.tools" :key="t.id" class="item">
            <span class="label">{{ t.label }}</span>
            <span class="status" :class="t.status">{{ t.status }}</span>
            <span class="time">{{ t.time }}</span>
            <pre v-if="t.output">{{ formatOutput(t.output) }}</pre>
          </li>
        </ul>
      </section>
      <section>
        <h3>缓存</h3>
        <div class="actions">
          <button @click="runGroup('cache')">运行本组</button>
        </div>
        <ul>
          <li v-for="t in results.cache" :key="t.id" class="item">
            <span class="label">{{ t.label }}</span>
            <span class="status" :class="t.status">{{ t.status }}</span>
            <span class="time">{{ t.time }}</span>
            <pre v-if="t.output">{{ formatOutput(t.output) }}</pre>
          </li>
        </ul>
      </section>
      <section>
        <h3>设备</h3>
        <div class="actions">
          <button @click="runGroup('device')">运行本组</button>
        </div>
        <div class="inline">
          <input v-model="deviceId" placeholder="设备ID" />
          <button @click="startLogcat">启动日志</button>
          <button @click="stopLogcat">停止日志</button>
        </div>
        <ul>
          <li v-for="t in results.device" :key="t.id" class="item">
            <span class="label">{{ t.label }}</span>
            <span class="status" :class="t.status">{{ t.status }}</span>
            <span class="time">{{ t.time }}</span>
            <pre v-if="t.output">{{ formatOutput(t.output) }}</pre>
          </li>
        </ul>
    <div class="logcat" v-if="logLines.length">
          <h4>Logcat</h4>
          <pre class="log" ref="logBox">
            <code>
              <div v-for="(l, i) in logLines" :key="i">{{ i + 1 }} {{ l }}</div>
            </code>
          </pre>
        </div>
      </section>
      <section>
        <h3>APK</h3>
        <div class="actions">
          <button @click="selectApk">选择 APK 并分析</button>
        </div>
        <ul>
          <li v-for="t in results.apk" :key="t.id" class="item">
            <span class="label">{{ t.label }}</span>
            <span class="status" :class="t.status">{{ t.status }}</span>
            <span class="time">{{ t.time }}</span>
            <pre v-if="t.output">{{ formatOutput(t.output) }}</pre>
          </li>
        </ul>
      </section>
    </div>
  </div>
  </template>
<script>
import { ref, onMounted, nextTick } from 'vue'
import unifiedAPI from '../api/unifiedApi.js'
export default {
  name: 'InteractionTest',
  setup() {
    const now = () => new Date().toLocaleTimeString()
    const electronAPI = unifiedAPI.getAPI()
    const deviceId = ref('')
    const systemSearch = ref(false)
    const logLines = ref([])
    const currentProcessId = ref('')
    const results = ref({
      system: [
        { id: 'devtools-open', label: 'open-dev-tools', status: 'pending', time: '', output: null },
        { id: 'devtools-toggle', label: 'toggle-dev-tools', status: 'pending', time: '', output: null },
        { id: 'msg-box', label: 'show-message-box', status: 'pending', time: '', output: null },
        { id: 'open-dialog', label: 'show-open-dialog', status: 'pending', time: '', output: null },
        { id: 'save-dialog', label: 'show-save-dialog', status: 'pending', time: '', output: null },
        { id: 'file-stats', label: 'get-file-stats', status: 'pending', time: '', output: null }
      ],
      tools: [
        { id: 'tools-all', label: 'tool.get_tools', status: 'pending', time: '', output: null },
        { id: 'tools-adb', label: 'tool.check_tool_availability(adb)', status: 'pending', time: '', output: null },
        { id: 'aapt-version', label: 'aapt.version', status: 'pending', time: '', output: null }
      ],
      cache: [
        { id: 'cache-info', label: 'cache.info', status: 'pending', time: '', output: null },
        { id: 'cache-clear', label: 'cache.clear', status: 'pending', time: '', output: null }
      ],
      device: [
        { id: 'adb-devices', label: 'adb.devices', status: 'pending', time: '', output: null },
        { id: 'device-info', label: 'device.info', status: 'pending', time: '', output: null }
      ],
      apk: [
        { id: 'apk-analyze', label: 'apk.analyze', status: 'pending', time: '', output: null }
      ]
    })
    const setResult = (group, id, status, output) => {
      const item = results.value[group].find(x => x.id === id)
      if (!item) return
      item.status = status
      item.time = now()
      item.output = output || null
    }
    const formatOutput = o => {
      try { return typeof o === 'string' ? o : JSON.stringify(o, null, 2) } catch { return String(o) }
    }
    const runSystem = async () => {
      try {
        const r1 = electronAPI ? await electronAPI.openDevTools() : false
        setResult('system', 'devtools-open', r1 ? 'success' : 'error', r1)
      } catch (e) { setResult('system', 'devtools-open', 'error', e.message) }
      try {
        const r2 = electronAPI ? await electronAPI.toggleDevTools() : false
        setResult('system', 'devtools-toggle', r2 ? 'success' : 'error', r2)
      } catch (e) { setResult('system', 'devtools-toggle', 'error', e.message) }
      try {
        const r3 = electronAPI ? await electronAPI.showMessageBox({ type: 'info', message: '消息框测试' }) : null
        setResult('system', 'msg-box', r3 ? 'success' : 'error', r3)
      } catch (e) { setResult('system', 'msg-box', 'error', e.message) }
      try {
        const r4 = electronAPI ? await electronAPI.showOpenDialog({ properties: ['openFile', 'multiSelections'] }) : null
        setResult('system', 'open-dialog', r4 ? 'success' : 'error', r4)
        let statPath = r4 && r4.filePaths && r4.filePaths[0]
        if (statPath) {
          const st = await electronAPI.getFileStats(statPath)
          setResult('system', 'file-stats', st ? 'success' : 'error', st)
        } else {
          setResult('system', 'file-stats', 'skipped', { reason: '未选择文件' })
        }
      } catch (e) { setResult('system', 'open-dialog', 'error', e.message) }
      try {
        const r5 = electronAPI ? await electronAPI.showSaveDialog({}) : null
        setResult('system', 'save-dialog', r5 ? 'success' : 'error', r5)
      } catch (e) { setResult('system', 'save-dialog', 'error', e.message) }
    }
    const runTools = async () => {
      try {
        const r1 = electronAPI ? await electronAPI.getCacheInfo() : null
        setResult('cache', 'cache-info', r1 ? 'success' : 'error', r1)
      } catch (e) { setResult('cache', 'cache-info', 'error', e.message) }
      try {
        const r2 = electronAPI ? await electronAPI.clearCache([], true) : null
        setResult('cache', 'cache-clear', r2 ? 'success' : 'error', r2)
      } catch (e) { setResult('cache', 'cache-clear', 'error', e.message) }
      try {
        const r3 = await unifiedAPI.call('tool.get_tools', {})
        setResult('tools', 'tools-all', r3 ? 'success' : 'error', r3)
      } catch (e) { setResult('tools', 'tools-all', 'error', e.message) }
      try {
        const r4 = electronAPI ? await electronAPI.checkTool('adb') : null
        setResult('tools', 'tools-adb', r4 ? 'success' : 'error', r4)
      } catch (e) { setResult('tools', 'tools-adb', 'error', e.message) }
      try {
        const r5 = await unifiedAPI.call('aapt.version', {})
        setResult('tools', 'aapt-version', r5 ? 'success' : 'error', r5)
      } catch (e) { setResult('tools', 'aapt-version', 'error', e.message) }
    }
    const runDevice = async () => {
      try {
        const r1 = await unifiedAPI.call('adb.devices', {})
        setResult('device', 'adb-devices', r1 ? 'success' : 'error', r1)
        const list = r1 && r1.payload ? r1.payload : []
        const id = deviceId.value || (Array.isArray(list) && list[0] ? (typeof list[0] === 'string' ? list[0] : list[0].id) : '')
        if (!id) { setResult('device', 'device-info', 'skipped', { reason: '无设备' }); return }
        const r2 = await unifiedAPI.call('device.info', { device_id: id })
        setResult('device', 'device-info', r2 ? 'success' : 'error', r2)
      } catch (e) { setResult('device', 'adb-devices', 'error', e.message) }
    }
    const selectApk = async () => {
      try {
        const sel = electronAPI ? await electronAPI.showOpenDialog({ properties: ['openFile'], filters: [{ name: 'APK', extensions: ['apk'] }] }) : null
        if (!sel || !sel.filePaths || !sel.filePaths[0]) { setResult('apk', 'apk-analyze', 'skipped', { reason: '未选择APK' }); return }
        const r = await unifiedAPI.call('apk.analyze', { apk_path: sel.filePaths[0] })
        setResult('apk', 'apk-analyze', r ? 'success' : 'error', r)
      } catch (e) { setResult('apk', 'apk-analyze', 'error', e.message) }
    }
    const startLogcat = async () => {
      logLines.value = []
      currentProcessId.value = ''
      if (!deviceId.value) { return }
      try {
        const r = await electronAPI.startLogcat(deviceId.value)
        setResult('device', 'adb-devices', 'success', r)
      } catch (e) {}
    }
    const stopLogcat = async () => {
      if (!currentProcessId.value) return
      try { 
        await electronAPI.stopLogcat(currentProcessId.value)
        if (electronAPI && electronAPI.removeLogcatListener) {
          electronAPI.removeLogcatListener()
        }
        currentProcessId.value = ''
      } catch (e) {}
    }
    const onLog = (event, payload) => {
      const p = payload || {}
      if (p.process_id && !currentProcessId.value) { currentProcessId.value = p.process_id }
      const line = p.line || ''
      if (line) { 
        logLines.value.push(line) 
        nextTick(() => {
          const el = logBox.value
          if (el) el.scrollTop = el.scrollHeight
        })
      }
    }
    if (electronAPI && electronAPI.onLogcatOutput) {
      electronAPI.onLogcatOutput(onLog)
    }
    if (electronAPI && electronAPI.onLogcatFinished) {
      electronAPI.onLogcatFinished(() => { currentProcessId.value = '' })
    }
    const applySearchToggle = async () => {
      try {
        const r = await unifiedAPI.call('tool.set_search_mode', { system_search: systemSearch.value })
        setResult('tools', 'tools-all', r ? 'success' : 'error', r)
      } catch (e) {}
    }
    const runGroup = async (group) => {
      if (group === 'system') await runSystem()
      if (group === 'tools') await runTools()
      if (group === 'cache') await runTools()
      if (group === 'device') await runDevice()
      if (group === 'apk') await selectApk()
    }
    const runAll = async () => {
      await runSystem()
      await runTools()
      await runDevice()
    }
    onMounted(() => { runAll() })
    const logBox = ref(null)
    return { results, runGroup, runAll, formatOutput, deviceId, startLogcat, stopLogcat, logLines, systemSearch, applySearchToggle, logBox }
  }
}
</script>
<style scoped>
.test-page { padding: var(--spacing-lg); }
.controls { margin-bottom: var(--spacing-md); }
.toggle { margin-left: var(--spacing-md); display: inline-flex; gap: var(--spacing-xs); align-items: center; }
.groups section { margin-bottom: var(--spacing-lg); }
.actions { margin-bottom: var(--spacing-sm); }
.item { display: grid; grid-template-columns: 1fr auto auto; gap: var(--spacing-sm); align-items: center; padding: var(--spacing-xs) 0; }
.label { color: var(--text-primary); }
.status { padding: 2px 8px; border-radius: 4px; font-size: 12px; }
.status.success { background: #e6ffed; color: #037b21; }
.status.error { background: #ffecec; color: #b00020; }
.status.skipped { background: #f2f2f2; color: #666; }
.time { color: var(--text-secondary); font-size: 12px; }
pre { background: var(--bg-secondary); padding: 8px; border-radius: 4px; overflow: auto; max-height: 180px; }
.inline { display: flex; gap: var(--spacing-sm); align-items: center; margin-bottom: var(--spacing-sm); }
.inline input { padding: 6px 8px; border: 1px solid var(--border-color); border-radius: 4px; background: var(--bg-secondary); color: var(--text-primary); }
.logcat .log { height: 280px; overflow: auto; }
.logcat .log { font-size: 12px; line-height: 1.25; }
</style>
