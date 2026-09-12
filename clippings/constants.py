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

# Every model call this project makes is over public sources only.
GATEWAY_DATA_CLASS: Final = "public"

# One user agent for every outbound request, so a publisher reading its logs can see who this
# is and how to ask it to stop.
USER_AGENT: Final = (
    "clippings/0.1 (+https://github.com/Peter-A-P/department-news-digest) news digest research"
)
