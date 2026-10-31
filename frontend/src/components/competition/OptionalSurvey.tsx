'use client';
import { useState } from 'react';
import { competitionService } from '@/services/competition.service';
import { getApiErrorMessage } from '@/utils/api-error';
import { ErrorNotice } from './CompetitionUI';
import styles from './Competition.module.css';

export function OptionalSurvey({ sessionId }: { sessionId: number }) {
  const [usability, setUsability] = useState(3); const [engagement, setEngagement] = useState(3); const [feedback, setFeedback] = useState('');
  const [busy, setBusy] = useState(false); const [sent, setSent] = useState(false); const [error, setError] = useState('');
  async function submit() { setBusy(true); setError(''); try { await competitionService.survey(sessionId, usability, engagement, feedback); setSent(true); } catch (err) { setError(getApiErrorMessage(err)); } finally { setBusy(false); } }
  return <section className={styles.panel} style={{ margin: '20px 0' }}><h2>Optional feedback</h2><p className={styles.muted}>Participation is already complete. This survey does not affect attendance, points or badges. Responses are available to your instructor for evaluating this activity.</p>{sent ? <p className={styles.success}>Your feedback was submitted.</p> : <><div className={styles.grid}><label className={styles.field}>How easy was the activity to use? (1 difficult – 5 easy)<select value={usability} onChange={e => setUsability(Number(e.target.value))}>{[1, 2, 3, 4, 5].map(n => <option key={n}>{n}</option>)}</select></label><label className={styles.field}>How engaging was the investigation? (1 low – 5 high)<select value={engagement} onChange={e => setEngagement(Number(e.target.value))}>{[1, 2, 3, 4, 5].map(n => <option key={n}>{n}</option>)}</select></label></div><label className={styles.field}>What helped, or what should improve?<textarea value={feedback} maxLength={3000} onChange={e => setFeedback(e.target.value)} /></label><ErrorNotice message={error} /><button className="btn btn-secondary" disabled={busy} onClick={() => void submit()}>Submit optional feedback</button></>}</section>;
}
