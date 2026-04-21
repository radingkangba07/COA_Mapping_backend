from pydantic import BaseModel


class SuggestionAccountResponse(BaseModel):
    id: str | None = None
    suggestion_id: str
    source_name: str
    target_name: str
    score: float
    status: str
    mapping_source: str | None = None


class SuggestionGroupResponse(BaseModel):
    source_type: str
    target_type: str
    confidence: float
    accounts: list[SuggestionAccountResponse]
