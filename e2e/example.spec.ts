import { test, expect } from '@playwright/test';

test('has title', async ({ page }) => {
  await page.goto('http://127.0.0.1:3000');

  // Expect a title "to contain" a substring.
  await expect(page).toHaveTitle(/Local Telemetry Dashboard/);
});

test('get started link', async ({ page }) => {
  await page.goto('http://127.0.0.1:3000');

  await expect(page.getByRole('heading', { name: 'Device state' })).toBeVisible();

  await expect(page.locator('article').first()).toBeVisible({ timeout: 15000 });
});
