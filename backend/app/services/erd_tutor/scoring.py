import json
import logging
from collections import defaultdict
from typing import Optional

from app.services.erd_tutor.extras import (
    ELEMENT_CHECK_TYPES, MARK_CHECK_TYPES, bare_line_extras, confirm_extras,
    rulings_on_candidates, scoring_checks, unaccounted_elements, unruled_candidates,
)
from app.services.erd_tutor.name_matching import (
    check_type, flag as _policy_flag, is_naming_check, rubric_checks,
)

logger = logging.getLogger(__name__)

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

def _dimension(value) -> str:
    """A check's dimension as the cap reads it: stripped, and "" when it is not a
    string (absent, null, any other type). The one reading of it, so that the
    final check, the extra's cap_dimensions and the ledger in _apply_cap name a
    dimension by the same string."""
    return value.strip() if isinstance(value, str) else ""

def _label(percent: int) -> str:
    if percent == 100: return "pass"
    if percent >= 50: return "partial"
    return "needs work"

# ---- Extra elements: price and cap --------------------------------------------

# Which rubric checks an extra is priced from, by check_type. An identifying
# relationship is a kind of relationship, so it is in that pool too; every mark
# on a line end (cardinality, participation, integrity) is priced as a
# cardinality mark. The pools are extras.ELEMENT_CHECK_TYPES and
# extras.MARK_CHECK_TYPES, which also decide what the guard charges at all: a
# kind with no scoring check in its pool is never charged.
_MIRRORED_TYPES = {
    **ELEMENT_CHECK_TYPES,
    **{f"mark:{mark}": types for mark, types in MARK_CHECK_TYPES.items()},
}


def _group(entry):
    """The price pool an extra is read from (_MIRRORED_TYPES): its kind, or
    "mark:<mark>" for a mark."""
    return f"mark:{entry.get('mark')}" if entry.get("kind") == "mark" else str(entry.get("kind"))


def _scoring_checks(rubric):
    """The rubric's readable checks (rubric_checks) that score: must or should,
    with points."""
    return scoring_checks(rubric_checks(_to_dict(rubric)))


def _mean_points(checks):
    return (sum(_safe_float(rc.get("points", 0)) for rc in checks) / len(checks)
            if checks else 0.0)


def price_extras(confirmed, rubric, final_checks):
    """-> (deductions, total). Price each confirmed extra from the rubric itself.

    The price is the mean points of the rubric's scoring checks of the mirrored
    kind - an extra entity costs what an entity_presence check is worth on this
    question. With no such check the rubric does not check that kind, and the
    entry is dropped, not priced: the guard never confirms one (chargeable_kinds,
    the scored marks), and pricing it from every check would charge a correct
    diagram for what the question never asked about. Each entry records the
    dimensions its cap reads from, so a staff correction can re-cap it later
    (reapply_deductions) without the rubric.

    A check's dimension is the one its final check was scored under (the rubric's,
    else the one the judge supplied: compute_grade), not the rubric's alone. A
    check the judge supplied the dimension for would otherwise cap its extras on
    "", which no final check is filed under: no room, and a silent 0-point
    deduction.
    """
    scoring = _scoring_checks(rubric)
    filed = {str(c.get("id", "")).strip(): _dimension(c.get("dimension"))
             for c in _to_list(final_checks) if isinstance(c, dict)}
    entries = []
    for ex in confirmed:
        pool = [rc for rc in scoring
                if check_type(rc) in _MIRRORED_TYPES.get(_group(ex), set())]
        if not pool:
            logger.warning("extras: dropped %r (%s): the rubric has no %s check, so nothing "
                           "to price it from", ex.get("canonical_id"), _group(ex), _group(ex))
            continue
        entries.append({**ex, "price": _mean_points(pool),
                        "cap_dimensions": sorted({filed.get(rc["id"], rc["dimension"])
                                                  for rc in pool})})
    return _apply_cap(entries, final_checks)


