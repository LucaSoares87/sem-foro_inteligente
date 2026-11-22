import { useEffect, useState } from 'react'
import { fetchHealth } from './health.js'

export default function useHealth() {
  const [state, setState] = useState({ data: null, status: 'loading' })
  const [revision, setRevision] = useState(0)
  useEffect(() => {
    let disposed = false
    let timer
    let controller
    async function poll() {
      controller = new AbortController()
      const timeout = setTimeout(() => controller.abort(), 9000)
      try {
        const data = await fetchHealth(controller.signal)
        if (!disposed) setState({ data, status: 'current' })
      } catch {
        if (!disposed) setState({ data: null, status: 'error' })
      } finally {
        clearTimeout(timeout)
        if (!disposed) timer = setTimeout(poll, 5000)
      }
    }
    poll()
    return () => { disposed = true; clearTimeout(timer); controller?.abort() }
  }, [revision])
  return { ...state, refresh: () => setRevision(n => n + 1) }
}
