'use client';

import Link from 'next/link';
import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/services/query-keys';
import { useRouter } from 'next/navigation';
import { competitionService } from '@/services/competition.service';
import type { AdminIncident, IncidentDocument, QueryOutput, ValidationReport } from '@/types/competition.types';
import { getApiErrorMessage } from '@/utils/api-error';
import { ErrorNotice, ResultTable } from './CompetitionUI';
import styles from './Competition.module.css';

export const starterIncident: IncidentDocument = {
  title: 'Directory records have disappeared', topic: 'joins', difficulty: 'easy',
  complaint: 'A reader without a saved location no longer appears in the library directory.',
  business_rules: 'The directory must show every reader, including readers with no location. Missing location values should be NULL. The record summary counts every reader.',
  schema_sql: 'CREATE TABLE Readers(id INTEGER, name TEXT); CREATE TABLE Locations(id INTEGER, reader_id INTEGER, city TEXT);',
  components: [
    { id: 'directory', label: 'Reader directory', purpose: 'Displays readers and their saved location.', query: 'SELECT r.name, l.city FROM Readers r INNER JOIN Locations l ON l.reader_id = r.id', reference_query: 'SELECT r.name, l.city FROM Readers r LEFT JOIN Locations l ON l.reader_id = r.id' },
    { id: 'summary', label: 'Reader summary', purpose: 'Counts registered readers.', query: 'SELECT COUNT(*) AS readers FROM Readers', reference_query: 'SELECT COUNT(*) AS readers FROM Readers' },
  ], culprit_component: 'directory', fault_template: 'left_to_inner:v1',
  fault_cause: 'The inner join drops readers without a matching location, while the required directory preserves them.',
  checkpoints: ['Compare the Readers table to the directory output.', 'Which join preserves readers with no location?', 'Inspect the join in the directory component and preserve unmatched readers.'],
  scenarios: [
    { id: 'visible', label: 'Unmatched reader', visible: true, seed_sql: "INSERT INTO Readers VALUES (1, 'Ari'), (2, 'Bo'); INSERT INTO Locations VALUES (10, 2, 'East');", approved_outputs: { directory: { columns: ['name', 'city'], rows: [['Ari', null], ['Bo', 'East']] }, summary: { columns: ['readers'], rows: [[2]] } } },
    { id: 'matched', label: 'Every reader matched', visible: false, seed_sql: "INSERT INTO Readers VALUES (5, 'Cai'); INSERT INTO Locations VALUES (20, 5, 'West');", approved_outputs: { directory: { columns: ['name', 'city'], rows: [['Cai', 'West']] }, summary: { columns: ['readers'], rows: [[1]] } } },
    { id: 'empty', label: 'Empty locations and repeated names', visible: false, seed_sql: "INSERT INTO Readers VALUES (8, 'Dee'), (9, 'Dee');", approved_outputs: { directory: { columns: ['name', 'city'], rows: [['Dee', null], ['Dee', null]] }, summary: { columns: ['readers'], rows: [[2]] } } },
  ], oracle_confirmed: false, alternative_repairs: [],
};

function editableDefinition(document: IncidentDocument) {
  // Review confirmation has its own control; it is never a JSON editing task.
  const definition: Partial<IncidentDocument> = { ...document };
  delete definition.oracle_confirmed;
  return JSON.stringify(definition, null, 2);
}

