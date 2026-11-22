import { useEffect, useState } from 'react'
import { websocketUrl } from './health.js'

export default function useRealtime() {
  const [status, setStatus] = useState('connecting')
  useEffect(() => {
    let disposed = false, socket, reconnect, heartbeat, watchdog
    let failures = 0
    function connect() {
      if (disposed) return
      setStatus('connecting')
      socket = new WebSocket(websocketUrl(window.location))
      const active = socket
      function armWatchdog() {
        clearTimeout(watchdog)
        watchdog = setTimeout(() => active.close(), 20000)
      }
      armWatchdog()
      active.onmessage = event => {
        if (disposed || active !== socket) return
        try {
          const data = JSON.parse(event.data)
          if (data.version !== 1) return
          if (data.type === 'connection_ack') {
            failures = 0
            setStatus('connected')
            clearInterval(heartbeat)
            heartbeat = setInterval(() => {
              if (active.readyState === WebSocket.OPEN) active.send('ping')
            }, 10000)
            active.send('ping')
            armWatchdog()
          } else if (data.type === 'heartbeat') {
            armWatchdog()
          }
        } catch { active.close() }
      }
      active.onerror = () => active.close()
      active.onclose = () => {
        clearInterval(heartbeat)
        clearTimeout(watchdog)
        if (disposed || active !== socket) return
        setStatus('disconnected')
        const delay = Math.min(1000 * 2 ** Math.min(failures++, 5), 30000)
        reconnect = setTimeout(connect, delay + Math.random() * 500)
      }
    }
    connect()
    return () => {
      disposed = true
      clearTimeout(reconnect)
      clearTimeout(watchdog)
      clearInterval(heartbeat)
      if (socket) socket.close()
    }
  }, [])
  return status
}
