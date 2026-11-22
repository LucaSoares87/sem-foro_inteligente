import React from 'react'
import useHealth from './useHealth.js'
import useRealtime from './useRealtime.js'
import useIntersections from './useIntersections.js'
import useRoute from './app/useRoute.js'
import AppShell from './components/AppShell.jsx'
import ExecutiveView from './views/ExecutiveView.jsx'
import OperationalView from './views/OperationalView.jsx'
import LaboratoryView from './views/LaboratoryView.jsx'

const views = {
  executive: ExecutiveView,
  operations: OperationalView,
  laboratory: LaboratoryView
}

export default function App() {
  const { data, status, refresh } = useHealth()
  const realtime = useRealtime()
  const intersections = useIntersections()
  const { route, params, navigate } = useRoute()
  const View = views[route.id] || ExecutiveView

  return <AppShell route={route} navigate={navigate} data={data} healthStatus={status} realtime={realtime} refresh={refresh}>
    <View data={data} healthStatus={status} realtime={realtime}
      intersections={intersections.data} intersectionStatus={intersections.status}
      params={params} navigate={navigate} refreshIntersections={intersections.refresh} />
  </AppShell>
}
