/* Generated from pipeline/schema/contract.schema.json by `npm run gen:contract`. Do not edit. */

/**
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "Areas".
 */
export type Areas = Area[]

export interface Contract {
Manifest?: Manifest
Areas?: Areas
Current?: Current
Series?: Series
}
/**
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "Manifest".
 */
export interface Manifest {
schemaVersion?: number
generatedAt: string
snapshotWeek: string
countries: CountryStatus[]
sources: SourceInfo[]
}
/**
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "CountryStatus".
 */
export interface CountryStatus {
code: string
name: string
status: ("active" | "stale" | "withdrawn")
note?: (string | null)
}
/**
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "SourceInfo".
 */
export interface SourceInfo {
id: string
country: string
name: string
url: string
cadence?: ("daily" | "weekly" | "monthly")
lastFetched?: (string | null)
lastPublished?: (string | null)
lastError?: (string | null)
}
/**
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "Area".
 */
export interface Area {
id: string
level: ("country" | "region" | "reservoir")
name: string
country: string
parentId?: (string | null)
capacityHm3: number
/**
 * @minItems 1
 */
sourceIds: [string, ...(string)[]]
totalOnly?: (boolean | null)
centroid?: ([number, number] | null)
}
/**
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "Current".
 */
export interface Current {
[k: string]: CurrentEntry
}
/**
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "CurrentEntry".
 */
export interface CurrentEntry {
pct: number
anomalyPts?: (number | null)
normalPct?: (number | null)
normalYears?: number
asOf: string
stale: boolean
nReporting: number
nTotal: number
flags?: string[]
}
/**
 * One area's weekly history over the 10-year window (B6), as parallel arrays.
 * 
 * Columnar keeps ~520 weeks x ~400 areas small; index i of every array is weeks[i].
 * 
 * This interface was referenced by `Contract`'s JSON-Schema
 * via the `definition` "Series".
 */
export interface Series {
areaId: string
weeks: string[]
pct: number[]
normal: (number | null)[]
p10: (number | null)[]
p90: (number | null)[]
n: number[]
}
