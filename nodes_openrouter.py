import base64
import time
from io import BytesIO

import requests
import torch

import comfy.model_management
from comfy_api.latest import InputImpl, io
from comfy_api_nodes.util.conversions import bytesio_to_image_tensor, tensor_to_data_uri

from . import openrouter

Kunde = io.Custom("MAYBAUM_OPENROUTER")

# Alle Werte, die OpenRouter kennt. Pro Modell blendet web/openrouter_options.js nur die erlaubten ein,
# validate_inputs prüft gegen die Modellliste. "auto" heisst: nicht mitschicken, Standard des Modells.
IMAGE_ASPECT_RATIOS = ["auto", "1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3", "5:4", "4:5", "21:9", "9:21", "2:1", "1:2", "4:1", "1:4", "8:1", "1:8", "7:5", "5:7", "19.5:9", "9:19.5", "20:9", "9:20"]
VIDEO_ASPECT_RATIOS = ["auto", "1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3", "5:4", "4:5", "21:9", "9:21"]
VIDEO_DURATIONS = ["auto"] + [str(s) for s in range(1, 61)]
VIDEO_TIMEOUT = 30 * 60


def model_input(kind):
    return io.Combo.Input(
        "model",
        options=[],
        remote=io.RemoteOptions(route=f"/maybaum/openrouter/models/{kind}", refresh_button=True),
        tooltip="Live-Liste von OpenRouter.",
    )


def reference_input():
    return io.Autogrow.Input(
        "reference_images",
        template=io.Autogrow.TemplatePrefix(io.Image.Input("image"), prefix="image_", min=0, max=16),
        tooltip="Referenzbilder. Jeder Eingang nimmt auch einen ganzen Batch, jedes Bild darin wird eine eigene Referenz.",
    )


def image_urls(images):
    return [{"type": "image_url", "image_url": {"url": tensor_to_data_uri(image)}} for batch in images for image in batch]


def format_info(kunde, model, usage, start):
    parts = [f"Kunde: {kunde}", f"Modell: {model}", f"Zeit: {time.time() - start:.1f} s"]
    if usage and usage.get("cost") is not None:
        parts.append(f"Kosten: ${float(usage['cost']):.4f}")
    return " · ".join(parts)


class MaybaumOpenRouterKunde(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MaybaumOpenRouterKunde",
            display_name="OpenRouter API",
            category="Maybaum",
            description="Wählt den OpenRouter-Key eines Kunden. Keys liegen nur im RAM und gehen bei einem Neustart verloren.",
            inputs=[
                io.Combo.Input(
                    "alias",
                    options=[],
                    remote=io.RemoteOptions(route="/maybaum/openrouter/aliases", refresh_button=True, refresh=1000),
                    tooltip="Kunden-Alias. Keys über «Keys verwalten» einfügen.",
                ),
            ],
            outputs=[Kunde.Output(display_name="kunde")],
        )

    @classmethod
    def validate_inputs(cls, alias):
        return openrouter.check_alias(alias)

    @classmethod
    def execute(cls, alias):
        return io.NodeOutput(alias)


class MaybaumOpenRouterImage(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MaybaumOpenRouterImage",
            display_name="OpenRouter Image",
            category="Maybaum",
            description="Bildgenerierung über OpenRouter (/api/v1/images). Optionen erscheinen nur, wenn das Modell sie unterstützt.",
            inputs=[
                Kunde.Input("kunde"),
                io.String.Input("prompt", multiline=True),
                model_input("images"),
                io.Combo.Input("aspect_ratio", options=IMAGE_ASPECT_RATIOS),
                io.Combo.Input("resolution", options=["auto", "512", "768", "1K", "1.5K", "2K", "4K"]),
                io.Combo.Input("quality", options=["auto", "low", "medium", "high", "xhigh", "max"]),
                io.Int.Input("seed", default=0, min=0, max=2147483647, control_after_generate=True),
                io.Combo.Input("output_format", options=["auto", "png", "jpeg", "webp"], tooltip="Format, in dem das Modell liefert. Kein Einfluss auf den Ausgang IMAGE."),
                io.Boolean.Input("transparent_background", default=False, tooltip="Die Transparenz kommt als Maske am Ausgang «mask»."),
                io.Int.Input("batch", default=1, min=1, max=10, tooltip="Anzahl Bilder pro Request. Manche Modelle liefern weniger."),
                reference_input(),
            ],
            outputs=[io.Image.Output(), io.String.Output(display_name="info"), io.Mask.Output(display_name="mask")],
        )

    @classmethod
    def validate_inputs(cls, model, aspect_ratio, resolution, quality, output_format, transparent_background, batch, reference_images=None):
        if transparent_background and output_format == "jpeg":
            return "Transparenter Hintergrund geht nicht mit output_format jpeg."
        return openrouter.check_options(
            "images", model, aspect_ratio=aspect_ratio, resolution=resolution, quality=quality,
            output_format=output_format, transparent_background=transparent_background, batch=batch,
        )

    @classmethod
    def execute(cls, kunde, prompt, model, aspect_ratio, resolution, quality, seed, output_format, transparent_background, batch, reference_images=None):
        payload = {"model": model, "prompt": prompt}
        for name, value in (("aspect_ratio", aspect_ratio), ("resolution", resolution), ("quality", quality), ("output_format", output_format)):
            if value != "auto":
                payload[name] = value
        if transparent_background:
            payload["background"] = "transparent"
            if "output_format" not in payload and (alpha_format := openrouter.transparent_format(model)):
                payload["output_format"] = alpha_format
        if batch > 1:
            payload["n"] = batch
        if "seed" in openrouter.capabilities("images", model):
            payload["seed"] = seed
        if reference_images:
            payload["input_references"] = image_urls(reference_images.values())

        start = time.time()
        data = openrouter.request(kunde, "POST", "/images", json=payload).json()
        images, masks = [], []
        for item in data["data"]:
            image = bytesio_to_image_tensor(BytesIO(base64.b64decode(item["b64_json"])))
            # Maske wie bei LoadImage: 1 = transparent. Ohne Alphakanal leer.
            masks.append(1.0 - image[..., 3] if image.shape[-1] == 4 else torch.zeros(image.shape[:3]))
            images.append(image[..., :3])
        info = format_info(kunde, model, data.get("usage"), start)
        if batch > 1:
            info += f" · Bilder: {len(images)}"
        return io.NodeOutput(torch.cat(images), info, torch.cat(masks))


