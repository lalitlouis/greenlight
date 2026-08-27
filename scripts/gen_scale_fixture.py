#!/usr/bin/env python3
"""Deterministic generator for the SCALE-GATE fixture: an original, entity-dense
feature screenplay that stresses what small fixtures cannot — 100+ scenes,
~150 clearance-relevant entities (4 clearance batches), plus seeded traps for
every doctrine layer. Regenerate with:  python scripts/gen_scale_fixture.py

The screenplay is original work ("STATIC & NOISE" — a band-tour comedy). Real
brands/songs/venues appear as MENTIONS the way real screenplays mention them;
that is the product's subject matter. The seeded answer key lives in
scripts/eval_scale.py — keep the two in sync.
"""

from __future__ import annotations

from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "fixtures" / "scale_gate.fountain"

BRANDS_NEUTRAL = [
    "Fender",
    "Shure",
    "Peavey",
    "Yamaha",
    "Roland",
    "Marshall",
    "Pioneer",
    "Panasonic",
    "Casio",
    "Timex",
    "Reebok",
    "Champion",
    "Carhartt",
    "Stanley",
    "Igloo",
    "Rand McNally",
    "Motel 6",
    "Waffle House",
    "Cracker Barrel",
    "7-Eleven",
    "Chevron",
    "Greyhound",
    "U-Haul",
    "Sharpie",
    "Post-it",
    "Gatorade",
    "Doritos",
    "Slim Jim",
    "Red Vines",
    "Folgers",
    "Zippo",
    "Duracell",
    "Coleman",
    "Thermos",
    "WD-40",
    "Duct Tape brand Duck Tape",
    "Advil",
    "Chapstick",
    "Old Spice",
    "Irish Spring",
    "Tide",
    "Cheerios",
    "Pop-Tarts",
    "Mountain Dew",
    "A&W",
    "Sunoco",
    "Les Paul",
    "Zildjian",
    "Ludwig",
    "Ampeg",
    "Boss pedals",
    "Ernie Ball",
    "D'Addario",
    "Crown Royal",
    "Pabst",
    "Denny's",
    "IHOP",
    "AutoZone",
    "Pep Boys",
    "Firestone",
]
CHARACTERS = [
    "Marisol Quist",
    "Deacon Ferrier",
    "Tally Obranovich",
    "Hugh Sandoval",
    "Petra Wilhelm",
    "Ansel Grieg",
    "Noor Fakhoury",
    "Casimir Boyle",
    "Ida Trethewey",
    "Solomon Park",
    "Bex Arquette",
    "Fenwick Ames",
    "Junia Marsh",
    "Othello Craine",
    "Sylvie Bex",
    "Aldous Penn",
    "Mabel Torres",
    "Grover Nishimura",
    "Odette Vance",
    "Ezra Coldwater",
]
PEOPLE_MENTIONS = [
    "Dolly Parton",
    "Willie Nelson",
    "Stevie Nicks",
    "Bruce Springsteen",
    "Joan Jett",
    "Tom Petty",
    "Patti Smith",
    "Johnny Cash",
]
SONGS_TITLE_ONLY = [
    "Free Bird",
    "Sweet Home Alabama",
    "Barracuda",
    "Jolene",
    "Fortunate Son",
    "Go Your Own Way",
]

SCENE = """{head}

{action}

{extra}
"""


