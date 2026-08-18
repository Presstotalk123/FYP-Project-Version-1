// One-off import helper: converts the scraped `leetcode_questions.json` (MySQL/LeetCode
// dialect) into SQLite-ready question data, using the SAME conversion code the admin
// "New Question" form's "Convert to SQLite" and "Suggest from answer query" buttons use
// (src/utils/sqlDialect.ts mysqlToSqlite, src/utils/sqlConcepts.ts detectConcepts) — not a
// reimplementation. Run from `frontend/`:
//
//   node --experimental-strip-types scripts/convert-leetcode-questions.mjs
//
// Writes scripts/leetcode_questions.converted.json, consumed by
// backend/scripts/import_leetcode_questions.py.

import { readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, '..', '..');
const INPUT_PATH = path.join(REPO_ROOT, 'leetcode_questions.json');
const OUTPUT_PATH = path.join(__dirname, 'leetcode_questions.converted.json');

const { mysqlToSqlite } = await import('../src/utils/sqlDialect.ts');
const { detectConcepts } = await import('../src/utils/sqlConcepts.ts');

// Known-bad ids that cannot be auto-imported (see the plan for why each is excluded):
// no sql_schema at all, garbled scraped answer data, parameterized stored
// functions/procedures, or a bare DELETE that needs Advanced SQL Testing mode.
const KNOWN_BAD = {
  '596': 'no sql_schema in the scraped data',
  '627': 'no sql_schema in the scraped data',
  '1939': 'answer field is garbled scraped table output, not SQL',
  '2205': 'answer is a parameterized MySQL CREATE FUNCTION (no parameterized-query support)',
  '2230': 'answer is a parameterized MySQL CREATE PROCEDURE (no parameterized-query support)',
  '177': 'answer is a parameterized MySQL CREATE FUNCTION (no parameterized-query support)',
  '196': 'answer is a bare DELETE statement; needs hand-authored Advanced SQL Testing setup',
};

// --- top-level statement splitter (quote/backtick/comment aware) --------------------

/** Split a SQL script into individual statements on top-level `;`, ignoring `;` inside
 * string literals, quoted identifiers, backtick identifiers, and comments. */
function splitStatements(sql) {
  const statements = [];
  let current = '';
  let i = 0;
  const n = sql.length;
  while (i < n) {
    const c = sql[i];
    if (c === "'" || c === '"' || c === '`') {
      const quote = c;
      let span = c;
      i += 1;
      while (i < n) {
        span += sql[i];
        if (sql[i] === quote) {
          // doubled quote = escaped quote, keep consuming
          if (sql[i + 1] === quote) {
            span += sql[i + 1];
            i += 2;
            continue;
          }
          i += 1;
          break;
        }
        i += 1;
      }
      current += span;
      continue;
    }
    if (c === '-' && sql[i + 1] === '-') {
      const end = sql.indexOf('\n', i);
      const stop = end === -1 ? n : end;
      current += sql.slice(i, stop);
      i = stop;
      continue;
    }
    if (c === '/' && sql[i + 1] === '*') {
      const end = sql.indexOf('*/', i + 2);
      const stop = end === -1 ? n : end + 2;
      current += sql.slice(i, stop);
      i = stop;
      continue;
    }
    if (c === ';') {
      statements.push(current.trim());
      current = '';
      i += 1;
      continue;
    }
    current += c;
    i += 1;
  }
  if (current.trim()) statements.push(current.trim());
  return statements.filter((s) => s.length > 0);
}

/** Split a LeetCode-style `sql_schema` blob into (schema, seed) statement lists:
 * CREATE TABLE -> schema, INSERT -> seed, TRUNCATE TABLE -> dropped (tables are always
 * freshly created, so pre-truncating is a no-op here). Anything else is logged and kept
 * in schema so it isn't silently lost. */
function splitSchemaAndSeed(sqlSchema, questionId) {
  const schemaStatements = [];
  const seedStatements = [];
  for (const stmt of splitStatements(sqlSchema)) {
    if (/^create\s+table/i.test(stmt)) {
      schemaStatements.push(stmt);
    } else if (/^insert\s+into/i.test(stmt)) {
      seedStatements.push(stmt);
    } else if (/^truncate\s+table/i.test(stmt)) {
      // no-op: freshly created table
    } else {
      console.warn(`  [#${questionId}] unrecognized statement kept in schema: ${stmt.slice(0, 60)}...`);
      schemaStatements.push(stmt);
    }
  }
  return {
    schema_sql: schemaStatements.map((s) => s + ';').join('\n'),
    sample_data_sql: seedStatements.map((s) => s + ';').join('\n'),
  };
}

