<template>
  <AppModal
    :show="show"
    :title="t('automation.shotPickTitle')"
    :width="520"
    @update:show="emit('update:show', $event)"
  >
    <p class="app-muted">{{ t('automation.shotPickHint') }}</p>

    <!-- capturing: spinner instead of looking frozen -->
    <div v-if="capturing" class="capturing">
      <n-spin size="medium" />
      <p class="app-muted capturing-hint">{{ t('automation.shotPickLoading') }}</p>
    </div>

    <template v-else>
      <!-- capture / decode failure: show the backend error + retry -->
      <div v-if="errorMsg" class="shot-error">
        <p class="shot-error-msg">{{ t('automation.shotPickFailed', { msg: errorMsg }) }}</p>
        <n-button size="tiny" type="info" secondary @click="capture">{{ t('automation.reshoot') }}</n-button>
      </div>

      <!-- unusable capture: rotation unknown or the image size does not
           match what the (known) rotation implies → the coordinate math
           would be wrong, so refuse and let the user re-capture -->
      <div v-else-if="shotSize && panelSize && !safe" class="rot-warning">
        <p class="rot-warning-msg">{{ t('automation.shotPickRotated') }}</p>
        <p class="app-muted rot-sizes">{{ t('automation.shotPickSizes', { shot: sizeText(shotSize), panel: sizeText(panelSize) }) }}</p>
        <n-button size="tiny" type="info" secondary @click="capture">{{ t('automation.reshoot') }}</n-button>
      </div>

      <n-empty v-else-if="!dataUrl" :description="t('automation.shotPickFailed', { msg: '—' })" size="small" />

      <div v-else class="shot-wrap">
        <img
          :src="dataUrl"
          class="shot-img"
          :alt="t('automation.shotPickTitle')"
          @click="onPick"
        />
      </div>
    </template>
  </AppModal>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, NEmpty, NSpin } from 'naive-ui'
import AppModal from '@components/common/AppModal.vue'
import { mapClickToPanel, displayToPanel, captureMatchesRotation, isPickSafe, parseSize, clampPanel, type PickDisplay } from './shotCoords'

const props = defineProps<{
  show: boolean
  deviceId: string
}>()

const emit = defineEmits<{
  (e: 'update:show', v: boolean): void
  (e: 'apply', coord: { x: number; y: number }): void
}>()

const { t } = useI18n()

const capturing = ref(false)
const dataUrl = ref('')
const shotSize = ref<{ w: number; h: number } | null>(null)
const panelSize = ref<{ w: number; h: number } | null>(null)
/** current surface rotation 0..3 from device.display_transform; null = unavailable */
const rotation = ref<number | null>(null)
const errorMsg = ref('')

const safe = computed(() => {
  const s = shotSize.value
  const p = panelSize.value
  if (!s || !p) return false
  if (rotation.value === null) return isPickSafe(s.w, s.h, p.w, p.h)
  return captureMatchesRotation(s.w, s.h, rotation.value, p.w, p.h)
})

function sizeText(s: { w: number; h: number }): string {
  return `${s.w}x${s.h}`
}

// Screenshot → data URL (dev renderer origin is http://localhost:3000, so a
// file:// <img> src is blocked by Chromium — same reason RunPanel uses this).
// Decode via Image() to learn naturalWidth/Height BEFORE deciding whether
// picking is safe, so the warning state can replace the image entirely.
watch(() => props.show, (v) => {
  if (v) void capture()
})

async function capture() {
  capturing.value = true
  errorMsg.value = ''
  dataUrl.value = ''
  shotSize.value = null
  panelSize.value = null
  rotation.value = null
  try {
    if (!props.deviceId) {
      errorMsg.value = t('automation.noDevice')
      return
    }
    const api = window.electronAPI
    // display_transform reads the same SurfaceOrientation the replay path
    // uses, so the picked coord can never drift from what the run taps.
    // A failed/zeros transform just degrades to the dimension-only fallback.
    const [shotRes, dtRes] = await Promise.all([
      api.callBackendAPI('device.screenshot', { device_id: props.deviceId }),
      api.callBackendAPI('device.display_transform', { device_id: props.deviceId }).catch(() => null),
    ])
    if (!shotRes || !shotRes.success || !shotRes.file_path) {
      errorMsg.value = shotRes.error || '—'
      return
    }
    let ps: { w: number; h: number } | null = null
    if (dtRes && dtRes.success && dtRes.width > 0 && dtRes.height > 0) {
      ps = { w: dtRes.width, h: dtRes.height }
      rotation.value = dtRes.rotation
    } else {
      const infoRes = await api.callBackendAPI('device.get_device_info', { device_id: props.deviceId })
      ps = parseSize(String(infoRes?.screenResolution || ''))
      if (!ps) {
        errorMsg.value = String(infoRes?.screenResolution || '—')
        return
      }
    }
    const imgRes = await api.readImageAsDataURL(shotRes.file_path)
    if (!imgRes || !imgRes.success || !imgRes.dataUrl) {
      errorMsg.value = imgRes?.error || 'unknown'
      return
    }
    const size = await imageSize(imgRes.dataUrl)
    panelSize.value = ps
    shotSize.value = size
    dataUrl.value = imgRes.dataUrl
  } catch (e: any) {
    errorMsg.value = e?.message || String(e)
  } finally {
    capturing.value = false
  }
}

function imageSize(url: string): Promise<{ w: number; h: number }> {
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.onload = () => resolve({ w: img.naturalWidth, h: img.naturalHeight })
    img.onerror = () => reject(new Error('image decode failed'))
    img.src = url
  })
}

function onPick(e: MouseEvent) {
  if (!safe.value) return
  const s = shotSize.value!
  const p = panelSize.value!
  const el = e.currentTarget as HTMLElement
  const rect = el.getBoundingClientRect()
  // Step 1: click → capture pixels (clamped to the capture bounds).
  const disp = mapClickToPanel({
    clickX: e.clientX,
    clickY: e.clientY,
    rectLeft: rect.left,
    rectTop: rect.top,
    rectWidth: rect.width,
    rectHeight: rect.height,
    panelW: s.w,
    panelH: s.h,
  } satisfies PickDisplay)
  if (rotation.value === null) {
    // Fallback: isPickSafe guarantees capture == panel, so capture px are panel px.
    emit('apply', disp)
    return
  }
  // Step 2: invert the replay's rotate_to_display, then clamp — the rotation
  // can push a boundary display point 1 px past the panel edge.
  const panel = displayToPanel(disp, rotation.value, p.w, p.h)
  emit('apply', clampPanel(panel.x, panel.y, p.w, p.h))
}
</script>

<style scoped>
.capturing { display: flex; flex-direction: column; align-items: center; gap: 10px; padding: 40px 0; }
.capturing-hint { margin: 0; }
.shot-error { display: flex; flex-direction: column; align-items: center; gap: 10px; padding: 24px 0; }
.shot-error-msg { margin: 0; font-size: var(--app-font-size-sm); color: var(--app-red); word-break: break-all; text-align: center; }
.rot-warning { display: flex; flex-direction: column; align-items: center; gap: 10px; padding: 24px 12px; border: 1px solid var(--app-yellow); border-radius: 8px; }
.rot-warning-msg { margin: 0; font-size: var(--app-font-size-sm); color: var(--app-yellow); text-align: center; }
.rot-sizes { margin: 0; font-variant-numeric: tabular-nums; }
.shot-wrap { max-height: 60vh; overflow: auto; scrollbar-gutter: stable; overscroll-behavior: contain; }
.shot-img { display: block; max-width: 100%; height: auto; cursor: crosshair; }
</style>
