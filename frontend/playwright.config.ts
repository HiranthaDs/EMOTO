import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: 'list',
  use: { baseURL: 'http://127.0.0.1:10001', channel: 'chrome', screenshot: 'only-on-failure', trace: 'retain-on-failure' },
  webServer: {
    command: '..\\.venv\\Scripts\\python.exe -m app.migrate && ..\\.venv\\Scripts\\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 10001',
    cwd: '../backend',
    env: { ...process.env, DATA_DIR: 'data/e2e', INITIAL_ADMIN_EMAIL: 'admin@gmail.com', INITIAL_ADMIN_PASSWORD: 'admin@123', SESSION_SECRET: 'e2e-session-secret-long-enough-for-testing' },
    url: 'http://127.0.0.1:10001/health',
    reuseExistingServer: false,
    timeout: 30_000,
  },
  projects: [
    { name: 'desktop-1440', use: { ...devices['Desktop Chrome'], channel: 'chrome', viewport: { width: 1440, height: 900 } } },
    { name: 'tablet-1024', use: { ...devices['Desktop Chrome'], channel: 'chrome', viewport: { width: 1024, height: 768 } } },
    { name: 'tablet-768', use: { ...devices['Desktop Chrome'], channel: 'chrome', viewport: { width: 768, height: 900 } } },
    { name: 'mobile-390', use: { ...devices['Desktop Chrome'], channel: 'chrome', viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true } },
    { name: 'mobile-360', use: { ...devices['Desktop Chrome'], channel: 'chrome', viewport: { width: 360, height: 800 }, isMobile: true, hasTouch: true } },
  ],
})

