"""Nothing is sent, and the test is what makes that a fact rather than an intention.

PLAN.md section 8 and the repository rules: no email, chat or notification path exists, no
mail client is a dependency, and a test asserts it. This is the test. It fails if anyone,
including a future version of this project, adds a way to send.

Two checks, because either alone is weak. The first reads every import in the package: a
send path has to import something. The second reads the installed dependency graph: a
library that can send is a temptation even before it is called.
"""

from __future__ import annotations

import ast
import importlib.metadata
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parents[1] / "clippings"

# Modules that send. `email` itself is absent from this list on purpose: the .eml draft the
# owner may send by hand is built with `email.message`, which constructs a message and has
# no transport. `smtplib` is the transport, and it is banned.
SENDING_MODULES = frozenset(
    {
        "smtplib",
        "imaplib",
        "poplib",
        "aiosmtplib",
        "aiosmtpd",
        "yagmail",
        "sendgrid",
        "mailjet_rest",
        "postmarker",
        "mailchimp_transactional",
        "slack_sdk",
        "slack_bolt",
        "discord",
        "twilio",
        "pywhatkit",
        "win32com",
        "exchangelib",
        "O365",
        "msgraph",
        "notify_run",
        "pushbullet",
        "apprise",
    }
)

# Distributions that exist to send messages. Checked against everything installed, not only
# against what this project declares, because a transitive dependency is still a dependency.
SENDING_DISTRIBUTIONS = frozenset(
    {
        "aiosmtplib",
        "aiosmtpd",
        "sendgrid",
        "yagmail",
        "mailjet-rest",
        "postmarker",
        "mailchimp-transactional",
        "slack-sdk",
        "slack-bolt",
        "discord.py",
        "twilio",
        "exchangelib",
        "o365",
        "msgraph-sdk",
        "msgraph-core",
        "apprise",
        "notify-run",
        "pushbullet.py",
        "python-telegram-bot",
    }
)


def imported_modules(path: Path) -> set[str]:
    """Every top-level module name imported by a source file."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module.split(".")[0])
    return names


@pytest.mark.parametrize("path", sorted(PACKAGE.rglob("*.py")), ids=lambda path: path.name)
def test_no_module_that_can_send_is_imported(path: Path) -> None:
    offending = imported_modules(path) & SENDING_MODULES
    assert not offending, (
        f"{path.relative_to(PACKAGE.parent)} imports {sorted(offending)}. "
        "Nothing in this project sends. Delivery is a page and a draft file."
    )


def test_no_mail_client_is_installed() -> None:
    installed = {
        (distribution.metadata["Name"] or "").lower()
        for distribution in importlib.metadata.distributions()
    }
    offending = installed & {name.lower() for name in SENDING_DISTRIBUTIONS}
    assert not offending, (
        f"a library that can send messages is installed: {sorted(offending)}. "
        "No mail or messaging client is a dependency of this project."
    )


def test_there_is_no_send_command() -> None:
    """The CLI has no verb that delivers anything to a person."""
    from clippings import cli

    commands = {
        command.callback.__name__
        for command in cli.app.registered_commands
        if command.callback is not None
    }
    forbidden = {"send", "email", "mail", "notify", "post", "publish_to"}
    assert not commands & forbidden, (
        f"the CLI grew a sending command: {sorted(commands & forbidden)}"
    )


def test_the_package_contains_no_smtp_configuration() -> None:
    """No host, port or credential for a mail server anywhere in the source."""
    needles = ("smtp.", "SMTP_HOST", "MAIL_SERVER", "sendmail", "SMTP_PASSWORD")
    for path in PACKAGE.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for needle in needles:
            assert needle not in text, f"{path.name} mentions {needle!r}"
