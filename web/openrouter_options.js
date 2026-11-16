import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

// Widgets that depend on the model. What the model cannot do is hidden and set to neutral.
// combo: values from the model, neutral "auto" · max: upper limit from the model, neutral 1
// toggle: neutral false · keep: value stays, the backend only sends it if supported
const NODES = {
    MaybaumOpenRouterImage: {
        kind: "images",
        widgets: {
            aspect_ratio: "combo",
            resolution: "combo",
            quality: "combo",
            output_format: "combo",
            seed: "keep",
            transparent_background: "toggle",
            batch: "max",
        },
        cost: ["resolution", "quality", "batch"],
    },
    MaybaumOpenRouterVideo: {
        kind: "videos",
        widgets: {
            duration: "combo",
            resolution: "combo",
            aspect_ratio: "combo",
            generate_audio: "keep",
            seed: "keep",
        },
        cost: ["duration", "resolution", "generate_audio"],
    },
};
const CACHE_MS = 10 * 60 * 1000;
const capabilities = {};

async function fetchCapabilities(kind) {
    const cached = capabilities[kind];
    if (!cached || Date.now() - cached.time > CACHE_MS) {
        const promise = api
            .fetchApi(`/maybaum/openrouter/capabilities/${kind}`)
            .then((res) => (res.ok ? res.json() : Promise.reject(res.status)))
            .catch(() => {
                delete capabilities[kind];
                return null;
            });
        capabilities[kind] = { time: Date.now(), promise };
    }
    return capabilities[kind].promise;
}

function setHidden(node, widget, hidden) {
    if (!!widget.hidden === hidden) return;
    widget.hidden = hidden;
    if (widget.options) widget.options.hidden = hidden;
    // Not node.computeSize(): it reads the remote combo's options and resets the model
    // to the first entry on first load.
    const height = (widget.computeSize?.(node.size[0])?.[1] ?? LiteGraph.NODE_WIDGET_HEIGHT) + 4;
    node.setSize([node.size[0], node.size[1] + (hidden ? -height : height)]);
}

function connected(node, test) {
    return (node.inputs ?? []).filter((i) => i.link != null && test(i.name)).length;
}

async function updateCost(node, config) {
    const model = node.widgets?.find((w) => w.name === "model")?.value;
    if (!model) return;
    const values = {
        references: connected(node, (name) => name.startsWith("reference_images.")),
        frames: connected(node, (name) => name === "first_frame" || name === "last_frame"),
    };
    for (const name of config.cost) values[name] = node.widgets.find((w) => w.name === name)?.value;
    const request = JSON.stringify({ model, values });
    node.maybaumCostRequest = request;
    const res = await api.fetchApi(`/maybaum/openrouter/estimate/${config.kind}`, { method: "POST", body: request });
    // Only the latest request counts, older responses may arrive later.
    if (node.maybaumCostRequest !== request) return;
    node.maybaumCost = res.ok ? (await res.json()).text : "";
    node.setDirtyCanvas(true, true);
}

async function syncOptions(node, config) {
    const model = node.widgets?.find((w) => w.name === "model");
    if (!model) return;
    const all = await fetchCapabilities(config.kind);
    // List not loadable: keep everything visible, the backend checks on execution.
    if (!all) return;
    const caps = all[model.value] ?? {};
    for (const [name, type] of Object.entries(config.widgets)) {
        const widget = node.widgets.find((w) => w.name === name);
        if (!widget) continue;
        const cap = caps[name];
        if (type === "combo") {
            if (cap) widget.options.values = ["auto", ...cap];
            if (!cap || !cap.includes(widget.value)) widget.value = "auto";
        } else if (type === "max") {
            if (cap) widget.options.max = cap;
            widget.value = cap ? Math.min(Math.max(widget.value, 1), cap) : 1;
        } else if (type === "toggle" && !cap) {
            widget.value = false;
        }
        for (const w of [widget, ...(widget.linkedWidgets ?? [])]) setHidden(node, w, !cap);
    }
    node.setDirtyCanvas(true, true);
    updateCost(node, config);
}

app.registerExtension({
    name: "Maybaum.OpenRouterOptions",
    nodeCreated(node) {
        const config = NODES[node.comfyClass];
        if (!config) return;
        const model = node.widgets?.find((w) => w.name === "model");
        if (!model) return;
        // The remote combo also calls callback after the list first loads.
        const callback = model.callback;
        model.callback = function (...args) {
            const result = callback?.apply(this, args);
            syncOptions(node, config);
            return result;
        };
        for (const name of config.cost) {
            const widget = node.widgets.find((w) => w.name === name);
            if (!widget) continue;
            const widgetCallback = widget.callback;
            widget.callback = function (...args) {
                const result = widgetCallback?.apply(this, args);
                updateCost(node, config);
                return result;
            };
        }
        const onConnectionsChange = node.onConnectionsChange;
        node.onConnectionsChange = function (...args) {
            const result = onConnectionsChange?.apply(this, args);
            updateCost(node, config);
            return result;
        };
        node.badges.push(() => new LGraphBadge({ text: node.maybaumCost || "", bgColor: "#35553a", fgColor: "#ffffff" }));
        const onConfigure = node.onConfigure;
        node.onConfigure = function (...args) {
            const result = onConfigure?.apply(this, args);
            syncOptions(node, config);
            return result;
        };
        syncOptions(node, config);
    },
});
