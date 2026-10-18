"""
#470: the StartOS package never tells anyone that public price sites don't
see their IP address without saying the exception. Since #241, once the
owner says Yes to downloading the price history without Tor, Bitstamp's
history downloads go directly and Bitstamp sees the server's address. The
Tor dependency's description (shown in the store before install) said
"so they never see your IP address" in all five languages while the Use Tor
action already said "unless you let BitcoinTX download Bitstamp's price
history without Tor".

The texts checked are every string of the manifest (`manifest/i18n.ts`) and
of the dictionaries the actions, tasks, health checks and interfaces use
(`i18n/dictionaries/`, English and the four translations), sentence by
sentence: the exception belongs in the sentence that makes the promise.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "startos" / "startos"
FILES = [
    SRC / "manifest" / "i18n.ts",
    SRC / "i18n" / "dictionaries" / "default.ts",
    SRC / "i18n" / "dictionaries" / "translations.ts",
]

# Per language: how it names the IP address (which also tells the text's
# language), the words that deny seeing it or say it's hidden, and the
# exception's words.
LANGUAGES = {
    "en": (
        r"\bIP address",
        r"\b(never|not|no|(do|does|ca|wo)n['’]t|hides?|hidden)\b",
        "without Tor",
    ),
    "es": (r"\bdirección IP\b", r"\b(nunca|no|jamás|ocult\w*)\b", "sin Tor"),
    "de": (
        r"\bIP-Adresse\b",
        r"\b(nie|niemals|nicht|kein\w*|verb[io]rg\w*|versteck\w*)\b",
        "ohne Tor",
    ),
    "pl": (r"\badres(u|em|y|ów)? IP\b", r"\b(nigdy|nie|ukry\w*)\b", "bez Tora"),
    "fr": (r"\badresse IP\b", r"\b(jamais|pas|masqu\w*|cach\w*)\b", "sans Tor"),
}

# A sentence ends at . ! or ? before a space, or at a line break (`\n`
# written in the string); a clause also at a comma, colon and the like.
SENTENCE_END = re.compile(r"(?<=[.!?])\s+|\\n")
CLAUSE_END = re.compile(r"[.,;:!?()]|\\n")
STRING = re.compile(r"'((?:[^'\\\n]|\\.)*)'|\"((?:[^\"\\\n]|\\.)*)\"")


def package_sentences():
    """Every sentence of every string literal of the files the package's
    texts live in."""
    for path in FILES:
        source = "\n".join(
            line
            for line in path.read_text(encoding="utf-8").splitlines()
            if not line.lstrip().startswith(("//", "*", "/*"))
        )
        for match in STRING.finditer(source):
            for sentence in SENTENCE_END.split(match.group(1) or match.group(2) or ""):
                yield path.name, sentence


def promises_hidden_ip(text):
    """The languages in which `text` says the IP address isn't seen: a
    clause naming it that also denies or hides (so "they see your IP
    address ..., never your transaction dates" is no such promise)."""
    found = set()
    for clause in CLAUSE_END.split(text):
        for lang, (ip, deny, _) in LANGUAGES.items():
            if re.search(ip, clause) and re.search(deny, clause, re.IGNORECASE):
                found.add(lang)
    return found


def names_the_exception(text, lang):
    return "Bitstamp" in text and LANGUAGES[lang][2] in text


PROMISES = [
    (name, lang, sentence)
    for name, sentence in package_sentences()
    for lang in promises_hidden_ip(sentence)
]


def test_the_check_sees_the_tor_texts_in_every_language():
    """The Tor dependency's description and the Use Tor action each make
    the promise in all five languages, so a check finding fewer would be
    reading the files wrongly, not passing."""
    expected = (
        {("i18n.ts", lang) for lang in LANGUAGES}
        | {("default.ts", "en")}
        | {("translations.ts", lang) for lang in LANGUAGES if lang != "en"}
    )
    assert expected <= {(name, lang) for name, lang, _ in PROMISES}


@pytest.mark.parametrize(
    "name, lang, text", PROMISES, ids=[f"{n}-{lang}" for n, lang, _ in PROMISES]
)
def test_no_text_hides_the_ip_address_without_the_exception(name, lang, text):
    assert names_the_exception(text, lang), (
        f"{name} ({lang}) says public price sites don't see the IP address "
        f"but not that Bitstamp's price history may go without Tor: {text}"
    )


def test_the_tor_dependency_says_the_exception_in_every_language():
    source = (SRC / "manifest" / "i18n.ts").read_text(encoding="utf-8")
    block = re.search(r"export const torDescription = \{(.*?)\n\}", source, re.S)
    assert block, "torDescription not found in manifest/i18n.ts"
    texts = {
        lang: single or double
        for lang, single, double in re.findall(
            r"(\w\w)_\w\w:\s*(?:'([^'\n]*)'|\"([^\"\n]*)\")", block.group(1)
        )
    }
    assert set(texts) == set(LANGUAGES)
    for lang, text in texts.items():
        assert names_the_exception(text, lang), (lang, text)
