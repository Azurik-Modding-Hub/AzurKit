"""Byte-safe failure output (``tests/_byte_safe.py``): a failing test never
prints long bytes, however its output shows them."""

from __future__ import annotations

import hashlib
import time

DATA = bytes(range(256)) * 16  # 4 KiB whose repr, text and hex are easy to spot
SPOTS = ("\\x00\\x01\\x02\\x03", "ABCDEFGHIJ", "\\xfd\\xfe", DATA[:0x30].hex(),
         "0123456789:;<=>?@", "\\\\x00\\\\x01\\\\x02\\\\x03", "quick brown fox jumps")


def test_failure_output_shows_no_long_bytes_in_any_run(pytester):
    """A failing test's output never shows long bytes, with or without
    ``--ci-full``: a plain ``assert`` on long bytes reports lengths, hash
    prefixes and the first differing offset, and each failure report is
    redacted. AZ-230: only ``--ci-full`` redacted reports, so a local run
    printed a traceback's function arguments (a timeout in a randomizer
    test printed the start of a level .xbr from a ``data`` argument),
    assertion rewriting's ``where`` values, ``-l``'s locals (which
    ``-vv`` wraps into short adjacent literals) and ``unittest``'s
    ``assertEqual`` messages, which no assert hook sees. In every run an
    ``assert`` on a list or dict holding the bytes printed pytest's own
    diff of them, and ``unittest`` shortened a dict's repr past its
    ``b'`` and kept 41 characters of the bytes. AZ-253: a str holding a
    bytes repr was redacted only in its own repr, which escapes the
    literal past the pattern, so pytest's str diff and ``unittest``'s
    shortened message printed it. AZ-261: a str's repr was still printed
    as a traceback argument, inside a container and as a ``where`` value,
    and a str's own text kept a repr cut off at its end, glued to a word
    (``"x" + repr(data)``) or a quote (``f"got '{data!r}'"``) or
    JSON-encoded. Text the redaction can't encode (a lone surrogate) never
    aborts the run, and a printable repr after an unclosed quote
    (``"`x`'s header: b'ABC…'"``) stays redacted. AZ-283: a str's repr
    glued to a word (``x'b\\'…'``) or after an unbalanced quote
    (``a ' and 'b\\'…'``) was not read back, and a printable bytes repr
    glued to a word (``xb'ABC…'``) or a quote (``'b'ABC…''``) was not
    found, so each printed. AZ-297: nor was a str's repr or a JSON string
    after a lone quote of the other kind (``a " and 'b\\'…'``, ``a ' and
    "b'…\\"…'"``), one whose bytes end in
    a non-word character and ``b`` (``a ' and "b'…!b'"``), or a glued
    printable repr in ``b"…"``, with a word after it, after ``rb``,
    starting ``s`` and a space, or inside a quoted word. AZ-297's
    residual: nor was one of those mid-line whose bytes start as prose or
    source (``s`` and a space, ``-``, ``/``, ``.`` or a space). AZ-433, the
    rest of it: nor one that also reads like words (a space or more per 40
    characters)."""
    pytester.makepyfile("""
        import json
        import unittest
        DATA = bytes(range(256)) * 16
        OTHER = DATA[:0x123] + b"!" + DATA[0x124:]

        def scan(data):
            raise TimeoutError("no match")

        def test_assert():
            assert DATA == OTHER

        def test_a_helper_times_out_on_its_argument():
            scan(DATA)

        def test_an_assert_explains_its_operands():
            data = DATA
            assert len(data) == 0

        def test_an_assert_on_lists():
            assert [DATA] == [OTHER]

        def test_an_assert_on_reprs():
            assert repr(DATA) == repr(OTHER)

        def test_a_helper_times_out_on_a_repr():
            scan(repr(DATA))

        def test_an_assert_on_lists_of_reprs():
            assert [repr(DATA)] == [repr(OTHER)]

        def test_an_assert_explains_a_repr_it_calls():
            assert not repr(DATA).startswith("b")

        def test_an_assert_on_cut_reprs():
            assert repr(DATA)[:3000] == repr(OTHER)[:3000]

        def test_an_assert_on_a_glued_repr():
            assert "x" + repr(DATA) == "x" + repr(OTHER)

        def test_an_assert_on_json():
            assert json.dumps(str(DATA)) == json.dumps(str(OTHER))

        def test_an_error_quotes_reprs():
            raise ValueError(f"got '{DATA!r}', want " + f'"{OTHER!r}"')

        def test_an_error_quotes_a_name_before_a_printable_repr():
            raise ValueError(f"`x`'s header: {bytes(range(65, 91)) * 2!r}")

        def test_an_error_glues_a_word_to_a_repr_of_a_repr():
            raise ValueError("x" + repr(repr(DATA)))

        def test_an_error_quotes_a_repr_after_an_unbalanced_quote():
            raise ValueError("a ' and " + repr(repr(DATA)))

        def test_an_error_glues_a_word_to_a_printable_repr():
            raise ValueError("x" + repr(bytes(range(65, 91)) * 2))

        def test_an_error_quotes_a_printable_repr():
            raise ValueError(f"got '{bytes(range(65, 91)) * 2!r}'")

        PRINT = bytes(range(65, 91)) * 2

        def test_an_error_quotes_a_repr_after_a_lone_quote_of_the_other_kind():
            raise ValueError('a " and ' + repr(repr(DATA)))

        def test_an_error_quotes_json_after_a_lone_quote_of_the_other_kind():
            raise ValueError("a ' and " + json.dumps(repr(DATA)))

        def test_an_error_quotes_a_repr_whose_bytes_end_in_a_b():
            raise ValueError("a ' and " + repr(repr(bytes(b for b in range(32, 97) if b not in (34, 39)) + b"!b")))

        def test_an_error_glues_a_word_to_a_printable_repr_in_double_quotes():
            raise ValueError("x" + repr(b"It's " + PRINT))

        def test_an_error_glues_words_to_both_sides_of_a_printable_repr():
            raise ValueError(f"x{PRINT!r}y")

        def test_an_error_glues_rb_to_a_printable_repr():
            raise ValueError("rb" + repr(PRINT)[1:])

        def test_an_error_glues_a_word_to_a_printable_repr_starting_s_and_a_space():
            raise ValueError("x" + repr(b"s " + PRINT))

        def test_an_error_quotes_a_word_glued_to_a_printable_repr():
            raise ValueError("'x" + repr(PRINT) + "'")

        def test_an_error_glues_mid_line_printable_reprs_that_start_as_prose():
            reprs = [repr(head + PRINT) for head in (b"s ", b"-", b"/", b".", b" ")]
            raise ValueError("\\n".join(f"x{r}y\\nrb{r[1:]} as\\n'x{r}' tail" for r in reprs))

        WORDS = b"the quick brown fox jumps over the lazy dog"

        def test_an_error_glues_mid_line_printable_reprs_that_read_like_words():
            reprs = [repr(head + WORDS) for head in (b"-", b"s, ", b"/", b".", b" ")]
            raise ValueError("\\n".join(f"x{r}y and x{r}: tail" for r in reprs))

        def test_an_assert_on_undecodable_text():
            assert (b"b'" + DATA[128:256] + b"'").decode("utf-8", "surrogateescape") == ""

        class Unittest(unittest.TestCase):
            maxDiff = None

            def test_assert_equal(self):
                self.assertEqual(DATA, OTHER)

            def test_assert_equal_on_dicts(self):
                self.assertEqual({"k": DATA}, {"k": OTHER})

            def test_assert_equal_on_reprs(self):
                self.assertEqual(repr(DATA), repr(OTHER))
    """)
    digest = f"<4096 bytes, sha256 {hashlib.sha256(DATA).hexdigest()[:12]}>"
    for args in ((), ("-l", "-vv")):
        result = pytester.runpytest("-p", "tests._byte_safe", *args)
        result.assert_outcomes(failed=31)
        out = result.stdout.str()
        assert digest in out
        assert "first differing offset 0x123" in out
        assert [s for s in SPOTS if s in out] == [], args


