import type { Feature, FeatureCollection, Geometry } from 'geojson'
import {
  type GeoJSONSource,
  type MapMouseEvent,
  Map as MapLibreMap,
  NavigationControl,
  Popup,
  setWorkerUrl,
} from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
// Bundlers must point MapLibre at its worker explicitly (maplibre-gl v6).
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url'
import { useEffect, useRef, useState } from 'react'
import type { Areas, Current } from '../contract'
import { geoUrl } from '../lib/data'
import { colorFor, type Mode } from '../lib/scale'
import { tooltipLines } from '../lib/tooltip'

setWorkerUrl(workerUrl)

const BASEMAP = 'https://tiles.openfreemap.org/styles/positron'
// Zoom levels at which the map hands over from country → river basin → reservoir (B11).
const REGION_ZOOM = 4.5
const RESERVOIR_ZOOM = 6.5

interface Props {
  areas: Areas
  current: Current
  mode: Mode
}

type Geo = FeatureCollection<Geometry, Record<string, unknown>>

function colour(geo: Geo, current: Current, mode: Mode): Geo {
  return {
    ...geo,
    features: geo.features.map((f) => {
      const entry = current[String(f.id)]
      return { ...f, properties: { ...f.properties, fill: colorFor(entry, mode), covered: !!entry } }
    }),
  }
}

function reservoirPoints(areas: Areas): Geo {
  const features: Feature<Geometry, Record<string, unknown>>[] = areas
    .filter((a) => a.level === 'reservoir' && a.centroid)
    .map((a) => ({
      type: 'Feature',
      id: a.id,
      properties: { id: a.id, capacity: a.capacityHm3 },
      geometry: { type: 'Point', coordinates: a.centroid as [number, number] },
    }))
  return { type: 'FeatureCollection', features }
}

function popupNode(areaId: string, areas: Map<string, Areas[number]>, current: Current): HTMLElement | null {
  const area = areas.get(areaId)
  const entry = current[areaId]
  if (!area || !entry) return null
  const t = tooltipLines(area, entry)
  const root = document.createElement('div')
  root.className = 'tip'
  const title = document.createElement('strong')
  title.textContent = t.title
  const subtitle = document.createElement('div')
  subtitle.className = 'tip-sub'
  subtitle.textContent = t.subtitle
  root.append(title, subtitle)
  for (const line of t.lines) {
    const div = document.createElement('div')
    div.textContent = line
    root.append(div)
  }
  if (t.stale) {
    const stale = document.createElement('div')
    stale.className = 'stale'
    stale.textContent = 'Out of date'
    root.append(stale)
  }
  return root
}

