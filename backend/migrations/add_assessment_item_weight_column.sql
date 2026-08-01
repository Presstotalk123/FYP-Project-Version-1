-- Per-question weightage.
-- assessment_items.weight: integer percentage (0-100) of the assessment total for this item.
-- Weights across an assessment's items must total 100 (enforced in the API layer / editor).
-- Default 0 = legacy/unweighted; the editor auto-distributes equally on next save.
ALTER TABLE assessment_items ADD COLUMN IF NOT EXISTS weight INTEGER NOT NULL DEFAULT 0;
