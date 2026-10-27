// Stable numeric id per query-result object, for use as a React `key` on a results table.
// Each execution produces a new result object, so keying the <table> on this rebuilds it
// from scratch per run — no cell from a previous result can survive into the next one —
// while ordinary re-renders (tab switches, typing) keep the same id and don't remount it.
const ids = new WeakMap<object, number>();
let nextId = 0;

export function resultKey(result: object): number {
  let id = ids.get(result);
  if (id === undefined) {
    id = ++nextId;
    ids.set(result, id);
  }
  return id;
}
