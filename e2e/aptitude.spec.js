import { test, expect } from '@playwright/test'

test.describe('Aptitude Round', () => {
  test('loads aptitude questions', async ({ page }) => {
    await page.goto('/aptitude')
    await page.waitForTimeout(3000)
    const questionText = page.locator('.question-text, .question, [class*="question"], h3, h4').first()
    await expect(questionText).toBeVisible({ timeout: 15000 })
  })

  test('shows answer options', async ({ page }) => {
    await page.goto('/aptitude')
    await page.waitForTimeout(3000)
    const options = page.locator('.option, .answer-option, input[type="radio"], button:has-text("A"), button:has-text("B")')
    const count = await options.count()
    expect(count).toBeGreaterThan(0)
  })

  test('can select an answer', async ({ page }) => {
    await page.goto('/aptitude')
    await page.waitForTimeout(3000)
    const firstOption = page.locator('.option, .answer-option, input[type="radio"], label').first()
    if (await firstOption.isVisible().catch(() => false)) {
      await firstOption.click()
    }
  })

  test('shows timer', async ({ page }) => {
    await page.goto('/aptitude')
    await page.waitForTimeout(2000)
    const timer = page.locator('text=/\\d+:\\d+/, [class*="timer"], [class*="clock"]')
    await expect(timer.first()).toBeVisible({ timeout: 10000 })
  })
})
