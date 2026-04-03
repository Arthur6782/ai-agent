#!/usr/bin/env python3
"""
Crypto Token Analyzer - CLI Entry Point
Elite token discovery and analysis engine.

Usage:
    python main.py                  # Full market scan
    python main.py --token ETH      # Analyze specific token
    python main.py --narrative AI   # Focus on specific narrative
"""

import argparse
import sys

from src.analyzer import CryptoTokenAnalyzer
from src.display import display_full_results, display_token_report, display_market_context, console


def main():
    parser = argparse.ArgumentParser(
        description="Crypto Token Analyzer - Elite Token Discovery Engine"
    )
    parser.add_argument(
        "--token",
        type=str,
        help="Analyze a specific token by ID (e.g., 'ethereum', 'render-token')",
    )
    parser.add_argument(
        "--symbol",
        type=str,
        default="",
        help="Token symbol (used with --token)",
    )
    parser.add_argument(
        "--contract",
        type=str,
        default="",
        help="Contract address for on-chain analysis",
    )
    parser.add_argument(
        "--chain",
        type=str,
        default="ethereum",
        choices=["ethereum", "solana", "bsc", "base", "arbitrum", "polygon"],
        help="Blockchain network",
    )
    parser.add_argument(
        "--narrative",
        type=str,
        nargs="+",
        help="Focus on specific narratives (e.g., AI DePIN RWA)",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=10,
        help="Maximum tokens to analyze in full scan (default: 10)",
    )
    parser.add_argument(
        "--market-only",
        action="store_true",
        help="Only show market context, no token analysis",
    )

    args = parser.parse_args()
    analyzer = CryptoTokenAnalyzer()

    try:
        if args.market_only:
            console.print("\n[bold]Fetching market context...[/]\n")
            ctx = analyzer.market_analyzer.get_market_condition()
            display_market_context(ctx)
            return

        if args.token:
            console.print(f"\n[bold]Analyzing {args.token}...[/]\n")
            report = analyzer.analyze_specific_token(
                token_id=args.token,
                symbol=args.symbol or args.token.upper(),
                name=args.token.replace("-", " ").title(),
                contract_address=args.contract,
                chain=args.chain,
                narratives=args.narrative,
            )
            ctx = analyzer.market_analyzer.get_market_condition()
            display_market_context(ctx)
            console.print()
            display_token_report(report)
            return

        console.print("\n[bold]Running full market scan...[/]\n")
        result = analyzer.run_full_analysis(max_tokens=args.max_tokens)
        display_full_results(result)

    except KeyboardInterrupt:
        console.print("\n[yellow]Analysis interrupted.[/]")
        sys.exit(0)
    except Exception as e:
        console.print(f"\n[red]Error: {e}[/]")
        sys.exit(1)


if __name__ == "__main__":
    main()
