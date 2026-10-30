"""Small, hand-maintained vocabulary used by query generation and relevance.

Keep this boring and explicit. Add entries as you need them.
"""

from __future__ import annotations

import re

# English part name -> German search terms (first one is the preferred term).
PART_TRANSLATIONS_DE: dict[str, list[str]] = {
    "front bumper": ["Stoßstange vorne", "Stoßfänger vorne"],
    "rear bumper": ["Stoßstange hinten", "Stoßfänger hinten"],
    "bumper": ["Stoßstange", "Stoßfänger"],
    "headlight": ["Scheinwerfer"],
    "headlamp": ["Scheinwerfer"],
    "tail light": ["Rückleuchte"],
    "taillight": ["Rückleuchte"],
    "bonnet": ["Motorhaube"],
    "hood": ["Motorhaube"],
    "fender": ["Kotflügel"],
    "wing": ["Kotflügel"],
    "door": ["Tür"],
    "mirror": ["Außenspiegel"],
    "wing mirror": ["Außenspiegel"],
    "radiator": ["Kühler", "Wasserkühler"],
    "condenser": ["Klimakondensator", "Kondensator"],
    "grille": ["Kühlergrill", "Niere"],
    "kidney grille": ["Niere", "Kühlergrill"],
    "windscreen": ["Windschutzscheibe"],
    "windshield": ["Windschutzscheibe"],
    "airbag": ["Airbag"],
    "steering wheel": ["Lenkrad"],
    "dashboard": ["Armaturenbrett"],
    "seat": ["Sitz"],
    "wheel": ["Felge"],
    "rim": ["Felge"],
    "engine": ["Motor"],
    "gearbox": ["Getriebe"],
    "transmission": ["Getriebe"],
    "turbo": ["Turbolader"],
    "turbocharger": ["Turbolader"],
    "starter": ["Anlasser"],
    "alternator": ["Lichtmaschine"],
    "control arm": ["Querlenker"],
    "shock absorber": ["Stoßdämpfer"],
    "brake disc": ["Bremsscheibe"],
    "brake caliper": ["Bremssattel"],
    "exhaust": ["Auspuff"],
    "fog light": ["Nebelscheinwerfer"],
    "parking sensor": ["PDC Sensor", "Einparksensor"],
    "intercooler": ["Ladeluftkühler"],
    "subframe": ["Achsträger", "Hilfsrahmen"],
    "bumper reinforcement": ["Stoßfängerträger", "Querträger"],
    "crash bar": ["Stoßfängerträger", "Querträger"],
    "bumper grille": ["Stoßstangengitter", "Gitter Stoßstange"],
    "bumper bracket": ["Stoßstangenhalter", "Halter Stoßstange"],
    "front panel": ["Frontmaske", "Schlossträger"],
    "radiator support": ["Schlossträger", "Frontmaske"],
    "front end": ["Front komplett", "Vorderwagen"],
    "tailgate": ["Heckklappe"],
    "boot lid": ["Heckklappe", "Kofferraumdeckel"],
    "trunk lid": ["Heckklappe", "Kofferraumdeckel"],
    "door mirror": ["Außenspiegel"],
    "side mirror": ["Außenspiegel"],
    "mirror glass": ["Spiegelglas"],
    "door handle": ["Türgriff"],
    "door lock": ["Türschloss"],
    "window regulator": ["Fensterheber"],
    "door panel": ["Türverkleidung"],
    "door card": ["Türverkleidung"],
    "side skirt": ["Seitenschweller", "Schwellerverkleidung"],
    "rocker panel": ["Seitenschweller", "Schwellerverkleidung"],
    "quarter panel": ["Seitenwand"],
    "rear window": ["Heckscheibe"],
    "side window": ["Seitenscheibe"],
    "sunroof": ["Schiebedach"],
    "spoiler": ["Spoiler", "Heckspoiler"],
    "wheel arch liner": ["Radhausschale", "Radlaufschale"],
    "undertray": ["Unterfahrschutz", "Motorabdeckung unten"],
    "fuel flap": ["Tankdeckel", "Tankklappe"],
    "indicator": ["Blinker"],
    "turn signal": ["Blinker"],
    "brake light": ["Bremsleuchte", "dritte Bremsleuchte"],
    "tail lamp": ["Rückleuchte"],
    "xenon ballast": ["Xenon Steuergerät", "Vorschaltgerät"],
    "cylinder head": ["Zylinderkopf"],
    "injector": ["Einspritzdüse", "Injektor"],
    "fuel injector": ["Einspritzdüse", "Injektor"],
    "fuel pump": ["Kraftstoffpumpe"],
    "high pressure pump": ["Hochdruckpumpe"],
    "water pump": ["Wasserpumpe"],
    "oil pump": ["Ölpumpe"],
    "egr valve": ["AGR Ventil", "Abgasrückführventil"],
    "throttle body": ["Drosselklappe"],
    "intake manifold": ["Ansaugkrümmer"],
    "exhaust manifold": ["Abgaskrümmer"],
    "dpf": ["Rußpartikelfilter", "DPF"],
    "particulate filter": ["Rußpartikelfilter", "DPF"],
    "catalytic converter": ["Katalysator"],
    "muffler": ["Auspuff", "Endschalldämpfer"],
    "silencer": ["Endschalldämpfer", "Auspuff"],
    "timing chain": ["Steuerkette"],
    "flywheel": ["Schwungrad", "Zweimassenschwungrad"],
    "clutch": ["Kupplung", "Kupplungssatz"],
    "ignition coil": ["Zündspule"],
    "oil cooler": ["Ölkühler"],
    "radiator fan": ["Kühlerlüfter", "Lüfter"],
    "cooling fan": ["Kühlerlüfter", "Lüfter"],
    "expansion tank": ["Ausgleichsbehälter"],
    "air filter box": ["Luftfilterkasten"],
    "mass air flow sensor": ["Luftmassenmesser"],
    "engine mount": ["Motorlager"],
    "ecu": ["Motorsteuergerät", "Steuergerät"],
    "wiring harness": ["Kabelbaum"],
    "battery": ["Batterie"],
    "propshaft": ["Kardanwelle"],
    "prop shaft": ["Kardanwelle"],
    "driveshaft": ["Antriebswelle", "Gelenkwelle"],
    "drive shaft": ["Antriebswelle", "Gelenkwelle"],
    "cv axle": ["Antriebswelle"],
    "differential": ["Differential", "Hinterachsgetriebe"],
    "transfer case": ["Verteilergetriebe"],
    "gear selector": ["Wählhebel", "Schalthebel"],
    "gear lever": ["Schalthebel", "Wählhebel"],
    "wheel hub": ["Radnabe"],
    "wheel bearing": ["Radlager"],
    "steering knuckle": ["Achsschenkel"],
    "coil spring": ["Feder", "Fahrwerksfeder"],
    "anti roll bar": ["Stabilisator"],
    "sway bar": ["Stabilisator"],
    "strut": ["Federbein"],
    "front axle": ["Vorderachse", "Achsträger vorne"],
    "rear axle": ["Hinterachse", "Achsträger hinten"],
    "steering rack": ["Lenkgetriebe"],
    "power steering pump": ["Servopumpe"],
    "steering column": ["Lenksäule"],
    "brake pads": ["Bremsbeläge"],
    "abs pump": ["ABS Pumpe", "ABS Hydraulikblock"],
    "instrument cluster": ["Tacho", "Kombiinstrument"],
    "speedometer": ["Tacho", "Kombiinstrument"],
    "radio": ["Radio"],
    "display": ["Display", "Bildschirm"],
    "navigation": ["Navigation", "Navi"],
    "climate control panel": ["Klimabedienteil", "Klimabedienung"],
    "blower motor": ["Gebläsemotor"],
    "heater core": ["Wärmetauscher", "Heizungskühler"],
    "ac compressor": ["Klimakompressor"],
    "window switch": ["Fensterheberschalter"],
    "driver airbag": ["Fahrerairbag", "Lenkradairbag"],
    "passenger airbag": ["Beifahrerairbag"],
    "seat belt": ["Sicherheitsgurt"],
    "centre console": ["Mittelkonsole"],
    "center console": ["Mittelkonsole"],
    "glovebox": ["Handschuhfach"],
    "key": ["Schlüssel"],
    "key fob": ["Schlüssel", "Funkschlüssel"],
    "reversing camera": ["Rückfahrkamera"],
    "rear camera": ["Rückfahrkamera"],
    "wiper motor": ["Wischermotor"],
    "wiper arm": ["Wischerarm"],
    "washer tank": ["Waschwasserbehälter"],
    "horn": ["Hupe", "Fanfare"],
    "fuel tank": ["Kraftstofftank", "Tank"],
    # Suspension and steering
    "suspension": ["Fahrwerk"],
    "front suspension": ["Fahrwerk vorne"],
    "rear suspension": ["Fahrwerk hinten"],
    "spring": ["Feder", "Fahrwerksfeder"],
    "leaf spring": ["Blattfeder"],
    "air suspension": ["Luftfahrwerk", "Luftfederung"],
    "air spring": ["Luftfeder", "Luftfederbalg"],
    "ball joint": ["Traggelenk"],
    "tie rod": ["Spurstange"],
    "track rod": ["Spurstange"],
    "tie rod end": ["Spurstangenkopf"],
    "stabilizer": ["Stabilisator"],
    "stabilizer link": ["Koppelstange", "Pendelstütze"],
    "drop link": ["Koppelstange", "Pendelstütze"],
    "trailing arm": ["Längslenker"],
    "wishbone": ["Querlenker"],
    "bump stop": ["Anschlagpuffer"],
    "top mount": ["Domlager", "Federbeinstützlager"],
    "strut mount": ["Domlager", "Federbeinstützlager"],
    "shock mount": ["Domlager", "Federbeinstützlager"],
}

