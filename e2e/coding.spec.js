import { test, expect } from '@playwright/test'

test.describe('Coding Round', () => {
  test('loads coding challenge', async ({ page }) => {
    await page.goto('/coding')
    await page.waitForTimeout(3000)
    const title = page.locator('.question-title, h3, h4, [class*="title"]').first()
    await expect(title).toBeVisible({ timeout: 15000 })
  })

  test('shows code editor', async ({ page }) => {
    await page.goto('/coding')
    await page.waitForTimeout(3000)
    const editor = page.locator('.cm-editor, .code-editor, textarea, [class*="editor"], [class*="code"]')
    await expect(editor.first()).toBeVisible({ timeout: 15000 })
  })

  test('can type in editor', async ({ page }) => {
    await page.goto('/coding')
    await page.waitForTimeout(3000)
    const editor = page.locator('.cm-editor, .code-editor, textarea, [class*="editor"], [class*="code"]').first()
    if (await editor.isVisible().catch(() => false)) {
      await editor.click()
      await page.keyboard.type('function test() { return 1; }')
    }
  })

  test('shows language selector', async ({ page }) => {
    await page.goto('/coding')
    await page.waitForTimeout(3000)
    const langSelector = page.locator('select, [class*="language"], [class*="lang"]')
    await expect(langSelector.first()).toBeVisible({ timeout: 15000 })
  })
})
