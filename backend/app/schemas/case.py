"""案例相关 Pydantic Schema"""
from datetime import date, datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class CaseSearchRequest(BaseModel):
    query: str = Field(default="", description="自然语言案情描述（结构化检索可为空）")
    mode: str = Field(default="semantic", description="semantic / structured / case_to_case")
    cause: Optional[List[str]] = None
    court_level: Optional[str] = None
    procedure: Optional[str] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    region: Optional[str] = None
    article: Optional[str] = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=50)
    sort_by: str = Field(default="relevance", description="relevance / date / court_level / procedure")


class CaseCardResponse(BaseModel):
    id: int
    case_no: str
    title: Optional[str]
    court: Optional[str]
    court_level: Optional[str]
    trial_procedure: Optional[str]
    judgment_date: Optional[date]
    ai_summary: Optional[str] = Field(description="≤50字AI摘要")
    matched_focus: Optional[str]
    relevance_score: float
    processing_status: str

    model_config = {"from_attributes": True}


class CaseSearchResponse(BaseModel):
    total: int
    page: int
    page_size: int
    results: List[CaseCardResponse]
    fallback_note: Optional[str] = None


class DisputeFocusResponse(BaseModel):
    id: int
    focus_name: str
    plaintiff_claim: Optional[str]
    defendant_defense: Optional[str]
    court_finding: Optional[str]

    model_config = {"from_attributes": True}


class LegalRuleResponse(BaseModel):
    id: int
    rule_text: str
    rule_type: Optional[str]
    related_article: Optional[str]

    model_config = {"from_attributes": True}


class CaseDetailResponse(BaseModel):
    id: int
    case_no: str
    title: Optional[str]
    court: Optional[str]
    court_level: Optional[str]
    court_region: Optional[str]
    judge_name: Optional[str]
    trial_procedure: Optional[str]
    case_category_1: Optional[str]
    case_category_2: Optional[str]
    case_category_3: Optional[str]
    judgment_date: Optional[date]
    full_text: Optional[str]
    summary: Optional[str]
    ruling_abstract: Optional[str]
    tags: Optional[List[str]]
    processing_status: str
    confidence_score: float
    dispute_focuses: List[DisputeFocusResponse] = []
    legal_rules: List[LegalRuleResponse] = []
    articles: List[str] = []
    created_at: datetime

    model_config = {"from_attributes": True}


class RelatedCaseResponse(BaseModel):
    id: int
    case_no: str
    title: Optional[str]
    court: Optional[str]
    relation_type: str
    relation_detail: Optional[str]

    model_config = {"from_attributes": True}
