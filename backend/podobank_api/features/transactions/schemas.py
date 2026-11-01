from pydantic import BaseModel, Field


class AmountRequest(BaseModel):
    amount: int = Field(strict=True)


class TransferRequest(AmountRequest):
    destination_account_id: int = Field(strict=True, gt=0)
