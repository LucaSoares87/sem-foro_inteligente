import {useEffect,useState} from 'react'
import {fetchQueueOptimization} from './queueOptimization.js'

export default function useQueueOptimization(){
  const [state,setState]=useState({data:null,status:'loading'})
  useEffect(()=>{
    let disposed=false,timer,controller
    async function poll(){
      controller=new AbortController()
      const timeout=setTimeout(()=>controller.abort(),8000)
      try{
        const data=await fetchQueueOptimization(controller.signal)
        if(!disposed) setState({data,status:'current'})
      }catch{
        if(!disposed) setState(previous=>({data:previous.data,status:'error'}))
      }finally{
        clearTimeout(timeout)
        if(!disposed) timer=setTimeout(poll,5000)
      }
    }
    poll()
    return ()=>{disposed=true;clearTimeout(timer);controller?.abort()}
  },[])
  return state
}
