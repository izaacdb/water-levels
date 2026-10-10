import { describe, expect, it } from 'vitest'
import { isoWeekStart, isoWeekParts } from './week'

describe('isoWeekStart', () => {
  it('returns the Monday of an ISO week (UTC)', () => {
    expect(isoWeekStart('2026-W41').toISOString().slice(0, 10)).toBe('2026-10-05')
    expect(isoWeekStart('2020-W53').toISOString().slice(0, 10)).toBe('2020-12-28')
    expect(isoWeekStart('2021-W01').toISOString().slice(0, 10)).toBe('2021-01-04')
  })
})

describe('isoWeekParts', () => {
  it('splits a label', () => {
    expect(isoWeekParts('2026-W09')).toEqual({ year: 2026, week: 9 })
  })
})
