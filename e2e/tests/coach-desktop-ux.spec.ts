import { expect, test, type Locator, type Page } from '../fixtures/test';

const desktopViewport = { width: 1440, height: 900 };

async function expectNoPageOverflow(page: Page) {
  const dimensions = await page.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
  }));

  expect(
    dimensions.scrollWidth,
    `page width ${dimensions.scrollWidth}px exceeds the ${dimensions.clientWidth}px desktop viewport`,
  ).toBeLessThanOrEqual(dimensions.clientWidth + 1);
}

async function expectActionAvailable(page: Page, action: Locator) {
  await expect(action).toBeVisible();
  const box = await action.boundingBox();
  expect(box, 'primary action should have a rendered bounding box').not.toBeNull();
  expect(box!.x, 'primary action should not begin outside the viewport').toBeGreaterThanOrEqual(0);
  expect(
    box!.x + box!.width,
    'primary action should not extend beyond the viewport',
  ).toBeLessThanOrEqual(desktopViewport.width + 1);
}

async function expectCoachNavigation(page: Page) {
  const navigation = page.locator('[data-coach-navigation]');
  await expect(navigation).toBeVisible();
  await expect(navigation.getByRole('link', { name: 'Dashboard', exact: true })).toHaveAttribute(
    'href',
    '/coach',
  );
  await expect(navigation.getByRole('link', { name: 'Athletes', exact: true })).toHaveAttribute(
    'href',
    '/athletes',
  );
  await expect(navigation.getByRole('link', { name: 'Programming', exact: true })).toHaveAttribute(
    'href',
    '/programming',
  );
  await expect(navigation.getByRole('link', { name: 'Nutrition', exact: true })).toHaveAttribute(
    'href',
    '/nutrition',
  );
}

