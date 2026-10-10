// Performance budget: the JavaScript needed for first render (entry chunk) stays small.
// MapLibre and ECharts load lazily and are excluded on purpose.
import { readFile } from 'node:fs/promises'
import { gzipSync } from 'node:zlib'

const BUDGET_KB = 300
const html = await readFile(new URL('../dist/index.html', import.meta.url), 'utf8')
const entries = [...html.matchAll(/<script[^>]+src="([^"]+\.js)"/g)].map((m) => m[1])
let total = 0
for (const src of entries) {
  const file = new URL(`../dist/${src.replace(/^.*?assets\//, 'assets/')}`, import.meta.url)
  total += gzipSync(await readFile(file)).length
}
const kb = Math.round(total / 1024)
console.log(`initial JS: ${kb} KB gzip (budget ${BUDGET_KB} KB)`)
if (kb > BUDGET_KB) process.exit(1)
