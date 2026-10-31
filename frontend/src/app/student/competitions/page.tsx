'use client';

import Link from 'next/link';
import { useQuery } from '@tanstack/react-query';
import { useAuth } from '@/contexts/AuthContext';
import { competitionService } from '@/services/competition.service';
import { queryKeys } from '@/services/query-keys';
import { getApiErrorMessage } from '@/utils/api-error';
import { CompetitionShell, ErrorNotice } from '@/components/competition/CompetitionUI';
import styles from '@/components/competition/Competition.module.css';

export default function CompetitionsPage() {
  const { user } = useAuth();
  const capability = useQuery({ queryKey: queryKeys.competitionCapabilities(user?.id ?? 0), queryFn: competitionService.capabilities, enabled: !!user, staleTime: 0, refetchOnMount: true });
  const query = useQuery({ queryKey: queryKeys.studentCompetitions(user?.id ?? 0), queryFn: competitionService.list, enabled: !!user && !!capability.data?.enabled, staleTime: 0, refetchOnMount: true });
  return <CompetitionShell>
    <div className={styles.hero}><span className={styles.eyebrow}>Database Rescue</span><h1>Find the fault. Restore the feature.</h1><p>Investigate application complaints, gather evidence and repair SQL that runs but returns the wrong results. Earn answer points for restored incidents. Participation comes from submitting the required answers, regardless of correctness or speed.</p></div>
    <div className={styles.between}><h2>Competitions</h2><button className="btn btn-secondary" disabled={query.isFetching} onClick={() => { void capability.refetch(); void query.refetch(); }}>Refresh</button></div>
    <ErrorNotice message={query.error ? getApiErrorMessage(query.error) : capability.error ? getApiErrorMessage(capability.error) : null} />
    {(capability.isLoading || query.isLoading) && <p role="status">Loading competitions…</p>}
    {capability.data && !capability.data.enabled && <div className={styles.notice}>Competition is being prepared. Your instructor will announce when it is available.</div>}
    {query.data?.length === 0 && <div className={styles.notice}>No competitions are assigned to your class yet.</div>}
    <div className={styles.grid}>{query.data?.map(comp => <article className={styles.panel} key={comp.id}><div className={styles.row}><span className={styles.pill}>{comp.topic}</span><span className={styles.muted}>{comp.mission_count} missions</span></div><h2 style={{ marginTop: 14 }}>{comp.title}</h2><p>{comp.description}</p><p className={styles.muted}>{comp.open ? 'Open for participation' : 'Outside the participation window'}{comp.closes_at ? ` · Closes ${new Date(comp.closes_at).toLocaleString()}` : ''}</p><Link className="btn btn-brand" href={`/student/competitions/${comp.id}`}>{comp.participation_id ? 'Resume competition' : 'View competition'}</Link></article>)}</div>
  </CompetitionShell>;
}
