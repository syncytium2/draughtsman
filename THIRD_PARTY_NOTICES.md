# Third-party notices

This repository is BSD-3-Clause. One file in it is derived from software under a
different licence, and this is where that is said.

## OpenAI Whisper — `examples/gallery/whisper_tiny.py`

[`examples/gallery/whisper_tiny.py`](examples/gallery/whisper_tiny.py) writes out
Whisper `tiny` in PyTorch so that the gallery has an encoder--decoder to trace. It
was written **following OpenAI's reference implementation**, not merely the
published dimensions, and the resemblance is not incidental: the module names
(`MultiHeadAttention`, `ResidualAttentionBlock`, `AudioEncoder`), the attribute
names (`attn_ln`, `cross_attn`, `mlp_ln`, `ln_post`, `positional_embedding`), the
`sinusoids()` helper and its signature, the key projection carrying no bias, and
the pre-norm residual pairs are all that implementation's.

**What is not taken.** There is no tokenizer, no multilingual head, no timestamp
logic, no KV cache, no decoding loop and no weights -- the weights are random,
because the file exists to be *traced* rather than run. `sinusoids()` uses `math`
where the original uses numpy, because nothing else in this gallery imports numpy.

Upstream: <https://github.com/openai/whisper>. Its licence, in full and unaltered:

```
MIT License

Copyright (c) 2022 OpenAI

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

The MIT licence asks that the notice above accompany copies and substantial
portions. Whether a reduced reimplementation for tracing is a substantial portion
is arguable, and this repository does not want the argument: the notice is here
either way, which costs nothing and settles it.

**This file travels with the source distribution.** The wheel contains
`src/draughtsman` only, so the derived file is not in it; the sdist carries the
whole tree, including `examples/`, and therefore carries this.
