# # ====== RECIPES COMMAND ======
import discord
from discord.ext import commands
from discord.ui import View, Button 
from core.shared import load_json
from core.constants import CRAFTING_FILE
from core.guards import require_no_lock
from core.items import load_items, resolve_item_by_name_or_alias

ITEMS_PER_PAGE = 4 # Number of recipes per page

class RecipesView(View):
    def __init__(self, recipes, category, ctx, items_data):  # CHANGED
        super().__init__(timeout=60)
        self.recipes = recipes
        self.category = category
        self.ctx = ctx
        self.index = 0
        self.items_data = items_data  # NEW

        # Buttons
        self.prev_button = Button(label="⬅️ Previous", style=discord.ButtonStyle.primary)
        self.next_button = Button(label="➡️ Next", style=discord.ButtonStyle.primary)
        self.add_item(self.prev_button)
        self.add_item(self.next_button)

        # Bind callbacks
        self.prev_button.callback = self.prev_page
        self.next_button.callback = self.next_page

    def _resolve_item_name_and_aliases(self, key: str) -> tuple:
        """Resolve a material/item ID to its display name and aliases; fallback to key if unknown."""
        # Try to find the item by key - could be the internal key like "plasteel" or "plasma"
        category, item_key, item_data = resolve_item_by_name_or_alias(self.items_data, str(key))
        
        if item_data:
            name = item_data.get("name", str(key))
            aliases = item_data.get("aliases", [])
            # Return name with first alias in parentheses if available
            if aliases:
                return f"{name} ({aliases[0]})"
            return name
        
        # Fallback: return the key as-is
        return str(key)

    def make_embed(self):
        embed = discord.Embed(
            title=f"📜 Recipes: {self.category.title()} (Page {self.index+1}/{self.total_pages})",
            color=discord.Color.green()
        )

        start = self.index * ITEMS_PER_PAGE
        end = start + ITEMS_PER_PAGE
        page_recipes = self.recipes[start:end]

        for r in page_recipes:
            name = r.get("name", "Unknown")
            description = r.get("description", "")
            recipe_aliases = r.get("aliases", [])
            recipe_aliases_str = ", ".join(recipe_aliases) if recipe_aliases else "None"
            materials = r.get("materials", {})
            # Display material names with aliases instead of raw IDs
            if isinstance(materials, dict):
                mat_pairs = []
                for k, v in materials.items():
                    mat_name = self._resolve_item_name_and_aliases(k)
                    mat_pairs.append(f"{mat_name}: {v}")
                materials_str = ", ".join(mat_pairs) if mat_pairs else "None"
            else:
                materials_str = "None"
            level_req = r.get("level_req", 0)

            value = f"**Description:** {description}\n**Craft Command:** `!craft {recipe_aliases[0] if recipe_aliases else name.lower()}`\n**Materials:** {materials_str}"
            if len(value) > 1024:
                value = value[:1021] + "..."
            if level_req > 0:
                value += f"\n**Level Requirement:** {level_req}"
            embed.add_field(name=name, value=value, inline=False)

        return embed

    @property
    def total_pages(self):
        return (len(self.recipes) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE

    async def prev_page(self, interaction: discord.Interaction):
        if interaction.user != self.ctx.author:
            await interaction.response.send_message("You can’t control this menu.", ephemeral=True)
            return
        if self.index > 0:
            self.index -= 1
            await interaction.response.edit_message(embed=self.make_embed(), view=self)

    async def next_page(self, interaction: discord.Interaction):
        if interaction.user != self.ctx.author:
            await interaction.response.send_message("You can’t control this menu.", ephemeral=True)
            return
        if self.index < self.total_pages - 1:
            self.index += 1
            await interaction.response.edit_message(embed=self.make_embed(), view=self)

class Recipes(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="recipes", aliases=["rcp", "recipe", "rec"])
    @require_no_lock()
    async def recipes(self, ctx, category: str = None):
        crafting_data = load_json(CRAFTING_FILE)
        recipes_dict = crafting_data.get("recipes", {})
        items_data = load_items()  # NEW

        if not category:
            categories = set(r.get("category", "Unknown") for r in recipes_dict.values())
            embed = discord.Embed(title="🛠 Crafting Categories", color=discord.Color.blue())
            embed.description = ", ".join(sorted(categories))
            embed.add_field(name="Usage", value="Type `!recipes <category>` to view recipes in that category.")
            await ctx.send(embed=embed)
            return

        category = category.lower()
        filtered = [r for r in recipes_dict.values() if r.get("category", "").lower() == category]

        if not filtered:
            await ctx.send(f"No recipes found for category `{category}`.")
            return

        view = RecipesView(filtered, category, ctx, items_data)  # CHANGED
        await ctx.send(embed=view.make_embed(), view=view)

async def setup(bot):
    await bot.add_cog(Recipes(bot))