# English part name -> Bulgarian search terms (bazar.bg and other Bulgarian sites).
PART_TRANSLATIONS_BG: dict[str, list[str]] = {
    "front bumper": ["предна броня"],
    "rear bumper": ["задна броня"],
    "bumper": ["броня"],
    "headlight": ["фар"],
    "headlamp": ["фар"],
    "tail light": ["стоп"],
    "taillight": ["стоп"],
    "bonnet": ["преден капак"],
    "hood": ["преден капак"],
    "fender": ["калник"],
    "wing": ["калник"],
    "door": ["врата"],
    "mirror": ["огледало"],
    "wing mirror": ["огледало"],
    "radiator": ["радиатор"],
    "condenser": ["климатичен радиатор"],
    "grille": ["решетка", "бъбреци"],
    "kidney grille": ["бъбреци"],
    "windscreen": ["предно стъкло"],
    "windshield": ["предно стъкло"],
    "airbag": ["airbag", "еърбег"],
    "steering wheel": ["волан"],
    "dashboard": ["табло"],
    "seat": ["седалка", "седалки"],
    "wheel": ["джанти"],
    "rim": ["джанти"],
    "engine": ["двигател"],
    "gearbox": ["скоростна кутия"],
    "transmission": ["скоростна кутия"],
    "turbo": ["турбо"],
    "turbocharger": ["турбо"],
    "starter": ["стартер"],
    "alternator": ["алтернатор", "генератор"],
    "control arm": ["носач"],
    "shock absorber": ["амортисьор"],
    "brake disc": ["спирачни дискове"],
    "brake caliper": ["спирачен апарат"],
    "exhaust": ["ауспух"],
    "fog light": ["халоген"],
    "parking sensor": ["сензор парктроник", "парктроник"],
    "intercooler": ["интеркулер"],
    "subframe": ["подрамка", "греда"],
    "bumper reinforcement": ["греда за броня"],
    "crash bar": ["греда за броня"],
    "bumper grille": ["решетка броня"],
    "bumper bracket": ["държач броня"],
    "front panel": ["преден панел"],
    "radiator support": ["преден панел"],
    "front end": ["предница"],
    "tailgate": ["заден капак"],
    "boot lid": ["заден капак"],
    "trunk lid": ["заден капак"],
    "door mirror": ["огледало"],
    "side mirror": ["огледало"],
    "mirror glass": ["стъкло огледало"],
    "door handle": ["дръжка врата"],
    "door lock": ["брава врата"],
    "window regulator": ["стъклоповдигач"],
    "door panel": ["кора врата"],
    "door card": ["кора врата"],
    "side skirt": ["праг"],
    "rocker panel": ["праг"],
    "quarter panel": ["заден калник"],
    "rear window": ["задно стъкло"],
    "side window": ["странично стъкло"],
    "sunroof": ["шибидах"],
    "spoiler": ["спойлер"],
    "wheel arch liner": ["подкалник"],
    "undertray": ["кора под двигател"],
    "fuel flap": ["капачка резервоар"],
    "indicator": ["мигач"],
    "turn signal": ["мигач"],
    "brake light": ["трети стоп"],
    "tail lamp": ["стоп"],
    "xenon ballast": ["баласт ксенон"],
    "cylinder head": ["цилиндрова глава", "глава двигател"],
    "injector": ["дюза", "дюзи"],
    "fuel injector": ["дюза", "дюзи"],
    "fuel pump": ["горивна помпа"],
    "high pressure pump": ["помпа високо налягане", "ГНП"],
    "water pump": ["водна помпа"],
    "oil pump": ["маслена помпа"],
    "egr valve": ["EGR клапан"],
    "throttle body": ["дроселова клапа"],
    "intake manifold": ["всмукателен колектор"],
    "exhaust manifold": ["изпускателен колектор"],
    "dpf": ["DPF", "филтър твърди частици"],
    "particulate filter": ["DPF", "филтър твърди частици"],
    "catalytic converter": ["катализатор"],
    "muffler": ["ауспух", "гърне"],
    "silencer": ["гърне", "ауспух"],
    "timing chain": ["ангренажна верига"],
    "flywheel": ["маховик", "двумасов маховик"],
    "clutch": ["съединител"],
    "ignition coil": ["бобина"],
    "oil cooler": ["маслен радиатор"],
    "radiator fan": ["перка", "вентилатор"],
    "cooling fan": ["перка", "вентилатор"],
    "expansion tank": ["разширителен съд"],
    "air filter box": ["кутия въздушен филтър"],
    "mass air flow sensor": ["дебитомер"],
    "engine mount": ["тампон двигател"],
    "ecu": ["компютър двигател"],
    "wiring harness": ["кабелна инсталация"],
    "battery": ["акумулатор"],
    "propshaft": ["кардан"],
    "prop shaft": ["кардан"],
    "driveshaft": ["полуоска"],
    "drive shaft": ["полуоска"],
    "cv axle": ["полуоска"],
    "differential": ["диференциал"],
    "transfer case": ["раздатка"],
    "gear selector": ["скоростен лост"],
    "gear lever": ["скоростен лост"],
    "wheel hub": ["главина"],
    "wheel bearing": ["лагер главина"],
    "steering knuckle": ["шенкел"],
    "coil spring": ["пружина"],
    "anti roll bar": ["стабилизираща щанга"],
    "sway bar": ["стабилизираща щанга"],
    "strut": ["амортисьор"],
    "front axle": ["преден мост"],
    "rear axle": ["заден мост"],
    "steering rack": ["кормилна рейка"],
    "power steering pump": ["хидравлична помпа"],
    "steering column": ["кормилна колона"],
    "brake pads": ["накладки"],
    "abs pump": ["ABS помпа"],
    "instrument cluster": ["километраж"],
    "speedometer": ["километраж"],
    "radio": ["радио"],
    "display": ["дисплей"],
    "navigation": ["навигация"],
    "climate control panel": ["управление климатик"],
    "blower motor": ["моторче парно"],
    "heater core": ["радиатор парно"],
    "ac compressor": ["компресор климатик"],
    "window switch": ["бутон стъкло"],
    "driver airbag": ["airbag волан"],
    "passenger airbag": ["airbag пасажер"],
    "seat belt": ["колан"],
    "centre console": ["конзола"],
    "center console": ["конзола"],
    "glovebox": ["жабка"],
    "key": ["ключ"],
    "key fob": ["ключ"],
    "reversing camera": ["камера задно виждане"],
    "rear camera": ["камера задно виждане"],
    "wiper motor": ["моторче чистачки"],
    "wiper arm": ["рамо чистачка"],
    "washer tank": ["казанче чистачки"],
    "horn": ["клаксон"],
    "fuel tank": ["резервоар"],
    # Suspension and steering
    "suspension": ["окачване"],
    "front suspension": ["предно окачване"],
    "rear suspension": ["задно окачване"],
    "spring": ["пружина"],
    "leaf spring": ["ресор", "листов ресор"],
    "air suspension": ["въздушно окачване"],
    "air spring": ["въздушна възглавница", "въздушен маншон"],
    "ball joint": ["шарнир", "долен шарнир"],
    "tie rod": ["кормилна щанга"],
    "track rod": ["кормилна щанга"],
    "tie rod end": ["кормилен накрайник"],
    "stabilizer": ["стабилизираща щанга"],
    "stabilizer link": ["животче", "биалетка"],
    "drop link": ["животче", "биалетка"],
    "trailing arm": ["надлъжен носач"],
    "wishbone": ["носач"],
    "bump stop": ["тампон"],
    "top mount": ["лагер на амортисьор", "тампон на амортисьор"],
    "strut mount": ["лагер на амортисьор", "тампон на амортисьор"],
    "shock mount": ["лагер на амортисьор", "тампон на амортисьор"],
}

