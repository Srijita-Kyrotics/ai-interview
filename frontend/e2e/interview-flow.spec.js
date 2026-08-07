import { test, expect } from '@playwright/test'

const RESUME_TXT = `Jane E2E
jane.e2e@example.com
+1 555 0100

Professional Summary
Full-stack engineer with 4 years building scalable web applications.

Skills: Python, React, Node.js, SQL, Docker

Experience
Software Engineer, Acme Corp (2022 - Present)
Built REST APIs and React dashboards.

Education
B.Tech Computer Science, Example University

Projects
E2E Automation Platform
`

async function skipProctoringAndWaitForRoom(page) {
  await page.getByRole('button', { name: 'Skip Proctoring (Test Mode)' }).click()
  await expect(page.locator('.test-topbar')).toBeVisible()
}

async function readTotalQuestions(page) {
  const counter = await page.locator('.topbar-block strong').first().textContent()
  const match = /\d+\s*\/\s*(\d+)/.exec(counter || '')
  return match ? parseInt(match[1], 10) : 0
}

test('full interview flow: resume -> aptitude -> coding -> technical -> report', async ({ page }) => {
  const pageErrors = []
  const cspErrors = []
  const startFailures = []
  page.on('pageerror', (err) => pageErrors.push(err))
  page.on('response', (resp) => {
    if (resp.url().includes('/ai-interview/start') && resp.status() >= 400) {
      startFailures.push(`${resp.status()} ${resp.url()}`)
    }
  })
  page.on('console', (msg) => {
    if (msg.type() === 'error' && msg.text().includes('Content Security Policy')) {
      cspErrors.push(msg.text())
    }
  })

  // ── Sign up (plain email + password, no captcha/OTP) ─────────────────
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'AI Interview Coach' })).toBeVisible()
  await page.getByRole('button', { name: 'New user? Create account' }).click()
  await page.getByLabel('Email address').fill(`obi.e2e.${Date.now()}@example.com`)
  await page.getByLabel('Full name').fill('Jane E2E')
  await page.getByRole('textbox', { name: /Create password/ }).fill('StrongPass123')
  await page.getByRole('textbox', { name: /Confirm password/ }).fill('StrongPass123')
  await page.getByRole('button', { name: 'Create account' }).click()

  // Dashboard loads after registration
  await expect(page.getByRole('heading', { name: 'Your Dashboard' })).toBeVisible({ timeout: 30000 })

  // ── Resume upload → company selection ────────────────────────────────
  await page.goto('/resume')
  await page.locator('input[type="file"]').setInputFiles({
    name: 'resume.txt',
    mimeType: 'text/plain',
    buffer: Buffer.from(RESUME_TXT),
  })
  await page.waitForURL('**/company', { timeout: 30000 })

  await expect(page.getByRole('heading', { name: 'Targeted Companies & Roles' })).toBeVisible()
  await page.getByRole('button', { name: 'Select All' }).click()
  await page.getByRole('button', { name: /Start Assessment/ }).click()
  await page.waitForURL('**/aptitude', { timeout: 30000 })

  // ── Aptitude round: skip every question ──────────────────────────────
  await skipProctoringAndWaitForRoom(page)
  const aptitudeTotal = await readTotalQuestions(page)
  expect(aptitudeTotal).toBeGreaterThan(0)

  for (let i = 1; i < aptitudeTotal; i++) {
    await page.getByRole('button', { name: 'Skip', exact: true }).click()
    await expect(page.locator('.topbar-block strong').first()).toHaveText(`${i + 1} / ${aptitudeTotal}`)
  }
  await page.getByRole('button', { name: 'Skip', exact: true }).click()
  await page.waitForURL('**/coding', { timeout: 30000 })

  // ── Coding round: run once, then save & advance ──────────────────────
  await skipProctoringAndWaitForRoom(page)
  const codingTotal = await readTotalQuestions(page)
  expect(codingTotal).toBeGreaterThan(0)

  for (let i = 1; i <= codingTotal; i++) {
    const runBtn = page.getByRole('button', { name: 'Run Code' })
    if (i === 1) {
      await runBtn.click()
      await expect(runBtn).toHaveText('Run Code', { timeout: 60000 })
    }
    if (i < codingTotal) {
      await page.getByRole('button', { name: 'Save & Next' }).click()
      await expect(page.locator('.topbar-block strong').first()).toHaveText(`${i + 1} / ${codingTotal}`)
    }
  }
  await page.getByRole('button', { name: 'Save & Next' }).click()
  await page.waitForURL('**/technical', { timeout: 30000 })

  // ── Technical round: the AI interviewer must MOUNT without crashing ──
  await expect(page.locator('.oiv-shell--onboarding')).toBeVisible({ timeout: 30000 })
  await expect(page.getByText('Something went wrong')).toHaveCount(0)

  // Walk the onboarding wizard: Meet Obi → Setup check → Ready
  await page.getByRole('button', { name: 'Continue' }).click()
  await page.getByRole('button', { name: 'Continue' }).click()
  await expect(page.getByRole('button', { name: 'Begin Interview' })).toBeVisible()
  await expect(page.getByText('Something went wrong')).toHaveCount(0)

  // ── Begin Interview: /ai-interview/start must NOT 401 (auth regression) ──
  await page.getByRole('button', { name: 'Begin Interview' }).click()
  await expect(
    page.locator('.oiv-connect-overlay, .oiv-error, .oiv-room-error')
  ).toBeVisible({ timeout: 15000 })
  await expect(page.getByText('Something went wrong')).toHaveCount(0)

  // ── Report renders from the session ──────────────────────────────────
  await page.goto('/report')
  await expect(page.getByRole('heading', { name: 'Candidate readiness summary' })).toBeVisible({ timeout: 30000 })
  await expect(page.getByRole('heading', { name: 'Something went wrong' })).toHaveCount(0)

  expect(pageErrors, `page errors:\n${pageErrors.map((e) => e.message).join('\n')}`).toEqual([])
  expect(cspErrors, `CSP violations:\n${cspErrors.join('\n')}`).toEqual([])
  expect(startFailures, `/ai-interview/start non-2xx:\n${startFailures.join('\n')}`).toEqual([])
})
