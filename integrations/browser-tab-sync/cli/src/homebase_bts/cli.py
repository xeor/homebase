"""Typer CLI. See IDEA.md "CLI commands"."""

from __future__ import annotations

import os
import socket
import uuid
from pathlib import Path

import typer

from homebase_bts import __version__, config, installer, profileio
from homebase_bts.backends.local import LocalBackend
from homebase_bts.backends.native import HostUnavailable, NativeBackend
from homebase_bts.models import Profile, SyncMode
from homebase_bts.protocol import ProfileSnapshot, WatchProfile, recv_frame, send_frame
from homebase_bts.reconcile import ApplyResult, MergeSummary, merge_snapshot, plan, result_from_plan

app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    help="Manage browser tab-group profiles from files.",
)
native = typer.Typer(help="Native messaging host install/management.")
app.add_typer(native, name="native-host")

ProfileArg = typer.Argument(
    ".",
    metavar="PROFILE",
    help="Profile file or folder. Folders resolve to .base-bts.yaml by default.",
)
LocalOpt = typer.Option(
    False,
    "--local",
    help="Use the file-backed simulator instead of the real browser.",
)
ExtensionIdOpt = typer.Option(..., help="Extension ID allowed to connect.")
BrowserOpt = typer.Option(
    ..., "--browser", help="Single browser variant to install into (e.g. chromium)."
)
ExtensionDirOpt = typer.Option(
    ..., "--extension-dir", help="WXT chrome output dir; its absolute path determines the ID."
)
ManifestDirOpt = typer.Option(
    ...,
    "--manifest-dir",
    help="NativeMessagingHosts dir to write into (the dev profile's, not a machine variant).",
)


def _backend(local: bool) -> LocalBackend | NativeBackend:
    return LocalBackend(config.sim_store()) if local else NativeBackend(config.host_sock())


def _snapshot(impl: LocalBackend | NativeBackend, prof: Profile) -> ProfileSnapshot | None:
    if isinstance(impl, LocalBackend):
        return impl.snapshot(prof.id)
    return impl.snapshot(prof)


def _run_apply(profile: str, local: bool, dry_run: bool) -> None:
    path, prof, impl = _load_command(profile, local)
    try:
        if dry_run:
            dry_result = result_from_plan(prof, plan(prof, _snapshot(impl, prof)), applied=False)
            typer.echo(dry_result.render(prof.title or prof.id, source=path))
            return
        result: ApplyResult = impl.apply(prof, dry_run=dry_run)
        typer.echo(result.render(prof.title or prof.id, source=path))
        if not dry_run and isinstance(impl, NativeBackend) and prof.sync.mode is SyncMode.two_way:
            impl.enable_sync(prof.id, str(path.resolve()), _group_title(prof))
            typer.echo("  sync:    two-way enabled (host writes the file while the browser runs)")
    except HostUnavailable as exc:
        raise typer.BadParameter(str(exc)) from exc


def _load_command(profile: str, local: bool) -> tuple[Path, Profile, LocalBackend | NativeBackend]:
    path = profileio.resolve(profile)
    return path, profileio.load(path), _backend(local)


def _group_title(prof: Profile) -> str:
    return prof.group.title or prof.title or prof.id


def _render_export(title: str, summary: MergeSummary, path: Path) -> str:
    return "\n".join(
        [
            title,
            f"  file:    {path.name} ({'updated' if summary.changed else 'unchanged'})",
            f"  tabs:    {summary.kept} kept, {summary.added} added, {summary.removed} removed",
            f"  group:   {'updated' if summary.group_changed else 'unchanged'}",
        ]
    )


@app.command()
def apply(
    profile: str = ProfileArg,
    local: bool = LocalOpt,
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Print the plan without changing browser state."
    ),
) -> None:
    """Reconcile the browser to match the profile (idempotent).

    Executes by default. Re-running is safe and reuses existing tabs.
    """
    _run_apply(profile, local, dry_run)


