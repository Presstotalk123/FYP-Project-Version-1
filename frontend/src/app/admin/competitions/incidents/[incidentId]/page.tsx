'use client';
import { useParams } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import { useAuth } from '@/contexts/AuthContext';
import { competitionService } from '@/services/competition.service';
import { CompetitionShell, ErrorNotice } from '@/components/competition/CompetitionUI';
import { IncidentEditor } from '@/components/competition/IncidentEditor';
import { getApiErrorMessage } from '@/utils/api-error';
export default function EditIncident() {
  const id = Number(useParams<{ incidentId: string }>().incidentId); const { isStaff } = useAuth();
  const query = useQuery({ queryKey: ['adminCompetitionIncident', id], queryFn: () => competitionService.adminIncident(id), enabled: isStaff, staleTime: 0, refetchOnMount: true });
  return <CompetitionShell staff><ErrorNotice message={query.error ? getApiErrorMessage(query.error) : null} />{query.isLoading && <p>Loading incident…</p>}{query.data && <IncidentEditor key={query.data.id} initial={query.data} />}</CompetitionShell>;
}
