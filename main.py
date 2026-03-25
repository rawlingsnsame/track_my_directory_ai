import time
import typer

from rich import print
from router import route
from model import answer
from rich.rule import Rule
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
            console.print(f"[dim]figuring out what to look at...[/dim]")
            tools_needed = route(query)

            if not tools_needed:
                console.print("[yellow]Warning: couldn't determine what to look at. Try rephrasing.[/yellow]")
                return
            
            console.print(f"[dim]gathering context with tools: {', '.join(tools_needed)}...[/dim]")

            context = {}

            for tool_name in tools_needed:
                if tool_name in TOOLS:
                    context[tool_name] = TOOLS[tool_name](repo_path)
            
            console.print(f"[dim]answering question...[/dim]\n")
            response = answer(query, context)
            console.print(Panel(response, title="Answer", subtitle="Based on the gathered context"))
            return  # Success! Exit the function.
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
            console.print("\n[yellow]Goodbye![/yellow]")
            return False
        
        if user_query.lower() == "back":
            console.print("[yellow]Going back to repository selection...[/yellow]")
            return True

        if user_query.lower() in {"exit", "quit"}:
            console.print("[yellow]Goodbye![/yellow]")
            return False
        
        run(user_query, repo_path)

@app.command()
def main():
    console.clear()
    console.print(Panel.fit(
        "[bold cyan]Welcome to the Repository Reporter![/bold cyan]\n\n" \
        "[dim]Monitoring code changes and commit intent[/dim]\n\n",
        border_style="cyan",
        title="Repo Reporter",
    ))

    while True:
        try:
            path_input = console.input("[bold magenta]Enter the path to a git repository (or 'exit' to quit): [/bold magenta]").strip()

            if not path_input:
                continue

            if not is_git_repo(path_input):
                console.print(f"[red]Error: '{path_input}' does not have a valid git repository. Please try again.[/red]")
                continue

            console.print(
                f"\n[bold green]✓[/bold green] Found git repo: "
                f"[bold underline]{path_input}[/bold underline]\n"
            )
            console.print(get_directory_tree(path_input))
            console.print(Rule(style="dim"))
            console.print("[dim]Type your question, 'back' to change directory, or 'exit' to quit.[/dim]\n")

            should_continue = query_loop(path_input)
            if not should_continue:
                break

        except KeyboardInterrupt:
            console.print("\n[red]Process interrupted by user. Exiting.[/red]")
            break

if __name__ == "__main__":
    main()