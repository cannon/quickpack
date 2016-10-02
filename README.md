# QuickPack
Utility for quickly and conveniently packing model, material, texture, and sound dependencies in Half-Life 2 BSP maps.

**Automatically packs materials used in custom models**, unlike Pakrat. Furthermore, it only packs used materials for models with multiple skins!

To use:  
* Install Python 3 from https://www.python.org/downloads/  
* Run QuickPack.py from a command prompt, with the full path to your map as the only argument. Example:  
`QuickPack.py "C:\Program Files (x86)\Steam\steamapps\common\Half-Life 2\hl2\maps\mymap.bsp"`

Your map must be located in the (game root)/maps folder. This program only runs on windows (as it uses bspzip.exe)

**New feature: File whitelists and blacklists:**
* To force the program to pack specific files and their dependencies, make a `mapname.pack.txt` file in your maps folder with one filename on each line. Filenames should be relative to the game root, for example: `materials/specialtexture.vmt`
* To force the program not to pack specific files and their dependencies, make a `mapname.nopack.txt` file in the maps folder.

If you experience any problems, or would like features to be added, please start an issue!
