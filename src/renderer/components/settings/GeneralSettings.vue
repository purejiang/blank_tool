<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import serviceManager from '@services/ServiceManager'
import { useNotification } from '@composables/useNotification'

const { showSuccess, showError } = useNotification()

const settings = reactive({
  language: 'zh-CN',
  theme: 'auto',
  autoSave: true,
  enableNotifications: true,
})

const hasUnsavedChanges = ref(false)

const onSettingChange = () => {
  hasUnsavedChanges.value = true
}

const loadSettings = async () => {
  try {
    const svc = await serviceManager.getService('settings')
    const model = await svc.loadSettingsModel()
    if (model && model.settings) {
      Object.keys(settings).forEach(key => {
        if (Object.prototype.hasOwnProperty.call(model.settings, key)) {
          (settings as Record<string, unknown>)[key] = model.settings[key]
        }
      })
    }
  } catch (error: unknown) {
    console.error('Failed to load settings:', error)
  }
}

const saveGeneralSettings = async () => {
  try {
    const generalSettings = {
      language: settings.language,
      theme: settings.theme,
      autoSave: settings.autoSave,
      enableNotifications: settings.enableNotifications,
    }
    const svc = await serviceManager.getService('settings')
    await svc.saveSettings(generalSettings)
    hasUnsavedChanges.value = false
    showSuccess('General settings saved')
  } catch (error: unknown) {
    showError('Failed to save general settings', error instanceof Error ? error.message : '')
  }
}

const resetGeneralSettings = async () => {
  if (!confirm('Reset general settings to defaults?')) return
  try {
    settings.language = 'zh-CN'
    settings.theme = 'auto'
    settings.autoSave = true
    settings.enableNotifications = true
    await saveGeneralSettings()
    showSuccess('General settings reset')
  } catch (error: unknown) {
    showError('Failed to reset', error instanceof Error ? error.message : '')
  }
}

onMounted(() => {
  loadSettings()
})
</script>

<template>
  <div class="section responsive-section">
    <div class="section-header">
      <h2><span class="section-icon">&#x2699;&#xFE0F;</span>General Settings</h2>
      <div class="section-actions">
        <button class="btn btn-sm btn-primary" @click="saveGeneralSettings" title="Save settings">
          <span>&#x1F4BE;</span>
        </button>
        <button class="btn btn-sm btn-secondary" @click="resetGeneralSettings" title="Reset to defaults">
          <span>&#x1F504;</span>
        </button>
      </div>
    </div>
    <div class="settings-group">
      <div class="form-group">
        <label class="form-label" for="language">Language</label>
        <select id="language" class="form-control" v-model="settings.language" @change="onSettingChange">
          <option value="zh-CN">Simplified Chinese</option>
          <option value="en-US">English</option>
        </select>
        <p class="form-text">Select the display language</p>
      </div>
      <div class="form-group">
        <label class="form-label" for="theme">Theme</label>
        <select id="theme" class="form-control" v-model="settings.theme" @change="onSettingChange">
          <option value="auto">Follow System</option>
          <option value="light">Light</option>
          <option value="dark">Dark</option>
        </select>
        <p class="form-text">Select the application theme</p>
      </div>
      <div class="form-group">
        <div class="form-check">
          <input type="checkbox" id="autoSave" class="form-check-input" v-model="settings.autoSave" @change="onSettingChange">
          <label class="form-check-label" for="autoSave">Auto Save</label>
        </div>
        <p class="form-text">Automatically save configuration and work state</p>
      </div>
      <div class="form-group">
        <div class="form-check">
          <input type="checkbox" id="enableNotifications" class="form-check-input" v-model="settings.enableNotifications" @change="onSettingChange">
          <label class="form-check-label" for="enableNotifications">Enable Notifications</label>
        </div>
        <p class="form-text">Show operation completion and error notifications</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.settings-group {
  padding: var(--space-sm) 0;
}
.form-group {
  margin-bottom: var(--space-md);
}
.form-label {
  display: block;
  font-weight: 600;
  margin-bottom: var(--space-xs);
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
}
.form-text {
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  margin-top: var(--space-xs);
}
.form-check {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
}
.form-check-label {
  cursor: pointer;
}
</style>
