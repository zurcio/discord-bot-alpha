# EMOJI SETUP GUIDE

## Step 1: Get Your Custom Emoji IDs

For each emoji you uploaded to Discord:

1. In Discord, type `\:emoji_name:` (with the backslash) and send it
2. Discord will show the full emoji format: `<:emoji_name:1234567890123456>`
3. Copy the number (the emoji ID)

OR right-click the emoji in your server's emoji settings and copy its ID.

## Step 2: Add Emoji IDs to data/items.json

For each item that has custom art in the `art/` directory, add an `"emoji_id"` field.

### Example Format:

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

### Items That Need Emoji IDs:

Based on your art/ directory, add emoji_id for these items:

**Materials:**
- plasteel → plasteel.png
- plasteel_sheet → plasteel_sheet.png
- plasteel_bar → plasteel_bar.png
- plasteel_beam → plasteel_beam.png
- plasteel_block → plasteel_block.png
- circuit → circuit.png
- microchip → microchip.png
- processor → processor.png
- motherboard → motherboard.png
- quantum_computer → quantum_computer.png
- plasma → plasma.png
- plasma_charge → plasma_charge.png
- plasma_core → plasma_core.png
- plasma_module → plasma_module.png
- plasma_slag → plasma_slag.png
- biofiber → biofiber.png
- bio_gel → bio_gel.png
- biopolymer → biopolymer.png
- bio_metal_hybrid → bio_metal_hybrid.png
- bio_material_block → bio_material_block.png

**Enemy Drops:**
- crawler_tail → crawler_tail.png
- slug_slime → slug_slime.png
- orchid_bloom → orchid_bloom.png
- crystal_shard → crystal_shard.png
- lithium_ion → lithium_ion.png

## Step 3: The Bot Will Automatically Use These Emojis

Once you add the `emoji_id` fields, the emojis will appear automatically in:
- Inventory displays
- Craft command outputs
- Drop notifications (scan/explore)
- Trade listings
- Code redemptions
- Quest progress
- Any other command that shows item names

The helper module (core/emoji_helper.py) handles the emoji formatting automatically.

## Note: Existing Unicode Emojis

Items that already have unicode emojis (like supply crates with 📦, 🎁, etc.) will continue to work.
You can replace them with custom emoji IDs if you create custom art for those too.

## Format Reference:

- **Unicode emoji** (current): `"emoji": "📦"`
- **Custom emoji** (new): `"emoji_id": 1234567890123456`

Both work! Custom emoji IDs take priority if both are present.
