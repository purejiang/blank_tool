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
</script>

<style scoped>
/* Page-specific styles */
</style>