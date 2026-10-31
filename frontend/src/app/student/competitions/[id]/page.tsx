'use client';

import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useAuth } from '@/contexts/AuthContext';
import { competitionService } from '@/services/competition.service';
import { queryKeys } from '@/services/query-keys';
import { getApiErrorMessage } from '@/utils/api-error';
import { CompetitionShell, ErrorNotice } from '@/components/competition/CompetitionUI';
import styles from '@/components/competition/Competition.module.css';
import { OptionalSurvey } from '@/components/competition/OptionalSurvey';

function elapsed(seconds: number | null) {
  if (seconds === null) return '—';
  return `${Math.floor(seconds / 60)}m ${(seconds % 60).toFixed(1)}s`;
}

export default function CompetitionOverview() {
  const id = Number(useParams<{ id: string }>().id);
  const { user } = useAuth();
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const query = useQuery({ queryKey: queryKeys.competition(id, user?.id ?? 0), queryFn: () => competitionService.detail(id), enabled: !!user && Number.isInteger(id), staleTime: 0, refetchOnMount: true, refetchOnWindowFocus: true });
  const comp = query.data;
  const part = comp?.participation;
  async function join() {
    setBusy(true); setError('');
    try { await competitionService.join(id); await query.refetch(); }
    catch (err) { setError(getApiErrorMessage(err)); }
    finally { setBusy(false); }
  }
  return <CompetitionShell>
    <Link href="/student/competitions">← All competitions</Link>
    <ErrorNotice message={error || (query.error ? getApiErrorMessage(query.error) : '')} />
    {query.isLoading && <p role="status">Loading competition…</p>}
    {comp && <>
      <div className={styles.hero} style={{ marginTop: 18 }}><span className={styles.eyebrow}>Database Rescue · {comp.topic}</span><h1>{comp.title}</h1><p>{comp.description}</p><p>Open the incidents in any order. Submit an answer for every required incident to complete participation. Incorrect attempts still count toward attendance.</p><button className="btn btn-secondary" onClick={() => void query.refetch()} disabled={query.isFetching}>Refresh progress</button></div>
      {!comp.open && <div className={styles.notice}>The participation window is closed. Saved work remains available to view.</div>}
      {!part ? <button className="btn btn-brand" disabled={busy || !comp.open} onClick={() => void join()}>Join competition</button> : <>
        <div className={styles.grid}>
          <div className={styles.panel}><span className={styles.muted}>Answer points</span><div className={styles.metric}>{part.points}</div><p className={styles.muted}>Awarded once per restored incident.</p></div>
          <div className={styles.panel}><span className={styles.muted}>Participation</span><h2 style={{ marginTop: 10 }}>{part.participation_complete ? 'Complete' : 'In progress'}</h2><p className={styles.muted}>{part.participation_complete ? 'Every required incident has a submitted answer.' : 'Submit each required answer. Correctness and points do not determine attendance.'}</p></div>
          <div className={styles.panel}><span className={styles.muted}>Skill badges</span><p>{part.badges.length ? part.badges.join(' · ') : 'Restore two missions, including a medium or hard incident, to earn a topic badge.'}</p></div>
        </div>
        <section className={styles.stage}><div className={styles.between}><h2>Rescue missions</h2><span className={styles.muted}>{part.items.filter(i => i.submitted).length} / {part.items.length} answers submitted</span></div>
          <p className={styles.muted}>Every incident is available immediately. Inspect the complaint and records, review the SQL, then explain your answer and attempt a repair.</p>
          <div className={styles.grid}>{part.items.map(i => <article className={styles.panel} key={i.key}><div className={styles.row}><span className={styles.pill}>{i.difficulty}</span><span className={styles.muted}>{i.points} points</span></div><h3 style={{ marginTop: 12 }}>{i.title}</h3><p className={styles.muted}>{i.submitted ? 'Answer submitted' : 'Answer required'}{i.restored ? ' · Feature restored' : ''}</p><Link className="btn btn-secondary" href={`/student/competitions/${id}/incidents/${encodeURIComponent(i.key)}`}>{i.submitted ? 'Review / continue' : 'Open incident'}</Link></article>)}</div>
        </section>
        {part.participation_complete && <OptionalSurvey sessionId={part.id} />}
        {comp.leaderboard.enabled && <section className={styles.panel}><div className={styles.between}><h2>Leaderboard</h2><span className={styles.muted}>Updated {new Date(comp.leaderboard.updated_at).toLocaleTimeString()}</span></div><p className={styles.muted}>Answer points in your class.{comp.time_tiebreak ? ' Equal points are ranked by time from joining to the first successful submission for the most recently restored incident. Judging delays do not add time.' : ' Equal points share a rank.'}</p><div className={styles.tableWrap}><table className={styles.table}><thead><tr><th>Rank</th><th>Engineer</th><th>Points</th>{comp.time_tiebreak && <th>Time</th>}</tr></thead><tbody>{comp.leaderboard.rows.map(r => <tr key={r.alias}><td>{r.rank}</td><td>{r.alias}{r.is_you ? ' (you)' : ''}</td><td>{r.points}</td>{comp.time_tiebreak && <td>{elapsed(r.elapsed_seconds)}</td>}</tr>)}</tbody></table></div></section>}
      </>}
    </>}
  </CompetitionShell>;
}
