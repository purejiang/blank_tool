<template>
  <div class="page other-tools-page">
    <div class="page-content responsive-two-column">
      <!-- 占位：后续添加其他工具 -->
      <div class="left-panel">
        <div class="section responsive-section">
          <h2><span class="section-icon">🔧</span>示例工具</h2>
          <div class="empty-state">
            <p>更多工具开发中...</p>
          </div>
        </div>
      </div>
      
      <div class="right-panel">
      </div>
    </div>
  </div>
</template>

<script>
export default {
  name: 'OtherToolsPage'
}
</script>

<style scoped>
.empty-state {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 200px;
  color: var(--text-secondary);
}
</style>