"""Curated local evidence seed for AstroLens V1.

The seed is intentionally compact. It provides enough reliable, provenance-rich
records to exercise the product contract without live archive fan-out.
"""

from datetime import UTC, datetime

from astrolens.core.enums import AccessStatus, BandFamily, CacheStatus, ReuseStatus
from astrolens.core.models import (
    Asset,
    CacheMeta,
    CelestialObject,
    Citation,
    Coordinates,
    CrossWavelengthNote,
    DataProduct,
    Fact,
    Observation,
    ReusePolicy,
    SourceReference,
    View,
    ViewScores,
)

RETRIEVED_AT = datetime(2026, 6, 30, tzinfo=UTC)


NASA_REUSE = ReusePolicy(
    id="reuse:nasa:general",
    status=ReuseStatus.USABLE_WITH_CREDIT,
    commercial_use="check_source_policy",
    credit_required=True,
    credit_text="NASA and partner mission/archive credit must be preserved.",
    policy_url="https://www.nasa.gov/nasa-brand-center/images-and-media/",
    notes=[
        "Do not imply NASA endorsement.",
        "Rights can vary for partner-contributed products; check the source record.",
    ],
)

ESA_REUSE = ReusePolicy(
    id="reuse:esa:general",
    status=ReuseStatus.CHECK_SOURCE_POLICY,
    commercial_use="check_source_policy",
    credit_required=True,
    credit_text="ESA and partner mission/archive credit must be preserved.",
    policy_url="https://www.esa.int/ESA_Multimedia/Terms_and_Conditions",
    notes=["Check source-specific credit and reuse policy before publication."],
)

UNKNOWN_REUSE = ReusePolicy(
    id="reuse:unknown",
    status=ReuseStatus.RESTRICTED_OR_UNKNOWN,
    commercial_use="check_source_policy",
    credit_required=True,
    credit_text="Credit and reuse policy unknown; follow the linked source.",
    policy_url="https://astrolens.local/policies/unknown",
    notes=["AstroLens could not determine source-specific reuse terms."],
)

REUSE_POLICIES = {policy.id: policy for policy in [NASA_REUSE, ESA_REUSE, UNKNOWN_REUSE]}

SOURCE_REFERENCES = {
    "simbad": SourceReference(
        name="SIMBAD",
        url="https://simbad.cds.unistra.fr/simbad/",
        retrieved_at=RETRIEVED_AT,
    ),
    "ned": SourceReference(
        name="NASA/IPAC Extragalactic Database",
        url="https://ned.ipac.caltech.edu/",
        retrieved_at=RETRIEVED_AT,
    ),
    "mast": SourceReference(
        name="MAST",
        url="https://archive.stsci.edu/",
        retrieved_at=RETRIEVED_AT,
    ),
    "irsa": SourceReference(
        name="NASA/IPAC IRSA",
        url="https://irsa.ipac.caltech.edu/",
        retrieved_at=RETRIEVED_AT,
    ),
    "skyview": SourceReference(
        name="NASA SkyView",
        url="https://skyview.gsfc.nasa.gov/",
        retrieved_at=RETRIEVED_AT,
    ),
    "heasarc": SourceReference(
        name="HEASARC",
        url="https://heasarc.gsfc.nasa.gov/",
        retrieved_at=RETRIEVED_AT,
    ),
    "chandra": SourceReference(
        name="Chandra Data Archive",
        url="https://cxc.harvard.edu/cda/",
        retrieved_at=RETRIEVED_AT,
    ),
    "ads": SourceReference(
        name="NASA ADS",
        url="https://ui.adsabs.harvard.edu/",
        retrieved_at=RETRIEVED_AT,
    ),
    "astrolens": SourceReference(
        name="astrolens:curated (ephemeris placeholder coordinates)",
        url=None,
        retrieved_at=RETRIEVED_AT,
    ),
}


def citation(source: str, title: str, url: str, credit: str | None = None) -> Citation:
    """Create a citation with a stable ID."""

    safe_title = (
        title.lower()
        .replace(" ", "_")
        .replace("/", "_")
        .replace(":", "")
        .replace("(", "")
        .replace(")", "")
    )
    return Citation(
        id=f"citation:{source.lower()}:{safe_title}",
        title=title,
        source=source,
        url=url,
        credit_text=credit,
        retrieved_at=RETRIEVED_AT,
    )


