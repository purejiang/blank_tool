// ==================== 工具相关 ====================
import { callBackendAPI } from '../core/callBackend';
import type { JsonObject } from '../../shared/ipc/protocol';

export const toolApi = {
  // 获取工具列表/检查工具
  getTools: (params?: JsonObject) => callBackendAPI('tool.get_tools', params || {}),
  checkTool: (toolName?: string, refresh?: boolean) =>
    callBackendAPI('tool.get_tools', { tool_name: toolName, refresh }),
  // 设置系统查找模式
  setToolSearchMode: (systemSearch: boolean) =>
    callBackendAPI('tool.set_search_mode', { system_search: systemSearch }),
  // 工具自定义路径
  setToolCustomPath: (toolName: string, path: string) =>
    callBackendAPI('tool.set_custom_path', { tool_name: toolName, path }),
  resetToolCustomPath: (toolName: string) =>
    callBackendAPI('tool.reset_custom_path', { tool_name: toolName }),
  getToolCustomPaths: () => callBackendAPI('tool.get_custom_paths'),
};
