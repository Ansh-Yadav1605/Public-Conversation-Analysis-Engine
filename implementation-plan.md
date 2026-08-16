# Implementation Plan — Public Conversation Analysis Engine

> **Project:** Graduation Project — Product Management  
> **Domain:** Fashion E-commerce (Wishlist-to-Purchase Behavior)  
> **Platforms:** Myntra, AJIO, and public sources  
> **Reference Documents:** `context.md`, `architecture.md`  
> **Last Updated:** 2026-08-15

---

## Overview

This plan breaks the engine build into **5 sequential phases**, each with a clear goal, deliverables, tasks, and exit criteria. Phases are ordered so that each one produces a working, testable artifact before the next begins — avoiding a "big bang" integration at the end.

```
Phase 1 → Phase 2 → Phase 3 → Phase 4 → Phase 5
Config     Scraping   Extraction  Clustering   Output &
& Setup    Layer      Layer       & Scoring    Delivery
```

---

## Phase Summary Table

| Phase | Name | Core Deliverable | Key Risk |
|---|---|---|---|
| 1 | Foundation & Config | Config schema + taxonomy + question set | Taxonomy too narrow or too broad |
| 2 | Source Scraping Layer | Normalized RawRecord store from all 7 sources | Rate limits, anti-scraping blocks |
| 3 | Taxonomy-Based Extraction | Signal records with source traceability | Low extraction accuracy, over-matching |
| 4 | Opportunity Clustering & Scoring | Ranked OpportunityArea records | Spurious clusters, score calibration |
| 5 | Output, Delivery & Validation | Final structured report answering all 10 questions | Report does not answer questions with evidence |

---

## Phase 1 — Foundation & Configuration

### Goal
Establish the project structure, define the full configuration schema, build the taxonomy, and write the 10-question set. No scraping or ML yet — this phase is purely definitional and structural.

### Rationale
Everything downstream — scraping targets, signal detection, opportunity scoring — depends on the taxonomy and question set being well-defined first. A poorly specified taxonomy at this stage propagates errors through all later phases.

### Tasks

#### 1.1 Project Structure Setup
- [ ] Create the engine's top-level directory and module structure (as per Component Map in `architecture.md`)
- [ ] Set up a virtual environment and dependency management (`requirements.txt` or `pyproject.toml`)
- [ ] Initialize a local data store (SQLite or flat JSON/JSONL files) for RawRecords, Signals, and OpportunityAreas
- [ ] Set up a logging framework for pipeline run visibility

#### 1.2 Configuration Schema Design
- [ ] Define and document the schema for `source_list.yaml`
  - Fields: source_type, source_name, enabled (bool), lookback_days, volume_cap
- [ ] Define and document the schema for `taxonomy.yaml`
  - Fields: node_id, label, dimension, sub_category, question_refs, detection_rules (keywords list + embedding_hint)
- [ ] Define and document the schema for `question_set.yaml`
  - Fields: question_id (1–10), question_text, related_dimensions
- [ ] Define and document the schema for `scoring_weights.yaml`
  - Fields: w_frequency, w_severity, w_evidence_strength (must sum to 1.0)

#### 1.3 Taxonomy Build (Fashion E-commerce Anchor)
Build out the full taxonomy covering all 10 behavioral dimensions. For each node, define:
- Human-readable label
- 10–20 seed keywords / phrases
- Which of the 10 behavioral questions it maps to

**Dimensions to cover:**

| Dimension | Minimum Nodes | Maps to Questions |
|---|---|---|
| Fit & Sizing | 4 nodes | Q2, Q3, Q7 |
| Styling & Occasion | 3 nodes | Q1, Q3, Q7 |
| Price & Value | 4 nodes | Q2, Q4, Q7 |
| Trust & Reviews | 3 nodes | Q2, Q3, Q6 |
| Return & Risk | 2 nodes | Q2, Q4 |
| Social Validation | 3 nodes | Q1, Q7, Q8 |
| Product Information | 3 nodes | Q3, Q6, Q7 |
| Comparison Behavior | 2 nodes | Q5, Q6 |
| Intent Signal | 2 nodes | Q8, Q9 |
| Segment Markers | 3 nodes | Q9, Q10 |

#### 1.4 Question Set Finalization
- [ ] Formalize all 10 behavioral questions in `question_set.yaml` with `related_dimensions` mappings
- [ ] Confirm that every taxonomy dimension maps to at least one question (no orphan dimensions)
- [ ] Confirm that every question is covered by at least one taxonomy dimension (no unanswerable questions)

