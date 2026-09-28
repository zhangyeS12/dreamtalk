# Model capacities and request reservations — 2026-09-28

User-approved goal: common models should not require ordinary users to type model input/output capacities. Keep an explicit reply-length preference and the shared hard turn quota; use a reliable request-specific input bound where the provider framing is verifiable.

## Reuse and provenance

- models.dev public API snapshot, reviewed 2026-09-28: https://models.dev/api.json. MIT; notice in `docs/licenses/models-dev.txt`. Select 18 model/service pairs into the single shared `model_presets.json`; React, desktop validation and Core consume this same data. Input reservation uses the full context window, never a catalog input field that may have subtracted the maximum output allowance. This is a reviewed snapshot, not a live capacity lookup, price feed, or guarantee for arbitrary proxies.
- Official DeepSeek pricing/API: https://api-docs.deepseek.com/quick_start/pricing/ and https://api-docs.deepseek.com/api/create-chat-completion/. Current Flash/V4 Pro and published compatibility aliases have 1M context and 393,216 output cap. Output includes reasoning. The UI starts with an 8,192 reply preference; this is an application choice, not a claimed provider capacity. Existing custom values remain visible.
- Official `deepseek-ai/deepseek-recipe`: https://github.com/deepseek-ai/deepseek-recipe; repository reference `8cadfede7063c896b944e7bae05daa3549ae97ea`, Rust crates `deepseek-recipe = 0.1.0` and `deepseek-recipe-encoding = 0.1.0`, locked by Cargo checksums, published source commit `b60af4cf40768602e6928772f01eba451483a442`. MIT notice retained. Reuse the official OpenAI-request conversion and V4/V4.1 conversation rendering. The Python distribution 0.1.1 lacks a Windows wheel and includes image/OpenCV handling; its separate Rust text crates provide the framing without that deployment burden. No chat template is independently recreated.
- SillyTavern context/reply settings inspired the separation of provider capacity and user reply preference. No AGPL SillyTavern code is copied.

## Conservative request bound

The local helper receives the exact adapter-generated text request body, converts it with the official recipe (default thinking enabled, matching the direct API), renders the complete conversation, and returns only the rendered UTF-8 byte length. This is deliberately an upper bound, not an exact token count.

Audit sources at the pinned official repository reference:

- `static/tokenizers/v4/tokenizer.json`
- `static/tokenizers/v41/tokenizer.json`
- `docs/tokenizer.md` and recipe request/conversation rendering code

Both published tokenizers use BPE, an empty Sequence normalizer, split pretokenizers and ByteLevel with `add_prefix_space=false`. The ByteLevel postprocessor handles offsets rather than adding tokens. Every ordinary text token consumes at least one original byte; merging can only reduce that count. Literal special-token spellings, BOS, role separators and the thinking-generation prefix are included in the rendered string and their byte lengths overcount the corresponding special tokens. Counting the complete framed bytes therefore conservatively bounds this text encoding without a character-ratio estimate or special-token injection undercount.

The trusted framing profile is explicitly limited to the reviewed direct `https://api.deepseek.com` or `/v1` endpoints and four published model IDs. Flash and aliases use V4.1; Pro uses V4. Same-named models on proxies do not inherit this profile. This depends on the provider continuing to serve the documented template/tokenizer; model and recipe updates require renewed review. It does not guarantee a provider invoice, undocumented hidden processing, or the accuracy of manually declared limits.

Unsupported structured/streaming/image shapes, converter failure, oversized stdin (>4 MiB), missing helper or a five-second timeout retain the original full-model trusted reservation. Never label an estimate HARD_UPPER_BOUND. The final reservation is the minimum of two independent trusted upper bounds: configured model limit and verified complete framed bytes. Requested output remains bounded by the existing adapter cap.

Core shares this same bounder between chat preflight, every routed physical attempt/retry/fallback and the monetary Budget Guard. Shared turn charging, accounting START and durable chat claim order remain unchanged. Requests are not replayed. No price guessing, hidden-knowledge bypass or world mutations are added. Context truncation/summarization is not implemented in this change; extremely long context may still fail admission or provider context validation.

## Deployment and checks

Build the Rust helper with `cargo build --locked --release --manifest-path tools/deepseek-request-bound/Cargo.toml` before freezing Core. `build-portable.py --build-only` does this automatically. PyInstaller bundles it under `request-bound/`; the shared JSON is package data. No network or credentials are supplied to the helper; stdin stays in memory, stderr is discarded, and only SHA256 digests/numeric results are cached (up to 64). The helper prints a fixed error label rather than conversion details.

Third-party notices and a source/registry-checksum inventory accompany the helper. Dependency source is available at the exact crates.io version URLs in the inventory, including MPL-licensed data dependencies. Source/lint/type/format checks and release compilation are permitted by AGENTS.md; no automated tests, smoke checks or paid-provider calls are performed. User acceptance must verify real saving, restart, direct/group replies and existing authored-content flows.

Capacity review cross-checks: https://developers.openai.com/api/docs/models/gpt-5-mini, https://developers.openai.com/api/docs/models/gpt-4.1, https://platform.claude.com/docs/en/models/overview and https://ai.google.dev/gemini-api/docs/models. Use the full context as the input ceiling even when catalog input/output subdivisions differ. These source pointers are not a live-update system.

The official compare API could not resolve the crate's published source commit (404); no claim is made that published and repository-review revisions are byte-identical. The trusted profile reuses and audits the published official recipe implementation, with the provider/template continuity assumption stated above.
