import { expect, test } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'

test('secure entry renders without horizontal overflow', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByText('EMOTO').first()).toBeVisible()
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth)
  expect(overflow).toBe(false)
})

test('administrator can enter the workspace and use navigation', async ({ page }, testInfo) => {
  await page.goto('/')
  const authHeading = page.locator('.auth-card h2')
  await expect(authHeading).toBeVisible()
  if ((await authHeading.textContent())?.includes('Create the first administrator')) {
    await page.getByLabel('Full name').fill('E2E Administrator')
    await page.getByLabel('Bootstrap token').fill('e2e-bootstrap-token')
    await page.getByLabel('Email address').fill('e2e@emoto.example.com')
    await page.getByLabel('Password').fill('PlaywrightSecure123!')
    await page.getByRole('button', { name: 'Create secure administrator' }).click()
  } else {
    await page.getByLabel('Email address').fill('e2e@emoto.example.com')
    await page.getByLabel('Password').fill('PlaywrightSecure123!')
    await page.getByRole('button', { name: 'Sign in' }).click()
  }
  await expect(page.getByRole('heading', { name: 'BMW parts overview' })).toBeVisible()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light')
  await page.getByRole('button', { name: 'Switch to dark theme' }).click()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
  const screenshotDir = path.resolve('../docs/screenshots')
  fs.mkdirSync(screenshotDir, { recursive: true })
  await page.screenshot({ path: path.join(screenshotDir, `${testInfo.project.name}.png`), fullPage: true })
  const menuButton = page.getByRole('button', { name: 'Open menu' })
  if (await menuButton.isVisible()) await menuButton.click()
  await page.getByRole('link', { name: 'Parts catalog' }).click()
  await expect(page.getByRole('heading', { name: 'Parts catalog' })).toBeVisible()
  await expect(page.getByRole('button', { name: /New part/i })).toBeVisible()
})
