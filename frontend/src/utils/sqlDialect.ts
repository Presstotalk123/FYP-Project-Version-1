// Best-effort MySQL → SQLite dialect converter for the question/lab authoring forms.
//
// Authors often paste setup scripts copied from LeetCode (and similar), which use MySQL
// syntax: `TRUNCATE TABLE`, `int`, `varchar(255)`, backtick-quoted identifiers, etc. This
// platform runs SQLite server-side, where `TRUNCATE TABLE` is invalid. `mysqlToSqlite`
// rewrites the cases that genuinely break on SQLite, plus a couple of type names for
// readability.
//
// Deliberately conservative: SQLite is very lenient about type names (it accepts DATETIME,
// FLOAT, DECIMAL(10,2), BOOLEAN, VARCHAR(255)… via type affinity), so we only rewrite type
// keywords that can NEVER also be a column name — i.e. the integer family and the
// paren-guarded char/varchar/*text forms. We do NOT touch bare words like `date`, `time`,
// `year`, `timestamp`, `text`, `bool`, `decimal`, `float`: real LeetCode tables use those as
// column names (e.g. problem 1661 has a `timestamp float` column), and rewriting them by
// keyword would corrupt the schema. SQLite accepts them unchanged anyway.
//
// This is a heuristic regex transform, NOT a SQL parser. To avoid rewriting keywords that
// appear inside string literals, comments, or quoted identifiers, those are masked out
// before the transforms run and restored afterward. The author reviews the result.

/**
 * Convert a MySQL / LeetCode-style SQL setup script to SQLite-compatible SQL.
 * Best-effort: handles TRUNCATE, the unambiguous MySQL type names, backtick identifiers, and
 * MySQL-only tokens. Content inside string literals, comments, and quoted identifiers is
 * left untouched.
 */
export function mysqlToSqlite(sql: string): string {
  if (!sql) return sql;

  // 1. Mask string literals, comments, and quoted identifiers so transforms never touch
  //    their contents. Backtick identifiers are converted to SQLite double-quotes here too.
  const { masked, restore } = maskProtectedSpans(sql);

  let out = masked;

  // 2. TRUNCATE TABLE x  ->  DELETE FROM x   (the one mandatory fix; SQLite has no TRUNCATE)
  out = out.replace(/\bTRUNCATE\s+TABLE\b/gi, 'DELETE FROM');

  // 3. Type mapping — only the forms that can never also be a column name.
  //    nvarchar(n) / varchar(n) / char(n)  ->  TEXT   (paren-guarded, so never a bare name)
  out = out.replace(/\bn?(?:var)?char\s*\(\s*\d+\s*\)/gi, 'TEXT');
  //    longtext / mediumtext / tinytext  ->  TEXT   (compound words, never column names;
  //    bare `text` is already the SQLite type, so it's intentionally left alone)
  out = out.replace(/\b(?:long|medium|tiny)text\b/gi, 'TEXT');
  //    integer family  ->  INTEGER   (int, tinyint, smallint, mediumint, bigint, integer,
  //    int(n)). Trailing \b so we don't rewrite the "int" inside words like "into"/"print".
  out = out.replace(/\b(?:tiny|small|medium|big)?int(?:eger)?\b(?:\s*\(\s*\d+\s*\))?/gi, 'INTEGER');

  // 4. Strip MySQL-only tokens SQLite rejects.
  out = out.replace(/\bauto_increment\b/gi, ''); // syntax error in SQLite (rowid auto-increments)
  out = out.replace(/\bunsigned\b/gi, '');
  //    Trailing table options: ENGINE=..., DEFAULT CHARSET=..., COLLATE ...
  out = out.replace(/\bengine\s*=\s*\w+/gi, '');
  out = out.replace(/\bdefault\s+charset\s*=\s*\w+/gi, '');
  out = out.replace(/\bcollate\s+\w+/gi, '');

  // Tidy up whitespace left by stripped tokens (collapse runs of spaces, trim before ,/) ).
  out = out.replace(/[ \t]{2,}/g, ' ').replace(/[ \t]+([),])/g, '$1');

  // 5. Best-effort: ensure each single-line statement is semicolon-terminated. LeetCode omits
  //    the separators, but the SQLite CLI/driver needs them to run a multi-statement block.
  //    Runs on the masked text so a newline inside a string literal can't be mistaken for a
  //    statement break. Conservative — only lines that start AND end a statement themselves
  //    (i.e. single-line statements) get a `;`, so it never terminates a multi-line CREATE or
  //    a CTE mid-way. Multi-line statements keep whatever terminator the author wrote.
  out = ensureStatementSemicolons(out);

  // 6. Restore masked literals / comments / identifiers.
  out = restore(out);

  return out;
}

// Swap the spans we must not rewrite — string literals ('...'), double-quoted identifiers
// ("..."), backtick identifiers (`...`), and comments (-- , /* */) — for opaque placeholders,
// returning a `restore` that splices the originals back. Backtick identifiers are stored in
// their converted SQLite form ("..."). Unlike sqlConcepts.sanitize (which blanks spans), we
// keep the text so the output is otherwise unchanged.
function maskProtectedSpans(sql: string): { masked: string; restore: (s: string) => string } {
  const store: string[] = [];
  // Sentinel has no whitespace and no word chars the type/keyword regexes match, so it
  // survives the transforms (and the whitespace-tidy step) intact and restores cleanly even
  // when adjacent to ')' or ','.
  const stash = (text: string): string => {
    const token = '@@MASK' + store.length + '@@';
    store.push(text);
    return token;
  };

  // One regex over every construct to protect, matched left-to-right so a marker inside a
  // string (or vice versa) is handled by whichever opens first.
  const masked = sql.replace(
    /--[^\n]*|\/\*[\s\S]*?\*\/|'(?:[^']|'')*'|"(?:[^"]|"")*"|`[^`]*`/g,
    (m) => {
      if (m[0] === '`') {
        // MySQL backtick identifier -> SQLite double-quoted identifier; protect its contents
        // (a column literally named `int`/`date` must not be type-mapped).
        return stash('"' + m.slice(1, -1).replace(/"/g, '""') + '"');
      }
      return stash(m);
    },
  );

  const restore = (s: string): string =>
    s.replace(/@@MASK(\d+)@@/g, (_, i) => store[Number(i)]);

  return { masked, restore };
}

// Append a `;` to single-line top-level statements that lack one. LeetCode setup lines have
// no terminators; the SQLite CLI/driver needs them to separate statements in a batch.
function ensureStatementSemicolons(sql: string): string {
  const lines = sql.split('\n');
  const result: string[] = [];
  const startsStatement = (s: string) =>
    /^\s*(create|insert|update|delete|drop|alter|select|with|truncate)\b/i.test(s);

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const trimmed = line.trimEnd();
    // Only a self-contained statement line gets a semicolon: it has content, doesn't already
    // end with ';' / ',' / an open paren (continuation), starts with a statement keyword, and
    // the next non-blank line begins a new statement (or we're at the end). This keeps us from
    // terminating a multi-line CREATE/CTE partway through.
    if (trimmed.length > 0 && !/[;,(]$/.test(trimmed) && startsStatement(line)) {
      let j = i + 1;
      while (j < lines.length && lines[j].trim() === '') j++;
      const nextStartsNew = j >= lines.length || startsStatement(lines[j]);
      if (nextStartsNew) {
        result.push(trimmed + ';');
        continue;
      }
    }
    result.push(line);
  }

  return result.join('\n');
}