#### 1.5 Source List Configuration
- [ ] Populate `source_list.yaml` with all 7 source types enabled
- [ ] Set initial `lookback_days: 365` and `volume_cap` per source

### Deliverables
- [ ] Project directory structure initialized
- [ ] `config/source_list.yaml` — complete
- [ ] `config/taxonomy.yaml` — complete with all 10 dimensions, min 29 nodes, seed keywords, question mappings
- [ ] `config/question_set.yaml` — all 10 questions defined with dimension mappings
- [ ] `config/scoring_weights.yaml` — initial weights set (e.g., 0.4 / 0.35 / 0.25)

### Exit Criteria
- [ ] Taxonomy reviewed for coverage: every question answerable via at least one taxonomy path
- [ ] Config files are valid YAML and parseable without errors
- [ ] Peer review of taxonomy labels and seed keywords completed

---

## Phase 2 — Source Scraping Layer

### Goal
Build a connector/adapter for each of the 7 source types. Each connector fetches raw content, and a shared normalization layer converts it into a `RawRecord`. All records are deduplicated and stored.

### Rationale
Reliable, clean raw data is the foundation of signal quality. A bug in normalization at this stage (e.g., dropping text, losing source metadata) corrupts every downstream signal and opportunity.

### Tasks

#### 2.1 RawRecord Schema & Storage
- [ ] Implement the `RawRecord` data class / schema (as defined in `architecture.md` Section 4.1.3)
- [ ] Implement the local storage layer for RawRecords (JSONL file or SQLite table)
- [ ] Write a `record_exists(record_id)` function for deduplication checks

#### 2.2 Normalization Layer
- [ ] Implement `normalizer.py` — a shared function `normalize(source_type, raw_data) → RawRecord`
- [ ] Ensure all fields are populated or explicitly set to `null` (no missing fields)
- [ ] Write unit tests for normalization with mock raw data from each source type

#### 2.3 Source Connectors

Build one connector per source type. Each connector must:
- Accept source config from `source_list.yaml`
- Fetch data within the `lookback_days` window, up to `volume_cap`
- Return a list of source-native raw objects (pre-normalization)
- Handle rate limits and basic errors gracefully

| Connector | Method | Notes |
|---|---|---|
| **App Store Reviews** | `app-store-scraper` library or iTunes RSS API | Filter by app (Myntra, AJIO) |
| **Play Store Reviews** | `google-play-scraper` library | Filter by app ID |
| **Reddit** | Reddit API (PRAW) or Pushshift | Target relevant subreddits |
| **Fashion Forums / Communities** | HTML scraping (BeautifulSoup / Scrapy) | Site-specific, may need custom selectors |
| **Social Media (Twitter/X)** | Twitter API v2 (Basic tier) or scraper | Keyword + hashtag search |
| **YouTube Comments** | YouTube Data API v3 | Target haul/review/try-on videos |
| **Product Reviews & Q&A** | HTML scraping (Myntra, AJIO review pages) | May require pagination handling |

- [ ] `connector_app_store.py` — implemented and tested
- [ ] `connector_play_store.py` — implemented and tested
- [ ] `connector_reddit.py` — implemented and tested
- [ ] `connector_social.py` — implemented and tested
- [ ] `connector_youtube.py` — implemented and tested
- [ ] `connector_forum.py` — implemented and tested
- [ ] `connector_review_qa.py` — implemented and tested

#### 2.4 Deduplication
- [ ] Implement `deduplicator.py` — fingerprint = `hash(source_type + content_id + text[:200])`
- [ ] Deduplication runs before write; duplicate records are logged and skipped
- [ ] Cross-run deduplication: fingerprints persisted between runs

#### 2.5 Scraping Orchestrator
- [ ] Implement a `scraper/run.py` entry point that:
  - Reads `source_list.yaml`
  - Runs each enabled connector
  - Normalizes output
  - Deduplicates and writes to RawRecord store
  - Logs summary: records fetched, new records written, duplicates skipped

### Deliverables
- [ ] 7 working source connectors
- [ ] Shared normalization layer
- [ ] Deduplication logic
- [ ] Populated RawRecord store (target: 500–2000 records for initial test run)
- [ ] Scraping run summary log

### Exit Criteria
- [ ] All 7 connectors return non-empty results for the fashion/wishlist domain
- [ ] RawRecords from at least 5 distinct source types present in the store
- [ ] Zero duplicate records in the store after a full run
- [ ] Spot-check: 20 random records manually inspected — text is clean, source_ref is accurate

---

## Phase 3 — Taxonomy-Based Extraction Layer

### Goal
Process every RawRecord through the extraction pipeline to produce `Signal` records — discrete, taxonomy-tagged, source-traced behavioral observations.

