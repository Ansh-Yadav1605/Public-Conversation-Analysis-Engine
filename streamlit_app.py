"""
streamlit_app.py
Public Conversation Analysis Engine — Interactive Streamlit Dashboard

Provides an end-to-end interface for:
  - Triggering and monitoring analysis pipeline runs
  - Exploring ranked Product Opportunity Areas & composite scores
  - Inspecting underlying verbatim signals and cross-source evidence
  - Downloading export deliverables (JSON, CSV, Markdown)
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

# Add repository root to PYTHONPATH
REPO_ROOT = Path(__file__).parent.resolve()
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from engine.analyzer.opportunity_store import OpportunityStore
from engine.config_loader import load_all_config
from engine.extractor.signal_store import SignalStore
from engine.output.export import export_all
from engine.output.report_builder import ReportBuilder
from run_pipeline import run_full_pipeline

# -----------------------------------------------------------------------------
# Streamlit Page Config & Custom Styling
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Public Conversation Analysis Engine",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .main-title {
        font-size: 2.2rem;
        font-weight: 700;
        color: #1E293B;
        margin-bottom: 0.2rem;
    }
    .sub-title {
        font-size: 1.05rem;
        color: #64748B;
        margin-bottom: 1.5rem;
    }
    .metric-card {
        background: #F8FAFC;
        border: 1px solid #E2E8F0;
        border-radius: 12px;
        padding: 1.2rem;
        text-align: center;
    }
    .score-badge {
        font-size: 0.85rem;
        padding: 0.25rem 0.6rem;
        border-radius: 6px;
        font-weight: 600;
    }
    .quote-box {
        background: #F1F5F9;
        border-left: 4px solid #3B82F6;
        padding: 0.8rem 1rem;
        border-radius: 4px;
        margin-bottom: 0.8rem;
        font-style: italic;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# -----------------------------------------------------------------------------
# Helper Functions
# -----------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def get_cached_data() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Load opportunities and signals from store."""
    op_store = OpportunityStore()
    sig_store = SignalStore()
    
    opportunities = [op.to_dict() for op in op_store.read_all()]
    signals = [sig.to_dict() for sig in sig_store.read_all()]
    return opportunities, signals


def clear_cache() -> None:
    get_cached_data.clear()


# -----------------------------------------------------------------------------
# Sidebar Navigation & Controls
# -----------------------------------------------------------------------------
st.sidebar.title("🔍 Conversation Engine")
st.sidebar.markdown(
    "Synthesize unorganized public discussions into **prioritized product opportunities**."
)

st.sidebar.divider()
st.sidebar.subheader("⚡ Quick Pipeline Run")
dry_run_opt = st.sidebar.checkbox("Fast Dry Run (Sample)", value=False)
skip_scrape_opt = st.sidebar.checkbox("Use Existing Data (Skip Scrape)", value=True)
match_layer_opt = st.sidebar.selectbox("Match Layer", options=["ab", "a"], index=0, help="ab = Keyword + Semantic Embedding, a = Keyword Only")
min_sources_opt = st.sidebar.slider("Min Unique Sources", min_value=1, max_value=4, value=2)

if st.sidebar.button("🚀 Run Pipeline Now", use_container_width=True, type="primary"):
    with st.spinner("Executing analysis pipeline... This may take a few moments."):
        log_placeholder = st.empty()
        try:
            start_t = time.time()
            summary = run_full_pipeline(
                dry_run=dry_run_opt,
                skip_scrape=skip_scrape_opt,
                layer=match_layer_opt,
                min_sources=min_sources_opt,
            )
            elapsed = round(time.time() - start_t, 2)
            clear_cache()
            st.sidebar.success(f"Pipeline finished in {elapsed}s!")
            st.rerun()
        except Exception as exc:
            st.sidebar.error(f"Pipeline error: {exc}")

st.sidebar.divider()
if st.sidebar.button("🔄 Refresh Data", use_container_width=True):
    clear_cache()
    st.rerun()


# -----------------------------------------------------------------------------
# Header & KPI Metrics
# -----------------------------------------------------------------------------
st.markdown('<div class="main-title">Public Conversation Analysis Engine</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="sub-title">Automated intelligence pipeline for product managers — turning public signals into ranked opportunities.</div>',
    unsafe_allow_html=True,
)

opportunities, signals = get_cached_data()

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric(label="Surfaced Opportunities", value=len(opportunities))
with col2:
    st.metric(label="Extracted Signals", value=len(signals))
with col3:
    unique_platforms = len(set(s.get("source_type", "") for s in signals if s.get("source_type")))
    st.metric(label="Active Sources", value=unique_platforms if unique_platforms else 4)
with col4:
    avg_score = round(sum(op.get("composite_score", 0) for op in opportunities) / len(opportunities), 2) if opportunities else 0
    st.metric(label="Avg Composite Score", value=avg_score)

st.divider()

