"""Answers shown in textbook notation: what was typed, as the parser read it."""
import pytest

from app.core.ra import parse
from app.core.ra.latex import program_to_latex


def latex(text, names=()):
    return [line["latex"] for line in program_to_latex(parse(text, names=names))]


def test_each_statement_is_one_line_with_subscripts():
    lines = program_to_latex(parse("R1 := σ Numphds < 50 (DEPT)\nAnswer := π Pname (PROF ⋈ R1)"))
    assert [(l["line"], l["name"]) for l in lines] == [(1, "R1"), (2, "Answer")]
    assert lines[0]["latex"] == r"\text{R1} \leftarrow \sigma_{\text{Numphds} < 50}(\text{DEPT})"
    assert lines[1]["latex"] == r"\text{Answer} \leftarrow \Pi_{\text{Pname}}(\text{PROF} \bowtie \text{R1})"


def test_brackets_show_what_an_operator_applies_to():
    # σ binds to the next relation only, so this σ does not cover the join.
    assert latex("σ GPA > 3 STUDENT ⋈ ENROLL") == [
        r"\sigma_{\text{GPA} > 3}(\text{STUDENT}) \bowtie \text{ENROLL}"]
    assert latex("R − (S ∪ T)") == [r"\text{R} - (\text{S} \cup \text{T})"]


@pytest.mark.parametrize("text, expected", [
    ("STUDENT ⋈ STUDENT.GPA = R1.MinGPA R1",
     r"\text{STUDENT} \bowtie_{\text{STUDENT.GPA} = \text{R1.MinGPA}} \text{R1}"),
    ("γ Dname, MIN(GPA) → Low STUDENT",
     r"\gamma_{\text{Dname}, \text{MIN}(\text{GPA}) \rightarrow \text{Low}}(\text{STUDENT})"),
    ("γ COUNT(*) → n R", r"\gamma_{\text{COUNT}(*) \rightarrow \text{n}}(\text{R})"),
    ("ρ S(a, b) R", r"\rho_{\text{S}(\text{a}, \text{b})}(\text{R})"),
    ("σ Cname = 'Database System' AND NOT (Cno <> 1 OR Cno >= 9) COURSE",
     r"\sigma_{\text{Cname} = \text{‘Database System’} \land \lnot (\text{Cno} \neq 1 \lor \text{Cno} \geq 9)}"
     r"(\text{COURSE})"),
    ("Π a + b → total_sum R", r"\Pi_{\text{a} + \text{b} \rightarrow \text{total\_sum}}(\text{R})"),
    ("δ (R × S) ÷ T", r"\delta(\text{R} \times \text{S}) \div \text{T}"),
    ("R ⟕ S", r"\text{R} \mathbin{\text{⟕}} \text{S}"),
])
def test_operators(text, expected):
    assert latex(text) == [expected]


def test_hyphenated_names_come_back_as_typed():
    assert latex("Π teamid-one TEAMS", names=["TEAMS", "teamid-one"]) == [r"\Pi_{\text{teamid-one}}(\text{TEAMS})"]
