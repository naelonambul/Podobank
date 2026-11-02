import { expect, test } from '@playwright/test';
import { login } from './helpers.js';

test('a customer can log in again after a protected request expires the session', async ({
  page,
}) => {
  await login(page, 'customer', 'customer');
  await page.goto('/transactions?mode=deposit');
  await expect(page.getByLabel('금액 (원)')).toBeVisible();

  await page.context().clearCookies();
  await page.getByLabel('금액 (원)').fill('1000');
  await page.getByRole('button', { name: '입금하기' }).click();

  await expect(page).toHaveURL(/\/login\?next=/);
  await expect(page.getByRole('heading', { name: '다시 만나 반가워요' })).toBeVisible();
  await login(page, 'customer', 'customer');
});