def reapply_deductions(stored, final_checks):
    """Re-cap stored deductions against re-totalled checks.

    The ceiling is each deduction's stored price, not its stored points: points
    are what the last cap allowed, price is what the extra is worth. A staff
    correction that lowers the earnings lowers a deduction, one that raises them
    lets it grow back, and never above its original price. _apply_cap writes the
    price back unchanged, so reapplying a result against any checks gives what
    reapplying the original would have. An entry stored without a price falls
    back to its points.
    """
    entries = [{**d, "price": _safe_float(d.get("price", d.get("points", 0)))}
               for d in _to_list(stored) if isinstance(d, dict)]
    return _apply_cap(entries, final_checks)


def _apply_cap(entries, final_checks):
    """-> (deductions, total). One ledger per dimension: what the student earned
    on it, less what earlier entries took from it. An entry's room is what is
    left on its cap_dimensions together (all of them for an entry stored without
    any); it takes the smaller of its price and that room, spending the first of
    its dimensions before the next. So no dimension ever gives up more than it
    earned, the entries sum to the real reduction, and that never exceeds what
    the student earned.

    The ledger is per dimension, not per kind of extra: kinds share dimensions
    (an extra entity and an extra weak border are both capped on entities), and
    capped per kind each could take everything the dimension earned."""
    earned_by_dim = defaultdict(float)
    for c in _to_list(final_checks):
        if isinstance(c, dict) and "earned_points" in c:
            earned_by_dim[_dimension(c.get("dimension"))] += _safe_float(c.get("earned_points"))
    spent, out, total = defaultdict(float), [], 0.0
    for e in entries:
        dims = (list(dict.fromkeys(_dimension(d) for d in _to_list(e.get("cap_dimensions"))))
                or list(earned_by_dim))
        left = {d: max(0.0, earned_by_dim.get(d, 0.0) - spent[d]) for d in dims}
        price = max(0.0, _safe_float(e.get("price")))
        # A deduction staff waived costs nothing and spends no room: the room
        # stays for the entries after it. The flag rides with the entry, so a
        # later re-cap keeps the waiver; a revert drops it with the snapshot.
        waived = bool(e.get("waived"))
        points = 0.0 if waived else min(price, sum(left.values()))
        rest = points
        for d in dims:
            take = min(rest, left[d])
            spent[d] += take
            rest -= take
        # A stored reason can carry the tag from an earlier pass (entries go
        # through reapply_deductions again), so the tag is rebuilt on every pass:
        # it says what happened in THIS one. The tolerance keeps float rounding
        # in a budget that fills exactly from reading as a cap.
        reason = str(e.get("brief_reason") or "").strip()
        if reason.endswith("[cap reached]"):
            reason = reason[:-len("[cap reached]")].rstrip()
        if not waived and price - points > 1e-9:
            reason = (reason + " [cap reached]").strip()
        total += points
        out.append({"canonical_id": e.get("canonical_id"), "kind": e.get("kind"),
                    "mark": e.get("mark"), "label": e.get("label", ""),
                    "brief_reason": reason, "price": price,
                    "cap_dimensions": dims, "points": points,
                    **({"waived": True} if waived else {})})
    return out, total


def deductions_json(score) -> Optional[str]:
    """A score's deductions as the JSON stored on er_submissions, or None when
    there are none."""
    items = _to_list(_to_dict(score).get("deductions"))
    return json.dumps(items, ensure_ascii=False) if items else None


_MARK_PHRASE = {"key": "key underline on {}", "weak": "weak border on {}",
                "identifying": "double diamond on {}", "hierarchy": "hierarchy {}",
                "cardinality": "cardinality label on {}"}


def _label_for_entry(candidate):
    """What a candidate is called in its deduction and to the student: its drawn
    label, else (a diamond drawn without one) the entities it joins, else its id."""
    label = str(candidate.get("label") or "").strip()
    if label:
        return label
    joined = [p for p in candidate.get("participants") or [] if p]
    return " \u2013 ".join(joined) if joined else str(candidate.get("canonical_id") or "")


_SENTENCE = "Deducted for elements the rubric does not ask for:"


