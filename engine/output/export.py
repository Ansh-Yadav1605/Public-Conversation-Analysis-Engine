"""
engine/output/export.py
Public Conversation Analysis Engine — Export Module (Phase 5)

Exports the FinalReport into three standard formats:
1. Markdown (.md): Comprehensive, human-readable, executive & stakeholder-facing document.
2. JSON (.json): Machine-readable, structured data format for downstream systems/tools.
3. CSV (.csv): Flat tabular format of all Opportunity Areas for spreadsheet analysis & filtering.
"""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any

from engine.analyzer.models import OpportunityArea
from engine.logger import get_logger
from engine.output.report_builder import FinalReport

log = get_logger(__name__)


def to_markdown(report: FinalReport) -> str:
    """
    Format FinalReport into a clean, stakeholder-ready Markdown document.
    """
    lines: list[str] = []

    # Title & Metadata Header
    lines.append("# Public Conversation Analysis Report")
    lines.append("## Wishlist-to-Purchase Behavioral Diagnostics & Opportunity Prioritization")
    lines.append(f"**Generated:** {report.generated_at}  ")
    lines.append(
        f"**Scope:** {report.metadata.get('total_opportunities', 0)} Opportunity Areas | "
        f"{report.metadata.get('total_signals', 0)} Customer Signals | "
        f"{report.metadata.get('source_types_count', 0)} Independent Source Types | "
        f"{report.metadata.get('dimensions_count', 0)} Behavioral Dimensions\n"
    )
    lines.append("---")

    # =========================================================================
    # Section 1: Executive Summary
    # =========================================================================
    lines.append("## Section 1: Executive Summary\n")
    lines.append(
        "The following prioritized opportunity matrix identifies the highest-leverage areas "
        "to reduce friction between wishlisting and purchasing. Opportunities are ranked by their "
        "**Composite Priority Score** combining Frequency (volume), Severity (pain intensity), "
        "and Cross-Source Evidence Strength.\n"
    )

    lines.append(
        "| Rank | Priority Opportunity | Dimension | Composite | Frequency | Severity | Evidence | Signals | Sources |"
    )
    lines.append(
        "|:---:|:---|:---|:---:|:---:|:---:|:---:|:---:|:---|"
    )

    for item in report.executive_summary_table:
        sources_str = ", ".join(item["sources"][:3])
        if len(item["sources"]) > 3:
            sources_str += f" +{len(item['sources'])-3}"
        lines.append(
            f"| **#{item['rank']}** | **{item['title']}** | {item['dimension']} | "
            f"**{item['composite_score']:.3f}** | {item['frequency_score']:.2f} | "
            f"{item['severity_score']:.2f} | {item['evidence_strength']:.2f} | "
            f"{item['signal_count']} | {sources_str} |"
        )
    lines.append("\n---\n")

    # =========================================================================
    # Section 2: Behavioral Question Answers (Q1 to Q10)
    # =========================================================================
    lines.append("## Section 2: Behavioral Question Answers\n")
    lines.append(
        "Direct evidence-backed diagnostic answers for each of the 10 core PM behavioral questions.\n"
    )

    for qa in report.question_answers:
        lines.append(f"### Q{qa.question_id}: {qa.question_text}")
        lines.append(f"**Related Dimensions:** {', '.join(qa.related_dimensions)} | **Signals Analyzed:** {qa.total_signals}\n")
        lines.append(f"> **Key Finding:** {qa.evidence_summary}\n")

        if qa.top_opportunities:
            lines.append("**Mapped Opportunity Areas:**")
            for op in qa.top_opportunities:
                lines.append(f"- **[Rank #{op.rank}] {op.title}** (Composite Score: `{op.scores.composite:.3f}` | Signals: `{op.signal_count}`)")
                lines.append(f"  *{op.opportunity_statement}*")
        else:
            lines.append("*No opportunities surpassed cross-source validation threshold for this question.*")
        lines.append("")

    lines.append("---\n")

    # =========================================================================
    # Section 3: Opportunity Detail Cards
    # =========================================================================
    lines.append("## Section 3: Opportunity Detail Cards\n")

    for op in report.opportunity_cards:
        lines.append(f"### Rank #{op.rank}: {op.title}")
        lines.append(f"**Dimension:** `{op.dimension}` | **Taxonomy Node(s):** `{', '.join(op.taxonomy_nodes)}`\n")
        lines.append(f"**Opportunity Statement:**\n> {op.opportunity_statement}\n")

        # Score Breakdown Table
        lines.append("#### Priority Scores")
        lines.append("| Metric | Score | Formula / Rationale |")
        lines.append("|:---|:---:|:---|")
        lines.append(f"| **Composite Priority** | **{op.scores.composite:.3f}** | Weighted sum (w_freq*Freq + w_sev*Sev + w_ev*Evidence) |")
        lines.append(f"| Frequency Score | {op.scores.frequency:.3f} | {op.signal_count} signals relative to peak cluster volume |")
        lines.append(f"| Severity Score | {op.scores.severity:.3f} | Average user pain/frustration intensity across signals |")
        lines.append(f"| Evidence Strength | {op.scores.evidence_strength:.3f} | {len(op.source_spread)} independent source platforms × confidence |")
        lines.append("")

        # Context Breakdown
        lines.append(f"**Target User Segments:** {op.segment_concentration}  ")
        spread_str = ", ".join(f"{src}: {cnt}" for src, cnt in op.source_spread.items())
        lines.append(f"**Cross-Platform Source Spread:** {spread_str}  ")
        lines.append(f"**Addressed Questions:** Q{', Q'.join(str(q) for q in op.question_answers)}\n")

        # Representative Verbatim Quotes
        lines.append("#### Representative Customer Quotes (Verbatim)")
        if op.representative_quotes:
            for quote in op.representative_quotes:
                url_str = f" ([Source Link]({quote.url}))" if quote.url else ""
                lines.append(f"- *\"{quote.verbatim}\"* — **{quote.source_name or quote.source_type}**{url_str}")
        else:
            lines.append("*(No representative quotes available)*")

        lines.append("\n---\n")

    # =========================================================================
    # Section 4: Raw Signal Appendix
    # =========================================================================
    lines.append("## Section 4: Signal Audit Appendix\n")
    lines.append(
        f"Audit sample of {min(len(report.signal_appendix), 50)} raw signals extracted across all sources "
        f"(total repository signals: {len(report.signal_appendix)}).\n"
    )

    lines.append("| Signal ID | Source | Dimension | Confidence | Verbatim Quote |")
    lines.append("|:---|:---|:---|:---:|:---|")

    for sig in report.signal_appendix[:50]:
        quote_clean = sig.verbatim_quote.replace("|", "/").replace("\n", " ")[:120]
        if len(sig.verbatim_quote) > 120:
            quote_clean += "..."
        src_name = sig.source_ref.source_name if sig.source_ref else "Unknown"
        lines.append(
            f"| `{sig.signal_id[:8]}` | {src_name} | {sig.dimension} | "
            f"{sig.confidence:.2f} | \"{quote_clean}\" |"
        )

    lines.append("\n\n*End of Report — Public Conversation Analysis Engine*\n")
    return "\n".join(lines)


