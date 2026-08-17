# Implementing and Validating Physically Based Rendering Techniques

A thesis renderer implemented as extensible [Mitsuba 3](https://mitsuba-renderer.org/) plugins. The project combines a custom path tracer, Disney-style Principled BSDF, HDR environment importance sampling, a physical thin-lens camera, auxiliary image outputs, and optional Intel Open Image Denoise (OIDN) processing.

This repository accompanies the thesis **“Implementing and Validating Physically Based Rendering Techniques in an Extensible Renderer.”** Its focus is not merely producing plausible images: each component is tested progressively against theory, Mitsuba reference components, statistical controls, isolated feature scenes, Blender-authored assets, and a production-scale interior.

Mitsuba and Dr.Jit provide scene loading, geometry, ray intersection, films, samplers, plugin interfaces, and vectorised execution. The work in this repository implements and evaluates the transport, material, lighting, camera, scene-integration, and post-processing behaviour built on that foundation.

> **Project walkthrough:** [Watch the renderer demonstration on YouTube](https://youtu.be/x9QPDBPHqjg)

## Contents

- [Thesis context](#thesis-context)
- [System overview](#system-overview)
- [Installation](#installation)
- [Rendering with main.py](#rendering-with-mainpy)
- [Generating useful images](#generating-useful-images)
- [Reproducing the evaluations](#reproducing-the-evaluations)
- [Output files](#output-files)
- [Repository structure](#repository-structure)
- [Implementation documentation](#implementation-documentation)
- [Reproducibility and external evidence](#reproducibility-and-external-evidence)
- [Known limitations](#known-limitations)
- [Troubleshooting](#troubleshooting)
- [AI Acknowledgement](#ai-acknowledgement)
- [Attribution](#attribution)

## Thesis context

The thesis investigates the implementation gap between rendering equations and a working, testable renderer. Correct integration requires more than individual formulas: sampling and PDFs must agree, multiple importance sampling must compare compatible probabilities, path-depth conventions must be explicit, numerical edge cases must be controlled, and custom components must follow the host framework’s interfaces.

The implementation addresses four practical questions:

1. Can established physically based rendering techniques be implemented coherently as interchangeable Mitsuba plugins?
2. How do importance sampling, stratification, clamping, and denoising affect variance, bias, and presentation?
3. What problems appear only when moving from synthetic controls to authored and production-scale scenes?
4. How closely can the custom pipeline reproduce Blender Cycles under carefully matched—but not identical—conditions?

The contribution is implementation, integration, and experimental validation rather than new rendering theory or a replacement for a production renderer.

### Validation ladder

| Thesis section | Responsibility | Main evidence |
| --- | --- | --- |
| 5.1 | Path tracer | Furnace convergence, GGX controls, reference-integrator substitution, AOV checks |
| 5.2 | Principled BSDF | Furnace behaviour, chi-squared tests, GTR1 checks, smooth dielectric equivalence |
| 5.3 | Sampling and reconstruction | HDR importance sampling, sampler comparisons, clamping, OIDN |
| 5.4 | Isolated features | Material gallery, glazing, camera projection, DoF, bokeh, visibility |
| 5.5 | Production integration | Blender-authored LEGO Bulldozer and Country Kitchen |
| 5.6 | Scale-dependent failure | Environment shadow-ray distance regression and historical evidence audit |
| 6 | Blender Cycles comparison | Descriptive controlled and production-scene comparisons |

Numerical tests and production scenes serve different purposes. A plausible final render does not prove estimator correctness, while a small furnace test cannot expose every scale, visibility, or asset-integration problem. The repository therefore preserves both.

## System overview

```text
Scene + sampler
      |
      v
Physical camera ---------> camera rays
      |
      v
Custom path tracer ------> intersections supplied by Mitsuba
      |  \
      |   +--------------> custom HDR environment emitter
      |                   luminance / solid-angle importance sampling
      |
      +------------------> BSDF eval(), pdf(), sample()
                          Principled diffuse, GGX, anisotropy,
                          clearcoat, sheen, textures and transmission
      |
      v
Beauty + optional albedo / normal / depth AOVs
      |
      +------------------> linear EXR or display PNG
      |
      +------------------> optional OIDN post-processing
```

The components remain independently replaceable. This makes controlled comparisons possible—for example, changing only the path integrator while retaining the same BSDF, camera, emitter, sampler, geometry, and path-depth settings.

### Main components

| Component | Plugin | Main controls | Documentation |
| --- | --- | --- | --- |
| Path tracer | `path_tracer` | NEE/MIS, depth, roulette, AOVs, clamping, visibility | [integrators/README.md](integrators/README.md) |
| Principled BSDF | `principled_bsdf` | colour, metallic, specular, roughness, anisotropy, clearcoat, sheen, transmission | [bsdfs/README.md](bsdfs/README.md) |
| Environment emitter | `custom_envmap` | HDR map, scale, rotation, importance CDF, MIS compensation | [emitters/README.md](emitters/README.md) |
| Physical camera | `physical_camera` | FOV, aperture radius, focus distance, aperture blades | [cameras/README.md](cameras/README.md) |
| Denoiser | post-process | beauty + albedo + normal, HDR mode, emitter preservation | [denoisers/oidn.py](denoisers/oidn.py) |

## Installation

### Requirements

- Git
- [Git LFS](https://git-lfs.com/)
- [uv](https://docs.astral.sh/uv/)
- Python 3.13 or newer; the project version is recorded in `.python-version`
- A 64-bit CPU supported by Mitsuba’s LLVM backend
- Sufficient disk space for production meshes, textures, HDR environments, and generated renders

A GPU is not required. The default `llvm_ad_rgb` Mitsuba variant runs on CPU.

### Clone and install

```sh
git lfs install
git clone https://github.com/Gabrielazmbr/Physically-Based-Renderer.git
cd Physically-Based-Renderer
git lfs pull
uv sync --locked
```

`uv sync --locked` creates the project environment from `uv.lock` without silently updating dependency versions.

Confirm that dependencies and required LFS assets are available:

```sh
uv run python main.py doctor
```

A successful preflight checks Python, Git LFS, Mitsuba, NumPy, OIDN, the Kitchen assets, LEGO meshes, HDR environments, and whether discovered LFS source assets have been downloaded.

Then make a small installation render:

```sh
uv run python main.py render cornell --quality draft
```

The image and its metadata are written to `outputs/renders/`.

### Optional CUDA backend

Place the global variant option before the subcommand:

```sh
uv run python main.py --variant cuda_ad_rgb render cornell --quality draft
```

CUDA requires a compatible Mitsuba installation and GPU. All evaluator-facing commands default to the CPU LLVM variant.

## Rendering with main.py

`main.py` is the interactive entry point for exploring and demonstrating the renderer. It is intentionally separate from the canonical thesis experiments.

List the available scenes:

```sh
uv run python main.py list-scenes
```

| Scene | Purpose | Useful options |
| --- | --- | --- |
| `cornell` | Global illumination, colour bleeding, AOVs, integrator substitution | `--aovs`, `--integrator` |
| `materials` | Eighteen Principled BSDF configurations | `--spp`, `--denoise` |
| `glazing` | Open, thin-sheet, and finite-thickness transmission | `--glazing-mode` |
| `dof` | Near/focal/far depth-of-field behaviour | aperture and focus options |
| `bokeh` | Circular and polygonal out-of-focus highlights | `--aperture-blades` |
| `environment` | Metallic object under HDR image-based lighting | `--envmap-scale` |
| `lego` | Blender-authored LEGO Bulldozer through the custom pipeline | quality and sampling |
| `kitchen` | Country Kitchen hero camera and five close-ups | `--view`, visibility, denoising |

Inspect every available render option:

```sh
uv run python main.py render --help
```

Use `--dry-run` to resolve settings and the destination without loading or rendering the scene:

```sh
uv run python main.py render kitchen --view stove --quality preview --dry-run
```

### Quality presets

| Preset | 16:9 base resolution | Sampling | Intended use |
| --- | ---: | ---: | --- |
| `draft` | 320 × 180 | 4 spp × 1 pass | Installation, framing, fast demonstrations |
| `preview` | 640 × 360 | 16 spp × 1 pass | Visual inspection |
| `final` | 1280 × 720 | 256 spp × 4 passes | Presentation-quality starting point |

Each scene retains its authored aspect ratio. Explicit `--width`, `--height`, `--spp`, `--passes`, and `--seed` values override the selected preset. These presets are conveniences, not the controlled settings used by the thesis evaluations.

The Kitchen and shared material/glazing scenes use stratified sampling. Valid sample counts are `1`, `4`, `16`, `64`, `256`, and so on. Other scenes can use arbitrary positive counts with the independent sampler.

### Path-integrator-only comparison

```sh
uv run python main.py render cornell --quality draft --integrator mitsuba-path
```

This changes only the path integrator to Mitsuba’s `path` implementation. It is **not** a general custom-renderer-versus-Mitsuba comparison, and it does not compare the custom Principled BSDF with a Mitsuba equivalent. The CLI prints this warning and records the comparison scope in metadata.

## Generating useful images

These commands recreate the most useful demonstrations without running an entire thesis section.

### Principled material capability gallery

```sh
uv run python main.py render materials --quality preview --spp 64
```

Output:

```text
outputs/renders/materials_preview.png
outputs/renders/materials_preview.png.json
```

The raw 18-material gallery underlies the labelled Section 5.4 capability map. Its metadata includes every material name and parameter set.

### Transmission and glazing

Solid glass slab:

```sh
uv run python main.py render glazing --quality preview --spp 64
```

Matched controls:

```sh
uv run python main.py render glazing --glazing-mode open --quality preview --spp 64
uv run python main.py render glazing --glazing-mode thin --quality preview --spp 64
```

The default filenames include `open`, `thin`, or `solid`, preventing the three configurations from overwriting one another.

### Circular and six-blade bokeh

```sh
uv run python main.py render bokeh --quality preview --spp 64 \
  --aperture-blades 0 \
  --output outputs/renders/bokeh_circular.png

uv run python main.py render bokeh --quality preview --spp 64 \
  --aperture-blades 6 \
  --output outputs/renders/bokeh_hexagonal.png
```

The dedicated scene uses small bright emitters against a dark background because aperture shape is visible in out-of-focus highlights, not in the silhouette of an ordinary diffuse sphere.

### Depth of field

```sh
uv run python main.py render dof --quality preview --spp 64 \
  --aperture-radius 0.15 --focus-distance 12 \
  --output outputs/renders/dof_finite_aperture.png
```

### AOV output

```sh
uv run python main.py render cornell --quality preview --aovs \
  --output outputs/renders/cornell_aovs.exr
```

The multi-channel EXR contains beauty RGB, albedo RGB, world-space shading-normal XYZ, and depth.

### OIDN denoising

```sh
uv run python main.py render kitchen --view hero --quality preview \
  --spp 16 --transparent-shadows --denoise
```

Denoising automatically enables the auxiliary AOVs needed by OIDN and writes a normal RGB image. It is available only with the custom integrator and is mutually exclusive with `--aovs`.

OIDN is most effective with box-filtered input. Kitchen, materials, and glazing use box reconstruction filters. Denoising is a presentation step, not evidence that the underlying transport estimator is correct.

### LEGO production scene

```sh
uv run python main.py render lego --quality preview --spp 64
```

The scene is reconstructed from the Blender-authored Mitsuba export and rendered entirely through the custom pipeline. Blender is not launched.

### Country Kitchen and close-ups

```sh
uv run python main.py render kitchen --view hero --quality preview \
  --spp 64 --transparent-shadows --denoise

uv run python main.py render kitchen --view stove --quality preview \
  --spp 64 --transparent-shadows --denoise

uv run python main.py render kitchen --view radio --quality preview \
  --spp 64 --transparent-shadows --denoise
```

The available views are `hero`, `stove`, `table`, `radio`, `towel`, and `island`.

### Exact Section 5.4 camera and glazing figures

Some thesis figures combine several controlled renders and labels. Those belong to the evaluation interface:

```sh
uv run python tests/evaluation/features/evaluate_features.py \
  --only camera --output outputs/manual/camera_validation

uv run python tests/evaluation/features/evaluate_features.py \
  --only glazing --output outputs/manual/glazing_validation
```

The first command writes the pinhole/DoF and circular/hexagonal composites. The second writes the open/thin/solid glazing comparison.

## Reproducing the evaluations

`tests/run_evaluations.py` is the common entry point for the controlled thesis experiments. It separates reduced checks from canonical evidence and records experiment-specific settings and metadata.

### Available targets

```sh
uv run python tests/run_evaluations.py --list
```

Targets:

```text
path-tracer
bsdf
sampling
features
lego
kitchen
scale-failure
```

### Low-cost smoke check

Run this first on a new machine:

```sh
uv run python tests/run_evaluations.py --smoke
```

The smoke workflow renders the inexpensive path-tracer AOV control and checks the LEGO and Kitchen manifests. It does not overwrite canonical evidence.

### Reduced evaluations

Reduced settings are the default:

```sh
uv run python tests/run_evaluations.py path-tracer bsdf
uv run python tests/run_evaluations.py features
uv run python tests/run_evaluations.py all
```

These write to `outputs/quick/`.

### Canonical evaluations

Use `--full` deliberately. Full runs can take substantially longer and consume significant disk space:

```sh
uv run python tests/run_evaluations.py --full path-tracer
uv run python tests/run_evaluations.py --full sampling
uv run python tests/run_evaluations.py --full all
```

Canonical artifacts are written beneath `outputs/evaluation/`. For final evidence, run from a clean committed revision so metadata can identify a stable Git state.

### Inspect commands without running

```sh
uv run python tests/run_evaluations.py --dry-run all
uv run python tests/run_evaluations.py --full --dry-run all
```

Use `--keep-going` to complete a batch and report every failure instead of stopping after the first.

### Run one evaluation group

The section runners expose more focused controls. Examples:

```sh
uv run python tests/evaluation/path_tracer/evaluate_path_tracer.py \
  --quick --only aov --output outputs/quick/aov_check

uv run python tests/evaluation/features/evaluate_features.py \
  --quick --only gallery --output outputs/quick/material_gallery

uv run python tests/evaluation/features/evaluate_features.py \
  --quick --only camera --output outputs/quick/camera_features

uv run python tests/evaluation/integration/evaluate_integration.py \
  --scene kitchen --quick --only manifest
```

See [tests/README.md](tests/README.md) for the section map and each folder’s README for methodology, settings, figures, and interpretation.

## Output files

Generated results are intentionally excluded from Git.

```text
outputs/
├── renders/       interactive images and JSON sidecars from main.py
├── quick/         reduced evaluation runs
├── evaluation/    canonical thesis evidence
├── manual/        optional targeted figure runs
└── legacy/        preserved historical outputs when available
```

A successful `main.py` render normally writes:

- a PNG or EXR;
- a neighbouring `.json` sidecar;
- resolved scene, quality, sampling, path, camera, and feature settings;
- effective spp and elapsed time;
- Python, Mitsuba, and backend versions;
- Git commit and dirty-worktree state;
- scene-specific metadata such as material or glazing configuration;
- denoising details when OIDN is enabled.

Evaluation runners additionally write CSV measurements, raw linear EXRs, display PNGs, labelled SVGs, and section metadata as appropriate.

### Why images are absent after cloning

Generated `.exr`, `.png`, and `.svg` files are ignored because canonical and exploratory renders are large and reproducible from the code. The thesis submission’s selected reference images and historical diagnostic evidence are delivered separately.

To obtain images after cloning:

1. run `main.py` for an interactive demonstration;
2. run a reduced evaluation for quick figures;
3. run a selected full evaluation for canonical settings;
4. supply separately delivered reference evidence only when a cross-renderer comparison or historical audit requires it.

The repository does not automatically download WeTransfer or other submission evidence.

## Repository structure

```text
.
├── main.py                         interactive renderer CLI
├── pyproject.toml                  project metadata and dependencies
├── uv.lock                         locked dependency graph
├── bsdfs/
│   ├── principled.py               custom Principled BSDF
│   └── README.md                   material-model implementation notes
├── integrators/
│   ├── path_tracer.py              custom path tracer
│   └── README.md                   transport, NEE, MIS and roulette notes
├── emitters/
│   ├── envmap.py                   HDR environment emitter
│   └── README.md                   IBL sampling notes
├── cameras/
│   ├── physical_camera.py          thin-lens camera
│   └── README.md                   projection and aperture notes
├── denoisers/
│   └── oidn.py                     AOV-guided post-processing
├── assets/
│   ├── scenes/                     reusable demonstration scenes
│   ├── hdri/                       runtime HDR environments
│   └── production_scenes/
│       ├── lego_bulldozer/         meshes, export, Blender file and provenance
│       ├── kitchen_scene/           XML, models, textures and Blender file
│       └── blender_comparison/      optional Chapter 6 controlled sources
├── tests/
│   ├── run_evaluations.py          common launcher
│   ├── _common.py                  shared plugin registration
│   ├── evaluation/                 canonical Section 5.1–5.6 evaluators
│   └── legacy/                     superseded experiments and diagnostics
├── docs/
│   ├── README.md                   documentation map
│   └── development/
│       └── validation-journal.md   historical learning/debugging record
└── outputs/                        generated, ignored artifacts
```

The source tree mirrors Mitsuba’s plugin model and stays intentionally shallow. Active evaluation code is separated from historical experiments so an evaluator can identify the current evidence path quickly.

## Implementation documentation

The component READMEs preserve concept-first explanations and implementation reasoning:

- [Principled BSDF](bsdfs/README.md)
- [Path tracer](integrators/README.md)
- [HDR environment emitter](emitters/README.md)
- [Physical camera](cameras/README.md)

Formal reproducibility documentation is separate:

- [Evaluation catalogue](tests/README.md)
- [Evaluation conventions](tests/evaluation/README.md)
- [Path-tracer evaluation](tests/evaluation/path_tracer/README.md)
- [BSDF evaluation](tests/evaluation/bsdf/README.md)
- [Sampling evaluation](tests/evaluation/sampling/README.md)
- [Feature evaluation](tests/evaluation/features/README.md)
- [Production integration](tests/evaluation/integration/README.md)
- [Scale failure audit](tests/evaluation/scale_failure/README.md)

The [development validation journal](docs/development/validation-journal.md) preserves the chronological experiments, debugging decisions, and intermediate measurements that led to the final suite. It is historical evidence, not the current evaluator interface.

## Reproducibility and external evidence

- `uv.lock` fixes Python dependencies, including Mitsuba and the OIDN binding.
- Random seeds, resolution, spp, pass count, sampler, path depths, clamping, and output destinations are explicit.
- Quick and canonical runs use separate output trees.
- Quantitative images are retained as linear EXRs; PNGs are display derivatives.
- `main.py` writes a JSON sidecar for every successful render.
- Evaluation metadata records software, backend, hardware, Git state, and relevant script or scene hashes.
- Runtime source assets use Git LFS.
- Generated results and separately delivered references are not version-controlled.

### Git LFS policy

Git LFS stores the large source assets needed to render:

- HDR environments;
- LEGO PLY meshes and HDR texture;
- Kitchen OBJ meshes and textures;
- production-scene `.blend` files.

It does not store generated EXR/PNG/SVG results. The Blender files remain available for provenance and optional manual inspection; the evaluator does not need Blender to run the custom renderer or the standard Chapter 5 evaluations.

### External reference images

The LEGO Cycles EXR, selected Chapter 6 Cycles images, and the historical scale-failure images are supplied separately. Evaluators accept them explicitly when available. Without them, the relevant runners still render or inspect the custom implementation and record the external comparison as skipped.

## Known limitations

- The project extends Mitsuba rather than implementing geometry traversal, scene loading, and films from scratch.
- The custom Principled BSDF is not claimed to be numerically equivalent to Mitsuba’s or Blender’s Principled material.
- The `mitsuba-path` option compares path integrators only while retaining the same scene components.
- Smooth transmission supports thin sheets and solid dielectric interfaces, but not rough glass, dispersion, volumetric absorption, or nested-medium management.
- Clearcoat and sheen are documented approximations rather than a complete layered-material simulation.
- Single-scattering GGX loses energy at high roughness because multiple microfacet scattering is not compensated.
- Transparent shadows are an opt-in straight-through visibility approximation for smooth panes.
- Firefly clamping is biased and disabled unless requested.
- OIDN is post-processing and may remove or invent detail; denoised images are not raw transport evidence.
- Cross-renderer Cycles comparisons are descriptive because estimators, BSDFs, filtering, colour handling, and random sequences are not identical.
- The physical camera does not model aberration, lens distortion, cat-eye vignetting, or full optical assemblies.

## Troubleshooting

### `doctor` reports Git LFS pointer files

```sh
git lfs pull
uv run python main.py doctor
```

Do not replace required source assets with generated renders.

### A stratified render rejects the spp value

Use a square power-of-four count such as `1`, `4`, `16`, `64`, or `256`, or select the independent sampler where the scene permits it.

### OIDN cannot run

Synchronise the locked environment:

```sh
uv sync --locked
uv run python main.py doctor
```

`--denoise` requires the custom integrator and cannot be combined with `--aovs`.

### The repository contains no rendered images after cloning

This is intentional. Generated images are ignored. Use the commands under [Generating useful images](#generating-useful-images) or [Reproducing the evaluations](#reproducing-the-evaluations).

### A full evaluation takes a long time

Start with `--smoke`, a selected reduced target, or `--dry-run`. Full material, production-scene, repeated-seed, and high-spp reference runs are intentionally expensive.

## AI Acknowledgement

OpenAI Codex, using GPT-5-family models, was used as a supporting coding assistant during the development of this research project. Its use included assistance with research phase, testing and debugging, consulting the Mitsuba API and related technical documentation, and improving the organization, documentation, and presentation of the repository.

AI-generated suggestions were reviewed, adapted, and tested by the author before being incorporated. The tool supported the development process, while the project’s direction, evaluation, and conclusions were determined by the author.

## Attribution

Third-party production scenes retain their own licensing and provenance records:

- [Country Kitchen licence](assets/production_scenes/kitchen_scene/LICENSE.txt)
- [LEGO Bulldozer licence and attribution](assets/production_scenes/lego_bulldozer/LICENSE.txt)
- [Country Kitchen scene notes](assets/production_scenes/kitchen_scene/README.md)
- [LEGO scene notes](assets/production_scenes/lego_bulldozer/README.md)

The LEGO model is *Lego 856 Bulldozer* by Heinzelnisse, distributed through BlendSwap under CC-BY-NC. LEGO is a trademark of the LEGO Group, which does not sponsor or endorse this research project.

Blender and Cycles are optional external tools used to produce or inspect reference evidence. This repository does not automatically launch Blender or reproduce the separately delivered Cycles renders.
