// Change styles the curve classifier can name. Keys match `style` in the data contract.
window.OB = window.OB || {};
OB.STYLES = {
  drop:  { name: "HV drop",        color: "#c00000", what: "HV falls relative to peers. Candidate change; clearing or fire requires independent checks." },
  flood: { name: "HH jump",        color: "#0050c8", what: "HH rises relative to peers while HV changes little. Cause unverified; not a confirmed flood." },
  drift: { name: "Slow drift",     color: "#d86b00", what: "Phase drifts month after month. Ground sinking." },
  step:  { name: "Step",           color: "#007a1f", what: "Displacement jumps on one date. Earthquake." }
};

// ESA WorldCover v200 classes (code -> name, map colour from the product legend).
OB.COVER = {
  10: { name: "Tree cover",  color: "#006400" },
  20: { name: "Shrubland",   color: "#ffbb22" },
  30: { name: "Grassland",   color: "#ffff4c" },
  40: { name: "Cropland",    color: "#f096ff" },
  50: { name: "Built-up",    color: "#fa0000" },
  60: { name: "Bare",        color: "#b4b4b4" },
  80: { name: "Water",       color: "#0064c8" },
  90: { name: "Wetland",     color: "#0096a0" },
  95: { name: "Mangroves",   color: "#00cf75" }
};
