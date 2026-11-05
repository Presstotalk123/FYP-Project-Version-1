'use client';

import { useEffect, useRef, useState, type CSSProperties, type PointerEvent, type ReactNode } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { ActionIcon, Alert, Badge, Button, Group, Loader, Modal, MultiSelect, Select, Stack, Text, Textarea, TextInput, Tooltip } from '@mantine/core';
import { IconAlertTriangle, IconArrowBackUp, IconArrowForwardUp, IconArrowsSplit2, IconCheck, IconHistory, IconLayoutDistributeVertical, IconPlus, IconTrash, IconX } from '@tabler/icons-react';
import { ReactFlow, Background, BaseEdge, Controls, EdgeLabelRenderer, Handle, Position, MarkerType, type Edge, type EdgeProps, type Node, type NodeProps, type ReactFlowInstance } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { useAuth } from '@/contexts/AuthContext';
import { useAssessmentTimer } from '@/contexts/AssessmentTimerContext';
import { useNormalizationDraft, type NormalizationDraft } from '@/hooks/use-normalization-draft';
import { useWarnBeforeUnload } from '@/hooks/use-warn-before-unload';
import { DescriptionMarkdown } from '@/components/common/DescriptionMarkdown';
import { normalizationService, normalizationError } from '@/services/normalization.service';
import { queryKeys } from '@/services/query-keys';
import type { NormalizationAttempt, NormalizationFD, NormalizationQuestion, NormalizationRelation, NormalizationStep } from '@/types/normalization.types';
import styles from './NormalizationWorkspace.module.css';

const emptyFD = (): NormalizationFD => ({ lhs: [], rhs: [] });
const fdText = (fd: NormalizationFD) => `${fd.lhs.join(', ')} → ${fd.rhs.join(', ')}`;
const relation = (node_id: string, name = ''): NormalizationRelation => ({ node_id, name, attributes: [], primary_key: [] });

function layoutPositions(relations: NormalizationRelation[], steps: NormalizationStep[]) {
  const depth = new Map<string, number>([['root', 0]]);
  let changed = true;
  while (changed) {
    changed = false;
    for (const step of steps) {
      const parentDepth = depth.get(step.parent_node_id);
      if (parentDepth === undefined) continue;
      for (const child of step.children) if (!depth.has(child.node_id)) {
        depth.set(child.node_id, parentDepth + 1); changed = true;
      }
    }
  }
  const groups = new Map<number, NormalizationRelation[]>();
  for (const r of relations) {
    const level = depth.get(r.node_id) ?? (r.node_id === 'root' ? 0 : 1);
    groups.set(level, [...(groups.get(level) ?? []), r]);
  }
  return relations.map(r => {
    const level = depth.get(r.node_id) ?? (r.node_id === 'root' ? 0 : 1);
    const group = groups.get(level)!;
    return { node_id: r.node_id, x: 420 - Math.max(1, group.length) * 250 / 2 + group.indexOf(r) * 250, y: 45 + level * 260 };
  });
}

function DecompositionEdge({ id, sourceX, sourceY, targetX, targetY, markerEnd, style, label }: EdgeProps) {
  const branchY = sourceY + 36;
  return <><BaseEdge id={id} path={`M ${sourceX},${sourceY} L ${sourceX},${branchY} L ${targetX},${branchY} L ${targetX},${targetY}`} markerEnd={markerEnd} style={style} />
    {label && <EdgeLabelRenderer><div className={`${styles.edgeLabel} nodrag nopan`} style={{ transform: `translate(-50%, -50%) translate(${sourceX}px, ${branchY}px)` }}>{String(label)}</div></EdgeLabelRenderer>}</>;
}
const edgeTypes = { decomposition: DecompositionEdge };

type RelationData = Record<string, unknown> & {
  relation: NormalizationRelation; leaf: boolean; onEdit: () => void; editor?: ReactNode; onKeyChange: (key: string[]) => void;
};
type RelationNode = Node<RelationData, 'relation'>;

