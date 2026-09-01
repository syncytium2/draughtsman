"""Eight models spanning the architecture families draughtsman had not met.

`tube` (examples/tube/) is one 1-D dilated conv net with a filter bank. Everything
in SPEC.md was measured on it. These exist to find where that generalises and
where it does not, so each one is chosen for a DIFFERENT way it could break the
tool, named in its docstring. They are written out in full rather than imported
from torchvision so that the gallery is reproducible from this repo alone, with no
download and no pinned third-party version.

Sizes are small on purpose: the figure is of the architecture, not of the
hyperparameters, and a 25M-parameter ResNet traces to the same shape of graph as a
250k one.
"""

from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F


# 1 -----------------------------------------------------------------------------
class MLP(nn.Module):
    """The floor. A linear stack of Linear/ReLU, which every tool in SPEC.md §2
    already draws correctly. If draughtsman cannot beat five existing tools here it
    has no business on anything harder."""

    def __init__(self, d_in=784, hidden=(256, 128), n_class=10):
        super().__init__()
        self.fc1 = nn.Linear(d_in, hidden[0])
        self.fc2 = nn.Linear(hidden[0], hidden[1])
        self.out = nn.Linear(hidden[1], n_class)
        self.drop = nn.Dropout(0.2)

    def forward(self, x):
        x = x.flatten(1)
        x = F.relu(self.fc1(x))
        x = self.drop(x)
        x = F.relu(self.fc2(x))
        return self.out(x)


def build_mlp():
    return MLP()


# 2 -----------------------------------------------------------------------------
class LeNet(nn.Module):
    """The canonical 2-D image CNN — the one architecture nn-SVG, visualtorch and
    pytorch-graph are all built around. Everything here is a registered module, so
    a module enumerator gets it right; this is the case where draughtsman's
    advantage should be zero and the figure should still be as good."""

    def __init__(self, n_class=10):
        super().__init__()
        self.conv1 = nn.Conv2d(1, 6, 5, padding=2)
        self.conv2 = nn.Conv2d(6, 16, 5)
        self.fc1 = nn.Linear(16 * 5 * 5, 120)
        self.fc2 = nn.Linear(120, 84)
        self.out = nn.Linear(84, n_class)

    def forward(self, x):
        x = F.max_pool2d(F.relu(self.conv1(x)), 2)
        x = F.max_pool2d(F.relu(self.conv2(x)), 2)
        x = x.flatten(1)
        x = F.relu(self.fc1(x))
        x = F.relu(self.fc2(x))
        return self.out(x)


def build_lenet():
    return LeNet()


# 3 -----------------------------------------------------------------------------
class BasicBlock(nn.Module):
    def __init__(self, c_in, c_out, stride=1):
        super().__init__()
        self.conv1 = nn.Conv2d(c_in, c_out, 3, stride, 1, bias=False)
        self.bn1 = nn.BatchNorm2d(c_out)
        self.conv2 = nn.Conv2d(c_out, c_out, 3, 1, 1, bias=False)
        self.bn2 = nn.BatchNorm2d(c_out)
        self.down = None
        if stride != 1 or c_in != c_out:
            self.down = nn.Sequential(
                nn.Conv2d(c_in, c_out, 1, stride, bias=False),
                nn.BatchNorm2d(c_out))

    def forward(self, x):
        idt = x if self.down is None else self.down(x)
        y = F.relu(self.bn1(self.conv1(x)))
        y = self.bn2(self.conv2(y))
        return F.relu(y + idt)


class ResNet(nn.Module):
    """Residual blocks: the first model here whose architecture is a REAL fork and
    rejoin in the traced graph, repeated eight times. Two questions it asks — does
    the layout engine draw a short skip without bowing it halfway across the page,
    and does a figure with eight identical blocks want a `repeat` primitive that
    the spec format does not have?"""

    def __init__(self, n_class=10, widths=(16, 32, 64)):
        super().__init__()
        self.stem = nn.Conv2d(3, widths[0], 3, 1, 1, bias=False)
        self.bn = nn.BatchNorm2d(widths[0])
        blocks, c_prev = [], widths[0]
        for i, c in enumerate(widths):
            blocks.append(BasicBlock(c_prev, c, stride=1 if i == 0 else 2))
            blocks.append(BasicBlock(c, c))
            c_prev = c
        self.blocks = nn.Sequential(*blocks)
        self.head = nn.Linear(widths[-1], n_class)

    def forward(self, x):
        x = F.relu(self.bn(self.stem(x)))
        x = self.blocks(x)
        x = F.adaptive_avg_pool2d(x, 1).flatten(1)
        return self.head(x)


