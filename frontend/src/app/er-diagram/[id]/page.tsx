import { notFound } from "next/navigation";
import { erQuestions } from "@/data/er-questions";
import { ERDiagramWorkspace } from "@/components/ERDiagramWorkspace";

type PageProps = {
  params: Promise<{ id: string }>;
};

export default async function ERDiagramQuestionPage({ params }: PageProps) {
  const { id } = await params;
  const question = erQuestions.find((item) => String(item.id) === id);

  if (!question) {
    notFound();
  }

  return <ERDiagramWorkspace question={question} />;
}
