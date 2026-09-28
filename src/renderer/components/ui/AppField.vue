<template>
  <!-- 表单字段容器：label + 必填星 + 帮助文本 + 错误提示。
       控件本身用 Naive（Input / Select / Switch…），它们的取值、边框、焦点环
       已在 theme/overrides.ts 里对齐 tokens.css，所以这里只管排版与可访问性。 -->
  <div class="app-field" :class="{ 'app-field--error': !!error }">
    <label :for="controlId" class="app-field-label">
      {{ label }}
      <span v-if="required" class="app-field-req" aria-hidden="true">*</span>
      <span v-if="required" class="sr-only">{{ t('common.required') }}</span>
    </label>
    <div class="app-field-control">
      <slot :id="controlId" :invalid="!!error" />
    </div>
    <div v-if="error" class="app-field-error" role="alert">{{ error }}</div>
    <div v-else-if="help" class="app-field-help">{{ help }}</div>
  </div>
</template>

<script setup lang="ts">
import { computed, useId } from 'vue'
import { useI18n } from 'vue-i18n'

const props = defineProps<{
  label: string
  required?: boolean
  help?: string
  error?: string | null
  /** 需要与控件 id 关联时传入；缺省自动生成，保证 label 可点击聚焦 */
  id?: string
}>()

const { t } = useI18n()
const autoId = useId()
const controlId = computed(() => props.id ?? `field-${autoId}`)
</script>

<style scoped>
.app-field {
  display: flex;
  flex-direction: column;
  gap: 5px;
  min-width: 0;
}

.app-field-label {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--text-secondary);
}

.app-field-req {
  color: var(--danger-text);
}

.app-field-control {
  min-width: 0;
}

.app-field-help {
  font-size: 11px;
  color: var(--text-muted);
}

.app-field-error {
  font-size: 11.5px;
  color: var(--danger-text);
}
</style>
