"""Phonetic narration spans (spec §6.3): IPA, X-SAMPA, Pinyin and Jyutping to IPA phonemes."""

from __future__ import annotations

import re
import threading
import unicodedata

PHONETIC_STYLES = {"ipa", "x-sampa", "pinyin", "jyutping"}

# X-SAMPA -> IPA, matched longest first (backslash and diacritic forms before single characters)
XSAMPA = {
    "r\\`": "ɻ", "s\\": "ɕ", "z\\": "ʑ", "j\\": "ʝ", "J\\": "ɟ", "G\\": "ɢ", "h\\": "ɦ", "K\\": "ɮ",
    "R\\": "ʀ", "r\\": "ɹ", "l\\": "ɺ", "v\\": "ʋ", "x\\": "ɧ", "4\\": "ɺ", ":\\": "ˑ", "@`": "ɚ", "3`": "ɝ",
    "_h": "ʰ", "_j": "ʲ", "_w": "ʷ", "_0": "̥", "_~": "̃",
    "a": "a", "A": "ɑ", "{": "æ", "6": "ɐ", "Q": "ɒ", "e": "e", "E": "ɛ", "@": "ə", "3": "ɜ", "i": "i",
    "I": "ɪ", "o": "o", "O": "ɔ", "2": "ø", "9": "œ", "&": "ɶ", "u": "u", "U": "ʊ", "}": "ʉ", "V": "ʌ",
    "y": "y", "Y": "ʏ", "1": "ɨ", "8": "ɵ", "7": "ɤ", "M": "ɯ",
    "p": "p", "b": "b", "t": "t", "d": "d", "k": "k", "g": "ɡ", "q": "q", "G": "ɣ", "?": "ʔ", "m": "m",
    "F": "ɱ", "n": "n", "J": "ɲ", "N": "ŋ", "r": "r", "R": "ʁ", "4": "ɾ", "B": "β", "f": "f", "v": "v",
    "T": "θ", "D": "ð", "s": "s", "z": "z", "S": "ʃ", "Z": "ʒ", "C": "ç", "x": "x", "X": "χ", "h": "h",
    "K": "ɬ", "P": "ʋ", "j": "j", "l": "l", "L": "ʎ", "5": "ɫ", "w": "w", "H": "ɥ", "W": "ʍ", "c": "c",
    '"': "ˈ", "%": "ˌ", ":": "ː", "'": "ʲ", "~": "̃", "=": "̩", "`": "˞", ".": ".",
}
_XSAMPA_KEYS = sorted(XSAMPA, key=len, reverse=True)


def xsampa_to_ipa(text: str) -> str:
    out, i = [], 0
    while i < len(text):
        for key in _XSAMPA_KEYS:
            if text.startswith(key, i):
                out.append(XSAMPA[key])
                i += len(key)
                break
        else:
            out.append(text[i])
            i += 1
    return "".join(out)


def normalize_ipa(text: str) -> str:
    """User IPA in the form the speech models expect: no delimiters, syllable dots or tie bars."""
    text = text.strip().strip("/[]")
    text = text.replace("͡", "").replace("͜", "").replace(".", "")
    text = text.replace("g", "ɡ").replace("'", "ˈ").replace(":", "ː")
    return " ".join(text.split())


_TONE_MARKS = {"̄": "1", "́": "2", "̌": "3", "̀": "4"}


def pinyin_numbers(text: str) -> str:
    """`Běi jīng` or `bei 3 - jing 1` -> `bei3 jing1` (tone numbers, which espeak reads)."""
    text = re.sub(r"([A-Za-zÜü]+)\s*([1-5])\b", r"\1\2", text.replace(" - ", " "))
    syllables = []
    for syllable in text.split():
        decomposed = unicodedata.normalize("NFD", syllable)
        tone = next((_TONE_MARKS[c] for c in decomposed if c in _TONE_MARKS), "")
        plain = "".join(c for c in decomposed if c not in _TONE_MARKS)
        plain = unicodedata.normalize("NFC", plain).replace("ü", "v").replace("Ü", "V")
        syllables.append(plain + tone if tone and not plain[-1:].isdigit() else plain)
    return " ".join(syllables).lower()


