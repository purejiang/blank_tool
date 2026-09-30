<template>
  <!-- 端口类型徽标：把"这个参数是什么类型"从控件形态里显式说出来。
       参数面板、输出列表、引用候选、运行入参共用一份，类型口径只在这里定义。 -->
  <span
    class="ptb"
    :class="[`ptb--${kind}`, { 'ptb--compact': compact }]"
    :title="title"
    data-test="port-type-badge"
  >
    {{ label }}
    <span v-if="subtypeText" class="ptb-sub">{{ subtypeText }}</span>
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import { portJsonToTypeKey, type PortTypeKey } from './ioAuthoring'

/**
 * Type badge for a port. Accepts the loose port shape the editor holds
 * (bare base strings included) and reuses the shared widget-type mapping, so
 * the badge can never disagree with the control PortInput renders.
 */
const props = defineProps<{
  /** Port type: bare base name or the wire `{base, subtype}` object. */
  type?: string | { base?: string; subtype?: string | null } | null
  /** Select-like options (single_select / multi_select detection). */
  options?: unknown
  /** Select-like multi flag. */
  multi?: unknown
  /** Explicit subtype override (when `type` is a bare base string). */
  subtype?: string | null
  /** Dense variant for list rows. */
  compact?: boolean
}>()

const { t } = useI18n()

const base = computed(() => {
  const type = props.type
  if (typeof type === 'string') return type.toLowerCase()
  if (type && typeof type === 'object' && typeof type.base === 'string') return type.base.toLowerCase()
  return ''
})

const subtypeText = computed(() => {
  const explicit = props.subtype
  if (typeof explicit === 'string' && explicit) return explicit
  const type = props.type
  if (type && typeof type === 'object' && typeof type.subtype === 'string' && type.subtype) {
    return type.subtype
  }
  return ''
})

/** Widget kind — same reverse mapping PortInput uses (`portJsonToTypeKey`). */
const kind = computed<PortTypeKey>(() =>
  portJsonToTypeKey({
    name: '',
    type: { base: base.value },
    options: Array.isArray(props.options) ? (props.options as string[]) : [],
    multi: props.multi === true,
  }),
)

const label = computed(() => t(`workflow.editor.io.types.${kind.value}`))
const title = computed(() =>
  subtypeText.value ? `${label.value} · ${subtypeText.value}` : label.value,
)
</script>

<style scoped>
.ptb {
  display: inline-flex;
  flex: none;
  gap: 3px;
  align-items: center;
  padding: 0 5px;
  font-size: 10px;
  line-height: 16px;
  color: var(--ptb-color, var(--app-text-muted));
  white-space: nowrap;
  background: var(--app-storage-bg);
  border: 1px solid var(--app-card-border);
  border-radius: var(--radius-chip);
}

.ptb--compact {
  padding: 0 4px;
  font-size: 10px;
  line-height: 14px;
}

.ptb-sub {
  color: var(--app-text-dim);
}

/* 类型色：与节点调色板的分类色（--tn-accent 一族）保持同一套语义 */
.ptb--file,
.ptb--directory {
  --ptb-color: var(--app-blue);
}

.ptb--text,
.ptb--single_select,
.ptb--multi_select {
  --ptb-color: var(--app-green);
}

.ptb--number,
.ptb--boolean {
  --ptb-color: var(--app-orange, var(--app-yellow));
}

.ptb--json {
  --ptb-color: var(--app-purple, var(--app-text-secondary));
}
</style>
