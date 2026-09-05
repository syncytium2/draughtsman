"""The 1986 neural cocktail-party processor, at the paper's own parameters.

    Ch. von der Malsburg and W. Schneider, "A Neural Cocktail-Party Processor",
    Biological Cybernetics 54:29-40 (1986).  DOI 10.1007/BF00337113.
    PDF in `lit/`; provenance and the search for it in `lit/malsburg-1986.md`.

WHAT IT IS. Twenty excitatory cells and one inhibitory cell. Each E-cell stands
for one spectral component of the input. Cells driven by the same sound
synchronise their activity bursts; cells driven by different sounds are pushed
into antiphase. **The segregated stream is the set of cells bursting together** —
the answer is a temporal pattern, not a value on an output line.

The mechanism is the point and it is unusual: the coupling matrix `s` between
E-cells is not a trained weight. It changes DURING a single stimulus
presentation, strengthening between cells that burst together and weakening
between cells that do not. That is von der Malsburg's synaptic modulation, and it
means the object carrying the model's meaning is state rather than a parameter.

**Nothing here is trained. Every constant below is stated in the paper**, and each
carries the equation number it comes from so a reader can check it against the
PDF rather than trusting this file.

WHY IT IS WRITTEN IN TORCH AND NOT NUMPY. `tests/test_gallery_imports.py` allows
this directory `torch`, `draughtsman` and the standard library, and nothing else.
That is a real constraint and it is also the right answer: the whole point of
having this model here is that draughtsman may one day be asked to draw it, and
that needs a traceable module.

FAITHFUL, AND WHERE IT IS NOT. Section 3 of the paper is complete, so equations 1
through 8 are transcribed rather than reconstructed. Two places need judgement and
both are marked `INTERPOLATED` in the code below: the exact stretching of the
coactivity cosine when a burst is not half the period, and a sign ambiguity the
paper itself contains. See `lit/malsburg-1986-implementation.md`.

BUILT TO BE CHANGED. The dynamics, the burst detector and the plasticity rule are
three separate methods on purpose. Replacing any one of them with a modern
element -- a different oscillator, a learned coupling, a real cochlear front end
-- should not require touching the other two.
"""

from __future__ import annotations

import math

import torch
import torch.nn as nn

# ----------------------------------------------------------------- constants
# Every value below is from the paper, with its equation number. They are module
# constants rather than defaults buried in a signature so that a reader can diff
# this block against Section 3 and be done.

ALPHA = 0.89        # eq 1: an E-cell's self-excitation from one step to the next
S_HE = 0.22         # eq 1: inhibition from the H-cell onto every E-cell
BETA = 0.63         # eq 2: the H-cell's self-excitation
S_EH = 0.036        # eq 2: excitation from each E-cell onto the H-cell
AFFERENT = 0.1      # eq 3: the input an E-cell gets while its component sounds
DELTA = 0.35        # eq 5: the gliding average's rate
G_UPPER = 0.4       # eq 6: gliding average at which a burst breaks off
G_LOWER = 0.01      # eq 6: gliding average at which the cell may burst again
Q0 = 0.01           # eq 8: the size of one synaptic modulation step
S0 = 0.012          # eq 8: resting coupling strength, and the centre of q(s)
S_D = 0.8           # eq 8: half-width of the control function, in units of S0
NOISE = 0.01        # Sect 3: noise is drawn flat on (0, NOISE)

N_CELLS = 20        # Sect 3: two stimuli of ten spectral components each
DEFAULT_STEPS = 1000  # Sect 4: "1000 steps long (which may correspond to 1 s)"


def clip(x: torch.Tensor) -> torch.Tensor:
    """Eq 4. The output nonlinearity: simple clipping to [0, 1].

    The paper notes the upper threshold is never reached in the runs it shows, so
    this is in practice a rectifier. It is written as stated rather than as
    observed, because "never reached in these runs" is not "cannot be reached".
    """
    return x.clamp(0.0, 1.0)


