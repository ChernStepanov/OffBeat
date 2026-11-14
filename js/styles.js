// Change styles the curve classifier can name. Keys match `style` in the data contract.
window.OB = window.OB || {};
OB.STYLES = {
  drop:  { name: "HV drop",        color: "#c00000", what: "Downward HV shift. Cause requires independent checks." },
  flood: { name: "HH jump",        color: "#0050c8", what: "Upward HH shift with limited HV change. Flooding unverified." },
  drift: { name: "Slow drift",     color: "#d86b00", what: "Displacement trend. Ground motion requires validated time series." },
  step:  { name: "Step",           color: "#007a1f", what: "Displacement step. Event attribution unverified." }
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
