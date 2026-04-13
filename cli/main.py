# Phase 2 — CLI not implemented in Phase 1
# Run: pip install -e . then: careercore --help
import typer

app = typer.Typer(help="CareerCore CLI — Phase 2")


if __name__ == "__main__":
    app()
