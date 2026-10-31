'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useEffect, useRef, useState } from 'react';
import { EditorPanel } from '@/components/workspace/EditorPanel';
import { DescriptionMarkdown } from '@/components/common/DescriptionMarkdown';
import { competitionService } from '@/services/competition.service';
import { getApiErrorMessage } from '@/utils/api-error';
import type { IncidentReport, PublicIncident, QueryOutput, RepairFeedback } from '@/types/competition.types';
import { ErrorNotice, ResultTable } from './CompetitionUI';
import styles from './Competition.module.css';

export function CompetitionWorkspace({ competitionId, sessionId, itemKey, incident }: { competitionId: number; sessionId: number; itemKey: string; incident: PublicIncident }) {
  const router = useRouter();
  const simple = incident.report_style === 'verdict';
  const primary = incident.components[0];
  const initial: IncidentReport = { verdict: '', investigation_sql: simple ? primary.query : '', component_id: simple ? primary.id : '', evidence: '', diagnosis: '', repair_sql: simple ? primary.query : '', explanation: '', run_id: null, ...incident.draft.report };
  const [report, setReport] = useState<IncidentReport>(initial);
  const reportRef = useRef(initial);
  const revision = useRef(incident.draft.revision);
  const saved = useRef(JSON.stringify(initial));
  const queue = useRef<Promise<void>>(Promise.resolve());
  const conflict = useRef(false);
  const requestKey = useRef<string | null>(null);
  const [saveStatus, setSaveStatus] = useState('Saved');
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [output, setOutput] = useState<QueryOutput | null>(null);
  const [outputSQL, setOutputSQL] = useState('');
  const [repairOutput, setRepairOutput] = useState<QueryOutput | null>(null);
  const [previewSQL, setPreviewSQL] = useState('');
  const [feedback, setFeedback] = useState<RepairFeedback | null>(null);
  const [checkedSQL, setCheckedSQL] = useState('');
  const [hints, setHints] = useState(incident.checkpoints);
  const readOnly = incident.read_only;

  function change(patch: Partial<IncidentReport>) {
    if (patch.verdict !== undefined && patch.verdict !== reportRef.current.verdict) {
      setFeedback(null); setCheckedSQL('');
    }
    reportRef.current = { ...reportRef.current, ...patch };
    setReport(reportRef.current); setSaveStatus('Unsaved changes'); requestKey.current = null;
  }

  function save(): Promise<void> {
    const snapshot = { ...reportRef.current };
    const serialized = JSON.stringify(snapshot);
    const next = queue.current.catch(() => {}).then(async () => {
      if (saved.current === serialized || readOnly) return;
      if (conflict.current) throw new Error('Reload to resolve the draft conflict. Copy your unsaved text before reloading.');
      setSaveStatus('Saving…');
      try {
        const result = await competitionService.save(sessionId, itemKey, revision.current, snapshot);
        revision.current = result.revision; saved.current = serialized;
        setSaveStatus(JSON.stringify(reportRef.current) === serialized ? 'Saved' : 'Unsaved changes');
      } catch (err) {
        if ((err as { response?: { status?: number } }).response?.status === 409) conflict.current = true;
        setSaveStatus('Not saved'); setError(getApiErrorMessage(err)); throw err;
      }
    });
    queue.current = next;
    return next;
  }

  useEffect(() => {
    if (readOnly) return;
    const timer = window.setTimeout(() => { void save().catch(() => {}); }, 900);
    return () => window.clearTimeout(timer);
    // save reads the latest report/ref and serialises requests across revisions.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [report, readOnly]);

  useEffect(() => {
    function guard(event: BeforeUnloadEvent) {
      if (JSON.stringify(reportRef.current) !== saved.current) { event.preventDefault(); event.returnValue = ''; }
    }
    window.addEventListener('beforeunload', guard);
    return () => window.removeEventListener('beforeunload', guard);
  }, []);

  async function action(kind: string) {
    if (busy || readOnly) return;
    setBusy(kind); setError(''); setNotice('');
    try {
      if (kind === 'investigate') {
        const sql = reportRef.current.investigation_sql;
        const result = await competitionService.run(sessionId, itemKey, sql);
        setOutput(result); setOutputSQL(sql); change({ run_id: result.run_id });
      } else if (kind === 'preview') {
        if (!reportRef.current.component_id) throw new Error('Choose the query component you want to repair.');
        const sql = simple && reportRef.current.verdict === 'correct' ? primary.query : reportRef.current.repair_sql;
        const result = await competitionService.run(sessionId, itemKey, sql, reportRef.current.component_id);
        setRepairOutput(result); setPreviewSQL(sql);
      } else if (kind === 'check') {
        const { repair_sql, component_id } = reportRef.current;
        if (!component_id) throw new Error('Choose the query component you want to repair.');
        const result = await competitionService.check(sessionId, itemKey, repair_sql, component_id);
        setFeedback(result); setCheckedSQL(`${component_id}:${repair_sql}`);
      } else if (kind === 'help') {
        const result = await competitionService.help(sessionId, itemKey); setHints(result.checkpoints);
      } else if (kind === 'save') {
        await save(); setNotice('Your draft is saved.');
      } else if (kind === 'submit') {
        await save();
        requestKey.current ??= crypto.randomUUID();
        const result = await competitionService.submit(sessionId, itemKey, revision.current, requestKey.current);
        if (result.feedback) { setFeedback(result.feedback); setCheckedSQL(`${reportRef.current.component_id}:${reportRef.current.repair_sql}`); }
        setNotice(result.status === 'judge_error' ? 'Your activity report is submitted and retained for participation. Judging hit a technical problem; submit again to retry the same saved report.' : result.submitted ? 'Answer submitted. Return to the overview to view your progress.' : 'Your report is retained. Retry this submission if judging has not finished.');
      }
    } catch (err) { setError(getApiErrorMessage(err)); }
    finally { setBusy(''); }
  }

  return <>
    <div className={styles.between}><Link href={`/student/competitions/${competitionId}`} onClick={e => { if (busy) { e.preventDefault(); return; } if (JSON.stringify(reportRef.current) !== saved.current) { e.preventDefault(); void save().then(() => router.push(`/student/competitions/${competitionId}`)).catch(() => {}); } }}>← Competition overview</Link><span className={styles.muted} role="status">{saveStatus}</span></div>
    <div className={styles.hero} style={{ marginTop: 18 }}><span className={styles.eyebrow}>Rescue mission · {incident.difficulty} · {incident.points} points</span><h1>{incident.title}</h1><DescriptionMarkdown content={incident.complaint} fontSize={16} /></div>
    {readOnly && <div className={styles.notice}>This report is available for review. The participation window is closed for editing.</div>}
    <ErrorNotice message={error} />
    {notice && <div className={styles.success} role="status">{notice}</div>}
    {incident.runs.length > 0 && <details className={styles.panel} style={{ marginBottom: 18 }}><summary>Saved investigation history ({incident.runs.length} recent runs)</summary>{incident.runs.map(run => <details key={run.id} className={styles.component}><summary>Run #{run.id}</summary><pre className={styles.code}>{run.sql}</pre><ResultTable result={run.result} /><button className="btn btn-secondary" disabled={readOnly || !!busy} onClick={() => change({ run_id: run.id, investigation_sql: run.sql })}>Use this run as evidence</button></details>)}</details>}
    <div className={styles.workspace}>
      <div className={styles.stack}>
        <section className={styles.panel}><h2>Application behaviour</h2><DescriptionMarkdown content={incident.business_rules} /><p className={styles.muted}>These features show the application before your repair.</p>{incident.features.map(feature => <div key={feature.component_id} className={styles.component}><h3>{feature.label}</h3><ResultTable result={feature.output} /></div>)}</section>
        <section className={styles.panel}><h2>Database records</h2>{incident.database.map(table => <details className={styles.component} key={table.name} open={simple || undefined} onToggle={e => { if (e.currentTarget.open) void competitionService.inspect(sessionId, itemKey, 'table', table.name).catch(err => setError(getApiErrorMessage(err))); }}><summary>{table.name}</summary><p className={styles.muted}>{table.columns.map(c => `${c.name}: ${c.type}${c.primary_key ? ' (PK)' : ''}`).join(' · ')}</p><ResultTable result={{ columns: table.columns.map(c => c.name), rows: table.rows }} /></details>)}<details className={styles.component}><summary>Schema SQL</summary><pre className={styles.code}>{incident.schema_sql}</pre></details></section>
        {!simple && <section className={styles.panel}><h2>Query components</h2><p className={styles.muted}>Inspect the components and decide which one causes the complaint.</p>{incident.components.map(c => <details className={styles.component} key={c.id} onToggle={e => { if (e.currentTarget.open) void competitionService.inspect(sessionId, itemKey, 'component', c.id).catch(err => setError(getApiErrorMessage(err))); }}><summary>{c.label}</summary><p>{c.purpose}</p><pre className={styles.code}>{c.query}</pre><button className="btn btn-secondary" disabled={readOnly || !!busy} onClick={() => change({ component_id: c.id, repair_sql: c.query })}>Investigate a repair here</button></details>)}</section>}
        {incident.assistance_allowed && <section className={styles.panel}><h2>Checkpoint assistance</h2><p className={styles.muted}>Available whenever you need it. Usage is recorded and does not reduce participation credit or points.</p>{hints.map((hint, i) => <p key={i}><strong>{i + 1}.</strong> {hint}</p>)}<button className="btn btn-secondary" disabled={readOnly || !!busy || hints.length >= incident.checkpoint_count} onClick={() => void action('help')}>{hints.length >= incident.checkpoint_count ? 'All checkpoints revealed' : 'Reveal next checkpoint'}</button></section>}
      </div>
      <div className={styles.stack}>
        {simple ? <>
          <section className={styles.panel}>
            <h2>SQL to review</h2>
            <p className={styles.muted}>Judge whether the query meets the expected behaviour. If incorrect, edit the SQL to attempt a repair.</p>
            <fieldset disabled={readOnly || !!busy} style={{ border: 0, padding: 0, margin: '16px 0' }}>
              <legend style={{ fontWeight: 650, marginBottom: 8 }}>Your verdict</legend>
              <div className={styles.row}>
                <label className={styles.row}><input type="radio" name="verdict" value="correct" checked={report.verdict === 'correct'} onChange={() => change({ verdict: 'correct' })} /> Correct</label>
                <label className={styles.row}><input type="radio" name="verdict" value="incorrect" checked={report.verdict === 'incorrect'} onChange={() => change({ verdict: 'incorrect' })} /> Incorrect</label>
              </div>
            </fieldset>
            <div className={styles.editor}><EditorPanel query={report.verdict === 'correct' ? primary.query : report.repair_sql} onQueryChange={v => { if (reportRef.current.verdict !== 'correct') change({ repair_sql: v }); }} onExecute={() => void action('preview')} onClear={() => change({ repair_sql: '' })} isExecuting={!!busy} executionTime={repairOutput?.execution_time_ms ?? null} readOnly={readOnly || !!busy || report.verdict === 'correct'} runLabel="Preview query output" /></div>
            {repairOutput && <><p className={styles.muted}>{previewSQL === (report.verdict === 'correct' ? primary.query : report.repair_sql) ? 'Query output on the visible records.' : 'This preview is from an earlier SQL revision. Preview the edited query again.'}</p><ResultTable result={repairOutput} /></>}
            {report.verdict === 'incorrect' && <button className="btn btn-secondary" disabled={readOnly || !!busy || !report.repair_sql} onClick={() => void action('check')}>Check repair across scenarios</button>}
            {feedback && <div className={feedback.restored ? styles.success : styles.notice}>
              {checkedSQL !== `${report.component_id}:${report.repair_sql}` ? 'Earlier result; submit or check the edited SQL again. ' : ''}
              {feedback.restored ? 'The repair passes all required checks. Points are awarded when you submit your answer.' : `${feedback.passed_checks} of ${feedback.total_checks} checks passed. Review the verdict and SQL, or submit your attempted answer.`}
            </div>}
          </section>
          <section className={styles.panel}>
            <h2>Explain and submit</h2>
            <label className={styles.field}>Short explanation<textarea disabled={readOnly || !!busy} value={report.explanation} onChange={e => change({ explanation: e.target.value })} placeholder="Explain why the SQL meets or violates the requirements, using the records and output. If incorrect, explain your repair." maxLength={5000} /></label>
            <p className={styles.muted}>Explain your verdict. If incorrect, correct the SQL above. Additional datasets check the repair. Submitted attempts count toward participation even when incorrect.</p>
            <p className={styles.muted}>Saving a draft does not update a submitted answer. Submit again to include your edits. Points are awarded once per restored incident.</p>
            <div className={styles.row}><button className="btn btn-secondary" disabled={readOnly || !!busy} onClick={() => void action('save')}>Save draft</button><button className="btn btn-brand" disabled={readOnly || !!busy} onClick={() => void action('submit')}>{busy === 'submit' ? 'Submitting…' : 'Submit answer'}</button></div>
          </section>
        </> : <>
        <section className={styles.panel}><h2>1. Investigate</h2><p className={styles.muted}>Run read-only SQLite queries to test your hypothesis. Runs do not submit your report or award points.</p><div className={styles.editor}><EditorPanel query={report.investigation_sql} onQueryChange={v => change({ investigation_sql: v })} onExecute={() => void action('investigate')} onClear={() => change({ investigation_sql: '' })} isExecuting={!!busy} executionTime={output?.execution_time_ms ?? null} readOnly={readOnly || !!busy} runLabel="Run investigation" /></div>{output && <><details><summary className={styles.muted}>SQL used for this result</summary><pre className={styles.code}>{outputSQL}</pre></details><ResultTable result={output} /></>}<label className={styles.field}>Evidence gathered<textarea disabled={readOnly || !!busy} value={report.evidence} onChange={e => change({ evidence: e.target.value })} placeholder="Which records or outputs support your hypothesis? Refer to what you observed." maxLength={5000} /></label></section>
        <section className={styles.panel}><h2>2. Diagnose and repair</h2><label className={styles.field}>Suspected query component<select disabled={readOnly || !!busy} value={report.component_id} onChange={e => change({ component_id: e.target.value })}><option value="">Select a component</option>{incident.components.map(c => <option key={c.id} value={c.id}>{c.label}</option>)}</select></label><label className={styles.field}>Semantic cause<textarea disabled={readOnly || !!busy} value={report.diagnosis} onChange={e => change({ diagnosis: e.target.value })} placeholder="Explain why the query runs successfully but produces the wrong application output." maxLength={5000} /></label><div className={styles.editor}><EditorPanel query={report.repair_sql} onQueryChange={v => change({ repair_sql: v })} onExecute={() => void action('preview')} onClear={() => change({ repair_sql: '' })} isExecuting={!!busy} executionTime={repairOutput?.execution_time_ms ?? null} readOnly={readOnly || !!busy} runLabel="Preview repair output" /></div>{repairOutput && <><p className={styles.muted}>{previewSQL === report.repair_sql ? 'Repair output on visible records.' : 'This preview is from an earlier SQL revision. Run the edited repair again.'}</p><ResultTable result={repairOutput} /></>}{incident.assistance_allowed && <button className="btn btn-secondary" disabled={readOnly || !!busy || !report.repair_sql} onClick={() => void action('check')}>Check repair across scenarios</button>}{feedback && <div className={feedback.restored ? styles.success : styles.notice}>{checkedSQL !== `${report.component_id}:${report.repair_sql}` ? 'Earlier repair result; check the edited SQL again. ' : ''}{feedback.restored ? 'The checked repair restored the application across all scenarios.' : `${feedback.passed_checks} of ${feedback.total_checks} feature checks passed. Keep investigating, or submit your attempted repair.`}</div>}</section>
        <section className={styles.panel}><h2>3. Explain and submit</h2><label className={styles.field}>Effect on application outputs<textarea disabled={readOnly || !!busy} value={report.explanation} onChange={e => change({ explanation: e.target.value })} placeholder="Connect your evidence to the SQL behaviour. What changes for the affected records after your repair? If it is still unresolved, explain your current hypothesis." maxLength={5000} /></label><p className={styles.muted}>Saving a draft does not update a previously submitted report. Submit again to include your edits.</p><p className={styles.muted}>Required: an investigation run, evidence, a suspected component and cause, a repair attempt, and a consequence explanation. Your report counts toward participation even if the repair is incorrect.</p><div className={styles.row}><button className="btn btn-secondary" disabled={readOnly || !!busy} onClick={() => void action('save')}>Save draft</button><button className="btn btn-brand" disabled={readOnly || !!busy} onClick={() => void action('submit')}>{busy === 'submit' ? 'Submitting…' : 'Submit incident report'}</button></div></section>
        </>}
      </div>
    </div>
  </>;
}
