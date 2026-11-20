"""Entry point for python -m akko_ctl; preserve caller's working directory."""

from .cli import main

raise SystemExit(main())
