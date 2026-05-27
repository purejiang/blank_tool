<script setup lang="ts">
import { ref } from 'vue'
import GeneralSettings from '@components/settings/GeneralSettings.vue'
import PathSettings from '@components/settings/PathSettings.vue'
import AdvancedSettings from '@components/settings/AdvancedSettings.vue'

const activeTab = ref('general')
const tabs = [
  { key: 'general', label: 'General' },
  { key: 'paths', label: 'Paths' },
  { key: 'advanced', label: 'Advanced' },
]
</script>

<template>
  <div class="page settings-page">
    <nav class="settings-tabs">
      <button
        v-for="tab in tabs"
        :key="tab.key"
        :class="{ active: activeTab === tab.key }"
        @click="activeTab = tab.key"
      >{{ tab.label }}</button>
    </nav>
    <div class="page-content">
      <GeneralSettings v-if="activeTab === 'general'" />
      <PathSettings v-if="activeTab === 'paths'" />
      <AdvancedSettings v-if="activeTab === 'advanced'" />
    </div>
  </div>
</template>

<style scoped>
.settings-tabs {
  display: flex;
  gap: var(--space-xs);
  padding: var(--space-md) var(--space-lg) 0;
  border-bottom: 2px solid var(--color-border);
  margin-bottom: var(--space-lg);
}
.settings-tabs button {
  padding: var(--space-sm) var(--space-lg);
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  margin-bottom: -2px;
  cursor: pointer;
  font-size: var(--font-size-base);
  color: var(--color-text-secondary);
  transition: all 0.2s;
}
.settings-tabs button:hover {
  color: var(--color-text);
}
.settings-tabs button.active {
  color: var(--color-primary);
  border-bottom-color: var(--color-primary);
  font-weight: 600;
}
.page-content {
  padding: 0 var(--space-lg) var(--space-lg);
}
</style>
