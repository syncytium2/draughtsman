"""CASCADE — spike inference from calcium imaging, at its published dimensions.

WHY THIS ONE IS DIFFERENT FROM THE OTHER TEN. Every other model in this gallery
was written to break draughtsman in a particular way. This one is a tool in use:
CASCADE turns a calcium ΔF/F trace into a spike rate, and the figure of it is
wanted for its own sake rather than as a test case.

SOURCE. Rupprecht et al., *A database and deep learning toolbox for
noise-optimized, generalized spike inference from calcium imaging*, Nature
Neuroscience 25:1471-1481 (2022). The original is TensorFlow
(HelmchenLabSoftware/Cascade); this transcribes the PyTorch re-implementation,
PTRRupprecht/CascadeTorch (2026), whose `define_model` in `cascade2p/utils.py`
is the authority for the layers below, with the shipped `cascade2p/config.py`
defaults for the sizes.

ONE POINT ABOUT THE PRETRAINED MODELS, BECAUSE IT DECIDES WHAT THE FIGURE MEANS.
CASCADE ships dozens of pretrained models -- `Global_EXC_10Hz_50ms` is the one
interface2's `Cascade_showPredictions2.m` loads. They do NOT differ in
architecture. Every one is this same network; what differs is the ground-truth
set it was trained on, the sampling rate it was resampled to, and the smoothing
kernel applied to the target. So this figure is the figure for all of them, and a
caption naming one model would be wrong about the other dozens.

The weights here are random. This draws the architecture, not a trained model,
and the parameter counts are exact because they follow from the shapes.
"""

from __future__ import annotations

import torch
import torch.nn as nn

# cascade2p/config.py, shipped defaults. The pretrained models keep these.
WINDOWSIZE = 64          # timepoints of ΔF/F handed to the network
BEFORE_FRAC = 0.5        # the predicted timepoint sits at the window's centre
FILTER_SIZES = (31, 19, 5)
FILTER_NUMBERS = (30, 40, 50)
DENSE_EXPANSION = 10


def _flattened_size(windowsize: int, filter_sizes: tuple[int, ...]) -> int:
    """CascadeModel._calculate_flattened_size, transcribed.

    NOT A LAYER, AND WORTH KNOWING ABOUT BEFORE READING THE FIGURE. The
    convolutions are unpadded and the pools halve, so the window shrinks
    64 -> 34 -> 16 -> 8 -> 4 -> 2 and the final dense layer's input width is
    computed in Python from the window and the filter sizes. It is arithmetic on
    hyperparameters, not on a fitted quantity, so the number the trace records is
    the number every instance of this model has.
    """
    size = windowsize
    size = size - (filter_sizes[0] - 1)
    size = size - (filter_sizes[1] - 1)
    size = size // 2
    size = size - (filter_sizes[2] - 1)
    return size // 2


class CascadeModel(nn.Module):
    """Three convolutions, two poolings, two dense layers.

    Transcribed from CascadeTorch `define_model`, including the two permutes:
    the network is handed (batch, time, channel) and works in (batch, channel,
    time), then goes back so the first dense layer acts per timepoint.
    """

    def __init__(self, filter_sizes=FILTER_SIZES, filter_numbers=FILTER_NUMBERS,
                 dense_expansion=DENSE_EXPANSION, windowsize=WINDOWSIZE):
        super().__init__()
        self.conv1 = nn.Conv1d(1, filter_numbers[0], filter_sizes[0], stride=1)
        self.relu1 = nn.ReLU()
        self.conv2 = nn.Conv1d(filter_numbers[0], filter_numbers[1], filter_sizes[1])
        self.relu2 = nn.ReLU()
        self.pool1 = nn.MaxPool1d(2)
        self.conv3 = nn.Conv1d(filter_numbers[1], filter_numbers[2], filter_sizes[2])
        self.relu3 = nn.ReLU()
        self.pool2 = nn.MaxPool1d(2)
        # Applied per timepoint, which is why the tensor is permuted back first.
        self.dense1 = nn.Linear(filter_numbers[2], dense_expansion)
        self.relu4 = nn.ReLU()
        self.dense2 = nn.Linear(
            _flattened_size(windowsize, filter_sizes) * dense_expansion, 1)

    def forward(self, x):
        x = x.permute(0, 2, 1)          # (B, T, C) -> (B, C, T)
        x = self.relu1(self.conv1(x))
        x = self.relu2(self.conv2(x))
        x = self.pool1(x)
        x = self.relu3(self.conv3(x))
        x = self.pool2(x)
        x = x.permute(0, 2, 1)          # back to (B, T, C) for the per-step dense
        x = self.relu4(self.dense1(x))
        x = x.view(x.size(0), -1)
        return self.dense2(x)


def build_cascade():
    m = CascadeModel()
    m.eval()
    return m
