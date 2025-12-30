<template>
  <div class="page other-tools-page">
    <div class="page-content responsive-two-column">
      <div class="left-panel">
        <div class="section responsive-section">
          <div class="section-header">
            <h2><span class="section-icon">🔌</span>插件管理</h2>
            <div class="section-actions">
              <button class="btn btn-sm btn-secondary" @click="reloadPlugins" :disabled="isLoading" data-tooltip="重新加载插件">
                <span :class="{ 'spin': isLoading }">🔄</span>
              </button>
            </div>
          </div>
          
          <div v-if="plugins.length === 0" class="empty-state">
            <p v-if="!isLoading">暂无已加载的插件</p>
            <p v-else>正在加载插件...</p>
          </div>

          <div v-else class="plugin-list">
            <div v-for="plugin in plugins" :key="plugin.name" class="plugin-item">
              <div class="plugin-header">
                <div class="plugin-title">
                  <h3>{{ plugin.name }}</h3>
                  <span class="plugin-version">v{{ plugin.version }}</span>
                </div>
                <div class="plugin-author">By {{ plugin.author }}</div>
              </div>
              <div class="plugin-body">
                <p class="plugin-description">{{ plugin.description }}</p>
              </div>
              <div class="plugin-actions">
                <button class="btn btn-sm btn-primary" @click="runPlugin(plugin)" :disabled="plugin.running">
                  <span v-if="!plugin.running">▶️ 运行</span>
                  <span v-else class="btn-spinner"></span>
                </button>
              </div>
              <div v-if="plugin.lastResult" class="plugin-result">
                <pre>{{ plugin.lastResult }}</pre>
              </div>
            </div>
          </div>
        </div>
      </div>
      
      <div class="right-panel">
        <div class="section">
          <h2><span class="section-icon">💡</span>如何添加插件</h2>
          <div class="help-content">
            <p>您可以通过编写 Python 脚本来扩展本工具的功能。</p>
            <ol>
              <li>编写一个 Python 脚本 (例如 <code>my_tool.py</code>)</li>
              <li>实现 <code>run(context, **kwargs)</code> 函数</li>
              <li>将脚本放入 <code>backend/plugins</code> 目录</li>
              <li>点击左侧的 <span class="icon">🔄</span> 刷新按钮</li>
            </ol>
            <div class="code-example">
<pre><code># 示例插件结构
DESCRIPTION = "插件描述"
VERSION = "1.0.0"
AUTHOR = "Your Name"

def run(context, **kwargs):
    context.log("开始执行...")
    # 您的业务逻辑
    return {"status": "ok"}
</code></pre>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, onMounted } from 'vue'
import PluginService from '@/services/PluginService'
import { useNotification } from '@/composables/useNotification'

export default {
  name: 'OtherToolsPage',
  setup() {
    const plugins = ref([])
    const isLoading = ref(false)
    const { showSuccess, showError } = useNotification()

    const loadPlugins = async () => {
      isLoading.value = true
      try {
        plugins.value = await PluginService.getPlugins()
      } catch (error) {
        showError('加载插件失败', error.message)
      } finally {
        isLoading.value = false
      }
    }

    const reloadPlugins = async () => {
      isLoading.value = true
      try {
        plugins.value = await PluginService.reloadPlugins()
        showSuccess('插件列表已更新')
      } catch (error) {
        showError('重载插件失败', error.message)
      } finally {
        isLoading.value = false
      }
    }

    const runPlugin = async (plugin) => {
      plugin.running = true
      plugin.lastResult = null
      try {
        const result = await PluginService.runPlugin(plugin.name)
        plugin.lastResult = JSON.stringify(result, null, 2)
        showSuccess(`插件 ${plugin.name} 执行完成`)
      } catch (error) {
        showError(`插件 ${plugin.name} 执行失败`, error.message)
        plugin.lastResult = `Error: ${error.message}`
      } finally {
        plugin.running = false
      }
    }

    onMounted(() => {
      loadPlugins()
    })

    return {
      plugins,
      isLoading,
      reloadPlugins,
      runPlugin
    }
  }
}
</script>

<style scoped>
.empty-state {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 200px;
  color: var(--text-secondary);
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.spin {
  animation: spin 1s linear infinite;
  display: inline-block;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.plugin-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.plugin-item {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 16px;
  transition: all 0.2s;
}

.plugin-item:hover {
  border-color: var(--primary-color);
  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
}

.plugin-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 8px;
}

.plugin-title {
  display: flex;
  align-items: center;
  gap: 8px;
}

.plugin-title h3 {
  margin: 0;
  font-size: 16px;
  color: var(--text-primary);
}

.plugin-version {
  font-size: 12px;
  background: var(--bg-primary);
  padding: 2px 6px;
  border-radius: 4px;
  color: var(--text-secondary);
}

.plugin-author {
  font-size: 12px;
  color: var(--text-secondary);
}

.plugin-description {
  color: var(--text-secondary);
  font-size: 14px;
  margin-bottom: 12px;
}

.plugin-actions {
  display: flex;
  justify-content: flex-end;
}

.plugin-result {
  margin-top: 12px;
  background: var(--bg-primary);
  padding: 8px;
  border-radius: 4px;
  font-size: 12px;
  overflow-x: auto;
}

.plugin-result pre {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-all;
}

.help-content {
  color: var(--text-primary);
  font-size: 14px;
  line-height: 1.6;
}

.help-content ol {
  padding-left: 20px;
  margin-bottom: 16px;
}

.help-content li {
  margin-bottom: 8px;
}

.code-example {
  background: var(--bg-secondary);
  padding: 12px;
  border-radius: 6px;
  overflow-x: auto;
  border: 1px solid var(--border-color);
}

.code-example pre {
  margin: 0;
  font-family: 'Consolas', monospace;
  font-size: 13px;
}

.icon {
  font-style: normal;
}
</style>
