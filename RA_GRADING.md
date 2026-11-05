# How RA answers are graded

This explains how the Relational Algebra module decides whether a student's answer is right. It
covers the method, the mathematics behind each part and its limits, and is written for the FYP
report. The code is in `backend/app/core/ra/`, and each file's opening comment repeats the relevant
part.

## 1. What "correct" means

A student's answer is correct when it returns the same relation as the model answer **on every
valid database** of the question's schema. The two relations must have the same attribute names
(in any order) and the same tuples. Tuples are compared as a set by default, or as a bag if the
question asks for it.

A database is *valid* when:

- every attribute holds a value of its declared type (INTEGER holds whole numbers, REAL numbers,
  TEXT strings);
- primary keys are unique;
- every foreign key points at an existing tuple;
- stored tables hold no NULLs, as in the relational model taught in the course. NULLs appear only
  after outer joins, where SQL's three-valued logic is followed exactly.

Equal results on one database, or on many, don't make two answers equivalent. "On every valid
database" is the definition, and it is what the grader tries to prove.

## 2. The grading algorithm

For one submitted answer:

| # | Step | Outcome if it fails |
|---|------|---------------------|
| 1 | Parse it and run it on the empty schema (unknown names, type errors…) | *invalid expression*, with line and column |
| 2 | Its attributes must be the model answer's | *wrong attributes* |
| 3 | Same result on the question's own data (if any)? | *wrong result* |
| 4 | Same result on every test database? | *not correct in general* + the smallest such database |
| 5 | Prove it equivalent on every valid database | see below |

The test databases in step 4 are the question's stored suite, built when staff save the question
(`suite.py`). The suite starts from the empty database and adds seeded random databases. It keeps
adding until every *mutant* of the model answer (MIN↔MAX, < ↔ ≤, ∪↔∩, a dropped condition, ÷ turned
into "at least one"… `mutate.py`) gives a different result on some database. Extra databases are
also built for constants that only the student used, so a hard-coded value is caught.

Step 5 runs only for an answer that passed every test. It ends in one of three ways:

- **proved equivalent** → *correct* (method `proof`);
- **a valid database where they differ** → *not correct in general* (method `proof`). Such a
  database exists but none of the test databases was one;
- **undecided** within the fixed amount of work → *correct* (method `tested`). The verdict then
  rests on the tests alone.

So every *wrong* verdict comes with a real database where the answers differ: it is certain.
Only a *correct* verdict can rest on testing alone, and the method recorded with it says whether
it did. Students see the same message either way, and staff see the method.

## 3. The proof

### 3.1 From relational algebra to logic (`logic.py`)

Each relation an answer computes becomes a formula `member(t)`, which is true exactly when the
tuple `t` is in the result. The stored tables are *uninterpreted predicates*: `Course(c, n)` reads
"(c, n) is a tuple of Course". This leaves them free, so one formula speaks about every database
at once. Values have three kinds, NULL, number and string, as in the evaluator.

| Operator | Formula for `t ∈ result` |
|----------|--------------------------|
| R | R(t) |
| σ_c E | E(t) ∧ c(t) is *true* |
| Π_A E | ∃u. E(u) ∧ t = u restricted to A (computed attributes as terms) |
| E × F, E ⋈_c F | E(t₁) ∧ F(t₂) (∧ c(t₁t₂) true) |
| E ⋈ F (natural) | E(t₁) ∧ F(t₂') with equal, non-NULL join attributes |
| E ⟕ F | (matched as above) ∨ (E(t₁) ∧ t₂ all NULL ∧ ¬∃u. F(u) ∧ c(t₁u)) |
| E ∪ F, E ∩ F, E − F | E(t) ∨ F(t), E(t) ∧ F(t), E(t) ∧ ¬F(t) |
| E ÷ F | (∃b. E(t, b)) ∧ ∀b. F(b) → E(t, b) |
| γ_{G; MAX(a)} E | the group exists ∧ some tuple of the group has a = m ∧ no tuple of the group has a > m (NULL if the group has no non-NULL a) |
| γ_{G; COUNT/SUM/AVG} E | the group exists ∧ value = f(g), f an unknown function (§3.3) |

Conditions use three-valued logic. Each condition becomes a pair (definitely true, definitely
false); NOT swaps the two, and σ keeps tuples whose condition is definitely true. Values of
different kinds are never equal and never ordered, as in the evaluator.

The translation reuses the evaluator's own name rules (qualifiers, ambiguity, ρ, union
compatibility), so an answer means exactly what it means when it runs. The schema becomes axioms:
types, no NULLs, primary keys (∀x, y: R(x) ∧ R(y) ∧ x.key = y.key → x = y) and foreign keys
(∀x: R(x) → ∃y: S(y) ∧ y.ref = x.fk).

### 3.2 Deciding equivalence (`equivalence.py`)

