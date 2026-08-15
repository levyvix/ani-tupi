from utils.mpv.log_manager import MPVLogManager


def test_detects_mp4_that_ends_before_decoding_data() -> None:
    log_output = "[v][cplayer] got EOF with no data before it"

    assert MPVLogManager.has_mpv_load_error("", log_output) is True


def test_classifies_early_eof_as_source_failure() -> None:
    log_output = "[v][cplayer] got EOF with no data before it"

    assert MPVLogManager.classify_mpv_error("", log_output) == (
        "Falha ao carregar vídeo nesta fonte."
    )
