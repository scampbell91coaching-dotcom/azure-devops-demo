import { test, expect } from '../fixtures/test';

async function expectNoHorizontalOverflow(page: import('@playwright/test').Page) {
  const overflow = await page.locator('html').evaluate((root) => {
    const viewportWidth = root.clientWidth;
    const offenders = Array.from(document.querySelectorAll<HTMLElement>('body *'))
      .filter((element) => {
        const style = getComputedStyle(element);
        if (style.display === 'none' || style.visibility === 'hidden') return false;
        const rect = element.getBoundingClientRect();
        return rect.left < -0.5 || rect.right > viewportWidth + 0.5;
      })
      .map((element) => {
        const rect = element.getBoundingClientRect();
        return `${element.tagName.toLowerCase()}.${Array.from(element.classList).join('.')} (${rect.left.toFixed(1)}..${rect.right.toFixed(1)})`;
      });

    return {
      fits: root.scrollWidth <= viewportWidth,
      rootWidth: `${root.scrollWidth}/${viewportWidth}`,
      offenders,
    };
  });

  expect(
    overflow.fits,
    `Horizontal overflow ${overflow.rootWidth}; outside viewport: ${overflow.offenders.join(', ') || 'none detected'}`,
  ).toBe(true);
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
  await expect(page.getByRole('link', { name: 'Meet Prep: Meet Day' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Sign out' })).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(menu).toHaveAttribute('aria-expanded', 'false');
  await expect(menu).toBeFocused();

  for (const width of [320, 390, 430]) {
    await page.setViewportSize({ width, height: 800 });
    await expectNoHorizontalOverflow(page);
  }
});

test('athlete core workflow fits a 320px phone viewport', async ({ page, athleteSession, athleteIds }) => {
  await page.setViewportSize({ width: 320, height: 700 });
  await athleteSession(page.request, athleteIds.primary);

  await page.goto('/athlete/dashboard');
  await expect(page.getByRole('heading', { level: 1, name: /Welcome back, Alex/i })).toBeVisible();
  const mobileNav = page.getByRole('navigation', { name: 'Athlete navigation' }).last();
  await expect(mobileNav).toBeVisible();
  await expect(mobileNav.getByRole('link', { name: /Home/ })).toHaveAttribute('aria-current', 'page');
  await expect(page.getByRole('link', { name: 'View session' })).toBeVisible();
  await expect(page.locator('html')).toHaveJSProperty('scrollWidth', 320);

  await mobileNav.getByRole('link', { name: /Programme/ }).click();
  await expect(page).toHaveURL('/athlete/programme');
  await expect(page.getByRole('heading', { level: 1, name: 'Your programme' })).toBeVisible();
  await page.getByRole('link', { name: /Squat day/ }).click();
  const squatHeading = page.getByRole('heading', {
    level: 2,
    name: 'Competition Squat',
  });
  await expect(squatHeading).toBeVisible();

  const squatCard = squatHeading.locator(
    'xpath=ancestor::*[self::article or contains(@class, "exercise") or contains(@class, "session")][1]',
  );

  await expect(squatCard).toContainText('3 × 5');
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
