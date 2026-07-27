import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  timeout: 60000,
  expect: { timeout: 10000 },
  fullyParallel: true,
  retries: 1,
  workers: 1,
  reporter: 'list',
  use: {
    baseURL: 'http://localhost:5173',
    trace: 'on-first-retry',
    screenshot: 'on-first-retry',
    headless: true,
  },
  webServer: [
    {
      command: 'cd backend && .venv/Scripts/python.exe -m uvicorn app.main:app --port 8000',
      port: 8000,
      reuseExistingServer: true,
      timeout: 30000,
    },
    {
      command: 'cd frontend && npm run dev',
      port: 5173,
      reuseExistingServer: true,
      timeout: 30000,
    },
  ],
  projects: [
    { name: 'chromium', use: { browserName: 'chromium' } },
  ],
})
