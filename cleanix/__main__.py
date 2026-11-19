import sys

from .cli import main_cli, parse


def main() -> int:
    args = parse()
    if args.clean or args.analyze or args.list:
        return main_cli(args)
    from .ui.app import run_gui
    return run_gui()


if __name__ == "__main__":
    sys.exit(main())