### Rationale
This is the core intelligence layer. The accuracy of signal extraction directly determines the quality of opportunities. Over-matching creates noise; under-matching creates blind spots. Both undermine the product team's ability to trust the output.

### Tasks

#### 3.1 Signal Schema & Storage
- [ ] Implement the `Signal` data class / schema (as defined in `architecture.md` Section 4.2.4)
- [ ] Implement the local storage layer for Signals
- [ ] Link Signals back to RawRecords via `record_id`

#### 3.2 Text Preprocessor
- [ ] Implement `preprocessor.py`:
  - Strip HTML tags, URLs, emojis (or normalize emojis to text)
  - Language detection — filter to English (or the target language)
  - Tokenize and sentence-split for multi-signal detection
  - Preserve original text alongside cleaned text

#### 3.3 Taxonomy Matcher

Implement detection in two layers (start simple, add sophistication as needed):

**Layer A — Keyword/Rule Matching (implement first):**
- [ ] Load taxonomy from `taxonomy.yaml`
- [ ] For each sentence in a RawRecord, check against keyword sets for each taxonomy node
- [ ] Return all matching nodes for that sentence

**Layer B — Embedding Similarity (implement second):**
- [ ] Embed each sentence using a sentence-transformer model (e.g., `all-MiniLM-L6-v2`)
- [ ] Embed each taxonomy node using its label + seed keywords
- [ ] For sentences with no keyword match, compute cosine similarity and flag nodes above a threshold (e.g., 0.65)
- [ ] Assign confidence score based on match type: keyword match = 0.90, embedding match = similarity score

**Optional Layer C — LLM Classification (if accuracy is insufficient after Layer B):**
- [ ] Prompt an LLM (GPT-4o, Gemini, Claude — TBD) with: taxonomy node definitions + sentence → classification
- [ ] Use only for ambiguous cases to control cost
- [ ] Store model used + prompt version for reproducibility

#### 3.4 Signal Constructor
- [ ] For each (RawRecord, matched taxonomy node) pair, construct one `Signal` record:
  - Extract `verbatim_quote`: the exact sentence(s) that triggered the match
  - Populate `severity_hint` using intensity keywords (e.g., "never", "always", "hate", "frustrated" → high)
  - Extract `segment_hints` from author_meta and surrounding text
  - Populate `question_refs` from the taxonomy node's `question_refs` field
  - Set `confidence` based on match layer

#### 3.5 Extraction Orchestrator
- [ ] Implement `extractor/run.py`:
  - Reads all unprocessed RawRecords from the store
  - Runs preprocessor → taxonomy matcher → signal constructor
  - Writes Signal records to store
  - Logs: records processed, signals extracted, average signals per record, low-confidence count

### Deliverables
- [ ] Text preprocessor
- [ ] Taxonomy matcher (Layer A keyword, Layer B embedding)
- [ ] Signal constructor
- [ ] Populated Signal store (target: 1,000–5,000 signals from test run corpus)
- [ ] Extraction run log

### Exit Criteria
- [ ] At least 8 of 10 taxonomy dimensions have signals present
- [ ] Average signal confidence ≥ 0.70
- [ ] Manual spot-check of 50 signals: verbatim quote is relevant to the assigned taxonomy node in ≥ 85% of cases
- [ ] All 7 source types represented in the Signal store
- [ ] Multi-signal extraction verified: at least 10% of RawRecords produce ≥ 2 signals

---

## Phase 4 — Opportunity Clustering & Scoring

### Goal
Group signals into **Opportunity Areas**, score them on frequency/severity/evidence-strength, and produce a ranked, comparable list that maps directly to the 10 behavioral questions.

### Rationale
This phase transforms a flat list of thousands of signals into a small number (10–25) of actionable, comparable insights. The quality of clustering and scoring determines whether the product team gets a genuinely useful prioritization or a noisy, untrusted list.

### Tasks

#### 4.1 OpportunityArea Schema & Storage
- [ ] Implement the `OpportunityArea` data class / schema (as defined in `architecture.md` Section 4.3.5)
- [ ] Implement the local storage layer for OpportunityAreas

#### 4.2 Signal Grouper
- [ ] Group signals by `taxonomy_node` (primary grouping)
- [ ] Merge sibling nodes under the same dimension where signal counts warrant (e.g., `fit_sizing.inconsistent_sizing` + `fit_sizing.size_uncertainty` → combined cluster)
- [ ] Output: a list of candidate clusters, each with a list of Signal records

