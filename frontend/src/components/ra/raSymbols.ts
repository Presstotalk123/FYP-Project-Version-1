/**
 * What each relational-algebra symbol means, as the course slides use it. One list, shown
 * when hovering a symbol on the operator bar, in the editor and in the notation preview.
 */
export interface RaSymbolInfo {
  symbol: string;
  name: string;
  meaning: string;
  write: string;
  example: string;
  /** Other ways the grammar (grammar.lark) accepts the same symbol. */
  aliases?: string[];
}

export const RA_SYMBOLS: RaSymbolInfo[] = [
  {
    symbol: 'σ', name: 'Selection', aliases: ['\\select'],
    meaning: 'Keeps only the tuples that satisfy the condition.',
    write: 'σ condition R', example: "σ School = 'SCSE' Students",
  },
  {
    symbol: 'Π', name: 'Projection', aliases: ['π', '\\project'],
    meaning: 'Keeps only the listed attributes.',
    write: 'Π attributes R', example: 'Π ID, Name Students',
  },
  {
    symbol: 'ρ', name: 'Rename', aliases: ['\\rename'],
    meaning: 'Gives the relation a new name, and optionally new attribute names.',
    write: 'ρ NewName(a, b, …) R', example: 'ρ Eval1(SName, QScore) Quiz1',
  },
  {
    symbol: 'δ', name: 'Duplicate elimination', aliases: ['\\distinct'],
    meaning: 'Removes duplicate tuples.',
    write: 'δ R', example: 'δ Π Name Grades',
  },
  {
    symbol: 'γ', name: 'Grouping and aggregation', aliases: ['\\group'],
    meaning: 'Groups the tuples by the listed attributes and computes an aggregate for each group.',
    write: 'γ attributes, AGG(attribute) → NewName R', example: 'γ School, AVG(GPA) → AvgGPA Students',
  },
  {
    symbol: '⋈', name: 'Join', aliases: ['\\join'],
    meaning: 'Natural join: combines tuples that agree on every common attribute. '
      + 'With a condition (theta join): combines the pairs of tuples that satisfy it.',
    write: 'R ⋈ S   or   R ⋈ condition S', example: 'Quiz1 ⋈ Quiz1.Name = Quiz2.Name Quiz2',
  },
  {
    symbol: '⟕', name: 'Left outer join', aliases: ['\\leftjoin'],
    meaning: "A join that also keeps the left side's tuples with no match, filling the right side's attributes with NULL.",
    write: 'R ⟕ S   or   R ⟕ condition S', example: 'Students ⟕ Enrol',
  },
  {
    symbol: '⟖', name: 'Right outer join', aliases: ['\\rightjoin'],
    meaning: "A join that also keeps the right side's tuples with no match, filling the left side's attributes with NULL.",
    write: 'R ⟖ S   or   R ⟖ condition S', example: 'Enrol ⟖ Students',
  },
  {
    symbol: '⟗', name: 'Full outer join', aliases: ['\\fulljoin'],
    meaning: 'A join that also keeps the tuples with no match from both sides, filling the missing attributes with NULL.',
    write: 'R ⟗ S   or   R ⟗ condition S', example: 'Quiz1 ⟗ Quiz2',
  },
  {
    symbol: '×', name: 'Cartesian product', aliases: ['\\cross'],
    meaning: 'Pairs every tuple of R with every tuple of S.',
    write: 'R × S', example: 'Quiz1 × Quiz2',
  },
  {
    symbol: '÷', name: 'Division', aliases: ['\\divide'],
    meaning: "The values of R's other attributes that appear together with every tuple of S. S's attributes must all be in R.",
    write: 'R ÷ S', example: 'Π SID, Course Enrol ÷ Π Course Courses',
  },
  {
    symbol: '∪', name: 'Union', aliases: ['\\union'],
    meaning: 'The tuples in R, in S, or in both. Both sides need the same attributes.',
    write: 'R ∪ S', example: 'Π Name Quiz1 ∪ Π Name Quiz2',
  },
  {
    symbol: '∩', name: 'Intersection', aliases: ['\\intersect'],
    meaning: 'The tuples in both R and S. Both sides need the same attributes.',
    write: 'R ∩ S', example: 'Π Name Quiz1 ∩ Π Name Quiz2',
  },
  {
    symbol: '−', name: 'Difference', aliases: ['-', '\\diff'],
    meaning: 'The tuples in R that are not in S. Both sides need the same attributes.',
    write: 'R − S', example: 'Π Name Students − Π Name Enrol',
  },
  {
    symbol: ':=', name: 'Assignment', aliases: ['←'],
    meaning: 'Names the result of an expression, so later lines can use it.',
    write: 'R1 := expression', example: 'R1 := σ Score > 50 Quiz1',
  },
  {
    symbol: '→', name: 'Name a new attribute', aliases: ['->'],
    meaning: 'Names a computed attribute or an aggregate.',
    write: 'expression → NewName', example: 'Π Name, Quiz1 + Quiz2 → Total Scores',
  },
  {
    symbol: '≠', name: 'Not equal', aliases: ['<>', '!='],
    meaning: 'True when the two values are different.',
    write: 'a ≠ b', example: "σ Course ≠ 'DM' Enrol",
  },
  {
    symbol: '≤', name: 'Less than or equal', aliases: ['<='],
    meaning: 'True when the left value is smaller than or equal to the right one.',
    write: 'a ≤ b', example: 'σ Score ≤ 50 Quiz1',
  },
  {
    symbol: '≥', name: 'Greater than or equal', aliases: ['>='],
    meaning: 'True when the left value is larger than or equal to the right one.',
    write: 'a ≥ b', example: 'σ GPA ≥ 3.5 Students',
  },
  {
    symbol: 'AND', name: 'And', aliases: ['∧'],
    meaning: 'True when both conditions are true.',
    write: 'condition AND condition', example: "σ School = 'SCSE' AND GPA > 3 Students",
  },
  {
    symbol: 'OR', name: 'Or', aliases: ['∨'],
    meaning: 'True when at least one of the conditions is true.',
    write: 'condition OR condition', example: "σ School = 'SCSE' OR School = 'EEE' Students",
  },
  {
    symbol: 'NOT', name: 'Not', aliases: ['¬'],
    meaning: 'True when the condition is false.',
    write: 'NOT condition', example: "σ NOT School = 'SCSE' Students",
  },
  {
    symbol: 'COUNT', name: 'Count (aggregate)',
    meaning: 'The number of tuples in each group. Only allowed inside γ.',
    write: 'γ attributes, COUNT(attribute) → NewName R', example: 'γ School, COUNT(ID) → NumStudents Students',
  },
  {
    symbol: 'SUM', name: 'Sum (aggregate)',
    meaning: 'The total of the values in each group. Only allowed inside γ.',
    write: 'γ attributes, SUM(attribute) → NewName R', example: 'γ Name, SUM(Score) → Total Quiz1',
  },
  {
    symbol: 'AVG', name: 'Average (aggregate)',
    meaning: 'The average of the values in each group. Only allowed inside γ.',
    write: 'γ attributes, AVG(attribute) → NewName R', example: 'γ School, AVG(GPA) → AvgGPA Students',
  },
  {
    symbol: 'MIN', name: 'Minimum (aggregate)',
    meaning: 'The smallest value in each group. Only allowed inside γ.',
    write: 'γ attributes, MIN(attribute) → NewName R', example: 'γ Course, MIN(Score) → Lowest Grades',
  },
  {
    symbol: 'MAX', name: 'Maximum (aggregate)',
    meaning: 'The largest value in each group. Only allowed inside γ.',
    write: 'γ attributes, MAX(attribute) → NewName R', example: 'γ Course, MAX(Score) → Highest Grades',
  },
];

// Words (AND, count, …) match in any case, as the grammar reads them; symbols match exactly.
const key = (text: string) => (/^[A-Za-z]+$/.test(text) ? text.toUpperCase() : text);

const BY_TEXT = new Map<string, RaSymbolInfo>();
for (const info of RA_SYMBOLS) {
  for (const text of [info.symbol, ...(info.aliases ?? [])]) BY_TEXT.set(key(text), info);
}

/** The symbol written as ``text`` (any accepted spelling), if it is one. */
export function raSymbolInfo(text: string): RaSymbolInfo | undefined {
  return BY_TEXT.get(key(text.trim()));
}
