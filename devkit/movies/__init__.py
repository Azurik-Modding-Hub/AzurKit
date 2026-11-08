"""the movie tools: a Bink movie's header read, and its frames written as PNGs by ffmpeg

Modkit's ``azurik-mod movies`` verbs, ported in Step 4.6l; each verb's
reference is ``devkit/movies/README.md``."""

VERBS = {
    "info": "a .bik movie's size, frames, rate, length and audio tracks, or a folder's in a table",
    "frames": "a .bik movie's frame offsets and keyframes, or its frames as PNGs into a new folder by ffmpeg",
}
