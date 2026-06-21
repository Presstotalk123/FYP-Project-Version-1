'use client';
import { Badge, Box, Group, Stack, Text } from '@mantine/core';
import { DatabaseState } from '@/types/unified-lab.types';
import { ResultsGrid } from './ResultsGrid';

// DatabaseState.tables is DatabaseTableState[] where:
//   - columns: DatabaseColumn[] (objects with .name and .type, NOT string[])
//   - sample_rows: Array<Record<string, unknown>> (NOT .rows)
//   - row_count: number
export function DbStateView({ db }: { db: DatabaseState | null }) {
  if (!db || !db.tables?.length) return <Text size="sm" c="dimmed">No data yet.</Text>;
  return (
    <Stack gap="md">
      {db.tables.map((t) => (
        <Box key={t.name}>
          <Group gap="xs" mb={4}>
            <Text size="sm" fw={600}>{t.name}</Text>
            <Badge size="xs" variant="light">{t.row_count} rows</Badge>
          </Group>
          <Text size="xs" c="dimmed" mb={4}>
            {t.columns.map((c) => `${c.name} ${c.type}`).join(', ')}
          </Text>
          {t.sample_rows.length > 0 && (
            <ResultsGrid columns={t.columns.map((c) => c.name)} rows={t.sample_rows} />
          )}
        </Box>
      ))}
    </Stack>
  );
}
