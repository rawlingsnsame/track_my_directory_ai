import sys
import time
import typer

from rich.rule import Rule
from agent.agent import run_agent
from rich.panel import Panel
from dotenv import load_dotenv
from rich.console import Console
from gatherer import is_git_repo, get_directory_tree, TOOLS

load_dotenv()
console = Console()
app = typer.Typer()

MAX_RETRIES = 3
RETRY_DELAY = 2

def run(query: str, repo_path: str) -> None:
    """
    Execute one full cycle of the agent: route, gather context, and answer.
    Retries the whole process up to MAX_RETRIES times if it fails.
    """
    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            run_agent(query, repo_path)
            return
        except KeyboardInterrupt:
            console.print("\n[red]Process interrupted by user. Exiting.[/red]")
            return
        except Exception as e:
            last_error = e
            if attempt < MAX_RETRIES:
                console.print(
                    f"[yellow] → attempt {attempt} failed: {e}. "
                    f"Retrying in {RETRY_DELAY}s...[/yellow]"
                )
                time.sleep(RETRY_DELAY)
            else:
                console.print(
                    f"[bold red]Error:[/bold red] Failed after {MAX_RETRIES} attempts. "
                    f"Last error: {last_error}"
                )


def query_loop(repo_path: str) -> bool:
    """
    Main loop: ask the user for a question, run the agent, and repeat.
    """
    while True:
        try:
            user_query = console.input("[bold magenta]❯ [/bold magenta]").strip()
        except KeyboardInterrupt:
            console.print("\n[yellow]Returning to zila shell...![/yellow]") # Return to zila shell
            sys.exit(0)
        
        if not user_query:
            continue

        if user_query.lower() == "back":
            console.print("[yellow]Returning to ZILA shell...[/yellow]")
            sys.exit(0)

        if user_query.lower() in {"exit", "quit"}:
            console.print("[yellow]Goodbye![/yellow]")
            sys.exit(0)

        run(user_query, repo_path)

@app.command()
def main(
    path: str = typer.Argument(
        ..., 
        help="Absolute path to the curriculum directory for analysis.",
        show_default=False,
    ),
    ) -> None:
    
    if not is_git_repo(path):
        console.print(
            f"[bold red]Error:[/bold red] "
            f"'{path}' is not a valid git repository.\n"
            f"Run [bold cyan]zila init[/bold cyan] to set up your workspace." 
        )
        sys.exit(1)

    console.print(Panel.fit(
        "[bold cyan]ZILA Assistant[/bold cyan]\n\n"
        "[dim]Your AI companion for the ML & AI curriculum.[/dim]\n"
        f"[dim]Workspace: {path}[/dim]",
        border_style="cyan",
        title="Assistant",
    ))

    # Show directory tree so the student knows what's loaded 
    console.print(get_directory_tree(path))
    console.print(Rule(style="dim"))

    # Enter the conversation loop 
    query_loop(path)

if __name__ == "__main__":
    app()