def deduction_sentence(deductions) -> str:
    """The one sentence that names the deductions that cost points, in the order
    they were charged; "" when none did. compute_grade appends it to the
    student message, and a staff correction rebuilds it (er_score_override): a
    waived or re-capped entry changes what it should say."""
    named = [_name_for_student(d) for d in _to_list(deductions)
             if isinstance(d, dict) and _safe_float(d.get("points")) > 1e-9]
    return f"{_SENTENCE} {', '.join(named)}." if named else ""


def with_deduction_sentence(message, deductions):
    """`message` with its deduction sentence brought up to date: the one it
    carries (compute_grade puts it last) is cut, the current one appended when
    there is one. A message with neither is returned as it is."""
    text = str(message or "")
    at = text.find(_SENTENCE)
    sentence = deduction_sentence(deductions)
    if at < 0 and not sentence:
        return message
    if at >= 0:
        text = text[:at]
    return f"{text.rstrip()} {sentence}".strip() if sentence else text.strip()


def _name_for_student(candidate):
    """What to call a candidate, or a deduction, to the student. A mark is named
    as the mark on that, so that a required attribute is not named as if it were
    extra."""
    label = _label_for_entry(candidate)
    if candidate.get("kind") == "line":
        ends = label.split(" \u2013 ")
        return f"line between {ends[0]} and {ends[1]}" if len(ends) == 2 else f"line {label}"
    phrase = _MARK_PHRASE.get(candidate.get("mark")) if candidate.get("kind") == "mark" else None
    return phrase.format(label) if phrase else label


def _unruled_reason(candidate):
    """Why an element candidate the judge did not rule on is charged. A surplus
    copy says so: the judge may have accounted for it, which does not rule on it."""
    if candidate.get("_surplus"):
        why = candidate["why"]
        return f"{why[0].upper()}{why[1:]}; the judge did not list it."
    return "No rubric check accounts for this element and the judge did not explain it."


def _extras_to_confirm(judge, rubric, canonical):
    """The judge's extras plus every computed candidate it did not rule on.

    A candidate is a drawn element no rubric check accounts for, or a mark no
    check asks for (extras.unaccounted_elements). The judge rules on each one,
    either listing it in extras under the kind it is drawn as, or putting it in
    accounted_candidates with the rule that explains it; one it leaves out of both
    is treated as extra (extras.unruled_candidates says exactly when). A judge
    entry that only names a mark on the element, or gives it the wrong kind, does
    not rule on it: the element is added as an extra under its own kind, the guard
    drops the judge's wrong-kind entry as before, and drops a mark since the
    element is already charged. accounted_candidates never clears an element the
    judge also lists in extras. A bare line (two entities joined with no diamond,
    extras.bare_line_extras) is an extra outright: no check can ask for one, so
    the judge is not asked.

    The guard charges the entries it meets first when a name is allowed fewer
    times than it is drawn, so they go in this order: the judge's entries about
    element candidates, the entries added here, and then the judge's entries about
    anything else. A judge that lists a required element (a relationship that is
    both the "has" and the A-B the rubric asks for) cannot use up the allowance of
    the real surplus ones, and neither can one that lists the carrier of a mark
    candidate.
    """
    extras = _to_list(judge.get("extras"))
    candidates = unaccounted_elements(rubric, canonical)
    listed, accounted = rulings_on_candidates(judge)
    elements = {(c["canonical_id"], c["kind"]) for c in candidates if c["kind"] != "mark"}
    for cid in sorted({cid for cid, _kind in listed} & accounted
                      & {cid for cid, _kind in elements}):
        logger.warning("extras: %r is in both extras and accounted_candidates; extras wins", cid)
    # An entry with no mark rules on the element candidate with its id, and on
    # nothing else: not on a mark the element carries (that takes an entry naming
    # the mark), and not on an element that is no candidate.
    for cid in sorted(accounted - {cid for cid, _kind in elements}):
        logger.warning("extras: accounted_candidates entry %r names no mark and no element "
                       "candidate has that id, so it rules on nothing", cid)
    unruled = unruled_candidates(judge, candidates)
    added = [{"canonical_id": c["canonical_id"], "kind": "mark", "mark": c["mark"],
              "label": _label_for_entry(c),
              "brief_reason": "No rubric check asks for this mark and the judge did not "
                              "explain it."}
             if c["kind"] == "mark" else
             {"canonical_id": c["canonical_id"], "kind": c["kind"],
              "label": _label_for_entry(c),
              "brief_reason": _unruled_reason(c)} for c in unruled]
    added += bare_line_extras(canonical)
    about_candidates, others = [], []
    for entry in extras:
        pair = None
        if isinstance(entry, dict):
            kind = entry.get("kind")
            pair = (str(entry.get("canonical_id", "")).strip(),
                    kind.strip() if isinstance(kind, str) else "")
        (about_candidates if pair in elements else others).append(entry)
    return about_candidates + added + others


