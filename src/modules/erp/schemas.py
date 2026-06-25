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
    vendor_id: str | None = None
    vendor_name: str | None = None
    connection_methods: list[str] = []
    fields: list[ERPField] = []


class ERPVendor(BaseModel):
    id: str
    name: str
    products: list[str] = []


class ConnectionMethod(BaseModel):
    id: str
    name: str


class AccountTypesResponse(BaseModel):
    erp_id: str
    account_types: list[str]


class SampleDataResponse(BaseModel):
    erp_id: str
    erp_name: str
    data: list[dict]
    row_count: int
