import { expect, test, type Page } from '@playwright/test';

const api = 'http://127.0.0.1:8019';

async function login(page: Page, role: 'student' | 'staff') {
  const { token } = await (await page.request.get(`${api}/test-token/${role}`)).json();
  await page.addInitScript(value => localStorage.setItem('access_token', value), token);
}

async function choose(page: Page, label: string, values: string[]) {
  const control = page.getByRole('textbox', { name: label, exact: true });
  for (const value of values) {
    // Non-searchable Mantine MultiSelect uses a hidden pills field; Space is
    // its supported keyboard interaction (the visible wrapper owns pointer clicks).
    await control.press('Space');
    await page.getByRole('option', { name: value, exact: true }).click();
    await page.keyboard.press('Escape');
  }
}

async function submit(page: Page) {
  await page.getByRole('button', { name: 'Submit', exact: true }).click();
  await page.getByRole('button', { name: 'Evaluate both sections', exact: true }).click();
}

test.beforeEach(async ({ page }) => {
  page.on('dialog', dialog => dialog.accept());
  // The production bundle uses its configured API origin. Route only the test
  // browser's requests to the disposable real backend, preserving JWT headers.
  await page.route('**/api/v1/**', async route => {
    const url = new URL(route.request().url());
    const response = await route.fetch({ url: `${api}${url.pathname}${url.search}` });
    await route.fulfill({ response });
  });
  await login(page, 'student');
});

test('normalization outage leaves existing SQL and ERD problems available', async ({ page }) => {
  const { token } = await (await page.request.get(`${api}/test-token/staff`)).json();
  const headers = { Authorization: `Bearer ${token}` };
  const sql = await page.request.post(`${api}/api/v1/questions`, { headers, data: {
    title: 'SQL outage regression', description: 'Select one', difficulty: 'easy',
    schema_sql: 'CREATE TABLE t (id INTEGER);', sample_data_sql: 'INSERT INTO t VALUES (1);', correct_answer_query: 'SELECT id FROM t',
  } });
  expect(sql.ok()).toBeTruthy();
  expect((await page.request.post(`${api}/api/v1/questions/${(await sql.json()).id}/publish`, { headers })).ok()).toBeTruthy();
  const erd = await page.request.post(`${api}/api/v1/er-diagram/questions`, { headers, multipart: {
    title: 'ERD outage regression', problem_statement: 'An entity', notation: 'Chen', difficulty_label: 'Easy',
    difficulty_rationale: 'One entity', rubric_md: 'Entity 1 mark', rubric_json: '{}', instruction_history: '[]',
  } });
  expect(erd.ok()).toBeTruthy();
  expect((await page.request.post(`${api}/api/v1/er-diagram/questions/${(await erd.json()).id}/publish`, { headers })).ok()).toBeTruthy();
  await page.route('**/api/v1/normalization/**', route => route.fulfill({ status: 503, json: { detail: 'Simulated normalization outage' } }));
  await page.goto('/student');
  await expect(page.getByText('Normalization questions are temporarily unavailable. You can still use the other question types.', { exact: true })).toBeVisible();
  await expect(page.getByText('SQL outage regression', { exact: true })).toBeVisible();
  await expect(page.getByText('ERD outage regression', { exact: true })).toBeVisible();
  await login(page, 'staff');
  await page.goto('/admin/problems');
  await expect(page.getByText('Normalization questions are temporarily unavailable. You can still use the other problem types.', { exact: true })).toBeVisible();
  await expect(page.getByText('SQL outage regression', { exact: true })).toBeVisible();
  await expect(page.getByText('ERD outage regression', { exact: true })).toBeVisible();
});

