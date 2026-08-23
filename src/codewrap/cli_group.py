import click
from typer.core import TyperGroup


class GlobalOptionsGroup(TyperGroup):
    """Group that parses global options placed after positional arguments and
    routes bare subcommand invocations (e.g. 'codewrap config show') correctly."""

    _directory_param = "directory"

    def parse_args(self, ctx: click.Context, args: list[str]) -> list[str]:
        if args and args[0] in self.commands:
            return self._parse_subcommand(ctx, args)
        if args:
            args = self._hoist_options(ctx, args)
        return super().parse_args(ctx, args)

    def _parse_subcommand(self, ctx: click.Context, args: list[str]) -> list[str]:
        original_params = list(self.params)
        self.params = [p for p in self.params if getattr(p, "name", None) != self._directory_param]
        try:
            return super().parse_args(ctx, args)
        finally:
            self.params = original_params

    def _hoist_options(self, ctx: click.Context, args: list[str]) -> list[str]:
        known: dict[str, click.Option] = {}
        for param in self.get_params(ctx):
            if isinstance(param, click.Option):
                for token in (*param.opts, *param.secondary_opts):
                    known[token] = param

        front: list[str] = []
        tail: list[str] = []
        i = 0
        while i < len(args):
            token = args[i]
            if token == "--" or not token.startswith("-"):
                tail.append(token)
                i += 1
                continue

            option = known.get(token.split("=", 1)[0])
            if option is None:
                tail.append(token)
                i += 1
                continue

            front.append(token)
            i += 1
            if "=" not in token and not option.is_flag and i < len(args):
                front.append(args[i])
                i += 1
        return front + tail
