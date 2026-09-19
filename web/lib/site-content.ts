export const NAV = [
  {
    label: "Solutions",
    href: "/solutions",
    blurb: "One package: climb, observe, report, return.",
    links: [
      ["The flight loop", "/solutions#loop", "Four steps, each earned before the next."],
      ["Float north star", "/solutions#float", "Persistent observation from 20 km."],
    ],
  },
  {
    label: "Applications",
    href: "/applications",
    blurb: "Where the view from 20 km is the product.",
    links: [
      ["Environment", "/applications#environment", "Fire, coast, and watershed at regional scale."],
      ["Emergency response", "/applications#emergency-response", "A picture when the ground is dark."],
      ["Maritime", "/applications#maritime", "A five-hundred-kilometre horizon."],
      ["All six areas", "/applications", "Agriculture, energy, science."],
    ],
  },
  {
    label: "Commitments",
    href: "/commitments",
    blurb: "Evidence before claims, without exception.",
    links: [
      ["The flight package", "/commitments#interface", "The S0-A bench and chamber gate."],
      ["Exit criteria", "/commitments#interface", "Targets, labelled as targets."],
      ["Design rules", "/commitments#rules", "What may be published, and when."],
    ],
  },
  {
    label: "Company",
    href: "/company",
    blurb: "Manufacturer and operator, one team.",
    links: [
      ["Structure", "/company#structure", "Two roles, no wall between them."],
      ["Programme gates", "/company#program", "S0-A through S0-C."],
      ["What changed recently", "/resources#news", "Each entry links to the change itself."],
    ],
  },
  {
    label: "Careers",
    href: "/careers",
    blurb: "Small, physical, unglamorous by design.",
    links: [
      ["What we look for", "/careers#roles", "Envelope, avionics, test, modelling."],
      ["How to apply", "/careers#apply", "The repository is the front door."],
    ],
  },
] as const;

export const REPO_URL = "https://github.com/0xSoftBoi/aiur";

export const APPLICATIONS = [
  {
    id: "01",
    slug: "environment",
    accent: "#5d9b6d",
    title: "Environment",
    copy:
      "Fire perimeter, smoke, coastline, and watershed observed at regional scale, on a cadence a launch decides rather than an orbit.",
  },
  {
    id: "02",
    slug: "emergency-response",
    accent: "#e8442b",
    title: "Emergency response",
    copy:
      "A picture of a whole region within hours of a launch, when ground infrastructure is degraded or absent and the satellite pass is tomorrow.",
  },
  {
    id: "03",
    slug: "agriculture",
    accent: "#c8823a",
    title: "Agriculture",
    copy:
      "Crop condition across a district in one flight, at a ground sample distance that separates a field's rows from its headland.",
  },
  {
    id: "04",
    slug: "energy",
    accent: "#ff6428",
    title: "Energy",
    copy:
      "Transmission corridors, pipeline rights-of-way, and remote sites covered end to end from a single ascent, without a crew convoy.",
  },
  {
    id: "05",
    slug: "maritime",
    accent: "#3f8fa8",
    title: "Maritime",
    copy:
      "Coastal domain awareness from a horizon five hundred kilometres away, from a package that costs less than one patrol sortie.",
  },
  {
    id: "06",
    slug: "science",
    accent: "#7a7fa6",
    title: "Science and atmosphere",
    copy:
      "In-situ stratospheric sampling alongside imaging: temperature, pressure, and the aerosol column the ground never sees directly.",
  },
] as const;

export const SYSTEM_LOOP = [
  {
    index: "01",
    title: "CLIMB",
    copy: "A sub-kilogram package under a helium balloon reaches 20 km in about an hour.",
  },
  {
    index: "02",
    title: "OBSERVE",
    copy: "Geotagged frames over a ten-kilometre swath, with a five-hundred-kilometre horizon in view.",
  },
  {
    index: "03",
    title: "REPORT",
    copy: "Thumbnails downlinked in flight, so a lost package does not lose the whole record.",
  },
  {
    index: "04",
    title: "RETURN",
    copy: "Termination on its own power, a parachute drop-tested to five metres a second, and a predicted landing.",
  },
] as const;

