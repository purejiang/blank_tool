<template>
  <n-modal
    :show="visible"
    preset="card"
    :title="t('quit.title')"
    :mask-closable="false"
    :closable="false"
    style="width: 420px"
    @after-leave="cleanup"
  >
    <p class="qd-message">{{ t('quit.message') }}</p>
    <p class="qd-detail">{{ t('quit.detail') }}</p>
    <template #footer>
      <div class="qd-actions">
        <n-button @click="respond('cancel')">{{ t('quit.cancel') }}</n-button>
        <n-button type="default" secondary @click="respond('minimize')">{{ t('quit.minimize') }}</n-button>
        <n-button type="error" @click="respond('quit')">{{ t('quit.quit') }}</n-button>
      </div>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { NModal, NButton } from 'naive-ui'

const { t } = useI18n()
const visible = ref(false)
let cleanup: () => void

onMounted(() => {
  const api = (window as any).electronAPI
  if (api?.onQuitDialog) {
    cleanup = api.onQuitDialog(() => { visible.value = true })
  }
})

onUnmounted(() => {
  if (cleanup) cleanup()
})

function respond(action: string) {
  visible.value = false
  const api = (window as any).electronAPI
  api?.respondQuitDialog?.(action)
}
</script>

<style scoped>
.qd-message {
  font-size: 15px;
  color: var(--app-text-primary);
  margin: 0 0 6px;
}
.qd-detail {
  font-size: 13px;
  color: var(--app-text-muted);
  margin: 0;
}
.qd-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
