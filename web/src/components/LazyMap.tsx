import { lazy } from 'react'

// MapLibre is most of the bundle; load it after the panel so the figures appear first.
export const MapView = lazy(() => import('./MapView').then((m) => ({ default: m.MapView })))
