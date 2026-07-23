import uuid

from pydantic import BaseModel, field_validator


class RunCreateRequest(BaseModel):
    source_file_ref: str

    @field_validator("source_file_ref")
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("source_file_ref must not be empty")
        return v


class RunCreateResponse(BaseModel):
    run_id: uuid.UUID
    status: str