# English part name -> Polish search terms (first one is the preferred term).
# A verified subset of the German/Bulgarian tables: the common body, lighting
# and mechanical parts. Missing keys simply yield no Polish query (translate_part
# returns []), so it is safe to grow this over time. Side/position words are left
# out of the stored terms on purpose (Polish inflects for gender: przedni/przednia/
# przednie, lewy/lewa/lewe); scoring still recognises every form via OPPOSITES.
PART_TRANSLATIONS_PL: dict[str, list[str]] = {
    "front bumper": ["zderzak przedni"],
    "rear bumper": ["zderzak tylny"],
    "bumper": ["zderzak"],
    "headlight": ["reflektor", "lampa przednia"],
    "headlamp": ["reflektor", "lampa przednia"],
    "tail light": ["lampa tylna"],
    "taillight": ["lampa tylna"],
    "tail lamp": ["lampa tylna"],
    "bonnet": ["maska"],
    "hood": ["maska"],
    "fender": ["błotnik"],
    "wing": ["błotnik"],
    "door": ["drzwi"],
    "mirror": ["lusterko"],
    "wing mirror": ["lusterko"],
    "door mirror": ["lusterko"],
    "side mirror": ["lusterko"],
    "mirror glass": ["wkład lusterka"],
    "radiator": ["chłodnica"],
    "condenser": ["chłodnica klimatyzacji", "skraplacz"],
    "grille": ["atrapa", "grill"],
    "kidney grille": ["atrapa", "grill"],
    "windscreen": ["szyba przednia", "szyba czołowa"],
    "windshield": ["szyba przednia", "szyba czołowa"],
    "airbag": ["poduszka powietrzna"],
    "steering wheel": ["kierownica"],
    "dashboard": ["deska rozdzielcza"],
    "seat": ["fotel"],
    "wheel": ["felga"],
    "rim": ["felga"],
    "engine": ["silnik"],
    "gearbox": ["skrzynia biegów"],
    "transmission": ["skrzynia biegów"],
    "turbo": ["turbosprężarka"],
    "turbocharger": ["turbosprężarka"],
    "starter": ["rozrusznik"],
    "alternator": ["alternator"],
    "control arm": ["wahacz"],
    "shock absorber": ["amortyzator"],
    "brake disc": ["tarcza hamulcowa"],
    "brake caliper": ["zacisk hamulcowy"],
    "exhaust": ["wydech", "tłumik"],
    "fog light": ["halogen", "światło przeciwmgielne"],
    "parking sensor": ["czujnik parkowania"],
    "intercooler": ["intercooler", "chłodnica powietrza"],
    "subframe": ["sanki silnika"],
    "bumper reinforcement": ["belka zderzaka"],
    "crash bar": ["belka zderzaka"],
    "front panel": ["pas przedni"],
    "radiator support": ["pas przedni"],
    "front end": ["pas przedni"],
    "tailgate": ["klapa bagażnika"],
    "boot lid": ["klapa bagażnika"],
    "trunk lid": ["klapa bagażnika"],
    "door handle": ["klamka"],
    "door lock": ["zamek drzwi"],
    "window regulator": ["podnośnik szyby"],
    "door panel": ["tapicerka drzwi", "boczek drzwi"],
    "door card": ["tapicerka drzwi", "boczek drzwi"],
    "side skirt": ["próg"],
    "rocker panel": ["próg"],
    "quarter panel": ["ćwiartka", "błotnik tylny"],
    "rear window": ["szyba tylna"],
    "side window": ["szyba boczna"],
    "sunroof": ["szyberdach"],
    "spoiler": ["spoiler"],
    "fuel flap": ["klapka wlewu paliwa"],
    "indicator": ["kierunkowskaz"],
    "turn signal": ["kierunkowskaz"],
    "brake light": ["światło stop"],
    "cylinder head": ["głowica"],
    "injector": ["wtryskiwacz"],
    "fuel injector": ["wtryskiwacz"],
    "fuel pump": ["pompa paliwa"],
    "high pressure pump": ["pompa wysokiego ciśnienia"],
    "water pump": ["pompa wody"],
    "oil pump": ["pompa oleju"],
    "egr valve": ["zawór EGR"],
    "throttle body": ["przepustnica"],
    "intake manifold": ["kolektor ssący"],
    "exhaust manifold": ["kolektor wydechowy"],
    "dpf": ["filtr cząstek stałych", "DPF"],
    "particulate filter": ["filtr cząstek stałych", "DPF"],
    "catalytic converter": ["katalizator"],
    "muffler": ["tłumik"],
    "silencer": ["tłumik"],
    "timing chain": ["łańcuch rozrządu"],
    "flywheel": ["koło zamachowe"],
    "clutch": ["sprzęgło"],
    "ignition coil": ["cewka zapłonowa"],
    "oil cooler": ["chłodnica oleju"],
    "radiator fan": ["wentylator chłodnicy"],
    "cooling fan": ["wentylator chłodnicy"],
    "expansion tank": ["zbiornik wyrównawczy"],
    "mass air flow sensor": ["przepływomierz"],
    "engine mount": ["poduszka silnika"],
    "ecu": ["sterownik silnika", "komputer"],
    "wiring harness": ["wiązka elektryczna"],
    "battery": ["akumulator"],
    "propshaft": ["wał napędowy"],
    "prop shaft": ["wał napędowy"],
    "driveshaft": ["półoś napędowa"],
    "drive shaft": ["półoś napędowa"],
    "fuel tank": ["zbiornik paliwa"],
    "horn": ["klakson"],
    "wiper motor": ["silnik wycieraczek"],
    "wiper arm": ["ramię wycieraczki"],
    "washer tank": ["zbiornik spryskiwacza"],
    # Suspension and steering
    "suspension": ["zawieszenie"],
    "front suspension": ["zawieszenie przednie"],
    "rear suspension": ["zawieszenie tylne"],
    "spring": ["sprężyna"],
    "coil spring": ["sprężyna"],
    "leaf spring": ["resor piórowy"],
    "air suspension": ["zawieszenie pneumatyczne"],
    "air spring": ["miech zawieszenia"],
    "strut": ["kolumna McPhersona", "amortyzator"],
    "ball joint": ["sworzeń wahacza"],
    "tie rod": ["drążek kierowniczy"],
    "track rod": ["drążek kierowniczy"],
    "tie rod end": ["końcówka drążka kierowniczego"],
    "stabilizer": ["stabilizator"],
    "anti roll bar": ["stabilizator"],
    "sway bar": ["stabilizator"],
    "stabilizer link": ["łącznik stabilizatora"],
    "drop link": ["łącznik stabilizatora"],
    "trailing arm": ["wahacz wzdłużny"],
    "wishbone": ["wahacz"],
    "bump stop": ["odbój"],
    "top mount": ["poduszka amortyzatora", "łożysko amortyzatora"],
    "strut mount": ["poduszka amortyzatora", "łożysko amortyzatora"],
    "shock mount": ["poduszka amortyzatora", "łożysko amortyzatora"],
    "rear axle": ["oś tylna", "tylny most"],
    "front axle": ["oś przednia"],
    "cv axle": ["półoś napędowa"],
    "wheel bearing": ["łożysko koła"],
    "wheel hub": ["piasta koła"],
    "steering rack": ["przekładnia kierownicza", "maglownica"],
}

