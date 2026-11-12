# Maybaum Custom Nodes

Bild- und Videogenerierung über OpenRouter mit einem Key pro Kunde.

## Installation

1. ZIP in den Ordner `ComfyUI/custom_nodes/` entpacken. Danach existiert `ComfyUI/custom_nodes/maybaum_nodes/`.
2. ComfyUI neu starten.
3. Prüfen: Im Node-Menü gibt es die Kategorie «Maybaum».

Getestet mit ComfyUI v0.39.0. Zusätzliche Python-Pakete sind nicht nötig.

## Nodes

- **OpenRouter API** · Wählt den Kunden-Key. Ausgang an Bild- und Video-Node anschliessen.
- **OpenRouter Image** · Bildgenerierung. Referenzbilder: Neue Eingänge erscheinen automatisch, jeder nimmt auch einen ganzen Batch. Bei transparentem Hintergrund liegt die Transparenz am Ausgang `mask`.
- **OpenRouter Video** · Videogenerierung, optional mit Start- und Endbild. Ausgang an «Save Video».

Der Ausgang `info` zeigt Kunde, Modell, Dauer und Kosten.

Optionen wie Seitenverhältnis, Auflösung, Dauer, Batch, Seed, Audio oder Transparenz erscheinen nur, wenn das gewählte Modell sie unterstützt. Dropdowns zeigen nur die Werte des Modells. «auto» heisst: Standard des Modells. Modellliste und Optionen kommen von OpenRouter und werden alle 10 Minuten neu geladen.

## Keys

1. Key des Kunden im Keeper kopieren.
2. Auf der Node «OpenRouter API» «Keys verwalten» klicken, einen Alias eingeben (z. B. `kunde-a`) und den Key einfügen.
3. «Prüfen und speichern». Ein ungültiger Key wird abgelehnt.
4. Kunden im Dropdown der Node «OpenRouter API» wählen.

Keys bleiben nur im Arbeitsspeicher von ComfyUI. Nach jedem Neustart neu einfügen. Im Workflow und in den Bild-Metadaten steht nur der Alias.

Keys nie in ein Textfeld einer Node schreiben. Was in einem Node-Feld steht, landet in jedem gespeicherten Bild.
