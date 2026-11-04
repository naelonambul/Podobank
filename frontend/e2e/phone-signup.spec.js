import { expect, test } from '@playwright/test';

test('test_phone_signup_submits_formatted_phone_and_redirects_home', async ({ page }) => {
  await page.route('**/auth/phone/signup', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: '{"status":"authenticated"}',
    }),
  );
  await page.route('**/auth/me', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        id: 501,
        name: '새 고객',
        phone_number: '01012345678',
        role: 'customer',
      }),
    }),
  );
  await page.route('**/accounts/me/ledger*', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ items: [] }),
    }),
  );
  await page.route('**/accounts/me', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ account_number: '1000000000501', balance: 0 }),
    }),
  );

  await page.goto('/signup/phone');
  await page.getByLabel('이름').fill('새 고객');
  await page.getByLabel('휴대전화번호').fill('010-1234-5678');
  await page.getByLabel('비밀번호', { exact: true }).fill('customer-password');
  await page.getByLabel('비밀번호 확인').fill('customer-password');
  await page.getByLabel('나이').fill('30');
  await page.getByLabel('성별').selectOption('female');
  await page.getByLabel('혼인 상태').selectOption('single');
  await page.getByLabel('현재 직장이 있어요').check();

  const signupRequest = page.waitForRequest('**/auth/phone/signup');
  await page.getByRole('button', { name: '가입하고 계좌 만들기' }).click();
  const request = await signupRequest;

  expect(JSON.parse(request.postData() || '{}')).toEqual({
    name: '새 고객',
    phone_number: '010-1234-5678',
    password: 'customer-password',
    age: 30,
    gender: 'female',
    marital_status: 'single',
    is_employed: true,
  });
  await expect(page).toHaveURL(/\/home$/);
  await expect(page.getByRole('heading', { name: '새 고객님, 안녕하세요' })).toBeVisible();
});

test('test_phone_signup_rejects_invalid_number_format', async ({ page }) => {
  let signupRequests = 0;
  page.on('request', (request) => {
    if (request.url().includes('/auth/phone/signup')) signupRequests += 1;
  });

  await page.goto('/signup/phone');
  const phoneNumber = page.getByLabel('휴대전화번호');
  await phoneNumber.fill('010-1234-567');
  await page.getByLabel('이름').fill('새 고객');
  await page.getByLabel('비밀번호', { exact: true }).fill('customer-password');
  await page.getByLabel('비밀번호 확인').fill('customer-password');
  await page.getByLabel('나이').fill('30');

  await page.getByRole('button', { name: '가입하고 계좌 만들기' }).click();

  expect(await phoneNumber.evaluate((input) => input.checkValidity())).toBe(false);
  expect(signupRequests).toBe(0);
});
