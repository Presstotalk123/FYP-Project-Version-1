'use client';

import { useState, type CSSProperties } from 'react';
import { useQuery } from '@tanstack/react-query';
import { IconRefresh } from '@tabler/icons-react';
import { useAuth } from '@/contexts/AuthContext';
import { chatbotManagementService } from '@/services/chatbot-management.service';
import { getApiErrorMessage } from '@/utils/api-error';
import { AkelaButton } from './AkelaButton';
import styles from './ChatbotDashboard.module.css';

const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];

type Point = { label: string; count: number };
const metricLabel: CSSProperties = {
  fontSize: 13, color: 'var(--text-muted)', fontWeight: 700,
  textTransform: 'uppercase', letterSpacing: '0.04em',
};

function BarChart({ data, label }: { data: Point[]; label: string }) {
  const max = Math.max(1, ...data.map((point) => point.count));
  return <div className={styles.bars} role="img" aria-label={label}>
    {data.map((point, i) => <div key={`${point.label}-${i}`} className={styles.barRow} title={`${point.label}: ${point.count} queries`}>
      <span className={styles.courseLabel}>{point.label}</span>
      <div className={styles.track}><div className={styles.bar} style={{ width: `${point.count / max * 100}%` }} /></div>
      <strong>{point.count.toLocaleString()}</strong>
    </div>)}
  </div>;
}

function DataTable({ data, label }: { data: Point[]; label: string }) {
  return <details className={styles.details}><summary>View data</summary><table>
    <thead><tr><th>{label}</th><th>Queries</th></tr></thead>
    <tbody>{data.map((point, i) => <tr key={`${point.label}-${i}`}><td>{point.label}</td><td>{point.count.toLocaleString()}</td></tr>)}</tbody>
  </table></details>;
}

export function ChatbotDashboard() {
  const { user } = useAuth();
  const query = useQuery({ queryKey: ['chatbot-management', user?.id, 'dashboard'], queryFn: chatbotManagementService.dashboard });
  const data = query.data;
  const currentYear = Number(new Intl.DateTimeFormat('en', { year: 'numeric', timeZone: 'Asia/Singapore' }).format(new Date()));
  const [selectedYear, setSelectedYear] = useState(currentYear);
  const years = [...new Set([currentYear, selectedYear, ...(data?.usage ?? []).map((point) => Number(point.label.split(' ').at(-1))).filter(Number.isFinite)])].sort((a, b) => b - a);
  const monthlyUsage = MONTHS.map((month) => ({
    label: month.slice(0, 3),
    count: (data?.usage ?? []).filter((point) => point.label === `${month} ${selectedYear}`).reduce((sum, point) => sum + point.count, 0),
  }));
  const metrics = [
    { label: 'Total Courses', value: data?.courses, color: 'var(--brand-lilac)', description: 'Course knowledge bases' },
    { label: 'Total Users', value: data?.users, color: 'var(--success)', description: 'Users counted per course' },
    { label: 'Total Queries', value: data?.queries, color: 'var(--warning)', description: 'Questions sent to the chatbot' },
  ];
  return <>
    <div className="page-head"><div><h2>Chatbot Management</h2><p>An overview of your course chatbots and knowledge bases.</p></div>
      <div className="button-row"><AkelaButton variant="default" leftSection={<IconRefresh size={15} />} loading={query.isFetching} onClick={() => query.refetch()}>{query.isFetching ? 'Refreshing…' : 'Refresh'}</AkelaButton></div>
    </div>
    {query.error && <div role="alert" className="da-alert alert-error" style={{ marginBottom: 18 }}><strong>Unable to load dashboard</strong><span>{getApiErrorMessage(query.error)}</span></div>}
    <div className="grid-3" style={{ marginBottom: 18 }}>
      {metrics.map((metric) => <article className="card metric" key={metric.label} style={{ borderLeft: `3px solid ${metric.color}` }}>
        <div><span style={metricLabel}>{metric.label}</span><strong>{metric.value?.toLocaleString() ?? '—'}</strong><span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{query.isPending ? 'Loading…' : metric.description}</span></div>
      </article>)}
    </div>
    <div className={styles.graphs}>
      <article className="card">
        <div className={styles.cardHeader}>
          <div><h3>Usage Over Time</h3><p className={styles.subtitle}>Monthly queries across your courses · {selectedYear}</p></div>
          <label className={styles.yearSelector}>Year
          <select className="da-select" style={{ width: 'auto' }} value={selectedYear} onChange={(event) => setSelectedYear(Number(event.target.value))}>
            {years.map((year) => <option key={year} value={year}>{year}</option>)}
          </select>
          </label>
        </div>
        {query.isPending ? <p role="status">Loading usage…</p> : !data ? <p className={styles.empty}>Usage data unavailable.</p> : <><BarChart data={monthlyUsage} label={`Usage Over Time for ${selectedYear}`} /><DataTable data={monthlyUsage} label="Month" /></>}
      </article>
      <article className="card"><h3>Queries by Course</h3><p className={styles.subtitle}>Total queries for each course</p>
        {query.isPending ? <p role="status">Loading courses…</p> : !data ? <p className={styles.empty}>Course usage unavailable.</p> : !data.by_course.length ? <p className={styles.empty}>No courses yet. Add a course in Knowledge Base.</p> : <><BarChart data={data.by_course} label="Queries by Course" /><DataTable data={data.by_course} label="Course" /></>}
      </article>
    </div>
    <p className={styles.note}>A user who uses multiple courses is counted once in each course. Queries count individual user messages across all available history.</p>
  </>;
}