function RelationCard({ data, selected }: NodeProps<RelationNode>) {
  return <div className={`${styles.relation} ${selected ? styles.selected : ''} ${!data.leaf ? styles.intermediate : ''}`}>
    <Handle type="target" position={Position.Top} />
    <div className={styles.relationHeader}><strong>{data.relation.name}</strong></div>
    <div className={styles.attributes}>{data.relation.attributes.map(a =>
      <div key={a}>{data.leaf ? <Tooltip label="Toggle proposed key" openDelay={600}><button type="button" className={`${styles.attributeButton} ${data.relation.primary_key.includes(a) ? styles.key : ''} nodrag nopan`}
        aria-label={`Propose ${a} as key`} aria-pressed={data.relation.primary_key.includes(a)} onClick={() => data.onKeyChange(data.relation.primary_key.includes(a)
          ? data.relation.primary_key.filter(key => key !== a) : [...data.relation.primary_key, a])}>{a}</button></Tooltip>
        : <span className={data.relation.primary_key.includes(a) ? styles.key : ''}>{a}</span>}</div>)}</div>
    {data.leaf && selected && !data.editor && <button type="button" className={`${styles.splitTrigger} nodrag nopan`}
      onClick={event => { event.stopPropagation(); data.onEdit(); }}><IconArrowsSplit2 size={14} /><span>Decompose</span></button>}
    {data.editor && <div className={`${styles.inlineEditor} nodrag nopan nowheel`} onClick={event => event.stopPropagation()} onKeyDown={event => event.stopPropagation()}>{data.editor}</div>}
    <Handle type="source" position={Position.Bottom} />
  </div>;
}
const nodeTypes = { relation: RelationCard };

export function NormalizationFeedback({ attempt }: { attempt: NormalizationAttempt }) {
  if (attempt.feedback_hidden) return <Alert color="blue">Submitted successfully. Feedback is hidden for this question.</Alert>;
  if (!attempt.result) return <Alert color={attempt.status === 'failed' ? 'red' : 'blue'}>
    {attempt.status === 'failed' ? 'Grading did not finish. Your submitted work is preserved. Contact staff or submit a new attempt.' : 'Your submission is saved. Grading is in progress.'}</Alert>;
  const { result } = attempt;
  const formal = result.normalization_evaluation;
  const checks: [string, boolean, boolean?][] = [
    ['FD interpretation', result.fd_evaluation.decision === 'accepted'],
    ['Attribute coverage', formal.attribute_coverage], ['Lossless join', formal.lossless_join],
    ['Target normal form', formal.relations_satisfy_target], ['Proposed keys', formal.proposed_keys_correct],
    ['Dependency preservation', formal.dependency_preservation, !formal.dependency_preservation_required],
    ['Process', formal.process_evaluation.valid],
  ];
  return <Stack gap="sm">
    <div className={`${styles.evaluationHero} ${result.decision === 'accepted' ? styles.acceptedHero : styles.revisionHero}`}>
      {result.decision === 'accepted' ? <IconCheck size={28} /> : <IconAlertTriangle size={28} />}<div><strong>{result.decision === 'accepted' ? 'Complete solution accepted' : result.decision === 'staff_review' ? 'Review required' : 'Revision needed'}</strong>
        <p>Overall score: {result.score.overall_percent}%</p>{result.decision === 'staff_review' && <Text size="xs">Provisional score · staff review required</Text>}</div>
    </div>
    <div className={styles.scoreGrid}><div><span>Functional dependencies</span><strong>{result.score.fd_percent}%</strong><small>{result.fd_evaluation.feedback}</small></div><div><span>Normalization</span><strong>{result.score.normalization_percent}%</strong><small>{formal.note}</small></div></div>
    {result.fd_evaluation.formal_evidence.sample_contradictions.map((c, i) => <Text key={i} c="red">{fdText(c)} contradicts sample rows {c.first_row} and {c.second_row}.</Text>)}
    <div className={styles.checks}>{checks.map(([label, pass, optional]) => <div className={styles.check} key={label}>{pass ? <IconCheck size={17} color="#2b8a3e" /> : <IconX size={17} color={optional ? '#868e96' : '#c92a2a'} />}<span>{label}</span>{optional && <small>informational</small>}</div>)}</div>
    {formal.process_evaluation.errors.map((error, i) => <Text c="red" key={i}>{error}</Text>)}
    <details className={styles.attemptFeedback}><summary>Detailed feedback</summary>{formal.process_evaluation.step_results.map((s, i) => <Text size="sm" key={i}>{s.step}: {s.feedback}</Text>)}
      {formal.relation_results.map((r, i) => <Text size="sm" key={i}>{r.name}: candidate keys {r.candidate_keys.map(k => k.join(', ')).join(' / ')}{r.violations.length ? `; ${r.violations.join('; ')}` : ''}</Text>)}</details>
    {attempt.reviews.map(review => <Text size="sm" key={review.id}>{review.decision === 'requested' ? 'Review requested' : `Staff decision: ${review.decision}`} — {review.reason}</Text>)}
  </Stack>;
}

