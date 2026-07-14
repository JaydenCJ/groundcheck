"""Tokenizer and normalization: the foundation every check stands on."""

from __future__ import annotations

from groundcheck.textnorm import fold_chars, tokenize, word_key


def test_tokens_carry_exact_offsets_into_the_original_text():
    text = "Reads hit the cache."
    tokens = tokenize(text)
    assert [t.text for t in tokens] == ["Reads", "hit", "the", "cache"]
    for t in tokens:
        assert text[t.start : t.end] == t.text


def test_punctuation_and_empty_input_yield_no_word_tokens():
    tokens = tokenize("wait -- really?! (yes; truly...)")
    assert [t.norm for t in tokens] == ["wait", "really", "yes", "truly"]
    assert tokenize("") == []
    assert tokenize("   \n\t ") == []


def test_casefold_makes_matching_case_insensitive():
    assert [t.key for t in tokenize("CACHE Cache cache")] == ["cache"] * 3


def test_curly_quotes_and_dashes_fold_to_ascii():
    folded = fold_chars("“smart” — ‘quotes’ – here")
    assert folded == '"smart" - \'quotes\' - here'
    # Folding is length-preserving so offsets survive.
    assert len(folded) == len("“smart” — ‘quotes’ – here")


def test_number_keys_are_canonicalized():
    (tok,) = tokenize("1,000")
    assert tok.is_number
    assert tok.key == "1000"  # thousands separators stripped
    assert tokenize("1000")[0].key == "1000"
    assert tokenize("3.50")[0].key == "3.5"  # trailing zeros dropped
    assert tokenize("12.0")[0].key == "12"


def test_percent_sign_stays_in_norm_but_not_in_key():
    (tok,) = tokenize("40%")
    assert tok.norm == "40%"
    assert tok.key == "40"  # so "40%" aligns with "40 percent"
    assert tokenize("40 %")[0].norm == "40%"  # spaced percent is one token


def test_possessive_and_cheap_plural_fold_to_the_bare_noun():
    assert tokenize("the company's")[1].key == "company"
    assert tokenize("the company’s")[1].key == "company"  # curly apostrophe
    assert word_key("caches") == word_key("cache")
    assert word_key("less") == "less"  # -ss words are left alone
    assert word_key("was") == "was"  # too short to fold


def test_hyphenated_words_are_single_tokens():
    (tok,) = tokenize("write-through")
    assert tok.key == "write-through"


def test_unicode_words_survive_and_fullwidth_forms_normalize():
    tokens = tokenize("naïve café résumé")
    assert [t.norm for t in tokens] == ["naïve", "café", "résumé"]
    # NFKC: fullwidth "ＡＰＩ" compares equal to "api".
    assert tokenize("ＡＰＩ")[0].norm == "api"
