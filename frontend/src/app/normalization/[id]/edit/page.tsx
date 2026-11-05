'use client';

import { useParams } from 'next/navigation';
import { NormalizationQuestionEditor } from '@/components/normalization/NormalizationQuestionEditor';

export default function EditNormalizationQuestionPage() {
  const { id } = useParams<{ id: string }>();
  return <NormalizationQuestionEditor questionId={Number(id)} />;
}
