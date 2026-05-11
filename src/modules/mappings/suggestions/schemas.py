from pydantic import BaseModel


class SuggestionAccountResponse(BaseModel):
    id: str | None = None
    suggestion_id: str
    source_account_number: str | None = None
    source_name: str
    target_account_number: str | None = None
    target_name: str
    score: float
    status: str
    mapping_source: str | None = None


class SuggestionGroupResponse(BaseModel):
    source_type: str
    target_type: str
    confidence: float
    accounts: list[SuggestionAccountResponse]


class SuggestionListResponse(BaseModel):
    total: int
    groups: list[SuggestionGroupResponse]