CITATIONS = {
    item.id: item
    for item in [
        citation(
            "SIMBAD",
            "SIMBAD astronomical object database",
            "https://simbad.cds.unistra.fr/simbad/",
            "CDS/SIMBAD",
        ),
        citation(
            "NED",
            "NASA/IPAC Extragalactic Database",
            "https://ned.ipac.caltech.edu/",
            "NASA/IPAC Extragalactic Database",
        ),
        citation("MAST", "MAST archive", "https://archive.stsci.edu/", "MAST/STScI"),
        citation(
            "IRSA", "NASA/IPAC IRSA archive", "https://irsa.ipac.caltech.edu/", "NASA/IPAC IRSA"
        ),
        citation(
            "SkyView",
            "NASA SkyView virtual observatory",
            "https://skyview.gsfc.nasa.gov/",
            "NASA SkyView",
        ),
        citation(
            "HEASARC", "HEASARC archive", "https://heasarc.gsfc.nasa.gov/", "NASA/GSFC HEASARC"
        ),
        citation("Chandra", "Chandra Data Archive", "https://cxc.harvard.edu/cda/", "NASA/CXC"),
        citation(
            "ADS", "NASA ADS bibliographic service", "https://ui.adsabs.harvard.edu/", "NASA ADS"
        ),
    ]
}


def object_record(
    slug: str,
    name: str,
    aliases: list[str],
    object_type: str,
    ra: float,
    dec: float,
    identity: str,
    *,
    ephemeris_object: bool = False,
) -> CelestialObject:
    """Create a curated object record."""

    return CelestialObject(
        id=f"astro:object:{slug}",
        name=name,
        aliases=aliases,
        type=object_type,
        coordinates=Coordinates(ra_deg=ra, dec_deg=dec),
        identity_sources=[SOURCE_REFERENCES[identity]],
        ephemeris_object=ephemeris_object,
    )


def ephemeris_record(slug: str, name: str, object_type: str) -> CelestialObject:
    """Create a solar-system record whose (0, 0) coordinates are placeholders."""

    return object_record(
        slug,
        name,
        [],
        object_type,
        0.0,
        0.0,
        "astrolens",
        ephemeris_object=True,
    )


