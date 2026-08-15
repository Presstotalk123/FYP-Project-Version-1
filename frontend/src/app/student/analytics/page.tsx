'use client';

import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { DashboardLayout } from '@/components/common/DashboardLayout';
import { UserRole } from '@/types/user.types';
import { ladService } from '@/services/lad.service';
import { queryKeys } from '@/services/query-keys';
import { ConceptGraph } from '@/components/lad/ConceptGraph';
import { PeerBenchmarkPanel } from '@/components/lad/PeerBenchmarkPanel';

export default function StudentAnalyticsPage() {
  const graphQuery = useQuery({
    queryKey: queryKeys.ladConceptGraph,
    queryFn: () => ladService.getConceptGraph(),
  });
  const benchmarkQuery = useQuery({
    queryKey: queryKeys.ladPeerBenchmark,
    queryFn: () => ladService.getPeerBenchmark(),
  });

  const graph = graphQuery.data;
  const benchmark = benchmarkQuery.data;

  const peerAvgByConcept = useMemo(() => {
    const map: Record<number, number> = {};
    if (benchmark && !benchmark.suppressed) {
      for (const a of benchmark.averages) map[a.concept_id] = a.avg_mastery;
    }
    return map;
  }, [benchmark]);

  const loading = graphQuery.isLoading || benchmarkQuery.isLoading;
  const loadError = graphQuery.error || benchmarkQuery.error;
  const error = loadError
    ? ((loadError as { response?: { data?: { detail?: string } } }).response?.data?.detail ||
        'Failed to load your learning analytics')
    : null;

  return (
    <ProtectedRoute requiredRole={UserRole.STUDENT}>
      <DashboardLayout>
        <div className="page-head">
          <div>
            <h2>My Learning</h2>
            <p>See how well you know each SQL concept and how you compare with your class.</p>
          </div>
        </div>

        {loading && (
          <div className="loading-center">
            <div className="spinner" />
            <span>Loading your analytics…</span>
          </div>
        )}

        {error && (
          <div className="da-alert alert-error" role="alert">
            <strong>Error</strong>
            <span>{error}</span>
          </div>
        )}

        {!loading && !error && graph && (
          <>
            <h3 style={{ margin: '4px 0 12px' }}>Concept map</h3>
            <div className="card" style={{ marginBottom: 26, padding: 16 }}>
              <p style={{ marginTop: 0, fontSize: 13, color: 'var(--text-muted)' }}>
                Each box is a SQL concept, coloured by how well you know it. Arrows point from a
                concept to the ones that build on it.
              </p>
              <ConceptGraph data={graph} peerAvgByConcept={peerAvgByConcept} />
            </div>

            <h3 style={{ margin: '4px 0 12px' }}>You vs your class</h3>
            <div className="card" style={{ padding: 16 }}>
              {benchmark ? (
                <PeerBenchmarkPanel nodes={graph.nodes} benchmark={benchmark} />
              ) : (
                <p style={{ color: 'var(--text-muted)', fontSize: 13 }}>Peer data unavailable.</p>
              )}
            </div>
          </>
        )}
      </DashboardLayout>
    </ProtectedRoute>
  );
}
