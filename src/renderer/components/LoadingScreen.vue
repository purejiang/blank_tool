<template>
  <div class="loading-screen">
    <div class="loading-container">
      <div class="loading-brand">
        <img src="@assets/images/logo.svg" class="loading-logo" alt="Blank Tool" />
        <h1 class="loading-title">{{ $t('app.title') }}</h1>
        <p class="loading-subtitle">{{ $t('app.subtitle') }}</p>
      </div>
      <n-progress
        type="line"
        :percentage="progress"
        :height="6"
        :border-radius="3"
        color="#22C55E"
        rail-color="rgba(255,255,255,0.1)"
      />
      <div class="loading-info">
        <p class="loading-step">{{ step }}</p>
        <p class="loading-timer">{{ time }}s</p>
      </div>
      <div v-if="error" class="loading-error-card">
        <n-alert type="error" :title="error">
          <template #footer>
            <n-button v-if="retryCount < maxRetries" @click="emit('retry')" type="error" size="small">
              {{ $t('app.retry') }} ({{ retryCount }}/{{ maxRetries }})
            </n-button>
          </template>
        </n-alert>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
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
.loading-logo {
  width: 48px;
  height: 48px;
  display: block;
  margin: 0 auto;
}
.loading-title {
  font-family: Inter, sans-serif;
  font-size: 24px;
  font-weight: 700;
  color: var(--app-text-primary);
  margin: 12px 0 0;
}
.loading-subtitle {
  font-family: Inter, sans-serif;
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
