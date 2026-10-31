'use client';

import type { ReactNode } from 'react';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { DashboardLayout } from '@/components/common/DashboardLayout';
import { UserRole } from '@/types/user.types';
import type { QueryOutput } from '@/types/competition.types';
import styles from './Competition.module.css';

export function CompetitionShell({ children, staff = false }: { children: ReactNode; staff?: boolean }) {
  return <ProtectedRoute allowedRoles={staff ? [UserRole.STAFF, UserRole.ADMIN] : [UserRole.STUDENT]}><DashboardLayout><div className={styles.page}>{children}</div></DashboardLayout></ProtectedRoute>;
}

export function ResultTable({ result }: { result: QueryOutput }) {
  if (result.success === false) return <p className={styles.error} role="alert">{result.error || 'The query could not be executed.'}</p>;
  return <>
    <div className={styles.tableWrap}><table className={styles.table}>
      <thead><tr>{result.columns.map((column, i) => <th key={i}>{column}</th>)}</tr></thead>
      <tbody>{result.rows.map((row, i) => <tr key={i}>{row.map((value, j) => <td key={j}>{value === null ? <em className={styles.muted}>NULL</em> : String(value)}</td>)}</tr>)}</tbody>
    </table></div>
    {!result.rows.length && <p className={styles.muted}>No rows returned.</p>}
    {result.truncated && <p className={styles.muted}>Preview limited to 200 rows. Judging uses the complete bounded output.</p>}
  </>;
}

export function ErrorNotice({ message }: { message: string | null | undefined }) {
  return message ? <div className={styles.error} role="alert">{message}</div> : null;
}
