'use client';

import Link from 'next/link';
import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/contexts/AuthContext';
import { competitionService } from '@/services/competition.service';
import { questionService } from '@/services/question.service';
import { queryKeys } from '@/services/query-keys';
import { getApiErrorMessage } from '@/utils/api-error';
import { CompetitionShell, ErrorNotice } from '@/components/competition/CompetitionUI';
import styles from '@/components/competition/Competition.module.css';

export default function AdminCompetitions() {
  const { isStaff } = useAuth();
  const router = useRouter();
  const queryClient = useQueryClient();
  const [tab, setTab] = useState('competitions');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState('');
  const [origin, setOrigin] = useState<'bank' | 'imported' | 'scratch'>('bank');
  const [questionId, setQuestionId] = useState('');
  const [sourceId, setSourceId] = useState('');
  const [template, setTemplate] = useState('left_to_inner');
  const [complaint, setComplaint] = useState('Application users report that expected records have disappeared from the report.');
  const [rules, setRules] = useState('Describe which records must be retained, how duplicate matches are handled, and what the application should display.');
  const [authorised, setAuthorised] = useState(false);
  const competitions = useQuery({ queryKey: ['adminCompetitions'], queryFn: competitionService.adminList, enabled: isStaff, staleTime: 0, refetchOnMount: true });
  const incidents = useQuery({ queryKey: queryKeys.competitionIncidents, queryFn: competitionService.incidents, enabled: isStaff, staleTime: 0, refetchOnMount: true });
  const sources = useQuery({ queryKey: queryKeys.competitionSources, queryFn: competitionService.sources, enabled: isStaff && tab === 'sources' && origin !== 'scratch', staleTime: 0, refetchOnMount: true });
  const questions = useQuery({ queryKey: ['competitionBankQuestions'], queryFn: () => questionService.getQuestions(), enabled: isStaff && tab === 'sources' && origin === 'bank', staleTime: 0, refetchOnMount: true });

  async function action(kind: 'create' | 'file', file?: File) {
    if (busy) return;
    setBusy(kind); setError(''); setNotice('');
    try {
      if (kind === 'file' && file) {
        if (file.size > 12_000_000) throw new Error('Split source files larger than 12 MB into smaller batches.');
        const entries: unknown = JSON.parse(await file.text());
        if (!Array.isArray(entries) || entries.length > 400 || entries.some(entry => !entry || typeof entry !== 'object' || Array.isArray(entry))) throw new Error('Upload a JSON array of at most 400 source objects.');
        let firstEligible: number | undefined;
        for (let i = 0; i < entries.length; i += 10) {
          const imported = await competitionService.importSources(entries.slice(i, i + 10) as Record<string, unknown>[], false);
          firstEligible ??= imported.find(source => source.eligible)?.id;
        }
        await sources.refetch();
        setOrigin('imported'); setAuthorised(false);
        if (firstEligible !== undefined) setSourceId(String(firstEligible));
        setNotice(`${entries.length} source entries processed. Choose an eligible uploaded source, add a fault and create an incident.`);
        return;
      }
      if (origin === 'scratch') {
        router.push('/admin/competitions/incidents/new');
        return;
      }
      if (!authorised) throw new Error('Confirm permission to use the selected exercise before creating an incident.');
      if (origin === 'bank' && !questionId) throw new Error('Choose a SQL question from the question bank.');
      if (origin === 'imported' && !sourceId) throw new Error('Choose an eligible imported source.');
      const source = origin === 'bank'
        ? await competitionService.importQuestion(Number(questionId))
        : await competitionService.source(Number(sourceId));
      await queryClient.invalidateQueries({ queryKey: queryKeys.competitionSources });
      if (!source.eligible) throw new Error(`This exercise needs review before a fault can be added. ${source.diagnostics.join(' ')}`);
      const savedSource = await competitionService.authorise(source.id);
      queryClient.setQueryData(queryKeys.competitionSource(source.id), savedSource);
      const incident = await competitionService.adapt(source.id, template, complaint, rules);
      await queryClient.invalidateQueries({ queryKey: queryKeys.competitionIncidents });
      router.push(`/admin/competitions/incidents/${incident.id}`);
    } catch (err) { setError(getApiErrorMessage(err)); }
    finally { setBusy(''); }
  }

  const queryError = competitions.error || incidents.error;
  return <CompetitionShell staff>
    <div className={styles.hero}><span className={styles.eyebrow}>Instructor workspace</span><h1>Database Rescue</h1><p>Select SQL exercises, add semantic faults and review the resulting incidents. Approve incident versions before assembling a competition.</p></div>
    <div className={styles.row}>{['competitions', 'incidents', 'sources'].map(value => <button className={`btn ${tab === value ? 'btn-brand' : 'btn-secondary'}`} key={value} onClick={() => { setTab(value); setError(''); setNotice(''); }}>{value === 'sources' ? 'Question sources' : value === 'incidents' ? 'Incident library' : 'Competitions'}</button>)}</div>
    <ErrorNotice message={tab !== 'sources' ? error || (queryError ? getApiErrorMessage(queryError) : '') : ''} />
    {tab !== 'sources' && notice && <div className={styles.success} role="status">{notice}</div>}
    {tab === 'competitions' && <><div className={styles.between} style={{ margin: '22px 0' }}><h2>Competitions</h2><Link className="btn btn-brand" href="/admin/competitions/new">Create competition</Link></div>{competitions.data?.length === 0 && <p>Create incidents and approve their versions, then assemble a competition.</p>}<div className={styles.grid}>{competitions.data?.map(comp => <article className={styles.panel} key={comp.id}><span className={styles.pill}>{comp.published ? 'Published · content frozen' : 'Draft'}</span><h2 style={{ marginTop: 12 }}>{comp.title}</h2><p>{comp.description}</p><Link className="btn btn-secondary" href={`/admin/competitions/${comp.id}`}>Manage competition</Link></article>)}</div></>}
    {tab === 'incidents' && <><h2 style={{ marginTop: 22 }}>Incident library</h2><p className={styles.muted}>View, edit, validate and approve your incidents here. To create an incident from an existing question or from scratch, open Question sources. Approved versions appear in the competition builder.</p><div className={styles.grid}>{incidents.data?.map(incident => <article className={styles.panel} key={incident.id}><div className={styles.row}><span className={styles.pill}>{incident.status}</span><span className={styles.muted}>{incident.topic} · {incident.difficulty}</span></div><h3 style={{ marginTop: 14 }}>{incident.title}</h3><Link className="btn btn-secondary" href={`/admin/competitions/incidents/${incident.id}`}>Review incident</Link></article>)}</div></>}
    {tab === 'sources' && <div className={styles.stack} style={{ marginTop: 22 }}>
      <section className={styles.panel}>
        <h2>Create an incident</h2>
        <p className={styles.muted}>Start from an existing SQL question or write your own incident. Review and approve the resulting draft before adding it to a competition.</p>
        <fieldset disabled={!!busy} style={{ border: 0, padding: 0 }}>
          <legend style={{ fontWeight: 650, marginBottom: 8 }}>How would you like to start?</legend>
          <div className={styles.row}>
            <label className={styles.row}><input type="radio" name="origin" checked={origin === 'bank'} onChange={() => { setOrigin('bank'); setAuthorised(false); setError(''); }} /> Question bank</label>
            <label className={styles.row}><input type="radio" name="origin" checked={origin === 'imported'} onChange={() => { setOrigin('imported'); setAuthorised(false); setError(''); }} /> Uploaded or previously imported sources</label>
            <label className={styles.row}><input type="radio" name="origin" checked={origin === 'scratch'} onChange={() => { setOrigin('scratch'); setAuthorised(false); setError(''); setNotice(''); }} /> Create from scratch</label>
          </div>
        </fieldset>
        {origin === 'scratch' ? <p className={styles.muted}>Open the editor with an editable example, then define your own schema, faulty SQL, reference SQL, datasets and expected outputs.</p> : <>
          <p className={styles.muted}>Choose a question and a fault. The original exercise is copied automatically so your changes do not alter the question bank.</p>
          {origin === 'bank' ? <>
            <label className={styles.field}>SQL question<select disabled={!!busy || questions.isPending || !!questions.error} value={questionId} onChange={e => { setQuestionId(e.target.value); setAuthorised(false); setError(''); }}><option value="">Choose a bank question</option>{questions.data?.map(question => <option key={question.id} value={question.id}>{question.title} · {question.difficulty}</option>)}</select></label>
            {questions.isPending && <p role="status">Loading the question bank…</p>}
            {questions.error && <div className={styles.notice}>The question bank is unavailable from this backend. The lightweight demo supports uploaded sources; the full application backend provides the database question bank. <button className="btn btn-secondary" onClick={() => void questions.refetch()}>Retry loading questions</button></div>}
            {questions.data?.length === 0 && <p className={styles.notice}>The question bank on this backend is empty. You can upload extracted questions below.</p>}
          </> : <>
            <label className={styles.field}>Imported source<select disabled={!!busy || sources.isPending} value={sourceId} onChange={e => { setSourceId(e.target.value); setAuthorised(false); setError(''); }}><option value="">Choose an eligible source</option>{sources.data?.map(source => <option key={source.id} value={source.id} disabled={!source.eligible}>{source.external_id} · {source.title}{source.eligible ? '' : ' (needs review)'}</option>)}</select></label>
            <ErrorNotice message={sources.error ? getApiErrorMessage(sources.error) : ''} />
          </>}
          <label className={styles.field}>Fault to introduce<select disabled={!!busy} value={template} onChange={e => setTemplate(e.target.value)}><option value="left_to_inner">LEFT JOIN → INNER JOIN</option><option value="remove_distinct">Remove required DISTINCT</option><option value="invert_exists">Invert EXISTS / NOT EXISTS</option><option value="count_all">COUNT(nullable column) → COUNT(*)</option></select></label>
          <label className={styles.field}>Application complaint<textarea disabled={!!busy} value={complaint} onChange={e => setComplaint(e.target.value)} /></label>
          <label className={styles.field}>Required application behaviour<textarea disabled={!!busy} value={rules} onChange={e => setRules(e.target.value)} /></label>
          <label className={styles.row}><input type="checkbox" disabled={!!busy} checked={authorised} onChange={e => { setAuthorised(e.target.checked); setError(''); }} /> I confirm permission to use the selected exercise.</label>
        </>}
        <ErrorNotice message={error} />
        {notice && <div className={styles.success} role="status">{notice}</div>}
        <button className="btn btn-brand" disabled={!!busy} onClick={() => void action('create')}>{busy === 'create' ? 'Creating incident…' : 'Create incident draft'}</button>
        {origin !== 'scratch' && <p className={styles.muted}>The selected fault must fit the reference query. Review the resulting draft, author distinct hidden datasets and confirm expected outputs before approval.</p>}
      </section>
      {origin !== 'scratch' && <>
        <details className={styles.panel}><summary style={{ cursor: 'pointer', fontWeight: 650 }}>Upload extracted SQL questions (optional)</summary><p className={styles.muted}>Use this when exercises are in a JSON file instead of the application database. Upload a JSON array of at most 400 question entries.</p><label className={styles.field}>Source JSON file<input type="file" accept="application/json,.json" disabled={!!busy} onChange={e => { const file = e.target.files?.[0]; if (file) void action('file', file); e.target.value = ''; }} /></label>{busy === 'file' && <p role="status">Importing source questions…</p>}</details>
        <details className={styles.panel}><summary style={{ cursor: 'pointer', fontWeight: 650 }}>Source import diagnostics</summary><ErrorNotice message={sources.error ? getApiErrorMessage(sources.error) : ''} />{sources.data?.map(source => <details className={styles.component} key={source.id}><summary>{source.external_id} · {source.title} — {source.eligible ? 'Can be adapted' : 'Needs review'}</summary><p>{source.diagnostics.join('\n')}</p><p className={styles.muted}>{source.authorised ? 'Source permission confirmed' : 'Source permission has not been recorded'}</p></details>)}</details>
      </>}
    </div>}
  </CompetitionShell>;
}
