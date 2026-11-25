# Changelog

All notable changes to Spool Inventory, newest first. The version number is the one in `manifest.json`.
Updating never needs anything beyond copying the folder over and restarting Home Assistant
(plus Ctrl+F5 in the browser for panel changes).

## 1.1.0 - Price calculator

- New **Price** tab: what a print costs and what to ask for it. Filament cost comes from the spools you already have
  (price and weight of the spool), plus electricity, machine wear, preparation and post-processing time, extras and a
  failure allowance. It shows a suggested price (a markup that gets smaller above a limit you choose) and a fixed-markup
  price, and your profit once you type the price you ask.
- Up to four filaments per quote, up to 10 machines, up to 500 saved quotes (with customer, description and status
  draft / sent / paid). Open a saved quote to change it.
- **New layout**: *Filament*, *Printer* and *Price* are now three buttons in the blue bar at the top. Under *Filament* you
  still have Spools, By color, By location, Archive and History with the same filters. The summary cards only show
  under *Filament*, and *Add spool* only appears there too.
- **Row buttons everywhere**: the buttons of a spool (loaded in printer, reorder, bought another, weigh, use filament and
  the ⋯ menu with edit, history, duplicate, archive, delete) now also show in the *By location* view and in the spools
  listed under a color in *By color*, not only in the main list.
- Rates and machines are yours to set; they start empty (zero), so no one's prices are built in.
- Included in backups, and restored or merged like the rest of the data. Nothing about the stored spools changes.

## 1.0.2 - No alarm at the start of a USB print

- When the printer does not give out the file while it prints (seen with prints started from the USB stick), there is
  no longer a notification at the start of the print. The file is read again when the print ends, and a notification is
  only shown if that fails too. Multi-material prints are still announced at the start.

## 1.0.1 - Prints started from the USB stick

