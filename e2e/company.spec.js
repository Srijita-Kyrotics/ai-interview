import { test, expect } from '@playwright/test'

test.describe('Company Selection', () => {
  test('shows company selection page', async ({ page }) => {
    await page.goto('/company')
    await expect(page.locator('text=/company|select|choose/i').first()).toBeVisible({ timeout: 10000 })
  })

  test('displays company cards', async ({ page }) => {
    await page.goto('/company')
    await page.waitForTimeout(2000)
    const cards = page.locator('.company-card, .card, [class*="company"]')
    const count = await cards.count()
    expect(count).toBeGreaterThan(0)
  })
})
