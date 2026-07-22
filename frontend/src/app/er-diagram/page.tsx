"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { notifications } from "@mantine/notifications";
import { QuestionCard, QuestionCardData } from "@/components/QuestionCard";
import { useAuth } from "@/contexts/AuthContext";
import { useERAbility } from "@/hooks/use-er-ability";
import { toERQuestionSubject } from "@/permissions/er-ability";
import { erDiagramService } from "@/services/er-diagram.service";
import { erLabsService } from "@/services/erLabs.service";
import type { ErLabResponse } from "@/types/er-lab.types";

type ERQuestionCardData = QuestionCardData & {
  created_by: number;
  created_by_role: "student" | "staff" | "admin";
};

const IconPlus = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
  </svg>
);

export default function ERDiagramPage() {
  const router = useRouter();
  const ability = useERAbility();
  const { isStaff } = useAuth();
  const [questions, setQuestions] = useState<ERQuestionCardData[]>([]);
  const [labs, setLabs] = useState<ErLabResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [deletingQuestionId, setDeletingQuestionId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<string>("student-created");

  const studentCreatedQuestions = useMemo(
    () => questions.filter((q) => q.created_by_role === "student"),
    [questions]
  );
  const staffCreatedQuestions = useMemo(
    () => questions.filter((q) => q.created_by_role === "staff" || q.created_by_role === "admin"),
    [questions]
  );

  const refreshLabs = async () => {
    try {
      const ls = await erLabsService.list();
      setLabs(ls);
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } }; message?: string };
      notifications.show({ color: "red", message: e.response?.data?.detail || e.message || "Failed to load ER labs" });
    }
  };

  useEffect(() => {
    const fetchAll = async () => {
      try {
        setLoading(true);
        setError(null);
        const data = await erDiagramService.getQuestions();
        setQuestions(
          data.map((item) => ({
            id: item.id,
            title: item.title,
            summary: item.problem_statement,
            description: item.problem_statement,
            difficulty: item.difficulty_label,
            created_by: item.created_by,
            created_by_role: item.created_by_role,
          }))
        );
      } catch (err) {
        const e = err as { response?: { data?: { detail?: string } }; message?: string };
        setError(e.response?.data?.detail || e.message || "Failed to load ER questions");
      } finally {
        setLoading(false);
      }
      refreshLabs();
    };
    fetchAll();
  }, []);

  const handleDeleteQuestion = async (questionId: number) => {
    const shouldDelete = window.confirm(`Delete ER question #${questionId}?`);
    if (!shouldDelete) return;
    try {
      setDeletingQuestionId(questionId);
      setError(null);
      await erDiagramService.deleteQuestion(questionId);
      setQuestions((prev) => prev.filter((item) => item.id !== questionId));
    } catch (err) {
      const e = err as { response?: { status?: number; data?: { detail?: string } }; message?: string };
      if (e.response?.status === 403) {
        setError(e.response?.data?.detail || "Only the question owner or staff can delete this question");
      } else {
        setError(e.response?.data?.detail || e.message || "Failed to delete ER question");
      }
    } finally {
      setDeletingQuestionId(null);
    }
  };

  const renderQuestions = (questionList: ERQuestionCardData[], emptyMessage: string) => {
    if (questionList.length === 0) {
      return <p style={{ color: "var(--text-muted)" }}>{emptyMessage}</p>;
    }
    return (
      <div className="grid-3">
        {questionList.map((question) => (
          <QuestionCard
            key={question.id}
            data={question}
            showDeleteButton={ability.can("delete", toERQuestionSubject(question))}
            deleteLoading={deletingQuestionId === question.id}
            onDelete={handleDeleteQuestion}
          />
        ))}
      </div>
    );
  };

  const onLabPublishToggle = async (lab: ErLabResponse) => {
    try {
      if (lab.is_published) await erLabsService.unpublish(lab.id);
      else await erLabsService.publish(lab.id);
      refreshLabs();
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } }; message?: string };
      notifications.show({ color: "red", message: e.response?.data?.detail || e.message || "Failed" });
    }
  };

  const onLabRunToggle = async (lab: ErLabResponse) => {
    try {
      if (lab.is_running) await erLabsService.stop(lab.id);
      else await erLabsService.start(lab.id);
      refreshLabs();
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } }; message?: string };
      notifications.show({ color: "red", message: e.response?.data?.detail || e.message || "Failed" });
    }
  };

  const onLabDelete = async (lab: ErLabResponse) => {
    if (!window.confirm(`Delete "${lab.title}"?`)) return;
    try {
      await erLabsService.remove(lab.id);
      refreshLabs();
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } }; message?: string };
      notifications.show({ color: "red", message: e.response?.data?.detail || e.message || "Failed" });
    }
  };

  const renderStaffLabTable = () => {
    if (labs.length === 0)
      return <p style={{ color: "var(--text-muted)" }}>No labs yet. Click &quot;New ER Lab&quot; to create one.</p>;
    return (
      <div className="table-wrap">
        <table className="da-table">
          <thead>
            <tr>
              <th>Title</th>
              <th>Status</th>
              <th>Updated</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {labs.map((lab) => (
              <tr key={lab.id}>
                <td>
                  <a
                    onClick={() => router.push(`/er-diagram/lab/${lab.id}`)}
                    style={{ cursor: "pointer", color: "var(--brand-lilac)", fontWeight: 600 }}
                  >
                    {lab.title}
                  </a>
                </td>
                <td>
                  <div style={{ display: "flex", gap: 6 }}>
                    <span className={`badge ${lab.is_published ? "badge-success" : "neutral"}`}>
                      {lab.is_published ? "Published" : "Unpublished"}
                    </span>
                    <span className={`badge ${lab.is_running ? "badge-info" : "neutral"}`}>
                      {lab.is_running ? "Running" : "Stopped"}
                    </span>
                  </div>
                </td>
                <td style={{ color: "var(--text-muted)", fontSize: 13 }}>
                  {new Date(lab.updated_at).toLocaleString()}
                </td>
                <td>
                  <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                    <button className="btn btn-secondary" style={{ minHeight: 32, padding: "0 10px", fontSize: 12 }}
                      onClick={() => router.push(`/er-diagram/lab/${lab.id}`)}>
                      Manage
                    </button>
                    <button className="btn btn-secondary" style={{ minHeight: 32, padding: "0 10px", fontSize: 12 }}
                      onClick={() => router.push(`/er-diagram/lab/${lab.id}/students`)}>
                      Students
                    </button>
                    <button className="btn btn-secondary" style={{ minHeight: 32, padding: "0 10px", fontSize: 12 }}
                      onClick={() => onLabPublishToggle(lab)}>
                      {lab.is_published ? "Unpublish" : "Publish"}
                    </button>
                    <button className="btn btn-secondary" style={{ minHeight: 32, padding: "0 10px", fontSize: 12 }}
                      disabled={!lab.is_published}
                      onClick={() => onLabRunToggle(lab)}>
                      {lab.is_running ? "Stop" : "Start"}
                    </button>
                    <button className="btn btn-danger" style={{ minHeight: 32, padding: "0 10px", fontSize: 12 }}
                      onClick={() => onLabDelete(lab)}>
                      Delete
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  };

  const renderStudentLabTable = () => {
    if (labs.length === 0)
      return <p style={{ color: "var(--text-muted)" }}>No labs available right now.</p>;
    return (
      <div className="table-wrap">
        <table className="da-table">
          <thead>
            <tr>
              <th>Title</th>
              <th>Status</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {labs.map((lab) => (
              <tr key={lab.id}>
                <td style={{ fontWeight: 600 }}>{lab.title}</td>
                <td>
                  <span className={`badge ${lab.is_running ? "badge-info" : "neutral"}`}>
                    {lab.is_running ? "Running" : "Closed"}
                  </span>
                </td>
                <td>
                  {lab.is_running ? (
                    <button className="btn btn-brand" style={{ minHeight: 32, padding: "0 12px", fontSize: 13 }}
                      onClick={() => router.push(`/er-diagram/lab/${lab.id}/join`)}>
                      Join
                    </button>
                  ) : (
                    <button className="btn btn-secondary" style={{ minHeight: 32, padding: "0 12px", fontSize: 13 }}
                      onClick={() => router.push(`/er-diagram/lab/${lab.id}/history`)}>
                      View history
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  };

  return (
    <div className="er-page-container">
      {/* Page head */}
      <div className="page-head">
        <div>
          <h2 style={{ fontSize: 28, marginBottom: 6 }}>ER Diagram Practice</h2>
          <p style={{ color: "var(--text-muted)" }}>
            Pick a question and sketch the entities, relationships, and keys.
          </p>
        </div>
        {activeTab === "lab" ? (
          isStaff && (
            <a href="/er-diagram/lab/new" className="btn btn-brand">
              <IconPlus />
              New ER Lab
            </a>
          )
        ) : (
          <a href="/er-diagram/add" className="btn btn-secondary">
            <IconPlus />
            Add Question
          </a>
        )}
      </div>

      {/* Loading */}
      {loading && (
        <div className="loading-center">
          <div className="spinner" />
          <span>Loading…</span>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="da-alert alert-error" role="alert">
          <strong>Error</strong>
          <span>{error}</span>
        </div>
      )}

      {/* Tabs + content */}
      {!loading && !error && (
        <>
          <div className="tabs" role="tablist">
            {["student-created", "staff-created", "lab"].map((tab) => (
              <button
                key={tab}
                role="tab"
                className={`tab${activeTab === tab ? " active" : ""}`}
                aria-selected={activeTab === tab}
                onClick={() => setActiveTab(tab)}
              >
                {tab === "student-created"
                  ? "Student-created"
                  : tab === "staff-created"
                  ? "Staff-created"
                  : "Lab"}
              </button>
            ))}
          </div>

          <div role="tabpanel">
            {activeTab === "student-created" &&
              renderQuestions(studentCreatedQuestions, "No student-created ER questions saved yet.")}
            {activeTab === "staff-created" &&
              renderQuestions(staffCreatedQuestions, "No staff-created ER questions saved yet.")}
            {activeTab === "lab" && (isStaff ? renderStaffLabTable() : renderStudentLabTable())}
          </div>
        </>
      )}
    </div>
  );
}
