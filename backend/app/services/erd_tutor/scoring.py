import json

def _to_dict(x):
    if isinstance(x, dict): return x
    if isinstance(x, str):
        x = x.strip()
        try: return json.loads(x) if x else {}
        except Exception: return {}
    return {}

def _to_list(x):
    return x if isinstance(x, list) else []

def _safe_float(x):
    try: return float(x)
    except Exception: return 0.0

def _label(percent: int) -> str:
    if percent == 100: return "pass"
    if percent >= 50: return "partial"
    return "needs work"

def compute_grade(judge_result: dict, rubric: dict, prev: dict) -> dict:
    judge, rubric, prev = _to_dict(judge_result), _to_dict(rubric), _to_dict(prev)
    rubric_by_id, rubric_order = {}, []
    for rc in _to_list(rubric.get("checks")):
        cid = str(rc.get("id", "")).strip()
        if cid: rubric_by_id[cid] = rc; rubric_order.append(cid)
    judge_by_id = {str(jc.get("id", "")).strip(): jc
                   for jc in _to_list(judge.get("checks")) if str(jc.get("id", "")).strip()}

    final_checks, total_points, earned_points = [], 0.0, 0.0
    for cid in rubric_order:
        rc, jc = rubric_by_id[cid], judge_by_id.get(cid, {})
        level = rc.get("requirement_level", "optional")
        points = _safe_float(rc.get("points", 0))
        status = jc.get("status", "fail")
        reason = str(jc.get("brief_reason", "Missing check result from judge output.")).strip()
        if status not in {"pass", "fail", "partial", "not_applicable"}:
            status = "fail"; reason = (reason + " Invalid status normalized to fail.").strip()
        if level in {"must", "should"} and status != "not_applicable":
            total_points += points
            if status == "pass": earned_points += points
            elif status == "partial": earned_points += 0.5 * points
        final_checks.append({"id": cid, "dimension": rc.get("dimension", jc.get("dimension", "")),
                             "requirement_level": level, "points": points,
                             "status": status, "brief_reason": reason})

    percent = round(100 * earned_points / total_points) if total_points > 0 else 0
    failed_must = [{"check_id": c["id"], "dimension": c["dimension"], "summary": c["brief_reason"]}
                   for c in final_checks if c["requirement_level"] == "must" and c["status"] == "fail"][:5]
    top_issues = [f'{c["id"]}: {c["brief_reason"]}'
                  for c in final_checks if c["status"] in {"fail", "partial"}][:3]

    # The persisted report stores checks as a JSON string (DSL output contract),
    # so decode it before comparing against the current submission.
    prev_checks = prev.get("checks")
    if isinstance(prev_checks, str):
        try:
            prev_checks = json.loads(prev_checks)
        except Exception:
            prev_checks = []
    prev_status = {str(pc.get("id", "")).strip(): pc.get("status") for pc in _to_list(prev_checks)}
    rank = {"fail": 0, "partial": 1, "pass": 2, "not_applicable": 3}
    improvements, regressions = [], []
    for c in final_checks:
        ps = prev_status.get(c["id"])
        if ps is None: continue
        if rank.get(c["status"], -1) > rank.get(ps, -1): improvements.append(f'{c["id"]}: {ps} -> {c["status"]}')
        elif rank.get(c["status"], -1) < rank.get(ps, -1): regressions.append(f'{c["id"]}: {ps} -> {c["status"]}')

    return {
        "score": {"label": _label(percent), "earned_points": earned_points,
                  "total_points": total_points, "percent": percent},
        "top_issues": top_issues, "failed_must_checks": failed_must,
        "progress": {"improvements": improvements[:5], "regressions": regressions[:5]},
        "ibl": judge.get("ibl", {}), "student_message": judge.get("student_message", ""),
        # checks is an ARRAY, matching the Dify engine's over-the-wire contract
        # (app.schemas.er_diagram.ERSubmissionStructuredOutput.checks: list[...])
        # and the frontend rubric matcher. Emitting a JSON string here made the
        # frontend iterate characters, so every rubric item showed "Not evaluated".
        "checks": final_checks,
    }
