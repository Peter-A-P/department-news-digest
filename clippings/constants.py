"""Values fixed by the project's rules rather than by an audience file.

These are not configuration. PLAN.md section 2.2 and the repository rules make them
promises the project publishes, so an audience file cannot raise them.
"""

from typing import Final

# Article text is kept thirty days and never republished (PLAN.md section 2.2).
RETENTION_DAYS: Final = 30

# A digest shows summaries, links and quotes of at most twenty-five words. The verifier
# enforces this alongside the verbatim check; no audience can widen it.
QUOTE_MAX_WORDS: Final = 25

# The identifier of this project in the gateway's ledger, so cost per digest can be read back
# out of it (PLAN.md section 1).
GATEWAY_PROJECT: Final = "clippings"

# Costs are shown in Canadian dollars at a fixed rate, the one the portfolio plan budgets at
# (Peter, 2026-10-10). The gateway's ledger, its prices and its caps stay in US dollars, as
# the vendors bill; this is only how a cost is printed. Fixed rather than fetched, so a
# figure in the README is reproducible from the repository alone.
CAD_PER_USD: Final = 1.35


def cad(usd: float) -> float:
    return usd * CAD_PER_USD


# Every model call this project makes is over public sources only.
GATEWAY_DATA_CLASS: Final = "public"

# One user agent for every outbound request, so a publisher reading its logs can see who this
# is and how to ask it to stop.
#
# It deliberately carries no URL. The `Product/Version (+https://...)` convention is the
# standard way a well-behaved crawler gives its contact address, and it is what this used to
# send. Measured against CBC on 2026-09-13, one variable at a time through the same client:
#
#     curl/8.5.0                                              200
#     clippings/0.1                                           200
#     clippings/0.1 news digest research                      200
#     clippings/0.1 (+https://github.com/Peter-A-P/...)        connection reset
#     python-httpx/0.28.1                                     connection reset
#
# CBC's edge refuses a user agent containing a URL, which is to say it refuses the one
# convention designed to make a crawler identifiable. Its robots.txt permits the feed paths
# and names no rule against this project, so the refusal is a filter rather than a decision,
# and dropping the URL is not going around anything: the product token, the version and the
# purpose are all still here and all still true.
#
# "How to ask it to stop" survives intact, because the mechanism was never the URL. A
# publisher writes `User-agent: clippings` in robots.txt, and `clippings.sources.robots`
# checks that token on every request.
USER_AGENT: Final = "clippings/0.1 news digest research"
