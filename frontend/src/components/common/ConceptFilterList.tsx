'use client';

import { Concept } from '@/types/lad.types';

// Taxonomy groups in curriculum order. /lad/concepts sorts categories
// alphabetically, which would put "advanced" first; any group not listed here
// goes last rather than disappearing.
const GROUP_ORDER = [
  'filtering',
  'sorting',
  'joins',
  'aggregation',
  'subqueries',
  'set_operations',
  'advanced',
  'database_objects',
];

const groupLabel = (category: string): string => {
  const words = category.replace(/_/g, ' ');
  return words.charAt(0).toUpperCase() + words.slice(1);
};

interface ConceptFilterListProps {
  concepts: Concept[];
  /** concept_id -> number of questions in the list tagged with it. */
  counts: Map<number, number>;
  selected: number | null;
  onSelect: (conceptId: number | null) => void;
  /** Collapsed shows only the selected concept, so a narrowed list still says why. */
  collapsed?: boolean;
}

/** Chevron on the SQL row that shows / hides the concept list. */
export function ConceptListToggle({ open, onToggle }: { open: boolean; onToggle: () => void }) {
  return (
    <button
      type="button"
      className="icon-btn"
      onClick={onToggle}
      aria-expanded={open}
      aria-label={open ? 'Hide SQL concepts' : 'Show SQL concepts'}
      title={open ? 'Hide SQL concepts' : 'Show SQL concepts'}
      style={{ width: 28, height: 28, flexShrink: 0, color: 'var(--brand-lilac)' }}
    >
      <svg
        xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none"
        stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"
        style={{ transform: open ? 'none' : 'rotate(-90deg)', transition: 'transform 140ms ease' }}
      >
        <polyline points="6 9 12 15 18 9" />
      </svg>
    </button>
  );
}

/**
 * The SQL concepts nested under the "SQL" category in the Problems / Questions
 * sidebars. Concepts no listed question is tagged with are hidden, so every row
 * leads somewhere. Clicking the active concept clears it.
 */
export function ConceptFilterList({ concepts, counts, selected, onSelect, collapsed = false }: ConceptFilterListProps) {
  const visible = concepts.filter(
    (c) => (counts.get(c.id) ?? 0) > 0 && (!collapsed || c.id === selected),
  );
  if (visible.length === 0) return null;

  const groups = new Map<string, Concept[]>();
  for (const c of visible) {
    const list = groups.get(c.category);
    if (list) list.push(c);
    else groups.set(c.category, [c]);
  }
  const rank = (category: string) => {
    const i = GROUP_ORDER.indexOf(category);
    return i === -1 ? GROUP_ORDER.length : i;
  };
  const ordered = [...groups.entries()].sort(([a], [b]) => rank(a) - rank(b));

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: '2px',
        margin: '2px 0 6px 12px',
        paddingLeft: '8px',
        borderLeft: '1px solid var(--border)',
      }}
    >
      {ordered.map(([category, list]) => (
        <div key={category} style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
          {!collapsed && <span
            style={{
              fontSize: '11px',
              fontWeight: 650,
              textTransform: 'uppercase',
              letterSpacing: '0.05em',
              color: 'var(--text-muted)',
              padding: '8px 8px 2px',
            }}
          >
            {groupLabel(category)}
          </span>}
          {list.map((c) => {
            const active = selected === c.id;
            return (
              <button
                key={c.id}
                onClick={() => onSelect(active ? null : c.id)}
                aria-pressed={active}
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  gap: '6px',
                  padding: '6px 8px',
                  borderRadius: 'var(--radius)',
                  border: 'none',
                  background: active ? 'var(--surface-brand)' : 'transparent',
                  color: active ? 'var(--brand-lilac)' : 'var(--brand-charcoal)',
                  fontWeight: active ? 700 : 550,
                  fontSize: '13px',
                  width: '100%',
                  cursor: 'pointer',
                  textAlign: 'left',
                  transition: 'background 140ms ease, color 140ms ease',
                }}
              >
                <span>{c.display_name}</span>
                <span style={{ fontSize: '11px', opacity: 0.8 }}>{counts.get(c.id)}</span>
              </button>
            );
          })}
        </div>
      ))}
    </div>
  );
}
