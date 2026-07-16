import { describe, it, expect } from 'vitest'
import { formatDuration } from '@utils/formatDuration'

/**
 * formatDuration unit tests — 6 scenarios covering:
 *   running, completed, after-retry, old-data-migration,
 *   negative-guard, zero-duration
 */

describe('formatDuration', () => {
  it('running task: uses nowOverride when finishedAt is null', () => {
    const task = {
      id: 1, source: 'local' as const, filePath: '', fileName: 'test.apk',
      operation: 'analyze' as const, operationLabel: '分析',
      status: 'running' as const, progress: 50, progressLabel: '',
      result: '', outputPath: '', logs: [], error: '', collapsed: false,
      taskDir: '',
      startedAt: 1000, finishedAt: null, createdAt: 1000,
    }
    expect(formatDuration(task, 2500)).toBe('1s')
  })

  it('completed task: uses finishedAt without nowOverride', () => {
    const task = {
      id: 1, source: 'local' as const, filePath: '', fileName: 'test.apk',
      operation: 'analyze' as const, operationLabel: '分析',
      status: 'completed' as const, progress: 100, progressLabel: '完成',
      result: '', outputPath: '', logs: [], error: '', collapsed: false,
      taskDir: '',
      startedAt: 1000, finishedAt: 62000, createdAt: 1000,
    }
    expect(formatDuration(task)).toBe('1m 1s')
  })

  it('after-retry: uses startedAt (last attempt) not createdAt', () => {
    const task = {
      id: 1, source: 'local' as const, filePath: '', fileName: 'test.apk',
      operation: 'analyze' as const, operationLabel: '分析',
      status: 'completed' as const, progress: 100, progressLabel: '完成',
      result: '', outputPath: '', logs: [], error: '', collapsed: false,
      taskDir: '',
      startedAt: 5000, finishedAt: 8000, createdAt: 1000,
    }
    // Only last attempt: 3000ms = 3s, NOT 7000ms (old bug)
    expect(formatDuration(task)).toBe('3s')
  })

  it('old-data-migration: fallback to createdAt when startedAt is missing', () => {
    const task = {
      id: 1, source: 'local' as const, filePath: '', fileName: 'test.apk',
      operation: 'analyze' as const, operationLabel: '分析',
      status: 'completed' as const, progress: 100, progressLabel: '完成',
      result: '', outputPath: '', logs: [], error: '', collapsed: false,
      taskDir: '',
      startedAt: undefined as any, finishedAt: 3000, createdAt: 1000,
    }
    expect(formatDuration(task)).toBe('2s')
  })

  it('negative-guard: returns empty string when finishedAt < startedAt', () => {
    const task = {
      id: 1, source: 'local' as const, filePath: '', fileName: 'test.apk',
      operation: 'analyze' as const, operationLabel: '分析',
      status: 'completed' as const, progress: 100, progressLabel: '完成',
      result: '', outputPath: '', logs: [], error: '', collapsed: false,
      taskDir: '',
      startedAt: 5000, finishedAt: 3000, createdAt: 1000,
    }
    expect(formatDuration(task)).toBe('')
  })

  it('zero-duration: returns 0s when finishedAt === startedAt', () => {
    const task = {
      id: 1, source: 'local' as const, filePath: '', fileName: 'test.apk',
      operation: 'analyze' as const, operationLabel: '分析',
      status: 'completed' as const, progress: 100, progressLabel: '完成',
      result: '', outputPath: '', logs: [], error: '', collapsed: false,
      taskDir: '',
      startedAt: 1000, finishedAt: 1000, createdAt: 1000,
    }
    expect(formatDuration(task)).toBe('0s')
  })
})
