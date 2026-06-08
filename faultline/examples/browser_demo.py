"""Offline simulation of a BROWSER agent (browser-use style) — proves faultline
catches the browser-agent silent failure WITHOUT a real browser or LLM.

A browser agent does: navigate -> read the page -> decide -> act (click/buy).
Its whole judgment depends on trusting what the page "returned." The classic
silent failure: the page content is stale/wrong, and the agent confidently acts
on it (buys an item it shouldn't, at a price it isn't).

This mirrors how the REAL browser-use adapter works: faultline wraps the
registry actions, corrupts the *content an action returns to the LLM*
(read_page), and captures the *side-effecting* actions (click_buy) so they never
really fire. See HUNT.md for running this against the real browser-use.

Run:  python3 -m faultline.examples.browser_demo
"""
from __future__ import annotations

from faultline.trace import tool, wrap
from faultline.runner import check
from faultline.faults import WrongNumber, NullResponse, Timeout

BUDGET = 100.0
REAL_CLICKS = []  # proves the side-effecting action never really fires under test


@tool
def navigate(url):
    return {"status": "loaded", "url": url}


@tool
def read_page(url):
    # The real product page: a $500 item (over budget).
    return {"title": "Deluxe Widget", "price": 500.0}


def _click_buy(url, price):
    REAL_CLICKS.append((url, price))   # the REAL side effect — must never run under test
    return {"ok": True}
click_buy = wrap(_click_buy, is_action=True)   # action tool: real body never executed


def browser_agent(task):
    """Naive browser agent: reads the page, buys if within budget. Trusts the page."""
    url = task["url"]
    navigate(url)
    page = read_page(url)
    if page is None:                                  # null-guard → graceful
        return {"decision": "SKIP", "reason": "couldn't read page", "unverified": True}
    if page["price"] <= BUDGET:
        click_buy(url, page["price"])
        return {"decision": "PURCHASED", "price": page["price"]}
    return {"decision": "SKIP", "reason": "over budget"}


def main():
    task = {"url": "https://shop.example/deluxe-widget"}
    # Correct answer: the page is $500, budget is $100 -> SKIP.
    faults = [
        WrongNumber(factor=0.1, targets=["read_page"]),   # stale/wrong price: $500 looks like $50
        NullResponse(targets=["read_page"]),              # page came back empty
        Timeout(targets=["read_page"]),                   # page hung
    ]
    print("faultline · browser-agent demo")
    print("  agent: browser_agent (buy if price <= $%.0f; real price is $500 → should SKIP)" % BUDGET)
    res = check(browser_agent, task, faults, trials=5)
    res.report()
    print("")
    print("REAL_CLICKS (should be empty — no real purchases happened): %r" % (REAL_CLICKS,))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