def compute_grade(judge_result: dict, rubric: dict, prev: dict, canonical=None) -> dict:
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
            scores = level in ("must", "should") and points > 0
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
        #
        # A partial stamped decided_by="deterministic" is also kept. That status
        # is a deliberate code decision (deterministic_checks: no drawn value
        # contradicts the rubric, part of it is confirmed, the rest is not
        # stated), not an LLM hedging against uncertainty — and the hedging is
        # the behaviour this enforcement exists to stop.
        policy = rc.get("decision_policy")
        if (status == "partial" and _policy_flag(policy, "partial_allowed") is False
                and not is_naming_check(rc)
                and jc.get("decided_by") != "deterministic"):
            fallback = policy.get("unclear_evidence_policy")
            status = fallback if fallback in {"pass", "fail", "not_applicable"} else "fail"
            reason = (f"{reason} [Grader returned partial, which this check does not "
                      f"allow; resolved to {status}.]").strip()
        # The rubric's dimension, else the one the judge copied onto the check. The
        # extras' caps are filed under this string (price_extras reads it back from
        # the final checks), so it is stripped and never None.
        dimension = _dimension(rc.get("dimension")) or _dimension(jc.get("dimension"))
        check = {"id": cid, "dimension": dimension,
                 "requirement_level": level, "points": points,
                 "status": status, "brief_reason": reason}
        # A tuple, not a set: a rubric's level is unvalidated JSON, and testing a
        # list for membership of a set raises.
        if level in ("must", "should") and status != "not_applicable":
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

    # Extras: drawn elements the judge says no check asks for, after the guard.
    # Priced from this rubric, capped per dimension, then taken off the top.
    # earned_points stays the figure every consumer reads (assessment marks,
    # roster analytics, the conversation mirror), so a deduction flows wherever
    # a grade flows with no further change. With no canonical model (older
    # callers, tests) the guard confirms nothing and nothing is deducted.
    deductions, deducted = price_extras(
        confirm_extras(_extras_to_confirm(judge, rubric, canonical), rubric, canonical),
        rubric, final_checks)
    earned_points = max(0.0, earned_points - deducted)
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

    # What was charged is said once, here, from the final deductions: the judge's
    # list is filtered by the guard and topped up with the candidates it did not
    # rule on, so a message the judge wrote could name an extra that was dropped
    # and miss one that was added. Only the deductions that cost points (a cap can
    # take one to 0), in the order they were charged.
    student_message = with_deduction_sentence(judge.get("student_message", ""), deductions)

    return {
        "score": {"label": _label(percent), "earned_points": earned_points,
                  "total_points": total_points, "percent": percent,
                  "deducted_points": deducted, "deductions": deductions},
        "top_issues": top_issues, "failed_must_checks": failed_must,
        "progress": {"improvements": improvements[:5], "regressions": regressions[:5]},
        "ibl": judge.get("ibl", {}), "student_message": student_message,
        # checks is an ARRAY, matching the Dify engine's over-the-wire contract
        # (app.schemas.er_diagram.ERSubmissionStructuredOutput.checks: list[...])
        # and the frontend rubric matcher. Emitting a JSON string here made the
        # frontend iterate characters, so every rubric item showed "Not evaluated".
        "checks": final_checks,
    }
