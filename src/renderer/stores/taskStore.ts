import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export interface Task {
  id: number
  source: 'url' | 'local'
  url?: string
  filePath: string
  fileName: string
  operation: 'analyze' | 'install' | 'decompile' | 'recompile' | 'resign'
  operationLabel: string
  status: 'downloading' | 'queued' | 'running' | 'completed' | 'failed'
  progress: number
  progressLabel: string
  result: string
  outputPath: string
  logs: string[]
  error: string
  collapsed: boolean
  createdAt: number
  finishedAt: number | null
}

let nextId = 1

const STORAGE_KEY = 'task-history'

function loadTasks(): Task[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) return JSON.parse(raw) as Task[]
  } catch {}
  return []
}

function saveTasks(tasks: Task[]) {
  try {
    const toSave = tasks.filter(t => t.status === 'completed' || t.status === 'failed').slice(0, 100)
    localStorage.setItem(STORAGE_KEY, JSON.stringify(toSave))
  } catch {}
}

export const useTaskStore = defineStore('task', () => {
  const tasks = ref<Task[]>(loadTasks())
  const maxTasks = 50

  // Restore nextId from saved tasks
  if (tasks.value.length > 0) {
    const maxId = Math.max(...tasks.value.map(t => t.id), 0)
    nextId = maxId + 1
  }

  const runningCount = computed(() => tasks.value.filter(t => t.status === 'running').length)
  const hasRunning = computed(() => runningCount.value > 0)

  function createTask(partial: Pick<Task, 'source' | 'url' | 'filePath' | 'fileName' | 'operation' | 'operationLabel'>): Task {
    const task: Task = {
      id: nextId++,
      ...partial,
      status: partial.source === 'url' ? 'downloading' : 'queued',
      progress: 0,
      progressLabel: partial.source === 'url' ? '下载中...' : '排队中',
      result: '',
      outputPath: '',
      logs: [],
      error: '',
      collapsed: false,
      createdAt: Date.now(),
      finishedAt: null,
    }
    tasks.value.unshift(task)
    if (tasks.value.length > maxTasks) tasks.value.pop()
    persist()
    return task
  }

  function persist() {
    saveTasks(tasks.value)
  }

  function updateTask(id: number, updates: Partial<Task>) {
    const idx = tasks.value.findIndex(t => t.id === id)
    if (idx !== -1) {
      Object.assign(tasks.value[idx], updates)
      if (updates.status === 'completed' || updates.status === 'failed') persist()
    }
  }

  function appendLog(id: number, line: string) {
    const task = tasks.value.find(t => t.id === id)
    if (task) {
      task.logs.push(line)
      if (task.logs.length > 1000) task.logs.shift()
    }
  }

  function removeTask(id: number) {
    const idx = tasks.value.findIndex(t => t.id === id)
    if (idx !== -1) { tasks.value.splice(idx, 1); persist() }
  }

  function clearCompleted() {
    tasks.value = tasks.value.filter(t => t.status !== 'completed' && t.status !== 'failed')
    persist()
  }

  function clearAll() {
    tasks.value = []
    persist()
  }

  return { tasks, runningCount, hasRunning, maxTasks, createTask, updateTask, appendLog, removeTask, clearCompleted, clearAll }
})
