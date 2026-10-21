'use client';

import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { Stack, Tabs } from '@mantine/core';
import { LabLeaderboard } from './LabLeaderboard';
import { OverallLeaderboard } from './OverallLeaderboard';

const IconRefresh = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/>
    <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
  </svg>
);

/**
 * Leaderboard page body shared by the student and staff routes. The backend masks
 * other students' names for student viewers, so the only role difference here is
 * whether the email column is shown.
 */
export function LeaderboardView({ showEmail }: { showEmail: boolean }) {
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<string | null>('lab');
  const [refreshing, setRefreshing] = useState(false);

  // The app-wide cache never refetches on its own, so this is how a viewer picks
  // up new submissions. Invalidating the prefix refetches whatever is on screen.
  const refresh = async () => {
    setRefreshing(true);
    try {
      await queryClient.invalidateQueries({
        queryKey: tab === 'overall' ? ['overallLeaderboard'] : ['labLeaderboard'],
      });
    } finally {
      setRefreshing(false);
    }
  };

  return (
    <>
      <div className="page-head">
        <div>
          <h2>Leaderboard</h2>
          <p>See how students rank on each lab, or across all practice.</p>
        </div>
        <div className="button-row">
          <button className="btn btn-secondary" onClick={refresh} disabled={refreshing} title="Reload latest data from the server">
            <IconRefresh />
            {refreshing ? 'Refreshing…' : 'Refresh'}
          </button>
        </div>
      </div>

      <Tabs value={tab} onChange={setTab} keepMounted={false}>
        <Tabs.List>
          <Tabs.Tab value="lab">By lab</Tabs.Tab>
          <Tabs.Tab value="overall">Overall</Tabs.Tab>
        </Tabs.List>

        <Tabs.Panel value="lab" pt="md">
          <Stack gap="md"><LabLeaderboard showEmail={showEmail} /></Stack>
        </Tabs.Panel>
        <Tabs.Panel value="overall" pt="md">
          <Stack gap="md"><OverallLeaderboard showEmail={showEmail} /></Stack>
        </Tabs.Panel>
      </Tabs>
    </>
  );
}
