# Control-design and probe-aiming pitfalls (dogfood real-use passes)

Rules for designing the test controls and probes a dogfood run drives — the run is only as honest as its controls.

## Generate every encoded/transformed test payload with a canonical encoder, never by hand

An apparent deliver-threshold MISS on a normalizer/classifier pipeline (a ROT13/base64/homoglyph payload scored benign) is usually a malformed CONTROL: an off-by-one hand-rotated string is plausible-looking gibberish that is genuinely benign, and the product is innocent. Encode with the mechanism the product decodes (`python3 -c "import codecs; print(codecs.encode(s,'rot13'))"`, `base64 -w0`, ...) and re-run before filing the miss. The correctly encoded control should block with `load_bearing_normalizations` populated — which is also the free re-proof that attribution works.

## Discover a pip-installed console script from package metadata, not the package name

`pip install <local dir>/` can succeed while a command name guessed from the package (`<pkg>-client`) fails 'No such file or directory' — `[project.scripts]` is free to name the console command anything. Before filing 'no CLI entry point': `ls <venv>/bin/` and grep the project's pyproject for `[project.scripts]`. The guess itself is the false finding; the real gap is a README that never states the command name (a P3 docs finding, not a packaging defect).

## Aim a 0-action/0-row policy probe at the stat the policy reader actually consumes

Before reading a 0-action/0-row policy result as 'the product ignores X', verify WHICH stat the reader consumes and aim the probe at THAT object. An age/size sweep that keys on a run dir's own mtime reports '0 actions' forever if you only touched files inside it — the probe was mis-aimed, not the product inert. One stat check (or one source read of the expiry predicate) before building the first synthetic fixture; then drive each policy bound alone, the bounds together (whichever-first must still fire the second), and the invalid combination.