# -----------------------------------------------------------------------------
# Navigation Tabs
# -----------------------------------------------------------------------------
tab_opps, tab_signals, tab_export, tab_taxonomy = st.tabs(
    ["🏆 Ranked Opportunities", "🔎 Signal Explorer", "📥 Export & Reports", "⚙️ Taxonomy & Questions"]
)

# -----------------------------------------------------------------------------
# TAB 1: Ranked Opportunities
# -----------------------------------------------------------------------------
with tab_opps:
    st.subheader("Prioritized Product Opportunity Areas")
    
    if not opportunities:
        st.info("No opportunity data found in store. Run the pipeline using the sidebar to generate results.")
    else:
        # Filters
        f_col1, f_col2, f_col3 = st.columns([2, 2, 3])
        with f_col1:
            all_dims = sorted(list(set(op.get("dimension", "") for op in opportunities if op.get("dimension"))))
            selected_dim = st.selectbox("Filter by Dimension", options=["All"] + all_dims)
        with f_col2:
            min_score = st.slider("Min Composite Score", min_value=0.0, max_value=1.0, value=0.0, step=0.05)
        with f_col3:
            search_query = st.text_input("Search Opportunities", placeholder="e.g. sizing, battery, checkout...")

        filtered_opps = opportunities
        if selected_dim != "All":
            filtered_opps = [o for o in filtered_opps if o.get("dimension") == selected_dim]
        if min_score > 0:
            filtered_opps = [o for o in filtered_opps if o.get("composite_score", 0) >= min_score]
        if search_query:
            q = search_query.lower()
            filtered_opps = [
                o for o in filtered_opps
                if q in o.get("title", "").lower() or q in o.get("description", "").lower()
            ]

        # Sort by rank / composite score
        filtered_opps = sorted(filtered_opps, key=lambda x: x.get("composite_score", 0), reverse=True)

        st.caption(f"Showing {len(filtered_opps)} of {len(opportunities)} opportunities")

        # Opportunity Cards
        for idx, opp in enumerate(filtered_opps, start=1):
            comp_score = opp.get("composite_score", 0.0)
            scores = opp.get("scores", {})
            freq_score = scores.get("frequency_score", 0.0)
            sev_score = scores.get("severity_score", 0.0)
            evid_score = scores.get("evidence_score", 0.0)
            
            with st.expander(f"#{idx} — {opp.get('title', 'Untitled Opportunity')} (Score: {comp_score:.2f})", expanded=(idx <= 3)):
                st.markdown(f"**Dimension:** `{opp.get('dimension', 'General')}` | **Sources:** `{', '.join(opp.get('sources', []))}`")
                st.markdown(f"**Description:** {opp.get('description', '')}")

                # Score progress bars
                sc_col1, sc_col2, sc_col3, sc_col4 = st.columns(4)
                with sc_col1:
                    st.metric("Composite Score", f"{comp_score:.2f}")
                    st.progress(min(max(comp_score, 0.0), 1.0))
                with sc_col2:
                    st.metric("Frequency Score", f"{freq_score:.2f}")
                    st.progress(min(max(freq_score, 0.0), 1.0))
                with sc_col3:
                    st.metric("Severity Score", f"{sev_score:.2f}")
                    st.progress(min(max(sev_score, 0.0), 1.0))
                with sc_col4:
                    st.metric("Evidence Score", f"{evid_score:.2f}")
                    st.progress(min(max(evid_score, 0.0), 1.0))

                if opp.get("segment_note"):
                    st.info(f"💡 **Customer Segment & Impact:** {opp.get('segment_note')}")

                # Representative Quotes
                quotes = opp.get("representative_quotes", [])
                if quotes:
                    st.markdown("##### 💬 Verbatim Customer Quotes")
                    for q in quotes:
                        quote_text = q.get("text", "") if isinstance(q, dict) else str(q)
                        src = q.get("source_type", "") if isinstance(q, dict) else ""
                        url = q.get("source_url", "") if isinstance(q, dict) else ""
                        
                        src_str = f" — *{src.title()}*" if src else ""
                        url_link = f" [[View Source]({url})]" if url else ""
                        st.markdown(f'<div class="quote-box">"{quote_text}"{src_str}{url_link}</div>', unsafe_allow_html=True)


