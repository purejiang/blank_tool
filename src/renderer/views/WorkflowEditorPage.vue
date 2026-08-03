<template>
  <div class="workflow-editor-page">
    <!-- Left panel: tool palette (populated in todo 34) -->
    <aside class="we-panel we-palette">
      <div class="we-panel-header">Tool Palette</div>
      <div class="we-placeholder">Tools will be listed here.</div>
    </aside>

    <!-- Center: vue-flow canvas -->
    <main class="we-canvas">
      <VueFlow :min-zoom="0.2" :max-zoom="4">
        <Background />
        <Controls />
        <MiniMap />
      </VueFlow>
      <div v-if="nodes.length === 0" class="we-empty-hint">
        Empty workflow — add nodes to get started
      </div>
    </main>

    <!-- Right panel: node config (todo 36, hidden initially) -->
    <aside v-if="showConfigPanel" class="we-panel we-config">
      <div class="we-panel-header">Node Config</div>
      <div class="we-placeholder">Select a node to edit its parameters.</div>
    </aside>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { VueFlow, useVueFlow, type Node, type Edge } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import { MiniMap } from '@vue-flow/minimap'

import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import '@vue-flow/controls/dist/style.css'
import '@vue-flow/minimap/dist/style.css'

// Shared store: created here, injected by the <VueFlow> child component.
// Initial state is empty; todo 34 adds palette drag-and-drop, todo 36 node config.
const { nodes, edges } = useVueFlow({
  nodes: [] as Node[],
  edges: [] as Edge[],
})

// Right panel is hidden until node selection exists (todo 36).
const showConfigPanel = ref(false)
</script>

<style scoped>
.workflow-editor-page {
  display: flex;
  gap: 8px;
  height: 100%;
}

.we-panel {
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  width: 220px;
  background: var(--app-card-bg);
  border: 1px solid var(--app-card-border);
  border-radius: 6px;
}

.we-panel-header {
  padding: 10px 12px;
  border-bottom: 1px solid var(--app-card-border);
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--app-text-secondary);
}

.we-placeholder {
  padding: 12px;
  font-size: 12px;
  color: var(--app-text-muted);
}

.we-canvas {
  position: relative;
  flex: 1;
  min-width: 0;
  overflow: hidden;
  background: var(--app-card-bg);
  border: 1px solid var(--app-card-border);
  border-radius: 6px;
}

.we-empty-hint {
  position: absolute;
  top: 50%;
  left: 50%;
  z-index: 1;
  transform: translate(-50%, -50%);
  pointer-events: none;
  font-size: 13px;
  color: var(--app-text-muted);
}
</style>
