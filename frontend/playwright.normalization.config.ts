import { defineConfig } from '@playwright/test';
import path from 'node:path';
import { existsSync } from 'node:fs';

const localPython = path.resolve(__dirname,
  process.platform === 'win32' ? '../backend/venv/Scripts/python.exe' : '../backend/venv/bin/python');
const python = process.env.NORMALIZATION_TEST_PYTHON || (existsSync(localPython) ? localPython : 'python');

export default defineConfig({
  testDir: './normalization-tests', testMatch: 'normalization.spec.ts', timeout: 60000, workers: 1,
  use: { baseURL: 'http://127.0.0.1:3019', channel: process.env.PLAYWRIGHT_CHANNEL || 'chrome', headless: true, actionTimeout: 10000,
    viewport: { width: 1440, height: 1000 }, trace: 'retain-on-failure' },
  webServer: [
    { command: `"${python}" ../backend/tests/normalization/browser_server.py`, url: 'http://127.0.0.1:8019/health', timeout: 90000, reuseExistingServer: false },
    { command: 'node node_modules/next/dist/bin/next start --hostname 127.0.0.1 --port 3019', url: 'http://127.0.0.1:3019/login', timeout: 60000, reuseExistingServer: false },
  ],
});
