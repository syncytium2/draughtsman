"""A small model with the three properties that broke every tool in SPEC.md §2.

Deliberately NOT a copy of bugarach's `tube`. A vendored copy would drift from
its original in silence, and a regression suite that quietly stops testing the
thing it names is the same defect this project exists to catch. This is a fresh
model that has the same awkward shape:

  * a data-dependent integer in ``forward`` — defeats ``torch.fx.symbolic_trace``
    and ``torch.export.export``, so it pins SPEC.md §3's finding;
  * a filter bank that is one convolution with N output channels, so its
    parallelism is a channel dimension and not a fork — the case that makes
    ``lanes`` necessary;
  * a bypass that skips the bank and rejoins at a concat, so the graph forks and
    rejoins for real.

`examples/tube/` holds the actual bugarach artifacts. This holds the test.
"""

import math

import torch
from torch import nn


class Branchy(nn.Module):
    def __init__(self, n_scales: int = 3, width: int = 4, depth: int = 3):
        super().__init__()
        self.k = 4
        self.log_w = nn.Parameter(
            torch.tensor([math.log(1.0 * 2 ** i) for i in range(n_scales)]))
        self.gain = nn.Parameter(torch.ones(n_scales))
        layers: list[nn.Module] = []
        c_in = n_scales + 1
        for d in range(depth):
            layers += [nn.Conv1d(c_in, width, 3, padding=2 ** d, dilation=2 ** d),
                       nn.GELU()]
            c_in = width
        layers.append(nn.Conv1d(width, 1, 1))
        self.head = nn.Sequential(*layers)

    def _kernels(self):
        t = torch.arange(-self.k, self.k + 1, dtype=torch.float32).view(1, -1)
        c = torch.exp(self.log_w).clamp(0.5, 4.0).view(-1, 1)
        g = torch.exp(-0.5 * (t / c) ** 2)
        g = g / g.sum(dim=1, keepdim=True)
        return (g * self.gain.view(-1, 1)).unsqueeze(1)

    def forward(self, x):                                   # (B, cells, T)
        # The data-dependent integer. fx and export both die on this line.
        kmin = int(torch.exp(self.log_w.detach()).min().clamp(1, self.k))
        pooled = torch.nn.functional.max_pool1d(
            x, kernel_size=2 * kmin + 1, stride=1, padding=kmin)
        mean = pooled.sum(dim=1, keepdim=True) / x.shape[1]
        resp = torch.nn.functional.conv1d(mean, self._kernels(), padding=self.k)
        return self.head(torch.cat([mean, resp], dim=1)).squeeze(1)


def build_branchy():
    m = Branchy()
    m.eval()
    return m


class TiedTwoInput(nn.Module):
    """Two inputs and a tied weight — the two things Whisper needs and `tube`
    never exercised.

    The embedding table is BOTH the input lookup and the output projection, so
    `torch.jit.trace` emits two prim::GetAttr nodes for one parameter. Charging
    both put more parameters on the model than it has, which is precisely the
    confident-and-wrong number SPEC.md §4 exists to prevent.
    """

    def __init__(self, vocab=32, d=8, c_in=3):
        super().__init__()
        self.embed = nn.Embedding(vocab, d)
        self.conv = nn.Conv1d(c_in, d, 3, padding=1)

    def forward(self, signal, tokens):
        ctx = self.conv(signal).mean(dim=2, keepdim=True)
        x = self.embed(tokens) + ctx.transpose(1, 2)
        return x @ self.embed.weight.transpose(0, 1)


def build_tied_two_input():
    m = TiedTwoInput()
    m.eval()
    return m
