import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const STYLE = `
.maybaum-keys-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.5); z-index: 10000; display: flex; align-items: center; justify-content: center; }
.maybaum-keys { background: var(--comfy-menu-bg); color: var(--fg-color); border: 1px solid var(--border-color); border-radius: 8px; padding: 16px; width: min(440px, calc(100vw - 32px)); font-size: 14px; display: flex; flex-direction: column; gap: 10px; }
.maybaum-keys h3 { margin: 0; font-size: 16px; }
.maybaum-keys p { margin: 0; opacity: 0.7; font-size: 12px; }
.maybaum-keys input { background: var(--comfy-input-bg); color: var(--input-text); border: 1px solid var(--border-color); border-radius: 4px; padding: 6px 8px; }
.maybaum-keys button { background: var(--comfy-input-bg); color: var(--input-text); border: 1px solid var(--border-color); border-radius: 4px; padding: 6px 10px; cursor: pointer; }
.maybaum-keys .row { display: flex; gap: 8px; align-items: center; justify-content: space-between; }
.maybaum-keys .status { min-height: 1.2em; font-size: 12px; }
`;

async function refreshAliases() {
    const res = await api.fetchApi("/maybaum/keys/aliases");
    const aliases = await res.json();
    for (const node of app.graph.nodes) {
        if (node.comfyClass !== "MaybaumAPIKey") continue;
        const widget = node.widgets?.find((w) => w.name === "alias");
        if (!widget) continue;
        widget.options.values = aliases;
        if (!widget.value && aliases.length) widget.value = aliases[0];
        node.setDirtyCanvas(true, true);
    }
}

async function fetchKeys() {
    const res = await api.fetchApi("/maybaum/keys");
    return await res.json();
}

function openDialog(node) {
    if (!document.getElementById("maybaum-keys-style")) {
        const style = document.createElement("style");
        style.id = "maybaum-keys-style";
        style.textContent = STYLE;
        document.head.appendChild(style);
    }

    const overlay = document.createElement("div");
    overlay.className = "maybaum-keys-overlay";
    overlay.innerHTML = `
        <div class="maybaum-keys">
            <h3>API keys</h3>
            <p>One alias per client, with an OpenRouter key, a fal key or both. Keys stay in ComfyUI's memory only. Add them again after a restart.</p>
            <div class="list"></div>
            <input class="alias" placeholder="Alias, e.g. client-a" autocomplete="off">
            <input class="key" name="openrouter" type="password" placeholder="OpenRouter key from Keeper" autocomplete="off">
            <input class="key" name="fal" type="password" placeholder="fal key from Keeper" autocomplete="off">
            <p>Leave a field empty to keep the key already loaded for this alias.</p>
            <div class="row">
                <button class="save">Verify and save</button>
                <button class="close">Close</button>
            </div>
            <div class="status"></div>
        </div>`;
    document.body.appendChild(overlay);

    const list = overlay.querySelector(".list");
    const aliasInput = overlay.querySelector(".alias");
    const keyInputs = [...overlay.querySelectorAll(".key")];
    const clearKeys = () => keyInputs.forEach((input) => (input.value = ""));
    const status = overlay.querySelector(".status");

    const close = () => {
        clearKeys();
        overlay.remove();
        document.removeEventListener("keydown", onKey);
    };
    const onKey = (e) => {
        if (e.key === "Escape") close();
    };
    document.addEventListener("keydown", onKey);
    overlay.addEventListener("click", (e) => {
        if (e.target === overlay) close();
    });
    overlay.querySelector(".close").addEventListener("click", close);

    const renderList = (loaded) => {
        list.replaceChildren();
        const aliases = Object.keys(loaded);
        if (!aliases.length) {
            list.textContent = "No keys loaded yet.";
            return;
        }
        for (const alias of aliases) {
            const row = document.createElement("div");
            row.className = "row";
            const name = document.createElement("span");
            name.textContent = `${alias} · ${loaded[alias].join(", ")}`;
            name.title = "Click to add or replace a key for this alias";
            name.style.cursor = "pointer";
            name.addEventListener("click", () => {
                aliasInput.value = alias;
                keyInputs[0].focus();
            });
            const remove = document.createElement("button");
            remove.textContent = "Remove";
            remove.addEventListener("click", async () => {
                const res = await api.fetchApi(`/maybaum/keys/${encodeURIComponent(alias)}`, { method: "DELETE" });
                renderList(await res.json());
                refreshAliases();
            });
            row.append(name, remove);
            list.appendChild(row);
        }
    };

    overlay.querySelector(".save").addEventListener("click", async () => {
        status.textContent = "Verifying keys ...";
        const body = { alias: aliasInput.value };
        for (const input of keyInputs) body[input.name] = input.value;
        const res = await api.fetchApi("/maybaum/keys", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        });
        const data = await res.json();
        if (!res.ok) {
            status.textContent = data.error;
            return;
        }
        clearKeys();
        aliasInput.value = "";
        const parts = [`${data.alias} saved: ${data.providers.join(", ")}`];
        if (data.label) parts.push(`Label: ${data.label}`);
        if (data.usage != null) parts.push(`Usage: $${data.usage}`);
        if (data.limit_remaining != null) parts.push(`Remaining: $${data.limit_remaining}`);
        status.textContent = parts.join(" · ");
        await refreshAliases();
        const widget = node.widgets?.find((w) => w.name === "alias");
        if (widget) {
            widget.value = data.alias;
            node.setDirtyCanvas(true, true);
        }
        renderList(await fetchKeys());
    });

    fetchKeys().then(renderList);
    aliasInput.focus();
}

app.registerExtension({
    name: "Maybaum.Keys",
    nodeCreated(node) {
        if (node.comfyClass !== "MaybaumAPIKey") return;
        const button = node.addWidget("button", "Manage keys", null, () => openDialog(node), { serialize: false });
        button.serialize = false;
        refreshAliases();
    },
});
