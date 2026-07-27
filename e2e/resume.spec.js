import { test, expect } from '@playwright/test'

test.describe('Resume Upload', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    const emailInput = page.locator('input[type="email"], input[placeholder*="email" i], input[name="email"]').first()
    if (await emailInput.isVisible().catch(() => false)) {
      await emailInput.fill('e2etest@example.com')
      await page.locator('input[type="password"]').first().fill('TestPass123!')
      await page.locator('button[type="submit"], button:has-text("Log in"), button:has-text("Sign in")').first().click()
      await page.waitForTimeout(2000)
    }
  })

  test('shows resume upload page', async ({ page }) => {
    await page.goto('/resume')
    await expect(page.locator('text=/upload|resume|paste/i').first()).toBeVisible({ timeout: 10000 })
  })

  test('accepts resume text input', async ({ page }) => {
    await page.goto('/resume')
    const textarea = page.locator('textarea').first()
    if (await textarea.isVisible().catch(() => false)) {
      await textarea.fill('John Doe\nSoftware Engineer\nSkills: Python, JavaScript, React')
      const nextBtn = page.locator('button:has-text("Next"), button:has-text("Continue"), button[type="submit"]').first()
      if (await nextBtn.isVisible().catch(() => false)) {
        await nextBtn.click()
        await expect(page).not.toHaveURL('/resume', { timeout: 10000 })
      }
    }
  })
})
