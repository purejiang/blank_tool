/**
 * Port connection validation for the workflow editor (todo 35).
 *
 * Mirrors backend/app/protocol/types.py: two ports connect when their base
 * types match (TypeAnnotation.is_compatible). Subtypes are advisory only
 * (decision D7) and are deliberately never enforced here or in the engine.
 *
 * This runs in the renderer at edge-create time as UX feedback (toast +
 * handle highlighting); the engine re-checks base types at runtime, so the
 * editor check can be bypassed without producing an invalid workflow.
 */
import type { InjectionKey, Ref } from 'vue'

import { portTypeLabel, type PortTypeRef } from './toolMeta'

/** Valid base type values (BaseType enum, backend/app/protocol/types.py). */
export const BASE_TYPES = ['file', 'directory', 'text', 'number', 'boolean', 'json'] as const

export type BaseType = (typeof BASE_TYPES)[number]

/** True when the string is a known base type (guards backend payload drift). */
export function isBaseType(value: string | null | undefined): value is BaseType {
  return typeof value === 'string' && (BASE_TYPES as readonly string[]).includes(value)
}

/**
 * Two ports are compatible iff their base types match.
 * Mirrors TypeAnnotation.is_compatible: subtype is advisory (D7) and ignored.
 */
export function isPortCompatible(sourceType: string, targetType: string): boolean {
  return isBaseType(sourceType) && isBaseType(targetType) && sourceType === targetType
}

/** One side of a candidate connection, resolved from node + handle ids. */
export interface PortRef {
  nodeId: string
  portName: string
  portType?: PortTypeRef | null
}

export interface ConnectionValidation {
  valid: boolean
  reason?: string
}

/**
 * Validate a candidate source→target connection.
 * On rejection the reason is user-facing (shown as a toast).
 */
export function validateConnection(source: PortRef, target: PortRef): ConnectionValidation {
  if (!source.portType) {
    return { valid: false, reason: `Source port "${source.portName || '?'}" has no type information` }
  }
  if (!target.portType) {
    return { valid: false, reason: `Target port "${target.portName || '?'}" has no type information` }
  }
  if (!isPortCompatible(source.portType.base, target.portType.base)) {
    return {
      valid: false,
      reason: `Incompatible types: ${portTypeLabel(source.portType)} → ${portTypeLabel(target.portType)}`,
    }
  }
  return { valid: true }
}

/**
 * Live connection-drag state: provided by WorkflowEditorPage on
 * connect-start, injected by ToolNode to highlight compatible handles and
 * dim incompatible ones while the user drags a connection.
 *
 * `base` is the base type of the handle the drag started from; candidate
 * handles on the opposite side match when their base type equals `base`.
 */
export interface ConnectionDragInfo {
  base: BaseType
  fromHandleType: 'source' | 'target'
}

export const CONNECTION_DRAG_KEY: InjectionKey<Ref<ConnectionDragInfo | null>> =
  Symbol('workflow-connection-drag')
