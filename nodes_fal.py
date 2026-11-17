import time
from io import BytesIO

import requests
import torch

import comfy.utils
from comfy_api.latest import InputImpl, Types, io
from comfy_api_nodes.util.conversions import bytesio_to_image_tensor, tensor_to_bytesio

from . import fal
from .nodes_keys import APIKey

# web/fal_options.js fills model, variant and target_resolution from fal and shows only the widgets the model uses.
WIDGETS = {
    "upscale_factor": lambda: io.Float.Input("upscale_factor", default=2.0, min=1.0, max=200.0, step=0.5, tooltip="Scale factor."),
    "variant": lambda: io.Combo.Input("variant", options=["auto"], tooltip="Model variant offered by the selected model."),
    "target_resolution": lambda: io.Combo.Input("target_resolution", options=["auto"]),
    "creativity": lambda: io.Float.Input("creativity", default=0.5, min=0.0, max=10.0, step=0.05, tooltip="How much detail the model may invent. Range depends on the model."),
    "prompt": lambda: io.String.Input("prompt", multiline=True, default="", tooltip="Optional guidance for models that accept a prompt."),
    "negative_prompt": lambda: io.String.Input("negative_prompt", multiline=True, default="", tooltip="What the model should avoid."),
    "strength": lambda: io.Float.Input("strength", default=0.85, min=0.0, max=1.0, step=0.01, tooltip="How much the masked area may change. Range depends on the model."),
    "seed": lambda: io.Int.Input("seed", default=0, min=0, max=2147483647, control_after_generate=True),
    "target_fps": lambda: io.Int.Input("target_fps", default=0, min=0, max=120, tooltip="0 = model default, usually the source frame rate."),
    "frames_between": lambda: io.Int.Input("frames_between", default=1, min=1, max=8, tooltip="Frames generated between each pair of input frames."),
    "slowdown_factor": lambda: io.Int.Input("slowdown_factor", default=1, min=1, max=8, tooltip="1 keeps the speed, 2 doubles the duration (slow motion)."),
}


def model_payload(model, values):
    """Model parameters from the widget values the model uses."""
    payload = {}
    for widget, param in fal.params(model).items():
        if widget not in values:
            continue
        value = values[widget]
        if value == "auto" or (widget == "target_fps" and value == 0):
            if param["required"]:
                raise ValueError(f"{widget}: model '{model}' needs a value.")
            continue
        if widget == "prompt" and not value.strip():
            continue
        if param["type"] == "integer":
            value = round(float(value))
        payload[param["name"]] = value
    return payload


def check_values(model, values):
    try:
        params = fal.params(model)
    except requests.RequestException as e:
        return f"Could not load parameters of '{model}' from fal: {type(e).__name__}"
    except (KeyError, IndexError, StopIteration):
        return f"Model '{model}' is not available on fal."
    for widget in fal.COMBO_WIDGETS:
        value = values.get(widget, "auto")
        if value != "auto" and value not in (params.get(widget) or {}).get("enum", []):
            return f"{widget} '{value}' is not possible with model '{model}'."
    return True


def first_url(result, kind):
    if kind in result:
        return result[kind]["url"]
    return result[kind + "s"][0]["url"]


def format_info(api_key, model, start):
    parts = [f"Alias: {api_key}", f"Model: {model}", f"Time: {time.time() - start:.1f} s"]
    if price := fal.price(model):
        parts.append(f"Price: {price}")
    return " · ".join(parts)


def upload_video(api_key, video):
    buffer = BytesIO()
    # Keeps the original streams if they fit into MP4, otherwise transcodes.
    video.save_to(buffer, format=Types.VideoContainer.MP4)
    return fal.upload(api_key, buffer.getvalue(), "video/mp4", "input.mp4")


def run_video(api_key, model, values, video):
    start = time.time()
    payload = {"video_url": upload_video(api_key, video), **model_payload(model, values)}
    result = fal.run(api_key, model, payload)
    content = fal.download(first_url(result, "video"))
    return io.NodeOutput(InputImpl.VideoFromFile(BytesIO(content)), format_info(api_key, model, start))


def video_schema(node_id, display_name, description, widgets):
    return io.Schema(
        node_id=node_id,
        display_name=display_name,
        category="Maybaum",
        description=description,
        inputs=[
            APIKey.Input("api_key", display_name="API Key"),
            io.Video.Input("video"),
            io.Combo.Input("model", options=[], tooltip="Live list from fal."),
            *(WIDGETS[w]() for w in widgets),
        ],
        outputs=[io.Video.Output(), io.String.Output(display_name="info")],
    )


def resize_to(image, height, width):
    if image.shape[1:3] == (height, width):
        return image
    return comfy.utils.common_upscale(image.movedim(-1, 1), width, height, "bilinear", "disabled").movedim(1, -1)


def upload_image(api_key, image):
    return fal.upload(api_key, tensor_to_bytesio(image, total_pixels=None).getvalue(), "image/png", "input.png")


