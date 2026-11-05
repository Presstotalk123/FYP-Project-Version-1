'use client';

import { useState, type ReactNode } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Button, Group, Loader, Modal, MultiSelect, Select, Stack, Switch, Table, TagsInput, Text, TextInput, Textarea } from '@mantine/core';
import { MarkdownDescriptionField } from '@/components/common/MarkdownDescriptionField';
import { NormalizationWorkspace } from './NormalizationWorkspace';
import { normalizationError, normalizationService } from '@/services/normalization.service';
import type { NormalizationAuthoring, NormalizationQuestionInput } from '@/types/normalization.types';
import styles from './NormalizationStaff.module.css';

const blank: NormalizationQuestionInput = {
  version: 1, title: '', difficulty: 'easy', scenario: '', relation_name: 'R', attributes: [],
  statements: [{ id: 'S1', text: '' }], sample_rows: [], target_normal_form: '3NF',
  approved_fds: [{ lhs: [], rhs: [] }], semantic_judge_enabled: false, hide_correctness: false,
};

function FormSection({ id, number, title, description, children }: { id: string; number: string; title: string; description: string; children: ReactNode }) {
  return <section id={id} className={styles.section}>
    <header className={styles.sectionHeading}><span>{number}</span><div><h2>{title}</h2><Text size="sm" c="dimmed">{description}</Text></div></header>
    <Stack gap="md" p="lg">{children}</Stack>
  </section>;
}

export function NormalizationQuestionForm({ questionId, onSaved, onCancel }: { questionId?: number; onSaved: () => void; onCancel: () => void }) {
  const existing = useQuery({ queryKey: ['normalization', 'authoring', questionId], queryFn: () => normalizationService.authoring(questionId!), enabled: !!questionId, refetchOnMount: true });
  if (existing.isLoading) return <Loader />;
  if (existing.error) return <Alert color="red">{normalizationError(existing.error)}</Alert>;
  return <Form key={questionId ?? 'new'} initial={existing.data} onSaved={onSaved} onCancel={onCancel} />;
}