- A print started from a file on the printer's USB stick reports only the folder (`/usb`) and the file's short name,
  and gives no filament numbers while it runs. The file is now also looked up under the folder and the name joined
  together (and through the printer's file information).
- On the Core One+ the file cannot be read while it is being printed, only afterwards. The grams were read when the print
  ended and subtracted correctly. The notification at the start of such a print said "nothing will be subtracted", which
  was misleading: it now says the file is looked at once more when the print ends. If that fails too, you always get a
  message that says nothing was subtracted and points to "Used in printer".
- Automatic subtraction is still in beta.

## 1.0.0 - First stable release

The first release that is no longer a pre-release. Nothing changes in the stored data and nothing needs to be set
up again: copy the folder over and restart Home Assistant (plus Ctrl+F5 in the browser for the panel).

What the stable part covers: the inventory (spools, weigh sessions, low and empty alerts, reorder list, locations,
archive, history with undo, backups), the catalog of about 150 brands, **What fits?**, the **By color** and
**By location** views, the printer tab (maintenance, parts, shopping list), and the option to clear the
loaded spool when the printer is unloaded.

**Automatic subtraction stays in beta.** It works on the Core One+ it was tested on, but it has only seen a few
weeks of real prints and one printer. It is still off by default, and the plan is to take the beta label off once
it has had more testing. Weigh your spools now and then.

- No code changes compared to 0.11.3, apart from the version number.

## 0.11.3 - Unload clearing and everything since 0.9.2

Everything new since 0.9.2, in short:

- **What fits?**: type the grams a print needs and see which spools have enough, by material and color family.
- **By color** tab: one row per color family, tap to see every spool of that color whatever the material.
- **Automatic subtraction (beta, off by default)**: with a PrusaLink printer in Home Assistant, the filament of a print is subtracted from the loaded spool by itself (full on finish, a share on cancel). Tested on a Core One+.
- **Unload clears the loaded spool (optional, off by default)**, described below.
- Issue forms for bug reports and ideas, and a "Printers and limits" section in the README.

Details of this version:

- New optional setting **Clear "loaded in printer" when the printer reports no filament** (off by default, shown when the PrusaLink integration is set up). When the printer's Material sensor changes from a material to `---` (you unloaded the filament), no spool is marked as loaded any more, and the history shows "Unloaded from printer". Nothing is ever marked as loaded automatically: you pick the spool when you load filament.
- It ignores "unavailable" (printer switched off, Home Assistant restarting) and anything while a print is running or paused, so a filament runout in the middle of a print does not clear the spool.

## 0.11.2 - Retries at the start of a print

- Automatic subtraction no longer gives up at the very start of a print. Right after a print begins, the printer may not yet report the file or its filament numbers, so it now tries again after 10, 20, 40, 60 and 120 seconds while the print runs. A notification is only shown when all of those tries failed, and it says why. A last look at the file is also taken when the print ends.

## 0.11.1 - Version in notifications

- Notifications about automatic subtraction now end with the installed version, so it is clear which copy is running.

## 0.11.0 - Automatic subtraction (beta)

- New optional setting **Automatic subtraction (beta)**, off by default. It only appears when the official PrusaLink
  integration is set up in Home Assistant, and it uses that printer, so nothing needs to be configured twice.
- When a print starts, the filament estimate (grams) is read once from the print file (G-code or binary G-code). When
  the printer reports the print as finished, it is subtracted from the spool marked as loaded. If the print is cancelled
  or fails, the estimate scaled by the progress reached is subtracted.
- The spool that was loaded when the print started is the one that is charged (if none was, the one loaded at the end).
  Exactly one spool must be marked as loaded; otherwise you get a notification and nothing is changed.
- Each print is subtracted only once, even across restarts of Home Assistant. A notification tells you when the file
  could not be read.
- If the printer already reports the filament numbers with the job, those are used and nothing is downloaded. Otherwise the file is read from the printer and several addresses are tried (the notification lists them if none works).
- When no filament numbers can be found, the notification says what was found at each address (for example "not found", "file information without numbers") so the cause can be seen. "Total filament used" lines are accepted too.
- The file is read by Spool Inventory itself (text .gcode and binary .bgcode), so it works with whatever PrusaLink library your Home Assistant ships. A .bgcode is only read as far as its header; a .gcode is streamed, never loaded whole into memory. Multi-material files are recognised and skipped, not guessed.
- Entries appear in the history as "auto: file, X g, estimate" and can be undone with "Set back to".
- This is an estimate from the slicer: weigh the spool now and then. Only single-material prints are supported.
- The **By color** tab now has one row per color family (Black, Green, ...) instead of one row per material and color. Tap a row to see every spool of that color, whatever the material, with its remaining filament. The row shows the total and how much of each material.
- New stored data: the print being followed and the last prints already subtracted. Older versions ignore it.

## 0.10.0 - What fits?

- New **What fits?** button in the toolbar. Choose a material, optionally a color, and type the grams a print needs
  (your slicer shows it). It lists the spools with enough filament left: the one in the printer first, then the
  ones with the least left over. A spool that would end with only a few grams to spare is marked "tight", because the
  slicer's number is an estimate. Spools that are too small are listed below.
- Colors are grouped into broad families (Black, White, Grey, Red, Green, Blue, ...): "Emerald Green" and "Pistachio Green" both count as Green, "Prusa Urban Grey" and "Azurefilm Grey" as Grey. The family comes from the color name, or from the color swatch when the name has no color word. Each spool still shows its own color name in the results.
- The material and color lists only contain what you actually have (spools with filament left) and update by
  themselves while the dialog is open, for example when you archive or add a spool. Empty and archived spools are never offered.
- A **Load** button in the list marks the chosen spool as loaded in the printer (administrators only).
- No changes to your stored data.

## 0.9.2 - Catalog cleanup

- Product families are no longer listed as brands. The database marks them with a parent brand, and they are now
  product lines of that brand: PolyFlex, PolyLite, PolyMide, PolySonic, Panchroma and Fiberon under Polymaker;
  PrimaSelect, PrimaValue and EasyPrint under PrimaCreator; Jessie under PrintedSolid; The Filament under Spectrum;
  Professional LAB under SmartPrint. 160 brands became 148. Colors the parent already lists are not duplicated.
- One spelling per product line (PrimaSelect / Primaselect / PRIMASELECT), no duplicate colors, and product
  lines keep their "+" (Silk and Silk+, Tough and Tough+ stay separate).
- Lines no longer start with the brand name ("Artillery Basic" under Artillery is now "Basic"), and "PLA+" stays "PLA+"
  instead of becoming "+".
- Color names: shouting capitals ("BONDI BEACH") are title-cased, the material word is dropped
  ("PLA Marble" is "Marble"), single-letter names are removed, and a database entry cut at a comma
  (Cookiecad Mermaid) is repaired.
- The seven hand-tuned brands are unchanged for PLA, PETG and TPU (Polymaker gains its former sub-brands' lines).

## 0.9.1 - Full filament database

- The catalog now contains the whole Open Filament Database (snapshot of 2026-11-01): about 150 brands,
  14,700 colors and 38 materials (PLA, PETG, ABS, ASA, TPU, PC, PA, PCTG ... PEEK). Only 1.75 mm variants with a known
  color are listed.
- Prusament, AzureFilm, Polymaker, Rosa3D, Raise3D, Elegoo and Buddy3D keep their tidy hand-made product lines for
  PLA, PETG and TPU; their other materials now come from the database too.
- Other brands show the database's product names as the product line (for example "Bambu Lab > PLA > Basic").
- Brands are listed after your seven, in alphabetical order. Custom entries and your own catalog work as before.
- `tools/build_catalog.py` rebuilds the catalog from a database checkout.

## 0.9.0 - Release candidate (publishing preparation)

- Stat cards now lay out in tidy rows (2 columns on phones).
- Regenerated all README screenshots without brand logos.
- Rewrote the README for publication.
- Added LICENSE (MIT), THIRD_PARTY_NOTICES.md (Open Filament Database license and trademark notice), hacs.json,
  GitHub workflows (hassfest, HACS validation, tests), an issue template, requirements-test.txt and an original icon.
- No functional changes to your data.

## 0.6.0

- Added: **Printer tab** for your 3D printer(s) (up to 5):
  - Maintenance tasks with an interval in days and a "last done" date, shown as "due in 12 days" / "overdue by 3 days".
    The "Done" button restarts the countdown. When adding a printer you can start from a list (wipe the print sheet, clean
    the nozzle area, lubricate the rods, check the belts, clean the fans and filters, general check); all can be changed or deleted.
  - Parts and consumables in one list (spare nozzles, print sheets, IPA, wipes, needles, tools): category, how many you have,
    a unit, the printer it belongs to, an alert level, and + / - buttons. Items that reach the alert level (or that you mark)
    go on the same shopping list as the filament ("Copy shopping list" in the to-reorder view).
  - A "maintenance overdue" card, and a count on the Printer tab.
- Added: Home Assistant notifications and events for overdue maintenance (`spool_inventory_task_due`) and low parts
  (`spool_inventory_item_low`). Overdue tasks are checked every hour. They follow the same notification switch as the filament alerts.
- Added: sensors "Maintenance overdue" and "Parts and consumables low" (with the names in their attributes).
- Added: the history log also records maintenance done, and parts added, changed and deleted.
- Added: printers, tasks and items are part of the stored data, the backup file and the diagnostics.
- Fixed: the tab row no longer runs off the screen on a phone.
- Not included on purpose: connecting to the printer. The "Used in printer" button stays manual.

## 0.5.1

- Changed: the buttons on each spool are tidier. The everyday ones stay on the row (in the printer, reorder,
  bought another when on the reorder list, weigh, use). Edit, history, add another like this one, archive and delete moved
  into the "..." menu at the end of the row.
- Added: "Used in printer" button (shown when a spool is marked as loaded). It subtracts the grams of a print from the spool
  that is in the printer, and asks which one if more than one is marked. Nothing is connected to the printer for this.

## 0.5.0

- Added: history log. Every add, edit (when something other than the reorder / printer flags changed), weigh, use,
  archive, delete, restore and "bought another" is recorded with the date, the amount before and after, and a note.
  Open it with the clock button on a spool, or in the new History tab (latest 200 events of all spools).
  Entries that changed the amount have a "Set back to ... g" button. The last 2000 events are kept.
- The history is part of the backup file, the restore ("add missing" merges it without duplicates) and the stored data.
- Added: diagnostics download (Settings > Devices & services > Spool Inventory > the three dots > Download diagnostics).
  It contains your spools, settings and history, for bug reports. No passwords are stored by this integration.
- New command for scripts and the panel: `spool_inventory/history` (websocket).

## 0.4.3

- Added: Prusament refills. In the Add and Edit dialogs, Prusament spools have a "Format" choice: Spool (1000 g) or
  Refill (900 g, on a reusable spool). Only Prusament offers it. A refill shows a "refill" label, the shopping list
  says "(refill)", "Bought another" and "Add another like this one" keep the format, and it is in backups, the CSV and the
  `add_spool` / `update_spool` services (`refill`).
- Fixed: a stray word "null" appeared in the toolbar when there were no spools yet.

## 0.4.2

- Added: currency setting (Settings > Currency for prices: RON, EUR, USD, GBP or your own). It is shown on the value card
  ("61.00 RON"), on the value per location and on the Price field of the Add / Edit dialog. Default is RON.
  The currency is a label only: prices are not converted. It is included in backups.
- Fixed: a backup made in memory could change afterwards when settings changed (the settings and catalog are now copied).

## 0.4.1

- Added: each spool shows when it was last weighed ("weighed 3 days ago" / "not weighed yet"), in the table and the cards.
- Added: a "value of filament left" card, calculated from the prices you entered (price x share still on the spool).
  Spools without a price are left out (hover the card to see how many). The By location tab shows the value per place.
- Added: "Add another like this one" button (copy icon) on every spool. It opens the Add dialog filled with the same
  vendor, material, color, weights, price and location, as a full new spool.

## 0.4.0

- Added: Weigh session (one spool after another, Enter to save and go to the next, warnings for odd readings).
- Added: Archive tab for finished spools (no sensor, no alerts, not counted in totals); can be restored.
- Added: Undo after delete, and a "Recently deleted" list in Settings (last 25).
- Added: "Bought another" button, only on spools on the reorder list (adds a new full spool, clears the flag).
- Added: Backup download (JSON), restore from file (add missing / replace everything) and CSV export.
- Changed: stored data format is now version 2. A copy of the old file is saved before the upgrade
  (`.storage/spool_inventory.backup_before_upgrade`) and a daily copy is kept (`.storage/spool_inventory.backup_daily`).
- New stored fields: `archived`, `archived_at`, `weighed`; new list of deleted spools.

## 0.3.1

- Fixed: the location, vendor and material dropdowns did not work on phones. They are now normal selects with an "Other..." entry.
- Fixed: the "More fields" section of the Add dialog no longer closes by itself.

## 0.3.0

- Added: "in the printer" flag per spool (no automatic deduction yet).
- Added: low / empty alerts (threshold setting, Home Assistant notification, events `spool_inventory_low` and `spool_inventory_empty`).
- Added: reorder flag per spool, "to reorder" card and a copyable shopping list.
- Added: By location tab and a Settings dialog (threshold, notifications, your locations).
- Added: custom spools can be saved to "my catalog" and picked later; entries can be removed in Settings.
- Added: the stat cards are clickable filters.

## 0.2.2 / 0.2.1

- Catalog: added the missing colors you reported (Prusament Galaxy Black PETG, AzureFilm Red Pearl PETG, Polymaker TPU and PolyTerra PLA,
  Prusament Emerald Green PETG and the Noctua colors), plus Elegoo and Buddy3D (PLA and PETG).
- Catalog: restored ASA and PC for Prusament, ASA for AzureFilm and PC for Polymaker.
- Fixed: repeated and badly grouped product lines in the dropdown (Prusament, Rosa3D).

## 0.2.0 and earlier (summarized, details not recorded)

- Sidebar panel with the inventory table and cards, By color view, add / edit / weigh / use / delete,
  vendor badges and a filament catalog (Open Filament Database, MIT license).
- First version: sensors per spool, total filament and spool count, and the services
  `add_spool`, `update_spool`, `weigh_spool`, `consume_filament`, `delete_spool`, `list_spools`.