The solver is asked whether a valid database and a tuple exist that are in one answer but not the
other:

  axioms ∧ ((A(t) ∧ ¬B(t)) ∨ (B(t) ∧ ¬A(t)))

- **Unsatisfiable:** no such database exists. The answers are equivalent on every valid database.
  This is the proof.
- **Satisfiable:** the solver's model describes a candidate counterexample.
- **Unknown:** the solver gave up within its share of the work.

If the whole is unknown, the prover tries **piece by piece**. It proves pairs of corresponding
sub-relations of the two answers equal (same attributes, biggest first), replaces each proved pair
by one shared unknown relation, and asks again. This is sound: if the parts are equal on every
valid database, replacing them by the same arbitrary relation can only make the question harder.

### 3.3 Aggregates

MIN and MAX can be written in first-order logic, as in the table. COUNT, SUM and AVG cannot, so
each one becomes an unknown function of the group's values. Two aggregates share one function
only when they aggregate the same attribute, group by the same attributes, and have inputs proved
to be the same relation. Equal sets give equal counts only when neither input can repeat a tuple,
so that is checked too. A key, δ, a set operator or γ all rule repeats out. In short, aggregates
are proved equal when they aggregate provably the same data.

### 3.4 Counterexamples (`bounded.py`)

Solvers are good at showing quantified formulas unsatisfiable but poor at satisfying them. So if
no proof was found, the prover also runs a bounded search: every database with at most 1, 2, then
3 tuples per table.

- **How it works:** each table gets k tuple slots, each an unknown tuple that may or may not be
  there. Every operator is worked out on the slots (σ keeps a slot whose condition holds, × pairs
  slots, γ adds up the slots of a group…), so the formulas have no quantifiers. Z3 decides those
  quickly, including COUNT, SUM, AVG and duplicates.
- **Checks before use:** a counterexample, whether from the solver's model or from the search, is
  never used on the solver's word. It is loaded into SQLite with the schema's constraints switched
  on, and both answers are run on it with the real evaluator. It counts only if they really
  differ. It is then shrunk (tuples removed while the answers still differ and the database stays
  valid), and the solver's made-up values are replaced with readable ones (`name_1`, small whole
  numbers).

### 3.5 Determinism and cost

- **Fixed work, not time:** the solver gets a fixed amount of *work*, Z3's deterministic resource
  counter (about 2 seconds on the server), not a clock, so the same answer gets the same verdict on
  any machine, however busy. A wall-clock cap well above it only guards against a stuck solver.
- **Pinned version:** Z3's version is pinned.
- **Caching:** proofs are cached per question and answer text.

## 4. Results on the course's questions

These are the Tutorial 5.5 and Lecture 2 questions, and the grader's own test cases.

| Check | Result |
|-------|--------|
| Model answers proved equivalent to themselves | 11 of 11 |
| Correct alternative answers proved (one expression vs steps, ÷ as a double difference, ∩ as ⋈, ≤ 49 for < 50 on whole numbers, ρ instead of :=, …) | 18 of 19 |
| Mutants of the model answers (60) disproved by the prover alone, without the test databases | 58 |
| Mutants wrongly proved equivalent | 0 |
| Mutant the tests miss | 1, proved equivalent (an outer join that a later join cancels) |
| Typical time | well under a second |

The one undecided correct answer computes "the lowest GPA" by a difference instead of γ MIN. It is
graded correct by testing and shown to staff as *tested*.

## 5. Limits

- **Undecidability.** Equivalence of relational algebra is undecidable in general: with −, it can
  express first-order logic (Trakhtenbrot's theorem). No algorithm decides every pair, so
  "undecided" is unavoidable for some answers. The parts that *are* decidable, and that the solver
  usually settles, are:
  - unions of conjunctive queries (σ with =, Π, ⋈, ×, ∪), the Chandra–Merlin and
    Sagiv–Yannakakis results;
  - comparisons <, ≤, >, ≥ (Klug);
  - one level of − and ÷.
- **Nonlinear arithmetic** (multiplying two attributes) may make the solver give up.
- **CHECK and UNIQUE constraints** are not used in proofs. This is sound, because proofs then hold
  on even more databases, but some answers that are equivalent only because of a CHECK stay
  *tested*. Counterexamples always obey them, since SQLite checks every one.
- **Bag questions** are proved only when neither answer can repeat a tuple.
- **The bounded search** finds counterexamples of up to 3 tuples per table. Larger ones are left
  to the test databases.

## 6. Past attempts

A better grader can change old verdicts. For example, the previous proof ignored foreign keys and
marked `Π sid (Enrolled ⋈ Course)` wrong. Nothing changes by itself. On a question's analytics
page, staff press **Check past attempts** to see every attempt the current grader would grade
differently, then **Save**. Marks set by hand are kept.
