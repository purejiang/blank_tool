/**
 * Live run-log lines for the editor's 运行日志 panel.
 *
 * Two sources feed the panel and both must read the SAME way:
 *
 *  - the `stream-event` channel while a run is in flight (node lifecycle +
 *    `log` events emitted by tools such as `flow.log`);
 *  - `task.read_log` once the run reaches a terminal state — the per-task log
 *    file the engine writes at teardown, which contains exactly the same lines
 *    plus anything logged by tools that do not stream.
 *
 * Both sources are parsed into the SAME structured shape (time / node /
 * status / level / text) so the panel can render columns.  The on-disk format
 * mirrors the backend's `render_event_line`
 * (`cli/app/workflow/streaming.py`) and therefore the CLI console:
 *
 *     [12:00:01] [node_started] convert (file.read)
 *     [12:00:02] [node_completed] convert status=ok (12 ms)
 *     [12:00:03] [log] convert [info] 扫描完成
 *     [12:00:04] [workflow_completed] success=true
 *
 * Keeping the formatting here (a pure module) is what makes the panel testable
 * without a canvas, an IPC bridge or a backend.
 */

/** Visual category of one line — drives the row tone only. */
export type RunLogKind = 'node' | 'log' | 'workflow' | 'plain'

export interface RunLogLine {
  kind: RunLogKind
  /** Local HH:MM:SS at emission ('' when unknown). */
  time: string
  /** Node path from the run root ('' for workflow-level / plain lines). */
  node: string
  /** Display text: tool name, duration summary, log message, raw line. */
  text: string
  /** Terminal node status (`node_completed` only). */
  status?: string
  /** Log level (`log` only). */
  level?: string
  /** Error text (failed nodes, workflow_failed). */
  error?: string
}

/**
 * Event types the editor's run-log understands.  Terminal types settle the run;
 * `log` is a tool-level line (`streaming.LOG`).
 */
export const RUN_LOG_EVENT_TYPES = new Set([
  'node_started',
  'node_completed',
  'log',
  'workflow_completed',
  'workflow_failed',
  'workflow_cancelled',
])

export const TERMINAL_RUN_EVENT_TYPES = new Set([
  'workflow_completed',
  'workflow_failed',
  'workflow_cancelled',
])

/** Log levels `flow.log` accepts (anything else is rendered as-is). */
const LOG_LEVELS = new Set(['debug', 'info', 'warning', 'error', 'critical'])

/** Local HH:MM:SS — fallback when a streamed event carries no backend `ts`. */
export function nowTimeString(): string {
  const d = new Date()
  const p = (n: number) => String(n).padStart(2, '0')
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}

/** `[node_started] id (tool)` / `[node_completed] id status=… (N ms)` + error. */
function formatNodeEvent(record: Record<string, any>, time: string): RunLogLine {
  const node = String(record.node_id ?? '?')
  if (record.type === 'node_started') {
    return { kind: 'node', time, node, text: String(record.tool ?? '') }
  }
  const attempts = Number(record.attempts ?? 1)
  const duration = `${record.duration_ms ?? '?'} ms${attempts > 1 ? `, attempts=${attempts}` : ''}`
  const line: RunLogLine = {
    kind: 'node',
    time,
    node,
    status: String(record.status ?? '?'),
    text: `(${duration})`,
  }
  if (record.error) line.error = String(record.error)
  return line
}

/**
 * Format one streamed workflow event into a structured log line.
 *
 * @returns the line, or null for event types the run log ignores (logcat /
 *   download / progress noise sharing the same channel).
 */
export function formatRunLogEvent(event: unknown): RunLogLine | null {
  if (!event || typeof event !== 'object') return null
  const record = event as Record<string, any>
  const type = typeof record.type === 'string' ? record.type : ''
  if (!RUN_LOG_EVENT_TYPES.has(type)) return null
  const time = typeof record.ts === 'string' && record.ts ? record.ts : nowTimeString()

  switch (type) {
    case 'node_started':
    case 'node_completed':
      return formatNodeEvent(record, time)
    case 'log':
      return {
        kind: 'log',
        time,
        node: String(record.node_id ?? ''),
        level: String(record.level ?? 'info'),
        text: String(record.message ?? ''),
      }
    case 'workflow_completed':
      return { kind: 'workflow', time, node: '', text: `success=${record.success ?? '?'}` }
    case 'workflow_failed': {
      const error = String(record.error ?? '')
      return { kind: 'workflow', time, node: '', text: error, error }
    }
    case 'workflow_cancelled':
      return { kind: 'workflow', time, node: '', text: 'cancelled' }
    default:
      return null
  }
}

