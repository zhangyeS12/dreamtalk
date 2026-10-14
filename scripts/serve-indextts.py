"""Optional IndexTTS 2.5 loopback bridge; run inside the official model environment.

Not imported by Core, not bundled with model weights. See docs/CHARACTER_VOICES.md.
"""

import argparse
import asyncio
import base64
import contextlib
import faulthandler
import hashlib
import hmac
import logging
import math
import os
import re
import sqlite3
import tempfile
import threading
import time
import traceback
import warnings
import wave
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Header, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

log = logging.getLogger("dreamtalk.speech.local")
INFERENCE_REVISION = 8
CACHE_SECONDS = 6 * 60 * 60
DECODE_CANDIDATES = 3
DECODE_BEAMS = 1
_SENTENCE_CLOSERS = frozenset("”’\"'）)]】》」』〕〉}")
_LENGTH_WARNING = r"^WARN: generation stopped due to exceeding `max_mel_tokens`"
_METRICS = re.compile(
    r"^>> (gpt_gen_time|s2mel_time|bigvgan_time|Total inference time|Generated audio length|RTF): "
    r"([0-9]+(?:\.[0-9]+)?)(?: seconds)?$"
)


class IncompleteSpeechError(ValueError):
    pass


class SentenceCapacityError(ValueError):
    pass


class SpeechReceipts:
    """Content-free dispatch receipts outlive the bounded in-memory audio cache."""

    def __init__(self, path):
        if path.is_symlink():
            raise ValueError("speech_receipts_path_invalid")
        self.connection = sqlite3.connect(path, isolation_level=None)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS receipts "
            "(identity TEXT PRIMARY KEY, state TEXT NOT NULL, error TEXT)"
        )

    def claim(self, identity):
        return (
            self.connection.execute(
                "INSERT OR IGNORE INTO receipts VALUES (?, 'running', NULL)", (identity,)
            ).rowcount
            == 1
        )

    def finish(self, identity, state, error=None):
        self.connection.execute(
            "UPDATE receipts SET state = ?, error = ? WHERE identity = ?", (state, error, identity)
        )

    def lookup(self, identity):
        row = self.connection.execute(
            "SELECT state, error FROM receipts WHERE identity = ?", (identity,)
        ).fetchone()
        if row is None:
            return None
        state, error = row
        if state == "running":
            # A restart or another bridge owns this claim. Never infer it again.
            state, error = "failed", "speech_outcome_unknown"
        elif state == "ready":
            state, error = "expired", "speech_cache_expired"
        return dict(state=state, phase=state, segment=None, segments=None, error=error)


class ReferenceIdentity:
    """Reuse native conditioning only for identical consecutive reference bytes.

    IndexTTS identifies its one-entry tensor cache by a file path. Each attempt
    still owns/deletes its temporary media; only a proven identical reference
    may rebind that cache's identity to the new temporary path. No audio or
    extra tensor cache is retained here.
    """

    def __init__(self):
        self.key = None
        self.path = None

    def bind(self, model, prompt, reference, reference_name):
        key = (id(model), hashlib.sha256(reference).digest(), reference_name)
        same_reference = key == self.key
        speaker_hit = (
            same_reference
            and getattr(model, "cache_spk_audio_prompt", None) == self.path
            and all(
                getattr(model, field, None) is not None
                for field in (
                    "cache_spk_cond",
                    "cache_s2mel_style",
                    "cache_s2mel_prompt",
                    "cache_mel",
                )
            )
        )
        emotion_hit = (
            same_reference
            and getattr(model, "cache_emo_audio_prompt", None) == self.path
            and getattr(model, "cache_emo_cond", None) is not None
        )
        path = str(prompt)
        if speaker_hit:
            model.cache_spk_audio_prompt = path
        if emotion_hit:
            model.cache_emo_audio_prompt = path
        self.key, self.path = key, path
        log.info(
            "local_speech reference_cache speaker_hit=%s emotion_hit=%s reference_bytes=%d",
            speaker_hit,
            emotion_hit,
            len(reference),
        )


def token_count(value):
    try:
        shape = getattr(value, "shape", ())
        if len(shape) != 2 or not 1 <= int(shape[0]) <= DECODE_CANDIDATES:
            return -1
        count = int(shape[-1])
        return count if 0 <= count <= 65536 else -1
    except (TypeError, ValueError, OverflowError):
        return -1


