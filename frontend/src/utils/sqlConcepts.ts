// Best-effort SQL → concept-tag suggester for the question authoring form.
//
// Given a question's correct answer query, detect which SQL concepts (matching the
// `sql_concepts` taxonomy slugs) it exercises, each with a default "salience" weight.
// This is a heuristic keyword scanner, not a parser: it covers the reliably
// keyword-detectable concepts and deliberately skips the ones that need structural
// analysis (self join, correlated subquery, scalar subquery) — those stay manual.
// The author always reviews/adjusts the result before saving.

export interface DetectedConcept {
  slug: string;
  weight: number;
}

// Default weight per concept, by how central it typically is to a question. Weight
// scales per-concept mastery credit (see CONCEPT_MASTERY_*_DELTA on the backend), so a
// join question shouldn't give the incidental WHERE the same credit as the join itself.
export const CONCEPT_DEFAULT_WEIGHT: Record<string, number> = {
  // 1.0 — distinctive / advanced: what the question is really teaching
  left_join: 1.0,
  right_join: 1.0,
  full_outer_join: 1.0,
  cross_join: 1.0,
  self_join: 1.0,
  multi_table_join: 1.0,
  scalar_subquery: 1.0,
  subquery_in_where: 1.0,
  subquery_in_from: 1.0,
  correlated_subquery: 1.0,
  window_functions: 1.0,
  cte: 1.0,
  union: 1.0,
  intersect_except: 1.0,
  having_clause: 1.0,
  case_expressions: 1.0,
  // 0.7 — core intermediate
  inner_join: 0.7,
  group_by: 0.7,
  aggregate_functions: 0.7,
  order_by: 0.7,
  like_pattern_matching: 0.7,
  null_handling: 0.7,
  // 0.3 — ubiquitous basics (present in almost every query)
  where_clause: 0.3,
  comparison_operators: 0.3,
  logical_operators: 0.3,
  limit: 0.3,
};

// Strip comments and blank out string literals so keywords inside them (e.g. a LIKE
// pattern like '%GROUP BY%') can't false-trigger a detection.
function sanitize(sql: string): string {
  return sql
    .replace(/--[^\n]*/g, ' ') // line comments
    .replace(/\/\*[\s\S]*?\*\//g, ' ') // block comments
    .replace(/'(?:[^']|'')*'/g, "''") // single-quoted string literals
    .replace(/"(?:[^"]|"")*"/g, '""'); // double-quoted identifiers/strings
}

/**
 * Detect the SQL concepts a query exercises, each with its default salience weight.
 * Reliable keyword detections only — see module header.
 */
export function detectConcepts(sql: string): DetectedConcept[] {
  const s = sanitize(sql);
  const found = new Set<string>();

  const has = (re: RegExp) => re.test(s);

  // Filtering / basics
  if (has(/\bWHERE\b/i)) found.add('where_clause');
  if (has(/(<>|!=|<=|>=|<|>)/) || (has(/\bWHERE\b/i) && has(/=/))) {
    found.add('comparison_operators');
  }
  if (has(/\b(AND|OR|NOT)\b/i)) found.add('logical_operators');
  if (has(/\bLIKE\b/i)) found.add('like_pattern_matching');
  if (has(/\bIS\s+(NOT\s+)?NULL\b/i) || has(/\b(COALESCE|IFNULL|NULLIF)\b/i)) {
    found.add('null_handling');
  }

  // Sorting / paging
  if (has(/\bORDER\s+BY\b/i)) found.add('order_by');
  if (has(/\bLIMIT\b/i)) found.add('limit');

  // Joins — classify each JOIN token by its qualifier.
  const joinRe = /\b(LEFT|RIGHT|FULL|CROSS|INNER|NATURAL)?\s*(OUTER\s+)?JOIN\b/gi;
  let joinCount = 0;
  let m: RegExpExecArray | null;
  while ((m = joinRe.exec(s)) !== null) {
    joinCount += 1;
    const kind = (m[1] || '').toUpperCase();
    switch (kind) {
      case 'LEFT':
        found.add('left_join');
        break;
      case 'RIGHT':
        found.add('right_join');
        break;
      case 'FULL':
        found.add('full_outer_join');
        break;
      case 'CROSS':
        found.add('cross_join');
        break;
      default:
        // bare JOIN, INNER JOIN, or NATURAL JOIN → treated as an inner join
        found.add('inner_join');
        break;
    }
  }
  if (joinCount >= 2) found.add('multi_table_join');

  // Aggregation
  if (has(/\b(COUNT|SUM|AVG|MIN|MAX)\s*\(/i)) found.add('aggregate_functions');
  if (has(/\bGROUP\s+BY\b/i)) found.add('group_by');
  if (has(/\bHAVING\b/i)) found.add('having_clause');

  // Subqueries — only meaningful if there's a nested SELECT.
  const selectCount = (s.match(/\bSELECT\b/gi) || []).length;
  if (selectCount > 1) {
    if (has(/\bFROM\s*\(\s*SELECT\b/i)) found.add('subquery_in_from');
    if (has(/\b(IN|EXISTS|ANY|ALL|SOME)\s*\(\s*SELECT\b/i)) found.add('subquery_in_where');
  }

  // Set operations
  if (has(/\bUNION\b/i)) found.add('union');
  if (has(/\b(INTERSECT|EXCEPT)\b/i)) found.add('intersect_except');

  // Advanced
  if (has(/\bOVER\s*\(/i)) found.add('window_functions');
  if (has(/\bWITH\b\s+\w+\s+AS\s*\(/i)) found.add('cte');
  if (has(/\bCASE\b/i)) found.add('case_expressions');

  return Array.from(found).map((slug) => ({
    slug,
    weight: CONCEPT_DEFAULT_WEIGHT[slug] ?? 1.0,
  }));
}
