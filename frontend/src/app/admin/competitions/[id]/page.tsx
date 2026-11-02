'use client';
import { useParams } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import { useAuth } from '@/contexts/AuthContext';
import { competitionService } from '@/services/competition.service';
import { CompetitionShell, ErrorNotice } from '@/components/competition/CompetitionUI';
import { CompetitionManager } from '@/components/competition/CompetitionManager';
import { getApiErrorMessage } from '@/utils/api-error';
export default function ManageCompetition() {
  const id = Number(useParams<{ id: string }>().id); const { isStaff } = useAuth();
  const query = useQuery({ queryKey: ['adminCompetition', id], queryFn: () => competitionService.adminDetail(id), enabled: isStaff, staleTime: 0, refetchOnMount: true });
  return <CompetitionShell staff><ErrorNotice message={query.error ? getApiErrorMessage(query.error) : null} />{query.isLoading && <p>Loading competition…</p>}{query.data && <CompetitionManager key={query.data.id} initial={query.data} />}</CompetitionShell>;
}
