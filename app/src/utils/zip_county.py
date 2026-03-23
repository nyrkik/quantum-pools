"""Zip code to county lookup for Sacramento metro area."""

# Sacramento metro area zip-to-county mapping
# Extend as service area grows
ZIP_COUNTY: dict[str, str] = {
    # Sacramento County
    "95608": "Sacramento", "95610": "Sacramento", "95621": "Sacramento",
    "95624": "Sacramento", "95628": "Sacramento", "95630": "Sacramento",
    "95632": "Sacramento", "95638": "Sacramento", "95655": "Sacramento",
    "95660": "Sacramento", "95662": "Sacramento", "95670": "Sacramento",
    "95673": "Sacramento", "95683": "Sacramento", "95693": "Sacramento",
    "95742": "Sacramento", "95757": "Sacramento", "95758": "Sacramento",
    "95811": "Sacramento", "95812": "Sacramento", "95814": "Sacramento",
    "95815": "Sacramento", "95816": "Sacramento", "95817": "Sacramento",
    "95818": "Sacramento", "95819": "Sacramento", "95820": "Sacramento",
    "95821": "Sacramento", "95822": "Sacramento", "95823": "Sacramento",
    "95824": "Sacramento", "95825": "Sacramento", "95826": "Sacramento",
    "95827": "Sacramento", "95828": "Sacramento", "95829": "Sacramento",
    "95830": "Sacramento", "95831": "Sacramento", "95832": "Sacramento",
    "95833": "Sacramento", "95834": "Sacramento", "95835": "Sacramento",
    "95836": "Sacramento", "95837": "Sacramento", "95838": "Sacramento",
    "95841": "Sacramento", "95842": "Sacramento", "95843": "Sacramento",
    "95864": "Sacramento",
    # Placer County
    "95602": "Placer", "95603": "Placer", "95604": "Placer",
    "95648": "Placer", "95650": "Placer", "95661": "Placer",
    "95663": "Placer", "95677": "Placer", "95678": "Placer",
    "95681": "Placer", "95713": "Placer", "95722": "Placer",
    "95736": "Placer", "95746": "Placer", "95747": "Placer",
    "95765": "Placer",
    # El Dorado County
    "95667": "El Dorado", "95672": "El Dorado", "95682": "El Dorado",
    "95762": "El Dorado",
    # Yolo County
    "95605": "Yolo", "95616": "Yolo", "95618": "Yolo",
    "95691": "Yolo", "95695": "Yolo", "95776": "Yolo",
    # Sutter County
    "95991": "Sutter", "95993": "Sutter",
    # Yuba County
    "95901": "Yuba", "95903": "Yuba",
    # San Joaquin County
    "95206": "San Joaquin", "95209": "San Joaquin", "95210": "San Joaquin",
    "95212": "San Joaquin", "95219": "San Joaquin", "95240": "San Joaquin",
}


def get_county(zip_code: str) -> str | None:
    """Return county name for a zip code, or None if unknown."""
    return ZIP_COUNTY.get(zip_code.strip()[:5]) if zip_code else None
