import { useCallback, useEffect, useState } from 'react'
import { parseState, serializeState, type ViewState } from './urlState'

/** The URL is the single source of truth for what's on screen (B22). */
export function useUrlState(): [ViewState, (patch: Partial<ViewState>) => void] {
  const [state, setState] = useState(() => parseState(window.location.search))

  useEffect(() => {
    const onPop = () => setState(parseState(window.location.search))
    window.addEventListener('popstate', onPop)
    return () => window.removeEventListener('popstate', onPop)
  }, [])

  const update = useCallback((patch: Partial<ViewState>) => {
    setState((prev) => {
      const next = { ...prev, ...patch }
      const url = `${window.location.pathname}${serializeState(next)}${window.location.hash}`
      window.history.replaceState(null, '', url)
      return next
    })
  }, [])

  return [state, update]
}