def to_json(report: FinalReport) -> str:
    """
    Serialize FinalReport to a formatted JSON string.
    """
    return json.dumps(report.to_dict(), indent=2, ensure_ascii=False)


def to_csv(opportunities: list[OpportunityArea]) -> str:
    """
    Export OpportunityAreas into a flat CSV format.
    """
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")

    # Header
    writer.writerow([
        "rank",
        "opportunity_id",
        "title",
        "dimension",
        "composite_score",
        "frequency_score",
        "severity_score",
        "evidence_strength",
        "signal_count",
        "source_count",
        "sources",
        "target_segments",
        "question_answers",
        "opportunity_statement",
    ])

    for op in opportunities:
        sources_str = "; ".join(f"{src}:{cnt}" for src, cnt in op.source_spread.items())
        questions_str = "; ".join(str(q) for q in op.question_answers)
        writer.writerow([
            op.rank or "",
            op.opportunity_id,
            op.title,
            op.dimension,
            f"{op.scores.composite:.4f}",
            f"{op.scores.frequency:.4f}",
            f"{op.scores.severity:.4f}",
            f"{op.scores.evidence_strength:.4f}",
            op.signal_count,
            len(op.source_spread),
            sources_str,
            op.segment_concentration,
            questions_str,
            op.opportunity_statement,
        ])

    return output.getvalue()


def export_all(report: FinalReport, output_dir: Path) -> dict[str, Path]:
    """
    Save the report into Markdown, JSON, and CSV in the specified directory.

    Args:
        report: Assembled FinalReport.
        output_dir: Destination directory.

    Returns:
        Dict mapping format name ('markdown', 'json', 'csv') to saved Path.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    md_path = output_dir / "final_analysis_report.md"
    json_path = output_dir / "final_analysis_report.json"
    csv_path = output_dir / "opportunities_matrix.csv"

    # 1. Write Markdown
    md_content = to_markdown(report)
    md_path.write_text(md_content, encoding="utf-8")

    # 2. Write JSON
    json_content = to_json(report)
    json_path.write_text(json_content, encoding="utf-8")

    # 3. Write CSV
    csv_content = to_csv(report.opportunity_cards)
    csv_path.write_text(csv_content, encoding="utf-8")

    log.info(
        "Export complete:\n  Markdown: %s\n  JSON: %s\n  CSV: %s",
        md_path, json_path, csv_path,
    )

    return {
        "markdown": md_path,
        "json": json_path,
        "csv": csv_path,
    }