PART_TRANSLATIONS = {"de": PART_TRANSLATIONS_DE, "bg": PART_TRANSLATIONS_BG, "pl": PART_TRANSLATIONS_PL}

# "Spare parts" words used for a broad vehicle query.
GENERIC_PARTS_WORD_DE = "Ersatzteile"
GENERIC_PARTS_WORD_BG = "части"
GENERIC_PARTS_WORD_PL = "części"

# Position words. If the query says one side and the listing says the opposite,
# that's a different part.
OPPOSITES: list[tuple[set[str], set[str]]] = [
    ({"front", "vorne", "vorn", "vorder", "avant", "przod", "przedni", "предна", "преден", "предни", "предно"},
     {"rear", "hinten", "heck", "arriere", "tył", "tylny", "задна", "заден", "задни", "задно"}),
    ({"left", "links", "gauche", "lewy", "lh", "лява", "ляв", "ляво", "леви"},
     {"right", "rechts", "droite", "prawy", "rh", "дясна", "десен", "дясно", "десни"}),
]

# Side words added to translated queries ("left headlight" -> "Scheinwerfer links").
# Bulgarian is left out of queries: the word changes with gender (ляв/лява/ляво), so
# a query with the wrong form would miss listings. Scoring still checks all forms.
SIDE_WORDS = {
    "left": {"de": "links"}, "lh": {"de": "links"},
    "right": {"de": "rechts"}, "rh": {"de": "rechts"},
}


