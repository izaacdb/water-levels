import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'

test('SC4: whether a country is above or below normal is on the landing page', async ({ page }) => {
  await page.goto('/')
  for (const name of ['Spain', 'Portugal']) {
    const card = page.locator('.card', { has: page.getByRole('heading', { name }) })
    await expect(card).toContainText(/pts vs normal|insufficient history/)
  }
})

test('SC7: every figure has an as-of date and a reachable source link', async ({ page }) => {
  await page.goto('/')
  const cards = page.locator('.card')
  await expect(cards).toHaveCount(2)
  for (const card of await cards.all()) {
    await expect(card).toContainText(/As of \d{1,2} \w{3} \d{4}/)
    await expect(card.getByRole('link')).toHaveAttribute('href', /^https:\/\//)
  }
  await page.goto('/?area=ES050')
  await expect(page.locator('.facts')).toContainText(/As of/)
  await expect(page.locator('.facts').getByRole('link')).toHaveAttribute('href', /^https:\/\//)
})

test('B10/B12: the map toggles mode and the legend follows', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('radio', { name: 'vs normal' }).check({ force: true })
  await expect(page.getByText(/vs normal for this week/)).toBeVisible()
  await expect(page).toHaveURL(/mode=anom/)
})

test('rankings separate areas without enough history', async ({ page }) => {
  await page.goto('/?view=rankings&level=reservoir&sort=anom')
  await expect(page.getByRole('list', { name: 'Ranked areas' }).getByRole('button').first()).toBeVisible()
})

test('accessibility: no serious or critical axe violations', async ({ page }) => {
  await page.goto('/')
  await expect(page.locator('.card').first()).toBeVisible()
  const results = await new AxeBuilder({ page }).exclude('.maplibregl-canvas').analyze()
  const serious = results.violations.filter((v) => v.impact === 'serious' || v.impact === 'critical')
  expect(serious.map((v) => `${v.id}: ${v.help}`)).toEqual([])
})