test.describe('coach desktop design-system guardrails', () => {
  test.beforeEach(async ({ page, authenticatedState }) => {
    await page.setViewportSize(desktopViewport);
    await authenticatedState(page);
  });

  test('coach home and athlete profile preserve navigation and primary actions', async ({ page }) => {
    await page.goto('/coach');
    await expect(page.getByRole('heading', { level: 1, name: 'Daily review' })).toBeVisible();
    await expect(page.getByText('Coach workspace', { exact: true })).toHaveCount(0);
    await expect(page.locator('.coach-panel').first()).toHaveCSS('border-radius', '0px');
    await expect(page.locator('.coach-panel').first()).toHaveCSS('background-color', 'rgba(0, 0, 0, 0)');
    await expectActionAvailable(
      page,
      page.getByRole('link', { name: 'View programme' }).first(),
    );
    await expectCoachNavigation(page);
    await expectNoPageOverflow(page);

    await page.goto('/athletes/101');
    await expect(page.getByRole('heading', { level: 1, name: 'Alex Rivera' })).toBeVisible();
    await expectActionAvailable(page, page.getByRole('link', { name: 'View programme' }));
    await expect(page.locator('#client-services')).toBeVisible();
    await expectCoachNavigation(page);
    await expectNoPageOverflow(page);
  });

  test('coach shell and roster retain keyboard and validation affordances', async ({ page }) => {
    await page.goto('/athletes');

    await page.keyboard.press('Tab');
    const skipLink = page.getByRole('link', { name: 'Skip to content' });
    await expect(skipLink).toBeFocused();
    await skipLink.press('Enter');
    await expect(page.locator('#coach-main')).toBeFocused();

    await page.locator('input[name="first_name"]').fill('Duplicate');
    await page.locator('input[name="last_name"]').fill('Athlete');
    await page.locator('input[name="email"]').fill('alex.e2e@example.test');
    await page.getByRole('button', { name: 'Create athlete' }).click();

    const email = page.locator('input[name="email"]');
    await expect(email).toHaveAttribute('aria-invalid', 'true');
    await expect(email).toHaveAttribute('aria-describedby', 'email-error');
    await expect(page.locator('#email-error')).toHaveAttribute('role', 'alert');
    await expectNoPageOverflow(page);
  });

  test('compact coach navigation and flat panels fit a phone viewport', async ({ page }) => {
    await page.setViewportSize({ width: 360, height: 740 });
    await page.goto('/coach');

    const menu = page.getByRole('button', { name: 'Menu' });
    await expect(menu).toHaveAttribute('aria-expanded', 'false');
    await menu.click();
    await expect(menu).toHaveAttribute('aria-expanded', 'true');
    await expect(page.locator('[data-coach-navigation]')).toBeVisible();

    const panelPadding = await page.locator('.coach-panel').first().evaluate(element => {
      const styles = getComputedStyle(element);
      return { left: styles.paddingLeft, right: styles.paddingRight };
    });
    expect(panelPadding).toEqual({ left: '0px', right: '0px' });
    await expectNoPageOverflow(page);
  });

  test('block builder and programming hierarchy remain usable without overflow', async ({ page }) => {
    await page.goto('/programming/factory?athlete_id=101');
    await expect(page.getByRole('heading', { level: 1, name: 'Block Factory' })).toBeVisible();
    await expectActionAvailable(page, page.getByRole('button', { name: 'Preview' }));
    await expectCoachNavigation(page);
    await expectNoPageOverflow(page);

    await page.goto('/programming');
    const athlete = page.getByTestId('programming-athlete').filter({ hasText: 'Alex Rivera' });
    await expect(athlete).toBeVisible();
    await athlete.click();
    await expect(page.getByRole('heading', { level: 1, name: 'Alex Rivera' })).toBeVisible();
    await expectActionAvailable(page, page.getByRole('link', { name: /Open block/i }).first());
    await expectNoPageOverflow(page);

    await page.goto('/programming/blocks/301');
    await expect(page.getByRole('heading', { level: 1, name: 'Deterministic strength block' })).toBeVisible();
    await expect(page.getByRole('navigation', { name: 'Programme hierarchy' })).toBeVisible();
    await expectActionAvailable(page, page.getByRole('link', { name: /Foundation week/ }));
    await expectNoPageOverflow(page);

    await page.goto('/programming/weeks/401');
    await expect(page.getByRole('heading', { level: 1, name: 'Foundation week' })).toBeVisible();
    await expect(page.getByTestId('programming-session').first()).toBeVisible();
    await expect(page.getByTestId('lift-slot').first()).toBeVisible();
    await expectActionAvailable(page, page.getByRole('link', { name: 'Open session' }).first());
    await expectNoPageOverflow(page);

    await page.goto('/programming/sessions/501');
    await expect(page.getByRole('navigation', { name: 'Programme hierarchy' })).toBeVisible();
    await expect(page.getByTestId('warmup-editor')).toBeVisible();
    await expectActionAvailable(page, page.getByRole('button', { name: 'Use template' }));
    await expectNoPageOverflow(page);
  });

  test('nutrition, meal plans and performance dashboard retain desktop controls', async ({ page }) => {
    await page.goto('/nutrition');
    await expect(page.getByRole('heading', { level: 1, name: 'Nutrition' })).toBeVisible();
    await expectCoachNavigation(page);
    await expectNoPageOverflow(page);

    await page.goto('/coach/meal-plans');
    await expectActionAvailable(page, page.getByRole('button', { name: 'Create meal plan' }));
    await expectCoachNavigation(page);
    await expectNoPageOverflow(page);

    await page.goto('/athletes/404');
    await expect(page.getByRole('heading', { level: 1, name: 'Morgan Performance' })).toBeVisible();
    const dashboard = page.locator('#performance-dashboard');
    await expect(dashboard).toBeVisible();
    await expectActionAvailable(page, dashboard.getByLabel('Training block'));
    await expectCoachNavigation(page);
    await expectNoPageOverflow(page);
  });
});