class MaybaumFalImageUpscale(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MaybaumFalImageUpscale",
            display_name="fal Image Upscale",
            category="Maybaum",
            description="Image upscaling via fal. Every image of a batch is upscaled on its own. Options appear only if the model supports them.",
            inputs=[
                APIKey.Input("api_key", display_name="API Key"),
                io.Image.Input("image"),
                io.Combo.Input("model", options=[], tooltip="Live list from fal."),
                *(WIDGETS[w]() for w in ("upscale_factor", "variant", "target_resolution", "creativity", "prompt")),
            ],
            outputs=[io.Image.Output(), io.String.Output(display_name="info"), io.Mask.Output(display_name="mask")],
        )

    @classmethod
    def validate_inputs(cls, model, variant, target_resolution):
        return check_values(model, {"variant": variant, "target_resolution": target_resolution})

    @classmethod
    def execute(cls, api_key, image, model, **values):
        start = time.time()
        params = model_payload(model, values)
        images, masks = [], []
        for single in image:
            result = fal.run(api_key, model, {"image_url": upload_image(api_key, single), **params})
            upscaled = bytesio_to_image_tensor(BytesIO(fal.download(first_url(result, "image"))))
            # Mask as in LoadImage: 1 = transparent. Empty without alpha channel.
            masks.append(1.0 - upscaled[..., 3] if upscaled.shape[-1] == 4 else torch.zeros(upscaled.shape[:3]))
            images.append(upscaled[..., :3])
        return io.NodeOutput(torch.cat(images), format_info(api_key, model, start), torch.cat(masks))


INPAINT_WIDGETS = ("prompt", "negative_prompt", "strength", "seed")


class MaybaumFalImageInpaint(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MaybaumFalImageInpaint",
            display_name="fal Image Inpaint",
            category="Maybaum",
            description="Inpainting via fal: the model repaints the masked area. Every image of a batch runs on its own. Options appear only if the model supports them.",
            inputs=[
                APIKey.Input("api_key", display_name="API Key"),
                io.Image.Input("image"),
                io.Mask.Input("mask", tooltip="White (1) = repaint. Paint it in the mask editor of «Load Image»."),
                io.Combo.Input("model", options=[], tooltip="Live list from fal."),
                *(WIDGETS[w]() for w in INPAINT_WIDGETS),
                io.Boolean.Input("keep_unmasked", default=True, tooltip="Paste the result into the original only where the mask is, so everything else stays pixel-exact."),
                io.Image.Input("reference_image", optional=True, tooltip="Reference image. Only models with a reference input use it, for example Flux Kontext Inpaint."),
            ],
            outputs=[io.Image.Output(), io.String.Output(display_name="info")],
        )

    @classmethod
    def validate_inputs(cls, model):
        checked = check_values(model, {})
        if checked is not True:
            return checked
        names, required = fal.inputs(model)
        if not names & {"mask_url", "mask_image_url"}:
            return f"Model '{model}' takes no mask."
        params = fal.params(model)
        provided = {"image_url", "mask_url", "mask_image_url", "reference_image_url"} | {params[w]["name"] for w in INPAINT_WIDGETS if w in params}
        if missing := required - provided:
            return f"Model '{model}' needs {', '.join(sorted(missing))}, which this node does not provide."
        return True

    @classmethod
    def execute(cls, api_key, image, mask, model, keep_unmasked, reference_image=None, **values):
        start = time.time()
        names, _ = fal.inputs(model)
        mask_name = next(n for n in ("mask_url", "mask_image_url") if n in names)
        params = model_payload(model, values)
        if reference_image is not None and "reference_image_url" in names:
            params["reference_image_url"] = upload_image(api_key, reference_image[0])
        height, width = image.shape[1:3]
        mask = resize_to(mask.unsqueeze(-1), height, width)
        images = []
        for i, single in enumerate(image):
            single_mask = mask[min(i, len(mask) - 1)]
            payload = {"image_url": upload_image(api_key, single), mask_name: upload_image(api_key, single_mask.expand(-1, -1, 3)), **params}
            result = fal.run(api_key, model, payload)
            # Some models return another size. Back to the input size, so the mask fits and the batch stays one size.
            painted = resize_to(bytesio_to_image_tensor(BytesIO(fal.download(first_url(result, "image"))), mode="RGB"), height, width)[0]
            images.append(torch.lerp(single, painted, single_mask) if keep_unmasked else painted)
        return io.NodeOutput(torch.stack(images), format_info(api_key, model, start))


class MaybaumFalVideoUpscale(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return video_schema(
            "MaybaumFalVideoUpscale", "fal Video Upscale",
            "Video upscaling via fal. Options appear only if the model supports them.",
            ("upscale_factor", "variant", "target_resolution", "creativity", "prompt", "target_fps"),
        )

    @classmethod
    def validate_inputs(cls, model, variant, target_resolution):
        return check_values(model, {"variant": variant, "target_resolution": target_resolution})

    @classmethod
    def execute(cls, api_key, video, model, **values):
        return run_video(api_key, model, values, video)


class MaybaumFalVideoInterpolate(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return video_schema(
            "MaybaumFalVideoInterpolate", "fal Video Interpolate",
            "Frame interpolation via fal: higher frame rate or slow motion. Options appear only if the model supports them.",
            ("variant", "target_fps", "frames_between", "slowdown_factor"),
        )

    @classmethod
    def validate_inputs(cls, model, variant):
        return check_values(model, {"variant": variant})

    @classmethod
    def execute(cls, api_key, video, model, **values):
        return run_video(api_key, model, values, video)
