import numpy as np
import pytest

from narrate.phonetics import jyutping_to_ipa, normalize_ipa, pinyin_numbers, to_ipa, xsampa_to_ipa
from narrate.tts import ElevenLabsSynth, Voice


def test_xsampa():
    assert xsampa_to_ipa('t@"meIt@U') == "təˈmeɪtəʊ"
    assert xsampa_to_ipa("r\\`") == "ɻ" and xsampa_to_ipa("t_h") == "tʰ"


def test_normalize_ipa():
    assert normalize_ipa("/tə'meɪ.toʊ/") == "təˈmeɪtoʊ"
    assert normalize_ipa("t͡ʃiːz") == "tʃiːz" and normalize_ipa("go:") == "ɡoː"


@pytest.mark.parametrize("text", ["Běi jīng", "bei3 jing1", "bei 3 - jing 1"])
def test_pinyin_forms_agree(text):
    assert pinyin_numbers(text) == "bei3 jing1"
    assert to_ipa(text, "pinyin") == to_ipa("bei3 jing1", "pinyin")


@pytest.mark.parametrize("text", ["hoeng1 gong2", "Hoeng¹ Gong²", "hoeng 1 - gong 2"])
def test_jyutping_forms_agree(text):
    assert jyutping_to_ipa(text) == "hœːŋ kɔːŋ"


def test_elevenlabs_phonetic_segments_use_a_phoneme_tag(monkeypatch, tmp_path):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    monkeypatch.setenv("NARRATE_CACHE", str(tmp_path))
    synth = ElevenLabsSynth()
    calls = []
    monkeypatch.setattr(synth, "_post", lambda v, body: calls.append(body) or np.zeros(240, "<i2").tobytes())
    notes: set[str] = set()
    synth.synth((("Americans say", None), ("təˈmeɪ.toʊ", "ipa")), Voice("x" * 20, None), 1.0, notes)
    assert calls[0]["model_id"] == "eleven_multilingual_v2"
    assert calls[1] == {"text": '<phoneme alphabet="ipa" ph="təˈmeɪtoʊ">təˈmeɪtoʊ</phoneme>',
                        "model_id": "eleven_flash_v2"}
    assert any("eleven_flash_v2" in n for n in notes)


@pytest.mark.kokoro
def test_kokoro_pronounces_ipa(monkeypatch, tmp_path):
    from narrate.tts import MODEL_FILES, KokoroSynth, kokoro_resolve, model_dir

    if not (model_dir() / MODEL_FILES[0]).exists():
        pytest.skip("Kokoro model files not downloaded")
    monkeypatch.setenv("NARRATE_CACHE", str(tmp_path))
    synth = KokoroSynth()
    spoken = []
    real = synth._engine().create
    monkeypatch.setattr(synth._engine(), "create", lambda p, **kw: spoken.append(p) or real(p, **kw))
    voice = kokoro_resolve("bf_emma", None, set())
    us = synth.synth((("Americans say", None), ("təˈmeɪ.toʊ", "ipa")), voice, 1.0, set())
    uk = synth.synth((("Americans say", None), ("tʰə̥ˈmɑːtʰəʊ", "ipa")), voice, 1.0, set())
    assert "təˈmeɪtoʊ" in spoken[0] and "ˈmɑː" in spoken[1] and len(us) != len(uk)
