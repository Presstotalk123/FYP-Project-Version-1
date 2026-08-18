/**
 * Best-effort detection + fencing of hand-aligned ASCII tables (the
 * `+----+----+` / `| a | b |` style used by LeetCode problem statements and
 * similar sources) inside a block of pasted text.
 *
 * Descriptions are rendered as GFM Markdown (see DescriptionMarkdown.tsx),
 * which reflows/collapses whitespace outside of fenced code blocks. ASCII
 * tables only keep their column alignment when wrapped in a ``` fence, so
 * authors pasting a problem statement directly would otherwise need to add
 * the fences by hand. This scans the pasted text line by line and wraps any
 * contiguous run of table-shaped lines in ``` fences automatically.
 *
 * Heuristic, not a full parser:
 * - A line is "table-shaped" if it's a border line (`+---+---+`) or a pipe
 *   row (`| ... | ... |`).
 * - A contiguous run of table-shaped lines only gets fenced if it has at
 *   least 3 lines and at least 2 border lines — this avoids fencing
 *   incidental text that merely contains a `|` character (e.g. a stray
 *   pipe in prose), and avoids interfering with GFM pipe-table syntax
 *   (`| a | b |` / `|---|---|`), which has no `+` border lines and is
 *   already handled natively by remark-gfm.
 * - Lines already inside an existing ``` fence are left untouched so
 *   already-fenced content is never double-fenced.
 */
export function fenceAsciiTables(text: string): string {
  const lines = text.split('\n');
  const output: string[] = [];
  let currentRun: string[] = [];
  let inFence = false;

  const flushRun = () => {
    if (currentRun.length === 0) return;
    const borderCount = currentRun.filter((line) => isBorderLine(line)).length;
    if (currentRun.length >= 3 && borderCount >= 2) {
      output.push('```');
      output.push(...currentRun);
      output.push('```');
    } else {
      output.push(...currentRun);
    }
    currentRun = [];
  };

  for (const line of lines) {
    if (isFenceMarker(line)) {
      flushRun();
      output.push(line);
      inFence = !inFence;
      continue;
    }

    if (inFence) {
      output.push(line);
      continue;
    }

    if (isBorderLine(line) || isRowLine(line)) {
      currentRun.push(line);
    } else {
      flushRun();
      output.push(line);
    }
  }
  flushRun();

  return output.join('\n');
}

function isFenceMarker(line: string): boolean {
  return /^\s*```/.test(line);
}

function isBorderLine(line: string): boolean {
  return /^\s*\+[-+]+\+\s*$/.test(line);
}

function isRowLine(line: string): boolean {
  return /^\s*\|.*\|\s*$/.test(line);
}
