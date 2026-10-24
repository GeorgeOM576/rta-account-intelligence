from dataclasses import dataclass, field, asdict
import re
import unicodedata

INTELLIGENCE_PENDING = 'Intelligence Proposed — Pending Approval'
AI_PENDING = INTELLIGENCE_PENDING  # Retain the existing internal import contract.
MANUAL_REQUIRED = 'Manual Review Required'
REVIEW_FILTERS = ['All', INTELLIGENCE_PENDING, MANUAL_REQUIRED, 'Approved', 'Rejected', 'Manually Verified']


def has_proposal(result):
    return result.proposed is not None and bool(str(result.proposed).strip())


def review_status_label(result):
    """Display the effective proposal without granting approval eligibility or mutating data."""
    if result.decision in ('Approve', 'Approve proposal'):
        return 'Approved'
    if result.decision == 'Reject':
        return 'Rejected'
    if result.decision in ('Manual', 'Manual value', 'Retain original'):
        return 'Manually Verified'
    return INTELLIGENCE_PENDING if has_proposal(result) else MANUAL_REQUIRED


def normalize(value):
    return re.sub(r'[^\w]', '', unicodedata.normalize('NFKC', str(value or '')).casefold())


def valid(value):
    return normalize(value) not in {'', 'verify', 'verified', 'unmapped', 'duplicate', 'blank', 'null', 'na', 'none'}


@dataclass
class Mapping:
    master_id: str
    source_id: str
    master_value: str
    source_value: str


@dataclass
class Result:
    row_id: int
    identifier: str
    original: str
    proposed: str = ''
    final: str = ''
    match_status: str = 'Unresolved'
    identity_confidence: str = 'Unverified'
    review_status: str = 'Pending'
    candidates: list = field(default_factory=list)
    relationship: str = ''
    research_status: str = 'Not researched'
    explanation: str = ''
    evidence: list = field(default_factory=list)
    decision: str = ''
    notes: str = ''
    reviewer: str = ''
    reviewed_at: str = ''
    value_origin: str = ''
    verified_original: str = ''
    ai_proposed: str = ''
    recommended_source_account: str = ''
    parent_company: str = ''
    ai_confidence: str = ''
    recommendation_status: str = ''
    recommendation_reasoning: str = ''
    researched_at: str = ''
    research_snapshot: dict = field(default_factory=dict)
    research_history: list = field(default_factory=list)
    research_cache_hit: bool = False
    verified_facts: list = field(default_factory=list)
    suggested_matches: list = field(default_factory=list)
    mapping_policy: str = ''
    selected_source: dict = field(default_factory=dict)
    translation_provenance: list = field(default_factory=list)
    account_context: dict = field(default_factory=dict)
    match_method: str = ''
    match_basis: str = ''
    local_proposed: str = ''
    local_confidence: str = ''
    local_reason: str = ''
    match_score: float | None = None

    def __post_init__(self):
        if self.decision == 'Manual value':
            self.decision = 'Manual'
            self.review_status = 'Manually Verified'
            self.value_origin = self.value_origin or 'custom entry'
        if (self.decision == 'Retain original' and valid(self.original)
                and normalize(self.final) == normalize(self.original)):
            self.verified_original = self.original

    @property
    def status_label(self):
        return review_status_label(self)

    def dict(self):
        return asdict(self)
