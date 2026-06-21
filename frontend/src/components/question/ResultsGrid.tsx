'use client';
import { Table } from '@mantine/core';

export function ResultsGrid({ columns, rows }: { columns: string[]; rows: Array<Record<string, unknown>> }) {
  if (columns.length === 0) return null;
  return (
    <Table withTableBorder striped>
      <Table.Thead><Table.Tr>{columns.map((c) => <Table.Th key={c}>{c}</Table.Th>)}</Table.Tr></Table.Thead>
      <Table.Tbody>{rows.slice(0, 50).map((row, i) => (
        <Table.Tr key={i}>{columns.map((c) => <Table.Td key={c}>{String(row[c] ?? '')}</Table.Td>)}</Table.Tr>
      ))}</Table.Tbody>
    </Table>
  );
}
