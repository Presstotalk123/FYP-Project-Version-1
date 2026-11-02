import { defineConfig } from '@playwright/test';

const apiPort = process.env.RESCUE_TEST_API_PORT || '8017';
const webPort = process.env.RESCUE_TEST_WEB_PORT || '3017';

export default defineConfig({
  testDir: './tests',
  timeout: 60000,
  workers: 1,
  use: { baseURL: `http://127.0.0.1:${webPort}`, channel: process.env.PLAYWRIGHT_CHANNEL || 'chrome', headless: true, trace: 'retain-on-failure' },
  webServer: [
    { command: `"${process.env.RESCUE_TEST_PYTHON || 'python'}" ../backend/competition_tests/browser_server.py`, url: `http://127.0.0.1:${apiPort}/health`, timeout: 120000, reuseExistingServer: false },
    { command: `node node_modules/next/dist/bin/next start --hostname 127.0.0.1 --port ${webPort}`, url: `http://127.0.0.1:${webPort}/login`, timeout: 60000, reuseExistingServer: false },
  ],
});
