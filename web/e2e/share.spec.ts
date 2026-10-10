import { expect, test } from '@playwright/test'

const compared = (page: import('@playwright/test').Page) =>
  page.getByRole('list', { name: 'Areas being compared' }).getByRole('listitem')

async function addArea(page: import('@playwright/test').Page, query: string, name: RegExp) {
  await page.getByLabel(/add an area/i).fill(query)
  await page.getByRole('list', { name: 'Matching areas' }).getByRole('button', { name }).click()
}

test('SC5: a three-area, two-country comparison survives a shared link', async ({ page, browser }) => {
  await page.goto('/')
  await page.getByRole('button', { name: 'Compare' }).click()
  await addArea(page, 'Alpha', /^Alpha/)
  await addArea(page, 'Douro', /^Douro/)
  await addArea(page, 'Portugal', /^Portugal/)
  await page.getByRole('radio', { name: 'vs normal' }).check({ force: true })

  await expect(compared(page)).toHaveCount(3)
  await expect(page.getByRole('img', { name: /Comparison of Alpha, Douro, Portugal/ })).toBeVisible()
  const link = page.url()
  expect(link).toContain('cmp=ES-alpha,PTRH3,PT')

  const fresh = await browser.newContext()
  const other = await fresh.newPage()
  await other.goto(link)
  await expect(compared(other)).toHaveText([/Alpha/, /Douro/, /Portugal/])
  await expect(other.getByRole('radio', { name: 'vs normal' })).toBeChecked()
  await expect(other.getByRole('img', { name: /Comparison of Alpha, Douro, Portugal/ })).toBeVisible()
  await fresh.close()
})

test('E7: unknown areas in a link are dropped with a notice', async ({ page }) => {
  await page.goto('/?view=compare&cmp=ES,ES-gone,PT')
  await expect(page.getByRole('status')).toContainText('ES-gone')
  await expect(compared(page)).toHaveText([/Spain/, /Portugal/])
  await expect(page).toHaveURL(/cmp=ES,PT$/)
})

test('B22: an area link opens its detail view', async ({ page }) => {
  await page.goto('/?area=ES050')
  await expect(page.getByRole('heading', { name: 'Guadalquivir' })).toBeVisible()
  await expect(page.getByRole('img', { name: /last 10 years/i })).toBeVisible()
})