// --- import-only extra dialect fixups ---------------------------------------------
//
// mysqlToSqlite (the shared admin-form utility) deliberately stops at TRUNCATE/type
// mapping — it never touches date functions, MySQL-only aggregate syntax, etc. (see its
// own header comment). These few extra rewrites are specific to unattended bulk import
// of this LeetCode dataset and are applied ON TOP OF mysqlToSqlite's output, not folded
// into it, so the shared admin-form tool's behavior for live staff authoring is
// unaffected. Each rule below targets one confirmed, mechanical MySQL->SQLite gap seen
// in this dataset's dry run; anything not covered here is left to fail validation and
// gets reported for manual fixing rather than silently guessed at.
function applyImportFixups(sql) {
  if (!sql) return sql;
  let out = sql;

  // ENUM('a','b',...) column type -> TEXT (SQLite has no ENUM; schema-only).
  out = out.replace(/\benum\s*\([^)]*\)/gi, 'TEXT');

  // A function-call argument, allowing one level of nested parens (e.g. `min(event_date)`
  // as an arg to `adddate(...)`) — plain `[^,()]+` isn't enough once an arg itself calls
  // another function.
  const ARG = '(?:[^(),]|\\([^()]*\\))+';

  // DATEDIFF(a, b) -> (julianday(a) - julianday(b))  [day-count difference]
  out = out.replace(
    new RegExp(`\\bdatediff\\s*\\(\\s*(${ARG})\\s*,\\s*(${ARG})\\s*\\)`, 'gi'),
    '(julianday($1) - julianday($2))'
  );

  // DATE_FORMAT(expr, 'fmt') -> strftime('fmt', expr). Only safe because every format
  // string in this dataset uses %Y/%m/%d tokens, which mean the same thing in both.
  out = out.replace(
    new RegExp(`\\bdate_format\\s*\\(\\s*(${ARG})\\s*,\\s*('(?:[^']|'')*')\\s*\\)`, 'gi'),
    "strftime($2, $1)"
  );

  // WEEKDAY(expr): MySQL 0=Monday..6=Sunday: SQLite strftime('%w', expr) is
  // 0=Sunday..6=Saturday. Shift to match MySQL's convention.
  out = out.replace(
    new RegExp(`\\bweekday\\s*\\(\\s*(${ARG})\\s*\\)`, 'gi'),
    "((cast(strftime('%w', $1) as integer) + 6) % 7)"
  );

  // DATE_ADD/ADDDATE(expr, INTERVAL n DAY) -> date(expr, '+' || n || ' day'). n is
  // matched as an arbitrary expression (not just a literal digit) so a variable day
  // count (e.g. `interval rn day`, seen in #2701) still produces a valid runtime
  // modifier string for SQLite's date() rather than a bare "near <ident>" syntax error.
  out = out.replace(
    new RegExp(`\\b(?:date_add|adddate)\\s*\\(\\s*(${ARG})\\s*,\\s*interval\\s+(${ARG})\\s+day\\s*\\)`, 'gi'),
    "date($1, '+' || ($2) || ' day')"
  );
  // DATE_SUB/SUBDATE(expr, INTERVAL n DAY) -> date(expr, '-' || n || ' day')
  out = out.replace(
    new RegExp(`\\b(?:date_sub|subdate)\\s*\\(\\s*(${ARG})\\s*,\\s*interval\\s+(${ARG})\\s+day\\s*\\)`, 'gi'),
    "date($1, '-' || ($2) || ' day')"
  );

  // MONTH(expr) / YEAR(expr) -> extract via strftime, cast to integer so numeric
  // comparisons (`month(x) = 1`) still work.
  out = out.replace(
    new RegExp(`\\bmonth\\s*\\(\\s*(${ARG})\\s*\\)`, 'gi'),
    "cast(strftime('%m', $1) as integer)"
  );
  out = out.replace(
    new RegExp(`\\byear\\s*\\(\\s*(${ARG})\\s*\\)`, 'gi'),
    "cast(strftime('%Y', $1) as integer)"
  );

  // LEFT(expr, n) -> substr(expr, 1, n). MySQL-only string function.
  out = out.replace(
    new RegExp(`\\bleft\\s*\\(\\s*(${ARG})\\s*,\\s*(${ARG})\\s*\\)`, 'gi'),
    'substr($1, 1, $2)'
  );

  // GROUP_CONCAT(... SEPARATOR 'x') -> GROUP_CONCAT(... , 'x'). SQLite 3.44+ (bundled
  // with this project's Python) already supports ORDER BY inside the aggregate call
  // itself, so only the SEPARATOR keyword needs rewriting to a plain second argument.
  out = out.replace(/\bseparator\s+('(?:[^']|'')*')/gi, ', $1');

  // Some scraped answers have a rendered example-output Markdown table glued onto the
  // end of the query text (a scrape artifact — the page's sample-output table got
  // captured along with the SQL). SQL never legitimately starts a line with a bare `|`
  // (that's a `||` concat continuation at most, always doubled), so truncate at the
  // first such line.
  {
    const lines = out.split('\n');
    const tableStart = lines.findIndex((l) => /^\s*\|[^|]/.test(l));
    if (tableStart !== -1) {
      out = lines.slice(0, tableStart).join('\n').trimEnd();
    }
  }

  // Some scraped answers concatenate two alternative solutions with a blank line
  // between them (a scrape artifact, not valid multi-statement SQL) — e.g. "select
  // ... \n\nselect ...". Keep only the first solution. Guarded to never fire on a
  // genuine multi-part query: UNION/INTERSECT/EXCEPT legitimately put each SELECT on
  // its own blank-line-separated block, and a CTE (`WITH x AS (...)`) legitimately has
  // a blank line between its definition and the final SELECT that uses it — trimming
  // there would decapitate the query and leave only the CTE definition (caught via a
  // real dry run against the deployed server: "incomplete input" on ~40 CTE questions).
  if (!/\b(union|intersect|except)\b/i.test(out) && !/^\s*with\b/i.test(out)) {
    const dupSelect = out.match(/\n[ \t]*\n[ \t]*select\b/i);
    if (dupSelect) {
      out = out.slice(0, dupSelect.index);
    }
  }

  return out;
}

