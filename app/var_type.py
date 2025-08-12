from typing import Any, Dict

from pydantic import BaseModel


class TFVars(BaseModel):
    model_config = {"extra": "allow"}

    def __init__(self, **data: Any):
        super().__init__(**data)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TFVars":
        return cls(**data)

    def __eq__(self, other):
        if isinstance(other, dict):
            return dict(self) == other
        return super().__eq__(other)

    def __iter__(self):
        return iter(self.model_dump())

    def __getitem__(self, key):
        return self.model_dump()[key]

    def keys(self):
        return self.model_dump().keys()

    def values(self):
        return self.model_dump().values()

    def items(self):
        return self.model_dump().items()
