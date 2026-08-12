export const NAV = [
  {
    label: "Solutions",
    href: "/solutions",
    blurb: "One loop: deploy, coordinate, recover, repeat.",
    links: [
      ["The carrier loop", "/solutions#loop", "Four steps, each earned before the next."],
      ["Carrier north star", "/solutions#carrier", "Compute, comms, energy, and recovery aloft."],
    ],
  },
  {
    label: "Applications",
    href: "/applications",
    blurb: "Where the limiting factor is not the aircraft.",
    links: [
      ["Energy", "/applications#energy", "Corridors, substations, offshore assets."],
      ["Emergency response", "/applications#emergency-response", "Sensing that stays overhead."],
      ["Maritime", "/applications#maritime", "Recovery onto a moving deck."],
      ["All six areas", "/applications", "Industry, environment, defence."],
    ],
  },
  {
    label: "Structures",
    href: "/structures",
    blurb: "Thin laminates, and what the analysis changed.",
    links: [
      ["What the analysis changed", "/structures#findings-title", "Seven results, none of them confirmations."],
      ["The parts", "/structures#parts-title", "Four laminates against a mass budget."],
      ["Defect disposition", "/structures#depth-title", "Where a defect sits decides what it costs."],
      ["The package", "/structures#package-title", "Thirteen modules, one gate."],
    ],
  },
  {
    label: "Commitments",
    href: "/commitments",
    blurb: "Evidence before claims, without exception.",
    links: [
      ["Recovery interface", "/commitments#interface", "The P0-A bench article."],
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
      ["Programme gates", "/company#program", "P0-A through P0-D."],
      ["What changed recently", "/resources#news", "Each entry links to the change itself."],
    ],
  },
  {
    label: "Careers",
    href: "/careers",
    blurb: "Small, physical, unglamorous by design.",
    links: [
      ["What we look for", "/careers#roles", "Mechanism, controls, test, simulation."],
      ["How to apply", "/careers#apply", "The repository is the front door."],
    ],
  },
] as const;

export const REPO_URL = "https://github.com/0xSoftBoi/aiur";

export const APPLICATIONS = [
  {
    id: "01",
    slug: "energy",
    accent: "#ff6428",
    title: "Energy",
    copy:
      "Persistent inspection of transmission corridors, substations, and offshore assets without a crew convoy per sortie.",
    image: "/renders/carrier-v1-hero.png",
  },
  {
    id: "02",
    slug: "emergency-response",
    accent: "#e8442b",
    title: "Emergency response",
    copy:
      "Communications and sensing that stay overhead while ground infrastructure is degraded or absent.",
    image: "/renders/carrier-v1-approach.png",
  },
  {
    id: "03",
    slug: "industry-and-logistics",
    accent: "#c8823a",
    title: "Industry and logistics",
    copy:
      "Repeated survey and transfer loops over sites that are far from any runway, hangar, or maintenance bay.",
    image: "/renders/carrier-v1-profile.png",
  },
  {
    id: "04",
    slug: "maritime",
    accent: "#3f8fa8",
    title: "Maritime",
    copy:
      "Launch and recovery over water, where a landing site is a moving deck rather than a prepared surface.",
    image: "/renders/dock-hero.png",
  },
  {
    id: "05",
    slug: "environment",
    accent: "#5d9b6d",
    title: "Environment",
    copy:
      "Long-duration monitoring of forest, coastline, and watershed at a cadence that periodic flights cannot hold.",
    image: "/renders/dock-section.png",
  },
  {
    id: "06",
    slug: "defence-and-security",
    accent: "#7a7fa6",
    title: "Defence and security",
    copy:
      "Fleet coordination at the edge, with the expensive layers kept aloft instead of duplicated in every aircraft.",
    image: "/renders/dock-capture-detail.png",
  },
] as const;

export const SYSTEM_LOOP = [
  {
    index: "01",
    title: "DEPLOY",
    copy: "Release mission aircraft from persistent infrastructure already in the air.",
  },
  {
    index: "02",
    title: "COORDINATE",
    copy: "Keep mission state, communications, and eventually edge compute with the carrier.",
  },
  {
    index: "03",
    title: "RECOVER",
    copy: "Bring the aircraft back through a physical interface that can seat, retain, verify, and release.",
  },
  {
    index: "04",
    title: "REPEAT",
    copy: "Turn a one-way sortie into a reusable loop, then add energy and fleet scale.",
  },
] as const;

/** Mirrors the gate table in hardware/dock/p0a-bench.md. Do not soften. */
export const BENCH_GATE = [
  ["600", "LIFE-TEST CYCLES"],
  ["≥15", "RUN-IN CYCLES / FORCE TREND LEVEL"],
  ["≥5 N", "AXIAL RETENTION / 10 S"],
  ["≥1 N", "LATERAL ±X / ±Y / 10 S"],
  ["10 + 10", "EMERGENCY RELEASES / UNLOADED + LOADED"],
  ["≥2.0", "KEEPER FORCE MARGIN / CLOSE + OPEN"],
] as const;

export const COMPANY = [
  {
    role: "Manufacturer",
    title: "We build the carrier",
    copy:
      "Envelope, gondola, and the recovery interface are designed in the open, dimensioned in CAD, and fabricated to a published Rev pack.",
    facts: [
      ["1", "ACTIVE ARTICLE / CARRIER-P0"],
      ["Rev-B", "CAPTURE GEOMETRY"],
    ],
  },
  {
    role: "Operator",
    title: "We fly the loop",
    copy:
      "The same team runs the bench, the moving dock, and eventually the tethered carrier, so the operating record and the design record are one record.",
    facts: [
      ["4", "PROGRAM GATES / P0-A → P0-D"],
      ["100%", "PUBLIC ENGINEERING LOG"],
    ],
  },
] as const;

export const PROGRAM = [
  ["P0-A", "BENCH CAPTURE", "ACTIVE", "Positive retention + independent physical truth"],
  ["P0-B", "MOVING DOCK", "LOCKED", "Earn dynamic approach only after the bench gate"],
  ["P0-C", "TETHERED CARRIER", "LOCKED", "Integrate the recovery article with buoyant lift"],
  ["P0-D", "TWO AIRCRAFT", "LOCKED", "Prove separation, sequencing, and repeated recovery"],
] as const;

export const NEWS = [
  {
    date: "August 2026",
    tag: "Engineering",
    title: "Rev-A fabrication pack published",
    copy: "Reproducible CAD, fabrication geometry, and strict evidence reduction.",
    href: `${REPO_URL}/pull/3`,
  },
  {
    date: "July 2026",
    tag: "Design",
    title: "P0-A bench article dimensioned",
    copy: "A recovery interface with explicit pass / fail criteria, ahead of any motion.",
    href: `${REPO_URL}/pull/2`,
  },
  {
    date: "July 2026",
    tag: "Program",
    title: "CARRIER-P0 programme opened",
    copy: "Closed-loop architecture, payload budget, and the evidence gates that govern it.",
    href: `${REPO_URL}/pull/1`,
  },
] as const;

export const FOOTER_NAV = [
  {
    heading: "Solutions",
    links: [
      ["The system loop", "/solutions#loop"],
      ["Recovery interface", "/commitments#interface"],
      ["Carrier north star", "/solutions#carrier"],
    ],
  },
  {
    heading: "Applications",
    links: [
      ["Energy", "/applications#energy"],
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
  ["/structures", "Structures"],
  ["/commitments", "Commitments"],
  ["/company", "Company"],
  ["/careers", "Careers"],
  ["/resources", "Resources"],
] as const;
