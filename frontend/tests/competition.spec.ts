import { expect, test, type Page } from '@playwright/test';

const api = `http://127.0.0.1:${process.env.RESCUE_TEST_API_PORT || '8017'}`;

async function editQuery(page: Page, sql: string) {
  const editor = page.locator('.monaco-editor');
  await expect(editor).toHaveCount(1, { timeout: 30000 });
  await editor.click();
  await page.keyboard.press('ControlOrMeta+A');
  await page.keyboard.insertText(sql);
}

test('presentation missions open directly, autosave, judge repairs and complete participation', async ({ page, request }) => {
  test.setTimeout(120000);
  const token = (await (await request.get(`${api}/test-token/student`)).json()).token as string;
  const headers = { Authorization: `Bearer ${token}` };
  await page.addInitScript(value => localStorage.setItem('access_token', value), token);
  await page.goto('/student/competitions');
  await expect(page.getByRole('heading', { name: 'Find the fault. Restore the feature.' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Competition', exact: true })).toBeVisible();
  await page.getByRole('link', { name: 'View competition' }).click();
  await page.getByRole('button', { name: 'Join competition' }).click();
  await expect(page.getByRole('heading', { name: 'Rescue missions', exact: true })).toBeVisible();
  await expect(page.getByText(/unaided|pre-test|post-test/i)).toHaveCount(0);
  await expect(page.getByRole('link', { name: 'Open incident', exact: true })).toHaveCount(2);
  const assistance = await request.post(`${api}/api/v1/chatbot/course-chat`, { headers, data: {} });
  expect(assistance.status()).toBe(200);

  await page.getByRole('link', { name: 'Open incident', exact: true }).first().click();
  await expect(page.getByRole('heading', { name: 'Empty student directory', exact: true })).toBeVisible();
  await expect(page.getByText('Alice', { exact: true })).toBeVisible();
  await expect(page.getByText('Business', { exact: true })).toBeVisible();
  await expect(page.getByText('No rows returned.', { exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Checkpoint assistance' })).toBeVisible();
  await page.getByLabel('Incorrect', { exact: true }).check();
  const explanation = 'Student IDs identify people. The directory needs the department foreign key to find each department.';
  await page.getByRole('textbox', { name: 'Short explanation', exact: true }).fill(explanation);
  await expect(page.getByText('Saved', { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByRole('textbox', { name: 'Short explanation', exact: true })).toHaveValue(explanation);
  await expect(page.getByLabel('Incorrect', { exact: true })).toBeChecked();

  await editQuery(page, 'SELECT 42 AS attempted_repair');
  await page.getByRole('button', { name: 'Preview query output', exact: true }).click();
  await expect(page.getByRole('columnheader', { name: 'attempted_repair', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Submit answer', exact: true }).click();
  await expect(page.getByText('Answer submitted. Return to the overview to view your progress.')).toBeVisible();
  let detail = await (await request.get(`${api}/api/v1/competitions/1`, { headers })).json();
  expect(detail.participation.points).toBe(0);
  expect(detail.participation.items[0].submitted).toBe(true);
  expect(detail.participation.participation_complete).toBe(false);

  const easyRepair = 'SELECT s.student_name, d.department_name FROM Students s JOIN Departments d ON s.department_id=d.department_id ORDER BY s.student_id';
  await editQuery(page, easyRepair);
  await page.getByRole('button', { name: 'Check repair across scenarios', exact: true }).click();
  await expect(page.getByText('The repair passes all required checks. Points are awarded when you submit your answer.')).toBeVisible();
  await page.getByLabel('Correct', { exact: true }).check();
  await expect(page.getByText('The repair passes all required checks. Points are awarded when you submit your answer.')).toHaveCount(0);
  await page.getByLabel('Incorrect', { exact: true }).check();
  await page.getByRole('button', { name: 'Submit answer', exact: true }).click();
  await expect(page.getByText('Answer submitted. Return to the overview to view your progress.')).toBeVisible();
  await page.getByRole('link', { name: 'Competition overview', exact: false }).click();
  await expect(page.getByText('1 / 2 answers submitted', { exact: true })).toBeVisible();
  detail = await (await request.get(`${api}/api/v1/competitions/1`, { headers })).json();
  expect(detail.participation.points).toBe(10);

  await page.getByRole('article').filter({ has: page.getByRole('heading', { name: 'Missing residents', exact: true }) }).getByRole('link', { name: 'Open incident', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Missing residents', exact: true })).toBeVisible();
  await page.getByLabel('Incorrect', { exact: true }).check();
  await editQuery(page, "SELECT r.resident_id, r.resident_name, COUNT(t.ticket_id) AS open_tickets FROM Residents r LEFT JOIN Tickets t ON r.resident_id=t.resident_id AND t.status='OPEN' GROUP BY r.resident_id,r.resident_name ORDER BY r.resident_id");
  await page.getByRole('textbox', { name: 'Short explanation', exact: true }).fill('WHERE excludes residents without open tickets. Filter in ON and count actual ticket IDs to preserve zero counts.');
  await page.getByRole('button', { name: 'Submit answer', exact: true }).click();
  await expect(page.getByText('Answer submitted. Return to the overview to view your progress.')).toBeVisible();
  await page.getByRole('link', { name: 'Competition overview', exact: false }).click();
  await expect(page.getByRole('heading', { name: 'Complete', exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Optional feedback', exact: true })).toBeVisible();
  await expect(page.getByText('Joins Rescuer', { exact: true })).toBeVisible();
  detail = await (await request.get(`${api}/api/v1/competitions/1`, { headers })).json();
  expect(detail.participation.points).toBe(30);
  expect(detail.participation.participation_complete).toBe(true);
  expect(detail.participation.items).toHaveLength(2);
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 2)).toBeTruthy();
  await page.screenshot({ path: 'test-results/competition-presentation-mobile.png', fullPage: true });
});

test('staff sees the two slide examples and mission-only configuration', async ({ page, request }) => {
  const token = (await (await request.get(`${api}/test-token/staff`)).json()).token as string;
  await page.addInitScript(value => localStorage.setItem('access_token', value), token);
  await page.goto('/admin/competitions');
  await expect(page.getByRole('button', { name: 'Prepare starter drafts', exact: true })).toHaveCount(0);
  await expect(page.getByRole('heading', { name: 'Database Rescue', exact: true })).toBeVisible();
  await page.getByRole('link', { name: 'Manage competition', exact: true }).click();
  await expect(page.getByRole('listbox', { name: 'Required incidents', exact: true })).toBeVisible();
  await expect(page.getByRole('spinbutton', { name: 'easy answer points', exact: true })).toHaveValue('10');
  await expect(page.getByRole('spinbutton', { name: 'medium answer points', exact: true })).toHaveValue('20');
  await expect(page.getByText(/test form|pre-test|post-test/i)).toHaveCount(0);
  await page.getByRole('link', { name: 'Competition management', exact: false }).click();
  await page.getByRole('button', { name: 'Incident library', exact: true }).click();
  await expect(page.getByRole('link', { name: 'Create private incident', exact: true })).toHaveCount(0);
  await expect(page.locator('a[href="/admin/competitions/incidents/new"]')).toHaveCount(0);
  await expect(page.getByRole('link', { name: 'Review incident', exact: true })).toHaveCount(2);
  await page.getByRole('link', { name: 'Review incident', exact: true }).first().click();
  await expect(page.getByRole('textbox', { name: 'Definition JSON', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Validate all scenarios' })).toBeVisible();
});

test('source permission persists and approval uses review controls, then refreshes the incident picker', async ({ page, request }) => {
  test.setTimeout(120000);
  const token = (await (await request.get(`${api}/test-token/staff`)).json()).token as string;
  const headers = { Authorization: `Bearer ${token}` };
  await page.addInitScript(value => localStorage.setItem('access_token', value), token);
  const approved = await (await request.get(`${api}/api/v1/admin/competition-incident-versions/1`, { headers })).json();
  const doc = { ...approved.document, title: 'Approval via review controls', oracle_confirmed: false };
  const sourceResponse = await request.post(`${api}/api/v1/admin/competition-sources/import`, { headers, data: { entries: [{
    id: 'browser-permission', title: 'Permission review exercise', schema_sql: doc.schema_sql,
    sample_data_sql: doc.scenarios.find((scenario: { visible: boolean }) => scenario.visible).seed_sql,
    correct_answer_query: doc.components[0].reference_query,
  }] } });
  expect(sourceResponse.ok()).toBeTruthy();
  const source = (await sourceResponse.json())[0];
  const created = await (await request.post(`${api}/api/v1/admin/competition-incidents`, { headers, data: { document: doc, source_id: source.id } })).json();

  await page.goto('/admin/competitions/new');
  await expect(page.getByRole('listbox', { name: 'Required incidents', exact: true })).toBeVisible();
  await expect(page.getByRole('option', { name: /Approval via review controls/ })).toHaveCount(0);
  await page.getByRole('link', { name: 'Competition management', exact: false }).click();
  await page.getByRole('button', { name: 'Incident library', exact: true }).click();
  await page.getByRole('article').filter({ has: page.getByRole('heading', { name: doc.title, exact: true }) }).getByRole('link', { name: 'Review incident', exact: true }).click();
  const definition = page.getByRole('textbox', { name: 'Definition JSON', exact: true });
  expect(JSON.parse(await definition.inputValue())).not.toHaveProperty('oracle_confirmed');
  const permission = page.getByRole('region', { name: 'Source permission', exact: true });
  await permission.getByRole('button', { name: 'Save source permission', exact: true }).click();
  await expect(permission.getByRole('alert')).toContainText('Tick the source permission checkbox');
  await permission.getByRole('checkbox', { name: 'I confirm permission to use this source exercise.', exact: true }).check();

  const authorisePath = `**/api/v1/admin/competition-sources/${source.id}/authorise`;
  await page.route(authorisePath, route => route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: 'Source permission temporarily unavailable. Try again.' }) }));
  await permission.getByRole('button', { name: 'Save source permission', exact: true }).click();
  await expect(permission.getByRole('alert')).toContainText('Source permission temporarily unavailable');
  await expect(permission.getByRole('button', { name: 'Save source permission', exact: true })).toBeEnabled();
  await page.unroute(authorisePath);
  await permission.getByRole('button', { name: 'Save source permission', exact: true }).click();
  await expect(permission.getByText('Source permission is confirmed', { exact: false })).toBeVisible();
  await page.reload();
  await expect(permission.getByText('Source permission is confirmed', { exact: false })).toBeVisible();
  await expect(permission.getByRole('button', { name: 'Save source permission', exact: true })).toHaveCount(0);

  await page.getByRole('button', { name: 'Approve immutable version', exact: true }).click();
  await expect(page.getByRole('alert').filter({ hasText: 'review checkbox' })).toContainText('review checkbox');
  await page.getByRole('checkbox', { name: 'I have reviewed the expected outputs and business rules.', exact: true }).check();
  await page.getByRole('button', { name: 'Approve immutable version', exact: true }).click();
  await expect(page.getByText(/Incident approved as version v\d+\./)).toBeVisible({ timeout: 30000 });
  const saved = await (await request.get(`${api}/api/v1/admin/competition-incidents/${created.id}`, { headers })).json();
  expect(saved.document.oracle_confirmed).toBe(true);
  expect(saved.status).toBe('approved');
  await page.getByRole('link', { name: 'Create a competition using approved incidents', exact: true }).click();
  await expect(page.getByRole('listbox', { name: 'Required incidents', exact: true }).getByRole('option', { name: /Approval via review controls/ })).toHaveCount(1);

  await page.goto(`/admin/competitions/incidents/${created.id}`);
  const reviewed = page.getByRole('checkbox', { name: 'I have reviewed the expected outputs and business rules.', exact: true });
  await expect(reviewed).toBeChecked();
  const changed = JSON.parse(await definition.inputValue());
  changed.complaint = 'The directory still needs investigation after a newly reported complaint.';
  await definition.fill(JSON.stringify(changed, null, 2));
  await expect(reviewed).not.toBeChecked();
  await page.getByRole('button', { name: 'Approve immutable version', exact: true }).click();
  await expect(page.getByRole('alert').filter({ hasText: 'review checkbox' })).toContainText('review checkbox');
});

test('an incident created from scratch through question sources can be reviewed and approved', async ({ page, request }) => {
  const token = (await (await request.get(`${api}/test-token/staff`)).json()).token as string;
  await page.addInitScript(value => localStorage.setItem('access_token', value), token);
  await page.goto('/admin/competitions');
  await page.getByRole('button', { name: 'Question sources', exact: true }).click();
  await page.getByRole('radio', { name: 'Create from scratch', exact: true }).check();
  await expect(page.getByRole('combobox', { name: 'Fault to introduce', exact: true })).toHaveCount(0);
  await expect(page.getByRole('checkbox', { name: 'I confirm permission to use the selected exercise.', exact: true })).toHaveCount(0);
  await page.getByRole('button', { name: 'Create incident draft', exact: true }).click();
  await expect(page).toHaveURL(/\/admin\/competitions\/incidents\/new$/);
  await expect(page.getByRole('checkbox', { name: 'I have reviewed the expected outputs and business rules.', exact: true })).not.toBeChecked();
  await page.getByRole('checkbox', { name: 'I have reviewed the expected outputs and business rules.', exact: true }).check();
  await page.getByRole('button', { name: 'Approve immutable version', exact: true }).click();
  await expect(page.getByText(/Incident approved as version v\d+\./)).toBeVisible({ timeout: 30000 });
  await page.getByRole('link', { name: 'Create a competition using approved incidents', exact: true }).click();
  await expect(page.getByRole('listbox', { name: 'Required incidents', exact: true }).getByRole('option', { name: /Directory records have disappeared/ })).toHaveCount(1);
});

test('question selection and fault adaptation share one form and surface validation blockers', async ({ page, request }) => {
  const token = (await (await request.get(`${api}/test-token/staff`)).json()).token as string;
  await page.addInitScript(value => localStorage.setItem('access_token', value), token);
  await page.goto('/admin/competitions');
  await page.getByRole('button', { name: 'Question sources', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Create an incident', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Import a source snapshot', exact: true })).toHaveCount(0);
  await page.getByText('Upload extracted SQL questions (optional)', { exact: true }).click();
  const question = { id: 'browser-upload', title: 'Uploaded directory exercise',
    sql_schema: "CREATE TABLE Person(id INT, name VARCHAR(20)); CREATE TABLE Address(personId INT, city VARCHAR(20)); INSERT INTO Person VALUES (1,'Ari'),(2,'Bo'); INSERT INTO Address VALUES (2,'East');",
    answer: 'SELECT p.name, a.city FROM Person p LEFT JOIN Address a ON p.id=a.personId' };
  await page.getByLabel('Source JSON file', { exact: true }).setInputFiles({ name: 'questions.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify([question])) });
  await expect(page.getByRole('radio', { name: 'Uploaded or previously imported sources', exact: true })).toBeChecked();
  await expect(page.getByRole('combobox', { name: 'Imported source', exact: true })).not.toHaveValue('');
  await page.getByRole('combobox', { name: 'Fault to introduce', exact: true }).selectOption('left_to_inner');
  await page.getByRole('textbox', { name: 'Application complaint', exact: true }).fill('A registered person has disappeared from the directory.');
  await page.getByRole('textbox', { name: 'Required application behaviour', exact: true }).fill('Display every person with their address or NULL for an unmatched address.');
  await page.getByRole('checkbox', { name: 'I confirm permission to use the selected exercise.', exact: true }).check();
  await page.getByRole('button', { name: 'Create incident draft', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Edit incident: Uploaded directory exercise', exact: true })).toBeVisible();
  await expect(page.getByText('Source permission is confirmed', { exact: false })).toBeVisible();
  const definition = JSON.parse(await page.getByRole('textbox', { name: 'Definition JSON', exact: true }).inputValue());
  expect(definition.components[0].query).toContain('INNER JOIN');
  expect(definition).not.toHaveProperty('oracle_confirmed');
  await page.getByRole('checkbox', { name: 'I have reviewed the expected outputs and business rules.', exact: true }).check();
  await page.getByRole('button', { name: 'Approve immutable version', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Review required', exact: true })).toBeVisible();
  await expect(page.getByText('Scenario seeds must be distinct; replace adaptation placeholders.', { exact: true })).toBeVisible();
  await expect(page.getByText(/Incident approved as version v\d+\./)).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Approve immutable version', exact: true })).toBeEnabled();
});
