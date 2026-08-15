import type { Page } from '@playwright/test';
import { test, expect } from '../fixtures/test';

async function expectNoHorizontalOverflow(page: Page) {
  expect(
    await page.evaluate(
      () => document.body.scrollWidth <= document.documentElement.clientWidth,
    ),
  ).toBeTruthy();
}

async function completeSession(page: Page) {
  const sets = page.locator('[data-set-row]');
  for (let index = 0; index < await sets.count(); index += 1) {
    const row = sets.nth(index);
    await row.getByLabel('Complete').check();
    await row.locator('input[name$="-load"]').fill('100');
    await row.locator('input[name$="-reps"]').fill('5');
    await row.locator('input[name$="-rpe"]').fill('7');
  }
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
  await expect(page.getByRole('heading', { level: 1, name: /Alex’s coaching/i })).toBeVisible();
  const mobileNav = page.getByRole('navigation', { name: 'Athlete navigation' }).last();
  await expect(mobileNav).toBeVisible();
  await expect(mobileNav.getByRole('link', { name: /Today/ })).toHaveAttribute('aria-current', 'page');
  await expect(page.getByRole('link', { name: 'View session' })).toBeVisible();
  await expect(page.getByText('Nothing is assigned to a calendar date.')).toBeVisible();
  await expect(page.locator('html')).toHaveJSProperty('scrollWidth', 320);

  await mobileNav.getByRole('link', { name: /Programme/ }).click();
  await expect(page).toHaveURL('/athlete/programme');
  await expect(page.getByRole('heading', { level: 1, name: 'Your programme' })).toBeVisible();
  await expect(page.getByText(/dates are not set; sessions follow programme order/i)).toBeVisible();
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
  test(`Mobile UX V2 critical actions complete at ${width}px`, async ({
    page,
    request,
    athleteSession,
    athleteIds,
    authenticatedState,
    resetE2EFixture,
  }) => {
    await page.setViewportSize({ width, height: 844 });

    await athleteSession(page.request, athleteIds.primary);
    await page.goto('/athlete/dashboard');
    const more = page.locator('[data-athlete-more]');
    const moreSummary = more.locator('summary');
    await moreSummary.focus();
    await page.keyboard.press('Enter');
    await expect(more).toHaveAttribute('open', '');
    await expect(more.getByRole('link', { name: 'Meal plan', exact: true })).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(more).not.toHaveAttribute('open', '');
    await expect(moreSummary).toBeFocused();
    await expectNoHorizontalOverflow(page);

    await resetE2EFixture(request, 'training');
    await athleteSession(page.request, athleteIds.primary);
    await page.goto('/athlete/programme/sessions/502');
    await completeSession(page);
    const finish = page.getByRole('button', { name: 'Finish session' });
    page.once('dialog', dialog => dialog.dismiss());
    await finish.click();
    await expect(finish).toBeFocused();
    page.once('dialog', dialog => dialog.accept());
    await finish.click();
    await expect(page.getByText('Session complete', { exact: true })).toBeVisible();
    await expectNoHorizontalOverflow(page);

    await resetE2EFixture(request, 'check-in');
    await athleteSession(page.request, athleteIds.primary);
    await page.goto(`/athletes/${athleteIds.primary}/check-ins/new`);
    await page.locator('input[name="fatigue"]').fill('6');
    await page.locator('input[name="recovery"]').fill('8');
    await page.locator('textarea[name="general_notes"]').fill(`Mobile ${width}px submission`);
    await page.getByRole('button', { name: 'Send check-in' }).click();
    await expect(page.getByText(`Mobile ${width}px submission`)).toBeVisible();
    await expectNoHorizontalOverflow(page);

    await page.context().clearCookies();
    await authenticatedState(page);
    await page.goto('/programming/factory');
    await page.getByLabel('Athlete').selectOption({ label: 'Sam Morgan' });
    await page.getByLabel('Selection mode').selectOption('none');
    await page.getByRole('button', { name: 'Preview' }).click();
    const evidence = page.locator('.factory-decision-details');
    const evidenceSummary = evidence.getByText('Review decision evidence and progression', { exact: true });
    await evidenceSummary.focus();
    await page.keyboard.press('Enter');
    await expect(evidence).toHaveAttribute('open', '');
    await expect(page.getByText(/Incomplete data:/)).toBeVisible();
    await expect(page.getByText(/0 assistance exercises/)).toHaveCount(4);
    await expectNoHorizontalOverflow(page);
  });

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

    await page.goto('/coach');
    await expect(page.locator('.coach-topbar__inner')).toHaveCSS('min-height', '60px');
    await expect(page.locator('.coach-dashboard__summary')).toHaveCSS('grid-template-columns', /.+ .+/);

    await page.goto('/nutrition');
    const nutritionRecord = page.locator('.nutrition-ledger tbody > tr:not(.nutrition-evidence-row)').first();
    await expect(nutritionRecord).toHaveCSS('display', 'grid');
    await expect(nutritionRecord.locator('[data-label="Actual intake"]')).toBeVisible();
    await expect(nutritionRecord.getByRole('link', { name: /Open record/ })).toBeVisible();
    await expectNoHorizontalOverflow(page);

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
    await week.getByRole('link', { name: /Foundation week/ }).click();
    await expect(page.getByLabel('Taxonomy-backed competition lift exposures')).toBeVisible();
    await expectNoHorizontalOverflow(page);
    const session = page.getByTestId('programming-session').filter({ hasText: 'Squat day' });
    await session.getByRole('link', { name: 'Open session' }).click();
    await expect(page.getByTestId('lift-slot').filter({ hasText: 'Competition Squat' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Edit lift slots' })).toBeVisible();
    await expectNoHorizontalOverflow(page);
  });
}
