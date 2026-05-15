"""Shell-integration scripts for ``b``.

Emits a small wrapper function (named ``b``) that lets the CLI
binary `cd` the *parent shell* into a target directory, instead of
forking off a sub-shell at that directory (which is the fallback
when the wrapper isn't installed). The handshake is a temp file:

    wrapper:  mktemp → export HOMEBASE_CD_FILE=$f → command b "$@"
    binary :  open_shell_in_dir(p) → write str(p) to $HOMEBASE_CD_FILE
              instead of os.execvp(...)
    wrapper:  cat $f → builtin cd that path → rm $f

Same pattern as zoxide / direnv / pyenv: leaves stdout/stderr/stdin
fully untouched so the interactive picker, y/N prompts, and live
summaries the binary already prints aren't disturbed.
"""

from __future__ import annotations


def shell_init_script(shell: str) -> str:
    """Return the wrapper script for ``shell`` (bash / zsh / fish)."""
    value = str(shell).strip().lower()
    if value in {"bash", "zsh"}:
        return _bash_zsh_init_script()
    if value == "fish":
        return _fish_init_script()
    raise ValueError(f"unsupported shell: {shell}")


def _bash_zsh_init_script() -> str:
    # POSIX-compatible body; works identically in bash and zsh.
    # Install with:
    #   bash:  b shell-init bash >> ~/.bashrc
    #   zsh:   b shell-init zsh  >> ~/.zshrc
    return """# homebase shell integration — wrap `b` so the parent shell can cd.
# Install: append this script to ~/.bashrc or ~/.zshrc and re-source.
b() {
    local f
    f=$(mktemp) || { command b "$@"; return $?; }
    HOMEBASE_CD_FILE="$f" command b "$@"
    local rc=$?
    if [ -s "$f" ]; then
        local d
        d=$(cat "$f")
        [ -d "$d" ] && builtin cd "$d"
    fi
    rm -f "$f"
    return $rc
}
"""


def _fish_init_script() -> str:
    # Install: `b shell-init fish > ~/.config/fish/conf.d/b.fish`
    # conf.d/ files are sourced once at every shell startup, which is
    # the idiomatic location for shell-integration scripts (matches
    # zoxide / starship / direnv conventions). functions/ would also
    # work via lazy autoload, but conf.d/ keeps the function with the
    # rest of the user's shell-init customizations.
    return """# homebase shell integration — wrap `b` so the parent shell can cd.
# Install: b shell-init fish > ~/.config/fish/conf.d/b.fish
function b
    set -l f (mktemp)
    if test $status -ne 0
        command b $argv
        return $status
    end
    HOMEBASE_CD_FILE=$f command b $argv
    set -l rc $status
    if test -s $f
        set -l d (cat $f)
        if test -d $d
            builtin cd $d
        end
    end
    rm -f $f
    return $rc
end
"""
