"""Query-time retrieval strategy."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class QueryAnalysis:
    """Analyzed query with extracted filters and intent."""
    original_query: str
    vehicle_scope: list[str]
    system_scope: list[str]
    engine_scope: list[str]
    drivetrain_scope: list[str]
    query_type: str  # "procedure" | "specification" | "diagnostic"
    manual_id_filter: str | None = None


@dataclass
class RetrievalResult:
    """A single retrieval result with chunk data and score."""
    chunk_id: str
    text: str
    metadata: dict[str, Any]
    score: float
    source: str  # "primary" | "parent" | "sibling" | "cross_ref"


@dataclass
class RetrievalResponse:
    """Complete retrieval response with ranked results."""
    query: QueryAnalysis
    results: list[RetrievalResult]
    has_safety_warnings: bool = False
    multi_manual: bool = False


# ── Vehicle / engine / drivetrain detection patterns ──────────────

_VEHICLE_PATTERNS = [
    re.compile(r'\bCherokee\b', re.IGNORECASE),
    re.compile(r'\bCJ[-\s]?([23567])\b', re.IGNORECASE),
    re.compile(r'\bCJ[-\s]?3[AB]\b', re.IGNORECASE),
    re.compile(r'\bM38A1\b', re.IGNORECASE),
    re.compile(r'\bM38\b', re.IGNORECASE),
    re.compile(r'\bXJ\b'),
    re.compile(r'\bWrangler\b', re.IGNORECASE),
]

_ENGINE_PATTERNS = [
    re.compile(r'\b(\d+\.\d+)\s*[Ll]\b'),                  # e.g. "4.0L"
    re.compile(r'\bI[46]\b'),                                # e.g. "I4", "I6"
    re.compile(r'\bV[68]\b'),                                # e.g. "V6", "V8"
    re.compile(r'\bHurricane\b', re.IGNORECASE),
    re.compile(r'\b[Dd]iesel\b'),
    re.compile(r'\bF[\-]?4\b'),                              # Hurricane F4
    re.compile(r'\bF[\-]?head\b', re.IGNORECASE),
    re.compile(r'\bL[\-]?head\b', re.IGNORECASE),
]

_DRIVETRAIN_PATTERNS = [
    re.compile(r'\b4WD\b', re.IGNORECASE),
    re.compile(r'\b2WD\b', re.IGNORECASE),
    re.compile(r'\bAWD\b', re.IGNORECASE),
    re.compile(r'\b4x4\b', re.IGNORECASE),
    re.compile(r'\b4[\s-]?wheel\s+drive\b', re.IGNORECASE),
    re.compile(r'\b2[\s-]?wheel\s+drive\b', re.IGNORECASE),
    re.compile(r'\btransfer\s+case\b', re.IGNORECASE),
]

# ── System scope detection patterns ───────────────────────────────

_SYSTEM_KEYWORDS: dict[str, list[str]] = {
    "brake": ["brake", "braking", "caliper", "rotor", "pad", "drum", "abs"],
    "engine": ["engine", "motor", "cylinder", "piston", "valve", "camshaft", "crankshaft", "oil pump"],
    "cooling": ["coolant", "radiator", "thermostat", "water pump", "cooling"],
    "electrical": ["battery", "alternator", "starter", "wiring", "fuse", "ignition", "spark plug"],
    "transmission": ["transmission", "clutch", "gear", "shift", "transaxle"],
    "suspension": ["suspension", "shock", "spring", "strut", "control arm", "ball joint"],
    "steering": ["steering", "power steering", "tie rod", "rack"],
    "fuel": ["fuel", "carburetor", "carburettor", "fuel pump", "fuel filter", "fuel injection", "injector"],
    "exhaust": ["exhaust", "muffler", "catalytic", "manifold"],
    "lubrication": ["oil", "lubrication", "lubricant", "grease"],
    "body": ["body", "door", "window", "fender", "hood", "bumper"],
    "hvac": ["heater", "air conditioning", "a/c", "hvac", "blower"],
    "transfer case": ["transfer case"],
    "axle": ["axle", "differential", "drive shaft", "driveshaft"],
}

# ── Query type classification patterns ────────────────────────────

_PROCEDURE_PATTERNS = [
    re.compile(r'\bhow\s+(do|to|can)\b', re.IGNORECASE),
    re.compile(r'\bprocedure\b', re.IGNORECASE),
    re.compile(r'\breplace\b', re.IGNORECASE),
    re.compile(r'\binstall\b', re.IGNORECASE),
    re.compile(r'\bremov(e|al)\b', re.IGNORECASE),
    re.compile(r'\bchange\b', re.IGNORECASE),
    re.compile(r'\badjust\b', re.IGNORECASE),
    re.compile(r'\bstep[s]?\b', re.IGNORECASE),
    re.compile(r'\brepair\b', re.IGNORECASE),
    re.compile(r'\brebuild\b', re.IGNORECASE),
    re.compile(r'\bservice\b', re.IGNORECASE),
    re.compile(r'\bbleed\b', re.IGNORECASE),
    re.compile(r'\bflush\b', re.IGNORECASE),
]

_SPECIFICATION_PATTERNS = [
    re.compile(r'\bspec(ification)?s?\b', re.IGNORECASE),
    re.compile(r'\btorque\b', re.IGNORECASE),
    re.compile(r'\bcapacity\b', re.IGNORECASE),
    re.compile(r'\bpressure\b', re.IGNORECASE),
    re.compile(r'\bwhat\s+is\b', re.IGNORECASE),
    re.compile(r'\bwhat\s+are\b', re.IGNORECASE),
    re.compile(r'\bhow\s+much\b', re.IGNORECASE),
    re.compile(r'\bhow\s+many\b', re.IGNORECASE),
    re.compile(r'\brating\b', re.IGNORECASE),
    re.compile(r'\bsize\b', re.IGNORECASE),
    re.compile(r'\bweight\b', re.IGNORECASE),
    re.compile(r'\bdimension\b', re.IGNORECASE),
    re.compile(r'\bclearance\b', re.IGNORECASE),
    re.compile(r'\bgap\b', re.IGNORECASE),
    re.compile(r'\bfluid\s+type\b', re.IGNORECASE),
]

_DIAGNOSTIC_PATTERNS = [
    re.compile(r"\bwon'?t\s+start\b", re.IGNORECASE),
    re.compile(r'\btroubleshoot\b', re.IGNORECASE),
    re.compile(r'\bdiagnos(e|tic|is)\b', re.IGNORECASE),
    re.compile(r'\bwhat\s+should\s+I\s+check\b', re.IGNORECASE),
    re.compile(r'\bproblem\b', re.IGNORECASE),
    re.compile(r'\bnoise\b', re.IGNORECASE),
    re.compile(r'\bleak\b', re.IGNORECASE),
    re.compile(r'\boverheating\b', re.IGNORECASE),
    re.compile(r'\bvibration\b', re.IGNORECASE),
    re.compile(r'\bfault\b', re.IGNORECASE),
    re.compile(r'\bcheck\b', re.IGNORECASE),
    re.compile(r'\bwhy\b', re.IGNORECASE),
]


def analyze_query(query: str, available_manuals: list[str]) -> QueryAnalysis:
    """Parse a natural language query to extract filters and intent.

    Identifies vehicle scope, system scope, engine/drivetrain scope,
    and classifies query type.
    """
    # Extract vehicle scope
    vehicle_scope: list[str] = []
    for pat in _VEHICLE_PATTERNS:
        match = pat.search(query)
        if match:
            vehicle = match.group(0)
            if vehicle not in vehicle_scope:
                vehicle_scope.append(vehicle)

    # Extract engine scope
    engine_scope: list[str] = []
    for pat in _ENGINE_PATTERNS:
        match = pat.search(query)
        if match:
            engine = match.group(0)
            if engine not in engine_scope:
                engine_scope.append(engine)

    # Extract drivetrain scope
    drivetrain_scope: list[str] = []
    for pat in _DRIVETRAIN_PATTERNS:
        match = pat.search(query)
        if match:
            drivetrain = match.group(0)
            if drivetrain not in drivetrain_scope:
                drivetrain_scope.append(drivetrain)

    # Extract system scope
    system_scope: list[str] = []
    query_lower = query.lower()
    for system, keywords in _SYSTEM_KEYWORDS.items():
        for keyword in keywords:
            if keyword.lower() in query_lower:
                if system not in system_scope:
                    system_scope.append(system)
                break

    # Classify query type
    query_type = _classify_query_type(query)

    # Determine manual_id_filter if a specific manual can be inferred
    manual_id_filter: str | None = None
    if len(available_manuals) == 1:
        manual_id_filter = available_manuals[0]

    return QueryAnalysis(
        original_query=query,
        vehicle_scope=vehicle_scope,
        system_scope=system_scope,
        engine_scope=engine_scope,
        drivetrain_scope=drivetrain_scope,
        query_type=query_type,
        manual_id_filter=manual_id_filter,
    )


def _classify_query_type(query: str) -> str:
    """Classify the query type as procedure, specification, or diagnostic."""
    # Score each type based on pattern matches
    scores = {"procedure": 0, "specification": 0, "diagnostic": 0}

    for pat in _PROCEDURE_PATTERNS:
        if pat.search(query):
            scores["procedure"] += 1

    for pat in _SPECIFICATION_PATTERNS:
        if pat.search(query):
            scores["specification"] += 1

    for pat in _DIAGNOSTIC_PATTERNS:
        if pat.search(query):
            scores["diagnostic"] += 1

    # Return the type with the highest score, defaulting to procedure
    max_score = max(scores.values())
    if max_score == 0:
        return "procedure"

    # In case of ties, use priority order: diagnostic > specification > procedure
    # (diagnostic patterns are more specific)
    if scores["diagnostic"] == max_score and scores["diagnostic"] > scores["procedure"]:
        return "diagnostic"
    if scores["specification"] == max_score and scores["specification"] > scores["procedure"]:
        return "specification"
    if scores["procedure"] == max_score:
        return "procedure"

    # Fallback
    return max(scores, key=lambda k: scores[k])


def enrich_with_parent(results: list[RetrievalResult]) -> list[RetrievalResult]:
    """Add parent chunk context to retrieval results."""
    enriched = list(results)

    for result in results:
        parent_id = result.metadata.get("parent_chunk_id")
        if parent_id is None:
            continue

        # Check if parent is already in results
        existing_ids = {r.chunk_id for r in enriched}
        if parent_id in existing_ids:
            continue

        # Add a placeholder parent result with reduced score
        parent_result = RetrievalResult(
            chunk_id=parent_id,
            text="",  # Would be populated from store in production
            metadata={},
            score=result.score * 0.7,  # Parent gets reduced score
            source="parent",
        )
        enriched.append(parent_result)

    return enriched


def enrich_with_siblings(results: list[RetrievalResult]) -> list[RetrievalResult]:
    """Add sibling chunk context above similarity threshold."""
    enriched = list(results)

    for result in results:
        sibling_ids = result.metadata.get("sibling_chunk_ids", [])
        if not sibling_ids:
            continue

        existing_ids = {r.chunk_id for r in enriched}

        for sibling_id in sibling_ids:
            if sibling_id in existing_ids:
                continue

            sibling_result = RetrievalResult(
                chunk_id=sibling_id,
                text="",  # Would be populated from store in production
                metadata={},
                score=result.score * 0.6,  # Siblings get further reduced score
                source="sibling",
            )
            enriched.append(sibling_result)

    return enriched


def resolve_cross_references(results: list[RetrievalResult]) -> list[RetrievalResult]:
    """Resolve cross-references found in retrieved chunks."""
    enriched = list(results)

    for result in results:
        cross_refs = result.metadata.get("cross_references", [])
        if not cross_refs:
            continue

        # In a full implementation, we'd look up the cross-reference targets
        # in the SQLite index and add them as results. For now, we keep
        # the results as-is since cross-refs need external resolution.

    return enriched


def rerank(results: list[RetrievalResult], top_n: int = 5) -> list[RetrievalResult]:
    """Re-rank retrieval results and return top N."""
    # Sort by score descending
    sorted_results = sorted(results, key=lambda r: r.score, reverse=True)
    # Return top N
    return sorted_results[:top_n]


def retrieve(
    query: QueryAnalysis,
    top_k: int = 10,
    collection_name: str = "service_manuals",
) -> RetrievalResponse:
    """Execute the full retrieval pipeline.

    Steps:
    1. Embed query -> ANN search with metadata filters
    2. Parent-chunk enrichment
    3. Sibling-chunk enrichment
    4. Cross-reference resolution
    5. Re-rank -> top-3 to top-5
    """
    from .embeddings import generate_embedding

    # Step 1: Generate query embedding and search
    query_vector = generate_embedding(query.original_query)

    # In production, we'd search Qdrant here. For now, return empty
    # since the actual search requires a running Qdrant instance.
    primary_results: list[RetrievalResult] = []

    # Step 2: Parent-chunk enrichment
    enriched = enrich_with_parent(primary_results)

    # Step 3: Sibling-chunk enrichment
    enriched = enrich_with_siblings(enriched)

    # Step 4: Cross-reference resolution
    enriched = resolve_cross_references(enriched)

    # Step 5: Re-rank and return top results
    final_results = rerank(enriched, top_n=min(top_k, 5))

    # Check for safety warnings in results
    has_safety = any(
        r.metadata.get("has_safety_callouts")
        for r in final_results
    )

    return RetrievalResponse(
        query=query,
        results=final_results,
        has_safety_warnings=has_safety,
        multi_manual=query.manual_id_filter is None,
    )
