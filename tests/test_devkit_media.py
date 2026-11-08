"""devkit's movie and audio tools, ``python -m devkit movies`` and ``audio``
(``devkit/movies/``, ``devkit/audio/``, Step 4.6l; Modkit's ``movies`` and
``audio`` verbs and their test_movies and test_audio_and_plugins, leanly):
a Bink header and its frame table read at each track layout, ffmpeg run
only into a new folder and named when missing or failing, every wave of an
XBR classified, written and wrapped as the game decodes it, named from the
archive's own table, with no byte in its manifest; then the game's 14
movies and its two sound banks."""

from __future__ import annotations

import hashlib
import json
import struct
import subprocess
from pathlib import Path

import pytest

from azurkit.core import iso
from devkit.audio import dump
from devkit.movies import frames, info


def bik(frames_at: list[int], end: int, tracks: int = 1, per_track: int = 16, size: int = 0) -> bytes:
    """A Bink 1 file: its header (640x480 at 30 fps), ``tracks`` audio track
    descriptors of ``per_track`` bytes, then the frame table (each offset,
    the first a keyframe, then ``end``), zero-filled to ``size``."""
    out = bytearray(struct.pack("<4s10I", b"BIKi", 0, len(frames_at), 64, len(frames_at), 640, 480, 30, 1, 0, tracks))
    out += bytes(per_track * tracks) + struct.pack(f"<{len(frames_at) + 1}I", frames_at[0] | 1, *frames_at[1:], end)
    return bytes(out.ljust(size, b"\0"))


def run(capsys, verb, *argv) -> tuple[int, str, str]:
    code = verb.main([str(a) for a in argv])
    out, err = capsys.readouterr()
    return code, out, err


def test_movies_info_reads_a_bink_header_and_a_folders_table_and_refuses_by_name(tmp_path, capsys):
    """The header's frames (its second count), size, rate and tracks give
    the length; a folder is a table of each .bik it can read; a file of
    another magic, one shorter than the header and a missing one are one
    line, exit 1."""
    (tmp_path / "a.bik").write_bytes(bik(list(range(64, 364)), 400, size=400))
    (tmp_path / "notes.bik").write_bytes(b"not a movie" * 8)
    one = info.inspect_bink_file(tmp_path / "a.bik")
    assert (one.resolution, one.frame_count, one.fps, one.duration_seconds, one.audio_track_count) == (
        "640x480", 300, 30.0, 10.0, 1)
    code, out, _ = run(capsys, info, tmp_path)
    assert code == 0 and "a.bik" in out and "notes.bik" not in out and "Total: 1 files" in out
    for path, why in ((tmp_path / "notes.bik", "bad magic"), (tmp_path / "short.bik", "too small"),
                      (tmp_path / "gone.bik", "no such file")):
        if why == "too small":
            path.write_bytes(b"BIKi")
        code, _, err = run(capsys, info, path)
        assert code == 1 and len(err.splitlines()) == 1 and err.startswith("movies info: ") and why in err


def test_movies_frames_reads_the_frame_table_at_each_layout_and_runs_ffmpeg_only_into_a_new_folder(
        tmp_path, capsys, monkeypatch):
    """The frame table follows 16-byte track descriptors (the game's) or
    12-byte ones (an earlier Bink), told by where its first offset points;
    its low bits mark keyframes. Extracting needs --out (D36, Modkit's
    AZ-179) that isn't the input, names ffmpeg when it isn't on PATH
    (AZ-226) and, when ffmpeg fails, its last lines, removing the folder it
    made (AZ-147); --dry-run prints the command."""
    for per_track, start in ((16, 76), (12, 72)):
        movie = tmp_path / f"m{per_track}.bik"
        movie.write_bytes(bik([start, start + 4, start + 14], start + 24, per_track=per_track, size=start + 24))
        table = frames.describe_bink(movie)
        assert (table.offsets, table.keyframes, table.frame_size(2)) == ((start, start + 4, start + 14), (0,), 10)
    (tmp_path / "x.bik").write_bytes(b"RIFF" + bytes(60))
    assert run(capsys, frames, tmp_path / "x.bik", "--info")[0] == 1
    movie, out = tmp_path / "m16.bik", tmp_path / "frames"
    calls = []
    monkeypatch.setattr(frames.subprocess, "run", lambda *a, **k: calls.append(a))
    monkeypatch.setattr(frames.shutil, "which", lambda name: f"/bin/{name}")
    for argv, why in (((), "pass --out DIR"), (("--out", movie), "it is the input")):
        code, _, err = run(capsys, frames, movie, *argv)
        assert code == 1 and err.startswith("movies frames: ") and why in err and not calls
    code, text, _ = run(capsys, frames, movie, "--out", out, "--dry-run")
    assert code == 0 and f"command: /bin/ffmpeg -y -i {movie} -vf format=rgb24 {out}/frame_%04d.png" in text
    assert not out.exists() and not calls

    def fail(*a, **k):
        raise subprocess.CalledProcessError(1, a[0], stderr=b"banner\nline 1\nline 2\nInvalid data found")
    monkeypatch.setattr(frames.subprocess, "run", fail)
    code, _, err = run(capsys, frames, movie, "--out", out)
    assert code == 1 and "ffmpeg failed with exit 1: line 1 / line 2 / Invalid data found" in err and not out.exists()
    monkeypatch.setattr(frames.shutil, "which", lambda name: None)
    code, _, err = run(capsys, frames, movie, "--out", out)
    assert code == 1 and err.startswith("movies frames: ffmpeg is not on PATH") and not out.exists()