def side_terms(part_name: str | None, language: str) -> list[str]:
    """Side words in the part name, translated into `language` (only where it is reliable)."""
    return [SIDE_WORDS[w][language] for w in sorted(words(part_name)) if language in SIDE_WORDS.get(w, {})]


# Left/right-hand drive. Only explicit phrases count: a UK seller can still sell LHD parts.
DRIVE_PHRASES = {
    "LHD": ["lhd", "left hand drive", "left-hand drive", "linkslenker", "ляв волан", "eu spec", "eu-version"],
    "RHD": ["rhd", "right hand drive", "right-hand drive", "rechtslenker", "десен волан", "uk spec",
            "uk-version", "uk version"],
}

# Parts that are usually different between LHD and RHD cars.
DRIVE_SENSITIVE_PARTS = {
    "headlight", "headlamp", "dashboard", "steering", "steering rack", "steering column", "pedal",
    "wiper", "windscreen", "windshield", "heater", "blower", "climate", "glovebox", "airbag",
    "brake booster", "master cylinder", "bulkhead", "fuse box", "instrument cluster",
}


def drive_mentioned(text: str | None) -> set[str]:
    """{"LHD"} / {"RHD"} if the text explicitly says so."""
    tf = fold(text)
    return {d for d, phrases in DRIVE_PHRASES.items()
            if any(re.search(r"(?<!\w)%s(?!\w)" % re.escape(fold(p)), tf) for p in phrases)}