OBJECTS = [
    object_record(
        "m87",
        "M87",
        ["Messier 87", "NGC 4486", "Virgo A"],
        "giant elliptical galaxy",
        187.70593,
        12.39112,
        "ned",
    ),
    object_record(
        "crab_nebula",
        "Crab Nebula",
        ["M1", "Messier 1", "NGC 1952"],
        "supernova remnant",
        83.63308,
        22.01450,
        "simbad",
    ),
    object_record(
        "orion_nebula",
        "Orion Nebula",
        ["M42", "Messier 42", "NGC 1976"],
        "star-forming nebula",
        83.82208,
        -5.39111,
        "simbad",
    ),
    object_record(
        "andromeda_galaxy",
        "Andromeda Galaxy",
        ["M31", "Messier 31", "NGC 224"],
        "spiral galaxy",
        10.68471,
        41.26875,
        "ned",
    ),
    object_record(
        "pillars_of_creation",
        "Pillars of Creation",
        ["Eagle Nebula pillars", "M16 pillars"],
        "star-forming structure",
        274.70000,
        -13.81667,
        "simbad",
    ),
    object_record(
        "cassiopeia_a",
        "Cassiopeia A",
        ["Cas A", "3C 461"],
        "supernova remnant",
        350.85000,
        58.81500,
        "simbad",
    ),
    object_record(
        "sagittarius_a_star",
        "Sagittarius A*",
        ["Sgr A*", "Galactic Center"],
        "compact radio source",
        266.41683,
        -29.00781,
        "simbad",
    ),
    object_record(
        "carina_nebula",
        "Carina Nebula",
        ["NGC 3372", "Eta Carinae Nebula"],
        "star-forming nebula",
        161.26500,
        -59.68400,
        "simbad",
    ),
    object_record(
        "sombrero_galaxy",
        "Sombrero Galaxy",
        ["M104", "Messier 104", "NGC 4594"],
        "spiral galaxy",
        189.99763,
        -11.62305,
        "ned",
    ),
    object_record(
        "whirlpool_galaxy",
        "Whirlpool Galaxy",
        ["M51", "Messier 51", "NGC 5194"],
        "interacting spiral galaxy",
        202.46958,
        47.19525,
        "ned",
    ),
    object_record(
        "horsehead_nebula",
        "Horsehead Nebula",
        ["Barnard 33", "B33"],
        "dark nebula",
        85.25000,
        -2.45833,
        "simbad",
    ),
    object_record(
        "ring_nebula",
        "Ring Nebula",
        ["M57", "Messier 57", "NGC 6720"],
        "planetary nebula",
        283.39620,
        33.02920,
        "simbad",
    ),
    object_record(
        "eagle_nebula",
        "Eagle Nebula",
        ["M16", "Messier 16", "NGC 6611"],
        "star-forming nebula",
        274.70000,
        -13.80670,
        "simbad",
    ),
    object_record(
        "tarantula_nebula",
        "Tarantula Nebula",
        ["30 Doradus", "NGC 2070"],
        "star-forming region",
        84.67620,
        -69.10060,
        "simbad",
    ),
    object_record(
        "centaurus_a",
        "Centaurus A",
        ["NGC 5128", "Cen A"],
        "active galaxy",
        201.36510,
        -43.01910,
        "ned",
    ),
    object_record(
        "eta_carinae",
        "Eta Carinae",
        ["Eta Car", "HD 93308"],
        "massive stellar system",
        161.26480,
        -59.68440,
        "simbad",
    ),
    object_record(
        "cartwheel_galaxy",
        "Cartwheel Galaxy",
        ["ESO 350-40"],
        "ring galaxy",
        9.42080,
        -33.71690,
        "ned",
    ),
    object_record(
        "antennae_galaxies",
        "Antennae Galaxies",
        ["NGC 4038", "NGC 4039"],
        "interacting galaxies",
        180.47380,
        -18.86760,
        "ned",
    ),
    object_record(
        "stephans_quintet",
        "Stephan's Quintet",
        ["HCG 92"],
        "galaxy group",
        339.01400,
        33.97700,
        "ned",
    ),
    object_record(
        "helix_nebula",
        "Helix Nebula",
        ["NGC 7293", "Caldwell 63"],
        "planetary nebula",
        337.41000,
        -20.83700,
        "simbad",
    ),
    object_record(
        "triangulum_galaxy",
        "Triangulum Galaxy",
        ["M33", "Messier 33", "NGC 598"],
        "spiral galaxy",
        23.46210,
        30.66020,
        "ned",
    ),
    object_record(
        "large_magellanic_cloud",
        "Large Magellanic Cloud",
        ["LMC"],
        "satellite galaxy",
        80.89390,
        -69.75610,
        "ned",
    ),
    object_record(
        "small_magellanic_cloud",
        "Small Magellanic Cloud",
        ["SMC"],
        "satellite galaxy",
        13.15830,
        -72.80030,
        "ned",
    ),
    object_record("ngc_1300", "NGC 1300", [], "barred spiral galaxy", 49.92080, -19.41110, "ned"),
    object_record(
        "ngc_253", "NGC 253", ["Sculptor Galaxy"], "starburst galaxy", 11.88800, -25.28820, "ned"
    ),
    object_record("ngc_1365", "NGC 1365", [], "barred spiral galaxy", 53.40150, -36.14040, "ned"),
    object_record(
        "ngc_4258", "NGC 4258", ["M106", "Messier 106"], "spiral galaxy", 184.73960, 47.30390, "ned"
    ),
    object_record("3c_273", "3C 273", [], "quasar", 187.27790, 2.05240, "ned"),
    object_record("cygnus_a", "Cygnus A", ["3C 405"], "radio galaxy", 299.86820, 40.73390, "ned"),
    object_record(
        "vela_supernova_remnant",
        "Vela Supernova Remnant",
        ["Vela SNR"],
        "supernova remnant",
        128.83600,
        -45.17600,
        "simbad",
    ),
    object_record(
        "bullet_cluster",
        "Bullet Cluster",
        ["1E 0657-56"],
        "galaxy cluster",
        104.62500,
        -55.95000,
        "ned",
    ),
    object_record(
        "smacs_0723",
        "SMACS 0723",
        ["SMACS J0723.3-7327"],
        "galaxy cluster",
        110.83750,
        -73.45420,
        "ned",
    ),
    object_record(
        "abell_2744",
        "Abell 2744",
        ["Pandora's Cluster"],
        "galaxy cluster",
        3.58630,
        -30.40020,
        "ned",
    ),
    object_record(
        "omega_centauri",
        "Omega Centauri",
        ["NGC 5139"],
        "globular cluster",
        201.69700,
        -47.47950,
        "simbad",
    ),
    object_record(
        "pleiades",
        "Pleiades",
        ["M45", "Seven Sisters"],
        "open star cluster",
        56.75000,
        24.11670,
        "simbad",
    ),
    object_record(
        "rosette_nebula",
        "Rosette Nebula",
        ["NGC 2237"],
        "emission nebula",
        97.98580,
        4.94280,
        "simbad",
    ),
    object_record(
        "lagoon_nebula",
        "Lagoon Nebula",
        ["M8", "Messier 8"],
        "star-forming nebula",
        270.90420,
        -24.38670,
        "simbad",
    ),
    object_record(
        "trifid_nebula",
        "Trifid Nebula",
        ["M20", "Messier 20"],
        "star-forming nebula",
        270.67500,
        -23.03000,
        "simbad",
    ),
    object_record(
        "veil_nebula",
        "Veil Nebula",
        ["Cygnus Loop"],
        "supernova remnant",
        312.50000,
        30.70000,
        "simbad",
    ),
    object_record(
        "north_america_nebula",
        "North America Nebula",
        ["NGC 7000"],
        "emission nebula",
        314.70000,
        44.33300,
        "simbad",
    ),
    object_record(
        "pinwheel_galaxy",
        "Pinwheel Galaxy",
        ["M101", "Messier 101", "NGC 5457"],
        "spiral galaxy",
        210.80230,
        54.34890,
        "ned",
    ),
    object_record(
        "black_eye_galaxy",
        "Black Eye Galaxy",
        ["M64", "NGC 4826"],
        "spiral galaxy",
        194.18210,
        21.68310,
        "ned",
    ),
    object_record(
        "sunflower_galaxy",
        "Sunflower Galaxy",
        ["M63", "NGC 5055"],
        "spiral galaxy",
        198.95540,
        42.02930,
        "ned",
    ),
    object_record(
        "omega_nebula",
        "Omega Nebula",
        ["M17", "Swan Nebula"],
        "star-forming nebula",
        275.19600,
        -16.17100,
        "simbad",
    ),
    ephemeris_record("jupiter", "Jupiter", "solar system planet"),
    ephemeris_record("saturn", "Saturn", "solar system planet"),
    ephemeris_record("uranus", "Uranus", "solar system planet"),
    ephemeris_record("neptune", "Neptune", "solar system planet"),
    ephemeris_record("titan", "Titan", "moon"),
    ephemeris_record("io", "Io", "moon"),
]