def build_resnet():
    return ResNet()


# 4 -----------------------------------------------------------------------------
def _double_conv(c_in, c_out):
    return nn.Sequential(
        nn.Conv2d(c_in, c_out, 3, padding=1), nn.ReLU(inplace=True),
        nn.Conv2d(c_out, c_out, 3, padding=1), nn.ReLU(inplace=True))


class UNet(nn.Module):
    """The layout stress case. Three skip connections that each span the whole
    depth of the network, so the figure has long edges crossing many ranks at once
    — exactly what DECISIONS.md §8.2's dummy-node handling was tuned on a single
    bypass. A U is also the one architecture readers expect drawn in a specific
    SHAPE, which a left-to-right ranked layout cannot produce."""

    def __init__(self, c_in=3, base=16, n_class=2):
        super().__init__()
        self.enc1 = _double_conv(c_in, base)
        self.enc2 = _double_conv(base, base * 2)
        self.enc3 = _double_conv(base * 2, base * 4)
        self.bottleneck = _double_conv(base * 4, base * 8)
        self.up3 = nn.ConvTranspose2d(base * 8, base * 4, 2, stride=2)
        self.dec3 = _double_conv(base * 8, base * 4)
        self.up2 = nn.ConvTranspose2d(base * 4, base * 2, 2, stride=2)
        self.dec2 = _double_conv(base * 4, base * 2)
        self.up1 = nn.ConvTranspose2d(base * 2, base, 2, stride=2)
        self.dec1 = _double_conv(base * 2, base)
        self.out = nn.Conv2d(base, n_class, 1)

    def forward(self, x):
        e1 = self.enc1(x)
        e2 = self.enc2(F.max_pool2d(e1, 2))
        e3 = self.enc3(F.max_pool2d(e2, 2))
        b = self.bottleneck(F.max_pool2d(e3, 2))
        d3 = self.dec3(torch.cat([self.up3(b), e3], dim=1))
        d2 = self.dec2(torch.cat([self.up2(d3), e2], dim=1))
        d1 = self.dec1(torch.cat([self.up1(d2), e1], dim=1))
        return self.out(d1)


def build_unet():
    return UNet()


# 5 -----------------------------------------------------------------------------
class EncoderBlock(nn.Module):
    def __init__(self, d_model, n_head, d_ff):
        super().__init__()
        self.attn = nn.MultiheadAttention(d_model, n_head, batch_first=True)
        self.n1 = nn.LayerNorm(d_model)
        self.n2 = nn.LayerNorm(d_model)
        self.ff = nn.Sequential(nn.Linear(d_model, d_ff), nn.GELU(),
                                nn.Linear(d_ff, d_model))

    def forward(self, x):
        h = self.n1(x)
        a, _ = self.attn(h, h, h, need_weights=False)
        x = x + a
        return x + self.ff(self.n2(x))


class TinyTransformer(nn.Module):
    """The case the market actually wants drawn, and the hardest one here. Four
    identical blocks, each an attention sublayer and an MLP sublayer with residual
    streams around both. Two distinct problems: node count (attention traces to
    dozens of reshapes and transposes that no reader wants) and repetition (a
    figure that draws four identical blocks in a row wastes three quarters of its
    width saying nothing)."""

    def __init__(self, vocab=1000, d_model=64, n_head=4, d_ff=128, n_layer=4,
                 max_len=32, n_class=4):
        super().__init__()
        self.embed = nn.Embedding(vocab, d_model)
        self.pos = nn.Parameter(torch.zeros(1, max_len, d_model))
        self.blocks = nn.ModuleList(
            [EncoderBlock(d_model, n_head, d_ff) for _ in range(n_layer)])
        self.norm = nn.LayerNorm(d_model)
        self.head = nn.Linear(d_model, n_class)

    def forward(self, tok):
        x = self.embed(tok) + self.pos[:, :tok.shape[1]]
        for blk in self.blocks:
            x = blk(x)
        return self.head(self.norm(x).mean(dim=1))