def is_drive_sensitive(part_name: str | None) -> bool:
    name = fold(part_name)
    return any(re.search(r"(?<!\w)%s" % re.escape(p), name) for p in DRIVE_SENSITIVE_PARTS)


# Words that usually mean "accessory of the part" rather than the part itself.
# Penalized only when they are NOT part of what the user asked for.
ACCESSORY_WORDS = {
    "bracket", "holder", "mount", "clip", "clips", "screw", "bolt", "cover",
    "trim", "emblem", "badge", "sticker", "decal", "grille", "grill", "spoiler",
    "lip", "moulding", "molding", "seal", "gasket", "bulb", "cap", "plug",
    "sensor", "cable", "harness", "toy", "keyring", "manual",
    "halter", "halterung", "blende", "abdeckung", "leiste", "schraube",
    "zierleiste", "gitter", "kappe", "dichtung",
    "греда", "решетка", "решетки", "скоба", "скоби", "държач", "държачи", "лайсна", "лайсни",
    "капачка", "капачки", "основа", "сензор", "сензори", "уплътнение", "кука", "емблема", "спойлер",
}

# Words that mean "several parts sold together". Shown, but not as a clean match.
BUNDLE_WORDS = {
    "teilepaket", "paket", "set", "kit", "bundle", "konvolut", "frontpaket", "komplettpaket",
    "комплект", "пакет",
}

