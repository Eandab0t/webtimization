"""`python -m webtim` behaves like the `webtim` command, including in `--help` output."""
from webtim.cli import main

if __name__ == "__main__":
    main(prog_name="webtim")
