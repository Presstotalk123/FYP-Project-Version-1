import { StudentAssessmentItemView } from '@/types/assessment.types';

/**
 * Builds the workspace route for an assessment item. weight/resourceId are carried in the
 * URL (display-only) so the workspace can show them without a second fetch.
 */
export function itemWorkspaceUrl(assessmentId: number, item: StudentAssessmentItemView): string {
  const base = `/student/assessments/${assessmentId}/items/${item.id}`;
  const rid = `?resourceId=${item.item_id}&weight=${item.weight}`;
  switch (item.item_type) {
    case 'sql_question': return `${base}/sql-question${rid}`;
    case 'sql_lab':      return `${base}/sql-lab${rid}`;
    case 'graph_lab':    return `${base}/graph-lab${rid}`;
    case 'er_question':  return `${base}/er-question${rid}`;
  }
}
