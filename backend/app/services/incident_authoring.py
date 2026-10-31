"""Conservative source adapters, AST fault templates and reproducible validation."""
from __future__ import annotations

import html
import re
import time

import sqlglot
from sqlglot import exp

from app.config import settings
from app.core.competition_executor import digest, execute, parse_select
from app.core.competition_comparator import matches
from app.schemas.competition import IncidentDocument

PARSER_VERSION = f"rescue-1/sqlglot-{sqlglot.__version__}"
APPROVED_TEMPLATES = {name + ":v1" for name in ("left_to_inner", "remove_distinct", "invert_exists", "count_all", "wrong_join_key", "reverse_comparison", "left_join_where")}


def normalise_source(raw: dict) -> tuple[dict, list[str]]:
    """No executable source text is trusted, including a nominal fetch success."""
    diagnostics = []
    snapshot = {"title": str(raw.get("title", "Untitled"))[:255], "external_id": str(raw.get("id", raw.get("external_id", "")))[:100],
                "original": raw, "parser_version": PARSER_VERSION}
    schema = raw.get("sql_schema", "")
    if raw.get("schema_sql") is not None:
        ddl, seeds = raw["schema_sql"], raw.get("sample_data_sql", "")
        schema = ddl + "\n" + seeds if isinstance(ddl, str) and isinstance(seeds, str) else None
    answer = raw.get("correct_answer_query") or raw.get("answer") or ""
    try:
        if not schema or not answer:
            raise ValueError("Missing schema or reference SQL; instructor repair is required.")
        if not isinstance(schema, str) or not isinstance(answer, str):
            raise ValueError("Schema and reference SQL must be text fields.")
        # MySQL '#' comments must not remove hashtags inside string literals.
        nodes = [n for n in sqlglot.parse(schema, read="mysql") if n is not None]
        ddl, seed = [], []
        for node in nodes:
            if isinstance(node, exp.Create) and str(node.args.get("kind", "")).upper() in {"TABLE", "INDEX"}:
                ddl.append(node.sql(dialect="sqlite", unsupported_level=sqlglot.ErrorLevel.RAISE))
            elif isinstance(node, exp.Insert):
                seed.append(node.sql(dialect="sqlite", unsupported_level=sqlglot.ErrorLevel.RAISE))
            elif isinstance(node, exp.TruncateTable):
                continue  # Each fixture starts empty.
            else:
                raise ValueError("Unsupported source setup statement; review it manually.")
        references = [n for n in sqlglot.parse(answer, read="mysql") if n is not None]
        if len(references) != 1:
            raise ValueError("Select one unambiguous reference query before adaptation.")
        reference = references[0].sql(dialect="sqlite", unsupported_level=sqlglot.ErrorLevel.RAISE)
        parse_select(reference)
        snapshot.update(schema_sql=";\n".join(ddl) + ";", seed_sql=";\n".join(seed) + (";" if seed else ""), reference_query=reference)
        result = execute(snapshot["schema_sql"], snapshot["seed_sql"], reference)
        if not result["success"]:
            raise ValueError(result["error"])
        snapshot["sample_reference_output"] = {"columns": result["columns"], "rows": result["rows"]}
        description = raw.get("question_markdown", raw.get("description", ""))
        snapshot["example_output"] = extract_example(description) if isinstance(description, str) else None
        snapshot["declared_tables"] = [t.name for n in nodes if isinstance(n, exp.Create) and (t := n.find(exp.Table))]
        if snapshot["example_output"] is None:
            diagnostics.append("Expected example rows need instructor extraction/confirmation.")
        elif not matches(result, snapshot["example_output"]):
            diagnostics.append("Reference and extracted example differ; check aliases, typing and source correctness.")
        diagnostics.append("Keys and relationships described only in prose are not enforced by extracted DDL.")
    except (ValueError, TypeError, RecursionError, sqlglot.errors.SqlglotError) as exc:
        diagnostics.append(str(exc)[:1000])
        snapshot["eligible"] = False
    else:
        snapshot["eligible"] = True
    return snapshot, diagnostics


def extract_example(markdown: str):
    match = re.search(r"Output\s*:\s*(.*?)(?:Explanation\s*:|\Z)", html.unescape(markdown), flags=re.I | re.S)
    if not match:
        return None
    lines = [line.strip() for line in match.group(1).splitlines() if line.strip().startswith("|")]
    if not lines:
        return None
    cells = lambda line: [s.strip() for s in line.strip("|").split("|")]
    columns = cells(lines[0])
    rows = []
    for line in lines[1:]:
        values = cells(line)
        if all(re.fullmatch(r"[-: ]+", v or "-") for v in values):
            continue
        if len(values) != len(columns):
            return None
        row = []
        for value in values:
            if value.lower() == "null":
                row.append(None)
            elif re.fullmatch(r"-?\d+", value):
                row.append(int(value))
            elif re.fullmatch(r"-?\d+\.\d+", value):
                row.append(float(value))
            else:
                row.append(value)
        rows.append(row)
    return {"columns": columns, "rows": rows}