// ---- per-task log file parsing -------------------------------------------------

/** `[12:00:01] [node_started] …` → ('12:00:01', rest). */
const TIME_PREFIX_RE = /^\[(\d{1,2}:\d{2}:\d{2})\]\s*(.*)$/
/** `[node_started] <node> (<tool>)`. */
const NODE_STARTED_RE = /^\[node_started\] (\S+) \((.*)\)$/
/** `[node_completed] <node> status=<s> (<N ms[, attempts=M]>)` + ` error: …`. */
const NODE_COMPLETED_RE = /^\[node_completed\] (\S+) status=(\S+) \(([^)]*)\)(?: error: (.*))?$/
/** `[log] <node> [<level>] <message>` — node segment is optional. */
const LOG_WITH_NODE_RE = /^\[log\] (\S+) \[([a-zA-Z]+)\] (.*)$/
const LOG_RE = /^\[log\] \[([a-zA-Z]+)\] (.*)$/
/** Old-format bare tool lines: `[<level>] <message>`. */
const LEVEL_TAG_RE = /^\[([a-zA-Z]+)\] (.*)$/

/** Classify one already-written line of the per-task log file. */
function parseTaskLogLine(text: string): RunLogLine {
  let time = ''
  let rest = text
  const timeMatch = TIME_PREFIX_RE.exec(text)
  if (timeMatch) {
    time = timeMatch[1]
    rest = timeMatch[2]
  }
  const base = { time, node: '' }

  const started = NODE_STARTED_RE.exec(rest)
  if (started) return { kind: 'node', ...base, node: started[1], text: started[2] }

  const completed = NODE_COMPLETED_RE.exec(rest)
  if (completed) {
    const line: RunLogLine = {
      kind: 'node',
      ...base,
      node: completed[1],
      status: completed[2],
      text: `(${completed[3]})`,
    }
    if (completed[4]) line.error = completed[4]
    return line
  }

  const logWithNode = LOG_WITH_NODE_RE.exec(rest)
  if (logWithNode) {
    return { kind: 'log', ...base, node: logWithNode[1], level: logWithNode[2].toLowerCase(), text: logWithNode[3] }
  }
  const log = LOG_RE.exec(rest)
  if (log) return { kind: 'log', ...base, level: log[1].toLowerCase(), text: log[2] }

  const completedWf = /^\[workflow_completed\] ?(.*)$/.exec(rest)
  if (completedWf) return { kind: 'workflow', ...base, text: completedWf[1] }
  const failedWf = /^\[workflow_failed\] ?(.*)$/.exec(rest)
  if (failedWf) return { kind: 'workflow', ...base, text: failedWf[1], error: failedWf[1] }
  if (/^\[workflow_cancelled\]/.test(rest)) return { kind: 'workflow', ...base, text: 'cancelled' }

  const levelTag = LEVEL_TAG_RE.exec(rest)
  if (levelTag && LOG_LEVELS.has(levelTag[1].toLowerCase())) {
    return { kind: 'log', ...base, level: levelTag[1].toLowerCase(), text: levelTag[2] }
  }
  return { kind: 'plain', ...base, text: rest }
}

/**
 * Split `task.read_log` content into lines.  Blank trailing lines are dropped;
 * everything else is kept (parsed into the structured shape) so the panel
 * shows exactly what is on disk.
 */
export function linesFromTaskLog(content: unknown): RunLogLine[] {
  if (typeof content !== 'string' || content.length === 0) return []
  return content
    .split(/\r?\n/)
    .filter((line) => line.length > 0)
    .map(parseTaskLogLine)
}
