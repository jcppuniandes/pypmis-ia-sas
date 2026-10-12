"""Only approved-model execution requests; no arbitrary simulation inputs."""

from pydantic import BaseModel, ConfigDict, Field, StrictInt


class RunCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    title: str = Field("Governed QRA Run", min_length=1, max_length=240)
    comments: str = Field("", max_length=10000)
    seed: StrictInt | None = Field(None, ge=0, le=18446744073709551615)
    iterations: StrictInt | None = Field(None, ge=1, le=1000000)


class RunActionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    comments: str = Field("", max_length=10000)
