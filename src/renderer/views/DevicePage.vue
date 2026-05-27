<template>
  <div class="device-page">
    <div class="page-content">
      <div class="left-panel">
        <DeviceManager />
        <DeviceActions />
      </div>
      <div class="right-panel">
        <AppManager />
        <!-- LogcatViewer removed: DeviceManager has a built-in logcat viewer -->
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import serviceManager from '@services/ServiceManager'

import DeviceManager from '@components/DeviceManager.vue'
import DeviceActions from '@components/DeviceActions.vue'
import AppManager from '@components/AppManager.vue'

const deviceServiceRef = ref<any>(null)

onMounted(async () => {
  console.log('DevicePage component mounted')
  try {
    deviceServiceRef.value = await serviceManager.getService('device')
  } catch {}
})
</script>

<style scoped>
.device-page {
  max-width: 1400px;
  margin: 0 auto;
}
.page-content {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}
.left-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.right-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

@media (max-width: 1100px) {
  .page-content {
    grid-template-columns: 1fr;
  }
}
</style>
