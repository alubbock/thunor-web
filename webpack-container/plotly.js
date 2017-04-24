var Plotly = require("plotly.js/lib/core");

var modules = [
    require("plotly.js/lib/bar"),
    require("plotly.js/lib/scatter")
];

// TODO: Make 3D plots optional
modules.push(require("plotly.js/lib/surface"));

Plotly.register(modules);

module.exports = Plotly;
