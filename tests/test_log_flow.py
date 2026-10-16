from pathlib import Path

from valorant_switcher.logs import LogTailer, parse_line
from valorant_switcher.state import Coordinator


SAMPLE = """[2026.09.20-07.48.05:462][310]LogShooterGameState: Warning: AShooterGameState::OnRoundEnded for round '0'
[2026.09.20-07.48.05:692][335]LogShooterGameState: Warning: Gameplay started at local time 0.000000 (server time 0.000000)
[2026.09.20-07.48.35:721][923]LogShooterGameState: Warning: Gameplay started at local time 30.171875 (server time 30.292187)
[2026.09.20-07.49.04:697][446]LogShooterGameState: Warning: AShooterGameState::OnRoundEnded for round '1'
[2026.09.20-07.49.04:918][460]LogShooterGameState: Warning: Gameplay started at local time 0.007812 (server time 0.000000)
[2026.09.20-07.49.34:953][820]LogShooterGameState: Warning: Gameplay started at local time 30.164062 (server time 30.292187)
"""


def test_cn_round_transitions_and_no_historical_action(tmp_path: Path):
    path = tmp_path / "ShooterGame.log"
    path.write_text(SAMPLE, encoding="utf-8")
    tailer = LogTailer(path)
    assert tailer.baseline() == "combat"
    assert tailer.poll() == []  # launch during combat does not replay earlier shopping
    with path.open("a", encoding="utf-8") as stream:
        stream.write("AShooterGameState::OnRoundEnded for round '2'\n")
        stream.write("Gameplay started at local time 0.015625 (server time 0.000000)\n")
    assert [event.kind for event in tailer.poll()] == ["ended", "shopping"]


def test_log_partial_line_and_truncation(tmp_path: Path):
    path = tmp_path / "ShooterGame.log"
    path.write_text("", encoding="utf-8")
    tailer = LogTailer(path)
    tailer.baseline()
    with path.open("ab") as stream:
        stream.write(b"Gameplay started at local time 0.0")
    assert tailer.poll() == []
    with path.open("ab") as stream:
        stream.write(b" (server time 0.000000)\n")
    assert [event.kind for event in tailer.poll()] == ["shopping"]
    path.write_text("Gameplay started at local time 30.1 (server time 30.2)\n", encoding="utf-8")
    assert [event.kind for event in tailer.poll()] == ["combat"]


def test_ambiguous_gameplay_lines_not_shopping():
    assert parse_line("Gameplay started at local time 30.1 (server time 30.2)").kind == "combat"
    assert parse_line("Gameplay started at local time 5 (server time 0.000000)") is None


def test_skirmish_2v2_short_buy_phase(tmp_path: Path):
    mode = "LogMapLoadModel: Update: [URL: x?game=/Game/GameModes/Skirmish/SkirmishGameMode.SkirmishGameMode_C#8311]"
    assert parse_line(mode).mode == "round_based"
    assert parse_line("Gameplay started at local time 4.179688 (server time 4.292188)") is None
    path = tmp_path / "ShooterGame.log"
    path.write_text(mode + "\nGameplay started at local time 0.000000 (server time 0.000000)\n", encoding="utf-8")
    tailer = LogTailer(path)
    assert tailer.baseline() == "shopping"
    assert tailer.mode == "round_based"
    with path.open("a", encoding="utf-8") as stream:
        stream.write("Gameplay started at local time 4.179688 (server time 4.292188)\n")
        stream.write("AShooterGameState::OnRoundEnded for round '1'\n")
    assert [event.kind for event in tailer.poll()] == ["combat", "ended"]


def test_mode_gate_distinguishes_round_match_from_short_skirmish(tmp_path: Path):
    supported = "LogMapLoadModel: Update: [URL: x?game=/Game/GameModes/Bomb/BombGameMode.BombGameMode_C#123]"
    swiftplay = "LogMapLoadModel: Update: [URL: x?game=/Game/GameModes/_Development/Swiftplay_EndOfRoundCredits/Swiftplay_EoRCredits_GameMode.Swiftplay_EoRCredits_GameMode_C#123]"
    unsupported = "LogMapLoadModel: Update: [URL: x?game=/Game/GameModes/Deathmatch/DeathmatchGameMode.DeathmatchGameMode_C#123]"
    assert parse_line(supported).mode == "round_based"
    assert parse_line(swiftplay).mode == "round_based"
    assert parse_line(unsupported).mode == "unsupported"
    path = tmp_path / "ShooterGame.log"
    path.write_text(unsupported + "\nGameplay started at local time 0.000000 (server time 0.000000)\n", encoding="utf-8")
    tailer = LogTailer(path)
    assert tailer.baseline() == "shopping"
    assert tailer.mode == "unsupported"


def test_death_once_then_return_only_at_next_shopping():
    state = Coordinator(actions_enabled=True)
    state.on_phase("combat")
    assert state.on_frame("alive", game_foreground=True) == []
    assert state.on_frame("dead", game_foreground=True) == []
    assert state.on_frame("dead", game_foreground=True) == ["open_edge"]
    assert state.on_frame("dead", game_foreground=True) == []
    assert state.on_phase("ended") == []
    assert state.on_phase("shopping") == ["return_game"]
    assert state.on_phase("shopping") == []
    state.on_phase("combat")
    assert state.on_frame("dead", game_foreground=True) == []  # no proven alive state


def test_unknown_frames_and_lost_focus_clear_confirmation():
    state = Coordinator(actions_enabled=True)
    state.on_phase("combat")
    state.on_frame("alive", game_foreground=True)
    state.on_frame("dead", game_foreground=True)
    state.on_frame("unknown", game_foreground=True)
    state.on_frame("dead", game_foreground=True)
    state.on_frame("dead", game_foreground=False)
    assert state.on_frame("dead", game_foreground=True) == []
    assert not state.death_sent


def test_shadow_mode_records_without_switching():
    state = Coordinator(actions_enabled=False)
    state.on_phase("combat")
    state.on_frame("alive", game_foreground=True)
    for _ in range(3):
        assert state.on_frame("dead", game_foreground=True) == []
    assert state.death_sent
    assert state.on_phase("shopping") == []
