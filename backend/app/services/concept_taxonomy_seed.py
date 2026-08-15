"""Static, hand-authored SQL concept taxonomy + prerequisite DAG.

This is a one-time curriculum artifact (not LLM-generated). ``seed_taxonomy`` is
idempotent: it inserts any missing concepts and prerequisite edges and leaves
existing rows untouched, so it is safe to re-run after editing this file.

The exact concept list and edges are a curriculum decision — staff should sanity-
check them before this is seeded in production.
"""
from sqlalchemy.orm import Session

from app.models.sql_concept import SqlConcept
from app.models.sql_concept_prerequisite import SqlConceptPrerequisite

# (slug, display_name, category, description)
CONCEPTS = [
    # filtering
    ("where_clause", "WHERE clause", "filtering", "Restricting rows with a WHERE condition."),
    ("comparison_operators", "Comparison operators", "filtering", "=, <>, <, >, <=, >= in predicates."),
    ("logical_operators", "Logical operators", "filtering", "Combining conditions with AND / OR / NOT."),
    ("like_pattern_matching", "LIKE pattern matching", "filtering", "Wildcard matching with LIKE and %/_ ."),
    ("null_handling", "NULL handling", "filtering", "IS NULL / IS NOT NULL and three-valued logic."),
    # sorting / limiting
    ("order_by", "ORDER BY", "sorting", "Sorting result rows ascending/descending."),
    ("limit", "LIMIT", "sorting", "Restricting the number of returned rows."),
    # joins
    ("inner_join", "INNER JOIN", "joins", "Matching rows across tables on a join condition."),
    ("left_join", "LEFT JOIN", "joins", "Keeping unmatched left-table rows."),
    ("right_join", "RIGHT JOIN", "joins", "Keeping unmatched right-table rows."),
    ("full_outer_join", "FULL OUTER JOIN", "joins", "Keeping unmatched rows from both sides."),
    ("self_join", "Self join", "joins", "Joining a table to itself."),
    ("cross_join", "CROSS JOIN", "joins", "Cartesian product of two tables."),
    ("multi_table_join", "Multi-table join", "joins", "Joining three or more tables."),
    # aggregation
    ("aggregate_functions", "Aggregate functions", "aggregation", "COUNT, SUM, AVG, MIN, MAX."),
    ("group_by", "GROUP BY", "aggregation", "Grouping rows to aggregate per group."),
    ("having_clause", "HAVING clause", "aggregation", "Filtering groups after aggregation."),
    # subqueries
    ("scalar_subquery", "Scalar subquery", "subqueries", "A subquery returning a single value."),
    ("subquery_in_where", "Subquery in WHERE", "subqueries", "IN / EXISTS / comparison subqueries."),
    ("subquery_in_from", "Subquery in FROM", "subqueries", "Derived tables in the FROM clause."),
    ("correlated_subquery", "Correlated subquery", "subqueries", "A subquery referencing the outer query."),
    # set operations
    ("union", "UNION", "set_operations", "Combining result sets with UNION / UNION ALL."),
    ("intersect_except", "INTERSECT / EXCEPT", "set_operations", "Set intersection and difference."),
    # advanced
    ("window_functions", "Window functions", "advanced", "OVER(...) analytic functions."),
    ("cte", "Common table expressions", "advanced", "WITH clauses / named subqueries."),
    ("case_expressions", "CASE expressions", "advanced", "Conditional expressions with CASE."),
]

# (concept_slug, prerequisite_slug)
PREREQUISITES = [
    ("comparison_operators", "where_clause"),
    ("logical_operators", "where_clause"),
    ("like_pattern_matching", "where_clause"),
    ("null_handling", "where_clause"),
    ("having_clause", "group_by"),
    ("group_by", "aggregate_functions"),
    ("left_join", "inner_join"),
    ("right_join", "inner_join"),
    ("full_outer_join", "inner_join"),
    ("self_join", "inner_join"),
    ("multi_table_join", "inner_join"),
    ("subquery_in_where", "scalar_subquery"),
    ("subquery_in_from", "scalar_subquery"),
    ("correlated_subquery", "scalar_subquery"),
    ("cte", "scalar_subquery"),
    ("window_functions", "aggregate_functions"),
    ("intersect_except", "union"),
]


def seed_taxonomy(db: Session) -> int:
    """Insert any missing concepts and prerequisite edges. Idempotent.

    Returns the number of concepts present after seeding.
    """
    slug_to_id = {c.slug: c.id for c in db.query(SqlConcept).all()}

    for slug, display_name, category, description in CONCEPTS:
        if slug not in slug_to_id:
            concept = SqlConcept(
                slug=slug, display_name=display_name,
                category=category, description=description, is_active=1,
            )
            db.add(concept)
            db.flush()  # assign id
            slug_to_id[slug] = concept.id

    existing_edges = {
        (e.concept_id, e.prerequisite_concept_id)
        for e in db.query(SqlConceptPrerequisite).all()
    }
    for concept_slug, prereq_slug in PREREQUISITES:
        cid = slug_to_id.get(concept_slug)
        pid = slug_to_id.get(prereq_slug)
        if cid is None or pid is None:
            continue
        if (cid, pid) not in existing_edges:
            db.add(SqlConceptPrerequisite(concept_id=cid, prerequisite_concept_id=pid))
            existing_edges.add((cid, pid))

    db.commit()
    return len(slug_to_id)
