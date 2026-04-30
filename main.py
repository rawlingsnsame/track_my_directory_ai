"""
ZILA Assistant - Main Entry Point

AI companion for the ML & AI curriculum.
Handles user queries by routing to appropriate tools and gathering context.
"""
import sys
import os
import io
import time
import logging
from typing import Optional

# Force UTF-8 encoding before any I/O operations
if sys.platform == "win32":
    os.environ["PYTHONIOENCODING"] = "utf-8"
    try:
        sys.stdin.reconfigure(encoding="utf-8")
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, io.UnsupportedOperation):
        sys.stdin = open(sys.stdin.fileno(), "r", encoding="utf-8", buffering=1)
        sys.stdout = open(sys.stdout.fileno(), "w", encoding="utf-8", buffering=1)
        sys.stderr = open(sys.stderr.fileno(), "w", encoding="utf-8", buffering=1)

import typer
from rich.rule import Rule
from rich.panel import Panel
from rich.console import Console
from rich.logging import RichHandler
from dotenv import load_dotenv

# Load environment variables early
load_dotenv()

# Configure logging.
# We use DEBUG here so that all log levels (debug, info, warning, error) are
# visible during development. The RichHandler formats them cleanly in the
# terminal. Change to logging.WARNING in production if you want silence.
logging.basicConfig(
    level=logging.DEBUG,
    format="%(message)s",
    handlers=[RichHandler(rich_tracebacks=True, show_time=False, show_path=False)],
)

# Quiet down noisy third-party loggers that get pulled in at DEBUG level
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)

log = logging.getLogger("zila")

# Import after logging setup so child loggers inherit the configuration
from agent.agent import run_agent
from gatherer import is_git_repo, get_directory_tree

console = Console()
app = typer.Typer()

# Configuration constants
MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds


def run(query: str, repo_path: str) -> None:
    """
    Execute one full cycle of the agent: route, gather context, and answer.
    Retries the whole process up to MAX_RETRIES times if it fails.
    """
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            run_agent(query, repo_path)
            return
        except KeyboardInterrupt:
            console.print("\n[red]Interrupted.[/red]")
            raise
        except Exception as e:
            log.debug(f"Attempt {attempt} failed: {type(e).__name__}: {e}")

            if attempt < MAX_RETRIES:
                console.print(
                    f"[yellow]Attempt {attempt} failed: {type(e).__name__}. "
                    f"Retrying in {RETRY_DELAY}s...[/yellow]"
                )
                time.sleep(RETRY_DELAY)
            else:
                console.print(
                    f"[bold red]Error:[/bold red] Failed after {MAX_RETRIES} attempts. "
                    f"Last error: {type(e).__name__}: {e}"
                )


def query_loop(repo_path: str) -> int:
    """
    Main loop: ask the user for a question, run the agent, and repeat.
    Returns exit code (0 for normal exit, 1 for error).
    """
    while True:
        try:
            try:
                user_query = console.input("[bold magenta]❯ [/bold magenta]").strip()
            except UnicodeEncodeError:
                user_query = console.input("[bold magenta]> [/bold magenta]").strip()

        except KeyboardInterrupt:
            console.print("\n[yellow]Returning to ZILA shell...[/yellow]")
            return 0
        except EOFError:
            # stdin was closed — this can happen if the parent process dies
            console.print("\n[yellow]Input stream closed. Exiting...[/yellow]")
            return 1

        if not user_query:
            continue

        if user_query.lower() == "back":
            console.print("[yellow]Returning to ZILA shell...[/yellow]")
            return 0

        if user_query.lower() in {"exit", "quit"}:
            console.print("[yellow]Goodbye![/yellow]")
            return 0

        try:
            run(user_query, repo_path)
        except Exception as e:
            console.print(f"[bold red]Query failed:[/bold red] {e}")
            log.exception("Query execution failed")


@app.command()
def main(
    path: str = typer.Argument(
        ...,
        help="Absolute path to the curriculum directory for analysis.",
        show_default=False,
    ),
) -> None:
    """
    Launch the ZILA Assistant for the given curriculum directory.

    The directory must be a valid git repository.
    """
    exit_code = 0

    try:
        if not os.path.exists(path):
            console.print(f"[bold red]Error:[/bold red] Path does not exist: {path}")
            exit_code = 1
            return

        if not is_git_repo(path):
            console.print(
                f"[bold red]Error:[/bold red] "
                f"'{path}' is not a valid git repository.\n"
                f"Run [bold cyan]zila init[/bold cyan] to set up your workspace."
            )
            exit_code = 1
            return

        console.print(Panel.fit(
            "[bold cyan]ZILA Assistant[/bold cyan]\n\n"
            "[dim]Your AI companion for the ML & AI curriculum.[/dim]\n"
            f"[dim]Workspace: {path}[/dim]\n\n"
            "[dim]Type [bold]back[/bold] to return to ZILA shell.[/dim]",
            border_style="cyan",
            title="Assistant",
        ))

        try:
            tree = get_directory_tree(path)
            if tree:
                console.print(tree)
        except Exception as e:
            log.warning(f"Could not display directory tree: {e}")

        console.print(Rule(style="dim"))

        exit_code = query_loop(path)

    except Exception as e:
        console.print(f"[bold red]Fatal error:[/bold red] {e}")
        log.exception("Fatal error in main")
        exit_code = 1
    finally:
        sys.exit(exit_code)


if __name__ == "__main__":
    app()