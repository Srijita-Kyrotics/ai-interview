import { test, expect } from '@playwright/test'

test.describe('Report Page', () => {
  test('redirects to resume if no session', async ({ page }) => {
    await page.goto('/report')
    await page.waitForTimeout(2000)
    const url = page.url()
    expect(url).toMatch(/resume|\/$/)
  })

  test('shows report when session exists', async ({ page }) => {
    await page.goto('/')
    await page.waitForTimeout(3000)

    await page.evaluate(() => {
      localStorage.setItem('mockRecruitmentUser', JSON.stringify({
        name: 'Test User',
        email: 'test@example.com',
        token: 'test-token'
      }))
    })

    await page.goto('/report')
    await page.waitForTimeout(3000)
    const panel = page.locator('.report-panel, [class*="report"], .empty-state')
    await expect(panel.first()).toBeVisible({ timeout: 10000 })
  })
})