def xbr(entries: list[tuple[bytes, bytes]], names: dict[int, str]) -> bytes:
    """An XBR of ``entries`` (tag, payload) whose named rows give ``names``
    (TOC index: name), its pool ending the file."""
    start = 0x3C + 16 * len(entries)
    out = bytearray(start)
    out[:4] = b"xobx"
    struct.pack_into("<II", out, 0x0C, len(entries), start)
    for k, (tag, body) in enumerate(entries):
        struct.pack_into("<II4sI", out, 0x3C + 16 * k, len(out) - start, len(body), tag, 0)
        out += body
    pool = b"".join(name.encode() + b"\0" for name in names.values())
    rows, at = b"", 0
    for index, name in names.items():
        rows, at = rows + struct.pack("<II", index, at), at + len(name) + 1
    struct.pack_into("<IIII", out, 0x2C, len(names), len(out), len(out) + len(rows), len(pool))
    return bytes(out + rows + pool)


def test_audio_dump_classifies_each_wave_wraps_what_decodes_and_names_it(tmp_path, capsys):
    """An inline 22050 Hz mono Xbox ADPCM wave, a streamed one (HM-83: its
    samples in the sdsr its 20 bytes name), a duplicate, one too small, one
    with a TOC tag inside and one the game's parser refuses (codec 2) take
    their classes; each that decodes gets a WAV of its codec's bytes alone,
    each its archive's own name (AZ-217); the manifest holds a sha256 of
    each entry's first bytes, never the bytes; --only-audio and
    --entropy-min list but don't write; --raw-previews wraps the non-audio
    one; a file that isn't an XBR is one line, exit 1."""
    head = struct.pack("<IIBBBBI", 22050, 128, 1, 4, 0, 1, 0)
    samples = bytes(range(72))
    streamed = struct.pack("<IIBBBBI", 22050, 128, 1, 4, 1, 1, 0) + struct.pack("<I", 6)
    refused = struct.pack("<IIBBBBI", 22050, 128, 1, 4, 0, 2, 0) + bytes(range(100, 172))
    entries = [(b"wave", head + samples), (b"wave", streamed), (b"wave", head + samples), (b"wave", bytes(10)),
               (b"wave", b"node" + bytes(80)), (b"wave", refused), (b"sdsr", samples)]
    fx = tmp_path / "fx.xbr"
    fx.write_bytes(xbr(entries, {0: "fx/sound/a/one", 5: "fx/sound/a/odd"}))
    code, out, _ = run(capsys, dump, fx, "-o", tmp_path / "out", "--raw-previews", "--json")
    report = json.loads(out)
    got = [(e["classification"], e.get("name", ""), e.get("duplicate_of", -1), e.get("streamed_sdsr", -1),
            "wav_output" in e, "preview_wav" in e) for e in report["entries"]]
    assert code == 0 and got == [("xbox-adpcm", "fx/sound/a/one", -1, -1, True, False),
                                 ("xbox-adpcm", "", -1, 6, True, False), ("xbox-adpcm", "", 0, -1, True, False),
                                 ("too-small", "", -1, -1, False, False),
                                 ("likely-animation", "", -1, -1, False, False),
                                 ("non-audio", "fx/sound/a/odd", -1, -1, False, True)]
    assert report["entries"][5]["first_bytes_sha256"] == hashlib.sha256(refused[:32]).hexdigest()[:12]
    assert "first_bytes_hex" not in out and json.loads((tmp_path / "out" / "manifest.json").read_text()) == report
    for k in (0, 1):
        wav = (tmp_path / "out" / f"waves/wave_000{k}.wav").read_bytes()
        assert wav[:4] == b"RIFF" and wav.endswith(samples)
        assert struct.unpack_from("<I", wav, wav.index(b"data") + 4)[0] == len(samples)
        assert struct.unpack_from("<HHIIHHHH", wav, 20) == (0x69, 1, 22050, 12403, 36, 4, 2, 64)
    assert (tmp_path / "out/waves/wave_0001.bin").read_bytes() == streamed[:16] + samples
    preview = (tmp_path / "out/waves/wave_0005.preview.wav").read_bytes()
    assert struct.unpack_from("<HHIIHH", preview, 20) == (1, 1, 22050, 44100, 2, 16) and preview.endswith(refused)
    code, out, _ = run(capsys, dump, fx, "-o", tmp_path / "only", "--only-audio", "--entropy-min", 0.9)
    assert code == 0 and "blobs written to disk:   0" in out and "xbox-adpcm:           3" in out
    assert sorted(p.name for p in (tmp_path / "only/waves").iterdir()) == []
    code, out, _ = run(capsys, dump, fx, "-o", tmp_path / "audio", "--only-audio", "--no-wav")
    assert sorted(p.name for p in (tmp_path / "audio/waves").iterdir()) == [
        "wave_0000.bin", "wave_0001.bin", "wave_0002.bin"]
    code, _, err = run(capsys, dump, tmp_path / "out/manifest.json", "-o", tmp_path / "x")
    assert code == 1 and len(err.splitlines()) == 1 and err.startswith("audio dump: ")


