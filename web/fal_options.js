import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

// Node -> fal task. The backend maps each widget to a model parameter, see PARAMS in fal.py.
const NODES = {
    MaybaumFalImageUpscale: "image_upscale",
    MaybaumFalVideoUpscale: "video_upscale",
    MaybaumFalVideoInterpolate: "video_interpolate",
    MaybaumFalImageInpaint: "image_inpaint",
};
const WIDGETS = ["upscale_factor", "variant", "target_resolution", "creativity", "prompt", "negative_prompt", "strength", "seed", "target_fps", "frames_between", "slowdown_factor"];
const COMBOS = ["variant", "target_resolution"];
const CACHE_MS = 10 * 60 * 1000;
const cache = {};

function cached(url) {
    const entry = cache[url];
    if (!entry || Date.now() - entry.time > CACHE_MS) {
        const promise = api
            .fetchApi(url)
            .then((res) => (res.ok ? res.json() : Promise.reject(res.status)))
            .catch(() => {
                delete cache[url];
                return null;
            });
        cache[url] = { time: Date.now(), promise };
    }
    return cache[url].promise;
}

function setHidden(node, widget, hidden) {
    if (!!widget.hidden === hidden) return;
    widget.hidden = hidden;
    if (widget.options) widget.options.hidden = hidden;
    const height = (widget.computeSize?.(node.size[0])?.[1] ?? LiteGraph.NODE_WIDGET_HEIGHT) + 4;
    node.setSize([node.size[0], node.size[1] + (hidden ? -height : height)]);
}

function applyParam(widget, param, defaults) {
    if (COMBOS.includes(widget.name)) {
        widget.options.values = param.required ? param.enum : ["auto", ...param.enum];
        if (defaults) widget.value = param.default != null ? String(param.default) : widget.options.values[0];
        if (!widget.options.values.includes(widget.value)) widget.value = widget.options.values[0];
        return;
    }
    if (widget.name === "prompt" || widget.name === "negative_prompt") return;
    // target_fps keeps 0 as "model default".
    if (param.min != null && widget.name !== "target_fps") widget.options.min = param.min;
    if (param.max != null) widget.options.max = param.max;
    if (param.type === "integer") widget.options.round = 1;
    if (defaults) widget.value = param.default ?? (widget.name === "target_fps" ? 0 : widget.value);
    if (widget.name === "target_fps" && widget.value === 0) return;
    widget.value = Math.min(Math.max(widget.value, widget.options.min ?? -Infinity), widget.options.max ?? Infinity);
}

async function syncOptions(node, task, defaults) {
    const model = node.widgets?.find((w) => w.name === "model");
    if (!model) return;
    const models = await cached(`/maybaum/fal/models/${task}`);
    if (models?.length) {
        model.options.values = models;
        if (!models.includes(model.value)) {
            model.value = models[0];
            defaults = true;
        }
    }
    if (!model.value) return;
    const request = model.value;
    node.maybaumModel = request;
    const params = await cached(`/maybaum/fal/params?model=${encodeURIComponent(request)}`);
    // Only the latest model counts, older responses may arrive later.
    if (node.maybaumModel !== request) return;
    // Parameters not loadable: keep everything visible, the backend checks on execution.
    if (!params) return;
    for (const name of WIDGETS) {
        const widget = node.widgets.find((w) => w.name === name);
        if (!widget) continue;
        const param = params[name];
        if (param) applyParam(widget, param, defaults && !node.maybaumLoaded);
        setHidden(node, widget, !param);
    }
    const price = await cached(`/maybaum/fal/price?model=${encodeURIComponent(request)}`);
    node.maybaumCost = price?.text ?? "";
    node.setDirtyCanvas(true, true);
}

app.registerExtension({
    name: "Maybaum.FalOptions",
    nodeCreated(node) {
        const task = NODES[node.comfyClass];
        if (!task) return;
        const model = node.widgets?.find((w) => w.name === "model");
        if (!model) return;
        const callback = model.callback;
        model.callback = function (...args) {
            const result = callback?.apply(this, args);
            node.maybaumLoaded = false;
            syncOptions(node, task, true);
            return result;
        };
        node.badges.push(() => new LGraphBadge({ text: node.maybaumCost || "", bgColor: "#35553a", fgColor: "#ffffff" }));
        const onConfigure = node.onConfigure;
        node.onConfigure = function (...args) {
            const result = onConfigure?.apply(this, args);
            // Loaded from a workflow: keep the saved values.
            node.maybaumLoaded = true;
            syncOptions(node, task, false);
            return result;
        };
        syncOptions(node, task, true);
    },
});
