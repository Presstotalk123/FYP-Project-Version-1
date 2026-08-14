'use client';

import { useState } from 'react';
import { AssessmentAnalyticsList } from './AssessmentAnalyticsList';
import { AssessmentAnalyticsDetail } from './AssessmentAnalyticsDetail';

export function AssessmentAnalyticsTab() {
  // List ⇄ detail. Component state only: refreshing returns to the list, which is accepted
  // (deep-linking is out of scope for this feature).
  const [selectedId, setSelectedId] = useState<number | null>(null);

  if (selectedId !== null) {
    return (
      <AssessmentAnalyticsDetail
        assessmentId={selectedId}
        onBack={() => setSelectedId(null)}
      />
    );
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h2>Assessment analytics</h2>
          <p>Per-question averages and how many registered students attempted each one.</p>
        </div>
      </div>
      <AssessmentAnalyticsList onSelect={setSelectedId} />
    </>
  );
}
