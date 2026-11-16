# Maybaum Custom Nodes

ComfyUI-Nodes für Bild- und Videogenerierung über OpenRouter sowie Upscaling und Frame-Interpolation über fal.

Die Nodes nutzen kostenpflichtige Cloud-Dienste. Es braucht ein eigenes Konto mit API-Key bei OpenRouter, fal oder beiden.

## Installation

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/maybaum-ag/maybaum-nodes.git
```

ComfyUI neu starten. Die Nodes erscheinen in der Kategorie «Maybaum». Getestet mit ComfyUI v0.42.5.

## API-Keys

1. Key erstellen bei [OpenRouter](https://openrouter.ai/settings/keys) oder [fal](https://fal.ai/dashboard/keys).
2. Node «API Key» einfügen, «Manage keys» klicken.
3. Alias wählen (z. B. `projekt-a`), Key einfügen, «Verify and save».
4. Ausgang «API Key» an die anderen Nodes anschliessen.

Keys bleiben nur im Arbeitsspeicher und müssen nach jedem Neustart neu eingefügt werden. Im Workflow steht nur der Alias. Keys nie in ein Textfeld einer Node schreiben.

## Nodes

- **API Key** · Wählt den Alias.
- **OpenRouter Image** · Bildgenerierung, optional mit Referenzbildern.
- **OpenRouter Video** · Videogenerierung, optional mit Start-, Endbild und Referenzen.
- **fal Image Upscale** · Vergrössert Bilder.
- **fal Video Upscale** · Vergrössert Videos.
- **fal Video Interpolate** · Höhere Bildrate oder Slow-Motion.

Jede Node zeigt nur die Optionen, die das gewählte Modell unterstützt. «auto» bedeutet: Standard des Modells. Oben rechts stehen die geschätzten Kosten, der Ausgang `info` zeigt die Details zum Run.

## Datenschutz

Eingaben gehen an OpenRouter, fal und die jeweiligen Modellanbieter. Vertrauliche oder personenbezogene Inhalte nur verarbeiten, wenn das zulässig ist.

## Lizenz

GPL-3.0, wie ComfyUI. Siehe [LICENSE](LICENSE).
