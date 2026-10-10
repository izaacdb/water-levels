import type { FeatureCollection } from 'geojson'
import { Map as MapLibreMap, NavigationControl, setWorkerUrl } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
// Bundlers must point MapLibre at its worker explicitly (maplibre-gl v6).
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url'
import { useEffect, useRef } from 'react'
import type { Current } from '../contract'
import { geoUrl } from '../lib/data'
import { NOT_COVERED, pctColor } from '../lib/scale'

setWorkerUrl(workerUrl)

const BASEMAP = 'https://tiles.openfreemap.org/styles/positron'

interface Props {
  current: Current
}

/** Europe map: covered countries coloured by % full, everything else neutral (B9). */
export function MapView({ current }: Props) {
  const container = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!container.current) return
    const map = new MapLibreMap({
      container: container.current,
      style: BASEMAP,
      bounds: [
        [-24, 32],
        [42, 70],
      ],
      fitBoundsOptions: { padding: 16 },
      attributionControl: { compact: true },
    })
    map.addControl(new NavigationControl({ showCompass: false }), 'top-right')

    map.on('load', async () => {
      const geo = (await (await fetch(geoUrl('countries.geojson'))).json()) as FeatureCollection
      for (const f of geo.features) {
        const entry = current[String(f.id)]
        f.properties = { ...f.properties, fill: entry ? pctColor(entry.pct) : NOT_COVERED, covered: !!entry }
      }
      map.addSource('countries', { type: 'geojson', data: geo })
      // Draw data beneath the basemap's labels so place names stay readable.
      const firstLabel = map.getStyle().layers.find((l) => l.type === 'symbol')?.id
      map.addLayer({
        id: 'country-fill',
        type: 'fill',
        source: 'countries',
        paint: {
          'fill-color': ['get', 'fill'],
          'fill-opacity': ['case', ['get', 'covered'], 0.9, 0.55],
        },
      }, firstLabel)
      map.addLayer({
        id: 'country-line',
        type: 'line',
        source: 'countries',
        paint: { 'line-color': '#fcfcfb', 'line-width': 1 },
      }, firstLabel)
    })
    return () => map.remove()
  }, [current])

  return <div ref={container} className="map" role="region" aria-label="Map of reservoir storage in Europe" />
}
