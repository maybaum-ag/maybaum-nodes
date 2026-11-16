# Maybaum Custom Nodes

Bild- und Videogenerierung über OpenRouter mit Keys pro Kunde. Ein Kunde kann zusätzlich einen fal-Key haben.

## Installation

1. ZIP in den Ordner `ComfyUI/custom_nodes/` entpacken. Danach existiert `ComfyUI/custom_nodes/maybaum_nodes/`.
2. ComfyUI neu starten.
3. Prüfen: Im Node-Menü gibt es die Kategorie «Maybaum».

Getestet mit ComfyUI v0.39.0. Zusätzliche Python-Pakete sind nicht nötig.

## Nodes

- **API Key** · Wählt den Kunden. Ausgang an Bild- und Video-Node anschliessen.
- **OpenRouter Image** · Bildgenerierung. Referenzbilder: Neue Eingänge erscheinen automatisch, jeder nimmt auch einen ganzen Batch. Bei transparentem Hintergrund liegt die Transparenz am Ausgang `mask`.
- **OpenRouter Video** · Videogenerierung, optional mit Start- und Endbild und einem Referenzvideo. Das Referenzvideo verwenden nur Modelle, die Video-Referenzen kennen. Ausgang an «Save Video».

Der Ausgang `info` zeigt Kunde, Modell, Dauer und Kosten.

Oben rechts auf der Image- und Video-Node stehen die geschätzten Kosten pro Run. Die Schätzung rechnet mit Modell, Auflösung, Qualität, Batch, Dauer, Audio und angeschlossenen Bildern. Die Preise kommen von OpenRouter. Rechnet ein Modell nach Tokens ab, steht dort «Token pricing, cost known after run». Massgebend sind die effektiven Kosten am Ausgang `info`.

Optionen wie Seitenverhältnis, Auflösung, Dauer, Batch, Seed, Audio oder Transparenz erscheinen nur, wenn das gewählte Modell sie unterstützt. Dropdowns zeigen nur die Werte des Modells. «auto» heisst: Standard des Modells. Modellliste und Optionen kommen von OpenRouter und werden alle 10 Minuten neu geladen.

## Keys

1. Keys des Kunden im Keeper kopieren.
2. Auf der Node «API Key» «Manage keys» klicken, einen Alias eingeben (z. B. `client-a`) und den OpenRouter-Key, den fal-Key oder beide einfügen.
3. «Verify and save». Jeder Key wird beim Anbieter geprüft. Ist einer ungültig, wird nichts gespeichert.
4. Kunden im Dropdown der Node «API Key» wählen.

Zweiten Key später ergänzen: In der Liste auf den Alias klicken, nur das fehlende Feld ausfüllen, speichern. Ein leeres Feld lässt den geladenen Key unverändert.

Fehlt für den Kunden der Key des Anbieters, den eine Node braucht, bricht der Run mit einer Meldung ab.

Keys bleiben nur im Arbeitsspeicher von ComfyUI. Nach jedem Neustart neu einfügen. Im Workflow und in den Bild-Metadaten steht nur der Alias.

Keys nie in ein Textfeld einer Node schreiben. Was in einem Node-Feld steht, landet in jedem gespeicherten Bild.
