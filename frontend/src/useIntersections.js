import { useEffect, useState } from 'react'
import { fetchIntersections } from './intersections.js'

export default function useIntersections() {
  const [state,setState]=useState({data:[],status:'loading'})
  const [revision,setRevision]=useState(0)
  useEffect(()=>{
    let disposed=false,timer,controller
    async function poll(){
      controller=new AbortController()
      const timeout=setTimeout(()=>controller.abort(),8000)
      try{
        const data=await fetchIntersections(controller.signal)
        if(!disposed) setState({data,status:'current'})
      }catch{
        if(!disposed) setState(previous=>({data:previous.data,status:'error'}))
      }finally{
        clearTimeout(timeout)
        if(!disposed) timer=setTimeout(poll,15000)
      }
    }
    poll()
    return ()=>{disposed=true;clearTimeout(timer);controller?.abort()}
  },[revision])
  return {...state,refresh:()=>setRevision(value=>value+1)}
}
