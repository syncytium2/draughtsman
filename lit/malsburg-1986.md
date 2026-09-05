# von der Malsburg & Schneider 1986 — the search, and what it found

**A neural cocktail-party processor.** *Biological Cybernetics* 54(1):29–40, 1986.
DOI [`10.1007/BF00337113`](https://doi.org/10.1007/BF00337113) · PMID `3719028`.
Both confirmed against PubMed and Semantic Scholar; the DOI was a guess before
that and is now checked.

## Status: a human has to get this one

**Closed access, with zero open full-text locations.** Checked independently
against OpenAlex, Unpaywall via Semantic Scholar, Europe PMC, OpenAIRE, and the
Max Planck Society's own repository. All five agree.

The dead ends are worth writing down, because a negative result nobody records
gets re-derived by the next session:

| checked | result |
|---|---|
| Springer `content/pdf/…` direct link | not a PDF — redirects through `idp.springer.com` to a purchase page |
| MPG.PuRe item 2551393 (the MPI's own repository) | **catalogued with an empty file list.** The most promising lead, and there is no scan behind it |
| Europe PMC / PubMed | abstract only; `inPMC: N`, `hasPDF: N` |
| Semantic Scholar | `openAccessPdf.url: ""`, status `CLOSED` |
| author homepages at RUB, USC, FIAS | all four 404 |
| his Cogprints self-archive | four items deposited; **this is not one of them** |
| the 1992 sequel, von der Malsburg & Buhmann, *Sensory segmentation with coupled neural oscillators*, Biol Cybern 67:233–242 | also closed, no OA location |

ResearchGate lists it and returns 403 to any automated check, so whether it serves
a PDF is unverified — and a 1986 Springer-copyright paper there is not plainly
authorised, so it is not a route this repository will take. Pirate mirrors were
excluded from the search by instruction.

**It needs library access, an interlibrary loan, or an email to von der Malsburg,
who is still a senior fellow at FIAS.**

## What the model does

Paraphrased rather than quoted. `lit/README.md` says notes in our own words are
ours to license and a reproduction is not, and one paragraph of convenience is not
worth breaking that in a public repository. Read the abstract at the DOI or PMID
above.

The claim is that sensory segmentation is expressed as **synchronisation within a
segment and desynchronisation between segments** — unit responses are deliberately
unstable in time, and the correlations that group them arise from an autonomous
pattern-formation process rather than being read off a fixed weight matrix.
Coupling comes from two sources: peripheral evidence, meaning similarity of local
quality, and central evidence, meaning shared membership in a stored pattern. The
1986 paper treats only the peripheral case, using the amplitude modulations
present across all components of one sound spectrum — which is common-onset
grouping. It requires a physiological mechanism the authors had to postulate:
**synaptic modulation**, weights changing on a fast timescale. The paper presents
itself as an application of the Correlation Theory of brain function, which is the
1981 report below.

## What is reachable, all verified live

**The parent theory, deposited by von der Malsburg himself** — unambiguously
authorised, and the substrate the 1986 paper says it illustrates:

- *The Correlation Theory of Brain Function* (1981) —
  `web-archive.southampton.ac.uk/cogprints.org/1380/1/vdM_correlation.pdf`
  (308 KB, `%PDF-1.1`; a PostScript version is also listed)
- *Binding in Models of Perception and Brain Function* (1995) — `…/cogprints.org/1486/5/Mal1995a.pdf`
- *The What and Why of Binding: The Modeler's Perspective* (Neuron, 1999) — `…/cogprints.org/1488/5/cvdm.pdf`

**Describing the model without restating its equations:**

- Brown & Cooke's review has a section on this paper specifically —
  `staffwww.dcs.shef.ac.uk/people/G.Brown/pdf/keele96.pdf`. Read: qualitative only.
- DeLiang Wang, *Relaxation Oscillators and Networks*, characterises the 1986 model
  as a fully connected network with an ad hoc oscillator plus a global inhibitory
  oscillator — **and says it cannot simulate basic stream segregation.** That is a
  substantive criticism and it changes what a figure of this model would be
  claiming.
- *An oscillatory correlation model of auditory streaming* — open access via
  Europe PMC, `PMC2289253`. Fetched.

**No open paper restates the 1986 equations in full.** The open oscillator work is
Wang's LEGION lineage, not a faithful restatement, so the architecture cannot be
reconstructed from open sources without guessing — and guessing the architecture
of somebody else's published model is the exact failure this repository is named
for.

## Note on the fetch tool

`murderboard/fetch_paper.py` restricts itself to an allowlist of open-access
hosts, and `web-archive.southampton.ac.uk` is not on it, so the three Cogprints
PDFs above cannot be fetched with it as configured. That allowlist is the tool's
whole design — the host check lives in code rather than in a shell permission
pattern any flag reordering defeats — so the answer is to propose the host
upstream in `murderboard`, not to route around it here. Cogprints is an author
self-archive and von der Malsburg deposited these himself, which is a good case
for the addition; it is somebody else's repository and somebody else's call.
