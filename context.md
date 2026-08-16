# Project Context

## Overview

This document captures the complete context of the graduation project — a **Public Conversation Analysis Engine** for product teams. The engine scrapes and analyzes public user conversations at scale to surface evidence-backed behavioral insights that traditional analytics, sentiment analysis, and manual research cannot provide.

---

## The Problem

### Core Gap

Product teams trying to understand **why users hesitate, stall, or abandon a specific behavior** — such as adding a fashion product to a wishlist but never buying it — routinely default to internal analytics and gut-instinct hypotheses. Reading real user language at scale across public sources is too slow and manual to do consistently.

### Consequences

- Product decisions get made on **assumption rather than evidence**.
- Qualitative research arrives **late** — as validation of a solution someone already committed to, not as early discovery of the real problem.

### Data Complexity

Public conversation data is **messy and inconsistent** across sources:

- A single review or thread can contain **multiple distinct signals** — a fit complaint, a styling doubt, a price hesitation, a trust concern.
- There is **no shared structure** to make signals comparable, clusterable, or rankable.
- **Sentiment analysis alone is insufficient** — two "negative" mentions can point to completely different root causes.

---

## The Solution — What This Engine Does

Scrapes and analyzes public conversation to answer a defined set of **behavioral questions** that summarization or sentiment analysis alone cannot answer.

### Data Sources

| Source Type             | Examples                                      |
|-------------------------|-----------------------------------------------|
| App Store Reviews       | Apple App Store                               |
| Play Store Reviews      | Google Play Store                             |
| Reddit Discussions      | Relevant subreddits                           |
| Fashion & Shopping Communities | Forums, community sites                |
| Social Media            | Twitter/X, Instagram comments, etc.           |
| YouTube Comments        | Video comment threads                         |
| Product Reviews / Q&A   | On-platform review and Q&A sections           |

### Core Behavioral Questions (The Question Set)

| #  | Question |
|----|----------|
| 1  | Why do users add fashion products to their wishlist in the first place? |
| 2  | What prevents wishlisted products from eventually being purchased? |
| 3  | What uncertainties remain after a user has already identified a product they like? |
| 4  | What causes users to postpone a purchase rather than abandon or complete it? |
| 5  | How do users compare multiple shortlisted products against each other? |
| 6  | What information do users seek outside the platform (Myntra/AJIO and beyond) before deciding? |
| 7  | What role do fit, size, styling, price, reviews, occasion, and social validation each play — and how do they interact? |
| 8  | When is a wishlist add genuine purchase intent, and when is it just bookmarking? |
| 9  | How do these behaviors and motivations differ across user segments? |
| 10 | What unmet needs show up consistently, across independent conversations, rather than as one-off complaints? |

### Key Capabilities (Beyond Sentiment/Summarization)

- **Identifies discrete opportunity areas** from raw public conversation data.
- **Quantifies opportunities** where evidence allows — by frequency, severity, and segment concentration.
- **Makes opportunities comparable** against each other — enabling ranked prioritization.
- Moves a product team from *"we don't know why users behave this way"* to a **ranked, evidence-tagged shortlist** worth taking into primary research.

---

## Pipeline Architecture (Conceptual)

The underlying pipeline consists of three generic stages:

```
Source Scraping → Taxonomy-Based Extraction → Opportunity Clustering & Scoring
```

| Stage                        | Description |
|------------------------------|-------------|
| **Source Scraping**          | Collects raw public conversation data from the defined source list. |
| **Taxonomy-Based Extraction**| Applies a configurable taxonomy to extract structured signals from unstructured text. |
| **Opportunity Clustering & Scoring** | Groups extracted signals into opportunity areas, scores them by frequency/severity/evidence-strength, and ranks them. |

---

## Design Principles

### Generic & Configurable

- While the graduation project anchors on **fashion e-commerce**, the pipeline is **not fashion-specific**.
- The **taxonomy and question set are configurable inputs**, not hardcoded logic.
- The same engine could be re-pointed at a **different product category or business problem** without a rebuild.

### Explicit Boundaries — What It Is NOT

| It is NOT                                      | Why                                                                 |
|------------------------------------------------|---------------------------------------------------------------------|
| A replacement for primary user research        | Interviews remain the validation layer, per the project's own research sequence. |
| A sentiment-analysis tool                      | Sentiment scoring alone cannot distinguish different root causes.    |
| A review-summarization tool                    | Summarization loses the discrete, comparable signal structure needed for prioritization. |

---

## Success Criteria

Given the fashion-shopping source list and the ten-question set, the engine returns:

- A **structured, source-traceable set of opportunity areas**.
- Each opportunity tagged with **frequency / severity / evidence-strength** where the data supports it.
- Answers to the **ten behavioral questions** above with **real evidence rather than assumption**.
- Delivered in **far less time** than a manual research pass would take.

---

## Domain Context

| Dimension           | Detail                                                    |
|---------------------|-----------------------------------------------------------|
| **Domain**          | Fashion e-commerce (initial anchor)                       |
| **Platforms**       | Myntra, AJIO, and beyond                                  |
| **User Behavior**   | Wishlist-to-purchase journey                              |
| **Key Factors**     | Fit, size, styling, price, reviews, occasion, social validation |
| **Project Type**    | Graduation Project — Product Management                   |
| **Research Sequence**| Engine output feeds into primary research (interviews)    |
