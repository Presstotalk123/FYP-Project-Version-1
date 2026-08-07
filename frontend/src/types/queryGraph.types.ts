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
  /**
   * A WHERE filter on this column rendered for display, e.g. "< 10" or "= 'x'".
   * Null when the column has no single-column filter.
   */
  filter: string | null;
}

/**
 * A node in the diagram. `entity` renders as a record-box with columns;
 * `junction` renders as a distinct circle/pill (a pure link table) with no rows —
 * its keys live on the edge labels instead.
 */
export interface GraphNode {
  /** Stable id — the table alias when present, else the table name. */
  id: string;
  kind: 'entity' | 'junction';
  /** Real table name shown as the node title. */
  table: string;
  /** Alias as written in the query (e.g. "c"), or null if none. */
  alias: string | null;
  /** A colour derived from the alias/table, tying the node to its label. */
  color: string;
  /** Columns to render (empty for junction nodes). */
  columns: GraphColumn[];
}

/** An undirected join relationship, labelled with the predicate. */
export interface GraphEdge {
  /** Source node id. */
  from: string;
  /** Target node id. */
  to: string;
  /** Human-readable predicate, e.g. "purchase.cID = customer.cID". */
  label: string;
}

export interface QueryGraph {
  nodes: GraphNode[];
  edges: GraphEdge[];
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
