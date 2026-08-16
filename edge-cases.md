# Edge Cases — Public Conversation Analysis Engine

> **Project:** Graduation Project — Product Management
> **Domain:** Fashion E-commerce (Wishlist-to-Purchase Behavior)
> **Reference Documents:** `context.md`, `architecture.md`, `implementation-plan.md`
> **Last Updated:** 2026-08-15

---

## Purpose

This document catalogs all known corner cases, boundary conditions, and failure scenarios across every stage of the pipeline. Each entry defines the scenario, its impact if unhandled, and the recommended handling strategy. This is a living reference — new edge cases discovered during implementation should be added here.

---

## Table of Contents

1. [Configuration Layer Edge Cases](#1-configuration-layer-edge-cases)
2. [Stage 1 — Source Scraping Edge Cases](#2-stage-1--source-scraping-edge-cases)
3. [Stage 2 — Taxonomy-Based Extraction Edge Cases](#3-stage-2--taxonomy-based-extraction-edge-cases)
4. [Stage 3 — Opportunity Clustering & Scoring Edge Cases](#4-stage-3--opportunity-clustering--scoring-edge-cases)
5. [Output & Delivery Edge Cases](#5-output--delivery-edge-cases)
6. [Cross-Cutting / System-Wide Edge Cases](#6-cross-cutting--system-wide-edge-cases)
7. [Domain-Specific Edge Cases (Fashion E-commerce)](#7-domain-specific-edge-cases-fashion-e-commerce)

---

## 1. Configuration Layer Edge Cases

### EC-C01 — Taxonomy Node With No Seed Keywords
**Scenario:** A taxonomy node is defined in `taxonomy.yaml` but its keyword list is empty or contains only stopwords.
**Impact:** The matcher never fires for that node, silently creating a blind spot. No error is raised.
**Handling:** Validate all taxonomy nodes at startup — reject any node with fewer than 3 non-stopword keywords. Log a warning and halt pipeline if validation fails.

---

### EC-C02 — Behavioral Question With No Taxonomy Mapping
**Scenario:** One of the 10 behavioral questions in `question_set.yaml` has no `related_dimensions` entry, or all mapped dimensions have no taxonomy nodes.
**Impact:** That question will produce zero opportunity answers in the final report. The report fails its own success criteria silently.
**Handling:** At startup, validate that every question ID maps to at least one active taxonomy node. Raise a configuration error if any question is unmapped.

---

### EC-C03 — Scoring Weights Do Not Sum to 1.0
**Scenario:** `scoring_weights.yaml` has `w1 + w2 + w3 ≠ 1.0` due to a typo (e.g., `0.4 + 0.4 + 0.4 = 1.2`).
**Impact:** Composite scores exceed 1.0, breaking ranking comparability and any downstream normalization.
**Handling:** Validate weights at startup. Either auto-normalize (divide each weight by the sum) or raise a configuration error. Log which option was taken.

---

### EC-C04 — Source Disabled But Signals Expected From It
**Scenario:** A source type is set to `enabled: false` in `source_list.yaml`, but it is the primary source for signals answering a specific question.
**Impact:** That question may be unanswerable in the final report; the cross-source validator may also reject valid clusters due to missing source diversity.
**Handling:** At startup, check whether any question's taxonomy nodes rely exclusively on a disabled source. Log a warning identifying which questions may have reduced evidence.

---

### EC-C05 — Taxonomy Node Maps to a Non-Existent Question ID
**Scenario:** A taxonomy node references `question_refs: [11]` but only questions 1–10 exist.
**Impact:** Signal records carry invalid `question_refs`, corrupting the question-answer mapping in the report.
**Handling:** Validate all `question_refs` in taxonomy nodes against the active question set at startup. Reject any node referencing an out-of-range question ID.

---

### EC-C06 — Duplicate Taxonomy Node IDs
**Scenario:** Two taxonomy nodes share the same `node_id` in `taxonomy.yaml`.
**Impact:** One silently overwrites the other during loading, causing signals to be mis-tagged.
**Handling:** Detect and reject duplicate `node_id` values at config load time with an explicit error.

---

## 2. Stage 1 — Source Scraping Edge Cases

### EC-S01 — Source Returns Zero Records
**Scenario:** A connector runs successfully (no error) but returns 0 records — e.g., the subreddit has no posts in the lookback window, or the app has no reviews in that period.
**Impact:** Silent gap in data. Downstream stages are unaware a source contributed nothing.
**Handling:** Log a `WARN: zero records returned from [source_name]` after each connector run. If all sources return zero, halt the pipeline with an explicit error.

---

### EC-S02 — Source Returns Only Metadata, Text Field Is Empty
**Scenario:** A scraper fetches a review or comment record where the `text` field is null, whitespace-only, or contains only an emoji.
**Impact:** Empty records pass into the RawRecord store and waste processing in Stage 2.
**Handling:** In the normalization layer, reject any record where `len(clean(text)) < 10`. Log count of rejected empty records per source.

---

### EC-S03 — Rate Limiting / HTTP 429 Mid-Scrape
**Scenario:** A source's API or website returns HTTP 429 (Too Many Requests) after partial data collection, mid-run.
**Impact:** Run terminates early. Partial data from that source is inconsistent — some pages scraped, others not.
**Handling:** Implement exponential backoff with a configurable `max_retries` (default: 3). On final failure, persist a checkpoint of the last successfully fetched page/cursor and resume from there on the next run.

---

### EC-S04 — Source Structure Changes (HTML Scraping Breaks)
**Scenario:** Myntra or AJIO updates their review page DOM structure, breaking the CSS selectors used by the connector.
**Impact:** Connector returns zero records or malformed records with no error raised.
**Handling:** Validate that scraped records contain expected fields after normalization. Alert when a previously active source drops to zero records across 2 consecutive runs. Document selectors with their last-verified date.

---

### EC-S05 — Duplicate Records Across Sources
**Scenario:** A user's review is cross-posted — e.g., the same text appears in a Google Play review and a screenshot quoted in a Reddit post.
**Impact:** The same signal is counted twice, inflating frequency scores.
**Handling:** Deduplication fingerprinting covers same-source duplicates. For cross-source duplicates, apply fuzzy text matching (e.g., Jaccard similarity > 0.85 on trigrams) during the normalization step. Log detected cross-source duplicates.

---

### EC-S06 — Very Long Records (Wall-of-Text Reviews)
**Scenario:** A record contains an unusually long review — 2,000+ words — covering many unrelated topics.
**Impact:** Single-signal detection may miss signals buried deep in the text; processing time increases significantly.
**Handling:** Apply a `max_record_length` cap (e.g., 2,000 tokens). Records exceeding this are sentence-segmented and processed as multiple sub-records, each with the same `record_id` and a `segment_index` suffix.

---

### EC-S07 — Non-English Records
**Scenario:** A connector returns records in Hindi, Tamil, Hinglish (Hindi-English code-switching), or other languages.
**Impact:** The English-tuned taxonomy matcher produces no matches or false positives.
**Handling:**
- **Pure Hindi/Tamil:** Filter out using language detection (`langdetect` or `fasttext`). Log count of filtered non-English records.
- **Hinglish:** Flag as `language: hinglish` and retain. Apply keyword matching only (not embedding similarity) since embedding models are less reliable for code-switched text. Track separately in run logs.

---

### EC-S08 — Records From Bot Accounts / Spam Reviews
**Scenario:** A source contains reviews or comments that are bot-generated, templated spam, or incentivized fake reviews (e.g., "Great product, 5 stars!" repeated 50 times with minor variation).
**Impact:** Inflated frequency scores for generic positive signals; drowns out genuine behavioral signals.
**Handling:**
- Flag records with text similarity > 0.90 to 3 or more other records from the same source as `is_suspect: true`.
- Suspect records are processed but their signals receive a `confidence` penalty of -0.3.
- Count of suspect records reported in run log.

---

### EC-S09 — API Authentication Failure
**Scenario:** A stored API key (Reddit, YouTube, Twitter) expires or is revoked mid-project.
**Impact:** That connector returns an auth error. If uncaught, the pipeline either halts or proceeds with silently missing data.
**Handling:** Each connector must catch auth errors specifically (HTTP 401/403), log them as `ERROR: auth failure on [source_name]`, and continue with other sources. Auth errors are surfaced prominently in the run summary.

---

### EC-S10 — `volume_cap` Reached Too Quickly (Skewed Sample)
**Scenario:** A high-volume source (e.g., Play Store) hits its `volume_cap` after fetching only the most recent 200 reviews, all from the past week — missing older, long-tail signals.
**Impact:** The sample is time-biased toward recency, potentially missing seasonal patterns or older unresolved issues.
**Handling:** Distribute fetches across the full `lookback_days` window using date-range chunking, not recency-first pagination. Ensure the sample spans the full time window before hitting the cap.

---

## 3. Stage 2 — Taxonomy-Based Extraction Edge Cases

### EC-E01 — One Record Yields Zero Signal Matches
**Scenario:** A RawRecord is processed but no taxonomy node matches — the text discusses something outside the taxonomy scope (e.g., a delivery complaint, a packaging comment).
**Impact:** The record contributes nothing to the signal store. If this is common, meaningful signals are being missed.
**Handling:**
- Log all zero-match records in a `unmatched_records.log`.
- After a full run, review a random sample of 20 unmatched records. If ≥ 30% contain clearly relevant content, the taxonomy has gaps — add new nodes.
- Do not treat zero-match as an error; treat it as a diagnostic signal.

---

### EC-E02 — One Record Yields an Unusually High Number of Signals (Signal Explosion)
**Scenario:** A single long-form Reddit thread comment yields 15+ taxonomy matches, many of which are low-confidence or spurious.
**Impact:** That one record disproportionately inflates frequency scores for multiple opportunity areas.
**Handling:** Cap signals per record at `max_signals_per_record` (configurable, default: 8). When the cap is hit, retain the 8 highest-confidence signals. Log records that hit the cap.

---

### EC-E03 — Same Text Span Matches Multiple Taxonomy Nodes
**Scenario:** The phrase *"I wasn't sure if it would fit my body type for a formal event"* matches both `Fit & Sizing` and `Styling & Occasion` nodes simultaneously.
**Impact:** This is a legitimate multi-signal case — both signals are valid. However, if handled incorrectly, it could create spurious co-occurrence inflation.
**Handling:** This is expected and correct behavior. Both signals should be created. The verbatim quote for each will be the same sentence — that is intentional and traceable. Document this in the data model as "a quote may appear in multiple Signal records."

---

### EC-E04 — Negation Flipping Signal Meaning
**Scenario:** *"I had NO issue with sizing on Myntra"* triggers a keyword match on "sizing" and is tagged as a `Fit & Sizing` concern — but it is actually a positive signal.
**Impact:** A positive experience is incorrectly counted as a barrier, inflating severity for that opportunity.
**Handling:**
- Implement a negation detector: if a keyword match occurs within 3 tokens of a negation word ("no", "not", "never", "without", "zero issues"), apply a `negation_flag: true` to the signal.
- Negated signals are retained in the store but tagged. They are **excluded from severity scoring** and surfaced separately as "counter-signals" in the report.

---

### EC-E05 — Irony and Sarcasm
**Scenario:** *"Oh great, another size that 'fits' only if you're a mannequin."* — sarcastic, but the keyword matcher reads it as a neutral sizing mention.
**Impact:** Sarcastic mentions of positive outcomes are incorrectly categorized as low-severity when they may be high-severity frustrations.
**Handling:**
- Flag records containing sarcasm markers (e.g., quotation marks around adjectives, "oh great", "just wonderful", excessive punctuation like `!!!!`) for manual review or LLM reclassification.
- In Phase 3 (keyword + embedding only), these are logged but not corrected automatically. LLM layer (if activated) should handle sarcasm natively.

---

### EC-E06 — Comparative Mentions That Are Not About the Platform
**Scenario:** *"Zara's sizing is so much better than what I get on Myntra."* — this mentions Myntra but the signal is actually about cross-brand comparison behavior.
**Impact:** May be mis-tagged as a platform-trust signal rather than a comparison-behavior signal.
**Handling:** The `Comparison Behavior` taxonomy node should have "better than", "compared to", "versus", "prefer X over Y" as seed keywords. The presence of a competitor brand name alongside a comparison keyword should boost confidence for the `Comparison Behavior` node specifically.

---

### EC-E07 — Question-Form Text (No Clear Signal Direction)
**Scenario:** *"Does anyone know if Myntra's size chart is accurate for western wear?"* — this is a question, not a statement of experience.
**Impact:** The question signals uncertainty but provides no evidence of actual behavior or barrier. If treated as a barrier signal, severity is inflated.
**Handling:** Detect question-form sentences (ends with `?` or begins with `Does/Do/Is/Are/How/What/Why`). Tag such signals with `signal_type: question` rather than `signal_type: observation`. Questions are counted in frequency but contribute `severity_hint: low` by default, overriding any intensity keywords.

---

### EC-E08 — Generic Praise / Generic Complaints Without Behavioral Signal
**Scenario:** *"Worst app ever"* or *"Love Myntra!"* — emotional but content-free. No behavioral insight, no specific barrier or motivation.
**Impact:** These match broad keyword patterns ("worst", "love") but carry no diagnostic value.
**Handling:** Apply a minimum `verbatim_quote` length of 15 words for a signal to be stored. Signals extracted from quotes shorter than 15 words are flagged as `low_information: true` and excluded from opportunity scoring. They are logged for volume context only.

---

### EC-E09 — Mentions of Resolved Issues (Historical, Not Current)
**Scenario:** *"Myntra used to have terrible sizing but they've really improved in the last year."* — the barrier existed but is resolved.
**Impact:** Counts as a sizing barrier signal despite the behavior being resolved. Inflates frequency of an opportunity that may no longer exist.
**Handling:** Detect resolution markers ("used to", "earlier", "previously", "improved", "fixed", "now it's better"). Tag such signals `resolution_flag: true`. Resolution-flagged signals are counted in frequency at 0.5 weight and excluded from severity scoring. Surfaced as a footnote in the opportunity card.

---

### EC-E10 — Extracted Signal Has No Verbatim Quote
**Scenario:** The taxonomy matcher fires on a record but the signal constructor cannot isolate the triggering sentence (e.g., the match spanned a sentence boundary).
**Impact:** Signal is created with an empty or truncated `verbatim_quote`, making it non-traceable and invalid for the report.
**Handling:** A signal with `len(verbatim_quote) < 10` is rejected and logged. The record is flagged for manual review. Never store a signal without a usable verbatim quote.

---

## 4. Stage 3 — Opportunity Clustering & Scoring Edge Cases

### EC-O01 — All Signals for a Cluster Come From One Source Type
**Scenario:** 90 signals about "return policy friction" exist, but all 90 come from Reddit. No app store, play store, or review data corroborates it.
**Impact:** The cross-source validator correctly rejects this cluster. However, the issue may still be real — it's just not cross-validated.
**Handling:**
- Block the cluster from the main ranked output (as designed).
- Surface it in a separate **"Single-Source Observations"** appendix in the report, clearly labeled as unvalidated.
- Note the source and signal count so the product team can decide whether to treat it as a hypothesis for interview probing.

---

### EC-O02 — Two Taxonomy Nodes Produce Near-Identical Opportunity Areas
**Scenario:** `fit_sizing.size_uncertainty` and `fit_sizing.inconsistent_sizing` both produce high-signal clusters with very similar opportunity statements.
**Impact:** The ranked list contains redundant entries, giving the product team a misleading impression of two separate problems when it is one.
**Handling:**
- The Signal Grouper should merge sibling nodes under the same dimension by default (as described in Phase 4 of the implementation plan).
- After merging, if two Opportunity Areas still have > 70% shared signal_ids, flag them as `potential_duplicates` and surface only the higher-scoring one. The other is noted as a variant.

---

### EC-O03 — An Opportunity Area Has a Very High Signal Count But Low Source Spread
**Scenario:** 500 signals for "price hesitation" but 480 come from one subreddit. Source diversity score is artificially low despite high volume.
**Impact:** The composite score underweights a genuinely important opportunity due to source concentration.
**Handling:**
- Distinguish between **source type diversity** (the 7 types) and **source instance diversity** (different subreddits, different apps).
- Use source type spread (not instance count) as the primary diversity metric, as designed.
- A single subreddit still counts as "Reddit" source type — the cross-source validator passes it if ≥ 1 other source type also has signals. High volume from one subreddit is not penalized.

---

### EC-O04 — Composite Score Ties
**Scenario:** Two Opportunity Areas have identical composite scores (e.g., both score 0.72). Rank assignment is ambiguous.
**Impact:** Ranking is non-deterministic; the same run may produce different rank orders on different machines.
**Handling:** Define a deterministic tie-breaking rule: on equal composite score, rank by `signal_count` descending; on further tie, rank by `source_spread` (number of distinct source types) descending; on further tie, rank alphabetically by `opportunity_id`. Document this rule.

---

### EC-O05 — Zero Opportunities Survive the Cross-Source Validator
**Scenario:** Every candidate cluster fails the ≥ 2 source type threshold. This happens if the scraper only successfully fetched data from one source type (e.g., Reddit only, due to auth failures elsewhere).
**Impact:** The pipeline produces zero ranked opportunities. The report is empty.
**Handling:**
- Detect this at the end of Stage 3 before output is generated.
- Halt with a clear error: `"PIPELINE HALTED: 0 opportunities passed cross-source validation. Check source coverage in scraping log."`
- Do not generate an empty report — an empty report is more dangerous than a halt (a reader might interpret absence of opportunities as absence of problems).

---

### EC-O06 — Severity Score Denominator Is Zero
**Scenario:** All signals in a cluster have `severity_hint: unknown`. The severity score formula returns 0.0 (or NaN if division by zero occurs).
**Impact:** The composite score is artificially suppressed. A genuine, high-frequency opportunity appears low-priority.
**Handling:** Treat `severity_hint: unknown` as 0.5 (neutral) in the weighted average, not as 0.0. This prevents collapse and accurately reflects that severity is unknown, not absent. Log clusters where > 80% of signals have unknown severity.

---

### EC-O07 — A Segment Is Over-Represented in Signals, Skewing Concentration
**Scenario:** 70% of signals for an opportunity come from records where `segment_hints` contains "female". The segment concentration is reported as "Female" — but this may simply reflect that women post more reviews, not that the issue is female-specific.
**Impact:** A product team may incorrectly design a female-specific intervention for a gender-neutral problem.
**Handling:**
- Report segment concentration alongside the **base rate** of that segment in the overall signal store (e.g., "Female: 70% of cluster signals vs. 65% base rate in corpus — marginally concentrated").
- Only flag a segment as "concentrated" if its share in the cluster exceeds its base rate by > 15 percentage points.

---

### EC-O08 — Opportunity Statement Synthesis Fails (LLM / Template Error)
**Scenario:** The opportunity synthesizer produces a malformed, truncated, or nonsensical opportunity statement (e.g., LLM hallucination, template variable left unfilled).
**Impact:** The final report contains unreadable opportunity cards.
**Handling:**
- Validate synthesized statements: minimum 20 words, must contain subject + verb. If validation fails, fall back to a structured template: `"[signal_count] signals across [source_count] source types indicate [dimension] as a barrier, particularly around [top_sub_category]."` This template always renders correctly.

---

### EC-O09 — No Representative Quotes Available After Filtering
**Scenario:** An opportunity cluster has 50 signals, but after applying quality filters (min quote length, negation exclusion, low-information exclusion), fewer than 3 quotes remain.
**Impact:** Opportunity card cannot meet the minimum 3-quote requirement, compromising evidence traceability.
**Handling:** Progressively relax filters in order: (1) allow quotes with `low_information: true`, (2) allow `negation_flag: true` quotes with a label ("counter-signal"), (3) allow quotes from suspect records (with a disclaimer). If still < 1 quote, the opportunity is blocked from the final report.

---

## 5. Output & Delivery Edge Cases

### EC-OUT01 — Behavioral Question Answered by Zero Opportunity Areas
**Scenario:** After ranking, question Q5 ("How do users compare multiple shortlisted products?") maps to zero surfaced opportunities (all comparison clusters failed cross-source validation).
**Impact:** The final report has a blank answer for Q5, violating the success criteria.
**Handling:**
- In the Question Answers section, flag unanswered questions explicitly: `"Q5: Insufficient cross-source evidence collected in this run. Possible gap in source coverage or taxonomy."`
- Never leave a question silently absent — every question must have either an evidence-backed answer or an explicit "insufficient evidence" flag.

---

### EC-OUT02 — Markdown Report Contains Broken Source URLs
**Scenario:** A source URL stored during scraping has since changed (content deleted, page moved) or was malformed at scrape time.
**Impact:** A stakeholder clicks a quote's source link and gets a 404. Evidence traceability is broken.
**Handling:**
- Validate all stored URLs at scrape time using a HEAD request. Flag URLs returning non-2xx as `url_status: unreachable` at the time of collection.
- In the report, unreachable URLs are rendered with a footnote: *"[URL unavailable at time of report generation. Archived text retained.]"*
- Consider storing a snapshot of the verbatim text even if the URL dies — the quote itself is the evidence.

---

### EC-OUT03 — Report File Size Becomes Unmanageable
**Scenario:** The Raw Signal Appendix contains 10,000+ signals, making the Markdown file > 50MB — too large to open in most editors or share via email.
**Impact:** The report is technically complete but practically unusable.
**Handling:**
- Cap the Raw Signal Appendix at 500 entries in the Markdown/PDF export (highest-confidence signals first).
- The full signal log is always exported as a separate `signals_full.json` / `signals_full.csv` file, referenced in the appendix with: *"Full signal log: signals_full.csv ([N] total signals)"*.

---

### EC-OUT04 — JSON Export Contains Non-Serializable Fields
**Scenario:** Signal or Opportunity records contain Python `datetime` objects, `float('nan')`, or `Infinity` values that break JSON serialization.
**Impact:** The JSON export fails or produces malformed output consumed by downstream tools.
**Handling:** All data classes must implement a `to_dict()` method that explicitly serializes dates to ISO-8601 strings and replaces `NaN`/`Infinity` with `null`. Run a JSON validity check (`json.loads(json.dumps(obj))`) on all exports before writing to file.

---

### EC-OUT05 — Report Generated Before Pipeline Fully Completes
**Scenario:** A partial pipeline run (e.g., Stage 3 crashes halfway) leaves a stale `opportunities.json` on disk. The report builder picks it up and generates a report from incomplete data.
**Impact:** The report reflects partial results without any indication that it is incomplete.
**Handling:**
- Write a `pipeline_run_manifest.json` at the start of each run with `status: in_progress` and the start timestamp.
- Update it to `status: complete` only when all stages finish successfully.
- The report builder checks `status` before proceeding. If `status: in_progress`, it refuses to generate a report and surfaces an error.

---

## 6. Cross-Cutting / System-Wide Edge Cases

### EC-SYS01 — Pipeline Runs on Insufficient Data Volume
**Scenario:** The total RawRecord store contains fewer than 100 records after scraping (e.g., all sources had auth failures or volume caps set too low).
**Impact:** Signal counts are too low to produce statistically meaningful clusters. Frequency scores are unreliable.
**Handling:** Enforce a minimum record threshold before Stage 2 begins (default: `min_records: 200`). If the threshold is not met, log a `WARN: low data volume` and allow the user to override with a `--force` flag. Note the low-volume warning prominently in the report.

---

### EC-SYS02 — Re-Running the Pipeline After Config Changes
**Scenario:** The taxonomy is updated between two runs (a node is renamed or removed). Signals from the previous run reference a node that no longer exists.
**Impact:** Clustering in Stage 3 breaks when it tries to look up an obsolete `taxonomy_node` value.
**Handling:**
- Tag every Signal and RawRecord with the `taxonomy_version` (a hash of `taxonomy.yaml` at run time).
- On re-run, detect version mismatch between stored signals and current taxonomy. Auto-invalidate and re-extract signals from stored RawRecords using the new taxonomy, rather than breaking or silently mixing versions.

---

### EC-SYS03 — Two Concurrent Pipeline Runs Writing to the Same Store
**Scenario:** A user accidentally triggers two pipeline runs simultaneously. Both write to the same RawRecord and Signal stores.
**Impact:** Store corruption — duplicate records, race conditions in the deduplicator, mixed-version signals.
**Handling:** Implement a **pipeline lock file** (`pipeline.lock`) created at run start and deleted at run end. A second run that detects an existing lock file exits immediately with: `"PIPELINE HALTED: another run is in progress. Delete pipeline.lock to force."`.

---

### EC-SYS04 — Disk Space Exhausted Mid-Run
**Scenario:** The signal store or raw record store runs out of disk space while writing, causing a partial write.
**Impact:** Corrupted store files. Next run reads incomplete data.
**Handling:**
- Estimate required disk space before each run (rough formula: `N_records * avg_record_size * 1.5 safety_margin`). Alert if available disk space is less than the estimate.
- Use atomic writes (write to a temp file, then rename) so a failed write never corrupts the existing good file.

---

### EC-SYS05 — Pipeline Runs With a Brand-New (Empty) Store
**Scenario:** First-ever run on a clean installation. All stores are empty. Stage 3 has no signals to cluster.
**Impact:** If not handled, Stage 3 raises an unhandled exception on an empty signal list.
**Handling:** Stage 3 checks for an empty signal store before clustering. If empty, it logs `"No signals to cluster — run Stage 2 (scraping) and Stage 3 (extraction) first."` and exits gracefully. Not an error; it is the expected first-run sequence.

---

### EC-SYS06 — Embedding Model Not Available / Download Fails
**Scenario:** The sentence-transformer model (`all-MiniLM-L6-v2`) fails to download (no internet) or is corrupted.
**Impact:** Layer B (embedding similarity) in the taxonomy matcher is unavailable.
**Handling:**
- The pipeline falls back to Layer A (keyword matching) only.
- Logs: `"WARN: embedding model unavailable — falling back to keyword-only matching. Extraction recall may be reduced."`
- The run proceeds. The `confidence` of all signals in this run is capped at 0.90 (max keyword confidence), and the run log flags the fallback.

---

## 7. Domain-Specific Edge Cases (Fashion E-commerce)

### EC-D01 — Seasonal Signals (Sale Season vs. Regular Season)
**Scenario:** A large volume of records are from the Big Billion Day / End-of-Season Sale period. Price hesitation signals are abnormally high — "waiting for a sale" appears in 60% of price-related records.
**Impact:** Price hesitation is ranked #1 opportunity. But this may be a seasonal artifact, not a structural barrier to purchase.
**Handling:**
- Tag signals with a `time_context` flag if the record date falls within known sale windows (configurable list in `source_list.yaml`).
- Report scores with and without sale-period signals so the product team can see seasonal vs. structural picture separately.

---

### EC-D02 — Signals About Competitor Platforms (Not Myntra/AJIO)
**Scenario:** A Reddit thread compares Zara, H&M, and Shein sizing — none of which are the target platforms.
**Impact:** Behavioral signals about competitor platforms inflate the signal store with off-target data.
**Handling:**
- The taxonomy includes a `platform_ref` extractor: if a signal mentions only competitor platforms (and not Myntra/AJIO), it is tagged `platform_relevance: competitor_only`.
- Competitor-only signals contribute to `Comparison Behavior` clusters only (where cross-platform comparison is the insight), not to platform-specific opportunity areas.

---

### EC-D03 — Signals About Physical Store Experience (Not E-commerce)
**Scenario:** A Reddit comment says *"I tried this on at the Myntra Studio and the fitting was great."* — this is about a physical touchpoint, not the app/website.
**Impact:** A positive physical store signal for sizing is incorrectly counted as evidence against online size uncertainty.
**Handling:** Detect physical retail markers ("tried on", "went to the store", "fitting room", "in-store"). Tag such signals `channel: offline`. Offline signals are excluded from core opportunity scoring and surfaced separately as *"Offline channel signals"* in the appendix.

---

### EC-D04 — Aspirational Wishlist Adds (Not Behavioral Barriers)
**Scenario:** *"I just wish I could afford this someday 😭"* — this is an aspirational add, not a behavioral barrier. It does not represent a user who is close to purchase.
**Impact:** Incorrectly counted as a purchase-barrier signal (price hesitation), inflating severity.
**Handling:**
- The `Intent Signal` taxonomy node should distinguish between **near-purchase hesitation** (user has the money, is evaluating) and **aspirational bookmarking** (user is not a near-term buyer).
- Markers like "wish I could", "someday", "one day", "if only" → tag `intent_type: aspirational`. These signals answer Q8 (genuine intent vs. bookmarking) but are excluded from purchase-barrier scoring.

---

### EC-D05 — Signals From Brand/Seller Accounts Posing as Users
**Scenario:** A "user" review on Myntra is actually written by the brand or a paid promoter — detectable by formulaic language, 5-star rating, and account with only 1 review.
**Impact:** Inflates positive signals or introduces misleading product information claims.
**Handling:**
- Flag reviews with `platform_meta.rating = 5` + `author_meta` showing 0 prior reviews + text length < 30 words as `is_suspect: true`.
- Suspect records are processed with a confidence penalty of -0.3. Verbatim quotes from suspect records are never selected as representative quotes in the report.

---

### EC-D06 — Occasion-Specific Signals That Skew Timing
**Scenario:** A surge of wishlist/purchase content appears in the 2 weeks before Diwali or a wedding season. Occasion-driven hesitation ("not sure if it's formal enough") dominates the signal store.
**Impact:** Occasion-specific uncertainty is ranked as a year-round structural barrier.
**Handling:**
- Tag signals with a detected occasion marker (`occasion_hint`: wedding, festival, party, casual, etc.) where present.
- Report scores stratified by occasion vs. non-occasion signals. An opportunity dominated by occasion-tagged signals is annotated as "may be seasonal or occasion-specific."

---

### EC-D07 — Size Inclusivity Signals (Niche Segment, High Severity)
**Scenario:** Users with plus sizes or non-standard body types express extreme frustration about sizing availability. Signal count is low (niche segment) but severity is very high.
**Impact:** Low frequency score suppresses this opportunity in ranking, despite it being a high-severity, high-specificity insight.
**Handling:**
- Surface a secondary ranking that sorts by `severity_score` alone (in addition to composite rank).
- Flag opportunities where `severity > 0.85` but `frequency < 0.4` with a callout: *"Low-volume, high-severity signal — potential underserved segment."*

---

## Edge Case Severity Index

| ID | Stage | Severity | Likelihood | Status |
|---|---|---|---|---|
| EC-E04 | Extraction | 🔴 High | High | Must handle before Phase 3 exit |
| EC-O05 | Clustering | 🔴 High | Medium | Must handle — empty report is dangerous |
| EC-S03 | Scraping | 🔴 High | High | Must handle — common in production |
| EC-C02 | Config | 🔴 High | Medium | Must handle before any run |
| EC-SYS02 | System | 🔴 High | Medium | Must handle before Phase 4 |
| EC-S08 | Scraping | 🟡 Medium | High | Implement in Phase 2 |
| EC-E01 | Extraction | 🟡 Medium | High | Implement in Phase 3 |
| EC-E07 | Extraction | 🟡 Medium | High | Implement in Phase 3 |
| EC-D01 | Domain | 🟡 Medium | Medium | Implement in Phase 5 report layer |
| EC-D04 | Domain | 🟡 Medium | High | Implement in Phase 3 taxonomy |
| EC-O07 | Clustering | 🟡 Medium | Medium | Implement in Phase 4 |
| EC-OUT02 | Output | 🟢 Low | Medium | Implement in Phase 5 |
| EC-D05 | Domain | 🟢 Low | Low | Flag in Phase 2, handle in Phase 3 |

---

*This document is a living reference. Add new edge cases as they are discovered during implementation. Each edge case should be linked to the phase where it is handled and marked with its resolution status.*
