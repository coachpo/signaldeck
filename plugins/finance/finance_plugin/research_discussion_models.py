"""Bounded, closed records for independently authored research discussion stages."""

from typing import Annotated, Literal

from plugin_runtime.common import CamelModel
from pydantic import Field

ArgumentId = Annotated[str, Field(min_length=1, max_length=80)]
DiscussionText = Annotated[str, Field(min_length=1, max_length=1000)]
EvidenceId = Annotated[str, Field(min_length=1, max_length=160)]


class DiscussionArgument(CamelModel):
    argument_id: ArgumentId
    statement: DiscussionText
    evidence_ids: list[EvidenceId] = Field(max_length=10)


class DiscussionCase(CamelModel):
    arguments: list[DiscussionArgument] | None = Field(default=None, max_length=3)


class DiscussionResponse(CamelModel):
    argument_id: ArgumentId
    disposition: Literal["accepted", "partially_accepted", "rejected", "unresolved"]
    rationale: DiscussionText
    evidence_ids: list[EvidenceId] = Field(max_length=10)


class DiscussionResponses(CamelModel):
    responses: list[DiscussionResponse] | None = Field(default=None, max_length=3)


class DiscussionAssessment(CamelModel):
    argument_id: ArgumentId
    assessment: Literal["supported", "weakened", "unresolved"]
    rationale: DiscussionText
    evidence_ids: list[EvidenceId] = Field(max_length=10)


class DiscussionRiskReview(CamelModel):
    assessments: list[DiscussionAssessment] | None = Field(default=None, max_length=6)


class DiscussionDecision(CamelModel):
    argument_id: ArgumentId
    disposition: Literal["retained", "revised", "withdrawn", "unresolved"]
    rationale: DiscussionText
    evidence_ids: list[EvidenceId] = Field(max_length=10)


class DiscussionAdjudication(CamelModel):
    decisions: list[DiscussionDecision] | None = Field(default=None, max_length=6)


class ResearchDiscussion(CamelModel):
    bull_case: DiscussionCase | None = None
    bear_case: DiscussionCase | None = None
    bull_response: DiscussionResponses | None = None
    bear_response: DiscussionResponses | None = None
    risk_review: DiscussionRiskReview | None = None
    adjudication: DiscussionAdjudication | None = None
