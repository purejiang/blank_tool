<script setup lang="ts">
interface Device {
  id: string
  name?: string
  status?: string
}

defineProps<{
  devices: Device[]
  selectedId: string
}>()

const emit = defineEmits<{
  select: [id: string]
}>()
</script>

<template>
  <div class="device-list">
    <div
      v-for="device in devices"
      :key="device.id"
      class="device-item"
      :class="{ active: device.id === selectedId }"
      @click="emit('select', device.id)"
    >
      <span class="device-name">{{ device.name || device.id }}</span>
      <span class="device-id">{{ device.id }}</span>
      <span class="device-status" :class="device.status">{{ device.status || 'unknown' }}</span>
    </div>
    <div v-if="devices.length === 0" class="empty-state">
      No devices connected
    </div>
  </div>
</template>

<style scoped>
.device-list { display: flex; flex-direction: column; gap: var(--space-xs); }
.device-item { padding: var(--space-sm) var(--space-md); cursor: pointer; border-radius: var(--radius-sm); border: 1px solid var(--color-border); transition: background 0.2s; }
.device-item.active { background: var(--color-primary); color: white; border-color: var(--color-primary); }
.device-item:hover:not(.active) { background: var(--color-bg); }
.device-name { font-weight: 600; }
.device-id { font-size: var(--font-size-sm); color: var(--color-text-secondary); margin-left: var(--space-sm); }
.device-status.online { color: var(--color-success); }
.device-status.offline { color: var(--color-error); }
.device-item.active .device-id,
.device-item.active .device-status { color: rgba(255,255,255,0.8); }
.empty-state { padding: var(--space-lg); text-align: center; color: var(--color-text-secondary); }
</style>
