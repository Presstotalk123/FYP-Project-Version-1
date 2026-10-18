import { useQuery } from '@tanstack/react-query';
import { raQueryKeys, raService } from '@/services/ra.service';

/** Is the RA module switched on? Cached for the session like the rest of the app's reads. */
export function useRaStatus() {
  const query = useQuery({ queryKey: raQueryKeys.status, queryFn: () => raService.getStatus() });
  return { enabled: query.data?.enabled ?? false, status: query.data, loading: query.isLoading };
}
