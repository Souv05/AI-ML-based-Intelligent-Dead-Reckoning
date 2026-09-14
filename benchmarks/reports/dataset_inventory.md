# IO-VNBD dataset inventory

- CSV files scanned: **564**  (241 `S-*`, 323 `V-*`), total 1.79 GB
- the tree holds ~3 overlapping copies (Synchronised/Categorised, Synchronised/Uncategorised, Unsynchronised); the pipeline uses only **Synchronised / Categorised** (144 files, 72 pairs)

## sampling rate (measured, not assumed)

- Synchronised/Categorised `S-*`: median 10.00 Hz, range 10.00-10.00 (uniformly 10 Hz - see `timestamp_diagnostics.csv`)
- all `S-*` incl. other pools: median 10.00 Hz, range 2.00-1000.00 (driver-A uncategorised logs are 2 Hz; a couple of `S-T*` files have sub-ms duplicate timestamps -> not used)
- all `V-*`: median 10.00 Hz

## incomplete / do-not-use (27 file entries, 11 unique names across copies)

- `S-Vta19.csv` - [292, 292, 292] rows
- `S-Vta9.csv` - [156, 156, 156] rows
- `S-Vtb10.csv` - [196, 196, 196] rows
- `S-Vw13.csv` - [284, 284, 284] rows
- `V-Vta18.csv` - [100] rows
- `V-Vta9.csv` - [226, 226] rows
- `V-Vtb10.csv` - [195, 195] rows
- `V-Vw13.csv` - [284, 284, 297, 297] rows
- `V-vta19.csv` - [292, 292] rows
- `V-vta9.csv` - [156, 156] rows
- `V-vtb10.csv` - [195, 195] rows

Full per-file detail: `dataset_inventory.csv`.