@pytest.mark.parametrize("bank, waves, streamed, named", [("fx", 700, 31, 574), ("english", 234, 134, None)])
def test_the_media_verbs_read_the_games_movies_and_sound_banks(usa_iso, tmp_path, bank, waves, streamed, named):
    """The USA image's 14 movies are 640x480 at 30 fps with one audio
    track, AdreniumLogo 573 frames (19.1 s, its frame table read whole);
    every wave of fx.xbr and english.xbr is Xbox ADPCM and gets a WAV, the
    streamed ones from their sdsr, fx.xbr's 574 named from its own table."""
    with iso.Reader(usa_iso) as r:
        data = r.read(f"gamedata/{bank}.xbr")
        if bank == "fx":
            for e in r.entries():
                if e.path.startswith("movies/") and e.path.endswith(".bik"):
                    whole = e.path.endswith("AdreniumLogo.bik")   # its frame table is read whole; the rest's headers
                    (tmp_path / e.path.rpartition("/")[2]).write_bytes(r.read(e) if whole else r.range(e, 0, 4096))
    if bank == "fx":
        infos = info.inspect_directory(tmp_path)
        assert len(infos) == 14 and {(i.resolution, i.fps, i.audio_track_count) for i in infos} == {
            ("640x480", 30.0, 1)}
        logo = frames.describe_bink(tmp_path / "AdreniumLogo.bik")
        assert (len(logo.offsets), round(logo.info.duration_seconds, 1), len(logo.keyframes)) == (573, 19.1, 1)
    (tmp_path / f"{bank}.xbr").write_bytes(data)
    report = dump.dump_waves(tmp_path / f"{bank}.xbr", tmp_path / "out")
    assert (report.total_waves, report.counts["xbox-adpcm"], report.wav_written) == (waves, waves, waves)
    assert sum(e.streamed_sdsr >= 0 for e in report.entries) == streamed
    if named:
        count, table, pool = struct.unpack_from("<III", data, 0x2C)
        own = {}
        for k in range(count):
            index, at = struct.unpack_from("<II", data, table + 8 * k)
            own[index] = data[pool + at:data.index(b"\0", pool + at)].decode("ascii")
        toc = [k for k in range(struct.unpack_from("<I", data, 0x0C)[0])
               if data[0x3C + 16 * k + 8:0x3C + 16 * k + 12] == b"wave"]
        assert {e.index: e.name for e in report.entries if e.name} == {
            i: own[k] for i, k in enumerate(toc) if k in own} and len([e for e in report.entries if e.name]) == named
