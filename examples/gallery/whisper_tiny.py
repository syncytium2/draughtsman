"""Whisper-tiny, written out at its published dimensions.

WHY THIS ONE. Deepgram publishes nothing about Nova's architecture beyond
marketing prose, so the ASR net that can actually be drawn is OpenAI's Whisper
(Radford et al., 2022, *Robust Speech Recognition via Large-Scale Weak
Supervision*). It is the encoder--decoder family the other nine models in this
gallery do not cover, and it is the one architecture that draughtsman could not
trace at all until `trace` learned to take more than one input: `forward` needs
the mel spectrogram AND the token ids.

WHAT IS FAITHFUL AND WHAT IS NOT. The module structure, the layer counts, the
widths, the head counts, the two conv frontend layers with their stride, the
pre-norm residual pairs, the cross-attention in every decoder block, the
sinusoidal audio positions as a buffer against learned text positions as a
parameter, and the weight tying between the token embedding and the output
projection are all as published for `tiny`. The WEIGHTS ARE RANDOM -- this draws
the architecture, not the trained model -- and there is no tokenizer, no
multilingual head, no timestamp logic, and no KV cache, because none of those are
architecture a reader needs from the figure.

Attention is written out with explicit q/k/v projections rather than
`nn.MultiheadAttention`, which is what Whisper itself does. That choice is load
bearing for this gallery: `nn.MultiheadAttention` FUSES into a single traced node
and hides its heads, while this spells them out, so the two transformer plates
bracket the range of what a tracer hands you for the same idea.
"""

from __future__ import annotations

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

# Whisper `tiny`, from the released model card.
N_MELS = 80
N_AUDIO_CTX = 1500
N_AUDIO_STATE = 384
N_AUDIO_HEAD = 6
N_AUDIO_LAYER = 4
N_TEXT_CTX = 448
N_TEXT_STATE = 384
N_TEXT_HEAD = 6
N_TEXT_LAYER = 4
N_VOCAB = 51865


def sinusoids(length: int, channels: int, max_timescale: int = 10000):
    """Whisper's audio positional encoding. A buffer, never trained."""
    log_timescale_increment = np.log(max_timescale) / (channels // 2 - 1)
    inv_timescales = torch.exp(
        -log_timescale_increment * torch.arange(channels // 2))
    scaled = torch.arange(length)[:, None] * inv_timescales[None, :]
    return torch.cat([torch.sin(scaled), torch.cos(scaled)], dim=1)


class MultiHeadAttention(nn.Module):
    """Written out, as Whisper writes it: no bias on the key projection."""

    def __init__(self, n_state: int, n_head: int):
        super().__init__()
        self.n_head = n_head
        self.query = nn.Linear(n_state, n_state)
        self.key = nn.Linear(n_state, n_state, bias=False)
        self.value = nn.Linear(n_state, n_state)
        self.out = nn.Linear(n_state, n_state)

    def forward(self, x, xa=None, mask=None):
        q = self.query(x)
        source = x if xa is None else xa
        k = self.key(source)
        v = self.value(source)

        b, t, d = q.shape
        h = self.n_head
        q = q.view(b, t, h, d // h).permute(0, 2, 1, 3)
        k = k.view(b, k.shape[1], h, d // h).permute(0, 2, 1, 3)
        v = v.view(b, v.shape[1], h, d // h).permute(0, 2, 1, 3)

        w = F.scaled_dot_product_attention(q, k, v, attn_mask=mask)
        w = w.permute(0, 2, 1, 3).reshape(b, t, d)
        return self.out(w)


class ResidualAttentionBlock(nn.Module):
    def __init__(self, n_state: int, n_head: int, cross_attention: bool = False):
        super().__init__()
        self.attn = MultiHeadAttention(n_state, n_head)
        self.attn_ln = nn.LayerNorm(n_state)
        self.cross_attn = (MultiHeadAttention(n_state, n_head)
                           if cross_attention else None)
        self.cross_attn_ln = nn.LayerNorm(n_state) if cross_attention else None
        self.mlp = nn.Sequential(
            nn.Linear(n_state, n_state * 4), nn.GELU(),
            nn.Linear(n_state * 4, n_state))
        self.mlp_ln = nn.LayerNorm(n_state)

    def forward(self, x, xa=None, mask=None):
        x = x + self.attn(self.attn_ln(x), mask=mask)
        if self.cross_attn is not None:
            x = x + self.cross_attn(self.cross_attn_ln(x), xa=xa)
        return x + self.mlp(self.mlp_ln(x))


class AudioEncoder(nn.Module):
    def __init__(self):
        super().__init__()
        self.conv1 = nn.Conv1d(N_MELS, N_AUDIO_STATE, 3, padding=1)
        self.conv2 = nn.Conv1d(N_AUDIO_STATE, N_AUDIO_STATE, 3, stride=2, padding=1)
        self.register_buffer("positional_embedding",
                             sinusoids(N_AUDIO_CTX, N_AUDIO_STATE))
        self.blocks = nn.ModuleList([
            ResidualAttentionBlock(N_AUDIO_STATE, N_AUDIO_HEAD)
            for _ in range(N_AUDIO_LAYER)])
        self.ln_post = nn.LayerNorm(N_AUDIO_STATE)

    def forward(self, mel):
        x = F.gelu(self.conv1(mel))
        x = F.gelu(self.conv2(x))
        x = x.permute(0, 2, 1) + self.positional_embedding
        for block in self.blocks:
            x = block(x)
        return self.ln_post(x)


class TextDecoder(nn.Module):
    def __init__(self):
        super().__init__()
        self.token_embedding = nn.Embedding(N_VOCAB, N_TEXT_STATE)
        self.positional_embedding = nn.Parameter(
            torch.empty(N_TEXT_CTX, N_TEXT_STATE))
        nn.init.normal_(self.positional_embedding, std=0.02)
        self.blocks = nn.ModuleList([
            ResidualAttentionBlock(N_TEXT_STATE, N_TEXT_HEAD, cross_attention=True)
            for _ in range(N_TEXT_LAYER)])
        self.ln = nn.LayerNorm(N_TEXT_STATE)
        mask = torch.full((N_TEXT_CTX, N_TEXT_CTX), float("-inf")).triu_(1)
        self.register_buffer("mask", mask, persistent=False)

    def forward(self, tokens, audio):
        n = tokens.shape[1]
        x = self.token_embedding(tokens) + self.positional_embedding[:n]
        mask = self.mask[:n, :n]
        for block in self.blocks:
            x = block(x, xa=audio, mask=mask)
        x = self.ln(x)
        # Tied weights: the output projection IS the token embedding.
        return x @ self.token_embedding.weight.transpose(0, 1)


class Whisper(nn.Module):
    def __init__(self):
        super().__init__()
        self.encoder = AudioEncoder()
        self.decoder = TextDecoder()

    def forward(self, mel, tokens):
        return self.decoder(tokens, self.encoder(mel))


def build_whisper_tiny():
    return Whisper()
