from pydantic import BaseModel, Field


class RecipientSearchRequest(BaseModel):
    query: str = Field(min_length=10, max_length=64)
