# Custom Emoji Integration - Complete Guide

## ✅ What's Been Set Up

### 1. Core Emoji Helper Module (`core/emoji_helper.py`)
A new module that handles:
- Unicode emojis (like 📦)
- Custom Discord emojis (by ID)
- Automatic fallback if emoji not found

### 2. Updated `core/items.py`
New function: `get_item_display_name(item_data, item_id, bot)`
- Returns "emoji Name" format
- Works with both unicode and custom emojis
- Automatically looks up emoji from item data

### 3. Commands Updated to Show Emojis
✅ **scan** - Shows emojis next to dropped items  
✅ **explore** - Shows emojis next to dropped items  
✅ **code** - Shows emojis in reward displays  

## 📝 How to Add Your Custom Emojis

### Step 1: Get Emoji IDs from Discord

In Discord, type this in any channel:
```
\:plasteel:
```
(Replace `plasteel` with your emoji name)

Discord will display: `<:plasteel:1234567890123456>`

The number `1234567890123456` is your emoji ID.

### Step 2: Add to `data/items.json`

For each item with custom art, add an `"emoji_id"` field:

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

### Items to Add (from your `art/` directory):

**Materials:**
```json
"plasteel": { "emoji_id": YOUR_ID_HERE },
"plasteel_sheet": { "emoji_id": YOUR_ID_HERE },
"plasteel_bar": { "emoji_id": YOUR_ID_HERE },
"plasteel_beam": { "emoji_id": YOUR_ID_HERE },
"plasteel_block": { "emoji_id": YOUR_ID_HERE },
"circuit": { "emoji_id": YOUR_ID_HERE },
"microchip": { "emoji_id": YOUR_ID_HERE },
"processor": { "emoji_id": YOUR_ID_HERE },
"motherboard": { "emoji_id": YOUR_ID_HERE },
"quantum_computer": { "emoji_id": YOUR_ID_HERE },
"plasma": { "emoji_id": YOUR_ID_HERE },
"plasma_charge": { "emoji_id": YOUR_ID_HERE },
"plasma_core": { "emoji_id": YOUR_ID_HERE },
"plasma_module": { "emoji_id": YOUR_ID_HERE },
"plasma_slag": { "emoji_id": YOUR_ID_HERE },
"biofiber": { "emoji_id": YOUR_ID_HERE },
"bio_gel": { "emoji_id": YOUR_ID_HERE },
"biopolymer": { "emoji_id": YOUR_ID_HERE },
"bio_metal_hybrid": { "emoji_id": YOUR_ID_HERE },
"bio_material_block": { "emoji_id": YOUR_ID_HERE }
```

**Enemy Drops:**
```json
"crawler_tail": { "emoji_id": YOUR_ID_HERE },
"slug_slime": { "emoji_id": YOUR_ID_HERE },
"orchid_bloom": { "emoji_id": YOUR_ID_HERE },
"crystal_shard": { "emoji_id": YOUR_ID_HERE },
"lithium_ion": { "emoji_id": YOUR_ID_HERE }
```

## 🔧 Adding Emojis to More Commands

For any command that displays items, use this pattern:

```python
from core.items import get_item_display_name

# In your command function (must be in a Cog class):
item_data = get_item_by_id(items, item_id)
display_text = get_item_display_name(item_data, item_id, self.bot)
```

This will automatically show: `<:emoji:123456> Item Name` or `📦 Item Name`

### Commands That Will Automatically Show Emojis:
- `!scan` - Drop displays
- `!explore` - Drop displays  
- `!code` - Reward redemptions
- `!craft` - Crafting results (if you update it)
- `!inventory` - Item listings (if you update it)
- `!trade` - Trade displays (if you update it)
- Any other command using `get_item_display_name()`

## 🎯 Testing Your Setup

1. Add emoji IDs to `items.json` for at least one material (like plasteel)
2. Restart your bot
3. Run `!scan` or `!explore` until you get a drop
4. You should see your custom emoji next to the item name!

Example output:
```
✅ You defeated the Crawler!
Rewards: 💰 150 Scrap + ⭐ 25 XP!
Dropped Items: <:plasteel:123456> Plasteel x2, <:crawler_tail:789012> Crawler Tail x1
```

## 📊 Priority Order

The system checks for emojis in this order:
1. `emoji_id` (custom Discord emoji) - **Highest priority**
2. `emoji` (unicode emoji) - Fallback
3. No emoji - Just shows name

## ⚠️ Important Notes

- Custom emojis must be uploaded to a server your bot is in
- The bot needs access to that server to fetch the emoji
- If emoji ID is wrong, it will show as `<:emoji:123456>` instead of the actual emoji
- Unicode emojis (like 📦) always work regardless of server

## 🔄 Backward Compatibility

All existing unicode emojis (supply crates, etc.) will continue to work!
You can mix unicode and custom emojis freely.