JYUTPING_INITIALS = {
    "gw": "kʷ", "kw": "kʷʰ", "ng": "ŋ", "b": "p", "p": "pʰ", "m": "m", "f": "f", "d": "t", "t": "tʰ",
    "n": "n", "l": "l", "g": "k", "k": "kʰ", "h": "h", "w": "w", "z": "ts", "c": "tsʰ", "s": "s", "j": "j",
}
JYUTPING_FINALS = {
    "aa": "aː", "aai": "aːi", "aau": "aːu", "aam": "aːm", "aan": "aːn", "aang": "aːŋ", "aap": "aːp",
    "aat": "aːt", "aak": "aːk", "a": "ɐ", "ai": "ɐi", "au": "ɐu", "am": "ɐm", "an": "ɐn", "ang": "ɐŋ",
    "ap": "ɐp", "at": "ɐt", "ak": "ɐk", "e": "ɛː", "ei": "ei", "eu": "ɛːu", "em": "ɛːm", "eng": "ɛːŋ",
    "ep": "ɛːp", "ek": "ɛːk", "i": "iː", "iu": "iːu", "im": "iːm", "in": "iːn", "ing": "ɪŋ", "ip": "iːp",
    "it": "iːt", "ik": "ɪk", "o": "ɔː", "oi": "ɔːy", "ou": "ou", "on": "ɔːn", "ong": "ɔːŋ", "ot": "ɔːt",
    "ok": "ɔːk", "oe": "œː", "oeng": "œːŋ", "oek": "œːk", "eoi": "ɵy", "eon": "ɵn", "eot": "ɵt",
    "u": "uː", "ui": "uːy", "un": "uːn", "ung": "ʊŋ", "ut": "uːt", "uk": "ʊk", "yu": "yː", "yun": "yːn",
    "yut": "yːt", "m": "m̩", "ng": "ŋ̩",
}
_SUPERSCRIPTS = str.maketrans("¹²³⁴⁵⁶", "123456")


def jyutping_to_ipa(text: str) -> str:
    """Cantonese Jyutping (`hoeng1 gong2`, `Hoeng¹ Gong²`) -> IPA; tones are dropped."""
    text = re.sub(r"([a-z]+)\s*([1-6])\b", r"\1\2", text.translate(_SUPERSCRIPTS).lower().replace(" - ", " "))
    out = []
    for syllable in text.split():
        body = syllable.rstrip("123456")
        if body in JYUTPING_FINALS:  # syllabic m / ng, or a vowel-initial syllable
            out.append(JYUTPING_FINALS[body])
            continue
        initial = next((i for i in sorted(JYUTPING_INITIALS, key=len, reverse=True) if body.startswith(i)), "")
        final = JYUTPING_FINALS.get(body[len(initial):])
        out.append(JYUTPING_INITIALS.get(initial, "") + final if final else body)
    return " ".join(out)


_tokenizer = None
_tokenizer_lock = threading.Lock()


def phonemize(text: str, espeak_language: str) -> str:
    """espeak phonemes for text (the tokenizer serialises espeak itself)."""
    global _tokenizer
    with _tokenizer_lock:
        if _tokenizer is None:
            from kokoro_onnx.tokenizer import Tokenizer

            _tokenizer = Tokenizer()
    return _tokenizer.phonemize(text, espeak_language)


def to_ipa(text: str, style: str) -> str:
    """IPA phonemes for a phonetic span."""
    if style == "ipa":
        return normalize_ipa(text)
    if style == "x-sampa":
        return normalize_ipa(xsampa_to_ipa(text))
    if style == "pinyin":
        return phonemize(pinyin_numbers(text), "cmn")
    if style == "jyutping":
        return normalize_ipa(jyutping_to_ipa(text))
    raise ValueError(f"not a phonetic style: {style!r}")
