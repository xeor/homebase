from __future__ import annotations


def load_open_mode_config(
    data: object,
    *,
    default_profile: str,
    known_profiles: set[str],
) -> dict[str, str]:
    out = {"profile": default_profile}
    raw = data.get("open_mode", {}) if isinstance(data, dict) else {}
    if not isinstance(raw, dict):
        return out

    profile = str(raw.get("profile", "")).strip()
    if profile in known_profiles:
        out["profile"] = profile
        return out

    use_tmux = bool(raw.get("use_tmux_tab", False))
    run_load = bool(raw.get("run_tmux_load", False))
    goto_loaded = bool(raw.get("goto_existing_loaded", False))
    if not use_tmux:
        out["profile"] = "shell_cd"
    elif run_load and goto_loaded:
        out["profile"] = "tmux_tab_load_or_goto"
    elif run_load:
        out["profile"] = "tmux_tab_load"
    else:
        out["profile"] = "tmux_tab"
    return out


def save_open_mode_config(
    data: object,
    conf: dict[str, str],
    *,
    default_profile: str,
    known_profiles: set[str],
) -> dict[str, object]:
    out = dict(data) if isinstance(data, dict) else {}
    profile = str(conf.get("profile", default_profile)).strip() or default_profile
    if profile not in known_profiles:
        profile = default_profile
    out["open_mode"] = {"profile": profile}
    return out
