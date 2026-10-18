"""Tests for the RA parser: course notation, statement splitting and syntax errors."""
import pytest

from app.core.ra import RAError, parse
from app.core.ra import ast
from app.core.ra.parser import split_statements


def test_slide_style_program_is_split_by_lines():
    prog = """R1 := σ School = 'SCSE' CrsSch
R2 := Π Course R1
R3 := Π Name, Course (Grades)
R3 ÷ R2"""
    p = parse(prog)
    assert [s.name for s in p.statements] == ["R1", "R2", "R3", None]
    assert isinstance(p.result.expr, ast.Binary) and p.result.expr.op == "division"


def test_expressions_can_span_lines():
    chunks = split_statements("Π Name Grades -\n   Π Name (Grades ⋈ (σ School <> 'EEE' CrsSch))")
    assert len(chunks) == 1
    chunks = split_statements("R1 := Quiz1\n   ⋈ Quiz2\nR1")
    assert [c[0].split()[0] for c in chunks] == ["R1", "R1"]


def test_bare_final_expression_after_assignments():
    p = parse("R1 := Π Name Students\nR2 := Π Name Volunteer\nR1 ∪ R2")
    assert [s.name for s in p.statements] == ["R1", "R2", None]


def test_semicolons_and_comments():
    p = parse("R1 := Quiz1; -- copy\nR2 := σ Score > 80 R1 // the good ones\nΠ Name R2")
    assert [s.name for s in p.statements] == ["R1", "R2", None]


def test_positions_are_absolute():
    p = parse("R1 := Quiz1\nR2 := σ Score > 80 R1")
    sel = p.statements[1].expr
    assert (sel.pos.line, sel.pos.col) == (2, 7)


def test_extended_operators_parse():
    p = parse("γ School, COUNT(*) → n, AVG(GPA) → g (δ Quiz1)")
    g = p.result.expr
    assert isinstance(g, ast.Group) and [a.func for a in g.aggregates] == ["COUNT", "AVG"]
    assert g.aggregates[0].attr is None
    p = parse("Π Name, (Quiz1 + Quiz2) / 2 → Average Scores")
    assert p.result.expr.items[1].alias == "Average"
    for op, sym in [("left_join", "⟕"), ("right_join", "⟖"), ("full_join", "⟗")]:
        assert parse(f"A {sym} B").result.expr.op == op
        assert parse(f"A {sym} A.x = B.y B").result.expr.condition is not None


def test_keywords_are_whole_words():
    cond = parse("σ nothing = 1 AND order_no <> 2 R").result.expr.condition
    assert str(cond) == "nothing = 1 AND order_no ≠ 2"


@pytest.mark.parametrize("text, code", [
    ("π Name (Students ⋈ )", "RA001"),
    ("σ Age > Students", "RA001"),
    ("Π Name Students @", "RA001"),
    ("σ Score = MAX(Score) Quiz1", "RA013"),
    ("R1 ∪ R2\nR3 := R1", "RA001"),
    ("x" * 6000, "RA009"),
    ("", "RA001"),
])
def test_errors(text, code):
    with pytest.raises(RAError) as e:
        parse(text)
    assert e.value.code == code


def test_syntax_error_says_what_was_expected():
    with pytest.raises(RAError) as e:
        parse("Π Name Students ∪")
    assert e.value.line == 1 and "Expected" in e.value.hint and "σ" in e.value.hint
