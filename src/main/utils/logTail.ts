import { promises as fs } from 'fs'

export interface LogTailResult {
  lines: string[]
  truncated: boolean
  size: number
  logPath: string
}

export async function readTail(filePath: string, maxLines: number = 200): Promise<LogTailResult> {
  const content = await fs.readFile(filePath, 'utf-8')
  const allLines = content.split('\n')
  // Drop trailing empty line if file ends with \n
  if (allLines.length > 0 && allLines[allLines.length - 1] === '') allLines.pop()
  const truncated = allLines.length > maxLines
  const tail = allLines.slice(-maxLines)
  return { lines: tail, truncated, size: Buffer.byteLength(content, 'utf-8'), logPath: filePath }
}