NSSDC_CITATION = Citation(
    id="citation:nssdc:planetary-fact-sheet",
    title="NASA NSSDC Planetary Fact Sheets",
    source="NASA NSSDC",
    url="https://nssdc.gsfc.nasa.gov/planetary/factsheet/",
    credit_text="NASA Goddard Space Flight Center, NSSDCA",
)


def _planetary_fact(
    slug: str,
    quantity_kind: str,
    claim: str,
    *,
    value: float | None = None,
    unit: str | None = None,
    scale_comparison: str | None = None,
) -> Fact:
    return Fact(
        id=f"fact:{slug}:{quantity_kind}",
        entity_type="object",
        entity_id=f"astro:object:{slug}",
        claim=claim,
        scope="curated_planetary_fact",
        confidence=0.9,
        citation_ids=[NSSDC_CITATION.id],
        value=value,
        unit=unit,
        quantity_kind=quantity_kind,
        source_fields=["nssdc.planetary_fact_sheet"],
        scale_comparison=scale_comparison,
    )


# Solar-system bodies have no SIMBAD records; these values come from the NASA
# NSSDC planetary fact sheets and satisfy the numeric-fact traceability rule.
CURATED_OBJECT_FACTS: dict[str, list[Fact]] = {
    "astro:object:jupiter": [
        _planetary_fact(
            "jupiter",
            "diameter",
            "Jupiter's equatorial diameter is about 142,984 km.",
            value=142_984.0,
            unit="km",
            scale_comparison="about 11 times the diameter of Earth",
        ),
        _planetary_fact(
            "jupiter",
            "distance_from_sun",
            "Jupiter orbits about 5.2 times farther from the Sun than Earth.",
            value=5.2,
            unit="AU",
        ),
        _planetary_fact(
            "jupiter",
            "orbital_period",
            "A Jupiter year lasts about 11.9 Earth years.",
            value=11.9,
            unit="Earth years",
        ),
        _planetary_fact(
            "jupiter",
            "mass",
            "Jupiter's mass is about 318 times Earth's, more than all other "
            "planets combined.",
            value=318.0,
            unit="Earth masses",
        ),
    ],
    "astro:object:saturn": [
        _planetary_fact(
            "saturn",
            "diameter",
            "Saturn's equatorial diameter is about 120,536 km.",
            value=120_536.0,
            unit="km",
            scale_comparison="about 9.4 times the diameter of Earth",
        ),
        _planetary_fact(
            "saturn",
            "distance_from_sun",
            "Saturn orbits about 9.6 times farther from the Sun than Earth.",
            value=9.58,
            unit="AU",
        ),
        _planetary_fact(
            "saturn",
            "orbital_period",
            "A Saturn year lasts about 29.4 Earth years.",
            value=29.4,
            unit="Earth years",
        ),
        _planetary_fact(
            "saturn",
            "density",
            "Saturn's mean density is about 687 kg per cubic meter.",
            value=687.0,
            unit="kg/m^3",
            scale_comparison="less dense than water",
        ),
    ],
    "astro:object:uranus": [
        _planetary_fact(
            "uranus",
            "diameter",
            "Uranus's equatorial diameter is about 51,118 km.",
            value=51_118.0,
            unit="km",
            scale_comparison="about 4 times the diameter of Earth",
        ),
        _planetary_fact(
            "uranus",
            "distance_from_sun",
            "Uranus orbits about 19.2 times farther from the Sun than Earth.",
            value=19.2,
            unit="AU",
        ),
        _planetary_fact(
            "uranus",
            "axial_tilt",
            "Uranus's rotation axis is tilted about 97.8 degrees, so it "
            "effectively orbits on its side.",
            value=97.8,
            unit="degrees",
        ),
    ],
    "astro:object:neptune": [
        _planetary_fact(
            "neptune",
            "diameter",
            "Neptune's equatorial diameter is about 49,528 km.",
            value=49_528.0,
            unit="km",
            scale_comparison="about 3.9 times the diameter of Earth",
        ),
        _planetary_fact(
            "neptune",
            "distance_from_sun",
            "Neptune orbits about 30 times farther from the Sun than Earth.",
            value=30.1,
            unit="AU",
        ),
        _planetary_fact(
            "neptune",
            "orbital_period",
            "A Neptune year lasts about 164.8 Earth years.",
            value=164.8,
            unit="Earth years",
        ),
    ],
    "astro:object:titan": [
        _planetary_fact(
            "titan",
            "diameter",
            "Titan's diameter is about 5,150 km, larger than the planet Mercury.",
            value=5_150.0,
            unit="km",
            scale_comparison="larger than the planet Mercury",
        ),
        _planetary_fact(
            "titan",
            "orbital_period",
            "Titan orbits Saturn about every 15.9 Earth days.",
            value=15.9,
            unit="Earth days",
        ),
        _planetary_fact(
            "titan",
            "surface_pressure",
            "Titan's thick nitrogen atmosphere has a surface pressure about 1.5 "
            "times Earth's.",
            value=1.5,
            unit="bar",
        ),
    ],
    "astro:object:io": [
        _planetary_fact(
            "io",
            "diameter",
            "Io's diameter is about 3,643 km, slightly larger than Earth's Moon.",
            value=3_643.0,
            unit="km",
            scale_comparison="slightly larger than Earth's Moon",
        ),
        _planetary_fact(
            "io",
            "orbital_period",
            "Io orbits Jupiter about every 1.8 Earth days.",
            value=1.77,
            unit="Earth days",
        ),
    ],
}