class CocktailParty(nn.Module):
    """The model of Section 3, as a module whose forward advances one step.

    ONE STEP IS THE TRACEABLE UNIT and that is deliberate. The interesting
    behaviour is a transient over hundreds of steps, so there is no single
    forward pass that contains the phenomenon -- which is exactly what makes this
    model hard to draw and worth having.
    """

    def __init__(self, n_cells: int = N_CELLS, *, dtype=torch.float32):
        super().__init__()
        self.n = n_cells
        self.dtype = dtype
        # NOT A PARAMETER, AND THIS IS THE WHOLE THESIS. `s` is coupling that
        # changes during one presentation. It is registered as a buffer so it
        # travels with the module and is saved with it, and so that nothing here
        # ever hands it to an optimiser.
        self.register_buffer("s", torch.full((n_cells, n_cells), S0, dtype=dtype))
        # No self-coupling: eq 1 sums over j != i.
        self.s.fill_diagonal_(0.0)

    # ------------------------------------------------------------- dynamics
    def step(self, e, h, g, refractory, afferent, noise):
        """Eqs 1, 2, 5 and 6: one time step of the cell dynamics.

        Returns the new (e, h, g, refractory). Pure and side-effect free so it
        can be traced, tested and replaced on its own.
        """
        # eq 1. The coupled sum uses s with a zero diagonal, so `s @ e` is
        # exactly the sum over j != i.
        drive = afferent + ALPHA * e + self.s @ e - S_HE * h + noise
        e_next = refractory * clip(drive)

        # eq 2. The H-cell sees the total E activity and returns inhibition; it
        # is what caps activity and forces blocks apart.
        h_next = clip(BETA * h + S_EH * e.sum())

        # eq 5. A gliding average of each cell's own activity.
        g_next = (1.0 - DELTA) * g + DELTA * e_next

        # eq 6. The refractory latch: switch off at G_UPPER, and stay off until
        # the average has decayed past G_LOWER. Written as a latch rather than a
        # threshold because that is what the equation says -- the second clause
        # depends on the PREVIOUS value of N.
        was_off = refractory < 0.5
        off = (g_next > G_UPPER) | (was_off & (g_next > G_LOWER))
        refractory_next = (~off).to(self.dtype)
        return e_next, h_next, g_next, refractory_next

    # ----------------------------------------------------------- plasticity
    @staticmethod
    def coactivity(dt, period, burst):
        """The Co(.) of eq 7, as described by Fig. 6 and the text at p. 33.

        +1 when two bursts coincide, 0 when they overlap for half their duration,
        -1 in antiphase. The paper gives a cosine of period T for the special case
        of a burst half the period, and says that otherwise the positive and
        negative half-waves are "linearly stretched and compressed" so the
        crossing-over still lands at half-overlap.

        INTERPOLATED. The paper does not write the general formula. This warps the
        cosine's PHASE piecewise-linearly so its zero crossing sits at burst/2:

            |dt| <= burst/2   ->  phase from 0 to pi/2
            otherwise         ->  phase from pi/2 to pi at |dt| = period/2

        It is checked in `selftest()` that this reduces exactly to
        cos(2*pi*dt/period) when burst == period/2, which is the case the paper
        states -- so the interpolation is pinned at the one point where the source
        is explicit.
        """
        half = period / 2.0
        # Earlier bursts a full period back count as advanced rather than
        # delayed: wrap dt into (-T/2, +T/2].
        dt = dt - period * torch.round(dt / period)
        a = dt.abs()
        edge = burst / 2.0
        inner = (math.pi / 2.0) * (a / edge.clamp(min=1e-9))
        outer = (math.pi / 2.0) * (1.0 + (a - edge) / (half - edge).clamp(min=1e-9))
        phase = torch.where(a <= edge, inner, outer)
        return torch.cos(phase.clamp(max=math.pi))

    @staticmethod
    def control(s):
        """Eq 8. q(s), the convex control on how far one step may move a synapse.

        Largest at the resting value and falling to zero at the edges, which is
        what keeps strengths inside 80% of resting and makes short-term memory
        insensitive to a stray episode of false synchrony.
        """
        return Q0 * (1.0 - ((s - S0) / (S0 * S_D)) ** 2)

    def modulate(self, post, last_break, period, burst):
        """Eq 7 for one postsynaptic cell that has just finished a burst.

        Only cells that just entered the inter-burst period are updated, which is
        the paper's own economy at the end of Section 3.
        """
        dt = last_break[post] - last_break               # eq 7's t_i - t_j
        seen = torch.isfinite(dt)
        co = self.coactivity(torch.nan_to_num(dt), period, burst)
        delta = self.control(self.s[post]) * co
        delta = torch.where(seen, delta, torch.zeros_like(delta))
        delta[post] = 0.0
        lo, hi = S0 * (1.0 - S_D), S0 * (1.0 + S_D)
        self.s[post] = (self.s[post] + delta).clamp(lo, hi)

    def forward(self, e, h, g, refractory, afferent, noise):
        """One step. Named `forward` so the module is traceable as it stands."""
        return self.step(e, h, g, refractory, afferent, noise)


