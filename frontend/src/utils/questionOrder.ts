// Shared ordering for the merged problem lists (student practice pool, admin Problems),
// matching DATABASE_README_EN.md: items WITHOUT a LeetCode number — labs, ERD questions,
// hand-authored SQL — come first, newest-first; then LeetCode-imported questions in
// ascending problem-number order. Kept in one place so every list sorts identically.
export function byReadmeOrder<T extends { leetcode_id?: number | null; created_at: string }>(
  a: T,
  b: T,
): number {
  const aLC = a.leetcode_id != null;
  const bLC = b.leetcode_id != null;
  if (aLC !== bLC) return aLC ? 1 : -1; // non-LeetCode group before the LeetCode group
  if (aLC && bLC) return a.leetcode_id! - b.leetcode_id!; // LeetCode group by number asc
  return new Date(b.created_at).getTime() - new Date(a.created_at).getTime(); // group newest-first
}