def test_failure_output_keeps_source_text_that_quotes_b_before_an_empty_literal():
    """AZ-283's quote form, a printable bytes repr between two quotes
    (``'b'ABC…''``), also took source that quotes a one-letter ``'b'``
    and ends on an empty literal (``if 'b' in mode: … return b''``), on
    one line or in a str's one-line repr, for a bytes repr, and digested
    it: a traceback's source line or a str comparison (whose own diff
    pytest then drops) lost its text. Such text keeps it."""
    from tests._byte_safe import _redact

    for source in ("if 'b' in self._mode:\n            return b''\n",
                   "mode = 'b' if the_file_is_opened_as_binary_data else ''",
                   "parts = ('b', len(header) + offset_of_the_first_record, b'')"):
        for text in (source, repr(source)):
            assert _redact(text) == text


def test_failure_output_redacts_a_long_one_line_repr_in_linear_time():
    """AZ-298: a str literal was tried from every escaped quote of a
    one-line repr, each try running to the line's end once a bytes
    literal's start had stopped the repr's own literal, so a 1.4 MB repr
    took about a minute. An escaped quote opens no literal: four times the
    line takes about four times as long, where a quadratic takes sixteen,
    on any host's speed. CPU time (``process_time``), as a loaded host adds
    waiting, not work (AZ-231); the quicker of two runs, for a shared host's
    other noise."""
    from tests._byte_safe import _redact

    def took(quotes: int) -> float:
        text = repr("it's " * quotes + ' b"x"')   # the escaped quotes, then a bytes start
        runs = []
        for _ in range(2):
            t0 = time.process_time()
            assert _redact(text) == text
            runs.append(time.process_time() - t0)
        return min(runs)
    short, long = took(58_250), took(233_000)   # 0.35 MB and 1.4 MB
    assert long < 8 * short, (short, long)
