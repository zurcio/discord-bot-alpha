# QUICK START: Add Your First Custom Emoji

## Step-by-Step Example

### 1. Get the Emoji ID

In your Discord server (where you uploaded the emojis), type:
```
\:plasteel:
```

Discord will show you:
```
<:plasteel:1234567890123456>
```

Copy just the number: `1234567890123456`

### 2. Open `data/items.json`

Find the plasteel item (around line 385):
```json
"plasteel": {
  "name": "Plasteel",
  "aliases": ["plas", "p"],
  "type": "material",
  "usable": false,
  "sellable": true,
  "value": 25,
  "description": "Basic Plasteel material used for crafting."
}
```

### 3. Add the emoji_id

Update it to:
```json
"plasteel": {
  "name": "Plasteel",
  "aliases": ["plas", "p"],
  "type": "material",
  "emoji_id": 1234567890123456,
  "usable": false,
  "sellable": true,
  "value": 25,
  "description": "Basic Plasteel material used for crafting."
}
```

### 4. Restart Your Bot

### 5. Test It!

Run `!scan` or `!explore` until you get Plasteel as a drop.

You'll see:
```
Dropped Items: <:plasteel:1234567890123456> Plasteel x2
```

The emoji will render as your custom image!

## Repeat for All Your Art Files

Do the same for each .png file in your `art/` directory:

| Art File | Emoji Name | Item Key in items.json |
|----------|------------|------------------------|
| plasteel.png | :plasteel: | "plasteel" |
| circuit.png | :circuit: | "circuit" |
| plasma.png | :plasma: | "plasma" |
| biofiber.png | :biofiber: | "biofiber" |
| crawler_tail.png | :crawler_tail: | "crawler_tail" |
| slug_slime.png | :slug_slime: | "slug_slime" |
| orchid_bloom.png | :orchid_bloom: | "orchid_bloom" |
| crystal_shard.png | :crystal_shard: | "crystal_shard" |
| lithium_ion.png | :lithium_ion: | "lithium_ion" |
| plasteel_sheet.png | :plasteel_sheet: | "plasteel_sheet" |
| plasteel_bar.png | :plasteel_bar: | "plasteel_bar" |
| plasteel_beam.png | :plasteel_beam: | "plasteel_beam" |
| plasteel_block.png | :plasteel_block: | "plasteel_block" |
| microchip.png | :microchip: | "microchip" |
| processor.png | :processor: | "processor" |
| motherboard.png | :motherboard: | "motherboard" |
| quantum_computer.png | :quantum_computer: | "quantum_computer" |
| plasma_charge.png | :plasma_charge: | "plasma_charge" |
| plasma_core.png | :plasma_core: | "plasma_core" |
| plasma_module.png | :plasma_module: | "plasma_module" |
| plasma_slag.png | :plasma_slag: | "plasma_slag" |
| bio_gel.png | :bio_gel: | "bio_gel" |
| biopolymer.png | :biopolymer: | "biopolymer" |
| bio_metal_hybrid.png | :bio_metal_hybrid: | "bio_metal_hybrid" |
| bio_material_block.png | :bio_material_block: | "bio_material_block" |

## Pro Tip: Batch Get All IDs

In Discord, type all of these at once:
```
\:plasteel: \:circuit: \:plasma: \:biofiber: \:crawler_tail: \:slug_slime: \:orchid_bloom: \:crystal_shard: \:lithium_ion: \:plasteel_sheet: \:plasteel_bar: \:plasteel_beam: \:plasteel_block: \:microchip: \:processor: \:motherboard: \:quantum_computer: \:plasma_charge: \:plasma_core: \:plasma_module: \:plasma_slag: \:bio_gel: \:biopolymer: \:bio_metal_hybrid: \:bio_material_block:
```

You'll get all the IDs in one message that you can copy from!
