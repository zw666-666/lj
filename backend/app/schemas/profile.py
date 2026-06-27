"""法官/法院画像 Schema"""
from typing import Optional, List
from pydantic import BaseModel, Field, model_validator


class JudgeProfileResponse(BaseModel):
    id: int
    judge_name: str
    court: Optional[str]
    division: Optional[str]
    total_cases: int
    avg_duration_days: Optional[float]
    support_plaintiff_ratio: Optional[float]
    support_defendant_ratio: Optional[float]
    partial_support_ratio: Optional[float]
    appeal_reversal_ratio: Optional[float]
    reversed_by_superior_ratio: Optional[float]
    avg_opinion_length: Optional[int]
    top_articles: Optional[List[dict]]
    case_type_distribution: Optional[List[dict]]
    style_tags: Optional[List[str]]

    model_config = {"from_attributes": True}


class CourtProfileResponse(BaseModel):
    court_name: str
    total_cases: int
    support_ratio_distribution: dict
    reversal_ratio: Optional[float]
    division_comparison: Optional[List[dict]]
    compensation_range: Optional[dict]


class CompareRequest(BaseModel):
    case_ids: List[int] = Field(default_factory=list, max_length=5)
    uploaded_cases: List[dict] = Field(default_factory=list, max_length=5)

    @model_validator(mode="after")
    def check_min_cases(self):
        if len(self.case_ids) + len(self.uploaded_cases) < 2:
            raise ValueError("至少需要2个案例")
        return self


class CompareMatrixRow(BaseModel):
    dimension: str
    values: List[str]


class KeyVariable(BaseModel):
    description: str
    case_a: str
    case_b: str
    evidence_refs: List[str]


class CompareResponse(BaseModel):
    matrix: List[CompareMatrixRow]
    key_variables: List[KeyVariable]
    is_premium: bool = False
