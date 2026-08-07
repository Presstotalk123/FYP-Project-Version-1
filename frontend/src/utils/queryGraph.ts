/* eslint-disable @typescript-eslint/no-explicit-any */
// The SQL AST from node-sql-parser is loosely typed and varies across query
// shapes, so this module works with `any` internally. The exported surface
// (buildQueryGraph → QueryGraphResult) is fully typed.

import { Parser } from 'node-sql-parser';
import {
  QueryGraph,
  QueryGraphResult,
  GraphNode,
  GraphEdge,
  GraphColumn,
  SchemaInfo,
  SchemaTable,
} from '@/types/queryGraph.types';

/* ────────────────────────── identifier helpers ────────────────────────── */

/** Strip SQL identifier quoting: "x", `x`, [x] → x. */
function unquote(id: string): string {
  return id.trim().replace(/^["`[]/, '').replace(/["`\]]$/, '');
}

/** node-sql-parser sometimes returns a column name as a string, sometimes an object. */
function colName(col: any): string {
  if (typeof col === 'string') return col;
  if (col && typeof col === 'object') {
    if (typeof col.column === 'string') return col.column;
    if (col.expr && typeof col.expr.value === 'string') return col.expr.value;
  }
  return String(col);
}

/* ─────────────────────────── schema (DDL) parsing ─────────────────────── */

/**
 * Parse one or more `CREATE TABLE` statements into a normalised SchemaInfo.
 * Uses a focused hand-parser rather than the AST: SQLite DDL FK/PK forms are
 * simple and this stays robust across parser versions. Returns {} when no DDL.
 */
export function parseSchema(ddl?: string | null): SchemaInfo {
  const schema: SchemaInfo = {};
  if (!ddl || !ddl.trim()) return schema;

  const re = /create\s+table\s+(?:if\s+not\s+exists\s+)?([`"[]?\w+[`"\]]?)\s*\(/gi;
  let m: RegExpExecArray | null;
  while ((m = re.exec(ddl)) !== null) {
    const tableName = unquote(m[1]);
    // Match the body from the "(" the regex just consumed to its closing ")".
    const bodyStart = re.lastIndex;
    let depth = 1;
    let i = bodyStart;
    for (; i < ddl.length && depth > 0; i++) {
      if (ddl[i] === '(') depth++;
      else if (ddl[i] === ')') depth--;
    }
    const body = ddl.slice(bodyStart, i - 1);
    schema[tableName.toLowerCase()] = parseTableBody(tableName, body);
    re.lastIndex = i;
  }
  return schema;
}

/** Split a CREATE TABLE body on top-level commas (ignoring commas inside parens). */
function splitTopLevel(body: string): string[] {
  const parts: string[] = [];
  let depth = 0;
  let cur = '';
  for (const ch of body) {
    if (ch === '(') depth++;
    else if (ch === ')') depth--;
    if (ch === ',' && depth === 0) {
      parts.push(cur);
      cur = '';
    } else {
      cur += ch;
    }
  }
  if (cur.trim()) parts.push(cur);
  return parts;
}