BAND_NOTES = {
    BandFamily.VISIBLE: CrossWavelengthNote(
        band_family=BandFamily.VISIBLE,
        general_meaning=(
            "Visible-light views often trace stars, glowing gas, dust lanes, "
            "and shapes closer to what optical telescopes record."
        ),
        confidence=0.82,
    ),
    BandFamily.INFRARED: CrossWavelengthNote(
        band_family=BandFamily.INFRARED,
        general_meaning=(
            "Infrared views often reveal cooler material, dust-obscured regions, "
            "embedded stars, or redshifted distant light."
        ),
        confidence=0.82,
    ),
    BandFamily.XRAY: CrossWavelengthNote(
        band_family=BandFamily.XRAY,
        general_meaning=(
            "X-ray views often trace very energetic environments such as hot gas, "
            "shocks, compact objects, and accretion."
        ),
        confidence=0.82,
    ),
    BandFamily.RADIO: CrossWavelengthNote(
        band_family=BandFamily.RADIO,
        general_meaning=(
            "Radio views often trace jets, cold gas, magnetic fields, and structures "
            "invisible in ordinary optical images."
        ),
        confidence=0.82,
    ),
    BandFamily.MILLIMETER: CrossWavelengthNote(
        band_family=BandFamily.MILLIMETER,
        general_meaning=(
            "Millimeter views often trace the coldest dust, dense molecular gas, and "
            "foregrounds of the cosmic microwave background."
        ),
        confidence=0.82,
    ),
    BandFamily.GAMMA: CrossWavelengthNote(
        band_family=BandFamily.GAMMA,
        general_meaning=(
            "Gamma-ray views often trace the most violent particle acceleration, such "
            "as pulsars, blazar jets, and supernova shocks."
        ),
        confidence=0.82,
    ),
}


