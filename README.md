# Maybaum Custom Nodes

Custom Nodes für ComfyUI: Bild- und Videogenerierung über OpenRouter, Upscaling und Frame-Interpolation über fal.

Die Nodes nutzen kostenpflichtige Cloud-Dienste. Dafür braucht es ein eigenes Konto mit API-Key bei OpenRouter, bei fal oder bei beiden. Die Kosten werden über dieses Konto abgerechnet.

## Installation

Mit git:

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/maybaum-ag/maybaum-nodes.git
```

Oder als ZIP: Das Archiv in den Ordner `ComfyUI/custom_nodes/` entpacken.

Danach ComfyUI neu starten. Im Node-Menü erscheint die Kategorie «Maybaum».

Getestet mit ComfyUI v0.42.5. Zusätzliche Python-Pakete sind nicht nötig.

## API-Keys

1. API-Key beim Anbieter erstellen: OpenRouter unter [openrouter.ai/settings/keys](https://openrouter.ai/settings/keys), fal unter [fal.ai/dashboard/keys](https://fal.ai/dashboard/keys).
2. Node «API Key» einfügen und «Manage keys» klicken.
3. Einen Alias eingeben, z. B. `projekt-a`, und den OpenRouter-Key, den fal-Key oder beide einfügen. Der Alias ist ein frei wählbarer Name, z. B. pro Projekt oder Konto.
4. «Verify and save». Jeder Key wird beim Anbieter geprüft. Ist einer ungültig, wird nichts gespeichert.
5. Alias im Dropdown der Node «API Key» wählen und den Ausgang an die anderen Maybaum-Nodes anschliessen.

Einen zweiten Key später ergänzen: In der Liste auf den Alias klicken, nur das fehlende Feld ausfüllen und speichern. Ein leeres Feld lässt den bereits geladenen Key unverändert.

Fehlt für einen Alias der Key, den eine Node braucht, bricht der Run mit einer Meldung ab.

Keys bleiben nur im Arbeitsspeicher von ComfyUI und müssen nach jedem Neustart neu eingefügt werden. Im Workflow und in den Metadaten gespeicherter Bilder steht nur der Alias.

API-Keys wie Passwörter behandeln: nie in ein Textfeld einer Node schreiben, nicht in Workflows, Screenshots oder Chats weitergeben. Was in einem Node-Feld steht, landet in jedem gespeicherten Bild.

## Nodes

- **API Key** · Wählt den Alias und damit die Keys für die anderen Nodes.
- **OpenRouter Image** · Bildgenerierung. Für Referenzbilder erscheinen neue Eingänge automatisch, jeder nimmt auch einen ganzen Batch. Bei transparentem Hintergrund liegt die Transparenz am Ausgang `mask`.
- **OpenRouter Video** · Videogenerierung, optional mit Start- und Endbild und einem Referenzvideo. Das Referenzvideo verwenden nur Modelle, die Video-Referenzen unterstützen. Ausgang an «Save Video».
- **fal Image Upscale** · Vergrössert Bilder. Jedes Bild eines Batches wird einzeln verarbeitet. Transparenz liegt am Ausgang `mask`.
- **fal Video Upscale** · Vergrössert ein Video.
- **fal Video Interpolate** · Höhere Bildrate oder Slow-Motion, z. B. mit Topaz, RIFE oder FILM.

Der Ausgang `info` zeigt Alias, Modell, Dauer und Kosten. Bei fal steht dort der Preis pro Einheit, da fal keine effektiven Kosten pro Run zurückgibt.

### OpenRouter

Oben rechts auf der Image- und Video-Node stehen die geschätzten Kosten pro Run. Die Schätzung berücksichtigt Modell, Auflösung, Qualität, Batch, Dauer, Audio und angeschlossene Bilder. Die Preise kommen von OpenRouter. Rechnet ein Modell nach Tokens ab, steht dort «Token pricing, cost known after run». Massgebend sind die effektiven Kosten am Ausgang `info`.

Optionen wie Seitenverhältnis, Auflösung, Dauer, Batch, Seed, Audio oder Transparenz erscheinen nur, wenn das gewählte Modell sie unterstützt. Dropdowns zeigen nur die Werte des Modells. «auto» bedeutet: Standard des Modells.

### fal

Jedes fal-Modell hat eigene Parameter. Die Node zeigt nur die Felder, die das gewählte Modell kennt, mit dessen Grenzen und Standardwerten: `upscale_factor`, `variant` (z. B. Topaz-Modell), `target_resolution`, `creativity`, `prompt`, `target_fps`, `frames_between`, `slowdown_factor`. Alle übrigen Parameter laufen mit dem Standard des Modells. `target_fps` 0 bedeutet: Standard des Modells.

Oben rechts steht der Preis pro Einheit. Er erscheint, sobald ein fal-Key geladen ist.

fal begrenzt Abfragen ohne Key stark. Laden Modellliste oder Optionen nicht, kurz warten und die Node neu anlegen.

### Modelllisten

Modelllisten und Optionen kommen live von den Anbietern und werden bis zu 10 Minuten zwischengespeichert. Neue Modelle erscheinen nach dem Neuladen der Seite oder beim Anlegen einer neuen Node. Ein Neustart von ComfyUI lädt sie sofort.

## Datenschutz

Eingaben gehen an OpenRouter, an fal und an die Modellanbieter dahinter. Bei fal werden Eingaben und Resultate auf dem CDN von fal unter öffentlichen, nicht erratbaren Links abgelegt. Die Nodes verlangen bei fal eine Löschung nach einer Stunde. Ob fal das einhält, ist nicht geprüft.

Vor der Verarbeitung vertraulicher oder personenbezogener Inhalte klären, ob das zulässig ist.