// --- order-sensitive grading heuristic (prose-based, see plan for verification) -----

function isOrderSensitive(questionMarkdown) {
  const prose = (questionMarkdown || '').replace(/```[\s\S]*?```/g, ' ');
  const saysAnyOrder = /any order/i.test(prose);
  const saysMustOrder = /sorted|ascending order|descending order|in order of|order the result/i.test(prose);
  return saysMustOrder && !saysAnyOrder;
}

// --- main -----------------------------------------------------------------

const raw = JSON.parse(readFileSync(INPUT_PATH, 'utf8'));

const converted = [];
const skippedKnownBad = [];
const skippedFetchFailed = [];

for (const q of raw) {
  if (q.fetch_status === 'failed') {
    skippedFetchFailed.push({ id: q.id, title: q.title });
    continue;
  }
  if (KNOWN_BAD[q.id]) {
    skippedKnownBad.push({ id: q.id, title: q.title, reason: KNOWN_BAD[q.id] });
    continue;
  }

  const { schema_sql, sample_data_sql } = splitSchemaAndSeed(q.sql_schema || '', q.id);
  const schemaSqlite = applyImportFixups(mysqlToSqlite(schema_sql));
  const seedSqlite = applyImportFixups(mysqlToSqlite(sample_data_sql));
  const answerSqlite = applyImportFixups(mysqlToSqlite(q.answer || ''));

  const concepts = detectConcepts(answerSqlite);
  const orderSensitive = isOrderSensitive(q.question_markdown);

  const description = (q.question_markdown && q.question_markdown.trim())
    ? q.question_markdown
    : '```\n' + (q.sql_schema || '') + '\n```';

  converted.push({
    id: q.id,
    title: q.title,
    description,
    difficulty: (q.difficulty || 'Easy').toLowerCase(),
    schema_sql: schemaSqlite,
    sample_data_sql: seedSqlite,
    correct_answer_query: answerSqlite,
    concepts,
    order_sensitive: orderSensitive,
  });
}

writeFileSync(OUTPUT_PATH, JSON.stringify(converted, null, 2), 'utf8');

console.log(`Converted ${converted.length} questions -> ${path.relative(REPO_ROOT, OUTPUT_PATH)}`);
console.log(`Skipped (fetch_status=failed): ${skippedFetchFailed.length}`);
console.log(`Skipped (known-bad): ${skippedKnownBad.length}`);
for (const s of skippedKnownBad) console.log(`  #${s.id} ${s.title} — ${s.reason}`);

const orderSensitiveList = converted.filter((c) => c.order_sensitive);
console.log(`\norder_sensitive = true for ${orderSensitiveList.length} question(s):`);
for (const c of orderSensitiveList) console.log(`  #${c.id} ${c.title}`);
