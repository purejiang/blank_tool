<script setup lang="ts">
defineProps<{
  hasSelection: boolean
  isMonitoring: boolean
  connectionText: string
  connectionConnected: boolean
}>()

const emit = defineEmits<{
  refresh: []
  toggleMonitoring: []
}>()
</script>

<template>
  <div class="action-bar">
    <div class="connection-status">
      <span class="status-indicator" :class="connectionConnected ? 'status-connected' : 'status-disconnected'"></span>
      <span>{{ connectionText }}</span>
    </div>
    <div class="action-right">
      <label class="toggle-label" title="自动监听">
        <span class="toggle-desc">Auto</span>
        <label class="toggle-switch">
          <input type="checkbox" :checked="isMonitoring" @change="emit('toggleMonitoring')">
          <span class="toggle-slider"></span>
        </label>
      </label>
      <button class="btn" @click="emit('refresh')" title="Refresh device list">Refresh</button>
    </div>
  </div>
</template>

<style scoped>
.action-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--space-sm) 0 var(--space-sm) 0;
}
.connection-status {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
}
.status-indicator {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  display: inline-block;
}
.status-connected { background: var(--color-success); }
.status-disconnected { background: var(--color-error); }
.toggle-desc {
  font-size: var(--font-size-sm);
  margin-right: var(--space-xs);
  color: var(--color-text-secondary);
}
.toggle-label {
  display: flex;
  align-items: center;
  cursor: pointer;
  gap: 0;
}
/* Inherited toggle style */
.toggle-switch {
  position: relative;
  display: inline-block;
  width: 36px;
  height: 20px;
}
.toggle-switch input {
  opacity: 0;
  width: 0;
  height: 0;
}
.toggle-slider {
  position: absolute;
  cursor: pointer;
  top: 0; left: 0; right: 0; bottom: 0;
  background-color: #ccc;
  transition: .3s;
  border-radius: 20px;
}
.toggle-slider:before {
  position: absolute;
  content: "";
  height: 14px;
  width: 14px;
  left: 3px;
  bottom: 3px;
  background-color: white;
  transition: .3s;
  border-radius: 50%;
}
input:checked + .toggle-slider { background-color: var(--color-primary); }
input:checked + .toggle-slider:before { transform: translateX(16px); }
.action-right {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
}
.btn {
  padding: var(--space-xs) var(--space-md);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-bg-card);
  cursor: pointer;
  font-size: var(--font-size-base);
}
.btn:hover {
  background: var(--color-primary);
  color: white;
  border-color: var(--color-primary);
}
</style>
