'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { notifications } from '@mantine/notifications';
import dynamic from 'next/dynamic';

const Editor = dynamic(() => import('@monaco-editor/react'), { ssr: false });
import { LabDetail } from '@/types/lab.types';
import { labService } from '@/services/lab.service';
import { MarkdownDescriptionField } from '@/components/common/MarkdownDescriptionField';

interface LabFormProps {
  lab?: LabDetail;
  isEdit?: boolean;
  onSuccess?: (labId: number) => void;
  submitLabel?: string;
  labType?: 'sql' | 'graph';
}

export function LabForm({ lab, isEdit = false, onSuccess, submitLabel, labType: labTypeProp }: LabFormProps) {
  const labType: 'sql' | 'graph' = labTypeProp ?? lab?.lab_type ?? 'sql';
  const router = useRouter();

  // Form state
  const [title, setTitle] = useState(lab?.title || '');
  const [description, setDescription] = useState(lab?.description || '');
  const [schemaSql, setSchemaSql] = useState(lab?.schema_sql || '');
  const [sampleDataSql, setSampleDataSql] = useState(lab?.sample_data_sql || '');

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    // Validation
    if (!title.trim()) {
      setError('Title is required');
      return;
    }
    if (!description.trim()) {
      setError('Description is required');
      return;
    }
    if (!schemaSql.trim()) {
      setError(labType === 'graph' ? 'Cypher Statements are required' : 'Schema SQL is required');
      return;
    }
    if (labType !== 'graph' && !sampleDataSql.trim()) {
      setError('Sample Data SQL is required');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const payload = {
        title,
        description,
        schema_sql: schemaSql,
        // Graph labs use a single Cypher field; send a placeholder for the unused column
        sample_data_sql: labType === 'graph' ? ' ' : sampleDataSql,
        lab_type: labType,
      };

      if (isEdit && lab) {
        await labService.updateLab(lab.id, payload);
        notifications.show({
          title: 'Success',
          message: 'Lab updated successfully',
          color: 'green',
        });
        if (onSuccess) { onSuccess(lab.id); } else { router.push('/admin/labs'); }
      } else {
        const created = await labService.createLab(payload);
        notifications.show({
          title: 'Success',
          message: 'Lab created successfully',
          color: 'green',
        });
        if (onSuccess) { onSuccess(created.id); } else { router.push('/admin/labs'); }
      }
    } catch (err) {
      const error = err as { response?: { data?: { detail?: string } } };
      const errorMessage =
        error.response?.data?.detail || `Failed to ${isEdit ? 'update' : 'create'} lab`;
      setError(errorMessage);
      notifications.show({
        title: 'Error',
        message: errorMessage,
        color: 'red',
      });
    } finally {
      setLoading(false);
    }
  };

  const isDisabled = loading || (isEdit && lab?.is_running);

  return (
    <form onSubmit={handleSubmit} style={{ display: 'grid', gap: 20 }}>
      {/* Error alert */}
      {error && (
        <div className="da-alert alert-error" role="alert">
          <strong>Error</strong>
          <span>{error}</span>
        </div>
      )}

      {/* Running warning */}
      {isEdit && lab && lab.is_running && (
        <div className="da-alert alert-warn" role="alert">
          <strong>Lab is Running</strong>
          <span>This lab is currently running. Stop the lab before editing.</span>
        </div>
      )}

      {/* Title */}
      <div style={{ display: 'grid', gap: 6 }}>
        <label htmlFor="lab-title" style={{ fontSize: 13, fontWeight: 700, color: 'var(--brand-charcoal)' }}>
          Title <span style={{ color: 'var(--error)' }}>*</span>
        </label>
        <input
          id="lab-title"
          className="da-input"
          style={{ width: '100%' }}
          type="text"
          placeholder="Enter lab title"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          disabled={isDisabled}
          required
        />
      </div>

      {/* Description */}
      <MarkdownDescriptionField
        id="lab-description"
        label="Description"
        required
        placeholder="Enter lab description"
        value={description}
        onChange={setDescription}
        disabled={isDisabled}
      />

      {/* SQL / Graph editors */}
      {labType === 'graph' ? (
        <div style={{ display: 'grid', gap: 6 }}>
          <label style={{ fontSize: 13, fontWeight: 700, color: 'var(--brand-charcoal)' }}>
            Cypher Statements (CREATE / MERGE) <span style={{ color: 'var(--error)' }}>*</span>
          </label>
          <div style={{ border: '1px solid var(--border-strong)', borderRadius: 'var(--radius)', overflow: 'hidden' }}>
            <Editor
              height="300px"
              language="cypher"
              theme="vs-dark"
              value={schemaSql}
              onChange={(value) => setSchemaSql(value || '')}
              options={{
                minimap: { enabled: false },
                fontSize: 13,
                lineNumbers: 'on',
                scrollBeyondLastLine: false,
                readOnly: isDisabled ?? false,
              }}
            />
          </div>
        </div>
      ) : (
        <>
          <div style={{ display: 'grid', gap: 6 }}>
            <label style={{ fontSize: 13, fontWeight: 700, color: 'var(--brand-charcoal)' }}>
              Schema SQL (CREATE TABLE statements) <span style={{ color: 'var(--error)' }}>*</span>
            </label>
            <div style={{ border: '1px solid var(--border-strong)', borderRadius: 'var(--radius)', overflow: 'hidden' }}>
              <Editor
                height="200px"
                language="sql"
                theme="vs-dark"
                value={schemaSql}
                onChange={(value) => setSchemaSql(value || '')}
                options={{
                  minimap: { enabled: false },
                  fontSize: 13,
                  lineNumbers: 'on',
                  scrollBeyondLastLine: false,
                  readOnly: isDisabled ?? false,
                }}
              />
            </div>
          </div>

          <div style={{ display: 'grid', gap: 6 }}>
            <label style={{ fontSize: 13, fontWeight: 700, color: 'var(--brand-charcoal)' }}>
              Sample Data SQL (INSERT statements) <span style={{ color: 'var(--error)' }}>*</span>
            </label>
            <div style={{ border: '1px solid var(--border-strong)', borderRadius: 'var(--radius)', overflow: 'hidden' }}>
              <Editor
                height="200px"
                language="sql"
                theme="vs-dark"
                value={sampleDataSql}
                onChange={(value) => setSampleDataSql(value || '')}
                options={{
                  minimap: { enabled: false },
                  fontSize: 13,
                  lineNumbers: 'on',
                  scrollBeyondLastLine: false,
                  readOnly: isDisabled ?? false,
                }}
              />
            </div>
          </div>
        </>
      )}

      {/* Actions */}
      <div className="button-row" style={{ justifyContent: 'flex-end', marginTop: 8 }}>
        <button
          type="button"
          className="btn btn-secondary"
          onClick={() => router.push('/admin/labs')}
          disabled={loading}
        >
          Cancel
        </button>
        <button
          type="submit"
          className="btn btn-brand"
          disabled={isDisabled ?? false}
        >
          {loading ? 'Saving…' : (submitLabel ?? (isEdit ? 'Update Lab' : 'Create Lab'))}
        </button>
      </div>
    </form>
  );
}
