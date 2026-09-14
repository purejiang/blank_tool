import { describe, it, expect } from 'vitest';
import zh from '@/renderer/i18n/locales/zh-CN';
import en from '@/renderer/i18n/locales/en-US';

// Task 6: the 8 new automation record.* keys
const RECORD_KEYS = [
  'record',
  'recordStart',
  'recordStop',
  'recordEmpty',
  'recordApplied',
  'recordFailed',
  'recordStopped',
  'noDeviceRecord',
];

// Flatten nested namespaces into dotted paths (act.* -> act.tap, ...)
function flattenKeys(obj: Record<string, unknown>, prefix = ''): string[] {
  const keys: string[] = [];
  for (const [key, value] of Object.entries(obj)) {
    const path = prefix ? `${prefix}.${key}` : key;
    if (value !== null && typeof value === 'object') {
      keys.push(...flattenKeys(value as Record<string, unknown>, path));
    } else {
      keys.push(path);
    }
  }
  return keys;
}

describe('i18n automation record.* keys', () => {
  // Dynamic baseline: key counts change with parallel work, so the test only
  // locks parity between locales + presence of the new keys (no hardcoded totals).
  const zhKeys = flattenKeys(zh.automation);
  const enKeys = flattenKeys(en.automation);

  it('zh-CN and en-US automation namespaces have identical flattened key sets', () => {
    const zhSet = new Set(zhKeys);
    const enSet = new Set(enKeys);
    const onlyInZh = zhKeys.filter((k) => !enSet.has(k));
    const onlyInEn = enKeys.filter((k) => !zhSet.has(k));
    expect(onlyInZh).toEqual([]);
    expect(onlyInEn).toEqual([]);
    // no duplicate keys within either locale
    expect(new Set(zhKeys).size).toBe(zhKeys.length);
    expect(new Set(enKeys).size).toBe(enKeys.length);
  });

  it('contains the 8 new record.* keys in both locales', () => {
    for (const key of RECORD_KEYS) {
      expect(zhKeys, `zh-CN missing automation.${key}`).toContain(key);
      expect(enKeys, `en-US missing automation.${key}`).toContain(key);
    }
  });
});
