# mods/

Your Fire Emblem Fates mods live here, one folder per mod:

```
mods/MyMod/
  mod.json                          name, description, on/off, order, override
  text/m/@E/GameData.bin.lz.txt     names and other game text, as a text file (works today)
  romfs/face/...                    whole replacement files, installed as they are (works today)
  tables/Person.csv ...             spreadsheets (once config/tables/ has the Fates layouts)
```

They are made from your own game's data, so git ignores everything in this folder except
this README.

```bash
python tools/mods/mods.py example-text                        # demo: Ryoma's name shows as "Ryouma"
python tools/mods/mods.py new MyText --text m/@E/GameData.bin.lz   # a text mod to edit
python tools/mods/mods.py archives                            # where all the game text is
python tools/mods/mods.py install                             # check, build, copy into Zakuro
python tools/mods/mods.py uninstall                           # back to the original game
```

How it works, what you can edit and how sure we are of each part: docs/MODDING.md.
