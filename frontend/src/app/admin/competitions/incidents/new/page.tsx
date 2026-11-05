'use client';
import { CompetitionShell } from '@/components/competition/CompetitionUI';
import { IncidentEditor } from '@/components/competition/IncidentEditor';
export default function NewIncident() { return <CompetitionShell staff><IncidentEditor /></CompetitionShell>; }
