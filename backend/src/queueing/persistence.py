import asyncio
from starlette.concurrency import run_in_threadpool

PERSIST_INTERVAL_SECONDS=10
CAPACITY=32

class QueuePersistence:
    def __init__(self,store,enabled):
        self.store,self.enabled=store,enabled
        self.queue=asyncio.Queue(maxsize=CAPACITY)
        self.task=None
        self.accepting=False
        self.last_queued={}
        self.saved=self.failed=self.dropped=0

    def start(self):
        if self.enabled and self.task is None:
            self.accepting=True
            self.task=asyncio.create_task(self.run(),name="queue-history")

    def consume(self,snapshot,result):
        if not self.accepting:
            return
        previous=self.last_queued.get(snapshot.source_id)
        if previous is not None and (snapshot.received_at-previous).total_seconds()<PERSIST_INTERVAL_SECONDS:
            return
        self.last_queued[snapshot.source_id]=snapshot.received_at
        try:
            self.queue.put_nowait((snapshot,result))
        except asyncio.QueueFull:
            self.dropped+=1

    async def run(self):
        while True:
            item=await self.queue.get()
            try:
                await run_in_threadpool(self.store.save,*item)
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
        self.last_queued.clear()
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
                "queued":self.queue.qsize(),"capacity":CAPACITY,"saved":self.saved,
                "failed":self.failed,"dropped":self.dropped,
                "persist_interval_seconds":PERSIST_INTERVAL_SECONDS}
