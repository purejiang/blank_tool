<template>
  <!--
    统一的「路径行」：设置页里所有路径设置项都走这一个组件，避免每处各写一套
    （有的用只读 n-input + 「浏览」按钮，有的用纯文本，视觉和交互都不一致）。

    统一规则：
      - 支持修改的路径（editable）→ 路径后面跟一个铅笔图标按钮，点击 emit edit
      - 不支持修改的路径 → 只展示路径文本，不出现任何按钮
      - 已覆盖默认值时 → 额外给出「重置」

    可变内容走插槽：badge（版本/状态徽标，跟在标题后）、value（替换路径文本，
    用于不是单条路径的场合，如设备列表）、actions（额外动作，排在重置/修改之前）。
  -->
  <div class="path-row">
    <div class="path-row-main">
      <div class="path-row-head">
        <span class="path-row-label" :class="{ 'is-mono': labelMono }">
          <slot name="label">{{ label }}</slot>
        </span>
        <slot name="badge" />
      </div>
      <div class="path-row-value">
        <slot name="value">
          <span
            class="path-row-text"
            :class="{ 'is-empty': !path }"
            :title="path || undefined"
          >{{ path || placeholder }}</span>
        </slot>
        <!-- 存在性标记：紧跟在路径文本之后，**不进右侧操作区**（不跟编辑按钮混在
             一起）。unknown（undefined / null）时不渲染，避免探测失败时误报。 -->
        <n-tooltip v-if="typeof exists === 'boolean'" trigger="hover" placement="top">
          <template #trigger>
            <n-icon
              class="path-row-exists"
              :class="exists ? 'is-ok' : 'is-missing'"
              size="14"
            >
              <Check v-if="exists" /><AlertCircle v-else />
            </n-icon>
          </template>
          {{ exists ? t('settings.pathExists') : t('settings.pathMissing') }}
        </n-tooltip>
      </div>
      <div v-if="hint" class="path-row-hint">{{ hint }}</div>
    </div>

    <div v-if="editable || overridden || $slots.actions" class="path-row-actions">
      <slot name="actions" />
      <n-button
        v-if="overridden"
        size="tiny"
        quaternary
        type="warning"
        :loading="resetLoading"
        @click="emit('reset')"
      >
        {{ resetText || t('settings.reset') }}
      </n-button>
      <IconButton
        v-if="editable"
        :icon="Pencil"
        :label="editTitle || t('settings.changePath')"
        size="tiny"
        quaternary
        :loading="editing"
        @click="emit('edit')"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { NButton, NIcon, NTooltip } from 'naive-ui'
import { AlertCircle, Check, Pencil } from 'lucide-vue-next'
import IconButton from './IconButton.vue'

/**
 * 注意 `exists` 必须有显式默认值：Vue 对声明了 Boolean 的 prop 会把「未传」
 * 强转成 `false`，那样每一行都会默认显示「路径不存在」。给 `null` 之后未传即
 * 「未知」，才不会误报。
 */
const props = withDefaults(defineProps<{
  /** 行标题（左侧第一行） */
  label?: string
  /** 路径值；为空时显示 placeholder */
  path?: string
  placeholder?: string
  /** 标题下方的说明文字 */
  hint?: string
  /** 该路径是否支持修改：true 才出现铅笔图标 */
  editable?: boolean
  /** 当前值是否是用户自定义（覆盖默认）→ 显示重置 */
  overridden?: boolean
  /** 修改/校验进行中（铅笔按钮转圈） */
  editing?: boolean
  /** 重置进行中 */
  resetLoading?: boolean
  /** 标题使用等宽字体（工具名等） */
  labelMono?: boolean
  /** 铅笔按钮的悬浮提示，默认「修改路径」 */
  editTitle?: string
  /** 重置按钮文案，默认「重置」 */
  resetText?: string
  /**
   * 路径是否存在（探测结果）：true → 路径后的 ✓；false → ！；
   * undefined / null → 未知，不渲染图标。
   */
  exists?: boolean | null
}>(), {
  exists: null,
})

const emit = defineEmits<{ (e: 'edit'): void; (e: 'reset'): void }>()
const { t } = useI18n()
</script>

<style scoped>
.path-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 9px 6px;
  border-radius: 6px;
  transition: background 0.15s ease;
}
.path-row:hover { background: var(--app-storage-bg); }
.path-row-main { flex: 1; min-width: 0; }
.path-row-head { display: flex; align-items: center; gap: 8px; min-width: 0; }
.path-row-label {
  font-size: var(--app-font-size-md);
  font-weight: 600;
  color: var(--app-text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.path-row-label.is-mono { font-family: var(--app-font-mono); }
.path-row-value { margin-top: 3px; min-width: 0; display: flex; align-items: center; gap: 6px; }
.path-row-value > :first-child { min-width: 0; }
.path-row-text {
  display: block;
  flex: 1;
  min-width: 0;
  font-family: var(--app-font-mono);
  font-size: var(--app-font-size-sm);
  color: var(--app-text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  /* 只读路径也要能选中复制——截断只是视觉上的，DOM 里仍是完整路径 */
  user-select: text;
}
.path-row-text.is-empty { color: var(--app-text-dim); font-style: italic; }
/* 存在性标记：跟在路径后面，不参与操作区 */
.path-row-exists { flex: none; }
.path-row-exists.is-ok { color: var(--app-green); }
.path-row-exists.is-missing { color: var(--app-yellow); }
.path-row-hint {
  font-size: var(--app-font-size-sm);
  color: var(--app-text-muted);
  margin-top: 4px;
}
.path-row-actions { display: flex; align-items: center; gap: 4px; flex: none; }
</style>
