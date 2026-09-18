<template>
  <!--
    统一的弹窗外壳：所有业务弹窗都走这一个组件，布局契约靠组件强制，而不是靠各页
    自己记得：

      标题在左上角（n-card 头部左对齐）
      关闭 X 在右上角（n-card 自带，组件不再自绘第二个 X）
      内容在中间
      功能按钮在右下角（#footer 插槽，**只在真的有功能按钮时才用**）

    约定：#footer 里**不要**再放「关闭」按钮 —— 右上角的 X 已经承担了关闭，
    右下角再来一个就是同一件事画两遍。footer 只留给真正的动作（刷新、确定…）；
    一个纯展示性的弹窗（如运行配置）没有 footer。

    历史问题：录制弹窗既自绘了标题、又自绘了 X，于是页面上出现两个关闭按钮；运行
    记录弹窗同时有 n-card 标题和组件内标题，出现两个标题。把外壳收敛到这里之后，
    各业务组件只负责内容与功能按钮。
  -->
  <n-modal
    :show="show"
    preset="card"
    :title="title"
    :style="modalStyle"
    :closable="closable"
    :mask-closable="maskClosable"
    @update:show="emit('update:show', $event)"
  >
    <slot />

    <template v-if="$slots.footer" #footer>
      <div class="app-modal-footer">
        <slot name="footer" />
      </div>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { NModal } from 'naive-ui'

const props = withDefaults(defineProps<{
  show: boolean
  /** 标题（左上角）。空字符串表示不显示标题栏标题。 */
  title?: string
  /** 宽度：数字按 px 处理，字符串原样使用 */
  width?: string | number
  closable?: boolean
  maskClosable?: boolean
}>(), {
  title: '',
  width: 520,
  closable: true,
  maskClosable: true,
})

const emit = defineEmits<{ (e: 'update:show', v: boolean): void }>()

const modalStyle = computed(() => ({
  width: typeof props.width === 'number' ? `${props.width}px` : props.width,
}))
</script>

<style scoped>
/* 功能按钮统一右下角：组件只给容器，按钮由使用方通过 #footer 传入 */
.app-modal-footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  width: 100%;
}
</style>
