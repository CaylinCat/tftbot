import argparse
import asyncio
from collections import defaultdict
from urllib.parse import quote

import aiohttp


CURRENT_TFT_SET = "set17"
OVERVIEWS_URL = "https://tft.dakgg.io/api/v1/summoners/na1/{name}/overviews?season={season}"
TRAITS_DATA_URL = "https://tft.dakgg.io/api/v1/data/traits?hl=en&season={season}"


def bar(value: float, max_value: float, width: int = 30) -> str:
    if max_value <= 0:
        return ""
    filled = int((value / max_value) * width)
    return "#" * filled + "." * (width - filled)


async def fetch_json(session: aiohttp.ClientSession, url: str):
    async with session.get(url, timeout=30) as resp:
        resp.raise_for_status()
        return await resp.json()


async def main():
    parser = argparse.ArgumentParser(description="Local DAKGG trait tester")
    parser.add_argument("--name", default="Satella018-LOOT", help="Riot ID (e.g. Satella018-LOOT)")
    parser.add_argument("--set", dest="set_name", default=CURRENT_TFT_SET, help="Set id (e.g. set17)")
    parser.add_argument("--top", type=int, default=10, help="How many top traits to print/chart")
    args = parser.parse_args()

    encoded_name = quote(args.name)
    overviews_url = OVERVIEWS_URL.format(name=encoded_name, season=args.set_name)
    traits_url = TRAITS_DATA_URL.format(season=args.set_name)

    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}

    async with aiohttp.ClientSession(headers=headers) as session:
        overviews_data = await fetch_json(session, overviews_url)
        traits_data = await fetch_json(session, traits_url)

    api_trait_map = {}
    for trait in traits_data.get("traits", []):
        ingame_key = trait.get("ingameKey")
        name = trait.get("name")
        if ingame_key and name:
            api_trait_map[ingame_key] = name

    trait_stats = []
    for overview in overviews_data.get("summonerSeasonOverviews", []):
        for match in overview.get("matchStats", []):
            if match.get("key") == "last20" and match.get("plays") == 20:
                trait_stats = match.get("traitStats", [])
                break
        if trait_stats:
            break

    print("\n=== API RAW CHECK ===")
    print(f"Summoner: {args.name}")
    print(f"Set: {args.set_name}")
    print(f"Trait mapping entries: {len(api_trait_map)}")
    print(f"Trait stats entries in last20: {len(trait_stats)}")
    if trait_stats:
        print(f"First raw trait entry: {trait_stats[0]}")

    if not trait_stats:
        print("\nNo last20 trait stats found for this player.")
        return

    grouped = defaultdict(lambda: {"plays": 0, "wins": 0, "tops": 0, "placements": 0})
    for entry in trait_stats:
        key_value = entry.get("key")
        if isinstance(key_value, list) and key_value:
            raw_trait = key_value[0]
        elif isinstance(key_value, str):
            raw_trait = key_value
        else:
            continue

        grouped[raw_trait]["plays"] += entry.get("plays", 0)
        grouped[raw_trait]["wins"] += entry.get("wins", 0)
        grouped[raw_trait]["tops"] += entry.get("tops", 0)
        grouped[raw_trait]["placements"] += entry.get("placements", 0)

    parsed = []
    for raw_trait, stats in grouped.items():
        plays = stats["plays"]
        wins = stats["wins"]
        tops = stats["tops"]
        placements = stats["placements"]
        parsed.append(
            {
                "trait": api_trait_map.get(raw_trait, raw_trait),
                "raw_trait": raw_trait,
                "plays": plays,
                "win_rate": round((wins / plays) * 100, 2) if plays else 0.0,
                "top4_rate": round((tops / plays) * 100, 2) if plays else 0.0,
                "avg_rank": round((placements / plays), 2) if plays else 0.0,
            }
        )

    parsed.sort(key=lambda x: x["plays"], reverse=True)
    top_rows = parsed[: args.top]

    print("\n=== PARSED TRAIT TABLE (LAST 20) ===")
    print(f"{'Trait':<18} {'Plays':>5} {'Win%':>8} {'Top4%':>8} {'Avg':>7}  Raw Key")
    print("-" * 80)
    for row in top_rows:
        print(
            f"{row['trait'][:18]:<18} {row['plays']:>5} {row['win_rate']:>8.2f} {row['top4_rate']:>8.2f} {row['avg_rank']:>7.2f}  {row['raw_trait']}"
        )

    print("\n=== ASCII CHART: TOP TRAITS BY PLAYS ===")
    max_plays = max(r["plays"] for r in top_rows) if top_rows else 0
    for row in top_rows:
        print(f"{row['trait'][:16]:<16} | {bar(row['plays'], max_plays)} | {row['plays']}")

    print("\n=== ASCII CHART: TOP TRAITS BY WIN RATE ===")
    max_wr = max(r["win_rate"] for r in top_rows) if top_rows else 0
    for row in sorted(top_rows, key=lambda x: x["win_rate"], reverse=True):
        print(f"{row['trait'][:16]:<16} | {bar(row['win_rate'], max_wr)} | {row['win_rate']:.2f}%")

    print(
        "\nNote: DAKGG overviews gives aggregated last20 stats. "
        "It does not provide per-game placement timeline in this endpoint."
    )


if __name__ == "__main__":
    asyncio.run(main())