export function IncidentEditor({ initial }: { initial?: AdminIncident }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [id, setId] = useState(initial?.id);
  const [revision, setRevision] = useState(initial?.revision);
  const [text, setText] = useState(editableDefinition(initial?.document ?? starterIncident));
  const [reviewed, setReviewed] = useState(initial?.document.oracle_confirmed ?? false);
  const [lastSaved, setLastSaved] = useState(initial ? JSON.stringify({ text: editableDefinition(initial.document), reviewed: initial.document.oracle_confirmed }) : '');
  const [validation, setValidation] = useState<ValidationReport | null>(initial?.validation ?? null);
  const [preview, setPreview] = useState<{ features: { label: string; faulty: QueryOutput; reference: QueryOutput }[] } | null>(null);
  const [approvedVersion, setApprovedVersion] = useState<number | null>(null);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [feedbackArea, setFeedbackArea] = useState<'source' | 'editor'>('editor');
  const [sourceConfirmed, setSourceConfirmed] = useState(false);
  const sourceId = initial?.source_id ?? null;
  const source = useQuery({ queryKey: queryKeys.competitionSource(sourceId ?? 0), queryFn: () => competitionService.source(sourceId!), enabled: sourceId !== null, staleTime: 0, refetchOnMount: true, refetchOnWindowFocus: true });
  const sourceAuthorised = !!source.data?.authorised;
  const snapshot = JSON.stringify({ text, reviewed });
  const dirty = snapshot !== lastSaved;

  function edit(value: string) {
    setText(value); setReviewed(false); setValidation(null); setApprovedVersion(null);
    setError(''); setNotice('');
  }

  async function saveSourcePermission() {
    if (!sourceId) return;
    if (!sourceConfirmed && !sourceAuthorised) throw new Error('Tick the source permission checkbox before saving permission.');
    await queryClient.cancelQueries({ queryKey: queryKeys.competitionSource(sourceId) });
    const savedSource = await competitionService.authorise(sourceId);
    queryClient.setQueryData(queryKeys.competitionSource(sourceId), savedSource);
    await queryClient.invalidateQueries({ queryKey: queryKeys.competitionSources });
  }

  async function action(kind: 'save' | 'preview' | 'validate' | 'approve' | 'authorise') {
    if (busy) return;
    setBusy(kind); setError(''); setNotice('');
    setFeedbackArea(kind === 'authorise' ? 'source' : 'editor');
    try {
      if (kind === 'authorise') {
        await saveSourcePermission();
        setNotice('Source permission saved. It will remain confirmed when you reopen this incident.');
        return;
      }
      if (kind === 'approve') {
        if (!reviewed) throw new Error('Confirm that you have reviewed the expected outputs and business rules using the review checkbox below.');
        if (sourceId && !sourceAuthorised) {
          if (!sourceConfirmed) throw new Error('Confirm permission to use the source exercise before approving. Tick the source permission checkbox above.');
          await saveSourcePermission();
        }
      }
      const parsed: unknown = JSON.parse(text);
      if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) throw new Error('Enter an incident definition object.');
      const doc = { ...parsed, oracle_confirmed: reviewed } as IncidentDocument;
      let currentId = id;
      if (!currentId || dirty) {
        const row = await competitionService.saveIncident(doc, sourceId, currentId, revision);
        currentId = row.id;
        setId(row.id); setRevision(row.revision); setLastSaved(snapshot); setValidation(null);
        queryClient.setQueryData(queryKeys.competitionIncident(row.id), row);
        await queryClient.invalidateQueries({ queryKey: queryKeys.competitionIncidents });
      }
      if (!currentId) return;
      if (kind === 'validate' || kind === 'approve') {
        const checked = await competitionService.validate(currentId);
        setValidation(checked);
        await queryClient.invalidateQueries({ queryKey: queryKeys.competitionIncidents });
        if (!checked.valid) {
          setError('Validation found issues. Review the messages below, correct the definition and try again.');
          return;
        }
        if (kind === 'approve') {
          const approved = await competitionService.approve(currentId);
          setApprovedVersion(approved.version_id);
          await Promise.all([
            queryClient.invalidateQueries({ queryKey: queryKeys.competitionVersions }),
            queryClient.invalidateQueries({ queryKey: queryKeys.competitionIncidents }),
            queryClient.invalidateQueries({ queryKey: queryKeys.competitionIncident(currentId) }),
          ]);
          setNotice(`Incident approved as version v${approved.version_id}. It is now available under Required incidents when creating a competition.`);
        } else setNotice('All scenarios passed validation. You can now approve this incident.');
      } else if (kind === 'preview') setPreview(await competitionService.preview(currentId));
      else setNotice('Incident draft and review confirmation saved. Published versions remain unchanged.');
      // Keep a new editor mounted while saving/validating; navigating earlier lost
      // its validation result and made approval appear to do nothing.
      if (!initial && kind === 'save') router.replace(`/admin/competitions/incidents/${currentId}`);
    } catch (err) { setError(getApiErrorMessage(err)); }
    finally { setBusy(''); }
  }

  return <>
    <Link href="/admin/competitions">← Competition management</Link>
    <h1>{initial ? `Edit incident: ${initial.title}` : 'New incident'}</h1>
    <p className={styles.notice}>Review the complaint, SQL, records and expected outputs. Confirm your review below, then approve. Approval saves your latest changes and validates every scenario before creating a fixed version.</p>

    {sourceId !== null && <section className={styles.panel} style={{ marginBottom: 18 }} aria-label="Source permission">
      <h2>Source permission</h2>
      {source.isPending ? <p role="status">Checking saved source permission…</p> : sourceAuthorised ? <p className={styles.success} role="status">Source permission is confirmed{source.data?.title ? ` for “${source.data.title}”` : ''}.</p> : <>
        <p className={styles.muted}>{source.data?.title || 'This incident uses an imported SQL exercise.'}</p>
        <label className={styles.row}><input type="checkbox" checked={sourceConfirmed} disabled={!!busy} onChange={e => { setSourceConfirmed(e.target.checked); setError(''); }} /> I confirm permission to use this source exercise.</label>
        <p className={styles.muted}>Save permission now, or leave the checkbox ticked and Approve will save it for you.</p>
        <button className="btn btn-secondary" disabled={!!busy} onClick={() => void action('authorise')}>{busy === 'authorise' ? 'Saving source permission…' : 'Save source permission'}</button>
      </>}
      {source.error && <ErrorNotice message={getApiErrorMessage(source.error)} />}
      {busy === 'authorise' && <p role="status">Saving source permission…</p>}
      {feedbackArea === 'source' && notice && <p className={styles.success} role="status">{notice}</p>}
      {feedbackArea === 'source' && error && <ErrorNotice message={error} />}
    </section>}

    <section className={styles.panel}>
      <h2>Incident definition</h2>
      <p className={styles.muted}>Edit the content and scenarios here. Review confirmation is managed by the checkbox below. Changing this definition clears your review confirmation.</p>
      <label className={styles.field}>Definition JSON<textarea className={styles.json} spellCheck={false} value={text} onChange={e => edit(e.target.value)} disabled={!!busy} /></label>
      <section aria-label="Expected output review">
        <h3>Expected output review</h3>
        <p className={styles.muted}>Check that the expected rows and reference SQL satisfy the business rules for every visible and hidden dataset. Preview application and Validate all scenarios can help you inspect the outputs.</p>
        <label className={styles.row}><input type="checkbox" checked={reviewed} disabled={!!busy} onChange={e => { setReviewed(e.target.checked); setValidation(null); setApprovedVersion(null); setError(''); setNotice(''); }} /> I have reviewed the expected outputs and business rules.</label>
        <p className={styles.muted}>{reviewed ? dirty ? 'Review confirmed; it will be saved with your next action.' : 'Your review confirmation is saved.' : 'Confirm your review before approving this incident.'}</p>
      </section>
      <div className={styles.row}>
        <button className="btn btn-secondary" disabled={!!busy} onClick={() => void action('save')}>{busy === 'save' ? 'Saving…' : 'Save draft'}</button>
        <button className="btn btn-secondary" disabled={!!busy} onClick={() => void action('preview')}>{busy === 'preview' ? 'Preparing preview…' : 'Preview application'}</button>
        <button className="btn btn-secondary" disabled={!!busy} onClick={() => void action('validate')}>{busy === 'validate' ? 'Validating…' : 'Validate all scenarios'}</button>
        <button className="btn btn-brand" disabled={!!busy} onClick={() => void action('approve')}>{busy === 'approve' ? 'Validating and approving…' : 'Approve immutable version'}</button>
      </div>
      {busy && <p role="status">{busy === 'approve' ? 'Saving, validating all scenarios and approving. Please wait…' : 'Working…'}</p>}
      {feedbackArea === 'editor' && <ErrorNotice message={error} />}
      {feedbackArea === 'editor' && notice && <div className={styles.success} role="status">{notice}</div>}
      {approvedVersion !== null && <Link className="btn btn-secondary" href="/admin/competitions/new">Create a competition using approved incidents</Link>}
    </section>
    {validation && <section className={styles.panel} style={{ marginTop: 20 }}><h2>{validation.valid ? 'Validation passed' : 'Review required'}</h2><p className={styles.muted}>{validation.parser_version} · {validation.content_hash}</p>{validation.errors.map((message, i) => <p className={styles.error} key={i}>{message}</p>)}{validation.cases.map(c => <details className={styles.component} key={`${c.scenario}:${c.component}`}><summary>{c.scenario} / {c.component} — reference {c.reference_ok ? 'passes' : 'fails'}, initial SQL {c.fault_executes ? 'executes' : 'fails to execute'}, output {c.matches_approved ? 'matches' : 'differs'}</summary><h3>Initial application output</h3><ResultTable result={c.actual} /><h3 style={{ marginTop: 16 }}>Approved output</h3><ResultTable result={c.approved} /></details>)}</section>}
    {preview && <section className={styles.panel} style={{ marginTop: 20 }}><h2>Application preview</h2>{preview.features.map((f, i) => <div key={i} className={styles.component}><h3>{f.label}</h3><div className={styles.grid}><div>Before repair<ResultTable result={f.faulty} /></div><div>Reference behaviour<ResultTable result={f.reference} /></div></div></div>)}</section>}
  </>;
}
