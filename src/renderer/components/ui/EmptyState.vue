<template>
  <!-- 空态：虚线 art 盒 + 标题 + 说明 + 下一步动作。空态必须给可点击的下一步。 -->
  <div class="app-empty">
    <div v-if="$slots.icon" class="app-empty-art"><slot name="icon" /></div>
    <h3>{{ title }}</h3>
    <p v-if="description">{{ description }}</p>
    <div v-if="$slots.actions" class="app-empty-acts"><slot name="actions" /></div>
  </div>
</template>

<script setup lang="ts">
defineProps<{ title: string; description?: string }>()
</script>

<style scoped>
.app-empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 40px 20px;
  text-align: center;
  color: var(--text-muted);
}

.app-empty-art {
  width: 88px;
  height: 88px;
  margin-bottom: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-muted);
  background: var(--surface-alt);
  border: 1.5px dashed var(--border);
  border-radius: 20px;
}

.app-empty h3 {
  margin: 0;
  font-size: 14.5px;
  font-weight: 600;
  color: var(--text-secondary);
}

.app-empty p {
  margin: 0;
  max-width: 420px;
  font-size: 12.5px;
  line-height: 1.6;
}

.app-empty-acts {
  display: flex;
  gap: 8px;
  margin-top: 8px;
  flex-wrap: wrap;
  justify-content: center;
}
</style>
