import json

from app.services.erd_tutor.name_matching import flag as _policy_flag, is_naming_check

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
        if jc:
            status = jc.get("status", "fail")
            reason = str(jc.get("brief_reason", "")).strip()
        else:
            # The judge did not return this check at all. That is a grader failure,
            # not student evidence, so do not report it as something the student got
            # wrong when it cannot cost them anything: optional/zero-point checks
            # become not_applicable ("not evaluated"). must/should stay conservative
            # — silently passing an unevaluated scoring check would be worse.
            scores = level in {"must", "should"} and points > 0
            status = "fail" if scores else "not_applicable"
            reason = ("Not evaluated — the grader did not return a result for this check."
                      if not scores else
                      "The grader did not return a result for this check, so it could not be verified.")
        if not reason:
            reason = "No reason given."
        if status not in {"pass", "fail", "partial", "not_applicable"}:
            status = "fail"; reason = (reason + " Invalid status normalized to fail.").strip()
        # GRADE_SYSTEM rules 12a/14a tell the judge that a check's decision_policy
        # is binding, but it is an LLM and sometimes returns "partial" anyway —
        # typically when it is merely uncertain, which rule 13 already forbids.
        # Enforce the rubric's own policy here so a non-compliant judge cannot
        # award half marks on a check that does not allow them. Rubrics without a
        # decision_policy (pre-LangGraph, or Dify-authored) are left untouched.
        #
        # Naming checks are exempt. GRADE_SYSTEM rule 16 makes "partial" the
        # defined outcome for a token mismatch under exact_name_required, and it
        # is the ONLY route to partial that rule 12 allows at all. The generator
        # prompt gives partial_allowed guidance for structural checks only, so on
        # naming checks the value is unguided — and it lands "false" on 403 of the
        # 409 naming checks in the stored rubrics, which deleted rule 16 outright
        # and turned every synonym into a whole-check fail (48 of 100 points on
        # question 30). The flag is honoured everywhere else.
        #
        # _policy_flag, not `is False`: eight rubrics store these flags as the
        # strings "true"/"false", so an identity test enforced the same declared
        # policy on some questions and ignored it on others.
        policy = rc.get("decision_policy")
        if (status == "partial" and _policy_flag(policy, "partial_allowed") is False
                and not is_naming_check(rc)):
            fallback = policy.get("unclear_evidence_policy")
            status = fallback if fallback in {"pass", "fail", "not_applicable"} else "fail"
            reason = (f"{reason} [Grader returned partial, which this check does not "
                      f"allow; resolved to {status}.]").strip()
        check = {"id": cid, "dimension": rc.get("dimension", jc.get("dimension", "")),
                 "requirement_level": level, "points": points,
                 "status": status, "brief_reason": reason}
        if level in {"must", "should"} and status != "not_applicable":
            earned = points if status == "pass" else 0.5 * points if status == "partial" else 0.0
            total_points += points
            earned_points += earned
            # Record what the check earned, not just its maximum. `points` is the
            # ceiling; staff analytics show the award per row, and while this was
            # only accumulated into the total, every AI-graded check rendered as 0
            # against a correct overall score. Carried on scoring checks only, so
            # the shape matches er_score_override.score_from_awards.
            check["earned_points"] = earned
        final_checks.append(check)

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
