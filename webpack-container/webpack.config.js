var path = require("path");
var webpack = require("webpack");
var BundleTracker = require("webpack-bundle-tracker");
var ExtractTextPlugin = require("extract-text-webpack-plugin");
var glob = require("glob");
var isDebug = (process.env.DJANGO_DEBUG === undefined ? false : process.env.DJANGO_DEBUG.toLowerCase() === "true");

module.exports = {
    context: __dirname,

    entry: {
        favicons: glob.sync("./thunor/favicons/*"),
        app:    ["expose?pyHTS!./thunor/js/pyhts",
                 "./thunor/css/fonts.css",
                 "./thunor/css/pyhts.css"],

        //TODO: Compile more modules from source, removing unneeded components
        plots:  ["expose?Plotly!plotly.js/dist/plotly-gl3d"],
        raven:  ["expose?Raven!raven-js"],
        vendor: ["expose?jQuery!expose?$!jquery",      // sitewide
                 "bootstrap/dist/js/bootstrap",
                 "bootstrap/dist/css/bootstrap.css",
                 "font-awesome/css/font-awesome.css",

                 "bootstrap-switch", //toggle switch widget
                 "bootstrap-switch/dist/css/bootstrap3/bootstrap-switch.css",

                 "bootstrap-fileinput",//uploader
                 "bootstrap-fileinput/css/fileinput.css",//uploader
                 "bootstrap-select",//plate mapper
                 "bootstrap-select/dist/css/bootstrap-select.css",//plate map
                 "typeahead.js/dist/typeahead.jquery",//plate mapper
                 "jquery-ui-js/widgets/sortable",//plots interface
                 "jquery-ui-js/widgets/selectable",//plate mapper
                 "jquery-ui-css/core.css",
                 "jquery-ui-css/selectable.css",
                 "jquery-ui-css/sortable.css",
                 "jquery-ui-css/theme.css",
                 "jquery-ui-touch-punch",
                 "datatables.net",
                 "datatables.net-bs",
                 "datatables.net-bs/css/dataTables.bootstrap.css",
                 "jquery-file-download"]
    },

    output: {
        path: path.resolve("../_state/webpack-bundles/"),
        filename: "[name]-[chunkhash].js"
    },

    plugins: [
        new BundleTracker({path: __dirname,
            filename: "../_state/webpack-bundles/webpack-stats.json"}),
        new webpack.optimize.OccurenceOrderPlugin(),
        new ExtractTextPlugin("[name]-[chunkhash].css"),
        new webpack.optimize.UglifyJsPlugin({
            compress: isDebug ? false : {
                screw_ie8: true,
                warnings: false
            },
            mangle: !isDebug
        }),
        new webpack.SourceMapDevToolPlugin({
            filename: "[file].map",
            include: /^app/
        })
    ],

    module: {
        loaders: [
            // {
            //     // required by plotly
            //     test: /\.js$/,
            //     // include: [/node_modules\/(plotly|glsl-|gl-|cwise)/],
            //     loader: "ify"
            // },
            {
                test: /\.css$/,
                loader: ExtractTextPlugin.extract("css-loader")
            },
            {
                test: /\.(png|ico)$/,
                include: [
                    path.resolve(__dirname, "thunor/favicons"),
                    path.resolve(__dirname, "../pyhts/static/pyhts/favicons")
                ],
                loader: "file?name=favicon/[name].[ext]"
            },
            {
                test: /\.(png|jpg|gif|ico)$/,
                exclude: /\/favicons\//,
                loader: "file?name=img/[name]-[hash].[ext]"
            },
            {test: /\.(woff|woff2)(\?v=\d+\.\d+\.\d+)?$/, loader: "url?limit=10000&mimetype=application/font-woff&name=font/[name]-[hash].[ext]"},
            {test: /\.ttf(\?v=\d+\.\d+\.\d+)?$/, loader: "url?limit=10000&mimetype=application/octet-stream&name=font/[name]-[hash].[ext]"},
            {test: /\.eot(\?v=\d+\.\d+\.\d+)?$/, loader: "file?name=font/[name]-[hash].[ext]"},
            {test: /\.svg(\?v=\d+\.\d+\.\d+)?$/, loader: "url?limit=10000&mimetype=image/svg+xml&name=font/[name]-[hash].[ext]"}
        ]
    },

    resolve: {
        modulesDirectories: ["node_modules"],
        extensions: ["", ".js"],
        alias: {
            "jquery-ui-js": "jquery-ui/ui",
            "jquery-ui-css": "jquery-ui/themes/base"
        }
    }
};
