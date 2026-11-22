import { useCallback, useEffect, useState } from 'react'
import { isKnownRoute, routeById, routeFromPath } from './navigation.js'

export default function useRoute() {
  const [route, setRoute] = useState(() => routeFromPath(window.location.pathname))

  useEffect(() => {
    if (!isKnownRoute(window.location.pathname)) {
      const canonical = routeFromPath(window.location.pathname)
      window.history.replaceState({}, '', canonical.path)
      setRoute(canonical)
    }
    const onPopState = () => setRoute(routeFromPath(window.location.pathname))
    window.addEventListener('popstate', onPopState)
    return () => window.removeEventListener('popstate', onPopState)
  }, [])

  const navigate = useCallback(id => {
    const next = routeById(id)
    if (window.location.pathname !== next.path) window.history.pushState({}, '', next.path)
    setRoute(next)
    window.scrollTo({ top: 0, behavior: 'auto' })
  }, [])

  return { route, navigate }
}
