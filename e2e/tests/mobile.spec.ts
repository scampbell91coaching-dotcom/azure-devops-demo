import { test, expect } from '../fixtures/test';

async function expectNoHorizontalOverflow(page: import('@playwright/test').Page) {
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= document.documentElement.clientWidth,
    ),
  ).toBeTruthy();
}

test('public and coach pages render and navigation toggles at a mobile viewport', async ({ page, authenticatedState }) => {
  await page.goto('/guides/shoulder-pain');
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  await authenticatedState(page);
  await page.goto('/athletes');
  await expect(page.getByRole('heading', { level: 1, name: 'Athletes', exact: true })).toBeVisible();
  await expect(page.locator('body')).not.toHaveCSS('overflow-x', 'scroll');
  const menu = page.getByRole('button', { name: 'Menu' });
  await menu.click();
  await expect(menu).toHaveAttribute('aria-expanded', 'true');
  await expect(page.locator('[data-coach-navigation]')).toHaveClass(/is-open/);
  await menu.click();
  await expect(menu).toHaveAttribute('aria-expanded', 'false');
});

test('athlete core workflow fits a 320px phone viewport', async ({ page, athleteSession, athleteIds }) => {
  await page.setViewportSize({ width: 320, height: 700 });
  await athleteSession(page.request, athleteIds.primary);

  await page.goto('/athlete/dashboard');
  await expect(page.getByRole('heading', { level: 1, name: /Alex’s training/i })).toBeVisible();
  const mobileNav = page.getByRole('navigation', { name: 'Athlete navigation' }).last();
  await expect(mobileNav).toBeVisible();
  await expect(mobileNav.getByRole('link', { name: /Today/ })).toHaveAttribute('aria-current', 'page');
  await expect(page.getByRole('link', { name: 'View session' })).toBeVisible();
  await expect(page.locator('html')).toHaveJSProperty('scrollWidth', 320);

  await mobileNav.getByRole('link', { name: /Programme/ }).click();
  await expect(page).toHaveURL('/athlete/programme');
  await expect(page.getByRole('heading', { level: 1, name: 'Your programme' })).toBeVisible();
  await page.getByRole('link', { name: /Squat day/ }).click();
  const squatHeading = page
    .getByRole('listitem')
    .filter({ hasText: 'Top Set' })
    .getByRole('heading', {
      level: 2,
      name: 'Competition Squat',
    });
  await expect(squatHeading).toBeVisible();

  const squatCard = squatHeading.locator(
    'xpath=ancestor::*[self::article or contains(@class, "exercise") or contains(@class, "session")][1]',
  );

  await expect(squatCard).toContainText(/3\s*[x×]\s*5/i);
  await expect(squatCard).toContainText(/(?:RPE|@)\s*7(?:\.0)?/i);
  await expect(page.locator('html')).toHaveJSProperty('scrollWidth', 320);
});

test('athlete check-in controls remain usable at 430px', async ({ page, athleteSession, athleteIds }) => {
  await page.setViewportSize({ width: 430, height: 800 });
  await athleteSession(page.request, athleteIds.primary);
  await page.goto(`/athletes/${athleteIds.primary}/check-ins/new`);
  await expect(page.getByRole('heading', { level: 1, name: 'How has your week been?' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Send check-in' })).toBeVisible();
  await expect(page.locator('input[name="recovery"]')).toHaveCSS('min-height', '48px');
  await expect(page.locator('html')).toHaveJSProperty('scrollWidth', 430);
});

for (const width of [320, 390, 430]) {
  test(`core athlete surfaces remain readable at ${width}px`, async ({ page, athleteSession, athleteIds }) => {
    await page.setViewportSize({ width, height: 844 });
    await athleteSession(page.request, athleteIds.primary);

    for (const route of ['/athlete/dashboard', '/athlete/programme', '/athlete/programme/sessions/502']) {
      await page.goto(route);
      await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
      await expect(page.getByRole('navigation', { name: 'Athlete navigation' }).last()).toBeVisible();
      await expectNoHorizontalOverflow(page);
    }

    const firstSet = page.locator('[data-set-row]').first();
    await expect(firstSet.getByLabel('Complete')).toBeVisible();
    await expect(firstSet.locator('input[name$="-load"]')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Finish session' })).toBeVisible();
  });

  test(`coach action surfaces remain usable at ${width}px`, async ({ page, authenticatedState }) => {
    await page.setViewportSize({ width, height: 844 });
    await authenticatedState(page);

    for (const route of ['/coach', '/check-ins', '/nutrition', '/applications', '/meet-day']) {
      await page.goto(route);
      await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
      await expectNoHorizontalOverflow(page);
    }

    const menu = page.getByRole('button', { name: 'Menu' });
    await menu.click();
    await expect(page.getByRole('link', { name: 'Nutrition', exact: true })).toBeVisible();
    await expect(page.getByRole('link', { name: /Meet Prep: Meet Day/ })).toBeVisible();
    await expect(page.locator('.coach-navigation__utilities').getByRole('link', { name: 'Platform' })).toBeVisible();
    await expect(page.locator('.coach-navigation__utilities').getByRole('button', { name: 'Sign out' })).toBeVisible();
    await expectNoHorizontalOverflow(page);
  });

  test(`coach programming hierarchy remains usable at ${width}px`, async ({ page, authenticatedState }) => {
    await page.setViewportSize({ width, height: 844 });
    await authenticatedState(page);
    await page.goto('/programming');
    await page.getByTestId('programming-athlete').filter({ hasText: 'Alex Rivera' }).click();
    await expect(
      page.getByRole('heading', { level: 1, name: 'Alex Rivera' })
    ).toBeVisible();
    await page
      .locator('a[href="/programming/blocks/301"]')
      .filter({ hasText: 'Open block' })
      .click();
    await expect(page.getByRole('navigation', { name: 'Programme hierarchy' })).toBeVisible();
    const week = page.getByTestId('programming-week').filter({ hasText: 'Foundation week' });
    await expect(week.getByLabel('Week 1 taxonomy-backed lift exposures')).toContainText('Squat 2');
    await expect(week.getByLabel('Week 1 taxonomy-backed lift exposures')).toContainText('Bench 1');
    await expect(week.getByLabel('Week 1 taxonomy-backed lift exposures')).toContainText('Deadlift 1');
    await expectNoHorizontalOverflow(page);
    await week.getByRole('link').click();
    await expect(page.getByLabel('Taxonomy-backed competition lift exposures')).toBeVisible();
    await expectNoHorizontalOverflow(page);
    const session = page.getByTestId('programming-session').filter({ hasText: 'Squat day' });
    await session.getByRole('link', { name: 'Open session' }).click();
    await expect(page.getByTestId('lift-slot').filter({ hasText: 'Squat exposure' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Edit lift slots' })).toBeVisible();
    await expectNoHorizontalOverflow(page);
  });
}
