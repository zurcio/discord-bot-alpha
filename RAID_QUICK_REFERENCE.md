# Raid System Quick Reference

## Commands

### Status & Information
- `!raid` or `!raid status` - View current raid status
- `!raid leaderboard` - View top 5 contributors

### Personal Artillery Battery
- `!raid charge <resource> <amount>` - Charge your personal battery
  - Resources: `scrap`, `plasteel`, `circuit`, `plasma`, `biofiber`
  - Example: `!raid charge plasteel 100`
- `!raid attack` - Preview your charge and request confirmation
- `!raid attack yes` - Confirm and fire artillery

### Mega-Weapons
- `!raid support <resource> <amount>` - Charge mega-weapons
  - Resources match weapon types (same as above)
  - Example: `!raid support plasma 500`
  - Auto-fires at 100% with announcement

### Rewards
- `!raid claim` - Claim your rewards after raid ends

## Conversion Rates

### Personal Battery (100 units capacity)
| Resource | Units per Item |
|----------|---------------|
| Materials (plasteel/circuit/plasma/biofiber) | 1 unit per 10 items |
| Scrap | 1 unit per 0.2% of total scrap* |

*Total scrap = wallet + bank balance

### Mega-Weapons (100 units capacity)
| Resource | Units per Item |
|----------|---------------|
| Materials | 1 unit per 100 items |
| Scrap | 1 unit per 0.5% of total scrap* |

## Damage Output
- **Personal Artillery**: 0.5% of boss max HP at 100% charge (linear scaling)
- **Mega-Weapons**: 10% of boss max HP per firing

## Cooldowns
- **Personal Battery**:
  - 5 minutes between charge actions
  - 1 hour after firing (blocks both charging and attacking)
- **Mega-Weapons**:
  - 1 hour after charging (resets when weapon fires)

## Mega-Weapon Types
1. **Flak Cannon** - Plasteel
2. **Chain Vulcan** - Circuit
3. **Artillery Beam** - Plasma
4. **Almond Launcher** - Biofiber
5. **ATM Machine** - Scrap

## Rewards (Rank-Based)
| Rank | % of Pool |
|------|-----------|
| 1st | 30% |
| 2nd-3rd | 20% each |
| 4th-5th | 10% each |
| 6th-10th | 5% each |
| 11th+ | 2% each |

**Base Pool**: 50,000 Scrap (victory)  
**Consolation**: 5,000 Scrap (defeat) - same rank distribution

## Tips
- Higher total scrap (wallet + bank) = more expensive to charge, but same effectiveness
- Mega-weapons are 10x more expensive than personal battery
- Personal artillery fires on demand, mega-weapons fire automatically
- Save your personal battery for strategic timing (e.g., finishing blow)
- Coordinate with team to charge different mega-weapons
- Check `!raid status` to see cooldowns and current charge levels