def build_transformer():
    return TinyTransformer()


# 6 -----------------------------------------------------------------------------
class BiLSTMTagger(nn.Module):
    """The OPPOSITE failure to tube's. tube traced to 200 nodes and needed
    collapsing; a two-layer bidirectional LSTM is a single fused `aten::lstm` node
    carrying most of the parameters. There is nothing for an agent to group, and
    the interesting structure — layers, directions, gates — is inside one opaque
    op. If the tool has a floor below which it adds nothing, this finds it."""

    def __init__(self, vocab=1000, d_emb=32, d_hid=48, n_layer=2, n_tag=9):
        super().__init__()
        self.embed = nn.Embedding(vocab, d_emb)
        self.lstm = nn.LSTM(d_emb, d_hid, n_layer, batch_first=True,
                            bidirectional=True, dropout=0.1)
        self.drop = nn.Dropout(0.3)
        self.out = nn.Linear(d_hid * 2, n_tag)

    def forward(self, tok):
        x = self.embed(tok)
        h, _ = self.lstm(x)
        return self.out(self.drop(h))


def build_lstm():
    return BiLSTMTagger()


# 7 -----------------------------------------------------------------------------
class ConvVAE(nn.Module):
    """A fork that is not a branch. The encoder splits into mu and logvar through
    two sibling Linear layers, then the reparameterisation recombines them with a
    sample of noise — so the graph forks, rejoins, and takes in a tensor that came
    from nowhere. `randn_like` is a source node with no ancestor, which is a shape
    of node tube's graph never contained."""

    def __init__(self, c_in=1, base=16, z=8):
        super().__init__()
        self.enc = nn.Sequential(
            nn.Conv2d(c_in, base, 3, 2, 1), nn.ReLU(inplace=True),
            nn.Conv2d(base, base * 2, 3, 2, 1), nn.ReLU(inplace=True))
        self.mu = nn.Linear(base * 2 * 7 * 7, z)
        self.logvar = nn.Linear(base * 2 * 7 * 7, z)
        self.lift = nn.Linear(z, base * 2 * 7 * 7)
        self.dec = nn.Sequential(
            nn.ConvTranspose2d(base * 2, base, 4, 2, 1), nn.ReLU(inplace=True),
            nn.ConvTranspose2d(base, c_in, 4, 2, 1))
        self.base = base

    def forward(self, x):
        h = self.enc(x).flatten(1)
        mu, logvar = self.mu(h), self.logvar(h)
        z = mu + torch.exp(0.5 * logvar) * torch.randn_like(mu)
        h = self.lift(z).view(-1, self.base * 2, 7, 7)
        return torch.sigmoid(self.dec(h))


def build_vae():
    return ConvVAE()


# 8 -----------------------------------------------------------------------------
class DualBranchNet(nn.Module):
    """tube's own shape, generalised: two genuinely parallel branches over the SAME
    input that rejoin at a concat, where neither branch is a registered-module
    sequence a enumerator would find in order. It is here as the control — the one
    architecture family draughtsman was designed against — to check that the design
    holds when the branches are deep rather than a bank of kernels."""

    def __init__(self, c_in=8, width=32, n_class=5):
        super().__init__()
        self.slow = nn.Sequential(
            nn.Conv1d(c_in, width, 9, padding=4), nn.ReLU(inplace=True),
            nn.Conv1d(width, width, 9, padding=8, dilation=2),
            nn.ReLU(inplace=True))
        self.fast = nn.Sequential(
            nn.Conv1d(c_in, width, 3, padding=1), nn.ReLU(inplace=True),
            nn.Conv1d(width, width, 3, padding=1), nn.ReLU(inplace=True))
        self.gate = nn.Conv1d(width * 2, width * 2, 1)
        self.head = nn.Sequential(
            nn.Conv1d(width * 2, width, 3, padding=1), nn.ReLU(inplace=True),
            nn.Conv1d(width, n_class, 1))

    def forward(self, x):
        s = self.slow(x)
        f = self.fast(x)
        both = torch.cat([s, f], dim=1)
        both = both * torch.sigmoid(self.gate(both))
        return self.head(both).mean(dim=2)


def build_dual():
    return DualBranchNet()