# ------------------------------------------------------------------ stimulus
def two_streams(n_cells: int = N_CELLS, onset: int = 1):
    """Section 4's stimulus: two spectra of ten components each.

    Cells 0-9 carry the first sound, 10-19 the second, and the second starts
    `onset` steps later. Fig. 7 uses a one-step delay, and the paper's claim is
    that this is enough: a delay that small is amplified by the dynamics until
    the two groups are in complete antiphase.
    """
    half = n_cells // 2
    def afferent_at(t: int) -> torch.Tensor:
        a = torch.zeros(n_cells)
        if t >= 0:
            a[:half] = AFFERENT
        if t >= onset:
            a[half:] = AFFERENT
        return a
    return afferent_at, half


def simulate(steps: int = DEFAULT_STEPS, *, onset: int = 1, seed: int = 0,
             n_cells: int = N_CELLS, plastic: bool = True):
    """Run the model and return its traces and its final coupling matrix.

    `plastic=False` freezes `s`, which is how you see what the synaptic
    modulation is actually contributing: the dynamics alone will separate the
    groups, and the plasticity is what makes the separation stick.
    """
    torch.manual_seed(seed)
    net = CocktailParty(n_cells)
    afferent_at, half = two_streams(n_cells, onset)

    e = torch.zeros(n_cells)
    h = torch.zeros(())
    g = torch.zeros(n_cells)
    refractory = torch.ones(n_cells)

    # Burst bookkeeping. `last_break` is a real-valued time, not an integer step:
    # see `INTERPOLATED` below.
    last_break = torch.full((n_cells,), float("nan"))
    burst_start = torch.zeros(n_cells)
    period, burst_len = torch.tensor(6.5), torch.tensor(3.25)  # Sect 4: T ~ 5.8-7.0

    e_trace, h_trace = [], []
    for t in range(steps):
        noise = torch.rand(n_cells) * NOISE          # Sect 3: flat on (0, NOISE)
        prev_refractory, prev_g = refractory, g
        e, h, g, refractory = net.step(e, h, g, refractory,
                                       afferent_at(t), noise)
        e_trace.append(e.clone())
        h_trace.append(h.clone())

        broke = (prev_refractory > 0.5) & (refractory < 0.5)
        for i in broke.nonzero(as_tuple=True)[0].tolist():
            # INTERPOLATED, and Fig. 4 says why it matters: with break-off pinned
            # to whole steps, discrete time synchronises cells that are not
            # actually in phase. Linear interpolation of where the gliding
            # average crossed G_UPPER recovers a sub-step time.
            denom = float(g[i] - prev_g[i])
            frac = (G_UPPER - float(prev_g[i])) / denom if abs(denom) > 1e-12 else 0.0
            t_c = t - 1 + min(max(frac, 0.0), 1.0)

            if math.isfinite(float(last_break[i])):
                gap = t_c - float(last_break[i])
                if 0.0 < gap < 4 * float(period):     # ignore restarts after silence
                    period = 0.9 * period + 0.1 * gap
                    burst_len = 0.9 * burst_len + 0.1 * min(
                        gap, max(t_c - float(burst_start[i]), 1e-3))
            if plastic:
                net.modulate(i, last_break, period, burst_len)
            last_break[i] = t_c

        restarted = (prev_refractory < 0.5) & (refractory > 0.5)
        burst_start = torch.where(restarted, torch.full_like(burst_start, float(t)),
                                  burst_start)

    return {
        "e": torch.stack(e_trace),        # steps x cells
        "h": torch.stack(h_trace),        # steps
        "s": net.s.clone(),               # final coupling
        "half": half,
        "period": float(period),
        "burst": float(burst_len),
    }


