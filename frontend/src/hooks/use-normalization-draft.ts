'use client';

import { useCallback, useEffect, useReducer, useState } from 'react';
import type { NormalizationFD, NormalizationRelation, NormalizationStep } from '@/types/normalization.types';

export interface NormalizationDraft {
  fds: NormalizationFD[]; assumption: string; root: NormalizationRelation; steps: NormalizationStep[];
  positions: { node_id: string; x: number; y: number }[];
}

type Timeline = { draft: NormalizationDraft; past: NormalizationDraft[]; future: NormalizationDraft[] };
type Action = { type: 'change'; update: NormalizationDraft | ((previous: NormalizationDraft) => NormalizationDraft) }
  | { type: 'restore'; draft: NormalizationDraft } | { type: 'undo' | 'redo' }
  | { type: 'move'; nodeId: string; position: { x: number; y: number } };

function reducer(state: Timeline, action: Action): Timeline {
  if (action.type === 'restore') return { draft: action.draft, past: [], future: [] };
  if (action.type === 'change') return {
    draft: typeof action.update === 'function' ? action.update(state.draft) : action.update,
    past: [...state.past.slice(-49), state.draft], future: [],
  };
  if (action.type === 'move') return { ...state, draft: { ...state.draft,
    positions: [...state.draft.positions.filter(p => p.node_id !== action.nodeId), { node_id: action.nodeId, ...action.position }] } };
  if (action.type === 'undo' && state.past.length) return {
    draft: state.past[state.past.length - 1], past: state.past.slice(0, -1), future: [...state.future, state.draft],
  };
  if (action.type === 'redo' && state.future.length) return {
    draft: state.future[state.future.length - 1], past: [...state.past, state.draft], future: state.future.slice(0, -1),
  };
  return state;
}

function validDraft(value: unknown, attributes: string[]): value is NormalizationDraft {
  const draft = value as NormalizationDraft | undefined;
  const names = (values: unknown): values is string[] => Array.isArray(values) && values.length <= 8
    && values.every(v => typeof v === 'string' && attributes.includes(v));
  const fd = (value: NormalizationFD) => !!value && names(value.lhs) && names(value.rhs);
  const relation = (value: NormalizationRelation) => !!value && typeof value.node_id === 'string'
    && typeof value.name === 'string' && names(value.attributes) && names(value.primary_key);
  return !!draft && typeof draft.assumption === 'string' && draft.assumption.length <= 1000
    && Array.isArray(draft.fds) && draft.fds.length <= 64 && draft.fds.every(fd)
    && relation(draft.root) && draft.root.node_id === 'root'
    && Array.isArray(draft.steps) && draft.steps.length <= 49 && draft.steps.every(s => s
      && typeof s.step_id === 'string' && typeof s.parent_node_id === 'string' && fd(s.selected_fd)
      && Array.isArray(s.children) && s.children.length === 2 && s.children.every(relation))
    && Array.isArray(draft.positions) && draft.positions.length <= 100
    && draft.positions.every(p => p && typeof p.node_id === 'string' && Number.isFinite(p.x) && Number.isFinite(p.y));
}

export function useNormalizationDraft(key: string, initial: NormalizationDraft, persist: boolean) {
  const [timeline, dispatch] = useReducer(reducer, { draft: initial, past: [], future: [] });
  const { draft } = timeline;
  const [ready, setReady] = useState(false);
  const [storageError, setStorageError] = useState('');
  const attributes = initial.root.attributes.join('\u0000');
  useEffect(() => {
    if (persist) {
      try {
        const stored = JSON.parse(localStorage.getItem(key) || 'null');
        if (stored?.schema === 1 && validDraft(stored.draft, attributes.split('\u0000')))
          dispatch({ type: 'restore', draft: stored.draft });
      // Browser storage is hydrated after mount so server and client markup agree.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      } catch { setStorageError('The saved draft could not be restored.'); }
    }
    setReady(true);
  }, [key, persist, attributes]);
  useEffect(() => {
    if (!ready || !persist) return;
    try { localStorage.setItem(key, JSON.stringify({ schema: 1, draft })); }
    // eslint-disable-next-line react-hooks/set-state-in-effect -- Report failure of the external storage write.
    catch { setStorageError('Draft storage is unavailable. Keep this tab open until you submit.'); }
  }, [draft, key, persist, ready]);
  const change = useCallback((update: NormalizationDraft | ((previous: NormalizationDraft) => NormalizationDraft)) => {
    dispatch({ type: 'change', update });
  }, []);
  const undo = () => dispatch({ type: 'undo' });
  const redo = () => dispatch({ type: 'redo' });
  const move = (nodeId: string, position: { x: number; y: number }) => dispatch({ type: 'move', nodeId, position });
  return { draft, change, move, undo, redo, ready, storageError, canUndo: timeline.past.length > 0, canRedo: timeline.future.length > 0 };
}
