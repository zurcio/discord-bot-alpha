# Raid System Rework - Type 1: World Boss (Complete)

## Overview
Completely reworked the raid system to implement Type 1 World Boss mechanics with personal artillery batteries and mega-weapons. Removed old support buff system entirely.

## Key Changes

### 1. Personal Artillery Battery
- **Capacity**: 100 units = 100% charge
- **Charging**: Use `!raid charge <resource> <amount>`
  - Resources: scrap, plasteel, circuit, plasma, biofiber
  - Conversion rates:
    - Materials: 10 units = 1 battery unit
    - Scrap: 0.2% of total scrap (wallet + bank) = 1 battery unit
- **Attacking**: Use `!raid attack`
  - Shows confirmation prompt with current charge %
  - Confirm with `!raid attack yes`
  - Deals 0.5% boss max HP at 100% charge (linear scaling)
  - Consumes all charge on fire
- **Cooldowns**:
  - 5 minutes between charge actions
  - 1 hour cooldown after firing (blocks both charging and attacking)

### 2. Mega-Weapons (5 Types)
- **Flak Cannon** (plasteel)
- **Chain Vulcan** (circuit)
- **Artillery Beam** (plasma)
- **Almond Launcher** (biofiber)
- **ATM Machine** (scrap)

**Mechanics**:
- Charging: Use `!raid support <resource> <amount>`
- Conversion rates:
  - Materials: 100 units = 1 battery unit
  - Scrap: 0.5% of total scrap (wallet + bank) = 1 battery unit
- Auto-fire at 100% charge
- Deals 10% boss max HP per firing
- Announces to channel: "@player charged the [Weapon Name]! It fires at [Boss] for X damage!"
- **Cooldown**: 1 hour after any charge action (resets on fire)

### 3. Reward System (Rank Bands)
Replaced proportional rewards with tiered rank bands:

| Rank | Reward % of Pool |
|------|------------------|
| 1    | 30%              |
| 2-3  | 20% each         |
| 4-5  | 10% each         |
| 6-10 | 5% each          |
| 11+  | 2% each          |

**Base Pool**: 50,000 Scrap (successful raid)
**Consolation**: 10% of pool (failed raid)

**Claiming**: Use `!raid claim` after raid ends
- One-time claim per player per raid
- Cannot claim during active raid

### 4. Status Display (Enhanced)
`!raid status` now shows:
- **Before Raid**: Battery charge progress with embed
- **During Raid**:
  - Boss name, HP bar with percentage
  - Time remaining
  - Your personal artillery battery % (with cooldown timer if active)
  - All 5 mega-weapons with charge percentages
  - Top 5 contributors with damage dealt
  - Command hints in footer

### 5. Removed Features
- Old support buff system (supply fighters)
- Group damage multipliers
- `add_support()` function
- `_get_group_buff_mult()` function
- All buff-related tracking in raid state

### 6. Rate Limiting Details
**Personal Battery**:
- 5-min cooldown between charge actions
- 1-hour cooldown after firing (blocks charging/attacking)

**Mega-Weapons**:
- 1-hour cooldown after charging any mega-weapon
- Cooldown resets when weapon fires (allows immediate recharge)

**Material/Scrap Costs**:
- Based on percentage of total scrap (wallet + bank balance)
- Scales with player wealth
- Prevents infinite charging exploits

## Configuration Tuning
All reward values are clearly defined in `systems/raids.py`:

```python
# Rank band payouts (line ~82)
RANK_BANDS = [
    (1, 0.30),    # Rank 1: 30% of pool
    (3, 0.20),    # Ranks 2-3: 20% each
    (5, 0.10),    # Ranks 4-5: 10% each
    (10, 0.05),   # Ranks 6-10: 5% each
    (999, 0.02),  # Ranks 11+: 2% each
]

# Base reward pool (line ~80)
BASE_REWARD_POOL_SCRAP = 50_000

# Cooldown timers (lines ~60-77)
PERSONAL_ATTACK_COOLDOWN_SEC = 60 * 60   # 1 hour
PERSONAL_CHARGE_COOLDOWN_SEC = 5 * 60    # 5 minutes
MEGA_CHARGE_COOLDOWN_SEC = 60 * 60       # 1 hour

# Conversion rates (lines ~65-75)
PERSONAL_MATERIALS_PER_UNIT = 10
PERSONAL_SCRAP_PERCENT_PER_UNIT = 0.2
MEGA_MATERIALS_PER_UNIT = 100
MEGA_SCRAP_PERCENT_PER_UNIT = 0.5

# Damage scaling (lines ~61-73)
PERSONAL_FULL_DAMAGE_FRAC = 0.005  # 0.5% boss HP at 100%
MEGA_DAMAGE_FRAC = 0.10            # 10% boss HP per shot
```

## Testing Checklist
- [ ] !raid status (prep phase) - shows battery charging
- [ ] !raid status (active raid) - shows all weapons and personal battery
- [ ] !raid charge plasteel 100 - charges personal battery
- [ ] !raid charge (with cooldown) - shows cooldown message
- [ ] !raid attack - shows confirmation prompt
- [ ] !raid attack yes - fires and applies cooldown
- [ ] !raid support scrap 1000 - charges mega-weapon
- [ ] !raid support (at 100%) - fires mega-weapon with announcement
- [ ] !raid claim (after raid) - distributes rank-based rewards
- [ ] Multiple players contributing - verify leaderboard and rank payouts

## Commands Summary
```
!raid status           - View raid status (battery or active raid)
!raid charge <res> <amt> - Charge personal artillery
!raid attack           - Preview personal battery charge
!raid attack yes       - Confirm and fire personal artillery
!raid support <res> <amt> - Charge mega-weapons
!raid leaderboard      - View top contributors
!raid claim            - Claim rewards after raid ends
```

## Files Modified
1. `commands/raid.py` - Complete rewrite of attack/charge/support/status commands
2. `systems/raids.py` - Added cooldowns, rank-based rewards, removed old buff system

## Notes
- Total scrap calculation includes both wallet and bank balance
- Material inventory uses lowercase keys (plasteel, circuit, plasma, biofiber)
- Scrap costs are percentage-based to scale with player wealth
- All cooldowns and reward values can be easily tuned in systems/raids.py constants