/** Europe map: country → river basin → reservoir, coloured by % full or vs normal. */
export function MapView({ areas, current, mode }: Props) {
  const container = useRef<HTMLDivElement>(null)
  const mapRef = useRef<MapLibreMap | null>(null)
  const geo = useRef<{ countries: Geo; rbd: Geo } | null>(null)
  const latest = useRef({ areas, current })
  const [ready, setReady] = useState(false)
  useEffect(() => {
    latest.current = { areas, current }
  }, [areas, current])

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
    mapRef.current = map
    // Exposed for end-to-end tests, which drive and inspect the map directly.
    ;(window as unknown as { __map?: MapLibreMap }).__map = map
    map.addControl(new NavigationControl({ showCompass: false }), 'top-right')
    const popup = new Popup({ closeButton: false, closeOnClick: false, maxWidth: '260px' })

    map.on('load', async () => {
      const [countries, rbd] = (await Promise.all(
        ['countries.geojson', 'rbd.geojson'].map((f) => fetch(geoUrl(f)).then((r) => r.json())),
      )) as [Geo, Geo]
      geo.current = { countries, rbd }
      const empty: Geo = { type: 'FeatureCollection', features: [] }
      // Draw data beneath the basemap's labels so place names stay readable.
      const firstLabel = map.getStyle().layers.find((l) => l.type === 'symbol')?.id
      map.addSource('countries', { type: 'geojson', data: empty })
      map.addSource('rbd', { type: 'geojson', data: empty })
      map.addSource('reservoirs', { type: 'geojson', data: empty })
      map.addLayer(
        {
          id: 'country-fill',
          type: 'fill',
          source: 'countries',
          paint: {
            'fill-color': ['get', 'fill'],
            // Covered countries hand over to their river basins when zoomed in.
            // (MapLibre requires zoom at the top level, so the case sits inside each stop.)
            'fill-opacity': [
              'interpolate',
              ['linear'],
              ['zoom'],
              REGION_ZOOM - 0.3,
              ['case', ['get', 'covered'], 0.9, 0.55],
              REGION_ZOOM,
              ['case', ['get', 'covered'], 0, 0.55],
            ],
          },
        },
        firstLabel,
      )
      map.addLayer(
        {
          id: 'rbd-fill',
          type: 'fill',
          source: 'rbd',
          minzoom: REGION_ZOOM - 0.3,
          filter: ['get', 'covered'],
          paint: {
            'fill-color': ['get', 'fill'],
            // Fade the basins back once reservoir dots take over.
            'fill-opacity': [
              'interpolate',
              ['linear'],
              ['zoom'],
              REGION_ZOOM - 0.3,
              0,
              REGION_ZOOM,
              0.85,
              RESERVOIR_ZOOM,
              0.6,
              RESERVOIR_ZOOM + 1,
              0.25,
            ],
          },
        },
        firstLabel,
      )
      map.addLayer(
        {
          id: 'rbd-line',
          type: 'line',
          source: 'rbd',
          minzoom: REGION_ZOOM,
          filter: ['get', 'covered'],
          paint: { 'line-color': '#fcfcfb', 'line-width': 1.5 },
        },
        firstLabel,
      )
      map.addLayer(
        {
          id: 'country-line',
          type: 'line',
          source: 'countries',
          paint: { 'line-color': '#fcfcfb', 'line-width': 1 },
        },
        firstLabel,
      )
      map.addLayer({
        id: 'reservoir-dot',
        type: 'circle',
        source: 'reservoirs',
        minzoom: RESERVOIR_ZOOM,
        paint: {
          'circle-color': ['get', 'fill'],
          // Area ∝ capacity, so big reservoirs read as big.
          'circle-radius': ['interpolate', ['linear'], ['sqrt', ['get', 'capacity']], 0, 4, 10, 9, 60, 18],
          'circle-stroke-color': '#fcfcfb',
          'circle-stroke-width': 1.5,
        },
      })
      setReady(true)
    })

    // B12: hover (mouse) or tap (touch) shows the area's figures. The most
    // detailed visible tier wins: reservoir, then river basin, then country.
    const pick = (e: MapMouseEvent): string | undefined => {
      if (!map.getLayer('reservoir-dot')) return undefined
      const zoom = map.getZoom()
      const layers = [
        ...(zoom >= RESERVOIR_ZOOM ? ['reservoir-dot'] : []),
        ...(zoom >= REGION_ZOOM ? ['rbd-fill'] : []),
        'country-fill',
      ]
      const hits = map.queryRenderedFeatures(e.point, { layers })
      const best = layers
        .map((layer) => hits.find((h) => h.layer.id === layer))
        .find((h) => h && !(h.layer.id === 'country-fill' && zoom >= REGION_ZOOM && h.properties.covered))
      return best?.properties.id as string | undefined
    }
    const update = (e: MapMouseEvent) => {
      const id = pick(e)
      const node = id ? popupNode(id, new Map(latest.current.areas.map((a) => [a.id, a])), latest.current.current) : null
      if (!node) {
        popup.remove()
        map.getCanvas().style.cursor = ''
        return
      }
      popup.setLngLat(e.lngLat).setDOMContent(node).addTo(map)
      map.getCanvas().style.cursor = 'pointer'
    }
    map.on('mousemove', update)
    map.on('click', update)
    map.on('mouseout', () => popup.remove())

    return () => {
      popup.remove()
      map.remove()
      mapRef.current = null
    }
  }, [])

  useEffect(() => {
    const map = mapRef.current
    if (!ready || !map || !geo.current) return
    ;(map.getSource('countries') as GeoJSONSource).setData(colour(geo.current.countries, current, mode))
    ;(map.getSource('rbd') as GeoJSONSource).setData(colour(geo.current.rbd, current, mode))
    ;(map.getSource('reservoirs') as GeoJSONSource).setData(colour(reservoirPoints(areas), current, mode))
  }, [ready, areas, current, mode])

  return <div ref={container} className="map" role="region" aria-label="Map of reservoir storage in Europe" />
}