# "M Paket" / "M-Sport package" is a trim level, not a bundle of parts.
TRIM_PACKAGE_RE = re.compile(r"\b(?:m|amg|s|rs)[\s\-]?(?:paket|packet|package|пакет|sport\s*paket)\b", re.I)

KNOWN_MAKES = {
    "alfa romeo", "audi", "bmw", "citroen", "cupra", "dacia", "fiat", "ford",
    "honda", "hyundai", "jaguar", "jeep", "kia", "land rover", "lexus", "mazda",
    "mercedes", "mini", "mitsubishi", "nissan", "opel", "peugeot", "porsche",
    "renault", "seat", "skoda", "smart", "subaru", "suzuki", "tesla", "toyota",
    "vauxhall", "volkswagen", "vw", "volvo",
}

MAKE_ALIASES = {
    "volkswagen": {"vw", "volkswagen"},
    "vw": {"vw", "volkswagen"},
    "mercedes-benz": {"mercedes", "mercedes-benz", "benz", "mb"},
    "opel": {"opel", "vauxhall"},
    "vauxhall": {"opel", "vauxhall"},
    "bmw": {"bmw", "бмв"},
    "audi": {"audi", "ауди"},
    "mercedes": {"mercedes", "mercedes-benz", "benz", "mb", "мерцедес"},
}

# Common model name variants (lowercase). "3 series" listings in Germany say "3er".
MODEL_ALIASES = {
    "1 series": ["1er", "серия 1", "1 серия"], "2 series": ["2er", "серия 2", "2 серия"],
    "3 series": ["3er", "серия 3", "3 серия"], "4 series": ["4er", "серия 4", "4 серия"],
    "5 series": ["5er", "серия 5", "5 серия"], "6 series": ["6er"], "7 series": ["7er", "серия 7"],
    "8 series": ["8er"],
    "a class": ["a-klasse"], "b class": ["b-klasse"], "c class": ["c-klasse"],
    "e class": ["e-klasse"], "s class": ["s-klasse"], "glc": ["glc"],
}

