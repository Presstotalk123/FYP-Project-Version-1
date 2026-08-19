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
  GraphGroup,
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

/* ─────────────────────────── expression helpers ──────────────────────── */

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

/** Best-effort render of an expression for HAVING / aggregate display text. */
function exprToString(n: any): string {
  if (!n || typeof n !== 'object') return String(n ?? '');
  switch (n.type) {
    case 'column_ref':
      return (n.table ? `${n.table}.` : '') + colName(n.column);
    case 'aggr_func': {
      const inner =
        n.args?.expr?.type === 'star' ? '*' : exprToString(n.args?.expr);
      return `${n.name}(${inner})`;
    }
    case 'function': {
      const fname = getFunctionName(n) ?? '';
      const args = (n.args?.value ?? []).map(exprToString).join(', ');
      return `${fname}(${args})`;
    }
    case 'star':
      return '*';
    case 'binary_expr':
      return `${exprToString(n.left)} ${n.operator} ${exprToString(n.right)}`;
    default: {
      const lit = literalToString(n);
      return lit ?? '…';
    }
  }
}

function getFunctionName(n: any): string | null {
  const raw = n?.name?.name?.[0]?.value ?? n?.name;
  return typeof raw === 'string' ? raw.toUpperCase() : null;
}

/** Return the nested SELECT ast if `n` wraps a subquery, else null. */
function extractSubselect(n: any): any | null {
  if (!n || typeof n !== 'object') return null;
  if (n.ast && n.ast.type === 'select') return n.ast;
  if (n.type === 'expr_list' && Array.isArray(n.value)) {
    const inner = n.value.find((v: any) => v?.ast?.type === 'select');
    if (inner) return inner.ast;
  }
  return null;
}