#### 4.3 Cross-Source Validator
- [ ] For each candidate cluster, count distinct `source_type` values
- [ ] **Threshold:** a cluster must appear in ≥ 2 distinct source types to proceed to scoring
- [ ] Clusters failing this filter are logged as "insufficient cross-source evidence" — not surfaced in output
- [ ] Rationale: prevents surfacing issues that are artifacts of a single platform's culture

#### 4.4 Opportunity Synthesizer
- [ ] For each validated cluster:
  - Write a one-sentence **opportunity statement** (template: *"[Segment] [stalls/hesitates/abandons] because [root cause], as evidenced by [signal pattern]"*)
  - Select 3–5 **representative verbatim quotes** (prioritize: high confidence + diverse sources)
  - Populate `question_answers` from the union of `question_refs` across all signals in the cluster

#### 4.5 Scorer
Implement the scoring logic for each Opportunity Area:

| Score | Formula / Logic |
|---|---|
| **Frequency Score** | `min(signal_count / max_signal_count_in_run, 1.0)` — normalized 0–1 |
| **Severity Score** | `weighted_avg(signal.severity_hint)` where high=1.0, medium=0.6, low=0.3, unknown=0.5 |
| **Evidence Strength Score** | `(distinct_source_types / 7) * avg_confidence_in_cluster` |
| **Composite Score** | `w1 * frequency + w2 * severity + w3 * evidence_strength` (weights from `scoring_weights.yaml`) |

- [ ] Implement `scorer.py` with all four score computations
- [ ] Compute `segment_concentration` from the most frequent `segment_hints` across cluster signals

#### 4.6 Ranker
- [ ] Sort OpportunityAreas by `composite_score` descending
- [ ] Assign `rank` (1 = highest priority)
- [ ] Implement `ranker.py`

#### 4.7 Clustering Orchestrator
- [ ] Implement `analyzer/run.py`:
  - Reads all Signals
  - Runs grouper → validator → synthesizer → scorer → ranker
  - Writes OpportunityAreas to store
  - Logs: candidate clusters, clusters filtered, final opportunity count, top-5 by score

### Deliverables
- [ ] Signal Grouper
- [ ] Cross-Source Validator
- [ ] Opportunity Synthesizer
- [ ] Scorer (all 4 scoring dimensions)
- [ ] Ranker
- [ ] Populated OpportunityArea store (target: 10–25 ranked opportunities)

### Exit Criteria
- [ ] ≥ 10 opportunity areas surfaced with composite scores
- [ ] Every opportunity area has ≥ 3 verbatim quotes with source links
- [ ] Every opportunity area covers signals from ≥ 2 source types
- [ ] All 10 behavioral questions are answered by at least one opportunity area
- [ ] Manual review: top-5 ranked opportunities are intuitively credible given domain knowledge

---

## Phase 5 — Output, Delivery & Validation

### Goal
Assemble the final structured report in all three export formats, validate it against the 10 behavioral questions and success criteria, and prepare the deliverable for use in primary research (user interviews).

### Tasks

#### 5.1 Report Builder
- [ ] Implement `output/report_builder.py` that assembles:

**Section 1 — Executive Summary**
  - Ranked table of all Opportunity Areas (title, dimension, composite score, signal count, source spread)

**Section 2 — Behavioral Question Answers**
  - For each of the 10 questions: the top 2–3 Opportunity Areas that answer it, with evidence summary

**Section 3 — Opportunity Detail Cards**
  - One card per Opportunity Area containing:
    - Title + opportunity statement
    - Score breakdown table (frequency / severity / evidence strength / composite)
    - Segment concentration
    - Source spread table
    - 3–5 representative verbatim quotes with source name + URL

**Section 4 — Raw Signal Appendix**
  - Full signal log (signal_id, taxonomy_node, verbatim_quote, source URL, confidence) for audit

#### 5.2 Export Module
- [ ] Implement `output/export.py` with three exporters:
  - `to_markdown(report) → .md file` — human-readable, stakeholder-facing
  - `to_json(report) → .json file` — structured, machine-readable
  - `to_csv(opportunities) → .csv file` — for filtering/sorting in spreadsheets

#### 5.3 Full Pipeline Run
- [ ] Implement `run_pipeline.py` — a single entry point that runs Phase 2 → 3 → 4 → 5 in sequence
- [ ] Add a `--dry-run` flag that runs extraction on a 10% sample for fast iteration
- [ ] Add total pipeline runtime logging

#### 5.4 Validation Against Success Criteria
Run the following checks on the generated report:

