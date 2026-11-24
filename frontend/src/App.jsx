import React from 'react'
import useHealth from './useHealth.js'
import useRealtime from './useRealtime.js'
import useIntersections from './useIntersections.js'
import useRoute from './app/useRoute.js'
import AppShell from './components/AppShell.jsx'
import ExecutiveView from './views/ExecutiveView.jsx'
import OperationalView from './views/OperationalView.jsx'
import LaboratoryView from './views/LaboratoryView.jsx'
import VideowallView from './views/VideowallView.jsx'
import PresentationView from './views/PresentationView.jsx'
import ValidationView from './views/ValidationView.jsx'

const views = {
  executive: ExecutiveView,
  operations: OperationalView,
  laboratory: LaboratoryView,
  videowall: VideowallView,
  presentation: PresentationView,
  validation: ValidationView
}
const immersive = new Set(['videowall','presentation'])

export default function App() {
  const { data, status, refresh } = useHealth()
  const realtime = useRealtime()
  const intersections = useIntersections()
  const { route, params, navigate } = useRoute()
  const View = views[route.id] || ExecutiveView
  const props={data,healthStatus:status,realtime,intersections:intersections.data,
    intersectionStatus:intersections.status,params,navigate,refreshIntersections:intersections.refresh,refresh}

  if(immersive.has(route.id)) return <View {...props}/>

  return <AppShell route={route} navigate={navigate} data={data} healthStatus={status} realtime={realtime} refresh={refresh}>
    <View {...props}/>
  </AppShell>
}
