from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TaskCreate(BaseModel):
    agent_key: str
    description: str = Field(min_length=3, max_length=4000)
    priority: int = Field(default=3, ge=1, le=5)
    action: str | None = None
    depends_on: list[int] = []
    input: dict = {}
    due_at: datetime | None = None


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    agent_key: str
    department: str
    description: str
    priority: int
    status: str
    action: str | None
    requires_approval: bool
    depends_on: list
    output: dict | None
    error: str | None
    attempts: int
    created_at: datetime
    due_at: datetime | None


class TaskLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    event: str
    message: str
    created_at: datetime


class AgentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    key: str
    name: str
    department: str
    role: str
    status: str
    model: str
    can_spend: bool
    last_run_at: datetime | None


class GoalIn(BaseModel):
    goal: str = Field(min_length=3, max_length=500)
    pipeline: str = "new_product"
    priority: int = Field(default=3, ge=1, le=5)


class ApprovalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    task_id: int | None
    action: str
    details: dict
    consequences: str
    status: str
    decision_note: str
    created_at: datetime
    decided_at: datetime | None


class DecisionIn(BaseModel):
    decision: str
    note: str = ""


class ProductIn(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    niche: str = ""
    description: str = ""
    price_cents: int = Field(default=0, ge=0)


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    niche: str
    description: str
    price_cents: int
    status: str


class SaleIn(BaseModel):
    product_id: int | None = None
    gross_cents: int = Field(gt=0)
    fee_cents: int = Field(default=0, ge=0)
    refunded_cents: int = Field(default=0, ge=0)


class ExpenseIn(BaseModel):
    category: str = Field(pattern="^(ads|hosting|ai|tools|other)$")
    description: str = ""
    amount_cents: int = Field(gt=0)


class ExperimentIn(BaseModel):
    """Mercado e moeda são obrigatórios e sem padrão: é decisão do proprietário."""
    name: str = Field(min_length=1, max_length=150)
    product_id: int | None = None
    market: str = Field(pattern="^[A-Z]{2}$")
    currency: str = Field(pattern="^[A-Z]{3}$")
    price_cents: int = Field(gt=0)
    fee_bps: int = Field(default=0, ge=0, le=10_000)
    fee_fixed_cents: int = Field(default=0, ge=0)
    budget_cap_cents: int = Field(gt=0)
    max_spend_without_sale_cents: int = Field(gt=0)
    min_sales_to_decide: int = Field(ge=1)

    @model_validator(mode="after")
    def _limits_are_coherent(self):
        if self.max_spend_without_sale_cents > self.budget_cap_cents:
            raise ValueError("max_spend_without_sale_cents não pode passar do teto (budget_cap_cents)")
        return self


class ExperimentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    product_id: int | None
    market: str
    currency: str
    price_cents: int
    fee_bps: int
    fee_fixed_cents: int
    budget_cap_cents: int
    max_spend_without_sale_cents: int
    min_sales_to_decide: int
    status: str
    outcome: str | None
    outcome_note: str
    created_at: datetime
    approved_at: datetime | None
    closed_at: datetime | None
    metrics: dict | None = None


class ExperimentSpendIn(BaseModel):
    amount_cents: int = Field(gt=0)
    note: str = ""


class ExperimentSaleIn(BaseModel):
    gross_cents: int = Field(gt=0)
    fee_cents: int = Field(default=0, ge=0)
    refunded_cents: int = Field(default=0, ge=0)


class ExperimentCloseIn(BaseModel):
    outcome: str = Field(pattern="^(killed|validated)$")
    note: str = ""
