<template>
  <div class="page device-page">
    <div class="page-content responsive-two-column">
      <div class="left-panel">
        <DeviceManager />
        <DeviceActions />
      </div>
      <div class="right-panel">
        <AppManager />
        <LogcatViewer />
      </div>
    </div>
  </div>
</template>

<script>
import { onMounted, ref } from 'vue'
import serviceManager from '@/services/ServiceManager'

import DeviceManager from '@components/DeviceManager.vue'
import DeviceActions from '@components/DeviceActions.vue'
import AppManager from '@components/AppManager.vue'
import LogcatViewer from '@components/LogcatViewer.vue'

export default {
  name: 'DevicePage',
  components: {
    DeviceManager,
    DeviceActions,
    AppManager,
    LogcatViewer
  }
}
  onMounted(async () => {
      console.log('DevicePage 组件已挂载')
      try {
        deviceServiceRef.value = await serviceManager.getService('device')
      } catch {}
    })
</script>

<style scoped>

</style>