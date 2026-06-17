'use client';

import { useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Box, Group, Loader, Text } from '@mantine/core';
import { unifiedLabService } from '@/services/unifiedLab.service';
import { erDiagramService } from '@/services/er-diagram.service';
import { LabItem, LabProgress, LabSessionResponse, UnifiedLabDetail } from '@/types/unified-lab.types';
import { ERDiagramWorkspace, ERDiagramWorkspaceQuestion } from '@/components/ERDiagramWorkspace';
import { ERDiagramQuestion } from '@/types/er-diagram.types';
import { LabItemSidebar } from './LabItemSidebar';
import { LabSqlItemPanel } from './LabSqlItemPanel';
import { LabSectionPanel } from './LabSectionPanel';

function mapErQuestion(q: ERDiagramQuestion): ERDiagramWorkspaceQuestion {
  return {
    id: q.id,
    title: q.title,
    description: q.problem_statement,
    difficulty: q.difficulty_label,
    rubric_md: q.rubric_md ?? '',
    rubric_json: q.rubric_json ?? null,
    show_rubric_on_attempt: q.show_rubric_on_attempt,
  };
}

export function UnifiedLabWorkspace({ labId }: { labId: number }) {
  const router = useRouter();
  const [lab, setLab] = useState<UnifiedLabDetail | null>(null);
  const [progress, setProgress] = useState<LabProgress | null>(null);
  const [activeId, setActiveId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [sessionId, setSessionId] = useState<number | null>(null);
  const [erQuestion, setErQuestion] = useState<ERDiagramWorkspaceQuestion | null>(null);

  const reloadProgress = useCallback(async () => {
    try { setProgress(await unifiedLabService.progress(labId)); } catch { /* ignore */ }
  }, [labId]);

  useEffect(() => {
    (async () => {
      try {
        const session: LabSessionResponse = await unifiedLabService.startSession(labId);
        setSessionId(session.id);
        const detail = await unifiedLabService.get(labId);
        setLab(detail);
        setActiveId(detail.items[0]?.id ?? null);
        await reloadProgress();
      } catch {
        router.replace(`/labs/${labId}/join`);
      } finally {
        setLoading(false);
      }
    })();
  }, [labId, reloadProgress, router]);

  // Load ER question when the active item is of kind 'erd'
  useEffect(() => {
    if (!lab) return;
    const active = lab.items.find((i) => i.id === activeId);
    if (active?.kind === 'erd' && active.ref_id != null) {
      erDiagramService.getQuestionById(active.ref_id)
        .then((q) => setErQuestion(mapErQuestion(q)))
        .catch(() => setErQuestion(null));
    } else {
      setErQuestion(null);
    }
  }, [activeId, lab]);

  if (loading) return <Group justify="center" py="xl"><Loader /></Group>;
  if (!lab) return null;
  const active: LabItem | undefined = lab.items.find((i) => i.id === activeId);

  const renderSolver = () => {
    if (!active) return <Text c="dimmed">This lab has no items.</Text>;

    if (active.kind === 'sql') {
      return <LabSqlItemPanel labId={labId} item={active} onGraded={reloadProgress} />;
    }

    if (active.kind === 'erd') {
      if (!erQuestion) return <Group justify="center" py="xl"><Loader size="sm" /></Group>;
      return (
        <ERDiagramWorkspace
          question={erQuestion}
          unifiedLabContext={{ lab_id: labId, lab_item_id: active.id }}
        />
      );
    }

    if (active.kind === 'sqllab') {
      if (sessionId == null) return <Group justify="center" py="xl"><Loader size="sm" /></Group>;
      return (
        <LabSectionPanel
          labId={labId}
          itemId={active.id}
          sessionId={sessionId}
          onGraded={reloadProgress}
        />
      );
    }

    return <Text c="dimmed">[{active.kind}] solver — unknown kind</Text>;
  };

  return (
    <Box style={{ display: 'flex', minHeight: 'calc(100vh - 60px)' }}>
      <LabItemSidebar items={lab.items} progress={progress} activeId={activeId} onSelect={setActiveId} />
      <Box style={{ flex: 1, padding: 24 }}>
        {renderSolver()}
      </Box>
    </Box>
  );
}
