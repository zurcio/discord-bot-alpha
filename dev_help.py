from core.shared import load_json
from core.constants import PLANETS_FILE, BOSSES_FILE, ITEMS_FILE

def expected_power(planet_id:int):
    planets = load_json(PLANETS_FILE)
    bosses = load_json(BOSSES_FILE)
    items = load_json(ITEMS_FILE)
    p = planets[str(planet_id)]
    L = int(p["level_requirement"])
    # Pull required gear from this planet's boss
    boss = bosses[p["boss_id"]]
    w = items["weapons"][str(boss["required_weapon_id"])]["attack"]
    a = items["armor"][str(boss["required_armor_id"])]["defense"]
    A_level = 5 * L
    D_level = 5 * L
    A_eff = max(A_level, w) + 0.2 * min(A_level, w)
    D_eff = max(D_level, a) + 0.2 * min(D_level, a)
    return round(A_eff), round(D_eff)

def recommend_enemy_stats(planet_id:int):
    A_eff, D_eff = expected_power(planet_id)
    basic = dict(atk=D_eff + 7,  defn=max(0, A_eff - 10), hp=40)
    elite = dict(atk=D_eff + 12, defn=max(0, A_eff - 8),  hp=110)
    boss  = dict(atk=D_eff + 20, defn=max(0, A_eff - 12), hp_per_player= int(30 * 11))
    return {"basic": basic, "elite": elite, "boss": boss}


if __name__ == "__main__":
    for pid in range(1, 11):
        print(pid, recommend_enemy_stats(pid))