function parseTableBody(name: string, body: string): SchemaTable {
  const table: SchemaTable = { name, columns: [], foreignKeys: [] };

  for (const rawPart of splitTopLevel(body)) {
    let part = rawPart.trim();
    if (!part) continue;
    // Drop a leading "CONSTRAINT <name>" so PK/FK constraints match uniformly.
    part = part.replace(/^constraint\s+[`"[]?\w+[`"\]]?\s+/i, '');
    const upper = part.toUpperCase();

    // Table-level FOREIGN KEY (a,..) REFERENCES t (b,..)
    const tfk = part.match(
      /^foreign\s+key\s*\(([^)]+)\)\s*references\s+([`"[]?\w+[`"\]]?)\s*\(([^)]+)\)/i,
    );
    if (tfk) {
      const cols = tfk[1].split(',').map((c) => unquote(c));
      const refCols = tfk[3].split(',').map((c) => unquote(c));
      const refTable = unquote(tfk[2]);
      cols.forEach((c, idx) =>
        table.foreignKeys.push({
          column: c,
          refTable,
          refColumn: refCols[idx] ?? refCols[0],
        }),
      );
      continue;
    }

    // Table-level PRIMARY KEY (a, b)
    const tpk = part.match(/^primary\s+key\s*\(([^)]+)\)/i);
    if (tpk) {
      const pkCols = tpk[1].split(',').map((c) => unquote(c).toLowerCase());
      table.columns.forEach((c) => {
        if (pkCols.includes(c.name.toLowerCase())) c.pk = true;
      });
      continue;
    }

    // Skip other table-level constraints.
    if (/^(unique|check|primary\s+key|foreign\s+key)\b/i.test(part)) continue;

    // Otherwise: a column definition. First token is the column name.
    const nameMatch = part.match(/^([`"[]?[\w$]+[`"\]]?)/);
    if (!nameMatch) continue;
    const columnName = unquote(nameMatch[1]);
    const pk = /\bprimary\s+key\b/i.test(upper);
    table.columns.push({ name: columnName, pk });

    // Inline REFERENCES t (b)
    const ifk = part.match(
      /\breferences\s+([`"[]?\w+[`"\]]?)\s*\(\s*([`"[]?\w+[`"\]]?)\s*\)/i,
    );
    if (ifk) {
      table.foreignKeys.push({
        column: columnName,
        refTable: unquote(ifk[1]),
        refColumn: unquote(ifk[2]),
      });
    }
  }

  return table;
}

/* ─────────────────────────── expression walking ──────────────────────── */

const COMPARATORS = new Set(['=', '<', '>', '<=', '>=', '!=', '<>', 'LIKE', 'IS']);

function isColumnRef(n: any): boolean {
  return n && n.type === 'column_ref';
}

/** Format a literal AST node for display, or null if it isn't a simple value. */
function literalToString(n: any): string | null {
  if (!n || typeof n !== 'object') return null;
  switch (n.type) {
    case 'number':
      return String(n.value);
    case 'bool':
      return n.value ? 'TRUE' : 'FALSE';
    case 'null':
      return 'NULL';
    case 'single_quote_string':
    case 'string':
    case 'double_quote_string':
      return `'${n.value}'`;
    default:
      return null;
  }
}

interface RawPredicate {
  op: string;
  left: any;
  right: any;
}

/** Collect leaf comparison predicates from an ON/WHERE expression tree. */
function collectPredicates(expr: any, out: RawPredicate[]): void {
  if (!expr || typeof expr !== 'object') return;
  if (expr.type === 'binary_expr') {
    const op = String(expr.operator || '').toUpperCase();
    if (op === 'AND' || op === 'OR') {
      collectPredicates(expr.left, out);
      collectPredicates(expr.right, out);
      return;
    }
    out.push({ op: expr.operator, left: expr.left, right: expr.right });
  }
}

/* ─────────────────────────── junction detection ──────────────────────── */

function isJunctionBySchema(table: SchemaTable | undefined): boolean {
  if (!table) return false;
  const fkTargets = new Set(table.foreignKeys.map((f) => f.refTable.toLowerCase()));
  if (fkTargets.size < 2) return false;
  const fkCols = new Set(table.foreignKeys.map((f) => f.column.toLowerCase()));
  const nonKeyCols = table.columns.filter(
    (c) => !c.pk && !fkCols.has(c.name.toLowerCase()),
  );
  return nonKeyCols.length <= 1;
}

/* ─────────────────────────────── palette ─────────────────────────────── */

// Distinct, legible hues that read on both light and dark surfaces.
const PALETTE = ['#7c3aed', '#0891b2', '#059669', '#d97706', '#db2777', '#4f46e5', '#0d9488'];

function colorFor(key: string): string {
  let h = 0;
  for (let i = 0; i < key.length; i++) h = (h * 31 + key.charCodeAt(i)) >>> 0;
  return PALETTE[h % PALETTE.length];
}

/* ───────────────────────────── main builder ──────────────────────────── */

export function buildQueryGraph(sql: string, schemaSql?: string | null): QueryGraphResult {
  if (!sql || !sql.trim()) {
    return { error: 'Type a query to see its structure.' };
  }

  const schema = parseSchema(schemaSql);

  let ast: any;
  try {
    const parsed = new Parser().astify(sql, { database: 'sqlite' });
    ast = Array.isArray(parsed) ? parsed[0] : parsed;
  } catch {
    return { error: "Couldn't parse this query — check the SQL syntax." };
  }

  if (!ast || ast.type !== 'select') {
    return { error: 'Only SELECT queries can be diagrammed.' };
  }
  if (ast.with) {
    return { error: 'CTEs (WITH …) aren’t supported yet.' };
  }
  if (ast.set_op || ast._next) {
    return { error: 'UNION / set operations aren’t supported yet.' };
  }
  const fromList: any[] = Array.isArray(ast.from) ? ast.from : [];
  if (fromList.length === 0) {
    return { error: 'This query has no tables to diagram.' };
  }
  if (fromList.some((f) => !f || !f.table)) {
    return { error: 'Subqueries in FROM aren’t supported yet.' };
  }

  const notes: string[] = [];

  // Relations: id is the alias when present, else the table name.
  interface Rel {
    id: string;
    table: string;
    alias: string | null;
  }
  const rels: Rel[] = fromList.map((f) => ({
    id: f.as ? f.as : f.table,
    table: f.table,
    alias: f.as ?? null,
  }));
  const relById = new Map(rels.map((r) => [r.id, r]));
  // alias-or-table (as written in the query) → relation id
  const refToId = new Map<string, string>();
  rels.forEach((r) => {
    refToId.set(r.id.toLowerCase(), r.id);
    refToId.set(r.table.toLowerCase(), r.id);
  });

  function resolveRef(tableRef: string | null): string | null {
    if (tableRef) return refToId.get(tableRef.toLowerCase()) ?? null;
    if (rels.length === 1) return rels[0].id; // unqualified & unambiguous
    return null;
  }

  // Per-relation collected column metadata.
  const projected = new Map<string, Set<string>>();
  const filters = new Map<string, Map<string, string>>();
  const referenced = new Map<string, Set<string>>(); // columns seen (for schemaless boxes)
  rels.forEach((r) => {
    projected.set(r.id, new Set());
    filters.set(r.id, new Map());
    referenced.set(r.id, new Set());
  });
  const projectAll = new Set<string>(); // relation ids with SELECT * / t.*

  /* ── projections ── */
  if (ast.columns === '*' || ast.columns === null) {
    rels.forEach((r) => projectAll.add(r.id));
    notes.push('SELECT * — every column is projected.');
  } else if (Array.isArray(ast.columns)) {
    for (const c of ast.columns) {
      const e = c.expr;
      if (isColumnRef(e)) {
        const name = colName(e.column);
        const id = resolveRef(e.table ?? null);
        if (id) {
          if (name === '*') projectAll.add(id);
          else {
            projected.get(id)!.add(name.toLowerCase());
            referenced.get(id)!.add(name);
          }
        } else if (!e.table) {
          notes.push(`Couldn’t place unqualified column "${name}".`);
        }
      }
      // Aggregates / expressions are not attributed to a single column.
    }
  }

  /* ── predicates (joins + filters) from every ON and the WHERE ── */
  const preds: RawPredicate[] = [];
  fromList.forEach((f) => f.on && collectPredicates(f.on, preds));
  if (ast.where) collectPredicates(ast.where, preds);

  const edges: GraphEdge[] = [];
  const edgeSeen = new Set<string>();

  for (const p of preds) {
    const opUpper = String(p.op || '').toUpperCase();
    const leftIsCol = isColumnRef(p.left);
    const rightIsCol = isColumnRef(p.right);

    if (leftIsCol && rightIsCol) {
      // column = column → a join between two relations
      const lId = resolveRef(p.left.table ?? null);
      const rId = resolveRef(p.right.table ?? null);
      if (!lId || !rId || lId === rId) continue;
      const lCol = colName(p.left.column);
      const rCol = colName(p.right.column);
      referenced.get(lId)!.add(lCol);
      referenced.get(rId)!.add(rCol);
      const lRel = relById.get(lId)!;
      const rRel = relById.get(rId)!;
      const label = `${lRel.table}.${lCol} ${p.op} ${rRel.table}.${rCol}`;
      const key = [lId, rId].sort().join('|') + '|' + label;
      if (!edgeSeen.has(key)) {
        edgeSeen.add(key);
        edges.push({ from: lId, to: rId, label });
      }
    } else if (leftIsCol || rightIsCol) {
      // column <op> value → a filter
      const colNode = leftIsCol ? p.left : p.right;
      const valNode = leftIsCol ? p.right : p.left;
      if (!COMPARATORS.has(opUpper)) continue;
      const val = literalToString(valNode);
      if (val === null) continue;
      const id = resolveRef(colNode.table ?? null);
      if (!id) continue;
      const name = colName(colNode.column);
      referenced.get(id)!.add(name);
      const disp = `${p.op} ${val}`;
      const fmap = filters.get(id)!;
      const existing = fmap.get(name.toLowerCase());
      fmap.set(name.toLowerCase(), existing ? `${existing}, ${disp}` : disp);
    }
  }

  /* ── join degree (distinct neighbours) for the schemaless heuristic ── */
  const neighbours = new Map<string, Set<string>>();
  rels.forEach((r) => neighbours.set(r.id, new Set()));
  edges.forEach((e) => {
    neighbours.get(e.from)!.add(e.to);
    neighbours.get(e.to)!.add(e.from);
  });

  /* ── build nodes ── */
  const nodes: GraphNode[] = rels.map((r) => {
    const sTable = schema[r.table.toLowerCase()];
    const projSet = projected.get(r.id)!;
    const fmap = filters.get(r.id)!;
    const allProjected = projectAll.has(r.id);

    // Junction classification.
    const junction = sTable
      ? isJunctionBySchema(sTable)
      : neighbours.get(r.id)!.size >= 2 && projSet.size === 0 && !allProjected;

    let columns: GraphColumn[] = [];
    if (!junction) {
      if (sTable) {
        columns = sTable.columns.map((c) => ({
          name: c.name,
          pk: c.pk,
          projected: allProjected || projSet.has(c.name.toLowerCase()),
          filter: fmap.get(c.name.toLowerCase()) ?? null,
        }));
      } else {
        // No schema: show only the columns the query actually references.
        const seen = referenced.get(r.id)!;
        columns = Array.from(seen).map((name) => ({
          name,
          pk: false,
          projected: allProjected || projSet.has(name.toLowerCase()),
          filter: fmap.get(name.toLowerCase()) ?? null,
        }));
      }
    }

    return {
      id: r.id,
      kind: junction ? 'junction' : 'entity',
      table: r.table,
      alias: r.alias,
      color: colorFor(r.alias ?? r.table),
      columns,
    };
  });

  const graph: QueryGraph = { nodes, edges, notes };
  return graph;
}