@contextlib.contextmanager
def decode_diagnostics(model, job):
    """Observe the unchanged native decoder; never log tokens, text or audio."""
    decoder = model.gpt
    original = decoder.inference_speech
    had_override = "inference_speech" in decoder.__dict__
    override = decoder.__dict__.get("inference_speech")

    def observed(*args, **kwargs):
        inputs = args[1] if len(args) > 1 else kwargs.get("text_inputs")
        input_count = token_count(inputs)
        log.info(
            "local_speech decode_started input_tokens=%d limit=%d beams=%d "
            "candidates=%d segment=%s segments=%s",
            input_count,
            int(model.cfg.gpt.max_mel_tokens),
            DECODE_BEAMS,
            DECODE_CANDIDATES,
            job["segment"],
            job["segments"],
        )
        started = time.monotonic()
        result = original(*args, **kwargs)
        try:
            codes = result[0]
            output_count = token_count(codes)
            if output_count < 1:
                raise ValueError("unsupported_decoder_result")
            ended = bool((codes[:, -1] == model.stop_mel_token).all().item())
            log.info(
                "local_speech decode_finished input_tokens=%d output_tokens=%d "
                "ended=%s decode_seconds=%.3f segment=%s segments=%s",
                input_count,
                output_count,
                ended,
                time.monotonic() - started,
                job["segment"],
                job["segments"],
            )
        except Exception:
            # Diagnostic incompatibility must not invalidate otherwise valid audio.
            log.warning("local_speech decode_diagnostics_unavailable")
        return result

    decoder.inference_speech = observed
    try:
        yield
    finally:
        if had_override:
            decoder.inference_speech = override
        else:
            del decoder.inference_speech


@contextlib.contextmanager
def sampled_candidates(model):
    """One native sampling call returns three candidates; keep a completed one.

    Beam sampling can exhaust the full audio capacity on otherwise short input.
    Use the installed Transformers API, without editing upstream model code or
    rerunning the decoder. Scores and unselected tokens exist only in this call.
    """
    generator = model.gpt.inference_model
    original = generator.generate
    had_override = "generate" in generator.__dict__
    override = generator.__dict__.get("generate")

    def generate(*args, **kwargs):
        inputs = args[0] if args else kwargs.get("inputs", kwargs.get("input_ids"))
        if token_count(inputs) < 1 or int(inputs.shape[0]) != 1:
            raise ValueError("speech_candidate_inputs_unsupported")
        prefix = int(inputs.shape[-1])
        kwargs.update(
            do_sample=True,
            num_beams=DECODE_BEAMS,
            num_return_sequences=DECODE_CANDIDATES,
            return_dict_in_generate=True,
            output_scores=True,
        )
        result = original(*args, **kwargs)
        sequences = result.sequences
        if token_count(sequences) < 1 or int(sequences.shape[0]) != DECODE_CANDIDATES:
            raise ValueError("speech_candidate_results_unsupported")
        scores = generator.compute_transition_scores(
            sequences, result.scores, normalize_logits=True
        )
        generated = sequences[:, prefix:]
        if scores.shape != generated.shape or generated.shape[-1] < 1:
            raise ValueError("speech_candidate_scores_unsupported")
        choices, lengths, ended = [], [], []
        for index, codes in enumerate(generated):
            endings = (codes == model.stop_mel_token).nonzero()
            complete = bool(endings.numel())
            length = int(endings[0, 0].item()) + 1 if complete else int(codes.shape[0])
            score = float(scores[index, :length].sum().item())
            lengths.append(length)
            ended.append(complete)
            if math.isfinite(score) and length > 1:
                choices.append((complete, score, index))
        if not choices:
            raise IncompleteSpeechError("speech_audio_incomplete")
        # Prefer normal termination, then the sequence log probability, matching
        # the existing length_penalty=0. Never insert or force an end token.
        complete, _score, selected = max(choices)
        log.info(
            "local_speech candidates count=%d ended=%s tokens=%s selected=%d",
            DECODE_CANDIDATES,
            ",".join(str(int(value)) for value in ended),
            ",".join(str(value) for value in lengths),
            selected,
        )
        # A candidate without EOS goes back unchanged to the official warning
        # path. Completed candidates lose only post-EOS padding before synthesis.
        end = prefix + lengths[selected] if complete else int(sequences.shape[-1])
        return sequences[selected : selected + 1, :end]

    generator.generate = generate
    try:
        yield
    finally:
        if had_override:
            generator.generate = override
        else:
            del generator.generate