def _source_for_band(band: BandFamily) -> tuple[str, str, str, str, str]:
    if band == BandFamily.VISIBLE:
        return ("MAST", "Hubble Space Telescope", "HST imaging", "mast", "reuse:nasa:general")
    if band == BandFamily.INFRARED:
        return (
            "IRSA",
            "Spitzer/WISE/JWST context",
            "infrared survey",
            "irsa",
            "reuse:nasa:general",
        )
    if band == BandFamily.XRAY:
        return ("Chandra", "Chandra X-ray Observatory", "ACIS", "chandra", "reuse:nasa:general")
    if band == BandFamily.RADIO:
        return ("SkyView", "Radio survey composite", "survey", "skyview", "reuse:nasa:general")
    return ("SkyView", "Survey composite", "survey", "skyview", "reuse:unknown")


def make_view(
    obj: CelestialObject, band: BandFamily, overall: float
) -> tuple[Observation, DataProduct, Asset, View, Fact]:
    """Create a compact curated evidence view for a seed object."""

    source_archive, facility, instrument, source_key, reuse_id = _source_for_band(band)
    slug = obj.id.rsplit(":", maxsplit=1)[-1]
    band_value = str(band)
    obs_id = f"obs:{source_archive.lower()}:{slug}:{band_value}"
    product_id = f"product:{source_archive.lower()}:{slug}:{band_value}:preview"
    asset_id = f"asset:{slug}:{band_value}:preview"
    view_id = f"view:{slug}:{band_value}"
    source = SOURCE_REFERENCES[source_key]
    source_record_url = str(source.url)
    citation_id = next(
        c.id
        for c in CITATIONS.values()
        if c.source == source_archive or c.source == source.name.split()[0]
    )
    cited = CITATIONS[citation_id]

    observation = Observation(
        id=obs_id,
        object_id=obj.id,
        source_archive=source_archive,
        facility=facility,
        instrument=instrument,
        band_family=band,
        access_status=AccessStatus.PUBLIC,
        source_url=source_record_url,
        source_record_id=f"{source_archive.lower()}:{slug}:{band_value}",
        raw_metadata={"seed": True, "object_name": obj.name},
    )
    product = DataProduct(
        id=product_id,
        observation_id=obs_id,
        product_type="preview",
        file_format="html",
        calibration_level="generated_or_archive_preview",
        download_url=source_record_url,
        preview_url=source_record_url,
        file_size_mb=0.0,
        renderability_score=0.8,
        source_record_id=observation.source_record_id,
        raw_metadata={"seed": True, "source": source_archive},
    )
    asset = Asset(
        id=asset_id,
        source_product_ids=[product_id],
        format="external_preview",
        width=1920,
        height=1080,
        asset_url=source_record_url,
        thumbnail_url=source_record_url,
        false_color=band != BandFamily.VISIBLE,
        processing_note=(
            "Curated AstroLens seed pointer to public archive or generated survey preview."
        ),
        credit_text=REUSE_POLICIES[reuse_id].credit_text,
        reuse_policy_id=reuse_id,
        citations=[cited],
    )
    fact = Fact(
        id=f"fact:{slug}:{band_value}:general",
        entity_type="view",
        entity_id=view_id,
        claim=BAND_NOTES.get(band, BAND_NOTES[BandFamily.VISIBLE]).general_meaning,
        scope="general_wavelength_interpretation",
        confidence=0.82,
        citation_ids=[cited.id],
    )
    view = View(
        id=view_id,
        label=f"{obj.name} {band_value} evidence",
        band_family=band,
        facility=facility,
        instrument=instrument,
        source_archive=source_archive,
        asset=asset,
        raw_products=[product],
        facts=[fact],
        reuse=REUSE_POLICIES[reuse_id],
        citations=[cited],
        caveats=[
            "Curated seed evidence; inspect raw archive links for source-specific details.",
            "Colors, resolution, and observation dates can differ across wavelength views.",
        ],
        scores=ViewScores(
            object_match=0.9,
            public_access=1.0,
            asset_availability=0.8,
            preview_quality=0.75,
            science_ready=0.75,
            provenance_quality=0.85,
            citation_quality=0.85,
            renderability=0.7,
            source_reliability=0.8,
            overall=overall,
        ),
    )
    return observation, product, asset, view, fact


