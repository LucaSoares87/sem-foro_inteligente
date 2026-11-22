from sqlalchemy.exc import SQLAlchemyError

class GeographyService:
    def __init__(self,store):
        self.store=store
        self.configured=0
        self.synced=0
        self.error=None

    def sync(self,entries):
        try:
            self.store.sync(entries)
            self.synced=len(entries)
            self.error=None
        except SQLAlchemyError:
            self.error="registry_sync_failed"

    def status(self):
        if self.error:
            state="error"
        elif self.configured:
            state="available"
        else:
            state="not_configured"
        return {"state":state,"configured":self.configured,"synced":self.synced,
                "error_code":self.error,"coordinate_system":"WGS84",
                "external_map_service":False}