class MaybaumOpenRouterVideo(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MaybaumOpenRouterVideo",
            display_name="OpenRouter Video",
            category="Maybaum",
            description="Videogenerierung über OpenRouter (/api/v1/videos, asynchron). Optionen erscheinen nur, wenn das Modell sie unterstützt.",
            inputs=[
                Kunde.Input("kunde"),
                io.String.Input("prompt", multiline=True),
                model_input("videos"),
                io.Combo.Input("duration", options=VIDEO_DURATIONS, tooltip="Sekunden."),
                io.Combo.Input("resolution", options=["auto", "480p", "720p", "768p", "1080p", "2K", "4K"]),
                io.Combo.Input("aspect_ratio", options=VIDEO_ASPECT_RATIOS),
                io.Boolean.Input("generate_audio", default=True),
                io.Int.Input("seed", default=0, min=0, max=2147483647, control_after_generate=True),
                io.Image.Input("first_frame", optional=True),
                io.Image.Input("last_frame", optional=True),
                reference_input(),
            ],
            outputs=[io.Video.Output(), io.String.Output(display_name="info")],
        )

    @classmethod
    def validate_inputs(cls, model, duration, resolution, aspect_ratio, reference_images=None):
        return openrouter.check_options("videos", model, duration=duration, resolution=resolution, aspect_ratio=aspect_ratio)

    @classmethod
    def execute(cls, kunde, prompt, model, duration, resolution, aspect_ratio, generate_audio, seed, first_frame=None, last_frame=None, reference_images=None):
        caps = openrouter.capabilities("videos", model)
        payload = {"model": model, "prompt": prompt}
        if duration != "auto":
            payload["duration"] = int(duration)
        for name, value in (("resolution", resolution), ("aspect_ratio", aspect_ratio)):
            if value != "auto":
                payload[name] = value
        if "generate_audio" in caps:
            payload["generate_audio"] = generate_audio
        if "seed" in caps:
            payload["seed"] = seed
        frames = []
        for frame_type, image in (("first_frame", first_frame), ("last_frame", last_frame)):
            if image is not None:
                frames.append({**image_urls([image[:1]])[0], "frame_type": frame_type})
        if frames:
            payload["frame_images"] = frames
        if reference_images:
            payload["input_references"] = image_urls(reference_images.values())

        start = time.time()
        job = openrouter.request(kunde, "POST", "/videos", json=payload, timeout=120).json()
        job_id = job["id"]
        while job["status"] in ("pending", "in_progress"):
            if time.time() - start > VIDEO_TIMEOUT:
                raise RuntimeError(f"Video-Job {job_id} nach {VIDEO_TIMEOUT // 60} min nicht fertig. Abgebrochen, der Job läuft bei OpenRouter evtl. weiter.")
            time.sleep(5)
            comfy.model_management.throw_exception_if_processing_interrupted()
            try:
                job = openrouter.request(kunde, "GET", f"/videos/{job_id}", timeout=60).json()
            except (requests.ConnectionError, requests.Timeout):
                continue
        if job["status"] != "completed":
            raise RuntimeError(f"Video-Job {job_id} · Status {job['status']}: {job.get('error')}")

        content = openrouter.request(kunde, "GET", f"/videos/{job_id}/content", params={"index": 0}).content
        return io.NodeOutput(InputImpl.VideoFromFile(BytesIO(content)), format_info(kunde, model, job.get("usage"), start))
