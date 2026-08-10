/**
 * Types for the query-structure visualiser (the "Diagram" tab).
 *
 * A QueryGraph is a small, render-ready model derived purely in the browser from
 * the student's SQL (parsed with node-sql-parser) plus, when available, the
 * database schema DDL (for foreign keys / full column lists / junction detection).
 * The renderer (QueryGraph.tsx) never touches SQL — it only draws this model.
 */

/** A column as it should appear inside an entity node. */
export interface GraphColumn {
  name: string;
  /** True if the column is a primary key (from schema, when known). */
  pk: boolean;
  /** True if the column appears in the SELECT list → emphasised in the diagram. */
  projected: boolean;
  /** True if the column appears in GROUP BY → shown with a "grouped" badge. */
  grouped: boolean;
  /**
   * A WHERE filter on this column rendered for display, e.g. "< 10" or "= 'x'".
   * Null when the column has no single-column filter.
   */
  filter: string | null;
}

/**
 * A node in the diagram.
 * - `entity`   — a record-box with columns.
 * - `junction` — a distinct circle/pill (a pure link table) with no rows; its keys
 *                live on the edge labels instead.
 * - `agg`      — a small card summarising a query scope's aggregation (GROUP BY
 *                outputs + HAVING). Carries `agg`, ignores `columns`.
 */
export interface GraphNode {
  /** Stable, scope-namespaced id (e.g. "root::c", "s1::orders"). */
  id: string;
  kind: 'entity' | 'junction' | 'agg';
  /** Real table name shown as the node title (label text for agg cards). */
  table: string;
  /** Alias as written in the query (e.g. "c"), or null if none. */
  alias: string | null;
  /** A colour derived from the alias/table, tying the node to its label. */
  color: string;
  /** The subquery scope this node belongs to; null = root scope. */
  groupId: string | null;
  /** Columns to render (empty for junction/agg nodes). */
  columns: GraphColumn[];
  /** Aggregation payload — present only for `kind === 'agg'`. */
  agg?: { aggregates: string[]; having: string | null };
}

/** An edge — either a join (solid) or a subquery link (dashed). */
export interface GraphEdge {
  /** Source node id. */
  from: string;
  /** Target node id. */
  to: string;
  /** Human-readable label, e.g. "purchase.cID = customer.cID" or "NOT IN". */
  label: string;
  kind: 'join' | 'subquery';
  /** Column on the `from` node the edge should anchor to (for row-aligned routing). */
  fromColumn?: string;
  /** Column on the `to` node the edge should anchor to. */
  toColumn?: string;
}

/** A subquery scope, drawn as a shaded cluster containing its nodes. */
export interface GraphGroup {
  /** Scope id (e.g. "s1"). */
  id: string;
  /** Parent scope id, or null when nested directly under the root query. */
  parentGroupId: string | null;
  /** Label shown on the cluster, e.g. "NOT IN" / "EXISTS" / "subquery". */
  label: string;
}

export interface QueryGraph {
  nodes: GraphNode[];
  edges: GraphEdge[];
  /** Subquery clusters (empty for a flat single-level query). */
  groups: GraphGroup[];
  /**
   * Non-fatal notes surfaced to the user (e.g. "SELECT * — showing all columns",
   * "unqualified column ignored"). Never blocks rendering.
   */
  notes: string[];
}

/** Returned by buildQueryGraph when the query can't be diagrammed. */
export interface QueryGraphError {
  error: string;
}

export type QueryGraphResult = QueryGraph | QueryGraphError;

export function isQueryGraphError(r: QueryGraphResult): r is QueryGraphError {
  return (r as QueryGraphError).error !== undefined;
}

/** Normalised schema derived from DDL — used for FK/junction detection. */
export interface SchemaTable {
  name: string;
  columns: { name: string; pk: boolean }[];
  /** Foreign keys declared on this table. */
  foreignKeys: { column: string; refTable: string; refColumn: string }[];
}

export type SchemaInfo = Record<string, SchemaTable>;
