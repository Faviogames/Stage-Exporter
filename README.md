# WRC to ACR Stage Exporter

**Stage Exporter 1.6.4** is a Windows add-on that extends Sando Rally Stage Export Tool 0.3.7. It allows you to export stages from WRC Generations to Assetto Corsa Rally, choose which stages to include in the pack, and reuse previously built stages.

## Requirements

- Sando Rally Stage Export Tool **0.3.7**, installed separately.
- WRC Generations and Assetto Corsa Rally installed locally.
- Assetto Corsa Rally closed while installing or updating the pack.

## Installation

Download [Stage-Exporter-v1.6.4-Instalar.zip](https://github.com/Faviogames/Stage-Exporter/releases/download/v1.6.4/Stage-Exporter-v1.6.4-Instalar.zip). Extract its contents directly into your Sando folder: `payload/`, `INSTALAR.bat`, and the guides must sit at the root level of that folder, without an extra wrapper folder.

Run `INSTALAR.bat` inside the Sando folder. If the installer does not detect the path automatically, select the folder containing `_internal\wrcg2acr-worker.exe`. Once finished, the installer generates **WRC to ACR Stage Exporter.exe** inside the Sando folder. Launch that executable.

In the **Stage Exporter** window, select a stage and click **Exportar tramo** (*Export Stage*). Use **Actualizar pack** (*Update Pack*) to install the checked or imported stages. The pack is saved to `acr/Content/Paks/~mods`, and exported stages appear in-game under `[MOD] <country>`.

This repository contains the add-on's source code and configuration files. The Sando core and game assets are loaded from your local installations. Stage compatibility depends on the inventory included in this release.

See [README_INSTALLER.txt](README_INSTALLER.txt) for more details.

## Updates

Latest version support auto update when launch (normally)
ACR 0.37 ready!
a bunch of fixes and a lot of hours i dont even remember.


# WARNING
The more stages you generate the bigger grows the .work folder on your drive make sure you have a lot of space for it! (30gb at least) and even more if you want to generate all the stages!
the final .pak files that goes into ACR is way less size! Deleting everything from the project or .work folder means you wont be able to generate the maps faster if you have the .stage files is different you can save a lot of time, so make sure to upload those ones to the cloud! or even better share to the comunity on Overtake!
