<template>
  <div class="loading-screen">
    <div class="loading-container">
      <div class="loading-brand">
        <h1 class="loading-title">{{ $t('app.title') }}</h1>
        <p class="loading-subtitle">{{ $t('app.subtitle') }}</p>
      </div>
      <n-progress
        type="line"
        :percentage="progress"
        :height="6"
        :border-radius="3"
        color="var(--success-text)"
        rail-color="var(--border)"
      />
      <div class="loading-info">
        <p class="loading-step">{{ step }}</p>
        <p class="loading-timer">{{ time }}s</p>
      </div>
      <div v-if="error" class="loading-error-card">
        <AppNotice tone="danger" :title="error">
          <template #action>
            <AppButton
              v-if="retryCount < maxRetries"
              variant="danger"
              size="small"
              @click="emit('retry')"
            >
              {{ $t('app.retry') }} ({{ retryCount }}/{{ maxRetries }})
            </AppButton>
          </template>
        </AppNotice>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import AppButton from '@components/ui/AppButton.vue'
import AppNotice from '@components/ui/AppNotice.vue'

defineProps<{
  progress: number
  step: string
  time: string
  error: string
  retryCount: number
  maxRetries: number
}>()

const emit = defineEmits<{
  retry: []
}>()
</script>

<style scoped>
.loading-screen {
  position: fixed;
  inset: 0;
  background: var(--app-body-bg);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
}
.loading-container {
  width: 360px;
  text-align: center;
}
.loading-brand {
  margin-bottom: 32px;
}
.loading-title {
  font-family: var(--font-family-base);
  font-size: 24px;
  font-weight: 700;
  color: var(--app-text-primary);
  margin: 12px 0 0;
}
.loading-subtitle {
  font-family: var(--font-family-base);
  font-size: 13px;
  color: var(--app-text-muted);
  margin: 4px 0 0;
}
.loading-info {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 12px;
}
.loading-step {
  font-size: 13px;
  color: var(--app-text-muted);
  margin: 0;
}
.loading-timer {
  font-size: 12px;
  color: var(--app-text-muted);
  margin: 0;
  font-variant-numeric: tabular-nums;
}
.loading-error-card {
  margin-top: 24px;
}
</style>
