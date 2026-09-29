import { describe, expect, it } from 'vitest'

import {
  RUN_LOG_EVENT_TYPES,
  TERMINAL_RUN_EVENT_TYPES,
  formatRunLogEvent,
  linesFromTaskLog,
} from '@/renderer/components/workflow/runLog'

/**
 * Run-log formatting (docs/08 §3·S2 的「运行日志」).
 *
 * The live panel (stream events) and the post-run view (`task.read_log`) must
 * parse into the SAME structured shape (time / node / status / level / text),
 * and the file view must match the engine's own per-task log lines
 * (`cli/app/workflow/streaming.py::render_event_line`) — otherwise the panel
 * rewrites itself into a different dialect the moment a run ends.
 */
describe('formatRunLogEvent', () => {
  it('formats node lifecycle events with time + node columns', () => {
    expect(formatRunLogEvent({ type: 'node_started', node_id: 'convert', tool: 'file.read', ts: '12:00:01' })).toEqual({
      kind: 'node',
      time: '12:00:01',
      node: 'convert',
      text: 'file.read',
    })
    expect(
      formatRunLogEvent({
        type: 'node_completed',
        node_id: 'convert',
        status: 'ok',
        duration_ms: 12,
        ts: '12:00:02',
      }),
    ).toEqual({ kind: 'node', time: '12:00:02', node: 'convert', status: 'ok', text: '(12 ms)' })
  })

  it('appends the error text on a failed node', () => {
    expect(
      formatRunLogEvent({
        type: 'node_completed',
        node_id: 'assert_limit',
        status: 'failed',
        duration_ms: 0,
        error: '命中 2 行，超过上限 0',
        ts: '08:30:00',
      }),
    ).toEqual({
      kind: 'node',
      time: '08:30:00',
      node: 'assert_limit',
      status: 'failed',
      text: '(0 ms)',
      error: '命中 2 行，超过上限 0',
    })
  })

  it('surfaces retry attempts on repeated nodes', () => {
    expect(
      formatRunLogEvent({
        type: 'node_completed',
        node_id: 'retry_me',
        status: 'ok',
        duration_ms: 250,
        attempts: 3,
        ts: '08:30:05',
      }),
    ).toEqual({
      kind: 'node',
      time: '08:30:05',
      node: 'retry_me',
      status: 'ok',
      text: '(250 ms, attempts=3)',
    })
  })

  it('formats tool-level log events (flow.log → streaming.LOG) with the node column', () => {
    expect(
      formatRunLogEvent({
        type: 'log',
        level: 'warning',
        message: '样本文件 115 字节',
        node_id: 'log_size',
        ts: '12:01:00',
      }),
    ).toEqual({ kind: 'log', time: '12:01:00', node: 'log_size', level: 'warning', text: '样本文件 115 字节' })
    // A missing level falls back to info rather than printing "undefined".
    expect(formatRunLogEvent({ type: 'log', message: 'hi', ts: '12:01:01' })).toEqual({
      kind: 'log',
      time: '12:01:01',
      node: '',
      level: 'info',
      text: 'hi',
    })
  })

  it('formats the three terminal events', () => {
    expect(formatRunLogEvent({ type: 'workflow_completed', success: true, ts: '12:02:00' })).toEqual({
      kind: 'workflow',
      time: '12:02:00',
      node: '',
      text: 'success=true',
    })
    expect(formatRunLogEvent({ type: 'workflow_failed', error: 'kapow', ts: '12:02:01' })).toEqual({
      kind: 'workflow',
      time: '12:02:01',
      node: '',
      text: 'kapow',
      error: 'kapow',
    })
    expect(formatRunLogEvent({ type: 'workflow_cancelled', ts: '12:02:02' })).toEqual({
      kind: 'workflow',
      time: '12:02:02',
      node: '',
      text: 'cancelled',
    })
  })

  it('falls back to local time when the event carries no backend ts', () => {
    const line = formatRunLogEvent({ type: 'node_started', node_id: 'n1', tool: 't' })
    expect(line?.time).toMatch(/^\d{2}:\d{2}:\d{2}$/)
  })

  it('ignores foreign channel noise and junk input', () => {
    expect(formatRunLogEvent({ type: 'logcat', line: 'x' })).toBeNull()
    expect(formatRunLogEvent({ type: 'download_progress', percent: 10 })).toBeNull()
    expect(formatRunLogEvent({})).toBeNull()
    expect(formatRunLogEvent(null)).toBeNull()
    expect(formatRunLogEvent('node_started')).toBeNull()
  })

  it('keeps the terminal set a subset of the accepted set', () => {
    for (const type of TERMINAL_RUN_EVENT_TYPES) {
      expect(RUN_LOG_EVENT_TYPES.has(type)).toBe(true)
    }
  })
})

describe('linesFromTaskLog', () => {
  it('parses the engine-written per-task log into structured columns', () => {
    const content = [
      '[12:00:01] [node_started] write_sample (file.write)',
      '[12:00:02] [node_completed] write_sample status=ok (8 ms)',
      '[12:00:03] [log] write_sample [info] 扫描完成：命中 2 行',
      '[12:00:04] [log] [warning] 全局警告',
      '[12:00:05] [node_completed] sub/r status=failed (10 ms) error: boom',
      '[12:00:06] [workflow_completed] success=True',
      'plain stdout line',
      '',
    ].join('\n')

    expect(linesFromTaskLog(content)).toEqual([
      { kind: 'node', time: '12:00:01', node: 'write_sample', text: 'file.write' },
      { kind: 'node', time: '12:00:02', node: 'write_sample', status: 'ok', text: '(8 ms)' },
      { kind: 'log', time: '12:00:03', node: 'write_sample', level: 'info', text: '扫描完成：命中 2 行' },
      { kind: 'log', time: '12:00:04', node: '', level: 'warning', text: '全局警告' },
      {
        kind: 'node',
        time: '12:00:05',
        node: 'sub/r',
        status: 'failed',
        text: '(10 ms)',
        error: 'boom',
      },
      { kind: 'workflow', time: '12:00:06', node: '', text: 'success=True' },
      { kind: 'plain', time: '', node: '', text: 'plain stdout line' },
    ])
  })

  it('tolerates old-format lines without a time prefix', () => {
    expect(linesFromTaskLog('[node_started] n1 (file.read)\n[info] 扫描完成\n')).toEqual([
      { kind: 'node', time: '', node: 'n1', text: 'file.read' },
      { kind: 'log', time: '', node: '', level: 'info', text: '扫描完成' },
    ])
  })

  it('tolerates CRLF, an empty file and non-string input', () => {
    expect(linesFromTaskLog('[12:00:00] [info] a\r\n[12:00:01] [info] b\r\n')).toEqual([
      { kind: 'log', time: '12:00:00', node: '', level: 'info', text: 'a' },
      { kind: 'log', time: '12:00:01', node: '', level: 'info', text: 'b' },
    ])
    expect(linesFromTaskLog('')).toEqual([])
    expect(linesFromTaskLog(undefined)).toEqual([])
    expect(linesFromTaskLog({ content: 'x' })).toEqual([])
  })
})