# Condition words in listing text.
CONDITION_WORDS = {
    "used": {"used", "gebraucht", "occasion", "używany", "uzywany", "použitý",
             "употребяван", "употребявана", "употребявано", "употребявани"},
    "new": {"new", "neu", "fabrikneu", "neuf", "nowy", "nový", "нов", "нова", "ново", "нови"},
    "refurbished": {"refurbished", "generalüberholt", "aufbereitet", "reconditioned", "remanufactured"},
}

# Letters that start engine codes rather than chassis codes, per make
# (BMW engines are B47, N47, S58, M57... while chassis codes are E90, F30, G20).
ENGINE_CODE_LETTERS = {"bmw": "BNSM", "mini": "BNW"}

_CHASSIS_RE = re.compile(r"^[A-Z]{1,2}\d{2,3}$")


def fold(text: str | None) -> str:
    """Lowercase and fold German spelling variants so "Stoßfänger" == "stossfaenger"."""
    if not text:
        return ""
    text = text.lower().replace("ß", "ss")
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue")):
        text = text.replace(a, b)
    return text


def words(text: str | None) -> set[str]:
    return set(re.findall(r"[\w\-]+", fold(text)))


def chassis_codes(model: str | None) -> list[str]:
    """ "3 Series G20" -> ["G20"]. """
    return [t for t in re.split(r"[\s,/()]+", (model or "").upper()) if _CHASSIS_RE.match(t)]


def model_without_codes(model: str | None) -> str:
    codes = set(chassis_codes(model))
    return " ".join(t for t in (model or "").split() if t.upper() not in codes).strip()


def model_terms(model: str | None) -> list[str]:
    """Folded strings any of which indicates the model is mentioned."""
    terms: list[str] = [fold(c) for c in chassis_codes(model)]
    base = fold(model_without_codes(model))
    if base:
        terms.append(base)
        terms.extend(fold(a) for a in MODEL_ALIASES.get(base, []))
    return [t for t in dict.fromkeys(terms) if t]


def make_terms(make: str | None) -> set[str]:
    m = fold(make).strip()
    if not m:
        return set()
    return {fold(x) for x in MAKE_ALIASES.get(m, {m})}


def translate_part(part_name: str | None, language: str) -> list[str]:
    """Terms for an English part name in `language`. Exact key first, else longest key contained."""
    table = PART_TRANSLATIONS.get(language, {})
    name = (part_name or "").lower().strip()
    if not name:
        return []
    if name in table:
        return table[name]
    for key in sorted(table, key=len, reverse=True):
        if re.search(r"\b%s\b" % re.escape(key), name):
            return table[key]
    return []


def translate_part_de(part_name: str | None) -> list[str]:
    return translate_part(part_name, "de")


def translate_part_all(part_name: str | None) -> list[str]:
    """All known translations, used for matching listing text in any language."""
    return [t for lang in PART_TRANSLATIONS for t in translate_part(part_name, lang)]


def detect_condition(text: str | None) -> str | None:
    """Return "used" / "new" / "refurbished" when the text clearly says so."""
    # "като нова" / "wie neu" / "like new" describe a used part.
    w = words(re.sub(r"\b(?:като|wie|like)\s+\w+", " ", text or "", flags=re.I))
    for cond in ("refurbished", "used", "new"):  # refurbished before new ("generalüberholt")
        if w & {fold(x) for x in CONDITION_WORDS[cond]}:
            return cond
    return None


# Country names as they appear in listing locations, keyed by ISO code.
COUNTRY_NAMES = {
    "DE": {"germany", "deutschland"}, "AT": {"austria", "oesterreich"}, "GB": {"uk", "united kingdom"},
    "FR": {"france"}, "IT": {"italy", "italia"}, "ES": {"spain", "espana"}, "NL": {"netherlands"},
    "BE": {"belgium"}, "PL": {"poland", "polska"}, "CZ": {"czechia", "czech republic"},
    "LT": {"lithuania"}, "BG": {"bulgaria", "българия"},
}


def location_in_country(location: str | None, code: str | None) -> bool:
    if not location or not code:
        return False
    loc = fold(location)
    names = COUNTRY_NAMES.get(code.upper(), set()) | {code.lower()}
    return any(re.search(r"(?<!\w)%s(?!\w)" % re.escape(n), loc) for n in names)