/** Recurse AND/OR, invoking `onLeaf` for each non-boolean condition node. */
function walkConditions(expr: any, onLeaf: (leaf: any) => void): void {
  if (!expr || typeof expr !== 'object') return;
  if (expr.type === 'binary_expr') {
    const op = String(expr.operator || '').toUpperCase();
    if (op === 'AND' || op === 'OR') {
      walkConditions(expr.left, onLeaf);
      walkConditions(expr.right, onLeaf);
      return;
    }
  }
  onLeaf(expr);
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

/* ───────────────────────────── scope builder ─────────────────────────── */

const MAX_DEPTH = 6;

interface BuildCtx {
  schema: SchemaInfo;
  nodes: GraphNode[];
  edges: GraphEdge[];
  groups: GraphGroup[];
  notes: string[];
  subCounter: { n: number };
  /** Lowercased CTE name → its cluster's output node id (populated before the root scope). */
  cteOut: Map<string, string>;
}

/** A resolved relation within one scope. */
interface Rel {
  id: string;
  table: string;
  alias: string | null;
}

type Resolver = (tableRef: string | null) => string | null;

/**
 * Build one query scope (the root SELECT or a subquery). Appends nodes/edges/
 * groups into `ctx`. `parentResolve` resolves table refs against enclosing
 * scopes so correlated subquery predicates connect across the cluster boundary.
 * Returns this scope's "output" node id (owner of its first projected column).
 */
function buildScope(
  select: any,
  scopeId: string,
  groupId: string | null,
  ctx: BuildCtx,
  parentResolve: Resolver,
  depth: number,
): string | null {
  const fromList: any[] = Array.isArray(select.from) ? select.from : [];
  const rels: Rel[] = [];
  const refToId = new Map<string, string>();
  // Output nodes of FROM entries that live in another cluster (CTE refs): this
  // scope owns no node for them, but may use one as its own output / unqualified target.
  const externalOuts: string[] = [];

  // ── resolve FROM entries (CTE refs + real tables + derived-table subqueries) ──
  for (const f of fromList) {
    if (f && f.table && ctx.cteOut.has(f.table.toLowerCase())) {
      // A reference to a WITH … CTE: reuse the CTE cluster's output node rather
      // than drawing a duplicate table. Predicates against it link into that cluster.
      const outId = ctx.cteOut.get(f.table.toLowerCase())!;
      const key = (f.as ?? f.table).toLowerCase();
      refToId.set(key, outId);
      refToId.set(f.table.toLowerCase(), outId);
      externalOuts.push(outId);
    } else if (f && f.table) {
      const key = f.as ? f.as : f.table;
      const id = `${scopeId}::${key}`;
      rels.push({ id, table: f.table, alias: f.as ?? null });
      refToId.set(key.toLowerCase(), id);
      refToId.set(f.table.toLowerCase(), id);
    } else {
      const sub = extractSubselect(f) ?? (f?.expr ? extractSubselect(f.expr) : null);
      if (sub && depth < MAX_DEPTH) {
        const subId = `s${++ctx.subCounter.n}`;
        ctx.groups.push({
          id: subId,
          parentGroupId: groupId,
          label: f.as ? `${f.as} (derived table)` : 'derived table',
        });
        const outId = buildScope(sub, subId, subId, ctx, localResolve, depth + 1);
        if (f.as && outId) refToId.set(f.as.toLowerCase(), outId);
      } else if (sub) {
        ctx.notes.push('A deeply nested subquery was not expanded.');
      }
    }
  }

  const relById = new Map(rels.map((r) => [r.id, r]));

  function localResolve(tableRef: string | null): string | null {
    if (tableRef) {
      return refToId.get(tableRef.toLowerCase()) ?? parentResolve(tableRef);
    }
    if (rels.length === 1) return rels[0].id; // unqualified & unambiguous
    // Only source is a single CTE ref → attribute unqualified columns to it.
    if (rels.length === 0 && externalOuts.length === 1) return externalOuts[0];
    return parentResolve(null);
  }

  if (rels.length === 0 && fromList.length === 0) {
    return null;
  }

  // ── per-relation column metadata ──
  const projected = new Map<string, Set<string>>();
  const grouped = new Map<string, Set<string>>();
  const filters = new Map<string, Map<string, string>>();
  const referenced = new Map<string, Set<string>>();
  const projectAll = new Set<string>();
  rels.forEach((r) => {
    projected.set(r.id, new Set());
    grouped.set(r.id, new Set());
    filters.set(r.id, new Map());
    referenced.set(r.id, new Set());
  });

  const isLocal = (id: string | null) => !!id && relById.has(id);

  // ── projections + aggregate outputs (SELECT list) ──
  const aggregates: string[] = [];
  if (select.columns === '*' || select.columns === null) {
    rels.forEach((r) => projectAll.add(r.id));
    if (rels.length) ctx.notes.push('SELECT * — every column is projected.');
  } else if (Array.isArray(select.columns)) {
    for (const c of select.columns) {
      const e = c.expr;
      if (isColumnRef(e)) {
        const name = colName(e.column);
        const id = localResolve(e.table ?? null);
        if (isLocal(id)) {
          if (name === '*') projectAll.add(id!);
          else {
            projected.get(id!)!.add(name.toLowerCase());
            referenced.get(id!)!.add(name);
          }
        } else if (!e.table && !id) {
          ctx.notes.push(`Couldn’t place unqualified column "${name}".`);
        }
      } else if (e && e.type === 'aggr_func') {
        const str = exprToString(e) + (c.as ? ` AS ${c.as}` : '');
        aggregates.push(str);
      } else if (e && e.type === 'select') {
        // Scalar subquery in the SELECT list.
        maybeSubquery(e, null, 'subquery');
      }
    }
  }

  // ── GROUP BY ──
  const groupbyCols: any[] = select.groupby?.columns ?? [];
  for (const g of groupbyCols) {
    if (isColumnRef(g)) {
      const id = localResolve(g.table ?? null);
      const name = colName(g.column);
      if (isLocal(id)) {
        grouped.get(id!)!.add(name.toLowerCase());
        referenced.get(id!)!.add(name);
      }
    }
  }

  // ── HAVING display text (+ any subquery inside it) ──
  const having = select.having ? exprToString(select.having) : null;
  if (select.having) walkConditions(select.having, (leaf) => classifyLeaf(leaf));

  /** Recurse into a subquery and connect it; `outerId` is the outer node (or null). */
  function maybeSubquery(
    subAst: any,
    outerId: string | null,
    label: string,
    outerColumn?: string,
  ): boolean {
    if (!subAst) return false;
    if (depth >= MAX_DEPTH) {
      ctx.notes.push('A deeply nested subquery was not expanded.');
      return true;
    }
    const subId = `s${++ctx.subCounter.n}`;
    // Cluster label is rendered verbatim; append "subquery" unless it's already that word.
    const groupLabel = label.toLowerCase() === 'subquery' ? 'subquery' : `${label} subquery`;
    ctx.groups.push({ id: subId, parentGroupId: groupId, label: groupLabel });
    const childOut = buildScope(subAst, subId, subId, ctx, localResolve, depth + 1);
    const source = outerId ?? rels[0]?.id ?? null;
    if (source && childOut) {
      ctx.edges.push({ from: source, to: childOut, label, kind: 'subquery', fromColumn: outerColumn });
    }
    return true;
  }

  // ── classify one WHERE/ON/HAVING leaf: subquery | join | filter ──
  function classifyLeaf(leaf: any): void {
    if (!leaf || typeof leaf !== 'object') return;

    // EXISTS / NOT EXISTS (a function node, or NOT wrapping one)
    if (leaf.type === 'function') {
      const fn = getFunctionName(leaf);
      if (fn === 'EXISTS' || fn === 'NOT EXISTS') {
        maybeSubquery(extractSubselect(leaf.args), null, fn);
        return;
      }
    }
    if (leaf.type === 'unary_expr' && String(leaf.operator).toUpperCase() === 'NOT') {
      const inner = leaf.expr;
      if (inner?.type === 'function' && getFunctionName(inner) === 'EXISTS') {
        maybeSubquery(extractSubselect(inner.args), null, 'NOT EXISTS');
        return;
      }
    }

    if (leaf.type !== 'binary_expr') return;
    const op = String(leaf.operator || '');
    const opUpper = op.toUpperCase();

    // Subquery on either side (IN / NOT IN / scalar comparison)
    const subRight = extractSubselect(leaf.right);
    const subLeft = extractSubselect(leaf.left);
    if (subRight || subLeft) {
      const outerCol = isColumnRef(leaf.left)
        ? leaf.left
        : isColumnRef(leaf.right)
          ? leaf.right
          : null;
      const outerId = outerCol ? localResolve(outerCol.table ?? null) : null;
      maybeSubquery(subRight ?? subLeft, outerId, opUpper, outerCol ? colName(outerCol.column) : undefined);
      return;
    }

    const leftCol = isColumnRef(leaf.left);
    const rightCol = isColumnRef(leaf.right);

    if (leftCol && rightCol) {
      // column op column → a join (possibly correlated, crossing scopes)
      const lId = localResolve(leaf.left.table ?? null);
      const rId = localResolve(leaf.right.table ?? null);
      if (!lId || !rId || lId === rId) return;
      const lCol = colName(leaf.left.column);
      const rCol = colName(leaf.right.column);
      if (isLocal(lId)) referenced.get(lId)!.add(lCol);
      if (isLocal(rId)) referenced.get(rId)!.add(rCol);
      const lName = relById.get(lId)?.table ?? leaf.left.table ?? '';
      const rName = relById.get(rId)?.table ?? leaf.right.table ?? '';
      const label = `${lName}.${lCol} ${op} ${rName}.${rCol}`;
      pushEdge(lId, rId, label, 'join', lCol, rCol);
    } else if (leftCol || rightCol) {
      // column op literal → a filter
      if (!COMPARATORS.has(opUpper)) return;
      const colNode = leftCol ? leaf.left : leaf.right;
      const valNode = leftCol ? leaf.right : leaf.left;
      const val = literalToString(valNode);
      if (val === null) return;
      const id = localResolve(colNode.table ?? null);
      if (!isLocal(id)) return;
      const name = colName(colNode.column);
      referenced.get(id!)!.add(name);
      const disp = `${op} ${val}`;
      const fmap = filters.get(id!)!;
      const key = name.toLowerCase();
      const existing = fmap.get(key);
      fmap.set(key, existing ? `${existing}, ${disp}` : disp);
    }
  }

  const edgeSeen = new Set<string>();
  function pushEdge(
    a: string,
    b: string,
    label: string,
    kind: 'join' | 'subquery',
    fromColumn?: string,
    toColumn?: string,
  ) {
    const key = [a, b].sort().join('|') + '|' + label;
    if (edgeSeen.has(key)) return;
    edgeSeen.add(key);
    ctx.edges.push({ from: a, to: b, label, kind, fromColumn, toColumn });
  }

  // ── run predicate classification over ON + WHERE ──
  fromList.forEach((f) => f.on && walkConditions(f.on, classifyLeaf));
  if (select.where) walkConditions(select.where, classifyLeaf);

  // ── join degree (local join edges only) for the schemaless heuristic ──
  const neighbours = new Map<string, Set<string>>();
  rels.forEach((r) => neighbours.set(r.id, new Set()));
  ctx.edges.forEach((e) => {
    if (e.kind !== 'join') return;
    if (relById.has(e.from) && relById.has(e.to)) {
      neighbours.get(e.from)!.add(e.to);
      neighbours.get(e.to)!.add(e.from);
    }
  });

  // ── materialise nodes for this scope ──
  for (const r of rels) {
    const sTable = ctx.schema[r.table.toLowerCase()];
    const projSet = projected.get(r.id)!;
    const grpSet = grouped.get(r.id)!;
    const fmap = filters.get(r.id)!;
    const allProjected = projectAll.has(r.id);

    const junction = sTable
      ? isJunctionBySchema(sTable)
      : neighbours.get(r.id)!.size >= 2 && projSet.size === 0 && !allProjected;

    let columns: GraphColumn[] = [];
    if (!junction) {
      const mk = (name: string, pk: boolean): GraphColumn => ({
        name,
        pk,
        projected: allProjected || projSet.has(name.toLowerCase()),
        grouped: grpSet.has(name.toLowerCase()),
        filter: fmap.get(name.toLowerCase()) ?? null,
      });
      if (sTable) {
        columns = sTable.columns.map((c) => mk(c.name, c.pk));
      } else {
        columns = Array.from(referenced.get(r.id)!).map((name) => mk(name, false));
      }
    }

    ctx.nodes.push({
      id: r.id,
      kind: junction ? 'junction' : 'entity',
      table: r.table,
      alias: r.alias,
      color: colorFor(r.alias ?? r.table),
      groupId,
      columns,
    });
  }

  // ── aggregation card for this scope ──
  if (aggregates.length > 0 || having) {
    const aggId = `${scopeId}::__agg`;
    ctx.nodes.push({
      id: aggId,
      kind: 'agg',
      table: 'Aggregation',
      alias: null,
      color: '#6b7280',
      groupId,
      columns: [],
      agg: { aggregates, having },
    });
    // Light layout edge so dagre parks the card beside this scope's tables.
    const anchor = rels[0]?.id;
    if (anchor) ctx.edges.push({ from: anchor, to: aggId, label: '', kind: 'join' });
  }

  // ── output node = owner of the first projected column, else first relation,
  //    else a single CTE-ref output this scope passes through. ──
  const outputRel =
    rels.find((r) => projected.get(r.id)!.size > 0 || projectAll.has(r.id)) ?? rels[0];
  return outputRel ? outputRel.id : (externalOuts[0] ?? null);
}

/* ─────────────────────── UNION / set-op branch chain ─────────────────── */

/** CTE name (node-sql-parser gives an object, occasionally a bare string). */
function cteName(entry: any): string | null {
  const raw = entry?.name?.value ?? entry?.name;
  return typeof raw === 'string' ? raw : null;
}

/** True if any FROM in this select (across branches) names `table` — used for recursion detection. */
function referencesTable(select: any, table: string): boolean {
  const target = table.toLowerCase();
  for (let cur = select; cur; cur = cur._next ?? null) {
    const from: any[] = Array.isArray(cur.from) ? cur.from : [];
    if (from.some((f) => typeof f?.table === 'string' && f.table.toLowerCase() === target)) {
      return true;
    }
  }
  return false;
}

/**
 * Build a query that may be a chain of set operations (`A UNION B EXCEPT C …`).
 * node-sql-parser links branches through `_next`, with each node's `set_op`
 * naming the operator that joins it to the next. A single branch is just an
 * ordinary scope. Multiple branches each become their own "Query N" cluster,
 * wired output-to-output with `setop` edges. Returns the first branch's output.
 */
function buildBranchChain(
  head: any,
  baseId: string,
  parentGroup: string | null,
  ctx: BuildCtx,
  resolve: Resolver,
  depth: number,
): string | null {
  const branches: { ast: any; setOp: string | null }[] = [];
  for (let cur = head; cur; cur = cur._next ?? null) {
    branches.push({ ast: cur, setOp: cur.set_op ?? null });
  }

  if (branches.length <= 1) {
    return buildScope(head, baseId, parentGroup, ctx, resolve, depth);
  }

  const outs: (string | null)[] = branches.map((b, i) => {
    const branchId = `${baseId}_u${i + 1}`;
    ctx.groups.push({ id: branchId, parentGroupId: parentGroup, label: `Query ${i + 1}` });
    return buildScope(b.ast, branchId, branchId, ctx, resolve, depth + 1);
  });

  for (let i = 0; i < branches.length - 1; i++) {
    const from = outs[i];
    const to = outs[i + 1];
    if (from && to) {
      ctx.edges.push({
        from,
        to,
        label: (branches[i].setOp ?? 'union').toUpperCase(),
        kind: 'setop',
      });
    }
  }

  return outs.find((o) => o) ?? null;
}

/** Remove clusters holding neither a node nor a surviving child cluster (repeated to a fixpoint). */
function pruneEmptyGroups(groups: GraphGroup[], nodes: GraphNode[]): GraphGroup[] {
  const nodeGroupIds = new Set(nodes.map((n) => n.groupId).filter(Boolean));
  let kept = groups;
  for (;;) {
    const parentIds = new Set(kept.map((g) => g.parentGroupId).filter(Boolean));
    const next = kept.filter((g) => nodeGroupIds.has(g.id) || parentIds.has(g.id));
    if (next.length === kept.length) return next;
    kept = next;
  }
}

/* ───────────────────────────── public entry ──────────────────────────── */

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

  const ctx: BuildCtx = {
    schema,
    nodes: [],
    edges: [],
    groups: [],
    notes: [],
    subCounter: { n: 0 },
    cteOut: new Map(),
  };

  // ── CTE pre-pass: build each WITH … as its own top-level cluster, in order,
  //    so a later CTE can reference an earlier one via ctx.cteOut. ──
  const cteList: any[] = Array.isArray(ast.with) ? ast.with : [];
  for (const entry of cteList) {
    const name = cteName(entry);
    const body = entry?.stmt?.ast;
    if (!name || !body) continue;
    // A self-reference (recursive CTE) can't resolve to its own cluster yet;
    // it falls through to a plain table node. Flag it so the diagram isn't misread.
    if (referencesTable(body, name)) {
      ctx.notes.push(`Recursive CTE "${name}" — its self-reference is shown as a table.`);
    }
    const cteId = `cte_${name.toLowerCase()}`;
    ctx.groups.push({ id: cteId, parentGroupId: null, label: `${name} (CTE)` });
    const outId = buildBranchChain(body, cteId, cteId, ctx, () => null, 1);
    if (outId) ctx.cteOut.set(name.toLowerCase(), outId);
  }

  buildBranchChain(ast, 'root', null, ctx, () => null, 0);

  if (ctx.nodes.length === 0) {
    return { error: 'This query couldn’t be diagrammed.' };
  }

  // Drop clusters that ended up empty (e.g. a CTE that only passes another CTE
  // through), keeping any that still hold nodes or surviving child clusters.
  const groups = pruneEmptyGroups(ctx.groups, ctx.nodes);

  const graph: QueryGraph = {
    nodes: ctx.nodes,
    edges: ctx.edges,
    groups,
    notes: Array.from(new Set(ctx.notes)),
  };
  return graph;
}
