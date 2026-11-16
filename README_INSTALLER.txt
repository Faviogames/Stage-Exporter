Stage Exporter - Enhancements for Sando Rally's Stage Export Tool
==============================================================

You must have the Sando Rally application downloaded and remove any other mods from the 'Paks' directory of your Assetto Corsa Rally installation.

What it does
This adds several enhancements to a copy of the Stage Export Tool (v0.3.7), including: dense vegetation (along roadsides, around rocks, in meadows, and in distant forests); crowds and people seated at tables; finish lines and stop controls; replay cameras; illuminated streetlights; skid marks; snow effects for Sweden; corrected LOD (Level of Detail) and building models; seamless roads; a starting area with a marshal present; ACR-style finish and "STOP" signs; collision-enabled tall posts and tire stacks; thin cables; power pylons and ground-level fencing; tunnels with asphalt surfaces; intersections with correctly oriented textures; properly oriented cars in the service park; performance optimizations; and the ability to export individual stages (reusing the rest of the pack). 
Full details can be found in `custom\LEEME.txt` (README.txt) after installation.

Stage Exporter window (new)
Short step-by-step guide, with how to import a stage: QUICK_GUIDE.txt
- Tick the stages you want in the "STATUS" column (built or imported stages can be ticked) and press "Update pack": one pack with exactly the ticked stages is built and installed. Built stages are kept, so ticking or unticking never exports again.
- "Save as .stage" packs a built stage into one file (about 2-3 GB) that you can share, with its names, images and its country's description, logo and background; "Import stage" adds a .stage file from someone else to your tool (the country's description and images only fill what you have empty). Then tick it and press "Update pack". Never keep two stage packs in the Paks folder: they replace each other's menus.
- To import a .stage you need: this Stage Exporter version, WRC Generations and Assetto Corsa Rally installed in the versions below. Only import files from people you trust: they hold data the tool loads when it builds the pack.
- "Logo and description" edits the country's logo, background and description; "Name and images" the stage's names and pictures (a reverse stage opens with the images of its forward stage). They apply with "Update pack", no export needed.
- English / Spanish: the "English" / "Español" button (restart to apply).
- The terrain bake now limits its worker processes to your free memory (set WR_BAKE_WORKERS=<n> to force a number).
- Locations are named "[MOD] <Country>".

Available Stages
The included inventory has 25 stage variants across Belgium, Corsica, Germany, Greece, Italy, Kenya, Mexico, Portugal, Spain, and Sweden. See payload/custom/data/allowed_stages.json for the exact list. In-game verification varies by stage.

How to Install
1. Copy this folder into the Stage Export Tool directory (alongside `Sando-Rally-Stage-Export-Tool.exe`). 
2. Double-click `INSTALAR.bat`. 
- The script will attempt to locate WRC Generations and Assetto Corsa Rally on Steam (if it cannot find them, it will prompt you to specify the folders). - Using your own ACR installation, prepare the data for the finish line, streetlights, skid marks, and grass color.
- Create "WRC to ACR Stage Exporter.exe".
3. With Assetto Corsa Rally CLOSED, open "WRC to ACR Stage Exporter.exe" and export the stages.
4. Launch the game once the export is complete (the game only loads the stages upon startup). They will appear under the "[MOD] Spain" location (one per country).

Troubleshooting
If you do not see the stages in the game and have another stage mod installed (e.g., Bio Bio), note that both mods modify the same game stage list, meaning only one will be visible. Try removing the other mod from the "Paks" folder (without deleting it).

Notes
- No game files are included; everything is generated from your own installations.
- The enhancements rely on functions from version 0.3.7 of the tool; they may not work with other versions.