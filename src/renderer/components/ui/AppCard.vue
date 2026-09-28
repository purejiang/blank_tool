<template>
  <!-- 卡片：surface 底 + border 边 + 14px 圆角 + 设计给定阴影。
       hoverable 时 hover 边框转 primary-soft-border 并轻微上浮（键盘聚焦同样生效）。 -->
  <component
    :is="as"
    class="app-card"
    :class="{ 'app-card--hoverable': hoverable, 'app-card--flat': flat }"
  >
    <div v-if="$slots.header || title" class="app-card-hd">
      <slot name="header">
        <h3>{{ title }}</h3>
      </slot>
      <div v-if="$slots.actions" class="app-card-actions"><slot name="actions" /></div>
    </div>
    <div class="app-card-bd" :class="{ 'app-card-bd--flush': flushBody }">
      <slot />
    </div>
    <div v-if="$slots.footer" class="app-card-ft"><slot name="footer" /></div>
  </component>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    /** 语义容器：卡片通常是 div，可点击时传 button/a 以获得键盘可达性 */
    as?: string
    title?: string
    hoverable?: boolean
    /** 去掉阴影（嵌套卡片用） */
    flat?: boolean
    /** 去掉 body 内边距（列表型内容自行控制） */
    flushBody?: boolean
  }>(),
  { as: 'div' },
)
</script>

<style scoped>
.app-card {
  display: flex;
  flex-direction: column;
  min-width: 0;
  text-align: left;
  color: var(--text);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  box-shadow: var(--shadow-card);
  transition: border-color 0.15s ease, box-shadow 0.15s ease, transform 0.15s ease;
}

.app-card--flat {
  box-shadow: none;
}

.app-card--hoverable {
  cursor: pointer;
}

.app-card--hoverable:hover,
.app-card--hoverable:focus-visible {
  border-color: var(--primary-soft-border);
  box-shadow: var(--shadow-lift);
  transform: translateY(-1px);
}

.app-card-hd {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
}

.app-card-hd h3 {
  margin: 0;
  font-size: 13.5px;
  font-weight: 600;
  color: var(--text);
}

.app-card-actions {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 6px;
}

.app-card-bd {
  padding: 16px;
  min-width: 0;
}

.app-card-bd--flush {
  padding: 0;
}

.app-card-ft {
  padding: 12px 16px;
  border-top: 1px solid var(--border);
  display: flex;
  align-items: center;
  gap: 8px;
}
</style>
