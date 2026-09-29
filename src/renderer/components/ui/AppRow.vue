<template>
  <!-- 列表行：surface 底 + 1px 描边 + 控件圆角，左侧自由内容 + 右侧动作组。
       替代 `.tl-row` / `.rl-row` / `.env-row` / `.plugin-row` —— 四者骨架相同，
       内距却漂成 10/12、8/12、10/14、10/14 四种，这里统一取 --row-pad-*。

       可点击的行请传 `interactive`（出 hover 反馈），行内需要真正的键盘可访问性时
       用 `as="button"`，不要在 div 上挂 @click。 -->
  <component :is="as" class="app-row" :class="{ 'app-row--interactive': interactive }">
    <div class="app-row-main"><slot /></div>
    <div v-if="$slots.actions" class="app-actions"><slot name="actions" /></div>
  </component>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    /** 语义容器：纯展示用 div；整行可点击时传 button/a 以获得键盘可达性 */
    as?: string
    interactive?: boolean
  }>(),
  { as: 'div' },
)
</script>

<style scoped>
.app-row {
  display: flex;
  gap: var(--gap-md);
  align-items: center;
  min-width: 0;
  padding: var(--row-pad-y) var(--row-pad-x);
  background: var(--surface);
  border: var(--hairline);
  border-radius: var(--radius-control);
  transition: border-color var(--duration-fast) var(--ease-standard);
}

.app-row--interactive {
  cursor: pointer;
}

.app-row--interactive:hover {
  border-color: var(--primary-soft-border);
}

.app-row-main {
  flex: 1 1 auto;
  min-width: 0;
}
</style>