def gen() -> str:
    scenes: list[str] = []
    n = 0

    def add(head: str, action: str, extra: str = ""):
        nonlocal n
        n += 1
        scenes.append(SCENE.format(head=head, action=action, extra=extra).rstrip() + "\n")

    # --- act 1: seeded traps up front, in story order -----------------------
    add(
        "INT. THE SPARE ROOM - PRACTICE SPACE - DAY",
        "Cables everywhere. RENATA MOSS (34) tunes a Fender bass. Her brother "
        "OTIS (29) drums on an Igloo cooler. On the wall, a framed print of "
        "Edward Hopper's NIGHTHAWKS, and beside it a THRIFT-STORE OIL PAINTING "
        "of a lighthouse, unsigned.",
        "RENATA\nIf the van starts, we're a real band.",
    )
    add(
        "INT. TOUR VAN - MOVING - DAY",
        "The radio plays 'Baba O'Riley' by The Who — the actual recording, tinny "
        "through blown speakers. Otis drums the wheel. A Rand McNally atlas "
        "slides off the dash.",
        "OTIS\nTurn it up. This is church.",
    )
    add(
        "EXT. TRUCK STOP - CONTINUOUS - DAY",
        "Renata fills the tank at a Chevron. Otis buys Slim Jims and Gatorade "
        "at the 7-Eleven counter. On his forearm: a TATTOO of a coiled serpent, "
        "'inked by the artist Vera Kest at her Asheville parlor' — Renata says "
        "so, admiring it.",
        "RENATA\nKest charges four hundred an hour now. You got in early.",
    )
    add(
        "INT. ROADSIDE BAR 'THE DERAILLEUR' - NIGHT",
        "A dive. The band's first gig. A drunk HECKLER (50s) waves a Coors "
        "Light and bellows that it, quote, tastes like a wet sock wrung into a "
        "can, unquote, and hurls the full can at the stage. It sprays across "
        "Renata's amp — a Marshall stack.",
        "HECKLER\nWet sock! In a can!",
    )
    add(
        "INT. THE DERAILLEUR - LATER - NIGHT",
        "Closing time. June the bartender hums 'Amazing Grace' to herself, a "
        "cappella, stacking chairs. Renata harmonizes. It is quiet and lovely.",
        "",
    )
    add(
        "INT. GRAND MERIDIAN CASINO - GAMING FLOOR - NIGHT",
        "The band, broke, sneaks through the Grand Meridian Casino in Reno — "
        "a real gaming floor, security everywhere. Otis, drunk, climbs onto a "
        "blackjack table and KICKS OVER a rack of chips; the table FELT TEARS. "
        "Security wrestles him down as Renata films it.",
        "RENATA\nWe are absolutely using this for the album cover.",
    )
    add(
        "EXT. STATE FAIR - MAIN STAGE - DUSK",
        "Sound check. A BANNER reads WELCOME DOLLY PARTON FANS — the fair's "
        "headliner canceled; the band is the replacement. Renata tapes a "
        "handwritten setlist over the banner. Nobody disparages anyone; the "
        "crowd just wants Jolene.",
        "OTIS\nWe don't know Jolene.\n\nRENATA\nWe do now.",
    )

    # safety climax cluster
    add(
        "EXT. FAIRGROUND - PYRO TENT - NIGHT",
        "A FAIR TECH (17) — a minor, his badge says JUNIOR CREW — loads "
        "commercial FIREWORKS mortars twenty feet from the stage while Otis "
        "fuels a generator with a jerry can. Sparks from a grinder fan across "
        "dry August grass.",
        "",
    )
    add(
        "EXT. FAIRGROUND - STAGE - NIGHT",
        "Mid-song, the fireworks go off EARLY. Burning cardboard rains onto "
        "the stage canopy. Renata swings her bass through a burning guy-wire. "
        "The crowd cheers, thinking it is the show. The junior crew kid drags "
        "a hose alone.",
        "RENATA\n(shouting)\nFuck! Fuck! FUCK!",
    )

    # territory / rating cluster
    add(
        "INT. MOTEL 6 - ROOM 114 - NIGHT",
        "The band splits a joint, passing it in a lazy circle, and toasts with "
        "warm beer. On the TV, muted, a rerun plays. Otis recounts — in words "
        "only, nothing shown — the night he says he saw his dead grandmother "
        "at the foot of his bed. Everyone laughs it off as a dream.",
        "",
    )

    # neutral living-person cameo (counterweight: NOT defamation)
    add(
        "EXT. FESTIVAL PARKING LOT - DAY",
        "A tour bus idles. A ROADIE swears Bruce Springsteen once borrowed his "
        "phone charger at this exact rest stop and returned it with a thank-you "
        "note. The band is delighted. That is the whole story.",
        "",
    )

    # --- act 2: entity-density engine (bounded, deterministic) --------------
    towns = [
        "Mercer",
        "Ballard",
        "Coyle",
        "Ferndale",
        "Ruston",
        "Ashford",
        "Selleck",
        "Wilkeson",
        "Napavine",
        "Mineral",
    ]
    for i in range(88):
        town = towns[i % len(towns)]
        brand = BRANDS_NEUTRAL[i % len(BRANDS_NEUTRAL)]
        extra = ""
        who = CHARACTERS[i % len(CHARACTERS)]
        body = (
            f"The van rolls into {town} past a shuttered {BRANDS_NEUTRAL[(i + 31) % len(BRANDS_NEUTRAL)]} "
            f"franchise and a working {brand} sign that hums over the hall's counter. "
            f"Load-in. The local promoter, {who.upper()}, meets them at the dock with a "
            "clipboard and a story about the last band that came through — a story that "
            "gets longer every town. Renata restrings while the house PA crackles; Otis "
            "naps on the amp cases until soundcheck, then plays like the room owes him "
            "money. Merch sells in ones and twos. The tip jar is a Thermos with the "
            "label half gone. After, they load out in the dark, count gas money on the "
            "dashboard, and circle the next town on the atlas."
        )
        if i % 11 == 0:
            person = PEOPLE_MENTIONS[(i // 11) % len(PEOPLE_MENTIONS)]
            body += (
                f" A gig poster on the corkboard advertises a {person} tribute night, next month."
            )
        if i % 13 == 0:
            song = SONGS_TITLE_ONLY[(i // 13) % len(SONGS_TITLE_ONLY)]
            extra = f'OTIS\nRequest bucket says "{song}" again.\n\nRENATA\nTitle drop only. We play originals.'
        day = "NIGHT" if i % 3 else "DAY"
        add(f"INT. {town.upper()} GRANGE HALL - {day}", body, extra)

    # --- act 3: resolution ---------------------------------------------------
    add(
        "EXT. COLUMBIA GORGE OVERLOOK - DAWN",
        "The van, dented, steaming. The band watches the sun come up over the "
        "river. Renata pulls the thrift-store lighthouse painting from the "
        "back and props it on the guardrail like a trophy.",
        "RENATA\nOkay. Home. Then we do it again.",
    )

    title = (
        "Title: STATIC & NOISE\n"
        "Credit: written by\n"
        "Author: The GREENLIGHT Project (original fixture for the scale gate)\n"
        "Source: Based on the zine tour diaries 'Grange Hall Summers' by R. Moss (rights held)\n"
        "Draft date: 2026-08-26\n\n"
    )
    return title + "\n".join(scenes)


if __name__ == "__main__":
    text = gen()
    OUT.write_text(text)
    scene_count = text.count("INT.") + text.count("EXT.")
    print(f"wrote {OUT} — ~{scene_count} scenes, {len(text)} chars")
