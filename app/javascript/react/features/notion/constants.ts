// Tree indentation for NodeRow and TreeNode. Notion imposes no nesting-depth
// limit, so we clamp indent past MAX_INDENT_DEPTH; otherwise a deeply nested
// workspace squeezes the (truncating) title to nothing.
export const INDENT_BASE_REM = 0.75
export const INDENT_PER_DEPTH_REM = 1.25
export const MAX_INDENT_DEPTH = 5

export function indentRem(depth: number): string {
  return `${INDENT_BASE_REM + Math.min(depth, MAX_INDENT_DEPTH) * INDENT_PER_DEPTH_REM}rem`
}
