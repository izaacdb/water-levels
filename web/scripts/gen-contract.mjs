// Generates src/contract.ts from the pipeline's JSON Schema (the contract's source of truth).
import { readFile, writeFile } from 'node:fs/promises'
import { compile } from 'json-schema-to-typescript'

const schemaUrl = new URL('../../pipeline/schema/contract.schema.json', import.meta.url)
const outUrl = new URL('../src/contract.ts', import.meta.url)

const schema = JSON.parse(await readFile(schemaUrl, 'utf8'))
const ts = await compile(schema, 'Contract', {
  bannerComment: '/* Generated from pipeline/schema/contract.schema.json by `npm run gen:contract`. Do not edit. */',
  additionalProperties: false,
  unreachableDefinitions: true,
  format: false,
})
await writeFile(outUrl, ts)
console.log('wrote src/contract.ts')
