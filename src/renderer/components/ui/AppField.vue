<template>
  <!-- 表单字段容器：label + 必填星 + 帮助文本 + 错误提示。
       控件本身用 Naive（Input / Select / Switch…），它们的取值、边框、焦点环
       已在 theme/overrides.ts 里对齐 tokens.css，所以这里只管排版与可访问性。

       替代 TaskEditorPage 的 `.te-field/.te-label/.te-req/.te-help/.te-error`
       （同一文件里 6 遍）与 NodeConfigPanel 的 `.npc-field/.npc-field-label/
       .npc-hint/.npc-error`（4 遍）。

       ⚠️ 边界：**在 `n-form` 里请继续用 `n-form-item`**。它带 validation-status /
       feedback 的联动与 label 关联，换成 AppField 会丢掉校验展示。AppField 只服务
       「不在 form 里的独立字段」与「需要完全自定义排版的字段」。 -->
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
  gap: var(--sp-4);
  min-width: 0;
}

.app-field-label {
  display: flex;
  align-items: center;
  gap: var(--sp-4);
  font-size: var(--fs-label);
  color: var(--text-secondary);
}

/* 必填星统一用语义危险色（此前 TaskEditorPage 用的是警告色黄色，属漂移） */
.app-field-req {
  color: var(--danger-text);
}

.app-field-control {
  min-width: 0;
}

.app-field-help {
  font-size: var(--fs-meta);
  line-height: 1.45;
  color: var(--text-dim);
}

.app-field-error {
  font-size: var(--fs-11);
  line-height: 1.45;
  color: var(--danger-text);
}
</style>
