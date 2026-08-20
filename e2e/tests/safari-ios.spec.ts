import { expect, test, type Page } from '../fixtures/test';

test.use({ mutationScope: 'training' });

const viewports = [
  { name: 'phone-320', width: 320, height: 700 },
  { name: 'phone-375', width: 375, height: 812 },
  { name: 'phone-390', width: 390, height: 844 },
  { name: 'phone-430', width: 430, height: 932 },
  { name: 'ipad-portrait', width: 768, height: 1024 },
  { name: 'ipad-landscape', width: 1024, height: 768 },
  { name: 'desktop-1280', width: 1280, height: 800 },
  { name: 'desktop-1440', width: 1440, height: 900 },
];

async function expectNoPageOverflow(page: Page) {
  const dimensions = await page.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
  }));
  expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.clientWidth + 1);
}

for (const viewport of viewports) {
  test(`WebKit shell and long names remain accessible at ${viewport.name}`, async ({
    page,
    athleteSession,
    athleteIds,
  }) => {
    await page.setViewportSize(viewport);
    await athleteSession(page.request, athleteIds.primary);
    await page.goto('/athlete/programme');

    await expect(page.locator('meta[name="viewport"]')).toHaveAttribute('content', /viewport-fit=cover/);
    await page.locator('h1, .programme-summary h2, .programme-week h2, .session-card strong').evaluateAll(elements => {
      const longName = 'International Competition Preparation Programme With An UninterruptedLongContextNameForSafari';
      elements.forEach(element => { element.textContent = longName; });
    });
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
    await expectNoPageOverflow(page);

    if (viewport.width < 760) {
      const shellSpacing = await page.locator('.athlete-shell').evaluate(element => ({
        paddingBottom: Number.parseFloat(getComputedStyle(element).paddingBottom),
        navHeight: document.querySelector('.athlete-mobile-nav')?.getBoundingClientRect().height ?? 0,
      }));
      expect(shellSpacing.paddingBottom).toBeGreaterThan(shellSpacing.navHeight);
      await expect(page.getByRole('navigation', { name: 'Athlete navigation' }).last()).toBeVisible();
    }
  });
}

test('WebKit More fallback and coach sticky/table accessibility work without :has()', async ({
  page,
  athleteSession,
  athleteIds,
  authenticatedState,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await athleteSession(page.request, athleteIds.primary);
  await page.goto('/athlete/meal-plan');
  const more = page.locator('[data-athlete-more]');
  await expect(more).toHaveClass(/is-active/);
  await expect(more.locator('summary')).toHaveAttribute('aria-current', 'page');

  await page.context().clearCookies();
  await authenticatedState(page);
  await page.goto('/athletes');
  const tableRegion = page.getByRole('region', { name: 'Athlete roster' });
  await expect(tableRegion).toHaveAttribute('tabindex', '0');
  const offsets = await page.evaluate(() => ({
    scrollPaddingTop: Number.parseFloat(getComputedStyle(document.documentElement).scrollPaddingTop),
    headerHeight: document.querySelector('.coach-topbar')?.getBoundingClientRect().height ?? 0,
    contextHeight: document.querySelector('.coach-context')?.getBoundingClientRect().height ?? 0,
  }));
  expect(offsets.scrollPaddingTop).toBeGreaterThan(offsets.headerHeight + offsets.contextHeight);
});

test.describe('reduced motion', () => {
  test.use({ reducedMotion: 'reduce' });

  test('WebKit athlete and coach roots disable smooth scrolling and transitions', async ({
    page,
    athleteSession,
    athleteIds,
    authenticatedState,
  }) => {
    await athleteSession(page.request, athleteIds.primary);
    await page.goto('/athlete/dashboard');
    await expect(page.locator('html')).toHaveCSS('scroll-behavior', 'auto');
    const athleteDuration = await page.locator('.athlete-mobile-nav').evaluate(element => getComputedStyle(element).transitionDuration);
    const athleteDurationMs = athleteDuration.endsWith('ms') ? Number.parseFloat(athleteDuration) : Number.parseFloat(athleteDuration) * 1000;
    expect(athleteDurationMs).toBeLessThanOrEqual(.01);

    await page.context().clearCookies();
    await authenticatedState(page);
    await page.goto('/coach');
    await expect(page.locator('html')).toHaveCSS('scroll-behavior', 'auto');
    const coachDuration = await page.locator('.coach-link-button').first().evaluate(element => getComputedStyle(element).transitionDuration);
    const coachDurationMs = coachDuration.endsWith('ms') ? Number.parseFloat(coachDuration) : Number.parseFloat(coachDuration) * 1000;
    expect(coachDurationMs).toBeLessThanOrEqual(.01);
  });
});
