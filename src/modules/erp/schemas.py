from pydantic import BaseModel


class ERPField(BaseModel):
    id: str
    name: str
    type: str
    required: bool


class ERPSystem(BaseModel):
    id: str
    name: str
    description: str = ""
    fields: list[ERPField] = []


class AccountTypesResponse(BaseModel):
    erp_id: str
    account_types: list[str]


class SampleDataResponse(BaseModel):
    erp_id: str
    erp_name: str
    data: list[dict]
    row_count: int