DETAILED_OBJECT_BANDS = {
    "astro:object:m87": [BandFamily.VISIBLE, BandFamily.XRAY, BandFamily.RADIO],
    "astro:object:crab_nebula": [
        BandFamily.VISIBLE,
        BandFamily.INFRARED,
        BandFamily.XRAY,
        BandFamily.RADIO,
    ],
    "astro:object:orion_nebula": [BandFamily.VISIBLE, BandFamily.INFRARED],
    "astro:object:andromeda_galaxy": [BandFamily.VISIBLE, BandFamily.INFRARED, BandFamily.XRAY],
    "astro:object:pillars_of_creation": [BandFamily.VISIBLE, BandFamily.INFRARED],
    "astro:object:cassiopeia_a": [
        BandFamily.VISIBLE,
        BandFamily.INFRARED,
        BandFamily.XRAY,
        BandFamily.RADIO,
    ],
    "astro:object:sagittarius_a_star": [BandFamily.INFRARED, BandFamily.XRAY, BandFamily.RADIO],
    "astro:object:carina_nebula": [BandFamily.VISIBLE, BandFamily.INFRARED],
    "astro:object:sombrero_galaxy": [BandFamily.VISIBLE, BandFamily.INFRARED],
    "astro:object:whirlpool_galaxy": [BandFamily.VISIBLE, BandFamily.INFRARED, BandFamily.XRAY],
}


OBSERVATIONS: list[Observation] = []
PRODUCTS: list[DataProduct] = []
ASSETS: list[Asset] = []
VIEWS: list[View] = []
FACTS: list[Fact] = []

for seeded_object in OBJECTS:
    bands = DETAILED_OBJECT_BANDS.get(seeded_object.id, [BandFamily.VISIBLE])
    for index, seeded_band in enumerate(bands):
        observation, product, asset, view, fact = make_view(
            seeded_object,
            seeded_band,
            overall=max(0.55, 0.92 - (index * 0.04)),
        )
        OBSERVATIONS.append(observation)
        PRODUCTS.append(product)
        ASSETS.append(asset)
        VIEWS.append(view)
        FACTS.append(fact)

DEFAULT_CACHE = CacheMeta(status=CacheStatus.HIT, refreshed_at=RETRIEVED_AT, stale=False)