@app.command()
def focus(profile: str = ProfileArg) -> None:
    """Focus an existing profile/group/window without creating missing tabs."""
    prof = profileio.load(profileio.resolve(profile))
    impl = NativeBackend(config.host_sock())
    try:
        result = impl.focus(prof)
    except HostUnavailable as exc:
        raise typer.BadParameter(str(exc)) from exc
    state = "focused" if result.focused else "not focused"
    typer.echo(
        "\n".join(
            [
                prof.title or prof.id,
                f"  browser: {prof.browser.preferred.value}",
                f"  group:   {_group_title(prof)}",
                f"  focus:   {state} ({prof.group.focus})",
            ]
        )
    )


@app.command()
def export(profile: str = ProfileArg, local: bool = LocalOpt) -> None:
    """Snapshot actual browser state back into the file (atomic write)."""
    path, prof, impl = _load_command(profile, local)
    try:
        snapshot = _snapshot(impl, prof)
    except HostUnavailable as exc:
        raise typer.BadParameter(str(exc)) from exc
    if snapshot is None:
        raise typer.BadParameter(f"group not found: {_group_title(prof)}")
    merged, summary = merge_snapshot(prof, snapshot)
    if prof.model_dump() != merged.model_dump():
        profileio.write_atomic(path, merged)
    typer.echo(_render_export(prof.title or prof.id, summary, path))


@app.command()
def status(profile: str = ProfileArg, local: bool = LocalOpt) -> None:
    """Show diff between desired and actual state."""
    path, prof, impl = _load_command(profile, local)
    try:
        snapshot = _snapshot(impl, prof)
    except HostUnavailable as exc:
        raise typer.BadParameter(str(exc)) from exc
    result = result_from_plan(prof, plan(prof, snapshot), applied=False)
    typer.echo(result.render(prof.title or prof.id, source=path))


@app.command()
def debug(profile: str = ProfileArg) -> None:
    """Read-only: print live group snapshots for a profile (writes nothing).

    Two-way sync is enabled by `apply` and runs in the host; this just lets you
    watch what the extension reports on each change. Ctrl-C to stop.
    """
    path = profileio.resolve(profile)
    prof = profileio.load(path)

    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.connect(str(config.host_sock()))
    except (FileNotFoundError, ConnectionRefusedError) as exc:
        raise typer.BadParameter(
            "native host not reachable — is the browser running? run `homebase-bts doctor`"
        ) from exc

    typer.echo(f"debug {prof.id!r} (group {_group_title(prof)!r}); Ctrl-C to stop")
    with sock:
        send_frame(
            sock,
            WatchProfile(
                request_id=str(uuid.uuid4()),
                profile_id=prof.id,
                group_title=_group_title(prof),
                debug=True,
            ),
        )
        try:
            while True:
                msg = recv_frame(sock)
                if msg is None:
                    typer.echo("host closed the connection")
                    break
                if isinstance(msg, ProfileSnapshot):
                    urls = ", ".join(t.url for t in msg.tabs)
                    typer.echo(f"snapshot: {len(msg.tabs)} tabs [{urls}]")
        except KeyboardInterrupt:
            typer.echo("\nstopped")


@app.command()
def doctor() -> None:
    """Check native host install, extension origin, and live socket."""
    ok = True
    for check in installer.doctor():
        mark = "ok " if check.ok else "FAIL"
        ok = ok and check.ok
        typer.echo(f"[{mark}] {check.name}: {check.detail}")
    if not ok:
        raise typer.Exit(code=1)


@native.command("install")
def native_install(
    extension_id: str = ExtensionIdOpt,
    browser: installer.Browser = BrowserOpt,
) -> None:
    """Write the native messaging manifest into one browser variant."""
    path = installer.install_native_host(extension_id, browser=browser)
    typer.echo(f"wrote {path}")


@native.command("install-dev")
def native_install_dev(
    extension_dir: str = ExtensionDirOpt,
    manifest_dir: str = ManifestDirOpt,
) -> None:
    """Install the manifest into the dev profile, computing the extension ID itself."""
    ext_id = installer.extension_id_for_path(Path(os.path.abspath(extension_dir)))
    path = installer.install_native_host(ext_id, directory=Path(os.path.abspath(manifest_dir)))
    typer.echo(f"dev extension id: {ext_id}")
    typer.echo(f"wrote {path}")


@native.command("uninstall")
def native_uninstall() -> None:
    """Remove the native messaging manifest."""
    for path in installer.uninstall_native_host():
        typer.echo(f"removed {path}")


@app.command()
def version() -> None:
    typer.echo(__version__)
