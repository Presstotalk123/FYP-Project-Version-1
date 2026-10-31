'use client';

import Link from 'next/link';
import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import { useAuth } from '@/contexts/AuthContext';
import { competitionService } from '@/services/competition.service';
import { queryKeys } from '@/services/query-keys';
import { getApiErrorMessage } from '@/utils/api-error';
import type { AdminCompetition, CompetitionConfig, StaffSubmission } from '@/types/competition.types';
import { ErrorNotice } from './CompetitionUI';
import styles from './Competition.module.css';

function localDate(value: string | null) { if (!value) return ''; const date = new Date(value); return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16); }
const defaultConfig: CompetitionConfig = { missions: [], class_groups: [], leaderboard: true, time_tiebreak: true, points: { easy: 10, medium: 20, hard: 30 } };

function ReviewCard({ submission, onReviewed }: { submission: StaffSubmission; onReviewed: () => void }) {
  const previous = submission.reviews[0];
  const [diagnosis, setDiagnosis] = useState(previous?.diagnosis_score ?? 0);
  const [explanation, setExplanation] = useState(previous?.explanation_score ?? 0);
  const [rationale, setRationale] = useState(previous?.rationale ?? '');
  const [error, setError] = useState(''); const [busy, setBusy] = useState(false);
  async function save() { setBusy(true); setError(''); try { await competitionService.review(submission.id, diagnosis, explanation, rationale); onReviewed(); } catch (err) { setError(getApiErrorMessage(err)); } finally { setBusy(false); } }
  return <details className={styles.panel}><summary style={{ cursor: 'pointer', fontWeight: 650 }}>{submission.name} · {submission.item} · {submission.status}{previous ? ' · Reviewed' : ' · Needs review'}</summary><div className={styles.notice}>Expected cause: {submission.fault_cause}<pre className={styles.code}>{submission.reference_query}</pre></div>{(submission.status === 'pending' || submission.status === 'judge_error') && <button className="btn btn-secondary" disabled={busy} onClick={() => { setBusy(true); void competitionService.retryJudgement(submission.id).then(onReviewed).catch(err => setError(getApiErrorMessage(err))).finally(() => setBusy(false)); }}>Retry retained judgement</button>}<p className={styles.muted}>Assistance level: {submission.help_level} · Objective repair: {submission.result?.restored ? 'Restored' : 'Not restored'}</p><div className={styles.grid}><div><h3>Verdict</h3><p>{submission.payload.verdict || 'Investigation report'}</p><h3>Evidence</h3><p>{submission.payload.evidence}</p><h3>Diagnosis</h3><p>{submission.payload.diagnosis}</p></div><div><h3>Repair</h3><pre className={styles.code}>{submission.payload.repair_sql}</pre><h3>Consequence explanation</h3><p>{submission.payload.explanation}</p></div></div><p className={styles.muted}>Rubric v1: 0 absent/unrelated; 1 symptom only; 2 partly correct cause/consequence; 3 correct cause linked to evidence and before/after output. Mark diagnosis and explanation separately.</p><div className={styles.row}><label className={styles.field}>Diagnosis (0–3)<input type="number" min={0} max={3} value={diagnosis} onChange={e => setDiagnosis(Number(e.target.value))} /></label><label className={styles.field}>Explanation (0–3)<input type="number" min={0} max={3} value={explanation} onChange={e => setExplanation(Number(e.target.value))} /></label></div><label className={styles.field}>Marking rationale<textarea value={rationale} onChange={e => setRationale(e.target.value)} /></label><ErrorNotice message={error} /><button className="btn btn-brand" disabled={busy || rationale.trim().length < 5} onClick={() => void save()}>Record rubric review</button>{submission.reviews.length > 0 && <p className={styles.muted}>{submission.reviews.length} review record(s). Corrections add a new record; earlier marks are preserved.</p>}</details>;
}

