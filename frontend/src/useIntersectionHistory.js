import {useEffect,useState} from 'react'
import {fetchIntersectionHistory} from './history.js'

export default function useIntersectionHistory(intersection,enabled=true){
  const [state,setState]=useState({data:null,status:intersection?'loading':'idle'})
  useEffect(()=>{
    if(!intersection||!enabled){
      setState({data:null,status:enabled?'idle':'disabled'})
      return
    }
    let disposed=false,timer,controller
    async function poll(){
      controller=new AbortController()
      const timeout=setTimeout(()=>controller.abort(),8000)
      try{
        const data=await fetchIntersectionHistory(intersection,controller.signal)
        if(!disposed) setState({data,status:'current'})
      }catch{
        if(!disposed) setState(previous=>({data:previous.data,status:'error'}))
      }finally{
        clearTimeout(timeout)
        if(!disposed) timer=setTimeout(poll,30000)
      }
    }
    setState({data:null,status:'loading'})
    poll()
    return ()=>{disposed=true;clearTimeout(timer);controller?.abort()}
  },[intersection,enabled])
  return state
}
