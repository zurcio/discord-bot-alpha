import asyncio, time, random, discord
from typing import Optional
from core.decorators import requires_profile
from core.players import save_profile
from core.guards import set_lock, clear_lock
from core.crew import (
    capacity_for_sector, ensure_crew_struct, spawn_candidate, parse_offer_string,
    clamp_offer_to_wallet, hire_probability, pay_now, add_hired_crew
)

SPAWN_CHANCE = 0.03  # 3%

async def maybe_spawn_crew(ctx, source: str):
    player = ctx.player
    ensure_crew_struct(player)
    sector = int(player.get("sector") or 1)
    cap = capacity_for_sector(sector)
    if cap <= 0:
        return
    if len(player["crew"]) >= cap:
        return
    if random.random() >= SPAWN_CHANCE:
        return

    cand = spawn_candidate()
    # Lock during prompt
    set_lock(str(ctx.author.id), lock_type="crew_hire", allowed=set(), note="Crew hire prompt")
    try:
        embed = discord.Embed(
            title="🧑‍🚀 Applicant Appeared!",
            description=(
                f"Name: {cand['name']}\nType: {cand['type'].title()}\n"
                f"Demands: {cand['salary_demand']:,} Scrap salary, {cand['benefits_demand']} Medkits benefits.\n\n"
                "Reply within 15s using up to 6 tokens: 'scrap' (1000 each) and/or 'med' (1 each).\n"
                "Example: scrap scrap med med"
            ),
            color=discord.Color.teal()
        )
        await ctx.send(embed=embed)

        def check(m): return m.author.id == ctx.author.id and m.channel == ctx.channel

        try:
            msg = await ctx.bot.wait_for("message", timeout=15.0, check=check)
        except asyncio.TimeoutError:
            await ctx.send("The applicant left for another job.")
            return

        offer_scrap_nominal, offer_med_nominal, used = parse_offer_string(msg.content, max_tokens=6)

        # If no tokens offered at all, decline
        if offer_scrap_nominal <= 0 and offer_med_nominal <= 0:
            await ctx.send("No offer made. Applicant declined.")
            return

        # Hiring probability should reflect the strength of the actual offer the player can afford now
        pay_scrap, pay_med = clamp_offer_to_wallet(player, offer_scrap_nominal, offer_med_nominal)
        p = hire_probability(pay_scrap, pay_med, cand["salary_demand"], cand["benefits_demand"])
        hired = (random.random() <= p)

        # Deduct now (consumed on hire), clamped to wallet
        pay_now(player, pay_scrap, pay_med)

        if not hired:
            await ctx.send("The applicant declined your offer.")
            save_profile(ctx.author.id, player)
            return

        # Per-job cost is the nominal tokens offered (not clamped)
        crew = add_hired_crew(
            player,
            cand,
            per_job_scrap=offer_scrap_nominal,
            per_job_meds=offer_med_nominal,
            now=int(time.time())
        )
        save_profile(ctx.author.id, player)

        paid_note = ""
        if pay_scrap != offer_scrap_nominal or pay_med != offer_med_nominal:
            paid_note = f" Paid now: {pay_scrap:,} Scrap, {pay_med} Medkits."
        await ctx.send(
            f"Hired {crew['name']} ({crew['type'].title()}) as crew {crew['code']}. "
            f"Per-job cost: {crew['cost_scrap']:,} Scrap + {crew['cost_medkits']} Medkits.{paid_note}"
        )
    finally:
        clear_lock(str(ctx.author.id))