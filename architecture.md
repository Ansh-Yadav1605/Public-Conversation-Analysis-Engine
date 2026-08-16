# Architecture — Public Conversation Analysis Engine

> **Project:** Graduation Project — Product Management  
> **Domain:** Fashion E-commerce (initial anchor; engine is generic)  
> **Version:** 1.0  
> **Last Updated:** 2026-08-15

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Guiding Design Principles](#2-guiding-design-principles)
3. [High-Level Architecture Diagram](#3-high-level-architecture-diagram)
4. [Pipeline Stages — Detailed Breakdown](#4-pipeline-stages--detailed-breakdown)
   - 4.1 [Stage 1 — Source Scraping](#41-stage-1--source-scraping)
   - 4.2 [Stage 2 — Taxonomy-Based Extraction](#42-stage-2--taxonomy-based-extraction)
   - 4.3 [Stage 3 — Opportunity Clustering & Scoring](#43-stage-3--opportunity-clustering--scoring)
5. [Component Map](#5-component-map)
6. [Data Models](#6-data-models)
7. [Configurability Layer](#7-configurability-layer)
8. [Quality & Integrity Controls](#8-quality--integrity-controls)
9. [Output Schema & Delivery](#9-output-schema--delivery)
10. [Explicit Boundaries](#10-explicit-boundaries)
11. [Alignment with Success Criteria](#11-alignment-with-success-criteria)

---

## 1. System Overview

The **Public Conversation Analysis Engine** is a three-stage analytical pipeline that converts raw, unstructured public conversation data into a ranked, evidence-tagged set of product opportunity areas.

It is designed to answer a fixed set of **behavioral questions** about why users exhibit a specific behavior — in this project, why users add fashion products to wishlists but do not convert to purchase. These questions cannot be reliably answered by sentiment scoring or review summarization alone.

### Core Transformation

```
Raw Public Text  →  Structured Signals  →  Ranked Opportunity Areas
```

The engine outputs a deliverable that a product team can directly take into primary research (user interviews), replacing the slow, manual process of reading public conversations at scale.

---

## 2. Guiding Design Principles

| Principle | Description |
|---|---|
| **Generic & Configurable** | The taxonomy and question set are runtime inputs, not hardcoded logic. The engine can be re-pointed at any product category without a rebuild. |
| **Signal-Level Granularity** | A single review or thread may yield multiple distinct signals. The engine preserves this granularity rather than collapsing it into a single label. |
| **Source Traceability** | Every extracted signal retains a pointer to its exact source — platform, content ID, date — so every insight is fully auditable. |
| **Comparability First** | Opportunities are structured to be ranked against each other, not just listed. Frequency, severity, and evidence-strength are first-class attributes. |
| **Not a Sentiment Tool** | Sentiment polarity is insufficient; two "negative" mentions can represent completely different root causes. The engine resolves root cause, not tone. |

---

## 3. High-Level Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                        CONFIGURATION LAYER                          │
│         [ Taxonomy ]  [ Question Set ]  [ Source List ]             │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ injects config
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    STAGE 1 — SOURCE SCRAPING                         │
│                                                                      │
│  ┌────────────┐  ┌─────────────┐  ┌──────────┐  ┌────────────────┐  │
│  │ App Store  │  │ Play Store  │  │  Reddit  │  │ Fashion Forums │  │
│  │  Reviews   │  │   Reviews   │  │ Threads  │  │  Communities   │  │
│  └────────────┘  └─────────────┘  └──────────┘  └────────────────┘  │
│                                                                      │
│  ┌────────────┐  ┌─────────────┐  ┌──────────────────────────────┐  │
│  │  Social    │  │  YouTube    │  │  Product Reviews & Q&A       │  │
│  │  Media     │  │  Comments   │  │  (Myntra, AJIO, etc.)        │  │
│  └────────────┘  └─────────────┘  └──────────────────────────────┘  │
│                                                                      │
│               → Raw Conversation Store (Normalized)                  │
└──────────────────────────────┬───────────────────────────────────────┘
                               │ normalized raw records
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│                 STAGE 2 — TAXONOMY-BASED EXTRACTION                  │
│                                                                      │
│   Text Preprocessing → Signal Detection → Taxonomy Mapping           │
│                                                                      │
│   Output: Signal Records                                             │
│   [ signal_type | dimension | quote | source_ref | metadata ]        │
└──────────────────────────────┬───────────────────────────────────────┘
                               │ structured signal records
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│           STAGE 3 — OPPORTUNITY CLUSTERING & SCORING                 │
│                                                                      │
│   Signal Clustering → Opportunity Area Synthesis                     │
│   → Scoring (Frequency · Severity · Evidence Strength)               │
│   → Ranking → Question Mapping                                       │
│                                                                      │
│   Output: Ranked Opportunity Report                                  │
└──────────────────────────────┬───────────────────────────────────────┘
                               │
                               ▼
                  ┌────────────────────────┐
                  │   DELIVERY / OUTPUT    │
                  │  Structured Report +   │
                  │  Source-Traced Quotes  │
                  └────────────────────────┘
                               │
                               ▼
              Primary Research (User Interviews)
```

---

## 4. Pipeline Stages — Detailed Breakdown

### 4.1 Stage 1 — Source Scraping

**Purpose:** Collect raw, unstructured public conversation data from all configured sources and normalize it into a common intermediate format.

#### 4.1.1 Data Sources

| Source Type | Examples | Signal Richness |
|---|---|---|
| App Store Reviews | Apple App Store (Myntra, AJIO apps) | High — detailed, structured |
| Play Store Reviews | Google Play Store | High — detailed, structured |
| Reddit Discussions | r/IndianFashionAddicts, r/frugalmalefashion, r/india | Very High — long-form, contextual |
| Fashion & Shopping Communities | Forums, Quora threads, community sites | High — topic-specific |
| Social Media | Twitter/X, Instagram comments | Medium — short but high volume |
| YouTube Comments | Haul videos, review videos, try-on videos | Medium-High — contextual |
| Product Reviews & Q&A | Myntra, AJIO on-platform reviews and Q&A | High — product-specific |

#### 4.1.2 Scraping Sub-Components

```
┌──────────────┐     ┌─────────────────────┐     ┌──────────────────────┐
│ Source       │────▶│  Connector /        │────▶│  Raw Content Store   │
│ Config List  │     │  Scraper Adapter    │     │  (per-source schema) │
└──────────────┘     └─────────────────────┘     └──────────┬───────────┘
                                                             │
                                                             ▼
                                                  ┌──────────────────────┐
                                                  │  Normalization Layer │
                                                  │  (Unified Record)    │
                                                  └──────────────────────┘
```

- Each source type has a dedicated **Connector/Adapter** responsible for fetching data via API, web scraping, or file import.
- The **Normalization Layer** maps each source's schema to a unified `RawRecord` format.

#### 4.1.3 Unified Raw Record Schema

```json
{
  "record_id":      "uuid",
  "source_type":    "reddit | app_store | play_store | social | youtube | forum | review_qa",
  "source_name":    "Reddit — r/IndianFashionAddicts",
  "content_id":     "platform-specific post/review ID",
  "url":            "https://...",
  "text":           "Full raw text of the post/review/comment",
  "author_meta":    { "user_type": "anonymous | identified", "segment_hints": [] },
  "date_collected": "ISO-8601",
  "date_published": "ISO-8601 or null",
  "platform_meta":  { "upvotes": 0, "reply_count": 0, "rating": null }
}
```

#### 4.1.4 Deduplication & Freshness

- **Deduplication:** Records are fingerprinted (source + content_id + text hash) to avoid processing the same content twice across runs.
- **Freshness Policy:** Configurable lookback window (e.g., last 12 months) to keep signals relevant.

---

### 4.2 Stage 2 — Taxonomy-Based Extraction

**Purpose:** Transform unstructured `RawRecord` text into discrete, structured `Signal` records by applying the configured taxonomy.

#### 4.2.1 What is a Signal?

A **signal** is a single, atomic behavioral observation extracted from text. A single review or comment can yield **multiple signals** — for example, a review may simultaneously express a fit uncertainty, a price hesitation, and a return-policy concern. Each is captured as a separate signal record.

#### 4.2.2 Extraction Sub-Pipeline

```
RawRecord
    │
    ▼
┌───────────────────────┐
│  Text Preprocessor    │  — clean, de-noise, language detect, tokenize
└───────────┬───────────┘
            │
            ▼
┌───────────────────────┐
│  Taxonomy Matcher     │  — maps text spans to taxonomy nodes
│  (NLP / LLM-assisted) │    using keyword rules, embeddings, or LLM prompts
└───────────┬───────────┘
            │
            ▼
┌───────────────────────┐
│  Signal Constructor   │  — assembles one Signal record per detected node
└───────────┬───────────┘
            │
            ▼
┌───────────────────────┐
│  Signal Store         │  — persists all signal records with source refs
└───────────────────────┘
```

#### 4.2.3 The Taxonomy

The taxonomy is a **configurable, hierarchical classification scheme** that defines what signals to look for. It is injected at runtime — not hardcoded.

For the fashion e-commerce anchor, the taxonomy covers the following **dimensions**:

| Dimension | Sub-categories (examples) |
|---|---|
| **Fit & Sizing** | Size uncertainty, inconsistent sizing across brands, fit for body type |
| **Styling** | Occasion mismatch, coordination doubt, styling advice-seeking |
| **Price & Value** | Price hesitation, waiting for sale, price-vs-quality doubt |
| **Trust & Reviews** | Review scarcity, review authenticity doubt, brand credibility |
| **Return & Risk** | Return policy friction, fear of irreversible purchase |
| **Social Validation** | Seeking peer approval, trend alignment, gifting uncertainty |
| **Product Information** | Missing details, image quality doubt, fabric/material uncertainty |
| **Comparison Behavior** | Cross-platform comparison, shortlisting multiple options |
| **Intent Signal** | Genuine purchase intent vs. bookmarking/aspiration |
| **Segment Markers** | Demographic, occasion, purchase frequency cues |

**Each taxonomy node includes:**
- A unique `node_id` and human-readable `label`
- A mapping to one or more of the **10 behavioral questions**
- Detection rules (keyword sets, embedding centroids, or LLM prompt templates)

#### 4.2.4 Signal Record Schema

```json
{
  "signal_id":       "uuid",
  "record_id":       "ref → RawRecord.record_id",
  "source_ref": {
    "source_type":   "reddit",
    "source_name":   "r/IndianFashionAddicts",
    "url":           "https://...",
    "date_published":"ISO-8601"
  },
  "taxonomy_node":   "fit_sizing.inconsistent_sizing",
  "dimension":       "Fit & Sizing",
  "sub_category":    "Inconsistent Sizing Across Brands",
  "question_refs":   [2, 3, 7],
  "verbatim_quote":  "I always order an M from Zara but on Myntra I had to size up twice",
  "severity_hint":   "high | medium | low | unknown",
  "segment_hints":   ["female", "urban", "repeat_buyer"],
  "confidence":      0.87
}
```

---

### 4.3 Stage 3 — Opportunity Clustering & Scoring

**Purpose:** Group related signals into coherent **Opportunity Areas**, score them on multiple dimensions, and produce a ranked, comparable shortlist for the product team.

#### 4.3.1 What is an Opportunity Area?

An **Opportunity Area** is a cluster of signals that share the same root cause and represent a consistently appearing unmet need — observed across **independent conversations and sources**, not as isolated incidents.

#### 4.3.2 Clustering Sub-Pipeline

```
Signal Store
    │
    ▼
┌──────────────────────────┐
│  Signal Grouper          │  — groups by taxonomy_node and dimension
└──────────────┬───────────┘
               │
               ▼
┌──────────────────────────┐
│  Cross-Source Validator  │  — checks that a cluster appears in >= 2 independent sources
│                          │    (filters out platform-specific noise)
└──────────────┬───────────┘
               │
               ▼
┌──────────────────────────┐
│  Opportunity Synthesizer │  — writes a human-readable opportunity statement
│                          │    and selects representative verbatim quotes
└──────────────┬───────────┘
               │
               ▼
┌──────────────────────────┐
│  Scorer                  │  — computes Frequency, Severity, Evidence Strength
└──────────────┬───────────┘
               │
               ▼
┌──────────────────────────┐
│  Ranker                  │  — produces final ranked list
└──────────────────────────┘
```

#### 4.3.3 Scoring Dimensions

| Dimension | Description | Input Data |
|---|---|---|
| **Frequency** | How many unique signals (and unique sources) reference this opportunity | Signal count, source-type spread |
| **Severity** | How strongly users express this as a barrier to action | Severity hints from signals, language intensity |
| **Evidence Strength** | How consistent and cross-source the signal cluster is | Source diversity, confidence scores, quote quality |
| **Segment Concentration** | Whether the opportunity is concentrated in a specific user segment | Segment hints from signals |

#### 4.3.4 Composite Priority Score

```
Priority Score = w1 * (Frequency Score)
              + w2 * (Severity Score)
              + w3 * (Evidence Strength Score)
```

Weights (`w1`, `w2`, `w3`) are configurable to allow the product team to tune prioritization emphasis.

#### 4.3.5 Opportunity Area Record Schema

```json
{
  "opportunity_id":       "uuid",
  "title":                "Size inconsistency creates pre-purchase paralysis",
  "dimension":            "Fit & Sizing",
  "taxonomy_nodes":       ["fit_sizing.inconsistent_sizing", "fit_sizing.size_uncertainty"],
  "question_answers":     [2, 3, 7],
  "signal_count":         142,
  "source_spread": {
    "reddit":             45,
    "app_store":          38,
    "play_store":         29,
    "youtube":            18,
    "forum":              12
  },
  "scores": {
    "frequency":          0.84,
    "severity":           0.91,
    "evidence_strength":  0.78,
    "composite":          0.85
  },
  "segment_concentration": "Female, 22-35, urban, repeat buyers",
  "opportunity_statement": "Users who have identified a product they like frequently stall at purchase because they cannot trust that the listed size will fit — driven by inconsistency across brands and poor-quality size charts.",
  "representative_quotes": [
    {
      "verbatim":    "I always order an M from Zara but on Myntra I had to size up twice",
      "source_type": "reddit",
      "source_name": "r/IndianFashionAddicts",
      "url":         "https://..."
    }
  ],
  "rank": 1
}
```

---

## 5. Component Map

```
Engine
├── config/
│   ├── source_list.yaml          # Which sources to scrape, lookback window
│   ├── taxonomy.yaml             # Taxonomy nodes, detection rules, question mappings
│   ├── question_set.yaml         # The 10 behavioral questions
│   └── scoring_weights.yaml      # Priority score weights
│
├── scraper/
│   ├── connector_app_store       # Apple App Store adapter
│   ├── connector_play_store      # Google Play Store adapter
│   ├── connector_reddit          # Reddit API adapter
│   ├── connector_social          # Twitter/X, Instagram adapter
│   ├── connector_youtube         # YouTube Comments adapter
│   ├── connector_forum           # Fashion/shopping forums adapter
│   ├── connector_review_qa       # Myntra, AJIO review & Q&A adapter
│   ├── normalizer                # Converts source-specific schema → RawRecord
│   └── deduplicator              # Content fingerprinting & dedup
│
├── extractor/
│   ├── preprocessor              # Clean, tokenize, language detect
│   ├── taxonomy_matcher          # NLP / LLM-assisted signal detection
│   ├── signal_constructor        # Assembles Signal records
│   └── signal_store              # Persists Signal records
│
├── analyzer/
│   ├── signal_grouper            # Groups signals by taxonomy node
│   ├── cross_source_validator    # Filters single-source clusters
│   ├── opportunity_synthesizer   # Writes opportunity statements + picks quotes
│   ├── scorer                    # Frequency, severity, evidence strength scores
│   ├── ranker                    # Produces final ranked list
│   └── opportunity_store         # Persists OpportunityArea records
│
└── output/
    ├── report_builder            # Assembles final structured report
    └── export                    # JSON / Markdown / CSV export
```

---

## 6. Data Models

### Entity Relationship Summary

```
RawRecord (1) ─────────────────────── (N) Signal
    │                                        │
    │  source_ref preserved in Signal        │  taxonomy_node
    │                                        │
    └────────────────────────────────────────┘
                                             │
                                      (N) grouped into (1)
                                             │
                                      OpportunityArea
                                             │
                                       ranked in
                                             │
                                      FinalReport
```

| Entity | Purpose | Key Fields |
|---|---|---|
| `RawRecord` | Normalized raw text unit | record_id, source_type, text, date |
| `Signal` | Atomic behavioral observation | signal_id, taxonomy_node, verbatim_quote, source_ref, question_refs |
| `OpportunityArea` | Clustered, scored insight | opportunity_id, scores, signal_count, source_spread, rank |
| `FinalReport` | Ranked deliverable | question answers, ranked opportunities, metadata |

---

## 7. Configurability Layer

The engine's behavior is fully driven by four configuration files, making it domain-agnostic:

| Config File | Controls |
|---|---|
| `source_list.yaml` | Which platforms to scrape, lookback window, volume caps |
| `taxonomy.yaml` | Signal categories, detection rules, dimension labels, question mappings |
| `question_set.yaml` | The behavioral questions the report must answer |
| `scoring_weights.yaml` | Priority score weights (frequency / severity / evidence strength) |

**Changing the domain** (e.g., from fashion e-commerce to fintech onboarding) requires only updating these four files — the pipeline code itself does not change. This is the core architectural guarantee of generic reusability.

---

## 8. Quality & Integrity Controls

| Control | Mechanism |
|---|---|
| **Deduplication** | Content fingerprinting prevents double-counting the same post across runs |
| **Source Diversity Filter** | An Opportunity Area is only surfaced if signals appear across 2 or more independent sources |
| **Confidence Thresholding** | Signals below a configurable confidence threshold are flagged for review, not silently discarded |
| **Verbatim Traceability** | Every opportunity is backed by direct, auditable verbatim quotes with source URLs |
| **Freshness Window** | Configurable date filter ensures insights reflect current user behavior |
| **Segment Tagging** | Segment hints propagate from signals to opportunities, enabling segment-level validation in interviews |

---

## 9. Output Schema & Delivery

The engine produces a **structured, human-readable report** containing:

1. **Executive Summary** — ranked list of Opportunity Areas with composite scores
2. **Behavioral Question Answers** — for each of the 10 questions, the top supporting Opportunity Areas with evidence
3. **Opportunity Detail Cards** — for each Opportunity Area:
   - Title, dimension, score breakdown
   - Segment concentration note
   - Source spread table
   - Representative verbatim quotes with source links
4. **Raw Signal Appendix** — full signal log for audit and traceability

### Export Formats

| Format | Use Case |
|---|---|
| Markdown / PDF | Human consumption, stakeholder sharing |
| JSON | Downstream tooling, programmatic analysis |
| CSV | Quick filtering and sorting in spreadsheets |

---

## 10. Explicit Boundaries

| The Engine IS | The Engine IS NOT |
|---|---|
| A behavioral signal extraction and prioritization tool | A replacement for primary user research (interviews) |
| A cross-source evidence aggregator | A sentiment analysis tool |
| A source-traceable insight generator | A review summarization tool |
| A ranked opportunity prioritizer | A product decision-maker |

The output of this engine feeds **into** primary research (user interviews), not around it. Interviews remain the validation layer. The engine accelerates discovery; it does not replace judgment.

---

## 11. Alignment with Success Criteria

| Success Criterion | Architecture Element That Delivers It |
|---|---|
| Structured, source-traceable opportunity areas | `Signal.source_ref` → `OpportunityArea.representative_quotes` |
| Frequency / severity / evidence-strength scores | Scoring Dimensions in Stage 3 Scorer component |
| Answers to all 10 behavioral questions | `taxonomy_node.question_refs` → `OpportunityArea.question_answers` |
| Evidence-backed, not assumption-based | Verbatim quote traceability at every pipeline level |
| Faster than manual research | Automated three-stage pipeline runs without manual reading |
| Comparable, rankable opportunities | Composite Priority Score + Ranker component |
| Generic, not fashion-specific | Configurability Layer — taxonomy & question set are runtime inputs |

---

*This document reflects the architecture as designed for the graduation project anchor domain (fashion e-commerce / wishlist-to-purchase behavior). The pipeline generalizes to any behavioral question set and source list via the Configurability Laye