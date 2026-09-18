// ============================================================
// scripts/lib/version.mjs — 版本号解析与比较（纯函数，无副作用）
//
// 单独成一个模块是为了**能被直接验证**：`release.mjs` 顶层会立即跑 main()，
// 无法被 import 测试，而「新版本号是否真的比上一个 tag 新」这条判断一旦写错，
// 后果是用户端自更新静默失效（见 release.mjs 里 compareVersions 的调用点）。
// ============================================================

/**
 * 解析 x.y.z（允许 v 前缀，如 v2.5.0）为数字数组。
 * @param {string} text
 * @returns {[number, number, number] | null} 不合法返回 null
 */
export function parseVersion(text) {
  const m = /^v?(\d+)\.(\d+)\.(\d+)$/.exec(String(text ?? '').trim());
  if (!m) return null;
  return [Number(m[1]), Number(m[2]), Number(m[3])];
}

/**
 * 数值化比较版本号（**不是**字符串比较：'2.10.0' > '2.9.0'）。
 * @param {string} a
 * @param {string} b
 * @returns {-1 | 0 | 1 | null} 任一侧不合法时返回 null（调用方自行决定跳过还是报错）
 */
export function compareVersions(a, b) {
  const pa = parseVersion(a);
  const pb = parseVersion(b);
  if (!pa || !pb) return null;
  for (let i = 0; i < 3; i++) {
    if (pa[i] !== pb[i]) return pa[i] < pb[i] ? -1 : 1;
  }
  return 0;
}