export function NormalizationWorkspace({ questionId, preview = false, assessmentId }: { questionId: number; preview?: boolean; assessmentId?: number }) {
  const { user } = useAuth();
  const question = useQuery({ queryKey: queryKeys.normalizationQuestion(questionId, user?.id ?? 0), queryFn: () => normalizationService.question(questionId), enabled: questionId > 0, refetchOnMount: true });
  if (question.isLoading) return <Loader aria-label="Loading normalization question" />;
  if (question.error) return <Alert color="red">{normalizationError(question.error)}</Alert>;
  if (!question.data) return <Alert color="red">Question not found.</Alert>;
  return <Workspace key={`${questionId}:${question.data.version}:${user?.id}:${assessmentId ?? 'practice'}:${preview}`} question={question.data} preview={preview} assessmentId={assessmentId} />;
}

function Workspace({ question, preview, assessmentId }: { question: NormalizationQuestion; preview: boolean; assessmentId?: number }) {
  const { user } = useAuth();
  const cache = useQueryClient();
  const timer = useAssessmentTimer();
  const initial: NormalizationDraft = {
    fds: [emptyFD()], assumption: '', root: { ...relation('root', question.relation_name), attributes: question.attributes }, steps: [], positions: [],
  };
  const storageKey = `normalization:v1:${user?.id}:${question.id}:${question.version}:${assessmentId ?? 'practice'}`;
  const state = useNormalizationDraft(storageKey, initial, !preview);
  const { draft, change } = state;
  const [selected, setSelected] = useState<string | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const [fdIndex, setFdIndex] = useState<string | null>(null);
  const [children, setChildren] = useState([relation('left'), relation('right')]);
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [confirmSubmit, setConfirmSubmit] = useState(false);
  const [attempt, setAttempt] = useState<NormalizationAttempt | null>(null);
  const [reopening, setReopening] = useState<NormalizationAttempt | null>(null);
  const [reviewReason, setReviewReason] = useState('');
  const [paneWidths, setPaneWidths] = useState({ left: 320, right: 260 });
  const [measurements, setMeasurements] = useState<Record<string, { width: number; height: number }>>({});
  const grid = useRef<HTMLDivElement>(null);
  const resizing = useRef<{ side: 'left' | 'right'; start: number; width: number } | null>(null);
  const request = useRef<{ signature: string; key: string } | null>(null);
  const flow = useRef<ReactFlowInstance<RelationNode> | null>(null);
  useWarnBeforeUnload(!preview);
  const history = useQuery({ queryKey: queryKeys.normalizationHistory(question.id, user?.id ?? 0), queryFn: () => normalizationService.history(question.id), enabled: !preview, refetchOnMount: true });
  const pending = useQuery({ queryKey: ['normalizationPending', attempt?.id, user?.id], queryFn: () => normalizationService.attempt(attempt!.id),
    enabled: !!attempt && attempt.status === 'processing', refetchInterval: 2000 });
  useEffect(() => { if (pending.data && pending.data.status !== 'processing') { setAttempt(pending.data); void cache.invalidateQueries({ queryKey: ['normalization'] }); } }, [pending.data, cache]);
  const parents = new Set(draft.steps.map(s => s.parent_node_id));
  const relations = [draft.root, ...draft.steps.flatMap(s => s.children)];
  const leaves = relations.filter(r => !parents.has(r.node_id));
  const completeFDs = draft.fds.filter(fd => fd.lhs.length && fd.rhs.length);

  function resizePane(side: 'left' | 'right', width: number) {
    setPaneWidths(current => {
      const otherWidth = window.matchMedia('(max-width: 1150px)').matches ? 0 : current[side === 'left' ? 'right' : 'left'];
      return { ...current, [side]: Math.max(side === 'left' ? 280 : 240, Math.min(width, 620, (grid.current?.clientWidth ?? 1300) - otherWidth - 336)) };
    });
  }

  function divider(side: 'left' | 'right') {
    const onMove = (event: PointerEvent<HTMLDivElement>) => {
      if (!resizing.current || resizing.current.side !== side) return;
      resizePane(side, resizing.current.width + (event.clientX - resizing.current.start) * (side === 'left' ? 1 : -1));
    };
    return <div className={styles.divider} role="separator" tabIndex={0} aria-orientation="vertical"
      aria-label={`Resize ${side === 'left' ? 'problem' : 'attempt history'} panel`} aria-valuenow={Math.round(paneWidths[side])} aria-valuemin={side === 'left' ? 280 : 240} aria-valuemax={620}
      onPointerDown={event => { resizing.current = { side, start: event.clientX, width: paneWidths[side] }; event.currentTarget.setPointerCapture(event.pointerId); }}
      onPointerMove={onMove} onPointerUp={() => { resizing.current = null; }} onPointerCancel={() => { resizing.current = null; }}
      onLostPointerCapture={() => { resizing.current = null; }} onDoubleClick={() => resizePane(side, side === 'left' ? 320 : 260)}
      onKeyDown={event => { if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') { event.preventDefault(); resizePane(side, paneWidths[side] + (event.key === 'ArrowRight' ? 20 : -20) * (side === 'left' ? 1 : -1)); } }} />;
  }

  function split(parent: NormalizationRelation) {
    if (fdIndex === null || !completeFDs[Number(fdIndex)]) { setError('Choose a functional dependency for this split.'); return; }
    if (children.some(c => !c.name.trim() || !c.attributes.length)) { setError('Each child needs a name and attributes.'); return; }
    const id = crypto.randomUUID();
    const steps = [...draft.steps, { step_id: id, parent_node_id: parent.node_id, selected_fd: completeFDs[Number(fdIndex)],
      children: children.map((c, i) => ({ ...c, name: c.name.trim(), node_id: `${id}-${i}` })) }];
    const parentIndex = relations.findIndex(r => r.node_id === parent.node_id);
    const position = draft.positions.find(p => p.node_id === parent.node_id) ?? { node_id: parent.node_id,
      x: 310 + (parentIndex % 2) * 250, y: 56 + Math.ceil(parentIndex / 2) * 260 };
    const committed = steps[steps.length - 1];
    change({ ...draft, steps, positions: [...draft.positions.filter(p => p.node_id !== parent.node_id), position,
      ...committed.children.map((child, i) => ({ node_id: child.node_id, x: position.x + (i === 0 ? -145 : 145), y: position.y + 250 }))] });
    setSelected(committed.children[0].node_id); setEditing(null); setError('');
    setTimeout(() => flow.current?.fitView({ padding: 0.22, duration: 300 }), 140);
  }

  function editor(parent: NormalizationRelation) {
    return <>
      <div className={styles.editorStem}><IconArrowsSplit2 size={18} /></div>
      <div className={styles.editorFdControl}><Select size="xs" aria-label="Dependency used for this split" placeholder="Select FD" value={fdIndex} onChange={setFdIndex}
        data={completeFDs.flatMap((fd, i) => [...fd.lhs, ...fd.rhs].every(a => parent.attributes.includes(a)) ? [{ value: String(i), label: fdText(fd) }] : [])} />
        <ActionIcon aria-label="Cancel decomposition" variant="subtle" onClick={() => setEditing(null)}><IconX size={16} /></ActionIcon>
      </div>
      <div className={styles.editorBranches} aria-hidden="true"><span /><span /></div>
      <div className={styles.children}>{children.map((child, i) => <Stack key={i} gap={0} className={styles.childEditor}>
        <TextInput size="xs" aria-label={`Child ${i + 1} name`} placeholder="Relation name" value={child.name} onChange={e => { const name = e.currentTarget.value; setChildren(old => old.map((c, j) => i === j ? { ...c, name } : c)); }} />
        <MultiSelect size="xs" aria-label={`Child ${i + 1} attributes`} placeholder="Choose attributes" data={parent.attributes} value={child.attributes} onChange={attributes => setChildren(old => old.map((c, j) => i === j ? { ...c, attributes, primary_key: c.primary_key.filter(a => attributes.includes(a)) } : c))} />
        <MultiSelect size="xs" aria-label={`Child ${i + 1} proposed key`} placeholder="Underline key attributes" data={child.attributes} value={child.primary_key} onChange={primary_key => setChildren(old => old.map((c, j) => i === j ? { ...c, primary_key } : c))} />
      </Stack>)}</div>
      {error && <Alert color="red" mt="xs" py={6}>{error}</Alert>}
      <Group justify="center" mt="sm"><Button size="xs" variant="default" onClick={() => setEditing(null)}>Cancel</Button><Button size="xs" onClick={() => split(parent)}>Add split</Button></Group>
    </>;
  }

  const nodes: RelationNode[] = relations.map((r, i) => {
    const position = draft.positions.find(p => p.node_id === r.node_id);
    const defaultPosition = { x: 310 + (i % 2) * 250, y: 56 + Math.ceil(i / 2) * 260 };
    return { id: r.node_id, type: 'relation', selected: selected === r.node_id, measured: measurements[r.node_id], position: position ? { x: position.x, y: position.y } : defaultPosition,
      data: { relation: r, leaf: !parents.has(r.node_id), editor: editing === r.node_id ? editor(r) : undefined,
        onKeyChange: primary_key => change(d => r.node_id === 'root' ? { ...d, root: { ...d.root, primary_key } }
          : { ...d, steps: d.steps.map(s => ({ ...s, children: s.children.map(c => c.node_id === r.node_id ? { ...c, primary_key } : c) })) }), onEdit: () => {
        setSelected(r.node_id); setEditing(r.node_id); setFdIndex(null); setError('');
        setChildren([relation('left', `R${draft.steps.length * 2 + 1}`), relation('right', `R${draft.steps.length * 2 + 2}`)]);
        setTimeout(() => flow.current?.setCenter((position?.x ?? defaultPosition.x) + 102, (position?.y ?? defaultPosition.y) + 320, { zoom: 0.9, duration: 300 }), 20);
      } } };
  });
  const edges: Edge[] = draft.steps.flatMap(step => step.children.map((child, i) => ({ id: `${step.step_id}:${child.node_id}`, source: step.parent_node_id, target: child.node_id,
    type: 'decomposition', markerEnd: { type: MarkerType.ArrowClosed, color: '#75549c' }, label: i === 0 ? fdText(step.selected_fd) : undefined,
    style: { stroke: '#75549c', strokeWidth: 1.5 } })));

  function autoLayout() {
    change({ ...draft, positions: layoutPositions(relations, draft.steps) });
    setTimeout(() => flow.current?.fitView({ padding: 0.2, duration: 300 }), 20);
  }

  function removeSplit() {
    if (!editing && selected && selected !== 'root') {
      const step = draft.steps.find(s => s.children.some(c => c.node_id === selected));
      if (!step) return;
      const removed = new Set(step.children.map(c => c.node_id));
      draft.steps.forEach(s => { if (removed.has(s.parent_node_id)) s.children.forEach(c => removed.add(c.node_id)); });
      change({ ...draft, steps: draft.steps.filter(s => s !== step && !removed.has(s.parent_node_id)), positions: draft.positions.filter(p => !removed.has(p.node_id)) });
      setSelected(step.parent_node_id);
    }
  }

  async function submit() {
    if (!completeFDs.length || completeFDs.length !== draft.fds.length) { setError('Complete both sides of each FD before submitting.'); return; }
    setSubmitting(true); setError(''); timer.pause();
    const body = { exercise_id: String(question.id), exercise_version: question.version, target_normal_form: question.target_normal_form,
      functional_dependencies: draft.fds, assumption: question.semantic_judge_enabled ? draft.assumption : '', relations: leaves.map(r => ({ name: r.name, attributes: r.attributes, primary_key: r.primary_key })),
      process: { workflow: 'recursive_decomposition' as const, root: draft.root, steps: draft.steps }, canvas_positions: draft.positions };
    const signature = JSON.stringify(body);
    if (request.current?.signature !== signature) request.current = { signature, key: crypto.randomUUID() };
    try {
      const result = await normalizationService.submit(question.id, { ...body, request_key: request.current.key }, preview);
      setAttempt(result); setConfirmSubmit(false); request.current = null;
      await cache.invalidateQueries({ queryKey: ['normalization'] });
      await cache.invalidateQueries({ queryKey: queryKeys.assessmentAnalyticsSummary });
    } catch (e) { setError(normalizationError(e)); } finally { setSubmitting(false); timer.resume(); }
  }

  function reopen(item: NormalizationAttempt) {
    change({ fds: item.payload.functional_dependencies, assumption: item.payload.assumption, root: item.payload.process.root,
      steps: item.payload.process.steps, positions: item.payload.canvas_positions });
    setAttempt(null); setReopening(null); setEditing(null); setSelected('root'); request.current = null;
  }

  if (!state.ready) return <Loader />;
  return <div className={`${styles.workspace} ${!assessmentId && !preview ? styles.practice : ''}`}>
    {error && <Alert color="red" role="alert">{error}</Alert>}
    {state.storageError && <Alert color="orange">{state.storageError}</Alert>}
    <div className={styles.columns} ref={grid} style={{ '--left-pane': `${paneWidths.left}px`, '--right-pane': `${paneWidths.right}px` } as CSSProperties}>
      <aside className={styles.contextPane} aria-label="Problem and functional dependencies">
        <section className={styles.problem}>
          <div className={styles.panelHeading}><h1>{question.title}</h1><Badge size="sm" variant="light">{question.target_normal_form}</Badge></div>
          <div className={styles.panelBody}><div className={styles.scenario}><DescriptionMarkdown content={question.scenario} fontSize={14} /></div>
            <ol className={styles.rules}>{question.statements.map(s => <li key={s.id}>{s.text}</li>)}</ol>
            <div className={styles.schema}><strong>{question.relation_name}</strong><span>({question.attributes.join(', ')})</span></div>
          </div>
        </section>
        <section className={styles.fdPanel}>
          <div className={styles.panelHeading}><h2>Functional dependencies</h2></div>
          <div className={styles.panelBody}><Stack gap="sm">
          {draft.fds.map((fd, i) => <div className={styles.fd} key={i}>
            <span className={styles.fdNumber}>{i + 1}</span><MultiSelect size="xs" hidePickedOptions={false} aria-label={`FD ${i + 1} determinant`} data={question.attributes} value={fd.lhs} onChange={lhs => change({ ...draft, fds: draft.fds.map((f, j) => i === j ? { ...f, lhs } : f) })} />
            <span aria-hidden="true">→</span><MultiSelect size="xs" hidePickedOptions={false} aria-label={`FD ${i + 1} dependent`} data={question.attributes} value={fd.rhs} onChange={rhs => change({ ...draft, fds: draft.fds.map((f, j) => i === j ? { ...f, rhs } : f) })} />
            <ActionIcon variant="subtle" color="gray" aria-label={`Remove FD ${i + 1}`} onClick={() => change({ ...draft, fds: draft.fds.length === 1 ? [emptyFD()] : draft.fds.filter((_, j) => i !== j) })}><IconX size={15} /></ActionIcon>
          </div>)}
          <Button variant="subtle" size="xs" leftSection={<IconPlus size={14} />} disabled={draft.fds.length >= 64} onClick={() => change({ ...draft, fds: [...draft.fds, emptyFD()] })}>Add functional dependency</Button>
        </Stack></div></section>
      </aside>
      {divider('left')}
      <section className={styles.canvasPane} aria-label="Normalization canvas">
        <div className={styles.canvasBar}><h2>Decomposition</h2><div className={styles.toolbar} role="toolbar" aria-label="Canvas tools">
          <Tooltip label="Undo"><ActionIcon aria-label="Undo" variant="subtle" disabled={!state.canUndo} onClick={state.undo}><IconArrowBackUp size={18} /></ActionIcon></Tooltip>
          <Tooltip label="Redo"><ActionIcon aria-label="Redo" variant="subtle" disabled={!state.canRedo} onClick={state.redo}><IconArrowForwardUp size={18} /></ActionIcon></Tooltip>
          <Tooltip label="Arrange"><ActionIcon aria-label="Auto-layout" variant="subtle" onClick={autoLayout}><IconLayoutDistributeVertical size={18} /></ActionIcon></Tooltip>
          <Tooltip label="Remove selected split"><ActionIcon aria-label="Remove split" variant="subtle" color="red" disabled={!selected || selected === 'root' || !!editing} onClick={removeSplit}><IconTrash size={18} /></ActionIcon></Tooltip>
          {!!draft.steps.length && <Text size="xs" c="dimmed">{draft.steps.length} {draft.steps.length === 1 ? 'step' : 'steps'}</Text>}
          {preview && <Badge size="xs" color="yellow">Preview</Badge>}
          <Button size="xs" onClick={() => setConfirmSubmit(true)}>Submit</Button>
        </div></div>
        <div className={styles.canvas}><ReactFlow nodes={nodes} edges={edges} nodeTypes={nodeTypes} edgeTypes={edgeTypes} fitView fitViewOptions={{ padding: 0.25 }} minZoom={0.35} maxZoom={1.7} onInit={instance => { flow.current = instance; }}
          onNodesChange={changes => {
            for (const change of changes) if (change.type === 'select' && change.selected) setSelected(change.id);
            const dimensions = changes.filter(change => change.type === 'dimensions' && change.dimensions);
            if (dimensions.length) setMeasurements(current => {
              const next = { ...current };
              for (const change of dimensions) if (change.type === 'dimensions' && change.dimensions) next[change.id] = change.dimensions;
              return next;
            });
          }}
          onNodeClick={(_, node) => setSelected(node.id)} onNodeDragStart={() => change(d => d)}
          onPaneClick={() => { if (!editing) setSelected(null); }}
          onNodeDrag={(_, node) => state.move(node.id, node.position)} onNodeDragStop={(_, node) => state.move(node.id, node.position)}
          nodesConnectable={false} deleteKeyCode={null}><Background gap={18} size={1} color="#d9d4e4" /><Controls showInteractive={false} fitViewOptions={{ padding: 0.25 }} /></ReactFlow></div>
      </section>
      {divider('right')}
      <aside className={styles.inspectorPane} aria-label="Attempt history">
          <div className={styles.panelHeading}><h2>Attempts</h2><span className={styles.attemptCount}>{history.data?.length ?? 0}</span></div>
          <div className={styles.inspectorBody}>
            {history.isLoading && <Loader size="sm" />}{history.error && <Alert color="red">{normalizationError(history.error)}</Alert>}
            {preview ? <Text size="sm" c="dimmed">Preview evaluations do not create student attempts.</Text> : <>
              {(history.data ?? []).map((item, i) => <article className={styles.attemptItem} key={item.id}>
                <Group justify="space-between" gap={4}><button type="button" className={styles.attemptTitle} aria-label="View submission result" onClick={() => setAttempt(item)}>Attempt {(history.data?.length ?? 0) - i}</button>
                  {item.result && !item.feedback_hidden && <Badge size="sm" color={item.result.decision === 'accepted' ? 'green' : item.result.decision === 'staff_review' ? 'yellow' : 'red'}>{item.result.decision === 'accepted' ? 'Accepted' : item.result.decision === 'staff_review' ? 'Review' : 'Revise'}</Badge>}</Group>
                <Text size="xs" c="dimmed" mt={4}>{item.created_at ? new Date(item.created_at).toLocaleString(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : 'Saved attempt'}</Text>
                {item.result && !item.feedback_hidden && <><Text size="xs" mt="xs">Score {item.result.score.overall_percent}%</Text><details className={styles.attemptFeedback}><summary>Feedback</summary>
                  <Text size="xs" mt="xs"><strong>FDs:</strong> {item.result.fd_evaluation.feedback}</Text><Text size="xs" mt={4}><strong>Normalization:</strong> {item.result.score.normalization_percent}%</Text>
                </details></>}
                <Button size="compact-xs" variant="subtle" aria-label="Reopen copy" mt="xs" disabled={String(item.question_version) !== question.version} onClick={() => setReopening(item)}>Reopen</Button>
              </article>)}
              {!history.isLoading && !history.data?.length && <div className={styles.emptyHistory}><IconHistory size={30} /><Text fw={700} size="sm">No submissions yet</Text><Text size="sm" c="dimmed">Completed evaluations will appear here.</Text></div>}
            </>}
          </div>
      </aside>
    </div>
    <Modal opened={confirmSubmit} onClose={() => !submitting && setConfirmSubmit(false)} title={question.semantic_judge_enabled ? 'Add an assumption (optional)' : 'Submit complete solution'} closeButtonProps={{ 'aria-label': 'Close submission confirmation' }} classNames={{ content: styles.workspaceModal }} centered size="lg">
      <Text>Evaluate your functional dependencies and normalization together. Submitted attempts remain in history.</Text>
      <div className={styles.submissionSummary}><span><strong>{completeFDs.length}</strong>functional dependencies</span><span><strong>{leaves.length}</strong>final relations</span><span><strong>{draft.steps.length}</strong>decomposition steps</span></div>
      {question.semantic_judge_enabled && <Textarea mt="md" label="Assumptions" description="Optional: explain an assumption behind your interpretation of the business rules."
        placeholder="Record an interpretation, if needed…" autosize minRows={3} maxRows={5} maxLength={1000} value={draft.assumption} onChange={e => change({ ...draft, assumption: e.currentTarget.value })} />}
      {error && <Alert color="red" mt="sm">{error}</Alert>}<Group justify="flex-end" mt="md"><Button variant="default" disabled={submitting} onClick={() => setConfirmSubmit(false)}>Continue editing</Button><Button loading={submitting} onClick={submit}>Evaluate both sections</Button></Group>
    </Modal>
    <Modal opened={!!reopening} onClose={() => setReopening(null)} title="Replace current draft?" closeButtonProps={{ 'aria-label': 'Close reopen confirmation' }} centered><Text>Reopening replaces your current FD and decomposition work. The submitted attempt stays unchanged.</Text>
      <Group mt="md"><Button variant="default" onClick={() => setReopening(null)}>Cancel</Button><Button onClick={() => reopening && reopen(reopening)}>Reopen copy</Button></Group></Modal>
    <Modal opened={!!attempt} onClose={() => setAttempt(null)} title="Submit complete solution" closeButtonProps={{ 'aria-label': 'Close submission result' }} classNames={{ content: styles.workspaceModal }} centered size="lg">
      {attempt && <NormalizationFeedback attempt={attempt} />}
      {attempt?.result && !preview && <details className={styles.attemptFeedback}><summary>Request staff review</summary><Stack mt="sm"><Textarea label="Request staff review of FD interpretation" value={reviewReason} onChange={e => setReviewReason(e.currentTarget.value)} maxLength={2000} />
        <Button variant="light" disabled={!reviewReason.trim()} onClick={async () => {
          try { setAttempt(await normalizationService.requestReview(attempt.id, reviewReason)); setReviewReason(''); await history.refetch(); }
          catch (e) { setError(normalizationError(e)); }
        }}>Request review</Button></Stack></details>}
      <Group justify="flex-end" mt="md"><Button onClick={() => setAttempt(null)}>Return to workspace</Button></Group>
    </Modal>
  </div>;
}