# --------------------------------------------------------------- diagnostics
def coupling_blocks(s: torch.Tensor, half: int):
    """Fig. 9's claim as two numbers: mean coupling within a group, and between.

    The paper shows a matrix that has gone block-diagonal -- strong inside each
    stimulus, weak across. This is that picture reduced to something a test can
    assert on.
    """
    n = s.shape[0]
    within = torch.zeros((n, n), dtype=torch.bool)
    within[:half, :half] = True
    within[half:, half:] = True
    within.fill_diagonal_(False)
    between = ~within
    between.fill_diagonal_(False)
    return float(s[within].mean()), float(s[between].mean())


def group_antiphase(e: torch.Tensor, half: int, *, last: int = 300):
    """How far apart the two groups' bursts are, as a correlation in [-1, 1].

    -1 is complete antiphase, which is what successful segregation looks like.
    Measured over the tail of the run, because the paper's claim is about the
    state the system settles into, not the transient it starts in.
    """
    tail = e[-last:]
    a = tail[:, :half].mean(dim=1)
    b = tail[:, half:].mean(dim=1)
    a = a - a.mean()
    b = b - b.mean()
    denom = (a.norm() * b.norm()).clamp(min=1e-9)
    return float((a @ b) / denom)


def h_cell_rate(h: torch.Tensor, *, last: int = 300):
    """Bursts per step in the H-cell over the tail of the run.

    The paper calls frequency doubling and amplitude reduction in the H-cell "a
    good indicator of desynchronization": when the two groups alternate, the
    inhibitory pool is driven twice per cycle instead of once.
    """
    tail = h[-last:]
    mid = (tail.max() + tail.min()) / 2.0
    above = tail > mid
    crossings = int(((~above[:-1]) & above[1:]).sum())
    return crossings / max(len(tail), 1)