export function CompetitionManager({ initial }: { initial?: AdminCompetition }) {
  const router = useRouter(); const { isStaff } = useAuth();
  const [record, setRecord] = useState(initial);
  const [title, setTitle] = useState(initial?.title ?? 'Database Rescue: Joins');
  const [description, setDescription] = useState(initial?.description ?? 'Investigate independent database incidents and restore application features.');
  const [topic, setTopic] = useState(initial?.topic ?? 'joins');
  const [config, setConfig] = useState<CompetitionConfig>(initial?.config ?? defaultConfig);
  const [groups, setGroups] = useState(initial?.config.class_groups.join(', ') ?? '');
  const [opens, setOpens] = useState(localDate(initial?.opens_at ?? null));
  const [closes, setCloses] = useState(localDate(initial?.closes_at ?? null));
  const [busy, setBusy] = useState(''); const [error, setError] = useState(''); const [notice, setNotice] = useState('');
  const versions = useQuery({ queryKey: queryKeys.competitionVersions, queryFn: competitionService.versions, enabled: isStaff, staleTime: 0, refetchOnMount: true, refetchOnWindowFocus: true });
  const participants = useQuery({ queryKey: ['competitionParticipants', record?.id], queryFn: () => competitionService.participants(record!.id), enabled: !!record?.published && isStaff, staleTime: 0, refetchOnMount: true });
  const submissions = useQuery({ queryKey: ['competitionSubmissions', record?.id], queryFn: () => competitionService.submissions(record!.id), enabled: !!record?.published && isStaff, staleTime: 0, refetchOnMount: true });
  async function action(kind: string) {
    setBusy(kind); setError(''); setNotice('');
    try {
      let saved = record;
      if (kind === 'save' || kind === 'publish') {
        const body = { title, description, topic, config: { ...config, class_groups: groups.split(',').map(s => s.trim()).filter(Boolean) }, opens_at: opens ? new Date(opens).toISOString() : null, closes_at: closes ? new Date(closes).toISOString() : null };
        if (!record?.published) saved = await competitionService.saveCompetition(body, record?.id);
        if (kind === 'publish' && saved) saved = await competitionService.publish(saved.id);
        setRecord(saved); setNotice(kind === 'publish' ? 'Competition published with frozen incident versions.' : 'Competition draft saved.');
        if (!record && saved) router.replace(`/admin/competitions/${saved.id}`);
      } else if (kind === 'window' && record) {
        saved = await competitionService.window(record.id, opens ? new Date(opens).toISOString() : null, closes ? new Date(closes).toISOString() : null);
        setRecord(saved); setNotice('Participation window updated.');
      } else if (kind.startsWith('export:') && record) await competitionService.export(record.id, kind.slice(7));
      else if (kind === 'refresh') { await participants.refetch(); await submissions.refetch(); }
    } catch (err) { setError(getApiErrorMessage(err)); }
    finally { setBusy(''); }
  }
  const frozen = !!record?.published;
  const queryError = versions.error || participants.error || submissions.error;
  return <>
    <Link href="/admin/competitions">← Competition management</Link><h1>{frozen ? record.title : 'Build a competition'}</h1>
    <ErrorNotice message={error || (queryError ? getApiErrorMessage(queryError) : '')} />{notice && <div className={styles.success} role="status">{notice}</div>}
    {frozen && <div className={styles.notice}>Published content, incident versions and points are frozen. You can manage the access window below.</div>}
    <section className={styles.panel}><h2>Competition content</h2><label className={styles.field}>Title<input value={title} disabled={frozen || !!busy} onChange={e => setTitle(e.target.value)} /></label><label className={styles.field}>Description<textarea value={description} disabled={frozen || !!busy} onChange={e => setDescription(e.target.value)} /></label><div className={styles.grid}><label className={styles.field}>Topic<input value={topic} disabled={frozen || !!busy} onChange={e => setTopic(e.target.value)} /></label><label className={styles.field}>Class groups (comma-separated; empty means all)<input value={groups} disabled={frozen || !!busy} onChange={e => setGroups(e.target.value)} /></label></div>
      <label className={styles.field}>Required incidents<select multiple size={8} disabled={frozen || !!busy} value={config.missions.map(String)} onChange={e => setConfig({ ...config, missions: Array.from(e.target.selectedOptions).map(o => Number(o.value)) })}>{versions.data?.map(v => <option key={v.id} value={v.id}>v{v.id} · {v.difficulty} · {v.title}</option>)}</select></label>
      {!frozen && <button className="btn btn-secondary" disabled={versions.isFetching} onClick={() => void versions.refetch()}>{versions.isFetching ? 'Refreshing incidents…' : 'Refresh incidents'}</button>}
      <p className={styles.muted}>Choose approved incidents for the topic. Any mix of difficulties is allowed. Each incident identity and schema appears once. Ctrl/Cmd-click to select multiple versions.</p>
      <div className={styles.grid}>{['easy', 'medium', 'hard'].map(d => <label key={d} className={styles.field}>{d} answer points<input type="number" min={0} max={1000} value={config.points[d]} disabled={frozen || !!busy} onChange={e => setConfig({ ...config, points: { ...config.points, [d]: Number(e.target.value) } })} /></label>)}</div>
      <p className={styles.muted}>Award answer points once when all required checks pass. Submitted attempts count toward participation independently of points.</p>
      <label className={styles.row}><input type="checkbox" disabled={frozen || !!busy} checked={config.leaderboard} onChange={e => setConfig({ ...config, leaderboard: e.target.checked })} /> Show cohort leaderboard</label>
      <label className={styles.row}><input type="checkbox" disabled={frozen || !!busy} checked={config.time_tiebreak} onChange={e => setConfig({ ...config, time_tiebreak: e.target.checked })} /> Break equal-point ties by time to the most recently restored incident</label>
      {!frozen && <div className={styles.row} style={{ marginTop: 18 }}><button className="btn btn-secondary" disabled={!!busy} onClick={() => void action('save')}>Save draft</button><button className="btn btn-brand" disabled={!!busy} onClick={() => void action('publish')}>{busy === 'publish' ? 'Publishing…' : 'Publish frozen competition'}</button></div>}
    </section>
    <section className={styles.panel} style={{ marginTop: 20 }}><h2>Participation window</h2><div className={styles.grid}><label className={styles.field}>Opens (your local time)<input type="datetime-local" value={opens} onChange={e => setOpens(e.target.value)} /></label><label className={styles.field}>Closes (your local time)<input type="datetime-local" value={closes} onChange={e => setCloses(e.target.value)} /></label></div><p className={styles.muted}>Empty dates leave the corresponding boundary open. Saved work remains readable after closing.</p>{frozen && <button className="btn btn-secondary" disabled={!!busy} onClick={() => void action('window')}>Update window</button>}</section>
    {frozen && <>
      <section className={styles.panel} style={{ marginTop: 20 }}><div className={styles.between}><h2>Participation roster</h2><button className="btn btn-secondary" disabled={!!busy} onClick={() => void action('refresh')}>Refresh activity</button></div><p className={styles.muted}>Attendance is independent of correctness, points and manual marking.</p><div className={styles.tableWrap}><table className={styles.table}><thead><tr><th>Student</th><th>Class</th><th>Stage</th><th>Attendance</th><th>Missing reports</th><th>Points</th></tr></thead><tbody>{participants.data?.map(p => <tr key={p.id}><td>{p.name || p.email}</td><td>{p.cohort}</td><td>{p.phase}</td><td>{p.participation_complete ? 'Complete' : 'In progress'}</td><td>{p.items.filter(i => !i.submitted).map(i => i.key).join(', ') || 'None'}</td><td>{p.points}</td></tr>)}</tbody></table></div></section>
      <section className={styles.panel} style={{ marginTop: 20 }}><h2>Research and attendance exports</h2><p className={styles.muted}>Exports use the configured research salt and exclude staff/test groups. Raw narratives and SQL are restricted research data and may contain learner-entered identifiers. Outcomes include missing mission reports and separately marked diagnosis/explanation scores.</p><div className={styles.row}>{['participation', 'outcomes', 'submissions', 'events', 'runs', 'survey'].map(mode => <button className="btn btn-secondary" key={mode} disabled={!!busy} onClick={() => void action(`export:${mode}`)}>Export {mode}</button>)}</div></section>
      <section className={styles.stack} style={{ marginTop: 20 }}><h2>Rubric review</h2>{submissions.data?.length === 0 && <p>No reports have been submitted yet.</p>}{submissions.data?.map(s => <ReviewCard key={`${s.id}:${s.reviews.length}`} submission={s} onReviewed={() => { void submissions.refetch(); }} />)}</section>
    </>}
  </>;
}
