import asyncio
from starlette.concurrency import run_in_threadpool
from src.predictive.aggregation import WindowAccumulator

class HistoryService:
    def __init__(self,store,enabled):
        self.store,self.enabled=store,enabled
        self.accumulators={}
        self.queue=asyncio.Queue(maxsize=32)
        self.task=None
        self.accepting=False
        self.saved=self.failed=self.dropped=self.produced=0

    def start(self):
        if self.enabled and self.task is None:
            self.accepting=True
            self.task=asyncio.create_task(self.run(),name="traffic-history")

    def consume(self,snapshot):
        if not self.accepting:
            return
        try:
            accumulator=self.accumulators.setdefault(snapshot.source_id,WindowAccumulator())
            w=accumulator.consume(snapshot)
            if w is not None:
                self.produced+=1
                try:
                    self.queue.put_nowait(w)
                except asyncio.QueueFull:
                    self.dropped+=1
        except Exception:
            self.accumulators.pop(snapshot.source_id,None)
            self.failed+=1

    def clear(self):
        self.accumulators.clear()

    async def run(self):
        while True:
            window=await self.queue.get()
            try:
                await run_in_threadpool(self.store.save,window)
                self.saved+=1
            except asyncio.CancelledError:
                self.dropped+=1
                raise
            except Exception:
                self.failed+=1
            finally:
                self.queue.task_done()

    async def stop(self):
        self.accepting=False
        self.clear()
        if self.task is None:
            return
        try:
            await asyncio.wait_for(self.queue.join(),5)
        except TimeoutError:
            pass
        finally:
            self.task.cancel()
            await asyncio.gather(self.task,return_exceptions=True)
            self.task=None
            while not self.queue.empty():
                self.queue.get_nowait()
                self.queue.task_done()
                self.dropped+=1

    def status(self):
        return {"state":"disabled" if not self.enabled else "degraded" if self.failed or self.dropped else "available",
                "queued":self.queue.qsize(),"capacity":32,"produced":self.produced,"saved":self.saved,
                "failed":self.failed,"dropped":self.dropped,"window_seconds":60,
                "physical_queue_estimate":None,"physical_congestion_index":None,
                "operationally_validated":False}
