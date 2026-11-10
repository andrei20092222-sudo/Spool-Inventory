# Changelog

All notable changes to Spool Inventory, newest first. The version number is the one in `manifest.json`.
Updating never needs anything beyond copying the folder over and restarting Home Assistant
(plus Ctrl+F5 in the browser for panel changes).

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
