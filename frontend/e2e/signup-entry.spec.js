import { expect, test } from '@playwright/test';

test('landing start opens a distinct Kakao signup entry', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: '포도뱅크 시작하기' }).click();

  await expect(page).toHaveURL(/\/signup$/);
  await expect(page.getByRole('heading', { name: '포도뱅크 회원가입' })).toBeVisible();
  await expect(page.getByRole('button', { name: '카카오로 가입하기' })).toBeVisible();
});

test('existing-account login stays separate and links to signup', async ({ page }) => {
  await page.goto('/login');

  await expect(page.getByLabel('휴대전화번호')).toBeVisible();
  await expect(page.getByRole('link', { name: '카카오로 가입하기' })).toHaveAttribute(
    'href',
    '/signup',
  );
});

test('a first-time Kakao callback opens the signup profile form', async ({ page }) => {
  await page.route('**/auth/kakao/login', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'registration_required' }),
    }),
  );
  await page.goto('/auth/kakao/callback?code=demo-code&state=demo-state');

  await expect(page).toHaveURL(/\/signup\/profile$/);
  await expect(page.getByRole('heading', { name: '포도뱅크 시작하기' })).toBeVisible();
});