test('shared Problems, composite submission, immutable reopen, and draft restoration', async ({ page }, testInfo) => {
  await page.goto('/student');
  await page.getByRole('button', { name: /^Normalization\s/ }).click();
  await page.getByText('Normalization browser exercise', { exact: true }).click();
  await expect(page).toHaveURL(/student\/workspace\/1\?type=normalization/);
  await choose(page, 'FD 1 determinant', ['A']);
  await choose(page, 'FD 1 dependent', ['B']);
  await page.getByRole('button', { name: 'Propose A as key', exact: true }).click();
  await expect(page.getByLabel('Assumptions', { exact: true })).toHaveCount(0);
  await page.reload();
  await expect(page.getByRole('button', { name: 'Propose A as key', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await submit(page);
  await expect(page.getByText('Overall score: 100%', { exact: true })).toBeVisible();
  await page.getByText('Request staff review', { exact: true }).click();
  await page.getByLabel('Request staff review of FD interpretation').fill('Please explain the accepted interpretation.');
  await page.getByRole('button', { name: 'Request review', exact: true }).click();
  await expect(page.getByText(/Review requested —/)).toBeVisible();
  await page.getByRole('button', { name: 'Close submission result', exact: true }).click();
  await page.getByRole('button', { name: 'Reopen copy', exact: true }).first().click();
  const confirmation = page.getByRole('dialog').filter({ has: page.getByRole('heading', { name: 'Replace current draft?' }) });
  await expect(confirmation).toBeVisible();
  await confirmation.getByRole('button', { name: 'Reopen copy' }).click();
  await expect(page.getByRole('button', { name: 'Propose A as key', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await page.screenshot({ path: testInfo.outputPath('normalization-workspace.png'), fullPage: true });
});

test('recursive graph split, undo/redo, layout, and deterministic grade', async ({ page }, testInfo) => {
  await page.goto('/student/workspace/2?type=normalization');
  await choose(page, 'FD 1 determinant', ['A']); await choose(page, 'FD 1 dependent', ['B']);
  await page.getByRole('button', { name: 'Add functional dependency', exact: true }).click();
  await choose(page, 'FD 2 determinant', ['C']); await choose(page, 'FD 2 dependent', ['A']);
  await page.locator('.react-flow__node').first().click();
  await page.getByRole('button', { name: 'Decompose', exact: true }).click();
  await expect(page.getByRole('tab', { name: 'Build', exact: true })).toHaveCount(0);
  await expect(page.locator('.react-flow__node').getByRole('textbox', { name: 'Child 1 name', exact: true })).toBeVisible();
  await page.getByRole('textbox', { name: 'Dependency used for this split', exact: true }).click();
  await page.getByRole('option', { name: 'A → B', exact: true }).click();
  await choose(page, 'Child 1 attributes', ['A', 'B']); await choose(page, 'Child 1 proposed key', ['A']);
  await choose(page, 'Child 2 attributes', ['A', 'C']); await choose(page, 'Child 2 proposed key', ['C']);
  await page.getByRole('button', { name: 'Add split', exact: true }).click();
  await expect(page.locator('.react-flow__node')).toHaveCount(3);
  await page.getByRole('button', { name: 'Undo', exact: true }).click();
  await expect(page.locator('.react-flow__node')).toHaveCount(1);
  await page.getByRole('button', { name: 'Redo', exact: true }).click();
  await expect(page.locator('.react-flow__node')).toHaveCount(3);
  await page.getByRole('button', { name: 'Auto-layout' }).click();
  await expect(page.getByText(/candidate keys/)).toHaveCount(0);
  await submit(page);
  await expect(page.getByText('Overall score: 100%', { exact: true })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath('normalization-result.png'), fullPage: true });
});

test('assumptions appear only at submission when semantic interpretation is enabled', async ({ page }) => {
  let enabled = false;
  await page.route('**/api/v1/normalization/questions/1', async route => {
    const response = await route.fetch({ url: `${api}/api/v1/normalization/questions/1` });
    await route.fulfill({ response, json: { ...await response.json(), semantic_judge_enabled: enabled } });
  });
  await page.goto('/student/workspace/1?type=normalization');
  await expect(page.getByLabel('Assumptions', { exact: true })).toHaveCount(0);
  await page.getByRole('button', { name: 'Submit', exact: true }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await expect(page.getByLabel('Assumptions', { exact: true })).toHaveCount(0);
  await page.getByRole('button', { name: 'Continue editing', exact: true }).click();
  enabled = true;
  await page.reload();
  await expect(page.getByLabel('Assumptions', { exact: true })).toHaveCount(0);
  await page.getByRole('button', { name: 'Submit', exact: true }).click();
  const assumptions = page.getByRole('dialog').getByLabel('Assumptions', { exact: true });
  await expect(assumptions).toBeVisible();
  await assumptions.fill('A business-rule interpretation.');
  await page.getByRole('button', { name: 'Continue editing', exact: true }).click();
  await expect(page.getByLabel('Assumptions', { exact: true })).toHaveCount(0);
  await page.getByRole('button', { name: 'Submit', exact: true }).click();
  await expect(assumptions).toHaveValue('A business-rule interpretation.');
});

test('staff authors in shared Problems and resolves an FD interpretation', async ({ page }) => {
  const { token } = await (await page.request.get(`${api}/test-token/student`)).json();
  const relation = { name: 'R', attributes: ['A', 'B'], primary_key: ['A'] };
  const seeded = await page.request.post(`${api}/api/v1/normalization/questions/1/submissions`, {
    headers: { Authorization: `Bearer ${token}` }, data: {
      exercise_id: '1', exercise_version: '1', target_normal_form: 'BCNF', request_key: crypto.randomUUID(),
      functional_dependencies: [{ lhs: ['A'], rhs: ['B'] }], assumption: '', relations: [relation],
      process: { workflow: 'recursive_decomposition', root: { node_id: 'root', ...relation }, steps: [] }, canvas_positions: [],
    },
  });
  expect(seeded.ok()).toBeTruthy();
  await login(page, 'staff');
  await page.goto('/admin/problems');
  await page.getByRole('button', { name: 'Create Question' }).click();
  await page.getByRole('menuitem', { name: 'Normalization question', exact: true }).click();
  await page.getByRole('textbox', { name: 'Title', exact: true }).fill('Staff authored normalization');
  await page.getByRole('textbox', { name: /^Scenario/ }).fill('Each A determines one B.');
  const attributes = page.getByRole('textbox', { name: 'Attributes', exact: true });
  await attributes.fill('A'); await attributes.press('Enter'); await attributes.fill('B'); await attributes.press('Enter');
  await page.getByLabel('Rule', { exact: true }).fill('Each A determines B.');
  await choose(page, 'Approved FD 1 determinant', ['A']); await choose(page, 'Approved FD 1 dependent', ['B']);
  await expect(page.getByLabel('Enable AI semantic interpretation for this question')).not.toBeChecked();
  await page.getByRole('button', { name: 'Save question', exact: true }).click();
  const row = page.getByRole('row').filter({ hasText: 'Staff authored normalization' });
  await expect(row).toBeVisible();
  await row.getByTitle('Publish (show to students)', { exact: true }).click();
  await expect(row.getByText('Published', { exact: true })).toBeVisible();
  await page.getByRole('row').filter({ hasText: 'Normalization browser exercise' }).getByTitle('Normalization analytics').click();
  await page.getByRole('button', { name: 'View submission', exact: true }).first().click();
  await page.getByLabel('Reason (required, visible in review history)').fill('FD interpretation confirmed by staff.');
  await page.getByRole('button', { name: 'Record staff decision' }).click();
  await expect(page.getByText(/Staff decision: accepted — FD interpretation confirmed/)).toBeVisible();
});

test('assessment wrapper hides all correctness feedback', async ({ page }) => {
  const { token, clone_id } = await (await page.request.get(`${api}/test-token/student`)).json();
  const joined = await page.request.post(`${api}/api/v1/student-assessments/1/join`, { headers: { Authorization: `Bearer ${token}` }, data: {} });
  expect(joined.ok()).toBeTruthy();
  await page.goto(`/student/assessments/1/items/1/normalization-question?resourceId=${clone_id}&weight=100`);
  await choose(page, 'FD 1 determinant', ['A']); await choose(page, 'FD 1 dependent', ['B']); await page.getByRole('button', { name: 'Propose A as key', exact: true }).click();
  await submit(page);
  await expect(page.getByText('Submitted successfully. Feedback is hidden for this question.')).toBeVisible();
  await expect(page.getByText(/Overall \d/)).toHaveCount(0);
  await expect(page.getByText(/candidate keys/)).toHaveCount(0);
});