def mutate(reference: str, template: str) -> str:
    node = parse_select(reference).copy()
    if template == "left_to_inner":
        join = next((j for j in node.find_all(exp.Join) if j.side == "LEFT"), None)
        if join is None:
            raise ValueError("This template requires a LEFT JOIN that should retain unmatched records.")
        join.set("side", None)
        join.set("kind", "INNER")
    elif template == "remove_distinct":
        target = next((s for s in node.find_all(exp.Select) if s.args.get("distinct")), None)
        if target is None:
            raise ValueError("This template requires SELECT DISTINCT and a duplicate-sensitive business rule.")
        target.set("distinct", None)
    elif template == "invert_exists":
        target = node.find(exp.Exists)
        if target is None:
            raise ValueError("This template requires EXISTS/NOT EXISTS and matched/unmatched witness records.")
        if isinstance(target.parent, exp.Not):
            target.parent.replace(target.copy())
        else:
            target.replace(exp.Not(this=target.copy()))
    elif template == "count_all":
        target = next((n for n in node.find_all(exp.Count) if isinstance(n.this, exp.Column)), None)
        if target is None:
            raise ValueError("This template requires COUNT(nullable_column) and a NULL witness.")
        target.set("this", exp.Star())
    else:
        raise ValueError("Unknown approved fault template.")
    return node.sql(dialect="sqlite")


def adaptation(snapshot: dict, template: str, complaint: str, business_rules: str) -> dict:
    if not snapshot.get("eligible"):
        raise ValueError("Repair the source diagnostics before adapting it.")
    faulty = mutate(snapshot["reference_query"], template)
    tables = snapshot["declared_tables"]
    if not tables:
        raise ValueError("No source table was identified.")
    count = f'SELECT COUNT(*) AS record_count FROM "{tables[0].replace(chr(34), chr(34) * 2)}"'
    components = [
        {"id": "report", "label": "Directory report", "purpose": "Populates the report shown to application users.", "query": faulty, "reference_query": snapshot["reference_query"]},
        {"id": "records", "label": "Record summary", "purpose": "Displays the number of records in the primary table.", "query": count, "reference_query": count},
    ]
    outputs = {}
    for c in components:
        result = execute(snapshot["schema_sql"], snapshot["seed_sql"], c["reference_query"])
        if not result["success"]:
            raise ValueError(result["error"])
        outputs[c["id"]] = {"columns": result["columns"], "rows": result["rows"]}
    # These placeholder fixtures intentionally cannot pass publication validation:
    # staff must author independent counterexamples and confirm the oracle.
    scenarios = [{"id": name, "label": label, "visible": i == 0, "seed_sql": snapshot["seed_sql"], "approved_outputs": outputs}
                 for i, (name, label) in enumerate((("visible", "Source example"), ("witness", "Author a distinct defect witness"), ("edge", "Author a distinct boundary case")))]
    return {"title": snapshot["title"], "topic": "joins", "difficulty": "easy", "complaint": complaint, "business_rules": business_rules,
            "schema_sql": snapshot["schema_sql"], "components": components, "culprit_component": "report", "fault_template": template + ":v1",
            "fault_cause": "Instructor: describe the semantic cause and required witness before approval.",
            "checkpoints": ["Compare the primary table records with the affected report.", "Inspect how unmatched or duplicate records are handled."],
            "scenarios": scenarios, "oracle_confirmed": False, "alternative_repairs": []}


def validate_document(value: dict) -> dict:
    document = IncidentDocument.model_validate(value)
    errors, cases = [], []
    if document.fault_template not in APPROVED_TEMPLATES:
        errors.append("Choose a registered, approved semantic fault template.")
    if any("Instructor:" in text for text in (document.complaint, document.business_rules, document.fault_cause)):
        errors.append("Replace the instructor authoring placeholders before validation.")
    if not document.oracle_confirmed:
        errors.append("Confirm that you have reviewed the expected outputs and business rules using the review checkbox.")
    if len({digest(s.seed_sql) for s in document.scenarios}) != len(document.scenarios):
        errors.append("Scenario seeds must be distinct; replace adaptation placeholders.")
    if not any(not s.visible for s in document.scenarios):
        errors.append("At least one hidden scenario is required.")
    deadline = time.monotonic() + settings.COMPETITION_JUDGE_SECONDS
    visible_failure, witness = False, False
    for scenario in document.scenarios:
        for component in document.components:
            approved = scenario.approved_outputs[component.id].model_dump()
            opts = {"order_sensitive": component.order_sensitive, "numeric_tolerance": component.numeric_tolerance}
            result = execute(document.schema_sql, scenario.seed_sql, component.reference_query, deadline=deadline)
            reference_ok = matches(result, approved, **opts)
            mutant = execute(document.schema_sql, scenario.seed_sql, component.query, deadline=deadline)
            mutant_ok = matches(mutant, approved, **opts)
            cases.append({"scenario": scenario.id, "component": component.id, "reference_ok": reference_ok,
                          "fault_executes": mutant["success"], "matches_approved": mutant_ok, "actual": mutant, "approved": approved})
            if not reference_ok:
                errors.append(f"{scenario.id}/{component.id}: reference does not match approved output.")
            if not mutant["success"]:
                errors.append(f"{scenario.id}/{component.id}: initial SQL must execute successfully.")
            if component.id == document.culprit_component:
                witness |= not mutant_ok and mutant["success"]
                visible_failure |= scenario.visible and not mutant_ok and mutant["success"]
            elif not mutant_ok:
                errors.append(f"{scenario.id}/{component.id}: a healthy component is faulty.")
            if component.id == document.culprit_component:
                for repair in document.alternative_repairs:
                    if not matches(execute(document.schema_sql, scenario.seed_sql, repair, deadline=deadline), approved, **opts):
                        errors.append(f"{scenario.id}: alternative repair does not satisfy the oracle.")
    if not witness or not visible_failure:
        errors.append("The seeded semantic fault must reproduce the visible complaint and fail a witness.")
    return {"valid": not errors, "errors": errors, "cases": cases, "content_hash": digest(value), "parser_version": PARSER_VERSION}
