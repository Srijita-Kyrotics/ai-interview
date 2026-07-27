import { test, expect } from '@playwright/test'

test.describe('Full Application Flow', () => {
  test('loads home page', async ({ page }) => {
    await page.goto('/')
    await page.waitForTimeout(3000)
    const body = page.locator('body')
    await expect(body).toBeVisible()
    const title = await page.title()
    expect(title).toBeTruthy()
  })

  test('navigation works', async ({ page }) => {
    await page.goto('/')
    await page.waitForTimeout(2000)

    const links = page.locator('a[href], button[onclick], [class*="nav"] a')
    const count = await links.count()
    expect(count).toBeGreaterThan(0)
  })

  test('responsive layout loads', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 })
    await page.goto('/')
    await page.waitForTimeout(2000)
    const body = page.locator('body')
    await expect(body).toBeVisible()
  })

  test('API health check', async ({ request }) => {
    const response = await request.get('http://localhost:8000/health')
    expect(response.ok()).toBeTruthy()
  })

  test('questions API returns data', async ({ request }) => {
    const response = await request.get('http://localhost:8000/questions/technical')
    expect(response.ok()).toBeTruthy()
    const data = await response.json()
    expect(Array.isArray(data)).toBeTruthy()
    expect(data.length).toBeGreaterThan(0)
  })

  test('HR questions API returns data', async ({ request }) => {
    const response = await request.get('http://localhost:8000/questions/hr')
    expect(response.ok()).toBeTruthy()
    const data = await response.json()
    expect(Array.isArray(data)).toBeTruthy()
    expect(data.length).toBeGreaterThan(0)
  })

  test('coding questions API returns data', async ({ request }) => {
    const response = await request.get('http://localhost:8000/questions/coding')
    expect(response.ok()).toBeTruthy()
    const data = await response.json()
    expect(Array.isArray(data)).toBeTruthy()
    expect(data.length).toBeGreaterThan(0)
  })

  test('companies API returns data', async ({ request }) => {
    const response = await request.get('http://localhost:8000/companies')
    expect(response.ok()).toBeTruthy()
    const data = await response.json()
    expect(typeof data).toBe('object')
  })
})