| Check | Pass Condition |
|---|---|
| All 10 questions answered | Section 2 has a non-empty answer for every question |
| Source traceability | Every opportunity in Section 3 has ≥ 3 quotes with valid source URLs |
| Frequency / severity / evidence scores present | All three sub-scores populated for every opportunity |
| Cross-source evidence | Every opportunity spans ≥ 2 source types |
| Report generated faster than manual | Full run completes within 4 hours on a standard laptop |
| Domain-agnostic config confirmed | Run pipeline with a dummy taxonomy/question set for a different domain — same code, different config |

#### 5.5 Stakeholder Review Prep
- [ ] Export Markdown report
- [ ] Write a 1-page "How to read this report" guide for non-technical stakeholders
- [ ] Annotate top-5 opportunity areas with notes on which to prioritize for interview recruitment

### Deliverables
- [ ] `output/report_builder.py`
- [ ] `output/export.py`
- [ ] `run_pipeline.py` (full pipeline entry point)
- [ ] Final report in Markdown, JSON, and CSV formats
- [ ] Validation checklist completed (all checks passing)
- [ ] "How to read this report" one-pager

### Exit Criteria
- [ ] All 10 behavioral questions answered with real evidence in the report
- [ ] Top opportunity areas have verbatim quotes from ≥ 3 distinct source types
- [ ] Report reviewed by at least one other person — insights are credible and traceable
- [ ] Pipeline runs end-to-end from raw scrape to final report without manual intervention

---

## Cross-Phase Decisions & Open Questions

| Decision | Options | Recommended | Notes |
|---|---|---|---|
| **LLM for extraction** | GPT-4o, Gemini 1.5 Pro, Claude Sonnet, Llama 3 (local) | TBD | Start with keyword + embedding (Layers A+B). Add LLM only if accuracy is insufficient after Phase 3 exit review. |
| **Data storage** | SQLite, JSONL flat files, PostgreSQL | JSONL for Phase 2–3, SQLite for Phase 4–5 | Keeps the setup simple for a graduation project. |
| **Embedding model** | `all-MiniLM-L6-v2`, `bge-small-en`, OpenAI `text-embedding-3-small` | `all-MiniLM-L6-v2` (local, free) | Avoids API dependency for embedding; good accuracy for classification tasks. |
| **Social media scraping** | Official API vs. scraper libraries | Official API where available | Twitter API Basic tier has volume limits; factor into `volume_cap` config. |
| **Language scope** | English only vs. multi-lingual | English only (Phase 1) | Myntra/AJIO reviews are predominantly English; Hindi/Hinglish can be added later. |

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Anti-scraping blocks on Myntra/AJIO | High | High | Use rate limiting, user-agent rotation, and respect `robots.txt`; fall back to publicly available review datasets if blocked |
| Taxonomy too broad → noisy signals | Medium | High | Tight keyword sets in Phase 1; strict confidence threshold in Phase 3 |
| Taxonomy too narrow → missing signals | Medium | High | Manual spot-check of 50 RawRecords in Phase 3 to catch unmatched relevant text |
| Low cross-source signal for some opportunities | Medium | Medium | Cross-source filter threshold (≥ 2 sources) may be lowered to 1.5 (weighted) if data is sparse |
| LLM API costs exceed budget | Low | Medium | Default to keyword + embedding only; use LLM only for a sampled validation pass |
| Insufficient data volume from some sources | Medium | Medium | Volume caps per source can be raised; Reddit is the highest-volume fallback |

---

## Timeline Estimate

| Phase | Estimated Duration | Dependencies |
|---|---|---|
| Phase 1 — Foundation & Config | 3–5 days | None |
| Phase 2 — Source Scraping | 7–10 days | Phase 1 complete |
| Phase 3 — Extraction Layer | 7–10 days | Phase 2 complete (≥ 500 records) |
| Phase 4 — Clustering & Scoring | 5–7 days | Phase 3 complete (≥ 1,000 signals) |
| Phase 5 — Output & Delivery | 3–5 days | Phase 4 complete |
| **Total** | **25–37 days** | Sequential execution |

---

## Definition of Done

The engine is complete when:

1. A full pipeline run — scrape → extract → cluster → score → report — completes without manual intervention.
2. The output report contains a **ranked, evidence-tagged set of opportunity areas**.
3. All **10 behavioral questions** are answered with real verbatim evidence.
4. Every opportunity is backed by signals from **≥ 2 independent source types**.
5. A **non-technical stakeholder** can read the Markdown report and understand the top 5 opportunities without additional context.
6. The engine produces equivalent output for a **different domain** by swapping only the 4 config files.

---

*This plan follows the architecture defined in `architecture.md`. Each phase exit criteria must be met before the next phase begins. Phases 2–4 may iterate internally (re-running with refined config) without resetting the phase.*