# ------------------------------------------------------------------ selftest
def selftest() -> int:
    """Check the transcription against the parts of the paper that are explicit.

    The behavioural claim -- that the two groups end up in antiphase with a
    block-diagonal coupling matrix -- is checked by `__main__` and by
    `tests/test_cocktail.py`. What is checked HERE is the arithmetic, because a
    model that segregates for the wrong reason still segregates.
    """
    t = torch.tensor

    # eq 4
    assert float(clip(t(-1.0))) == 0.0 and float(clip(t(2.0))) == 1.0
    assert abs(float(clip(t(0.3))) - 0.3) < 1e-9

    # THE ONE PLACE THE PAPER IS EXPLICIT ABOUT Co(.), AND SO THE ONE PLACE THE
    # INTERPOLATION CAN BE PINNED: for a burst half the period it must be exactly
    # a cosine of period T.
    period, burst = t(6.0), t(3.0)
    for dt in (-3.0, -2.0, -1.0, 0.0, 0.5, 1.0, 2.0, 3.0):
        got = float(CocktailParty.coactivity(t(dt), period, burst))
        want = math.cos(2 * math.pi * dt / 6.0)
        assert abs(got - want) < 1e-6, (
            f"Co({dt}) = {got}, and the paper says it is a cosine of period T "
            f"when the burst is half the period: {want}")

    # ... and the three points that must hold for any burst length
    for b in (1.0, 2.0, 3.0, 4.0, 5.0):
        bb = t(b)
        assert abs(float(CocktailParty.coactivity(t(0.0), period, bb)) - 1.0) < 1e-6
        half_overlap = float(CocktailParty.coactivity(t(b / 2), period, bb))
        assert abs(half_overlap) < 1e-6, (
            f"burst {b}: crossing-over must be at half overlap, got {half_overlap}")
        assert float(CocktailParty.coactivity(t(3.0), period, bb)) < -0.999

    # eq 8: largest at rest, zero at the edges, and never negative in between
    assert abs(float(CocktailParty.control(t(S0))) - Q0) < 1e-12
    assert abs(float(CocktailParty.control(t(S0 * (1 + S_D))))) < 1e-12
    assert abs(float(CocktailParty.control(t(S0 * (1 - S_D))))) < 1e-12

    # eq 6 is a LATCH, not a threshold. A cell above G_LOWER but below G_UPPER
    # stays off if it was off, and stays on if it was on. Getting this wrong
    # gives a model that bursts at the wrong rate and still looks plausible.
    net = CocktailParty(2)
    mid = (G_UPPER + G_LOWER) / 2
    on = torch.ones(2)
    _, _, _, after_on = net.step(torch.full((2,), mid / DELTA), t(0.0),
                                 torch.zeros(2), on, torch.zeros(2), torch.zeros(2))
    assert float(after_on[0]) == 1.0, "a cell below G_UPPER must not switch off"
    off = torch.zeros(2)
    _, _, _, after_off = net.step(torch.zeros(2), t(0.0), torch.full((2,), mid),
                                  off, torch.zeros(2), torch.zeros(2))
    assert float(after_off[0]) == 0.0, (
        "a cell that is already off must stay off until the average falls below "
        "G_LOWER -- eq 6's second clause depends on the previous value of N")

    # `s` must never be handed to an optimiser: it is state, not a weight.
    assert not any(p.requires_grad for p in net.parameters()), (
        "the coupling matrix is a buffer, not a parameter -- the whole thesis is "
        "that it changes during a presentation rather than being trained")
    assert len(list(net.parameters())) == 0, "this model has no trained parameters"

    print("selftest OK -- eq 4 clipping, Co reduces to the paper's cosine at "
          "T_a = T/2, half-overlap crossing for every burst length, eq 8 control, "
          "eq 6 latch in both directions, and no trainable parameters")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) > 1 and argv[1] == "--selftest":
        return selftest()

    steps = int(argv[1]) if len(argv) > 1 else DEFAULT_STEPS
    print(f"von der Malsburg & Schneider 1986, {N_CELLS} E-cells + 1 H-cell, "
          f"{steps} steps\n")
    for plastic in (False, True):
        r = simulate(steps, plastic=plastic)
        within, between = coupling_blocks(r["s"], r["half"])
        label = "with synaptic modulation" if plastic else "coupling frozen"
        print(f"  {label}")
        print(f"    group antiphase        {group_antiphase(r['e'], r['half']):+.3f}"
              "   (-1 is complete antiphase)")
        print(f"    coupling within group  {within:.5f}")
        print(f"    coupling between       {between:.5f}"
              f"   ratio {within / between if between else float('inf'):.2f}")
        print(f"    H-cell bursts/step     {h_cell_rate(r['h']):.3f}")
        print(f"    burst period T         {r['period']:.2f} steps"
              f"   (paper: 5.8 to 7.0)\n")
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(main(sys.argv))
