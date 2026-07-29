import { callBackendAPI } from '../core/callBackend';

export const taskApi = {
  readLog: (task_id: string, tail_bytes?: number) => callBackendAPI('task.read_log', { task_id, tail_bytes }),
  appendLog: (task_id: string, line: string) => callBackendAPI('task.append_log', { task_id, line }),
  deleteOutput: (paths: string[]) => callBackendAPI('task.delete_output', { paths }),
  deleteTaskDir: (task_id: string) => callBackendAPI('task.delete_task_dir', { task_id }),
  list: () => callBackendAPI('task.list'),
  cancelRequest: (request_id: string) => callBackendAPI('request.cancel', { request_id }),
};
