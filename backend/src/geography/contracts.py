import json
from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_INTERSECTIONS=500

class IntersectionSeed(BaseModel):
    model_config=ConfigDict(frozen=True,extra="forbid",allow_inf_nan=False)
    code: str = Field(pattern=r"^[A-Z0-9_-]{2,80}$")
    name: str = Field(min_length=2,max_length=160)
    district: str | None = Field(default=None,min_length=2,max_length=120)
    latitude: float | None = Field(default=None,ge=-90,le=90)
    longitude: float | None = Field(default=None,ge=-180,le=180)
    enabled: bool = True

    @model_validator(mode="after")
    def coordinate_pair(self):
        if (self.latitude is None)!=(self.longitude is None):
            raise ValueError("latitude and longitude must be supplied together")
        return self

class IntersectionView(BaseModel):
    model_config=ConfigDict(from_attributes=True)
    code: str
    name: str
    district: str | None
    latitude: float | None
    longitude: float | None
    enabled: bool
    has_coordinates: bool

def load_registry(raw):
    try:
        if len(raw)>128000:
            raise ValueError
        data=json.loads(raw)
        if not isinstance(data,list) or len(data)>MAX_INTERSECTIONS:
            raise ValueError
        values=tuple(IntersectionSeed.model_validate(item) for item in data)
        if len({item.code for item in values})!=len(values):
            raise ValueError
        return values
    except (TypeError,ValueError):
        raise ValueError("invalid intersection registry") from None
