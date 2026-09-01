// Client-side, best-effort detection of obvious SQL syntax errors *before* a student's query is
// submitted to the backend. The goal is narrow: stop clearly-broken SQL (a typo'd leading keyword,
// unbalanced parentheses, an unclosed quote) so it never round-trips to the server — which, in a
// capped assessment, would otherwise burn one of the student's limited query attempts just to come
// back with a syntax error.
//
// Two confidence levels, so this can never lock a student out of a valid query:
//   - `block`: high-precision, deterministic, DIALECT-NEUTRAL structural checks. Set only when the
//              query is unambiguously broken. Callers hard-stop the submit on these.
//   - `warn` : the softer node-sql-parser verdict. node-sql-parser doesn't cover every valid SQLite
//              construct, so its failure is advisory only — callers surface a hint but STILL submit.
//              The backend stays the source of truth.
//
// Both SQLite and MySQL are accepted: the block scanner understands MySQL backtick identifiers, and
// the warn pass only fires when the query parses as NEITHER dialect.

import { Parser } from 'node-sql-parser';

export interface SyntaxCheck {
  /** Set when the query is clearly broken — callers should refuse to submit. */
  block?: string;
  /** Set when the query merely fails to parse — callers should hint but still submit. */
  warn?: string;
}

// A permissive superset of SQL statement starters across SQLite + MySQL. We only block a *first
// token* that is no SQL keyword at all (e.g. `SELCT`), never one that's merely disallowed on a
// given path — that's the backend's job. Kept broad on purpose to avoid false blocks.
const STATEMENT_KEYWORDS = new Set([
  'SELECT', 'WITH', 'INSERT', 'UPDATE', 'DELETE', 'CREATE', 'DROP', 'ALTER', 'REPLACE',
  'PRAGMA', 'EXPLAIN', 'VALUES', 'BEGIN', 'COMMIT', 'ROLLBACK', 'SAVEPOINT', 'RELEASE',
  'ANALYZE', 'ATTACH', 'DETACH', 'REINDEX', 'VACUUM',
]);

/**
 * Inspect a query for obvious syntax errors. Returns `{}` when nothing looks wrong.
 * See the module header for the block-vs-warn contract.
 */
export function checkSqlSyntax(sql: string): SyntaxCheck {
  if (!sql || !sql.trim()) return {}; // empty is handled by callers' own guard

  const structural = structuralError(sql);
  if (structural) return { block: structural };

  const keyword = leadingKeywordError(sql);
  if (keyword) return { block: keyword };

  // Soft pass: only warn when the query is valid in NEITHER dialect, so MySQL-flavored SQL
  // (backticks, `LIMIT a, b`, …) doesn't get flagged.
  if (!parsesAsEither(sql)) {
    return { warn: 'This may have a syntax error — double-check your SQL before running.' };
  }

  return {};
}

/**
 * Single char-by-char scan for the two structural faults: unbalanced parentheses and an
 * unterminated quote. Parens inside string literals, comments, or quoted identifiers don't count,
 * so `WHERE note = 'a)b'` is fine. Handles single-quote strings, double-quote strings/identifiers,
 * MySQL backtick identifiers (all with doubled-delimiter escaping: '', "", ``), plus line comments
 * and block comments. Returns a message on the first fault found, else null.
 */
function structuralError(sql: string): string | null {
  let depth = 0;
  let i = 0;
  const n = sql.length;

  while (i < n) {
    const ch = sql[i];

    // Line comment: -- … to end of line
    if (ch === '-' && sql[i + 1] === '-') {
      i += 2;
      while (i < n && sql[i] !== '\n') i++;
      continue;
    }
    // Block comment: /* … */ (SQLite/MySQL don't nest these)
    if (ch === '/' && sql[i + 1] === '*') {
      i += 2;
      while (i < n && !(sql[i] === '*' && sql[i + 1] === '/')) i++;
      if (i >= n) return 'Unterminated comment — a /* is missing its closing */.';
      i += 2;
      continue;
    }
    // Quoted span: ' ', " ", or ` ` — with doubled-delimiter escaping inside.
    if (ch === "'" || ch === '"' || ch === '`') {
      const quote = ch;
      i++;
      let closed = false;
      while (i < n) {
        if (sql[i] === quote) {
          if (sql[i + 1] === quote) {
            i += 2; // escaped delimiter ('' / "" / ``) — stays inside the span
            continue;
          }
          closed = true;
          i++;
          break;
        }
        i++;
      }
      if (!closed) {
        const label = quote === '`' ? 'identifier (`)' : `string (${quote})`;
        return `Unterminated ${label} — a quote is missing its closing match.`;
      }
      continue;
    }

    if (ch === '(') depth++;
    else if (ch === ')') {
      depth--;
      if (depth < 0) return 'Unbalanced parentheses — a closing ) has no matching (.';
    }
    i++;
  }

  if (depth > 0) return 'Unbalanced parentheses — an opening ( is missing its closing ).';
  return null;
}

/**
 * The first real token (after leading whitespace and comments) must be a recognizable SQL
 * statement keyword. Catches `SELCT …` / `FORM …`. Returns a message or null.
 */
function leadingKeywordError(sql: string): string | null {
  let i = 0;
  const n = sql.length;

  // Skip leading whitespace and comments to reach the first token.
  while (i < n) {
    const ch = sql[i];
    if (/\s/.test(ch)) { i++; continue; }
    if (ch === '-' && sql[i + 1] === '-') {
      i += 2;
      while (i < n && sql[i] !== '\n') i++;
      continue;
    }
    if (ch === '/' && sql[i + 1] === '*') {
      i += 2;
      while (i < n && !(sql[i] === '*' && sql[i + 1] === '/')) i++;
      i += 2;
      continue;
    }
    break;
  }

  const match = sql.slice(i).match(/^[A-Za-z_]+/);
  if (!match) return null; // starts with a non-word char (e.g. `(SELECT …)`) — leave to the parser
  const first = match[0].toUpperCase();
  if (!STATEMENT_KEYWORDS.has(first)) {
    return `"${match[0]}" doesn't look like a SQL statement — check the first keyword.`;
  }
  return null;
}

/** True if node-sql-parser accepts the query as SQLite OR MySQL. */
function parsesAsEither(sql: string): boolean {
  const parser = new Parser();
  for (const database of ['sqlite', 'mysql'] as const) {
    try {
      parser.astify(sql, { database });
      return true;
    } catch {
      // try the next dialect
    }
  }
  return false;
}