/** Mirrors the S0-A gate in aiur/loop_graph.py. Do not soften. */
export const BENCH_GATE = [
  ["≤1.814 KG", "PACKAGE MASS / 4 LB CEILING"],
  ["≥3 H", "COLD SOAK / ≤ −55 °C"],
  ["0", "FUNCTIONAL DROPOUTS / SOAK"],
  ["≥100", "STORED CAPTURES / IMAGING CHAIN"],
  ["10 + 0", "TERMINATION TRIALS / FAILURES"],
  ["≤5 M/S", "DROP-TESTED DESCENT"],
] as const;

export const COMPANY = [
  {
    role: "Manufacturer",
    title: "We build the package",
    copy:
      "Enclosure, imager, trackers, termination, and parachute are designed in the open, budgeted in an executable model, and built to a published allocation.",
    facts: [
      ["1", "ACTIVE ARTICLE / STRATO-P0"],
      ["850 G", "BASELINE PACKAGE ALLOCATION"],
    ],
  },
  {
    role: "Operator",
    title: "We fly the loop",
    copy:
      "The same team runs the chamber, the tether, and the free flight, so the operating record and the design record are one record.",
    facts: [
      ["3", "PROGRAM GATES / S0-A → S0-C"],
      ["100%", "PUBLIC ENGINEERING LOG"],
    ],
  },
] as const;

export const PROGRAM = [
  ["S0-A", "BENCH + COLD CHAMBER", "ACTIVE", "Mass, cold soak, imaging chain, termination, drop test"],
  ["S0-B", "TETHERED ASCENT", "LOCKED", "Earn the air only after the chamber gate"],
  ["S0-C", "STRATOSPHERIC SOUNDING", "LOCKED", "Two free flights, one configuration, ≥ 20 km"],
  ["S1", "PERSISTENT FLOAT", "GATED", "A fixed-volume envelope, only once S0-C is boring"],
] as const;

export const NEWS = [
  {
    date: "September 2026",
    tag: "Program",
    title: "Programme re-pointed at the stratosphere",
    copy: "STRATO-P0: no aircraft, no dock, pure observation. Executable ascent, geometry, and budget model with S0 gates.",
    href: `${REPO_URL}/blob/main/docs/prototype-strato-p0.md`,
  },
  {
    date: "August 2026",
    tag: "Engineering",
    title: "Rev-A fabrication pack published",
    copy: "Reproducible CAD, fabrication geometry, and strict evidence reduction for the carrier lineage.",
    href: `${REPO_URL}/pull/3`,
  },
  {
    date: "July 2026",
    tag: "Program",
    title: "CARRIER-P0 programme opened",
    copy: "Closed-loop architecture, payload budget, and the evidence gates that the current programme inherits.",
    href: `${REPO_URL}/pull/1`,
  },
] as const;

export const FOOTER_NAV = [
  {
    heading: "Solutions",
    links: [
      ["The flight loop", "/solutions#loop"],
      ["The flight package", "/commitments#interface"],
      ["Float north star", "/solutions#float"],
    ],
  },
  {
    heading: "Applications",
    links: [
      ["Environment", "/applications#environment"],
      ["Emergency response", "/applications#emergency-response"],
      ["Maritime", "/applications#maritime"],
    ],
  },
  {
    heading: "Company",
    links: [
      ["Manufacturer and operator", "/company"],
      ["Programme gates", "/company#program"],
      ["Careers", "/careers"],
    ],
  },
  {
    heading: "Resources",
    links: [
      ["News", "/resources"],
      ["Engineering repository", REPO_URL],
      ["Design rules", "/commitments#rules"],
    ],
  },
] as const;

/** Order used by the prev / next pager at the foot of every interior page. */
export const PAGE_ORDER = [
  ["/", "Home"],
  ["/solutions", "Solutions"],
  ["/applications", "Applications"],
  ["/commitments", "Commitments"],
  ["/company", "Company"],
  ["/careers", "Careers"],
  ["/resources", "Resources"],
] as const;
