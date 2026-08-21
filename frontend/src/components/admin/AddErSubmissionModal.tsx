'use client';

import { useEffect, useState } from 'react';
import {
  Alert,
  Button,
  FileInput,
  Group,
  Modal,
  Radio,
  Stack,
  Text,
  Textarea,
} from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { IconAlertTriangle, IconInfoCircle } from '@tabler/icons-react';

import {
  addStudentSubmission,
  AddStudentSubmissionResult,
  fetchStudentDraft,
} from '@/services/er-analytics.service';
import { DRAWIO_RENDERER_URL, OFFSCREEN_FRAME_STYLE, useErXmlToPng } from './useErXmlToPng';

/** Where the diagram comes from. All three end in the same grader; they differ
 *  only in how the diagram is read, so the picker is the whole interface. */
type Source = 'draft' | 'file' | 'image';

interface AddErSubmissionModalProps {
  opened: boolean;
  onClose: () => void;
  onGraded: (result: AddStudentSubmissionResult) => void;
  studentId: number;
  studentName: string;
  questionId: number;
  questionTitle: string;
  hasSavedDraft: boolean;
  draftUpdatedAt?: string | null;
  hasExistingGrade: boolean;
}


export function AddErSubmissionModal({
  opened,
  onClose,
  onGraded,
  studentId,
  studentName,
  questionId,
  questionTitle,
  hasSavedDraft,
  draftUpdatedAt,
  hasExistingGrade,
}: AddErSubmissionModalProps) {
  const [source, setSource] = useState<Source>(hasSavedDraft ? 'draft' : 'file');
  const [file, setFile] = useState<File | null>(null);
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [stage, setStage] = useState<'drawing' | 'grading' | null>(null);
  const [draftXml, setDraftXml] = useState<string | null>(null);

  const { frameRef, render } = useErXmlToPng();

  // The draft XML is fetched up front so it can be drawn to a PNG before the
  // request goes out. The server reads its own copy for grading — this one only
  // exists to make a picture.
  useEffect(() => {
    if (!opened || !hasSavedDraft) return;
    let cancelled = false;
    fetchStudentDraft(questionId, studentId)
      .then((d) => {
        if (!cancelled && d.exists && d.xml) setDraftXml(d.xml);
      })
      .catch(() => {
        // A picture is optional; grading the draft does not need this copy.
      });
    return () => {
      cancelled = true;
    };
  }, [opened, hasSavedDraft, questionId, studentId]);

  const needsFile = source === 'file' || source === 'image';
  // The reason is optional. A diagram is not: without one there is nothing to grade.
  const canSubmit = (!needsFile || file !== null) && !busy;

  const handleSubmit = async () => {
    setBusy(true);
    try {
      // A .drawio file is XML, so it is read here and sent as text; the server
      // parses it exactly. Only an image goes up as a file for the vision model.
      const xmlText = source === 'file' && file ? await file.text() : undefined;

      // An XML source stores no picture of its own, so draw one. Best effort:
      // a null result means the attempt is graded without a thumbnail, which is
      // strictly better than refusing to grade it.
      let renderedPng: File | null = null;
      const xmlToDraw = source === 'draft' ? draftXml : xmlText;
      if (xmlToDraw) {
        setStage('drawing');
        renderedPng = await render(xmlToDraw);
      }

      setStage('grading');
      const result = await addStudentSubmission({
        questionId,
        studentId,
        reason: reason.trim(),
        regrade: hasExistingGrade,
        useSavedDraft: source === 'draft',
        xmlText,
        imageFile: source === 'image' && file ? file : undefined,
        renderedPng,
      });

      notifications.show({
        color: 'teal',
        title: 'Submission added',
        message: `${studentName} scored ${result.score.percent ?? '?'}%.`,
      });
      onGraded(result);
      onClose();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data
        ?.detail;
      notifications.show({
        color: 'red',
        title: 'Could not add the submission',
        message: detail ?? 'The grader did not return a result. Nothing was saved.',
      });
    } finally {
      setBusy(false);
      setStage(null);
    }
  };

  return (
    <Modal
      opened={opened}
      // Closing mid-request would only hide the spinner; the grade still lands.
      // Blocking the close keeps the result visible instead.
      onClose={busy ? () => undefined : onClose}
      title={`Add a submission for ${studentName}`}
      size="lg"
    >
      <Stack gap="md">
        <Text size="sm" c="dimmed">
          This creates a real submission for <strong>{questionTitle}</strong> and changes{' '}
          {studentName}&apos;s assessment mark.
        </Text>

        {hasExistingGrade && (
          <Alert color="orange" icon={<IconAlertTriangle size={16} />}>
            {studentName} already has a grade for this question. Continuing replaces it.
          </Alert>
        )}

        <Radio.Group
          label="Where does the diagram come from?"
          value={source}
          onChange={(value) => {
            setSource(value as Source);
            setFile(null);
          }}
        >
          <Stack gap="xs" mt="xs">
            <Radio
              value="draft"
              disabled={!hasSavedDraft || busy}
              label="The student's autosaved canvas"
              description={
                hasSavedDraft
                  ? `Last saved ${
                      draftUpdatedAt ? new Date(draftUpdatedAt).toLocaleString() : 'at an unknown time'
                    }`
                  : 'No autosaved canvas exists for this student'
              }
            />
            <Radio
              value="file"
              disabled={busy}
              label="A .drawio or XML file"
              description="Graded from the file's structure. Exact."
            />
            <Radio
              value="image"
              disabled={busy}
              label="An image"
              description="A PNG or JPG, read by the vision model. Less exact, but it stores a picture."
            />
          </Stack>
        </Radio.Group>

        {needsFile && (
          <FileInput
            label={source === 'file' ? 'Diagram file' : 'Image file'}
            placeholder={
              source === 'file' ? 'Choose a .drawio or .xml file' : 'Choose a PNG or JPG'
            }
            accept={source === 'file' ? '.drawio,.xml,text/xml' : 'image/png,image/jpeg'}
            value={file}
            onChange={setFile}
            disabled={busy}
            clearable
          />
        )}

        <Textarea
          label="Reason, stored on the record (optional)"
          placeholder="Timer ended before the student submitted"
          value={reason}
          onChange={(event) => setReason(event.currentTarget.value)}
          minRows={2}
          maxLength={500}
          disabled={busy}
        />

        {busy && (
          <Alert color="blue" icon={<IconInfoCircle size={16} />}>
            {stage === 'drawing'
              ? 'Drawing a picture of the diagram…'
              : 'Grading the diagram. This takes up to 90 seconds. Keep this tab open.'}
          </Alert>
        )}

        {/* Off screen, but real pixels: draw.io exports a blank image from a
            hidden or zero-sized frame. */}
        <iframe
          ref={frameRef}
          src={DRAWIO_RENDERER_URL}
          title="Diagram renderer"
          style={OFFSCREEN_FRAME_STYLE}
        />

        <Group justify="flex-end">
          <Button variant="default" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} loading={busy} disabled={!canSubmit}>
            Add submission
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}
