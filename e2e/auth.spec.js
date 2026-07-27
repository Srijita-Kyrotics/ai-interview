import { test, expect } from '@playwright/test'

const TEST_USER = {
  name: 'E2E Test Candidate',
  email: `e2etest_${Date.now()}@example.com`,
  password: 'TestPass123!',
}

test.describe('Authentication', () => {
  test('shows login page by default', async ({ page }) => {
    await page.goto('/')
    await expect(page.locator('input[type="email"], input[placeholder*="email"], input[name="email"]')).toBeVisible({ timeout: 15000 })
  })

  test('can register a new user', async ({ page }) => {
    await page.goto('/')

    const nameInput = page.locator('input[placeholder*="name" i], input[name="name"]').first()
    const emailInput = page.locator('input[type="email"], input[placeholder*="email" i], input[name="email"]').first()
    const passwordInput = page.locator('input[type="password"]').first()

    if (await nameInput.isVisible().catch(() => false)) {
      await nameInput.fill(TEST_USER.name)
    }
    await emailInput.fill(TEST_USER.email)
    await passwordInput.fill(TEST_USER.password)

    const submitBtn = page.locator('button[type="submit"], button:has-text("Sign Up"), button:has-text("Register"), button:has-text("Log in")').first()
    await submitBtn.click()

    await expect(page).not.toHaveURL('/', { timeout: 10000 })
  })

  test('can login with existing credentials', async ({ page }) => {
    await page.goto('/')

    const emailInput = page.locator('input[type="email"], input[placeholder*="email" i], input[name="email"]').first()
    const passwordInput = page.locator('input[type="password"]').first()

    await emailInput.fill(TEST_USER.email)
    await passwordInput.fill(TEST_USER.password)

    const submitBtn = page.locator('button[type="submit"], button:has-text("Log in"), button:has-text("Sign in")').first()
    await submitBtn.click()

    await expect(page).not.toHaveURL('/', { timeout: 10000 })
  })
})