# -----------------------------------------------------------------------------
# TAB 2: Signal Explorer
# -----------------------------------------------------------------------------
with tab_signals:
    st.subheader("Raw Extracted Signals")
    if not signals:
        st.info("No signal data available. Run the pipeline to collect and extract signals.")
    else:
        sig_col1, sig_col2, sig_col3 = st.columns(3)
        with sig_col1:
            sources_list = sorted(list(set(s.get("source_type", "") for s in signals if s.get("source_type"))))
            src_filter = st.multiselect("Filter by Source Platform", options=sources_list, default=sources_list)
        with sig_col2:
            sig_dims = sorted(list(set(s.get("dimension", "") for s in signals if s.get("dimension"))))
            dim_filter = st.multiselect("Filter by Dimension", options=sig_dims, default=sig_dims)
        with sig_col3:
            sig_search = st.text_input("Search in Signal Content", placeholder="Keyword search...")

        # Filter signals
        display_signals = signals
        if src_filter:
            display_signals = [s for s in display_signals if s.get("source_type") in src_filter]
        if dim_filter:
            display_signals = [s for s in display_signals if s.get("dimension") in dim_filter]
        if sig_search:
            q = sig_search.lower()
            display_signals = [s for s in display_signals if q in s.get("verbatim_quote", "").lower()]

        st.caption(f"Showing {len(display_signals)} matching signals")

        # Table data formatting
        table_rows = []
        for s in display_signals:
            table_rows.append({
                "Platform": s.get("source_type", "").title(),
                "Dimension": s.get("dimension", ""),
                "Node ID": s.get("taxonomy_node_id", ""),
                "Confidence": round(s.get("confidence", 0.0), 2),
                "Severity": s.get("severity", ""),
                "Sentiment": round(s.get("sentiment_score", 0.0), 2),
                "Verbatim Quote": s.get("verbatim_quote", ""),
            })

        df_signals = pd.DataFrame(table_rows)
        st.dataframe(df_signals, use_container_width=True, height=450)


# -----------------------------------------------------------------------------
# TAB 3: Export Deliverables
# -----------------------------------------------------------------------------
with tab_export:
    st.subheader("Generate & Download Deliverables")
    st.markdown("Export the current analysis as JSON, CSV, or Markdown reports for stakeholders.")

    if not opportunities:
        st.warning("No opportunities currently available to export. Run the pipeline first.")
    else:
        cfg = load_all_config()
        op_store = OpportunityStore()
        sig_store = SignalStore()
        
        ops_obj = op_store.read_all()
        sigs_obj = sig_store.read_all()
        
        builder = ReportBuilder(config=cfg)
        final_rep = builder.build_report(opportunities=ops_obj, signals=sigs_obj)
        
        # Prepare downloads
        json_str = json.dumps(final_rep.to_dict(), indent=2)
        
        # Prepare CSV string
        df_exp = pd.DataFrame([
            {
                "Rank": idx + 1,
                "Title": op.title,
                "Dimension": op.dimension,
                "Composite Score": round(op.composite_score, 4),
                "Frequency Score": round(op.scores.frequency_score, 4),
                "Severity Score": round(op.scores.severity_score, 4),
                "Evidence Score": round(op.scores.evidence_score, 4),
                "Sources": ", ".join(op.sources),
                "Segment Note": op.segment_note,
            }
            for idx, op in enumerate(ops_obj)
        ])
        csv_str = df_exp.to_csv(index=False)

        # Prepare Markdown string
        from engine.output.export import to_markdown
        temp_md_path = REPO_ROOT / "engine" / "data" / "reports" / "report.md"
        md_content = ""
        if temp_md_path.exists():
            md_content = temp_md_path.read_text(encoding="utf-8")
        else:
            md_content = f"# Public Conversation Analysis Report\n\nTotal Opportunities: {len(ops_obj)}"

        exp_col1, exp_col2, exp_col3 = st.columns(3)
        with exp_col1:
            st.download_button(
                label="📄 Download JSON Report",
                data=json_str,
                file_name="opportunity_report.json",
                mime="application/json",
                use_container_width=True,
            )
        with exp_col2:
            st.download_button(
                label="📊 Download CSV Table",
                data=csv_str,
                file_name="opportunity_rankings.csv",
                mime="text/csv",
                use_container_width=True,
            )
        with exp_col3:
            st.download_button(
                label="📝 Download Markdown Report",
                data=md_content,
                file_name="opportunity_report.md",
                mime="text/markdown",
                use_container_width=True,
            )

        st.divider()
        st.markdown("#### Report Preview")
        st.dataframe(df_exp, use_container_width=True)


# -----------------------------------------------------------------------------
# TAB 4: Taxonomy & PM Questions
# -----------------------------------------------------------------------------
with tab_taxonomy:
    st.subheader("Core PM Question Set & Taxonomy")
    try:
        cfg = load_all_config()
        st.markdown("##### 🎯 6 Core PM Questions")
        for q in cfg.question_set.questions:
            with st.expander(f"Q{q.id}: {q.text}"):
                st.markdown(f"**Target Dimension:** `{q.dimension}`")
                st.markdown(f"**Intent:** {q.intent}")
                st.markdown(f"**Weight:** `{q.weight}`")

        st.markdown("##### 🗂️ Taxonomy Dimensions & Nodes")
        for node in cfg.taxonomy.nodes:
            with st.expander(f"[{node.dimension}] {node.node_name} (`{node.id}`)"):
                st.markdown(f"**Keywords:** {', '.join(node.keywords)}")
                if node.negative_keywords:
                    st.markdown(f"**Negative Keywords:** {', '.join(node.negative_keywords)}")
    except Exception as exc:
        st.error(f"Could not load config: {exc}")
