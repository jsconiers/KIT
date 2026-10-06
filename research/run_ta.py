"""Run TradingAgents for Kit: one ticker and date, Claude models, a markdown report, a notification.

Called by kit-research inside TradingAgents' own environment (uv run). Research only.
"""
import datetime as dt
import os
import pathlib
import subprocess
import sys

ticker, day, out = sys.argv[1], sys.argv[2], pathlib.Path(sys.argv[3])
TA = pathlib.Path.home() / "Claude/Agents/TradingAgents"
DEEP, QUICK = "claude-opus-5-5", "claude-sonnet-5-5"

# Load the API key from TradingAgents' .env without printing it.
env_file = TA / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
os.environ["TRADINGAGENTS_LLM_PROVIDER"] = "anthropic"
os.environ["TRADINGAGENTS_DEEP_THINK_LLM"] = DEEP
os.environ["TRADINGAGENTS_QUICK_THINK_LLM"] = QUICK

from tradingagents.default_config import DEFAULT_CONFIG  # noqa: E402
from tradingagents.graph.trading_graph import TradingAgentsGraph  # noqa: E402


def notify(message):
    message = message.replace('"', "'")
    subprocess.run(["/usr/bin/osascript", "-e",
                    f'display notification "{message}" with title "Kit research"'])


def section(title, body):
    text = str(body or "").strip()
    return f"## {title}\n\n{text or '_Nothing returned._'}\n\n"


config = DEFAULT_CONFIG.copy()
config.update({"llm_provider": "anthropic", "deep_think_llm": DEEP, "quick_think_llm": QUICK,
               "backend_url": None})
started = dt.datetime.now()
try:
    state, decision = TradingAgentsGraph(debug=False, config=config).propagate(ticker, day)
except Exception as e:  # noqa: BLE001
    notify(f"{ticker} research failed: {str(e)[:80]}")
    raise

minutes = int((dt.datetime.now() - started).total_seconds() // 60)
debate = state.get("investment_debate_state") or {}
risk = state.get("risk_debate_state") or {}
out.write_text(
    f"# {ticker}: TradingAgents research for {day}\n\n"
    f"Research only, not an order. Opus 5.5 for deep thinking, Sonnet 5.5 for quick; "
    f"the run took {minutes} minutes.\n\n"
    f"**Final call:** {str(decision).strip()}\n\n"
    + section("Final trade decision", state.get("final_trade_decision"))
    + section("Trader's plan", state.get("trader_investment_plan"))
    + section("Research manager: bull vs. bear", debate.get("judge_decision"))
    + section("Risk team", risk.get("judge_decision"))
    + section("Market and technicals", state.get("market_report"))
    + section("Fundamentals", state.get("fundamentals_report"))
    + section("News", state.get("news_report"))
    + section("Sentiment", state.get("sentiment_report")))
notify(f"{ticker} research done: {str(decision).strip()[:40]}")
print(f"Report: {out}")
