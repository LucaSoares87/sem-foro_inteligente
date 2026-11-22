import { useCallback, useEffect, useState } from 'react'
import { isKnownRoute, routeFromPath, workspaceUrl } from './navigation.js'

function readLocation() {
  return {
    route: routeFromPath(window.location.pathname),
    params: Object.fromEntries(new URLSearchParams(window.location.search))
  }
}

export default function useRoute() {
  const [location, setLocation] = useState(readLocation)

  useEffect(() => {
    if (!isKnownRoute(window.location.pathname)) {
      const canonical = routeFromPath(window.location.pathname)
      window.history.replaceState({}, '', canonical.path)
      setLocation(readLocation())
    }
    const onPopState = () => setLocation(readLocation())
    window.addEventListener('popstate', onPopState)
    return () => window.removeEventListener('popstate', onPopState)
  }, [])

  const navigate = useCallback((id, params = {}) => {
    const url = workspaceUrl(id, params)
    const current = window.location.pathname + window.location.search
    if (current !== url) window.history.pushState({}, '', url)
    setLocation(readLocation())
    window.scrollTo({ top: 0, behavior: 'auto' })
  }, [])

  return { ...location, navigate }
}