class SentenceSegmentation:
    """Pack full-stop sentences into the loaded model's actual text capacity."""

    def text_capacity(self):
        return min(
            int(self.cfg.gpt.max_text_tokens),
            int(self.gpt.text_pos_embedding.emb.num_embeddings) - 2,
        )

    def infer(self, spk_audio_prompt, text, output_path, lang, **kwargs):
        # Use the official full-audio generator directly. Its normalization and
        # language prefix must precede packing, including on low-VRAM devices;
        # the outer infer wrapper would first split raw text at 40 characters.
        kwargs["max_text_tokens_per_segment"] = self.text_capacity()
        kwargs["stream_return"] = False
        return next(self.infer_generator(spk_audio_prompt, text, output_path, lang, **kwargs), None)

    def sentences(self, text):
        sentences, current = [], []
        boundary = False
        for piece, atomic in self._split_atomic_pieces(text):
            if atomic:
                if boundary:
                    sentences.append("".join(current))
                    current = []
                current.append(piece)
                boundary = False
                continue
            for index, char in enumerate(piece):
                if boundary and not (char in _SENTENCE_CLOSERS or char in ".。" or char.isspace()):
                    sentences.append("".join(current))
                    current = []
                    boundary = False
                current.append(char)
                decimal = (
                    char == "."
                    and index > 0
                    and index + 1 < len(piece)
                    and piece[index - 1].isdecimal()
                    and piece[index + 1].isdecimal()
                )
                if char == "。" or (char == "." and not decimal):
                    boundary = True
        if current:
            sentences.append("".join(current))
        return [sentence for sentence in sentences if sentence.strip()]

    def split_text_by_tokens(self, text, max_tokens, lang_prefix=""):
        # Ignore the caller's software threshold; read the loaded model's real
        # embedding capacity and reserve its language/termination positions.
        del max_tokens
        capacity = self.text_capacity()
        budget = capacity - self._token_len(lang_prefix)
        if budget < 1:
            raise SentenceCapacityError("speech_sentence_capacity")

        def fits(value):
            return self._token_len(lang_prefix + value) <= capacity

        if fits(text):
            return [text]
        segments = []
        current = ""
        for sentence in self.sentences(text):
            if fits(current + sentence):
                current += sentence
                continue
            # The accumulated text ends at the last full stop that fits.
            if current:
                segments.append(current)
                current = ""
            if fits(sentence):
                current = sentence
                continue
            # Only a sentence exceeding physical capacity uses the original
            # tokenizer-aware fallback, including its protected pronunciation tags.
            pieces = super().split_text_by_tokens(sentence, capacity, lang_prefix)
            if not pieces or any(not fits(piece) for piece in pieces):
                raise SentenceCapacityError("speech_sentence_capacity")
            segments.extend(pieces[:-1])
            current = pieces[-1]
        if current:
            segments.append(current)
        return segments or [text]


class MetricsSink:
    """Discard model text; retain only bounded, fixed numerical performance labels."""

    def __init__(self):
        self.values = {}
        self.pending = ""
        self.dropping = False
        self.enabled = False

    def write(self, value):
        for part in value.splitlines(keepends=True):
            ended = part.endswith(("\n", "\r"))
            if not self.dropping:
                self.pending += part
                if len(self.pending) > 256:
                    self.pending = ""
                    self.dropping = True
            if ended:
                if not self.dropping:
                    matched = _METRICS.fullmatch(self.pending.rstrip("\r\n"))
                    if matched and self.enabled:
                        name = matched[1]
                        self.values[name] = self.values.get(name, 0) + float(matched[2])
                self.pending = ""
                self.dropping = False
        return len(value)

    def flush(self):
        pass


class SpeechRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    engine: str = Field(pattern=r"^indextts-2\.5$")
    text: str = Field(min_length=1, max_length=2000)
    language: str = Field(pattern=r"^(ZH|EN|JA|ES|AR)$")
    speed: float = Field(ge=0.5, le=2)
    reference_name: str = Field(pattern=r"^reference\.(wav|mp3)$")
    reference_base64: str = Field(max_length=14 * 1024 * 1024)
    request_id: str = Field(pattern=r"^[0-9a-f-]{36}$")


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
    faulthandler.enable()
    parser = argparse.ArgumentParser(description="dreamtalk 的可选 IndexTTS 2.5 本地配音服务")
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--token-file", type=Path, required=True)
    parser.add_argument("--port", type=int, default=7861)
    options = parser.parse_args()
    token = options.token_file.read_text(encoding="utf-8").strip()
    if len(token) < 32 or len(token) > 4096:
        parser.error("token-file 需包含至少 32 字符的本地访问密钥")
    model_dir = options.model_dir.resolve()
    if not (model_dir / "config.yaml").is_file():
        parser.error("model-dir 未找到官方 config.yaml 和模型权重")
    gate = asyncio.Lock()
    model = None
    reference_identity = ReferenceIdentity()
    jobs = {}
    receipts = SpeechReceipts(
        options.token_file.resolve().parent / "dreamtalk-speech-receipts.sqlite3"
    )
    status_lock = threading.Lock()
    cache_changed = asyncio.Event()

    def expire_audio():
        now = time.monotonic()
        delay = 60.0
        with status_lock:
            for job in jobs.values():
                if "audio" not in job:
                    continue
                remaining = job["audio_saved"] + CACHE_SECONDS - now
                if remaining <= 0:
                    job.pop("audio")
                    job.update(state="expired", phase="expired", error="speech_cache_expired")
                else:
                    delay = min(delay, remaining)
            # Keep recent live/cache metadata bounded without losing dispatch IDs.
            terminal = [key for key, job in jobs.items() if job["state"] != "running"]
            terminal.sort(key=lambda key: "audio" in jobs[key])
            for identity in terminal[: max(0, len(jobs) - 1024)]:
                del jobs[identity]
        return max(0.1, delay)

    async def clean_cache():
        while True:
            cache_changed.clear()
            delay = expire_audio()
            try:
                await asyncio.wait_for(cache_changed.wait(), timeout=delay)
            except TimeoutError:
                pass

    @contextlib.asynccontextmanager
    async def lifespan(_app):
        cleanup = asyncio.create_task(clean_cache())
        try:
            yield
        finally:
            cleanup.cancel()
            await asyncio.gather(cleanup, return_exceptions=True)
            receipts.connection.close()

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)

    def authorize(authorization):
        if not hmac.compare_digest(authorization, "Bearer " + token):
            raise HTTPException(401, "speech_local_key_required")

    def phase(job, value, segment=None, segments=None):
        with status_lock:
            job.update(phase=value, segment=segment, segments=segments, updated=time.monotonic())
        log.info("local_speech phase=%s segment=%s segments=%s", value, segment, segments)

    def infer(body, reference, job):
        nonlocal model
        # Collect final fixed numerical labels without retaining replies or paths.
        sink = MetricsSink()
        with contextlib.redirect_stdout(sink):
            if model is None:
                phase(job, "loading_model")
                log.info("local_speech model_loading")
                loading_started = time.monotonic()
                from indextts.infer_v2_5 import IndexTTS2

                class SentenceIndexTTS(SentenceSegmentation, IndexTTS2):
                    pass

                model = SentenceIndexTTS(
                    cfg_path=str(model_dir / "config.yaml"),
                    model_dir=str(model_dir),
                    use_bf16=True,
                    use_cuda_kernel=False,
                )
                log.info(
                    "local_speech model_ready load_seconds=%.3f",
                    time.monotonic() - loading_started,
                )
            device = str(model.device)
            if not re.fullmatch(r"cpu|cuda(?::[0-9]{1,2})?|mps|xpu", device):
                device = "other"
            log.info(
                "local_speech inference_config device=%s bf16=%s "
                "segmentation=full_stop_packed text_capacity=%d audio_capacity=%d "
                "strategy=independent_sampling candidates=%d beams=%d text_chars=%d",
                device,
                bool(model.use_bf16),
                model.text_capacity(),
                int(model.cfg.gpt.max_mel_tokens),
                DECODE_CANDIDATES,
                DECODE_BEAMS,
                len(body.text),
            )
            phase(job, "preparing_text")

            def progress(_value, desc="", **_kwargs):
                # Only the official fixed stage labels are used; never publish text.
                if desc == "starting inference...":
                    sink.enabled = False
                match = re.fullmatch(r"speech synthesis (\d+)/(\d+)\.\.\.", desc)
                if match:
                    phase(job, "synthesizing", int(match[1]), int(match[2]))
                elif desc == "saving audio...":
                    sink.enabled = True
                    phase(job, "saving_audio")
                elif desc == "text processing...":
                    phase(job, "preparing_text")

            model.gr_progress = progress
            with tempfile.TemporaryDirectory(prefix="dreamtalk-voice-") as folder:
                prompt = Path(folder) / body.reference_name
                output = Path(folder) / "output.wav"
                prompt.write_bytes(reference)
                reference_identity.bind(model, prompt, reference, body.reference_name)
                log.info("local_speech generation_started")
                inference_started = time.monotonic()
                try:
                    with (
                        sampled_candidates(model),
                        decode_diagnostics(model, job),
                        warnings.catch_warnings(),
                    ):
                        warnings.filterwarnings(
                            "error",
                            message=_LENGTH_WARNING,
                            category=RuntimeWarning,
                            module=r"indextts\.infer_v2_5",
                        )
                        model.infer(
                            spk_audio_prompt=str(prompt),
                            text=body.text,
                            lang=body.language,
                            output_path=str(output),
                            duration_factor=1 / body.speed,
                            use_emo_text=False,
                            use_random=False,
                            verbose=False,
                            max_mel_tokens=int(model.cfg.gpt.max_mel_tokens),
                            num_beams=DECODE_BEAMS,
                        )
                except RuntimeWarning as error:
                    if not re.match(_LENGTH_WARNING, str(error)):
                        raise
                    log.warning(
                        "local_speech incomplete_generation elapsed_seconds=%.3f "
                        "segment=%s segments=%s",
                        time.monotonic() - inference_started,
                        job["segment"],
                        job["segments"],
                    )
                    raise IncompleteSpeechError("speech_audio_incomplete") from None
                with output.open("rb") as file:
                    data = file.read(32 * 1024 * 1024 + 1)
                if len(data) > 32 * 1024 * 1024:
                    raise ValueError("audio_size_limit")
                with wave.open(str(output), "rb") as saved_audio:
                    audio_seconds = saved_audio.getnframes() / saved_audio.getframerate()
                if audio_seconds <= 0:
                    raise ValueError("empty_audio")
                metrics = sink.values
                inference_seconds = time.monotonic() - inference_started
                log.info(
                    "local_speech generation_finished elapsed_seconds=%.3f gpt_seconds=%.3f "
                    "acoustic_seconds=%.3f vocoder_seconds=%.3f audio_seconds=%.3f rtf=%.4f",
                    inference_seconds,
                    metrics.get("gpt_gen_time", -1),
                    metrics.get("s2mel_time", -1),
                    metrics.get("bigvgan_time", -1),
                    audio_seconds,
                    inference_seconds / audio_seconds,
                )
                return data

    async def run(body, reference, job):
        try:
            data = await asyncio.to_thread(infer, body, reference, job)
            receipts.finish(body.request_id, "ready")
            job["audio"] = data
            job["audio_saved"] = time.monotonic()
            job["state"] = "ready"
            phase(job, "ready")
            cache_changed.set()
            # Bounded derived audio; durable receipts prevent old-ID regeneration.
            total = sum(len(item.get("audio", b"")) for item in jobs.values())
            for item in jobs.values():
                if total <= 96 * 1024 * 1024:
                    break
                if item is not job and item.get("audio"):
                    total -= len(item["audio"])
                    item.pop("audio")
                    item.update(state="expired", phase="expired")
        except IncompleteSpeechError:
            job.update(state="failed", error="speech_audio_incomplete")
            phase(job, "failed")
        except SentenceCapacityError:
            job.update(state="failed", error="speech_sentence_capacity")
            phase(job, "failed")
        except Exception as error:
            frames = traceback.extract_tb(error.__traceback__)[-8:]
            labels = ";".join(f"{Path(f.filename).name}:{f.lineno}:{f.name}" for f in frames)
            log.error(
                "local_speech generation_failed type=%s frames=%s", type(error).__name__, labels
            )
            job.update(state="failed", error="speech_generation_failed")
            phase(job, "failed")
        finally:
            if job["state"] == "failed":
                try:
                    receipts.finish(body.request_id, "failed", job["error"])
                except sqlite3.Error:
                    # The durable running claim remains unknown, never replayable.
                    log.error("local_speech receipt_update_failed")
            gate.release()
            cache_changed.set()

    def snapshot(job):
        with status_lock:
            return {key: job[key] for key in ("state", "phase", "segment", "segments", "error")}

    @app.get("/health")
    async def health(authorization: str = Header(default="")):
        authorize(authorization)
        expire_audio()
        return {
            "engine": "indextts-2.5",
            "protocol": 2,
            "inference_revision": INFERENCE_REVISION,
            "busy": gate.locked(),
            "model_loaded": model is not None,
            "maintenance_protocol": 1,
            "pid": os.getpid(),
        }

    @app.post("/maintenance/shutdown")
    async def maintenance_shutdown(authorization: str = Header(default="")):
        authorize(authorization)
        if gate.locked():
            raise HTTPException(409, "speech_local_busy")
        await gate.acquire()
        server.should_exit = True
        return {"state": "stopping"}

    async def submit(request, authorization):
        authorize(authorization)
        expire_audio()
        payload = bytearray()
        async for chunk in request.stream():
            if len(payload) + len(chunk) > 14 * 1024 * 1024 + 32768:
                raise HTTPException(413, "speech_request_too_large")
            payload.extend(chunk)
        try:
            body = SpeechRequest.model_validate_json(bytes(payload))
            reference = base64.b64decode(body.reference_base64, validate=True)
            if len(reference) > 10 * 1024 * 1024:
                raise ValueError()
        except ValueError:
            raise HTTPException(422, "speech_request_invalid") from None
        if body.request_id in jobs:
            return body.request_id, snapshot(jobs[body.request_id])
        if stored := receipts.lookup(body.request_id):
            return body.request_id, stored
        if gate.locked():
            raise HTTPException(409, "speech_local_busy")
        await gate.acquire()
        try:
            if not receipts.claim(body.request_id):
                gate.release()
                return body.request_id, receipts.lookup(body.request_id)
        except sqlite3.Error:
            gate.release()
            raise HTTPException(503, "speech_local_receipts_unavailable") from None
        job = {
            "state": "running",
            "phase": "accepted",
            "segment": None,
            "segments": None,
            "error": None,
            "updated": time.monotonic(),
        }
        jobs[body.request_id] = job
        # Retain the task until completion, independent of the submitting socket.
        job["task"] = asyncio.create_task(run(body, reference, job))
        job["task"].add_done_callback(lambda _task: job.pop("task", None))
        log.info("local_speech request_accepted")
        return body.request_id, snapshot(job)

    @app.post("/jobs", status_code=202)
    async def speech(request: Request, authorization: str = Header(default="")):
        _identity, result = await submit(request, authorization)
        return result

    @app.post("/speech")
    async def legacy_speech(request: Request, authorization: str = Header(default="")):
        # Preserve the old single-response transport without another inference.
        identity, _result = await submit(request, authorization)
        job = jobs.get(identity)
        if job is None:
            raise HTTPException(502, "speech_cache_expired")
        if task := job.get("task"):
            await asyncio.shield(task)
        if job["state"] != "ready" or "audio" not in job:
            raise HTTPException(502, "speech_local_generation_failed")
        return Response(job["audio"], media_type="audio/wav", headers={"Cache-Control": "no-store"})

    @app.get("/jobs/{identity}")
    async def status(identity: str, authorization: str = Header(default="")):
        authorize(authorization)
        expire_audio()
        if identity in jobs:
            return snapshot(jobs[identity])
        if stored := receipts.lookup(identity):
            return stored
        raise HTTPException(404, "speech_job_not_found")

    @app.get("/jobs/{identity}/audio")
    async def audio(identity: str, authorization: str = Header(default="")):
        authorize(authorization)
        expire_audio()
        job = jobs.get(identity)
        if job is None or job["state"] != "ready" or "audio" not in job:
            raise HTTPException(404, "speech_audio_not_ready")
        return Response(job["audio"], media_type="audio/wav", headers={"Cache-Control": "no-store"})

    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=options.port, access_log=False)
    )
    server.run()


if __name__ == "__main__":
    main()
