'use client';

import { useParams } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import { useAuth } from '@/contexts/AuthContext';
import { competitionService } from '@/services/competition.service';
import { queryKeys } from '@/services/query-keys';
import { CompetitionShell, ErrorNotice } from '@/components/competition/CompetitionUI';
import { CompetitionWorkspace } from '@/components/competition/CompetitionWorkspace';
import { getApiErrorMessage } from '@/utils/api-error';

export default function IncidentPage() {
  const params = useParams<{ id: string; itemKey: string }>();
  const id = Number(params.id);
  const itemKey = decodeURIComponent(params.itemKey);
  const { user } = useAuth();
  const competition = useQuery({ queryKey: queryKeys.competition(id, user?.id ?? 0), queryFn: () => competitionService.detail(id), enabled: !!user, staleTime: 0, refetchOnMount: true });
  const sessionId = competition.data?.participation?.id;
  const query = useQuery({ queryKey: queryKeys.competitionItem(sessionId ?? 0, itemKey, user?.id ?? 0), queryFn: () => competitionService.incident(sessionId!, itemKey), enabled: !!sessionId, staleTime: 0, refetchOnMount: true });
  const error = query.error || competition.error;
  return <CompetitionShell><ErrorNotice message={error ? getApiErrorMessage(error) : null} />{(query.isLoading || competition.isLoading) && <p role="status">Loading incident…</p>}{competition.data && !sessionId && <p>Join this competition from its overview before opening an incident.</p>}{query.data && sessionId && <CompetitionWorkspace key={`${sessionId}:${itemKey}`} competitionId={id} sessionId={sessionId} itemKey={itemKey} incident={query.data} />}</CompetitionShell>;
}