function Form({ initial, onSaved, onCancel }: { initial?: NormalizationAuthoring; onSaved: () => void; onCancel: () => void }) {
  const cache = useQueryClient();
  const [id, setId] = useState(initial?.id);
  const [input, setInput] = useState<NormalizationQuestionInput>(() => initial ? {
    version: initial.version, title: initial.title, difficulty: initial.difficulty, scenario: initial.scenario,
    relation_name: initial.relation_name, attributes: initial.attributes, statements: initial.statements,
    sample_rows: initial.sample_rows, target_normal_form: initial.target_normal_form, approved_fds: initial.approved_fds,
    semantic_judge_enabled: initial.semantic_judge_enabled, hide_correctness: initial.hide_correctness,
  } : structuredClone(blank));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [preview, setPreview] = useState(false);
  const capabilities = useQuery({ queryKey: ['normalization', 'capabilities'], queryFn: normalizationService.capabilities });
  const field = <K extends keyof NormalizationQuestionInput>(key: K, value: NormalizationQuestionInput[K]) => setInput(old => ({ ...old, [key]: value }));
  async function save(showPreview: boolean) {
    setSaving(true); setError('');
    try {
      const saved = await normalizationService.save(input, id);
      setId(saved.id); field('version', saved.version);
      await cache.invalidateQueries({ queryKey: ['normalization'] });
      await cache.invalidateQueries({ queryKey: ['assessmentAnalyticsSummary'] });
      if (showPreview) setPreview(true); else onSaved();
    } catch (e) { setError(normalizationError(e)); } finally { setSaving(false); }
  }
  return <div className={styles.authoringLayout}><Stack gap="lg" className={styles.formMain}>
    {error && <Alert color="red" role="alert">{error}</Alert>}
    <FormSection id="question-details" number="01" title="Question details" description="Set the learning context and the relation students will normalize.">
    <TextInput label="Title" required maxLength={255} value={input.title} onChange={e => field('title', e.currentTarget.value)} />
    <Group grow><Select label="Difficulty" value={input.difficulty} data={['easy', 'medium', 'hard']} onChange={v => v && field('difficulty', v as NormalizationQuestionInput['difficulty'])} />
      <Select label="Assigned target" value={input.target_normal_form} data={['3NF', 'BCNF']} onChange={v => v && field('target_normal_form', v as '3NF' | 'BCNF')} /></Group>
    <MarkdownDescriptionField id="normalization-scenario" label="Scenario" required value={input.scenario} onChange={v => field('scenario', v)} />
    <TextInput label="Original relation name" required value={input.relation_name} onChange={e => field('relation_name', e.currentTarget.value)} />
    <TagsInput label="Attributes" description="Enter each name and press Enter. Up to eight attributes." value={input.attributes} maxTags={8} onChange={attributes => {
      setInput(old => ({ ...old, attributes, sample_rows: old.sample_rows.map(row => Object.fromEntries(attributes.map(a => [a, row[a] ?? '']))),
        approved_fds: old.approved_fds.map(fd => ({ lhs: fd.lhs.filter(a => attributes.includes(a)), rhs: fd.rhs.filter(a => attributes.includes(a)) })) }));
    }} />
    </FormSection>
    <FormSection id="rules-reference" number="02" title="Rules & approved answer" description="Write the business rules, then define the private reference FD set.">
    <Text fw={700} size="sm">Business rules</Text>
    {input.statements.map((statement, i) => <div key={i} className={styles.ruleRow}>
      <TextInput label="Rule ID" w={90} value={statement.id} onChange={e => { const value = e.currentTarget.value; field('statements', input.statements.map((s, j) => i === j ? { ...s, id: value } : s)); }} />
      <Textarea label="Rule" autosize minRows={2} maxRows={6} value={statement.text} onChange={e => { const value = e.currentTarget.value; field('statements', input.statements.map((s, j) => i === j ? { ...s, text: value } : s)); }} />
      <Button variant="subtle" aria-label={`Remove rule ${i + 1}`} onClick={() => field('statements', input.statements.filter((_, j) => i !== j))}>Remove</Button>
    </div>)}
    <Button variant="default" disabled={input.statements.length >= 100} onClick={() => field('statements', [...input.statements, { id: `S${input.statements.length + 1}`, text: '' }])}>Add rule</Button>
    <div className={styles.privateHeading}><Text fw={700} size="sm">Private approved functional dependencies</Text><span>Staff only</span></div>
    <Text size="sm" c="dimmed">The system accepts logically equivalent sets. Sample rows must not contradict any approved FD. No model decomposition is required.</Text>
    {input.approved_fds.map((fd, i) => <div key={i} className={styles.approvedFd}>
      <MultiSelect label={`Approved FD ${i + 1} determinant`} data={input.attributes} value={fd.lhs} onChange={lhs => field('approved_fds', input.approved_fds.map((f, j) => i === j ? { ...f, lhs } : f))} />
      <span aria-hidden="true">→</span>
      <MultiSelect label={`Approved FD ${i + 1} dependent`} data={input.attributes} value={fd.rhs} onChange={rhs => field('approved_fds', input.approved_fds.map((f, j) => i === j ? { ...f, rhs } : f))} />
      <Button variant="subtle" onClick={() => field('approved_fds', input.approved_fds.filter((_, j) => i !== j))}>Remove FD</Button>
    </div>)}
    <Button variant="default" disabled={input.approved_fds.length >= 64} onClick={() => field('approved_fds', [...input.approved_fds, { lhs: [], rhs: [] }])}>Add approved FD</Button>
    </FormSection>
    <FormSection id="sample-data" number="03" title="Sample data" description="Provide examples that are consistent with every approved dependency.">
    {!input.attributes.length && <Text size="sm" c="dimmed">Add attributes in Question details to start building sample rows.</Text>}
    {!!input.attributes.length && <Table.ScrollContainer minWidth={Math.max(550, input.attributes.length * 150 + 110)}><Table className={styles.sampleTable}><Table.Thead><Table.Tr>{input.attributes.map(a => <Table.Th key={a}>{a}</Table.Th>)}<Table.Th /></Table.Tr></Table.Thead>
      <Table.Tbody>{input.sample_rows.map((row, i) => <Table.Tr key={i}>{input.attributes.map(a => <Table.Td key={a}>
        <TextInput aria-label={`Sample row ${i + 1} ${a}`} value={row[a] ?? ''} onChange={e => { const value = e.currentTarget.value; field('sample_rows', input.sample_rows.map((r, j) => i === j ? { ...r, [a]: value } : r)); }} />
      </Table.Td>)}<Table.Td><Button variant="subtle" onClick={() => field('sample_rows', input.sample_rows.filter((_, j) => i !== j))}>Remove row</Button></Table.Td></Table.Tr>)}</Table.Tbody>
    </Table></Table.ScrollContainer>}
    {!input.sample_rows.length && !!input.attributes.length && <Text size="sm" c="dimmed">No sample rows yet. Add a row to illustrate the relation.</Text>}
    <Button variant="default" disabled={!input.attributes.length || input.sample_rows.length >= 100} onClick={() => field('sample_rows', [...input.sample_rows, Object.fromEntries(input.attributes.map(a => [a, '']))])}>Add sample row</Button>
    </FormSection>
    <FormSection id="feedback-settings" number="04" title="Feedback & evaluation" description="Choose how students receive feedback for this question.">
    <Switch label="Enable AI semantic interpretation for this question" checked={!!input.semantic_judge_enabled}
      disabled={!capabilities.data?.semantic_judge_configured && !input.semantic_judge_enabled} onChange={e => field('semantic_judge_enabled', e.currentTarget.checked)} />
    {!capabilities.data?.semantic_judge_configured && <Text size="sm" c="dimmed">Semantic AI requires server configuration. Deterministic equivalence and formal grading always run.</Text>}
    <Switch label="Hide correctness feedback in practice" checked={!!input.hide_correctness} onChange={e => field('hide_correctness', e.currentTarget.checked)} />
    <Text size="sm" c="dimmed">Saving validates the approved FDs against the sample rows. Publication approves this version. Published assessments keep their frozen copy.</Text>
    </FormSection>
    <Group justify="flex-end" className={styles.formActions}><Button variant="subtle" disabled={saving} onClick={onCancel}>Cancel</Button><Button variant="default" loading={saving} onClick={() => save(true)}>Save & preview</Button><Button loading={saving} onClick={() => save(false)}>Save question</Button></Group>
    <Modal opened={preview} onClose={() => setPreview(false)} title="Student workspace preview" closeButtonProps={{ 'aria-label': 'Close workspace preview' }} fullScreen>{id && <NormalizationWorkspace key={`${id}:${input.version}`} questionId={id} preview />}</Modal>
  </Stack><aside className={styles.authoringSidebar}>
    <nav className={styles.sectionNav} aria-label="Question sections"><Text fw={700} size="sm" mb="md">In this question</Text>
      <a href="#question-details"><span>01</span>Question details</a><a href="#rules-reference"><span>02</span>Rules & approved answer</a><a href="#sample-data"><span>03</span>Sample data</a><a href="#feedback-settings"><span>04</span>Feedback & evaluation</a>
    </nav>
    <div className={styles.questionSummary}><Text fw={700} size="sm">At a glance</Text><dl><div><dt>Target</dt><dd>{input.target_normal_form}</dd></div><div><dt>Attributes</dt><dd>{input.attributes.length} / 8</dd></div><div><dt>Business rules</dt><dd>{input.statements.length}</dd></div><div><dt>Approved FDs</dt><dd>{input.approved_fds.length}</dd></div><div><dt>Sample rows</dt><dd>{input.sample_rows.length}</dd></div></dl>
      <Text size="xs" c="dimmed">Use Save & preview to try the student workspace. Save first, then publish from Problems when the question is ready.</Text>
    </div>
  </aside></div>;
}
