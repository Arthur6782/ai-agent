"""
Display Module
Rich terminal output for analysis results.
"""

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich import box

from src.analyzer import AnalysisResult
from src.scoring import TokenReport
from src.market_context import MarketContext, MarketCondition


console = Console()


def display_market_context(ctx: MarketContext):
    """Display market context summary."""
    condition_color = {
        MarketCondition.BULLISH: "green",
        MarketCondition.BEARISH: "red",
        MarketCondition.RANGING: "yellow",
    }
    color = condition_color.get(ctx.condition, "white")

    panel_content = Text()
    panel_content.append(f"Condition: ", style="bold")
    panel_content.append(f"{ctx.condition.value.upper()}\n", style=f"bold {color}")
    panel_content.append(f"BTC Dominance: ", style="bold")
    panel_content.append(f"{ctx.btc_dominance:.1f}%\n")
    panel_content.append(f"Total Market Cap: ", style="bold")
    panel_content.append(f"${ctx.total_market_cap:,.0f}\n")
    panel_content.append(f"24h Change: ", style="bold")
    mc_color = "green" if ctx.market_cap_change_24h > 0 else "red"
    panel_content.append(f"{ctx.market_cap_change_24h:+.2f}%\n", style=mc_color)
    if ctx.fear_greed_index is not None:
        panel_content.append(f"Fear & Greed: ", style="bold")
        fg_color = "green" if ctx.fear_greed_index > 50 else "red"
        panel_content.append(f"{ctx.fear_greed_index}/100\n", style=fg_color)
    panel_content.append(f"Dominant Narratives: ", style="bold")
    panel_content.append(", ".join(ctx.dominant_narratives))

    console.print(Panel(panel_content, title="MARKET CONTEXT", border_style="cyan"))


def display_token_report(report: TokenReport):
    """Display a single token analysis report."""
    score_color = "green" if report.score >= 7 else "yellow" if report.score >= 5 else "red"
    rec_text = "RECOMMENDED" if report.recommended else "NOT RECOMMENDED"
    rec_color = "green" if report.recommended else "red"

    table = Table(box=box.ROUNDED, show_header=False, border_style=score_color)
    table.add_column("Field", style="bold cyan", width=22)
    table.add_column("Value", style="white")

    table.add_row("Name", f"{report.name} ({report.symbol})")
    table.add_row("Chain", report.chain)
    table.add_row("Narrative", report.narrative)
    table.add_row("Why Potential", report.why_potential)
    table.add_row("Smart Money Signal", report.smart_money_signal)
    table.add_row("Entry Zone", report.entry_zone)
    table.add_row("Risk Level", report.risk_level)
    table.add_row("Score", f"[bold {score_color}]{report.score}/10[/]")
    table.add_row("Verdict", f"[bold {rec_color}]{rec_text}[/]")

    if report.breakdown:
        breakdown_parts = []
        for k, v in report.breakdown.items():
            breakdown_parts.append(f"{k}: {v}")
        table.add_row("Score Breakdown", " | ".join(breakdown_parts))

    if report.risk_score.red_flags:
        flags = "\n".join(f"  - {f}" for f in report.risk_score.red_flags)
        table.add_row("[red]Red Flags[/]", f"[red]{flags}[/]")

    console.print(table)
    console.print()


def display_full_results(result: AnalysisResult):
    """Display complete analysis results."""
    console.print()
    console.print(
        Panel(
            "[bold]CRYPTO TOKEN ANALYZER[/]\n"
            "Elite Token Discovery & Analysis Engine\n"
            "Think like a sniper, not a gambler.",
            border_style="bright_blue",
        )
    )
    console.print()

    # Market Context
    display_market_context(result.market_context)
    console.print()

    # Pipeline Summary
    console.print(
        f"[bold]Pipeline:[/] {result.total_discovered} discovered -> "
        f"{result.total_filtered} filtered -> "
        f"{result.total_analyzed} analyzed -> "
        f"[bold green]{len(result.recommended_tokens)} recommended[/]"
    )
    console.print()

    # Recommended Tokens
    if result.recommended_tokens:
        console.print(
            Panel("[bold green]RECOMMENDED TOKENS (Score >= 7)[/]", border_style="green")
        )
        for report in result.recommended_tokens:
            display_token_report(report)
    else:
        console.print(
            Panel(
                "[yellow]No tokens met the minimum score threshold (7/10).\n"
                "Market conditions may not favor new entries right now.\n"
                "Think like a sniper - patience is key.[/]",
                border_style="yellow",
            )
        )

    # Non-recommended analyzed tokens
    non_recommended = [r for r in result.all_reports if not r.recommended]
    if non_recommended:
        console.print(
            Panel("[bold yellow]ANALYZED BUT NOT RECOMMENDED[/]", border_style="yellow")
        )
        summary_table = Table(box=box.SIMPLE)
        summary_table.add_column("Token", style="bold")
        summary_table.add_column("Score")
        summary_table.add_column("Reason")

        for report in non_recommended[:5]:
            score_color = "yellow" if report.score >= 5 else "red"
            issues = []
            if report.risk_score.red_flags:
                issues.extend(report.risk_score.red_flags[:2])
            if report.score < 7:
                issues.append(f"Score too low ({report.score}/10)")
            summary_table.add_row(
                f"{report.symbol}",
                f"[{score_color}]{report.score}/10[/]",
                "; ".join(issues) if issues else "Below threshold",
            )

        console.print(summary_table)
        console.print()

    # Rejected tokens
    if result.rejected_tokens:
        console.print(
            Panel("[bold red]FILTERED OUT (Bad Tokens)[/]", border_style="red")
        )
        reject_table = Table(box=box.SIMPLE)
        reject_table.add_column("Token", style="bold")
        reject_table.add_column("Reason", style="red")
        for rej in result.rejected_tokens[:10]:
            reject_table.add_row(rej["token"], rej["reason"])
        console.print(reject_table)

    console.print()
    console.print("[dim]Disclaimer: This is not financial advice. DYOR.[/]")
